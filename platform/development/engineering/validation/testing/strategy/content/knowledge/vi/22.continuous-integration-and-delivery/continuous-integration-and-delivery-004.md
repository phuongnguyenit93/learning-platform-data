# Thiết kế ma trận môi trường và giới hạn số tổ hợp

Một sản phẩm thường phải hoạt động trên nhiều môi trường: hệ điều hành, phiên bản runtime, trình duyệt, cơ sở dữ liệu, cấu hình, thiết bị, vùng triển khai và dịch vụ phụ thuộc khác nhau. Nếu kiểm thử mọi tổ hợp có thể có, số lượng job sẽ tăng rất nhanh, kéo dài pipeline và làm tăng chi phí hạ tầng. Nếu chỉ kiểm tra một môi trường duy nhất, nhóm có thể bỏ sót lỗi tương thích chỉ xuất hiện ở một phiên bản hoặc một cấu hình cụ thể.

Ma trận môi trường (environment matrix) giúp mô tả có hệ thống các môi trường mà sản phẩm cần hỗ trợ và những tổ hợp được chọn để kiểm thử. Mục tiêu của thiết kế ma trận là tạo đủ bằng chứng về khả năng tương thích và rủi ro trong giới hạn thời gian, tài nguyên và chi phí. Nhóm cần lựa chọn các chiều môi trường có ý nghĩa, loại bỏ tổ hợp không hợp lệ, ưu tiên tổ hợp rủi ro cao và dùng kỹ thuật giảm tổ hợp như pairwise hoặc t-way testing khi phù hợp.

Trong chiến lược CI/CD, ma trận tốt làm rõ test nào chạy ở đâu, khi nào chạy, vì sao tổ hợp được chọn và khoảng trống nào còn lại. Ma trận không phải danh sách mọi cấu hình có thể tưởng tượng; nó là một mô hình kiểm thử có chủ đích, được cập nhật khi sản phẩm, khách hàng và nền tảng thay đổi.

## 1. Ma trận môi trường là gì?

Ma trận môi trường là cách biểu diễn các chiều cấu hình có thể ảnh hưởng đến hành vi của phần mềm và những giá trị được chọn cho từng chiều. Một ứng dụng web có thể có các chiều như:

- Hệ điều hành của máy khách hoặc runner.
- Trình duyệt và phiên bản trình duyệt.
- Thiết bị, kích thước màn hình hoặc phương thức nhập liệu.
- Phiên bản runtime, framework hoặc thư viện nền tảng.
- Hệ quản trị cơ sở dữ liệu và phiên bản.
- Cấu hình triển khai, feature flag và biến môi trường.
- Vùng địa lý, locale, múi giờ và ngôn ngữ.
- Loại mạng, proxy, TLS hoặc điều kiện kết nối.
- Dịch vụ phụ thuộc và phiên bản API của chúng.

Một tổ hợp (combination) là một lựa chọn cụ thể từ nhiều chiều. Ví dụ: Windows 11 + Chrome phiên bản hiện hành + PostgreSQL 16 + locale vi-VN. Tổ hợp này có thể được dùng để chạy một nhóm test trình duyệt và API.

Cần phân biệt ma trận môi trường với ma trận test case. Ma trận môi trường mô tả cấu hình nơi test chạy; ma trận test case mô tả hành vi, yêu cầu hoặc rủi ro được kiểm tra. Một test case có thể chạy trên nhiều môi trường, nhưng không phải test nào cũng cần chạy trên tất cả tổ hợp.

### Mục đích của ma trận

Ma trận giúp nhóm trả lời:

1. Sản phẩm cam kết hỗ trợ những môi trường nào?
2. Những chiều nào có thể làm thay đổi kết quả hoặc trải nghiệm?
3. Tổ hợp nào cần được kiểm tra ở mỗi giai đoạn CI/CD?
4. Những tổ hợp nào không hợp lệ hoặc không có ý nghĩa?
5. Rủi ro nào được bao phủ bởi tập tổ hợp đã chọn?
6. Tổ hợp nào còn chưa có bằng chứng và ai chấp nhận rủi ro đó?

Nếu không có câu trả lời rõ ràng, ma trận dễ trở thành một danh sách phiên bản được thêm vào tùy tiện, khó duy trì và không phản ánh chính sách hỗ trợ thực tế.

## 2. Phân biệt môi trường được hỗ trợ và môi trường được kiểm thử

Một sản phẩm có thể hỗ trợ nhiều cấu hình hơn số cấu hình được chạy trong mọi pipeline. Chính sách hỗ trợ và kế hoạch kiểm thử có quan hệ với nhau nhưng không giống nhau.

- **Môi trường được hỗ trợ:** môi trường mà tổ chức cam kết sản phẩm hoạt động theo mức dịch vụ hoặc chính sách đã công bố.
- **Môi trường được kiểm thử:** môi trường đã được chọn để chạy một hoặc nhiều kiểm tra nhằm thu thập bằng chứng.
- **Môi trường tham chiếu:** cấu hình đại diện được dùng làm chuẩn cho phát triển, kiểm thử thường xuyên hoặc điều tra lỗi.
- **Môi trường thử nghiệm:** cấu hình được dùng để khảo sát khả năng tương thích hoặc đánh giá một phiên bản mới, chưa nhất thiết nằm trong cam kết hỗ trợ.

