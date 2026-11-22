# Vai trò của thiết kế, kiểm thử, công cụ và rà soát trong chất lượng mã nguồn

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao chất lượng mã nguồn cần được xây dựng từ khi thiết kế và được kiểm chứng liên tục trong quá trình phát triển.
2. Phân biệt vai trò của **thiết kế**, **kiểm thử**, **công cụ tự động** và **rà soát mã nguồn (code review)**.
3. Chọn kỹ thuật phù hợp cho từng loại rủi ro: sai nghiệp vụ, phụ thuộc khó thay đổi, lỗi tích hợp, lỗ hổng bảo mật hoặc thay đổi gây hồi quy.
4. Áp dụng bốn hoạt động này vào một thay đổi Java nhỏ và xác định tín hiệu cho thấy quy trình đang hiệu quả.

Trong học phần **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã nguồn được nhìn nhận qua khả năng chương trình **hoạt động đúng, dễ hiểu, dễ sửa, có thể kiểm chứng và đủ an toàn, tin cậy** cho bối cảnh sử dụng. Mã biên dịch thành công hoặc chạy qua một trường hợp mẫu chưa đủ để khẳng định những thuộc tính này.

## 1. Bốn hoạt động giải quyết bốn nhóm câu hỏi khác nhau

Giả sử nhóm phát triển cần thêm quy tắc miễn phí vận chuyển cho đơn hàng đủ điều kiện. Thay đổi có vẻ nhỏ, nhưng có nhiều câu hỏi: điều kiện miễn phí có được xác định tại một nơi không; đơn hàng ngay dưới ngưỡng sẽ thế nào; có ảnh hưởng đến mã khuyến mại hiện tại không; có ai nhận ra trường hợp ngoại lệ bị bỏ sót không?

| Hoạt động | Câu hỏi chính | Đóng góp cho chất lượng | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Thiết kế (design)** | Nên tổ chức trách nhiệm, dữ liệu và quan hệ phụ thuộc thế nào? | Giảm độ phức tạp, cô lập thay đổi, làm rõ quy tắc và điểm mở rộng | Một thiết kế hợp lý vẫn có thể được triển khai sai |
| **Kiểm thử (testing)** | Hệ thống có tạo ra hành vi mong đợi ở những tình huống đã chọn không? | Phát hiện sai lệch, bảo vệ hành vi khi sửa mã, cung cấp bằng chứng có thể chạy lại | Không bao phủ mọi đầu vào và không chứng minh tuyệt đối rằng không có lỗi |
| **Công cụ (tooling)** | Những quy tắc và tín hiệu nào có thể kiểm tra nhất quán, nhanh và lặp lại? | Phát hiện sớm lỗi cơ học, cảnh báo rủi ro, chuẩn hóa phản hồi trong CI | Có thể bỏ sót lỗi ngữ nghĩa hoặc tạo cảnh báo không phù hợp |
| **Rà soát (review)** | Thay đổi đã đúng ý định, phù hợp ngữ cảnh và dễ bảo trì chưa? | Bổ sung góc nhìn con người về nghiệp vụ, thiết kế, an toàn và tính dễ đọc | Phụ thuộc vào chất lượng ngữ cảnh và sự tập trung của người rà soát |

Các hoạt động **bổ trợ**, không thay thế lẫn nhau. Thiết kế làm hệ thống dễ kiểm thử; kiểm thử tạo phản hồi về thiết kế và hiện thực; công cụ giúp kiểm tra thường xuyên; rà soát đánh giá những điều mà kiểm tra tự động khó diễn đạt thành quy tắc.

### Chất lượng là nhiều thuộc tính, không chỉ một con số

- **Tính đúng đắn:** kết quả đúng quy tắc nghiệp vụ, bao gồm điều kiện biên và lỗi đầu vào.
- **Khả năng bảo trì:** người khác có thể đọc, xác định nơi sửa và thay đổi mà ít gây hiệu ứng dây chuyền.
- **Độ tin cậy:** xử lý hợp lý các lỗi, trạng thái bất thường và tương tác với hệ thống khác.
- **Bảo mật:** kiểm soát dữ liệu đầu vào, quyền truy cập và thông tin nhạy cảm.
- **Hiệu năng:** đáp ứng nhu cầu thực tế với chi phí tài nguyên chấp nhận được.

