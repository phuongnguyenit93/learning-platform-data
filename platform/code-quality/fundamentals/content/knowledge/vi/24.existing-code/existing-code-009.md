# Cải thiện cục bộ trong quá trình thực hiện thay đổi cần thiết

Một nhóm được giao thêm phụ phí giao hàng vùng xa vào một lớp tính phí đã tồn tại nhiều năm. Trong lúc sửa, developer nhận thấy các mức phí đang được viết trực tiếp trong biểu thức và tên biến chưa thể hiện rõ ý nghĩa. Có thể dành thêm vài phút để đặt tên hằng số và tách phép tính phí tiêu chuẩn thành một bước có tên rõ ràng. Nhưng cũng có thể nhân dịp đó viết lại toàn bộ checkout, đổi cấu trúc package, thay framework và di chuyển mọi lớp liên quan.

Hai lựa chọn đều bắt đầu từ cùng một yêu cầu, nhưng phạm vi và rủi ro rất khác nhau. **Cải thiện cục bộ trong quá trình thực hiện thay đổi cần thiết** là cách nâng chất lượng ngay tại vùng mã đang chạm tới, với phạm vi đủ nhỏ để hiểu, kiểm chứng và review.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Mã hiện hữu**, kỹ năng quan trọng là làm việc an toàn với codebase đã có lịch sử, caller, dữ liệu và quy ước. Không phải lúc nào cũng có thể thiết kế lại từ đầu; thường ta phải cải thiện từng phần khi nhu cầu sản phẩm buộc phải chạm vào chúng.

Bài học giải thích cách chọn cải thiện phù hợp, giữ hành vi ngoài yêu cầu, dùng kiểm thử làm điểm tựa và tránh biến một thay đổi nhỏ thành dự án tái cấu trúc không kiểm soát.

## 1. Cải thiện cục bộ là gì?

**Cải thiện cục bộ (local improvement)** là một thay đổi có chủ đích nhằm làm phần mã đang được sửa trở nên dễ hiểu, đáng tin cậy hoặc dễ thay đổi hơn, đồng thời giữ phạm vi và tác động ở mức có thể kiểm chứng.

Ví dụ:

- Đặt tên cho các giá trị nghiệp vụ đang viết trực tiếp trong biểu thức.
- Tách một đoạn điều kiện khó hiểu thành phương thức có tên thể hiện ý định.
- Bổ sung test cho trường hợp biên ngay tại vùng đang thay đổi.
- Loại bỏ một bản sao logic khi đã xác nhận các luồng thực sự dùng cùng hợp đồng.
- Làm rõ xử lý tài nguyên ở đúng phương thức đang được sửa.
- Cập nhật comment hoặc Javadoc đã lỗi thời vì thay đổi hiện tại.
- Đưa một phụ thuộc trực tiếp ra sau interface nhỏ khi điều đó giải quyết đúng khó khăn của thay đổi.

Một cải thiện cục bộ không cần thay đổi lớn mới có giá trị. Đôi khi một tên biến rõ ràng hoặc một test tại ngưỡng đã giúp lần sửa tiếp theo an toàn hơn.

### Nguyên tắc “để phần mã tốt hơn khi rời đi”

Một cách diễn đạt quen thuộc là **Boy Scout Rule**: khi chạm vào một vùng mã, hãy cố gắng để vùng đó tốt hơn một chút so với lúc bắt đầu. Nguyên tắc này khuyến khích cải thiện liên tục thay vì chờ một dự án dọn dẹp lớn.

Tuy nhiên, áp dụng tốt cần ba giới hạn:

1. **Có liên quan:** cải thiện gắn với vùng đang thay đổi hoặc trực tiếp giảm rủi ro của yêu cầu hiện tại.
2. **Có thể kiểm chứng:** biết hành vi nào phải giữ, test nào bảo vệ và diff nào thể hiện thay đổi.
3. **Có quy mô phù hợp:** lợi ích rõ ràng hơn chi phí review, kiểm thử và phối hợp phát sinh.

Boy Scout Rule không phải lời mời sửa mọi thứ nhìn thấy trong repository. Nếu mỗi PR đều mở rộng sang nhiều module không liên quan, nhóm sẽ khó review và khó xác định nguyên nhân khi có lỗi.

## 2. Vì sao nên cải thiện khi đang chạm vào mã?

Một vùng mã đang được sửa đã nằm trong ngữ cảnh làm việc của developer và reviewer. Họ đang đọc caller, hiểu quy tắc, chạy test và xem dữ liệu liên quan. Đây là thời điểm thuận lợi để thực hiện một cải thiện nhỏ có liên quan.

Lợi ích có thể gồm:

- **Giảm chi phí lần sửa sau:** tên biến, hằng số và ranh giới trách nhiệm rõ hơn.
- **Giảm lỗi lặp lại:** test mới bảo vệ đúng nhánh vừa được chạm tới.
- **Giảm trùng lặp:** một quy tắc dùng chung được đặt tại nơi sở hữu phù hợp.
- **Giữ kiến thức trong codebase:** comment và tài liệu được cập nhật cùng hành vi.
- **Giảm rủi ro khi mở rộng:** phụ thuộc hoặc tác dụng phụ được làm rõ trước khi thêm tính năng.
- **Tạo tiến bộ liên tục:** những cải thiện nhỏ tích lũy mà không cần dừng phát triển để viết lại toàn bộ hệ thống.

Tuy nhiên, cải thiện chỉ có giá trị khi không làm mờ mục tiêu chính. Một PR thêm phụ phí vùng xa nhưng thay đổi đồng thời hệ thống xác thực, cấu trúc database và formatter toàn repository sẽ tạo thêm nhiều điểm cần xác minh.

**Cải thiện cục bộ giúp giảm chi phí thay đổi trong tương lai; nó không phải lý do để tăng phạm vi của mọi PR.**

## 3. Phân biệt yêu cầu chính và cải thiện đi kèm

Khi bắt đầu một công việc trên code hiện hữu, hãy phân loại những thay đổi dự định:

| Loại thay đổi | Mục tiêu | Ví dụ | Cách quản lý |
| --- | --- | --- | --- |
| **Thay đổi bắt buộc** | Đáp ứng yêu cầu sản phẩm hoặc sửa lỗi hiện tại. | Thêm phụ phí vùng xa 15.000 VND. | Phải hoàn thành và kiểm thử theo đặc tả. |
| **Refactor hỗ trợ** | Làm cấu trúc vùng đang sửa rõ hơn để triển khai yêu cầu an toàn. | Tách phép tính phí tiêu chuẩn thành helper. | Giữ hành vi cũ ngoài phần tính năng mới; review cùng yêu cầu nếu phạm vi nhỏ. |
| **Cải thiện tùy chọn gần kề** | Giảm một khó khăn cụ thể phát hiện trong vùng đang chạm. | Đổi tên biến local từ fee thành standardFee. | Chỉ làm nếu diff vẫn nhỏ và lợi ích rõ. |
| **Công việc độc lập** | Giải quyết vấn đề ở vùng khác hoặc cần quyết định rộng. | Thay framework checkout, di chuyển package toàn hệ thống. | Tách issue/PR hoặc lập kế hoạch riêng. |
| **Bug phát hiện thêm** | Sửa hành vi đang sai so với hợp đồng. | Đơn đúng ngưỡng miễn phí vẫn bị thu phí. | Ghi rõ là bug fix; cân nhắc tách nếu làm thay đổi phạm vi hoặc rủi ro. |

Không phải cứ có nhiều loại thay đổi là bắt buộc tách thành nhiều PR. Một refactor nhỏ, trực tiếp hỗ trợ tính năng và có test rõ có thể nằm cùng PR. Nhưng một thay đổi độc lập, lớn hoặc có hợp đồng khác cần được xem xét riêng.

### Một câu hỏi để giữ phạm vi

Trước khi thêm một chỉnh sửa, hãy tự hỏi:

> Nếu không có yêu cầu hiện tại, mình có định làm thay đổi này ngay bây giờ không? Và nếu làm, nó có trực tiếp giúp vùng đang sửa an toàn hơn hoặc dễ thay đổi hơn không?

Nếu câu trả lời là “không liên quan, chỉ tiện tay”, nhiều khả năng nên ghi nhận cho một công việc riêng hoặc bỏ qua.

## 4. Đọc code hiện hữu trước khi chỉnh

Mã cũ thường có lý do tồn tại mà một đoạn code riêng lẻ không thể hiện hết. Trước khi sửa, hãy tìm hiểu đủ ngữ cảnh:

- **Caller:** Ai gọi phương thức, gọi với dữ liệu nào và có bao nhiêu đường sử dụng?
- **Hợp đồng:** API, schema, exception, trạng thái và kết quả nào đã được caller dựa vào?
- **Test hiện tại:** Test nào bảo vệ quy tắc, test nào chỉ kiểm tra implementation?
- **Quy ước:** Formatter, naming, package và cách xử lý lỗi của module là gì?
- **Phụ thuộc:** Có database, SDK, message broker, filesystem hoặc dịch vụ ngoài không?
- **Lịch sử thay đổi liên quan:** Vùng này thường thay đổi vì lý do gì? Có bug lặp lại không?
- **Owner:** Ai hiểu nghiệp vụ hoặc quyết định hợp đồng của thành phần?

Không cần đọc toàn bộ repository trước mọi thay đổi. Hãy mở rộng phạm vi tìm hiểu theo **đường phụ thuộc và mức rủi ro thực tế**.

Một phương thức private nhỏ có thể chỉ cần đọc lớp chứa nó và test. Một method public được nhiều service dùng cần tìm caller, contract và compatibility trước khi đổi.

## 5. Thiết lập điểm tựa trước khi cải thiện

Nếu vùng mã có test tốt, chạy các test liên quan trước khi sửa để biết baseline. Nếu chưa có test, cần tạo bằng chứng phù hợp trước hoặc trong quá trình thay đổi.

Một baseline hữu ích có thể gồm:

- Kết quả test hiện tại.
- Các input đại diện và output mong đợi theo hợp đồng.
- Hành vi của đường lỗi.
- Trạng thái dữ liệu hoặc tác dụng phụ có ý nghĩa.
- Các ràng buộc hiệu năng/tài nguyên nếu vùng đó nhạy cảm.
- Những test đang fail trước khi bắt đầu.

**Đừng giả định mọi hành vi của code cũ đều đúng.** Nếu phát hiện bug đã tồn tại, phân loại nó là bug và quyết định sửa có chủ đích. Test ghi nhận hành vi cũ chỉ nên trở thành hợp đồng lâu dài sau khi đã xác nhận hành vi đó được yêu cầu.

### Characterization test khi chưa hiểu hết code cũ

Nếu không có tài liệu rõ, có thể dùng **characterization test** để ghi nhận hành vi đang quan sát được:

1. Chọn đầu vào đại diện từ cách sử dụng thật.
2. Chạy phiên bản hiện tại và ghi output, exception, trạng thái hoặc tác dụng phụ.
3. Đối chiếu kết quả với yêu cầu và owner nghiệp vụ.
4. Phân loại điều cần giữ, điều là bug và điều chưa rõ.
5. Tạo assertion cho các hành vi đã xác nhận cần bảo vệ.

Đừng sao chép mọi output cũ thành expected rồi gọi đó là đặc tả. Làm vậy có thể đóng băng bug hoặc dữ liệu sai vào test suite.

## 6. Ví dụ xuyên suốt: thêm phụ phí vùng xa vào mã tính phí cũ

Giả sử codebase có một lớp tính phí đã được dùng bởi nhiều caller. Hợp đồng hiện tại:

- Tổng tiền hàng **subtotalVnd** được cung cấp bằng VND nguyên.
- Đơn từ **500.000 VND** trở lên được miễn phí giao tiêu chuẩn.
- Đơn dưới ngưỡng trả phí tiêu chuẩn **30.000 VND**.
- Giao nhanh cộng **20.000 VND**.
- Các caller hiện tại chưa có khái niệm vùng xa.

Yêu cầu mới:

- Nếu đơn thuộc vùng xa, cộng phụ phí **15.000 VND**.
- Phụ phí vùng xa áp dụng độc lập với phí tiêu chuẩn và giao nhanh.
- Những caller không chọn vùng xa phải giữ nguyên kết quả trước đây.

Đây là **quy tắc giả định cho ví dụ học tập**, không phải chính sách của một sản phẩm thực tế.

### Phiên bản hiện tại

~~~java
public final class ShippingFeeCalculator {
    private ShippingFeeCalculator() {
    }

    public static long calculate(long subtotalVnd, boolean express) {
        long fee = subtotalVnd >= 500_000L ? 0L : 30_000L;

        if (express) {
            fee = fee + 20_000L;
        }

        return fee;
    }
}
~~~

Code này ngắn, có thể chạy đúng theo hợp đồng hiện tại. Nhưng các con số chưa có tên và phương thức chỉ thể hiện tổng phí, chưa phân biệt các thành phần.

Yêu cầu mới cần thêm một điều kiện. Ta có thể **chỉ thêm một nhánh**, hoặc kết hợp một refactor nhỏ để tên và các bước tính phí rõ ràng hơn.

Điều cần bảo vệ trước tiên: với remoteArea = false, kết quả của API cũ phải giữ nguyên ở mọi trường hợp đã được xác nhận.

## 7. Cải thiện cục bộ hỗ trợ thay đổi

Một phiên bản sau có thể là:

~~~java
public final class ShippingFeeCalculator {
    private static final long FREE_STANDARD_THRESHOLD = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_SURCHARGE = 20_000L;
    private static final long REMOTE_AREA_SURCHARGE = 15_000L;

    private ShippingFeeCalculator() {
    }

    public static long calculate(
            long subtotalVnd,
            boolean express,
            boolean remoteArea) {

        long standardFee = calculateStandardFee(subtotalVnd);
        long expressFee = express ? EXPRESS_SURCHARGE : 0L;
        long remoteAreaFee =
                remoteArea ? REMOTE_AREA_SURCHARGE : 0L;

        return standardFee + expressFee + remoteAreaFee;
    }

    private static long calculateStandardFee(long subtotalVnd) {
        return subtotalVnd >= FREE_STANDARD_THRESHOLD
                ? 0L
                : STANDARD_FEE;
    }
}
~~~

Những cải thiện cục bộ:

- **Đặt tên hằng số:** người đọc hiểu các con số đại diện cho chính sách nào.
- **Tách phép tính phí tiêu chuẩn:** phương thức chính thể hiện từng thành phần phí.
- **Đặt tên biến theo ý nghĩa:** standardFee, expressFee và remoteAreaFee dễ kiểm tra hơn fee.
- **Không tạo tầng trừu tượng thừa:** chỉ có một helper thực sự làm rõ trách nhiệm.
- **Giữ quy tắc cũ:** khi remoteArea = false, phụ phí vùng xa bằng 0.

Phần thay đổi hành vi mới là **remoteArea = true** làm tổng phí tăng 15.000 VND. Refactor và tính năng có thể được review trong cùng PR vì chúng gắn trực tiếp với cùng phép tính và vẫn có thể phân biệt bằng test.

Nếu phương thức hai tham số là API công khai mà caller cũ cần tiếp tục sử dụng, có thể giữ overload:

~~~java
public static long calculate(long subtotalVnd, boolean express) {
    return calculate(subtotalVnd, express, false);
}
~~~

Nếu API chỉ được dùng nội bộ và tất cả caller có thể được cập nhật cùng lúc, thay chữ ký và sửa caller có thể đơn giản hơn. Quyết định phụ thuộc **hợp đồng và phạm vi tương thích**, không phải sở thích về overload.

## 8. Kiểm thử phần cũ và phần mới

Một bộ JUnit 5 có thể bảo vệ các trường hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeCalculatorTest {
    @ParameterizedTest
    @CsvSource({
            "0, false, false, 30000",
            "499999, false, false, 30000",
            "500000, false, false, 0",
            "500001, false, false, 0",
            "500000, true, false, 20000"
    })
    void preservesExistingBehaviorWhenNotRemote(
            long subtotal, boolean express,
            boolean remoteArea, long expected) {
        assertEquals(expected,
                ShippingFeeCalculator.calculate(
                        subtotal, express, remoteArea));
    }

    @Test
    void addsRemoteSurchargeBelowFreeThreshold() {
        assertEquals(45_000L,
                ShippingFeeCalculator.calculate(499_999L, false, true));
    }

    @Test
    void addsRemoteSurchargeEvenWhenStandardShippingIsFree() {
        assertEquals(15_000L,
                ShippingFeeCalculator.calculate(500_000L, false, true));
    }

    @Test
    void combinesExpressAndRemoteSurcharges() {
        assertEquals(35_000L,
                ShippingFeeCalculator.calculate(500_000L, true, true));
    }
}
~~~

Các kết quả kỳ vọng:

| subtotalVnd | express | remoteArea | Phí tiêu chuẩn | Phụ phí giao nhanh | Phụ phí vùng xa | Tổng |
| ---: | :---: | :---: | ---: | ---: | ---: | ---: |
| 499.999 | false | false | 30.000 | 0 | 0 | **30.000** |
| 500.000 | false | false | 0 | 0 | 0 | **0** |
| 500.000 | true | false | 0 | 20.000 | 0 | **20.000** |
| 499.999 | false | true | 30.000 | 0 | 15.000 | **45.000** |
| 500.000 | false | true | 0 | 0 | 15.000 | **15.000** |
| 500.000 | true | true | 0 | 20.000 | 15.000 | **35.000** |

Bộ test tách hai mục tiêu:

- Với remoteArea = false, **hành vi cũ phải giữ nguyên**.
- Với remoteArea = true, **tính năng mới phải áp dụng đúng**.

Nếu chỉ test ca remoteArea = true, một refactor vô tình thay ngưỡng phí tiêu chuẩn có thể bị bỏ sót. Nếu chỉ test ca cũ, tính năng mới có thể chưa được kiểm chứng.

Đây là ví dụ minh họa cách viết test, không phải kết quả chạy test của repository.

