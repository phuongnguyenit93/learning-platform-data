# So sánh các phương án theo hiệu quả phát hiện lỗi và chi phí

Nhóm kiểm thử thường có nhiều cách để tìm lỗi: rà soát yêu cầu, phân tích tĩnh, kiểm thử đơn vị, kiểm thử tích hợp, kiểm thử đầu cuối, kiểm thử thăm dò, kiểm thử bảo mật hoặc kiểm thử hiệu năng. Mỗi phương án phát hiện những loại lỗi khác nhau, cần thời gian và nguồn lực khác nhau, đồng thời tạo ra mức độ tin cậy khác nhau cho quyết định phát hành.

Không có phương án nào tốt nhất trong mọi tình huống. Một bài kiểm thử chạy nhanh nhưng không chạm đến rủi ro quan trọng có thể tạo cảm giác an toàn mà không giúp ích nhiều. Một kịch bản đầu cuối gần với hành vi người dùng có thể phát hiện lỗi xuyên suốt hệ thống nhưng tốn công bảo trì và khó xác định nguyên nhân. Cách chọn phù hợp là so sánh hiệu quả phát hiện lỗi với tổng chi phí trong suốt vòng đời, rồi phối hợp các phương án để kiểm tra đúng rủi ro ở thời điểm thích hợp.

## 1. Xác định thế nào là hiệu quả phát hiện lỗi

Hiệu quả phát hiện lỗi mô tả khả năng một phương án tìm ra lỗi có ý nghĩa trong phạm vi và điều kiện đã xác định. Không nên chỉ đo bằng số lượng lỗi hoặc số bài kiểm thử đã chạy.

Một phương án có thể được đánh giá qua các khía cạnh:

- **Mức độ liên quan đến rủi ro:** có nhắm đến loại lỗi gây hậu quả đáng kể cho người dùng hoặc nghiệp vụ không?
- **Khả năng phát hiện:** khi lỗi thuộc phạm vi xuất hiện, phép kiểm tra có đủ nhạy để nhận ra sai lệch không?
- **Độ bao phủ:** các luồng, quy tắc, trạng thái, dữ liệu, thành phần và môi trường quan trọng có được kiểm tra không?
- **Thời điểm phát hiện:** lỗi được tìm thấy trước khi tốn nhiều công sức sửa hoặc trước khi đến tay người dùng?
- **Độ chính xác của kết quả:** kết quả thất bại có thực sự chỉ ra lỗi sản phẩm hay thường do môi trường, dữ liệu hoặc bài kiểm thử không ổn định?
- **Khả năng chẩn đoán:** khi phát hiện lỗi, nhóm có xác định được thành phần và nguyên nhân tương đối nhanh không?
- **Khả năng lặp lại:** phép kiểm tra có thể chạy lại trong điều kiện tương đương để xác minh sửa lỗi không?

Hiệu quả không đồng nghĩa với số lượng lỗi phát hiện. Một bài rà soát có thể tìm ra một lỗi phân quyền nghiêm trọng, trong khi hàng trăm lỗi hiển thị nhỏ được phát hiện qua kiểm thử giao diện. Số lượng lớn hơn không nhất thiết có giá trị cao hơn.

Cũng cần phân biệt lỗi được phát hiện với lỗi được ngăn chặn. Kiểm thử phát hiện sai lệch; một quy trình yêu cầu sửa lỗi trước khi merge hoặc phát hành mới ngăn lỗi đã biết đi tiếp. Nếu nhóm ghi nhận lỗi nhưng vẫn phát hành mà không có quyết định chấp nhận rủi ro, hiệu quả giảm thiểu thực tế sẽ thấp.

## 2. Xác định chi phí đầy đủ của một phương án

Chi phí không chỉ là thời gian chạy bài kiểm thử. Một phương án có thể chạy trong vài giây nhưng cần nhiều giờ thiết lập dữ liệu, sửa fixture, điều tra kết quả sai hoặc bảo trì khi giao diện thay đổi.

Hãy xem xét toàn bộ chi phí:

