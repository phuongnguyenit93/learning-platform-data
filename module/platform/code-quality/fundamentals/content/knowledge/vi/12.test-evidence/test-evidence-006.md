# Độ bao phủ câu lệnh, nhánh và giới hạn diễn giải

Trong chương **Bằng chứng kiểm thử** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học cách đọc một trong những nhóm chỉ số xuất hiện thường xuyên trên báo cáo CI: **độ bao phủ mã nguồn** (*code coverage*). Đặc biệt, hai cách đo phổ biến là **độ bao phủ câu lệnh** (*statement coverage*) và **độ bao phủ nhánh** (*branch coverage*).

Mục tiêu của module là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Một bộ kiểm thử tốt giúp người bảo trì có bằng chứng khi sửa chương trình. Nhưng một báo cáo “coverage 100%” dễ tạo cảm giác yên tâm quá mức nếu không hiểu chính xác số đó đo điều gì.

> **Coverage cho biết phần cấu trúc chương trình nào đã được thực thi trong những lần kiểm thử được đo. Nó không tự cho biết kết quả mong đợi đúng hay chưa, assertion có đủ mạnh hay không, hoặc còn lỗi nào nằm ngoài các tình huống đã chạy.**

Bài này tập trung vào cách diễn giải *statement coverage*, *branch coverage* và những giới hạn của chúng trong công việc phát triển Java.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích độ bao phủ câu lệnh và độ bao phủ nhánh đo điều gì.
2. Phân biệt một dòng mã đã được chạy với một hành vi đã được xác minh.
3. Tính mức bao phủ từ ví dụ nhỏ, nhận ra vì sao bao phủ câu lệnh 100% vẫn có thể thiếu nhánh.
4. Giải thích vì sao bao phủ nhánh 100% vẫn có thể bỏ sót lỗi ở giá trị biên, tổ hợp điều kiện, trạng thái hoặc tích hợp.
5. Đọc báo cáo coverage trong Java mà không nhầm độ bao phủ dòng lệnh với độ bao phủ câu lệnh hoặc nhánh.
6. Chọn ca kiểm thử bổ sung dựa trên yêu cầu và rủi ro, thay vì chỉ cố tăng một tỷ lệ phần trăm.
7. Kết hợp coverage với assertion có ý nghĩa, giá trị biên, kiểm thử đột biến và kiểm thử tích hợp.
8. Diễn đạt trung thực phạm vi bằng chứng khi đưa kết quả kiểm thử vào code review hoặc quyết định phát hành.

## 2. Coverage thực chất đo cái gì?

Công cụ coverage ghi nhận những phần mã đã được thực thi trong các lượt chạy được theo dõi. Tùy loại chỉ số và công cụ, “phần mã” có thể là câu lệnh, dòng nguồn, lệnh bytecode, nhánh điều kiện, phương thức hoặc những đơn vị khác.

Có thể hình dung:

~~~text
Mã chương trình
    |
    +-- Đường chạy được chọn bởi đầu vào và trạng thái
    |          |
    |          v
    |     Các câu lệnh / nhánh được thực thi
    |          |
    |          v
    |     Công cụ ghi nhận coverage
    |
    +-- Các đường chạy chưa xảy ra
               |
               v
         Phần còn thiếu bằng chứng thực thi
~~~

Coverage phụ thuộc vào **tập test được chạy**, **phiên bản chương trình**, **cấu hình công cụ đo** và **phạm vi mã được đưa vào báo cáo**. Một lần chạy chỉ có unit test có thể cho kết quả khác khi gộp thêm integration test. Một phần mã bị loại trừ khỏi báo cáo cũng làm thay đổi mẫu số tính toán.

Coverage là **thông tin về mức độ thực thi**, không phải phép chứng minh tổng quát về tính đúng đắn.

### 2.1. Một mô hình định lượng đơn giản

Với các đơn vị được tính trong phạm vi báo cáo:

\[
\text{Coverage} = \frac{\text{Số đơn vị đã được bao phủ}}{\text{Tổng số đơn vị cần tính}} \times 100\%
\]

Chỉ số cụ thể phụ thuộc vào cách xác định “đơn vị”. Nếu tổng mẫu số có 10 câu lệnh thực thi được và test đã chạy qua 8 câu lệnh, *statement coverage* theo mô hình đó là 80%. Nếu có 6 kết quả nhánh cần xét và test đã thực thi 4, *branch coverage* theo mô hình đó là khoảng 66,7%.

Đây là **ví dụ về phép tính**, không có nghĩa mọi công cụ đều đếm câu lệnh và nhánh theo cùng một cách.

## 3. Độ bao phủ câu lệnh (*statement coverage*)

**Độ bao phủ câu lệnh** là tỷ lệ các câu lệnh thực thi được đã được chạy ít nhất một lần trong tập kiểm thử được đo.

Với cách hiểu khái niệm:

\[
C_{\text{statement}} =
\frac{\text{Số câu lệnh đã thực thi ít nhất một lần}}
{\text{Tổng số câu lệnh thực thi được}}
\times 100\%
\]

Một câu lệnh chỉ cần được thực thi **một lần** để được tính là đã bao phủ. Số lần nó chạy và các giá trị mà nó xử lý không phản ánh trực tiếp vào công thức.

### 3.1. Ví dụ Java: toàn bộ câu lệnh đều chạy nhưng vẫn thiếu nhánh

Giả sử chính sách vận chuyển: đơn hàng từ 500.000 đơn vị tiền nhỏ nhất được miễn phí; đơn thấp hơn chịu phí 30.000.

