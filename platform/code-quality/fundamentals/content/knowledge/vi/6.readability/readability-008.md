# Phân biệt mã ngắn với mã dễ hiểu

Một phương thức chỉ có ba dòng chưa chắc dễ đọc hơn phương thức có mười dòng. Ba dòng đó có thể chứa nhiều điều kiện lồng nhau, các tên viết tắt khó đoán hoặc những tác động phụ bị giấu trong biểu thức. Ngược lại, một đoạn mã ngắn dùng cấu trúc quen thuộc, tên rõ nghĩa và một quy tắc đơn giản có thể rất dễ hiểu.

Trong chương **Khả năng đọc** của module **CODE_QUALITY_FUNDAMENTALS**, điều quan trọng là nhận diện những thuộc tính khiến mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi. Vì thế, cần phân biệt **độ ngắn của mã** với **nỗ lực cần thiết để người khác hiểu đúng mã**. Mục tiêu không phải kéo dài mọi đoạn mã, mà là biểu đạt ý định, điều kiện và kết quả đủ rõ để người đọc có thể sửa đổi an toàn.

## 1. Hai khái niệm liên quan nhưng khác nhau

**Mã ngắn** thường được hiểu là mã có ít dòng, ít ký tự hoặc ít cấu trúc nhìn thấy. Đây là đặc điểm có thể đếm được, nhưng tự nó chưa phản ánh người đọc có hiểu đúng hay không.

**Mã dễ hiểu** là mã giúp người đọc nhanh chóng xây dựng được hình dung chính xác về:

- **Mục đích:** Đoạn mã thực hiện quy tắc nghiệp vụ nào?
- **Đầu vào và đầu ra:** Dữ liệu mang ý nghĩa gì, có đơn vị và ràng buộc nào?
- **Luồng điều khiển:** Khi nào đi vào từng nhánh, khi nào thoát hoặc ném lỗi?
- **Thay đổi trạng thái:** Có cập nhật đối tượng, lưu dữ liệu hoặc gọi hệ thống bên ngoài không?
- **Trường hợp biên:** Điều gì xảy ra với giá trị bằng ngưỡng, rỗng, âm hoặc không hợp lệ?
- **Vị trí cần sửa:** Nếu quy tắc thay đổi, nên sửa ở đâu và cần kiểm tra gì?

Một đoạn mã dễ hiểu giúp người đọc trả lời các câu hỏi đó **dựa trên bằng chứng trong mã và hợp đồng liên quan**, thay vì suy đoán.

| Góc nhìn | Mã ngắn | Mã dễ hiểu |
| --- | --- | --- |
| Cách nhận diện | Ít dòng, ít ký tự hoặc ít lời gọi | Ý định, dữ liệu và nhánh xử lý rõ ràng |
| Lợi ích có thể có | Ít nội dung phải nhìn, giảm lặp đơn giản | Giảm hiểu nhầm, hỗ trợ review và thay đổi an toàn |
| Rủi ro khi tối ưu quá mức | Nén nhiều ý vào một biểu thức; tên khó đoán | Trừu tượng hóa quá mức nếu “làm rõ” thiếu chọn lọc |
| Cách đánh giá | Đếm dòng hoặc ký tự | Thử giải thích quy tắc, lần theo nhánh, xác định lỗi và điểm sửa |
| Quan hệ với tính đúng | Không bảo đảm đúng | Dễ kiểm chứng hơn nhưng vẫn không bảo đảm đúng |

Độ dài vẫn có ý nghĩa: mã quá dài thường khiến người đọc phải giữ nhiều chi tiết trong đầu. Tuy nhiên, **số dòng là tín hiệu để xem xét, không phải thước đo độc lập của khả năng đọc**.

## 2. Vì sao mã càng nén có thể càng khó đọc?

Khi đọc mã, lập trình viên phải xây dựng một mô hình trong đầu: biến nào đại diện cho điều gì, điều kiện nào ưu tiên, trạng thái nào có thể xảy ra. Mã càng đòi hỏi nhiều bước suy luận ngầm, khả năng hiểu sai càng cao.

