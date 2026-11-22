# Assertions cho giá trị, tập hợp và ngoại lệ

Trong JUnit Jupiter, assertion là những lời khẳng định giúp test xác nhận kết quả thực tế đáp ứng điều mong đợi. Một test có thể chạy hết mà không có assertion nào, nhưng khi đó nó chưa chứng minh được hành vi cần kiểm tra. Chọn đúng assertion giúp test thể hiện rõ hợp đồng của mã nguồn, phát hiện lỗi ở đúng điểm và cung cấp thông tin đủ tốt để tìm nguyên nhân khi thất bại.

JUnit Jupiter cung cấp các phương thức trong lớp org.junit.jupiter.api.Assertions. Các phương thức thường gặp gồm assertEquals cho giá trị, assertArrayEquals và assertIterableEquals cho dữ liệu dạng mảng hoặc iterable, assertAll để nhóm nhiều điều kiện, assertThrows để xác nhận ngoại lệ và assertDoesNotThrow để xác nhận một thao tác hoàn tất bình thường. Các assertion này có thể dùng trong unit test thuần Java lẫn test chạy cùng Spring TestContext.

## 1. Cấu trúc một test có assertion rõ ràng

Một test thường có ba phần:

1. **Arrange:** chuẩn bị đối tượng, dữ liệu đầu vào và trạng thái ban đầu.
2. **Act:** gọi đúng hành vi đang kiểm tra.
3. **Assert:** so sánh kết quả thực tế với điều mong đợi.

Ví dụ, một bộ chuyển đổi trạng thái đơn hàng:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}

public class OrderStatusPolicy {
    public OrderStatus afterPayment(OrderStatus current) {
        if (current != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "Only a new order can be paid");
        }
        return OrderStatus.PAID;
    }
}
~~~

Test thể hiện ba phần tách biệt:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class OrderStatusPolicyTest {
    @Test
    void changesANewOrderToPaid() {
        // Arrange
        OrderStatusPolicy policy = new OrderStatusPolicy();

        // Act
        OrderStatus result = policy.afterPayment(OrderStatus.NEW);

        // Assert
        assertEquals(OrderStatus.PAID, result);
    }
}
~~~

Với các assertion có dạng expected và actual, hãy truyền giá trị mong đợi trước, giá trị thực tế sau. Quy ước này làm thông điệp lỗi của JUnit dễ đọc: test đang mong đợi gì và chương trình thực tế trả về gì. Một assertion nên kiểm tra điều có ý nghĩa với hành vi công khai, tránh kiểm tra chi tiết triển khai không thuộc hợp đồng của lớp.

Tên test cũng nên nói rõ điều kiện và kết quả, chẳng hạn changesANewOrderToPaid hoặc rejectsPaymentForAnAlreadyPaidOrder. Khi test thất bại, người đọc có thể xác định mục tiêu của nó trước khi xem thân test.

## 2. Kiểm tra giá trị đơn và trạng thái đối tượng

### So sánh bằng equals

assertEquals(expected, actual) kiểm tra hai giá trị bằng nhau theo ngữ nghĩa equals của kiểu dữ liệu. Nó phù hợp với chuỗi, số nguyên, enum, record, value object và các đối tượng miền có triển khai equals đúng.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

Các import tĩnh thường được viết riêng trong test thực tế; ví dụ kiểm tra giá trị có thể như sau:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class CustomerTest {
    @Test
    void createsCustomerWithTheRequestedIdentity() {
        Customer customer = new Customer("C-100", "Lan");

        assertNotNull(customer);
        assertEquals("C-100", customer.id());
        assertEquals("Lan", customer.name());
    }
}

record Customer(String id, String name) {
}
~~~

record tự sinh equals và hashCode dựa trên các component. Vì vậy hai Customer có cùng id và name được xem là bằng nhau theo giá trị, dù là hai instance riêng biệt.

Nếu kiểu đối tượng không triển khai equals theo nội dung mong muốn, assertEquals có thể không kiểm tra điều bạn định kiểm tra. Khi đó hãy kiểm tra các thuộc tính công khai hoặc triển khai equals theo đúng ngữ nghĩa miền nếu kiểu đó thực sự là value object.

### Phân biệt bằng nhau và cùng một instance

