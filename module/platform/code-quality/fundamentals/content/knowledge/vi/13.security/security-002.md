# Kiểm tra dữ liệu theo miền giá trị và ngữ cảnh sử dụng

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một dữ liệu **đúng kiểu** vẫn có thể không hợp lệ hoặc không an toàn đối với một thao tác cụ thể.
2. Phân biệt **kiểm tra cú pháp, miền giá trị, quy tắc nghiệp vụ và ngữ cảnh sử dụng**; xác định ranh giới tin cậy cần kiểm tra.
3. Thiết kế quá trình **diễn giải → chuẩn hóa có chủ đích → kiểm tra → sử dụng an toàn** mà không tự ý thay đổi ý nghĩa dữ liệu.
4. Phân biệt kiểm tra đầu vào với **truy vấn tham số hóa, mã hóa đầu ra theo ngữ cảnh và kiểm tra quyền**.
5. Viết và kiểm thử một bộ kiểm tra dữ liệu Java có điều kiện biên rõ ràng, đồng thời giải thích được các giới hạn của nó.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Bảo mật là một chiều chất lượng quan trọng: chương trình cần từ chối dữ liệu vi phạm hợp đồng, ngăn dữ liệu không đáng tin thay đổi ý nghĩa của lệnh và bảo vệ các hành động mà người gọi không được phép thực hiện.

Một sai lầm thường gặp là chỉ hỏi: **“Chuỗi này có hợp lệ không?”**. Câu hỏi chính xác hơn là: **“Giá trị này có hợp lệ cho trường dữ liệu, nghiệp vụ và vị trí sử dụng cụ thể hay không?”**. Cùng một chuỗi có thể phù hợp để hiển thị như lời nhắn, nhưng không phù hợp làm mã sản phẩm, đường dẫn tệp hoặc tên bảng SQL.

## 1. Vì sao kiểm tra theo ngữ cảnh?

Giả sử một API nhận ba trường:

~~~json
{
  "sku": "SP-001",
  "quantity": 2,
  "note": "Giao sau 18 giờ"
}
~~~

Cả **sku** và **note** đều là chuỗi, nhưng hợp đồng khác nhau:

- **sku** là mã sản phẩm: có thể chỉ cho phép chữ cái Latin không dấu, chữ số và dấu gạch nối, có giới hạn độ dài; phải tồn tại trong danh mục sản phẩm.
- **quantity** là số lượng đặt mua: phải là số nguyên trong khoảng cho phép, ví dụ từ 1 đến 100 cho một dòng hàng.
- **note** là lời nhắn tự do: có thể có tiếng Việt, dấu câu, ký hiệu toán học, thậm chí chứa các ký tự **<** và **>** với ý nghĩa văn bản. Nhưng khi đưa note vào trang HTML, ứng dụng phải xuất nó như **văn bản**, không để trình duyệt hiểu thành mã HTML.

Chỉ kiểm tra **quantity là int**, **sku là String** hay **note không null** chưa đủ. Ngược lại, cấm mọi ký tự đặc biệt trong note để “chống XSS” vừa gây mất dữ liệu hợp lệ, vừa không thay thế được biện pháp mã hóa khi render.

### Bốn tầng câu hỏi

| Tầng kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Kiểu và cấu trúc** | Dữ liệu có đọc được theo schema không? | quantity là số nguyên, các trường có đúng kiểu |
| **Miền giá trị** | Giá trị có thuộc tập được phép cho trường này không? | quantity từ 1–100, SKU theo định dạng đã công bố |
| **Nghiệp vụ và trạng thái** | Giá trị có hợp lệ với sản phẩm, tài khoản, thời điểm và trạng thái hiện tại không? | SKU tồn tại, còn được bán, số lượng không vượt giới hạn hiện hành |
| **Ngữ cảnh sử dụng** | Khi đưa giá trị tới database, HTML, URL, shell hoặc tệp, nó có được xử lý an toàn theo ngữ pháp của đích không? | SQL có tham số, HTML được escape theo ngữ cảnh, URL đích được hạn chế |

Một trường có thể vượt qua ba tầng đầu nhưng vẫn gây nguy hiểm nếu tầng cuối dùng sai cơ chế. Ví dụ, ghi chú khách hàng hoàn toàn hợp lệ nhưng được nối trực tiếp vào HTML không mã hóa có thể khiến trình duyệt diễn giải nó thành markup.

## 2. Miền giá trị không chỉ là độ dài và regex

**Miền giá trị (domain of values)** là tập giá trị có ý nghĩa theo hợp đồng. Nó có thể được xác định bằng kiểu dữ liệu, khoảng số, tập liệt kê, định dạng, quan hệ giữa nhiều trường hoặc dữ liệu tham chiếu.

| Dữ liệu | Kiểm tra có thể phù hợp | Điều cần làm rõ |
| --- | --- | --- |
| Số lượng hàng | Số nguyên dương, có giới hạn trên | Giới hạn theo dòng, theo đơn hay theo tồn kho? |
| Giá tiền | Không âm, đơn vị tiền, độ chính xác được phép, giới hạn hợp lý | Giá do server quyết định hay có thể do client gửi? |
| Mã sản phẩm | Tập ký tự, độ dài, quy tắc viết hoa/thường, tồn tại trong catalog | Mã có phân biệt chữ hoa/thường không? Có mã quốc tế không? |
| Ngày giao | Ngày hợp lệ và thuộc khoảng hỗ trợ | Ngày theo múi giờ nào? Có ngày nghỉ hoặc giờ cắt đơn không? |
| Trạng thái đơn | Một trong các trạng thái đã định nghĩa | Chuyển từ trạng thái hiện tại sang trạng thái mới có hợp lệ không? |
| Địa chỉ email | Cấu trúc và độ dài theo hợp đồng, lưu/so sánh nhất quán | Email xác minh quyền sở hữu thế nào? Có hỗ trợ quốc tế hóa không? |
| Lời nhắn | Độ dài và quy định điều khiển ký tự phù hợp | Có chấp nhận xuống dòng, emoji, dấu câu không? |
| Đường dẫn truy xuất tài liệu | ID tài liệu hoặc đường dẫn hợp lệ trong phạm vi được cấp quyền | Đường dẫn này có thoát thư mục được phép không? |
| URL phía server sẽ gọi | Scheme, host, cổng, đích mạng và chính sách redirect | Có nguy cơ truy cập dịch vụ nội bộ ngoài ý muốn không? |

