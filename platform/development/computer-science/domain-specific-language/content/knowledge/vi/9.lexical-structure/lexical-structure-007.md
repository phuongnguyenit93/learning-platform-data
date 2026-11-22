# Chú thích

## 1. Chú thích trong DSL là gì?

Chú thích (comment) là phần văn bản được đặt trong mã nguồn để giải thích ý định, cung cấp ngữ cảnh hoặc ghi lại thông tin dành cho người đọc. Trình phân tích DSL thường nhận biết dấu mở đầu của chú thích và bỏ qua nội dung đó khi tạo cấu trúc thực thi. Vì vậy, chú thích thường không làm thay đổi kết quả chương trình.

Ví dụ, một DSL quy tắc có thể mô tả điều kiện áp dụng chiết khấu:

~~~text
# Chỉ áp dụng cho khách hàng thân thiết
rule loyal-customer-discount {
    when customer.membership == "GOLD"
    then discount.percent = 10
}
~~~

Dòng bắt đầu bằng dấu thăng giải thích mục đích của quy tắc. Khi xử lý, DSL engine cần hiểu phần khai báo rule, điều kiện và hành động; dòng chú thích không phải là một điều kiện hay một hành động.

Chú thích là một phần của từ vựng (lexical vocabulary) vì lexer hoặc parser phải nhận biết cách bắt đầu và kết thúc chú thích. Tùy thiết kế ngôn ngữ, chú thích có thể được loại bỏ ngay trong bước phân tích từ vựng, được giữ lại như trivia gắn với token, hoặc được đưa vào AST nếu công cụ cần hiển thị và xử lý chúng.

## 2. Vì sao DSL cần chú thích?

Một DSL tốt giúp người viết diễn đạt công việc bằng khái niệm của miền nghiệp vụ. Tuy nhiên, cú pháp không thể tự giải thích mọi quyết định. Chú thích bổ sung những thông tin mà cấu trúc chương trình không thể hiện đầy đủ:

- **Giải thích lý do:** vì sao một quy tắc tồn tại hoặc vì sao chọn một ngưỡng cụ thể.
- **Ghi lại ngữ cảnh:** liên kết tới yêu cầu, quyết định nghiệp vụ hoặc quy trình liên quan.
- **Làm rõ ngoại lệ:** giải thích trường hợp đặc biệt mà người đọc dễ hiểu nhầm.
- **Hỗ trợ bảo trì:** cảnh báo về giới hạn, giả định hoặc điều kiện cần xem xét trước khi sửa.
- **Tạo tài liệu:** cung cấp mô tả cho rule, module, hàm hoặc cấu hình.
- **Hỗ trợ công cụ:** đánh dấu TODO, FIXME, mã issue hoặc metadata theo quy ước của dự án.

Chú thích hữu ích nhất khi trả lời câu hỏi tại sao. Nếu chỉ lặp lại điều mà cú pháp đã nói rõ, chú thích sẽ nhanh chóng lỗi thời khi mã nguồn thay đổi.

Ví dụ:

~~~sql
-- Giữ khoảng thời gian nửa mở để không đếm trùng đầu tháng kế tiếp.
SELECT *
FROM invoices
WHERE issued_at >= DATE '2026-01-01'
  AND issued_at <  DATE '2026-02-01';
~~~

Chú thích giải thích lý do dùng điều kiện nhỏ hơn ngày đầu tháng kế tiếp. Nó cung cấp ngữ cảnh thiết kế mà bản thân câu truy vấn không thể hiện.

## 3. Các kiểu chú thích phổ biến

Mỗi DSL có thể định nghĩa một hoặc nhiều kiểu chú thích. Những dạng thường gặp gồm:

| Kiểu | Dấu hiệu phổ biến | Phạm vi |
|---|---|---|
| Chú thích cuối dòng | # hoặc // | Từ dấu mở đầu đến hết dòng |
| Chú thích dòng SQL | -- | Từ dấu mở đầu đến hết dòng |
| Chú thích khối | /* ... */ | Có thể trải qua nhiều dòng |
| Chú thích tài liệu | /** ... */ hoặc cú pháp riêng | Gắn với thành phần cần tài liệu hóa |
| Chú thích có cấu trúc | Cú pháp comment kết hợp tag hoặc metadata | Được công cụ trích xuất theo quy ước |

