# Retry budget

## 1. Từ khả năng phục hồi đến nguy cơ khuếch đại sự cố

Trong chương **Availability và resilience**, retry budget là ngân sách giới hạn lượng công việc bổ sung mà hệ thống được phép tạo ra do thử lại. Mục tiêu là cho phép phục hồi trước lỗi tạm thời mà vẫn bảo vệ tài nguyên, dịch vụ phụ thuộc và khả năng phục vụ của các yêu cầu khác.

Retry có thể giúp một yêu cầu vượt qua lỗi kết nối ngắn. Tuy nhiên, khi dịch vụ phụ thuộc đang quá tải, việc nhiều client đồng loạt thử lại có thể làm tình hình xấu hơn: request mới tiếp tục đến, retry tạo thêm tải, độ trễ tăng, timeout tăng và lại sinh thêm retry. Đây là vòng phản hồi cần được kiểm soát bằng yêu cầu bảo mật đo được.

Một yêu cầu như “hệ thống phải tự retry khi lỗi” chưa đủ. Cần trả lời: retry ở đâu, cho loại lỗi nào, tối đa bao nhiêu, dùng chung ngân sách với ai, trong thời hạn nào và dừng bằng cách nào khi ngân sách hết.

Sau bài học, người học cần có khả năng:

- Phân biệt giới hạn số lần thử của một thao tác với ngân sách retry của một nhóm lưu lượng.
- Chọn đại lượng, phạm vi và thuật toán ngân sách có thể kiểm chứng.
- Kết hợp retry budget với deadline, backoff, idempotency và các giới hạn tài nguyên.
- Liên kết rủi ro khuếch đại tải với yêu cầu kiến trúc, logging và ca kiểm thử.

Các ngưỡng và thời gian trong bài là **ví dụ cho hệ thống giả định**, cần hiệu chỉnh theo đo tải, mô hình đe dọa và mục tiêu phục vụ của hệ thống thực tế.

## 2. Thống nhất thuật ngữ và cách đếm

Một **thao tác logic** là công việc mà caller muốn hoàn thành, chẳng hạn tạo một báo cáo hoặc lấy số dư. Một thao tác có thể phát sinh nhiều **lần thực hiện**, còn gọi là attempt.

Trong phạm vi một lời gọi tới một dịch vụ phụ thuộc:

- **Initial attempt:** lần gọi đầu của thao tác tại ranh giới đang xét.
- **Retry attempt:** lần gọi bổ sung để thực hiện lại thao tác sau một kết quả hoặc tình trạng được chính sách cho phép thử lại.
- **Hedged attempt:** lần gọi bổ sung được gửi khi lần trước vẫn đang chạy, với hy vọng một bản sao hoàn thành sớm hơn.
- **Retry budget:** giới hạn dùng chung cho các lần gọi bổ sung trong một phạm vi đã chọn.
- **Per-operation attempt limit:** số attempt tối đa của riêng một thao tác, gồm hoặc không gồm initial attempt tùy hợp đồng; tài liệu phải nói rõ.

Ví dụ, “tối đa 3 attempt” thường được đặc tả thành 1 lần đầu và tối đa 2 lần retry. Cụm “retry 3 lần” có thể được hiểu thành tổng cộng 4 attempt. Không dùng hai cách diễn đạt này thay thế nhau.

Trong bài, khi tính ngân sách, **lần gọi bổ sung** bao gồm retry và hedging nếu có. Điều này ngăn một triển khai chuyển sang hedging để tạo cùng loại tải nhưng né cơ chế đếm retry.

Cần định nghĩa ranh giới đếm: bài này xét các lần gọi ứng dụng từ service A sang dependency B. Kết nối TCP được thiết lập lại nhưng chưa phát sinh lời gọi ứng dụng không mặc nhiên được tính là một retry ứng dụng; tài nguyên kết nối vẫn cần giới hạn riêng.

## 3. Vì sao giới hạn retry cho từng request chưa đủ?

### 3.1. Nhiều thao tác cùng retry

Giả sử có 1.000 thao tác ban đầu và mỗi thao tác được phép retry 2 lần. Nếu mọi thao tác đều thất bại, dependency có thể nhận:

```text
1.000 initial attempts + 2.000 retry attempts = 3.000 attempts
```

Giới hạn 2 retry/thao tác vẫn cho phép tổng tải tăng gấp 3. Khi dependency đã suy giảm năng lực, phần tải bổ sung này có thể ngăn nó phục hồi.

Một ngân sách chung cho phép nói: “Dù mỗi thao tác có thể retry tối đa 2 lần, toàn bộ nhóm lưu lượng chỉ được phát thêm một lượng retry có cận.” Hai giới hạn bổ sung cho nhau.

### 3.2. Retry ở nhiều tầng

Xét chuỗi:

```text
Client -> API -> Service -> Dependency
```

Nếu có ba tầng retry độc lập và mỗi tầng cho phép tối đa 3 attempt cho một lời gọi mà nó quản lý, một thao tác gốc có thể tạo tới:

```text
3 × 3 × 3 = 27 attempts tới tầng cuối
```

Đây là trường hợp xấu nhất khi các lần gọi đều đi tới tầng cuối và các tầng bên ngoài vẫn còn điều kiện thử lại. Con số không có nghĩa mọi thao tác đều tạo 27 attempt, nhưng cho thấy giới hạn cục bộ có thể nhân lên.

Các retry ẩn trong SDK, proxy, service mesh hoặc consumer xử lý lại message cũng phải được nhận diện. Đặt ngân sách ở một lớp không tự kiểm soát các lần gửi phát sinh bên trong lớp khác.

### 3.3. Góc nhìn mô hình đe dọa

Rủi ro không chỉ xuất phát từ client có lỗi. Một tác nhân có thể cố ý tạo thao tác đắt tài nguyên, gây lỗi lặp lại, thay danh tính hoặc khai thác đường retry thiếu kiểm soát để làm tăng chi phí.

