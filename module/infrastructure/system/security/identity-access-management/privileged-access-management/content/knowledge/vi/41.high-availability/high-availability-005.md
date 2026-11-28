# KMS dependency: thiết kế PAM sẵn sàng cao khi phụ thuộc dịch vụ quản lý khóa

## 1. Mục tiêu và phạm vi

Một hệ thống Privileged Access Management (PAM) có thể có nhiều vault node, nhiều session broker và cơ sở dữ liệu sao chép, nhưng vẫn không cấp được credential nếu mọi node cùng cần giải mã bằng một dịch vụ quản lý khóa đang gián đoạn. Đếm số máy chủ PAM không đủ để kết luận hệ thống đã có high availability (HA).

Bài học này phân tích **KMS dependency**: sự phụ thuộc của PAM vào Key Management Service (KMS) trong các thao tác bảo vệ dữ liệu và vận hành quyền đặc biệt. Trọng tâm là nhận diện đường phụ thuộc, xác định hành vi khi lỗi và thiết kế phục hồi mà vẫn giữ được ranh giới bảo mật.

Sau bài học, bạn có thể:

- Chỉ ra thao tác PAM nào cần gọi KMS ngay và thao tác nào có thể tiếp tục với trạng thái hợp lệ đã có.
- Phân biệt HA của vault với HA của khóa, quyền sử dụng khóa và các dịch vụ hỗ trợ KMS.
- Đặt timeout, retry, circuit breaker và giới hạn cache theo từng thao tác.
- Thiết kế failover, rotation và backup có kiểm chứng khả năng giải mã.
- Xây dựng diễn tập mất KMS, mất quyền, mất vùng và phục hồi khóa.

Các tên khóa, số liệu và sơ đồ trong bài là ví dụ thiết kế giả định, không phải mặc định của một sản phẩm. KMS ở đây có thể là dịch vụ managed hoặc nền tảng do tổ chức vận hành; tính năng sao chép khóa, chuyển vùng và quản lý phiên bản phải được xác minh trên triển khai thực tế.

## 2. Hiểu đúng vai trò của KMS trong PAM

### 2.1. KMS, HSM và vault không phải cùng một thành phần

**Vault** quản lý secret, credential, policy và quy trình cấp quyền. **KMS** cung cấp giao diện quản lý và sử dụng khóa mật mã, chẳng hạn mã hóa, giải mã, bọc khóa hoặc mở khóa đã bọc. **Hardware Security Module (HSM)** là thành phần bảo vệ và thực hiện các thao tác mật mã trong một ranh giới phần cứng; một KMS có thể sử dụng HSM ở bên dưới.

Ba khái niệm này mô tả các trách nhiệm khác nhau. Có HSM không tự giải quyết lỗi DNS, sai quyền truy cập KMS hay cạn quota API. Có KMS nhiều vùng cũng không tự bảo đảm rằng vault đã sao chép dữ liệu, workload có danh tính hợp lệ ở vùng dự phòng hoặc ứng dụng chọn đúng khóa.

Tùy kiến trúc, PAM có thể dùng KMS để:

| Chức năng | Cách phụ thuộc có thể gặp | Hậu quả khi không thực hiện được |
|---|---|---|
| Khởi động hoặc mở trạng thái khóa của vault | Mở khóa gốc hoặc khóa trung gian | Node mới không đạt trạng thái phục vụ |
| Đọc credential mã hóa | Mở DEK hoặc giải mã trực tiếp | Không cung cấp được credential mới |
| Ghi secret hoặc kết quả rotation | Tạo, bọc hoặc sử dụng khóa | Không lưu được bản credential mới một cách an toàn |
| Ghi bản ghi phiên, backup | Bọc khóa mã hóa cho đối tượng mới | Không hoàn thành được dữ liệu bảo vệ theo policy |
| Ký dữ liệu hay bằng chứng | Gọi thao tác ký bằng khóa được quản lý | Không phát hành được đối tượng cần chữ ký |
| Quản lý vòng đời khóa | Tạo phiên bản, đổi quyền, vô hiệu hóa | Ảnh hưởng hoạt động quản trị và phục hồi |

Không phải sản phẩm PAM nào cũng dùng KMS cho tất cả các mục trên. Bản đồ phụ thuộc phải xuất phát từ luồng xử lý thực tế và được kiểm chứng bằng thử nghiệm, không dựa vào tên thành phần.

### 2.2. Envelope encryption và điểm KMS nằm trên đường xử lý

Trong một thiết kế envelope encryption điển hình:

1. Một Data Encryption Key (DEK) mã hóa dữ liệu secret.
2. Một Key Encryption Key (KEK) do KMS quản lý bọc DEK.
3. Vault lưu ciphertext, DEK đã bọc và metadata cần thiết.
4. Khi đọc, một thành phần được cấp quyền gọi KMS để mở DEK.
5. Thành phần đó dùng DEK để giải mã dữ liệu trong bộ nhớ theo phạm vi đã cho phép.

~~~mermaid
flowchart LR
    U["Yêu cầu đọc credential"] --> P["PAM kiểm tra quyền và phê duyệt"]
    P --> V["Đọc ciphertext và DEK đã bọc"]
    V --> K["KMS: mở DEK"]
    K --> M["DEK trong bộ nhớ được bảo vệ"]
    M --> D["Giải mã credential"]
    D --> B["Broker sử dụng credential cho phiên được phép"]
~~~

KMS không nhất thiết nhận toàn bộ dữ liệu credential. Tuy nhiên, thao tác mở DEK có thể nằm trên đường xử lý bắt buộc của việc đọc dữ liệu.