Ví dụ, hai giá trị **0** và **-1** đều là số nguyên hợp lệ theo kiểu **int**, nhưng không hợp lệ nếu số lượng yêu cầu phải dương. **999999999** cũng là int nhưng có thể vượt năng lực xử lý của nghiệp vụ. Vì thế, cú pháp đúng chỉ là bước đầu.

### Độ dài cũng phải có đơn vị

Trong Java, **String.length()** đếm số **UTF-16 code unit**, không nhất thiết bằng số ký tự người dùng nhìn thấy. **String.codePointCount(...)** đếm code point Unicode, nhưng một ký tự hiển thị (grapheme cluster) có thể bao gồm nhiều code point.

Khi đặt giới hạn, cần biết nó nhằm bảo vệ điều gì:
- Giới hạn **byte** để bảo vệ giao thức, lưu trữ hoặc payload.
- Giới hạn **code unit/code point** theo hợp đồng của trường.
- Giới hạn **ký tự hiển thị** nếu cần gần với trải nghiệm nhập liệu.

Không tự suy luận rằng **100 ký tự** luôn có cùng kích thước byte, hay một ký tự nhìn thấy luôn tương ứng với một code point. Những quy tắc ảnh hưởng đến dữ liệu quốc tế hóa nên được làm rõ và kiểm thử bằng ví dụ thực.

## 3. Ranh giới tin cậy: dữ liệu từ đâu đến?

Dữ liệu không tự đáng tin chỉ vì nó đi qua một lớp Java hoặc nằm trong database. Nguồn và cách sử dụng mới quyết định mức tin cậy.

~~~mermaid
flowchart LR
    A[Client hoặc hệ thống ngoài] --> B[Parse và kiểm tra cấu trúc]
    B --> C[Chuẩn hóa theo hợp đồng]
    C --> D[Kiểm tra miền và nghiệp vụ]
    D --> E[Kiểm tra quyền và trạng thái]
    E --> F[Logic ứng dụng]
    F --> G[Database hoặc hệ thống ngoài]
    F --> H[HTML, JSON hoặc báo cáo]
    G --> I[Đọc lại dữ liệu khi cần]
    I --> D
~~~

Một số ranh giới đáng chú ý:

1. **HTTP request, message, file nhập:** dữ liệu do bên khác cung cấp phải được đọc theo schema và kiểm tra trước khi tạo tác dụng phụ.
2. **Database:** dữ liệu lưu từ phiên bản cũ, migration hoặc nguồn tích hợp có thể không đáp ứng bất biến hiện tại. Không mặc định xem mọi bản ghi database là hợp lệ tuyệt đối.
3. **Cache:** dữ liệu có thể cũ hoặc chứa định dạng từ phiên bản ứng dụng trước.
4. **Cấu hình và môi trường:** cấu hình sai có thể khiến ứng dụng gọi sai URL, dùng sai giới hạn hoặc hoạt động ngoài phạm vi mong đợi.
5. **Đầu ra tới hệ thống khác:** hợp đồng phía nhận có thể khác; cần kiểm tra hoặc ánh xạ theo ngữ nghĩa của đích.

Việc kiểm tra có thể diễn ra ở nhiều lớp với vai trò riêng:
- Tầng tiếp nhận từ chối **schema** và định dạng không hợp lệ.
- Mô hình miền bảo vệ các **bất biến** gần dữ liệu.
- Application service kiểm tra **ngữ cảnh, quyền và chuyển trạng thái** trước khi hành động.
- Adapter thực hiện **giao tiếp an toàn** với database, HTML renderer, URL client hoặc file system.

**Không tin cậy client để tự xác nhận những điều chỉ server biết**, chẳng hạn số dư tài khoản, quyền cập nhật đơn hàng hoặc giá chính thức tại thời điểm mua. Client có thể gửi một giá trị để tham khảo hoặc hiển thị, nhưng server phải áp dụng nguồn tin cậy và hợp đồng nghiệp vụ khi tạo giao dịch.

## 4. Diễn giải, chuẩn hóa và kiểm tra theo thứ tự rõ ràng

Một luồng xử lý đầu vào hợp lý thường gồm:

1. **Parse:** đọc JSON, form hoặc giao thức thành kiểu dữ liệu; từ chối dữ liệu sai cấu trúc, kích thước hoặc định dạng.
2. **Canonicalize/normalize khi hợp đồng cho phép:** tạo biểu diễn thống nhất để kiểm tra và lưu, chẳng hạn cắt khoảng trắng bao quanh một mã, chuẩn hóa chữ hoa cho một mã không phân biệt hoa/thường.
3. **Validate miền giá trị:** kiểm tra tập ký tự, độ dài, khoảng số, các bất biến liên trường.
4. **Validate ngữ cảnh nghiệp vụ và quyền:** kiểm tra sự tồn tại, trạng thái, chủ sở hữu, giới hạn theo người dùng hoặc chính sách hiện tại.
5. **Sử dụng ở đích an toàn:** dùng API xử lý tham số và mã hóa theo đúng ngữ pháp của đích.
6. **Phản hồi có kiểm soát:** trả lỗi rõ ràng, không để lộ bí mật hoặc chuỗi nội bộ nhạy cảm.

### Chuẩn hóa phải có mục đích

Giả sử mã SKU **không phân biệt chữ hoa/thường** theo quy định, **" sp-01 "** có thể được chuẩn hóa thành **"SP-01"**. Nhưng với mật khẩu, chữ ký số, mã dùng một lần hoặc định danh có phân biệt chữ hoa, tự ý trim hoặc đổi case có thể làm sai ý nghĩa.

**Không có một bước “sanitize chuỗi” áp dụng cho mọi trường.** Một số trường phải giữ nguyên dữ liệu, một số được chuẩn hóa theo quy định rõ ràng và một số cần loại bỏ ngay nếu không hợp lệ.

### Thận trọng với nhiều cách biểu diễn

Unicode có thể biểu diễn cùng ký tự nhìn thấy theo nhiều tổ hợp code point. URL và đường dẫn cũng có thể chứa ký tự được mã hóa, dấu phân cách hoặc các đoạn **..** có ý nghĩa riêng sau khi giải mã/chuẩn hóa.

Với dữ liệu mà sự tương đương biểu diễn ảnh hưởng quyền hoặc định danh, hãy xác định **biểu diễn chuẩn ở đúng tầng**, kiểm tra theo biểu diễn đó và tránh chuỗi xử lý “giải mã một lần để kiểm tra, giải mã lần nữa để sử dụng”. Hai thành phần diễn giải khác nhau có thể tạo lỗ hổng vượt kiểm tra.

