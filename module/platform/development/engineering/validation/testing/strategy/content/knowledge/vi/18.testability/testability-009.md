# Ưu tiên cải tiến sản phẩm khi chi phí kiểm tra xuất phát từ thiết kế khó quan sát

Một nhóm có thể đầu tư nhiều vào framework, test data và pipeline nhưng vẫn mất nhiều thời gian để xác minh một hành vi đơn giản. Test phải chờ bằng sleep dài vì không biết tác vụ đã hoàn tất chưa; người kiểm thử phải đọc trực tiếp nhiều bảng dữ liệu để suy ra trạng thái; một lỗi chỉ xuất hiện trong môi trường tích hợp vì các phụ thuộc bị kết nối cứng; hoặc khi E2E thất bại, nhóm không biết request đã dừng ở API, queue hay worker. Trong những trường hợp này, chi phí kiểm tra có thể bắt nguồn từ cách sản phẩm được thiết kế, chứ không chỉ từ chất lượng mã kiểm thử.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, cần nhận diện lúc nào nên ưu tiên cải tiến thiết kế sản phẩm để giảm chi phí kiểm tra. Mục tiêu là làm cho hành vi quan trọng dễ quan sát, trạng thái có thể xác minh, phụ thuộc có thể kiểm soát và lỗi có thể truy vết. Nhóm cần đánh giá lợi ích của cải tiến so với rủi ro thay đổi, mức đầu tư và tác động đến người dùng. Không phải mọi khó khăn khi kiểm thử đều đòi hỏi thay đổi sản phẩm; quyết định phải dựa trên bằng chứng về nguyên nhân và giá trị lâu dài.

## 1. Hiểu khả năng kiểm thử và chi phí kiểm tra

### Khả năng kiểm thử là thuộc tính của sản phẩm

Khả năng kiểm thử (testability) là mức độ dễ dàng để xác định sản phẩm có đáp ứng yêu cầu hay không trong các điều kiện xác định. Một sản phẩm có khả năng kiểm thử tốt cho phép nhóm:

- Đưa hệ thống vào trạng thái cần kiểm tra một cách có kiểm soát.
- Tạo đầu vào và điều kiện cần thiết mà không phải thao tác thủ công phức tạp.
- Quan sát hành vi và trạng thái thông qua tín hiệu đáng tin cậy.
- Phân biệt kết quả đúng, sai và chưa xác định.
- Tái hiện tình huống lỗi và xác định thành phần liên quan.
- Dọn dẹp hoặc khôi phục trạng thái sau kiểm tra.

Khả năng kiểm thử chịu ảnh hưởng bởi kiến trúc, giao diện, mô hình trạng thái, ranh giới phụ thuộc, dữ liệu, cơ chế bất đồng bộ, khả năng quan sát và tài liệu vận hành. Nó cần được xem xét từ yêu cầu và thiết kế, không chỉ sau khi sản phẩm đã hoàn thành.

### Phân biệt khả năng kiểm thử với khả năng quan sát

Khả năng quan sát (observability) là mức độ có thể suy ra trạng thái và hành vi bên trong hệ thống từ các đầu ra mà hệ thống cung cấp, chẳng hạn log, metric, trace, sự kiện và trạng thái nghiệp vụ.

Khả năng kiểm thử rộng hơn. Ngoài việc quan sát, nhóm còn cần kiểm soát hoặc tạo ra điều kiện kiểm tra. Ví dụ:

- Một hệ thống có log chi tiết nhưng không có cách tạo trạng thái lỗi có thể quan sát tốt nhưng khó kiểm thử phục hồi.
- Một API cho phép tạo dữ liệu thử nghiệm nhưng không trả trạng thái xử lý có thể điều khiển được đầu vào nhưng khó xác minh kết quả.
- Một worker có thể chạy lại với dữ liệu cố định và phát trạng thái có correlation ID hỗ trợ cả điều khiển lẫn quan sát.

Hai thuộc tính liên quan chặt chẽ. Cải thiện khả năng quan sát thường giảm chi phí chẩn đoán; cải thiện khả năng điều khiển trạng thái thường giảm chi phí chuẩn bị và tái hiện.

### Chi phí kiểm tra gồm nhiều phần

Không chỉ tính thời gian chạy test. Tổng chi phí kiểm tra có thể gồm:

| Thành phần chi phí | Ví dụ |
|---|---|
| Chuẩn bị | Tạo tài khoản, dữ liệu, quyền và trạng thái ban đầu bằng thao tác thủ công |
| Thực thi | Test phải chờ lâu, chạy nhiều bước hoặc khởi động nhiều dịch vụ |
| Xác minh | Đọc nhiều bảng, gọi nhiều API hoặc đối chiếu thủ công để biết kết quả |
| Chẩn đoán | Điều tra timeout, log rời rạc hoặc lỗi không có định danh xuyên dịch vụ |
| Khôi phục | Dọn dữ liệu, reset môi trường hoặc xử lý tác dụng phụ còn sót |
| Bảo trì | Sửa test khi cấu trúc nội bộ thay đổi dù hành vi nghiệp vụ không đổi |
| Điều phối | Chờ môi trường, người có quyền hoặc dịch vụ phụ thuộc để chạy kiểm tra |

