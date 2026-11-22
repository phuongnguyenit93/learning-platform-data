# Vòng đời phát triển: Đưa phân tích rủi ro và tiêu chí chấp nhận vào giai đoạn làm rõ yêu cầu

## 1. Vì sao phải đưa rủi ro và tiêu chí chấp nhận vào giai đoạn yêu cầu?

Nhiều lỗi khó sửa bắt đầu từ một yêu cầu chưa rõ. Câu mô tả như “hệ thống phải xử lý thanh toán nhanh”, “người dùng có thể quản lý lịch hẹn” hoặc “dữ liệu phải an toàn” chưa cho biết hành vi nào được mong đợi, trường hợp nào phải bị từ chối, mức độ chậm nào được chấp nhận hay bằng chứng nào chứng minh yêu cầu đã được đáp ứng. Nếu nhóm phát triển tự diễn giải các câu này theo những cách khác nhau, sản phẩm có thể được xây dựng đúng theo cách hiểu của từng người nhưng vẫn không giải quyết đúng nhu cầu.

Trong **VALIDATION_TESTING_STRATEGY**, làm rõ yêu cầu là điểm bắt đầu để xác định điều cần xác nhận. Phân tích rủi ro cho biết sai lệch nào có hậu quả lớn và cần được ưu tiên. Tiêu chí chấp nhận chuyển kỳ vọng nghiệp vụ thành điều kiện có thể quan sát, kiểm thử và đánh giá. Khi hai hoạt động này diễn ra sớm, nhóm có thể:

- Phát hiện yêu cầu mơ hồ, thiếu trường hợp lỗi hoặc mâu thuẫn trước khi thiết kế và viết mã.
- Tập trung trao đổi vào những tình huống có tác động lớn đối với người dùng, dữ liệu và hoạt động kinh doanh.
- Xác định dữ liệu, trạng thái, phụ thuộc và điều kiện môi trường cần có để kiểm thử.
- Thiết kế test oracle và bằng chứng ngay từ đầu thay vì tìm cách suy ra kết quả sau khi sản phẩm đã hoàn thành.
- Ước lượng công sức dựa trên rủi ro và độ phức tạp thực tế.
- Tạo liên kết truy vết từ mục tiêu người dùng đến yêu cầu, rủi ro, tiêu chí chấp nhận và kiểm thử.

Phân tích rủi ro và tiêu chí chấp nhận không phải thủ tục chỉ làm một lần ở đầu dự án. Chúng cần được xem xét lại khi yêu cầu, kiến trúc, phụ thuộc, dữ liệu hoặc cách sử dụng thay đổi.

## 2. Hiểu mục tiêu trước khi viết tiêu chí

### 2.1. Bắt đầu từ vấn đề của người dùng

Một yêu cầu tốt mô tả vấn đề hoặc kết quả cần đạt, người dùng liên quan và bối cảnh sử dụng. Trước khi viết tiêu chí chấp nhận, nhóm cần làm rõ:

1. Ai gặp vấn đề hoặc cần thực hiện công việc này?
2. Người đó đang cố đạt kết quả gì?
3. Họ thực hiện hành động trong hoàn cảnh nào?
4. Điều gì được xem là kết quả thành công?
5. Nếu hệ thống không thể hoàn thành hành động, người dùng cần biết hoặc làm gì tiếp theo?
6. Có quy tắc, chính sách, nghĩa vụ hoặc ràng buộc nào giới hạn giải pháp không?

Hãy phân biệt nhu cầu với giải pháp được đề xuất. Ví dụ, “cần nút gửi lại thanh toán” là một giải pháp giả định; nhu cầu thực có thể là “người dùng cần biết giao dịch đang ở trạng thái nào sau khi kết nối bị gián đoạn”. Làm rõ nhu cầu giúp nhóm xem xét các cách giải quyết và các trạng thái ngoại lệ trước khi cam kết vào một thiết kế.

### 2.2. Mô tả hành trình và trạng thái

Với mỗi khả năng nghiệp vụ, hãy xác định điểm bắt đầu, các bước chính, dữ liệu đầu vào, kết quả và trạng thái cuối. Với quy trình có nhiều bước, cần làm rõ trạng thái trung gian và điều kiện chuyển trạng thái.

Ví dụ về một yêu cầu đặt lịch:

- Người dùng đã xác thực chọn dịch vụ và khung giờ.
- Hệ thống kiểm tra khung giờ còn khả dụng tại thời điểm xác nhận.
- Hệ thống tạo lịch ở trạng thái chờ thanh toán hoặc đã xác nhận tùy quy tắc nghiệp vụ.
- Kết quả thanh toán có thể đến ngay hoặc qua callback bất đồng bộ.
- Người dùng nhận trạng thái cuối cùng và có thể xem lại lịch đã đặt.

Nếu chỉ ghi “người dùng đặt lịch thành công”, nhóm chưa biết điều gì xảy ra khi hai người chọn cùng khung giờ, thanh toán timeout, callback bị gửi lặp hoặc thông báo không gửi được. Các tình huống đó cần được làm rõ vì chúng ảnh hưởng trực tiếp đến cách thiết kế và kiểm thử.

### 2.3. Xác định phạm vi và giả định

Một yêu cầu cần ghi rõ phần nào thuộc sản phẩm, phần nào phụ thuộc vào hệ thống bên ngoài và điều kiện nào đang được giả định. Chẳng hạn, nhóm có thể chịu trách nhiệm xử lý callback thanh toán nhưng không kiểm soát thời gian phản hồi của nhà cung cấp.

Với mỗi giả định, cần ghi:

- Nội dung giả định và lý do sử dụng.
- Người hoặc nhóm xác nhận giả định.
- Hậu quả nếu giả định không đúng.
- Cách kiểm chứng hoặc thời điểm cần xem xét lại.

Giả định không được kiểm chứng có thể trở thành rủi ro ẩn. Không nên biến một giả định thành tiêu chí chấp nhận mà không xác định nguồn xác nhận.

## 3. Phân tích rủi ro ngay trong quá trình làm rõ yêu cầu

### 3.1. Tìm rủi ro từ hành vi và hậu quả

Phân tích rủi ro bắt đầu bằng câu hỏi: điều gì có thể sai trong hành trình này và nếu xảy ra thì hậu quả là gì? Hãy xem xét các nhóm tình huống:

- **Nghiệp vụ:** tính sai giá, áp dụng sai chính sách, chuyển trạng thái sai hoặc bỏ qua điều kiện bắt buộc.
- **Dữ liệu:** mất dữ liệu, ghi trùng, sai lệch, không nhất quán hoặc không thể khôi phục.
- **Quyền và bảo mật:** người dùng xem hoặc thay đổi dữ liệu không thuộc quyền, lộ bí mật hoặc bỏ qua kiểm soát truy cập.
- **Tích hợp:** API hoặc event thay đổi hợp đồng, phụ thuộc timeout, callback lặp hoặc sự kiện đến sai thứ tự.
- **Hiệu năng và tải:** thời gian phản hồi vượt ngưỡng, cạn tài nguyên hoặc suy giảm khi nhiều người dùng đồng thời.
- **Khả năng phục hồi:** dịch vụ gián đoạn, retry gây tác dụng phụ hoặc hệ thống không thể tiếp tục sau lỗi.
- **Trải nghiệm và khả năng truy cập:** người dùng không hiểu trạng thái, không thể hoàn thành hành trình hoặc không sử dụng được bằng thiết bị/công nghệ hỗ trợ.
- **Tuân thủ và quyền riêng tư:** xử lý dữ liệu không đúng mục đích, thời hạn lưu giữ hoặc yêu cầu pháp lý áp dụng.

Không phải mọi nhóm đều liên quan đến mọi tính năng. Hãy dùng bối cảnh sản phẩm, dữ liệu và người dùng để chọn rủi ro có căn cứ.

### 3.2. Mô tả rủi ro theo cấu trúc rõ ràng

Một bản ghi rủi ro hữu ích nên có:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Điều kiện hoặc nguyên nhân | Trong hoàn cảnh nào sai lệch có thể xuất hiện? |
| Sự kiện hoặc lỗi | Hệ thống có thể làm gì sai hoặc không làm được điều gì? |
| Hậu quả | Người dùng, dữ liệu, tài chính hoặc hoạt động bị ảnh hưởng ra sao? |
| Kiểm soát hiện có | Có quy tắc, xác nhận, kiểm tra hoặc cơ chế phục hồi nào đang giảm rủi ro? |
| Khoảng trống | Điều gì chưa được xác nhận hoặc chưa được kiểm soát? |
| Chủ sở hữu | Ai chịu trách nhiệm quyết định và xử lý rủi ro? |

Ví dụ:

> Khi hai người dùng xác nhận cùng một khung giờ gần như đồng thời, hệ thống có thể tạo hai lịch hẹn cho cùng một tài nguyên. Điều này làm khách hàng đến trùng giờ và gây gián đoạn vận hành. Cần xác nhận tính duy nhất ở thao tác ghi cuối cùng, không chỉ ở bước hiển thị danh sách khung giờ.

Mô tả này xác định được điều kiện, sai lệch, hậu quả và gợi ý kiểm soát cần có. Nó cũng giúp QA thiết kế kịch bản đồng thời và oracle phù hợp.

### 3.3. Xếp hạng rủi ro để ưu tiên trao đổi

Nhóm có thể sử dụng thang điểm định tính hoặc định lượng. Một mô hình đơn giản dùng ba yếu tố:

- **Tác động (Impact):** mức độ nghiêm trọng nếu lỗi xảy ra.
- **Khả năng xảy ra (Likelihood):** mức độ thường gặp hoặc khả năng kích hoạt điều kiện gây lỗi.
- **Khả năng phát hiện (Detectability):** mức độ khó nhận ra lỗi trước khi gây hậu quả; điểm cao biểu thị khó phát hiện.

Có thể tính điểm ưu tiên tham khảo:

\[
R = I \times L \times D
\]

Với mỗi yếu tố được chấm từ 1 đến 5, R nằm trong khoảng 1 đến 125. Thang điểm và ngưỡng cần được nhóm thống nhất; đây là công cụ hỗ trợ thảo luận, không phải xác suất thống kê hay tiêu chuẩn phổ quát.

| Mức ưu tiên tham khảo | Ý nghĩa | Cách xử lý ở giai đoạn yêu cầu |
| --- | --- | --- |
| Thấp | Tác động nhỏ, dễ phát hiện và dễ khôi phục | Làm rõ hành vi cơ bản và giữ kiểm tra nền tảng |
| Trung bình | Có ảnh hưởng đáng kể trong một số điều kiện | Bổ sung trường hợp biên, lỗi phổ biến và tiêu chí quan sát |
| Cao | Có thể ảnh hưởng lớn đến người dùng, dữ liệu hoặc nghiệp vụ | Yêu cầu tiêu chí cụ thể, kiểm thử nhiều ranh giới và xác nhận độc lập khi cần |
| Rất cao | Hậu quả nghiêm trọng hoặc khó phát hiện, có thể liên quan yêu cầu bắt buộc | Ưu tiên làm rõ trước khi triển khai; xác định kiểm soát, người chấp nhận rủi ro và điều kiện phát hành |

Không để điểm tổng che khuất một tác động đặc biệt nghiêm trọng. Rủi ro liên quan đến an toàn, quyền riêng tư, giao dịch tài chính hoặc nghĩa vụ pháp lý có thể cần mức xử lý bắt buộc dù khả năng xảy ra được đánh giá thấp.

### 3.4. Đặt câu hỏi theo rủi ro

Trong workshop làm rõ yêu cầu, hãy dùng câu hỏi cụ thể thay vì hỏi chung chung “có trường hợp lỗi nào không?”:

- Nếu người dùng gửi cùng một yêu cầu hai lần thì kết quả phải như thế nào?
- Nếu một dịch vụ phụ thuộc không phản hồi thì trạng thái nào được hiển thị?
- Nếu dữ liệu đầu vào thiếu, sai định dạng hoặc vượt giới hạn thì hệ thống phản hồi ra sao?
- Nếu hai người dùng thao tác đồng thời trên cùng tài nguyên thì quy tắc ưu tiên là gì?
- Nếu một sự kiện đến trễ hoặc bị gửi lặp thì hệ thống phải bảo toàn bất biến nào?
- Ai được phép xem, tạo, sửa hoặc hủy dữ liệu?
- Người dùng có thể khôi phục hành động sau khi mất kết nối không?
- Có giới hạn thời gian, tải, dung lượng hoặc độ chính xác nào phải đáp ứng?
- Bằng chứng nào cho thấy kết quả cuối đã được ghi nhận?

Những câu hỏi này biến rủi ro thành các quyết định nghiệp vụ có thể xác nhận.

## 4. Viết tiêu chí chấp nhận có thể kiểm thử

### 4.1. Đặc điểm của tiêu chí chấp nhận tốt

Tiêu chí chấp nhận (acceptance criteria) mô tả điều kiện để một yêu cầu được xem là đáp ứng mục tiêu. Một tiêu chí tốt nên:

- **Cụ thể:** nêu rõ vai trò, điều kiện, hành động và kết quả.
- **Có thể quan sát:** kết quả có thể được kiểm tra qua UI, API, trạng thái nghiệp vụ hoặc bằng chứng phù hợp.
- **Có thể kiểm thử:** có dữ liệu đầu vào và điều kiện để tái hiện.
- **Không mâu thuẫn:** thống nhất với quy tắc nghiệp vụ và các tiêu chí liên quan.
- **Có giới hạn rõ:** xác định ngưỡng, thời hạn, phạm vi hoặc điều kiện ngoại lệ nếu cần.
- **Tập trung vào kết quả:** mô tả điều sản phẩm phải làm, tránh áp đặt chi tiết triển khai khi không cần thiết.

Tránh những từ không có định nghĩa như “nhanh”, “dễ dàng”, “an toàn”, “ổn định”, “hợp lý” nếu chúng không được giải thích bằng điều kiện hoặc ngưỡng có thể đánh giá.

### 4.2. Cấu trúc Given–When–Then

Một cách viết phổ biến là Given–When–Then:

- **Given:** bối cảnh hoặc trạng thái ban đầu.
- **When:** hành động hoặc sự kiện kích hoạt.
- **Then:** kết quả quan sát được.

Ví dụ:

~~~gherkin
Feature: Đặt lịch hẹn

  Scenario: Người dùng đặt một khung giờ còn trống
    Given người dùng đã đăng nhập
      And khung giờ được chọn còn khả dụng
    When người dùng xác nhận đặt lịch
    Then hệ thống tạo một lịch hẹn cho người dùng đó
      And lịch hẹn có mã tham chiếu duy nhất
      And khung giờ không còn khả dụng cho yêu cầu đặt trùng
~~~

Given–When–Then giúp các bên thảo luận cùng một tình huống. Nó không bắt buộc phải được tự động hóa bằng một framework BDD cụ thể. Giá trị chính là làm rõ điều kiện, hành động và kết quả.

### 4.3. Bổ sung trường hợp âm tính và biên

Tiêu chí chỉ mô tả đường thành công thường để lại nhiều khoảng trống. Với mỗi hành vi quan trọng, cần xem xét:

- Đầu vào không hợp lệ hoặc thiếu trường bắt buộc.
- Người dùng chưa xác thực hoặc không đủ quyền.
- Tài nguyên không tồn tại, đã bị xóa hoặc không còn khả dụng.
- Trạng thái hiện tại không cho phép hành động.
- Giới hạn tối thiểu, tối đa, thời gian hết hạn và giá trị sát biên.
- Yêu cầu lặp, thao tác đồng thời, timeout và retry.
- Phụ thuộc bên ngoài trả lỗi, phản hồi trễ hoặc dữ liệu không hợp lệ.
- Hành động bị gián đoạn giữa chừng và cách tiếp tục hoặc khôi phục.

Không cần viết một scenario riêng cho mọi tổ hợp dữ liệu. Hãy chọn trường hợp đại diện theo rủi ro, quy tắc nghiệp vụ và kỹ thuật thiết kế kiểm thử.

### 4.4. Tiêu chí phi chức năng phải có điều kiện đo

Một số yêu cầu không thể mô tả chỉ bằng trạng thái đúng/sai. Chúng cần điều kiện đo cụ thể:

| Yêu cầu mơ hồ | Cách làm rõ có thể kiểm thử |
| --- | --- |
| Trang phải tải nhanh | Xác định loại trang, thiết bị/mạng, dữ liệu, tải đồng thời và phân vị thời gian phản hồi mục tiêu |
| Hệ thống phải ổn định | Xác định thời gian quan sát, tỷ lệ lỗi tối đa, mức sẵn sàng và hành vi khi phụ thuộc lỗi |
| Dữ liệu phải an toàn | Xác định vai trò, quyền, dữ liệu nhạy cảm, thao tác được phép và kiểm soát cần chứng minh |
| Có thể khôi phục khi lỗi | Xác định loại lỗi, dữ liệu cần bảo toàn, thời gian phục hồi và trạng thái sau phục hồi |
| Giao diện dễ sử dụng | Xác định nhóm người dùng, nhiệm vụ, điều kiện hoàn thành và phương pháp đánh giá trải nghiệm |

Các ngưỡng cụ thể phải đến từ mục tiêu sản phẩm, dữ liệu sử dụng, thỏa thuận dịch vụ hoặc yêu cầu bắt buộc. Không tự đặt một con số tùy ý rồi xem đó là cam kết của sản phẩm.

## 5. Liên kết rủi ro với tiêu chí chấp nhận và kiểm thử

