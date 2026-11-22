# Chọn thời điểm đánh giá bảo mật, hiệu năng và độ tin cậy

Bảo mật, hiệu năng và độ tin cậy cần được đánh giá xuyên suốt vòng đời phát triển. Nếu chỉ kiểm tra ở giai đoạn trước phát hành, nhóm có thể phát hiện vấn đề khi kiến trúc và mã nguồn đã khó thay đổi, dữ liệu kiểm thử không còn đại diện hoặc không còn đủ thời gian để xử lý. Ngược lại, đánh giá quá sớm mà không lặp lại sau thay đổi cũng không bảo đảm sản phẩm hiện tại vẫn đáp ứng yêu cầu.

Chiến lược phù hợp là chọn thời điểm đánh giá dựa trên rủi ro, mức độ trưởng thành của sản phẩm và loại bằng chứng cần thu thập. Một số câu hỏi có thể được trả lời ngay khi phân tích yêu cầu hoặc thiết kế; một số khác chỉ có thể xác minh khi mã nguồn, môi trường tích hợp hoặc hệ thống gần production đã sẵn sàng. Sau phát hành, dữ liệu vận hành tiếp tục cung cấp bằng chứng để cập nhật đánh giá.

## 1. Ba thuộc tính chất lượng cần được xem xét từ sớm

**Bảo mật (security)** là khả năng bảo vệ tính bí mật, tính toàn vẹn và tính sẵn sàng của thông tin và chức năng trước các hành vi trái phép hoặc có chủ đích. Đánh giá bảo mật cần xem xét tài sản cần bảo vệ, tác nhân đe dọa, ranh giới tin cậy, quyền truy cập, dữ liệu nhạy cảm và cách hệ thống phát hiện, ứng phó với sự cố.

**Hiệu năng (performance efficiency)** mô tả mức độ hệ thống đáp ứng yêu cầu về thời gian phản hồi, thông lượng và sử dụng tài nguyên trong điều kiện tải xác định. Đánh giá hiệu năng cần gắn với mô hình sử dụng thực tế: số người dùng đồng thời, phân bố yêu cầu, kích thước dữ liệu, thời điểm tải cao và giới hạn hạ tầng.

**Độ tin cậy (reliability)** là khả năng hệ thống thực hiện chức năng đúng và duy trì hoặc khôi phục dịch vụ trong những điều kiện đã xác định, kể cả khi xảy ra lỗi. Đánh giá độ tin cậy bao gồm tính sẵn sàng, khả năng chịu lỗi, khả năng phục hồi, tính nhất quán của dữ liệu và khả năng vận hành ổn định theo thời gian.

Ba thuộc tính có liên hệ với nhau. Một cuộc tấn công có thể làm cạn tài nguyên và ảnh hưởng hiệu năng; tải cao có thể làm tăng timeout và lỗi; cơ chế bảo mật quá yếu có thể ảnh hưởng tính toàn vẹn; một cơ chế kiểm soát hoặc ghi log được cấu hình sai có thể làm dịch vụ mất ổn định. Vì vậy, kế hoạch kiểm thử nên xác định cả mục tiêu riêng và các tương tác quan trọng giữa chúng.

## 2. Nguyên tắc chọn thời điểm đánh giá

Không phải mọi hoạt động đánh giá đều cần chờ đến khi hệ thống chạy hoàn chỉnh. Hãy chọn thời điểm theo năm nguyên tắc:

1. **Đánh giá ngay khi có đủ thông tin để trả lời câu hỏi:** yêu cầu bảo mật có thể được rà soát trước khi có mã; giới hạn tải có thể được ước lượng từ mô hình sử dụng và kiến trúc.
2. **Đưa phản hồi về nơi có thể xử lý hiệu quả:** lỗi thiết kế nên được phát hiện trong review thiết kế; lỗi triển khai nên được phát hiện trong review mã hoặc CI; lỗi tích hợp cần môi trường tích hợp.
3. **Lặp lại sau thay đổi có ảnh hưởng:** kết quả cũ chỉ còn giá trị nếu phiên bản, cấu hình, dữ liệu và điều kiện vẫn phù hợp.
4. **Dùng môi trường và dữ liệu đại diện cho câu hỏi:** kiểm thử hiệu năng cần tải và hạ tầng gần với mục tiêu; kiểm thử bảo mật cần cấu hình, danh tính và ranh giới tin cậy phù hợp; kiểm thử phục hồi cần mô phỏng đúng loại lỗi cần đánh giá.
5. **Kết hợp kiểm thử trước và sau phát hành:** kiểm thử trước phát hành giảm rủi ro đã biết; giám sát production và phản hồi sự cố giúp phát hiện rủi ro mà môi trường thử nghiệm không thể tái tạo đầy đủ.

