# Chuyển yêu cầu thành hành vi có thể kiểm tra

Một tính năng có thể **chạy không lỗi**, được viết gọn gàng và đạt tỷ lệ bao phủ kiểm thử cao nhưng vẫn trả kết quả sai với mong đợi của người dùng. Nguyên nhân thường không nằm ở cú pháp Java mà ở khoảng cách giữa **điều người dùng yêu cầu**, **điều nhóm phát triển hiểu** và **điều chương trình thực sự làm**.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những thuộc tính quyết định mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Tính đúng đắn**, bước nền tảng là biến một yêu cầu bằng ngôn ngữ tự nhiên thành **quy tắc rõ ràng, hành vi quan sát được và bằng chứng kiểm tra được**. Khi đó, lập trình viên biết mình phải xây dựng gì, người kiểm thử biết phải xác minh gì và người phụ trách nghiệp vụ có cơ sở để chấp nhận kết quả.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện những chỗ mơ hồ trong yêu cầu và đặt câu hỏi để làm rõ trước khi triển khai.
- Chuyển yêu cầu thành **điều kiện đầu vào, đầu ra, quy tắc nghiệp vụ, tình huống lỗi và tiêu chí chấp nhận**.
- Viết ví dụ hành vi theo mẫu **Given–When–Then**, bao gồm các giá trị biên.
- Liên kết yêu cầu với mã Java và kiểm thử JUnit để phát hiện sai khác giữa mong đợi và thực tế.
- Phân biệt việc **kiểm thử chạy thành công** với việc **đã có đủ bằng chứng cho tính đúng đắn**.

## 1. Tính đúng đắn bắt đầu từ yêu cầu có thể xác minh

**Tính đúng đắn (correctness)** là mức độ hành vi của phần mềm đáp ứng những yêu cầu và quy tắc đã được xác định. Không thể kết luận chương trình đúng chỉ vì chương trình biên dịch thành công, không ném ngoại lệ hoặc vượt qua các bài kiểm thử do chính người viết mã lựa chọn.

Xét yêu cầu ban đầu:

> “Đơn hàng từ 500.000 đồng được miễn phí giao hàng.”

Câu này có vẻ đơn giản nhưng chưa đủ để triển khai một cách nhất quán:

- “Giá trị đơn hàng” là trước hay sau khi áp dụng mã giảm giá?
- Có tính thuế, phí gói quà hoặc phí vận chuyển vào ngưỡng 500.000 đồng không?
- Chính xác **500.000 đồng** có được miễn phí không?
- Áp dụng cho mọi phương thức vận chuyển và mọi địa chỉ giao hàng?
- Nếu tổng tiền bằng 0, âm hoặc chưa được tính xong thì xử lý thế nào?
- Khi không đạt ngưỡng, phí giao hàng là bao nhiêu?

Hai lập trình viên có thể viết hai cách xử lý khác nhau và cả hai đều cho rằng mình đã làm đúng. Vì thế, **việc đầu tiên là thống nhất ý nghĩa của yêu cầu**, không phải viết câu lệnh `if`.

## 2. Từ câu mô tả sang một hợp đồng hành vi

Để minh họa, giả sử nhóm sản phẩm đã xác nhận **các quy tắc sau** cho chức năng *tính phí giao hàng tiêu chuẩn nội địa*. Đây là đặc tả giả định của ví dụ, không phải quy tắc chung của thương mại điện tử.

| Mã | Quy tắc đã làm rõ | Kết quả có thể kiểm tra |
| --- | --- | --- |
| SHIP-01 | Đầu vào là tổng tiền hàng **sau giảm giá, chưa gồm phí giao hàng**, tính bằng **đồng Việt Nam nguyên đơn vị (VND)** | Hàm nhận một số nguyên biểu diễn số đồng |
| SHIP-02 | Tổng tiền hàng **từ 500.000 VND trở lên** | Phí giao hàng bằng **0 VND** |
| SHIP-03 | Tổng tiền hàng **từ 0 đến dưới 500.000 VND** | Phí giao hàng bằng **30.000 VND** |
| SHIP-04 | Tổng tiền hàng âm | Từ chối với lỗi đầu vào không hợp lệ |
| SHIP-05 | Tính phí không thay đổi đơn hàng hay gọi dịch vụ bên ngoài | Cùng đầu vào hợp lệ luôn cho cùng kết quả |

