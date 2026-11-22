# Ghi nhận sự cố để cải tiến quy trình thay vì chỉ chạy lại cho thành công

Một pipeline đỏ rồi xanh sau khi bấm chạy lại có thể tạo cảm giác vấn đề đã biến mất. Nhưng lần chạy lại chỉ cho biết lần thực thi sau đã thành công trong điều kiện của nó. Nó không giải thích vì sao lần đầu thất bại, điều kiện nào đã thay đổi, hay lỗi có thể quay lại ở lần phát hành tiếp theo hay không.

Trong CI/CD, chạy lại là một thao tác khôi phục hoặc thu thập thêm tín hiệu. Ghi nhận sự cố mới là cách biến tín hiệu đó thành hiểu biết có thể hành động. Nhóm cần giữ lại bằng chứng, xác định tác động, tìm các điều kiện góp phần gây lỗi, giao việc cải tiến có người chịu trách nhiệm và kiểm tra xem thay đổi có thực sự giảm rủi ro hay không.

Bài học này trình bày cách phối hợp giữa phát triển, kiểm thử, vận hành và bảo mật để xử lý sự cố theo hướng học hỏi. Mục tiêu không phải tạo thêm thủ tục cho mọi lần build thất bại, mà là nhận diện đúng những vấn đề ảnh hưởng đến độ tin cậy của pipeline, việc phát hành hoặc người dùng.

## 1. Phân biệt lần chạy thất bại, sự kiện và sự cố

Không phải mọi job đỏ đều là một sự cố vận hành. Một unit test thất bại vì vừa phát hiện lỗi trong pull request có thể là phản hồi đúng mà pipeline được thiết kế để cung cấp. Ngược lại, một test thường xuyên timeout trên runner dùng chung, một artifact bị phát hành sai digest hoặc một lần triển khai làm gián đoạn dịch vụ có thể cần quy trình quản lý sự cố.

Có thể phân biệt ba khái niệm:

- **Lần chạy thất bại (failed run):** một lần thực thi job hoặc pipeline kết thúc không thành công. Đây là trạng thái kỹ thuật, chưa đủ để kết luận nguyên nhân hay mức độ tác động.
- **Sự kiện (event):** điều đã xảy ra và có thể quan sát được, chẳng hạn runner mất kết nối, dependency registry trả về HTTP 503, test timeout hoặc deployment health check thất bại.
- **Sự cố (incident):** một tình huống làm suy giảm đáng kể độ tin cậy, tính sẵn sàng, an toàn hoặc khả năng cung cấp phần mềm; cần phối hợp xử lý, đánh giá tác động và theo dõi đến khi rủi ro được kiểm soát.

Một sự cố có thể gồm nhiều lần chạy thất bại và nhiều sự kiện liên quan. Một lần chạy thất bại đơn lẻ cũng có thể trở thành sự cố nếu nó làm lộ bí mật, tạo artifact không đáng tin cậy hoặc gây ảnh hưởng cho người dùng.

Nhóm nên định nghĩa ngưỡng ghi nhận phù hợp với sản phẩm. Ví dụ, cần mở incident khi triển khai gây gián đoạn dịch vụ, pipeline phát hành bị chặn trên diện rộng, kết quả kiểm thử không đáng tin cậy lặp lại, artifact hoặc provenance bị nghi ngờ, hay có dấu hiệu lộ credential. Một lỗi kiểm thử dự kiến trên nhánh tính năng có thể chỉ cần xử lý như feedback của pull request.

Mức độ nghiêm trọng nên dựa trên tác động và phạm vi, không chỉ dựa trên màu đỏ của pipeline. Một job phụ trợ thất bại trong vài phút có thể có mức ảnh hưởng thấp; một lỗi xác minh chữ ký artifact có thể nghiêm trọng dù chưa có người dùng nào bị gián đoạn.

## 2. Vì sao chỉ chạy lại là chưa đủ?

Chạy lại có thể hữu ích trong một số tình huống:

- Một dịch vụ bên ngoài gặp lỗi tạm thời và đã phục hồi.
- Runner bị mất kết nối hoặc máy ảo bị thu hồi.
- Hệ thống kiểm thử phụ thuộc vào thời điểm, lịch chạy hoặc tài nguyên dùng chung.
- Một bài test không ổn định có thể thất bại ở lần này và thành công ở lần khác.

Tuy nhiên, kết quả chạy lại không chứng minh nguyên nhân ban đầu đã được loại bỏ. Khi lần chạy sau thành công, cần biết điều gì đã thay đổi: commit có giữ nguyên không, dependency có đổi không, runner có khác không, cache có được làm mới không, dữ liệu kiểm thử có được tạo lại không, và dịch vụ bên ngoài có phục hồi không.

