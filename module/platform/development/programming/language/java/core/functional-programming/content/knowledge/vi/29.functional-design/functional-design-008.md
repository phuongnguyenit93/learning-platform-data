# Giữ tên miền nghiệp vụ dễ hiểu khi dùng generic và hàm bậc cao trong Java

Generic và lập trình hàm giúp Java tái sử dụng thuật toán, kết hợp hành vi và giảm mã lặp. Nhưng một API có quá nhiều tham số kiểu như `<T,R,K,V>`, nhiều `Function`, `Predicate`, `Supplier` lồng nhau có thể làm mất đi điều quan trọng nhất của một chương trình nghiệp vụ: **người đọc hiểu ngay hệ thống đang làm việc gì**.

Ví dụ, “lọc đơn hàng đã thanh toán rồi tạo tóm tắt hóa đơn” là một câu chuyện nghiệp vụ dễ hiểu. Nếu toàn bộ ý nghĩa ấy bị giấu sau một hàm tên `process(data, f1, f2, f3)`, code tuy tổng quát nhưng khó review, khó sửa chính sách và dễ truyền nhầm hàm.

Mục tiêu bài học là biết **đặt abstraction đúng chỗ**:

- Đặt tên **kiểu, biến, phương thức và quy tắc** theo ngôn ngữ nghiệp vụ.
- Dùng `Predicate<T>` cho điều kiện, `Function<T,R>` cho biến đổi, `Comparator<T>` cho thứ tự khi chúng truyền đạt ý định rõ ràng.
- Viết **hàm bậc cao** (*higher-order function*) khi cần truyền/nhận hành vi, nhưng không biến mọi phương thức thành một framework generic.
- Đặt các tiện ích generic ở lớp kỹ thuật phù hợp; bọc bên ngoài bằng **API nghiệp vụ có kiểu và tên rõ ràng**.
- Thiết kế `record`, value object, enum và functional interface có tên để tránh “stringly typed” hoặc primitive obsession.
- Giữ null, lỗi, side effect, thứ tự và quy tắc tổng hợp **có ý nghĩa nghiệp vụ**, ngay cả khi dùng Stream.
- Kiểm thử hành vi và ranh giới abstraction, thay vì chỉ kiểm thử một chuỗi lời gọi lambda.

Ví dụ đầy đủ sử dụng **Java 17 trở lên**, gồm lệnh `javac`, `java` và stdout có thể kiểm tra được. Các đoạn ngắn không độc lập được ghi rõ.

## 1. Ngôn ngữ miền nghiệp vụ phải xuất hiện trong code

“Miền nghiệp vụ” (*domain*) là phần vấn đề thực tế mà phần mềm giải quyết: khách hàng, đơn hàng, thanh toán, điều kiện đủ nhận ưu đãi, hạn mức, hóa đơn, v.v.

Hãy so sánh hai cách diễn đạt cùng một phép lọc. Cách thứ nhất:

```java
List<Order> x = list.stream()
        .filter(a -> a.status() == Status.PAID)
        .filter(a -> a.totalCents() >= 12000)
        .toList();
```

Đây là **mảnh mã minh họa** với `Order`, `Status`, `list` tồn tại trong chương trình. Người đọc phải nhìn vào từng điều kiện để suy ra `x` mang ý nghĩa gì.

Cách thứ hai:

```java
Predicate<Order> eligibleForInvoice =
        isPaidOrder().and(hasMinimumAmount(12000));

List<Order> invoiceCandidates = orders.stream()
        .filter(eligibleForInvoice)
        .toList();
```

Đây cũng là mảnh mã; `isPaidOrder()` và `hasMinimumAmount(long)` là những phương thức nghiệp vụ được định nghĩa ở phần sau. Lợi ích: code thuật lại **chính sách** thay vì làm người đọc giải mã các phép so sánh.

Cách viết thứ hai không nhất thiết cần thiết cho một biểu thức chỉ dùng một lần. Nhưng khi một điều kiện xuất hiện nhiều nơi, có tên nghiệp vụ giúp giảm sai khác về ngưỡng hoặc trạng thái khi cần thay đổi.

**Điểm cốt lõi:** ngôn ngữ miền nghiệp vụ phải là một phần của API, test và tên kiểu; generic là công cụ giúp triển khai, **không phải thay thế cho ý nghĩa nghiệp vụ**.

## 2. Generic là phương tiện bảo toàn kiểu, không phải mục tiêu tự thân

Generic của Java cho phép trình biên dịch ràng buộc kiểu mà không cần cast tùy tiện. Ví dụ:

```java
List<Order> orders = ...;
List<Customer> customers = ...;
```

Dấu `...` ở đây biểu thị **mã minh họa chưa hoàn chỉnh**, không phải Java runnable. Hai danh sách khác loại; trình biên dịch ngăn bạn lấy `Customer` từ `List<Order>` mà không chuyển đổi hợp lệ.

Một helper generic hữu ích khi **cùng một thuật toán thật sự áp dụng cho nhiều miền**:

```java
static <T> List<T> select(
        List<T> input,
        Predicate<? super T> rule) {
    return input.stream()
            .filter(rule)
            .toList();
}
```

Đây là **phương thức minh họa**, đặt trong class và cần `List`, `Predicate`. `T` là kiểu phần tử, `Predicate<? super T>` là điều kiện áp dụng được lên phần tử ấy. Helper này có ích nếu nhiều module cần một phép chọn tương tự.

Ngược lại:

```java
static <T, R, K, V> V doAnything(
        T data,
        Function<T, R> first,
        Function<R, K> second,
        Function<K, V> third) {
    return third.apply(second.apply(first.apply(data)));
}
```

Đây là phương thức **biên dịch được** nếu có import `Function`, nhưng chưa chắc là một abstraction tốt cho nghiệp vụ. Nó không cho biết “data” là gì, từng phép biến đổi có ý nghĩa gì, và xử lý lỗi ở đâu. Nếu chỉ có một đường xử lý, dùng các phương thức mang tên `calculateInvoiceTotal`, `checkEligibility`, `issueReceipt` thường rõ hơn.

