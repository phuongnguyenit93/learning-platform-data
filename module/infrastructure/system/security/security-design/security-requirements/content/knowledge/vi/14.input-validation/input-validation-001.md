# Yêu cầu kiểm tra dữ liệu đầu vào — Input validation requirement

## 1. Từ “kiểm tra đầu vào” đến một yêu cầu bảo mật có thể kiểm chứng

Một hệ thống nhận dữ liệu hợp lệ về mặt cú pháp vẫn có thể thực hiện thao tác sai. Chẳng hạn, JSON chứa số lượng mua hàng là -3 có thể được đọc thành công, nhưng không được phép tạo đơn. Ngược lại, một ghi chú có dấu nháy đơn có thể hoàn toàn hợp lệ; chặn ký tự đó không chứng minh hệ thống đã chống được SQL injection.

**Yêu cầu kiểm tra dữ liệu đầu vào** mô tả chính xác dữ liệu nào được chấp nhận tại một ranh giới tin cậy, cách xác định tính hợp lệ và hành vi của hệ thống khi dữ liệu không đáp ứng hợp đồng. Đầu ra cần thiết là điều kiện mà lập trình viên có thể triển khai, người kiểm thử có thể quan sát và người sở hữu rủi ro có thể nghiệm thu.

Trong thiết kế yêu cầu bảo mật, câu “mọi input phải an toàn” quá mơ hồ. Nó chưa trả lời được input nào, an toàn cho thao tác nào, giới hạn bao nhiêu và từ chối bằng cách nào.

So sánh:

> Yêu cầu mơ hồ: Hệ thống phải validate số lượng.

> Yêu cầu có thể kiểm chứng: Tại API tạo đơn, máy chủ phải yêu cầu `quantity` là một số nguyên từ 1 đến 100, kể cả hai đầu. Thiếu trường, giá trị null, chuỗi, số thập phân hoặc giá trị ngoài khoảng phải bị từ chối trước khi tạo đơn, giữ hàng hay phát sự kiện nghiệp vụ.

Câu thứ hai liên kết được bốn thành phần: **điểm kiểm tra → miền giá trị hợp lệ → hành vi thất bại → bằng chứng quan sát**. Đây là trọng tâm của bài học: chuyển rủi ro liên quan đến dữ liệu thành yêu cầu cụ thể, đo được và gắn với kiến trúc xử lý.

Các endpoint, mã yêu cầu, thông số và mã lỗi dưới đây là **thiết kế minh họa cho một dịch vụ đặt hàng**, không phải giới hạn mặc định của một tiêu chuẩn bảo mật.

## 2. Xác định dữ liệu và ranh giới cần kiểm soát

Trước khi viết quy tắc cho từng trường, phải biết dữ liệu đi vào đâu và ai có thể thay đổi nó. “Dữ liệu nội bộ” không đủ để kết luận dữ liệu đáng tin: một message có thể được tạo từ request bên ngoài, hoặc một bản ghi cũ có thể được nhập trước khi quy tắc hiện hành tồn tại.

Trong ví dụ đặt hàng, những đường vào cần được nhận diện gồm:

| Đường vào | Dữ liệu tiêu biểu | Câu hỏi cần trả lời trong đặc tả |
| --- | --- | --- |
| HTTP body | Mã sản phẩm, số lượng, ghi chú | Đúng kiểu nào, trường nào bắt buộc, có nhận trường dư không? |
| Path và query | Mã đơn, bộ lọc, số trang | Có cho phép lặp tham số, giá trị âm hoặc khoảng quá lớn không? |
| Header do client gửi | Mã theo dõi từ client, lựa chọn phiên bản | Header nào được dùng, giới hạn bao nhiêu, có phải dữ liệu định danh đáng tin không? |
| Message từ hệ thống khác | Yêu cầu nhập đơn từ đối tác | Schema phiên bản nào, xử lý message không hợp lệ ra sao? |
| File nhập lô | Các dòng đơn hàng | Giới hạn cả file và mỗi dòng, xử lý lỗi từng phần như thế nào? |

Bảng này không có nghĩa mọi đường vào dùng chung một validator. Request HTTP có thể trả phản hồi ngay; message không hợp lệ cần một chính sách xác nhận, cách ly hoặc xử lý lỗi phù hợp với broker. Yêu cầu phải gắn với đường đi thực tế, không chỉ nêu một hàm tiện ích chung.

Đối với một request đặt hàng, có thể mô tả chuỗi xử lý như sau:

~~~mermaid
flowchart TD
    A[Nhận request] --> B[Giới hạn kích thước và định dạng]
    B --> C[Giải mã và parse theo hợp đồng]
    C --> D[Kiểm tra cấu trúc và giá trị]
    D --> E[Phân quyền và kiểm tra trạng thái nghiệp vụ]
    E --> F[Ghi thay đổi có bảo vệ tính nhất quán]
    B -->|Không đạt| R[Từ chối có kiểm soát]
    C -->|Không đạt| R
    D -->|Không đạt| R
    E -->|Không đạt| R
