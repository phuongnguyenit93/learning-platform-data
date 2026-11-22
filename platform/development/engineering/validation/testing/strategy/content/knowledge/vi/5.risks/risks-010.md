# Cập nhật đánh giá khi có bằng chứng mới hoặc thay đổi phạm vi

Đánh giá rủi ro trong kiểm thử cần được cập nhật trong suốt vòng đời sản phẩm. Một đánh giá được lập khi bắt đầu dự án chỉ phản ánh hiểu biết tại thời điểm đó. Khi nhóm nhận được kết quả kiểm thử mới, phát hiện sự cố, thay đổi yêu cầu, bổ sung tích hợp hoặc mở rộng đối tượng sử dụng, khả năng xảy ra và mức độ tác động của các rủi ro có thể thay đổi. Nếu vẫn dùng thứ tự ưu tiên cũ, nhóm có thể dành nguồn lực cho những vấn đề đã được kiểm soát trong khi bỏ sót nguy cơ mới.

Cập nhật đánh giá rủi ro là quá trình xem xét lại thông tin, điều chỉnh nhận định và quyết định hành động dựa trên bằng chứng hiện có. Mục đích không phải chỉ đổi màu hoặc điểm số trong một bảng theo dõi. Nhóm cần hiểu điều gì đã thay đổi, bằng chứng mới đáng tin cậy đến đâu, rủi ro nào tăng hoặc giảm, phạm vi nào chưa được xác minh và cần làm gì tiếp theo.

## 1. Vì sao đánh giá rủi ro phải thay đổi theo thời gian?

Rủi ro sản phẩm phụ thuộc vào bối cảnh. Một chức năng ít được sử dụng trong giai đoạn thử nghiệm có thể trở thành luồng quan trọng khi mở rộng triển khai. Một tích hợp ổn định trong nhiều tháng có thể phát sinh nguy cơ khi nhà cung cấp thay đổi API. Một lỗi từng được đánh giá là ít nghiêm trọng có thể trở nên nghiêm trọng hơn khi dữ liệu hoặc quy trình kinh doanh thay đổi.

Đánh giá ban đầu thường dựa trên yêu cầu, thiết kế, kinh nghiệm, giả định và dữ liệu lịch sử. Khi sản phẩm được xây dựng và sử dụng, nhóm có thêm bằng chứng thực tế. Bằng chứng đó có thể:

- Xác nhận một rủi ro đã nhận diện và cho thấy khả năng xảy ra cao hơn dự kiến.
- Cho thấy tác động tiềm tàng lớn hơn vì có thêm người dùng, dữ liệu hoặc quy trình phụ thuộc.
- Làm giảm mức rủi ro khi một biện pháp kiểm soát đã được kiểm chứng trong điều kiện đại diện.
- Phát hiện một rủi ro mới chưa có trong danh sách trước đó.
- Cho thấy giả định hoặc điều kiện của đánh giá cũ không còn đúng.
- Làm thay đổi phạm vi cần kiểm thử, khiến bằng chứng trước đây không còn đại diện.

Vì vậy, đánh giá rủi ro nên được xem là một nhận định có thời điểm và điều kiện áp dụng. Mỗi kết luận cần cho biết dựa trên thông tin nào và khi nào cần xem xét lại.

## 2. Phân biệt rủi ro, vấn đề đã xảy ra và rủi ro còn lại

Để cập nhật đúng, nhóm cần phân biệt các khái niệm thường xuất hiện trong báo cáo:

- **Rủi ro (risk):** một sự kiện hoặc điều kiện chưa chắc chắn có thể xảy ra và gây ảnh hưởng đến mục tiêu. Ví dụ, khi cổng thanh toán timeout, yêu cầu thử lại có thể tạo giao dịch trùng.
- **Vấn đề hoặc sự cố (issue):** một tình trạng không mong muốn đã xảy ra và cần được xử lý. Ví dụ, một khách hàng đã bị ghi nợ hai lần.
- **Biện pháp kiểm soát (control):** cách ngăn ngừa, phát hiện hoặc giảm tác động của rủi ro. Ví dụ, dùng khóa định danh yêu cầu để bảo đảm thao tác thanh toán có thể gửi lại an toàn.
- **Rủi ro còn lại (residual risk):** phần rủi ro vẫn tồn tại sau khi đã áp dụng biện pháp kiểm soát.
- **Rủi ro được chấp nhận (accepted risk):** rủi ro còn lại mà người có thẩm quyền đồng ý tiếp tục chịu trong điều kiện đã xác định.

Khi một rủi ro đã xảy ra, nhóm cần ghi nhận sự cố và xử lý nguyên nhân. Điều đó không có nghĩa rủi ro biến mất: cùng nguyên nhân có thể tiếp tục gây ra sự cố khác, hoặc tác động có thể lặp lại ở những luồng tương tự. Sau khi sửa lỗi, nhóm cần đánh giá bằng chứng xác minh biện pháp sửa và phần rủi ro còn lại.

## 3. Những sự kiện cần kích hoạt việc đánh giá lại

Không cần chờ đến cuộc họp đánh giá định kỳ nếu xuất hiện thông tin có thể làm thay đổi quyết định. Các tín hiệu thường gặp gồm:

| Tín hiệu mới | Vì sao cần xem xét lại |
| --- | --- |
| Kiểm thử phát hiện lỗi nghiêm trọng hoặc lỗi lặp lại | Khả năng xảy ra hoặc mức độ tác động có thể cao hơn ước lượng ban đầu; có thể còn lỗi cùng nguyên nhân ở phạm vi khác |
| Kiểm thử đạt sau khi sửa lỗi | Có bằng chứng về hiệu quả của biện pháp sửa, nhưng cần kiểm tra điều kiện, phạm vi và khả năng tái phát |
| Kiểm thử bị chặn hoặc không thể tái hiện | Mức độ bất định tăng; nhóm chưa có bằng chứng đủ để kết luận rủi ro thấp |
| Sự cố production hoặc phản hồi người dùng | Cung cấp dữ liệu thực tế về tần suất, tác động và các điều kiện trước đó chưa được mô hình hóa |
| Thay đổi yêu cầu hoặc quy tắc nghiệp vụ | Có thể tạo hành vi mới, thay đổi hậu quả của lỗi hoặc làm mất hiệu lực tiêu chí kiểm thử cũ |
| Thay đổi kiến trúc, mã nguồn hoặc cấu hình | Có thể mở ra đường lỗi mới hoặc làm thay đổi các biện pháp kiểm soát hiện có |
| Thay đổi phiên bản dịch vụ, thư viện hoặc nhà cung cấp | Hợp đồng, hành vi, lỗ hổng và độ tin cậy của phụ thuộc có thể thay đổi |
| Mở rộng người dùng, dữ liệu, tải hoặc nền tảng | Xác suất, quy mô ảnh hưởng và điều kiện vận hành có thể khác trước |
| Thay đổi môi trường triển khai hoặc quy trình vận hành | Các giả định về quyền truy cập, mạng, sao lưu, giám sát và phục hồi có thể không còn phù hợp |
| Có cảnh báo bảo mật, quy định mới hoặc thay đổi mối đe dọa | Mức tác động, nghĩa vụ kiểm soát hoặc mức ưu tiên có thể tăng |

Các thay đổi nhỏ cũng có thể ảnh hưởng đến rủi ro nếu chúng nằm trên đường đi của một luồng quan trọng. Nhóm nên xác định trước những sự kiện nào bắt buộc phải đánh giá lại, ví dụ thay đổi xác thực, xử lý thanh toán, quyền truy cập dữ liệu, schema sự kiện hoặc cơ chế phục hồi.

## 4. Bằng chứng mới cần được đánh giá như thế nào?

Không phải mọi thông tin mới đều có sức nặng như nhau. Trước khi điều chỉnh mức rủi ro, hãy kiểm tra chất lượng và phạm vi của bằng chứng.

