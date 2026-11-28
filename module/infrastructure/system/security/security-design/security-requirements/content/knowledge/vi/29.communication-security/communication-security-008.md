# Webhook signature

## 1. Chữ ký webhook bảo vệ điều gì?

Trong chương **Communication security**, webhook signature là cơ chế giúp bên nhận kiểm tra một thông báo webhook có được tạo bởi chủ thể giữ khóa phù hợp và các thành phần được bảo vệ có còn nguyên vẹn hay không.

Webhook thường là một HTTP request do hệ thống khác chủ động gửi khi có sự kiện, chẳng hạn tài liệu hoàn tất, đơn đổi trạng thái hoặc tác vụ xử lý xong. Endpoint nhận có thể phải mở ra ngoài, trong khi một request giả có thể khiến ứng dụng thay đổi dữ liệu.

Một yêu cầu như “webhook phải có chữ ký” chưa đủ. Cần xác định:

- Những byte và trường nào được bảo vệ.
- Khóa thuộc bên gửi nào, endpoint nào và môi trường nào.
- Cách xử lý timestamp, phiên bản thuật toán và header.
- Cách chặn phát lại mà vẫn nhận được retry hợp lệ.
- Khi nào được trả thành công và cách ngăn tác dụng phụ trùng.
- Bằng chứng nào nối request nhận được với quyết định nghiệp vụ.

Mục tiêu của bài là chuyển rủi ro giao tiếp thành chuỗi yêu cầu:

**Nguồn sự kiện → phạm vi khóa → dữ liệu được bảo vệ → xác minh → chống phát lại → xử lý nghiệp vụ và audit.**

Các tên header, định dạng thông điệp, ngưỡng và thời hạn trong bài là **profile minh họa cho hệ thống giả định**, không phải giao thức dùng chung của mọi nhà cung cấp. Khi tích hợp một hệ thống thực tế, phải thực hiện đúng hợp đồng ký và giao hàng của hệ thống đó.

## 2. Phân biệt tính toàn vẹn, nguồn gửi và các kiểm soát khác

### 2.1. HMAC và chữ ký bất đối xứng

Trong nhiều tích hợp, “signature” là mã xác thực HMAC tính từ một secret dùng chung. Bên giữ secret có thể tạo và kiểm tra mã này.

Với chữ ký bất đối xứng, bên gửi dùng khóa riêng và bên nhận kiểm tra bằng khóa công khai đã được xác lập tin cậy. Cơ chế phân phối khóa, lựa chọn thuật toán và luân chuyển phải được đặc tả tương ứng.

Hai mô hình không có cùng thuộc tính:

| Thuộc tính | HMAC | Chữ ký bất đối xứng |
|---|---|---|
| Bí mật dùng để tạo thông điệp | Secret dùng chung | Khóa riêng của bên ký |
| Dữ liệu để kiểm tra | Cũng cần secret | Khóa công khai tin cậy |
| Bên nhận có thể tạo mã hợp lệ không? | Có, nếu giữ cùng secret | Không chỉ từ khóa công khai |
| Vấn đề cần quản lý | Phạm vi secret, rò rỉ và phân phối | Nguồn khóa công khai, ánh xạ key ID và vòng đời khóa |

Không dùng HMAC như bằng chứng phân biệt tuyệt đối bên nào trong hai bên giữ secret đã tạo thông điệp. Đồng thời, không tự thiết kế một phép ghép hash thay thế cho HMAC hoặc một thuật toán chữ ký đã được chọn.

### 2.2. Chữ ký không mã hóa nội dung

Một payload có chữ ký vẫn có thể đọc được nếu không có kênh bảo mật. Webhook cần HTTPS với kiểm tra đúng danh tính server và chính sách TLS phù hợp để bảo vệ đường truyền.

HTTPS không thay thế xác thực thông điệp theo hợp đồng webhook. Ngược lại, signature không thay thế xác thực server, phân quyền endpoint hoặc bảo vệ dữ liệu trong log.

### 2.3. Signature không chứng minh nghiệp vụ được phép

Một sự kiện được ký hợp lệ chỉ chứng minh theo mô hình khóa và dữ liệu đã ký. Bên nhận vẫn cần kiểm tra:

- Loại sự kiện có được xử lý không.
- Nguồn gửi có quyền thông báo cho tenant và đối tượng này không.
- Dữ liệu có hợp lệ và phù hợp trạng thái hiện tại không.
- Sự kiện đã xử lý, đến muộn hoặc trái thứ tự hay chưa.

Secret của một đối tác không được biến thành quyền cập nhật tùy ý toàn bộ tài nguyên.

## 3. Mô hình đe dọa và hợp đồng thông điệp

| Rủi ro | Tác động | Hướng đặc tả |
|---|---|---|
| Request giả từ Internet | Tạo thay đổi nghiệp vụ trái phép | Xác minh thông điệp bằng khóa đúng phạm vi |
| Sửa payload hoặc trường quyết định | Thay đối tượng, số lượng hoặc trạng thái | Xác định đầy đủ dữ liệu được bảo vệ |
| Phát lại request hợp lệ | Tạo tác dụng phụ nhiều lần | Timestamp được bảo vệ và deduplication bền vững |
| Đổi endpoint hoặc tenant | Dùng thông điệp hợp lệ ở ngữ cảnh khác | Ràng buộc audience và phạm vi khóa |
| Retry sau mất response | Xử lý lại một sự kiện đã commit | Event identity ổn định, inbox và idempotency |
| Dùng key ID hoặc thuật toán tùy ý | Chọn khóa hoặc chế độ không được phép | Allowlist profile, lookup tin cậy, không fallback |
| Parser hoặc proxy làm đổi byte | Từ chối nhầm hoặc kiểm tra sai nội dung | Bảo toàn byte và thống nhất quy tắc encoding |
| Secret bị lộ | Tạo thông điệp có mã xác thực hợp lệ | Phân tách secret, thu hồi, luân chuyển và đối soát |

