# Đánh giá chiến lược đang phụ thuộc quá nhiều vào E2E hoặc kiểm thử thủ công

Một chiến lược kiểm thử có thể tạo cảm giác an toàn vì có rất nhiều kịch bản chạy xuyên suốt hệ thống hoặc có một nhóm tester thực hiện quy trình thủ công trước mỗi lần phát hành. Tuy nhiên, khi phần lớn bằng chứng chất lượng chỉ đến từ kiểm thử đầu cuối (end-to-end, E2E) hoặc kiểm thử thủ công, nhóm thường nhận phản hồi chậm, tốn chi phí duy trì, khó xác định nguyên nhân lỗi và dễ bỏ sót thay đổi nhỏ giữa các lần kiểm tra. Một thay đổi đơn giản có thể phải chờ toàn bộ môi trường được dựng lên; một lỗi ở một hàm nhỏ có thể chỉ được phát hiện sau khi nhiều dịch vụ đã phối hợp.

Đánh giá mức độ phụ thuộc vào E2E hoặc kiểm thử thủ công là hoạt động xem xét danh mục kiểm thử, luồng công việc, rủi ro được bao phủ, chi phí và chất lượng tín hiệu để xác định liệu nhóm đang dùng đúng loại kiểm thử ở đúng cấp độ hay không. Mục tiêu không phải loại bỏ E2E hoặc kiểm thử thủ công. E2E cần thiết để xác minh hành trình người dùng và sự phối hợp của hệ thống; kiểm thử thủ công cần thiết cho khám phá, khả năng sử dụng và các tình huống cần phán đoán. Vấn đề xuất hiện khi chúng trở thành cách xác minh mặc định cho hầu hết mọi quy tắc và thay đổi.

Một chiến lược cân bằng đặt kiểm tra ở lớp có thể phát hiện lỗi sớm, nhanh và rõ nguyên nhân nhất, sau đó dùng kiểm thử tích hợp, hợp đồng, E2E và kiểm thử thủ công để xác nhận những rủi ro cần góc nhìn rộng hơn. Cách phân bổ phải dựa trên rủi ro, kiến trúc, khả năng kiểm thử và bằng chứng thực tế của sản phẩm.

## 1. Nhận diện dấu hiệu phụ thuộc quá nhiều

Không nên kết luận chiến lược mất cân bằng chỉ vì có nhiều test E2E hoặc nhiều hoạt động thủ công. Một hệ thống có quy trình nghiệp vụ phức tạp, tích hợp nhiều bên thứ ba hoặc yêu cầu xác nhận hành trình người dùng có thể cần một số lượng E2E đáng kể. Cần xem xét vai trò của các kiểm tra đó, loại lỗi chúng phát hiện, chi phí vận hành và liệu có lớp kiểm thử khác phù hợp hơn hay không.

Các dấu hiệu thường gặp:

- Phần lớn thay đổi phải chờ một bộ E2E lớn hoàn tất mới có tín hiệu đáng tin cậy.
- Unit test, component test, API test hoặc contract test còn ít, yếu hoặc không được duy trì.
- Nhiều lỗi logic đơn giản chỉ được phát hiện ở UI hoặc cuối hành trình.
- Một test E2E thất bại khiến nhóm phải điều tra nhiều dịch vụ, dữ liệu và môi trường trước khi tìm ra nguyên nhân.
- Bộ E2E thường xuyên flaky do timing, animation, selector, dữ liệu dùng chung hoặc phụ thuộc mạng.
- Thời gian chạy và thời gian xếp hàng khiến nhóm bỏ qua test, chạy lại nhiều lần hoặc trì hoãn merge.
- Tester phải lặp lại các bước giống nhau trước mỗi release, nhưng bằng chứng không được lưu hoặc tái sử dụng hiệu quả.
- Kiểm thử thủ công chủ yếu xác minh những quy tắc có thể kiểm tra tự động ở lớp thấp hơn.
- Test thủ công phụ thuộc vào một vài cá nhân hiểu quy trình, khiến việc bàn giao và mở rộng khó khăn.
- Mỗi lần thay đổi nhỏ đều yêu cầu kiểm tra lại toàn bộ hệ thống bằng tay.
- Báo cáo cho biết “hành trình thất bại” nhưng không xác định được component, hợp đồng hoặc bất biến nào bị vi phạm.
- Nhóm có nhiều kịch bản E2E nhưng thiếu kiểm thử âm tính, giá trị biên, quyền truy cập hoặc lỗi ở cấp API.

Một dấu hiệu riêng lẻ chưa đủ kết luận. Hãy kết hợp dữ liệu thời gian, flaky rate, defect escape, mức bao phủ rủi ro, nỗ lực thủ công và phản hồi của nhóm.

## 2. Phân biệt các cấp độ và mục đích kiểm thử

Trước khi đánh giá danh mục, cần phân biệt loại kiểm thử theo phạm vi và mục tiêu. Tên gọi có thể khác giữa các framework, vì vậy nên mô tả ranh giới thực tế: thành phần nào chạy thật, thành phần nào được thay thế, và điều gì đang được xác minh.

