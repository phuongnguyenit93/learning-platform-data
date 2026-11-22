# Kết hợp đặc tả bằng AND, OR, NOT khi phù hợp với ngữ nghĩa

Trong Domain-Driven Design (DDD), **Specification** đóng gói một tiêu chí nghiệp vụ thành một đối tượng có thể diễn đạt, tái sử dụng và kiểm tra. Một đặc tả có thể trả lời câu hỏi như “đơn hàng có đủ điều kiện xác nhận không?”, “khách hàng có được hưởng ưu đãi không?” hoặc “sản phẩm có phù hợp với chính sách nhập kho không?”. Khi nhiều điều kiện cùng tham gia một quyết định, ta có thể kết hợp các Specification bằng các phép logic **AND**, **OR** và **NOT**.

Kết hợp đúng giúp quy tắc phức tạp được diễn đạt từ những tiêu chí nhỏ, có tên và có thể kiểm thử riêng. Tuy nhiên, phép toán logic chỉ có ý nghĩa khi nhóm hiểu chính xác phạm vi, dữ liệu và cách diễn giải của từng điều kiện. Một biểu thức `A OR B` có thể mở rộng quyền lợi cho nhiều nhóm; `A AND B` có thể thu hẹp đối tượng; `NOT A` có thể bao gồm cả những trường hợp chưa đủ thông tin nếu định nghĩa không rõ.

Bài học này trình bày ngữ nghĩa của AND, OR, NOT, cách kết hợp Specification trong Java, các lưu ý về null và dữ liệu chưa xác định, cách sử dụng trong domain model và truy vấn, cùng phương pháp kiểm thử để bảo đảm biểu thức phản ánh đúng chính sách nghiệp vụ.

## 1. Specification biểu diễn một tiêu chí nghiệp vụ

Specification là một cách đóng gói điều kiện để xác định một đối tượng có thỏa mãn tiêu chí hay không. Thay vì rải một biểu thức điều kiện dài ở nhiều service hoặc controller, nhóm đặt tiêu chí vào một đơn vị có tên và trách nhiệm rõ.

Ví dụ trong hệ thống bán hàng:

- `OrderIsSubmitted`: đơn đã được gửi.
- `OrderHasValidPayment`: đơn có thông tin thanh toán hợp lệ.
- `OrderIsNotCancelled`: đơn chưa bị hủy.
- `CustomerIsEligibleForPromotion`: khách hàng đủ điều kiện nhận ưu đãi.
- `OrderMeetsMinimumAmount`: đơn đạt giá trị tối thiểu.

Một Specification thường trả lời một câu hỏi boolean trên một đối tượng ứng viên. Trong DDD, Specification có thể được dùng để kiểm tra một đối tượng miền, chọn đối tượng phù hợp hoặc diễn đạt một chính sách. Cách triển khai có thể là một class, một lambda, một predicate hoặc một cây biểu thức tùy độ phức tạp và yêu cầu lưu trữ/truy vấn.

### 1.1. Ví dụ tiêu chí đơn giản

```java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}
```

Một đặc tả kiểm tra đơn hàng đã được gửi:

```java
public final class OrderIsSubmitted implements Specification<Order> {
    @Override
    public boolean isSatisfiedBy(Order order) {
        return order.status() == OrderStatus.SUBMITTED;
    }
}
```

Đặc tả có tên giúp người đọc hiểu mục đích nghiệp vụ mà không cần giải mã một biểu thức boolean dài. Khi tiêu chí thay đổi, nhóm có một nơi rõ ràng để cập nhật và kiểm thử.

## 2. Ngữ nghĩa của AND, OR và NOT

Các phép toán logic kết hợp kết quả của những Specification thành một tiêu chí mới.

### 2.1. AND — tất cả điều kiện đều phải đúng

`A AND B` chỉ đúng khi cả A và B đều đúng. Trong nghiệp vụ, AND thường biểu diễn nhiều điều kiện bắt buộc phải đồng thời thỏa mãn.

Ví dụ: một đơn chỉ được tự động xác nhận khi:

- Đơn đã được gửi.
- Thanh toán đã được ghi nhận.
- Đơn chưa bị hủy.
- Địa chỉ giao hàng hợp lệ.

Có thể diễn đạt:

\[
Eligible = Submitted \land Paid \land NotCancelled \land ValidAddress
\]

Nếu chỉ một điều kiện sai, kết quả tổng thể là sai. Khi một điều kiện chưa có đủ dữ liệu để kết luận, cần xác định rõ nó được xem là không thỏa, cần chờ bổ sung hay chuyển sang xử lý thủ công.

### 2.2. OR — ít nhất một điều kiện đúng

`A OR B` đúng khi A hoặc B hoặc cả hai cùng đúng. OR thường diễn đạt các con đường thay thế để đạt một điều kiện nghiệp vụ.

Ví dụ: khách hàng có thể đủ điều kiện nhận ưu đãi nếu là thành viên Gold **hoặc** là nhân viên công ty:

\[
EligibleCustomer = Gold \lor Employee
\]

Nếu cả hai cùng đúng, kết quả vẫn là đúng. Nhưng việc có được cộng dồn hai ưu đãi hay chỉ áp dụng một ưu đãi là một chính sách khác cần được mô tả riêng. OR chỉ trả lời điều kiện có thỏa mãn hay không; nó không tự quyết định cách tính quyền lợi khi nhiều nhánh cùng đúng.

