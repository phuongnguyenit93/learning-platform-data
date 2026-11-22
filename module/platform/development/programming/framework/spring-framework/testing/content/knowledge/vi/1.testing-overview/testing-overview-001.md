# Kiểm thử là gì và bằng chứng mà một bài kiểm thử cung cấp

Trong Spring Framework, kiểm thử là cách kiểm tra một thành phần hoặc một nhóm thành phần có thực hiện đúng hành vi đã được mong đợi hay không. Một bài kiểm thử tốt biến một yêu cầu thành một tình huống có thể chạy lại: chuẩn bị dữ liệu, thực hiện một hành động, quan sát kết quả và đối chiếu kết quả đó với điều kiện mong đợi.

Kết quả kiểm thử cung cấp bằng chứng về hành vi trong tình huống đã chạy. Nó giúp nhóm phát hiện lỗi, xác nhận một quy tắc nghiệp vụ và nhận biết khi một thay đổi làm hỏng hành vi cũ. Tuy nhiên, một lần chạy thành công không chứng minh toàn bộ ứng dụng không còn lỗi. Muốn hiểu đúng giá trị của kiểm thử, cần biết bài kiểm thử đã kiểm tra điều gì, trong điều kiện nào và còn bỏ ngỏ điều gì.

## 1. Vì sao phần mềm cần được kiểm thử?

Mã nguồn thể hiện cách lập trình viên dự định giải quyết một vấn đề. Người sử dụng lại quan tâm đến kết quả quan sát được: một yêu cầu HTTP trả về trạng thái nào, một đơn hàng được tính tổng ra sao, dữ liệu được lưu thế nào, hoặc một trường hợp không hợp lệ bị từ chối ra sao.

Giữa ý định trong mã nguồn và hành vi thực tế có thể xuất hiện sai lệch. Sai lệch có thể đến từ:

- Logic xử lý không đúng quy tắc nghiệp vụ.
- Điều kiện biên bị bỏ sót, chẳng hạn số lượng bằng 0 hoặc dữ liệu rỗng.
- Các thành phần phối hợp sai, ví dụ controller truyền nhầm dữ liệu cho service.
- Cấu hình hoặc cơ chế tích hợp không hoạt động như dự kiến.
- Một thay đổi mới vô tình làm hỏng hành vi đã hoạt động trước đó.

Đọc mã nguồn và kiểm tra thủ công có ích, nhưng chúng không thay thế được những tình huống kiểm tra có thể lặp lại. Khi một bài kiểm thử được tự động hóa, nhóm có thể chạy lại nó sau mỗi thay đổi và nhận được tín hiệu nhanh về những hành vi đã bị ảnh hưởng.

## 2. Kiểm thử là một phép thử có điều kiện

Có thể hiểu một bài kiểm thử như một phép thử có thể lặp lại. Người viết bài kiểm thử xác định trước điều kiện ban đầu, hành động cần thực hiện và kết quả được xem là đúng.

Một tình huống kiểm thử thường có bốn phần:

| Phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Bối cảnh | Trạng thái hoặc dữ liệu ban đầu | Đơn hàng có 3 sản phẩm |
| Đầu vào | Dữ liệu được đưa vào thành phần | Đơn giá là 12.50 |
| Hành động | Hoạt động cần kiểm tra | Tính tổng tiền |
| Kỳ vọng | Kết quả phải quan sát được | Tổng tiền là 37.50 |

Khi chạy bài kiểm thử, chương trình thực hiện hành động với dữ liệu đã chuẩn bị. Các câu lệnh kiểm tra, thường gọi là *assertion*, so sánh kết quả thực tế với kết quả mong đợi.

Có thể mô tả luồng này như sau:

```text
Yêu cầu hoặc quy tắc
        |
        v
Điều kiện ban đầu + dữ liệu đầu vào
        |
        v
Thực hiện hành động cần kiểm tra
        |
        v
Quan sát kết quả thực tế
        |
        v
So sánh với kết quả mong đợi
        |
        +---- Khớp ------> PASS
        |
        +---- Không khớp -> FAIL
```