| Cấp độ/loại | Phạm vi điển hình | Câu hỏi chính | Đặc điểm phản hồi |
|---|---|---|---|
| Unit test | Hàm, lớp hoặc đơn vị logic nhỏ; phụ thuộc thường được thay thế | Quy tắc hoặc bất biến nội bộ có đúng không? | Thường nhanh, cô lập và dễ chẩn đoán |
| Component/service test | Một component hoặc service với một phần dependency được kiểm soát | Thành phần xử lý đầu vào, trạng thái và lỗi đúng không? | Nhanh hơn E2E, phạm vi rộng hơn unit |
| API test | Giao tiếp qua API của một dịch vụ | Contract, validation, authorization và hành vi API có đúng không? | Có thể kiểm tra nhiều trường hợp mà không cần UI |
| Contract test | Sự phù hợp giữa consumer và provider theo hợp đồng | Hai phía có hiểu schema, status và semantics giống nhau không? | Tập trung vào ranh giới tích hợp |
| Integration test | Hai hoặc nhiều thành phần giao tiếp qua dependency thật hoặc được kiểm soát | Sự phối hợp, transaction, message và dữ liệu có đúng không? | Phát hiện lỗi tại ranh giới, cần quản lý môi trường |
| System/E2E test | Hệ thống tích hợp qua hành trình hoặc luồng người dùng | Một hành trình quan trọng có hoạt động từ đầu đến cuối không? | Có phạm vi rộng, thường tốn thời gian và khó khoanh vùng |
| Kiểm thử thủ công khám phá | Người kiểm thử chủ động khám phá sản phẩm | Có hành vi bất ngờ, vấn đề trải nghiệm hoặc rủi ro chưa được giả định không? | Linh hoạt, phụ thuộc kỹ năng và ghi chép của tester |
| Kiểm thử chấp nhận/thăm dò có hướng dẫn | Người dùng hoặc tester đánh giá tiêu chí và bối cảnh sử dụng | Sản phẩm có đáp ứng nhu cầu và quy tắc nghiệp vụ không? | Cần phán đoán, trao đổi và bằng chứng rõ |

Không phải mọi API test đều là integration test, và không phải mọi E2E đều chạy qua giao diện. Một kịch bản gọi nhiều service qua API có thể là E2E ở cấp hệ thống. Khi kiểm kê, hãy ghi rõ phạm vi thực tế thay vì chỉ dựa trên tên thư mục hoặc công cụ.

## 3. Vì sao chiến lược quá nặng E2E hoặc thủ công gây khó khăn?

### 3.1. Phản hồi chậm

E2E thường cần khởi động nhiều dịch vụ, chuẩn bị dữ liệu, đăng nhập, chờ bất đồng bộ và dọn dẹp. Khi số lượng tăng, thời gian chạy và queue time có thể kéo dài. Kiểm thử thủ công còn cần điều phối người, môi trường và lịch thực hiện. Phản hồi đến muộn khiến lỗi khó gắn với thay đổi gây ra nó.

### 3.2. Khó chẩn đoán

Một hành trình thất bại có thể do UI, API gateway, service, database, queue, dữ liệu, mạng hoặc bên thứ ba. Nếu test chỉ báo bước cuối không đạt, nhóm phải điều tra một vùng rộng. Kiểm tra cùng quy tắc ở lớp gần logic hơn thường cho thông báo lỗi cụ thể và dễ tái hiện.

### 3.3. Tính ổn định thấp hơn

E2E chịu ảnh hưởng của timing, tài nguyên dùng chung, trạng thái môi trường, browser, mạng và dependency ngoài. Kiểm thử thủ công cũng chịu ảnh hưởng của người thực hiện, dữ liệu, thời điểm và cách diễn giải. Nếu không kiểm soát, cùng một sản phẩm có thể cho kết quả khác nhau.

### 3.4. Chi phí bảo trì tăng

Thay đổi giao diện nhỏ có thể làm hỏng nhiều selector và kịch bản E2E. Thay đổi quy trình thủ công có thể yêu cầu cập nhật tài liệu, đào tạo và phối hợp. Khi nhiều test kiểm tra cùng một quy tắc ở tầng cao, nhóm phải duy trì nhiều bản sao của cùng kỳ vọng.

### 3.5. Phản hồi không tương xứng với nguyên nhân

Nếu quy tắc tính thuế chỉ được xác minh qua hành trình UI, lỗi làm tròn có thể chỉ xuất hiện ở cuối luồng. Một unit test hoặc API test được thiết kế tốt có thể kiểm tra nhiều tổ hợp biên nhanh hơn, trong khi E2E chỉ cần xác minh một số hành trình đại diện.

### 3.6. Khó mở rộng phạm vi

Khi số lượng tổ hợp người dùng, vai trò, dữ liệu, trình duyệt, thiết bị và trạng thái tăng lên, nhân số lượng tổ hợp trong E2E hoặc kiểm thử thủ công sẽ rất tốn kém. Nhiều tổ hợp có thể được xác minh hiệu quả ở cấp API, component hoặc contract; E2E tập trung vào các luồng có giá trị đại diện.

## 4. Không áp dụng máy móc mô hình kim tự tháp

Mô hình kim tự tháp kiểm thử thường gợi ý nhiều kiểm thử đơn vị, ít kiểm thử tích hợp và một lớp E2E nhỏ hơn. Đây là nguyên tắc định hướng về chi phí, tốc độ và phạm vi, không phải tỷ lệ bắt buộc cho mọi hệ thống.

Một kiến trúc hướng dịch vụ có thể cần nhiều contract và integration test. Một ứng dụng ít logic nhưng nhiều quy trình cấu hình có thể cần kiểm thử hệ thống ở một số điểm. Một sản phẩm phần cứng hoặc thiết bị thực có thể cần kiểm thử vật lý mà không thể thay thế bằng unit test. Vì vậy, cần chọn danh mục theo rủi ro và kiến trúc.

