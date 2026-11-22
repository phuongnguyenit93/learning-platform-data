# Xác định nguồn xác nhận kết quả mong đợi cho dữ liệu khó dự đoán

Một ca kiểm thử chỉ có ý nghĩa khi nhóm có cách xác định kết quả quan sát được là đúng hay sai. Cách xác định đó được gọi là **test oracle** (nguồn hoặc cơ chế xác nhận kết quả mong đợi). Với dữ liệu đơn giản, oracle có thể là một giá trị cố định đã tính trước. Nhưng với dữ liệu lớn, dữ liệu biến động, thuật toán phức tạp, hệ thống ngẫu nhiên hoặc mô hình học máy, việc biết chính xác kết quả mong đợi có thể rất khó hoặc tốn kém.

Trong chiến lược kiểm thử xác thực, nhóm cần xác định nguồn bằng chứng phù hợp với từng loại dữ liệu và quyết định cần đưa ra. Có thể dùng đặc tả đã được phê duyệt, quy tắc nghiệp vụ, phép tính độc lập, hệ thống tham chiếu, bất biến dữ liệu, quan hệ giữa nhiều lần chạy, kết quả của chuyên gia hoặc ngưỡng thống kê. Nhiều trường hợp cần kết hợp nhiều nguồn thay vì phụ thuộc vào một đáp án duy nhất.

Điểm quan trọng là oracle phải có căn cứ độc lập và đủ đáng tin cậy. Nếu nhóm lấy kết quả từ chính thuật toán đang kiểm thử rồi dùng nó làm đáp án chuẩn, kiểm thử có thể xác nhận một lỗi mà không phát hiện được. Nếu dùng dữ liệu lịch sử làm chuẩn mà không kiểm tra tính hợp lệ, kiểm thử có thể bảo vệ cả hành vi sai đã tồn tại.

## 1. Test oracle là gì?

Test oracle là nguồn thông tin hoặc cơ chế giúp xác định kết quả thực tế của một phép kiểm thử có đáp ứng kỳ vọng hay không. Oracle có thể trả về một giá trị chính xác, một tập giá trị hợp lệ, một quan hệ cần giữ đúng hoặc một đánh giá có điều kiện.

Ví dụ với chức năng tính tổng đơn hàng:

- Đầu vào: giá từng sản phẩm, số lượng, giảm giá, thuế và phí vận chuyển.
- Kết quả thực tế: tổng tiền do ứng dụng trả về.
- Oracle: quy tắc tính tiền đã được nghiệp vụ phê duyệt và một phép tính độc lập.
- Quyết định: kết quả thực tế có khớp kết quả mong đợi theo quy tắc làm tròn đã thống nhất hay không.

Với dữ liệu khó dự đoán, oracle có thể không cung cấp một giá trị duy nhất. Ví dụ, một thuật toán gợi ý có thể trả về nhiều danh sách sản phẩm khác nhau theo dữ liệu và thời điểm. Khi đó, oracle có thể xác nhận rằng kết quả tuân thủ các điều kiện như không đề xuất sản phẩm đã ngừng bán, có liên quan đến sở thích đã biết và không vi phạm quy tắc ưu tiên.

Oracle không nhất thiết là một chương trình. Nó có thể là:

- Một đặc tả, chính sách hoặc quy tắc nghiệp vụ đã được phê duyệt.
- Một bảng dữ liệu chuẩn được kiểm tra và quản lý phiên bản.
- Một phép tính độc lập hoặc mô hình tham chiếu.
- Một hệ thống khác có nguồn dữ liệu và cách triển khai độc lập.
- Một tập bất biến, thuộc tính hoặc quan hệ toán học.
- Một đánh giá của chuyên gia hoặc người dùng đại diện theo rubric đã thống nhất.
- Một ngưỡng định lượng, khoảng giá trị hoặc phân phối thống kê.
- Một kết quả đã được xác nhận trước đó và được quản lý như golden master.

## 2. Vì sao dữ liệu khó dự đoán cần oracle được lựa chọn cẩn thận?

Một số loại dữ liệu có thể khiến việc viết expected result trực tiếp trở nên khó khăn:

- **Khối lượng lớn:** Có hàng triệu bản ghi hoặc nhiều tổ hợp đầu vào, không thể tính tay từng kết quả.
- **Dữ liệu biến động:** Kết quả phụ thuộc thời gian, tỷ giá, tồn kho, vị trí, trạng thái dịch vụ hoặc nguồn dữ liệu bên ngoài.
- **Thuật toán phức tạp:** Kết quả đòi hỏi phép tính tối ưu, mô phỏng hoặc nhiều quy tắc tương tác.
- **Tính ngẫu nhiên:** Kết quả thay đổi theo seed, thứ tự xử lý, lịch chạy hoặc thuật toán xác suất.
- **Hệ thống phi xác định:** Cùng đầu vào có thể tạo ra nhiều kết quả hợp lệ do xử lý đồng thời, phân tán hoặc lịch thực thi.
- **Dữ liệu do mô hình tạo ra:** Mô hình học máy hoặc hệ thống sinh nội dung có thể trả lời theo nhiều cách đúng, không có một chuỗi đầu ra duy nhất.
- **Thiếu đáp án có sẵn:** Dữ liệu mới, trường hợp hiếm hoặc tình huống chưa từng xuất hiện trong lịch sử chưa có nhãn chuẩn.

Nếu nhóm ép mọi trường hợp vào một giá trị expected cố định, có thể tạo ra false failure khi kết quả khác nhưng vẫn hợp lệ. Ngược lại, nếu tiêu chí quá rộng hoặc chỉ kiểm tra rằng chương trình không bị lỗi, có thể bỏ sót sai lệch nghiêm trọng.

Do đó, trước khi chọn oracle, cần làm rõ câu hỏi kiểm thử: cần xác nhận giá trị chính xác, tính nhất quán, tính hợp lệ, chất lượng theo tiêu chí, hay hành vi thống kê trong một khoảng điều kiện?

## 3. Các đặc tính của một oracle đáng tin cậy

Không phải nguồn dữ liệu nào cũng phù hợp làm chuẩn. Hãy đánh giá oracle theo các đặc tính sau:

| Đặc tính | Câu hỏi đánh giá | Ý nghĩa |
|---|---|---|
| Đúng đắn | Nguồn chuẩn có được xác nhận theo yêu cầu hoặc quy tắc có thẩm quyền không? | Tránh dùng đáp án sai làm chuẩn |
| Độc lập | Oracle có được tạo bằng cách khác với thành phần đang kiểm thử không? | Giảm nguy cơ cùng một lỗi xuất hiện ở cả hai phía |
| Phù hợp phạm vi | Oracle có kiểm tra đúng hành vi và điều kiện đang quan tâm không? | Tránh kết luận vượt quá bằng chứng |
| Đủ bao phủ | Oracle có xét trường hợp biên, ngoại lệ và dữ liệu bất thường không? | Tránh chỉ xác nhận luồng thông thường |
| Xác định được | Cùng điều kiện có cho kết quả so sánh ổn định không? | Hỗ trợ tái hiện và tự động hóa |
| Có thể truy vết | Có biết nguồn, phiên bản, thời điểm và người phê duyệt không? | Hỗ trợ điều tra và kiểm toán |
| Duy trì được | Khi quy tắc thay đổi, có thể cập nhật và rà soát oracle không? | Tránh chuẩn kiểm thử lỗi thời |
| Chi phí hợp lý | Chi phí tạo và đánh giá oracle có tương xứng với rủi ro không? | Giúp kiểm thử khả thi ở quy mô thực tế |

Oracle không cần hoàn hảo trong mọi chiều, nhưng các giới hạn phải được ghi nhận. Với một phép tính tài chính, tính đúng đắn và khả năng truy vết thường rất quan trọng. Với kết quả sinh nội dung, rubric và đánh giá của con người có thể cần thiết, nhưng cần thừa nhận mức độ chủ quan.

## 4. Nguồn oracle từ yêu cầu và quy tắc nghiệp vụ

Nguồn đầu tiên nên xem xét là yêu cầu, tiêu chí chấp nhận, chính sách và quy tắc nghiệp vụ đã được chủ sở hữu xác nhận. Đây thường là căn cứ phù hợp nhất khi cần xác định sản phẩm có đáp ứng mục tiêu sử dụng hay không.

Ví dụ:

- Chính sách hoàn tiền quy định số tiền hoàn không vượt quá số tiền đã thanh toán sau khi trừ các khoản không được hoàn.
- Quy tắc phân quyền quy định người dùng chỉ xem được hồ sơ thuộc phạm vi được cấp.
- Chính sách vận chuyển quy định một đơn hàng chỉ được chọn dịch vụ giao hàng phù hợp với vùng và trọng lượng.
- Quy tắc làm tròn xác định cách xử lý phần thập phân của thuế và tiền tệ.

Để dùng quy tắc làm oracle, cần làm rõ:

1. Quy tắc đến từ nguồn nào và ai có thẩm quyền phê duyệt?
2. Quy tắc áp dụng từ thời điểm nào, cho khu vực hoặc loại giao dịch nào?
3. Có ngoại lệ, giới hạn hoặc thứ tự ưu tiên nào không?
4. Khi hai quy tắc mâu thuẫn, quy tắc nào được ưu tiên?
5. Quy tắc có thể chuyển thành phép kiểm tra hoặc bộ dữ liệu chuẩn như thế nào?