| Rủi ro | Tác động | Yêu cầu kiểm soát cần xem xét |
|---|---|---|
| Nhiều caller retry đồng loạt | Tăng tải lên dependency đang suy yếu | Ngân sách chung, backoff, jitter và giới hạn đồng thời |
| Retry lồng nhau qua nhiều tầng | Khuếch đại số lần gọi cuối chuỗi | Chốt tầng sở hữu retry; kiểm soát attempt xuyên tầng |
| Timeout sau khi tạo tác dụng phụ | Tạo đơn hàng, thanh toán hoặc job trùng | Idempotency, đối soát và quy tắc lỗi được retry |
| Tenant A gây nhiều retry | Chiếm phần phục hồi của tenant B | Ngân sách theo tenant và cận chung cho dependency |
| Thay key hoặc restart để lấy ngân sách mới | Vượt cận tải đã thiết kế | Khóa ổn định, trạng thái dùng chung và quy tắc khởi động |
| Request mới được dùng để tạo thêm tín dụng retry | Ngân sách tăng theo tải tấn công | Admission control, rate limit và điều kiện cấp tín dụng |

Một retry budget không giới hạn lượng request ban đầu. Nếu initial traffic đã vượt năng lực hệ thống, vẫn cần cơ chế kiểm soát tiếp nhận riêng.

## 4. Chọn mô hình ngân sách và công thức đo

### 4.1. Định nghĩa tỷ lệ một cách tường minh

Trong một khoảng quan sát, đặt:

- `O`: số initial attempt đủ điều kiện được tiếp nhận tại ranh giới đã chọn.
- `R`: số lần gọi bổ sung đã được phát.
- `A = O + R`: tổng attempt trong phạm vi đó.

Nếu chính sách nói “retry tối đa 10% initial attempts”, tỷ lệ cần đo là:

```text
retry_ratio = R / O, khi O > 0
```

Đây khác với `R / A`. Khi `R = 0,1 × O`, tỷ lệ retry trên tổng attempt xấp xỉ 9,09%. Tài liệu và dashboard cần dùng cùng mẫu số.

Khi `O = 0`, không được chia cho 0 hoặc tự hiểu tỷ lệ bằng 0. Hãy thể hiện trạng thái không có mẫu số và báo riêng số retry tuyệt đối. Ngân sách burst hoặc tín dụng còn lại vẫn có thể cho phép retry trong lúc không có initial attempt mới.

### 4.2. Mô hình cửa sổ quan sát

Một thiết kế có thể đặt cận retry dựa trên initial attempts trong cửa sổ gần nhất. Khi chọn cách này, phải chốt:

- Fixed window hay sliding window, độ dài và quy ước biên.
- Có phần ngân sách tối thiểu hoặc burst cho lưu lượng thấp hay không.
- Làm tròn phần trăm ra số attempt như thế nào.
- Tính cả initial attempt thất bại hay chỉ các lần thành công.
- Cách xử lý khi lượng initial traffic giảm mạnh.

Ví dụ, giới hạn “10 retry trong mỗi phút theo mốc cố định” có thể cho 10 retry ở cuối phút và 10 retry ở đầu phút kế tiếp. Nó không đồng nghĩa với tối đa 10 retry trong mọi khoảng 60 giây liên tiếp.

Nếu ngân sách chỉ được cấp từ lần gọi thành công, dependency lỗi kéo dài sẽ làm cạn tín dụng nhanh hơn. Nếu cấp từ mọi initial attempt được tiếp nhận, chính sách sẽ có hành vi khác trong sự cố. Đây là lựa chọn cần được đặc tả, không phải chi tiết có thể bỏ qua.

### 4.3. Mô hình bucket tín dụng theo initial attempt

Bài dùng mô hình minh họa sau:

- Dung lượng bucket tối đa là `Bmax` đơn vị retry.
- Số dư ban đầu là `B0`, với `0 <= B0 <= Bmax`.
- Mỗi initial attempt đủ điều kiện cấp `β` đơn vị tín dụng.
- Mỗi lần gọi bổ sung tiêu thụ 1 đơn vị.
- Không tự nạp tín dụng theo thời gian.
- Số dư không được âm; tín dụng vượt `Bmax` bị bỏ.

Quy tắc logic:

```text
initial attempt đủ điều kiện:
    credits = min(Bmax, credits + β)

retry hoặc hedged attempt:
    chỉ được cấp phép nếu credits >= 1
    credits = credits - 1
```

Với cập nhật nguyên tử và không có nguồn tín dụng khác, trong khoảng `(t1, t2]`:

```text
R(t1, t2) <= credits(t1) + β × O(t1, t2)
         <= Bmax + β × O(t1, t2)
```

Phần burst khiến tỷ lệ trong một cửa sổ ngắn có thể vượt `β`. Vì vậy, không mô tả bucket này thành “mọi cửa sổ đều có retry_ratio <= β”.

Ví dụ: `Bmax = 20`, `B0 = 20`, `β = 0,1`. Sau khi bucket cạn, 100 initial attempt mới chỉ cấp đủ tín dụng cho tối đa 10 lần gọi bổ sung. Từ lúc khởi tạo, nếu có 1.000 initial attempt, cận trên là:

```text
R <= 20 + 0,1 × 1.000 = 120
A <= 1.000 + 120 = 1.120
```

Cận trên không bảo đảm toàn bộ 120 retry đều có thể phát: tín dụng có thể bị bỏ khi bucket đầy, hoặc thao tác bị chặn vì deadline, số attempt hay giới hạn tài nguyên khác.

Mô hình này cũng không tự dàn đều retry theo thời gian. Nếu cần cận số retry/giây hoặc burst tức thời nhỏ hơn, phải kết hợp thêm rate limit hoặc cơ chế điều phối.

### 4.4. Trường hợp chi phí không đồng đều

