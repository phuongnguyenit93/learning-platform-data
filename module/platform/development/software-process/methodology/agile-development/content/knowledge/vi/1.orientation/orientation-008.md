# Điều kiện áp dụng và giới hạn của phát triển Agile

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện những điều kiện khiến cách làm Agile tạo ra giá trị thực trong một dự án phần mềm.
2. Phân biệt **hạn chế vốn có** của Agile với **vấn đề do triển khai Agile chưa đúng**.
3. Đánh giá khi nào nên dùng Scrum, Kanban, các thực hành kỹ thuật của Extreme Programming (XP), hoặc phối hợp Agile với cách quản trị khác.
4. Đề xuất cách thử nghiệm Agile ở phạm vi nhỏ, theo dõi phản hồi và điều chỉnh cách làm dựa trên bằng chứng.

## 1. Agile phù hợp để giải quyết loại vấn đề nào?

**Agile** là tư duy phát triển phần mềm thích ứng: tạo ra những phần sản phẩm có giá trị theo từng bước nhỏ, nhận phản hồi sớm và liên tục điều chỉnh cách thực hiện. Agile khuyến khích hợp tác chặt với người dùng, giao tiếp trực tiếp, phần mềm hoạt động được và khả năng phản ứng với thay đổi. Các giá trị, nguyên tắc Agile không bắt buộc mọi đội dùng cùng một bộ nghi thức hoặc một quy trình duy nhất.

Trong một dự án phần mềm, hai nhóm câu hỏi thường tồn tại song song:

- **Ta nên xây dựng cái gì?** Nhu cầu khách hàng, tính năng nào quan trọng, hành vi người dùng ra sao và giả thuyết kinh doanh nào cần kiểm chứng.
- **Ta có thể xây dựng và giao nó một cách tin cậy không?** Kiến trúc, chất lượng, bảo mật, vận hành, thời gian giao hàng và các ràng buộc khác.

Agile đặc biệt hữu ích khi câu trả lời cho nhóm thứ nhất **còn chưa chắc chắn**, trong khi nhóm thứ hai có thể được cải thiện nhờ kỹ thuật, phối hợp và phản hồi thường xuyên. Nếu chỉ viết kế hoạch chi tiết cho nhiều tháng mà không kiểm tra với người dùng, đội có nguy cơ tối ưu việc giao đúng kế hoạch nhưng giao sai sản phẩm.

**Ví dụ:** Một nền tảng đào tạo trực tuyến cần cải thiện tỷ lệ học viên hoàn thành bài học. Nhóm sản phẩm chưa biết nên ưu tiên lời nhắc, chia bài thành đơn vị ngắn hay bổ sung bài thực hành. Họ có thể thử từng thay đổi trên một nhóm người học, quan sát hành vi và điều chỉnh backlog. Cách làm tăng dần giúp kiểm chứng giả thuyết trước khi đầu tư toàn bộ ngân sách.

Ngược lại, nếu sản phẩm phải được giao theo một bộ đặc tả cố định, phụ thuộc vào lịch chứng nhận bên ngoài hoặc không thể kiểm thử từng phần, lợi ích của những vòng lặp ngắn sẽ bị giới hạn. Điều đó không tự động loại bỏ Agile: nhóm vẫn có thể dùng phản hồi sớm, kiểm thử tự động và minh bạch công việc, nhưng phải thiết kế quy trình cho phù hợp với các ràng buộc thực tế.

## 2. Điều kiện giúp Agile phát huy tác dụng

Không cần tất cả điều kiện đều hoàn hảo ngay từ ngày đầu. Tuy nhiên, nhóm nên nhận diện thiếu hụt và có kế hoạch cải thiện, vì thiếu những điều kiện nền tảng sẽ biến Agile thành chuỗi cuộc họp mà không tạo được khả năng thích ứng.

### 2.1. Có sự bất định đáng để học hỏi

Agile mang lại nhiều lợi ích khi yêu cầu, hành vi người dùng hoặc giải pháp kỹ thuật có thể thay đổi sau mỗi đợt học hỏi. Những dấu hiệu điển hình:

- Các bên liên quan thống nhất được vấn đề cần giải quyết nhưng chưa chắc giải pháp nào hiệu quả.
- Nhóm có thể tạo bản chạy được, nguyên mẫu hoặc thử nghiệm để giảm rủi ro.
- Thị trường, chính sách nội bộ hoặc ưu tiên kinh doanh thường thay đổi.
- Sai lầm về nhu cầu sản phẩm có thể được phát hiện và sửa với chi phí thấp hơn nếu phát hiện sớm.

Nếu toàn bộ đầu ra đã xác định rõ, thay đổi rất hiếm và chi phí tái hoạch định cao, lợi ích của việc điều chỉnh backlog thường xuyên sẽ giảm. Ngược lại, **mức bất định càng cao không có nghĩa càng nên thay đổi vô hạn**: mỗi thay đổi vẫn cần đánh giá giá trị, rủi ro và chi phí.

### 2.2. Có phản hồi đủ nhanh, đủ đáng tin cậy

Một vòng lặp Agile có ý nghĩa khi nhóm có thể:

1. Đưa ra một giả thuyết về giá trị cần tạo.
2. Xây dựng một phần sản phẩm hoặc thí nghiệm đủ để kiểm tra giả thuyết.
3. Thu thập phản hồi từ người dùng, khách hàng hoặc đại diện nghiệp vụ có thẩm quyền.
4. Chuyển kết quả học được thành quyết định cụ thể cho backlog hoặc thiết kế.

Nếu người đại diện chỉ xuất hiện vào ngày nghiệm thu cuối cùng, nhóm khó xác nhận mình đang làm đúng. Thời gian phản hồi có thể dài hơn một Sprint; điều quan trọng là **có nhịp phản hồi phù hợp với tốc độ ra quyết định**, và biết phân biệt phản hồi thực tế với giả định của đội.

**Dấu hiệu cảnh báo:** Cuộc Sprint Review có nhiều slide mô tả tiến độ nhưng không có sản phẩm để xem, không có người đủ quyền phản hồi và không dẫn đến quyết định tiếp theo.

### 2.3. Có thể chia giá trị thành các phần nhỏ để kiểm chứng

Một **increment** (phần sản phẩm tăng thêm) nên có khả năng tích hợp với sản phẩm đang tồn tại và đủ chất lượng để được xem xét, kiểm thử. Không phải increment nào cũng phải được triển khai ra tất cả người dùng ngay lập tức. Trong Scrum, mỗi increment cần đáp ứng Definition of Done để có thể sử dụng được; quyết định phát hành còn phụ thuộc kinh doanh, pháp lý và vận hành.

Một cách chia tốt thường đi theo **lát cắt giá trị từ đầu đến cuối**: người dùng làm được một việc nhỏ, qua giao diện, xử lý nghiệp vụ, dữ liệu và kiểm thử cần thiết. Chia thành các phần “chỉ làm cơ sở dữ liệu”, “chỉ làm giao diện” trong nhiều vòng mà không có luồng sử dụng hoàn chỉnh sẽ trì hoãn việc học từ sản phẩm.

Ví dụ với tính năng ghi danh khóa học:

- Bản đầu: học viên có thể ghi danh một khóa miễn phí và nhìn thấy khóa trong danh sách của mình.
- Bản sau: hỗ trợ kiểm tra điều kiện tiên quyết và thông báo khi không đủ điều kiện.
- Bản tiếp: hỗ trợ mã giảm giá hoặc luồng thanh toán nếu có nhu cầu được xác nhận.

Đội có thể dùng **user story** để diễn đạt giá trị: “Là học viên, tôi muốn ghi danh khóa học miễn phí để bắt đầu học ngay.” Tiêu chí chấp nhận có thể gồm: người học chưa đăng nhập được yêu cầu đăng nhập; ghi danh thành công không tạo bản ghi trùng; trạng thái khóa học hiển thị chính xác.

### 2.4. Đội có đủ năng lực kỹ thuật để thay đổi an toàn

Phản hồi sớm chỉ có giá trị nếu nhóm có thể biến phản hồi thành phần mềm chất lượng mà không tạo chi phí sửa lỗi ngày càng lớn. Những năng lực thường cần:

- Kiểm thử tự động ở mức phù hợp, kiểm thử tích hợp và hồi quy cho đường đi quan trọng.
- Tích hợp thường xuyên, quy trình build nhất quán, môi trường thử nghiệm tin cậy.
- Review mã, quản lý phiên bản, quan sát lỗi và khả năng khôi phục khi phát hành.
- Thiết kế đủ linh hoạt, refactor có kỷ luật, quản lý nợ kỹ thuật.
- Bảo mật, quyền riêng tư và hiệu năng được xem là yêu cầu chất lượng xuyên suốt.

**XP (Extreme Programming)** cung cấp nhiều thực hành kỹ thuật như phát triển hướng kiểm thử (TDD), pair programming, tích hợp liên tục, refactor và thiết kế đơn giản. Những thực hành này giúp giảm chi phí thay đổi, nhưng không phải dự án nào cũng cần áp dụng đồng loạt.

Nếu mỗi lần thay đổi mất ba tuần kiểm thử thủ công và một lần triển khai có nguy cơ làm hỏng toàn bộ hệ thống, đội nên cải thiện nền tảng kỹ thuật song song với việc rút ngắn nhịp lập kế hoạch. Đặt Sprint một tuần tự nó không làm tốc độ giao phần mềm tăng lên.

### 2.5. Quyền quyết định và cơ chế phối hợp rõ ràng

Agile cần một cách xác định **ai quyết định thứ tự ưu tiên**, **ai chịu trách nhiệm chất lượng**, **ai tháo gỡ cản trở**, và **người dùng nào có tiếng nói khi kiểm chứng giá trị**. Trong Scrum, Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; Developers chịu trách nhiệm tạo increment có chất lượng; Scrum Master giúp Scrum được hiểu và áp dụng hiệu quả.

Khả năng tự quản của đội không đồng nghĩa muốn làm gì cũng được. Đội cần biết mục tiêu sản phẩm, giới hạn ngân sách, yêu cầu bắt buộc, tiêu chuẩn chất lượng và những quyết định phải báo cáo hoặc xin phê duyệt.