Thời điểm đánh giá cũng phụ thuộc vào mức độ tác động và chi phí sửa lỗi. Một luồng xử lý dữ liệu cá nhân, thanh toán hoặc xác thực cần được xem xét sớm và sâu hơn một trang nội dung ít rủi ro. Một hệ thống có tải biến động lớn cần xác lập mô hình tải trước khi hoàn thiện kiến trúc.

## 3. Đánh giá theo từng giai đoạn phát triển

### Giai đoạn yêu cầu và khởi tạo

Đây là thời điểm chuyển nhu cầu thành các yêu cầu chất lượng có thể đánh giá. Nhóm sản phẩm, kiến trúc, phát triển, kiểm thử, bảo mật và vận hành nên cùng xác định mục tiêu, rủi ro và tiêu chí chấp nhận.

**Bảo mật:** xác định tài sản, dữ liệu nhạy cảm, nhóm người dùng, vai trò, yêu cầu xác thực và phân quyền, nghĩa vụ bảo vệ dữ liệu, luồng dữ liệu và các tình huống lạm dụng. Ghi nhận yêu cầu như giới hạn truy cập, thời gian lưu dữ liệu, mã hóa hoặc kiểm toán khi phù hợp. Làm rõ các hành vi không được phép, không chỉ luồng sử dụng hợp lệ.

**Hiệu năng:** xác định loại giao dịch quan trọng, tải bình thường và tải đỉnh dự kiến, thời gian phản hồi mong muốn, thông lượng, kích thước dữ liệu và các giới hạn tài nguyên. Phân biệt yêu cầu cho người dùng cuối với yêu cầu xử lý nền hoặc tác vụ theo lô.

**Độ tin cậy:** xác định mức sẵn sàng cần đạt, thời gian gián đoạn có thể chấp nhận, mức mất dữ liệu tối đa, thời gian khôi phục, hành vi khi phụ thuộc không sẵn sàng và quy trình vận hành. Các mục tiêu như RTO (Recovery Time Objective) và RPO (Recovery Point Objective) cần được thống nhất khi hệ thống có yêu cầu phục hồi sau sự cố.

Đầu ra nên là các yêu cầu phi chức năng có thể kiểm chứng, các tình huống rủi ro và tiêu chí chấp nhận sơ bộ. Nếu không có dữ liệu đường cơ sở, hãy ghi rõ giả định và cách thu thập dữ liệu ban đầu.

### Giai đoạn kiến trúc và thiết kế

Ở giai đoạn này, nhóm có thể đánh giá nhiều rủi ro trước khi triển khai. Review kiến trúc và mô hình hóa giúp phát hiện vấn đề về cấu trúc mà kiểm thử hộp đen sau này có thể khó định vị.

**Bảo mật:** thực hiện threat modeling hoặc phân tích mối đe dọa cho tài sản quan trọng, ranh giới tin cậy, luồng dữ liệu và điểm tích hợp. Xem xét xác thực, phân quyền, quản lý bí mật, mã hóa, phân vùng mạng, nguyên tắc đặc quyền tối thiểu và cách xử lý lỗi. Kiểm tra thiết kế có tạo đường truy cập trái phép hoặc lưu dữ liệu vượt nhu cầu không.

**Hiệu năng:** đánh giá các điểm có nguy cơ nghẽn như truy vấn cơ sở dữ liệu, gọi dịch vụ đồng bộ, khóa dùng chung, hàng đợi, xử lý tệp và giao tiếp mạng. Ước lượng dung lượng, khả năng mở rộng, chiến lược cache và giới hạn kết nối. Xác định các giả định cần được kiểm chứng bằng prototype hoặc thử nghiệm tải.

**Độ tin cậy:** xem xét điểm lỗi đơn, phụ thuộc bên ngoài, chiến lược timeout, retry, circuit breaker, idempotency, hàng đợi, sao lưu, failover và phục hồi. Xác định dữ liệu nào phải nhất quán và trạng thái nào cần đối soát khi một bước thất bại.

Review thiết kế nên tạo ra quyết định và hành động có chủ sở hữu. Nếu một giả định về tải, nhà cung cấp hoặc cơ chế phục hồi chưa có bằng chứng, hãy đưa nó vào danh sách cần kiểm chứng trong giai đoạn tiếp theo.

### Giai đoạn triển khai và review mã

