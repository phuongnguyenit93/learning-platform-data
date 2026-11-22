# Kết hợp số liệu với rà soát định tính và bằng chứng hành vi

Một nhóm phát triển tuyên bố chức năng tính phí vận chuyển đã “đạt chất lượng” vì **100% dòng mã được kiểm thử chạy qua**. Tuy nhiên, khách đặt đơn hàng đúng ngưỡng miễn phí vận chuyển lại vẫn bị tính phí. Nhóm khác có chỉ số độ phức tạp khá cao, nhưng những phương thức liên quan đều xử lý các trạng thái nghiệp vụ đã được mô hình hóa rõ ràng và có bài kiểm thử về những chuyển đổi quan trọng. Nếu chỉ nhìn vào một con số, người review có thể kết luận sai về cả hai nhóm.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Chỉ số chất lượng**, bài này tập trung vào cách sử dụng **số liệu định lượng**, **rà soát định tính** và **bằng chứng hành vi** như ba nguồn thông tin bổ sung cho nhau, thay vì biến một chỉ số thành thước đo duy nhất cho “mã tốt”.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **chất lượng cần đạt** với **chỉ số thay thế (proxy)** đang dùng để quan sát một khía cạnh của chất lượng.
- Đọc một số chỉ số thường gặp: độ bao phủ kiểm thử, độ phức tạp, trùng lặp, mức độ thay đổi, cảnh báo phân tích tĩnh, lỗi thoát ra môi trường thực tế.
- Nhận diện những kết luận **không thể** rút ra chỉ từ điểm số hoặc tỉ lệ phần trăm.
- Sử dụng code/design review để giải thích nguyên nhân, tác động và khả năng thay đổi của một đoạn mã.
- Dùng kiểm thử có kỳ vọng độc lập, kiểm thử ranh giới, kiểm thử tích hợp và dữ liệu vận hành để xác minh hành vi quan trọng.
- Tạo một quyết định cải tiến **có truy vết** từ mục tiêu → chỉ số → giả thuyết → kiểm chứng → hành động → kết quả.

## 1. Vì sao chất lượng không có một con số đại diện?

Chất lượng mã nguồn gồm nhiều thuộc tính có thể ảnh hưởng và đôi khi đánh đổi lẫn nhau: **tính đúng đắn, dễ đọc, dễ sửa, khả năng kiểm thử, an toàn, hiệu năng, độ tin cậy và tính tương thích**. Một tính năng có thể rất dễ hiểu nhưng chưa xử lý đồng thời đúng; một hàm chạy nhanh có thể khó sửa hoặc không kiểm soát được dữ liệu đầu vào.

Số liệu giúp biến một số hiện tượng thành điều có thể quan sát và so sánh. Nhưng mọi chỉ số đều **chọn một phạm vi đo cụ thể**:

| Thuộc tính muốn quan tâm | Chỉ số có thể hỗ trợ | Điều chỉ số không tự chứng minh |
| --- | --- | --- |
| Khả năng kiểm thử | Line/branch coverage, mutation score | Kỳ vọng trong test đúng với nghiệp vụ; tất cả trạng thái được xét |
| Khả năng hiểu | Cyclomatic/cognitive complexity, kích thước phương thức | Tên và mô hình nghiệp vụ có rõ; lý do thiết kế có đúng |
| Khả năng thay đổi | Trùng lặp, coupling, change frequency, thời gian sửa lỗi | Chi phí thật của một thay đổi tương lai hoặc mức độ phù hợp của kiến trúc |
| Mức rủi ro lỗi | Static-analysis findings, lỗi sản xuất, sự cố lặp lại | Mọi cảnh báo là bug thật; việc không có cảnh báo nghĩa là an toàn |
| Hiệu năng | Latency, throughput, phân bổ bộ nhớ | Kết quả đúng hoặc tuân thủ hợp đồng ở mọi đầu vào |
| Độ tin cậy vận hành | Error rate, số sự cố, thời gian phục hồi | Không có lỗi tiềm ẩn hoặc mọi tính năng được sử dụng đầy đủ |

Một chỉ số chỉ có giá trị khi trả lời được: **đo điều gì, trong phạm vi nào, với cách tính nào, nhằm hỗ trợ quyết định gì?**

### Chỉ số là tín hiệu, không phải phán quyết

Có thể xem quy trình suy luận theo ba tầng:

~~~text
SỐ LIỆU                 RÀ SOÁT ĐỊNH TÍNH            BẰNG CHỨNG HÀNH VI
"Có điều gì bất thường?" -> "Vì sao có thể xảy ra?" -> "Hệ thống thực sự làm gì?"
         |                         |                         |
         +-------------------------+-------------------------+
                                   |
                                   v
                     QUYẾT ĐỊNH CÓ NGỮ CẢNH
                   (sửa gì, vì sao, kiểm tra thế nào)
~~~

Ví dụ, **branch coverage thấp** có thể dẫn đến giả thuyết “đường xử lý lỗi thiếu test”. Reviewer đọc mã sẽ biết các nhánh đó có phải điều kiện nghiệp vụ quan trọng không. Sau đó, một bài kiểm thử mô phỏng lỗi hạ tầng mới xác minh liệu hệ thống có rollback và trả đúng lỗi hay không.