Không nên suy luận rằng môi trường không xuất hiện trong ma trận CI là môi trường không được hỗ trợ. Nếu sản phẩm cam kết hỗ trợ một phiên bản, nhóm cần có kế hoạch bằng chứng phù hợp: có thể chạy đầy đủ theo lịch, kiểm tra smoke trước phát hành hoặc dùng thiết bị/phòng lab chuyên biệt.

Ngược lại, không phải mọi môi trường từng được khách hàng sử dụng đều phải trở thành môi trường được hỗ trợ. Chủ sở hữu sản phẩm cần xác định phạm vi hỗ trợ, thời hạn duy trì và quy trình thông báo khi loại bỏ phiên bản cũ.

### Ví dụ về chính sách hỗ trợ

Một ứng dụng web có thể công bố hỗ trợ hai phiên bản chính của trình duyệt trên desktop và một tập phiên bản hệ điều hành di động. Nhóm có thể:

- Chạy test cốt lõi trên trình duyệt chuẩn trong mỗi pull request.
- Chạy smoke test trên các trình duyệt còn lại sau khi hợp nhất.
- Chạy hồi quy rộng trên toàn bộ ma trận hỗ trợ theo lịch hoặc trước phát hành.
- Kiểm tra phiên bản trình duyệt mới sắp được hỗ trợ trong một job thử nghiệm riêng.

Chính sách này cần được ghi rõ để người dùng, nhóm phát triển và người vận hành hiểu mức bằng chứng có sẵn.

## 3. Xác định các chiều môi trường có ý nghĩa

Không phải mọi thuộc tính cấu hình đều cần trở thành một chiều độc lập trong ma trận. Hãy chọn những chiều có thể ảnh hưởng đến hành vi, tương thích, hiệu năng, bảo mật hoặc trải nghiệm.

### Bắt đầu từ kiến trúc và cách sử dụng

Xem xét:

- Nền tảng mà người dùng thực sự sử dụng.
- Các runtime và dịch vụ mà hệ thống triển khai.
- Những phiên bản phụ thuộc được hỗ trợ.
- Các khác biệt về API, driver, giao thức hoặc định dạng dữ liệu.
- Những tính năng phụ thuộc vào hệ điều hành hoặc trình duyệt.
- Cấu hình khách hàng có thể thay đổi.
- Lịch sử lỗi và sự cố theo môi trường.

Ví dụ, ứng dụng xử lý ngày giờ có thể chịu ảnh hưởng bởi locale, múi giờ và quy tắc DST. Ứng dụng upload tệp có thể chịu ảnh hưởng bởi trình duyệt, kích thước tệp, hệ điều hành và giới hạn proxy. Nếu các yếu tố này đã gây lỗi, chúng cần được cân nhắc trong ma trận.

### Nhóm các giá trị tương đương

Một chiều có thể có nhiều phiên bản nhưng một số phiên bản có cùng hành vi kỹ thuật liên quan. Có thể nhóm chúng theo họ runtime, engine hoặc mức tương thích nếu có bằng chứng rằng nhóm đó đại diện hợp lý.

Không nên gộp chỉ vì các phiên bản có số gần nhau. Một bản cập nhật có thể thay đổi TLS, parser, API hoặc hành vi mặc định. Hãy dùng tài liệu nhà cung cấp, kiểm tra tương thích và lịch sử lỗi để quyết định nhóm.

### Chọn giá trị đại diện

Với mỗi chiều, cân nhắc các giá trị:

- Phổ biến nhất trong người dùng hoặc production.
- Phiên bản thấp nhất còn được hỗ trợ.
- Phiên bản mới nhất được hỗ trợ.
- Phiên bản vừa có thay đổi quan trọng.
- Phiên bản có lịch sử lỗi hoặc rủi ro cao.
- Cấu hình đặc biệt được khách hàng sử dụng.

Ví dụ, nếu hỗ trợ PostgreSQL 14 đến 16, nhóm có thể chọn phiên bản thấp nhất, phiên bản mới nhất và một phiên bản trung gian làm đại diện. Việc có chạy tất cả phiên bản trong mọi pull request hay không là quyết định riêng về lịch chạy và rủi ro.

## 4. Tạo mô hình chiều và giá trị

Trước khi tạo tổ hợp, hãy lập danh sách chiều, giá trị và lý do lựa chọn. Ví dụ cho một dịch vụ web:

| Chiều | Giá trị ứng viên | Lý do cần xem xét |
|---|---|---|
| Hệ điều hành runner | Linux, Windows | Khác biệt đường dẫn, tiến trình, quyền tệp và thư viện native |
| Runtime | Java 17, Java 21 | Khả năng tương thích bytecode, API và thư viện |
| Database | PostgreSQL 14, 16 | SQL, driver, migration và hành vi phiên bản |
| Browser | Chrome, Firefox, Safari | Engine, API trình duyệt và rendering |
| Locale | vi-VN, en-US | Định dạng ngày, số, tiền tệ và thông báo |
| Time zone | UTC, Asia/Ho_Chi_Minh | Chuyển đổi thời gian và ranh giới ngày |
| Feature flag | bật, tắt | Hai nhánh hành vi của tính năng |

Bảng này mới là tập chiều ứng viên, chưa phải ma trận thực thi. Một số chiều chỉ áp dụng cho một loại test. Ví dụ browser không liên quan đến unit test ở backend; database không cần thiết cho test thuần xử lý dữ liệu trong bộ nhớ.

### Ghi rõ phạm vi của từng chiều

Mỗi chiều nên có:

- Tên và định nghĩa.
- Các giá trị được hỗ trợ.
- Phiên bản cụ thể hoặc quy tắc chọn phiên bản.
- Những test hoặc thành phần bị ảnh hưởng.
- Các giá trị không tương thích với nhau.
- Chủ sở hữu và nguồn xác nhận.
- Thời điểm cần xem xét lại.

Tránh các nhãn mơ hồ như “latest” nếu pipeline không ghi lại phiên bản thực tế. Có thể dùng alias để chọn phiên bản mới nhất, nhưng kết quả cần lưu giá trị đã phân giải nhằm tái hiện lần chạy.

## 5. Ước lượng sự bùng nổ tổ hợp

Nếu mỗi chiều có số giá trị nhất định và tất cả đều kết hợp được với nhau, tổng số tổ hợp là tích số lượng giá trị của từng chiều.

Với k chiều, trong đó chiều thứ i có n_i giá trị:

\[
N = \prod_{i=1}^{k} n_i
\]

Ví dụ có 4 chiều:

- 3 hệ điều hành.
- 3 trình duyệt.
- 3 phiên bản runtime.
- 2 database.

Tổng số tổ hợp lý thuyết là:

\[
N = 3 \times 3 \times 3 \times 2 = 54
\]

Nếu mỗi tổ hợp chạy một bộ test mất 12 phút, tổng thời gian CPU tuần tự là 648 phút, tương đương 10,8 giờ. Chạy song song có thể rút ngắn thời gian lịch nhưng không làm giảm tổng tài nguyên, chi phí runner hoặc áp lực lên dịch vụ dùng chung.

### Ví dụ tổ hợp lớn hơn

Giả sử một sản phẩm có 5 chiều với số giá trị lần lượt là 4, 4, 3, 3 và 2:

\[
N = 4 \times 4 \times 3 \times 3 \times 2 = 288
\]

Khi thêm một chiều có 5 giá trị, tổng số tổ hợp thành 1.440. Một thay đổi tưởng nhỏ trong danh sách phiên bản có thể làm số job tăng gấp năm lần.

Vì vậy, cần ước lượng số tổ hợp trước khi đưa ma trận vào CI. Xem xét thời gian trung bình mỗi job, số runner đồng thời, thời gian chờ hàng đợi, chi phí dịch vụ phụ thuộc và chi phí điều tra khi một tổ hợp thất bại.

### Tổ hợp lý thuyết và tổ hợp hợp lệ

Không phải mọi kết hợp đều có thể triển khai. Ví dụ:

- Một phiên bản database chỉ hỗ trợ một số runtime.
- Safari chỉ chạy trên nền tảng hệ điều hành nhất định.
- Một thiết bị không có phiên bản trình duyệt desktop.
- Một tính năng chỉ tồn tại khi feature flag được bật.
- Một driver không tương thích với phiên bản runtime cũ.

Nếu loại các kết hợp bất hợp lệ, số tổ hợp thực tế có thể nhỏ hơn tích lý thuyết. Hãy ghi rõ ràng buộc thay vì để job thất bại do cấu hình không thể chạy.

## 6. Áp dụng ràng buộc để loại tổ hợp không hợp lệ

Ràng buộc (constraint) mô tả những giá trị không thể hoặc không cần kết hợp. Nó giúp ma trận phản ánh kiến trúc thật và tránh lãng phí runner.

Ví dụ:

| Chiều A | Chiều B | Ràng buộc |
|---|---|---|
| Browser = Safari | OS = Windows | Không hợp lệ nếu Safari không nằm trong nền tảng hỗ trợ của sản phẩm |
| Runtime = Java 17 | Library = phiên bản yêu cầu Java 21 | Không tương thích |
| Feature = experimental | Environment = production-like stable | Không áp dụng cho bộ kiểm thử phát hành |
| DB = PostgreSQL | Driver = driver chỉ dành cho SQL Server | Không hợp lệ |

Có thể biểu diễn ràng buộc bằng điều kiện logic:

~~~text
IF browser == Safari THEN os == macOS
IF runtime == Java 17 THEN libraryVersion != requires-Java-21
IF featureFlag == experimental THEN suite != release-smoke
~~~

Các điều kiện trên chỉ minh họa. Ràng buộc cần được kiểm tra cùng chủ sở hữu nền tảng và chính sách hỗ trợ. Không loại một tổ hợp chỉ vì hiện tại chưa có runner nếu tổ hợp đó vẫn nằm trong cam kết hỗ trợ.

### Phân biệt bất hợp lệ và ít ưu tiên

- **Bất hợp lệ:** tổ hợp không thể chạy hoặc không được sản phẩm hỗ trợ theo chính sách.
- **Ít ưu tiên:** tổ hợp hợp lệ nhưng có mức rủi ro hoặc mức sử dụng thấp hơn.
- **Chưa có khả năng kiểm thử:** tổ hợp cần được kiểm tra nhưng runner hoặc dịch vụ chưa sẵn có.
- **Không áp dụng:** chiều đó không ảnh hưởng đến test đang chạy.

Những trạng thái này cần được ghi riêng. Không nên đánh dấu một tổ hợp “không hợp lệ” chỉ để giảm số job khi thực chất nhóm chưa có hạ tầng kiểm tra.

## 7. Chọn chiến lược bao phủ tổ hợp

Sau khi xác định chiều, giá trị và ràng buộc, nhóm cần chọn mức bao phủ phù hợp. Có một số chiến lược thường dùng.

### Full combination testing

