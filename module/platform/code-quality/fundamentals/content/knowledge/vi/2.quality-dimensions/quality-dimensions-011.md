# Chọn dấu hiệu và bằng chứng cho từng chiều chất lượng

Một nhóm phát triển nhận thấy dịch vụ tính tiền có phương thức dài, nhiều điều kiện và thời gian phản hồi đôi lúc tăng mạnh. Nhóm nên sửa vấn đề nào trước? Phương thức dài có chắc gây lỗi không? Một lần gọi API chậm có đủ chứng minh hệ thống gặp vấn đề hiệu năng không? Để trả lời, nhóm cần biết **chiều chất lượng nào đang bị ảnh hưởng**, nhận ra **dấu hiệu đáng chú ý** và chọn **bằng chứng phù hợp** để kiểm tra nhận định.

Trong phạm vi **Code Quality Fundamentals**, chất lượng mã nguồn được xem qua các thuộc tính làm cho phần mềm **đáng tin cậy, dễ hiểu và dễ thay đổi**. Mỗi thuộc tính cần cách quan sát khác nhau. Số dòng mã không đo được tính đúng đắn; kiểm thử chức năng thành công không tự chứng minh hiệu năng tốt; độ bao phủ kiểm thử cao không bảo đảm kiểm thử phát hiện được sai sót quan trọng.

Bài học này hướng dẫn chọn phép kiểm tra theo câu hỏi cụ thể, phân biệt tín hiệu với bằng chứng và đọc kết quả một cách thận trọng. Các chỉ số trong bài là ví dụ về **cách đo**, không phải ngưỡng bắt buộc áp dụng cho mọi dự án.

## 1. Phân biệt chiều chất lượng, dấu hiệu, bằng chứng và kết luận

Khi trao đổi về chất lượng, bốn khái niệm sau thường bị dùng lẫn nhau:

| Khái niệm | Ý nghĩa | Ví dụ ở dịch vụ tính tiền |
| --- | --- | --- |
| **Chiều chất lượng** (*quality dimension*) | Thuộc tính muốn bảo đảm hoặc cải thiện | Tính đúng đắn, tính dễ bảo trì, hiệu năng |
| **Dấu hiệu** (*signal/indicator*) | Quan sát gợi ý rằng cần xem xét một chiều chất lượng | Một quy tắc giảm giá được viết ở ba nơi |
| **Bằng chứng** (*evidence*) | Kết quả quan sát/kiểm tra có bối cảnh, có thể đối chiếu | Ba đường xử lý dùng các điều kiện biên khác nhau; kiểm thử tái hiện hai kết quả khác nhau cho cùng quy tắc |
| **Kết luận** (*assessment*) | Nhận định có giới hạn dựa trên các bằng chứng | Quy tắc phân tán đang tạo rủi ro sai lệch khi sửa; cần gom điểm quyết định và bổ sung kiểm thử |

Ví dụ, câu **“phương thức này có 150 dòng”** là một quan sát mô tả. Nó có thể là dấu hiệu về khả năng đọc hiểu, nhưng chưa đủ để kết luận phương thức sai hoặc nhất thiết phải tách. Để kết luận có vấn đề, cần xem người bảo trì phải hiểu bao nhiêu trách nhiệm, các đường đi có độc lập hay không, lỗi đã xuất hiện ở đâu và những thay đổi dự kiến sẽ tác động thế nào.

Tương tự, **“95% code coverage”** là số liệu về phạm vi mã được chạy khi kiểm thử. Nó không nói rằng các giá trị trả về được khẳng định đúng, các trường hợp biên được chọn phù hợp hay quy tắc nghiệp vụ đã được kiểm tra đầy đủ.

Một bằng chứng hữu ích nên trả lời được: **Đo cái gì? Trong điều kiện nào? Bằng cách nào? Kết quả bao nhiêu? Có thể kết luận đến đâu?**

## 2. Bản đồ chọn dấu hiệu và bằng chứng theo chiều chất lượng

Các chiều trong bảng có liên quan với nhau và không nhất thiết là những nhóm loại trừ nhau. Chẳng hạn *khả năng đọc hiểu* và *khả năng kiểm thử* đều góp phần tạo nên *khả năng bảo trì*. Khi đánh giá, hãy đặt tên rõ thuộc tính cần cải thiện thay vì chỉ nói chung rằng “chất lượng kém”.

