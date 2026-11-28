# Request smuggling defense

## 1. Request smuggling là lỗi về ranh giới request

HTTP request smuggling xuất hiện khi các thành phần trong một chuỗi HTTP không thống nhất cách xác định ranh giới của request. Một phần dữ liệu mà tầng trước coi là body có thể bị tầng sau hiểu là một request khác hoặc dữ liệu của request kế tiếp.

Vấn đề cốt lõi không phải một chuỗi từ khóa trong body, mà là sự khác nhau giữa các parser, quá trình chuyển đổi giao thức và trạng thái kết nối.

Một hệ thống điển hình:

```text
Client → CDN → reverse proxy → gateway → application server
```

Nếu một thành phần kiểm tra quyền hoặc định tuyến dựa trên cách hiểu A, còn thành phần phía sau thực thi theo cách hiểu B, kiểm soát an toàn có thể bị vượt qua.

Trong thiết kế yêu cầu bảo mật, mục tiêu là:

> Mỗi thông điệp được chấp nhận phải có một ranh giới xác định, một cách diễn giải nhất quán qua các chặng, và không để lỗi framing ảnh hưởng tới request khác.

### 1.1. Vì sao connection reuse làm hậu quả lan rộng?

Để giảm chi phí kết nối, proxy thường tái sử dụng kết nối tới backend cho nhiều request. Dữ liệu còn dư trên một kết nối có thể ảnh hưởng tới request khác nếu các parser đã mất đồng bộ.

Hậu quả có thể gồm:

- Một request không đi qua đầy đủ kiểm soát ở edge.
- Request bị định tuyến theo cách không dự kiến.
- Response được liên kết với sai request.
- Dữ liệu hoặc cache bị ảnh hưởng qua ranh giới người dùng.
- Gián đoạn dịch vụ do kết nối rơi vào trạng thái không nhất quán.