assertEquals kiểm tra giá trị; assertSame kiểm tra hai tham chiếu trỏ đến đúng cùng một instance. assertNotSame xác nhận hai tham chiếu không cùng instance.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;

class IdentityAssertionTest {
    @Test
    void distinguishesValueEqualityFromObjectIdentity() {
        Customer first = new Customer("C-100", "Lan");
        Customer second = new Customer("C-100", "Lan");

        assertEquals(first, second);
        assertNotSame(first, second);
        assertSame(first, first);
    }
}
~~~

Trong hầu hết test nghiệp vụ, giá trị mới là điều cần xác nhận. assertSame hữu ích khi identity là một phần của hợp đồng, ví dụ cache phải trả lại đúng instance đã lưu hoặc một factory có chủ đích dùng singleton. Không nên dùng assertSame chỉ vì hai đối tượng tình cờ được giữ trong cùng một biến.

### Kiểm tra null và boolean

JUnit cung cấp assertNull, assertNotNull, assertTrue và assertFalse:

~~~java
assertNull(result);
assertNotNull(customer);
assertTrue(account.isActive());
assertFalse(account.isLocked());
~~~

Hãy dùng assertion mô tả trực tiếp điều kiện. Ví dụ assertNotNull(customer) cho biết rõ test mong đợi một đối tượng tồn tại hơn là assertTrue(customer != null). Khi kiểm tra một giá trị boolean trả về, assertTrue hoặc assertFalse giúp thông điệp lỗi sát với ý định.

Nếu cần truy cập thuộc tính của một kết quả có thể null, hãy khẳng định sự tồn tại trước khi dereference. Nếu không, test có thể dừng bằng NullPointerException và che mất thông điệp assertion có ích:

~~~java
Customer customer = customerService.find("C-100");

assertNotNull(customer, "Customer should be found");
assertEquals("Lan", customer.name());
~~~

### Kiểm tra kiểu của kết quả

assertInstanceOf xác nhận một giá trị thuộc kiểu mong đợi và trả về giá trị đã được kiểm tra với kiểu tương ứng. Nó hữu ích khi API trả về một kiểu cha hoặc interface nhưng test cần kiểm tra implementation cụ thể là một phần của hợp đồng.

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ResultTypeTest {
    @Test
    void returnsTheExpectedResultVariant() {
        Object result = "completed";

        String value = assertInstanceOf(String.class, result);

        assertEquals("completed", value);
    }
}
~~~

Không nên kiểm tra implementation cụ thể nếu người dùng API chỉ được cam kết nhận một interface hoặc kiểu cha. Trong trường hợp đó, kiểm tra hành vi qua hợp đồng chung sẽ giúp test bền vững hơn khi implementation thay đổi.

## 3. So sánh số và giá trị có độ chính xác

### Số nguyên và kiểu số chính xác

Với số nguyên, long và các kiểu số có ngữ nghĩa equals ổn định, có thể dùng assertEquals trực tiếp:

~~~java
assertEquals(3, cart.itemCount());
assertEquals(125L, invoice.totalInCents());
~~~

Với BigDecimal, cần hiểu rằng equals xét cả giá trị lẫn scale. Vì vậy new BigDecimal("10.0") không equals new BigDecimal("10.00"), dù compareTo cho kết quả bằng 0. Nếu quy tắc nghiệp vụ chỉ quan tâm giá trị số, hãy biểu đạt điều đó:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MoneyCalculationTest {
    @Test
    void comparesDecimalAmountsByNumericValue() {
        BigDecimal expected = new BigDecimal("10.00");
        BigDecimal actual = new BigDecimal("10.0");

        assertEquals(0, expected.compareTo(actual));
    }
}
~~~

Trong ví dụ này, assertEquals(0, compareTo(...)) đã đủ; không cần giữ thêm assertTrue cho cùng một điều kiện. Khi viết test thật, chọn một cách diễn đạt để tránh kiểm tra trùng lặp. Nếu scale là một phần của hợp đồng lưu trữ hoặc định dạng, assertEquals trên BigDecimal sẽ phù hợp hơn.

### Số thực và delta