| Chiều chất lượng | Dấu hiệu nên chú ý | Bằng chứng có sức thuyết phục hơn | Điểm cần tránh khi diễn giải |
| --- | --- | --- | --- |
| **Tính đúng đắn** (*correctness*) | Kết quả bất thường, lỗi ở trường hợp biên, quy tắc không nhất quán | Trường hợp tái hiện với đầu vào, kết quả kỳ vọng theo yêu cầu và kết quả thực tế; kiểm thử hồi quy | “Test xanh” chỉ khẳng định các tình huống đã được kiểm tra |
| **Độ tin cậy** (*reliability*) | Lỗi không liên tục, thao tác thất bại khi tải tăng, sự cố lặp lại | Tần suất lỗi trên số yêu cầu, log tương quan, thử nghiệm đường lỗi, thời gian phục hồi | Không kết luận từ một sự cố không rõ phạm vi và điều kiện |
| **An toàn thông tin** (*security*) | Đầu vào thiếu xác thực, quyền kiểm tra không đầy đủ, dữ liệu nhạy cảm có thể bị lộ | Tình huống kiểm thử quyền truy cập, rà soát luồng dữ liệu, báo cáo phân tích được xác minh | Cảnh báo công cụ là điểm khởi đầu, không tự động chứng minh lỗ hổng khai thác được |
| **Hiệu năng** (*performance*) | Phản hồi chậm, tăng bộ nhớ, nhiều truy vấn thừa | Phân bố độ trễ, thông lượng, CPU/bộ nhớ, hồ sơ thực thi với tải và môi trường xác định | Không so thời gian đo trên những cấu hình hoặc khối lượng công việc khác nhau |
| **Khả năng đọc hiểu** (*readability/understandability*) | Tên khó hiểu, điều kiện rối, trách nhiệm không rõ, nhiều trường hợp đặc biệt | Review có chỉ ra chỗ hiểu nhầm, thời gian và số bước truy vết một yêu cầu, ví dụ đường đi khó giải thích | Ít dòng hoặc ít hàm chưa chắc dễ hiểu hơn |
| **Khả năng thay đổi/bảo trì** (*modifiability/maintainability*) | Một thay đổi phải sửa nhiều nơi; phụ thuộc vòng; lỗi hồi quy khi sửa | Phạm vi ảnh hưởng của thay đổi thực tế, nơi quy tắc bị lặp, lịch sử lỗi liên quan, kết quả review thay đổi | Số file sửa hoặc độ phức tạp tĩnh chỉ là chỉ báo gián tiếp |
| **Khả năng kiểm thử** (*testability*) | Cần cơ sở dữ liệu thật cho mọi test, phụ thuộc thời gian, test chạy không ổn định | Khả năng chạy test độc lập, cách cô lập phụ thuộc, tần suất test không ổn định, độ rõ của đầu vào/đầu ra | Có nhiều test chưa chắc thiết kế đã dễ kiểm thử |
| **Khả năng quan sát và chẩn đoán** (*observability/diagnosability*) | Không xác định được giao dịch lỗi hoặc nguyên nhân thất bại | Log có ngữ cảnh, trace, chỉ số liên kết với giao dịch, khả năng tái dựng một đường xử lý | Nhiều log chưa chắc giúp chẩn đoán; log còn có rủi ro lộ dữ liệu |

Đối với sản phẩm cụ thể, có thể xem xét thêm khả năng tương thích, tính di động, khả năng sử dụng hoặc khả năng mở rộng. Những chiều này thường đòi hỏi bằng chứng ở cấp hệ thống hoặc trải nghiệm người dùng, vượt ra ngoài một file mã nguồn. **Phạm vi đánh giá cần khớp với phạm vi bằng chứng.**

## 3. Tính đúng đắn: bắt đầu từ hợp đồng hành vi

**Câu hỏi:** Cùng một đầu vào và trạng thái hệ thống, chương trình có tạo ra kết quả phù hợp với yêu cầu không?

Dấu hiệu thường gặp gồm sai lệch số tiền, điều kiện biên được xử lý khác nhau, ngoại lệ bất ngờ và chức năng chỉ đúng với dữ liệu phổ biến. Với chiều này, bằng chứng mạnh là một tình huống **có thể tái hiện**, gồm đầu vào, điều kiện ban đầu, quy tắc kỳ vọng và kết quả thực tế.

Ví dụ quy tắc tính chiết khấu giả định: khách hàng được giảm 10% trên tổng tiền hàng, mức giảm tối đa 50.000 đồng, và tổng tiền hàng phải không âm. Khi kiểm thử, cần chọn cả tình huống bình thường lẫn tại biên và ngoài biên:

| Tiền hàng (đồng) | Chiết khấu kỳ vọng (đồng) | Lý do chọn |
| ---: | ---: | --- |
| 0 | 0 | Giá trị hợp lệ nhỏ nhất |
| 100.000 | 10.000 | Trường hợp thông thường |
| 500.000 | 50.000 | Đúng ngưỡng giới hạn |
| 500.001 | 50.000 | Vừa vượt giới hạn |
| -1 | Báo lỗi đầu vào | Trường hợp không hợp lệ |

