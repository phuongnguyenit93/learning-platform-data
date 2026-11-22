# Kích thước mã và phạm vi mà số dòng có ý nghĩa

Một hệ thống có 50.000 dòng Java chưa chắc kém chất lượng hơn hệ thống có 5.000 dòng. Một phương thức 70 dòng chưa chắc khó hiểu hơn phương thức 10 dòng; một lần xóa 800 dòng chưa chắc làm hệ thống đơn giản hơn. **Số dòng mã (Lines of Code – LOC)** là một phép đo hữu ích, nhưng chỉ khi ta biết **đang đếm cái gì, trong phạm vi nào và để trả lời câu hỏi gì**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã liên quan đến khả năng **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Chỉ số chất lượng**, LOC nên được xem là **tín hiệu về kích thước và phạm vi cần chú ý**, không phải điểm số trực tiếp cho tính đúng đắn, bảo mật hoặc chất lượng thiết kế.

Bài này làm rõ các cách đếm dòng, khi nào con số có ý nghĩa, cách so sánh công bằng, những sai lầm khi đặt ngưỡng và một ví dụ Java cho thấy **viết nhiều dòng hơn đôi khi lại dễ đọc hơn**.

## 1. Số dòng mã đo điều gì?

Theo nghĩa đơn giản, LOC trả lời: **có bao nhiêu dòng trong một phạm vi mã nguồn được định nghĩa?**

Vấn đề là các công cụ và nhóm phát triển có thể dùng những định nghĩa khác nhau:

| Cách gọi | Điều được tính | Lưu ý |
| --- | --- | --- |
| **Physical LOC** | Số dòng vật lý trong tệp nguồn, theo quy tắc nhận diện dòng của công cụ. | Có thể bao gồm dòng trống và chú thích. |
| **Source LOC (SLOC)** | Số dòng nguồn theo định nghĩa được công cụ hoặc tổ chức chọn. | Thuật ngữ không được mọi công cụ dùng hoàn toàn giống nhau; phải đọc cách tính. |
| **Non-comment LOC (NCLOC)** | Các dòng có mã thực thi/khai báo, không phải dòng chỉ chứa comment hoặc dòng trống, theo quy tắc công cụ. | Dòng vừa chứa code vừa chứa comment vẫn có thể được tính; cần xem định nghĩa cụ thể. |
| **Logical LOC / statements** | Các đơn vị logic, như câu lệnh hoặc khai báo, được đếm theo cú pháp. | Không nhất thiết bằng số dòng vật lý; khác biệt đáng kể giữa ngôn ngữ và công cụ. |
| **Changed lines / churn** | Số dòng thêm, xóa hoặc thay đổi trong một khoảng thời gian/diff. | Đo **mức thay đổi**, không phải kích thước hiện tại của codebase. |

Không nên dùng SLOC và NCLOC như từ đồng nghĩa tuyệt đối. Trong báo cáo thực tế, phải kèm **tên công cụ, phiên bản, định nghĩa và bộ lọc**. Một công cụ có thể tính comment nằm trên cùng dòng với code khác một công cụ khác; lệnh đếm bằng ký tự xuống dòng cũng không tương đương parser hiểu cú pháp.

### Ví dụ: đổi định dạng làm số dòng vật lý tăng

~~~java
// Cách viết gọn trên một dòng:
if (isActive && hasPermission) { process(); }
~~~

~~~java
// Cùng quyết định, trình bày thành nhiều dòng:
if (isActive && hasPermission) {
    process();
}
~~~

Với giả định các lời gọi không đổi, **đường chạy và điều kiện tương tự nhau**, nhưng số dòng vật lý của đoạn if khác nhau. Vì vậy, nếu đổi formatter rồi LOC tăng, không thể lập tức kết luận lượng logic nghiệp vụ tăng.

Ở chiều ngược lại, ép nhiều câu lệnh lên cùng một dòng có thể giảm Physical LOC mà khiến code **khó review hơn**.

## 2. Phạm vi đo quan trọng ngang bản thân con số

Trước khi đọc chỉ số, hãy xác định **đơn vị phân tích**. LOC ở các phạm vi khác nhau trả lời các câu hỏi khác nhau:

| Phạm vi | Câu hỏi hữu ích | Điều dễ bị hiểu sai |
| --- | --- | --- |
| **Một phương thức** | Có dấu hiệu đang chứa quá nhiều bước hoặc nhánh cần xem lại không? | Phương thức dài không tự động là phương thức sai. |
| **Một lớp** | Lớp có đang gom nhiều trách nhiệm hoặc quá nhiều trạng thái không? | Lớp lớn có thể là bảng ánh xạ dữ liệu hoặc logic tuần tự rõ ràng. |
| **Một package/module** | Phần nào của hệ thống có khối lượng mã lớn hoặc tăng nhanh? | Module lớn có thể chủ ý sở hữu nhiều tính năng. |
| **Một service/repository** | Quy mô mã cần bảo trì, phân chia sở hữu và tác động của thay đổi là gì? | Không thể dùng tổng LOC để xếp hạng chất lượng giữa hai sản phẩm khác nhiệm vụ. |
| **Một pull request** | Reviewer phải xem khoảng bao nhiêu dòng thay đổi và loại thay đổi nào? | 1.000 dòng format-only khác 30 dòng thay đổi quyền truy cập. |
| **Một giai đoạn lịch sử** | Phần mã nào có xu hướng tăng, giảm hoặc bị sửa nhiều? | Chuyển file, code generation và thay formatter có thể làm lệch xu hướng. |