~~~java
static int shippingFee(long subtotalCents) {
    int fee = 30_000;
    if (subtotalCents >= 500_000) {
        fee = 0;
    }
    return fee;
}
~~~

Bài test đầu tiên:

~~~java
@Test
void offersFreeShippingForLargeOrder() {
    assertEquals(0, shippingFee(600_000));
}
~~~

Với đầu vào `600_000`, các câu lệnh gán giá trị ban đầu, gán lại `fee = 0` và trả về đều chạy. Theo mô hình đếm câu lệnh ở trên, **100% câu lệnh của phương thức đã được thực thi**.

Nhưng điều kiện `subtotalCents >= 500_000` mới chỉ được đánh giá theo nhánh **đúng**. Chưa có lần chạy nào chứng minh phương thức trả phí 30.000 cho đơn **dưới** ngưỡng.

Đây là giới hạn quan trọng: **một lần thực thi tất cả câu lệnh không đồng nghĩa đã kiểm tra tất cả hướng rẽ của luồng điều khiển**.

### 3.2. Chỉ chạy qua câu lệnh chưa đủ để xác minh kết quả

Nếu viết:

~~~java
@Test
void exercisesShippingFee() {
    shippingFee(600_000);
}
~~~

Bài test vẫn thực thi các câu lệnh tương tự, nhưng **không có assertion** nào xác nhận phí phải là 0. Ví dụ, nếu triển khai sai và trả 15.000, bài test này vẫn có thể đỗ miễn là không ném ngoại lệ.

Một bài test có giá trị phải gắn với **yêu cầu và kết quả mong đợi**, chứ không chỉ tạo hoạt động thực thi để tăng coverage.

## 4. Độ bao phủ nhánh (*branch coverage*)

**Độ bao phủ nhánh** đo tỷ lệ những hướng rẽ của luồng điều khiển đã được thực thi. Với một điều kiện `if` đơn giản có thể nhận cả `true` và `false`, ta quan tâm hai kết quả đó.

Theo mô hình đơn giản:

\[
C_{\text{branch}} =
\frac{\text{Số kết quả nhánh đã thực thi}}
{\text{Tổng số kết quả nhánh được tính}}
\times 100\%
\]

Ở ví dụ phí vận chuyển, có hai hướng:

~~~text
           subtotal >= 500_000?
                    |
              +-----+-----+
              |           |
            true         false
              |           |
           fee = 0    giữ fee = 30_000
              |           |
              +-----+-----+
                    |
               return fee
~~~

| Tập đầu vào kiểm thử | Nhánh điều kiện đã xảy ra | Bao phủ câu lệnh theo ví dụ | Bao phủ nhánh theo ví dụ |
| --- | --- | --- | --- |
| Chỉ `600_000` | Chỉ `true` | 100% | 1/2 = 50% |
| `600_000` và `400_000` | `true` và `false` | 100% | 2/2 = 100% |

Đây là minh họa theo **mô hình điều kiện của mã nguồn**. Công cụ cụ thể có thể đo các lệnh rẽ nhánh ở cấp bytecode và báo thêm những chỉ số khác, nên số hiển thị có thể khác cách đếm thủ công.

### 4.1. Bổ sung một ca test nhánh còn thiếu

~~~java
@Test
void chargesShippingBelowThreshold() {
    assertEquals(30_000, shippingFee(400_000));
}
~~~

Test mới khiến nhánh `false` được thực thi và đồng thời xác minh một phần yêu cầu cho đơn hàng dưới ngưỡng. Đây là cách sử dụng coverage hợp lý: **tìm ra nhánh bị bỏ sót, kiểm tra lý do nghiệp vụ và thêm assertion có ý nghĩa**.

### 4.2. Tại sao bao phủ nhánh thường giàu thông tin hơn bao phủ câu lệnh?

Một nhánh `else` có thể không chứa câu lệnh riêng, nhưng vẫn là một tình huống hành vi khác. Branch coverage giúp nhìn thấy tình huống chưa chạy ấy.

Tuy nhiên, nó không nói rõ **giá trị nào trong mỗi nhóm đầu vào** đã được chọn, hoặc liệu các kết quả có được kiểm tra đúng không. Branch coverage bổ sung thông tin cho statement coverage; nó không thay thế phân tích yêu cầu.

## 5. Bao phủ nhánh 100% vẫn có thể để lọt lỗi giá trị biên

Giả sử lập trình viên viết sai toán tử so sánh:

~~~java
// Sai yêu cầu: đúng ngưỡng 500_000 vẫn bị tính phí.
static int shippingFeeWithBug(long subtotalCents) {
    if (subtotalCents > 500_000) {
        return 0;
    }
    return 30_000;
}
~~~

Bộ test sau kiểm tra hai hướng rẽ:

~~~java
@Test
void freeForClearlyLargeOrder() {
    assertEquals(0, shippingFeeWithBug(600_000));
}

@Test
void chargesForClearlySmallOrder() {
    assertEquals(30_000, shippingFeeWithBug(400_000));
}
~~~

Hai test **đều đỗ**, và cả hai kết quả `true`/`false` của điều kiện đã được thực thi. Theo mô hình nhánh của `if` này, **branch coverage là 100%**.

Nhưng bài test ở **đúng ngưỡng** sẽ phát hiện lỗi:

~~~java
@Test
void freeAtExactThreshold() {
    assertEquals(0, shippingFeeWithBug(500_000));
    // FAIL: thực tế là 30_000.
}
~~~

Bảng quyết định cho ngưỡng:

| Tiền hàng | Yêu cầu nghiệp vụ | Phiên bản dùng `>` |
| ---: | --- | --- |
| 499.999 | Phí 30.000 | Đúng |
| 500.000 | Phí 0 | **Sai** |
| 500.001 | Phí 0 | Đúng |

Bài học: **branch coverage kiểm tra hướng rẽ đã được đi qua, nhưng không tự bảo đảm test đã chọn những giá trị quan trọng nhất của hướng rẽ đó**.

Các kỹ thuật bổ sung như **phân tích giá trị biên** (*boundary value analysis*), **phân hoạch tương đương** và **bảng quyết định** giúp chọn đầu vào có ý nghĩa hơn.

## 6. Điều kiện ghép: một nhánh tổng thể có thể che nhiều khả năng

Trong Java, biểu thức điều kiện có thể ghép nhiều mệnh đề:

~~~java
static boolean eligible(boolean premium, long subtotalCents) {
    return premium && subtotalCents >= 200_000;
}
~~~

Hành vi phụ thuộc vào cả hai phần: khách có hạng premium hay không và số tiền có đạt ngưỡng hay không.

| `premium` | `subtotalCents >= 200_000` | Kết quả |
| --- | --- | --- |
| `false` | `false` | `false` |
| `false` | `true` | `false` |
| `true` | `false` | `false` |
| `true` | `true` | `true` |

### 6.1. Đủ hai kết quả của quyết định tổng thể chưa có nghĩa đủ mọi tổ hợp

Nếu chỉ test:

- Khách thường, tiền thấp → `false`.
- Khách premium, tiền cao → `true`.

Ta đã thấy cả hai **kết quả tổng thể** của biểu thức, nhưng chưa kiểm tra khách premium có tiền thấp, hoặc khách thường có tiền cao. Sai sót ở một nhánh nghiệp vụ vẫn có thể bị bỏ qua.

**Cần phân biệt cách đo:** một số công cụ ghi nhận các nhánh của từng phép rẽ ở bytecode do toán tử `&&` tạo ra. Vì vậy, “đã thử kết quả true và false của toàn biểu thức” **không nhất thiết tương đương với 100% branch coverage do công cụ báo**.

### 6.2. Kiểm tra ảnh hưởng riêng của từng điều kiện

Với hai mệnh đề A và B trong `A && B`, ba trường hợp sau giúp thấy mỗi mệnh đề có thể tự thay đổi kết quả khi mệnh đề còn lại được giữ thích hợp:

1. A = `true`, B = `true` → `true`.
2. A = `false`, B = `true` → `false`.
3. A = `true`, B = `false` → `false`.

Đây là trực giác đứng sau những tiêu chí chặt hơn như **Modified Condition/Decision Coverage (MC/DC)**, trong đó cần chứng minh từng điều kiện có ảnh hưởng độc lập đến quyết định theo định nghĩa áp dụng. Không nên coi ba ca ở ví dụ là công thức tổng quát cho mọi biểu thức phức tạp: điều kiện bị ràng buộc, lặp lại hoặc không thể độc lập có thể cần phân tích khác.

### 6.3. Ngắn mạch làm cho việc đo càng cần đúng ngữ nghĩa công cụ

Java đánh giá `&&` và `||` từ trái sang phải và ngắn mạch:

~~~java
if (customer != null && customer.active()) {
    grantBenefit();
}
~~~

Nếu `customer == null`, `customer.active()` không được gọi. Hai nhánh “khách không tồn tại” và “khách tồn tại nhưng không hoạt động” cùng cho kết quả tổng thể `false`, nhưng có hành vi thực thi khác nhau.

Khi phân tích báo cáo cho biểu thức ghép, cần hiểu **những kết quả rẽ nhánh nào công cụ đã instrument**, tránh đồng nhất số phần trăm với “mọi tổ hợp đã được kiểm thử”.

## 7. Vì sao bao phủ đường đi (*path coverage*) cũng khó đạt đầy đủ?

*Path coverage* xét các đường đi khả dĩ qua một đoạn chương trình. Với nhiều điều kiện độc lập, số tổ hợp đường đi có thể tăng rất nhanh.

Ví dụ, nếu có 10 quyết định nhị phân độc lập được thực hiện nối tiếp, có thể tồn tại tới \(2^{10} = 1024\) tổ hợp kết quả. Vòng lặp với số vòng tùy ý và các lần gọi phụ thuộc môi trường có thể tạo không gian đường đi lớn hơn rất nhiều, thậm chí không có giới hạn hữu hạn đơn giản.

Do đó:

- **Statement coverage**: mỗi câu lệnh đã chạy chưa?
- **Branch coverage**: những hướng rẽ được đo đã xảy ra chưa?
- **Path coverage**: những đường đi cụ thể qua các hướng rẽ đã xảy ra chưa?

Branch coverage 100% **không đồng nghĩa** path coverage 100%. Một test có thể đi qua nhánh A-true trong một ca và B-true trong một ca khác, nhưng chưa chạy tổ hợp A-true rồi B-true nếu tổ hợp đó có ý nghĩa.

Trong thực tế, ta thường chọn **đường đi rủi ro cao** thay vì cố bao phủ mọi tổ hợp. Các kỹ thuật như pairwise, bảng quyết định, kiểm thử trạng thái, property-based testing hoặc fuzzing có thể hỗ trợ tùy loại vấn đề.

## 8. Ví dụ Java hoàn chỉnh: từ nhánh thiếu đến test có căn cứ

Giả sử yêu cầu của hệ thống là:

> Số tiền đơn hàng phải không âm. Khách hàng premium được giảm 10% khi tổng tiền hàng đạt ít nhất 200.000 đơn vị tiền nhỏ nhất. Số tiền chiết khấu được làm tròn xuống đến đơn vị nhỏ nhất. Khách không premium hoặc đơn dưới ngưỡng không được giảm.

### 8.1. Hàm nghiệp vụ

~~~java
public final class DiscountPolicy {
    private DiscountPolicy() {}

    public static long discountCents(boolean premium, long subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (!premium) {
            return 0;
        }

        if (subtotalCents < 200_000) {
            return 0;
        }

        return subtotalCents / 10;
    }
}
~~~

Hàm chứa ba quyết định `if`, mỗi quyết định có hai hướng rẽ `true` và `false` theo mô hình nguồn.

Các tình huống cần xác minh không chỉ là “đã vào nhánh”, mà còn có:

- Đầu vào âm phải ném ngoại lệ.
- Khách thường không được giảm, dù đơn hàng cao.
- Khách premium dưới ngưỡng không được giảm.
- Khách premium **đúng ngưỡng** được giảm.
- Giá trị không chia hết cho 10 phải làm tròn xuống theo phép chia nguyên.

### 8.2. Bộ test JUnit 5 với trường hợp rủi ro

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DiscountPolicyTest {
    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> DiscountPolicy.discountCents(true, -1));
    }

    @Test
    void regularCustomerDoesNotGetDiscount() {
        assertEquals(0,
                DiscountPolicy.discountCents(false, 500_000));
    }

    @Test
    void premiumCustomerBelowThresholdDoesNotGetDiscount() {
        assertEquals(0,
                DiscountPolicy.discountCents(true, 199_999));
    }

    @Test
    void premiumCustomerAtThresholdGetsDiscount() {
        assertEquals(20_000,
                DiscountPolicy.discountCents(true, 200_000));
    }

    @Test
    void discountUsesIntegerRoundingDown() {
        assertEquals(20_001,
                DiscountPolicy.discountCents(true, 200_019));
    }
}
~~~

Với bộ test này, cả hướng đúng và sai của ba `if` đều có tình huống được thực thi, và các assertion kiểm tra **nhiều yêu cầu khác nhau**. Đây là thiết kế test tốt hơn việc chọn ngẫu nhiên vài đầu vào chỉ để đạt màu xanh trên báo cáo.

### 8.3. Bảng đối chiếu nhánh và trường hợp kiểm thử

| Quyết định | Hướng `true` được kiểm tra bởi | Hướng `false` được kiểm tra bởi |
| --- | --- | --- |
| `subtotalCents < 0` | `rejectsNegativeSubtotal` | Các ca đầu vào không âm |
| `!premium` | `regularCustomerDoesNotGetDiscount` | Các ca premium |
| `subtotalCents < 200_000` | `premiumCustomerBelowThresholdDoesNotGetDiscount` | Các ca premium đạt ngưỡng |

Khi thấy một nhánh chưa được bao phủ, ta có thể dùng bảng này để hỏi: **có một trường hợp hợp lệ hoặc lỗi nghiệp vụ tương ứng chưa được test không?** Nếu nhánh thực sự không thể đạt theo hợp đồng, cần xem thiết kế hoặc tiền điều kiện thay vì tạo dữ liệu vô nghĩa để “bôi xanh” báo cáo.

### 8.4. Một số lỗi vẫn có thể tồn tại dù bao phủ đầy đủ

Ngay cả sau khi tất cả nhánh đã chạy, vẫn còn những câu hỏi nằm ngoài hàm:

- `premium` được lấy đúng từ trạng thái khách hàng hay không?
- Có hai luồng cùng dùng một mã giảm giá vượt giới hạn sử dụng hay không?
- Giá trị tiền ở API/database có đúng đơn vị hay bị nhầm đồng với đơn vị nhỏ nhất?
- Đặc tả làm tròn có đúng yêu cầu pháp lý và nghiệp vụ hay không?
- Tỷ lệ chiết khấu có thay đổi theo chiến dịch mà hàm hiện chưa mô hình hóa không?

Các câu hỏi này cần test tích hợp, đối chiếu đặc tả và những bằng chứng khác. **Coverage của một hàm không đánh giá được toàn bộ vòng đời nghiệp vụ.**

## 9. Thực hành đo coverage trong Java: hiểu chỉ số đang xem

Các công cụ coverage Java phổ biến, như **JaCoCo**, instrument chương trình khi test chạy và cung cấp những thước đo về phần mã đã được thực thi.

Một lưu ý quan trọng: **không phải công cụ nào cũng hiển thị “statement coverage” như một chỉ số riêng**. Ví dụ, JaCoCo có các chỉ số như *instruction coverage*, *line coverage*, *branch coverage*, *method coverage* và *complexity coverage*. Các chỉ số này được xây dựng từ thông tin của bytecode và ánh xạ về mã nguồn khi có đủ thông tin debug.

### 9.1. Statement, line và instruction coverage khác nhau

| Chỉ số | Đơn vị được đo | Cách hiểu thực tế |
| --- | --- | --- |
| **Statement coverage** | Câu lệnh thực thi được theo định nghĩa của công cụ/mô hình. | Câu lệnh đã chạy ít nhất một lần hay chưa? |
| **Line coverage** | Dòng nguồn có mã thực thi được, theo cách ánh xạ của công cụ. | Dòng có lệnh đã chạy toàn bộ, một phần hoặc chưa chạy? |
| **Instruction coverage** | Lệnh trong mã đã biên dịch, chẳng hạn bytecode JVM. | Bao nhiêu lệnh được thực thi? |
| **Branch coverage** | Các hướng rẽ có điều kiện được công cụ đếm. | Những kết quả rẽ nhánh nào chưa được thực thi? |

