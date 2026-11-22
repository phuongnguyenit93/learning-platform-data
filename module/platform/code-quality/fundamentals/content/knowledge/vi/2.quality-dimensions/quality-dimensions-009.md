# Tính nhất quán trong cùng một hệ thống

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **tính nhất quán (consistency)** là một chiều của chất lượng mã nguồn và vì sao nó ảnh hưởng đến độ tin cậy, khả năng đọc hiểu và khả năng thay đổi.
2. Nhận ra sự thiếu nhất quán trong cách đặt tên, tổ chức mã, xử lý lỗi, định nghĩa hợp đồng, biểu diễn dữ liệu và kiểm thử.
3. Phân biệt **quy ước cần thống nhất** với **khác biệt có chủ đích** xuất phát từ nghiệp vụ hoặc ranh giới kỹ thuật.
4. Đề xuất cách duy trì tính nhất quán trong một dự án Java bằng quy ước rõ ràng, ví dụ tham chiếu, kiểm tra tự động và code review.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Tính nhất quán là một thuộc tính quan trọng vì người đọc thường dự đoán phần mã chưa biết dựa trên các phần mã đã quen thuộc.

## 1. Tính nhất quán nghĩa là gì?

**Tính nhất quán trong cùng một hệ thống** là mức độ mà các thành phần dùng chung những quy ước, cách biểu diễn và nguyên tắc xử lý khi chúng giải quyết **cùng một loại vấn đề**. Khi một lập trình viên hiểu cách hệ thống kiểm tra đầu vào, trả lỗi hoặc gọi repository ở một tính năng, họ có thể dùng hiểu biết đó để đọc tính năng khác.

Ví dụ: hai API cùng tiếp nhận dữ liệu đơn hàng. API thứ nhất trả HTTP 400 cùng mã lỗi có cấu trúc khi số lượng không hợp lệ; API thứ hai lại trả HTTP 200 và chuỗi “FAILED”. Cả hai có thể được viết đúng cú pháp, nhưng người dùng API phải học hai hợp đồng trái ngược nhau. Hậu quả là phía gọi dễ xử lý sai và đội phát triển khó bảo trì.

**Nhất quán không có nghĩa là mọi đoạn mã phải giống nhau.** Một phép tính giá tiền có thể cần **BigDecimal**, trong khi phép đo thời gian thực thi dùng số nguyên nano giây. Sự khác nhau này phản ánh bản chất dữ liệu. Mục tiêu là: **cùng ý nghĩa thì theo cùng quy tắc; khác ý nghĩa thì thể hiện sự khác biệt rõ ràng**.

### Phân biệt với các khái niệm gần nhau

- **Tính nhất quán của mã nguồn:** quy ước, tổ chức, hợp đồng và hành vi của các thành phần có cùng vai trò trong hệ thống.
- **Tính đúng đắn (correctness):** kết quả thực tế có đáp ứng yêu cầu hay không. Hai hàm có thể cùng sai theo một cách nhất quán; do đó nhất quán không thay thế kiểm tra tính đúng đắn.
- **Tính đồng nhất tuyệt đối (uniformity):** áp dụng một hình thức như nhau cho mọi tình huống. Ép mọi thành phần vào một cấu trúc có thể làm thiết kế kém rõ ràng.
- **Tính nhất quán dữ liệu trong hệ phân tán:** dữ liệu giữa các bản sao hoặc dịch vụ được quan sát theo mô hình nhất quán nào. Đây là vấn đề khác với trọng tâm của bài, dù quy ước xử lý dữ liệu cũng ảnh hưởng đến chất lượng mã.

## 2. Vì sao nhất quán làm tăng chất lượng?

Giả sử dự án có 20 dịch vụ xử lý dữ liệu. Nếu mỗi dịch vụ tự định nghĩa quy tắc kiểm tra đầu vào, ghi log và mã lỗi theo cách riêng, người tham gia dự án phải kiểm tra lại từng nơi trước khi sửa một tính năng. Ngược lại, một cách làm đã được mô tả và áp dụng thường xuyên giúp giảm số giả định phải kiểm chứng.