Không nên giả định một kiểu chú thích có mặt trong mọi DSL. Cú pháp phụ thuộc grammar, lexer và quy ước của ngôn ngữ.

### 3.1. Chú thích cuối dòng

Chú thích cuối dòng bắt đầu bằng một ký hiệu và kết thúc khi dòng hiện tại kết thúc:

~~~text
# Mức ưu tiên cao hơn được xử lý trước
priority = 100

timeout = 30  # Đơn vị: giây
~~~

Một số DSL dùng dấu thăng, một số dùng hai dấu gạch chéo. Cần chú ý rằng ký hiệu chú thích có thể xung đột với dữ liệu hợp lệ. Ví dụ, dấu thăng có thể xuất hiện trong chuỗi hoặc trong cú pháp màu sắc; lexer phải phân biệt ngữ cảnh chuỗi với ngữ cảnh comment.

### 3.2. Chú thích khối

Chú thích khối được mở và đóng bằng một cặp dấu phân cách:

~~~text
/*
 * Quy tắc này chỉ áp dụng cho đơn hàng nội địa.
 * Đơn hàng quốc tế được xử lý trong policy riêng.
 */
rule domestic-shipping {
    when order.destination.region == "DOMESTIC"
    then shipping.method = "STANDARD"
}
~~~

Chú thích khối phù hợp với giải thích nhiều dòng hoặc tạm thời vô hiệu hóa một phần văn bản trong một số ngôn ngữ. Tuy nhiên, không phải mọi DSL đều cho phép lồng chú thích khối. Nếu dấu mở đầu xuất hiện bên trong một comment chưa đóng, cách xử lý phải được grammar quy định rõ.

### 3.3. Chú thích tài liệu

Một số ngôn ngữ phân biệt comment thông thường với comment dùng để sinh tài liệu. Ví dụ, Java sử dụng dạng Javadoc:

~~~java
/**
 * Tính phí giao hàng theo khu vực và trọng lượng.
 *
 * @param region khu vực nhận hàng
 * @param weightKg trọng lượng tính bằng kilogram
 * @return chi phí giao hàng theo đơn vị tiền tệ của bảng giá
 */
public Money calculateShippingCost(Region region, BigDecimal weightKg) {
    // Phần triển khai
}
~~~

Tài liệu hóa có cấu trúc giúp IDE hoặc công cụ sinh tài liệu trích xuất mô tả, tham số và giá trị trả về. Trong một DSL riêng, có thể thiết kế cú pháp tương tự cho module, rule, schema hoặc function. Cần phân biệt rõ comment tài liệu với comment thông thường để người viết biết phần nào được công cụ xuất bản.

## 4. Cú pháp chú thích trong một số DSL và định dạng quen thuộc

Các ví dụ dưới đây minh họa những quy ước phổ biến. Khi dùng trong dự án thật, cần theo đúng đặc tả của ngôn ngữ hoặc dialect đang chạy.

### 4.1. SQL

SQL phổ biến hai dạng comment:

~~~sql
-- Chú thích một dòng
SELECT id, total
FROM orders;

/*
  Chú thích nhiều dòng.
  Có thể giải thích mục đích của truy vấn.
*/
SELECT COUNT(*)
FROM orders
WHERE status = 'PAID';
~~~

Comment SQL không được gửi tới bộ thực thi như một phần của biểu thức truy vấn, dù một số công cụ có thể giữ comment trong log hoặc dùng comment hint theo cú pháp riêng của hệ quản trị. Cú pháp hint không nên bị nhầm với comment thông thường vì nó có thể ảnh hưởng đến cách tối ưu hóa truy vấn.

### 4.2. YAML

YAML dùng dấu thăng để bắt đầu comment:

~~~yaml
# Cấu hình kết nối dịch vụ báo cáo
report:
  format: pdf
  retries: 3  # Số lần thử lại khi dịch vụ tạm thời lỗi
~~~

YAML không có cú pháp comment khối riêng. Muốn chú thích nhiều dòng, người viết đặt dấu thăng ở đầu từng dòng. Comment không phải là một phần của mô hình dữ liệu YAML sau khi parser tạo object, nên nếu đọc YAML rồi ghi lại, comment và cách định dạng ban đầu thường bị mất.