Không phải mọi dữ liệu Unicode đều cần chuẩn hóa NFC/NFKC: **NFKC** còn có thể làm các ký tự tương thích trở thành cùng biểu diễn và thay đổi ý nghĩa mong muốn. Với mã, tên người, mật khẩu hoặc chữ ký, phải có hợp đồng riêng về chuẩn hóa.

## 5. Ví dụ Java: tạo đầu vào nghiệp vụ hợp lệ trước khi tính tiền

Giả sử API đặt hàng tiếp nhận **SKU**, **số lượng** và **lời nhắn**. Quy ước minh họa:

- SKU gồm chữ Latin ASCII, chữ số, dấu gạch nối hoặc gạch dưới; ký tự đầu phải là chữ hoặc số; tối đa 32 ký tự. Hệ thống quy định SKU không phân biệt hoa/thường và cho phép bỏ khoảng trắng bao quanh.
- Số lượng là số nguyên trong **1–100**.
- Lời nhắn không bắt buộc, tối đa **500 Unicode code point**, không cho phép ký tự điều khiển ISO trong ví dụ này. Dấu câu, ký tự tiếng Việt, dấu **<** và **>** không bị cấm chỉ vì có thể xuất hiện trong HTML.
- **Giá tiền không được lấy từ request làm nguồn sự thật**; ứng dụng tra bảng giá đáng tin cậy rồi mới tính.

Đây là những quy tắc **giả định để học**, không phải chuẩn chung cho mọi hệ thống thương mại điện tử.

### Mô hình request và miền dữ liệu

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public final class OrderInputValidation {
    private static final Pattern SKU =
            Pattern.compile("[A-Z0-9][A-Z0-9_-]{0,31}");
    private static final int MAX_QUANTITY = 100;
    private static final int MAX_NOTE_CODE_POINTS = 500;

    private OrderInputValidation() {}

    // Dữ liệu mới parse ở ranh giới HTTP, chưa được tin cậy.
    public record IncomingOrder(String sku, int quantity, String note) {}

    // Đối tượng nghiệp vụ bảo vệ bất biến khi được tạo trực tiếp.
    public record OrderCommand(String sku, int quantity, String note) {
        public OrderCommand {
            if (sku == null || !SKU.matcher(sku).matches()) {
                throw new IllegalArgumentException("invalid normalized SKU");
            }
            if (quantity < 1 || quantity > MAX_QUANTITY) {
                throw new IllegalArgumentException("invalid quantity");
            }
            if (note == null
                    || note.codePointCount(0, note.length())
                            > MAX_NOTE_CODE_POINTS
                    || note.codePoints()
                            .anyMatch(Character::isISOControl)) {
                throw new IllegalArgumentException("invalid note");
            }
        }
    }

    public static OrderCommand validate(IncomingOrder request) {
        if (request == null || request.sku() == null) {
            throw new IllegalArgumentException("missing order data");
        }

        // Chỉ chuẩn hóa SKU vì hợp đồng đã cho phép.
        String sku = request.sku()
                .strip()
                .toUpperCase(Locale.ROOT);

        // Lời nhắn được giữ nguyên ngữ nghĩa; null là không ghi chú.
        String note = request.note() == null ? "" : request.note();

        return new OrderCommand(sku, request.quantity(), note);
    }
}
~~~

**Điểm đáng chú ý:**

- **IncomingOrder** biểu diễn dữ liệu mới parse; **OrderCommand** chỉ biểu diễn dữ liệu đáp ứng hợp đồng.
- Constructor của **OrderCommand** bảo vệ bất biến, nên những đoạn mã tạo trực tiếp đối tượng cũng không dễ bỏ qua kiểm tra.
- **Pattern.matcher(...).matches()** kiểm tra **toàn bộ** SKU, không chỉ một đoạn con khớp regex.
- **Locale.ROOT** tránh việc chuyển chữ hoa phụ thuộc locale của máy; đây là lựa chọn phù hợp cho mã ASCII đã được định nghĩa là không phân biệt hoa/thường.
- Với **note**, code không cắt bớt ký tự **<** và **>**. Nếu hiển thị trong HTML, renderer phải xuất note như văn bản đã mã hóa theo ngữ cảnh.
- Quy tắc cấm **ISO control** ở note chỉ là chính sách minh họa. Một hệ thống muốn hỗ trợ xuống dòng/tab có thể cần chính sách khác và vẫn phải xử lý an toàn ở đầu ra.

**Giới hạn:** Trong Java, một số code point có tính chất điều khiển hoặc định hướng hiển thị không thuộc nhóm ISO control. Khi một mã định danh hoặc trường hiển thị có rủi ro giả mạo trực quan, cần bổ sung chính sách Unicode/format character theo đúng ngữ cảnh; không nên coi đoạn mã trên là giải pháp toàn diện chống mọi kiểu ký tự gây nhầm lẫn.

### Không lấy đơn giá do người mua gửi làm nguồn sự thật

Mã hợp lệ ở trên **chưa xác nhận SKU tồn tại hoặc khách có quyền mua sản phẩm**. Tầng ứng dụng phải kiểm tra theo trạng thái và nguồn dữ liệu hiện tại.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record PriceQuoteVnd(BigDecimal unitPrice) {
    PriceQuoteVnd {
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (unitPrice.signum() < 0
                || unitPrice.stripTrailingZeros().scale() > 0
                || unitPrice.compareTo(new BigDecimal("1000000000")) > 0) {
            throw new IllegalArgumentException("invalid VND unit price");
        }
    }
}

final class OrderPricing {
    static BigDecimal subtotal(
            OrderInputValidation.OrderCommand order,
            PriceQuoteVnd trustedQuote) {

        Objects.requireNonNull(order, "order");
        Objects.requireNonNull(trustedQuote, "trustedQuote");

        return trustedQuote.unitPrice()
                .multiply(BigDecimal.valueOf(order.quantity()));
    }
}
~~~

**PriceQuoteVnd** chỉ nên được tạo từ bảng giá hoặc dịch vụ đáng tin và phải chịu kiểm tra chất lượng dữ liệu. Trong hợp đồng ví dụ, tiền VND không có phần lẻ; dùng **BigDecimal** tránh nhiều sai số nhị phân của **double**. Quy tắc thực tế về giới hạn, thuế, làm tròn và hỗ trợ tiền tệ khác cần được xác định riêng.

Nếu client gửi **unitPrice = 1000** nhưng bảng giá server là **120000**, ứng dụng phải dùng giá mà hệ thống đã xác nhận theo chính sách. Việc dữ liệu là một số hợp lệ không chứng minh **client được phép quyết định số tiền thanh toán**.

