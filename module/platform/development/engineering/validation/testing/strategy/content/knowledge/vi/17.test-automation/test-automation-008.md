# Đặt yêu cầu về tính xác định, độc lập và khả năng chẩn đoán

Một bộ kiểm thử tự động chỉ tạo được niềm tin khi kết quả của nó có thể lặp lại, các bài kiểm thử không làm sai lệch lẫn nhau và khi thất bại, nhóm có thể nhanh chóng hiểu điều gì đã xảy ra. Một bài kiểm thử lúc xanh lúc đỏ dù mã nguồn không đổi làm giảm độ tin cậy của pipeline. Một bài chỉ chạy được sau khi bài khác tạo dữ liệu khiến kết quả phụ thuộc thứ tự. Một thông báo lỗi chung chung không kèm ngữ cảnh khiến người phát triển mất nhiều thời gian tái hiện lỗi.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, yêu cầu đối với tự động hóa kiểm thử cần quy định rõ ba thuộc tính: **tính xác định**, **tính độc lập** và **khả năng chẩn đoán**. Ba thuộc tính này cần được thiết kế ngay từ cấu trúc test, dữ liệu, môi trường và cách chạy trong pipeline. Chúng giúp kết quả kiểm thử có thể lặp lại, mở rộng chạy song song và hỗ trợ xử lý lỗi dựa trên bằng chứng.

## 1. Hiểu ba thuộc tính cốt lõi

### Tính xác định

Tính xác định (determinism) nghĩa là trong cùng điều kiện đầu vào và môi trường được kiểm soát, một bài kiểm thử cho kết quả nhất quán theo tiêu chí đã định. Nếu hành vi sản phẩm thay đổi, bài kiểm thử cần phản ánh thay đổi đó bằng kết quả pass hoặc fail có thể giải thích.

Một bài kiểm thử xác định không có nghĩa mọi lần chạy trong mọi môi trường đều phải cho cùng kết quả bất kể điều kiện. Thay vào đó, các yếu tố có thể ảnh hưởng đến kết quả phải được kiểm soát hoặc ghi nhận. Ví dụ, nếu bài kiểm thử phụ thuộc vào thời gian, cần cố định đồng hồ hoặc dùng khoảng thời gian có tiêu chí rõ ràng; nếu phụ thuộc dữ liệu ngẫu nhiên, cần lưu seed để có thể tái hiện.

### Tính độc lập

Tính độc lập (independence) nghĩa là một bài kiểm thử có thể chạy riêng, chạy lại hoặc chạy song song mà không phụ thuộc vào trạng thái do bài khác tạo ra. Bài kiểm thử phải chuẩn bị dữ liệu và điều kiện cần thiết, đồng thời dọn dẹp hoặc cô lập tác động của chính nó.

Một test suite độc lập không yêu cầu người chạy phải thực hiện theo thứ tự đặc biệt. Việc chạy riêng một test, chạy cả suite hoặc chạy lại sau thất bại không làm thay đổi ý nghĩa của kết quả.

### Khả năng chẩn đoán

Khả năng chẩn đoán (diagnosability) là mức độ dễ dàng xác định nguyên nhân, phạm vi và bước gây thất bại dựa trên thông tin mà bài kiểm thử thu thập. Khi test fail, người đọc cần biết phiên bản nào được kiểm tra, điều kiện nào được dùng, hành động nào đã diễn ra, kết quả thực tế khác kỳ vọng ở đâu và có bằng chứng nào để điều tra.

Khả năng chẩn đoán không chỉ là ghi nhiều log. Log quá nhiều, không có cấu trúc hoặc chứa dữ liệu nhạy cảm có thể làm việc điều tra khó hơn. Cần thu thập đúng ngữ cảnh, có liên kết giữa các thành phần và bảo vệ thông tin.

### Vì sao phải xem xét đồng thời

Ba thuộc tính hỗ trợ lẫn nhau:

| Thuộc tính | Câu hỏi cần trả lời | Nếu thiếu |
|---|---|---|
| Xác định | Chạy lại trong điều kiện tương đương có cho kết quả đáng tin cậy không? | Test chập chờn, khó phân biệt lỗi sản phẩm với nhiễu môi trường |
| Độc lập | Bài test có tự chuẩn bị và kiểm soát trạng thái của nó không? | Kết quả phụ thuộc thứ tự, dữ liệu dùng chung hoặc chạy song song |
| Chẩn đoán | Khi thất bại, có đủ bằng chứng để hiểu và xử lý không? | Tốn thời gian tái hiện, khó phân loại và dễ bỏ qua lỗi |

Một bài kiểm thử có thể xác định nhưng không độc lập: nó luôn pass nếu chạy sau một bài setup cụ thể. Một bài có thể độc lập nhưng khó chẩn đoán: nó tạo dữ liệu riêng nhưng chỉ báo timeout. Một bài có thể có log phong phú nhưng vẫn không xác định vì phụ thuộc thời gian thực và dịch vụ bên ngoài.

## 2. Chuyển ba thuộc tính thành yêu cầu kiểm thử cụ thể

### Viết yêu cầu có thể đánh giá