Điểm quan trọng là kỳ vọng phải xuất phát từ yêu cầu hoặc quy tắc cần bảo vệ. Nếu người viết chỉ sao chép hành vi hiện tại của mã nguồn thành kết quả mong đợi, bài kiểm thử có thể xác nhận một lỗi đang tồn tại thay vì phát hiện nó.

## 3. Một bài kiểm thử cung cấp loại bằng chứng nào?

Bằng chứng của kiểm thử là thông tin thu được khi một tình huống cụ thể được thực thi. Bằng chứng có thể bao gồm:

- Kết quả trả về của phương thức.
- Giá trị hoặc trạng thái của đối tượng sau khi xử lý.
- HTTP status, header và response body của một yêu cầu.
- Dữ liệu thực sự được ghi hoặc đọc từ nơi lưu trữ.
- Ngoại lệ được ném ra khi đầu vào không hợp lệ.
- Tương tác với một thành phần phụ thuộc, nếu bài kiểm thử có chủ đích kiểm tra tương tác đó.
- Trạng thái PASS/FAIL cùng thông tin lỗi giúp xác định assertion nào không đạt.

Ví dụ, nếu một bài kiểm thử gửi yêu cầu với số lượng bằng 3 và xác nhận tổng tiền bằng 37.50, bằng chứng thu được là: với dữ liệu và điều kiện đã thiết lập, đường xử lý được gọi đã tạo ra kết quả 37.50.

Bằng chứng đó có giá trị vì nó gắn với một hành vi quan sát được. Nó cụ thể hơn nhận định chung như “hàm này có vẻ đúng”. Nhưng phạm vi của bằng chứng cũng bị giới hạn bởi dữ liệu, cấu hình và phần hệ thống thực sự tham gia vào bài kiểm thử.

### PASS và FAIL nói lên điều gì?

**PASS** có nghĩa là các điều kiện kiểm tra trong lần chạy đó đều đạt. Nó cho thấy hành vi được quan sát phù hợp với kỳ vọng đã viết trong bài kiểm thử.

**FAIL** có nghĩa là ít nhất một điều kiện kiểm tra không đạt, hoặc bài kiểm thử không thể hoàn thành như dự kiến. Đây là tín hiệu cần điều tra. Nguyên nhân có thể là:

- Mã nguồn có lỗi.
- Kỳ vọng trong bài kiểm thử không đúng với yêu cầu.
- Dữ liệu chuẩn bị hoặc cấu hình kiểm thử sai.
- Thành phần phụ thuộc không sẵn sàng.
- Bài kiểm thử phụ thuộc vào thời gian, thứ tự chạy hoặc trạng thái dùng chung.

Vì vậy, FAIL không tự động chứng minh mã nguồn sai; nó cho biết phép thử chưa đạt điều kiện đã đặt ra. Người đọc cần xem thông báo lỗi, dữ liệu đầu vào và phần assertion để tìm nguyên nhân.

Tương tự, PASS cũng không tự động chứng minh yêu cầu đã được đáp ứng trong mọi trường hợp. Nó chỉ có ý nghĩa trong phạm vi mà bài kiểm thử thực sự quan sát.

## 4. Ví dụ: kiểm tra một quy tắc bằng unit test

Giả sử ứng dụng có quy tắc tính tổng tiền từ đơn giá và số lượng:

```java
import java.math.BigDecimal;

public class PriceCalculator {

    public BigDecimal total(BigDecimal unitPrice, int quantity) {
        if (unitPrice == null) {
            throw new IllegalArgumentException("unitPrice must not be null");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must be >= 0");
        }

        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Ta muốn kiểm tra hai hành vi: số lượng hợp lệ tạo ra tổng tiền đúng, còn số lượng âm bị từ chối.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class PriceCalculatorTest {

    private final PriceCalculator calculator = new PriceCalculator();

    @Test
    void calculatesTotalForPositiveQuantity() {
        BigDecimal result = calculator.total(
                new BigDecimal("12.50"),
                3
        );

        assertEquals(new BigDecimal("37.50"), result);
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.total(new BigDecimal("12.50"), -1)
        );
    }
}
```

