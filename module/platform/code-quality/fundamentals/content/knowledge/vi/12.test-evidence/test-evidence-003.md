# Trường hợp bình thường, biên, lỗi và dữ liệu bất thường

Một bộ kiểm thử có thể có hàng trăm ca đều thành công mà vẫn bỏ sót lỗi quan trọng nhất: sai đúng tại ngưỡng, chấp nhận dữ liệu không hợp lệ, xử lý nhầm ký tự đặc biệt hoặc để lại trạng thái sai sau một ngoại lệ. Điều đó xảy ra khi ta chỉ kiểm tra **một vài ví dụ quen thuộc**, thay vì chủ động tìm những lớp tình huống khác nhau mà phần mềm phải xử lý.

Trong chương **Bằng chứng kiểm thử** của module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu cách kiểm thử cung cấp **bằng chứng có giới hạn nhưng có thể kiểm chứng** cho chất lượng mã nguồn: mã có đáng tin cậy, dễ hiểu và dễ thay đổi an toàn hay không. Bài này tập trung vào bốn nhóm ca kiểm thử bổ trợ nhau: **bình thường, biên, lỗi và dữ liệu bất thường**.

## 1. Kiểm thử là bằng chứng về điều gì?

Một **ca kiểm thử** (*test case*) không chỉ là một lời gọi hàm. Nó cần nêu đủ:

- **Điều kiện ban đầu:** dữ liệu, trạng thái, phụ thuộc, cấu hình hoặc môi trường trước khi chạy.
- **Hành động:** phương thức, API hoặc quy trình được thực hiện.
- **Kết quả mong đợi:** giá trị trả về, ngoại lệ, trạng thái, tác dụng phụ và những điều **không được xảy ra**.
- **Kết quả thực tế:** quan sát được khi chạy kiểm thử.
- **Tiêu chí đối chiếu:** quy tắc nào quyết định đạt hay không đạt.

Kết quả mong đợi còn được gọi là **test oracle**: nguồn để quyết định phần mềm có hành xử đúng hay không. Oracle nên dựa trên **yêu cầu nghiệp vụ, hợp đồng hoặc quy tắc độc lập**, thay vì đơn thuần sao chép công thức đang có trong phần mã được kiểm thử.

Ví dụ, nếu yêu cầu nói “đơn từ **500.000 VND trở lên** được miễn phí vận chuyển”, oracle cho đơn **500.000 VND** là phí vận chuyển **0 VND**. Nếu kiểm thử chỉ lặp lại biểu thức **subtotal > 500_000** của mã triển khai, cả mã và kiểm thử có thể cùng mắc lỗi ở dấu so sánh.

### 1.1. Vì sao kiểm thử không phải bằng chứng tuyệt đối?

Một ca kiểm thử đạt chứng minh rằng **với những tiền điều kiện và quan sát của ca đó**, hệ thống đáp ứng oracle. Nó không chứng minh mọi đầu vào, mọi lịch chạy đồng thời và mọi sự cố bên ngoài đều đúng.

Ví dụ, kiểm thử thành công với một bản ghi có thể chưa phát hiện lỗi khi:

- Tập dữ liệu có hàng triệu bản ghi.
- Hai người dùng cùng thay đổi một giá trị.
- Cơ sở dữ liệu trả lỗi sau khi bước đầu đã ghi.
- Một chuỗi chứa ký tự Unicode hoặc dấu xuống dòng.
- Yêu cầu chạy lại sau timeout, dẫn đến tác dụng phụ trùng.

Do đó, giá trị của bộ kiểm thử đến từ **phạm vi rủi ro được chọn**, **oracle đúng**, **khả năng tái lập** và **mức độ quan sát phù hợp**, không chỉ từ số lượng ca hoặc tỷ lệ chạy xanh.

## 2. Bốn nhóm ca kiểm thử

| Nhóm | Mục tiêu chính | Ví dụ | Câu hỏi khi kiểm thử |
| --- | --- | --- | --- |
| **Bình thường** (*normal*) | Chứng minh luồng hợp lệ điển hình hoạt động đúng | Mua 2 cuốn sách với giá xác định | Kết quả có đúng quy tắc phổ biến không? |
| **Biên** (*boundary*) | Tìm lỗi tại điểm chuyển giữa hai miền giá trị | Số lượng 1, 100; ngưỡng phí 500.000 | Các dấu **<**, **<=**, **>**, **>=** có chính xác không? |
| **Lỗi** (*error*) | Xác minh cách từ chối hoặc phục hồi khi điều kiện không hợp lệ hay thao tác thất bại | Số lượng 0; truy vấn DB thất bại | Ngoại lệ, trạng thái và tác dụng phụ có đúng hợp đồng không? |
| **Dữ liệu bất thường** (*unusual/anomalous data*) | Tìm giả định ngầm về dạng, cấu trúc, phân bố dữ liệu | Chuỗi chứa khoảng trắng, Unicode, ký tự điều khiển, tệp lớn hoặc bản ghi trùng | Hệ thống có xử lý nhất quán, an toàn và có chủ đích không? |