Hợp đồng phải định nghĩa riêng **sự kiện logic** và **lần giao hàng**. Một sự kiện có thể được giao nhiều lần, mỗi lần có timestamp và signature mới nhưng cùng event ID và cùng nội dung sự kiện.

Không dùng request ID của proxy làm event ID nếu mỗi retry lại có request ID khác. Ngược lại, không lấy một field do request chưa xác minh tự khai làm căn cứ cập nhật nghiệp vụ trước khi kiểm tra.

## 4. Profile HMAC minh họa và dữ liệu được bảo vệ

### 4.1. Các thành phần

Ví dụ endpoint chỉ nhận `POST` với payload JSON và không dùng content encoding nén. Mỗi cấu hình endpoint xác định sẵn producer và `endpoint_id` từ nguồn tin cậy.

Bên gửi có thể dùng các header:

```http
Webhook-Version: v1
Webhook-Key-Id: key_prod_a
Webhook-Timestamp: <unix_timestamp_seconds>
Webhook-Event-Id: evt_001
Webhook-Signature: <64_lowercase_hex_characters>
Content-Type: application/json
```

Các giá trị trong dấu `<...>` là chỗ giữ chỗ, không phải chữ ký hoặc timestamp hợp lệ để triển khai.

Profile quy định:

- `endpoint_id`, `key_id` và `event_id` là chuỗi ASCII có độ dài và tập ký tự hữu hạn, không chứa ký tự xuống dòng.
- Timestamp là số nguyên giây Unix ở dạng thập phân chuẩn hóa, không có dấu hoặc khoảng trắng và không có số 0 dư ở đầu.
- Mỗi header bảo mật chỉ được xuất hiện một lần; không ghép các giá trị mơ hồ.
- Phiên bản `v1` xác định duy nhất HMAC-SHA-256 và quy tắc biểu diễn.
- Signature là 32 byte được biểu diễn thành đúng 64 ký tự hex chữ thường.
- Secret là dữ liệu ngẫu nhiên đủ độ mạnh được cấp qua kênh quản lý bí mật; trong ví dụ dùng 32 byte ngẫu nhiên mật mã.

Server không cho request chọn một thuật toán khác ngoài profile. Key ID chỉ dùng để tìm khóa đã được cấu hình trong đúng phạm vi, không phải địa chỉ để tải khóa tùy ý.

### 4.2. Chuỗi byte dùng để tính HMAC

Ký hiệu `LF` là byte xuống dòng và `||` là phép nối byte:

```text
signed_bytes =
    ASCII("whsig-v1") || LF ||
    ASCII(endpoint_id) || LF ||
    ASCII(key_id) || LF ||
    ASCII(timestamp) || LF ||
    ASCII(event_id) || LF ||
    raw_body

tag = HMAC-SHA-256(secret, signed_bytes)
signature = lowercase_hex(tag)
```

Các trường trước body bị giới hạn để không chứa delimiter. Body là phần cuối có độ dài được xác định bởi HTTP request nên không cần suy ranh giới từ một nội dung JSON đã parse.

Đây là profile minh họa có quy tắc riêng. Không áp dụng công thức này thay cho công thức của một đối tác dùng giao thức khác.

### 4.3. Raw body có nghĩa chính xác là gì?

Trong profile này, `raw_body` là byte payload do HTTP server cung cấp sau khi xử lý framing truyền tải, trước khi parse JSON hoặc chuẩn hóa nội dung. Không ký ranh giới chunk của HTTP.

Vì profile không nhận content encoding nén, không có bước giải nén làm thay đổi byte trước xác minh. Nếu một tích hợp hỗ trợ encoding khác, hợp đồng phải chỉ rõ phía nào ký biểu diễn nào.

Các biến đổi như đổi khoảng trắng, đổi thứ tự field JSON, đổi newline, decode rồi encode lại Unicode có thể thay đổi byte và làm HMAC khác. Không parse JSON rồi serialize lại để đoán byte mà bên gửi đã ký.

Middleware hoặc proxy không được làm thay đổi biểu diễn được bảo vệ mà không có thiết kế tương ứng. Cần kiểm thử bằng byte thực tế qua toàn bộ đường truyền.

### 4.4. Ràng buộc với ngữ cảnh

`endpoint_id` được bên nhận lấy từ cấu hình route có thẩm quyền, không tin một audience do caller tự khai. Nhờ vậy thông điệp của một endpoint không tự dùng được ở endpoint khác có cùng cấu trúc.

Khóa cũng cần được ràng buộc producer, môi trường và endpoint theo policy. Không dùng chung một secret giữa mọi tenant và mọi môi trường chỉ để giảm số lượng cấu hình.

Với profile JSON cố định, Content-Type và method ngoài hợp đồng bị từ chối thay vì được dùng để chọn parser khác. Những tham số có thể thay đổi nghiệp vụ phải nằm trong dữ liệu đã bảo vệ hoặc được ràng buộc an toàn bằng hợp đồng, không được thêm ở bước thực thi từ một header chưa được ký.

## 5. Quy trình xác minh phía nhận

### 5.1. Từ tiếp nhận tới quyết định

Một pipeline có thể gồm:

1. Kiểm tra route, method, Content-Type, encoding và giới hạn header.
2. Đọc body theo streaming có cận, giữ nguyên byte cần xác minh.
3. Kiểm tra cú pháp header, phiên bản và định dạng signature.
4. Tìm khóa trong cấu hình tin cậy của đúng producer và endpoint.
5. Tạo lại `signed_bytes` theo đúng profile.
6. So sánh tag bằng hàm kiểm tra thời gian hằng phù hợp của thư viện mật mã.
7. Kiểm tra cửa sổ timestamp bằng đồng hồ có thẩm quyền.
8. Parse và kiểm tra schema, event ID, loại sự kiện và phạm vi nghiệp vụ.
9. Ghi nhận sự kiện theo quy tắc chống trùng trước khi công nhận đã nhận bền vững.

Có thể loại request sớm vì cú pháp, kích thước hoặc giá trị ngoài hợp đồng. Tuy nhiên, không xem các trường chưa xác minh là nguồn thẩm quyền để cập nhật dữ liệu hoặc cấp quyền.

### 5.2. So sánh đúng tag và kiểm soát input

Tag cần được decode theo định dạng chặt chẽ về độ dài và ký tự trước khi so sánh byte. Không chấp nhận signature thiếu, nhiều giá trị không được hỗ trợ hoặc chuỗi bị cắt.

Dùng hàm HMAC và hàm kiểm tra tag của thư viện phù hợp. Không dùng so sánh chuỗi tự viết có thể dừng sớm theo ký tự đầu khác nhau.

Hành vi thời gian hằng của phép so sánh không có nghĩa toàn bộ endpoint phải trả lời trong thời gian giống hệt nhau với mọi request. Các kiểm soát cú pháp, giới hạn và lookup vẫn cần thiết để hạn chế chi phí.

Không thử mọi secret có trong hệ thống khi key ID không tồn tại. Nếu hỗ trợ một tập khóa chuyển tiếp, tập đó phải có cận và nằm trong cùng phạm vi tin cậy.

### 5.3. Parser không được chạy nghiệp vụ trước xác minh

Giữ raw body không đồng nghĩa bắt buộc nạp mọi request vào bộ nhớ không giới hạn. Có thể đọc có cận hoặc dùng vùng đệm được kiểm soát theo thiết kế.

Sau khi signature hợp lệ, vẫn phải parse bằng quy tắc rõ ràng: schema, độ sâu, độ dài field, kiểu dữ liệu và cách xử lý field trùng. Không để các parser khác nhau chọn giá trị khác nhau cho cùng một trường có ý nghĩa bảo mật.

Nếu event ID xuất hiện cả ở header đã được bảo vệ và body, hai giá trị phải khớp theo hợp đồng. Producer principal và tenant được phép không lấy tùy ý từ body; chúng phải được ràng buộc với cấu hình nguồn gửi và policy.

### 5.4. Mã giả

```text
receive_webhook(request):
    enforce_route_method_media_type_and_size_limits(request)
    raw_body = read_bounded_body_without_json_transformation(request)

    fields = parse_strict_signature_headers(request)
    profile = require_supported_version(fields.version)
    endpoint = trusted_endpoint_configuration(request.route)
    key = require_eligible_key(endpoint.producer, endpoint.id, fields.key_id)

    expected_tag = hmac_sha256(key, build_signed_bytes(
        endpoint.id, fields.key_id, fields.timestamp,
        fields.event_id, raw_body
    ))

    if not constant_time_verify(expected_tag, decode_strict_tag(fields.signature)):
        return authentication_failure

    verify_signed_timestamp_against_trusted_clock(fields.timestamp)
    event = parse_and_validate_event_schema(raw_body)
    verify_event_identity_and_authorized_business_scope(event, fields, endpoint)

    result = persist_or_find_event_atomically(
        producer=endpoint.producer,
        endpoint=endpoint.id,
        event_id=fields.event_id,
        body_digest=server_computed_digest(raw_body),
        trusted_verification_record=verification_context
    )

    return delivery_receipt_after_durable_result(result)
```

Mã giả mô tả trách nhiệm, không phải code triển khai chạy nguyên trạng. Việc hết hiệu lực khóa, định dạng input, trạng thái lưu trữ và kết quả xung đột phải có quy tắc cụ thể.

Không thực hiện side effect nghiệp vụ chỉ vì HMAC hợp lệ ở bước giữa. Cổng tiếp nhận còn phải kiểm soát schema, phạm vi và chống trùng.

## 6. Chống phát lại và xử lý giao hàng lặp

### 6.1. Timestamp phải được bảo vệ

Nếu timestamp không nằm trong dữ liệu được ký, người phát lại có thể thay nó bằng thời gian mới. Trong profile minh họa, timestamp đã là thành phần của HMAC.

Ví dụ bên nhận chấp nhận:

```text
now - 300 giây <= signed_timestamp <= now + 60 giây
```

Hai biên đều được tính là nằm trong cửa sổ ở ví dụ này. Cần quy định đơn vị, đồng hồ, độ lệch và hành vi khi đồng hồ ngoài mức cho phép.

Cửa sổ này hạn chế việc dùng một lần giao hàng quá cũ, nhưng không ngăn cùng request được phát nhiều lần trong 5 phút. Nó cũng không biết sự kiện đã làm thay đổi dữ liệu hay chưa.

### 6.2. Event ID ổn định và receipt bền vững

Một khóa chống trùng có thể là:

```text
(producer_principal_id, endpoint_id, event_id)
```

