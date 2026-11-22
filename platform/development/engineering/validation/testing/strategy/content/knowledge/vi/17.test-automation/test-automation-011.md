# Đo hiệu quả tự động hóa bằng phản hồi và lỗi được phát hiện

Tự động hóa kiểm thử có giá trị khi giúp nhóm nhận được thông tin đáng tin cậy về chất lượng sớm hơn, phát hiện vấn đề trước khi chúng ảnh hưởng đến người dùng và đưa ra quyết định phát hành có căn cứ. Số lượng kiểm thử tự động, tỷ lệ dòng mã được bao phủ hoặc số lần pipeline chạy chỉ mô tả hoạt động. Chúng chưa cho biết tự động hóa có phát hiện đúng rủi ro, phản hồi đủ nhanh hay tạo ra chi phí bảo trì quá lớn hay không.

Để đánh giá hiệu quả, cần nhìn tự động hóa như một hệ thống cung cấp phản hồi. Hệ thống đó nhận thay đổi mã nguồn, cấu hình hoặc dữ liệu; chạy các kiểm tra phù hợp; phân loại kết quả; thông báo vấn đề; và giúp nhóm hành động. Một chiến lược đo lường tốt kết hợp tốc độ phản hồi, độ tin cậy của tín hiệu, khả năng phát hiện lỗi, mức bao phủ rủi ro và chi phí duy trì.

## 1. Hiệu quả tự động hóa được thể hiện qua điều gì?

Hiệu quả tự động hóa không đồng nghĩa với việc tự động hóa càng nhiều càng tốt. Một kiểm thử tự động có ích khi nó:

- Kiểm tra một yêu cầu hoặc rủi ro có ý nghĩa.
- Tạo kết quả ổn định trong điều kiện đã xác định.
- Phản hồi đủ nhanh để nhóm xử lý vấn đề khi bối cảnh thay đổi còn mới.
- Phân biệt được lỗi sản phẩm với lỗi môi trường hoặc lỗi của chính kiểm thử.
- Cung cấp thông tin giúp xác định nguyên nhân và hành động tiếp theo.
- Có chi phí phát triển, chạy và bảo trì hợp lý so với giá trị mang lại.

Ví dụ, một bộ kiểm thử có 2.000 trường hợp nhưng thường xuyên thất bại do timeout ngẫu nhiên có thể làm nhóm mất niềm tin và bỏ qua cảnh báo. Một bộ nhỏ hơn, tập trung vào các luồng thanh toán, phân quyền và dữ liệu quan trọng, có kết quả ổn định và chỉ ra nguyên nhân rõ ràng có thể hỗ trợ quyết định tốt hơn.

Do đó, nên đánh giá tự động hóa theo kết quả mà nó tạo ra cho nhóm và sản phẩm, không chỉ theo khối lượng kiểm thử đã xây dựng.

## 2. Xác định mục tiêu trước khi chọn chỉ số

Trước khi đo, hãy xác định vấn đề mà tự động hóa cần giải quyết. Mục tiêu có thể là:

- Rút ngắn thời gian phát hiện lỗi sau mỗi thay đổi.
- Phát hiện sớm lỗi hồi quy ở các luồng nghiệp vụ có rủi ro cao.
- Giảm số lỗi nghiêm trọng lọt tới production.
- Tăng độ tin cậy của kiểm tra trước khi merge hoặc phát hành.
- Giảm thời gian kiểm tra thủ công lặp lại để dành nguồn lực cho khám phá và đánh giá phức tạp.
- Cung cấp bằng chứng nhất quán cho các yêu cầu hoặc tiêu chí phát hành.

Mỗi mục tiêu cần phạm vi, đường cơ sở, chỉ số, ngưỡng và thời gian đánh giá. Ví dụ: “Trong quý tới, giảm thời gian phản hồi p90 của bộ kiểm thử hồi quy pull request từ 18 phút xuống dưới 12 phút, đồng thời duy trì tỷ lệ kiểm thử không ổn định dưới 1% và không loại bỏ kiểm thử cho rủi ro ưu tiên cao.”

Ví dụ này kết hợp tốc độ với chỉ số bảo vệ. Nếu chỉ đặt mục tiêu giảm thời gian pipeline, nhóm có thể đạt con số bằng cách bỏ các kiểm thử quan trọng. Chỉ số bảo vệ giúp nhận ra tác dụng phụ đó.

## 3. Nhóm chỉ số nên theo dõi

Không có một chỉ số đơn lẻ mô tả đầy đủ hiệu quả tự động hóa. Có thể tổ chức các phép đo thành sáu nhóm:

1. **Tốc độ phản hồi:** nhóm biết kết quả nhanh đến đâu.
2. **Độ tin cậy của tín hiệu:** kết quả có ổn định, đúng và có thể hành động không.
3. **Khả năng phát hiện lỗi:** tự động hóa tìm được vấn đề nào trước khi phát hành và có bỏ sót vấn đề nghiêm trọng không.
4. **Mức bao phủ rủi ro:** những yêu cầu, luồng và điều kiện quan trọng nào có bằng chứng tự động.
5. **Chi phí vận hành và bảo trì:** nhóm cần bao nhiêu công sức để giữ bộ kiểm thử hữu ích.
6. **Mức sử dụng phản hồi:** nhóm có điều tra và xử lý những tín hiệu do tự động hóa tạo ra không.