| Thành phần chi phí | Nội dung |
|---|---|
| Thiết kế | Thời gian hiểu yêu cầu, xác định rủi ro, viết kịch bản và tiêu chí kết quả |
| Chuẩn bị | Thiết lập công cụ, môi trường, tài khoản, dữ liệu và phụ thuộc |
| Thực thi | Thời gian chạy tự động hoặc thời gian người kiểm thử thao tác |
| Bảo trì | Cập nhật bài kiểm thử khi mã nguồn, giao diện, API hoặc dữ liệu thay đổi |
| Phân tích và xử lý | Đọc kết quả, phân loại lỗi, điều tra nguyên nhân và xác minh sửa lỗi |
| Hạ tầng | Máy chạy, thiết bị, dịch vụ đám mây, giấy phép, lưu trữ và giám sát |
| Chi phí do kết quả không tin cậy | Điều tra false positive, chạy lại, xử lý flaky test hoặc bỏ sót lỗi |
| Chi phí cơ hội | Thời gian và năng lực không thể dùng cho hoạt động khác |

Một cách nhìn hữu ích là tổng chi phí vòng đời:

\[
C_{\text{total}} =
C_{\text{design}} + C_{\text{setup}} + C_{\text{run}} +
C_{\text{maintenance}} + C_{\text{triage}} + C_{\text{infrastructure}}
\]

Đây là khung phân tích, không phải công thức kế toán bắt buộc. Có thể bổ sung chi phí đào tạo, phối hợp nhóm hoặc vận hành tùy bối cảnh.

Khi so sánh hai phương án, dùng cùng khoảng thời gian và cùng phạm vi. So sánh chi phí chạy một lần của kiểm thử tự động với chi phí thiết kế và thực thi của kiểm thử thủ công sẽ dẫn đến kết luận sai. Hãy tính cả chi phí ban đầu và số lần dự kiến sử dụng.

## 3. So sánh các lớp kiểm thử theo lỗi chúng phát hiện

Mỗi lớp kiểm thử quan sát hệ thống ở một mức khác nhau. Lớp gần mã nguồn thường nhanh và dễ khoanh vùng; lớp gần hành vi người dùng thường kiểm tra được nhiều thành phần cùng lúc nhưng khó chẩn đoán hơn.

| Phương án | Lỗi thường phát hiện tốt | Tốc độ và chi phí tương đối | Giới hạn chính |
|---|---|---|---|
| Rà soát yêu cầu và thiết kế | Mơ hồ, mâu thuẫn, thiếu trường hợp, sai giả định nghiệp vụ | Chi phí thấp đến trung bình; phát hiện rất sớm | Phụ thuộc kiến thức người rà soát; không chứng minh hành vi thực thi |
| Phân tích tĩnh và kiểm tra cấu hình | Lỗi cú pháp, mẫu mã nguy hiểm, dependency hoặc cấu hình sai có thể nhận diện bằng quy tắc | Nhanh, dễ tích hợp vào CI | Có thể có cảnh báo sai; không quan sát được mọi hành vi runtime |
| Kiểm thử đơn vị | Sai logic, điều kiện biên, phép tính, chuyển trạng thái trong phạm vi nhỏ | Thường rất nhanh, chi phí chạy thấp | Không chứng minh tích hợp, cấu hình hay hành vi toàn hệ thống |
| Kiểm thử thành phần | Lỗi trong module hoặc dịch vụ với phụ thuộc được kiểm soát | Nhanh đến trung bình; chẩn đoán khá rõ | Mock hoặc môi trường cô lập có thể che lỗi tương tác thật |
| Kiểm thử hợp đồng | Sai schema, giao thức, giả định không tương thích giữa các bên | Trung bình; tập trung vào ranh giới | Không chứng minh toàn bộ quy trình nghiệp vụ xuyên hệ thống |
| Kiểm thử tích hợp | Lỗi kết nối, giao dịch, dữ liệu, xác thực và phối hợp dịch vụ | Trung bình; cần môi trường và dữ liệu phù hợp | Khó cô lập nguyên nhân hơn kiểm thử đơn vị |
| Kiểm thử đầu cuối | Lỗi trong hành trình người dùng qua nhiều thành phần | Thường chậm, chi phí bảo trì cao | Dễ nhạy cảm với môi trường và giao diện; lỗi khó khoanh vùng |
| Kiểm thử thăm dò và đánh giá sử dụng | Luồng bất thường, vấn đề trải nghiệm, giả định chưa được mô hình hóa | Cần thời gian chuyên môn của con người | Khó lặp lại hoàn toàn và phụ thuộc kỹ năng người kiểm thử |
| Kiểm thử phi chức năng | Hiệu năng, bảo mật, độ tin cậy, khả năng tiếp cận và phục hồi | Chi phí thay đổi theo công cụ, tải và chuyên môn | Cần mục tiêu đo rõ; kết quả có thể không đại diện production |

