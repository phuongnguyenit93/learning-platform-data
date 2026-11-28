# Request size limit

## 1. Vì sao kích thước request là một yêu cầu bảo mật?

Một API có thể xác thực và phân quyền đúng nhưng vẫn bị làm cạn tài nguyên khi tiếp nhận nội dung quá lớn. Trước khi tới logic nghiệp vụ, request có thể đã chiếm buffer tại proxy, dung lượng tệp tạm, bộ nhớ để giải nén và bộ nhớ của parser. Sau đó, dữ liệu tiếp tục được chuyển thành chuỗi, cây JSON hoặc tập đối tượng Java.

**Request size limit** là giới hạn có thể thực thi đối với kích thước và cấu trúc dữ liệu mà một thao tác API tiếp nhận. Mục tiêu là giữ chi phí tiếp nhận trong ngân sách đã thiết kế, từ chối dữ liệu vượt hợp đồng và tránh tác dụng phụ do xử lý một phần.

Ví dụ chưa đủ rõ:

> API phải giới hạn request ở 1 MB.

Yêu cầu này còn thiếu nhiều quyết định: MB được hiểu là bao nhiêu byte, giới hạn tính cả header hay chỉ body, áp dụng trước hay sau giải nén, xử lý multipart ra sao và hệ thống phải làm gì khi vượt ngưỡng.

Một yêu cầu cụ thể hơn:

> Với thao tác nhập báo cáo v1, tổng body sau loại bỏ framing HTTP và trước giải mã `Content-Encoding` không vượt 1.048.576 byte; body sau giải mã cũng không vượt 1.048.576 byte. Dịch vụ phải kiểm tra số byte thực tế khi đọc, kể cả khi không có `Content-Length`. Request vượt một trong hai giới hạn phải không tạo bản ghi báo cáo hoặc job nhập thành công.

Giới hạn kích thước là một phần của bảo vệ tính sẵn sàng, không phải toàn bộ giải pháp chống DoS. Giới hạn tổng request, tránh cấp phát theo đầu vào và kiểm soát thời gian đọc là các biện pháp được thảo luận trong [OWASP Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html).

## 2. Phải xác định đang đo lớp dữ liệu nào

### 2.1. Byte trên từng ranh giới không giống nhau

Một request có thể đi qua các bước:

```text
Client
  -> HTTP server xử lý framing / DATA frame
  -> body còn Content-Encoding, nếu có
  -> bộ giải mã Content-Encoding
  -> byte nội dung được đưa vào parser
  -> cấu trúc JSON / multipart / đối tượng nghiệp vụ
```

Đối với bài học này, dùng các đại lượng:

- `B_encoded`: số byte body sau khi lớp HTTP xử lý framing, nhưng trước giải mã `Content-Encoding`.
- `B_decoded`: số byte nội dung sau giải mã `Content-Encoding`, trước khi parse JSON hoặc định dạng ứng dụng khác.
- `S_parsed`: kích thước và độ phức tạp của cấu trúc sau parse, được kiểm soát bằng các giới hạn riêng.

Hai điều kiện độc lập là:

```text
B_encoded <= L_encoded
B_decoded <= L_decoded
```

Nếu request không nén, hai số byte có thể bằng nhau ở các ranh giới này. Nếu dùng gzip, một body nhỏ có thể giải nén thành nội dung lớn hơn nhiều. Dù đặt hai giới hạn cùng giá trị, vẫn cần kiểm tra tại cả hai vị trí nếu hệ thống hỗ trợ nén.

Giới hạn body không bao gồm mọi chi phí giao thức. Request target, query string, header, trailer và số lượng frame hoặc chunk có các ngân sách riêng phù hợp với HTTP server và giao thức đang dùng. Không gọi một giới hạn body là “tổng request” nếu các phần khác chưa nằm trong phép đo.

### 2.2. Byte không đồng nghĩa ký tự

Với UTF-8 và chuỗi Java, có thể gặp:

| Giá trị | Số Unicode code point | Số UTF-16 code unit trong Java | Số byte UTF-8 |
| --- | --- | --- | --- |
| `A` | 1 | 1 | 1 |
| `ế` dạng dựng sẵn | 1 | 1 | 3 |
| `🙂` | 1 | 2 | 4 |

Ngoài nội dung trường, JSON còn có dấu nháy, tên trường, dấu phân cách và khoảng trắng. Một giá trị cũng có thể được biểu diễn bằng escape trong tài liệu nguồn. Vì vậy, `String.length()` của một trường không phải số byte của request body.

Yêu cầu nên ghi số byte tuyệt đối hoặc đơn vị không mơ hồ:

```text
1 KiB = 1.024 byte
1 MiB = 1.048.576 byte
```

Nếu tổ chức dùng MB theo hệ thập phân, hãy ghi rõ số byte tương ứng. Không để proxy dùng một cách hiểu, tài liệu client dùng cách khác và kiểm thử so sánh theo số ký tự.

## 3. Chuyển rủi ro thành một profile giới hạn

### 3.1. Tình huống minh họa

Giả sử nền tảng có API nhập báo cáo dạng JSON:

```http
POST /v1/report-imports
Content-Type: application/json
```

Hệ thống có thể nhận request không nén hoặc gzip theo hợp đồng. Người gọi phải có quyền nhập dữ liệu, nhưng quyền đó không cho phép vượt ngân sách tài nguyên. Mọi con số dưới đây là lựa chọn minh họa, chưa phải cấu hình sản xuất.

| Đại lượng | Giới hạn minh họa | Ranh giới áp dụng |
| --- | --- | --- |
| Body trước giải mã content coding | 1.048.576 byte | Khi tiếp nhận body ở ingress và đường vào dịch vụ phù hợp |
| Body sau giải mã | 1.048.576 byte | Đầu ra của bộ giải mã, trước parser |
| Content coding | Không nén hoặc đúng một lớp gzip | Kiểm tra metadata và đường giải mã |
| Số báo cáo trong một request | 1.000 | Parser hoặc validation trước xử lý nghiệp vụ |
| Độ sâu JSON | 32 mức theo quy ước của parser đã chọn | Trong quá trình parse |
| Thời gian nhận body | Tối đa 15 giây tổng cộng | Đồng hồ tính từ khi bắt đầu giai đoạn nhận body |
| Khoảng chờ không có tiến triển | Tối đa 3 giây theo hợp đồng vận hành | Lớp đọc hoặc HTTP server có cơ chế phù hợp |

Giới hạn độ sâu cần đối chiếu với cách parser đếm mức gốc, object và array; không chỉ ghi một số rồi kỳ vọng mọi implementation hiểu giống nhau. Hạn thời gian cũng phải xác định mốc bắt đầu và bước nào nằm trong thời hạn.

Một request dưới giới hạn byte chưa chắc hợp lệ về schema hoặc quyền. Một request chứa 1.001 báo cáo vẫn có thể bị từ chối dù chỉ vài trăm KiB. Các điều kiện cùng tạo thành hợp đồng tiếp nhận, không thay thế nhau.

### 3.2. Các yêu cầu có thể giao cho nhóm triển khai

| Mã | Yêu cầu | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| SIZE-01 | Phải kiểm tra `B_encoded` bằng số byte thực tế, không chỉ số khai báo | Body có và không có độ dài được biết trước |
| SIZE-02 | Phải dừng xử lý khi `B_decoded` vượt giới hạn | Nội dung nén nhỏ nhưng đầu ra giải nén quá lớn |
| SIZE-03 | Phải áp dụng profile theo thao tác, không cho client tự chọn giới hạn | Thay header, method hoặc đường dẫn tương đương |
| SIZE-04 | Request bị từ chối do kích thước không được commit nghiệp vụ | Kiểm tra dữ liệu, job và tác dụng phụ |
| SIZE-05 | Mọi đường vào được phép tới chức năng phải có kiểm soát phù hợp | Qua gateway và đường gọi dịch vụ thực sự tồn tại |
| SIZE-06 | Buffer, tệp tạm và tác vụ đọc phải được giải phóng sau từ chối | Ngắt kết nối, lỗi parse và nhiều request đồng thời |
| SIZE-07 | Phải có giới hạn cấu trúc, thời gian và tổng tải liên quan | JSON sâu, nhiều phần tử, đọc chậm và tải đồng thời |
| SIZE-08 | Phản hồi và telemetry phải xác định được loại giới hạn bị vượt | Mã lỗi, tầng từ chối và tên profile |

Mỗi yêu cầu nên có chủ sở hữu. Ví dụ, nhóm nền tảng sở hữu giới hạn ingress; nhóm dịch vụ sở hữu số byte sau giải mã và giới hạn nghiệp vụ; nhóm vận hành sở hữu quota dung lượng tạm và cảnh báo. Việc nhiều nhóm cùng tham gia không có nghĩa một yêu cầu có thể không có ai chịu trách nhiệm cuối cùng.

## 4. `Content-Length` chỉ hỗ trợ kiểm tra sớm

### 4.1. Có thể từ chối sớm, nhưng vẫn phải đếm khi đọc

Nếu metadata hợp lệ cho biết body chắc chắn vượt profile, tầng tiếp nhận có thể từ chối trước khi đọc toàn bộ. Điều này tiết kiệm tài nguyên. Tuy nhiên, không dùng giá trị do client khai báo để bỏ qua kiểm tra byte thực tế hoặc cấp phát một mảng có kích thước tùy ý.

Các trường hợp cần phân biệt:

| Trường hợp | Cách xử lý theo hợp đồng |
| --- | --- |
| Độ dài khai báo hợp lệ và lớn hơn giới hạn | Từ chối sớm nếu tầng tiếp nhận có đủ thông tin |
| Độ dài khai báo trong giới hạn | Vẫn thực thi giới hạn khi tiếp nhận và giải mã |
| Không có độ dài biết trước nhưng framing hợp lệ | Đếm số byte qua stream |
| Metadata độ dài hoặc framing không hợp lệ | Lớp HTTP xử lý như lỗi giao thức; không đưa tới nghiệp vụ như body hợp lệ |
| Body nhỏ trước giải nén nhưng quá lớn sau giải nén | Từ chối tại giới hạn sau giải mã |

