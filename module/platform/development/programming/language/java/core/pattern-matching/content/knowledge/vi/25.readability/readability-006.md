# Giữ nhánh case cùng mức trừu tượng trong Java Pattern Matching

## 1. “Cùng mức trừu tượng” là gì?

Trong một `switch`, mỗi nhánh `case` nên trả lời **cùng một câu hỏi ở cùng cấp độ ý nghĩa**. Nếu `switch` đóng vai trò chọn bộ xử lý cho sự kiện, các nhánh nên cùng chọn bộ xử lý; nếu nó phân loại hình học, các nhánh nên cùng trả kết quả phân loại; nếu nó chuyển một kiểu dữ liệu thành DTO, các nhánh nên cùng trả DTO tương ứng.

Ví dụ cách trình bày ý định rõ ràng:

```java
// Minh họa; các kiểu và handler được định nghĩa ở lớp phù hợp.
return switch (event) {
    case OrderCreated created -> handleCreated(created);
    case PaymentReceived payment -> handlePayment(payment);
    case OrderCancelled cancelled -> handleCancelled(cancelled);
};
```

Cả ba nhánh có một mẫu ý nghĩa: **sự kiện nào → quy tắc xử lý của sự kiện đó**. Phần `switch` không cần bày ra việc xác thực số lượng, kiểm tra tiền thanh toán hoặc định dạng lý do hủy.

Một `switch` khó đọc thường làm người đọc phải đổi liên tục giữa các cấp:

- Một nhánh chỉ trả về tên loại sự kiện.
- Một nhánh tự truy cập database và ghi log.
- Một nhánh gọi service cấp ứng dụng.
- Một nhánh xử lý một chuỗi ký tự và ném exception.
- Một nhánh có hàng chục điều kiện nghiệp vụ trong `when`.

Các nhánh trên có thể hợp lệ về cú pháp, nhưng **trách nhiệm của cả `switch` không còn rõ**. Người đọc khó dự đoán cần thay đổi chỗ nào khi thêm một loại đầu vào mới hoặc sửa chính sách xử lý.

**Quan trọng:** cùng mức trừu tượng không yêu cầu các nhánh có số dòng bằng nhau, cùng dùng helper hoặc có cùng độ phức tạp. Một phép tính rất nhỏ có thể để inline nếu nó thể hiện rõ cùng mục đích. Mục tiêu là giảm chi phí đọc hiểu và rủi ro khi sửa code, không phải làm các nhánh giống nhau về hình thức.

Bài học thuộc Java Core Pattern Matching. Pattern matching cho `switch` (JEP 441) và record patterns (JEP 440) đều chính thức từ **Java 21**. Chương trình hoàn chỉnh dưới đây dùng **JDK 21+**, không cần `--enable-preview`. Các nguyên tắc thiết kế vẫn có ích với `switch` enum hoặc truyền thống.

## 2. Xác định một trách nhiệm cho switch

Trước khi code, viết một câu: **“Switch này dùng để ...”**.

| Vai trò | Cách diễn đạt mỗi case ở cùng mức | Dấu hiệu đang lẫn mức |
| --- | --- | --- |
| Phân loại | `case` nào cũng xác định một nhãn/domain state | Có case tự lưu database, có case chỉ trả nhãn |
| Điều phối | `case` nào cũng chọn một handler phù hợp | Một case dispatch, case khác tự làm tất cả bước chi tiết |
| Chuyển đổi | Các case cùng trả DTO/result có cùng hợp đồng | Một case trả DTO, case khác trả object hạ tầng |
| Quyết định | Các case đều tạo `Decision`/`Result` về một nghiệp vụ | Một case ra quyết định, case khác in console và không trả kết quả |
| Diễn giải | Mỗi case biến một giá trị thành cùng dạng mô tả | Một case parse/call API ngoài, case khác format String |

Không phải cứ các nhánh cùng trả `String` là cùng mức trừu tượng. Ví dụ, một case tạo chuỗi nhãn từ field, còn case khác gọi HTTP để cập nhật đơn hàng rồi trả chuỗi, thì **hợp đồng tác dụng phụ khác nhau** dù kiểu trả về giống nhau.

