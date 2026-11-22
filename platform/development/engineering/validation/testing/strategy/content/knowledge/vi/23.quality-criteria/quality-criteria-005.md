# Quy định bằng chứng bắt buộc và điều kiện đo hợp lệ

Trong module **VALIDATION_TESTING_STRATEGY**, một kết quả kiểm thử chỉ có giá trị khi có đủ bằng chứng để người khác hiểu điều gì đã được kiểm tra, điều kiện nào đã được sử dụng và vì sao có thể tin vào kết luận. Việc ghi “PASS” hoặc “đạt” mà không xác định dữ liệu, môi trường, phép đo và nguồn quan sát khiến kết quả khó tái hiện, khó đánh giá và dễ bị diễn giải vượt quá phạm vi.

**Bằng chứng bắt buộc** là tập thông tin và dữ liệu cần được thu thập để chứng minh một tiêu chí chất lượng đã được kiểm tra theo cách có thể đánh giá. **Điều kiện đo hợp lệ** là các điều kiện bảo đảm phép đo phản ánh đúng thuộc tính cần đánh giá, dùng phương pháp phù hợp và có độ tin cậy đủ cho quyết định. Hai yếu tố này liên quan chặt chẽ: có nhiều log nhưng phép đo sai thì kết luận vẫn không hợp lệ; phép đo đúng nhưng không lưu dữ liệu và ngữ cảnh thì người khác không thể xác minh.

Bài học này hướng dẫn cách quy định bằng chứng trước khi chạy kiểm thử, lựa chọn nguồn và định dạng bằng chứng, xác định điều kiện đo hợp lệ, kiểm soát độ chính xác và tính đại diện, xử lý kết quả thiếu hoặc không ổn định, bảo vệ tính toàn vẹn của bằng chứng và liên kết kết quả với quyết định chất lượng. Mục tiêu là tạo ra kết luận có thể truy vết, tái lập và giới hạn đúng theo những gì đã được chứng minh.

## 1. Hiểu bằng chứng và tính hợp lệ của phép đo

### 1.1. Bằng chứng kiểm thử là gì?

Bằng chứng kiểm thử (test evidence) là thông tin được thu thập trong quá trình chuẩn bị, thực thi và đánh giá để hỗ trợ kết luận về một yêu cầu, tiêu chí hoặc thuộc tính chất lượng.

Bằng chứng có thể bao gồm:

- Test case, bước thực hiện, tiền điều kiện và dữ liệu đã dùng.
- Kết quả thực tế so với kết quả mong đợi.
- Request, response, mã trạng thái và payload đã được làm sạch.
- Bản ghi dữ liệu trước và sau thao tác.
- Log, trace, event ID và correlation ID.
- Metrics, biểu đồ, kết quả đo và báo cáo phân tích.
- Ảnh chụp màn hình, video hoặc bản ghi thao tác.
- Artifact, package digest, build ID và cấu hình môi trường.
- Báo cáo quét, findings, kết quả kiểm tra bảo mật.
- Biên bản rà soát, quyết định và phê duyệt.
- Thông tin về giới hạn, sai lệch và rủi ro còn lại.

Không phải trường hợp nào cũng cần tất cả các loại bằng chứng. Tập bằng chứng cần thiết phụ thuộc vào điều cần chứng minh và mức độ hậu quả nếu kết luận sai.

### 1.2. Bằng chứng khác với nhận xét hoặc kết luận

Cần phân biệt:

- **Quan sát:** điều thực tế đã xảy ra, ví dụ API trả về HTTP 409.
- **Bằng chứng:** dữ liệu hoặc bản ghi giúp người khác xác minh quan sát, ví dụ response đã lưu cùng request ID, timestamp và phiên bản dịch vụ.
- **Diễn giải:** ý nghĩa của quan sát so với tiêu chí, ví dụ trạng thái đơn không cho phép thao tác hủy.
- **Kết luận:** quyết định về tiêu chí, ví dụ trường hợp không đạt vì API chấp nhận yêu cầu hủy trái chính sách.

Câu “kiểm thử đã thành công” là kết luận, không phải bằng chứng. Câu “request với đơn hàng trạng thái SHIPPED trả 409, trạng thái đơn không đổi và bản ghi được truy vấn lại sau thao tác” mô tả quan sát có thể kiểm chứng.

### 1.3. Điều kiện đo hợp lệ là gì?

Một phép đo hợp lệ khi nó thực sự đo thuộc tính mà tiêu chí yêu cầu, được thực hiện bằng phương pháp và công cụ phù hợp, trong điều kiện được kiểm soát hoặc được mô tả đầy đủ.

Ví dụ:

- Nếu tiêu chí yêu cầu thời gian phản hồi ở percentile 95, chỉ đo thời gian trung bình là chưa đủ.
- Nếu tiêu chí yêu cầu hệ thống chịu tải 500 request/giây, chạy 500 request tổng cộng không chứng minh thông lượng đó.
- Nếu tiêu chí yêu cầu khả năng truy cập bằng bàn phím, ảnh chụp giao diện không chứng minh người dùng có thể hoàn thành tác vụ.
- Nếu tiêu chí yêu cầu không tạo giao dịch trùng sau retry, response thành công không đủ; cần kiểm tra số giao dịch và trạng thái cuối.

Phép đo sai thuộc tính hoặc sai điều kiện có thể tạo ra con số chính xác về mặt tính toán nhưng không trả lời câu hỏi chất lượng.

### 1.4. Ba câu hỏi cần trả lời trước khi chấp nhận kết quả

1. **Đã thu thập đủ bằng chứng chưa?** Có dữ liệu, ngữ cảnh và nguồn quan sát để xác minh tiêu chí không?
2. **Phép đo có hợp lệ không?** Công cụ, phương pháp, đơn vị, mẫu và điều kiện có phù hợp không?
3. **Kết luận có nằm trong phạm vi bằng chứng không?** Có giới hạn hoặc yếu tố chưa kiểm tra nào cần nêu rõ không?

Chỉ khi ba câu hỏi được trả lời thỏa đáng, kết quả mới có thể được dùng làm căn cứ cho quyết định chất lượng.

## 2. Quy định bằng chứng bắt buộc từ tiêu chí chất lượng

### 2.1. Bắt đầu từ tiêu chí có thể xác minh

Trước khi thiết kế kiểm thử, chuyển yêu cầu chất lượng thành tiêu chí có:

- Đối tượng hoặc thành phần được đánh giá.
- Thuộc tính cần xác minh.
- Điều kiện hoặc tải áp dụng.
- Phương pháp đo hoặc kiểm tra.
- Ngưỡng chấp nhận.
- Nguồn dữ liệu có thẩm quyền.
- Phạm vi và ngoại lệ.
- Bằng chứng cần lưu.

Ví dụ, tiêu chí “API phải nhanh” chưa đủ để xác định bằng chứng. Có thể cụ thể hóa thành: “Trong môi trường performance được chỉ định, với tải ổn định 200 request/giây trong 15 phút và dataset đã định nghĩa, p95 latency của endpoint tìm kiếm không vượt 400 ms; tỷ lệ lỗi dưới ngưỡng đã thống nhất; kết quả phải kèm cấu hình tải, phiên bản artifact và metrics hệ thống.”

Các con số trong ví dụ chỉ minh họa cách viết. Ngưỡng thật cần được xác nhận từ yêu cầu sản phẩm, mục tiêu vận hành hoặc thỏa thuận dịch vụ.

### 2.2. Lập ma trận tiêu chí – phép kiểm tra – bằng chứng

Mỗi tiêu chí cần liên kết với phương pháp kiểm tra và bằng chứng tương ứng.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Criterion ID | Tiêu chí nào đang được xác minh? | PERF-API-01 |
| Thuộc tính | Điều gì cần đo hoặc quan sát? | p95 response time |
| Điều kiện | Trong môi trường và tải nào? | 200 req/s, 15 phút |
| Phương pháp | Đo bằng công cụ hoặc quy trình nào? | Load test với kịch bản cố định |
| Ngưỡng | Điều kiện đạt là gì? | p95 không vượt ngưỡng đã duyệt |
| Nguồn có thẩm quyền | Dữ liệu nào được dùng để kết luận? | Load generator và telemetry server |
| Bằng chứng bắt buộc | Cần lưu những gì? | Kết quả thô, cấu hình tải, metrics, build ID |
| Người đánh giá | Ai xác nhận kết quả? | QA/performance owner |
| Giới hạn | Điều gì chưa được kiểm tra? | Chưa đo trên topology production |

Ma trận này giúp tránh trường hợp có test case nhưng không có cách xác định bằng chứng cần lưu, hoặc có số liệu nhưng không biết nó chứng minh tiêu chí nào.

### 2.3. Xác định mức bằng chứng theo rủi ro

Không phải mọi tiêu chí đều cần cùng mức chi tiết. Có thể chia theo mức rủi ro:

- **Rủi ro thấp:** kết quả test, phiên bản và dữ liệu chính có thể đủ.
- **Rủi ro trung bình:** cần thêm cấu hình môi trường, log hoặc dữ liệu trước/sau để tái hiện.
- **Rủi ro cao:** cần bằng chứng độc lập hoặc đối chiếu chéo, kiểm soát tính toàn vẹn, người đánh giá và quyết định được ghi nhận.
- **Rủi ro trọng yếu:** cần nguồn dữ liệu có thẩm quyền, kiểm tra chéo, kiểm soát truy cập và phê duyệt theo quy trình của tổ chức.

Ví dụ, kiểm tra văn bản trợ giúp có thể chỉ cần ảnh chụp và checklist review. Kiểm tra số tiền hoàn cần request, giao dịch gốc, giao dịch hoàn, trạng thái cuối và đối soát từ nguồn có thẩm quyền.

### 2.4. Quy định bằng chứng trước khi thực thi

Bằng chứng cần được xác định trong test plan hoặc test design trước khi chạy, không đợi đến lúc kiểm thử thất bại mới tìm cách thu thập. Trước khi chạy, cần biết:

- Công cụ nào tạo ra bằng chứng?
- Bằng chứng được lưu ở đâu?
- Có cần thu thập dữ liệu thô hay chỉ báo cáo tổng hợp?
- Ai có quyền đọc và phê duyệt?
- Thời gian lưu là bao lâu?
- Có dữ liệu nhạy cảm cần che hoặc loại bỏ không?
- Nếu nguồn đo bị lỗi thì kết quả được phân loại thế nào?

Nếu không thể thu thập một bằng chứng bắt buộc, cần ghi nhận điều đó là giới hạn hoặc blocker thay vì mặc định tiêu chí đã đạt.

## 3. Chọn loại bằng chứng phù hợp với mục tiêu

### 3.1. Bằng chứng thực thi

Bằng chứng thực thi mô tả test case đã được chạy như thế nào:

- Test ID và phiên bản test.
- Tiền điều kiện và dữ liệu.
- Các bước hoặc hành động.
- Kết quả mong đợi và thực tế.
- Trạng thái pass, fail, blocked hoặc skipped.
- Thời điểm và người hoặc hệ thống thực hiện.

Bằng chứng này giúp xác định một trường hợp đã chạy thật hay chỉ được đánh dấu hoàn tất trong công cụ quản lý.

### 3.2. Bằng chứng trạng thái và dữ liệu

Dùng khi cần xác nhận tác dụng phụ hoặc kết quả nghiệp vụ:

- Bản ghi trước và sau thao tác.
- Mã định danh đối tượng.
- Trạng thái và các trường quan trọng.
- Số lượng, số tiền hoặc quan hệ giữa các bản ghi.
- Event hoặc giao dịch phát sinh.
- Kết quả đối soát từ nguồn dữ liệu có thẩm quyền.

Ví dụ, để xác nhận hủy đơn, cần chứng minh trạng thái đơn đã chuyển đúng và không có giao dịch hoặc tác dụng phụ trái quy tắc. Chỉ có toast “Đã hủy” trên giao diện là bằng chứng chưa đủ nếu dữ liệu phía server chưa được xác minh.

### 3.3. Bằng chứng kỹ thuật và quan sát hệ thống

Có thể bao gồm:

- Log ứng dụng và nền tảng.
- Trace phân tán.
- Metrics tài nguyên và dịch vụ.
- Event ID, queue offset hoặc message metadata.
- Network trace hoặc thông tin giao tiếp.
- Deployment status và cấu hình.
- Crash report hoặc dump theo chính sách.

Các nguồn này giúp chẩn đoán nguyên nhân và liên kết sự kiện xuyên hệ thống. Cần biết nguồn nào có thể bị sampling, trễ, mất hoặc thay đổi định dạng.

### 3.4. Bằng chứng đo lường

Bằng chứng đo lường cần có giá trị thô hoặc dữ liệu đủ để kiểm tra phép tính:

- Mẫu thời gian phản hồi.
- Số request thành công và thất bại.
- Throughput theo khoảng thời gian.
- Phân bố độ trễ và percentile.
- CPU, RAM, I/O và queue depth.
- Kích thước dữ liệu và số bản ghi.
- Độ chính xác hoặc sai số của kết quả.
- Cấu hình, công cụ và phiên bản đo.

Chỉ lưu một ảnh biểu đồ hoặc một con số cuối có thể không đủ để xác minh cách tổng hợp. Với tiêu chí quan trọng, giữ dữ liệu thô hoặc báo cáo máy đọc được cùng phương pháp tính.

### 3.5. Bằng chứng trực quan và đánh giá chuyên gia

Ảnh chụp, video, bản ghi thao tác hoặc checklist review hữu ích cho:

- Giao diện và hành trình người dùng.
- Khả năng truy cập.
- Nội dung và thông báo.
- Hành vi tương tác.
- Quy trình nghiệp vụ cần đánh giá trực quan.

Bằng chứng trực quan cần gắn với phiên bản, thiết bị, trình duyệt, kích thước màn hình và trạng thái đã kiểm tra. Một ảnh đơn lẻ không chứng minh toàn bộ hành trình hoặc khả năng sử dụng trong mọi điều kiện.

### 3.6. Bằng chứng phê duyệt và quyết định

Với tiêu chí có ngoại lệ hoặc rủi ro còn lại, lưu:

- Người có thẩm quyền quyết định.
- Phạm vi và lý do chấp nhận.
- Bằng chứng đã xem xét.
- Biện pháp giảm thiểu.
- Điều kiện hoặc thời hạn xem xét lại.
- Liên kết tới lỗi, risk record hoặc release decision.

Sự đồng ý bằng lời nói không có ghi nhận có thể không đủ để truy vết sau này.

## 4. Xác định điều kiện đo hợp lệ

### 4.1. Đo đúng thuộc tính cần đánh giá

Trước tiên, xác định phép đo có đại diện cho khái niệm cần đánh giá hay không (construct validity).

Ví dụ:

- Nếu cần đo trải nghiệm phản hồi của người dùng, đo từ phía client có thể phù hợp hơn chỉ đo thời gian xử lý nội bộ của server.
- Nếu cần đo tỷ lệ giao dịch hoàn tất, không thể chỉ đếm HTTP 200 nếu nghiệp vụ còn xử lý bất đồng bộ.
- Nếu cần đo khả năng hoàn thành tác vụ bằng bàn phím, phải thực hiện tác vụ bằng bàn phím thay vì suy luận từ DOM.
- Nếu cần đo tính sẵn sàng của dịch vụ, một lần gọi health endpoint không đủ đại diện cho thời gian hoạt động trong cả tháng.

Cần mô tả chính xác điểm bắt đầu, điểm kết thúc và ý nghĩa của phép đo.

### 4.2. Công cụ đo phù hợp và được kiểm tra

Công cụ cần phù hợp với đại lượng và phạm vi:

- Đồng hồ hoặc timer đủ độ phân giải cho thời gian cần đo.
- Load generator đủ năng lực để tạo tải mục tiêu.
- Metrics collector có đơn vị và sampling interval rõ.
- Công cụ kiểm tra tương phản hoặc accessibility phù hợp với tiêu chí.
- Bộ đếm hoặc nguồn dữ liệu có thẩm quyền cho số giao dịch.
- Instrumentation không làm thay đổi đáng kể hành vi được đo.

Kiểm tra phiên bản, cấu hình, giới hạn và cách công cụ tính kết quả. Nếu công cụ có sai số, sampling hoặc làm tròn, cần hiểu ảnh hưởng của chúng đến ngưỡng chấp nhận.

### 4.3. Độ chính xác, độ chụm và độ phân giải

Ba khái niệm cần phân biệt:

- **Độ chính xác (accuracy):** mức gần với giá trị đúng hoặc giá trị tham chiếu.
- **Độ chụm (precision):** mức độ các phép đo lặp lại gần nhau.
- **Độ phân giải (resolution):** mức thay đổi nhỏ nhất mà công cụ có thể phân biệt.

Một timer chỉ ghi đến giây không phù hợp để đánh giá ngưỡng 50 ms. Một load generator tự nó đã quá tải có thể báo latency cao dù server chưa đạt giới hạn. Một metric được làm tròn có thể che việc giá trị nằm sát ngưỡng.

Khi ngưỡng chấp nhận gần với sai số đo, cần cải thiện công cụ hoặc phương pháp, dùng khoảng không chắc chắn phù hợp hoặc xác định vùng cần đánh giá thêm.

### 4.4. Độ lặp lại và khả năng tái lập

- **Repeatability:** kết quả gần nhau khi cùng người, cùng công cụ, cùng phương pháp và điều kiện gần như không đổi.
- **Reproducibility:** kết quả có thể được tạo lại khi thay đổi người thực hiện, thiết bị hoặc môi trường trong phạm vi được xác định.

Đối với kiểm thử tự động, cần lưu phiên bản test, dữ liệu, seed, cấu hình và artifact. Đối với đo hiệu năng, cần ghi mô hình tải, thời gian warm-up, thời gian đo, số lần chạy và trạng thái hạ tầng.

Không yêu cầu mọi lần đo phải có kết quả giống hệt nhau. Cần xác định mức biến thiên chấp nhận được và phân biệt biến thiên tự nhiên với lỗi của sản phẩm hoặc phương pháp.

### 4.5. Hiệu chuẩn và kiểm tra công cụ đo

Với thiết bị hoặc công cụ đo có yêu cầu chính xác, xác định:

- Công cụ có cần hiệu chuẩn định kỳ không?
- Có chứng nhận hoặc nguồn tham chiếu không?
- Phiên bản phần mềm và cấu hình nào ảnh hưởng kết quả?
- Có kiểm tra trước khi dùng không?
- Khi công cụ hết hạn hiệu chuẩn hoặc có lỗi, các kết quả trước đó có bị ảnh hưởng không?

Trong kiểm thử phần mềm, “hiệu chuẩn” có thể là kiểm tra timer, đồng bộ đồng hồ, xác minh load generator, đối chiếu metric với nguồn độc lập hoặc xác nhận bộ đếm. Không phải mọi công cụ đều cần chứng nhận đo lường chính thức; mức kiểm soát phải tương xứng với quyết định dựa trên phép đo.

## 5. Kiểm soát điều kiện môi trường và yếu tố gây nhiễu