Một node PAM đã mở khóa không đồng nghĩa mọi secret đều có thể đọc khi KMS mất. Node có thể chỉ giữ một khóa trung gian, có thể cần KMS cho mỗi đối tượng hoặc có thể đã hết thời gian lưu DEK. Cần trả lời bằng dữ liệu quan sát: **thao tác nào gọi KMS, với tần suất nào, dùng loại khóa nào và còn tiếp tục được bao lâu khi mất kết nối?**

## 3. Vẽ đầy đủ đồ thị phụ thuộc

### 3.1. Phụ thuộc trực tiếp và phụ thuộc hỗ trợ

Đường gọi KMS thường cần nhiều điều kiện cùng đúng:

~~~mermaid
flowchart TD
    P["PAM workload"] --> I["Danh tính và token hợp lệ"]
    P --> D["DNS và định tuyến"]
    P --> T["TLS, CA và thời gian hệ thống"]
    P --> N["Đường mạng, proxy hoặc endpoint riêng"]
    P --> E["Endpoint KMS"]
    I --> A["Quyền sử dụng đúng khóa"]
    N --> E
    E --> Q["Quota và năng lực xử lý"]
    E --> K["Khóa, phiên bản và backend mật mã sẵn sàng"]
~~~

Đây là đồ thị trách nhiệm, không phải khẳng định mọi sản phẩm có đúng các thành phần như nhau. Ví dụ, một triển khai dùng token ngắn hạn sẽ phụ thuộc vào khả năng cấp mới token; triển khai khác dùng chứng chỉ client sẽ có thêm vòng đời chứng chỉ tương ứng.

Những lỗi dễ bị bỏ sót gồm:

- Token hiện tại còn dùng được, nhưng dịch vụ cấp token hỏng khiến node thất bại sau lần gia hạn tiếp theo.
- KMS hoạt động bình thường, nhưng private endpoint hoặc tuyến mạng của vùng PAM bị lỗi.
- Node mới không có trust store, quyền hoặc cấu hình khóa giống node đang chạy.
- Tất cả node dùng chung một proxy, DNS resolver hoặc tài khoản dịch vụ bị vô hiệu hóa.
- Key policy thay đổi, trong khi health check vẫn chỉ kiểm tra cổng TCP.
- KMS còn hoạt động nhưng quota bị dùng hết bởi rotation, backup hoặc quá trình phục hồi.
- Bản sao ciphertext đã đến vùng dự phòng nhưng khóa hoặc điều kiện truy cập khóa chưa có ở đó.

### 3.2. Tránh vòng phụ thuộc khi khởi động

Một vòng phụ thuộc nguy hiểm là:

~~~text
PAM cần KMS để mở khóa vault
KMS client cần credential đang được lưu trong vault đó
~~~

Khi cả hai cùng khởi động lại, không thành phần nào lấy được đầu vào cần thiết. Quy trình bootstrap phải có gốc tin cậy độc lập, được quản lý rõ ràng.

Một lựa chọn có thể là workload identity do hạ tầng cung cấp, với quyền tối thiểu để sử dụng đúng khóa cần cho bootstrap. Một lựa chọn khác là cơ chế phục hồi được thiết kế và kiểm soát riêng. Không nên giải quyết vòng phụ thuộc bằng cách đặt credential quản trị KMS dài hạn vào file cấu hình không được bảo vệ.

Tài liệu bootstrap cần chỉ ra ai cấp danh tính, ai phê duyệt quyền, dữ liệu nào được dùng trước khi vault mở và bằng cách nào thu hồi đường truy cập đó. Tài khoản phục hồi cũng cần tránh phụ thuộc vào chính PAM đang mất khả năng phục vụ.

## 4. Đặt mục tiêu sẵn sàng theo thao tác, không theo nhãn hệ thống

### 4.1. Thời gian đáp ứng và ngân sách phụ thuộc

Với một thao tác đọc secret cần KMS, có thể ước lượng ngân sách độ trễ:

~~~text
T_yêu_cầu =
    T_xác_thực_và_policy
  + T_đọc_vault
  + T_KMS
  + T_xử_lý_và_trả_kết_quả
~~~

Nếu thời hạn toàn yêu cầu là 2 giây, không thể cho mỗi lần gọi KMS timeout 2 giây rồi retry ba lần. Timeout, thời gian chờ kết nối, backoff và số lần thử đều phải nằm trong thời hạn còn lại của yêu cầu.

Ví dụ giả định:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Xác thực, policy và phê duyệt đã có | 250 ms |
| Đọc dữ liệu vault | 150 ms |
| Tổng thời gian cho KMS, gồm cả retry nếu có | 900 ms |
| Giải mã, kiểm tra và trả kết quả | 200 ms |
| Dự phòng cho dao động và hàng đợi | 500 ms |
| Tổng | 2.000 ms |

Đây là phân bổ thiết kế cần đo lại bằng tải thực tế. Độ trễ p95 hoặc p99 của từng thành phần không cộng cơ học thành p95 hay p99 của toàn hệ thống; tương quan lỗi và hàng đợi có thể làm phần đuôi xấu hơn đáng kể.

### 4.2. SLO phải thể hiện đúng khả năng phục vụ

Tách riêng ít nhất các luồng:

- Cấp credential mới cho một yêu cầu đã được phê duyệt.
- Tạo phiên đặc quyền mới.
- Duy trì và kiểm soát phiên đang hoạt động.
- Rotation credential và lưu kết quả.
- Khởi động hoặc thay thế node PAM.
- Khôi phục vault từ backup.

Một phiên SSH đang chạy có thể chưa cần KMS trong một khoảng thời gian, trong khi node vault mới không thể mở khóa. Báo cáo “PAM vẫn hoạt động” chỉ từ việc phiên cũ chưa rớt sẽ che khuất việc không thể cấp phiên mới hoặc thay thế node lỗi.

Cũng không được tính mọi yêu cầu bị từ chối là thành công bảo mật rồi loại khỏi SLO. Một yêu cầu hợp lệ bị từ chối do dependency hỏng là lỗi khả dụng của luồng tương ứng; yêu cầu thật sự không được phép là kết quả policy bình thường. Cách phân loại phải được định nghĩa trước.