**Phạm vi:** các quy tắc này chỉ áp dụng cho hình thức giao tiêu chuẩn nội địa. Giao nhanh, giao quốc tế, miễn phí theo hạng thành viên và điều kiện đặt hàng thành công là những yêu cầu khác, cần đặc tả riêng nếu sản phẩm có hỗ trợ.

Chúng ta có thể diễn đạt quy tắc tính phí bằng một hàm:

\[
\operatorname{shippingFee}(t)=
\begin{cases}
\text{lỗi}, & t<0\\
30\,000, & 0\le t<500\,000\\
0, & t\ge 500\,000
\end{cases}
\]

Trong đó \(t\) là tổng tiền hàng sau giảm giá, tính bằng VND. Công thức nêu rõ **ranh giới** và **kết quả mong đợi**; vì thế, nó dễ được kiểm tra và chuyển thành mã hơn câu nói ban đầu.

### Những thành phần nên có trong một đặc tả hành vi

| Thành phần | Câu hỏi | Ví dụ ở chức năng tính phí |
| --- | --- | --- |
| Đầu vào | Nhận dữ liệu gì, kiểu gì, đơn vị gì? | `long`, số nguyên VND sau giảm giá |
| Tiền điều kiện | Điều gì phải đúng trước khi xử lý? | Tổng tiền đã được tính và không âm |
| Quy tắc | Với điều kiện nào, kết quả nào được chọn? | `t >= 500_000` thì phí bằng 0 |
| Hậu điều kiện | Sau khi xử lý, điều gì phải đúng? | Phí thuộc tập {0, 30.000} VND |
| Xử lý sai đầu vào | Nếu không đáp ứng điều kiện thì sao? | Báo `IllegalArgumentException` |
| Tác dụng phụ | Hàm có ghi dữ liệu hoặc gọi bên ngoài? | Không có |
| Ngoại lệ phạm vi | Điều gì chưa được đặc tả trong chức năng này? | Giao quốc tế, giao hỏa tốc |

Một yêu cầu **kiểm tra được** khi có thể xác định ít nhất một phép quan sát hoặc phép thử giúp phân biệt **đạt** và **không đạt**. Những câu như “phí giao hàng phải hợp lý” hoặc “chức năng phải chạy tốt” cần được làm rõ thêm vì chưa có thước đo hay kết quả mong đợi.

## 3. Viết tiêu chí chấp nhận dưới dạng Given–When–Then

**Given–When–Then** giúp mô tả một tình huống từ góc nhìn hành vi:

- **Given** (*Cho trước*): trạng thái hoặc điều kiện ban đầu.
- **When** (*Khi*): hành động hoặc sự kiện cần kiểm tra.
- **Then** (*Thì*): kết quả quan sát được phải xảy ra.

Ví dụ:

~~~gherkin
Feature: Tính phí giao hàng tiêu chuẩn nội địa

  Scenario: Đạt đúng ngưỡng miễn phí
    Given tổng tiền hàng sau giảm giá là 500000 VND
    When hệ thống tính phí giao hàng
    Then phí giao hàng là 0 VND

  Scenario: Thấp hơn ngưỡng đúng một đồng
    Given tổng tiền hàng sau giảm giá là 499999 VND
    When hệ thống tính phí giao hàng
    Then phí giao hàng là 30000 VND

  Scenario: Tổng tiền không hợp lệ
    Given tổng tiền hàng sau giảm giá là -1 VND
    When hệ thống tính phí giao hàng
    Then hệ thống từ chối đầu vào với lỗi đã quy định
~~~

Đây là các tình huống mô tả hành vi, không nhất thiết phải dùng công cụ BDD chuyên dụng. Chúng có thể được chuyển thành kiểm thử JUnit thông thường. Điều quan trọng là **người phụ trách nghiệp vụ và người phát triển hiểu cùng một kết quả mong đợi**.