| Lợi ích | Cơ chế tạo ra lợi ích | Ví dụ quan sát được |
| --- | --- | --- |
| **Dễ đọc hiểu** | Cấu trúc quen thuộc giảm thời gian tìm vị trí xử lý | Biết lỗi nghiệp vụ được chuyển thành HTTP response ở cùng một lớp biên |
| **Dễ bảo trì** | Quy ước ổn định giúp định vị nơi sửa và phạm vi tác động | Quy tắc làm tròn tiền chỉ có một chủ sở hữu rõ ràng |
| **Giảm lỗi** | Hạn chế cách xử lý trái ngược cho cùng một tình huống | Giá trị đầu vào không hợp lệ được từ chối nhất quán |
| **Dễ kiểm thử** | Hợp đồng tương tự tạo ra mẫu test tương tự và có thể dùng chung dữ liệu kiểm thử | Các endpoint đều có test về mã lỗi và cấu trúc phản hồi |
| **Hợp tác hiệu quả** | Code review tập trung vào ý nghĩa thay vì tranh cãi lặp lại về phong cách | Formatter tự giải quyết cách xuống dòng và thứ tự import |
| **Dễ mở rộng hệ thống** | Tính năng mới có điểm tham chiếu đáng tin cậy | Thành viên mới dựa vào một tính năng mẫu để xây dựng tính năng tương tự |

Tác động mạnh nhất xuất hiện khi nhất quán ở **hợp đồng và quyết định kỹ thuật**, chứ không chỉ ở dấu cách hay cách đặt dấu ngoặc. Một hệ thống có thể được format rất đẹp nhưng vẫn khó bảo trì nếu các dịch vụ định nghĩa khác nhau về cùng một trạng thái nghiệp vụ.

## 3. Những mặt của tính nhất quán cần quan sát

### 3.1. Ngôn ngữ nghiệp vụ và cách đặt tên

Tên gọi phải phản ánh cùng một ý nghĩa xuyên suốt những nơi liên quan. Ví dụ, nếu hệ thống dùng **customerId** để chỉ định danh khách hàng, việc một số thành phần gọi cùng giá trị đó là **clientCode** hoặc **userKey** mà không có lý do rõ ràng sẽ gây hiểu nhầm.

Trong Java, nên dùng quy ước tên quen thuộc: tên lớp **UpperCamelCase**, phương thức/biến **lowerCamelCase**, hằng số **UPPER_SNAKE_CASE**; đồng thời thống nhất từ vựng nghiệp vụ như **subtotal**, **discount**, **total**. Tên cần phân biệt những khái niệm thật sự khác nhau: **subtotal** trước giảm giá và **payableAmount** sau giảm giá không nên bị ép thành một tên “amount” mơ hồ.

Một số tín hiệu cần xem lại:

- Cùng khái niệm nhưng nhiều tên không được giải thích.
- Cùng tên nhưng khác đơn vị: **timeout** có nơi là mili giây, nơi là giây.
- Tên phương thức gợi ý một hành vi, nhưng thực tế có thêm tác dụng phụ: **calculateTotal()** đồng thời lưu đơn hàng.
- Những chữ viết tắt nội bộ khó đoán hoặc nghĩa của chúng thay đổi giữa các đội.

Nên có **bảng thuật ngữ nhỏ (glossary)** cho các khái niệm xuyên suốt nhiều tính năng; không cần tạo tài liệu đồ sộ cho mọi biến tạm.

### 3.2. Phong cách viết và cấu trúc thành phần

Các quy ước về import, thụt lề, cách dùng dấu ngoặc, tổ chức package và thứ tự thành phần giúp người đọc nhận diện cấu trúc nhanh hơn. Đây là phần phù hợp để tự động hóa bằng formatter, IDE và linter.

Ở mức kiến trúc, các thành phần cùng trách nhiệm nên đi theo cùng mô hình mà nhóm đã chọn. Chẳng hạn, nếu dự án thường đi qua **controller → application service → repository**, một controller mới không nên tự chứa toàn bộ truy vấn cơ sở dữ liệu và quy tắc nghiệp vụ chỉ vì “viết như vậy nhanh hơn”.

Tuy nhiên, việc có thêm lớp abstraction chỉ để tạo hình thức giống nhau không phải lúc nào cũng tốt. Một bộ xử lý file chạy theo lô có thể cần luồng khác một HTTP controller. Cần kiểm tra trách nhiệm và ranh giới thực tế trước khi chuẩn hóa.

