# Bỏ qua kiểm thử lỗi hoặc thử lại vô hạn để đạt trạng thái xanh

Một pipeline xanh thường được xem là tín hiệu rằng thay đổi đã vượt qua các kiểm tra cần thiết. Nhưng màu xanh chỉ có ý nghĩa khi các kiểm tra thực sự chạy, kết quả được giữ lại và những lỗi quan trọng không bị che giấu. Nếu nhóm bỏ qua test thất bại, bật chế độ tiếp tục khi có lỗi hoặc bấm retry cho đến khi thành công, pipeline có thể xanh trong khi phần mềm vẫn chứa lỗi chưa được hiểu rõ.

Đây là một lỗi tư duy phổ biến trong CI/CD: xem trạng thái cuối cùng là mục tiêu, thay vì xem bằng chứng kiểm thử là cơ sở để quyết định. Một lần chạy lại thành công không xóa đi lần thất bại trước đó. Nó chỉ bổ sung một quan sát mới trong một điều kiện thực thi có thể đã khác.

Bài học này giúp nhận diện hành vi tạo ra trạng thái xanh giả, phân loại lỗi trước khi retry, thiết kế giới hạn thử lại, quản lý test không ổn định và giữ cho quality gate phản ánh đúng rủi ro của thay đổi.

## 1. Hiểu đúng ý nghĩa của trạng thái xanh

Một pipeline có thể kết thúc thành công vì nhiều lý do khác nhau:

- Tất cả kiểm tra bắt buộc đã chạy và đạt ngay lần đầu.
- Một lỗi hạ tầng tạm thời được xác định rõ, sau đó thao tác an toàn được retry trong giới hạn và thành công.
- Một test thất bại ở lần đầu nhưng thành công khi chạy lại do tính không ổn định.
- Job quan trọng bị bỏ qua, bị đánh dấu cho phép thất bại hoặc không được đưa vào luồng kiểm tra.
- Pipeline chỉ chạy một tập test nhỏ hơn dự kiến vì cấu hình path filter hoặc điều kiện job sai.

Những trường hợp này không có cùng mức độ tin cậy. Trạng thái cuối cùng là một phần của kết quả, nhưng cần đọc cùng lịch sử attempt, danh sách kiểm tra đã chạy, các bước bị bỏ qua và lý do ngoại lệ.

Có thể phân biệt các trạng thái sau:

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Passed on first attempt | Tất cả kiểm tra bắt buộc đạt ngay lần đầu | Bằng chứng tốt cho commit và môi trường đã kiểm tra |
| Passed after transient retry | Lỗi tạm thời đã được phân loại, retry hữu hạn thành công | Có thể phục hồi luồng nhưng phải lưu lịch sử retry |
| Flaky | Cùng đầu vào và điều kiện tương đương cho kết quả không nhất quán | Kết quả kiểm thử chưa đáng tin cậy; cần điều tra |
| Failed | Kiểm tra bắt buộc thất bại hoặc lỗi không được phép retry | Chặn quality gate tương ứng |
| Quarantined | Test được tách khỏi cổng chính theo ngoại lệ có kiểm soát | Phải có owner, thời hạn và kiểm tra thay thế |
| Not run / skipped | Kiểm tra không được thực thi | Không được diễn giải thành đã đạt |

Một báo cáo chỉ ghi “success” sẽ làm mất khác biệt giữa những trạng thái này. Hệ thống nên thể hiện rõ một lần chạy đạt ngay lần đầu hay đạt sau retry, test nào bị quarantine và job nào không chạy.

## 2. Vì sao nhóm dễ chạy theo màu xanh?

Áp lực giao hàng thường khiến nhóm ưu tiên hoàn tất pipeline để pull request được merge hoặc release được tiếp tục. Khi một test thất bại không ổn định, bấm retry có thể là cách nhanh nhất để gỡ tắc nghẽn trước mắt. Nếu lần chạy sau thành công, mọi người có thể cảm thấy vấn đề đã được xử lý.

Một số suy nghĩ dẫn đến hành vi này:

- “Lần sau đã xanh nên lần đầu chắc chỉ là lỗi ngẫu nhiên.”
- “Test này hay lỗi, cứ bỏ qua để nhóm khác làm việc.”
- “Chỉ cần build thành công là có thể phát hành.”
- “Nếu retry đủ nhiều thì sớm muộn cũng có một lần pass.”
- “Tỷ lệ pipeline xanh đang là KPI, không nên để một test làm chậm release.”
- “Sửa test mất thời gian hơn nhiều so với chạy lại.”

Những suy nghĩ này đánh đồng việc hoàn tất thao tác với việc giảm rủi ro. Một lỗi ngẫu nhiên vẫn có thể chỉ ra race condition, tranh chấp dữ liệu, phụ thuộc môi trường hoặc thiếu tính cô lập. Một test đã lâu không ổn định có thể đang kiểm tra đúng một luồng quan trọng mà nhóm chưa có cách xác minh khác.

Mục tiêu của CI không phải làm cho mọi lần chạy đều xanh bằng mọi giá. Mục tiêu là đưa ra phản hồi đáng tin cậy để nhóm biết thay đổi có đủ điều kiện đi tiếp hay không.

## 3. Phân biệt các loại lỗi trước khi quyết định retry

Retry chỉ có ý nghĩa khi nhóm hiểu loại lỗi đang gặp. Một thông báo timeout hoặc exit code khác không tự nói lên nguyên nhân. Cần kết hợp log, metric, lịch sử attempt, trạng thái runner và thay đổi gần nhất để phân loại.

| Loại lỗi | Dấu hiệu thường gặp | Hướng xử lý ban đầu |
|---|---|---|
| Lỗi xác định từ code | Assertion sai, compile error, test phát hiện regression | Sửa code hoặc test theo hợp đồng; không retry để vượt qua |
| Lỗi cấu hình | Thiếu biến, sai quyền, sai endpoint, cấu hình môi trường không hợp lệ | Sửa cấu hình hoặc quyền; retry khi điều kiện đã được sửa |
| Lỗi hạ tầng tạm thời | Runner mất kết nối, registry trả 503/429, connection reset | Có thể retry hữu hạn nếu thao tác an toàn |
| Test không ổn định (flaky) | Cùng commit và điều kiện tương đương nhưng lúc pass lúc fail | Điều tra tính xác định, cô lập có thời hạn nếu cần |
| Lỗi phụ thuộc bên ngoài | API sandbox chậm, service test không sẵn sàng, dữ liệu chưa đồng bộ | Kiểm tra trạng thái phụ thuộc, timeout và backoff |
| Lỗi bảo mật hoặc chính sách | Secret scan, chữ ký artifact, policy gate hoặc quyền truy cập thất bại | Giữ gate thất bại cho đến khi có bằng chứng hợp lệ |

Một số lỗi có biểu hiện giống nhau nhưng nguyên nhân khác nhau. Ví dụ, test timeout có thể do code bị treo, deadlock, runner thiếu tài nguyên, database phản hồi chậm hoặc timeout đặt quá thấp. Không nên tự động phân loại mọi timeout là lỗi tạm thời.

### 3.1. Lỗi xác định không trở thành lỗi tạm thời sau một lần retry

Nếu assertion báo kết quả thực tế khác kết quả mong đợi, chạy lại không thay đổi hợp đồng của phần mềm. Nếu compile error xuất hiện vì API bị đổi, một lần retry nữa cũng không sửa được mã nguồn. Với các lỗi có tính xác định, cần dừng và điều tra.

Một test assertion thất bại rồi pass ở lần chạy sau không chứng minh assertion ban đầu có thể bỏ qua. Nó cho thấy test hoặc môi trường có tính không xác định. Kết quả cần được phân loại là flaky cho đến khi tìm được lời giải thích có bằng chứng.

### 3.2. Lỗi hạ tầng có thể retry nhưng phải có điều kiện

Runner bị thu hồi hoặc registry tạm thời trả về 503 có thể là tình huống retry phù hợp. Trước khi retry, hãy kiểm tra:

- Mã lỗi có thuộc danh sách lỗi tạm thời được chấp nhận không?
- Hệ thống phụ thuộc đã phục hồi hoặc có khả năng phục hồi không?
- Thao tác có an toàn khi thực hiện lại không?
- Retry có nằm trong giới hạn tổng thời gian và số lần thử không?
- Bằng chứng của lần thất bại đầu tiên có được giữ lại không?

Nếu lỗi cấu hình, xác thực hoặc policy bị xem nhầm là lỗi tạm thời, retry chỉ tạo thêm tải và làm chậm việc sửa đúng vấn đề.

## 4. Retry vô hạn tạo ra trạng thái xanh giả như thế nào?

Giả sử một job test thất bại với xác suất 20% ở mỗi lần chạy độc lập. Nếu hệ thống cứ chạy lại đến khi thành công, xác suất cuối cùng có được ít nhất một lần pass sẽ tiến gần 100% khi số lần thử tăng. Nhưng xác suất đó không có nghĩa test đáng tin cậy hơn; nó chỉ có nghĩa nhóm đã chờ đủ lâu để gặp một lần kết quả thuận lợi.

Với test flaky, giả định độc lập thường không hoàn toàn đúng. Tuy nhiên, nguyên tắc vẫn giữ nguyên: càng cho phép thử lại không giới hạn, trạng thái cuối càng ít phản ánh độ tin cậy của lần kiểm tra ban đầu.

~~~mermaid
flowchart TD
    A["Test bắt đầu"] --> B{"Kết quả?"}
    B -->|Pass| C["Đạt lần đầu"]
    B -->|Fail| D{"Phân loại lỗi"}
    D -->|Lỗi xác định| E["Giữ trạng thái thất bại"]
    D -->|Lỗi tạm thời được phép retry| F{"Còn retry budget?"}
    D -->|Flaky hoặc chưa rõ| G["Ghi nhận không ổn định và điều tra"]
    F -->|Có| H["Lưu attempt và chờ backoff"]
    H --> A
    F -->|Không| I["Thất bại sau retry hữu hạn"]
    C --> J["Tổng hợp quality gate"]
    E --> J
    G --> J
    I --> J
~~~

Khi pipeline lặp lại cho đến khi pass, nhóm có thể gặp các hệ quả:

- **Che giấu regression:** test thất bại ở lần đầu nhưng trạng thái cuối được báo cáo như chưa từng có lỗi.
- **Tạo tải không cần thiết:** runner, database, registry và dịch vụ test phải xử lý nhiều lần thực thi.
- **Kéo dài phản hồi:** pull request chờ lâu hơn và nhóm khó dự đoán thời gian hoàn tất.
- **Tăng nguy cơ tác dụng phụ:** deployment, migration, gửi message hoặc tạo tài nguyên có thể được thực hiện nhiều lần.
- **Làm sai metric:** tỷ lệ pass cuối cao trong khi tỷ lệ lỗi ban đầu và retry tăng.
- **Giảm niềm tin vào quality gate:** người phát triển học cách bấm retry thay vì đọc và sửa lỗi.

Một pipeline chạy lại ba lần rồi thành công không tương đương pipeline đạt ngay lần đầu. Báo cáo và quyết định phát hành cần giữ được sự khác biệt đó.

## 5. Thiết kế retry có giới hạn và có lý do

Retry nên là một chính sách có thể giải thích, không phải vòng lặp vô hạn để chờ kết quả thuận lợi.

Một chính sách thực tế cần xác định:

1. Danh sách lỗi được phép retry.
2. Số lần thử tối đa cho từng loại thao tác.
3. Tổng thời gian retry tối đa.
4. Khoảng chờ giữa các lần thử.
5. Điều kiện idempotent hoặc cơ chế chống thực hiện trùng.
6. Dữ liệu phải lưu cho từng attempt.
7. Cách kết quả retry tác động đến quality gate.

Ví dụ logic tổng quát:

~~~text
MAX_ATTEMPTS = 2