### Bao phủ các lớp tình huống

Một trường hợp “đơn hàng 600.000 đồng được miễn phí” chưa đủ để chứng minh toàn bộ quy tắc. Cần xét:

| Loại tình huống | Dữ liệu ví dụ | Kết quả theo đặc tả |
| --- | ---: | ---: |
| Giá trị hợp lệ thấp nhất | 0 | 30.000 |
| Dưới ngưỡng | 120.000 | 30.000 |
| **Sát dưới ngưỡng** | **499.999** | **30.000** |
| **Đúng ngưỡng** | **500.000** | **0** |
| Sát trên ngưỡng | 500.001 | 0 |
| Lớn hơn nhiều so với ngưỡng | 2.000.000 | 0 |
| Đầu vào không hợp lệ | -1 | Lỗi |

Việc tập trung vào **giá trị biên** có lý do: sai sót `>` thay vì `>=` thường không lộ ra khi chỉ kiểm thử những giá trị cách ngưỡng quá xa.

## 4. Chuyển đặc tả thành mã Java

Sau khi các bên đã thống nhất quy tắc, phần cài đặt có thể ngắn và rõ:

~~~java
public final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    private ShippingFeePolicy() {
        // Utility class: khong can tao doi tuong.
    }

    public static long calculate(long merchandiseTotalVnd) {
        if (merchandiseTotalVnd < 0) {
            throw new IllegalArgumentException(
                "merchandiseTotalVnd must not be negative"
            );
        }

        if (merchandiseTotalVnd >= FREE_THRESHOLD_VND) {
            return 0L;
        }

        return STANDARD_FEE_VND;
    }
}
~~~

Ở đây, kiểu `long` được chọn vì đầu vào là **số nguyên VND đã quy định**, không có phần thập phân. Nếu nghiệp vụ có số tiền nhiều đơn vị hoặc phần lẻ, cần mô hình tiền tệ có đơn vị và quy tắc làm tròn rõ ràng, chẳng hạn `BigDecimal` kết hợp mã tiền tệ; không nên ngầm chuyển tiền sang `double` rồi so sánh.

Chú ý sự liên hệ giữa quy tắc và mã:

- `SHIP-01` thể hiện qua tên tham số và đơn vị `Vnd` trong tên.
- `SHIP-04` nằm ở nhánh kiểm tra tổng âm.
- `SHIP-02` nằm ở phép so sánh `>= FREE_THRESHOLD_VND`.
- `SHIP-03` nằm ở nhánh trả phí tiêu chuẩn.
- `SHIP-05` được hỗ trợ bởi việc hàm chỉ dựa vào tham số và trả kết quả, không đọc trạng thái bên ngoài.

Tên biến, hằng số và cấu trúc chương trình giúp mã **dễ hiểu và dễ thay đổi**, nhưng **tính đúng đắn** vẫn phải được xác nhận bằng phép kiểm tra độc lập với chính mã đó.

## 5. Chuyển tiêu chí thành kiểm thử JUnit 5

Một bộ kiểm thử nhỏ có thể kiểm tra trực tiếp những tình huống đã thống nhất:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeePolicyTest {

    @ParameterizedTest
    @CsvSource({
        "0,       30000",
        "120000,  30000",
        "499999,  30000",
        "500000,  0",
        "500001,  0",
        "2000000, 0"
    })
    void returnsExpectedFeeForValidTotal(long totalVnd, long expectedFeeVnd) {
        assertEquals(expectedFeeVnd, ShippingFeePolicy.calculate(totalVnd));
    }

    @Test
    void rejectsNegativeTotal() {
        assertThrows(
            IllegalArgumentException.class,
            () -> ShippingFeePolicy.calculate(-1L)
        );
    }
}
~~~

Các giá trị `expectedFeeVnd` xuất phát từ **bảng quy tắc đã được xác nhận**, chứ không tính lại bằng cùng thuật toán trong hàm đang được kiểm tra. Nếu bài kiểm thử sao chép nguyên logic triển khai để tạo kết quả mong đợi, cả mã và test có thể sai theo cùng một cách.