Kết quả phép tính float hoặc double có thể có sai số biểu diễn nhị phân. Vì vậy, so sánh bằng tuyệt đối với assertEquals(expected, actual) thường không thích hợp cho kết quả tính toán số thực. Hãy dùng overload có delta:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GeometryTest {
    @Test
    void calculatesTheDiagonal() {
        double diagonal = Math.sqrt(2.0);

        assertEquals(1.41421356, diagonal, 0.00000001);
    }
}
~~~

Delta là sai số tối đa được chấp nhận giữa giá trị mong đợi và thực tế. Hãy chọn delta theo độ chính xác mà nghiệp vụ cần, đơn vị đo và quy mô dữ liệu. Delta quá lớn có thể khiến lỗi thật vẫn được chấp nhận; delta quá nhỏ có thể làm test thất bại do sai số không đáng kể.

Không nên sao chép một delta tùy ý cho mọi phép tính. Ví dụ, sai số 0.01 có thể hợp lý cho một phép đo gần đơn vị, nhưng không phù hợp với một phép tính tỷ lệ hoặc một đại lượng rất nhỏ. Với tiền tệ, thường nên dùng BigDecimal và quy tắc làm tròn được xác định rõ thay vì dựa vào double.

## 4. Kiểm tra mảng và tập hợp

Các dữ liệu dạng tập hợp có nhiều khía cạnh: số lượng phần tử, giá trị, thứ tự, quan hệ chứa phần tử và ánh xạ khóa-giá trị. Chọn assertion theo đúng khía cạnh cần kiểm tra.

### Mảng với assertArrayEquals

assertArrayEquals so sánh các phần tử của mảng theo thứ tự. Nó phù hợp với mảng primitive và mảng object:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import org.junit.jupiter.api.Test;

class CsvParserTest {
    @Test
    void splitsColumnsInTheirOriginalOrder() {
        String[] columns = {"id", "name", "status"};

        assertArrayEquals(
                new String[] {"id", "name", "status"},
                columns);
    }

    @Test
    void calculatesMonthlyTotals() {
        int[] totals = {10, 20, 30};

        assertArrayEquals(new int[] {10, 20, 30}, totals);
    }
}
~~~

Với mảng object, phép so sánh phần tử sử dụng ngữ nghĩa bằng nhau của phần tử; với mảng lồng nhau, JUnit hỗ trợ so sánh cấu trúc mảng nhiều chiều. Nếu thứ tự không thuộc hợp đồng, hãy chuyển dữ liệu sang kiểu tập hợp phù hợp và so sánh theo ngữ nghĩa của kiểu đó thay vì dùng assertArrayEquals.

### Iterable với assertIterableEquals

assertIterableEquals so sánh hai đối tượng Iterable theo các phần tử được duyệt và thứ tự duyệt. Hai đối tượng có thể có kiểu triển khai khác nhau, chẳng hạn List và một Iterable khác, nhưng vẫn bằng nhau nếu chuỗi phần tử tương ứng giống nhau.

~~~java
import static org.junit.jupiter.api.Assertions.assertIterableEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SearchResultTest {
    @Test
    void returnsMatchingIdsInTheRequestedOrder() {
        Iterable<String> actual =
                new ArrayList<>(List.of("P-10", "P-20", "P-30"));

        assertIterableEquals(
                List.of("P-10", "P-20", "P-30"),
                actual);
    }
}
~~~

Thứ tự là một phần của phép so sánh. Nếu actual chứa đúng các phần tử nhưng theo thứ tự khác, assertion sẽ thất bại. Điều này phù hợp với kết quả tìm kiếm có thứ tự ưu tiên, danh sách bước xử lý hoặc dữ liệu được sắp xếp.

Hãy cẩn thận với Iterable chỉ duyệt được một lần hoặc được tạo từ Stream. Một Stream là nguồn dữ liệu tiêu thụ một lần; đừng dùng nó trong nhiều assertion như thể nó là một collection có thể duyệt lại. Nếu cần kiểm tra nhiều khía cạnh, thu thập kết quả thành List một lần rồi thực hiện assertion trên List đó.

### List, Set và Map

Với collection tiêu chuẩn, assertEquals thường đã đủ vì List, Set và Map có quy tắc equals riêng:

- List so sánh số lượng, phần tử và thứ tự.
- Set so sánh các phần tử theo ngữ nghĩa tập hợp, không phụ thuộc thứ tự duyệt.
- Map so sánh các ánh xạ khóa-giá trị, không phụ thuộc thứ tự duyệt.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class CollectionEqualityTest {
    @Test
    void comparesListIncludingItsOrder() {
        List<String> actual = List.of("A", "B", "C");

        assertEquals(List.of("A", "B", "C"), actual);
    }

    @Test
    void comparesSetWithoutDependingOnIterationOrder() {
        Set<String> actual = Set.of("A", "B", "C");

        assertEquals(Set.of("C", "A", "B"), actual);
    }

    @Test
    void comparesMapByKeyValueMappings() {
        Map<String, Integer> actual =
                Map.of("new", 2, "paid", 5);

        assertEquals(
                Map.of("paid", 5, "new", 2),
                actual);
    }
}
~~~

Không nên chuyển mọi collection thành Set chỉ để test dễ hơn. Nếu thứ tự có ý nghĩa nghiệp vụ, việc bỏ thứ tự có thể che lỗi sắp xếp. Ngược lại, nếu kết quả được định nghĩa là một tập hợp không có thứ tự, hãy so sánh bằng Set để test không phụ thuộc thứ tự triển khai.

### Kiểm tra phần tử bắt buộc có mặt

Đôi khi test chỉ cần xác nhận một collection có chứa phần tử cụ thể:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

assertTrue(actual.contains("ADMIN"));
~~~

Nếu cần xác nhận nhiều phần tử bắt buộc đều có mặt, có thể dùng containsAll:

~~~java
assertTrue(actual.containsAll(Set.of("READ", "WRITE")));
~~~

Các kiểm tra contains chỉ xác nhận sự hiện diện, không đảm bảo collection không có phần tử dư. Nếu hợp đồng yêu cầu tập hợp phải khớp hoàn toàn, hãy dùng assertEquals với Set mong đợi. Nếu cần phát hiện phần tử thiếu và dư một cách rõ ràng, so sánh hai tập hợp đầy đủ thường cho kết quả dễ hiểu hơn nhiều assertion contains riêng lẻ.

JUnit Jupiter không định nghĩa một assertion cốt lõi riêng cho mọi thư viện collection hoặc mọi câu hỏi kiểu contains/hasSize. Có thể kết hợp assertion chuẩn với API collection của Java. Nếu dự án đã dùng thư viện assertion như AssertJ, có thể dùng API của thư viện đó theo quy ước dự án; cần phân biệt chúng với Assertions của JUnit Jupiter.

### Kiểm tra Map theo khóa và giá trị

Nếu test cần tập trung vào một ánh xạ cụ thể, hãy kiểm tra khóa và giá trị theo mục đích:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;

Map<String, Integer> quantities = Map.of("book", 2, "pen", 5);

assertTrue(quantities.containsKey("book"));
assertEquals(2, quantities.get("book"));
~~~

Khi khóa có thể không tồn tại, get trả về null nếu không có ánh xạ và cũng có thể trả về null nếu Map cho phép ánh xạ null. Nếu phân biệt hai trường hợp là quan trọng, hãy kiểm tra containsKey trước khi kiểm tra giá trị.

## 5. Gom nhiều điều kiện với assertAll

assertAll nhận nhiều Executable và chạy tất cả các assertion trong nhóm, sau đó báo lỗi tổng hợp nếu một hoặc nhiều assertion thất bại. Nó hữu ích khi các điều kiện độc lập cùng mô tả một kết quả.

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class CustomerProfileTest {
    @Test
    void returnsTheExpectedProfile() {
        Customer customer =
                new Customer("C-100", "Lan");

        assertAll("customer profile",
                () -> assertNotNull(customer),
                () -> assertEquals("C-100", customer.id()),
                () -> assertEquals("Lan", customer.name()));
    }
}

record Customer(String id, String name) {
}
~~~

Nếu một assertion trong assertAll thất bại, các assertion độc lập còn lại vẫn được chạy. JUnit thu thập các lỗi và báo chúng cùng nhau bằng lỗi tổng hợp. Điều này giúp người đọc thấy nhiều thuộc tính sai trong một lần chạy test thay vì phải sửa từng lỗi rồi chạy lại.