**Tính liên quan:** bằng chứng có trực tiếp liên quan đến rủi ro đang xem xét không? Một bài kiểm thử trên luồng đăng nhập có thể không nói lên nhiều về rủi ro tính sai phí vận chuyển.

**Tính đại diện:** điều kiện thử có gần với điều kiện sử dụng dự kiến không? Kết quả trên bộ dữ liệu nhỏ hoặc môi trường giả lập có thể không đại diện cho dữ liệu lớn, tải cao hoặc dịch vụ thật.

**Tính đầy đủ:** đã kiểm tra các trường hợp quan trọng, dữ liệu biên, trạng thái lỗi và phụ thuộc cần thiết chưa? Một lần chạy thành công không đủ để kết luận nếu chỉ mới bao phủ đường đi thuận lợi.

**Tính mới và hiệu lực:** bằng chứng được tạo trên phiên bản, cấu hình và hợp đồng nào? Sau khi thay đổi mã hoặc phụ thuộc, một kết quả cũ có thể không còn áp dụng.

**Khả năng truy nguyên và lặp lại:** có thể xác định mã build, dữ liệu, môi trường, bước thực hiện, nhật ký và kết quả không? Bằng chứng có thể kiểm tra lại giúp giảm tranh luận dựa trên trí nhớ.

**Giới hạn và độ bất định:** có yếu tố nào chưa được quan sát, mô phỏng hoặc kiểm soát? Cần ghi rõ điều chưa biết thay vì chuyển nó thành giả định rằng rủi ro thấp.

Các nguồn bằng chứng có thể bao gồm kết quả kiểm thử chức năng, tích hợp, hiệu năng và bảo mật; báo cáo lỗi; log và số liệu vận hành; sự cố thực tế; phản hồi người dùng; kết quả rà soát kiến trúc; thông báo từ nhà cung cấp; và thay đổi trong yêu cầu hoặc quy định.

Ví dụ, một kiểm thử hợp đồng đạt xác nhận rằng client và provider tuân thủ schema đã mô tả trong phiên bản được kiểm tra. Nó chưa chứng minh dịch vụ luôn sẵn sàng, đáp ứng tải production hoặc xử lý đúng mọi chuỗi giao dịch. Khi cập nhật rủi ro, nhóm cần gắn kết luận với đúng loại bằng chứng.

## 5. Cập nhật mức rủi ro một cách có căn cứ

Rủi ro thường được đánh giá dựa trên khả năng xảy ra và mức độ tác động. Một mô hình đơn giản có thể dùng:

`Mức rủi ro tham khảo = Khả năng xảy ra × Mức độ tác động`

Nhóm có thể dùng thang định tính như thấp, trung bình, cao hoặc thang điểm đã thống nhất. Điểm số hỗ trợ so sánh và ưu tiên; nó không phải xác suất chính xác hay phép đo khách quan tuyệt đối. Cần có mô tả cho từng mức để người đánh giá hiểu giống nhau.

Khi có bằng chứng mới, hãy xem xét riêng từng yếu tố:

1. **Khả năng xảy ra:** dữ liệu mới cho thấy sự kiện xuất hiện thường xuyên hơn, ít hơn hay trong nhiều điều kiện hơn? Có lỗi tương tự ở thành phần khác không?
2. **Mức độ tác động:** phạm vi người dùng, dữ liệu, tiền, hoạt động hoặc nghĩa vụ liên quan có thay đổi không? Có hậu quả dây chuyền hoặc khó phục hồi hơn không?
3. **Khả năng phát hiện:** nếu sự kiện xảy ra, nhóm có nhận biết kịp thời không? Giám sát, cảnh báo và log có đủ để phát hiện trước khi hậu quả lan rộng không?
4. **Khả năng khôi phục:** có thể hoàn tác, đối soát, khôi phục dữ liệu hoặc chuyển sang phương án dự phòng không? Thời gian khôi phục có đáp ứng nhu cầu không?
5. **Mức độ bất định:** dữ liệu có đủ đại diện để giảm độ tin cậy của ước lượng cũ không? Nếu chưa đủ, cần thêm kiểm thử hoặc quan sát nào?

