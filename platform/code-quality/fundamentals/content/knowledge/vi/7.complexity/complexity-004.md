# Độ phức tạp nhận thức và khác biệt giữa các cách đo

Trong một dự án phần mềm, câu “đoạn mã này quá phức tạp” có thể mang nhiều ý nghĩa: khó đọc, có quá nhiều nhánh điều khiển, số đường đi kiểm thử lớn, xử lý dữ liệu chậm hoặc phụ thuộc vào quá nhiều thành phần khác. Những vấn đề ấy liên quan đến nhau nhưng **không thể thay thế bằng cùng một chỉ số**.

Bài học thuộc chương **Độ phức tạp** của **CODE_QUALITY_FUNDAMENTALS**, hướng đến việc hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Trọng tâm là **Cognitive Complexity** (độ phức tạp nhận thức), sự khác biệt so với các phép đo phổ biến khác và cách dùng số liệu để cải thiện mã trong bối cảnh thực tế.

## 1. Cần hỏi “phức tạp theo nghĩa nào?”

Hãy hình dung ba đoạn mã:

- Một phương thức có nhiều khối điều kiện lồng nhau nhưng xử lý chỉ vài bản ghi. Nó có thể chạy nhanh, song người đọc phải giữ nhiều điều kiện trong đầu để hiểu khi nào mỗi nhánh được thực hiện.
- Một phương thức gồm một vòng lặp đơn giản nhưng thực hiện phép tìm kiếm lồng hai tầng trên hàng triệu phần tử. Cấu trúc có thể dễ hiểu, nhưng thời gian chạy tăng nhanh theo kích thước đầu vào.
- Một phương thức chỉ ba dòng, lần lượt gọi năm dịch vụ khác nhau. Điểm phức tạp cục bộ có thể thấp, nhưng toàn bộ nghiệp vụ vẫn khó hiểu và khó khôi phục khi có sự cố.

Vì vậy, cần xác định đối tượng muốn đánh giá:

| Góc nhìn | Câu hỏi chính | Ví dụ thước đo hoặc bằng chứng |
| --- | --- | --- |
| **Nhận thức** | Người đọc phải giữ bao nhiêu bối cảnh và lần theo bao nhiêu luồng điều khiển? | Cognitive Complexity, review các nhánh lồng, tên và cấu trúc mã |
| **Luồng điều khiển** | Mã có bao nhiêu đường đi độc lập trong sơ đồ điều khiển? | Cyclomatic Complexity |
| **Số đường đi khả thi về cấu trúc** | Có bao nhiêu đường đi không lặp có thể xuất hiện trong phương thức theo cách công cụ mô hình hóa? | NPath Complexity |
| **Thuật toán và tài nguyên** | Khi kích thước dữ liệu tăng, thời gian và bộ nhớ tăng như thế nào? | Big-O, benchmark, profiling, số đo thực tế |
| **Quy mô và bề mặt mã** | Có bao nhiêu dòng hoặc thao tác mã cần xem xét? | LOC, số statement, số phương thức |
| **Mức phụ thuộc** | Thay đổi ở một thành phần lan tới những thành phần nào? | Coupling, fan-out, dependency graph, review ranh giới module |

Không có công thức đáng tin cậy kiểu “Cognitive Complexity thấp ⇒ thuật toán nhanh” hoặc “ít dòng ⇒ dễ bảo trì”. Mỗi phép đo phản ánh một phần của vấn đề.

## 2. Cognitive Complexity là gì?

**Cognitive Complexity** là một phép đo tĩnh nhằm ước lượng **mức khó khăn khi con người đọc và theo dõi luồng điều khiển**. Tư tưởng chính của phép đo được phổ biến bởi SonarSource: một cấu trúc làm gián đoạn luồng đọc tuyến tính thường tạo chi phí nhận thức; cấu trúc nằm sâu trong các cấu trúc điều khiển khác khiến việc theo dõi tình huống khó hơn.

Có ba ý quan trọng:

1. **Thay đổi luồng đọc:** các nhánh `if`, vòng lặp, `catch`, điều kiện nhiều nhánh hoặc một số dạng nhảy điều khiển buộc người đọc suy nghĩ về đường đi tiếp theo.
2. **Chi phí của lồng nhau:** hiểu một `if` bên trong hai `if` khác thường đòi hỏi nhớ thêm các điều kiện bao ngoài. Vì vậy, nhiều cấu trúc được cộng điểm bổ sung theo độ sâu.
3. **Dễ đọc không đồng nghĩa ít cấu trúc:** một số cú pháp giúp diễn đạt trường hợp quen thuộc rõ ràng hơn có thể được đối xử khác nhau, tùy quy tắc công cụ và phiên bản.