Số **120 dòng** có thể là cảnh báo hữu ích cho một method, nhưng là quá ít nếu đang mô tả cả một module. Số **10.000 dòng** có thể nhỏ với một hệ thống trưởng thành, nhưng là biến động bất thường nếu một PR chỉ được yêu cầu đổi một dấu so sánh.

**Không có một ngưỡng LOC phổ quát** phù hợp mọi ngôn ngữ, loại mã và bối cảnh thay đổi.

## 3. Đếm những tệp nào?

Giả sử một repository có các thành phần sau. Đây là **số liệu giả định để minh họa cách chọn phạm vi**, không phải kết quả đo một dự án thực tế.

| Nhóm tệp | Dòng theo một cách đếm nhất quán | Nên gộp chung không? |
| --- | ---: | --- |
| Java production viết tay | 6.200 | Dùng khi phân tích khối lượng logic sản phẩm. |
| Java test viết tay | 3.100 | Nên báo riêng vì mục đích và cấu trúc khác production. |
| Java generated từ schema | 7.500 | Nên tách riêng; kích thước có thể do generator quyết định. |
| Tệp cấu hình và migration | 900 | Có thể rất quan trọng nhưng không tương đương logic Java. |
| README, tài liệu và ví dụ | 1.300 | Thuộc nội dung hỗ trợ, không nên trộn thành LOC Java production. |
| **Tổng tất cả nhóm** | **19.000** | Là tổng quy mô tệp theo phép đếm này, không phải “19.000 dòng nghiệp vụ Java”. |

Nếu hỏi “Độ lớn Java production cần bảo trì thủ công là bao nhiêu?”, con số phù hợp hơn là **6.200 dòng theo cách đếm đã chốt**, không phải tổng 19.000.

Nếu hỏi “Repository chứa bao nhiêu nội dung nguồn và tài liệu?”, tổng 19.000 có thể hữu ích, nhưng cần trình bày thành phần của nó.

### Generated code làm méo nhận định thế nào?

Một lần nâng cấp công cụ sinh client API có thể tăng từ 3.000 lên 8.000 dòng Java generated dù hợp đồng API chỉ thay đổi ít. Nếu không tách loại này, dashboard có thể báo hệ thống phình ra đột ngột dù mã nghiệp vụ viết tay gần như không thay đổi.

Ngược lại, **generated code vẫn cần được kiểm tra khi tích hợp**: nó có thể được biên dịch, phân phối và gây lỗi runtime. Tách khỏi chỉ số kích thước mã viết tay **không có nghĩa loại khỏi mọi quy trình kiểm thử, bảo mật hoặc quản lý phụ thuộc**.

## 4. Những câu hỏi LOC có thể trả lời tốt

Số dòng có giá trị nhất khi được dùng làm **tín hiệu hướng sự chú ý**:

1. **Xác định vùng lớn bất thường:** Một method, class hoặc file lớn hơn nhiều so với các thành phần cùng vai trò có thể cần review.
2. **Theo dõi xu hướng có kiểm soát:** Một module liên tục tăng LOC mà không có thay đổi chức năng tương xứng có thể có sao chép hoặc tích tụ trách nhiệm.
3. **Ước lượng phạm vi bảo trì:** Nhiều mã sản phẩm do nhóm sở hữu có thể kéo theo nhu cầu review, kiểm thử, hiểu hợp đồng và chuyển giao cao hơn.
4. **Phát hiện thay đổi cơ học lớn:** PR sửa một yêu cầu rất hẹp nhưng thay hàng nghìn dòng có thể đã chạy formatter ngoài phạm vi.
5. **Phân tích nơi cần đầu tư hiểu mã:** Kết hợp LOC với số lần thay đổi, lỗi hồi quy và độ phức tạp để tìm những nơi thường xuyên gây khó khăn.
6. **Định hướng chia việc review:** Diff quá lớn có thể cần tách thành các PR có chủ đích để tăng khả năng kiểm chứng.

Nhưng LOC không trả lời trực tiếp:

- Thuật toán có đúng không?
- Quyền truy cập có an toàn không?
- Code có hiệu năng tốt không?
- Mọi đường thất bại có được xử lý không?
- Mức độ kết dính và ghép nối có phù hợp không?
- Người mới có thể tìm hành vi nhanh không?
- Bộ kiểm thử có phát hiện lỗi quan trọng không?

Những câu hỏi ấy cần **bằng chứng khác**.

## 5. Java: ít dòng hơn chưa chắc dễ hiểu hơn