Không nên chỉ ghi “test phải ổn định”, “test không phụ thuộc nhau” hoặc “log phải đầy đủ”. Mỗi yêu cầu cần mô tả điều kiện, hành vi và bằng chứng để xác minh.

| Thuộc tính | Yêu cầu chưa đủ cụ thể | Yêu cầu có thể đánh giá |
|---|---|---|
| Xác định | Test phải chạy ổn định | Với cùng phiên bản, fixture và cấu hình đã ghi nhận, chạy lặp lại theo số lần quy định phải cho cùng kết quả; mọi seed và nguồn thời gian phải có thể kiểm soát |
| Độc lập | Test không được phụ thuộc test khác | Mỗi test có thể chạy riêng và theo thứ tự bất kỳ; dữ liệu tạo ra được namespace theo run/test ID và không đọc trạng thái do test khác tạo |
| Chẩn đoán | Khi fail phải có log | Báo cáo thất bại phải chứa tên test, bước lỗi, expected/actual, phiên bản, môi trường, run ID, correlation ID và liên kết đến log/trace phù hợp |

Mức chi tiết phụ thuộc loại test. Một unit test thuần có thể không cần ảnh chụp giao diện hoặc trace phân tán. Một E2E đi qua nhiều dịch vụ cần nhiều ngữ cảnh hơn.

### Xác định phạm vi áp dụng

Áp dụng yêu cầu theo cấp kiểm thử:

- **Unit test:** kiểm soát đầu vào, đồng hồ, seed và trạng thái; lỗi cần chỉ rõ điều kiện hoặc nhánh logic.
- **Component và integration test:** cô lập database, cache, broker và phụ thuộc; ghi nhận phiên bản dịch vụ và cấu hình.
- **System và E2E:** kiểm soát danh tính, dữ liệu, môi trường, tác dụng phụ, thời gian chờ và correlation ID.
- **Performance hoặc resilience test:** lưu cấu hình tải, seed, thời điểm, số worker, phiên bản hạ tầng và baseline để so sánh.
- **Acceptance test:** ghi nhận vai trò người đánh giá, tiêu chí, dữ liệu đại diện và bằng chứng quyết định.

Không áp dụng một mẫu thu thập giống nhau cho mọi cấp. Mục tiêu là đủ bằng chứng cho rủi ro và phạm vi của từng loại test.

### Xác định tiêu chí chất lượng cho test suite

Có thể đưa các tiêu chí sau vào chuẩn nhóm:

1. Mọi test có tên và mục tiêu rõ ràng.
2. Mọi test có thể chạy độc lập hoặc khai báo phụ thuộc được quản lý rõ.
3. Dữ liệu và tài nguyên do test tạo có cách cô lập và dọn dẹp.
4. Nguồn gây biến thiên được kiểm soát hoặc ghi lại.
5. Chờ bất đồng bộ dựa trên điều kiện và có thời hạn.
6. Assertion kiểm tra kết quả nghiệp vụ có ý nghĩa.
7. Thất bại có thông tin đủ để phân loại và tái hiện.
8. Retry không che giấu lỗi hoặc biến một lần fail thành pass không có giải thích.
9. Test có chủ sở hữu và quy trình xử lý khi không ổn định.
10. Các ngoại lệ với chuẩn chung có lý do và thời hạn xem xét.

## 3. Thiết kế tính xác định cho bài kiểm thử

### Kiểm soát thời gian

Thời gian thực là nguồn gây biến thiên phổ biến. Test có thể thất bại quanh ranh giới ngày, giờ, hết hạn hoặc lịch chạy.

Các yêu cầu nên xem xét:

- Dùng clock có thể giả lập hoặc cố định cho logic phụ thuộc thời gian.
- Truyền thời điểm tham chiếu vào hàm thay vì gọi đồng hồ hệ thống ở nhiều nơi.
- Xác định timezone và cách xử lý giờ mùa hè nếu liên quan.
- Tránh assertion dựa trên thời điểm chính xác đến mili giây nếu yêu cầu không cần độ chính xác đó.
- Với token, cache hoặc job có TTL, điều khiển clock hoặc chờ theo điều kiện có giới hạn.
- Ghi thời điểm bắt đầu, kết thúc và timezone trong báo cáo khi thời gian có ảnh hưởng.

Ví dụ, kiểm thử hạn sử dụng mã xác minh nên cố định thời điểm hiện tại rồi kiểm tra ngay trước, đúng tại và sau ngưỡng hết hạn. Không phụ thuộc vào việc test chạy nhanh hay chậm trên máy CI.

### Kiểm soát dữ liệu ngẫu nhiên

Dữ liệu ngẫu nhiên hữu ích để mở rộng miền đầu vào, tìm lỗi bất thường hoặc kiểm tra property-based. Tuy nhiên, mỗi lần chạy cần có thể tái hiện.

- Dùng seed xác định cho generator.
- Ghi seed và phiên bản generator khi test fail.
- Lưu hoặc tái tạo chính xác đầu vào gây lỗi.
- Phân biệt fuzzing liên tục với test hồi quy có seed cố định.
- Khi phát hiện lỗi từ seed ngẫu nhiên, thêm trường hợp tối giản vào bộ hồi quy.
- Không dùng giá trị ngẫu nhiên làm ID nếu không có cách truy vết và dọn dẹp.