### 3.3. Hợp đồng đầu vào, đầu ra và lỗi

**Hợp đồng (contract)** nói rõ thành phần chấp nhận điều gì, trả về điều gì và phản ứng ra sao khi không thể thực hiện yêu cầu.

Trong cùng một loại API, cần quyết định nhất quán về:

| Câu hỏi | Ví dụ về quy ước rõ ràng |
| --- | --- |
| Khi dữ liệu đầu vào sai, xử lý thế nào? | Trả HTTP 400 và mã lỗi có cấu trúc thay vì lúc ném lỗi, lúc trả “false” |
| Khi tài nguyên không tồn tại? | Trả HTTP 404 kèm mã **RESOURCE_NOT_FOUND** |
| Khi có xung đột trạng thái? | Trả HTTP 409 khi yêu cầu mâu thuẫn trạng thái hiện tại, nếu ngữ nghĩa API phù hợp |
| Khi thành công? | Dùng schema phản hồi đã công bố; tránh cùng một loại thao tác mà nơi trả object, nơi trả chuỗi khó phân tích |
| Khi trả lỗi? | Không tiết lộ stack trace, mật khẩu, token hay chi tiết hạ tầng trong phản hồi công khai |

Ví dụ hợp đồng lỗi giả định:

~~~json
{
  "code": "INVALID_QUANTITY",
  "message": "quantity must be greater than zero",
  "requestId": "req-8f2c"
}
~~~

Đây là một lựa chọn thiết kế, không phải định dạng bắt buộc của mọi API. Điều đáng chú ý là các API cùng nhóm chia sẻ **nguyên tắc mã trạng thái, cấu trúc và ý nghĩa trường**; mã lỗi và thông điệp cụ thể vẫn phải phản ánh tình huống thực.

Ngoài HTTP, tính nhất quán cũng áp dụng cho phương thức Java: cùng một nhóm hàm truy vấn không nên lúc trả **null**, lúc trả **Optional**, lúc ném ngoại lệ cho cùng một trạng thái “không tìm thấy” mà không ghi rõ quy tắc. Chọn cách phù hợp với ngữ nghĩa từng API và diễn đạt rõ trong hợp đồng.

### 3.4. Biểu diễn dữ liệu và quy tắc tính toán

Các lỗi khó phát hiện thường đến từ sự khác biệt ngầm về **đơn vị, thời gian, tiền tệ, độ chính xác hoặc cách làm tròn**.

- Tiền tệ: thống nhất việc biểu diễn số tiền, mã tiền tệ và chính sách làm tròn. **BigDecimal** tránh nhiều sai số nhị phân của **double** nhưng không tự quyết định cách làm tròn hay số chữ số thập phân đúng theo nghiệp vụ.
- Thời gian: thể hiện rõ **Instant**, thời gian địa phương hay múi giờ, đặc biệt tại ranh giới API và lưu trữ. Không để một nơi coi timestamp là giây, nơi khác là mili giây.
- Định danh: phân biệt ID nội bộ, ID công khai và mã nghiệp vụ; không đổi qua lại tùy ý.
- Trạng thái: tập giá trị như **CREATED**, **PAID**, **CANCELLED** cần định nghĩa và dùng thống nhất. Không để nhiều dịch vụ dùng các chuỗi khác nhau cho cùng trạng thái mà thiếu tầng ánh xạ.
- Kiểm tra điều kiện: quy tắc “số lượng phải lớn hơn 0” hoặc “đơn hàng được giảm giá từ ngưỡng X” cần một nơi chịu trách nhiệm chính, thay vì bị sao chép với dấu so sánh khác nhau.

Ví dụ, nếu một trang hiển thị giá theo đơn vị đồng nhưng API lại xử lý đơn vị nghìn đồng mà không chỉ rõ, mã có thể trông hợp lệ và vẫn tính sai. Những quy ước về đơn vị cần xuất hiện trong kiểu dữ liệu, tên trường hoặc tài liệu hợp đồng.

### 3.5. Ghi log, bảo mật và khả năng quan sát

Trong cùng hệ thống, các luồng tương tự nên có nguyên tắc thống nhất về mức độ log, thông tin tương quan yêu cầu, phân loại lỗi và dữ liệu không được ghi lại. Ví dụ, **requestId** hoặc **traceId** giúp nối các sự kiện thuộc cùng một yêu cầu.