Không dùng key ID làm producer identity duy nhất vì một producer có thể luân chuyển khóa. Nếu đổi khóa làm đổi namespace chống trùng, cùng sự kiện có thể bị xử lý lại.

Với cùng khóa logic:

- Chưa có: ghi nhận một sự kiện mới.
- Đã có và cùng payload bất biến: trả receipt phù hợp mà không tạo tác dụng phụ mới.
- Đã có nhưng khác payload: từ chối hoặc đưa vào đối soát như xung đột, không âm thầm ghi đè.

Profile ví dụ yêu cầu retry giữ nguyên byte body. Sender cần lưu sự kiện và biểu diễn đã chốt, không serialize lại theo một cách khác mỗi lần thử. Nếu một hệ thống cho phép thay biểu diễn hoặc nội dung theo retry, phải định nghĩa phép so sánh khác có tính quyết định; không áp dụng quy tắc digest raw body một cách mù quáng.

### 6.3. Retry hợp lệ khác phát lại không được kiểm soát

Trong profile này, mỗi lần giao lại có timestamp và signature mới, nhưng giữ event ID và body:

```text
Lần 1: event_id=evt_001, body=B, timestamp=T1, signature=S1
Lần 2: event_id=evt_001, body=B, timestamp=T2, signature=S2
```

Nếu lần 1 đã commit receipt nhưng mất response, lần 2 vẫn được xác minh rồi nhận receipt cũ. Không bỏ xác minh chỉ vì event ID đã tồn tại; nếu không, một người biết ID có thể tác động endpoint mà không có bằng chứng nguồn gửi.

Phát lại request cũ trong cửa sổ có thể vẫn có signature hợp lệ, nhưng chỉ được hấp thụ như một bản giao trùng. Sau cửa sổ, timestamp cũ không được dùng để vượt xác thực, kể cả ID đã từng được nhận.

### 6.4. Tuổi sự kiện và thời hạn giữ deduplication

Timestamp của lần giao hàng không phải thời điểm sự kiện phát sinh. Một retry được ký hôm nay có thể mang sự kiện cũ nhiều ngày.

Ví dụ policy bổ sung:

- Body có `occurredAt` bất biến, được bảo vệ bởi HMAC.
- Không nhận sự kiện quá 72 giờ hoặc có thời điểm phát sinh vượt quá mức tương lai 60 giây.
- Receipt chống trùng giữ ít nhất 7 ngày kể từ lần tiếp nhận đầu.
- Event ID không được producer tái sử dụng cho một sự kiện khác.

Các mốc này cần tương thích với hợp đồng retry. Cửa sổ tuổi sự kiện ngăn việc sau khi xóa receipt lại nhận một sự kiện cũ như mới chỉ vì sender tạo signature mới.

Nếu không có giới hạn tuổi sự kiện đáng tin hoặc có nhu cầu replay lịch sử dài hơn, cần cơ chế replay riêng và bất biến nghiệp vụ đủ bền. Không tự kết luận TTL của một cache chống trùng giải quyết mọi phát lại.

### 6.5. Inbox và tác dụng phụ

Ghi receipt phải nguyên tử theo khóa chống trùng. Hai request đồng thời cùng đọc “chưa có” rồi đều xử lý sẽ phá mục tiêu.

Một thiết kế thường tách:

```text
Request đã xác minh
  -> Inbox bền vững, duy nhất theo event identity
  -> Worker xử lý theo trạng thái
  -> Thay đổi nghiệp vụ và outbox
  -> Tác dụng phụ bên ngoài theo hợp đồng idempotency/đối soát
```

Trong cùng kho giao dịch, cập nhật nghiệp vụ và đánh dấu inbox đã xử lý cần được phối hợp phù hợp. Nếu gọi hệ thống ngoài, một transaction local không tự bảo đảm tác dụng phụ chỉ xảy ra một lần.

Sau khi inbox đã lưu bằng chứng xác minh, worker xử lý nội bộ dùng record tin cậy đó. Không áp lại cửa sổ timestamp HTTP như thể công việc chờ trong queue là một request Internet mới; quyền và điều kiện nghiệp vụ hiện tại vẫn cần kiểm tra theo policy.

### 6.6. Thứ tự sự kiện là một yêu cầu riêng

Signature không làm các webhook đến đúng thứ tự. Deduplication cũng không ngăn một sự kiện cũ ghi đè trạng thái mới.

Có thể cần version của đối tượng, sequence hoặc đối soát từ nguồn có thẩm quyền. Cách xử lý phải dựa trên hợp đồng nghiệp vụ, không lấy timestamp giao hàng mới hơn làm bằng chứng trạng thái nghiệp vụ mới hơn.

Nếu cần truy vấn lại nguồn, endpoint và quyền truy vấn phải được xác định an toàn. Không tự tải một URL bất kỳ trong payload chỉ vì payload đã được ký bởi một đối tác.

## 7. Vòng đời khóa, proxy và hành vi khi có lỗi

### 7.1. Quản lý secret theo phạm vi

Secret cần được tạo bằng nguồn ngẫu nhiên phù hợp, phân phối qua cơ chế quản lý bí mật và chỉ cấp cho thành phần cần ký hoặc xác minh.

Phải quy định encoding khi lưu cấu hình. Một secret được biểu diễn bằng base64 cần được giải mã theo hợp đồng để lấy đúng byte; không tự dùng chuỗi hiển thị như khóa nếu profile không quy định như vậy.

Không đưa secret vào URL, body webhook, repository, ảnh triển khai hoặc log. Mỗi producer, endpoint và môi trường cần có phạm vi khóa rõ để sự cố một khóa không mở rộng ngoài dự kiến.