**Các nhóm không phải bốn hộp tách biệt.** Ví dụ, chuỗi rỗng vừa là một ca biên về độ dài, vừa có thể là dữ liệu lỗi. Một giá trị **Long.MAX_VALUE** vừa là giá trị biên của kiểu số, vừa có thể gây lỗi tràn số khi nhân. Hãy phân loại theo **mục đích kiểm tra** thay vì tranh luận một ca chỉ được thuộc một nhóm.

Một điểm quan trọng: **dữ liệu bất thường không đồng nghĩa dữ liệu sai**. Một tên người dùng có dấu tiếng Việt, dấu nháy hoặc độ dài khác thường có thể hoàn toàn hợp lệ. Hệ thống phải tuân theo hợp đồng, không từ chối chỉ vì dữ liệu ít gặp.

## 3. Thiết kế trường hợp bình thường

Ca bình thường xác nhận chức năng đáp ứng quy trình chính khi đầu vào và các phụ thuộc hợp lệ.

Ví dụ một hệ thống tính giá dòng hàng:

~~~text
Đầu vào: mã hàng BOOK-7
Số lượng: 2
Đơn giá: 90.000 VND
Kết quả: 180.000 VND
~~~

Ca này hữu ích vì kết quả dễ hiểu và đại diện cho thao tác người dùng thường thực hiện. Tuy nhiên, nếu chỉ có ca này, các lỗi sau vẫn có thể chưa lộ diện:

- Chương trình chỉ chấp nhận số lượng từ 2 trở lên, bỏ sót số lượng 1 hợp lệ.
- Chương trình vô tình cho phép số lượng 101 ngoài giới hạn.
- Mã hàng có dấu cách cuối bị âm thầm chấp nhận.
- Khi nhân số lớn, kết quả vượt giới hạn kiểu số.

Một nhóm ca bình thường tốt nên có **nhiều đại diện mang ý nghĩa**, chẳng hạn sản phẩm miễn phí có giá 0 nếu nghiệp vụ cho phép, đơn hàng với giá lớn thông thường, hoặc trường hợp mã hàng có dấu gạch nối hợp lệ.

Không cần tạo hàng trăm biến thể chỉ khác tên mã hàng mà không đi qua hành vi mới.

## 4. Thiết kế trường hợp biên

### 4.1. Phân hoạch tương đương

**Phân hoạch tương đương** (*equivalence partitioning*) chia miền đầu vào thành các nhóm mà ta kỳ vọng có hành vi xử lý giống nhau theo một quy tắc.

Giả sử số lượng hợp lệ từ **1 tới 100**, tính cả hai đầu:

| Lớp dữ liệu | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| Nhỏ hơn miền hợp lệ | -1 hoặc 0 | Từ chối |
| Thuộc miền hợp lệ | 2 hoặc 50 | Chấp nhận |
| Lớn hơn miền hợp lệ | 101 hoặc 1.000 | Từ chối |

Một ca đại diện trong mỗi lớp có thể cho thấy xử lý tổng quát. Tuy nhiên, lỗi rất hay xảy ra ở **điểm chuyển tiếp**, vì vậy cần thêm kiểm thử giá trị biên.

### 4.2. Phân tích giá trị biên

Với miền hợp lệ **1..100**, bộ giá trị thường có ích là:

~~~text
0 | 1 | 2 ... 99 | 100 | 101
    ^                 ^
    Biên dưới         Biên trên
~~~

| Giá trị | Mục đích |
| ---: | --- |
| 0 | Ngay dưới biên dưới; phải bị từ chối |
| 1 | Đúng biên dưới; phải được chấp nhận |
| 2 | Ngay trên biên dưới; phải được chấp nhận |
| 99 | Ngay dưới biên trên; phải được chấp nhận |
| 100 | Đúng biên trên; phải được chấp nhận |
| 101 | Ngay trên biên trên; phải bị từ chối |

Nếu quy tắc là **từ 500.000 VND trở lên miễn phí**, nên kiểm thử **499.999**, **500.000**, **500.001** với đơn vị VND nguyên. Nếu quy tắc về thời gian là “sau hạn” thay vì “từ lúc hết hạn”, cần kiểm tra thời điểm **trước, đúng bằng và sau** hạn theo độ chính xác của hệ thống.

**Đừng bỏ qua biên của kiểu dữ liệu.** Ví dụ, nếu lưu tổng tiền bằng **long**, phép nhân số lượng với đơn giá có thể tràn số. Giá trị bản thân hợp lệ chưa chắc làm phép tính có kết quả biểu diễn được.

### 4.3. Biên không chỉ là số

Các ranh giới khác đáng kiểm tra:

- **Độ dài chuỗi:** 0, 1, tối đa cho phép, tối đa + 1 ký tự.
- **Số phần tử:** danh sách rỗng, một phần tử, số lượng đúng giới hạn, vượt giới hạn.
- **Thời gian:** đúng giờ đóng đăng ký, trước/sau một mili giây, ngày nhuận nếu liên quan.
- **Quyền truy cập:** đúng thời điểm hết phiên, đúng ranh giới phân quyền.
- **Trạng thái:** bước ngay trước/sau khi đơn hàng chuyển từ **PENDING** sang **PAID**.
- **Tải hệ thống:** khi connection pool còn một kết nối hoặc đã dùng hết, nếu hợp đồng liên quan.

Không phải tất cả các giá trị trên đều cần một ca kiểm thử cho mọi hàm. Chỉ chọn những biên ảnh hưởng tới **quy tắc của đơn vị được kiểm thử**.