### 2.3. NOT — điều kiện phủ định

`NOT A` đúng khi A sai trong miền giá trị đang xét. Ví dụ:

- Đơn chưa bị hủy.
- Sản phẩm không thuộc danh mục bị loại trừ.
- Khách hàng không nằm trong danh sách bị hạn chế.

NOT cần được dùng cẩn thận vì “không thỏa A” không phải lúc nào cũng đồng nghĩa với “đủ điều kiện”. Nếu dữ liệu bị thiếu hoặc trạng thái chưa xác định, phủ định một điều kiện có thể tạo ra kết quả ngoài mong muốn.

Ví dụ, `NOT CustomerIsBlocked` không nên tự động trả về true nếu hệ thống chưa tra cứu được trạng thái khách hàng. “Không bị chặn” và “chưa biết có bị chặn hay không” là hai trạng thái nghiệp vụ khác nhau.

## 3. Bảng chân trị và quy tắc kết hợp

Với logic hai giá trị (`true`/`false`), các phép toán có bảng chân trị:

| A | B | A AND B | A OR B | NOT A |
|---|---|---|---|---|
| true | true | true | true | false |
| true | false | false | true | false |
| false | true | false | true | true |
| false | false | false | false | true |

Các quy tắc này có vẻ đơn giản, nhưng khi áp dụng vào chính sách thực tế, cần hiểu phạm vi ứng viên, dữ liệu đầu vào và ý nghĩa của từng nhánh.

### 3.1. Thứ tự ưu tiên và dấu ngoặc

Trong toán học và nhiều ngôn ngữ lập trình, NOT được xử lý trước AND, rồi đến OR. Tuy nhiên, không nên dựa vào thứ tự ưu tiên ngầm trong một chính sách quan trọng. Hãy nhóm điều kiện bằng dấu ngoặc hoặc bằng cách kết hợp Specification thành các biến có tên.

Ví dụ, yêu cầu “khách hàng Gold hoặc nhân viên, và đơn đạt giá trị tối thiểu” là:

\[
(Gold \lor Employee) \land MinimumAmount
\]

Nó khác với:

\[
Gold \lor (Employee \land MinimumAmount)
\]

Ở biểu thức thứ hai, khách hàng Gold được chấp nhận dù đơn không đạt giá trị tối thiểu. Nếu chính sách yêu cầu mọi khách hàng đều phải đạt ngưỡng, thiếu dấu ngoặc có thể tạo ra lỗ hổng quyền lợi.

### 3.2. Luật De Morgan

Hai luật De Morgan giúp chuyển đổi giữa AND, OR và NOT:

\[
\neg(A \land B) = (\neg A) \lor (\neg B)
\]

\[
\neg(A \lor B) = (\neg A) \land (\neg B)
\]

Ví dụ, “không phải cả hai điều kiện đều đúng” tương đương “ít nhất một điều kiện sai”. “Không thuộc bất kỳ nhóm bị loại trừ nào” có thể được diễn đạt thành “không thuộc nhóm A và cũng không thuộc nhóm B”.

Các luật này đúng với logic hai giá trị. Nếu hệ thống có trạng thái chưa biết, null hoặc dữ liệu không thể xác minh, cần xác định ngữ nghĩa riêng trước khi biến đổi biểu thức.

## 4. Thiết kế Specification có thể kết hợp trong Java

Một interface có thể cung cấp các phương thức mặc định `and`, `or` và `not`. Mỗi phương thức trả về một Specification mới, kết hợp hành vi của các đặc tả thành phần.

```java
import java.util.Objects;

@FunctionalInterface
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);

    default Specification<T> and(Specification<T> other) {
        Objects.requireNonNull(other, "other");
        return candidate ->
                this.isSatisfiedBy(candidate)
                && other.isSatisfiedBy(candidate);
    }

    default Specification<T> or(Specification<T> other) {
        Objects.requireNonNull(other, "other");
        return candidate ->
                this.isSatisfiedBy(candidate)
                || other.isSatisfiedBy(candidate);
    }

    default Specification<T> not() {
        return candidate -> !this.isSatisfiedBy(candidate);
    }
}
```

Các phương thức dùng `&&` và `||` của Java nên có short-circuit evaluation:

- Với AND, nếu vế trái là false thì vế phải không được gọi.
- Với OR, nếu vế trái là true thì vế phải không được gọi.
- Với NOT, kết quả của một đặc tả được đảo lại.

Short-circuit giúp tránh thực hiện các phép kiểm tra không cần thiết. Tuy nhiên, Specification nên thuần (pure) và không có side effect. Không nên dựa vào việc một nhánh được hoặc không được gọi để ghi dữ liệu, gửi message hay thực hiện một hành động nghiệp vụ.

### 4.1. Tạo các Specification có tên

Giả sử mô hình có `Order` với trạng thái, tổng tiền, hạng khách hàng và cờ kiểm tra thủ công. Ta có thể tạo các đặc tả:

```java
public final class OrderIsSubmitted implements Specification<Order> {
    @Override
    public boolean isSatisfiedBy(Order order) {
        return order.status() == OrderStatus.SUBMITTED;
    }
}

public final class OrderIsNotCancelled implements Specification<Order> {
    @Override
    public boolean isSatisfiedBy(Order order) {
        return order.status() != OrderStatus.CANCELLED;
    }
}

public final class OrderDoesNotRequireManualReview
        implements Specification<Order> {
    @Override
    public boolean isSatisfiedBy(Order order) {
        return !order.requiresManualReview();
    }
}
```

Những lớp này có thể được thay bằng lambda khi tiêu chí rất đơn giản. Nên ưu tiên tên thể hiện ý nghĩa nghiệp vụ và giữ các điều kiện quan trọng có thể kiểm thử độc lập.

## 5. Ví dụ kết hợp AND: tất cả điều kiện bắt buộc

Giả sử đơn hàng chỉ được xác nhận tự động khi:

1. Đơn đã được gửi.
2. Thanh toán đã được ghi nhận.
3. Đơn chưa bị hủy.
4. Đơn không cần kiểm tra thủ công.

Ta có thể kết hợp:

```java
Specification<Order> eligibleForAutomaticConfirmation =
        new OrderIsSubmitted()
                .and(new OrderHasRecordedPayment())
                .and(new OrderIsNotCancelled())
                .and(new OrderDoesNotRequireManualReview());
```

Đặc tả tổng hợp chỉ đúng khi tất cả điều kiện thành phần đều đúng. Khi một điều kiện thay đổi, nhóm có thể kiểm thử riêng tiêu chí đó và kiểm thử lại kết quả tổng hợp.

### 5.1. Đặt tên cho nhóm điều kiện

Nếu một nhóm tiêu chí được dùng ở nhiều nơi, hãy đặt tên cho nó:

```java
Specification<Order> paymentAndOrderStateAreValid =
        new OrderIsSubmitted()
                .and(new OrderHasRecordedPayment())
                .and(new OrderIsNotCancelled());

Specification<Order> eligibleForAutomaticConfirmation =
        paymentAndOrderStateAreValid
                .and(new OrderDoesNotRequireManualReview());
```

Tên trung gian giúp người đọc nhận ra nhóm quy tắc và giảm độ dài biểu thức. Nhưng không nên tạo quá nhiều tên trừu tượng khiến người đọc phải nhảy qua nhiều file mới hiểu điều kiện.

## 6. Ví dụ kết hợp OR: nhiều con đường thay thế

Giả sử một chương trình ưu đãi dành cho khách hàng Gold hoặc nhân viên, với điều kiện đơn đạt mức tối thiểu. Có thể xây dựng:

```java
Specification<Customer> isGold = new CustomerHasTier(CustomerTier.GOLD);
Specification<Customer> isEmployee = new CustomerIsEmployee();

Specification<Customer> qualifiesForAudience = isGold.or(isEmployee);

Specification<Order> meetsMinimumAmount = new OrderMeetsMinimumAmount(
        new Money(new java.math.BigDecimal("500000"),
                  java.util.Currency.getInstance("VND")));
```

Vì Specification ở đây nhận các kiểu khác nhau (`Customer` và `Order`), không thể kết hợp trực tiếp bằng `and` trong interface generic. Application hoặc một domain policy cần nhận cả đối tượng và phối hợp hai tiêu chí:

```java
public final class PromotionEligibility {
    private final Specification<Customer> eligibleAudience;
    private final Specification<Order> minimumOrderAmount;

    public PromotionEligibility(
            Specification<Customer> eligibleAudience,
            Specification<Order> minimumOrderAmount) {
        this.eligibleAudience = eligibleAudience;
        this.minimumOrderAmount = minimumOrderAmount;
    }

    public boolean isEligible(Customer customer, Order order) {
        return eligibleAudience.isSatisfiedBy(customer)
                && minimumOrderAmount.isSatisfiedBy(order);
    }
}
```

Điểm quan trọng là AND/OR chỉ kết hợp trực tiếp các đặc tả có cùng kiểu ứng viên. Nếu tiêu chí liên quan nhiều đối tượng hoặc nhiều nguồn dữ liệu, cần một policy hoặc specification cấp cao hơn có đầu vào phù hợp, không ép kiểu tùy tiện.

### 6.1. OR không đồng nghĩa cộng dồn quyền lợi

Nếu khách hàng vừa là Gold vừa là nhân viên, biểu thức `isGold.or(isEmployee)` chỉ kết luận khách hàng thuộc nhóm đủ điều kiện. Nó không quyết định:

- Khách hàng được nhận một ưu đãi hay hai ưu đãi.
- Ưu đãi nào được ưu tiên.
- Có được cộng dồn với mã giảm giá khác không.
- Mức giảm được tính trên giá trước hay sau thuế.

Những câu hỏi đó thuộc chính sách tính quyền lợi và cần được mô hình hóa riêng. Specification xác định điều kiện; policy quyết định hành động hoặc kết quả khi điều kiện thỏa.

## 7. Ví dụ kết hợp NOT: loại trừ một nhóm

Giả sử một chương trình không áp dụng cho sản phẩm thuộc danh mục bị loại trừ. Ta có thể định nghĩa:

```java
Specification<Product> isInExcludedCategory =
        new ProductInCategory(ProductCategory.CLEARANCE);

Specification<Product> isEligibleProduct = isInExcludedCategory.not();
```

Hoặc đặt tên trực tiếp cho tiêu chí dương:

```java
public final class ProductIsPromotionEligible
        implements Specification<Product> {
    @Override
    public boolean isSatisfiedBy(Product product) {
        return product.category() != ProductCategory.CLEARANCE;
    }
}
```

Tên dương thường dễ đọc ở nơi gọi. Phương thức `not()` hữu ích khi cần tái sử dụng tiêu chí gốc hoặc kết hợp động, nhưng không bắt buộc phải phủ định mọi điều kiện bằng toán tử NOT.

### 7.1. Phủ định một điều kiện có thể quá rộng

Giả sử `CustomerHasVerifiedEmail` trả về false nếu email chưa xác minh, nhưng cũng trả false nếu dữ liệu khách hàng chưa tải được. Khi dùng `.not()`, cả hai trường hợp đều trở thành true. Điều này có thể vô tình cho phép khách hàng chưa được kiểm tra.

Hãy phân biệt ít nhất ba trạng thái khi nghiệp vụ cần:

- Đã xác minh.
- Chưa xác minh.
- Chưa biết hoặc không thể kiểm tra.

Nếu chưa biết phải dẫn đến từ chối hoặc chờ xác minh, Specification boolean cần được thiết kế sao cho không biến trạng thái chưa biết thành kết quả phủ định được chấp nhận.

## 8. Kết hợp biểu thức phức hợp

Một chính sách thực tế thường có nhiều nhánh. Ví dụ, một đơn được phép chuyển sang giao hàng khi:

- Đã thanh toán và tồn kho đã được xác nhận.
- Hoặc đơn thuộc hình thức thanh toán khi nhận hàng và tồn kho đã được xác nhận.
- Đồng thời đơn chưa bị hủy và không bị giữ để kiểm tra gian lận.

Có thể biểu diễn:

\[
CanFulfill = ((Paid \land StockConfirmed) \lor (CashOnDelivery \land StockConfirmed))
\land \neg Cancelled \land \neg FraudHold
\]

Trong Java:

```java
Specification<Order> paidAndStockConfirmed =
        new OrderHasRecordedPayment()
                .and(new OrderHasConfirmedStock());

Specification<Order> codAndStockConfirmed =
        new OrderUsesCashOnDelivery()
                .and(new OrderHasConfirmedStock());

Specification<Order> fulfillmentEligible =
        paidAndStockConfirmed
                .or(codAndStockConfirmed)
                .and(new OrderIsNotCancelled())
                .and(new OrderIsNotOnFraudHold());
```

Do `and` và `or` được gọi theo chuỗi, biểu thức trên được nhóm theo thứ tự gọi: kết quả OR được tạo trước, sau đó AND với các điều kiện còn lại. Nếu cách nhóm có thể gây tranh luận, hãy dùng biến trung gian hoặc factory method để thể hiện dấu ngoặc nghiệp vụ rõ hơn.

### 8.1. Tránh biểu thức boolean khó đọc

Không nên viết một điều kiện dài với nhiều `&&`, `||` và `!` ngay trong application service. Hãy chia thành những Specification có tên và có ý nghĩa:

```java
Specification<Order> paymentPath =
        new OrderHasRecordedPayment()
                .or(new OrderUsesCashOnDelivery());

Specification<Order> readyToFulfill =
        paymentPath
                .and(new OrderHasConfirmedStock())
                .and(new OrderIsNotCancelled())
                .and(new OrderIsNotOnFraudHold());
```

Tên `paymentPath` làm rõ hai cách thanh toán thay thế nhau; `readyToFulfill` diễn đạt quyết định cuối cùng. Cần bảo đảm cấu trúc code phản ánh chính xác dấu ngoặc của chính sách.

## 9. Những luật đại số hữu ích khi kết hợp Specification

Với các Specification thuần, cùng kiểu đầu vào và logic hai giá trị, một số luật giúp đơn giản hóa biểu thức.

### 9.1. Tính kết hợp

\[
(A \land B) \land C = A \land (B \land C)
\]

\[
(A \lor B) \lor C = A \lor (B \lor C)
\]

Có thể nhóm các điều kiện AND hoặc OR theo từng phần mà không đổi kết quả logic.

### 9.2. Tính giao hoán

\[
A \land B = B \land A
\]

\[
A \lor B = B \lor A
\]

Về mặt logic, đổi thứ tự không đổi kết quả. Nhưng nếu Specification có side effect, truy cập mạng hoặc có thể ném lỗi khác nhau, thứ tự thực thi có thể tạo khác biệt. Vì vậy, Specification nên là phép kiểm tra thuần, không tạo tác động phụ.

### 9.3. Tính phân phối

\[
A \land (B \lor C) = (A \land B) \lor (A \land C)
\]

\[
A \lor (B \land C) = (A \lor B) \land (A \lor C)
\]

Các phép biến đổi này có thể giúp tổ chức hoặc tối ưu biểu thức, nhưng không nên làm mất cấu trúc dễ hiểu của chính sách. Hãy ưu tiên cách diễn đạt mà chuyên gia nghiệp vụ có thể xác nhận.

### 9.4. Idempotence và phần bù

\[
A \land A = A
\]

\[
A \lor A = A
\]

\[
A \land \neg A = False
\]

\[
A \lor \neg A = True
\]