Ví dụ, một test sinh 500 giỏ hàng ngẫu nhiên nên in hoặc đính kèm seed, số vòng lặp và dữ liệu thu nhỏ khi phát hiện tổng tiền âm. Nếu không có seed, lỗi có thể biến mất ở lần chạy sau.

### Kiểm soát mạng và dịch vụ bên ngoài

Mạng và dịch vụ bên ngoài có thể chậm, gián đoạn hoặc thay đổi dữ liệu. Chọn phương pháp theo mục tiêu:

- Unit test dùng stub hoặc fake để kiểm tra logic phản ứng.
- Contract test xác minh schema và kỳ vọng giữa hai phía.
- Integration test dùng sandbox hoặc dịch vụ thật trong phạm vi kiểm soát.
- E2E có thể dùng sandbox cho tác dụng phụ như thanh toán hoặc email.
- Synthetic test định kỳ cần tài khoản và dữ liệu riêng.

Không giả lập phụ thuộc khi mục tiêu chính là kiểm tra chính phụ thuộc đó. Ví dụ, mock broker không chứng minh broker thật giữ thứ tự hoặc xác nhận message đúng. Hãy ghi rõ phần nào dùng test double và phần nào được xác minh với thành phần thật.

### Kiểm soát tính bất đồng bộ

Không dùng khoảng ngủ cố định làm cơ chế đồng bộ chính. Thay vào đó, chờ điều kiện có ý nghĩa với thời hạn rõ ràng:

- Chờ job chuyển sang trạng thái hoàn tất.
- Chờ event xuất hiện với đúng ID.
- Chờ dữ liệu hội tụ trong khoảng nhất quán được chấp nhận.
- Chờ consumer xử lý message và xác minh tác dụng phụ.
- Chờ UI phản ánh trạng thái từ nguồn có thẩm quyền.

Mỗi lần chờ cần có timeout, tần suất polling phù hợp và thông tin trạng thái cuối khi hết hạn. Timeout phải phản ánh giới hạn dịch vụ và môi trường; không tăng vô hạn để làm test pass.

### Kiểm soát thứ tự và đồng thời

Một bài test có thể phụ thuộc vào thứ tự thực thi hoặc cạnh tranh tài nguyên. Để phát hiện:

- Chạy từng test riêng.
- Chạy suite theo thứ tự đảo ngược hoặc ngẫu nhiên có seed.
- Chạy lại test nhiều lần.
- Chạy song song với mức concurrency dự kiến.
- Tạo tranh chấp có chủ đích cho các bài kiểm thử đồng thời.
- Xác minh lock, transaction, idempotency và dữ liệu cuối.

Không loại bỏ nondeterminism thật của sản phẩm bằng cách làm test tuần tự nếu mục tiêu cần xác minh hành vi đồng thời. Cần phân biệt nhiễu do test harness với race condition thực tế.

## 4. Loại bỏ các nguồn gây kết quả chập chờn

### Nguồn gây biến thiên thường gặp

| Nguồn | Biểu hiện | Biện pháp |
|---|---|---|
| Đồng hồ hệ thống | Test hết hạn thất thường hoặc sai ngày | Clock giả lập, timezone cố định |
| Dữ liệu dùng chung | Test pass khi chạy riêng nhưng fail trong suite | Fixture và namespace riêng |
| Mạng | Timeout ngẫu nhiên, dịch vụ sandbox không ổn định | Giới hạn timeout, retry có kiểm soát, test double đúng mục tiêu |
| Thứ tự thực thi | Test phụ thuộc kết quả bài trước | Setup tự chứa và chạy đảo thứ tự |
| Đồng thời | Race condition, khóa hoặc cập nhật đè | Dữ liệu riêng, đồng bộ rõ, kiểm thử cạnh tranh có chủ đích |
| Animation hoặc giao diện | Click trước khi phần tử sẵn sàng | Chờ trạng thái hiển thị và tương tác được |
| Tài nguyên máy chạy | Test chậm khi CI bận | Giới hạn tải, đo tài nguyên và phân vùng suite |
| Locale và timezone | Sắp xếp hoặc định dạng khác nhau | Cố định locale/timezone hoặc kiểm tra theo hợp đồng |
| Phiên bản phụ thuộc | Hành vi khác giữa máy cá nhân và CI | Khóa phiên bản, ghi nhận image và cấu hình |
| Thứ tự dữ liệu | Kết quả truy vấn không ổn định | Sắp xếp rõ ràng khi thứ tự là một phần của yêu cầu |

### Tránh assertion quá chặt

Assertion cần kiểm tra điều kiện nghiệp vụ, không nên ràng buộc chi tiết không thuộc hợp đồng. Ví dụ:

- Không so sánh timestamp chính xác đến từng mili giây nếu chỉ cần nằm trong khoảng.
- Không phụ thuộc thứ tự danh sách nếu API không cam kết thứ tự.
- Không so sánh toàn bộ thông điệp lỗi có chứa đường dẫn hoặc ID biến thiên nếu mã lỗi và nội dung cốt lõi mới là hợp đồng.
- Không yêu cầu một ID sinh tự động phải giống nhau giữa các lần chạy.
- Không dùng snapshot quá rộng khiến thay đổi vô hại tạo ra hàng loạt lỗi.

