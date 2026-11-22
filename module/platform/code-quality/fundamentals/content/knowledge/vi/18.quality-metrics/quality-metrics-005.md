# Độ bao phủ và chất lượng khẳng định trong kiểm thử

Một dự án có thể công bố **95% code coverage** mà vẫn bỏ lọt lỗi tính tiền ở đúng ngưỡng miễn phí vận chuyển. Một bộ kiểm thử có thể chạy qua hầu hết các dòng mã nhưng chỉ khẳng định “kết quả không phải `null`”. Ngược lại, vài kiểm thử được chọn cẩn thận có thể phát hiện những lỗi quan trọng mà hàng trăm test hình thức không bắt được.

Trong chương **Chỉ số chất lượng** của **CODE_QUALITY_FUNDAMENTALS**, bài học này giải thích cách đọc **độ bao phủ kiểm thử** (*test coverage*) cùng với **chất lượng khẳng định** (*assertion quality*). Chủ đề phục vụ mục tiêu của module: hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Coverage cho biết phần nào của chương trình đã được thực thi theo một mô hình đo; assertion mới giúp kiểm tra kết quả được quan sát có đúng theo hợp đồng hay không.

**Luận điểm chính:** *Có chạy qua một dòng mã không đồng nghĩa có kiểm chứng được hành vi của dòng mã ấy.*

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **line, instruction, branch, condition và path coverage** cùng giới hạn của từng cách đo.
2. Giải thích vì sao coverage cao chưa chứng minh chất lượng bộ test cao hoặc chương trình đúng.
3. Viết assertion kiểm chứng **kết quả, ngoại lệ, bất biến, tác dụng phụ** và các trường hợp biên theo hợp đồng.
4. Nhận diện test có assertion yếu, assertion trùng với implementation hoặc không kiểm tra được lỗi mà tên test tuyên bố.
5. Hiểu **mutation testing**, cách diễn giải mutation score và những vấn đề như equivalent mutant.
6. Kết hợp coverage report, kiểm tra rủi ro và chất lượng assertion thành quy trình cải thiện kiểm thử trong dự án Java.

## 1. Coverage đo điều gì?

**Code coverage** là các chỉ số mô tả phần mã đã được thực thi bởi một tập kiểm thử, theo cách công cụ định nghĩa “phần mã”. Một tỷ lệ đơn giản có dạng:

```text
coverage = số đơn vị được bao phủ / tổng số đơn vị hợp lệ để đo × 100%
```

“Đơn vị” ở đây có thể là câu lệnh, dòng mã, instruction của bytecode, nhánh hoặc phần tử khác. Vì vậy **hai báo cáo cùng ghi 90%** nhưng sử dụng các loại coverage khác nhau **không nhất thiết tương đương**.

| Chỉ số | Câu hỏi được trả lời | Không thể suy ra trực tiếp |
| --- | --- | --- |
| **Line coverage** | Bao nhiêu dòng mã thực thi được đã có lần được chạy? | Mọi đường đi qua dòng đó đã đúng. |
| **Statement coverage** | Bao nhiêu câu lệnh đã được thực thi? | Mọi quyết định ở các điều kiện đã được thử. |
| **Instruction coverage** | Bao nhiêu instruction, thường là bytecode, đã được thực thi? | Hợp đồng nghiệp vụ được đáp ứng. |
| **Branch coverage** | Những nhánh của điểm quyết định đã được đi qua đến đâu? | Tất cả tổ hợp điều kiện và tất cả đường đi. |
| **Condition coverage** | Mỗi điều kiện con có nhận cả giá trị true và false không, theo mô hình đo? | Mỗi điều kiện con độc lập tác động đến quyết định cuối. |
| **Path coverage** | Những đường đi thực thi khác nhau đã được thử? | Tất cả đường đi trong chương trình có vòng lặp đều đã được thử. |
| **Method/function coverage** | Những phương thức nào từng được gọi? | Mọi trường hợp của từng phương thức đã đúng. |

Các tên trên thường xuất hiện trong tài liệu kiểm thử, nhưng cách tính cụ thể phụ thuộc công cụ. Chẳng hạn **JaCoCo** phân tích bytecode Java và báo instruction, branch, line, method/class cùng các chỉ số khác. JaCoCo không tự biến mỗi tổ hợp điều kiện Boolean thành một chỉ số MC/DC hay path coverage đầy đủ.

### Ví dụ hai kiểu kiểm tra rất khác nhau

```java
int result = calculator.add(2, 3);
assertTrue(result >= 0);
```

Assertion này sẽ đi qua lời gọi `add(2, 3)`, nhưng **không phát hiện** kết quả sai là `4` hay `100`. So với:

```java
assertEquals(5, calculator.add(2, 3));
```

Cả hai đều có thể tạo số liệu coverage tương tự cho phương thức `add`. Chỉ assertion thứ hai kiểm chứng kết quả chính xác của ví dụ. Do đó **coverage thuộc về đường chạy; mức mạnh của assertion thuộc về điều kiện mà test thực sự bác bỏ được**.

## 2. Ví dụ xuyên suốt: chính sách phí vận chuyển

Giả sử một ứng dụng có quy tắc minh họa như sau:

- Tổng tiền giỏ hàng `basketMinor` phải không âm.
- Từ **500.000** đơn vị tiền trở lên được miễn phí giao hàng.
- Dưới ngưỡng đó, phí thông thường là **30.000**.
- Với giao hàng nhanh `express=true` và dưới ngưỡng, phí là **55.000**.
- Miễn phí theo ngưỡng áp dụng cho cả đơn hàng thông thường lẫn giao hàng nhanh.

Đây là **hợp đồng giả định phục vụ bài học**, không phải biểu phí thật. Tên `Minor` cho biết số tiền lưu theo đơn vị nhỏ nhất đã quy định trong hệ thống; mã ví dụ không giải quyết bài toán nhiều loại tiền tệ hoặc quy đổi.

