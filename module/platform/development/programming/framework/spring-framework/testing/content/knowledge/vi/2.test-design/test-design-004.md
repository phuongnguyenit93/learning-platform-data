# Phân vùng tương đương, giá trị biên và dữ liệu không hợp lệ

Khi kiểm thử một chức năng nhận dữ liệu đầu vào, số trường hợp có thể xảy ra thường rất lớn. Một API nhận số lượng từ 1 đến 100 đã có ít nhất một trăm giá trị hợp lệ, chưa kể giá trị thiếu, `null`, số âm, số quá lớn, chuỗi, số thập phân và JSON sai cấu trúc. Nếu chỉ kiểm thử vài giá trị tùy ý, ta có thể bỏ sót lỗi. Nếu thử mọi khả năng, chi phí kiểm thử sẽ nhanh chóng vượt quá lợi ích.

Phân vùng tương đương (Equivalence Partitioning), phân tích giá trị biên (Boundary Value Analysis) và thiết kế kiểm thử dữ liệu không hợp lệ giúp chọn một tập trường hợp nhỏ nhưng có căn cứ. Ba kỹ thuật thường được dùng cùng nhau: phân vùng tương đương chia miền đầu vào thành các nhóm có hành vi dự kiến giống nhau; phân tích giá trị biên tập trung vào những điểm chuyển tiếp giữa các nhóm; kiểm thử dữ liệu không hợp lệ xác nhận hệ thống từ chối dữ liệu sai theo đúng hợp đồng và không tạo ra tác dụng phụ ngoài ý muốn.

Trong ứng dụng Spring, các kỹ thuật này có thể áp dụng ở nhiều lớp: kiểm thử đơn vị cho quy tắc nghiệp vụ, kiểm thử controller với `MockMvc`, kiểm thử tích hợp cho luồng qua Spring và kiểm thử persistence cho các ràng buộc dữ liệu. Việc chọn đúng lớp giúp bài kiểm thử tập trung vào hành vi cần bảo vệ.

## 1. Bắt đầu từ hợp đồng đầu vào

Trước khi chia nhóm dữ liệu, cần diễn đạt rõ chức năng chấp nhận điều gì và phải phản hồi thế nào. Hợp đồng có thể đến từ yêu cầu nghiệp vụ, đặc tả API, annotation validation, quy tắc miền hoặc ràng buộc cơ sở dữ liệu.

Giả sử API tạo đơn hàng nhận trường `quantity` với quy tắc:

- Trường bắt buộc phải có.
- Giá trị phải là số nguyên.
- Giá trị nhỏ nhất là 1 và lớn nhất là 100.
- Cả 1 và 100 đều được chấp nhận.
- Nếu dữ liệu không hợp lệ, API trả về lỗi đầu vào theo quy ước của ứng dụng và không gọi nghiệp vụ tạo đơn hàng.

Hợp đồng này cho biết miền hợp lệ là tập số nguyên từ 1 đến 100, bao gồm cả hai đầu mút. Nó cũng nêu những loại đầu vào cần xem xét: giá trị nằm ngoài khoảng, giá trị thiếu, `null` và biểu diễn sai kiểu.

Không nên suy ra hợp đồng chỉ từ kiểu Java. Ví dụ, khai báo trường là `Integer` không tự giới hạn giá trị trong khoảng 1 đến 100; khai báo `int` cũng không thể phân biệt rõ trường bị thiếu với giá trị mặc định bằng 0 sau một số cách binding. Quy tắc cần được xác định từ yêu cầu và được thực thi rõ ràng trong ứng dụng.

## 2. Phân vùng tương đương

### 2.1. Khái niệm

Phân vùng tương đương là kỹ thuật chia miền dữ liệu đầu vào thành các lớp (partitions) sao cho các giá trị trong cùng một lớp được kỳ vọng có cách xử lý tương tự. Thay vì kiểm thử từng giá trị, ta chọn một hoặc một vài đại diện từ mỗi lớp.

