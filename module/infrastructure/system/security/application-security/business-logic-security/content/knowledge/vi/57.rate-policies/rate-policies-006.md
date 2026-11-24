# Rate policy disclosure — Công bố chính sách giới hạn tần suất

## 1. Bài toán: client cần biết gì để sử dụng đúng?

Trong chương **Rate Policies** của bảo mật logic nghiệp vụ, *rate policy disclosure* là việc quyết định thông tin nào về chính sách giới hạn được công bố, cho ai, qua kênh nào và với độ chính xác nào. “Disclosure” ở đây bao gồm cả công bố có chủ đích để hỗ trợ tích hợp và tiết lộ ngoài ý muốn qua phản hồi, header, tài liệu hoặc công cụ hỗ trợ.

Ví dụ, API tạo yêu cầu hoàn tiền cần giúp đối tác biết khi nào nên thử lại. Nhưng phản hồi không nên cho biết một đơn hàng của người khác đã có bao nhiêu lần hoàn tiền, tài khoản nào đang bị theo dõi hay điểm rủi ro nào khiến yêu cầu bị chặn.

Mục tiêu của bài học:

- Xác định phần hợp đồng sử dụng cần minh bạch và phần quyết định chống lạm dụng cần giữ nội bộ.
- Thiết kế phản hồi hạn mức có ích nhưng không tạo kênh dò tài khoản, đối tượng hoặc hoạt động của tenant khác.
- Gắn thông tin công bố với quyền theo đối tượng, trạng thái nghiệp vụ, transaction và idempotency.
- Nhận diện tình huống client bị chặn đúng nhưng hệ thống vẫn làm lộ thông tin hoặc tạo tác dụng phụ trùng.

Biết được hạn mức công khai không được giúp người dùng vượt quyền hoặc phá quy tắc nghiệp vụ. Hệ thống phải tiếp tục an toàn khi đối tác biết rõ cách sử dụng hạn mức được cấp.

## 2. Phân biệt ba lớp thông tin

| Lớp thông tin | Ví dụ | Mục đích |
|---|---|---|
| Hợp đồng chính sách công khai | Tối đa 5 lệnh tạo hoàn tiền mới trong cửa sổ trượt 60 giây cho mỗi merchant | Giúp đối tác thiết kế hàng đợi và dự toán lưu lượng |
| Trạng thái hạn mức tại thời điểm phản hồi | Cần chờ ít nhất 12 giây theo các giới hạn công khai đang chặn | Hướng dẫn điều tiết và retry |
| Cơ chế thực thi, chống lạm dụng nội bộ | Khóa lưu bộ đếm, tín hiệu liên kết tài khoản, trọng số rủi ro, ngưỡng điều tra | Vận hành và ngăn hành vi lạm dụng |

Không mặc định rằng công khai lớp thứ nhất đồng nghĩa được công khai toàn bộ lớp thứ hai và thứ ba.

Đặc biệt, có sự khác nhau giữa:

- **Rate limit:** giới hạn tốc độ hoặc số lần thao tác trong một khoảng thời gian.
- **Business quota:** quyền sử dụng tài nguyên nghiệp vụ, chẳng hạn số lượt khuyến mại được cấp.
- **Business invariant:** điều kiện luôn phải đúng, chẳng hạn tổng số tiền hoàn thành công không vượt số tiền đã thanh toán.

Một quota nghiệp vụ có thể có chu kỳ theo thời gian nhưng vẫn cần cách xử lý và thông báo riêng. Không biến mọi lỗi hết quyền lợi, sai trạng thái hoặc thiếu quyền thành lỗi “hãy chờ rồi thử lại”.