Assertion quá lỏng cũng nguy hiểm. “Có ít nhất một bản ghi” không đủ nếu nghiệp vụ yêu cầu đúng một bản ghi cho một giao dịch. Chọn mức kiểm tra tương ứng với hợp đồng.

### Không dùng retry để che lỗi

Retry có thể phù hợp với lỗi tạm thời được xác định, nhưng retry toàn bộ test cho đến khi pass làm mất thông tin quan trọng. Cần quy định:

- Retry chỉ áp dụng cho lỗi nào và ở tầng nào.
- Số lần tối đa và khoảng chờ.
- Kết quả lần đầu và các lần tiếp theo được lưu riêng.
- Test pass sau retry có được đánh dấu flaky hay không.
- Ai điều tra và thời hạn loại bỏ nguyên nhân.
- Có rủi ro tác dụng phụ khi chạy lại không.

Nếu một E2E thanh toán fail lần đầu rồi pass lần hai, báo cáo cần giữ cả hai kết quả. Không được chỉ ghi pass cuối cùng và bỏ mất dấu hiệu bất ổn.

## 5. Thiết kế tính độc lập giữa các bài kiểm thử

### Mỗi test tự chuẩn bị điều kiện cần

Một test nên tự tạo hoặc yêu cầu fixture rõ ràng cho mọi dữ liệu mà nó cần. Mẫu Arrange–Act–Assert giúp phân tách:

- **Arrange:** tạo danh tính, dữ liệu, quyền, cấu hình và trạng thái ban đầu.
- **Act:** thực hiện hành động đang kiểm tra.
- **Assert:** xác minh kết quả và tác dụng phụ.
- **Cleanup:** thu hồi hoặc xóa tài nguyên thuộc test khi phù hợp.

Không nên dựa vào dữ liệu do test khác tạo mà không khai báo quan hệ. Nếu một quy trình nhiều bước cần giữ trạng thái giữa các bước, hãy tổ chức nó thành một kịch bản có chủ đích hoặc fixture có vòng đời rõ ràng.

### Cô lập dữ liệu theo lần chạy và test

Có thể dùng run ID, test ID, tenant riêng hoặc namespace để tránh va chạm. Ví dụ:

- Email thử nghiệm có hậu tố riêng cho mỗi run.
- Tên tenant và tài nguyên có prefix của test.
- Cache key dùng namespace riêng.
- Queue hoặc consumer group được phân tách theo suite khi hạ tầng cho phép.
- File upload được lưu trong thư mục hoặc bucket dành riêng.
- Bản ghi có marker để cleanup tìm đúng tài nguyên.

ID phải đủ duy nhất để chạy song song nhưng vẫn có thể truy vết. Tránh ghi thông tin bí mật hoặc dữ liệu cá nhân vào ID.

### Tránh trạng thái toàn cục có thể thay đổi

Các biến toàn cục, singleton hoặc dữ liệu dùng chung có thể khiến test ảnh hưởng lẫn nhau. Cần chú ý:

- Cấu hình thay đổi trong một test phải được khôi phục.
- Fake clock phải được reset sau mỗi test.
- Mock hoặc spy phải được xóa trạng thái giữa các test.
- Bộ nhớ đệm cục bộ phải được làm mới hoặc cô lập.
- Biến môi trường phải được đặt trong phạm vi rõ và phục hồi sau khi dùng.
- Listener, thread, socket và background task phải được đóng.

Một test thất bại giữa chừng không được để lại trạng thái khiến test tiếp theo thất bại theo cách khó hiểu.

### Bảo đảm an toàn khi chạy song song

Chạy song song giúp giảm thời gian pipeline nhưng làm lộ vấn đề chia sẻ tài nguyên. Hãy xác định:

- Những tài nguyên nào được chia sẻ?
- Có khóa hoặc namespace đủ để tránh va chạm không?
- Mỗi test có thể tạo và dọn dữ liệu độc lập không?
- Database pool, broker quota và giới hạn sandbox có đủ không?
- Test có thể gửi tác dụng phụ đến cùng một người nhận không?
- Thứ tự cleanup có ảnh hưởng đến test đang chạy không?

Nếu một nhóm test chưa an toàn khi chạy song song, có thể tạm giới hạn concurrency cho đúng nhóm đó, ghi rõ lý do và kế hoạch khắc phục. Không tuần tự hóa toàn bộ suite vô thời hạn chỉ để che giấu lỗi cô lập.

### Cleanup phải có tính an toàn và có thể lặp lại

Cleanup nên chỉ tác động đến tài nguyên thuộc test hiện tại. Thiết kế cleanup để:

- Chạy được nhiều lần mà không gây lỗi ngoài ý muốn.
- Hoạt động cả khi một phần setup thất bại.
- Không xóa dữ liệu dùng chung hoặc của người dùng thật.
- Có thể phát hiện tài nguyên còn sót.
- Ghi nhận lỗi cleanup riêng với lỗi kiểm thử chính.

Trong môi trường có dữ liệu quan trọng, dùng tài khoản và namespace riêng, xác định chủ sở hữu và giới hạn quyền xóa.

## 6. Thiết kế khả năng chẩn đoán

