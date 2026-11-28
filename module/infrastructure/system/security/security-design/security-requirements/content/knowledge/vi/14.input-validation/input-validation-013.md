# Từ chối đầu vào không hợp lệ sớm — Reject invalid input sớm

## 1. “Sớm” phải được gắn với một mốc xử lý

Một API có trả lỗi cho dữ liệu sai chưa chắc đã bảo vệ hệ thống đúng cách. Nếu nó đọc toàn bộ một body rất lớn rồi mới kiểm tra kích thước, bộ nhớ đã được sử dụng. Nếu nó giữ hàng rồi mới phát hiện số lượng âm, trạng thái kho đã bị tác động.

**Từ chối đầu vào không hợp lệ sớm** nghĩa là phát hiện và dừng dữ liệu sai tại điểm sớm nhất có đủ thông tin để kết luận, trước khi dữ liệu đó gây chi phí hoặc tác dụng phụ mà yêu cầu bảo mật muốn ngăn.

Không có một vị trí duy nhất có thể thực hiện mọi phép kiểm tra:

- Kích thước thực tế cần được giới hạn trong lúc đọc dữ liệu.
- Độ sâu cấu trúc cần được giới hạn khi parser đi qua cấu trúc đó.
- Miền giá trị trường được kiểm tra sau khi xác định đúng kiểu và biểu diễn.
- Quyền truy cập đối tượng cần ngữ cảnh danh tính và đối tượng tương ứng.
- Tính sẵn có của tài nguyên có thể cần được xác nhận tại thời điểm cập nhật trạng thái.

Vì vậy, câu “validate ngay đầu request” vẫn chưa đủ rõ để triển khai. Một yêu cầu có thể kiểm chứng cần chỉ ra **kiểm tra gì, ở đâu, trước công việc nào và khi thất bại phải dừng những gì**.

So sánh:

> Mơ hồ: Hệ thống phải reject invalid input càng sớm càng tốt.

> Cụ thể: Với request giữ hàng, nếu `quantity` không phải số nguyên từ 1 đến 100 thì máy chủ phải trả lỗi trước khi đọc dữ liệu tồn kho, tạo reservation hoặc phát sự kiện giữ hàng. Kết quả lỗi không được làm giảm tồn kho hay tạo reservation.

Câu thứ hai đưa ra được bằng chứng: bên cạnh response lỗi, có thể quan sát số lần gọi phụ thuộc và thay đổi trạng thái. Nó cũng phân biệt phần kiểm tra trường với các điều kiện nghiệp vụ cần thực hiện sau đó.

Bài học dùng dịch vụ giữ hàng làm ví dụ. Endpoint, giới hạn, mã yêu cầu và mã lỗi dưới đây là lựa chọn minh họa, không phải ngưỡng bắt buộc cho mọi hệ thống.

## 2. Phân biệt dừng sớm, từ chối an toàn và phản hồi nhanh

Ba ý tưởng thường bị dùng lẫn:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Dừng sớm — fail fast | Khi đã biết không thể tiếp tục hợp lệ, có dừng phần việc phía sau không? | Số lượng sai thì không gọi kho |
| Từ chối an toàn — fail closed | Khi điều kiện bảo mật không được xác nhận, hệ thống có tránh cấp phép thao tác không? | Không xác minh được quyền thì không giữ hàng |
| Phản hồi nhanh | Người gọi nhận được kết quả trong ngân sách thời gian nào? | Có deadline cho việc đọc request và gọi phụ thuộc |

Một hàm `return error` có thể dừng luồng hiện tại nhưng không dừng một tác vụ đã chạy song song. Nó cũng không hoàn tác một message đã được gửi.

Tương tự, nếu dịch vụ kiểm tra quyền bị timeout, hệ thống không được suy ra “người gọi có quyền”. Tuy nhiên, điều đó cũng không chứng minh input của người gọi sai. Cần dừng thao tác và phân loại đúng lỗi vận hành, thay vì đổi mọi lỗi thành `INVALID_INPUT`.

“Phản hồi nhanh” không yêu cầu kiểm tra tất cả dữ liệu bằng những phép kiểm tra hời hợt. Một phản hồi thành công nhanh nhưng bỏ qua quyền hoặc điều kiện nghiệp vụ không đáp ứng yêu cầu từ chối an toàn.

Trong tài liệu yêu cầu, nên ghi riêng ba mục tiêu: vị trí dừng, điều kiện không được phép tiếp tục và ngân sách thời gian. Chúng liên quan nhưng không thay thế nhau.