Không nên suy diễn expected result từ mô tả mơ hồ. Nếu chính sách chưa rõ, cần ghi nhận câu hỏi và yêu cầu chủ sở hữu quyết định trước khi kết luận. Tester có thể chỉ ra các trường hợp chưa được định nghĩa, nhưng không nên tự đặt chính sách nghiệp vụ thay cho người có thẩm quyền.

## 5. Dùng phép tính hoặc mô hình tham chiếu độc lập

Khi kết quả có thể tính được, một cách mạnh là tạo oracle độc lập với mã sản phẩm. Ví dụ, ứng dụng tính phí vận chuyển có thể được so sánh với một bảng giá chuẩn hoặc một chương trình tham chiếu được viết bằng cách tiếp cận khác.

Một mô hình tham chiếu tốt nên:

- Được xây dựng từ cùng đặc tả đã thống nhất, nhưng không sao chép nguyên logic triển khai của hệ thống cần kiểm thử.
- Có phạm vi rõ, đặc biệt với giới hạn và trường hợp ngoại lệ.
- Được kiểm tra bằng ví dụ đã biết hoặc dữ liệu được chuyên gia xác nhận.
- Có thể chạy độc lập để đối chiếu.
- Được quản lý phiên bản và cập nhật khi quy tắc thay đổi.

Ví dụ, nếu hệ thống tính chiết khấu bằng một chuỗi quy tắc phức tạp, oracle có thể dùng bảng quyết định được chủ sản phẩm phê duyệt hoặc một phép tính độc lập trong bộ kiểm thử. Nếu cả ứng dụng và oracle cùng gọi một hàm tính tiền dùng chung, hai bên có thể cùng chứa một lỗi và kết quả so sánh sẽ không phát hiện được sai lệch.

### 5.1. Kiểm tra chéo bằng công cụ khác

Với một số phép tính, có thể dùng thư viện hoặc công cụ độc lập để xác nhận kết quả, chẳng hạn:

- So sánh phép tính số học với thư viện độ chính xác cao.
- So sánh truy vấn dữ liệu với một truy vấn tham chiếu được viết độc lập.
- So sánh kết quả định dạng ngày giờ với thư viện chuẩn đã được kiểm chứng.
- Đối chiếu kết quả mã hóa hoặc giải mã với triển khai độc lập theo cùng tiêu chuẩn.

Hai công cụ cùng cho kết quả không tự động chứng minh kết quả đúng. Chúng có thể dùng chung thư viện nền, cùng hiểu sai đặc tả hoặc có cùng giới hạn. Cần biết mức độ độc lập và nguồn thẩm quyền đứng sau kết quả.

## 6. Dùng dữ liệu chuẩn và golden master

Golden master là tập kết quả đã được xác nhận và lưu lại để so sánh với các lần chạy sau. Nó hữu ích khi kết quả khó tự tính lại nhưng có thể xác nhận một lần bằng chuyên gia hoặc nguồn đáng tin cậy.

Ví dụ:

- Bộ ảnh chuẩn để so sánh kết quả render.
- Tập báo cáo đã được nghiệp vụ phê duyệt.
- Bộ kết quả phân tích dữ liệu đã được chuyên gia xác nhận.
- Các thông điệp hoặc tệp xuất mẫu được dùng để kiểm tra định dạng.
- Tập đầu ra của một phiên bản đã được chấp nhận cho mục tiêu hồi quy.

Golden master cần được quản lý cẩn thận:

- Ghi nguồn gốc, phiên bản sản phẩm, điều kiện tạo và người xác nhận.
- Bảo vệ dữ liệu nhạy cảm và tuân thủ quyền sử dụng dữ liệu.
- Chỉ cập nhật khi có lý do được phê duyệt, không tự động ghi đè bằng kết quả mới.
- Phân biệt thay đổi hợp lệ với sai lệch do lỗi.
- Có thể dùng ngưỡng so sánh khi đầu ra có sai khác nhỏ được phép, chẳng hạn ảnh render khác biệt do khử răng cưa.

Một nguy cơ phổ biến là **golden master drift**: nhóm cập nhật kết quả chuẩn mỗi khi kiểm thử thất bại mà không xác minh nguyên nhân. Khi đó, lỗi mới sẽ được chấp nhận và bộ kiểm thử mất giá trị. Mọi thay đổi chuẩn cần được xem xét như một thay đổi yêu cầu hoặc bằng chứng.

## 7. Dùng bất biến và thuộc tính thay vì một đáp án cố định