Nếu chỉ dừng ở con số, nhóm mới biết **một tín hiệu** chứ chưa có đủ **bằng chứng về hành vi**.

## 2. Đọc số liệu kèm định nghĩa và mẫu đo

Không nên so sánh hai báo cáo trước khi xác nhận **mẫu số, phạm vi và thời điểm đo**.

| Chỉ số | Ý nghĩa tổng quát | Cần xem thêm gì? |
| --- | --- | --- |
| **Line coverage** | Tỷ lệ dòng có thể đo được đã được thực thi bởi test | Công cụ tính dòng như thế nào; những tệp nào được tính/loại trừ |
| **Branch coverage** | Tỷ lệ hướng quyết định trong mô hình công cụ đã được thực thi | Nhánh nào chưa chạy; cấu trúc `if`, `switch`, điều kiện logic |
| **Mutation score** | Tỷ lệ biến thể mã do công cụ tạo ra bị test phát hiện trong tập mutant được tính | Mutant tương đương, timeout, loại trừ, quy tắc của công cụ |
| **Cyclomatic complexity** | Đặc điểm đồ thị luồng điều khiển và số đường độc lập | Phương thức cụ thể, quyết định nghiệp vụ, quy tắc đo của tool |
| **Cognitive complexity** | Ước lượng gánh nặng hiểu luồng, thường có xét lồng nhau | Ngữ nghĩa tên, trách nhiệm và mức rõ ràng của quy tắc |
| **Duplication** | Lượng mã giống nhau theo phép nhận diện của công cụ | Đó là lặp logic có hại hay các ví dụ/định nghĩa cần tách biệt |
| **Change frequency / churn** | Tần suất hoặc lượng thay đổi trong một giai đoạn | Thành phần đang có tính năng mới hay đang sửa lỗi liên tiếp |
| **Static-analysis findings** | Số lượng cảnh báo theo rule và phạm vi scan | Severity, confidence, trạng thái xác minh, cách cấu hình |
| **Lỗi thoát ra sản xuất** | Lỗi được phát hiện sau khi phát hành trong phạm vi theo dõi | Mức sử dụng, độ dài kỳ quan sát, cách phân loại, khả năng phát hiện |

### Ví dụ về mẫu số

Giả sử một công cụ đo được **90 trên 100 dòng** và ghi “90% line coverage”. Điều này không phải “90% yêu cầu được kiểm tra” hoặc “90% chương trình đúng”. Mười dòng chưa được chạy có thể là các trường hợp lỗi quan trọng; 90 dòng đã chạy cũng có thể chứa một phép tính sai mà test không kiểm tra kết quả.

Tương tự, “giảm một nửa số cảnh báo” chưa có nghĩa giảm một nửa lỗi nếu nhóm thay đổi rule, loại trừ nhiều thư mục hơn hoặc chuyển các cảnh báo vào baseline. **Số liệu chỉ có thể so sánh khi định nghĩa và phạm vi đo tương đối ổn định**, hoặc những thay đổi về cách đo được ghi rõ.

## 3. Coverage trả lời “đã chạy qua?”, không trả lời “đã đúng?”

Đây là giới hạn thường bị hiểu sai nhất của chỉ số kiểm thử.

Một test như sau có thể **thực thi hàm** nhưng hầu như không kiểm tra kết quả:

~~~java
@Test
void invokesShippingPolicy() {
    FreeShippingPolicy.isEligible(600_000, false);
}
~~~

Dòng mã trong hàm được gọi có thể được ghi nhận là đã thực thi, nhưng bài test không có assertion xác minh hành vi mong đợi.

Ngay cả khi các nhánh đã được đi qua và test có assertion, **giá trị biên** vẫn có thể bị bỏ sót. Cần nhìn tiếp vào yêu cầu nghiệp vụ.

### Ví dụ Java: sai đúng một dấu so sánh

Giả sử chính sách giao hàng **đã được nhóm sản phẩm xác nhận cho ví dụ này**:

- Đơn hàng giao tiêu chuẩn có tổng tiền **từ 500.000 VND trở lên** được miễn phí vận chuyển.
- Đơn giao nhanh **không** thuộc chính sách miễn phí này.
- Tổng tiền âm là đầu vào không hợp lệ.
- Phương thức chỉ quyết định đủ điều kiện; không thu tiền và không thay đổi đơn hàng.

Phiên bản triển khai sau có một lỗi nhỏ nhưng ảnh hưởng đúng tại ranh giới:

~~~java
public final class FreeShippingPolicy {
    private static final long THRESHOLD_VND = 500_000;

    private FreeShippingPolicy() {
    }

    public static boolean isEligible(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        if (express) {
            return false;
        }
        return subtotalVnd > THRESHOLD_VND; // BUG: bỏ sót đúng ngưỡng.
    }
}
~~~

Giả sử bộ test chỉ có các tình huống:

| Ca test | Subtotal | Giao nhanh? | Kỳ vọng | Kết quả của mã trên |
| --- | ---: | --- | --- | --- |
| Đơn thường trên ngưỡng | 600.000 | Không | `true` | `true` |
| Đơn thường dưới ngưỡng | 400.000 | Không | `false` | `false` |
| Đơn giao nhanh trên ngưỡng | 600.000 | Có | `false` | `false` |
| Tổng tiền âm | -1 | Không | Ném `IllegalArgumentException` | Ném ngoại lệ |

Những test này có thể làm **mọi câu lệnh và hướng quyết định cơ bản** trong hàm được thực thi, tùy quy tắc của công cụ coverage. Nhưng chúng **chưa kiểm tra đúng 500.000 VND**. Vì thế, coverage cao — thậm chí đạt tối đa theo mô hình đo được — vẫn có thể đi kèm lỗi nghiệp vụ thật.

Một ca mới làm lộ sai khác:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class FreeShippingBoundaryTest {
    @Test
    void standardDeliveryIsFreeAtExactThreshold() {
        assertTrue(FreeShippingPolicy.isEligible(500_000, false));
    }
}
~~~

Với bản triển khai `>`, bài kiểm thử này **thất bại**. Quy tắc cần `>=`:

~~~java
return subtotalVnd >= THRESHOLD_VND;
~~~

Đây là một thay đổi rất nhỏ về số ký tự, nhưng quan trọng về hợp đồng. Chỉ số coverage không nói được rằng dấu `>` là sai; **yêu cầu và test giá trị biên** mới xác định điều đó.

### Kiểm thử sau sửa

Một bảng kiểm thử có thể tự chứa các trường hợp quan trọng bằng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class FreeShippingPolicyTest {
    @ParameterizedTest
    @CsvSource({
        "499999, false, false",
        "500000, false, true",
        "500001, false, true",
        "600000, true,  false"
    })
    void followsFreeShippingPolicy(
            long subtotalVnd, boolean express, boolean expected) {
        assertEquals(
            expected,
            FreeShippingPolicy.isEligible(subtotalVnd, express)
        );
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
            IllegalArgumentException.class,
            () -> FreeShippingPolicy.isEligible(-1, false)
        );
    }
}
~~~

Lưu ý: để bộ test này đạt, **phải áp dụng sửa `>=` vào `FreeShippingPolicy` ở trên**. Các ví dụ được tách thành đoạn mã giải thích trình tự “phát hiện lỗi → viết test → sửa → kiểm chứng”; không nên ghép phiên bản có lỗi với test sau sửa rồi kỳ vọng toàn bộ test xanh.

Giới hạn của ví dụ: trong hệ thống thực tế cần xác nhận `subtotalVnd` đã gồm hay chưa gồm thuế/giảm giá; trạng thái express có những loại nào; giá trị tổng có thể tràn số ở khâu tính trước không. Những câu hỏi này cần **rà soát ngữ nghĩa**, không thể được trả lời chỉ bằng công cụ coverage.

## 4. Mutation testing tăng sức mạnh kiểm chứng, nhưng không tự định nghĩa đúng sai

**Mutation testing** tạo những biến thể nhỏ của mã, chẳng hạn đổi `>=` thành `>`, thay một hằng số hoặc đảo điều kiện, rồi kiểm tra xem test có phát hiện thay đổi hành vi hay không.

Một **mutant bị tiêu diệt (killed)** khi test thất bại phù hợp với sự thay đổi. Một **mutant sống sót (survived)** là tín hiệu rằng bộ test chưa phân biệt được biến thể đó trong các tình huống đã chạy.

Trong ví dụ chính sách vận chuyển, nếu bộ test không có ca đúng ngưỡng, biến thể đổi dấu so sánh có thể sống sót. Thêm test ranh giới có thể khiến biến thể bị phát hiện.

Ví dụ một báo cáo minh họa có **35 mutant bị phát hiện**, **5 mutant sống sót** và **10 mutant được loại khỏi mẫu vì timeout hoặc điều kiện loại trừ được công bố**:

| Kết quả | Số lượng |
| --- | ---: |
| Killed | 35 |
| Survived | 5 |
| Loại trừ/không có kết quả hợp lệ | 10 |

Nếu cách tính của công cụ lấy `killed / (killed + survived)` cho **40 mutant có kết quả hợp lệ**, mutation score của mẫu này là **87,5%**. Mười mutant bị loại phải được ghi riêng; **không được âm thầm loại bỏ nhiều trường hợp khó rồi coi điểm số là đầy đủ**.

Các lưu ý:

- Một số mutant có thể **tương đương về hành vi quan sát được** trong phạm vi hợp đồng, nên không có test hợp lệ nào phân biệt được.
- Các công cụ khác nhau tạo và lọc mutant theo các quy tắc khác nhau.
- Mutation score cao cũng có thể chỉ chứng minh test nhạy với những biến thể công cụ tạo, **không chứng minh kết quả mong đợi đã đúng về nghiệp vụ**.
- Mutation testing có chi phí chạy lớn, nên có thể ưu tiên **vùng logic quan trọng**, thay vì áp cùng một ngưỡng trên toàn bộ dự án.