Hai luật cuối chỉ đúng khi A có kết quả xác định trong logic hai giá trị và NOT được tính trên cùng một miền ứng viên. Nếu có unknown/null, cần định nghĩa logic khác.

## 10. Xử lý null và dữ liệu chưa xác định

Một Specification boolean thường chỉ trả về `true` hoặc `false`. Nhưng dữ liệu nghiệp vụ có thể thiếu, chưa đồng bộ hoặc chưa được xác minh. Cần quyết định rõ cách xử lý thay vì để null gây lỗi hoặc bị phủ định thành true.

### 10.1. Fail closed cho điều kiện bắt buộc

Với điều kiện an toàn hoặc quyền lợi cần xác minh, một lựa chọn là xem dữ liệu thiếu như không đủ điều kiện:

```java
Specification<Customer> hasVerifiedEmail = customer ->
        customer.emailVerificationStatus() == VerificationStatus.VERIFIED;
```

Nếu `emailVerificationStatus()` có thể null, phép so sánh enum `==` trả false khi giá trị null. Tuy nhiên, cần chắc rằng đây là chính sách mong muốn. Có thể tốt hơn nếu mô hình dùng một kiểu trạng thái không null như `UNKNOWN`, `PENDING`, `VERIFIED`, `REJECTED`.

### 10.2. Không dùng NOT để suy ra điều chưa biết

Nếu một truy vấn thất bại hoặc không tải được dữ liệu, không nên trả `false` rồi phủ định thành `true`. Hãy để lỗi kỹ thuật được thể hiện riêng hoặc dùng một kết quả ba trạng thái nếu nghiệp vụ cần phân biệt.

Ví dụ một kiểu kết quả:

```java
public enum EvaluationResult {
    SATISFIED,
    NOT_SATISFIED,
    UNDETERMINED
}
```

Khi dùng kết quả ba trạng thái, phải định nghĩa bảng kết hợp AND/OR/NOT phù hợp. Không nên tự động áp dụng bảng chân trị hai giá trị cho `UNDETERMINED`.

### 10.3. Khác biệt với SQL NULL

SQL sử dụng logic ba giá trị trong nhiều biểu thức: `TRUE`, `FALSE` và `UNKNOWN`. Ví dụ, `NULL = 5` cho kết quả UNKNOWN; `NOT UNKNOWN` vẫn là UNKNOWN. Vì vậy, điều kiện trong Java và điều kiện trong SQL có thể không tương đương nếu field nullable.

Khi chuyển Specification sang truy vấn database, cần kiểm tra rõ:

- Field có thể null hay không.
- Null được xem là không thỏa, chưa biết hay một giá trị đặc biệt.
- Phủ định có bao gồm bản ghi null không.
- Truy vấn có cần `IS NULL` hoặc `IS NOT NULL` rõ ràng không.

Không nên giả định `NOT predicate` trong Java tự động tương đương `NOT (...)` trong SQL.

## 11. Specification nên thuần và không chứa side effect

Specification nên trả lời “đối tượng có thỏa điều kiện không?” chứ không nên thực hiện hành động khi đánh giá.

Tránh viết:

```java
Specification<Order> sendsNotification = order -> {
    notificationService.send(order.customerEmail());
    return order.total().isPositive();
};
```

Đoạn code này nguy hiểm khi được kết hợp bằng AND/OR vì short-circuit có thể khiến notification được gửi hoặc không gửi tùy thứ tự và kết quả của nhánh trước. Việc đánh giá lặp lại cũng có thể gửi nhiều thông báo.

Thay vào đó:

```java
Specification<Order> hasPositiveTotal =
        order -> order.total().isPositive();

if (hasPositiveTotal.isSatisfiedBy(order)) {
    notificationService.send(order.customerEmail());
}
```

Specification quyết định điều kiện; application service hoặc policy handler thực hiện side effect sau khi quyết định được đưa ra. Nếu hành động cần transaction hoặc event, hãy xử lý bằng cơ chế phù hợp.

## 12. Kết hợp Specification trên cùng một kiểu ứng viên

Interface generic `Specification<T>` cho phép kết hợp các đặc tả cùng nhận kiểu `T`. Ví dụ, `Specification<Order>` có thể kết hợp với `Specification<Order>`. Không thể trực tiếp AND `Specification<Customer>` với `Specification<Order>` vì chúng mô tả hai miền ứng viên khác nhau.

Khi cần quyết định dựa trên nhiều đối tượng, có một số cách:

- Tạo một policy nhận cả hai đối tượng và gọi từng Specification thành phần.
- Tạo một kiểu ứng viên chứa các tham chiếu cần thiết, ví dụ `PromotionCandidate(customer, order)`.
- Dùng một domain service để phối hợp dữ liệu và đánh giá chính sách.

Ví dụ kiểu ứng viên:

```java
public record PromotionCandidate(Customer customer, Order order) {}

Specification<PromotionCandidate> eligibleForPromotion = candidate ->
        customerAudience.isSatisfiedBy(candidate.customer())
        && minimumOrderAmount.isSatisfiedBy(candidate.order());
```

Cách này hữu ích khi nhiều quy tắc thường xuyên được kết hợp trên cùng một tập dữ liệu nghiệp vụ. Nếu chỉ có một quyết định đơn giản, một policy method có thể dễ đọc hơn việc tạo thêm abstraction.

## 13. Dùng Specification cho truy vấn và lựa chọn đối tượng