Bảng này mô tả xu hướng thường gặp, không phải thứ hạng cố định. Một bài kiểm thử đơn vị phức tạp có thể tốn công hơn một kiểm thử tích hợp đơn giản; một bài kiểm thử đầu cuối được thiết kế tốt có thể rất ổn định. Hãy đánh giá theo hệ thống và rủi ro cụ thể.

## 4. So sánh kiểm thử thủ công và tự động hóa

Thủ công và tự động hóa là cách tổ chức thực thi, không phải hai lớp kiểm thử đối lập. Một luồng có thể được kiểm tra tự động ở phần hồi quy ổn định và được khám phá thủ công khi nhóm muốn tìm hành vi bất ngờ.

| Tiêu chí | Thủ công | Tự động |
|---|---|---|
| Phản hồi ban đầu | Có thể bắt đầu nhanh nếu không cần thiết lập nhiều | Cần thời gian xây dựng và cấu hình ban đầu |
| Lặp lại | Tốn thời gian khi phải chạy thường xuyên | Phù hợp với kiểm tra lặp lại có kết quả xác định |
| Khám phá | Linh hoạt, dễ điều chỉnh theo quan sát | Cần kịch bản hoặc cơ chế sinh dữ liệu được thiết kế trước |
| Quy mô | Bị giới hạn bởi thời gian và số người | Có thể chạy song song và mở rộng theo hạ tầng |
| Độ nhất quán | Có thể khác giữa người và lần chạy | Có thể nhất quán nếu dữ liệu, môi trường và bài kiểm thử ổn định |
| Bảo trì | Tốn công thực hiện lại và cập nhật hướng dẫn | Tốn công sửa mã kiểm thử, fixture và môi trường |
| Khả năng đánh giá cảm nhận | Tốt với trải nghiệm, nội dung và khả năng sử dụng | Có thể hỗ trợ kiểm tra quy tắc, truy cập và một số tiêu chí máy đo được |
| Chi phí dài hạn | Cao nếu phải lặp lại thường xuyên | Có thể giảm chi phí lặp lại, nhưng cần duy trì chất lượng tự động hóa |

Nên cân nhắc tự động hóa khi phép kiểm tra:

- Được chạy thường xuyên, chẳng hạn mỗi pull request hoặc mỗi bản phát hành.
- Có kết quả mong đợi rõ và có thể xác định bằng máy.
- Liên quan đến rủi ro đáng kể hoặc luồng nghiệp vụ quan trọng.
- Cần chạy trên nhiều dữ liệu hoặc môi trường.
- Có thể duy trì với chi phí hợp lý khi sản phẩm thay đổi.

Kiểm thử thủ công vẫn phù hợp khi cần khám phá, đánh giá trải nghiệm, quan sát tính dễ hiểu, kiểm tra nội dung hoặc điều tra lỗi chưa rõ nguyên nhân. Có thể tự động hóa một phần việc chuẩn bị và thu thập bằng chứng để người kiểm thử dành thời gian cho phán đoán chuyên môn.

## 5. Đo hiệu quả bằng nhiều chỉ số, không dùng một con số duy nhất

Một số chỉ số có thể giúp so sánh phương án:

### 5.1. Lỗi được phát hiện theo mức độ rủi ro

Ghi nhận lỗi theo loại, mức độ nghiêm trọng, luồng nghiệp vụ và phương án đã phát hiện. Có thể dùng trọng số ưu tiên để tránh coi mọi lỗi có giá trị như nhau.

Ví dụ minh họa:

| Phương án | Lỗi nghiêm trọng | Lỗi trung bình | Lỗi nhỏ |
|---|---:|---:|---:|
| Rà soát thiết kế | 2 | 1 | 0 |
| Kiểm thử đơn vị | 1 | 5 | 3 |
| Kiểm thử tích hợp | 3 | 4 | 2 |
| Kiểm thử đầu cuối | 1 | 2 | 4 |

Bảng này chỉ cho thấy loại phát hiện trong một đợt giả định. Không thể kết luận phương án rà soát thiết kế tốt nhất chỉ vì tìm được hai lỗi nghiêm trọng; cần xem phạm vi đã kiểm tra, thời gian thực hiện, mức độ trùng lặp và những lỗi chưa được phát hiện.