Một thay đổi thiết kế có thể giảm nhiều khoản cùng lúc. Ví dụ, bổ sung trạng thái job có định danh và API truy vấn giúp test không cần sleep, giảm truy vấn trực tiếp database và làm lỗi timeout dễ chẩn đoán hơn.

### Nhận biết dấu hiệu chi phí bắt nguồn từ thiết kế

Một số dấu hiệu lặp lại cho thấy nhóm nên xem xét cải tiến sản phẩm:

- Không thể biết một thao tác bất đồng bộ đã hoàn tất hay chưa nếu không chờ tùy ý.
- Không có cách tạo hoặc đọc trạng thái cần kiểm tra qua giao diện được hỗ trợ.
- Logic phụ thuộc đồng hồ, số ngẫu nhiên hoặc dịch vụ bên ngoài mà không có điểm kiểm soát.
- Trạng thái nghiệp vụ bị phân tán và không có nguồn có thẩm quyền rõ ràng.
- Một lỗi chỉ được phát hiện bằng cách suy luận từ nhiều log không liên kết.
- Test phải truy cập chi tiết nội bộ dễ thay đổi vì sản phẩm thiếu hợp đồng quan sát ổn định.
- Một thay đổi nhỏ khiến nhiều test phải viết lại do các thành phần kết nối quá chặt.
- Không thể cô lập một tenant, tài khoản, giao dịch hoặc luồng xử lý trong môi trường kiểm thử.
- Nhóm thường xuyên phải nhờ vận hành hoặc nhà phát triển thực hiện thao tác thủ công để đưa hệ thống vào trạng thái test.

Một lần test khó chạy chưa đủ để kết luận thiết kế kém. Cần xem xét tần suất, mức ảnh hưởng, nguyên nhân và khả năng giải quyết ở tầng test hoặc môi trường.

## 2. Phân biệt vấn đề thiết kế với vấn đề của bộ kiểm thử

### Kiểm tra nguyên nhân trước khi đề xuất thay đổi sản phẩm

Không phải mọi test chập chờn đều là vấn đề thiết kế sản phẩm. Có thể test đang dùng locator không ổn định, assertion quá chặt, dữ liệu dùng chung hoặc timeout sai. Trước khi đề xuất thay đổi, hãy xác định vấn đề thuộc nhóm nào:

| Nguồn vấn đề | Dấu hiệu | Hướng xử lý ban đầu |
|---|---|---|
| Test code | Assertion sai, setup lặp, selector phụ thuộc cấu trúc giao diện | Sửa test, helper và oracle |
| Test data | Dữ liệu trùng, fixture không xác định, trạng thái cũ | Cải thiện factory, seed và cô lập dữ liệu |
| Môi trường | Tài nguyên thiếu, cấu hình khác nhau, sandbox không ổn định | Chuẩn hóa và quản lý môi trường |
| Pipeline | Concurrency sai, timeout không hợp lý, artifact thiếu | Sửa cách lập lịch, cấu hình và thu thập bằng chứng |
| Phụ thuộc bên ngoài | Nhà cung cấp không ổn định hoặc không có sandbox | Contract test, simulator hoặc thỏa thuận môi trường |
| Thiết kế sản phẩm | Không có trạng thái quan sát, ranh giới khó kiểm soát, dữ liệu không thể truy vết | Đề xuất cải tiến kiến trúc hoặc hợp đồng sản phẩm |

Một test có thể chứa nhiều nguyên nhân. Ví dụ, test phải sleep 60 giây có thể do worker xử lý chậm, nhưng cũng có thể do hệ thống không cung cấp trạng thái để biết khi nào xử lý xong. Cần đo thời gian xử lý thật và kiểm tra cách quan sát trước khi quyết định.

### Dùng bằng chứng để xác nhận nguyên nhân

Thu thập các bằng chứng sau:

- Số lần nhóm phải thực hiện thao tác thủ công cho cùng một loại kiểm tra.
- Thời gian trung bình từ khi bắt đầu test đến khi xác định được kết quả.
- Số lần test timeout do không biết trạng thái thực.
- Tỷ lệ thất bại không thể phân loại vì thiếu log hoặc correlation ID.
- Số test phải truy cập trực tiếp cấu trúc dữ liệu nội bộ.
- Mức độ phụ thuộc vào thứ tự hoặc trạng thái còn sót.
- Số lần phải sửa test do thay đổi triển khai không ảnh hưởng hợp đồng.
- Tần suất cần hỗ trợ từ nhóm sở hữu dịch vụ hoặc vận hành.
- Các lỗi sản phẩm từng bị bỏ sót vì không thể quan sát hoặc tạo điều kiện kiểm tra.

Bằng chứng cần gắn với một hành trình hoặc loại kiểm tra cụ thể. Không nên yêu cầu cải tiến lớn chỉ dựa trên cảm nhận rằng hệ thống “khó test”.

### Xác định phần khó có thể giải quyết ở tầng test

Trước khi sửa sản phẩm, thử các biện pháp ít xâm lấn khi phù hợp:

- Dùng fixture hoặc API setup đã được hỗ trợ.
- Thay sleep cố định bằng polling có timeout.
- Dùng clock hoặc random seed giả lập trong unit test.
- Dùng contract test cho ranh giới dịch vụ.
- Cải thiện correlation ID trong test harness nếu hệ thống đã phát tín hiệu tương ứng.
- Tạo test data namespace riêng.
- Dùng sandbox hoặc test double cho nhà cung cấp ngoài phạm vi.