for attempt in 1..MAX_ATTEMPTS:
    result = run_check()
    save_attempt_evidence(attempt, result)

    if result.is_success:
        if attempt == 1:
            return PASSED_FIRST_ATTEMPT
        return PASSED_AFTER_RETRY

    if not is_explicitly_retryable(result.failure):
        return FAILED

    if attempt == MAX_ATTEMPTS:
        return FAILED_AFTER_RETRY

    wait_with_backoff_and_jitter(attempt)
~~~

Đây là pseudocode minh họa, không phải cú pháp của một CI vendor cụ thể. Giá trị giới hạn phải dựa trên loại lỗi, thời gian phục hồi của dependency và mức độ an toàn của thao tác. Với một số thao tác, một lần retry là đủ; một số tác vụ đọc có thể có ngân sách khác. Không nên dùng một con số chung cho mọi job.

### 5.1. Tránh retry lồng nhau

Một job có thể retry toàn bộ pipeline, trong khi script bên trong cũng retry request và test framework lại tự rerun test. Nếu mỗi tầng đều có ba lần thử, số lần thực thi thực tế có thể nhân lên nhiều lần.

Hãy xác định tầng nào sở hữu retry và truyền ngân sách còn lại cho các tầng bên dưới. Log cần cho biết số attempt tổng thể, không chỉ số lần thử cục bộ của một script.

### 5.2. Dùng backoff và jitter cho dependency có giới hạn tải

Khi registry hoặc API trả về 429 hay 503, retry ngay lập tức có thể tạo thêm tải và làm dịch vụ phục hồi chậm hơn. Exponential backoff tăng khoảng chờ theo số lần thử; jitter thêm độ lệch ngẫu nhiên để nhiều job không cùng retry vào một thời điểm.

Tôn trọng thông tin Retry-After khi dịch vụ cung cấp. Nếu tổng thời gian chờ vượt ngân sách pipeline, dừng với trạng thái lỗi có chẩn đoán rõ ràng.

### 5.3. Không retry thao tác có tác dụng phụ nếu chưa kiểm soát

Một lệnh đọc thường an toàn hơn một lệnh ghi. Retry deployment, migration, publish package hoặc gửi sự kiện có thể tạo kết quả trùng nếu hệ thống đã nhận lệnh trước khi kết nối bị ngắt.

Trước khi retry, cần biết trạng thái của thao tác trước đó. Dùng idempotency key, transaction, trạng thái đối soát hoặc cơ chế kiểm tra đã hoàn tất. Nếu không xác định được trạng thái, dừng để điều tra thay vì gửi lại mù quáng.

## 6. Giữ nguyên bằng chứng của mọi lần thử

Mỗi lần thử nên có attempt ID hoặc liên kết rõ ràng với cùng pipeline run. Đừng ghi đè log của lần đầu bằng log của lần sau.

Tối thiểu nên lưu:

| Trường | Mục đích |
|---|---|
| Pipeline run ID và job ID | Liên kết các lần thực thi |
| Attempt number | Biết đây là lần thử thứ mấy |
| Commit SHA và pipeline definition revision | Xác nhận đầu vào có giữ nguyên |
| Test name hoặc command | Xác định kiểm tra cụ thể |
| Runner ID, image và môi trường | So sánh điều kiện thực thi |
| Dependency versions và cache state | Phát hiện đầu vào khác nhau |
| Start/end time và exit code | Dựng timeline |
| Failure category và retry reason | Giải thích vì sao được retry |
| Artifact/log reference | Cho phép điều tra lại |

Bằng chứng cần được bảo vệ khỏi việc sửa đổi ngoài ý muốn. Nếu log có thể chứa secret, hãy redaction trước khi chia sẻ và giới hạn quyền truy cập vào bản gốc.

Một báo cáo hữu ích có thể thể hiện:

~~~text
Pipeline: run-1842
Commit: a1b2c3d
Check: order-api-contract-test

Attempt 1:
  Result: FAILED
  Category: FLAKY_SUSPECTED
  Runner: linux-pool-03
  Exit code: 1