Khi mã nguồn được tạo, nhóm có thể kiểm tra thường xuyên với chi phí thấp bằng review, phân tích tĩnh và kiểm thử tự động.

**Bảo mật:** thực hiện review mã theo rủi ro; dùng SAST để tìm một số dạng điểm yếu trong mã; quét thư viện và thành phần phụ thuộc (SCA); phát hiện bí mật bị đưa vào repository; kiểm tra cấu hình an toàn và quyền truy cập. Công cụ có thể tạo cảnh báo sai hoặc bỏ sót vấn đề, vì vậy phát hiện quan trọng cần được xác minh.

**Hiệu năng:** dùng profiling, benchmark thành phần hoặc kiểm thử vi mô cho đoạn mã có nguy cơ tốn CPU, bộ nhớ hoặc I/O. Xem xét truy vấn, thuật toán, cấp phát bộ nhớ và xử lý dữ liệu lớn. Benchmark vi mô giúp so sánh một phần mã trong điều kiện kiểm soát; nó không thay thế kiểm thử tải toàn hệ thống.

**Độ tin cậy:** kiểm thử đơn vị cho xử lý lỗi, chuyển trạng thái, timeout, retry, tính lặp an toàn và bất biến dữ liệu. Review mã cần chú ý tài nguyên được giải phóng, transaction, xử lý ngoại lệ, tính đồng thời và các đường thoát lỗi.

Những kiểm tra này nên được tích hợp vào quy trình commit hoặc pull request khi phù hợp để phát hiện sớm. Cần quy định cách xử lý cảnh báo nghiêm trọng và cách ghi nhận ngoại lệ được chấp nhận.

### Giai đoạn tích hợp và kiểm thử hệ thống

Khi các thành phần được kết nối, nhiều giả định chỉ có thể kiểm tra bằng tương tác thật hoặc mô phỏng gần thực tế. Đây là giai đoạn quan trọng để đánh giá rủi ro tại ranh giới giữa dịch vụ, cơ sở dữ liệu, hàng đợi và nhà cung cấp.

**Bảo mật:** kiểm tra xác thực và phân quyền qua API, kiểm soát truy cập giữa dịch vụ, cấu hình TLS, xử lý token, CORS nếu có giao diện web, quản lý phiên và các luồng dữ liệu nhạy cảm. DAST có thể kiểm tra ứng dụng đang chạy; kiểm thử bảo mật API và kiểm thử xâm nhập có phạm vi xác định giúp đánh giá các đường tấn công quan trọng.

**Hiệu năng:** chạy kiểm thử tải với mô hình yêu cầu, dữ liệu, cấu hình và số người dùng đồng thời đại diện. Đo thời gian phản hồi theo phân vị, thông lượng, tỷ lệ lỗi và mức sử dụng CPU, bộ nhớ, mạng, kết nối cơ sở dữ liệu. Kiểm tra các phụ thuộc và xác định nơi gây nghẽn.

**Độ tin cậy:** mô phỏng timeout, mất kết nối, lỗi phụ thuộc, hàng đợi tăng, tiến trình dừng, khởi động lại và lỗi một phần. Xác minh hệ thống giữ được bất biến dữ liệu, phản hồi phù hợp, thử lại có kiểm soát và phục hồi được. Kiểm thử tích hợp cần xác minh các tương tác mà mock không thể chứng minh.

Ở giai đoạn này, cần ghi rõ thành phần thật, thành phần giả lập, phiên bản dịch vụ, cấu hình và giới hạn của môi trường. Một kiểm thử sandbox đạt không tự động chứng minh hành vi production giống hệt.

### Giai đoạn tiền phát hành và sẵn sàng vận hành

Trước phát hành, nhóm tổng hợp bằng chứng và kiểm tra cấu hình của phiên bản sẽ triển khai. Không nên chỉ xem kết quả kiểm thử mà bỏ qua khác biệt giữa môi trường thử nghiệm và production.

**Bảo mật:** rà soát cấu hình triển khai, quyền truy cập, bí mật, chứng thư, quy tắc mạng, logging và các cảnh báo còn mở. Thực hiện kiểm thử xâm nhập hoặc đánh giá độc lập cho hệ thống có rủi ro cao, phạm vi lớn hoặc thay đổi đáng kể. Xác nhận lỗ hổng nghiêm trọng đã được xử lý hoặc có quyết định chấp nhận rủi ro đúng thẩm quyền.