### 4.3. RTO và RPO phải bao gồm khả năng giải mã

RTO của PAM không chỉ là thời gian dựng lại cơ sở dữ liệu. Nó còn gồm thời gian có lại đường mạng KMS, danh tính, quyền dùng khóa và khả năng mở dữ liệu cần thiết.

RPO dữ liệu bằng không không bảo đảm phục hồi thành công nếu khóa tương ứng đã mất hoặc bị hủy. Với dữ liệu đã bọc khóa, điều kiện phục hồi tối thiểu là:

~~~text
Có ciphertext đúng phiên bản
AND có DEK đã bọc cùng metadata tương ứng
AND còn khóa/phiên bản có thể mở DEK đó
AND có quyền và đường truy cập thực hiện thao tác
~~~

Cơ chế sao lưu khóa phụ thuộc loại KMS/HSM và chính sách triển khai. Một số khóa không thể xuất ra ngoài. Khi đó phải thiết kế theo cơ chế khôi phục hoặc sao chép được hỗ trợ, không giả định sẽ luôn tạo được một bản sao khóa thủ công.

## 5. Phân loại sự cố trước khi quyết định retry hoặc failover

Một chuỗi lỗi “decrypt failed” có thể xuất phát từ nhiều nguyên nhân với cách xử lý khác nhau.

| Nhóm lỗi | Ví dụ | Xử lý ưu tiên |
|---|---|---|
| Mạng hoặc dịch vụ tạm thời | Mất kết nối, timeout, dịch vụ quá tải | Retry có giới hạn; kiểm tra sức khỏe đường gọi |
| Hạn mức | Throttling, vượt quota | Giảm tải, backoff, ưu tiên luồng quan trọng |
| Danh tính | Token hết hạn, không cấp mới được token | Kiểm tra luồng danh tính; tránh lặp vô hạn |
| Phân quyền | Workload không còn quyền trên khóa | Xác minh thay đổi policy; không tự tăng quyền |
| Trạng thái khóa | Khóa bị vô hiệu hóa hoặc đang trong quy trình hủy | Chặn thao tác liên quan; chuyển đúng người có thẩm quyền |
| Sai dữ liệu hoặc ngữ cảnh | Nhầm khóa, thiếu context, ciphertext bị hỏng | Kiểm tra tính toàn vẹn và mapping; không đổi khóa ngẫu nhiên |
| Cấu hình | Sai endpoint, vùng, trust store | Sửa theo cấu hình đã xác minh |
| Lỗi ứng dụng | Dùng sai phiên bản hoặc bỏ mất metadata | Xử lý tính nhất quán; tránh retry gây thêm tải |

**Timeout không chứng minh thao tác chưa được thực hiện.** Với thao tác quản trị có thay đổi trạng thái, hệ thống phải có cách truy vấn lại hoặc đối chiếu trước khi gửi lại. Với thao tác đọc/giải mã, retry vẫn phải tuân thủ thời hạn và không tạo thêm bản ghi nhạy cảm.

Thất bại do quyền hoặc khóa vô hiệu hóa không nên tự động kích hoạt chuyển sang một credential KMS mạnh hơn. Điều đó có thể làm mất tác dụng của một hành động thu hồi hợp lệ.

## 6. Xác định hành vi khi KMS không dùng được

### 6.1. Fail-closed không đồng nghĩa mọi luồng cùng dừng tức thì

Fail-closed nghĩa là không cho phép một thao tác vượt qua kiểm soát bắt buộc chỉ vì thành phần phụ thuộc đang lỗi. Nó không tự quyết định rằng tất cả phiên đang chạy phải bị ngắt trong cùng một thời điểm.

Cần định nghĩa riêng từng trường hợp:

| Thao tác | Có thể tiếp tục khi nào? | Khi không đủ điều kiện |
|---|---|---|
| Đọc credential mới | Có khóa trong cache hợp lệ, policy cho phép và mọi điều kiện cấp quyền còn hiệu lực | Từ chối hoặc trả lỗi tạm thời có kiểm soát |
| Cấp phiên mới | Đủ xác thực, phê duyệt, credential và yêu cầu giám sát theo policy | Không tạo phiên thiếu kiểm soát bắt buộc |
| Phiên đang chạy | Còn thời hạn và còn các kiểm soát mà phiên đó bắt buộc duy trì | Chuyển trạng thái, hạn chế hoặc chấm dứt theo policy |
| Ghi dữ liệu mã hóa mới | Có cơ chế mã hóa và lưu bền vững hợp lệ | Không ghi plaintext thay thế |
| Rotation | Có thể hoàn tất và lưu credential mới một cách an toàn | Hoãn trước điểm thay đổi hoặc xử lý trạng thái chưa xác định |
| Khởi động node | Bootstrap và điều kiện mở khóa đều hợp lệ | Giữ node ngoài nhóm nhận yêu cầu |

Một cache DEK hợp lệ chỉ giải quyết nhu cầu mật mã tương ứng. Nó không thay thế xác thực, JIT/JEA, phê duyệt, thời hạn phiên hay kiểm tra tài khoản bị thu hồi.

### 6.2. Trạng thái đã giải mã không tự bị thu hồi bởi KMS

Vô hiệu hóa một khóa KMS có thể ngăn các lần sử dụng khóa tiếp theo tại KMS. Nó không tự xóa DEK đang nằm trong RAM, credential đã được cấp hay phiên đã đăng nhập vào hệ đích.

Vì vậy, khi sự cố có yếu tố xâm nhập hoặc thu hồi quyền khẩn cấp, cần kết hợp:

- Vô hiệu hóa hoặc hạn chế danh tính bị ảnh hưởng.
- Xóa cache bằng cơ chế ứng dụng hỗ trợ và kiểm soát node liên quan.
- Thu hồi lease, token hoặc credential theo khả năng của hệ đích.
- Chấm dứt phiên đặc quyền theo policy.
- Rotation và kiểm tra các đường truy cập khác.

Không được hứa rằng TTL của cache khóa cũng là thời hạn tối đa của mọi quyền đã cấp. Hai thời hạn này có thể khác nhau và cần kiểm soát riêng.

## 7. Cache khóa: tăng khả dụng nhưng làm thay đổi mô hình rủi ro

### 7.1. Phân biệt loại dữ liệu được cache

Cache DEK trong bộ nhớ, cache ciphertext, cache credential plaintext và cache kết quả phê duyệt có rủi ro khác nhau. Đánh giá một loại không thể thay thế đánh giá các loại còn lại.

Ví dụ, cache ciphertext có thể giảm tải storage nhưng vẫn cần KMS để giải mã. Cache DEK có thể giảm số lần gọi KMS, song tăng thời gian khóa plaintext tồn tại trong tiến trình. Cache credential có thể duy trì khả năng đăng nhập ngay cả sau khi không còn gọi KMS, nhưng mở rộng phạm vi dữ liệu nhạy cảm phải bảo vệ.

Bài học ưu tiên phân tích cache DEK vì nó nằm trực tiếp ở ranh giới KMS. Nếu sản phẩm PAM không hỗ trợ cache an toàn hoặc không cho cấu hình các giới hạn cần thiết, không tự xây cache plaintext để lấp chỗ trống.

### 7.2. Hợp đồng cache cần rõ ràng

Một cache khóa được thiết kế có chủ đích cần xác định:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Phạm vi | Khóa được dùng cho tenant, vault, đối tượng hoặc phiên bản nào? |
| Cache key | Có phân biệt đúng định danh khóa, DEK đã bọc và ngữ cảnh mật mã không? |
| Thời gian | TTL tối đa, thời điểm bắt đầu và điều kiện hết hạn là gì? |
| Mức sử dụng | Có giới hạn số lần dùng hoặc lượng dữ liệu nếu thiết kế mật mã yêu cầu không? |
| Thu hồi | Khi policy hoặc trạng thái khóa thay đổi, cache bị vô hiệu hóa bằng cách nào? |
| Nơi lưu | Chỉ trong tiến trình hay có bản sao khác? Có nguy cơ vào swap, dump hoặc log không? |
| Cô lập | Node, tenant và môi trường có dùng chung cache không? |
| Khi đầy | Loại bỏ mục nào; có tạo đột biến gọi KMS không? |
| Khi hết hạn | Có từ chối đúng lúc hay tự kéo dài vì KMS đang lỗi? |
| Khi restart | Cold start cần bao nhiêu lời gọi KMS và có giới hạn tốc độ không? |

Không nên dùng cache key chỉ gồm alias dễ thay đổi. Cache phải giữ được mối liên hệ với đúng vật liệu khóa/phiên bản và ciphertext hoặc khóa đã bọc tương ứng. Nếu hệ thống sử dụng encryption context hoặc authenticated additional data, việc so khớp phải bảo toàn ngữ cảnh đó và không trộn dữ liệu giữa các phạm vi.

Thông tin context thường không nên chứa secret; mức độ hiển thị của nó trong audit hoặc API cần được xác minh theo KMS thực tế.

### 7.3. Không kéo dài TTL tùy tiện để “cứu” sự cố

Giả sử TTL tối đa là 5 phút và một DEK đã ở cache 4 phút 50 giây khi mất KMS. Mục đó chỉ còn tối đa 10 giây theo hợp đồng hiện tại, không tự có thêm 5 phút.

Thời gian tiếp tục phục vụ của toàn hệ thống cũng không bằng TTL tối đa: các mục có tuổi khác nhau, node có cache khác nhau, và yêu cầu có thể nhắm tới đối tượng chưa từng được mở khóa.

Nếu có chế độ degraded được phê duyệt trước, giới hạn của chế độ đó phải rõ và đo được. Không để mã xử lý lỗi tự gia hạn vô hạn, lấy khóa từ node khác không qua kiểm soát hoặc lưu cache ra đĩa để tránh cold start.

Trong các runtime có cơ chế garbage collection, việc xóa tham chiếu không bảo đảm mọi bản sao khóa lập tức biến mất khỏi RAM. Giảm thời gian sống, hạn chế sao chép, quản lý core dump và dùng primitive bảo vệ bộ nhớ phù hợp vẫn là trách nhiệm của triển khai.

## 8. Timeout, retry, circuit breaker và hàng đợi

### 8.1. Retry theo thời hạn còn lại

Một cấu trúc xử lý khái niệm:

~~~text
handle(request):
    authorization = authorize_current_request(request)
    if authorization is not valid:
        deny

    cache_entry = find_exact_key_cache_entry(request)
    if cache_entry satisfies cache_policy:
        return decrypt_and_complete_under_current_policy(cache_entry)

    if request has insufficient remaining_time:
        return dependency_unavailable

    if circuit_breaker refuses this dependency partition:
        return dependency_unavailable

    repeat within remaining_time and bounded_attempts:
        result = call_kms_with_bounded_timeout()

        if result is success:
            validate_response_and_binding()
            cache_only_if_policy_allows()
            return decrypt_and_complete_under_current_policy(result)

        if result is not a retryable_failure:
            return classified_failure

        wait randomized_backoff_that_fits_remaining_time

    return dependency_unavailable
~~~

Đây là mã giả về thứ tự quyết định, không phải implementation dùng trực tiếp. Việc hoàn thành yêu cầu vẫn phải kiểm tra các điều kiện có thể hết hiệu lực trong lúc chờ theo policy của hệ thống. Không ghi DEK, credential hoặc toàn bộ phản hồi KMS vào log để chẩn đoán lỗi.