### 5.2. Hiệu quả loại bỏ lỗi trước phát hành

Có thể tham khảo tỷ lệ lỗi được phát hiện trước phát hành trong một nhóm lỗi đã được theo dõi:

\[
DRE = \frac{N_{\text{pre-release}}}
{N_{\text{pre-release}} + N_{\text{post-release}}} \times 100\%
\]

Trong đó \(N_{\text{pre-release}}\) là số lỗi được phát hiện trước phát hành và \(N_{\text{post-release}}\) là số lỗi cùng phạm vi được phát hiện sau phát hành.

Chỉ số này có thể gây hiểu lầm nếu nhóm không thống nhất cách đếm lỗi, thời gian quan sát, mức độ nghiêm trọng hoặc cách gộp lỗi trùng. Một sản phẩm ít người dùng có thể có ít lỗi production được báo cáo dù vẫn tồn tại lỗi. Hãy dùng nó như tín hiệu xu hướng, không phải bằng chứng độc lập về chất lượng.

### 5.3. Chi phí cho một phát hiện hữu ích

Có thể tính chi phí thực tế trên mỗi lỗi hữu ích được phát hiện:

\[
C_{\text{per finding}} =
\frac{C_{\text{total}}}{N_{\text{useful findings}}}
\]

Chỉ số này cần định nghĩa “phát hiện hữu ích”. Một cảnh báo trùng lặp, false positive hoặc lỗi đã được một phương án khác tìm ra có thể không nên tính như một phát hiện độc lập. Với rủi ro nghiêm trọng, một phát hiện duy nhất có thể có giá trị lớn hơn nhiều phát hiện nhỏ.

### 5.4. Thời gian phản hồi và chẩn đoán

Theo dõi thời gian từ khi thay đổi được tạo đến khi nhận kết quả, thời gian từ lúc phát hiện đến khi xác định nguyên nhân và thời gian xác minh sửa lỗi. Phát hiện sớm thường giúp giảm chi phí sửa vì ít thành phần và thay đổi liên quan hơn.

### 5.5. Độ ổn định của bài kiểm thử

Theo dõi tỷ lệ flaky test, số lần chạy lại, false positive và thời gian bảo trì. Một bộ kiểm thử có độ bao phủ lớn nhưng thường xuyên thất bại không ổn định có thể khiến nhóm bỏ qua cảnh báo thật.

## 6. Ước lượng giá trị phát hiện và chi phí theo rủi ro

Để so sánh các phương án, có thể dùng một bảng chấm điểm định tính. Trước hết, xác định rủi ro cần kiểm tra và trọng số tác động. Sau đó đánh giá từng phương án theo khả năng phát hiện, độ bao phủ, thời điểm phản hồi và chi phí vòng đời.

Ví dụ thang điểm:

- 1: thấp hoặc hạn chế.
- 2: trung bình thấp.
- 3: trung bình.
- 4: cao.
- 5: rất cao.

Một ma trận đánh giá giả định:

| Phương án | Phát hiện lỗi logic | Phát hiện lỗi tích hợp | Tốc độ phản hồi | Chi phí vòng đời |
|---|---:|---:|---:|---|
| Rà soát thiết kế | 3 | 2 | 5 | Thấp đến trung bình |
| Unit test | 5 | 1 | 5 | Thấp đến trung bình |
| Integration test | 3 | 5 | 3 | Trung bình |
| End-to-end test | 3 | 4 | 2 | Cao |
| Kiểm thử thăm dò | 4 | 4 | 3 | Phụ thuộc nhân lực |

Điểm số trong bảng là ví dụ để minh họa cách thảo luận, không phải số liệu đo thực tế. Không nên cộng các điểm thành một kết quả duy nhất nếu chưa xác định trọng số theo mục tiêu. Nếu rủi ro chính là lỗi tính phí, khả năng phát hiện logic cần trọng số cao. Nếu rủi ro là giao dịch không nhất quán giữa hai dịch vụ, kiểm thử tích hợp và hợp đồng có thể quan trọng hơn.

Một cách diễn giải giá trị là:

\[
V \approx \frac{\text{Rủi ro được giảm hoặc phát hiện có ích}}
{\text{Chi phí vòng đời}}
\]