Request HTTP/1.1 có thể dùng chunked framing; HTTP/2 có cách vận chuyển body khác. Giới hạn phải bao phủ các đường giao thức được hỗ trợ. Không buộc ứng dụng tự parse chunk chỉ để đếm byte nếu HTTP server đã chịu trách nhiệm tách framing.

### 4.2. Sai framing khác với vượt kích thước

Nếu proxy và backend diễn giải ranh giới request khác nhau, đó là vấn đề giao thức có thể liên quan tới request smuggling. Không sửa bằng cách bỏ qua một header bất tiện hoặc tin giá trị nhỏ hơn để request lọt qua. Quy tắc về message body length và các trường hợp mâu thuẫn trong HTTP/1.1 được quy định tại [RFC 9112, mục 6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3).

Một chính sách triển khai có thể chọn từ chối request có metadata framing mơ hồ tại tầng HTTP. Chính sách đó phải thống nhất qua các hop và dùng implementation giao thức phù hợp. Đây không phải trách nhiệm của một hàm đọc JSON trong controller.

Ca kiểm thử vượt kích thước nên dùng body được đóng khung hợp lệ. Ca thử sai `Content-Length` hoặc metadata xung đột cần được tách thành ca giao thức, để không kết luận sai rằng mọi lỗi tiếp nhận đều phải trả 413.

## 5. Đặt kiểm soát trước bước tiêu thụ tài nguyên lớn

### 5.1. Nhiều tầng bảo vệ, mỗi tầng có điểm đo

```text
Ingress / reverse proxy
  - giới hạn body tại điểm tiếp nhận
  - giới hạn header, thời gian đọc và kết nối
             |
             v
HTTP server / container
  - framing, giới hạn transport và multipart phù hợp
             |
             v
Bộ giải mã content coding
  - ngân sách byte đầu ra và thời gian xử lý
             |
             v
Parser
  - độ sâu, số token / phần tử / trường theo profile
             |
             v
Validation và nghiệp vụ
  - số bản ghi, độ dài trường, quyền, tính nguyên tử
```

Nếu một filter kiểm tra độ dài sau khi framework đã đọc toàn bộ body, filter đó không bảo vệ được bước buffer trước nó. Tương tự, bắt exception trong controller không chứng minh parser multipart chưa ghi một lượng lớn dữ liệu vào đĩa.

Yêu cầu phải chỉ ra vị trí kiểm soát so với bước tiêu thụ tài nguyên. Câu “kiểm tra càng sớm càng tốt” nên được cụ thể hóa bằng đường xử lý và bằng chứng của stack đang dùng.

### 5.2. Chỉ lấy giá trị nhỏ nhất khi các giới hạn cùng lớp biểu diễn

Nếu ba tầng cùng đếm một loại byte body với cùng quy ước, giới hạn hiệu lực trên đường đó có thể là giá trị nhỏ nhất. Tuy nhiên, không so trực tiếp giới hạn trước nén của tầng này với giới hạn sau giải nén của tầng khác để suy ra hệ thống đã được bảo vệ đầy đủ.

Ví dụ, proxy giới hạn body gzip ở 1 MiB còn ứng dụng không giới hạn đầu ra giải nén. Việc ứng dụng có giới hạn trường chuỗi sau parse không tự bảo vệ bộ giải nén hoặc parser trước đó.

Khi một tầng giải nén rồi chuyển nội dung cho tầng sau, cần xác định tầng sau nhận biểu diễn nào và metadata đã được cập nhật ra sao. Không để backend giải nén lần nữa vì header vẫn mô tả biểu diễn cũ.

### 5.3. Giữ hợp đồng giữa đường công khai và đường nội bộ

Nếu chỉ gateway có giới hạn nhưng backend còn được gọi trực tiếp, đường nội bộ có thể trở thành đường bỏ qua. Có thể giới hạn kết nối để backend chỉ nhận từ nguồn được phép, hoặc duy trì kiểm soát tương ứng ở backend theo kiến trúc.

Các tác vụ replay, import từ hàng đợi hoặc công cụ quản trị cũng cần profile dữ liệu của riêng chúng nếu đưa nội dung tới cùng parser. Không mặc định bản tin trong hàng đợi hoặc tệp do nhân viên tải lên là nhỏ và đáng tin.

## 6. Giải nén: giới hạn đầu ra quan trọng hơn một header nhỏ

### 6.1. Nén HTTP tạo thêm một ranh giới

Một body gzip 20 KiB có thể giải nén thành hơn 1 MiB. Nếu ứng dụng giải nén toàn bộ vào bộ nhớ rồi mới kiểm tra, giới hạn sau giải nén đã được thực hiện quá muộn đối với phần cấp phát đó.

Yêu cầu nên quy định bộ giải mã hoặc lớp đọc đầu ra phải có ngân sách tăng dần. Khi vượt ngân sách, dừng đường xử lý, hủy công việc liên quan và không chuyển dữ liệu bị cắt sang nghiệp vụ.

Một pipeline khái niệm:

```text
body có content coding
    -> bộ đếm byte encoded
    -> bộ giải mã đã chọn
    -> bộ đếm / bộ đọc có giới hạn byte decoded
    -> parser có giới hạn cấu trúc
```

Đếm đầu ra không tự bảo đảm CPU giải nén luôn nhỏ. Cần bổ sung ngân sách thời gian và khả năng hủy phù hợp. Cũng cần xem bộ giải mã có buffer hoặc read-ahead riêng không; giới hạn ở lớp đọc không chứng minh toàn bộ hệ thống chỉ chạm tới đúng một số byte tuyệt đối.

### 6.2. Tỷ lệ nén chỉ là kiểm soát bổ sung

Có thể theo dõi tỷ lệ `B_decoded / B_encoded`, nhưng không dùng nó thay giới hạn tuyệt đối. Một dữ liệu có tỷ lệ nén thấp vẫn quá lớn nếu kích thước đầu vào đủ lớn. Ngược lại, văn bản hợp lệ có thể nén rất tốt.

Nếu áp dụng giới hạn tỷ lệ, cần nêu rõ cách tính khi số byte encoded ban đầu còn rất nhỏ, thời điểm đánh giá và hành vi với dữ liệu nhiều member hoặc nhiều lớp coding. Không triển khai một phép chia tùy ý rồi coi mọi trường hợp bị từ chối là tấn công.

Profile minh họa chỉ cho phép không nén hoặc một lớp gzip. Chuỗi coding khác hoặc nhiều lớp bị từ chối theo hợp đồng định dạng. Tắt hỗ trợ nén request cũng là lựa chọn hợp lệ nếu nghiệp vụ không cần, nhưng đó phải là quyết định được công bố cho client.

### 6.3. Tệp ZIP bên trong body là một vấn đề khác

`Content-Encoding: gzip` mô tả cách biểu diễn nội dung HTTP. Một tệp ZIP được upload qua multipart là dữ liệu ứng dụng. Giới hạn body sau giải mã HTTP không giới hạn tổng dung lượng sau khi ứng dụng giải nén ZIP.

