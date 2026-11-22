# Giới hạn số pattern trong một method: tối ưu tính dễ đọc của Java Pattern Matching

## 1. Không có “con số tối đa” chung cho mọi method

Khi dùng Java Pattern Matching, một method có thể chứa nhiều nhánh `case Type x`, record patterns, nested record patterns và guard `when`. **Đặc tả Java không đặt quy tắc rằng một method chỉ được có 3, 5 hay 10 pattern.** Compiler kiểm tra tính hợp lệ của từng pattern, kiểu selector, khả năng bao phủ của `switch`, thứ tự nhánh bị bao phủ (*domination*) và cú pháp, **không** đánh giá mức độ dễ đọc theo một con số cố định.

Vì vậy, câu hỏi hữu ích hơn “tối đa bao nhiêu pattern?” là:

> Người đọc có thể nhanh chóng hiểu **method này quyết định điều gì**, các nhánh ưu tiên thế nào, mỗi nhánh thực hiện nhiệm vụ gì và đã xử lý hết các trường hợp biên chưa?

**Số pattern** là một tín hiệu dễ quan sát, nhưng không đủ phản ánh độ phức tạp:

- Năm nhánh ngắn, cùng phân loại một thuộc tính đơn giản có thể dễ hiểu hơn ba nhánh lồng record patterns sâu và gọi nhiều phương thức trong guard.
- Một `switch` expression ánh xạ nhiều biến thể kiểu sang nhãn đơn giản có thể nên được giữ nguyên trong một method.
- Một method chỉ có vài pattern nhưng mỗi nhánh cập nhật database, gửi message và thay đổi trạng thái có thể khó hiểu hơn rất nhiều.

**Nguyên tắc chính:** Giới hạn theo **mức tải nhận thức và trách nhiệm nghiệp vụ**, không theo số lượng pattern tùy ý. Nếu nhóm muốn có ngưỡng cảnh báo trong code review, hãy ghi rõ đó là **quy ước của dự án**, không phải giới hạn của Java/JVM hay quy tắc được JEP khuyến nghị.

**Phiên bản:** Pattern matching cho `instanceof` chính thức từ Java 16; record patterns (JEP 440) và pattern matching for `switch` (JEP 441) chính thức từ **Java 21**. Các ví dụ đầy đủ dưới đây sử dụng Java 21+, không cần `--enable-preview`.

## 2. Bốn yếu tố cần đánh giá trước khi tách method

### 2.1. Số nhánh và số quyết định

Một pattern thường biểu diễn một khả năng khớp; nhưng **số nhánh không nhất thiết bằng số quyết định nghiệp vụ**. Ví dụ:

```java
return switch (event) {
    case Login(var user, var success) -> ...;
    case Purchase(var buyer, var amount) -> ...;
    case Refund(var buyer, var amount) -> ...;
    case Alert(var message, var severity) -> ...;
    case null -> ...;
};
```

Method này có các nhánh theo **loại event**, dễ đọc nếu phần thân chỉ gọi helper thích hợp. Nếu mỗi nhánh lại chứa nhiều điều kiện định giá, kiểm tra quyền, tính thuế và xử lý lỗi thì một method đang chịu quá nhiều trách nhiệm.

Nên xem xét **fan-out**: một method phải phân biệt bao nhiêu nhóm hành vi? Các nhóm có cùng một mục tiêu và cùng kiểu kết quả không? Việc thêm biến thể mới có đòi sửa rất nhiều nhánh không liên quan không?

### 2.2. Độ sâu của record patterns

Một record pattern có thể deconstruct nhiều tầng:

```java
record Address(String city) {}
record Customer(Address address) {}
record Sale(Customer buyer, int total) {}

// Ví dụ minh họa một case trong switch:
case Sale(Customer(Address(String city)), int total)
        when total >= 100 -> "high sale in " + city;
```

Mẫu này ngắn, nhưng người đọc phải theo dõi đồng thời `Sale` → `Customer` → `Address` → `String`, điều kiện số tiền và quy tắc null của record con. Nếu nhánh xử lý còn dài, chi phí đọc và debug tăng nhanh.