Kiểm thử toàn bộ tổ hợp hợp lệ. Phù hợp khi số tổ hợp nhỏ, hậu quả lỗi cao hoặc chính sách yêu cầu xác minh đầy đủ.

Ưu điểm là mọi tổ hợp trong phạm vi đều có bằng chứng. Nhược điểm là chi phí tăng theo tích các chiều và có thể không khả thi khi ma trận lớn.

Full combination thường phù hợp với một tập chiều nhỏ, ví dụ hai phiên bản runtime và hai cấu hình database cho một thành phần cốt lõi.

### Representative testing

Chọn một số tổ hợp đại diện theo mức sử dụng, phiên bản thấp nhất/cao nhất, kiến trúc khác biệt hoặc lịch sử lỗi. Chiến lược này dễ giải thích và vận hành, nhưng có thể bỏ sót tương tác giữa các chiều nếu chọn chỉ dựa trên mức phổ biến.

### Pairwise testing

Pairwise testing chọn tập tổ hợp sao cho mọi cặp giá trị giữa hai chiều đều xuất hiện ít nhất một lần trong tập được chọn, trong phạm vi các ràng buộc hợp lệ. Nhiều lỗi cấu hình phát sinh từ tương tác của hai yếu tố, vì vậy pairwise có thể giảm mạnh số tổ hợp trong khi vẫn tạo độ bao phủ cặp có hệ thống.

Ví dụ, với 3 chiều:

- OS: Linux, Windows.
- Runtime: Java 17, Java 21.
- Database: PostgreSQL, MySQL.

Full combination có 2 × 2 × 2 = 8 tổ hợp. Một tập pairwise có thể chỉ cần 4 tổ hợp nếu không có ràng buộc:

| Tổ hợp | OS | Runtime | Database |
|---|---|---|---|
| A | Linux | Java 17 | PostgreSQL |
| B | Linux | Java 21 | MySQL |
| C | Windows | Java 17 | MySQL |
| D | Windows | Java 21 | PostgreSQL |

Trong ví dụ này, từng cặp giá trị của mỗi cặp chiều xuất hiện ít nhất một lần. Nhóm cần xác minh tập được tạo thực sự đạt pairwise coverage, nhất là khi có ràng buộc hoặc nhiều giá trị hơn.

Pairwise không chứng minh mọi tương tác ba chiều hoặc cao hơn đã được kiểm tra. Nếu lỗi chỉ xảy ra khi Windows + Java 21 + PostgreSQL cùng xuất hiện, một ma trận pairwise có thể bỏ sót tổ hợp đó.

### T-way testing

T-way testing tổng quát hóa pairwise. Với t=2, đó là pairwise; với t=3, mọi bộ giá trị của ba chiều cần xuất hiện ít nhất một lần; với t=4, mọi bộ bốn chiều được bao phủ.

Tăng t làm tăng độ bao phủ tương tác nhưng thường làm tăng số tổ hợp. Chọn t theo rủi ro, lịch sử lỗi và mức độ tương tác giữa các thành phần. Với một số tính năng nhạy cảm, có thể dùng 3-way hoặc 4-way cho các chiều liên quan trực tiếp.

### Orthogonal array và covering array

Orthogonal array là cấu trúc thiết kế thực nghiệm có tính cân bằng theo các tổ hợp giá trị nhất định. Covering array được dùng để tạo tập cấu hình bao phủ mọi tương tác t-way theo yêu cầu. Công cụ combinatorial testing có thể sinh tập này và xử lý constraints.

Nhóm không cần tự xây dựng thuật toán sinh ma trận nếu đã có công cụ phù hợp. Tuy nhiên, cần hiểu tiêu chí bao phủ, định nghĩa chiều, cách xử lý ràng buộc và báo cáo kết quả của công cụ. Một danh sách ngắn hơn không tự động có nghĩa là bao phủ tốt hơn.

## 8. Kết hợp pairwise với kiểm thử rủi ro cao

Pairwise là kỹ thuật giảm số tổ hợp, không phải chính sách thay thế phân tích rủi ro. Hãy xác định những tổ hợp cần kiểm tra bắt buộc trước khi áp dụng giảm tổ hợp.

Một cách tiếp cận thực tế:

1. Xác định tổ hợp nền tảng quan trọng nhất theo mức sử dụng.
2. Bổ sung các tổ hợp biên như phiên bản thấp nhất và mới nhất.
3. Bổ sung các tổ hợp có lịch sử lỗi hoặc thay đổi lớn.
4. Giữ các tổ hợp bắt buộc theo hợp đồng hỗ trợ hoặc yêu cầu pháp lý.
5. Dùng pairwise/t-way để bao phủ phần còn lại.
6. Kiểm tra xem mọi cặp hoặc nhóm tương tác quan trọng có xuất hiện không.

### Ưu tiên theo rủi ro

Có thể đánh giá mỗi tổ hợp theo các yếu tố:

- Mức độ ảnh hưởng nếu lỗi xảy ra.
- Khả năng người dùng gặp cấu hình đó.
- Khả năng tương tác giữa các chiều.
- Độ mới của phiên bản hoặc thay đổi gần đây.
- Lịch sử defect và sự cố.
- Khả năng phát hiện lỗi ở tầng thấp hơn.

Không nhất thiết gán điểm số phức tạp. Một phân loại Cao/Trung bình/Thấp có thể đủ nếu tiêu chí rõ và có người chịu trách nhiệm.

### Tổ hợp bắt buộc

