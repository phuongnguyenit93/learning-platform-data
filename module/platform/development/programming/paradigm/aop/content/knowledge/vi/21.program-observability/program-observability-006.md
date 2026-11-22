# Lấy mẫu, giới hạn tần suất và giảm khối lượng đầu ra khi quan sát chương trình bằng Aspect (AOP)

## 1. Vì sao cần kiểm soát dữ liệu quan sát?

Một aspect quan sát có thể can thiệp nhiều lượt gọi và tạo log, trace hoặc metric tại các join point đã chọn. Tính tập trung của AOP hữu ích cho mã nguồn, nhưng khiến lượng dữ liệu phát ra tăng nhanh nếu mỗi lần gọi đều ghi chi tiết.

Nhưng “quan sát tất cả, xuất tất cả” thường gây phản tác dụng. Nếu một phương thức được gọi 100.000 lần mỗi giây và mỗi lời gọi phát log 1 KiB, một bản sao ứng dụng có thể tạo xấp xỉ 100 MiB log mỗi giây, **chưa tính** metadata, serialization, đường truyền và bộ thu thập. Khi giám sát tạo thêm áp lực CPU, bộ nhớ, đĩa hoặc mạng, chính cơ chế quan sát có thể làm hệ thống chậm hay mất ổn định.

Ba cơ chế giải quyết các vấn đề khác nhau:

| Cơ chế | Câu hỏi chính | Quyết định tại thời điểm nào? | Ví dụ |
| --- | --- | --- | --- |
| **Lấy mẫu (sampling)** | Sự kiện/truy vết nào được chọn để quan sát chi tiết? | Theo xác suất, khóa ổn định, điều kiện hoặc kết quả thao tác | Giữ khoảng 1% trace thành công |
| **Giới hạn tần suất (rate limiting)** | Được phép phát tối đa bao nhiêu sự kiện trong một khoảng thời gian? | Theo ngân sách/token và thời gian | Không quá 100 log chi tiết/giây cho một nhóm lỗi |
| **Giảm khối lượng đầu ra (output reduction)** | Nếu đã chọn phát, mỗi bản ghi chứa những gì và lớn đến đâu? | Khi xây dựng/chuẩn hóa dữ liệu đầu ra | Chỉ giữ mã lỗi, nhãn thao tác, thời lượng; rút gọn stack trace lặp |

**Sampling không bảo đảm giới hạn tuyệt đối** vì tải đầu vào có thể tăng đột biến. **Rate limiting không bảo đảm mẫu đại diện** vì những sự kiện đến sau có thể bị bỏ có hệ thống. **Truncation không giảm số sự kiện** nếu vẫn phát một dòng log cho mỗi lần gọi. Một Aspect quan sát tốt thường phối hợp cả ba, đồng thời bảo đảm các số đo quan trọng vẫn phản ánh đầy đủ lưu lượng.

Bài này tập trung vào **AOP tổng quát**, từ cơ chế cơ bản đến thiết kế nâng cao. Ví dụ Java 17+ dùng interface proxy tiêu chuẩn như một cách cụ thể để minh họa around advice; các nguyên tắc không phụ thuộc một framework AOP cụ thể.

## 2. Xác định đúng nơi Aspect quan sát

Giả sử có thao tác nghiệp vụ `lookup(key)`. Một advice quanh lời gọi có thể:

1. **Trước khi chạy:** ghi nhận thời điểm bắt đầu bằng `System.nanoTime()`, lấy trace/request context và nhãn nghiệp vụ cho phép.
2. **Gọi phương thức gốc đúng một lần:** giữ nguyên tham số, kiểu trả về và hành vi lỗi; hạn chế sinh telemetry trước khi biết thao tác có thực sự chạy.
3. **Sau khi trả về hoặc ném lỗi:** cập nhật số đếm/độ trễ; quyết định chọn log/trace chi tiết dựa trên sampling, quota và trạng thái.
4. **Cuối cùng:** dọn context, hoàn trả tài nguyên telemetry và không thay đổi kết quả nghiệp vụ.

Trong ví dụ đồng bộ, around advice bao trùm toàn bộ công việc. Nhưng nếu phương thức trả `Future`, `CompletionStage` hoặc một luồng sự kiện, thời điểm advice kết thúc có thể chỉ là **thời điểm trả handle**. Muốn ghi thời gian hoàn tất thật hoặc lỗi bất đồng bộ, phải gắn callback hay chặn đúng ranh giới hoàn tất; không mặc định `finally` quanh lời gọi phản ánh cả vòng đời tác vụ.

Một sơ đồ điều phối hữu ích:

~~~text
                  Invocation / completion
                            |
                   Ghi counter tối thiểu
                            |
                Lấy context và nhãn an toàn
                            |
               Chọn mẫu theo policy / trace
                            |
                    Qua rate limiter?
                       /         \
                     Có          Không
                     |             |
              Giới hạn trường      Ghi nhận số bị bỏ
              và dung lượng        (dạng metric/báo cáo gộp)
                     |
               Phát tới sink/queue
                     |
           Quan sát độ trễ và lỗi của sink
~~~

Thực tế có thể tính quyết định **head sampling** ngay khi bắt đầu để tránh tạo span/tải dữ liệu dư thừa. Với **tail sampling**, phải quan sát hoặc giữ bộ đệm hữu hạn đến khi biết kết quả, rồi mới chọn phát. Sơ đồ chỉ mô tả thứ tự quyết định chung, không yêu cầu mọi phương thức phải tạo sẵn toàn bộ log trước khi lọc.

### 2.1. Phân biệt telemetry không thể đánh đồng