Chỉ nhóm những điều kiện thực sự độc lập. Nếu điều kiện sau cần kết quả hợp lệ của điều kiện trước, hãy tách ra để tránh lỗi dây chuyền hoặc NullPointerException che khuất nguyên nhân:

~~~java
Customer customer = customerService.find("C-100");
assertNotNull(customer);

assertAll("customer fields",
        () -> assertEquals("C-100", customer.id()),
        () -> assertEquals("Lan", customer.name()));
~~~

Ở đây assertNotNull đứng ngoài vì những assertion bên trong cần truy cập customer. Nếu customer null, test dừng với thông điệp trực tiếp. Các thuộc tính độc lập sau đó được gom lại.

assertAll cũng có overload nhận một Stream hoặc Collection các Executable. Dùng overload đó khi các điều kiện được tạo từ dữ liệu lặp, nhưng tránh tạo một nhóm quá lớn đến mức khó xác định assertion nào tương ứng với phần tử nào. Có thể thêm heading hoặc thông điệp theo từng mục để kết quả dễ đọc.

## 6. Viết thông điệp lỗi hữu ích

Nhiều assertion có overload nhận thông điệp. Thông điệp này được hiển thị khi assertion thất bại và nên giải thích ý nghĩa nghiệp vụ của điều kiện:

~~~java
assertEquals(
        OrderStatus.PAID,
        actualStatus,
        "A successful payment should mark the order as PAID");
~~~

JUnit cũng hỗ trợ Supplier<String> để chỉ tạo thông điệp khi assertion thất bại:

~~~java
assertEquals(
        expectedTotal,
        actualTotal,
        () -> "Unexpected total for order " + orderId);
~~~

Supplier hữu ích khi xây dựng thông điệp tốn chi phí hoặc cần chuyển đổi dữ liệu. Không cần dùng nó cho mọi assertion đơn giản; một chuỗi trực tiếp dễ đọc hơn khi không có công việc đáng kể để tạo thông điệp.

Tránh thông điệp chung chung như "test failed" hoặc lặp lại nguyên văn assertion. Một thông điệp tốt bổ sung ngữ cảnh mà expected và actual chưa thể hiện, chẳng hạn mã đơn hàng, loại tiền hoặc điều kiện nghiệp vụ đang được xác nhận.

## 7. Xác nhận ngoại lệ với assertThrows

Ngoại lệ thường là một phần của hợp đồng khi đầu vào không hợp lệ, tài nguyên không tồn tại hoặc một thao tác không được phép ở trạng thái hiện tại. assertThrows xác nhận một đoạn mã ném ra ngoại lệ thuộc kiểu mong đợi và trả về chính đối tượng ngoại lệ để test kiểm tra thêm.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderStatusPolicyExceptionTest {
    @Test
    void rejectsPaymentForAnAlreadyPaidOrder() {
        OrderStatusPolicy policy = new OrderStatusPolicy();

        IllegalStateException exception = assertThrows(
                IllegalStateException.class,
                () -> policy.afterPayment(OrderStatus.PAID));

        assertEquals(
                "Only a new order can be paid",
                exception.getMessage());
    }
}
~~~

assertThrows chấp nhận ngoại lệ có kiểu đúng hoặc kiểu con của kiểu mong đợi. Ví dụ, nếu test truyền RuntimeException.class, một IllegalStateException cũng làm assertion thành công vì IllegalStateException kế thừa RuntimeException. Do đó hãy chọn kiểu ngoại lệ cụ thể nhất mà hợp đồng công khai cam kết.

Không nên bắt một kiểu quá rộng như Exception hoặc Throwable nếu hành vi cần kiểm tra là IllegalArgumentException. Một lỗi lập trình bất ngờ cũng có thể làm test vượt qua khi kiểu mong đợi quá rộng. Kiểu ngoại lệ cụ thể khiến test phát hiện được khi mã nguồn thay đổi sang ném một loại lỗi khác.

### Chỉ đặt hành động cần kiểm tra bên trong lambda

Đối số thứ hai của assertThrows là một Executable, vì vậy đoạn mã có thể ném ngoại lệ phải nằm trong lambda:

~~~java
IllegalArgumentException exception = assertThrows(
        IllegalArgumentException.class,
        () -> pricePolicy.calculate(null));
~~~

Không gọi phương thức trước khi truyền kết quả vào assertThrows:

~~~java
// Sai: lời gọi có thể ném ngoại lệ trước khi assertThrows được thực thi.
// assertThrows(IllegalArgumentException.class, pricePolicy.calculate(null));
~~~

Giữ lambda ngắn và chỉ chứa thao tác dự kiến phát sinh lỗi. Nếu đặt nhiều hành động không liên quan trong cùng lambda, test có thể thành công vì một hành động khác ném ngoại lệ, dù hành vi chính không ném lỗi như mong đợi.

Ví dụ, khi xác nhận thao tác cập nhật từ chối một giá trị không hợp lệ, hãy chuẩn bị đối tượng ở ngoài lambda và chỉ gọi update trong lambda. Điều đó làm rõ chính xác ranh giới phát sinh ngoại lệ.

### Kiểm tra thông điệp và nguyên nhân

Sau khi assertThrows trả về ngoại lệ, có thể kiểm tra message, cause hoặc các thuộc tính miền mà ngoại lệ cung cấp:

~~~java
import java.math.BigDecimal;

IllegalArgumentException exception = assertThrows(
        IllegalArgumentException.class,
        () -> discountPolicy.apply(new BigDecimal("-5")));

assertEquals("Discount cannot be negative", exception.getMessage());
~~~

Chỉ kiểm tra thông điệp khi thông điệp là một phần của hợp đồng mà người gọi hoặc người vận hành dựa vào. Nếu thông điệp chỉ là chi tiết nội bộ, việc so sánh toàn bộ chuỗi có thể làm test dễ vỡ khi nội dung được chỉnh sửa để dễ hiểu hơn. Khi phù hợp, hãy kiểm tra kiểu ngoại lệ, mã lỗi ổn định hoặc thuộc tính có cấu trúc thay cho toàn bộ câu chữ.

Nếu ngoại lệ bọc một nguyên nhân khác, có thể kiểm tra cause:

~~~java
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

RuntimeException exception = assertThrows(
        RuntimeException.class,
        () -> service.performOperation());

assertInstanceOf(IllegalStateException.class, exception.getCause());
~~~

Hãy kiểm tra cause khi việc giữ nguyên nguyên nhân là hành vi được yêu cầu, chẳng hạn một adapter chuyển ngoại lệ kỹ thuật thành ngoại lệ ứng dụng nhưng vẫn giữ cause để chẩn đoán. Không nên phụ thuộc vào cấu trúc chuỗi nguyên nhân sâu nếu nó không thuộc hợp đồng.

### Phân biệt assertThrows và assertDoesNotThrow

assertDoesNotThrow xác nhận một đoạn mã hoàn tất mà không ném ngoại lệ. Với biểu thức trả về giá trị, nó trả lại giá trị đó để có thể tiếp tục kiểm tra:

~~~java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;

String normalized = assertDoesNotThrow(
        () -> usernamePolicy.normalize(" Lan "));

assertEquals("lan", normalized);
~~~

Nếu không cần giá trị trả về, có thể dùng với một thao tác void:

~~~java
assertDoesNotThrow(() -> service.refreshCache());
~~~

Thông thường, một test thành công mà không phát sinh ngoại lệ đã chứng minh thao tác hoàn tất. assertDoesNotThrow hữu ích khi test muốn thể hiện rõ rằng một đầu vào hợp lệ không được phép gây lỗi, hoặc khi cần lấy giá trị trả về từ Supplier. Không cần bọc mọi lời gọi phương thức trong assertDoesNotThrow vì điều đó có thể làm test dài hơn mà không tăng thông tin.

## 8. Kết hợp assertion trong test nghiệp vụ

Một ví dụ đầy đủ hơn cho thấy cách kết hợp kiểm tra giá trị, tập hợp và ngoại lệ trong cùng một lớp chính sách:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class AccessPolicy {
    public List<String> permissionsFor(String role) {
        return switch (role) {
            case "ADMIN" -> List.of("READ", "WRITE", "DELETE");
            case "EDITOR" -> List.of("READ", "WRITE");
            case "VIEWER" -> List.of("READ");
            default -> throw new IllegalArgumentException(
                    "Unknown role: " + role);
        };
    }
}

class AccessPolicyTest {
    private final AccessPolicy policy = new AccessPolicy();