Nếu dùng Java và JUnit 5, có thể ghi lại hợp đồng bằng kiểm thử tham số hóa (giả sử lớp `DiscountPolicy` và phương thức `discountVnd(long)` đã tồn tại):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class DiscountPolicyTest {
    private final DiscountPolicy policy = new DiscountPolicy();

    @ParameterizedTest
    @CsvSource({
        "0, 0",
        "100000, 10000",
        "500000, 50000",
        "500001, 50000"
    })
    void respectsDiscountRules(long subtotalVnd, long expectedDiscountVnd) {
        assertEquals(expectedDiscountVnd, policy.discountVnd(subtotalVnd));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.discountVnd(-1));
    }
}
```

Kiểm thử trên chỉ là một cách mô tả hành vi kỳ vọng; **nó chưa phải bằng chứng kiểm thử đã chạy thành công**. Khi dùng trong dự án thật, cần chạy trên phiên bản mã cụ thể và lưu kết quả. Nếu tiền tệ cho phép phần lẻ, còn phải thống nhất cách làm tròn và kiểu dữ liệu; quy tắc minh họa ở đây dùng tiền đồng nguyên.

Để kết luận có cải thiện, hãy so sánh cùng bộ kiểm thử trước và sau sửa, đồng thời kiểm tra trường hợp đã tạo lỗi ban đầu. Việc thêm nhiều test giống nhau mà không mở rộng tình huống quan trọng không làm bằng chứng mạnh lên tương ứng.

## 4. Độ tin cậy: xem hành vi qua thời gian và khi có lỗi

**Câu hỏi:** Chức năng có hoạt động ổn định trong những điều kiện hệ thống thực sự gặp phải không?

Một chức năng có thể đúng trong kiểm thử đơn lẻ nhưng thất bại khi mạng chập chờn, dịch vụ phụ trợ chậm, yêu cầu được gửi lại hoặc nhiều yêu cầu cùng cập nhật một dữ liệu. Vì vậy, độ tin cậy thường cần quan sát **lặp lại theo thời gian** và kiểm tra đường lỗi.

Ví dụ với API tạo đơn hàng:

- **Dấu hiệu:** Thỉnh thoảng khách nhận thông báo lỗi, sau khi thử lại có hai đơn hàng giống nhau.
- **Bằng chứng cần tìm:** Các yêu cầu có cùng mã idempotency, mã phản hồi, dấu thời gian, giao dịch ghi dữ liệu và số đơn hàng thực sự được tạo.
- **Kiểm tra:** Mô phỏng gửi lại sau timeout, thử nhiều yêu cầu đồng thời, kiểm tra giao dịch và ràng buộc chống trùng.
- **Giới hạn kết luận:** Một lần thử không tạo đơn trùng không chứng minh mọi lịch trình chạy đồng thời đều an toàn.

Với số liệu vận hành, luôn kèm **mẫu số và khoảng thời gian**. Ví dụ “12 lỗi trên 20.000 yêu cầu trong 24 giờ” cho nhiều thông tin hơn “hôm nay có 12 lỗi”. Tuy nhiên, vẫn cần xét các yêu cầu có cùng loại, phần trăm lưu lượng bị ảnh hưởng và mức độ nghiêm trọng. Khi điều tra, phân biệt lỗi do mã của mình, phụ thuộc bên ngoài và cấu hình môi trường.

Kiểm tra khôi phục sau lỗi, khả năng gửi lại an toàn và xử lý dữ liệu nhất quán thường có giá trị cao hơn một chỉ số phức tạp của phương thức khi mục tiêu là giảm sự cố sản xuất.

## 5. An toàn thông tin: kiểm tra ranh giới tin cậy và quyền hạn

**Câu hỏi:** Thành phần có từ chối những thao tác không được phép và bảo vệ dữ liệu khi gặp đầu vào không đáng tin cậy không?

Các dấu hiệu đáng xem gồm sử dụng dữ liệu đầu vào để ghép câu truy vấn, thiếu kiểm tra quyền ở phía máy chủ, ghi token vào log hoặc phụ thuộc chứa lỗ hổng đã được công bố. Tuy nhiên, một cảnh báo phân tích tĩnh đôi khi là kết quả dương tính giả; không thể chỉ đếm cảnh báo rồi kết luận ứng dụng an toàn hay không an toàn.

Với API xem hóa đơn theo ID, có thể thiết kế các trường hợp bằng chứng sau:

| Trường hợp | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- |
| Chủ hóa đơn truy cập | Được trả dữ liệu cho phép | Kiểm thử API với phiên đăng nhập hợp lệ |
| Người dùng khác truy cập cùng ID | Bị từ chối theo chính sách; không lộ chi tiết hóa đơn | Kiểm thử kiểm soát truy cập ở máy chủ |
| Người chưa xác thực truy cập | Không truy cập được dữ liệu cần bảo vệ | Kiểm thử xác thực |
| Dữ liệu nhạy cảm xuất hiện trong log | Không ghi nội dung bị cấm hoặc phải che thông tin | Kiểm tra log trong môi trường kiểm thử và review luồng dữ liệu |

Khi phát hiện vấn đề, ghi rõ **đường vào, tài nguyên cần bảo vệ, quyền của tác nhân, điều kiện xảy ra và tác động**. Đối với dữ liệu nhạy cảm, dùng dữ liệu giả trong bằng chứng và giới hạn việc chia sẻ log. Các bài kiểm thử nêu trên hỗ trợ đánh giá một nhóm rủi ro cụ thể, không phải chứng chỉ an toàn toàn hệ thống.

## 6. Hiệu năng: chọn phép đo khớp với trải nghiệm thực tế

**Câu hỏi:** Hệ thống có đáp ứng mục tiêu thời gian và tài nguyên dưới khối lượng công việc đã định không?

Dấu hiệu có thể là độ trễ tăng đột biến, thời gian truy vấn cao, nhiều lần đọc dữ liệu thừa hoặc sử dụng bộ nhớ tăng dần. Bằng chứng thích hợp gồm **độ trễ theo phân bố**, **thông lượng**, **tài nguyên tiêu thụ** và hồ sơ thực thi (*profiling*) trong một điều kiện có thể lặp lại.

Một phép đo cần nêu rõ:

1. **Đối tượng:** API, đường xử lý, truy vấn hoặc tác vụ nào?
2. **Khối lượng:** Số người dùng/yêu cầu đồng thời, kích thước dữ liệu, tỉ lệ loại yêu cầu.
3. **Môi trường:** Cấu hình phần cứng, JVM, cơ sở dữ liệu, trạng thái cache, phiên bản ứng dụng.
4. **Chỉ số:** Độ trễ p50/p95/p99, thông lượng, CPU, bộ nhớ, số truy vấn; chỉ chọn chỉ số phục vụ mục tiêu.
5. **Phương pháp:** Số lần chạy, thời gian khởi động, cách ghi và so sánh dữ liệu.

Ví dụ giả định: nếu p95 của API tăng trong giờ cao điểm, nhóm có thể đo lại với tải và dữ liệu tương đương, xem trace để xác định đoạn gọi cơ sở dữ liệu chiếm thời gian. **p95** là giá trị mà khoảng 95% quan sát không vượt quá trong mẫu được xét; nó không mô tả trải nghiệm tệ nhất và có thể dao động mạnh nếu mẫu quá nhỏ. Chỉ tối ưu đoạn mã khi dữ liệu cho thấy nó đóng góp đáng kể vào vấn đề.

Phép đo thủ công `System.nanoTime()` quanh một lần gọi có thể hỗ trợ điều tra ban đầu, nhưng không đủ để kết luận một thay đổi Java nhanh hơn: JIT, warm-up, GC và dao động môi trường đều ảnh hưởng kết quả. Với vi mô hiệu năng Java, sử dụng công cụ đo phù hợp như JMH; với trải nghiệm API, đo ở cấp yêu cầu và phụ thuộc thực tế. Không dùng một microbenchmark để suy ra trực tiếp hiệu quả toàn hệ thống.

## 7. Khả năng đọc hiểu: chọn bằng chứng từ quá trình hiểu mã

**Câu hỏi:** Người khác có thể giải thích một quy tắc, tìm đúng nơi sửa và kiểm tra tác động mà không phải suy đoán quá nhiều không?

Tên biến khó hiểu, nhánh điều kiện lồng nhiều tầng, dữ liệu có đơn vị không rõ hoặc các bước nghiệp vụ bị trộn là **dấu hiệu**. Để củng cố nhận định, hãy xem xét một nhiệm vụ cụ thể: “Tìm nơi xác định mức giảm giá tối đa và giải thích hành vi tại ngưỡng.”

So sánh hai cách thể hiện:

```java
// Khó đọc: đơn vị và vai trò của 50000 không thể hiện rõ.
long d = Math.min(amount * 10 / 100, 50000);