- **Metric tổng hợp:** số yêu cầu, số lỗi, histogram thời lượng, độ dài queue; thông thường cập nhật cho **mọi sự kiện** với nhãn có cardinality kiểm soát.
- **Log chi tiết:** mô tả một biến cố cụ thể; có thể lấy mẫu, giới hạn tốc độ và cắt nội dung, ngoại trừ những nghĩa vụ lưu trữ/kiểm toán bắt buộc.
- **Trace/span:** ghi quan hệ nhân quả và thời gian theo một trace; lựa chọn toàn trace hay từng sự kiện phải bảo toàn context, tránh các đoạn không nối được.
- **Audit/security event:** có thể yêu cầu tính đầy đủ, thứ tự hoặc độ bền khác log chẩn đoán. Không đưa các sự kiện bắt buộc này vào chính sách sampling/drop thông thường mà chưa có hợp đồng cho phép.

Nếu bỏ 99% request log, `requests_total` vẫn phải tăng cho mọi request nếu mục đích metric là đếm tải thực. Nếu chỉ đếm các bản ghi đã phát, số liệu sẽ bị lệch và không còn là tổng số lời gọi.

## 3. Sampling: giảm số lượng nhưng giữ thông tin có ích

### 3.1. Head sampling — quyết định sớm

**Head sampling** quyết định có quan sát chi tiết ở hoặc gần thời điểm bắt đầu thao tác. Một số lựa chọn:

- **Xác suất Bernoulli:** mỗi yêu cầu được chọn độc lập với xác suất `p`, ví dụ `p = 0,01` cho khoảng 1%. Số bản ghi thực tế biến động theo thời gian; 1% không đồng nghĩa đúng một bản ghi trong mỗi 100 yêu cầu.
- **Bộ đếm mỗi N yêu cầu:** chọn một trong mỗi N lượt gọi. Dễ giải thích/kiểm thử nhưng nhạy với thứ tự và những chu kỳ trong lưu lượng, thường không thích hợp để bảo đảm mẫu thống kê đại diện.
- **Hash theo trace ID hoặc operation ID ổn định:** quyết định lặp lại nhất quán cho cùng một trace. Phù hợp khi nhiều thành phần cần dùng chung quyết định; thuật toán/hash, tỷ lệ và quy tắc kế thừa phải thống nhất.
- **Parent-based:** nếu nhận một trace context hợp lệ đã có quyết định sampled, các span con kế thừa chính sách theo quy ước; cần thiết kế rõ trường hợp không có parent hoặc parent chưa sampled.

Với hash ổn định, một ý tưởng là:

~~~text
sample(traceId, p):
    nếu traceId rỗng hoặc không tin cậy: dùng chính sách mặc định
    h = stable_uniform_hash(traceId)
    return h < threshold(p)
~~~

Đây là **giả mã**, không phải API Java. Hash cần phân phối tương đối đều trên miền ID hợp lệ và quy tắc chung ở mọi nơi. Không dùng trực tiếp hash của dữ liệu nhạy cảm như mật khẩu hoặc thông tin nhận dạng; log không nên giữ raw ID nếu không cần.

Sampling theo `traceId` giúp một trace không bị quyết định độc lập tại từng span, tránh trace bị đứt đoạn. Tuy vậy, nó vẫn cần xử lý khi một bên thay đổi xác suất, thiếu context hoặc khi trace đi qua thành phần không hỗ trợ policy.

### 3.2. Tail sampling — chọn theo kết quả

**Tail sampling** cân nhắc sau khi biết kết quả: giữ trace lỗi, thao tác quá chậm, hoặc một số dấu hiệu bất thường; còn trace thành công ngắn thì lấy mẫu thưa. Ưu điểm là giữ được ca hiếm nhưng quan trọng. Đổi lại, nó phải:

- Giữ hoặc chuyển đủ thông tin tạm thời cho đến khi biết trace kết thúc.
- Có giới hạn số trace chờ, kích thước buffer và thời gian giữ; trace dài/mồ côi cần chính sách hết hạn.
- Có cách gom các span cùng trace, đôi khi phải chuyển chúng về cùng điểm ra quyết định.
- Xử lý thiếu span, span đến muộn, worker chết, áp lực bộ nhớ và quota đầu ra.

Một điều cần tránh: lời quảng cáo “giữ toàn bộ lỗi” chỉ đúng nếu hệ thống có đủ dung lượng từ đường thu thập đến sink, và nếu lỗi được nhận diện trước khi sự kiện bị loại. Nếu quota đầu ra đã cạn, chính sách ưu tiên lỗi có thể phải bảo đảm một kênh dự phòng/đường ưu tiên khác, hoặc chấp nhận mất chi tiết và báo rõ tỷ lệ bị bỏ.

### 3.3. Sampling thích nghi và thiên lệch

Có thể điều chỉnh xác suất theo tải, nhóm thao tác hoặc loại sự kiện. Ví dụ, giữ tỷ lệ cao cho giao dịch hiếm và thấp cho health-check. Nhưng phải hiểu hệ quả:

- Mẫu ưu tiên lỗi **không đại diện cho tỷ lệ lỗi thực**. Đừng lấy số log lỗi chia cho tổng log để suy ra error rate.
- Nếu muốn ước lượng tổng từ mẫu Bernoulli độc lập với xác suất biết trước `p`, có thể cân nhắc trọng số `1/p`; chỉ áp dụng khi giả định lấy mẫu phù hợp, không tự suy diễn cho dữ liệu đã bị rate limit theo thứ tự hoặc tail sampling có điều kiện.
- Điều chỉnh tỷ lệ giữa các tenant hoặc operation có thể che khuất nhóm ít lưu lượng nếu một ngân sách chung bị nhóm tải cao chiếm hết.
- Nếu thu mẫu liên tục từ một tập request đặc biệt (ví dụ mọi request lỗi), cần gắn metadata về lý do chọn mẫu để người phân tích không nhầm đó là traffic ngẫu nhiên.