### 2.1. Mật độ ý nghĩa cao

Một dòng có thể chứa nhiều quyết định:

~~~java
return (vip && total >= 300_000) || total >= 500_000 ? 0 : 30_000;
~~~

Để hiểu, người đọc phải tự xác định:

1. **vip** có ý nghĩa và phạm vi áp dụng gì?
2. Hai ngưỡng **300.000** và **500.000** đại diện cho chính sách nào?
3. Toán tử **&&**, **||** và **?:** kết hợp như thế nào?
4. Giá trị **0** và **30.000** đại diện cho phí, điểm hay đơn vị khác?
5. Điều kiện biên dùng **>=** có đúng với yêu cầu không?

Biểu thức này không nhất thiết sai, nhưng ngắn về mặt ký tự trong khi chứa nhiều ý nghĩa cần giải mã.

### 2.2. Tên ngắn làm thiếu thông tin

~~~java
int a = 500_000;
int b = 30_000;
int c = x >= a ? 0 : b;
~~~

Nếu không có ngữ cảnh, không rõ **a**, **b**, **c**, **x** là gì. Đổi thành **freeShippingThresholdVnd**, **standardShippingFeeVnd**, **subtotalVnd** giúp người đọc hiểu quy tắc và đơn vị tiền mà không cần nhớ bảng đối chiếu tên.

Tên dài hơn đôi chút có thể giảm đáng kể lượng thông tin phải suy luận. Nhưng không cần đặt tên như một câu văn hoàn chỉnh hoặc lặp lại tên lớp ở mọi biến cục bộ.

### 2.3. Biểu thức có tác động phụ bị che giấu

Khi một biểu thức vừa tính kết quả vừa thay đổi đối tượng, ghi log, gửi thông điệp hoặc lưu dữ liệu, người đọc phải theo dõi thêm **thứ tự thực thi** và **trạng thái sau mỗi bước**.

Ví dụ, một chuỗi xử lý Stream có lời gọi **peek** dùng để sửa đối tượng có thể trông gọn nhưng che giấu tác động phụ. Stream là cơ chế xử lý lười; một số thao tác có thể được tối ưu và không phải mọi hành động trong pipeline đều được thực thi theo trực giác của người mới. Vì vậy, **peek** không nên được dùng làm nơi đặt tác động nghiệp vụ quan trọng.

### 2.4. Trừu tượng hóa có thể che giấu quy tắc

~~~java
return policy.execute(context);
~~~

Dòng này rất ngắn, nhưng người đọc chưa thể biết **policy** chứa những quy tắc nào hoặc **execute** có tác động gì. Nó có thể là một thiết kế tốt nếu giao diện và tên gọi diễn đạt đúng trách nhiệm, hoặc là thiết kế khó hiểu nếu phải mở qua nhiều lớp mới tìm thấy một phép so sánh đơn giản.

**Ẩn chi tiết triển khai** có ích khi chi tiết đó thuộc một trách nhiệm độc lập. **Ẩn ý nghĩa nghiệp vụ** sau các tên mơ hồ lại khiến mã khó đọc hơn.

## 3. Ví dụ Java: cùng hành vi nhưng khác khả năng đọc

Giả sử một cửa hàng có chính sách phí vận chuyển:

1. Tổng giá trị đơn hàng âm là đầu vào không hợp lệ.
2. Khách VIP được miễn phí khi tổng giá trị từ **300.000 VND** trở lên.
3. Mọi khách hàng được miễn phí khi tổng giá trị từ **500.000 VND** trở lên.
4. Những đơn hàng hợp lệ còn lại phải trả **30.000 VND** phí vận chuyển.

### 3.1. Phiên bản ngắn

~~~java
public final class ShippingFeeCalculator {
    public int calculate(int total, boolean vip) {
        if (total < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        return ((vip && total >= 300_000) || total >= 500_000)
                ? 0 : 30_000;
    }
}
~~~

Mã này đúng theo quy tắc đã nêu. Tuy nhiên, ba con số và một biểu thức điều kiện gộp buộc người đọc tự đối chiếu ý nghĩa của từng trường hợp.

### 3.2. Phiên bản diễn đạt quy tắc

~~~java
public final class ShippingFeeCalculator {
    private static final int VIP_FREE_SHIPPING_FROM_VND = 300_000;
    private static final int STANDARD_FREE_SHIPPING_FROM_VND = 500_000;
    private static final int STANDARD_SHIPPING_FEE_VND = 30_000;