Không nên vì “đồng nhất log” mà ghi toàn bộ request ở mọi nơi: dữ liệu có thể chứa thông tin cá nhân hoặc bí mật. Quy ước tốt phải xác định **điều gì được ghi**, **điều gì phải che**, và **khi nào cần cảnh báo**.

### 3.6. Kiểm thử và cách xác nhận thay đổi

Các phần mã cùng đặc trưng nên được kiểm chứng theo nguyên tắc tương đương. Nếu mỗi endpoint mới đều có trường hợp “đầu vào không hợp lệ”, bài test cần xác nhận cùng những yếu tố quan trọng: mã trạng thái, mã lỗi, cấu trúc phản hồi và không có tác dụng phụ ngoài ý muốn.

Nhất quán trong kiểm thử không phải sao chép từng test; test phải chứng minh hành vi cụ thể. Đừng chỉ tăng tỷ lệ bao phủ bằng những assertion không liên quan đến hợp đồng.

## 4. Ví dụ Java: quy tắc giống nhau nhưng cách làm khác nhau

Hãy xét hai phần của ứng dụng bán hàng đều tính **thành tiền dòng hàng**. Đây là ví dụ giả định để minh họa vấn đề.

### 4.1. Cách viết thiếu nhất quán

~~~java
// Ở giỏ hàng: dùng double, âm thì coi như 0.
double cartLineTotal(double unitPrice, int quantity) {
    return Math.max(0, unitPrice * quantity);
}

// Ở đơn hàng: dùng BigDecimal, chỉ kiểm tra quantity.
BigDecimal orderLineTotal(BigDecimal price, int quantity) {
    if (quantity < 0) {
        throw new IllegalArgumentException("quantity");
    }
    return price.multiply(BigDecimal.valueOf(quantity));
}
~~~

Hai phương thức xử lý một khái niệm nhưng có các khác biệt quan trọng:

1. Một nơi dùng **double**, nơi khác dùng **BigDecimal** cho tiền.
2. Đơn giá hoặc số lượng âm có thể bị biến thành 0 trong giỏ hàng nhưng ở đơn hàng lại tạo giá trị âm hoặc bị từ chối.
3. Số lượng bằng 0 được chấp nhận ở phương thức thứ hai dù nghiệp vụ có thể yêu cầu số lượng dương.
4. Việc sửa quy tắc cho giỏ hàng chưa chắc sửa được kết quả ở đơn hàng.

Sự không nhất quán này có thể dẫn tới chênh lệch giữa số tiền khách nhìn thấy và số tiền được ghi vào đơn. Chỉ đổi tên hàm cho giống nhau không giải quyết vấn đề, vì điểm bất đồng nằm ở **hợp đồng và cách biểu diễn dữ liệu**.

### 4.2. Thống nhất hợp đồng tại nơi sở hữu quy tắc