Đây là **quy tắc tính điểm theo mô hình**, không phải số giây một người thật cần để hiểu phương thức. Mức hiểu còn phụ thuộc vào tên biến, kiến thức miền, chất lượng hợp đồng, tác dụng phụ, cách đặt trách nhiệm và kinh nghiệm của người đọc.

### 2.1. Những mẫu thường làm tăng chi phí nhận thức

**Lồng điều kiện sâu:**

~~~java
if (authenticated) {
    if (accountActive) {
        if (hasPermission) {
            performAction();
        }
    }
}
~~~

Để hiểu lúc nào gọi `performAction()`, người đọc phải giữ đồng thời cả ba điều kiện. Khi thêm `else`, xử lý lỗi, vòng lặp hoặc `try/catch` lồng vào nữa, chi phí theo dõi tăng mạnh.

**Nhiều đường điều khiển ngầm:** nhánh trả về rải rác trong phương thức dài, `break` có nhãn, nhiều `catch` với hành vi khác nhau hoặc điều kiện boolean quá dài có thể khiến người đọc khó dựng lại luồng xử lý.

**Đưa logic ra khỏi bối cảnh một cách khó theo dõi:** một hàm rất ngắn nhưng gọi liên tiếp nhiều hàm có tên mơ hồ vẫn có thể khó hiểu, dù điểm Cognitive Complexity của riêng nó thấp.

Mặt khác, một số nhánh và vòng lặp là biểu diễn cần thiết của nghiệp vụ. Mục tiêu không phải làm mọi phương thức có điểm 0 mà là **giảm công sức hiểu và rủi ro sửa sai**.

### 2.2. Cách tính điểm phụ thuộc vào công cụ

Quy tắc Sonar về Cognitive Complexity có xét các cấu trúc làm gián đoạn luồng điều khiển, mức lồng nhau và một số trường hợp như chuỗi toán tử logic, đệ quy hoặc cú pháp điều khiển đặc biệt. Việc xử lý **`switch`/switch expression, `else if`, toán tử ba ngôi, lambda, pattern matching, `catch` và các cú pháp mới** phải được kiểm tra theo tài liệu của **phiên bản công cụ đang dùng**.

Không nên tự khẳng định một công thức cộng điểm áp dụng cho mọi ngôn ngữ, mọi phiên bản. Để so sánh hai lần đo, phải giữ nhất quán ngôn ngữ, quy tắc phân tích, phiên bản analyzer và phạm vi đo.

## 3. Ví dụ Java: cùng số nhánh, khác độ khó khi đọc

Giả sử quy tắc nghiệp vụ cho phép một đơn hàng nhận ưu đãi khi:

- Đơn hàng tồn tại.
- Đơn đã được thanh toán.
- Đơn chưa bị hủy.
- Tổng tiền từ **500.000 VND** trở lên.

Ta dùng `record` (Java 16+) để biểu diễn dữ liệu:

~~~java
record Order(long totalVnd, boolean paid, boolean cancelled) {}
~~~

### 3.1. Phiên bản có các nhánh lồng nhau

~~~java
final class EligibilityNested {
    static boolean eligible(Order order) {
        if (order != null) {
            if (order.paid()) {
                if (!order.cancelled()) {
                    return order.totalVnd() >= 500_000;
                }
            }
        }
        return false;
    }
}
~~~

Luồng đọc đi qua ba tầng `if`. Muốn hiểu dòng `return` nằm sâu nhất, người đọc phải nhớ cả ba điều kiện bao quanh.

### 3.2. Phiên bản dùng guard clause

~~~java
final class EligibilityGuards {
    static boolean eligible(Order order) {
        if (order == null) {
            return false;
        }
        if (!order.paid()) {
            return false;
        }
        if (order.cancelled()) {
            return false;
        }
        return order.totalVnd() >= 500_000;
    }
}
~~~

Ở cách thứ hai, mỗi điều kiện loại sớm một trường hợp không đủ điều kiện. Đường xử lý chính nằm ở cuối phương thức, không bị lồng ba cấp.

### 3.3. Vì sao điểm đo có thể khác nhau?

Trong **mô hình đơn giản hóa** chỉ tính các `if` và độ sâu lồng nhau:

| Phép đo | Phiên bản lồng nhau | Phiên bản guard clause |
| --- | --- | --- |
| Số `if` | 3 | 3 |
| Cyclomatic Complexity theo “số quyết định + 1” | 4 | 4 |
| Chi phí nhận thức do ba `if` (minh họa 1 + 2 + 3 so với 1 + 1 + 1) | 6 | 3 |
| Số trường hợp cần suy xét theo quy tắc nghiệp vụ | Không tự giảm | Không tự giảm |
| Cách đọc đường đi chính | Theo dõi ba điều kiện lồng nhau | Lần lượt loại các trường hợp thất bại |

**Các giá trị nhận thức 6 và 3 ở bảng là minh họa cho nguyên tắc cộng chi phí lồng nhau**, không phải kết quả xuất trực tiếp từ một công cụ cụ thể. Với biểu thức và cú pháp phức tạp hơn, phải dùng analyzer để biết điểm được báo thực tế.

Cả hai phiên bản vẫn có ba quyết định `if` nên **Cyclomatic Complexity không giảm** theo phép đếm cơ bản. Người đọc có thể thấy phương thức guard dễ theo dõi hơn, nhưng không vì thế mà mã tự động kiểm thử đủ mọi quy tắc hay không còn lỗi.

### 3.4. Bảo vệ hành vi khi refactor

Có thể dùng JUnit 5 kiểm tra các trường hợp biên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class EligibilityTest {
    @Test
    void rejectsMissingOrder() {
        assertFalse(EligibilityGuards.eligible(null));
    }

    @Test
    void rejectsUnpaidOrder() {
        assertFalse(EligibilityGuards.eligible(
                new Order(800_000, false, false)));
    }

    @Test
    void rejectsCancelledOrder() {
        assertFalse(EligibilityGuards.eligible(
                new Order(800_000, true, true)));
    }

    @Test
    void acceptsPaidActiveOrderAtThreshold() {
        Order order = new Order(500_000, true, false);
        assertTrue(EligibilityGuards.eligible(order));
        assertEquals(
                EligibilityNested.eligible(order),
                EligibilityGuards.eligible(order));
    }

    @Test
    void rejectsOrderBelowThreshold() {
        assertFalse(EligibilityGuards.eligible(
                new Order(499_999, true, false)));
    }
}
~~~

Các bài kiểm thử xác nhận một số trường hợp quan trọng, nhưng **không chứng minh mọi đầu vào đều tương đương**. Khi thay đổi cấu trúc, cần chú ý thứ tự kiểm tra, điều kiện có tác dụng phụ, ngoại lệ và các lối thoát sớm. Ở ví dụ này, các accessor trên `record` không có tác dụng phụ và những điều kiện được giữ đúng thứ tự, giúp việc refactor tương đối an toàn.

## 4. Cyclomatic Complexity đo điều gì?

**Cyclomatic Complexity** gắn với sơ đồ luồng điều khiển (*control-flow graph*) và số đường đi độc lập tuyến tính của đồ thị. Với đồ thị điều khiển thông thường, có thể biểu diễn:

`V(G) = E - N + 2P`

Trong đó `E` là số cạnh, `N` là số nút và `P` là số thành phần liên thông được xét theo quy ước tính của mô hình. Đối với một phương thức có một luồng vào và một luồng ra trong mô hình đơn giản, ta thường dùng cách đếm gần đúng **1 + số điểm quyết định**.

Ví dụ:

~~~java
static String feeLabel(int totalVnd, boolean vip) {
    if (vip) {
        return "FREE";
    }
    if (totalVnd >= 500_000) {
        return "FREE";
    }
    return "STANDARD";
}
~~~

Có hai nhánh `if`, vì thế trong phép đếm cơ bản ta được độ phức tạp chu trình **3**. Điều này nói về cấu trúc các đường đi độc lập, không phải “phương thức có đúng ba bộ dữ liệu đầu vào” hoặc “chỉ cần ba phép thử bất kỳ là đủ”.

### 4.1. Cyclomatic Complexity hữu ích ở đâu?

- Nhận diện phương thức có nhiều nhánh điều khiển cần review kỹ.
- Gợi ý số đường đi độc lập của sơ đồ điều khiển cần được quan tâm khi xây kiểm thử.
- Theo dõi thay đổi cấu trúc điều khiển sau các lần refactor.
- Tìm vùng có nhiều nhánh có nguy cơ che khuất trường hợp biên.

Không nên hiểu điểm cyclomatic là **số ca test tối thiểu bảo đảm không có lỗi**. Kiểm thử còn cần giá trị biên, dữ liệu hợp lệ và không hợp lệ, hợp đồng nghiệp vụ, trạng thái chia sẻ, tác dụng phụ và điều kiện lỗi. Một đường đi có thể chứa nhiều điều kiện đầu vào quan trọng.

### 4.2. Khác Cognitive Complexity ở đâu?