Đo theo các nhóm giúp tránh tối ưu một khía cạnh trong khi làm suy giảm khía cạnh khác.

## 4. Đo tốc độ phản hồi

Tốc độ phản hồi cho biết từ lúc có thay đổi đến khi người phát triển hoặc nhóm chịu trách nhiệm nhận được kết quả có ích mất bao lâu. Phản hồi càng sớm, chi phí điều tra thường càng thấp vì người thực hiện còn nhớ bối cảnh thay đổi.

### Thời gian phản hồi kiểm thử

Có thể đo từ lúc một commit hoặc pull request được gửi đến lúc kết quả kiểm thử liên quan sẵn sàng:

`Thời gian phản hồi = thời điểm có kết quả - thời điểm bắt đầu thay đổi hoặc gửi yêu cầu kiểm tra`

Cần định nghĩa mốc bắt đầu thống nhất. Với pipeline pull request, mốc bắt đầu có thể là thời điểm CI nhận sự kiện; với trải nghiệm lập trình viên, có thể đo từ lúc push commit đến khi trạng thái kiểm tra xuất hiện.

Nên theo dõi trung vị và các phân vị như p90 hoặc p95 thay vì chỉ dùng trung bình. Một số pipeline rất chậm có thể bị che khuất bởi phần lớn lần chạy nhanh.

### Thời gian chờ và thời gian thực thi

Phân rã thời gian tổng thành các phần giúp tìm nút thắt:

- Thời gian chờ runner hoặc tài nguyên CI.
- Thời gian cài đặt, khởi động dịch vụ và chuẩn bị dữ liệu.
- Thời gian thực thi kiểm thử.
- Thời gian thu thập artifact, log và báo cáo.
- Thời gian phân tích hoặc xác nhận kết quả.

Nếu thời gian chờ runner chiếm phần lớn, tối ưu mã kiểm thử sẽ không giải quyết được vấn đề. Nếu khởi động môi trường chậm, có thể cần xem lại cách tạo môi trường hoặc tái sử dụng tài nguyên an toàn.

### Tốc độ theo tầng kiểm thử

Đo riêng các tầng giúp hiểu nhóm nhận phản hồi ở đâu:

| Tầng kiểm thử | Vai trò | Chỉ số thời gian có thể theo dõi |
| --- | --- | --- |
| Thành phần/đơn vị | Phản hồi nhanh về logic cục bộ | p50/p90 thời gian chạy, thời gian CI hoàn tất nhóm test |
| Tích hợp | Xác minh giao tiếp và hạ tầng tại ranh giới | Thời gian khởi tạo dịch vụ, thời gian chạy, thời gian chờ phụ thuộc |
| Hệ thống/E2E | Xác minh hành trình và tương tác nhiều thành phần | Thời gian hoàn tất suite, thời gian chờ trạng thái bất đồng bộ |
| Kiểm tra trước phát hành | Tổng hợp bằng chứng cho phiên bản | Thời gian từ build đến kết quả sẵn sàng quyết định |

Không nên đặt cùng một mục tiêu thời gian cho mọi tầng. Kiểm thử đơn vị cần phản hồi rất nhanh; kiểm thử E2E có thể tốn nhiều thời gian hơn nhưng nên tập trung vào hành trình có giá trị cao.

## 5. Đo độ tin cậy của tín hiệu

Một kết quả kiểm thử chỉ hữu ích khi nhóm có thể tin tưởng và diễn giải nó. Bộ kiểm thử thất bại do môi trường, dữ liệu dùng chung hoặc race condition có thể tạo nhiều cảnh báo giả, khiến nhóm tốn thời gian xác minh.

### Tỷ lệ kiểm thử không ổn định (flaky rate)

Kiểm thử không ổn định là kiểm thử có thể cho kết quả khác nhau trong những lần chạy được cho là tương đương, mà không có thay đổi sản phẩm hoặc điều kiện đầu vào giải thích được.

Một cách tính tham khảo:

`Flaky rate = số trường hợp được xác nhận không ổn định / tổng số trường hợp đã chạy × 100%`

Nhóm cần xác định đơn vị tính là test case, lần chạy hay failure event. Nếu dùng số lần chạy, cần tránh đếm một test nhiều lần không tương đương với các test khác. Có thể báo cáo thêm số lần thất bại được xác nhận là flaky trên tổng số lần chạy.

Các nguyên nhân thường gặp:

- Phụ thuộc thời gian, múi giờ hoặc đồng hồ hệ thống.
- Chờ cố định thay vì chờ điều kiện.
- Dữ liệu hoặc tài nguyên dùng chung giữa các test.
- Thứ tự chạy hoặc tính đồng thời không được kiểm soát.
- Phụ thuộc mạng, dịch vụ bên ngoài hoặc môi trường không ổn định.
- Assertion dựa trên nội dung hoặc thứ tự không được bảo đảm.

Không nên tự động coi mọi lần chạy lại thành công là bằng chứng flaky. Một lần chạy lại có thể thành công vì lỗi sản phẩm chỉ xảy ra không thường xuyên. Cần điều tra log, điều kiện, lịch sử và khả năng tái hiện.