Thay vì xem sampling là công tắc “có/không”, một Aspect nên coi nó là **chính sách chọn dữ liệu có mục đích**, với xác suất/điều kiện được cấu hình, giám sát và kiểm thử.

## 4. Rate limiting: đặt ngân sách phát dữ liệu

Sau khi một sự kiện được chọn, lượng sự kiện thực tế vẫn có thể quá lớn khi tải đột biến. **Rate limiter** kiểm soát tốc độ cấp quyền phát.

### 4.1. Các thuật toán phổ biến

| Cơ chế | Nguyên tắc | Điểm cần chú ý |
| --- | --- | --- |
| **Token bucket** | Một bucket có sức chứa `B`, bổ sung token với tốc độ `r`; mỗi sự kiện tiêu một hoặc nhiều token | Cho phép burst ngắn đến `B`, sau đó giới hạn theo tốc độ bổ sung |
| **Leaky bucket / queue drain** | Đưa vào hàng đợi hữu hạn và rút ra với tốc độ cố định | Làm mượt đầu ra nhưng tăng độ trễ; cần chiến lược khi queue đầy |
| **Fixed window counter** | Đếm số phát trong cửa sổ thời gian cố định | Đơn giản nhưng có thể cho burst dồn ở ranh giới hai cửa sổ |
| **Sliding window** | Tính trên khoảng thời gian trượt, có thể dùng log/tập bucket nhỏ | Mượt hơn nhưng cần thêm trạng thái và đồng bộ |
| **Concurrency cap** | Giới hạn số sự kiện/worker đồng thời đang xử lý | Kiểm soát số việc đang thực thi, **không phải** tốc độ sự kiện/giây |

Với token bucket, để **tốc độ trung bình** khoảng `r` sự kiện/giây và burst tối đa `B`, ta đặt sức chứa `B` và bổ sung token theo thời gian. Nếu bản ghi có kích thước rất khác nhau, limiter theo **byte** hoặc weighted token thường phù hợp hơn limiter mỗi sự kiện một token. Không thể suy ra bandwidth chỉ từ số dòng log.

### 4.2. Phạm vi ngân sách

Một limiter có thể áp dụng cho:

- **Mỗi phương thức/join point:** ngăn một thao tác chatty chiếm toàn bộ quota.
- **Mỗi loại lỗi:** gộp lỗi lặp, bảo vệ những nhóm lỗi quan trọng khác.
- **Mỗi service/instance:** dễ triển khai, nhưng tổng nhiều instance có thể vượt ngân sách hệ thống.
- **Mỗi tenant:** tránh một tenant chiếm tài nguyên; lưu ý số lượng tenant lớn cũng làm phình trạng thái quota.
- **Toàn hệ thống:** cần bộ điều phối phân tán hoặc chia ngân sách; phải xét độ trễ, sự cố mạng, clock và phân vùng.

Nếu mỗi trong 10 instance có quota 100 sự kiện/giây, tổng có thể đến khoảng 1.000 sự kiện/giây. Đó là **giới hạn theo từng instance**, không phải quota toàn hệ thống. Kể cả ở một instance, quota theo bộ đếm thread-local có thể vô tình nhân lên theo số thread.

### 4.3. Chặn, xếp hàng hay bỏ?

Trong đường chạy nghiệp vụ, logging/telemetry thường cần **không chặn** hoặc có chặn trong một ngân sách rất nhỏ. Khi hết quota:

- Bỏ sự kiện chi tiết và tăng counter `telemetry_suppressed_total`.
- Gộp thành báo cáo kiểu “đã bỏ N sự kiện tương tự trong kỳ”.
- Nếu cần giữ thông tin, dùng bounded queue với backpressure hoặc chính sách ưu tiên rõ ràng; không biến queue thành bộ nhớ vô hạn.
- Với sự kiện buộc phải lưu bền, dùng đường ghi có hợp đồng độ bền/khả năng chịu tải riêng và xử lý thất bại theo yêu cầu nghiệp vụ.

Đừng ngầm để một lời gọi nghiệp vụ thông thường đứng chờ hàng giây chỉ vì sink log chậm. Cũng đừng âm thầm coi “ghi log thất bại” là “nghiệp vụ thất bại” khi hợp đồng không cho phép.

### 4.4. Thời gian và đồng thời

Limiter đo khoảng thời gian trong một tiến trình nên dùng **đồng hồ đơn điệu** như `System.nanoTime()`; `System.currentTimeMillis()` là wall clock và có thể nhảy khi chỉnh giờ. Với nhiều thread, quyền tiêu token phải được đồng bộ/atomic để tránh cấp quá mức. Với limiter phân tán, cần một hợp đồng thời gian và điều phối toàn cục phù hợp; dùng `nanoTime()` của hai máy để so trực tiếp là sai.

Khi bổ sung token, xử lý tràn số, thời gian dài bị treo/sleep, clock không tiến và burst sau khi không hoạt động. Một quota “100 sự kiện/giây” cũng phải định nghĩa có cho phép burst bao nhiêu và cách tính trọng lượng bản ghi.

## 5. Giảm khối lượng đầu ra: mỗi sự kiện có ý nghĩa hơn

Ngay cả sau sampling và rate limiting, một bản ghi có thể rất lớn. **Output reduction** thiết kế lại payload để giữ giá trị chẩn đoán với ít byte hơn.

### 5.1. Chỉ ghi những trường cần thiết

Thay vì:

~~~text
DEBUG request=... fullHttpHeaders=... fullBody=... fullObjectGraph=... allStackFrames=...
~~~