Nếu nhóm chỉ ghi nhận trạng thái cuối cùng là “success”, các tín hiệu quan trọng sẽ biến mất:

- Tỷ lệ test không ổn định không được đo.
- Lỗi hạ tầng lặp lại bị che khuất bởi các lần retry.
- Thời gian chờ của nhóm phát triển tăng nhưng không xuất hiện trong báo cáo chất lượng.
- Một thay đổi có nguy cơ vẫn được phát hành mà không có người đánh giá.
- Các nhóm khác tiếp tục gặp cùng lỗi vì không có tri thức hoặc biện pháp phòng ngừa dùng chung.

Do đó, hãy lưu cả lần thất bại đầu tiên và các lần thử tiếp theo. Trạng thái cuối cùng có thể là thành công, nhưng hồ sơ vẫn cần thể hiện pipeline đã phải retry và lý do retry được chấp nhận.

## 3. Quy trình xử lý sự cố CI/CD

Một quy trình gọn có thể chia thành các bước nối tiếp nhau. Trong sự cố nghiêm trọng, một số bước diễn ra song song, nhưng việc ghi lại bằng chứng và quyết định vẫn phải có người chịu trách nhiệm.

~~~mermaid
flowchart TD
    A["Phát hiện tín hiệu bất thường"] --> B["Phân loại tác động và mức độ"]
    B --> C["Ổn định hệ thống, bảo vệ người dùng"]
    C --> D["Thu thập và bảo toàn bằng chứng"]
    D --> E["Dựng timeline và điều tra nguyên nhân"]
    E --> F["Ghi nhận bài học và yếu tố góp phần"]
    F --> G["Giao hành động cải tiến có người phụ trách"]
    G --> H["Triển khai thay đổi và đo hiệu quả"]
    H --> I{"Rủi ro đã giảm theo tiêu chí?"}
    I -->|Chưa| G
    I -->|Rồi| J["Đóng sự cố và cập nhật tri thức"]
~~~

### 3.1. Phát hiện và phân loại

Nguồn phát hiện có thể là cảnh báo pipeline, deployment health check, giám sát dịch vụ, báo cáo của người dùng, thông báo bảo mật hoặc phản ánh từ nhóm phát triển.

Khi tiếp nhận, hãy ghi lại thời điểm phát hiện, hệ thống bị ảnh hưởng, người hoặc nhóm báo cáo, biểu hiện quan sát được và mức độ khẩn cấp. Phân loại ban đầu có thể thay đổi khi có thêm bằng chứng; điều quan trọng là quyết định ban đầu được lưu cùng lý do.

### 3.2. Ổn định và giảm tác động

Ưu tiên khôi phục khả năng phục vụ và ngăn tác động lan rộng. Tùy tình huống, biện pháp có thể là dừng promotion, khóa một pipeline phát hành, chuyển traffic về phiên bản ổn định, thu hồi credential, vô hiệu hóa một runner pool hoặc tạm thời giới hạn concurrency.

Ghi lại ai quyết định, thời điểm thực hiện, phạm vi thay đổi và kết quả quan sát được. Nếu cần retry để xác định lỗi có tái hiện hay không, hãy xác nhận thao tác đó an toàn và không tạo tác dụng phụ như phát hành trùng, gửi thông báo hai lần hoặc chạy migration không idempotent.

### 3.3. Bảo toàn bằng chứng

Thu thập bằng chứng trước khi log hết hạn, runner bị xóa hoặc môi trường bị thay đổi. Không sửa nội dung log gốc để làm cho báo cáo dễ đọc hơn. Nếu cần trích đoạn hoặc chuẩn hóa dữ liệu, giữ liên kết đến bản gốc và ghi rõ cách tạo bản trích.

### 3.4. Điều tra và quyết định hành động

Dựng timeline, kiểm tra các thay đổi gần thời điểm xảy ra, phân biệt trigger với nguyên nhân nền và những điều kiện góp phần. Sau đó chuyển kết luận thành các hành động có người phụ trách, thời hạn và tiêu chí nghiệm thu.

### 3.5. Xác minh và đóng sự cố

Một ticket được đánh dấu hoàn thành không tự chứng minh rủi ro đã giảm. Hãy xác minh bằng test, metric, log, diễn tập hoặc quan sát qua một khoảng thời gian đủ đại diện. Nếu hành động chưa đạt tiêu chí, mở lại hoặc tạo hành động tiếp theo và giữ liên kết với sự cố gốc.

