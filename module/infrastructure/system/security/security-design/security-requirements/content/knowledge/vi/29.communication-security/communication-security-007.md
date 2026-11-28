# Replay protection cho message — Đặc tả yêu cầu chống phát lại thông điệp

## 1. Mục tiêu bảo mật

**Replay protection** là các yêu cầu ngăn một thông điệp đã được tạo hoặc chấp nhận trước đó bị sử dụng lại để tạo hiệu ứng ngoài số lần, thời hạn hoặc phạm vi được phép.

Ví dụ, orders-service gửi thông điệp giữ hai sản phẩm cho một đơn hàng. Bản sao của thông điệp có thể xuất hiện do retry, broker giao lại, thao tác phát lại từ nơi lưu hoặc hành vi sao chép thông điệp hợp lệ. Nếu consumer giữ thêm hai sản phẩm mỗi lần nhận, một yêu cầu nghiệp vụ có thể tạo nhiều hiệu ứng.

Thông điệp phát lại vẫn có thể có chữ ký đúng. Kênh truyền được mã hóa và bên gửi được xác thực cũng không tự chứng minh rằng hiệu ứng của thông điệp chưa từng được thực hiện.

Trong module đặc tả yêu cầu bảo mật, cần trả lời:

> Ai được phát thông điệp, thông điệp có hiệu lực trong phạm vi và thời gian nào, đơn vị nào chỉ được xử lý một lần, trạng thái chống lặp được lưu ở đâu và hiệu ứng được cam kết như thế nào?

Sau bài học, người đọc có thể:

- Phân biệt tính xác thực, độ mới và tính duy nhất của hiệu ứng.
- Thiết kế hợp đồng envelope, định danh và phạm vi chống phát lại.
- Đặc tả cập nhật trạng thái chống lặp nhất quán với dữ liệu nghiệp vụ.
- Xử lý thông điệp trùng, sai thứ tự, hết hạn và kết quả chưa rõ.
- Viết tiêu chí kiểm thử cho nhiều consumer replica, lỗi từng phần và phát lại có kiểm soát.

Các mốc thời gian và giới hạn trong bài thuộc hệ thống giả định. Chúng minh họa cách viết yêu cầu đo được, không phải cấu hình mặc định cho mọi giao thức.

## 2. Những bảo đảm không được nhầm lẫn

| Bảo đảm | Câu hỏi được trả lời | Điều chưa được chứng minh |
|---|---|---|
| Xác thực nguồn và tính toàn vẹn | Thông điệp có đến từ nguồn được chấp nhận và nội dung được bảo vệ có bị sửa không? | Thông điệp chưa từng được nhận hoặc xử lý. |
| Bảo mật kênh | Kết nối có được bảo vệ theo hồ sơ truyền thông không? | Dữ liệu hợp lệ không bị giao lại ở tầng ứng dụng. |
| Freshness — độ mới | Thông điệp có nằm trong khoảng thời gian được chấp nhận không? | Không có hai bản sao trong chính khoảng đó. |
| Deduplication — chống xử lý trùng | Định danh này đã được consumer chấp nhận theo phạm vi chưa? | Một định danh mới không biểu diễn cùng nghĩa vụ nghiệp vụ. |
| Idempotency nghiệp vụ | Lặp lại cùng thao tác logic có tạo thêm hiệu ứng không? | Mọi thông điệp đều có nguồn hợp lệ và đúng quyền. |
| Ordering — thứ tự | Thông điệp có được xử lý theo quy tắc trình tự không? | Mỗi hiệu ứng chỉ xuất hiện một lần hoặc thông điệp không bị giả mạo. |

Các tình huống cần đưa vào mô hình đe dọa:

- Sao chép một message hợp lệ và gửi lại khi nó vẫn còn hạn.
- Broker giao lại vì mất xác nhận sau khi consumer đã cam kết.
- Hai replica cùng nhận bản sao và cùng thấy chưa có dấu vết xử lý.
- Dùng message_id cũ với nội dung khác hoặc đổi message_id cho cùng một thao tác.
- Phát lại thông điệp cũ từ hàng đợi lỗi mà bỏ qua kiểm tra thời gian.
- Mất trạng thái chống lặp sau khởi động lại hoặc phục hồi backup.
- Lợi dụng việc reset số thứ tự hoặc hết hạn bản ghi để tạo thêm hiệu ứng.

Không phải mọi bản sao đều là tấn công. Hợp đồng phải cho phép hệ thống xử lý retry hợp lệ mà vẫn giữ bất biến nghiệp vụ.

## 3. Envelope phải bảo vệ cả ngữ cảnh sử dụng

### 3.1. Các trường quan trọng

Giả sử message yêu cầu inventory-service giữ hàng cho một đơn:

| Trường logic | Ý nghĩa |
|---|---|
| protocol_version | Phiên bản cách biểu diễn và quy tắc kiểm chứng. |
| message_type | Loại hành động, chẳng hạn reserve_inventory. |
| producer_id | Danh tính nguồn phát, được đối chiếu với bằng chứng xác thực. |
| audience | Dịch vụ hoặc nhóm consumer logic được phép nhận. |
| tenant_id | Phạm vi dữ liệu của thao tác, phải được kiểm tra quyền. |
| message_id | Định danh một thông điệp logic cùng các lần giao lại của nó. |
| business_operation_id | Định danh thao tác nghiệp vụ, chẳng hạn lần giữ hàng của đơn. |
| issued_at và expires_at | Mốc phát hành và hết hạn theo quy ước thời gian. |
| payload | Dữ liệu cần xử lý hoặc tham chiếu nội dung bất biến. |
| Bằng chứng xác thực | Cơ chế cho phép kiểm chứng nguồn và các trường được bảo vệ. |

Các trường quyết định phạm vi, thời gian, định danh và nội dung phải được bảo vệ toàn vẹn theo hồ sơ. Chỉ ký payload nhưng để audience hoặc message_id có thể bị sửa là chưa đủ.

Nếu payload tham chiếu dữ liệu bên ngoài, cần ràng buộc phiên bản hoặc dấu vân tay nội dung theo nghiệp vụ. Một đường dẫn có chữ ký không tự làm dữ liệu ở đường dẫn đó trở thành bất biến mãi mãi.

### 3.2. Không tin danh tính tự khai

producer_id phải khớp chủ thể được xác minh qua cơ chế đã phê duyệt. tenant_id có chữ ký cũng cần nằm trong phạm vi mà producer được phép tác động.

Nguồn khóa và thuật toán kiểm chứng phải bị giới hạn bởi chính sách máy chủ. Không để nội dung chưa xác minh chọn một địa chỉ tùy ý để tải khóa hoặc tự hạ mức kiểm tra.

Dữ liệu cần được phân tích trong giới hạn kích thước và cấu trúc trước khi thực hiện công việc tốn tài nguyên. Trong hồ sơ ví dụ, toàn bộ message không quá 64 KiB.

### 3.3. Biểu diễn và fingerprint

Bên ký và bên kiểm chứng phải thống nhất byte hoặc biểu diễn chuẩn hóa được bảo vệ. Không tự giả định rằng hai bản JSON được các thành phần diễn giải giống nhau nếu quy tắc chuẩn hóa chưa được xác định.

Để phát hiện cùng message_id nhưng khác nội dung, có thể lưu fingerprint của các trường ngữ nghĩa đã được xác minh. Fingerprint cần bao phủ danh tính nguồn, audience, tenant, loại, định danh nghiệp vụ, thời gian và payload theo hồ sơ.

Metadata giao nhận như delivery tag của broker hoặc số lần thử không được làm thay đổi danh tính message logic. Bản thân chữ ký có thể được biểu diễn khác trong một cơ chế; quy tắc nhận biết cùng nội dung cần được định nghĩa rõ, thay vì so tùy ý toàn bộ gói truyền.

## 4. Timestamp, nonce và số thứ tự

### 4.1. Timestamp giới hạn tuổi, không ngăn lặp trong cửa sổ

Hồ sơ minh họa quy định:

- expires_at phải lớn hơn issued_at.
- Khoảng hiệu lực được khai không quá mười phút.
- Sai lệch đồng hồ được phép tối đa 30 giây theo quy tắc kiểm chứng.
- Một message chưa được chấp nhận trước đó chỉ được nhận để tạo công việc mới khi còn trong cửa sổ hợp lệ.

Quy tắc thời gian minh họa tại quyết định tiếp nhận:

~~~text
issued_at - 30 giây <= thời_gian_máy_chủ <= expires_at + 30 giây

0 < expires_at - issued_at <= 10 phút
~~~

Timestamp phải thuộc phần được bảo vệ. Nếu bên phát lại có thể tự đổi thời gian mà không làm mất hiệu lực bằng chứng, giới hạn độ mới không còn ý nghĩa.

Mốc tiếp nhận bền vững cần được xác định trong thiết kế; không dùng thời điểm request đi qua một proxy làm bằng chứng rằng consumer đã chấp nhận. Thời hạn cho phép xử lý xong nghiệp vụ là yêu cầu khác. Một message được nhận đúng hạn không mặc nhiên được phép thực thi vô thời hạn.

Hai bản sao trong cùng cửa sổ mười phút đều có thể qua kiểm tra thời gian. Cần thêm trạng thái chống lặp hoặc cơ chế tương đương.

### 4.2. Nonce hoặc message_id cần được kiểm chứng và ghi nhớ

Một nonce ứng dụng hoặc định danh đủ khả năng tránh trùng giúp phân biệt các thông điệp. Tuy nhiên, sinh giá trị ngẫu nhiên ở producer không ngăn consumer chấp nhận lại chính giá trị đó.