Có thể đổi sang trích xuất nông hơn:

```java
// Phần minh họa tiếp nối các record trên:
case Sale(var buyer, int total) ->
        describeSale(buyer, total);
```

Hàm `describeSale` sẽ chịu trách nhiệm kiểm tra cấu trúc bên trong nếu cần. **Đừng tự động tách mọi nested record pattern**: với quy tắc đơn giản, các component hiện rõ vẫn có thể là lựa chọn dễ hiểu nhất. Chỉ tách khi nó giảm độ sâu phải giữ trong đầu, tạo ra tên gọi domain rõ ràng hoặc cho phép test độc lập.

### 2.3. Độ phức tạp của guard và ưu tiên

Một `when` thêm quyết định Boolean vào nhánh:

```java
case Purchase(var buyer, int amount) when amount >= 100 ->
        "large";
case Purchase(var buyer, int amount) when amount > 0 ->
        "normal";
case Purchase(var buyer, int amount) ->
        "invalid";
```

Guard đơn giản, có thứ tự rõ ràng là điều hợp lý. Nhưng nếu phải đọc nhiều điều kiện với `&&`/`||`, gọi các phương thức chưa biết side effect hoặc hiểu mối quan hệ chồng lấn giữa các guard, hãy cân nhắc chuyển logic nhóm `Purchase` sang một helper có tên nghiệp vụ.

**Quan trọng:** Việc tách helper không được vô tình đổi thứ tự ưu tiên của guard. Nhánh có guard cụ thể cần được thử trước nhánh không guard bao phủ cùng kiểu. Khi nhiều guard cùng đúng, nhánh được chọn phụ thuộc vào thứ tự trong `switch`.

### 2.4. Phần thân và hiệu ứng phụ

Một `switch` ánh xạ dữ liệu thuần túy thường dễ đọc hơn một `switch` trộn định tuyến và thao tác nghiệp vụ. Ví dụ:

```java
// Minh họa định tuyến có side effect; các phương thức ở đây là giả định.
switch (event) {
    case Purchase p -> processPurchase(p);
    case Refund r -> processRefund(r);
    case null -> handleMissing();
    default -> handleOther(event);
}
```

Nếu từng hành động bao gồm lưu dữ liệu, retry hoặc gửi sự kiện, người đọc nên thấy **tên hành động** trong switch, còn chi tiết nằm ở những method chịu trách nhiệm tương ứng. Không nên chuyển side effect vào guard chỉ để phần thân ngắn hơn: guard có thể chạy nhưng nhánh đó cuối cùng không được chọn.

## 3. Ví dụ Java hoàn chỉnh: từ switch nhiều pattern sang điều phối gọn

Bài toán giả định: một hệ thống có bốn loại event trong **sealed hierarchy** và cần trả về nhãn phân loại. Bản ban đầu `before` chứa nhiều nhãn pattern để xử lý đồng thời loại sự kiện và quy tắc bên trong. Bản `after` giữ một switch điều phối theo **bốn loại domain**, còn quy tắc chi tiết nằm trong helper.

Ví dụ cố ý giữ mọi hàm **thuần túy**, không I/O và không sửa dữ liệu ngoài, để đối chiếu hành vi rõ ràng.

Lưu thành **`PatternCountReadabilityDemo.java`**:

```java
public class PatternCountReadabilityDemo {
    sealed interface Event permits Login, Purchase, Refund, Alert {}

    record Login(String user, boolean success) implements Event {}
    record Purchase(String buyer, int amount) implements Event {}
    record Refund(String buyer, int amount) implements Event {}
    record Alert(String message, int severity) implements Event {}

    static String label(String raw) {
        return raw == null ? "(unknown)" : raw;
    }

    // Trước: một switch chứa nhiều pattern + guard của
    // các nhóm nghiệp vụ khác nhau.
    static String before(Event event) {
        return switch (event) {
            case Login(String user, boolean success) when success ->
                    "LOGIN_OK:" + label(user);
            case Login(String user, boolean success) ->
                    "LOGIN_FAIL:" + label(user);

            case Purchase(String buyer, int amount) when amount >= 100 ->
                    "PURCHASE_HIGH:" + label(buyer) + ":" + amount;
            case Purchase(String buyer, int amount) when amount > 0 ->
                    "PURCHASE:" + label(buyer) + ":" + amount;
            case Purchase(String buyer, int amount) ->
                    "PURCHASE_INVALID";

            case Refund(String buyer, int amount) when amount > 0 ->
                    "REFUND:" + label(buyer) + ":" + amount;
            case Refund(String buyer, int amount) ->
                    "REFUND_INVALID";

            case Alert(String message, int severity) when severity >= 3 ->
                    "ALERT_HIGH:" + label(message);
            case Alert(String message, int severity) ->
                    "ALERT:" + label(message);

            case null -> "UNKNOWN";
        };
    }

    // Sau: một switch điều phối theo loại event.
    // Mỗi helper xử lý quy tắc nội bộ của một nhóm.
    static String after(Event event) {
        return switch (event) {
            case Login(var user, var success) ->
                    describeLogin(user, success);
            case Purchase(var buyer, var amount) ->
                    describePurchase(buyer, amount);
            case Refund(var buyer, var amount) ->
                    describeRefund(buyer, amount);
            case Alert(var message, var severity) ->
                    describeAlert(message, severity);
            case null -> "UNKNOWN";
        };
    }

    static String describeLogin(String user, boolean success) {
        return (success ? "LOGIN_OK:" : "LOGIN_FAIL:") + label(user);
    }

    static String describePurchase(String buyer, int amount) {
        if (amount >= 100) {
            return "PURCHASE_HIGH:" + label(buyer) + ":" + amount;
        }
        if (amount > 0) {
            return "PURCHASE:" + label(buyer) + ":" + amount;
        }
        return "PURCHASE_INVALID";
    }

    static String describeRefund(String buyer, int amount) {
        return amount > 0
                ? "REFUND:" + label(buyer) + ":" + amount
                : "REFUND_INVALID";
    }

    static String describeAlert(String message, int severity) {
        return (severity >= 3 ? "ALERT_HIGH:" : "ALERT:") + label(message);
    }

    public static void main(String[] args) {
        Event[] samples = {
                new Login("Ada", true),
                new Login("Ada", false),
                new Login(null, true),
                new Purchase("Mai", 100),
                new Purchase("Mai", 5),
                new Purchase("Mai", 0),
                new Refund("Mai", 5),
                new Refund("Mai", -1),
                new Alert("disk", 3),
                new Alert("disk", 1),
                null
        };

        for (Event event : samples) {
            String original = before(event);
            String refactored = after(event);

            if (!original.equals(refactored)) {
                throw new AssertionError(
                        original + " != " + refactored);
            }
            System.out.println(refactored);
        }
    }
}
```

Biên dịch/chạy với JDK 21 trở lên:

```bash
javac --release 21 PatternCountReadabilityDemo.java
java PatternCountReadabilityDemo
```

**Stdout chính xác:**

```text
LOGIN_OK:Ada
LOGIN_FAIL:Ada
LOGIN_OK:(unknown)
PURCHASE_HIGH:Mai:100
PURCHASE:Mai:5
PURCHASE_INVALID
REFUND:Mai:5
REFUND_INVALID
ALERT_HIGH:disk
ALERT:disk
UNKNOWN
```

### Vì sao bản `after` dễ đọc hơn trong tình huống này?