~~~

Sơ đồ mô tả thứ tự xử lý **payload đặt hàng**. Xác thực kết nối, xác thực người gọi, kiểm soát lưu lượng và kiểm tra header có thể diễn ra sớm hơn hoặc đan xen theo kiến trúc. Không nên hiểu sơ đồ là yêu cầu phải parse toàn bộ nội dung trước mọi kiểm soát danh tính.

## 3. Các loại điều kiện thường cần đặc tả

Để tránh dùng một từ “validate” cho nhiều mục đích khác nhau, hãy tách điều kiện theo câu hỏi mà chúng giải quyết:

| Loại điều kiện | Câu hỏi | Ví dụ trong dịch vụ đặt hàng |
| --- | --- | --- |
| Cấu trúc | Payload có đúng hình dạng được hỗ trợ không? | Root phải là object, không có trường ngoài hợp đồng |
| Kiểu và cú pháp | Dữ liệu có được biểu diễn đúng định dạng không? | `quantity` phải là token số nguyên, không nhận chuỗi `"2"` |
| Miền giá trị | Giá trị có thuộc tập cho phép không? | `quantity` thuộc [1, 100] |
| Quan hệ giữa các trường | Các giá trị có nhất quán với nhau không? | Nếu hỗ trợ khoảng ngày, ngày kết thúc không trước ngày bắt đầu |
| Trạng thái nghiệp vụ | Thao tác có phù hợp với trạng thái hiện tại không? | Sản phẩm còn được bán tại thời điểm tạo đơn |
| Quyền truy cập | Người gọi có được thực hiện thao tác trên đối tượng không? | Người gọi được đặt sản phẩm thuộc danh mục của tenant hiện tại |
| Giới hạn tài nguyên | Một đầu vào có buộc hệ thống dùng quá nhiều tài nguyên không? | Body và độ sâu parse đều có giới hạn |

OWASP phân biệt kiểm tra cú pháp với kiểm tra ngữ nghĩa và khuyến nghị xác định miền đầu vào được chấp nhận. Kiểm tra định danh hợp lệ không thay thế kiểm tra quyền truy cập. [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html).

Một yêu cầu có thể tham chiếu nhiều loại điều kiện, nhưng từng điều kiện nên có tiêu chí riêng. Ví dụ “mã sản phẩm hợp lệ” có ít nhất ba nghĩa khác nhau:

- Chuỗi tuân theo định dạng mã.
- Mã trỏ tới sản phẩm tồn tại và đang được bán.
- Người gọi được phép đặt sản phẩm đó trong ngữ cảnh hiện tại.

Nếu cả ba đều trả cùng một thông báo bên ngoài để hạn chế tiết lộ thông tin, hệ thống vẫn cần phân biệt nguyên nhân nội bộ theo chính sách logging. Phản hồi giống nhau không có nghĩa ba phép kiểm tra là một.

## 4. Cấu trúc của một yêu cầu đủ rõ

Một đặc tả hữu ích cần ghi được cả điều kiện chấp nhận và hậu quả khi không đạt. Có thể dùng mẫu:

~~~text
ID:
Rủi ro được xử lý:
Phạm vi và điểm thực thi:
Nguồn đầu vào:
Điều kiện chấp nhận:
Quy tắc biểu diễn/chuẩn hóa:
Hành vi khi không đạt:
Tác dụng phụ không được phép xảy ra:
Bằng chứng nghiệm thu:
Chủ sở hữu:
~~~

Không phải mọi dự án đều cần một biểu mẫu dài cho mỗi trường. Với nhiều trường cùng endpoint, một bảng hợp đồng có thể chứa miền dữ liệu; các yêu cầu chung mô tả cách parse, lỗi và giới hạn tài nguyên. Điều quan trọng là người triển khai không phải tự đoán các quyết định có ảnh hưởng đến bảo mật.

Các chi tiết hay bị bỏ sót gồm:

**Thiếu, null và rỗng.** Không gửi `deliveryNote`, gửi `null` và gửi `""` là ba trạng thái khác nhau của dữ liệu. Dự án phải quyết định có hợp nhất chúng hay giữ nguyên ý nghĩa.

**Đơn vị của giới hạn.** “Tối đa 500 ký tự” chưa nói đang đếm byte UTF-8, đơn vị UTF-16, Unicode code point hay ký tự hiển thị. Chọn đơn vị khác nhau có thể làm frontend, backend và database bất đồng.

**Khoảng và tính bao hàm.** Viết rõ [1, 100] thay vì “từ 1 đến 100” nếu nhóm có nguy cơ hiểu khác nhau về hai đầu mút.

**Ép kiểu.** Nếu client gửi `"2"` hoặc `2.0`, máy chủ có tự đổi thành số nguyên không? Việc DTO cuối cùng chứa một `Integer` không chứng minh đầu vào gốc đã tuân đúng hợp đồng.