### 4.3. JSON và JSONC

JSON chuẩn không hỗ trợ comment. Tệp sau không phải JSON hợp lệ:

~~~json
{
  // Không hợp lệ trong JSON chuẩn
  "retries": 3
}
~~~

Một số công cụ hỗ trợ JSONC hoặc JSON5, là các biến thể mở rộng cho phép comment hoặc cú pháp bổ sung. Không nên đặt comment vào tệp được tiêu thụ bởi parser JSON chuẩn nếu không chắc hệ thống hỗ trợ biến thể đó. Nếu cần ghi chú trong JSON chuẩn, có thể dùng trường mô tả được schema cho phép, nhưng trường này là dữ liệu thực sự chứ không phải comment.

### 4.4. HCL và Terraform

HCL thường cho phép comment bằng dấu thăng, hai dấu gạch chéo và comment khối:

~~~hcl
# Sử dụng mạng của môi trường staging
variable "vpc_id" {
  type = string
}

// Chỉ mở cổng HTTPS cho dịch vụ web
resource "example_firewall_rule" "https" {
  port = 443
}

/*
 * Mô tả tài nguyên cần được giữ đồng bộ
 * với cấu hình triển khai của nhóm.
 */
~~~

Các comment giúp giải thích ý định của cấu hình hạ tầng. Chúng không thay thế tên resource rõ nghĩa, metadata hoặc tài liệu vận hành.

### 4.5. CSS

CSS dùng comment khối:

~~~css
/* Bố cục danh sách sản phẩm */
.product-list {
    display: grid;
    gap: 1rem;
}
~~~

CSS không dùng dấu // để mở comment. Viết nhầm cú pháp có thể khiến phần văn bản bị hiểu là token hoặc giá trị không hợp lệ.

### 4.6. Regular expression

Regex không có một cú pháp comment chung cho mọi engine. Một số engine hỗ trợ chế độ extended hoặc verbose, trong đó có thể dùng dấu thăng để ghi chú và khoảng trắng được bỏ qua:

~~~regex
(?x)
^
  ORD-       # Tiền tố mã đơn hàng
  \d{4}      # Bốn chữ số
  -
  [A-Z]{2}   # Hai chữ cái viết hoa
$
~~~

Ví dụ này phụ thuộc engine hỗ trợ inline flag x. Nếu engine không hỗ trợ, dấu thăng có thể được hiểu là ký tự cần khớp hoặc làm mẫu không hợp lệ.

## 5. Chú thích được xử lý như thế nào?

Trong một DSL dạng văn bản, comment thường được xử lý ở bước phân tích từ vựng:

~~~mermaid
flowchart TD
    A["Mã nguồn DSL"] --> B["Lexer"]
    B --> C["Nhận diện token"]
    B --> D["Nhận diện comment"]
    C --> E["Parser"]
    E --> F["AST"]
    D -.-> G["Bỏ qua hoặc lưu trivia"]
    G -.-> H["Formatter / Documentation Tool"]
~~~

Lexer đọc ký tự đầu vào và phân loại chúng thành token như identifier, keyword, literal, operator và dấu phân cách. Khi gặp dấu mở đầu comment, lexer tiêu thụ nội dung theo quy tắc đã định. Có hai chiến lược phổ biến:

1. **Bỏ qua comment:** lexer không phát token comment cho parser. AST chỉ chứa cấu trúc có ý nghĩa cú pháp.
2. **Giữ comment như trivia:** lexer lưu comment cùng vị trí và liên kết nó với token hoặc node gần đó. Parser vẫn có thể bỏ qua comment khi xây dựng ngữ nghĩa, nhưng formatter và editor có thể dùng lại nội dung.

Nếu công cụ chỉ cần thực thi DSL, bỏ qua comment có thể đơn giản và hiệu quả. Nếu công cụ cần format mã, refactor, hiển thị tài liệu, giữ comment khi ghi lại tệp hoặc hỗ trợ IDE, cần lưu thông tin comment và vị trí nguồn.

### 5.1. Phân biệt comment với chuỗi ký tự