- **Câu hỏi cấp cao rõ ràng:** event này thuộc nhóm `Login`, `Purchase`, `Refund` hay `Alert`?
- **Mỗi nhóm có tên xử lý:** `describePurchase` tập trung vào chính sách đối với amount, thay vì làm mọi người phải theo dõi các điều kiện `Purchase` trong cùng một switch dài.
- **Giảm lặp hình dạng pattern:** không cần viết ba lần `case Purchase(String buyer, int amount)`.
- **Giữ tính exhaustive:** `Event` là sealed interface chỉ cho phép bốn record implements. Các nhánh xử lý đủ bốn loại cùng `case null` nên không cần thêm `default`. Việc thêm một subtype được cho phép mà không bổ sung nhánh phù hợp có thể khiến compiler yêu cầu cập nhật switch.
- **Không đổi hợp đồng:** `before` và `after` cùng chọn các ngưỡng `amount >= 100` và `amount > 0`, xử lý `null` ở selector là `UNKNOWN`, và xử lý tên buyer/user null bằng `label`.
- **Có test so sánh:** `main` tính cả hai kết quả cho 11 input và ném `AssertionError` nếu khác nhau.

Bản sau **không “tốt hơn vì có đúng bốn pattern”**. Nó tốt hơn ở đây vì switch chính chỉ làm **điều phối một quyết định**, trong khi helper mang tên domain giữ các quyết định con. Nếu mỗi helper chỉ có đúng một câu lệnh tầm thường và không phục vụ việc hiểu tên gọi, việc tách quá mức có thể làm code khó lần theo hơn.

Ví dụ chỉ kiểm tra 11 trường hợp, không chứng minh tương đương tuyệt đối cho mọi input. Khi refactor sản phẩm thật, cần test biên và test tích hợp phù hợp với domain.

## 4. Tiêu chí nhận biết một method đã quá nhiều pattern

Không cần đạt một số lượng nhất định mới được tách. Hãy xem các **dấu hiệu thực tế**:

1. **Không thể tóm tắt mục tiêu method trong một câu.** Ví dụ method vừa phân loại request, vừa tính phí, vừa gọi API, vừa cập nhật trạng thái.
2. **Một nhóm domain xuất hiện qua nhiều case có guard.** Chẳng hạn `Purchase` có nhiều nhánh tương tác phức tạp với nhau; hiểu một nhánh buộc phải liên tục nhảy đến các nhánh khác.
3. **Thứ tự các pattern là một logic ẩn.** Các type pattern cha/con, null và guard chồng lấn đòi người đọc mô phỏng toàn bộ thứ tự.
4. **Record patterns lồng sâu khiến khó xác định biến.** Người đọc phải nhớ một loạt component và kiểu để hiểu hành động cuối cùng.
5. **Nhiều nhánh giống nhau trừ vài hằng số hay định dạng.** Có thể gom theo logic domain hoặc một helper, thay vì sao chép code.
6. **Test một quy tắc buộc thiết lập nhiều loại dữ liệu không liên quan.** Việc tách theo nhóm có thể tạo điểm kiểm thử trực tiếp.
7. **Một thay đổi nhỏ gây sửa nhiều vùng trong cùng switch.** Đây là dấu hiệu trách nhiệm chưa được phân chia phù hợp.
8. **Có nhiều side effect, xử lý ngoại lệ hay trạng thái dùng chung.** Khó suy ra nhánh nào có tác động và trong tình huống nào.
9. **Code review chỉ tập trung đếm case thay vì hiểu hợp đồng.** Số lượng nhiều có thể không phải vấn đề nếu các nhánh vẫn là một bảng phân loại rõ ràng.
10. **Method thực hiện nhiều bước xử lý tuần tự xen với matching.** Cần tách luồng xử lý với khâu chọn chiến lược.

Một **ngưỡng đội nhóm** ví dụ “từ một số nhóm pattern nhất định phải cân nhắc tách helper” chỉ nên là tín hiệu đặt câu hỏi trong review. Đừng đặt con số cứng làm lý do duy nhất để sửa mã hay tuyên bố trình biên dịch giới hạn số pattern.

## 5. Những cách giảm độ phức tạp phù hợp

### 5.1. Giữ switch điều phối, tách helper theo domain

Đây là giải pháp ít xâm lấn nhất khi `switch` chủ yếu chọn **nhóm nghiệp vụ**, như `after` trong chương trình mẫu.

