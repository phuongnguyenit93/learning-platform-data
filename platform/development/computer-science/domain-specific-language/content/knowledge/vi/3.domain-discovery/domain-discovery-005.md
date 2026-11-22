# Ma trận quyết định miền

## 1. Vai trò của ma trận trong quá trình khám phá miền

Khi xây dựng ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL), nhóm phát triển thường phải đưa ra nhiều quyết định ngay từ giai đoạn khám phá miền: nên tập trung vào nhóm công việc nào, khái niệm nào thuộc phạm vi ngôn ngữ, yêu cầu nào cần hỗ trợ trước, và trường hợp nào nên để ngôn ngữ chủ hoặc công cụ khác xử lý. Những quyết định này ảnh hưởng trực tiếp đến độ lớn của DSL, cách người dùng học và sử dụng nó, cũng như chi phí triển khai và bảo trì.

Thông tin khám phá miền thường đến từ nhiều nguồn: phỏng vấn người dùng, quan sát quy trình, tài liệu, mã nguồn hiện có, cấu hình, ví dụ đầu vào và kết quả thực tế. Nếu chỉ dựa vào một vài ý kiến nổi bật, nhóm dễ ưu tiên nhầm vấn đề, bỏ qua ràng buộc hoặc mở rộng phạm vi theo sở thích của người thiết kế.

**Ma trận quyết định miền** là một cách tổ chức các lựa chọn và tiêu chí thành bảng để nhóm có thể so sánh chúng một cách minh bạch. Ma trận giúp trả lời những câu hỏi như:

- Trong các miền hoặc nhóm công việc đang được xem xét, miền nào phù hợp để bắt đầu xây dựng DSL?
- Những khả năng nào cần nằm trong phạm vi DSL phiên bản đầu?
- Hai phương án mô hình hóa cùng một khái niệm khác nhau ở điểm nào?
- Quyết định nào có bằng chứng hỗ trợ, quyết định nào còn dựa trên giả định?

Không có một mẫu ma trận duy nhất phù hợp với mọi dự án. Đây là kỹ thuật hỗ trợ thảo luận và ra quyết định, không phải thuật toán tự động xác định miền đúng. Chất lượng của kết quả phụ thuộc vào câu hỏi được đặt ra, tiêu chí được chọn, dữ liệu làm căn cứ và cách nhóm giải thích các đánh giá.

## 2. Ma trận quyết định gồm những thành phần nào?

Một ma trận cơ bản có các thành phần sau:

| Thành phần | Ý nghĩa | Ví dụ trong dự án DSL |
|---|---|---|
| Câu hỏi quyết định | Việc cụ thể cần lựa chọn | Nên bắt đầu với miền xử lý dữ liệu hay miền cấu hình triển khai? |
| Phương án | Các lựa chọn được đem ra so sánh | Xử lý dữ liệu; cấu hình triển khai; tự động hóa quy trình tổng quát |
| Tiêu chí | Những khía cạnh dùng để đánh giá | Tần suất sử dụng, tính ổn định của quy tắc, độ rõ của khái niệm, khả năng kiểm tra |
| Trọng số | Mức quan trọng tương đối của từng tiêu chí | Tính ổn định có trọng số cao hơn mức độ dễ triển khai |
| Điểm đánh giá | Mức đáp ứng của từng phương án đối với tiêu chí | Chấm từ 1 đến 5 theo thang đã thống nhất |
| Bằng chứng và giả định | Căn cứ hoặc điều chưa được xác nhận đằng sau điểm số | Có 12 quy trình mẫu; chưa phỏng vấn nhóm vận hành |
| Kết quả và lý do | Phương án được ưu tiên cùng những đánh đổi | Chọn xử lý dữ liệu vì có quy tắc lặp lại và có thể kiểm tra sớm |

Trong ma trận, mỗi hàng thường đại diện cho một tiêu chí hoặc một quyết định; mỗi cột đại diện cho một phương án, tùy mục đích trình bày. Phần ghi chú nên lưu lại bằng chứng và giả định để người xem hiểu điểm số đến từ đâu.

### 2.1. Phân biệt lựa chọn, tiêu chí và bằng chứng

Ba khái niệm này dễ bị trộn lẫn:

- **Lựa chọn** trả lời câu hỏi “ta có thể làm theo những phương án nào?”. Ví dụ: DSL chỉ xử lý phép biến đổi dữ liệu dạng bảng, hoặc DSL hỗ trợ cả điều phối luồng xử lý.
- **Tiêu chí** trả lời câu hỏi “dựa vào điều gì để so sánh?”. Ví dụ: tần suất công việc, độ ổn định của quy tắc, khả năng giới hạn phạm vi.
- **Bằng chứng** trả lời câu hỏi “vì sao ta cho rằng phương án đáp ứng tiêu chí ở mức đó?”. Ví dụ: số lượng cấu hình thực tế, kết quả phỏng vấn, thống kê lỗi hoặc mẫu mã nguồn.

Không nên dùng một nhận xét như “phương án A hiện đại hơn” làm tiêu chí nếu nhóm không thể giải thích nó có ý nghĩa gì đối với mục tiêu DSL. Tương tự, không nên chấm điểm chỉ vì một thành viên thích phương án đó.

## 3. Hai cách sử dụng ma trận khi khám phá miền

Trong thiết kế DSL, ma trận thường hữu ích ở ít nhất hai cấp độ. Cấp thứ nhất giúp chọn miền hoặc nhóm công việc cần tập trung. Cấp thứ hai giúp xác định ranh giới và nội dung của DSL sau khi đã chọn được miền.

### 3.1. So sánh các miền hoặc nhóm công việc ứng viên

Ở giai đoạn đầu, nhóm có thể có nhiều miền ứng viên. Ví dụ, một tổ chức muốn chuẩn hóa các cấu hình kỹ thuật và đang cân nhắc:

- Miền xử lý dữ liệu theo lô.
- Miền cấu hình và triển khai dịch vụ.
- Miền tự động hóa quy trình công việc tổng quát.

Ma trận giúp so sánh mức phù hợp của từng miền với mục tiêu dự án. Những tiêu chí thường có ích gồm:

| Tiêu chí | Câu hỏi cần đặt ra | Dấu hiệu phù hợp với DSL |
|---|---|---|
| Tần suất và mức độ lặp lại | Công việc xuất hiện thường xuyên đến đâu? Có nhiều trường hợp dùng chung mẫu không? | Có nhiều mô tả tương tự cần được chuẩn hóa |
| Tính ổn định của miền | Khái niệm và quy tắc có thay đổi liên tục không? | Các khái niệm cốt lõi đủ ổn định để định nghĩa và duy trì |
| Tính rõ ràng của từ vựng | Người làm trong miền có hiểu và dùng nhất quán các thuật ngữ không? | Có thể đặt tên cho thực thể, thao tác và quan hệ một cách nhất quán |
| Chi phí của cách làm hiện tại | Cách dùng ngôn ngữ đa dụng hoặc cấu hình hiện tại gây khó khăn gì? | DSL có cơ hội giảm mã lặp, lỗi hoặc chi phí phối hợp |
| Khả năng kiểm tra | Có thể phát hiện lỗi bằng quy tắc, kiểu dữ liệu hoặc ràng buộc không? | Mô tả có thể được kiểm tra trước khi thực thi |
| Ranh giới miền | Có thể xác định rõ phần nào thuộc phạm vi và phần nào nằm ngoài không? | Phạm vi đủ hẹp để thiết kế và đủ rộng để có giá trị |
| Khả năng tiếp cận người dùng | Nhóm có thể làm việc với người hiểu miền và lấy ví dụ thực tế không? | Có người dùng, chuyên gia và tình huống đại diện để xác minh |
| Khả năng tích hợp | DSL có thể kết nối với hệ thống và dữ liệu hiện có không? | Đầu vào, đầu ra và môi trường thực thi có thể được xác định |
| Rủi ro và hậu quả | Sai sót trong mô tả gây hậu quả lớn đến mức nào? | Có thể đặt ràng buộc, kiểm tra và cơ chế kiểm soát phù hợp |

Không nhất thiết đưa tất cả tiêu chí vào cùng một ma trận. Hãy chọn những yếu tố có ảnh hưởng thực sự đến quyết định. Nếu một tiêu chí không phân biệt được các phương án hoặc không liên quan đến mục tiêu, tiêu chí đó có thể không cần thiết.

### 3.2. Quyết định phạm vi và khả năng của DSL