Hãy dùng các câu hỏi:

1. Người đọc có thể dự đoán vai trò mọi case sau khi đọc tên hàm `switch` không?
2. Mỗi case có cùng loại output/action tại boundary đó không?
3. Muốn thêm subtype mới, có một nơi rõ ràng để đặt xử lý tương ứng không?
4. Có case nào buộc người đọc hiểu chi tiết thấp như SQL, networking hay format byte khi những case khác chỉ diễn đạt nghiệp vụ không?

Nếu câu trả lời là không, xem lại ranh giới trách nhiệm.

## 3. Phát hiện switch trộn dispatch với chi tiết xử lý

Ví dụ dưới đây **chỉ là phác họa**, không phải chương trình chạy độc lập; các service/repository được giả định đã tồn tại:

```java
switch (event) {
    case OrderCreated created -> {
        if (created.orderId() == null ||
                created.orderId().isBlank()) {
            throw new IllegalArgumentException("Invalid order id");
        }
        repository.insert(created.orderId(), created.itemCount());
        audit.write("created: " + created.orderId());
    }

    case PaymentReceived payment ->
        paymentService.handle(payment);

    case OrderCancelled cancelled ->
        System.out.println("Cancel " + cancelled.orderId());
}
```

Vấn đề không phải có nhiều dòng mà là **trộn ba vai trò**: kiểm tra dữ liệu + persistence, dispatch service, và hiển thị console. Khi thay đổi quy tắc xử lý, ta phải soi một phần của `switch` và một service bên ngoài, rồi kiểm tra những side effect không đồng đều.

Việc viết lại phần điều phối theo cùng một kiểu:

```java
// Phác họa: handler có sẵn trong tầng ứng dụng.
switch (event) {
    case OrderCreated created ->
        createdHandler.handle(created);
    case PaymentReceived payment ->
        paymentHandler.handle(payment);
    case OrderCancelled cancelled ->
        cancelledHandler.handle(cancelled);
}
```

làm rõ cấu trúc “chọn đúng người xử lý”. Còn điều kiện hợp lệ, transaction, audit, retry và persistence phải đặt tại tầng có quyền chịu trách nhiệm tương ứng. **Không được xem việc di chuyển side effect là refactor chắc chắn tương đương**: thứ tự thực thi, phạm vi transaction, exception và chính sách retry có thể thay đổi.

## 4. Pattern matching hỗ trợ cách tổ chức này ra sao?

### Type patterns

```java
case OrderCreated created -> handleCreated(created);
```

Nhánh này kiểm tra kiểu và ràng buộc biến `created` có kiểu `OrderCreated`. Không phải tự viết `instanceof` + cast. Nếu tất cả case đều theo mẫu “kiểu nào → xử lý loại đó”, cấu trúc rất dễ nhìn.

### Record patterns

```java
record Point(int x, int y) {}

// Minh họa trong switch phù hợp:
case Point(var x, var y) -> describePoint(x, y);
```

Record pattern vừa kiểm tra `Point`, vừa tách các component theo thứ tự khai báo. Nếu mục đích của `switch` là chuyển các cấu trúc thành cùng một dạng mô tả, tách hai component trực tiếp có thể rõ ý.

Tuy nhiên, pattern lồng sâu không mặc nhiên làm ý định rõ hơn:

```java
record Customer(String name, boolean vip) {}
record Purchase(Customer customer, long amount) {}

// Minh họa trong switch phù hợp:
case Purchase(Customer(var name, var vip), var amount)
        when vip && amount >= 1000L ->
    makePriorityDecision(name, amount);
```

Nếu chỉ một điều kiện `vip` và một ngưỡng tiền, mã có thể vẫn dễ đọc. Nhưng nếu `when` thêm kiểm tra hạn mức, mã vùng, ngày hiệu lực, tên khách, cấu hình feature flag và trạng thái trong database, phần `switch` đang biết quá nhiều chi tiết. Có thể chuyển sang `case Purchase p when isPriorityPurchase(p) -> ...`, hoặc `case Purchase p -> classifyPurchase(p)` nếu muốn switch chỉ dispatch theo kiểu.

