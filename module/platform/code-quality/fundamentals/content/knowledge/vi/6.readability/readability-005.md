# Giới hạn mức lồng nhau và khoảng cách giữa các thông tin liên quan

Trong chương **Khả năng đọc** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta xem xét hai yếu tố thường làm mã nguồn khó hiểu dù cú pháp vẫn hợp lệ: **cấu trúc điều khiển lồng nhau quá sâu** và **các thông tin cần để hiểu một hành vi bị đặt cách xa nhau**.

Mục tiêu xuyên suốt của module là hiểu những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một phương thức dễ đọc giúp người bảo trì nhanh chóng biết điều gì xảy ra, điều kiện nào quyết định kết quả và phải sửa ở đâu. Khi phải ghi nhớ nhiều điều kiện từ các tầng `if`, hoặc liên tục chuyển giữa các file để ghép một quy tắc đơn giản, chi phí hiểu và nguy cơ bỏ sót tăng lên.

Bài này tập trung vào **thiết kế luồng xử lý và bố trí thông tin để người đọc suy luận tại chỗ**. “Ít tầng lồng nhau” và “đặt thông tin gần nhau” là hai hướng cải thiện hữu ích, nhưng không phải các mục tiêu hình thức cần đạt bằng mọi giá. Điều quan trọng là **ý định nghiệp vụ được nhìn thấy rõ và hành vi vẫn đúng**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao độ sâu lồng nhau và khoảng cách giữa thông tin liên quan làm tăng tải nhận thức.
2. Nhận ra các kiểu lồng nhau khó theo dõi trong `if`, vòng lặp, `try/catch` và xử lý trạng thái.
3. Dùng **guard clause**, `continue`, biểu thức điều kiện và phương thức có tên để làm phẳng luồng xử lý khi phù hợp.
4. Bố trí khai báo biến, quy tắc, hằng số và kiểm tra hợp đồng đủ gần nơi chúng được dùng.
5. Phân biệt việc đặt thông tin **gần về ý nghĩa** với việc nhồi mọi thứ vào cùng một hàm hoặc file.
6. Bảo toàn hành vi khi refactor, nhất là thứ tự kiểm tra, ngoại lệ, tác dụng phụ và việc giải phóng tài nguyên.
7. Đánh giá thay đổi về khả năng đọc dựa trên việc người khác có thể giải thích, kiểm thử và sửa mã hay không.

## 2. Hai nguồn gây khó đọc

### 2.1. Mức lồng nhau là gì?

*Mức lồng nhau* (nesting depth) thể hiện một đoạn mã nằm bên trong bao nhiêu khối điều khiển khác. Những cấu trúc phổ biến làm tăng độ lồng nhau gồm `if/else`, `for`, `while`, `switch` và `try/catch`.

~~~java
if (customer != null) {                 // tầng 1
    if (customer.active()) {            // tầng 2
        if (subtotalCents >= 100_000) { // tầng 3
            applyDiscount();            // hành động chính
        }
    }
}
~~~

Người đọc đến `applyDiscount()` phải nhớ đồng thời ba điều kiện. Nếu giữa các điều kiện có thêm xử lý khác hoặc nhiều nhánh `else`, việc truy vết hành vi trở nên khó hơn.

Độ sâu không phải vấn đề duy nhất. Một `if` dài với nhiều điều kiện phủ định, biểu thức có tác dụng phụ hoặc các nhánh tương tác với nhau cũng có thể khó hiểu dù chỉ lồng một tầng.

### 2.2. Khoảng cách giữa các thông tin liên quan là gì?

*Khoảng cách thông tin* là lượng công sức phải bỏ ra để kết nối những phần mã cùng mô tả một hành vi. Khoảng cách có thể là:

- **Khoảng cách theo dòng:** khai báo biến, điều kiện kiểm tra và nơi sử dụng nằm xa nhau trong một phương thức.
- **Khoảng cách theo cấu trúc:** quy tắc nằm ở nhiều phương thức, lớp hoặc module mà người đọc phải lần theo.
- **Khoảng cách về khái niệm:** tên và trừu tượng hóa không cho biết hai phần có cùng trách nhiệm, khiến người đọc phải tự suy đoán.
- **Khoảng cách giữa yêu cầu và triển khai:** một quy tắc quan trọng không có tên, không có test mô tả ý định hoặc nằm lẫn trong mã hạ tầng.

Ví dụ, để hiểu mức miễn phí vận chuyển, người bảo trì phải tìm một hằng số ở cuối file, một điều kiện trong controller và một ngoại lệ ở service khác. Từng phần có thể ngắn nhưng **toàn bộ hành vi không thể hiểu tại một vị trí hợp lý**.

