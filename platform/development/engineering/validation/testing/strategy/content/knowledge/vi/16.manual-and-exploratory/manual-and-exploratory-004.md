# Phân bổ thời gian khám phá trong vòng lặp phát triển

Kiểm thử thăm dò là hoạt động trong đó người kiểm thử vừa tìm hiểu sản phẩm, vừa thiết kế và thực hiện kiểm thử dựa trên những gì quan sát được. Hoạt động này giúp phát hiện hành vi bất ngờ, giả định sai và rủi ro chưa được mô tả đầy đủ trong yêu cầu hoặc bộ kiểm thử hiện có.

Để kiểm thử thăm dò tạo ra giá trị ổn định, nhóm cần dành thời gian cho nó ngay trong vòng lặp phát triển. Nếu chỉ thực hiện vào cuối dự án hoặc khi còn thời gian, những phát hiện quan trọng thường đến quá muộn, khó sửa và dễ bị trì hoãn. Ngược lại, nếu đặt lịch cố định mà không xét đến thay đổi, rủi ro và kết quả trước đó, thời gian có thể bị dùng cho những khu vực ít giá trị.

Phân bổ thời gian khám phá là quyết định về năng lực và thời điểm: ai sẽ khám phá, khám phá phần nào, trong bao lâu, dựa trên tín hiệu nào và kết quả sẽ được đưa trở lại quy trình ra sao. Mục tiêu là tạo các khoảng thời gian có chủ đích để tìm hiểu và kiểm chứng rủi ro, đồng thời giữ khả năng điều chỉnh khi sản phẩm hoặc bằng chứng thay đổi.

## 1. Vì sao cần dành thời gian khám phá trong suốt vòng lặp?

Kiểm thử theo kịch bản có sẵn rất hữu ích khi hành vi và điều kiện đã được hiểu rõ. Tuy nhiên, trong quá trình phát triển, yêu cầu có thể thay đổi, thiết kế có thể chứa giả định chưa được xác minh và các thành phần mới có thể tương tác theo cách nhóm chưa dự đoán.

Kiểm thử thăm dò bổ sung góc nhìn này bằng cách cho phép người kiểm thử điều chỉnh hướng đi dựa trên bằng chứng vừa thu được. Một thao tác bất thường có thể dẫn đến giả thuyết mới; một phản hồi chậm có thể gợi ý kiểm tra trạng thái đồng thời; một thông báo khó hiểu có thể cho thấy người dùng không biết cách phục hồi sau lỗi.

Nếu dành thời gian khám phá xuyên suốt vòng lặp, nhóm có thể:

- Phát hiện câu hỏi nghiệp vụ và yêu cầu mơ hồ trước khi chúng trở thành chi phí sửa đổi lớn.
- Tìm lỗi trong thay đổi mới khi ngữ cảnh kỹ thuật còn rõ và người phát triển vẫn sẵn sàng hỗ trợ.
- Kiểm tra các tương tác giữa chức năng, dữ liệu, vai trò và trạng thái mà kịch bản định sẵn chưa bao phủ.
- Điều chỉnh phạm vi kiểm thử theo rủi ro mới xuất hiện.
- Khám phá lỗi hồi quy ở khu vực bị ảnh hưởng bởi thay đổi.
- Chuyển phát hiện có giá trị thành kiểm thử hồi quy, cải tiến thiết kế hoặc cập nhật yêu cầu.
- Giảm việc dồn toàn bộ hoạt động khám phá vào giai đoạn cuối trước phát hành.

Khám phá sớm không có nghĩa mọi vấn đề đều được phát hiện trước khi viết mã. Một số hành vi chỉ có thể quan sát khi thành phần đã tích hợp hoặc chạy trong môi trường gần thực tế. Vì vậy, thời gian khám phá cần được phân bổ ở nhiều điểm trong vòng lặp, theo bản chất của rủi ro.

## 2. Hiểu đúng thời gian kiểm thử thăm dò

Một phiên kiểm thử thăm dò không phải là khoảng thời gian sử dụng sản phẩm tùy ý. Đó là một hoạt động có mục tiêu, phạm vi, thời lượng và kết quả cần ghi nhận. Người kiểm thử có thể thay đổi các bước trong phiên, nhưng vẫn cần biết mình đang tìm hiểu điều gì và vì sao.

Một phiên thường có:

- **Mục tiêu khám phá:** câu hỏi hoặc rủi ro cần làm rõ.
- **Phạm vi:** chức năng, luồng, thành phần, vai trò hoặc dữ liệu liên quan.
- **Điều kiện:** môi trường, phiên bản, tài khoản và dữ liệu.
- **Timebox:** khoảng thời gian được dành cho phiên.
- **Hướng kiểm tra:** giả thuyết, vùng cần chú ý hoặc gợi ý thao tác.
- **Ghi nhận:** thao tác, quan sát, câu hỏi, lỗi và bằng chứng.
- **Debrief:** tổng hợp điều đã học và hành động tiếp theo.

Timebox là giới hạn thời gian giúp giữ trọng tâm, không phải cam kết rằng mọi rủi ro sẽ được kiểm tra xong trong khoảng đó. Nếu phát hiện vấn đề quan trọng cần điều tra thêm, nhóm có thể tạo một nhiệm vụ tiếp nối hoặc tổ chức phiên mới.

### Phân biệt khám phá với kiểm thử tùy hứng