Những nguyên tắc nên giữ:

- Kiểm tra quy tắc logic ở lớp gần nơi quy tắc được thực hiện.
- Kiểm tra hợp đồng ở ranh giới giữa các thành phần.
- Dùng integration test để xác minh tương tác quan trọng với dependency thật hoặc môi trường được kiểm soát.
- Dùng E2E cho hành trình có giá trị, nơi cần chứng minh các thành phần phối hợp.
- Dùng kiểm thử thủ công cho khám phá, trải nghiệm, tính mới và những đánh giá cần phán đoán.
- Tránh xác minh cùng một chi tiết ở quá nhiều tầng nếu không có lý do rủi ro rõ ràng.
- Giữ một số kiểm tra độc lập ở các tầng khác nhau khi chúng cung cấp bằng chứng bổ sung.

Không đặt mục tiêu “giảm E2E xuống một tỷ lệ đẹp”. Hãy đặt mục tiêu “mỗi rủi ro được kiểm tra ở tầng có tín hiệu tốt nhất, với lớp xác nhận bổ sung khi cần”.

## 5. Kiểm kê danh mục kiểm thử hiện tại

Đánh giá cần bắt đầu bằng dữ liệu thực tế. Không thể kết luận chiến lược nặng E2E chỉ từ số lượng file test hoặc tên suite.

### 5.1. Thu thập thông tin cho từng nhóm kiểm thử

Với mỗi suite hoặc hoạt động, ghi nhận:

- ID, tên, mục tiêu và loại kiểm thử thực tế.
- Thành phần, hành trình, yêu cầu và rủi ro được bao phủ.
- Mức độ phụ thuộc vào UI, API, database, queue, dịch vụ ngoài và môi trường.
- Dữ liệu, tài khoản, setup và cleanup được sử dụng.
- Tần suất chạy và điều kiện kích hoạt.
- Thời gian queue, setup, execution và công bố kết quả.
- Tỷ lệ pass/fail, retry, flaky, blocked, skipped và cancelled.
- Loại lỗi mà test đã phát hiện trong lịch sử.
- Chi phí tạo mới, bảo trì và điều tra.
- Người hoặc nhóm sở hữu.
- Giới hạn và giả định của bằng chứng.

Nếu có thể, lấy dữ liệu từ nhiều chu kỳ phát triển và nhiều lần phát hành để tránh kết luận từ một thời điểm bất thường. Tách các nhóm test có môi trường và mục tiêu khác nhau.

### 5.2. Phân loại theo mục đích thay vì chỉ theo công cụ

Một test chạy bằng browser automation không nhất thiết phải là E2E; nó có thể chỉ xác minh một component UI. Một script gọi API có thể kiểm tra một dịch vụ hoặc toàn bộ hành trình nhiều service. Hãy phân loại theo phạm vi thực tế và số dependency cần thiết.

Nên gắn test với một hoặc nhiều mục tiêu:

- Quy tắc nghiệp vụ.
- Validation và trường hợp biên.
- Contract/schema.
- Tương tác giữa service.
- Hành trình người dùng quan trọng.
- Phân quyền và bảo mật.
- Hiệu năng và độ tin cậy.
- Khả năng tương thích hoặc trải nghiệm.

Việc này giúp nhận ra những quy tắc chỉ có một lớp test kiểm tra, những hành trình có quá nhiều test trùng lặp và những rủi ro chưa có bằng chứng.

### 5.3. Lập bản đồ phân bố test

Có thể tổng hợp theo số lượng, thời gian thực thi và mức độ rủi ro. Ví dụ:

| Nhóm | Số test | Tỷ lệ số lượng | Tỷ lệ thời gian chạy | Rủi ro chính |
|---|---:|---:|---:|---|
| Unit/component | 180 | 36% | 8% | Logic, validation và bất biến |
| API/contract | 90 | 18% | 14% | Contract, authorization và service behavior |
| Integration | 75 | 15% | 23% | Database, queue và service interaction |
| E2E tự động | 105 | 21% | 42% | Hành trình quan trọng xuyên hệ thống |
| Kiểm thử thủ công | 50 kịch bản | 10% | 13% effort người | Khám phá, trải nghiệm và acceptance |

Các số liệu trên chỉ minh họa cách kiểm kê, không phải mục tiêu phân bổ. Lưu ý rằng effort thủ công và thời gian máy không cùng đơn vị; không nên cộng trực tiếp để tạo một tỷ lệ tổng nếu chưa quy đổi và giải thích cách tính.

## 6. Đánh giá mức phụ thuộc bằng nhiều chỉ số

Không nên dùng một con số duy nhất để đánh giá sự mất cân bằng. Hãy xem xét ít nhất các nhóm chỉ số sau.

### 6.1. Phân bố danh mục

- Số lượng và tỷ trọng test theo cấp độ.
- Thời gian chạy theo cấp độ.
- Effort thủ công theo tuần hoặc release.
- Tỷ lệ rủi ro chỉ có bằng chứng ở E2E hoặc kiểm thử thủ công.
- Tỷ lệ quy tắc có thể kiểm tra ở lớp thấp hơn nhưng chỉ đang được kiểm tra ở lớp cao.

### 6.2. Tốc độ phản hồi