Một retry truy vấn nhỏ và một retry xuất báo cáo lớn có thể khác nhau hàng trăm lần về chi phí. Khi cần, có thể tính ngân sách theo điểm công việc thay vì số attempt.

Khi đó công thức, cách cấp tín dụng và metric phải cùng đơn vị chi phí. Không trộn `R` đo bằng số request với tín dụng đo bằng điểm CPU mà vẫn dùng công thức tỷ lệ request. Chi phí phải do server xác định hoặc kiểm chứng, không tin trực tiếp số do client khai.

## 5. Điều kiện để một attempt được phép retry

Có tín dụng không đồng nghĩa với được phép thực hiện lại mọi thao tác. Một retry chỉ được phát khi đồng thời thỏa các điều kiện sau:

1. Kết quả trước đó thuộc nhóm được chính sách cho phép retry.
2. Ngữ nghĩa nghiệp vụ cho phép thực hiện lại an toàn hoặc có cơ chế chống tác dụng phụ trùng.
3. Thao tác chưa bị hủy và còn đủ deadline.
4. Chưa vượt giới hạn attempt của chính thao tác.
5. Dependency không bị chặn bởi chính sách sức khỏe hoặc circuit breaker.
6. Các giới hạn tốc độ, đồng thời và ngân sách retry đều cho phép.

### 5.1. Phân loại lỗi và tác dụng phụ

| Tình huống | Cách đánh giá |
|---|---|
| Đứt kết nối trước khi gửi lời gọi ứng dụng | Có thể thử lại nếu transport xác định được trạng thái; vẫn chịu giới hạn kết nối và deadline |
| Timeout sau khi gửi request | Kết quả nghiệp vụ có thể chưa xác định; phải xét idempotency hoặc đối soát |
| Lỗi phụ thuộc tạm thời | Chỉ retry nếu hợp đồng thao tác cho phép và còn điều kiện tài nguyên |
| Bị rate limit | Tôn trọng hướng dẫn chờ; không dùng retry để vượt giới hạn |
| Sai dữ liệu đầu vào, thiếu quyền hoặc credential không hợp lệ | Không lặp lại nguyên request một cách mù quáng |
| Caller đã hủy hoặc deadline đã hết | Dừng; không tạo thêm attempt |
| Dependency thông báo không nên thử lại | Dừng theo hợp đồng, không bỏ qua chỉ vì còn tín dụng |

Không quyết định retry chỉ dựa vào một mã HTTP mà bỏ qua ngữ nghĩa thao tác. Ví dụ, mất phản hồi sau khi tạo đơn hàng không chứng minh đơn hàng chưa tồn tại. Gửi lại một thao tác tạo mới thiếu idempotency có thể tạo trùng.

Idempotency cần có phạm vi khóa, ràng buộc với tenant và nội dung, thời hạn hiệu lực và cách xử lý hai request đồng thời. Một idempotency key do client gửi không tự bảo đảm an toàn nếu server không thực thi hợp đồng đó.

### 5.2. Retry budget và các cơ chế phục hồi khác

| Cơ chế | Câu hỏi nó trả lời |
|---|---|
| Per-operation attempt limit | Một thao tác được thử tổng cộng bao nhiêu lần? |
| Retry budget | Cả nhóm lưu lượng được tạo thêm bao nhiêu công việc do thử lại? |
| Backoff và jitter | Khi đã đủ điều kiện, lần thử tiếp theo nên diễn ra lúc nào? |
| Deadline | Toàn bộ thao tác còn bao nhiêu thời gian hữu ích? |
| Rate limit | Có thể đưa vào bao nhiêu request hoặc đơn vị công việc theo thời gian? |
| Concurrency limit | Có thể có bao nhiêu attempt đang chiếm tài nguyên? |
| Circuit breaker | Khi dependency có dấu hiệu hỏng, có nên tiếp tục gọi bình thường không? |
| Idempotency | Thực hiện lại có tạo thêm tác dụng phụ ngoài ý muốn không? |

Một retry budget cạn không nhất thiết làm initial attempt bị từ chối. Initial traffic vẫn được kiểm soát bởi admission control, chính sách sức khỏe và năng lực còn lại. Phải tách nguyên nhân từ chối để không quy mọi lỗi thành “hết retry”.

Các lần thăm dò phục hồi của circuit breaker cần ngân sách riêng hoặc quy tắc tính vào ngân sách hiện có. Nếu có ngoại lệ, phải chốt cận tốc độ, số probe đồng thời và chủ thể được phát. Không tạo một nhánh retry không giới hạn dưới tên “health check” hoặc “probe”.

## 6. Chọn phạm vi ngân sách và chủ thể tin cậy

Một khóa ngân sách có thể gồm:

```text
(policy_version, caller_service, dependency_group, operation_class, tenant_scope)
```

Mỗi thành phần cần có nguồn xác định và quy tắc chuẩn hóa. Không dùng URL tùy ý, request ID hoặc API key có thể thay liên tục để tạo bucket mới cho cùng một chủ thể bảo vệ.

### 6.1. Tách và kết hợp ngân sách

- Ngân sách theo dependency ngăn lỗi của dependency B tiêu thụ hết khả năng thử lại khi gọi dependency C.
- Ngân sách theo nhóm thao tác tách các luồng có chi phí và ưu tiên khác nhau.
- Ngân sách theo tenant hạn chế một tenant chiếm toàn bộ phần retry.
- Ngân sách chung cho dependency tạo cận tổng khi có nhiều tenant hoặc nhiều caller.

Nếu yêu cầu cả ngân sách tenant lẫn ngân sách chung, retry phải đáp ứng cả hai. Một tập ngân sách riêng lẻ cho hàng nghìn tenant không thay thế cận tải tổng.

Cũng cần xác định công bằng khi tranh tín dụng. Một bucket chung đơn thuần có thể bị một caller tiêu thụ hết ngay khi được nạp. Nếu cần phần phục hồi tối thiểu cho luồng quan trọng, phải đặc tả cơ chế phân bổ hoặc ưu tiên thay vì suy ra từ sự tồn tại của bucket.