### Tỷ lệ cảnh báo có thể hành động

Có thể theo dõi tỷ lệ thất bại sau phân loại được xác nhận là lỗi sản phẩm hoặc cần hành động cụ thể:

`Tỷ lệ failure có thể hành động = số failure cần hành động / tổng failure đã phân loại × 100%`

Nhóm nên thống nhất các nhóm kết quả: lỗi sản phẩm, lỗi kiểm thử, lỗi môi trường, lỗi hạ tầng CI, dữ liệu không hợp lệ và chưa xác định. Failure chưa phân loại không nên âm thầm được tính là lỗi sản phẩm hoặc bị bỏ khỏi báo cáo.

### Tỷ lệ chạy lại để đạt (rerun-to-pass)

Chỉ số này có thể phản ánh số lần thất bại ban đầu nhưng đạt khi chạy lại mà không có thay đổi mã hoặc cấu hình có liên quan. Tỷ lệ cao là tín hiệu cần điều tra, nhưng không tự chứng minh test flaky: có thể có lỗi sản phẩm thoáng qua, phụ thuộc không ổn định hoặc khác biệt môi trường.

Chạy lại có thể hỗ trợ chẩn đoán, nhưng không nên xóa kết quả thất bại ban đầu hoặc biến kết quả cuối thành PASS mà không giữ lịch sử. Báo cáo cần thể hiện cả lần chạy đầu, số lần thử lại, lý do phân loại và trạng thái cuối.

## 6. Đo khả năng phát hiện lỗi

Khả năng phát hiện lỗi cho biết tự động hóa có tìm được vấn đề mà nhóm quan tâm hay không. Cần xem xét cả lỗi được phát hiện trước phát hành và lỗi vẫn lọt tới người dùng.

### Lỗi được phát hiện trước phát hành

Có thể phân tích:

- Số lỗi được phát hiện bởi từng tầng kiểm thử.
- Mức độ nghiêm trọng và tác động của lỗi.
- Thời điểm phát hiện so với thời điểm đưa thay đổi vào.
- Lỗi được phát hiện ở lần chạy đầu hay sau khi điều tra.
- Yêu cầu hoặc rủi ro mà lỗi liên quan.

Số lượng lỗi phát hiện cao không tự động có nghĩa bộ kiểm thử tốt hơn. Nó có thể phản ánh sản phẩm có nhiều lỗi hơn, thay đổi lớn hơn, phạm vi kiểm thử rộng hơn hoặc công cụ phát hiện nhạy hơn. Cần đọc số liệu cùng mức độ nghiêm trọng, khối lượng thay đổi và lịch sử phát hành.

### Lỗi lọt tới production (escaped defects)

Lỗi lọt là lỗi chỉ được phát hiện sau khi sản phẩm đã được triển khai tới môi trường sử dụng thực tế. Một chỉ số tham khảo:

`Tỷ lệ lỗi lọt = số lỗi được xác nhận sau phát hành trong phạm vi / tổng số lỗi được xác nhận trong phạm vi × 100%`

Cần định nghĩa cửa sổ theo dõi, phạm vi sản phẩm, cách phân loại và cách tránh đếm trùng. Có thể báo cáo riêng lỗi nghiêm trọng hoặc lỗi thuộc luồng rủi ro cao.

Không nên kết luận tự động hóa thất bại chỉ vì có lỗi production. Một số lỗi phụ thuộc quy mô, dữ liệu hoặc hành vi thực tế mà môi trường thử nghiệm không thể tái tạo đầy đủ. Cần phân tích vì sao lỗi lọt: thiếu trường hợp, sai giả định, môi trường không đại diện, dữ liệu không đủ, assertion yếu hay lỗi chỉ xuất hiện sau thời gian dài.

### Hiệu quả phát hiện theo mức độ

Để tránh một số lượng lớn lỗi nhỏ che khuất lỗi nghiêm trọng, nên phân tích theo mức độ tác động. Ví dụ, báo cáo số lỗi nghiêm trọng, cao, trung bình và thấp được phát hiện trước và sau phát hành.

Có thể dùng trọng số để tổng hợp phục vụ xu hướng nội bộ, nhưng phải công bố quy tắc và không để điểm tổng hợp thay thế việc xem xét từng lỗi nghiêm trọng. Một lỗi có khả năng làm mất dữ liệu hoặc thu tiền sai cần được chú ý dù tổng số lỗi khác rất lớn.

## 7. Đánh giá khả năng phát hiện bằng lỗi được cấy hoặc mutation testing

Chỉ dựa vào lỗi thực tế có thể khó đánh giá bộ kiểm thử vì mỗi phiên bản có lượng thay đổi và loại lỗi khác nhau. Một cách bổ sung là cố ý đưa lỗi nhỏ vào bản sao mã để xem bộ kiểm thử có phát hiện hay không.

### Mutation testing

Mutation testing tạo các biến thể mã (mutants) bằng cách thay đổi một biểu thức hoặc toán tử, chẳng hạn đổi `>` thành `>=`, thay giá trị trả về hoặc bỏ một điều kiện. Sau đó chạy bộ kiểm thử:

- **Mutant bị tiêu diệt (killed):** ít nhất một kiểm thử phát hiện khác biệt và thất bại theo cách mong đợi.
- **Mutant sống sót (survived):** bộ kiểm thử không phát hiện thay đổi đó.
- **Mutant tương đương (equivalent):** thay đổi không làm thay đổi hành vi quan sát được trong miền liên quan; không thể kỳ vọng kiểm thử phân biệt nó.
- **Mutant không hợp lệ hoặc không chạy được:** không cung cấp bằng chứng hữu ích cho phép đo.

Một công thức tham khảo:

`Mutation score = số mutant bị tiêu diệt / (tổng mutant hợp lệ - mutant tương đương) × 100%`

Mutation score giúp đánh giá độ nhạy của kiểm thử đối với một số thay đổi trong mã. Nó không đo trực tiếp chất lượng sản phẩm và không chứng minh mọi lỗi nghiệp vụ đều được phát hiện. Kết quả phụ thuộc toán tử mutation, phạm vi mã, cách xử lý mutant tương đương và chất lượng môi trường.

Không nên tối ưu mutation score bằng cách thêm assertion kiểm tra chi tiết nội bộ không có ý nghĩa nghiệp vụ. Hãy xem các mutant sống sót trong mã rủi ro cao, xác định hành vi chưa được kiểm tra và bổ sung trường hợp có giá trị.

### Lỗi được cấy có chủ đích

Nhóm cũng có thể tạo một số lỗi có chủ đích trong môi trường cô lập để đánh giá khả năng phát hiện, ví dụ:

- Thay đổi quy tắc tính phí hoặc làm tròn.
- Bỏ kiểm tra quyền ở một nhánh.
- Làm sai ánh xạ trạng thái API.
- Bỏ thao tác cập nhật dữ liệu hoặc phát sự kiện.
- Thay đổi xử lý timeout hoặc retry.

Việc cấy lỗi phải được giới hạn trong nhánh hoặc môi trường thử nghiệm, có cách khôi phục rõ và không được đưa vào phát hành. Chọn lỗi phản ánh rủi ro thực tế thay vì chỉ các thay đổi cú pháp dễ phát hiện.

## 8. Đo mức bao phủ rủi ro thay vì chỉ đếm test case

Độ bao phủ cho biết phần nào của đối tượng đã được kiểm tra theo một tiêu chí. Nhưng số lượng test case hoặc tỷ lệ dòng mã không thể hiện đầy đủ rủi ro đã được kiểm soát.

Nên liên kết kiểm thử tự động với:

- Yêu cầu hoặc tiêu chí chấp nhận.
- Hành trình nghiệp vụ và trạng thái quan trọng.
- Rủi ro sản phẩm và mức độ tác động.
- Loại dữ liệu, vai trò, nền tảng và điều kiện lỗi.
- Tầng kiểm thử cung cấp bằng chứng.

Ví dụ, luồng thanh toán có thể có 20 test case tự động cho happy path nhưng chưa có trường hợp timeout, gửi lại, giao dịch trùng hoặc đối soát. Tỷ lệ test case đã chạy là 100%, nhưng rủi ro quan trọng vẫn chưa có bằng chứng.

### Ma trận bao phủ theo rủi ro

| Rủi ro | Mức độ | Kiểm thử tự động | Bằng chứng hiện có | Khoảng trống |
| --- | --- | --- | --- | --- |
| Tính tổng đơn hàng sai khi có ưu đãi | Cao | Unit tests cho quy tắc giá và giá trị biên | Kết quả tính tiền trên các nhóm dữ liệu | Cần xác minh thêm tổ hợp ưu đãi ở cấp tích hợp |
| Giao dịch bị ghi nhận hai lần sau timeout | Rất cao | Integration tests gửi lại cùng khóa idempotency | Một số tình huống retry và trạng thái giao dịch | Chưa kiểm tra hết thời hạn khóa và đối soát |
| Người không đủ quyền xem đơn hàng | Cao | API authorization tests theo vai trò | Phản hồi 403 với vai trò không hợp lệ | Chưa kiểm tra mọi endpoint liên quan |
| Giao diện hiển thị sai trạng thái | Trung bình | E2E kiểm tra một số trạng thái | Hành trình thanh toán thành công | Chưa có kiểm thử trạng thái chờ và phản hồi đến muộn |

Ma trận này giúp nhóm biết kiểm thử nào tạo bằng chứng và phần nào vẫn cần khám phá hoặc xác minh thủ công. Một rủi ro có thể cần nhiều test ở các tầng khác nhau.

## 9. Đo chi phí bảo trì và vận hành

Tự động hóa có chi phí liên tục. Bộ kiểm thử cần được cập nhật khi yêu cầu, giao diện, dữ liệu, môi trường hoặc phụ thuộc thay đổi. Nếu chi phí sửa test quá lớn, nhóm có thể giảm phạm vi hoặc mất niềm tin vào kết quả.

Các chỉ số có thể theo dõi:

- Thời gian kỹ sư dành cho điều tra và sửa lỗi kiểm thử.
- Số test phải sửa do thay đổi giao diện hoặc dữ liệu.
- Số pipeline thất bại do hạ tầng hoặc cấu hình.
- Thời gian bảo trì test so với thời gian phát triển tính năng.
- Tỷ lệ kiểm thử bị vô hiệu hóa và thời gian chúng ở trạng thái tắt.
- Chi phí runner, môi trường, license và dịch vụ kiểm thử.
- Số test trùng lặp hoặc không còn gắn với yêu cầu/rủi ro hiện tại.