### `when` và điều kiện

`when` cho phép phân biệt các trường hợp **cùng kiểu** nhưng khác quy tắc. Việc dùng guard phù hợp khi guard **ngắn, cùng ý nghĩa với việc chọn case**. Guard phức tạp nên được đặt tên hoặc đưa vào handler.

Đọc kỹ thứ tự:
- Pattern phải khớp trước; sau đó mới đánh giá guard.
- Nếu guard sai, `switch` xét nhánh khác.
- Biến pattern có phạm vi trong `when` và thân nhánh, không tự động tồn tại trong case khác.
- Case có guard/cụ thể thường phải đứng **trước** case bao phủ rộng hơn.

## 5. Chương trình Java 21 hoàn chỉnh: mọi case cùng trả Decision

Mô hình ba sự kiện đơn hàng: tạo đơn, nhận thanh toán và hủy đơn. Chương trình minh họa **phân loại yêu cầu thành quyết định**, không thực hiện thanh toán, ghi cơ sở dữ liệu hay cập nhật hệ thống thật.

Tạo file **`SameLevelSwitchDemo.java`**:

```java
public class SameLevelSwitchDemo {

    sealed interface OrderEvent
            permits OrderCreated, PaymentReceived, OrderCancelled {}

    record OrderCreated(String orderId, int itemCount)
            implements OrderEvent {}

    record PaymentReceived(String orderId, long amount)
            implements OrderEvent {}

    record OrderCancelled(String orderId, String reason)
            implements OrderEvent {}

    record Decision(String status, String detail) {}

    static boolean hasId(String id) {
        return id != null && !id.isBlank();
    }

    // Switch chỉ làm một việc: điều phối tới bộ quyết định phù hợp.
    static Decision route(OrderEvent event) {
        return switch (event) {
            case null ->
                new Decision("REJECTED", "Không có sự kiện");
            case OrderCreated created ->
                handleCreated(created);
            case PaymentReceived payment ->
                handlePayment(payment);
            case OrderCancelled cancelled ->
                handleCancelled(cancelled);
        };
    }

    static Decision handleCreated(OrderCreated event) {
        if (!hasId(event.orderId())) {
            return new Decision("REJECTED", "Thiếu mã đơn hàng");
        }
        if (event.itemCount() <= 0) {
            return new Decision(
                "REJECTED", "Số mặt hàng không hợp lệ");
        }
        return new Decision(
            "CREATED",
            event.orderId() + ": " + event.itemCount() + " mặt hàng");
    }

    static Decision handlePayment(PaymentReceived event) {
        if (!hasId(event.orderId())) {
            return new Decision("REJECTED", "Thiếu mã đơn hàng");
        }
        if (event.amount() <= 0) {
            return new Decision(
                "REJECTED", "Số tiền không hợp lệ: " + event.orderId());
        }
        return new Decision(
            "PAID", event.orderId() + ": " + event.amount());
    }

    static Decision handleCancelled(OrderCancelled event) {
        if (!hasId(event.orderId())) {
            return new Decision("REJECTED", "Thiếu mã đơn hàng");
        }
        if (event.reason() == null || event.reason().isBlank()) {
            return new Decision(
                "REJECTED", "Thiếu lý do hủy: " + event.orderId());
        }
        return new Decision(
            "CANCELLED", event.orderId() + ": " + event.reason());
    }

    static void show(OrderEvent event) {
        Decision decision = route(event);
        System.out.println(
            decision.status() + " | " + decision.detail());
    }

    public static void main(String[] args) {
        show(new OrderCreated("O-1", 2));
        show(new PaymentReceived("O-1", 1200));
        show(new OrderCancelled("O-2", "Trùng đơn"));
        show(new PaymentReceived("O-3", 0));
        show(new OrderCreated("  ", 1));
        show(new OrderCancelled("O-4", ""));
        show(null);
    }
}
```