### 5.1. Ghi điều kiện môi trường

Một phép đo chỉ có thể được diễn giải khi biết điều kiện thực thi. Ghi các thông tin liên quan:

- Môi trường, vùng và topology.
- Phiên bản ứng dụng, service và dependency.
- CPU, RAM, lưu trữ và giới hạn tài nguyên.
- Cấu hình, feature flag và cache.
- Dataset, trạng thái ban đầu và kích thước dữ liệu.
- Mạng, latency và phụ thuộc ngoài.
- Số lượng worker, thread hoặc instance.
- Thời gian, timezone và lịch chạy.
- Tải nền và các job khác đang hoạt động.

Không cần ghi mọi chi tiết nếu chúng không ảnh hưởng phép đo, nhưng phải nêu các điều kiện có khả năng làm thay đổi kết quả.

### 5.2. Nhận diện yếu tố gây nhiễu

Yếu tố gây nhiễu (confounding factor) là biến ngoài mục tiêu có thể ảnh hưởng kết quả, khiến nhóm quy nhầm nguyên nhân.

Ví dụ khi đo latency:

- Một job backup chạy cùng thời điểm.
- Cache đã nóng ở lần chạy thứ hai.
- Load generator dùng chung CPU với ứng dụng.
- Một dịch vụ ngoài có độ trễ biến động.
- Network route khác giữa các lần chạy.
- Dataset thay đổi hoặc phân bố không giống nhau.

Khi có yếu tố gây nhiễu, hãy cô lập, kiểm soát hoặc ghi nhận để phân tích. Không nên loại một kết quả bất lợi chỉ vì nó không giống mong đợi; cần có căn cứ cho thấy phép đo bị ảnh hưởng ngoài phạm vi.

### 5.3. Chuẩn bị trạng thái ban đầu

Trước khi đo hoặc chạy kiểm thử:

- Xác nhận dữ liệu và trạng thái đúng.
- Xác định cache nóng hay lạnh theo mục tiêu.
- Làm rõ dịch vụ đã warm-up chưa.
- Kiểm tra queue tồn đọng hoặc job nền.
- Xác nhận cấu hình và số instance.
- Bảo đảm các test khác không thay đổi dữ liệu dùng chung.
- Ghi nhận mọi thao tác setup có thể ảnh hưởng kết quả.

Nếu tiêu chí cần đo cold start, không được warm-up theo cách làm mất điều kiện cần đo. Nếu mục tiêu là hiệu năng ổn định, cần xác định warm-up và thời gian đo riêng.

### 5.4. Kiểm soát tải và lấy mẫu

Với performance test, mô tả:

- Số virtual users hoặc request rate.
- Phân bố hành động và think time.
- Ramp-up, steady state và ramp-down.
- Thời gian warm-up.
- Cửa sổ đo.
- Số lần lặp.
- Phân bố dữ liệu và tỷ lệ cache hit dự kiến.
- Tỷ lệ lỗi và timeout được tính thế nào.

Với phép đo khác, cũng cần xác định mẫu đại diện. Ví dụ, kiểm tra accessibility trên một số trang phải chọn trang theo mẫu component và hành trình; kiểm tra dữ liệu cần bao phủ các nhóm, trạng thái và giá trị biên quan trọng.

### 5.5. Kiểm tra tính đầy đủ của dữ liệu đo

Một phép đo có thể không hợp lệ nếu:

- Một phần request không được ghi nhận.
- Log bị sampling mà không có thông tin về tỷ lệ.
- Metrics mất dữ liệu trong khoảng quan trọng.
- Clock giữa các nguồn lệch đáng kể.
- Collector bị quá tải.
- Kết quả bị cắt do timeout hoặc giới hạn lưu trữ.
- Bộ đếm tính trùng hoặc bỏ sót sự kiện.

Trước khi đánh giá ngưỡng, xác nhận dữ liệu đo đầy đủ trong phạm vi cần thiết. Nếu thiếu dữ liệu, phân loại kết quả là không đủ bằng chứng hoặc không kết luận được.

## 6. Quy định phép đo, đơn vị và ngưỡng chấp nhận

### 6.1. Định nghĩa phép đo không mơ hồ

Mỗi metric cần có:

- Tên và mục đích.
- Định nghĩa chính xác.
- Công thức hoặc cách thu thập.
- Đơn vị.
- Nguồn dữ liệu.
- Cửa sổ thời gian.
- Cách xử lý mẫu thiếu hoặc lỗi.
- Phương pháp tổng hợp.
- Ngưỡng và điều kiện đạt.

Ví dụ, “error rate” cần nói rõ mẫu số là tổng request, request hợp lệ hay giao dịch đã bắt đầu; lỗi client, lỗi server và timeout có được tính không; retry có được tính là request mới không.

### 6.2. Chọn đúng cách tổng hợp

Không dùng trung bình cho mọi phân bố. Với latency, percentile thường giúp thấy trải nghiệm ở phần đuôi:

- p50 mô tả trung vị.
- p90 hoặc p95 mô tả phần lớn request ở mức chậm hơn.
- p99 giúp quan sát tail latency.

Một giá trị trung bình tốt có thể che một nhóm request rất chậm. Ngược lại, percentile cao từ mẫu quá nhỏ có thể không ổn định. Cần ghi số lượng mẫu và cửa sổ đo khi diễn giải percentile.

Với tỷ lệ, ghi rõ tử số và mẫu số. Với dung lượng, ghi đơn vị và cách quy đổi. Với thời gian, ghi đơn vị, timezone nếu là thời điểm lịch và độ phân giải của timer.

### 6.3. Đặt ngưỡng và vùng không chắc chắn

Ngưỡng phải được xác định trước khi chạy, có căn cứ từ yêu cầu, baseline, SLA/SLO hoặc quyết định của chủ sở hữu chất lượng.

Ví dụ:

- p95 latency không vượt ngưỡng.
- Error rate thấp hơn giới hạn.
- Không có lỗi bảo mật ở mức bị cấm theo chính sách.
- Tỷ lệ giao dịch thành công đạt mục tiêu.
- Migration không làm mất hoặc sai lệch dữ liệu.
- Hành trình truy cập quan trọng hoàn thành bằng phương thức được hỗ trợ.

Nếu phép đo có độ không chắc chắn và kết quả nằm sát ngưỡng, không nên tự động kết luận đạt bằng cách làm tròn. Có thể cần thêm mẫu, công cụ tốt hơn hoặc quy tắc vùng quyết định được thống nhất trước.

