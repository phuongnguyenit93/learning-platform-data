# Nợ kỹ thuật là gì và khác khuyết điểm thông thường như thế nào?

Một hệ thống có thể **đang chạy đúng** nhưng mỗi lần sửa một quy tắc lại phải thay đổi sáu nơi. Ngược lại, một hàm rất ngắn, rõ ràng và dễ đọc vẫn có thể chứa lỗi ở đúng một dấu so sánh. Cả hai đều ảnh hưởng đến chất lượng mã, nhưng chúng **không phải cùng một vấn đề**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Nợ kỹ thuật**, cần phân biệt:

- **Khuyết điểm/lỗi (defect, bug):** phần mềm đang vi phạm một yêu cầu hoặc hành vi được kỳ vọng.
- **Nợ kỹ thuật (technical debt):** một lựa chọn hoặc cấu trúc kỹ thuật đang tạo ra **chi phí, rủi ro hoặc hạn chế khi duy trì và thay đổi hệ thống trong tương lai**, so với một phương án phù hợp hơn.
- **Đánh đổi thiết kế:** lựa chọn có chi phí và lợi ích, nhưng **không mặc nhiên là nợ kỹ thuật**.
- **Thiếu tính năng:** nhu cầu chưa được triển khai; không tự động là bug hay nợ kỹ thuật.

Mục tiêu của bài học là nhận diện đúng loại vấn đề, hiểu **“gốc” và “lãi”** của nợ kỹ thuật, và quyết định lúc nào nên trả nợ mà không đánh đồng mọi mã cũ hoặc mọi việc cần làm với nợ.

## 1. Định nghĩa nợ kỹ thuật trong ngữ cảnh chất lượng mã

Nợ kỹ thuật là cách mô tả một **gánh nặng kỹ thuật được mang từ hiện tại sang những thay đổi sau này**. Gánh nặng có thể đến từ việc chọn giải pháp nhanh để đáp ứng thời hạn, thiếu hiểu biết ở thời điểm thiết kế, những thay đổi môi trường hoặc việc chưa cập nhật cấu trúc khi nhu cầu phát triển.

Ví dụ:

- Một quy tắc tính phí bị **sao chép** ở ba luồng; đổi mức phí phải nhớ sửa cả ba.
- Mọi ca kiểm thử cần khởi động toàn bộ hệ thống; việc kiểm chứng thay đổi nhỏ rất chậm và khó cô lập lỗi.
- Một module nghiệp vụ phụ thuộc trực tiếp vào SDK của nhà cung cấp bên ngoài; đổi nhà cung cấp kéo theo chỉnh sửa lan rộng.
- Không có ranh giới transaction rõ ràng; mỗi tính năng ghi nhiều bảng lại phải tự xử lý logic khôi phục phức tạp.
- Một đoạn mã đã từng phù hợp, nhưng nhu cầu mới làm giao diện và cấu trúc của nó trở thành điểm cản trở thay đổi.

Điểm chung không chỉ là “mã chưa đẹp” mà là **hệ quả thực tế hoặc có cơ sở đối với việc sửa, mở rộng, kiểm thử, vận hành hay kiểm soát rủi ro**.

Một định nghĩa làm việc hữu ích:

> **Nợ kỹ thuật là quyết định hoặc tình trạng kỹ thuật khiến những công việc cần thực hiện về sau đắt hơn, chậm hơn hoặc rủi ro hơn, và có một hướng cải thiện được nhận diện đủ rõ.**

Định nghĩa này không đòi hỏi mọi khoản nợ đều phải bắt đầu bằng một lựa chọn có chủ đích. Nhưng nếu không chỉ ra được **gánh nặng** và **việc cải thiện sẽ giải quyết điều gì**, nhãn “nợ kỹ thuật” rất dễ trở thành lời phê bình mơ hồ.

## 2. Vì sao gọi là “nợ”?

Ẩn dụ nợ giúp phân biệt hai loại chi phí:

| Khái niệm trong ẩn dụ | Ý nghĩa đối với phần mềm | Ví dụ |
| --- | --- | --- |
| **Gốc nợ (principal)** | Công sức cần bỏ ra để loại bỏ hoặc giảm gánh nặng kỹ thuật đang tồn tại. | Hợp nhất ba bản sao quy tắc phí và bổ sung test tương đương. |
| **Lãi nợ (interest)** | Chi phí hoặc rủi ro tăng thêm mỗi khi tiếp tục phát triển, vận hành và thay đổi trên cấu trúc đó. | Mỗi lần đổi phí phải sửa ba nơi, review lâu hơn và dễ quên một nơi. |
| **Trả nợ** | Cải thiện có mục tiêu nhằm giảm gánh nặng trong tương lai. | Tách một chính sách dùng chung và chuyển các bên gọi qua chính sách ấy. |
| **Tiếp tục mang nợ** | Giữ nguyên thiết kế hiện tại trong một thời gian, với hệ quả được chấp nhận. | Chưa refactor vì nhánh tích hợp cũ sẽ ngừng sử dụng trong một tháng. |

Đây là **ẩn dụ giúp thảo luận**, không phải công thức tài chính chính xác. “Lãi” không nhất thiết tăng đều theo ngày và không phải khoản nợ nào cũng có thể quy đổi chắc chắn thành tiền.

Đặc biệt, **nợ kỹ thuật không phải luôn là lỗi đạo đức hoặc quyết định thiếu chuyên nghiệp**. Có trường hợp nhóm chủ động chọn giải pháp giới hạn để kiểm chứng sản phẩm sớm, ghi nhận tác động và lập kế hoạch cải thiện khi nhu cầu được xác nhận.

## 3. Khác biệt cốt lõi: bug nói về điều đang sai, nợ nói về chi phí thay đổi

Hãy so sánh theo tiêu chí:

| Tiêu chí | Lỗi/khuyết điểm thông thường | Nợ kỹ thuật |
| --- | --- | --- |
| **Câu hỏi chính** | Phần mềm **đang** làm gì sai so với hợp đồng? | Cấu trúc hoặc quyết định nào khiến **việc tiếp theo** tốn kém/rủi ro? |
| **Dấu hiệu trực tiếp** | Có đầu vào hoặc bối cảnh gây ra kết quả không đúng. | Có công việc lặp, thay đổi lan rộng, khó kiểm thử hoặc khó vận hành có thể chỉ ra. |
| **Cần có lỗi chức năng hiện tại?** | Thường có sự sai lệch hiện tại so với yêu cầu. | **Không bắt buộc**; hệ thống có thể vẫn chạy đúng. |
| **Cách khắc phục chính** | Sửa kết quả, điều kiện, hợp đồng hoặc tác dụng phụ bị sai. | Cải thiện cấu trúc, kiểm thử, phụ thuộc hoặc quy trình gây gánh nặng. |
| **Bằng chứng xác nhận** | Test thất bại trước sửa và thành công sau sửa, hoặc dữ liệu vận hành chứng minh lỗi. | Thay đổi trở nên ít lan rộng hơn, dễ kiểm chứng hơn, giảm lỗi lặp hoặc giảm chi phí có cơ sở. |
| **Ưu tiên** | Dựa trên mức ảnh hưởng, độ nghiêm trọng, khả năng tái hiện và rủi ro. | Dựa trên “lãi” đang trả, xác suất cần thay đổi, mức rủi ro và chi phí cải thiện. |
| **Có thể cùng xuất hiện?** | **Có.** | **Có.** |

Ví dụ một hàm tính phí dùng toán tử **>** thay vì **>=** ở ngưỡng miễn phí: đây là **bug** nếu hợp đồng quy định “từ ngưỡng trở lên”.

Ví dụ cùng công thức phí được sao chép ở năm luồng nhưng hiện đều tính đúng: đây **có thể là nợ kỹ thuật**, vì một thay đổi chính sách phải được triển khai ở nhiều nơi. Chưa có bug nhưng đã tồn tại gánh nặng thay đổi và nguy cơ bỏ sót.

Khi một bản sao không được cập nhật và tính sai phí, **bug và nợ xuất hiện đồng thời**. Sửa số phí sai giải quyết triệu chứng hiện tại; loại bỏ việc sao chép có thể giảm nguy cơ lỗi tương tự tái diễn.

## 4. Không phải mọi khuyết điểm đều là nợ kỹ thuật

“Khuyết điểm” trong ngôn ngữ đời thường có thể bao gồm nhiều dạng: sai hành vi, đặt tên chưa tốt, thiếu test, thiết kế khó sửa hoặc tài liệu lỗi thời. Trong công việc kỹ thuật, nên **phân loại theo câu hỏi cần giải quyết**.

| Tình huống | Phân loại ban đầu hợp lý | Vì sao |
| --- | --- | --- |
| Phí giao hàng tại đúng ngưỡng 500.000 VND bị tính sai | **Bug** | Có kết quả trái quy tắc hiện hành. |
| Cùng quy tắc phí nằm ở ba file, hiện vẫn tính đúng | **Nợ kỹ thuật tiềm năng** | Mỗi lần đổi phí phải sửa nhiều nơi; cần xác minh các luồng có thực sự cùng chính sách. |
| Một tên biến nội bộ khó hiểu ở phương thức ít thay đổi | **Vấn đề dễ đọc / cải thiện nhỏ**, chưa chắc là nợ đáng theo dõi | Chưa thấy chi phí tương lai đủ đáng kể để cần quản trị như một khoản nợ. |
| Hệ thống chưa hỗ trợ xuất PDF dù chưa từng cam kết | **Thiếu tính năng** | Chưa phải hành vi sai hoặc một gánh nặng kiến trúc. |
| Dùng một thư viện ổn định, được hỗ trợ, có hợp đồng phù hợp | **Đánh đổi kỹ thuật bình thường** | Sự tồn tại của phụ thuộc không tự tạo nợ. |
| Bỏ test cho luồng hoàn tiền để kịp phát hành, khiến mỗi sửa đổi phải test tay tốn thời gian | **Nợ kiểm thử; có thể kèm rủi ro chất lượng hiện tại** | Có gánh nặng xác minh rõ và nguy cơ hồi quy. |
| Một lỗ hổng cho phép người khác đọc dữ liệu riêng tư | **Vấn đề bảo mật cần xử lý theo mức rủi ro** | Không được giảm mức ưu tiên chỉ vì gọi là “nợ”. |
| Một thư viện cũ không còn được vá, ngăn nâng nền tảng | **Nợ phụ thuộc, có thể kèm lỗ hổng bảo mật** | Vừa làm thay đổi khó, vừa có thể tạo rủi ro hiện tại. |

**Không dùng “technical debt” để làm nhẹ đi lỗi bảo mật, thất thoát tiền hoặc vi phạm dữ liệu.** Những vấn đề có tác động hiện tại cần được đánh giá và xử lý theo mức độ nghiêm trọng thực tế, dù nguyên nhân sâu xa có liên quan đến nợ kỹ thuật.

## 5. Ví dụ Java: mã chạy đúng nhưng tích lũy gánh nặng

Giả sử hai luồng **web** và **đối tác** đều sử dụng **cùng chính sách** phí giao hàng:

- Tổng tiền hàng không được âm.
- Đơn từ **500.000 VND** trở lên miễn phí giao hàng tiêu chuẩn.
- Dưới ngưỡng, phí tiêu chuẩn là **30.000 VND**.
- Giao nhanh cộng **20.000 VND** ở mọi trường hợp.

Một thiết kế ban đầu sao chép công thức ở hai phương thức:

~~~java
public final class LegacyShippingFees {
    private LegacyShippingFees() {
    }