**Trường không được nhận.** Cần quyết định rõ cách xử lý `price`, `approved` hoặc `tenantId` nếu chúng không thuộc request công khai. Việc không hiển thị chúng trên form không ngăn client tự gửi.

**Thời điểm kiểm tra.** Một điều kiện phải đúng trước khi ghi dữ liệu hoặc trước khi phát message nào? Nếu chỉ viết “trước xử lý”, người triển khai có thể kiểm tra sau khi tác dụng phụ đã xảy ra.

## 5. Hợp đồng minh họa cho API tạo đơn

Giả sử dịch vụ cung cấp `POST /orders`, nhận JSON để đặt một loại sản phẩm trong mỗi đơn. Giá bán và tenant thực thi do máy chủ xác định từ ngữ cảnh được tin cậy. Client không được đặt các giá trị đó trong body.

### 5.1. Hợp đồng trường

| Trường | Bắt buộc | Hợp đồng chấp nhận |
| --- | --- | --- |
| `productId` | Có | String ASCII dài 1–64; khớp toàn bộ `[A-Za-z0-9][A-Za-z0-9_-]{0,63}` |
| `quantity` | Có | Token số JSON có dạng số nguyên không có phần thập phân hoặc số mũ; giá trị từ 1 đến 100 |
| `deliveryNote` | Không | Nếu có phải là string; sau NFC dài tối đa 500 Unicode code point và 2.000 byte UTF-8; string rỗng được chấp nhận |
| Trường khác | Không được nhận | Bất kỳ tên trường nào ngoài ba tên trên đều làm request bị từ chối |

Quy tắc bổ sung cho hợp đồng này:

1. Tên trường phân biệt hoa thường: `productId` khác `ProductId`.
2. Không tự trim, đổi hoa/thường hoặc URL-decode `productId`.
3. `quantity` không nhận string, boolean, null, array hoặc object; `2.0` và `2e0` cũng bị từ chối theo chính sách biểu diễn của endpoint này.
4. `deliveryNote` thiếu có nghĩa “không có ghi chú”; `null` không được nhận.
5. Ghi chú cho phép tiếng Việt, dấu câu và emoji; không cho phép code point điều khiển thuộc nhóm Cc, ngoại trừ tab U+0009 và xuống dòng U+000A.
6. Không nhận surrogate đơn lẻ trong chuỗi Unicode sau giải mã. Bộ giải mã và parser phải thực hiện điều kiện này trước validator trường.
7. Không chấp nhận tên trường JSON lặp lại, kể cả khi hai lần xuất hiện có cùng giá trị.
8. Đối tượng root phải là object. Không nhận array hoặc giá trị scalar thay thế.

Từ “token số nguyên” ở đây là chính sách riêng của API, chặt hơn việc chỉ hỏi giá trị toán học có phải số nguyên hay không. Nó đòi hỏi tầng đọc JSON còn quan sát được dạng token; một mapper tự chuyển `2.0` thành `2` có thể làm mất bằng chứng cần kiểm tra.

Ví dụ được chấp nhận về cấu trúc và giá trị:

~~~json
{
  "productId": "BOOK_101",
  "quantity": 2,
  "deliveryNote": "Gọi trước khi giao, cảm ơn!"
}
~~~

Ví dụ phải bị từ chối:

~~~json
{
  "productId": "BOOK_101",
  "quantity": "2",
  "price": 1,
  "approved": true
}
~~~

Payload thứ hai vi phạm đồng thời kiểu của `quantity` và tập tên trường cho phép. Đặc tả lỗi phải quyết định có trả một lỗi hay một tập lỗi giới hạn; không để số lỗi phản hồi tăng không giới hạn theo payload.

### 5.2. Giới hạn ở cấp request

Trong ví dụ này, nhóm thiết kế chọn:

| Thuộc tính | Giới hạn minh họa |
| --- | --- |
| Media type | Chỉ nhận `application/json` theo hợp đồng endpoint |
| Encoding | UTF-8 hợp lệ; không tự thay byte sai bằng ký tự thay thế |
| Content encoding | Không hỗ trợ body nén ở endpoint này; từ chối content encoding ngoài chính sách |
| Kích thước body | Tối đa 8.192 byte payload trước parse, bao gồm whitespace JSON |
| Độ sâu JSON | Tối đa 4 container lồng nhau; container root được tính là mức 1 |
| Số lỗi trường trong phản hồi | Tối đa 3 mục |
| Trường JSON lặp | Từ chối trước khi ánh xạ sang object nghiệp vụ |

Giới hạn body phải được áp dụng bằng lượng dữ liệu thực tế đã đọc, không chỉ tin giá trị `Content-Length`. Hệ thống cũng cần áp dụng chính sách tương ứng khi request được truyền theo cơ chế không biết trước toàn bộ chiều dài.

Các con số này phải được lựa chọn lại nếu API đổi thành đơn nhiều dòng hoặc nhận dữ liệu phong phú hơn. “Có giới hạn” chưa đủ; giới hạn phải phù hợp với tải hợp lệ và được đặt tại thành phần thực sự đọc hoặc cấp phát dữ liệu.