Một sự kiện cấu trúc tối giản có thể là:

~~~json
{"event":"lookup.completed","operation":"lookup","outcome":"error","error_type":"TimeoutException","latency_bucket":"100-500ms","trace_id":"<opaque-id>"}
~~~

Ví dụ JSON chỉ minh họa schema; giá trị `trace_id` trong hệ thống thật phải lấy từ context được cho phép, và có chính sách bảo vệ riêng. Trường như access token, session secret, mật khẩu, dữ liệu cá nhân, nội dung request nhạy cảm và đối tượng chứa bí mật **không được đưa vào log** chỉ để rồi cắt ngắn sau đó. Cần **allowlist trường và redaction trước khi phát**, áp dụng tới cả exception message, argument `toString()` và URL/query string.

Thông tin tối thiểu thường gồm mã thao tác, kết quả, loại lỗi đã chuẩn hóa, nhãn môi trường có cardinality thấp và một correlation ID hợp lệ. Chỉ thêm dữ liệu bổ sung khi có trường hợp sử dụng rõ ràng và quyền truy cập phù hợp.

### 5.2. Rút gọn thông tin có kiểm soát

Một số kỹ thuật:

- **Truncation:** giới hạn số code point/byte cho chuỗi người dùng; để ý UTF-8 và surrogate pair, tránh cắt hỏng ký tự Unicode. Giữ thêm cờ `truncated=true` để không nhầm dữ liệu với bản gốc.
- **Stack trace grouping:** gom cùng exception type và nhóm frame liên quan, có số đếm các lần lặp; vẫn giữ nơi thu đủ thông tin cho việc điều tra khi thực sự cần.
- **Aggregation:** đếm theo operation, error code và cửa sổ thời gian; phát một summary thay vì hàng nghìn thông điệp y hệt.
- **Deduplication:** dùng fingerprint đã chuẩn hóa, TTL và số lần xuất hiện; tránh dùng toàn bộ message biến động để tạo vô số nhóm giả.
- **Cardinality reduction:** không gắn user ID, full URL path với ID động hoặc request ID vào nhãn metric. Dùng route template hoặc error code hữu hạn.
- **Batch/compact encoding/compression:** tối ưu truyền và lưu trữ ở collector/sink khi phù hợp; cần kiểm soát queue, latency và khả năng mất dữ liệu.
- **Lazy formatting:** chỉ tạo chuỗi log/serialize object sau khi sampling và quota đã cho phép. Có thể thiết kế `Supplier<String>` hoặc callback formatter để tránh tính toán tốn kém cho bản ghi sẽ bị bỏ.

Không được rút gọn đến mức mất sự phân biệt cần thiết giữa lỗi timeout, lỗi validation và lỗi hệ thống. Nên đánh giá mức độ hữu dụng dựa trên câu hỏi điều tra thực tế, chứ không chỉ phần trăm byte tiết kiệm.

### 5.3. Cẩn thận với output của chương trình và sink

“Giảm khối lượng đầu ra” trong quan sát bằng Aspect có thể bao gồm **log, span attribute, event payload và metric labels**. Nó không đồng nghĩa tự ý cắt **giá trị trả về nghiệp vụ** của phương thức. Around advice phải tôn trọng hợp đồng của API: chỉ thay đổi kết quả nghiệp vụ nếu đó là yêu cầu riêng được định nghĩa rõ.

Nếu telemetry được đưa vào hàng đợi nền, Aspect cần giới hạn kích thước queue và số byte đang chờ. Hệ thống không thể coi dữ liệu đã “xuất thành công” chỉ vì đã thêm nó vào queue; phải phân biệt accepted, exported, retried và dropped.

## 6. Kết hợp chính sách trong một Aspect

Một luồng hợp lý cho phương thức đồng bộ:

1. Thu **metadata tối thiểu**: operation, timestamp đơn điệu, trace context hợp lệ. Không serialize toàn bộ tham số.
2. Thực thi nghiệp vụ theo đúng semantics, đo kết quả và lỗi; tăng các metric cốt lõi cho **mọi invocation**.
3. Xác định event có thuộc nhóm bắt buộc, ưu tiên cao, hay nhóm được phép lấy mẫu.
4. Quyết định sampling theo context và policy. Nếu không chọn, chỉ cập nhật counter “not sampled” phù hợp.
5. Kiểm tra rate limiter ở đúng scope; nếu hết quota, ghi counter “suppressed by quota” mà không tạo payload chi tiết.
6. Với sự kiện được phép phát, chọn các trường an toàn, chuẩn hóa, redact, cắt gọn đúng giới hạn byte; sau đó đưa vào sink một cách có kiểm soát.
7. Ghi nhận lỗi telemetry ở kênh dự phòng phù hợp, không làm thay đổi thành công/thất bại của nghiệp vụ trừ khi hợp đồng yêu cầu.

Thứ tự giữa **lấy mẫu và ghi counter tổng** rất quan trọng: nếu đặt counter trong nhánh “được chọn”, metric sẽ báo số request theo mẫu chứ không còn là tổng thật. Đặt serialization trước sampling/quota cũng triệt tiêu một phần lợi ích tiết kiệm CPU.

### 6.1. Các phép đếm nên tách riêng

Gợi ý dùng các counter với nhãn cardinality thấp:

| Counter | Tăng khi nào? | Mục đích |
| --- | --- | --- |
| `invocations_total` | Mọi lời gọi được chặn | Số lượt chạy thật |
| `invocation_failures_total` | Nghiệp vụ ném lỗi | Tỷ lệ lỗi nghiệp vụ |
| `sample_candidates_total` | Được chính sách sampling chọn | Hiểu chính sách chọn mẫu |
| `telemetry_emitted_total` | Sink xác nhận theo hợp đồng | Số sự kiện thực sự xuất |
| `telemetry_throttled_total` | Đã chọn nhưng hết quota | Mức độ mất chi tiết do limiter |
| `telemetry_export_failures_total` | Gửi sang sink thất bại | Đánh giá độ tin cậy đường quan sát |