Bài kiểm thử thứ nhất cung cấp bằng chứng rằng đầu vào đơn giá 12.50 và số lượng 3 tạo ra kết quả 37.50. Bài thứ hai cung cấp bằng chứng rằng số lượng âm dẫn đến `IllegalArgumentException`.

Hai bài kiểm thử này chưa kiểm tra mọi hành vi của lớp. Chúng chưa kiểm tra đơn giá bằng `null`, số lượng bằng 0, giá trị rất lớn hoặc những quy tắc làm tròn nếu nghiệp vụ có quy định. Ta cần bổ sung tình huống khi những quy tắc đó thuộc phạm vi yêu cầu.

Ví dụ cũng cho thấy một bài kiểm thử nên nói rõ hành vi được bảo vệ. Tên `calculatesTotalForPositiveQuantity` mô tả kết quả mong đợi; tên `rejectsNegativeQuantity` mô tả cách hệ thống xử lý dữ liệu không hợp lệ. Khi một bài kiểm thử thất bại, tên và assertion giúp người đọc hiểu điều gì đang bị phá vỡ.

## 5. Bằng chứng thay đổi theo phạm vi kiểm thử trong Spring

Ứng dụng Spring thường gồm nhiều lớp: controller tiếp nhận yêu cầu, service xử lý nghiệp vụ, repository truy cập dữ liệu và các thành phần cấu hình hoặc tích hợp. Không phải bài kiểm thử nào cũng cần khởi động toàn bộ ứng dụng.

Chọn phạm vi kiểm thử quyết định loại bằng chứng có thể thu được:

| Phạm vi | Cách kiểm tra thường gặp | Bằng chứng chính |
|---|---|---|
| Unit test | Gọi trực tiếp một lớp Java, không khởi động Spring context | Logic của lớp với đầu vào và phụ thuộc đã kiểm soát |
| MVC slice test | Dùng `@WebMvcTest` và `MockMvc` | Mapping, binding tham số, validation, HTTP status và response của lớp MVC được nạp |
| Persistence slice test | Dùng `@DataJpaTest` | Mapping và truy vấn persistence trong cấu hình cơ sở dữ liệu kiểm thử |
| Integration test | Dùng `@SpringBootTest` | Sự phối hợp giữa các bean và cấu hình được nạp trong application context |

Các phạm vi này trả lời những câu hỏi khác nhau. Unit test chạy nhanh và tập trung vào logic. MVC slice test kiểm tra đường xử lý HTTP ở lớp MVC. Persistence slice test tập trung vào truy cập dữ liệu. Integration test kiểm tra nhiều thành phần phối hợp trong cùng ứng dụng.

Khởi động Spring context không tự động có nghĩa mọi hệ thống bên ngoài đều được kiểm tra. Nếu database, message broker hoặc dịch vụ HTTP được thay bằng mock, bài kiểm thử chỉ cung cấp bằng chứng về cách ứng dụng tương tác với mock đó. Muốn kiểm tra tích hợp thật, môi trường kiểm thử phải có thành phần tương ứng và bài kiểm thử phải thực sự gửi dữ liệu qua ranh giới tích hợp.

### Ví dụ: kiểm tra một endpoint bằng MockMvc

Giả sử controller nhận tên người dùng và gọi `GreetingService`:

```java
@RestController
class GreetingController {

    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greetings")
    String greet(@RequestParam String name) {
        return greetingService.greet(name);
    }
}
```

Một MVC slice test có thể kiểm tra endpoint như sau:

```java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private GreetingService greetingService;

    @Test
    void returnsGreetingForName() throws Exception {
        when(greetingService.greet("Lan")).thenReturn("Xin chào, Lan");

        mockMvc.perform(get("/greetings").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(content().string("Xin chào, Lan"));
    }
}
```