- P50/P90/P95 feedback time theo suite.
- Queue time và setup time.
- Thời gian từ thay đổi đến tín hiệu đầu tiên có thể hành động.
- Thời gian chờ người kiểm thử và thời gian điều phối thủ công.
- Thời gian triage từ khi test fail đến khi xác định được lớp nguyên nhân.

### 6.3. Độ tin cậy

- Flaky failure rate và retry recovery rate.
- Tỷ lệ cảnh báo fail được xác nhận là lỗi sản phẩm.
- Tỷ lệ lỗi tái hiện được với build và dữ liệu tương đương.
- Số test bị quarantine, skipped hoặc không còn người sở hữu.
- Lỗi lọt qua kiểm thử và được phát hiện ở staging, production hoặc bởi người dùng.

### 6.4. Hiệu quả phát hiện lỗi

- Loại và mức nghiêm trọng của defect được phát hiện ở mỗi tầng.
- Thời điểm phát hiện so với thời điểm lỗi được đưa vào.
- Chi phí sửa lỗi theo giai đoạn phát hiện.
- Những lỗi mà E2E phát hiện nhưng không có test thấp hơn tương ứng.
- Những lỗi được phát hiện lặp lại bởi nhiều tầng mà không cung cấp thêm thông tin.

Số defect phát hiện ở mỗi tầng không phải thước đo hiệu quả độc lập. Một lớp có ít lỗi có thể vì sản phẩm ổn định hoặc vì test chưa đủ nhạy. Cần kết hợp với phân tích rủi ro, review test và dữ liệu lỗi lọt.

## 7. Phân tích từng test E2E để tìm cơ hội chuyển xuống lớp phù hợp

Với mỗi E2E, hãy xem test đang xác minh phần nào và phần nào cần thiết phải chạy xuyên hệ thống.

Các câu hỏi:

1. Mục tiêu chính là xác minh quy tắc nghiệp vụ, hợp đồng, tích hợp hay toàn bộ hành trình?
2. Thành phần nào cần chạy thật để tạo bằng chứng có ý nghĩa?
3. Có thể kiểm tra logic chính ở unit hoặc component test không?
4. Có thể xác minh request/response, validation và quyền ở API test không?
5. Có contract test để phát hiện không tương thích giữa consumer và provider không?
6. Có cần dependency thật cho transaction, message hoặc persistence không?
7. Phần nào của E2E chỉ lặp lại assertion đã được xác minh ở lớp khác?
8. Test có phát hiện loại lỗi độc đáo nào mà lớp thấp hơn không thể phát hiện không?
9. Chi phí setup, dữ liệu, flaky và triage của test là bao nhiêu?
10. Nếu chuyển một phần xuống lớp thấp hơn, bằng chứng nào sẽ bị mất?

### 7.1. Ví dụ phân rã E2E thanh toán

Một kịch bản E2E hiện tại:

1. Mở trình duyệt và đăng nhập.
2. Tìm sản phẩm và thêm vào giỏ hàng.
3. Nhập địa chỉ giao hàng.
4. Chọn phương thức thanh toán.
5. Gửi giao dịch sandbox.
6. Chờ callback và trạng thái đơn hàng.
7. Mở trang lịch sử và xác minh đơn đã thanh toán.

Không cần mọi quy tắc trong hành trình chỉ được kiểm tra qua kịch bản này. Có thể phân rã:

| Quy tắc/bằng chứng | Lớp phù hợp | Lý do |
|---|---|---|
| Tính tổng tiền, thuế và phí | Unit/component | Nhiều giá trị biên, phản hồi nhanh và oracle rõ |
| Validation địa chỉ và dữ liệu đơn | Unit/API | Có thể kiểm tra nhiều đầu vào mà không cần browser |
| API tạo đơn và kiểm tra quyền | API test | Xác minh status, payload, scope và tác dụng phụ |
| Consumer/provider schema | Contract test | Phát hiện thay đổi không tương thích sớm |
| Ghi đơn và cập nhật tồn kho | Integration test | Cần xác minh transaction hoặc tương tác dữ liệu thật |
| Retry thanh toán không tạo giao dịch trùng | Integration/concurrency test | Tập trung vào idempotency và ranh giới nhà cung cấp |
| Một hành trình mua hàng quan trọng | E2E | Xác nhận các thành phần phối hợp từ góc nhìn người dùng |
| Khả năng hiểu và hoàn tất biểu mẫu | Kiểm thử thủ công khám phá/usability | Cần quan sát và phán đoán của con người |

Sau khi phân rã, có thể giữ một số E2E đại diện cho hành trình thành công, một số lỗi quan trọng và một số vai trò chính. Các tổ hợp dữ liệu, quy tắc và trường hợp biên được chuyển sang API, component hoặc unit test phù hợp.

### 7.2. Không chuyển xuống chỉ để giảm thời gian

Chỉ chuyển kiểm tra khi lớp mới có thể cung cấp bằng chứng đáng tin cậy. Nếu lỗi chỉ xuất hiện do cấu hình gateway, transaction phân tán hoặc callback thật, unit test với mock không thể thay thế hoàn toàn integration/E2E. Ghi rõ ranh giới được xác minh ở mỗi lớp và giữ một kiểm tra tích hợp khi cần.

## 8. Đánh giá các hoạt động kiểm thử thủ công

Kiểm thử thủ công cần được xem xét theo mục tiêu, mức lặp lại và khả năng phán đoán.

### 8.1. Phân loại hoạt động thủ công