## 5. Kiểm thử trường hợp lỗi

Ca lỗi cần xác nhận không chỉ **có lỗi**, mà còn **lỗi được báo đúng chỗ và không để lại kết quả sai**.

Có thể phân biệt:

| Nhóm lỗi | Ví dụ | Bằng chứng cần thu được |
| --- | --- | --- |
| Đầu vào không hợp lệ | Số lượng âm, mã hàng rỗng | Từ chối với loại lỗi và thông tin phù hợp |
| Lỗi tính toán | Tràn số nguyên, phép chia không được phép | Không trả kết quả sai hoặc im lặng làm tròn ngoài hợp đồng |
| Lỗi phụ thuộc | DB không sẵn sàng, dịch vụ mạng timeout | Lỗi được truyền/ánh xạ đúng, không báo thành công sai |
| Lỗi giữa nhiều bước | Đã ghi một phần dữ liệu rồi bước sau thất bại | Giao dịch rollback hoặc trạng thái trung gian hợp lệ được ghi nhận |
| Lỗi khi thử lại | Mất phản hồi sau khi bên ngoài đã xử lý | Không tạo tác dụng phụ trùng nếu yêu cầu có idempotency |
| Lỗi dọn dẹp | Đóng kết nối/tệp thất bại | Tài nguyên được xử lý theo hợp đồng và lỗi gốc không bị che |

### 5.1. Kiểm tra ngoại lệ và trạng thái sau ngoại lệ

Giả sử một phương thức chuyển tiền ném **IllegalStateException** khi số dư không đủ. Kiểm thử chỉ có:

~~~java
assertThrows(IllegalStateException.class,
        () -> ledger.transfer(500_000L));
~~~

vẫn chưa đủ nếu mã đã trừ số dư nguồn **trước khi** ném ngoại lệ. Nên bổ sung:

~~~java
long sourceBefore = ledger.sourceBalance();
long targetBefore = ledger.targetBalance();

assertThrows(IllegalStateException.class,
        () -> ledger.transfer(500_000L));

assertEquals(sourceBefore, ledger.sourceBalance());
assertEquals(targetBefore, ledger.targetBalance());
~~~

**ledger** là đối tượng minh họa với API đã định nghĩa trong bối cảnh bài toán; hai đoạn trên không phải một lớp Java hoàn chỉnh. Nội dung quan trọng là **kiểm tra bất biến sau lỗi**, chứ không chỉ kiểm tra đường đi ném ngoại lệ.

### 5.2. Lỗi dự kiến khác lỗi ngoài dự kiến

Nếu người dùng nhập số lượng 0, đây là **lỗi xác thực** có thể dự đoán. Nếu kết nối DB thất bại khi lưu đơn, đây là **lỗi vận hành**. Hợp đồng API có thể ánh xạ chúng thành các trạng thái phản hồi khác nhau; không nên bắt mọi ngoại lệ và mặc định trả thành công.

Kiểm thử cần quyết định:

- Bên gọi nhận loại lỗi nào?
- Có thông điệp phù hợp nhưng không tiết lộ dữ liệu nhạy cảm không?
- Hệ thống đã ghi hoặc gửi gì trước lúc lỗi?
- Có thể retry không? Retry có cần idempotency key?
- Tài nguyên và trạng thái có được dọn dẹp nhất quán không?

## 6. Dữ liệu bất thường và giả định ngầm

Dữ liệu bất thường có thể vẫn **hợp lệ**, hoặc không hợp lệ tùy quy tắc được công bố. Mục đích kiểm thử là phát hiện giả định không được phát biểu rõ.

### 6.1. Chuỗi và Unicode

Ví dụ tên hiển thị người dùng có thể chứa:

- Ký tự có dấu: **Đặng**, **Nguyễn**.
- Khoảng trắng đầu/cuối hoặc nhiều khoảng trắng liên tiếp.
- Dấu nháy đơn, dấu nháy kép, dấu gạch nối.
- Emoji hoặc ký tự ngoài vùng Basic Multilingual Plane.
- Hai chuỗi nhìn giống nhau nhưng có dạng Unicode chuẩn hóa khác nhau.
- Chuỗi trống, chỉ có khoảng trắng hoặc quá dài.
- Dấu xuống dòng, tab và ký tự điều khiển.

Chính sách xử lý phụ thuộc **vai trò của trường**. Tên hiển thị có dấu tiếng Việt thường là dữ liệu hợp lệ; còn mã sản phẩm nội bộ có thể bị giới hạn theo một mẫu ASCII cụ thể. Không nên dùng cùng một quy tắc cho hai miền dữ liệu khác nhau.

Nếu hệ thống cần chuẩn hóa Unicode, hãy xác định dạng chuẩn hóa và kiểm thử tính nhất quán. Đừng tự ý biến một mã định danh thành chữ hoa hoặc xóa khoảng trắng nếu điều đó có thể thay đổi ý nghĩa của mã.

### 6.2. Dữ liệu tập hợp và tệp