    public static long forWeb(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }

        long base = subtotalVnd >= 500_000L ? 0L : 30_000L;
        return base + (express ? 20_000L : 0L);
    }

    public static long forPartner(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }

        long base = subtotalVnd >= 500_000L ? 0L : 30_000L;
        return base + (express ? 20_000L : 0L);
    }
}
~~~

Hai phương thức này đều **đúng** theo chính sách giả định. Nếu gọi với **500.000 VND, giao tiêu chuẩn**, cả hai trả **0**.

Vấn đề nằm ở **cấu trúc phụ thuộc của thay đổi**. Khi doanh nghiệp đổi ngưỡng, người sửa phải nhớ hai nơi. Nếu có thêm luồng mobile và batch, số nơi cần giữ đồng bộ có thể tăng.

Vì sao đây là một ứng viên nợ kỹ thuật chứ không phải chỉ một sở thích code style?

1. Hai luồng **được xác nhận dùng cùng quy tắc**.
2. Quy tắc có khả năng thay đổi theo chính sách sản phẩm.
3. Mỗi lần đổi có **chi phí chỉnh sửa và review lặp**.
4. Nếu bỏ sót một luồng, cùng một đơn có thể bị tính phí khác nhau.
5. Có phương án cụ thể để tập trung chính sách mà không trộn các trách nhiệm không liên quan.

Nếu hai luồng có **chính sách thực sự độc lập**, việc tách riêng chưa chắc là nợ. Hợp nhất sai những quy tắc chỉ “trông giống nhau” có thể tạo ghép nối mới nguy hiểm hơn.

## 6. Từ nợ kỹ thuật đến bug: một thay đổi có thể làm lộ rủi ro

Sau một thời gian, yêu cầu mới được phê duyệt: ngưỡng miễn phí tiêu chuẩn đổi thành **600.000 VND** cho **cả hai luồng**.

Developer sửa web nhưng quên đối tác. Giờ mã ở hai nơi có dạng:

~~~java
// Web: đã cập nhật theo chính sách mới.
long webBase = subtotalVnd >= 600_000L ? 0L : 30_000L;

// Đối tác: vẫn dùng ngưỡng cũ.
long partnerBase = subtotalVnd >= 500_000L ? 0L : 30_000L;
~~~

Với tổng tiền **550.000 VND** và giao tiêu chuẩn:

| Luồng | Kết quả thực tế | Kỳ vọng theo chính sách mới | Đánh giá |
| --- | ---: | ---: | --- |
| Web | 30.000 | 30.000 | Đúng. |
| Đối tác | 0 | 30.000 | **Sai: bug.** |

Tại thời điểm này:

- **Bug:** luồng đối tác trả sai phí theo hợp đồng mới.
- **Nợ kỹ thuật nền:** một quy tắc dùng chung có nhiều bản sao cần duy trì.
- **Tác động của “lãi nợ”:** tăng công sức sửa, tăng nguy cơ quên một nơi, tăng kiểm thử hồi quy cho mỗi thay đổi.

Phân biệt hai việc giúp tránh hai thái cực:

- **Chỉ sửa bug:** đổi ngưỡng trong luồng đối tác thì tính phí đúng trở lại, nhưng cấu trúc sao chép vẫn còn.
- **Chỉ refactor:** gom hai phương thức vào một helper nhưng để ngưỡng cũ thì code có thể gọn hơn mà **vẫn sai nghiệp vụ**.

Cả **tính đúng hiện tại** và **khả năng thay đổi tương lai** đều cần được quan tâm, nhưng bằng chứng hoàn thành của chúng khác nhau.

## 7. Trả nợ bằng cách đưa quy tắc đến một nơi sở hữu rõ

Khi có cơ sở rằng web và đối tác thực sự dùng cùng chính sách, ta có thể đưa phép tính về một thành phần:

~~~java
public final class ShippingFeePolicy {
    private static final long FREE_STANDARD_THRESHOLD = 600_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_SURCHARGE = 20_000L;

    private ShippingFeePolicy() {
    }

    public static long calculate(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative subtotal");
        }

        long standardFee =
                subtotalVnd >= FREE_STANDARD_THRESHOLD
                        ? 0L
                        : STANDARD_FEE;

        return standardFee + (express ? EXPRESS_SURCHARGE : 0L);
    }
}
~~~

Hai luồng giờ gọi cùng một hợp đồng:

~~~java
long webFee = ShippingFeePolicy.calculate(subtotalVnd, express);
long partnerFee = ShippingFeePolicy.calculate(subtotalVnd, express);
~~~

Đây là ví dụ đơn giản. Trong hệ thống thực, cần xác định nơi sở hữu chính sách, đơn vị tiền tệ, cấu hình theo thời điểm hiệu lực và các điều kiện khác trước khi hợp nhất.

**Mục tiêu trả nợ không phải chỉ giảm dòng mã.** Giá trị dự kiến là:

- Một thay đổi chính sách được thực hiện ở một nơi chịu trách nhiệm.
- Hai luồng sử dụng cùng điều kiện và cách tính.
- Test biên cho chính sách được viết một cách có chủ đích.
- Người bảo trì biết nơi tìm và sửa quy tắc trong những thay đổi tiếp theo.

Tạo thêm nhiều lớp **FeeFacade → FeeManager → FeeProcessor → ShippingFeePolicy** chỉ để chuyển lời gọi có thể làm tăng nợ do gián tiếp không cần thiết. Cần cải thiện **chi phí thay đổi**, không chạy theo số lớp hay số dòng thấp nhất.

## 8. Kiểm thử cần chứng minh hai việc khác nhau

Một bộ kiểm thử đủ rõ cần bảo vệ:

1. **Kết quả đúng theo quy tắc hiện hành**: tổng dưới ngưỡng phải trả phí, tại ngưỡng phải miễn phí tiêu chuẩn.
2. **Các luồng dùng chung chính sách**: web và đối tác không tự tính theo công thức khác nhau khi hợp đồng yêu cầu giống nhau.

Ví dụ JUnit 5 cho ShippingFeePolicy:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    @Test
    void justBelowThresholdPaysStandardFee() {
        assertEquals(30_000L,
                ShippingFeePolicy.calculate(599_999L, false));
    }

    @Test
    void atThresholdStandardShippingIsFree() {
        assertEquals(0L,
                ShippingFeePolicy.calculate(600_000L, false));
    }

    @Test
    void expressStillHasSurchargeAtThreshold() {
        assertEquals(20_000L,
                ShippingFeePolicy.calculate(600_000L, true));
    }

    @Test
    void expressBelowThresholdPaysBothCharges() {
        assertEquals(50_000L,
                ShippingFeePolicy.calculate(599_999L, true));
    }

    @Test
    void invalidSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeePolicy.calculate(-1L, false));
    }
}
~~~

Các kết quả **30.000, 0, 20.000, 50.000** được suy từ đặc tả, **không lấy từ chính hàm đang kiểm thử**.

Test của ShippingFeePolicy chưa chứng minh mọi caller đã chuyển sang dùng nó. Trong hệ thống thật, cần test tích hợp hoặc kiểm tra đường gọi của **web** và **đối tác**, đồng thời bảo vệ các hợp đồng bên ngoài như HTTP response hoặc dữ liệu được ghi.

### Nên xử lý bug và refactor theo thứ tự nào?

Tùy độ rủi ro và nhu cầu phát hành:

- Khi có lỗi đang gây hại: ưu tiên **bản vá nhỏ kèm test tái hiện**, rồi trả nợ ở một thay đổi riêng nếu hợp lý.
- Khi refactor đủ nhỏ và có bằng chứng tốt: có thể thực hiện **cơ học giữ hành vi** trước, sau đó sửa quy tắc và test mới.
- Khi cần gấp trên nhánh bảo trì: tránh ép đợt refactor diện rộng vào bản vá khẩn cấp.
- Với dữ liệu, giao dịch và phân quyền: yêu cầu kiểm thử tích hợp và quy trình triển khai phù hợp, không chỉ unit test.

**Một thay đổi có thể giải quyết cả bug và nợ**, nhưng trong review vẫn nên chỉ rõ phần nào sửa kết quả hiện tại, phần nào giảm gánh nặng cấu trúc.

## 9. Nợ kỹ thuật có thể được tạo ra có chủ đích hoặc vô tình

Một cách phân loại hữu ích dựa trên mức độ hiểu biết và thái độ chấp nhận đánh đổi:

| Bối cảnh | Ví dụ | Cách đánh giá |
| --- | --- | --- |
| **Có chủ đích, cân nhắc** | Dùng giải pháp giản lược cho thử nghiệm sản phẩm 2 tuần, ghi rõ khi nào phải nâng cấp. | Có thể là khoản nợ được chấp nhận hợp lý, cần biết phạm vi và thời điểm xem lại. |
| **Có chủ đích nhưng thiếu kiểm soát** | Bỏ tất cả test để kịp deadline dù tính năng liên quan đến tiền và không có kế hoạch bảo vệ. | Rủi ro cao; không thể xem “có chủ đích” là đủ biện minh. |
| **Vô tình do chưa hiểu rõ** | Sao chép quy tắc trước khi biết chúng cần được quản lý chung. | Cần cải thiện khi hiểu được hợp đồng và tác động. |
| **Phát sinh khi bối cảnh thay đổi** | Thiết kế cho một nhà cung cấp trở nên khó mở rộng khi phải tích hợp nhiều nhà cung cấp. | Không nhất thiết là quyết định sai ở thời điểm ban đầu. |
| **Tích lũy vì bỏ qua bảo trì** | Lặp đi lặp lại nâng thư viện chậm, workarounds tăng và thay đổi nền tảng ngày càng khó. | Cần làm rõ “lãi” và rủi ro tiếp tục mang nợ. |

Tránh phân loại nợ thành **tội lỗi của người viết mã trước**. Một thiết kế phù hợp tại thời điểm trước có thể trở thành gánh nặng khi tải, quy tắc hoặc tổ chức thay đổi.

Điều cần xem là **hệ thống hiện tại cần gì**, những ràng buộc cũ còn đúng không và có phương án cải thiện hợp lý hay không.

## 10. Nợ kỹ thuật không chỉ là mã nguồn

Những gánh nặng có thể xuất hiện ở nhiều lớp của hệ thống:

| Dạng nợ | Dấu hiệu thường gặp | “Lãi” có thể trả |
| --- | --- | --- |
| **Nợ mã nguồn / cấu trúc** | Trùng quy tắc, lớp nhiều trách nhiệm, phụ thuộc vòng. | Sửa một yêu cầu phải chạm nhiều nơi, dễ gây lỗi hồi quy. |
| **Nợ kiến trúc** | Ranh giới module mờ, tích hợp bên ngoài lan vào nghiệp vụ. | Thêm tính năng hoặc thay nhà cung cấp cần thay đổi diện rộng. |
| **Nợ kiểm thử** | Thiếu test ở các điểm rủi ro, fixture khó tạo, suite chậm hoặc không ổn định. | Tăng thời gian xác minh, sợ refactor, lỗi lọt qua. |
| **Nợ dữ liệu** | Schema khó mở rộng, migration thiếu kế hoạch, định nghĩa dữ liệu thiếu thống nhất. | Phải chuyển đổi thủ công, tăng rủi ro dữ liệu sai khi thêm chức năng. |
| **Nợ vận hành** | Thiếu observability, runbook lỗi thời, triển khai và khôi phục thủ công. | Mất thời gian điều tra, phục hồi chậm khi sự cố. |
| **Nợ phụ thuộc** | Thư viện hoặc nền tảng lỗi thời, không còn được bảo trì. | Nâng cấp bị chặn, nguy cơ tương thích và bảo mật tăng. |
| **Nợ tài liệu/hợp đồng** | API thay đổi mà ví dụ và hướng dẫn không cập nhật. | Tích hợp sai, cần hỏi chuyên gia, khó chuyển giao. |

