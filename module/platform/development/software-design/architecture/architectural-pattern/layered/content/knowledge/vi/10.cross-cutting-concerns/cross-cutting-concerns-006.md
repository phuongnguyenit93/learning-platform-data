# Xác định lỗi được thử lại, giới hạn thời gian và tránh gây tác động lặp

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, trong chương **Các mối quan tâm xuyên tầng**. Module hướng tới cách tổ chức phần mềm theo kiến trúc phân tầng, với presentation tiếp nhận yêu cầu, application điều phối ca sử dụng, business/domain bảo vệ quy tắc và data access/infrastructure giao tiếp với hệ thống lưu trữ hoặc dịch vụ bên ngoài. Trọng tâm ở đây là xử lý lỗi tạm thời một cách có kiểm soát: xác định lỗi nào có thể thử lại, đặt giới hạn thời gian và bảo đảm việc thử lại không tạo ra tác động nghiệp vụ trùng lặp.

Mạng có thể chập chờn, dịch vụ phụ thuộc có thể quá tải, database có thể tạm thời từ chối kết nối. Thử lại giúp vượt qua một số lỗi thoáng qua, nhưng mỗi lần thử cũng tiêu tốn thời gian và tài nguyên. Đặc biệt, timeout không chứng minh thao tác chưa xảy ra: server có thể đã commit dữ liệu nhưng phản hồi bị mất trên đường về. Vì vậy, retry chỉ an toàn khi có chính sách lỗi, giới hạn thời gian và cơ chế bảo vệ tính lặp phù hợp.

## 1. Vì sao không thể thử lại mọi lỗi?

Một yêu cầu có thể thất bại vì nhiều nguyên nhân khác nhau:

| Nhóm lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Lỗi đầu vào hoặc quy tắc nghiệp vụ | Thiếu trường, số lượng âm, đơn hàng không hợp lệ | Trả lỗi; sửa dữ liệu hoặc điều kiện trước khi gửi lại |
| Lỗi xác thực/phân quyền | Token hết hạn, người gọi không có quyền | Làm mới thông tin xác thực hoặc xử lý quyền; không retry mù |
| Lỗi tạm thời của hạ tầng | Kết nối bị reset, database tạm quá tải | Có thể retry có giới hạn nếu thao tác an toàn |
| Quá tải hoặc giới hạn tốc độ | HTTP 429, dịch vụ tạm thời không nhận thêm tải | Tôn trọng thời gian chờ, giảm tốc độ và retry nếu còn deadline |
| Lỗi cấu hình hoặc lỗi lập trình | Sai URL, thiếu cấu hình, lỗi null, truy vấn sai | Sửa nguyên nhân; retry thường chỉ lặp lại thất bại |
| Kết quả không xác định | Client timeout sau khi gửi yêu cầu ghi | Kiểm tra trạng thái hoặc retry bằng cơ chế idempotency |

Một lỗi chỉ nên được thử lại khi có cơ sở cho rằng nguyên nhân có thể biến mất sau một khoảng chờ. Ví dụ, connection reset hoặc HTTP 503 có thể là tạm thời. Ngược lại, HTTP 400 do dữ liệu không hợp lệ sẽ không tự biến thành thành công sau vài giây.

Không nên chỉ dựa vào loại exception tổng quát. Cùng một `IOException` có thể biểu thị kết nối bị ngắt tạm thời hoặc một lỗi cấu hình cố định. Chính sách retry cần dựa trên loại lỗi cụ thể, giai đoạn thao tác, trạng thái của hệ thống và khả năng lặp an toàn.

## 2. Phân loại lỗi có thể retry

Trước khi thêm retry, hãy xác định rõ các trường hợp được phép thử lại và trường hợp phải dừng.

### 2.1. Lỗi thường có thể retry

Tùy dịch vụ và ngữ cảnh, các trường hợp sau có thể là lỗi tạm thời:

- Kết nối mạng bị reset hoặc tạm thời không thiết lập được.
- Một số lỗi timeout khi gọi dịch vụ phụ thuộc.
- HTTP 429 khi bị giới hạn tốc độ, nếu có thể chờ theo hướng dẫn.
- HTTP 502, 503 hoặc 504 trong một số hệ thống gateway/service.
- Deadlock hoặc serialization failure của database, nếu toàn bộ transaction có thể chạy lại an toàn.
- Một lỗi tạm thời được dịch vụ phụ thuộc công bố rõ là có thể thử lại.

Đây là danh sách gợi ý, không phải quy tắc áp dụng cho mọi hệ thống. Ví dụ, HTTP 503 có thể là sự cố kéo dài; retry liên tục chỉ làm tăng tải. Một lỗi HTTP 500 có thể do bug cố định và cần điều tra, không mặc định retry.

### 2.2. Lỗi thường không nên retry

Các lỗi sau thường cần dừng và trả kết quả phù hợp:

- Dữ liệu đầu vào sai hoặc vi phạm validation.
- Không đủ quyền truy cập.
- Tài nguyên không tồn tại, trừ khi có quy trình eventual consistency đã được xác định.
- Quy tắc nghiệp vụ từ chối thao tác, ví dụ đơn hàng đã bị hủy hoặc tồn kho không đủ.
- Lỗi lập trình, lỗi cấu hình hoặc lỗi schema không tương thích.
- Một thao tác không idempotent mà kết quả lần trước chưa rõ và không có cơ chế chống lặp.

Không nên retry mọi exception chỉ vì chúng được bọc trong một kiểu exception chung. Cần phân biệt lỗi kỹ thuật có thể hồi phục với lỗi nghiệp vụ và lỗi cần sửa cấu hình.

### 2.3. HTTP method không đủ để quyết định mọi trường hợp

Theo ngữ nghĩa HTTP, GET, HEAD, PUT và DELETE được định nghĩa là các method idempotent; lặp cùng một yêu cầu không làm thay đổi thêm trạng thái mong muốn sau lần đầu. Tuy vậy, implementation vẫn phải tuân thủ ngữ nghĩa đó. Một endpoint GET có side effect ngoài ý muốn hoặc một endpoint PUT cộng dồn dữ liệu thay vì thay thế trạng thái có thể không an toàn khi retry.

POST thường tạo tài nguyên hoặc thực hiện hành động, nên không mặc định an toàn để gửi lại. Nếu client không biết server đã xử lý hay chưa, gửi lại POST có thể tạo hai đơn hàng hoặc hai lần thanh toán. Có thể làm POST an toàn hơn bằng idempotency key và cơ chế lưu kết quả đã xử lý.

## 3. Đặt timeout và deadline

Retry mà không có timeout có thể khiến request chờ vô hạn. Timeout giới hạn thời gian chờ của một thao tác; deadline giới hạn tổng thời gian mà toàn bộ ca sử dụng được phép tiêu tốn.

### 3.1. Các loại timeout

Khi gọi HTTP hoặc truy cập database, cần phân biệt các khoảng thời gian:

- **Connection timeout:** thời gian tối đa để thiết lập kết nối.
- **Read/response timeout:** thời gian chờ dữ liệu phản hồi hoặc lần đọc tiếp theo.
- **Call/request timeout:** giới hạn tổng thời gian cho một lần gọi, nếu client hỗ trợ.
- **Pool acquisition timeout:** thời gian tối đa chờ lấy connection từ pool.
- **Transaction/query timeout:** giới hạn thời gian của giao dịch hoặc truy vấn theo cấu hình hỗ trợ.

Tên và ngữ nghĩa chính xác phụ thuộc thư viện client, driver và framework. Cần đọc cấu hình của công cụ đang dùng thay vì giả định mọi thuộc tính có cùng ý nghĩa.

Timeout nên phản ánh mục tiêu của ca sử dụng và khả năng của dịch vụ phụ thuộc. Đặt timeout quá dài khiến thread, connection và request context bị giữ lâu. Đặt quá ngắn làm tăng lỗi giả khi hệ thống vẫn có thể phản hồi trong điều kiện bình thường.