Sau khi chọn được miền, nhóm vẫn phải xác định những khái niệm và thao tác nào cần hỗ trợ. Chẳng hạn, DSL xử lý dữ liệu có thể bắt đầu từ các bước đọc nguồn, lọc, nhóm, tổng hợp và ghi kết quả. Một số đề xuất mở rộng như vòng lặp tùy ý, gọi dịch vụ bên ngoài hoặc thực thi mã người dùng có thể làm phạm vi phức tạp hơn.

Có thể lập ma trận để quyết định từng khả năng:

| Khả năng được đề xuất | Giá trị với người dùng | Mức độ thường gặp | Độ phức tạp và rủi ro | Quyết định ban đầu |
|---|---|---|---|---|
| Đọc nguồn dữ liệu dạng bảng | Cao | Cao | Thấp | Đưa vào phạm vi đầu tiên |
| Lọc bản ghi theo điều kiện | Cao | Cao | Trung bình | Đưa vào phạm vi đầu tiên |
| Nhóm và tổng hợp dữ liệu | Cao | Cao | Trung bình | Đưa vào phạm vi đầu tiên |
| Ghi kết quả ra tệp | Cao | Cao | Thấp | Đưa vào phạm vi đầu tiên |
| Gọi dịch vụ mạng tùy ý | Chưa rõ | Thấp trong mẫu ban đầu | Cao | Hoãn, cần thêm bằng chứng và thiết kế kiểm soát |
| Thực thi mã tùy ý | Chưa rõ | Hiếm | Rất cao | Để ngoài phạm vi ban đầu |

Ma trận này làm rõ vì sao một khả năng được đưa vào, hoãn lại hoặc loại khỏi phạm vi hiện tại. Quyết định “hoãn” không có nghĩa là tính năng đó sẽ không bao giờ được hỗ trợ; nó cho biết hiện chưa có đủ lợi ích hoặc bằng chứng để chấp nhận chi phí và rủi ro.

## 4. Xây dựng ma trận có trọng số

Khi nhiều tiêu chí có mức quan trọng khác nhau, nhóm có thể dùng ma trận chấm điểm có trọng số. Cách này hữu ích khi cần xếp thứ tự ưu tiên giữa các phương án, nhưng phải thống nhất thang điểm và cách tính trước khi chấm.

### 4.1. Chọn thang điểm

Một thang điểm đơn giản từ 1 đến 5 có thể được định nghĩa như sau:

| Điểm | Diễn giải chung |
|---:|---|
| 1 | Rất kém: hầu như không đáp ứng tiêu chí hoặc có trở ngại lớn |
| 2 | Kém: đáp ứng một phần nhỏ, còn nhiều vấn đề chưa giải quyết |
| 3 | Trung bình: đáp ứng ở mức chấp nhận được nhưng còn hạn chế |
| 4 | Tốt: đáp ứng phần lớn yêu cầu, có thể xử lý các hạn chế còn lại |
| 5 | Rất tốt: đáp ứng rõ ràng, có bằng chứng hỗ trợ và ít trở ngại đáng kể |

Đây là thang điểm minh họa. Với từng tiêu chí, nên viết hướng dẫn cụ thể để tránh việc mỗi người hiểu điểm 3 hoặc điểm 5 theo một cách khác nhau. Ví dụ, tiêu chí tần suất có thể dựa trên số quy trình thực tế trong một khoảng thời gian; tiêu chí tính ổn định có thể dựa trên số lần quy tắc cốt lõi thay đổi trong các phiên bản gần đây.

### 4.2. Gán trọng số cho tiêu chí

Trọng số thể hiện mức quan trọng của tiêu chí đối với câu hỏi đang xét. Có thể phân bổ theo phần trăm, sao cho tổng trọng số bằng 100%. Trọng số không phải điểm đánh giá của phương án.

Ví dụ, khi chọn miền để xây dựng DSL đầu tiên, nhóm có thể đặt trọng số như sau:

| Tiêu chí | Trọng số |
|---|---:|
| Tần suất và mức độ lặp lại | 15% |
| Tính ổn định của quy tắc | 15% |
| Tính rõ ràng của khái niệm miền | 15% |
| Chi phí của cách biểu đạt hiện tại | 15% |
| Khả năng kiểm tra và tự động hóa | 15% |
| Khả năng giới hạn phạm vi | 10% |
| Mức độ kiểm soát rủi ro | 5% |
| Khả năng tiếp cận người dùng và ví dụ thực tế | 10% |
| **Tổng** | **100%** |