| Hoạt động | Đặc điểm | Cách quản lý thời gian |
|---|---|---|
| Kiểm thử theo kịch bản | Thực hiện các bước và assertion đã định nghĩa | Ước lượng theo số kịch bản, dữ liệu và thời gian chạy |
| Kiểm thử thăm dò | Học, thiết kế và kiểm tra đồng thời; hướng đi có thể thay đổi | Dành timebox theo mục tiêu và rủi ro |
| Kiểm tra nhanh (ad hoc) | Thao tác không có mục tiêu hoặc ghi nhận rõ ràng | Có thể hữu ích để quan sát ban đầu nhưng khó đo và truy vết |
| Rà soát hoặc điều tra lỗi | Tập trung xác minh một phát hiện hoặc nguyên nhân | Ước lượng theo độ phức tạp và bằng chứng còn thiếu |

Khám phá có thể bắt đầu tự do, nhưng cần chuyển thành một phiên có cấu trúc khi nhóm muốn dùng kết quả làm bằng chứng hoặc giao việc tiếp theo.

## 3. Những nguyên tắc phân bổ thời gian

Một cách phân bổ tốt cần đủ ổn định để nhóm duy trì thói quen, nhưng đủ linh hoạt để thay đổi theo rủi ro.

### Dành thời gian như một phần của công việc phát triển

Không nên xem khám phá là phần việc chỉ làm sau khi phát triển và kiểm thử theo kịch bản đã hoàn tất. Khi lập kế hoạch một tính năng, nhóm cần dự trù thời gian để hiểu hành vi mới, khám phá các giả định và kiểm tra tương tác.

### Phân bổ theo rủi ro và độ bất định

Khu vực mới, phức tạp, có nhiều phụ thuộc hoặc có hậu quả lỗi lớn thường cần nhiều thời gian khám phá hơn khu vực ổn định, ít thay đổi và đã có bằng chứng tốt.

### Chia nhỏ thời gian qua nhiều thời điểm

Một phiên ngắn khi làm rõ yêu cầu có thể tìm ra thiếu sót sớm. Một phiên khác sau khi tích hợp có thể phát hiện vấn đề ở ranh giới. Một phiên trước phát hành có thể tập trung vào các giả thuyết còn lại. Việc chia nhỏ giúp phản hồi xuất hiện đúng lúc.

### Bảo vệ thời gian đã thống nhất

Nếu mọi phiên khám phá đều bị thay thế bởi công việc khẩn cấp khác, hoạt động này sẽ không diễn ra. Nhóm cần thống nhất năng lực dành cho khám phá và chỉ thay đổi lịch khi có lý do rõ ràng.

### Điều chỉnh theo bằng chứng mới

Nếu một phiên phát hiện lỗi nghiêm trọng hoặc một phụ thuộc mới có hành vi không ổn định, nhóm có thể chuyển thời gian từ khu vực ít rủi ro sang khu vực đó. Ngược lại, khu vực đã có bằng chứng tốt và ít thay đổi có thể cần ít thời gian hơn.

### Không dùng khám phá để thay thế mọi kiểm thử khác

Những quy tắc quan trọng, hành vi lặp lại và điều kiện phát hành cần được kiểm tra có thể tái hiện, thường xuyên bằng tự động hóa phù hợp. Khám phá giúp tìm ra điều cần kiểm tra và mở rộng hiểu biết, sau đó kết quả có thể được chuyển thành kiểm thử ổn định.

## 4. Đặt khám phá tại các điểm trong vòng lặp phát triển

Thời điểm phù hợp phụ thuộc vào loại câu hỏi cần trả lời. Không có một phiên duy nhất có thể phát hiện mọi rủi ro.

### Khi làm rõ yêu cầu và tiêu chí chấp nhận

Trước khi triển khai, nhóm có thể khám phá mô hình nghiệp vụ, bản mẫu giao diện, dữ liệu mẫu hoặc hành trình hiện tại. Mục tiêu là phát hiện giả định thiếu rõ ràng và tình huống người dùng chưa được mô tả.

Ví dụ:

- Người dùng có thể hủy thao tác ở bước nào?
- Điều gì xảy ra khi dữ liệu đã thay đổi ở hệ thống khác?
- Vai trò nào được phép xem hoặc sửa thông tin?
- Quy tắc thời gian áp dụng theo múi giờ nào?
- Người dùng nhận được thông tin gì khi một phụ thuộc không sẵn sàng?

Phiên khám phá ở giai đoạn này có thể ngắn, dùng prototype, ví dụ dữ liệu hoặc mô hình trạng thái. Kết quả nên được đưa vào yêu cầu và tiêu chí chấp nhận trước khi nhóm bắt đầu triển khai.

### Trong quá trình phát triển từng thay đổi

Khi chức năng đã có bản chạy được, người kiểm thử có thể khám phá các hành vi mới và kiểm tra giả định trong thiết kế. Đây là thời điểm tốt để phối hợp trực tiếp với người phát triển vì mã và quyết định kỹ thuật còn mới.

Có thể khám phá:

- Đầu vào bất thường và giá trị biên.
- Trạng thái trước và sau thao tác.
- Hành vi khi người dùng thao tác nhanh hoặc gửi lặp.
- Thông báo lỗi và khả năng phục hồi.
- Các vai trò và quyền khác nhau.
- Tương tác với chức năng lân cận.

### Khi tích hợp giữa các thành phần

Sau khi các thành phần kết nối, cần dành thời gian khám phá dữ liệu, trạng thái và lỗi tại ranh giới. Những vấn đề này có thể không xuất hiện khi từng thành phần được kiểm tra riêng.

Ví dụ:

- Phản hồi đến muộn hoặc sai thứ tự.
- Thông điệp được giao lặp.
- Dịch vụ ngoài timeout sau khi đã xử lý yêu cầu.
- Một phần giao dịch thành công, phần khác thất bại.
- Cấu hình hoặc quyền giữa các môi trường khác nhau.