**Quy tắc:** tạo generic khi có **một quy luật tái sử dụng ổn định**. Đừng tổng quát hóa sớm chỉ để giảm vài dòng code.

## 3. Các functional interface chuẩn và cách đặt tên

Java cung cấp những interface trong `java.util.function`:

| Interface | Dạng hàm | Cách hiểu nghiệp vụ |
| --- | --- | --- |
| `Predicate<T>` | `T -> boolean` | Một quy tắc điều kiện: có đủ điều kiện hay không |
| `Function<T,R>` | `T -> R` | Biến đối tượng đầu vào thành dạng kết quả |
| `Consumer<T>` | `T -> void` | Thực hiện action trên một đối tượng |
| `Supplier<T>` | `() -> T` | Cấp một giá trị khi được yêu cầu |
| `UnaryOperator<T>` | `T -> T` | Biến đổi nhưng giữ cùng kiểu |
| `BinaryOperator<T>` | `(T,T) -> T` | Gộp hai giá trị cùng kiểu |
| `Comparator<T>` | `(T,T) -> int` | Xác định thứ tự theo tiêu chí |

Đôi khi một lambda rất ngắn là đủ:

```java
orders.stream().filter(order -> order.isPaid()).toList();
```

Đây là mảnh minh họa giả định `Order` có `isPaid()`, không phải API sẵn có của Java.

Nhưng với điều kiện có tính chính sách, dùng tên có ý nghĩa:

```java
Predicate<Order> eligibleForRefund = order ->
        order.isPaid() && order.refundableAmountCents() > 0;
```

Đây là mảnh minh họa với các phương thức của một domain model cụ thể. Tên `eligibleForRefund` nói rõ **ý định**, thay vì một tên chung chung như `p`, `f`, `check`.

Một số quy ước thực dụng:
- Predicate: `isActiveCustomer`, `requiresManualReview`, `canReceiveDiscount`.
- Function: `toInvoiceLine`, `extractCustomerId`, `calculateNetAmount`.
- Comparator: `byPaymentDate`, `byPriorityThenCreationTime`.
- Supplier: `createEmptyReport`, `loadFallbackConfiguration`.
- Consumer: `publishInvoiceIssuedEvent`, nhưng chỉ sử dụng side effect có chủ đích.

**Đừng đặt tên hàm bằng kiểu kỹ thuật khi nội dung là luật nghiệp vụ.** `filter` mô tả thao tác, còn `isEligibleForRefund` mô tả chính sách thực sự.

## 4. Chương trình Java 17: tên nghiệp vụ làm pipeline tự giải thích

Lưu thành **`DomainVocabularyDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class DomainVocabularyDemo {
    enum OrderState { DRAFT, PAID, CANCELLED }

    record Order(String id, OrderState state, long totalCents) {}
    record InvoiceSummary(String orderId, long amountCents) {}

    static Predicate<Order> isPaidOrder() {
        return order -> order.state() == OrderState.PAID;
    }

    static Predicate<Order> hasMinimumAmount(long minimumCents) {
        if (minimumCents < 0) {
            throw new IllegalArgumentException("minimumCents");
        }
        return order -> order.totalCents() >= minimumCents;
    }

    static Function<Order, InvoiceSummary> toInvoiceSummary() {
        return order -> new InvoiceSummary(
                order.id(), order.totalCents());
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-1", OrderState.PAID, 15_000),
                new Order("O-2", OrderState.DRAFT, 24_000),
                new Order("O-3", OrderState.PAID, 8_000),
                new Order("O-4", OrderState.PAID, 21_000)
        );

        Predicate<Order> eligibleForInvoice =
                isPaidOrder().and(hasMinimumAmount(12_000));

        List<InvoiceSummary> summaries = orders.stream()
                .filter(eligibleForInvoice)
                .map(toInvoiceSummary())
                .toList();

        long totalCents = orders.stream()
                .filter(eligibleForInvoice)
                .mapToLong(Order::totalCents)
                .sum();

        System.out.println("summaries=" + summaries);
        System.out.println("totalCents=" + totalCents);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DomainVocabularyDemo.java
java DomainVocabularyDemo
```

**Stdout chính xác:**

```text
summaries=[InvoiceSummary[orderId=O-1, amountCents=15000], InvoiceSummary[orderId=O-4, amountCents=21000]]
totalCents=36000
```

Bốn đơn hàng minh họa:
- `O-1` là PAID, 15.000 cent, đủ ngưỡng 12.000.
- `O-2` là DRAFT, không được chọn dù giá trị lớn.
- `O-3` là PAID nhưng chỉ 8.000, chưa đạt ngưỡng.
- `O-4` là PAID, 21.000, đủ điều kiện.

Kết quả có hai `InvoiceSummary` và tổng 36.000 cent. Code thể hiện chính sách qua `eligibleForInvoice` thay vì lặp điều kiện ở nhiều pipeline. Ngưỡng được kiểm tra trong factory `hasMinimumAmount`; việc tách logic ra thành hàm có tên cũng giúp viết unit test cho ngưỡng.

**Lưu ý:** `record` không tự bảo đảm object hợp lệ về mặt nghiệp vụ. Nếu cần ngăn `Order` có ID rỗng, trạng thái null hoặc tổng tiền âm, hãy thêm compact constructor hoặc validation thích hợp. Ví dụ chỉ tập trung vào cách đặt tên và ghép hành vi.

## 5. Hàm bậc cao là gì, và nên dùng ở đâu?

Một **hàm bậc cao** (*higher-order function*) là hàm **nhận một hàm làm tham số**, **trả một hàm**, hoặc cả hai. Java biểu diễn các hàm đó qua functional interface và lambda/method reference.

Ví dụ nhận hành vi:

```java
static <T> List<T> filterBy(
        List<T> values,
        Predicate<? super T> accepted) {
    return values.stream().filter(accepted).toList();
}
```

Ví dụ trả về hành vi:

```java
static Predicate<Order> paidOrdersAbove(long cents) {
    return order ->
            order.state() == OrderState.PAID
            && order.totalCents() >= cents;
}
```

Hai khối trên là **mảnh phương thức minh họa**, cần có `Order` và `OrderState` như chương trình trước. Cả hai là higher-order functions, nhưng đem lại giá trị ở hai mức khác nhau:

- `filterBy` là abstraction kỹ thuật về một **thuật toán lọc chung**.
- `paidOrdersAbove` là abstraction nghiệp vụ về **chính sách chọn đơn hàng**.

Không cần ép mọi quy tắc vào `Function<Function<...>>` hay chuỗi constructor vô danh. Nếu người gọi muốn hiểu “đơn hàng thanh toán đạt tối thiểu bao nhiêu”, hàm `paidOrdersAbove` nói điều đó rõ ràng.

### Vị trí abstraction và mức độ công khai

Một helper như `filterBy` có thể nằm trong lớp utility nội bộ; API công khai của dịch vụ vẫn nên là:

```java
List<Order> findOrdersEligibleForInvoice(long minimumCents)
```

Đây là **chữ ký minh họa**, không phải lời gọi runnable. Người gọi không phải biết hệ thống dùng Stream, `Predicate` hay vòng lặp. Như vậy bạn giữ được quyền đổi implementation mà không buộc thay code ở mọi lớp.

**Một abstraction tốt giấu cơ chế, không giấu quy tắc nghiệp vụ.**

## 6. Khi nào tạo functional interface riêng thay vì Predicate<T>?

`Predicate<Customer>` thường đủ để biểu diễn một phép kiểm tra. Tuy nhiên, có những lúc một luật nghiệp vụ cần:

- Tên chuyên biệt thể hiện hợp đồng hơn là “boolean test”.
- Một số thao tác phối hợp có cùng ngôn ngữ nghiệp vụ.
- Các quy tắc validation hoặc chú giải quan trọng cần đặt gần interface.
- Chữ ký API rõ ràng, tránh truyền nhầm một `Predicate<Customer>` mang nghĩa hoàn toàn khác.

Một functional interface chuyên biệt có thể như sau:

```java
@FunctionalInterface
interface CustomerEligibilityRule {
    boolean allows(Customer customer);
}
```

Đây là mảnh khai báo, cần class hoặc record `Customer`. Interface này vẫn dùng được với lambda vì chỉ có **một abstract method**.

Đừng tự tạo interface mới cho mỗi lambda nhỏ. Nếu chỉ có một phép lọc nội bộ và API không cần một hợp đồng domain riêng, `Predicate<T>` thường đơn giản hơn. Cần đánh giá bằng **độ rõ của mã và khả năng đổi luật**, không theo số lượng interface.

### Tích hợp default method để ghép luật

Có thể thêm `default CustomerEligibilityRule and(CustomerEligibilityRule other)`, trả về một luật kết hợp. Đây là nơi higher-order design trở nên hữu ích: các luật được tạo/ghép như giá trị nhưng vẫn giữ một tên kiểu nghiệp vụ.

## 7. Chương trình Java 17: functional interface với tên nghiệp vụ

Lưu thành **`CustomerEligibilityDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class CustomerEligibilityDemo {
    record Customer(String id, boolean active, long spendCents) {}

    @FunctionalInterface
    interface CustomerEligibilityRule {
        boolean allows(Customer customer);

        default CustomerEligibilityRule and(
                CustomerEligibilityRule other) {
            Objects.requireNonNull(other);
            return customer ->
                    this.allows(customer) && other.allows(customer);
        }
    }

    static CustomerEligibilityRule isActiveCustomer() {
        return Customer::active;
    }

    static CustomerEligibilityRule hasSpentAtLeast(long minimumCents) {
        return customer -> customer.spendCents() >= minimumCents;
    }

    static List<String> loyaltyCandidateIds(
            List<Customer> customers,
            CustomerEligibilityRule eligibility) {
        return customers.stream()
                .filter(eligibility::allows)
                .map(Customer::id)
                .toList();
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
                new Customer("C1", true, 20_000),
                new Customer("C2", false, 50_000),
                new Customer("C3", true, 8_000),
                new Customer("C4", true, 30_000)
        );

        CustomerEligibilityRule loyaltyRule =
                isActiveCustomer().and(hasSpentAtLeast(15_000));

        System.out.println("eligible="
                + loyaltyCandidateIds(customers, loyaltyRule));
        System.out.println("activeOnly="
                + loyaltyCandidateIds(customers, isActiveCustomer()));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CustomerEligibilityDemo.java
java CustomerEligibilityDemo
```

**Stdout chính xác:**

```text
eligible=[C1, C4]
activeOnly=[C1, C3, C4]
```

Giải thích:
- `CustomerEligibilityRule` là một hợp đồng domain, không phải helper generic nhận mọi thứ.
- `isActiveCustomer()` và `hasSpentAtLeast(...)` trả các luật có tên rõ nghĩa.
- Default method `and` kết hợp chúng bằng logic short-circuit `&&`, với kiểm tra null cho luật thứ hai.
- Khách C2 tiêu nhiều nhưng không hoạt động, C3 hoạt động nhưng chưa đạt ngưỡng 15.000. C1, C4 thỏa cả hai.
- `loyaltyCandidateIds` trả **ID**, không trả nguyên entity, vì tên API nói rõ mục đích. Nếu yêu cầu cần cả Customer, đổi tên/kiểu trả về thành phương thức thích hợp.

**Cẩn trọng về điều kiện ghép:** `and` không nhất thiết giao hoán nếu các luật có side effect, có exception hoặc bị lệ thuộc trạng thái. Với các rule thuần như ví dụ, thứ tự không làm thay đổi tính đúng đắn, nhưng `&&` vẫn short-circuit. Đừng giấu việc ghi log bắt buộc hoặc gọi I/O trong một predicate rồi mong mọi luật đều được chạy.

## 8. Phân biệt rõ domain rule và thuật toán generic