## 9. Chọn cải thiện nào đáng làm ngay?

Không phải vấn đề nào nhìn thấy trong vùng mã cũng cần sửa. Dùng các tiêu chí:

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Liên quan** | Cải thiện có gắn trực tiếp với yêu cầu hoặc vùng code đang chạm không? |
| **Lợi ích cụ thể** | Nó làm giảm nguy cơ nào hoặc giúp lần sửa sau dễ hơn ra sao? |
| **Phạm vi** | Có thể làm trong một vài thay đổi nhỏ, dễ hiểu không? |
| **Bằng chứng** | Có test, hợp đồng hoặc tiêu chí review để chứng minh không? |
| **Tương thích** | Có ảnh hưởng caller, dữ liệu, API, serialization hoặc vận hành không? |
| **Chi phí review** | Có làm reviewer phải hiểu thêm nhiều module không liên quan không? |
| **Khả năng tách** | Nếu không làm bây giờ, có thể ghi thành issue/PR riêng mà không làm tăng rủi ro hiện tại không? |

Một ma trận quyết định đơn giản:

| Tình huống | Hành động phù hợp |
| --- | --- |
| Đặt tên hằng số cho ba giá trị đang dùng trong phép tính vừa sửa | Thường làm ngay nếu giúp làm rõ chính sách. |
| Thêm test tại ngưỡng mà feature mới chạm tới | Làm ngay; đây là bằng chứng cần thiết. |
| Tách helper nhỏ để phép tính mới dễ đọc | Làm ngay nếu giữ hành vi cũ và không tạo abstraction thừa. |
| Phát hiện bug bảo mật trong đường gọi liên quan | Xử lý theo mức rủi ro; không trì hoãn chỉ vì ngoài yêu cầu ban đầu. |
| Muốn đổi formatter toàn repository | Tách kế hoạch/PR riêng nếu không cần cho yêu cầu hiện tại. |
| Muốn thay framework persistence | Phân tích và lập công việc riêng, trừ khi đây là điều kiện bắt buộc của yêu cầu. |
| Muốn đổi tên API được nhiều consumer sử dụng | Đánh giá compatibility và migration; không xem là cleanup nhỏ. |
| Thấy một class khác dài nhưng không liên quan | Ghi nhận nếu có bằng chứng và owner; không tự tiện mở rộng diff. |

## 10. Cải thiện nhỏ không được làm thay đổi ngầm hợp đồng

Một số chỉnh sửa nhìn có vẻ nội bộ nhưng có thể thay hành vi:

- Đổi thứ tự kiểm tra đầu vào và gọi phụ thuộc.
- Chuyển lazy evaluation sang eager evaluation.
- Đổi HashMap sang cấu trúc có thứ tự hoặc ngược lại khi caller quan sát iteration order.
- Thay exception cụ thể bằng exception chung.
- Đổi null thành empty collection hoặc ngược lại.
- Đưa lời gọi bên ngoài vào vòng lặp hoặc ra khỏi transaction.
- Đổi thời điểm gửi event.
- Thêm cache làm dữ liệu cũ tồn tại lâu hơn.
- Đổi kiểu số nguyên sang số thực cho phép tính tiền.
- Thêm validation mới khiến caller trước đây hợp lệ bị từ chối.

Nếu một cải thiện làm thay đổi hợp đồng, hãy gọi đúng tên là **bug fix, behavior change hoặc contract change**. Có thể nó vẫn là một quyết định tốt, nhưng cần test và phê duyệt phù hợp.

### Ví dụ: thêm validation có thể là thay đổi hành vi

Giả sử code cũ nhận subtotal âm và trả một kết quả không có ý nghĩa. Thêm kiểm tra subtotal âm có thể là sửa bug cần thiết, nhưng nó cũng thay đổi cách API phản hồi với input đó.

Trước khi thêm, cần biết:

- Hợp đồng có yêu cầu subtotal không âm không?
- Caller đã validate ở đâu?
- Có client nào đang gửi giá trị sentinel âm không?
- Loại exception hoặc mã lỗi nào được mong đợi?
- Có cần cập nhật API docs và test contract không?

Không nên gọi thay đổi này là “chỉ refactor” để né review hợp đồng.

## 11. Đừng hợp nhất những quy tắc chỉ tình cờ giống nhau

Loại bỏ duplicate code là một cải thiện phổ biến, nhưng **hai đoạn giống nhau về cú pháp không nhất thiết cùng một khái niệm**.

Ví dụ hai thị trường đều đang có:

- Ngưỡng miễn phí 500.000 VND.
- Phí tiêu chuẩn 30.000 VND.

Nhưng hai thị trường có owner, quy định và thời điểm hiệu lực độc lập. Nếu gộp thành một chính sách duy nhất, lần thay đổi ở thị trường A có thể vô tình ảnh hưởng B.

Trước khi hợp nhất, xác minh:

1. Hai đoạn mã có cùng **ý nghĩa nghiệp vụ** không?
2. Chúng có cùng owner và cùng lý do thay đổi không?
3. Các khác biệt có phải chỉ là tham số của cùng một quy tắc không?
4. Có cần version hoặc effective date không?
5. Việc gom chung có tạo phụ thuộc mới không?

Nếu câu trả lời chưa rõ, có thể chỉ cải thiện tên và test trong từng vùng trước, rồi lập quyết định thiết kế khi đã có đủ ngữ cảnh.

**Tránh trùng lặp cú pháp có thể tạo lợi ích; hợp nhất sai khái niệm có thể tạo nợ mới.**

## 12. Cải thiện cục bộ ở những dạng code hiện hữu thường gặp