Ví dụ: Nhóm sản phẩm có thể tự quyết thứ tự thử nghiệm hai giao diện ghi danh trong ngân sách đã cấp, nhưng việc dùng dữ liệu cá nhân mới hoặc thay đổi điều khoản thanh toán vẫn phải qua quy trình phê duyệt phù hợp.

### 2.6. Có sự minh bạch và văn hóa học hỏi

Để cải tiến liên tục, đội cần chia sẻ vấn đề sớm: một tính năng chưa có kết quả, một phụ thuộc bị chặn, một khiếm khuyết, hoặc một ước lượng chưa chắc chắn. Nếu mọi thay đổi kế hoạch đều bị coi là thất bại cá nhân, mọi người có xu hướng che giấu vấn đề và báo cáo tiến độ đẹp.

Những cuộc retrospective có ích khi tạo ra **hành động nhỏ, có người phụ trách và được kiểm tra hiệu quả**. Ví dụ: “Trong hai tuần tới, giới hạn tối đa hai yêu cầu chờ review trên mỗi reviewer và xem liệu thời gian chờ giảm hay không.”

### 2.7. Điều kiện kiểm tra nhanh

| Điều kiện | Câu hỏi kiểm tra | Nếu đang thiếu |
| --- | --- | --- |
| Mục tiêu và giá trị | Có biết người dùng nào, vấn đề nào và kết quả nào cần cải thiện? | Làm rõ mục tiêu, giả thuyết và tiêu chí thành công trước khi tăng tốc thực hiện. |
| Phản hồi | Ai xem được sản phẩm và quyết định điều chỉnh? Bao lâu một lần? | Đặt lịch review với người có thẩm quyền; thử nghiệm với người dùng thật khi phù hợp. |
| Chia nhỏ | Có thể hoàn thiện một luồng có giá trị trong thời gian ngắn? | Chia lát cắt theo hành vi, dùng feature flag hoặc nguyên mẫu để giảm phạm vi. |
| Chất lượng kỹ thuật | Có thể tích hợp, kiểm thử và khôi phục thay đổi an toàn? | Bổ sung kiểm thử, CI, kiểm soát phát hành và thời gian trả nợ kỹ thuật. |
| Quyền quyết định | Ai sắp xếp backlog, phê duyệt rủi ro và giải quyết phụ thuộc? | Làm rõ trách nhiệm, cấp quyền trong giới hạn và đường xử lý xung đột. |
| Đo lường | Có nhìn thấy giá trị, dòng công việc và lỗi sau khi giao? | Thiết lập chỉ số tối thiểu và quan sát kết quả qua nhiều vòng lặp. |

## 3. Giới hạn và đánh đổi cần hiểu đúng

Agile không loại bỏ ràng buộc về ngân sách, hợp đồng, thời hạn, phụ thuộc hay an toàn. Nó giúp nhóm **phát hiện và quản lý** những rủi ro này theo nhịp học hỏi ngắn hơn, trong phạm vi có thể kiểm soát.

### 3.1. Không thể cam kết đồng thời phạm vi cố định, ngày cố định và nguồn lực cố định khi bất định cao

Một dự án có thời hạn cứng, ngân sách cứng và danh sách yêu cầu vẫn đang thay đổi sẽ đối diện đánh đổi. Nếu giữ cả ba, chất lượng hoặc tính bền vững của đội dễ bị ép xuống. Agile không biến các giới hạn này thành vô nghĩa.

Các lựa chọn có trách nhiệm bao gồm:

- **Cố định thời gian và ngân sách, điều chỉnh phạm vi theo giá trị:** Xếp hạng các kết quả và chức năng quan trọng; hoàn thiện phần cốt lõi trước.
- **Cố định phạm vi bắt buộc:** Phân tích phụ thuộc, dự phòng rủi ro và đàm phán thời gian hoặc nguồn lực thực tế.
- **Cố định mốc kiểm định hay pháp lý:** Phát triển tăng dần ở bên trong nhưng bố trí các cổng kiểm tra, bằng chứng và ngày phê duyệt bắt buộc.

Sự minh bạch về mức độ chắc chắn của dự báo quan trọng hơn việc cam kết một con số chính xác giả tạo.

### 3.2. Vòng phản hồi có thể chậm hoặc tốn kém

Không phải sản phẩm nào cũng có thể phát hành và nhận số liệu mỗi vài ngày. Ví dụ:

- Một thay đổi trong thiết bị nhúng cần phần cứng thử nghiệm và nhiều tuần kiểm định.
- Hệ thống giao dịch chịu kiểm toán cần đánh giá bảo mật và phê duyệt độc lập.
- Tích hợp với bên thứ ba phụ thuộc lịch cung cấp môi trường, API hoặc dữ liệu.

Đội vẫn có thể dùng mô phỏng, contract test, nguyên mẫu, kiểm thử tự động, thử nghiệm trong môi trường cô lập và review kiến trúc để rút ngắn **một phần** chu kỳ học hỏi. Tuy vậy, không được coi kết quả mô phỏng là bằng chứng thay thế hoàn toàn cho thử nghiệm bắt buộc.