Một dòng Java có thể chứa **nhiều biểu thức hoặc nhiều nhánh**; một câu lệnh nguồn có thể biên dịch thành nhiều lệnh bytecode. Vì vậy, **100% line coverage không được diễn giải tự động thành 100% statement coverage hay 100% branch coverage**.

### 9.2. Đọc báo cáo theo đúng phạm vi

Khi xem báo cáo coverage, trước tiên cần xác nhận:

1. **Bộ test đã chạy:** chỉ unit test hay còn integration test?
2. **Phạm vi tính:** package/class nào được tính, class nào bị loại trừ?
3. **Phiên bản mã:** báo cáo thuộc commit/build nào?
4. **Định nghĩa chỉ số:** đang xem line, instruction, branch hay một chỉ số khác?
5. **Các điểm thiếu:** nhánh và phương thức chưa chạy thuộc nghiệp vụ quan trọng hay mã phụ trợ?
6. **Cấu hình instrument:** thông tin debug, bộ lọc do công cụ hỗ trợ và cách xử lý mã được sinh có ảnh hưởng kết quả không?

Nếu hai nhóm dùng cấu hình và phạm vi khác nhau, so sánh “nhóm A có 90%, nhóm B có 80%” dễ dẫn đến kết luận sai.

### 9.3. Nhánh trong bytecode và ngoại lệ

Một số công cụ, trong đó có JaCoCo, đếm nhánh dựa trên các lệnh rẽ như `if` và `switch` trong bytecode; **cạnh điều khiển do xử lý ngoại lệ không nhất thiết được tính như branch coverage**. Vì vậy, kiểm tra đường đi `catch` hoặc tình huống ném ngoại lệ phải được thiết kế dựa trên rủi ro, kể cả khi báo cáo nhánh nhìn đã đầy đủ.

Tương tự, các biểu thức ngắn mạch, biểu thức ba ngôi, `switch`, lambda hoặc mã được compiler sinh có thể ảnh hưởng cách một công cụ hiển thị phần chưa bao phủ. Khi một số liệu trông bất thường, hãy xem tài liệu của **đúng phiên bản công cụ** và đối chiếu mã nguồn với các tình huống thực tế.

## 10. Tại sao 100% coverage không đồng nghĩa 100% đúng đắn?

Có nhiều nguyên nhân độc lập:

### 10.1. Oracle có thể sai

*Test oracle* là quy tắc xác định kết quả mong đợi. Nếu yêu cầu thật là miễn phí vận chuyển ở mức 500.000 nhưng test mong phí 30.000 tại đúng ngưỡng, một triển khai sai vẫn có thể làm test đỗ với coverage rất cao.

### 10.2. Assertion có thể yếu hoặc thiếu

Bài test chỉ gọi hàm, hoặc chỉ kiểm tra kết quả khác `null`, không nhất thiết phát hiện sai lệch về giá trị nghiệp vụ. Coverage không đánh giá độ mạnh của assertion.

### 10.3. Các giá trị biên chưa được chọn

Tập test có thể đi qua cả hai nhánh nhưng không có giá trị ở đúng ngưỡng, giá trị âm, số rất lớn hay ngày hết hạn. Lỗi tràn số, sai toán tử so sánh và làm tròn có thể bị bỏ sót.

### 10.4. Các điều kiện và trạng thái tương tác

Nhánh A có thể đã chạy, nhánh B cũng đã chạy, nhưng chưa có trường hợp A và B cùng xảy ra. Với đối tượng có trạng thái, **thứ tự các lời gọi** cũng có thể ảnh hưởng hành vi.

### 10.5. Lỗi tích hợp và môi trường

Unit test có thể dùng fake repository và mock API, nên không phát hiện vấn đề commit, phân quyền, serialization, timeout hay cấu hình của hệ thống thật.

### 10.6. Đồng thời và các sự kiện hiếm

Hai test tuần tự chạy đúng không chứng minh thao tác đọc–kiểm tra–ghi là nguyên tử khi hai luồng cùng xử lý. Không gian các lịch thực thi đồng thời thường lớn hơn nhiều những lần chạy test đã đo.

### 10.7. Chức năng còn thiếu không xuất hiện trong mẫu số

Nếu yêu cầu cần một bước xác thực nhưng bước ấy **chưa được viết**, coverage của các đoạn mã hiện có vẫn có thể là 100%. Coverage không biết những hành vi nghiệp vụ nào lẽ ra phải có nhưng chưa xuất hiện trong codebase.

## 11. Bổ sung bằng chứng: mutation testing và kiểm tra tính chất

Coverage cho biết mã đã chạy; một câu hỏi tiếp theo là **“nếu mã sai một chút, test có nhận ra không?”**.

### 11.1. Kiểm thử đột biến (*mutation testing*)

Công cụ mutation testing tạo những thay đổi nhỏ vào mã, chẳng hạn:

- Đổi `>=` thành `>`.
- Đổi `+` thành `-`.
- Đảo một kết quả Boolean.
- Bỏ một hành động hoặc thay một giá trị trả về.

Sau đó bộ test được chạy trên phiên bản biến đổi. Nếu test phát hiện sự khác biệt và thất bại, mutant được coi là **bị tiêu diệt**. Nếu vẫn đỗ, có thể test thiếu ca hoặc assertion chưa mạnh.