Giả sử chính sách phí giao hàng:

- Đơn có **subtotalVnd không âm**.
- Từ **500.000 VND** trở lên được miễn phí giao tiêu chuẩn.
- Dưới ngưỡng đó, phí tiêu chuẩn là **30.000 VND**.
- Giao nhanh cộng **20.000 VND**, kể cả khi phí tiêu chuẩn bằng 0.

Hai cách viết sau được đặt chung trong một lớp để **so sánh bài học**. Trong codebase thật, nên giữ một implementation được lựa chọn thay vì để hai bản sao cùng tồn tại.

~~~java
public final class ShippingFeeCalculator {
    private static final long FREE_THRESHOLD = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_FEE = 20_000L;

    private ShippingFeeCalculator() {
    }

    // Cách viết rất gọn nhưng dùng số trực tiếp trong biểu thức.
    public static long compact(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) throw new IllegalArgumentException("negative");
        return (subtotalVnd >= 500_000L ? 0L : 30_000L)
                + (express ? 20_000L : 0L);
    }

    // Cách viết chủ động đặt tên cho các bước.
    public static long readable(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative");
        }

        long standardFee = subtotalVnd >= FREE_THRESHOLD
                ? 0L
                : STANDARD_FEE;
        long expressSurcharge = express ? EXPRESS_FEE : 0L;

        return standardFee + expressSurcharge;
    }
}
~~~

**readable** có nhiều dòng thân phương thức hơn **compact**, nhưng từng bước thể hiện rõ ý định: kiểm tra tiền điều kiện, phí tiêu chuẩn, phụ phí giao nhanh và tổng phí.

Số dòng tăng trong phạm vi nhỏ này **có thể là sự đánh đổi tốt** vì tính dễ đọc và khả năng sửa quy tắc riêng từng phần. Tuy nhiên, không phải cứ tách một biểu thức thành nhiều biến là luôn tốt; biến mới phải có tên và vai trò bổ sung ý nghĩa.

Hai bản chỉ được xem là tương đương trong **hợp đồng minh họa**. Cần kiểm thử thay vì khẳng định tương đương vì nhìn bằng mắt.

## 6. Bảo vệ hành vi bằng expected cụ thể

JUnit 5 có thể chứng minh cả hai phiên bản đạt cùng các **kết quả kỳ vọng độc lập theo đặc tả**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeCalculatorTest {
    @ParameterizedTest
    @CsvSource({
            "0, false, 30000",
            "499999, false, 30000",
            "499999, true, 50000",
            "500000, false, 0",
            "500000, true, 20000",
            "2000000, true, 20000"
    })
    void bothFormsMatchContract(
            long subtotal, boolean express, long expected) {
        assertEquals(expected,
                ShippingFeeCalculator.compact(subtotal, express));
        assertEquals(expected,
                ShippingFeeCalculator.readable(subtotal, express));
    }

    @Test
    void negativeSubtotalIsRejectedByBoth() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeeCalculator.compact(-1L, false));
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeeCalculator.readable(-1L, false));
    }
}
~~~

Phần kiểm thử tham số cần thư viện **JUnit Jupiter Params** trong cấu hình dự án. Đây là ví dụ kiến thức; việc có mã JUnit không đồng nghĩa các lệnh test đã được chạy.

Các assertion dùng **30.000, 50.000, 0 và 20.000** là kết quả đã được suy từ yêu cầu. Không lấy expected bằng cách gọi một trong hai phương thức rồi so với phương thức kia, vì hai bản có thể cùng chứa một lỗi.

Điểm rút ra không phải “phương thức dài hơn luôn tốt hơn”, mà là **tính đúng và khả năng đọc cần được đánh giá riêng với LOC**.

## 7. Số dòng và độ phức tạp là hai trục khác nhau

Một method 15 dòng có thể chứa:

- Nhiều điều kiện boolean khó hiểu.
- Một biểu thức Stream lồng nhau khó debug.
- Nhiều lời gọi có tác dụng phụ ẩn.
- Logic bảo mật nhạy cảm hoặc chuyển trạng thái phức tạp.

Trong khi đó, một method 60 dòng có thể là một chuỗi chuyển đổi dữ liệu dễ theo dõi, có tên biến rõ và ít nhánh.

| Ví dụ | LOC có thể cho thấy | Muốn kết luận thêm cần xem |
| --- | --- | --- |
| Method ngắn nhưng nhiều nhánh | Chiều dài nhỏ. | Độ phức tạp điều khiển, điều kiện boolean, đường đi. |
| Method dài nhưng nhiều bước tuần tự | Chiều dài lớn. | Độ kết dính, tên các bước và lý do để trích xuất. |
| Class có hàng trăm dòng getter/setter | Kích thước class lớn. | Bao nhiêu logic có ý nghĩa, có thể là generated code không. |
| Service 300 dòng xử lý nhiều trách nhiệm | Có tín hiệu cần chú ý. | Quy tắc thay đổi cùng nhau không, phụ thuộc và khả năng kiểm thử. |
| Module 4.000 dòng có nhiều lỗi hồi quy | Kích thước và vùng sở hữu. | Churn, lỗi, kiểm thử, ownership và lịch sử thay đổi. |