**`ShippingFeePolicy.java`:**

```java
public final class ShippingFeePolicy {
    private static final long FREE_FROM = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_FEE = 55_000L;

    public long feeMinor(long basketMinor, boolean express) {
        if (basketMinor < 0) {
            throw new IllegalArgumentException(
                    "Basket amount must be non-negative");
        }

        if (basketMinor >= FREE_FROM) {
            return 0L;
        }

        return express ? EXPRESS_FEE : STANDARD_FEE;
    }
}
```

Hàm này có ba quyết định đáng chú ý: **số âm hay không**, **đạt ngưỡng miễn phí hay không**, và **giao nhanh hay không** khi chưa đạt ngưỡng. Các điều kiện ấy xác định những lớp tình huống cần được kiểm chứng.

### Chỉ có một test rất dễ gây hiểu nhầm

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class WeakShippingTest {
    @Test
    void feeLooksValid() {
        ShippingFeePolicy policy = new ShippingFeePolicy();
        long fee = policy.feeMinor(100_000L, false);
        assertTrue(fee >= 0L);
    }
}
```

Test gọi được một đường đi thực tế, nên tạo ra một phần line/instruction coverage. Tuy nhiên nó vẫn xanh nếu phí giao thường bị tính thành 1, 50.000 hoặc 100.000. Nó cũng không thử giao nhanh, đơn hàng miễn phí và đầu vào âm.

Một test tốt hơn cần lấy kỳ vọng từ **bảng quy tắc nghiệp vụ**, không lấy từ kết quả tình cờ trả về trong lần chạy đầu.

## 3. Đọc line coverage và branch coverage cùng nhau

Từ mã `ShippingFeePolicy`, một bộ ca kiểm thử tối thiểu nên bao gồm:

| Trường hợp | `basketMinor` | `express` | Kết quả kỳ vọng | Ý nghĩa |
| --- | ---: | --- | ---: | --- |
| Đầu vào sai | -1 | false | Ném `IllegalArgumentException` | Nhánh từ chối giá trị âm. |
| Giao thường | 100.000 | false | 30.000 | Dưới ngưỡng, nhánh thường. |
| Giao nhanh | 100.000 | true | 55.000 | Dưới ngưỡng, nhánh nhanh. |
| Đúng ngưỡng | 500.000 | false | 0 | Phân biệt `>=` với `>`. |
| Trên ngưỡng, giao nhanh | 500.001 | true | 0 | Xác nhận miễn phí được ưu tiên trước lựa chọn giao nhanh. |
| Số tiền bằng 0 | 0 | false | 30.000 | Trường hợp thấp nhất trong miền hợp lệ. |

### Line coverage chưa đủ để thấy logic điều kiện

Một dòng chứa toán tử ba ngôi có thể được đánh dấu đã chạy khi chỉ một vế được thực thi:

```java
return express ? EXPRESS_FEE : STANDARD_FEE;
```

Nếu chỉ thử `express=false`, dòng trên vẫn có thể được tính là covered theo tiêu chí dòng, nhưng **nhánh `express=true` chưa được kiểm chứng**. Vì vậy cần xem branch coverage bên cạnh line coverage, nhất là ở các phương thức chứa nhiều điều kiện.

### Branch coverage cũng chưa phải mọi tổ hợp

Xét:

```java
if (customer.isVip() && order.totalMinor() >= 500_000L) {
    return freeShipping();
}
return standardShipping();
```

Hai kết quả chung của câu `if` là có thể vào nhánh miễn phí hoặc nhánh thường. Nhưng còn các trường hợp:

| `isVip()` | `totalMinor >= 500000` | Quyết định |
| --- | --- | --- |
| false | false | Không miễn phí. |
| false | true | Không miễn phí. |
| true | false | Không miễn phí. |
| true | true | Miễn phí. |

Do toán tử `&&` ngắt mạch, vế phải **không nhất thiết được đánh giá** khi vế trái là false. Cần phân biệt **decision outcome**, **condition outcome** và **tổ hợp điều kiện được đánh giá**. Công cụ branch coverage có thể thể hiện các nhánh bytecode liên quan đến ngắt mạch, nhưng chỉ số đó không tự chứng minh đã thử đúng tất cả kết hợp ngữ nghĩa mong muốn.

**MC/DC (Modified Condition/Decision Coverage)** đặt yêu cầu mạnh hơn trong những bối cảnh cần thiết: thể hiện khả năng từng điều kiện độc lập ảnh hưởng đến kết quả quyết định, theo định nghĩa và ràng buộc áp dụng. Đây không phải điều JaCoCo mặc định bảo đảm khi báo branch coverage.

### Vì sao path coverage nhanh chóng trở nên khó?

Với nhiều nhánh liên tiếp, số đường đi khả thi có thể tăng rất nhanh. Khi có vòng lặp, số lần lặp khác nhau còn tạo ra số đường đi tiềm năng không bị giới hạn bởi một số hữu hạn nhỏ. Do đó không nên lấy “100% mọi đường đi” làm yêu cầu chung cho mọi ứng dụng Java.

Thay vào đó, lựa chọn đường đi **theo rủi ro, điều kiện biên, trạng thái, tương tác và hợp đồng**, rồi dùng coverage để tìm phần mã chưa có bằng chứng.

## 4. Viết test có assertion đủ mạnh

Một bộ test JUnit 5 có thể diễn đạt bảng nghiệp vụ trực tiếp:

**`ShippingFeePolicyTest.java`:**

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void chargesStandardFeeBelowThreshold() {
        assertEquals(30_000L, policy.feeMinor(100_000L, false));
    }

    @Test
    void chargesExpressFeeBelowThreshold() {
        assertEquals(55_000L, policy.feeMinor(100_000L, true));
    }

    @Test
    void includesExactlyTheFreeShippingThreshold() {
        assertEquals(0L, policy.feeMinor(500_000L, false));
    }

    @Test
    void freeShippingOverridesExpressFeeAboveThreshold() {
        assertEquals(0L, policy.feeMinor(500_001L, true));
    }

    @Test
    void zeroAmountUsesStandardFee() {
        assertEquals(30_000L, policy.feeMinor(0L, false));
    }

    @Test
    void rejectsNegativeBasketAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeMinor(-1L, false));
    }
}
```