Ví dụ, mutant đổi `subtotalCents >= 500_000` thành `subtotalCents > 500_000` sẽ bị test ở **đúng ngưỡng 500.000** phát hiện, nhưng có thể sống sót nếu chỉ test 400.000 và 600.000 dù branch coverage đã 100%.

**Giới hạn:** có mutant tương đương về hành vi trong miền hợp đồng; không phải mutant sống sót nào cũng là lỗ hổng test. Mutation testing bổ sung tín hiệu, không phải chứng minh tuyệt đối về tính đúng đắn.

### 11.2. Property-based testing

Thay vì chỉ liệt kê vài bộ dữ liệu, ta có thể nêu những tính chất đúng với một miền đầu vào.

Với hàm giảm giá:

- Với `subtotalCents >= 0`, kết quả không âm.
- Với khách không premium, chiết khấu luôn bằng 0.
- Với khách premium, số tiền dưới ngưỡng không được giảm.
- Với các giá trị hợp lệ, chiết khấu không lớn hơn tiền hàng.

Một công cụ property-based testing có thể sinh nhiều trường hợp để tìm phản ví dụ. Nhưng **bộ sinh dữ liệu**, **miền áp dụng** và **tính chất được viết** cũng phải đúng; một tính chất quá yếu vẫn có thể bỏ sót lỗi.

### 11.3. Những loại bằng chứng nên bổ sung theo rủi ro

| Rủi ro | Bằng chứng bổ sung phù hợp |
| --- | --- |
| Sai ở ranh giới số tiền hoặc ngày hết hạn | Giá trị biên, bảng quyết định, ví dụ từ nghiệp vụ. |
| Một điều kiện ghép không thực sự ảnh hưởng kết quả | Ca làm từng điều kiện thay đổi kết quả, phân tích logic, MC/DC khi cần. |
| Assertion yếu | Mutation testing, review oracle và review kết quả mong đợi. |
| Sai sau một chuỗi thao tác | State-transition testing, kiểm thử bất biến trước/sau. |
| Giao dịch bị mất cập nhật | Integration test với lưu trữ thật, lập luận về tính nguyên tử. |
| API không tương thích | Contract test và kiểm thử nhiều phiên bản client. |
| Đầu vào khó lường | Fuzzing, property-based testing, kiểm tra dữ liệu bất thường. |

## 12. Coverage thấp có phải lúc nào cũng xấu?

**Phần mã chưa được thực thi là một tín hiệu cần điều tra.** Tuy nhiên, không phải mọi dòng hoặc nhánh đều có cùng rủi ro và giá trị.

Ví dụ:

- Một nhánh tính phí thanh toán sai có thể làm thất thoát tiền.
- Một nhánh xử lý lỗi khi hệ thống phụ thuộc bị timeout có thể gây mất dữ liệu.
- Một đường log hỗ trợ debug ít quan trọng hơn vẫn có thể được cân nhắc theo mức ưu tiên phù hợp.
- Mã sinh tự động, mã chỉ chạy trên một nền tảng khác hoặc một đường lỗi bất khả đạt dưới giả định đã chứng minh có thể cần cách phân tích riêng.

Không nên bỏ test cho hành vi quan trọng chỉ vì khó kích hoạt. Với nhánh lỗi, có thể cần thiết kế điểm điều khiển như stub, fake, môi trường tích hợp hoặc fault injection để tạo đúng điều kiện.

Ngược lại, ép mọi nhánh trở thành “xanh” bằng test không có assertion, thay đổi code chỉ để đo dễ hơn hoặc loại trừ tùy tiện khỏi báo cáo có thể làm chỉ số đẹp nhưng **làm suy yếu giá trị bằng chứng**.

### 12.1. Trường hợp không thể đạt được

Nếu công cụ báo nhánh chưa chạy nhưng ta tin đó là trạng thái bất khả đạt, cần đặt câu hỏi:

1. Tiền điều kiện hay bất biến nào khiến nhánh đó không thể xảy ra?
2. Bất biến có được kiểm tra hoặc bảo đảm ở mọi điểm gọi không?
3. Nếu giả định sai trong môi trường thực, nhánh ấy có nên xử lý an toàn không?
4. Có thể bỏ mã chết hoặc làm rõ hợp đồng để người đọc hiểu hơn không?

Không nên ghi “unreachable” chỉ dựa vào trực giác. Một trường hợp hiếm trong production có thể là điều test bình thường chưa tái hiện được.

## 13. Dùng coverage như công cụ điều tra trong code review

Một quy trình thực tế khi nhận pull request sửa logic Java:

1. **Đọc yêu cầu trước.** Xác định hành vi cần thêm/sửa, trường hợp biên và điều phải giữ nguyên.
2. **Đọc diff.** Tìm các `if`, `switch`, điều kiện ghép, ngoại lệ và các tác dụng phụ mới.
3. **Xem coverage của mã thay đổi.** Những câu lệnh/nhánh nào vừa thêm hoặc sửa chưa được chạy trong test?
4. **Liên hệ nhánh với nghiệp vụ.** Nhánh chưa chạy là một trường hợp hợp lệ, trường hợp lỗi, điều kiện hiếm hay mã chết?
5. **Bổ sung test có oracle.** Viết assertion về kết quả, ngoại lệ, dữ liệu hoặc sự kiện theo hợp đồng.
6. **Xem lại trường hợp biên dù coverage đã đủ.** Thử đúng ngưỡng, sát ngưỡng và những giá trị bất thường có rủi ro.
7. **Kiểm tra cấp tích hợp nếu cần.** Coverage của unit test không thay thế các bảo đảm từ database, API hay hệ thống chạy đồng thời.
8. **Ghi lại phạm vi bằng chứng.** Nói rõ những phần đã xác minh và rủi ro nào còn phụ thuộc môi trường hoặc mức kiểm thử khác.