// Dễ truy vết ý định hơn (vẫn cần kiểm tra yêu cầu thực tế).
long discountVnd = Math.min(
        subtotalVnd * DISCOUNT_PERCENT / 100,
        MAX_DISCOUNT_VND);
```

Tốt hơn về tên gọi không tự chứng minh tính đúng đắn; ví dụ trên còn giả định cách chia số nguyên là phù hợp. Muốn kiểm tra khả năng đọc hiểu, một reviewer có thể ghi lại những điểm phải hỏi lại, chỗ dễ hiểu sai và thời gian tìm quy tắc trong cùng một nhiệm vụ. Đánh giá này có yếu tố định tính; nên có ví dụ cụ thể thay vì chỉ ghi “code clean hơn”.

Các chỉ số như độ dài phương thức, độ sâu lồng nhau hoặc độ phức tạp chu trình giúp **khoanh vùng nơi nên review**, nhưng không nên chuyển thành mục tiêu duy nhất. Hai phương thức có cùng số nhánh có thể khác xa về mức độ dễ hiểu nếu một phương thức có khái niệm nghiệp vụ rõ ràng hơn.

## 8. Khả năng thay đổi và bảo trì: theo dấu chi phí của một yêu cầu thật

**Câu hỏi:** Khi quy tắc thay đổi, cần sửa bao nhiêu trách nhiệm, bao nhiêu nơi và khó khăn lớn nhất nằm ở đâu?

Dấu hiệu thường gặp: quy tắc trùng lặp, thay đổi lan qua nhiều lớp không liên quan, phụ thuộc hai chiều, logic nghiệp vụ rải rác hoặc lỗi hồi quy lặp lại ở cùng vùng mã. Để đánh giá, chọn **một yêu cầu thay đổi có thật** và xác định hành trình của nó:

```mermaid
flowchart LR
    A[Quy tắc cần thay đổi] --> B[Tìm nơi quyết định quy tắc]
    B --> C[Xác định những nơi bị ảnh hưởng]
    C --> D[Cập nhật mã và kiểm thử]
    D --> E[Review và kiểm chứng]
    E --> F[Ghi lại tác động và rủi ro còn lại]