Bài kiểm thử gửi một yêu cầu GET đến `/greetings` với tham số `name=Lan`. Nó xác nhận endpoint trả về HTTP 200 và nội dung phản hồi là `Xin chào, Lan`.

Bằng chứng ở đây bao gồm việc Spring MVC nhận diện mapping, đọc tham số yêu cầu, gọi controller và tạo phản hồi theo kỳ vọng. Nhưng `GreetingService` đã được thay bằng mock. Vì vậy, bài kiểm thử này không chứng minh logic thật bên trong service đúng, cũng không chứng minh database hoặc dịch vụ bên ngoài hoạt động.

Muốn kiểm tra logic của service, hãy viết unit test cho service. Muốn kiểm tra đường đi từ HTTP request qua service đến repository hoặc database, hãy chọn một bài integration test với các phụ thuộc phù hợp. Mỗi bài kiểm thử cần có mục tiêu và phạm vi rõ ràng.

## 6. Những điều một bài kiểm thử không thể tự chứng minh

Một bài kiểm thử luôn có giới hạn. Hiểu giới hạn giúp tránh diễn giải quá mức kết quả PASS.

**Không kiểm tra mọi đầu vào.** Một bài kiểm thử chỉ chạy những trường hợp được mô tả. Đầu vào khác có thể đi qua nhánh xử lý khác và bộc lộ lỗi mới.

**Không chứng minh toàn bộ ứng dụng không có lỗi.** Một tập hợp bài kiểm thử có thể bảo vệ nhiều hành vi quan trọng, nhưng không thể bao quát mọi trạng thái, thứ tự sự kiện và môi trường vận hành.

**Không chứng minh môi trường production giống môi trường kiểm thử.** Cấu hình, phiên bản database, quyền truy cập, mạng và dữ liệu thực tế có thể khác nhau.

**Không bảo đảm yêu cầu nghiệp vụ được hiểu đúng.** Nếu kỳ vọng trong test sai, bài kiểm thử vẫn có thể PASS một cách nhất quán. Chất lượng của test phụ thuộc vào chất lượng của quy tắc và dữ liệu kỳ vọng.

**Không bảo đảm mã nguồn bên trong được thiết kế tốt.** Một bài kiểm thử có thể xác nhận đầu ra đúng dù mã nguồn khó bảo trì, xử lý chậm hoặc có cấu trúc không phù hợp. Những vấn đề đó cần các hình thức đánh giá khác.

### Độ bao phủ không đồng nghĩa với độ đúng

Độ bao phủ kiểm thử (*test coverage*) cho biết phần mã nào đã được thực thi trong quá trình chạy test, tùy theo loại đo lường như dòng lệnh, nhánh hoặc phương thức.

Độ bao phủ cao có thể cho thấy nhiều phần mã đã được chạy, nhưng không cho biết các kết quả có được kiểm tra đúng hay không. Một bài kiểm thử có thể đi qua một dòng lệnh mà không có assertion hữu ích. Ngược lại, một số bài kiểm thử tập trung vào các quy tắc rủi ro cao có thể cung cấp bằng chứng rất có giá trị dù tỷ lệ coverage chưa đạt 100%.

Vì vậy, coverage là một chỉ số hỗ trợ tìm vùng chưa được thực thi. Nó không phải chứng nhận rằng chương trình đúng.

## 7. Đặc điểm của một bài kiểm thử đáng tin cậy

Một bài kiểm thử có giá trị khi người đọc hiểu nó đang bảo vệ hành vi nào và có thể tin vào kết quả chạy lại.