Không có kỹ thuật đơn lẻ nào tối ưu tất cả thuộc tính. Ví dụ, trừu tượng hóa thêm nhiều tầng có thể tăng tính thay thế nhưng cũng làm một luồng đơn giản khó theo dõi hơn. Quyết định chất lượng phải dựa trên rủi ro và nhu cầu cụ thể.

## 2. Thiết kế: phòng ngừa sự phức tạp trước khi nó lan rộng

Thiết kế là cách phân chia trách nhiệm, định nghĩa ranh giới, dữ liệu và hợp đồng giữa các phần của chương trình. Mục tiêu không phải tạo nhiều lớp hay áp dụng càng nhiều mẫu thiết kế càng tốt, mà là làm cho ý định rõ và thay đổi có phạm vi dự đoán được.

### Những nguyên tắc thiết kế thực dụng

**Trách nhiệm rõ ràng và tính gắn kết cao.** Một thành phần nên có lý do thay đổi tương đối tập trung. Mã tính tiền không cần đồng thời mở kết nối cơ sở dữ liệu, gửi email và định dạng HTML. Khi các trách nhiệm bị trộn lẫn, việc kiểm tra một quy tắc nhỏ kéo theo nhiều cấu hình và tác dụng phụ.

**Giảm liên kết không cần thiết.** Đặt phụ thuộc ở ranh giới thích hợp. Ví dụ, logic quyết định phí vận chuyển có thể nhận dữ liệu đơn hàng và chính sách giá, trong khi tầng ứng dụng chịu trách nhiệm truy xuất cơ sở dữ liệu. Nhờ vậy, thay đổi cơ sở dữ liệu ít ảnh hưởng đến quy tắc tính phí.

**Hợp đồng và bất biến rõ ràng.** Xác định đầu vào hợp lệ, đầu ra mong đợi và hành vi khi dữ liệu sai. Các câu hỏi như “số lượng có được bằng 0 không?” hay “giá có thể âm không?” cần được trả lời ở vị trí gần dữ liệu liên quan.

**Đơn giản theo nhu cầu hiện tại.** Đặt tên diễn đạt ý định; tránh nhân bản quy tắc nghiệp vụ; chỉ tạo lớp giao diện hoặc cơ chế mở rộng khi có lợi ích cụ thể. Tách các phép tính thuần khỏi thao tác I/O thường mang lại giá trị rõ ràng hơn việc thêm một tầng trừu tượng chưa cần thiết.

### Ví dụ Java: giữ quy tắc tính tiền dễ hiểu và dễ kiểm thử