Kiểm thử đơn vị này phù hợp với **logic tính phí thuần túy**. Khi dữ liệu tổng tiền thực sự được tạo từ giỏ hàng, mã giảm giá hoặc cơ sở dữ liệu, cần thêm kiểm thử ở mức tích hợp để chắc chắn hệ thống truyền vào **tổng sau giảm giá** theo đúng hợp đồng. Một hàm tính phí đúng vẫn có thể cho kết quả nghiệp vụ sai nếu tầng gọi truyền **tổng trước giảm giá**.

## 6. Tiêu chí đúng đắn không chỉ là giá trị trả về

Trong ứng dụng thực tế, hành vi có thể bao gồm **thay đổi trạng thái**, **ghi dữ liệu**, **phát sự kiện** và **giao tiếp hệ thống khác**. Khi đó, tiêu chí chấp nhận phải nêu cả những điều được phép và không được phép xảy ra.

Ví dụ, đối với chức năng xác nhận thanh toán, giả sử quy tắc đã được nghiệp vụ xác nhận:

| Trạng thái ban đầu | Sự kiện | Trạng thái mong đợi | Tác dụng phụ mong đợi |
| --- | --- | --- | --- |
| `PENDING` | Thanh toán thành công | `PAID` | Lưu một lần thanh toán hợp lệ |
| `PAID` | Nhận lại đúng thông báo thanh toán đã xử lý | `PAID` | Không ghi trùng lần thanh toán |
| `CANCELLED` | Nhận thông báo thanh toán thành công | Theo chính sách xử lý ngoại lệ đã thống nhất | Không tự ý chuyển sang `PAID` |

Ở ví dụ này, cần làm rõ thêm quy tắc xử lý tiền đã thu khi đơn bị hủy; bảng chỉ cho thấy cách mô tả **chuyển trạng thái và tác dụng phụ**, chưa phải đặc tả đầy đủ của hệ thống thanh toán.

Với xử lý song song, một tình huống khác phải xét là **hai thông báo đến gần như đồng thời**. Hai kiểm thử đơn vị chạy tuần tự có thể đều qua, trong khi hệ thống vẫn ghi trùng giao dịch vì thiếu ràng buộc duy nhất hoặc cơ chế đồng bộ. Khi tính đúng đắn phụ thuộc vào trạng thái chia sẻ, cần kiểm thử và bảo vệ cả những điều kiện đồng thời có thể xảy ra.

## 7. Những kỹ thuật giúp làm rõ đặc tả

### Phân lớp tương đương và kiểm tra giá trị biên

Thay vì kiểm tra mọi số nguyên có thể có, chia đầu vào thành **những nhóm được dự kiến xử lý giống nhau**: số âm, từ 0 đến 499.999, từ 500.000 trở lên. Sau đó chọn giá trị đại diện và các điểm sát ranh giới để bắt lỗi so sánh.

### Bảng quyết định

Khi quy tắc có nhiều điều kiện, lập bảng kết hợp điều kiện và kết quả. Ví dụ nếu thêm loại giao hàng hoặc quyền lợi thành viên, cần trả lời rõ **quy tắc nào được ưu tiên** khi các điều kiện cùng đúng. Bảng quyết định giúp phát hiện tổ hợp bị bỏ sót hoặc các quy tắc mâu thuẫn trước khi viết nhiều nhánh `if`.

### Kiểm thử theo trạng thái

Với đối tượng có vòng đời (đơn hàng, hồ sơ, yêu cầu phê duyệt), hãy liệt kê các trạng thái, sự kiện và chuyển đổi **được phép hoặc bị từ chối**. Test phải kiểm tra trạng thái sau cùng, dữ liệu đã ghi và tác dụng phụ quan trọng.

### Bất biến và thuộc tính

Một **bất biến (invariant)** là điều luôn phải đúng trong phạm vi đã xác định. Với hàm tính phí ở trên:

- Mọi đầu vào không âm chỉ có thể trả về **0 hoặc 30.000** VND.
- Khi tổng tiền tăng, phí giao hàng theo chính sách này **không được tăng**.
- Với cùng đầu vào hợp lệ, hàm luôn cho cùng kết quả.