Biên dịch bằng JDK 21 hoặc mới hơn:

```bash
javac --release 21 -encoding UTF-8 SameLevelSwitchDemo.java
java SameLevelSwitchDemo
```

Kết quả dự kiến:

```text
CREATED | O-1: 2 mặt hàng
PAID | O-1: 1200
CANCELLED | O-2: Trùng đơn
REJECTED | Số tiền không hợp lệ: O-3
REJECTED | Thiếu mã đơn hàng
REJECTED | Thiếu lý do hủy: O-4
REJECTED | Không có sự kiện
```

### Vì sao switch trong chương trình này ở cùng mức?

**`route` chỉ điều phối.** Các case `OrderCreated`, `PaymentReceived`, `OrderCancelled` đều chuyển input sang một helper trả `Decision`. Người đọc hiểu cấu trúc trước khi phải xem chi tiết từng quy tắc.

**Các helper ở mức chính sách.** `handleCreated` có thể kiểm tra số lượng, `handlePayment` kiểm tra số tiền, `handleCancelled` kiểm tra lý do. Các hàm không cần số dòng bằng nhau; điều quan trọng là mỗi hàm tự xử lý chính sách của một event.

**`hasId` dùng chung quy tắc cấp thấp.** Việc kiểm tra null/blank của ID được đặt tên và chỉ viết một lần. Nếu sau này domain đổi định dạng ID, nơi sửa rõ ràng hơn so với lặp guard dài trong nhiều case.

**`Decision` thống nhất output.** Nơi gọi `show` không phải biết mỗi handler trả một kiểu khác nhau; nó chỉ xử lý `status` và `detail`. Trong hệ thống thật có thể dùng enum trạng thái hoặc một sealed result hierarchy có contract mạnh hơn.

**`case null` xử lý lỗi biên theo cùng kiểu output.** Mặc dù không gọi handler, case null vẫn làm đúng việc của switch: quyết định kết quả cho một input. “Cùng mức” không đòi mọi case đều gọi hàm.

**`sealed interface` hỗ trợ exhaustive switch.** Bởi `OrderEvent` chỉ cho phép ba subtype trong mô hình này, một `switch expression` có các type pattern tương ứng có thể exhaustive mà không cần `default`. Khi bổ sung subtype permitted mới, compiler buộc đánh giá lại nơi dispatch nếu chưa có nhánh bao phủ nó.

### Tình huống cần kiểm thử

| Input | Lý do | Output |
| --- | --- | --- |
| `new OrderCreated("O-1", 2)` | ID có giá trị, số mặt hàng dương | `CREATED | O-1: 2 mặt hàng` |
| `new PaymentReceived("O-1", 1200)` | ID có giá trị, tiền dương | `PAID | O-1: 1200` |
| `new OrderCancelled("O-2", "Trùng đơn")` | Có ID và lý do | `CANCELLED | O-2: Trùng đơn` |
| `new PaymentReceived("O-3", 0)` | Tiền không dương | `REJECTED | Số tiền không hợp lệ: O-3` |
| `new OrderCreated("  ", 1)` | ID chỉ gồm khoảng trắng | `REJECTED | Thiếu mã đơn hàng` |
| `new OrderCancelled("O-4", "")` | Lý do rỗng | `REJECTED | Thiếu lý do hủy: O-4` |
| `null` | Chính sách selector null | `REJECTED | Không có sự kiện` |

Bảng giúp kiểm tra phân loại và tính nhất quán của output. Đây là quy tắc demo; không thay thế các yêu cầu giao dịch thật như idempotency, authorization, trạng thái đơn, retry và atomic transaction.

## 6. Cùng kiểu output chưa đủ: còn phải đồng nhất tác dụng phụ

Một `switch expression` có thể có các case cùng trả `String` nhưng khác xa trách nhiệm:

```java
// PHÁC HỌA: các đối tượng hạ tầng không được khai báo tại đây.
return switch (event) {
    case OrderCreated c -> "New: " + c.orderId();
    case PaymentReceived p ->
        paymentService.record(p).toString();
    case OrderCancelled c ->
        repository.delete(c.orderId()) ? "OK" : "FAILED";
};
```

Nhánh đầu chỉ format; nhánh thứ hai gọi dịch vụ; nhánh cuối thay đổi persistence. Tất cả cùng trả `String`, nhưng **cùng kiểu tĩnh không đồng nghĩa cùng abstraction**.

Tổ chức rõ hơn:

```text
OrderEvent
    |
    v
switch theo subtype          = CHỌN bộ xử lý
    |
    +--> handleCreated       = QUYẾT ĐỊNH cho Create
    +--> handlePayment       = QUYẾT ĐỊNH cho Payment
    +--> handleCancelled     = QUYẾT ĐỊNH cho Cancel
    |
    v
Decision / Result            = HỢP ĐỒNG chung
    |
    v
delivery boundary            = HÀNH ĐỘNG ngoài (nếu có)
```

Không phải mọi ứng dụng đều cần kiến trúc nhiều tầng như sơ đồ. Đây là cách phân định trách nhiệm để suy nghĩ: bản thân `switch` cần bộc lộ lựa chọn ở cấp mà phương thức của nó được đặt tên.

### Side effect và refactor

Nếu code cũ viết audit log trước khi ghi repository, chuyển sang helper mới có thể vô tình đảo thứ tự. Nếu một nhánh bắt exception còn nhánh khác ném ra ngoài, gom chúng vào handler cũng có thể làm hợp đồng lỗi đổi. Vì vậy cần kiểm tra:

- thứ tự thực hiện I/O, audit, metric;
- phạm vi transaction;
- trường hợp lỗi từng bước;
- idempotency và retry;
- thời điểm tạo output cho caller.

Refactor để dễ đọc **không miễn trừ yêu cầu bảo toàn hành vi**.

## 7. Guard `when` và mức trừu tượng

Guard nên là một điều kiện dễ hiểu trực tiếp về **lựa chọn nhánh**:

```java
// Nhãn case minh họa trong switch có các handler phù hợp.
case PaymentReceived p when p.amount() <= 0 ->
    rejectPayment(p);
case PaymentReceived p ->
    acceptPayment(p);
```

Cả hai case ở cùng mức “đưa ra quyết định cho payment”. Guard ngắn chỉ phân biệt trường hợp đặc biệt.

Nếu quy tắc bao gồm mười điều kiện, thay vì:

```java
// PHÁC HỌA: guard dài trộn nhiều chính sách.
case PaymentReceived p
        when p.amount() > 0
            && p.orderId() != null
            && !p.orderId().isBlank()
            && isCustomerActive(p)
            && isWithinCreditLimit(p)
            && passesRegionalPolicy(p) ->
    acceptPayment(p);
```

có thể đặt tên:

```java
case PaymentReceived p when isEligiblePayment(p) ->
    acceptPayment(p);
case PaymentReceived p ->
    rejectPayment(p);
```

Tuy nhiên, helper `isEligiblePayment` nên là điều kiện có hợp đồng rõ ràng, có test và tránh side effect không mong đợi. Không đặt một tên chung chung như `check(p)` khiến reviewer phải mở hàm mới hiểu ý.

### Dominance: nhánh cụ thể phải đến trước

Ví dụ **cố ý sai, không biên dịch**:

```java
case PaymentReceived p -> acceptPayment(p);
case PaymentReceived p when p.amount() <= 0 ->
    rejectPayment(p); // Dominated bởi case rộng phía trước.
```

`case PaymentReceived p` ở trên nhận mọi `PaymentReceived` không-null. Nhánh guard bên dưới sẽ không thể tới; compiler báo dominance. Viết nhánh có guard trước rồi nhánh tổng quát.

Một switch có ý định rõ nhưng thứ tự case sai vẫn là code sai. Khi review, kiểm tra cả **level of abstraction** lẫn các quy tắc Java về pattern matching.

### Pattern thất bại và guard false là hai việc khác nhau