### Assertion phải cho biết điều gì sai

Thông báo lỗi nên chỉ ra giá trị mong đợi, giá trị thực tế và ngữ cảnh. Ví dụ:

- Kém: thông báo chung “assertion failed”.
- Tốt hơn: “Đơn hàng ORD-... kỳ vọng trạng thái PAID nhưng nhận PROCESSING sau 30 giây; run_id=...; correlation_id=...”.

Không đưa token, mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân vào thông báo. Có thể che giấu hoặc rút gọn định danh khi cần.

### Thu thập ngữ cảnh của lần chạy

Mỗi lần chạy nên có metadata tối thiểu:

- Run ID và test ID.
- Tên suite, tên test và phiên bản test.
- Commit, build hoặc image đang kiểm tra.
- Môi trường, vùng và cấu hình liên quan.
- Thời điểm bắt đầu, kết thúc và timezone.
- Seed, fixture ID và danh tính thử nghiệm khi có liên quan.
- Số lần retry và kết quả từng lần.
- Người hoặc pipeline khởi chạy.

Metadata này giúp so sánh giữa máy cá nhân, CI, staging và các lần chạy khác nhau.

### Liên kết log, metric và trace

Với test đi qua nhiều dịch vụ, dùng correlation ID hoặc trace ID để nối request và sự kiện. Báo cáo nên liên kết đến:

- Log của ứng dụng và dịch vụ phụ thuộc.
- Trace phân tán theo hành trình.
- Metric về độ trễ, lỗi, queue backlog hoặc tài nguyên.
- Request/response đã loại bỏ dữ liệu nhạy cảm.
- Audit event và trạng thái dữ liệu có thẩm quyền.
- Screenshot, video hoặc DOM snapshot khi test giao diện cần bằng chứng đó.

Không cần đính kèm mọi log của toàn hệ thống cho mọi test. Thu thập quanh khoảng thời gian và tài nguyên liên quan, đồng thời giới hạn kích thước và thời gian lưu.

### Ghi lại trạng thái khi test thất bại

Với lỗi bất đồng bộ hoặc E2E, trạng thái cuối thường quan trọng hơn stack trace đơn lẻ. Khi timeout, nên ghi:

- Điều kiện đang chờ.
- Thời hạn đã cấu hình và thời gian đã chờ.
- Giá trị hoặc trạng thái cuối quan sát được.
- Số lần polling hoặc retry.
- Correlation ID và tài nguyên liên quan.
- Các bước đã hoàn thành trước khi timeout.

Điều này giúp phân biệt worker chưa chạy, worker đã chạy nhưng chưa commit, callback bị mất hay giao diện chưa cập nhật.

### Phân loại lỗi theo nguyên nhân có thể hành động

Có thể phân loại thất bại thành:

- Lỗi sản phẩm: hành vi thực tế vi phạm yêu cầu.
- Lỗi test: assertion sai, fixture lỗi hoặc test harness có lỗi.
- Lỗi môi trường: dịch vụ, cấu hình hoặc tài nguyên kiểm thử không sẵn sàng.
- Lỗi phụ thuộc: nhà cung cấp hoặc hệ thống bên ngoài gặp sự cố.
- Flaky: kết quả thay đổi giữa các lần chạy trong điều kiện được cho là tương đương.
- Bị chặn: thiếu quyền, dữ liệu hoặc điều kiện để thực hiện.
- Lỗi cleanup: tài nguyên không được dọn theo kế hoạch.

Phân loại ban đầu có thể cần điều chỉnh sau điều tra. Không tự động gán mọi timeout thành lỗi môi trường; timeout có thể là lỗi hiệu năng của sản phẩm.

## 7. Xây dựng quy trình chạy có thể tái hiện

### Chuẩn hóa môi trường

Để so sánh kết quả, cần ghi nhận và kiểm soát:

- Phiên bản runtime, trình duyệt, driver và thư viện.
- Image hoặc phiên bản database, cache, broker và dịch vụ phụ thuộc.
- Locale, timezone và biến môi trường liên quan.
- Cấu hình feature flag và quyền.
- Dữ liệu seed hoặc fixture.
- Tài nguyên máy chạy và mức concurrency.

Không phải lúc nào cũng cần môi trường giống hệt production. Nhưng mọi khác biệt có thể ảnh hưởng kết luận phải được ghi lại.

### Lưu cấu hình và đầu vào gây lỗi

Khi test fail, lưu những thông tin cần thiết để tái hiện:

- Seed và dữ liệu đầu vào.
- Cấu hình runtime và phiên bản phụ thuộc.
- Các bước thực hiện và thứ tự sự kiện.
- Mốc thời gian hoặc clock giả lập.
- Request/response đã khử dữ liệu nhạy cảm.
- Tệp hoặc trạng thái fixture có liên quan.

Với property-based testing, có thể thu nhỏ đầu vào thất bại để tạo trường hợp hồi quy dễ đọc. Với test giao diện, lưu screenshot hoặc video khi có ích, nhưng tránh ghi lại bí mật và dữ liệu người dùng thật.

### Quy định cách chạy lại

Một quy trình chạy lại cần giữ được ngữ cảnh ban đầu. Không chỉ bấm rerun mà không biết test dùng dữ liệu, seed và cấu hình nào.

