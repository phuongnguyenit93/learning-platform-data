# Định nghĩa mục tiêu cụ thể, đo được và phù hợp thời hạn

Mục tiêu chất lượng mô tả kết quả chất lượng mà nhóm muốn đạt được trong một phạm vi và khoảng thời gian xác định. Mục tiêu tốt giúp các bên thống nhất điều gì cần cải thiện, đo bằng cách nào, mức nào được xem là đạt và khi nào cần đánh giá kết quả. Trong chiến lược kiểm thử, mục tiêu chất lượng định hướng việc chọn rủi ro cần kiểm soát, loại kiểm thử cần thực hiện và bằng chứng cần thu thập.

Những phát biểu như “hệ thống phải nhanh hơn”, “cần giảm lỗi” hoặc “nâng cao độ tin cậy” thể hiện mong muốn nhưng chưa đủ để lập kế hoạch hay đánh giá. Nhóm cần chuyển mong muốn đó thành một kết quả có phạm vi rõ, chỉ số được định nghĩa, mục tiêu định lượng hoặc tiêu chí quan sát được, phương pháp đo và mốc thời gian.

## 1. Mục tiêu chất lượng là gì?

Mục tiêu chất lượng là kết quả có thể đánh giá được liên quan đến một hoặc nhiều thuộc tính chất lượng của sản phẩm, dịch vụ hoặc quy trình. Tùy bối cảnh, thuộc tính cần cải thiện có thể là:

- **Tính đúng đắn chức năng:** hệ thống thực hiện đúng quy tắc nghiệp vụ và tạo ra kết quả mong đợi.
- **Hiệu năng:** thời gian phản hồi, thông lượng và mức sử dụng tài nguyên đáp ứng nhu cầu.
- **Độ tin cậy:** hệ thống hoạt động ổn định, xử lý lỗi và phục hồi phù hợp.
- **An toàn thông tin:** dữ liệu và chức năng được bảo vệ trước các truy cập hoặc hành vi trái phép.
- **Khả năng sử dụng và tiếp cận:** người dùng có thể hoàn thành tác vụ và hiểu phản hồi của hệ thống.
- **Khả năng tương thích:** sản phẩm hoạt động phù hợp trên các nền tảng, thiết bị và môi trường được hỗ trợ.
- **Khả năng bảo trì:** hệ thống có thể được hiểu, sửa đổi và kiểm tra với chi phí hợp lý.

Mục tiêu chất lượng cần xuất phát từ nhu cầu của người dùng, cam kết dịch vụ, quy định áp dụng và rủi ro của sản phẩm. Không phải mọi thuộc tính đều có cùng mức ưu tiên trong mọi dự án. Ví dụ, hệ thống xử lý thanh toán cần chú trọng tính chính xác, tính toàn vẹn giao dịch và khả năng phục hồi; một ứng dụng đọc tin có thể ưu tiên khả năng sử dụng, khả năng tiếp cận và hiệu năng tải nội dung.

Mục tiêu chất lượng không phải danh sách hoạt động cần hoàn thành. “Viết thêm 50 kiểm thử tự động” là mục tiêu hoạt động. “Giảm số lỗi nghiêm trọng lọt tới người dùng xuống không quá một lỗi trong mỗi bản phát hành trong quý tới” mô tả kết quả chất lượng. Hoạt động kiểm thử có thể góp phần đạt mục tiêu, nhưng số lượng kiểm thử được viết không tự chứng minh sản phẩm đã tốt hơn.

## 2. Phân biệt mục tiêu, chỉ số, mức mục tiêu và tiêu chí chấp nhận

Các khái niệm dưới đây có liên quan nhưng giữ vai trò khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Mục tiêu chất lượng | Kết quả chất lượng cần đạt và lý do cần đạt | Cải thiện tốc độ phản hồi của chức năng tìm kiếm trong giờ cao điểm |
| Chỉ số (metric) | Đại lượng hoặc quy tắc quan sát dùng để đánh giá kết quả | Phân vị thứ 95 của thời gian phản hồi (p95) |
| Đường cơ sở (baseline) | Giá trị hiện tại hoặc giá trị tham chiếu trước khi cải thiện | p95 hiện tại là 1,4 giây trong bài đo tải đã thống nhất |
| Mức mục tiêu (target) | Giá trị hoặc ngưỡng cần đạt | p95 không vượt quá 700 mili giây |
| Tiêu chí chấp nhận | Điều kiện để xác nhận một phạm vi hoặc thay đổi cụ thể đủ điều kiện được chấp nhận | Trong ba lần chạy tải liên tiếp, p95 đều không vượt ngưỡng ở mức tải quy định |
| Hoạt động | Công việc được thực hiện để tiến tới mục tiêu | Tối ưu truy vấn và chạy kiểm thử hiệu năng |