Có thể chia thành:

- **Khám phá (exploratory):** Tester học sản phẩm, đặt giả thuyết và tìm hành vi bất ngờ.
- **Đánh giá khả năng sử dụng:** Quan sát người dùng hoặc tester tương tác, nhận diện vấn đề về hiểu biết và trải nghiệm.
- **Kiểm thử chấp nhận:** Xác nhận quy tắc và kết quả nghiệp vụ với người có thẩm quyền.
- **Kiểm thử theo checklist lặp lại:** Thực hiện các bước và kết quả đã biết qua nhiều lần phát hành.
- **Kiểm thử tương thích trên thiết bị thật:** Kiểm tra hành vi phụ thuộc thiết bị, cảm biến, phần cứng hoặc cấu hình thực.
- **Kiểm thử đặc biệt cần phán đoán:** Nội dung, hình ảnh, quy trình phức tạp hoặc hành vi khó định lượng.

Những hoạt động khám phá, usability và đánh giá nghiệp vụ có thể cần con người. Những bước lặp lại, có đầu vào và kết quả xác định, có thể phù hợp với tự động hóa hoặc kiểm tra ở lớp khác.

### 8.2. Tìm hoạt động thủ công có thể cải tiến

Với mỗi kịch bản thủ công, hãy hỏi:

- Có lặp lại mỗi commit, mỗi ngày hoặc mỗi release không?
- Các bước có ổn định và kết quả có thể xác định không?
- Có thể kiểm tra cùng quy tắc qua API hoặc component không?
- Có công cụ hỗ trợ tạo dữ liệu, xác minh kết quả hoặc thu thập bằng chứng không?
- Hoạt động có cần quan sát, phán đoán hoặc tương tác với người dùng không?
- Chi phí tự động hóa và bảo trì có thấp hơn lợi ích trong vòng đời không?
- Nếu không tự động hóa, có thể rút gọn checklist hoặc lấy mẫu theo rủi ro không?

Không nên tự động hóa một quy trình thủ công chỉ vì nó đang tồn tại. Trước hết hãy xác nhận quy trình cần thiết, tiêu chí đúng và dữ liệu đầu vào. Tự động hóa một quy trình sai sẽ khiến sai sót lặp lại nhanh hơn.

## 9. Xác định lớp kiểm thử phù hợp cho từng loại rủi ro

Một cách đánh giá thực tế là lập bảng rủi ro với bằng chứng hiện tại và lớp kiểm thử đề xuất.

| Loại rủi ro | Bằng chứng nên ưu tiên | Khi nào vẫn cần E2E/thủ công |
|---|---|---|
| Quy tắc tính toán | Unit/component với giá trị biên và property | Khi cần xác nhận giá trị được hiển thị và sử dụng đúng trong hành trình |
| Validation đầu vào | Unit và API negative test | Khi hành vi phụ thuộc tương tác nhiều bước hoặc trải nghiệm biểu mẫu |
| Authorization | API/contract hoặc component với ma trận role/tenant | Một số E2E để xác nhận người dùng không thể vượt quyền qua giao diện và luồng tích hợp |
| Schema và tương thích API | Contract test và schema validation | E2E/integration cho hành trình có nhiều consumer quan trọng |
| Transaction và persistence | Integration test với database phù hợp | E2E để xác nhận hành trình và kết quả người dùng |
| Message và xử lý bất đồng bộ | Component/integration test với broker, duplicate và retry | E2E cho một luồng xuyên dịch vụ quan trọng |
| Hiệu năng | Benchmark, load và stress test ở cấp phù hợp | Kiểm tra thủ công/quan sát khi đánh giá trải nghiệm thực tế |
| Khả năng sử dụng | Nghiên cứu người dùng, exploratory và heuristic review | Không thể thay thế hoàn toàn bằng assertion tự động |
| Tương thích thiết bị | Test tự động trên ma trận thiết bị kết hợp thiết bị thật | Kiểm tra thủ công cho phần cứng hoặc hành vi trực quan đặc thù |

Mỗi rủi ro có thể cần nhiều loại bằng chứng. Ví dụ, authorization cần test API cho nhiều role và tenant, nhưng một E2E đại diện vẫn hữu ích để xác nhận UI không vô tình hiển thị thao tác không được phép.

## 10. Xác định mức bao phủ và số lượng E2E hợp lý

Không có tỷ lệ E2E đúng cho mọi sản phẩm. Số lượng cần dựa trên số hành trình quan trọng, mức độ độc lập của chúng, số tích hợp và rủi ro cần xác nhận.

Một bộ E2E có thể tập trung vào:

- Hành trình kinh doanh quan trọng nhất.
- Các tích hợp mà chỉ kiểm tra riêng từng service chưa đủ chứng minh.
- Một số luồng thành công đại diện.
- Các lỗi có hậu quả lớn cần xác nhận xuyên hệ thống.
- Các vai trò hoặc cấu hình tạo ra đường đi khác biệt thực sự.
- Smoke test sau triển khai để xác nhận môi trường hoạt động.

Tránh tạo E2E cho mọi tổ hợp dữ liệu nếu các tổ hợp đó chỉ thay đổi quy tắc ở một service. Chuyển ma trận dữ liệu sang API hoặc component test khi phù hợp. Tránh nhiều E2E lặp lại cùng một hành trình chỉ khác tên người dùng mà không xác minh thêm rủi ro.

### 10.1. Bộ E2E tối thiểu có giá trị