### 3.2. Deadline tổng cho cả chuỗi gọi

Giả sử API phải trả lời trong tối đa 2 giây. Nếu mỗi lần gọi dịch vụ kho có timeout 2 giây và ứng dụng thử lại ba lần, một request có thể kéo dài vượt xa giới hạn của API. Vì vậy, cần có ngân sách thời gian chung (deadline budget).

Ví dụ một luồng:

```text
Client deadline: 2.0 s
       |
       v
Application: còn 1.8 s
       |
       +--> Inventory call: tối đa 500 ms
       |       retry nếu còn ngân sách
       |
       +--> Pricing call: tối đa 400 ms
       |
       +--> Lưu database: tối đa 500 ms
       |
       v
Trả kết quả trước deadline
```

Đây là con số minh họa. Khi thiết kế thật, cần dành thời gian cho xử lý nội bộ, serialization và gửi phản hồi. Timeout của dependency phải nhỏ hơn hoặc phù hợp với phần ngân sách còn lại, để application còn cơ hội xử lý lỗi và trả kết quả.

Nếu một service gọi tiếp service khác, nên truyền deadline hoặc thời gian còn lại qua context/header theo hợp đồng nội bộ. Không nên để mỗi tầng tự bắt đầu một timeout đầy đủ mới; cách đó có thể làm tổng thời gian vượt xa kỳ vọng của caller.

Dùng đồng hồ đơn điệu như `System.nanoTime()` để đo thời lượng trong tiến trình Java, vì đồng hồ lịch có thể bị điều chỉnh. Không dùng timestamp lịch để tính khoảng thời gian timeout.

## 4. Thiết kế retry có giới hạn

Một chính sách retry cần quy định ít nhất:

- Những lỗi nào được thử lại.
- Số lần thử tối đa, tính cả lần đầu hay chỉ lần lặp.
- Khoảng chờ giữa các lần thử.
- Deadline tổng hoặc thời gian tối đa dành cho retry.
- Điều kiện dừng sớm khi không còn đủ thời gian.
- Cách xử lý khi caller hủy hoặc thread bị interrupt.
- Thao tác có an toàn khi lặp hay không.

### 4.1. Exponential backoff

Nếu thử lại liên tục với khoảng chờ cố định quá ngắn, nhiều client có thể cùng dồn yêu cầu vào một dịch vụ đang quá tải. Exponential backoff tăng khoảng chờ sau mỗi lần thất bại:

\[
d_n = min(d_{max}, d_0 	imes 2^{n-1})
\]

Trong đó `d_0` là khoảng chờ ban đầu, `d_max` là giới hạn tối đa và `n` là số thứ tự lần thử lại.

Ví dụ với khoảng chờ ban đầu 100 ms và giới hạn 1.000 ms, các khoảng chờ cơ sở có thể là 100, 200, 400, 800, 1.000 ms. Số lần thử và các khoảng chờ phải phù hợp deadline của ca sử dụng.

### 4.2. Jitter để tránh đồng bộ retry

Nếu hàng nghìn client cùng thất bại tại một thời điểm và đều retry sau đúng 1 giây, chúng có thể tạo ra một đợt tải mới cùng lúc. Jitter thêm độ ngẫu nhiên vào khoảng chờ để phân tán thời điểm retry.

Một cách đơn giản là chọn ngẫu nhiên khoảng chờ trong một khoảng từ 0 đến giá trị backoff đã tính. Một số thư viện dùng full jitter, equal jitter hoặc decorrelated jitter. Chọn chiến lược nhất quán và đặt giới hạn trên để không vượt deadline.

### 4.3. Số lần thử và tổng thời gian

Không nên đặt số lần retry quá cao chỉ để “tăng khả năng thành công”. Mỗi lần thử tiêu thụ connection, thread, CPU và tải của dependency. Nếu lỗi là quá tải, retry dày có thể làm tình hình tệ hơn.