Không phải lúc nào cũng có thể lượng hóa chính xác tử số. Có thể dùng phân loại cao/trung bình/thấp, bằng chứng lịch sử và đánh giá của chuyên gia. Mục tiêu là làm rõ lý do chọn phương án, không tạo ra một điểm số có vẻ chính xác nhưng dựa trên giả định yếu.

## 7. Chọn phương án theo loại rủi ro

Dùng loại lỗi và hậu quả để quyết định lớp kiểm thử phù hợp:

| Loại rủi ro | Phương án thường có giá trị cao | Bằng chứng cần tìm |
|---|---|---|
| Quy tắc tính toán sai | Rà soát yêu cầu, unit test, kiểm thử giá trị biên và property-based test khi phù hợp | Kết quả đúng với biên, trường hợp bất thường và quy tắc đã xác nhận |
| API giữa dịch vụ không tương thích | Contract test, integration test | Schema, trạng thái, xác thực và xử lý lỗi nhất quán |
| Quyền truy cập sai | Rà soát thiết kế bảo mật, kiểm thử API và kiểm thử phân quyền | Tài khoản không đủ quyền bị từ chối ở phía máy chủ |
| Hành trình người dùng bị gián đoạn | End-to-end test trọng yếu, kiểm thử thăm dò | Người dùng hoàn thành luồng và trạng thái cuối cùng chính xác |
| Hệ thống chậm dưới tải | Kiểm thử hiệu năng, profiling và kiểm thử tải theo mục tiêu | Độ trễ, thông lượng, tài nguyên và tỷ lệ lỗi dưới tải |
| Dịch vụ phụ mất kết nối | Kiểm thử chịu lỗi, fault injection và kiểm thử phục hồi | Timeout, retry, circuit breaker và phục hồi theo thiết kế |
| Trải nghiệm khó hiểu hoặc khó thao tác | Kiểm thử khả năng sử dụng và đánh giá khả năng tiếp cận | Người dùng mục tiêu hoàn thành nhiệm vụ và hiểu phản hồi |
| Lỗi tương thích môi trường | Ma trận trình duyệt/thiết bị, kiểm thử khói và hồi quy đại diện | Kết quả gắn với phiên bản và cấu hình thực tế |

Một rủi ro lớn thường cần nhiều phương án. Ví dụ, kiểm thử API không thể thay thế kiểm thử hành trình thanh toán; kiểm thử đầu cuối cũng không thể thay thế kiểm thử phân quyền ở mọi endpoint.

## 8. Ví dụ: so sánh phương án kiểm thử cho luồng thanh toán

Giả sử một cửa hàng trực tuyến thay đổi cách tính phí vận chuyển và tích hợp với nhà cung cấp thanh toán mới. Nhóm có ba rủi ro chính:

1. Phí vận chuyển được tính sai ở ranh giới khối lượng hoặc khu vực.
2. API thanh toán thay đổi trạng thái hoặc schema làm giao dịch không hoàn tất.
3. Người dùng gửi lại yêu cầu sau timeout và bị thu tiền hai lần.

Có thể so sánh phương án như sau:

| Phương án | Lỗi có thể phát hiện | Chi phí và giới hạn | Quyết định sử dụng |
|---|---|---|---|
| Rà soát quy tắc tính phí | Thiếu điều kiện khu vực, quy tắc biên chưa rõ | Rất sớm, chi phí thấp; phụ thuộc người hiểu nghiệp vụ | Dùng trước khi triển khai |
| Unit test cho công thức | Sai phép tính, giá trị biên và nhánh điều kiện | Chạy nhanh, dễ khoanh vùng; không kiểm tra nhà cung cấp | Tự động chạy trên mỗi thay đổi |
| Contract test với nhà cung cấp | Schema hoặc trạng thái phản hồi không tương thích | Cần hợp đồng API và dữ liệu đại diện | Chạy khi thay đổi tích hợp hoặc API |
| Integration test | Lỗi lưu trạng thái, callback, transaction và retry | Cần môi trường phụ thuộc; chi phí trung bình | Chạy trong pipeline trước phát hành |
| End-to-end test | Hành trình từ giỏ hàng đến kết quả thanh toán | Chậm và cần dữ liệu/môi trường ổn định | Giữ một số luồng trọng yếu |
| Kiểm thử thăm dò | Hành vi bất thường khi người dùng quay lại, tải lại trang hoặc đổi phương thức thanh toán | Cần thời gian người kiểm thử; khó bao phủ mọi biến thể | Thực hiện khi thay đổi lớn và trước phát hành |