LOC và **cyclomatic complexity**, **cognitive complexity**, độ ghép nối hay độ bao phủ test là **những phép đo khác nhau**. Cần đọc định nghĩa từng metric; không nên tạo “điểm chất lượng tổng hợp” bằng cách cộng tùy ý các con số không cùng đơn vị.

## 8. Phân bố kích thước hữu ích hơn một số tổng

Hai module đều có **2.000 dòng Java production viết tay**:

- **Module A:** phần lớn method nhỏ, một số lớp điều phối hợp lý, mỗi trách nhiệm dễ tìm.
- **Module B:** một lớp chứa phần lớn quy tắc, có method dài nhiều nhánh và phải sửa thường xuyên.

Tổng LOC bằng nhau nhưng chi phí hiểu, sửa và kiểm thử có thể rất khác.

Để phát hiện vùng cần xem, có thể phân tích:

- Số dòng **theo file**, **class**, **method** và **module**.
- Phân bố và các trường hợp ngoại lệ, thay vì chỉ số trung bình.
- Những thành phần **lớn và được sửa nhiều lần**.
- Những thành phần lớn nhưng gần như không thay đổi.
- Các phần mã generated hoặc cấu hình không thuộc loại công việc đang đánh giá.

Ví dụ một báo cáo giả định:

| Method | Dòng mã theo cách đếm đã chốt | Thay đổi trong kỳ | Tín hiệu |
| --- | ---: | ---: | --- |
| calculateShippingFee | 24 | 1 lần | Có thể bình thường; kiểm tra hợp đồng và test. |
| parseLegacyPayload | 180 | 0 lần | Lớn nhưng ổn định; chưa đủ lý do refactor ngay. |
| confirmOrder | 95 | 12 lần | Đáng xem vì kích thước và mức thay đổi cùng cao. |
| mapGeneratedDto | 260 | Tạo lại theo schema | Cần tách khỏi phân tích mã viết tay. |

**Không có quy tắc mặc định rằng method 95 dòng phải bị chia nhỏ.** Số liệu giúp đặt câu hỏi: liệu nó có nhiều trách nhiệm, quá nhiều nhánh hoặc thay đổi chạm tới những phần không liên quan hay không?

## 9. Thay đổi kích thước theo thời gian: phải giữ nguyên cách đếm

Công thức cơ bản:

\[
\Delta LOC = LOC_{sau} - LOC_{trước}
\]

Ví dụ một module có **1.600 NCLOC Java production viết tay**, sau một phiên bản tăng thành **1.800 NCLOC** theo **cùng công cụ, cấu hình và phạm vi**. Mức tăng là **200 NCLOC**, tương đương **12,5%** so với thời điểm trước.

Con số này cho biết **quy mô mã được đếm tăng**, chưa nói tăng vì:

- Thêm tính năng mới đã được yêu cầu.
- Bổ sung xử lý lỗi, quyền hoặc kiểm tra đầu vào bị thiếu.
- Sao chép một quy tắc thay vì tái sử dụng.
- Sinh thêm lớp trung gian không có ý nghĩa.
- Đổi cách đếm, ngôn ngữ hoặc phạm vi.

Muốn diễn giải cần xem **diff, yêu cầu thay đổi và phân bố**.

### Các sự kiện có thể tạo “đứt gãy” số liệu

1. **Đổi formatter:** nhiều dòng được xuống khác đi.
2. **Đổi công cụ đếm:** cách tính NCLOC/comment khác.
3. **Đổi phạm vi:** thêm/bỏ thư mục test hoặc generated.
4. **Tách/gộp module:** dòng di chuyển sang nơi khác.
5. **Thay code bằng thư viện:** LOC giảm nhưng phụ thuộc và rủi ro vận hành có thể tăng.
6. **Chuyển ngôn ngữ:** ngôn ngữ biểu đạt cùng hành vi bằng lượng dòng khác nhau.
7. **Sinh mã từ schema:** LOC tăng mà lượng quyết định viết tay không tăng tương ứng.

Nếu thay một trong các điều kiện đo, hãy **đánh dấu thời điểm thay đổi phép đo** hoặc tính lại cả quá khứ theo cùng quy tắc nếu hợp lý. Không trình bày biểu đồ liền mạch như thể hai con số hoàn toàn tương đương.

## 10. Churn và kích thước mã là hai điều khác nhau

Giả sử một pull request có:

~~~text
+80 dòng được thêm
-70 dòng bị xóa
-----------------
+10 dòng thay đổi ròng
~~~

Điều này **không có nghĩa** PR chỉ tác động đến 10 dòng. Có thể có 150 dòng nằm trong phần thêm/xóa của diff, còn mức thay đổi ròng của phép đếm ấy là +10.