**Nguyên tắc:** những thông tin **thường được đọc, sửa và xác minh cùng nhau** nên có một ranh giới tổ chức rõ ràng; thông tin dùng rộng rãi nên có một nơi định nghĩa đáng tin cậy thay vì bị sao chép nhiều chỗ.

## 3. Vì sao lồng nhau sâu làm tăng tải nhận thức?

Đọc chương trình không chỉ là đọc từng dòng theo thứ tự. Người đọc phải mô phỏng điều kiện, giữ trạng thái trong trí nhớ và trả lời: *“Dòng này chạy trong trường hợp nào?”*

Một đoạn lồng nhau sâu làm người đọc phải:

1. **Giữ các điều kiện đang có hiệu lực.** Đang ở nhánh khách hàng hợp lệ, đơn chưa thanh toán, số tiền đủ ngưỡng hay không?
2. **Theo dõi nhánh thay thế.** Khi điều kiện sai, chạy `else` nào? Một `return` bên trong có thoát hàm hay chỉ thoát vòng lặp?
3. **Theo dõi trạng thái bị thay đổi.** Biến nào đã được cập nhật trước khi đến nhánh này?
4. **Nhớ mục đích của khối đang xét.** Hành động chính có thể bị đẩy xuống xa đầu phương thức.

Nếu hai người phải đọc lại nhiều lần mới giải thích được điều kiện để một dòng chạy, đây là dấu hiệu cần đánh giá khả năng đọc.

### 3.1. Đừng dùng một ngưỡng số học cứng cho mọi trường hợp

Quy ước “không lồng quá hai tầng” có thể là tín hiệu nhắc review hữu ích, nhưng **không phải định luật về chất lượng**. Một vòng lặp đi cùng một `if` rõ ràng có thể dễ hiểu hơn một chuỗi năm phương thức được trích xuất chỉ để giảm thụt lề.

Hãy xét đồng thời:

| Câu hỏi khi đọc mã | Dấu hiệu thuận lợi | Dấu hiệu cần xem lại |
| --- | --- | --- |
| Hành động chính có dễ tìm? | Nhìn một lượt thấy điều kiện và kết quả. | Hành động bị chôn ở đáy nhiều nhánh. |
| Điều kiện có dễ diễn giải? | Tên biểu đạt ý định, trường hợp loại trừ rõ. | Nhiều phủ định, điều kiện lặp lại, nhánh khó phân biệt. |
| Trạng thái có dễ theo dõi? | Ít biến thay đổi, phạm vi sống ngắn. | Một biến bị cập nhật ở nhiều nhánh xa nhau. |
| Luồng thoát có rõ? | `return`, `continue`, ngoại lệ đúng chỗ và có chủ đích. | Khó biết khi nào hàm/vòng lặp kết thúc. |
| Cần mở bao nhiêu chỗ khác? | Tên phương thức/hợp đồng đủ nói lên ý nghĩa. | Phải nhảy nhiều file chỉ để hiểu một điều kiện. |

Các phép đo về độ phức tạp của luồng điều khiển có thể hỗ trợ tìm điểm đáng đọc kỹ hơn, nhưng không thay thế được review hành vi và ngữ cảnh nghiệp vụ.

## 4. Kỹ thuật 1: guard clause đưa trường hợp loại trừ ra sớm

*Guard clause* là điều kiện kiểm tra ở đầu một phạm vi xử lý và **thoát sớm** khi điều kiện để đi tiếp không thỏa. Nhờ đó, “đường đi chính” không phải nằm trong nhiều lớp `if`.

Giả sử yêu cầu giảm giá là: khách hàng phải tồn tại, đang hoạt động, có hạng thành viên tối thiểu là 2 và giá trị giỏ hàng từ 100.000 đơn vị tiền nhỏ nhất trở lên. Tổng tiền âm được xem là đầu vào không hợp lệ.

Trong cả hai phiên bản dưới đây, giả định dữ liệu khách hàng được biểu diễn bằng:

~~~java
record Customer(boolean active, int loyaltyLevel) {}
~~~

### 4.1. Trước: điều kiện hợp lệ lồng nhau

~~~java
static boolean eligibleForDiscount(Customer customer, int subtotalCents) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("Subtotal must be non-negative");
    }

    if (customer != null) {
        if (customer.active()) {
            if (customer.loyaltyLevel() >= 2) {
                if (subtotalCents >= 100_000) {
                    return true;
                }
            }
        }
    }
    return false;
}
~~~

Mã này không nhất thiết sai. Nhưng muốn hiểu vì sao trả về `true`, người đọc phải ghép bốn điều kiện ở các độ sâu khác nhau.

### 4.2. Sau: loại các trường hợp không đạt trước