RFC 8259 cho phép implementation đặt giới hạn về kích thước, độ sâu và phạm vi số. RFC cũng mô tả khác biệt giữa các implementation khi object có tên thành viên lặp. Vì vậy, không nên mặc định mọi parser hoặc gateway sẽ tự có cùng hành vi. [RFC 8259, mục 4 và 9](https://www.rfc-editor.org/rfc/rfc8259.html).

## 6. Bộ yêu cầu bảo mật và truy vết rủi ro

Có thể chuyển hợp đồng thành các yêu cầu độc lập để phân công và nghiệm thu:

| ID minh họa | Rủi ro | Yêu cầu | Bằng chứng cần có |
| --- | --- | --- | --- |
| IV-001 | Đọc body quá lớn hoặc parse quá sâu | Áp dụng giới hạn body và độ sâu trước khi xử lý nghiệp vụ | Request vượt biên bị từ chối; không tạo đơn |
| IV-002 | Ép kiểu làm nhận dữ liệu ngoài hợp đồng | Từ chối kiểu và dạng biểu diễn không được hỗ trợ | `"2"`, `2.0`, `2e0` không đi tới tạo đơn |
| IV-003 | Nhận trường điều khiển do client chèn | Chỉ ánh xạ ba trường công khai; trường dư làm thất bại toàn request | Chèn `price`, `approved` hoặc `tenantId` đều thất bại |
| IV-004 | Hai tầng hiểu khác giá trị cùng một trường | Từ chối tên trường lặp ngay tại parser | Payload chứa hai `quantity` không tạo object đầu vào hợp lệ |
| IV-005 | Các tầng kiểm tra và lưu khác biểu diễn | Thực hiện chính sách biểu diễn nhất quán cho từng trường | Ghi chú lưu và kiểm tra theo cùng dạng NFC |
| IV-006 | Giá trị ngoài miền gây thao tác sai | Chỉ nhận `quantity` trong [1, 100] | Các ca 0, 1, 100, 101 có kết quả đúng hợp đồng |
| IV-007 | Yêu cầu sai vẫn gây thay đổi một phần | Request bị từ chối không tạo đơn, giữ hàng hoặc phát sự kiện tạo đơn | Kiểm tra kho dữ liệu và sự kiện cho correlation ID tương ứng |
| IV-008 | Phản hồi lỗi hoặc log tiết lộ dữ liệu | Trả mã lỗi giới hạn; không phản chiếu toàn bộ body hoặc ghi chú | Response và log không chứa payload, token hay stack trace |

Bảng trên chỉ là tập yêu cầu **input validation** của ví dụ. Tính đúng đắn toàn hệ thống còn phụ thuộc các yêu cầu riêng về xác thực, phân quyền, xử lý đồng thời, audit và khôi phục.

Chẳng hạn, nếu số lượng còn trong kho là 2, hai request hợp lệ cùng đặt 2 đơn vị có thể gây vượt tồn nếu kiểm tra và cập nhật không được bảo vệ đúng. Đó không phải lỗi mà việc kiểm tra `quantity <= 100` có thể tự giải quyết.

Vì vậy, yêu cầu “chỉ tạo đơn khi đủ hàng” cần một cơ chế bảo đảm tính nhất quán khi cập nhật trạng thái, thay vì chỉ đọc tồn kho một lần tại bước validation. Có thể tham chiếu yêu cầu quản lý tồn kho từ IV-007 nhưng không gộp mọi vấn đề thành một validator.

## 7. Biểu diễn, chuẩn hóa và ý nghĩa dữ liệu

Trong hợp đồng minh họa, `productId` là định danh ASCII do hệ thống cấp. Nhóm chọn từ chối khoảng trắng và ký tự ngoài tập, thay vì sửa chúng. Nếu nhận `" BOOK_101"` rồi tự trim, API đã chấp nhận một biểu diễn mà hợp đồng nói là không hợp lệ.

Với `deliveryNote`, nhóm chọn NFC trước khi kiểm tra giới hạn và lưu. Mục đích của lựa chọn này là tạo một biểu diễn ổn định cho nội dung văn bản trong ví dụ; nó không biến nội dung thành chuỗi “an toàn trong mọi ngữ cảnh”.

Thứ tự cho trường ghi chú được quy định cụ thể:

~~~text
Byte UTF-8 hợp lệ
    → JSON parser tạo chuỗi Unicode hợp lệ
    → chuẩn hóa NFC
    → kiểm tra code point, số byte và ký tự điều khiển
    → lưu đúng chuỗi đã kiểm tra
~~~

Giới hạn body vẫn phải có trước các bước này. Một giới hạn đặt sau chuẩn hóa không ngăn việc đọc một body đầu vào quá lớn.

Trong Java, `String.length()` đếm đơn vị UTF-16; `codePointCount(0, length())` đếm Unicode code point. Một emoji ngoài Basic Multilingual Plane có thể chiếm hai đơn vị UTF-16. Số code point cũng không phải số grapheme mà người dùng nhìn thấy. [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html).

Do đó, hợp đồng “500 code point và 2.000 byte UTF-8” phải được thực hiện đúng hai phép đo đó. Không được âm thầm thay bằng `String.length() <= 500` rồi coi là tương đương.

Quy tắc chuẩn hóa phải được quyết định theo **ý nghĩa trường**. Không áp dụng NFC, chuyển hoa/thường hoặc trim hàng loạt cho token bí mật, chữ ký, mật khẩu hay identifier mà giao thức khác yêu cầu giữ nguyên. Nếu hệ thống có xác minh chữ ký trên byte gốc, thứ tự xác minh và biến đổi dữ liệu phải tuân theo giao thức chữ ký đó, không suy từ quy tắc ghi chú của ví dụ.

## 8. Minh họa chuyển hợp đồng trường thành Java

Đoạn mã sau minh họa phần kiểm tra giá trị sau khi tầng transport đã áp dụng hợp đồng JSON. Nó không phải một HTTP server, JSON parser hay toàn bộ cơ chế bảo vệ endpoint.

Các tiền điều kiện của đoạn mã:

- Parser đã từ chối tên trường lặp, trường dư và Unicode không hợp lệ.
- Parser chỉ ánh xạ `quantity` từ token số nguyên được hỗ trợ, không ép kiểu.
- Nếu `deliveryNote` xuất hiện dưới dạng null thì parser đã từ chối; giá trị Java `null` ở đây chỉ biểu diễn trường không được gửi.
- Giới hạn body và độ sâu đã được thực thi trước khi tạo DTO.

~~~java
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.regex.Pattern;

public final class PurchaseInputRules {
    private static final Pattern PRODUCT_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,63}");

    public record Incoming(
            String productId,
            Integer quantity,
            String deliveryNote) {
    }

    public record Accepted(
            String productId,
            int quantity,
            String deliveryNote) {
    }

    public static Accepted validate(Incoming input) {
        if (input == null) {
            throw invalid("body", "OBJECT_REQUIRED");
        }

        String productId = input.productId();
        if (productId == null
                || productId.length() < 1
                || productId.length() > 64
                || !PRODUCT_ID.matcher(productId).matches()) {
            throw invalid("productId", "INVALID_PRODUCT_ID");
        }

        Integer quantity = input.quantity();
        if (quantity == null || quantity < 1 || quantity > 100) {
            throw invalid("quantity", "INVALID_QUANTITY");
        }

        String note = input.deliveryNote();
        if (note != null) {
            note = Normalizer.normalize(note, Normalizer.Form.NFC);

            int codePoints = note.codePointCount(0, note.length());
            int utf8Bytes = note.getBytes(StandardCharsets.UTF_8).length;
            boolean forbiddenControl = note.codePoints().anyMatch(
                    cp -> Character.getType(cp) == Character.CONTROL
                            && cp != 0x0009
                            && cp != 0x000A);

            if (codePoints > 500 || utf8Bytes > 2000
                    || forbiddenControl) {
                throw invalid("deliveryNote", "INVALID_DELIVERY_NOTE");
            }
        }

        return new Accepted(productId, quantity, note);
    }

    private static IllegalArgumentException invalid(
            String field, String code) {
        return new IllegalArgumentException(field + ":" + code);
    }
}
~~~