### 3.3. Tuân thủ, an toàn và truy vết vẫn là yêu cầu bắt buộc

Trong các ngành có kiểm soát chặt, nhóm có thể phải lưu yêu cầu, quyết định thiết kế, ma trận truy vết, bằng chứng kiểm thử, chữ ký phê duyệt và hồ sơ thay đổi. Agile không có nghĩa “không cần tài liệu”: giá trị Agile nhấn mạnh phần mềm hoạt động hơn tài liệu toàn diện **khi phải chọn ưu tiên**, chứ không loại bỏ tài liệu có giá trị pháp lý, vận hành hay chuyển giao.

Cách thích ứng thực tế là đưa việc chuẩn bị bằng chứng và tiêu chí tuân thủ vào Definition of Done, tự động hóa phần thu thập bằng chứng có thể tự động và xác định rõ những cổng phê duyệt độc lập. Tần suất phát hành ra thị trường có thể thấp hơn tần suất tích hợp nội bộ.

### 3.4. Nhiều phụ thuộc làm giảm khả năng tự chủ của một nhóm

Một đội có backlog rõ ràng vẫn bị chặn nếu phải chờ hạ tầng, pháp chế, đội dữ liệu hoặc nhà cung cấp. Càng nhiều lần bàn giao giữa các bộ phận, việc tối ưu riêng một Sprint càng ít phản ánh thời gian từ yêu cầu đến giá trị thực.

Cách giảm giới hạn:

- Tạo nhóm có đủ kỹ năng để hoàn thành lát cắt giá trị khi khả thi.
- Công khai phụ thuộc và thời gian chờ trong backlog hoặc bảng Kanban.
- Ưu tiên thỏa thuận giao diện, dữ liệu thử nghiệm và cách tích hợp sớm.
- Dùng kế hoạch phối hợp đa đội và quản trị phụ thuộc; tránh coi việc tăng số cuộc họp là giải pháp chính.

### 3.5. Thay đổi liên tục có thể phá hỏng khả năng tập trung

Agile khuyến khích phản ứng với thông tin mới, nhưng **không đòi hỏi thay đổi ưu tiên hằng giờ**. Với Scrum, Sprint Goal tạo điểm tựa để đội tập trung trong Sprint; các thay đổi được thương lượng sao cho không gây nguy hiểm cho mục tiêu. Với Kanban, các chính sách chọn việc và giới hạn WIP giúp giữ dòng công việc ổn định.

Nếu lãnh đạo đưa mọi yêu cầu vào trạng thái “khẩn cấp”, nhóm sẽ bắt đầu nhiều việc mà không hoàn thành được bao nhiêu. Cách phản ứng đúng là thống nhất tiêu chí ưu tiên, lớp dịch vụ cho việc khẩn và giới hạn số việc đang làm.

### 3.6. Thiếu thiết kế dài hạn dễ dẫn đến nợ kỹ thuật

“Thiết kế vừa đủ” không có nghĩa bỏ qua kiến trúc, mô hình dữ liệu, bảo mật hay khả năng mở rộng. Với hệ thống phức tạp, một quyết định cấu trúc sai có thể gây chi phí sửa lớn về sau. Nhóm nên dùng các hoạt động khám phá kỹ thuật có mục tiêu (technical spike), review rủi ro, kiểm thử kiến trúc và định hướng dài hạn, rồi cập nhật quyết định từ bằng chứng mới.

Một increment có nhiều tính năng nhưng nhiều lỗi và không thể bảo trì không phải dấu hiệu thành công của Agile. **Chất lượng là điều kiện của khả năng thích ứng**.

### 3.7. Thước đo dễ bị dùng sai

Velocity (số story point hoàn thành trong một Sprint) có thể giúp **chính đội đó** dự báo nội bộ trong một số hoàn cảnh. Nó không phải chỉ số năng suất chung để so sánh hai đội, không đo trực tiếp giá trị khách hàng và không nên biến thành chỉ tiêu thưởng phạt. Nếu chỉ đếm số story hoặc số ticket hoàn thành, nhóm có thể chia việc cho đẹp chỉ số mà không cải thiện kết quả.

Theo dõi đồng thời **kết quả sản phẩm**, **dòng công việc** và **chất lượng** sẽ hữu ích hơn một con số đơn lẻ.

### 3.8. Agile không tự sửa được các vấn đề về tổ chức

Lịch họp Sprint Planning, Daily Scrum, Review và Retrospective không bù được việc thiếu quyền quyết định, mục tiêu mâu thuẫn, nhân sự bị phân bổ vào quá nhiều dự án hoặc văn hóa không cho phép báo cáo rủi ro. Ở tổ chức lớn, việc phối hợp nhiều nhóm còn đòi hỏi chiến lược sản phẩm chung, kiến trúc, tài chính và cách quản lý danh mục đầu tư phù hợp.