Điểm khác biệt không đơn thuần là số lượng test tăng. Mỗi test có **một quy tắc có thể giải thích độc lập** và một assertion đủ cụ thể để phát hiện vi phạm quy tắc đó.

### Một assertion tốt thường có các đặc điểm

1. **Đúng nguồn kỳ vọng:** so sánh với hợp đồng hoặc yêu cầu đã được thống nhất, không “sao chép” cùng công thức có thể sai từ implementation.
2. **Đủ nhạy với lỗi đáng quan tâm:** nếu kết quả sai thành 50.000 thay vì 30.000, assertion phải thất bại.
3. **Quan sát đúng thứ cần bảo đảm:** giá trị, ngoại lệ, trạng thái, lời gọi đến dependency hoặc tác dụng phụ bên ngoài.
4. **Có ngữ cảnh biên rõ ràng:** đúng ngưỡng, ngay trước/ngay sau ngưỡng, dữ liệu rỗng hoặc trạng thái bất hợp lệ.
5. **Không phụ thuộc chi tiết tùy tiện:** test không nên hỏng chỉ vì đổi tên biến nội bộ hoặc refactor giữ nguyên hành vi.
6. **Có thông điệp dễ điều tra:** tên test và assertion giúp nhận ra quy tắc nào bị phá.

Một assertion quá chặt với chi tiết không được cam kết cũng có hại. Ví dụ, so sánh chính xác toàn bộ chuỗi JSON khi thứ tự field không thuộc hợp đồng có thể làm test thất bại vì một thay đổi vô hại. **Mạnh với hành vi cần giữ, linh hoạt với chi tiết không cần giữ** là sự cân bằng quan trọng.

## 5. “Test có assertion” vẫn có thể là test yếu

Hãy so sánh các cặp sau:

| Assertion yếu hoặc sai mục tiêu | Vấn đề | Assertion có giá trị hơn |
| --- | --- | --- |
| `assertTrue(fee >= 0)` | Nhiều mức phí sai vẫn qua. | `assertEquals(30_000L, fee)` khi hợp đồng đòi đúng mức đó. |
| `assertNotNull(result)` | Đối tượng có thể chứa dữ liệu sai. | Kiểm tra những trường kết quả mà consumer dựa vào và bất biến liên trường. |
| `assertDoesNotThrow(() -> service.save(order))` | Không bảo đảm dữ liệu đã được lưu đúng. | Kiểm tra trạng thái lưu, bản ghi và tác dụng phụ được cam kết. |
| Chỉ `verify(repository).save(any())` | Không biết nội dung lưu đúng hay sai. | Kiểm tra giá trị/định danh trong đối tượng được lưu. |
| `assertEquals(actual, actual)` | Tự so với chính nó nên không bác bỏ lỗi. | Lấy expected từ quy tắc, bảng dữ liệu hay oracle độc lập. |
| `assertTrue(list.contains(item))` | Danh sách có thể dư, trùng hoặc sai thứ tự. | Kiểm tra tập, số lượng, thứ tự nếu chúng là hợp đồng. |
| Chỉ xác minh HTTP `200` | Body có thể sai, thiếu dữ liệu hoặc sai nghĩa. | Kiểm tra status, các trường thiết yếu và lỗi theo contract. |

**Không có một loại assertion luôn tốt nhất.** Khi hợp đồng chỉ yêu cầu giá trị không âm, `assertTrue(value >= 0)` có thể đúng. Khi hợp đồng yêu cầu một mức phí chính xác, assertion không âm quá yếu. Chất lượng chỉ được đánh giá khi biết **điều gì cần được bảo đảm**.

### Tránh tautology và oracle có cùng lỗi với implementation

Ví dụ:

```java
long actual = policy.feeMinor(500_000L, false);
long expected = policy.feeMinor(500_000L, false);
assertEquals(expected, actual); // Không kiểm tra quy tắc độc lập.
```

Đoạn test gọi cùng phương thức hai lần và so sánh kết quả với chính cách tính ấy. Nếu implementation sai ở ngưỡng 500.000, cả hai vế có khả năng cùng sai và test vẫn xanh.

Một phép so sánh có ý nghĩa cần có **oracle**: nguồn xác định kết quả đúng. Với ví dụ này, oracle là bảng giá đã chấp thuận, không phải phương thức đang được kiểm tra.

## 6. Assertions phải bảo vệ cả đường lỗi và tác dụng phụ

Chương trình có thể trả đúng kết quả nhưng thực hiện sai hành động. Ví dụ, một yêu cầu bị từ chối đúng là `false` nhưng vẫn gửi email; chỉ kiểm giá trị trả về sẽ không phát hiện.

Giả sử nghiệp vụ kích hoạt tài khoản có quy tắc: chỉ yêu cầu đã được duyệt mới được gửi thông báo; email bắt buộc khác rỗng.

**`ActivationService.java`:**

```java
import java.util.Objects;

interface NotificationSender {
    void send(String destination, String message);
}

final class ActivationService {
    private final NotificationSender sender;

    ActivationService(NotificationSender sender) {
        this.sender = Objects.requireNonNull(sender);
    }

    boolean activate(String email, boolean approved) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        if (!approved) {
            return false;
        }
        sender.send(email, "Activated");
        return true;
    }
}
```