    public int calculate(int subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        if (vip && subtotalVnd >= VIP_FREE_SHIPPING_FROM_VND) {
            return 0;
        }

        if (subtotalVnd >= STANDARD_FREE_SHIPPING_FROM_VND) {
            return 0;
        }

        return STANDARD_SHIPPING_FEE_VND;
    }
}
~~~

Phiên bản này dài hơn nhưng cho thấy các quy tắc theo thứ tự:

- **subtotalVnd** nói rõ đây là tổng giá trị tính bằng VND.
- Tên hằng số chỉ ra chính sách nào đang được áp dụng.
- Mỗi nhánh **if** diễn đạt một lý do miễn phí cụ thể.
- Đường xử lý mặc định là phí vận chuyển tiêu chuẩn.
- Trường hợp không hợp lệ được xử lý ngay, tránh lan truyền xuống các nhánh còn lại.

Hai phiên bản được viết thành hai đoạn độc lập để so sánh; trong mã dự án chỉ chọn **một** phiên bản của lớp **ShippingFeeCalculator**.

### 3.3. Kiểm tra sự tương đương

| Khách VIP | Tổng đơn (VND) | Phí đúng (VND) | Ý nghĩa |
| --- | ---: | ---: | --- |
| Không | 0 | 30.000 | Đơn hợp lệ dưới ngưỡng |
| Có | 299.999 | 30.000 | Sát dưới ngưỡng VIP |
| Có | 300.000 | 0 | Đúng ngưỡng VIP |
| Không | 499.999 | 30.000 | Sát dưới ngưỡng chung |
| Không | 500.000 | 0 | Đúng ngưỡng chung |
| Có | 500.000 | 0 | Đồng thời thỏa hai điều kiện |
| Bất kỳ | -1 | Ném IllegalArgumentException | Đầu vào không hợp lệ |

Những ca biên cho thấy vì sao **rõ nghĩa** giúp review tốt hơn: khi chính sách là “từ 300.000 trở lên”, người đọc dễ nhận ra việc đổi **>=** thành **>** sẽ làm sai đơn hàng đúng 300.000 VND.

Ví dụ kiểm thử với JUnit 5 cho cả giá trị thường và giá trị biên:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingFeeCalculatorTest {
    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @ParameterizedTest
    @CsvSource({
        "false, 0, 30000",
        "true, 299999, 30000",
        "true, 300000, 0",
        "false, 499999, 30000",
        "false, 500000, 0",
        "true, 500000, 0"
    })
    void calculatesShippingFee(
            boolean vip, int subtotalVnd, int expectedFeeVnd) {
        assertEquals(expectedFeeVnd,
                calculator.calculate(subtotalVnd, vip));
    }

    @Test
    void rejectsNegativeSubtotal() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> calculator.calculate(-1, false));
        assertEquals("Negative subtotal", error.getMessage());
    }
}
~~~

Kiểm thử giúp phát hiện thay đổi hành vi ngoài ý muốn; chúng **không thay thế việc đọc mã** để đánh giá người phát triển có hiểu và sửa quy tắc dễ dàng hay không.

### 3.4. Một điểm cân bằng khác cũng có thể hợp lý

Nếu nhóm đã quen với biểu thức Boolean và muốn một phương thức ngắn, có thể đặt tên cho kết quả điều kiện:

~~~java
boolean qualifiesAsVip =
        vip && subtotalVnd >= VIP_FREE_SHIPPING_FROM_VND;
boolean qualifiesByOrderValue =
        subtotalVnd >= STANDARD_FREE_SHIPPING_FROM_VND;

return qualifiesAsVip || qualifiesByOrderValue
        ? 0
        : STANDARD_SHIPPING_FEE_VND;
~~~