~~~java
static boolean eligibleForDiscount(Customer customer, int subtotalCents) {
    if (subtotalCents < 0) {
        throw new IllegalArgumentException("Subtotal must be non-negative");
    }
    if (customer == null || !customer.active()) {
        return false;
    }
    if (customer.loyaltyLevel() < 2) {
        return false;
    }
    return subtotalCents >= 100_000;
}
~~~

Phiên bản thứ hai cho thấy một chuỗi dễ đọc:

~~~text
Dữ liệu sai?       → báo lỗi
Khách không hợp lệ? → không đủ điều kiện
Hạng quá thấp?     → không đủ điều kiện
Còn lại            → kiểm tra ngưỡng đơn hàng
~~~

Ở đây, guard clause giúp làm phẳng mã và **không thay đổi ý nghĩa**, vì các kiểm tra đều thuần túy, không có tác dụng phụ, và các trường hợp bị loại đều trả về cùng kết quả `false`.

**Lưu ý về thứ tự:** đặt kiểm tra `customer == null` trước khi truy cập `customer.active()` là cần thiết. Toán tử `||` trong Java đánh giá ngắn mạch nên biểu thức thứ hai không được chạy khi `customer == null`. Tương tự, kiểm tra số tiền âm được giữ ở đầu để vẫn ném ngoại lệ kể cả khi khách hàng không tồn tại.

### 4.3. Khi nào guard clause phát huy tác dụng?

Guard clause thường phù hợp khi:

- Có một đường đi thành công chính và nhiều điều kiện loại trừ đơn giản.
- Nhiều nhánh thất bại kết thúc bằng `return`, `throw` hoặc kết quả rõ ràng.
- Điều kiện độc lập và có thể biểu đạt ngắn gọn.
- Việc thoát sớm không làm mất bước bắt buộc như giải phóng tài nguyên, ghi nhận giao dịch hoặc hoàn tất xử lý.

Không nên biến một phương thức thành hàng chục `return` khó tìm, hoặc tự động đưa nhánh lên đầu khi **thứ tự kiểm tra chính là một phần yêu cầu nghiệp vụ**.

## 5. Kỹ thuật 2: dùng continue để giảm lồng nhau trong vòng lặp

Khi vòng lặp xử lý một tập phần tử nhưng phần lớn phần tử không liên quan, việc kiểm tra và bỏ qua sớm giúp hành động chính nổi bật.

Giả sử `Invoice` là một hóa đơn có trạng thái đã thanh toán, trạng thái hoàn tiền và số tiền tính bằng đơn vị nhỏ nhất. Đầu vào cho phép phần tử `null` và quy ước bỏ qua phần tử này; các hóa đơn hợp lệ có số tiền không âm.

### 5.1. Trước: hành động nằm ở đáy nhánh

~~~java
static long settledTotalCents(List<Invoice> invoices) {
    long total = 0;
    for (Invoice invoice : invoices) {
        if (invoice != null) {
            if (invoice.paid()) {
                if (!invoice.refunded()) {
                    total = Math.addExact(total, invoice.amountCents());
                }
            }
        }
    }
    return total;
}
~~~

### 5.2. Sau: bỏ qua phần tử không phù hợp

~~~java
static long settledTotalCents(List<Invoice> invoices) {
    long total = 0;
    for (Invoice invoice : invoices) {
        if (invoice == null || !invoice.paid() || invoice.refunded()) {
            continue;
        }
        total = Math.addExact(total, invoice.amountCents());
    }
    return total;
}
~~~

Trong hai đoạn mã, giả định có các khai báo và import cần thiết:

~~~java
import java.util.List;

record Invoice(boolean paid, boolean refunded, long amountCents) {}
~~~

Đây là **hai phiên bản thay thế của cùng phương thức**; phần khai báo được tách riêng chỉ để tập trung vào cách tổ chức luồng xử lý. Việc dùng `Math.addExact` giữ cùng một quy tắc: nếu tổng vượt miền của `long`, Java ném `ArithmeticException` thay vì tràn số âm thầm.

Đoạn mã sau dễ nhận ra bước quan trọng: “với mỗi hóa đơn đủ điều kiện, cộng số tiền”. `continue` bỏ qua **lần lặp hiện tại** rồi chuyển sang phần tử tiếp theo; nó không thoát toàn bộ hàm như `return`.

**Đánh đổi:** khi một vòng lặp có nhiều bước phải thực hiện cho mọi phần tử (ví dụ ghi thống kê hoặc giải phóng tài nguyên), `continue` có thể vô tình bỏ qua những bước ấy. Vì vậy, phải hiểu rõ những hành động nào bắt buộc thực hiện kể cả khi hóa đơn không đủ điều kiện.