| Dấu hiệu khi chạm mã | Cải thiện nhỏ có thể cân nhắc | Điều cần giữ |
| --- | --- | --- |
| Giá trị nghiệp vụ viết trực tiếp nhiều lần | Đặt tên hằng số hoặc cấu hình có nguồn sở hữu rõ. | Giá trị và thời điểm áp dụng theo hợp đồng. |
| Một biểu thức dài trộn nhiều quy tắc | Tách helper có tên theo ý nghĩa. | Thứ tự, kết quả và ngoại lệ. |
| Một đoạn logic giống nhau trong cùng khái niệm | Gom về nơi sở hữu chung. | Khác biệt thực sự giữa các caller. |
| Không có test cho nhánh đang sửa | Thêm test biên và đường lỗi liên quan. | Expected được suy từ yêu cầu độc lập. |
| Comment mô tả code cũ | Cập nhật hoặc xóa comment lỗi thời. | Lý do nghiệp vụ vẫn cần được lưu nếu không thể suy ra từ code. |
| Phương thức có nhiều tác dụng phụ | Làm rõ ranh giới và thứ tự thao tác. | Transaction, idempotency và event ordering. |
| Tài nguyên mở thủ công | Dùng cấu trúc quản lý vòng đời phù hợp như try-with-resources. | Thời điểm đóng và xử lý lỗi. |
| Phụ thuộc khó thay trong đúng vùng đang mở rộng | Cách ly bằng adapter/interface nhỏ. | Contract, timeout, retry và mapping lỗi. |
| Tài liệu ví dụ đã sai do thay đổi hiện tại | Cập nhật cùng PR hoặc chuyển owner phù hợp. | Tài liệu phản ánh hợp đồng đã được phê duyệt. |
| Logging thiếu ngữ cảnh tại điểm vừa sửa | Bổ sung thông tin vận hành cần thiết. | Không log secret, dữ liệu cá nhân hoặc payload nhạy cảm. |

Không có cải thiện nào trong bảng là lệnh phải áp dụng mọi nơi. **Chỉ thực hiện khi nó giải quyết một vấn đề có thật trong ngữ cảnh.**

## 13. Tách thay đổi theo mục tiêu khi diff bắt đầu lớn

Một PR có thể bắt đầu nhỏ rồi mở rộng:

- Thêm tính năng vùng xa.
- Đổi tên các lớp liên quan.
- Chuyển package.
- Format toàn module.
- Thay cách lưu dữ liệu.
- Nâng framework.

Khi đó, hãy xem lại ranh giới. Một quy tắc thực dụng:

- **Cùng mục tiêu, cùng vùng, ít rủi ro:** có thể để trong một PR.
- **Refactor nhỏ để hỗ trợ feature:** có thể ở cùng PR nếu diff rõ và test bảo vệ hành vi.
- **Bug độc lập:** cân nhắc tách, trừ khi rủi ro hiện tại cần sửa ngay cùng thay đổi.
- **Migration/hợp đồng rộng:** thường cần kế hoạch và review riêng.
- **Format-only diện rộng:** thường tách để tránh nhiễu diff.
- **Công việc không liên quan:** ghi issue hoặc bỏ khỏi PR.

Một thay đổi lớn không tự động sai, nhưng reviewer cần có khả năng xác định **điều gì đổi, vì sao đổi và bằng chứng nào xác nhận**. Nếu không thể giải thích toàn bộ diff một cách mạch lạc, hãy chia nhỏ.

## 14. Giữ thay đổi có thể rollback và dễ điều tra

Cải thiện cục bộ nên ưu tiên bước nhỏ, có thể kiểm chứng và rollback:

1. Thêm test bảo vệ hành vi hiện tại.
2. Thực hiện một refactor cơ học nhỏ.
3. Chạy lại test và review diff.
4. Thêm phần hành vi mới.
5. Bổ sung test cho hành vi mới.
6. Kiểm tra caller và tích hợp.
7. Ghi nhận kết quả và rủi ro còn lại.

Không phải mọi thay đổi đều cần đúng thứ tự này. Với một feature đơn giản, có thể thêm test mới cùng implementation rồi refactor trong cùng commit. Nhưng nếu baseline yếu hoặc rủi ro cao, **tách bước để xác định nguyên nhân khi test fail** sẽ hữu ích hơn.

Nếu một bước refactor gây lỗi, có thể quay lại bước gần nhất mà test còn xanh. Điều này giúp tránh tình trạng một commit chứa nhiều loại thay đổi khiến việc điều tra khó khăn.

## 15. Khi nào nên dừng cải thiện và mở công việc riêng?

Một số dấu hiệu cho thấy việc cải thiện đã vượt khỏi phạm vi cục bộ:

- Cần thay đổi hợp đồng của nhiều service hoặc consumer.
- Cần migration database hoặc dữ liệu lớn.
- Cần thay framework, thư viện lõi hoặc cách triển khai.
- Cần phối hợp nhiều nhóm hoặc owner nghiệp vụ.
- Cần thay đổi diện rộng ở bảo mật, quyền hoặc quy trình vận hành.
- Chưa có test hoặc môi trường đủ để kiểm chứng rủi ro.
- PR bắt đầu chứa nhiều quyết định kiến trúc không liên quan đến yêu cầu ban đầu.

Khi đó, hãy:

- Ghi rõ vấn đề và bằng chứng.
- Chỉ ra tác động nếu tiếp tục trì hoãn.
- Đề xuất phạm vi riêng và người sở hữu.
- Nêu phụ thuộc và điều kiện cần trước khi bắt đầu.
- Giữ phần sửa hiện tại ở mức an toàn nếu có thể.

Không cần tạo issue cho mọi ý tưởng. Chỉ theo dõi những vấn đề có **lợi ích, rủi ro hoặc chi phí bảo trì đủ rõ**.

## 16. Cải thiện cục bộ không đồng nghĩa sửa mọi code smell

Code smell là tín hiệu để điều tra, không phải kết luận tự động. Một class dài, một method nhiều tham số hoặc một số dòng lặp có thể đáng xem xét, nhưng quyết định cần dựa vào bối cảnh.

Ví dụ:

- Một switch dài có thể là cách rõ nhất để ánh xạ một enum nhỏ.
- Một phương thức dài có thể mô tả một quy trình tuần tự có thứ tự bắt buộc.
- Hai đoạn code giống nhau có thể đại diện cho hai chính sách độc lập.
- Một interface có một implementation có thể cần thiết ở ranh giới kiến trúc, hoặc chỉ tạo gián tiếp thừa.
- Một class chứa nhiều field có thể là data transfer object, không nhất thiết là lớp có quá nhiều trách nhiệm.