Một lớp tương đương tốt phải dựa trên hành vi của hệ thống, không chỉ dựa trên việc các giá trị trông giống nhau. Nếu hai nhóm giá trị dẫn đến hai kết quả khác nhau theo hợp đồng, chúng cần được tách thành hai lớp, ngay cả khi cả hai đều hợp lệ.

Ví dụ, với `quantity` từ 1 đến 100, có thể chia miền đầu vào như sau:

| Lớp | Dữ liệu đại diện | Hành vi mong đợi |
|---|---|---|
| Hợp lệ | `25` | Chấp nhận và tiếp tục xử lý |
| Nhỏ hơn giới hạn dưới | `0` hoặc `-3` | Từ chối vì nhỏ hơn 1 |
| Lớn hơn giới hạn trên | `101` hoặc `500` | Từ chối vì lớn hơn 100 |
| Thiếu trường | `{}` | Từ chối vì thiếu `quantity` |
| Giá trị `null` | `{"quantity": null}` | Từ chối vì trường bắt buộc |
| Sai kiểu dữ liệu | `{"quantity": "abc"}` | Từ chối vì không thể chuyển thành số nguyên |

Các lớp trên giúp bảo đảm ta kiểm tra được cả vùng hợp lệ lẫn những cách dữ liệu có thể không hợp lệ. Một giá trị đại diện như `25` có thể xác nhận đường xử lý thông thường; một giá trị `0` đại diện cho lớp nhỏ hơn giới hạn; một giá trị `101` đại diện cho lớp lớn hơn giới hạn.

### 2.2. Khi nào cần tách một lớp thành nhiều lớp?

Không phải cứ cùng hợp lệ hoặc cùng không hợp lệ thì luôn thuộc một lớp. Cần tách lớp khi quy tắc hoặc kết quả mong đợi khác nhau.

Ví dụ, nếu đơn hàng được áp dụng mức chiết khấu khác nhau:

- `quantity` từ 1 đến 10: không giảm giá.
- `quantity` từ 11 đến 50: giảm giá 5%.
- `quantity` từ 51 đến 100: giảm giá 10%.
- Ngoài khoảng 1 đến 100: từ chối.

Khi đó, miền hợp lệ phải được chia thành ba lớp riêng vì cùng một yêu cầu có thể tạo ra kết quả nghiệp vụ khác nhau. Chỉ kiểm tra `quantity = 25` sẽ không xác nhận được quy tắc ở hai mức còn lại.

Một số yếu tố thường làm thay đổi lớp tương đương:

- Quy tắc nghiệp vụ hoặc mức xử lý khác nhau theo khoảng giá trị.
- Vai trò người dùng hoặc quyền truy cập khác nhau.
- Trạng thái hiện tại của tài nguyên, chẳng hạn đang hoạt động, đã khóa hoặc đã xóa.
- Định dạng, độ dài, bảng chữ cái hoặc cấu trúc dữ liệu khác nhau.
- Quy tắc phụ thuộc vào thời điểm, múi giờ, loại tiền tệ hoặc cấu hình.

Ví dụ, mã khách hàng chỉ chấp nhận chữ in hoa và chữ số có thể cần các lớp riêng cho mã đúng định dạng, mã có chữ thường, mã thiếu ký tự, mã chứa ký tự đặc biệt và mã quá dài. Nếu các loại sai định dạng tạo ra cùng một lỗi validation thì có thể dùng một đại diện cho mỗi nhóm quy tắc; nếu API trả về lỗi khác nhau theo từng điều kiện, nên tách nhóm tương ứng.

### 2.3. Chọn giá trị đại diện

Giá trị đại diện nên đơn giản, dễ đọc và thể hiện rõ lớp mà nó đại diện. Với lớp hợp lệ 1 đến 100, có thể chọn 25. Với lớp nhỏ hơn 1, chọn 0. Với lớp lớn hơn 100, chọn 101.

Không nên chỉ chọn các giá trị gần nhau hoặc các giá trị quen thuộc mà không xét quy tắc. Một giá trị nằm giữa khoảng có thể đại diện cho lớp hợp lệ thông thường, nhưng nó không thể thay thế kiểm thử ở các điểm biên. Đó là lý do phân vùng tương đương thường được kết hợp với phân tích giá trị biên.