```

Ví dụ: để đổi ngưỡng miễn phí giao hàng, nếu phải sửa ba điều kiện độc lập ở web, API và xử lý đơn hàng thì **số nơi giữ cùng quy tắc** là bằng chứng về phạm vi thay đổi. Khi đưa quy tắc về một thành phần có trách nhiệm rõ ràng, cần xác minh các luồng phụ thuộc vẫn nhận được hành vi đúng. Đừng tự động gom mọi điều kiện giống nhau về một hàm: có thể chúng chỉ tình cờ cùng giá trị nhưng thuộc các quy tắc khác nhau.

Các phép đo bổ trợ có thể gồm số nơi thay đổi một quy tắc, số lỗi xuất hiện ở cùng khu vực sau các lần sửa, độ rõ của phụ thuộc và review về phạm vi tác động. Chỉ số *lead time* hay thời gian hoàn thành một PR cần đọc trong bối cảnh: thay đổi có độ lớn và độ khó khác nhau nên không thể lấy một con số đơn lẻ làm bằng chứng kiến trúc đã tốt lên.

## 9. Khả năng kiểm thử: kiểm tra tính cô lập và kết quả có thể dự đoán

**Câu hỏi:** Có thể thiết lập đầu vào, kiểm soát phụ thuộc và xác nhận đầu ra một cách ổn định không?

Một phương thức phụ thuộc đồng thời vào thời gian thực, mạng, cơ sở dữ liệu và trạng thái toàn cục thường khó kiểm thử hơn phương thức nhận rõ các phụ thuộc cần thiết. Dấu hiệu có thể là test chỉ chạy trên máy của tác giả, thất bại không ổn định, cần thứ tự chạy cố định hoặc phải khởi động toàn hệ thống cho một quy tắc nhỏ.

Ví dụ về phụ thuộc thời gian:

```java
import java.time.Clock;
import java.time.LocalDate;

public class SubscriptionPolicy {
    private final Clock clock;

    public SubscriptionPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isActive(LocalDate expirationDate) {
        return !LocalDate.now(clock).isAfter(expirationDate);
    }
}
```

Khi truyền `Clock.fixed(...)` trong test, có thể tạo một ngày kiểm tra cố định thay vì phụ thuộc vào ngày hiện tại của máy chạy CI. Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class SubscriptionPolicyTest {
    @Test
    void isActiveOnExpirationDate() {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-16T08:00:00Z"), ZoneOffset.UTC);
        SubscriptionPolicy policy = new SubscriptionPolicy(clock);
        assertTrue(policy.isActive(LocalDate.of(2026, 11, 16)));
    }
}
```

Đây là minh họa cách **tạo khả năng kiểm soát đầu vào**, không phải khuyến nghị thêm abstraction cho mọi phương thức. Bằng chứng cải thiện có thể là kiểm thử chạy được mà không kết nối mạng, kiểm thử biên thời gian ổn định hoặc giảm những thất bại do môi trường. Với hành vi liên quan cơ sở dữ liệu hay giao dịch, vẫn cần kiểm thử tích hợp ở lớp phù hợp; chỉ mock mọi phụ thuộc có thể che đi lỗi tương tác thật.

## 10. Khả năng quan sát: chứng minh có thể tìm được nguyên nhân

**Câu hỏi:** Khi chức năng sai trong môi trường vận hành, nhóm có đủ dữ kiện để xác định yêu cầu nào và bước nào đã thất bại không?

Một triệu dòng log không có mã tương quan có thể ít hữu ích hơn vài bản ghi có `requestId`, tên thao tác, mã lỗi và thời điểm. Có thể chọn một sự cố giả lập, rồi thử truy vết từ phản hồi lỗi đến nguyên nhân ở dịch vụ liên quan.