Nếu dùng chữ ký bất đối xứng, khóa công khai không phải bí mật nhưng nguồn của nó phải đáng tin. Không tin một public key hoặc một URL tải khóa do chính request chưa xác minh đưa ra.

### 7.2. Luân chuyển và thu hồi

Một kế hoạch có thể phân biệt:

- Khóa đang dùng để ký.
- Khóa cũ còn được xác minh trong thời gian chuyển tiếp.
- Khóa đã hết quyền xác minh.
- Khóa bị thu hồi do sự cố.

Khoảng đồng tồn tại phải có cận, được kiểm thử và không làm đổi producer identity của sự kiện. Bên gửi có thể ký retry bằng khóa mới trong khi giữ event ID và body cũ.

Nếu khóa bị lộ, không mặc nhiên tiếp tục tin đến hết khoảng chuyển tiếp thông thường. Cần quy trình chặn sử dụng, phân phối trạng thái, điều tra các sự kiện đã nhận và phục hồi giao hàng có kiểm soát.

Key ID được bảo vệ trong profile ví dụ, nhưng lookup vẫn phải kiểm tra nó thuộc endpoint và producer nào, còn hiệu lực xác minh hay không. Một key ID hợp lệ ở test không được tìm ra secret production.

### 7.3. Bảo toàn dữ liệu qua proxy và framework

Framework cần cho verifier tiếp cận byte body theo hợp đồng. Một middleware parse JSON rồi thay body bằng dữ liệu serialize lại có thể làm mất biểu diễn gốc.

Nếu xác minh ở gateway rồi chuyển request nội bộ, phải định nghĩa nguồn tin cậy của kết quả và binding với nội dung thực sự được xử lý. Không nhận một header `signature_verified=true` từ Internet.

Nếu gateway thay nội dung sau xác minh, signature gốc không tự chứng minh biểu diễn đã biến đổi. Cần quan hệ dẫn xuất và ngữ cảnh nội bộ được bảo vệ, hoặc một giao thức xác thực phù hợp cho đoạn sau.

### 7.4. Phản hồi và retry

Hợp đồng phản hồi cần phân biệt:

| Tình huống | Hành vi minh họa |
|---|---|
| Cú pháp hoặc schema không hỗ trợ | Phản hồi 4xx theo hợp đồng, không xử lý nghiệp vụ |
| Không xác minh được signature hoặc freshness | Từ chối với thông báo ngoài đủ tổng quát; log phân biệt nguyên nhân |
| Cùng event ID nhưng khác payload | Báo xung đột và ghi nhận điều tra, không ghi đè |
| Sự kiện mới đã commit inbox | Trả receipt 2xx theo hợp đồng |
| Bản giao trùng đã xác minh và cùng nội dung | Trả receipt phù hợp mà không tạo hiệu ứng mới |
| Chưa thể lưu bền vững | Không trả như thể đã nhận thành công; dùng lỗi tạm thời nếu phù hợp |

Trong ví dụ, `202 Accepted` nghĩa là đã tiếp nhận bền vững để xử lý, không có nghĩa nghiệp vụ đã hoàn tất. Producer phải hiểu đúng ý nghĩa này.

Nếu receipt đã commit nhưng response mất trên mạng, producer có thể retry. Receiver phải chịu được tình huống này, không cố hứa một response 2xx sẽ luôn đến được bên gửi.

Backoff, giới hạn retry và thời hạn giao hàng phải được hai bên thống nhất. Không dùng lỗi xác thực như lý do retry vô hạn hoặc chuyển sang endpoint không kiểm tra chữ ký.

## 8. Ví dụ đặc tả: webhook thông báo báo cáo sẵn sàng

### 8.1. Bối cảnh

Đối tác gửi sự kiện `report.ready` tới một endpoint đã đăng ký của cổng tài liệu. Sự kiện chỉ được dùng cho tenant và báo cáo mà đối tác đó được phép thông báo.

Rủi ro `R-WHS-01` là request giả hoặc phát lại làm công bố sai báo cáo, tạo thông báo trùng hoặc cập nhật nhầm tenant.

Ví dụ dùng profile HMAC ở trên, giới hạn body 1 MiB, chỉ nhận JSON không nén, timestamp giao hàng lùi tối đa 300 giây và vượt tương lai tối đa 60 giây. Tuổi sự kiện tối đa 72 giờ, receipt giữ tối thiểu 7 ngày.

Payload logic có thể gồm:

```json
{
  "eventId": "evt_001",
  "type": "report.ready",
  "occurredAt": 1790000000,
  "reportId": "report_17",
  "reportVersion": 3
}
```

Giá trị thời gian chỉ minh họa schema. Khi kiểm thử hợp lệ phải dùng thời gian nằm trong các cửa sổ đã định nghĩa; không dùng con số cố định này như thông điệp còn hiệu lực.

### 8.2. Tập yêu cầu có thể kiểm chứng