Một cách phân bổ hợp lý là rà soát quy tắc và unit test cho công thức tính phí, contract test và integration test cho nhà cung cấp, sau đó giữ một số kịch bản end-to-end để xác minh hành trình hoàn chỉnh. Kiểm thử thăm dò bổ sung các tình huống chưa được mô hình hóa, đặc biệt là thao tác lặp và chuyển đổi giữa các bước.

Nhóm không nên tự động hóa toàn bộ tổ hợp giao diện ngay từ đầu nếu giao diện còn thay đổi liên tục. Trước tiên, hãy ổn định các quy tắc nghiệp vụ và API; sau đó tự động hóa các luồng đầu cuối có giá trị lặp lại cao. Cách phân bổ này giúp giảm chi phí bảo trì và vẫn kiểm tra được rủi ro trọng yếu.

## 9. Tối ưu chi phí mà không làm mất bằng chứng quan trọng

Khi ngân sách hoặc thời gian hạn chế, có thể tối ưu theo các hướng:

- **Ưu tiên theo rủi ro:** dành mức kiểm tra cao hơn cho chức năng có tác động lớn hoặc lịch sử lỗi nhiều.
- **Phát hiện sớm:** rà soát yêu cầu và thiết kế trước khi triển khai, chạy kiểm tra nhanh ở mỗi thay đổi.
- **Đặt kiểm thử đúng lớp:** kiểm tra logic ở unit test, hợp đồng ở contract test, tương tác ở integration test và hành trình ở end-to-end.
- **Tái sử dụng dữ liệu và fixture:** chuẩn hóa dữ liệu kiểm thử có thể tạo lại, tránh phụ thuộc trạng thái từ lần chạy trước.
- **Chạy song song có kiểm soát:** giảm thời gian chờ nhưng bảo đảm tài nguyên, dữ liệu và môi trường không tranh chấp.
- **Chọn ma trận đại diện:** dùng pairwise hoặc phân tầng môi trường khi toàn bộ tổ hợp quá lớn, đồng thời bổ sung trường hợp rủi ro cao.
- **Giảm flaky test:** điều tra nguyên nhân thay vì chạy lại vô hạn hoặc bỏ qua lỗi.
- **Loại bỏ bài kiểm thử ít giá trị:** đánh giá bài trùng lặp, không còn liên quan hoặc có chi phí bảo trì cao so với rủi ro được kiểm tra.
- **Theo dõi chi phí sau thay đổi:** kiểm tra xem một tính năng mới có làm bộ kiểm thử chậm, khó bảo trì hoặc kém tin cậy hơn không.

Không nên tối ưu bằng cách loại bỏ kiểm thử chỉ vì nó chậm. Nếu bài kiểm thử bảo vệ một giao dịch trọng yếu, hãy xem xét chạy theo lịch, theo nhóm thay đổi hoặc trước phát hành, và giữ một kiểm tra nhanh hơn ở pipeline thường ngày. Quyết định cần duy trì bằng chứng phù hợp với mức rủi ro.

## 10. Xem xét chi phí cơ hội và hậu quả của lỗi lọt

Một phương án kiểm thử có thể đắt khi thực thi nhưng vẫn kinh tế nếu ngăn được hậu quả lớn. Ngược lại, một phép thử rẻ có thể không đáng duy trì nếu không tìm được lỗi có ý nghĩa và không tạo bằng chứng cần thiết.

Khi đánh giá, hãy xem cả chi phí của lỗi lọt:

- Thời gian điều tra và sửa lỗi sau phát hành.
- Hỗ trợ khách hàng, hoàn tiền hoặc xử lý dữ liệu sai.
- Gián đoạn hoạt động và mất doanh thu.
- Nghĩa vụ thông báo, kiểm toán hoặc khắc phục theo hợp đồng.
- Ảnh hưởng đến niềm tin và uy tín.
- Chi phí phục hồi, đối soát và triển khai bản vá khẩn cấp.

Không cần cố gắng gán một giá tiền chính xác cho mọi hậu quả. Có thể phân loại tác động và dùng nó để xác định mức kiểm thử tối thiểu. Với rủi ro an toàn, bảo mật hoặc mất dữ liệu, mức ưu tiên có thể cao dù xác suất xảy ra thấp và chi phí kiểm thử lớn.