Trọng số này chỉ là một ví dụ. Một DSL dùng trong hệ thống có ảnh hưởng lớn đến an toàn có thể cần đặt trọng số cao hơn cho khả năng kiểm soát rủi ro. Một dự án thử nghiệm trong phạm vi nhỏ có thể quan tâm nhiều hơn đến tốc độ kiểm chứng giả thuyết.

### 4.3. Tính điểm có trọng số

Nếu điểm của mỗi phương án được chấm từ 1 đến 5, có thể chuẩn hóa tổng điểm về thang 100 theo công thức:

\[
S = \sum_{i=1}^{n} w_i \times \frac{r_i}{5}
\]

Trong đó:

- \(S\) là tổng điểm có trọng số của phương án.
- \(n\) là số tiêu chí.
- \(w_i\) là trọng số của tiêu chí thứ \(i\), tính theo phần trăm.
- \(r_i\) là điểm của phương án ở tiêu chí thứ \(i\), từ 1 đến 5.

Ví dụ, một phương án đạt 4 điểm ở tiêu chí có trọng số 15% sẽ nhận được \(15 \times 4/5 = 12\) điểm đóng góp. Cộng đóng góp của tất cả tiêu chí sẽ thu được điểm tổng.

## 5. Ví dụ hoàn chỉnh: chọn miền cho DSL đầu tiên

Giả sử một nhóm kỹ thuật muốn xây dựng DSL để chuẩn hóa một số công việc nội bộ. Sau khi khảo sát sơ bộ, nhóm chọn ba phương án để so sánh:

- **A — Xử lý dữ liệu theo lô:** đọc dữ liệu dạng bảng, lọc, nhóm, tổng hợp và xuất kết quả.
- **B — Cấu hình triển khai dịch vụ:** mô tả dịch vụ, tài nguyên, biến cấu hình, phụ thuộc và trạng thái mong muốn.
- **C — Tự động hóa quy trình tổng quát:** kết hợp nhiều bước công việc, điều kiện, tích hợp và hành động trên các hệ thống khác nhau.

Nhóm dùng các tiêu chí và trọng số ở phần trước. Sau khi xem các ví dụ cấu hình, quy trình hiện tại và trao đổi với người dùng, nhóm đưa ra điểm đánh giá minh họa:

| Tiêu chí | Trọng số | A: Xử lý dữ liệu | B: Triển khai dịch vụ | C: Quy trình tổng quát |
|---|---:|---:|---:|---:|
| Tần suất và mức độ lặp lại | 15% | 5 | 4 | 5 |
| Tính ổn định của quy tắc | 15% | 4 | 4 | 2 |
| Tính rõ ràng của khái niệm | 15% | 5 | 4 | 3 |
| Chi phí của cách biểu đạt hiện tại | 15% | 4 | 4 | 5 |
| Khả năng kiểm tra và tự động hóa | 15% | 5 | 5 | 3 |
| Khả năng giới hạn phạm vi | 10% | 4 | 3 | 1 |
| Mức độ kiểm soát rủi ro | 5% | 4 | 2 | 2 |
| Khả năng tiếp cận người dùng và ví dụ | 10% | 5 | 4 | 3 |
| **Tổng điểm có trọng số** | **100%** | **91** | **79** | **64** |

Điểm của phương án A được tính như sau:

\[
\begin{aligned}
S_A ={}& 15\times\frac{5}{5} + 15\times\frac{4}{5} + 15\times\frac{5}{5} \\
&+ 15\times\frac{4}{5} + 15\times\frac{5}{5} + 10\times\frac{4}{5} \\
&+ 5\times\frac{4}{5} + 10\times\frac{5}{5} = 91
\end{aligned}
\]

Theo các giả định và trọng số đang dùng, phương án A được ưu tiên để thử nghiệm trước. Lý do là nhóm đã nhận diện được tập thao tác ổn định, có nhiều tình huống lặp lại, có người dùng cung cấp ví dụ và có thể kiểm tra nhiều quy tắc trước khi chạy.

Điểm số không có nghĩa phương án B không đáng làm. Cấu hình triển khai vẫn có điểm cao và có thể là ứng viên tiếp theo. Phương án C có điểm thấp hơn chủ yếu vì phạm vi rất rộng, các quy tắc thay đổi theo hệ thống tích hợp và khó giới hạn một tập biểu thức đủ rõ cho phiên bản đầu.

### 5.1. Ghi lại căn cứ cho điểm

Để ma trận có thể được xem xét lại, nhóm cần ghi lại căn cứ của những điểm quan trọng. Ví dụ:

| Nhận định | Bằng chứng cần thu thập | Trạng thái trong ví dụ |
|---|---|---|
| Công việc xử lý dữ liệu lặp lại thường xuyên | Danh sách báo cáo, lịch chạy, số lượng pipeline | Đã có một số pipeline mẫu |
| Quy tắc xử lý dữ liệu tương đối ổn định | Lịch sử thay đổi, yêu cầu và phiên bản cấu hình | Cần xác nhận thêm với nhóm vận hành |
| Có thể kiểm tra tên trường và kiểu dữ liệu | Schema của nguồn dữ liệu và quy tắc tổng hợp | Có thể thử trên tập dữ liệu mẫu |
| Phạm vi xử lý dữ liệu có ranh giới rõ | Danh sách thao tác cần hỗ trợ và ngoại lệ | Đã xác định phạm vi ban đầu |

Nếu một điểm chưa có bằng chứng, nên ghi rõ đó là giả định hoặc đánh dấu cần xác minh. Không nên trình bày điểm số như dữ liệu đo lường khách quan khi thực tế chúng chỉ là đánh giá ban đầu của nhóm.

## 6. Ma trận quyết định phạm vi: đưa khả năng nào vào DSL?

Chọn được miền chưa đồng nghĩa với việc phải đưa mọi yêu cầu trong miền vào DSL. Nhóm cần tiếp tục quyết định khả năng nào thuộc phiên bản đầu, khả năng nào được hoãn và khả năng nào nằm ngoài phạm vi.

Có thể dùng các tiêu chí như:

- Mức độ cần thiết đối với các tình huống sử dụng cốt lõi.
- Tần suất xuất hiện trong dữ liệu hoặc quy trình thực tế.
- Mức độ dùng chung giữa các nhóm người dùng.
- Khả năng diễn đạt rõ bằng một khái niệm hoặc cấu trúc DSL.
- Khả năng kiểm tra trước khi thực thi.
- Chi phí triển khai, bảo trì và hỗ trợ người dùng.
- Rủi ro khi thực thi hoặc khi người dùng hiểu sai.
- Sự phụ thuộc vào hệ thống bên ngoài.

Ví dụ, trong DSL xử lý dữ liệu theo lô, nhóm có thể lập ma trận sau:

| Khả năng | Tần suất | Giá trị cốt lõi | Khả năng kiểm tra | Chi phí/rủi ro | Đề xuất |
|---|---|---|---|---|---|
| Khai báo nguồn dữ liệu | Cao | Cao | Cao | Thấp | Bao gồm |
| Lọc theo biểu thức điều kiện | Cao | Cao | Cao | Trung bình | Bao gồm |
| Nhóm và tổng hợp | Cao | Cao | Cao | Trung bình | Bao gồm |
| Sắp xếp và giới hạn kết quả | Trung bình | Trung bình | Cao | Thấp | Cân nhắc theo tình huống sử dụng |
| Gọi API bên ngoài trong một bước xử lý | Thấp | Chưa rõ | Trung bình | Cao | Hoãn để khảo sát thêm |
| Thực thi đoạn mã bất kỳ từ cấu hình | Thấp | Thấp trong phạm vi hiện tại | Thấp | Rất cao | Để ngoài phạm vi ban đầu |

Kết quả nên được ghi dưới dạng quyết định có lý do. Ví dụ: “Phiên bản đầu hỗ trợ nguồn dữ liệu dạng bảng, lọc, nhóm, tổng hợp và xuất tệp vì đây là chuỗi thao tác xuất hiện trong phần lớn quy trình được khảo sát. Các thao tác gọi mạng và thực thi mã tùy ý được hoãn do chưa có nhu cầu đủ rõ và cần cơ chế kiểm soát riêng.”

## 7. Ma trận lựa chọn giữa các phương án thiết kế

Ma trận cũng có thể dùng sau khi đã xác định yêu cầu, khi nhóm cần chọn giữa nhiều cách biểu đạt một khái niệm. Chẳng hạn, một điều kiện lọc có thể được biểu diễn bằng biểu thức dạng toán tử, lời gọi hàm hoặc cấu trúc khai báo.