| Dấu hiệu | Bằng chứng kiểm tra | Hạn chế cần nhớ |
| --- | --- | --- |
| Không ghép được log giữa các dịch vụ | Một request ID xuất hiện nhất quán qua các bước xử lý | Nếu không truyền ngữ cảnh xuyên dịch vụ, dấu vết vẫn đứt |
| Lỗi chỉ hiện thông báo chung | Log/trace chỉ ra loại lỗi và bước thất bại | Cần tránh ghi thông tin cá nhân, token, dữ liệu thanh toán |
| Không biết lỗi tăng từ lúc nào | Chỉ số theo thời gian gắn với phiên bản phát hành | Chỉ số tổng có thể che giấu vấn đề ở nhóm người dùng nhỏ |

Khả năng quan sát tốt giúp kiểm chứng các chiều khác: tính đúng đắn trong sản xuất, hiệu năng thực tế, khả năng phục hồi và nguyên nhân lỗi. Tuy nhiên, log và metric vẫn là các **quan sát gián tiếp**; kết luận phải nối chúng với đường xử lý và hành vi đã xác minh.

## 11. Quy trình chọn phép đo khi thời gian và nguồn lực có hạn

Không cần đo mọi thứ cùng lúc. Để chọn bộ bằng chứng đủ dùng, tiến hành theo các bước:

1. **Nêu tác động cần xử lý.** Ví dụ: “Khách đôi khi nhận hai đơn sau khi thử lại” cụ thể hơn “service kém chất lượng”.
2. **Xác định chiều chính và chiều liên quan.** Trường hợp này ưu tiên độ tin cậy và tính đúng đắn; khả năng quan sát giúp truy nguyên nguyên nhân.
3. **Chọn một dấu hiệu có thể kiểm tra.** Ví dụ: yêu cầu trùng trong khoảng thời gian ngắn, hai giao dịch ghi dữ liệu cho cùng mã thao tác.
4. **Chọn bằng chứng trực tiếp trước, chỉ số gián tiếp sau.** Bắt đầu từ kịch bản tái hiện trùng đơn, rồi dùng thống kê lỗi và log để đánh giá phạm vi.
5. **Đặt baseline và điều kiện so sánh.** Ghi mã phiên bản, dữ liệu, cấu hình, cách kích hoạt kịch bản và kết quả trước sửa.
6. **Sửa trong phạm vi kiểm soát rồi kiểm tra lại.** Giữ kịch bản cũ để đánh giá hồi quy; bổ sung kiểm tra cho trường hợp vừa phát hiện.
7. **Nêu giới hạn và theo dõi tiếp.** Chỉ kết luận trong phạm vi kịch bản, tải và môi trường được kiểm tra; xác định số liệu cần theo dõi sau khi phát hành.

### Lựa chọn bằng chứng theo ba cấp

| Cấp bằng chứng | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| **Quan sát ban đầu** | Cảnh báo tĩnh, phương thức dài, người dùng phản ánh chậm | Xác định nơi cần điều tra |
| **Kiểm chứng trực tiếp** | Test tái hiện lỗi; kiểm tra quyền; benchmark đúng tải; review một đường thay đổi | Xác nhận vấn đề cụ thể và đánh giá sửa đổi |
| **Theo dõi thực tế** | Tỉ lệ lỗi, phân bố thời gian đáp ứng, sự cố sau phát hành, phản hồi bảo trì | Xem tác động có tiếp tục tồn tại theo thời gian không |

Thông thường cần ít nhất một dạng kiểm chứng trực tiếp cho vấn đề đang giải quyết. Các chỉ số vận hành giúp hiểu quy mô, nhưng không thay thế phép kiểm chứng hành vi. Với quyết định có rủi ro cao, nên kết hợp bằng chứng độc lập, chẳng hạn kiểm thử đường lỗi với dữ liệu giám sát thực tế.

## 12. Ví dụ tổng hợp: đánh giá một thay đổi ở chức năng khuyến mãi

**Bối cảnh giả định:** Một nhóm chuẩn bị thêm mã khuyến mãi cho quy trình thanh toán. Mã hiện tại rải logic tính giảm giá ở nhiều nơi, đồng thời API thanh toán đôi khi chậm vào giờ cao điểm. Nhóm không thể kết luận tất cả chiều chất lượng đều kém chỉ từ hai dấu hiệu này.

### 12.1. Lập bảng giả thuyết trước khi sửa