## 4. Thu thập bằng chứng có thể tái dựng

Bằng chứng tốt giúp người khác hiểu sự cố ngay cả khi họ không có mặt lúc xảy ra. Với CI/CD, nên thu thập các nhóm thông tin sau:

| Nhóm bằng chứng | Thông tin nên lưu | Câu hỏi được trả lời |
|---|---|---|
| Nhận diện thay đổi | Repository, commit SHA, pull request, branch, merge base | Mã nào đang được xác minh? |
| Pipeline | Pipeline/run ID, workflow hoặc pipeline definition revision, trigger, thời điểm bắt đầu/kết thúc | Luồng tự động nào đã chạy? |
| Job và attempt | Job ID, stage, step, số lần thử, exit code, thời lượng | Chính xác bước nào thất bại? |
| Worker | Runner/agent ID, image hoặc version, hệ điều hành, loại tài nguyên, pool | Lỗi có liên quan đến môi trường thực thi không? |
| Dependency | Lockfile, version đã resolve, registry, checksum | Build có dùng cùng dependency không? |
| Artifact | Tên, version, digest, build metadata, provenance | Đầu ra nào được tạo hoặc đưa đi triển khai? |
| Môi trường | Environment, deployment ID, cấu hình và revision có liên quan | Lỗi xảy ra ở đâu và với cấu hình nào? |
| Quan sát | Log, metric, trace, health check, sự kiện hạ tầng | Hệ thống biểu hiện ra sao trước và sau lỗi? |
| Tác động | Dịch vụ, người dùng, thời gian gián đoạn, release bị chặn | Ai hoặc điều gì bị ảnh hưởng? |

Không phải mọi sự cố đều cần toàn bộ trường trên. Hãy lưu tối thiểu những dữ liệu đủ để liên kết commit, pipeline, attempt, worker, artifact và môi trường.

Các thời điểm nên được ghi theo định dạng có múi giờ rõ ràng, ưu tiên UTC và ISO 8601. Đồng bộ thời gian giữa runner, hệ thống CI, registry và hệ thống quan sát giúp dựng timeline chính xác hơn.

Bảo vệ dữ liệu nhạy cảm trong suốt quá trình thu thập. Không đưa access token, private key, mật khẩu, cookie, nội dung secret hoặc dữ liệu cá nhân không cần thiết vào ticket hay báo cáo. Dùng ID tham chiếu đến secret hoặc hệ thống quản lý credential; che thông tin nhạy cảm trước khi chia sẻ log. Quyền truy cập bằng chứng phải theo nguyên tắc tối thiểu và thời hạn lưu giữ phù hợp.

Nếu nghi ngờ credential bị lộ, coi việc thu hồi hoặc xoay vòng credential là một hành động ứng phó riêng. Không chờ đến khi báo cáo nguyên nhân hoàn tất mới xử lý nguy cơ đang tồn tại.

## 5. Dựng timeline thay vì suy đoán từ một dòng log

Timeline là chuỗi sự kiện có mốc thời gian và nguồn bằng chứng. Một timeline hữu ích thường gồm:

1. Thời điểm commit hoặc cấu hình được thay đổi.
2. Thời điểm pipeline được kích hoạt và job bắt đầu.
3. Thời điểm có tín hiệu đầu tiên về bất thường.
4. Thời điểm retry, rollback, dừng promotion hoặc biện pháp giảm tác động được thực hiện.
5. Thời điểm hệ thống phục hồi.
6. Thời điểm xác minh sau khôi phục và quyết định đóng sự cố.

Ví dụ, hai job thất bại cách nhau vài phút có thể có nguyên nhân khác nhau. Nếu timeline cho thấy cả hai cùng sử dụng một runner vừa bị quá tải, giả thuyết về tài nguyên dùng chung có cơ sở hơn. Nếu chỉ một project thất bại sau khi dependency lockfile thay đổi, cần xem xét dependency trước khi kết luận runner có vấn đề.

Khi chưa biết chính xác thời điểm, ghi rõ đó là ước lượng và nguồn ước lượng. Không biến phỏng đoán thành sự kiện đã xác nhận. Có thể đánh dấu từng nhận định là “đã xác minh”, “đang kiểm tra” hoặc “chưa đủ dữ liệu” để nhóm phối hợp mà không nhầm lẫn mức độ chắc chắn.

## 6. Phân tích nguyên nhân mà không quy lỗi cho cá nhân