Một số tổ hợp không nên bị loại khỏi lịch chạy chỉ vì pairwise đã bao phủ các cặp của chúng. Ví dụ:

- Phiên bản thấp nhất được hỗ trợ với cấu hình cài đặt chuẩn.
- Phiên bản mới nhất của runtime hoặc browser.
- Tổ hợp liên quan đến lỗi nghiêm trọng từng xảy ra.
- Cấu hình khách hàng trọng yếu.
- Cặp dịch vụ có thay đổi API hoặc giao thức trong lần phát hành.
- Cấu hình bảo mật đặc biệt như TLS, mã hóa hoặc quyền truy cập.

Giữ riêng danh sách tổ hợp bắt buộc giúp quyết định có thể kiểm tra và giải thích được.

## 9. Dùng equivalence partitioning và boundary value analysis

Ma trận môi trường không thay thế kỹ thuật thiết kế dữ liệu kiểm thử. Khi một chiều có rất nhiều giá trị, có thể chia thành các lớp tương đương và kiểm tra giá trị biên.

Ví dụ, nếu sản phẩm hỗ trợ trình duyệt từ phiên bản 120 trở lên, nhóm có thể phân lớp:

- Phiên bản thấp nhất được hỗ trợ.
- Một phiên bản giữa đại diện cho nhánh ổn định.
- Phiên bản mới nhất được hỗ trợ.
- Phiên bản ngay dưới ngưỡng hỗ trợ để xác nhận thông báo hoặc hành vi từ chối.

Tương tự, với runtime:

- Phiên bản tối thiểu được hỗ trợ.
- Phiên bản LTS phổ biến.
- Phiên bản mới nhất được hỗ trợ.
- Phiên bản không còn hỗ trợ để xác nhận chính sách từ chối nếu cần.

Không nên kiểm tra một giá trị ngẫu nhiên ở giữa mà không hiểu nó đại diện cho lớp nào. Lớp tương đương cần dựa trên hành vi kỹ thuật và chính sách tương thích.

## 10. Phân bổ ma trận theo giai đoạn CI/CD

Không phải mọi tổ hợp cần chạy trong mọi pull request. Có thể chia ma trận thành các lớp theo tốc độ phản hồi và mức độ rủi ro.

| Giai đoạn | Phạm vi môi trường | Mục tiêu |
|---|---|---|
| Local / pre-commit | Một môi trường tham chiếu | Phản hồi nhanh khi phát triển |
| Pull request | Smoke trên môi trường chuẩn và một tập tổ hợp nhỏ có rủi ro cao | Chặn lỗi cơ bản và lỗi tương thích quan trọng |
| Sau merge | Pairwise hoặc tập mở rộng | Xác minh tương tác cấu hình rộng hơn |
| Nightly / scheduled | Ma trận rộng, t-way và phiên bản phụ trợ | Phát hiện lỗi ít gặp và thay đổi nền tảng |
| Release candidate | Toàn bộ tổ hợp bắt buộc cùng kiểm tra hồi quy trọng yếu | Tạo bằng chứng phát hành |
| Post-release | Smoke và synthetic checks trên môi trường thật theo chính sách | Phát hiện vấn đề sau triển khai |

Phân tầng giúp cân bằng thời gian phản hồi với độ bao phủ. Tuy nhiên, các tổ hợp bắt buộc theo rủi ro hoặc cam kết hỗ trợ phải xuất hiện ở thời điểm phù hợp trước khi phát hành.

### Quy tắc khi thay đổi chiều môi trường

Khi thêm phiên bản browser, runtime hoặc database:

1. Xác định phiên bản có thuộc phạm vi hỗ trợ không.
2. Xác định test và thành phần chịu ảnh hưởng.
3. Đánh giá số tổ hợp tăng thêm và constraints mới.
4. Chọn chiến lược chạy: PR, nightly hoặc release.
5. Bổ sung bằng chứng cho phiên bản thấp nhất/cao nhất nếu chính sách yêu cầu.
6. Cập nhật tài liệu hỗ trợ và chủ sở hữu ma trận.

Không nên thêm giá trị vào ma trận mà không xem lại chi phí pipeline và năng lực runner.

## 11. Triển khai ma trận trong CI/CD

Nhiều nền tảng CI hỗ trợ matrix strategy để tạo job từ danh sách giá trị. Ma trận nên được định nghĩa rõ, có thể tái hiện và tránh sinh tổ hợp không hợp lệ.

### Ví dụ YAML minh họa cấu trúc matrix

~~~yaml
name: Compatibility checks

on:
  pull_request:

jobs:
  test:
    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        os: [ubuntu-latest, windows-latest]
        java: [17, 21]
        database: [postgresql, mysql]
        exclude:
          - os: windows-latest
            database: mysql
        include:
          - os: ubuntu-latest
            java: 21
            database: postgresql
            label: primary
    runs-on: matrix.os
    steps:
      - checkout: source
      - setup-java:
          distribution: temurin
          java-version: matrix.java
      - run: ./gradlew test
~~~

Đây là YAML giả lập để minh họa matrix, include, exclude, fail-fast và max-parallel, không phải workflow có thể chạy trực tiếp. Khi triển khai, hãy chuyển các khóa thành cú pháp của nền tảng CI đang dùng, đồng thời khai báo dịch vụ database và chờ healthcheck tương ứng trước khi chạy test.

### Giới hạn song song

max-parallel giới hạn số job chạy đồng thời trong một ma trận. Chọn giá trị dựa trên:

- Số runner thực tế và quota của nền tảng CI.
- CPU, bộ nhớ và dung lượng đĩa.
- Giới hạn kết nối của database và dịch vụ dùng chung.
- Quota của sandbox hoặc API đối tác.
- Thời gian hàng đợi và deadline pipeline.
- Mức độ cô lập dữ liệu giữa các job.

Chạy song song quá nhiều có thể làm môi trường chậm, gây timeout và tạo flaky test. Nếu nhiều job cùng ghi vào một database hoặc tài khoản, kết quả có thể bị ảnh hưởng lẫn nhau. Cần dùng namespace, schema, tenant hoặc dữ liệu riêng cho từng job.

### Quản lý fail-fast

Fail-fast dừng các job còn lại khi một job thất bại đầu tiên. Điều này tiết kiệm tài nguyên khi lỗi chung khiến toàn bộ ma trận không còn ý nghĩa. Nhưng nó cũng có thể che khuất việc một số tổ hợp độc lập có lỗi riêng.

- Dùng fail-fast khi một lỗi nền tảng chung khiến các job khác không thể cung cấp thông tin hữu ích.
- Tắt fail-fast khi cần biết phạm vi ảnh hưởng trên nhiều môi trường, nhất là trước phát hành.
- Có thể phân nhóm job theo mức độ quan trọng để dừng nhóm phụ nhưng tiếp tục nhóm bắt buộc.

Quyết định cần phản ánh mục tiêu của lần chạy và khả năng tiêu thụ kết quả.

### Lưu dấu vết của tổ hợp

Mỗi job nên ghi lại các giá trị đã phân giải: OS image, runtime chính xác, browser build, database version, locale, feature flags và commit. Không chỉ ghi tên alias như latest hoặc stable.

Khi test thất bại, nhóm cần tái tạo được tổ hợp và dữ liệu. Artifact nên chứa cấu hình không nhạy cảm, log, test report và thông tin phiên bản; không đưa secret vào artifact.

## 12. Tách ma trận theo loại test

Một ma trận chung cho mọi test thường gây lãng phí. Tạo profile theo tầng và mục tiêu kiểm thử giúp chọn chiều phù hợp.

### Unit và component

Unit test thường không cần toàn bộ môi trường. Chạy trên runtime và hệ điều hành tham chiếu; thêm một số phiên bản runtime nếu tương thích thư viện là rủi ro. Component test có thể cần browser hoặc service giả lập nhưng không nhất thiết cần mọi database.

### API và integration

Tập trung vào runtime, database, driver, broker, schema và phiên bản dịch vụ. Browser hoặc kích thước màn hình không liên quan. Có thể chạy một số tổ hợp database/version trong nightly nếu số lượng lớn.

### UI và E2E

Tập trung vào browser engine, OS, viewport, thiết bị, locale và hành vi nhập liệu. Không cần nhân tất cả phiên bản database ở mỗi browser job nếu backend đã được kiểm tra riêng và môi trường backend là cố định.

### Performance và resilience

Dùng môi trường có tài nguyên, cấu hình và tải nền được kiểm soát. Không trộn nhiều job gây tải cạnh tranh trên cùng một hệ thống nếu mục tiêu là đo hiệu năng. Với resilience test, cần xác nhận khả năng khôi phục và cleanup trước khi chạy trên môi trường chia sẻ.

## 13. Bảo đảm tính tái lập và cô lập giữa các job

Một ma trận chỉ đáng tin khi mỗi job chạy trên cấu hình xác định và không bị job khác làm thay đổi kết quả.

### Cố định phiên bản và cấu hình

- Ghi lại image digest hoặc phiên bản runner.
- Cố định runtime và browser build khi cần so sánh.
- Khóa phiên bản dependency hoặc lưu lockfile.
- Ghi schema và migration version.
- Lưu cấu hình feature flag và locale đã dùng.
- Tránh dùng latest không được phân giải trong báo cáo.

### Cô lập dữ liệu

Mỗi job nên có dữ liệu độc lập hoặc không gian dữ liệu riêng. Có thể dùng database/schema riêng, tenant riêng, prefix tài nguyên hoặc test run identifier. Test cần dọn dữ liệu của chính nó và không dựa vào thứ tự chạy.

Nếu không thể cô lập hoàn toàn, phải có cơ chế khóa, phân vùng hoặc chạy tuần tự. Dữ liệu dùng chung có thể khiến test pass/fail phụ thuộc vào thứ tự và số job chạy đồng thời.

### Kiểm soát phụ thuộc dùng chung

Các dịch vụ sandbox, message broker hoặc API giới hạn quota có thể trở thành nút thắt. Nên xác định giới hạn, dùng dữ liệu riêng, giới hạn song song và ghi nhận lỗi throttling. Nếu một dịch vụ ngoài gặp sự cố, cần phân biệt lỗi phụ thuộc với lỗi ứng dụng.

## 14. Đánh giá mức bao phủ và khoảng trống của ma trận

Một ma trận có ít job không có nghĩa là bao phủ tốt. Nhóm cần đo được các chiều và tương tác đã được kiểm tra.

### Chỉ số bao phủ

Có thể theo dõi:

- Tỷ lệ giá trị của từng chiều đã xuất hiện trong test.
- Tỷ lệ cặp giá trị hợp lệ đã được bao phủ.
- Tỷ lệ bộ t-way đã được bao phủ.
- Số tổ hợp bắt buộc đã chạy trên phiên bản hiện tại.
- Số tổ hợp chưa chạy, bị chặn hoặc thất bại do môi trường.
- Tỷ lệ tổ hợp có thể tái hiện từ metadata.
- Thời gian và chi phí trung bình của một vòng ma trận.