**Coverage và mutation score bổ sung cho nhau:** một chỉ số nói mã/nhánh nào được chạy, chỉ số kia đặt thêm câu hỏi test có phản ứng khi logic bị thay đổi không. Cả hai vẫn cần một nguồn kỳ vọng độc lập.

## 5. Độ phức tạp và trùng lặp là tín hiệu để review có mục tiêu

Một công cụ có thể báo:

~~~text
OrderService.approve(): cognitive complexity = 28
InvoiceCalculator.calculate(): 43 dòng
PaymentHandler: duplicated blocks = 3
~~~

Những giá trị trên có thể giúp nhóm ưu tiên đọc kỹ, nhưng không tự đưa ra thiết kế đúng.

### Cần hỏi gì khi độ phức tạp cao?

- Những nhánh có đại diện cho **các quy tắc nghiệp vụ thực sự khác nhau** không?
- Người đọc phải giữ bao nhiêu điều kiện trong đầu cùng lúc? Có nhiều mức lồng nhau không?
- Có các tham số điều khiển làm hành vi thay đổi âm thầm không?
- Quy tắc có thể biểu diễn bằng **bảng quyết định**, trạng thái có tên hoặc phương thức mang ý định rõ hơn không?
- Nếu tách phương thức, người bảo trì có tìm ra luồng chính dễ hơn hay phải chuyển qua quá nhiều helper?

Một hàm xử lý nhiều loại trạng thái có thể có điểm cyclomatic cao vì **bài toán thật phức tạp**. Việc chia hàm thành nhiều đoạn chỉ để giảm điểm từng phương thức có thể làm tổng mức khó hiểu tăng lên. Cần review trách nhiệm và tính nhất quán của mô hình trước khi refactor.

### Cần hỏi gì khi có mã trùng lặp?

Hai đoạn code giống nhau có thể:

- Cùng thực hiện **một quy tắc** được nhân bản không cần thiết, có nguy cơ sửa một nơi mà quên nơi khác.
- Chỉ giống cấu trúc hiện tại nhưng phục vụ **hai chính sách sẽ thay đổi độc lập**, nên việc trừu tượng hóa thành một hàm chung có thể tạo phụ thuộc không mong muốn.

Vì vậy, tỉ lệ duplication nên giúp **chọn nơi xem xét**, không dùng làm lý do duy nhất để gộp mã. Người review phải trả lời *hai đoạn có cùng trách nhiệm và cùng lý do thay đổi không?*

## 6. Tần suất thay đổi và sự cố cho biết nơi nào đáng chú ý

Một thành phần được sửa nhiều lần có thể là nơi **đang phát triển tính năng tích cực**, chứ không hẳn là mã kém chất lượng. Nhưng nếu thành phần đó cũng có độ phức tạp cao, nhiều lỗi hồi quy và phụ thuộc chằng chịt, nó có thể là một **hotspot bảo trì**.

Ví dụ số liệu minh họa cho **cùng kỳ quan sát đã được xác định trước**:

| Thành phần | Line coverage | Max cognitive complexity | Lần thay đổi trong 30 ngày | Sự cố ghi nhận trong 90 ngày |
| --- | ---: | ---: | ---: | ---: |
| Thanh toán | 95% | 29 | 18 | 2 |
| Giao diện cấu hình nội bộ | 72% | 8 | 2 | 0 |

Không nên lập tức kết luận:

> “Thanh toán chất lượng hơn vì coverage cao hơn.”

Cũng không nên nói:

> “Giao diện cấu hình an toàn vì chưa có sự cố.”

Những điều cần làm rõ:

1. **Tác động:** Thanh toán có thể ảnh hưởng dữ liệu/tài chính nghiêm trọng hơn giao diện cấu hình.
2. **Ngữ cảnh thay đổi:** 18 lần thay đổi là phát triển có kế hoạch hay sửa đi sửa lại cùng một lỗi?
3. **Phạm vi đo:** Coverage có tính cả những mã xử lý lỗi và cạnh tranh đồng thời không?
4. **Độ tin cậy của sự cố:** Hai sự cố có nguồn gốc từ thành phần này không? Có đủ quan sát để biết giao diện cấu hình thực sự không lỗi không?
5. **Thiết kế:** Điểm complexity 29 là do thiếu phân tách trách nhiệm hay do nhiều trạng thái nghiệp vụ được xử lý đúng ở một chỗ?

Đối với ví dụ này, nhóm có thể **ưu tiên review và kiểm thử những đường thanh toán rủi ro cao**, mặc dù coverage đang cao hơn. Đó là một quyết định dựa trên **mức tác động + tín hiệu thay đổi + bằng chứng hành vi còn thiếu**, không phải một cuộc thi điểm số.

### Không so sánh sự cố thiếu mẫu số

Nếu một API nhận một triệu yêu cầu còn API khác nhận một trăm yêu cầu, cùng “một sự cố” có thể phản ánh hai tình huống rất khác. Khi phù hợp, cần ghi:

- Số lượng yêu cầu hoặc lượng sử dụng liên quan.
- Khoảng thời gian và phiên bản triển khai.
- Định nghĩa thế nào là một lỗi/sự cố.
- Mức nghiêm trọng và tác động của sự cố.
- Khả năng phát hiện, mức độ đầy đủ của telemetry.