| Dữ liệu bất thường | Rủi ro | Ví dụ kiểm thử |
| --- | --- | --- |
| Danh sách rỗng | Giả định luôn có phần tử đầu | Tính tổng của danh sách rỗng theo hợp đồng |
| Bản ghi trùng | Ghi lặp, đếm trùng | Hai dòng CSV có cùng định danh |
| Thiếu cột hoặc thừa cột | Dịch lệch ánh xạ | Tệp có tiêu đề khác thứ tự |
| Dấu xuống dòng khác nhau | Tách dòng sai | CRLF và LF |
| Dấu BOM đầu tệp | Tên cột đầu tiên không khớp | CSV UTF-8 có BOM |
| Giá trị cực lớn | Tràn số, hết bộ nhớ | Số lượng ở ranh giới kiểu hoặc tệp rất lớn |
| Giá trị đến sai thứ tự | Giả định đã sắp xếp | Sự kiện B đến trước sự kiện A |
| Mã định danh khác chữ hoa/thường | Ghép nhầm khóa | Hai mã chỉ khác chữ hoa |

Một số trường hợp nên kiểm thử ở **tầng parser hoặc tích hợp**, không phải nhồi tất cả vào kiểm thử của một hàm tính số học.

### 6.3. Dữ liệu thiếu khác dữ liệu giá trị 0

Ví dụ đơn giá **0 VND** có thể hợp lệ cho sản phẩm tặng kèm. Nhưng **không có trường đơn giá** trong yêu cầu chưa chắc tương đương với đơn giá 0.

Nếu DTO dùng kiểu **long** nguyên thủy, một số cơ chế ánh xạ có thể khiến giá trị thiếu bị thay bằng 0 tùy cấu hình. Khi hợp đồng cần phân biệt “thiếu” với “0”, hãy dùng kiểu đầu vào hoặc quy tắc validation thể hiện được sự khác biệt.

Tương tự, một chuỗi **null**, chuỗi rỗng và chuỗi toàn dấu cách không nhất thiết có cùng ý nghĩa. Kiểm thử phải phản ánh **hợp đồng của từng trường**, thay vì áp dụng một cách mặc định.

## 7. Ví dụ Java tự chứa: tính tổng dòng hàng

Xét một API thuần tính tổng tiền của một dòng hàng. Hợp đồng ví dụ:

1. **sku** là mã hàng gồm **1 tới 12 ký tự ASCII**; ký tự đầu là chữ in hoa **A–Z**, các ký tự sau thuộc **A–Z**, **0–9** hoặc dấu gạch nối **-**. Không tự động trim hoặc đổi chữ hoa/thường.
2. **quantity** nằm trong **1..100**, kể cả hai đầu.
3. **unitPriceVnd** là số nguyên **không âm**; giá 0 được chấp nhận.
4. **totalVnd** bằng **quantity × unitPriceVnd**; nếu vượt phạm vi **long**, API ném **ArithmeticException** thay vì trả kết quả tràn số.
5. Dữ liệu không hợp lệ theo ba điều kiện đầu khiến API ném **IllegalArgumentException**.
6. Không có I/O hoặc thay đổi trạng thái bên ngoài; cùng đầu vào tạo cùng kết quả hoặc cùng lỗi.

Đây là **hợp đồng minh họa**, không phải quy tắc bắt buộc cho mọi ứng dụng. Mã SKU có dấu hoặc chữ thường hoàn toàn có thể hợp lệ trong một hệ thống khác.

### 7.1. Cách triển khai

~~~java
public record LineQuote(
        String sku,
        int quantity,
        long unitPriceVnd,
        long totalVnd) {}
~~~

~~~java
import java.util.regex.Pattern;

public final class LinePricing {
    private static final Pattern SKU_PATTERN =
            Pattern.compile("[A-Z][A-Z0-9-]{0,11}");

    private LinePricing() {}

    public static LineQuote quote(
            String sku, int quantity, long unitPriceVnd) {
        if (sku == null || !SKU_PATTERN.matcher(sku).matches()) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException("Negative price");
        }

        long totalVnd = Math.multiplyExact(unitPriceVnd, quantity);
        return new LineQuote(sku, quantity, unitPriceVnd, totalVnd);
    }
}
~~~

Đoạn này dùng **record** có từ Java 16; hai khai báo **public** được trình bày riêng, tương ứng với hai tệp nguồn Java khi đưa vào dự án thật. Điều kiện trong **Pattern** yêu cầu chữ đầu **A–Z** và tối đa 11 ký tự tiếp theo, nên tổng độ dài nằm trong **1..12**. **Math.multiplyExact** bảo đảm phép nhân không âm thầm tràn số.

### 7.2. Bảng ca kiểm thử theo hợp đồng

| Nhóm | sku | quantity | unitPriceVnd | Kỳ vọng |
| --- | --- | ---: | ---: | --- |
| Bình thường | BOOK-7 | 2 | 90.000 | totalVnd = 180.000 |
| Bình thường | A9 | 5 | 20.000 | totalVnd = 100.000 |
| Biên dưới | A | 1 | 0 | totalVnd = 0 |
| Biên trên số lượng | A12345678901 | 100 | 9.000 | totalVnd = 900.000 |
| Biên kiểu số | B | 1 | Long.MAX_VALUE | totalVnd = Long.MAX_VALUE |
| Lỗi số lượng | BOOK-7 | 0 | 90.000 | IllegalArgumentException |
| Lỗi số lượng | BOOK-7 | 101 | 90.000 | IllegalArgumentException |
| Lỗi đơn giá | BOOK-7 | 2 | -1 | IllegalArgumentException |
| Lỗi tràn số | B | 2 | Long.MAX_VALUE | ArithmeticException |
| Dữ liệu bất thường | book-7 | 2 | 90.000 | Invalid SKU vì chữ thường |
| Dữ liệu bất thường | BOOK-7 và dấu cách cuối | 2 | 90.000 | Invalid SKU; không tự trim |
| Dữ liệu bất thường | SÁCH-1 | 2 | 90.000 | Invalid SKU theo mẫu ASCII của ví dụ |
| Dữ liệu bất thường | null hoặc chuỗi rỗng | 2 | 90.000 | Invalid SKU |