Cần nêu rõ mẫu số. Ví dụ, pairwise coverage nên tính trên các cặp giá trị hợp lệ theo constraints, không tính các cặp bất khả thi như một khoảng trống chưa kiểm thử.

### Báo cáo khoảng trống

Một báo cáo hữu ích nên cho biết:

- Chiều hoặc giá trị nào chưa được kiểm tra.
- Cặp hoặc nhóm tương tác nào chưa được bao phủ.
- Lý do tổ hợp chưa chạy: không hợp lệ, chưa có runner, bị bỏ qua hay lỗi môi trường.
- Mức độ rủi ro và người chấp nhận khoảng trống.
- Hành động và thời điểm bổ sung bằng chứng.

Không gộp không chạy thành đạt. Một tổ hợp được loại bởi constraint hợp lệ khác với một job bị skip vì thiếu runner.

### Dùng defect history để điều chỉnh

Khi lỗi chỉ xuất hiện trên một browser hoặc database cụ thể, hãy bổ sung tổ hợp đó hoặc tăng mức t-way cho các chiều liên quan. Nếu nhiều vòng không phát hiện thêm lỗi ở một nhóm cấu hình ít sử dụng, có thể cân nhắc giảm tần suất, nhưng cần xem chính sách hỗ trợ và thay đổi nền tảng.

Ma trận nên được điều chỉnh theo bằng chứng, không phải chỉ theo thói quen.

## 15. Ví dụ thực hành: thiết kế ma trận cho dịch vụ đặt hàng

Giả sử dịch vụ đặt hàng hỗ trợ Java 17 và 21, PostgreSQL 14 và 16, chạy trên Linux và Windows ở môi trường CI. API được kiểm tra bằng integration test; một phần luồng được kiểm tra E2E trên Chrome và Firefox.

### Bước 1: xác định chiều

| Chiều | Giá trị |
|---|---|
| OS runner | Linux, Windows |
| Java | 17, 21 |
| Database | PostgreSQL 14, PostgreSQL 16 |
| Browser cho E2E | Chrome, Firefox |

Nếu nhân tất cả chiều sẽ có 2 × 2 × 2 × 2 = 16 tổ hợp. Nhưng browser chỉ liên quan đến E2E, trong khi integration test backend không cần browser. Vì vậy, tách thành hai profile.

### Bước 2: ma trận integration backend

Dùng OS, Java và database: 2 × 2 × 2 = 8 tổ hợp. Nếu chi phí lớn, có thể chạy tổ hợp chuẩn trên pull request và pairwise hoặc toàn bộ 8 tổ hợp theo lịch. Nếu Java 17 là phiên bản thấp nhất được hỗ trợ, cần giữ ít nhất một tổ hợp bắt buộc xác nhận nó.

### Bước 3: ma trận E2E trình duyệt

Dùng browser và OS hợp lệ theo chính sách hỗ trợ. Nếu Firefox và Chrome được hỗ trợ trên cả hai OS, có 4 tổ hợp. Nếu Safari chỉ hỗ trợ trên macOS thì phải đưa macOS vào chiều OS của profile E2E và áp dụng constraint tương ứng.

### Bước 4: lịch chạy

- Pull request: unit test, integration trên Linux + Java 21 + PostgreSQL 16 và E2E smoke trên Chrome.
- Sau merge: bổ sung tổ hợp Java thấp nhất và database thấp nhất.
- Nightly: chạy ma trận integration rộng và pairwise E2E trên browser/OS được hỗ trợ.
- Release candidate: chạy mọi tổ hợp bắt buộc và hồi quy trọng yếu.
- Khi nâng database: chạy thêm các kiểm tra migration và tương thích trên phiên bản cũ/mới.

Lịch này là ví dụ. Nhóm cần điều chỉnh theo thời gian pipeline, cam kết hỗ trợ và rủi ro thực tế.

### Bước 5: theo dõi kết quả

Mỗi kết quả nên gắn với commit, job ID, profile, phiên bản runtime/database/browser, trạng thái test, thời gian chạy và artifact. Nếu một tổ hợp thất bại, có thể xác định lỗi thuộc ứng dụng, môi trường, dữ liệu hay runner.

## 16. Quản lý thay đổi và vòng đời ma trận

Ma trận là một phần của chính sách tương thích và cần có chủ sở hữu. Khi phiên bản mới phát hành hoặc phiên bản cũ hết hỗ trợ, nhóm phải cập nhật chiều và lịch chạy.

### Thêm giá trị mới

Trước khi thêm một giá trị:

1. Xác nhận sản phẩm có ý định hỗ trợ giá trị đó.
2. Xác định thành phần và test chịu ảnh hưởng.
3. Kiểm tra runner, image, driver và dịch vụ cần thiết.
4. Đánh giá constraints và số tổ hợp mới.
5. Chọn mức bao phủ và giai đoạn chạy.
6. Ghi nhận kết quả đầu tiên và lỗi tương thích.
7. Cập nhật tài liệu hỗ trợ, dashboard và chủ sở hữu.

### Loại bỏ giá trị cũ

Trước khi loại bỏ:

- Xác nhận chính sách hỗ trợ và ngày kết thúc.
- Xem mức sử dụng và yêu cầu khách hàng.
- Kiểm tra phụ thuộc hoặc hợp đồng còn liên quan.
- Thông báo thay đổi theo quy trình sản phẩm.
- Loại khỏi ma trận ở đúng thời điểm.
- Giữ lại thông tin lịch sử để điều tra lỗi cũ khi cần.

Không nên xóa phiên bản khỏi ma trận chỉ vì job thường xuyên đỏ. Cần xác định lỗi sản phẩm, lỗi runner hay môi trường không còn được duy trì.

### Chủ sở hữu và rà soát

Mỗi ma trận nên có chủ sở hữu chịu trách nhiệm:

- Duyệt thêm hoặc loại chiều và giá trị.
- Xem lại constraints.
- Theo dõi chi phí và thời gian pipeline.
- Kiểm tra các khoảng trống rủi ro.
- Xem xét lịch chạy sau thay đổi kiến trúc.
- Ghi nhận lý do cho ngoại lệ.

Rà soát định kỳ hoặc khi có thay đổi lớn sẽ giúp ma trận không trở thành cấu hình lỗi thời.

## 17. Những sai lầm thường gặp

- **Chạy mọi tổ hợp ở mọi pull request:** pipeline dài và tiêu tốn tài nguyên mà không phải lúc nào cũng tăng bằng chứng tương xứng.
- **Chọn tổ hợp chỉ theo mức phổ biến:** có thể bỏ qua phiên bản thấp nhất, mới nhất hoặc tương tác rủi ro cao.
- **Dùng pairwise như bảo đảm đầy đủ:** pairwise không bao phủ mọi lỗi tương tác ba chiều hoặc cao hơn.
- **Không khai báo constraints:** tạo job bất hợp lệ và báo lỗi giả do cấu hình không thể chạy.
- **Gộp mọi loại test vào một ma trận:** tạo ra tổ hợp không liên quan, ví dụ browser cho unit test backend.
- **Dùng alias phiên bản không được ghi lại:** khiến kết quả khó tái hiện.
- **Chạy song song không giới hạn:** gây quá tải runner, database hoặc sandbox và tạo flaky test.
- **Dùng chung dữ liệu giữa job:** khiến kết quả phụ thuộc thứ tự và trạng thái của job khác.
- **Không lưu metadata:** không thể biết chính xác tổ hợp nào đã chạy khi điều tra lỗi.
- **Đánh dấu tổ hợp bị skip như đã đạt:** làm báo cáo bao phủ sai lệch.
- **Không cập nhật ma trận khi chính sách hỗ trợ thay đổi:** tạo khoảng trống giữa cam kết và bằng chứng.
- **Tối ưu số job mà bỏ qua rủi ro:** ma trận nhỏ hơn nhưng có thể bỏ mất tổ hợp bắt buộc.

## 18. Danh sách kiểm tra thiết kế ma trận môi trường

**Phạm vi và chiều**

- Chính sách môi trường được hỗ trợ đã rõ chưa?
- Các chiều có khả năng ảnh hưởng đến hành vi đã được xác định chưa?
- Mỗi giá trị có lý do đại diện hoặc rủi ro cụ thể không?
- Các chiều không liên quan đến từng loại test đã được tách ra chưa?

**Tổ hợp và ràng buộc**

- Đã tính số tổ hợp lý thuyết và số tổ hợp hợp lệ chưa?
- Constraints có được ghi rõ và kiểm chứng không?
- Tổ hợp bắt buộc theo rủi ro hoặc cam kết hỗ trợ đã được giữ chưa?
- Pairwise/t-way có tiêu chí bao phủ và báo cáo rõ chưa?
- Các tương tác có lịch sử lỗi có được kiểm tra riêng không?

**CI/CD và vận hành**

- Ma trận được phân bổ theo local, pull request, nightly và release hợp lý chưa?
- Giới hạn song song có phù hợp với năng lực runner và dịch vụ phụ thuộc không?
- Fail-fast có phù hợp với mục tiêu của lần chạy không?
- Mỗi job có dữ liệu độc lập và cấu hình có thể tái lập không?
- Artifact có lưu phiên bản chính xác và kết quả không nhạy cảm không?

**Theo dõi và quản trị**

- Có báo cáo giá trị, cặp hoặc nhóm tương tác chưa được bao phủ không?
- Các tổ hợp bị skip, blocked và invalid có được phân loại riêng không?
- Có chủ sở hữu và lịch rà soát ma trận không?
- Việc thêm/bỏ phiên bản có được liên kết với chính sách hỗ trợ không?
- Chi phí, thời gian pipeline và defect history có được dùng để điều chỉnh ma trận không?

## Kết luận

Thiết kế ma trận môi trường là bài toán cân bằng giữa cam kết hỗ trợ, rủi ro tương thích, độ bao phủ và chi phí CI/CD. Nhóm cần xác định các chiều có ý nghĩa, chọn giá trị đại diện, áp dụng constraints để loại tổ hợp bất hợp lệ và ước lượng sự bùng nổ tổ hợp trước khi triển khai. Full combination phù hợp với phạm vi nhỏ hoặc rủi ro bắt buộc; representative, pairwise và t-way giúp giảm số job nhưng cần được kết hợp với các tổ hợp rủi ro cao và phiên bản biên. Tách ma trận theo loại test và giai đoạn pipeline, giới hạn song song, cô lập dữ liệu, lưu metadata và rà soát chính sách hỗ trợ giúp kết quả có thể tái lập, giải thích được và đủ tin cậy cho quyết định phát hành.