Không nên dùng số lần test được sửa làm chỉ số xấu một cách máy móc. Một sản phẩm thay đổi nhiều có thể cần cập nhật kiểm thử thường xuyên. Điều cần quan sát là chi phí đó có hợp lý, có thể dự đoán và có duy trì được bằng chứng quan trọng hay không.

### Tỷ lệ kiểm thử bị vô hiệu hóa

Các test bị skip hoặc quarantine có thể che giấu khoảng trống. Nên theo dõi số lượng, lý do, chủ sở hữu, ngày bắt đầu và hạn xem xét. Mỗi test bị vô hiệu hóa cần có quyết định: sửa, thay thế, loại bỏ có căn cứ hoặc khôi phục.

Quarantine là biện pháp tạm thời để cô lập test không ổn định trong khi điều tra. Nó không nên trở thành nơi chứa các kiểm thử quan trọng bị bỏ quên. Nếu test rủi ro cao bị quarantine, cần có biện pháp kiểm tra thay thế và người chịu trách nhiệm.

## 10. Đo việc sử dụng phản hồi và hành động sau thất bại

Pipeline chỉ tạo ra giá trị khi kết quả được xem xét và dẫn đến hành động phù hợp. Có thể theo dõi:

- Thời gian từ khi failure xuất hiện đến khi được phân loại.
- Thời gian từ khi phát hiện lỗi sản phẩm đến khi có người nhận xử lý.
- Tỷ lệ failure có chủ sở hữu và trạng thái điều tra rõ.
- Tỷ lệ lỗi được tái hiện và liên kết với yêu cầu hoặc rủi ro.
- Tỷ lệ lỗi đã sửa được xác minh bằng kiểm thử hồi quy.
- Tỷ lệ cảnh báo bị bỏ qua hoặc đóng mà không có lý do.

Ví dụ, nếu CI phát hiện lỗi trong 3 phút nhưng nhóm mất 2 ngày mới xác định đó là lỗi môi trường hay lỗi sản phẩm, vấn đề nằm ở khả năng phân loại và chẩn đoán. Cần cải thiện log, phân loại failure, tài liệu hoặc trách nhiệm xử lý, không chỉ tối ưu thời gian chạy.

## 11. Xây dựng quy trình phân loại kết quả

Để các chỉ số có ý nghĩa, mọi failure cần được phân loại nhất quán. Một quy trình thực tế:

1. Thu thập kết quả lần chạy đầu, log, trace, artifact, build và môi trường.
2. Xác định test nào thất bại và điều kiện cụ thể.
3. Kiểm tra xem lỗi có tái hiện được trong điều kiện tương đương không.
4. Phân loại nguyên nhân: lỗi sản phẩm, lỗi test, lỗi dữ liệu, lỗi môi trường/hạ tầng hoặc chưa xác định.
5. Gắn failure với yêu cầu, rủi ro, thành phần và người phụ trách.
6. Ghi hành động: sửa sản phẩm, sửa test, ổn định môi trường, bổ sung bằng chứng hoặc điều tra thêm.
7. Chạy lại theo quy tắc đã thống nhất và giữ lịch sử của lần chạy ban đầu.
8. Đóng failure khi có bằng chứng xác nhận và cập nhật chỉ số tương ứng.

Ví dụ về phân loại:

| Nhóm | Dấu hiệu | Hành động |
| --- | --- | --- |
| Lỗi sản phẩm | Kết quả thực tế vi phạm yêu cầu và có thể tái hiện | Tạo/ liên kết defect, đánh giá mức độ và sửa sản phẩm |
| Lỗi kiểm thử | Test có assertion sai, dữ liệu không hợp lệ hoặc phụ thuộc nội bộ không đúng | Sửa test và xác minh lại hành vi mong đợi |
| Lỗi môi trường/hạ tầng | Runner, mạng, database hoặc dịch vụ thử nghiệm không sẵn sàng | Khôi phục môi trường, lưu bằng chứng và chạy lại có kiểm soát |
| Flaky | Kết quả thay đổi trong điều kiện tương đương mà chưa có thay đổi sản phẩm giải thích | Điều tra tính đồng thời, thời gian, dữ liệu và phụ thuộc |
| Chưa xác định | Chưa đủ bằng chứng để kết luận | Giữ trạng thái mở, chỉ định người điều tra và thời hạn |

Không nên tự động đóng mọi failure sau một lần rerun thành công. Nếu nguyên nhân chưa rõ, trạng thái nên là chưa xác định hoặc cần điều tra.

## 12. Thiết kế bảng điều khiển cân bằng

Một dashboard hữu ích nên trả lời được ba câu hỏi: tự động hóa có phản hồi đủ nhanh không, tín hiệu có đáng tin cậy không và nó có giúp giảm rủi ro sản phẩm không?

Ví dụ một bảng theo dõi theo sprint hoặc theo tháng:

| Nhóm | Chỉ số | Kết quả kỳ này | Xu hướng | Cách diễn giải |
| --- | --- | --- | --- | --- |
| Tốc độ | p90 thời gian phản hồi PR | 14 phút | Giảm từ 19 phút | Phản hồi nhanh hơn; kiểm tra không bị loại bỏ |
| Độ tin cậy | Flaky rate | 1,8% | Tăng từ 0,9% | Cần điều tra test không ổn định |
| Chất lượng tín hiệu | Failure cần hành động / failure đã phân loại | 62% | Tăng từ 48% | Tín hiệu có ích hơn nhưng vẫn còn nhiều nhiễu |
| Phát hiện lỗi | Lỗi nghiêm trọng phát hiện trước phát hành | 4 | Tương đương kỳ trước | Xem cùng khối lượng thay đổi và phạm vi kiểm thử |
| Lỗi lọt | Lỗi nghiêm trọng được xác nhận sau phát hành | 1 | Giảm từ 3 | Phân tích nguyên nhân và mức phơi lộ |
| Bao phủ rủi ro | Rủi ro cao có bằng chứng tự động hiện hành | 82% | Tăng từ 74% | Còn khoảng trống ở hai luồng quan trọng |
| Bảo trì | Giờ điều tra/sửa test trong sprint | 26 giờ | Tăng từ 18 giờ | Xem phần tăng do thay đổi sản phẩm hay flaky |

Các con số trên là dữ liệu giả định để minh họa dashboard. Không nên diễn giải xu hướng chỉ từ hai kỳ nếu khối lượng thay đổi, số lần chạy hoặc cách phân loại khác nhau.

Dashboard nên cho phép truy ngược từ chỉ số tổng hợp đến test, build, failure, lỗi và rủi ro liên quan. Nếu không thể truy nguyên, nhóm khó xác định hành động cần thiết.

## 13. Ví dụ: đánh giá hiệu quả bộ kiểm thử thanh toán

Giả sử nhóm có bộ tự động hóa cho dịch vụ thanh toán gồm unit tests, integration tests và một số E2E. Sau ba tháng, nhóm thu thập dữ liệu:

- Thời gian p90 từ lúc mở pull request đến kết quả: giảm từ 22 phút xuống 15 phút.
- Flaky rate tăng từ 0,6% lên 2,4%.
- 12 lỗi sản phẩm được phát hiện trước phát hành; trong đó 3 lỗi mức cao liên quan đến retry và làm tròn tiền.
- 2 lỗi mức cao lọt tới production; một lỗi liên quan đến timeout của nhà cung cấp chưa được mô phỏng.
- 85% rủi ro ưu tiên cao có ít nhất một kiểm thử tự động gắn với bằng chứng hiện hành.
- 30 giờ trong sprint được dùng để điều tra và sửa test; 18 giờ trong số đó liên quan đến môi trường và tính không ổn định.

Không thể kết luận tự động hóa đã cải thiện toàn diện chỉ vì thời gian phản hồi giảm. Dữ liệu cho thấy tốc độ tốt hơn và bộ test đã phát hiện một số lỗi có ý nghĩa, nhưng độ ổn định giảm và vẫn có lỗi nghiêm trọng lọt tới production.

Nhóm có thể hành động theo thứ tự:

1. Phân loại 2 lỗi production để xác định thiếu tình huống timeout, khác biệt sandbox/production hay vấn đề quan sát.
2. Ưu tiên sửa các test flaky thuộc luồng thanh toán và ổn định môi trường.
3. Bổ sung kiểm thử tích hợp cho timeout, gửi lại, idempotency và đối soát.
4. Kiểm tra hai rủi ro ưu tiên cao chưa có bằng chứng tự động hiện hành.
5. Theo dõi lại p90, flaky rate, lỗi lọt và giờ bảo trì trong các sprint tiếp theo.

Đây là cách dùng số liệu để tìm nguyên nhân và điều chỉnh chiến lược. Mục tiêu không phải làm cho mọi chỉ số đều đẹp trong một kỳ, mà là tăng chất lượng phản hồi và giảm bất định về rủi ro.

## 14. Đặt mục tiêu và ngưỡng đo phù hợp

Mục tiêu nên được đặt từ đường cơ sở và nhu cầu thực tế. Tránh sao chép ngưỡng của dự án khác vì quy mô suite, kiến trúc, mức độ quan trọng và hạ tầng có thể khác nhau.

Một mục tiêu đo lường có thể gồm:

- Phạm vi và khoảng thời gian.
- Chỉ số và công thức tính.
- Đường cơ sở và nguồn dữ liệu.
- Mức mục tiêu hoặc ngưỡng cảnh báo.
- Chỉ số bảo vệ để tránh tối ưu sai hướng.
- Người chịu trách nhiệm và nhịp xem xét.

Ví dụ:

> Trong 8 tuần, giảm p90 thời gian phản hồi pull request từ 18 phút xuống 13 phút; giữ flaky rate dưới 1%; bảo đảm mọi rủi ro mức cao trong luồng thanh toán có ít nhất một kiểm thử tự động hoặc bằng chứng thay thế được phê duyệt; không tăng số lỗi nghiêm trọng lọt tới production.

Đây là ví dụ cách viết mục tiêu. Mức cụ thể cần dựa trên dữ liệu của nhóm và được thống nhất trước khi đo.