**`ActivationServiceTest.java` — fake tự ghi nhận hành động:**

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ActivationServiceTest {
    static final class FakeSender implements NotificationSender {
        final List<String> destinations = new ArrayList<>();
        final List<String> messages = new ArrayList<>();

        @Override
        public void send(String destination, String message) {
            destinations.add(destination);
            messages.add(message);
        }
    }

    @Test
    void rejectedActivationDoesNotSendNotification() {
        FakeSender sender = new FakeSender();
        ActivationService service = new ActivationService(sender);

        assertFalse(service.activate("customer@example.test", false));
        assertTrue(sender.destinations.isEmpty());
    }

    @Test
    void approvedActivationSendsExactlyOneExpectedMessage() {
        FakeSender sender = new FakeSender();
        ActivationService service = new ActivationService(sender);

        assertTrue(service.activate("customer@example.test", true));
        assertEquals(List.of("customer@example.test"),
                sender.destinations);
        assertEquals(List.of("Activated"), sender.messages);
    }

    @Test
    void invalidEmailFailsBeforeSending() {
        FakeSender sender = new FakeSender();
        ActivationService service = new ActivationService(sender);

        assertThrows(IllegalArgumentException.class,
                () -> service.activate(" ", true));
        assertTrue(sender.destinations.isEmpty());
    }
}
```

Ở đây assertion kiểm tra cả **kết quả** lẫn **số lần và dữ liệu của tác dụng phụ**. Fake làm rõ hợp đồng của `ActivationService`; nó chưa chứng minh gateway gửi email ngoài hệ thống thật thành công. Kiểm thử tích hợp cần được dùng ở ranh giới transport nếu hành vi đó quan trọng.

### Assertions cho ngoại lệ cần đúng mức

`assertThrows(IllegalArgumentException.class, ...)` có giá trị khi **loại ngoại lệ** là phần hợp đồng. Việc khẳng định nguyên văn thông điệp lỗi chỉ nên làm khi thông điệp đó được cam kết ổn định (ví dụ mã lỗi công khai). Thông điệp phục vụ debug có thể đổi khi refactor mà không phá hợp đồng.

Đừng bắt mọi exception rồi coi đó là thành công:

```java
// Yếu: bất kỳ lỗi không mong muốn nào cũng được chấp nhận.
assertThrows(Exception.class,
        () -> policy.feeMinor(-1L, false));
```

Kiểm tra đúng loại lỗi và — nếu cần — trạng thái sau lỗi: giao dịch không được ghi một phần, email không bị gửi, đối tượng cũ không bị biến đổi.

## 7. Độ bao phủ không phải độ bao phủ yêu cầu

Một chức năng có thể được chia thành các lớp: controller, service, repository và adapter. Coverage của `ShippingFeePolicy` chỉ nói các dòng/nhánh của lớp này được chạy, không chứng minh:

- Controller ánh xạ số tiền đúng đơn vị và xử lý đầu vào lỗi.
- API trả status code/JSON đúng hợp đồng.
- Database transaction thực hiện nguyên tử.
- Nhiều request đồng thời không làm sai trạng thái.
- Retry không lặp tác dụng phụ.
- Cấu hình production áp dụng đúng ngưỡng.

Vì thế cần phân biệt:

| Góc nhìn | Kiểm tra được gì? | Ví dụ bằng chứng |
| --- | --- | --- |
| **Code coverage** | Bao nhiêu phần mã đã thực thi trong bộ test. | JaCoCo line/branch report. |
| **Requirement coverage** | Những yêu cầu hoặc quy tắc nào có ít nhất một test liên kết. | Ma trận yêu cầu → kịch bản → test. |
| **Behavioral assertion quality** | Test có đủ khả năng phát hiện những vi phạm quan trọng không. | Đánh giá oracle, negative cases, mutation testing. |
| **Integration coverage** | Các ranh giới thực tế nào được thử cùng nhau. | HTTP, DB, queue, filesystem, provider. |
| **Failure-scenario coverage** | Những kiểu lỗi/cạnh tranh nào đã được kiểm chứng. | Timeout sau commit, request trùng, dữ liệu sai. |

Một test có thể bao phủ rất nhiều dòng production khi khởi tạo ứng dụng, nhưng không có assertion kiểm tra được hành vi chính của những dòng ấy. **Số dòng chạy qua và số yêu cầu được kiểm chứng là hai đại lượng khác nhau**.

## 8. Mutation testing: test có phát hiện lỗi được cài có chủ đích?

**Mutation testing** cố tình tạo những thay đổi nhỏ trong mã production (*mutants*) như thay toán tử so sánh, thay hằng số, phủ định điều kiện hoặc bỏ lời gọi. Sau đó chạy bộ test để xem nó có phát hiện thay đổi hay không.

Giả sử mã gốc:

```java
if (basketMinor >= FREE_FROM) {
    return 0L;
}
```

Một mutant đổi `>=` thành `>`:

```java
if (basketMinor > FREE_FROM) {
    return 0L;
}
```

Nếu bộ test chỉ thử `basketMinor=600_000` và `basketMinor=100_000`, mutant này có thể **sống sót** (*survived*): mọi test vẫn xanh dù hợp đồng tại đúng ngưỡng 500.000 bị phá. Test `includesExactlyTheFreeShippingThreshold` kiểm tra 500.000 sẽ thất bại khi chạy với mutant này, vì thế mutant bị **kill**.

### Mutation score

Một cách tính thường dùng:

```text
mutation score = số mutant bị phát hiện /
                 số mutant hợp lệ được đánh giá × 100%