Lexer phải xử lý đúng ngữ cảnh chuỗi. Ví dụ:

~~~text
message = "Giá trị // này là văn bản, không phải comment"
url = "https://example.com/rules"
~~~

Nếu lexer tìm dấu // một cách đơn giản mà không biết nó đang ở trong string literal, nó có thể cắt mất phần còn lại của giá trị. Tương tự, dấu /* trong chuỗi không được mở comment khối.

Một lexer thường cần các trạng thái như normal, string, escape và block comment để phân biệt chính xác. Quy tắc escape cũng cần rõ ràng: dấu phân cách comment xuất hiện sau ký tự escape có được xem là dữ liệu hay không phụ thuộc cú pháp string của DSL.

### 5.2. Comment khối và comment lồng nhau

Với comment khối, ngôn ngữ cần quyết định có cho phép lồng nhau hay không. Nếu không hỗ trợ lồng, comment bên trong không thể mở một phạm vi comment mới. Nếu hỗ trợ, lexer cần đếm độ sâu hoặc dùng cơ chế tương đương.

Ví dụ cú pháp lồng:

~~~text
/*
  Giải thích bên ngoài
  /*
    Ghi chú bên trong
  */
  Phần giải thích tiếp tục
*/
~~~

Hỗ trợ comment lồng nhau có thể tiện khi tạm vô hiệu hóa một đoạn mã chứa comment khác, nhưng làm lexer phức tạp hơn. Một DSL nhỏ thường có thể chọn không hỗ trợ và ghi rõ quy tắc đó.

### 5.3. Vị trí nguồn và thông báo lỗi

Khi parser báo lỗi, vị trí dòng và cột cần được tính nhất quán dù trước đó có comment nhiều dòng. Nếu lexer bỏ comment, nó vẫn phải cập nhật offset và số dòng để thông báo lỗi trỏ đúng vị trí trong tệp gốc.

Với công cụ editor, có thể lưu span bắt đầu và kết thúc của comment. Span này hỗ trợ highlight, lựa chọn vùng văn bản và liên kết comment với node tương ứng.

## 6. Chú thích không thay thế cấu trúc của DSL

Comment chỉ là văn bản dành cho con người hoặc công cụ tài liệu hóa. Nếu một thông tin cần được parser, runtime hoặc hệ thống khác sử dụng để quyết định hành vi, thông tin đó thường nên được biểu diễn bằng cấu trúc dữ liệu hoặc cú pháp chính thức.

Ví dụ, thay vì ghi:

~~~text
# Retry tối đa 5 lần
call payment-service
~~~

nên biểu diễn giới hạn retry bằng cấu trúc có ý nghĩa:

~~~yaml
action:
  name: payment-service
  retry:
    maxAttempts: 5
~~~

Comment có thể giải thích lý do chọn năm lần thử, còn maxAttempts mới là dữ liệu mà runtime đọc để thực thi. Nếu chương trình cần tìm kiếm, kiểm tra, phân quyền hoặc báo cáo theo thông tin đó, không nên giấu thông tin trong comment tự do.

Một số DSL có directive hoặc annotation trông giống comment nhưng thực sự ảnh hưởng đến công cụ:

~~~text
@deprecated("Use calculateFeeV2")
function calculateFee(order) { ... }
~~~

Annotation là cú pháp có cấu trúc được parser nhận biết. Nó khác comment thông thường dù mục đích có thể là cung cấp metadata. Tương tự, một số hệ thống dùng comment đặc biệt làm chỉ thị cho compiler hoặc công cụ kiểm tra; khi đó cần tài liệu hóa chính xác vì chúng không còn là comment thuần túy.

## 7. Chú thích có cấu trúc và quy ước nhóm

Comment tự do dễ viết nhưng khó tìm kiếm và phân tích tự động. Một nhóm có thể đặt quy ước cho các nhãn thường gặp:

| Nhãn | Mục đích | Cách sử dụng |
|---|---|---|
| TODO | Công việc cần hoàn thành | Nêu việc còn thiếu và điều kiện để hoàn tất |
| FIXME | Vấn đề đã biết cần sửa | Mô tả lỗi và ảnh hưởng |
| NOTE | Thông tin cần lưu ý | Giải thích quyết định hoặc giới hạn |
| DEPRECATED | Cấu trúc không còn khuyến nghị | Chỉ rõ phương án thay thế |
| SECURITY | Lưu ý liên quan đến bảo mật | Nêu rủi ro và biện pháp kiểm soát |