### 6.4. Không thay đổi ngưỡng sau khi thấy kết quả

Thay đổi ngưỡng sau khi đo để biến fail thành pass làm giảm độ tin cậy của đánh giá. Nếu ngưỡng cần điều chỉnh vì yêu cầu hoặc điều kiện đo đã thay đổi:

1. Ghi lý do và nguồn quyết định.
2. Đánh giá ảnh hưởng đến tiêu chí và kết quả trước.
3. Có người có thẩm quyền phê duyệt.
4. Cập nhật phiên bản tiêu chí.
5. Chạy lại hoặc đánh giá lại bằng chứng theo ngưỡng mới.
6. Giữ lịch sử ngưỡng cũ và quyết định thay đổi.

Không xóa lịch sử kết quả bất lợi hoặc sửa report đã phát hành mà không lưu dấu vết.

## 7. Ví dụ điều kiện đo hợp lệ theo loại kiểm thử

### 7.1. Kiểm thử chức năng và API

Bằng chứng cần có:

- Test ID, phiên bản API và endpoint.
- Request đã làm sạch, response và mã trạng thái.
- Dữ liệu và trạng thái ban đầu.
- Kết quả nghiệp vụ sau thao tác.
- Nguồn xác minh trạng thái có thẩm quyền.
- Timestamp, correlation ID và môi trường.

Điều kiện đo hợp lệ:

- Test gọi đúng phiên bản và endpoint.
- Tài khoản có quyền phù hợp với mục tiêu.
- Dữ liệu tiền điều kiện tồn tại và được xác minh.
- Assertion kiểm tra đúng hành vi cần chứng minh.
- Không có phụ thuộc bị mô phỏng ngoài phạm vi kết luận.

Ví dụ, kiểm tra API hoàn tiền cần đối chiếu số tiền đã thu, số tiền đã hoàn, số tiền yêu cầu và giao dịch cuối cùng. Response 200 không đủ để chứng minh số tiền hoàn chính xác.

### 7.2. Kiểm thử tích hợp và E2E

Bằng chứng cần có:

- Các thành phần tham gia và phiên bản.
- Thành phần thật, sandbox, mock hoặc stub.
- Dữ liệu xuyên hệ thống và mã tương quan.
- Request, event và kết quả cuối.
- Log/trace hoặc trạng thái ở nguồn có thẩm quyền.
- Các bước và nhánh đã chạy.

Điều kiện hợp lệ:

- Các dịch vụ liên quan sẵn sàng và đúng phiên bản.
- Hợp đồng và cấu hình phù hợp.
- Dữ liệu được cô lập và có quan hệ đúng.
- Trạng thái bất đồng bộ được chờ theo điều kiện quan sát.
- Giới hạn do mock hoặc môi trường được ghi rõ.

### 7.3. Kiểm thử hiệu năng

Bằng chứng cần có:

- Build, cấu hình và topology.
- Công cụ và phiên bản load generator.
- Mô hình tải, số mẫu và thời gian chạy.
- Dataset và trạng thái cache.
- Latency distribution, throughput và error rate.
- CPU, RAM, I/O, network và queue metrics.
- Log hoặc trace khi có bất thường.

Điều kiện hợp lệ:

- Load generator đủ năng lực và không trở thành nút thắt.
- Tải được tạo đúng mô hình.
- Warm-up và steady-state được phân biệt.
- Môi trường không có yếu tố gây nhiễu không được kiểm soát.
- Dữ liệu đủ lớn và đại diện cho mục tiêu.
- Phương pháp tổng hợp và ngưỡng được xác định trước.

### 7.4. Kiểm thử bảo mật

Bằng chứng có thể gồm:

- Phạm vi và quyền kiểm thử được phê duyệt.
- Phiên bản artifact, scanner và rule set.
- Cấu hình quét và credential scope.
- Findings, mức độ, bằng chứng tái hiện.
- Kết quả xác minh thủ công cho phát hiện quan trọng.
- False positive có căn cứ và quyết định xử lý.

Điều kiện hợp lệ:

- Kiểm tra đúng tài sản và phiên bản trong phạm vi.
- Scanner được cập nhật và cấu hình phù hợp.
- Credential không vượt quyền được phép.
- Không thực hiện thao tác ngoài phạm vi phê duyệt.
- Findings được phân loại và xác minh, không chỉ dựa vào số lượng cảnh báo.

### 7.5. Kiểm thử khả năng truy cập

Bằng chứng có thể gồm:

- Tiêu chí và phiên bản tiêu chuẩn áp dụng.
- Trang, component và hành trình đã kiểm tra.
- Trình duyệt, hệ điều hành và công nghệ hỗ trợ.
- Các bước bàn phím hoặc trình đọc màn hình.
- Kết quả quét tự động và kiểm tra thủ công.
- Ảnh, video hoặc ghi chú thao tác phù hợp.

Điều kiện hợp lệ:

- Công nghệ hỗ trợ thuộc ma trận mục tiêu.
- Kiểm tra trong trạng thái và hành trình thực tế.
- Không dùng kết quả tự động thay cho đánh giá thủ công cần thiết.
- Nội dung và ngữ cảnh được xem xét, không chỉ thuộc tính DOM.

### 7.6. Kiểm thử migration và tính toàn vẹn dữ liệu

Bằng chứng cần có:

- Phiên bản schema trước và sau.
- Dataset và số lượng bản ghi.
- Quy tắc chuyển đổi.
- Kết quả đối chiếu trước/sau.
- Số bản ghi lỗi, bỏ qua hoặc xử lý lại.
- Log migration và thời gian thực thi.
- Kết quả kiểm tra ràng buộc và quan hệ.

Điều kiện hợp lệ:

- Dataset đại diện cho cấu trúc và trạng thái cần hỗ trợ.
- Có baseline hoặc snapshot trước migration.
- Đối chiếu dùng cùng quy tắc và đơn vị.
- Không có thao tác ghi ngoài phạm vi.
- Có thể tái hiện hoặc điều tra bản ghi sai lệch.

## 8. Đánh giá kết quả thiếu, không ổn định hoặc mâu thuẫn