```

Tuy nhiên, **định nghĩa mẫu số khác nhau giữa công cụ và cách báo cáo**. Các mutant không thể chạy, không được bao phủ hoặc bị lọc có thể được xử lý khác nhau. Khi báo con số, cần ghi rõ công cụ, cấu hình, operator, phạm vi mã và cách xử lý mutant tương đương.

Ví dụ minh họa: nếu trong một tập 100 mutant được xem là có ý nghĩa, 82 mutant bị test phát hiện và 18 sống sót, tỷ lệ là 82%. Nhưng **82% không phải xác suất phần mềm đúng 82%**, cũng không chứng minh 18% còn lại là bug thật.

### Mutant sống sót có thể nói gì?

| Tình huống | Ý nghĩa có thể có | Hành động |
| --- | --- | --- |
| Thay `>=` bằng `>` mà test vẫn xanh. | Thiếu ca đúng ngưỡng. | Thêm test biên theo yêu cầu. |
| Thay mức phí 30.000 thành 31.000 mà test vẫn xanh. | Assertion chỉ kiểm phí không âm. | Kiểm tra mức phí kỳ vọng chính xác. |
| Bỏ lời gọi gửi thông báo mà test vẫn xanh. | Thiếu assertion về tác dụng phụ. | Kiểm tra số lần gửi và dữ liệu. |
| Mutant không thể tạo kết quả quan sát khác. | Có thể là *equivalent mutant*. | Xác minh tương đương, không thêm test vô ích. |
| Mutant nằm ở mã sinh tự động hoặc không còn được sử dụng. | Có thể cần xem lại phạm vi đo. | Phân loại mã hoặc chính sách loại trừ rõ ràng. |

**Equivalent mutant** là một thay đổi cú pháp nhưng không làm đổi hành vi quan sát trong miền hợp đồng. Không tồn tại test đúng đắn nào có thể phân biệt được nó nếu thật sự tương đương. Việc nhận diện tương đương hoàn toàn nhìn chung không đơn giản; trong thực tế cần review và cơ chế quản lý ngoại lệ.

### Công cụ trong hệ sinh thái Java

**PIT (PITest)** là một lựa chọn phổ biến cho mutation testing Java. Nó có thể tích hợp vào quy trình build để tạo mutant và chạy những test liên quan. Việc kích hoạt, các toán tử và cách báo cáo phụ thuộc phiên bản/cấu hình của dự án. **Không nên chạy mutation testing nặng trên toàn bộ repository ở mọi lần gõ phím**; có thể phân tầng local, CI theo module và quét sâu định kỳ.

Mutation testing vẫn không hiểu toàn bộ nghiệp vụ: một mutant bị kill vì test lỗi do nguyên nhân không liên quan chưa chắc chứng minh assertion đúng mục tiêu. Hãy dùng nó làm **tín hiệu về khả năng phát hiện thay đổi sai**, kết hợp review ca test và oracle.

## 9. JaCoCo: đọc báo cáo đúng phạm vi

Với dự án JVM, **JaCoCo** là công cụ thu thập coverage cho mã Java. Nó đo từ bytecode được instrument và có thể xuất báo cáo HTML/XML để nhóm hoặc CI xem line, instruction, branch cùng các chỉ số khác.

### Ví dụ cấu hình Gradle Kotlin DSL

Đoạn dưới đây chỉ minh họa một dự án **Gradle/Kotlin DSL** đã cấu hình JUnit Jupiter; nó không giả định repository hiện tại dùng cấu hình này:

```kotlin
plugins {
    java
    jacoco
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        html.required.set(true)
        xml.required.set(true)
    }
}
```

Khi chạy các task tương ứng, Gradle và JaCoCo tạo dữ liệu coverage theo cấu hình plugin. Cần đối chiếu build script thực tế của dự án để biết báo cáo nằm ở đâu, những test task nào được gắn và module nào được tính vào mẫu số.

### Coverage report có thể bị hiểu sai vì những lý do nào?

1. **Sai phạm vi test:** chỉ chạy unit test nhưng báo cáo được dùng để khẳng định bao phủ toàn bộ luồng tích hợp.
2. **Sai phạm vi production:** nhiều module, lớp sinh tự động, mã cấu hình hoặc phần loại trừ không nhất quán khiến tỷ lệ đổi dù test không đổi.
3. **Test thất bại hoặc không chạy:** dữ liệu coverage thiếu/không được tạo; không nên dùng báo cáo cũ như kết quả mới.
4. **Bytecode không trùng source:** phiên bản build khác hoặc công cụ xử lý bytecode khác nhau có thể khiến mapping dòng/nhánh khó hiểu.
5. **Code thực thi được sinh ra:** compiler và framework có thể sinh instruction/nhánh không hiển thị trực tiếp như một lệnh source.
6. **Nhánh exception:** coverage của JaCoCo về nhánh `if`/`switch` không đồng nghĩa đã đo mọi đường ngoại lệ; xử lý exception không được JaCoCo tính thành branch theo cùng cách các câu điều kiện.

Một test gọi được phương thức nhưng không đi qua nhánh lỗi vẫn có thể khiến một phần lớn dòng mã được đánh dấu xanh. Đừng đọc màu sắc báo cáo thay cho việc xem logic và kịch bản.

### Báo cáo một chỉ số đủ ngữ cảnh

Thay vì nói “coverage 91%”, một báo cáo có ích hơn là:

```text
Phạm vi: module billing-core, production classes được quy định
Build: commit / phiên bản đã kiểm thử
Nguồn test: JUnit unit test, không tính integration test
Chỉ số: JaCoCo line 91%; branch 78%
Loại trừ: lớp sinh tự động theo danh sách đã review
Vùng rủi ro: logic hoàn tiền và xử lý timeout còn nhánh chưa thử
Hành động: bổ sung test ngưỡng và lỗi sau khi ghi giao dịch
```

Các tỷ lệ là **ví dụ minh họa**, không phải kết quả đo của module này. Mục tiêu là để người đọc biết một số đo đang đại diện điều gì và **không đại diện điều gì**.

## 10. Số lượng assertion cũng không phải chất lượng assertion

Một test chứa 40 assertion không tự động mạnh hơn test có 4 assertion. Có thể cả 40 đều kiểm thuộc tính dễ đúng hoặc trùng nhau, trong khi một lỗi nghiêm trọng không bị kiểm tra.

### Ví dụ nhiều assertion nhưng thiếu quy tắc

```java
long fee = policy.feeMinor(500_000L, false);
assertTrue(fee >= 0);
assertTrue(fee <= 100_000);
assertNotEquals(-1, fee);
assertFalse(fee < 0);
```

Tất cả đều xanh nếu phí trả về 30.000, dù **đúng ngưỡng phải miễn phí**. Chỉ cần một assertion:

```java
assertEquals(0L, policy.feeMinor(500_000L, false));
```

Assertion này có sức phát hiện lỗi tốt hơn cho chính hợp đồng miễn phí tại ngưỡng.

### Nên kiểm tra điều gì với đối tượng nhiều trường?

Nếu kết quả là `Receipt` gồm ID, số tiền, tiền tệ và trạng thái, hãy chọn:

- Những trường **consumer thực sự dựa vào**.
- Những **bất biến giữa các trường**, như tổng tiền bằng số tiền đã chốt.
- Trạng thái sau thao tác và **những điều không được xảy ra**.
- Những trường hợp lỗi có ảnh hưởng đến giao dịch hoặc an toàn.

Không cần so sánh mọi trường nội bộ nếu chúng không thuộc hợp đồng; tránh snapshot quá chặt khiến refactor không đổi hành vi cũng làm test hỏng.

## 11. Lựa chọn dữ liệu biên và thuộc tính để tăng sức mạnh test

Coverage của một nhánh có thể được đạt với vô số bộ dữ liệu, nhưng **không phải mọi bộ dữ liệu có giá trị kiểm chứng như nhau**.

Với ngưỡng 500.000:

```text
499_999  → ngay dưới ngưỡng
500_000  → đúng ngưỡng
500_001  → ngay trên ngưỡng
```

Ba giá trị này đặc biệt hữu ích vì phân biệt các lỗi `<`, `<=`, `>` và `>=`. Trong khi đó, thử 100.000 và 200.000 có thể đều đi cùng một đường, làm tăng số test nhưng không cung cấp nhiều bằng chứng mới.

### Thuộc tính tổng quát

Ngoài ví dụ cố định, có thể phát biểu:

```text
Với mọi basketMinor >= 500000:
    feeMinor(basketMinor, false) == 0
    feeMinor(basketMinor, true) == 0