- **Có mục tiêu rõ ràng:** tên test và assertion thể hiện một hành vi cụ thể.
- **Kỳ vọng độc lập với cách cài đặt:** kết quả mong đợi đến từ yêu cầu hoặc quy tắc, không được suy ra bằng cách gọi lại chính logic đang kiểm tra.
- **Kiểm tra kết quả quan sát được:** ưu tiên đầu ra, trạng thái hoặc tương tác thuộc hợp đồng của thành phần.
- **Có dữ liệu đại diện và trường hợp biên:** bao gồm trường hợp bình thường, dữ liệu không hợp lệ và ranh giới quan trọng của quy tắc.
- **Có thể chạy lặp lại:** không phụ thuộc ngẫu nhiên vào thời gian, thứ tự chạy, trạng thái dùng chung hoặc dịch vụ ngoài không được kiểm soát.
- **Báo lỗi đủ rõ:** khi thất bại, người đọc xác định được đầu vào, kỳ vọng và kết quả thực tế.

Mock và stub là công cụ hữu ích để cô lập một thành phần, nhưng việc sử dụng chúng cần có chủ đích. Mock giúp kiểm soát phụ thuộc và kiểm tra tương tác; đồng thời, nó có thể che khuất lỗi trong phần triển khai thật của phụ thuộc đó. Chỉ nên thay thế những thành phần nằm ngoài mục tiêu của bài kiểm thử.

## 8. Cách đọc kết quả kiểm thử

Khi một test chạy xong, đừng chỉ nhìn tổng số PASS và FAIL. Hãy đọc kết quả theo thứ tự:

1. **Bài kiểm thử nào đã chạy?** Xác định tên lớp và phương thức test để biết hành vi được kiểm tra.
2. **Điều kiện ban đầu là gì?** Xem dữ liệu, cấu hình và các mock hoặc stub đã được thiết lập.
3. **Hành động nào được thực hiện?** Xác định phương thức được gọi hoặc yêu cầu HTTP được gửi.
4. **Assertion nào đạt hoặc thất bại?** So sánh giá trị mong đợi với giá trị thực tế, hoặc đọc ngoại lệ được báo cáo.
5. **Phạm vi nào chưa được kiểm tra?** Xác định phụ thuộc thật có được tham gia hay đã bị thay thế, và những nhánh đầu vào nào chưa có tình huống tương ứng.

Ví dụ, thông báo “expected 37.50 but was 35.00” cho biết assertion về tổng tiền không đạt. Nó chưa nói nguyên nhân nằm ở công thức, dữ liệu đầu vào hay kỳ vọng. Cần quay lại tình huống test và quy tắc nghiệp vụ để xác định điểm sai.

Khi tất cả test PASS, có thể kết luận rằng các hành vi được mô tả trong những bài kiểm thử đó đã đạt điều kiện kiểm tra tại lần chạy hiện tại. Đây là bằng chứng hữu ích để tiếp tục phát triển và giảm rủi ro hồi quy. Mức độ tin cậy tăng lên khi các bài kiểm thử có mục tiêu rõ ràng, bao phủ những tình huống quan trọng và kiểm tra đúng ranh giới cần bảo vệ.

## 9. Kết nối khái niệm với công việc phát triển Spring

Trong một dự án Spring, kiểm thử nên bắt đầu từ câu hỏi cần có bằng chứng:

- Quy tắc nghiệp vụ của service có đúng với các đầu vào quan trọng không?
- Controller có nhận đúng tham số và trả đúng HTTP status, response không?
- Repository có lưu và truy vấn dữ liệu theo đúng mapping không?
- Các bean và cấu hình có phối hợp được khi ứng dụng khởi động không?
- Một thay đổi có làm hỏng hành vi đã được xác nhận trước đó không?

Câu hỏi xác định phạm vi; phạm vi giúp chọn loại test; assertion xác định bằng chứng cần thu thập. Khi một bài kiểm thử PASS hoặc FAIL, kết quả chỉ nên được diễn giải trong phạm vi câu hỏi đó.

Kiểm thử vì thế là một phần của quá trình xây dựng phần mềm có thể kiểm chứng. Nó biến các kỳ vọng thành tình huống thực thi được, giúp nhóm phát hiện sai lệch sớm và lưu giữ bằng chứng rằng những hành vi quan trọng vẫn hoạt động sau mỗi thay đổi.