Một bộ E2E có giá trị thường có:

- Mục tiêu rõ, gắn với hành trình hoặc rủi ro.
- Dữ liệu độc lập, có thể tạo và dọn dẹp.
- Số bước vừa đủ để xác minh hành vi xuyên hệ thống.
- Assertion kiểm tra trạng thái cuối quan trọng, không chỉ thao tác UI.
- Log hoặc correlation ID để chẩn đoán.
- Cách chạy ổn định và không phụ thuộc thứ tự.
- Chủ sở hữu và quy tắc cập nhật khi hành trình thay đổi.

## 11. Lập kế hoạch chuyển dịch từ E2E/thủ công sang danh mục cân bằng

Không nên xóa hàng loạt test E2E hoặc ngừng kiểm thử thủ công trước khi có bằng chứng thay thế. Chuyển dịch nên theo từng rủi ro và từng nhóm test.

### Bước 1: Thiết lập đường cơ sở

Thu thập thời gian chạy, flaky rate, retry, chi phí thủ công, defect được phát hiện và mức bao phủ rủi ro. Ghi rõ cách đo để có thể so sánh sau cải tiến.

### Bước 2: Chọn nhóm có chi phí hoặc rủi ro cao

Ưu tiên suite E2E chậm, thường xuyên flaky, trùng lặp nhiều hoặc chỉ kiểm tra logic đơn giản. Với kiểm thử thủ công, chọn checklist lặp lại thường xuyên và có kết quả xác định.

### Bước 3: Phân tích mục tiêu từng test

Xác định test đang kiểm tra quy tắc, contract, tích hợp, hành trình hay trải nghiệm. Tách các assertion có thể kiểm tra độc lập và phần cần hệ thống thật.

### Bước 4: Thiết kế bằng chứng ở lớp phù hợp

Bổ sung unit/component/API/contract/integration test với oracle và dữ liệu rõ. Nếu cần, tạo seam hoặc testability support trong sản phẩm để kiểm tra hành vi mà không phải thao tác qua UI.

### Bước 5: Chạy song song trong giai đoạn chuyển tiếp

Giữ test cũ trong thời gian xác nhận test mới phát hiện được các trường hợp quan trọng. So sánh kết quả trên cùng build và dữ liệu. Không loại bỏ test cũ chỉ vì test mới pass một lần.

### Bước 6: Thu gọn có kiểm soát

Khi có bằng chứng tương đương hoặc tốt hơn cho mục tiêu cụ thể, giảm tổ hợp E2E hoặc bước thủ công trùng lặp. Giữ lại những E2E độc đáo và ghi lý do loại bỏ các ca cũ.

### Bước 7: Đo lại và cập nhật chiến lược

So sánh feedback time, flaky rate, defect detection, chi phí bảo trì và mức bao phủ rủi ro. Cập nhật kế hoạch, ownership và quality gate.

## 12. Ví dụ chuyển một bộ E2E lớn sang danh mục cân bằng

Giả sử nhóm có 120 kịch bản E2E UI cho hệ thống đặt hàng. Bộ test mất 95 phút, P95 là 150 phút do queue và retry. Khoảng 18% lần chạy có ít nhất một lỗi được xác định là flaky. Nhiều test khác nhau chỉ thay đổi dữ liệu về số lượng, mã giảm giá hoặc địa chỉ.

Nhóm kiểm kê và nhận thấy:

- 35 kịch bản kiểm tra quy tắc tính giá và coupon.
- 25 kịch bản kiểm tra validation của API đơn hàng.
- 20 kịch bản kiểm tra quyền và tenant.
- 15 kịch bản kiểm tra tương tác thanh toán, tồn kho và message.
- 15 kịch bản kiểm tra hành trình UI quan trọng.
- 10 kịch bản kiểm tra trạng thái lỗi hoặc phục hồi xuyên hệ thống.

Đây là phân loại giả định để minh họa cách phân tích. Nhóm không chuyển mọi test xuống unit. Họ thực hiện:

1. Chuyển ma trận giá, coupon và giá trị biên sang unit/component test.
2. Chuyển validation và ma trận role/tenant sang API test.
3. Bổ sung contract test cho consumer/provider của order và payment service.
4. Giữ integration test cho transaction, message, retry và cập nhật tồn kho.
5. Giữ E2E cho một số hành trình mua hàng, thanh toán và hủy đơn quan trọng.
6. Giữ exploratory session cho usability, nội dung và hành vi mới.
7. Thay các checklist thủ công lặp lại bằng API hoặc UI automation ở nơi kết quả xác định.

Sau chuyển dịch, giả sử bộ kiểm tra pull request có 180 unit/component, 55 API/contract và 35 integration test, còn bộ E2E UI giảm còn 25 hành trình đại diện. Thời gian E2E giảm, nhưng tổng số test tăng vì lớp thấp hơn có nhiều tổ hợp đầu vào. Điều cần đánh giá là tổng thời gian phản hồi, độ ổn định, chi phí bảo trì và mức bao phủ rủi ro, không phải chỉ số lượng test.

Nhóm chạy song song bộ cũ và mới trong vài chu kỳ, xác minh các lỗi lịch sử quan trọng vẫn bị phát hiện. Sau đó họ loại bỏ các E2E trùng lặp, giữ test thủ công khám phá và ghi lại những rủi ro vẫn cần kiểm tra bằng người.

## 13. Cách đo hiệu quả sau chuyển dịch