Một chính sách minh họa:

| Tham số | Giá trị ví dụ |
|---|---:|
| Tổng số lần gọi tối đa, gồm lần đầu | 3 |
| Backoff ban đầu | 100 ms |
| Backoff tối đa | 500 ms |
| Jitter | Có |
| Deadline cho dependency | 1.2 giây |
| Lỗi được retry | Một số lỗi kết nối và 503/504 đã xác định |
| Lỗi dừng ngay | Validation, authorization, lỗi nghiệp vụ |

Không sao chép nguyên các giá trị này cho mọi hệ thống. Cần dựa trên latency thực tế, SLO, timeout của caller và khả năng chịu tải của dependency.

### 4.4. Tôn trọng Retry-After

Khi server trả HTTP 429 hoặc 503, response có thể chứa header `Retry-After` cho biết thời điểm hoặc khoảng thời gian nên chờ trước khi gửi lại. Client nên tôn trọng hướng dẫn này trong giới hạn deadline và chính sách của mình. Không nên retry sớm hơn chỉ vì backoff nội bộ ngắn hơn.

Nếu `Retry-After` vượt quá deadline của request hiện tại, hãy dừng và trả kết quả phù hợp thay vì giữ request chờ quá lâu. Với công việc nền có thể chạy lâu, có thể lên lịch lại thay vì giữ thread chờ.

## 5. Timeout không chứng minh thao tác chưa xảy ra

Đây là điểm quan trọng nhất khi retry thao tác ghi.

Giả sử client gửi yêu cầu tạo đơn hàng. Server nhận yêu cầu, ghi đơn hàng và commit database. Nhưng response bị mất trên mạng. Client hết thời gian chờ và nhận timeout. Từ góc nhìn client, kết quả chưa rõ; từ góc nhìn server, đơn hàng đã được tạo.

Nếu client gửi lại cùng yêu cầu và server tạo đơn mới, một hành động của người dùng tạo ra hai đơn hàng.

Có thể xảy ra ba tình huống:

1. Request chưa tới server: thao tác chưa được thực hiện.
2. Request đã tới nhưng server thất bại trước commit: thao tác có thể chưa hoàn tất.
3. Server đã commit nhưng response bị mất: thao tác đã hoàn tất dù client không nhận được kết quả.

Timeout chỉ nói rằng caller không nhận được kết quả đúng hạn. Nó không cho biết chắc chắn tình huống nào đã xảy ra. Do đó, cần cơ chế idempotency hoặc tra cứu trạng thái trước khi lặp lại một thao tác ghi.

## 6. Idempotency: lặp yêu cầu nhưng không lặp tác động

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng định danh yêu cầu mà vẫn tạo ra cùng một kết quả nghiệp vụ như thực hiện một lần.

Ví dụ, client gửi header:

```http
POST /orders
Idempotency-Key: 4c8e2a1b-...
Content-Type: application/json
```

Server dùng key này để nhận diện lần thực hiện logic. Nếu request cùng key đã hoàn tất, server trả lại kết quả đã lưu thay vì tạo đơn hàng mới.

### 6.1. Lưu key và kết quả một cách nguyên tử

Một bảng lưu idempotency record có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| `scope` | Phạm vi key, ví dụ tenant hoặc người dùng |
| `idempotency_key` | Khóa do client tạo cho một hành động logic |
| `request_hash` | Dấu vân tay payload để phát hiện dùng lại key sai nội dung |
| `status` | Trạng thái đang xử lý hoặc đã hoàn tất |
| `response_data` | Kết quả cần trả lại khi request được gửi lại |
| `created_at`, `expires_at` | Thời điểm tạo và chính sách lưu giữ |

Cần có ràng buộc unique trên tổ hợp scope và key. Nếu hai request cùng key đến đồng thời, database phải giúp chỉ một request chiếm quyền xử lý. Việc ghi idempotency record, tạo đơn hàng và lưu kết quả nên được tổ chức trong một transaction phù hợp để không có record hoàn tất nhưng thiếu dữ liệu nghiệp vụ, hoặc có đơn hàng nhưng không có thông tin nhận diện lần xử lý.