Trong một bản demo ghi trực tiếp `System.out`, có thể coi “đã gọi println thành công” là số emitted ở mức minh họa. Trong hệ thống bất đồng bộ, “accepted into queue” chưa phải “exported”; telemetry adapter phải cung cấp semantic chính xác cho từng counter.

## 7. Ví dụ Java 17+: một around advice kết hợp cả ba cơ chế

Chương trình hoàn chỉnh dưới đây dùng **JDK dynamic proxy** để chặn lời gọi qua interface. Aspect:

- Tăng tổng lượt gọi và tổng lỗi cho **mọi** invocation, dù không in log.
- Lấy mẫu có chủ đích **một trong mỗi hai lượt gọi** để đầu ra chạy mẫu dễ kiểm chứng. Chính sách tuần tự này dùng cho demo; trong hệ thống thật, nên cân nhắc xác suất hoặc hash ổn định theo trace ID.
- Dùng token bucket đồng bộ, capacity một sự kiện và refill một token sau mỗi 1.000 tick của **đồng hồ giả lập**. Nhờ clock do demo điều khiển, stdout hoàn toàn xác định.
- Chỉ in request ID đã được làm sạch, kết quả thành công/thất bại; **không in secret payload** và không định dạng các trường không được chọn.
- Phân biệt số “không được chọn mẫu” với số “được chọn nhưng bị giới hạn quota”.