Hãy hỏi **code smell này đang gây chi phí gì ở yêu cầu hiện tại?** Nếu chưa có tác động cụ thể, có thể quan sát thay vì sửa ngay.

## 17. Cách review một cải thiện đi kèm

Reviewer nên đánh giá cả mục tiêu chính và phần cải thiện:

| Câu hỏi | Bằng chứng cần xem |
| --- | --- |
| Tính năng chính có đúng không? | Test theo yêu cầu, giá trị biên và caller. |
| Hành vi cũ ngoài phạm vi có được giữ không? | Test regression/characterization và diff. |
| Cải thiện có liên quan không? | Lý do trực tiếp với vùng đang thay đổi. |
| Cấu trúc sau sửa có rõ hơn không? | Trách nhiệm, tên, luồng dữ liệu và phụ thuộc. |
| Có tạo abstraction thừa không? | Số tầng chuyển tiếp, khả năng tái sử dụng thực tế và nơi sở hữu. |
| Có đổi hợp đồng ngoài ý muốn không? | API, schema, exception, trạng thái, tác dụng phụ. |
| Phạm vi có quá rộng không? | Danh sách file, module, migration và quyết định độc lập. |
| Test có đủ tin cậy không? | Expected độc lập, dữ liệu cô lập và mức test phù hợp. |

Nếu cải thiện là tùy chọn, comment nên nói rõ **không chặn merge** hoặc đề nghị tách công việc. Nếu cải thiện là điều kiện để tránh rủi ro quan trọng, reviewer cần nêu hợp đồng hoặc tác động khiến nó bắt buộc.

## 18. Mô tả PR để phân biệt feature và cải thiện cục bộ

Một mô tả rõ ràng có thể viết:

~~~markdown
## Thay đổi cần thiết
Thêm phụ phí vùng xa 15.000 VND vào cách tính phí giao hàng.

## Cải thiện cục bộ đi kèm
- Đặt tên hằng số cho ngưỡng và các mức phí.
- Tách phép tính phí tiêu chuẩn thành helper có tên rõ.
- Giữ cách gọi cũ bằng overload nếu caller hiện tại cần tương thích.

## Hành vi được bảo vệ
- Không chọn vùng xa: giữ kết quả cũ.
- Miễn phí tiêu chuẩn từ 500.000 VND.
- Giao nhanh vẫn cộng 20.000 VND.
- Vùng xa cộng 15.000 VND độc lập với các khoản khác.

## Kiểm chứng
- Test dưới, tại và trên ngưỡng.
- Test các tổ hợp express/remoteArea.
- Kiểm tra caller và contract liên quan.
- Ghi kết quả test thực tế trên revision cuối.
~~~

Mẫu này giúp reviewer biết **phần nào là yêu cầu, phần nào là refactor hỗ trợ và hành vi nào phải giữ**. Khi áp dụng thực tế, chỉ ghi những test đã chạy và kết quả thật.

## 19. Những anti-pattern cần tránh

| Anti-pattern | Hệ quả | Cách xử lý tốt hơn |
| --- | --- | --- |
| **Tiện tay viết lại module** | Diff lớn, nhiều rủi ro và khó xác định nguyên nhân. | Chọn cải thiện trực tiếp và tách kế hoạch lớn. |
| **Xóa code trùng mà chưa hiểu khái niệm** | Gộp nhầm hai chính sách độc lập. | Xác nhận cùng owner, cùng hợp đồng và cùng lý do thay đổi. |
| **Đổi hành vi dưới nhãn refactor** | Bug fix hoặc feature bị che trong thay đổi cấu trúc. | Phân loại và test riêng. |
| **Thêm abstraction vì có thể tái sử dụng** | Tăng số lớp và đường gián tiếp. | Chỉ tạo abstraction khi giải quyết phụ thuộc hoặc trách nhiệm cụ thể. |
| **Sửa mọi code smell trong vùng nhìn thấy** | PR mất trọng tâm, reviewer quá tải. | Ưu tiên theo tác động và giới hạn phạm vi. |
| **Không chạy baseline** | Không biết lỗi đã có trước hay do thay đổi mới. | Ghi trạng thái test trước khi sửa. |
| **Expected lấy từ implementation cũ** | Đóng băng bug vào test. | Đối chiếu đặc tả và owner nghiệp vụ. |
| **Chỉ kiểm tra happy path** | Bỏ sót biên, lỗi và tác dụng phụ. | Bổ sung test theo rủi ro. |
| **Format toàn repository cùng feature nhỏ** | Nhiễu diff và tăng xung đột. | Tách format-only hoặc giới hạn file. |
| **Không cập nhật caller** | Một số luồng dùng API cũ, luồng khác dùng logic mới. | Tìm caller và kiểm tra compatibility. |
| **Tạo issue cho mọi nit** | Backlog đầy việc ít giá trị. | Theo dõi vấn đề có tác động rõ. |
| **Không ghi lý do cải thiện** | Người review không biết vì sao phạm vi tăng. | Nêu lợi ích và tiêu chí hoàn tất trong PR. |

## 20. Quy trình thực hành cải thiện cục bộ

~~~mermaid
flowchart TD
    A["Nhận yêu cầu thay đổi"] --> B["Đọc caller, hợp đồng và test liên quan"]
    B --> C["Ghi baseline và xác định rủi ro"]
    C --> D["Chọn cải thiện nhỏ gắn với vùng đang chạm"]
    D --> E{"Có thể kiểm chứng trong phạm vi hợp lý?"}
    E -- "Không" --> F["Tách thành issue/PR hoặc xin làm rõ"]
    E -- "Có" --> G["Sửa từng bước nhỏ"]
    G --> H["Chạy test và xem diff"]
    H --> I{"Hành vi ngoài yêu cầu có giữ nguyên?"}
    I -- "Không" --> J["Sửa lại hoặc phân loại thành bug/contract change"]
    J --> G
    I -- "Có" --> K["Review mục tiêu, cải thiện và rủi ro"]
    K --> L["Merge khi gate bắt buộc đạt"]