### Trong pull request và tích hợp liên tục

Không phải mọi pull request đều cần một phiên dài. Với thay đổi nhỏ, có thể dành một khoảng khám phá ngắn cho vùng bị ảnh hưởng. Với thay đổi lớn hoặc nhạy cảm, cần phiên riêng sau khi có bản dựng tích hợp.

Mục tiêu là xem xét hành vi mà kiểm thử tự động có thể chưa bao phủ, kiểm tra các giả định mới và đánh giá xem thay đổi có tác động dây chuyền hay không.

### Trước phát hành

Phiên khám phá trước phát hành nên tập trung vào rủi ro còn lại, thay đổi gần đây, các luồng quan trọng và những khu vực có bằng chứng chưa đầy đủ. Không nên dùng phiên này để bắt đầu tìm hiểu toàn bộ sản phẩm từ đầu.

### Sau phát hành và trong vận hành

Phản hồi người dùng, log, cảnh báo và sự cố có thể tạo ra giả thuyết mới. Nhóm nên dành thời gian khám phá để xác minh vấn đề trong môi trường an toàn, hiểu điều kiện gây lỗi và tìm các khu vực có hành vi tương tự.

Không nên thực hiện thao tác gây ảnh hưởng lên dữ liệu thật hoặc người dùng thật nếu chưa có quyền và biện pháp kiểm soát phù hợp. Có thể tái hiện trong môi trường thử nghiệm bằng dữ liệu tổng hợp hoặc bản sao đã được bảo vệ.

## 5. Xác định lượng thời gian cần dành

Thời lượng nên được quyết định dựa trên phạm vi, độ bất định, rủi ro và khả năng sẵn sàng của sản phẩm. Một tỷ lệ cố định cho mọi nhóm thường không phù hợp.

Có thể cân nhắc các yếu tố sau:

- Mức độ mới của chức năng hoặc công nghệ.
- Độ phức tạp của quy tắc và số lượng trạng thái.
- Số lượng điểm tích hợp và phụ thuộc bên ngoài.
- Tác động nếu lỗi xảy ra.
- Lịch sử lỗi và sự cố của khu vực.
- Mức độ thay đổi so với phiên bản trước.
- Chất lượng yêu cầu và mức độ rõ của tiêu chí chấp nhận.
- Chất lượng và phạm vi của kiểm thử tự động hiện có.
- Khả năng chuẩn bị môi trường, dữ liệu và người tham gia.
- Thời gian cần để phân tích và chuyển phát hiện thành hành động.

### Dùng mức rủi ro để chọn timebox

Một hướng dẫn tham khảo:

| Mức rủi ro và độ bất định | Cách phân bổ gợi ý |
|---|---|
| Thấp, hành vi quen thuộc, thay đổi nhỏ | Một phiên ngắn tập trung vào vùng bị ảnh hưởng hoặc khám phá theo cặp với rà soát thay đổi |
| Trung bình, có một số quy tắc hoặc tích hợp mới | Một hoặc nhiều phiên có mục tiêu riêng, kèm thời gian debrief |
| Cao, nhiều trạng thái hoặc phụ thuộc quan trọng | Nhiều phiên qua các giai đoạn, có chuyên gia nghiệp vụ/kỹ thuật tham gia |
| Rất cao, ảnh hưởng tiền, dữ liệu nhạy cảm hoặc hoạt động cốt lõi | Kế hoạch khám phá riêng, ưu tiên theo rủi ro, có phiên xác minh lỗi và thời gian kiểm tra lại |

Không nên hiểu các mức này thành số giờ cố định. Nhóm cần ước lượng theo phạm vi thật và cập nhật sau mỗi phiên.

### Ví dụ về timebox

Có thể bắt đầu với các khoảng thời gian dễ tổ chức:

- 30–45 phút để khám phá một thay đổi nhỏ hoặc một câu hỏi cụ thể.
- 60–90 phút cho một luồng hoặc một nhóm giả thuyết có phạm vi vừa phải.
- 2–3 giờ cho khu vực phức tạp, cần nhiều dữ liệu hoặc phối hợp giữa các thành phần.
- Nhiều phiên nối tiếp khi cần khám phá một hành trình lớn hoặc điều tra vấn đề khó tái hiện.

Đây chỉ là khoảng tham khảo để lập lịch. Nếu phiên kéo dài nhưng không có thêm thông tin mới, nên dừng để debrief và đổi hướng. Nếu rủi ro quan trọng vẫn chưa được kiểm tra, hãy lập phiên tiếp theo thay vì kéo dài không giới hạn.

## 6. Dùng mô hình phân bổ kết hợp

Một cách thực tế là kết hợp hai loại thời gian:

1. **Năng lực khám phá định kỳ:** khoảng thời gian được dành đều trong mỗi vòng lặp để nhóm không phải chờ đến khi có sự cố mới khám phá.
2. **Năng lực khám phá theo sự kiện:** thời gian bổ sung khi có thay đổi lớn, rủi ro mới, lỗi nghiêm trọng hoặc tín hiệu vận hành đáng chú ý.

Cách kết hợp này tạo nhịp làm việc ổn định và vẫn cho phép phản ứng với tình huống mới.

### Năng lực định kỳ

Có thể bố trí:

- Một phiên khám phá ngắn trong mỗi vòng lặp cho tính năng đang phát triển.
- Một phiên theo cặp giữa người phát triển và người kiểm thử khi hoàn tất thay đổi quan trọng.
- Một khoảng thời gian khám phá luồng hoặc khu vực có rủi ro cao trong mỗi sprint.
- Một phiên rà soát phát hiện và khoảng trống sau mỗi mốc tích hợp.