Với mọi 0 <= basketMinor < 500000:
    feeMinor(basketMinor, false) == 30000
    feeMinor(basketMinor, true) == 55000

Với mọi basketMinor < 0:
    feeMinor(...) từ chối dữ liệu
```

Property-based testing có thể sinh nhiều đầu vào cho mỗi miền, giúp phát hiện lỗi ngoài những ví dụ người viết nghĩ tới. Nhưng một property được chạy hữu hạn lần vẫn **không chứng minh** điều kiện đúng trên mọi `long`. Hơn nữa, nếu property lấy cùng công thức sai từ mã thì test và implementation vẫn có thể đồng ý với nhau.

### Kết hợp nhiều dạng oracle

| Dạng oracle | Đặt câu hỏi | Ví dụ |
| --- | --- | --- |
| Kết quả chính xác | Giá trị phải là bao nhiêu? | Phí đúng ngưỡng phải bằng 0. |
| Bất biến | Điều gì phải luôn đúng? | Phí không âm với input hợp lệ. |
| Quan hệ/metamorphic | Hai lần thực thi liên quan thế nào? | Khi đã được miễn phí, bật express không làm tăng phí. |
| Trạng thái và tác dụng phụ | Thao tác nào được/không được xảy ra? | Không gửi thông báo khi kích hoạt bị từ chối. |
| Lỗi theo hợp đồng | Dữ liệu sai phải bị xử lý thế nào? | Tổng tiền âm bị từ chối trước khi xử lý. |

Không phải thuộc tính nào cũng đúng cho mọi nghiệp vụ. Ví dụ “phí không bao giờ tăng khi tổng tiền tăng” chỉ hợp lệ nếu bảng quy tắc đã cam kết tính đơn điệu. Khi có khu vực giao hàng, cân nặng hoặc phụ phí khác, quy tắc cần được phát biểu lại theo điều kiện bổ sung.

## 12. Các chỉ số chất lượng kiểm thử cần được dùng cùng nhau

Một dashboard có thể kết hợp:

| Thông tin | Nó giúp đánh giá | Điều không nên làm |
| --- | --- | --- |
| Line coverage | Tìm vùng mã chưa được chạy. | Xem tỷ lệ dòng như xác suất phần mềm đúng. |
| Branch coverage | Tìm quyết định chưa được thử đủ các nhánh. | Suy rằng tất cả tổ hợp điều kiện đều được thử. |
| Mutation score | Đánh giá test có phát hiện một tập lỗi nhân tạo không. | Xem mutant sống sót nào cũng là lỗi production. |
| Mapping yêu cầu–test | Xem quy tắc quan trọng nào có bằng chứng. | Đếm “có test” mà không review assertion. |
| Thời gian test / flakiness | Biết test có phản hồi ổn định, kịp thời không. | Xóa test quan trọng chỉ vì nó chạy lâu. |
| Lỗi lọt production | Xem xu hướng và những kịch bản bị bỏ sót. | Kết luận một chỉ số đơn lẻ là nguyên nhân duy nhất. |
| Dữ liệu test và kịch bản lỗi | Hiểu miền được kiểm chứng. | Chỉ chạy happy path rồi tuyên bố đủ coverage. |

Chỉ số cần giúp **ra quyết định kỹ thuật**. Ví dụ, nếu branch coverage ở module thanh toán thấp và mutation testing cho thấy các điều kiện xử lý lỗi chưa được kiểm chứng, hành động nên là viết test cho luồng lỗi thực tế, chứ không phải thêm các assertion vô nghĩa ở phần khác để “đẹp số”.

### Coverage threshold có nên dùng không?

Có thể dùng ngưỡng ở CI để phát hiện sự suy giảm bất thường, nhưng:

- Chọn **phạm vi và loại coverage** rõ ràng.
- Không để đội ngũ bỏ test hữu ích hoặc viết test giả tạo chỉ để đạt chỉ tiêu.
- Ưu tiên **mã mới hoặc mã thay đổi** và những vùng có rủi ro cao; đồng thời giữ kế hoạch xử lý nợ cũ.
- Review loại trừ coverage, tránh tùy tiện bỏ qua các lớp quan trọng khỏi mẫu số.
- Không dùng một tỷ lệ chung để tự động chứng nhận an toàn cho logic thanh toán, phân quyền hoặc đồng thời.

**100% line coverage** có thể là mục tiêu khả thi trong một hàm nhỏ; nó vẫn không phải chứng minh mọi hành vi đúng. **100% branch coverage** cũng có thể bỏ qua lỗi từ sai đặc tả, điều kiện không được mô hình hóa, dữ liệu biên hoặc các interleaving đồng thời.

## 13. Quy trình đọc báo cáo và cải thiện test có hệ thống

Giả sử sau một đợt thay đổi, báo cáo của một module có **92% line coverage nhưng 66% branch coverage**. Đừng lập tức viết thêm test chỉ để tăng tỷ lệ; hãy thực hiện:

1. **Xác nhận tính hợp lệ của báo cáo:** test có thật sự chạy thành công, report có mới, source/build và phạm vi đo có đúng không?
2. **Xác định vùng chưa được thử:** mở báo cáo theo lớp/method và xem những nhánh nào thiếu, không chỉ đọc tỷ lệ tổng.
3. **Đối chiếu với hợp đồng:** nhánh đó xử lý đầu vào sai, ngưỡng, lỗi I/O, retry, thiếu quyền hay trường hợp không khả thi?
4. **Xác định rủi ro:** ảnh hưởng tiền, dữ liệu, quyền, tài nguyên và người dùng như thế nào?
5. **Viết test với assertion có mục tiêu:** kỳ vọng lấy từ đặc tả, có ví dụ biên/negative và kiểm tra tác dụng phụ khi cần.
6. **Thử “đột biến” tư duy hoặc công cụ:** nếu sửa một toán tử hoặc bỏ một lời gọi, test có thất bại vì đúng lý do không?
7. **Không che cảnh báo bằng test hình thức:** tránh test chỉ chạy code nhưng không xác nhận kết quả.
8. **Giữ test bền vững:** cô lập dữ liệu, loại trừ phụ thuộc thời gian ngẫu nhiên, dùng fake ở đúng tầng và integration test khi cần.
9. **Đo lại và giải thích thay đổi:** coverage nào tăng, mutant nào bị kill, quy tắc nghiệp vụ nào được bảo vệ thêm?

Một PR có thể tăng line coverage rất ít nhưng bổ sung kiểm thử đúng ngưỡng thanh toán hoặc xử lý mất kết nối sau commit. **Giá trị bảo vệ của test** khi ấy có thể lớn hơn phần trăm tăng thêm.

### Khi một nhánh khó hoặc không thể đi tới

Không phải mọi code chưa phủ đều đáng viết test bằng mọi giá. Một nhánh có thể tồn tại để phòng vệ nhưng gần như không đạt tới dưới bất biến đang được bảo đảm; đôi khi là dead code; hoặc cần test integration thay vì unit test. Hãy:

- Chứng minh đường đi không khả thi theo các tiền điều kiện đã kiểm chứng, **nếu thật sự không khả thi**.
- Loại bỏ dead code nếu không cần thiết.
- Giữ nhánh phòng vệ và ghi lý do nếu nó bảo vệ một ranh giới quan trọng.
- Đưa test đến cấp thích hợp, chẳng hạn lỗi filesystem/DB ở integration test.

Không nên tạo đầu vào vi phạm hợp đồng của những tầng thấp chỉ để ép một nhánh chạy, rồi coi tỷ lệ cao hơn là thắng lợi.

## 14. Những ngộ nhận phổ biến

**“95% coverage nghĩa là 95% trường hợp nghiệp vụ đúng.”** Không. Coverage chỉ mô tả phần mã được thực thi theo mô hình công cụ.

**“Nếu mọi dòng đều xanh thì không còn lỗi.”** Một dòng chứa hai nhánh hoặc tính sai giá trị vẫn có thể đã được chạy. Assertion có thể quá yếu.

**“Test có ít nhất một assertion là đạt chất lượng.”** Một assertion trùng chính kết quả thực tế, chỉ kiểm non-null hoặc kiểm thuộc tính không liên quan chưa bảo vệ hợp đồng.

**“Thêm nhiều assertion luôn tốt.”** Assertion trùng và gắn chặt vào chi tiết nội bộ làm test giòn mà không tăng khả năng bắt lỗi.

**“Mutation score càng cao càng chứng minh phần mềm đúng.”** Mutation testing chỉ thử một tập thay đổi nhân tạo. Kết quả chịu ảnh hưởng operator, equivalent mutants và scope; nó không chứng minh yêu cầu đúng.

**“Chỉ cần unit test là đủ cho service.”** Có những bất biến thuộc DB, mạng, bảo mật và đồng thời không được bảo vệ bằng fake Java đơn thuần.

**“Chạy mọi đường lỗi là làm hỏng code.”** Không. Các đường lỗi theo hợp đồng cần test; có thể dùng fake, fault injection có kiểm soát hoặc môi trường integration cô lập.

**“Chặn PR nếu coverage giảm dù thay đổi không liên quan.”** Ngưỡng có ích khi kèm phạm vi, ngữ cảnh và review; không nên trở thành mục tiêu để tối ưu số đo thay vì chất lượng.

**“Coverage report của hai môi trường tự nhiên phải giống nhau.”** Khác JDK, phạm vi test, version công cụ, bytecode sinh ra và exclusions có thể làm số liệu khác. Cần ghi rõ điều kiện đo.

## 15. Checklist dành cho code review

Khi review một PR thêm hoặc thay đổi test:

1. **Test đang bảo vệ yêu cầu nào?** Có mô tả và expected result độc lập không?
2. **Đầu vào đã gồm biên và tình huống bị từ chối chưa?** Những điều kiện `<`, `<=`, `>`, `>=` có được phân biệt không?
3. **Assertion có đủ mạnh?** Nếu thay kết quả đúng bằng một giá trị sai hợp lý, test có thất bại không?
4. **Có kiểm tra tác dụng phụ và điều không được xảy ra?** Nhất là gửi thông báo, ghi DB, thanh toán và event.
5. **Coverage thiếu ở đâu?** Có nhánh lỗi quan trọng bị bỏ sót hay chỉ là mã sinh tự động không liên quan?
6. **Test có độc lập với implementation và môi trường?** Tránh dùng lại cùng logic làm expected hoặc phụ thuộc thứ tự thực thi.
7. **Có dấu hiệu test giòn không?** So chuỗi lỗi, log, thứ tự nội bộ hoặc thời điểm không thuộc hợp đồng.
8. **Báo cáo metric có đủ ngữ cảnh?** Công cụ, phạm vi mã, tập test, commit và exclusions.
9. **Những lỗi không thể bắt bằng unit test đã có kế hoạch kiểm chứng riêng chưa?** Tích hợp, đồng thời, thời gian thực và nhà cung cấp ngoài.

Một test tốt không nhất thiết dài. Nó phải **giải thích được vì sao trạng thái này đúng và sai lệch nào khiến nó thất bại**.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một lớp đạt 100% line coverage nhưng chỉ 70% branch coverage. Có mâu thuẫn không?

*Gợi ý:* Không. Một dòng có thể được thực thi mà chưa thử mọi kết quả của điều kiện hoặc toán tử rẽ nhánh nằm trên dòng đó.

**Câu 2.** Test kiểm `assertTrue(fee >= 0)` cho đơn hàng 500.000. Tại sao test này chưa xác minh miễn phí vận chuyển?

*Gợi ý:* Kết quả 30.000 cũng không âm. Hợp đồng ở đúng ngưỡng yêu cầu phí chính xác bằng 0, nên cần assertion tương ứng.

**Câu 3.** Mutant thay `basketMinor >= 500000` bằng `basketMinor > 500000` sống sót. Nên bổ sung test nào?

*Gợi ý:* Một test có đầu vào **đúng 500.000** và kỳ vọng phí bằng 0. Các giá trị xa ngưỡng không phân biệt được hai toán tử.

**Câu 4.** Test chỉ khẳng định `activate(...) == false` khi không duyệt. Nó có bảo đảm email không được gửi không?

*Gợi ý:* Chưa. Cần fake/mock hoặc kiểm thử tích hợp để kiểm tra số lần gửi bằng 0 ở nhánh bị từ chối.

**Câu 5.** Tại sao một API có branch coverage cao nhưng vẫn có thể trả JSON sai đơn vị tiền?

*Gợi ý:* Coverage không kiểm tra ngữ nghĩa dữ liệu; test cần khẳng định giá trị và đơn vị tại ranh giới HTTP/serialization.

**Câu 6.** Một mutant sống sót nhưng theo hợp đồng nó không thể làm thay đổi hành vi quan sát được. Có nên cố thêm test để kill nó?

*Gợi ý:* Không nếu đó thực sự là equivalent mutant. Cần review và ghi nhận trong cách tính/diễn giải, thay vì tạo assertion vào chi tiết không thuộc hợp đồng.

**Câu 7.** Hai dự án cùng có line coverage 90%. Có thể kết luận bộ test của chúng có chất lượng tương đương không?

*Gợi ý:* Không. Phạm vi code, độ rủi ro, chất lượng assertion, tỷ lệ nhánh, mutation score và loại lỗi được kiểm tra có thể rất khác nhau.

## Ghi nhớ

- **Coverage cho biết phần mã được chạy**, không cho biết mọi hành vi của phần đó đã đúng.
- **Line, branch, condition và path coverage** có ý nghĩa khác nhau; đọc đúng loại chỉ số và cách công cụ tính.
- **Assertion có giá trị phải có oracle từ hợp đồng**, phát hiện được giá trị sai, bảo vệ biên, lỗi và tác dụng phụ đáng quan tâm.
- **Mutation testing** giúp phát hiện vùng test không nhạy với thay đổi lỗi, nhưng không phải chứng minh chương trình đúng tuyệt đối.
- **Đánh giá chất lượng kiểm thử cần nhiều bằng chứng:** coverage, yêu cầu–test, assertion, mutation, test tích hợp và dữ liệu lỗi thực tế.
- **Đừng tối ưu phần trăm để có số đẹp.** Ưu tiên những test có thể ngăn lỗi nghiệp vụ quan trọng và giúp người bảo trì thay đổi mã một cách tự tin.

**Câu hỏi cốt lõi khi xem một test:** “Nếu implementation vẫn chạy qua các dòng này nhưng trả sai kết quả, sai trạng thái hoặc tạo tác dụng phụ không mong muốn, assertion nào sẽ phát hiện điều đó?”