Một API tổng quát có thể hữu ích nếu thực sự có nhiều hành vi cùng cấu trúc. Ví dụ:

```java
static <T, R> List<R> selectAndMap(
        List<T> source,
        Predicate<? super T> accepted,
        Function<? super T, ? extends R> mapper) {
    return source.stream()
            .filter(accepted)
            .map(mapper)
            .toList();
}
```

Đây là **mảnh phương thức minh họa**, với import `List`, `Predicate`, `Function`.

`T` có thể là `Invoice`, `Customer` hoặc một kiểu khác. `R` là kết quả sau biến đổi. Các wildcard ở tham số được chọn theo ý nghĩa:
- `Predicate<? super T>` nhận được phần tử kiểu `T`.
- `Function<? super T, ? extends R>` nhận `T` và có thể trả subtype của `R`.
- `List<R>` là kết quả có kiểu rõ ràng mà trình biên dịch kiểm tra.

Nhưng nếu public API chỉ là:

```java
selectAndMap(invoices, a, b)
```

thì caller vẫn khó biết đó là phép gì. Tốt hơn là dùng tên miền nghiệp vụ bên ngoài:

```java
List<Receipt> findReceiptsForPaidInvoices(List<Invoice> invoices)
```

Đây là một chữ ký minh họa. Bên trong nó có thể dùng `selectAndMap`, còn người gọi chỉ thấy **ý nghĩa nghiệp vụ**.

**Quy tắc thiết kế hai tầng:** helper generic nằm trong tầng chia sẻ cơ chế; phương thức domain đứng ở biên mà các lớp khác gọi đến.

## 9. Chương trình Java 17: helper generic ẩn sau API nghiệp vụ

Lưu thành **`GenericBoundaryDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

public class GenericBoundaryDemo {
    record Invoice(String number, boolean paid, long cents) {}
    record Receipt(String invoiceNumber, long cents) {}

    static <T, R> List<R> selectAndMap(
            List<T> rows,
            Predicate<? super T> eligible,
            Function<? super T, ? extends R> toResult) {
        return rows.stream()
                .filter(eligible)
                .map(toResult)
                .toList();
    }

    static List<Receipt> receiptsForPaidInvoices(
            List<Invoice> invoices) {
        return selectAndMap(
                invoices,
                Invoice::paid,
                invoice -> new Receipt(
                        invoice.number(),
                        invoice.cents())
        );
    }

    static List<String> numbersOfLargeUnpaidInvoices(
            List<Invoice> invoices,
            long minimumCents) {
        return selectAndMap(
                invoices,
                invoice -> !invoice.paid()
                        && invoice.cents() >= minimumCents,
                Invoice::number
        );
    }

    public static void main(String[] args) {
        List<Invoice> invoices = List.of(
                new Invoice("INV-1", true, 20_000),
                new Invoice("INV-2", false, 40_000),
                new Invoice("INV-3", true, 15_000)
        );

        List<Receipt> receipts = receiptsForPaidInvoices(invoices);
        List<String> largeUnpaid =
                numbersOfLargeUnpaidInvoices(invoices, 30_000);

        System.out.println("receipts=" + receipts);
        System.out.println("paidTotal=" + receipts.stream()
                .mapToLong(Receipt::cents).sum());
        System.out.println("largeUnpaid=" + largeUnpaid);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 GenericBoundaryDemo.java
java GenericBoundaryDemo
```

**Stdout chính xác:**

```text
receipts=[Receipt[invoiceNumber=INV-1, cents=20000], Receipt[invoiceNumber=INV-3, cents=15000]]
paidTotal=35000
largeUnpaid=[INV-2]
```

Hai phương thức domain cho biết rõ kết quả: `receiptsForPaidInvoices` tạo bản ghi receipt cho invoice đã thanh toán; `numbersOfLargeUnpaidInvoices` chỉ lấy mã các invoice chưa thanh toán và vượt ngưỡng. Helper `selectAndMap` được tái sử dụng ở hai trường hợp khác nhau mà không phải đưa generic ra ngoài API nghiệp vụ.

**Giới hạn của helper:** nó không xử lý lỗi validation, transaction hay authorization; chỉ là một phép filter rồi map. Đừng thêm hàng loạt callback không liên quan vào helper như `onError`, `onSuccess`, `beforeFilter`, `afterMap` nếu code thực tế chưa có nhu cầu lặp ổn định.

Nếu một pipeline có nhiều bước khác nhau và chỉ được gọi một lần, **viết thẳng Stream** đôi khi dễ hiểu hơn một helper generic.

## 10. Kiểu miền nghiệp vụ chống nhầm ID và tiền

Hai giá trị đều là `String` không có nghĩa chúng cùng vai trò. `CustomerId` và `OrderId` có thể đều chứa chữ/số, nhưng truyền nhầm ID vẫn là lỗi nghiêm trọng nếu API chỉ nhận `String`.

Một hướng thiết kế là tạo **value object** hoặc `record` riêng:

```java
record CustomerId(String value) {}
record OrderId(String value) {}
```

Khi đó `CustomerId` không tự thay cho `OrderId`. Generic vẫn hữu ích như `Map<CustomerId,Long>`, nhưng caller nhìn thấy kiểu domain rõ ràng.

Tương tự, với đơn vị tiền, `long amountCents` tốt hơn một `double amount` mơ hồ nếu hệ thống làm việc với đơn vị cent cố định; trong domain phức tạp hơn, một `Money` value object có currency và quy tắc tính toán riêng có thể cần thiết.

**Generic không thay domain validation:** `Map<String,Long>` không chứng minh khóa là Customer ID hợp lệ; `Map<CustomerId,Money>` có thể rõ hơn nếu việc bảo toàn kiểu rất quan trọng. Tuy nhiên, đừng tạo lớp wrapper cho mọi primitive chỉ vì có thể làm được: mỗi lớp mới mang thêm chi phí API, mapping, serialization và hiểu biết.

## 11. Chương trình Java 17: dùng record ID để bảo vệ ranh giới