Khi không thể biết chính xác đầu ra, có thể kiểm tra các điều kiện luôn phải đúng. Những điều kiện này được gọi là bất biến (invariant) hoặc thuộc tính (property).

Ví dụ:

- Tổng số lượng sau khi gộp nhóm không được âm.
- Mỗi mã giao dịch phải duy nhất trong phạm vi quy định.
- Số dư sau giao dịch phải bằng số dư trước cộng tiền vào trừ tiền ra, theo quy tắc làm tròn.
- Một người dùng không thể truy cập tài nguyên ngoài quyền được cấp.
- Kết quả sắp xếp phải tuân theo thứ tự đã định nghĩa.
- Mọi bản ghi con phải tham chiếu đến bản ghi cha hợp lệ.
- Tổng số bản ghi sau chuyển đổi phải khớp với số lượng được giải thích bởi quy tắc lọc hoặc loại trừ.

Ví dụ với dữ liệu giao dịch, nhóm có thể không biết trước số dư của hàng triệu tài khoản sau một đợt xử lý. Tuy nhiên, có thể kiểm tra rằng mỗi giao dịch được ghi đúng một lần, tổng tiền ghi nợ và ghi có cân bằng theo quy tắc, không có số dư vi phạm giới hạn và mọi thay đổi đều có mã tham chiếu.

Property-based testing là kỹ thuật sinh nhiều đầu vào và kiểm tra các thuộc tính này. Thay vì viết expected result cho từng đầu vào, nhóm xác định một hoặc nhiều property phải giữ đúng với mọi đầu vào hợp lệ.

Ví dụ giả mã:

```text
property: chuẩn hóa địa chỉ phải có tính idempotent

for any validAddress:
    once = normalize(validAddress)
    twice = normalize(once)
    assert twice == once
```

Thuộc tính này nói rằng chuẩn hóa một địa chỉ hai lần phải cho cùng kết quả như chuẩn hóa một lần. Nó không xác nhận địa chỉ đã chuẩn hóa có đúng với dữ liệu địa lý chính thức hay không; để xác nhận điều đó vẫn cần oracle khác.

## 8. Metamorphic testing: kiểm tra quan hệ giữa các lần chạy

Metamorphic testing hữu ích khi không biết kết quả chính xác của một đầu vào nhưng biết kết quả phải thay đổi hoặc giữ nguyên như thế nào khi đầu vào được biến đổi.

Một **metamorphic relation** mô tả quan hệ kỳ vọng giữa đầu vào và đầu ra của nhiều lần chạy.

Ví dụ:

- Nếu tăng số lượng một sản phẩm từ 1 lên 2 và không có giảm giá theo bậc, tổng tiền trước thuế của dòng hàng phải tăng gấp đôi.
- Nếu thêm một bản ghi không liên quan vào dữ liệu đầu vào, kết quả tính cho nhóm bản ghi cũ không được thay đổi.
- Nếu hoán đổi thứ tự đầu vào của một phép tổng hợp không phụ thuộc thứ tự, tổng kết quả phải giữ nguyên.
- Nếu tăng độ phân giải đầu vào cho thuật toán xấp xỉ, sai số đo được phải nằm trong giới hạn hoặc có xu hướng cải thiện theo đặc tả.
- Nếu một người dùng bị thu hồi quyền, các request tiếp theo cần bị từ chối theo chính sách.

Ví dụ với chức năng lọc đơn hàng:

```text
Input A: danh sách đơn hàng D
Output A: kết quả lọc các đơn có trạng thái "Đã giao"

Input B: hoán vị thứ tự các phần tử trong D
Output B: kết quả lọc tương ứng

Quan hệ mong đợi:
Output A và Output B chứa cùng tập đơn hàng.
```

Metamorphic testing không cần biết trước danh sách kết quả chính xác, nhưng vẫn kiểm tra được tính nhất quán. Tuy nhiên, quan hệ phải được suy ra từ yêu cầu thật. Nếu thuật toán được phép phụ thuộc thứ tự, hoặc việc thêm dữ liệu có thể ảnh hưởng kết quả do giới hạn toàn cục, quan hệ trên không còn hợp lệ.

## 9. Differential testing: đối chiếu nhiều triển khai

Differential testing chạy cùng đầu vào qua hai hoặc nhiều triển khai độc lập rồi so sánh kết quả. Nó hữu ích khi không có oracle tuyệt đối nhưng có nhiều triển khai được kỳ vọng tuân theo cùng một đặc tả.

Ví dụ:

- Chạy cùng truy vấn trên hai phiên bản bộ xử lý hoặc hai cơ sở dữ liệu được hỗ trợ.
- Đối chiếu kết quả parser với một thư viện độc lập.
- So sánh bộ chuyển đổi dữ liệu mới với bộ chuyển đổi cũ trên tập dữ liệu đã chọn.
- Chạy cùng phép tính trên hai thuật toán khác nhau và điều tra sai khác.

Không được mặc định đa số luôn đúng. Nếu ba triển khai cùng dùng một thư viện lỗi hoặc cùng hiểu sai quy tắc, kết quả đồng thuận vẫn có thể sai. Cần xác định nguồn độc lập, phạm vi tương đương và cách xử lý khác biệt hợp lệ giữa các nền tảng.

Khi kết quả khác nhau, nhóm cần phân loại:

1. Một triển khai sai so với đặc tả.
2. Các triển khai có hành vi hợp lệ khác nhau trong giới hạn được phép.
3. Đầu vào không xác định hoặc không thuộc miền hợp lệ.
4. Môi trường hoặc cấu hình khác nhau làm thay đổi kết quả.
5. Đặc tả chưa đủ rõ để quyết định triển khai nào đúng.

Sai khác là tín hiệu cần điều tra, không tự động là lỗi của một phía.

## 10. Oracle thống kê cho dữ liệu ngẫu nhiên và hệ thống phi xác định

Với thuật toán ngẫu nhiên, mô phỏng, xử lý phân tán hoặc mô hình học máy, một đầu vào có thể tạo ra nhiều kết quả hợp lệ. Oracle có thể đánh giá phân phối, tỷ lệ, giới hạn hoặc xu hướng thay vì so sánh từng giá trị.

Ví dụ với bộ sinh số ngẫu nhiên:

- Kết quả phải nằm trong khoảng đã quy định.
- Không có giá trị ngoài miền hợp lệ.
- Với số lần lấy mẫu đủ lớn, phân phối quan sát phải nằm trong ngưỡng thống kê đã xác định.
- Seed cố định phải giúp tái hiện kết quả khi sản phẩm cam kết tính lặp lại.

Với một mô phỏng, nhóm có thể so sánh trung bình, phương sai, phân vị hoặc sai số với khoảng tham chiếu. Cần xác định trước kích thước mẫu, mức tin cậy, ngưỡng sai lệch và cách xử lý kết quả nằm gần biên.

Với hệ thống phân tán, thứ tự hoàn thành có thể thay đổi. Oracle có thể xác nhận các điều kiện cuối cùng như không mất sự kiện, không xử lý trùng tác dụng phụ, trạng thái cuối cùng hợp lệ và mọi thao tác được ghi nhận theo bảo đảm đã công bố.

Không nên đặt ngưỡng thống kê sau khi đã quan sát kết quả để làm cho kiểm thử đạt. Ngưỡng phải có căn cứ từ yêu cầu, phân tích dữ liệu hoặc chuyên gia, và cần được rà soát khi điều kiện vận hành thay đổi.

## 11. Oracle cho hệ thống học máy và đầu ra do mô hình tạo ra

Đầu ra của mô hình học máy thường không có một đáp án duy nhất. Một mô hình phân loại có thể tạo xác suất; hệ thống gợi ý có thể đưa ra nhiều thứ tự phù hợp; mô hình sinh ngôn ngữ có thể diễn đạt cùng nội dung theo nhiều cách.

Các nguồn oracle có thể gồm:

- **Tập dữ liệu gán nhãn:** Nhãn được tạo hoặc kiểm tra bởi chuyên gia, kèm hướng dẫn gán nhãn và mức đồng thuận.
- **Rubric đánh giá:** Tiêu chí rõ về tính chính xác, liên quan, đầy đủ, an toàn, tuân thủ định dạng hoặc phù hợp ngữ cảnh.
- **Kiểm tra dựa trên quy tắc:** Các điều kiện bắt buộc như không bịa trường dữ liệu, không đưa nội dung ngoài phạm vi hoặc không tiết lộ thông tin được bảo vệ.
- **Đánh giá con người:** Người đánh giá được huấn luyện chấm theo rubric, có quy trình xử lý bất đồng và kiểm tra nhất quán.
- **So sánh với nguồn có thẩm quyền:** Kiểm tra sự kiện hoặc dữ liệu được trích xuất với nguồn chuẩn được phê duyệt.
- **Chỉ số tổng hợp:** Đo precision, recall, tỷ lệ lỗi, mức độ phù hợp hoặc phân phối kết quả trên tập đánh giá đại diện.

Với đầu ra sinh, không nên chỉ so sánh chuỗi ký tự chính xác nếu nhiều cách diễn đạt đều hợp lệ. Có thể đánh giá nội dung theo các tiêu chí, kiểm tra các sự kiện bắt buộc, xác nhận định dạng có cấu trúc và dùng người đánh giá cho khía cạnh cần phán đoán.