### 6.2. Khi nào một initial attempt được cấp tín dụng?

Trong mô hình minh họa, chỉ initial attempt được admission control cho phép và ghi nhận tại ranh giới gửi xuống dependency mới đủ điều kiện cấp tín dụng. Việc ghi nhận phải chống lặp cho cùng một lần cấp tín dụng.

Không cấp tín dụng cho:

- Request không xác thực hoặc không đủ quyền khi luồng yêu cầu xác thực, phân quyền.
- Request bị từ chối trước khi được tiếp nhận để gọi dependency.
- Một retry tự đổi nhãn thành “initial”.
- Cùng một sự kiện được gửi lại nhiều lần do lỗi mạng hoặc xử lý lại telemetry.

Tín dụng phải được ghi nhận tại điểm thực thi đáng tin, không suy ra từ một header `isRetry=false` do caller không đáng tin tự khai. Request mới hợp lệ vẫn có thể làm tăng tín dụng; vì thế rate limit và chính sách tiếp nhận initial traffic là thành phần bắt buộc khi rủi ro tải đòi hỏi.

Nếu một thiết kế cấp tín dụng ở thời điểm hoàn thành thay vì lúc tiếp nhận, cần viết lại công thức và các ca kiểm thử tương ứng. Không trộn hai mốc đếm trên dashboard và bộ thực thi.

### 6.3. Tầng sở hữu retry và fan-out

Với một đường gọi, nên xác định rõ tầng nào chịu trách nhiệm retry cho từng loại lỗi. Các retry tự động ở SDK hoặc proxy phải được tắt, giới hạn hoặc đưa vào cùng cách đếm có thể quan sát.

Một request gốc có thể fan-out thành nhiều lời gọi khác nhau. Những lời gọi cần thiết để thực hiện công việc ban đầu không phải tất cả đều là retry. Tuy nhiên, chúng vẫn tạo tải; cần mô hình hóa fan-out và ngân sách công việc ban đầu riêng.

Ngược lại, retry toàn bộ thao tác cha có thể tạo lại tất cả các nhánh fan-out. Cận theo từng dependency không tự bảo đảm cận số attempt cho một request gốc.

Nếu truyền “số attempt còn lại” qua các tầng, phải xử lý hai vấn đề:

1. Ngữ cảnh phải có tính toàn vẹn và được xác minh tại ranh giới tin cậy.
2. Hai nhánh song song không được cùng sử dụng toàn bộ ngân sách còn lại như thể chúng sở hữu độc lập.

Có thể cần phân chia ngân sách cho từng nhánh hoặc một cơ chế cấp phép dùng chung. Chỉ thêm một header chứa số nguyên không giải quyết được việc dùng ngân sách hai lần.

## 7. Backoff, deadline và vòng đời một retry

### 7.1. Đợi đúng lúc, không chỉ đợi đủ lâu

Một ví dụ exponential backoff với full jitter cho retry thứ `k`, bắt đầu từ `k = 1`:

```text
upper_bound(k) = min(backoff_cap, base_delay × 2^(k - 1))
jitter_delay(k) = random_uniform(0, upper_bound(k))
```

Nếu dependency công bố thời gian tối thiểu trước khi thử lại, lịch gửi không được sớm hơn mốc đó:

```text
delay = max(jitter_delay, thời_gian_chờ_tối_thiểu_còn_lại)
```

Đây là ví dụ chính sách, không phải công thức bắt buộc cho mọi hệ thống. Cần chốt cách giới hạn giá trị, cách xử lý hướng dẫn chờ không hợp lệ và hành vi khi thời gian chờ vượt deadline.

Jitter giảm nguy cơ đồng bộ các lần retry, nhưng không tạo cận tổng số retry. Ngược lại, retry budget không tự ngăn mọi attempt cùng dồn vào một thời điểm.

### 7.2. Deadline và timeout của từng attempt

Gọi `Dremaining` là thời gian còn lại của thao tác. Trước khi lên lịch retry, cần kiểm tra:

```text
Dremaining >= delay + minimum_useful_attempt_time + processing_margin
```

Đến thời điểm thực sự phát attempt, phải kiểm tra lại deadline và trạng thái hủy. Timeout của attempt không được vượt phần deadline còn lại sau khi trừ chi phí cần thiết để xử lý kết quả.

Không chỉ giới hạn timeout riêng của từng attempt rồi để tổng thời gian vô hạn. Một caller đã hết nhu cầu mà service vẫn tiếp tục retry sẽ tạo công việc mồ côi và giữ tài nguyên không cần thiết.

### 7.3. Mã giả cho điểm quyết định

```text
on_attempt_result(operation, result):
    if not retry_policy.allows(result, operation):
        return finish_without_retry(result)

    if operation.total_attempts >= max_total_attempts:
        return finish_with_reason("attempt_limit")

    delay = compute_backoff_jitter_and_server_minimum(result)

    if not fits_remaining_deadline(operation, delay):
        return finish_with_reason("deadline")

    schedule_after(delay):
        if operation.cancelled or not has_useful_time_left(operation):
            return finish_with_reason("cancelled_or_deadline")

        if not health_and_admission_allow(operation):
            return finish_with_reason("dependency_or_capacity")

        if not retry_budget.try_consume_atomically(scope, cost=1):
            return finish_with_reason("retry_budget_exhausted")

        dispatch_next_attempt_with_bounded_timeout(operation)
```

Mã giả thể hiện thứ tự logic, chưa thay thế thiết kế đồng thời và xử lý lỗi thực tế. Một lần tiêu thụ thành công phải gắn với nhiều nhất một lần phát attempt; không được dùng cùng giấy phép cho hai nhánh gửi.

Kiểm tra ngân sách sát thời điểm phát giúp tránh giữ tín dụng trong suốt thời gian backoff. Không tạo task chờ, timer hoặc queue vô hạn cho các retry đã lên lịch; các tài nguyên này cũng cần cận và phải được giải phóng khi hủy.