## 6. Kỹ thuật 3: đặt tên cho quy tắc, thay vì bắt người đọc giải mã biểu thức

Đôi khi độ lồng nhau chỉ là một triệu chứng. Vấn đề thực tế là các điều kiện quá dài và không rõ mục đích.

~~~java
if (user != null
        && user.enabled()
        && user.roles().contains("APPROVER")
        && document.status() == Status.PENDING
        && !document.locked()) {
    approve(document);
}
~~~

Đoạn điều kiện cho biết *cách tính*, nhưng người đọc còn phải suy ra mục đích tổng thể. Nếu chính sách phê duyệt được dùng ở nhiều vị trí, một tên có ý nghĩa sẽ hữu ích:

~~~java
if (canApprove(user, document)) {
    approve(document);
}
~~~

Tên `canApprove` giúp người đọc nhận ra ý định ở nơi gọi; phương thức triển khai nó nên nằm ở thành phần có trách nhiệm về chính sách phê duyệt, đủ gần để tìm thấy khi cần. Hợp đồng của phương thức phải nói rõ có thể nhận `null` hay không và hành vi với tài liệu bị khóa.

Tuy nhiên, **không phải mọi điều kiện đều cần trích xuất**. Với biểu thức ngắn, không tái sử dụng và đã rõ nghĩa, tạo thêm phương thức có thể buộc người đọc di chuyển xa hơn. Một phép trích xuất tốt cần đạt ít nhất một lợi ích cụ thể: đặt tên ý định, gom quy tắc nhất quán, giảm chi phí kiểm thử hoặc cho phép thay đổi độc lập.

### 6.1. Đổi điều kiện phủ định thành cách diễn đạt dễ hiểu

So sánh:

~~~java
if (!(!order.paid() || order.cancelled())) {
    prepareShipment(order);
}
~~~

Với:

~~~java
if (order.paid() && !order.cancelled()) {
    prepareShipment(order);
}
~~~

Hai điều kiện tương đương theo logic Boolean, nhưng phiên bản thứ hai bớt một lớp phủ định cần giải mã. Nếu điều kiện này là quy tắc quan trọng được dùng ở nhiều nơi, phương thức `order.isReadyForShipment()` có thể còn diễn đạt ý định tốt hơn, với điều kiện tên khớp chính xác với hành vi đã định nghĩa.

Trong Java, không nên thực hiện biến đổi logic một cách máy móc khi các vế có **tác dụng phụ**, có thể ném ngoại lệ hoặc thay đổi thứ tự đánh giá. Toán tử `&&` và `||` đánh giá từ trái sang phải và có tính ngắn mạch; đổi thứ tự vế có thể làm hành vi khác đi.

### 6.2. Đừng đẩy độ phức tạp ra nơi khác rồi gọi đó là “đơn giản”

Một chuỗi như `validate() → check() → compute() → handle() → execute()` với tên mơ hồ có thể khiến người đọc phải mở năm phương thức mới hiểu một quy tắc nhỏ. Giảm độ sâu thụt lề ở hàm đầu không có giá trị nếu **khoảng cách để hiểu hành vi** lại tăng mạnh.

Tên phương thức nên nêu mục đích hoặc kết quả quan sát được, ví dụ `isWithinCreditLimit`, `calculateShippingFee`, `rejectExpiredCoupon`, hơn là `doStep2` hoặc `processData`.

## 7. Giảm khoảng cách giữa thông tin liên quan trong cùng một phương thức

### 7.1. Khai báo biến gần nơi dùng, giới hạn phạm vi sống

Xem ví dụ tính phần phụ phí:

~~~java
int additionalFeeCents = 0;
// ... nhiều đoạn xử lý không liên quan ...
if (rushDelivery) {
    additionalFeeCents = 20_000;
}
// ... nhiều đoạn xử lý khác ...
return baseFeeCents + additionalFeeCents;
~~~

Người đọc phải nhớ một biến được khai báo từ lâu và xác định xem nó có bị cập nhật ở nơi nào khác hay không.

Nếu quy tắc đủ đơn giản, có thể đưa phép tính gần nơi kết quả được sử dụng:

~~~java
int additionalFeeCents = rushDelivery ? 20_000 : 0;
return Math.addExact(baseFeeCents, additionalFeeCents);
~~~

Ví dụ này minh họa cách rút ngắn phạm vi biến và tập trung phép tính; `Math.addExact` còn xác định rõ hành vi nếu tổng vượt giới hạn của `int`. Khi refactor mã thật, phải kiểm tra lại yêu cầu và hành vi tràn số hiện tại trước khi thay phép `+` bằng `Math.addExact`, vì việc thêm ngoại lệ có thể là thay đổi hợp đồng.

Giảm khoảng cách thường đồng nghĩa với:

- Khai báo biến sau khi đã có đủ dữ liệu để gán giá trị một lần.
- Ưu tiên biến cục bộ ít bị gán lại khi không cần cập nhật.
- Đặt kiểm tra tiền điều kiện gần điểm bắt đầu sử dụng dữ liệu cần bảo vệ.
- Không để một biến trạng thái “đi qua” nhiều nhánh không liên quan.

### 7.2. Đặt quy tắc và hằng số tại ranh giới sở hữu phù hợp

Ví dụ:

~~~java
final class ShippingPolicy {
    private static final int FREE_SHIPPING_FROM_CENTS = 500_000;
    private static final int STANDARD_FEE_CENTS = 30_000;

    static int feeFor(int subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must be non-negative");
        }
        return subtotalCents >= FREE_SHIPPING_FROM_CENTS
                ? 0
                : STANDARD_FEE_CENTS;
    }
}
~~~

Hai hằng số được định nghĩa gần quy tắc sử dụng chúng và có tên chứa đơn vị. Người đọc có thể hiểu mức phí mà không cần lần theo “magic number” rải rác. Cách này phù hợp khi chính sách chỉ thuộc về một thành phần.

Nếu nhiều service phải chia sẻ giá trị, việc sao chép hằng số tới mỗi service không còn là “đặt gần” đúng nghĩa: nó tạo nhiều nguồn sự thật. Khi ấy, cần một hợp đồng hay cơ chế quản lý chính sách phù hợp. **Gần về ý nghĩa và có một nơi chịu trách nhiệm** quan trọng hơn việc giữ mọi khai báo nằm sát nhau theo số dòng.

### 7.3. Đặt thông tin cần sửa cùng nhau tại một ranh giới

Ví dụ chính sách có hai tham số luôn thay đổi cùng một chiến dịch:

~~~java
record ShippingSettings(int freeFromCents, int flatFeeCents) {
    ShippingSettings {
        if (freeFromCents < 0 || flatFeeCents < 0) {
            throw new IllegalArgumentException("Fees must be non-negative");
        }
    }
}
~~~

Gom chúng vào một kiểu dữ liệu có tên làm rõ sự gắn kết của hai giá trị. Nó giúp người bảo trì tìm được ranh giới thay đổi và chỗ xác thực. Nhưng nếu các tham số độc lập hoàn toàn hoặc lớp chứa hàng chục trường không liên quan, gom tất cả vào một kiểu chung sẽ giảm tính gắn kết.

## 8. Gần nhau về ý nghĩa, không phải nhồi mọi thứ vào một khối

Một phương thức dài 200 dòng có thể chứa tất cả thông tin trong cùng một file, nhưng người đọc vẫn phải tìm quy tắc ở nhiều vị trí. Ở chiều ngược lại, tách mỗi biểu thức thành một helper nhỏ có thể làm người đọc phải nhảy liên tục giữa các nơi.

Mục tiêu là **local reasoning**: có thể hiểu một bước xử lý bằng ngữ cảnh gần nhất và một số ít hợp đồng rõ ràng.

Một luồng xử lý đơn hàng thường gồm những trách nhiệm khác nhau:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đặt hàng"] --> B["Kiểm tra dữ liệu đầu vào"]
    B --> C["Áp dụng quy tắc giá và giảm giá"]
    C --> D["Lưu giao dịch"]
    D --> E["Phát sự kiện xác nhận"]
~~~

Không nhất thiết đưa cả năm bước vào cùng một phương thức hay tách thành năm module độc lập. Có thể giữ một phương thức **điều phối** ngắn mô tả thứ tự, còn những quy tắc phức tạp nhưng có trách nhiệm rõ ràng được đặt trong thành phần chuyên trách.

Ví dụ ở mức ý tưởng:

~~~java
OrderResult placeOrder(PlaceOrderCommand command) {
    ValidatedOrder order = validate(command);
    PricedOrder priced = pricing.calculate(order);
    OrderResult result = orderRepository.save(priced);
    eventPublisher.publishOrderPlaced(result);
    return result;
}
~~~

Đoạn trên chỉ minh họa khả năng đọc của luồng điều phối. Các kiểu dữ liệu và thành phần phụ thuộc là giả định; nó không trình bày giao dịch, cơ chế đảm bảo phát sự kiện hay xử lý lỗi khi ghi dữ liệu thành công nhưng gửi sự kiện thất bại.

Người đọc nhìn thấy trình tự chính ngay tại một vị trí; để sửa quy tắc giá, họ đi đến thành phần `pricing`. Nếu tất cả chi tiết về giá bị phân tán tiếp thành nhiều helper không có tên ý nghĩa, khả năng đọc vẫn kém.