| Phương án | Ví dụ minh họa | Dễ đọc với người dùng miền | Dễ phân tích | Khả năng mở rộng | Điểm cần cân nhắc |
|---|---|---|---|---|---|
| Biểu thức toán tử | `amount >= 100` | Cao với biểu thức đơn giản | Cần quy tắc ưu tiên và kiểu toán hạng | Tốt nếu ngữ pháp được thiết kế rõ | Biểu thức phức tạp có thể cần ngoặc |
| Lời gọi hàm | `greaterOrEqual(amount, 100)` | Có thể rõ nhưng dài | Thường đơn giản hơn | Có thể thêm hàm mới | Dễ trở nên dài và thiên về API |
| Cấu trúc khai báo | `field: amount, operator: ">=", value: 100` | Phù hợp với cấu hình có cấu trúc | Có thể dùng parser định dạng dữ liệu | Linh hoạt cho công cụ sinh cấu hình | Dài và khó biểu đạt biểu thức lồng nhau |

Đánh giá phải dựa trên người dùng và bối cảnh thật. Nếu DSL chủ yếu được viết thủ công bởi chuyên gia dữ liệu, biểu thức có thể thuận tiện. Nếu cấu hình được sinh và trao đổi giữa nhiều công cụ, cấu trúc khai báo có thể phù hợp hơn. Không nên chọn cú pháp chỉ vì nó dễ cài đặt nhất cho nhóm phát triển.

## 8. Quy trình xây dựng và sử dụng ma trận

Một quy trình thực tế có thể triển khai theo các bước sau:

1. **Phát biểu câu hỏi quyết định.** Viết thành một câu rõ ràng, chẳng hạn “Miền nào phù hợp để làm DSL thử nghiệm đầu tiên?” hoặc “Khả năng nào cần có trong phiên bản đầu?”.
2. **Liệt kê phương án thực tế.** Dựa trên tình huống và dữ liệu đã thu thập. Tránh tạo các phương án quá mơ hồ hoặc cố ý làm yếu một lựa chọn.
3. **Chọn tiêu chí liên quan.** Mỗi tiêu chí cần giúp phân biệt phương án hoặc phản ánh một mục tiêu quan trọng. Định nghĩa tiêu chí để mọi người hiểu giống nhau.
4. **Xác định ràng buộc bắt buộc.** Một số điều kiện là ngưỡng loại trừ, không nên bù bằng điểm cao ở tiêu chí khác. Ví dụ, nếu không có cách kiểm soát quyền thực thi tối thiểu thì phương án có thể không được chọn dù tổng điểm cao.
5. **Gán trọng số nếu cần.** Thảo luận mức quan trọng tương đối và kiểm tra tổng trọng số. Không cần dùng trọng số khi chỉ cần so sánh định tính.
6. **Đánh giá từng phương án.** Dùng cùng một thang điểm, ghi lý do và nguồn bằng chứng. Có thể để nhiều người đánh giá độc lập trước khi thống nhất.
7. **Tính điểm và xem xét đánh đổi.** Xem điểm tổng, điểm từng tiêu chí, ràng buộc và các rủi ro chưa được giải quyết.
8. **Kiểm tra độ nhạy.** Thử thay đổi trọng số hoặc điểm ở các tiêu chí còn bất định để xem kết quả có đảo chiều không.
9. **Xác minh với người dùng miền.** Trình bày kết quả cùng ví dụ thực tế, hỏi xem các giả định và ưu tiên có phản ánh đúng công việc không.
10. **Ghi quyết định và điều kiện xem xét lại.** Lưu phương án được chọn, lý do, người tham gia, bằng chứng, vấn đề còn mở và thời điểm hoặc sự kiện cần đánh giá lại.

Không phải quyết định nào cũng cần ma trận có trọng số. Với lựa chọn nhỏ và ít rủi ro, một bảng so sánh định tính có thể đủ. Nên chọn mức độ hình thức tương xứng với tác động và chi phí của quyết định.

## 9. Kiểm tra độ nhạy và xử lý bất định

Điểm tổng có thể tạo cảm giác chính xác hơn thực tế. Nếu thay đổi nhẹ một trọng số đã khiến thứ hạng đảo ngược, quyết định đang phụ thuộc nhiều vào cách đánh giá. Khi đó, nhóm cần tìm thêm bằng chứng hoặc thực hiện một thử nghiệm nhỏ trước khi chốt phạm vi.

Một số cách kiểm tra hữu ích:

- **Thay đổi trọng số:** tăng hoặc giảm trọng số của tiêu chí quan trọng để xem phương án đứng đầu có thay đổi không.
- **Thay đổi điểm chưa chắc chắn:** nếu điểm của một phương án chỉ dựa trên phỏng đoán, thử tính với mức thấp hơn và cao hơn.
- **Xem từng tiêu chí riêng:** phương án có tổng điểm cao nhưng rất yếu ở một tiêu chí bắt buộc có thể không phù hợp.
- **Ghi mức tin cậy:** đánh dấu điểm có bằng chứng trực tiếp, bằng chứng gián tiếp hoặc chỉ là giả định.
- **Tách dữ kiện khỏi ý kiến:** số lượng quy trình, tỷ lệ lỗi và lịch sử thay đổi là dữ liệu; nhận xét “khó sử dụng” cần được gắn với người dùng, tình huống và quan sát cụ thể.

Nếu các phương án gần điểm nhau, đừng cố tạo ra một người thắng bằng cách điều chỉnh trọng số tùy ý. Hãy xác định thông tin còn thiếu, tạo một nguyên mẫu nhỏ hoặc thu thập thêm ví dụ để giải quyết điểm bất định quan trọng nhất.

## 10. Ghi lại quyết định để có thể truy vết

Ma trận chỉ có ích lâu dài khi người khác có thể hiểu cách nhóm đã đi đến kết quả. Một bản ghi quyết định nên có:

| Trường thông tin | Nội dung nên lưu |
|---|---|
| Mã và tên quyết định | Mã duy nhất và tiêu đề ngắn |
| Câu hỏi | Câu hỏi cần trả lời |
| Bối cảnh | Mục tiêu DSL và tình huống dẫn đến quyết định |
| Phương án | Những lựa chọn đã xem xét |
| Tiêu chí và trọng số | Định nghĩa, thang điểm và mức quan trọng |
| Bằng chứng | Ví dụ, dữ liệu, phỏng vấn và nguồn liên quan |
| Kết quả | Phương án được chọn và điểm số nếu có |
| Lý do và đánh đổi | Lợi ích, hạn chế và rủi ro được chấp nhận |
| Người tham gia | Người cung cấp dữ liệu và người quyết định |
| Giả định còn mở | Những điều chưa được xác minh |
| Điều kiện xem xét lại | Sự kiện, thay đổi hoặc mốc thời gian khiến quyết định cần được đánh giá lại |

Ví dụ bản ghi ngắn:

```text
DEC-DSL-001: Chọn miền cho nguyên mẫu DSL

Câu hỏi:
  Nên xây dựng nguyên mẫu đầu tiên cho miền nào?

Phương án được chọn:
  Xử lý dữ liệu theo lô

Lý do:
  - Có nhiều quy trình dùng chung các bước đọc, lọc, nhóm và tổng hợp.
  - Khái niệm dữ liệu dạng bảng đã quen thuộc với người dùng.
  - Có thể kiểm tra tên trường và kiểu dữ liệu trước khi chạy.

Đánh đổi:
  - Chưa hỗ trợ điều phối công việc tổng quát.
  - Chưa hỗ trợ gọi dịch vụ mạng hoặc thực thi mã tùy ý.

Giả định cần xác minh:
  - Các quy tắc xử lý cốt lõi ổn định giữa các nhóm.

Điều kiện xem xét lại:
  - Có thêm nhóm người dùng hoặc loại nguồn dữ liệu mới làm thay đổi phạm vi.
```

## 11. Những sai lầm thường gặp

### 11.1. Chọn tiêu chí theo phương án mình đã thích

Nếu nhóm đã muốn chọn một phương án từ trước, họ có thể vô thức tạo tiêu chí có lợi cho phương án đó. Hãy phát biểu câu hỏi và tiêu chí trước khi chấm điểm; mời người hiểu miền xem lại tính công bằng của chúng.

### 11.2. Dùng quá nhiều tiêu chí hoặc tiêu chí trùng nhau

Một ma trận có hàng chục tiêu chí gần giống nhau làm tăng công sức nhưng không tăng chất lượng quyết định. Ví dụ, “dễ học”, “dễ hiểu” và “dễ sử dụng” có thể đang đo cùng một đặc tính. Hãy gộp chúng hoặc định nghĩa ranh giới rõ.

### 11.3. Chấm điểm mà không có thang định nghĩa

Nếu không giải thích điểm 1 và điểm 5 có nghĩa gì, kết quả dễ phản ánh cảm nhận cá nhân. Mỗi tiêu chí nên có mô tả hoặc chỉ báo quan sát được.