Với đầu vào nhiều trường, cần xem xét cả quan hệ giữa các trường. Ví dụ, `startDate` và `endDate` có thể đều là ngày hợp lệ riêng lẻ nhưng tổ hợp lại không hợp lệ nếu `endDate` đứng trước `startDate`. Trong trường hợp đó, lớp tương đương phải xét cả điều kiện liên trường, không chỉ từng trường độc lập.

## 3. Phân tích giá trị biên

### 3.1. Vì sao cần kiểm thử biên?

Lỗi thường xuất hiện ở điểm chuyển tiếp giữa hai miền xử lý: dùng nhầm `>` thay cho `>=`, tính sai độ dài tối đa, bỏ sót ngày cuối kỳ hoặc xử lý lệch chỉ số một đơn vị. Phân tích giá trị biên tập trung vào các điểm này.

Với một khoảng hợp lệ có giới hạn dưới `min` và giới hạn trên `max`, bộ giá trị thường dùng là:

- `min - 1`: ngay dưới giới hạn dưới.
- `min`: đúng giới hạn dưới.
- `min + 1`: ngay trên giới hạn dưới.
- `max - 1`: ngay dưới giới hạn trên.
- `max`: đúng giới hạn trên.
- `max + 1`: ngay trên giới hạn trên.

Với `quantity` từ 1 đến 100, các giá trị cần chú ý là:

| Vị trí | Giá trị | Kết quả mong đợi |
|---|---:|---|
| Ngay dưới min | 0 | Từ chối |
| Min | 1 | Chấp nhận |
| Ngay trên min | 2 | Chấp nhận |
| Ngay dưới max | 99 | Chấp nhận |
| Max | 100 | Chấp nhận |
| Ngay trên max | 101 | Từ chối |

Bộ sáu giá trị này phát hiện được nhiều lỗi phổ biến hơn việc chỉ kiểm tra một giá trị hợp lệ ở giữa và một giá trị không hợp lệ ở xa giới hạn.

### 3.2. Biên bao gồm và biên loại trừ

Điều kiện giới hạn có thể bao gồm hoặc loại trừ chính giá trị biên. Hai quy tắc sau không tương đương:

```java
quantity >= 1 && quantity <= 100
```

```java
quantity > 1 && quantity < 100
```

Quy tắc đầu chấp nhận cả 1 và 100; quy tắc thứ hai từ chối cả hai giá trị. Bài kiểm thử phải thể hiện đúng ý nghĩa của hợp đồng, không chỉ kiểm tra các giá trị nằm sâu bên trong khoảng.

Với chuỗi có độ dài từ 3 đến 20 ký tự, cần chú ý độ dài 2, 3, 4, 19, 20 và 21. Với trang kết quả có chỉ số trang bắt đầu từ 0, cần kiểm tra trang 0, trang 1, trang cuối và trang vượt quá phạm vi theo chính sách API. Với ngày hiệu lực, cần kiểm tra thời điểm ngay trước, đúng tại và ngay sau mốc chuyển trạng thái, đồng thời xác định rõ múi giờ và độ chính xác thời gian.

### 3.3. Biên của miền rời rạc và miền liên tục

Với miền rời rạc như số nguyên, có thể dùng giá trị liền kề `min - 1`, `min`, `min + 1`. Với miền liên tục như số tiền thập phân hoặc thời điểm, cần xác định độ chính xác mà hệ thống hỗ trợ trước khi chọn giá trị sát biên.

Ví dụ, nếu số tiền được lưu đến hai chữ số thập phân và giới hạn tối thiểu là 0.01, các trường hợp có thể gồm 0.00, 0.01 và 0.02. Nếu API chỉ chấp nhận số nguyên đơn vị nhỏ nhất, các giá trị thập phân phải được kiểm tra theo quy tắc định dạng riêng.

Không nên tự ý dùng một epsilon rất nhỏ cho mọi miền liên tục. Giá trị sát biên cần phản ánh độ chính xác của kiểu dữ liệu, đơn vị nghiệp vụ và cách hệ thống làm tròn.