Nếu client library đã retry, lớp ứng dụng cần biết tổng số lần thử thực tế. Ba lớp mỗi lớp retry ba lần có thể nhân số lời gọi và kéo dài độ trễ vượt dự kiến.

### 8.2. Circuit breaker phải có phạm vi phù hợp

Circuit breaker giúp ngăn một dependency đang lỗi bị gọi liên tục. Tuy nhiên, nếu mọi lỗi của mọi khóa dùng chung một breaker, việc một khóa bị từ chối quyền có thể làm ngừng cả các tenant không liên quan.

Có thể phân vùng breaker theo endpoint, vùng hoặc lớp thao tác, kết hợp xử lý lỗi theo khóa khi cần. Cách chia phải tránh cả hai cực: phạm vi quá rộng gây ảnh hưởng dây chuyền, hoặc quá nhỏ tạo quá nhiều trạng thái và vẫn làm quá tải dịch vụ.

Các lần thăm dò half-open cần có giới hạn. Khi dependency trở lại, không đồng loạt mở toàn bộ hàng đợi và làm dịch vụ sụp lần nữa.

### 8.3. Hàng đợi là bộ đệm có giới hạn

Mỗi yêu cầu chờ cần có thời hạn, giới hạn dung lượng và quy tắc ưu tiên. Không đưa credential plaintext hoặc DEK vào một hàng đợi bền vững không được thiết kế để bảo vệ chúng.

Các công việc như backup hoặc rewrap có thể hoãn theo policy để nhường quota cho thao tác cấp quyền quan trọng. Tuy nhiên, việc hoãn không được âm thầm vượt thời hạn rotation bắt buộc. Khi không thể đồng thời đáp ứng các mục tiêu, hệ thống cần thể hiện trạng thái suy giảm và gọi đúng người xử lý.

## 9. Failover KMS trong kiến trúc nhiều vùng

### 9.1. Chuyển endpoint không đồng nghĩa chuyển được khóa

Để một vùng dự phòng giải mã dữ liệu hiện có, phải đồng thời có:

1. Dữ liệu ciphertext và DEK đã bọc tương ứng.
2. Khóa tương thích với dữ liệu đó theo cơ chế được hỗ trợ.
3. Mapping đúng giữa dữ liệu và khóa/phiên bản.
4. Danh tính workload và quyền sử dụng khóa tại vùng dự phòng.
5. Đường mạng, DNS, TLS và quota đủ cho tải phục hồi.
6. Chính sách ứng dụng cho phép thực hiện thao tác ở vùng đó.

Hai khóa có cùng tên hoặc alias không có nghĩa là cùng vật liệu mật mã. Tạo một khóa mới rồi gắn alias cũ không làm khóa mới giải mã được DEK đã bọc bằng khóa cũ.

Không phải mọi KMS đều có cùng cơ chế multi-region. Có hệ thống hỗ trợ quan hệ khóa sao chép cụ thể; có hệ thống cần bọc DEK cho nhiều khóa; có hệ thống phải phục hồi qua quy trình HSM chuyên biệt. Thiết kế cần dựa trên khả năng được hỗ trợ và thử nghiệm giải mã thực tế.

### 9.2. Hai mô hình cần phân biệt

| Mô hình khái niệm | Điều kiện chính | Điểm phải kiểm chứng |
|---|---|---|
| Khóa sao chép hoặc khóa liên vùng được nền tảng hỗ trợ | Cơ chế mật mã và quan hệ khóa tương thích | Trạng thái từng vùng, policy, quyền, dữ liệu và thời gian chuyển |
| Nhiều bản DEK được bọc bằng các khóa độc lập | Mỗi đối tượng có đủ các envelope cần thiết | Ghi nhất quán, quản lý mapping, mở rộng ranh giới giải mã |

Ở mô hình thứ hai, một secret có thể đi kèm một DEK được bọc riêng cho vùng A và vùng B. Điều này mở thêm đường giải mã, vì vậy phải đánh giá quyền và phạm vi xâm nhập, không chỉ lợi ích HA.

Nếu policy yêu cầu dữ liệu mới phải phục hồi được ở cả hai vùng, ứng dụng không được báo ghi thành công chỉ sau khi tạo envelope vùng A. Nếu policy cho phép độ trễ bảo vệ vùng B, phải có trạng thái “chưa được bảo vệ đầy đủ”, hạn RPO rõ ràng và quy trình xử lý trước khi coi bản sao đó sẵn sàng cho DR.

### 9.3. Kịch bản chuyển vùng có kiểm soát

Một runbook có thể gồm:

1. Phân loại lỗi: endpoint vùng A gián đoạn hay khóa/danh tính bị thu hồi vì an ninh.
2. Xác minh vùng B có thể mở một đối tượng kiểm tra đã biết bằng đúng đường truy cập dự kiến.
3. Kiểm tra dữ liệu được phép phục hồi và tình trạng rotation đang dở.
4. Chọn đường xử lý vùng B theo policy đã duyệt, áp dụng giới hạn tốc độ.
5. Đo tỷ lệ thành công, độ trễ, throttling và mức đầy hàng đợi.
6. Dừng hoặc rollback chuyển vùng nếu xuất hiện lỗi mapping, thiếu dữ liệu hay nguy cơ cấp sai credential.
7. Sau sự cố, xác minh điều kiện quay về và tránh làm hai vùng đồng thời ghi xung đột.

Một hành động thu hồi khóa có chủ đích không được coi như lỗi mạng để tự động đi vòng qua bằng khóa dự phòng. Ý nghĩa của thu hồi phải được thiết kế xuyên vùng ngay từ đầu.

## 10. Vòng đời khóa và rotation credential là hai chuỗi khác nhau

### 10.1. Không nhầm rotation KEK với rotation mật khẩu