**Hiệu năng:** xác nhận kết quả kiểm thử tải, sức chịu đựng và khả năng mở rộng với cấu hình gần production. Kiểm tra dung lượng, giới hạn tài nguyên, autoscaling, cache, kết nối và khả năng xử lý tải đỉnh. Đặt ngưỡng cảnh báo và chuẩn bị kế hoạch khi vượt ngưỡng.

**Độ tin cậy:** diễn tập failover, phục hồi từ backup, khôi phục dữ liệu, rollback và quy trình ứng phó sự cố khi phù hợp. Kiểm tra health check, readiness, liveness, giám sát, cảnh báo, runbook và quyền trực vận hành. Đảm bảo người vận hành biết cách nhận biết và xử lý trạng thái không nhất quán.

Quyết định phát hành cần dựa trên mức rủi ro còn lại, bằng chứng có sẵn, phạm vi chưa kiểm tra và khả năng phát hiện/khôi phục. Nếu một bài kiểm thử quan trọng bị chặn, báo cáo phải thể hiện đó là khoảng trống bằng chứng.

### Giai đoạn triển khai và vận hành

Một số rủi ro chỉ xuất hiện ở quy mô, dữ liệu hoặc hành vi người dùng thật. Sau phát hành, đánh giá tiếp tục thông qua giám sát, cảnh báo, phản hồi và quy trình ứng phó.

**Bảo mật:** theo dõi cảnh báo, hành vi truy cập bất thường, lỗ hổng mới trong phụ thuộc, trạng thái chứng thư và các sự kiện liên quan đến dữ liệu. Duy trì quy trình vá lỗi, quản lý cấu hình, rà soát quyền định kỳ và phản ứng sự cố. Không đưa dữ liệu nhạy cảm vào log vượt nhu cầu.

**Hiệu năng:** theo dõi độ trễ, thông lượng, tỷ lệ lỗi, mức sử dụng tài nguyên và các chỉ số theo luồng nghiệp vụ. So sánh tải thực tế với mô hình dự kiến, phát hiện xu hướng tăng trưởng và điều chỉnh dung lượng trước khi hệ thống quá tải.

**Độ tin cậy:** theo dõi SLI (Service Level Indicator) và SLO (Service Level Objective), lỗi, thời gian gián đoạn, độ trễ, độ sâu hàng đợi và kết quả phục hồi. Phân tích sự cố, diễn tập khôi phục định kỳ và kiểm tra backup thực sự có thể khôi phục. Dùng bài học từ sự cố để cập nhật rủi ro và kiểm thử hồi quy.

Giám sát production bổ sung bằng chứng cho kiểm thử trước phát hành; nó không thay thế việc kiểm thử có kiểm soát. Khi cần thử nghiệm lỗi hoặc tải trên production, phải có phạm vi, giới hạn, giám sát, phương án dừng và sự phối hợp vận hành phù hợp.

## 4. Ma trận thời điểm đánh giá theo thuộc tính

Bảng sau gợi ý những hoạt động thường phù hợp ở từng giai đoạn. Mức độ và tần suất cần điều chỉnh theo kiến trúc, rủi ro và yêu cầu của sản phẩm.

| Giai đoạn | Bảo mật | Hiệu năng | Độ tin cậy |
| --- | --- | --- | --- |
| Yêu cầu | Phân loại dữ liệu, yêu cầu xác thực/phân quyền, tình huống lạm dụng và nghĩa vụ bảo vệ | Mô hình tải, thời gian phản hồi, thông lượng và giới hạn tài nguyên | Mục tiêu sẵn sàng, RTO/RPO, nhu cầu phục hồi và phụ thuộc quan trọng |
| Kiến trúc và thiết kế | Threat modeling, review ranh giới tin cậy và luồng dữ liệu | Phân tích điểm nghẽn, dung lượng và khả năng mở rộng | Phân tích điểm lỗi đơn, timeout, retry, sao lưu và failover |
| Triển khai và review mã | Review bảo mật, SAST, SCA, quét bí mật và cấu hình | Profiling, benchmark thành phần, review truy vấn và thuật toán | Kiểm thử đơn vị cho lỗi, trạng thái, transaction và tài nguyên |
| Tích hợp và hệ thống | Kiểm thử API, DAST, xác thực/phân quyền và kiểm thử xâm nhập theo phạm vi | Kiểm thử tải, stress, spike, soak và phân tích tài nguyên | Mô phỏng lỗi phụ thuộc, khởi động lại, retry, phục hồi và tính nhất quán |
| Tiền phát hành | Rà soát cấu hình, lỗ hổng còn mở, quyền và bí mật | Xác nhận dung lượng, ngưỡng hiệu năng và autoscaling | Diễn tập failover, backup/restore, rollback và runbook |
| Vận hành | Theo dõi sự kiện, vá lỗi, rà soát quyền và ứng phó sự cố | Theo dõi SLI, xu hướng tải và độ trễ thực tế | Theo dõi SLO, sự cố, cảnh báo và kiểm tra khả năng phục hồi |