Pseudocode minh họa:

```text
handleCreateOrder(key, request):
    hash = fingerprint(request)

    begin transaction
        record = insert idempotency(scope, key, hash)
                 or load existing record

        if record.request_hash != hash:
            reject key reused with different request

        if record is COMPLETED:
            return stored response

        create order
        store response and mark record COMPLETED
    commit

    return response
```

Đây là luồng khái niệm. Khi triển khai, cần xử lý xung đột unique khi insert đồng thời, trạng thái IN_PROGRESS, transaction rollback và việc đọc record đang được transaction khác tạo. Không nên chỉ dùng thao tác “kiểm tra key rồi mới insert” mà không có ràng buộc nguyên tử, vì hai request có thể cùng kiểm tra thấy key chưa tồn tại.

Nếu cùng key nhưng payload khác, server nên từ chối thay vì âm thầm trả kết quả của request cũ. Key cần được tạo mới cho hành động logic mới; client phải giữ nguyên key khi retry cùng một hành động.

### 6.2. Phạm vi và thời gian lưu key

Idempotency key cần được gắn với phạm vi thích hợp. Hai người dùng khác nhau có thể tạo cùng chuỗi key; do đó thường kết hợp key với tenant, tài khoản hoặc client identity.

Thời gian lưu key phải dài hơn khoảng thời gian mà client hoặc hệ thống có thể retry. Nếu xóa key quá sớm, request cũ được gửi lại có thể tạo tác động lần nữa. Nếu lưu mãi mãi, bảng có thể tăng không giới hạn. Chọn retention theo loại nghiệp vụ, thời gian retry và yêu cầu đối soát.

Với thao tác tài chính hoặc hành động có hậu quả lớn, cần chính sách lưu giữ và tra cứu bền vững hơn so với một thao tác tìm kiếm thông thường.

### 6.3. Idempotency ở client và provider bên ngoài

Khi gọi cổng thanh toán hoặc dịch vụ bên ngoài, nếu provider hỗ trợ idempotency key, hãy truyền cùng một key cho mọi lần retry của cùng một khoản thanh toán. Nếu provider không hỗ trợ, cần một cơ chế đối soát hoặc truy vấn trạng thái trước khi gửi lại; không thể giả định timeout có nghĩa là thanh toán chưa xảy ra.

Idempotency ở API của chính mình không tự động bảo đảm dịch vụ downstream cũng idempotent. Mỗi ranh giới có side effect cần một hợp đồng chống lặp phù hợp.

## 7. Kết hợp retry với transaction

Retry và transaction cần được phối hợp đúng thứ tự. Một sai lầm là đặt vòng lặp retry bên trong transaction dài, khiến connection và lock được giữ trong lúc chờ.

Với lỗi serialization hoặc deadlock của database, thông thường cần rollback transaction thất bại rồi thử lại toàn bộ đơn vị công việc trong một transaction mới. Không nên tiếp tục dùng persistence context hoặc transaction đã bị đánh dấu rollback-only.

Mô hình khái niệm:

```text
Retry boundary
   |
   +--> Begin transaction attempt 1
   |       Read -> validate -> write
   |       Failure -> rollback
   |
   +--> Backoff outside transaction
   |
   +--> Begin transaction attempt 2
           Read -> validate -> write
           Success -> commit
```

Trong Spring, có thể đặt retry ở một bean điều phối bên ngoài và transaction ở một bean xử lý một lần thử, để mỗi lần gọi transaction method đi qua proxy. Hoặc dùng cơ chế retry/transaction đã được tích hợp và kiểm tra thứ tự interceptor. Điều quan trọng là mỗi lần thử lại phải có transaction mới nếu transaction trước đã rollback.