Khả năng phát hiện và khôi phục có thể được ghi như các yếu tố bổ sung thay vì gộp tùy tiện vào một công thức. Nếu tổ chức dùng ma trận rủi ro riêng, hãy theo đúng định nghĩa và quy trình đã thống nhất.

### Rủi ro tăng, giảm hay thay đổi bản chất

- **Tăng:** kiểm thử phát hiện lỗi dễ tái hiện hơn dự kiến, hậu quả được xác định nghiêm trọng hơn hoặc có thêm luồng phụ thuộc.
- **Giảm:** biện pháp kiểm soát được triển khai và có bằng chứng đủ đại diện cho thấy khả năng xảy ra hoặc tác động đã giảm.
- **Không đổi:** thông tin mới không ảnh hưởng đáng kể đến giả định, phạm vi hoặc hiệu lực của biện pháp kiểm soát.
- **Thay đổi:** phạm vi hoặc nguyên nhân thay đổi đến mức cần tạo một mục rủi ro mới, liên kết với mục cũ thay vì chỉ sửa điểm số.

Không nên tự động hạ mức rủi ro chỉ vì một lần kiểm thử đạt hoặc lỗi đã được đóng. Cần xác minh nguyên nhân đã được xử lý, kiểm tra hồi quy có liên quan và xác định điều kiện mà biện pháp kiểm soát thực sự bao phủ.

## 6. Thay đổi phạm vi ảnh hưởng đến đánh giá như thế nào?

Phạm vi kiểm thử xác định chức năng, thành phần, nền tảng, dữ liệu, người dùng và điều kiện được đưa vào đánh giá. Khi phạm vi thay đổi, nhóm cần xem lại cả danh sách rủi ro lẫn mức độ phù hợp của bằng chứng hiện có.

**Mở rộng phạm vi** có thể bổ sung người dùng, khu vực, ngôn ngữ, thiết bị, luồng nghiệp vụ, loại dữ liệu, tích hợp hoặc mức tải. Mỗi phần mở rộng có thể tạo điều kiện lỗi mới và làm tăng quy mô tác động.

**Thu hẹp phạm vi** có thể loại bỏ một luồng hoặc nền tảng khỏi lần phát hành. Điều này có thể giảm rủi ro trong phạm vi phát hành hiện tại, nhưng cần xác nhận chức năng đó thực sự không thể được truy cập và không còn ảnh hưởng gián tiếp đến phần còn lại.

**Thay đổi ranh giới thành phần** có thể chuyển trách nhiệm giữa dịch vụ, thêm lớp trung gian hoặc thay đổi nơi thực hiện xác thực và kiểm tra dữ liệu. Những rủi ro trước đây được kiểm soát ở một thành phần có thể xuất hiện ở thành phần khác.

**Thay đổi phụ thuộc** như nâng phiên bản API, thay nhà cung cấp, thay cơ sở dữ liệu hoặc chuyển sang broker khác có thể làm bằng chứng hợp đồng và tích hợp cũ mất hiệu lực.

Với mỗi thay đổi phạm vi, nhóm nên hỏi:

- Những thành phần, người dùng, dữ liệu hoặc điều kiện nào vừa được thêm, bỏ hoặc thay đổi?
- Các rủi ro đã nhận diện có còn đúng với kiến trúc và luồng mới không?
- Có rủi ro mới nào do giao diện, phụ thuộc hoặc cách vận hành thay đổi không?
- Bằng chứng nào trước đây không còn áp dụng vì phiên bản, môi trường hoặc điều kiện đã khác?
- Cần kiểm thử lại, mở rộng kiểm thử hay chỉ cập nhật tài liệu và lý do?
- Ai cần xem xét và chấp nhận rủi ro còn lại sau thay đổi?