Bên nhận phải ràng buộc định danh với nguồn, phạm vi và nội dung, rồi ghi nhận việc chấp nhận theo cơ chế nguyên tử. Không chỉ tìm trong bộ nhớ tiến trình rồi tiếp tục nếu không thấy.

Nonce dùng cho chống phát lại ở tầng ứng dụng có ngữ nghĩa khác nonce hoặc IV của cơ chế mã hóa. Không tái dùng một trường cho hai mục đích mà chưa có hồ sơ mật mã xác định.

### 4.3. Số thứ tự cần chính sách sai thứ tự và reset

Một số giao thức dùng sequence number. Khi đó cần quy định:

- Số thứ tự thuộc luồng nào và nguồn nào.
- Có cho phép giao sai thứ tự không.
- Cửa sổ trượt hoặc tập số đã dùng được lưu như thế nào.
- Khi nào bắt đầu một thế hệ luồng mới và ai được phép xác lập.
- Cách giữ trạng thái qua khởi động lại, failover và phục hồi.

Chỉ nhận số lớn hơn số cao nhất đã thấy có thể loại nhầm một message hợp lệ đến muộn. Nếu dùng cửa sổ cho phép sai thứ tự, đánh dấu số đã dùng vẫn phải nguyên tử với hiệu ứng tương ứng.

Không cho producer tự reset số về đầu rồi coi mọi message là mới mà thiếu cơ chế xác minh thế hệ luồng. Hồ sơ ví dụ của bài dùng message_id, cửa sổ thời gian và inbox; không yêu cầu sequence cho mọi loại message.

## 5. Phạm vi chống lặp và thao tác nhận nguyên tử

### 5.1. Chọn đúng khóa logic

Một khóa chống lặp có thể có dạng:

~~~text
môi trường
+ danh tính producer đã xác minh
+ tenant
+ consumer logic hoặc phạm vi nhận
+ message_id
~~~

Các replica của cùng inventory-consumer phải dùng cùng miền quyết định chống lặp. Bộ nhớ riêng trên từng replica không đủ bảo vệ khi bản sao đi tới replica khác.

Hai consumer logic khác nhau có thể đều cần xử lý cùng sự kiện. Không dùng một bản ghi chống lặp toàn hệ thống để vô tình ngăn consumer thứ hai thực hiện trách nhiệm của nó. Audience và phạm vi fan-out cần được đặc tả.

message_id của broker có thể thay khi chuyển hàng đợi hoặc phát lại. Nếu đó không phải định danh message ứng dụng được bảo vệ, không dùng nó làm căn cứ duy nhất để chống phát lại.

### 5.2. “Kiểm tra rồi thêm” có khoảng trống cạnh tranh

Cách xử lý sau chưa đủ:

~~~text
replica A: không thấy message_id trong cache
replica B: không thấy message_id trong cache
replica A: thực hiện nghiệp vụ
replica B: thực hiện nghiệp vụ
~~~

Cần thao tác nhận có tính nguyên tử hoặc cơ chế tương đương: chỉ một bên được cam kết hiệu ứng mới cho cùng khóa logic.

Ràng buộc duy nhất hoặc thao tác có điều kiện giúp quyết định bên nào nhận quyền xử lý. Nó phải được kết hợp với việc ghi hiệu ứng; nếu chỉ đánh dấu xong trước khi thực hiện rồi worker chết, công việc có thể bị mất.

### 5.3. Cùng khóa, cùng nội dung và nội dung xung đột

| Kết quả tra cứu | Hành vi |
|---|---|
| Chưa có, message còn hợp lệ | Có thể chấp nhận mới sau các kiểm tra và điều phối nguyên tử. |
| Đã hoàn tất, fingerprint khớp | Không tạo hiệu ứng mới; xác nhận hoặc trả biên nhận theo hợp đồng và quyền đọc. |
| Đang xử lý, fingerprint khớp | Theo dõi cùng công việc; không tạo một công việc độc lập thứ hai. |
| Cùng khóa nhưng fingerprint khác | Từ chối xung đột và ghi bằng chứng, không ghi đè bản cũ. |
| Không có và message đã hết hạn | Không tạo hiệu ứng mới; từ chối hoặc cách ly theo hợp đồng. |

Bản sao đã hoàn tất có thể được xác nhận mà không thực hiện lại, kể cả khi cửa sổ tạo công việc mới đã hết, nếu hệ thống vẫn xác minh được nguồn, nội dung và quyền theo chính sách.

Nếu không đủ bằng chứng để xác minh bản sao, không cần cho qua chỉ để giảm lỗi. Điều quan trọng là không tạo thêm hiệu ứng và không trả dữ liệu ngoài quyền.

## 6. Inbox, giao dịch nghiệp vụ và xác nhận giao nhận

Trong ví dụ, hiệu ứng là ghi một khoản giữ hàng trong cùng cơ sở dữ liệu với inbox chống lặp.