Rubric cần mô tả các mức điểm bằng hành vi quan sát được. Ví dụ, thay vì ghi “câu trả lời tốt”, hãy xác định câu trả lời có nêu đúng các dữ kiện bắt buộc, không mâu thuẫn với nguồn, trả lời đúng câu hỏi và nêu giới hạn khi thiếu bằng chứng hay không.

Đánh giá con người cũng có sai lệch. Nên dùng nhiều người cho các trường hợp quan trọng, hiệu chuẩn cách chấm bằng ví dụ chuẩn, đo mức đồng thuận và có người phân xử khi bất đồng. Không dùng đánh giá chủ quan như bằng chứng tuyệt đối nếu chưa mô tả cách giảm sai lệch.

## 12. Kết hợp nhiều oracle cho một phép kiểm thử

Một oracle có thể xác nhận một khía cạnh nhưng bỏ qua khía cạnh khác. Với dữ liệu quan trọng, kết hợp nhiều nguồn giúp tăng độ tin cậy.

Ví dụ với hệ thống tính và ghi nhận giao dịch:

| Câu hỏi cần xác nhận | Nguồn oracle phù hợp |
|---|---|
| Số tiền từng giao dịch có đúng quy tắc không? | Quy tắc nghiệp vụ và phép tính tham chiếu độc lập |
| Tổng ghi nợ và ghi có có cân bằng không? | Bất biến kế toán |
| Một giao dịch có bị ghi nhận hai lần không? | Ràng buộc duy nhất và đối chiếu mã giao dịch |
| Trạng thái cuối có nhất quán giữa các dịch vụ không? | Đối chiếu dữ liệu và trạng thái từ các hệ thống liên quan |
| Báo cáo có khớp dữ liệu giao dịch không? | Tổng hợp độc lập từ dữ liệu nguồn đã xác nhận |
| Thời gian xử lý có đáp ứng yêu cầu không? | Ngưỡng hiệu năng trên môi trường và tải đã thống nhất |

Kết hợp oracle giúp nhóm tránh kết luận chỉ từ một chỉ số. Ví dụ, tổng số tiền cân bằng không chứng minh từng giao dịch đều đúng; một giao dịch sai có thể được bù bởi giao dịch sai khác. Cần kiểm tra cả bất biến tổng thể và tính đúng đắn ở từng bản ghi hoặc nhóm bản ghi phù hợp.

## 13. Quy trình lựa chọn và xây dựng oracle

Có thể áp dụng quy trình sau khi thiết kế kiểm thử cho dữ liệu khó dự đoán:

1. **Xác định câu hỏi kiểm thử:** Nêu chính xác điều cần chứng minh và quyết định phụ thuộc vào kết quả.
2. **Phân loại dữ liệu và hành vi:** Xác định đầu ra có xác định, ngẫu nhiên, biến động, xấp xỉ hay phụ thuộc người đánh giá.
3. **Tìm nguồn có thẩm quyền:** Rà soát đặc tả, chính sách, dữ liệu chuẩn, chuyên gia và hệ thống tham chiếu.
4. **Đánh giá tính độc lập:** Xem oracle có dùng chung logic, thư viện, dữ liệu hoặc giả định với hệ thống đang kiểm thử không.
5. **Chọn cách so sánh:** Giá trị chính xác, khoảng, bất biến, quan hệ metamorphic, đối chiếu nhiều triển khai, rubric hoặc ngưỡng thống kê.
6. **Xác định điều kiện và giới hạn:** Nêu miền đầu vào, dữ liệu, phiên bản nguồn, độ chính xác, sai số được phép và trường hợp không áp dụng.
7. **Xác nhận oracle:** Dùng ví dụ đã biết, chuyên gia hoặc nguồn thứ hai để kiểm tra chính oracle.
8. **Tự động hóa phù hợp:** Tạo script, bộ dữ liệu chuẩn hoặc quy tắc kiểm tra có thể lặp lại khi lợi ích lớn hơn chi phí.
9. **Ghi nhận sai khác:** Lưu đầu vào, kết quả thực tế, kết quả oracle, phiên bản và bằng chứng để điều tra.
10. **Duy trì và rà soát:** Cập nhật oracle khi quy tắc, dữ liệu nguồn hoặc môi trường thay đổi; không âm thầm chấp nhận kết quả mới làm chuẩn.

Nếu chưa có oracle đủ tin cậy, hãy ghi rõ giới hạn. Có thể thực hiện kiểm thử thăm dò hoặc thu thập thêm dữ liệu để xây dựng nguồn chuẩn, nhưng không nên tuyên bố đã xác nhận tính đúng đắn chỉ vì chương trình chạy không lỗi.