## 7. Quy trình thực hành để cập nhật đánh giá

Một quy trình nhất quán giúp nhóm tránh thay đổi điểm số tùy cảm tính. Có thể thực hiện theo tám bước:

1. **Ghi nhận tín hiệu:** lưu sự kiện, thay đổi hoặc bằng chứng mới, thời điểm phát hiện, nguồn và người cung cấp.
2. **Xác định phạm vi ảnh hưởng:** liên kết tín hiệu với yêu cầu, thành phần, luồng nghiệp vụ, phiên bản, người dùng và rủi ro liên quan.
3. **Kiểm tra giả định cũ:** xác định điều kiện nào còn đúng, điều kiện nào đã thay đổi và bằng chứng cũ nào còn hiệu lực.
4. **Nhận diện rủi ro mới hoặc thay đổi:** cập nhật nguyên nhân, sự kiện có thể xảy ra, hậu quả và mối liên hệ với các rủi ro khác.
5. **Đánh giá lại:** xem xét khả năng xảy ra, tác động, khả năng phát hiện, khả năng khôi phục và mức độ bất định theo phương pháp của nhóm.
6. **Chọn hành động:** bổ sung kiểm thử, sửa lỗi, thay đổi thiết kế, tăng giám sát, giới hạn phạm vi, chuẩn bị phương án khôi phục hoặc đề xuất chấp nhận rủi ro.
7. **Phân công và đặt thời điểm xem xét:** chỉ định người chịu trách nhiệm, thời hạn, điều kiện hoàn thành và người có thẩm quyền quyết định.
8. **Ghi nhận kết quả và truy nguyên:** lưu nhận định trước và sau, bằng chứng hỗ trợ, lý do thay đổi, quyết định, rủi ro còn lại và thời điểm đánh giá tiếp theo.

Không phải mọi tín hiệu đều cần một cuộc đánh giá lớn. Một thay đổi nhỏ có thể được xử lý trong quy trình review hoặc refinement nếu rủi ro thấp. Nhưng các thay đổi ảnh hưởng đến dữ liệu nhạy cảm, tiền, quyền truy cập, tính toàn vẹn, khả năng phục hồi hoặc điều kiện phát hành cần được xem xét rõ ràng và có người chịu trách nhiệm.

## 8. Ví dụ: cập nhật rủi ro khi thay đổi cổng thanh toán

Giả sử hệ thống thương mại điện tử ban đầu dùng một cổng thanh toán. Nhóm đã kiểm thử các trường hợp thanh toán thành công, bị từ chối và timeout. Hệ thống dùng mã định danh yêu cầu để tránh tạo giao dịch trùng khi người dùng gửi lại yêu cầu.

Trong một đợt thay đổi, nhóm chuyển sang phiên bản API mới của nhà cung cấp. Tài liệu mới quy định khóa định danh yêu cầu có thời hạn lưu ngắn hơn và cách truy vấn trạng thái giao dịch được thay đổi. Đồng thời, lưu lượng dự kiến tăng gấp đôi.

Đánh giá cũ không còn đủ vì hai giả định đã thay đổi: hành vi của phụ thuộc bên ngoài và tải vận hành. Nhóm cần cập nhật các rủi ro liên quan:

| Rủi ro | Bằng chứng hoặc thay đổi mới | Đánh giá cần cập nhật | Hành động kiểm thử hoặc kiểm soát |
| --- | --- | --- | --- |
| Giao dịch trùng khi gửi lại sau timeout | Thời hạn lưu khóa idempotency thay đổi | Khả năng giao dịch trùng có thể tăng nếu thử lại sau thời hạn mới | Kiểm thử gửi lặp trước và sau thời hạn, truy vấn trạng thái và đối soát giao dịch |
| Không xác định được trạng thái thanh toán | Cách truy vấn trạng thái trong API mới khác trước | Bằng chứng cũ về xử lý timeout có thể không còn áp dụng | Kiểm thử adapter với phản hồi mới, lỗi mạng và trạng thái không xác định |
| Thời gian phản hồi tăng khi tải cao | Lưu lượng dự kiến tăng gấp đôi | Tác động đến trải nghiệm và timeout có thể tăng | Kiểm thử tải theo mức lưu lượng mới, theo dõi p95, p99 và tỷ lệ timeout |
| Đơn hàng và giao dịch mất đồng bộ | Luồng cập nhật trạng thái thay đổi theo API mới | Có thể xuất hiện trạng thái thanh toán và đơn hàng không nhất quán | Kiểm thử tích hợp, thử lại thông điệp và đối soát dữ liệu |