Cyclomatic Complexity xem **độ phân nhánh của luồng điều khiển**. Cognitive Complexity còn nhấn mạnh **gánh nặng theo dõi cấu trúc lồng nhau**. Vì vậy, giảm độ sâu lồng bằng guard clause có thể giảm chi phí nhận thức mà số nhánh vẫn giữ nguyên.

Một số analyzer có cách đếm khác nhau cho toán tử `&&`, `||`, nhánh `switch`, biểu thức điều kiện, xử lý ngoại lệ hoặc cú pháp mới. Không nên so sánh các điểm số lấy từ hai công cụ không cùng quy tắc như thể chúng có đơn vị hoàn toàn giống nhau.

## 5. NPath Complexity: số đường đi có thể tăng nhanh hơn số nhánh

**NPath Complexity** tìm cách ước lượng số đường đi không lặp trong một đoạn mã dựa trên cấu trúc các điều kiện và nhánh. Phép tính này đặc biệt hữu ích để nhận ra trường hợp có nhiều tổ hợp xử lý.

Ví dụ, xét bốn điều kiện độc lập chạy nối tiếp:

~~~java
if (needsEmail) {
    sendEmail();
}
if (needsSms) {
    sendSms();
}
if (needsAudit) {
    writeAudit();
}
if (needsReceipt) {
    generateReceipt();
}
~~~

Mỗi `if` có lựa chọn vào hoặc bỏ qua. Theo mô hình tổ hợp đơn giản, bốn lựa chọn độc lập tạo **2^4 = 16** tổ hợp đường đi. Trong khi đó, phép đếm Cyclomatic Complexity cơ bản chỉ là **4 + 1 = 5**.

Đây là điểm khác biệt quan trọng: số nhánh tăng tuyến tính, nhưng **số tổ hợp đường đi** có thể tăng theo cấp số nhân khi các điều kiện độc lập được ghép nối.

Không phải mọi tổ hợp đều **khả thi trên dữ liệu thực**. Ví dụ, `needsReceipt` có thể chỉ đúng khi `needsEmail` đúng; khi đó một số tổ hợp bị loại bởi ràng buộc nghiệp vụ. Các công cụ NPath khác nhau cũng có thể tính toán biểu thức boolean, `switch`, vòng lặp hoặc lối thoát sớm theo quy tắc khác nhau. Vì vậy, NPath là **tín hiệu về không gian đường đi tiềm năng**, không phải bộ đếm chính xác các ca nghiệp vụ cần kiểm thử.

Khi NPath lớn, hãy xem liệu có nhiều tổ hợp trạng thái được phép không, những tổ hợp nào có ý nghĩa, và có thể gom các hành vi liên quan thành quyết định rõ ràng hơn không. Thêm một lớp trừu tượng không tự giảm số trường hợp nghiệp vụ.

## 6. Big-O: phức tạp về chi phí chạy, không phải độ khó khi đọc

**Big-O** thường mô tả bậc tăng của thời gian hoặc bộ nhớ theo kích thước đầu vào `n`, dưới các giả định về cấu trúc dữ liệu và phép toán. Một thuật toán dễ đọc vẫn có thể quá chậm khi dữ liệu tăng.

Giả sử cần kiểm tra một danh sách có mã định danh trùng hay không.

### 6.1. Duyệt các cặp phần tử

~~~java
import java.util.List;
import java.util.Objects;

final class DuplicateSearch {
    static boolean hasDuplicate(List<String> ids) {
        for (int i = 0; i < ids.size(); i++) {
            for (int j = i + 1; j < ids.size(); j++) {
                if (Objects.equals(ids.get(i), ids.get(j))) {
                    return true;
                }
            }
        }
        return false;
    }
}
~~~

Với một `ArrayList`, việc lấy phần tử theo chỉ số thông thường có chi phí hằng số. Nếu không có trùng để dừng sớm, thuật toán phải so sánh khoảng `n(n-1)/2` cặp, tức thời gian **O(n²)**. Bộ nhớ bổ sung ngoài danh sách đầu vào là **O(1)**.

Nếu truyền vào một `LinkedList`, việc `get(i)` không có cùng chi phí truy cập chỉ số như `ArrayList`. Vì thế, đánh giá độ phức tạp phải nêu **cấu trúc dữ liệu và giả thiết về phép toán**; chỉ nhìn số vòng lặp là chưa đủ.

### 6.2. Dùng tập hợp để phát hiện phần tử đã gặp

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class DuplicateSearchFast {
    static boolean hasDuplicate(List<String> ids) {
        Set<String> seen = new HashSet<>();
        for (String id : ids) {
            if (!seen.add(id)) {
                return true;
            }
        }
        return false;
    }
}
~~~