Tạo tệp **`DomainTypeSafetyDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

public class DomainTypeSafetyDemo {
    record CustomerId(String value) {
        CustomerId {
            Objects.requireNonNull(value);
            if (value.isBlank()) {
                throw new IllegalArgumentException("blank customer ID");
            }
        }
    }

    record OrderId(String value) {
        OrderId {
            Objects.requireNonNull(value);
            if (value.isBlank()) {
                throw new IllegalArgumentException("blank order ID");
            }
        }
    }

    record Payment(
            OrderId orderId,
            CustomerId customerId,
            long cents) {}

    static Map<CustomerId, Long> totalPaidByCustomer(
            List<Payment> payments) {
        return payments.stream()
                .collect(Collectors.groupingBy(
                        Payment::customerId,
                        Collectors.summingLong(Payment::cents)));
    }

    public static void main(String[] args) {
        List<Payment> payments = List.of(
                new Payment(new OrderId("O1"),
                        new CustomerId("C1"), 1_000),
                new Payment(new OrderId("O2"),
                        new CustomerId("C2"), 2_000),
                new Payment(new OrderId("O3"),
                        new CustomerId("C1"), 3_000)
        );

        Map<CustomerId, Long> totals = totalPaidByCustomer(payments);
        System.out.println("C1=" + totals.get(new CustomerId("C1")));
        System.out.println("C2=" + totals.get(new CustomerId("C2")));
        System.out.println("orderIds=" + payments.stream()
                .map(Payment::orderId)
                .toList());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DomainTypeSafetyDemo.java
java DomainTypeSafetyDemo
```

**Stdout chính xác:**

```text
C1=4000
C2=2000
orderIds=[OrderId[value=O1], OrderId[value=O2], OrderId[value=O3]]
```

`Payment` có `OrderId` và `CustomerId` khác kiểu, nên trình biên dịch không cho truyền nhầm vị trí chúng mà không có chuyển đổi có chủ đích. `CustomerId` là record có `equals` và `hashCode` theo `value`, nên `new CustomerId("C1")` dùng được để tra map với khóa đã được tạo trong record khác.

`groupingBy(Payment::customerId, summingLong(...))` biểu thị chính sách “tổng thanh toán theo khách hàng” rõ hơn một helper kiểu `aggregate(x,y,z)`. Mã in theo từng ID cụ thể, không phụ thuộc thứ tự duyệt của `HashMap`.

**Lưu ý:** `Collectors.summingLong` có thể tràn `long` nếu tổng cực lớn; ví dụ dùng số nhỏ. Compact constructor kiểm tra ID rỗng, nhưng `Payment` trong ví dụ chưa kiểm tra số tiền âm hoặc null của các ID; production model phải bổ sung các invariant thật sự cần thiết.

## 12. Đặt tên theo quy tắc nghiệp vụ, không phải hình dạng lambda

Hãy ưu tiên tên thể hiện **tại sao** một phép xử lý tồn tại:

| Tên quá tổng quát | Tên gợi ý theo nghiệp vụ | Khi nào phù hợp |
| --- | --- | --- |
| `filterItems` | `findOrdersEligibleForInvoice` | Trả các đơn hàng có đủ điều kiện xuất hóa đơn |
| `processCustomer` | `calculateCustomerLoyaltyTier` | Tính hạng thành viên |
| `mapData` | `toInvoiceSummary` | Chuyển đơn hàng thành dữ liệu hóa đơn |
| `check` | `isPaymentConfirmed` | Xác nhận điều kiện thanh toán |
| `calc` | `calculateNetAmountCents` | Tính tiền sau điều chỉnh |
| `fn`, `p` | `eligibleForRefund` | Điều kiện hoàn tiền |
| `sortItems` | `sortShipmentsByDeadline` | Quy tắc ưu tiên giao hàng |
| `converter` | `toShippingAddress` | Biến đổi domain có đích rõ |

Tên không nên quá dài đến mức lặp lại toàn bộ implementation. Ví dụ `findOrdersWithStatusPaidAndAmountGreaterThanOrEqualToTwelveThousandCents` có thể quá chi tiết nếu chính sách có thể thay đổi. Tên `findInvoiceEligibleOrders` cùng một domain policy được định nghĩa và kiểm thử riêng thường bền hơn.

**Tách chính sách khỏi tham số kỹ thuật:** `minimumCents` là tham số có ý nghĩa nghiệp vụ; `Predicate<Order>` là cách triển khai. Public method có thể nhận ngưỡng thay vì bắt mọi caller tự tạo lambda.

### Kết hợp nhiều điều kiện

Dùng `Predicate.and`, `or`, `negate` nếu các điều kiện độc lập, thuần và có tên:

```java
Predicate<Order> eligible = isPaidOrder()
        .and(hasMinimumAmount(12_000));
```

Khi chính sách phát triển thành nhiều nhánh và ngoại lệ, một class `InvoiceEligibilityPolicy` với phương thức `isEligible(Order)` có thể rõ hơn một biểu thức lambda dài hàng chục dòng. Không bắt buộc logic nghiệp vụ phải tồn tại hoàn toàn dưới dạng lambda.

## 13. API dễ hiểu ở ranh giới module

Khi một module cần cung cấp chức năng cho module khác, nên biểu đạt hợp đồng theo **domain input/output** trước:

```java
List<Receipt> issueReceiptsForPaidInvoices(
        List<Invoice> invoices)
```

Đây là chữ ký minh họa; nếu việc “issue” thật sự phát hành hóa đơn và có side effect, cần thêm hợp đồng giao dịch, lỗi và idempotency thay vì coi là phép map thuần. Nếu chỉ tạo dữ liệu hiển thị, tên `buildReceiptPreviewsForPaidInvoices` rõ hơn.

So sánh:

```java
<R> R execute(
        Object data,
        Function<Object, R> function)
```

Đây cũng là chữ ký minh họa. Nó ít truyền đạt domain và dùng `Object` làm mất khả năng compiler giúp kiểm tra kiểu. Dù generic `R` làm kiểu đầu ra rõ hơn, người gọi vẫn khó biết input đúng là gì và tác vụ làm gì.