Ngược lại, một lần di chuyển hoặc chạy formatter có thể tạo churn lớn dù hành vi dự kiến không đổi. Công cụ diff, nhận diện rename/move và cách đếm có thể làm con số khác nhau.

Để đánh giá review, cần xem:

- **Dòng thay đổi**: reviewer có bao nhiêu nội dung để đọc?
- **Dòng thay đổi có ý nghĩa**: bao nhiêu dòng chạm điều kiện, giá trị, hợp đồng và tác dụng phụ?
- **Phạm vi file/module**: thay đổi lan đến những thành phần nào?
- **Loại thay đổi**: formatting, refactor, hành vi, schema, dependency hoặc test?
- **Rủi ro nghiệp vụ**: thay đổi liên quan tiền, quyền, dữ liệu riêng tư hay tính nhất quán không?

Một PR 8 dòng sửa thuật toán phân quyền có thể cần review kỹ hơn PR 800 dòng chỉ chuẩn hóa khoảng trắng.

## 11. LOC không đo hiệu năng runtime

Mã ngắn không chắc chạy nhanh; mã dài không chắc chạy chậm.

Ví dụ, một lời gọi duy nhất tới CSDL có thể thực hiện truy vấn tốn nhiều giây, còn một vòng lặp Java dài hàng chục dòng có thể kết thúc nhanh với dữ liệu nhỏ. Một dòng gọi API bên ngoài có thể là điểm chậm nhất của toàn request.

Khi đánh giá hiệu năng, cần các phép đo phù hợp:

| Câu hỏi | Bằng chứng phù hợp hơn LOC |
| --- | --- |
| API phản hồi chậm ở đâu? | Profiling, distributed tracing và thời gian từng phụ thuộc. |
| Thuật toán tăng chi phí theo kích thước dữ liệu thế nào? | Phân tích độ phức tạp và benchmark với dữ liệu đại diện. |
| Hệ thống dùng nhiều bộ nhớ vì sao? | Allocation profile, heap analysis, số object/bytes giữ lại. |
| CSDL bị quá tải vì điều gì? | Query plan, số truy vấn, kết nối, thời gian chờ và throughput. |
| Thay đổi có cải thiện p95/p99 không? | Thử nghiệm có kiểm soát với tải và môi trường so sánh được. |

**LOC là metric kích thước của mã nguồn**, không phải số phép toán, latency, CPU time hay số byte cấp phát.

## 12. LOC không chứng minh mức độ kiểm thử

Một dự án có **tỷ lệ dòng test/production cao** chưa chắc có kiểm thử tốt. Một nghìn dòng test có thể lặp đi lặp lại một ca thành công, trong khi một kiểm thử ngắn tại ngưỡng có thể phát hiện lỗi nghiêm trọng.

Điều đáng quan sát:

- Các quy tắc và ranh giới quan trọng có **kết quả kỳ vọng cụ thể** không?
- Có dữ liệu **biên**, đầu vào không hợp lệ, lỗi phụ thuộc và tình huống đồng thời không?
- Các assertion có kiểm tra **tác dụng phụ**, không chỉ giá trị trả về không?
- Có thể chạy test ổn định, tái lập và hiểu thất bại không?
- Khi một quy tắc thay đổi, test có phát hiện sai lệch đúng chỗ không?

**Code coverage** và LOC cũng không đồng nghĩa. Coverage cho biết các phần code được thực thi theo định nghĩa công cụ, còn chất lượng oracle cần được xem riêng. Một test chạy qua nhánh có lỗi nhưng không assert đúng kết quả vẫn có thể để lỗi lọt.

## 13. Kết hợp chỉ số để tìm “hotspot” cần cải thiện

LOC có ích hơn khi kết hợp với bằng chứng thay đổi và lỗi:

~~~mermaid
flowchart TD
    A["Đo LOC đúng phạm vi"] --> D["Xác định vùng đáng chú ý"]
    B["Theo dõi số lần thay đổi / churn"] --> D
    C["Lỗi, test, độ phức tạp, trách nhiệm"] --> D
    D --> E{"Có khó khăn thực tế cần giải quyết?"}
    E -- "Không rõ" --> F["Tiếp tục quan sát"]
    E -- "Có" --> G["Review hành vi và ranh giới"]
    G --> H["Chọn thay đổi nhỏ, có test bảo vệ"]
    H --> I["Đo và đánh giá lại"]
~~~

Ví dụ, một lớp **lớn + thay đổi thường xuyên + thường gây lỗi** là ứng viên hợp lý để xem lại thiết kế. Nhưng nguyên nhân có thể là:

- Lớp gom nhiều trách nhiệm thay đổi độc lập.
- Quy tắc nghiệp vụ phức tạp không có tên rõ.
- Phụ thuộc hạ tầng gây lỗi khó kiểm soát.
- Test thiếu trường hợp biên hoặc tác dụng phụ.
- Nhóm thiếu hiểu biết về hợp đồng, không phải do kích thước đơn thuần.