Rotation credential thay đổi bí mật được hệ đích chấp nhận, ví dụ mật khẩu tài khoản quản trị. Rotation KEK thay đổi khóa dùng để bảo vệ DEK hoặc dữ liệu. Một việc không tự thực hiện việc còn lại.

Khi KMS tạo phiên bản khóa mới, dữ liệu cũ có thể vẫn cần phiên bản cũ để giải mã. Một số nền tảng tự lưu thông tin phiên bản trong ciphertext; nền tảng khác cần metadata bổ sung. Không xóa phiên bản cũ chỉ vì việc tạo phiên bản mới đã thành công.

Rewrap là bọc lại DEK bằng khóa hoặc phiên bản khác. Tùy cơ chế, nó có thể không cần mã hóa lại toàn bộ dữ liệu, nhưng vẫn phải bảo toàn ciphertext, context và mapping. Thao tác đó tạo tải KMS và cần tiến độ có thể tiếp tục sau gián đoạn.

### 10.2. Rotation credential có điểm không thể chỉ retry mù

Xét chuỗi thao tác:

~~~text
Tạo credential mới
    -> thay credential tại hệ đích
    -> mã hóa và lưu credential mới vào vault
    -> xác minh đăng nhập
    -> công bố phiên bản đang hiệu lực
~~~

Nếu hệ đích đã nhận credential mới nhưng KMS lỗi trước khi vault lưu bền vững, PAM có thể mất thông tin đăng nhập hiện tại. Không có giao dịch nguyên tử mặc định giữa KMS, vault và một hệ đích bất kỳ.

Thiết kế quy trình cần xác định trước:

- Bước nào có thể chuẩn bị và bảo vệ dữ liệu trước khi thay đổi hệ đích.
- Khi nào được công bố một phiên bản credential là đang hiệu lực.
- Cách ghi trạng thái công việc mà không để lộ secret.
- Cách lưu an toàn credential mới trong giai đoạn chuyển tiếp nếu cần.
- Cách xác minh hệ đích chấp nhận credential nào sau timeout.
- Cơ chế idempotency hoặc đối chiếu mà hệ đích thực sự hỗ trợ.
- Trường hợp nào cần tài khoản phục hồi độc lập hoặc can thiệp có kiểm soát.

Không coi một thao tác “thay mật khẩu” bất kỳ là idempotent. Gửi lại có thể tạo một giá trị khác, tăng version hoặc làm thay đổi trạng thái ngoài dự kiến.

Nếu chưa thay đổi hệ đích và KMS đang lỗi, hoãn rotation thường dễ kiểm soát hơn. Nếu đã vượt điểm thay đổi mà chưa biết kết quả, phải đưa công việc vào trạng thái cần đối chiếu; không tự trả về “rotation thành công” và cũng không tiếp tục cấp credential cũ chỉ vì nó còn trong cache.

## 11. Backup, xóa khóa và phục hồi

### 11.1. Backup cần lưu mối liên hệ mật mã

Bản backup cần giữ đủ dữ liệu và metadata để phục hồi, ví dụ:

- Ciphertext và DEK đã bọc.
- Định danh và thông tin phiên bản khóa khi cần.
- Thông tin thuật toán, định dạng và context cần cho giải mã.
- Phiên bản secret và mối liên hệ với credential ở hệ đích.
- Thông tin kiểm tra tính toàn vẹn và manifest phù hợp.

Không đưa khóa plaintext vào manifest để làm cho bản backup “tự giải mã được”. Với cơ chế envelope encryption, việc tách dữ liệu và quyền mở khóa là một phần ranh giới bảo vệ cần duy trì.

Manifest cũng không thay thế việc kiểm tra restore. Một tập hợp file đọc được trên storage có thể vẫn thiếu key version cần thiết.

### 11.2. Xóa khóa phải tính đến dữ liệu lịch sử

Trước khi hủy một khóa hoặc phiên bản, cần kiểm kê không chỉ secret hiện tại mà cả:

- Backup còn thời hạn lưu giữ.
- Bản ghi phiên và bằng chứng kiểm toán.
- Bản sao DR chưa rewrap.
- Snapshot cơ sở dữ liệu và dữ liệu lưu trữ lâu dài.
- Các đối tượng đang trong quy trình chuyển khóa.

Nếu một khóa là đường giải mã duy nhất và đã bị hủy không thể phục hồi, tạo khóa mới cùng tên không khôi phục được dữ liệu. Vì vậy, quyền hủy khóa, kiểm soát phê duyệt và thời gian chờ nếu nền tảng hỗ trợ cần được thiết kế theo mức rủi ro.

Khôi phục một snapshot cũ cũng có thể làm quay về metadata trỏ tới khóa cũ. Cần kiểm tra khả năng giải mã của đúng thời điểm backup, không chỉ đối tượng được tạo sau lần rotation gần nhất.

### 11.3. Break-glass không phải plaintext fallback

Một cơ chế khẩn cấp phù hợp phải được thiết kế trước, có phạm vi, danh tính độc lập, kiểm soát phê duyệt, thời hạn và bằng chứng. Tùy hạ tầng, nó có thể phục hồi đường KMS hoặc dùng một đường quản trị hệ đích riêng đã được phê duyệt.

Cơ chế đó không được ngầm trở thành:

- Bản sao toàn bộ mật khẩu quản trị dạng plaintext.
- Quyền quản trị KMS thường trực cấp cho mọi node PAM.
- Tự tắt mã hóa khi dependency lỗi.
- Cho phép đăng nhập mà không lưu được bằng chứng bắt buộc theo policy.
- Bỏ qua một quyết định thu hồi đang có hiệu lực.

Bài diễn tập phải kiểm tra cả việc đóng đường khẩn cấp và rotation sau sử dụng, không chỉ kiểm tra mở được quyền.