| ID | Yêu cầu |
|---|---|
| SEC-WHS-01 | Endpoint chỉ nhận method, media type, encoding và profile được allowlist; dữ liệu tệp body thực nhận không vượt 1 MiB. Header bảo mật có giới hạn độ dài, cú pháp và không xuất hiện lặp mơ hồ. |
| SEC-WHS-02 | Receiver phải tính HMAC trên đúng byte và các trường của profile. Không parse/serialize JSON để thay thế raw body được ký. |
| SEC-WHS-03 | Key ID chỉ lookup trong nguồn cấu hình tin cậy của producer và endpoint. Khóa sai môi trường, bị thu hồi hoặc hết quyền xác minh không được chấp nhận. |
| SEC-WHS-04 | Signature được decode chặt chẽ và kiểm tra bằng hàm phù hợp của thư viện mật mã; không chấp nhận thiếu, sai độ dài hoặc fallback sang không xác minh. |
| SEC-WHS-05 | Timestamp thuộc dữ liệu được bảo vệ và phải nằm trong cửa sổ `now - 300 <= ts <= now + 60`. Đồng hồ hoặc cấu hình ngoài điều kiện tin cậy phải có hành vi xử lý rõ ràng. |
| SEC-WHS-06 | Chỉ sau xác minh mới parse nghiệp vụ, kiểm tra schema và quyền nguồn gửi. Event ID trong header và body phải khớp; partner không được tự chọn tenant ngoài phạm vi. |
| SEC-WHS-07 | Inbox duy nhất theo producer, endpoint và event ID; retry cùng body nhận lại receipt, khác body tạo xung đột. Key rotation không đổi namespace chống trùng. |
| SEC-WHS-08 | Chỉ nhận sự kiện có `occurredAt` trong giới hạn 72 giờ và độ lệch tương lai 60 giây theo policy; receipt giữ ít nhất 7 ngày từ lần nhận đầu. Producer không tái sử dụng ID cho sự kiện khác. |
| SEC-WHS-09 | Response tiếp nhận thành công chỉ phát sau commit inbox và trạng thái đủ để phục hồi việc xử lý. Không cần chờ hoàn tất mọi tác vụ bên ngoài để trả receipt nếu hợp đồng dùng xử lý bất đồng bộ. |
| SEC-WHS-10 | Hai request đồng thời cùng sự kiện không được tạo hai kết quả nghiệp vụ trái hợp đồng. Business update, trạng thái inbox và outbox phải được phối hợp theo ranh giới giao dịch đã chọn. |
| SEC-WHS-11 | Retry worker, message lặp hoặc lỗi sau side effect phải dùng định danh thao tác ổn định và đối soát phù hợp. Không tuyên bố một transaction local bảo đảm đúng một lần ở mọi hệ thống ngoài. |
| SEC-WHS-12 | Sự kiện đến muộn hoặc trái thứ tự không được ghi đè phiên bản báo cáo mới hơn chỉ vì timestamp giao hàng mới hơn. |
| SEC-WHS-13 | Chính sách luân chuyển, thu hồi khóa và khoảng cache phải có phiên bản, thời hạn và bằng chứng kiểm thử. Không giữ secret cũ trong tập xác minh vô thời hạn. |
| SEC-WHS-14 | Log được producer, endpoint, event reference, profile, key reference, quyết định xác minh, replay/xung đột và kết quả xử lý; không log secret, toàn bộ signature hoặc payload nhạy cảm dư thừa. |

Các quyết định về freshness dùng đồng hồ có thẩm quyền. Không lấy timestamp do request gửi làm “thời gian hiện tại” để tự kiểm tra chính nó.

Signature hợp lệ không cho phép công bố một tệp đang bị cách ly hoặc thuộc người không được chia sẻ. Sự kiện `report.ready` cần liên kết đúng báo cáo, phiên bản và các điều kiện an toàn của tài nguyên trước khi tạo kết quả.

### 8.3. Ranh giới tiếp nhận và xử lý

```text
Internet
  -> HTTPS endpoint và giới hạn tiếp nhận
  -> verifier theo profile/khóa đúng phạm vi
  -> schema, freshness sự kiện và quyền nguồn gửi
  -> inbox commit
  -> receipt 202
  -> worker đọc inbox tin cậy
  -> cập nhật có điều kiện theo reportVersion
  -> outbox/thông báo với xử lý lặp phù hợp
```

Nếu kho inbox không sẵn sàng, không bỏ qua bước này rồi thực hiện nghiệp vụ trực tiếp. Nếu backlog tăng, cần backpressure và cận lưu trữ; không nới xác thực để cải thiện tỷ lệ nhận.

## 9. Tiêu chí kiểm thử và bằng chứng

### 9.1. Tạo fixture đúng hợp đồng

Dùng secret kiểm thử riêng, clock kiểm soát được và một signer độc lập với verifier khi có thể. Chuẩn bị byte body, các trường ký và expected tag đã chốt để phát hiện hai phía cùng lặp một lỗi.

Kiểm thử cần đi qua proxy và middleware thực tế để xác nhận byte verifier đọc đúng biểu diễn. Không chỉ gọi trực tiếp một hàm HMAC trên chuỗi JSON tự tạo.