Mục tiêu có thể được chia thành nhiều tiêu chí chấp nhận và hoạt động. Chỉ số cho biết cách quan sát kết quả; mức mục tiêu cho biết kết quả mong muốn. Nếu thiếu định nghĩa chỉ số, hai nhóm có thể đo cùng một tên gọi theo hai cách khác nhau và đưa ra kết luận không thể so sánh.

## 3. Dùng nguyên tắc SMART để định nghĩa mục tiêu

SMART là khung thực hành phổ biến giúp kiểm tra một mục tiêu có đủ rõ để triển khai hay không. Năm thành phần thường được hiểu như sau:

### Specific — Cụ thể

Nêu rõ sản phẩm hoặc phần chức năng, nhóm người dùng, luồng nghiệp vụ, môi trường và điều kiện liên quan. “Cải thiện hiệu năng” quá rộng. “Giảm thời gian phản hồi của API tra cứu đơn hàng đối với người dùng đã đăng nhập khi tải đồng thời ở mức 300 phiên” có phạm vi rõ hơn.

Mục tiêu càng cụ thể thì nhóm càng dễ xác định rủi ro, thiết kế tình huống kiểm thử và hiểu kết quả nào có ý nghĩa. Tuy nhiên, không cần nhồi mọi chi tiết kỹ thuật vào một câu mục tiêu; các điều kiện đo có thể được mô tả trong phần định nghĩa chỉ số.

### Measurable — Đo được

Xác định chỉ số, đơn vị, công thức hoặc quy tắc đánh giá, nguồn dữ liệu và cách lấy mẫu. Có thể đo bằng số đếm, tỷ lệ, thời gian, phân vị, mức độ hoàn thành tác vụ hoặc đánh giá định tính có thang tiêu chí rõ ràng.

Ví dụ, “ít lỗi hơn” chưa đo được. “Số lỗi mức nghiêm trọng cao được xác nhận sau phát hành không vượt quá một lỗi trong mỗi bản phát hành” có thể đo được nếu nhóm thống nhất thế nào là lỗi nghiêm trọng cao, thời điểm tính lỗi và phạm vi bản phát hành.

### Achievable — Khả thi

Mức mục tiêu cần có cơ sở từ đường cơ sở, năng lực kỹ thuật, nguồn lực, thời gian và các phụ thuộc. Đặt mục tiêu quá dễ không tạo ra cải thiện đáng kể; đặt mục tiêu không thể đạt khiến nhóm bỏ qua hoặc tìm cách làm đẹp số liệu.

Khả thi không có nghĩa là chỉ đặt mục tiêu ngang với kết quả hiện tại. Nhóm có thể đặt một bước cải thiện có ý nghĩa, thử nghiệm giải pháp và điều chỉnh khi xuất hiện bằng chứng mới. Các giả định quan trọng cần được ghi lại.

### Relevant — Phù hợp

Mục tiêu cần gắn với nhu cầu người dùng, mục tiêu sản phẩm, cam kết dịch vụ hoặc rủi ro đã nhận diện. Một chỉ số dễ thu thập nhưng không phản ánh vấn đề quan trọng sẽ khiến nhóm tối ưu sai hướng.

Ví dụ, tăng tỷ lệ dòng mã được thực thi có thể hữu ích khi đánh giá phạm vi kiểm thử, nhưng nếu người dùng đang gặp giao dịch trùng thì mục tiêu trực tiếp hơn là giảm và kiểm soát các giao dịch trùng trong điều kiện lỗi hoặc gửi lại yêu cầu.

### Time-bound — Có thời hạn