~~~

Các bước áp dụng:

1. **Hiểu yêu cầu:** Viết rõ hành vi mới hoặc bug cần sửa.
2. **Tìm vùng chịu ảnh hưởng:** Xem caller, hợp đồng, test và phụ thuộc liên quan.
3. **Ghi baseline:** Biết test nào đang xanh/đỏ và hành vi nào đã được xác nhận.
4. **Chọn một cải thiện gần kề:** Nêu lợi ích cụ thể, tránh danh sách cleanup chung chung.
5. **Đánh giá phạm vi:** Nếu cần đổi nhiều module hoặc hợp đồng, tách công việc.
6. **Thực hiện bước nhỏ:** Đặt tên, trích xuất, loại bỏ lặp hoặc bổ sung test có mục đích.
7. **Kiểm chứng:** Chạy test liên quan, xem raw diff, kiểm tra caller và tác dụng phụ.
8. **Review:** Phân biệt feature, bug fix và refactor; nêu lý do cho phần cải thiện.
9. **Đóng công việc:** Cập nhật tài liệu và theo dõi vấn đề còn lại nếu thực sự cần.

## 21. Đo giá trị của cải thiện

Không nên đánh giá cải thiện cục bộ chỉ bằng số dòng giảm, số class mới hoặc số test tăng. Hãy xem kết quả theo mục tiêu:

| Mục tiêu | Tín hiệu phù hợp |
| --- | --- |
| Làm rõ ý nghĩa | Reviewer hiểu nhanh hơn nơi quy tắc nằm và các bước thực hiện. |
| Giảm trùng lặp cùng khái niệm | Một thay đổi chính sách chỉ cần cập nhật nơi sở hữu chung. |
| Giảm nguy cơ hồi quy | Có test cho các nhánh/biên trước đây chưa được bảo vệ. |
| Giảm phụ thuộc | Thay đổi một adapter không lan sang logic nghiệp vụ. |
| Tăng khả năng vận hành | Lỗi có ngữ cảnh, tài nguyên được giải phóng và trạng thái dễ quan sát. |
| Giảm phạm vi review | Diff tập trung hơn, ít thay đổi không liên quan. |

Một cải thiện có thể làm số dòng tăng nhưng giúp code rõ hơn. Một refactor có thể thêm interface và test, nhưng giảm rủi ro thay đổi. **Không có một metric đơn lẻ chứng minh phần mã đã tốt hơn.**

## 22. Khi code hiện hữu thiếu test hoặc khó chạy

Đây là tình huống phổ biến ở hệ thống lâu năm. Không phải lúc nào cũng có thể viết test đầy đủ ngay:

- Thành phần phụ thuộc trực tiếp vào database thật.
- Cần môi trường ngoài hoặc credential để chạy.
- Dữ liệu thử nghiệm khó tạo.
- Test suite cũ flaky hoặc chạy quá lâu.
- Hành vi phụ thuộc vào framework hoặc static state.
- Không có owner nghiệp vụ để xác nhận expected.

Cách tiến hành thận trọng:

1. **Tìm ranh giới có thể quan sát:** API, repository, adapter hoặc output.
2. **Tạo fixture nhỏ:** dữ liệu giả đại diện cho trường hợp cần sửa.
3. **Dùng characterization test:** ghi nhận hành vi cần giữ sau khi xác nhận.
4. **Tách logic thuần nếu hợp lý:** chỉ khi việc tách không làm đổi hợp đồng hoặc tăng abstraction vô nghĩa.
5. **Chạy kiểm chứng thủ công có ghi lại:** nếu chưa thể tự động hóa, ghi môi trường, bước và kết quả.
6. **Nêu giới hạn bằng chứng:** không tuyên bố test đầy đủ khi một phần chưa chạy.

Nếu thiếu test khiến thay đổi có rủi ro cao không thể xác minh, có thể cần một bước chuẩn bị riêng trước khi tiếp tục. **Không dùng việc code đã sửa xong làm bằng chứng rằng nó an toàn.**

## 23. Xử lý bug phát hiện trong lúc cải thiện

Trong lúc đọc code cũ, có thể thấy một lỗi không nằm trong yêu cầu ban đầu. Hãy phân loại:

- **Bug nghiêm trọng hoặc đang gây hại:** ưu tiên xử lý theo mức rủi ro; có thể cần bản vá riêng hoặc phối hợp với yêu cầu hiện tại.
- **Bug nhỏ, trực tiếp liên quan:** có thể sửa cùng PR nếu test và mô tả phân biệt rõ.
- **Bug độc lập, ít rủi ro:** ghi nhận thành issue với điều kiện tái hiện và owner.
- **Nghi vấn chưa xác minh:** hỏi owner hoặc tạo test/điều tra trước khi kết luận.

Ví dụ, khi thêm phụ phí vùng xa, phát hiện điều kiện miễn phí hiện dùng **>** trong khi hợp đồng yêu cầu **>=**. Đây là bug trực tiếp ở cùng phép tính và cần test tại ngưỡng. Có thể sửa cùng PR nếu mô tả rõ **thay đổi hành vi tại biên**.

Ngược lại, phát hiện một endpoint báo cáo không liên quan đang thiếu pagination không nên tự động đưa vào PR tính phí.

## 24. Giữ tương thích khi thay đổi code được nhiều nơi sử dụng

Một cải thiện nhỏ ở method có thể ảnh hưởng nhiều caller:

- Đổi chữ ký public.
- Đổi thứ tự tham số.
- Đổi kiểu trả về.
- Đổi exception.
- Đổi JSON field hoặc message schema.
- Đổi default config.
- Đổi thứ tự event hoặc trạng thái.

Trước khi làm, xác định:

1. Ai đang gọi API?
2. Caller nào có thể được cập nhật cùng lúc?
3. Có consumer ngoài repository không?
4. Có cần overload hoặc adapter tương thích không?
5. Có versioning/deprecation cần áp dụng không?
6. Có thể triển khai theo pha mà vẫn giữ hệ thống nhất quán không?