Với giả thiết về phân bố hash hợp lý và thao tác `HashSet.add` có chi phí trung bình hằng số, thuật toán thứ hai có thời gian kỳ vọng **O(n)** và bộ nhớ bổ sung **O(n)** trong trường hợp phải giữ các phần tử đã gặp. Hiệu năng thực tế còn phụ thuộc kích thước dữ liệu, chi phí băm, va chạm, cấp phát và bộ nhớ.

So sánh:

| Góc nhìn | Duyệt mọi cặp | Dùng `HashSet` |
| --- | --- | --- |
| Bậc thời gian điển hình | O(n²) với truy cập chỉ số O(1) | O(n) kỳ vọng với hash phù hợp |
| Bộ nhớ bổ sung | O(1) | O(n) |
| Độ sâu vòng lặp | Hai tầng | Một tầng |
| Điều cần kiểm tra | Cấu trúc `List`, kích thước dữ liệu | Hành vi `equals`/`hashCode`, dung lượng bộ nhớ |
| Khả năng đọc | Có thể dễ hiểu với đầu vào rất nhỏ | Thường diễn đạt trực tiếp ý “đã gặp” |

Một cải thiện thuật toán có thể đồng thời giảm độ sâu lồng nhau và tăng tốc; nhưng nó cũng thêm cấu trúc dữ liệu, tiêu thụ bộ nhớ và dựa vào hợp đồng hash. Không được kết luận chọn phương án nào từ Big-O một cách máy móc mà không xét kích thước đầu vào và giới hạn tài nguyên.

## 7. LOC, số câu lệnh và chỉ số tổng hợp

**Lines of Code (LOC)** hoặc số câu lệnh giúp đo quy mô tương đối, nhưng **mã dài không mặc nhiên khó hiểu**. Phương thức 50 dòng gồm các phép gán có tên rõ ràng có thể dễ đọc hơn một biểu thức 5 dòng có nhiều điều kiện lồng và toán tử ba ngôi. LOC cũng dễ thay đổi vì format hoặc quy tắc đếm comment và dòng trống.

**Halstead metrics** xuất phát từ số lượng toán tử và toán hạng theo một mô hình phân tích mã. Chúng có thể mô tả độ lớn và một số đặc tính của biểu thức, nhưng không tự diễn tả quy tắc nghiệp vụ hay chi phí hiểu kiến trúc.

**Maintainability Index** là một chỉ số tổng hợp có những biến thể kết hợp các phép đo như Halstead, Cyclomatic Complexity và LOC. Cách chuẩn hóa, thang điểm và ngưỡng cảnh báo không hoàn toàn giống nhau giữa công cụ. Không thể lấy số “80” từ công cụ A rồi khẳng định tốt hơn số “75” từ công cụ B nếu chưa biết hai công cụ tính gì.

**Coupling/fan-out** cho thấy một thành phần phụ thuộc bao nhiêu phần khác, có thể gợi ý khó thay đổi khi các phụ thuộc không ổn định. Nhưng số phụ thuộc nhiều chưa chắc là vấn đề: một lớp điều phối có thể cần gọi nhiều thành phần được phân tách hợp lý. Chất lượng ranh giới, độ ổn định và tính chất phụ thuộc quan trọng hơn số lượng đơn thuần.

## 8. Bảng so sánh các phép đo

| Phép đo | Tập trung vào | Phát hiện tốt | Không chứng minh được |
| --- | --- | --- | --- |
| **Cognitive Complexity** | Nỗ lực theo dõi cấu trúc điều khiển | Lồng nhau sâu, luồng đọc rối | Tốc độ chạy, đúng nghiệp vụ, mọi chi phí đọc hiểu |
| **Cyclomatic Complexity** | Đường đi độc lập trong đồ thị điều khiển | Phân nhánh nhiều, điểm cần xem xét khi thiết kế test | Số ca test chắc chắn đủ, mức khó hiểu thực tế |
| **NPath Complexity** | Tổ hợp các đường đi cấu trúc | Sự bùng nổ tổ hợp của nhiều nhánh | Mọi đường có khả thi, mọi đường cần kiểm thử riêng |
| **Big-O** | Mức tăng tài nguyên theo kích thước dữ liệu | Rủi ro không mở rộng ở quy mô lớn | Hằng số thực thi, độ trễ thực tế, khả năng đọc |
| **LOC** | Kích thước mã theo quy ước đếm | Vùng quá lớn cần xem xét phân chia | Chất lượng thiết kế hoặc độ chính xác |
| **Halstead/MI** | Đặc tính cú pháp hoặc chỉ số tổng hợp | So sánh xu hướng trong cùng bộ quy tắc | Chất lượng tuyệt đối hay quyết định kiến trúc tốt |
| **Coupling/fan-out** | Mối liên hệ giữa thành phần | Phạm vi phụ thuộc có thể ảnh hưởng khi sửa | Ý nghĩa nghiệp vụ và mức ổn định của các phụ thuộc |