Vì vậy, câu hỏi không nên chỉ là “Có làm đủ nghi thức Scrum không?” mà là “Từ phản hồi đến quyết định và từ quyết định đến phần mềm chất lượng, điểm nghẽn thực nằm ở đâu?”

## 4. Lựa chọn Scrum, Kanban, XP hoặc cách phối hợp

Agile là tập hợp giá trị và nguyên tắc; **Scrum**, **Kanban** và **XP** giải quyết các khía cạnh khác nhau. Chúng có thể bổ sung cho nhau khi được sử dụng có chủ đích.

| Bối cảnh công việc | Cách tiếp cận đáng cân nhắc | Vì sao |
| --- | --- | --- |
| Phát triển sản phẩm có mục tiêu thay đổi theo phản hồi, có thể tạo increment mỗi Sprint | **Scrum** | Sprint Goal, Product Backlog, review và retrospective tạo nhịp lập kế hoạch và học hỏi. |
| Bảo trì, hỗ trợ, vận hành hoặc yêu cầu đến liên tục với độ khẩn khác nhau | **Kanban** | Trực quan hóa dòng việc, chính sách rõ ràng, giới hạn WIP và quản lý thời gian chờ. |
| Phần mềm thay đổi thường xuyên nhưng hồi quy, lỗi tích hợp và nợ kỹ thuật cao | **Thực hành XP** | TDD, pair programming, CI và refactor giúp duy trì khả năng thay đổi an toàn. |
| Dự án có chuẩn chứng nhận, hợp đồng cứng hoặc mốc phê duyệt độc lập | **Cách phối hợp (hybrid)** | Tăng dần trong giai đoạn kỹ thuật, đồng thời giữ kế hoạch mốc, hồ sơ và kiểm soát cần thiết. |
| Yêu cầu rất ổn định, đầu ra định trước, thay đổi cực đắt hoặc một lần chuyển đổi không thể đảo ngược | **Cách quản lý theo kế hoạch có kiểm soát** | Đầu tư vào phân tích trước, quản trị phụ thuộc và xác minh chính thức có thể kinh tế hơn; vẫn có thể áp dụng các thực hành kỹ thuật Agile. |

### Minh họa sự khác biệt

**Scrum:** Một nhóm làm sản phẩm đăng ký khóa học đặt Sprint Goal là “Học viên mới có thể tìm và bắt đầu một khóa miễn phí”. Nhóm chọn các Product Backlog Item phục vụ mục tiêu đó, tạo increment đáp ứng Definition of Done và trình diễn kết quả để nhận phản hồi. Nếu kết quả cho thấy người dùng khó tìm khóa phù hợp, thứ tự backlog Sprint sau có thể đổi.

**Kanban:** Nhóm hỗ trợ nền tảng nhận lỗi, yêu cầu truy cập và cập nhật cấu hình mỗi ngày. Họ dùng các cột “Sẵn sàng → Đang làm → Chờ review → Hoàn thành”, giới hạn số việc đang làm, theo dõi thời gian chờ và tìm điểm nghẽn. Kanban không buộc phải chia công việc thành Sprint.

**XP:** Nhóm nâng cấp dịch vụ thanh toán muốn thay đổi nghiệp vụ thường xuyên mà không phá tính năng cũ. Họ dùng test tự động cho quy tắc cốt lõi, CI và refactor từng bước. Các thực hành này có thể được dùng cùng Scrum hoặc Kanban.

**Hybrid:** Dự án hệ thống cần thẩm định độc lập có thể tạo increment và nhận phản hồi thường xuyên trong giai đoạn xây dựng, nhưng chỉ phát hành sau khi hoàn tất báo cáo bảo mật, kiểm định và chấp thuận chính thức. Nhóm cần ghi rõ điều kiện chuyển qua từng mốc; “hybrid” không có nghĩa ghép ngẫu nhiên tất cả nghi thức.

Không nên chọn khung làm việc chỉ vì “công ty nào cũng dùng” hoặc vì chức danh dự kiến. Hãy bắt đầu từ **loại công việc, nhịp phản hồi, mức bất định, rủi ro và khả năng giao phần mềm**.

## 5. Khung ra quyết định trước khi áp dụng

Một quyết định có cơ sở có thể đi qua năm câu hỏi:

1. **Giá trị:** Đầu ra cần tạo tác động gì cho ai? Có cách quan sát tác động đó không?
2. **Bất định:** Phần nào cần khám phá thêm: nhu cầu, trải nghiệm, kiến trúc, hay chính sách?
3. **Vòng phản hồi:** Bằng chứng mới có thể xuất hiện sau bao lâu và với chi phí nào?
4. **Khả năng giao:** Đội có thể hoàn thành một lát cắt kiểm chứng được với chất lượng chấp nhận được không?
5. **Ràng buộc:** Có mốc pháp lý, hợp đồng, an toàn, phụ thuộc hay tài nguyên nào bắt buộc quản trị riêng?