## 6. Kiểm tra dữ liệu và biện pháp an toàn ở nơi sử dụng là hai việc khác nhau

Một chương trình có thể kiểm tra đầu vào rất chặt mà vẫn mắc lỗi **SQL injection**, **XSS** hoặc truy cập tài nguyên trái phép nếu đưa giá trị vào ngữ cảnh sai.

### 6.1. SQL: dùng câu truy vấn tham số hóa

Ví dụ dưới đây dùng **PreparedStatement**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

final class ProductRepository {
    static Optional<String> findName(
            Connection connection, String sku) throws SQLException {

        String sql = "SELECT product_name FROM products WHERE sku = ?";
        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, sku);
            try (ResultSet rows = statement.executeQuery()) {
                return rows.next()
                        ? Optional.of(rows.getString("product_name"))
                        : Optional.empty();
            }
        }
    }
}
~~~

Trong đó, dữ liệu **sku** được truyền dưới dạng **giá trị** tách khỏi cấu trúc SQL. Không nên nối chuỗi dữ liệu đầu vào thành một đoạn câu lệnh SQL.

**Ngay cả khi SKU đã được regex kiểm tra**, vẫn nên dùng truy vấn tham số hóa. Định dạng SKU có thể thay đổi, dữ liệu có thể đến từ đường xử lý khác, và truy vấn tham số hóa là cơ chế dành riêng cho ngữ cảnh SQL.

Cần lưu ý: tham số **?** thường dùng cho **giá trị**, không thay thế trực tiếp tên bảng, cột hoặc từ khóa SQL. Nếu một phần cấu trúc SQL cần chọn động, hãy chọn từ **danh sách định danh tin cậy đã được cho phép**, thay vì đưa tên bảng do client gửi thẳng vào SQL.

### 6.2. HTML: mã hóa đầu ra theo vị trí chèn

Giả sử ghi chú là:

~~~text
Giao cho người nhận <Tầng 2>
~~~

Đây có thể là lời nhắn hợp lệ. Nếu tạo HTML bằng cách nối:

~~~java
// SAI: ghép văn bản không đáng tin trực tiếp vào HTML.
String html = "<p>" + note + "</p>";
~~~

trình duyệt có thể diễn giải dấu **<** và **>** như markup. Cách phù hợp là dùng **template engine có auto-escaping** hoặc bộ mã hóa đầu ra đã được thiết kế cho **HTML text context**.

Không phải mọi vị trí trong HTML dùng chung một quy tắc mã hóa:
- Văn bản giữa thẻ HTML cần cơ chế mã hóa văn bản HTML.
- Giá trị thuộc tính HTML cần cách chèn và mã hóa phù hợp cho thuộc tính.
- URL trong thuộc tính còn phải có chính sách cho scheme và đích được phép.
- Đặt dữ liệu không tin cậy trực tiếp vào JavaScript, CSS hoặc nội dung script đòi hỏi xử lý đặc thù, thường nên tránh bằng API/template an toàn.
- Trong DOM, dùng **textContent** để đặt văn bản có ý nghĩa khác với **innerHTML**, vốn được trình duyệt phân tích như markup.

**Không viết hàm tự thay vài ký tự rồi coi là bảo vệ XSS cho mọi ngữ cảnh.** Hãy dùng API/framework có hợp đồng escape rõ ràng và ưu tiên tách dữ liệu khỏi mã.

### 6.3. URL: mã hóa tham số chưa đủ để bảo vệ đích truy cập

Khi chèn một giá trị vào **query parameter**, cần dùng cách tạo URL hoặc mã hóa thành phần URL phù hợp. Ví dụ, **URLEncoder** trong Java là công cụ dành cho định dạng **application/x-www-form-urlencoded**, không phải bộ mã hóa dùng chung cho toàn bộ URL hay đường dẫn.

Quan trọng hơn, nếu server nhận URL do client cung cấp rồi tự đi tải tài nguyên, chỉ kiểm tra URL có cú pháp hợp lệ hoặc có prefix **https://** là chưa đủ. Tình huống này có nguy cơ **SSRF**: ứng dụng có thể bị điều hướng tới địa chỉ mạng nội bộ hoặc dịch vụ không được phép.

Một chính sách fetch URL cần cân nhắc:
- Chỉ cho phép **scheme, host, cổng và mục đích** thực sự cần.
- Kiểm tra địa chỉ được phân giải và ngăn đích mạng không được phép; xét cả IPv4/IPv6 và sự thay đổi phân giải DNS.
- Xử lý redirect có kiểm soát; không để redirect vượt qua kiểm tra host.
- Giới hạn timeout, kích thước dữ liệu tải về và số lần chuyển hướng.
- Không gửi token hoặc header bí mật sang đích không đáng tin.

Đối với một API chỉ cần ID tài nguyên, giải pháp đơn giản và an toàn hơn thường là **nhận ID rồi để server tự chọn URL từ cấu hình tin cậy**, thay vì nhận URL tùy ý.

### 6.4. Đường dẫn tệp: tránh kiểm tra chuỗi một cách ngây thơ

Khi người dùng chọn tệp, việc cấm chuỗi **"../"** không đủ cho mọi hệ điều hành và dạng mã hóa. Nếu nghiệp vụ cho phép truy cập một tập tệp, nên ưu tiên **ID tệp do ứng dụng quản lý** và tra cứu trong phạm vi cấp quyền.

Khi buộc phải ghép đường dẫn, cần chuẩn hóa và kiểm tra đường dẫn nằm trong thư mục cho phép, cân nhắc symbolic link, thay đổi tệp giữa lúc kiểm tra và lúc mở (TOCTOU), quyền truy cập hệ điều hành và cách API mở tệp thật. Kiểm tra đường dẫn hợp lệ vẫn không thay cho **kiểm tra quyền của người dùng đối với tệp đó**.

### 6.5. Shell, biểu thức tìm kiếm và template

Một giá trị đầu vào có thể trở thành **tham số lệnh**, **biểu thức regex**, **cú pháp tìm kiếm** hoặc **template expression**. Quy tắc an toàn phụ thuộc vào vị trí đó:
- Nếu cần chạy tiến trình, dùng API truyền **danh sách tham số** thay vì ghép chuỗi thành lệnh shell; tránh gọi shell nếu không cần.
- Nếu dùng dữ liệu người dùng làm **chuỗi cần tìm trong regex**, cân nhắc **Pattern.quote(...)** hoặc giao diện truy vấn giới hạn, thay vì coi nó là regex tùy ý.
- Giới hạn kích thước và độ phức tạp khi chấp nhận biểu thức do người dùng điều khiển; một regex có backtracking quá mức có thể gây tiêu tốn CPU.
- Với template, phân biệt dữ liệu và biểu thức được thực thi; không diễn giải văn bản do người dùng gửi như mã template.