Nếu các biện pháp này vẫn cần truy cập nội bộ không ổn định, thao tác thủ công hoặc suy luận không đáng tin cậy, đó là tín hiệu mạnh hơn để xem xét cải tiến thiết kế sản phẩm.

## 3. Những đặc điểm thiết kế thường làm tăng chi phí kiểm tra

### Trạng thái ẩn hoặc không có nguồn có thẩm quyền

Khi trạng thái nghiệp vụ nằm rải rác trong nhiều bảng hoặc chỉ thể hiện qua giao diện, test khó xác minh kết quả. Ví dụ, một job xuất báo cáo có thể có bản ghi trong database, message trong queue và file trên storage nhưng không có trạng thái thống nhất cho người gọi.

Cải tiến có thể gồm:

- Định nghĩa mô hình trạng thái nghiệp vụ rõ ràng.
- Xác định nguồn dữ liệu có thẩm quyền cho từng trạng thái.
- Cung cấp cách truy vấn trạng thái qua API hoặc giao diện quản trị được kiểm soát.
- Ghi nhận thời điểm chuyển trạng thái và mã tương quan.
- Quy định trạng thái trung gian, trạng thái cuối và điều kiện lỗi.

Không nhất thiết công khai mọi trường nội bộ. Chỉ cần cung cấp hợp đồng ổn định đủ để người dùng, vận hành và kiểm thử xác minh kết quả.

### Phụ thuộc kết nối cứng

Một thành phần gọi trực tiếp đồng hồ hệ thống, dịch vụ thanh toán, gửi email hoặc broker khiến test khó thay thế phụ thuộc và khó tạo lỗi có kiểm soát.

Cải tiến có thể gồm:

- Đưa phụ thuộc qua interface hoặc adapter có ranh giới rõ.
- Tiêm dependency trong cấu hình phù hợp.
- Cung cấp clock abstraction cho logic thời gian.
- Tách logic nghiệp vụ khỏi client của nhà cung cấp.
- Cho phép cấu hình endpoint sandbox và test double qua cơ chế an toàn.
- Định nghĩa hợp đồng lỗi, timeout và retry.

Mục tiêu là kiểm tra logic nghiệp vụ mà không cần gọi dịch vụ thật trong mọi bài test. Khi cần xác minh chính tích hợp thật, vẫn phải có contract hoặc integration test tương ứng.

### Tác dụng phụ không thể cô lập

Nếu một hành động luôn gửi email thật, phát sự kiện đến hệ thống dùng chung hoặc tạo giao dịch không thể đảo ngược, test sẽ tốn chi phí và có thể gây ảnh hưởng ngoài ý muốn.

Cải tiến có thể gồm:

- Hỗ trợ sandbox hoặc sink nhận email và webhook.
- Tách việc ghi nhận ý định nghiệp vụ khỏi việc gửi tác dụng phụ.
- Dùng idempotency key và event ID ổn định.
- Cung cấp cơ chế truy vết tác dụng phụ theo giao dịch.
- Cho phép cấu hình adapter trong môi trường kiểm thử.
- Có quy trình bù trừ hoặc hủy trong phạm vi nghiệp vụ cho phép.

Không thêm cờ tắt tác dụng phụ tùy tiện vào production path. Cấu hình test cần được giới hạn, xác thực và không thể vô tình vô hiệu hóa kiểm soát nghiệp vụ hoặc bảo mật.

### Không kiểm soát được thời gian và tính ngẫu nhiên

Logic gọi trực tiếp thời gian hệ thống hoặc random generator ở nhiều nơi làm test phụ thuộc thời điểm chạy. Điều này thường gây lỗi quanh hạn sử dụng, lịch định kỳ, phân bổ hoặc mã sinh tự động.

Cải tiến có thể gồm:

- Truyền Clock hoặc nguồn thời gian vào thành phần cần dùng.
- Tách random generator khỏi logic nghiệp vụ.
- Cho phép seed trong môi trường test.
- Định nghĩa timezone và cách xử lý ngày giờ.
- Lưu nguồn thời gian hoặc seed trong audit/diagnostic context khi phù hợp.

Không nên tạo một cơ chế thay đổi thời gian tùy ý có thể được kích hoạt trong môi trường thật. Quyền điều khiển clock và seed phải được giới hạn theo cấu hình hoặc dependency injection.

### Thiếu ranh giới và trạng thái cho xử lý bất đồng bộ

Một API trả về đã tiếp nhận nhưng không cung cấp mã job, trạng thái hoặc cách truy vấn kết quả khiến test phải chờ tùy ý hoặc đọc database nội bộ.

Cải tiến có thể gồm:

- Trả về định danh tác vụ hoặc correlation ID.
- Cung cấp trạng thái đã tiếp nhận, đang xử lý, hoàn tất hoặc thất bại.
- Định nghĩa cách truy vấn trạng thái và thời gian lưu trạng thái.
- Ghi nhận lỗi cuối và thông tin có thể điều tra.
- Hỗ trợ idempotency để request lặp không tạo job trùng.
- Phân biệt trạng thái tiếp nhận với trạng thái hoàn tất nghiệp vụ.