Ma trận không có nghĩa mọi dự án phải thực hiện mọi hoạt động ở mọi giai đoạn. Nó giúp nhóm kiểm tra xem có thuộc tính nào chỉ được xem xét quá muộn hoặc chưa có người chịu trách nhiệm.

## 5. Chọn đúng loại kiểm thử cho đúng thời điểm

Thời điểm đánh giá cần phù hợp với câu hỏi cần trả lời và loại bằng chứng có thể thu được.

### Bảo mật

- **Rà soát yêu cầu và threat modeling:** phù hợp khi yêu cầu, luồng dữ liệu và kiến trúc đã đủ rõ để nhận diện tài sản, tác nhân và ranh giới tin cậy.
- **Review mã, SAST, SCA và quét bí mật:** thực hiện thường xuyên khi mã hoặc phụ thuộc thay đổi; phát hiện sớm các vấn đề có thể nhận diện từ mã và cấu hình.
- **Kiểm thử bảo mật API và DAST:** thực hiện khi dịch vụ hoặc ứng dụng có thể chạy trong môi trường kiểm thử với cấu hình xác định.
- **Kiểm thử xâm nhập:** lên lịch theo mức rủi ro, thay đổi kiến trúc, bề mặt tấn công và yêu cầu tuân thủ; có thể cần đánh giá độc lập trước phát hành lớn hoặc theo chu kỳ.
- **Giám sát và quản lý lỗ hổng:** duy trì sau phát hành vì mối đe dọa, thư viện và cấu hình tiếp tục thay đổi.

### Hiệu năng

- **Ước lượng và mô hình tải:** thực hiện khi xác định yêu cầu và thiết kế kiến trúc để tránh chọn giải pháp không đáp ứng nhu cầu.
- **Benchmark và profiling:** dùng trong phát triển khi cần tìm chi phí của thuật toán, truy vấn hoặc thành phần cụ thể.
- **Kiểm thử tải:** thực hiện khi hệ thống tích hợp đủ để tạo luồng đại diện và môi trường có thể đo được.
- **Kiểm thử stress:** tăng tải vượt mức dự kiến để tìm giới hạn và quan sát cách hệ thống suy giảm hoặc phục hồi.
- **Kiểm thử spike:** thay đổi tải đột ngột để đánh giá phản ứng với đợt tăng hoặc giảm lưu lượng.
- **Kiểm thử soak (endurance):** duy trì tải trong thời gian dài để phát hiện rò rỉ bộ nhớ, cạn tài nguyên, tăng độ trễ hoặc suy giảm theo thời gian.
- **Theo dõi production:** kiểm tra mô hình tải và ngưỡng đã giả định có phù hợp với hành vi thật hay không.

### Độ tin cậy

- **Phân tích thiết kế và failure mode:** thực hiện trước triển khai để nhận diện điểm lỗi và tác động.
- **Kiểm thử lỗi ở cấp thành phần và tích hợp:** thực hiện khi có thể mô phỏng timeout, lỗi phụ thuộc, lỗi transaction hoặc trạng thái không hợp lệ.
- **Kiểm thử phục hồi và failover:** thực hiện khi hạ tầng, cấu hình và quy trình phục hồi đã đủ đại diện.
- **Kiểm thử backup/restore và khôi phục thảm họa:** diễn tập trước phát hành quan trọng và lặp lại theo lịch để xác nhận quy trình vẫn hoạt động.
- **Kiểm thử chịu lỗi hoặc chaos engineering:** chỉ thực hiện khi có giả thuyết rõ, giới hạn tác động, giám sát và cơ chế dừng; tăng dần phạm vi khi đã có năng lực vận hành phù hợp.
- **Theo dõi SLI/SLO và sự cố:** liên tục trong vận hành để nhận diện xu hướng và cập nhật giả định.

## 6. Ví dụ: chọn thời điểm đánh giá cho hệ thống thanh toán

Giả sử nhóm phát triển một hệ thống thanh toán trực tuyến mới. Hệ thống xử lý thông tin người dùng, gọi nhà cung cấp thanh toán và cần phục vụ lưu lượng tăng cao vào một số thời điểm.