### 8.1. Một số nguyên tắc tổ chức thông tin

| Thông tin cần gắn kết | Vị trí thường phù hợp | Lý do |
| --- | --- | --- |
| Giá trị trung gian của một phép tính | Biến cục bộ gần chỗ sử dụng | Giảm phạm vi phải theo dõi trạng thái. |
| Điều kiện bảo vệ thao tác | Ngay trước thao tác hoặc ở đầu quy trình hợp lệ | Dễ thấy tiền điều kiện. |
| Hằng số riêng của một quy tắc | Cùng thành phần sở hữu quy tắc | Giảm tìm kiếm và tránh “giá trị ma thuật”. |
| Các bước cùng mô tả một nghiệp vụ | Một phương thức điều phối rõ ràng | Dễ nhìn thứ tự và mục tiêu. |
| Logic nghiệp vụ độc lập và đủ phức tạp | Phương thức/class có tên theo nghiệp vụ | Dễ kiểm thử, sửa và review. |
| Hợp đồng giữa nhiều thành phần | Kiểu dữ liệu/API/tài liệu hợp đồng có nơi sở hữu rõ | Tránh mỗi bên hiểu một cách. |
| Lý do của quyết định bất thường | Comment ngắn, test theo yêu cầu hoặc tài liệu quyết định dễ tìm | Giảm phụ thuộc vào trí nhớ người viết. |

## 9. Những đánh đổi cần tránh khi làm phẳng mã

### 9.1. Early return có thể bỏ qua việc bắt buộc phải làm

Ví dụ xử lý chưa an toàn:

~~~java
Resource resource = openResource();
if (!isValid(request)) {
    return; // Resource chưa được đóng!
}
use(resource);
resource.close();
~~~

Một cách phù hợp hơn là bảo đảm tài nguyên luôn được đóng bằng `try-with-resources` nếu kiểu tài nguyên hỗ trợ `AutoCloseable`:

~~~java
try (Resource resource = openResource()) {
    if (!isValid(request)) {
        return;
    }
    use(resource);
} // Đóng resource khi rời khối, kể cả return hoặc ném ngoại lệ
~~~

Ở đây `Resource`, `openResource` và `use` là các thành phần minh họa. Trong Java, cú pháp này hợp lệ khi `Resource` triển khai `AutoCloseable`.

Không nên bỏ các bước bù trừ, lưu nhật ký bắt buộc hoặc dọn trạng thái chỉ để giảm tầng thụt lề. Với giao dịch database, còn cần xem xét commit/rollback và tính nguyên tử. Guard clause có thể tốt hơn nếu đặt **trước** khi tạo tác dụng phụ; nhưng thứ tự ấy phải được kiểm tra theo hành vi thực.

### 9.2. Đảo thứ tự điều kiện có thể đổi hành vi

~~~java
if (account != null && account.active()) {
    // ...
}
~~~

Không thể tự ý đổi thành:

~~~java
if (account.active() && account != null) {
    // Có thể ném NullPointerException khi account == null
}
~~~

Ngay cả khi hai điều kiện không có `null`, đổi vị trí các lời gọi có tác dụng phụ vẫn có thể tạo kết quả khác. Khi refactor `if` lồng nhau thành một biểu thức ghép, phải xét **ngắn mạch, thứ tự gọi, ngoại lệ và tác dụng phụ**.

### 9.3. Tách phương thức quá mức tăng số lần chuyển ngữ cảnh

Ví dụ:

~~~java
int calculateTotal(Cart cart) {
    return stepOne(cart);
}

int stepOne(Cart cart) {
    return stepTwo(cart);
}

int stepTwo(Cart cart) {
    return cart.subtotalCents();
}
~~~

Ba phương thức không thêm ý nghĩa nghiệp vụ; người đọc bị buộc đi qua nhiều điểm trung gian chỉ để biết một giá trị. Nếu không có lợi ích riêng về hợp đồng, cô lập phụ thuộc hoặc tái sử dụng, mã trực tiếp thường dễ đọc hơn.

### 9.4. Biểu thức “gọn” chưa chắc dễ đọc

~~~java
int fee = vip ? subtotal > limit ? 0 : 10_000
              : subtotal > limit ? 15_000 : 30_000;
~~~

Cách viết ngắn nhưng các nhóm điều kiện khó đối chiếu. Với nhiều nhánh nghiệp vụ, `if/else` rõ ràng, `switch` phù hợp hoặc bảng quyết định đôi khi đọc tốt hơn.

Trong Java, toán tử ba ngôi (`? :`) thích hợp cho **lựa chọn ngắn và hiển nhiên**; lồng nhiều toán tử chỉ để giảm số dòng thường không đem lại lợi ích.