Đoạn này giả định đầu vào đã được kiểm tra trước đó. Việc chọn giữa hai nhánh **if** và biểu thức có tên tùy phong cách dự án, mức độ quen thuộc và khả năng thay đổi của quy tắc. Cả hai đều có thể dễ hiểu khi ý nghĩa được diễn đạt rõ.

## 4. Không phải cứ thêm dòng là cải thiện khả năng đọc

Xét một quy tắc đơn giản:

~~~java
boolean isAdult(int age) {
    return age >= 18;
}
~~~

Viết lại thành nhiều biến trung gian chỉ để “dễ đọc hơn” có thể gây nhiễu:

~~~java
boolean isAdult(int age) {
    int requiredAge = 18;
    boolean ageIsEnough = age >= requiredAge;
    boolean result = ageIsEnough;
    return result;
}
~~~

Ở đây, phần lớn biến trung gian không thêm ý nghĩa. Nếu **18** là chính sách có thể thay đổi, nên cân nhắc một hằng số có tên phù hợp; nếu ngữ cảnh không cần, một phép so sánh đơn giản có thể đã đủ sáng rõ.

Một số mẫu ngắn thường rất dễ đọc:

~~~java
if (customer == null) {
    return;
}

return items.isEmpty();

return Math.max(minimum, requested);
~~~

Mục tiêu là **giữ lại những thông tin giúp người đọc hiểu**, đồng thời bỏ các bước chỉ lặp lại điều đã rõ.

## 5. Điều kiện phức tạp: đặt tên để giảm suy luận

Giả sử một bài viết chỉ được xuất bản khi:

- Đã được duyệt.
- Không bị khóa.
- Có nội dung.
- Người thao tác có quyền xuất bản.

Một điều kiện nén dễ khiến người đọc bỏ sót nhánh:

~~~java
if (doc.isReviewed() && !doc.isLocked()
        && !doc.getBody().isBlank() && user.canPublish()) {
    publish(doc);
}
~~~

Có thể tạo các tên diễn đạt ý nghĩa trước khi dùng:

~~~java
boolean approved = doc.isReviewed();
boolean editable = !doc.isLocked();
boolean hasContent = !doc.getBody().isBlank();
boolean authorized = user.canPublish();

if (approved && editable && hasContent && authorized) {
    publish(doc);
}
~~~

Hai phiên bản giả định **doc**, **user** không null và các lời gọi kiểm tra không có tác động phụ đáng kể. **Lưu ý quan trọng:** Phiên bản đầu dùng **short-circuit evaluation** và có thể không gọi những điều kiện phía sau khi điều kiện trước sai; phiên bản thứ hai luôn đánh giá cả bốn phép kiểm tra. Nếu **getBody()** có thể null hoặc **canPublish()** có tác động phụ/chi phí lớn, thay đổi trên có thể ảnh hưởng hành vi hoặc hiệu năng.

Một cách tách điều kiện mà vẫn giữ thứ tự kiểm tra là đặt tên cho một phương thức có hợp đồng rõ:

~~~java
boolean canBePublished(Document doc, User user) {
    return doc.isReviewed()
            && !doc.isLocked()
            && !doc.getBody().isBlank()
            && user.canPublish();
}
~~~

Phương thức này có thể được dùng tại nhiều vị trí khi **quy tắc xét quyền xuất bản** thực sự là một khái niệm của miền nghiệp vụ. Tuy nhiên, nếu phương thức chỉ được dùng một lần và tên khó tìm hơn điều kiện gốc, tách hàm có thể không tạo thêm giá trị.

**Bài học:** Đặt tên để giảm suy luận, nhưng khi sửa cấu trúc điều kiện phải kiểm tra cả thứ tự đánh giá, ngoại lệ và tác động phụ.

## 6. Đoạn mã ngắn với Stream và lambda

Java Stream có thể giúp diễn đạt gọn gàng một phép biến đổi dữ liệu:

~~~java
List<String> normalizedNames = names.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(name -> !name.isBlank())
        .toList();
~~~