~~~text
xác minh envelope, nguồn, audience và quyền
tính fingerprint theo hồ sơ

trong một đơn vị giao dịch bảo vệ được bất biến:
  kiểm tra bản ghi inbox theo khóa logic

  nếu đã hoàn tất và nội dung khớp:
    dùng biên nhận đã lưu, không giữ hàng thêm
  nếu chưa có:
    kiểm tra độ mới tại mốc tiếp nhận được đặc tả
    nhận quyền xử lý bằng cơ chế chống cạnh tranh
    kiểm tra business_operation_id và điều kiện nghiệp vụ
    ghi hiệu ứng giữ hàng nếu chưa có hiệu ứng tương ứng
    ghi kết quả inbox và audit bắt buộc
    ghi outbox nếu cần phát sự kiện tiếp theo

sau khi giao dịch cam kết:
  xác nhận giao nhận theo hợp đồng broker
~~~

Đây là mã giả về ngữ nghĩa, không phải API của một sản phẩm. Thiết kế phải chỉ rõ ranh giới giao dịch và cơ chế xử lý tranh chấp.

Nếu lỗi trước cam kết, dữ liệu cục bộ phải giữ nhất quán và việc thử lại tuân theo hợp đồng. Nếu cam kết thành công nhưng mất xác nhận với broker, bản giao lại phải tìm được kết quả và không tạo hiệu ứng mới.

Không xác nhận với broker quá sớm rồi mới ghi hiệu ứng nếu hợp đồng yêu cầu bảo đảm công việc không mất. Cũng không giả định rằng xác nhận giao nhận và giao dịch cơ sở dữ liệu luôn là cùng một giao dịch.

Inbox ghi nhận message, còn business_operation_id bảo vệ thao tác nghiệp vụ. Một message mới với ID mới nhưng vẫn yêu cầu cùng lần giữ hàng không được tự tạo khoản giữ thứ hai trái hợp đồng.

## 7. Công việc kéo dài và hiệu ứng bên ngoài

### 7.1. Trạng thái đang xử lý không phải kết quả đã hoàn tất

Nếu công việc không thể kết thúc trong một giao dịch ngắn, inbox có thể có trạng thái như ACCEPTED, PROCESSING, COMPLETED hoặc RECONCILING.

Thiết kế phải quy định ai sở hữu công việc, cách nhận lại khi worker chết và bằng chứng nào cho phép chuyển trạng thái. Không xóa bản ghi PROCESSING chỉ vì đã lâu rồi cho bản sao tạo một công việc mới mà chưa biết công việc cũ đã làm gì.

Một lease hết hạn cũng không chứng minh worker cũ đã dừng. Quyền cam kết của worker cũ phải bị giới hạn tại nơi ghi hiệu ứng, chẳng hạn qua phiên bản sở hữu được kiểm tra, hoặc cơ chế tương đương phù hợp.

Chống lặp đầu vào không tự giải quyết mọi tranh chấp của công việc nền. Các bước xử lý và kết quả cuối vẫn cần giữ bất biến.

### 7.2. Outbox không tự làm hiệu ứng bên ngoài xảy ra một lần

Một sự kiện đã lưu trong outbox có thể được gửi nhiều lần. Consumer tiếp theo phải kiểm tra message logic hoặc định danh nghiệp vụ tương ứng.

Nếu gọi một hệ thống ngoài:

- Ghi execution_id trước khi gửi theo đơn vị cam kết được thiết kế.
- Dùng cùng định danh khi retry nếu hợp đồng bên ngoài hỗ trợ.
- Xác định lỗi nào chứng minh chưa thực hiện và lỗi nào chỉ là chưa biết kết quả.
- Tra cứu hoặc đối soát trước khi tạo một ý định mới khi kết quả còn chưa rõ.
- Xử lý callback trùng, sai thứ tự và không khớp với ý định đã lưu.

Khi bên ngoài đã thực hiện nhưng phản hồi bị mất, việc xóa inbox rồi chạy lại có thể tạo thêm hiệu ứng. Cần trạng thái RECONCILING và quy trình giải quyết, không coi timeout là bằng chứng chưa thực hiện.

### 7.3. Tính duy nhất cần được phát biểu theo hiệu ứng

Câu “message chỉ đến một lần” không phải bảo đảm ứng dụng luôn có thể kiểm chứng. Yêu cầu nên nói hiệu ứng nào không được tạo thêm, trong phạm vi và điều kiện nào.

Ví dụ: với một business_operation_id của lần giữ hàng, chỉ có một khoản giữ logic; mọi message liên quan tới lần đó phải trả về hoặc liên kết cùng kết quả, trừ hành động điều chỉnh được nghiệp vụ cho phép riêng.

Nếu ranh giới bên ngoài không hỗ trợ chống lặp hoặc tra cứu đủ để kiểm chứng, phải chỉ rõ giới hạn và bổ sung thiết kế trước khi kết luận đạt yêu cầu hiệu ứng một lần.

