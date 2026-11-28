# Fail open có kiểm soát

## 1. Lỗi của một kiểm soát không tự tạo ra quyền truy cập

Fail open là hành vi tiếp tục cho phép một hoạt động khi một kiểm soát vốn tham gia quyết định không thể thực hiện đầy đủ. Hành vi đó có thể xuất hiện do chủ ý thiết kế hoặc do lỗi như trả về true trong một khối xử lý ngoại lệ.

Ví dụ, dịch vụ đánh giá rủi ro bổ sung không phản hồi. Ứng dụng tiếp tục cho phép một số thao tác thay vì chặn toàn bộ. Câu hỏi bảo mật là: thao tác nào, với bằng chứng gì, trong bao lâu và dưới giới hạn nào?

“Có kiểm soát” phải được thể hiện thành điều kiện thực thi. Một cờ cấu hình cho phép bỏ qua dịch vụ không tự trở thành một thiết kế có kiểm soát.

MITRE mô tả CWE-636 là tình huống lỗi làm sản phẩm chuyển sang trạng thái kém an toàn hơn các lựa chọn sẵn có. Đây là rủi ro cần nhận diện, không phải một đặc tính tự được chấp nhận vì giúp hệ thống tiếp tục hoạt động. [MITRE CWE-636](https://cwe.mitre.org/data/definitions/636.html).

Trong bài này, fail open có kiểm soát là một ngoại lệ đã được xác định trước cho đúng kiểm soát, đúng hoạt động và đúng điều kiện. Ngoại lệ có giới hạn thời gian, khối lượng, phạm vi dữ liệu, cách quan sát và cách chấm dứt. Rủi ro còn lại phải được nêu rõ.

Mục tiêu của bài là chuyển nhu cầu duy trì dịch vụ khi lỗi thành yêu cầu bảo mật cụ thể, đo được và kiểm chứng được.

## 2. Phân biệt các cách phản ứng khi kiểm soát gặp lỗi

| Cách phản ứng | Ý nghĩa | Điều phải làm rõ |
| --- | --- | --- |
| Fail closed | Không cho hoạt động khi thiếu điều kiện bắt buộc | Kết quả từ chối, retry và ảnh hưởng nghiệp vụ |
| Fail open | Cho hoạt động dù thiếu một kiểm soát dự kiến | Kiểm soát nào bị thiếu và rủi ro tăng thêm |
| Graceful degradation | Giảm chức năng hoặc chất lượng phục vụ | Có làm yếu bảo đảm bảo mật nào hay không |
| Dùng bằng chứng còn hiệu lực | Quyết định từ nguồn hoặc bản sao được chính sách cho phép | Phạm vi, độ mới, thời hạn và tính toàn vẹn |
| Dùng thông tin cũ vượt yêu cầu bình thường | Chấp nhận thêm rủi ro dữ liệu trạng thái | Cửa sổ rủi ro, điều kiện giới hạn và dừng |
| Xử lý trì hoãn | Tiếp nhận công việc nhưng chưa thực hiện tác động | Trạng thái chờ, bảo vệ dữ liệu và điều kiện thực thi sau |
| Circuit breaker | Ngừng gọi một phụ thuộc theo trạng thái sức khỏe | Không tự quyết định request được cấp quyền |
| Break-glass | Đường truy cập khẩn cấp theo chính sách riêng | Actor, quyền, thời hạn, lý do và audit |

### 2.1. Suy giảm chức năng không nhất thiết là fail open

Nếu dịch vụ gợi ý không hoạt động và trang bỏ phần gợi ý, ứng dụng có thể chỉ mất tính năng.

Nếu bộ kiểm tra quyền không hoạt động và ứng dụng cho mọi người xem tài nguyên, ứng dụng đã bỏ qua một điều kiện bảo mật.

Hai trường hợp cần yêu cầu khác nhau. Không gọi mọi fallback là fail open, cũng không dùng tên graceful degradation để che việc mở rộng quyền.

### 2.2. Bản cache không tự trở thành bằng chứng hợp lệ

Một quyết định được cache có thể vẫn đáp ứng hợp đồng bảo mật, nếu nó còn trong phạm vi và độ mới được phép. Khi đó, hệ thống đang sử dụng bằng chứng hợp lệ theo thiết kế.

Nếu dùng quá giới hạn độ mới cần thiết, hệ thống đã thay đổi mức bảo đảm. Cần đặc tả ngoại lệ và rủi ro, không chỉ nói “đã có cache”.

Token còn hạn cũng không tự chứng minh mọi điều kiện phân quyền và thu hồi vẫn đúng. Phải xét những điều kiện mà hệ thống thực sự cam kết kiểm tra.

### 2.3. Nguyên tắc mặc định của kiểm soát truy cập

OWASP khuyến nghị deny by default và xử lý an toàn khi kiểm tra phân quyền thất bại. Việc xử lý ngoại lệ không được tạo đường bypass phân quyền. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Vì vậy, ngoại lệ trong bài không có nghĩa một lỗi bất kỳ được phép biến thành ALLOW. Cần xác định rõ kiểm soát bổ sung nào được nới, trong khi những điều kiện bắt buộc khác vẫn được chứng minh.

## 3. Bắt đầu từ mục tiêu và rủi ro

### 3.1. Tại sao hệ thống muốn tiếp tục hoạt động?

Một phụ thuộc có thể không sẵn sàng vì timeout, lỗi mạng, quá tải hoặc sự cố triển khai. Chặn mọi thao tác có thể gây gián đoạn lớn hơn mức cần thiết nếu chỉ một chức năng bổ sung bị lỗi.

Tuy nhiên, kẻ tấn công cũng có thể gây hoặc tận dụng sự cố đó. Mô hình đe dọa phải xem xét đường “làm phụ thuộc hỏng rồi thực hiện hành động” thay vì chỉ coi lỗi là ngẫu nhiên.

Cần xác định tài sản, tác động của việc cho phép sai, khả năng hoàn tác và giới hạn ảnh hưởng.

### 3.2. Bảng rủi ro minh họa

| Đe dọa hoặc sai sót | Hậu quả | Hành vi cần đặc tả |
| --- | --- | --- |
| Mọi exception đều trở thành cho phép | Bypass cả kiểm soát không liên quan | Chỉ lớp lỗi đã xác định mới đủ điều kiện xét ngoại lệ |
| Kết quả DENY bị hiểu là lỗi dịch vụ | Người bị từ chối vẫn truy cập | Tách từ chối hợp lệ khỏi không có kết quả |
| Gây timeout để bật fallback | Chủ động hạ mức bảo vệ | Điều kiện độc lập, hạn mức và phát hiện lạm dụng |
| Cờ áp dụng cho toàn bộ route | Thao tác nhạy cảm được mở ngoài ý định | Allowlist theo hành động và loại tài nguyên |
| Cache không ràng buộc tenant | Dùng quyết định của người hoặc tổ chức khác | Kiểm tra ngữ cảnh và khóa cache đầy đủ |
| Mỗi request reset thời hạn | Ngoại lệ kéo dài vô hạn | Mốc bắt đầu và deadline của đợt sự cố không bị reset |
| Scale thêm node làm tăng hạn mức | Vượt ngân sách rủi ro | Quota theo phạm vi toàn cục hoặc phân bổ có chứng minh |
| Mất audit vẫn cho phép | Không thể điều tra phần đã mở | Hành vi khi thiếu bằng chứng bắt buộc |
| Phụ thuộc chập chờn | Lặp mở và reset giới hạn | Điều kiện phục hồi ổn định và quản lý đợt |
| Restart phục hồi cờ cũ | Hệ thống mở lại sau hạn | Trạng thái bền vững và khởi động mặc định an toàn |

Mỗi ngoại lệ cần owner và lý do gắn với các rủi ro này. Tối ưu tỷ lệ thành công không thay thế việc xác định giới hạn chấp nhận.

## 4. Xác định ranh giới được phép nới

### 4.1. Tách điều kiện bắt buộc và kiểm soát được xét ngoại lệ

Đối với từng hành động, cần phân biệt:

- Danh tính và credential phải được xác minh.
- Quyền đối với hành động, tài nguyên và tenant phải đủ căn cứ.
- Giới hạn dữ liệu và trạng thái nghiệp vụ phải được kiểm tra.
- Kiểm soát bổ sung nào có thể không được thực hiện trong ngoại lệ.
- Những điều kiện bổ sung để bù phần bảo đảm bị thiếu.

Việc phân loại phải dựa vào yêu cầu hệ thống, không phải việc thư viện đang hỗ trợ tùy chọn fail-open nào.

Nếu một điều kiện là bắt buộc theo nguồn yêu cầu đang áp dụng, không được đổi tên nó thành “bổ sung” để bỏ qua khi lỗi.

### 4.2. Phạm vi theo ngữ nghĩa, không chỉ HTTP method

“Chỉ cho GET” không đủ. Một request GET có thể export dữ liệu, đọc thông tin nhạy cảm hoặc tạo tác động qua một thiết kế sai.

Cần xác định hành động cụ thể, loại tài nguyên, tập trường trả về, quan hệ sở hữu và khối lượng. Một truy vấn đọc hàng loạt có rủi ro khác đọc một phần hồ sơ của chính người gọi.

Các thao tác như cấp quyền, thay thông tin khôi phục, export diện rộng hoặc tạo credential cần được đánh giá riêng. Chúng không tự được hưởng ngoại lệ của một màn hình đọc rủi ro thấp.

### 4.3. Không biến trạng thái không biết thành trạng thái tốt

Thiếu thông tin không đồng nghĩa tài khoản đang hoạt động, token chưa bị thu hồi hoặc chủ thể không bị chặn.

Thiết kế phải nêu bằng chứng nào vẫn đủ để quyết định. Nếu không chứng minh được điều kiện bắt buộc, kết quả là không thực hiện hành động đó theo chính sách lỗi.

Một ngoại lệ hợp lệ vẫn có thể tăng rủi ro. Biện pháp giới hạn giúp kiểm soát mức tăng này, không làm nó biến mất.

## 5. Tình huống minh họa: thiếu một lớp đánh giá rủi ro bổ sung

### 5.1. Điều kiện bình thường

Giả sử một ứng dụng có hành động READ_SELF_BASIC_PROFILE: người đã xác thực đọc tên hiển thị và ngôn ngữ của chính mình trong đúng tenant.

Ứng dụng vẫn kiểm tra credential, quyền trên tài nguyên, trạng thái tài khoản bắt buộc, quan hệ tenant và giới hạn dữ liệu. Một dịch vụ chấm điểm rủi ro bổ sung có thể từ chối request khi phát hiện dấu hiệu bất thường.

Tổ chức quyết định xét ngoại lệ khi riêng dịch vụ bổ sung này không sẵn sàng. Những phụ thuộc dùng để chứng minh các điều kiện bắt buộc vẫn phải đáp ứng hợp đồng của chúng.

Nếu đường kiểm tra trạng thái thu hồi bắt buộc cũng lỗi, request không được tiếp tục chỉ vì dịch vụ chấm điểm đang lỗi.

### 5.2. Phạm vi ngoại lệ

Trong ví dụ, chỉ cho phép:

- Hành động READ_SELF_BASIC_PROFILE đã được định danh rõ.
- Đọc tài nguyên của chính chủ thể trong đúng tenant.
- Trả tập trường cố định, không có mở rộng qua tham số.
- Request đáp ứng mọi kiểm tra bắt buộc còn lại.
- Có chính sách ngoại lệ còn hiệu lực, ngân sách còn và audit được ghi nhận.
- Lỗi thuộc nhóm không sẵn sàng đã xác định.

Không cho phép tạo phiên mới, cấp quyền, export, đọc hồ sơ người khác hoặc đổi thông tin bảo mật.

Phạm vi này chỉ là giả định để học phương pháp đặc tả, không phải khuyến nghị rằng mọi hệ thống nên cho phép hành động tương tự khi thiếu đánh giá rủi ro.

### 5.3. Nhóm kết quả phải được phân biệt

| Kết quả kiểm soát bổ sung | Xử lý trong ví dụ |
| --- | --- |
| ALLOW hợp lệ | Tiếp tục qua các kiểm tra còn lại |
| DENY hợp lệ | Từ chối; không chuyển sang ngoại lệ |
| Timeout hoặc không kết nối thuộc nhóm được phép | Xét điều kiện ngoại lệ |
| Chữ ký, chứng chỉ hoặc nguồn phản hồi không hợp lệ | Không coi là timeout thông thường; dừng theo chính sách lỗi |
| Payload sai cấu trúc, phiên bản không hỗ trợ hoặc null ngoài hợp đồng | Không tự cho phép; ghi lỗi và xử lý theo chính sách |
| Lỗi trong kiểm tra danh tính hoặc tenant | Không thuộc ngoại lệ |
| Hết hạn credential, thiếu quyền hoặc tài khoản bị chặn | Từ chối |

Một timeout có thể làm kết quả cuối cùng đến muộn. Nếu DENY hợp lệ đã được nhận trước điểm quyết định thực hiện, nó không được bỏ qua chỉ vì nhánh fallback đã bắt đầu.

Nếu kết quả đến sau tác động đã xảy ra, hệ thống cần ghi nhận và xử lý theo yêu cầu riêng. Nó không thể cam kết tự đảo ngược mọi tác động đã hoàn tất.

## 6. Mô hình trạng thái và quyền chuyển chế độ

### 6.1. Trạng thái phải có ngữ nghĩa rõ

~~~mermaid
stateDiagram-v2
    [*] --> NORMAL
    NORMAL --> LIMITED_OPEN: Lỗi đủ điều kiện và mọi ràng buộc đạt
    NORMAL --> CLOSED: Không đủ điều kiện bắt buộc
    LIMITED_OPEN --> CLOSED: Hết hạn, hết ngân sách hoặc có lệnh dừng
    LIMITED_OPEN --> RECOVERING: Phụ thuộc có dấu hiệu phục hồi
    RECOVERING --> NORMAL: Đáp ứng điều kiện ổn định
    RECOVERING --> CLOSED: Không còn đủ điều kiện ngoại lệ
    CLOSED --> NORMAL: Phục hồi đã được xác minh
~~~

Sơ đồ là mô hình khái niệm. Một lỗi tại một hành động không nhất thiết đóng toàn ứng dụng. Phạm vi trạng thái cần được xác định, chẳng hạn tenant, hành động và kiểm soát phụ thuộc.

LIMITED_OPEN không có nghĩa mọi request đều được cho phép. Mỗi request vẫn phải qua các điều kiện và hạn mức.

### 6.2. Kích hoạt theo chính sách, không theo yêu cầu của caller

Caller không được tự bật ngoại lệ bằng header, query parameter, một mã lỗi tự khai hoặc cờ debug.

Có thể có kích hoạt tự động theo chính sách đã được chấp thuận trước, hoặc thao tác vận hành có quyền. Hai cách đều cần phạm vi, thời hạn và bằng chứng.

Người sửa chính sách hoặc kéo dài ngoại lệ phải có quyền tương ứng. Quyền xem dashboard không tự bao gồm quyền mở rộng phạm vi bảo mật.

### 6.3. Circuit breaker không phải bộ cấp quyền

Breaker có thể báo không nên gọi dịch vụ đang lỗi. Nhánh xử lý sau đó vẫn phải quyết định từ chối, trì hoãn hoặc xét một ngoại lệ cụ thể.

Nếu mọi trạng thái open của breaker đều trả ALLOW thì cơ chế chống quá tải đã trở thành đường bỏ kiểm soát.

Các health probe cũng không tự chứng minh kiểm soát hoạt động đúng. Kết nối TCP thành công hoặc endpoint health trả 200 có thể chưa bảo đảm hệ thống đã đưa ra quyết định hợp lệ.

## 7. Thời gian, độ mới và vòng đời đợt sự cố

### 7.1. Chọn mốc không bị reset

Trong ví dụ, chọn:

~~~text
T_start: lần đầu ghi nhận lỗi đủ điều kiện của đợt trong nguồn điều phối
T_deadline: T_start + 120 giây

Chỉ xét ngoại lệ khi:
T_decision < T_deadline
~~~

Mốc áp dụng cho toàn phạm vi đã định, không phải mỗi request hoặc mỗi node tự bắt đầu một đồng hồ mới.

Tại đúng deadline, nhánh ngoại lệ không còn được sử dụng. Các điều kiện khác có thể làm nó dừng sớm hơn.

### 7.2. Deadline thực tế là giới hạn chặt nhất

Có thể diễn đạt:

~~~text
effective_deadline =
    min(
        deadline của đợt,
        thời điểm chính sách hết hiệu lực,
        thời điểm bằng chứng bắt buộc hết hiệu lực,
        các giới hạn thời gian khác đang áp dụng
    )
~~~

Thời hạn ngoại lệ không gia hạn credential. Cũng không gia hạn một quyết định phân quyền hoặc thông tin thu hồi vượt hợp đồng của chúng.

Ví dụ, nếu một cam kết thu hồi yêu cầu chặn trong 60 giây, không thể dùng bản trạng thái cũ 5 phút mà vẫn tuyên bố đáp ứng cam kết đó khi không có cơ chế khác.

### 7.3. Restart và đồng hồ

Restart không được tạo lại 120 giây từ đầu. Node mới phải biết đợt đang có hiệu lực và deadline đã được xác lập.

Cần quy định nguồn thời gian, sai lệch và cách phát hiện trạng thái không thể tin cậy. Một thay đổi đồng hồ không được biến thời hạn đã hết thành còn hạn.

Nếu không xác minh được deadline hoặc phiên bản đợt, request không được dùng ngoại lệ trong ví dụ này.

### 7.4. Chập chờn không được kéo dài vô hạn

Một lần gọi thành công không tự kết thúc đợt để lần timeout kế tiếp nhận ngân sách mới.

Ví dụ có thể yêu cầu 60 giây phục hồi ổn định, với các phản hồi kiểm soát hợp lệ theo phạm vi quan sát đã chọn, trước khi đóng đợt và về NORMAL. Các con số là giả định cần được kiểm chứng với hệ thống thực tế.

Trong RECOVERING, request nào đã lấy được quyết định bình thường thì phải tôn trọng quyết định đó. Request dùng ngoại lệ vẫn chịu deadline và ngân sách cũ.

Khi đã hết deadline mà chưa phục hồi, không tự gia hạn vì dịch vụ vẫn lỗi. Một quyết định ngoại lệ mới, nếu chính sách cho phép, phải có thẩm quyền, phạm vi và bằng chứng riêng.

## 8. Hạn mức và cách giới hạn phạm vi ảnh hưởng

### 8.1. Ngân sách phải được thực thi trước tác động

Giả sử ví dụ chọn:

- Tối đa 100 quyết định cho phép theo ngoại lệ cho mỗi tenant trong một đợt.
- Tối đa 10 cho mỗi principal trong cùng đợt.
- Tối đa 200 cho mỗi tenant trong cửa sổ trượt 3.600 giây, tính cả các đợt.

Mỗi quyết định ngoại lệ phải giữ được phần ngân sách cần thiết bằng cơ chế nguyên tử trước khi thực hiện. Không kiểm tra số đếm rồi tăng sau ở nhiều node độc lập.

Hết một giới hạn là dừng, dù thời gian còn. Retry không được tự hoàn lại ngân sách để tạo đường sử dụng không giới hạn.

### 8.2. Local quota không tự là global quota

Nếu mỗi node được cho phép q lần và có N node độc lập, mức cho phép có thể tăng theo N nhân q trong phạm vi đo tương ứng.

Scale thêm node, đổi định danh node hoặc restart bộ đếm có thể phá giới hạn đã công bố. Vì vậy cần bộ đếm chung hoặc phân bổ ngân sách có chứng minh không cấp trùng và không reset.

Trong ví dụ, nguồn quản lý ngân sách độc lập vẫn phải sẵn sàng. Nếu nó cũng lỗi hoặc không chứng minh được số dư, ngoại lệ dừng. Không dùng sự cố của một kiểm soát để cho phép bỏ thêm kiểm soát giới hạn.

### 8.3. Đọc ít vẫn cần giới hạn dữ liệu

Read-only không tự có nghĩa rủi ro thấp. Phạm vi phải giới hạn tài nguyên, tập trường, số đối tượng và khả năng lặp để thu thập dữ liệu.

Một endpoint đọc một phần hồ sơ không được biến thành tìm kiếm hoặc export nhờ tham số tùy chọn trong chế độ ngoại lệ.

Giới hạn theo thời gian và request không thay thế phân quyền. Kẻ tấn công chỉ cần một lần đọc sai cũng có thể gây lộ dữ liệu.

## 9. Đặc tả đường quyết định để không che lỗi bằng ALLOW

### 9.1. Tránh một giá trị boolean cho mọi tình huống

Nếu hàm kiểm tra chỉ trả true hoặc false rồi exception cũng được chuyển thành true, bên gọi không biết request được chấp nhận theo căn cứ nào.

Nên mô tả kết quả theo ngữ nghĩa: cho phép bình thường, từ chối, lỗi đủ điều kiện xét ngoại lệ, lỗi không đủ điều kiện hoặc không thể xác minh điều kiện bắt buộc.

Không gộp phản hồi 4xx, 5xx, timeout, lỗi giải mã và lỗi kiểm tra chữ ký thành một nhánh “dịch vụ không hoạt động”.

### 9.2. Mã giả ở mức yêu cầu

~~~text
decide(request):

    context = xác lập danh tính, tenant, tài nguyên và hành động đáng tin cậy

    nếu không chứng minh được điều kiện bảo mật bắt buộc:
        không thực hiện hành động

    result = gọi kiểm soát bổ sung với timeout đã xác định

    nếu result là DENY hợp lệ:
        từ chối

    nếu result là ALLOW hợp lệ:
        quyết định theo chính sách bình thường

    nếu result không thuộc nhóm lỗi được phép:
        không dùng ngoại lệ

    policy = lấy chính sách ngoại lệ có thẩm quyền
    episode = lấy đợt và deadline đã được xác lập

    nếu sai phạm vi, hết hạn hoặc không có tín hiệu cho phép còn hiệu lực:
        không dùng ngoại lệ

    nếu không giữ được ngân sách bằng cơ chế được cam kết:
        không dùng ngoại lệ

    nếu không ghi bền được ngữ cảnh quyết định bắt buộc:
        không dùng ngoại lệ

    tại điểm quyết định đã quy định:
        kiểm tra lại thời hạn và điều kiện cần còn hiệu lực
        tôn trọng kết quả DENY đã biết trước điểm này

    chỉ thực hiện hành động và tập dữ liệu đã được giới hạn
    ghi nhận kết quả và đối soát theo chính sách
~~~

Đây là mã giả mô tả yêu cầu, không phải một triển khai giao dịch phân tán. Kiến trúc phải chứng minh các điều kiện tại điểm quyết định và xử lý các cuộc đua tương ứng.

Không dùng sơ đồ này để khẳng định một lần kiểm tra ở đầu request bảo vệ mọi tác động xảy ra nhiều phút sau.

### 9.3. Request bị đổi ngữ cảnh sau kiểm tra

Nếu gateway đã kiểm tra hành động đọc hồ sơ nhưng downstream đổi route, tài nguyên hoặc tập trường, quyết định trước đó có thể không còn áp dụng.

Cần ràng buộc ngữ cảnh đã kiểm tra với hành động thực tế. Các bước mở rộng tài nguyên, chuyển tenant hoặc tạo tác động mới phải được đánh giá theo yêu cầu tương ứng.

Một mã ALLOW_LIMITED không được dùng như quyền chung cho các thao tác khác trong cùng phiên.

### 9.4. Không dùng ngoại lệ để che lỗi lập trình

Lỗi null, dữ liệu sai kiểu hoặc lỗi deserialize bất ngờ có thể cho thấy hợp đồng bị phá. Không mặc định chúng là tín hiệu được phép nới kiểm soát.

Phân loại lỗi phải rõ và có kiểm thử. Nhánh xử lý cuối cho tình huống chưa biết phải dẫn tới hành vi an toàn đã định, không phải cho phép toàn bộ.

Phản hồi cho caller không nên lộ stack trace, secret hoặc chi tiết có thể giúp ép hệ thống vào nhánh ngoại lệ.

## 10. Quan sát và audit là một phần điều kiện hoạt động

### 10.1. Ghi được lý do và phạm vi

Một bản ghi hữu ích có thể có:

- Mã request và mã đợt.
- Actor hoặc mã tham chiếu phù hợp, tenant và hành động.
- Kiểm soát bị lỗi và loại lỗi đã phân loại.
- Phiên bản chính sách và nguồn quyết định.
- Mốc bắt đầu, deadline và thời điểm quyết định.
- Ngân sách được sử dụng và phạm vi dữ liệu.
- Kết quả cho phép giới hạn, từ chối hoặc chưa xác minh.

Không ghi credential nguyên giá trị hoặc toàn bộ dữ liệu phản hồi vào log.

Cần phân biệt ý định cấp phép, quyết định và kết quả thực thi. Một bản ghi chuẩn bị hành động không chứng minh hành động đã hoàn thành.

### 10.2. Nếu hệ thống log tập trung cũng lỗi

Có thể dùng bộ đệm bền vững được bảo vệ nếu chính sách cho phép. Phải xác định dung lượng, quyền đọc, thời gian giữ, chuyển tiếp và xử lý đầy bộ đệm.

Trong ví dụ, nếu không ghi được bằng chứng bắt buộc theo mô hình độ bền đã chọn, không tiếp tục cấp phép theo ngoại lệ. Không chuyển sang “cho phép nhưng không log” như một ngoại lệ thứ hai ngầm định.

Độ bền phải gắn với mô hình sự cố. Ghi vào RAM hoặc chỉ xác nhận đã đưa vào hàng chờ trong bộ nhớ không chứng minh có thể điều tra sau restart.

### 10.3. Cảnh báo không thay thế giới hạn

Có cảnh báo không ngăn request vượt phạm vi hoặc vượt deadline. Các điều kiện phải được thực thi trên đường quyết định.

Ví dụ, có thể đặt mục tiêu cảnh báo trong 30 giây từ khi vào LIMITED_OPEN. Nếu không đáp ứng, cần ghi nhận vi phạm quan sát; nhưng cảnh báo chậm không được tự kéo dài deadline.

Không coi tất cả request trả thành công là dấu hiệu hệ thống khỏe khi chúng đang sử dụng mức bảo đảm thấp hơn.

## 11. Dừng khẩn cấp, phục hồi và khởi động lại

### 11.1. Tín hiệu dừng phải có giới hạn độ trễ

Cần một cơ chế có quyền để dừng ngoại lệ theo toàn hệ thống hoặc phạm vi bị ảnh hưởng.

Giả sử yêu cầu dừng có hiệu lực trong tối đa 5 giây từ khi nguồn điều khiển ghi bền. Một cách thiết kế là yêu cầu quyền sử dụng ngoại lệ dưới dạng lease ngắn, có nguồn đáng tin cậy và thời hạn phù hợp.

Node không thể làm mới điều kiện này phải dừng dùng ngoại lệ khi lease hết hạn. Không dùng bản cấu hình “đang cho phép” vô thời hạn nếu đã mất liên lạc với nguồn dừng.

Giới hạn phải bao gồm polling, cache, truyền trạng thái và sai lệch đồng hồ. “Có nút tắt” chưa chứng minh được thời gian tắt.

### 11.2. Phục hồi phải chứng minh hơn khả năng kết nối

Điều kiện về NORMAL có thể cần:

- Phản hồi hợp lệ từ kiểm soát thực tế.
- Phiên bản chính sách và trạng thái cần thiết đã sẵn sàng.
- Giai đoạn ổn định theo tiêu chí đã chọn.
- Không còn tín hiệu buộc dừng hoặc sự cố chưa đối soát.
- Kết thúc đợt được ghi nhận trong nguồn có thẩm quyền.

Không reset trạng thái chỉ vì một health endpoint thành công. Cũng không tiếp tục bỏ qua một DENY sau khi dịch vụ đã phục hồi.

Nếu nghi ngờ lỗi do tấn công hoặc giả mạo phản hồi, quá trình trở lại bình thường cần theo quy trình xử lý sự cố phù hợp, không chỉ kiểm tra mạng.

### 11.3. Khởi động mới phải bảo toàn giới hạn

Node khởi động lại cần biết deadline, ngân sách và phiên bản đợt hiện hành. Nếu không có bằng chứng cần thiết, nó không bắt đầu một đợt mới độc lập.

Autoscaling và failover phải được xét trong mô hình hạn mức. Một cơ chế chỉ đúng khi có một node không tự đúng trong cụm.

Cấu hình debug hoặc cờ môi trường không được vô tình mở ngoại lệ ở môi trường thật. Giá trị thiếu hoặc không hợp lệ phải có hành vi được định trước.

### 11.4. Công việc đã tiếp nhận và công việc đang chạy

Một request có thể được nhận trước deadline nhưng chỉ thực hiện sau deadline. Cần xác định điểm mà điều kiện ngoại lệ phải còn hiệu lực.

Trong ví dụ đọc hồ sơ, áp dụng tại quyết định cấp dữ liệu. Với job hoặc stream, có thể cần kiểm tra trước từng tác động hoặc theo chu kỳ có giới hạn.

Không đưa công việc vào queue dưới nhãn “đã được cho phép” rồi thực thi vô hạn về sau. Nếu muốn trì hoãn, phải phân biệt tiếp nhận với cấp quyền thực hiện.

Ngoại lệ cũng không tự hoàn tác hoạt động đã hoàn thành. Yêu cầu hậu xử lý, bù trừ hoặc thông báo phải được xác định riêng.

## 12. Bộ yêu cầu đo được cho tình huống minh họa

### 12.1. Phạm vi và nguồn giả định

Bộ yêu cầu sau áp dụng cho ngoại lệ của kiểm soát chấm điểm rủi ro bổ sung trong hành động READ_SELF_BASIC_PROFILE đã mô tả.

Các ngưỡng 120 giây, 100 request, 10 request, 200 request, 5 giây, 30 giây và 60 giây chỉ là giả định học tập. Hệ thống thực tế phải chọn giới hạn theo rủi ro, nguồn yêu cầu và khả năng thực thi.

Các cơ chế xác thực, phân quyền bắt buộc, tenant, quản lý ngân sách, tín hiệu dừng và ghi bằng chứng vẫn phải hoạt động theo hợp đồng của chúng. Ngoại lệ không bao phủ lỗi của mọi phụ thuộc.

Trong các yêu cầu này, CLOSED là đóng đường ngoại lệ của phạm vi liên quan. Nó không tự cấm một request có đầy đủ quyết định bình thường hợp lệ và đáp ứng mọi điều kiện khác.

### 12.2. Ma trận yêu cầu và tiêu chí chấp nhận

| ID | Yêu cầu bảo mật | Tiêu chí chấp nhận |
| --- | --- | --- |
| FO-01 | Chỉ hành động, tài nguyên, tập trường và tenant được allowlist mới được xét ngoại lệ | Route mới, export, đọc người khác hoặc thêm trường không tự được chấp nhận |
| FO-02 | Mọi điều kiện bảo mật bắt buộc vẫn phải có bằng chứng đủ hiệu lực | Thiếu danh tính, sai tenant, credential hết hạn, thiếu quyền hoặc trạng thái bắt buộc không xác minh được đều không được dùng ngoại lệ |
| FO-03 | Chỉ lỗi không sẵn sàng đã phân loại của đúng kiểm soát bổ sung mới đủ điều kiện | DENY, phản hồi giả mạo, lỗi cấu trúc hoặc lỗi lập trình không chuyển thành ALLOW_LIMITED |
| FO-04 | Ngoại lệ kết thúc trước hoặc tại T_start cộng 120 giây của cùng đợt | Request tại ranh giới và sau ranh giới không dùng ngoại lệ; restart hoặc retry không reset mốc |
| FO-05 | Không vượt 100 quyết định mỗi tenant mỗi đợt, 10 mỗi principal mỗi đợt và 200 mỗi tenant trong 3.600 giây trượt | Request đồng thời ở mọi node không vượt bất kỳ hạn mức; không giữ được ngân sách thì không thực hiện |
| FO-06 | Lệnh dừng có hiệu lực trong tối đa 5 giây từ khi được ghi bền | Cache nóng, mất kết nối cập nhật và node mới không tiếp tục sử dụng lease ngoại lệ sau giới hạn |
| FO-07 | Mọi quyết định ngoại lệ phải có ngữ cảnh audit bền vững bắt buộc | Không ghi được bằng chứng hoặc bộ đệm đầy thì không cấp phép theo ngoại lệ; không chứa credential nguyên giá trị |
| FO-08 | Vào LIMITED_OPEN phải phát cảnh báo trong tối đa 30 giây từ T_start | Đối chiếu mốc đợt, phát hiện và nhận cảnh báo theo phạm vi đã chọn; lỗi cảnh báo không gia hạn ngoại lệ |
| FO-09 | Chỉ kết thúc đợt sau điều kiện phục hồi ổn định 60 giây theo đường kiểm soát thực tế | Có kiểm tra mỗi 10 giây qua các đường thuộc inventory, phản hồi hợp lệ và không có lỗi không sẵn sàng xen kẽ trong cửa sổ; không chỉ dùng health 200 |
| FO-10 | Autoscaling, failover và rollback không mở thêm phạm vi hoặc reset ngân sách | Node mới sử dụng cùng đợt và giới hạn; thiếu trạng thái có thẩm quyền dẫn tới không dùng ngoại lệ |
| FO-11 | Thiếu chính sách, deadline, ngân sách hoặc tín hiệu dừng đủ mới không được tự cho phép | Gây lỗi riêng và đồng thời từng thành phần; không có chuỗi fallback bỏ qua thêm kiểm soát |
| FO-12 | Chính sách và trạng thái ngoại lệ chỉ được thay đổi bởi actor có quyền, có phiên bản và audit | Caller không bật bằng tham số; sửa phạm vi, kéo dài thời hạn hoặc thay quota ngoài quyền bị từ chối |

FO-09 là điều kiện đóng đợt và xác nhận phục hồi, không cấp quyền vượt FO-04 trong lúc chờ ổn định.

FO-05 yêu cầu đo trên phạm vi chia sẻ thực tế. Nếu chỉ có bộ đếm cục bộ và không chứng minh tổng phân bổ, không được báo đạt hạn mức toàn tenant.

### 12.3. Ví dụ đặc tả có truy vết

~~~yaml
requirement_id: FO-04
risk_id: TH-ERROR-07
risk: Ngoại lệ tiếp tục vô hạn do retry, restart hoặc trạng thái chập chờn
control_scope: Kiểm soát chấm điểm rủi ro bổ sung
allowed_action: READ_SELF_BASIC_PROFILE
allowed_resource_relation: Hồ sơ của chính chủ thể trong đúng tenant
required_baseline:
  - Danh tính và credential được xác minh
  - Phân quyền bắt buộc và tenant đủ căn cứ
  - Trạng thái bảo mật bắt buộc đáp ứng hợp đồng
  - Tập trường trả về được giới hạn
trigger: Lỗi không sẵn sàng thuộc nhóm được chính sách cho phép
episode_start: Mốc đầu tiên được nguồn điều phối có thẩm quyền ghi nhận
maximum_episode_seconds: 120
decision_boundary: Chỉ dùng ngoại lệ khi thời điểm quyết định nhỏ hơn deadline
earlier_stop_conditions:
  - Chính sách hoặc bằng chứng bắt buộc hết hiệu lực
  - Có DENY hợp lệ áp dụng trước điểm quyết định
  - Hết ngân sách
  - Không có tín hiệu cho phép còn hiệu lực
  - Không ghi được audit bắt buộc
failure_behavior: Không thực hiện qua đường ngoại lệ
verification:
  - Kiểm tra ngay trước, tại và sau deadline
  - Restart và thêm node không tạo deadline mới
  - Phụ thuộc chập chờn không reset đợt
evidence:
  - Mã đợt, phiên bản chính sách và mốc bắt đầu
  - Nguồn thời gian và sai lệch được chấp nhận
  - Kết quả tại từng điểm thực thi
owner: Nhóm ứng dụng, nhóm identity và nhóm vận hành
~~~

Đây là đặc tả minh họa, không phải cấu hình của một framework. Trong hồ sơ thực tế cần thay các phạm vi khái niệm bằng inventory, nguồn chính sách và phương pháp kiểm chứng cụ thể.

### 12.4. Một ví dụ ngân sách dừng trước deadline

~~~text
T0       Đợt lỗi đủ điều kiện được ghi nhận
T0+30s   Hạn phát cảnh báo của ví dụ
T0+75s   Tenant đã dùng hết 100 quyết định ngoại lệ
T0+75s   Đường ngoại lệ phải dừng dù chưa hết 120 giây
T0+120s  Không còn request nào được dùng deadline của đợt này
~~~

Nếu một principal dùng đủ 10 lần sớm hơn, principal đó dừng sớm hơn. Nếu ngân sách cửa sổ trượt đã hết từ các đợt trước, đợt mới cũng không có quyền vượt nó.

Các giới hạn là điều kiện đồng thời, không phải những lựa chọn có thể lấy điều dễ đáp ứng nhất.

## 13. Thiết kế kiểm chứng theo rủi ro

### 13.1. Ca nền và bằng chứng nguyên nhân

Dùng danh tính, tenant và dữ liệu tổng hợp trong môi trường kiểm chứng.

Trước khi tạo lỗi, cần chứng minh request hợp lệ đi theo đường bình thường và request thiếu quyền bị từ chối. Nếu mọi request vốn đã lỗi mạng, kết quả sau đó không chứng minh nhánh bảo mật hoạt động.

Với mỗi quyết định, cần biết nó là ALLOW bình thường, ALLOW_LIMITED, DENY hay lỗi không thực hiện. Không dùng mã HTTP thành công làm bằng chứng duy nhất của nguyên nhân.

Phản hồi công khai cần theo hợp đồng API và tránh lộ chi tiết nội bộ. Phân loại chính xác có thể nằm trong audit được bảo vệ.

### 13.2. Ma trận lỗi và từ chối

Kiểm tra riêng:

- Timeout đủ điều kiện.
- Kết nối không sẵn sàng thuộc nhóm cho phép.
- Phản hồi DENY hợp lệ.
- Phản hồi sai nguồn hoặc sai chữ ký.
- Chứng chỉ không hợp lệ.
- Payload thiếu trường, sai kiểu hoặc phiên bản không hỗ trợ.
- Lỗi lập trình trong adapter.
- Lỗi của một kiểm soát bắt buộc khác.

Mục tiêu là chứng minh chỉ đúng lớp lỗi mới đi tới bước xét ngoại lệ. Không chỉ kiểm thử một exception được cố ý ném ra rồi kết luận mọi đường lỗi an toàn.

Thêm ca phản hồi DENY đến trong lúc request đang chuẩn bị quyết định ngoại lệ. Hành vi phải theo điểm quyết định đã đặc tả, không ngẫu nhiên do nhánh nào chạy trước.

### 13.3. Ranh giới thời gian và khởi động lại

Kiểm tra ngay trước, đúng tại và sau deadline; credential hết hạn sớm hơn; chính sách hết hiệu lực; lease dừng hết hạn; và nguồn thời gian không đáng tin cậy.

Restart node giữa đợt, thêm node hoặc chuyển vùng phục vụ không được tạo mốc mới.

Trong môi trường kiểm chứng có thể dùng cơ chế kiểm soát thời gian phù hợp. Không thay đồng hồ hệ thống đang phục vụ thật chỉ để chạy ca thử.

Cần đo tại điểm cấp quyền hoặc tác động đã chọn, không chỉ thời điểm một task dọn cờ chạy.

### 13.4. Ngân sách và đồng thời

Gửi request đồng thời tới nhiều điểm thực thi trong phạm vi thử.

Đối chiếu tổng quyết định ngoại lệ, ngân sách mỗi principal, mỗi tenant, mỗi đợt và cửa sổ trượt. Ca cuối cùng ở ranh giới không được vượt số lượng do nhiều request cùng thấy “còn một”.

Thử restart bộ đếm cục bộ, thay định danh node và scale pool. Nếu kiến trúc dùng phân bổ, cần chứng minh không cấp lại phần đã được dùng hoặc đang giữ.

Mô phỏng nguồn ngân sách không sẵn sàng. Hệ thống phải dừng xét ngoại lệ theo FO-11 thay vì mặc định số dư vô hạn.

### 13.5. Lạm dụng có chủ đích

Kiểm tra khả năng caller ép timeout, lặp retry, đổi request ID hoặc chuyển tenant để nhận ngân sách mới ngoài quyền.

Không cần tấn công hệ thống của bên khác. Dùng fault injection và tải thử trong phạm vi được phép.

Giới hạn chỉ có tác dụng nếu điểm thực thi không thể bị bypass bằng route phụ, tác vụ nền, proxy khác hoặc tham số mở rộng dữ liệu.

### 13.6. Dừng, phục hồi và audit lỗi

Kiểm tra tín hiệu dừng với cache nóng, node mất cập nhật và request đang chờ.

Mô phỏng dịch vụ chập chờn để chứng minh cửa sổ ổn định không reset đợt sớm. Phản hồi DENY hợp lệ sau khi dịch vụ phục hồi phải được tôn trọng.

Làm đầy bộ đệm audit, mất kết nối log tập trung và restart tiến trình. Kết quả phải phù hợp mô hình độ bền được cam kết.

Một lần diễn tập cần có bằng chứng tại các điểm thực thi trong inventory. Một node đạt không chứng minh toàn cụm đạt.

## 14. Vận hành và báo cáo mức bảo đảm

Các số liệu hữu ích gồm:

| Số liệu | Mục đích |
| --- | --- |
| Số quyết định ALLOW_LIMITED theo hành động, tenant và đợt | Biết phạm vi đang dùng ngoại lệ |
| Độ tuổi đợt và thời gian còn lại | Phát hiện nguy cơ vượt deadline |
| Ngân sách còn và số lần bị chặn | Đối soát giới hạn khối lượng |
| Loại lỗi kích hoạt | Phát hiện phân loại sai hoặc tấn công ép lỗi |
| Độ trễ tín hiệu dừng theo điểm thực thi | Kiểm tra khả năng đóng ngoại lệ |
| Node không biết trạng thái hoặc lệch phiên bản | Nhận diện phần chưa đủ bằng chứng |
| Audit tồn đọng, mất hoặc không đối soát được | Đánh giá chất lượng điều tra |
| Số lần mở lại và tổng sử dụng qua nhiều đợt | Phát hiện việc sống lâu trong chế độ suy giảm |

Nếu yêu cầu là giới hạn tối đa, p95 hoặc số trung bình không chứng minh mọi request đều đạt. Cần thống kê vi phạm và phần không quan sát được.

Báo cáo phải phân biệt dịch vụ còn trả được kết quả với dịch vụ đang duy trì đầy đủ mức bảo đảm bình thường. Không ghi “mọi kiểm soát hoạt động” khi một lớp đang được nới có chủ đích.

Ngoại lệ sử dụng thường xuyên có thể cho thấy kiến trúc phụ thuộc hoặc mục tiêu ban đầu không phù hợp. Cần xử lý nguyên nhân, không chỉ tăng quota hoặc deadline để làm cảnh báo biến mất.

Quyết định chấp nhận rủi ro cũng có phạm vi và thời hạn. Thay loại dữ liệu, mức quyền hoặc chức năng phải được đánh giá lại, không tự kế thừa ngoại lệ cũ.

## 15. Những cách viết yêu cầu dễ gây bypass

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| Khi dịch vụ lỗi thì cho qua | Không biết lỗi nào, điều kiện nào bị bỏ | Phân loại kết quả và chỉ rõ kiểm soát được xét ngoại lệ |
| Chỉ mở tạm thời | Không có mốc và deadline | Định nghĩa đợt, nguồn thời gian và điểm quyết định |
| Chỉ cho GET nên an toàn | GET có thể đọc dữ liệu nhạy cảm hoặc diện rộng | Giới hạn hành động, tài nguyên và tập trường |
| Có cache nên vẫn đủ quyền | Cache có thể cũ hoặc sai ngữ cảnh | Ràng buộc subject, tenant, action, resource và độ mới |
| Breaker mở thì trả ALLOW | Nhầm cơ chế bảo vệ phụ thuộc với cấp quyền | Tách breaker khỏi chính sách quyết định |
| Mỗi node chỉ cho ít request | Tổng cụm và autoscaling có thể vượt giới hạn | Ngân sách dùng chung hoặc phân bổ có chứng minh |
| Restart để bắt đầu lại thời gian | Ngoại lệ có thể kéo dài vô hạn | Giữ deadline và ngân sách của cùng đợt |
| Có cảnh báo là đủ kiểm soát | Cảnh báo không chặn hành động | Điều kiện dừng thực thi trên đường quyết định |
| Chưa ghi được log thì ghi sau | Có thể mất bằng chứng bắt buộc | Bộ đệm bền vững có giới hạn hoặc ngừng ngoại lệ |
| Health 200 là đã phục hồi | Kiểm soát thực tế có thể vẫn sai | Điều kiện phản hồi hợp lệ và cửa sổ ổn định |
| Mọi sự cố đều nhận cùng ngoại lệ | Bỏ thêm kiểm soát ngoài dự kiến | Chỉ đúng phụ thuộc và lớp lỗi đã đánh giá |
| Hết hạn thì tự gia hạn nếu còn lỗi | Biến ngoại lệ thành trạng thái thường trực | Dừng và xử lý theo thẩm quyền, không tự reset |

Fail open có kiểm soát cần một lập luận rủi ro và một tập ràng buộc được thực thi đồng thời. Có thể kiểm chứng được hành động nào còn được phép, vì sao, đến khi nào, trong khối lượng bao nhiêu và bằng chứng nào cho thấy ngoại lệ đã dừng mới là cơ sở để chấp nhận thiết kế đó.