Hướng dẫn tái hiện nên nêu:

1. Phiên bản hoặc commit.
2. Môi trường và cấu hình.
3. Tên test hoặc bộ lọc test.
4. Fixture hoặc seed.
5. Lệnh chạy tương ứng.
6. Điều kiện phụ thuộc cần khởi động.
7. Cách thu thập cùng loại bằng chứng.

Nếu không thể tái hiện do lỗi phụ thuộc đã biến mất, vẫn giữ báo cáo lần đầu và phân loại là chưa xác định cho đến khi có đủ bằng chứng.

## 8. Quản lý test không ổn định

### Nhận diện flaky test

Một test được xem là flaky khi có thể cho kết quả khác nhau giữa các lần chạy trong điều kiện được cho là tương đương, mà không có thay đổi sản phẩm hoặc đầu vào có chủ đích giải thích sự khác biệt.

Dấu hiệu thường gặp:

- Fail ngẫu nhiên trong CI nhưng pass ở máy cá nhân.
- Pass khi chạy riêng nhưng fail trong suite.
- Fail ở một worker hoặc thời điểm tải cao.
- Chỉ pass sau khi retry.
- Timeout thay đổi dù thời gian xử lý sản phẩm không có thay đổi rõ.
- Phụ thuộc vào thứ tự test hoặc trạng thái còn sót.

Không gắn nhãn flaky chỉ vì nguyên nhân chưa biết. Hãy ghi nhận số lần chạy, điều kiện và tỷ lệ thất bại để hỗ trợ điều tra.

### Quy trình xử lý

Một quy trình thực tế gồm:

1. Giữ nguyên kết quả lần chạy đầu.
2. Thu thập log, trace, seed, fixture và metadata.
3. Chạy lại có kiểm soát để xác định khả năng tái hiện.
4. Phân loại nguyên nhân: sản phẩm, test, môi trường hoặc phụ thuộc.
5. Gán chủ sở hữu và thời hạn xử lý.
6. Nếu cần cách ly, đánh dấu rõ trạng thái và rủi ro bị mất bảo vệ.
7. Thêm trường hợp hồi quy hoặc sửa test sau khi xác định nguyên nhân.
8. Xác minh test ổn định qua các lần chạy và điều kiện liên quan trước khi bỏ cách ly.

Cách ly không có nghĩa xóa test khỏi báo cáo. Báo cáo cần thể hiện test nào đang bị cách ly, vì sao, ai chịu trách nhiệm và khi nào phải xem xét lại.

### Không biến retry thành tiêu chí đạt

Nếu pipeline cho phép retry, cần hiển thị kết quả ban đầu và kết quả sau retry. Một test pass sau retry vẫn là tín hiệu cần điều tra nếu kết quả đầu tiên không được giải thích.

Không dùng tỷ lệ pass sau nhiều lần thử làm chỉ số duy nhất. Cần theo dõi tỷ lệ flaky, số test bị cách ly, tuổi của vấn đề và tác động đến thời gian phản hồi.

## 9. Ví dụ: yêu cầu cho E2E tạo đơn hàng

Giả sử một bài E2E kiểm tra người dùng đăng nhập, thêm sản phẩm vào giỏ, thanh toán sandbox và nhận đơn hàng đã xác nhận. Bài test đi qua giao diện, API, database, queue và dịch vụ thanh toán.

### Yêu cầu về tính xác định

- Tài khoản và tenant được tạo riêng cho mỗi run.
- Giá, thuế, tiền tệ và trạng thái sản phẩm được seed rõ.
- Clock được điều khiển cho thời hạn mã giảm giá hoặc phiên nếu có.
- Nhà cung cấp thanh toán dùng sandbox với phản hồi và trạng thái xác định.
- Event ID và idempotency key được tạo từ run ID.
- Test chờ trạng thái đơn hàng đạt điều kiện cuối trong timeout đã thống nhất.
- Nếu có dữ liệu ngẫu nhiên, seed và đầu vào được ghi lại.

### Yêu cầu về tính độc lập

- Test có thể chạy riêng mà không cần chạy bài đăng nhập hoặc tạo sản phẩm trước.
- Mỗi run có giỏ hàng, đơn hàng và mã tham chiếu riêng.
- Cache key và queue message có thể truy vết theo run ID.
- Cleanup chỉ xóa đơn hàng, dữ liệu và tài nguyên của run đó.
- Hai instance của cùng test có thể chạy song song mà không ghi đè dữ liệu.
- Test không phụ thuộc thứ tự giữa các test thanh toán khác.

### Yêu cầu về khả năng chẩn đoán

Nếu test fail, báo cáo cần có:

- Run ID, commit, môi trường và phiên bản trình duyệt.
- Tài khoản thử nghiệm và tenant đã che giấu định danh nhạy cảm.
- ID giỏ hàng, đơn hàng, giao dịch và event.
- Bước thất bại cùng expected/actual.
- Request/response đã khử bí mật.
- Correlation ID, trace và log dịch vụ.
- Trạng thái database và queue có liên quan.
- Screenshot hoặc video tại thời điểm lỗi nếu lỗi thuộc giao diện.
- Trạng thái cleanup và các tài nguyên còn lại.