**Một bộ lọc “ký tự nguy hiểm” chung không thể bảo vệ tất cả những ngữ cảnh này.** Sử dụng các cơ chế an toàn tại **sink** mới là phần quan trọng.

## 7. Validation khác authorization và business invariants

Hãy xét một request:

~~~json
{
  "orderId": "O-2026-015",
  "newStatus": "CANCELLED"
}
~~~

Hai trường có thể đúng cấu trúc và đúng định dạng. Nhưng hệ thống vẫn cần kiểm tra:

- Người gọi có quyền hủy **đơn cụ thể này** không?
- Đơn hàng có tồn tại không?
- Trạng thái hiện tại có cho phép chuyển sang **CANCELLED** không?
- Đơn đã giao hoặc đã thanh toán có cần quy trình hoàn tiền riêng không?
- Có yêu cầu khác đang cập nhật cùng đơn không?

Những câu hỏi này **không thể giải quyết bằng regex**. Tầng ứng dụng/domain cần kiểm tra chủ sở hữu, quyền và bất biến ở thời điểm thực hiện hành động, với cơ chế đồng thời phù hợp.

### Đừng tin đối tượng đã kiểm tra từ nhiều thời điểm trước

Một lần kiểm tra tồn kho thành công tại thời điểm A không bảo đảm còn hàng khi ghi đơn tại thời điểm B. Giữa hai thao tác, giao dịch khác có thể đã trừ tồn kho.

Nếu tính đúng đắn cần bảo vệ trạng thái tại thời điểm cập nhật, có thể dùng **transaction, optimistic locking, thao tác cập nhật có điều kiện hoặc ràng buộc database** tùy kiến trúc. Việc validate ban đầu giúp phản hồi sớm nhưng không tự xử lý xung đột đồng thời.

### Kiểm tra quyền gắn với tài nguyên

ID người dùng hoặc ID đơn hàng có định dạng hợp lệ không chứng minh người gọi được xem/sửa tài nguyên tương ứng. Cần kiểm tra **người gọi, hành động và tài nguyên** trong cùng ngữ cảnh; đây là một ranh giới bảo mật riêng với kiểm tra dữ liệu.

## 8. Kích thước, số lượng và độ phức tạp đầu vào cũng phải được giới hạn

Dữ liệu có thể thỏa tất cả điều kiện định dạng nhưng vẫn gây quá tải nếu quá lớn hoặc bị lồng quá sâu.

Ví dụ:
- JSON chứa hàng triệu phần tử.
- Một chuỗi hợp lệ nhưng dài hàng chục megabyte.
- Danh sách ID được phép nhưng có số lượng không giới hạn.
- Bộ lọc tìm kiếm có biểu thức lồng nhiều tầng.
- File nén nhỏ nhưng mở rộng thành lượng dữ liệu rất lớn.
- Regex do người dùng cung cấp gây thời gian xử lý bất thường.
- Số nguyên không bị giới hạn rồi được dùng để cấp phát mảng hoặc lặp.

Cần giới hạn ở nhiều điểm theo nhu cầu:

| Ranh giới | Giới hạn có thể cần |
| --- | --- |
| HTTP / message | Kích thước body, số trường, số phần tử, độ sâu nesting |
| Parser | Thời gian, bộ nhớ và các tính năng parse được phép |
| Mô hình miền | Độ dài, khoảng số, số mục tối đa, quan hệ giữa trường |
| Database | Kích thước batch, số bản ghi mỗi request, giới hạn truy vấn |
| Gọi dịch vụ ngoài | Timeout, concurrency, response size, retry budget |
| File / archive | Kích thước tệp, tổng dung lượng giải nén, loại nội dung thực |
| Kết quả tìm kiếm | Pagination, giới hạn tổng lượng dữ liệu trả về |

Ví dụ, **quantity** giới hạn 1–100 bảo vệ quy tắc một dòng hàng. Nhưng request vẫn có thể chứa hàng triệu dòng nếu **số dòng** không được giới hạn. Các giới hạn cần phối hợp theo tổng ngân sách công việc mà hệ thống chấp nhận.

### Cẩn trọng với phép toán số