Nếu chức năng xử lý archive, cần có ngân sách riêng cho tổng byte giải nén, số entry, độ sâu lồng, thời gian và vùng lưu trữ. Hướng dẫn giới hạn kích thước file và xem xét kích thước sau giải nén được nêu trong [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

## 7. Multipart phải có nhiều giới hạn đồng thời

Giả sử một API riêng cho phép gửi tối đa hai tệp đính kèm. Một profile minh họa có thể là:

| Thành phần | Giới hạn minh họa |
| --- | --- |
| Tổng body multipart | 12 MiB, tính cả boundary, header phần và trường văn bản |
| Mỗi tệp | 5 MiB dữ liệu tệp |
| Số tệp | 2 |
| Tổng số part | 8 |
| Mỗi trường metadata dạng văn bản | 16 KiB theo biểu diễn đã đặc tả |

Giới hạn mỗi tệp không thay giới hạn toàn request. Nhiều tệp nhỏ hoặc nhiều trường văn bản vẫn có thể vượt ngân sách. Ngược lại, giới hạn tổng body không thay chính sách mỗi tệp hoặc số part.

Tên tệp, header của part và các trường không phải file cũng tiêu thụ tài nguyên. Nếu parser cho phép hàng chục nghìn part nhỏ, body có thể chưa quá lớn nhưng chi phí tạo đối tượng đã cao. Cần đối chiếu khả năng cấu hình của container và bổ sung kiểm soát tại nơi cần thiết.

Khi multipart dùng tệp tạm, yêu cầu nên xác định:

- Thư mục hoặc storage được phép dùng và quyền truy cập tương ứng.
- Ngân sách tổng dung lượng tạm và số upload đồng thời.
- Cách thu hồi phần dữ liệu đã ghi khi vượt giới hạn hoặc client ngắt kết nối.
- Thời hạn dọn phần dữ liệu còn lại sau sự cố tiến trình.
- Điều kiện chỉ công bố tệp hoặc chuyển trạng thái nghiệp vụ khi upload hoàn tất.

Không lấy dung lượng do client khai báo làm bằng chứng rằng quota đĩa còn đủ. Cần đếm dữ liệu thực tế và kiểm soát tổng tài nguyên đang sử dụng. Tệp tạm đã bị từ chối cũng không được trở thành một URL tải xuống hợp lệ.

## 8. Ví dụ Java: đọc body decoded có giới hạn

Đoạn mã dưới đây minh họa việc đọc một stream nội dung đã được chọn đúng ranh giới. Nó phù hợp với body nhỏ có hợp đồng giữ trong bộ nhớ, không phải giải pháp tổng quát cho upload lớn.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

public final class LimitedBodyReader {
    private static final int MAX_IN_MEMORY_BYTES = 1_048_576;

    private LimitedBodyReader() {
    }

    public static byte[] readDecodedBody(InputStream decoded, int limit)
            throws IOException {
        Objects.requireNonNull(decoded, "decoded");
        if (limit < 0 || limit > MAX_IN_MEMORY_BYTES) {
            throw new IllegalArgumentException("Invalid body limit");
        }

        ByteArrayOutputStream output = new ByteArrayOutputStream(
                Math.min(8_192, limit));
        byte[] buffer = new byte[8_192];
        long accepted = 0;

        while (true) {
            // Đọc thêm tối đa một byte ngoài phần ngân sách còn lại
            // để phân biệt body đúng giới hạn với body vượt giới hạn.
            int wanted = (int) Math.min(
                    buffer.length, (long) limit - accepted + 1L);
            int count = decoded.read(buffer, 0, wanted);

            if (count == -1) {
                return output.toByteArray();
            }
            if (count == 0) {
                throw new IOException("Input stream made no progress");
            }
            if (accepted + count > limit) {
                throw new BodyTooLargeException(limit);
            }

            output.write(buffer, 0, count);
            accepted += count;
        }
    }

    public static final class BodyTooLargeException extends IOException {
        private final int limit;

        public BodyTooLargeException(int limit) {
            super("Decoded request body exceeds the configured limit");
            this.limit = limit;
        }

        public int limit() {
            return limit;
        }
    }
}
```

Các tính chất cần hiểu đúng:

- Hàm không tin `Content-Length`; nó kiểm tra byte đọc được từ stream đã truyền vào.
- Body đúng bằng `limit` vẫn cần xác định đã kết thúc. Hàm thực hiện một lần đọc thăm dò cho phần còn lại thay vì cắt stream và coi là thành công.
- Byte làm vượt giới hạn không được ghi vào kết quả trả về. Hàm ném exception thay vì trả một body bị cắt.
- Hàm không đóng stream; vòng đời stream thuộc lớp gọi hoặc HTTP container theo hợp đồng tích hợp.
- Phép tính ngân sách dùng `long` để không cộng trực tiếp `limit + 1` trong kiểu `int`.

Hàm không tự thực hiện giới hạn encoded, giải nén, timeout, kiểm tra schema hoặc giải phóng tài nguyên của HTTP container. Nếu truyền stream gzip chưa giải mã vào hàm, nó đếm byte gzip chứ không đếm nội dung decoded. Tên hàm không thay đổi vị trí thực tế của stream.

Việc đọc thăm dò có thể chờ nếu client chưa gửi phần tiếp theo hoặc chưa kết thúc body; do đó cần deadline và cơ chế hủy ở lớp tích hợp. Khi dùng stream của decoder, decoder còn có thể đọc trước hoặc cấp phát buffer riêng. Mã này chỉ giới hạn dữ liệu mà hàm chấp nhận vào buffer kết quả, không tuyên bố giới hạn tuyệt đối mọi byte đã đi qua toàn bộ stack.

Không dùng `InputStream.available()` để quyết định tổng kích thước request: API đó mô tả lượng byte có thể đọc mà không chặn theo implementation, không phải độ dài toàn nội dung. Cũng không dùng `readAllBytes()` trên stream chưa được bảo vệ rồi kiểm tra độ dài sau. Xem hợp đồng trong [Java SE 21 InputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html).

Đối với body lớn, cần thiết kế streaming tới storage có quota hoặc parser có giới hạn, đồng thời giữ quy tắc không commit dữ liệu bị cắt. Chỉ đổi từ mảng byte sang tệp mà không giới hạn dung lượng sẽ chuyển rủi ro từ heap sang đĩa.

## 9. Ví dụ cấu hình và phạm vi thực sự của chúng

### 9.1. Reverse proxy NGINX

Ví dụ cho đường nhập báo cáo:

```nginx
location = /v1/report-imports {
    client_max_body_size 1048576;
    client_body_timeout 3s;
    proxy_pass http://report_service;
}
```

`client_max_body_size` giới hạn body tại lớp NGINX và có thể trả 413 khi vượt ngưỡng. Giá trị `0` tắt kiểm tra kích thước, không mang nghĩa cấm mọi body. `client_body_timeout` là khoảng thời gian giữa các lần đọc liên tiếp, không phải thời hạn tổng nhận request. Các hành vi này được mô tả trong [tài liệu ngx_http_core_module](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).

Hai directive trên không chứng minh giới hạn byte sau giải nén, deadline tổng 15 giây hoặc độ sâu JSON đã được thực thi. Cần đối chiếu pipeline thực tế, module có tham gia biến đổi body hay không và cấu hình tại các lớp khác.

Đường dẫn phải được quản lý theo route thực tế. Một location khác, alias API hoặc phiên bản cũ có thể có profile khác. Không kiểm tra một route rồi kết luận toàn bộ chức năng nhập đã được bao phủ.

### 9.2. Spring Boot Servlet multipart

Ví dụ thể hiện giới hạn mỗi tệp và tổng multipart bằng số byte rõ ràng:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 5242880B
      max-request-size: 12582912B
      file-size-threshold: 0B
```

Các thuộc tính này thuộc cấu hình multipart Servlet; chúng không tự tạo giới hạn body JSON cho mọi request. `file-size-threshold` quyết định ngưỡng chuyển dữ liệu tệp sang đĩa, không phải hạn mức tổng storage. Ý nghĩa các thuộc tính được mô tả trong [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#appendix.application-properties.web).

Khi áp dụng, phải đối chiếu phiên bản Spring Boot, container và kiểu ứng dụng thật sự. Không suy từ một giới hạn dành cho form POST của container rằng mọi JSON body hoặc reactive stream đều đã được bảo vệ. Ví dụ cấu hình trong bài chưa bao gồm giới hạn số part, số tệp, quota storage hoặc chính sách cleanup.

Các đoạn cấu hình trên chỉ minh họa cách ánh xạ một phần yêu cầu vào công nghệ. Chúng không phải bằng chứng nghiệm thu cho một dự án chưa được kiểm tra đường xử lý thực tế.

## 10. Hành vi từ chối phải an toàn và có thể vận hành

### 10.1. Trả lỗi phù hợp với nguyên nhân

Khi server từ chối vì nội dung quá lớn, mã phù hợp là `413 Content Too Large`. Nếu tình trạng chỉ tạm thời, chuẩn HTTP khuyến nghị có `Retry-After` để mô tả lúc có thể thử lại. Xem [RFC 9110, mục 15.5.14](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.14).

Với giới hạn cố định theo hợp đồng, chỉ đợi rồi gửi nguyên body cũ thường không giải quyết vấn đề; client cần giảm nội dung hoặc dùng luồng upload được hỗ trợ. Không gắn `Retry-After` tùy ý khi hệ thống không có điều kiện phục hồi theo thời gian.

Một phản hồi ứng dụng có thể là:

```json
{
  "code": "REQUEST_BODY_TOO_LARGE",
  "message": "Nội dung yêu cầu vượt giới hạn của thao tác.",
  "requestId": "req-size-example-001"
}
```

Nếu proxy từ chối trước ứng dụng, cấu trúc lỗi có thể do proxy tạo. Hợp đồng cần quyết định có chuẩn hóa phản hồi tại biên hay công bố các dạng lỗi được hỗ trợ. Không yêu cầu ứng dụng sửa một response mà nó chưa từng nhận request tương ứng.

Phân biệt 413 với 429 do tần suất hoặc quota request, 415 do định dạng không được hỗ trợ và lỗi giao thức do framing. Mã lỗi giúp client phản ứng đúng; không map mọi exception đọc stream sang “body quá lớn”.

### 10.2. Không cắt body rồi xử lý như request thành công

Một cách chống tràn sai là chỉ đọc N byte đầu rồi chuyển cho parser mà không phát hiện phần dư. Nếu N byte đó tạo thành dữ liệu có vẻ hợp lệ hoặc parser chấp nhận phần đầu, nghiệp vụ có thể xử lý dữ liệu khác điều client gửi.

Yêu cầu phải phân biệt “đã đọc đủ body hợp lệ trong giới hạn” với “đã ngừng đọc vì hết ngân sách”. Trường hợp thứ hai là từ chối, không phải import thành công một phần, trừ khi sản phẩm có một giao thức streaming với semantics từng bản ghi được đặc tả riêng.

Đối với API nhập báo cáo minh họa, chỉ tạo job hoặc commit dữ liệu sau khi body đã hoàn tất, nằm trong giới hạn và qua validation cần thiết. Không gửi thông báo, ghi dữ liệu chính thức hoặc giữ trạng thái thành công từ một body bị từ chối.

### 10.3. Dừng đọc và quản lý kết nối

Sau khi phát hiện vượt ngưỡng, không đọc bỏ vô hạn phần còn lại chỉ để cố giữ kết nối. Cần để HTTP server hoặc framework xử lý đóng kết nối, drain có giới hạn hoặc reset stream phù hợp giao thức.

Với kết nối dùng lại, phần body chưa xử lý không được trở thành request kế tiếp do xử lý framing sai. Trong môi trường multiplexing, chính sách hủy nên phù hợp với phạm vi stream và khả năng của implementation. Đây là lý do cần kiểm thử qua server và proxy thực tế, thay vì chỉ thử hàm đọc với một `ByteArrayInputStream`.

`Expect: 100-continue` có thể hỗ trợ từ chối sớm trong một số luồng, nhưng không thay giới hạn thực tế. Client có thể không dùng cơ chế đó, và một tầng trung gian có thể đã xử lý nó trước khi request tới ứng dụng.

## 11. Giới hạn mỗi request phải đi cùng ngân sách tổng

### 11.1. Nhiều request hợp lệ vẫn có thể làm cạn bộ nhớ

Nếu mỗi body decoded được phép 1 MiB và có 200 request đang giữ toàn bộ body trong bộ nhớ, riêng dữ liệu body có thể đã chiếm khoảng 200 MiB. Chưa tính các bản sao khi chuyển buffer, chuỗi, cây parse, đối tượng nghiệp vụ và chi phí của framework.

Một mô hình ngân sách đơn giản:

```text
Bộ nhớ đỉnh ước tính
  = số request đồng thời
      * (buffer body + phần lưu decoded + cấu trúc parse + bản sao)
    + ngân sách nền của dịch vụ
```

Các thành phần phải được đo hoặc ước lượng có căn cứ trên stack thật. `ByteArrayOutputStream.toByteArray()` trong ví dụ tạo thêm một mảng kết quả; do đó không được coi giới hạn body 1 MiB là trần heap 1 MiB cho mỗi request.

Cần phối hợp giới hạn kích thước với số request đang đọc, số request đang parse, quota tenant, hàng đợi và admission control. Việc autoscale thêm instance cũng không tự bảo vệ một storage tạm dùng chung hoặc một dịch vụ phụ thuộc có quota toàn cục.

### 11.2. Body nhỏ nhưng gửi chậm vẫn chiếm tài nguyên

Một client có thể gửi vài byte định kỳ để giữ kết nối. Idle timeout giữa hai lần đọc không đồng nghĩa deadline cho toàn bộ body. Nếu chỉ cấu hình idle timeout, client gửi đủ thường xuyên có thể kéo dài việc tiếp nhận.

Yêu cầu thời gian nên phân biệt:

- Thời gian nhận header.
- Khoảng chờ không có tiến triển khi nhận body.
- Thời hạn tổng cho giai đoạn nhận body.
- Thời gian giải mã và parse.
- Khả năng hủy và giải phóng tài nguyên khi hết ngân sách.

Các giá trị cần phù hợp đường truyền của người dùng hợp lệ. Nếu chức năng thực sự cần upload lớn qua mạng chậm, nên thiết kế một luồng riêng có quota, xác thực và cơ chế tiếp tục phù hợp; không tăng vô hạn giới hạn cho tất cả API JSON.

## 12. Kế hoạch nghiệm thu tại biên và qua toàn đường xử lý

Các ca sau là kế hoạch kiểm chứng cho profile minh họa, không phải tuyên bố đã chạy thử trên một hệ thống sản xuất.

| Ca | Dữ liệu hoặc điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| Nhỏ hơn giới hạn | Body hợp lệ có kích thước `L - 1` | Đi tiếp tới các kiểm tra còn lại |
| Đúng giới hạn | Body hợp lệ có kích thước `L` và kết thúc đúng | Không bị từ chối chỉ vì phép so sánh sai ở biên |
| Vượt một byte | Body hợp lệ có kích thước `L + 1` | Từ chối, không commit nghiệp vụ |
| Khai báo lớn | Metadata hợp lệ cho biết vượt ngưỡng | Từ chối sớm theo khả năng tầng tiếp nhận |
| Không biết trước độ dài | Stream có framing hợp lệ, không có độ dài biết trước | Vẫn thực thi giới hạn bằng số byte thực tế |
| Nhiều chunk nhỏ | Tổng body vượt ngưỡng qua nhiều chunk | Không reset bộ đếm theo từng chunk |
| HTTP/2 | Body vượt ngưỡng trên đường HTTP/2 được hỗ trợ | Giới hạn vẫn có hiệu lực |
| Nén nhỏ, decoded lớn | Gzip nằm dưới `L_encoded`, đầu ra vượt `L_decoded` | Dừng ở giới hạn decoded, không parse toàn bộ |
| Unicode nhiều byte | JSON có tiếng Việt hoặc ký tự ngoài BMP | So theo byte tại ranh giới, không theo `String.length()` |
| Cấu trúc quá phức tạp | Body dưới ngưỡng byte nhưng JSON quá sâu hoặc nhiều bản ghi | Từ chối theo giới hạn cấu trúc phù hợp |
| Multipart nhiều tệp | Mỗi tệp dưới giới hạn nhưng tổng request vượt | Từ chối tổng request và thu hồi dữ liệu tạm |
| Nhiều part nhỏ | Tổng byte chưa vượt nhưng số part vượt profile | Không để chi phí đối tượng tăng không kiểm soát |
| Đọc chậm | Có tiến triển nhỏ nhưng vượt deadline tổng | Kết thúc theo chính sách thời gian |
| Ngắt giữa chừng | Client ngắt khi đã có buffer hoặc tệp tạm | Không tạo job thành công; giải phóng tài nguyên |
| Đồng thời | Nhiều body trong giới hạn đến cùng lúc | Ngân sách tổng và dịch vụ khác vẫn được bảo vệ |
| Đường gọi khác | Route cũ, backend nội bộ được phép, tác vụ replay | Không có đường bỏ qua kiểm soát bắt buộc |

### 12.1. Tạo dữ liệu kiểm thử theo đúng đơn vị

Để kiểm tra biên byte, nên tạo tài liệu hợp lệ rồi tính byte của biểu diễn thực sự gửi. Không suy từ số ký tự hoặc từ độ dài một object đã parse. Với gzip, cần ghi nhận riêng kích thước encoded và decoded; với multipart, tính cả overhead của body.

Ca `L` chỉ chứng minh giới hạn kích thước nếu tài liệu cũng đúng định dạng. Nếu cắt một JSON ngẫu nhiên đúng L byte rồi nhận lỗi parse, chưa thể kết luận hệ thống chấp nhận hoặc từ chối chính xác tại biên dung lượng.

Ca framing sai phải kiểm tra hành vi giao thức riêng. Không dùng một request mâu thuẫn metadata để thay thế ca stream hợp lệ thiếu độ dài biết trước.

### 12.2. Quan sát nhiều hơn status code

Một response 413 không đủ chứng minh tài nguyên được bảo vệ nếu proxy đã ghi hàng GiB xuống đĩa trước khi trả lỗi. Bằng chứng nghiệm thu nên gồm:

- Tầng phát hiện và giá trị giới hạn đã áp dụng.
- Số byte quan sát tại điểm đo, ghi rõ có phải số dừng tại ngưỡng phát hiện không.
- Bộ nhớ, dung lượng tạm và công việc nền trong ca kiểm thử liên quan.
- Dữ liệu nghiệp vụ và hàng đợi không có hiệu ứng ngoài hợp đồng.
- Tài nguyên được thu hồi sau lỗi, timeout hoặc ngắt kết nối.
- Request hợp lệ tiếp theo vẫn được xử lý trong điều kiện tải được thiết kế.

Không yêu cầu mọi số đo đều bằng chính xác L. Buffer, đọc thăm dò và read-ahead có thể tạo phần vượt có giới hạn; cần xác định ngân sách overhead chấp nhận được và chứng minh nó không tăng theo toàn bộ body không giới hạn.

## 13. Telemetry, thay đổi cấu hình và ngoại lệ

Sự kiện từ chối nên ghi được route chuẩn hóa, tên profile, loại giới hạn, tầng phát hiện và request ID nếu đã có. Chỉ ghi số byte đã quan sát được, không gán một kích thước toàn request mà hệ thống chưa đọc hết.

Không log nguyên body bị từ chối: nó có thể lớn, nhạy cảm hoặc được tạo để làm cạn log storage. Tên metric nên dùng nhãn có tập giá trị hữu hạn, chẳng hạn route template và loại lỗi; tránh đưa từng URL hoặc tenant tùy ý vào nhãn gây tăng cardinality không kiểm soát.

Khi tăng đột biến lỗi kích thước, cần phân biệt client dùng sai hợp đồng, thay đổi profile chưa được thông báo và hoạt động lạm dụng. Có thể đối chiếu tỷ lệ từ chối, dung lượng tạm, lỗi giải nén và thời gian đọc. Giới hạn bảo vệ tốt nhưng không có khả năng chẩn đoán vẫn có thể gây gián đoạn kéo dài cho client hợp lệ.

Thay đổi giới hạn phải được đánh giá qua toàn đường xử lý. Tăng ứng dụng lên 4 MiB nhưng proxy vẫn 1 MiB có thể làm tính năng không hoạt động như tài liệu; tăng proxy mà parser hoặc storage chưa có ngân sách phù hợp có thể mở rủi ro mới.

Ngoại lệ cho một chức năng import lớn cần có route, danh tính được phép, thời hạn, quota và bằng chứng năng lực riêng. Không dùng giá trị “unlimited” toàn cục để giải quyết một trường hợp hiếm, và không để một ngoại lệ tạm trở thành mặc định không được quản lý.

## 14. Một yêu cầu hoàn chỉnh để đưa vào thiết kế

Ví dụ hồ sơ ngắn cho chức năng nhập báo cáo:

```text
ID: SIZE-IMPORT-001
Phạm vi: POST /v1/report-imports và mọi đường vào được phép
         đưa nội dung tương đương tới chức năng nhập v1.

Giới hạn:
  - Body encoded tối đa 1.048.576 byte.
  - Body decoded tối đa 1.048.576 byte.
  - Chỉ nhận không nén hoặc một lớp gzip theo hợp đồng.
  - Cấu trúc JSON và số bản ghi theo profile đã công bố.

Thực thi:
  - Có thể dùng metadata hợp lệ để từ chối sớm.
  - Phải đếm byte thực tế khi đọc, kể cả không biết trước độ dài.
  - Giới hạn decoded được áp dụng trước khi giữ toàn bộ nội dung
    hoặc parse không giới hạn.

Khi vượt:
  - Từ chối theo lỗi kích thước, không xử lý body bị cắt.
  - Không tạo dữ liệu hoặc job nghiệp vụ thành công.
  - Dừng công việc liên quan và thu hồi tài nguyên tạm.

Kiểm chứng:
  - L-1, L, L+1; stream nhiều đoạn; gzip; multipart liên quan;
    timeout; ngắt kết nối; đồng thời; đường vào thay thế.

Trách nhiệm:
  - Nền tảng: ingress và khả năng tiếp nhận.
  - Dịch vụ: decoded, parser, validation và hiệu ứng nghiệp vụ.
  - Vận hành: quota tổng, cleanup và cảnh báo.
```

Giá trị của request size limit nằm ở việc xác định rõ đại lượng được đo, điểm dừng xử lý và kết quả sau từ chối. Khi những điều đó được liên kết với ngân sách tổng và bằng chứng nghiệm thu, giới hạn kích thước trở thành một yêu cầu bảo mật có thể thực thi, thay vì một con số cấu hình không rõ bảo vệ lớp nào.