## 8. Thời hạn lưu, phát lại từ hàng đợi lỗi và phục hồi

### 8.1. Chọn thời hạn từ các cửa sổ thực tế

Trong hồ sơ ví dụ:

| Khoảng thời gian | Chính sách |
|---|---|
| Hiệu lực cho lần tiếp nhận mới | Tối đa mười phút, áp sai lệch đồng hồ 30 giây theo quy tắc. |
| Giao lại tự động của broker | Trong 24 giờ kể từ lần phát ban đầu của luồng này. |
| Lưu biên nhận inbox | Tối thiểu 24 giờ từ lần chấp nhận bền vững đầu tiên. |
| Ràng buộc thao tác nghiệp vụ | Giữ cùng lịch sử vòng đời của nghiệp vụ để ngăn tạo lại cùng hiệu ứng trái phép. |
| Bản sao đã hết hạn mà không có kết quả đã xác minh | Không tạo hiệu ứng mới. |

Không chỉ đặt thời hạn inbox bằng cửa sổ timestamp mà bỏ qua retry, chậm giao nhận, phục hồi và các đường phát lại khác.

Khi thời hạn lưu inbox kết thúc, message gốc vẫn đã hết cửa sổ tiếp nhận mới. Nó không được coi là công việc mới chỉ vì không còn bản ghi chống lặp.

Một producer có quyền phát message mới và thời gian mới vẫn không được dùng message_id mới để vượt ràng buộc business_operation_id. Đây là lớp bảo vệ khác với nhận diện bản sao nguyên trạng.

### 8.2. Dead-letter queue và phát lại có kiểm soát

Chuyển message sang hàng đợi lỗi không làm mới hiệu lực hoặc đổi nghĩa vụ nghiệp vụ. Nếu dùng lại message gốc, phải giữ các trường ứng dụng được bảo vệ, kể cả message_id và thời gian.

Message hết hạn không được tự đi qua một cờ “bỏ replay check”. Nếu cần xử lý nghiệp vụ muộn, cần một quy trình có thẩm quyền:

1. Kiểm tra nguyên nhân lỗi và kết quả đã có hoặc còn chưa rõ.
2. Xác định nghiệp vụ còn cho phép thực hiện hay không.
3. Quyết định dùng lại công việc đã được chấp nhận hay tạo một yêu cầu nghiệp vụ phù hợp.
4. Nếu phát envelope mới, bảo vệ đầy đủ ngữ cảnh và giữ liên kết tới nguồn gốc.
5. Áp lại guard theo business_operation_id, quyền và trạng thái.
6. Ghi người phê duyệt hoặc dịch vụ thực hiện cùng bằng chứng.

Một hành động bù hoặc điều chỉnh thực sự mới cần định danh và quyền riêng. Không đặt một ID ngẫu nhiên mới chỉ để vượt dấu vết của hành động cũ.

### 8.3. Khởi động lại và khôi phục backup

Cache trong bộ nhớ có thể mất khi tiến trình khởi động lại. Nếu đó là nơi duy nhất ghi thông điệp đã xử lý, hiệu ứng cũ có thể được tạo lại.

Inbox và dữ liệu nghiệp vụ cần được lưu, sao lưu và phục hồi theo cơ chế giữ nhất quán. Nếu phục hồi về thời điểm trước một hiệu ứng bên ngoài đã xảy ra, phải đối soát trước khi mở lại xử lý có thể tạo hiệu ứng.

Không chỉ kiểm tra số lượng bản ghi inbox sau phục hồi. Cần xác minh liên kết với biên nhận, business_operation_id, outbox và kết quả ngoài hệ thống.

### 8.4. Kho chống lặp không khả dụng

Khi không thể xác định message đã được xử lý hay chưa, không được mặc định rằng nó chưa từng được xử lý.

Đối với thao tác được bảo vệ, phải trả lỗi tạm thời, trì hoãn hoặc chuyển trạng thái theo hợp đồng mà không tạo hiệu ứng mới. Retry cần giới hạn và khoảng chờ phù hợp để tránh tạo vòng lặp giao lại gây quá tải.

Đầu vào chưa được xác thực không được chiếm bản ghi như một message hợp lệ. Đồng thời, cần hạn mức theo producer và năng lực lưu để nguồn hợp lệ bị lỗi không làm cạn kho trạng thái. Chạm giới hạn lưu không được âm thầm vô hiệu hóa chống lặp.

## 9. Bộ yêu cầu replay protection mẫu

### SR-RP-001 — Envelope được xác thực và ràng buộc đúng ngữ cảnh

Mỗi message phải được kiểm chứng nguồn và tính toàn vẹn theo hồ sơ có phiên bản. Các trường protocol_version, message_type, producer_id, audience, tenant_id, message_id, business_operation_id, thời gian và payload phải thuộc phạm vi được bảo vệ.