### 9.5. “Một lối thoát duy nhất” cũng không phải luật cứng

Một số nhóm thích một `return` cuối hàm để tiện theo dõi. Điều này có thể hợp lý trong quy trình cần một khối hoàn tất chung. Tuy nhiên, gom mọi kết quả vào biến `result` rồi đặt nhiều nhánh sâu chỉ để có một `return` có thể làm mã khó hiểu hơn.

Nên chọn cách giúp **điểm kết thúc và trách nhiệm dọn dẹp dễ kiểm chứng nhất**, thay vì tuyệt đối hóa số lượng `return`.

## 10. Bảo toàn hành vi khi refactor

Một thay đổi làm mã phẳng hơn chỉ thực sự cải thiện chất lượng khi **không vô tình thay đổi kết quả và tác dụng phụ**. Trước khi sửa, hãy lập bảng các trường hợp quan trọng.

Với ví dụ giảm giá ở mục 4:

| Đầu vào | Hành vi phải giữ |
| --- | --- |
| `subtotalCents < 0`, bất kể khách hàng | Ném `IllegalArgumentException`. |
| `customer == null` và tiền hợp lệ | Trả `false`. |
| Khách hàng không hoạt động | Trả `false`. |
| Khách hoạt động nhưng hạng dưới 2 | Trả `false`. |
| Khách hạng 2, giỏ 99.999 | Trả `false`. |
| Khách hạng 2, giỏ 100.000 | Trả `true`. |
| Khách hạng cao hơn, giỏ vượt ngưỡng | Trả `true`. |

Test JUnit 5 minh họa cho hai ranh giới và hợp đồng dữ liệu:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class DiscountPolicyTest {
    @Test
    void acceptsAtExactThreshold() {
        Customer customer = new Customer(true, 2);
        assertTrue(DiscountPolicy.eligibleForDiscount(customer, 100_000));
    }

    @Test
    void rejectsBelowThreshold() {
        Customer customer = new Customer(true, 2);
        assertFalse(DiscountPolicy.eligibleForDiscount(customer, 99_999));
    }

    @Test
    void rejectsMissingCustomer() {
        assertFalse(DiscountPolicy.eligibleForDiscount(null, 100_000));
    }

    @Test
    void validatesAmountBeforeCustomer() {
        assertThrows(IllegalArgumentException.class,
                () -> DiscountPolicy.eligibleForDiscount(null, -1));
    }
}
~~~

Đoạn test giả định phương thức ở mục 4 là phương thức `static` của lớp `DiscountPolicy` và bản ghi `Customer` nằm trong phạm vi package có thể truy cập. Khi đưa vào project thực, cần đặt các khai báo trong file Java phù hợp, cấu hình JUnit Jupiter và nhất quán tên class/phương thức.

**Cách kiểm tra ý nghĩa của refactor:**

1. Đọc hai phiên bản và liệt kê đường đi có kết quả hoặc ngoại lệ khác nhau.
2. Kiểm tra thứ tự đánh giá của các điều kiện và các lời gọi có tác dụng phụ.
3. Chạy test cho trường hợp thường gặp và **giá trị biên**.
4. Kiểm tra thay đổi phạm vi biến, tài nguyên, transaction và xử lý đồng thời nếu có.
5. Yêu cầu người review giải thích nhanh “đường đi thành công” và “đường đi loại trừ” ở phiên bản mới.

Những test này là bằng chứng bảo vệ một số trường hợp đã chọn; không thay thế việc xem xét hành vi của mọi đường đi khác.

## 11. Tình huống thực tế: duyệt yêu cầu hoàn tiền

Một phương thức xử lý hoàn tiền đang có sáu tầng `if`:

- Yêu cầu tồn tại.
- Người dùng đăng nhập.
- Người dùng có quyền.
- Đơn đã thanh toán.
- Đơn chưa từng hoàn.
- Số tiền hoàn không vượt số tiền đã trả.

Ở đáy các điều kiện, phương thức gọi cổng thanh toán, ghi cơ sở dữ liệu và gửi thông báo.

### 11.1. Vấn đề về khả năng đọc

Người bảo trì phải giữ sáu điều kiện trong đầu để tìm lúc nào giao dịch được thực hiện. Các lỗi `null`, không có quyền, sai trạng thái và vượt số tiền có thể đều bị xử lý ở cuối phương thức, khiến khó biết lỗi nào có ưu tiên.

Nếu điều kiện cấp quyền nằm trong controller, kiểm tra trạng thái nằm ở service và phép so sánh tiền ở một utility không tên rõ nghĩa, việc hiểu toàn bộ hành vi cần nhiều lượt chuyển file. Việc sửa quy tắc có nguy cơ bỏ sót một điểm kiểm tra.