Nêu ngày hoàn thành hoặc mốc đánh giá, đồng thời xác định khoảng thời gian thu thập dữ liệu. “Trong tương lai gần” không tạo ra cam kết có thể kiểm tra. “Đạt ngưỡng trước ngày 30/06/2027 và duy trì trong bốn tuần đo liên tiếp sau khi triển khai” rõ hơn.

Thời hạn cần phù hợp với bản chất chỉ số. Một bài kiểm thử tải có thể cho kết quả trong một buổi; độ tin cậy hoặc tỷ lệ lỗi sau phát hành cần thời gian quan sát đủ dài. Chỉ đánh giá sau một ngày có thể không phản ánh biến động theo tuần hoặc theo chu kỳ sử dụng.

## 4. Cấu trúc một mục tiêu chất lượng có thể triển khai

Một câu mục tiêu thực tế thường có dạng:

> Đến **[mốc thời gian]**, đối với **[sản phẩm/phạm vi và điều kiện]**, đạt **[mức mục tiêu]** cho **[chỉ số được định nghĩa]**, so với **[đường cơ sở nếu có]**, được đo bằng **[phương pháp và nguồn dữ liệu]** trong **[khoảng thời gian hoặc số lần quan sát]**.

Để mục tiêu không chỉ đúng về câu chữ mà còn dùng được trong công việc, hồ sơ mục tiêu nên ghi rõ:

1. **Lý do và rủi ro liên quan:** vấn đề nào cần giải quyết, ai bị ảnh hưởng và hậu quả nếu không cải thiện.
2. **Phạm vi:** thành phần, chức năng, người dùng, nền tảng, môi trường và điều kiện nằm trong mục tiêu.
3. **Chỉ số và định nghĩa vận hành:** cách tính, đơn vị, mẫu số, cách xử lý dữ liệu thiếu và các trường hợp ngoại lệ.
4. **Đường cơ sở:** giá trị hiện tại, nguồn dữ liệu và khoảng thời gian đã đo; nếu chưa có thì xác định cách thu thập ban đầu.
5. **Mức mục tiêu:** giá trị kỳ vọng, ngưỡng cảnh báo và ngưỡng cần hành động nếu phù hợp.
6. **Phương pháp xác minh:** loại kiểm thử, công cụ, dữ liệu, môi trường hoặc hệ thống giám sát tạo ra bằng chứng.
7. **Thời hạn và nhịp đánh giá:** ngày cần đạt, thời gian quan sát và tần suất xem xét tiến độ.
8. **Người chịu trách nhiệm:** người điều phối mục tiêu, người cung cấp dữ liệu và người có thẩm quyền chấp nhận rủi ro.

Không phải mọi mục tiêu đều cần một biểu mẫu dài. Với mục tiêu nhỏ, các thông tin có thể nằm trong một đoạn mô tả hoặc ticket. Điều quan trọng là người thực hiện và người đánh giá hiểu giống nhau về kết quả cần đạt.

## 5. Chọn chỉ số phản ánh đúng chất lượng

Chỉ số nên đại diện cho điều người dùng hoặc hệ thống thực sự cần. Một vài nhóm chỉ số thường dùng gồm:

| Thuộc tính | Chỉ số có thể dùng | Điều cần định nghĩa rõ |
| --- | --- | --- |
| Hiệu năng | p50, p95 hoặc p99 của thời gian phản hồi; thông lượng; tỷ lệ timeout | Điểm bắt đầu và kết thúc phép đo, tải, dữ liệu, môi trường và phân vị |
| Độ tin cậy | Tỷ lệ sẵn sàng; tỷ lệ yêu cầu thất bại; thời gian phục hồi | Khoảng thời gian dịch vụ được cam kết, cách phân loại sự cố và cách tính thời gian gián đoạn |
| Tính đúng đắn | Số lỗi theo mức độ nghiêm trọng; tỷ lệ giao dịch sai; tỷ lệ kết quả đúng trên bộ dữ liệu xác định | Quy tắc xác nhận lỗi, phạm vi giao dịch và cách xác minh kết quả chuẩn |
| Bảo mật | Số phát hiện theo mức độ; tỷ lệ phát hiện được xử lý trước phát hành | Công cụ, phạm vi quét, tiêu chuẩn phân loại và cách xác nhận phát hiện |
| Khả năng sử dụng | Tỷ lệ hoàn thành tác vụ; thời gian hoàn thành; số lần cần trợ giúp | Hồ sơ người tham gia, tác vụ, điều kiện thử và cách ghi nhận quan sát |
| Hiệu quả kiểm thử | Tỷ lệ yêu cầu quan trọng có bằng chứng kiểm thử; số lỗi nghiêm trọng lọt tới môi trường thật | Phạm vi yêu cầu, tiêu chí “có bằng chứng”, cửa sổ quan sát và nguồn báo cáo lỗi |