Một rủi ro chỉ thực sự được xử lý khi có quyết định kiểm soát và bằng chứng tương ứng. Hãy nối các yếu tố theo chuỗi:

**Mục tiêu người dùng → yêu cầu → rủi ro → tiêu chí chấp nhận → test oracle → kịch bản kiểm thử → bằng chứng → quyết định.**

~~~mermaid
flowchart TD
    GOAL["Mục tiêu người dùng"] --> REQ["Yêu cầu được làm rõ"]
    REQ --> RISK["Tình huống rủi ro"]
    RISK --> CTRL["Quy tắc / kiểm soát cần có"]
    CTRL --> AC["Tiêu chí chấp nhận"]
    AC --> ORACLE["Test oracle và dữ liệu"]
    ORACLE --> TEST["Kịch bản kiểm thử"]
    TEST --> EVIDENCE["Kết quả và bằng chứng"]
    EVIDENCE --> DECISION["Đánh giá đạt / chưa đạt<br/>và rủi ro còn lại"]
    DECISION -->|"Phát hiện khoảng trống"| REQ
~~~

### 5.1. Ma trận truy vết mẫu

| Mục tiêu / yêu cầu | Rủi ro | Tiêu chí chấp nhận | Kiểm thử và bằng chứng |
| --- | --- | --- | --- |
| Người dùng đặt được khung giờ khả dụng | Hai yêu cầu đồng thời tạo lịch trùng | Tại một thời điểm chỉ một lịch được xác nhận cho tài nguyên và khung giờ không cho phép đặt trùng | Kiểm thử đồng thời; xác nhận kết quả API và trạng thái cuối |
| Giao dịch được ghi nhận đúng | Callback thanh toán lặp tạo giao dịch trùng | Một mã giao dịch chỉ làm thay đổi trạng thái nghiệp vụ một lần theo hợp đồng | Gửi callback lặp; kiểm tra idempotency và đối soát |
| Người dùng chỉ xem dữ liệu của mình | Truy cập trái phép dữ liệu người khác | Người dùng không có quyền nhận dữ liệu hoặc thực hiện thao tác trên tài nguyên của người khác | Kiểm thử âm tính theo vai trò; kiểm tra phản hồi và log truy cập |
| Người dùng nhận trạng thái kịp thời | Event bị trễ làm trạng thái chờ kéo dài | Trạng thái được cập nhật trong thời hạn đã thống nhất hoặc hiển thị trạng thái chờ cùng hướng xử lý rõ ràng | Kiểm thử bất đồng bộ; đo thời gian và kiểm tra trạng thái cuối |

Ma trận này giúp tìm ra các hàng chưa có tiêu chí hoặc chưa có kiểm thử. Nó cũng hỗ trợ đánh giá tác động khi một yêu cầu thay đổi: nhóm có thể xác định rủi ro, kịch bản và bằng chứng nào cần xem xét lại.

### 5.2. Xác định oracle trước khi thực thi

Oracle là căn cứ để kết luận kết quả thực tế có đúng hay không. Oracle có thể là:

- Giá trị hoặc trạng thái mong đợi.
- Quy tắc nghiệp vụ hoặc bảng quyết định.
- Bất biến dữ liệu, chẳng hạn mã giao dịch duy nhất.
- Hợp đồng API/event và mã lỗi.
- Điều kiện thời gian hoặc giới hạn hiệu năng.
- Bằng chứng từ một hệ thống độc lập, như kết quả đối soát.

Nếu không thể xác định oracle, yêu cầu chưa đủ rõ để tạo kết quả pass/fail đáng tin cậy. Cần trao đổi với chủ sản phẩm hoặc chuyên gia nghiệp vụ trước khi tự suy diễn kết quả.

## 6. Tổ chức workshop làm rõ yêu cầu

### 6.1. Thành phần tham gia

Một buổi làm rõ hiệu quả nên có đủ góc nhìn để thống nhất hành vi và cách xác nhận:

| Vai trò | Đóng góp |
| --- | --- |
| Chủ sản phẩm / chuyên gia nghiệp vụ | Mục tiêu, chính sách, quy tắc và mức chấp nhận rủi ro |
| Đại diện người dùng | Bối cảnh sử dụng, trở ngại và kết quả mong đợi |
| Phân tích nghiệp vụ | Làm rõ phạm vi, luồng, thuật ngữ và câu hỏi còn mở |
| Kiến trúc sư / nhà phát triển | Khả năng kỹ thuật, phụ thuộc, dữ liệu và tác động kiến trúc |
| QA / kỹ sư kiểm thử | Trường hợp lỗi, oracle, dữ liệu và khả năng kiểm thử |
| Bảo mật / vận hành khi phù hợp | Rủi ro truy cập, dữ liệu, khả năng quan sát và phục hồi |