Tạo file `ObservationAspectDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class ObservationAspectDemo {
    interface Service {
        String execute(String requestId, String secretPayload);
    }

    static final class ServiceImpl implements Service {
        @Override
        public String execute(String requestId, String secretPayload) {
            if ("r07".equals(requestId)) {
                throw new IllegalArgumentException("invalid request");
            }
            return "OK";
        }
    }

    static final class TokenBucket {
        private final LongSupplier nowNanos;
        private final long intervalNanos;
        private final int capacity;
        private long lastRefill;
        private int tokens;

        TokenBucket(int capacity, long intervalNanos, LongSupplier nowNanos) {
            if (capacity <= 0 || intervalNanos <= 0) {
                throw new IllegalArgumentException("invalid budget");
            }
            this.capacity = capacity;
            this.tokens = capacity;
            this.intervalNanos = intervalNanos;
            this.nowNanos = nowNanos;
            this.lastRefill = nowNanos.getAsLong();
        }

        synchronized boolean tryAcquire() {
            long now = nowNanos.getAsLong();
            long elapsed = now - lastRefill;
            if (elapsed < 0) {
                throw new IllegalStateException("clock moved backwards");
            }

            long refill = elapsed / intervalNanos;
            if (refill > 0) {
                tokens = (int) Math.min((long) capacity, tokens + refill);
                lastRefill += refill * intervalNanos;
            }

            if (tokens == 0) {
                return false;
            }
            tokens--;
            return true;
        }
    }

    static final class ObservationAspect implements InvocationHandler {
        private final Service target;
        private final TokenBucket limiter;
        private long calls;
        private long errors;
        private long candidates;
        private long emitted;
        private long throttled;

        ObservationAspect(Service target, TokenBucket limiter) {
            this.target = target;
            this.limiter = limiter;
        }

        @Override
        public synchronized Object invoke(
                Object proxy, Method method, Object[] args) throws Throwable {
            long ordinal = ++calls;
            boolean success = false;
            try {
                Object result = method.invoke(target, args);
                success = true;
                return result;
            } catch (InvocationTargetException e) {
                throw e.getCause();
            } finally {
                if (!success) {
                    errors++;
                }

                // Sampling minh hoa: lay moi invocation thu hai.
                if (ordinal % 2 == 0) {
                    candidates++;
                    if (limiter.tryAcquire()) {
                        String id = safeId(String.valueOf(args[0]));
                        System.out.println("observe id=" + id
                                + " outcome=" + (success ? "ok" : "error"));
                        emitted++;
                    } else {
                        throttled++;
                    }
                }
            }
        }

        private static String safeId(String value) {
            String normalized = value.replaceAll("[^A-Za-z0-9_-]", "_");
            return normalized.length() <= 8
                    ? normalized : normalized.substring(0, 8);
        }

        synchronized String summary() {
            return "total=" + calls + " errors=" + errors
                    + " sampled=" + candidates + " emitted=" + emitted
                    + " throttled=" + throttled;
        }
    }

    public static void main(String[] args) {
        AtomicLong demoClock = new AtomicLong(0);
        TokenBucket bucket = new TokenBucket(1, 1_000, demoClock::get);
        ObservationAspect aspect =
                new ObservationAspect(new ServiceImpl(), bucket);

        Service service = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                aspect);

        for (int i = 1; i <= 8; i++) {
            if (i == 5) {
                demoClock.set(1_000); // Refill truoc invocation thu nam.
            }
            String id = String.format("r%02d", i);
            try {
                service.execute(id, "PRIVATE-SECRET");
            } catch (IllegalArgumentException expected) {
                // Nghiep vu co mot loi co chu y o invocation r07.
            }
        }
        System.out.println(aspect.summary());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObservationAspectDemo.java
java ObservationAspectDemo
~~~

**Stdout chính xác:**

~~~text
observe id=r02 outcome=ok
observe id=r06 outcome=ok
total=8 errors=1 sampled=4 emitted=2 throttled=2
~~~

Giải thích theo đúng thứ tự thực thi:

| Lời gọi | Lấy mẫu (mỗi 2 lượt) | Còn token? | Kết quả |
| --- | --- | --- | --- |
| r01 | Không | Không cần kiểm tra | Không có log |
| r02 | Có | Có (token đầu tiên) | Phát log r02 |
| r03 | Không | Không cần kiểm tra | Không có log |
| r04 | Có | Không | Tăng throttled |
| r05 | Không | Không cần kiểm tra; clock tăng lên 1.000 | Không có log |
| r06 | Có | Có (token mới) | Phát log r06 |
| r07 | Không | Không cần kiểm tra | Lỗi nghiệp vụ; vẫn tăng errors |
| r08 | Có | Không | Tăng throttled |

Đồng hồ giả lập dùng đơn vị nanosecond **nhằm kiểm thử thuật toán**, không đại diện cho tải thực tế. Khi triển khai, truyền `System::nanoTime` và thiết kế xử lý số học/thời gian dài, độ trễ và burst phù hợp. Trong ví dụ, `synchronized` đơn giản hóa đồng thời để dễ đọc; một Aspect production cần xác định scope và tránh khóa toàn bộ lời gọi nghiệp vụ bằng monitor của advice như mã demo. Có thể tách phần lấy số thứ tự, counter và limiter sang `AtomicLong`/`LongAdder` cùng bucket thread-safe, chỉ khóa trạng thái limiter nếu cần.

Điểm cần quan sát là **r07 bị lỗi nhưng không được log chi tiết vì không được lấy mẫu; `errors=1` vẫn đúng**. Điều này minh họa khác biệt giữa số đo tổng và số log. Nếu lỗi luôn cần được ghi chi tiết, hãy thiết kế thêm policy ưu tiên lỗi với quota/kênh dự phòng thay vì chỉ tăng xác suất chung.

Ví dụ cũng cho thấy **output reduction bằng allowlist**: không hề log `secretPayload`; request ID được chuẩn hóa và giới hạn tám ký tự. Trong hệ thống thật, request ID có thể là dữ liệu nhạy cảm theo chính sách dữ liệu; nên dùng định danh tương quan được cấp phép thay vì nhận bất cứ chuỗi nào từ client rồi đưa vào log.

## 8. Thứ tự advice và khả năng bị quan sát trùng

Một hệ thống có thể dùng nhiều Aspect: một Aspect đo thời gian, một Aspect truy vết, một Aspect log lỗi. Thứ tự áp dụng advice ảnh hưởng đến số lần đo:

~~~text
Aspect quan sat tong
  -> Aspect retry
      -> Nghiep vu (co the chay 3 lan)
~~~

Nếu Aspect tổng nằm ngoài retry, nó ghi **một operation logic**; Aspect nằm trong retry có thể ghi **ba lần thử**. Không có cách đếm nào mặc nhiên đúng: phải đặt tên metric rõ `operations_total` và `attempts_total`. Không nên để sampling của outer Aspect vô tình ngăn ghi metrics ở inner Aspect nếu cần thống kê từng attempt.

Tương tự, một lời gọi chạy qua hai interception boundary có thể tạo hai span/log cho cùng event. Dùng operation ID, context đã gắn dấu hoặc thiết kế điểm chặn nhất quán để tránh đếm trùng. Khi dùng proxy, việc chặn phương thức trên interface phụ thuộc lời gọi đi qua proxy; lời gọi nội bộ trực tiếp không nhất thiết bị chặn. Cơ chế weaving khác có tập join point khác; cần xác định rõ nơi advice thực sự chạy.

Sampling head nên thường được xác định ở cấp **trace/operation**, sau đó truyền quyết định qua các nhánh. Nếu mỗi Aspect ở mỗi tầng tung đồng xu độc lập, một trace có thể mất các span quan trọng, trong khi số event phát vẫn nhiều bất ngờ.

## 9. Quan sát bất đồng bộ, context và callback

Khi phương thức trả `CompletionStage<T>`, một around advice nhìn thấy **stage được trả về**, không tự động thấy hoàn tất thực tế. Nếu muốn quan sát terminal outcome, có thể đăng ký callback:

~~~java
// Doan minh hoa trong advice; stage co kieu CompletionStage<T>.
CompletionStage<T> observed = stage.whenComplete((value, error) -> {
    // Tang counters tong cho terminal outcome.
    // Sau do ap sampling, limiter va xuat metadata an toan.
});
return observed;
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Chú ý:

- `whenComplete` có thể chạy trên thread hoàn tất stage, không có bảo đảm mặc định chạy trên thread gọi. Nếu callback làm serialize/IO lâu hoặc có limiter chặn, nó có thể kéo chậm cả pipeline.
- Callback không nhất thiết giữ `ThreadLocal` từ lúc gọi. Truyền context/sampling decision tường minh qua stage hoặc context propagation được thiết kế rõ.
- Nếu `whenComplete` ném exception, nó có thể ảnh hưởng stage được trả về. Cần bắt lỗi không quan trọng của telemetry và giữ nguyên hợp đồng kết quả, hoặc dùng một kênh observer độc lập theo thiết kế.
- Một stage có thể bị timeout/hủy ở mức handle trong khi worker còn chạy; phân biệt **logical completion** với **physical completion** trước khi tính độ trễ tác vụ thực hoặc giải phóng resource.
- Nếu tạo thêm callback chỉ để log, tránh giữ payload lớn trong closure hoặc làm tăng thời gian sống của dữ liệu nhạy cảm.
- Tại nhánh streaming, số item và số request là hai đơn vị quan sát khác nhau; sampling theo subscription/request hoặc từng item cần hợp đồng rõ. Không tạo một log cho mỗi item theo mặc định khi lưu lượng cực lớn.

Một thiết kế an toàn thường ghi counter tổng thật sớm hoặc tại mốc hoàn tất phù hợp, còn việc chọn/sắp xếp/publish log được chuyển sang adapter/queue có tài nguyên và quota độc lập. Đảm bảo trình xử lý async khi kết thúc không phát hai lần terminal event chỉ vì có cả callback success và callback timeout.

## 10. Bảo mật, độ tin cậy và tác động đến nghiệp vụ

### 10.1. Không rò dữ liệu qua telemetry

Aspect quan sát có thể truy cập nhiều tham số hơn log thủ công trong nghiệp vụ, nên dễ vô tình in dữ liệu nhạy cảm. Không dùng `Arrays.toString(args)`, phản chiếu toàn bộ field hoặc serialize object graph theo mặc định. Thực hiện theo thứ tự: **allowlist trường → chuẩn hóa/redact → giới hạn kích thước → phát**. Với exception, chỉ phát loại lỗi hoặc mã lỗi phù hợp; message có thể chứa secret, SQL, URL hay nội dung request.

Một hash của thông tin cá nhân không tự động vô danh nếu miền giá trị nhỏ hoặc dễ dò. Ưu tiên correlation ID ngẫu nhiên được cấp hợp lệ, và có chính sách retention/phân quyền cho log.

### 10.2. Không làm telemetry trở thành điểm nghẽn

Ở hot path, việc tạo stack trace, format chuỗi, lấy thời gian lặp lại, ghi file đồng bộ hoặc gọi network có thể đắt hơn nghiệp vụ. Khi sink thất bại, một Aspect quan sát thông thường nên ưu tiên giữ semantics nghiệp vụ, báo lỗi qua metric và bộ lọc circuit breaker hoặc cơ chế queue hữu hạn.

Không dùng `catch (Throwable)` một cách tùy tiện quanh logic nghiệp vụ rồi bỏ lỗi, cũng không nuốt `InterruptedException` của tác vụ. Nếu chỉ cần bắt lỗi ở đoạn telemetry tự quản lý, hãy bao phạm vi try/catch hẹp quanh emitter và định nghĩa lỗi nào được phép bỏ.

### 10.3. Trường hợp khẩn cấp và ưu tiên dữ liệu

Khi quá tải, cần phân cấp ưu tiên: lỗi hệ thống hiếm, cảnh báo mất dữ liệu, sự kiện bảo mật bắt buộc và log thông thường có giá trị khác nhau. Có thể dành quota riêng cho nhóm ưu tiên cao, giữ những counter cốt lõi và giảm log debug theo tải. Nhưng nếu một chính sách đòi hỏi **lưu mọi sự kiện kiểm toán**, không được dùng sampling/drop mà phải dự trù đường lưu bền và xử lý tắc nghẽn theo hợp đồng.

Nếu báo cáo “đã loại bỏ 12.000 bản ghi”, cần nói rõ **vì lấy mẫu**, **vì hết quota**, **vì queue đầy** hay **vì sink xuất thất bại**. Những nguyên nhân này có giải pháp khác nhau và không nên cộng bừa thành một chỉ số không giải thích được.

## 11. Thiết kế policy thực tế

Một tài liệu policy cho Aspect nên quy định ít nhất:

| Thành phần | Điều cần quyết định | Ví dụ minh họa |
| --- | --- | --- |
| Join point | Lời gọi logic hay từng attempt? Đồng bộ hay bất đồng bộ? | Bao quanh API truy vấn, đo terminal completion |
| Dữ liệu cốt lõi | Counter/histogram nào không lấy mẫu? | requests_total, failures_total, latency histogram |
| Sampling | Head/tail, xác suất, trace key, ngoại lệ theo kết quả | 1% trace bình thường; ưu tiên lỗi |
| Rate limiter | Scope, tốc độ, burst, trọng lượng bản ghi | 100 events/s, burst 200 cho mỗi instance |
| Reduction | Allowlist, schema, byte cap, redaction, fingerprints | <=2 KiB/event, bỏ body, gộp stack lặp |
| Overflow | Bỏ, gộp, queue hữu hạn hay kênh ưu tiên? | Đếm suppressed, gộp theo mỗi cửa sổ |
| Reliability | Khi emitter thất bại thì nghiệp vụ ra sao? | Ghi nhận export failure; không đổi kết quả |
| Governance | Quyền xem, lưu giữ, xóa và kiểm tra rò rỉ | Hạn lưu trữ và access theo loại dữ liệu |

Các con số trên **chỉ minh họa**, cần hiệu chỉnh từ tải, yêu cầu chẩn đoán, giới hạn sink và đặc tính thời gian của hệ thống cụ thể.

### 11.1. Tính ngân sách đầu ra sơ bộ

Giả sử một instance nhận 50.000 request/giây; một log chi tiết trung bình 1 KiB:

- Ghi mọi request: khoảng 50.000 KiB/giây, chưa tính overhead.
- Head sampling 1%: **kỳ vọng** khoảng 500 log/giây, tức 500 KiB/giây, nhưng số thực tế có biến động.
- Nếu limiter tiếp tục chỉ cho tối đa trung bình 100 log/giây (sau burst), đầu ra dài hạn khoảng 100 KiB/giây với giả định kích thước log giữ 1 KiB.
- Nếu rút payload trung bình xuống 300 byte, đầu ra dài hạn khoảng 30.000 byte/giây, chưa tính overhead, bất kỳ burst nào và queue đang tích lại.

Đây là ước lượng **dung lượng log chi tiết**, không phải tổng chi phí telemetry: counters, trace context, buffer, mạng, CPU serialization và metadata vẫn tiêu tốn tài nguyên. Cũng không thể dùng các số trên để kết luận chất lượng quan sát vẫn đủ: phải đo khả năng tìm lỗi sau khi giảm dữ liệu.

### 11.2. Chọn thứ tự ưu tiên phù hợp

Có thể chia dữ liệu thành một tầng **định lượng đầy đủ** (counter và histogram cardinality thấp) và một tầng **chẩn đoán chi tiết chọn lọc** (log/trace). Các sự kiện lỗi hiếm hoặc cảnh báo bắt buộc có thể đi qua kênh riêng với quota độc lập. Một sampler toàn cục cộng một limiter toàn cục rất dễ khiến một nhóm có tải lớn chiếm hết quyền phát của những nhóm nhỏ nhưng quan trọng.

Nếu đổi chính sách lúc chạy, phải quan sát hiệu lực và tỷ lệ mới. Việc đổi `p` từ 1% thành 0,1% làm lượng log giảm nhưng cũng làm tần suất thấy lỗi hiếm giảm khoảng 10 lần nếu lỗi cũng được lấy mẫu độc lập, cho nên cần đánh giá trên dữ liệu thực.

## 12. Kiểm thử và xác minh Aspect quan sát

Các phép kiểm thử cần tập trung vào **hành vi có thể chứng minh**, không chỉ thấy một số dòng log xuất hiện:

1. **Correctness của nghiệp vụ:** khi sampling từ chối hoặc limiter hết quota, kết quả/exception từ phương thức gốc phải giữ nguyên; phương thức gốc được gọi đúng một lần.
2. **Counter tổng:** gọi N lần, trong đó M lần lỗi; `invocations_total = N` và `failures_total = M` dù mọi log đều bị bỏ.
3. **Sampling xác định:** với fake sampler, kiểm tra các invocation nào được chọn; với hash theo trace ID, cùng ID phải cho quyết định nhất quán.
4. **Quota:** dùng clock giả để kiểm tra hết token, refill, burst, biên cửa sổ, clock bất thường và sự kiện trọng lượng lớn.
5. **Concurrency:** nhiều thread xin token đồng thời không vượt quota; counters thread-safe; không deadlock giữa advice với emitter/queue.
6. **Reduction & privacy:** secret không xuất hiện trong output kể cả lỗi, object có `toString()` nguy hiểm, dữ liệu Unicode dài, newline injection hoặc exception message nhạy cảm.
7. **Async:** phân biệt thời điểm trả stage và terminal completion; đo đúng một lần khi success/error/cancel/timeout; callback telemetry không làm hỏng future nghiệp vụ.
8. **Overload & failure:** queue đầy, exporter chậm, collector từ chối, shutdown; kiểm tra số suppressed/export failure và giới hạn bộ nhớ.
9. **Chất lượng phân tích:** với các ca lỗi hiếm, xác minh policy vẫn để lại bằng chứng đủ điều tra và metric không bị bias bởi sampling.
10. **Phạm vi interception:** nested calls, retry và self-call không tạo telemetry trùng/thiếu ngoài ý muốn.

Một bài kiểm tra tốt dùng fake clock, fake sink, sampler có kết quả kiểm soát được và bộ đếm độc lập. Đừng chỉ dựa trên `Thread.sleep` rồi so thứ tự log vì kết quả dễ dao động theo lịch chạy.

## 13. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| In toàn bộ arguments và return values bằng reflection | Rò dữ liệu, chuỗi log rất lớn | Dùng allowlist và schema an toàn; lazy serialization |
| Sampling xong mới tăng requests_total | Metric tổng bị thiếu | Tách counter tổng khỏi nhánh log chi tiết |
| Mỗi span tự quyết định sample độc lập | Trace đứt đoạn, khó ghép | Truyền và kế thừa sampling context ở cấp trace |
| Dùng fixed window rồi cho rằng không bao giờ có burst | Có thể dồn burst tại ranh giới | Chọn token bucket/sliding window, khai báo burst |
| Một limiter cho mọi loại sự kiện | Event bình thường lấn át lỗi hiếm | Quota theo mức ưu tiên/nhóm có giới hạn |
| Ghi log đồng bộ trong monitor của advice | Tăng tail latency, nghẽn thread | Chặn tối thiểu, queue hữu hạn, emitter độc lập |
| Coi đã enqueue là đã export | Báo sai độ tin cậy | Phân biệt accepted, exported, dropped |
| Cắt chuỗi theo byte tùy tiện | Hỏng UTF-8, mất ngữ nghĩa | Cắt đúng ranh giới ký tự; gắn cờ truncated |
| Bỏ lỗi telemetry mà không đo đếm | Mù quan sát ngay khi quá tải | Counter/signal dự phòng, giám sát loss |
| Coi sampling “lấy 1%” là quota cứng | Log vẫn bùng nổ khi traffic tăng | Kết hợp limiter theo tốc độ/byte |
| Tự ý cắt kết quả trả về của nghiệp vụ | Thay đổi hợp đồng API | Giảm **telemetry output**, giữ nguyên business result |
| Đếm cả retry là request mới mà không ghi rõ | Error rate/success rate sai nghĩa | Tách operation và attempt với tên metric khác nhau |

Ba cơ chế có quan hệ bổ sung: **sampling quyết định giữ sự kiện nào**, **rate limiting kiểm soát tốc độ hoặc ngân sách phát**, còn **output reduction tối thiểu hóa chi phí mỗi sự kiện**. Khi cài bằng Aspect, thiết kế tốt nhất đồng thời giữ đúng semantics nghiệp vụ, bảo đảm dữ liệu quan trọng không mất âm thầm, và giảm chi phí quan sát đến mức có thể kiểm chứng.