### Chọn cửa sổ thời gian

Thời gian phản hồi có thể đo theo từng commit hoặc pull request. Flaky rate cần đủ số lần chạy để tránh bị chi phối bởi vài quan sát. Lỗi lọt production thường cần cửa sổ theo dõi dài hơn và phải gắn với số lượng người dùng hoặc giao dịch. Chi phí bảo trì nên tổng hợp theo sprint hoặc tháng.

Không so sánh hai giai đoạn nếu định nghĩa chỉ số, phạm vi test, công cụ hoặc cách phân loại đã thay đổi mà không ghi chú. Khi thay đổi phương pháp đo, có thể cần thiết lập đường cơ sở mới.

## 15. Tránh các chỉ số phù phiếm và hành vi tối ưu sai

Một số chỉ số dễ thu thập nhưng có thể tạo động lực sai nếu dùng làm mục tiêu duy nhất.

- **Số lượng test case:** tăng số test không đồng nghĩa tăng bằng chứng; test có thể trùng lặp hoặc kiểm tra chi tiết không quan trọng.
- **Tỷ lệ code coverage:** cho biết mã nào được thực thi theo tiêu chí đo, không chứng minh assertion đúng hoặc rủi ro được bao phủ.
- **Tỷ lệ pass:** có thể cao vì test bỏ qua nhiều nhánh, bị skip hoặc không kiểm tra kết quả có ý nghĩa.
- **Số lỗi tìm được:** tăng có thể do sản phẩm nhiều lỗi hơn hoặc kiểm thử tốt hơn; cần xem mức độ và bối cảnh.
- **Thời gian pipeline:** giảm bằng cách bỏ kiểm thử quan trọng có thể làm tăng rủi ro.
- **Mutation score:** có thể bị tối ưu bằng assertion quá chặt hoặc thay đổi mã không có ý nghĩa nghiệp vụ.
- **Số test flaky:** phụ thuộc cách định nghĩa và phát hiện; cần xem cả tác động đến thời gian và niềm tin của nhóm.

Không nên thưởng hoặc đánh giá cá nhân chỉ dựa trên số lỗi tìm được, số test viết hoặc tỷ lệ pass. Những cách đo đó có thể khuyến khích tạo test kém giá trị, phân loại lỗi không nhất quán hoặc tránh ghi nhận thất bại.

## 16. Tổ chức vòng cải tiến liên tục

Đo lường chỉ có ích khi dẫn đến hành động. Có thể tổ chức vòng cải tiến theo các bước:

1. **Xem xét mục tiêu:** mục tiêu chất lượng và rủi ro nào cần được hỗ trợ trong kỳ này?
2. **Thu thập dữ liệu:** lấy kết quả pipeline, test, failure, defect, thay đổi và thời gian bảo trì.
3. **Kiểm tra chất lượng dữ liệu:** loại trừ trùng lặp, ghi rõ trường hợp chưa phân loại và xác nhận cửa sổ đo.
4. **Phân tích xu hướng:** xem chỉ số theo tầng, thành phần, mức độ lỗi và nhóm nguyên nhân.
5. **Chọn điểm nghẽn quan trọng:** ưu tiên vấn đề làm giảm độ tin cậy, chậm phản hồi hoặc bỏ sót rủi ro cao.
6. **Thực hiện thay đổi:** ổn định test, cải thiện môi trường, bổ sung trường hợp hoặc thay đổi pipeline.
7. **Đo lại:** so sánh với đường cơ sở trong điều kiện tương đương và ghi tác dụng phụ.
8. **Cập nhật chiến lược:** điều chỉnh mục tiêu, ma trận rủi ro và kế hoạch tự động hóa.

Ví dụ, nếu flaky rate tăng do các test dùng chung tài khoản và dữ liệu, giải pháp có thể là tạo dữ liệu riêng cho mỗi lần chạy, cô lập tài nguyên hoặc loại bỏ phụ thuộc thứ tự. Sau khi sửa, cần đo lại flaky rate và thời gian pipeline để kiểm tra cả độ ổn định lẫn tác động hiệu năng.

## 17. Phân công trách nhiệm với dữ liệu đo

Để chỉ số nhất quán, cần xác định ai sở hữu từng phần:

- **Nhóm phát triển:** duy trì test ở cấp thành phần, xử lý lỗi do thay đổi mã và cung cấp thông tin về phạm vi thay đổi.
- **Nhóm kiểm thử:** xác định mục tiêu bằng chứng, phân loại failure, liên kết test với yêu cầu/rủi ro và phân tích lỗi lọt.
- **Nhóm nền tảng/CI:** theo dõi runner, hàng đợi, môi trường, độ sẵn sàng và thời gian pipeline.
- **Chủ sở hữu sản phẩm hoặc rủi ro:** xác định ưu tiên, mức tác động và tiêu chí cần có bằng chứng.
- **Vận hành/SRE:** cung cấp dữ liệu production, sự cố, SLI/SLO và thông tin về lỗi thực tế.

Một failure không nên bị đẩy qua lại giữa các nhóm mà không có người điều phối. Cần có quy tắc phân loại, chủ sở hữu tạm thời và thời hạn điều tra.

## 18. Mẫu báo cáo hiệu quả tự động hóa