Không phải mọi lỗi database đều nên retry. Chỉ retry các lỗi xung đột/tạm thời đã xác định như deadlock hoặc serialization failure, giới hạn số lần và bảo đảm toàn bộ ca sử dụng có thể chạy lại an toàn. Nếu thao tác đã gọi side effect bên ngoài trước khi lỗi database xảy ra, retry toàn bộ có thể lặp side effect. Hãy đưa side effect sang outbox hoặc cơ chế phù hợp sau commit.

## 8. Đặt retry ở đúng tầng

Retry là một chính sách kỹ thuật xuyên tầng, nhưng nên được đặt gần nơi hiểu rõ lỗi và khả năng lặp của thao tác.

| Vị trí | Khi phù hợp | Điều cần tránh |
|---|---|---|
| HTTP client adapter | Gọi một dependency và biết loại lỗi mạng/HTTP có thể retry | Retry mọi request mà không xét method và idempotency |
| Persistence adapter | Retry một số lỗi database có thể hồi phục theo chính sách | Retry truy vấn/lưu tùy tiện trong transaction đã hỏng |
| Application service | Điều phối retry cho toàn bộ ca sử dụng khi cần chạy lại transaction | Lặp side effect hoặc giữ transaction trong lúc backoff |
| Message consumer | Retry xử lý message khi broker và consumer có chính sách redelivery | Xử lý lặp mà không có deduplication/idempotency |
| Controller | Thường chỉ chuyển lỗi thành response và mã trạng thái | Đặt vòng lặp retry làm kéo dài request và che giấu lỗi |

Không nên đặt retry độc lập ở nhiều tầng mà không phối hợp. Ví dụ HTTP client retry 3 lần, application retry 3 lần và gateway retry 3 lần có thể tạo tối đa 27 lần gọi downstream cho một yêu cầu ban đầu. Đây là retry amplification.

Hãy chọn một nơi sở hữu chính sách retry chính, hoặc tính tổng số lần thử trên toàn chuỗi. Các tầng khác cần truyền lỗi rõ ràng và tuân thủ deadline chung.

## 9. Bulkhead, circuit breaker và giới hạn tải

Retry không phải công cụ duy nhất để xử lý dependency không ổn định.

- **Circuit breaker** tạm ngừng gọi dependency khi tỷ lệ lỗi vượt ngưỡng, sau đó cho phép một số request thử lại để kiểm tra phục hồi.
- **Bulkhead** giới hạn số lời gọi đồng thời hoặc tách pool tài nguyên để một dependency chậm không chiếm hết thread/connection của ứng dụng.
- **Rate limiting** giới hạn tốc độ gửi yêu cầu.
- **Load shedding** từ chối sớm công việc khi hệ thống đã quá tải để bảo vệ phần còn lại.

Các cơ chế này có thể kết hợp với retry, nhưng cần thiết kế thứ tự và ngân sách rõ ràng. Ví dụ, circuit breaker đang mở thì không nên tiếp tục retry cùng dependency; request nên thất bại nhanh hoặc được đưa vào hàng đợi theo chính sách. Bulkhead giúp giới hạn số request đang chờ; timeout giúp giải phóng tài nguyên; retry chỉ nên xảy ra khi còn ngân sách và lỗi có thể hồi phục.

Không nên dùng circuit breaker để che giấu lỗi nghiệp vụ hoặc dùng retry để thay thế việc tăng năng lực của một dependency quá tải kéo dài.

## 10. Quan sát và kiểm thử retry

Retry có thể làm lỗi tạm thời ít xuất hiện với người dùng, nhưng nếu không quan sát thì hệ thống có thể âm thầm tốn nhiều tài nguyên. Nên ghi nhận:

- Số lần retry theo dependency và loại lỗi.
- Tỷ lệ request thành công ngay lần đầu và thành công sau retry.
- Thời gian chờ backoff và tổng latency.
- Số request hết deadline hoặc bị hủy.
- Số key idempotency được phát hiện trùng, đang xử lý hoặc dùng lại với payload khác.
- Tình trạng circuit breaker, bulkhead và pool connection.
- Các lỗi cuối cùng sau khi hết số lần thử.