| Chiều | Câu hỏi kiểm chứng | Bằng chứng ưu tiên | Tiêu chí thành công cần thống nhất |
| --- | --- | --- | --- |
| Đúng đắn | Kết hợp mã giảm giá với phí vận chuyển có cho đúng số tiền? | Test các tổ hợp, ngưỡng và trường hợp mã hết hạn | Các kịch bản yêu cầu đều đúng, kể cả biên |
| Dễ thay đổi | Quy tắc giảm giá xuất hiện ở bao nhiêu nơi cần đồng bộ? | Sơ đồ luồng gọi và diff của một thay đổi quy tắc | Có một nơi chịu trách nhiệm quyết định chính sách, không tạo phụ thuộc vòng |
| Dễ kiểm thử | Có thể kiểm tra tính tiền mà không gọi cổng thanh toán? | Test độc lập với phụ thuộc mô phỏng phù hợp | Chạy ổn định, không cần dịch vụ ngoài cho logic thuần |
| Hiệu năng | Độ trễ chủ yếu ở tính tiền hay gọi dịch vụ phụ trợ? | Trace và p95 theo cùng phân bố tải | Không vượt mục tiêu độ trễ đã được nhóm định nghĩa |
| Tin cậy | Khi người dùng gửi lại yêu cầu, có tạo giao dịch trùng? | Kịch bản retry, log tương quan, dữ liệu giao dịch | Cùng yêu cầu được xử lý an toàn theo hợp đồng API |
| An toàn | Mã giảm giá có thể bị áp dụng vượt quyền hoặc lặp trái quy tắc? | Kiểm thử kiểm soát quyền, giới hạn sử dụng, xác thực ở máy chủ | Các trường hợp không được phép bị từ chối |

### 12.2. Mẫu ghi bằng chứng có thể đi kèm pull request

```text
Vấn đề:
  Quy tắc giảm giá đang được kiểm tra ở nhiều đường xử lý;
  yêu cầu thêm loại mã mới có nguy cơ tạo kết quả không nhất quán.

Giả thuyết:
  Gom quyết định về điều kiện áp dụng mã giảm giá vào một thành phần
  sẽ làm rõ nơi sửa và giúp kiểm thử trường hợp biên độc lập hơn.

Baseline cần thu thập:
  - Các trường hợp đầu vào/đầu ra hiện hành và yêu cầu nghiệp vụ.
  - Những nơi quyết định điều kiện giảm giá.
  - Trạng thái kiểm thử trước thay đổi.

Kiểm chứng sau thay đổi:
  - Kết quả test cùng bộ tình huống, bổ sung test mã mới.
  - Diff thể hiện phạm vi trách nhiệm và những nơi gọi liên quan.
  - Review xác nhận không mở rộng hành vi ngoài yêu cầu.

Giới hạn:
  Kiểm thử đơn vị không thay thế kiểm thử giao dịch thanh toán thật;
  đo hiệu năng cần kịch bản tải riêng.
```

Mẫu trên mô tả **việc cần thu thập**, chưa khẳng định đã đo hay sửa thành công. Khi dự án có dữ liệu thực tế, thay mô tả bằng kết quả, phiên bản mã, môi trường và đường dẫn báo cáo có thể truy xuất.

### 12.3. Khi hai chỉ số cho tín hiệu trái chiều

Giả sử sau refactor, phương thức còn ít dòng hơn nhưng bộ kiểm thử phải khởi tạo thêm nhiều phụ thuộc và có test thường xuyên thất bại. Khi ấy, **khả năng đọc hiểu có thể cải thiện ở một khía cạnh**, trong khi **khả năng kiểm thử có thể xấu đi**. Không nên lấy một chỉ số thuận lợi để tuyên bố mọi chiều đều tốt hơn. Hãy xét lại mục tiêu, nhiệm vụ thực tế và chi phí phát sinh.

Tương tự, một thay đổi cache có thể giảm p95 nhưng làm dữ liệu trả về chậm cập nhật, ảnh hưởng tính đúng đắn hoặc độ tin cậy. Các chiều chất lượng có thể đánh đổi nhau, vì vậy tiêu chí chấp nhận phải bao gồm những ràng buộc không được vi phạm.

## 13. Những lỗi thường gặp khi chọn chỉ số

| Lỗi đánh giá | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Lấy số dòng mã làm thước đo chất lượng tổng quát | Có thể ưu tiên mã ngắn nhưng khó hiểu hoặc sai | Ghép với nhiệm vụ bảo trì và kiểm thử hành vi |
| Coi mọi cảnh báo công cụ là lỗi thật | Tốn công sửa sai trọng tâm | Kiểm tra đường đi thực tế, mức ảnh hưởng và khả năng tái hiện |
| Chỉ dùng tỉ lệ coverage | Bỏ sót test thiếu khẳng định hoặc thiếu kịch bản quan trọng | Xem nội dung test, trường hợp biên và các quy tắc cần bảo vệ |
| Đo một lần hoặc so môi trường khác nhau | Dao động bị hiểu nhầm thành cải thiện | Cố định điều kiện, chạy đủ mẫu và ghi sai số |
| Chọn chỉ số chỉ vì dễ lấy | Tối ưu số đo nhưng không giải quyết tác động | Bắt đầu từ câu hỏi chất lượng rồi mới chọn phép đo |
| Không phân biệt lỗi từ mã và hạ tầng | Đưa ra giải pháp sai nguyên nhân | Kết hợp log, trace, test cô lập và quan sát phụ thuộc |
| Gán ngưỡng “tốt/xấu” cho mọi dự án | Bỏ qua tải, rủi ro và hợp đồng dịch vụ khác nhau | Thống nhất ngưỡng theo mục tiêu của hệ thống |
| Tuyên bố quan hệ nhân quả từ hai số liệu đi cùng nhau | Kết luận quá mức bằng chứng | Nêu giả thuyết, kiểm soát yếu tố gây nhiễu và xác nhận trực tiếp |