Các phép đo **bổ sung thông tin cho nhau**. Khi một chỉ số tăng, câu hỏi tiếp theo phải là “tại sao?” chứ không phải “làm sao sửa code để con số thấp nhất?”.

## 9. Điểm thấp không tự bảo đảm mã dễ hiểu

Hãy xét đoạn mã giả:

~~~java
final class CheckoutCoordinator {
    Receipt checkout(OrderRequest request) {
        return orchestrator.execute(request);
    }
}
~~~

Phương thức chỉ một lời gọi, thường có điểm Cognitive Complexity và Cyclomatic Complexity thấp. Nhưng `orchestrator.execute` có thể ẩn nhiều bước xác thực, lấy giá, giữ hàng, thanh toán, gửi sự kiện và xử lý thất bại. Để hiểu tính đúng đắn của toàn luồng, người đọc vẫn phải theo dõi các hợp đồng giữa nhiều thành phần.

Điều này chỉ ra hai rủi ro:

1. **Chỉ chuyển phức tạp sang hàm khác:** cắt một phương thức dài thành nhiều hàm tên mơ hồ có thể làm điểm cục bộ giảm mà tổng công sức hiểu không giảm.
2. **Phức tạp phân tán:** retry, trạng thái chia sẻ, bất đồng bộ, giao dịch nhiều bước và phiên bản API thường nằm ngoài những nhánh nhìn thấy trong một phương thức.

Tách hàm có giá trị khi nó biểu đạt **đơn vị ý nghĩa độc lập**, có tên rõ, hợp đồng đơn giản và trách nhiệm phù hợp. Khi đánh giá, hãy đọc cả các hàm được gọi, đầu ra, lỗi, tác dụng phụ và ranh giới dữ liệu.

## 10. Phân biệt chỉ số và tín hiệu từ người sử dụng mã

Một chỉ số tĩnh là **tín hiệu**, không phải phán quyết về chất lượng. Có những phương thức có nhánh nhiều vì biểu diễn một máy trạng thái rõ ràng, kiểm thử đầy đủ, ít thay đổi và có chú thích nghiệp vụ phù hợp. Cũng có đoạn mã ít nhánh nhưng tên mơ hồ, phụ thuộc biến toàn cục hoặc gọi dịch vụ ngoài theo cách khó kiểm soát.

Có thể kết hợp các nguồn bằng chứng:

- **Review của người bảo trì:** mất bao lâu để xác định điều kiện vào, luồng thành công và lỗi?
- **Lịch sử thay đổi:** một quy tắc nhỏ cần sửa bao nhiêu vị trí, đã có lỗi hồi quy chưa?
- **Kiểm thử:** các trường hợp nghiệp vụ, điều kiện biên, trạng thái lỗi và đường tích hợp đã được bảo vệ chưa?
- **Chỉ số tĩnh:** phương thức nào có cấu trúc bất thường so với phần còn lại?
- **Quan sát vận hành:** lỗi, thời gian xử lý, tải và mức sử dụng bộ nhớ có đúng mục tiêu không?
- **Bối cảnh:** đây là PoC dùng một lần, công cụ nội bộ xử lý dữ liệu thật hay dịch vụ phải bảo trì nhiều năm?

Một quyết định refactor có căn cứ nên giải thích **khó khăn thật**, **mục tiêu cải thiện** và **cách kiểm chứng hành vi được giữ nguyên**.

## 11. Giảm độ phức tạp nhận thức một cách có ý nghĩa

### 11.1. Làm rõ điều kiện và loại trường hợp thất bại sớm

Guard clause hữu ích khi có các điều kiện không đáp ứng yêu cầu và không cần thực hiện thêm công việc. Tuy nhiên, không nên biến phương thức dài thành hàng chục `return` phân tán khó theo dõi; ưu tiên giữ đường đi chính dễ đọc.

### 11.2. Đặt tên cho khái niệm nghiệp vụ

Ví dụ:

~~~java
boolean eligible = customer.isVip()
        && order.totalVnd() >= minimumVipOrderVnd
        && !order.isCancelled();
~~~