OWASP API6:2023 mô tả rủi ro khi luồng nghiệp vụ nhạy cảm bị tự động hóa và sử dụng quá mức. Vì vậy, chính sách phải xuất phát từ tác hại đối với nghiệp vụ, không chỉ từ số HTTP request. [OWASP API6:2023](https://api-security.owasp.org/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/)

### 2.1. Rate limit không thay thế kiểm soát nghiệp vụ

Giả sử một merchant còn quyền gửi lệnh tạo hoàn tiền. Điều đó không có nghĩa merchant được:

- Hoàn tiền cho đơn hàng thuộc merchant khác.
- Hoàn số tiền lớn hơn phần còn được hoàn.
- Bỏ qua bước phê duyệt bắt buộc.
- Gửi lại cùng một ý định để tạo nhiều giao dịch hoàn tiền.

Về mặt thiết kế:

~~~text
Có thể tiếp nhận lệnh mới
    = xác thực hợp lệ
    AND được phép thao tác trên đúng đối tượng
    AND chuyển trạng thái hợp lệ
    AND bất biến nghiệp vụ được giữ
    AND các giới hạn áp dụng cho phép tiếp nhận
    AND ý định chưa được thực hiện trùng
~~~

Đây là quan hệ điều kiện, không phải thứ tự thực thi bắt buộc. Hệ thống còn cần một bộ giới hạn sơ bộ trước xác thực để chống cạn tài nguyên. Những kiểm tra có ảnh hưởng tới tính đúng đắn phải được kiểm tra lại trong ranh giới đồng thời thích hợp.

## 3. Xác định người nhận và mức độ được biết

### 3.1. Ma trận công bố

| Thông tin | Người nhận phù hợp | Cách công bố đề xuất |
|---|---|---|
| Hạn mức chung của API hoặc gói sản phẩm công khai | Người đọc tài liệu | Nêu phạm vi, đơn vị, cửa sổ thời gian, burst nếu có |
| Hạn mức riêng trong hợp đồng của tenant | Thành viên có quyền xem hợp đồng hoặc quản trị tenant đó | API hoặc trang quản trị đã kiểm tra quyền |
| Lượng còn lại của riêng một credential | Chủ thể có quyền đối với credential | Chỉ trả nếu có ích và không suy ra dữ liệu nhạy cảm khác |
| Lượng còn lại của ngân sách dùng chung toàn tenant | Vai trò được phép xem mức sử dụng chung | Có thể tổng hợp hoặc làm thô; không mặc định mọi thành viên đều được xem |
| Bộ đếm gắn với email, số điện thoại hoặc đơn hàng bất kỳ | Người chưa chứng minh quyền liên quan | Không công bố số đếm, khóa hoặc trạng thái tồn tại |
| Điểm rủi ro và điều kiện phát hiện gian lận | Nhóm vận hành được phân quyền | Giữ ở kênh nội bộ, có audit |
| Khóa Redis, tên node, địa chỉ dịch vụ, ID luật nội bộ | Thành phần vận hành cần thiết | Không đưa vào hợp đồng API bên ngoài |

“Cùng tenant” chưa đủ để kết luận được biết mọi thông tin của tenant. Một nhân viên chỉ xử lý một nhóm đơn hàng có thể không được xem tổng lưu lượng hoàn tiền của cả doanh nghiệp.

Làm tròn số không tự động bảo vệ riêng tư. Nếu một người liên tục lấy mẫu chỉ số tổng hợp, họ vẫn có thể suy ra hoạt động của đồng nghiệp. Khi không có lý do sử dụng rõ ràng, bỏ chỉ số đó thường dễ bảo vệ hơn.

### 3.2. Thông tin gián tiếp cũng là disclosure

Ngay cả khi body không có dữ liệu nhạy cảm, hệ thống vẫn có thể tiết lộ qua:

- `Retry-After` thay đổi theo bộ đếm của tài khoản đích.
- Header quota xuất hiện chỉ khi đơn hàng thực sự tồn tại.
- Một mã lỗi riêng dành cho tài khoản bị đánh dấu gian lận.
- Thời gian phản hồi khác biệt do nhánh xử lý tồn tại và không tồn tại.
- Endpoint “xem hạn mức” nhận tùy ý `tenantId`, `accountId` hoặc `email`.
- Nội dung debug do gateway thêm vào sau khi application đã lọc body.

Cần đánh giá cả phản hồi cuối cùng mà người gọi nhận được, bao gồm gateway, proxy, SDK và giao diện.

### 3.3. Ví dụ luồng khôi phục tài khoản

Một API nhận email để gửi hướng dẫn khôi phục. Nếu email tồn tại thì trả “còn 2 lần gửi”, còn email không tồn tại thì không có chỉ số đó, API trở thành công cụ dò tài khoản.

Thiết kế phù hợp có thể dùng thông báo:

> Nếu thông tin phù hợp với tài khoản, hệ thống sẽ xử lý yêu cầu. Vui lòng chờ trước khi gửi lại.

Không công bố bộ đếm của email đích cho người chưa xác thực. Nếu cần báo tạm chặn, chỉ dùng thông tin an toàn về phạm vi của người gọi hoặc thời gian chờ công khai không phụ thuộc sự tồn tại của tài khoản. Kiểm tra cả header và các nhánh thời gian xử lý; dùng cùng một câu thông báo chưa đủ để loại bỏ kênh dò.

Bộ giới hạn theo người nhận vẫn có thể tồn tại ở server để giảm email bombing. Việc giữ riêng tư phản hồi không thay thế chính sách chống việc kẻ xấu cố ý làm cạn lượt của nạn nhân.

## 4. Một hợp đồng rate policy phải đủ rõ

Câu “API giới hạn 5 request mỗi phút” để lại nhiều cách hiểu. Đối tác cần biết ít nhất các nội dung sau:

| Thành phần | Câu hỏi phải trả lời |
|---|---|
| Thao tác | Áp dụng riêng endpoint, nhóm endpoint hay toàn bộ ý định nghiệp vụ? |
| Chủ thể tính hạn mức | Theo merchant, tài khoản, credential hay tổ hợp nào? |
| Đơn vị tính | Một HTTP request, một đối tượng trong batch hay một lệnh nghiệp vụ mới? |
| Thời gian | Cửa sổ cố định, cửa sổ trượt hay cơ chế nạp token? |
| Burst | Có được dồn lưu lượng trong thời gian ngắn không? |
| Phạm vi chia sẻ | Đổi API key, phiên đăng nhập hoặc kênh gọi có tạo ngân sách mới không? |
| Lỗi và retry | Yêu cầu bị từ chối, timeout hoặc replay idempotency được tính thế nào? |
| Nhiều giới hạn | Hạn mức ngắn hạn, dài hạn và giới hạn đồng thời phối hợp ra sao? |
| Thông tin trả về | Trường nào là snapshot, trường nào chỉ là gợi ý, trường nào có thể vắng mặt? |
| Thay đổi | Phiên bản chính sách và quy trình thông báo thay đổi ở đâu? |

Không công bố một quy tắc chính xác mà hệ thống không có khả năng thực thi. Nếu giới hạn chỉ được đồng bộ trễ giữa các vùng, tài liệu phải phản ánh mức đảm bảo thực tế. Khi một số lượng là ràng buộc nghiệp vụ cứng, cần cơ chế lưu trữ và điều phối đủ mạnh để giữ ràng buộc đó.

### 4.1. Hợp đồng minh họa cho tạo hoàn tiền

Các số dưới đây là giả định của ví dụ, không phải giá trị khuyến nghị cho mọi hệ thống:

~~~text
Policy công khai: refund-create-v1
Thao tác: tiếp nhận lệnh tạo hoàn tiền mới
Chủ thể: merchant đã xác thực
Ngân sách chia sẻ: mọi API key và kênh tạo hoàn tiền của merchant
Hạn mức: tối đa 5 lệnh được tiếp nhận trong cửa sổ trượt 60 giây
Đơn vị: một ý định tạo hoàn tiền mới được lưu thành công

Lệnh không hợp lệ hoặc không đủ quyền:
    không tiêu lượt tạo mới; vẫn chịu giới hạn request đầu vào.

Replay cùng idempotency key và cùng payload:
    không tiêu thêm lượt tạo mới; vẫn chịu giới hạn request đầu vào.

Cùng key nhưng payload khác:
    từ chối do xung đột idempotency.

Lệnh đã được tiếp nhận nhưng bên thanh toán xử lý thất bại sau đó:
    vẫn tính một lượt tiếp nhận.

Quyền và trạng thái nghiệp vụ:
    được kiểm tra độc lập với hạn mức.
~~~

Giới hạn theo merchant không được lấy từ `merchantId` tùy ý trong body. Merchant phải được xác định từ ngữ cảnh xác thực và quan hệ ủy quyền phía server. Nếu đổi API key tạo ra ngân sách mới trong khi tài liệu nói dùng chung, chính sách đã bị thực thi sai.

Nếu API hỗ trợ batch, cần định nghĩa đơn vị và cơ chế toàn bộ thành công hoặc thành công từng phần. Một batch gồm 100 lệnh không được âm thầm chỉ tính một lượt nếu mục đích chính sách là hạn chế số ý định nghiệp vụ.

## 5. Thiết kế phản hồi mà client có thể sử dụng

### 5.1. Dùng đúng ý nghĩa HTTP

HTTP `429 Too Many Requests` biểu thị việc gửi quá nhiều yêu cầu trong một khoảng thời gian. RFC 6585 cho phép kèm `Retry-After` và quy định phản hồi 429 không được cache lưu trữ. RFC này không bắt buộc một cách xác định chủ thể hoặc thuật toán đếm duy nhất. [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)

Không dùng 429 để che mọi nguyên nhân từ chối:

| Tình huống | Cách xử lý trong hợp đồng ví dụ |
|---|---|
| Vượt tốc độ tiếp nhận lệnh | 429 và thông tin chờ an toàn nếu xác định được |
| Không có quyền trên đơn hàng | Phản hồi theo hợp đồng phân quyền; có thể che sự tồn tại của đối tượng |
| Đơn chưa được phê duyệt hoặc hết phần tiền được hoàn | Lỗi miền nghiệp vụ được tài liệu hóa, chẳng hạn 409 trong API này |
| Cùng idempotency key nhưng payload khác | Xung đột idempotency, chẳng hạn 409 |
| Dịch vụ giới hạn hoặc hạ tầng không sẵn sàng | Phản hồi lỗi khả dụng phù hợp, chẳng hạn 503 khi phù hợp với ngữ nghĩa |

Các mã cho lỗi nghiệp vụ ở đây là lựa chọn hợp đồng minh họa. Đặc biệt, lỗi hạ tầng không chứng minh người gọi đã vượt hạn mức.

### 5.2. Phản hồi công khai tối thiểu

Với chính sách hoàn tiền đã công bố và người gọi được phép biết:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 12

{
  "code": "RATE_LIMITED",
  "message": "Tạm thời vượt tần suất tiếp nhận yêu cầu hoàn tiền.",
  "policy": "refund-create-v1",
  "retryAfterSeconds": 12,
  "requestId": "req-example-7f2a"
}
~~~

`policy` và `retryAfterSeconds` trong body là các trường của hợp đồng ứng dụng trong ví dụ. Chúng không phải trường JSON bắt buộc của HTTP. `requestId` là mã tương quan do server tạo, không chứa danh tính, điểm rủi ro hay cấu trúc hạ tầng.

`Retry-After` có thể là một HTTP-date hoặc một số nguyên không âm biểu thị số giây cần chờ. Giá trị `12` ở trên là số giây, không phải mili giây hay Unix timestamp. [RFC 9110, mục 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)

Không đưa vào phản hồi:

~~~json
{
  "storageKey": "rate:merchant:internal-42:refund",
  "riskScore": 0.93,
  "internalRule": "linked-accounts-review",
  "relatedAccountCount": 7
}
~~~

Việc trả dữ liệu như trên vẫn là rò rỉ dù người gọi thật sự đang bị rate limit và dù HTTP status đã chính xác.

Với quyết định chống lạm dụng nhạy cảm, có thể chỉ trả mã ổn định và hướng dẫn hỗ trợ chung, bỏ chi tiết chính sách nội bộ và thời gian chờ nhạy cảm. Không nói “đợi đúng 12 giây sẽ được phép” khi quyết định còn phụ thuộc đánh giá rủi ro hoặc phê duyệt chưa biết thời điểm kết thúc.

### 5.3. Không biến snapshot thành lời hứa

Nếu công bố số lượt còn lại, phải xác định rõ:

- Đây là số lượt của phạm vi nào và được quan sát vào thời điểm nào.
- Số lượt đã trừ lệnh hiện tại hay chưa.
- Có dùng chung với các tiến trình hoặc credential khác không.
- Có phải số chính xác hay số ước lượng.
- Giá trị này không đặt chỗ và không bảo đảm yêu cầu tiếp theo thành công.

Ví dụ, hai worker đều đọc thấy còn một lượt. Chỉ việc tiếp nhận nguyên tử phía server mới quyết định worker nào được dùng lượt đó. Client không được dùng header làm bằng chứng đã được cấp quyền tạo giao dịch.

Không trả số âm để phản ánh trạng thái kỹ thuật khó hiểu. Nếu không có cách tính chỉ số đủ rõ hoặc đủ an toàn, hãy bỏ chỉ số tùy chọn thay vì tự tạo một con số.

Nếu dùng header hạn mức ngoài `Retry-After`, phải chọn và tài liệu hóa hợp đồng cụ thể: tên trường, cú pháp, đơn vị, phạm vi và cách biểu diễn nhiều chính sách. Không mặc định các gateway dùng tên gần giống nhau sẽ có cùng ngữ nghĩa.

### 5.4. Cache, CORS và tính nhất quán của phản hồi

Với dữ liệu hạn mức theo người gọi, thiết kế ví dụ dùng `Cache-Control: no-store` và kiểm tra CDN/gateway không lưu hoặc tái sử dụng phản hồi giữa các chủ thể. Với 429, yêu cầu không lưu cache còn được nêu trực tiếp trong RFC 6585. [RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)

Nếu ứng dụng trình duyệt cần đọc `Retry-After` từ phản hồi khác origin, cấu hình CORS phải cho phép origin phù hợp và expose header cần thiết, chẳng hạn:

~~~http
Access-Control-Expose-Headers: Retry-After
~~~

Expose header phục vụ khả năng đọc của JavaScript; nó không thay thế xác thực hay kiểm tra quyền. Đồng thời kiểm tra gateway không thêm header debug hoặc ghi đè thời gian chờ bằng thông tin của một chính sách khác.

## 6. Nhiều hạn mức và ý nghĩa thời gian chờ

Một lệnh có thể đồng thời chịu giới hạn theo người dùng, merchant và thao tác. Nếu các giới hạn đều phải thỏa, thời điểm sớm nhất có thể vượt qua các giới hạn công khai đang chặn được tính từ giới hạn hồi phục muộn nhất.

Ví dụ tại cùng thời điểm:

~~~text
Giới hạn công khai A: có thể tiếp nhận sau 8 giây.
Giới hạn công khai B: có thể tiếp nhận sau 35 giây.

Thời gian chờ tối thiểu theo hai giới hạn: max(8, 35) = 35 giây.
~~~

Kết quả chỉ có ý nghĩa theo trạng thái hiện tại và giả định không có lưu lượng khác tiêu ngân sách. Đây không phải lời hứa được tiếp nhận sau 35 giây.

Cũng cần phân biệt:

- **Fixed window:** có thể có mốc mở cửa sổ mới theo lịch server.
- **Sliding window:** lệnh cũ rời cửa sổ dần; không nhất thiết có một thời điểm “reset tất cả”.
- **Token bucket:** đủ token cho một lệnh mới không đồng nghĩa bucket đã đầy.
- **Giới hạn đồng thời:** thời điểm có chỗ trống phụ thuộc lệnh khác hoàn tất; có thể chưa dự đoán được.

Khi lệnh có trọng số, thời gian chờ phải tính cho đủ chi phí của chính lệnh đó. Nếu chi phí lớn hơn sức chứa tối đa, đợi thêm không giải quyết được; cần phản hồi theo lỗi hợp đồng thích hợp thay vì hướng dẫn retry vô hạn.

Không tính thời gian chờ tổng hợp rồi vô tình tiết lộ bộ đếm bí mật của một tài khoản khác. Khi không có ước lượng vừa đúng vừa an toàn, có thể bỏ `Retry-After` và trả hướng dẫn điều tiết chung theo hợp đồng. Nếu có làm tròn thời gian chờ để giảm độ chi tiết, làm tròn lên để tránh chủ động hướng dẫn client thử quá sớm.

## 7. Tách quyết định nội bộ khỏi dữ liệu được phép công bố

Thiết kế nguy hiểm thường serialize thẳng đối tượng quyết định của rate limiter. Đối tượng đó có thể chứa khóa bộ đếm, luật nội bộ và metadata phục vụ điều tra.

Nên có bước ánh xạ tường minh sang DTO công khai, chỉ lấy các trường đã được cho phép. Ví dụ Java 17 dưới đây chỉ minh họa bộ dựng phản hồi cho API hoàn tiền; không phải mã triển khai bộ giới hạn hoặc transaction:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

final class RefundRateDisclosure {
    // Được tạo SAU khi đánh giá quyền xem từng loại thông tin.
    record PublicAdvice(
            boolean discloseRefundPolicy,
            Long safeRetryAfterSeconds) {

        PublicAdvice {
            if (safeRetryAfterSeconds != null
                    && safeRetryAfterSeconds < 0) {
                throw new IllegalArgumentException("Negative retry delay");
            }
        }
    }

    record ErrorBody(
            String code,
            String message,
            String policy,
            Long retryAfterSeconds,
            String requestId) {}

    record Rejection(
            int status,
            Map<String, String> headers,
            ErrorBody body) {}

    static Rejection rejected(PublicAdvice advice, String requestId) {
        var headers = new LinkedHashMap<String, String>();
        headers.put("Cache-Control", "no-store");
        headers.put("Content-Type", "application/json");

        Long wait = advice.safeRetryAfterSeconds();
        if (wait != null) {
            headers.put("Retry-After", Long.toString(wait));
        }

        String policy = advice.discloseRefundPolicy()
                ? "refund-create-v1"
                : null;

        var body = new ErrorBody(
                "RATE_LIMITED",
                "Tạm thời chưa thể tiếp nhận yêu cầu. Vui lòng thử lại sau.",
                policy,
                wait,
                requestId);

        return new Rejection(429, Map.copyOf(headers), body);
    }
}
~~~

Các ranh giới quan trọng của ví dụ:

1. `PublicAdvice` chỉ chứa kết quả đã được kiểm tra quyền công bố. Không truyền trực tiếp đối tượng của kho bộ đếm vào serializer.
2. Quyền xem tên chính sách và quyền xem thời gian chờ được đánh giá riêng. Một giới hạn công khai không tự động làm mọi thông tin trạng thái trở thành công khai.
3. Tầng HTTP cần cấu hình bỏ trường tùy chọn có giá trị `null` nếu hợp đồng yêu cầu trường đó vắng mặt.
4. `requestId` phải do server quản lý. Không phản chiếu nguyên văn một header bất kỳ do người gọi cung cấp.
5. Bộ dựng này chỉ dùng cho quyết định rate limit. Lỗi phân quyền, state machine và lỗi khả dụng đi qua hợp đồng tương ứng.

Nếu cần hỗ trợ khách hàng, dùng `requestId` để truy xuất lý do chi tiết trong hệ thống nội bộ có phân quyền. Mã hỗ trợ không phải quyền truy cập tự động vào mọi bản ghi liên quan.

## 8. Gắn disclosure với transaction và idempotency

### 8.1. Luồng xử lý tham chiếu

~~~mermaid
flowchart TD
    A[Yêu cầu đến] --> B[Giới hạn request sơ bộ]
    B --> C[Xác thực và xác định chủ thể]
    C --> D[Kiểm tra quyền trên đối tượng]
    D --> E[Đọc hoặc claim idempotency an toàn]
    E --> F{Đã có ý định?}
    F -->|Có| G[Kiểm tra payload và quyền đọc kết quả]
    G --> H[Trả kết quả cũ hoặc trạng thái đang xử lý]
    F -->|Chưa| I[Kiểm tra lại quyền và invariant khi ghi]
    I --> J[Tiếp nhận nguyên tử với quota và idempotency]
    J -->|Bị giới hạn| K[Ánh xạ thông tin công khai được phép]
    K --> L[Phản hồi 429]
    J -->|Thành công| M[Lưu lệnh và outbox]
    M --> N[Worker xử lý tác dụng phụ]
~~~

Sơ đồ lược bỏ các nhánh lỗi để làm rõ quan hệ. Claim idempotency phải an toàn khi nhiều request cùng đến; không triển khai bằng cách đọc “chưa có” rồi ghi mà thiếu ràng buộc duy nhất hoặc điều phối tương đương.

Trong hợp đồng hoàn tiền ở trên, một phương án là giữ bản ghi idempotency, sổ lượt tiếp nhận và lệnh hoàn tiền trong cùng cơ sở dữ liệu. Transaction tiếp nhận cần điều phối truy cập theo merchant để việc đếm cửa sổ trượt và thêm lượt mới không bị vượt do ghi đồng thời. Chỉ dùng `COUNT` rồi `INSERT` trong transaction ở mức cô lập thông thường chưa tự bảo đảm điều này.

Lệnh được tiếp nhận, lượt được ghi và outbox được lưu phải có quan hệ commit rõ ràng. Worker đọc outbox không được tạo hoàn tiền ngoài hệ thống lần thứ hai khi nhận lại sự kiện.

Nếu ingress limiter nằm ở Redis còn giao dịch hoàn tiền nằm ở SQL, `@Transactional` của SQL không tự bao trùm Redis. Cần xác định rõ Redis đang giới hạn lần thử, còn quota tiếp nhận nghiệp vụ nằm ở đâu. Nếu thực sự phải giữ quota ở kho khác, thiết kế reservation, xác nhận, hết hạn, đối soát và lỗi giữa chừng trước khi công bố cách tính.

### 8.2. Retry không được tạo thêm ý định

Giả sử client gửi một lệnh với idempotency key, server đã commit nhưng phản hồi bị mất. Lần gọi lại với cùng key và payload phải tìm thấy ý định cũ, không tạo lệnh hoàn tiền mới hoặc tiêu thêm lượt tạo mới theo hợp đồng ví dụ.

Tuy nhiên:

- Replay vẫn chịu giới hạn bảo vệ request đầu vào để tránh làm cạn tài nguyên.
- Idempotency key phải được giới hạn theo chủ thể và thao tác; không dùng key chung toàn hệ thống mà bỏ qua quyền sở hữu.
- Chỉ trả kết quả cũ sau khi người gọi còn quyền xem kết quả đó.
- Cùng key nhưng payload khác phải được phát hiện.
- Phải công bố thời gian lưu key và cách xử lý sau khi hết hạn.
- Với hoàn tiền, cần ràng buộc nghiệp vụ và đối soát bền vững để xử lý việc gửi lại sau thời gian lưu key; không chỉ dựa vào TTL của cache.

Nếu yêu cầu bị 429 trước khi được tiếp nhận, hợp đồng phải xác định trạng thái idempotency để lần thử lại có thể tiến lên. Không lưu một 429 tạm thời như kết quả vĩnh viễn khiến cùng key không bao giờ được xử lý.

### 8.3. Quy tắc tiền và phê duyệt vẫn phải giữ

Ngay cả khi hạn mức cho phép, transaction tiếp nhận phải bảo vệ trạng thái có liên quan:

~~~text
Đơn thuộc merchant đang thao tác.
Lệnh đã được phê duyệt nếu quy trình yêu cầu.
Số tiền hoàn phải được xác định và kiểm tra phía server.
Tiền đã hoàn + tiền đang được giữ cho lệnh mới <= số tiền được phép hoàn.
Mỗi ý định chỉ tạo một tác dụng phụ nghiệp vụ.
~~~

Phần tiền đang giữ cho các lệnh chờ xử lý cũng quan trọng. Nếu chỉ cộng giao dịch hoàn thành công, hai lệnh chờ đồng thời có thể cùng được tiếp nhận và sau đó vượt tổng tiền được hoàn.

Giấu số lượt còn lại không sửa được lỗi này. Giới hạn tần suất cũng không sửa được lỗi này.

## 9. Hướng dẫn client retry có giới hạn

Một hợp đồng tốt đi kèm hành vi client rõ ràng:

1. Với 429, đọc thời gian chờ được công bố nếu có và điều tiết hàng đợi theo đúng phạm vi ngân sách dùng chung.
2. Dùng backoff có giới hạn và thêm jitter để nhiều worker không thức dậy cùng lúc.
3. Nếu có `Retry-After`, không tự rút ngắn thời gian đó. Nếu thời gian chờ vượt deadline của thao tác, dừng hoặc đưa vào quy trình chờ phù hợp.
4. Giữ nguyên idempotency key cho cùng một ý định. Không tạo key mới chỉ để né phản hồi trước đó.
5. Không retry vô hạn lỗi phân quyền, payload hoặc trạng thái nghiệp vụ.
6. Sau timeout hoặc lỗi kết nối, tra cứu trạng thái hoặc retry theo hợp đồng idempotency; không suy ra rằng giao dịch chưa xảy ra.
7. Đặt deadline tổng, số lần thử tối đa và cơ chế báo lỗi cho người dùng.

Một công thức minh họa cho thời gian chờ khi có gợi ý an toàn:

~~~text
delay = max(serverDelay, clientBackoff) + positiveJitter
~~~

Ở đây `positiveJitter` là lượng ngẫu nhiên không âm. Khi server không đưa ra thời gian chờ, client dùng backoff đã tài liệu hóa. Công thức không cho phép vượt deadline vô hạn hoặc bỏ qua bước xác minh kết quả của một thao tác có thể đã commit.

## 10. Các tình huống kiểm thử cần thiết

Kiểm thử phải kiểm tra cả điều đã bị từ chối, điều đã bị tiết lộ và tác dụng phụ đã xảy ra. Bảng dưới đây là kịch bản cho bài học, không phải kết quả kiểm thử một triển khai cụ thể.

| Tình huống | Điều cần xác minh |
|---|---|
| Người gọi đổi `merchantId` trong body | Không đổi được chủ thể tính hạn mức hoặc quyền trên đơn |
| Đổi API key trong cùng merchant | Không nhận ngân sách mới nếu hợp đồng quy định dùng chung |
| Truy vấn đơn không thuộc quyền và đơn không tồn tại | Không có header hoặc body tiết lộ số lượt, trạng thái hay sự tồn tại ngoài hợp đồng |
| Dò email ở API khôi phục tài khoản | Không phân biệt tài khoản qua bộ đếm, header hoặc nhánh xử lý dễ quan sát |
| Thành viên không có quyền xem tổng usage | Không nhận snapshot quota chung của tenant |
| Hai lệnh đến khi chỉ còn một lượt | Tối đa một lệnh mới được tiếp nhận theo quota cứng |
| Hai lệnh hoàn tiền khác key cùng đến | Tổng tiền đã hoàn và đang giữ không vượt số tiền hợp lệ |
| Lặp cùng key và cùng payload sau timeout | Không có thêm lệnh, không thêm tác dụng phụ, không tiêu lượt tạo mới |
| Lặp cùng key nhưng payload khác | Phản hồi xung đột; không trả nhầm kết quả cũ |
| Đổi key liên tục hoặc gửi batch lớn | Không vượt bất biến và đơn vị tính của chính sách |
| Một giới hạn hồi phục sau 8 giây, giới hạn khác sau 35 giây | Không công bố 8 giây như thời gian đủ cho cả hai |
| Luật nội bộ nhạy cảm kích hoạt | Không lộ rule ID, điểm rủi ro hoặc trạng thái tài khoản liên quan |
| Gateway hoặc limiter lỗi | Không gán nhầm thành người dùng vượt hạn mức; không công bố snapshot bịa |
| CDN, gateway và trình duyệt cùng tham gia | Không chia sẻ dữ liệu hạn mức giữa người gọi; header cuối cùng nhất quán |
| Chuyển phiên bản chính sách | Tài liệu, cấu hình thực thi, mã chính sách và SDK thống nhất |

Với kiểm thử đồng thời, cần quan sát số lệnh thực sự được commit và số tác dụng phụ, không chỉ đếm HTTP 200 hoặc 429. Với kiểm thử disclosure, thu cả status, header, body và các khác biệt thời gian có thể lặp lại.

Các thử nghiệm gây lưu lượng hoặc tác dụng phụ nghiệp vụ cần chạy trong môi trường kiểm thử có dữ liệu và ngân sách kiểm soát.

## 11. Vận hành và thay đổi chính sách

### 11.1. Tài liệu, API và hỗ trợ phải nhất quán

Đặt tên phiên bản công khai ổn định, chẳng hạn `refund-create-v1`. ID này mô tả hợp đồng bên ngoài, không phải tên luật nội bộ. Chính sách chống lạm dụng có thể tiến hóa mà không phải công bố cấu trúc phát hiện chi tiết.

Tài liệu nên giải thích rằng việc tuân thủ rate limit không cấp quyền vượt điều kiện bảo mật và nghiệp vụ khác. Đồng thời, khi thay đổi phần hạn mức đã cam kết với khách hàng, phải quản lý thay đổi theo hợp đồng và thông báo phù hợp.

Một quy trình thay đổi có thể gồm:

1. Đánh giá tác động với client đang dùng và luồng nghiệp vụ chịu ảnh hưởng.
2. Đồng bộ tài liệu, cấu hình, phản hồi và SDK.
3. Quan sát quyết định ở chế độ chưa chặn nếu phù hợp.
4. Triển khai theo nhóm, theo dõi tỷ lệ 429 và retry.
5. Có cơ chế quay lại phiên bản trước khi phát hiện chặn nhầm.

Việc bổ sung luật khẩn cấp không nên làm phản hồi vô tình lộ phân loại gian lận hoặc khuyến khích client retry dồn dập.

### 11.2. Log chi tiết ở đúng kênh

Log nội bộ có thể ghi mã chính sách, phạm vi áp dụng, quyết định, nguyên nhân, phiên bản cấu hình và request ID theo nhu cầu điều tra. Giới hạn truy cập và thời gian lưu; tránh ghi token, khóa bí mật, toàn bộ idempotency key hay dữ liệu cá nhân không cần thiết.

Không ghi một lý do chi tiết rồi đưa nguyên văn nó ra API hỗ trợ công khai. Công cụ hỗ trợ cũng phải kiểm tra người dùng đang hỏi về tenant và giao dịch mà họ có quyền xem.

Metric nên giúp phân biệt vượt hạn mức công khai, chặn chống lạm dụng, lỗi backend và lỗi nghiệp vụ. Không đưa email, số điện thoại hoặc từng object ID vào nhãn metric có số lượng giá trị không kiểm soát.

## 12. Ghi nhớ khi thiết kế rate policy disclosure

Chính sách công khai cần đủ rõ để người dùng hợp lệ điều tiết lưu lượng, hiểu đơn vị bị tính và xử lý retry. Thông tin thời điểm chạy chỉ nên được trả khi người nhận có quyền biết và khi ý nghĩa đủ chính xác để sử dụng.

Cơ chế chống lạm dụng nội bộ cần có kênh quan sát riêng. Giữ kín ngưỡng nhạy cảm là một lựa chọn kiểm soát thông tin, không phải nền tảng duy nhất của an toàn.

Với API hoàn tiền trong bài, thiết kế đạt mục tiêu khi merchant biết cách gọi đúng, không dò được dữ liệu ngoài quyền, và dù biết hạn mức vẫn không thể vượt phê duyệt, sửa giá trị tiền, vượt tổng tiền được hoàn hoặc tạo tác dụng phụ trùng.