## 14. Bài tập vận dụng

### Tình huống A — Nhiều cảnh báo độ phức tạp

Một công cụ đánh dấu phương thức `calculateInvoice()` có độ phức tạp cao, nhưng hệ thống chưa ghi nhận lỗi tính tiền. Tháng tới sẽ bổ sung loại thuế mới.

Hãy trả lời: (1) cần quan sát điều gì ngoài độ phức tạp; (2) chiều chất lượng nào cần ưu tiên; (3) bằng chứng nào sẽ cho biết refactor giúp việc thêm thuế an toàn hơn?

**Gợi ý đối chiếu:** Trọng tâm là tính đúng đắn, khả năng hiểu và thay đổi. Cần xác định các quy tắc/đường xử lý, kiểm thử đầu vào và biên theo yêu cầu, phạm vi sửa khi thêm thuế, rồi đối chiếu trước/sau. Chỉ số phức tạp có thể giúp chọn điểm điều tra, không thay cho kiểm chứng nghiệp vụ.

### Tình huống B — API lúc nhanh lúc chậm

Một API có thời gian phản hồi trung bình thấp, nhưng người dùng vẫn thỉnh thoảng phàn nàn chậm.

Hãy chọn ít nhất ba dữ kiện cần thu thập và giải thích vì sao số trung bình chưa đủ.

**Gợi ý đối chiếu:** Thu thập phân bố p95/p99 theo nhóm yêu cầu, tải và thời điểm, trace gọi phụ thuộc, tần suất timeout, dữ liệu và cấu hình chạy. Giá trị trung bình có thể che đi phần đuôi chậm của phân bố. Không khẳng định có lỗi ở mã Java nếu chưa biết thời gian bị dùng ở bước nào.

### Tình huống C — CI xanh nhưng sự cố vẫn xuất hiện

Sau mỗi lần phát hành, CI đều xanh nhưng có lỗi khi nhiều người cùng đặt hàng.

Hãy xác định chiều chất lượng liên quan và thiết kế một kiểm chứng có ích hơn việc tăng coverage bằng các test đơn giản.

**Gợi ý đối chiếu:** Cần xem xét tính đúng đắn dưới cạnh tranh và độ tin cậy. Có thể dùng kiểm thử đồng thời, kịch bản gửi lại yêu cầu và kiểm tra các bất biến của dữ liệu (ví dụ không tạo đơn trùng, số lượng tồn kho không âm), kết hợp quan sát lỗi trong vận hành. Mục tiêu là tái hiện tình huống thật còn thiếu trong bộ test.

## 15. Bảng kiểm nhanh trước khi kết luận chất lượng

- [ ] Tôi đã chỉ rõ chiều chất lượng cần đánh giá và tác động liên quan.
- [ ] Tôi phân biệt được dấu hiệu ban đầu với bằng chứng kiểm chứng.
- [ ] Tôi biết nguồn yêu cầu hoặc tiêu chí nào xác định kết quả đúng/tốt.
- [ ] Tôi đã ghi điều kiện đo, dữ liệu, phiên bản và phương pháp thu thập.
- [ ] Tôi có baseline thích hợp nếu mục tiêu là chứng minh sự cải thiện.
- [ ] Tôi đã xem xét những chiều chất lượng có thể bị ảnh hưởng ngược.
- [ ] Tôi không suy diễn vượt phạm vi của test, chỉ số hoặc kết quả review.
- [ ] Tôi có thể giải thích kết luận bằng một ví dụ hoặc kết quả mà người khác kiểm tra lại được.

**Điểm cần nhớ:** Dấu hiệu giúp **chọn nơi cần điều tra**; bằng chứng giúp **xác nhận hoặc bác bỏ một nhận định cụ thể**. Chọn đúng bằng chứng cho từng chiều chất lượng sẽ giúp nhóm cải thiện mã có cơ sở, đồng thời tránh tối ưu các con số dễ đo nhưng ít liên quan đến tính đáng tin cậy, khả năng đọc hiểu và khả năng thay đổi của phần mềm.