Có thể diễn đạt thành các hàm hoặc biến có tên khi mỗi điều kiện có nghĩa độc lập. Nếu logic lặp lại ở nhiều nơi vì cùng một quy tắc nghiệp vụ, nên cân nhắc gom quy tắc vào một nguồn được kiểm thử. Đừng tách chỉ để mỗi dòng ngắn hơn.

### 11.3. Dùng cấu trúc biểu diễn đúng mô hình

Với danh sách trạng thái rời rạc, `switch` hoặc ánh xạ dữ liệu có thể rõ hơn chuỗi `if/else if` dài. Với quy tắc có nhiều tổ hợp, bảng quyết định (*decision table*) giúp kiểm tra trường hợp thiếu hoặc xung đột. Với các giai đoạn xử lý, trạng thái và chuyển tiếp tường minh có thể tốt hơn nhiều biến boolean độc lập.

Dù chọn cách nào, phải giữ đúng yêu cầu, đặc biệt với giá trị không biết trước, mặc định, trường hợp lỗi và khả năng mở rộng trạng thái.

### 11.4. Tách xử lý thuần khỏi phụ thuộc bên ngoài

Một hàm tính toán thuần thường dễ kiểm thử hơn hàm vừa gọi API, kiểm tra điều kiện, ghi dữ liệu và gửi thông báo. Có thể giữ luồng điều phối đơn giản, đưa quy tắc nghiệp vụ thành hàm có đầu vào và đầu ra rõ ràng, đồng thời quản lý lỗi tích hợp tại ranh giới phù hợp.

### 11.5. Xác nhận cải thiện bằng kiểm thử và review

Quy trình refactor cơ bản:

1. Ghi lại hành vi hiện tại và các ca nghiệp vụ quan trọng, kể cả đầu vào không hợp lệ.
2. Viết hoặc củng cố kiểm thử hồi quy phù hợp.
3. Chỉ thay đổi cấu trúc cần thiết: giảm lồng nhau, đặt tên hoặc phân chia trách nhiệm.
4. Chạy lại kiểm thử và xem xét tác dụng phụ, ngoại lệ, thứ tự thao tác.
5. Đọc lại mã từ góc nhìn người chưa từng sửa nó, đánh giá sự rõ ràng của luồng chính.
6. Dùng chỉ số như bằng chứng bổ sung, kiểm tra điểm số ở cả hàm mới lẫn các hàm được gọi.

**Giảm điểm mà làm tăng phụ thuộc, che giấu nghiệp vụ hoặc thay đổi hành vi là refactor thất bại.**

## 12. Dùng ngưỡng cảnh báo thế nào để không tối ưu sai mục tiêu?

Công cụ phân tích tĩnh thường đặt ngưỡng cảnh báo cho Cognitive Complexity hoặc Cyclomatic Complexity. Ngưỡng giúp nhóm ưu tiên review, nhưng **không phải ranh giới khoa học tuyệt đối giữa mã tốt và mã xấu**.

Cách dùng thực tế:

- **Gắn ngưỡng với mục đích:** cần phát hiện hàm khó đọc, hay tìm vùng cần thêm kiểm thử? Hai mục đích có thể dùng hai chỉ số khác nhau.
- **Bắt đầu từ thực tế codebase:** xem phân bố điểm, loại mã, ngôn ngữ, tuổi thọ và mức rủi ro trước khi áp dụng ngưỡng cho mọi nơi.
- **Quan tâm thay đổi mới:** theo dõi khi một phương thức đang sửa tăng độ lồng hoặc số đường điều khiển mà không có lý do hợp lý.
- **Không ép mọi hàm về 0:** một số nhánh là nghiệp vụ thực; cố giấu chúng bằng thủ thuật cú pháp có thể giảm độ rõ ràng.
- **Nhìn kết quả theo thời gian:** so sánh trong cùng phiên bản analyzer và cùng quy tắc để tránh hiểu nhầm do thay đổi công cụ.
- **Ưu tiên nơi rủi ro cao:** nhánh điều kiện trong thanh toán, bảo mật hoặc ghi dữ liệu có thể cần review và test nhiều hơn dù điểm chưa vượt ngưỡng.

Khi một phương thức bị cảnh báo, phản hồi tốt là **xác định chỗ nào khiến người đọc khó theo dõi**. Nếu cảnh báo chỉ mang tính đặc thù của cú pháp nhưng cấu trúc đã rõ và đủ kiểm thử, nhóm có thể ghi nhận lý do, thay vì refactor chỉ để làm đẹp báo cáo.

## 13. Bài tập phân tích