Một dòng **TODO** không tự động đại diện cho khoản nợ đáng ưu tiên. Ngược lại, nhiều khoản nợ tồn tại **không có TODO nào**. Cần dựa vào gánh nặng và bằng chứng thực tế.

Đặc biệt, một lỗ hổng hoặc một tình trạng không đáp ứng yêu cầu pháp lý/bảo mật phải được quản trị theo **mức độ tác động hiện tại**, không chờ tới một “đợt trả nợ kỹ thuật” định kỳ.

## 11. Hiểu “lãi nợ” một cách có cơ sở

Trong ví dụ sao chép quy tắc, chi phí lặp có thể xuất hiện ở:

- **Thời gian tìm kiếm:** xác định tất cả bản sao cần thay.
- **Thời gian triển khai:** chỉnh nhiều nhánh và xử lý biến thể.
- **Thời gian review:** so sánh để chắc chắn mọi luồng nhất quán.
- **Thời gian kiểm thử:** chạy và đánh giá kết quả nhiều đường gọi.
- **Rủi ro bỏ sót:** lỗi lọt production gây thêm công sửa và xử lý khách hàng.
- **Khó thay đổi lớn hơn:** khi bổ sung kênh mới, không biết nên dùng bản sao nào.

Nhưng không được tự kết luận “năm bản sao nghĩa là lãi gấp năm”. Chi phí còn phụ thuộc độ quen thuộc của nhóm, công cụ, tần suất đổi chính sách, độ khác biệt giữa các luồng và chất lượng test.

Có thể ghi nhận bằng chứng như:

| Dấu hiệu | Cách thu thập hợp lý | Điều chưa thể kết luận |
| --- | --- | --- |
| Một thay đổi phí phải sửa bốn file | Xem PR/diff của các lần đổi trước. | Chưa biết cả bốn file đều là nợ; có thể thuộc bốn trách nhiệm hợp lệ. |
| Mỗi lần đổi chính sách mất 2 ngày review | So sánh lịch sử PR cùng loại và nguyên nhân chờ. | Không thể quy toàn bộ 2 ngày cho trùng lặp mã. |
| Có ba lỗi bỏ sót cập nhật ở các kênh | Liên kết bug với thay đổi và điểm phát sinh. | Không chắc mọi lỗi đều do một nguyên nhân. |
| Test tích hợp mất 40 phút và hay thất bại ngẫu nhiên | Quan sát thời gian, flaky rate và log. | Không nhất thiết rút ngắn bằng mọi giá nếu test bảo vệ rủi ro quan trọng. |

**Chứng minh nợ kỹ thuật mạnh nhất** là chỉ ra được một quan hệ có thể kiểm tra: **cấu trúc X khiến loại thay đổi Y tốn công hoặc rủi ro hơn; cải thiện Z được kỳ vọng giảm gánh nặng đó**.

## 12. “Trả gốc” không bảo đảm “tiết kiệm lãi” ngay lập tức

Một refactor có thể tốn công hôm nay nhưng chỉ mang lợi ích khi có thay đổi tương tự trong tương lai. Nếu hệ thống sắp bị thay thế, lợi ích dự kiến có thể thấp.

Hãy xét hai tình huống:

**Trường hợp A:** Một service sẽ liên tục thêm chính sách mới mỗi tháng. Cùng một chính sách đang bị sao chép ở nhiều luồng. Hợp nhất hợp đồng có thể giảm chi phí và nguy cơ trong nhiều lần thay đổi.

**Trường hợp B:** Một ứng dụng nội bộ nhỏ sẽ ngừng dùng trong vài tuần. Có một lớp dài nhưng ổn định, không có thay đổi dự kiến và không chứa lỗ hổng hay lỗi nghiêm trọng. Một đợt refactor lớn có thể không tạo đủ giá trị so với chi phí và rủi ro triển khai.

Vì vậy, **không phải mọi khoản nợ đều phải trả ngay**. Quyết định cần xem thời gian sử dụng còn lại, nhu cầu dự kiến, hậu quả lỗi, công sức trả nợ và mức chắc chắn của bằng chứng.

Tuy nhiên, **nợ có rủi ro hiện tại cao** (chẳng hạn tình trạng có thể làm mất dữ liệu hoặc kiểm soát quyền không đủ) không nên bị trì hoãn chỉ vì khó ước lượng lợi ích của refactor. Khi ấy cần quản trị rủi ro trực tiếp.

## 13. Ưu tiên trả nợ dựa trên hậu quả, không dựa trên độ “xấu”

Một backlog nợ kỹ thuật có thể được sắp xếp theo:

1. **Rủi ro hiện tại:** có nguy cơ bảo mật, mất dữ liệu, gián đoạn hay tác động lớn tới khách hàng không?
2. **Tần suất chạm vào:** thành phần có được sửa thường xuyên không, hay gần như không đổi?
3. **Mức cản trở:** một thay đổi bình thường phải vòng qua bao nhiêu bước, file hoặc nhóm?
4. **Khả năng gây lỗi hồi quy:** có lịch sử bỏ sót, khó test hoặc khó đối soát không?
5. **Công sức trả nợ:** cải thiện cần bao nhiêu công, có thể chia nhỏ không?
6. **Mức chắc chắn:** có biết rõ nguyên nhân và giải pháp, hay chỉ đang nghi ngờ?
7. **Thời hạn/điểm kích hoạt:** sắp có tính năng phụ thuộc vào khu vực đó hay đợt nâng cấp bắt buộc?
8. **Ngân sách kiểm chứng:** có test, công cụ và phương án rollback phù hợp không?