Đoạn mã này ngắn và tương đối dễ đọc nếu người đọc quen với Stream: bỏ phần tử null, cắt khoảng trắng đầu/cuối, loại chuỗi trống và thu kết quả. Với Java 16 trở lên, **Stream.toList()** trả về một danh sách không thể sửa đổi bằng các phương thức thay đổi cấu trúc danh sách; đây là chi tiết hợp đồng cần lưu ý khi thay thế bằng vòng lặp.

Ngược lại, nhồi nhiều phép biến đổi, điều kiện lồng nhau hoặc tác động phụ vào một pipeline có thể khiến việc kiểm tra khó hơn.

Ví dụ về việc **che một tác động nghiệp vụ** trong pipeline:

~~~java
List<String> startedIds = orders.stream()
        .filter(Order::isPending)
        .peek(Order::markProcessing)
        .map(Order::id)
        .toList();
~~~

Ở đây, **markProcessing()** thay đổi trạng thái đơn hàng. Người đọc có thể nhầm pipeline chỉ dùng để tính danh sách ID. Mặt khác, **peek()** được thiết kế chủ yếu để hỗ trợ quan sát/debug, không phải chỗ tin cậy để thực hiện các tác động nghiệp vụ.

Nếu chủ đích là chuyển những đơn hàng đang chờ sang trạng thái xử lý rồi thu ID, viết rõ các thao tác:

~~~java
List<String> startedIds = new ArrayList<>();
for (Order order : orders) {
    if (!order.isPending()) {
        continue;
    }

    order.markProcessing();
    startedIds.add(order.id());
}
~~~

**Order** và các phương thức trong hai ví dụ là kiểu miền nghiệp vụ minh họa. Phiên bản vòng lặp dài hơn nhưng cho thấy rõ **kiểm tra → thay đổi trạng thái → thu kết quả**. Đây chưa phải một giải pháp giao dịch hay đồng thời hoàn chỉnh: nếu một thao tác giữa chừng thất bại, một số đơn hàng có thể đã đổi trạng thái; nghiệp vụ cần cơ chế kiểm soát riêng.

### Khi nào dùng Stream, khi nào dùng vòng lặp?

| Công việc | Lựa chọn thường dễ hiểu |
| --- | --- |
| Lọc, ánh xạ, nhóm dữ liệu bằng các phép biến đổi thuần | Stream với pipeline có tên thao tác rõ |
| Nhiều bước thay đổi trạng thái theo thứ tự | Vòng lặp minh bạch hoặc phương thức nghiệp vụ có tên |
| Có nhiều nhánh rẽ và xử lý lỗi khác nhau | Khối điều khiển rõ ràng, đôi khi tách phương thức |
| Cần giải thích quy tắc đơn giản bằng một biểu thức quen thuộc | Biểu thức ngắn, trực tiếp |

Không nên áp dụng máy móc “Stream luôn tốt hơn vòng lặp” hoặc “vòng lặp luôn dễ đọc hơn Stream”. Hãy dựa vào **ý định được bộc lộ**, **đặc tính của dữ liệu**, **hợp đồng kết quả** và mức độ quen thuộc của đội ngũ.

## 7. Tên hàm và mức trừu tượng phù hợp

Tách phương thức có thể cải thiện khả năng đọc khi mỗi phương thức đại diện cho một bước có ý nghĩa:

~~~java
public Receipt completeOrder(Order order) {
    validateOrder(order);
    reserveInventory(order);
    chargePayment(order);
    return createReceipt(order);
}
~~~

Một người đọc ở cấp quy trình có thể nhìn thấy thứ tự nghiệp vụ mà không cần biết chi tiết cách lưu tồn kho hoặc tính tiền. Tuy nhiên, đoạn mã này **chỉ minh họa cấu trúc dễ đọc**, không tự bảo đảm tính nguyên tử hay khả năng phục hồi: nếu **chargePayment** thất bại sau **reserveInventory**, còn phải có thiết kế xử lý trạng thái đã giữ chỗ.

Ngược lại, phân tách một phép toán đơn giản thành nhiều hàm không có tên mang ý nghĩa sẽ tăng số lần người đọc phải chuyển vị trí:

~~~java
int calculate(int input) {
    return stepOne(input);
}

int stepOne(int value) {
    return stepTwo(value);
}

int stepTwo(int value) {
    return value * 2;
}
~~~

Người đọc phải đi qua ba phương thức chỉ để hiểu phép nhân đôi. Việc thêm các lớp hoặc hàm trung gian nên có lý do như **tách trách nhiệm**, **đặt tên cho quy tắc nghiệp vụ**, **quản lý phụ thuộc** hoặc **khả năng kiểm thử**.

### Tiêu chí để quyết định có tách hay không

Đáng cân nhắc tách hàm khi:

- Có **một khái niệm nghiệp vụ** có thể đặt tên chính xác.
- Đoạn mã dài vì phải xử lý nhiều trách nhiệm khác nhau.
- Một quy tắc cần được kiểm tra hoặc thay đổi độc lập.
- Có nhiều nơi dùng **cùng một quy tắc** và cần tránh sự khác nhau ngoài ý muốn.
- Tên hàm diễn đạt được **điều gì được bảo đảm**, thay vì chỉ mô tả thao tác máy móc.

Không nên tách chỉ vì số dòng vượt một ngưỡng tùy ý. Một phương thức dài với luồng xử lý thẳng, tên rõ, ít trạng thái có thể dễ đọc hơn chuỗi nhiều hàm nhỏ bị phân mảnh.

## 8. Bình luận, định dạng và khả năng giải thích

### 8.1. Bình luận nên bổ sung lý do, không lặp lại cú pháp

Ví dụ bình luận ít giá trị:

~~~java
// Tăng biến count lên một.
count++;
~~~

Ví dụ bình luận có ích:

~~~java
// Đối tác gửi mã đơn không theo thứ tự; chỉ dùng thời điểm xác nhận
// từ hệ thống nội bộ để quyết định bản ghi nào mới hơn.
if (internalConfirmedAt.isAfter(lastConfirmedAt)) {
    updateStatus();
}
~~~

Bình luận thứ hai giải thích **lý do của quyết định** mà mã không tự nói hết. Bình luận có thể sai lệch sau thay đổi, vì vậy cần giữ nó đồng bộ với quy tắc thực tế.

### 8.2. Định dạng giúp nhìn thấy cấu trúc

Khoảng trắng và xuống dòng phù hợp giúp người đọc nhận diện từng nhánh, từng bước và các nhóm thao tác liên quan. Chẳng hạn:

~~~java
if (customer.isVip()
        && subtotalVnd >= VIP_FREE_SHIPPING_FROM_VND) {
    return 0;
}
~~~

Định dạng nhất quán giúp giảm công sức tìm cấu trúc, nhưng **format đẹp không thể sửa một tên mơ hồ hoặc logic sai**. Công cụ formatter nên thống nhất phong cách trình bày để reviewer dành sự chú ý cho ý nghĩa.

### 8.3. Tránh “mật mã” viết tắt

Một biến cục bộ cực ngắn trong vòng lặp đơn giản có thể rõ theo ngữ cảnh:

~~~java
for (int i = 0; i < values.length; i++) {
    sum += values[i];
}
~~~

Nhưng trong logic nghiệp vụ với nhiều trạng thái, **st**, **x1**, **tmp2**, **f** khó truyền đạt ý nghĩa. Khi đặt tên, ưu tiên thuật ngữ được hiểu chung trong miền nghiệp vụ, và bổ sung đơn vị khi thiếu đơn vị dễ gây sai.

## 9. Đánh giá khả năng đọc bằng cách thực hành

Không có một công thức duy nhất cho khả năng đọc. Có thể kiểm tra bằng những câu hỏi cụ thể trong code review:

| Câu hỏi | Tín hiệu tốt | Tín hiệu cần xem lại |
| --- | --- | --- |
| Có thể nói một câu đoạn mã làm gì? | Tên và cấu trúc thể hiện nhiệm vụ | Phải suy ra từ nhiều biểu thức rời |
| Quy tắc nghiệp vụ ở đâu? | Thể hiện trực tiếp hoặc nằm trong hàm có tên rõ | Rải rác, ẩn sau các hàm chung chung |
| Trường hợp biên có rõ? | Ngưỡng, kiểm tra null, lỗi được thể hiện | Phụ thuộc vào giả định ngầm |
| Có cần nhẩm nhiều điều kiện cùng lúc? | Nhánh được tổ chức dễ theo dõi | Toán tử lồng sâu, phủ định kép |
| Có tác động phụ? | Gọi tên rõ và theo thứ tự dễ nhận thấy | Nằm trong getter, lambda hoặc pipeline |
| Nếu yêu cầu đổi, sửa ở đâu? | Quy tắc tập trung, kiểm thử liên quan | Nhiều chỗ có “mã giống mà khác” |

Cách thử đơn giản trong review là yêu cầu một người **không viết đoạn mã** giải thích ba tình huống: đầu vào bình thường, đầu vào sát giá trị biên và đầu vào gây lỗi. Nếu người đọc không thể diễn đạt điều gì xảy ra mà phải chạy thử từng nhánh, đoạn mã có thể cần đặt lại tên, tách quy tắc hoặc làm rõ hợp đồng.

Một hướng cải thiện thực dụng:

1. **Ghi rõ hành vi và quy tắc cần giữ:** Đầu vào, đầu ra, ngoại lệ và tác động phụ.
2. **Tìm nơi khó suy luận:** Biểu thức nhiều ý, biến thiếu nghĩa, nhánh lồng sâu hoặc trách nhiệm trộn lẫn.
3. **Chọn thay đổi nhỏ có mục đích:** Đặt tên, đưa hằng số nghiệp vụ ra riêng, dùng guard clause hoặc tách một khái niệm rõ ràng.
4. **Đọc lại ở cấp người mới:** Có còn phải liên tục nhảy qua các hàm chỉ để hiểu một thao tác đơn giản không?
5. **Kiểm tra hành vi:** Chạy kiểm thử liên quan, đặc biệt giá trị biên, ngoại lệ, tác động phụ và thứ tự đánh giá.
6. **Nhìn lại chi phí bảo trì:** Mã mới có giúp xác định đúng nơi thay đổi khi yêu cầu nghiệp vụ đổi không?

Các chỉ số như số dòng, độ phức tạp điều khiển hoặc số cảnh báo phân tích tĩnh có thể gợi ý nơi cần xem xét. Chúng **không thay thế** khả năng giải thích đúng mã và năng lực thay đổi mà không gây hồi quy.

## 10. Những hiểu nhầm thường gặp

**“Càng ít dòng càng sạch.”** Rút ngắn có thể giúp khi loại bỏ lặp thừa, nhưng có thể làm tăng số ý phải giữ trong đầu nếu gộp nhiều quy tắc vào một biểu thức.

**“Càng nhiều hàm nhỏ càng dễ đọc.”** Nếu hàm chỉ chuyển tiếp hoặc mang tên chung chung, người đọc phải mở quá nhiều nơi để theo dõi một luồng đơn giản.

**“Mọi biến trung gian đều là thừa.”** Biến đặt tên cho một khái niệm nghiệp vụ quan trọng có thể giảm suy luận. Biến chỉ chuyển một giá trị sang tên khác không thêm ý nghĩa thì có thể bỏ.

**“Không cần comment vì mã tự giải thích hoàn toàn.”** Mã nên biểu đạt điều nó làm; bình luận vẫn cần thiết để ghi lại lý do, ràng buộc bất thường hoặc quyết định thiết kế mà cú pháp không thể hiện hết.

**“Dùng Stream luôn đẹp hơn vòng lặp.”** Stream thích hợp cho biến đổi dữ liệu rõ ràng; các tác động phụ và nhánh nghiệp vụ phức tạp có thể dễ hiểu hơn khi viết tuần tự.

**“Dễ đọc thì chắc chắn chạy đúng.”** Tên tốt và cấu trúc rõ giúp phát hiện lỗi, nhưng không thay thế kiểm thử và xem xét hợp đồng. Một điều kiện **>** thay vì **>=** vẫn có thể sai dù được đặt tên đẹp.