Mô hình bất đồng giữa các hop và tác động của kết nối backend dùng lại được giải thích trong [nghiên cứu hướng dẫn của PortSwigger](https://portswigger.net/web-security/request-smuggling).

Không phải mọi lỗi 400 hoặc timeout đều là request smuggling. Cần bằng chứng về cách diễn giải hoặc trạng thái ranh giới, thay vì kết luận từ một dấu hiệu đơn lẻ.

### 1.2. Phạm vi của bài học

Bài học tập trung vào phòng vệ và đặc tả yêu cầu:

- Framing của HTTP/1.1.
- Header mâu thuẫn hoặc nhập nhằng.
- HTTP/2 và ranh giới chuyển sang HTTP/1.1.
- Request body không hoàn chỉnh.
- Connection pool và xử lý lỗi.
- Kiểm chứng bằng dữ liệu vô hại trong môi trường được kiểm soát.

Không cần xây một parser HTTP mới hoặc dựa vào payload khai thác để mô tả một yêu cầu phòng vệ rõ ràng.

## 2. Những khái niệm cần phân biệt

### 2.1. Framing và nội dung nghiệp vụ

Framing xác định thông điệp bắt đầu và kết thúc ở đâu. Sau đó ứng dụng mới diễn giải JSON, form, file hoặc dữ liệu nghiệp vụ.

Một body JSON hợp lệ không chứng minh framing HTTP hợp lệ. Ngược lại, một request được đóng khung đúng vẫn có thể chứa JSON không hợp lệ.

| Lớp | Câu hỏi |
|---|---|
| Transport | Những byte nào được truyền qua kết nối? |
| HTTP framing | Byte nào thuộc header/body của từng request? |
| HTTP semantics | Method, target và metadata có ý nghĩa gì? |
| Ứng dụng | JSON, quyền và hành động nghiệp vụ có hợp lệ không? |

Kiểm tra JSON ở controller thường đã quá muộn để giải quyết sự khác nhau giữa proxy và connector HTTP.

### 2.2. Content-Length

Content-Length biểu diễn độ dài theo octet, không phải số ký tự của một string. Việc tính theo ký tự Unicode rồi dùng làm số byte có thể làm giá trị không đúng với dữ liệu trên đường truyền.

RFC 9110 cũng quy định cách xử lý giá trị lặp và yêu cầu không chuyển tiếp Content-Length không hợp lệ, với ngoại lệ được mô tả cho những giá trị thập phân giống nhau. Xem [RFC 9110 §8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6).

Nếu ứng dụng dựng request gửi đi, nên để HTTP client được duy trì tính framing thay vì tự nối start-line, header và body thành một luồng byte.

### 2.3. Transfer-Encoding và Content-Encoding

Transfer-Encoding liên quan đến cách truyền thông điệp trên một chặng HTTP. Content-Encoding mô tả mã hóa nội dung biểu diễn, chẳng hạn nén dữ liệu.

Hai header không thay thế cho nhau. Giải nén body nghiệp vụ không đồng nghĩa đã xử lý đúng framing.

Đối với HTTP/1.1, chunked là một cơ chế framing. Các quy tắc về độ dài body và độ ưu tiên được định nghĩa trong [RFC 9112 §6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3).

Một yêu cầu phòng vệ có thể chọn tập transfer coding được hỗ trợ hẹp hơn tập mà giao thức có thể biểu diễn, miễn lựa chọn đó rõ ràng và phù hợp với client cần hỗ trợ.

### 2.4. Header TE không phải Transfer-Encoding

Tên gần giống không có nghĩa cùng vai trò. Không được dùng logic “thấy chữ TE thì xóa” như một parser bảo mật.

Quy tắc xử lý phải dựa vào tên field chính xác, phiên bản HTTP và ngữ nghĩa của field. Một lớp lọc chuỗi mơ hồ có thể bỏ sót điều cần chặn hoặc phá request hợp lệ.

## 3. Mô hình đe dọa theo từng hop

### 3.1. Kiểm kê chuỗi xử lý thực tế

Một sơ đồ cần chỉ rõ:

| Chặng | Giao thức vào/ra | Thành phần parse | Trạng thái cần quan tâm |
|---|---|---|---|
| Client → edge | HTTP/1.1 hoặc HTTP/2 | HTTP stack tại edge | Header, framing, timeout |
| Edge → gateway | Theo cấu hình thực tế | Proxy và gateway | Rewrite, chuyển đổi giao thức |
| Gateway → origin | Có thể là HTTP/1.1 | Connector ứng dụng | Pool, body và response |
| Origin → dịch vụ phụ | HTTP client nội bộ | Client và server phụ | Request được tái tạo |

Cần bao gồm CDN, WAF hoặc sidecar nếu chúng tham gia parse hoặc viết lại request. Nhãn “chỉ là proxy” không loại bỏ ranh giới tin cậy.

### 3.2. Những điểm có thể khác cách hiểu

Các nhóm khác biệt cần đánh giá:

- Một tầng chấp nhận header mà tầng khác coi là không hợp lệ.
- Một tầng giữ một giá trị lặp, tầng khác giữ giá trị khác.
- Một tầng giải mã body rồi vẫn chuyển tiếp metadata cũ.
- Một tầng bỏ qua body theo method, tầng khác vẫn đọc theo framing.
- Một tầng trả lỗi sớm nhưng tái sử dụng kết nối còn dữ liệu chưa xử lý.
- Một adapter chuyển giá trị field thành byte HTTP/1.1 không đúng.
- Một đường gọi origin bỏ qua kiểm soát của edge.

Danh sách này là cách tìm ranh giới, không phải một tập payload đầy đủ.

### 3.3. HTTPS không giải quyết bất đồng parser

TLS có thể bảo vệ dữ liệu giữa hai đầu kết nối. Hai đầu vẫn có thể diễn giải cùng byte theo hai cách khác nhau sau khi giải mã.

Vì vậy, yêu cầu HTTPS và yêu cầu chống request smuggling là những kiểm soát khác nhau. Mã hóa mọi hop không làm một parser dễ dãi trở nên nhất quán với parser phía sau.

## 4. Chọn policy xử lý HTTP/1.1 rõ ràng

Phần này đề xuất một policy phòng vệ cho API công khai giả định. Cần phân biệt quyết định của sản phẩm với mọi hành vi mà RFC cho phép.

### 4.1. Không chấp nhận hai cơ chế framing mâu thuẫn

Ví dụ chỉ gồm metadata, không phải một request khai thác hoàn chỉnh:

```text
Content-Length: <một giá trị>
Transfer-Encoding: chunked
```

RFC 9112 mô tả độ ưu tiên và cách xử lý trường hợp có cả hai field. Nó không đồng nghĩa rằng mọi hệ thống phải chấp nhận dạng đó. Policy của API giả định trong bài là từ chối tại ranh giới HTTP/1.1 đầu tiên, không chuyển tiếp tới nghiệp vụ và kết thúc kết nối theo quy tắc lỗi.

Lý do là giảm số cách diễn giải cần duy trì xuyên chuỗi. Không để edge chọn Content-Length còn origin chọn Transfer-Encoding hoặc ngược lại.

Nếu hệ thống buộc phải hỗ trợ một đường tương thích khác, phải thiết kế cách parse, tái tạo thông điệp và quản lý kết nối nhất quán cho toàn chuỗi; không chỉ xóa một header rồi giữ nguyên mọi byte còn lại.

### 4.2. Duplicate Content-Length

Một policy bảo thủ có thể từ chối:

- Nhiều field Content-Length.
- Một field chứa danh sách nhiều giá trị.
- Giá trị không hợp lệ hoặc vượt miền số được hỗ trợ.

Đây là quyết định hardening của sản phẩm giả định. Không tuyên bố mọi giá trị trùng giống nhau đều luôn bị RFC cấm; RFC 9110 có trường hợp cho phép từ chối hoặc thay bằng một giá trị duy nhất.

Nếu chọn chuẩn hóa giá trị lặp giống nhau thay vì từ chối, phải bảo đảm:

1. Tất cả giá trị đã được đọc và kiểm tra.
2. Không giá trị nào bị mất khi chuyển header thành map.
3. Kết quả phía sau chỉ có một biểu diễn hợp lệ.
4. Body được xử lý theo chính biểu diễn đó.
5. Không hop nào khôi phục lại dữ liệu thô đã loại.

Một lời gọi getHeader chỉ trả một giá trị có thể không đủ để chứng minh không có duplicate.

### 4.3. Cú pháp field và khoảng trắng

Policy cần xác định cách xử lý:

- Field name không hợp lệ.
- Khoảng trắng tại vị trí không được phép.
- Dòng header kiểu gấp cũ ngoài hợp đồng.
- Ký tự điều khiển trong tên hoặc giá trị.
- Kết thúc dòng không được hỗ trợ.
- Dòng không thể được diễn giải nhất quán.

Với một public API có client hiện đại, có thể chọn cú pháp nghiêm ngặt và từ chối dạng ngoài hợp đồng thay vì cố sửa để tương thích.

Không có quy tắc chung rằng “xóa mọi khoảng trắng” là an toàn. Khoảng trắng có thể là một phần dữ liệu hợp lệ trong field khác; cần HTTP parser hiểu vị trí và ngữ pháp.

### 4.4. Method không được quyết định tùy tiện việc bỏ body

Một lớp middleware có thể cho rằng GET không dùng body nên bỏ qua mọi byte sau header. Một tầng khác vẫn đọc chúng theo framing.

Yêu cầu cần thống nhất xử lý body cho từng method và không được tái sử dụng kết nối khi phần body đã khai báo chưa được xử lý an toàn.

Nếu API không hỗ trợ body ở một method, hãy từ chối theo policy; không âm thầm xem dữ liệu còn lại là request tiếp theo chỉ vì method đó thường không có nội dung.

### 4.5. Không dùng “repair” làm mặc định

Một proxy dễ dãi có thể nhận dữ liệu lỗi, sửa một phần rồi chuyển tiếp. Rủi ro xuất hiện nếu việc sửa không bao phủ toàn bộ ranh giới hoặc làm mất dấu thông tin mâu thuẫn.

Nguyên tắc thiết kế:

```text
Kiểm tra đầu vào theo policy
    → tạo mô hình request đã xác định
    → serialize hợp lệ cho hop kế tiếp
```

Không phải:

```text
Chuyển tiếp byte thô
    → xóa vài field nghi ngờ
    → hy vọng parser sau hiểu giống mình
```

## 5. Tái tạo request và metadata theo hop

### 5.1. Một request đã parse, một cách serialize

Nếu proxy giải mã chunked hoặc thay đổi body, metadata gửi đi phải được tạo lại từ nội dung và cách truyền thực tế.

Ví dụ:

- Body được buffer đầy đủ: HTTP stack có thể tạo Content-Length đúng theo byte gửi đi.
- Body được streaming: stack sử dụng cơ chế framing được hỗ trợ và quản lý hoàn tất.
- Chuyển phiên bản HTTP: adapter tạo cấu trúc hợp lệ của phiên bản đích.

Không giữ một Content-Length cũ sau khi đã thay đổi số byte body.

### 5.2. Không chuyển hop-by-hop metadata như dữ liệu end-to-end

Proxy cần xử lý các field dành cho một chặng theo ngữ nghĩa giao thức. Một field không được chuyển nguyên vẹn chỉ vì nó có trong map header của request.

Đặc biệt, Connection và những field liên quan không phải một danh sách tên do client được phép dùng để vô hiệu hóa kiểm soát bảo mật ở phía sau.

Hệ thống nên có chính sách cho metadata xác thực và chuyển tiếp riêng: client ngoài không được giả mạo danh tính nội bộ chỉ bằng cách đặt một header có tên giống header của gateway.

### 5.3. Authority, Host và route

Sai lệch về đích có thể kết hợp với bất đồng framing. Cần xác định một authority đã kiểm tra để dùng nhất quán cho routing, policy và request gửi tới origin.

Không để:

- WAF kiểm tra một Host nhưng gateway dùng một giá trị khác.
- Chuyển đổi giao thức chọn một authority không đúng.
- Field lặp bị từng hop xử lý theo quy tắc khác.
- Request không hợp lệ được định tuyến trước rồi mới bị từ chối ở một lớp khác.

Kiểm soát này không thay thế framing, nhưng giúp tránh một request có nhiều cách hiểu về đích.

### 5.4. Trailer không phải nơi thay đổi quyền

Nếu hỗ trợ trailer, cần xác định những field được phép và cách chúng được truyền tới ứng dụng.

Không cho phép trailer ghi đè dữ liệu định tuyến, xác thực hoặc framing đã dùng để xử lý request. Những nội dung chỉ được biết khi body hoàn tất không được âm thầm thay đổi quyết định kiểm soát đã thực hiện trước đó.

Nếu sản phẩm không có nhu cầu trailer, có thể áp dụng hợp đồng hẹp hơn với hành vi từ chối rõ ràng.

## 6. HTTP/2 và chuyển đổi sang HTTP/1.1

### 6.1. Frame không loại bỏ yêu cầu validation

HTTP/2 biểu diễn request theo stream và frame thay vì cùng dạng luồng văn bản HTTP/1.1. Tuy vậy, field và độ dài nội dung vẫn có quy tắc hợp lệ.

RFC 9113 xác định thông điệp malformed và xử lý lỗi, bao gồm trường hợp content-length không khớp nội dung. Xem [RFC 9113 §8.1.1](https://www.rfc-editor.org/rfc/rfc9113.html#section-8.1.1).

Không dùng việc “client kết nối HTTP/2” làm bằng chứng duy nhất rằng toàn hệ thống không có bất đồng giao thức.

### 6.2. Ranh giới downgrade

Ví dụ:

```text
HTTP/2 client → edge → HTTP/1.1 origin
```

Edge phải chuyển mô hình stream thành request HTTP/1.1. Nếu field chưa được validation chứa dữ liệu không phù hợp với cú pháp đích, bước chuyển đổi có thể tạo thông điệp khác ý nghĩa.

Yêu cầu cần xác định:

- Field name/value được kiểm tra trước serialize.
- Pseudo-header hợp lệ theo phiên bản và vai trò.
- Authority được xác định nhất quán.
- Metadata kết nối không được chuyển sai sang phiên bản khác.
- Cách tạo framing của body gửi tới backend.
- Cách xử lý stream lỗi đã gửi một phần dữ liệu xuống upstream.

### 6.3. Content length không khớp và lỗi phát hiện muộn

Một chênh lệch độ dài có thể chỉ được biết khi stream kết thúc. Vì vậy, yêu cầu “mọi lỗi đều được phát hiện trước khi byte nào tới origin” không thực tế với mọi mô hình streaming.

Cần tách:

| Loại lỗi | Thời điểm có thể phát hiện | Kết quả cần bảo đảm |
|---|---|---|
| Header hoặc pseudo-header lỗi | Trước khi forward body | Không tạo request nghiệp vụ từ metadata không hợp lệ |
| Lỗi độ dài khi hoàn tất | Sau một phần hoặc toàn bộ body | Không coi nội dung không hoàn chỉnh là request hợp lệ |
| Lỗi khi streaming | Trong quá trình truyền | Hủy đường xử lý liên quan và không tái sử dụng trạng thái hỏng |
| Lỗi ở kết nối HTTP/1.1 phía sau | Theo trạng thái connector | Không để byte dư ảnh hưởng request khác |

RFC 9113 cũng lưu ý các thành phần xử lý tăng dần có thể đã làm một phần công việc trước khi xác định lỗi. Do đó, ứng dụng có thao tác không thể đảo ngược cần có ranh giới hoàn tất phù hợp, thay vì commit chỉ vì đã nhận một phần đầu của body.

### 6.4. Không áp quy tắc đóng kết nối HTTP/1.1 cho mọi lỗi HTTP/2

HTTP/2 có lỗi theo stream và lỗi theo kết nối. Xử lý phải theo loại lỗi và stack giao thức, không phải luôn đóng mọi stream hoặc luôn giữ toàn bộ kết nối.

Nhưng nếu một stream lỗi đã được chuyển xuống một kết nối HTTP/1.1 mà ranh giới còn lại không thể tin cậy, connector phải hủy kết nối upstream đó. Việc reset stream phía client không tự làm sạch byte trên một kết nối khác.

Các yêu cầu về field validity và connection-specific fields nằm trong [RFC 9113 §8.2](https://www.rfc-editor.org/rfc/rfc9113.html#section-8.2).

## 7. Connection pool là một phần của ranh giới bảo mật

### 7.1. Trả lỗi chưa đủ

Một server có thể trả 400 nhưng vẫn giữ một kết nối đã mất đồng bộ trong pool. Request sau đó có thể bị ảnh hưởng dù request trước đã được ghi nhận là bị từ chối.

Cần đặc tả cả hai:

1. Request lỗi không được xử lý như hợp lệ.
2. Kết nối hoặc stream liên quan không được sử dụng tiếp ngoài điều kiện an toàn.

Đối với HTTP/1.1 có framing không đáng tin, đóng kết nối thực tế và loại khỏi pool là kiểm soát quan trọng. Chỉ gắn một header hoặc ghi một log không thay thế việc thay đổi trạng thái connector.

### 7.2. Các trạng thái cần loại khỏi pool

Một policy bảo thủ có thể hủy HTTP/1.1 upstream khi:

- Framing request hoặc response lỗi.
- Body bị thiếu do EOF hoặc timeout.
- Không xác định chắc chắn ranh giới sau lỗi.
- Client hủy request trong khi vẫn còn body chưa được xử lý an toàn.
- Connector phát hiện byte còn lại không thuộc trạng thái hợp lệ.
- Giao thức chuyển sang tunnel hoặc upgrade nhưng pool vẫn coi là HTTP thông thường.

Không nhất thiết mỗi tình huống hủy client đều bắt buộc hủy mọi upstream. Điều cần có là trạng thái hoàn tất được chứng minh bởi HTTP stack; khi không chứng minh được, không tái sử dụng theo suy đoán.

### 7.3. Minh họa Java cho quyết định reuse

Ví dụ Java 17 trở lên mô tả một policy bảo thủ cho kết nối upstream HTTP/1.1. Nó không phải parser hoặc implementation connection pool.

```java
public final class Http1ReusePolicy {
    public record ExchangeState(
            boolean requestFramingValid,
            boolean requestBodyComplete,
            boolean responseComplete,
            boolean parserError,
            boolean bodyTimeout,
            boolean protocolChanged,
            boolean unreadUnexpectedBytes
    ) {
    }

    private Http1ReusePolicy() {
    }

    public static boolean mayReuse(ExchangeState state) {
        if (state == null) {
            return false;
        }

        return state.requestFramingValid()
                && state.requestBodyComplete()
                && state.responseComplete()
                && !state.parserError()
                && !state.bodyTimeout()
                && !state.protocolChanged()
                && !state.unreadUnexpectedBytes();
    }
}
```

Các cờ phải đến từ connector có thẩm quyền, không phải request body hay header do client tự khai.

Một return false chỉ có ý nghĩa nếu pool thực sự đóng và không cấp lại kết nối đó. Không được dùng ví dụ để thay phần quản lý trạng thái của HTTP library bằng vài boolean ở controller.

### 7.4. Pipelining và multiplexing cần hợp đồng riêng

Một hệ thống có thể tắt upstream HTTP/1.1 pipelining để giảm trạng thái phải quản lý. Đây là lựa chọn bổ sung, không thay thế parser đúng.

Tương tự, không nên dùng khẩu hiệu “tắt keep-alive là đã sửa xong”. Nó có thể giảm một số ảnh hưởng qua request nhưng không chứng minh một request không bị tách hoặc diễn giải sai.

Mọi tối ưu kết nối phải giữ bất biến: dữ liệu và response của từng request không được bị gán sang request khác.

## 8. Body không hoàn chỉnh, giới hạn và side effect

### 8.1. Timeout không phải delimiter thay thế

Nếu body chưa đủ theo framing mà kết nối ngừng gửi, không được coi khoảng im lặng là dấu kết thúc hợp lệ rồi xử lý phần đã nhận như toàn bộ request.

Cần có deadline và giới hạn để giải phóng tài nguyên, đồng thời đánh dấu thông điệp không hoàn chỉnh. Sau đó connector xử lý kết nối theo trạng thái giao thức.

### 8.2. Giới hạn tài nguyên phải đi cùng parser

Những giới hạn thường cần xác định:

- Kích thước start-line.
- Tổng kích thước và số lượng header.
- Độ dài mỗi field.
- Số byte body được chấp nhận.
- Kích thước và tài nguyên dành cho trailer.
- Thời gian nhận header và body.
- Bộ nhớ hoặc dung lượng buffer.
- Số request hoặc stream đồng thời.

Giới hạn khác nhau giữa các hop có thể khiến một tầng tiếp tục truyền sau khi tầng sau đã dừng. Cần kiểm tra cách báo lỗi, hủy và làm sạch kết nối trong những tình huống đó.

Không tăng vô hạn timeout hoặc buffer chỉ để che một lỗi tương thích parser.

### 8.3. Streaming có ranh giới commit

Nếu ứng dụng nhận upload theo stream, có thể ghi vào vùng tạm có giới hạn trong khi nhận dữ liệu. Nhưng việc công bố file hoặc tạo tác dụng phụ cần dựa trên điều kiện hoàn tất theo hợp đồng.

Ví dụ:

```text
Nhận stream vào vùng tạm
    → xác nhận HTTP body hoàn tất
    → kiểm tra nội dung cần thiết
    → commit metadata và công bố artifact
```

Nếu stream lỗi, dữ liệu tạm phải có cách thu hồi. Một response lỗi không đủ nếu artifact không hoàn chỉnh đã được công bố cho người khác.

### 8.4. Retry không được làm thay đổi quyết định từ chối

Request bị từ chối vì framing không hợp lệ không nên được proxy tự sửa rồi retry sang một backend khác có parser dễ dãi hơn.

Nếu retry một thao tác hợp lệ do lỗi mạng, cần có chính sách về body replay và tác dụng phụ. Đó là yêu cầu riêng, nhưng không được biến đường retry thành đường bỏ qua validation.

## 9. Không giao trách nhiệm sai tầng

### 9.1. WAF không thay parser HTTP

Một WAF có thể phát hiện mẫu đáng ngờ nhưng vẫn dựa trên cách request được parse ở vị trí của nó. Nếu backend hiểu khác, kiểm tra nội dung ở WAF có thể không thấy đúng request mà origin thực thi.

Yêu cầu nên đặt kiểm soát framing vào HTTP stack và ranh giới proxy, kết hợp WAF như lớp bổ sung phù hợp.

### 9.2. Servlet filter thường không thấy toàn bộ byte gốc

Khi một request đến filter của ứng dụng Java, connector có thể đã:

- Parse start-line và header.
- Gộp hoặc loại một số giá trị.
- Xử lý transfer coding.
- Tạo luồng body cho ứng dụng.

Vì vậy, một filter kiểm tra getHeader không đủ chứng minh không có framing ambiguity ở chặng trước.

Không cố đọc lại socket hoặc tự dựng parser trong controller để bù cho connector không đáp ứng yêu cầu. Cần cấu hình hoặc nâng cấp thành phần đúng tầng.

### 9.3. Authentication ở edge vẫn cần bảo vệ tại service

Nếu origin tin một danh tính do gateway gắn vào header, cần có ranh giới mạng và cơ chế ngăn client tự giả mạo metadata đó.

Bảo vệ framing làm giảm khả năng một request ngoài kiểm soát xuất hiện ở phía sau, nhưng service vẫn cần hợp đồng xác thực và phân quyền phù hợp. Không để toàn bộ hệ thống dựa vào suy đoán “mọi request origin thấy chắc đã qua edge”.

## 10. Chuyển threat model thành yêu cầu cụ thể

### 10.1. Phát biểu mơ hồ

> Hệ thống phải chặn request smuggling.

Phát biểu này chưa xác định parser nào, protocol nào, những chặng nào và kết quả nào được coi là đạt.

### 10.2. Yêu cầu về framing công khai

> Public HTTP/1.1 ingress phải từ chối request có cả Content-Length và Transfer-Encoding theo policy của sản phẩm. Request có Content-Length lặp hoặc không hợp lệ bị xử lý theo cùng policy đã công bố. Header bị từ chối trước khi tạo request nghiệp vụ; kết nối không được tái sử dụng khi ranh giới thông điệp không còn đáng tin.

Nếu sản phẩm chọn chuẩn hóa duplicate giống nhau, phải thay câu tương ứng bằng thuật toán và điều kiện rõ ràng, không để mỗi hop chọn ngẫu nhiên.

### 10.3. Yêu cầu về chuyển đổi giao thức

> Mọi chuyển đổi HTTP/2 sang HTTP/1.1 phải dùng adapter được duy trì, kiểm tra field và pseudo-header trước khi serialize. Adapter tạo một framing hợp lệ duy nhất cho body, không chuyển nguyên metadata mâu thuẫn hoặc ký tự không hợp lệ sang cú pháp đích.

### 10.4. Yêu cầu về lỗi phát hiện muộn

> Khi body không hoàn chỉnh hoặc lỗi framing được phát hiện trong lúc streaming, hệ thống hủy xử lý liên quan, không coi body là hoàn tất và không tái sử dụng HTTP/1.1 upstream nếu ranh giới còn lại không được chứng minh an toàn. Những tác dụng phụ chỉ được commit theo ranh giới hoàn tất đã thiết kế.

Yêu cầu này thực tế hơn việc hứa mọi lỗi body đều được biết trước khi có byte nào đi qua proxy.

### 10.5. Yêu cầu về tính nhất quán

> Các tổ hợp edge, gateway, connector và phiên bản protocol được hỗ trợ phải có bộ tình huống kiểm chứng chung. Một thay đổi parser, rewrite, buffering hoặc pooling cần đánh giá lại những bất biến về số request, target, body và liên kết response.

### 10.6. Mẫu truy vết

```text
ID: HTTP-FRAME-01
Tài sản:
    tính toàn vẹn request, danh tính người gọi và response
Rủi ro:
    các hop hiểu khác nhau về ranh giới thông điệp
Phạm vi:
    ingress, gateway và origin connector
Quy tắc:
    một framing hợp lệ cho mỗi request
    từ chối nhập nhằng theo policy
    không reuse trạng thái không đáng tin
Điểm thực thi:
    HTTP parser và adapter giao thức
Bằng chứng:
    metadata, body marker và trạng thái pool ở các chặng thử
Chủ sở hữu:
    nhóm edge, nền tảng và ứng dụng theo ranh giới
```

## 11. Ma trận rủi ro, kiểm soát và bằng chứng

| Rủi ro | Kiểm soát | Bằng chứng chấp nhận |
|---|---|---|
| CL và TE được ưu tiên khác nhau | Từ chối tổ hợp theo policy ingress | Không có request nghiệp vụ tương ứng ở origin |
| Duplicate CL bị chọn khác | Policy duplicate thống nhất | Không mất thông tin trước validation |
| Field chứa dữ liệu không hợp lệ | Parser nghiêm ngặt tại ranh giới | Không serialize thành field hoặc request mới |
| Body đổi nhưng metadata cũ | Tái tạo framing từ dữ liệu thực | Upstream nhận đúng body và một cách đóng khung |
| H2 chuyển xuống H1 sai | Adapter validation và serialization | Request mỗi stream không bị tách hoặc ghép |
| Body bị cắt giữa chừng | Xử lý incomplete và hủy đúng trạng thái | Không commit như body hoàn chỉnh |
| Kết nối lỗi quay lại pool | Invalidate thực tế | Request sau không dùng trạng thái mất đồng bộ |
| Lỗi chỉ trả 400 nhưng vẫn xử lý | Chặn nghiệp vụ và side effect | Không phát sinh thao tác trái policy |
| Origin có đường vòng | Giới hạn nguồn vào | Không bỏ qua ranh giới ingress đã thiết kế |
| Retry sang backend dễ dãi | Giữ nguyên quyết định từ chối | Không biến request lỗi thành request được chấp nhận |

## 12. Thiết kế kiểm chứng an toàn

Các tình huống trong phần này là tiêu chí để triển khai kiểm thử, không phải kết quả kiểm thử đã chạy cho hệ thống cụ thể.

### 12.1. Môi trường cô lập và dữ liệu vô hại

Kiểm chứng trạng thái kết nối có thể ảnh hưởng request tiếp theo. Vì vậy, cần một môi trường thử được kiểm soát, backend riêng và dữ liệu marker không nhạy cảm.

Không sử dụng kết nối hoặc cache dùng chung với người dùng thật để chứng minh một vấn đề đồng bộ. Mục tiêu là quan sát bất biến, không tạo tác động ngoài phạm vi.

Có thể dùng endpoint kiểm thử ghi nhận:

- Correlation ID do hệ thống thử cấp.
- Số request nhận được.
- Method và target đã parse.
- Số byte hoặc digest của body marker.
- ID kết nối upstream trong phạm vi log thử.
- Response marker tương ứng.

Không cần đưa credential thật hoặc nội dung người dùng vào dữ liệu thử.

### 12.2. Tách nhóm request hợp lệ và không hợp lệ

Nhóm hợp lệ có thể gồm:

- Request không body theo hợp đồng.
- Request có Content-Length hợp lệ.
- Request chunked hợp lệ nếu được hỗ trợ.
- Nhiều request tuần tự hợp lệ.
- HTTP/2 stream hợp lệ và đường chuyển đổi được hỗ trợ.
- Upload streaming hoàn tất.

Nhóm không hợp lệ hoặc ngoài policy gồm:

- Metadata framing mâu thuẫn.
- Giá trị độ dài lặp theo nhóm bị cấm.
- Số độ dài không hợp lệ hoặc vượt miền.
- Field syntax ngoài hợp đồng.
- Body ngắn hơn khai báo hoặc chunked không hoàn tất.
- HTTP/2 content-length không khớp.
- Field không phù hợp khi chuyển sang HTTP/1.1.
- Timeout hoặc hủy giữa body.

Không chỉ kiểm tra nhóm bị chặn. Một policy từ chối mọi upload sẽ giảm một số rủi ro nhưng không đáp ứng chức năng nếu sản phẩm cần upload hợp lệ.

### 12.3. Quan sát ở cả ingress và origin

Đối với lỗi header phát hiện sớm:

```text
Ingress: từ chối đúng nguyên nhân
Origin: không có request nghiệp vụ được tạo
Pool: không tồn tại kết nối mất đồng bộ được cấp lại
```

Đối với lỗi body phát hiện muộn:

```text
Ingress/connector: đánh dấu incomplete hoặc malformed
Origin: không commit nội dung như request hoàn chỉnh
Upstream: hủy hoặc xử lý theo trạng thái an toàn
Request sau: không bị gán body, target hoặc response của request lỗi
```

Cần ghi nhận sự khác biệt này để không đánh giá sai một kiến trúc streaming chỉ vì origin đã thấy một phần dữ liệu trước khi lỗi được biết.

### 12.4. Kiểm tra connection reuse thật

Nếu môi trường thử mở kết nối backend mới cho mọi request trong khi production dùng pool, kết quả có thể không bao phủ trạng thái cần bảo vệ.

Bộ kiểm chứng nên có:

- Request hợp lệ trước một request lỗi.
- Request hợp lệ sau một request lỗi.
- Nhiều kết nối frontend đi qua pool thử.
- Các đường timeout và hủy.
- Response hoàn tất hoặc không hoàn tất theo tình huống.
- Xác nhận kết nối bị loại thực sự không được cấp lại.

Điều kiện đạt là mỗi request hợp lệ vẫn có target, body và response đúng, không phát sinh request ngoài dự kiến.

### 12.5. Không kết luận từ một timeout

Timeout có thể do giới hạn tốc độ, lỗi mạng, buffering hoặc một cơ chế bảo vệ khác. Nó không tự chứng minh smuggling hoặc chứng minh hệ thống an toàn.

Bằng chứng cần liên kết dữ liệu đã gửi với kết quả parse và trạng thái ở những chặng liên quan. Nếu chỉ có status code hoặc độ trễ, cần nêu giới hạn của kết luận.

### 12.6. Công cụ có thể tự sửa request

Một HTTP client hoặc proxy kiểm thử có thể tự tính Content-Length, đổi protocol hoặc chuẩn hóa field trước khi gửi.

Khi kiểm chứng framing, cần biết dữ liệu nào thực sự tới ingress. Nếu công cụ đã loại trường hợp lỗi, kết quả không chứng minh server đã xử lý nó đúng.

Điều này không có nghĩa phải tự viết công cụ raw socket. Có thể dùng công cụ phù hợp trong môi trường được phép, đồng thời lưu bằng chứng đường truyền cần thiết theo chính sách dữ liệu.

## 13. Vận hành và quản lý thay đổi

### 13.1. Theo dõi nguyên nhân thay vì chỉ đếm lỗi chung

Những nhóm sự kiện hữu ích:

- Framing conflict.
- Duplicate length bị từ chối.
- Header syntax lỗi.
- Body incomplete hoặc timeout.
- Protocol conversion failure.
- Kết nối bị loại khỏi pool.
- Request/response count bất thường giữa proxy và origin.

Log nên có correlation ID và thông tin chặng, nhưng không ghi toàn bộ raw body hoặc credential. Dữ liệu không tin cậy cũng cần được ghi theo định dạng chống làm hỏng log.

### 13.2. Giữ cấu hình và phiên bản có thể truy vết

Cần biết tổ hợp đang chạy:

- Sản phẩm và phiên bản edge/proxy.
- Connector ứng dụng.
- Protocol từng chặng.
- Cấu hình strict parsing.
- Buffering, timeout và giới hạn body.
- Pooling, pipelining và retry.
- Rewrite và forward header.

Một bản vá parser ở một hop có thể thay đổi hành vi so với hop còn lại. Quản lý thay đổi cần bao phủ tổ hợp, không chỉ tình trạng “đã nâng cấp component A”.

### 13.3. Những thay đổi cần kiểm chứng lại

- Thêm CDN, gateway, service mesh hoặc WAF.
- Bật HTTP/2 hay thay đổi protocol upstream.
- Thay cách chunking hoặc buffering.
- Thêm upload streaming.
- Đổi connector hoặc HTTP client nội bộ.
- Bật pooling hoặc tăng mức reuse.
- Thay giới hạn header, body và timeout.
- Thêm rewrite authority, path hoặc metadata xác thực.

Không cần coi mọi thay đổi giao diện là một lần đánh giá framing mới. Phạm vi kiểm chứng nên gắn với thay đổi có thể ảnh hưởng ranh giới thông điệp hoặc đường mạng.

### 13.4. Xử lý sự cố

Khi nghi có mất đồng bộ, cần bảo toàn bằng chứng phù hợp và giảm khả năng tái sử dụng trạng thái hỏng. Có thể tạm điều chỉnh tính năng liên quan trong phạm vi đã xác định, nhưng biện pháp tạm không thay thế sửa parser hoặc adapter.

Kết luận khắc phục phải dựa trên bất biến đã được kiểm chứng lại: không chỉ hết timeout mà request, body và response không còn bị diễn giải lệch qua các hop.

## 14. Những sai lầm cần tránh

### 14.1. Chỉ chặn một mẫu CL/TE

Nhập nhằng có thể liên quan tới nhiều trạng thái và bước chuyển đổi. Một signature không chứng minh các parser nhất quán.

### 14.2. Xóa một field rồi chuyển nguyên byte

Nếu chưa xác định đầy đủ body và ranh giới, sửa metadata có thể tạo thông điệp khác ở phía sau. Cần parse hợp lệ rồi tái tạo theo mô hình thống nhất.

### 14.3. Trả lỗi nhưng vẫn reuse

Quyết định lỗi phải đi tới connection pool và adapter. Một kết nối không đáng tin không được giữ chỉ vì có thể tiết kiệm chi phí thiết lập.

### 14.4. Tin HTTP/2 phía client là đủ

Cần biết protocol tới origin, cách chuyển đổi và validation. Nhãn protocol ở một chặng không mô tả toàn bộ hệ thống.

### 14.5. Tự viết parser trong ứng dụng

Một parser tạm bằng split dòng hoặc regex thường không có đầy đủ trạng thái HTTP. Dùng thành phần được duy trì và sửa đúng tầng, thay vì tạo thêm một cách hiểu cạnh tranh.

### 14.6. Yêu cầu không khả thi với streaming

Không hứa mọi lỗi body đều được chặn trước byte đầu tiên tới origin. Hãy phân loại thời điểm phát hiện, quy định hủy, ranh giới commit và loại bỏ kết nối hỏng.

## 15. Điểm cần ghi nhớ

Request smuggling defense bảo vệ sự thống nhất về ranh giới thông điệp xuyên qua các hop HTTP. Nó cần parser nghiêm ngặt, policy rõ về metadata nhập nhằng và chuyển đổi giao thức đúng.

Một yêu cầu đầy đủ còn phải bao phủ body không hoàn chỉnh, connection pool, timeout, retry và tác dụng phụ. Status lỗi không đủ nếu request hoặc trạng thái hỏng vẫn được dùng tiếp.

Bằng chứng chấp nhận cần cho thấy request hợp lệ được giữ nguyên ý nghĩa, request ngoài policy bị xử lý đúng và lỗi không làm target, body hoặc response của request khác bị thay đổi. Những bất biến này giúp chuyển một rủi ro giao thức thành yêu cầu bảo mật có thể triển khai và kiểm chứng.