Trong ví dụ này, nếu đã tiêu thụ tín dụng rồi bị hủy trước khi gửi, tín dụng không được hoàn lại. Đây là lựa chọn bảo thủ: giảm khả năng tận dụng nhưng không tạo thêm tải. Nếu thiết kế có hoàn lại, việc hoàn phải xảy ra nhiều nhất một lần và chỉ khi chứng minh attempt chưa được phát.

Khi đã gửi nhưng mất phản hồi, không tự hoàn tín dụng. Kết quả chưa xác định không đồng nghĩa với dependency chưa chịu tải.

## 8. Tính đúng trong hệ thống phân tán và khi có sự cố

### 8.1. Cấp và tiêu thụ tín dụng phải nguyên tử

Nếu hai replica cùng đọc “còn 1 tín dụng” rồi đều gửi retry, ngân sách đã bị vượt. Quyết định đọc, kiểm tra và trừ phải được thực thi nguyên tử trong phạm vi ngân sách đã cam kết.

Tương tự, một sự kiện initial attempt được xử lý hai lần có thể cấp hai lần tín dụng. Thiết kế cần định danh sự kiện, chống lặp hoặc một ranh giới cập nhật có tính chất tương đương.

Có thể dùng đơn vị số nguyên nhỏ để biểu diễn tín dụng phân số. Ví dụ, với `β = 0,1`, mỗi initial attempt cấp 1 đơn vị nhỏ và mỗi retry tốn 10 đơn vị nhỏ. Cần chốt quy tắc làm tròn, giới hạn số và hành vi khi đổi tham số.

### 8.2. Ngân sách cục bộ và ngân sách chung

Nếu mỗi replica có `B0 = 20` và có 10 replica, tổng tín dụng khởi tạo có thể là 200. Thêm replica hoặc restart có thể tiếp tục cấp thêm nếu trạng thái chỉ nằm trong bộ nhớ từng process.

Nếu yêu cầu `B0 = 20` cho toàn bộ một nhóm dependency, con số đó phải được chia sẻ hoặc phân bổ từ một nguồn chung. Không mô tả 20 tín dụng/replica thành 20 tín dụng toàn hệ thống.

Các lựa chọn triển khai có thể gồm:

- Kho trạng thái chung với thao tác cấp phép nguyên tử.
- Chia phần ngân sách cho replica từ một tổng ngân sách đã được trừ trước.
- Ngân sách cục bộ với cận tổng được chứng minh và được yêu cầu cho phép.

Khi cấp ngân sách theo phần, phải chốt vòng đời phần đã cấp, xử lý mất replica và thời điểm tái sử dụng. Thu hồi tín dụng trong khi replica cũ vẫn còn quyền tiêu thụ có thể tạo quyền chi tiêu trùng.

Metric tổng hợp chậm có thể dùng để quan sát nhưng không đủ làm bộ thực thi chính xác nếu yêu cầu không chấp nhận vượt ngưỡng. Sai số phân tán, nếu được phép, phải có cận và điều kiện áp dụng rõ ràng.

### 8.3. Kết quả không chắc chắn và chế độ lỗi

Một caller có thể timeout khi xin tín dụng sau khi kho đã trừ thành công. Trong mô hình bảo thủ, caller không gửi retry nếu chưa xác định được giấy phép. Không xin lại rồi gửi hai lần dựa trên hai kết quả đến muộn.

Nếu có mã cấp phép để đối soát, cần quy định hạn dùng, thao tác tiêu thụ và chống dùng lại. Nếu không có cơ chế đó, chấp nhận mất một phần tín dụng thường dễ bảo toàn cận tải hơn việc hoàn lại dựa trên phỏng đoán.

Ví dụ chính sách lỗi cho dependency đắt tài nguyên:

> Khi không thể xác định ngân sách, không phát retry mới. Initial attempt vẫn chịu admission control và chính sách sức khỏe hiện hành. Các attempt đang chạy giữ timeout và cơ chế hủy đã định nghĩa.

Chính sách khác có thể dùng ngân sách dự phòng được cấp trước, nhưng phải nêu cận tổng và thời hạn. Không âm thầm chuyển sang “mỗi replica tự cho thêm 20 retry” mà vẫn tuyên bố giữ nguyên cận toàn hệ thống.

### 8.4. Hết hạn trạng thái, khởi động và thay đổi cấu hình

Bucket trong mô hình này không tự nạp theo thời gian. Tuy nhiên, tín dụng còn lại có thể được giữ lâu nếu không có quy tắc hết hạn. Cần xác định:

- Trạng thái giữ bao lâu khi không có lưu lượng.
- Khởi tạo lại dùng số dư nào và sự kiện nào được phép khởi tạo.
- Restart, eviction hoặc đổi phiên bản policy có làm mất hay cấp lại tín dụng không.
- Khi giảm `Bmax`, số dư được cắt xuống thế nào.
- Khi thay `β`, tham số mới có hiệu lực từ mốc nào.
- Ai được đổi cấu hình, cấp ngoại lệ và kiểm tra dấu vết thay đổi.

Nếu bất kỳ reset nào cũng cấp lại `B0`, cận công thức phải cộng thêm tín dụng do reset. Muốn giữ cận cũ, phải ngăn việc cấp lại ngoài các sự kiện khởi tạo đã cho phép.

## 9. Ví dụ đặc tả yêu cầu bảo mật: gọi dịch vụ báo cáo

### 9.1. Bối cảnh và rủi ro

Service A gọi dependency B để lấy trạng thái xử lý báo cáo. Luồng đọc được hợp đồng xác nhận là không tạo tác dụng phụ nghiệp vụ. Rủi ro `R-RB-01` là khi B chậm hoặc lỗi, A tạo nhiều lần thử bổ sung khiến B khó phục hồi và làm cạn connection pool của A.