Nhóm ghi lại bằng chứng từ tài liệu phiên bản mới, cập nhật hợp đồng, chạy kiểm thử adapter và kiểm thử tích hợp trên sandbox. Nếu sandbox không mô phỏng đầy đủ tải hoặc thời hạn lưu khóa như production, nhóm phải nêu giới hạn đó. Việc kiểm thử đạt trên sandbox chỉ giảm bất định trong phạm vi đã mô phỏng.

Trước khi phát hành, người phụ trách rủi ro xem xét kết quả, các trường hợp chưa kiểm tra và phương án xử lý khi nhà cung cấp không phản hồi. Nếu rủi ro giao dịch trùng vẫn vượt ngưỡng chấp nhận, nhóm có thể trì hoãn luồng chuyển đổi, giới hạn phạm vi triển khai hoặc yêu cầu biện pháp kiểm soát bổ sung. Quyết định cần dựa trên mức rủi ro còn lại và thẩm quyền đã xác định.

## 9. Ghi nhận thay đổi trong hồ sơ rủi ro

Hồ sơ rủi ro cần đủ thông tin để một người khác hiểu vì sao đánh giá thay đổi. Với mỗi rủi ro, có thể lưu các trường sau:

| Trường thông tin | Nội dung cần ghi |
| --- | --- |
| Mã và tên rủi ro | Định danh ổn định và mô tả ngắn gọn |
| Nguyên nhân, sự kiện, hậu quả | Điều kiện gây ra, sự kiện có thể xảy ra và ảnh hưởng |
| Phạm vi liên quan | Thành phần, luồng, phiên bản, môi trường, người dùng và dữ liệu |
| Đánh giá trước đó | Mức khả năng, tác động và trạng thái trước khi có thông tin mới |
| Bằng chứng mới | Nguồn, ngày, kết quả, điều kiện và giới hạn |
| Đánh giá hiện tại | Mức rủi ro mới và lý do thay đổi hoặc giữ nguyên |
| Biện pháp kiểm soát | Hành động phòng ngừa, phát hiện, giảm thiểu hoặc phục hồi |
| Rủi ro còn lại | Phần chưa được loại bỏ sau khi áp dụng biện pháp |
| Chủ sở hữu và người quyết định | Người theo dõi, người thực hiện và người chấp nhận rủi ro |
| Hành động và hạn hoàn thành | Kiểm thử, sửa đổi, giám sát hoặc quyết định tiếp theo |
| Lịch sử cập nhật | Ai thay đổi, thời điểm, lý do và tham chiếu bằng chứng |

Ví dụ về một bản ghi ngắn:

```text
RISK-PAY-04 — Giao dịch có thể bị ghi nhận trùng khi thử lại sau timeout
Phạm vi: API thanh toán phiên bản mới; luồng đặt hàng trực tuyến
Đánh giá trước: Trung bình
Tín hiệu mới: Nhà cung cấp thay đổi thời hạn lưu khóa idempotency
Bằng chứng: Tài liệu API phiên bản mới; kiểm thử sandbox với yêu cầu gửi lại
Đánh giá hiện tại: Cao cho đến khi kiểm chứng thời hạn và cơ chế truy vấn trạng thái
Biện pháp: Lưu mã giao dịch nội bộ, truy vấn trạng thái trước khi thử lại, đối soát
Rủi ro còn lại: Sandbox chưa mô phỏng đầy đủ tải production
Chủ sở hữu: Nhóm thanh toán
Hành động tiếp theo: Kiểm thử tải và thử lại theo thời hạn; đánh giá trước phát hành
```