Ví dụ:

~~~text
# TODO(TEAM-421): Bổ sung quy tắc cho đơn hàng hoàn tiền một phần.
# NOTE: Ngưỡng này lấy từ chính sách tín dụng đã được phê duyệt.
rule credit-review {
    when order.total > 50000000
    then require_manual_review()
}
~~~

Nếu công cụ tự động quét các nhãn này, quy ước cần ổn định và có định dạng nhất quán. Một TODO không có chủ sở hữu, liên kết issue hoặc điều kiện hoàn thành có thể tồn tại mãi mà không giúp ích cho việc bảo trì.

Không nên biến comment thành nơi lưu trạng thái vận hành duy nhất. Ví dụ, nhãn DONE trong comment có thể lỗi thời so với issue tracker hoặc trạng thái thực tế của hệ thống.

## 8. Chú thích trong tài liệu hóa DSL

Một DSL có thể cung cấp comment tài liệu để sinh reference tự động. Ví dụ:

~~~text
/**
 * Xác định khách hàng có đủ điều kiện nhận ưu đãi.
 *
 * @param customer khách hàng cần đánh giá
 * @return true nếu khách hàng đủ điều kiện
 * @since 2.0
 */
function isEligible(customer) {
    return customer.status == "ACTIVE"
}
~~~

Công cụ tài liệu hóa có thể trích xuất mô tả và tag để tạo trang tham chiếu. Để tài liệu có chất lượng, nên quy định:

- Thành phần nào cần comment tài liệu: module, public function, rule hoặc schema.
- Tag nào được hỗ trợ và ý nghĩa của chúng.
- Cách viết tham số, kiểu trả về, ví dụ và phiên bản.
- Cách liên kết tới thành phần khác.
- Cách xử lý tag không nhận biết hoặc tag bị lặp.
- Cách hiển thị tài liệu khi comment thiếu hoặc không hợp lệ.

Comment tài liệu nên mô tả hành vi công khai, bao gồm điều kiện, kết quả và lỗi có thể xuất hiện. Không nên chỉ sao chép tên hàm thành một câu mà không giải thích thêm.

## 9. Bảo toàn comment khi chỉnh sửa và định dạng

Một compiler có thể không cần comment sau khi phân tích, nhưng editor hoặc formatter lại cần chúng. Nếu công cụ đọc tệp, tạo AST rồi ghi lại chỉ từ AST, comment có thể bị mất vì AST thường không lưu trivia.

Để bảo toàn nội dung, công cụ có thể:

- Giữ văn bản nguồn và lưu vị trí comment.
- Gắn comment vào node trước hoặc node sau theo quy tắc rõ ràng.
- Lưu comment độc lập với AST nhưng duy trì source span.
- Dùng concrete syntax tree (CST) hoặc mô hình cú pháp giữ token và trivia.
- Định dạng lại văn bản nhưng giữ nội dung và thứ tự comment.

Ví dụ:

~~~text
# Quy tắc được yêu cầu trong ticket TEAM-421
rule refund-review {
    when refund.amount > 1000000
    then require_approval()
}
~~~

Nếu formatter xóa comment hoặc chuyển nó sang vị trí khác, liên kết với rule có thể bị mất. Vì vậy, công cụ cần định nghĩa comment đứng trước một node thuộc về node đó, hay chỉ là comment độc lập giữa các câu lệnh.

Khi thực hiện refactor, cần cân nhắc cả comment gắn với biểu thức bị di chuyển. Một comment nói về điều kiện của rule không nên vô tình ở lại phía trên rule khác sau khi sắp xếp lại mã.

## 10. Chất lượng và phong cách viết comment

Comment nên bổ sung thông tin mà mã nguồn khó thể hiện. Một số nguyên tắc hữu ích:

1. **Giải thích tại sao:** nêu lý do nghiệp vụ, ràng buộc kỹ thuật hoặc quyết định thiết kế.
2. **Viết gần nội dung liên quan:** đặt comment ở vị trí người đọc cần thông tin.
3. **Cập nhật cùng thay đổi:** khi sửa quy tắc, xem comment có còn đúng không.
4. **Tránh lặp lại cú pháp:** không viết comment chỉ để đọc lại tên trường hoặc phép so sánh.
5. **Nêu nguồn của con số đặc biệt:** ghi chính sách, ticket hoặc tài liệu làm căn cứ cho ngưỡng khó hiểu.
6. **Giữ comment ngắn và cụ thể:** chia đoạn dài thành phần giải thích có tiêu đề hoặc tài liệu riêng.
7. **Không ghi thông tin nhạy cảm:** tránh token, mật khẩu, dữ liệu cá nhân hoặc thông tin vận hành bí mật.

Ví dụ comment kém hữu ích:

~~~text
# Kiểm tra số tiền lớn hơn 10000000
when order.total > 10000000
~~~

Comment này lặp lại biểu thức. Có thể thay bằng:

~~~text
# Ngưỡng rà soát thủ công theo chính sách tín dụng doanh nghiệp.
when order.total > 10000000
~~~

Comment thứ hai cung cấp lý do và nguồn gốc nghiệp vụ. Nếu ngưỡng thay đổi, người bảo trì biết cần xem lại chính sách liên quan.

## 11. Bảo mật và giới hạn của comment

Comment vẫn nằm trong mã nguồn được lưu, review, đóng gói hoặc phân phối. Vì vậy, comment có thể bị đọc bởi người có quyền truy cập repository hoặc artifact. Không ghi mật khẩu, API key, token, khóa riêng, dữ liệu khách hàng hoặc chi tiết lỗ hổng chưa được công bố vào comment.

Comment cũng không phải cơ chế vô hiệu hóa an toàn. Ví dụ, comment một dòng mã kiểm tra quyền không bảo đảm các đường gọi khác cũng bị bảo vệ. Kiểm soát bảo mật cần được thực hiện bằng logic thực thi, chính sách và quyền ở đúng ranh giới.

Nếu một DSL cho phép comment đặc biệt làm directive, công cụ phải xác thực directive như dữ liệu đầu vào. Không nên thực thi nội dung comment tùy ý chỉ vì nó có tiền tố đặc biệt. Chỉ các tag được công bố, có schema và quyền rõ ràng mới nên được xử lý.

## 12. Thiết kế hỗ trợ comment trong một DSL mới

Khi thiết kế grammar và công cụ cho một DSL, cần quyết định trước:

1. Có hỗ trợ comment không và mục tiêu của comment là gì?
2. Dùng dấu phân cách nào cho comment cuối dòng và comment khối?
3. Comment có được phép xuất hiện trong biểu thức, giữa token hoặc sau giá trị không?
4. Ký hiệu comment trong chuỗi được xử lý ra sao?
5. Comment khối có được lồng nhau không?
6. Comment có bị loại bỏ khỏi AST hay được giữ như trivia?
7. Có kiểu comment tài liệu hoặc tag có cấu trúc không?
8. Formatter và editor phải bảo toàn comment như thế nào?
9. Comment có thể chứa directive ảnh hưởng compiler không?
10. Có quy ước lint cho TODO, FIXME hoặc comment lỗi thời không?

Ví dụ grammar giản lược cho comment cuối dòng:

~~~text
COMMENT      : '#' ~[\r\n]* -> channel(HIDDEN);
IDENTIFIER   : [a-zA-Z_] [a-zA-Z0-9_]*;
INTEGER      : [0-9]+;
NEWLINE      : '\r'? '\n';
WHITESPACE   : [ \t]+ -> skip;
~~~

Đây là đoạn grammar minh họa theo phong cách ANTLR. COMMENT được đưa sang hidden channel để parser không xem nó như thành phần cú pháp thông thường, nhưng công cụ vẫn có thể truy cập token nếu cần giữ comment. Nếu dùng skip, lexer bỏ token khỏi luồng parser; cách đó đơn giản hơn nhưng khó bảo toàn comment khi formatter ghi lại tệp.