## 12. Năng lực xử lý và tải phục hồi

### 12.1. Ước lượng nhu cầu gọi KMS

Một mô hình đơn giản:

~~~text
Q_KMS = Q_đọc_cần_mở_khóa
      + Q_ghi_và_bọc_khóa
      + Q_rotation
      + Q_backup_và_rewrap
      + Q_bootstrap_và_phục_hồi
~~~

Nếu mỗi cache miss cần một lần mở DEK, có thể ước lượng:

~~~text
Q_đọc_cần_mở_khóa ≈ R_yêu_cầu_đọc × (1 - tỷ_lệ_cache_hit)
~~~

Công thức này chỉ đúng dưới các giả định đó; phải cộng thêm lời gọi nếu một yêu cầu mở nhiều khóa hoặc thực hiện thao tác khác.

Ví dụ, hệ thống có 200 yêu cầu đọc mỗi giây và cache hit 95% thì tải mở DEK ước tính là 10 lời gọi mỗi giây. Khi toàn bộ node restart, cache hit có thể gần 0%, khiến riêng tải đọc tăng tới khoảng 200 lời gọi mỗi giây trước cả retry, bootstrap và rotation.

Năng lực cần được kiểm tra theo quota thực tế của đúng khóa, danh tính, endpoint hoặc tài khoản, tùy cách nền tảng giới hạn. Con số tổng của dịch vụ không bảo đảm một workload được dùng toàn bộ phần đó.

### 12.2. Tránh thundering herd

Để hạn chế việc nhiều node cùng gọi KMS sau phục hồi:

- Khởi động và đưa node vào phục vụ theo từng nhóm.
- Giới hạn số yêu cầu KMS đồng thời.
- Gộp các yêu cầu đồng thời cần cùng một khóa nếu triển khai hỗ trợ an toàn.
- Áp dụng backoff có jitter.
- Điều tiết tác vụ nền như rewrap và backup.
- Giới hạn hàng đợi và trả lỗi rõ khi hết ngân sách.
- Dành năng lực cho luồng phục hồi và thao tác ưu tiên theo policy.

Không giảm tải bằng cách chia sẻ khóa plaintext giữa các node qua một kênh tự phát. Một thay đổi như vậy tạo thêm dependency và mở rộng ranh giới khóa cần đánh giá riêng.

Health check cũng tiêu thụ quota nếu thực hiện thao tác mật mã. Tần suất và phạm vi kiểm tra cần đủ phát hiện lỗi nhưng không tự tạo đợt quá tải.

## 13. Quan sát và diễn tập

### 13.1. Chỉ số và bằng chứng cần thu thập

Theo dõi ít nhất:

| Tín hiệu | Ý nghĩa vận hành |
|---|---|
| Tỷ lệ thành công của từng thao tác KMS | Phân biệt decrypt, wrap, ký và quản trị khóa |
| Độ trễ và timeout | Nhận diện suy giảm trước khi mất hoàn toàn |
| Throttling và số lần retry thực tế | Phát hiện tải khuếch đại |
| Lỗi danh tính và quyền | Phân biệt mất khả dụng với quyết định truy cập |
| Cache hit, miss, tuổi mục và hết hạn | Ước lượng cửa sổ tiếp tục phục vụ |
| Node chưa mở khóa hoặc không ready | Phát hiện mất khả năng thay thế node |
| Rotation chờ và trạng thái chưa xác định | Phát hiện nguy cơ sai credential |
| Tuổi bản sao và độ bao phủ envelope vùng dự phòng | Đánh giá khả năng DR |
| Thay đổi trạng thái khóa, quyền và cấu hình | Hỗ trợ điều tra nguyên nhân |

Liveness của tiến trình và readiness cho từng chức năng không nên bị nhập làm một. KMS tạm mất không nhất thiết là lý do restart tất cả node đang giữ trạng thái hợp lệ. Một restart diện rộng có thể làm mất cache và khiến tình hình xấu hơn.

Một canary có thể thử mở một đối tượng không nhạy cảm bằng cùng đường danh tính và khóa đại diện. Nhưng canary thành công không chứng minh mọi khóa, mọi tenant hoặc mọi policy đều hoạt động. Cần chọn độ bao phủ hợp lý và thể hiện giới hạn đó trong dashboard.

Log chỉ nên chứa định danh tham chiếu, loại thao tác, mã lỗi đã phân loại, thời điểm và correlation ID phù hợp. Không ghi credential, DEK, token hay nội dung phiên nhạy cảm. Quyền xem log và thời hạn lưu cũng phải được quản lý.

### 13.2. Ma trận diễn tập có tiêu chí đạt

Thực hiện trên môi trường được phép, với tài khoản và khóa thử nghiệm. Không vô hiệu hóa hoặc hủy khóa sản xuất để thử khả năng phục hồi.

| Kịch bản | Quan sát bắt buộc | Tiêu chí đạt minh họa |
|---|---|---|
| Chặn đường gọi KMS | Cache, timeout, queue, phiên cũ/mới | Đúng hành vi từng luồng, không gia hạn cache trái policy |
| Tăng độ trễ hoặc throttling | Retry thực tế, tải và thời hạn | Không vượt deadline, không khuếch đại tải ngoài giới hạn |
| Thu hồi quyền của workload thử nghiệm | Phân loại lỗi và đường failover | Không tự tăng quyền hoặc đi vòng thu hồi |
| Không cấp mới token | Thời điểm token hiện tại hết hạn | Phát hiện trước khi mọi node mất khả năng gọi |
| Restart một node khi KMS mất | Bootstrap và readiness | Node lỗi không nhận yêu cầu; node khác không bị kéo restart |
| Restart nhiều node có kiểm soát | Cold cache và quota | Tải phục hồi nằm trong ngân sách đã đo |
| Mất vùng chính | Dữ liệu, khóa, quyền ở vùng dự phòng | Đạt RTO/RPO được chọn bằng thao tác giải mã thực tế |
| Lỗi giữa rotation | Trạng thái hệ đích và vault | Không công bố thành công sai; đối chiếu được credential |
| Restore backup từ trước rotation khóa | Mapping và phiên bản khóa lịch sử | Đọc lại được dữ liệu đúng điểm phục hồi |
| Thu hồi phiên và xóa cache | Credential/phiên đã cấp | Thực thi đúng policy, không nhầm vô hiệu hóa KMS với thu hồi phiên |