Nếu phải thay hợp đồng rộng, việc đó có thể không còn là cải thiện cục bộ. Hãy tách thành kế hoạch tương thích rõ ràng thay vì gắn nhãn cleanup.

## 25. Bài tập tự luyện

### Tình huống A — Thêm tính năng và đặt tên hằng số

Bạn được giao thêm phụ phí vùng xa. Trong phương thức đang sửa có hai giá trị phí viết trực tiếp và một biến tên total.

**Câu hỏi:** Có thể đặt tên hằng số và đổi tên biến trong cùng PR không?

**Gợi ý:** Có, nếu thay đổi gắn trực tiếp với phép tính, không đổi hợp đồng và diff vẫn dễ review. Test phải bảo vệ kết quả cũ khi remoteArea không được chọn.

### Tình huống B — Tiện tay thay framework

Trong lúc sửa một controller, bạn thấy framework hiện tại không phải lựa chọn yêu thích và muốn chuyển toàn bộ module sang framework khác.

**Câu hỏi:** Đây có phải cải thiện cục bộ phù hợp?

**Gợi ý:** Thường không. Cần đánh giá riêng về lợi ích, migration, compatibility và phạm vi nhiều thành phần. Ghi thành công việc riêng trừ khi framework là nguyên nhân trực tiếp khiến yêu cầu hiện tại không thể thực hiện an toàn.

### Tình huống C — Trùng cú pháp nhưng khác nghiệp vụ

Hai thị trường có cùng mức phí hôm nay, nhưng owner và lịch thay đổi khác nhau.

**Câu hỏi:** Có nên gom thành một policy chung?

**Gợi ý:** Chưa chắc. Xác nhận chúng có cùng khái niệm và cùng lý do thay đổi không. Nếu độc lập, gom có thể tạo ghép nối không mong muốn.

### Tình huống D — Test cũ đang đỏ

Trước khi sửa một method, unit test đã thất bại trên nhánh chính vì một lỗi môi trường. Sau khi refactor, test vẫn đỏ.

**Câu hỏi:** Có thể kết luận refactor gây lỗi không?

**Gợi ý:** Chưa. Cần phân biệt baseline, xác minh lỗi môi trường và chạy lại trong điều kiện phù hợp. Ghi rõ phần nào chưa có bằng chứng.

### Tình huống E — Thêm validation không được yêu cầu

Một method cũ chấp nhận chuỗi rỗng. Khi chạm vào để thêm tính năng, bạn muốn thêm validation và ném exception.

**Câu hỏi:** Đây có phải chỉ là cleanup?

**Gợi ý:** Không mặc định. Nó đổi hành vi đối với input đó. Cần xác nhận hợp đồng, caller và loại lỗi; phân loại thành bug fix/contract change nếu cần.

### Tình huống F — PR có 40 file đổi format

Một thay đổi nhỏ bổ sung test cho lỗi thanh toán nhưng developer format toàn bộ module, tạo diff 40 file.

**Câu hỏi:** Có nên giữ tất cả trong cùng PR?

**Gợi ý:** Thường nên tách format-only để reviewer tập trung vào logic và test. Chỉ giữ chung nếu có lý do phụ thuộc rõ và mỗi mục tiêu vẫn review được riêng.

### Tình huống G — Không có test tự động

Một lớp cũ phụ thuộc database thật và không có test. Thay đổi sắp tới liên quan đến số dư tài khoản.

**Câu hỏi:** Nên sửa trực tiếp rồi hy vọng kiểm thử thủ công ổn?

**Gợi ý:** Cần tạo điểm tựa kiểm chứng trước: xác định hợp đồng, dữ liệu đại diện, test ở ranh giới hoặc môi trường kiểm soát. Nếu chưa thể chứng minh an toàn, cần ghi rõ blocker và bước chuẩn bị.

### Tình huống H — Một helper mới chỉ chuyển lời gọi

Bạn tạo ba lớp mới nhưng mỗi lớp chỉ gọi phương thức kế tiếp, không cách ly phụ thuộc hay làm rõ trách nhiệm.

**Câu hỏi:** Có phải code đã được cải thiện vì tách nhỏ hơn?

**Gợi ý:** Không nhất thiết. Số lớp tăng có thể làm đường đi khó hiểu hơn. Chỉ tạo abstraction khi nó giải quyết một ranh giới hoặc biến động thực tế.

## 26. Checklist trước khi hoàn tất một cải thiện cục bộ

- **Yêu cầu chính đã được thực hiện đúng chưa?**
- **Phần cải thiện có liên quan trực tiếp đến vùng đang sửa không?**
- **Có mô tả được lợi ích cụ thể không?**
- **Baseline và hành vi cần giữ đã được xác định chưa?**
- **Có phân biệt bug, feature và refactor không?**
- **Caller, API, schema và tác dụng phụ có được xem xét không?**
- **Test có bao gồm trường hợp cũ và hành vi mới không?**
- **Diff có chứa cleanup không liên quan hoặc format diện rộng không?**
- **Có tạo abstraction, interface hoặc tầng chuyển tiếp thừa không?**
- **Các giới hạn kiểm thử hoặc rủi ro còn lại đã được ghi rõ chưa?**
- **Nếu công việc vượt phạm vi, đã tách issue/PR và chỉ định owner chưa?**
- **Reviewer có thể nhận ra điều gì đổi và bằng chứng nào xác nhận không?**

---

**Ghi nhớ:** Cải thiện cục bộ là cách làm code hiện hữu tốt hơn từng bước khi đang thực hiện thay đổi cần thiết. Hãy hiểu caller và hợp đồng trước, ghi baseline, chọn một cải thiện gắn với vùng đang chạm, giữ hành vi ngoài yêu cầu và kiểm chứng bằng test phù hợp. **Đừng biến Boy Scout Rule thành lý do viết lại mọi thứ**: khi phạm vi tăng, hợp đồng rộng hoặc rủi ro khó kiểm soát, hãy tách công việc riêng. Những thay đổi nhỏ, có mục tiêu và có bằng chứng sẽ giúp hệ thống dễ hiểu, đáng tin cậy và dễ thay đổi hơn theo thời gian.