Tần suất cụ thể tùy độ dài sprint, quy mô nhóm và nhịp phát hành. Nhóm nhỏ có thể kết hợp phiên khám phá với buổi refinement hoặc kiểm tra theo cặp. Nhóm lớn có thể phân bổ theo từng nhóm sản phẩm hoặc dịch vụ.

### Năng lực theo sự kiện

Nên dự trù khả năng bổ sung phiên khi:

- Có thay đổi lớn về kiến trúc hoặc hợp đồng.
- Một lỗi nghiêm trọng xuất hiện ở sản xuất.
- Một phụ thuộc bên ngoài thay đổi phiên bản hoặc hành vi.
- Kiểm thử tự động trở nên không ổn định.
- Có phản hồi người dùng lặp lại nhưng chưa rõ nguyên nhân.
- Một luồng quan trọng được sửa sau sự cố.
- Một trạng thái mới hoặc quy tắc nghiệp vụ mới được thêm.

Không nên để mọi sự kiện đều làm gián đoạn kế hoạch. Hãy đánh giá mức độ ảnh hưởng và quyết định có cần thay đổi ưu tiên hay chỉ đưa vào phiên khám phá kế tiếp.

## 7. Phân bổ theo rủi ro, thay đổi và độ bất định

Khi nhiều khu vực cùng cần khám phá, nhóm cần cách chọn thứ tự. Có thể đánh giá từng khu vực theo một số chiều:

- **Tác động:** hậu quả nếu hành vi sai.
- **Khả năng xảy ra:** mức độ phức tạp, thay đổi hoặc lịch sử lỗi.
- **Độ bất định:** mức độ chưa rõ về yêu cầu, thiết kế hoặc hành vi.
- **Mức phơi nhiễm:** số người dùng, giao dịch hoặc thành phần bị ảnh hưởng.
- **Khả năng phát hiện:** khả năng hệ thống hoặc nhóm nhận ra lỗi khi xảy ra.
- **Chi phí kiểm tra:** thời gian và điều kiện cần thiết để tạo bằng chứng.

Có thể dùng thang định tính cao, trung bình và thấp. Không cần tạo điểm số phức tạp nếu nó không giúp nhóm quyết định. Điều quan trọng là giải thích vì sao một khu vực được ưu tiên.

### Ma trận ưu tiên tham khảo

| Khu vực | Tác động | Độ bất định | Ưu tiên khám phá |
|---|---|---|---|
| Tính phí và thanh toán vừa thay đổi | Cao | Cao | Rất cao |
| Màn hình nội dung ít thay đổi | Thấp | Thấp | Thấp |
| API mới kết nối nhà cung cấp bên ngoài | Cao | Cao | Rất cao |
| Bộ lọc báo cáo quen thuộc, ít phụ thuộc | Trung bình | Thấp | Trung bình |
| Quy trình hủy đơn từng có lỗi | Cao | Trung bình | Cao |

Ma trận chỉ minh họa. Nếu một khu vực có hậu quả nghiêm trọng nhưng khả năng xảy ra thấp, vẫn có thể cần khám phá sâu. Không nên để một điểm số tổng hợp làm mất đi rủi ro đặc biệt.

### Ưu tiên theo thay đổi

Mức khám phá nên tăng khi thay đổi:

- Thêm hành vi hoặc trạng thái mới.
- Thay đổi hợp đồng API hoặc schema sự kiện.
- Thay đổi quyền, xác thực hoặc dữ liệu nhạy cảm.
- Thay đổi thuật toán tính toán hoặc quy tắc nghiệp vụ.
- Thay đổi cơ chế retry, timeout hoặc xử lý đồng thời.
- Chạm đến thành phần được nhiều luồng phụ thuộc.
- Sửa lỗi từng gây sự cố nghiêm trọng.

Với thay đổi nhỏ, ổn định và có kiểm thử tự động đáng tin cậy, có thể dành thời gian khám phá ngắn hơn.

## 8. Lập kế hoạch khám phá trong sprint

Thời gian khám phá cần được đưa vào kế hoạch sprint cùng với phát triển, kiểm thử theo kịch bản, sửa lỗi và công việc kỹ thuật khác.

### Trong refinement

Khi xem xét một hạng mục:

1. Xác định mục tiêu người dùng và quy tắc nghiệp vụ.
2. Liệt kê điểm chưa rõ và giả định cần xác minh.
3. Xác định rủi ro và khu vực cần khám phá.
4. Ước lượng thời gian chuẩn bị và phiên khám phá.
5. Xác định ai cần tham gia và môi trường cần có.
6. Đưa kết quả mong đợi vào tiêu chí hoàn tất.

Nếu yêu cầu còn mơ hồ, có thể tổ chức một phiên khám phá prototype hoặc dữ liệu trước khi cam kết phạm vi triển khai.

### Trong planning

Đưa các phiên đã xác định vào năng lực sprint. Đừng chỉ ghi “kiểm thử” mà không nêu mục tiêu. Một công việc khám phá nên có tên, timebox, người phụ trách và đầu ra dự kiến.

Ví dụ:

| Công việc | Timebox minh họa | Kết quả |
|---|---:|---|
| Khám phá quy tắc mã giảm giá mới | 60 phút | Danh sách nhánh và câu hỏi nghiệp vụ |
| Khám phá tích hợp thanh toán | 90 phút | Bằng chứng về timeout, gửi lặp và trạng thái |
| Khám phá hồi quy ở luồng hủy đơn | 60 phút | Phát hiện và khu vực cần chạy lại |
| Debrief và cập nhật kiểm thử | 30 phút | Quyết định về lỗi, test hồi quy và rủi ro còn lại |