Không cần mời tất cả vai trò vào mọi buổi họp. Hãy mời những người có thể giải quyết câu hỏi hoặc chấp nhận rủi ro liên quan.

### 6.2. Agenda đề xuất

1. Nêu vấn đề người dùng và kết quả nghiệp vụ cần đạt.
2. Xác nhận thuật ngữ, tác nhân, phạm vi và giả định.
3. Đi qua luồng chính và các trạng thái quan trọng.
4. Liệt kê tình huống lỗi, trường hợp biên và hậu quả.
5. Xếp hạng rủi ro và xác định những điểm cần quyết định.
6. Viết hoặc chỉnh sửa tiêu chí chấp nhận.
7. Xác định oracle, dữ liệu, phụ thuộc và môi trường cần có.
8. Ghi câu hỏi còn mở, chủ sở hữu và thời hạn trả lời.

### 6.3. Kết quả đầu ra cần lưu

Sau buổi làm rõ, nhóm nên có:

- Yêu cầu đã thống nhất và thuật ngữ được định nghĩa.
- Luồng nghiệp vụ cùng trạng thái chính.
- Danh sách rủi ro, mức ưu tiên và người chịu trách nhiệm.
- Tiêu chí chấp nhận cho hành vi thành công, lỗi và trường hợp biên quan trọng.
- Giả định, phụ thuộc và giới hạn phạm vi.
- Câu hỏi chưa giải quyết, người phụ trách và thời hạn.
- Liên kết truy vết tới kịch bản kiểm thử hoặc hạng mục cần tạo.

Một cuộc họp kết thúc mà các câu hỏi quan trọng chưa có người chịu trách nhiệm vẫn để lại rủi ro. Hãy ghi rõ điều kiện nào đang chặn thiết kế hoặc kiểm thử và cách xử lý tiếp theo.

## 7. Ví dụ đầy đủ: làm rõ yêu cầu đặt lịch và thanh toán

### 7.1. Yêu cầu ban đầu

> Người dùng có thể đặt lịch và thanh toán trực tuyến. Hệ thống phải xử lý nhanh và không tạo lỗi.

Mô tả này chưa xác định khung giờ được giữ vào lúc nào, khi nào lịch được xác nhận, cách xử lý thanh toán chưa rõ trạng thái, thế nào là nhanh và “không tạo lỗi” có nghĩa gì.

### 7.2. Câu hỏi làm rõ

- Khung giờ được giữ trước thanh toán hay chỉ sau khi thanh toán thành công?
- Nếu hai người cùng chọn một khung giờ, quy tắc quyết định là gì?
- Thanh toán có trạng thái pending không? Ai xác nhận trạng thái cuối?
- Nếu người dùng đóng trình duyệt hoặc mất mạng sau khi gửi yêu cầu thì có thể tra cứu giao dịch bằng cách nào?
- Callback có thể được gửi nhiều lần hoặc đến trễ không?
- Khi thanh toán thất bại, khung giờ được giải phóng khi nào?
- Người dùng được phép hủy hoặc đổi lịch trong điều kiện nào?
- Mốc thời gian phản hồi và thời hạn cập nhật trạng thái được xác định dựa trên mục tiêu nào?

### 7.3. Rủi ro và tiêu chí chấp nhận

| Rủi ro | Ưu tiên | Tiêu chí chấp nhận đề xuất cần được nghiệp vụ xác nhận |
| --- | --- | --- |
| Hai người được xác nhận cùng một khung giờ | Cao | Một khung giờ không thể được xác nhận cho hai lịch trùng nhau theo quy tắc tài nguyên |
| Callback lặp làm ghi nhận thanh toán hai lần | Cao | Callback lặp của cùng giao dịch không tạo tác dụng phụ nghiệp vụ lần thứ hai |
| Timeout bị hiểu nhầm là thanh toán thất bại | Cao | Trạng thái chưa xác định được giữ và đối soát theo quy trình; không tự ghi nhận thất bại cuối khi chưa có căn cứ |
| Lịch đã thanh toán nhưng không cập nhật | Cao | Hệ thống cập nhật trong thời hạn được thống nhất hoặc hiển thị trạng thái chờ và hướng hỗ trợ |
| Người dùng không biết lịch đã được tạo | Trung bình | Sau thao tác, người dùng nhận mã tham chiếu và có thể tra cứu trạng thái |