Specification không chỉ dùng để quyết định một hành động. Nó còn có thể diễn đạt tiêu chí tìm kiếm, chẳng hạn tìm các đơn đã thanh toán, chưa bị hủy và có giá trị trên một ngưỡng.

Với một danh sách đã ở trong bộ nhớ:

```java
Specification<Order> reportableOrder =
        new OrderHasRecordedPayment()
                .and(new OrderIsNotCancelled())
                .and(new OrderMeetsMinimumAmount(minimumAmount));

List<Order> selected = orders.stream()
        .filter(reportableOrder::isSatisfiedBy)
        .toList();
```

Đây là cách dễ hiểu khi tập dữ liệu nhỏ và đã được nạp. Với dữ liệu lớn, không nên tải tất cả rồi lọc trong bộ nhớ.

### 13.1. Phân biệt Domain Specification và Query Specification

Một Specification kiểm tra domain object có thể chạy trong bộ nhớ. Một query specification có thể chuyển tiêu chí thành SQL, JPA Criteria hoặc truy vấn của kho dữ liệu. Hai mục tiêu liên quan nhưng không nhất thiết dùng cùng implementation.

Ví dụ:

- Domain Specification: `OrderCanBeCancelled` kiểm tra điều kiện nghiệp vụ trên một Order đã nạp.
- Query Specification: `OrdersWaitingForPayment` tạo truy vấn để tìm các đơn đang chờ thanh toán.

Không nên đưa `CriteriaBuilder`, `EntityManager` hoặc SQL vào domain model chỉ để tái sử dụng một interface. Có thể dùng chung ý nghĩa và tên tiêu chí, nhưng adapter truy vấn nên nằm ở application/infrastructure.

### 13.2. Không phải mọi Specification đều chuyển được sang SQL

Một điều kiện có thể gọi dịch vụ ngoài, dùng thuật toán phức tạp hoặc phụ thuộc vào dữ liệu chưa lưu trong database. Nó có thể phù hợp để kiểm tra trong bộ nhớ nhưng không thể dịch trực tiếp thành SQL.

Nếu cần hỗ trợ cả hai cách đánh giá, hãy định nghĩa phần tiêu chí có thể biểu diễn trong truy vấn và phần cần đánh giá sau khi nạp dữ liệu. Đừng giả định rằng mọi cây biểu thức Java đều có thể tự động chuyển thành truy vấn hiệu quả.

## 14. Empty Specification và ý nghĩa của tập điều kiện rỗng

Khi kết hợp một danh sách Specification động, trường hợp danh sách rỗng cần có ngữ nghĩa rõ.

Trong toán học:

- AND của tập rỗng thường được xem là `true` (đúng một cách hiển nhiên).
- OR của tập rỗng thường được xem là `false`.

Điều này phù hợp với một số trường hợp:

- Không có điều kiện bắt buộc nào bổ sung thì không loại đối tượng chỉ vì danh sách rỗng.
- Không có nhánh thay thế nào thì không có con đường nào thỏa.

Nhưng trong nghiệp vụ, danh sách rỗng có thể là lỗi cấu hình hoặc thiếu chính sách. Ví dụ, một chương trình khuyến mãi không có nhóm khách hàng được phép có thể cần bị vô hiệu hóa thay vì mặc định cho tất cả hoặc không ai. Hãy quyết định rõ ở cấp policy/configuration thay vì dựa ngầm vào identity của phép toán.

Nếu cài đặt `allOf` và `anyOf`, nên ghi rõ hành vi với danh sách rỗng trong tài liệu và test.

## 15. Kiểm thử Specification đơn lẻ và tổ hợp

Kiểm thử cần xác nhận cả từng tiêu chí thành phần lẫn ý nghĩa của biểu thức tổng hợp.

### 15.1. Kiểm thử từng Specification

Với mỗi tiêu chí, tạo ít nhất:

- Một đối tượng thỏa mãn.
- Một đối tượng không thỏa mãn.
- Giá trị biên nếu có ngưỡng.
- Trường hợp thiếu dữ liệu hoặc trạng thái chưa xác định.

Ví dụ, `OrderMeetsMinimumAmount` cần kiểm tra giá trị thấp hơn ngưỡng, bằng ngưỡng và cao hơn ngưỡng. Cần xác nhận “tối thiểu 500.000” có bao gồm đúng 500.000 hay không.

### 15.2. Kiểm thử bảng chân trị

Với hai đặc tả A và B, kiểm tra đủ bốn tổ hợp true/false để bảo đảm AND và OR đúng. Kiểm tra NOT đảo kết quả theo logic đã chọn.

```java
@Test
void andRequiresBothSpecifications() {
    Specification<String> a = value -> value.contains("A");
    Specification<String> b = value -> value.contains("B");

    Specification<String> both = a.and(b);

    assertTrue(both.isSatisfiedBy("AB"));
    assertFalse(both.isSatisfiedBy("A"));
    assertFalse(both.isSatisfiedBy("B"));
    assertFalse(both.isSatisfiedBy("C"));
}

@Test
void orRequiresAtLeastOneSpecification() {
    Specification<String> a = value -> value.contains("A");
    Specification<String> b = value -> value.contains("B");

    Specification<String> either = a.or(b);

    assertTrue(either.isSatisfiedBy("A"));
    assertTrue(either.isSatisfiedBy("B"));
    assertTrue(either.isSatisfiedBy("AB"));
    assertFalse(either.isSatisfiedBy("C"));
}

@Test
void notInvertsTheSpecificationResult() {
    Specification<String> containsA = value -> value.contains("A");

    assertFalse(containsA.not().isSatisfiedBy("A"));
    assertTrue(containsA.not().isSatisfiedBy("B"));
}
```