Ở giai đoạn yêu cầu, nhóm xác định dữ liệu thẻ không được lưu nếu không có nhu cầu và cơ chế được phê duyệt; quyền truy cập phải được giới hạn theo vai trò; p95 của API khởi tạo thanh toán cần đáp ứng ngưỡng đã thống nhất ở mức tải dự kiến; và giao dịch phải có khả năng đối soát sau timeout.

Trong review kiến trúc, nhóm lập sơ đồ luồng dữ liệu và ranh giới tin cậy, đánh giá cách lưu bí mật, giới hạn kết nối tới nhà cung cấp, thiết kế idempotency và chiến lược retry. Nhóm cũng ước lượng tải đỉnh và xác định điểm nghẽn có thể xảy ra ở cơ sở dữ liệu hoặc cổng thanh toán.

Trong lúc phát triển, CI chạy SAST, SCA, quét bí mật và kiểm thử đơn vị cho quy tắc phân quyền, tính tiền, trạng thái giao dịch và xử lý lỗi. Các benchmark thành phần được dùng khi tối ưu phần tính toán hoặc truy vấn có chi phí cao.

Khi tích hợp, nhóm chạy kiểm thử API và DAST trong môi trường kiểm thử, kiểm thử hợp đồng với nhà cung cấp, kiểm thử tải với dữ liệu đại diện và mô phỏng timeout, gửi lại yêu cầu, lỗi kết nối và khởi động lại dịch vụ. Kết quả được đối chiếu với tiêu chí bảo mật, hiệu năng và độ tin cậy đã đặt ra.

Trước phát hành, nhóm rà soát cấu hình và quyền production, xác nhận các lỗ hổng nghiêm trọng, kiểm tra dung lượng, diễn tập backup/restore và xác minh quy trình rollback. Nếu sandbox của nhà cung cấp không mô phỏng được tải hoặc một số hành vi production, khoảng trống đó được ghi nhận cùng biện pháp giám sát và phương án xử lý.

Sau phát hành, nhóm theo dõi sự kiện bảo mật, độ trễ, tỷ lệ timeout, số giao dịch chưa đối soát và SLO. Nếu lưu lượng thực tế vượt mô hình hoặc xuất hiện giao dịch chưa rõ trạng thái, nhóm cập nhật đánh giá rủi ro và bổ sung kiểm thử cho lần phát hành tiếp theo.

Ví dụ cho thấy mỗi giai đoạn đóng góp một loại bằng chứng. Review thiết kế không thể xác nhận thời gian phản hồi thực tế; kiểm thử tải không thể chứng minh hệ thống an toàn trước mọi tấn công; kiểm thử backup thành công một lần không thay thế việc kiểm tra phục hồi định kỳ.

## 7. Đánh giá lại khi có thay đổi hoặc tín hiệu mới

Nhóm cần đánh giá lại bảo mật, hiệu năng hoặc độ tin cậy khi có thay đổi ảnh hưởng đến giả định ban đầu. Những sự kiện thường kích hoạt đánh giá gồm:

- Thêm loại dữ liệu nhạy cảm, luồng xác thực mới, vai trò người dùng hoặc bề mặt API.
- Thay đổi kiến trúc, ranh giới dịch vụ, giao thức, thư viện, phiên bản nền tảng hoặc nhà cung cấp.
- Thay đổi thuật toán, truy vấn, cache, cấu trúc dữ liệu hoặc luồng xử lý đồng thời.
- Dự báo tải tăng, mở rộng thị trường, bổ sung thiết bị hoặc thay đổi mô hình sử dụng.
- Thay đổi cấu hình mạng, quyền, chứng thư, hạ tầng, vùng triển khai hoặc cơ chế autoscaling.
- Phát hiện lỗ hổng mới, cảnh báo bảo mật, lỗi nghiêm trọng hoặc sự cố production.
- Kết quả kiểm thử bị chặn, không ổn định hoặc không đại diện cho môi trường dự kiến.
- Thay đổi mục tiêu dịch vụ, cam kết khách hàng, quy định hoặc yêu cầu phục hồi.

Khi thay đổi xảy ra, hãy xác định bằng chứng cũ nào còn hiệu lực, kiểm thử nào cần chạy lại và rủi ro mới nào xuất hiện. Không nhất thiết chạy lại toàn bộ bộ kiểm thử nếu tác động đã được phân tích rõ; phạm vi hồi quy nên dựa trên phụ thuộc và rủi ro.

## 8. Xác định tiêu chí và điều kiện đánh giá

Để kết quả có thể hỗ trợ quyết định, mỗi hoạt động nên có mục tiêu, điều kiện và tiêu chí được thống nhất trước khi chạy.