- Input `OrderCreated` không khớp pattern `PaymentReceived p`.
- Input `PaymentReceived("O-1", 100)` khớp type pattern nhưng guard `amount <= 0` trả false.
- Guard false khiến `switch` xét nhánh tiếp theo; các biến của case đang xét không tự động có scope ở case khác.
- Với record pattern lồng, một component record con null có thể làm toàn bộ pattern không khớp trước khi guard được đánh giá.

Những khác biệt này phải được thể hiện bằng case dự phòng rõ ràng hoặc test tương ứng.

## 8. Lúc nào để inline, lúc nào tách helper?

**Giữ inline khi:**

- Biểu thức ngắn và thể hiện đúng cấp ý định của cả switch.
- Một case chỉ trả nhãn, chuyển đổi một giá trị hoặc gọi một phép toán đơn giản.
- Việc mở thêm helper làm mất tính trực tiếp mà không tăng khả năng tái sử dụng hay kiểm thử.

Ví dụ:

```java
// Minh họa trong phương thức có enum State:
return switch (state) {
    case NEW -> "Mới";
    case PAID -> "Đã thanh toán";
    case CANCELLED -> "Đã hủy";
};
```

Đây là một mapping ở cùng mức. Việc buộc từng nhánh gọi `newLabel()`, `paidLabel()`, `cancelledLabel()` chỉ để đạt “một dòng gọi hàm” có thể làm code khó đọc hơn.

**Tách helper khi:**

- Một nhánh gồm nhiều quy tắc nghiệp vụ độc lập.
- Pattern lồng sâu tạo nhiều biến chỉ dùng ở một số điều kiện.
- Cùng validation lặp ở nhiều case.
- Nhánh có side effects phải quản lý transaction/lỗi.
- Cần unit test một chính sách mà không chạy toàn bộ bộ điều phối.
- Tên helper mô tả một ý nghĩa domain rõ ràng hơn chuỗi điều kiện dài.

**Không tách chỉ vì số dòng.** Một case có khối `-> { ... }` dài hơn vẫn có thể hợp lý nếu toàn bộ khối cùng tạo một kết quả nhỏ và có liên hệ trực tiếp. Một helper vừa tách ra mà cần mười tham số có thể là dấu hiệu abstraction chưa tốt.

## 9. Null, sealed và exhaustiveness trong cùng một switch

Trong code Java 21 ở mục 5:

```java
return switch (event) {
    case null -> new Decision("REJECTED", "Không có sự kiện");
    case OrderCreated created -> handleCreated(created);
    case PaymentReceived payment -> handlePayment(payment);
    case OrderCancelled cancelled -> handleCancelled(cancelled);
};
```

`case null` quyết định cách xử lý selector null. Trong enhanced `switch` dùng pattern matching, không nên dựa vào `default` như một cách bắt null thay thế. Việc đặt một case null rõ chính sách vẫn cùng cấp **quyết định kết quả**, không buộc phải gọi handler.

Vì kiểu selector là một `sealed interface` với ba subtype, switch expression có thể exhaustive mà không cần `default`. Điều này có ích: thêm subtype permitted mới thường buộc cập nhật phần dispatch khi các case cũ chưa bao phủ subtype ấy.

Ngược lại, khi selector có kiểu `Object`, phải cân nhắc các đối tượng ngoài tập event. Một switch expression chỉ xử lý vài subtype cụ thể sẽ không exhaustive nếu không có nhánh đủ rộng. Lựa chọn thêm `default`, type pattern tổng quát hay thay đổi API phải theo hợp đồng của phương thức, không phải vì muốn ít code.

**Lưu ý:** một `default` rất rộng có thể che đi yêu cầu bổ sung xử lý một biến thể domain mới. Đừng thêm `default` vô điều kiện vào mọi switch sealed chỉ để tránh compiler nhắc sửa code khi hệ phân cấp được mở rộng.

## 10. Quy trình refactor giữ hành vi