Các thuộc tính này có thể được kiểm tra bằng các giá trị sinh tự động (property-based testing), bổ sung cho các ca ví dụ cố định. Tuy nhiên, thuộc tính cũng phải bắt nguồn từ quy tắc nghiệp vụ; không được tự giả định những điều sản phẩm chưa cam kết.

## 8. Từ kiểm thử đến bằng chứng đúng đắn

Cần phân biệt ba nhận định:

1. **Test chạy qua:** chương trình cho kết quả mong đợi trong các trường hợp đã viết.
2. **Đã kiểm tra các yêu cầu quan trọng:** có liên kết rõ từ từng quy tắc và rủi ro đến các tình huống kiểm thử phù hợp.
3. **Hệ thống đủ điều kiện chấp nhận:** cả hành vi, tích hợp, dữ liệu và các rủi ro cần thiết đều được xác minh theo tiêu chí đã thống nhất.

Nhận định thứ nhất **không tự suy ra** hai nhận định còn lại. Chẳng hạn, 100% line coverage chỉ cho biết các dòng đã được thực thi trong quá trình kiểm thử; nó không chứng minh rằng đã kiểm tra ngưỡng 500.000 hay tổng tiền sau giảm giá.

Một **bảng truy vết yêu cầu (traceability matrix)** giúp quan sát phần còn thiếu:

| Yêu cầu | Hành vi cần chứng minh | Kiểm thử |
| --- | --- | --- |
| SHIP-01 | Đầu vào thể hiện tổng sau giảm giá, đúng đơn vị VND | Kiểm thử tích hợp từ giỏ hàng và mã giảm giá |
| SHIP-02 | Tổng từ 500.000 VND được miễn phí | Test 500.000, 500.001, 2.000.000 |
| SHIP-03 | Tổng dưới 500.000 VND chịu phí 30.000 | Test 0, 120.000, 499.999 |
| SHIP-04 | Tổng âm bị từ chối | Test -1 và kiểm tra loại lỗi |
| SHIP-05 | Không phát sinh thay đổi trạng thái ngoài ý muốn | Unit test và kiểm tra ranh giới gọi hàm |

Đây là cách biến câu “đã kiểm thử chức năng tính phí” thành bằng chứng có thể xem xét. Trong dự án lớn, bảng này có thể được quản lý bằng ID yêu cầu, tên test, trạng thái thực thi và lịch sử thay đổi.

## 9. Quy trình thực hiện trong công việc hằng ngày

Một quy trình ngắn, có thể áp dụng từ lúc nhận yêu cầu đến lúc review:

**Bước 1 — Viết lại kết quả người dùng cần.** Mô tả ai thao tác, điều kiện ban đầu và điều gì phải thay đổi. Tách các mục tiêu chung chung như “dễ dùng” ra để bổ sung thước đo riêng.

**Bước 2 — Liệt kê điểm mơ hồ và xác nhận quyết định.** Hỏi về ranh giới, đơn vị, trường hợp lỗi, ngoại lệ, trạng thái và phạm vi. Ghi lại quyết định với người có thẩm quyền nghiệp vụ.

**Bước 3 — Tạo bảng quy tắc và ví dụ kiểm tra.** Gán ID cho các quy tắc, mô tả đầu vào, đầu ra và tác dụng phụ; viết tối thiểu trường hợp bình thường, trường hợp biên và dữ liệu không hợp lệ.

**Bước 4 — Chọn mức kiểm thử.** Dùng unit test cho quy tắc độc lập, integration test cho tương tác thành phần và dữ liệu, contract test cho giao tiếp giữa các hệ thống, end-to-end test cho luồng nghiệp vụ quan trọng khi cần.

**Bước 5 — Triển khai và đối chiếu với đặc tả.** Đặt tên miền nghiệp vụ rõ ràng, kiểm tra tiền điều kiện và bảo vệ bất biến. Không lấy hành vi tình cờ của chương trình làm tiêu chí chấp nhận.