## 3. Nhận diện chi phí và tác dụng phụ cần được bảo vệ

Muốn biết kiểm tra đang diễn ra muộn hay sớm, trước hết phải xác định công việc nào không nên xảy ra với input sai.

Giả sử dịch vụ cung cấp `POST /inventory-reservations`, nhận:

~~~json
{
  "sku": "BOOK_101",
  "quantity": 2
}
~~~

Tenant và danh tính người gọi được lấy từ ngữ cảnh xác thực đã được máy chủ kiểm chứng, không từ một trường `tenantId` tùy ý trong body.

Những mốc cần quan tâm gồm:

| Công việc | Chi phí hoặc tác động | Điều kiện cần đạt trước đó |
| --- | --- | --- |
| Buffer body | Dùng bộ nhớ theo dữ liệu đọc | Giới hạn kích thước khi đọc |
| Parse JSON | Dùng CPU, bộ nhớ và độ sâu ngăn xếp theo implementation | Body có giới hạn; parser có giới hạn cấu trúc |
| Ánh xạ trường | Tạo object và có thể ép kiểu | Schema và chính sách kiểu được xác định |
| Đọc catalog hoặc tồn kho | Dùng connection, I/O và quota phụ thuộc | Kiểm tra trường cục bộ đã đạt |
| Giữ hàng | Thay đổi tài nguyên nghiệp vụ | Danh tính, quyền và điều kiện nghiệp vụ đã được bảo đảm |
| Tạo reservation | Ghi trạng thái người dùng có thể quan sát | Các bất biến cần thiết được thực thi |
| Phát sự kiện thành công | Kích hoạt xử lý ở hệ thống khác | Thay đổi nghiệp vụ đã thành công theo thiết kế nhất quán |

Không phải mọi hoạt động ghi đều là tác dụng phụ cần cấm tuyệt đối. Bộ đếm giới hạn lưu lượng, telemetry hoặc audit về request bị từ chối có thể vẫn được ghi theo chính sách. Yêu cầu phải phân biệt chúng với ghi dữ liệu nghiệp vụ.

Ví dụ, “không có bất kỳ ghi nào” có thể mâu thuẫn với yêu cầu audit. Câu chính xác hơn là:

> Request bị từ chối vì input sai không được tạo reservation, giảm tồn kho hoặc phát sự kiện giữ hàng thành công; telemetry bảo mật có thể được ghi theo chính sách đã chốt.

## 4. Đặt các điểm chặn theo đường đi của dữ liệu

Một luồng minh họa có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A[Nhận request] --> B[Kiểm soát giao thức và ngân sách đọc]
    B --> C[Đọc body có giới hạn]
    C --> D[Parse và kiểm tra cấu trúc]
    D --> E[Kiểm tra giá trị cục bộ]
    E --> F[Xác nhận quyền và điều kiện cần dữ liệu]
    F --> G[Thực hiện thay đổi nghiệp vụ nhất quán]
    G --> H[Trả thành công]
    B -->|Không đạt| R[Từ chối có kiểm soát]
    C -->|Không đạt| R
    D -->|Không đạt| R
    E -->|Không đạt| R
    F -->|Không đạt| R
~~~

Sơ đồ thể hiện đường đi của payload. Xác thực người gọi và một số kiểm tra truy cập ở cấp endpoint có thể diễn ra trước khi đọc body hoặc đan xen theo kiến trúc. Không nên hiểu sơ đồ là chỉ kiểm tra danh tính sau khi đã parse.

Một số nguyên tắc sắp xếp hữu ích:

**Chặn trước chi phí cần ngăn.** Kiểm tra chiều dài string sau khi cả body đã được buffer không giải quyết được chi phí buffer body.

**Chỉ kiểm tra khi có đủ ngữ cảnh.** Không thể xác minh người gọi được thao tác trên SKU nào chỉ từ regex của SKU.

**Ưu tiên điều kiện cục bộ trước phụ thuộc đắt tiền khi an toàn.** Với request đã qua chính sách truy cập thích hợp, số lượng âm có thể được từ chối mà không gọi catalog.

**Không làm lộ thông tin nhờ thứ tự lỗi.** Một endpoint nhạy cảm có thể yêu cầu trả lỗi xác thực hoặc truy cập trước chi tiết validation. Thứ tự phải theo chính sách bảo mật, không chỉ theo chi phí CPU.

**Kiểm tra lại trạng thái có thể thay đổi ở nơi cập nhật.** Kết quả đọc tồn kho trước đó không đủ để bảo đảm tồn kho vẫn còn khi thực hiện giữ hàng.