### 3.4. Biên của nhiều điều kiện

Khi một chức năng có nhiều trường, mỗi trường có thể có biên riêng. Nếu kiểm thử mọi tổ hợp của tất cả giá trị biên, số trường hợp sẽ tăng nhanh. Có thể ưu tiên:

1. Kiểm tra từng trường tại biên trong khi giữ các trường còn lại ở giá trị hợp lệ ổn định.
2. Kiểm tra các tổ hợp có ý nghĩa nghiệp vụ, chẳng hạn hai trường phụ thuộc lẫn nhau.
3. Kiểm tra thêm tổ hợp rủi ro cao khi một lỗi ở một trường có thể làm thay đổi cách xử lý trường khác.

Ví dụ, biểu mẫu đăng ký có `age` từ 18 đến 65 và `startDate` không được nằm trong quá khứ. Trước tiên, kiểm tra các biên tuổi với ngày bắt đầu hợp lệ; sau đó kiểm tra các mốc ngày với tuổi hợp lệ. Cuối cùng, kiểm tra những kết hợp được quy tắc nghiệp vụ quan tâm. Cách làm này giúp xác định nguyên nhân khi một bài kiểm thử thất bại.

## 4. Thiết kế kiểm thử dữ liệu không hợp lệ

### 4.1. Dữ liệu không hợp lệ có nhiều dạng

Một đầu vào có thể sai ở nhiều lớp khác nhau. Việc phân loại giúp xác định thành phần chịu trách nhiệm phát hiện lỗi và kết quả cần kiểm tra.

| Nhóm dữ liệu | Ví dụ | Vấn đề cần phát hiện |
|---|---|---|
| Thiếu dữ liệu | Không gửi `quantity` | Trường bắt buộc chưa được cung cấp |
| Giá trị rỗng | `null`, `""` hoặc chuỗi chỉ có khoảng trắng | Phân biệt rỗng với thiếu và giá trị hợp lệ |
| Sai kiểu | Chuỗi thay cho số, object thay cho chuỗi | Binding hoặc chuyển đổi dữ liệu thất bại |
| Sai định dạng | Email thiếu phần tên miền, mã chứa ký tự cấm | Không thỏa định dạng quy định |
| Ngoài miền giá trị | Số âm, số vượt giới hạn | Vi phạm giới hạn hoặc miền hợp lệ |
| Vi phạm quan hệ | Ngày kết thúc trước ngày bắt đầu | Các trường riêng lẻ hợp lệ nhưng tổ hợp sai |
| Vi phạm nghiệp vụ | Đặt hàng với sản phẩm ngừng kinh doanh | Dữ liệu đúng cấu trúc nhưng không hợp lệ trong trạng thái hiện tại |
| Trùng lặp hoặc xung đột | Tạo tài khoản bằng email đã tồn tại | Vi phạm tính duy nhất hoặc trạng thái tài nguyên |

Không nên gom tất cả các trường hợp trên vào một bài kiểm thử duy nhất. Chúng có thể được xử lý ở các lớp khác nhau và tạo ra phản hồi khác nhau.

### 4.2. Phân biệt lỗi cú pháp, validation và nghiệp vụ

**Lỗi cú pháp hoặc binding** xảy ra khi request không thể được phân tích theo cấu trúc mà API mong đợi. Ví dụ, API chờ một số nguyên nhưng client gửi một object. Lỗi có thể xuất hiện trước khi controller được gọi.

**Lỗi validation** xảy ra khi dữ liệu đã được đọc thành công nhưng vi phạm ràng buộc. Ví dụ, `quantity = 0` là một số nguyên hợp lệ về mặt biểu diễn nhưng nằm ngoài khoảng cho phép.

**Lỗi nghiệp vụ** xảy ra khi dữ liệu đúng kiểu và có thể vượt qua validation cơ bản nhưng không phù hợp với quy tắc miền hoặc trạng thái hiện tại. Ví dụ, số lượng nằm trong khoảng cho phép nhưng sản phẩm đã ngừng bán.