`matches()` được dùng để kiểm tra toàn bộ mã sản phẩm; phần giới hạn chiều dài được thực hiện trước khi khớp mẫu. Đối tượng `Accepted` chứa chính ghi chú sau NFC đã vượt qua kiểm tra, giảm nguy cơ kiểm tra một chuỗi nhưng lưu chuỗi khác.

`IllegalArgumentException` chỉ là cách minh họa trả lỗi trong phạm vi hàm. Tầng API cần chuyển lỗi có cấu trúc thành hợp đồng phản hồi đã chốt, thay vì mặc định trả exception hoặc stack trace cho client. Không cần đưa giá trị bị từ chối vào thông báo exception.

Một khác biệt quan trọng là đoạn mã không biết DTO `quantity = 2` đã xuất phát từ `2`, `"2"` hay `2.0` nếu mapper trước đó tự ép kiểu. Bởi vậy, đọc annotation trên DTO hoặc xem validator đơn lẻ chưa đủ để chứng minh IV-002 đã được triển khai.

Tương tự, sau khi parser đưa JSON vào một map thông thường, bằng chứng về tên trường lặp có thể đã mất. IV-004 cần được thực thi tại nơi còn quan sát được từng thành viên của object.

Đối với annotation validation trong một framework, đặc tả vẫn phải nói rõ validation được kích hoạt trên đường vào nào và khi nào. Có annotation trên class không chứng minh đường nhập message hoặc đường gọi nội bộ đã thực sự chạy nó.

## 9. Hành vi thất bại phải là một phần của yêu cầu