### 13.1. Ví dụ nhận xét review rõ ràng

> “Nhánh đơn hàng dưới 500.000 chưa được thực thi trong tập unit test. Tôi đề nghị thêm ca ở 499.999 và kiểm tra phí 30.000. Hiện đã có test đơn 600.000, nhưng chưa có test ở đúng ngưỡng 500.000 để phát hiện lỗi `>` thay vì `>=`. Sau khi bổ sung, hãy xem kết quả assertion và coverage nhánh của phần thay đổi.”

Nhận xét này chỉ ra **hành vi còn thiếu bằng chứng**, chứ không chỉ yêu cầu tăng phần trăm cho đẹp.

### 13.2. Khi báo cáo coverage tăng mà chất lượng chưa chắc tăng

Giả sử một PR thêm test gọi hàng trăm phương thức nhưng ít assertion. Độ bao phủ dòng có thể tăng đáng kể. Vẫn cần xem các bài test mới có phát hiện được sai kết quả, thiếu cập nhật trạng thái hoặc sai trường hợp biên không.

Một PR khác thêm vài test giá trị biên làm coverage chỉ tăng nhẹ nhưng bắt được lỗi tính tiền thật. Trong bối cảnh này, **giá trị kiểm chứng** có thể cao hơn nhiều so với chênh lệch phần trăm.

## 14. Xây dựng quality gate mà không biến chỉ số thành mục tiêu hình thức

Nhóm có thể dùng một ngưỡng coverage trong CI để cảnh báo khi một thay đổi làm giảm đáng kể mức kiểm thử. Đây là một công cụ quản trị hữu ích nếu hiểu đúng phạm vi.

### 14.1. Ngưỡng cần có ngữ cảnh

Một quy tắc “mọi module phải đạt 80% line coverage” không tự bảo đảm công bằng hay chất lượng như nhau. Các module có rủi ro, phụ thuộc, mức độ ổn định và khả năng kiểm soát môi trường khác nhau.

Có thể ưu tiên:

- Những quy tắc tài chính, phân quyền và trạng thái dữ liệu quan trọng có test cho cả nhánh thường và nhánh lỗi có thể đạt tới.
- Những thay đổi mới có thêm bằng chứng tương xứng với hành vi mới.
- Những nhánh chưa bao phủ được giải thích hoặc có kế hoạch kiểm tra theo mức rủi ro.
- Không chấp nhận tăng coverage bằng cách bỏ assertion, làm yếu test hoặc loại trừ mã thiếu căn cứ.

### 14.2. Coverage của mã thay đổi và coverage toàn bộ

Coverage toàn bộ repository có thể bị ảnh hưởng bởi nhiều mã cũ ít dùng. Coverage của **những phần vừa thay đổi** giúp xem PR có được kiểm tra phù hợp không.

Tuy vậy, chỉ nhìn *diff coverage* cũng có giới hạn: một thay đổi nhỏ ở dữ liệu hoặc hợp đồng có thể ảnh hưởng đoạn mã **không nằm trong diff**. Những test hồi quy và kiểm thử tích hợp liên quan vẫn cần được chạy.

### 14.3. Đặt mục tiêu học được điều gì từ một lần giảm coverage

Nếu sau một thay đổi, branch coverage giảm, câu hỏi hữu ích là:

> “Nhánh nào mới xuất hiện hoặc không còn chạy? Nó tương ứng tình huống nào? Cần test, thiết kế lại hay giải thích phạm vi?”

Câu hỏi này tạo giá trị kỹ thuật cụ thể hơn một thông báo tự động “đạt 79,9%, thất bại vì thiếu 0,1%”.

## 15. Tình huống thực tế: coverage xanh nhưng bị tính sai phí giao hàng

Một đội phát triển có báo cáo branch coverage 100% cho hàm phí vận chuyển. Họ dùng hai ca:

- Đơn 400.000 → phí 30.000.
- Đơn 600.000 → phí 0.

Sau khi phát hành, khách có đơn **đúng 500.000** vẫn bị tính phí. Mã dùng `subtotal > 500_000` thay vì `subtotal >= 500_000`.

### 15.1. Phân tích nguyên nhân

Coverage đã ghi nhận đủ hai nhánh `true` và `false`, nên **chỉ số không bị tính sai**. Vấn đề nằm ở **thiết kế dữ liệu test**: nhóm chưa kiểm tra đúng ranh giới do đặc tả quy định.

Có thể là lỗi ở nhiều tầng:

- Yêu cầu “từ 500.000 trở lên” chưa được chuyển thành test ở đúng 500.000.
- Người review chỉ kiểm tra tỷ lệ coverage mà không xem các ca.
- Test không đủ khẳng định điều kiện biên quan trọng.

### 15.2. Cách khắc phục có giá trị lâu dài

1. Xác nhận yêu cầu miễn phí ở **từ 500.000 trở lên** và đơn vị tiền được dùng.
2. Thêm test hồi quy tại 499.999, 500.000 và 500.001.
3. Sửa toán tử so sánh; giữ assertion theo yêu cầu nghiệp vụ.
4. Kiểm tra đường đi từ dữ liệu giỏ hàng đến hàm tính phí để không nhầm tổng tiền trước/sau giảm giá.
5. Giữ coverage làm tín hiệu về các nhánh chưa chạy; dùng bảng giá trị biên để kiểm tra mức độ **đúng và đủ của các ca**.