**Oracle được xác định từ hợp đồng trước khi xem mã.** Ví dụ, số lượng 100 là hợp lệ bởi quy tắc “1..100”; số lượng 101 bị từ chối. Nếu mã kiểm tra **quantity >= 100** và từ chối cả 100, ca biên sẽ phát hiện lỗi đó.

### 7.3. Kiểm thử JUnit 5 cho ca hợp lệ

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class LinePricingValidTest {
    static Stream<Arguments> validLines() {
        return Stream.of(
                arguments("BOOK-7", 2, 90_000L, 180_000L),
                arguments("A9", 5, 20_000L, 100_000L),
                arguments("A", 1, 0L, 0L),
                arguments("A12345678901", 100, 9_000L, 900_000L),
                arguments("B", 1, Long.MAX_VALUE, Long.MAX_VALUE));
    }

    @ParameterizedTest
    @MethodSource("validLines")
    void quotesNormalAndBoundaryValues(
            String sku, int quantity,
            long unitPriceVnd, long expectedTotalVnd) {
        LineQuote result =
                LinePricing.quote(sku, quantity, unitPriceVnd);

        assertEquals(sku, result.sku());
        assertEquals(quantity, result.quantity());
        assertEquals(unitPriceVnd, result.unitPriceVnd());
        assertEquals(expectedTotalVnd, result.totalVnd());
    }
}
~~~

Các con số **expectedTotalVnd** được ghi trực tiếp từ bảng oracle. Không gọi lại **Math.multiplyExact** trong phần expected, nhằm tránh việc kiểm thử vô tình sao chép đúng cùng lỗi tính toán của triển khai nếu công thức sau này trở nên phức tạp hơn.

### 7.4. Kiểm thử JUnit 5 cho ca lỗi và dữ liệu bất thường

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class LinePricingInvalidTest {
    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 101, 1_000})
    void rejectsQuantityOutsideOneToHundred(int quantity) {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> LinePricing.quote("BOOK-7", quantity, 90_000L));
        assertEquals("Invalid quantity", error.getMessage());
    }

    @Test
    void rejectsNegativePrice() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> LinePricing.quote("BOOK-7", 2, -1L));
        assertEquals("Negative price", error.getMessage());
    }

    @Test
    void rejectsArithmeticOverflow() {
        assertThrows(ArithmeticException.class,
                () -> LinePricing.quote("B", 2, Long.MAX_VALUE));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {
        "book-7",
        "BOOK-7 ",
        "A B",
        "SÁCH-1",
        "A123456789012",
        "A\nB"
    })
    void rejectsUnexpectedSkuFormats(String sku) {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> LinePricing.quote(sku, 2, 90_000L));
        assertEquals("Invalid SKU", error.getMessage());
    }
}
~~~

Trong các chú thích Java, chuỗi nguồn **"A\nB"** biểu thị mã chứa **ký tự xuống dòng**, không phải hai mã riêng. Trong dự án thật, cần có dependency **JUnit Jupiter Params** cho các annotation chạy tham số.

Kiểm thử ở đây xác minh **cả loại ngoại lệ và thông điệp của các lỗi xác thực** vì hợp đồng ví dụ quy định các thông điệp đó. Nếu thông điệp không phải một phần hợp đồng công khai, nên ưu tiên loại lỗi hoặc mã lỗi ổn định, tránh làm kiểm thử giòn vì chỉ đổi câu chữ.

### 7.5. Kiểm thử nào chưa được ví dụ này bao phủ?

Đây là một phép tính thuần, nên chưa cần mô phỏng cơ sở dữ liệu hoặc mạng. Nhưng nếu hàm được gọi từ API đặt hàng, cần thêm kiểm thử ở ranh giới:

- JSON thiếu **quantity** có bị ánh xạ thành giá trị không mong muốn không?
- Hai đơn hàng có cùng mã yêu cầu có bị ghi hoặc tính phí trùng khi retry không?
- Khi **quote** từ chối dữ liệu, cổng thanh toán có chắc chắn **chưa được gọi** không?
- Với danh sách nhiều dòng, nếu một dòng sai thì cả đơn bị từ chối hay chỉ dòng đó bị bỏ qua theo hợp đồng?
- Khi dữ liệu từ tệp có BOM hoặc dấu xuống dòng khác nhau, parser có chuyển đúng thành các trường đầu vào không?

Những kiểm thử này thuộc API, parser hoặc lớp điều phối, vì chúng phụ thuộc cách hệ thống kết hợp các thành phần chứ không chỉ vào **LinePricing**.