Với ví dụ này, nhóm chọn hợp đồng phản hồi:

| Tình huống | HTTP status minh họa | Mã lỗi |
| --- | --- | --- |
| Body vượt giới hạn | 413 | `PAYLOAD_TOO_LARGE` |
| Media type hoặc content encoding không được hỗ trợ | 415 | `UNSUPPORTED_REPRESENTATION` |
| JSON không parse được, encoding sai hoặc cấu trúc bị cấm | 400 | `INVALID_REQUEST` |
| Trường không đạt hợp đồng giá trị | 400 | `INVALID_INPUT` |

Đây là lựa chọn của API minh họa. Một dự án có thể dùng quy ước khác cho lỗi ngữ nghĩa, miễn là hợp đồng được chốt và nhất quán. Không nên để client phải đoán dựa trên tên exception của framework.

Ví dụ phản hồi cho `quantity = 101`:

~~~json
{
  "code": "INVALID_INPUT",
  "requestId": "server-generated-id",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE"
    }
  ]
}
~~~

`requestId` ở ví dụ do máy chủ tạo hoặc chấp nhận qua một cơ chế kiểm soát riêng. Không phản chiếu vô điều kiện header tùy ý của client vào phản hồi và log.

Một yêu cầu thất bại còn cần nói rõ:

**Không tiếp tục một phần.** Nếu `quantity` không hợp lệ, hệ thống không được tự đổi thành 1 rồi tạo đơn. Nếu một trường bị từ chối, không được âm thầm bỏ trường đó và tiếp tục, trừ khi hợp đồng đã cho phép hành vi ấy.

**Không gây tác dụng phụ nghiệp vụ.** Với request bị từ chối ở bước validation, số đơn tạo ra, lần giữ tồn kho và sự kiện tạo đơn phải bằng 0. Telemetry bảo mật được phép phát sinh theo chính sách; cần phân biệt telemetry với sự kiện nghiệp vụ.

**Không trả chi tiết triển khai.** Phản hồi không bao gồm stack trace, câu SQL, đường dẫn nội bộ hoặc tên class. Thông báo cho người dùng có thể được dịch, nhưng mã lỗi phục vụ tích hợp cần ổn định.

**Không dùng validation làm kênh dò tài nguyên.** Sau khi qua định dạng, lỗi về quyền hoặc sự tồn tại của sản phẩm cần theo chính sách tiết lộ thông tin riêng. Đừng vô tình cho người gọi phân biệt toàn bộ danh mục sản phẩm qua các thông báo quá chi tiết.

## 10. Logging và vận hành đối với đầu vào không hợp lệ

Một request sai không nhất thiết là tấn công. Nó có thể đến từ phiên bản client cũ, người dùng nhập nhầm, lỗi đồng bộ hoặc một tác nhân đang dò hệ thống. Vì thế, logging cần đủ để tìm nguyên nhân mà không thu thập toàn bộ nội dung người dùng.

Với dịch vụ minh họa, bản ghi lỗi validation có thể chứa:

~~~json
{
  "event": "request_validation_failed",
  "route": "POST /orders",
  "ruleId": "IV-006",
  "field": "quantity",
  "reason": "OUT_OF_RANGE",
  "requestId": "server-generated-id",
  "contractVersion": "orders-v1"
}
~~~

Không cần đưa nguyên body, ghi chú giao hàng, thông tin xác thực hoặc giá trị bí mật vào bản ghi. Nếu cần phân tích dữ liệu mẫu, phải có cơ chế thu thập, quyền xem, thời hạn lưu và che dữ liệu được phê duyệt riêng.

Các metric nên dùng tập nhãn có số lượng hữu hạn như route, rule ID và reason code. Dùng raw `productId` hoặc nội dung ghi chú làm nhãn sẽ làm số lượng nhãn phụ thuộc dữ liệu tùy ý của client.

Đặc tả vận hành có thể yêu cầu theo dõi tỷ lệ lỗi theo phiên bản hợp đồng. Khi triển khai một thay đổi làm tỷ lệ `UNKNOWN_FIELD` tăng mạnh, nhóm có bằng chứng để phân biệt vấn đề tương thích với hành vi dò tìm. Ngưỡng cảnh báo cần dựa trên lưu lượng thật, không sao chép một con số chung cho mọi dịch vụ.

Trong trường hợp logging gặp lỗi, việc từ chối payload sai không được biến thành chấp nhận payload. Các yêu cầu về độ tin cậy của telemetry và hành vi khi hệ thống ghi log lỗi cần được quản lý riêng.

## 11. Tiêu chí nghiệm thu gắn với từng lớp

Tiêu chí nghiệm thu nên chỉ ra **đầu vào, kết quả bên ngoài và trạng thái bên trong cần quan sát**. “Có test validation” không đủ để kết luận yêu cầu đã đạt.

Ma trận sau là đặc tả ca kiểm thử cho ví dụ, không phải báo cáo rằng các ca đã được chạy:

| Ca | Đầu vào hoặc điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| T01 | `productId = "BOOK_101"`, `quantity = 1` | Qua validation; còn phải qua kiểm tra quyền và nghiệp vụ |
| T02 | `quantity = 100` | Qua giới hạn trường |
| T03 | `quantity = 0` hoặc `101` | `INVALID_INPUT`; không có tác dụng phụ nghiệp vụ |
| T04 | Thiếu `quantity` hoặc gửi null | Bị từ chối |
| T05 | `quantity` là `"2"`, `true` hoặc `[]` | Bị từ chối, không tự ép kiểu |
| T06 | `quantity = 2.0` hoặc `2e0` | Bị từ chối theo chính sách token của endpoint |
| T07 | `productId` dài 64 và 65 ký tự ASCII hợp lệ | 64 qua giới hạn; 65 bị từ chối |
| T08 | `productId = " BOOK_101"` | Bị từ chối; không trim thành mã khác |
| T09 | Thêm `price`, `approved` hoặc `tenantId` | Bị từ chối vì trường dư |
| T10 | Hai thành viên `quantity` trong cùng object | Bị từ chối tại parser |
| T11 | Ghi chú thiếu, string rỗng, null | Thiếu và rỗng được nhận; null bị từ chối |
| T12 | Ghi chú NFC đúng 500 và 501 code point | 500 được nhận nếu đạt điều kiện khác; 501 bị từ chối |
| T13 | Ghi chú có emoji hợp lệ trong giới hạn | Được nhận; không nhầm code point với UTF-16 unit |
| T14 | Ghi chú có U+0000 | Bị từ chối, không cắt chuỗi tại ký tự đó |
| T15 | Body đúng 8.192 và 8.193 byte, cùng có cấu trúc hợp lệ | Mức 8.192 qua giới hạn kích thước; 8.193 bị từ chối |
| T16 | UTF-8 sai, JSON lỗi hoặc surrogate đơn lẻ | Bị từ chối có kiểm soát |
| T17 | Mã sản phẩm đúng định dạng nhưng ngoài phạm vi được phép | Validation trường có thể qua; kiểm tra quyền phải chặn thao tác |
| T18 | Request sai có ghi chú nhạy cảm | Response và log không phản chiếu ghi chú |

Khi tạo dữ liệu ở biên kích thước, có thể thêm whitespace JSON để đạt đúng số byte mà không thay đổi nội dung object. Nếu một ca đồng thời vi phạm nhiều điều kiện, đặc tả phải nói rõ có ưu tiên lỗi nào hay chỉ yêu cầu request bị từ chối đúng cách.

Giới hạn độ sâu cần ca thử riêng ở lớp parser, kể cả khi hợp đồng object đặt hàng không có trường container lồng nhau. Payload lồng nhau có thể đã sai schema, nhưng mục tiêu của ca giới hạn parse là chứng minh parser không tiếp tục đọc cấu trúc vượt ngân sách chỉ để phát hiện schema sai ở bước sau.

Đối với hai ghi chú khác biểu diễn nhưng tương đương theo NFC, bằng chứng cần cho thấy chuỗi dùng để kiểm tra và chuỗi được lưu tuân cùng chính sách. Với yêu cầu không có tác dụng phụ, chỉ kiểm tra HTTP status là chưa đủ: cần quan sát kho đơn, tồn kho và nơi phát sự kiện trong môi trường kiểm thử.

## 12. Phân công trách nhiệm và bằng chứng

Một yêu cầu có thể cần nhiều thành phần cùng thực hiện:

| Thành phần | Trách nhiệm trong ví dụ | Giới hạn trách nhiệm |
| --- | --- | --- |
| Frontend | Hướng dẫn nhập, hiển thị lỗi sớm | Không là căn cứ duy nhất để tin request |
| Gateway hoặc HTTP server | Kiểm soát body và các giới hạn giao thức được giao | Không tự biết toàn bộ ngữ nghĩa sản phẩm |
| JSON parser và mapper | Tuân chính sách token, field, Unicode và giới hạn parse | Không tự quyết định người gọi có quyền đặt hàng |
| Validator ứng dụng | Kiểm tra miền giá trị và chuẩn hóa được cho phép | Không thay thế bảo vệ dữ liệu khi đưa vào SQL hoặc HTML |
| Service nghiệp vụ | Kiểm tra quyền, trạng thái và thực hiện thao tác nhất quán | Không giả định mọi caller nội bộ đã kiểm tra đủ |
| Database và eventing | Ràng buộc dữ liệu, giao dịch hoặc cơ chế nhất quán theo thiết kế | Không có nghĩa request sai được phép tới bước ghi |

Một đường gọi nội bộ đi thẳng vào service là một đường cần xem xét khi phân công. Nếu service chỉ nhận kiểu dữ liệu đã được kiểm tra, việc tạo kiểu đó phải được kiểm soát; nếu ai cũng tự dựng được object với giá trị tùy ý thì tên `Accepted` tự nó không tạo bảo đảm bảo mật.