Việc “không có bug được báo” có thể đơn giản là **chưa có đủ người sử dụng hoặc chưa quan sát được sai lệch**.

## 7. Rà soát định tính phải tạo nhận định có thể kiểm chứng

Một code review tốt không chỉ nói “mã xấu”, “mã quá dài” hoặc “nên tách hàm”. Nó cần liên kết **đặc điểm quan sát được**, **rủi ro cụ thể** và **đề xuất kiểm chứng**.

Ví dụ comment review thiếu thông tin:

> “Phương thức quá phức tạp. Refactor đi.”

Một nhận định hữu ích hơn:

> “Phương thức kiểm tra quyền và ghi thanh toán trong cùng một nhánh, đồng thời trả về sớm trước bước ghi audit. Nếu bị từ chối ở đường thứ ba, sự kiện có thể không được ghi nhận. Cần xác nhận audit có phải hợp đồng bắt buộc với mọi yêu cầu bị từ chối không; nếu có, bổ sung test cho đường này rồi tách trách nhiệm để giảm nguy cơ bỏ sót.”

Nhận định thứ hai:

- Chỉ ra **vị trí và cơ chế** của rủi ro.
- Không tự khẳng định một quy tắc chưa được xác nhận.
- Đề xuất test có thể chứng minh hoặc bác bỏ giả thuyết.
- Gắn refactor với **hành vi cần bảo vệ**, không chỉ với điểm số.

### Checklist review định tính

| Góc nhìn | Câu hỏi cần trả lời |
| --- | --- |
| **Ý định** | Tên và cấu trúc có thể hiện khái niệm nghiệp vụ không? |
| **Đúng đắn** | Các bất biến, giá trị biên và đường lỗi có được bảo vệ không? |
| **Phụ thuộc** | Các nguồn thời gian, I/O, cấu hình và trạng thái chia sẻ có rõ không? |
| **Đóng gói** | Người gọi có thể bỏ qua quy tắc bằng getter, setter hoặc collection có thể sửa không? |
| **Ranh giới** | Quyền truy cập, transaction, dữ liệu và trách nhiệm lỗi nằm đúng tầng không? |
| **Khả năng kiểm thử** | Test có thể kiểm soát nguồn bất định và quan sát kết quả có ý nghĩa không? |
| **Thay đổi** | Nếu chính sách đổi, phải sửa những nơi nào; có rủi ro sửa lệch không? |
| **Giải thích quyết định** | Có tài liệu hoặc ADR cho lý do khó suy ra từ mã không? |

Review nên được tiến hành **theo ngữ cảnh và mục tiêu cụ thể**, tránh biến thành danh sách dài các góp ý thẩm mỹ không có ảnh hưởng tới người sử dụng hoặc chi phí bảo trì.

## 8. Bằng chứng hành vi bổ sung điều gì cho số liệu?

**Bằng chứng hành vi** là quan sát có thể kiểm tra được về việc hệ thống thực hiện hay từ chối một hành vi trong những điều kiện xác định.

| Loại bằng chứng | Có thể xác minh điều gì? | Giới hạn cần ghi rõ |
| --- | --- | --- |
| **Unit test có assertion** | Quy tắc nhỏ trả kết quả đúng với input đã chọn | Không tự chứng minh các adapter thật hoặc toàn bộ nghiệp vụ |
| **Kiểm thử biên / bảng quyết định** | Các ranh giới và tổ hợp đã đặc tả | Bảng có thể thiếu quy tắc; test không bao phủ vô hạn đầu vào |
| **Property-based testing** | Bất biến đúng cho nhiều dữ liệu được sinh | Cần xác định invariant đúng và vùng sinh phù hợp |
| **Mutation testing** | Test nhận ra một số biến đổi logic đã thử | Chỉ đo các mutant có liên quan, không tự xác nhận oracle |
| **Integration/contract test** | Các tầng thật trao đổi đúng theo hợp đồng | Cấu hình và dữ liệu thử có thể khác production |
| **Concurrency test** | Một số lịch chạy/cạnh tranh được thử | Không chứng minh tất cả interleaving có thể xảy ra |
| **Canary/telemetry sản xuất** | Hành vi và lỗi được quan sát dưới một phần tải thực | Chỉ những gì được ghi nhận; có độ trễ, sampling và yếu tố nhiễu |
| **Đánh giá người dùng/đối chiếu yêu cầu** | Kết quả có đáp ứng mục tiêu và tình huống thực tế không | Cần xác định đối tượng, phương pháp và nguồn kỳ vọng |

### Một bằng chứng cần đủ ngữ cảnh

Không nên chỉ lưu dòng “test passed”. Có thể ghi:

~~~text
Yêu cầu: Giao tiêu chuẩn miễn phí khi subtotal >= 500000 VND
Phạm vi: FreeShippingPolicy.isEligible()
Đầu vào kiểm tra: 499999, 500000, 500001; express=true
Kỳ vọng: false, true, true; express không miễn phí
Phiên bản: <commit đã xác nhận>
Môi trường: JDK/test runner đã công bố
Kết quả: Đạt sau khi sửa điều kiện biên
Chưa kiểm tra: nguồn tính subtotal, giảm giá, API end-to-end
~~~