Đo trước và sau bằng cùng định nghĩa, cùng nhóm job và khoảng thời gian đủ đại diện.

| Góc nhìn | Chỉ số gợi ý | Điều cần kiểm tra |
|---|---|---|
| Tốc độ | P50/P95 feedback time, queue/setup/execution time | Người phát triển nhận tín hiệu sớm hơn không? |
| Ổn định | Flaky rate, retry recovery, test bị quarantine | Kết quả nhất quán hơn không? |
| Chẩn đoán | Time to triage, tỷ lệ lỗi tái hiện | Có xác định lớp nguyên nhân nhanh hơn không? |
| Phát hiện lỗi | Defect theo mức độ và tầng phát hiện, lỗi lọt | Có mất khả năng phát hiện rủi ro quan trọng không? |
| Bao phủ | Risk-to-test mapping, yêu cầu quan trọng có bằng chứng | Rủi ro được kiểm tra đầy đủ và đúng lớp không? |
| Chi phí | Effort bảo trì, thời gian thủ công, chi phí runner/môi trường | Tổng chi phí vòng đời có giảm không? |
| Trải nghiệm nhóm | Tỷ lệ test bị bỏ qua, thời gian chờ và phản hồi của người dùng quy trình | Nhóm có tin và sử dụng kết quả không? |

Không kết luận thành công chỉ vì E2E chạy nhanh hơn. Nếu lỗi phân quyền hoặc lỗi giao dịch bắt đầu lọt qua nhiều hơn, danh mục đã mất bằng chứng quan trọng. Ngược lại, số test unit tăng nhưng không có oracle hoặc test chỉ kiểm tra implementation detail cũng không đảm bảo chất lượng.

## 14. Quản lý rủi ro trong thời gian chuyển dịch

Chuyển dịch làm thay đổi vị trí và cách thu thập bằng chứng, vì vậy cần quản lý rủi ro tạm thời.

- Giữ các E2E quan trọng cho đến khi lớp thay thế được xác minh.
- Xác định các test bắt buộc chặn merge/release và test chỉ cung cấp thông tin.
- Không loại bỏ kiểm thử thủ công cần thiết cho usability, acceptance hoặc khám phá.
- Ghi rõ phần nào đã chuyển, phần nào chưa có bằng chứng và người chấp nhận rủi ro.
- Kiểm tra test mới trên cùng build, dữ liệu và điều kiện với test cũ khi có thể.
- Có phương án quay lại nếu lớp test mới không phát hiện được lỗi đã biết.
- Theo dõi các lỗi production và incident để phát hiện suy giảm sau chuyển dịch.
- Không thay thế E2E bằng mock hoàn toàn nếu mục tiêu cần xác minh dependency thật.

Nếu test cũ đang flaky đến mức không thể dùng làm đối chứng, hãy tìm bằng chứng khác như defect lịch sử, test thủ công có kiểm soát, log hoặc fault injection phù hợp. Ghi rõ giới hạn so sánh.

## 15. Tổ chức kiểm thử thủ công theo hướng có giá trị cao

Sau khi giảm các bước thủ công lặp lại, cần bảo vệ thời gian cho hoạt động mà con người làm tốt.

Một exploratory session nên có:

- Mục tiêu hoặc charter nêu khu vực và rủi ro cần khám phá.
- Thời lượng và phạm vi rõ.
- Bối cảnh build, môi trường, dữ liệu và vai trò.
- Ghi chép hành động, quan sát, câu hỏi và phát hiện.
- Bằng chứng như ảnh, video, log hoặc dữ liệu tái hiện khi phù hợp.
- Tổng kết điều đã kiểm tra, điều chưa kiểm tra và đề xuất follow-up.

Kiểm thử thủ công có cấu trúc giúp nhóm giữ được giá trị khám phá mà không biến nó thành một checklist dài khó tái sử dụng. Những phát hiện lặp lại nên được xem xét chuyển thành regression test ở lớp phù hợp, sau khi xác định oracle và điều kiện tái hiện.

## 16. Tiêu chí lựa chọn giữa tự động hóa và kiểm thử thủ công

Không phải thao tác nào cũng nên tự động hóa. Có thể dùng bảng cân nhắc:

| Yếu tố | Nghiêng về tự động hóa | Nghiêng về thủ công/con người |
|---|---|---|
| Tần suất | Lặp lại thường xuyên | Hiếm hoặc chỉ cần ở mốc đặc biệt |
| Kết quả | Có oracle rõ, có thể xác định | Cần đánh giá chất lượng cảm nhận hoặc ngữ cảnh |
| Đầu vào | Có thể tạo và kiểm soát | Cần tương tác người dùng hoặc thiết bị đặc thù |
| Độ ổn định | Hành vi và giao diện đủ ổn định | Đang khám phá thiết kế hoặc hành vi mới |
| Chi phí vòng đời | Tiết kiệm effort lặp lại nhiều hơn chi phí xây/bảo trì | Tự động hóa tốn kém và ít tái sử dụng |
| Rủi ro | Cần phản hồi nhanh, nhất quán | Cần phán đoán chuyên môn hoặc chấp nhận nghiệp vụ |

Một hoạt động có thể kết hợp cả hai. Ví dụ, tự động kiểm tra accessibility cơ bản trong CI, sau đó dùng screen reader và đánh giá thủ công cho các hành trình quan trọng.

## 17. Quản lý chất lượng của bộ E2E còn lại