Ví dụ chọn một ngân sách chung tại ranh giới A gọi B cho nhóm thao tác `report-status-read`. Retry tự động khác trong SDK hoặc proxy trên đường này phải được vô hiệu hoặc đưa vào cùng cơ chế cấp phép.

### 9.2. Tập yêu cầu minh họa

| ID | Yêu cầu |
|---|---|
| SEC-RB-01 | Ngân sách cho `report-status-read` áp dụng chung trên mọi replica A trong phạm vi triển khai, có `Bmax = 20`, `B0 = 20`, `β = 0,1`. Không có nạp theo thời gian. |
| SEC-RB-02 | Chỉ initial attempt được tiếp nhận tại ranh giới gọi B mới cấp tín dụng, nhiều nhất một lần cho mỗi sự kiện hợp lệ. Retry, request bị từ chối trước ranh giới và telemetry gửi lặp không cấp tín dụng. |
| SEC-RB-03 | Mỗi retry hoặc hedged attempt phải tiêu thụ 1 tín dụng trước khi phát. Các thao tác cấp và trừ bảo toàn cận `R <= B0 + β × O` từ lúc khởi tạo, nếu không có reset hoặc tín dụng bổ sung được phép. |
| SEC-RB-04 | Mỗi thao tác có tối đa 3 attempt, gồm 1 initial attempt và tối đa 2 lần bổ sung. Deadline toàn thao tác là 1.500 ms; timeout mỗi attempt không vượt 400 ms hoặc thời gian còn lại cho phép, tùy giá trị nào nhỏ hơn. |
| SEC-RB-05 | Chỉ retry các lỗi tạm thời có trong danh sách chính sách cho nhóm thao tác. Không retry khi caller đã hủy, thiếu quyền, sai đầu vào hoặc không còn ít nhất 100 ms hữu ích cho attempt và 20 ms xử lý kết quả. |
| SEC-RB-06 | Dùng full jitter với base delay 100 ms và cap 500 ms. Nếu B cung cấp thời gian chờ tối thiểu hợp lệ thì không gửi sớm hơn; nếu không vừa deadline thì dừng. |
| SEC-RB-07 | Khi hết tín dụng hoặc không xác định được giấy phép, không phát attempt bổ sung. Trả kết quả lỗi theo hợp đồng API với nguyên nhân kết thúc nội bộ có thể phân biệt. |
| SEC-RB-08 | Restart hoặc autoscaling không cấp lại `B0`; eviction hoặc mất trạng thái không được tự tạo một bucket đầy. Nếu chưa khôi phục được trạng thái tin cậy, dừng retry mới. |
| SEC-RB-09 | Tại ranh giới A gọi B, tổng initial và retry chịu giới hạn không quá 50 attempt đang chạy đồng thời. Cấp phép retry không miễn trừ giới hạn này hoặc giới hạn tốc độ khác. |
| SEC-RB-10 | Mỗi lần phát attempt được gắn với thao tác logic và số thứ tự attempt nội bộ; dữ liệu quan sát phân biệt initial, retry, hedging và lý do dừng. |
| SEC-RB-11 | Thay đổi ngưỡng, reset hoặc ngoại lệ phải được phân quyền, ghi người thực hiện, lý do, phạm vi, thời điểm và thời hạn nếu có. Tín dụng cấp thêm phải được ghi nhận trong kiểm chứng cận. |

“Danh sách lỗi tạm thời” trong SEC-RB-05 phải được nhóm thiết kế cụ thể hóa theo hợp đồng với B, ví dụ lỗi kết nối có trạng thái xác định và nhóm lỗi phụ thuộc có thể thử lại. Không suy ra rằng mọi timeout hoặc mọi phản hồi lỗi server đều an toàn cho mọi loại thao tác.

Vì ví dụ dùng thao tác đọc, cách đánh giá an toàn khác với tạo báo cáo, chuyển tiền hoặc gửi OTP. Khi tái sử dụng mẫu, phải đánh giá lại ngữ nghĩa và yêu cầu idempotency.

### 9.3. Liên kết với kiến trúc và rủi ro

| Rủi ro hoặc mục tiêu | Yêu cầu | Quyết định kiến trúc cần chứng minh | Bằng chứng |
|---|---|---|---|
| R-RB-01: Retry làm tăng tải trong sự cố | SEC-RB-01, 02, 03 | Bộ cấp phép chung, cấp tín dụng chống lặp | Số attempt thực phát và lịch sử tín dụng |
| Một thao tác giữ tài nguyên quá lâu | SEC-RB-04, 05, 06 | Deadline truyền xuyên lời gọi, timeout có cận, hủy timer | Timeline từng thao tác và thử hủy |
| Nhiều replica cùng tiêu thụ số dư cuối | SEC-RB-03, 08 | Cập nhật nguyên tử, trạng thái sống qua restart | Kiểm thử tranh chấp và restart |
| Retry vượt giới hạn connection pool | SEC-RB-09 | Admission control cho mọi attempt | Mức đồng thời cực đại và số lần bị chặn |
| Không điều tra được nguyên nhân dừng | SEC-RB-10 | Metric, trace và reason code thống nhất | Đối chiếu bộ đếm với sự kiện gửi |
| Reset cấu hình làm mất cận ngân sách | SEC-RB-08, 11 | Quyền reset và audit; công thức có tín dụng bổ sung | Thử quyền thay đổi và kiểm tra cận sau reset |

## 10. Tiêu chí kiểm thử và bằng chứng