Sơ đồ quyết định minh họa:

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và ràng buộc"] --> B{"Có bất định đáng kể cần học hỏi?"}
    B -- "Có" --> C{"Có thể nhận phản hồi theo từng phần?"}
    B -- "Ít" --> D["Ưu tiên kế hoạch và kiểm soát phù hợp; vẫn cải tiến kỹ thuật"]
    C -- "Có" --> E["Thử nghiệm phát triển tăng dần bằng Scrum hoặc Kanban"]
    C -- "Chưa" --> F["Tìm cách rút ngắn phản hồi: prototype, mô phỏng, kiểm thử"]
    F --> G{"Các ràng buộc bắt buộc được đáp ứng?"}
    E --> G
    G -- "Có" --> H["Chọn nhịp giao, chỉ số và điểm kiểm soát; đánh giá định kỳ"]
    G -- "Chưa" --> I["Kết hợp cổng kiểm định, hồ sơ, kế hoạch phụ thuộc"]
    I --> H
~~~

Đây là **hướng dẫn để thảo luận**, không phải thuật toán tự động phân loại dự án. Một tổ chức có thể dùng Scrum cho khám phá sản phẩm, Kanban cho vận hành và các cổng phê duyệt riêng cho bảo mật trong cùng một hệ thống.

### Tránh chấm điểm phù hợp một cách máy móc

Không nên cộng điểm “có Product Owner”, “có CI”, “có Sprint” rồi kết luận dự án phù hợp Agile theo một ngưỡng tùy ý. Một điều kiện thiếu nghiêm trọng, chẳng hạn không thể tiếp cận người dùng hoặc không có cách xác minh an toàn, có thể quan trọng hơn nhiều điều kiện thuận lợi cộng lại. Thảo luận định tính về **rủi ro, chi phí học hỏi và cách khắc phục** thường đáng tin hơn con số tổng hợp không có cơ sở.

## 6. Tình huống đối chiếu

### Tình huống A — Nền tảng học trực tuyến đang tìm cách tăng tỷ lệ hoàn thành

**Bối cảnh:** Đội biết tỷ lệ học viên bỏ dở cao nhưng chưa rõ nguyên nhân. Họ có thể triển khai tính năng cho một nhóm nhỏ, có dữ liệu sử dụng, nhân sự phát triển và một đại diện sản phẩm đưa ra quyết định.

**Đề xuất:** Tổ chức backlog quanh giả thuyết, ví dụ “Học viên dễ tiếp tục bài đang học sẽ hoàn thành nhiều buổi học hơn”. Đầu tiên hoàn thiện luồng “Tiếp tục học” đơn giản, đo tỷ lệ quay lại bài và phỏng vấn người học. Dùng Scrum nếu nhịp Sprint giúp cả đội tập trung vào một mục tiêu; kết hợp thực hành XP để tự động kiểm thử các luồng học tập hiện có.

**Rủi ro cần tránh:** Coi số lần bấm nút là bằng chứng học viên học tốt hơn. Nên chọn thêm thước đo kết quả có ý nghĩa, theo dõi dữ liệu đủ lâu và xem xét yếu tố gây nhiễu.

### Tình huống B — Nâng cấp hệ thống tính lương với lịch pháp lý cố định

**Bối cảnh:** Quy tắc tính lương có nhiều trường hợp đặc biệt, phải đối soát dữ liệu cũ, bảo đảm quyền riêng tư và hoạt động chính xác vào ngày chuyển đổi. Sai sót ảnh hưởng trực tiếp đến người lao động.

**Đề xuất:** Chia công việc thành các luồng nhỏ để kiểm thử và đối soát liên tục; dùng kiểm thử tự động cho các quy tắc và bộ dữ liệu chuẩn. Đồng thời giữ mốc đóng băng cấu hình, kiểm toán, phương án chuyển đổi/khôi phục, người phê duyệt và bằng chứng nghiệm thu. Có thể dùng Kanban để kiểm soát hàng đợi lỗi, Scrum cho những phần xây dựng phù hợp hoặc cách quản lý phối hợp.

**Rủi ro cần tránh:** Phát hành quy tắc lương chưa kiểm định chỉ để giữ lời hứa “mỗi Sprint phải release”. Increment nội bộ hoàn thành và quyền đưa vào sản xuất là hai quyết định khác nhau.

### Tình huống C — Firmware thiết bị cần chứng nhận trước khi bán

**Bối cảnh:** Mỗi thay đổi có thể cần thử nghiệm trên phần cứng, đánh giá an toàn hoặc chứng nhận. Vòng phản hồi ngoài thực tế dài và tốn kém.

**Đề xuất:** Sử dụng mô phỏng, test tự động và nguyên mẫu để học nhanh ở phần có thể. Xếp lịch đặt thiết bị thử nghiệm và kiểm định sớm, thiết kế cổng phê duyệt rõ ràng, quản trị cấu hình nghiêm ngặt. Một lịch phát hành chính thức cố định có thể hợp lý hơn nhiều lần phát hành nhỏ.

**Rủi ro cần tránh:** Giả định rằng có thể rút thời gian chứng nhận chỉ bằng việc chuyển sang Sprint ngắn hơn.

**Điểm chung của ba tình huống:** Quy trình hiệu quả là quy trình giúp đưa ra quyết định sớm hơn **mà vẫn đáp ứng rủi ro và chất lượng cần thiết**. Tên gọi “Agile” hay “hybrid” không thay thế được bằng chứng.