Đây là một **bản ghi minh họa**. Phần quan trọng là làm rõ **điều đã chứng minh** và **điều chưa chứng minh**. Khi test thất bại, log expected/actual, đầu vào và đường đi giúp nhóm xử lý thay vì chỉ biết một điểm coverage thay đổi.

## 9. Triangulation: kết hợp ba nguồn để ra quyết định

**Triangulation** trong ngữ cảnh này là xem cùng một vấn đề qua nhiều cách quan sát độc lập tương đối: số liệu chỉ ra vùng nghi ngờ, review giải thích khả năng xảy ra, và test/quan sát thực tế kiểm tra giả thuyết.

Một ví dụ theo từng bước:

| Bước | Quan sát | Câu hỏi tiếp theo |
| --- | --- | --- |
| 1. Số liệu | Phương thức xử lý hoàn tiền có nhiều nhánh và đã sửa 12 lần | Những trường hợp nào hay thay đổi và có hậu quả lớn? |
| 2. Review | Một nhánh retry có thể ghi hoàn tiền trước khi ghi idempotency key | Retry sau timeout có thể hoàn tiền trùng không? |
| 3. Bằng chứng | Integration test mô phỏng timeout sau ghi và yêu cầu lặp lại | Có tạo hai giao dịch thật hay không? |
| 4. Kết luận | Nếu lỗi được tái hiện, bổ sung ràng buộc và thiết kế khôi phục | Sửa ở đâu để bảo vệ trạng thái nhất quán? |
| 5. Kiểm chứng lại | Test hồi quy, kiểm tra lỗi và telemetry sau phát hành | Lỗi gốc đã được khắc phục và có tác dụng phụ mới không? |

Những con số như “12 lần sửa” hoặc “độ phức tạp cao” chỉ làm rõ **tại sao nên xem**. **Kịch bản và bằng chứng** mới giúp kết luận phải thay đổi phần nào.

Với lỗi không thể tái hiện, không nên mặc định kết luận không tồn tại. Hãy ghi tình trạng **chưa đủ bằng chứng**, tiếp tục tìm phạm vi, thu thập dấu vết và ưu tiên theo rủi ro nếu tác động tiềm tàng lớn.

## 10. Tách “mức chắc chắn” khỏi “mức tác động”

Một công cụ tĩnh có thể đưa ra cảnh báo `HIGH severity / LOW confidence`. Cảnh báo khác về import thừa có thể là `LOW severity / HIGH confidence`.

Đây là hai chiều riêng:

- **Severity / tác động:** nếu vấn đề thật, hậu quả là gì?
- **Confidence / bằng chứng:** công cụ hoặc nhóm chắc đến mức nào rằng nhận định đúng?
- **Priority:** cần điều tra/sửa trong thời điểm nào, xét thêm tác động, mức phơi lộ, tần suất sử dụng, rủi ro và hạn phát hành?

Không nên cộng hoặc nhân các nhãn định tính để tạo một “điểm tổng” rồi dùng như phán quyết tự động. Ví dụ, lỗi nguy cơ lộ dữ liệu có confidence thấp vẫn đáng điều tra sớm. Một import dư thừa có confidence cao có thể được formatter xử lý mà không chen trước những vấn đề bảo vệ dữ liệu.

Sau khi review, nhóm nên ghi trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `CONFIRMED` | Có bằng chứng phù hợp xác nhận lỗi hoặc vi phạm hợp đồng |
| `FALSE_POSITIVE` | Đã có cơ sở bác bỏ finding trong phạm vi đã đánh giá |
| `NEEDS_MORE_EVIDENCE` | Chưa đủ dữ liệu để xác nhận hoặc bác bỏ |
| `FIXED_AND_VERIFIED` | Đã sửa và có kiểm chứng tương ứng |
| `ACCEPTED_RISK` | Rủi ro đã được đánh giá và chấp nhận bởi người có thẩm quyền |

**Một cảnh báo không còn xuất hiện sau khi tắt rule không phải là một lỗi đã được sửa.** Việc giảm “số cảnh báo mở” chỉ mang ý nghĩa tích cực nếu biết cảnh báo đã được xử lý thế nào.

## 11. Đặt quality gate theo rủi ro, không chạy theo chỉ tiêu tuyệt đối

**Quality gate** là tập điều kiện giúp quyết định khi nào một bản thay đổi cần được sửa, review thêm hoặc có thể tiếp tục quy trình phát hành. Gate tốt làm rõ **bằng chứng tối thiểu** cho các thay đổi quan trọng mà không biến chỉ số thành trò chơi tối ưu hóa điểm.

Một chính sách **minh họa**, không phải ngưỡng bắt buộc cho mọi dự án:

| Trường hợp | Cách xử lý có thể phù hợp |
| --- | --- |
| Logic thanh toán mới thiếu test ở ranh giới hoặc đường lỗi quan trọng | Yêu cầu bổ sung test có assertion đúng hợp đồng trước khi merge |
| Lỗi bảo mật mức tác động cao đã được xác nhận | Chặn phát hành đến khi sửa/giảm thiểu theo quy trình rủi ro |
| Cảnh báo severity cao nhưng chưa đủ chứng cứ | Yêu cầu triage có người chịu trách nhiệm, không tự đánh dấu “fixed” |
| Coverage giảm nhỏ do thêm adapter chỉ định tuyến | Xem phạm vi và loại kiểm thử thay vì chặn máy móc |
| Formatter phát hiện lỗi định dạng đơn giản | Sửa tự động, không tạo một quy trình phê duyệt phức tạp |
| Độ phức tạp tăng do quy tắc mới được xác nhận | Review bảng quyết định và khả năng kiểm thử trước khi quyết định refactor |

Nếu một mục tiêu được đặt thành “coverage ít nhất 90%”, nhóm có thể vô tình thêm test chỉ gọi hàm để đạt ngưỡng, loại trừ tệp khó hoặc tránh viết mã ở vùng thiếu test. Đây là một ví dụ của hiện tượng **chỉ số bị tối ưu vì chính nó**, khiến chỉ số ngày càng xa mục tiêu chất lượng.

Gate nên đi kèm **điều kiện ngoại lệ có bằng chứng**, phạm vi áp dụng, chủ sở hữu và quy trình review ngưỡng. Những rủi ro cao không nên được miễn chỉ vì một chỉ số khác đang xanh.

## 12. Thiết lập một vòng cải tiến đo được

Một cách thực hành cho nhóm phát triển:

1. **Xác định mục tiêu có ý nghĩa.** Ví dụ “giảm lỗi tính phí sai ở giá trị biên” hoặc “giảm thời gian sửa lỗi trên luồng hoàn tiền”, thay vì mục tiêu đơn thuần “điểm chất lượng tăng”.
2. **Chọn chỉ số liên quan.** Có thể theo dõi coverage nhánh, mutation ở logic chính sách, số lỗi hồi quy hoặc thời gian review; tránh thu mọi metric chỉ vì công cụ có sẵn.
3. **Ghi baseline và phạm vi.** Chốt commit, thời gian, rule, file loại trừ, công cụ và cách tính để có cơ sở so sánh.
4. **Rà soát vùng có tín hiệu rủi ro.** Đọc mã, xác nhận chính sách, đánh giá độ phức tạp, tác dụng phụ, phụ thuộc và điểm thiếu test.
5. **Viết giả thuyết kiểm chứng được.** Ví dụ “đường refund sau timeout có thể gọi gateway hai lần cho một yêu cầu”.
6. **Tạo bằng chứng hành vi.** Dùng test biên, integration, test song song có kiểm soát hoặc dữ liệu vận hành phù hợp. Expected phải dựa trên yêu cầu chứ không sao chép thuật toán.
7. **Thay đổi có giới hạn và ghi nhận quyết định.** Sửa nguyên nhân, không chỉ xóa cảnh báo; ghi lại tác động và rủi ro còn lại.
8. **Đo lại cùng định nghĩa và so sánh có ngữ cảnh.** Điểm complexity giảm không đủ nếu độ trễ hoặc số lỗi thực tế tăng; thay đổi có thể cần theo dõi qua nhiều bản phát hành.
9. **Học từ kết quả.** Nếu metric không hỗ trợ quyết định hoặc dễ bị thao túng, thay metric/gate; nếu test không phát hiện lỗi, bổ sung oracle và trường hợp thực tế.

Trong các bước trên, “số liệu trước và sau” là **dấu hiệu**, không đủ để khẳng định quan hệ nguyên nhân–kết quả. Một giảm sút số bug có thể do lưu lượng ít hơn, tính năng ít được sử dụng hoặc thay đổi cách báo lỗi. Cần đối chiếu các yếu tố khác trước khi tuyên bố cải tiến thành công.

## 13. Một mẫu báo cáo cân bằng

Thay vì bảng chỉ ghi điểm số, báo cáo ngắn cho một thành phần có thể ghi:

| Mục | Nội dung minh họa |
| --- | --- |
| **Mục tiêu** | Tránh tính phí giao hàng sai tại ngưỡng miễn phí |
| **Chỉ số hiện có** | Line/branch coverage cao nhưng chưa có test giá trị chính xác 500.000 VND |
| **Đánh giá định tính** | Biểu thức dùng `>`, trong khi hợp đồng yêu cầu “từ ... trở lên” |
| **Bằng chứng hành vi** | Test tại 500.000 VND thất bại trước sửa, đạt sau khi đổi `>=` |
| **Đã thay đổi** | Sửa toán tử; bổ sung ca dưới, đúng và trên ngưỡng |
| **Đã kiểm chứng** | Unit test chính sách; chưa kiểm chứng nguồn subtotal trong tích hợp |
| **Rủi ro còn lại** | Cách tính subtotal, các chương trình giảm giá, nhiều đơn vị tiền |
| **Hành động tiếp theo** | Xác nhận hợp đồng về tổng tiền và thêm integration test cho checkout |

Báo cáo này có thể dài hơn một dòng “Coverage: 100%”, nhưng **hữu ích hơn cho quyết định kỹ thuật**: nó phân biệt điều đã biết, điều đã sửa và điều vẫn chưa kiểm tra.