### Bảng đánh giá ví dụ

| Tiêu chí | Cách xác minh | Kết quả mong đợi |
|---|---|---|
| Chạy riêng | Chạy test không chạy suite trước | Setup tự tạo đủ dữ liệu và test hoàn tất |
| Chạy lặp | Chạy nhiều lần với cùng fixture hoặc seed | Kết quả nhất quán, không dùng lại dữ liệu cũ |
| Chạy song song | Chạy hai run cùng lúc | Không trùng đơn hàng hoặc tác động chéo |
| Chạy đảo thứ tự | Đảo thứ tự suite | Kết quả không đổi do thứ tự |
| Tái hiện lỗi | Dùng seed và metadata đã lưu | Có thể tái tạo điều kiện thất bại |
| Chẩn đoán timeout | Cố ý làm chậm worker trong môi trường test | Báo cáo chỉ ra trạng thái cuối, timeout và trace |
| Cleanup | Chạy cleanup hai lần | Không xóa tài nguyên ngoài run và không gây lỗi ngoài ý muốn |

Ví dụ này cho thấy ba thuộc tính cần được xác định bằng tiêu chí kiểm tra cụ thể, không chỉ bằng quy ước viết code.

## 10. Đưa yêu cầu vào framework và pipeline

### Tạo chuẩn dùng chung

Nhóm có thể cung cấp các thành phần dùng chung để người viết test không phải tự xây lại:

- Fixture builder và factory dữ liệu.
- Clock giả lập và seedable random generator.
- Hàm chờ theo điều kiện với timeout chuẩn.
- Namespace và tiện ích cleanup.
- Client sandbox hoặc test double có hợp đồng rõ.
- Assertion helper có expected/actual dễ đọc.
- Correlation ID và metadata tự động.
- Thu thập log, trace và artifact khi fail.

Thành phần dùng chung cần có tài liệu, chủ sở hữu và kiểm thử riêng. Một helper lỗi có thể làm hàng loạt test thiếu ổn định hoặc báo sai.

### Phân tầng kiểm tra trong pipeline

Có thể tổ chức pipeline theo vòng phản hồi:

| Vòng | Kiểm tra | Mục tiêu |
|---|---|---|
| Khi phát triển | Unit test và kiểm tra nhanh | Phản hồi sớm, cô lập nguyên nhân |
| Pull request | Unit, component, contract và một số integration test | Ngăn thay đổi phá hợp đồng |
| Sau tích hợp | Integration và E2E trọng yếu | Kiểm tra trạng thái xuyên thành phần |
| Trước phát hành | Bộ hồi quy theo rủi ro, hiệu năng và phục hồi theo phạm vi | Hỗ trợ quyết định phát hành |
| Theo lịch | Kiểm tra lặp, synthetic journey và kiểm tra môi trường | Phát hiện suy giảm theo thời gian |

Vị trí chạy cần cân bằng tốc độ và mức rủi ro. Không phải test nào cũng cần chạy trong mọi vòng, nhưng mọi test quan trọng cần có lịch chạy và người chịu trách nhiệm rõ.

### Đặt cổng chất lượng cho test

Một test mới có thể cần đáp ứng trước khi được đưa vào pipeline chính:

- Có mục tiêu và tiêu chí pass/fail rõ.
- Chạy độc lập hoặc phụ thuộc được khai báo.
- Có dữ liệu riêng và cleanup.
- Không dùng sleep cố định làm đồng bộ chính.
- Có timeout hữu hạn.
- Assertion kiểm tra hành vi có ý nghĩa.
- Khi fail có thông tin chẩn đoán tối thiểu.
- Được chạy lặp và song song ở mức phù hợp.
- Tác dụng phụ được cô lập hoặc dùng sandbox.

Cổng chất lượng không nên biến thành thủ tục nặng cho test nhỏ. Hãy tự động hóa các kiểm tra có thể và yêu cầu review sâu hơn cho E2E hoặc test có tác động lớn.

## 11. Đo lường chất lượng của bộ kiểm thử tự động

### Chọn chỉ số có ý nghĩa

Có thể theo dõi:

- Tỷ lệ test pass ổn định qua các lần chạy.
- Tỷ lệ flaky và số test chỉ pass sau retry.
- Tỷ lệ test có thể chạy độc lập.
- Tỷ lệ test có thể chạy song song an toàn.
- Thời gian trung bình để phân loại nguyên nhân thất bại.
- Thời gian từ phát hiện đến khi sửa test flaky.
- Tỷ lệ thất bại có đủ log, trace và metadata.
- Tỷ lệ test bị cách ly và tuổi của các trường hợp đó.
- Thời gian pipeline và mức tài nguyên sử dụng.
- Tỷ lệ lỗi sản phẩm được phát hiện trước khi phát hành.

Không tối ưu một chỉ số riêng. Giảm thời gian pipeline bằng cách bỏ các test quan trọng có thể làm giảm bảo vệ. Tăng số log không có cấu trúc có thể làm tăng dung lượng mà không cải thiện chẩn đoán.

### Đánh giá chất lượng assertion và bằng chứng

Rà soát định kỳ một mẫu test để hỏi:

- Assertion có kiểm tra đúng hợp đồng không?
- Test có thể pass dù trạng thái nghiệp vụ sai không?
- Test có kiểm tra cả tác dụng phụ cần thiết không?
- Bằng chứng có giúp phân biệt lỗi sản phẩm với lỗi môi trường không?
- Có dữ liệu nhạy cảm trong artifact không?
- Kết quả có thể truy vết đến phiên bản và lần chạy không?

Số lượng test không phản ánh trực tiếp chất lượng. Một suite nhỏ với oracle tốt và độ ổn định cao có thể tạo niềm tin hơn một suite lớn có nhiều kiểm tra trùng lặp.

## 12. Những sai lầm thường gặp

- **Chỉ yêu cầu test chạy xanh:** bỏ qua khả năng tái hiện, độc lập và chẩn đoán.
- **Dùng sleep cố định:** gây chậm hoặc chập chờn khi thời gian xử lý biến động.
- **Dùng dữ liệu chung:** tạo va chạm và phụ thuộc thứ tự.
- **Không ghi seed:** không thể tái hiện lỗi do dữ liệu ngẫu nhiên.
- **Mock mọi phụ thuộc:** bỏ qua hành vi thật của ranh giới tích hợp.
- **Retry cho đến khi pass:** che giấu flaky test và lỗi sản phẩm.
- **Chỉ chạy tuần tự:** che giấu tranh chấp dữ liệu và lỗi an toàn song song.
- **Assertion quá chặt:** test fail vì chi tiết không thuộc hợp đồng.
- **Assertion quá lỏng:** test pass dù kết quả nghiệp vụ sai.
- **Log quá nhiều nhưng thiếu liên kết:** khó tìm sự kiện liên quan và có thể lộ dữ liệu.
- **Không cleanup khi thất bại:** để lại trạng thái làm hỏng lần chạy tiếp.
- **Cách ly test vô thời hạn:** làm mất bảo vệ mà không có kế hoạch sửa.
- **Không giữ kết quả lần chạy đầu:** mất dấu hiệu quan trọng khi test chỉ pass sau retry.
- **Đo số lượng test thay cho giá trị:** tăng bảo trì nhưng không tăng bằng chứng.

## 13. Đầu ra cần có trước khi chốt yêu cầu tự động hóa

Một bộ yêu cầu đủ dùng nên có:

1. **Định nghĩa ba thuộc tính:** tiêu chí xác định, độc lập và chẩn đoán theo từng cấp test.
2. **Chuẩn đầu vào:** phiên bản, môi trường, fixture, seed, clock và cấu hình cần ghi nhận.
3. **Quy tắc dữ liệu:** tạo, namespace, chia sẻ, làm sạch và thời hạn lưu.
4. **Quy tắc phụ thuộc:** khi nào dùng mock, fake, sandbox hoặc thành phần thật.
5. **Quy tắc đồng bộ:** điều kiện chờ, timeout và xử lý tác vụ bất đồng bộ.
6. **Quy tắc thực thi:** chạy riêng, chạy lại, đảo thứ tự và chạy song song.
7. **Chuẩn assertion:** expected/actual, oracle và kiểm tra tác dụng phụ.
8. **Chuẩn chẩn đoán:** metadata, log, trace, artifact và bảo vệ dữ liệu.
9. **Quy trình flaky test:** nhận diện, phân loại, cách ly, chủ sở hữu và thời hạn.
10. **Tích hợp pipeline:** vòng chạy, cổng chất lượng và cách báo cáo retry.
11. **Chỉ số theo dõi:** độ ổn định, khả năng tái hiện, thời gian chẩn đoán và chi phí chạy.
12. **Ngoại lệ được phê duyệt:** lý do, rủi ro, người chịu trách nhiệm và ngày xem xét lại.

Trước khi đưa test vào pipeline chính, hãy rà soát:

- Test có mục tiêu, đầu vào và kết quả mong đợi rõ ràng không?
- Nguồn thời gian, ngẫu nhiên, mạng và bất đồng bộ có được kiểm soát hoặc ghi nhận không?
- Test có thể chạy riêng và theo thứ tự khác nhau không?
- Dữ liệu và tài nguyên có được cô lập khi chạy song song không?
- Setup và cleanup có thể lặp lại và an toàn không?
- Timeout có hữu hạn và cung cấp trạng thái cuối khi thất bại không?
- Assertion có kiểm tra đúng hành vi và tác dụng phụ không?
- Báo cáo có đủ metadata, expected/actual và liên kết log/trace không?
- Retry có giữ lại kết quả lần đầu và không che giấu lỗi không?
- Có chủ sở hữu và thời hạn xử lý test không ổn định không?
- Artifact có bảo vệ dữ liệu nhạy cảm không?

Đặt yêu cầu rõ cho tính xác định, độc lập và khả năng chẩn đoán giúp tự động hóa kiểm thử trở thành nguồn bằng chứng đáng tin cậy. Khi test suite tăng về số lượng và chạy song song trên nhiều môi trường, ba thuộc tính này càng quan trọng để giữ kết quả có thể tái hiện, chi phí bảo trì hợp lý và thời gian điều tra ngắn. Hãy xem lại chuẩn khi kiến trúc, công cụ, quy mô pipeline hoặc loại rủi ro thay đổi.