```text
PERIOD: 2027-Q2
SCOPE: Checkout service automated regression
BASELINE: Previous 8 weeks
FEEDBACK:
  - PR result p50 / p90:
  - Queue wait p90:
  - Suite execution p90:
SIGNAL QUALITY:
  - Flaky rate:
  - Rerun-to-pass rate:
  - Actionable failure ratio:
DEFECT DETECTION:
  - Defects found before release by severity:
  - Escaped defects by severity:
  - Main escape causes:
RISK EVIDENCE:
  - High risks with current automated evidence:
  - High risks without evidence:
MAINTENANCE:
  - Engineering hours spent on test maintenance:
  - Disabled/quarantined tests and age:
ACTIONS:
  - Owner / due date / expected evidence:
LIMITATIONS:
  - Changes in scope, definitions or data quality:
```

Mẫu này giúp nhóm ghi lại cả kết quả và giới hạn. Không phải dự án nào cũng cần mọi trường; hãy chọn các chỉ số có thể dẫn đến quyết định hoặc hành động cụ thể.

## 19. Checklist đánh giá hiệu quả tự động hóa

- [ ] Mục tiêu tự động hóa gắn với yêu cầu hoặc rủi ro sản phẩm.
- [ ] Có đường cơ sở và định nghĩa rõ cho từng chỉ số.
- [ ] Đo thời gian phản hồi theo phân vị và phân rã thời gian chờ/thực thi.
- [ ] Phân loại failure thành lỗi sản phẩm, test, dữ liệu, môi trường hoặc chưa xác định.
- [ ] Theo dõi flaky rate và rerun-to-pass mà vẫn giữ kết quả lần chạy đầu.
- [ ] Phân tích lỗi phát hiện trước phát hành và lỗi lọt production theo mức độ.
- [ ] Có bằng chứng về độ nhạy kiểm thử như mutation testing hoặc lỗi cấy có chủ đích khi phù hợp.
- [ ] Liên kết test với yêu cầu, hành trình và rủi ro; không chỉ đếm số test hoặc dòng mã.
- [ ] Theo dõi thời gian bảo trì, test bị tắt và chi phí môi trường.
- [ ] Kiểm tra phản hồi có được điều tra và dẫn đến hành động hay không.
- [ ] Chỉ số kết quả đi kèm chỉ số bảo vệ để tránh tối ưu sai mục tiêu.
- [ ] Xu hướng được đọc cùng thay đổi phạm vi, khối lượng thay đổi và chất lượng dữ liệu.

## 20. Những điểm cần ghi nhớ

- Hiệu quả tự động hóa thể hiện qua phản hồi nhanh, tín hiệu đáng tin cậy, khả năng phát hiện lỗi có ý nghĩa và chi phí duy trì hợp lý.
- Số lượng test, tỷ lệ pass hoặc code coverage không thể đại diện một mình cho chất lượng tự động hóa.
- Theo dõi tốc độ phản hồi theo phân vị và hiểu phần thời gian chờ, khởi tạo, thực thi và phân tích.
- Flaky rate và rerun-to-pass là tín hiệu cần điều tra; chạy lại thành công không tự động chứng minh lỗi là flaky.
- Phân tích lỗi được phát hiện trước phát hành cùng lỗi lọt production, mức độ nghiêm trọng và nguyên nhân.
- Mutation testing hoặc lỗi cấy có chủ đích có thể bổ sung bằng chứng về khả năng phát hiện, nhưng có giới hạn.
- Liên kết kiểm thử với yêu cầu và rủi ro để đánh giá phần nào có bằng chứng hiện hành và phần nào còn khoảng trống.
- Đo chi phí bảo trì, test bị vô hiệu hóa và mức sử dụng phản hồi để hiểu tổng chi phí của tự động hóa.
- Dùng bộ chỉ số cân bằng, có đường cơ sở và cửa sổ thời gian rõ; tránh tạo động lực tối ưu một con số.
- Xem xét dữ liệu định kỳ và chuyển kết quả thành hành động cải tiến có chủ sở hữu.

## Câu hỏi tự kiểm tra

1. Vì sao số lượng test case tự động không đủ để kết luận hiệu quả tự động hóa?
2. Hãy phân biệt thời gian chờ CI, thời gian thực thi và thời gian phản hồi mà người phát triển nhận được.
3. Flaky rate có thể được định nghĩa theo những đơn vị nào? Vì sao cần giữ kết quả của lần chạy đầu khi retry?
4. Tỷ lệ lỗi lọt production cần có những định nghĩa và giới hạn nào để so sánh giữa các phiên bản?
5. Mutation testing cung cấp bằng chứng gì và không thể chứng minh điều gì?
6. Hãy chọn một rủi ro ưu tiên cao và mô tả cách liên kết nó với kiểm thử tự động, kết quả và khoảng trống bằng chứng.
7. Nếu pipeline nhanh hơn nhưng flaky rate và lỗi lọt đều tăng, bạn sẽ điều tra và cân bằng các mục tiêu như thế nào?
8. Hãy lập một bảng điều khiển gồm ít nhất một chỉ số tốc độ, một chỉ số độ tin cậy, một chỉ số phát hiện lỗi và một chỉ số chi phí bảo trì.