Bằng chứng có thể gồm hợp đồng API, cấu hình parser, ánh xạ yêu cầu tới mã thực thi và kết quả kiểm thử qua đường vào thật. Mỗi loại chứng minh một phần; không thay thế tất cả bằng một ảnh chụp có annotation.

Nếu frontend giới hạn 500 code point nhưng database chỉ chứa được số byte nhỏ hơn, nhóm cần xử lý sai khác trước khi nghiệm thu. Lỗi lưu trữ muộn không phải là một phản hồi validation đúng hợp đồng.

## 13. Giới hạn của validation và các lỗi đặc tả thường gặp

### Chặn chuỗi “đáng ngờ” thay cho xác định miền hợp lệ

Đối với mã sản phẩm có cấu trúc, yêu cầu tập ký tự và chiều dài là phù hợp. Đối với ghi chú tự do, cấm các từ `select`, `script` hoặc dấu nháy sẽ làm mất dữ liệu hợp lệ và không tạo bảo đảm an toàn khi dùng dữ liệu ở hệ thống khác.

Nếu giá trị được đưa vào câu SQL, cần một yêu cầu riêng về truy vấn tham số hóa cho giá trị dữ liệu. Không suy ra khả năng chống SQL injection từ việc ghi chú đã vượt qua validation. [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).

Nếu ghi chú được hiển thị trong giao diện, cần dùng API xử lý như văn bản hoặc cơ chế bảo vệ đúng ngữ cảnh hiển thị. Chấp nhận ký tự `<` trong văn bản không có nghĩa được phép chèn trực tiếp chuỗi đó vào HTML đang được diễn giải. [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).

### Viết “dùng regex cho mọi input”

Mẫu đơn giản phù hợp với `productId` nhưng không phải lời giải cho JSON parser, phạm vi số hoặc toàn bộ văn bản tự do. Một yêu cầu tốt chỉ ra điều kiện phải đạt; regex, parser hoặc hàm kiểm tra là lựa chọn triển khai phải đáp ứng điều kiện đó.

### Tự sửa giá trị sai mà không có hợp đồng

Đổi số âm thành 1, cắt ghi chú quá dài hoặc bỏ trường lạ có thể che lỗi client và làm thay đổi ý định người dùng. Nếu sản phẩm muốn tự sửa một số dữ liệu, phải đặc tả rõ trường nào, phép biến đổi nào và cách thông báo. Không dùng từ “sanitize” để mặc định cho phép mọi biến đổi.

### Tin dữ liệu vì đã lưu hoặc đã qua gateway

Bằng chứng dữ liệu đã lưu chỉ nói có một lần ghi. Nó không chứng minh dữ liệu tuân hợp đồng mới hoặc phù hợp với thao tác hiện tại. Tương tự, gateway cho request đi qua chỉ chứng minh các kiểm soát được cấu hình tại gateway đã cho phép; quyền và trạng thái nghiệp vụ vẫn thuộc phần được giao cho ứng dụng.

### Gộp mọi kiểm soát vào một câu “validate all”

Câu này làm mất ownership. Khi có lỗi, nhóm không xác định được parser, validator, phân quyền hay giao dịch phải xử lý. Chia thành điều kiện độc lập giúp định vị nơi thực thi và đặt bằng chứng cụ thể cho từng rủi ro.

## 14. Quản lý thay đổi hợp đồng đầu vào

Một thay đổi nhỏ về validation có thể làm client đang hoạt động bị từ chối. Ví dụ, từ chấp nhận trường dư sang từ chối trường dư sẽ ảnh hưởng client gửi metadata chưa được dùng. Thêm một trường mới cũng cần phối hợp nếu consumer cũ áp dụng tập trường đóng.

Vì vậy, thay đổi hợp đồng nên đi cùng:

- Phiên bản hoặc cơ chế tương thích được công bố cho API hay message.
- Phân tích caller nào đang gửi dữ liệu bị ảnh hưởng.
- Cập nhật giới hạn, mã lỗi và tiêu chí nghiệm thu liên quan.
- Thứ tự triển khai giữa producer và consumer.
- Kế hoạch xử lý dữ liệu cũ khi được đọc cho một thao tác mới.

Không nên mở rộng miền chấp nhận chỉ để làm biến mất metric lỗi mà chưa biết nguyên nhân. Ngược lại, không nên siết quy tắc chỉ vì một regex mới có vẻ “an toàn hơn” mà bỏ qua dữ liệu hợp lệ và mục tiêu nghiệp vụ.

Một đặc tả input validation hoàn chỉnh giúp nhóm trả lời được: dữ liệu nào được nhận, tại ranh giới nào, được hiểu theo biểu diễn nào, bị từ chối ra sao và bằng chứng nào xác nhận hệ thống chưa thực hiện thao tác ngoài hợp đồng. Khi những điều này rõ ràng, yêu cầu bảo mật trở thành một phần có thể triển khai và kiểm chứng của thiết kế hệ thống.