Trạng thái cần phản ánh nguồn có thẩm quyền và cập nhật theo semantics đã định. Không trả về hoàn tất trước khi công việc thực sự đáp ứng tiêu chí hoàn tất.

### Không có khả năng truy vết xuyên thành phần

Một request qua API, queue, worker và nhà cung cấp có thể tạo nhiều log nhưng không có định danh liên kết. Khi test fail, nhóm không biết log nào thuộc giao dịch đó.

Cải tiến có thể gồm:

- Truyền correlation ID hoặc trace context xuyên ranh giới.
- Gắn ID nghiệp vụ vào event và log.
- Ghi các mốc quan trọng như nhận request, commit, publish, consume và hoàn tất.
- Định nghĩa trường log có cấu trúc.
- Cung cấp liên kết từ báo cáo test đến trace hoặc log theo quyền truy cập.
- Che giấu dữ liệu nhạy cảm trong log và artifact.

Không cần log toàn bộ payload. Cần đủ định danh và sự kiện để tái dựng luồng mà không làm lộ bí mật.

## 4. Xác định loại cải tiến sản phẩm có giá trị cao

### Cải thiện khả năng quan sát

Ưu tiên khi nhóm không thể xác định trạng thái, nguyên nhân hoặc tiến trình xử lý.

Các cải tiến thường gặp:

- Trạng thái nghiệp vụ có ý nghĩa và API truy vấn.
- Log có cấu trúc với correlation ID.
- Metric phản ánh tỷ lệ hoàn tất, độ trễ và lỗi.
- Trace xuyên dịch vụ.
- Audit event cho thay đổi quan trọng.
- Thông tin lỗi ổn định, có mã và phân loại.

Lợi ích không chỉ dành cho kiểm thử. Vận hành, hỗ trợ khách hàng và điều tra sự cố cũng có thể sử dụng các tín hiệu đó.

### Cải thiện khả năng điều khiển

Ưu tiên khi khó tạo điều kiện đầu vào hoặc trạng thái cần kiểm tra.

Ví dụ:

- Clock abstraction.
- Seedable random source.
- Fixture builder hoặc API tạo dữ liệu có kiểm soát.
- Adapter cho phụ thuộc bên ngoài.
- Cơ chế tạo trạng thái lỗi trong môi trường test.
- Cấu hình concurrency hoặc retry có thể điều chỉnh trong môi trường cô lập.

Các điểm điều khiển cần có ranh giới rõ và quyền hạn phù hợp. Không biến test hook thành đường truy cập đặc quyền trong production.

### Cải thiện ranh giới và hợp đồng

Ưu tiên khi test phải phụ thuộc vào cấu trúc nội bộ dễ thay đổi hoặc các thành phần hiểu khác nhau về cùng một trạng thái.

Ví dụ:

- Tách domain logic khỏi I/O.
- Định nghĩa API và event schema rõ ràng.
- Chuẩn hóa mã lỗi và semantics timeout.
- Tách command tạo tác dụng phụ khỏi phần xử lý nghiệp vụ.
- Thiết kế transaction/outbox hoặc cơ chế idempotency khi cần.
- Định nghĩa nguồn dữ liệu có thẩm quyền và quy tắc nhất quán.

Ranh giới tốt giúp test ở đúng cấp: unit test cho logic, contract test cho giao tiếp, integration test cho hành vi thành phần và E2E cho hành trình.

### Cải thiện khả năng khôi phục và reset

Ưu tiên khi test để lại trạng thái khiến môi trường khó dùng lại hoặc phải reset toàn bộ.

Ví dụ:

- Dữ liệu có namespace và vòng đời rõ.
- Cleanup theo run ID.
- API quản trị được bảo vệ để reset fixture test.
- Transaction rollback hoặc database/schema riêng.
- Cơ chế purge message và job trong môi trường test.
- Seed dữ liệu có thể lặp lại.

Reset phải có phạm vi và quyền an toàn. Không cung cấp thao tác xóa rộng có thể nhắm nhầm dữ liệu dùng chung.

## 5. Đánh giá lợi ích và chi phí của cải tiến

### Ước lượng chi phí hiện tại

Để xác định giá trị, ước lượng chi phí lặp lại trong một khoảng thời gian:

- Số lần chạy test liên quan mỗi tuần hoặc mỗi tháng.
- Thời gian chuẩn bị và thực thi.
- Thời gian chẩn đoán khi fail.
- Thời gian hỗ trợ thủ công từ nhóm khác.
- Chi phí bảo trì test do thay đổi nội bộ.
- Chi phí do lỗi bị phát hiện muộn hoặc bị bỏ sót.
- Thời gian chờ môi trường và tác dụng phụ.

Không cần tạo mô hình tài chính chính xác cho mọi đề xuất. Ước lượng nhất quán đủ để so sánh các lựa chọn và nêu giả định.

### Ước lượng lợi ích dự kiến

Một cải tiến có thể tạo giá trị thông qua:

- Giảm thời gian chạy và chờ.
- Giảm thao tác setup/cleanup.
- Giảm số lần test flaky.
- Giảm thời gian xác định nguyên nhân.
- Giảm phụ thuộc vào người có chuyên môn hoặc quyền đặc biệt.
- Tăng khả năng chạy song song.
- Tăng độ tin cậy của bằng chứng.
- Giảm lỗi lọt đến production hoặc giảm thời gian xử lý sự cố.
- Tái sử dụng được cho nhiều test, dịch vụ hoặc nhóm.

