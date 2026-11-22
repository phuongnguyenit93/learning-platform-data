# Luồng điều khiển và các đường đi cần được xét

Một phương thức có thể trả về kết quả đúng trong trường hợp phổ biến nhưng vẫn sai khi đầu vào trống, giá trị nằm sát ngưỡng, có ngoại lệ hoặc nhiều điều kiện xảy ra cùng lúc. Muốn đánh giá **tính đúng đắn (correctness)**, chúng ta cần xem chương trình thực sự đi qua những nhánh nào và kết quả có phù hợp với yêu cầu ở từng nhánh hay không.

Trong kiến thức nền tảng về chất lượng mã, **luồng điều khiển (control flow)** cho biết thứ tự thực thi các câu lệnh. Phân tích luồng điều khiển giúp phát hiện đường đi bị bỏ sót, điều kiện mâu thuẫn, nhánh không thể tới và trường hợp kết thúc bất thường. Đây là cơ sở để thiết kế kiểm thử có ý nghĩa, nhưng số đường đi đã kiểm thử không tự nó bảo đảm chương trình đúng.

## 1. Phân biệt điều kiện, nhánh và đường đi

Xét đoạn Java:

~~~java
if (amount < 0) {
    throw new IllegalArgumentException("Invalid amount");
}

if (amount == 0) {
    return "EMPTY";
}

return "POSITIVE";
~~~

Các khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa | Minh họa |
| --- | --- | --- |
| **Điều kiện (condition)** | Biểu thức có kết quả true/false và ảnh hưởng quyết định thực thi. | amount < 0 |
| **Nhánh (branch)** | Hướng thực thi sau một quyết định. | Nhánh true hoặc false của câu lệnh if. |
| **Đường đi (path)** | Chuỗi bước/nhánh mà một lần chạy thực sự đi qua từ điểm bắt đầu đến điểm kết thúc quan sát. | amount = 0: bỏ qua ngoại lệ, trả về EMPTY. |
| **Điểm kết thúc** | Nơi luồng hiện tại dừng hoặc chuyển quyền điều khiển ra ngoài. | return, throw; với vòng lặp có thể có break để ra khỏi vòng lặp. |
| **Đường đi khả thi (feasible path)** | Có ít nhất một đầu vào/trạng thái hợp lệ khiến luồng chạy theo đường đó. | amount = -1 khiến nhánh throw được thực hiện. |

Ở ví dụ trên, ba nhóm đầu vào tương ứng ba đường đi chính: **âm** (ném ngoại lệ), **bằng 0** (trả EMPTY) và **dương** (trả POSITIVE).

Không phải mọi tổ hợp nhánh tưởng tượng đều khả thi. Chẳng hạn, trong một lần chạy, **amount < 0** và **amount == 0** không thể đồng thời đúng với cùng giá trị amount. Khi vẽ hoặc đếm đường đi, cần xét tính khả thi thay vì nhân máy móc số nhánh.

## 2. Vì sao chỉ kiểm tra “đường đi thành công” là chưa đủ?

Giả sử người viết chỉ thử amount = 10 và nhận POSITIVE. Thử nghiệm ấy xác nhận một trường hợp, nhưng không nói gì về:

- Giá trị **âm** có bị từ chối hay không.
- Giá trị **0** có được phân loại chính xác hay không.
- Lời gọi có **ném đúng loại ngoại lệ** khi dữ liệu không hợp lệ hay không.
- Nếu sau này thêm một điều kiện ở đầu phương thức, đường đi cũ có bị chặn nhầm hay không.

**Tính đúng đắn** đòi hỏi so sánh hành vi thực tế với **đặc tả**: điều kiện hợp lệ, kết quả mong đợi, trạng thái được thay đổi và những trường hợp phải từ chối. Kiểm thử chạy qua được một nhánh nhưng không có khẳng định đúng về đầu ra vẫn có thể bỏ qua lỗi logic.

## 3. Ví dụ xuyên suốt: tính phí vận chuyển

Giả sử yêu cầu nghiệp vụ được chốt như sau:

1. Tổng giá trị hàng (subtotalVnd) **không được âm**; âm thì báo lỗi.
2. Nếu tổng giá trị hàng từ **500.000 VND** trở lên, **phí vận chuyển cơ bản** bằng 0; nếu thấp hơn, phí cơ bản là **30.000 VND**.
3. Giao nhanh (express) cộng **20.000 VND**.
4. Giao vùng xa (remoteArea) cộng **15.000 VND**.
5. Phí cộng thêm vẫn được tính khi phí cơ bản bằng 0.

Một cách triển khai Java có thể đọc được từng quyết định:

~~~java
public final class ShippingFeeCalculator {
    private static final int FREE_BASE_FEE_THRESHOLD = 500_000;
    private static final int BASE_FEE = 30_000;
    private static final int EXPRESS_SURCHARGE = 20_000;
    private static final int REMOTE_SURCHARGE = 15_000;

    private ShippingFeeCalculator() {}

    public static int calculate(
            int subtotalVnd,
            boolean express,
            boolean remoteArea) {

        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }

        int fee = subtotalVnd >= FREE_BASE_FEE_THRESHOLD ? 0 : BASE_FEE;

        if (express) {
            fee += EXPRESS_SURCHARGE;
        }

        if (remoteArea) {
            fee += REMOTE_SURCHARGE;
        }

        return fee;
    }
}
~~~

Ví dụ dùng kiểu **int** để tập trung vào luồng điều khiển, với phí cố định nhỏ và đầu vào biểu diễn VND nguyên. Trong bài toán tiền tệ thực tế phải cân nhắc kiểu dữ liệu, giới hạn giá trị, làm tròn và cách lưu tiền theo yêu cầu hệ thống.

### Sơ đồ luồng điều khiển

~~~mermaid
flowchart TD
    A([Bắt đầu]) --> B{"subtotalVnd < 0?"}
    B -- Có --> X["Ném IllegalArgumentException"]
    B -- Không --> C{"subtotalVnd >= 500000?"}
    C -- Có --> D["fee = 0"]
    C -- Không --> E["fee = 30000"]
    D --> F{"express?"}
    E --> F
    F -- Có --> G["fee += 20000"]
    F -- Không --> H{"remoteArea?"}
    G --> H
    H -- Có --> I["fee += 15000"]
    H -- Không --> J([return fee])
    I --> J
~~~

Từ sơ đồ có thể thấy rõ hai loại kết thúc:

- **Đầu vào âm:** dừng bằng ngoại lệ; không được tính phí.
- **Đầu vào không âm:** lần lượt quyết định phí cơ bản, phí giao nhanh, phí vùng xa rồi trả về.

### Ma trận đường đi

Với đầu vào không âm, ba quyết định độc lập về **ngưỡng phí cơ bản, giao nhanh và vùng xa** tạo thành **8 tổ hợp khả thi**. Nhóm đầu vào âm tạo thêm một đường đi kết thúc bằng ngoại lệ.

| Trường hợp | subtotalVnd | express | remoteArea | Kết quả mong đợi |
| --- | ---: | :---: | :---: | ---: |
| C1 | 100.000 | false | false | 30.000 |
| C2 | 100.000 | true | false | 50.000 |
| C3 | 100.000 | false | true | 45.000 |
| C4 | 100.000 | true | true | 65.000 |
| C5 | 500.000 | false | false | 0 |
| C6 | 500.000 | true | false | 20.000 |
| C7 | 500.000 | false | true | 15.000 |
| C8 | 500.000 | true | true | 35.000 |
| C9 | -1 | Bất kỳ | Bất kỳ | IllegalArgumentException |

**Điểm dễ sai:** người triển khai có thể viết nhầm “đủ 500.000 VND thì phí cuối cùng bằng 0”, khiến phụ phí giao nhanh và vùng xa bị mất. Trong khi đó, yêu cầu chỉ miễn **phí cơ bản**. Muốn phát hiện lỗi này, cần kiểm thử các tổ hợp **C6–C8**, ngoài trường hợp miễn phí thông thường C5.

### Kiểm tra ranh giới của điều kiện

Ma trận trên phân biệt các nhánh, nhưng vẫn nên kiểm tra đúng **điểm chuyển nhánh**:

- 499.999 VND: phí cơ bản còn 30.000.
- 500.000 VND: phí cơ bản bằng 0.
- 500.001 VND: phí cơ bản vẫn bằng 0.
- -1 VND: bị từ chối; 0 VND: hợp lệ và có phí cơ bản 30.000.

Lỗi dùng **>** thay cho **>=** chỉ xuất hiện ở đúng ngưỡng 500.000 VND. Đây là lý do phân tích luồng điều khiển phải kết hợp **phân lớp tương đương** với **kiểm thử giá trị biên**.

## 4. Chuyển ma trận thành kiểm thử có khẳng định

Với JUnit 5, có thể kiểm tra các nhóm đường đi điển hình như sau:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {
    @Test
    void feeBelowThresholdWithBothSurcharges() {
        assertEquals(65_000,
                ShippingFeeCalculator.calculate(100_000, true, true));
    }

    @Test
    void thresholdOnlyWaivesBaseFee() {
        assertEquals(35_000,
                ShippingFeeCalculator.calculate(500_000, true, true));
    }

    @Test
    void justBelowThresholdStillPaysBaseFee() {
        assertEquals(30_000,
                ShippingFeeCalculator.calculate(499_999, false, false));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeeCalculator.calculate(-1, false, false));
    }
}
~~~