## 11. Quy trình ra quyết định và rà soát định kỳ

Để tránh chọn phương án theo sở thích cá nhân, hãy ghi lại quyết định theo một quy trình thống nhất:

1. **Xác định rủi ro:** mô tả lỗi có thể xảy ra, nguyên nhân, hậu quả và người dùng bị ảnh hưởng.
2. **Xác định bằng chứng cần có:** nhóm cần biết điều gì để kết luận kiểm soát hoặc hành vi đạt yêu cầu?
3. **Liệt kê phương án:** xem xét rà soát, phân tích tĩnh, các lớp kiểm thử, kiểm thử thủ công và kiểm soát vận hành.
4. **Ước lượng hiệu quả:** loại lỗi có thể phát hiện, phạm vi, thời điểm, độ tin cậy và khả năng chẩn đoán.
5. **Ước lượng chi phí vòng đời:** thiết kế, chuẩn bị, chạy, bảo trì, phân tích, hạ tầng và chi phí lỗi lọt.
6. **Chọn tổ hợp:** dùng nhiều phương án bổ sung nhau cho rủi ro quan trọng.
7. **Ghi giới hạn:** nêu phần chưa kiểm tra, giả định, môi trường không đại diện và lỗi có thể bị bỏ sót.
8. **Theo dõi kết quả:** so sánh lỗi phát hiện, lỗi lọt, thời gian phản hồi và chi phí thực tế sau các chu kỳ.
9. **Điều chỉnh:** tăng, giảm hoặc thay phương án khi rủi ro, sản phẩm hoặc chi phí thay đổi.

Sơ đồ sau thể hiện quá trình lựa chọn:

~~~mermaid
flowchart TD
    A["Xác định rủi ro và hậu quả"] --> B["Xác định bằng chứng cần có"]
    B --> C["Liệt kê phương án kiểm thử"]
    C --> D["Ước lượng hiệu quả phát hiện"]
    C --> E["Ước lượng chi phí vòng đời"]
    D --> F["So sánh theo mức rủi ro"]
    E --> F
    F --> G["Chọn tổ hợp phương án"]
    G --> H["Thực hiện và ghi bằng chứng"]
    H --> I["Đo lỗi phát hiện, lỗi lọt và chi phí"]
    I --> J{"Còn khoảng trống quan trọng?"}
    J -->|Có| C
    J -->|Không| K["Duy trì và rà soát khi có thay đổi"]
~~~

## 12. Checklist đánh giá phương án

Trước khi chọn hoặc loại bỏ một phương án kiểm thử, hãy tự hỏi:

- Phương án này nhắm đến loại lỗi và rủi ro nào?
- Nó có phát hiện được lỗi trước thời điểm chi phí sửa tăng cao không?
- Phạm vi dữ liệu, trạng thái, môi trường và thành phần đã đủ chưa?
- Kết quả có đáng tin, lặp lại được và dễ chẩn đoán không?
- Chi phí đã tính cả thiết kế, chuẩn bị, chạy, bảo trì, phân tích và hạ tầng chưa?
- Phương án có trùng lặp với kiểm tra khác hay bổ sung một loại bằng chứng mới?
- Có thể chuyển kiểm tra sang lớp nhanh và ổn định hơn mà vẫn giữ mục tiêu không?
- Nếu bỏ phương án, rủi ro hoặc khoảng trống bằng chứng nào sẽ tăng?
- Có cách kiểm soát vận hành hoặc thiết kế bổ sung khi không thể kiểm thử đầy đủ không?
- Có dữ liệu lịch sử để đánh giá hiệu quả và chi phí sau vài chu kỳ không?
- Ai chịu trách nhiệm duy trì phương án và rà soát giá trị của nó?

So sánh hiệu quả phát hiện lỗi với chi phí giúp nhóm sử dụng nguồn lực có chủ đích. Phương án tốt là phương án tạo ra bằng chứng phù hợp với rủi ro, phát hiện lỗi ở thời điểm có ích và có thể duy trì ổn định. Khi kết hợp các lớp kiểm thử bổ sung cho nhau, nhóm có thể giảm chi phí lặp lại mà vẫn giữ được độ tin cậy cần thiết cho quyết định phát hành.