Ưu tiên cải tiến có tác động rộng và giải quyết nguyên nhân gốc. Một trạng thái job dùng chung có thể giúp nhiều E2E, giám sát vận hành và hỗ trợ khách hàng.

### Ước lượng chi phí và rủi ro thay đổi

Cần tính đến:

- Thay đổi API hoặc schema và ảnh hưởng đến consumer.
- Công sức triển khai, review và tài liệu.
- Khả năng phát sinh lỗi trong quá trình thay đổi.
- Yêu cầu bảo mật và quyền truy cập.
- Tác động hiệu năng hoặc dung lượng log.
- Tính tương thích ngược và kế hoạch chuyển đổi.
- Chi phí duy trì cơ chế mới.

Một cải tiến giúp test dễ hơn nhưng làm API phức tạp, tăng bề mặt tấn công hoặc tạo gánh nặng vận hành có thể không đáng ưu tiên.

### Dùng mô hình so sánh đơn giản

Có thể đánh giá mỗi đề xuất theo thang định tính:

| Tiêu chí | Câu hỏi |
|---|---|
| Tác động đến rủi ro | Có giúp phát hiện hoặc ngăn lỗi quan trọng không? |
| Phạm vi tái sử dụng | Bao nhiêu test, hành trình hoặc nhóm hưởng lợi? |
| Tiết kiệm lặp lại | Giảm bao nhiêu thời gian hoặc thao tác qua mỗi lần chạy? |
| Chất lượng bằng chứng | Có làm kết quả đáng tin và dễ xác minh hơn không? |
| Chi phí thực hiện | Cần bao nhiêu công sức và thay đổi phụ thuộc? |
| Rủi ro thay đổi | Có ảnh hưởng tương thích, bảo mật hoặc vận hành không? |
| Độ chắc chắn | Nguyên nhân và lợi ích dự kiến có bằng chứng đến đâu? |

Có thể xếp hạng cao cho đề xuất có tác động lớn, tái sử dụng rộng, chi phí vừa phải và bằng chứng nguyên nhân rõ. Không nên cộng điểm máy móc khi các tiêu chí có mức độ quan trọng khác nhau; dùng ma trận để hỗ trợ thảo luận và ghi lại lý do quyết định.

## 6. Quy trình ưu tiên cải tiến theo từng bước

### Bước 1: Chọn hành trình hoặc nhóm test có chi phí cao

Dùng dữ liệu pipeline, báo cáo lỗi và phản hồi của người thực hiện để chọn một khu vực cụ thể. Ví dụ: E2E thanh toán mất nhiều thời gian vì phải chờ callback và kiểm tra nhiều bảng.

Tránh bắt đầu bằng mục tiêu chung như “làm hệ thống dễ test hơn”. Hãy chọn hành trình, loại kiểm tra và khoản chi phí có thể đo.

### Bước 2: Lập bản đồ điểm quan sát và điểm điều khiển

Vẽ luồng từ đầu vào đến kết quả:

- Đầu vào được tạo ở đâu?
- Ai xác thực và cấp quyền?
- Trạng thái được ghi ở đâu?
- Thành phần nào xử lý bất đồng bộ?
- Tác dụng phụ xảy ra tại đâu?
- Test có thể quan sát trạng thái nào?
- Có thể tạo lỗi hoặc trạng thái biên bằng cách nào?
- Cần truy vấn nguồn dữ liệu nào để xác minh?

Đánh dấu nơi phải dùng thao tác thủ công, truy cập nội bộ hoặc chờ không có tín hiệu.

### Bước 3: Xác định nguyên nhân gốc

Phân biệt thiếu công cụ với thiếu khả năng của sản phẩm. Ví dụ:

- Không có trace do pipeline chưa thu thập hay do ứng dụng không truyền trace context?
- Không biết job hoàn tất vì test chưa gọi API trạng thái hay vì sản phẩm không có trạng thái?
- Không thể tạo dữ liệu vì thiếu factory hay vì quy tắc nghiệp vụ không có giao diện tạo hợp lệ?
- Test phải mock nhiều lớp vì kiến trúc không có ranh giới hay vì test đang chọn sai cấp?

Ghi giả thuyết, bằng chứng hỗ trợ và điều gì cần kiểm tra để xác nhận.

### Bước 4: Đề xuất thay đổi nhỏ nhất giải quyết nguyên nhân

Mỗi đề xuất nên mô tả:

- Vấn đề quan sát được.
- Thay đổi thiết kế dự kiến.
- Hành vi hoặc hợp đồng sau thay đổi.
- Nhóm và thành phần được hưởng lợi.
- Rủi ro tương thích, bảo mật và vận hành.
- Cách kiểm tra thay đổi đã tạo giá trị.

Ưu tiên thay đổi có ranh giới rõ và có thể triển khai từng bước. Không thiết kế lại toàn hệ thống chỉ để giải quyết một test riêng lẻ nếu có cách nhỏ hơn.

### Bước 5: Xếp ưu tiên và thống nhất chủ sở hữu

Đối chiếu lợi ích, rủi ro, chi phí và mức bất định. Giao chủ sở hữu sản phẩm hoặc kỹ thuật phù hợp. Nếu thay đổi ảnh hưởng nhiều dịch vụ, cần xác định người điều phối và consumer cần tham gia review.