Đoạn kiểm thử minh họa những khẳng định quan trọng; để kiểm tra **đầy đủ 9 dòng ma trận**, cần thêm các ca tương ứng hoặc dùng kiểm thử tham số hóa. Không nên gọi bốn ca mẫu này là “đã kiểm tra hết mọi đường đi”.

Khi kiểm tra tính đúng đắn, cần xác minh cả **đầu ra** lẫn **tác động phụ** nếu có: dữ liệu được ghi, số lần gọi dịch vụ bên ngoài, trạng thái giao dịch, sự kiện phát đi và việc không thay đổi dữ liệu ở đường đi bị từ chối.

## 5. Các cấu trúc luồng điều khiển thường bị bỏ sót

### 5.1. If/else, guard clause và return sớm

~~~java
String classify(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    }
    if (score >= 80) {
        return "HIGH";
    }
    return "NORMAL";
}
~~~

Các đường đi cần xem gồm: score ngoài miền hợp lệ, score hợp lệ từ 80 trở lên, và score hợp lệ dưới 80. **Return sớm** giúp làm rõ điều kiện chặn, nhưng cũng dễ khiến người đọc quên rằng các câu lệnh phía sau sẽ **không chạy** trong nhánh đó.

Một quy tắc quan trọng: không suy đoán đặc tả chỉ từ cấu trúc hiện có. Nếu yêu cầu nói score âm phải ném ngoại lệ thay vì trả INVALID, việc chạy đúng đường đi nhưng trả INVALID vẫn là lỗi.

### 5.2. Điều kiện ghép và short-circuit

Trong Java, **&&** và **||** đánh giá từ trái sang phải và có thể **không đánh giá toán hạng bên phải**.

~~~java
boolean canNotify(User user) {
    return user != null
            && user.isActive()
            && user.hasNotificationConsent();
}
~~~

Cần xem tối thiểu các tình huống:

| Trạng thái | Biểu thức nào được gọi? | Kết quả |
| --- | --- | --- |
| user = null | Không gọi phương thức nào trên user | false |
| user tồn tại nhưng không active | Gọi isActive; bỏ qua hasNotificationConsent | false |
| active nhưng chưa đồng ý | Gọi cả hai phương thức | false |
| active và đã đồng ý | Gọi cả hai phương thức | true |

Nếu chuyển thứ tự thành **user.isActive() && user != null**, đầu vào null sẽ gây **NullPointerException**. Vì vậy, tính đúng đắn không chỉ phụ thuộc vào kết quả Boolean dự kiến mà còn vào **thứ tự đánh giá** và các lệnh có thể gây lỗi hoặc tác động phụ.

Đối với điều kiện ghép phức tạp, kiểm tra cả ảnh hưởng riêng của từng điều kiện. Ví dụ, chỉ thử “mọi điều kiện đều đúng” và “mọi điều kiện đều sai” sẽ không chứng minh rằng từng điều kiện thực sự hoạt động đúng.

### 5.3. Switch và các trường hợp chưa liệt kê

Một luồng dùng **switch** có thể có nhiều nhánh theo trạng thái (NEW, PAID, CANCELLED...). Cần xác định:

- Tất cả trạng thái **hợp lệ** đã có cách xử lý chưa?
- Trạng thái **không hỗ trợ** được từ chối hay bị hiểu nhầm thành trạng thái khác?
- Giá trị **null** có thể xuất hiện không; nếu có, chương trình được yêu cầu xử lý ra sao?
- Với **switch statement** dùng cú pháp case truyền thống, có vô tình rơi sang nhánh sau vì thiếu break không?

Java có nhiều dạng switch tùy phiên bản. Không phải switch nào cũng cần default; điều quan trọng là **xử lý đầy đủ miền đầu vào theo đặc tả**, đặc biệt khi enum hoặc trạng thái được mở rộng.

### 5.4. Vòng lặp

Vòng lặp có thể tạo ra số đường đi rất lớn, thậm chí vô hạn nếu không ràng buộc số lần lặp. Một bộ trường hợp tối thiểu hữu ích thường là:

| Đường đi cần xem | Câu hỏi |
| --- | --- |
| **0 lần lặp** | Danh sách rỗng có được xử lý đúng không? |
| **1 lần lặp** | Một phần tử có tạo kết quả chính xác không? |
| **Nhiều lần lặp** | Kết quả có được tích lũy đúng, không lặp/thất thoát dữ liệu? |
| **Dừng sớm (break/return)** | Trường hợp tìm thấy kết quả giữa chừng có làm bỏ qua công việc bắt buộc không? |
| **Bỏ qua lượt (continue)** | Phần tử không hợp lệ có bị loại đúng, không làm sai trạng thái? |
| **Điều kiện biên/kết thúc** | Có lỗi lệch một đơn vị, không kết thúc, hoặc truy cập vượt chỉ số không? |

Ví dụ đếm phần tử có giá trị dương: kiểm tra danh sách rỗng, một giá trị dương, một giá trị không dương, và danh sách trộn nhiều giá trị. Nếu bài toán có giới hạn số phần tử hoặc khả năng tràn số, cần bổ sung các trường hợp ấy theo đặc tả.

### 5.5. Ngoại lệ và nhánh dọn dẹp tài nguyên

~~~java
try (var stream = openInputStream()) {
    return parse(stream);
} catch (IOException ex) {
    return defaultValue();
}
~~~

Cần phân biệt ít nhất: mở thành công và parse thành công; mở thất bại với IOException; lỗi đọc trong parse dưới dạng IOException; lỗi khác không được catch này xử lý. **try-with-resources** cũng tham gia đóng tài nguyên khi khối try kết thúc, kể cả lúc ném ngoại lệ; trong một số tình huống ngoại lệ khi đóng được ghi nhận là **suppressed exception**.

Nếu **parse** có thể ném một ngoại lệ không thuộc IOException, nhánh catch trên không bắt ngoại lệ ấy. Việc có catch không có nghĩa mọi lỗi đều được phục hồi. Khi kiểm thử luồng ngoại lệ, xác minh **loại lỗi**, **hành vi phục hồi**, **tính toàn vẹn dữ liệu** và **tài nguyên được giải phóng**.

### 5.6. Trạng thái và thứ tự sự kiện

Đường đi thực tế có thể phụ thuộc không chỉ vào tham số của một lời gọi mà còn vào **trạng thái trước đó**:

- Gọi hoàn tiền khi đơn chưa thanh toán.
- Gọi hoàn tiền lần thứ hai sau khi đã hoàn hết.
- Hai yêu cầu cập nhật cùng bản ghi cùng lúc.
- Một thao tác thành công nhưng ghi nhận kết quả phản hồi bị gián đoạn, rồi phía gọi thử lại.

Đây là những tình huống cần kiểm tra trạng thái, thứ tự và tính bất biến, không chỉ đếm nhánh if trong một phương thức. Với hệ thống nhiều luồng hoặc nhiều dịch vụ, các lịch thực thi có thể thay đổi kết quả ngay cả khi đầu vào từng lời gọi giống nhau.

## 6. Coverage giúp quan sát điều gì, và giới hạn ở đâu?

Các chỉ số thường gặp:

| Chỉ số | Diễn giải | Điều không thể kết luận từ chỉ số |
| --- | --- | --- |
| **Statement/line coverage** | Bao nhiêu câu lệnh hoặc dòng thực thi được chạy ít nhất một lần (theo cách công cụ đo). | Một dòng đã chạy không đồng nghĩa các kết quả đều đúng. |
| **Branch coverage** | Bao nhiêu hướng của các quyết định đã được thực thi. | Chưa bảo đảm mọi tổ hợp nhánh được thử. |
| **Condition coverage** | Các điều kiện con nhận true và false như thế nào (tùy công cụ/tiêu chí). | Chưa chắc từng điều kiện ảnh hưởng độc lập đến quyết định cuối. |
| **Path coverage** | Bao nhiêu đường đi thực thi khác nhau đã được thử. | Có thể không khả thi để đạt toàn bộ do vòng lặp, dữ liệu hoặc số đường đi tăng rất nhanh. |

Chẳng hạn, trong hàm tính phí, hai ca **(100.000, true, true)** và **(500.000, false, false)** đi qua cả true lẫn false của từng quyết định trong phần đầu vào hợp lệ. Tuy nhiên, hai ca đó **không đi qua sáu tổ hợp hợp lệ còn lại**. Thêm ca giá trị âm mới đi qua nhánh ngoại lệ của điều kiện đầu tiên.

Điều đó minh họa: **branch coverage cao không đồng nghĩa path coverage cao**; và cả hai vẫn không chứng minh đúng đặc tả. Chỉ số là tín hiệu để phát hiện vùng chưa được thực thi, còn **assertion, dữ liệu kiểm thử, đặc tả và phân tích tác động** mới cho biết kiểm thử có ý nghĩa hay không.