**Bước 1. Chốt câu mô tả switch.** “Chuyển `OrderEvent` thành `Decision`” cụ thể hơn “xử lý event”.

**Bước 2. Liệt kê input và đường đi.** Có subtype nào, guard nào, null, input sai và default/fallback nào? Với switch expression, đã exhaustive chưa?

**Bước 3. Tách điều phối và chi tiết.** Đánh dấu đoạn gọi repository, mạng, audit, biến đổi dữ liệu, validation hoặc tính toán phụ không cùng vai trò với các case khác.

**Bước 4. Đặt tên helper theo nghiệp vụ.** `handlePayment` hoặc `toPaymentDecision` cho thấy phạm vi tốt hơn `run1` hay `doIt`.

**Bước 5. Cố định hợp đồng output.** Với ví dụ, các handler đều trả `Decision`. Trong thực tế có thể là sealed result types biểu đạt lỗi/thành công bằng kiểu an toàn hơn.

**Bước 6. Bảo toàn side effects.** Ghi lại thứ tự và điều kiện của repository, audit, lỗi, retry, transaction trước khi chuyển code sang vị trí khác.

**Bước 7. Kiểm thử before/after.** So sánh output cho từng subtype, guard true/false, null và dữ liệu không hợp lệ. Với I/O, test cả exception, rollback và thứ tự lời gọi.

**Bước 8. Đọc lại switch.** Nếu reviewer nhìn các case và biết ngay chương trình đang chọn chính sách nào, refactor đang đạt mục đích. Nếu phải nhảy qua nhiều helper tên mơ hồ mới hiểu chức năng cơ bản, có thể đã tách quá mức.

Một thay đổi có thể rút ngắn switch nhưng vẫn không cải thiện thiết kế nếu chỉ chuyển khối code sang `helper1`/`helper2` mà không đặt đúng trách nhiệm và hợp đồng.

## 11. Checklist code review

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| Switch có một trách nhiệm được đặt tên không? | Tên phương thức và output có cùng ý nghĩa |
| Mỗi case có trả lời cùng câu hỏi không? | Không lẫn dispatch/validation/IO tùy tiện |
| Các case có cùng hợp đồng kết quả không? | Kiểu và ý nghĩa output/side effect nhất quán |
| Guard có ngắn và ở cấp ý nghĩa phù hợp không? | Tránh điều kiện nghiệp vụ dài không tên |
| Case cụ thể có nằm trước case tổng quát không? | Tránh dominance |
| Pattern variable có đúng scope không? | Dùng trong guard/nhánh khớp, không lộ sang case khác |
| Record pattern có đi sâu hơn mức cần thiết không? | Tránh tách nhiều component không sử dụng |
| Có phân biệt record con null với `var` component null không? | Pattern con có thể không khớp trước khi xét guard |
| Null selector có chính sách rõ không? | `case null` hoặc chặn trước switch |
| Sealed hierarchy được xử lý exhaustive có chủ đích không? | Thêm subtype mới không bị quên |
| Refactor có test output và side effects không? | Không chỉ so sánh happy path |
| Helper có tên nêu intent không? | Không tạo lớp trừu tượng rỗng |

## 12. Lỗi phổ biến khi cố gắng giữ case đồng cấp

| Hiểu lầm | Rủi ro | Gợi ý |
| --- | --- | --- |
| “Mọi nhánh phải một dòng” | Tạo helper vô nghĩa, tăng điều hướng | Đánh giá theo ý định, không theo số dòng |
| “Cùng trả `String` là đủ” | Một nhánh có side effect, nhánh khác chỉ format | Phân biệt output type và responsibility |
| “Pattern matching tự bảo đảm clean code” | Cây nested quá sâu, guard dày đặc | Đặt boundary và tên chính sách phù hợp |
| Đặt `case Parent p` trước `case Child c` | Case con bị che, có thể không biên dịch | Đặt case cụ thể trước |
| Đặt case không guard trước cùng type có guard | Guard case bị dominated | Đảo thứ tự |
| Để nhiều I/O trong nhánh dispatch | Khó test và không đồng đều | Chuyển sang tầng chịu trách nhiệm |
| Chuyển side effect để làm đẹp | Thay đổi thứ tự, transaction, exception | Viết test và kiểm chứng |
| Dùng `default` rộng cho mọi sealed hierarchy | Thêm subtype không buộc sửa switch | Cân nhắc exhaustive type cases |
| Coi `default` là nhánh null chắc chắn | Runtime có thể xử lý null khác dự kiến | Đặt chính sách null tường minh |
| Trích helper nhưng đặt tên `handle`/`check` quá chung | Reviewer vẫn phải mở sâu | Đặt tên theo domain rule |
| Nhầm guard false và pattern không khớp | Nhánh fallback sai | Test từng kiểu thất bại |
| Nhiều case trả các lỗi không cùng hợp đồng | Caller khó sử dụng | Định nghĩa result/decision chung |