Timebox phải tính cả việc chuẩn bị và tổng hợp nếu các công việc này không được bố trí riêng. Nếu chỉ tính thời gian thao tác mà bỏ qua ghi nhận và debrief, lịch sẽ thường xuyên vượt dự kiến.

### Trong daily hoặc đồng bộ nhóm

Không cần báo cáo chi tiết từng thao tác. Chỉ cần nêu:

- Phiên khám phá đã hoàn thành hay chưa.
- Phát hiện nào đang chặn hoặc thay đổi ưu tiên.
- Điều kiện hoặc phụ thuộc nào đang thiếu.
- Cần ai hỗ trợ và khi nào.
- Có cần điều chỉnh thời gian khám phá tiếp theo không.

### Trong review và retrospective

Chia sẻ những điều đã học, rủi ro đã phát hiện, vấn đề còn mở và cải tiến cho vòng lặp tiếp theo. Nếu phiên khám phá liên tục bị dời, hãy tìm nguyên nhân trong cách lập kế hoạch hoặc phân bổ năng lực.

## 9. Thiết kế charter cho mỗi phiên khám phá

Charter là nhiệm vụ ngắn mô tả mục tiêu và phạm vi phiên. Nó giúp người kiểm thử có định hướng mà vẫn được tự do thay đổi cách kiểm tra khi có phát hiện mới.

Một charter nên có:

- **Mục tiêu:** điều cần tìm hiểu hoặc rủi ro cần kiểm tra.
- **Phạm vi:** chức năng, luồng, trạng thái hoặc điểm tích hợp.
- **Giả thuyết:** điều có thể sai hoặc chưa rõ.
- **Dữ liệu và điều kiện:** tài khoản, trạng thái, môi trường và cấu hình.
- **Hướng khám phá:** nhóm thao tác hoặc kỹ thuật gợi ý.
- **Timebox:** thời gian thực hiện.
- **Người tham gia:** người khám phá, người hỗ trợ và người ghi nhận.
- **Điều kiện dừng:** hết thời gian, đạt mục tiêu hoặc cần chuyển sang điều tra riêng.
- **Đầu ra:** phát hiện, câu hỏi, bằng chứng và hành động tiếp theo.

Ví dụ charter:

~~~text
Mục tiêu:
Khám phá cách luồng thanh toán xử lý phản hồi chậm và yêu cầu gửi lặp.

Phạm vi:
Từ lúc xác nhận đơn đến khi trạng thái thanh toán được ghi nhận.

Giả thuyết:
- Timeout có thể xảy ra sau khi nhà cung cấp đã xử lý giao dịch.
- Gửi lại yêu cầu có thể tạo giao dịch trùng.
- Webhook đến lặp có thể cập nhật trạng thái nhiều lần.

Điều kiện:
- Môi trường sandbox.
- Một tài khoản và đơn hàng thử nghiệm.
- Có thể xem log và trạng thái giao dịch.

Hướng khám phá:
- Mô phỏng phản hồi chậm.
- Gửi lại cùng yêu cầu.
- Phát lại webhook.
- Đối chiếu trạng thái đơn và giao dịch.

Timebox:
90 phút.

Đầu ra:
- Phát hiện có thể tái hiện.
- Bằng chứng request/response và trạng thái dữ liệu.
- Rủi ro chưa được kiểm tra.
- Đề xuất kiểm thử hồi quy hoặc điều tra tiếp.
~~~

Charter không phải kịch bản đóng. Nếu phát hiện mới cho thấy rủi ro quan trọng hơn, người kiểm thử có thể đổi hướng và ghi lại lý do trong ghi chú phiên.

## 10. Cấu trúc một phiên khám phá có timebox

Với phiên 60–90 phút, có thể chia thời gian như sau:

| Phần | Thời gian tham khảo | Mục đích |
|---|---:|---|
| Định hướng | 5–10 phút | Nhắc mục tiêu, phạm vi, dữ liệu và rủi ro |
| Khám phá chính | 35–55 phút | Thực hiện thao tác, thử giả thuyết và quan sát |
| Xác minh phát hiện | 10–15 phút | Tái hiện hoặc thu thập thêm bằng chứng |
| Debrief | 10 phút | Tổng hợp điều học được và quyết định tiếp theo |

Đây là cách chia tham khảo. Phiên ngắn có thể chỉ cần vài phút debrief; phiên phức tạp có thể cần một buổi riêng để điều tra.

### Khi nào nên dừng phiên?

Nên dừng hoặc chuyển sang nhiệm vụ khác khi:

- Timebox kết thúc.
- Mục tiêu đã có đủ bằng chứng.
- Môi trường hoặc dữ liệu không còn đáng tin cậy.
- Phát hiện cần điều tra sâu hơn và có thể ảnh hưởng dữ liệu.
- Một rủi ro nghiêm trọng xuất hiện cần báo ngay.
- Hướng khám phá không còn tạo ra thông tin mới.

Không nên kéo dài phiên chỉ để hoàn thành mọi ý tưởng. Hãy ghi nhận giả thuyết chưa thử và ưu tiên lại.

## 11. Phân bổ người tham gia và phối hợp theo cặp

Thời gian khám phá không chỉ phụ thuộc số giờ mà còn phụ thuộc người có mặt. Một phiên với người hiểu nghiệp vụ có thể phát hiện vấn đề khác với phiên chỉ có kỹ sư.

Các cách phối hợp:

- **Người kiểm thử khám phá độc lập:** phù hợp khi cần góc nhìn người dùng hoặc tìm hành vi chưa dự đoán.
- **Khám phá theo cặp với nhà phát triển:** phù hợp khi thay đổi kỹ thuật phức tạp hoặc cần điều tra nhanh.
- **Khám phá cùng chuyên gia nghiệp vụ:** phù hợp khi quy tắc và ngoại lệ chưa rõ.
- **Khám phá theo nhóm nhỏ:** phù hợp với luồng xuyên nhiều thành phần hoặc rủi ro liên nhóm.
- **Khám phá cùng người dùng đại diện:** phù hợp khi cần đánh giá quy trình thực tế và khả năng sử dụng.

Không cần có tất cả vai trò trong mọi phiên. Hãy mời người có thể giải đáp câu hỏi của phiên và tránh làm gián đoạn quá nhiều người.

### Luân phiên để chia sẻ kiến thức

Nếu chỉ một người luôn khám phá một khu vực, hiểu biết có thể tập trung. Có thể luân phiên người khám phá hoặc ghép cặp để nhiều thành viên hiểu sản phẩm, dữ liệu và các rủi ro đặc thù.

Luân phiên không có nghĩa bỏ qua chuyên môn. Với rủi ro bảo mật, dữ liệu hoặc tài chính, vẫn cần người có năng lực phù hợp xem xét kết quả.

## 12. Bảo đảm môi trường và dữ liệu không làm lãng phí timebox

Một phiên khám phá có thể mất phần lớn thời gian nếu tài khoản không hoạt động, dữ liệu không đúng trạng thái hoặc phụ thuộc không sẵn sàng. Cần tính công việc chuẩn bị vào kế hoạch.

Trước phiên, xác nhận:

- Bản dựng và phiên bản đúng phạm vi.
- Môi trường có thể truy cập và đủ ổn định.
- Tài khoản và vai trò đã được cấp.
- Dữ liệu có thể tái tạo và đặt lại.
- Dịch vụ phụ thuộc đang hoạt động hoặc có phương án giả lập.
- Log, trace và công cụ quan sát sẵn sàng.
- Người hỗ trợ có thể tham gia khi cần.
- Có cách dừng an toàn nếu thao tác gây tác động không mong muốn.

Nếu một điều kiện không sẵn sàng, hãy quyết định có thể tiếp tục khám phá phần khác hay phải dời phiên. Ghi nhận thời gian bị mất do chuẩn bị để cải thiện quy trình, không quy toàn bộ thành thời gian khám phá kém hiệu quả.

## 13. Ghi nhận kết quả và chuyển giao sau phiên

Thời gian khám phá chỉ tạo giá trị khi kết quả được chuyển thành hành động. Người kiểm thử nên ghi lại đủ để người khác hiểu điều đã thử, điều quan sát được và lý do cần tiếp tục.

Ghi nhận tối thiểu:

- Charter và timebox.
- Người tham gia và thời điểm.
- Phiên bản, môi trường, dữ liệu và cấu hình.
- Các thao tác đáng chú ý.
- Giả thuyết đã kiểm tra và kết quả.
- Phát hiện cùng bằng chứng.
- Câu hỏi hoặc rủi ro chưa được làm rõ.
- Kiểm thử hồi quy hoặc cập nhật yêu cầu cần tạo.
- Người phụ trách và bước tiếp theo.

### Phân loại đầu ra của phiên

| Đầu ra | Hành động tiếp theo |
|---|---|
| Lỗi có thể tái hiện | Tạo issue, ưu tiên, giao người sửa và kiểm tra lại |
| Dấu hiệu bất thường chưa rõ | Tạo nhiệm vụ điều tra hoặc phiên khám phá tiếp |
| Yêu cầu chưa rõ | Trao đổi với chủ sản phẩm hoặc chuyên gia nghiệp vụ |
| Khoảng trống kiểm thử | Bổ sung kịch bản, kiểm thử tự động hoặc tiêu chí bao phủ |
| Rủi ro đã được xác minh không xảy ra trong điều kiện thử | Ghi điều kiện và giới hạn; không kết luận rủi ro đã biến mất |
| Cải tiến trải nghiệm | Đánh giá giá trị, chi phí và đưa vào backlog |
| Không có phát hiện mới | Ghi phạm vi đã khám phá và điều kiện đã thử |

Một phiên không tìm được lỗi vẫn có thể có giá trị nếu nhóm đã kiểm tra một giả thuyết quan trọng và thu được bằng chứng. Không nên đánh giá phiên chỉ bằng số lỗi được báo.

### Debrief ngắn

Cuối phiên, người tham gia có thể trả lời:

- Mục tiêu ban đầu đã được đáp ứng đến đâu?
- Điều gì mới được phát hiện hoặc hiểu rõ?
- Khu vực nào có rủi ro cao hơn dự đoán?
- Điều gì chưa thể kiểm tra và vì sao?
- Có cần tạo kiểm thử hồi quy hoặc cập nhật yêu cầu không?
- Ai sở hữu hành động tiếp theo và khi nào cần xem lại?

Debrief giúp chuyển kinh nghiệm cá nhân thành kiến thức chung và tránh việc cùng một giả thuyết được khám phá lặp lại mà không có thông tin mới.

## 14. Chuyển phát hiện thành kiểm thử ổn định

Không phải mọi thao tác trong phiên khám phá đều cần tự động hóa. Hãy chọn những phát hiện có giá trị lặp lại hoặc liên quan đến rủi ro quan trọng.

Nên cân nhắc chuyển thành kiểm thử hồi quy khi:

- Lỗi đã xảy ra hoặc có hậu quả nghiêm trọng.
- Quy tắc có thể mô tả rõ bằng điều kiện và assertion.
- Hành vi có khả năng bị ảnh hưởng bởi thay đổi thường xuyên.
- Việc chạy lại thủ công tốn thời gian hoặc dễ bỏ sót.
- Có thể tạo dữ liệu và môi trường ổn định.