Ba loại lỗi này có thể cùng dẫn đến phản hồi 4xx, nhưng không nhất thiết dùng cùng mã trạng thái hoặc cùng cấu trúc lỗi. Mã HTTP cụ thể cần tuân theo hợp đồng API của ứng dụng. Điều quan trọng là bài kiểm thử xác nhận đúng nơi phát hiện lỗi, đúng phản hồi công khai và không để thao tác tiếp tục khi dữ liệu đã bị từ chối.

### 4.3. Kiểm tra tác dụng phụ

Khi dữ liệu không hợp lệ, chỉ kiểm tra HTTP status là chưa đủ. Một lỗi validation có thể trả về 400 nhưng vẫn gọi service hoặc ghi dữ liệu nếu luồng xử lý được thiết kế sai.

Tùy chức năng, cần xác nhận các điều kiện như:

- Service nghiệp vụ không được gọi khi request không qua validation ở tầng web.
- Không tạo bản ghi hoặc cập nhật trạng thái khi thao tác bị từ chối.
- Không gửi thông báo, email hoặc sự kiện ngoài hệ thống khi giao dịch không hợp lệ.
- Không làm thay đổi dữ liệu đã tồn tại.
- Lỗi trả về đủ thông tin để client sửa đầu vào nhưng không làm lộ stack trace, thông tin bí mật hoặc chi tiết nội bộ.

Với kiểm thử tích hợp có cơ sở dữ liệu, nên đọc lại trạng thái sau request để xác nhận dữ liệu không bị thay đổi. Với kiểm thử controller dùng mock, có thể xác nhận service không được gọi. Chọn cách kiểm tra phù hợp với tác dụng phụ mà lớp đang kiểm thử có trách nhiệm kiểm soát.

### 4.4. Phân biệt thiếu, null, rỗng và khoảng trắng

Các trạng thái sau có thể mang ý nghĩa khác nhau:

```json
{}
```

```json
{"name": null}
```

```json
{"name": ""}
```

```json
{"name": "   "}
```

`@NotNull` chỉ kiểm tra giá trị không phải `null`; nó không tự cấm chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng. Với chuỗi bắt buộc, có thể cần `@NotBlank`. Với chuỗi được phép rỗng nhưng không được vượt quá độ dài, `@Size` có ý nghĩa khác. Bài kiểm thử nên phản ánh chính xác annotation và hợp đồng đang dùng.

## 5. Áp dụng trong Spring với Jakarta Bean Validation

Spring MVC có thể kích hoạt Bean Validation cho request body bằng `@Valid`. Các constraint như `@NotNull`, `@Min`, `@Max`, `@Size`, `@NotBlank` và `@Pattern` giúp khai báo quy tắc đầu vào ngay trên DTO.

Ví dụ DTO nhận số lượng:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity
) {
}
```

Ở đây dùng `Integer` cùng `@NotNull` để biểu diễn rõ trường hợp không có giá trị. `@Min(1)` và `@Max(100)` xác định giới hạn dưới và trên. Để các constraint hoạt động trong ứng dụng Spring Boot, dự án cần có dependency validation tương ứng, thường là `spring-boot-starter-validation`.

Controller kích hoạt validation:

```java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    ResponseEntity<Void> create(@Valid @RequestBody CreateOrderRequest request) {
        orderService.create(request.quantity());
        return ResponseEntity.accepted().build();
    }
}
```

`@Valid` yêu cầu Spring kiểm tra các constraint trên request object trước khi thực thi phần thân phương thức controller. Nếu validation thất bại, Spring xử lý lỗi theo cơ chế exception handling của ứng dụng. Nếu JSON không thể được chuyển thành DTO, lỗi binding/deserialization có thể xảy ra trước bước Bean Validation.

## 6. Kiểm thử các lớp tương đương và giá trị biên bằng MockMvc

`@WebMvcTest` phù hợp để kiểm tra hợp đồng web của controller: request được binding, validation được kích hoạt và phản hồi HTTP được tạo đúng. Service có thể được mock để kiểm tra controller không chuyển dữ liệu sai xuống tầng nghiệp vụ.

Ví dụ dưới đây dùng JUnit 5 và Mockito. `OrderService` là dependency của controller:

```java
interface OrderService {
    void create(Integer quantity);
}
```

Kiểm thử các giá trị hợp lệ, gồm cả hai điểm biên:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private OrderService orderService;

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 25, 99, 100})
    void acceptsQuantityInsideAllowedRange(int quantity) throws Exception {
        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"quantity": %d}
                                """.formatted(quantity)))
                .andExpect(status().isAccepted());

        verify(orderService).create(quantity);
    }
}
```