Các mức ưu tiên trong bảng là ví dụ. Chủ sản phẩm và người chịu trách nhiệm rủi ro cần xác nhận mức thực tế và ngưỡng thời gian trước khi đưa vào đặc tả.

### 7.4. Ví dụ tiêu chí Given–When–Then

~~~gherkin
Feature: Thanh toán cho lịch hẹn

  Scenario: Callback thành công được gửi lặp
    Given một lịch hẹn đang chờ xác nhận thanh toán
      And giao dịch có mã tham chiếu duy nhất
    When hệ thống nhận cùng callback thành công hai lần
    Then lịch hẹn chỉ chuyển sang trạng thái đã thanh toán một lần
      And giao dịch không bị ghi nhận trùng
      And cả hai lần xử lý có thể được truy vết bằng mã tương quan

  Scenario: Nhà cung cấp chưa trả kết quả cuối
    Given người dùng đã gửi yêu cầu thanh toán
      And nhà cung cấp chưa xác nhận thành công hoặc thất bại
    When thời hạn chờ phản hồi đồng bộ kết thúc
    Then hệ thống giữ trạng thái chưa xác định theo quy tắc
      And người dùng có thể tra cứu trạng thái hoặc được hướng dẫn tiếp theo
      And hệ thống không tự tạo giao dịch thanh toán thứ hai
~~~

### 7.5. Kịch bản kiểm thử và bằng chứng

- Kiểm thử thành phần xác nhận quy tắc chuyển trạng thái và xử lý callback lặp.
- Kiểm thử tích hợp xác nhận transaction, idempotency và trạng thái dữ liệu.
- Kiểm thử hợp đồng xác nhận schema callback và mã phản hồi.
- Kiểm thử hệ thống xác nhận hành trình từ chọn khung giờ đến tra cứu lịch.
- Kiểm thử bất đồng bộ xác nhận callback trễ, retry và đối soát.
- Kiểm thử hiệu năng xác nhận ngưỡng phản hồi dưới tải đại diện đã thống nhất.

Bằng chứng cần gắn với phiên bản sản phẩm, dữ liệu, môi trường, mã giao dịch và correlation ID. Một phản hồi HTTP thành công không đủ để chứng minh toàn bộ lịch và thanh toán đã ở trạng thái đúng.

## 8. Quản lý thay đổi yêu cầu và tiêu chí chấp nhận

Yêu cầu thường thay đổi khi nhóm hiểu rõ hơn về người dùng, phát hiện ràng buộc kỹ thuật hoặc nhận phản hồi từ vận hành. Mỗi thay đổi có thể làm thay đổi rủi ro và bộ kiểm thử.

Khi một yêu cầu thay đổi:

1. Ghi phiên bản và lý do thay đổi.
2. Xác định hành trình, thành phần và phụ thuộc bị ảnh hưởng.
3. Chấm lại rủi ro nếu tác động, khả năng xảy ra hoặc khả năng phát hiện đã thay đổi.
4. Cập nhật tiêu chí chấp nhận và oracle.
5. Đánh giá kịch bản, dữ liệu và bằng chứng cần chạy lại.
6. Thông báo cho chủ sở hữu liên quan và ghi nhận quyết định.

Không sửa tiêu chí chấp nhận chỉ để làm cho một bài kiểm thử đang thất bại trở thành pass. Nếu kỳ vọng nghiệp vụ thay đổi, cần có người có thẩm quyền xác nhận, lý do và ảnh hưởng đến người dùng hoặc hợp đồng.

### 8.1. Quản lý câu hỏi còn mở

Một yêu cầu có thể chưa được làm rõ hoàn toàn. Hãy phân loại câu hỏi:

- **Chặn thiết kế:** chưa thể chọn kiến trúc hoặc hợp đồng khi chưa có câu trả lời.
- **Chặn kiểm thử:** chưa thể xác định oracle, dữ liệu hoặc kết quả mong đợi.
- **Chấp nhận giả định có điều kiện:** có thể tiếp tục với giả định đã ghi nhận, có chủ sở hữu và thời hạn xác minh.
- **Không ảnh hưởng phạm vi hiện tại:** có thể đưa vào backlog với lý do và thời điểm xem xét.