### Bước 6: Xác minh trước và sau cải tiến

Ghi baseline trước khi sửa:

- Thời gian setup, chạy, xác minh và chẩn đoán.
- Tỷ lệ timeout hoặc flaky.
- Số thao tác thủ công.
- Số nguồn dữ liệu cần đối chiếu.
- Khả năng tái hiện lỗi.

Sau thay đổi, chạy cùng bộ kiểm tra trong điều kiện tương đương. Đo lại và xác minh rằng sản phẩm vẫn đáp ứng yêu cầu chức năng, bảo mật và vận hành.

### Bước 7: Cập nhật chuẩn và tái sử dụng

Nếu cải tiến giải quyết vấn đề chung, cập nhật helper, test template, hướng dẫn kiến trúc hoặc tiêu chí review. Theo dõi việc sử dụng và các ngoại lệ để tránh tạo ra một cơ chế mới chỉ một nhóm biết cách dùng.

## 7. Ví dụ: giảm chi phí kiểm tra luồng xử lý đơn hàng bất đồng bộ

Giả sử người dùng tạo đơn hàng. API lưu đơn vào database, phát sự kiện vào queue, worker kiểm tra tồn kho và gửi yêu cầu đến dịch vụ thanh toán sandbox. Giao diện hiển thị trạng thái đơn.

### Hiện trạng và chi phí

Nhóm E2E hiện phải:

1. Tạo tài khoản và sản phẩm bằng script riêng.
2. Gửi request tạo đơn.
3. Chờ 45 giây vì không biết worker đã xử lý xong chưa.
4. Truy vấn nhiều bảng để suy ra đơn đã thanh toán hay chưa.
5. Tìm log của API và worker theo timestamp.
6. Dọn đơn, message và giao dịch sandbox thủ công khi test fail.

Các vấn đề lặp lại gồm timeout không giải thích được, test phụ thuộc dữ liệu dùng chung và khó phân biệt callback chậm với worker không chạy.

### Phân tích nguyên nhân

- API chỉ trả mã tiếp nhận, không trả định danh tác vụ ổn định.
- Không có API trạng thái đơn đủ thông tin để xác minh.
- Correlation ID không được truyền qua message.
- Logic gọi nhà cung cấp thanh toán được tạo trực tiếp trong handler.
- Dữ liệu test không có namespace theo run.

Các vấn đề này bắt nguồn một phần từ thiết kế ranh giới và trạng thái của sản phẩm.

### Các đề xuất cải tiến

| Đề xuất | Lợi ích | Chi phí hoặc rủi ro cần xem xét |
|---|---|---|
| Trả order ID và trạng thái tiếp nhận rõ ràng | Test biết tài nguyên cần theo dõi | Cần giữ hợp đồng API tương thích |
| Cung cấp API đọc trạng thái đơn theo quyền | Không phải suy luận từ nhiều bảng | Phải xác định nguồn có thẩm quyền và tránh lộ dữ liệu |
| Truyền correlation ID qua outbox, queue và worker | Nối log/trace xuyên luồng | Cần chuẩn hóa propagation và chính sách lưu |
| Tách payment adapter và cấu hình sandbox | Điều khiển phản hồi phụ thuộc | Cần bảo vệ cấu hình và bí mật |
| Hỗ trợ idempotency key | Chạy lại request an toàn | Phải định nghĩa phạm vi và thời hạn khóa |
| Namespace dữ liệu theo run ID | Chạy song song và cleanup chính xác | Cần giới hạn quyền tạo và xóa tài nguyên |

### Đo kết quả sau cải tiến

Nhóm chạy lại cùng hành trình và so sánh:

- Thời gian chờ cố định được thay bằng chờ trạng thái có timeout.
- Số bước truy vấn database nội bộ giảm.
- Tỷ lệ test timeout và flaky giảm.
- Thời gian từ fail đến xác định thành phần lỗi giảm.
- Hai run song song không ghi đè dữ liệu.
- Tác dụng phụ thanh toán vẫn được xác minh qua sandbox.
- API và log không làm lộ dữ liệu hoặc quyền vượt phạm vi.

Không giả định mọi cải tiến đều phải triển khai cùng lúc. Có thể bắt đầu với trạng thái và correlation ID vì chúng giúp cả kiểm thử lẫn vận hành, sau đó xử lý adapter và namespace dữ liệu theo mức ưu tiên.

## 8. Đảm bảo cải tiến không làm suy giảm sản phẩm

### Bảo vệ hợp đồng và trải nghiệm người dùng

Một API trạng thái mới cần được thiết kế theo quyền và nhu cầu thực tế. Không trả toàn bộ trạng thái nội bộ hoặc thông tin nhạy cảm chỉ để test dễ đọc. Hãy cung cấp trạng thái nghiệp vụ ổn định, tài liệu rõ và xử lý lỗi nhất quán.

Nếu thay đổi hợp đồng hiện có, cần đánh giá consumer, phiên bản, tương thích ngược và lộ trình chuyển đổi. Không để testability trở thành lý do phá vỡ tích hợp đang hoạt động.

### Giới hạn test hook và cấu hình đặc biệt

Test hook có thể giúp tạo trạng thái lỗi, giả lập thời gian hoặc kiểm tra tác dụng phụ. Cần bảo đảm:

- Chỉ khả dụng trong môi trường hoặc vai trò được phép.
- Không tạo đường bỏ qua xác thực hoặc phân quyền.
- Không thể vô tình kích hoạt trên production.
- Có log/audit cho thao tác quản trị nhạy cảm.
- Có giới hạn dữ liệu và phạm vi tài nguyên.
- Được review bảo mật và có người sở hữu.

Khi có thể, ưu tiên thiết kế dependency injection và adapter ở ranh giới thay vì thêm endpoint đặc quyền chỉ để phục vụ test.

### Đánh giá hiệu năng và vận hành

Log, trace và trạng thái bổ sung có thể tăng dung lượng hoặc độ trễ. Hãy chọn mức chi tiết phù hợp:

- Dùng sampling cho trace khi tải lớn.
- Giữ metric có cardinality được kiểm soát.
- Tránh đưa ID duy nhất vào label metric không giới hạn.
- Đặt retention cho log và sự kiện.
- Không ghi payload nhạy cảm.
- Đo overhead trước và sau thay đổi.

Một cải tiến có giá trị khi lợi ích về kiểm thử và vận hành lớn hơn chi phí duy trì, đồng thời đáp ứng yêu cầu bảo mật và hiệu năng.

## 9. Đo lường hiệu quả của cải tiến khả năng kiểm thử

### Đo chi phí trước và sau

Nên theo dõi một số chỉ số có thể so sánh:

| Chỉ số | Cách đo | Ý nghĩa |
|---|---|---|
| Thời gian chuẩn bị | Từ setup đến khi test sẵn sàng | Đo độ phức tạp tạo trạng thái |
| Thời gian xác minh | Từ hành động đến khi có oracle đáng tin | Đo khả năng quan sát kết quả |
| Thời gian chẩn đoán | Từ test fail đến khi xác định nguyên nhân | Đo khả năng truy vết |
| Tỷ lệ flaky | Số lần chạy cho kết quả không nhất quán trên tổng lần chạy tương đương | Đo độ tin cậy của suite |
| Số thao tác thủ công | Số bước cần người hỗ trợ ngoài pipeline | Đo mức tự phục vụ |
| Phạm vi tái sử dụng | Số test hoặc nhóm dùng được cơ chế mới | Đo lợi ích lan tỏa |
| Chi phí bảo trì | Thời gian sửa test do thay đổi không ảnh hưởng hợp đồng | Đo độ ổn định của ranh giới |

Định nghĩa cách đo nhất quán. Ví dụ, thời gian chẩn đoán nên tính đến lúc có phân loại nguyên nhân có thể hành động, không chỉ thời điểm mở log.

### Kết hợp số liệu với phản hồi định tính

Số liệu không cho biết mọi khía cạnh. Hãy hỏi người viết test, người phát triển và vận hành:

- Có còn cần truy cập database trực tiếp để xác minh không?
- Khi test fail, có biết bước nào và thành phần nào gây lỗi không?
- Có thể tạo lại điều kiện lỗi mà không nhờ người khác không?
- Test có chạy song song an toàn không?
- Hợp đồng quan sát có ổn định khi cấu trúc nội bộ thay đổi không?
- Cơ chế mới có gây thêm gánh nặng vận hành không?

Phản hồi cần được gắn với ví dụ cụ thể để xác định hành động tiếp theo.

### Tránh tối ưu sai chỉ số

Không nên:

- Giảm thời gian test bằng cách bỏ assertion quan trọng.
- Tăng log vô hạn để giảm thời gian điều tra.
- Công khai trạng thái nội bộ hoặc endpoint quản trị không cần thiết.
- Thêm test hook chỉ phục vụ một bài test khó bảo trì.
- Đo số lượng test có thể truy cập API nội bộ như chỉ số testability.
- Xem giảm flaky là thành công nếu test đã bị bỏ qua hoặc cách ly vô thời hạn.

Mục tiêu là giảm chi phí tạo bằng chứng đáng tin cậy trong khi vẫn giữ yêu cầu sản phẩm.

## 10. Quản trị danh mục cải tiến

### Ghi nhận đề xuất có thể xem xét

Một đề xuất nên nêu:

1. Hành trình hoặc nhóm kiểm thử bị ảnh hưởng.
2. Triệu chứng và chi phí đang phát sinh.
3. Bằng chứng xác nhận nguyên nhân thiết kế.
4. Thay đổi sản phẩm dự kiến và hợp đồng liên quan.
5. Lợi ích cho kiểm thử, vận hành và người dùng.
6. Chi phí, phụ thuộc và rủi ro thay đổi.
7. Phương án thay thế ở tầng test hoặc môi trường.
8. Cách đo trước/sau và tiêu chí hoàn tất.
9. Chủ sở hữu, người review và thời hạn.

Điều này giúp nhóm so sánh các đề xuất dựa trên giá trị thay vì mức độ khó chịu của một lần test.

### Ưu tiên theo phạm vi ảnh hưởng

Một cải tiến nên được ưu tiên khi:

- Nguyên nhân thiết kế đã được xác nhận.
- Vấn đề lặp lại ở nhiều test hoặc hành trình.
- Rủi ro sản phẩm có thể được phát hiện sớm hơn.
- Cải tiến giúp nhiều nhóm hoặc cả vận hành.
- Có thể triển khai theo bước với rủi ro kiểm soát được.
- Có cách đo hiệu quả rõ ràng.