### 15.3. Kiểm thử chính sách tổng hợp bằng ví dụ nghiệp vụ

Không chỉ kiểm tra toán tử. Hãy tạo các ví dụ mà chuyên gia nghiệp vụ có thể đọc:

| Khách hàng | Giá trị đơn | Bị loại trừ | Kết quả kỳ vọng |
|---|---:|---|---|
| Gold | 600.000 | Không | Đủ điều kiện |
| Employee | 600.000 | Không | Đủ điều kiện |
| Regular | 600.000 | Không | Không đủ điều kiện |
| Gold | 400.000 | Không | Không đủ điều kiện |
| Employee | 600.000 | Có | Không đủ điều kiện |

Ví dụ này kiểm tra biểu thức `(Gold OR Employee) AND MinimumAmount AND NOT Excluded`. Nếu chuyên gia không đồng ý một dòng, cần sửa định nghĩa chính sách trước khi sửa code.

### 15.4. Kiểm thử short-circuit và tính thuần

Nếu Specification có nguy cơ gọi logic đắt tiền, có thể kiểm tra rằng AND không gọi vế phải khi vế trái false và OR không gọi vế phải khi vế trái true. Tuy nhiên, không nên viết kiểm thử để khuyến khích side effect trong predicate. Tốt hơn là giữ Specification thuần và đo hiệu năng bằng benchmark phù hợp khi cần.

## 16. Tối ưu thứ tự đánh giá

Với AND, đặt điều kiện rẻ và thường loại được nhiều ứng viên ở trước có thể giảm số lần đánh giá các điều kiện sau. Với OR, đặt điều kiện rẻ và thường đúng ở trước có thể giúp short-circuit sớm.

Ví dụ:

```java
Specification<Order> eligible =
        new OrderIsNotCancelled()       // kiểm tra trạng thái trong bộ nhớ
                .and(new OrderHasValidPayment())
                .and(new OrderHasCreditApproval());
```

Nếu kiểm tra credit approval đắt hơn, có thể đánh giá trạng thái đơn trước. Nhưng tối ưu thứ tự chỉ nên thực hiện khi:

- Các Specification thuần, không có side effect.
- Kết quả của chúng không thay đổi trong cùng lần đánh giá.
- Việc đổi thứ tự không làm mất thông tin lỗi cần trả cho người dùng.
- Đã có bằng chứng hiệu năng cho thấy thứ tự hiện tại là vấn đề.

Nếu một tiêu chí cần gọi hệ thống ngoài hoặc truy vấn dữ liệu, hãy cân nhắc tải dữ liệu trước và truyền vào một candidate đầy đủ. Không nên để Specification tự thực hiện nhiều lời gọi mạng trong lúc đánh giá.

## 17. Specification, Policy và Validation có vai trò khác nhau

Các thuật ngữ này thường bị dùng thay thế nhau, nhưng nên phân biệt trách nhiệm:

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Specification | Đối tượng có thỏa một tiêu chí không? | Đơn có đủ điều kiện hủy không? |
| Policy | Khi một điều kiện hoặc sự kiện xảy ra, nên quyết định/hành động gì? | Khi thanh toán được ghi nhận, xác nhận đơn nếu đơn còn hiệu lực |
| Validation | Dữ liệu hoặc yêu cầu có hợp lệ theo cấu trúc và quy tắc không? | Số lượng phải lớn hơn 0; email đúng định dạng |
| Authorization | Chủ thể có quyền thực hiện hành động không? | Nhân viên có quyền hoàn tiền đơn này không? |
| Invariant | Điều kiện nào phải luôn được bảo vệ trong ranh giới nhất quán? | Tổng lượng giữ không vượt tồn khả dụng |

Một Policy có thể sử dụng nhiều Specification bằng AND/OR/NOT để đưa ra quyết định. Nhưng Specification không nhất thiết phải thực hiện hành động, còn Policy có thể điều phối quyết định và kết quả tiếp theo.

Ví dụ, `OrderCanBeCancelled` có thể là Specification. `CancellationPolicy` có thể dùng đặc tả này để quyết định có chấp nhận yêu cầu, tính phí hủy hoặc chuyển sang quy trình phê duyệt. Aggregate Root vẫn phải bảo vệ invariant khi trạng thái thực sự thay đổi.