### 10.1. Ma trận kiểm chứng

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Số dư có cận | Kiểm thử bộ cấp phép với 20 tín dụng, không có sự kiện cấp thêm; xin 21 giấy phép retry | Chỉ 20 lần thành công, số dư không âm |
| T02 — Cấp tín dụng | Từ số dư 0, ghi nhận 100 initial attempt đủ điều kiện rồi xin giấy phép | Cấp được 10 giấy phép; không có nạp theo thời gian |
| T03 — Trần bucket | Số dư đang là 20; ghi thêm nhiều initial attempt | Số dư vẫn không vượt 20; không tích lũy tín dụng ngoài bucket |
| T04 — Tranh tín dụng cuối | Chỉ còn 1 tín dụng; 50 caller qua nhiều replica đồng thời xin giấy phép | Nhiều nhất 1 caller được phép phát retry |
| T05 — Cận tổng | Từ khởi tạo, tạo 1.000 initial attempt và các lỗi cho phép retry, xen kẽ theo lịch kiểm thử, không reset | Tổng retry thực phát không vượt 120, dù từng thao tác còn attempt |
| T06 — Chống cấp lặp | Gửi cùng sự kiện initial attempt nhiều lần | Chỉ được cấp tín dụng một lần |
| T07 — Không tự cấp tín dụng | Phát retry và các request bị admission control từ chối | Các sự kiện này không tăng tín dụng |
| T08 — Deadline | Lịch backoff hoặc thời gian chờ từ B không vừa deadline | Không phát retry ngoài thời gian hữu ích; có lý do dừng rõ ràng |
| T09 — Giới hạn từng thao tác | Ngân sách còn nhiều, B tiếp tục trả lỗi được retry | Không có attempt thứ 4 cho cùng thao tác |
| T10 — Mất trạng thái | Restart replica, thêm replica hoặc làm kho trạng thái không truy cập được | Không nhận thêm tín dụng khởi tạo; không phát retry thiếu giấy phép |
| T11 — Hủy | Hủy thao tác trong thời gian backoff và sát thời điểm phát | Timer được dọn; không phát attempt khi đã quan sát hủy trước dispatch |
| T12 — Tác dụng phụ | Với luồng ghi có idempotency, làm mất phản hồi sau khi dependency đã xử lý | Không tạo thêm kết quả nghiệp vụ ngoài hợp đồng idempotency |
| T13 — Retry ẩn | Bật tracing tại mọi điểm gửi, gây lỗi ở SDK hoặc proxy | Mọi lần gọi bổ sung thuộc phạm vi đều có giấy phép; phát hiện cấu hình gửi ngoài kiểm soát |
| T14 — Giới hạn đồng thời | Nhiều thao tác initial và retry cùng tới ranh giới A gọi B | Không vượt 50 attempt đang chạy |
| T15 — Bỏ qua cách đếm | Đổi header, request ID, key client hoặc tên endpoint tương đương | Không tạo ngân sách mới trái phạm vi; tín dụng không tăng do nhãn do client tự khai |

T01–T04 có thể kiểm thử trực tiếp bộ cấp phép bằng trạng thái và đồng hồ kiểm soát được. Các ca tích hợp phải đối chiếu giấy phép với sự kiện gửi thật, không chỉ số lần một hàm retry được gọi.

Với T05, 120 là cận trên chứ không phải số retry bắt buộc đạt. Nếu tín dụng bị bỏ khi bucket đầy, hoặc deadline, attempt limit và giới hạn đồng thời chặn trước, số thực tế có thể thấp hơn.

T12 là kiểm thử cần bổ sung khi áp dụng chính sách cho thao tác ghi; nó không biến ví dụ đọc trạng thái ở phần trước thành một thao tác ghi.

### 10.2. Lỗi tại các điểm không chắc chắn

Cần có kịch bản gây lỗi ở những khoảng sau:

- Kho đã trừ tín dụng nhưng caller chưa nhận kết quả.
- Caller có giấy phép nhưng bị hủy trước khi gửi.
- Request đã gửi nhưng kết quả chưa về.
- Một sự kiện cấp tín dụng được phát lại sau reconnect.
- Replica cũ vẫn chạy trong khi một phần ngân sách được thu hồi và cấp cho replica khác.
- Cấu hình đổi giữa lúc initial attempt và retry tiếp theo.
- Backoff của nhiều thao tác kết thúc gần như đồng thời sau một đợt lỗi.

Để kết luận đạt, cần ghi phạm vi policy, số replica, trạng thái đầu, lịch sự kiện và nguồn đếm. Nếu cho phép sai số, phải so sánh với cận sai số đã phê duyệt. Cụm “phần lớn retry đã bị chặn” không chứng minh yêu cầu về ngân sách.

Đo riêng độ trễ và tài nguyên khi bật kiểm soát. Một ngân sách đúng về số học nhưng tạo hàng triệu timer chờ hoặc khóa nóng tại kho trạng thái vẫn có thể gây rủi ro availability.

## 11. Logging, metric và xử lý vận hành

Các chỉ số tối thiểu nên phân biệt:

```text
initial_attempts_admitted_total
additional_attempts_dispatched_total{kind=retry|hedge}
retry_budget_grants_total
retry_budget_denied_total
retry_credit_events_total
retry_budget_state_errors_total
retry_stop_total{reason}
attempts_in_flight
scheduled_retry_tasks
```

Đây là ví dụ tên metric. Chỉ dùng nhãn có tập giá trị được kiểm soát như dependency group, operation class và reason code. Không gắn request ID, user ID hoặc tenant ID có số lượng không giới hạn vào mọi nhãn metric.

Dữ liệu chi tiết có thể ghi ở log hoặc trace với chính sách truy cập và lưu giữ phù hợp:

- Request hoặc operation reference nội bộ.
- Dependency, policy ID và phiên bản.
- Loại attempt, số thứ tự và lý do retry.
- Thời gian chờ, deadline còn lại và timeout được áp dụng.
- Quyết định ngân sách và lý do dừng.
- Kết quả attempt, độ trễ và trạng thái hủy.

Không ghi credential, bearer token, OTP hoặc payload nhạy cảm chỉ để chứng minh retry. Một log storm trong sự cố có thể làm cạn chính tài nguyên cần bảo vệ, nên phải chốt sampling, tổng hợp và cận lưu lượng log.