**Quy tắc API:** khi domain đã xác định, tham số và kiểu trả về nên thể hiện domain. Generic nên dùng khi một cấu trúc kỹ thuật **thật sự độc lập** với domain và việc tái sử dụng đủ lớn để biện minh.

## 14. Chuỗi Function.compose, andThen: dùng đúng lúc

`Function<T,R>` có thể được kết hợp:

- `andThen(after)`: thực hiện hàm hiện tại trước, rồi gọi `after`.
- `compose(before)`: gọi `before` trước, rồi áp dụng hàm hiện tại.

Ví dụ:

```java
Function<String, String> trim = String::strip;
Function<String, Integer> length = String::length;

Function<String, Integer> trimmedLength =
        trim.andThen(length);
// trimmedLength.apply(" Java ") -> 4
```

Đây là mảnh code cần import `java.util.function.Function;`. Khi workflow ngắn, các tên `trim`, `length`, `trimmedLength` có thể giúp đọc hơn một lambda lồng sâu.

Nhưng với một luồng nghiệp vụ có nhánh lỗi, truy cập DB, kiểm tra quyền và phát sự kiện, **không nên ép tất cả vào một Function chain** chỉ để “trông functional”. Một phương thức domain rõ ràng với những bước có tên, handling lỗi và side effect minh bạch thường tốt hơn.

Đặc biệt, `Function.andThen` không tự bắt exception, không rollback transaction và không đồng bộ dữ liệu. Một hàm trung gian ném exception thì chain cũng không có kết quả thành công để chuyển tiếp.

## 15. Optional và domain error: đừng làm mất ý nghĩa vắng mặt

Nếu một phép tra cứu không tìm thấy bản ghi, `Optional<Customer>` có thể phù hợp để biểu diễn việc vắng mặt **được dự kiến trong hợp đồng**:

```java
Optional<Customer> customer = repository.findById(customerId);
String name = customer.map(Customer::name)
        .orElse("Khách chưa xác định");
```

Đây là mảnh mã minh họa với `repository`, `customerId`, `Customer` tương ứng.

Tuy nhiên, nếu một giao dịch không đủ điều kiện vì nhiều lý do khác nhau, `Optional.empty()` có thể làm mất thông tin cần thiết. Domain model có thể cần kết quả phong phú như enum lý do từ chối hoặc record kết quả chứa mã lỗi.

**Không nên trả null thay cho Optional rỗng.** Nếu API được công bố trả `Optional<T>`, caller phải có thể dựa vào việc tham chiếu Optional không null.

**Không dùng `orElseThrow` tùy tiện:** khi không tìm thấy là lỗi bắt buộc, chọn exception mang ý nghĩa nghiệp vụ và thông điệp rõ; khi vắng mặt là trạng thái bình thường, xử lý bằng `map`, `ifPresent`, `orElse` theo chính sách.

## 16. Side effect và tính thuần trong hàm bậc cao

Một callback được đưa vào `Stream.map` hoặc `filter` nên ưu tiên:

- **Stateless:** không phụ thuộc bộ đếm mutable dùng chung giữa các lần gọi.
- **Non-interfering:** không sửa nguồn đang được duyệt.
- **Deterministic khi cần:** cùng dữ liệu và quy tắc tạo cùng kết quả.
- **Rõ ràng về ngoại lệ:** người gọi biết điều kiện nào thất bại và lỗi được xử lý ở đâu.

Ví dụ không nên dùng một biến ngoài để gom dữ liệu trong `parallelStream()`:

```java
List<String> result = new ArrayList<>();
orders.parallelStream()
        .filter(isPaidOrder())
        .forEach(order -> result.add(order.id()));
```

Đây là **anti-pattern minh họa**, cần import phù hợp. `ArrayList` không an toàn cho nhiều thread cập nhật đồng thời. Thay bằng:

```java
List<String> result = orders.parallelStream()
        .filter(isPaidOrder())
        .map(Order::id)
        .toList();
```

Hai đoạn là **phương án thay thế**, không đặt hai khai báo `result` trong cùng phạm vi. Mục tiêu của pipeline là tạo danh sách nên `toList()` thể hiện đúng ý định và cho framework quản lý aggregation.

**Cần side effect nghiệp vụ?** Chẳng hạn thanh toán, gửi email hoặc cấp quyền, hãy thể hiện trong một service/action riêng, có hợp đồng transaction, retry, idempotency và lỗi. Một `Consumer<Order>` có thể được truyền như callback, nhưng tên hàm phải nói rõ hành động và người thiết kế phải kiểm soát khi nào, bao nhiêu lần, trên thread nào nó được gọi. Stream không tự mang các bảo đảm nghiệp vụ này.

## 17. Đừng che giấu chi phí I/O sau một Function đơn giản

Chữ ký như:

```java
Function<CustomerId, Customer> loadCustomer;
```

không cho caller biết `loadCustomer.apply(id)` có thể gọi database, thực hiện network I/O, có latency hoặc thất bại. Khi chức năng quan trọng, hãy dùng một abstraction domain rõ ràng như `CustomerRepository.findById(CustomerId)` và một hợp đồng trả lỗi thích hợp.

Có thể truyền repository method reference vào higher-order utility trong tầng application, nhưng **đừng đánh đồng phép map thuần trong bộ nhớ với một lần truy cập tài nguyên bên ngoài**. Ví dụ dùng `ids.parallelStream().map(repository::findById)` không tự bảo đảm repository thread-safe hoặc truy vấn thực hiện với giới hạn concurrency hợp lý.

Dấu hiệu abstraction đang quá tổng quát:
1. Caller phải truyền 4–5 lambda chỉ để thực hiện một use case cố định.
2. Mỗi lambda có thể gọi I/O nhưng tên method nói như một phép tính thuần.
3. Exception bị bắt rồi đổi hết thành null hoặc `Optional.empty()`.
4. Mọi giá trị đầu vào/đầu ra đều bị ép thành `Object` hoặc `Map<String,Object>`.
5. Unit test chỉ kiểm tra helper hoạt động, không kiểm tra chính sách business.