Một số đường đi do tổ hợp nhánh tạo ra **không thể xảy ra**. Một số khác có thể xảy ra nhưng rất đắt để tạo môi trường. Vì thế, mục tiêu thực tế là lựa chọn tập kiểm thử **đại diện, kiểm chứng các bất biến cốt lõi, ưu tiên biên và nhánh rủi ro cao**, rồi dùng coverage làm bằng chứng bổ trợ.

## 7. Quy trình phân tích các đường đi cần được xét

1. **Lấy yêu cầu làm chuẩn.** Ghi rõ miền đầu vào hợp lệ, đầu ra, ngoại lệ, thay đổi trạng thái và những điều luôn phải đúng.
2. **Đánh dấu điểm rẽ.** Tìm if/else, switch, điều kiện ghép, return/throw, vòng lặp, break/continue, catch/finally và lời gọi có thể thất bại.
3. **Vẽ hoặc mô tả luồng.** Với phương thức phức tạp, dùng sơ đồ luồng điều khiển để thấy nơi các nhánh tách và nhập; lưu ý đường đi có thể phụ thuộc trạng thái hoặc lời gọi khác.
4. **Loại tổ hợp bất khả thi.** Xét ràng buộc dữ liệu và thứ tự đánh giá để tránh lập các ca kiểm thử không thể xảy ra.
5. **Lập ma trận kiểm thử.** Chọn đường đi thường gặp, đầu vào không hợp lệ, điều kiện biên, tổ hợp nhánh quan trọng, ngoại lệ và trường hợp khôi phục.
6. **Viết kết quả mong đợi trước khi chạy.** Dựa vào đặc tả để xác định giá trị trả về, ngoại lệ và trạng thái sau xử lý; tránh dùng chính thuật toán đang kiểm tra làm nguồn duy nhất cho kết quả mong đợi.
7. **Chạy và đánh giá bằng chứng.** Kiểm tra assertion, xem coverage để phát hiện phần bỏ sót, rồi bổ sung ca khi thấy đường đi rủi ro chưa được kiểm chứng.
8. **Xem lại khi thay đổi mã hoặc yêu cầu.** Thêm nhánh, thay ngưỡng, đổi thứ tự điều kiện hoặc đưa vào trạng thái mới đều có thể tạo đường đi cần kiểm tra thêm.

Không nhất thiết lập bảng mọi đường đi cho một hàm rất nhỏ và ít rủi ro. Với vùng mã liên quan thanh toán, quyền truy cập, dữ liệu quan trọng hoặc an toàn, việc ghi lại bất biến và ca lỗi giúp review và bảo trì đáng tin cậy hơn.

## 8. Bài tập tự kiểm tra

Xét phương thức:

~~~java
static String decide(int stock, boolean priority) {
    if (stock < 0) {
        throw new IllegalArgumentException("Negative stock");
    }
    if (stock == 0) {
        return "OUT_OF_STOCK";
    }
    if (stock < 3 && !priority) {
        return "WAIT";
    }
    return "READY";
}
~~~

**Câu hỏi 1:** Xác định các nhóm đầu vào tạo ra kết quả khác nhau.

**Câu hỏi 2:** Nếu chỉ thử stock = 5, priority = true và stock = 0, priority = false, còn nhánh quan trọng nào chưa được xét?

**Câu hỏi 3:** Vì sao cần thử cả stock = 2, priority = false và stock = 2, priority = true?

**Gợi ý đáp án:**

- stock âm → ném ngoại lệ; stock bằng 0 → OUT_OF_STOCK; stock bằng 1 hoặc 2 và không ưu tiên → WAIT; stock dương còn lại → READY.
- Thiếu đường đi ném ngoại lệ và đường đi WAIT; cũng cần kiểm tra ranh giới **2/3** của điều kiện stock < 3.
- Với stock = 2, thay đổi priority làm kết quả đổi từ WAIT sang READY; hai ca giúp chứng minh điều kiện ưu tiên thực sự chi phối quyết định. Cần nhớ biểu thức !priority chỉ được đánh giá khi stock < 3 đúng.

---

**Ghi nhớ:** Xét luồng điều khiển là cách hỏi “chương trình có thể đi những đâu, và mỗi nơi cần đúng điều gì?”. Hãy bao phủ các trường hợp thành công, từ chối, giá trị biên, tổ hợp điều kiện, vòng lặp và ngoại lệ theo rủi ro của chức năng. Độ bao phủ mã hỗ trợ tìm chỗ thiếu kiểm tra, còn tính đúng đắn phải được xác nhận bằng **hành vi mong đợi theo đặc tả**.