Mỗi câu hỏi cần có người trả lời, ngày cần có kết quả và tác động nếu trễ. Điều này giúp nhóm tránh xem một yêu cầu chưa rõ là đã sẵn sàng chỉ vì nó đã được đưa vào kế hoạch.

## 9. Định nghĩa mức sẵn sàng của yêu cầu

Trước khi chuyển một yêu cầu sang thiết kế hoặc phát triển, nhóm có thể dùng checklist sẵn sàng:

- [ ] Vấn đề người dùng và kết quả mong muốn đã rõ.
- [ ] Tác nhân, phạm vi và thuật ngữ đã được thống nhất.
- [ ] Luồng chính, trạng thái và quy tắc nghiệp vụ đã được mô tả.
- [ ] Tình huống lỗi và rủi ro quan trọng đã được xem xét.
- [ ] Tiêu chí chấp nhận cụ thể, có thể quan sát và kiểm thử.
- [ ] Yêu cầu phi chức năng có điều kiện đo hoặc nguồn xác định ngưỡng.
- [ ] Oracle và dữ liệu cần thiết đã được xác định hoặc có kế hoạch tạo.
- [ ] Phụ thuộc, giả định và giới hạn đã được ghi nhận.
- [ ] Câu hỏi chặn có người chịu trách nhiệm và thời hạn xử lý.
- [ ] Yêu cầu có thể truy vết đến rủi ro và kế hoạch kiểm thử.

Nếu còn thiếu một điều kiện quan trọng, nhóm cần quyết định rõ có thể tiếp tục với giả định được kiểm soát hay phải làm rõ trước. Không nên dùng một nhãn “ready” chung để che giấu những điểm chưa có câu trả lời.

## 10. Mẫu ghi nhận phân tích rủi ro và tiêu chí chấp nhận

Có thể sử dụng mẫu sau trong refinement hoặc workshop:

~~~text
ID / tên yêu cầu:
Mục tiêu người dùng:
Tác nhân và bối cảnh:
Luồng chính:
Trạng thái và quy tắc nghiệp vụ:
Phạm vi / phụ thuộc:

Tình huống rủi ro:
Điều kiện hoặc nguyên nhân:
Sai lệch có thể xảy ra:
Hậu quả:
Tác động / khả năng xảy ra / khả năng phát hiện:
Kiểm soát hiện có:
Chủ sở hữu rủi ro:

Tiêu chí chấp nhận:
Given:
When:
Then:
Trường hợp lỗi / biên:
Oracle và dữ liệu:
Bằng chứng cần thu thập:

Giả định:
Câu hỏi còn mở:
Người phụ trách và thời hạn:
Liên kết kịch bản kiểm thử:
Phiên bản / lịch sử thay đổi:
~~~

Mẫu này nên đủ ngắn để dùng trong công việc hàng ngày nhưng vẫn ghi lại các quyết định quan trọng. Có thể liên kết đến tài liệu chi tiết thay vì sao chép cùng một nội dung ở nhiều nơi.

## 11. Checklist cuối buổi làm rõ yêu cầu

- [ ] Nhóm hiểu vấn đề người dùng thay vì chỉ ghi lại giải pháp được đề xuất.
- [ ] Hành trình, trạng thái, dữ liệu và ranh giới hệ thống đã được làm rõ.
- [ ] Rủi ro được mô tả bằng điều kiện, sai lệch và hậu quả cụ thể.
- [ ] Rủi ro quan trọng có mức ưu tiên và chủ sở hữu.
- [ ] Tiêu chí chấp nhận bao gồm đường thành công, lỗi và biên có ý nghĩa.
- [ ] Các tiêu chí có thể quan sát và có oracle phù hợp.
- [ ] Yêu cầu phi chức năng có ngưỡng hoặc cách đo được thống nhất.
- [ ] Giả định và câu hỏi còn mở có người phụ trách cùng thời hạn.
- [ ] Kịch bản kiểm thử và bằng chứng có thể truy vết đến yêu cầu.
- [ ] Thay đổi yêu cầu có cách đánh giá lại rủi ro và phạm vi kiểm thử.

Đưa phân tích rủi ro và tiêu chí chấp nhận vào giai đoạn làm rõ yêu cầu giúp nhóm thống nhất sớm điều gì quan trọng, điều gì có thể sai và cần bằng chứng nào để xác nhận. Khi các quyết định này được ghi lại và duy trì xuyên suốt vòng đời phát triển, kiểm thử trở thành một phần của quá trình định nghĩa sản phẩm, hỗ trợ phát hiện vấn đề sớm và đưa ra quyết định phát hành có căn cứ.