### 8.1. Phân biệt các trạng thái kết quả

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Pass | Bằng chứng đủ và đáp ứng tiêu chí trong điều kiện đã nêu | Ghi kết luận và phạm vi |
| Fail | Bằng chứng hợp lệ cho thấy tiêu chí không đạt | Mở lỗi, đánh giá ảnh hưởng và xử lý |
| Blocked | Không thể thực hiện do môi trường, quyền hoặc phụ thuộc | Ghi nguyên nhân và điều kiện cần để chạy |
| Inconclusive | Có dữ liệu nhưng không đủ để kết luận | Bổ sung mẫu, nguồn hoặc phép đo |
| Invalid measurement | Phương pháp hoặc điều kiện đo không hợp lệ | Không dùng kết quả để kết luận; sửa phép đo và chạy lại |
| Skipped | Không chạy theo thiết kế hoặc quyết định | Ghi lý do và rủi ro còn lại |
| Accepted risk | Rủi ro được người có thẩm quyền chấp nhận | Ghi quyết định, biện pháp và thời hạn xem xét |

Không nên gộp inconclusive hoặc invalid measurement vào pass. Cũng không nên xem blocked là fail của sản phẩm nếu nguyên nhân là môi trường, nhưng vẫn phải ghi rằng tiêu chí chưa được xác minh.

### 8.2. Xử lý flaky test và biến thiên tự nhiên

Khi kết quả dao động giữa các lần chạy:

1. Lưu kết quả từng lần, không chỉ kết quả cuối.
2. So sánh dữ liệu, cấu hình, tải và môi trường.
3. Xác định nguồn biến thiên có thể kiểm soát.
4. Kiểm tra trạng thái chia sẻ, thời gian, random seed và thứ tự chạy.
5. Đánh giá xem phép đo có đủ mẫu và độ ổn định không.
6. Sửa nguyên nhân hoặc phân loại kết quả chưa kết luận.
7. Chỉ dùng retry theo quy tắc đã định và giữ lịch sử retry.

Một lần pass sau nhiều lần fail không tự động chứng minh tiêu chí đạt. Cần hiểu vì sao các lần chạy khác nhau và xác định phương pháp đánh giá trước.

### 8.3. Xử lý dữ liệu đo mâu thuẫn

Ví dụ load generator báo p95 500 ms nhưng telemetry server báo p95 200 ms. Trước khi chọn một con số:

- Xác minh hai phép đo có cùng điểm bắt đầu/kết thúc không.
- Kiểm tra đơn vị, sampling và cửa sổ thời gian.
- Kiểm tra request có bị loại, retry hoặc queue ở phía client không.
- Đối chiếu correlation ID hoặc trace.
- Kiểm tra đồng hồ và độ trễ thu thập.
- Ghi rõ metric nào là nguồn có thẩm quyền cho tiêu chí.

Các số liệu khác nhau không nhất thiết có một số sai. Chúng có thể đo các đoạn khác nhau của hành trình. Cần làm rõ định nghĩa trước khi so sánh.

### 8.4. Không loại bỏ outlier tùy tiện

Một số mẫu rất chậm hoặc rất nhanh có thể là lỗi thực tế, không phải nhiễu. Nếu loại bỏ outlier:

- Nêu quy tắc loại bỏ đã xác định trước.
- Ghi số mẫu bị loại và lý do.
- Báo cáo kết quả có và không có outlier khi phù hợp.
- Đánh giá liệu outlier có tương ứng với rủi ro người dùng trải nghiệm.
- Không thay đổi quy tắc chỉ để đạt ngưỡng.

Với latency, tail event có thể là phần quan trọng nhất của trải nghiệm. Cần cẩn trọng khi dùng trung bình hoặc lọc mẫu.

## 9. Bảo vệ tính toàn vẹn và khả năng truy vết của bằng chứng

### 9.1. Liên kết bằng chứng với phiên bản và lần chạy

Mỗi bằng chứng cần có đủ định danh để biết nó thuộc về:

- Requirement hoặc quality criterion.
- Test case và test suite.
- Build, commit hoặc artifact digest.
- Environment và cấu hình.
- Test run ID.
- Thời điểm và timezone.
- Người hoặc hệ thống thực hiện.
- Nguồn thu thập và phiên bản công cụ.

Nếu ảnh chụp hoặc report không có phiên bản, người đọc có thể nhầm bằng chứng của bản cũ với bản mới.

### 9.2. Bảo đảm bằng chứng không bị sửa đổi ngoài kiểm soát

Tùy mức rủi ro, có thể dùng:

- Kho artifact có phân quyền.
- Lưu trữ chỉ đọc sau khi hoàn tất.
- Checksum hoặc hash để phát hiện thay đổi.
- Chữ ký hoặc metadata nguồn gốc.
- Audit log cho thao tác tải lên, sửa hoặc xóa.
- Quy trình phê duyệt và versioning.
- Thời hạn lưu và chính sách backup.

Hash có thể giúp phát hiện nội dung thay đổi so với giá trị đã ghi, nhưng không tự chứng minh người tạo hoặc tính đúng của phép đo. Cần kết hợp nguồn gốc, quyền và quy trình thu thập.

### 9.3. Bảo vệ dữ liệu nhạy cảm

Bằng chứng có thể chứa token, cookie, địa chỉ email, thông tin thanh toán, dữ liệu cá nhân hoặc bí mật kinh doanh.

Cần:

- Thu thập lượng dữ liệu tối thiểu cần thiết.
- Che hoặc loại bỏ secret trước khi lưu.
- Dùng dữ liệu tổng hợp hoặc đã xử lý theo chính sách.
- Phân quyền theo vai trò và nhu cầu.
- Quy định thời hạn lưu và xóa.
- Kiểm tra quyền chia sẻ report và artifact.
- Không đính kèm dữ liệu nhạy cảm vào ticket công khai hoặc kênh không được phép.

Che dữ liệu cần giữ đủ ngữ cảnh để điều tra. Ví dụ, có thể dùng mã định danh giả ổn định thay cho tên thật để vẫn liên kết được nhiều bản ghi.

### 9.4. Quản lý lưu trữ và thời hạn giữ bằng chứng

Thời gian lưu phụ thuộc yêu cầu kiểm toán, hợp đồng, quy định và nhu cầu điều tra. Xác định:

- Loại bằng chứng nào cần lưu dài hạn.
- Loại nào chỉ cần lưu trong thời gian ngắn.
- Nơi lưu và người có quyền truy cập.
- Cách tìm kiếm theo build, test run hoặc criterion.
- Cách xóa theo retention policy.
- Cách giữ bằng chứng khi có sự cố hoặc yêu cầu điều tra.

Không lưu mọi log vô thời hạn nếu điều đó làm tăng rủi ro bảo mật và chi phí. Cũng không xóa bằng chứng bắt buộc trước khi quyết định hoặc kiểm toán hoàn tất.