Với comment khối, grammar cần định nghĩa rõ dấu mở và đóng, xử lý xuống dòng, trường hợp kết thúc tệp khi comment chưa đóng và chính sách lồng nhau. Lexer cũng cần ưu tiên nhận diện comment đúng ngữ cảnh để không nhầm với chuỗi.

## 13. Những lỗi thường gặp

### Dùng cú pháp comment của ngôn ngữ khác

Người viết có thể dùng // trong YAML hoặc dùng # trong CSS vì quen tay. Nếu grammar không hỗ trợ, nội dung có thể gây lỗi parse hoặc bị diễn giải thành dữ liệu. Hãy tuân thủ cú pháp của đúng DSL và công bố quy ước rõ ràng.

### Đặt comment bên trong chuỗi

Lexer đơn giản có thể nhận nhầm dấu comment trong URL hoặc nội dung văn bản. Cần xử lý trạng thái string và escape trước khi nhận diện comment.

### Nghĩ rằng JSON chuẩn cho phép comment

Một số editor hỗ trợ JSONC nhưng parser của dịch vụ vẫn có thể yêu cầu JSON chuẩn. Cần thống nhất dialect giữa công cụ soạn thảo, kiểm tra và runtime.

### Mất comment khi format hoặc serialize

AST không giữ trivia có thể làm mất comment khi ghi lại tệp. Nếu công cụ cần bảo toàn nội dung, hãy lưu source text, token hoặc CST phù hợp.

### Comment lỗi thời

Comment nói một điều, mã nguồn làm điều khác sẽ khiến người đọc mất niềm tin. Cần cập nhật hoặc xóa comment khi thay đổi logic và dùng test cho hành vi thực tế.

### Dùng comment để thay thế dữ liệu cấu hình

Thông tin mà runtime cần sử dụng phải nằm trong cú pháp hoặc schema chính thức. Comment tự do khó xác thực, tìm kiếm và bảo đảm nhất quán.

### Đưa bí mật vào comment

Comment thường được lưu trong Git và artifact lâu dài. Không dùng comment làm nơi ghi thông tin xác thực hoặc dữ liệu nhạy cảm.

## 14. Quy trình sử dụng comment hiệu quả

Trong một dự án DSL, có thể áp dụng quy trình đơn giản:

1. Viết comment khi cần giải thích lý do, giả định, ngoại lệ hoặc liên kết yêu cầu.
2. Đặt comment gần rule, biểu thức hoặc trường mà nó mô tả.
3. Dùng tag thống nhất cho công việc còn lại hoặc vấn đề đã biết.
4. Khi review thay đổi, xem cả comment và nội dung DSL.
5. Khi format hoặc refactor, kiểm tra comment có còn gắn đúng thành phần không.
6. Dùng lint hoặc công cụ quét để tìm TODO quá hạn và comment chứa directive không hợp lệ.
7. Không lưu bí mật hoặc dữ liệu nhạy cảm trong comment.

## 15. Kết luận

Chú thích là thành phần từ vựng giúp người viết DSL truyền đạt lý do, ngữ cảnh, ngoại lệ và thông tin bảo trì mà cú pháp thực thi không thể hiện đầy đủ. DSL có thể hỗ trợ comment cuối dòng, comment khối, comment tài liệu hoặc tag có cấu trúc, nhưng cú pháp và ngữ nghĩa phải được quy định rõ để lexer, parser, editor và formatter xử lý nhất quán.

Với công cụ chỉ thực thi, comment có thể được bỏ qua sau khi phân tích. Với công cụ cần chỉnh sửa, định dạng hoặc sinh tài liệu, comment và vị trí nguồn nên được bảo toàn dưới dạng trivia hoặc trong mô hình cú pháp phù hợp. Những thông tin ảnh hưởng đến hành vi cần được biểu diễn bằng cấu trúc DSL chính thức, không giấu trong comment tự do.

Hãy dùng comment để giải thích tại sao một quy tắc tồn tại, cập nhật nó cùng mã nguồn và giữ nội dung ngắn gọn, chính xác. Khi thiết kế một DSL mới, quy định từ đầu dấu phân cách, phạm vi, xử lý chuỗi, comment lồng nhau và cách bảo toàn comment sẽ giúp ngôn ngữ dễ đọc và công cụ hỗ trợ dễ phát triển hơn.