## 8. Chọn ca kiểm thử theo rủi ro, không theo số lượng

Không phải mọi tổ hợp đều cần một ca độc lập. Nếu đầu vào có 20 trường, thử mọi giá trị của mọi trường có thể tạo không gian tổ hợp khổng lồ. Cần ưu tiên theo:

1. **Mức độ nghiêm trọng:** lỗi có thể làm mất tiền, rò rỉ dữ liệu hoặc sai quyền không?
2. **Khả năng xuất hiện:** người dùng có thường gặp tình huống đó không?
3. **Độ phức tạp của quy tắc:** có nhiều nhánh, ngưỡng, trạng thái và phụ thuộc không?
4. **Lịch sử lỗi:** phần nào từng gây sự cố hoặc sửa đi sửa lại?
5. **Ranh giới tích hợp:** dữ liệu đi qua những hệ thống có giả định định dạng khác nhau không?
6. **Khả năng quan sát:** nếu sai, hệ thống có phát hiện nhanh hay lỗi âm thầm tồn tại lâu?

Ví dụ, với một API thanh toán, kiểm thử retry sau timeout có thể quan trọng hơn việc thử 100 mã đơn hàng chỉ khác chữ số cuối. Với bộ parser CSV, dữ liệu có dấu nháy, dấu phẩy và xuống dòng trong trường có thể quan trọng hơn việc thay đổi vài giá trị số thông thường.

### 8.1. Bảng lựa chọn ca kiểm thử theo điều kiện

| Điều kiện có trong hợp đồng | Nên thử ít nhất |
| --- | --- |
| Có ngưỡng so sánh | Dưới, bằng, trên ngưỡng |
| Có miền giá trị hợp lệ | Ngay ngoài và ngay trong hai biên |
| Có trường bắt buộc | Thiếu, null, rỗng hoặc chỉ khoảng trắng tùy kiểu |
| Có dữ liệu Unicode | Đại diện hợp lệ và dạng không được phép theo quy tắc |
| Có phép tính số học | 0 nếu hợp lệ, giá trị lớn, tràn số, làm tròn |
| Có tập hợp | Rỗng, một phần tử, phần tử trùng, nhiều phần tử |
| Có trạng thái | Chuyển hợp lệ và chuyển bị cấm |
| Có I/O hoặc giao dịch | Thành công, lỗi trước và sau bước ghi, phục hồi |
| Có timeout/retry | Kết quả chưa rõ, thử lại, tác dụng phụ có thể trùng |
| Có truy cập đồng thời | Hai thao tác cạnh tranh cùng dữ liệu |

Bảng là **danh sách gợi ý xuất phát từ rủi ro**, không phải lời yêu cầu bắt buộc đưa mọi loại dữ liệu vào mọi bộ kiểm thử.

## 9. Kết hợp các cấp độ kiểm thử

Một rủi ro có thể cần nhiều cấp độ bằng chứng.

| Cấp độ | Kiểm thử phù hợp | Giới hạn |
| --- | --- | --- |
| **Unit test** | Hàm tính giá, validation, chuyển trạng thái trong bộ nhớ | Không chứng minh DB/network hoạt động đúng |
| **Component test** | Parser nhận dữ liệu lạ, repository với DB kiểm thử | Chưa chứng minh toàn bộ quy trình chạy thật |
| **Integration test** | Ghi DB, rollback, đồng bộ API, hàng đợi | Tốn thời gian và cần quản lý môi trường |
| **End-to-end test** | Người dùng thực hiện quy trình và quan sát kết quả | Khó tách nguyên nhân, thường chậm hơn |
| **Load/soak test** | Tải lớn, rò rỉ tài nguyên, độ trễ p95/p99 | Không thay thế kiểm thử đúng sai của từng giá trị |

Ví dụ:

- Unit test phát hiện dấu **>** thay vì **>=** tại ngưỡng.
- Integration test phát hiện DTO có trường thiếu bị biến thành giá trị mặc định sai.
- Kiểm thử đồng thời phát hiện hai yêu cầu cùng cập nhật một bản ghi theo dữ liệu cũ.
- Kiểm thử tải dài phát hiện kết nối chưa được trả về pool sau nhiều đường lỗi.

Không nên ép một unit test phải chứng minh những đặc tính chỉ quan sát được qua hệ thống tích hợp.

## 10. Bằng chứng kiểm thử phải đáng tin cậy

### 10.1. Tính tái lập

Một kiểm thử tốt nên kiểm soát dữ liệu, thời gian, ngẫu nhiên và phụ thuộc khi có thể.

Ví dụ, kiểm thử “đúng thời điểm hết hạn” không nên trực tiếp dựa vào **LocalDateTime.now()** rồi hy vọng luồng chạy đúng vào giây cần thiết. Có thể truyền **Clock.fixed(...)** hoặc một thời điểm cụ thể vào chính sách.

Với kiểm thử đồng thời, nên dùng **CountDownLatch** hoặc công cụ điều phối phù hợp để tạo tình huống tranh chấp thay vì chỉ ngủ một thời gian tùy ý. Tuy vậy, chạy xanh một lần không chứng minh mọi lịch chạy đồng thời đều an toàn.

### 10.2. Oracle độc lập và đủ mạnh

Một assertion yếu:

~~~java
assertNotNull(LinePricing.quote("BOOK-7", 2, 90_000L));
~~~

Kiểm thử này sẽ xanh dù phép tính trả tổng sai. Assertion mạnh hơn kiểm tra **180.000 VND**, các trường kết quả liên quan, và những điều kiện được hợp đồng yêu cầu.

Với luồng có tác dụng phụ, oracle có thể cần kiểm tra **không gửi email**, **không thu tiền** hoặc **không ghi DB** khi đầu vào bị từ chối. Chỉ kiểm tra HTTP 400 mà không xác minh trạng thái sau lỗi có thể bỏ sót hành vi nguy hiểm.

### 10.3. Đo độ bao phủ nhưng không đồng nhất với chất lượng

**Code coverage** cho biết phần mã nào đã được thực thi trong kiểm thử theo chỉ số được chọn (dòng, nhánh...). Nó **không cho biết assertion có đúng hay mạnh không**. Một nhánh được chạy nhưng không được kiểm tra kết quả vẫn có thể chứa lỗi.

**Mutation testing** đưa ra những biến đổi có chủ đích, ví dụ đổi **quantity > 100** thành **quantity >= 100**, để xem bộ kiểm thử có phát hiện sai khác không. Nếu ca số lượng đúng **100** tồn tại và oracle đúng, thay đổi này nên khiến kiểm thử thất bại.

Mutation testing hữu ích để đánh giá khả năng phát hiện lỗi của assertion, nhưng cũng có giới hạn: một số mutation tương đương về hành vi, hoặc không phù hợp với rủi ro nghiệp vụ quan tâm. Không nên dùng một tỷ lệ duy nhất làm thước đo đầy đủ cho chất lượng phần mềm.

### 10.4. Phân biệt kiểm thử ổn định với kiểm thử may rủi

Kiểm thử *flaky* là kiểm thử có thể xanh hoặc đỏ mà không có thay đổi có ý nghĩa trong mã. Một số nguyên nhân:

- Phụ thuộc thời gian thực hoặc múi giờ máy chạy.
- Phụ thuộc thứ tự thực thi của các test.
- Dùng dữ liệu chung không được dọn sạch.
- Cạnh tranh giữa các tác vụ bất đồng bộ.
- Kết nối tới dịch vụ bên ngoài không ổn định.
- Chờ bằng thời gian ngủ quá ngắn hoặc môi trường chạy quá tải.

Một kết quả đỏ không ổn định làm giảm giá trị bằng chứng, vì nhóm phát triển khó phân biệt lỗi thật với nhiễu. Cần sửa nguyên nhân và ghi rõ môi trường, thay vì mặc định chạy lại cho đến khi xanh.

## 11. Tài liệu hóa kết quả và khả năng truy vết

Khi một bộ kiểm thử được dùng làm bằng chứng trong review, CI hoặc nghiệm thu, người đọc cần biết:

- **Yêu cầu/hợp đồng** nào được kiểm tra.
- **Nhóm rủi ro** nào được ca kiểm thử đại diện.
- **Đầu vào, môi trường và dữ liệu nền** đã dùng.
- **Kết quả mong đợi** được xác định từ đâu.
- **Kết quả thực tế** và điều kiện đạt/trượt.
- **Giới hạn còn lại**: loại lỗi nào chưa được kiểm thử, vì sao chưa thể kết luận toàn diện.

Ví dụ mẫu bảng bằng chứng (dữ liệu **minh họa**, không phải kết quả chạy thực tế):

| Mã ca | Yêu cầu | Đầu vào trọng yếu | Oracle | Kết quả |
| --- | --- | --- | --- | --- |
| LN-N01 | Tổng giá dòng | BOOK-7, 2, 90.000 | 180.000 | Chưa chạy |
| LN-B01 | quantity = 100 hợp lệ | A, 100, 9.000 | 900.000 | Chưa chạy |
| LN-B02 | quantity = 101 sai | A, 101, 9.000 | Invalid quantity | Chưa chạy |
| LN-E01 | Không tràn số | B, 2, Long.MAX_VALUE | ArithmeticException | Chưa chạy |
| LN-U01 | Không tự trim SKU | BOOK-7 kèm khoảng trắng cuối | Invalid SKU | Chưa chạy |

Trong thực tế, cột **Kết quả** phải được điền từ lần chạy kiểm thử có thông tin phiên bản mã, môi trường và log thích hợp. Không được biến bảng thiết kế ca kiểm thử thành tuyên bố “đã đạt” nếu chưa thực sự chạy.

### 11.1. Khi yêu cầu thay đổi

Nếu chính sách đổi thành “quantity từ **1 tới 120**”, cần:

1. Cập nhật hợp đồng và các ví dụ người dùng.
2. Cập nhật ca biên cho **119, 120, 121** (và giữ kiểm tra biên dưới).
3. Sửa mã triển khai theo hợp đồng mới.
4. Kiểm tra hồi quy các quy tắc không đổi như giá 0, sku và tràn số.
5. Chạy lại bộ kiểm thử liên quan để có bằng chứng cho phiên bản mới.

Điểm cốt lõi là **bộ kiểm thử được suy ra từ hợp đồng**, không phải cố định như một bộ dữ liệu bất biến dù nghiệp vụ đã đổi.