Một ma trận định tính:

| Nợ kỹ thuật | Tần suất thay đổi | Hậu quả khi sai | Chi phí cải thiện | Hướng ưu tiên |
| --- | --- | --- | --- | --- |
| Chính sách giá bị sao chép ở nhiều kênh đang phát triển | Cao | Cao | Vừa | **Đáng xử lý sớm**, nhất là trước đợt đổi giá tiếp theo. |
| Test hoàn tiền thiếu ca gửi trùng | Vừa | Rất cao | Vừa | **Ưu tiên bảo vệ rủi ro**, không đợi chỉ số code style. |
| Tên biến chưa đẹp ở helper ít thay đổi | Thấp | Thấp | Thấp | Cải thiện khi chạm đúng vùng, không cần dự án riêng. |
| Tầng tương thích cũ sẽ bỏ trong 2 tuần | Thấp | Thấp nếu đã cô lập | Cao | Có thể trì hoãn refactor, tập trung kế hoạch loại bỏ an toàn. |
| Thư viện không còn được vá trong luồng xử lý nhạy cảm | Tùy | Có thể rất cao | Vừa/cao | Đánh giá bảo mật và hạn nâng cấp; không chỉ coi là việc dọn mã. |

Bảng này là **mô hình minh họa**, không phải điểm số cố định cho mọi tổ chức.

## 14. Ghi một khoản nợ đủ cụ thể để có thể hành động

Một issue ghi “code xấu, cần refactor” chưa giúp nhóm quyết định. Một mô tả có ích nên nêu **vấn đề, bằng chứng, tác động, hướng giải quyết, người sở hữu và thời điểm xem lại**.

Ví dụ **phiếu nợ kỹ thuật**:

~~~markdown
## Nợ kỹ thuật: Quy tắc phí giao hàng bị sao chép

**Phạm vi:** Web checkout và partner checkout.
**Owner:** Nhóm chịu trách nhiệm chính sách phí.
**Tình trạng:** Chưa xử lý; các luồng phải dùng cùng hợp đồng.

**Bằng chứng:**
- Cùng công thức và ngưỡng nằm tại hai đường gọi.
- Một thay đổi ngưỡng gần đây đã bỏ sót partner checkout.
- Test hiện có chưa kiểm tra tính nhất quán giữa các luồng.

**Hệ quả:**
- Thay đổi chính sách phải sửa nhiều nơi.
- Tăng nguy cơ tính phí khác nhau cho cùng điều kiện.

**Hướng cải thiện:**
- Xác nhận hai luồng vẫn dùng chung một chính sách.
- Đặt phép tính trong ShippingFeePolicy.
- Chuyển caller và bổ sung test cho ngưỡng, phụ phí và hai đường tích hợp.

**Tiêu chí hoàn tất:**
- Các luồng sử dụng một nơi sở hữu quy tắc.
- Test tại 599.999/600.000 VND và với giao nhanh đạt.
- Không đổi ngoài ý muốn hợp đồng API hoặc tác dụng phụ.

**Điểm xem lại:** Trước lần thay đổi chính sách phí tiếp theo.
~~~

Một phiếu tốt **không cần ước lượng chính xác “lãi mỗi tháng”** khi chưa có dữ liệu. Có thể dùng mô tả định tính và bổ sung quan sát dần.

Đừng biến backlog thành nơi chứa mọi TODO và mọi ý tưởng làm đẹp mã. Nếu mọi việc đều mang nhãn “nợ”, nhóm sẽ khó phân biệt **nguy cơ thực tế** và **sở thích cá nhân**.

## 15. Làm thế nào xác minh một khoản nợ đã được giảm?

Không nên chỉ ghi “đã xóa 300 dòng nên nợ đã hết”. Giảm dòng có thể làm mã tốt hơn, cũng có thể chuyển logic sang nơi khó tìm hoặc bỏ mất kiểm tra quan trọng.

Các tiêu chí có ý nghĩa hơn:

| Mục tiêu cải thiện | Bằng chứng phù hợp |
| --- | --- |
| Giảm sửa trùng lặp | Một thay đổi quy tắc chỉ cần sửa nơi sở hữu chính; các caller không tự có bản sao. |
| Giảm rủi ro hồi quy | Test trước/sau bảo vệ những đường quan trọng; ca đã gây lỗi không tái xuất hiện. |
| Tăng khả năng hiểu | Người review xác định rõ nơi quy tắc nằm và đường đi tới tác dụng phụ. |
| Giảm thời gian xác minh | Thời gian test/chạy thử được đo theo điều kiện tương đương và giảm hợp lý. |
| Giảm phụ thuộc hạ tầng | SDK nhà cung cấp được cách ly, phần nghiệp vụ không cần biết chi tiết giao thức. |
| Giảm nợ vận hành | Runbook và tín hiệu quan sát giúp giải quyết sự cố nhanh, được thử theo quy trình. |

Nếu mục tiêu chưa có bằng chứng, hãy ghi “đã refactor” thay vì tự khẳng định “đã giảm 80% nợ kỹ thuật”.

**Nợ kỹ thuật không có đơn vị chuẩn chung** giống mét hay giây. LOC, số lớp, độ phức tạp, churn và thời gian review chỉ là những **tín hiệu**, không phải phép đo tuyệt đối cho “lượng nợ”.

## 16. Hai sai lầm khi sử dụng ẩn dụ nợ

### Sai lầm A — “Code nào không hoàn hảo đều là nợ”

Mọi thiết kế đều có đánh đổi. Có những lựa chọn đơn giản nhưng phù hợp trong nhiều năm. Nếu không có gánh nặng hoặc rủi ro đáng kể, việc gọi chúng là nợ có thể làm nhóm mất tập trung vào vấn đề thật.