Mục đích điều tra là hiểu điều kiện khiến sự cố có thể xảy ra và vì sao các lớp bảo vệ không ngăn được hoặc không phát hiện sớm hơn. Câu hỏi “ai đã làm sai?” thường làm giảm chất lượng thông tin. Câu hỏi hữu ích hơn là “điều gì trong công cụ, quy trình, giao diện hoặc điều kiện làm việc khiến hành động đó trở nên hợp lý tại thời điểm ấy?”

Nên phân biệt các khái niệm:

- **Trigger:** thay đổi hoặc sự kiện khởi phát, chẳng hạn một commit mới, dependency registry chậm hoặc runner bị thu hồi.
- **Nguyên nhân nền (underlying cause):** điều kiện hệ thống khiến trigger dẫn đến sự cố, chẳng hạn timeout không phù hợp với tải thực tế hoặc pipeline không cô lập dữ liệu test.
- **Yếu tố góp phần (contributing factor):** điều kiện làm tăng xác suất hoặc mức độ tác động, chẳng hạn thiếu metric, retry không giới hạn hoặc runbook không rõ.
- **Lỗ hổng phát hiện (detection gap):** lý do nhóm không nhận ra vấn đề đủ sớm, chẳng hạn chỉ theo dõi trạng thái cuối của pipeline mà bỏ qua tỷ lệ retry.

Có thể sử dụng các kỹ thuật sau:

- **5 Whys:** hỏi “vì sao?” nhiều lần để lần theo chuỗi điều kiện. Không ép câu trả lời thành đúng năm lần; dừng khi có nguyên nhân có thể kiểm chứng và có hành động phù hợp.
- **Fishbone/Ishikawa:** phân nhóm yếu tố theo con người, quy trình, công cụ, môi trường, dữ liệu và đo lường để tránh chỉ nhìn vào code.
- **So sánh lần chạy tốt và lần chạy lỗi:** đối chiếu commit, dependency, runner, cấu hình, cache, dữ liệu và thời điểm.
- **Fault tree:** bắt đầu từ hậu quả rồi phân rã những tổ hợp điều kiện có thể dẫn đến hậu quả đó.

Không kết luận “do con người bất cẩn” hoặc “do mạng chập chờn” nếu chưa có bằng chứng. Một kết luận như “request đến registry bị timeout” mới mô tả triệu chứng; cần tiếp tục tìm xem timeout xuất hiện ở tầng nào, có lặp lại không, có tương quan với tải hay giới hạn kết nối không, và vì sao pipeline không xử lý được tình huống đó.

## 7. Đánh giá retry như một tín hiệu chẩn đoán

Retry có thể làm thay đổi môi trường thực thi. Vì thế, hãy ghi lại attempt đầu tiên và từng attempt sau với cùng một bộ nhận diện.

Khi xem một lần retry thành công, hãy kiểm tra:

- Commit SHA và pipeline definition có giữ nguyên không?
- Dependency lockfile và resolved versions có thay đổi không?
- Artifact được dùng lại hay được build lại?
- Runner, image, region, network route hoặc resource quota có khác không?
- Cache và workspace có được giữ nguyên, xóa hoặc khởi tạo lại không?
- Test data, database, queue hoặc trạng thái dịch vụ ngoài có thay đổi không?
- Retry có chạy lại cùng một tác vụ hay vô tình thực hiện một tác dụng phụ khác?

Từ đó có thể phân loại sơ bộ:

| Dấu hiệu | Khả năng cần điều tra |
|---|---|
| Cùng commit và dependency, đổi runner thì thành công | Runner, tài nguyên, mạng hoặc cấu hình worker |
| Cùng runner, cùng đầu vào nhưng test lúc qua lúc trượt | Race condition, dữ liệu chia sẻ hoặc test không ổn định |
| Retry sau một khoảng chờ thì thành công | Rate limit, dịch vụ phụ thuộc hoặc eventual consistency |
| Lỗi luôn xuất hiện với một commit | Regression hoặc thay đổi cấu hình/dependency |
| Lỗi chỉ xuất hiện khi nhiều job chạy đồng thời | Tranh chấp tài nguyên, khóa, cổng hoặc dữ liệu dùng chung |
| Retry tạo ra trạng thái khác hoặc tác dụng phụ lặp | Job không idempotent hoặc thiếu cơ chế chống thực thi trùng |

Đây là giả thuyết điều tra, không phải kết luận tự động. Cần kiểm tra log, metric và điều kiện thực tế trước khi gán nguyên nhân.

### 7.1. Thiết kế retry có giới hạn

Retry nên được áp dụng có chọn lọc:

- Chỉ retry những lỗi được phân loại là có khả năng tạm thời.
- Giới hạn số lần thử và tổng thời gian chờ.
- Dùng exponential backoff và jitter khi gọi dịch vụ dễ bị quá tải.
- Lưu kết quả và log của mọi attempt, kể cả attempt thất bại đầu tiên.
- Không retry mù quáng lỗi xác thực, lỗi cấu hình, lỗi kiểm tra chữ ký hoặc lỗi logic có tính xác định.
- Chỉ retry thao tác có tính idempotent hoặc đã có cơ chế kiểm soát tác dụng phụ.
- Hiển thị trạng thái “đã retry” hoặc “không ổn định” trong báo cáo chất lượng.

Ví dụ logic tổng quát:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    result = execute_job()
    store_attempt_evidence(attempt, result)

    if result.success:
        if attempt > 1:
            report_as_recovered_after_retry()
        stop_successfully()

    if not is_retryable(result.error):
        stop_with_failure()

    if attempt == MAX_ATTEMPTS:
        stop_with_failure()

    wait(exponential_backoff_with_jitter(attempt))
~~~

Ví dụ trên chỉ mô tả luồng quyết định. Chính sách thực tế cần xác định rõ lỗi nào retry được, attempt nào được phép chạy lại và điều kiện nào vẫn chặn phát hành. Với kiểm thử bảo mật, kiểm tra chất lượng bắt buộc hoặc xác minh provenance, một lần retry thành công không nên tự động xóa dấu vết thất bại đầu tiên khỏi quyết định release.

Đối với deployment hoặc migration, cần đặc biệt thận trọng: một lần gọi lại có thể tạo release trùng, chạy migration lần hai hoặc gửi lệnh đến hệ thống đã nhận lệnh trước đó. Trước khi retry, hãy kiểm tra trạng thái thực tế và thiết kế thao tác idempotent hoặc cơ chế đối soát.

## 8. Ví dụ: test chỉ thất bại trên runner dùng chung

Giả sử một pipeline chạy unit test của Order API. Attempt đầu tiên timeout sau 60 giây. Người phát triển bấm retry và attempt thứ hai thành công. Nếu chỉ nhìn trạng thái cuối, nhóm có thể kết luận rằng đây là lỗi ngẫu nhiên.

Hồ sơ sự cố được lập và nhóm thu thập các bằng chứng sau:

- Cả hai attempt dùng cùng commit và cùng dependency lockfile.
- Attempt đầu tiên chạy trên runner pool dùng chung với nhiều job nặng.
- Metric của runner cho thấy CPU và thời gian chờ I/O tăng cao trong khoảng test timeout.
- Attempt thứ hai được xếp trên runner khác, tải thấp hơn.
- Khi chạy lại với tải đồng thời cao, test có thể tái hiện timeout.

Từ các dữ liệu này, nhóm có cơ sở để xem xét tranh chấp tài nguyên. Trigger là một đợt chạy test trong thời điểm tải cao. Các yếu tố góp phần có thể là runner pool chưa phân loại workload, concurrency vượt quá năng lực thực tế và test timeout chưa dựa trên phân phối thời gian chạy đã đo.

Các hành động cải tiến có thể gồm:

1. Tách workload kiểm thử nặng khỏi job nhỏ, với owner là nhóm quản lý runner.
2. Đặt giới hạn concurrency theo năng lực runner và theo dõi thời gian chờ.
3. Bổ sung metric CPU, memory, I/O và thời lượng test theo runner pool.
4. Đo lại phân phối thời gian chạy để chọn timeout hợp lý.
5. Theo dõi tỷ lệ timeout và retry trong các sprint tiếp theo.

Tiêu chí xác minh không chỉ là “lần chạy kế tiếp xanh”. Nhóm có thể yêu cầu tỷ lệ timeout giảm dưới ngưỡng đã thống nhất trong một khoảng quan sát đủ dài, không làm tăng đáng kể thời gian chờ queue, và các job quan trọng vẫn đáp ứng thời gian phản hồi mục tiêu.

Ví dụ này cũng cho thấy một test có thể không có lỗi logic nhưng vẫn tạo ra phản hồi không đáng tin cậy khi môi trường thực thi không ổn định. Nhóm cần cải thiện cả cách chạy và cách đo, thay vì kéo dài timeout vô hạn hoặc tăng số lần retry.

## 9. Viết báo cáo sau sự cố có thể hành động

Báo cáo sau sự cố (incident review hoặc postmortem) nên giúp người đọc hiểu điều gì xảy ra, tác động ra sao, nhóm đã biết gì và cần thay đổi điều gì. Nó không phải bản tường trình để tìm người chịu lỗi.

Một báo cáo có thể có các phần:

| Phần | Nội dung cần ghi |
|---|---|
| Tóm tắt | Một hoặc hai câu mô tả sự cố và trạng thái hiện tại |
| Phạm vi và tác động | Dịch vụ, nhóm, release, người dùng, thời gian và mức độ ảnh hưởng |
| Phát hiện | Ai hoặc hệ thống nào phát hiện, phát hiện qua tín hiệu nào |
| Timeline | Các sự kiện chính, thời điểm, nguồn bằng chứng |
| Trigger | Sự kiện khởi phát đã được xác minh |
| Nguyên nhân và yếu tố góp phần | Điều kiện hệ thống và bằng chứng hỗ trợ |
| Ứng phó | Các biện pháp ổn định, rollback, retry, thu hồi hoặc giới hạn tác động |
| Điều đã làm tốt | Cơ chế phát hiện, phối hợp hoặc khôi phục có hiệu quả |
| Khoảng trống | Điều khiến tác động lớn hơn hoặc kéo dài hơn |
| Hành động | Việc cần làm, owner, hạn hoàn thành và tiêu chí xác minh |
| Theo dõi | Metric, dashboard, runbook hoặc quy trình được cập nhật |

Ví dụ một bản ghi tóm tắt có cấu trúc:

~~~yaml
incident:
  id: CI-2026-014
  title: Unit test timeout on shared runner pool
  severity: SEV-3
  status: monitoring
  detected_at: "2026-11-18T02:15:00Z"
  resolved_at: "2026-11-18T03:05:00Z"
  affected:
    - order-api-ci
  impact:
    blocked_pull_requests: 8
    production_outage: false
  trigger: "Test workload ran during high runner contention"
  contributing_factors:
    - "Runner pool mixed heavy and lightweight jobs"
    - "No alert on resource saturation"
  evidence:
    pipeline_run: "run-1842"
    commit: "a1b2c3d"
    attempts: 2
  actions:
    - id: ACT-101
      description: "Separate heavy test workload"
      owner: platform-team
      due_date: "2026-11-25"
      success_measure: "Timeout rate below agreed threshold"
~~~

Đây là ví dụ minh họa về cấu trúc dữ liệu, không phải mẫu severity hay cách đặt ID bắt buộc. Các trường phải phù hợp với quy ước nội bộ. Không đưa secret, token hoặc dữ liệu cá nhân vào bản ghi.

## 10. Chuyển bài học thành hành động cải tiến

Một báo cáo chỉ hữu ích khi kết quả điều tra thay đổi cách hệ thống hoạt động. Hành động nên nhắm vào một trong bốn hướng:

- **Phòng ngừa:** giảm khả năng lỗi xảy ra, ví dụ cô lập dữ liệu test, pin dependency, giới hạn concurrency hoặc kiểm tra cấu hình trước khi deploy.
- **Phát hiện:** nhận biết vấn đề sớm hơn, ví dụ cảnh báo tỷ lệ retry, theo dõi runner saturation hoặc xác minh health check sau triển khai.
- **Giảm tác động:** giới hạn blast radius, ví dụ canary, dừng promotion khi tín hiệu xấu hoặc cô lập runner bị lỗi.
- **Khôi phục:** giúp phục hồi an toàn, ví dụ rollback đã diễn tập, quy trình thu hồi credential hoặc cách tái tạo artifact có provenance.

Mỗi hành động cần có:

1. Mô tả cụ thể thay đổi sẽ tạo ra.
2. Một owner chịu trách nhiệm điều phối đến khi hoàn tất.
3. Thời hạn hoặc mốc xem xét.
4. Mức ưu tiên dựa trên tác động và xác suất tái diễn.
5. Tiêu chí nghiệm thu có thể quan sát hoặc đo lường.
6. Liên kết đến ticket, pull request, dashboard hoặc runbook liên quan.

Tránh những hành động mơ hồ như “cẩn thận hơn”, “theo dõi thêm” hoặc “không để xảy ra lần nữa”. Nếu hành động là “tăng độ ổn định của test”, hãy chuyển thành việc cụ thể như loại bỏ phụ thuộc vào thứ tự chạy, cô lập test data, thêm timeout theo từng bước và đo tỷ lệ flaky test.

Không nên giải quyết mọi sự cố bằng cách thêm retry. Retry có thể giảm số lần pipeline thất bại nhìn thấy được nhưng không loại bỏ lỗi nền. Tương tự, tăng timeout có thể che dấu việc runner bị quá tải. Chọn biện pháp dựa trên nguyên nhân đã có bằng chứng.

## 11. Phối hợp giữa các vai trò