### 11.4. Coi điểm tổng là câu trả lời cuối cùng

Điểm số không thể tự quyết định thay cho nhóm. Một ràng buộc bắt buộc, rủi ro nghiêm trọng hoặc thiếu người dùng để xác minh có thể quan trọng hơn chênh lệch vài điểm tổng.

### 11.5. Bỏ qua giả định và độ tin cậy

Một điểm số dựa trên dữ liệu thực tế có độ tin cậy khác một điểm số được ước lượng trong cuộc họp. Hãy lưu nguồn, thời điểm và mức chắc chắn của nhận định.

### 11.6. Không xem xét lại quyết định

Miền có thể thay đổi khi quy trình, công nghệ, quy định hoặc nhu cầu người dùng thay đổi. Ma trận nên được xem xét lại khi xuất hiện bằng chứng mới có ảnh hưởng đáng kể, không cần giữ một lựa chọn chỉ vì nó từng được chấm điểm cao.

## 12. Mẫu ma trận có thể tái sử dụng

Mẫu dưới đây có thể sao chép để bắt đầu một phiên đánh giá. Các ô điểm và trọng số cần được nhóm định nghĩa theo bối cảnh dự án.

| Câu hỏi quyết định | Nội dung điền |
|---|---|
| Quyết định cần đưa ra | [Mô tả câu hỏi] |
| Mục tiêu DSL liên quan | [Mục tiêu và người dùng] |
| Phương án A / B / C | [Mô tả từng phương án] |
| Thang điểm | [Ví dụ: 1 đến 5, kèm định nghĩa] |
| Ràng buộc bắt buộc | [Điều kiện loại trừ hoặc yêu cầu tối thiểu] |
| Nguồn bằng chứng | [Phỏng vấn, quy trình, dữ liệu, mã nguồn, tài liệu] |

| Tiêu chí | Định nghĩa | Trọng số | A | B | C | Bằng chứng / ghi chú |
|---|---|---:|---:|---:|---:|---|
| [Tiêu chí 1] | [Cách đánh giá] | [%] | [1–5] | [1–5] | [1–5] | [Nguồn và giả định] |
| [Tiêu chí 2] | [Cách đánh giá] | [%] | [1–5] | [1–5] | [1–5] | [Nguồn và giả định] |
| [Tiêu chí 3] | [Cách đánh giá] | [%] | [1–5] | [1–5] | [1–5] | [Nguồn và giả định] |
| **Tổng** |  | **100%** | [Điểm] | [Điểm] | [Điểm] |  |

**Kết quả quyết định:** [Phương án được chọn hoặc kết luận chưa đủ bằng chứng]

**Lý do:** [Các tiêu chí có ảnh hưởng lớn nhất và bằng chứng hỗ trợ]

**Đánh đổi và rủi ro:** [Những điểm yếu được chấp nhận hoặc cần xử lý]

**Việc cần xác minh:** [Dữ liệu, người dùng hoặc thử nghiệm còn thiếu]

**Điều kiện xem xét lại:** [Sự kiện hoặc thay đổi có thể làm quyết định mất hiệu lực]

## 13. Câu hỏi tự kiểm tra

1. Ma trận quyết định miền giúp nhóm giải quyết những loại câu hỏi nào trong quá trình khám phá và thiết kế DSL?
2. Phân biệt phương án, tiêu chí và bằng chứng. Vì sao không nên chấm điểm một phương án chỉ dựa trên sở thích cá nhân?
3. Khi nào nên dùng ma trận có trọng số? Trọng số và điểm đánh giá có ý nghĩa khác nhau như thế nào?
4. Vì sao một phương án có tổng điểm cao vẫn có thể bị loại do không đáp ứng ràng buộc bắt buộc?
5. Với ví dụ chọn DSL xử lý dữ liệu theo lô, hãy nêu hai bằng chứng có thể dùng để kiểm tra điểm số về tính ổn định và tần suất sử dụng.
6. Nếu thay đổi trọng số khiến phương án đứng đầu thay đổi, nhóm nên làm gì trước khi chốt quyết định?
7. Hãy lập một ma trận nhỏ để quyết định ba khả năng nên có trong phiên bản đầu của một DSL thuộc miền bạn quan tâm. Ghi rõ tiêu chí, bằng chứng, kết quả và một điều kiện cần xem xét lại.