### Ví dụ về cách định nghĩa chỉ số

**Phân vị thứ 95 của thời gian phản hồi (p95):** sắp xếp thời gian phản hồi của các yêu cầu hợp lệ theo thứ tự tăng dần; p95 là giá trị mà khoảng 95% quan sát không vượt quá. Chỉ số này giúp nhận diện trải nghiệm của nhóm yêu cầu chậm hơn so với chỉ nhìn vào trung bình. Cần ghi rõ loại yêu cầu, tải, khoảng đo, cách loại bỏ dữ liệu lỗi và nguồn thu thập.

**Tỷ lệ sẵn sàng:** có thể tính theo công thức `thời gian dịch vụ sẵn sàng / thời gian dịch vụ cam kết × 100%`. Nhóm phải thống nhất thế nào là sẵn sàng, thời gian cam kết được tính ra sao, cách xử lý bảo trì theo kế hoạch và cách ghi nhận sự cố. Nếu các định nghĩa khác nhau, tỷ lệ giữa các tháng sẽ không thể so sánh công bằng.

**Tỷ lệ lỗi lọt sau phát hành:** một cách tính tham khảo là `số lỗi được xác nhận sau phát hành trong phạm vi / tổng số lỗi được xác nhận trong phạm vi đó × 100%`. Phạm vi, thời gian theo dõi, cách phân loại mức độ và cách tránh đếm trùng phải được thống nhất. Tỷ lệ này có thể tăng khi hoạt động phát hiện lỗi sau phát hành tốt hơn, vì vậy cần đọc cùng số lỗi tuyệt đối, mức độ nghiêm trọng và mức độ sử dụng sản phẩm.

**Tỷ lệ hoàn thành tác vụ:** `số người tham gia hoàn thành tác vụ theo tiêu chí / tổng số người tham gia hợp lệ × 100%`. Cần xác định tác vụ, tiêu chí hoàn thành, đối tượng tham gia, số lượng mẫu và cách xử lý trường hợp cần trợ giúp. Kết quả từ một nhóm nhỏ cung cấp tín hiệu hữu ích nhưng không tự động đại diện cho toàn bộ người dùng.

### Tránh chọn chỉ số dễ đo nhưng sai trọng tâm

Không nên mặc định một chỉ số càng cao càng tốt. Tăng số lượng kiểm thử tự động có thể làm tăng chi phí bảo trì; tăng độ bao phủ mã có thể không phát hiện lỗi nghiệp vụ; giảm thời gian phản hồi trung bình có thể che giấu một nhóm yêu cầu rất chậm. Cần xem xét chỉ số kết quả cùng chỉ số bảo vệ để phát hiện tác dụng phụ.

Ví dụ, nếu mục tiêu là rút ngắn thời gian phản hồi, nhóm cũng cần theo dõi tỷ lệ lỗi và mức sử dụng tài nguyên. Một thay đổi làm hệ thống phản hồi nhanh hơn nhưng tăng lỗi timeout hoặc làm cạn tài nguyên không phải là cải thiện chất lượng bền vững.

## 6. Quy trình xây dựng mục tiêu chất lượng

Có thể xây dựng mục tiêu theo một chu trình gồm bảy bước:

1. **Thu thập nhu cầu:** trao đổi với người dùng, chủ sản phẩm, vận hành, bảo mật và các bên liên quan để hiểu kết quả họ cần.
2. **Chuyển nhu cầu thành tình huống chất lượng:** mô tả tác nhân, hành động, điều kiện môi trường và kết quả mong đợi. Ví dụ: người dùng gửi yêu cầu thanh toán trong lúc cổng thanh toán phản hồi chậm; hệ thống cần tránh tạo giao dịch trùng và phải hiển thị trạng thái có thể hiểu được.
3. **Đánh giá rủi ro và ưu tiên:** xem xét khả năng xảy ra, mức độ tác động, số người bị ảnh hưởng, khả năng khôi phục và mức độ chưa chắc chắn. Chọn các thuộc tính quan trọng nhất để đặt mục tiêu.
4. **Đo đường cơ sở:** thu thập dữ liệu hiện tại trong điều kiện đại diện. Nếu chưa có dữ liệu, đặt một giai đoạn đo ban đầu và ghi rõ đây là bước xác lập đường cơ sở.
5. **Chọn chỉ số và mức mục tiêu:** định nghĩa công thức, mẫu số, nguồn dữ liệu, ngưỡng và giả định. Kiểm tra mục tiêu có đủ tham vọng nhưng khả thi hay không.
6. **Lập cách xác minh và phân công:** chọn kiểm thử chức năng, tích hợp, hiệu năng, bảo mật, khả năng sử dụng hoặc giám sát phù hợp; xác định người chịu trách nhiệm và nguồn lực.
7. **Theo dõi và điều chỉnh:** xem xét bằng chứng theo lịch, phân tích sai lệch và cập nhật mục tiêu khi yêu cầu, rủi ro hoặc điều kiện thực tế thay đổi. Mọi thay đổi cần có lý do và được thống nhất.

Kiểm thử là một nguồn bằng chứng quan trọng trong chu trình này. Một mục tiêu về hiệu năng có thể cần kiểm thử tải và số liệu giám sát; mục tiêu về tính đúng đắn giao dịch có thể cần kiểm thử biên, kiểm thử tích hợp, kiểm thử lỗi và đối soát dữ liệu. Phương pháp xác minh phải được chọn dựa trên rủi ro và bản chất chỉ số.

## 7. Ví dụ thực tế: đặt mục tiêu cho luồng thanh toán

Giả sử một cửa hàng trực tuyến nhận phản ánh rằng trang thanh toán chậm vào giờ cao điểm và đôi khi khách hàng không biết giao dịch đã hoàn tất hay chưa. Nhóm muốn cải thiện trải nghiệm mà vẫn bảo vệ tính chính xác của giao dịch.

Trước tiên, nhóm xác định các tình huống quan trọng: tạo yêu cầu thanh toán bình thường; người dùng gửi lại yêu cầu; cổng thanh toán phản hồi chậm; kết nối bị ngắt sau khi cổng đã nhận yêu cầu; và hệ thống cập nhật đơn hàng sau khi nhận thông báo thanh toán.

Giả sử dữ liệu minh họa từ giai đoạn đo ban đầu cho thấy p95 của API khởi tạo thanh toán là 1,3 giây trong điều kiện tải đã thống nhất. Nhóm có thể xây dựng các mục tiêu riêng:

| Mục tiêu | Chỉ số và mức cần đạt | Cách xác minh |
| --- | --- | --- |
| Cải thiện tốc độ khởi tạo thanh toán | Trước 30/06/2027, p95 của API khởi tạo thanh toán không vượt quá 800 ms ở mức 300 phiên đồng thời; duy trì kết quả trong ba lần chạy tải liên tiếp | Kiểm thử tải trên môi trường gần giống production, dùng bộ dữ liệu và cấu hình đã ghi nhận; lưu phân bố thời gian phản hồi và tỷ lệ lỗi |
| Ngăn giao dịch bị ghi nhận trùng | Trước khi phát hành phiên bản tiếp theo, không có giao dịch bị ghi nhận trùng trong bộ tình huống kiểm thử gửi lặp, timeout và thử lại đã thống nhất | Kiểm thử tích hợp với cổng thanh toán giả lập, kiểm tra mã định danh yêu cầu, trạng thái giao dịch và dữ liệu đối soát |
| Làm rõ trạng thái cho người dùng | Trước 30/06/2027, ít nhất 90% người tham gia trong vòng đánh giá khả năng sử dụng hoàn thành tác vụ kiểm tra trạng thái thanh toán mà không cần trợ giúp | Thử nghiệm với nhóm người dùng đại diện, cùng kịch bản và tiêu chí hoàn thành đã thống nhất |