### 9.2. Ma trận kiểm chứng

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Thông điệp hợp lệ | Đúng profile, endpoint, khóa, body, thời gian và phạm vi | Commit một inbox record và trả receipt theo hợp đồng |
| T02 — Sửa trường đã bảo vệ | Đổi timestamp, event ID, key ID hoặc audience nhưng giữ tag cũ | Không xác minh thành công; không tạo side effect |
| T03 — Đổi byte body | Đổi một byte hoặc khoảng trắng JSON mà không ký lại | Tag không khớp; không dùng JSON serialize lại để làm thông điệp “hợp lệ” |
| T04 — Header không hợp lệ | Thiếu, lặp, quá dài, signature sai độ dài hoặc timestamp không chuẩn | Từ chối có kiểm soát; không chọn ngẫu nhiên một giá trị thuận lợi |
| T05 — Profile hoặc khóa sai | Phiên bản ngoài allowlist, key ID không thuộc endpoint hoặc khóa đã thu hồi | Không fallback; không thử toàn bộ secret của hệ thống |
| T06 — Biên timestamp | Thử đúng biên lùi 300 giây, tương lai 60 giây và vượt mỗi biên một giây | Kết quả khớp quy ước bao gồm biên đã định nghĩa |
| T07 — Phát lại trong cửa sổ | Gửi nhiều lần cùng request còn hợp lệ | Có thể xác minh nhưng chỉ một sự kiện và không thêm hiệu ứng nghiệp vụ |
| T08 — Retry có chữ ký mới | Giữ body và event ID, đổi timestamp và tag hợp lệ | Dùng cùng receipt/operation identity, không xử lý thành sự kiện mới |
| T09 — Cùng ID khác payload | Ký hợp lệ hai body khác nhau cho cùng event identity | Phát hiện xung đột; không ghi đè bản đã nhận |
| T10 — Hai request đồng thời | Dùng barrier cho nhiều request cùng event ID qua nhiều replica | Chỉ một inbox record mới và không có hai kết quả nghiệp vụ trái hợp đồng |
| T11 — Crash quanh commit | Dừng trước inbox commit, sau inbox commit hoặc quanh transaction worker | Không ACK giả trước lưu; retry và phục hồi không tạo tác dụng phụ ngoài hợp đồng |
| T12 — Body qua middleware | Dùng JSON có Unicode, newline và khoảng trắng qua đường triển khai thực | Verifier dùng đúng byte; xử lý framing không bị nhầm thành phần nội dung |
| T13 — Giới hạn tiếp nhận | Body vượt 1 MiB, media type hoặc encoding ngoài profile | Bị chặn theo policy; không dùng body tự khai nhỏ hơn thực tế |
| T14 — Sai tenant hoặc đối tượng | Producer có tag hợp lệ nhưng gửi báo cáo ngoài phạm vi | Không cập nhật đối tượng trái quyền |
| T15 — Trái thứ tự | Nhận phiên bản báo cáo mới trước phiên bản cũ | Trạng thái không bị lùi chỉ vì bản giao cũ có timestamp mới |
| T16 — Luân chuyển | Retry cùng sự kiện bằng khóa mới, sau đó thử khóa cũ đã hết quyền xác minh | Khóa mới giữ cùng namespace chống trùng; khóa hết hiệu lực bị từ chối |
| T17 — Đổi endpoint/môi trường | Dùng request của endpoint khác hoặc cấu hình test để gửi production | Không hợp lệ trong phạm vi mới |
| T18 — Tuổi sự kiện và retention | Sau khi receipt hết thời gian giữ, ký lại sự kiện quá cũ với timestamp giao hàng mới | Không nhận lại như sự kiện mới; policy tuổi sự kiện vẫn chặn |
| T19 — Queue xử lý chậm | Inbox đã xác minh chờ quá cửa sổ timestamp HTTP rồi worker xử lý | Không coi đây là request Internet mới; vẫn kiểm tra điều kiện nghiệp vụ theo policy |

T09 cần được tạo bằng khóa kiểm thử đủ quyền để chứng minh quy tắc chống xung đột sau xác minh. Một payload bị sửa mà không ký lại chỉ kiểm chứng toàn vẹn, chưa kiểm chứng inbox.

Với T10 và T11, đối chiếu cả inbox, thay đổi nghiệp vụ, outbox và kết quả bên ngoài. Đếm response 2xx không chứng minh không có tác dụng phụ trùng.

Với T18, phải kiểm soát cả thời gian nguồn sự kiện, thời gian receiver và tình trạng khóa. Một lỗi hết hạn khóa không thay thế bằng chứng chính sách tuổi sự kiện đã hoạt động.

### 9.3. Bằng chứng cần giữ

```text
producer/endpoint/profile có thẩm quyền
  -> các trường và digest của byte đã xác minh
  -> quyết định signature và freshness
  -> inbox identity và kết quả chống trùng
  -> thao tác nghiệp vụ/outbox
  -> receipt hoặc kết quả đối soát
```

Báo cáo ghi clock, phiên bản profile, khóa kiểm thử, số replica, lịch gây lỗi và trạng thái đầu. Không đưa secret thật vào hồ sơ kiểm thử hoặc bản ghi chia sẻ.

## 10. Liên kết rủi ro, yêu cầu và kiến trúc

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng |
|---|---|---|---|
| R-WHS-01: Request giả hoặc bị sửa | SEC-WHS-01–04 | Verifier strict, raw body và key lookup đúng phạm vi | T01–T05, T12, T13 |
| Phát lại gây thay đổi lặp | SEC-WHS-05, 07, 08 | Timestamp được ký, inbox duy nhất và tuổi sự kiện | T06–T10, T18 |
| ACK nhưng mất công việc hoặc xử lý lặp khi crash | SEC-WHS-09–11 | Inbox bền vững, worker giao dịch và outbox/idempotency | T11, T19 |
| Producer hợp lệ cập nhật sai đối tượng | SEC-WHS-06 | Ràng buộc tenant, báo cáo và loại sự kiện | T14 |
| Sự kiện cũ ghi đè dữ liệu mới | SEC-WHS-12 | Quy tắc version và đối soát nghiệp vụ | T15 |
| Luân chuyển làm mở lại replay hoặc giữ khóa cũ | SEC-WHS-03, 07, 13 | Producer identity ổn định và trạng thái khóa có cận | T16, T17 |
| Không giải thích được quyết định | SEC-WHS-14 | Audit có cấu trúc và liên kết inbox với tác dụng phụ | Đối chiếu chuỗi sự kiện tới kết quả |