OWASP khuyến nghị áp dụng giới hạn request trước buffering hoặc parsing, rồi kiểm tra giá trị trước xử lý nghiệp vụ và lưu trữ. Điều này phân biệt kiểm soát bảo vệ parser với validation chạy sau parser. [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

## 5. Hợp đồng đầu vào của ví dụ

Để diễn giải yêu cầu “sớm”, giả sử API giữ hàng có hợp đồng:

| Thành phần | Quy định minh họa |
| --- | --- |
| Media type | Body JSON với media type được endpoint hỗ trợ |
| Content encoding | Không hỗ trợ body nén ở endpoint này |
| Body | Tối đa 8.192 byte nội dung trước parse |
| Encoding chuỗi | UTF-8 hợp lệ, không tự thay byte lỗi bằng ký tự thay thế |
| JSON root | Một object |
| Độ sâu JSON | Tối đa 4 container; root tính là mức 1 |
| Tên trường | Chỉ `sku` và `quantity`; không có tên trường lặp |
| `sku` | String ASCII dài 1–64, khớp toàn bộ `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` |
| `quantity` | Token số nguyên JSON theo chính sách parser, giá trị 1–100 |
| Thiếu/null | Cả hai trường đều bắt buộc và không nhận null |
| Ép kiểu | Không tự đổi string, boolean hoặc số thập phân thành số lượng |

Đối với hợp đồng này, `"quantity": "2"` phải bị từ chối. Nếu mapper tự chuyển string thành `Integer` rồi validator chỉ kiểm tra [1, 100], hệ thống đã mất bằng chứng để thực thi quy tắc kiểu gốc.

Trường dư như `tenantId` hoặc `approved` cũng phải bị từ chối tại tầng cấu trúc. Không để chúng đi sâu vào object nghiệp vụ rồi mới hy vọng service bỏ qua đúng cách.

Nếu body vượt giới hạn, không cần tiếp tục parse để tìm đủ các lỗi trường. Nếu body nằm trong giới hạn nhưng có `quantity = 0`, hệ thống không được gọi kho để hỏi liệu có đủ hàng hay không.

Giới hạn 8.192 byte không thay thế deadline đọc request. Một client gửi rất chậm vẫn có thể chiếm tài nguyên dù tổng dữ liệu nhỏ. Dịch vụ cần ngân sách thời gian hoặc chính sách chống kết nối chậm ở tầng HTTP phù hợp.

OWASP REST Security cũng yêu cầu công bố media type hỗ trợ, từ chối kiểu nội dung không được hỗ trợ và đặt giới hạn kích thước request. [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).

## 6. Giới hạn phải được thực thi trước công việc nguy hiểm

### 6.1. Không đọc hết rồi mới kiểm tra kích thước

Cách làm sau đặt điều kiện đúng ở sai vị trí:

~~~java
byte[] bytes = body.readAllBytes();
if (bytes.length > MAX_BODY_BYTES) {
    throw new PayloadTooLarge();
}
~~~

Dù cuối cùng có từ chối, nó đã cho phép ứng dụng đọc và cấp phát theo toàn bộ nội dung trước khi áp dụng giới hạn.

Một helper minh họa bằng Java có thể chỉ đọc tối đa giới hạn cộng một byte để phân biệt hai trường hợp “đúng giới hạn” và “vượt giới hạn”:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

public final class BoundedReservationBody {
    private static final int MAX_BODY_BYTES = 8192;

    public static byte[] read(InputStream body) throws IOException {
        Objects.requireNonNull(body, "body");

        byte[] bytes = body.readNBytes(MAX_BODY_BYTES + 1);
        if (bytes.length > MAX_BODY_BYTES) {
            throw new PayloadTooLarge();
        }

        return bytes;
    }

    public static final class PayloadTooLarge
            extends RuntimeException {
        public PayloadTooLarge() {
            super("PAYLOAD_TOO_LARGE");
        }
    }
}
~~~

Helper này minh họa một body nhỏ được buffer có giới hạn. Nó không thay thế HTTP server, JSON parser hoặc cơ chế quản lý connection. Luồng được truyền vào phải là stream nội dung của **đúng một request** do tầng HTTP quản lý, không phải socket thô chứa nhiều message.

`readNBytes(n)` có thể chờ tới khi đọc đủ số byte yêu cầu, gặp cuối stream hoặc có lỗi. Nó không tự áp dụng read deadline và không tự đóng stream. `available()` chỉ là ước lượng dữ liệu đọc được mà không chặn, không phải độ dài body đáng tin để dùng làm giới hạn. [Java SE 21 — InputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html).

Do đó, helper phải đi cùng timeout của tầng I/O. Khi từ chối, tầng HTTP chịu trách nhiệm xử lý phần body còn lại hoặc kết thúc stream/connection theo giao thức; không đọc bỏ không giới hạn chỉ để tái sử dụng connection.

Nếu framework đã buffer toàn bộ request trước khi helper được gọi, helper không còn bảo vệ được chi phí buffer đó. Cần đặt giới hạn tại thành phần nhận dữ liệu ban đầu.

### 6.2. Đọc số byte thực tế, không chỉ tin header

Có thể từ chối sớm dựa trên kích thước khai báo lớn hơn giới hạn, nhưng vẫn phải có giới hạn trên dữ liệu thực tế. Một request có thể được tiếp nhận bằng cơ chế không cung cấp toàn bộ chiều dài trước khi đọc.

Các tầng xử lý phải thống nhất framing theo giao thức được dùng. Validator nghiệp vụ không nên tự viết lại logic diễn giải các header framing hoặc sửa request mơ hồ để cố tiếp tục.

Nếu endpoint hỗ trợ nén, cần giới hạn tài nguyên cả ở bước giải nén, chẳng hạn lượng nội dung sau giải nén và ngân sách xử lý. Kiểm tra sau khi giải nén hoàn toàn là quá muộn để bảo vệ bước đó. Ví dụ hiện tại chọn không hỗ trợ body nén để giữ hợp đồng đơn giản.

### 6.3. Giới hạn parser trước validation trường

Một annotation trên `quantity` chỉ có thể chạy sau khi mapper tạo được object. Nó không thể tự bảo vệ parser khỏi độ sâu lồng quá mức hoặc token rất dài.

Yêu cầu parser cần được cấu hình ở nơi bắt đầu parse: giới hạn độ sâu, độ dài token nếu cần, chính sách trường lặp và cấu trúc được hỗ trợ. Không biến lỗi parse thành một object rỗng rồi cho service tự điền default.

## 7. Dừng luồng trước tác dụng phụ nghiệp vụ

Xét một luồng sai về thứ tự:

~~~text
1. Đọc toàn bộ body.
2. Ánh xạ request.
3. Tạo reservation tạm.
4. Gọi dịch vụ kho để giữ hàng.
5. Kiểm tra quantity có thuộc [1, 100] không.
6. Nếu không đạt, trả lỗi.
~~~

Luồng này có thể trả response lỗi đúng nhưng đã tạo dữ liệu và gọi phụ thuộc. Nếu rollback không bao phủ dịch vụ kho, việc giữ hàng có thể còn tồn tại.

Một luồng được phân ranh rõ hơn:

~~~text
1. Áp dụng kiểm soát giao thức, truy cập và ngân sách đọc phù hợp.
2. Đọc body có giới hạn.
3. Parse JSON nghiêm ngặt và kiểm tra cấu trúc.
4. Kiểm tra sku và quantity cục bộ.
5. Xác nhận quyền trên tài nguyên và điều kiện cần dữ liệu hiện thời.
6. Thực hiện giữ hàng và tạo reservation theo cơ chế nhất quán đã chọn.
7. Phát tín hiệu thành công theo thiết kế giao dịch/sự kiện.
~~~

Đây là mã giả về thứ tự, không phải một triển khai giao dịch hoàn chỉnh. Bước 5 và 6 cần được thiết kế để tránh khoảng trống giữa kiểm tra trạng thái và cập nhật.

Trong code ứng dụng, cần chú ý những vị trí có thể gây tác dụng phụ ngoài dự kiến:

- Constructor hoặc mapper gọi repository.
- Validator gọi dịch vụ ngoài dù điều kiện cục bộ đã sai.
- Filter ghi business event trước khi controller quyết định.
- Tác vụ song song bắt đầu giữ hàng trước khi validation hoàn tất.
- Handler bắt exception nhưng vẫn chạy khối xử lý phía sau.
- Một bước “kiểm tra” thực chất là phép gọi có tác dụng ghi ở hệ thống khác.

Đặt tên phương thức là `validate` không bảo đảm phương thức đó không gây thay đổi. Hợp đồng giữa các thành phần phải nêu rõ phép nào chỉ đọc và phép nào thực hiện thao tác.

Một thiết kế hữu ích là chỉ tạo command nghiệp vụ sau khi kiểm tra cục bộ đạt, rồi yêu cầu service thực thi command qua các kiểm soát quyền và trạng thái cần thiết. Tuy nhiên, tên kiểu command không phải bảo đảm bảo mật nếu đường gọi khác vẫn có thể tạo dữ liệu không hợp lệ.

## 8. Dừng sớm không đồng nghĩa chỉ được báo một lỗi

Có hai quyết định khác nhau:

1. Có tiếp tục công việc nghiệp vụ sau khi biết request sai không?
2. Có thu thập thêm một số lỗi trường để hỗ trợ người gọi không?

Hệ thống có thể từ chối sớm về mặt nghiệp vụ nhưng vẫn trả nhiều lỗi trường trong một body nhỏ đã được parse an toàn.

Ví dụ:

~~~json
{
  "sku": "",
  "quantity": 0
}
~~~

Sau khi body và cấu trúc đã qua các giới hạn, validator có thể báo cả `sku` rỗng và `quantity` ngoài khoảng. Nó vẫn không được đọc tồn kho hoặc tạo reservation.

Một chính sách minh họa:

| Loại lỗi | Hành vi |
| --- | --- |
| Body vượt giới hạn hoặc cấu trúc vượt ngân sách | Dừng ngay, không tìm đủ lỗi trường |
| Không xác thực hoặc không có quyền ở cấp endpoint | Theo chính sách truy cập; không trả chi tiết validation nhạy cảm |
| Một số trường cục bộ sai trong body đã giới hạn | Cho phép thu thập tối đa hai lỗi |
| Kiểm tra phụ thuộc thất bại | Dừng các bước phụ thuộc phía sau; phân loại lỗi đúng |
| Đã biết request không được thực hiện | Không bắt đầu thao tác nghiệp vụ |

Nếu muốn thu thập lỗi, số lỗi và khối lượng công việc phải có giới hạn. Không quét hàng triệu phần tử chỉ để đưa tất cả lỗi vào response.

Thứ tự lỗi cũng cần ổn định nếu client phụ thuộc vào nó. Tuy nhiên, việc trả lỗi đầu tiên không chứng minh các trường chưa được kiểm tra đã đúng.

## 9. Lỗi input, lỗi quyền và lỗi phụ thuộc phải được phân loại đúng

Giả sử `quantity = 2` và SKU đúng hình dạng, nhưng dịch vụ kiểm tra quyền không truy cập được. Hệ thống chưa biết người gọi được phép thao tác hay không. Nó phải tránh giữ hàng, nhưng không nên kết luận input sai.

Một bảng phân loại cho ví dụ:

| Tình huống | Phân loại | Hành vi chính |
| --- | --- | --- |
| JSON hỏng hoặc trường sai kiểu/miền giá trị | Input không hợp lệ | Trả lỗi hợp đồng; không gọi thao tác nghiệp vụ |
| Body vượt giới hạn | Nội dung vượt chính sách tiếp nhận | Dừng đọc/xử lý theo cơ chế HTTP phù hợp |
| Media type không hỗ trợ | Biểu diễn không hỗ trợ | Không thử một parser khác để “đoán” nội dung |
| Người gọi không có quyền | Truy cập bị từ chối | Không thực hiện thao tác; phản hồi theo chính sách tiết lộ |
| Không đủ hàng tại thời điểm thực thi | Xung đột trạng thái nghiệp vụ | Không tạo reservation thành công |
| Dịch vụ cần thiết tạm thời không khả dụng | Lỗi phụ thuộc | Không mặc định cấp phép; trả lỗi vận hành phù hợp |
| Lỗi lập trình không dự kiến | Lỗi máy chủ | Phản hồi kiểm soát, ghi chẩn đoán nội bộ |

Ở API minh họa, nhóm có thể chọn `400` cho input sai, `413` cho body quá lớn, `415` cho biểu diễn không hỗ trợ, `409` cho xung đột tồn kho và `503` khi dịch vụ tạm thời không thể đáp ứng do phụ thuộc thiết yếu không khả dụng.

HTTP phân biệt lỗi request, nội dung quá lớn, biểu diễn không được hỗ trợ và lỗi máy chủ. Ánh xạ tình huống cụ thể cần được chốt trong hợp đồng API thay vì gom tất cả thành một mã lỗi. [RFC 9110 — HTTP Semantics, mục 15](https://www.rfc-editor.org/rfc/rfc9110.html).

Nếu một request đồng thời có body lớn và thiếu xác thực, thứ tự phản hồi không nên bị tự suy ra từ bảng. Dự án cần công bố chính sách ưu tiên cho các điểm chặn phù hợp, bảo đảm giới hạn tài nguyên và tránh lộ thông tin.

Response không nên chứa stack trace, tên lớp, đường dẫn nội bộ hay thông báo thô từ phụ thuộc. Chi tiết chẩn đoán được giữ ở phía máy chủ theo chính sách logging. [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html).

## 10. Những trường hợp không thể kiểm tra toàn bộ ngay đầu luồng

### 10.1. Trạng thái thay đổi đồng thời

Một lần đọc thấy còn 5 sản phẩm không bảo đảm vẫn còn 5 sản phẩm khi request giữ hàng được thực thi. Hai request hợp lệ có thể cạnh tranh cùng tài nguyên.

Kiểm tra sớm giúp loại bỏ những request chắc chắn sai, nhưng điều kiện “không giữ vượt tồn” phải được bảo vệ tại thao tác cập nhật, bằng cơ chế nhất quán phù hợp với kiến trúc.

Không kéo giao dịch database dài hơn cần thiết chỉ để bao cả việc đọc request chậm. Các kiểm tra tĩnh thường nên hoàn tất trước khi giữ tài nguyên giao dịch; kiểm tra trạng thái động vẫn phải nằm trong ranh giới bảo vệ thao tác.

### 10.2. Xử lý bất đồng bộ

Với message, producer kiểm tra đúng không có nghĩa consumer được phép tin mọi message. Consumer cần có điểm chặn trước tác dụng phụ của chính nó.

Message không hợp lệ vĩnh viễn thường không nên bị retry vô hạn như một lỗi mạng tạm thời. Thiết kế cần xác định cách phân loại, cách ly hoặc ghi nhận message, giới hạn lần thử và quyền truy cập vùng cách ly.

Nếu lưu payload vào vùng cách ly, phải xét dữ liệu nhạy cảm, giới hạn kích thước và thời hạn lưu. “Đưa vào dead-letter queue” không tự giải quyết bảo mật của dữ liệu được giữ lại.

Nếu hai nhánh xử lý chạy song song, lỗi validation ở một nhánh không tự hủy nhánh kia. Yêu cầu phải đặt rào chắn trước khi các nhánh được phép thực hiện tác dụng phụ; cancellation chỉ là biện pháp hỗ trợ, không phải rollback của thao tác đã hoàn tất.

### 10.3. File nhập nhiều dòng và streaming

Với file nhập lô, cần chọn rõ một trong các hợp đồng:

| Hợp đồng | Khi một dòng cuối file sai |
| --- | --- |
| Toàn bộ hoặc không gì cả | Không được công bố các thay đổi nghiệp vụ của những dòng trước như đã hoàn tất |
| Chấp nhận từng phần | Các dòng hợp lệ có thể được ghi theo quy tắc rõ ràng; kết quả chỉ ra dòng nào thành công/thất bại |

Nếu chọn toàn bộ hoặc không gì cả, có thể cần staging có giới hạn trước khi apply. Staging phải được phân biệt với dữ liệu nghiệp vụ đã được chấp nhận và có quy trình dọn dẹp.

Nếu chọn từng phần, không được trả một thông báo lỗi chung khiến người dùng tưởng chưa dòng nào được ghi rồi nhập lại toàn file gây trùng. Yêu cầu idempotency và báo cáo kết quả từng phần phải đi cùng thiết kế.

Nguyên tắc “reject sớm” vẫn áp dụng cho từng đơn vị công việc, nhưng không thể thay thế quyết định về ranh giới atomic của cả lô.

## 11. Đặc tả thành yêu cầu có thể kiểm chứng

Một bộ yêu cầu minh họa:

| ID | Yêu cầu | Điểm chặn và bằng chứng |
| --- | --- | --- |
| EARLY-001 | Giới hạn body thực tế ở 8.192 byte trước parse | Body vượt giới hạn không được gọi parser nghiệp vụ |
| EARLY-002 | Áp dụng giới hạn cấu trúc trong khi parse | Độ sâu vượt 4 bị dừng ở parser, không đợi tạo DTO |
| EARLY-003 | Từ chối kiểu và miền giá trị sai trước đọc tồn kho | `quantity = 0`, `101` hoặc string làm số lần đọc tồn kho bằng 0 |
| EARLY-004 | Không sửa ngầm dữ liệu sai để tiếp tục | Không đổi quantity sai thành giá trị mặc định, không cắt SKU quá dài |
| EARLY-005 | Request bị từ chối không gây tác dụng phụ nghiệp vụ | Không reservation, không giảm tồn kho, không sự kiện giữ hàng thành công |
| EARLY-006 | Không bỏ qua quyền khi không xác minh được | Lỗi phụ thuộc kiểm tra quyền không dẫn đến giữ hàng |
| EARLY-007 | Chặn tiếp tục xử lý sau quyết định từ chối | Không tác vụ ghi nghiệp vụ nào được khởi động từ nhánh lỗi |
| EARLY-008 | Trả lỗi giới hạn và đúng phân loại | Không đổi timeout phụ thuộc thành thành công hoặc lỗi input mặc định |
| EARLY-009 | Có ngân sách đọc request độc lập kích thước | Request nhỏ gửi quá chậm được xử lý theo deadline đã cấu hình |
| EARLY-010 | Có telemetry đủ xác định điểm từ chối | Log/metric ghi stage và rule ID từ tập hữu hạn, không ghi toàn payload |

EARLY-001 cần được diễn giải đúng: parser của ví dụ được gọi sau helper buffer có giới hạn, nên body vượt giới hạn không đi tới parser đó. Với một kiến trúc parser streaming, điều kiện tương đương là parser không tiêu thụ nội dung vượt ngân sách và không tạo tác dụng phụ; không áp nguyên xi cách đếm lời gọi của kiến trúc buffer.

Với EARLY-003, “số lần đọc tồn kho bằng 0” không có nghĩa không được có một lời gọi xác thực cần thiết ở trước đó. Yêu cầu cần nêu rõ phụ thuộc nghiệp vụ nào được bảo vệ, không đánh đồng mọi I/O.

Các điều kiện về deadline phải có giá trị cụ thể được lựa chọn theo tải, môi trường triển khai và loại endpoint trước nghiệm thu. Con số không được tự lấy từ một ví dụ nhỏ rồi áp cho upload hoặc stream dài.

## 12. Bằng chứng phải bao gồm thứ chưa xảy ra

Một response `400` chỉ cho biết client nhận lỗi. Nó không chứng minh service đã chặn sớm.

Để nghiệm thu, cần quan sát:

- Phần việc nào đã chạy trước khi từ chối.
- Lời gọi phụ thuộc nào không được thực hiện.
- Trạng thái nghiệp vụ nào không được thay đổi.
- Công việc đang chờ hoặc đang chạy có được kiểm soát không.
- Response và telemetry có đúng hợp đồng không.

Ma trận dưới đây là đặc tả ca kiểm thử cho ví dụ, không phải kết quả đã được thực thi:

| Ca | Điều kiện | Kết quả và bằng chứng cần có |
| --- | --- | --- |
| T01 | Body hợp lệ, `quantity = 1` | Qua validation cục bộ; chỉ thành công nếu các điều kiện sau cũng đạt |
| T02 | Body đúng 8.192 byte và cấu trúc hợp lệ | Qua giới hạn kích thước |
| T03 | Body 8.193 byte | Bị từ chối; parser ở sau buffer không được gọi |
| T04 | Không biết trước toàn bộ chiều dài body | Giới hạn dựa trên dữ liệu đọc thực tế vẫn có hiệu lực |
| T05 | Body nhỏ nhưng vượt độ sâu 4 | Parser dừng theo giới hạn; không tạo reservation |
| T06 | JSON hỏng hoặc có tên trường lặp | Từ chối có kiểm soát; không tạo DTO hợp lệ để xử lý tiếp |
| T07 | `quantity = 0` hoặc `101` | Không đọc tồn kho, không giữ hàng |
| T08 | `quantity = "2"` hoặc null | Từ chối kiểu/null, không ép về giá trị hợp lệ |
| T09 | SKU dài quá giới hạn | Không regex/parse sâu hơn cần thiết, không đọc tồn kho |
| T10 | Chèn `tenantId` hoặc `approved` | Từ chối trường dư; không ánh xạ vào quyền hoặc trạng thái |
| T11 | Phụ thuộc kiểm tra quyền timeout | Không giữ hàng; lỗi được phân loại là phụ thuộc/vận hành |
| T12 | Người gọi không được phép trên SKU | Không giữ hàng; phản hồi theo chính sách truy cập |
| T13 | Hai request cạnh tranh lượng tồn cuối | Không vượt tồn; kiểm tra trạng thái được bảo vệ tại thao tác |
| T14 | Validation thất bại trong luồng có xử lý song song | Không nhánh nào đã được phép tạo tác dụng phụ trước rào chắn |
| T15 | Client ngắt kết nối khi chưa đọc xong | Không tiếp tục tạo reservation từ payload chưa được xác nhận |
| T16 | Lỗi xảy ra sau khi thao tác đã commit | Không mô tả sai là lỗi validation trước xử lý; xử lý retry/idempotency đúng hợp đồng |
| T17 | Input sai chứa dữ liệu nhạy cảm hoặc ký tự điều khiển | Response/log không phản chiếu toàn bộ input |
| T18 | Request nhỏ được gửi chậm quá deadline | Có hành vi timeout/cancellation ở tầng I/O; không chạy nghiệp vụ |

Để dựng T02, có thể bổ sung whitespace JSON tới đúng số byte mà không đổi giá trị object. Đối với T03, cần kiểm tra cả response và việc parser chưa chạy trong triển khai buffer minh họa.

Trong kiểm thử đơn vị, test double hoặc spy có thể xác nhận các lời gọi nghiệp vụ bằng 0. Ở kiểm thử tích hợp, cần quan sát trạng thái reservation, tồn kho và nơi phát sự kiện trong một khoảng quan sát phù hợp với hệ thống.

Không dùng việc “chưa thấy event ngay” làm bằng chứng duy nhất cho hệ thống bất đồng bộ. Cần có dấu vết hoặc điểm kiểm soát cho thấy không có công việc thành công nào đã được đưa vào hàng đợi chờ phát.

Một lỗi được phát hiện sau commit không thể được đổi tên thành “đã reject input sớm”. Tình huống đó cần cơ chế nhất quán, khôi phục và idempotency riêng.

## 13. Telemetry và những phản mẫu cần tránh

Một sự kiện từ chối có thể có dạng:

~~~json
{
  "event": "request_rejected",
  "route": "POST /inventory-reservations",
  "stage": "FIELD_VALIDATION",
  "ruleId": "EARLY-003",
  "reason": "QUANTITY_OUT_OF_RANGE",
  "requestId": "server-generated-id"
}
~~~

`stage` và `ruleId` giúp xác định dữ liệu đã bị chặn ở đâu. Không cần ghi nguyên body hoặc dữ liệu xác thực để chứng minh một số lượng nằm ngoài miền được chấp nhận.

Metric nên có tập nhãn hữu hạn như route, stage và reason code. Tránh dùng SKU tùy ý hoặc thông điệp exception đầy đủ làm nhãn. Giới hạn cả lượng telemetry để một làn request sai không tạo tải không kiểm soát lên hệ thống logging.

Các phản mẫu thường gặp:

**Validate chỉ ở frontend.** Người gọi có thể gửi request trực tiếp. Điểm chặn bảo vệ máy chủ phải được thực thi ở phía máy chủ và các đường vào tương ứng.

**Đọc hết rồi kiểm tra.** Điều kiện kích thước chạy sau buffering chỉ là kết luận muộn, không bảo vệ bước buffer.

**Tạo dữ liệu “tạm” rồi mới hỏi request có hợp lệ không.** Dữ liệu tạm có thể đã được job khác đọc hoặc đã kích hoạt sự kiện. Nếu cần staging, phải có ranh giới rõ ràng và chưa được coi là trạng thái nghiệp vụ đã chấp nhận.

**Bắt mọi exception và trả `INVALID_INPUT`.** Cách này che lỗi phụ thuộc hoặc lỗi lập trình, khiến retry và vận hành xử lý sai nguyên nhân.

**Bỏ qua lỗi để giữ khả dụng.** Nếu kiểm tra quyền không thực hiện được, tiếp tục giữ hàng không phải là một chiến lược cải thiện khả dụng đúng yêu cầu bảo mật.

**Tự sửa và tiếp tục.** Đổi số lượng âm thành 1, cắt dữ liệu dài hoặc bỏ trường lạ chỉ được phép nếu hợp đồng đã công bố hành vi ấy; không được xem đó là cách từ chối.

**Khởi chạy việc ghi song song với validation.** Một lỗi được trả nhanh không thu hồi được thao tác đã hoàn tất ở nhánh khác.

**Cố kiểm tra mọi thứ ngay đầu rồi bỏ bảo vệ ở lúc cập nhật.** Kiểm tra sớm không thay thế ràng buộc chống vượt tồn hoặc kiểm tra trạng thái động tại thời điểm thực thi.

Yêu cầu “reject invalid input sớm” đạt giá trị khi gắn được một lỗi với ranh giới dừng cụ thể. Thiết kế cần cho thấy dữ liệu sai bị chặn trước chi phí cần bảo vệ, thao tác bị từ chối không tạo tác dụng phụ nghiệp vụ và lỗi được phản hồi đủ rõ mà không làm lộ nội dung không cần thiết.