Các con số trên chỉ là ví dụ để minh họa cách viết mục tiêu; nhóm dự án cần xác lập mục tiêu thực tế từ đường cơ sở, nhu cầu người dùng, tải dự kiến và mức rủi ro chấp nhận được.

Mỗi mục tiêu tạo ra một kế hoạch xác minh khác nhau. Kiểm thử tải trả lời câu hỏi về tốc độ dưới điều kiện xác định; kiểm thử tích hợp và lỗi trả lời câu hỏi về giao dịch trùng; thử nghiệm khả năng sử dụng đánh giá việc người dùng hiểu trạng thái. Không thể dùng kết quả đạt của một loại kiểm thử để kết luận các mục tiêu còn lại cũng đạt.

Nhóm cũng cần định nghĩa điều gì xảy ra khi không đạt. Ví dụ, nếu p95 vượt ngưỡng trong một lần chạy, cần xem lại tính ổn định của môi trường và điều kiện tải; nếu giao dịch trùng xuất hiện, cần phân tích tác động và xử lý trước khi chấp nhận rủi ro; nếu người dùng không hiểu trạng thái, cần xem lại nội dung thông báo và thiết kế luồng.

## 8. Gắn mục tiêu chất lượng với chiến lược kiểm thử

Mục tiêu chất lượng chỉ có giá trị khi được chuyển thành bằng chứng và quyết định. Với mỗi mục tiêu, nhóm nên trả lời các câu hỏi sau:

- Rủi ro hoặc nhu cầu nào khiến mục tiêu này quan trọng?
- Thuộc tính và phạm vi sản phẩm nào được đánh giá?
- Bằng chứng nào đủ để xác nhận mức mục tiêu?
- Kiểm thử ở cấp nào và trong môi trường nào có thể tạo ra bằng chứng đáng tin cậy?
- Dữ liệu, công cụ, phụ thuộc và người tham gia nào cần có?
- Khi kết quả không đạt hoặc dữ liệu thiếu, ai sẽ phân tích và quyết định bước tiếp theo?

Không phải mọi mục tiêu đều được xác minh hoàn toàn trước khi phát hành. Một số mục tiêu, như độ tin cậy trong điều kiện sử dụng dài hạn, cần được theo dõi sau phát hành. Trong trường hợp đó, nhóm có thể kết hợp kiểm thử trước phát hành với giám sát, cảnh báo, quy trình ứng phó và phương án khôi phục.

Nên liên kết mục tiêu với yêu cầu, rủi ro, trường hợp kiểm thử và kết quả thực hiện. Liên kết này giúp nhóm biết mục tiêu nào đang có bằng chứng, mục tiêu nào chưa được xác minh và thay đổi nào có thể làm mất hiệu lực của bằng chứng cũ.

## 9. Theo dõi tiến độ và xử lý khi mục tiêu thay đổi

Đánh giá mục tiêu không chỉ diễn ra vào ngày kết thúc. Với mục tiêu kéo dài nhiều tuần hoặc nhiều tháng, nhóm nên đặt các mốc xem xét phù hợp để phát hiện sớm xu hướng xấu, thiếu dữ liệu hoặc giả định không còn đúng.

Một lần xem xét nên trả lời:

1. Dữ liệu có đủ số lượng, đúng phạm vi và đúng điều kiện đo không?
2. Kết quả hiện tại đang tiến gần hay đi xa mức mục tiêu?
3. Có thay đổi về sản phẩm, người dùng, tải, môi trường hoặc phụ thuộc làm thay đổi ý nghĩa của chỉ số không?
4. Có tác dụng phụ hoặc hành vi tối ưu chỉ số gây hại cho chất lượng tổng thể không?
5. Cần tiếp tục, thay đổi biện pháp, điều chỉnh thời hạn hay xem xét lại mục tiêu?

Nếu mục tiêu không còn phù hợp, nhóm cần ghi rõ lý do và thống nhất phiên bản mục tiêu mới. Ví dụ, tải thực tế tăng gấp đôi so với giả định ban đầu có thể khiến ngưỡng hiệu năng cần được đánh giá lại. Không nên âm thầm thay đổi mẫu số, loại bỏ các lần đo không thuận lợi hoặc đổi định nghĩa chỉ số sau khi đã thấy kết quả.