**Bước 6 — Review khoảng trống và duy trì truy vết.** Khi thay đổi yêu cầu, cập nhật quy tắc và test tương ứng. Khi phát hiện bug, bổ sung kiểm thử hồi quy để chứng minh lỗi đã được sửa và hạn chế tái xuất hiện.

Không cần viết hàng trăm test cho một hàm đơn giản. Cần ưu tiên **những kết quả có ý nghĩa nghiệp vụ, các điểm dễ nhầm và hậu quả lỗi nghiêm trọng**.

## 10. Các lỗi thường gặp khi chuyển yêu cầu thành mã

| Cách làm dễ gây lỗi | Vì sao nguy hiểm | Cách cải thiện |
| --- | --- | --- |
| Lập trình trực tiếp từ một câu yêu cầu mơ hồ | Mỗi người tự suy diễn ranh giới | Xác nhận quy tắc và ví dụ trước khi viết mã |
| Chỉ test một trường hợp “thành công” | Bỏ qua giá trị biên và dữ liệu sai | Phân lớp tương đương, kiểm tra biên, trường hợp lỗi |
| Tự tính kết quả mong đợi bằng chính thuật toán đang test | Mã và test có thể lặp lại cùng một lỗi | Lấy expected từ bảng quy tắc hoặc nguồn nghiệp vụ độc lập |
| Chỉ kiểm tra giá trị trả về | Không nhìn thấy ghi trùng dữ liệu hoặc phát sự kiện sai | Kiểm tra trạng thái, dữ liệu lưu và tác dụng phụ |
| Đồng nhất coverage với đúng đắn | Coverage không đánh giá tính đầy đủ của tình huống | Truy vết yêu cầu và kiểm thử theo rủi ro |
| Không cập nhật test khi thay đổi chính sách | Test cũ có thể xác nhận hành vi không còn đúng | Đồng bộ yêu cầu, tiêu chí chấp nhận, mã và test |

## 11. Bài tập thực hành

Sản phẩm đưa ra yêu cầu mới: **“Đơn hàng có mã ưu đãi thì tính phí giao hàng theo giá trị sau khi trừ ưu đãi.”** Giả sử ngưỡng miễn phí và mức phí vẫn như các quy tắc SHIP-02, SHIP-03 ở trên.

**Câu hỏi A.** Có thể triển khai ngay không? Bạn cần làm rõ thêm ít nhất ba điều gì?

**Câu hỏi B.** Với một đơn hàng có tổng trước giảm giá **520.000 VND**, giảm **30.000 VND**, phí giao hàng theo quy tắc đã biết là bao nhiêu?

**Câu hỏi C.** Viết ít nhất ba tình huống kiểm thử, trong đó có một trường hợp nằm **đúng ngưỡng 500.000 VND sau giảm giá**.

### Gợi ý

- Cần xác định tổng trước giảm có bao gồm loại phí nào, cách tính mã giảm (theo tiền hay phần trăm), có thể dùng nhiều mã hay không, cách làm tròn và điều gì xảy ra khi giảm vượt tổng tiền hàng.
- Với dữ liệu của câu B, tổng sau giảm là **490.000 VND**. Nếu đây là tổng tiền hàng hợp lệ dùng cho tính phí tiêu chuẩn nội địa, phí giao hàng là **30.000 VND**.
- Những ca kiểm tra phù hợp gồm: tổng sau giảm **499.999 VND → 30.000 VND**; **500.000 VND → 0 VND**; **500.001 VND → 0 VND**. Bổ sung test để xác nhận tầng tạo đơn chuyển **giá trị sau giảm** vào hàm tính phí.

## Ghi nhớ

**Tính đúng đắn bắt đầu từ một kết quả mong đợi được xác định rõ.** Muốn kiểm tra mã có đúng hay không, trước hết phải biết **đúng theo quy tắc nào**, trong **điều kiện nào** và bằng **bằng chứng gì**. Chuyển yêu cầu thành bảng quy tắc, tiêu chí chấp nhận, tình huống kiểm thử và liên kết truy vết giúp phát hiện sai khác sớm, làm mã dễ hiểu hơn và giảm rủi ro khi thay đổi.