Sự cố CI/CD thường nằm ở ranh giới giữa nhiều nhóm. Một test timeout có thể do test code, runner, network, database hoặc cách pipeline phân bổ tài nguyên. Việc điều tra sẽ chậm nếu mỗi nhóm chỉ xem phần hệ thống mình quản lý.

Có thể phân công các vai trò sau:

- **Incident lead:** giữ mục tiêu xử lý, xác định mức độ, điều phối quyết định và cập nhật trạng thái.
- **Technical investigator:** phân tích code, pipeline, runner, dependency và môi trường liên quan.
- **Communicator:** cập nhật cho nhóm bị ảnh hưởng, người chờ release và bên liên quan theo nhịp đã thống nhất.
- **Scribe:** giữ timeline, quyết định, giả thuyết, liên kết bằng chứng và action items.

Trong nhóm nhỏ, một người có thể kiêm nhiều vai trò. Với sự cố đơn giản, không cần dựng bộ máy đầy đủ; vẫn cần xác định ai điều phối và ai lưu quyết định.

Khi chuyển giao giữa nhóm phát triển và nền tảng, hãy cung cấp một gói thông tin có thể kiểm tra: pipeline/run ID, commit SHA, job và attempt, runner, thời điểm, lỗi quan sát được, các bước đã thử và liên kết đến log đã được xử lý secret. Tránh gửi một ảnh chụp màn hình chỉ có dòng “failed” mà không có ngữ cảnh.

Các quyết định quan trọng như tiếp tục release, dừng promotion, rollback hoặc chấp nhận một retry phải có người có thẩm quyền phù hợp đưa ra. Báo cáo cần ghi lại quyết định và lý do để nhóm khác có thể tiếp tục công việc khi ca trực thay đổi.

## 12. Đo lường để biết quy trình có tốt hơn không

Nhóm có thể theo dõi một tập metric nhỏ để nhận diện xu hướng và đánh giá hành động cải tiến.

| Metric | Cách hiểu | Câu hỏi quản lý |
|---|---|---|
| Tỷ lệ retry | Số job phải retry trên tổng số job hoặc tổng số job thất bại, cần ghi rõ mẫu số | Bao nhiêu lần chạy không ổn định? |
| Tỷ lệ thành công sau retry | Số job thất bại ban đầu nhưng thành công sau retry trên số job đã retry | Bao nhiêu lỗi đang bị che bởi retry? |
| Flaky test rate | Tỷ lệ test có kết quả không nhất quán trên cùng đầu vào và điều kiện tương đương | Test nào không đáng tin cậy? |
| Pipeline failure rate | Tỷ lệ pipeline thất bại theo loại nguyên nhân | Nhóm lỗi nào tăng lên? |
| Time to detect | Thời gian từ lúc sự cố bắt đầu đến lúc được phát hiện | Hệ thống phát hiện sớm đến đâu? |
| Time to restore | Thời gian từ lúc phát hiện đến khi dịch vụ hoặc luồng phát hành phục hồi | Tác động kéo dài bao lâu? |
| Recurrence rate | Tỷ lệ sự cố lặp lại theo nhóm nguyên nhân hoặc thành phần | Hành động trước đó có hiệu quả không? |
| Action completion | Tỷ lệ hành động hoàn thành đúng hạn và đạt tiêu chí nghiệm thu | Bài học có được chuyển thành thay đổi không? |

Định nghĩa mẫu số và phạm vi đo phải nhất quán. Ví dụ, tỷ lệ retry có thể tính trên tổng job hoặc trên job thất bại; hai cách trả lời hai câu hỏi khác nhau. Hãy lưu cách tính cùng dashboard để người đọc không diễn giải nhầm.

Không dùng metric để khuyến khích nhóm che giấu lỗi hoặc đạt màu xanh bằng mọi giá. Một tỷ lệ pipeline xanh cao nhưng tỷ lệ retry tăng nhanh có thể báo hiệu chất lượng đang giảm. Một lần rollback được thực hiện nhanh và an toàn có thể là dấu hiệu của quy trình tốt, dù release đó được tính là change failure.

Nên phân tích theo loại nguyên nhân, runner pool, repository, loại test và giai đoạn pipeline. Tránh dùng một con số tổng hợp để quy trách nhiệm cho một nhóm hoặc một cá nhân.

## 13. Đưa bài học trở lại quy trình CI/CD

Khi hành động cải tiến được triển khai, cần cập nhật những nơi giúp người khác tránh lặp lại cùng vấn đề:

- Pipeline as Code: thêm điều kiện kiểm tra, timeout, concurrency, retry policy hoặc bước xác minh phù hợp.
- Test suite: cô lập dữ liệu, loại bỏ phụ thuộc thứ tự, cải thiện chẩn đoán và giảm tính không xác định.
- Runner và agent: phân loại workload, cập nhật image, giới hạn tài nguyên hoặc tăng khả năng quan sát.
- Artifact và dependency: khóa version, xác minh checksum, lưu digest và provenance.
- Release process: thêm health check, canary, approval hoặc rollback khi có căn cứ từ sự cố.
- Runbook: ghi các bước kiểm tra, khôi phục, người liên hệ và điều kiện escalation.
- Onboarding: bổ sung bài học vào tài liệu để thành viên mới hiểu các quyết định và quy ước đã được thống nhất.

Nếu một biện pháp chỉ tồn tại trong ghi chú cá nhân, nó sẽ mất tác dụng khi người đó đổi nhóm. Hãy đưa tri thức vào code, tài liệu, dashboard hoặc quy trình có thể được duy trì và review.

## 14. Những sai lầm thường gặp khi xử lý sự cố

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ ghi trạng thái cuối cùng sau retry | Mất bằng chứng về lần thất bại đầu tiên | Lưu từng attempt và liên kết chúng với cùng pipeline |
| Kết luận nguyên nhân từ một dòng log | Dễ sửa sai tầng hoặc bỏ sót yếu tố góp phần | Dựng timeline và kiểm tra giả thuyết bằng nhiều nguồn |
| Quy lỗi cho một cá nhân | Người tham gia ngại chia sẻ thông tin | Tập trung vào điều kiện hệ thống và khả năng phòng vệ |
| Tăng số lần retry cho mọi lỗi | Che lỗi xác định và kéo dài pipeline | Retry có điều kiện, giới hạn và metric |
| Tăng timeout mà không đo tải | Che dấu nghẽn tài nguyên | Đo phân phối thời gian và tài nguyên trước khi đổi |
| Đóng incident khi ticket đã đóng | Không biết rủi ro có thực sự giảm | Đóng theo tiêu chí xác minh và khoảng quan sát |
| Giao action cho “cả nhóm” | Không rõ ai chịu trách nhiệm | Chỉ định một owner và người phối hợp |
| Chia sẻ toàn bộ log vào ticket công khai | Có thể làm lộ credential hoặc dữ liệu nhạy cảm | Redact, phân quyền và lưu bằng chứng ở nơi phù hợp |

## 15. Checklist review sau sự cố

Trước khi kết thúc một incident review, nhóm có thể dùng checklist sau:

- [ ] Đã xác định loại sự cố, mức độ, phạm vi và tác động.
- [ ] Đã liên kết repository, commit, pipeline, job, attempt, runner, artifact và môi trường liên quan.
- [ ] Đã lưu bằng chứng gốc và bảo vệ secret, dữ liệu cá nhân.
- [ ] Timeline phân biệt sự kiện đã xác minh với giả thuyết hoặc thời điểm ước lượng.
- [ ] Đã ghi rõ trigger, nguyên nhân nền, yếu tố góp phần và khoảng trống phát hiện.
- [ ] Đã xem xét ý nghĩa của từng lần retry và điều kiện thay đổi giữa các attempt.
- [ ] Báo cáo tập trung vào học hỏi và điều kiện hệ thống, không quy lỗi cá nhân.
- [ ] Mỗi hành động có owner, thời hạn, mức ưu tiên và tiêu chí nghiệm thu.
- [ ] Có metric hoặc bằng chứng để xác minh hành động làm giảm rủi ro.
- [ ] Runbook, pipeline, test, dashboard hoặc tài liệu đã được cập nhật khi cần.
- [ ] Các nhóm liên quan biết trạng thái, quyết định và cách theo dõi tiếp theo.

## 16. Nguyên tắc kết thúc

Một pipeline thành công sau retry là thông tin hữu ích, nhưng chưa phải bằng chứng rằng hệ thống đã ổn định. Nhóm chỉ có thể cải tiến khi giữ lại được lần thất bại đầu tiên, hiểu điều kiện tạo ra nó, phân biệt sự kiện với giả thuyết và biến bài học thành thay đổi có thể kiểm chứng.

Khi incident review có owner, tiêu chí nghiệm thu và dữ liệu theo dõi, mỗi sự cố có thể giúp quy trình CI/CD đáng tin cậy hơn. Khi đó, mục tiêu của phối hợp nhóm không dừng ở việc đưa một lần chạy trở lại màu xanh, mà là giảm xác suất lặp lại và giảm tác động nếu vấn đề vẫn xảy ra.