Khi kết thúc, báo cáo nên ghi mức mục tiêu, kết quả thực tế, khoảng thời gian đo, phạm vi, chất lượng dữ liệu, sai lệch và rủi ro còn lại. Nếu đạt mục tiêu trong môi trường thử nghiệm nhưng chưa có dữ liệu production, cần nói rõ phạm vi bằng chứng đó.

## 10. Những lỗi thường gặp khi đặt mục tiêu

- **Mục tiêu mơ hồ:** dùng các từ như nhanh, ổn định, tốt hơn mà không có ngưỡng hoặc tiêu chí quan sát.
- **Không có đường cơ sở:** đặt một con số tùy ý nên không biết mức cải thiện có thực tế hay không.
- **Chỉ đo hoạt động:** đếm số test case hoặc số dòng mã được bao phủ mà không liên hệ với kết quả chất lượng.
- **Không định nghĩa mẫu số và phạm vi:** tỷ lệ có thể thay đổi chỉ vì cách đếm khác nhau.
- **Chọn giá trị trung bình cho dữ liệu có đuôi dài:** thời gian phản hồi trung bình có thể che giấu các yêu cầu rất chậm; cần cân nhắc phân vị phù hợp.
- **Đặt thời hạn nhưng thiếu cửa sổ quan sát:** một kết quả tốt trong một lần chạy không chứng minh mục tiêu độ tin cậy dài hạn đã đạt.
- **Có quá nhiều mục tiêu:** nhóm khó tập trung nguồn lực và khó giải thích ưu tiên.
- **Không có người chịu trách nhiệm:** dữ liệu không được thu thập hoặc kết quả không dẫn tới quyết định.
- **Tối ưu một chỉ số gây hại chỉ số khác:** cải thiện tốc độ nhưng tăng lỗi, hoặc tăng độ bao phủ nhưng làm kiểm thử dễ vỡ và tốn bảo trì.
- **Biến mục tiêu thành lời bảo đảm tuyệt đối:** một mục tiêu đạt được chỉ cung cấp bằng chứng trong phạm vi và thời gian đã định.

## 11. Những điểm cần ghi nhớ

- Mục tiêu chất lượng mô tả kết quả cần đạt, gắn với nhu cầu người dùng và rủi ro của sản phẩm.
- Một mục tiêu triển khai được cần cụ thể, đo được, khả thi, phù hợp và có thời hạn.
- Chỉ số phải có định nghĩa vận hành, đơn vị, phạm vi, nguồn dữ liệu và cách tính thống nhất.
- Đường cơ sở giúp đánh giá mức cải thiện và kiểm tra tính khả thi của mục tiêu.
- Mục tiêu chất lượng định hướng loại kiểm thử và bằng chứng cần thu thập; hoạt động kiểm thử hoặc độ bao phủ tự thân không phải kết quả chất lượng.
- Theo dõi kết quả cùng giới hạn, tác dụng phụ và rủi ro còn lại; cập nhật mục tiêu một cách minh bạch khi bối cảnh thay đổi.

## Câu hỏi tự kiểm tra

1. Mục tiêu “làm cho ứng dụng ổn định hơn” còn thiếu những thông tin nào để có thể triển khai và đánh giá?
2. Hãy giải thích sự khác nhau giữa mục tiêu chất lượng, chỉ số, đường cơ sở, mức mục tiêu và tiêu chí chấp nhận.
3. Vì sao cần xác định mẫu số, khoảng thời gian và điều kiện đo khi sử dụng một tỷ lệ làm chỉ số?
4. Một nhóm đặt mục tiêu tăng độ bao phủ mã từ 60% lên 90%. Những bằng chứng nào khác cần có để biết chất lượng sản phẩm thực sự được cải thiện?
5. Hãy chọn một luồng nghiệp vụ, viết một mục tiêu theo SMART và nêu cách kiểm thử hoặc giám sát để xác minh mục tiêu đó.
6. Nếu mục tiêu đạt trong môi trường thử nghiệm nhưng dữ liệu production chưa đủ, bạn nên báo cáo kết quả và giới hạn bằng chứng như thế nào?