Cách sửa thường là **tách các bước có tên nghiệp vụ**, giữ generic helper ở nơi thích hợp và đưa lỗi/side effect ra một boundary rõ ràng.

## 18. Generic wildcard và ranh giới kiểu: đủ linh hoạt nhưng đừng làm rối API

Generic trong Java là *invariant*: `List<PremiumCustomer>` không tự là `List<Customer>`, ngay cả khi `PremiumCustomer` kế thừa `Customer`.

Khi cần nhận dữ liệu chỉ để đọc, có thể cân nhắc `? extends T`; khi nhận hành vi tiêu thụ `T`, dạng `? super T` thường phù hợp. Nguyên tắc nhớ nhanh là **PECS** (*Producer Extends, Consumer Super*), nhưng phải áp dụng theo vai trò thực tế trong chữ ký.

Ví dụ helper:

```java
static <T, R> List<R> transform(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper) {
    return source.stream().map(mapper).toList();
}
```

Đây là mảnh method minh họa có import `List` và `Function`. Nó cho phép source cung cấp subtype của `T`, còn mapper có thể nhận một supertype của `T` và trả subtype của `R`. Với nhiều API nội bộ đơn giản, chữ ký `List<T>` là đủ; đừng thêm wildcard chỉ vì “generic hơn”.

**Điểm cần giữ nguyên:** wildcard phải phục vụ khả năng tái sử dụng thật; nếu tạo chữ ký khó đọc mà không giúp use case nào, lợi ích bị đảo ngược. Tại public domain API, `List<Invoice>` rõ nghĩa hơn `List<? extends BaseEntity>` nếu chức năng chỉ xử lý invoice.

### Khi dùng bounded type parameter

Một generic helper thật sự yêu cầu object so sánh được có thể dùng:

```java
static <T extends Comparable<? super T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là mảnh method hợp lệ, nhưng nó mô tả **quy tắc so sánh kỹ thuật**. Nếu business muốn “khách hàng ưu tiên theo cấp bậc”, hãy định nghĩa `Comparator<Customer>` theo chính sách ưu tiên, không dùng `compareTo` tùy tiện rồi gọi đó là thứ tự nghiệp vụ.

## 19. Code review: nhận diện abstraction hữu ích hay gây khó hiểu

Khi review code functional/generic, nên hỏi:

| Câu hỏi | Dấu hiệu tốt | Cảnh báo |
| --- | --- | --- |
| Tên method cho biết *việc gì*? | `eligibleForRefund`, `toInvoiceSummary` | `doWork`, `runFunc`, `handle` |
| Tên kiểu có domain? | `OrderId`, `CustomerId`, `Money` | `String`/ `Object` cho mọi thứ |
| Generic giúp gì? | Dùng lại 2+ thuật toán cùng cấu trúc | Viết một lần nhưng có quá nhiều type parameter |
| Tham số Function/Predicate có ý nghĩa? | Rule được đặt tên, có kiểm thử | Lambda dài và side effect |
| Có giữ business invariants? | Check trạng thái, tiền, ID ngay nơi thích hợp | Model cho phép trạng thái vô nghĩa |
| Có biết thứ tự không? | Pipeline ordered khi yêu cầu | Phụ thuộc `parallelStream().forEach` |
| Có biết lỗi đến từ đâu? | Exception/Result/Optional theo hợp đồng | Trả null hoặc nuốt mọi lỗi |
| Kết quả có đúng kiểu domain? | `Receipt`, `EligibilityDecision` | `Map<String,Object>` tùy ý |
| Test mô tả chính sách? | Tên test nêu điều kiện nghiệp vụ | Chỉ test một helper generic |

Một nguyên tắc hữu ích: **đặt abstraction tại nơi phát sinh sự thay đổi ổn định**. Nếu quy tắc đủ điều kiện thường đổi, đưa nó vào một policy có tên; nếu cơ chế duyệt danh sách đã ổn định, generic utility có thể tái sử dụng. Đừng nhét cả hai vào một callback `Function<T,R>` khó hiểu.

## 20. Những lỗi thường gặp

1. **Tên quá chung:** `process`, `apply`, `check` không nói rõ nghiệp vụ.
2. **Tổng quát hóa trước nhu cầu:** tạo `Pipeline<T,U,V,W>` cho một tác vụ duy nhất.
3. **Lạm dụng `Object`, `Map<String,Object>`:** mất sự trợ giúp của type system.
4. **Truyền nhiều lambda vô danh:** caller phải đọc implementation mới biết mục đích.
5. **Cho rằng Function nào cũng thuần:** callback có thể có side effect, lỗi và I/O.
6. **Cho rằng generic tự giữ invariant nghiệp vụ:** record/Class vẫn cần validation.
7. **Dùng `String` cho mọi loại ID:** compiler không bắt được việc đổi nhầm Customer ID và Order ID.
8. **Gắn tên `isEligible` cho điều kiện không đúng chính sách:** tên đẹp không cứu được logic sai; cần test ranh giới.
9. **Viết quy tắc tuổi/ngưỡng trực tiếp tại nhiều Stream:** dễ khác nhau giữa các use case.
10. **Dùng Optional để nuốt mọi loại lỗi:** không tìm thấy và lỗi hệ thống là hai trạng thái khác nhau.
11. **Lạm dụng generic ở public API:** bắt caller cung cấp framework callback dù business chỉ có một hành động rõ ràng.
12. **Dùng Predicate có side effect bắt buộc:** điều kiện có thể short-circuit, không chạy mọi callback.
13. **Dùng external mutable list trong parallel Stream:** nguy cơ race condition.
14. **Bọc mọi primitive thành class riêng:** tăng độ phức tạp không tương xứng nếu không bảo vệ invariant quan trọng.
15. **Đổi tên theo thao tác kỹ thuật thay vì ý nghĩa:** `filterOrders` mơ hồ hơn `findRefundableOrders` khi logic thực sự là hoàn tiền.
16. **Không phân biệt thao tác đọc với action có tác dụng:** `buildReceiptPreview` không giống `issueReceipt`.
17. **Giấu database/network sau mapper mà không kiểm soát concurrency:** có thể gây nghẽn và khó xử lý lỗi.
18. **Không so sánh chi phí abstraction:** một vòng lặp rõ ràng đôi khi tốt hơn một chain generic khó debug.

## 21. Gợi ý thực hành khi thiết kế API mới

Một quy trình đơn giản:

1. Viết một câu bằng ngôn ngữ nghiệp vụ: “Chọn đơn đã thanh toán và có giá trị đủ ngưỡng để tạo tóm tắt hóa đơn”.
2. Chọn domain types: `Order`, `OrderState`, `InvoiceSummary`, một loại ID nếu cần.
3. Định nghĩa policy bằng tên: `isPaidOrder`, `hasMinimumAmount`, `eligibleForInvoice`.
4. Xác định output: `List<InvoiceSummary>`, không dùng `List<Object>`.
5. Viết pipeline nhỏ, dễ đọc bằng `filter`, `map`, `toList`.
6. Chỉ trích xuất generic helper khi có ít nhất một quy luật tái sử dụng thực sự.
7. Đặt tên method public theo use case: `buildInvoiceSummariesForEligibleOrders`.
8. Kiểm tra boundary: null, amount âm, trạng thái lạ, không có dữ liệu, duplicate ID, lỗi I/O.
9. Viết test theo chính sách tại ngưỡng và trường hợp không đủ điều kiện.
10. Review lại một người khác có thể đọc tên/kiểu và hiểu flow mà không mở ngay implementation hay không.

**Tính rõ ràng là một chức năng chất lượng.** Compiler kiểm tra được kiểu dữ liệu, nhưng chỉ con người và kiểm thử có thể xác nhận ngôn ngữ nghiệp vụ được dùng chính xác.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `isPaidOrder()` thường dễ hiểu hơn `Predicate<Order> p = x -> x.state() == PAID` khi quy tắc xuất hiện nhiều nơi?

**Đáp án:** Tên đưa khái niệm “đơn đã thanh toán” vào API; caller không phải lặp và giải mã phép so sánh. Luật cũng có thể kiểm thử/tái sử dụng dễ hơn.

**Câu 2.** Khi nào nên tạo một helper generic `selectAndMap`?

Khi nhiều luồng xử lý thật sự lặp cùng cấu trúc lọc rồi biến đổi và helper có tên/hợp đồng rõ. Không chỉ vì một pipeline nhìn dài vài dòng.

**Câu 3.** `Predicate<Customer>` có khác `CustomerEligibilityRule` về khả năng nhận lambda không?

Cả hai có thể là functional interface. `Predicate<Customer>` phổ biến, dễ tích hợp Stream; `CustomerEligibilityRule` có thể có tên/hợp đồng domain và default methods riêng. Chọn theo giá trị truyền đạt ý nghĩa, không bắt buộc tự tạo interface.

**Câu 4.** Vì sao `Map<CustomerId,Long>` có thể an toàn hơn `Map<String,Long>`?

Vì generic với domain ID type giúp ngăn truyền nhầm loại khóa, trong khi String không nói rõ đó là Customer ID, Order ID hay một mã khác. Record còn có thể kiểm tra ID rỗng trong constructor.

**Câu 5.** `Function<? super T, ? extends R>` có ý nghĩa gì?

Mapper có thể **nhận T qua một kiểu cha phù hợp** và **trả một kiểu con của R**. Đây là cách thiết kế cho vai trò tiêu thụ đầu vào và cung cấp đầu ra, nhưng chỉ dùng khi mang lại tính linh hoạt thực.

**Câu 6.** Vì sao không nên giấu thao tác “gửi email thanh toán” trong một `map` thuần?

Vì đó là side effect/I/O cần kiểm soát lỗi, retry, idempotency và thời điểm thực thi. Stream có thể lazy và một số phép tối ưu/short-circuit không hứa mọi callback được gọi theo cách bạn mong.

**Câu 7.** Khi nào `Optional.empty()` không phù hợp làm toàn bộ kết quả?

Khi business cần biết **vì sao** thất bại: không đủ ngưỡng, bị khóa, không xác thực hoặc lỗi hệ thống. Một kết quả có mã lý do, record hoặc exception được thiết kế rõ có thể tốt hơn.

**Câu 8.** Tên `process(data, f1, f2, f3)` có phải một abstraction tốt nếu chỉ có một use case cụ thể không?

Thường không. Nó che giấu domain và khiến người đọc giải mã nhiều callback. Hãy đặt một API nghiệp vụ có tên/kiểu rõ trước; tổng quát hóa nếu có nhu cầu tái sử dụng bền vững.

**Câu 9.** Chương trình `GenericBoundaryDemo` cho thấy lợi ích gì khi có cả `selectAndMap` và `receiptsForPaidInvoices`?

Helper generic tái sử dụng cơ chế, còn phương thức domain mô tả mục tiêu rõ ràng. Người gọi dùng tên nghiệp vụ mà không cần truyền lambda mỗi lần.

**Câu 10.** Quy tắc nào quan trọng hơn: “sử dụng càng nhiều generic càng tốt” hay “giữ API diễn đạt domain rõ ràng”?

**Đáp án:** Giữ API diễn đạt đúng domain, dùng generic đúng mức để tái sử dụng cơ chế và bảo toàn kiểu. Generic là phương tiện, không phải mục tiêu.

**Ghi nhớ:** **Tên miền nghiệp vụ rõ ràng là ưu tiên của thiết kế functional.** Dùng `Predicate`, `Function`, generic, method reference và higher-order function để tổ chức logic, nhưng đừng đánh mất ý nghĩa của `Order`, `Customer`, `Payment`, `Eligibility` và kết quả cuối. Một abstraction tốt giúp đọc chính sách dễ hơn, chứ không buộc người đọc giải mã thêm nhiều tầng callback.