Khi parse dữ liệu vào **int** hoặc **long**, parser cần từ chối giá trị ngoài miền kiểu thay vì để tràn số hoặc âm thầm đổi sang số khác. Khi cộng nhân dùng kiểu nguyên, có thể cân nhắc **Math.addExact**/**Math.multiplyExact** để phát hiện tràn khi đúng với nghiệp vụ. Với số tiền, dùng mô hình có đơn vị và chính sách làm tròn rõ ràng.

Không phải dữ liệu “là số” nào cũng nên đọc vào **double**. Một mã đơn dài toàn chữ số là **định danh**, không nên tự chuyển thành số vì có thể mất số 0 đầu; tiền thập phân cần được mô hình hóa theo yêu cầu chính xác.

## 9. Viết thông báo lỗi rõ ràng và an toàn

Lỗi validation nên cho người gọi biết **trường nào không hợp lệ** và **cách sửa**, trong phạm vi không làm lộ thông tin nhạy cảm.

Ví dụ phản hồi giả định:

~~~json
{
  "code": "INVALID_QUANTITY",
  "field": "quantity",
  "message": "Số lượng phải từ 1 đến 100",
  "requestId": "req-abc123"
}
~~~

Một số nguyên tắc:

1. **Nhất quán schema lỗi** giữa các API cùng nhóm; client không phải đoán lỗi dựa trên chuỗi thông điệp.
2. **Không trả stack trace**, SQL, cấu hình nội bộ, bí mật hoặc toàn bộ request khi lỗi.
3. **Không phản chiếu đầu vào** chưa mã hóa vào trang HTML hoặc log công khai.
4. **Phân biệt lỗi đầu vào và lỗi nghiệp vụ/trạng thái** theo hợp đồng API; HTTP 400, 403, 404 hoặc 409 có ý nghĩa khác nhau tùy trường hợp.
5. **Cân nhắc nguy cơ lộ thông tin qua lỗi chi tiết**, ví dụ thông báo chính xác tài khoản/email nào tồn tại có thể tạo điều kiện dò tài khoản ở một số luồng xác thực.
6. **Không tự động sửa dữ liệu sai bằng giá trị mặc định** nếu nghiệp vụ chưa xác nhận; lỗi âm thầm thường khó điều tra hơn lỗi được báo rõ.

Đối với một bộ kiểm tra dùng nội bộ, exception có thể thích hợp. Ở biên HTTP, nên chuyển exception thành phản hồi **được kiểm soát** và có mã lỗi ổn định. Không nên gửi nguyên tên lớp exception hoặc thông tin môi trường cho người gọi.

## 10. Unit test: bảo vệ miền giá trị và các ranh giới

Từ ví dụ **OrderInputValidation**, có thể viết JUnit Jupiter (JUnit 5) để kiểm tra cả dữ liệu hợp lệ, điều kiện biên và dữ liệu bị từ chối.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderInputValidationTest {

    @Test
    void normalizesAllowedSkuAndPreservesFreeText() {
        var input = new OrderInputValidation.IncomingOrder(
                " sp-01 ", 2, "Giao cho <Tầng 2>");

        var command = OrderInputValidation.validate(input);

        assertEquals("SP-01", command.sku());
        assertEquals(2, command.quantity());
        assertEquals("Giao cho <Tầng 2>", command.note());
    }

    @Test
    void acceptsQuantityAtBothBoundaries() {
        assertEquals(
                1,
                OrderInputValidation.validate(
                        new OrderInputValidation.IncomingOrder(
                                "SKU-1", 1, null)).quantity());

        assertEquals(
                100,
                OrderInputValidation.validate(
                        new OrderInputValidation.IncomingOrder(
                                "SKU-1", 100, "")).quantity());
    }

    @Test
    void rejectsQuantityOutsideTheDomain() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderInputValidation.validate(
                        new OrderInputValidation.IncomingOrder(
                                "SKU-1", 0, "")));

        assertThrows(
                IllegalArgumentException.class,
                () -> OrderInputValidation.validate(
                        new OrderInputValidation.IncomingOrder(
                                "SKU-1", 101, "")));
    }

    @Test
    void rejectsSkuOutsideAsciiIdentifierContract() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderInputValidation.validate(
                        new OrderInputValidation.IncomingOrder(
                                "SẢN-PHẨM", 1, "")));
    }

    @Test
    void rejectsControlCharactersInNote() {
        assertThrows(
                IllegalArgumentException.class,
                () -> OrderInputValidation.validate(
                        new OrderInputValidation.IncomingOrder(
                                "SKU-1", 1, "\u0000")));
    }

    @Test
    void domainObjectCannotBypassInvariants() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderInputValidation.OrderCommand(
                        "SKU-1", -1, ""));
    }
}
~~~

Test có **note chứa dấu < và >** là có chủ đích: dữ liệu văn bản được phép đi qua bước kiểm tra nghiệp vụ. Test HTML renderer ở mức khác phải xác nhận nội dung ấy được **render an toàn** dưới dạng văn bản. Nếu ngay tại validator xóa hết dấu đặc biệt, test có thể làm mất dữ liệu hợp lệ mà vẫn không chứng minh việc render an toàn.

### Bảng trường hợp nên nghĩ tới

| Trường | Hợp lệ điển hình | Biên hợp lệ | Không hợp lệ | Tình huống ngữ cảnh |
| --- | --- | --- | --- | --- |
| SKU | **SP-01** | Dài đúng 32 ký tự | Rỗng, chứa ký tự ngoài tập cho phép, dài 33 | SKU đúng định dạng nhưng không tồn tại |
| Quantity | 2 | 1 và 100 | 0, -1, 101, số ngoài miền kiểu | Số lượng lớn hơn tồn kho hoặc hạn mức tài khoản |
| Note | Văn bản tiếng Việt | Đúng 500 code point | Vượt giới hạn, có control bị cấm | Được render trong HTML, JSON, PDF hoặc log |
| Giá từ catalog | 120.000 VND | 0 hoặc giới hạn tối đa nếu hợp đồng cho phép | Âm, phần lẻ trái quy tắc, vượt ngưỡng | Giá lịch sử, thuế, chiết khấu, quyền áp dụng |
| Ngày giao | Ngày hợp lệ | Ngày sớm nhất/muộn nhất hỗ trợ | Ngày không tồn tại | Ngày nghỉ, timezone, thời điểm cắt đơn |

Unit test xác nhận logic validation; cần **integration test** cho parser HTTP, độ dài payload, binding kiểu số, database, HTML template hoặc URL client vì những ranh giới này có cách diễn giải riêng.

## 11. Kiểm thử lỗi bảo mật không dừng ở “input bị từ chối”

Một test có thể chứng minh **SKU chứa dấu nháy** bị từ chối. Nhưng nếu dữ liệu cho phép dấu nháy ở trường khác, nó vẫn phải được dùng an toàn khi đi vào SQL. Chỉ test các chuỗi “nguy hiểm” rồi assert trả 400 không chứng minh hệ thống đã chống SQL injection ở mọi trường hợp.

Nên phân chia trách nhiệm kiểm chứng:

| Rủi ro | Test/kiểm tra phù hợp |
| --- | --- |
| Số lượng âm hoặc quá giới hạn | Unit test kiểm tra miền giá trị |
| SKU đúng cú pháp nhưng không tồn tại | Test ứng dụng với catalog stub và integration test với catalog thật |
| Mã đơn đúng định dạng nhưng thuộc người khác | Test phân quyền tại tầng ứng dụng/API |
| Dữ liệu tự do chứa HTML markup | Test render: xuất thành văn bản đã escape, không chạy như mã |
| Giá trị được đưa vào SQL | Kiểm tra adapter dùng tham số và integration test truy vấn |
| Server fetch URL do người dùng chọn | Test chính sách đích, phân giải, redirect và mạng bị chặn |
| Nhiều phần tử hoặc payload quá lớn | Test giới hạn tại gateway/parser/application; thử quá tải phù hợp |
| Hai request tranh quyền cập nhật trạng thái | Test đồng thời và ràng buộc transaction/database |
| Giá từ request khác giá server | Test bảo đảm lấy giá từ catalog tin cậy |
| Đầu vào sai có gây tác dụng phụ không | Kiểm tra không lưu đơn/không gửi thanh toán khi validation thất bại |

Kết luận cần tránh là “đã validate đủ nên mọi sink an toàn”. **Validation là điều kiện cần trong nhiều luồng, còn an toàn tại điểm sử dụng cần cơ chế chuyên biệt**.

## 12. Các lỗi thường gặp khi thiết kế validation

### 12.1. Chặn theo danh sách từ khóa thay vì định nghĩa dữ liệu hợp lệ

Ví dụ, một API nhận ID sản phẩm nhưng chỉ chặn dấu nháy, dấu chấm phẩy hoặc từ **SELECT**. Cách làm đó không diễn đạt được **ID sản phẩm hợp lệ** là gì và dễ bỏ sót biến thể khác.

Nếu ID có tập ký tự hữu hạn, **allowlist theo hợp đồng** thường dễ hiểu hơn. Nhưng không dùng một allowlist ASCII cứng cho mọi chuỗi; tên người và lời nhắn cần hỗ trợ ngôn ngữ thực của người dùng.

### 12.2. Dùng cùng regex cho mọi trường

Một regex “an toàn” chung có thể chấp nhận những thứ sai ngữ nghĩa (email dùng làm mã số lượng) và từ chối dữ liệu đúng (tên có dấu hoặc dấu câu). Hãy gắn validator với **kiểu miền và điểm sử dụng** cụ thể.

### 12.3. Cố sửa mọi đầu vào để nó trở nên hợp lệ

Tự động bỏ ký tự bất thường, cắt chuỗi hoặc thay số âm thành 0 có thể che giấu lỗi và tạo giao dịch không được người dùng dự định. Chỉ chuẩn hóa khi **hợp đồng cho phép**; với sai lệch thực sự, nên báo lỗi.

### 12.4. Kiểm tra một lần ở UI rồi tin server

Validation ở giao diện giúp phản hồi nhanh, nhưng client có thể gửi request trực tiếp, chạy phiên bản cũ hoặc bị chỉnh sửa. Server phải bảo vệ **hợp đồng và quyền** của mình.

### 12.5. Kiểm tra định dạng nhưng bỏ qua quyền sở hữu

Một ID hợp lệ vẫn có thể trỏ tới tài nguyên của người khác. Phải kiểm tra **caller + action + resource** theo chính sách, không chỉ nhìn chuỗi ID.

### 12.6. Giải mã/chuẩn hóa ở hai tầng khác nhau

Một tầng kiểm tra đường dẫn hoặc URL chưa chuẩn hóa; tầng tiếp theo giải mã thêm và hiểu thành đích khác. Cần thống nhất nơi tạo biểu diễn chuẩn và bảo đảm sử dụng cùng ngữ nghĩa đã được kiểm tra.

### 12.7. Cho phép dữ liệu lớn không giới hạn

Regex khớp một chuỗi dài hàng triệu ký tự vẫn có thể làm hệ thống tốn CPU/bộ nhớ. Cần thêm giới hạn **kích thước, số phần tử, độ sâu và chi phí xử lý** ở đúng ranh giới.

### 12.8. Coi chuỗi đã được làm sạch là an toàn cho mọi đích

Dữ liệu an toàn để lưu như văn bản trong database không tự an toàn để chèn vào HTML, URL, JavaScript hoặc shell. Chọn biện pháp bảo vệ **theo ngữ pháp tại sink**.

### 12.9. Chỉ kiểm tra ở constructor nhưng deserialize bỏ qua bất biến

Một số cơ chế framework/ORM có thể đi theo đường khởi tạo khác hoặc ánh xạ dữ liệu từ nguồn cũ. Không giả định rằng mọi giá trị trong hệ thống đều được tạo qua một constructor đã validate. Xác định ranh giới kiểm chứng và test con đường load/binding thật.

## 13. Tình huống thực hành: API tạo đơn và URL in hóa đơn

Một nhóm xây API đặt hàng nhận:

~~~json
{
  "sku": "SP-01",
  "quantity": 2,
  "unitPriceVnd": 1000,
  "note": "Giao cho <Tầng 2>",
  "invoiceUrl": "https://example.invalid/invoice"
}
~~~

Luồng hiện tại thực hiện:
1. Kiểm tra **quantity > 0** và **sku không rỗng**.
2. Lấy **unitPriceVnd** từ client để tính tổng.
3. Lưu note trong database rồi ghép note trực tiếp vào HTML của email xác nhận.
4. Server tự tải nội dung **invoiceUrl** theo URL client gửi.
5. Không kiểm tra người dùng có quyền đặt mua sản phẩm hoặc dùng khuyến mại hay không.

### Câu hỏi cần phân tích

1. Kiểm tra hiện tại đã đủ cho miền giá trị của SKU và quantity chưa?
2. Có nên dùng giá client gửi để tính giao dịch không? Nguồn dữ liệu nào có thẩm quyền?
3. Note có cần cấm dấu **<** và **>** để chống XSS không?
4. Rủi ro của **invoiceUrl** là gì, kể cả khi nó bắt đầu bằng **https://**?
5. Hệ thống cần kiểm tra quyền và trạng thái ở bước nào?
6. Bạn sẽ viết những test nào để xác nhận kết quả mà không làm phát sinh đơn hàng hay gửi email thật?

### Hướng phân tích

**SKU và quantity:** xác định tập ký tự/độ dài SKU, khoảng số lượng hợp lệ, tình huống SKU không tồn tại và quy định theo tồn kho. Kiểm tra khi tạo yêu cầu và bảo vệ bất biến ở tầng nghiệp vụ.

**Đơn giá:** server cần xác nhận giá theo bảng giá/chính sách đang có hiệu lực. Giá client gửi có thể chỉ phục vụ đối chiếu hoặc hiển thị, nếu sản phẩm cần, và không nên được coi là nguồn tin cậy cho tổng phải trả.

**Lời nhắn:** lưu văn bản theo hợp đồng, sau đó dùng HTML template có **output encoding** phù hợp để xuất thành văn bản an toàn. Việc xóa các dấu câu có thể phá nội dung hợp lệ mà vẫn không bảo vệ các vị trí chèn khác.

**URL:** cân nhắc bỏ hoàn toàn trường URL tự do; thay bằng **invoiceId** và cho server tự lấy hóa đơn từ nơi tin cậy. Nếu buộc phải fetch URL, chính sách SSRF cần kiểm soát scheme, host, địa chỉ đích, redirect và giới hạn tài nguyên.

**Quyền:** xác nhận người gọi, tài nguyên và hành động theo chính sách. Trước khi tạo tác dụng phụ phải kiểm tra các bất biến nghiệp vụ và điều kiện chuyển trạng thái; khi ghi dữ liệu đồng thời có thể cần ràng buộc transaction/locking.

**Kiểm thử:** unit test điều kiện biên; test với catalog giả xác nhận chỉ dùng giá server; test API kiểm tra quyền; test renderer xác nhận note được xuất thành văn bản; test HTTP client hạn chế đích; integration test database và các giới hạn parser. Không cần dùng một loại test duy nhất cho tất cả rủi ro.

## 14. Bài tập tự luyện

### Bài tập 1 — Chọn miền giá trị

Với các trường **couponCode**, **customerName**, **deliveryDate**, **quantity**, **note**, hãy đề xuất:
- Những ràng buộc có thể kiểm tra ngay khi parse.
- Những ràng buộc phụ thuộc trạng thái nghiệp vụ.
- Những chỗ cần xử lý theo ngữ cảnh đầu ra.

*Gợi ý:* Đừng áp một regex ASCII duy nhất cho coupon code, tên người và lời nhắn; định nghĩa tập giá trị theo hợp đồng của từng trường.

### Bài tập 2 — Sửa một bộ kiểm tra sai

Xem đoạn minh họa:

~~~java
String sanitize(String input) {
    return input.replace("'", "")
                .replace("<", "")
                .replace(">", "");
}
~~~

Một đồng nghiệp muốn gọi **sanitize(...)** cho mọi trường trước khi dùng trong SQL, HTML và URL.

Hãy giải thích:
1. Vì sao hàm trên làm mất dữ liệu hợp lệ?
2. Vì sao nó không thể thay cho truy vấn SQL tham số hóa?
3. Vì sao kết quả không tự an toàn cho mọi vị trí trong HTML?
4. Bạn sẽ thiết kế validation và cách sử dụng cho **SKU**, **note** và **URL** ra sao?

*Gợi ý:* Phải xác định miền giá trị riêng rồi áp dụng cơ chế an toàn theo **sink**. Không có “chuỗi sạch tuyệt đối” dùng được mọi nơi.

### Bài tập 3 — Kiểm tra ranh giới và số lượng

Một API nhận **List<Integer> quantities**. Mỗi phần tử từ 1–100, nhưng API không giới hạn số phần tử. Hãy nêu rủi ro và đề xuất test cho số phần tử **0, 1, N, N+1**, cùng các phần tử **0, 1, 100, 101** theo hợp đồng đã chọn.

*Gợi ý:* Giới hạn miền phần tử không thay thế giới hạn kích thước danh sách và tổng lượng công việc. Cần xác định N dựa trên năng lực và nghiệp vụ.

### Bài tập 4 — Chuẩn hóa có thể gây lỗi

Hệ thống A coi mã khách hàng **abC** và **ABC** là hai mã khác nhau. Hệ thống B tự chuyển mọi ID thành chữ hoa trước khi tra cứu.

Hãy phân tích sự cố có thể xảy ra, vì sao **Locale.ROOT** không giải quyết được sai hợp đồng này và cần kiểm tra gì ở bước tích hợp.

*Gợi ý:* Vấn đề nằm ở **ý nghĩa định danh có phân biệt hoa/thường**, không chỉ cách chọn locale. Chuẩn hóa chỉ đúng khi chính sách miền cho phép.

### Bài tập 5 — Validation và authorization

Một API **GET /orders/{id}** chỉ kiểm tra ID gồm chữ/số và tồn tại trong database. Khách A gửi ID của khách B và nhận được dữ liệu.

Hãy giải thích tại sao ID hợp lệ vẫn không an toàn và viết giả mã kiểm tra **người gọi có quyền đọc đơn tương ứng**. Nêu test cho yêu cầu hợp lệ, không tồn tại và thuộc người khác.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Một giá trị là **int** và đã parse được thì có hợp lệ để dùng làm quantity không?

*Trả lời:* Chưa. Còn cần khoảng số, số lượng tối đa theo nghiệp vụ và các điều kiện ngữ cảnh như tồn kho hoặc hạn mức.

**Câu 2.** Một lời nhắn có dấu **<** và **>** có mặc nhiên nguy hiểm và phải bị xóa không?

*Trả lời:* Không. Nếu đó là văn bản hợp lệ, giữ dữ liệu theo hợp đồng và mã hóa khi render vào HTML theo đúng ngữ cảnh.

**Câu 3.** Regex SKU có đủ để chống SQL injection không?

*Trả lời:* Không. SQL cần truy vấn tham số hóa ở vị trí sử dụng; validation SKU bảo vệ định dạng nghiệp vụ.

**Câu 4.** Server kiểm tra URL có scheme HTTPS thì đã an toàn để fetch chưa?

*Trả lời:* Chưa. Còn phải kiểm soát host, địa chỉ mạng đích, redirect, DNS, tài nguyên và quyền truy cập theo chính sách SSRF.

**Câu 5.** Dữ liệu đã đi qua validation ở frontend có cần kiểm tra tại server không?

*Trả lời:* Có. Server là ranh giới bảo vệ hành động và dữ liệu nghiệp vụ; client không phải nguồn tin cậy cho việc tuân thủ hợp đồng.

**Câu 6.** Vì sao kiểm tra quyền là vấn đề riêng với kiểm tra định dạng?

*Trả lời:* Một tài nguyên có ID đúng định dạng vẫn có thể thuộc người khác. Quyền phụ thuộc vào người gọi, hành động, tài nguyên và trạng thái.

**Câu 7.** Việc chuẩn hóa Unicode hay đổi chữ hoa luôn làm hệ thống an toàn hơn không?

*Trả lời:* Không. Nếu quy tắc định danh không cho phép thay đổi cách biểu diễn, chuẩn hóa có thể làm sai ý nghĩa hoặc gây va chạm giữa các giá trị. Cần hợp đồng cụ thể.

## Ghi nhớ

**Kiểm tra dữ liệu an toàn phải dựa trên miền giá trị và ngữ cảnh sử dụng**. Hãy định nghĩa tập giá trị hợp lệ cho từng trường, diễn giải và chuẩn hóa theo hợp đồng, bảo vệ bất biến nghiệp vụ và kiểm tra quyền tại ranh giới thích hợp. Khi đưa dữ liệu tới SQL, HTML, URL, shell hoặc file system, dùng **cơ chế an toàn dành riêng cho đích** thay vì một bộ lọc chuỗi chung. Cần kiểm thử cả giá trị biên, dữ liệu lỗi, kích thước đầu vào, quyền và các tác dụng phụ. Cách tiếp cận này giúp mã nguồn đáng tin cậy hơn, dễ điều tra lỗi và dễ thay đổi mà vẫn bảo vệ ý nghĩa dữ liệu của người dùng.