## 10. Tổ chức quy trình thu thập và đánh giá bằng chứng

### 10.1. Trước khi thực thi

- Xác định tiêu chí và phạm vi.
- Định nghĩa phép đo, đơn vị và ngưỡng.
- Chọn công cụ và nguồn có thẩm quyền.
- Ghi điều kiện môi trường, dữ liệu và trạng thái.
- Xác định bằng chứng bắt buộc và vị trí lưu.
- Kiểm tra công cụ, clock, cấu hình và quyền truy cập.
- Xác định người đánh giá và người phê duyệt.

### 10.2. Trong khi thực thi

- Gắn test run ID hoặc correlation ID.
- Thu thập dữ liệu theo phương pháp đã định.
- Ghi nhận mọi thay đổi điều kiện hoặc sự cố.
- Không sửa ngưỡng giữa lần chạy.
- Giữ kết quả từng lần và dữ liệu cần thiết.
- Bảo vệ secret và dữ liệu nhạy cảm.
- Kiểm tra collector hoặc công cụ đo không bị lỗi.

### 10.3. Sau khi thực thi

- Xác nhận dữ liệu đo đầy đủ.
- Tính metric theo công thức đã định.
- Đối chiếu với ngưỡng.
- Phân loại pass, fail, blocked, inconclusive hoặc invalid.
- Kiểm tra bất thường và mâu thuẫn.
- Liên kết bằng chứng với criterion và artifact.
- Ghi giới hạn, rủi ro và hành động.
- Đưa ra kết luận trong phạm vi đã được chứng minh.

### 10.4. Luồng đánh giá bằng chứng

~~~mermaid
flowchart TD
    A[Tiêu chí chất lượng] --> B[Định nghĩa phép đo và bằng chứng]
    B --> C[Kiểm tra công cụ và điều kiện]
    C --> D[Thực thi và thu thập]
    D --> E{Dữ liệu đầy đủ và hợp lệ?}
    E -- Không --> F[Invalid / Inconclusive / Blocked]
    F --> G[Bổ sung điều kiện hoặc đo lại]
    G --> C
    E -- Có --> H[Phân tích và so với ngưỡng]
    H --> I{Đáp ứng tiêu chí?}
    I -- Không --> J[Fail và đánh giá rủi ro]
    I -- Có --> K[Pass trong phạm vi bằng chứng]
    J --> L[Quyết định và hành động]
    K --> L
~~~

Luồng này nhấn mạnh rằng chỉ được đánh giá ngưỡng sau khi xác nhận phép đo hợp lệ. Nếu dữ liệu không đầy đủ, không nên tính ra một kết quả có vẻ chính xác rồi dùng nó để ra quyết định.

## 11. Mẫu hồ sơ bằng chứng bắt buộc

### 11.1. Mẫu Evidence Record

| Trường | Nội dung cần ghi |
|---|---|
| Evidence ID | Mã bằng chứng duy nhất |
| Criterion ID | Tiêu chí chất lượng được xác minh |
| Requirement / Risk | Yêu cầu hoặc rủi ro liên quan |
| Test ID / Run ID | Trường hợp và lần chạy |
| Artifact | Build, commit, package hoặc digest |
| Environment | Môi trường, vùng và cấu hình |
| Preconditions | Dữ liệu và trạng thái ban đầu |
| Method | Phương pháp thực thi hoặc đo |
| Tool | Công cụ, phiên bản và cấu hình |
| Measurement | Đại lượng, đơn vị, công thức và cửa sổ đo |
| Threshold | Ngưỡng và phiên bản tiêu chí |
| Actual result | Kết quả thực tế và dữ liệu hỗ trợ |
| Data completeness | Tính đầy đủ và nguồn bị thiếu nếu có |
| Validity assessment | Đánh giá công cụ, mẫu và điều kiện |
| Evidence location | Vị trí lưu và quyền truy cập |
| Integrity | Hash, version hoặc audit reference nếu cần |
| Limitations | Giới hạn và giả định |
| Verdict | Pass, fail, blocked, inconclusive hoặc invalid |
| Reviewer | Người đánh giá |
| Decision / Owner | Quyết định, người chịu trách nhiệm và hành động |

### 11.2. Ví dụ hồ sơ cho phép đo latency

| Trường | Giá trị minh họa |
|---|---|
| Criterion ID | PERF-SEARCH-01 |
| Test Run | RUN-2026-041 |
| Artifact | Build ID và digest đã ghi nhận |
| Environment | Performance staging |
| Dataset | Dataset tổng hợp theo profile đã duyệt |
| Load model | 200 request/giây, 15 phút steady state |
| Warm-up | 5 phút, tách khỏi cửa sổ đo |
| Metric | p95 end-to-end latency |
| Unit | Millisecond |
| Threshold | 400 ms theo tiêu chí minh họa |
| Actual | 365 ms |
| Samples | Số request hợp lệ được ghi nhận |
| Error rate | Ghi riêng theo định nghĩa đã duyệt |
| Validity | Load generator còn tài nguyên; không mất dữ liệu metrics |
| Limitations | Hạ tầng ít node hơn production |
| Verdict | Pass trong điều kiện staging đã nêu |

Ví dụ này chỉ minh họa cách ghi hồ sơ. Không thể kết luận hiệu năng production từ một lần đo staging nếu topology và tải khác đáng kể.

### 11.3. Mẫu kết luận có giới hạn

Một kết luận tốt nêu:

- Tiêu chí nào được đánh giá.
- Phép đo và ngưỡng nào được dùng.
- Điều kiện môi trường và dữ liệu.
- Kết quả thực tế.
- Tính hợp lệ và đầy đủ của phép đo.
- Giới hạn và rủi ro còn lại.
- Người đánh giá và quyết định.

Ví dụ:

> Criterion PERF-SEARCH-01 đạt trong performance staging với artifact digest đã ghi nhận, dataset và mô hình tải được mô tả. p95 end-to-end latency nằm dưới ngưỡng đã duyệt; dữ liệu metrics đầy đủ trong cửa sổ đo và load generator không bị quá tải. Môi trường có ít node hơn production nên kết quả chỉ chứng minh hiệu năng trong topology staging. Cần bổ sung kiểm tra trên cấu hình đại diện hơn trước khi kết luận về năng lực tải production.

## 12. Sử dụng bằng chứng trong quality gate và quyết định phát hành

### 12.1. Gate phải yêu cầu bằng chứng, không chỉ trạng thái

Một quality gate có thể quy định:

- Tiêu chí bắt buộc đã được thực thi.
- Bằng chứng được lưu và liên kết với artifact.
- Phép đo được xác nhận hợp lệ.
- Ngưỡng được xác định trước.
- Không có dữ liệu quan trọng bị thiếu.
- Người đánh giá đã xem xét kết quả.
- Lỗi và rủi ro còn lại được xử lý theo thẩm quyền.

Pipeline xanh chỉ cho biết các điều kiện tự động được cấu hình đã thành công. Nếu một test quan trọng bị skipped, dữ liệu đo bị thiếu hoặc công cụ sai cấu hình, gate không nên tuyên bố tiêu chí đã được xác minh.

### 12.2. Phân biệt pass với miễn trừ

Nếu một tiêu chí không thể kiểm tra trong lần phát hành:

- Ghi trạng thái blocked hoặc skipped.
- Nêu lý do và phạm vi ảnh hưởng.
- Xác định rủi ro còn lại.
- Đề xuất biện pháp giảm thiểu hoặc kiểm tra thay thế.
- Chuyển người có thẩm quyền quyết định.
- Ghi thời hạn hoặc điều kiện xem xét lại.

Miễn trừ có phê duyệt không biến phép đo thiếu thành pass. Báo cáo cần giữ đúng trạng thái để người ra quyết định hiểu điều gì chưa được chứng minh.

### 12.3. Bằng chứng độc lập cho quyết định quan trọng

Với thuộc tính có hậu quả cao, cân nhắc kiểm tra chéo bằng nguồn độc lập:

- So sánh số giao dịch từ API với ledger hoặc hệ thống đối soát.
- So sánh request count từ load generator với server metrics.
- Đối chiếu trạng thái migration với số bản ghi trước/sau.
- Xác minh scanner finding bằng kiểm tra thủ công.
- Đối chiếu deployment digest với artifact đã được kiểm thử.

Kiểm tra chéo không có nghĩa phải có hai công cụ cho mọi phép đo. Chọn nguồn độc lập khi sai số hoặc gian lận dữ liệu có thể làm thay đổi quyết định quan trọng.

## 13. Những sai lầm thường gặp

1. **Chỉ lưu trạng thái PASS:** không có dữ liệu hoặc ngữ cảnh để xác minh.
2. **Xác định bằng chứng sau khi chạy:** log hoặc metric cần thiết đã không được thu thập.
3. **Đo sai thuộc tính:** dùng trung bình khi tiêu chí yêu cầu percentile hoặc dùng health check thay cho hành vi nghiệp vụ.
4. **Không ghi đơn vị và công thức:** các nhóm tính cùng tên metric theo cách khác nhau.
5. **Không kiểm soát điều kiện môi trường:** kết quả bị ảnh hưởng bởi tải nền, cache, dữ liệu hoặc cấu hình.
6. **Dùng công cụ không đủ độ phân giải:** phép đo không thể phân biệt kết quả quanh ngưỡng.
7. **Không kiểm tra dữ liệu đo đầy đủ:** sampling hoặc mất telemetry làm kết luận sai.
8. **Thay ngưỡng sau khi thấy kết quả:** tạo thiên lệch và làm giảm tính khách quan.
9. **Loại outlier tùy tiện:** che giấu lỗi hiếm nhưng có tác động lớn.
10. **Coi retry là bằng chứng pass:** bỏ qua lịch sử thất bại và nguyên nhân biến thiên.
11. **Không bảo vệ bằng chứng:** để lộ secret hoặc dữ liệu cá nhân trong artifact.
12. **Không liên kết bằng chứng với artifact:** không biết kết quả thuộc phiên bản nào.
13. **Gộp blocked hoặc inconclusive vào pass:** tạo ấn tượng rằng tiêu chí đã được xác minh.
14. **Kết luận vượt phạm vi môi trường:** dùng kết quả staging để khẳng định mọi điều kiện production.
15. **Không có người đánh giá và chủ sở hữu rủi ro:** không rõ ai xác nhận phép đo hoặc quyết định ngoại lệ.

## 14. Checklist quy định bằng chứng bắt buộc và điều kiện đo hợp lệ

- [ ] Mỗi tiêu chí có mã, thuộc tính, điều kiện và ngưỡng rõ ràng.
- [ ] Phương pháp đo hoặc kiểm tra được xác định trước khi thực thi.
- [ ] Nguồn dữ liệu có thẩm quyền và loại bằng chứng bắt buộc đã được chỉ định.
- [ ] Bằng chứng liên kết với test case, run ID, artifact và môi trường.
- [ ] Công cụ đo phù hợp, phiên bản và cấu hình được ghi nhận.
- [ ] Độ chính xác, độ chụm, độ phân giải và sai số được xem xét khi cần.
- [ ] Điều kiện môi trường, dữ liệu, tải và trạng thái ban đầu được kiểm soát hoặc ghi rõ.
- [ ] Yếu tố gây nhiễu và tính đầy đủ của dữ liệu đo được đánh giá.
- [ ] Đơn vị, công thức, cửa sổ đo và cách tổng hợp được định nghĩa.
- [ ] Ngưỡng được thống nhất trước và có nguồn căn cứ.
- [ ] Kết quả sát ngưỡng hoặc có độ không chắc chắn được xử lý theo quy tắc đã định.
- [ ] Dữ liệu thô hoặc báo cáo đủ để kiểm tra phép tính được lưu khi cần.
- [ ] Pass, fail, blocked, skipped, inconclusive và invalid được phân biệt.
- [ ] Retry, flaky result và outlier được xử lý có lịch sử và căn cứ.
- [ ] Bằng chứng được bảo vệ, che dữ liệu nhạy cảm và lưu theo chính sách.
- [ ] Người đánh giá, người phê duyệt và chủ sở hữu rủi ro được xác định.
- [ ] Quality gate yêu cầu bằng chứng hợp lệ, không chỉ trạng thái pipeline.
- [ ] Kết luận nêu rõ phạm vi đã chứng minh và giới hạn còn lại.

Quy định bằng chứng bắt buộc và điều kiện đo hợp lệ giúp kết quả kiểm thử trở thành căn cứ đáng tin cậy cho quyết định chất lượng. Khi tiêu chí, phương pháp, công cụ, dữ liệu, môi trường, ngưỡng và nguồn bằng chứng được xác định trước, nhóm có thể phân biệt rõ điều đã được chứng minh với điều chưa đủ căn cứ, tái hiện kết quả và quản lý rủi ro minh bạch hơn.