## 13. Bài tập thực hành

**Bài 1 — Viết một câu mô tả.** Với switch phác họa ở mục 3, hãy xác định vai trò chung mong muốn. Đánh dấu từng dòng thuộc dispatch, validation, persistence và hiển thị. Refactor thành ba handler không cần thay đổi hợp đồng xử lý.

**Bài 2 — Cấu trúc sealed.** Khai báo `sealed interface Command permits Create, Update, Delete` và viết switch expression điều phối đến ba handler cùng trả `Decision`. Có chính sách null rõ ràng.

**Bài 3 — Dominance.** Viết hai case `PaymentReceived`: nhánh amount không hợp lệ và nhánh tổng quát. Thử đảo vị trí để quan sát lỗi compiler.

**Bài 4 — Không over-engineer.** Với mapping enum state sang ba nhãn hiển thị, giải thích vì sao không nhất thiết cần ba helper riêng dù mỗi nhánh chỉ có một biểu thức.

**Bài 5 — Bổ sung subtype.** Chạy `SameLevelSwitchDemo.java`. Thêm `record OrderRefunded(String id, long amount) implements OrderEvent {}` và khai báo vào `permits`. Xem compiler yêu cầu cập nhật `route` ra sao; thiết kế `handleRefunded` trả cùng `Decision`.

**Bài 6 — Test guard.** Thêm `PaymentReceived("O-5", -10)` và `OrderCancelled("O-6", null)` vào `main`. Dự đoán trạng thái và detail từ các helper; chạy để xác nhận.

**Bài 7 — Policy và I/O.** Một payment handler phải gửi audit sau khi xử lý thành công. Bạn sẽ đặt audit ở đâu để bộ điều phối vẫn dễ đọc? Liệt kê các test cho trường hợp audit ném exception.

**Bài 8 — Record pattern.** Với `Purchase(Customer(var name, var vip), var amount) when vip && amount >= 1000L`, so sánh giữ inline và chuyển quy tắc sang `isPriorityPurchase`. Nêu rõ khi nào deconstruction ngắn thể hiện ý định tốt hơn, khi nào helper dễ bảo trì hơn.

## 14. Ghi nhớ

**Giữ các nhánh `case` cùng mức trừu tượng** nghĩa là các case bộc lộ cùng **loại quyết định hoặc hành động**. Trong Java 21, type pattern, record pattern, `when` và sealed hierarchy làm bộ điều phối ngắn, đúng kiểu và dễ bao phủ trường hợp mới; nhưng chúng không thay thế việc thiết kế trách nhiệm.

Hãy:
- Viết một câu mô tả nhiệm vụ của switch.
- Đặt các nhánh ở cùng cấp domain/dispatch/chuyển đổi.
- Đưa validation, I/O hoặc quy tắc dài sang đúng helper/layer khi điều đó giúp dễ hiểu.
- Giữ output và chính sách null nhất quán, đồng thời kiểm tra dominance và exhaustiveness.
- Không ép mọi case về một dòng hoặc tách helper chỉ để mã trông đồng dạng.
- Khi refactor, so sánh cả kết quả, exception, thứ tự tác dụng phụ và transaction.

### Nguồn tham khảo

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