## 12. Những hiểu nhầm thường gặp

**“Có ca happy path là đã kiểm thử chức năng.”** Nó chỉ xác nhận một vài giá trị điển hình; sai ở ngưỡng, đầu vào thiếu hoặc lỗi giữa bước vẫn có thể tồn tại.

**“Dữ liệu bất thường phải bị từ chối.”** Một tên có dấu tiếng Việt hoặc emoji có thể hợp lệ. Cần đánh giá theo hợp đồng của trường dữ liệu, không theo mức độ quen thuộc.

**“Bắt được ngoại lệ là đủ.”** Cần xem dữ liệu và tác dụng phụ sau ngoại lệ. Mã ném lỗi nhưng đã sửa trạng thái trước đó vẫn có thể không đúng.

**“Mọi giá trị biên đều là 0 và số âm.”** Biên có thể là độ dài, thời điểm, kích thước tập hợp, số kết nối, ngưỡng quyền hoặc trạng thái.

**“Coverage cao đồng nghĩa ít lỗi.”** Coverage chỉ phản ánh mã đã được chạy; assertion và oracle có thể yếu hoặc sai.

**“Kiểm thử xanh chứng minh không có lỗi.”** Nó chỉ cung cấp bằng chứng trong điều kiện và phạm vi đã kiểm thử. Rủi ro chưa kiểm tra vẫn tồn tại.

**“Chỉ cần tăng số lượng test.”** Nhiều test lặp lại một lớp dữ liệu có thể kém giá trị hơn vài test chủ đích bao phủ ranh giới quan trọng.

**“Một test bất ổn không đáng quan tâm.”** Flaky test có thể che lỗi thật, làm nhóm bỏ qua cảnh báo. Tính tái lập là một phần của chất lượng bằng chứng.

## 13. Tình huống thực hành

Một API đăng ký hội thảo nhận:

~~~text
name: tên người tham dự, được phép dùng Unicode
age: tuổi từ 16 đến 100 (bao gồm cả hai đầu)
email: bắt buộc, phải có định dạng theo quy tắc ứng dụng
sessionId: mã phiên phải tồn tại và còn chỗ
~~~

Khi đăng ký thành công, hệ thống ghi một bản đăng ký và gửi thông báo xác nhận. Khi đầu vào không hợp lệ, không được ghi đăng ký hoặc gửi thông báo. Khi phiên đã hết chỗ, không được vượt sức chứa dù có nhiều người cùng đăng ký.

Hãy xây dựng một bảng kiểm thử gồm:

1. **Hai ca bình thường:** người tham dự hợp lệ, dữ liệu và phiên còn chỗ.
2. **Các ca biên:** tuổi **15, 16, 17, 99, 100, 101**, cùng ranh giới sức chứa của phiên.
3. **Các ca lỗi:** email thiếu, sessionId không tồn tại, lỗi DB sau khi đã thử ghi.
4. **Các ca dữ liệu bất thường:** tên có dấu tiếng Việt, dấu nháy, emoji; tên chỉ khoảng trắng; email có khoảng trắng đầu/cuối theo chính sách xử lý đã chọn.
5. **Ca đồng thời:** hai yêu cầu cùng tranh một chỗ cuối cùng.
6. **Ca retry:** bên gọi không nhận phản hồi sau khi server đã lưu thành công, rồi thử lại với cùng mã yêu cầu.

Với mỗi ca, ghi **đầu vào**, **kết quả mong đợi**, **trạng thái sau cùng**, **tác dụng phụ được phép** và **cấp độ kiểm thử** phù hợp. Đừng coi tất cả ca này là unit test của một hàm validation.

**Gợi ý đối chiếu:** Giá trị 16 và 100 phải được chấp nhận; 15 và 101 bị từ chối. Tên Unicode không nên mặc định bị từ chối nếu hợp đồng cho phép. Đầu vào không hợp lệ phải dừng trước khi ghi hoặc gửi. Tranh chấp chỗ cuối cùng cần kiểm thử tích hợp với cơ chế cập nhật có điều kiện hoặc khóa phù hợp. Retry sau kết quả chưa rõ cần hợp đồng idempotency để tránh tạo hai bản đăng ký. Lỗi DB cần kiểm tra rollback hoặc trạng thái phục hồi, thay vì chỉ kiểm tra mã lỗi HTTP.

## 14. Ghi nhớ

- Một bộ bằng chứng kiểm thử tốt phải có **ca bình thường, biên, lỗi và dữ liệu bất thường**, được chọn theo **hợp đồng và rủi ro**.
- **Phân hoạch tương đương** giúp chọn lớp đại diện; **phân tích giá trị biên** giúp phát hiện lỗi ngay tại ngưỡng.
- Ca lỗi phải kiểm tra **ngoại lệ, trạng thái sau lỗi và tác dụng phụ**, không chỉ việc phương thức đã ném lỗi.
- Dữ liệu ít gặp **không mặc nhiên sai**; tính hợp lệ phụ thuộc quy tắc của từng trường và từng ranh giới.
- Kết quả chạy xanh là **bằng chứng có phạm vi**, không phải lời chứng minh tuyệt đối. Oracle đúng, assertion có ý nghĩa, kiểm thử tái lập và khả năng truy vết mới làm bằng chứng đáng tin.