Attempt 2:
  Result: PASSED
  Category: PASSED_AFTER_RETRY
  Runner: linux-pool-07

Final quality state: UNSTABLE
Reason: Same test failed then passed; investigation required
~~~

Ví dụ này cho thấy job có lần chạy pass nhưng chất lượng tổng thể vẫn cần được đánh dấu không ổn định theo chính sách của nhóm.

## 7. Quản lý flaky test thay vì bỏ qua chúng

Flaky test là test có thể cho kết quả khác nhau khi đầu vào và điều kiện được cho là tương đương. Nguyên nhân có thể đến từ:

- Phụ thuộc vào thứ tự thực thi hoặc trạng thái còn sót lại từ test trước.
- Dùng chung file, database, port, queue hoặc tài khoản giữa nhiều test.
- Race condition và đồng bộ không đầy đủ.
- Phụ thuộc thời gian, timezone, random seed hoặc lịch chạy.
- Gọi dịch vụ bên ngoài không được kiểm soát.
- Tài nguyên runner biến động hoặc timeout quá chặt.
- Cleanup không đầy đủ sau khi test kết thúc.

### 7.1. Điều tra bằng cách làm cho test có thể tái hiện

Một quy trình điều tra có thể gồm:

1. Ghi lại test name, commit, seed, dữ liệu đầu vào và môi trường.
2. Chạy test độc lập để kiểm tra phụ thuộc thứ tự.
3. Chạy lặp trong môi trường có kiểm soát để ước lượng tần suất thất bại.
4. Chạy song song để tìm tranh chấp tài nguyên hoặc dữ liệu.
5. Thay thế dependency bên ngoài bằng fake hoặc test double khi phù hợp.
6. Kiểm tra log, trace và trạng thái sau cleanup.
7. Viết lại test để xác minh một hợp đồng rõ ràng và có thể lặp lại.

Chạy lặp lại là một kỹ thuật chẩn đoán có chủ đích, có giới hạn và được ghi nhận. Nó khác với việc retry trong pipeline cho đến khi có màu xanh.

### 7.2. Quarantine chỉ là biện pháp tạm thời

Khi một flaky test làm tắc toàn bộ nhóm, có thể tạm tách nó khỏi cổng chính nếu đã đánh giá rủi ro và có cơ chế thay thế phù hợp. Quarantine không có nghĩa xóa test hoặc đánh dấu nó như đã đạt.

Một ngoại lệ quarantine cần có:

- Test hoặc nhóm test được định danh cụ thể.
- Lý do, bằng chứng và phạm vi rủi ro.
- Owner chịu trách nhiệm sửa.
- Ticket và thời hạn hết hiệu lực.
- Cách chạy test ngoài cổng chính để tiếp tục thu thập tín hiệu.
- Quyết định rõ ràng về việc release có được phép tiếp tục hay không.

Không nên quarantine âm thầm test bảo mật, kiểm tra chữ ký artifact, migration, contract quan trọng hoặc test bảo vệ dữ liệu. Nếu một kiểm tra quan trọng không thể chạy đáng tin cậy, cần có biện pháp xác minh thay thế được phê duyệt trước khi cho phép phát hành.

Quarantine không có thời hạn sẽ biến lỗi tạm thời thành một phần cố định của quy trình. Dashboard nên hiển thị tuổi của từng quarantine và cảnh báo khi quá hạn.

## 8. Không biến bước kiểm tra bắt buộc thành tùy chọn

Một số cấu hình có thể làm pipeline xanh dù job thất bại hoặc không chạy:

- Cho phép job thất bại mà pipeline vẫn tiếp tục.
- Dùng lệnh shell bỏ qua exit code, chẳng hạn nối lệnh với cơ chế luôn trả về thành công.
- Đánh dấu job là optional mà không có lý do và owner.
- Dùng điều kiện khiến test chỉ chạy trên một số nhánh nhưng báo cáo không thể hiện phần bị bỏ qua.
- Bỏ qua bước scan hoặc kiểm tra chữ ký khi dịch vụ gặp lỗi.
- Dùng artifact cũ hoặc cache không hợp lệ để tránh chạy lại bước xác minh.