Khi thay framework, proxy, format body, retry policy hoặc hệ thống quản lý khóa, cần đánh giá lại các yêu cầu liên quan. Bật một thư viện xác minh không thay thế kiểm chứng toàn bộ đường nhận và xử lý.

## 11. Logging và vận hành

Một record có thể có:

```text
request_reference
producer_reference, endpoint_reference
profile_version, key_reference
event_reference
body_digest
signature_result, freshness_result
schema_result, authorization_result
inbox_decision = new | duplicate | conflict
processing_state, operation_reference
reason_code
received_at, verified_at
```

Các trường được lấy từ request trước xác minh phải được phân biệt với danh tính và dữ liệu đã được tin cậy. Không ghi producer đã xác thực chỉ vì caller tự nhận một tên trong header.

Không log secret, raw signature hoặc toàn bộ payload theo mặc định. Những dữ liệu cần cho xử lý và đối soát được lưu trong kho phù hợp, có quyền truy cập và thời hạn riêng; retention audit không nhất thiết đồng nhất với retention body.

Các chỉ số hữu ích gồm:

- Request hợp lệ, signature không khớp và profile không hỗ trợ.
- Timestamp quá cũ, vượt tương lai và sự kiện quá tuổi.
- Key lookup lỗi, khóa hết hiệu lực hoặc thu hồi chưa lan truyền.
- Sự kiện mới, giao trùng, payload xung đột và retry.
- Tuổi inbox chưa xử lý, lỗi worker, outbox và số việc cần đối soát.
- Độ trễ tiếp nhận bền vững, backlog và mức sử dụng tài nguyên.

Không đưa event ID, raw key ID không giới hạn hoặc digest làm nhãn metric tùy ý. Lưu chi tiết trong log được kiểm soát và giới hạn tác động của request lỗi hàng loạt.

Khi signature lỗi tăng, cần phân biệt sai secret, sai byte do middleware, đồng hồ, profile và hoạt động không hợp lệ. Không khắc phục bằng cách tạm bỏ xác minh trên endpoint thật.

Khi secret bị lộ, signature hợp lệ không còn đủ để phân biệt sự kiện thật với sự kiện giả trong phạm vi ảnh hưởng. Cần chặn khóa, đối soát nguồn, xem xét các thay đổi đã tạo và phục hồi theo quy trình.

Replay vận hành phải có danh tính, phạm vi, lý do và bằng chứng riêng. Không xóa receipt hàng loạt hoặc đổi event ID để ép mọi sự kiện cũ thành mới mà không kiểm tra hậu quả nghiệp vụ.

## 12. Các lỗi đặc tả thường gặp

| Phát biểu | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “Có HTTPS nên không cần kiểm tra nguồn webhook” | TLS server authentication chưa xác thực thông điệp theo hợp đồng | Đặc tả xác thực nguồn và dữ liệu được bảo vệ |
| “Chỉ hash body là đủ” | Hash không có khóa có thể được tính lại khi sửa body | Dùng HMAC hoặc chữ ký theo profile được chọn |
| “Ký JSON đã parse cho tiện” | Có thể khác byte bên gửi ký | Giữ đúng biểu diễn hoặc dùng canonicalization đã được cả hai bên định nghĩa |
| “Timestamp không cần ký” | Có thể bị đổi khi phát lại | Bảo vệ timestamp cùng các trường quyết định |
| “Có cửa sổ 5 phút là không replay được” | Cùng request vẫn có thể dùng nhiều lần trong cửa sổ | Kết hợp event identity và lưu chống trùng bền vững |
| “Key ID là producer ID” | Rotation có thể làm đổi namespace chống trùng | Giữ producer principal độc lập với phiên bản khóa |
| “Retry phải có event ID mới” | Làm mất khả năng nhận diện cùng sự kiện | Giữ ID và nội dung bất biến, thay metadata giao hàng theo hợp đồng |
| “Trả 2xx rồi lưu sau” | Có thể mất sự kiện dù sender đã ngừng retry | ACK sau tiếp nhận bền vững |
| “Signature đúng thì cập nhật mọi tenant được” | Nguồn có thể chỉ có quyền một phạm vi | Kiểm tra quyền đối tượng và loại sự kiện |
| “Cache dedup hết hạn thì nhận lại như mới” | Có thể mở replay lịch sử | Định nghĩa tuổi sự kiện, retention và đường replay có kiểm soát |

## 13. Bài tập áp dụng

Bạn thiết kế endpoint nhận sự kiện tài liệu đã xử lý từ một đối tác. Hãy viết tập yêu cầu gồm:

1. Producer identity, endpoint audience, môi trường và phạm vi khóa.
2. Các byte và field được ký, quy tắc encoding, header và phiên bản.
3. Cửa sổ timestamp, tuổi sự kiện, độ lệch clock và hành vi lỗi.
4. Event identity, quy tắc retry, xung đột payload và retention.
5. Ranh giới inbox, response tiếp nhận và tác dụng phụ nghiệp vụ.
6. Quy tắc khi sự kiện đến muộn, trái thứ tự hoặc thuộc tenant khác.
7. Ca kiểm thử sửa byte, phát lại, rotation và crash sau commit.
8. Chuỗi truy vết từ rủi ro tới yêu cầu, kiến trúc và bằng chứng.

Tự kiểm tra: **Receiver có chứng minh được nguồn và tính toàn vẹn của đúng thông điệp đang xử lý, đồng thời kiểm soát được số lần thông điệp đó tạo tác dụng phụ không?** Nếu chỉ có một header tên “signature” mà không trả lời được các câu hỏi này, yêu cầu vẫn còn thiếu.