Chọn tầng phù hợp. Một lỗi tính toán nên được bảo vệ bằng kiểm thử đơn vị; lỗi hợp đồng bằng kiểm thử hợp đồng; lỗi phối hợp nhiều dịch vụ bằng kiểm thử tích hợp; lỗi trong hành trình người dùng có thể cần một kiểm thử E2E đại diện.

Sau khi tạo kiểm thử tự động, vẫn có thể cần khám phá thêm các giả thuyết mới. Tự động hóa bảo vệ hành vi đã hiểu; khám phá tiếp tục tìm điều chưa biết.

## 15. Theo dõi hiệu quả phân bổ thời gian

Không nên đánh giá hiệu quả chỉ bằng số giờ đã dành hoặc số lỗi tìm được. Cần xem thời gian có tạo ra hiểu biết và bằng chứng hữu ích không.

Một số chỉ số và tín hiệu:

- Tỷ lệ phiên đã thực hiện so với phiên đã lên kế hoạch.
- Tỷ lệ thời gian bị mất do môi trường, dữ liệu hoặc quyền truy cập.
- Số rủi ro ưu tiên cao đã được khám phá hoặc có kế hoạch xử lý.
- Thời gian từ khi phát hiện đến khi có người sở hữu.
- Tỷ lệ phát hiện được tái hiện và xác minh.
- Số phát hiện được chuyển thành kiểm thử hồi quy hoặc cập nhật yêu cầu.
- Lỗi quan trọng được phát hiện trước khi phát hành.
- Mức độ lặp lại của cùng một loại lỗi.
- Phản hồi của nhóm về giá trị và tính khả thi của timebox.

Không nên đặt mục tiêu cứng như mỗi phiên phải tìm được một số lỗi nhất định. Mục tiêu như vậy có thể khiến người kiểm thử tạo báo cáo ít giá trị hoặc ưu tiên lỗi nhỏ dễ tìm.

### Đánh giá cả chi phí cơ hội

Thời gian khám phá sử dụng năng lực của nhóm. Cần so sánh giá trị thu được với công việc bị trì hoãn, nhưng không nên xem khám phá là chi phí phụ có thể loại bỏ mỗi khi sprint bận.

Nếu nhóm liên tục không có thời gian khám phá, đó có thể là dấu hiệu lập kế hoạch thiếu năng lực cho chất lượng, yêu cầu thay đổi quá nhiều hoặc công việc phát triển chưa được phân rã phù hợp. Hãy xử lý nguyên nhân thay vì chỉ rút ngắn phiên.

## 16. Ví dụ: phân bổ thời gian khám phá cho tính năng thanh toán trong sprint hai tuần

Giả sử nhóm phát triển tính năng hỗ trợ một phương thức thanh toán mới. Thay đổi liên quan đến giao diện, dịch vụ đơn hàng, dịch vụ thanh toán, webhook và cập nhật trạng thái giao dịch.

Đây là khu vực có rủi ro cao vì liên quan đến tiền, phụ thuộc bên ngoài và xử lý bất đồng bộ. Nhóm quyết định phân bổ nhiều phiên khám phá ở các thời điểm khác nhau.

### Lịch minh họa

| Thời điểm | Phiên khám phá | Timebox | Mục tiêu |
|---|---|---:|---|
| Đầu sprint | Khám phá quy tắc và prototype | 45 phút | Làm rõ trạng thái, từ chối và hủy |
| Khi có bản dựng đầu tiên | Khám phá giao diện và đầu vào | 60 phút | Tìm lỗi dữ liệu, thông báo và thao tác lặp |
| Sau tích hợp API | Khám phá hợp đồng và phản hồi lỗi | 90 phút | Kiểm tra timeout, mã lỗi và dữ liệu không hợp lệ |
| Sau khi tích hợp webhook | Khám phá thông điệp bất đồng bộ | 90 phút | Kiểm tra lặp, trễ và sai thứ tự |
| Trước khi kết thúc sprint | Khám phá hồi quy có trọng điểm | 60 phút | Kiểm tra tác động đến luồng đặt hàng hiện có |
| Debrief và chuyển giao | Tổng hợp phát hiện | 30 phút | Tạo issue, test hồi quy và danh sách rủi ro còn lại |

Tổng thời gian trong ví dụ là 6 giờ 15 phút, chưa tính phần chuẩn bị môi trường nếu cần một công việc riêng. Đây không phải tỷ lệ bắt buộc cho mọi tính năng; nhóm cần điều chỉnh theo phạm vi và năng lực thực tế.

### Cách điều chỉnh khi phát hiện mới xuất hiện

Giả sử phiên webhook phát hiện cùng một thông điệp có thể cập nhật giao dịch hai lần. Nhóm nên:

1. Ghi lại bằng chứng và xác minh khả năng tái hiện.
2. Đánh giá tác động đến trạng thái đơn và giao dịch.
3. Tạm ưu tiên điều tra và sửa cơ chế idempotency.
4. Chuyển một phần thời gian khám phá hồi quy sang kiểm tra thông điệp lặp và các luồng liên quan.
5. Tạo kiểm thử tích hợp để bảo vệ lỗi đã phát hiện.
6. Xác minh lại sau khi sửa và cập nhật rủi ro còn lại.

Nếu phiên đầu không phát hiện vấn đề lớn và các giả thuyết đã được kiểm tra, nhóm có thể giảm thời gian ở khu vực đó và chuyển sang điểm tích hợp chưa có bằng chứng.