Giả sử hệ thống xác nhận rằng **đơn giá không âm, số lượng phải dương** và thành tiền dòng hàng được tính bằng đơn giá nhân số lượng. Ta có thể sử dụng một thành phần dùng chung, không có phụ thuộc I/O:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public final class LineAmounts {
    private LineAmounts() {}

    public record Line(BigDecimal unitPrice, int quantity) {
        public Line {
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException("unitPrice must be non-negative");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }

        public BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static BigDecimal sum(List<Line> lines) {
        Objects.requireNonNull(lines, "lines");
        return lines.stream()
                .map(Line::total)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

Giỏ hàng và đơn hàng có thể dùng chung quy tắc tính **thành tiền dòng hàng** vì cùng một ý nghĩa. Nơi gọi vẫn chịu trách nhiệm cho quy tắc riêng như thuế, phí vận chuyển, chiết khấu hay trạng thái thanh toán.

Đoạn mã dùng **record**, có trong Java 17. Ví dụ chưa quyết định về mã tiền tệ, quy mô phần thập phân hay làm tròn; một hệ thống thực tế cần định nghĩa chúng ở đúng ranh giới nghiệp vụ. Không nên mở rộng lớp dùng chung thành một “siêu tiện ích tính mọi loại tiền” nếu những phép tính có hợp đồng khác nhau.

### 4.3. Kiểm thử hợp đồng đã thống nhất

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class LineAmountsTest {
    @Test
    void sumsLinesUsingTheSameRule() {
        var lines = List.of(
                new LineAmounts.Line(new BigDecimal("50.00"), 2),
                new LineAmounts.Line(new BigDecimal("25.00"), 1));

        assertEquals(new BigDecimal("125.00"), LineAmounts.sum(lines));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> new LineAmounts.Line(new BigDecimal("10.00"), 0));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> new LineAmounts.Line(new BigDecimal("-1.00"), 1));
    }
}
~~~

Ví dụ dùng **JUnit Jupiter (JUnit 5)**. Các test xác nhận quy tắc dùng chung; nhóm vẫn cần test riêng cho những hành vi khác của giỏ hàng và đơn hàng. Đặc biệt, nếu nghiệp vụ cho phép **dòng hoàn tiền âm**, đó là một khái niệm cần hợp đồng riêng; không nên lén nới điều kiện của **Line** và làm thay đổi mọi nơi sử dụng.

### 4.4. Khi nào không nên dùng chung mã?

Hai thành phần có thể trông giống nhau hôm nay nhưng có **lý do thay đổi khác nhau**. Ví dụ, phí hoàn tiền được tính dựa trên quy định thanh toán; giảm giá hàng hóa được tính theo chính sách khuyến mại. Dù cùng dùng phép nhân phần trăm, gộp chúng thành một lớp nghiệp vụ duy nhất có thể tạo liên kết không cần thiết.

Hãy phân biệt hai cấp độ:

- **Nhất quán về quy tắc:** hai phần tuân thủ cùng quy ước biểu diễn tiền, kiểm tra dữ liệu và đặt tên.
- **Tái sử dụng cách triển khai:** chỉ nên dùng chung khi hai phần thực sự chia sẻ **cùng hợp đồng và cùng lý do thay đổi**.

Không phải mọi sự trùng lặp vài dòng đều là lỗi thiết kế. Đôi khi hai đoạn mã riêng, rõ ràng và tuân thủ cùng quy ước lại dễ bảo trì hơn một trừu tượng dùng chung quá rộng.

## 5. Nhận diện sự thiếu nhất quán trong dự án thật

Không thể đánh giá tính nhất quán chỉ bằng một công cụ. Cần so sánh các thành phần **cùng loại** và hỏi liệu khác biệt có được giải thích bằng yêu cầu hay ranh giới kỹ thuật không.

| Dấu hiệu | Điều cần xác minh | Rủi ro |
| --- | --- | --- |
| Một số API lỗi trả mã HTTP đúng nghĩa, số khác luôn trả 200 | Có hợp đồng API chung hay tính tương thích lịch sử không? | Client hiểu sai thành công/thất bại |
| Cùng thông tin tiền nhưng lúc lưu double, lúc lưu số nguyên đơn vị nhỏ nhất | Đơn vị, tiền tệ, làm tròn và phạm vi dữ liệu là gì? | Sai số hoặc lệch số tiền |
| Hai đường đi tính cùng quy tắc giảm giá | Nơi nào sở hữu quy tắc và có test ranh giới không? | Sửa một nơi, bỏ sót nơi khác |
| Controller này gọi repository trực tiếp; controller khác dùng service | Đây là ngoại lệ có chủ đích hay cấu trúc phát triển tự phát? | Khó định vị nghiệp vụ, khó kiểm thử |
| Có nơi ném exception, nơi trả null cho “không tìm thấy” | Các hàm có thật sự cùng ngữ nghĩa không? | Quên xử lý kết quả, lỗi runtime |
| Một số luồng ghi toàn bộ payload vào log | Dữ liệu có bí mật, thông tin cá nhân hoặc mã định danh nhạy cảm không? | Rò rỉ thông tin, khó tuân thủ quy định |
| Review thường lặp lại cùng một góp ý về định dạng | Có thể tự động hóa quy tắc đó không? | Tốn thời gian và dễ bỏ sót |

Một dấu hiệu tốt để bắt đầu điều tra là **cùng một thay đổi nghiệp vụ nhưng phải sửa ở nhiều nơi không rõ liên hệ**. Tình huống này có thể cho thấy quy tắc bị phân tán hoặc hợp đồng chưa được xác định. Tuy nhiên, cần chứng minh rằng các nơi đó thực sự dùng cùng quy tắc trước khi gom chúng.

## 6. Cách xây dựng và duy trì tính nhất quán

### Bước 1: Tìm quy ước đã có và xác định phạm vi

Trước khi đưa ra chuẩn mới, đọc một số thành phần đang hoạt động tốt và có cùng trách nhiệm với phần cần sửa. Ghi lại những quyết định ảnh hưởng nhiều nơi: đặt tên, cách trả lỗi, giới hạn của các lớp, biểu diễn tiền/thời gian, xử lý null và chiến lược kiểm thử.

Không nên lấy một ngoại lệ lịch sử làm chuẩn chỉ vì nó xuất hiện đầu tiên. Nếu cùng một vấn đề đang được xử lý theo hai cách, hãy so sánh tính đúng đắn, tính tương thích và tác động bảo trì để chọn hướng chuẩn hóa.

### Bước 2: Ghi quyết định theo cách có thể áp dụng

Một quy ước tốt cần nêu **phạm vi áp dụng, quy tắc, lý do và ví dụ**. Chẳng hạn:

> **Phạm vi:** Các REST API nội bộ phiên bản mới. **Quy tắc:** Lỗi kiểm tra đầu vào trả HTTP 400 với trường code, message, requestId. **Lý do:** Client có thể xử lý lỗi nhất quán và truy vết yêu cầu. **Ngoại lệ:** API cũ có hợp đồng công khai khác cần chiến lược chuyển đổi riêng.

Quy ước như vậy dễ thực hiện và dễ review hơn chỉ thị mơ hồ “viết code sạch”. Với quyết định kiến trúc có tác động lâu dài, nhóm có thể lưu một **ADR (Architecture Decision Record)** ngắn ghi lựa chọn, lý do và đánh đổi.

### Bước 3: Cung cấp ví dụ tham chiếu

Một tính năng mẫu hoặc đoạn code minh họa có đủ xử lý thành công, lỗi và test giúp người mới làm đúng ngay từ đầu. Ưu tiên ví dụ đang được sử dụng và bảo trì thường xuyên; ví dụ lỗi thời có thể vô tình củng cố quy ước cũ.

### Bước 4: Tự động hóa những quy tắc kiểm tra được

| Nhu cầu | Công cụ hoặc cơ chế phù hợp |
| --- | --- |
| Đồng nhất định dạng Java | Formatter như google-java-format hoặc Spotless |
| Kiểm tra cách đặt tên, import, một số quy tắc mã | Checkstyle, PMD, cấu hình IDE |
| Phát hiện một số mẫu lỗi tiềm ẩn | SpotBugs, Error Prone |
| Xác nhận hành vi của hợp đồng | JUnit và các bộ unit/integration/contract test |
| Tránh mã không đạt quy tắc được tích hợp | CI chạy build, test và kiểm tra cấu hình phù hợp |

Formatter có thể thống nhất cách xuống dòng; nó **không thể bảo đảm** hai API có cùng ngữ nghĩa lỗi. Hợp đồng nghiệp vụ cần được chứng minh bằng test thích hợp và review. Cảnh báo công cụ cũng phải được xử lý theo ngữ cảnh, vì có thể có kết quả dương tính giả.

### Bước 5: Áp dụng trong code review

Với mỗi thay đổi, người review có thể hỏi:

1. Có thành phần tương tự đã giải quyết vấn đề này chưa? Nếu có, khác biệt mới được giải thích bằng yêu cầu nào?
2. Thuật ngữ, đơn vị, quy tắc lỗi và điểm sở hữu nghiệp vụ có phù hợp với phần còn lại không?
3. Test đã xác nhận những quy ước quan trọng và trường hợp biên chưa?
4. Nếu đây là ngoại lệ, lý do và phạm vi ngoại lệ có rõ để người sau không bắt chước sai không?

Phản hồi nên đi kèm dẫn chứng. Ví dụ: “Các API tạo tài nguyên cùng nhóm đang trả 400 và mã INVALID_INPUT cho dữ liệu không hợp lệ; endpoint này trả 200 nên client có thể hiểu nhầm. Bạn có thể dùng bộ xử lý lỗi chung hoặc giải thích yêu cầu tương thích ở đây không?”.

### Bước 6: Cải thiện dần mà vẫn bảo vệ tương thích

Trong hệ thống đang hoạt động, thay đổi đồng loạt cách trả lỗi, tên trường API hoặc cấu trúc dữ liệu có thể phá vỡ client và dữ liệu cũ. Cách tiếp cận thận trọng:

- **Ưu tiên nơi có rủi ro:** tiền, phân quyền, trạng thái, hợp đồng liên dịch vụ trước các khác biệt thuần trình bày.
- **Đặt chuẩn cho mã mới:** yêu cầu tính năng mới tuân thủ quy ước đã chọn.
- **Sửa khi chạm đến mã liên quan:** gom các chỉnh sửa có lý do và kiểm thử đủ, tránh cuộc đại tu toàn hệ thống không có mục tiêu.
- **Chuyển đổi có kế hoạch ở ranh giới công khai:** dùng versioning, adapter hoặc giai đoạn tương thích khi cần; theo dõi client trước khi loại bỏ hợp đồng cũ.
- **Ghi nhận ngoại lệ:** nêu rõ vì sao ngoại lệ còn tồn tại, ai chịu trách nhiệm và khi nào nên xem lại.

Sự thống nhất giữa các nhóm hình thành nhờ **ví dụ, giải thích và phản hồi liên tục**, không chỉ bằng một tài liệu quy định.

## 7. Những đánh đổi dễ bị bỏ qua

### Nhất quán với quy ước cũ hay cải thiện thiết kế?

Không phải quy ước đang phổ biến luôn là tốt. Một hệ thống cũ có thể dùng chuỗi để biểu diễn ngày tháng hoặc trả mã lỗi mơ hồ. Khi có bằng chứng về lỗi và chi phí bảo trì, nhóm nên đề xuất quy ước tốt hơn, xác định ranh giới áp dụng và kế hoạch chuyển đổi. Giữ cách làm sai chỉ vì “từ trước đến giờ đều vậy” cũng là một vấn đề chất lượng.

### Nhất quán cục bộ hay toàn hệ thống?

Trong hệ thống lớn, hai nhóm dịch vụ có thể có yêu cầu và công nghệ khác nhau. Nên thống nhất **hợp đồng giao tiếp, thuật ngữ chung và chính sách an toàn** ở cấp hệ thống, đồng thời cho phép cách tổ chức nội bộ khác nhau khi có lý do chính đáng. Không nhất thiết buộc mọi service có cùng cấu trúc package hoặc cùng thư viện nội bộ.

### Bao nhiêu quy tắc là đủ?

Quy tắc càng chi tiết càng tốn công duy trì và dễ làm giảm tính linh hoạt. Chọn trước những quy ước ngăn hiểu nhầm, lỗi hoặc thay đổi dây chuyền; tự động hóa phần cơ học. Nếu không thể giải thích rủi ro mà một quy tắc đang giảm bớt, cần xem lại mức cần thiết của quy tắc đó.

### Khi nào một ngoại lệ là hợp lý?

Khác biệt là hợp lý khi có **yêu cầu khác, hợp đồng khác, ranh giới khác hoặc ràng buộc tương thích**. Ngoại lệ nên đủ rõ để người khác không suy ra rằng mọi thành phần đều có thể áp dụng cách mới. Ví dụ, hệ thống tiếp nhận sự kiện bất đồng bộ cần cơ chế xử lý thất bại khác API đồng bộ; hai cách có thể cùng tuân thủ một chính sách chung về truy vết, không mất dữ liệu và thông báo lỗi.

## 8. Tình huống thực hành

Một ứng dụng có hai API cập nhật trạng thái đơn hàng:

**API A — cập nhật trạng thái giao hàng**

- Kiểm tra quyền người gọi trước khi cập nhật.
- Nếu đơn hàng không tồn tại, trả HTTP 404 với mã **ORDER_NOT_FOUND**.
- Nếu trạng thái chuyển đổi không hợp lệ, trả HTTP 409 với mã **INVALID_TRANSITION**.
- Ghi log với **requestId**, không ghi token xác thực.

**API B — hủy đơn hàng**

- Truy cập repository ngay trong controller, không kiểm tra quyền người gọi.
- Nếu đơn hàng không tồn tại, trả HTTP 200 kèm chuỗi **"FAILED"**.
- Nếu đã giao hàng, âm thầm bỏ qua yêu cầu.
- Ghi toàn bộ request, kể cả trường chứa token, vào log.

Hãy thử giải quyết các câu hỏi sau trước khi xem gợi ý:

1. Những khác biệt nào chủ yếu thuộc **tính nhất quán**, những khác biệt nào còn gây nguy cơ **đúng đắn hoặc bảo mật**?
2. Nếu hai API là cùng phiên bản và không bị ràng buộc bởi client cũ, những hợp đồng nào nên thống nhất?
3. Những test nào giúp chứng minh API B tuân thủ các hợp đồng quan trọng?
4. Có nên lập tức gom cả hai API vào một controller và một phương thức chung không? Vì sao?

### Gợi ý phân tích

API B có nhiều rủi ro: thiếu kiểm tra quyền là vấn đề bảo mật; âm thầm bỏ qua trạng thái không hợp lệ có thể khiến phía gọi tin rằng thao tác đã thành công; log token có thể làm lộ bí mật. Các khác biệt về mã lỗi, cấu trúc luồng và chính sách log cho thấy quy ước không được áp dụng thống nhất.

Nếu yêu cầu nghiệp vụ và hợp đồng API phù hợp, cả hai nên kiểm tra quyền ở vị trí đáng tin cậy, trả lỗi có cấu trúc với mã trạng thái tương ứng và chỉ ghi thông tin log an toàn. Có thể xây dựng các test cho: người gọi không đủ quyền; đơn hàng không tồn tại; hủy đơn đã giao; hủy thành công; phản hồi lỗi; dữ liệu nhạy cảm không xuất hiện trong log. Các test phải dựa trên hợp đồng thực sự được xác nhận và triển khai với môi trường phù hợp.

Chưa có căn cứ để gộp hai nghiệp vụ cập nhật giao hàng và hủy đơn vào một phương thức. Chúng có thể có điều kiện chuyển trạng thái và tác dụng phụ khác nhau. Mục tiêu là **chung nguyên tắc kiểm soát và hợp đồng**, trong khi vẫn giữ trách nhiệm riêng của từng nghiệp vụ.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Nếu mọi lớp đều dùng cùng một formatter, có thể kết luận hệ thống nhất quán không?

*Gợi ý:* Chưa. Formatter chỉ hỗ trợ nhất quán hình thức, không chứng minh hợp đồng, quy tắc dữ liệu hay tổ chức trách nhiệm.

**Câu 2.** Hai phần mã đều nhân giá với số lượng. Có cần đặt chúng trong một lớp dùng chung?

*Gợi ý:* Chỉ khi chúng thật sự có cùng ý nghĩa, cùng hợp đồng và cùng lý do thay đổi. Nếu một phần tính bán hàng còn phần kia tính hoàn tiền, cần xem xét khác biệt nghiệp vụ.

**Câu 3.** Một endpoint lâu đời dùng cấu trúc lỗi khác nhưng có nhiều client phụ thuộc. Nên đổi ngay để giống endpoint mới?

*Gợi ý:* Không đổi tùy tiện. Cần đánh giá tính tương thích, kế hoạch chuyển đổi hoặc phiên bản API, rồi làm rõ quy ước áp dụng cho endpoint mới.

**Câu 4.** Chọn một quy ước đang thiếu nhất quán trong dự án của bạn. Bạn sẽ mô tả quy tắc, kiểm tra tác động và tự động hóa phần nào?

*Gợi ý:* Chỉ rõ phạm vi, hành vi mong đợi, ví dụ đúng/sai, cách kiểm chứng, ngoại lệ và người chịu trách nhiệm.

## Ghi nhớ

Tính nhất quán giúp người phát triển **đoán đúng cách hệ thống hoạt động** dựa trên những quy ước đã biết. Nó biểu hiện ở từ vựng, cấu trúc, hợp đồng, dữ liệu, lỗi, quan sát hệ thống và kiểm thử. Duy trì tính nhất quán đòi hỏi quy ước có lý do, ví dụ tham chiếu, công cụ tự động và code review; đồng thời phải chấp nhận những khác biệt thực sự bắt nguồn từ nghiệp vụ hoặc kiến trúc. Một hệ thống đáng tin cậy, dễ hiểu và dễ thay đổi là hệ thống mà **những quyết định giống nhau được xử lý theo cách có thể dự đoán**, còn ngoại lệ được giải thích rõ ràng.