## 18. Các lỗi thường gặp khi kết hợp AND, OR, NOT

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Thiếu dấu ngoặc hoặc nhóm điều kiện | Nhánh OR có thể bỏ qua điều kiện bắt buộc | Dùng biến trung gian và diễn đạt lại chính sách bằng lời |
| Dùng OR nhưng tưởng chỉ một nhánh được chọn | Không xử lý trường hợp nhiều nhánh cùng đúng | Tách điều kiện đủ tư cách khỏi quy tắc ưu tiên/cộng dồn |
| Dùng NOT trên dữ liệu chưa biết | Trường hợp chưa xác minh có thể bị chấp nhận | Phân biệt false với unknown và xác định fail-closed khi cần |
| Kết hợp Specification khác kiểu ứng viên | Ép kiểu hoặc trộn trách nhiệm | Dùng policy hoặc candidate object chung |
| Specification có side effect | Short-circuit hoặc đánh giá lặp gây hành động khó đoán | Giữ predicate thuần, chuyển side effect sang application/policy handler |
| Dùng một biểu thức boolean quá dài | Khó review và khó xác định quy tắc nào sai | Tách thành các Specification có tên |
| Dùng domain Specification trực tiếp cho SQL | Domain phụ thuộc persistence và ngữ nghĩa có thể lệch | Tách query specification/adapter phù hợp |
| Bỏ qua SQL NULL semantics | Kết quả query khác với kiểm tra Java | Định nghĩa null rõ và kiểm thử truy vấn |
| Không xác định semantics của danh sách rỗng | Chính sách có thể mặc định quá rộng hoặc quá hẹp | Quy định rõ `allOf`/`anyOf` khi không có phần tử |
| Tối ưu thứ tự trước khi đo | Tăng độ phức tạp mà không có lợi ích | Đo workload và chỉ tối ưu điều kiện thuần |

## 19. Quy trình xây dựng một chính sách từ Specification

Một quy trình thực tế có thể gồm:

1. **Mô tả quyết định bằng ngôn ngữ nghiệp vụ:** viết câu mà chuyên gia có thể xác nhận.
2. **Tách các tiêu chí nguyên tử:** xác định điều kiện bắt buộc, điều kiện thay thế và điều kiện loại trừ.
3. **Xác định kiểu ứng viên:** một Aggregate, một entity hay một candidate gồm nhiều đối tượng.
4. **Làm rõ dữ liệu chưa biết:** null, pending, unavailable và trạng thái không thể xác minh.
5. **Chọn phép kết hợp:** dùng AND, OR, NOT với dấu ngoặc thể hiện đúng ngữ nghĩa.
6. **Đặt tên:** chọn tên Specification phản ánh ý nghĩa nghiệp vụ, không chỉ tên field kỹ thuật.
7. **Kiểm thử riêng và tổng hợp:** dùng bảng chân trị, ví dụ, phản ví dụ và giá trị biên.
8. **Đặt đúng nơi sử dụng:** domain model, policy, application hoặc query adapter tùy trách nhiệm.
9. **Review với chuyên gia:** xác nhận từng nhánh và trường hợp nhiều điều kiện cùng đúng.
10. **Theo dõi thay đổi:** cập nhật ví dụ và kiểm thử khi chính sách thay đổi.

## 20. Checklist trước khi đưa Specification tổng hợp vào sử dụng

- [ ] Mỗi Specification thành phần có tên và định nghĩa rõ.
- [ ] Các Specification được kết hợp có cùng kiểu ứng viên hoặc có policy phối hợp phù hợp.
- [ ] AND thể hiện đúng các điều kiện bắt buộc.
- [ ] OR thể hiện đúng các con đường thay thế.
- [ ] NOT không vô tình chấp nhận dữ liệu chưa xác định.
- [ ] Dấu ngoặc và thứ tự nhóm điều kiện được thể hiện rõ.
- [ ] Trường hợp nhiều nhánh OR cùng đúng đã được xử lý ở cấp policy nếu cần.
- [ ] Specification không có side effect và không gọi hệ thống ngoài tùy tiện.
- [ ] Semantics của null và unknown đã được xác định.
- [ ] Domain evaluation và database query không bị nhầm lẫn.
- [ ] Empty specification/list có hành vi được định nghĩa.
- [ ] Có test cho từng điều kiện, tổ hợp, giá trị biên và trường hợp chưa biết.
- [ ] Quyết định cuối cùng vẫn được Aggregate Root bảo vệ nếu nó thay đổi invariant.
- [ ] Chuyên gia nghiệp vụ đã xác nhận ví dụ và kết quả mong đợi.

## 21. Kết nối với các khái niệm DDD khác

Specification giúp diễn đạt tiêu chí nghiệp vụ có thể được tái sử dụng và kết hợp. Entity hoặc Aggregate cung cấp đối tượng ứng viên; Value Object có thể cung cấp các giá trị đã được kiểm tra; Policy dùng một hoặc nhiều Specification để đưa ra quyết định; Application Service điều phối use case và gọi hành vi miền.

Trong một số trường hợp, Specification hỗ trợ truy vấn Repository để tìm đối tượng phù hợp. Khi tiêu chí cần chạy trong database, cần một query adapter hoặc query specification có thể chuyển thành truy vấn hiệu quả. Domain Specification không nên phụ thuộc vào ORM chỉ để phục vụ tìm kiếm.

AND, OR và NOT là công cụ biểu đạt logic, không thay thế việc hiểu chính sách. Trước khi kết hợp, nhóm cần biết điều kiện nào bắt buộc, điều kiện nào là lựa chọn thay thế, điều gì bị loại trừ và cách xử lý dữ liệu chưa xác định. Khi ngữ nghĩa đã rõ, các Specification nhỏ có thể kết hợp thành chính sách dễ đọc, dễ kiểm thử và phù hợp với ngôn ngữ chung của miền nghiệp vụ.