Producer phải có quyền phát loại thao tác cho tenant và audience tương ứng. Thông điệp cho môi trường hoặc bên nhận khác phải bị từ chối; không ánh xạ danh tính chỉ từ trường tự khai.

Message tối đa 64 KiB trong hồ sơ này. Bằng chứng nghiệm thu phải gồm sửa từng trường có ý nghĩa bảo mật, nguồn không được phép và audience sai.

### SR-RP-002 — Độ mới cho tiếp nhận mới

Lần chấp nhận bền vững đầu tiên phải tuân thủ cửa sổ thời gian đã đặc tả: khoảng hiệu lực không quá mười phút và sai lệch tối đa 30 giây.

Message chưa có kết quả đã xác minh mà hết hạn không được tạo công việc hoặc hiệu ứng mới. Bản sao đã hoàn tất, có nội dung khớp và đủ bằng chứng theo chính sách có thể được xác nhận mà không thực hiện lại.

Nếu không thể kiểm tra thời gian trong mức sai lệch cho phép, không tắt kiểm tra để tiếp nhận. Thời hạn hoàn thành nghiệp vụ, nếu có, phải được kiểm soát riêng.

### SR-RP-003 — Chống lặp nguyên tử qua mọi replica

Các replica cùng consumer logic phải chia sẻ một miền quyết định chống lặp theo môi trường, producer đã xác minh, tenant, consumer logic và message_id.

Việc nhận quyền tạo hiệu ứng mới phải bảo đảm chỉ một bên thắng trước các bản sao cạnh tranh. Cùng khóa và cùng fingerprint không tạo công việc độc lập thứ hai; cùng khóa nhưng khác fingerprint bị từ chối xung đột.

Bằng chứng phải gửi đồng thời ít nhất 20 bản sao tới nhiều replica, kiểm tra hiệu ứng và trạng thái bền vững. Không chỉ kiểm tra cache hoặc số response thành công.

### SR-RP-004 — Inbox và hiệu ứng cam kết nhất quán

Với thao tác giữ hàng cục bộ, kết quả inbox, thay đổi nghiệp vụ, audit bắt buộc và outbox nếu có phải được cam kết trong một đơn vị giao dịch hoặc cơ chế tương đương đã chứng minh.

Chỉ xác nhận giao nhận sau khi đạt mốc bền vững của hợp đồng. Mất xác nhận sau cam kết phải dẫn tới nhận diện bản giao lại, không giữ hàng thêm.

Nếu công việc nhiều bước hoặc có hiệu ứng ngoài, phải có trạng thái, quyền sở hữu và đối soát phù hợp. Không dùng việc đã ghi nhận message làm bằng chứng rằng hiệu ứng ngoài đã hoàn tất.

### SR-RP-005 — ID mới không tạo lại cùng hiệu ứng nghiệp vụ

Một business_operation_id của lần giữ hàng chỉ được tạo một khoản giữ logic trong mô hình ví dụ. Nhiều message_id hoặc nhiều lần giao của cùng nghĩa vụ phải quy về kết quả nghiệp vụ phù hợp.

Định danh nghiệp vụ phải gắn với đơn hàng, tenant và loại hành động có thẩm quyền. Client hoặc producer không được tự đổi tham chiếu để vượt điều kiện nghiệp vụ.

Bằng chứng gồm hai message hợp lệ, hai ID khác nhau nhưng cùng lần giữ hàng. Hiệu ứng phải không bị nhân đôi, kể cả khi các message đến đồng thời.

### SR-RP-006 — Lưu giữ và phát lại không mở lại quyền thực thi

Biên nhận inbox được giữ tối thiểu 24 giờ từ lần chấp nhận bền vững đầu tiên. Hết hạn inbox không làm mới hiệu lực message và không xóa ràng buộc chống tạo lại thao tác trong vòng đời nghiệp vụ.

Phát lại từ hàng đợi lỗi phải giữ nguyên envelope nếu dùng lại message gốc. Xử lý muộn bằng envelope mới cần quyền, căn cứ nghiệp vụ và liên kết truy vết, đồng thời vẫn chịu guard hiện tại.

Sau phục hồi dữ liệu, không mở lại đường có thể tạo hiệu ứng cho tới khi đánh giá nhất quán với kết quả đã xảy ra và giải quyết phạm vi cần đối soát.

### SR-RP-007 — Lỗi kho trạng thái không cho phép thực thi thiếu bằng chứng

Trong cấu hình minh họa, một lần truy cập kho chống lặp chờ tối đa 500 ms và chịu deadline chung của công việc. Khi không quyết định được trạng thái chống lặp, không tạo hiệu ứng mới.

Lỗi tạm thời được thử lại theo chính sách hữu hạn; trong hồ sơ ví dụ, sau tối đa năm lần xử lý thất bại tạm thời thì chuyển hàng đợi lỗi. Việc retry không làm mới timestamp hoặc bỏ guard.