```java
// Minh họa ý tưởng, các kiểu/handler phụ thuộc vào ứng dụng.
return switch (event) {
    case Login login -> describeLogin(login.user(), login.success());
    case Purchase purchase ->
            describePurchase(purchase.buyer(), purchase.amount());
    case Refund refund ->
            describeRefund(refund.buyer(), refund.amount());
    case Alert alert ->
            describeAlert(alert.message(), alert.severity());
    case null -> "UNKNOWN";
};
```

Trong đoạn này, pattern biến đối tượng `Login login` thay vì deconstruct bằng record pattern. Cả hai cách đều hợp lệ. Khi method chỉ điều phối, giữ record nguyên vẹn có thể tránh danh sách component quá dài. Cách chọn phụ thuộc vào chữ ký helper và mức độ dễ hiểu của domain.

### 5.2. Đưa guard phức tạp vào predicate có tên

Ví dụ:

```java
static boolean isHighValue(Purchase purchase) {
    return purchase.amount() >= 100;
}

// Trong một switch trên Event:
case Purchase p when isHighValue(p) ->
        describePurchase(p.buyer(), p.amount());
```

Điều kiện có tên dễ hiểu hơn một biểu thức Boolean dài. Tuy nhiên, **không cần giữ guard ở switch nếu quy tắc riêng của `Purchase` đã được đưa trọn vào helper**. Hai bước phân loại lặp lại (ở switch và helper) còn làm khó đọc hơn.

Một predicate dùng trong guard nên có kết quả ổn định, không sửa trạng thái. Guard có thể được đánh giá khi pattern khớp ngay cả khi sau đó nhánh đó không được chọn.

### 5.3. Dùng đa hình khi hành vi thật sự thuộc về kiểu

Nếu các biến thể event được thiết kế và sở hữu trong cùng một module, việc đặt hành vi trong các lớp/record tương ứng có thể phù hợp:

```java
// Ý tưởng thiết kế, không phải chương trình chạy độc lập:
interface RenderableEvent {
    String description();
}
```

Khi đó lời gọi `event.description()` có thể thay thế một switch nhiều nhánh. Nhưng **không ép đa hình bằng mọi giá**: nếu có nhiều cách phân loại độc lập (log, UI, persistence, reporting), đưa tất cả vào model domain có thể làm các kiểu dữ liệu phình to và trộn trách nhiệm. Với sealed hierarchy và một thao tác phân loại tập trung, một switch exhaustive rõ ràng có thể là lựa chọn tốt hơn.

### 5.4. Chuyển sang cấu trúc dữ liệu khi đây chỉ là ánh xạ đơn giản

Nếu chỉ ánh xạ một `enum`/key cố định sang tên hiển thị hay metadata, một `Map` hoặc bảng cấu hình có thể dễ bảo trì hơn nhiều nhánh `case`. Nhưng không nên thay các record patterns có logic kiểm tra khác nhau bằng một `Map<Class<?>, Handler>` chỉ vì muốn giảm số pattern: cách đó có thể làm mất tính exhaustiveness, khó xử lý quan hệ kế thừa và chuyển lỗi compile-time thành runtime.

### 5.5. Tránh trích xuất từng nhánh vô nghĩa

Anti-pattern:

```java
return switch (value) {
    case String s -> returnString(s);
    case Integer n -> returnInteger(n);
    case null -> returnNull();
    default -> returnOther();
};
```

Nếu bốn helper chỉ trả lại một literal hoặc một biểu thức quá đơn giản, việc nhảy giữa file/method có thể tốn công hơn đọc trực tiếp. Chỉ tách khi tên helper giải thích **ý nghĩa**, logic đủ đáng kể, có trách nhiệm riêng hoặc cần test/đổi độc lập.

## 6. Không được hy sinh tính đúng để giảm pattern

### 6.1. Không xóa nhánh subtype đặc biệt

Với type hierarchy có inheritance:

```java
class Document {}
class ConfidentialDocument extends Document {}
```