Các giá trị 1 và 100 xác nhận hai đầu mút được chấp nhận; 2 và 99 nằm sát phía trong của mỗi đầu mút; 25 đại diện cho vùng hợp lệ thông thường. Nếu có thêm lớp nghiệp vụ trong khoảng, cần thêm đại diện cho mỗi lớp đó.

Kiểm thử các giá trị nằm ngoài giới hạn:

```java
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ParameterizedTest
@ValueSource(ints = {0, 101})
void rejectsQuantityOutsideAllowedRange(int quantity) throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"quantity": %d}
                            """.formatted(quantity)))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Hai giá trị 0 và 101 nằm ngay ngoài khoảng hợp lệ. Việc xác nhận service không có tương tác chứng minh request bị chặn trước khi đi vào nghiệp vụ. Nếu ứng dụng dùng mã trạng thái khác cho validation error, hãy thay assertion bằng mã được quy định trong hợp đồng API.

Các trường hợp thiếu và `null` có thể kiểm tra riêng vì chúng đại diện cho các lớp đầu vào khác nhau:

```java
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsMissingQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{}"))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}

@Test
void rejectsNullQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""{"quantity": null}"""))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Một giá trị sai kiểu cũng cần được kiểm tra ở tầng web:

```java
@Test
void rejectsNonNumericQuantity() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""{"quantity": "many"}"""))
            .andExpect(status().isBadRequest());

    verifyNoInteractions(orderService);
}
```

Trong ví dụ này, chuỗi `"many"` không thể được chuyển thành `Integer` theo cấu hình binding thông thường. Với các biểu diễn như số thập phân, số quá lớn hoặc chuỗi số, hành vi có thể phụ thuộc cấu hình Jackson và chính sách coercion của ứng dụng. Hãy xác định rõ API có cho phép chuyển đổi hay không rồi viết assertion theo cấu hình thực tế; không nên giả định mọi cấu hình đều xử lý các biểu diễn đó giống nhau.

Các đoạn mã là ví dụ minh họa cách tổ chức bài kiểm thử. Trong dự án cụ thể, cần bổ sung import, cấu hình test slice và các dependency tương ứng; đồng thời dùng đúng mã HTTP và response contract mà ứng dụng đã công bố.

## 7. Kiểm thử ở đúng tầng trong ứng dụng Spring

Một quy tắc có thể được kiểm tra ở nhiều tầng, nhưng mỗi tầng nên tập trung vào trách nhiệm của nó.

| Tầng kiểm thử | Nên kiểm tra | Ví dụ phù hợp |
|---|---|---|
| Unit test cho domain/service | Quy tắc nghiệp vụ thuần Java và các lớp tương đương của miền | Số lượng hợp lệ, mức chiết khấu, quan hệ giữa ngày bắt đầu và kết thúc |
| Kiểm thử validation | Constraint trên DTO hoặc đối tượng đầu vào | `@NotNull`, `@Min`, `@Max`, `@Pattern` |
| `@WebMvcTest` với `MockMvc` | Binding JSON, kích hoạt validation, mã HTTP và cấu trúc phản hồi | Thiếu trường, sai kiểu, giá trị ngoài khoảng |
| `@SpringBootTest` | Luồng tích hợp qua cấu hình Spring và các bean liên quan | Request đi qua controller, service và thành phần tích hợp |
| Kiểm thử persistence | Ràng buộc dữ liệu và hành vi lưu trữ | Unique constraint, foreign key, check constraint, rollback |

Không cần đưa mọi tổ hợp dữ liệu vào `@SpringBootTest`. Kiểm tra từng quy tắc ở tầng nhỏ nhất có thể giúp bài kiểm thử nhanh và dễ xác định nguyên nhân. Chỉ dùng kiểm thử tích hợp khi cần xác nhận sự phối hợp giữa nhiều thành phần, chẳng hạn validation, transaction và cơ sở dữ liệu.

Ràng buộc ở cơ sở dữ liệu vẫn có vai trò riêng. Validation ở API giúp trả lỗi sớm và thân thiện; constraint ở database bảo vệ tính toàn vẹn khi dữ liệu được ghi từ nhiều đường vào khác nhau hoặc khi có tranh chấp đồng thời. Một bài kiểm thử service có thể không phát hiện được vi phạm unique constraint xảy ra do hai request chạy gần như cùng lúc, vì vậy trường hợp đó cần kiểm thử ở tầng persistence hoặc tích hợp phù hợp.

## 8. Quy trình thiết kế một bộ kiểm thử

Với một chức năng nhận dữ liệu, có thể tiến hành theo trình tự sau:

1. **Viết lại quy tắc thành điều kiện rõ ràng.** Xác định trường bắt buộc, kiểu dữ liệu, khoảng hợp lệ, định dạng, quan hệ giữa các trường và quy tắc phụ thuộc trạng thái.
2. **Chia lớp tương đương.** Liệt kê các nhóm đầu vào có cùng hành vi dự kiến. Tách lớp khi kết quả nghiệp vụ hoặc phản hồi khác nhau.
3. **Chọn đại diện cho mỗi lớp.** Ưu tiên giá trị đơn giản, dễ hiểu và thể hiện đúng quy tắc.
4. **Bổ sung giá trị biên.** Với mỗi giới hạn, kiểm tra giá trị ngay dưới, đúng tại và ngay trên giới hạn nếu miền dữ liệu cho phép.
5. **Bổ sung dữ liệu không hợp lệ theo từng nguyên nhân.** Xét thiếu, `null`, rỗng, sai kiểu, sai định dạng, ngoài miền, vi phạm quan hệ và vi phạm nghiệp vụ.
6. **Chọn tầng kiểm thử.** Kiểm tra quy tắc thuần ở unit test, hợp đồng HTTP ở `MockMvc`, tích hợp bean hoặc database ở tầng tương ứng.
7. **Kiểm tra cả kết quả và tác dụng phụ.** Ngoài status hoặc giá trị trả về, xác nhận service, database, event hoặc thao tác ngoài hệ thống có được gọi đúng lúc hay không.

Khi số trường tăng lên, không nên nhân toàn bộ các tập giá trị với nhau một cách máy móc. Hãy kiểm tra độc lập từng điều kiện trước, sau đó thêm các tổ hợp mà nghiệp vụ thực sự phụ thuộc hoặc có rủi ro cao. Nếu hai trường có quan hệ, chẳng hạn `startDate <= endDate`, hãy thiết kế các trường hợp hợp lệ và không hợp lệ cho chính mối quan hệ đó.

## 9. Những sai lầm thường gặp

**Chỉ kiểm tra một giá trị hợp lệ và một giá trị không hợp lệ.** Hai trường hợp này thường bỏ qua giới hạn bao gồm/loại trừ, lớp nghiệp vụ ở giữa và các dạng dữ liệu sai khác nhau. Hãy dùng phân vùng để bảo đảm mỗi nhóm có đại diện, rồi bổ sung biên.

**Chỉ kiểm tra biên mà không kiểm tra vùng giữa.** Các giá trị 1, 2, 99 và 100 rất hữu ích, nhưng chúng không đại diện cho mọi lớp nghiệp vụ có thể nằm giữa khoảng. Nếu mức giá hoặc quyền xử lý thay đổi ở một mốc nội bộ, cần kiểm tra mốc đó.

**Gom mọi đầu vào sai vào một lớp.** Thiếu trường, `null`, sai kiểu và vi phạm nghiệp vụ có thể đi qua các thành phần khác nhau. Tách chúng giúp bài kiểm thử chỉ rõ lỗi nằm ở binding, validation hay nghiệp vụ.

**Dùng kiểu nguyên thủy rồi bỏ qua trường hợp thiếu.** `int` không biểu diễn được `null`; nếu trường bắt buộc và cần phân biệt thiếu với giá trị số, kiểu wrapper như `Integer` cùng constraint thích hợp thường rõ ràng hơn.

**Cho rằng `@NotNull` cũng cấm chuỗi rỗng.** Constraint này chỉ cấm `null`. Với chuỗi không được rỗng hoặc chỉ có khoảng trắng, cần chọn constraint như `@NotBlank` hoặc quy tắc phù hợp.

**Chỉ xác nhận status lỗi.** Một request có thể trả lỗi nhưng vẫn kích hoạt service hoặc tạo tác dụng phụ. Hãy kiểm tra tương tác hoặc trạng thái lưu trữ theo trách nhiệm của lớp đang kiểm thử.

**Kiểm tra thông điệp lỗi quá chi tiết ở mọi bài test.** Nếu nội dung thông điệp không phải hợp đồng ổn định, việc khóa cứng toàn bộ câu chữ khiến test dễ hỏng khi thay đổi cách diễn đạt hoặc bản địa hóa. Thường nên ưu tiên status, mã lỗi ổn định, tên trường và các thuộc tính công khai cần thiết. Chỉ kiểm tra nguyên văn thông điệp khi đó là yêu cầu sản phẩm.

**Dựa hoàn toàn vào validation ở controller.** Dữ liệu có thể đi vào service từ message consumer, scheduled job, batch hoặc một đường gọi nội bộ khác. Quy tắc nghiệp vụ quan trọng cần được bảo vệ ở tầng phù hợp với mọi đường vào; validation web chỉ bảo vệ hợp đồng HTTP.

## 10. Kết hợp ba kỹ thuật trong một ví dụ

Với hợp đồng `quantity` là số nguyên bắt buộc từ 1 đến 100, một bộ kiểm thử gọn có thể được tổ chức như sau:

| Mục tiêu | Đầu vào | Kỹ thuật | Kết quả cần xác nhận |
|---|---|---|---|
| Đường hợp lệ thông thường | `25` | Phân vùng tương đương | Request được chấp nhận |
| Biên dưới | `0`, `1`, `2` | Giá trị biên | 0 bị từ chối; 1 và 2 được chấp nhận |
| Biên trên | `99`, `100`, `101` | Giá trị biên | 99 và 100 được chấp nhận; 101 bị từ chối |
| Trường bị thiếu | `{}` | Dữ liệu không hợp lệ | Validation thất bại, service không được gọi |
| Giá trị null | `{"quantity": null}` | Dữ liệu không hợp lệ | Validation thất bại, service không được gọi |
| Sai kiểu | `{"quantity": "many"}` | Dữ liệu không hợp lệ | Binding thất bại, service không được gọi |

Nếu sau này có quy tắc chiết khấu tại mốc 10 và 50, cần bổ sung các lớp nghiệp vụ và kiểm thử biên quanh các mốc đó: 9, 10, 11 và 49, 50, 51. Nếu API bổ sung điều kiện theo trạng thái sản phẩm, cần thêm lớp tương đương cho sản phẩm đang bán và đã ngừng bán, rồi xác nhận phản hồi nghiệp vụ tương ứng.

Phân vùng tương đương giúp chọn đại diện có hệ thống; phân tích giá trị biên tập trung vào các điểm dễ phát sinh lỗi so sánh; kiểm thử dữ liệu không hợp lệ xác nhận hệ thống từ chối những đầu vào vi phạm hợp đồng và giữ nguyên trạng thái cần bảo vệ. Khi kết hợp chúng với đúng tầng kiểm thử của Spring, bộ kiểm thử vừa bao phủ được các quy tắc quan trọng vừa giữ được mục đích rõ ràng cho từng trường hợp.