Chỉ sau khi xác định nguyên nhân mới quyết định refactor, thêm test, tách module hoặc cải thiện tài liệu. **“Hotspot” là tín hiệu ưu tiên điều tra, không tự động là danh sách file cần xóa dòng.**

## 14. Ngưỡng cảnh báo nên được sử dụng thế nào?

Một nhóm có thể đặt ngưỡng để phát hiện method dài hoặc class lớn, nhưng cần phân biệt:

- **Ngưỡng gợi ý review:** vượt giới hạn thì người sửa giải thích vì sao cấu trúc hiện tại vẫn rõ.
- **Ngưỡng chặn build:** mọi vi phạm làm CI thất bại.
- **Ngưỡng xu hướng:** cảnh báo khi một thành phần tăng nhanh bất thường so với lịch sử của chính nó.

Với LOC, **ngưỡng gợi ý và ngưỡng theo xu hướng** thường dễ sử dụng để bắt đầu đánh giá. Nếu áp dụng ngưỡng chặn tuyệt đối, cần căn cứ theo dự án, ngoại lệ và cách xử lý mã hiện có; không nên coi một giá trị tùy ý là quy luật chất lượng.

### Vì sao tối ưu hóa theo LOC có thể phản tác dụng?

Nếu thưởng cho “giảm số dòng”, lập trình viên có thể:

- Nén nhiều điều kiện vào một biểu thức.
- Gộp các bước nghiệp vụ vào một hàm một dòng.
- Xóa kiểm tra lỗi hoặc logging có ích.
- Đưa logic sang cấu hình, code generation hoặc thư viện mà metric không đếm.
- Ngừng viết test hoặc tài liệu vì chúng làm số dòng tăng.

Hệ thống có thể **đạt chỉ số tốt hơn nhưng trở nên khó bảo trì hoặc kém an toàn hơn**. Đây là rủi ro khi biến một tín hiệu thành mục tiêu duy nhất.

Ngược lại, khuyến khích “viết nhiều mã hơn” cũng không chứng minh năng suất. LOC không phải thước đo độc lập để chấm điểm cá nhân hoặc so sánh năng suất của lập trình viên.

## 15. Một ví dụ đánh giá thay đổi bằng LOC và bằng chứng thực tế

Giả sử một PR sửa quy tắc chiết khấu với các thay đổi sau:

| Nhóm thay đổi trong PR | Dòng thêm/xóa giả định | Ý nghĩa cần review |
| --- | --- | --- |
| Sửa ngưỡng chiết khấu | +2 / -2 | Thay đổi hành vi tại ranh giới quan trọng. |
| Thêm dữ liệu test cho giá trị biên | +24 / -0 | Bổ sung bằng chứng mong muốn. |
| Bổ sung thông báo lỗi rõ hơn | +8 / -2 | Có thể tác động hợp đồng hoặc vận hành. |
| Formatter chạm 400 dòng không liên quan | +400 / -400 | Nhiễu diff lớn, không làm rõ hành vi. |

Không thể nói PR tốt hay xấu dựa vào **số dòng thêm ròng**. Nhưng bảng giúp đặt câu hỏi đúng: có thể **tách format-only** sang PR/commit riêng không? Test có đúng ngưỡng không? Thông báo lỗi có làm đổi hợp đồng không?

Nếu tách formatter, PR chức năng dễ review hơn dù **số LOC cuối cùng của codebase không đổi so với việc gộp cả hai**. Khả năng review là yếu tố chất lượng không thể hiện đầy đủ trong tổng LOC.

## 16. Lập báo cáo chỉ số có thể tái lập

Một báo cáo “module này có 8.500 dòng” là thiếu bối cảnh. Ít nhất nên ghi:

| Trường báo cáo | Ví dụ giá trị minh họa |
| --- | --- |
| **Đối tượng** | Module checkout, nhánh main, revision cố định. |
| **Thời điểm** | Commit được chọn và kỳ báo cáo cụ thể. |
| **Ngôn ngữ** | Java 17 production. |
| **Định nghĩa metric** | NCLOC theo công cụ đếm đã chốt. |
| **Công cụ/phiên bản** | Tên và phiên bản chính xác của công cụ tại kỳ đo. |
| **Include** | Các Java source viết tay trong vùng production. |
| **Exclude** | Test, generated code, vendored source và resource khác. |
| **So sánh** | Cùng phép đo ở revision trước. |
| **Bối cảnh thay đổi** | Thêm tính năng, tách module, nâng generator hoặc đổi formatter. |
| **Kết luận giới hạn** | Chỉ số mô tả kích thước; các nhận định chất lượng cần bằng chứng bổ sung. |

Có thể dùng công cụ đếm dòng hỗ trợ Java hoặc bộ phân tích mã tĩnh của dự án. Bất kể công cụ nào, **đừng trộn số của hai công cụ khi định nghĩa không giống nhau**.

### Một phép đếm đơn giản không thay thế metric theo ngôn ngữ

Ví dụ lệnh đếm dòng kiểu văn bản có thể trả số dòng file, nhưng không tự phân biệt:

- Dòng trống.
- Comment.
- Code và comment trên cùng dòng.
- Chuỗi nhiều dòng hoặc text block.
- Generated source.
- Câu lệnh logic.

Đếm byte, dòng văn bản và câu lệnh Java là **những phép đo khác nhau**. Chọn phép đo theo câu hỏi, thay vì sử dụng một con số dễ lấy nhất rồi gọi đó là chất lượng.

## 17. Cách review một class lớn

Khi thấy class có số dòng cao, không cần bắt đầu bằng việc “chia thành các class dưới 200 dòng”. Hãy trả lời những câu hỏi sau:

1. **Nó làm gì?** Có thể mô tả trách nhiệm trong một hoặc hai câu không?
2. **Vì sao các method cùng nằm ở đây?** Chúng thay đổi vì cùng một lý do hay do lịch sử tích tụ?
3. **Các phụ thuộc có rõ ràng không?** Class có dùng đồng thời CSDL, gửi email, tính tiền và HTTP mà không có ranh giới?
4. **Đường xử lý có khó theo dõi không?** Có lồng nhánh sâu hoặc điều kiện boolean khó hiểu?
5. **Dữ liệu và trạng thái có nhất quán không?** Có mutation khó dự đoán, tài nguyên không được giải phóng?
6. **Có lỗi thực tế hoặc chi phí sửa đổi cao không?** Thời gian tìm bug, số lỗi hồi quy và tần suất sửa nói gì?
7. **Refactor có làm rõ trách nhiệm không?** Hay chỉ tạo nhiều wrapper và tăng số lần nhảy file?
8. **Kiểm thử có đủ mạnh để bảo vệ hành vi không?** Có ca biên, thất bại và tác dụng phụ?

Nếu class là một bảng dữ liệu lớn được sinh từ schema, giải pháp có thể là **quản lý nguồn sinh** chứ không phải tách getter theo ngưỡng. Nếu class gom nhiều quy tắc thay đổi độc lập, tách theo trách nhiệm có thể hữu ích hơn việc cắt máy móc theo số dòng.

## 18. Đọc chỉ số trong pull request và trong dài hạn khác nhau

**Ở mức PR**, số dòng thay đổi có thể giúp lên kế hoạch review:

- PR lớn do format hay do logic?
- Đường đi nào có thay đổi hành vi?
- Có thể tách thay đổi cơ học và thay đổi chức năng không?
- Có test mới cho rủi ro của từng thay đổi không?

**Ở mức dài hạn**, LOC có thể hỗ trợ quan sát:

- Module nào tăng nhanh theo cùng định nghĩa đo?
- Tỷ lệ generated/test/production có thay đổi bất thường không?
- Có hotspot vừa lớn vừa được sửa thường xuyên không?
- Tổ chức lại module có cải thiện phạm vi hiểu và sửa thay vì chỉ chuyển dòng sang nơi khác không?

Hai mức phục vụ **quyết định khác nhau**. Không nên dùng một dashboard tổng LOC để quyết định merge một bản vá bảo mật, cũng không nên kết luận xu hướng dài hạn từ một PR riêng lẻ.

## 19. Những hiểu lầm phổ biến

| Nhận định thiếu cơ sở | Cách hiểu đúng hơn |
| --- | --- |
| “Ít LOC hơn nghĩa là code tốt hơn.” | Ít mã có thể tốt khi loại bỏ trùng lặp; cũng có thể xấu khi làm mất kiểm tra hoặc che ý định. |
| “Method hơn 50 dòng là sai.” | Đây có thể là ngưỡng gợi ý review, không phải bằng chứng về lỗi hoặc chất lượng. |
| “LOC tăng 20% nghĩa là technical debt tăng 20%.” | LOC có thể tăng vì tính năng, kiểm soát lỗi, test hoặc thay cách đếm; không suy ra nợ kỹ thuật tuyến tính. |
| “Test nhiều dòng hơn production nghĩa là an toàn.” | Chất lượng test phụ thuộc dữ liệu, expected, nhánh lỗi và tác dụng phụ được kiểm chứng. |
| “Hai đội làm cùng số LOC thì năng suất như nhau.” | Khác nhiệm vụ, độ khó, ngôn ngữ và chất lượng đầu ra; LOC không đủ để so sánh. |
| “PR nhỏ luôn ít rủi ro.” | Vài dòng thay quyền hoặc tiền có thể rất nhạy cảm. |
| “Generated code không tính là code nên có thể bỏ qua.” | Có thể tách khỏi metric mã viết tay, nhưng vẫn phải quản lý kiểm thử và rủi ro tích hợp. |
| “Đã có một chỉ số tổng nên không cần phân tích từng vùng.” | Phân bố, mục đích và lịch sử từng thành phần mới giúp giải thích. |

## 20. Checklist sử dụng LOC trong thực tế

Trước khi đưa LOC vào báo cáo hoặc đề xuất refactor, hãy kiểm tra:

1. **Mục tiêu đo rõ chưa?** Đang đo quy mô, xu hướng, phạm vi review hay tìm hotspot?
2. **Phạm vi đã khai báo chưa?** Method, class, module, production, test, generated, config?
3. **Định nghĩa phép đếm đã rõ chưa?** Physical LOC, NCLOC hay logical statements?
4. **Công cụ và cấu hình có nhất quán không?** Cùng phiên bản và bộ lọc?
5. **Có biến động do format hoặc di chuyển file không?**
6. **Có phân tích phân bố thay vì chỉ tổng không?**
7. **Có kết hợp churn, độ phức tạp, test và lỗi thực tế không?**
8. **Có xét mức độ quan trọng của hành vi không?** Đặc biệt với bảo mật, tiền và dữ liệu?
9. **Đề xuất thay đổi có làm mã dễ hiểu hơn không?** Hay chỉ giảm LOC một cách cơ học?
10. **Có thể chứng minh hành vi trước/sau bằng kiểm thử phù hợp không?**

Nếu thiếu câu trả lời cho nhiều mục, con số LOC nên được trình bày là **quan sát ban đầu**, chưa đủ cơ sở để kết luận hoặc đặt mục tiêu thưởng/phạt.

## 21. Bài tập tự luyện

### Tình huống A — Hai cách viết cùng hành vi

Một lập trình viên đổi một biểu thức 2 dòng thành nhiều bước 8 dòng, có tên biến rõ và test tại ngưỡng.

**Câu hỏi:** LOC tăng có nghĩa chất lượng giảm không?

**Gợi ý:** Không. Cần so sánh khả năng đọc, phạm vi trách nhiệm, kết quả kiểm thử và lý do các bước được đặt tên. Nhiều dòng hơn có thể làm ý định rõ hơn.

### Tình huống B — Nâng cấp generator

Sau khi nâng phiên bản client generator, báo cáo tổng LOC tăng từ 12.000 lên 18.000, trong đó mã viết tay không đổi.

**Câu hỏi:** Có thể kết luận module tăng 50% độ phức tạp nghiệp vụ không?

**Gợi ý:** Không. Cần tách generated code và xem thay đổi hợp đồng thực tế. Tổng LOC tăng là thật theo một phép đếm, nhưng kết luận về logic nghiệp vụ không được hỗ trợ.

### Tình huống C — Một PR chỉ sửa ngưỡng

PR sửa điều kiện áp phí ở một dòng, thêm ba test giá trị biên và đồng thời format lại 2.000 dòng khác.

**Câu hỏi:** Chỉ số dòng thay đổi giúp phát hiện điều gì, và nên làm gì để review an toàn?

**Gợi ý:** Diff lớn bất thường so với mục tiêu rất hẹp; nên tách format-only và thay đổi hành vi, review raw diff và giữ test độc lập.

### Tình huống D — Đặt ngưỡng tuyệt đối

Nhóm thiết lập “mọi method trên 40 dòng đều fail CI” cho cả Java production viết tay, code generated và một số trình phân tích cú pháp lớn.

**Câu hỏi:** Nguy cơ của chính sách này là gì?

**Gợi ý:** Ngưỡng không phân biệt loại mã và trách nhiệm, có thể khuyến khích chia method máy móc và tăng gián tiếp. Dùng scope/ngoại lệ hợp lý, kết hợp review cấu trúc và nguy cơ thật.

### Tình huống E — Mã giảm nhưng lỗi tăng

Một refactor xóa 300 dòng bằng cách dùng một helper chung; sau đó nhiều ca sử dụng bị lỗi vì helper giả định mọi luồng có cùng quy tắc.

**Câu hỏi:** Vì sao LOC giảm chưa chứng minh refactor thành công?

**Gợi ý:** Đã có khả năng gộp sai các khái niệm khác nhau. Cần đánh giá hợp đồng từng luồng, mức ghép nối mới, test và lỗi hồi quy.

### Tình huống F — So sánh hai nhóm

Nhóm A duy trì 20.000 dòng Java, nhóm B duy trì 4.000 dòng Kotlin. Quản lý kết luận A làm việc năng suất gấp năm.

**Câu hỏi:** Những dữ liệu nào đang thiếu?

**Gợi ý:** Khác ngôn ngữ, loại sản phẩm, mức độ sinh mã, nhiệm vụ, rủi ro, tính năng được giao và chất lượng kết quả. LOC không đại diện trực tiếp cho giá trị hoặc năng suất của cá nhân/nhóm.

---

**Ghi nhớ:** **Số dòng mã có ý nghĩa khi phạm vi, định nghĩa và mục tiêu đo được nói rõ.** LOC có thể giúp nhận diện quy mô, xu hướng, chi phí review và vùng đáng điều tra; nó không thay thế việc xem **tính đúng đắn, độ phức tạp, phụ thuộc, kiểm thử và rủi ro nghiệp vụ**. Hãy dùng LOC như một **tín hiệu đặt câu hỏi**, không phải đích đến buộc lập trình viên phải viết ít hay nhiều dòng hơn.