Đây là ví dụ minh họa cách ghi nhận, không phải kết luận cho một hệ thống thực tế. Điểm quan trọng là đánh giá mới có thể truy nguyên đến thay đổi và bằng chứng cụ thể.

## 10. Quyết định hành động theo mức rủi ro mới

Sau khi cập nhật đánh giá, nhóm cần chuyển nhận định thành hành động phù hợp. Các lựa chọn thường gồm:

- **Tránh rủi ro:** thay đổi thiết kế hoặc loại bỏ luồng gây rủi ro. Ví dụ, tạm thời không bật phương thức thanh toán mới nếu chưa xác minh được cách xử lý timeout.
- **Giảm khả năng xảy ra:** bổ sung xác thực, kiểm soát đầu vào, khóa định danh, giới hạn lưu lượng hoặc kiểm thử trước khi triển khai.
- **Giảm tác động:** bổ sung sao lưu, đối soát, cơ chế hoàn tác, phân vùng triển khai hoặc giới hạn số người dùng ban đầu.
- **Tăng khả năng phát hiện:** thêm log có cấu trúc, chỉ số, cảnh báo và theo dõi các trạng thái bất thường.
- **Chuyển giao hoặc chia sẻ:** dùng cam kết dịch vụ, điều khoản hợp đồng, bảo hiểm hoặc trách nhiệm hỗ trợ của nhà cung cấp khi phù hợp. Việc này không xóa bỏ trách nhiệm quản lý rủi ro của nhóm sử dụng.
- **Chấp nhận rủi ro:** tiếp tục trong điều kiện đã hiểu rõ mức rủi ro còn lại, có người đủ thẩm quyền phê duyệt và có kế hoạch theo dõi.

Chấp nhận rủi ro cần ghi rõ phạm vi, lý do, thời hạn hiệu lực và điều kiện khiến quyết định phải được xem xét lại. Không nên coi im lặng hoặc thiếu thời gian kiểm thử là sự chấp nhận mặc nhiên.

Với rủi ro vượt ngưỡng, cần chuyển cấp đến người có thẩm quyền theo quy trình của tổ chức. Nhóm kiểm thử cung cấp bằng chứng và khuyến nghị; quyết định chấp nhận rủi ro kinh doanh phải thuộc đúng vai trò chịu trách nhiệm.

## 11. Duy trì đánh giá rủi ro trong vòng đời phát triển

Để việc cập nhật trở thành một phần của công việc, có thể gắn nó với các điểm kiểm soát sẵn có:

- **Khi refinement yêu cầu:** rà soát rủi ro mới do thay đổi quy tắc nghiệp vụ, người dùng hoặc dữ liệu.
- **Khi review thiết kế:** đánh giá lại ranh giới thành phần, phụ thuộc, quyền truy cập, khả năng phục hồi và giả định kiến trúc.
- **Khi review mã nguồn:** xem thay đổi có ảnh hưởng đến đường đi quan trọng, kiểm soát bảo mật hoặc xử lý lỗi không.
- **Khi chạy kiểm thử:** cập nhật đánh giá khi phát hiện lỗi, kết quả bất thường, trường hợp bị chặn hoặc phạm vi chưa bao phủ.
- **Trước phát hành:** xem lại bằng chứng mới nhất, lỗi còn mở, thay đổi phạm vi, rủi ro còn lại và điều kiện chấp nhận.
- **Sau phát hành:** dùng log, chỉ số vận hành, sự cố và phản hồi người dùng để kiểm tra giả định và điều chỉnh ưu tiên.