Tình huống này minh họa rằng **coverage chính xác vẫn có thể đi cùng bộ kiểm thử chưa đủ mạnh**. Cách cải thiện là kết hợp nhiều loại bằng chứng.

## 16. Bài tập tự đánh giá

### Tình huống A: 100% câu lệnh, 50% nhánh

Xét:

~~~java
int handlingFee(boolean urgent) {
    int fee = 10_000;
    if (urgent) {
        fee = 20_000;
    }
    return fee;
}
~~~

Bài test duy nhất gọi `handlingFee(true)` và kiểm tra kết quả 20.000.

**Câu hỏi:** theo mô hình đếm câu lệnh và hai nhánh của `if`, mức bao phủ là bao nhiêu? Thiếu trường hợp nào?

**Gợi ý:** các câu lệnh đều đã chạy, nhưng mới có hướng `true`. Cần test `handlingFee(false)` và kỳ vọng 10.000.

### Tình huống B: 100% nhánh, vẫn sai yêu cầu

Một hàm miễn phí khi giá trị đơn **lớn hơn hoặc bằng** 1.000, nhưng mã dùng `> 1_000`. Test với 900 và 1.100 đều đỗ.

**Câu hỏi:** vì sao độ bao phủ nhánh có thể đã đầy đủ nhưng lỗi vẫn còn?

**Gợi ý:** hai hướng điều kiện đã được đi qua, song ca đúng ngưỡng 1.000 bị bỏ sót. Hãy bổ sung các giá trị biên 999, 1.000, 1.001.

### Tình huống C: nhánh xử lý timeout chưa chạy

Mã gọi API thanh toán, bắt một loại ngoại lệ timeout rồi chuyển sang trạng thái “chờ xác nhận”. Báo cáo chỉ ra phần xử lý timeout chưa bao phủ.

**Câu hỏi:** nên làm gì để có bằng chứng mà không chờ nhà cung cấp thật gặp sự cố?

**Gợi ý:** tạo stub hoặc môi trường tích hợp có thể trả timeout theo yêu cầu, kiểm tra trạng thái và số lần gọi. Nếu cần xác minh tính nhất quán giao dịch và hàng đợi, bổ sung kiểm thử tích hợp tại ranh giới thực.

### Tình huống D: một điều kiện ghép

Chức năng chỉ cho phép giảm giá khi `premium && amount >= threshold`. Bộ test chỉ có hai ca: khách thường với tiền thấp, khách premium với tiền cao.

**Câu hỏi:** những tổ hợp nào còn thiếu và vì sao cần xem thêm cách công cụ đếm nhánh?

**Gợi ý:** khách thường có tiền cao và khách premium có tiền thấp chưa được thử. Hai kết quả Boolean tổng thể không tự nói rõ mọi điều kiện con đã được đánh giá theo cả hai hướng trong bytecode.

## 17. Checklist khi diễn giải báo cáo coverage

- [ ] Tôi biết báo cáo đo **statement, line, instruction hay branch coverage**.
- [ ] Tôi biết phiên bản mã, phạm vi và bộ test dùng để tạo báo cáo.
- [ ] Tôi không coi “dòng đã chạy” là “hành vi đã được xác minh”.
- [ ] Test có assertion dựa trên yêu cầu hoặc hợp đồng được xác nhận.
- [ ] Các nhánh mới và nhánh lỗi quan trọng đã được phân tích.
- [ ] Tôi đã kiểm tra **giá trị biên** ngay cả khi coverage đã là 100%.
- [ ] Với điều kiện ghép, tôi hiểu những điều kiện con và tổ hợp nào đã được kiểm tra.
- [ ] Tôi đã xem xét ngoại lệ, trạng thái, đồng thời và ranh giới tích hợp nếu phù hợp.
- [ ] Tôi biết coverage không đo được hành vi còn thiếu trong đặc tả hoặc mã chưa viết.
- [ ] Mọi loại trừ khỏi báo cáo có lý do và phạm vi rõ ràng.
- [ ] Tôi không thêm test chỉ gọi hàm để làm đẹp phần trăm.
- [ ] Tôi có thể giải thích bằng chứng nào giúp tin vào thay đổi và điều nào vẫn chưa được kiểm chứng.

## 18. Kết luận

**Độ bao phủ câu lệnh** cho biết câu lệnh nào đã chạy; **độ bao phủ nhánh** bổ sung thông tin về các hướng rẽ trong luồng điều khiển. Chúng là những tín hiệu quan trọng để tìm phần mã chưa được tập kiểm thử chạm tới, đặc biệt trong những thay đổi có thêm điều kiện và trường hợp lỗi.

Tuy nhiên, **không có tỷ lệ coverage nào tự chứng minh phần mềm đúng**. Một test cần oracle đúng và assertion đủ mạnh; một nhánh được bao phủ cần đầu vào phù hợp, nhất là tại các giá trị biên; còn các rủi ro về dữ liệu, đồng thời và tích hợp đòi hỏi bằng chứng khác.

Trong **CODE_QUALITY_FUNDAMENTALS**, sử dụng coverage đúng cách nghĩa là biến báo cáo thành **câu hỏi cụ thể về những hành vi cần xác minh**. Người bảo trì có thể tự tin hơn khi mã thay đổi nếu họ biết rõ các trường hợp đã được kiểm thử, lý do lựa chọn chúng và giới hạn của kết luận — thay vì chỉ nhìn vào một con số phần trăm.