    @Test
    void grantsTheExpectedPermissionsToAnEditor() {
        List<String> permissions = policy.permissionsFor("EDITOR");

        assertIterableEquals(
                List.of("READ", "WRITE"),
                permissions);
    }

    @Test
    void rejectsAnUnknownRole() {
        IllegalArgumentException exception = assertThrows(
                IllegalArgumentException.class,
                () -> policy.permissionsFor("GUEST"));

        assertEquals("Unknown role: GUEST", exception.getMessage());
    }
}
~~~

Test đầu tiên xác nhận cả giá trị lẫn thứ tự quyền mà một vai trò nhận được. Test thứ hai xác nhận kiểu ngoại lệ và thông điệp cho vai trò không được hỗ trợ. Mỗi test tập trung vào một hành vi riêng nên khi thất bại, nguyên nhân dễ xác định.

Nếu thứ tự quyền không có ý nghĩa trong hợp đồng, hãy trả về và so sánh một Set thay vì dùng List. Kiểu dữ liệu được chọn trong production code và assertion trong test nên cùng thể hiện đúng ngữ nghĩa của dữ liệu.

## 9. Những lỗi thường gặp khi viết assertion

### Đảo vị trí expected và actual

JUnit thường chấp nhận cả hai giá trị cùng kiểu nên việc đảo thứ tự không làm code biên dịch thất bại, nhưng thông điệp lỗi trở nên khó đọc. Giữ quy ước expected trước, actual sau:

~~~java
assertEquals(expectedName, actualName);
~~~

### Dùng assertEquals khi cần assertSame

Hai đối tượng có thể bằng nhau về giá trị nhưng không phải cùng một instance. Hãy xác định hợp đồng đang nói về nội dung hay identity trước khi chọn assertion.

### So sánh double không có delta

Kết quả phép tính số thực có thể lệch nhẹ do cách biểu diễn. Dùng delta phù hợp với độ chính xác nghiệp vụ và ưu tiên BigDecimal cho số thập phân tài chính cần quy tắc làm tròn rõ ràng.

### Bỏ qua thứ tự hoặc vô tình yêu cầu thứ tự

assertIterableEquals và assertArrayEquals quan tâm đến thứ tự. List cũng vậy. Set và Map tiêu chuẩn so sánh theo ngữ nghĩa không phụ thuộc thứ tự duyệt. Hãy chọn cấu trúc và assertion phù hợp với hợp đồng thay vì sắp xếp dữ liệu chỉ để làm test qua.

### Chỉ kiểm tra size

assertEquals(3, actual.size()) chỉ xác nhận số phần tử. Một collection có ba phần tử sai vẫn làm test thành công. Nếu hợp đồng yêu cầu giá trị cụ thể, hãy so sánh cả collection mong đợi hoặc kiểm tra các phần tử quan trọng.

### Đặt quá nhiều thao tác trong assertThrows

Lambda dài có thể bắt được ngoại lệ từ bước chuẩn bị hoặc một lời gọi phụ không phải đối tượng kiểm tra. Chuẩn bị trước, đặt duy nhất thao tác cần kiểm tra trong lambda và xác nhận ngoại lệ sau đó.

### Bắt ngoại lệ trong code test rồi bỏ qua

Một try/catch rỗng hoặc chỉ ghi log có thể khiến test tiếp tục như thể không có lỗi. Hãy dùng assertThrows khi ngoại lệ là kết quả mong đợi. Nếu ngoại lệ không được mong đợi, để nó làm test thất bại hoặc dùng assertDoesNotThrow khi cần diễn đạt rõ hợp đồng.

### Lặp lại assertion cho cùng một điều kiện

Kiểm tra một biểu thức bằng cả assertEquals và assertTrue không cung cấp thêm bằng chứng. Chọn assertion diễn đạt rõ nhất điều cần kiểm tra và dùng phần còn lại cho các điều kiện độc lập khác.

### Kiểm tra chi tiết triển khai quá mức

Test chỉ xác minh một phương thức private đã được gọi hoặc một trường nội bộ có giá trị cụ thể thường bị gắn chặt với cấu trúc lớp. Ưu tiên kiểm tra kết quả công khai, trạng thái miền hoặc tương tác thuộc hợp đồng với collaborator.