Với dự án lớn, báo cáo có thể đặt link tới PR, test report, dashboard và quyết định thiết kế thay vì sao chép tất cả nội dung. Điều cốt lõi là **khả năng truy vết**.

## 14. Bài tập tình huống

Nhóm phụ trách ba module Java cung cấp các số liệu minh họa:

| Module | Line coverage | Max cognitive complexity | Lượt thay đổi trong 30 ngày | Lỗi sản xuất trong 90 ngày |
| --- | ---: | ---: | ---: | ---: |
| A — Xử lý hoàn tiền | 96% | 31 | 16 | 2 |
| B — Hiển thị lịch sử đơn | 70% | 9 | 3 | 0 |
| C — Đồng bộ dữ liệu đối tác | 82% | 22 | 11 | 1 |

Đội phát triển còn có các quan sát:

- A chưa có bài kiểm thử cạnh tranh giữa hai lệnh hoàn tiền cùng yêu cầu; các thay đổi gần đây sửa lỗi liên quan retry.
- B nhận rất ít lưu lượng vì chức năng mới thử nghiệm nội bộ.
- C có integration test với đối tác giả lập, nhưng không kiểm tra timeout sau khi phía đối tác đã xử lý yêu cầu thành công.

**Câu hỏi A.** Có thể xếp hạng chất lượng A, B, C chỉ dựa trên coverage không? Vì sao?

**Câu hỏi B.** Với A, đâu là giả thuyết rủi ro cần được xác nhận? Nên dùng bằng chứng hành vi nào?

**Câu hỏi C.** Với B, “không có lỗi sản xuất trong 90 ngày” có chứng minh module đủ tin cậy không?

**Câu hỏi D.** Với C, nếu một test mock đối tác trả timeout ngay lập tức nhưng không mô phỏng việc đối tác đã xử lý xong, test đó có đủ để chứng minh retry an toàn không?

**Câu hỏi E.** Hãy đề xuất một cách báo cáo ngắn gọn cho Prime hoặc người review để phân biệt **tín hiệu**, **giả thuyết**, **bằng chứng** và **quyết định tiếp theo**.

### Gợi ý đáp án

**A.** Không. Coverage thể hiện phạm vi mã được chạy, không phản ánh trực tiếp tính đúng đắn, tác động nghiệp vụ hoặc tình huống chưa kiểm tra. A có coverage cao nhất nhưng đang có rủi ro quan trọng về hoàn tiền đồng thời; B có lưu lượng quá thấp để kết luận từ số lỗi bằng không; C cần kiểm tra các tình huống lỗi tích hợp.

**B.** Giả thuyết: hai lần xử lý cùng yêu cầu hoặc retry sau timeout có thể ghi nhận **hai lần hoàn tiền**. Cần review idempotency, transaction và ranh giới với gateway; thiết lập integration/concurrency test kiểm tra không phát sinh hai giao dịch cho cùng một yêu cầu logic. Expected phải xuất phát từ chính sách giao dịch đã xác nhận.

**C.** Không. Khi chức năng ít được sử dụng, số lỗi quan sát bằng 0 có thể thiếu ý nghĩa. Cần xem test hành vi thực tế, dữ liệu thử, khả năng quan sát và mức độ sử dụng trước khi kết luận.

**D.** Chưa đủ. Nếu đối tác đã hoàn thành nhưng phản hồi bị mất, client có thể gửi lại cùng yêu cầu và gây tác dụng phụ trùng. Test phải mô phỏng được tình huống **thành công ở phía đối tác nhưng timeout ở phía gọi**, và xác minh cơ chế nhận diện yêu cầu lặp lại hoặc đối soát trạng thái.

**E.** Một báo cáo có thể viết: “A: coverage 96%, complexity 31, 16 lần thay đổi/30 ngày — đây là tín hiệu nên review; giả thuyết lặp hoàn tiền khi retry; hiện chưa có test đồng thời; ưu tiên xác nhận cơ chế idempotency trước phát hành.” Tương tự, ghi rõ B cần thêm quan sát khi tăng lưu lượng và C cần bổ sung test timeout sau thành công. **Đừng coi trạng thái chưa đủ bằng chứng là đã an toàn hoặc đã có lỗi.**

## Ghi nhớ

**Chỉ số chất lượng là tín hiệu, rà soát định tính giúp giải thích, bằng chứng hành vi giúp kiểm tra điều hệ thống thực sự làm.** Coverage cao không chứng minh quy tắc đúng; complexity thấp không bảo đảm dễ bảo trì; ít sự cố không đồng nghĩa không có rủi ro.

Để dùng số liệu có trách nhiệm, hãy luôn hỏi **đang đo gì, trong phạm vi nào, công cụ dựa trên giả định gì, hành vi quan trọng nào chưa được kiểm chứng và quyết định nào sẽ thay đổi sau khi có bằng chứng**. Mục tiêu cuối cùng không phải tối đa hóa một điểm số, mà là **giảm rủi ro thực, cải thiện khả năng hiểu và sửa mã, đồng thời giữ những cam kết hành vi mà người dùng cần**.