### 11.2. Hướng cải thiện

Có thể chia trách nhiệm theo **ranh giới nghiệp vụ thực sự**:

1. Xác định hợp đồng đầu vào và quyền truy cập; trường hợp không hợp lệ kết thúc rõ ràng.
2. Gom những quy tắc xác định một yêu cầu hoàn tiền đủ điều kiện vào một nơi có tên thể hiện ý định.
3. Giữ luồng điều phối ngắn để nhìn thấy thứ tự: **kiểm tra → thực hiện hoàn tiền → lưu trạng thái → phát thông báo**.
4. Dùng cơ chế phù hợp để bảo vệ tính nhất quán khi cổng thanh toán hoặc database thất bại; không mặc định các bước bên ngoài có thể được rollback trong cùng một transaction.
5. Đặt test bên cạnh hợp đồng: thiếu quyền, đã hoàn, đúng ngưỡng, vượt số tiền, lỗi từ cổng thanh toán và lặp lại yêu cầu.

Không nên làm phẳng luồng bằng cách đổi thứ tự “kiểm tra quyền” và “thực hiện hoàn tiền”, cũng không nên gọi hoàn tiền trước rồi mới trả về lỗi. Một phương thức trông gọn nhưng đổi thứ tự tác dụng phụ sẽ gây hậu quả nghiêm trọng.

### 11.3. Câu hỏi review hữu ích

Người review có thể hỏi:

- “Tôi có thể nhìn ở một nơi và hiểu tất cả điều kiện trước khi tiền được hoàn không?”
- “Một trường hợp bị từ chối có thoát rõ ràng trước khi tạo tác dụng phụ không?”
- “Muốn thay đổi quy tắc về hạn mức hoàn tiền, tôi phải sửa những nơi nào?”
- “Các tên phương thức có đủ mô tả ý định, hay tôi phải mở nhiều file mới biết chúng làm gì?”
- “Test nào cho biết việc làm phẳng không làm thay đổi kết quả và thứ tự hành động?”

Đây là các câu hỏi thực dụng hơn việc chỉ đếm số dấu ngoặc mở hoặc số dòng.

## 12. Checklist áp dụng khi viết và review mã

- [ ] Người đọc có thể tìm hành động chính mà không phải giữ quá nhiều điều kiện lồng nhau.
- [ ] Trường hợp không hợp lệ được xử lý rõ, ưu tiên guard clause khi không làm đổi hành vi.
- [ ] Trong vòng lặp, `continue` hoặc `break` được dùng đúng phạm vi và không bỏ qua hành động bắt buộc.
- [ ] Điều kiện phức tạp có tên giải thích **ý định**, không chỉ che giấu biểu thức phía sau helper mơ hồ.
- [ ] Biến cục bộ được khai báo đủ gần nơi dùng; ít cập nhật không cần thiết.
- [ ] Quy tắc, hằng số và kiểm tra đầu vào nằm gần ranh giới chịu trách nhiệm của chúng.
- [ ] Các thông tin thường phải thay đổi cùng nhau được nhóm hợp lý, không bị sao chép ở nhiều nguồn.
- [ ] Tôi có thể đọc luồng chính mà không phải nhảy qua quá nhiều file với tên không rõ nghĩa.
- [ ] Tôi không chia hàm hoặc gom hàm chỉ để đạt chỉ số độ sâu, độ dài hoặc số lượng `return`.
- [ ] Việc refactor giữ nguyên thứ tự đánh giá, ngoại lệ, tác dụng phụ và dọn tài nguyên.
- [ ] Có ca test bảo vệ các trường hợp biên và quy tắc quan trọng trước/sau thay đổi.
- [ ] Người bảo trì khác có thể giải thích nhanh điều kiện, kết quả và vị trí cần sửa.

## 13. Tổng kết

**Giới hạn mức lồng nhau** giúp người đọc không phải giữ quá nhiều trạng thái và điều kiện trong đầu. **Giảm khoảng cách giữa thông tin liên quan** giúp họ hiểu một hành vi ở nơi phù hợp mà không cần lần theo những mảnh logic rải rác.

Trong **CODE_QUALITY_FUNDAMENTALS**, đây là hai thực hành cụ thể để làm mã **dễ hiểu hơn**, từ đó **dễ kiểm thử, sửa đổi và tin cậy hơn**. Hãy ưu tiên đường đi chính rõ ràng, tên diễn đạt ý định, biến và quy tắc ở đúng ranh giới; đồng thời bảo vệ hành vi bằng kiểm thử. Số tầng lồng nhau và số dòng chỉ là tín hiệu để xem xét, còn tiêu chí quyết định là **chi phí hiểu và thay đổi mã trong ngữ cảnh thực tế**.