Nếu domain xử lý `ConfidentialDocument` đặc biệt, việc gộp mọi nhánh thành `case Document d` có thể làm mất hành vi. Ngoài ra, đặt `case Document d` **trước** `case ConfidentialDocument c` sẽ khiến nhánh sau bị dominated và compiler có thể báo lỗi.

“Giảm số pattern” không phải lý do để xóa một quy tắc mà người sử dụng dựa vào.

### 6.2. Không đổi cách xử lý null

`instanceof` với selector null thường trả `false`; trong pattern switch Java 21, selector null có hành vi riêng. Nếu muốn giữ giá trị mặc định như chương trình mẫu, dùng `case null -> "UNKNOWN"` một cách tường minh. `default` không phải lúc nào cũng xử lý null như `else` của chuỗi `if` cũ.

Một component record null khác selector null. Ví dụ `new Login(null, true)` là một `Login` hợp lệ về kiểu và được xử lý qua `label(null)`; code refactor không được tự tiện đổi thành lỗi nếu hợp đồng cũ chấp nhận dữ liệu đó.

### 6.3. Cẩn thận với tính exhaustive của sealed hierarchy

Trong ví dụ mẫu, `Event` là sealed interface với bốn record. Bỏ `default` **có chủ đích** giúp compiler phát hiện những thay đổi trong tập biến thể khi code cần được cập nhật. Nếu luôn thêm `default -> "UNKNOWN"`, một subtype được thêm trong tương lai có thể bị nuốt vào fallback thay vì buộc người viết định nghĩa cách xử lý.

Khi domain thật sự mở rộng động (plugin, interface có implementation ngoài kiểm soát), có thể cần fallback; đừng biến nó thành sealed chỉ để switch ngắn hơn mà chưa hiểu hợp đồng mở rộng.

### 6.4. Giữ thứ tự guard và ngưỡng

Trong chương trình mẫu, `amount == 100` đi vào `PURCHASE_HIGH` vì điều kiện `>= 100` được xét trước `> 0`. Nếu đổi thứ tự hoặc chọn `> 100`, kết quả ở biên thay đổi. Việc tách helper chỉ đúng khi giữ nguyên thứ tự và giá trị ranh giới.

### 6.5. Side effect của branch, guard và accessor

Một method dùng nhiều pattern có thể gọi record accessor/guard trong quá trình matching. Nếu những phương thức này có side effect, tách hoặc gộp pattern có thể đổi thời điểm/khả năng chúng được gọi. Khi cần refactor, ghi lại hành vi quan sát được và tránh giả định mọi pattern matching đều thuần túy. Các helper trong chương trình chính chỉ đọc input và trả chuỗi để minh họa thay đổi cấu trúc an toàn.

## 7. Test thế nào khi tách một method có nhiều pattern?

**Tối thiểu** nên có ma trận theo **loại input × trạng thái/điều kiện × fallback/null**. Với chương trình mẫu:

| Nhóm | Trường hợp cần test |
| --- | --- |
| `Login` | `success = true`, `false`, `user = null` |
| `Purchase` | `amount = 0`, số dương dưới 100, đúng 100, trên 100, số âm |
| `Refund` | số dương, 0, số âm |
| `Alert` | `severity` dưới 3, đúng 3, trên 3 |
| Selector | `null` |
| Tương lai | thêm một subtype `Event` mới: đảm bảo switch exhaustive được cập nhật |

Test ví dụ đã so sánh output của `before` và `after` trên 11 input. Trong code thực tế nên bổ sung thêm input biên chưa có trong demo, và nếu có side effect thì kiểm tra event, error, số lần thao tác hoặc tương tác với dependency quan trọng.

**Đừng cho hàm mới và cũ chạy song song trên production chỉ để so sánh** nếu chúng có thể cùng gửi tiền, ghi database hoặc phát event: sẽ tạo side effect kép. Sử dụng unit test trong môi trường cô lập, fake/mock hoặc test môi trường có kiểm soát. Một test tương đương đơn giản có ích cho logic thuần túy, nhưng không chứng minh mọi trạng thái của domain đều được xử lý.