### 11.1. Đọc số liệu đúng phạm vi

Dashboard phải nêu rõ tỷ lệ đang là `R/O` hay `R/(O+R)`, cửa sổ quan sát và phạm vi dependency. Với bucket có burst, so sánh tỷ lệ ngắn hạn trực tiếp với `β` có thể báo sai.

Cận kiểm chứng trong một khoảng cần tính cả số dư đầu khoảng:

```text
R_interval <= credits_at_interval_start + β × O_interval
```

Nếu không biết số dư đầu khoảng, có thể dùng `Bmax` làm cận bảo thủ. Nếu có reset, cấp ngoại lệ hoặc cơ chế hoàn tín dụng, phải tính các nguồn đó theo chính sách tương ứng.

Giấy phép đã cấp có thể nhiều hơn retry thực phát khi caller bị hủy sau lúc tiêu thụ. Cần giữ riêng hai đại lượng để giải thích chênh lệch. Không lấy số retry thành công làm số retry đã tạo tải.

Hủy hedged attempt thua cuộc cũng không chứng minh phía server đã ngừng mọi công việc. Tải quan sát tại dependency và thời gian giữ tài nguyên vẫn cần được đo.

### 11.2. Các tín hiệu cần phản ứng

- Retry tăng cùng timeout và độ trễ dependency: kiểm tra vòng khuếch đại tải.
- Ngân sách thường xuyên cạn: kiểm tra lỗi phụ thuộc, ngưỡng quá thấp, policy sai hoặc retry không hữu ích.
- Retry thành công rất thấp: cân nhắc loại lỗi được phép retry và thời gian chờ.
- Số retry thực phát vượt số giấy phép: điều tra retry ẩn hoặc lỗi ranh giới quan sát.
- Tín dụng tăng khi không có initial attempt đủ điều kiện: điều tra reset, cấp lặp hoặc định danh không ổn định.
- Số task chờ tăng dù số retry phát thấp: kiểm tra backoff queue và cơ chế hủy.

Không tự tăng ngân sách chỉ để giảm cảnh báo hết tín dụng. Cần xem dependency có năng lực xử lý phần tải bổ sung hay không và những thao tác nào đang tạo retry.

Với hàng đợi bất đồng bộ, xử lý lại message cũng cần mô hình tương tự: giới hạn số lần phát lại, tuổi tối đa của công việc, ngân sách chung và cơ chế chuyển sang hàng đợi lỗi khi không thể tiếp tục. Replay thủ công hoặc redelivery không được tự biến mọi công việc cũ thành nguồn tín dụng mới ngoài thiết kế.

## 12. Các lỗi đặc tả thường gặp

| Đặc tả hoặc cách hiểu | Hệ quả | Cách sửa |
|---|---|---|
| “Mỗi request được retry 3 lần” | Không rõ tổng attempt; không có cận cho cả nhóm | Nêu tổng attempt và ngân sách dùng chung |
| “Retry tối đa 10%” | Không rõ mẫu số, cửa sổ và burst | Nêu công thức, đơn vị và trạng thái khởi tạo |
| “Có backoff nên tải đã an toàn” | Retry vẫn có thể rất nhiều hoặc đồng loạt | Kết hợp ngân sách, jitter và cận tài nguyên |
| “Timeout nghĩa là chưa xử lý” | Tạo tác dụng phụ trùng | Xác định trạng thái chưa biết, idempotency và đối soát |
| “Ngân sách mỗi process là ngân sách toàn hệ thống” | Tổng tăng theo replica và restart | Dùng phạm vi thực thi đúng với cam kết |
| “SDK tự retry nên không cần đếm” | Ngân sách ứng dụng không phản ánh tải thật | Đưa mọi điểm gửi bổ sung vào chính sách |
| “Hedging không phải retry nên được miễn” | Tạo đường phát tải bổ sung ngoài cận | Định nghĩa nhóm additional attempts và ngoại lệ có cận |
| “Cứ thất bại thì hoàn tín dụng” | Dependency đã chịu tải nhưng ngân sách không giảm | Chỉ hoàn theo bằng chứng chưa phát, nhiều nhất một lần |
| “Đổi version policy thì tạo bucket đầy” | Reset trở thành nguồn cấp thêm ngoài công thức | Quy định chuyển trạng thái và audit tín dụng bổ sung |
| “Còn tín dụng thì phải retry” | Retry cả khi hết deadline, caller hủy hoặc lỗi vĩnh viễn | Kiểm tra đồng thời mọi điều kiện cần |

## 13. Bài tập áp dụng

Bạn phụ trách một service gửi yêu cầu tạo báo cáo sang một dependency xử lý bất đồng bộ. Dependency đôi khi nhận job thành công nhưng phản hồi bị mất. Hãy viết bản đặc tả gồm:

1. Rủi ro làm tăng tải và rủi ro tạo job trùng; chỉ ra tài nguyên bị ảnh hưởng.
2. Ranh giới initial attempt, retry, redelivery và thao tác đối soát.
3. Phạm vi ngân sách, công thức, trạng thái ban đầu và điều kiện cấp tín dụng.
4. Tổng attempt, deadline, backoff, quy tắc retry và hợp đồng idempotency.
5. Hành vi khi hết ngân sách, mất kho trạng thái, restart hoặc caller hủy.
6. Ít nhất một ca kiểm thử đồng thời, một ca mất phản hồi và một ca reset cấu hình.
7. Chuỗi truy vết từ rủi ro tới yêu cầu, quyết định kiến trúc và bằng chứng kiểm thử.

Tự kiểm tra: một nhóm triển khai độc lập có xác định được **khi nào được phát attempt tiếp theo**, và một nhóm kiểm thử độc lập có chứng minh được **tổng tải bổ sung không vượt cận đã cam kết** hay không? Nếu vẫn phải đoán cách đếm, phạm vi hoặc nguồn tín dụng, yêu cầu chưa đủ cụ thể.