| Thuộc tính | Điều kiện cần xác định | Ví dụ tiêu chí hoặc bằng chứng |
| --- | --- | --- |
| Bảo mật | Tài sản, vai trò, phạm vi kiểm thử, môi trường, phiên bản, quy tắc phân loại phát hiện | Không còn phát hiện nghiêm trọng chưa xử lý trong phạm vi đã đánh giá; các ngoại lệ có chủ sở hữu và phê duyệt |
| Hiệu năng | Mô hình tải, dữ liệu, thời lượng, cấu hình, điểm đo, phân vị và tài nguyên | p95 dưới ngưỡng ở mức tải quy định, tỷ lệ lỗi không vượt giới hạn và tài nguyên còn dư địa phù hợp |
| Độ tin cậy | Loại lỗi mô phỏng, trạng thái ban đầu, dữ liệu, phương án phục hồi và thời gian quan sát | Dịch vụ phục hồi trong RTO, mất dữ liệu không vượt RPO và trạng thái giao dịch có thể đối soát |

Các ví dụ tiêu chí không phải ngưỡng chung cho mọi hệ thống. Mức cụ thể cần được xác lập từ yêu cầu, rủi ro, đường cơ sở, cam kết dịch vụ và khả năng vận hành.

Với kiểm thử bảo mật, “không có phát hiện” chỉ có ý nghĩa trong phạm vi công cụ và kỹ thuật đã dùng; cần xem xét phạm vi quét, xác minh thủ công và các khu vực bị loại trừ. Với kiểm thử hiệu năng, phải báo cáo cả điều kiện tải và tỷ lệ lỗi, tránh chỉ nêu thời gian phản hồi. Với độ tin cậy, cần xác minh kết quả phục hồi và tính toàn vẹn dữ liệu, không chỉ thời gian dịch vụ hoạt động trở lại.

## 9. Phối hợp trách nhiệm và luồng phản hồi

Đánh giá chất lượng là trách nhiệm chung. Vai trò có thể khác nhau giữa các tổ chức, nhưng cần xác định rõ ai cung cấp yêu cầu, ai thực hiện đánh giá, ai xử lý phát hiện và ai chấp nhận rủi ro.

- **Chủ sản phẩm và nghiệp vụ:** xác định nhu cầu, mức tác động và ưu tiên chất lượng.
- **Kiến trúc sư và kỹ sư phát triển:** thiết kế biện pháp kiểm soát, tạo khả năng kiểm thử và xử lý vấn đề trong mã hoặc kiến trúc.
- **Kỹ sư kiểm thử:** thiết kế chiến lược, chọn kỹ thuật, thực hiện kiểm thử, lưu bằng chứng và báo cáo giới hạn.
- **Chuyên gia bảo mật:** hỗ trợ threat modeling, đánh giá điểm yếu, kiểm thử chuyên sâu và tư vấn xử lý.
- **Vận hành/SRE:** xác định mục tiêu độ tin cậy, giám sát, dung lượng, ứng phó sự cố và phục hồi.
- **Người có thẩm quyền phát hành hoặc chấp nhận rủi ro:** xem xét bằng chứng và quyết định theo chính sách của tổ chức.

Phát hiện cần được chuyển thành hành động có thể theo dõi: mô tả vấn đề, phạm vi ảnh hưởng, mức độ, bằng chứng, người phụ trách, hạn xử lý và điều kiện xác minh lại. Sau khi sửa, chạy kiểm thử xác nhận và hồi quy phù hợp; cập nhật đánh giá rủi ro nếu kết quả làm thay đổi nhận định.

## 10. Những sai lầm thường gặp khi chọn thời điểm

- **Chờ đến cuối dự án mới đánh giá:** vấn đề kiến trúc hoặc yêu cầu có thể đã trở nên tốn kém để sửa.
- **Chỉ dùng công cụ tự động:** công cụ phát hiện một số lớp vấn đề nhưng không thay thế review, mô hình hóa đe dọa, phân tích kết quả và kiểm thử theo ngữ cảnh.
- **Đánh giá một lần rồi coi như hoàn tất:** thay đổi mã, dữ liệu, tải, phụ thuộc và cấu hình có thể làm mất hiệu lực bằng chứng cũ.
- **Dùng môi trường không đại diện:** kết quả hiệu năng trên máy phát triển hoặc kết quả phục hồi với dữ liệu rất nhỏ có thể không phản ánh production.
- **Chỉ đo trung bình:** có thể che giấu nhóm yêu cầu rất chậm hoặc lỗi tập trung ở một luồng.
- **Chỉ kiểm tra dịch vụ còn chạy:** độ tin cậy còn bao gồm tính đúng đắn, tính toàn vẹn dữ liệu và khả năng phục hồi.
- **Đánh giá bảo mật chỉ bằng quét lỗ hổng:** cần xem xét quyền, luồng dữ liệu, cấu hình, logic nghiệp vụ và các tình huống lạm dụng.
- **Thử nghiệm lỗi hoặc tải trên production thiếu kiểm soát:** có thể ảnh hưởng người dùng và dữ liệu; cần giả thuyết, phạm vi, giám sát và cơ chế dừng rõ ràng.
- **Không ghi giới hạn:** báo cáo không nêu mock, sandbox, dữ liệu, cấu hình hoặc phạm vi bị bỏ qua khiến người đọc đánh giá quá cao bằng chứng.