Xét thành phần tính thành tiền trước thuế, khuyến mại và phí vận chuyển. Ta muốn từ chối dòng hàng không hợp lệ và không để phép tính phụ thuộc vào cơ sở dữ liệu hoặc thời gian hiện tại.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public final class OrderCalculator {

    public record Line(String productId, int quantity, BigDecimal unitPrice) {
        public Line {
            Objects.requireNonNull(productId, "productId");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (productId.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }

        public BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public BigDecimal subtotal(List<Line> lines) {
        Objects.requireNonNull(lines, "lines");

        return lines.stream()
                .map(Line::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

Ở đây, kiểu **Line** bảo vệ các bất biến: mã sản phẩm không rỗng, số lượng dương, đơn giá không âm. **OrderCalculator** chỉ cộng các dòng hợp lệ. Dùng **BigDecimal** tránh sai số biểu diễn nhị phân của **double** trong nhiều phép tính thập phân; quy tắc làm tròn và tỷ lệ chữ số thập phân cần được định nghĩa riêng khi nghiệp vụ yêu cầu.

Ví dụ sử dụng Java 17 trở lên (do có **record**). Một hệ thống thực tế còn phải quyết định giá trị trả về khi đơn hàng rỗng, đơn vị tiền tệ và vị trí áp dụng thuế/chiết khấu. Những quyết định đó là một phần của hợp đồng, không nên bị ẩn trong cách viết code.

### Dấu hiệu thiết kế đang gây khó khăn

| Dấu hiệu | Hệ quả thường gặp | Hướng cải thiện |
| --- | --- | --- |
| Một phương thức vừa tính toán vừa ghi dữ liệu và gọi API | Kiểm thử chậm, khó cô lập nguyên nhân lỗi | Tách tính toán thuần và các thao tác bên ngoài |
| Một quy tắc bị sao chép vào nhiều nơi | Sửa sót một nhánh dẫn đến hành vi không nhất quán | Xác định nơi sở hữu quy tắc và tái sử dụng qua giao diện rõ ràng |
| Nhiều cờ boolean điều khiển các nhánh khó theo dõi | Số tổ hợp tăng, khó hiểu trạng thái | Đặt tên trạng thái hoặc tách trường hợp theo ý nghĩa nghiệp vụ |
| Trừu tượng hóa sâu cho một tình huống duy nhất | Người đọc phải đi qua nhiều lớp để hiểu luồng | Đơn giản hóa cấu trúc khi chưa có nhu cầu mở rộng cụ thể |

## 3. Kiểm thử: cung cấp bằng chứng về hành vi

Kiểm thử trả lời câu hỏi “với điều kiện này, kết quả có phù hợp hợp đồng không?”. Một bài kiểm thử tốt mô tả hành vi quan sát được và thất bại khi hành vi đó bị phá vỡ. Kiểm thử chỉ xác nhận các tình huống nó bao phủ; vì thế việc chọn tình huống theo rủi ro quan trọng hơn đếm số lượng test.

### Những mức kiểm thử thường gặp

| Mức kiểm thử | Phạm vi | Ví dụ với hệ thống đặt hàng |
| --- | --- | --- |
| **Unit test** | Một đơn vị logic nhỏ, phụ thuộc được cô lập | Tính tổng của các dòng hàng, từ chối số lượng bằng 0 |
| **Integration test** | Sự phối hợp của các thành phần thực | Ghi và đọc đơn hàng qua repository với cơ sở dữ liệu kiểm thử |
| **Contract test** | Cam kết giao tiếp giữa bên cung cấp và bên sử dụng | API trả đúng cấu trúc, mã lỗi và trường bắt buộc |
| **End-to-end test** | Luồng nghiệp vụ xuyên qua nhiều phần hệ thống | Khách đặt hàng, thanh toán thử nghiệm và nhận xác nhận |

Unit test thường nhanh và cho biết vị trí lỗi tương đối rõ. Integration test phát hiện sai sót ở cấu hình, truy vấn, ánh xạ dữ liệu và giao tiếp. End-to-end test xác minh hành trình quan trọng nhưng có thể chậm và dễ chịu ảnh hưởng từ môi trường. Tỷ lệ giữa các mức nên dựa vào kiến trúc và rủi ro của sản phẩm, không phải một công thức cố định.

### Viết test theo hành vi, điều kiện biên và lỗi đầu vào

Ví dụ dùng JUnit Jupiter (JUnit 5) để kiểm tra thành phần vừa thiết kế:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderCalculatorTest {
    private final OrderCalculator calculator = new OrderCalculator();

    @Test
    void sumsValidLines() {
        var lines = List.of(
                new OrderCalculator.Line("A", 2, new BigDecimal("40.00")),
                new OrderCalculator.Line("B", 1, new BigDecimal("70.00")));

        assertEquals(new BigDecimal("150.00"), calculator.subtotal(lines));
    }

    @Test
    void emptyOrderHasZeroSubtotal() {
        assertEquals(BigDecimal.ZERO, calculator.subtotal(List.of()));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderCalculator.Line("A", 0, new BigDecimal("40.00")));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderCalculator.Line("A", 1, new BigDecimal("-1.00")));
    }
}
~~~

Nhóm test này kiểm tra trường hợp thông thường, tập rỗng và hai điều kiện không hợp lệ. Các rủi ro tiếp theo có thể là đầu vào **null**, tràn tài nguyên khi danh sách quá lớn, quy tắc làm tròn hoặc tính chiết khấu tại ngưỡng. Chỉ viết thêm test khi đã xác định rõ hợp đồng tương ứng; không biến hành vi tình cờ của chương trình thành yêu cầu nghiệp vụ.

Một cách tổ chức đơn giản là **Arrange – Act – Assert**: chuẩn bị dữ liệu, thực hiện hành vi, xác nhận kết quả. Tên test nên nói được ý nghĩa khi thất bại. Ví dụ “rejectsZeroQuantity” giúp người sửa mã hiểu ngay quy tắc nào bị phá.

### Coverage không đồng nghĩa chất lượng kiểm thử

Độ bao phủ dòng hoặc nhánh cho biết phần mã nào đã được thực thi, nhưng không nói rằng kết quả được kiểm tra đúng. Một test chạy qua một phương thức mà không có khẳng định phù hợp có thể tăng coverage nhưng không phát hiện lỗi. Hãy xem coverage như **tín hiệu về khoảng trống**, kết hợp với chất lượng assertion, trường hợp biên, tác dụng phụ và rủi ro nghiệp vụ.

Trong trường hợp lỗi xảy ra ngoài môi trường thật, quy trình hữu ích là: tái hiện lỗi bằng test thất bại, sửa nguyên nhân, sau đó giữ test đó để ngăn hồi quy. Tránh sửa test chỉ để hợp thức hóa kết quả sai.

## 4. Công cụ: phản hồi nhanh, nhất quán và có thể lặp lại

Một nhóm không nên phụ thuộc vào việc người rà soát nhớ từng quy tắc định dạng, lỗi cú pháp, phụ thuộc dễ bị khai thác hay cảnh báo tĩnh. Công cụ tự động hóa các kiểm tra có thể diễn đạt thành quy tắc và chạy lặp lại trên máy lập trình viên cũng như trong CI (continuous integration).

### Nhóm công cụ và mục đích

| Nhóm | Ví dụ trong hệ sinh thái Java | Phát hiện hoặc hỗ trợ |
| --- | --- | --- |
| Formatter | Spotless, google-java-format | Bố cục mã thống nhất, giảm tranh luận về định dạng |
| Quy tắc mã nguồn | Checkstyle, PMD | Quy ước đặt tên, cấu trúc và các mẫu mã cần chú ý |
| Phân tích tĩnh | SpotBugs, Error Prone | Một số mẫu lỗi tiềm ẩn mà không cần chạy chương trình |
| Kiểm thử và đo lường | JUnit, JaCoCo | Chạy kiểm thử tự động, báo cáo độ bao phủ |
| Phân tích phụ thuộc và bảo mật | OWASP Dependency-Check, công cụ quét bí mật | Cảnh báo thư viện có vấn đề đã được công bố hoặc nguy cơ lộ thông tin |
| Tích hợp liên tục | Jenkins, GitHub Actions, GitLab CI | Chạy các bước kiểm tra khi có thay đổi và công bố kết quả |

Danh sách là ví dụ về loại công cụ, không có nghĩa dự án phải dùng tất cả. Mỗi công cụ có phạm vi phát hiện, cấu hình, tốc độ và khả năng cảnh báo sai khác nhau. Một cảnh báo cần được kiểm tra ngữ cảnh; không phải mọi cảnh báo đều tương đương lỗi thực tế.

### Ví dụ luồng phản hồi cho một pull request

~~~mermaid
flowchart TD
    A[Thay đổi mã và test] --> B[Formatter và quy tắc mã]
    B --> C[Build và unit test]
    C --> D[Phân tích tĩnh và kiểm tra phụ thuộc]
    D --> E[Integration test phù hợp]
    E --> F[Rà soát mã nguồn]
    F --> G[Merge khi đáp ứng tiêu chí]
    B --> H[Phản hồi sửa lỗi]
    C --> H
    D --> H
    E --> H
    F --> H
    H --> A
~~~

Luồng trên minh họa các cổng kiểm tra; trong thực tế, nhiều job độc lập có thể chạy song song để giảm thời gian chờ. Nên chạy kiểm tra nhanh trước hoặc đồng thời với kiểm tra đắt hơn, và đảm bảo thất bại thực sự chặn bước cần bảo vệ. Với lỗi chỉ xuất hiện ở tích hợp thực, test đơn vị dù chạy xanh cũng không đủ.

### Cách sử dụng công cụ có trách nhiệm

1. **Đặt quy tắc rõ ràng:** mọi thành viên biết điều gì là lỗi chặn merge, điều gì chỉ là cảnh báo cần xem xét.
2. **Giữ kết quả có thể tái hiện:** khóa hoặc kiểm soát phiên bản công cụ, phụ thuộc và cấu hình; hạn chế tình trạng máy này xanh, máy khác đỏ.
3. **Xử lý cảnh báo theo rủi ro:** ưu tiên lỗi có bằng chứng, có tác động lớn hoặc dễ khai thác; ghi rõ lý do nếu chấp nhận ngoại lệ.
4. **Theo dõi thời gian phản hồi:** một pipeline quá chậm khiến phản hồi đến muộn và tăng chi phí sửa lỗi.
5. **Không chạy công cụ để tạo điểm số:** sửa nguyên nhân gây vấn đề; không xóa assertion, tắt kiểm tra quan trọng hoặc tăng ngưỡng tùy tiện chỉ để CI xanh.

Ví dụ, formatter giúp loại bỏ thay đổi khoảng trắng gây nhiễu trong pull request. Khi phần cơ học đã được tự động hóa, người rà soát có thêm thời gian tập trung vào tính đúng đắn và lựa chọn thiết kế.

## 5. Rà soát mã nguồn: đánh giá ngữ cảnh mà máy khó hiểu

Code review là hoạt động một hoặc nhiều người khác đọc thay đổi, hỏi về ý định và kiểm tra tác động. Một review tốt không chỉ tìm “đoạn code xấu”, mà xác nhận **vấn đề được giải đúng**, các ngoại lệ được xử lý và người bảo trì sau này có thể hiểu quyết định.

### Người tạo thay đổi nên cung cấp gì?

Một pull request dễ rà soát thường nêu rõ: vấn đề hoặc yêu cầu, hành vi trước/sau, phạm vi thay đổi, cách kiểm chứng, những quyết định thiết kế quan trọng và rủi ro còn lại. Nếu thay đổi ảnh hưởng dữ liệu, API hoặc cấu hình triển khai, hãy diễn giải tác động để người khác không phải suy đoán từ từng dòng mã.

Ví dụ mô tả thay đổi ngắn:

> **Yêu cầu:** Dòng đơn hàng phải có số lượng dương. **Trước:** dữ liệu số lượng bằng 0 có thể đi qua hàm tính tổng. **Sau:** tạo dòng hàng không hợp lệ phát sinh IllegalArgumentException. **Kiểm chứng:** bổ sung unit test cho số lượng bằng 0, tổng nhiều dòng và đơn hàng rỗng.

### Người rà soát nên hỏi gì?

- **Nghiệp vụ:** kết quả có phù hợp yêu cầu và các trường hợp biên không? Quy tắc có đang bị định nghĩa ở nhiều nơi?
- **Thiết kế:** thay đổi có đặt đúng trách nhiệm không? Có ràng buộc thêm thành phần khác một cách không cần thiết không?
- **An toàn:** đầu vào, phân quyền, dữ liệu nhạy cảm, lỗi và thông điệp trả về có được xử lý hợp lý không?
- **Kiểm thử:** test có thể thất bại trước một lỗi thật không? Có thiếu trường hợp tích hợp hoặc hồi quy quan trọng?
- **Vận hành:** khi lỗi xảy ra có cách phát hiện, truy vết và khôi phục phù hợp không? Thay đổi có tương thích với dữ liệu cũ không?
- **Khả năng hiểu:** tên gọi, cách phân tách và tài liệu có giúp người đọc kế tiếp hiểu ý định không?

Phản hồi nên cụ thể và có lý do, ví dụ: “Trường hợp số lượng bằng 0 cần bị từ chối theo hợp đồng của Line; thêm một test cho đầu vào này nhé”, thay vì “Code chưa sạch”. Tách lỗi bắt buộc sửa khỏi gợi ý về phong cách. Tác giả cũng cần phản hồi bằng lý do kỹ thuật khi có đánh đổi hợp lệ. Review là trao đổi hai chiều và là cơ hội chia sẻ hiểu biết về hệ thống.

### Review không phải lớp bảo vệ duy nhất

Khi pull request rất lớn, trộn refactor với đổi hành vi hoặc thiếu cách chạy lại kết quả, người rà soát khó đánh giá. Hãy chia thay đổi thành phần có ý nghĩa, dùng kiểm tra tự động để giảm nhiễu và nhấn mạnh vùng rủi ro cao. Một lượt phê duyệt không thay thế cho kiểm thử tích hợp hoặc đo lường hệ thống sau triển khai.

## 6. Kết hợp bốn hoạt động trong một thay đổi thực tế

Giả sử cần bổ sung quy tắc: **đơn hàng có tạm tính từ 500.000 đồng được miễn phí vận chuyển**, còn đơn hàng thấp hơn trả 30.000 đồng. Đây là ví dụ giả định để thực hành; quy định thực tế cần do nghiệp vụ xác nhận.

**Bước 1 — Làm rõ hợp đồng.** “Tạm tính” là trước hay sau khuyến mại? Đơn hàng bằng đúng ngưỡng có được miễn phí không? Trường hợp rỗng, tiền tệ khác hoặc đơn hàng bị hủy xử lý thế nào? Đây là câu hỏi cần làm rõ trước khi code.

**Bước 2 — Thiết kế trách nhiệm.** Đặt phép tính phí vào một thành phần riêng nhận tạm tính và chính sách phí, tránh cho nó trực tiếp gọi cơ sở dữ liệu hay API vận chuyển. Giữ quy tắc điều kiện tại một nơi để màn hình và API không tự tính theo hai cách.

**Bước 3 — Chọn test theo ranh giới.** Ít nhất kiểm tra tạm tính **499.999**, **500.000**, **500.001** đồng; xác nhận dữ liệu không hợp lệ được xử lý theo hợp đồng; thêm integration test khi thay đổi cả phần kết nối đơn hàng và vận chuyển.

**Bước 4 — Chạy kiểm tra tự động.** Formatter và build bảo đảm tính nhất quán cơ bản; unit test kiểm tra quy tắc; phân tích tĩnh và quét phụ thuộc phản hồi thêm rủi ro; kiểm tra tích hợp xác nhận hệ thống kết nối được.

**Bước 5 — Rà soát thay đổi.** Người review xác nhận ngưỡng, thời điểm áp dụng khuyến mại, vị trí sở hữu quy tắc và tính đủ của test. Nếu phát hiện “tạm tính” đang được hiểu khác nhau giữa các nhóm, phải quay lại làm rõ hợp đồng.

**Bước 6 — Theo dõi sau tích hợp.** Quan sát tỷ lệ lỗi và tình huống tính phí bất thường; giữ test hồi quy khi đã sửa một lỗi. Phản hồi từ vận hành có thể dẫn tới điều chỉnh thiết kế và bộ test.

Điểm quan trọng là các bước tạo thành **vòng phản hồi**. Một bài test khó viết có thể cho thấy thiết kế gắn chặt vào I/O; cảnh báo lặp lại có thể gợi ý một quy tắc kiến trúc; nhận xét từ review có thể làm lộ trường hợp nghiệp vụ chưa rõ. Khi xuất hiện thông tin mới, quay lại bước cần thiết thay vì coi quy trình là dây chuyền một chiều.

## 7. Lựa chọn mức đầu tư theo rủi ro

Không phải thay đổi nào cũng cần cùng mức kiểm chứng. Sửa câu chữ trong tài liệu và đổi thuật toán tính tiền có tác động rất khác nhau. Có thể cân nhắc:

| Tình huống | Ưu tiên hợp lý |
| --- | --- |
| Đổi tên biến nội bộ, không đổi hành vi | Formatter, build/test liên quan, review nhanh để xác nhận tính rõ ràng |
| Thay quy tắc giá, thuế hoặc quyền truy cập | Làm rõ hợp đồng, test biên và nhánh lỗi, review chuyên sâu về nghiệp vụ/an toàn |
| Đổi truy vấn hoặc ánh xạ cơ sở dữ liệu | Integration test với môi trường đại diện, xem xét tương thích dữ liệu và hiệu năng |
| Thêm phụ thuộc hoặc cập nhật phiên bản thư viện | Quét lỗ hổng/phụ thuộc, kiểm thử tương thích, kiểm tra giấy phép theo quy định dự án |
| Thay đổi giao tiếp giữa các dịch vụ | Contract/integration test, xử lý timeout và lỗi, review cách triển khai/khôi phục |

Một chỉ số đơn lẻ như coverage cao, không có cảnh báo tĩnh hoặc số người phê duyệt nhiều không phản ánh toàn bộ chất lượng. Nên kết hợp tín hiệu **trước tích hợp** (test thất bại, thời gian phản hồi, lỗi review có giá trị) với tín hiệu **sau triển khai** (lỗi lọt ra ngoài, tỷ lệ thay đổi gây sự cố, thời gian phục hồi) và đọc chúng theo bối cảnh. Tránh thưởng phạt dựa trên một điểm số khiến nhóm tối ưu chỉ số thay vì cải thiện sản phẩm.

## 8. Bài tập tự luyện

Một đồng nghiệp đề xuất viết hàm như sau để tính phí vận chuyển:

~~~java
double shippingFee(double subtotal) {
    if (subtotal > 500000) {
        return 0;
    }
    return 30000;
}
~~~

Hãy tự trả lời:

1. **Thiết kế:** Điều kiện và kiểu dữ liệu nào cần thay đổi nếu yêu cầu là “từ 500.000 đồng”? Nên xử lý đầu vào âm ở đâu? Có nên đưa ngưỡng và phí vào cấu hình/chính sách nếu chúng thường thay đổi?
2. **Kiểm thử:** Đề xuất ít nhất bốn trường hợp, trong đó có các giá trị ngay dưới, bằng và trên ngưỡng. Nêu kết quả mong đợi.
3. **Công cụ:** Công cụ nào sẽ giúp phát hiện lỗi cú pháp/kiểu dữ liệu? Công cụ nào có thể chạy tự động các test vừa viết? Công cụ phân tích tĩnh có chắc chắn nhận ra sai quy tắc “từ” với “lớn hơn” không?
4. **Rà soát:** Bạn sẽ viết một bình luận cụ thể thế nào để người tạo thay đổi hiểu lỗi nghiệp vụ và cách xác nhận bản sửa?

**Gợi ý tự kiểm tra:** Trong ví dụ giả định ở mục 6, giá trị bằng đúng 500.000 đồng phải được miễn phí. Vì vậy, điều kiện **>** hiện tại có lỗi ranh giới. Công cụ không hiểu yêu cầu nghiệp vụ sẽ khó phát hiện lỗi này nếu không có test hoặc quy tắc phù hợp. Khi sử dụng số tiền trong Java, nên xem xét **BigDecimal** và quy định rõ đơn vị cùng chính sách làm tròn.

## Ghi nhớ

**Thiết kế** giảm nguy cơ tạo ra hệ thống khó thay đổi; **kiểm thử** cung cấp bằng chứng có thể lặp lại về hành vi; **công cụ** giữ phản hồi nhanh và nhất quán; **rà soát** bổ sung đánh giá ngữ cảnh và chia sẻ hiểu biết. Chất lượng mã nguồn tốt xuất hiện khi bốn hoạt động liên kết thành một quá trình học hỏi và sửa sai liên tục, phù hợp với rủi ro thực tế của hệ thống.