Sau khi thu gọn, bộ E2E còn lại cần được quản lý nghiêm túc vì chúng thường đại diện cho các hành trình có giá trị cao.

- Mỗi test có risk ID hoặc mục tiêu hành trình rõ.
- Dữ liệu riêng theo lần chạy và cleanup có thể xác minh.
- Không phụ thuộc thứ tự hoặc trạng thái do test trước tạo ra.
- Chờ điều kiện thực tế thay vì sleep cố định.
- Dùng selector ổn định và có ý nghĩa.
- Có correlation ID, log và screenshot/video khi hữu ích.
- Giới hạn dependency ngoài hoặc dùng sandbox có kiểm soát.
- Phân loại lỗi sản phẩm, môi trường, dữ liệu và test framework.
- Theo dõi thời gian, flaky rate và người sở hữu.
- Review định kỳ để loại bỏ test không còn giá trị hoặc cập nhật khi hành trình thay đổi.

E2E có thể chạy theo nhiều tầng: smoke nhỏ trên mỗi pull request hoặc sau deploy, bộ hành trình mở rộng sau tích hợp và kiểm tra toàn diện theo lịch. Cách chia phải dựa trên thời điểm cần bằng chứng và khả năng tài nguyên.

## 18. Những sai lầm thường gặp khi đánh giá và chuyển dịch

- **Đếm số E2E rồi kết luận:** Không xem xét rủi ro, thời gian, giá trị phát hiện và tính độc đáo của bằng chứng.
- **Đặt tỷ lệ kim tự tháp cố định:** Ép danh mục theo tỷ lệ mà không xét kiến trúc hoặc yêu cầu sản phẩm.
- **Xóa E2E trước khi có bằng chứng thay thế:** Làm giảm khả năng phát hiện lỗi tích hợp hoặc hành trình.
- **Chuyển mọi thứ xuống unit test:** Unit test không thể xác minh transaction, contract hoặc hành vi hệ thống thật.
- **Dùng mock thay cho dependency thật ở mọi nơi:** Có thể bỏ sót lỗi tích hợp và cấu hình.
- **Tự động hóa toàn bộ checklist thủ công:** Giữ lại bước không cần thiết và tăng chi phí bảo trì.
- **Loại bỏ exploratory testing:** Mất khả năng tìm hành vi bất ngờ và vấn đề trải nghiệm.
- **Chỉ đo execution time:** Bỏ qua queue, setup, triage và effort của con người.
- **Không phân loại flaky:** Retry che giấu lỗi và làm sai số liệu độ tin cậy.
- **Đánh giá test theo số lượng:** Nhiều test yếu không bằng một bộ test có oracle và phạm vi rủi ro rõ.
- **Không gắn test với rủi ro:** Không biết lớp test nào đang cung cấp bằng chứng cho quyết định nào.
- **Không giữ lịch sử khi thay đổi danh mục:** Không thể giải thích vì sao một kiểm tra bị chuyển hoặc loại bỏ.

## 19. Checklist đánh giá chiến lược kiểm thử

Nhóm có thể dùng checklist sau trong buổi đánh giá chiến lược:

- [ ] Đã kiểm kê unit, component, API, contract, integration, E2E và hoạt động thủ công theo phạm vi thực tế.
- [ ] Mỗi suite có mục tiêu, chủ sở hữu và liên kết với yêu cầu hoặc rủi ro.
- [ ] Đã đo số lượng, thời gian chạy, effort thủ công, queue time và flaky rate.
- [ ] Đã xác định các quy tắc chỉ đang được kiểm tra qua E2E hoặc thủ công.
- [ ] Đã tìm test E2E trùng lặp hoặc chỉ xác minh logic có thể kiểm tra ở lớp thấp hơn.
- [ ] Đã giữ các E2E cần thiết để xác minh tương tác và hành trình xuyên hệ thống.
- [ ] Đã xác định hoạt động thủ công cần khám phá, usability hoặc phán đoán nghiệp vụ.
- [ ] Có oracle và dữ liệu phù hợp cho test được chuyển sang lớp mới.
- [ ] Test mới đã được chạy đối chứng trước khi loại bỏ test cũ.
- [ ] Có kế hoạch quản lý rủi ro và ngoại lệ trong thời gian chuyển dịch.
- [ ] Bộ E2E còn lại có dữ liệu cô lập, cleanup, log và cơ chế chẩn đoán.
- [ ] Có chỉ số trước/sau về tốc độ, độ ổn định, phát hiện lỗi, chi phí và bao phủ rủi ro.
- [ ] Không dùng tỷ lệ tự động hóa hoặc tỷ lệ kim tự tháp làm mục tiêu thay thế cho chất lượng bằng chứng.
- [ ] Có lịch rà soát danh mục khi kiến trúc, yêu cầu hoặc rủi ro thay đổi.

Đánh giá chiến lược đang phụ thuộc quá nhiều vào E2E hoặc kiểm thử thủ công giúp nhóm tìm ra nơi phản hồi chậm, chi phí cao và bằng chứng chưa đúng cấp độ. Khi từng rủi ro được kiểm tra ở lớp phù hợp, E2E được giữ cho các hành trình thực sự cần xác nhận xuyên hệ thống và kiểm thử thủ công tập trung vào khám phá cùng phán đoán, chiến lược có thể phản hồi nhanh hơn mà vẫn bảo vệ được những bằng chứng quan trọng cho quyết định chất lượng.