## 11. Checklist lập lịch đánh giá

Trước khi chốt kế hoạch cho một phiên bản, nhóm có thể rà soát:

- [ ] Yêu cầu bảo mật, hiệu năng và độ tin cậy đã được xác định cùng tiêu chí có thể kiểm chứng.
- [ ] Rủi ro quan trọng đã được xem xét từ giai đoạn yêu cầu và thiết kế.
- [ ] Có hoạt động review mã, phân tích tĩnh và kiểm thử thành phần phù hợp trong quá trình phát triển.
- [ ] Có kế hoạch kiểm thử tích hợp và hệ thống với dữ liệu, cấu hình và phụ thuộc đại diện.
- [ ] Mô hình tải và tiêu chí hiệu năng đã được thống nhất trước khi chạy kiểm thử.
- [ ] Các tình huống lỗi, phục hồi, backup/restore và failover quan trọng đã được kiểm tra.
- [ ] Cấu hình bảo mật, quyền, bí mật và lỗ hổng còn mở đã được rà soát trước phát hành.
- [ ] Có giám sát, cảnh báo, SLI/SLO, runbook và người chịu trách nhiệm sau phát hành.
- [ ] Các thay đổi quan trọng có tiêu chí kích hoạt đánh giá lại và kiểm thử hồi quy.
- [ ] Báo cáo ghi rõ bằng chứng, phiên bản, môi trường, phạm vi, giới hạn và rủi ro còn lại.

## 12. Những điểm cần ghi nhớ

- Bảo mật, hiệu năng và độ tin cậy cần được đánh giá xuyên suốt vòng đời, từ yêu cầu đến vận hành.
- Đánh giá sớm giúp phát hiện rủi ro về yêu cầu và thiết kế; kiểm thử mã, tích hợp và hệ thống cung cấp bằng chứng về triển khai; giám sát production cung cấp dữ liệu thực tế.
- Chọn thời điểm dựa trên câu hỏi cần trả lời, mức rủi ro, độ trưởng thành của hệ thống và tính đại diện của môi trường.
- Lặp lại đánh giá khi thay đổi mã, kiến trúc, phụ thuộc, dữ liệu, tải, cấu hình hoặc khi xuất hiện sự cố và lỗ hổng mới.
- Không một công cụ hoặc một lần kiểm thử nào chứng minh tuyệt đối hệ thống an toàn, nhanh và đáng tin cậy trong mọi điều kiện.
- Kết luận cần nêu phạm vi, điều kiện, bằng chứng, giới hạn và rủi ro còn lại để hỗ trợ quyết định phát hành và vận hành.

## Câu hỏi tự kiểm tra

1. Vì sao cần xem xét yêu cầu bảo mật, hiệu năng và độ tin cậy trước khi bắt đầu triển khai mã nguồn?
2. Hãy nêu ví dụ một rủi ro bảo mật có thể phát hiện trong review kiến trúc và một rủi ro chỉ có thể kiểm tra khi ứng dụng đang chạy.
3. Phân biệt kiểm thử tải, stress, spike và soak. Mỗi loại phù hợp với câu hỏi nào và nên thực hiện khi nào?
4. Vì sao kiểm thử backup thành công một lần chưa đủ để khẳng định khả năng phục hồi lâu dài?
5. Một thay đổi API của nhà cung cấp ảnh hưởng thế nào đến kế hoạch đánh giá bảo mật, hiệu năng và độ tin cậy?
6. Hãy lập lịch đánh giá cho một tính năng mới qua các giai đoạn yêu cầu, thiết kế, triển khai, tích hợp, tiền phát hành và vận hành.
7. Khi một kiểm thử quan trọng bị chặn do môi trường, báo cáo và quyết định phát hành cần thể hiện giới hạn đó như thế nào?