**“Đổi cách viết mà kết quả cuối giống nhau là đủ.”** Khi refactor, cần lưu ý thứ tự đánh giá, ngoại lệ, mutability của dữ liệu trả về, chi phí I/O và tác động phụ; đây có thể là phần hợp đồng hành vi.

## 11. Tình huống luyện tập

Một hệ thống phân loại yêu cầu hỗ trợ có mã sau:

~~~java
String route(Ticket t) {
    return t.isCritical() || t.getAgeHours() > 24 && !t.isResolved()
            ? "PRIORITY" : "NORMAL";
}
~~~

Quy tắc nghiệp vụ được mô tả: yêu cầu **nghiêm trọng** luôn có ưu tiên cao; yêu cầu **chưa xử lý** và **đã quá 24 giờ** cũng được ưu tiên cao. Các yêu cầu còn lại là bình thường.

Hãy thử trả lời:

1. Mã đang có bao nhiêu điều kiện tạo ra ưu tiên cao? Toán tử nào được đánh giá trước?
2. Trường hợp tuổi yêu cầu **đúng 24 giờ** có được ưu tiên không? Tại sao?
3. Tên **t**, **route**, chuỗi **PRIORITY** và **NORMAL** có đủ thông tin trong phạm vi hệ thống thật hay chưa?
4. Có thể viết lại để quy tắc dễ đọc hơn nhưng không thay đổi hành vi như thế nào?
5. Nếu hệ thống yêu cầu tuổi từ **24 giờ trở lên**, thay đổi nào là **sửa quy tắc** thay vì chỉ thay đổi khả năng đọc?

**Một cách viết rõ ràng hơn nhưng giữ nguyên điều kiện hiện tại:**

~~~java
String classifyTicket(Ticket ticket) {
    if (ticket.isCritical()) {
        return "PRIORITY";
    }

    boolean isOverdue = ticket.getAgeHours() > 24;
    if (!ticket.isResolved() && isOverdue) {
        return "PRIORITY";
    }

    return "NORMAL";
}
~~~

Ví dụ giả định đối tượng **Ticket** và các phương thức đọc dữ liệu đều hợp lệ, ổn định và không có tác động phụ. Phiên bản tách nhánh làm rõ hai lý do được ưu tiên và vẫn giữ trường hợp **đúng 24 giờ** là bình thường. Nếu chính sách mới yêu cầu từ 24 giờ, phải chủ động đổi điều kiện thành **>= 24** và cập nhật kiểm thử; đó là **thay đổi hành vi**, không chỉ chỉnh cách trình bày.

Cũng cần để ý rằng ở phiên bản ban đầu, biểu thức **getAgeHours()** được gọi trước **isResolved()** khi **isCritical()** là false; ở phiên bản minh họa, thứ tự gọi vẫn tương ứng. Khi thay đổi thứ tự điều kiện để tiện đọc, cần bảo đảm những phép kiểm tra có thể ném lỗi hoặc có tác động phụ vẫn được xử lý đúng hợp đồng.

## 12. Ghi nhớ

- **Mã ngắn** mô tả số lượng ký tự hoặc dòng; **mã dễ hiểu** cho phép người đọc nhanh chóng nắm đúng ý định, nhánh xử lý và tác động.
- Độ ngắn có ích khi loại bỏ thông tin thừa. Nó gây hại khi làm mất tên gọi, giấu quy tắc hoặc nén nhiều quyết định vào một biểu thức khó theo dõi.
- Khả năng đọc thường cải thiện nhờ **tên rõ nghĩa**, **điều kiện dễ theo dõi**, **trách nhiệm hợp lý** và **hợp đồng hành vi cụ thể**.
- Tránh cả hai cực đoan: viết mọi thứ thành một dòng và tách một ý đơn giản thành hàng loạt lớp, hàm, biến trung gian.
- Khi chỉnh mã để dễ đọc, cần **kiểm chứng rằng hành vi vẫn đúng**, kể cả ở giá trị biên, ngoại lệ, thứ tự đánh giá và tác động phụ.