Đối với sản phẩm thay đổi thường xuyên, nhóm có thể tổ chức đánh giá rủi ro ngắn theo từng đợt phát hành hoặc theo thay đổi quan trọng. Đối với thành phần ít thay đổi, chu kỳ định kỳ có thể phù hợp hơn. Tần suất nên dựa trên tốc độ thay đổi và mức tác động nếu rủi ro xảy ra.

## 12. Những lỗi thường gặp khi cập nhật đánh giá

- **Chỉ đổi điểm số mà không ghi lý do:** người đọc không biết bằng chứng nào dẫn đến thay đổi và không thể xem xét lại.
- **Hạ rủi ro sau một lần kiểm thử đạt:** kết quả đơn lẻ có thể không đại diện cho dữ liệu, tải hoặc điều kiện lỗi.
- **Giữ nguyên đánh giá sau khi phạm vi thay đổi:** giả định cũ có thể đã mất hiệu lực.
- **Coi kiểm thử bị chặn là kiểm thử đạt:** thiếu bằng chứng phải được thể hiện là bất định hoặc phần chưa xác minh.
- **Đóng rủi ro ngay khi đóng lỗi:** sửa một lỗi cụ thể không nhất thiết xử lý hết nguyên nhân hoặc các tình huống tương tự.
- **Không phân biệt sự cố với rủi ro:** sự cố cần xử lý ngay; đánh giá rủi ro xem xét khả năng tái diễn và hậu quả trong tương lai.
- **Bỏ qua phụ thuộc bên ngoài:** thay đổi của nhà cung cấp, API, chứng thư hoặc dịch vụ hạ tầng có thể làm thay đổi rủi ro.
- **Không xác định người chịu trách nhiệm:** đánh giá không dẫn đến hành động hoặc quyết định đúng hạn.
- **Chấp nhận rủi ro không có thời hạn:** điều kiện và bối cảnh có thể thay đổi nhưng quyết định cũ vẫn bị xem như còn hiệu lực.

## 13. Những điểm cần ghi nhớ

- Đánh giá rủi ro là nhận định theo thời điểm và điều kiện; cần cập nhật khi có bằng chứng mới hoặc thay đổi phạm vi.
- Bằng chứng phải được xem xét về tính liên quan, đại diện, đầy đủ, mới, truy nguyên và giới hạn.
- Cần phân biệt rủi ro, sự cố đã xảy ra, biện pháp kiểm soát và rủi ro còn lại.
- Khi cập nhật, xem xét khả năng xảy ra, tác động, khả năng phát hiện, khả năng khôi phục và mức độ bất định.
- Thay đổi phạm vi có thể tạo rủi ro mới và làm mất hiệu lực của bằng chứng cũ.
- Mọi thay đổi đánh giá cần có lý do, nguồn bằng chứng, người chịu trách nhiệm, hành động tiếp theo và lịch sử truy nguyên.
- Chỉ người có thẩm quyền mới có thể chấp nhận rủi ro còn lại theo quy trình đã thống nhất.

## Câu hỏi tự kiểm tra

1. Vì sao một đánh giá rủi ro được lập ở đầu dự án có thể không còn phù hợp sau vài lần phát hành?
2. Hãy phân biệt rủi ro, sự cố đã xảy ra, biện pháp kiểm soát và rủi ro còn lại bằng một ví dụ thực tế.
3. Một kiểm thử bị chặn do môi trường không sẵn sàng. Bạn nên cập nhật đánh giá rủi ro như thế nào và vì sao không thể xem trường hợp đó là đạt?
4. Khi nhà cung cấp thay đổi API, những giả định và bằng chứng nào cần được xem xét lại?
5. Nếu phạm vi triển khai mở rộng sang một nền tảng mới, hãy nêu các rủi ro có thể phát sinh và cách thu thập bằng chứng.
6. Một lỗi nghiêm trọng đã được sửa và kiểm thử hồi quy đạt. Cần có thêm thông tin nào trước khi hạ mức rủi ro?
7. Hãy mô tả cách ghi lại một lần cập nhật rủi ro sao cho người khác có thể truy nguyên lý do và quyết định.