## 7. Đo xem cách làm có thực sự phù hợp không

Sau vài vòng thực hiện, nhóm cần kiểm chứng liệu cách làm đã chọn có tạo ra kết quả tốt hơn. Có ba nhóm tín hiệu:

| Nhóm tín hiệu | Ví dụ | Cách diễn giải đúng |
| --- | --- | --- |
| **Giá trị sản phẩm** | Tỷ lệ hoàn thành khóa học, tỷ lệ hoàn tất đăng ký, thời gian hoàn thành thao tác, mức độ hài lòng | Gắn với mục tiêu đã đặt, xét chất lượng dữ liệu và bối cảnh thay vì quy mọi thay đổi cho một tính năng. |
| **Dòng công việc** | Lead time, cycle time, throughput, lượng việc đang làm (WIP), tuổi của các việc bị chặn | Quan sát xu hướng và phân bố; tìm nguyên nhân chờ đợi và biến động thay vì chỉ tăng số ticket. |
| **Chất lượng và bền vững** | Lỗi lọt đến sản xuất, thời gian khôi phục, tỷ lệ kiểm thử quan trọng, mức tái mở lỗi, tải công việc của đội | Một dòng việc nhanh nhưng lỗi nhiều hoặc đội kiệt sức không bền vững. |

Một số thuật ngữ:

- **Lead time:** Thời gian từ lúc yêu cầu được ghi nhận theo mốc bắt đầu đã quy ước đến khi được giao/xử lý xong theo mốc kết thúc đã quy ước.
- **Cycle time:** Thời gian từ lúc nhóm bắt đầu thực hiện một hạng mục đến khi hoàn tất theo quy ước. Vì điểm bắt đầu khác nhau, cycle time thường là một phần của lead time.
- **Throughput:** Số hạng mục hoàn thành trong một khoảng thời gian; chỉ có ý nghĩa khi quy ước hạng mục và cách đếm nhất quán.
- **WIP (work in progress):** Số hạng mục đã bắt đầu nhưng chưa hoàn thành.

Ví dụ minh họa: Trong một tháng, đội hoàn thành 20 yêu cầu, nhưng phần lớn thời gian một yêu cầu nằm ở cột “Chờ kiểm thử”. Việc yêu cầu lập trình viên code nhanh hơn có thể không rút ngắn lead time. Hành động tốt hơn là xử lý năng lực kiểm thử, tự động hóa đường kiểm thử lặp lại, làm rõ chính sách chuyển trạng thái hoặc giới hạn WIP trước bước bị nghẽn.

Khi thử một thay đổi quy trình, nên xác định trước giả thuyết và một dấu hiệu quan sát được:

> “Nếu giới hạn tối đa ba việc đang phát triển cùng lúc, thì các hạng mục sẽ ít bị bỏ dở; chúng ta sẽ theo dõi tuổi công việc, cycle time và lỗi trong bốn tuần để quyết định có giữ chính sách này hay không.”

Không có chỉ số đơn lẻ chứng minh “đã Agile”. Một đội giao rất thường xuyên nhưng không nói chuyện với khách hàng có thể đang tối ưu tốc độ sản xuất sai tính năng; một đội có nhiều cuộc review nhưng không kiểm soát được lỗi có thể đang đổi lấy tốc độ bằng nợ kỹ thuật.

## 8. Thử áp dụng trong phạm vi kiểm soát

Khi chưa chắc Agile có phù hợp, cách tiếp cận hữu ích là **thử nghiệm có mục tiêu** thay vì đổi toàn bộ cơ cấu tổ chức ngay lập tức:

1. **Chọn một dòng giá trị cụ thể.** Ví dụ luồng ghi danh khóa học hoặc quy trình sửa lỗi đăng nhập.
2. **Ghi lại điểm xuất phát.** Xác định thời gian chờ, lỗi thường gặp, độ trễ phản hồi và mức độ hài lòng hiện tại; tránh vội gán các con số cho một nguyên nhân duy nhất.
3. **Thống nhất quyền và giới hạn.** Ai quản lý backlog, ai quyết định phát hành, cần bằng chứng bảo mật hay kiểm toán nào?
4. **Chọn thay đổi nhỏ nhất hữu ích.** Có thể là nhịp review hai tuần một lần, một backlog duy nhất, giới hạn WIP, bổ sung CI hoặc đưa tiêu chí chấp nhận vào user story.
5. **Theo dõi qua vài chu kỳ.** Xem cả giá trị, dòng việc và chất lượng. Ghi rõ trở ngại, thay vì chỉ hỏi mọi người có “thích Agile” hay không.
6. **Giữ, điều chỉnh hoặc dừng.** Nếu không cải thiện và chi phí phối hợp quá lớn, thay đổi cách thực hiện; không ép nhóm tiếp tục một bộ nghi thức chỉ để giữ nhãn Agile.