## 14. Ví dụ thực tế: xác nhận kết quả phân bổ phí vận chuyển

Giả sử một cửa hàng trực tuyến tính phí vận chuyển dựa trên khu vực, trọng lượng, kích thước, loại dịch vụ, chương trình miễn phí và thời điểm đặt hàng. Với hàng nghìn tổ hợp, việc tính expected result thủ công cho từng đơn không khả thi.

Nhóm có thể xây dựng oracle từ nhiều nguồn:

1. **Bảng giá được phê duyệt:** Xác định mức phí theo vùng, trọng lượng và dịch vụ tại thời điểm áp dụng.
2. **Quy tắc nghiệp vụ:** Xác định cách làm tròn, phụ phí, miễn phí, giới hạn kích thước và thứ tự áp dụng khuyến mãi.
3. **Bộ ví dụ chuẩn:** Chuyên gia nghiệp vụ xác nhận các trường hợp thông thường, biên và ngoại lệ.
4. **Phép tính tham chiếu:** Một công cụ độc lập tính phí theo bảng và quy tắc đã xác nhận.
5. **Bất biến:** Phí không âm; dịch vụ không nhận đơn vượt giới hạn; miễn phí vận chuyển không tạo khoản phí dương nếu chính sách quy định miễn toàn bộ.
6. **Metamorphic relation:** Khi chỉ tăng trọng lượng trong cùng một bậc giá, phí không được giảm nếu chính sách không cho phép; khi thay đổi thứ tự sản phẩm trong giỏ, phí tổng không được đổi nếu cách tính không phụ thuộc thứ tự.
7. **Đối chiếu:** So sánh một mẫu kết quả với hệ thống tính phí của nhà vận chuyển, sau khi thống nhất các khoản phí và thời điểm dữ liệu.

Các tình huống kiểm thử cần bao gồm trọng lượng ở ranh giới bậc giá, địa chỉ ngoài vùng phục vụ, kích thước vượt giới hạn, mã miễn phí hết hạn và bảng giá thay đổi. Mỗi kết quả sai lệch phải được xem xét theo phiên bản bảng giá và quy tắc có hiệu lực tại thời điểm giao dịch.

Nếu công cụ tham chiếu và ứng dụng cùng đọc một bảng giá sai, chúng có thể đồng thuận nhưng vẫn tính sai. Vì vậy, bảng giá cần nguồn gốc và phê duyệt riêng; một số ví dụ quan trọng nên được kiểm tra độc lập bởi chuyên gia.

## 15. Quản lý sai số và kết quả gần đúng

Với phép tính số thực, mô phỏng và thuật toán xấp xỉ, so sánh bằng dấu bằng tuyệt đối có thể không phù hợp. Cần xác định loại sai số và ngưỡng chấp nhận dựa trên yêu cầu.

Một số cách so sánh:

- **Sai số tuyệt đối:** \(|actual - expected|\) không vượt quá ngưỡng.
- **Sai số tương đối:** Sai lệch được so với độ lớn của giá trị tham chiếu, phù hợp khi quy mô giá trị thay đổi nhiều.
- **Khoảng chấp nhận:** Kết quả phải nằm trong khoảng đã xác định.
- **So sánh theo đơn vị nghiệp vụ:** Ví dụ tiền tệ phải làm tròn đến đơn vị nhỏ nhất được phép, tọa độ phải nằm trong bán kính sai số đã quy định.
- **So sánh phân phối:** Đánh giá nhiều lần chạy bằng các chỉ số thống kê đã chọn.

Không nên dùng một epsilon tùy ý cho mọi phép tính. Với tiền tệ, quy tắc làm tròn thường phải chính xác theo đơn vị và chính sách. Với số đo vật lý, ngưỡng cần dựa trên độ chính xác của cảm biến hoặc yêu cầu sản phẩm. Với mô hình học máy, ngưỡng cần dựa trên chất lượng chấp nhận được và rủi ro của từng loại lỗi.

Khi kết quả nằm sát ngưỡng, cần quy định trước cách xử lý: chạy thêm mẫu, đánh giá bằng nguồn độc lập, xem xét độ không chắc chắn hay chuyển chuyên gia xác minh. Không nên thay ngưỡng sau mỗi lần thất bại mà không có căn cứ.

## 16. Bảo vệ tính toàn vẹn của oracle

Oracle có thể trở thành nguồn lỗi nếu bị thay đổi không kiểm soát hoặc chịu ảnh hưởng từ hệ thống đang kiểm thử. Cần bảo vệ nó như một tài sản chất lượng:

- Lưu nguồn, phiên bản, ngày hiệu lực và người phê duyệt.
- Tách quyền sửa oracle khỏi quyền thay đổi mã sản phẩm khi mức rủi ro yêu cầu.
- Review thay đổi dữ liệu chuẩn, quy tắc và ngưỡng so sánh.
- Giữ lịch sử thay đổi để biết vì sao expected result đã đổi.
- Dùng kiểm tra độc lập định kỳ để phát hiện oracle lỗi thời hoặc sai.
- Không đưa bí mật, dữ liệu cá nhân không cần thiết hoặc dữ liệu sản xuất chưa được bảo vệ vào bộ chuẩn.
- Theo dõi các lần kiểm thử bị bỏ qua, được miễn hoặc thay đổi ngưỡng.

Với golden master hoặc tập dữ liệu gán nhãn, nên quản lý phiên bản như mã nguồn: có người sở hữu, quy trình review và khả năng tái tạo. Nếu oracle thay đổi, cần đánh giá lại các kết quả kiểm thử trước đó khi thay đổi có ảnh hưởng đến kết luận.

## 17. Những sai lầm thường gặp

- **Dùng chính kết quả của hệ thống làm đáp án:** Hai phía có thể cùng chứa lỗi và tạo ra sự đồng thuận giả.
- **Suy diễn quy tắc nghiệp vụ:** Tester tự đặt expected result khi chính sách chưa được chủ sở hữu xác nhận.
- **Tin rằng đa số luôn đúng:** Nhiều triển khai có thể chia sẻ cùng một lỗi hoặc giả định.
- **Cập nhật golden master tự động:** Lỗi mới bị chấp nhận như hành vi chuẩn.
- **Dùng bất biến quá yếu:** Kiểm tra kết quả không âm hoặc không rỗng có thể bỏ qua sai lệch nghiệp vụ.
- **Dùng metamorphic relation không đúng:** Một quan hệ có vẻ hợp lý nhưng không được đặc tả bảo đảm có thể tạo false failure.
- **Không ghi điều kiện dữ liệu:** Kết quả tham chiếu có thể không còn đúng khi bảng giá, thời gian hoặc chính sách đã thay đổi.
- **Đặt ngưỡng sau khi thấy kết quả:** Làm mất tính khách quan và có thể che giấu lỗi.
- **Đánh giá mô hình bằng một nhãn duy nhất:** Bỏ qua bất đồng hợp lý, ngữ cảnh và mức độ nghiêm trọng của từng loại lỗi.
- **Không phân biệt thiếu oracle với sản phẩm đạt:** Không biết expected result không có nghĩa kết quả thực tế đúng.

## 18. Checklist lựa chọn nguồn xác nhận kết quả

Trước khi triển khai một bộ kiểm thử cho dữ liệu khó dự đoán, nhóm có thể dùng checklist sau:

- [ ] Câu hỏi kiểm thử và quyết định cần hỗ trợ được mô tả rõ.
- [ ] Đã xác định đầu ra cần chính xác tuyệt đối, nằm trong khoảng hay thỏa mãn quan hệ/thuộc tính.
- [ ] Nguồn oracle có căn cứ và người chịu trách nhiệm xác nhận.
- [ ] Oracle đủ độc lập với logic và dữ liệu của hệ thống đang kiểm thử.
- [ ] Miền đầu vào, điều kiện áp dụng và các trường hợp ngoại lệ đã rõ.
- [ ] Ngưỡng sai số hoặc tiêu chí đánh giá được xác định trước khi chạy.
- [ ] Oracle đã được kiểm tra bằng ví dụ chuẩn hoặc nguồn độc lập khác.
- [ ] Phiên bản, thời điểm hiệu lực và nguồn gốc dữ liệu được lưu lại.
- [ ] Sai khác có thể tái hiện bằng cách lưu đầu vào và bằng chứng cần thiết.
- [ ] Quy trình cập nhật oracle có review và người phê duyệt.
- [ ] Giới hạn của oracle và phần chưa thể kết luận được báo cáo rõ.

Khi dữ liệu khó dự đoán, chất lượng kiểm thử phụ thuộc vào cách nhóm xác định điều gì được xem là đúng. Một oracle có căn cứ, đủ độc lập và phù hợp với loại kết quả giúp nhóm kiểm tra được cả giá trị cụ thể lẫn các thuộc tính, quan hệ và xu hướng. Khi nguồn chuẩn được xác minh, quản lý phiên bản và cập nhật có kiểm soát, kết quả kiểm thử trở thành bằng chứng đáng tin cậy hơn cho quyết định chất lượng sản phẩm.