Một vấn đề chỉ xuất hiện ở một test đơn lẻ có thể phù hợp để sửa test trước. Một thiếu sót như không có trạng thái job hoặc correlation ID xuyên hệ thống thường có phạm vi ảnh hưởng lớn hơn.

### Theo dõi ngoại lệ và nợ testability

Nếu chưa thể cải tiến, ghi nhận nợ khả năng kiểm thử với:

- Mô tả giới hạn.
- Test hoặc hành trình bị ảnh hưởng.
- Chi phí lặp lại và rủi ro.
- Biện pháp tạm thời.
- Người sở hữu.
- Mốc đánh giá lại.

Biện pháp tạm thời có thể là polling, test double hoặc thao tác thủ công được kiểm soát. Cần tránh để giải pháp tạm thời trở thành quy trình lâu dài mà không có đánh giá.

## 11. Những sai lầm thường gặp

- **Đổ mọi lỗi flaky cho thiết kế sản phẩm:** có thể nguyên nhân nằm ở assertion, dữ liệu hoặc pipeline.
- **Thêm log mà không có cấu trúc:** tăng dung lượng nhưng không giúp truy vết.
- **Dùng API nội bộ làm oracle lâu dài:** test phụ thuộc chi tiết triển khai dễ thay đổi.
- **Thêm endpoint đặc quyền thiếu kiểm soát:** tạo rủi ro bảo mật để giảm công sức kiểm thử.
- **Coi mọi thao tác thủ công là lỗi kiến trúc:** một số bước cần kiểm soát hoặc phê duyệt có chủ đích.
- **Cải tiến quá rộng:** tăng chi phí và rủi ro mà không giải quyết nguyên nhân ưu tiên.
- **Không đo baseline:** không chứng minh được thay đổi đã giảm chi phí.
- **Chỉ đo thời gian chạy:** bỏ qua setup, chẩn đoán, cleanup và bảo trì.
- **Mock mọi phụ thuộc:** làm test nhanh nhưng không tạo bằng chứng cho tích hợp thật.
- **Không xét tương thích ngược:** thay đổi hợp đồng làm hỏng consumer hiện có.
- **Bỏ qua chi phí vận hành:** log, trace và trạng thái bổ sung có thể tạo tải đáng kể.
- **Không giao chủ sở hữu:** đề xuất được ghi nhận nhưng không chuyển thành cải tiến.

## 12. Đầu ra cần có trước khi chốt ưu tiên cải tiến

Một quyết định ưu tiên cải tiến nên có:

1. **Hành trình hoặc vùng kiểm thử:** phạm vi, người dùng, thành phần và rủi ro liên quan.
2. **Bằng chứng chi phí:** thời gian setup, thực thi, xác minh, chẩn đoán, cleanup và bảo trì.
3. **Phân tích nguyên nhân:** phần thuộc test, dữ liệu, môi trường, phụ thuộc hay thiết kế sản phẩm.
4. **Bản đồ quan sát và điều khiển:** trạng thái, nguồn dữ liệu, phụ thuộc và điểm tạo lỗi.
5. **Đề xuất thay đổi:** hợp đồng, ranh giới, trạng thái hoặc tín hiệu sẽ được cải thiện.
6. **Lợi ích dự kiến:** giảm chi phí, tăng độ tin cậy, khả năng tái sử dụng và giá trị vận hành.
7. **Chi phí và rủi ro:** tương thích, bảo mật, hiệu năng, triển khai và duy trì.
8. **Thứ tự ưu tiên:** căn cứ, mức bất định, phụ thuộc và người ra quyết định.
9. **Kế hoạch xác minh:** baseline, kiểm tra sau thay đổi và tiêu chí hoàn tất.
10. **Chủ sở hữu và theo dõi:** người thực hiện, người review, thời hạn và cách quản lý ngoại lệ.

Trước khi chốt, hãy rà soát:

- Chi phí kiểm tra có lặp lại và được đo bằng dữ liệu không?
- Nguyên nhân có thực sự nằm ở thiết kế sản phẩm không?
- Đã xem xét giải pháp ở tầng test và môi trường chưa?
- Cải tiến có làm hành vi quan trọng dễ quan sát hoặc điều khiển hơn không?
- Hợp đồng mới có ổn định, an toàn và hữu ích cho người dùng hoặc vận hành không?
- Có tránh lộ dữ liệu, mở quyền hoặc tạo test hook nguy hiểm không?
- Lợi ích có tương xứng với chi phí và rủi ro thay đổi không?
- Có baseline và tiêu chí đo sau cải tiến không?
- Có chủ sở hữu và kế hoạch duy trì không?

Ưu tiên cải tiến sản phẩm khi chi phí kiểm tra bắt nguồn từ thiết kế khó quan sát giúp nhóm xử lý nguyên nhân lặp lại thay vì liên tục bù đắp bằng thao tác thủ công và test phức tạp. Hãy dựa vào bằng chứng, chọn thay đổi có phạm vi và lợi ích rõ, rồi đo lại khả năng tạo, quan sát và chẩn đoán kết quả. Nhờ đó, khả năng kiểm thử trở thành một thuộc tính được thiết kế và duy trì cùng chất lượng sản phẩm.