Khi thay đổi lớn, refactor theo nhiều PR nhỏ, kiểm tra từng nhóm. Mọi thay đổi về nghiệp vụ nên được đánh dấu là behavior change có chủ đích, không gọi là “cleanup”.

## 8. Các lỗi thường gặp khi “giảm số pattern”

1. **Áp dụng một con số cứng như quy tắc ngôn ngữ.** Java không có giới hạn số pattern theo method được công bố như quy tắc thiết kế; code review nên dùng độ dễ hiểu và testability.
2. **Gộp theo kiểu cha làm mất nhánh con.** Quan hệ subclass không đồng nghĩa cùng cách xử lý nghiệp vụ.
3. **Tách helper quá vụn.** Một switch gọn bị biến thành nhiều lần nhảy sang helper không có ý nghĩa.
4. **Giấu guard phức tạp vào tên mơ hồ.** `check1` hoặc `valid` không nói rõ domain; nên đặt tên thể hiện quy tắc.
5. **Lặp lại điều kiện ở cả switch và helper.** Khó giữ nhất quán các ngưỡng và thứ tự.
6. **Chuyển code sang `Map<Class<?>, Handler>` mà không xét inheritance.** Có thể thay đổi cách chọn handler và mất kiểm tra compile-time.
7. **Thêm `default` vô điều kiện cho sealed type.** Có thể che việc thêm subtype chưa được xử lý.
8. **Quên null selector và nullable component.** Thay đổi behavior dù số pattern ít đi.
9. **Thay đổi thứ tự guard, dẫn tới kết quả khác ở giá trị biên.** Nên kiểm thử `<`, `==`, `>` quanh ngưỡng.
10. **Bỏ sót side effect.** Đếm pattern không thể hiện số lượng thao tác bên ngoài, exception hoặc transaction.
11. **Tưởng rằng mọi switch expression có nhiều case là xấu.** Một bảng chuyển đổi nhất quán với nhiều nhánh ngắn có thể dễ đọc hơn việc tách tùy tiện.
12. **Chỉ đo độ dài method.** Số dòng giảm không chứng minh mức phức tạp nghiệp vụ hay độ dễ bảo trì đã giảm.

## 9. Checklist review: có nên tách method không?

Trước khi refactor, tự trả lời:

- [ ] Method có **một mục đích rõ ràng** mà tên method diễn đạt đúng không?
- [ ] Các pattern có thể **nhóm theo một loại domain hay trách nhiệm** thay vì theo chi tiết kỹ thuật không?
- [ ] Người đọc có phải nhớ nhiều biến/tầng record lồng nhau hoặc guard chồng lấn để hiểu một nhánh không?
- [ ] Tên helper mới có giải thích “vì sao/điều gì” thay vì chỉ lặp lại một dòng code không?
- [ ] Các nhánh có giữ nguyên thứ tự ưu tiên, ranh giới `when`, null và fallback không?
- [ ] Tính exhaustive của sealed hierarchy có được giữ, tránh `default` che thiếu case không?
- [ ] Side effect, exception và phạm vi biến pattern có thay đổi không?
- [ ] Có test cho từng nhóm biến thể và trường hợp biên trước/sau refactor không?
- [ ] Kết quả có giúp code review nhận ra quy tắc nghiệp vụ nhanh hơn mà không phải mở quá nhiều helper không?

**Kết luận:** **Không giới hạn số pattern bằng một số tuyệt đối.** Hãy giới hạn **số quyết định và trách nhiệm phải hiểu đồng thời trong một method**. Khi `switch` là bảng phân loại rõ ràng, có thể giữ nguyên nhiều case. Khi method trộn nhiều nhóm domain, guards phức tạp, nested patterns và side effects, hãy tách thành một switch điều phối dễ đọc cùng các helper có tên rõ ràng—đồng thời kiểm thử để chứng minh không thay đổi hành vi.

### Tài liệu tham khảo

- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21 — `14.11 (switch statements) và `14.30 (patterns): https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html