## 17. Ví dụ: duy trì khám phá cho sản phẩm đang vận hành

Với sản phẩm đã phát hành, nhóm không có sprint riêng cho mọi lỗi. Có thể duy trì nhịp khám phá bằng cách gắn phiên vào các sự kiện thường xuyên:

- Sau khi phát hành thay đổi lớn, khám phá luồng bị ảnh hưởng.
- Khi có phản hồi hỗ trợ lặp lại, tái hiện và mở rộng kiểm tra.
- Khi metric hoặc log cho thấy bất thường, khám phá điều kiện gây ra.
- Khi nhà cung cấp thay đổi API, kiểm tra hành vi tích hợp trong môi trường an toàn.
- Trong mỗi chu kỳ bảo trì, chọn một khu vực có nợ kiểm thử hoặc ít được kiểm tra.
- Sau sự cố, khám phá các điều kiện tương tự ở thành phần liên quan.

Có thể dành một phiên ngắn mỗi tuần cho khu vực rủi ro cao và bổ sung phiên theo sự kiện. Nhịp này cần được thống nhất với lịch trực, bảo trì và phát hành của nhóm.

Nếu không có thay đổi hoặc tín hiệu mới, thời gian có thể dùng để khám phá sâu một giả thuyết chưa được kiểm tra hoặc xem lại dữ liệu và quy trình. Không nên tạo hoạt động giả chỉ để lấp đầy lịch.

## 18. Những sai lầm thường gặp khi phân bổ thời gian khám phá

- **Chỉ khám phá ở cuối dự án:** phát hiện đến muộn và khó sửa.
- **Chỉ khám phá khi còn thời gian:** hoạt động liên tục bị dời và không tạo được nhịp ổn định.
- **Dùng một tỷ lệ cố định cho mọi tính năng:** không phản ánh rủi ro và độ bất định.
- **Không có mục tiêu hoặc charter:** phiên dễ trôi sang thao tác ngẫu nhiên.
- **Timebox quá ngắn cho phạm vi phức tạp:** không đủ thời gian hiểu dữ liệu, trạng thái và phụ thuộc.
- **Timebox quá dài mà không debrief:** khó nhận ra khi phiên không còn tạo thông tin mới.
- **Không tính thời gian chuẩn bị và ghi nhận:** lịch thường vượt dự kiến và kết quả không được chuyển giao.
- **Chỉ mời một người kiểm thử quen thuộc:** có thể bỏ lỡ góc nhìn nghiệp vụ, vận hành hoặc người dùng.
- **Không bảo vệ thời gian:** phiên liên tục bị thay bằng công việc khác.
- **Đo thành công bằng số lỗi:** khuyến khích tìm lỗi nhỏ và bỏ qua giá trị học hỏi.
- **Không chuyển phát hiện thành hành động:** cùng một rủi ro phải khám phá lại ở vòng lặp sau.
- **Tự động hóa mọi thứ được tìm thấy:** tạo bộ kiểm thử nặng nề và khó bảo trì.
- **Không điều chỉnh theo bằng chứng:** tiếp tục dành thời gian cho khu vực đã ổn định trong khi rủi ro mới bị bỏ qua.

## 19. Mẫu kế hoạch phân bổ thời gian khám phá

Nhóm có thể dùng mẫu sau trong refinement hoặc sprint planning:

~~~text
VÒNG LẶP / SPRINT:
TÍNH NĂNG / KHU VỰC:
MỤC TIÊU NGHIỆP VỤ:

RỦI RO VÀ ĐỘ BẤT ĐỊNH:
- Rủi ro chính:
- Thay đổi gần đây:
- Phụ thuộc:
- Lịch sử lỗi:
- Bằng chứng hiện có:

KẾ HOẠCH PHIÊN:
1. Mục tiêu:
   Phạm vi:
   Người tham gia:
   Timebox:
   Điều kiện chuẩn bị:
   Đầu ra mong đợi:

2. Mục tiêu:
   Phạm vi:
   Người tham gia:
   Timebox:
   Điều kiện chuẩn bị:
   Đầu ra mong đợi:

NĂNG LỰC DỰ PHÒNG:
- Sự kiện có thể kích hoạt phiên bổ sung:
- Cách điều chỉnh ưu tiên:
- Người quyết định:

SAU PHIÊN:
- Phát hiện:
- Câu hỏi còn mở:
- Kiểm thử hồi quy cần bổ sung:
- Người sở hữu:
- Thời điểm xem xét lại:
~~~

Mẫu nên được điều chỉnh theo quy mô. Với thay đổi nhỏ, một charter ngắn trong ticket có thể đủ. Với rủi ro cao hoặc tích hợp nhiều nhóm, nên có kế hoạch riêng và liên kết đến bằng chứng.

## Kết luận

Phân bổ thời gian khám phá trong vòng lặp phát triển giúp nhóm tìm hiểu sản phẩm và kiểm chứng rủi ro khi còn đủ thời gian để hành động. Thời gian cần được đặt tại những điểm phù hợp: làm rõ yêu cầu, phát triển tính năng, tích hợp, trước phát hành và khi có tín hiệu từ vận hành.

Một kế hoạch hiệu quả kết hợp năng lực khám phá định kỳ với các phiên theo sự kiện, chọn timebox theo rủi ro và độ bất định, chuẩn bị người cùng môi trường, rồi dành thời gian debrief và chuyển phát hiện thành hành động. Khi nhóm theo dõi giá trị của bằng chứng và điều chỉnh ưu tiên theo những gì đã học, kiểm thử thăm dò trở thành một phần tự nhiên của vòng lặp phát triển thay vì công việc chỉ thực hiện khi còn thời gian.