Trong thử nghiệm, nên có **Definition of Done** phù hợp: mã được review, kiểm thử quan trọng đạt yêu cầu, tài liệu vận hành được cập nhật khi cần, không còn lỗi nghiêm trọng đã biết và các yêu cầu bảo mật/tuân thủ liên quan được đáp ứng. Tiêu chí này có thể thay đổi theo mức rủi ro sản phẩm; không nên tự đặt một checklist phình to mà không giúp kiểm soát chất lượng.

## 9. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu phù hợp hơn |
| --- | --- |
| “Agile là không cần lập kế hoạch.” | Agile lập kế hoạch nhiều lần ở các mức khác nhau; kế hoạch được điều chỉnh khi có thông tin mới. |
| “Agile không viết tài liệu.” | Tài liệu cần đủ để phục vụ vận hành, hiểu biết chung, tuân thủ và quản lý rủi ro; tránh tài liệu hình thức không ai sử dụng. |
| “Sprint nào cũng phải phát hành ra khách hàng.” | Increment cần đáp ứng chất lượng; phát hành ra người dùng là quyết định riêng, có thể phụ thuộc phê duyệt hoặc nhu cầu thị trường. |
| “Đổi yêu cầu bất cứ lúc nào mới là Agile.” | Thay đổi cần dựa trên giá trị và bằng chứng, với cơ chế giữ tập trung và quản lý chi phí chuyển ngữ cảnh. |
| “Tăng velocity nghĩa là hiệu suất tốt hơn.” | Velocity không đo trực tiếp giá trị; cần xem kết quả, chất lượng và khả năng dự báo. |
| “Dự án được kiểm soát chặt thì không dùng được bất kỳ thực hành Agile nào.” | Có thể phát triển, kiểm thử và học hỏi tăng dần bên trong những ràng buộc kiểm định và quản trị bắt buộc. |
| “Chỉ cần triển khai Scrum là đã chuyển đổi Agile.” | Scrum cung cấp khung làm việc; phản hồi, năng lực kỹ thuật, quyền quyết định và văn hóa cải tiến mới quyết định kết quả. |

## 10. Câu hỏi tự kiểm tra và thực hành

**Câu 1.** Một đội có Sprint hai tuần nhưng khách hàng chỉ đánh giá sản phẩm sau sáu tháng. Họ gặp trở ngại gì lớn nhất đối với Agile?

*Gợi ý:* Họ đang thiếu vòng phản hồi hữu ích từ người có khả năng xác nhận giá trị. Có thể bổ sung review với người đại diện nghiệp vụ, thử nghiệm nguyên mẫu hoặc kiểm tra các giả định sớm hơn; Sprint ngắn tự nó chưa bảo đảm học hỏi.

**Câu 2.** Dự án có hạn nộp hồ sơ bắt buộc và yêu cầu lưu bằng chứng kiểm thử. Có phải lựa chọn hợp lý duy nhất là bỏ Agile?

*Gợi ý:* Không. Phân biệt increment nội bộ với đợt phát hành chính thức, đưa bằng chứng bắt buộc vào tiêu chí hoàn thành và giữ các mốc phê duyệt. Đánh giá xem phần nào thật sự có thể nhận phản hồi tăng dần.

**Câu 3.** Hai nhóm cùng hoàn thành 40 story point mỗi Sprint. Có thể kết luận họ có năng suất bằng nhau không?

*Gợi ý:* Không. Story point là ước lượng tương đối phụ thuộc từng nhóm và từng cách quy ước; cần xem giá trị bàn giao, chất lượng, lead time và bối cảnh công việc.

**Bài tập ngắn:** Chọn một tính năng trong dự án bạn biết, rồi viết một bản đề xuất 5–8 câu trả lời: (a) người dùng và kết quả mong muốn, (b) giả định lớn nhất cần kiểm tra, (c) increment nhỏ đầu tiên, (d) ai sẽ đưa phản hồi và khi nào, (e) yêu cầu chất lượng hoặc phê duyệt bắt buộc, (f) một chỉ số giá trị và một chỉ số dòng công việc. Từ đó giải thích vì sao chọn Scrum, Kanban, XP hoặc cách phối hợp.

## 11. Ghi nhớ khi lựa chọn

- **Chọn Agile khi cần giảm bất định bằng phản hồi sớm**, và có khả năng tạo, kiểm tra các phần sản phẩm nhỏ một cách đáng tin cậy.
- **Không bỏ qua ràng buộc thật:** ngân sách, thời hạn, tuân thủ, an toàn, phụ thuộc kỹ thuật và tổ chức vẫn cần được quản trị rõ.
- **Khung làm việc phục vụ dòng giá trị:** Scrum giúp quản lý mục tiêu và nhịp học hỏi; Kanban giúp quản lý dòng công việc; các thực hành XP giúp thay đổi phần mềm an toàn hơn.
- **Đánh giá bằng kết quả và chất lượng**, không bằng số buổi họp, tên vai trò, số Sprint hay tốc độ story point.

Một quyết định áp dụng Agile tốt luôn trả lời được hai câu hỏi: **Chúng ta cần học điều gì sớm hơn?** và **Làm sao học được điều đó mà vẫn giữ các cam kết bắt buộc và chất lượng phần mềm?**