Audit phải ghi consumer logic, replica, producer đã xác minh, tenant, message_id, business_operation_id, fingerprint, quyết định và mốc cam kết phù hợp. Không ghi credential hoặc payload nhạy cảm đầy đủ.

## 10. Ma trận kiểm thử và bằng chứng

| Kịch bản | Điều kiện thử | Kết quả phải chứng minh |
|---|---|---|
| Message hợp lệ lần đầu | Đúng nguồn, audience, thời gian và quyền nghiệp vụ. | Tạo đúng hiệu ứng, inbox và biên nhận nhất quán. |
| Lặp trong cửa sổ thời gian | Gửi lại cùng envelope khi chưa hết hạn. | Không tạo hiệu ứng thứ hai. |
| Bản sao đồng thời | 20 bản sao qua nhiều replica cùng consumer logic. | Chỉ một hiệu ứng logic được cam kết. |
| Cùng ID, nội dung khác | Thay payload hoặc trường bảo mật trong một message được nguồn thử ký lại. | Phát hiện xung đột, không ghi đè dấu vết cũ. |
| Hai ID, cùng nghiệp vụ | Hai message hợp lệ cho cùng lần giữ hàng. | Guard nghiệp vụ không cho nhân đôi khoản giữ. |
| Hết hạn, chưa từng chấp nhận | Message cũ không có kết quả đã xác minh. | Không tạo công việc mới dù kho chống lặp không có bản ghi. |
| Hết hạn nhưng đã hoàn tất | Bản sao có bằng chứng khớp kết quả đã lưu. | Chỉ xác nhận theo hợp đồng, không làm lại. |
| Lỗi trước cam kết | Dừng giữa ghi inbox và dữ liệu nghiệp vụ trong giao dịch thử. | Không có trạng thái từng phần trái quy tắc. |
| Mất xác nhận sau cam kết | Hiệu ứng đã ghi, broker không nhận xác nhận rồi giao lại. | Tìm kết quả cũ và không giữ hàng thêm. |
| Kho trạng thái lỗi | Timeout hoặc không đọc được miền quyết định chống lặp. | Không tự coi là message mới; retry hữu hạn. |
| Worker cũ còn chạy | Quyền sở hữu công việc đổi nhưng worker trước tiếp tục. | Không có hai bên cam kết hiệu ứng trái bất biến. |
| Hệ thống ngoài đã làm, phản hồi mất | Kết quả chưa rõ rồi được xác nhận muộn. | Không tạo ý định mới vì timeout; đối soát đúng. |
| Phát lại từ hàng đợi lỗi | Giao lại sau cửa sổ hiệu lực hoặc sau khi inbox được dọn. | Không tự bỏ kiểm tra; cần quy trình có thẩm quyền nếu xử lý muộn. |
| Khôi phục backup | Inbox hoặc dữ liệu khôi phục chưa phản ánh kết quả ngoài. | Đối soát trước mở xử lý, không nhân đôi hiệu ứng. |
| Sai thứ tự hoặc reset sequence | Với hồ sơ dùng số thứ tự, giao muộn hoặc thay thế thế hệ luồng. | Đúng chính sách cửa sổ và quyền reset, không tự coi mọi số là mới. |

Ví dụ ca nghiệm thu mất xác nhận:

~~~gherkin
Feature: Giao lại message không tạo thêm khoản giữ

  Scenario: Consumer đã cam kết nhưng broker chưa nhận xác nhận
    Given message hợp lệ yêu cầu giữ hai sản phẩm cho một business_operation_id
    When consumer cam kết khoản giữ cùng kết quả inbox
    And xác nhận giao nhận bị làm mất trong môi trường thử
    And broker giao lại cùng message tới một replica khác
    Then vẫn chỉ có một khoản giữ logic cho thao tác đó
    And replica tìm được biên nhận có fingerprint khớp
    And không tạo thêm outbox hoặc công việc nghiệp vụ trùng trái hợp đồng
    And audit liên kết được hai lần giao với cùng kết quả
~~~

Kiểm thử cạnh tranh phải điều khiển hoặc quan sát được điểm giữa đọc trạng thái và cam kết. Gửi các bản sao tuần tự không chứng minh an toàn trước hai replica cùng xử lý.

Cần kiểm tra dữ liệu nghiệp vụ, inbox, outbox và trạng thái bên ngoài khi có, thay vì chỉ đếm xác nhận giao nhận. Mỗi mốc lỗi phải có bằng chứng quyết định đã cam kết hay chưa.

## 11. Logging, chỉ số và điều tra

Nên phân biệt các quyết định như accepted_new, duplicate_completed, duplicate_in_progress, fingerprint_conflict, expired_new, invalid_source và dedup_unavailable.

Một sự kiện minh họa:

~~~json
{
  "event": "message_replay_decision",
  "consumer": "inventory-reservation",
  "producer": "orders-service-prod",
  "message_id": "example-message",
  "business_operation_id": "example-order-reservation",
  "decision": "duplicate_completed",
  "new_business_effect": false,
  "correlation_id": "example-correlation"
}
~~~

Đây là dữ liệu minh họa, không phải giao diện của một sản phẩm. Hệ thống thực tế cần liên kết tenant, phiên bản hồ sơ và mốc cam kết phù hợp.

Claim của message chưa xác thực phải được phân biệt với danh tính đã kiểm chứng trong log. Không để một producer_id tự khai xuất hiện như một chủ thể đã được xác nhận.

Chỉ số cần theo dõi tỷ lệ bản sao, xung đột fingerprint, message hết hạn, lỗi kho chống lặp, công việc đang xử lý quá lâu và số lần phát lại thủ công. Không dùng định danh có số lượng không giới hạn làm nhãn cho mọi metric.

Bản sao tăng có thể do broker hoặc client đang gặp lỗi, không tự chứng minh có tấn công. Ngược lại, tỷ lệ giao nhận thành công cao không chứng minh hiệu ứng không bị nhân đôi. Cần đối soát theo business_operation_id và bất biến.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Message có chữ ký nên không bị replay.” | Bản sao nguyên trạng vẫn có chữ ký đúng. | Thêm độ mới, phạm vi và trạng thái chống lặp. |
| “Có timestamp là đủ.” | Nhiều bản sao có thể cùng nằm trong cửa sổ hợp lệ. | Nhận định danh nguyên tử và giữ kết quả. |
| “Nonce ngẫu nhiên nên consumer không cần lưu.” | Bên phát lại dùng lại chính nonce đã thấy. | Ghi nhớ việc chấp nhận hoặc dùng cơ chế tương đương có chứng minh. |
| “Mỗi replica có cache chống lặp.” | Bản sao có thể đi tới replica khác hoặc cache mất khi restart. | Dùng miền quyết định chung và lưu giữ phù hợp. |
| “Đánh dấu đã xử lý rồi mới làm.” | Worker chết có thể làm mất nghiệp vụ. | Cam kết inbox và hiệu ứng nhất quán, hoặc có vòng đời công việc rõ ràng. |
| “Ack trước cho broker đỡ giao lại.” | Công việc có thể mất nếu chưa có trạng thái bền vững. | Xác định đúng mốc xác nhận và phục hồi. |
| “ID mới nghĩa là thao tác mới.” | Nhiều ID có thể biểu diễn cùng nghĩa vụ. | Có guard theo định danh nghiệp vụ. |
| “TTL hết thì được xử lý lại.” | TTL là chính sách lưu, không phải quyền tạo hiệu ứng mới. | Kiểm tra thời gian và lịch sử nghiệp vụ. |
| “Requeue là làm mới message.” | Có thể bỏ qua thời hạn và mất nguồn gốc. | Giữ envelope hoặc phát yêu cầu mới qua quy trình có thẩm quyền. |
| “Sequence lớn hơn là luôn đúng.” | Có thể bỏ message đến muộn hoặc chấp nhận reset trái phép. | Đặc tả luồng, thế hệ và cửa sổ thứ tự. |

## 13. Duy trì yêu cầu trong vòng đời phát triển

Khi phân tích nghiệp vụ, xác định hiệu ứng nào chỉ được thực hiện một lần và thao tác điều chỉnh nào thực sự là công việc mới. Phân biệt message logic với lần giao ở tầng truyền.

Khi mô hình hóa đe dọa, đưa vào sao chép message hợp lệ, cạnh tranh nhiều replica, đổi định danh, lỗi xác nhận, kho chống lặp không khả dụng và phát lại có đặc quyền.

Khi thiết kế, gắn SR-RP với điểm kiểm chứng envelope, miền quyết định chống lặp, đơn vị giao dịch, guard nghiệp vụ và quy trình đối soát. Nếu có nhiều consumer hoặc nhiều hệ thống, nêu bảo đảm tại từng ranh giới.

Khi phát triển và nghiệm thu, kiểm tra cả bản sao hợp lệ, xung đột nội dung và lỗi từng phần. Khi vận hành, theo dõi công việc chưa rõ và quyền phát lại; thay đổi TTL, broker, audience, số replica hoặc cách lưu inbox cần đánh giá lại.

Bài tập áp dụng: một dịch vụ xử lý sự kiện cấp điểm thưởng cho đơn hàng và có công cụ phát lại từ hàng đợi lỗi. Hãy viết envelope được bảo vệ, phạm vi khóa chống lặp, cửa sổ thời gian, thời hạn lưu, guard theo đơn hàng và quy trình xử lý muộn. Nêu ca thử khi mất xác nhận sau ghi điểm, hai replica nhận bản sao cùng lúc và message được phát lại sau khi inbox đã hết thời hạn lưu.