Câu hỏi tốt hơn: **“Đối với thay đổi hay mục tiêu nào, cấu trúc này đang tạo chi phí không cần thiết?”**

### Sai lầm B — “Đã gọi là nợ thì có thể hoãn mọi thứ”

Một lỗi đang làm mất tiền hoặc rò rỉ dữ liệu cần được đánh giá theo mức độ ảnh hưởng hiện tại. Việc gắn nhãn “technical debt” không làm thay đổi nghĩa vụ xử lý an toàn.

Câu hỏi tốt hơn: **“Đây là rủi ro hiện tại cần sửa ngay, hay gánh nặng tương lai có thể lập kế hoạch?”**

Cũng cần tránh giả định trả nợ là một hoạt động hoàn toàn tách khỏi phát triển tính năng. Nếu đang sửa quy tắc phí, có thể nhân dịp đó **loại bỏ bản sao liên quan** và bổ sung test, miễn là phạm vi thay đổi đủ nhỏ để kiểm chứng.

## 17. Khi nào nên trả nợ dần, khi nào cần một dự án riêng?

**Trả nợ dần trong thay đổi thường ngày** phù hợp khi:

- Đoạn mã đang được sửa vì tính năng mới.
- Refactor có phạm vi rõ và không đòi hỏi migration lớn.
- Có test đủ tốt hoặc có thể bổ sung test trước.
- Cải thiện làm giảm công việc ngay trong thay đổi đang thực hiện.

**Dự án trả nợ riêng** có thể phù hợp khi:

- Cần nâng cấp nền tảng lớn hoặc chuyển mô hình dữ liệu.
- Có nhiều service cùng phải thay đổi hợp đồng.
- Cần kế hoạch chuyển đổi, khả năng chạy song song và rollback.
- Chi phí phải trả một lần lớn nhưng tạo năng lực cho nhiều thay đổi sau.
- Rủi ro bảo mật/vận hành đòi hỏi phối hợp giữa các nhóm.

Trong cả hai trường hợp, ưu tiên **bước nhỏ có thể kiểm chứng**, lưu lại quyết định và không trộn thay đổi định dạng hàng loạt với sửa bug nhạy cảm nếu không cần thiết.

## 18. Quy trình phân biệt bug, nợ và đánh đổi khi review

Khi ai đó nói “đoạn này là nợ kỹ thuật”, hãy đi theo các bước:

~~~mermaid
flowchart TD
    A["Phát hiện vấn đề trong mã"] --> B{"Đang vi phạm hành vi/hợp đồng hiện hành?"}
    B -- "Có" --> C["Ghi bug hoặc rủi ro hiện tại"]
    B -- "Không" --> D["Chưa có bug được chứng minh"]
    C --> E{"Có nguyên nhân cấu trúc gây chi phí lặp?"}
    D --> E
    E -- "Có" --> F["Mô tả nợ: gánh nặng, bằng chứng, phương án"]
    E -- "Chưa rõ" --> G["Đánh giá thêm, không tự gắn nhãn"]
    F --> H["Ưu tiên theo tác động và chi phí cải thiện"]
    G --> I["Giữ đánh đổi nếu phù hợp; theo dõi khi bối cảnh đổi"]
    H --> J["Sửa/kiểm thử, đánh giá chi phí thay đổi sau cải thiện"]
~~~

Một câu hỏi quan trọng: **“Nếu cấu trúc vẫn giữ nguyên và có một yêu cầu mới trong tháng tới, nhóm sẽ phải làm gì thêm?”**. Nếu có thể chỉ ra các bước không cần thiết, khả năng đó là khoản nợ đáng điều tra sẽ rõ hơn.

Nếu hiện tại chỉ có lỗi độc lập, sửa xong và không còn gánh nặng lặp, có thể không cần mở thêm một issue “nợ kỹ thuật” cho cùng vấn đề.

## 19. Dấu hiệu dễ nhầm giữa nợ kỹ thuật và độ phức tạp cần thiết

Không phải mọi sự phức tạp đều do nợ:

- Hệ thống thanh toán phải xử lý idempotency, trạng thái chưa xác định và đối soát; đó có thể là **độ phức tạp nghiệp vụ cần thiết**.
- Một thuật toán có nhiều trường hợp biên vì đặc tả toán học phức tạp; không thể “trả nợ” chỉ bằng cách xóa nhánh.
- Một ranh giới authorization rõ ràng làm tăng số thành phần, nhưng có thể **giảm rủi ro bảo mật**.
- Một lớp adapter cho API bên ngoài có thể tăng số file nhưng **giảm mức ghép nối**.
- Kiểm thử chi tiết cho lỗi hiếm có thể dài hơn implementation nhưng tạo bằng chứng an toàn.

Điều cần giảm là **độ phức tạp không cần thiết so với yêu cầu**, không phải mọi sự phức tạp.

Ngược lại, một phương thức rất ngắn vẫn có thể tạo nợ nếu nó giấu tác dụng phụ, sao chép logic hoặc tạo phụ thuộc khó thay.

## 20. Bài tập áp dụng

### Tình huống A — Sai một điều kiện

Một phương thức đơn lẻ dùng **quantity > 10**, trong khi hợp đồng yêu cầu **quantity >= 10**. Phương thức dễ đọc, có test cho các trường hợp khác, không có bản sao nào.

**Câu hỏi:** Đây là bug, nợ kỹ thuật hay cả hai?

**Gợi ý:** Trước hết là **bug** tại ngưỡng 10. Hãy thêm test cho 9, 10, 11 và sửa điều kiện. Chưa đủ bằng chứng để coi cấu trúc hiện tại là một khoản nợ riêng.

### Tình huống B — Ba bản sao đều đúng