## 10. Tổ chức assertion trong dự án Spring

JUnit Jupiter assertions hoạt động độc lập với Spring. Một service có thể được tạo trực tiếp trong unit test và kiểm tra bằng Assertions mà không cần Spring context. Khi test cần kiểm tra bean wiring, transaction hoặc tích hợp Spring, vẫn dùng chính các assertion đó sau khi context được khởi tạo.

Ví dụ, với một service được inject vào test bằng Spring:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(GreetingServiceContextTest.TestConfiguration.class)
class GreetingServiceContextTest {
    @Autowired
    GreetingService greetingService;

    @Test
    void createsGreetingThroughTheConfiguredBean() {
        assertNotNull(greetingService);
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }

    @Configuration
    static class TestConfiguration {
        @Bean
        GreetingService greetingService() {
            return new GreetingService();
        }
    }
}

class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Trong ví dụ này, Spring chịu trách nhiệm tạo và inject GreetingService; JUnit Jupiter chịu trách nhiệm chạy test và đánh giá kết quả. Hai vai trò bổ sung cho nhau. Nếu chỉ cần xác nhận logic greet, có thể tạo GreetingService trực tiếp và không cần context.

Với test Spring MVC, repository hoặc transaction, hãy giữ assertion sát với điều cần xác nhận: status và body của response, dữ liệu đã lưu, trạng thái transaction hoặc ngoại lệ được chuyển đổi. Không nên chỉ xác nhận context khởi động thành công nếu mục tiêu của test là một hành vi nghiệp vụ cụ thể.

JUnit Jupiter cho phép import tĩnh các phương thức assertion để code ngắn và dễ đọc. Một số dự án cũng dùng AssertJ hoặc Hamcrest để có API diễn đạt phong phú hơn, ví dụ kiểm tra collection hoặc chuỗi. Những thư viện đó có thể cùng tồn tại với JUnit Jupiter, nhưng cần tuân theo quy ước thống nhất trong dự án. Không trộn nhiều phong cách assertion trong cùng một test nếu không có lý do rõ ràng.

## 11. Chọn assertion theo câu hỏi cần trả lời

| Câu hỏi của test | Assertion phù hợp | Điều cần chú ý |
|---|---|---|
| Hai giá trị có bằng nhau không? | assertEquals | Dựa trên equals của kiểu dữ liệu |
| Hai biến có cùng instance không? | assertSame / assertNotSame | Chỉ dùng khi identity thuộc hợp đồng |
| Kết quả có null không? | assertNull / assertNotNull | Kiểm tra trước khi truy cập thuộc tính |
| Điều kiện boolean đúng hay sai? | assertTrue / assertFalse | Viết điều kiện có ý nghĩa nghiệp vụ |
| Kết quả có thuộc kiểu mong đợi không? | assertInstanceOf | Tránh phụ thuộc implementation không công khai |
| Hai mảng có phần tử giống nhau theo thứ tự không? | assertArrayEquals | So sánh cả nội dung và vị trí |
| Hai Iterable có cùng chuỗi phần tử không? | assertIterableEquals | Thứ tự duyệt phải khớp |
| Nhiều thuộc tính độc lập đều đúng không? | assertAll | Các assertion trong nhóm vẫn được chạy khi một điều kiện thất bại |
| Thao tác phải ném ngoại lệ nào? | assertThrows | Chọn kiểu cụ thể và lambda ngắn |
| Thao tác hợp lệ phải hoàn tất bình thường? | assertDoesNotThrow | Dùng khi điều này là ý định cần diễn đạt |
| Hai số thực gần nhau trong sai số cho phép? | assertEquals với delta | Chọn delta theo yêu cầu nghiệp vụ |

Khi viết test, hãy bắt đầu từ câu hỏi cần trả lời rồi chọn assertion tương ứng. Assertion tốt giúp người đọc hiểu hợp đồng của phương thức, cho kết quả lỗi có ích và vẫn ổn định khi cấu trúc triển khai được refactor. Với JUnit Jupiter, các công cụ cơ bản đã đủ để kiểm tra giá trị, cấu trúc dữ liệu và ngoại lệ một cách rõ ràng; điều quan trọng là dùng chúng đúng ngữ nghĩa của dữ liệu và hành vi đang kiểm tra.