Với mỗi bài thử, ghi thời điểm bắt đầu, thời điểm phát hiện, thời điểm thao tác người dùng bị ảnh hưởng, thời điểm phục hồi và bằng chứng. Một test “endpoint trả 200” không thay thế test “PAM giải mã đúng dữ liệu và chỉ cấp cho yêu cầu còn được phép”.

## 14. Tình huống thực hành: vault còn chạy nhưng không mở phiên mới

### 14.1. Bối cảnh

Một tổ chức vận hành ba vault node và hai session broker. Credential được mã hóa bằng DEK, DEK được KMS bọc. Cache DEK tối đa 5 phút. Quy trình rotation và backup cùng sử dụng quota KMS với luồng đọc.

Lúc 09:00, đường mạng đến endpoint KMS vùng A bị gián đoạn. Một số phiên đã mở tiếp tục chạy. Dashboard hạ tầng chỉ kiểm tra tiến trình nên vẫn hiển thị xanh. Lúc 09:02, hệ thống tự restart một vault node vì kiểm tra dependency thất bại. Node mới không mở khóa được. Đến 09:05, nhiều yêu cầu mở phiên bắt đầu thất bại do cache hết hạn.

### 14.2. Phân tích

Vấn đề không phải thiếu vault node. Cả cụm cùng phụ thuộc một đường KMS, còn cơ chế restart làm giảm số node có thể dùng trạng thái hợp lệ. Cache che bớt triệu chứng trong vài phút nhưng không thay thế dependency.

Cần xác minh:

1. Đây là lỗi mạng hay hành động thu hồi khóa/quyền có chủ đích.
2. Những đối tượng nào còn DEK hợp lệ trong cache và còn bao nhiêu thời gian.
3. Các phiên hiện có còn đáp ứng yêu cầu kiểm soát và ghi bằng chứng không.
4. Có rotation nào đã đổi credential ở hệ đích nhưng chưa lưu xong không.
5. Vùng B có đủ dữ liệu, khóa tương thích, quyền và quota hay chỉ có endpoint.
6. Retry từ nhiều node và tác vụ nền đang tạo bao nhiêu tải.

Không thể kết luận mọi dữ liệu sẽ dùng được đến 09:05. Một đối tượng chưa có cache có thể thất bại ngay từ 09:00; một mục cache cũ có thể hết hạn sớm hơn.

### 14.3. Hướng xử lý theo hợp đồng đã định

Trong sự cố, đội vận hành phân loại lỗi, ngừng vòng restart không phù hợp, điều tiết tác vụ nền và bảo đảm timeout/retry có giới hạn. Những yêu cầu không đủ điều kiện tiếp tục phải nhận lỗi rõ ràng; không cấp credential từ một bản sao ngoài kiểm soát.

Nếu vùng B đã được kiểm chứng và policy cho phép, thực hiện chuyển vùng theo runbook, bắt đầu với tải giới hạn. Với rotation chưa xác định kết quả, đối chiếu hệ đích và vault trước khi công bố phiên bản đang hiệu lực. Nếu cần đường khẩn cấp, dùng đúng cơ chế đã được phê duyệt và ghi bằng chứng.

Sau khi phục hồi, xác minh đủ cả đọc credential, mở phiên, kiểm soát phiên, rotation, ghi dữ liệu và khả năng bootstrap node mới. Tăng dần tải và kiểm tra hàng đợi còn tồn, thay vì chỉ chờ KMS trả lời trở lại.

### 14.4. Bài tập thiết kế

Hãy viết một hợp đồng vận hành ngắn cho hệ thống trên, trả lời bốn câu hỏi:

- Yêu cầu mở phiên mới được chờ tối đa bao lâu và được retry trong giới hạn nào?
- Cache DEK hết hạn khi KMS lỗi sẽ dẫn đến hành vi nào?
- Điều kiện chính xác để vùng B đủ khả năng tiếp quản là gì?
- Rotation bị gián đoạn sau khi đổi mật khẩu hệ đích sẽ được nhận diện và đối chiếu ra sao?

Một lời giải tốt phải nối được policy với trạng thái kỹ thuật đo được. “Có ba node”, “có cache” hoặc “đã bật multi-region” chưa phải điều kiện đủ.

## 15. Các nguyên tắc cần giữ khi thiết kế

KMS là một phần của đường cung cấp quyền đặc biệt, không chỉ là thành phần mã hóa nằm ngoài vận hành PAM. Mỗi thao tác cần biết mình dùng khóa nào, gọi dependency lúc nào và phản ứng ra sao khi dependency lỗi.

HA cần bao phủ cả dữ liệu, vật liệu khóa, danh tính, quyền, mạng và năng lực phục hồi. Cache có thể tạo một cửa sổ tiếp tục phục vụ được giới hạn; failover có thể tạo một đường giải mã khác đã kiểm chứng. Cả hai đều phải giữ đúng phạm vi truy cập và ý nghĩa của thu hồi.

Bằng chứng mạnh nhất là diễn tập end-to-end: phục hồi đúng dữ liệu, mở được bằng đúng khóa, chỉ cấp quyền còn hợp lệ, giữ được kiểm soát phiên và đối chiếu được các thao tác đang dở. Đó là cơ sở để xác nhận PAM sẵn sàng cao trước sự cố KMS.