Log nên có correlation ID, operation ID hoặc idempotency key ở dạng phù hợp với chính sách bảo mật. Không ghi token, thông tin thanh toán hoặc payload nhạy cảm chỉ để debug retry. Metric cần có nhãn giới hạn cardinality; không đưa key duy nhất của từng request thành label metric.

Các kịch bản test nên bao gồm:

1. Lỗi tạm thời ở lần đầu, thành công ở lần sau.
2. Lỗi không retry được thì dừng ngay.
3. Hết số lần thử hoặc deadline thì trả lỗi rõ ràng.
4. Thread bị interrupt thì dừng chờ và giữ trạng thái interrupt.
5. Timeout sau khi server đã commit nhưng response bị mất; retry cùng idempotency key chỉ tạo một tác động.
6. Hai request đồng thời dùng cùng key không tạo hai tài nguyên.
7. Cùng key nhưng payload khác bị từ chối.
8. Transaction thất bại rồi retry dùng transaction mới.
9. Backoff và jitter nằm trong giới hạn đã cấu hình.
10. Retry không vượt quá chính sách tổng của gateway, application và HTTP client.

Với test thời gian, nên tiêm clock/sleeper hoặc dùng cơ chế giả lập thời gian nếu thư viện hỗ trợ để tránh test phải chờ thật lâu. Integration test vẫn cần xác minh ràng buộc unique và transaction trên database phù hợp.

## 11. Checklist trước khi bật retry

Trước khi áp dụng retry cho một thao tác, hãy trả lời:

1. Lỗi cụ thể nào có thể hồi phục? Lỗi nào phải dừng ngay?
2. Một lần gọi có timeout không? Tổng ca sử dụng có deadline không?
3. Số lần thử, backoff, jitter và thời gian tối đa đã được giới hạn chưa?
4. Server có thể đã thực hiện thao tác dù caller timeout không?
5. Thao tác có idempotent không? Nếu không, có idempotency key, deduplication hoặc cơ chế tra cứu trạng thái không?
6. Retry có làm lặp email, thanh toán, message hoặc side effect bên ngoài không?
7. Retry nằm ở một tầng có chủ sở hữu rõ ràng hay bị nhân lên qua nhiều tầng?
8. Với lỗi database, mỗi lần thử có bắt đầu transaction mới không?
9. Có tôn trọng Retry-After, cancellation và deadline của caller không?
10. Metric, log và test có cho biết retry đang cải thiện khả năng phục hồi hay chỉ tăng tải?

Nếu chưa biết server đã thực hiện thao tác ghi hay chưa, đừng gửi lại một yêu cầu không idempotent chỉ dựa vào timeout.

## 12. Ghi nhớ

- Chỉ retry lỗi tạm thời đã phân loại; lỗi đầu vào, phân quyền và quy tắc nghiệp vụ thường phải dừng.
- Timeout giới hạn thời gian chờ nhưng không chứng minh thao tác chưa được thực hiện.
- Dùng timeout cho từng dependency và deadline tổng cho cả ca sử dụng; giữ ngân sách thời gian xuyên suốt các tầng.
- Exponential backoff, jitter, số lần thử tối đa và Retry-After giúp tránh retry dồn dập và quá tải.
- POST hoặc thao tác ghi cần idempotency key, deduplication hoặc tra cứu trạng thái khi kết quả lần trước chưa rõ.
- Lưu idempotency key và kết quả bằng cơ chế nguyên tử; cùng key nhưng payload khác cần được phát hiện.
- Retry lỗi transaction cần rollback lần thử trước và chạy lại toàn bộ đơn vị công việc trong transaction mới.
- Đặt retry ở tầng hiểu rõ lỗi và khả năng lặp; tránh retry amplification qua gateway, application và client.
- Kết hợp retry với timeout, circuit breaker, bulkhead và quan sát phù hợp; kiểm thử cả lỗi tạm thời lẫn tác động lặp.