Các cơ chế như continue-on-error hoặc allow-failure có thể hữu ích cho job thông tin, thử nghiệm hoặc kiểm tra chưa bắt buộc. Nhưng chúng cần được phân loại rõ và không được dùng cho gate bảo vệ release.

Một quality gate nên xác định:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Required check | Kiểm tra nào bắt buộc trước merge hoặc release? |
| Optional check | Job nào chỉ cung cấp thông tin và vì sao? |
| Skip condition | Điều kiện nào cho phép bỏ qua? |
| Failure policy | Lỗi nào chặn pipeline, lỗi nào được xử lý theo ngoại lệ? |
| Retry policy | Loại lỗi nào được retry và tối đa bao nhiêu lần? |
| Exception owner | Ai có quyền phê duyệt ngoại lệ và thời hạn của nó? |
| Evidence | Log và kết quả nào chứng minh gate đã thực sự chạy? |

Nếu một kiểm tra bắt buộc không chạy do thiếu secret, thiếu runner hoặc dịch vụ scan không sẵn sàng, kết quả phải là chưa xác minh hoặc thất bại theo chính sách. Không được tự diễn giải “không có kết quả” thành “đã đạt”.

## 9. Định nghĩa quy tắc quyết định cho quality gate

Nhóm nên định nghĩa cách tổng hợp kết quả trước khi pipeline được dùng để quyết định merge hoặc release.

Một ví dụ về quy tắc:

| Kết quả | Pull request | Production release |
|---|---|---|
| Required tests pass lần đầu | Cho phép tiếp tục nếu các gate khác đạt | Cho phép tiếp tục nếu các gate khác đạt |
| Lỗi hạ tầng tạm thời, retry hữu hạn thành công | Cho phép theo policy, ghi nhận recovered | Cho phép nếu artifact/đầu vào không đổi và gate không bị suy yếu |
| Test assertion fail rồi pass khi retry | Đánh dấu unstable, yêu cầu xử lý theo mức rủi ro | Không coi là pass sạch; yêu cầu đánh giá hoặc test thay thế |
| Required security/signature gate thất bại | Chặn | Chặn |
| Required test bị skip ngoài policy | Chặn hoặc yêu cầu phê duyệt ngoại lệ | Chặn |
| Retry hết ngân sách | Chặn gate liên quan | Chặn release tương ứng |
| Test được quarantine có kiểm soát | Theo ngoại lệ và rủi ro | Chỉ tiếp tục nếu có xác minh thay thế được phê duyệt |

Bảng này là chính sách mẫu. Mỗi tổ chức cần điều chỉnh theo criticality, loại sản phẩm và yêu cầu bảo mật. Điều quan trọng là không để một lần pass sau retry tự động biến một test flaky thành bằng chứng sạch.

Có thể biểu diễn logic tổng hợp:

~~~text
if any_required_check_is_missing:
    gate = NOT_VERIFIED
else if any_required_check_has_deterministic_failure:
    gate = FAILED
else if any_security_or_integrity_gate_failed:
    gate = FAILED
else if any_required_test_is_flaky:
    gate = UNSTABLE
else if only_approved_transient_failures_recovered_within_budget:
    gate = RECOVERED
else:
    gate = PASSED
~~~

Trạng thái RECOVERED cần được hiển thị riêng hoặc kèm metadata, không gộp mất vào PASSED_FIRST_ATTEMPT. Tổ chức có thể cho phép RECOVERED đi tiếp theo policy, nhưng vẫn giữ dữ liệu để phát hiện xu hướng bất ổn.

## 10. Ví dụ: test thất bại một lần rồi pass

Một pull request thay đổi logic tính phí. Contract test chạy lần đầu và báo rằng tổng tiền khác kết quả mong đợi. Người phát triển bấm retry; lần hai test pass.

Nếu pipeline chỉ nhìn attempt cuối, pull request có thể được merge. Tuy nhiên, nhóm chưa biết liệu lần đầu là:

- Regression do dữ liệu hoặc trạng thái cũ.
- Race condition khi nhiều test cùng ghi dữ liệu.
- Test phụ thuộc thứ tự chạy.
- Một lỗi thực trong logic tính phí chỉ xuất hiện với một bộ dữ liệu.
- Một lỗi hạ tầng khiến test không đọc được dependency hoặc service.

Quy trình phù hợp là giữ cả hai attempt, so sánh đầu vào, runner, dữ liệu và log. Nếu xác định được lỗi hạ tầng tạm thời, ghi nhận recovered theo retry policy. Nếu cùng test cho kết quả khác nhau trong điều kiện tương đương, đánh dấu flaky và điều tra. Nếu có bằng chứng regression, sửa code và yêu cầu test đạt ổn định.

Vì test liên quan đến tính tiền, nhóm cần đánh giá mức độ rủi ro cao. Không nên dùng quarantine hoặc retry để bỏ qua kiểm tra hợp đồng tài chính mà chưa có biện pháp xác minh thay thế.

## 11. Đo lường chất lượng thay vì chỉ đếm pipeline xanh

Nếu chỉ theo dõi tỷ lệ pipeline thành công cuối cùng, nhóm có thể vô tình khuyến khích retry và bỏ qua lỗi. Hãy bổ sung metric phản ánh những gì xảy ra trước khi pipeline kết thúc.

| Metric | Cách tính hoặc cách đọc | Ý nghĩa |
|---|---|---|
| First-attempt failure rate | Số job thất bại ở attempt đầu / tổng job có chạy | Tín hiệu lỗi ban đầu |
| Retry rate | Số job có ít nhất một retry / tổng job | Mức độ phụ thuộc vào retry |
| Pass-after-retry rate | Số job thất bại đầu nhưng pass sau retry / số job được retry | Tỷ lệ phục hồi sau retry |
| Flaky test rate | Số test có kết quả không nhất quán / số test được quan sát lặp đủ điều kiện | Độ tin cậy của test suite |
| Retry amplification | Tổng số attempt / số job logic | Chi phí thực thi do retry |
| Quarantine age | Thời gian test ở trạng thái quarantine | Mức tồn đọng chất lượng |
| Skipped required checks | Số gate bắt buộc không chạy hoặc bị bỏ qua | Khoảng trống xác minh |
| Escaped defect rate | Lỗi được phát hiện sau merge/release có liên quan đến gate đã bỏ qua | Hệ quả của quality gate yếu |

Ví dụ, nếu 1.000 job có 100 job thất bại ở lần đầu, trong đó 70 job pass sau retry, tỷ lệ pass cuối có thể nhìn rất tốt. Nhưng first-attempt failure rate là 10% và 70 job cần được phân loại để biết bao nhiêu lỗi thực sự là hạ tầng tạm thời, bao nhiêu là flaky hoặc regression.

Cần thống nhất mẫu số, cửa sổ thời gian và cách gom attempt. Không cộng từng attempt vào mẫu số như thể đó là job logic độc lập, vì sẽ làm sai tỷ lệ.

Không dùng metric để xếp hạng cá nhân hoặc ép nhóm đạt tỷ lệ xanh bằng mọi giá. Mục tiêu là phát hiện phần nào của hệ thống tạo ra lỗi lặp lại và kiểm tra các hành động cải tiến có hiệu quả không.

## 12. Phân công trách nhiệm để lỗi không bị bỏ quên

Khi test thất bại, người phát hiện cần cung cấp bằng chứng đủ để nhóm sở hữu kiểm tra. Người sở hữu test hoặc thành phần liên quan chịu trách nhiệm điều tra và sửa. Nhóm nền tảng hỗ trợ khi có dấu hiệu về runner, mạng, registry hoặc cấu hình CI.

Một cách phân công thực tế:

- **Người mở pull request:** đọc failure đầu tiên, phân loại sơ bộ và không tự ý bỏ qua required check.
- **Test owner:** kiểm tra test data, assertion, isolation, timeout và tính xác định.
- **Platform/CI owner:** kiểm tra runner, queue, network, cache và cơ chế retry.
- **Release owner:** đánh giá tác động của trạng thái unstable, quarantine hoặc ngoại lệ trước khi phát hành.
- **Security owner:** xác định cách xử lý khi scan, chữ ký, policy hoặc secret verification không thể hoàn tất.

Mỗi test flaky cần có một owner cụ thể và ticket. Một nhóm chung chung không phải là owner có thể chịu trách nhiệm theo dõi đến khi hoàn tất.

## 13. Các sai lầm cần tránh

| Hành vi | Vì sao nguy hiểm | Thay đổi cần làm |
|---|---|---|
| Retry đến khi pass | Biến lỗi không ổn định thành trạng thái xanh giả | Giới hạn số lần thử và lưu mọi attempt |
| Bỏ qua test lâu ngày bị flaky | Mất bảo vệ cho một hợp đồng quan trọng | Quarantine có thời hạn, owner và test thay thế |
| Dùng continue-on-error cho gate bắt buộc | Pipeline có thể xanh khi kiểm tra thất bại | Phân biệt required và informational job |
| Coi test pass sau retry là pass sạch | Che mất tín hiệu về độ tin cậy | Ghi trạng thái recovered hoặc unstable |
| Retry lỗi cấu hình và xác thực | Tốn tài nguyên mà không sửa điều kiện gây lỗi | Sửa nguyên nhân trước khi chạy lại |
| Retry deployment không idempotent | Có thể tạo release hoặc tác dụng phụ trùng | Đối soát trạng thái và dùng idempotency |
| Chỉ đo final success rate | Không thấy lỗi đầu tiên và chi phí retry | Đo first-attempt failure, retry và flaky rate |
| Quarantine không có ngày hết hạn | Ngoại lệ trở thành vĩnh viễn | Theo dõi tuổi và cảnh báo quá hạn |
| Chỉ kiểm tra job đã chạy | Bỏ sót gate bị skip | Báo cáo required check chưa được thực thi |

## 14. Checklist trước khi chấp nhận một pipeline xanh

- [ ] Tất cả required checks đã chạy hoặc được bỏ qua theo ngoại lệ có chủ sở hữu và lý do rõ ràng.
- [ ] Không có lỗi xác định bị retry chỉ để chờ một lần pass.
- [ ] Mọi retry đều có điều kiện, giới hạn số lần và tổng thời gian.
- [ ] Lần thất bại đầu tiên và toàn bộ attempt sau được lưu lại.
- [ ] Kết quả pass sau retry được phân biệt với pass lần đầu.
- [ ] Test flaky có owner, ticket, thời hạn quarantine và cách xác minh thay thế.
- [ ] Security, signature, provenance và policy gates không bị bỏ qua để đạt trạng thái xanh.
- [ ] Các thao tác có tác dụng phụ được kiểm tra idempotency trước khi retry.
- [ ] Báo cáo pipeline thể hiện rõ failed, recovered, flaky, quarantined và skipped.
- [ ] Quality gate có quy tắc quyết định cho pull request và production release.
- [ ] Metric theo dõi first-attempt failure, retry rate và tuổi quarantine.
- [ ] Ngoại lệ được review lại và gỡ bỏ sau khi nguyên nhân đã được xử lý.

## 15. Nguyên tắc kết thúc

Trạng thái xanh chỉ đáng tin khi nó phản ánh những kiểm tra đã thực sự chạy và bằng chứng của chúng. Bỏ qua một lỗi hoặc thử lại vô hạn có thể làm pipeline hoàn tất, nhưng không làm phần mềm an toàn hơn và cũng không làm test đáng tin cậy hơn.

Khi gặp thất bại, hãy giữ bằng chứng, phân loại lỗi, retry có giới hạn nếu có căn cứ, điều tra test không ổn định và giữ quality gate trung thực. Một pipeline đôi khi phải báo đỏ để bảo vệ quyết định phát hành. Đó là phản hồi có giá trị: nó cho nhóm biết nơi cần sửa trước khi rủi ro đi xa hơn.