Ba kênh bán hàng cùng tính một loại phí bằng ba phương thức riêng. Chưa phát hiện kết quả sai. Mỗi lần thay đổi quy tắc, nhóm phải kiểm tra và sửa cả ba nơi.

**Câu hỏi:** Vì sao vẫn có thể là nợ kỹ thuật?

**Gợi ý:** Không cần bug hiện tại. Chi phí cập nhật lặp lại và nguy cơ không nhất quán là dấu hiệu “lãi nợ”. Trước khi hợp nhất, xác nhận cả ba kênh thực sự phải theo một hợp đồng.

### Tình huống C — MVP có thời hạn

Nhóm chọn xử lý thủ công một bước dữ liệu trong bản thử nghiệm một tháng, ghi rõ owner, rủi ro và thời điểm xem lại. Nếu sản phẩm tiếp tục phát triển, bước đó sẽ được tự động hóa.

**Câu hỏi:** Quyết định này có mặc nhiên thiếu trách nhiệm không?

**Gợi ý:** Không. Đây có thể là đánh đổi chủ đích hợp lý nếu rủi ro chấp nhận được và có kế hoạch. Cần chú ý tới chi phí phát sinh nếu sản phẩm tiếp tục dùng lâu hơn dự kiến.

### Tình huống D — Xóa test để “giảm nợ”

Một refactor xóa 300 dòng test và làm báo cáo LOC giảm. Chưa có test thay thế, các ca lỗi thanh toán không còn được kiểm tra.

**Câu hỏi:** Có thể gọi là đã trả nợ không?

**Gợi ý:** Không. Giảm LOC không chứng minh cải thiện, và khả năng kiểm chứng có thể kém đi. Cần xem rủi ro hiện tại, bằng chứng test và chi phí thay đổi.

### Tình huống E — Hệ thống sắp ngừng hoạt động

Một module cũ có cấu trúc khó mở rộng nhưng sẽ dừng sử dụng trong ba tuần. Chưa có thay đổi nghiệp vụ mới, không có lỗ hổng được biết và chi phí refactor lớn.

**Câu hỏi:** Có nên lập tức trả hết nợ không?

**Gợi ý:** Không nhất thiết. Đánh giá rủi ro đến khi ngừng hoạt động, chi phí cải thiện và kế hoạch loại bỏ an toàn. Trì hoãn có chủ đích khác với quên vấn đề.

### Tình huống F — Lỗ hổng trong thư viện lỗi thời

Một thư viện không còn được duy trì đang có lỗ hổng ảnh hưởng luồng xác thực. Nhóm định đưa việc nâng cấp vào backlog “trả nợ quý sau”.

**Câu hỏi:** Cách phân loại đó có đủ không?

**Gợi ý:** Không. Đây còn là **rủi ro bảo mật hiện tại** cần được đánh giá và xử lý theo mức độ nghiêm trọng, biện pháp giảm thiểu và kế hoạch khắc phục. Nhãn nợ kỹ thuật không thay thế quy trình xử lý lỗ hổng.

### Tình huống G — Có vẻ trùng nhưng khác chính sách

Công thức phí giao hàng cho hai thị trường trông giống nhau hôm nay, nhưng từng thị trường có nhóm quản lý, lịch áp dụng và quy định độc lập.

**Câu hỏi:** Có nên gom ngay thành một hàm với nhiều if để xóa trùng lặp?

**Gợi ý:** Chưa chắc. Có thể đó là **hai khái niệm khác nhau tình cờ trùng giá trị**. Hợp nhất sai có thể tăng ghép nối và tạo nợ mới; cần xác định nơi sở hữu thay đổi trước khi refactor.

## 21. Checklist trước khi ghi hoặc xử lý một khoản nợ

- **Có vi phạm hợp đồng hiện tại không?** Nếu có, đã phân loại bug/rủi ro theo mức độ nghiêm trọng chưa?
- **Gánh nặng tương lai cụ thể là gì?** Tìm kiếm nhiều nơi, sửa lặp, test chậm, migration khó hay phụ thuộc dễ vỡ?
- **Có bằng chứng hoặc trường hợp thay đổi đại diện không?** Hay chỉ là cảm giác “code trông xấu”?
- **Vì sao thiết kế hiện tại tồn tại?** Do deadline, ràng buộc cũ, thay đổi bối cảnh hay lựa chọn có chủ đích?
- **Các phần định hợp nhất có cùng trách nhiệm/hợp đồng không?** Tránh tạo trừu tượng hóa sai.
- **Lợi ích trả nợ xuất hiện khi nào?** Có thay đổi sắp tới hoặc rủi ro đang phải gánh không?
- **Chi phí cải thiện và rủi ro triển khai là gì?** Có thể chia nhỏ, rollback hoặc giữ tương thích không?
- **Test nào xác nhận kết quả không đổi ngoài yêu cầu?** Đã xét ca biên, lỗi và tác dụng phụ chưa?
- **Ai sở hữu và khi nào xem lại?** Không để issue vô thời hạn chỉ có nhãn “technical debt”.
- **Hoàn thành được xác nhận bằng gì?** Một thay đổi sau refactor có ít lan rộng hoặc ít rủi ro hơn ra sao?

---

**Ghi nhớ:** **Bug** nói rằng phần mềm **đang làm sai** một hành vi được yêu cầu. **Nợ kỹ thuật** nói rằng cấu trúc hoặc quyết định hiện tại đang khiến việc **duy trì và thay đổi về sau tốn kém hoặc rủi ro hơn**. Hai vấn đề có thể độc lập hoặc cùng tồn tại. Đừng gọi mọi đoạn mã chưa đẹp là nợ, cũng đừng dùng nhãn nợ để trì hoãn lỗi nghiêm trọng. Hãy chỉ ra **gánh nặng, bằng chứng, tác động và phương án cải thiện**, rồi ưu tiên trả nợ ở những nơi tạo giá trị và giảm rủi ro thực sự.