### Tình huống A: Đổi `if` lồng nhau thành guard

Một hàm có bốn `if` lồng nhau. Nhóm chuyển thành bốn guard clause và giữ nguyên thứ tự kiểm tra. Điểm Cognitive Complexity giảm, nhưng Cyclomatic Complexity vẫn bằng 5 theo mô hình cơ bản.

**Câu hỏi:** công cụ có báo cáo sai không?

**Gợi ý:** Không nhất thiết. Số điểm quyết định không đổi, nhưng mức lồng giảm. Hai phép đo trả lời hai câu hỏi khác nhau. Cần kiểm thử để chắc rằng việc chuyển đổi không đổi hành vi.

### Tình huống B: Thay vòng lặp đôi bằng `HashSet`

Một phương thức kiểm tra trùng có hai vòng lặp trên `ArrayList`. Sau refactor, chỉ còn một vòng lặp và dùng `HashSet`.

**Câu hỏi:** đã cải thiện tiêu chí nào, có đánh đổi gì?

**Gợi ý:** Trong điều kiện hash hoạt động phù hợp, thời gian kỳ vọng có thể từ O(n²) thành O(n); mã cũng có thể dễ diễn đạt hơn. Đổi lại, bộ nhớ bổ sung tăng từ O(1) lên O(n). Cần xác nhận ngữ nghĩa `equals`/`hashCode` và dữ liệu đầu vào.

### Tình huống C: Chia một hàm thành 12 hàm một dòng

Điểm Cognitive Complexity của hàm gốc giảm đáng kể sau khi tách, nhưng hàm mới có tên như `step1`, `step2`, và việc hiểu luồng đòi hỏi nhảy giữa nhiều tệp.

**Câu hỏi:** chất lượng có chắc đã tăng?

**Gợi ý:** Không. Việc chia mã có thể phân tán gánh nặng hiểu. Cần xem ranh giới trách nhiệm, tên, tính kết dính, tác dụng phụ và số nơi phải theo dõi khi sửa.

### Tình huống D: Có nhiều test nhưng kết quả sản xuất sai

Một phương thức có Cyclomatic Complexity thấp, bao phủ nhánh rất cao, song vẫn tính sai phí ở trường hợp đơn hàng đúng ngưỡng ưu đãi.

**Câu hỏi:** chỉ số nào đã không trả lời đúng câu hỏi nghiệp vụ?

**Gợi ý:** Độ phức tạp và tỷ lệ bao phủ nhánh không chứng minh kiểm thử có giá trị đầu vào phù hợp. Cần kiểm thử biên dựa trên đặc tả và xem xét bất biến nghiệp vụ.

## 14. Bộ câu hỏi dùng khi review

Khi thấy một phương thức được đánh dấu “complex”, hãy lần lượt hỏi:

1. **Phức tạp theo cách nào?** Nhiều điều kiện lồng, nhiều tổ hợp đường đi, thuật toán chậm, hay phụ thuộc nhiều thành phần?
2. **Điểm đo được tính như thế nào?** Công cụ, phiên bản, quy tắc, phạm vi phương thức và ngôn ngữ?
3. **Có hành vi nghiệp vụ nào thật sự khó thấy?** Điều kiện biên, lối thoát sớm, lỗi, tác dụng phụ hoặc trạng thái dùng chung?
4. **Có thể diễn đạt ý định rõ hơn không?** Guard clause, tên nghiệp vụ, quyết định thành bảng hay ranh giới trách nhiệm?
5. **Điều gì sẽ bị đánh đổi?** Bộ nhớ, thời gian, phụ thuộc mới, chi phí vận hành hoặc kiểm thử?
6. **Làm sao bảo vệ hành vi khi sửa?** Test hồi quy, contract test, benchmark hoặc review theo rủi ro?
7. **Có đang chuyển vấn đề sang nơi khác không?** Sau khi tách hàm, tổng luồng và các phụ thuộc có dễ hiểu hơn không?

**Cognitive Complexity giúp phát hiện nơi luồng điều khiển có thể khó theo dõi; Cyclomatic Complexity mô tả độ phân nhánh; NPath nhìn vào tổ hợp đường đi; Big-O và benchmark nhìn vào chi phí xử lý.** Biết ranh giới của mỗi phép đo giúp nhóm dùng đúng bằng chứng cho đúng quyết định. Với **CODE_QUALITY_FUNDAMENTALS**, mục tiêu sau cùng là mã **đáng tin cậy khi chạy, dễ hiểu khi đọc và dễ thay đổi khi yêu cầu phát triển**, chứ không phải đạt một điểm số đẹp riêng lẻ.
