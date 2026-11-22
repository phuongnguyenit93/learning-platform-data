# Kiểm thử record pattern với dữ liệu lồng nhau, generic và null

Record patterns trong Java 21 cho phép kiểm tra kiểu record và phân rã các component ngay trong một biểu thức `instanceof` hoặc nhánh `switch`. Khi dữ liệu có nhiều record lồng nhau hoặc record generic, pattern có thể kiểm tra cấu trúc ở từng tầng và bind component vào biến có kiểu phù hợp. Kiểm thử cần xác nhận cả trường hợp khớp hoàn toàn, sai kiểu ở tầng lồng nhau, giá trị `null` và hành vi fallback.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), Record Patterns đã là tính năng ổn định từ JEP 440 và Pattern Matching for `switch` ổn định từ JEP 441. Các ví dụ dưới đây dùng cú pháp Java 21, không cần bật preview. Bài học sử dụng JUnit Jupiter để minh họa cách tổ chức assertion; nguyên tắc kiểm thử vẫn áp dụng nếu dự án dùng framework khác.

## Mô hình dữ liệu dùng trong test

Giả sử một API trả về envelope generic chứa payload. Payload có thể là customer record, page record hoặc một kiểu dữ liệu khác:

```java
import java.util.List;

record Customer(String id, String name) {}

record Envelope<T>(T data, String requestId) {}

record Page<T>(List<T> items, int total) {}

record CustomerSummary(String id, String name, String requestId) {}
```

`Envelope<T>` và `Page<T>` là generic record. `Envelope<Customer>` chứa một record lồng nhau; `Envelope<Integer>` có cùng cấu trúc ngoài nhưng payload khác kiểu. Mô hình này cho phép kiểm tra pattern ở cả cấp outer record, component generic và nested record.

## Viết logic cần kiểm thử bằng record pattern

Hàm sau phân loại một object. Nó xử lý riêng envelope chứa customer, sau đó xử lý mọi envelope còn lại:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null-input";
        case Envelope<?>(Customer(var id, var name), var requestId) ->
                "customer:" + id + ":" + name + ":" + requestId;
        case Envelope<?>(var data, var requestId) ->
                data == null ? "empty-payload:" + requestId : "other-payload:" + requestId;
        default -> "unsupported";
    };
}
```

Nhánh đầu kiểm tra hai tầng: giá trị phải là `Envelope<?>`, và component `data` phải là `Customer`. Các component của `Customer` được bind vào `id` và `name`; `requestId` được lấy từ envelope ngoài.

Nhánh thứ hai xử lý mọi envelope khác, kể cả envelope có `data == null`, vì `var` pattern chấp nhận giá trị null. Nhánh `default` xử lý các object không phải envelope. `case null` phải đứng riêng vì `default` không khớp null.

Pattern cụ thể cần đứng trước pattern tổng quát. Nếu đưa `case Envelope<?>(var data, var requestId)` lên trước, nhánh này sẽ bao phủ mọi envelope và nhánh customer phía sau trở thành unreachable do dominance.

## Kiểm thử nested record pattern với instanceof

Record pattern trong `instanceof` phù hợp khi chỉ cần kiểm tra một object có cấu trúc mong muốn hay không và lấy component ngay tại chỗ:

```java
import java.util.Optional;

static Optional<CustomerSummary> customerSummary(Object value) {
    if (value instanceof Envelope<?> (
            Customer(var id, var name),
            var requestId)) {
        return Optional.of(new CustomerSummary(id, name, requestId));
    }

    return Optional.empty();
}
```

Nếu outer object không phải `Envelope`, payload không phải `Customer`, hoặc payload là null, pattern không khớp và hàm trả về `Optional.empty()`. Không cần ép kiểu thủ công hoặc gọi accessor nhiều lần sau khi đã kiểm tra cấu trúc.

Có thể viết test kiểm tra trường hợp khớp và không khớp:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class NestedRecordPatternTest {
    @Test
    void deconstructsNestedCustomer() {
        Object input = new Envelope<>(
                new Customer("C-42", "An"), "REQ-7");

        assertEquals(
                Optional.of(new CustomerSummary("C-42", "An", "REQ-7")),
                customerSummary(input));
    }

    @Test
    void rejectsDifferentNestedType() {
        Object input = new Envelope<>(123, "REQ-8");

        assertEquals(Optional.empty(), customerSummary(input));
    }

    @Test
    void rejectsNullNestedRecord() {
        Object input = new Envelope<Customer>(null, "REQ-9");

        assertEquals(Optional.empty(), customerSummary(input));
    }
}
```

Các test xác nhận pattern không chỉ kiểm tra outer type. `Envelope<Integer>` vẫn là envelope hợp lệ, nhưng không khớp nested `Customer(...)`. Tương tự, nested record null không khớp record pattern ở tầng trong.

## Kiểm thử generic record với wildcard

Khi selector có kiểu tổng quát như `Object`, không thể giả định runtime giữ lại type argument của generic record. Java dùng type erasure; pattern nên kiểm tra một kiểu có thể kiểm tra an toàn lúc chạy, chẳng hạn `Page<?>`, rồi dùng pattern ở component để kiểm tra kiểu cụ thể nếu cần.

```java
static String pageSummary(Object value) {
    return switch (value) {
        case null -> "null-page";
        case Page<?> (var items, var total) -> items.size() + "/" + total;
        default -> "not-a-page";
    };
}
```

`Page<?>` biểu diễn một `Page` với một kiểu phần tử chưa biết. Component `items` có kiểu `List<?>`, vì vậy có thể gọi `size()` nhưng không thể đọc phần tử như một `String` hoặc `Integer` nếu chưa kiểm tra kiểu tương ứng.

Test có thể chạy cùng pattern với nhiều type argument:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class GenericRecordPatternTest {
    @Test
    void matchesPageOfStrings() {
        Object input = new Page<>(List.of("a", "b"), 2);

        assertEquals("2/2", pageSummary(input));
    }

    @Test
    void matchesPageOfIntegers() {
        Object input = new Page<>(List.of(10, 20, 30), 3);

        assertEquals("3/3", pageSummary(input));
    }

    @Test
    void rejectsNonPageObject() {
        assertEquals("not-a-page", pageSummary("not a page"));
    }
}
```

Không viết pattern `Page<String>` khi selector là `Object` để mong JVM kiểm tra được type argument `String`: generic type argument bị xóa ở runtime và kiểu tham số hóa như `Page<String>` không phải kiểu reifiable. Dùng `Page<?>` để kiểm tra outer record, sau đó kiểm tra từng phần tử hoặc component theo kiểu cụ thể khi có yêu cầu.

Nếu một phương thức đã có kiểu tĩnh `Page<T>`, hãy tận dụng type information ở compile time và để compiler suy luận kiểu component khi deconstruct. Tránh raw type vì nó làm mất an toàn kiểu và có thể tạo unchecked warning.

## Kiểm thử null ở selector và component lồng nhau

Có hai trường hợp null cần tách biệt:

1. **Selector là null:** không có record nào để phân rã. Trong pattern switch, cần `case null` nếu muốn xử lý rõ ràng; `default` không nhận null.
2. **Một component bên trong record là null:** outer record vẫn tồn tại, nhưng nested record pattern không khớp component null. Một nhánh tổng quát có thể nhận envelope đó và kiểm tra component bằng `var` hoặc điều kiện phù hợp.

Ví dụ test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class NullRecordPatternTest {
    @Test
    void handlesNullSelectorExplicitly() {
        assertEquals("null-input", describe(null));
    }

    @Test
    void fallsBackWhenNestedRecordIsNull() {
        Object input = new Envelope<Customer>(null, "REQ-10");

        assertEquals("empty-payload:REQ-10", describe(input));
    }

    @Test
    void defaultDoesNotHandleNull() {
        assertThrows(NullPointerException.class,
                () -> describeWithoutNullCase(null));
    }
}
```

Hàm `describeWithoutNullCase()` minh họa switch có `default` nhưng không có `case null`:

```java
static String describeWithoutNullCase(Object value) {
    return switch (value) {
        case Envelope<?> (var data, var requestId) -> "envelope";
        default -> "other";
    };
}
```

Khi selector null, switch ném `NullPointerException`. Nếu null là đầu vào hợp lệ, hãy thêm `case null`; nếu null vi phạm hợp đồng, hãy xác thực ở ranh giới API và kiểm thử lỗi theo hợp đồng đó.

## Kiểm thử nested mismatch và thứ tự pattern

Nested record pattern có thể thất bại ở bất kỳ tầng nào: outer type không đúng, component không đúng kiểu record, hoặc một nested component tiếp tục không khớp. Test nên xác nhận các nhánh fallback có nhận đúng dữ liệu đó hay không.

```java
@Test
void fallsBackForWrongPayloadType() {
    Object input = new Envelope<>(42, "REQ-11");

    assertEquals("other-payload:REQ-11", describe(input));
}

@Test
void fallsBackForUnrelatedOuterType() {
    assertEquals("unsupported", describe(List.of("x")));
}
```

Khi refactor thứ tự nhánh, cần giữ pattern hẹp trước pattern rộng. Compiler phát hiện nhiều trường hợp dominated/unreachable, nhưng test vẫn cần xác nhận ý nghĩa nghiệp vụ của fallback, đặc biệt khi thêm một loại payload mới.

## Kiểm thử component có giá trị null

`var` pattern có thể bind component null. Vì vậy, không nên giả định một record pattern tổng quát đã loại bỏ null ở tất cả component:

```java
static String describeCustomer(Object value) {
    return switch (value) {
        case null -> "null-envelope";
        case Envelope<?> (Customer(var id, var name), var requestId)
                when name != null -> "customer:" + name;
        case Envelope<?> (Customer(var id, var name), var requestId) ->
                "customer-with-null-name:" + id;
        case Envelope<?> (var data, var requestId) -> "other:" + requestId;
        default -> "unsupported";
    };
}
```

Ở đây, `Customer` tồn tại nhưng `name` có thể null. Guard `when name != null` tách trường hợp hợp lệ theo quy tắc nghiệp vụ. Nhánh kế tiếp vẫn khớp customer có tên null và xử lý rõ ràng. Nếu không có guard hoặc nhánh kiểm tra, việc nối chuỗi có thể tạo chữ `null` hoặc logic nghiệp vụ có thể chấp nhận dữ liệu sai.

Test cần bao phủ cả hai trạng thái:

```java
@Test
void handlesNullRecordComponent() {
    Object input = new Envelope<>(new Customer("C-50", null), "REQ-12");

    assertEquals("customer-with-null-name:C-50", describeCustomer(input));
}
```

## Bộ test hoàn chỉnh với JUnit Jupiter

Một test class có thể gom các record fixture và hàm xử lý để dễ chạy độc lập. Ví dụ dưới đây minh họa các helper được dùng trong những phần trước:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class RecordPatternTest {
    record Customer(String id, String name) {}
    record Envelope<T>(T data, String requestId) {}
    record Page<T>(List<T> items, int total) {}
    record CustomerSummary(String id, String name, String requestId) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "null-input";
            case Envelope<?> (Customer(var id, var name), var requestId) ->
                    "customer:" + id + ":" + name + ":" + requestId;
            case Envelope<?> (var data, var requestId) ->
                    data == null ? "empty-payload:" + requestId
                            : "other-payload:" + requestId;
            default -> "unsupported";
        };
    }

    static String pageSummary(Object value) {
        return switch (value) {
            case null -> "null-page";
            case Page<?> (var items, var total) -> items.size() + "/" + total;
            default -> "not-a-page";
        };
    }

    static Optional<CustomerSummary> customerSummary(Object value) {
        if (value instanceof Envelope<?> (
                Customer(var id, var name), var requestId)) {
            return Optional.of(new CustomerSummary(id, name, requestId));
        }
        return Optional.empty();
    }

    static String describeWithoutNullCase(Object value) {
        return switch (value) {
            case Envelope<?> (var data, var requestId) -> "envelope";
            default -> "other";
        };
    }

    static String describeCustomer(Object value) {
        return switch (value) {
            case null -> "null-envelope";
            case Envelope<?> (Customer(var id, var name), var requestId)
                    when name != null -> "customer:" + name;
            case Envelope<?> (Customer(var id, var name), var requestId) ->
                    "customer-with-null-name:" + id;
            case Envelope<?> (var data, var requestId) -> "other:" + requestId;
            default -> "unsupported";
        };
    }

    @Test
    void nestedRecordIsDeconstructed() {
        Object input = new Envelope<>(new Customer("C-1", "An"), "R-1");
        assertEquals("customer:C-1:An:R-1", describe(input));
    }

    @Test
    void genericEnvelopeWithOtherPayloadUsesFallback() {
        Object input = new Envelope<>(123, "R-2");
        assertEquals("other-payload:R-2", describe(input));
    }

    @Test
    void nullNestedPayloadUsesFallback() {
        Object input = new Envelope<Customer>(null, "R-3");
        assertEquals("empty-payload:R-3", describe(input));
    }

    @Test
    void nullSelectorUsesExplicitCase() {
        assertEquals("null-input", describe(null));
    }

    @Test
    void defaultDoesNotMatchNull() {
        assertThrows(NullPointerException.class,
                () -> describeWithoutNullCase(null));
    }

    @Test
    void genericPageAcceptsDifferentElementTypes() {
        assertEquals("2/2", pageSummary(new Page<>(List.of("a", "b"), 2)));
        assertEquals("3/3", pageSummary(new Page<>(List.of(1, 2, 3), 3)));
    }

    @Test
    void instanceofPatternReturnsTypedSummary() {
        Object input = new Envelope<>(new Customer("C-4", "Binh"), "R-4");
        assertEquals(Optional.of(new CustomerSummary("C-4", "Binh", "R-4")),
                customerSummary(input));
    }

    @Test
    void instanceofPatternRejectsNullAndWrongNestedType() {
        assertEquals(Optional.empty(), customerSummary(null));
        assertEquals(Optional.empty(), customerSummary(new Envelope<>(99, "R-5")));
    }

    @Test
    void handlesNullRecordComponent() {
        Object input = new Envelope<>(new Customer("C-50", null), "REQ-12");

        assertEquals("customer-with-null-name:C-50", describeCustomer(input));
    }
}
```

Các fixture được đặt trong test class để ví dụ có thể đọc như một đơn vị độc lập. Trong dự án thật, record domain thường nằm trong production source, còn test chỉ import và tạo fixture cần thiết.

## Những điểm cần lưu ý khi viết test

- **Kiểm tra cấu trúc từng tầng:** một outer record đúng kiểu chưa đủ để nested pattern khớp; component ở tầng trong cũng phải phù hợp.
- **Dùng wildcard với generic runtime:** `Envelope<?>` và `Page<?>` kiểm tra outer record mà không giả vờ kiểm tra type argument đã bị erasure.
- **Kiểm tra null riêng:** selector null và nested component null là hai trường hợp khác nhau; `default` không xử lý selector null.
- **Kiểm tra fallback:** test nên xác nhận dữ liệu sai kiểu hoặc chưa hỗ trợ đi vào nhánh dự kiến.
- **Kiểm tra guard:** nếu dùng `when`, test cả trường hợp guard đúng và sai.
- **Chú ý thứ tự pattern:** nhánh cụ thể phải đứng trước nhánh tổng quát để tránh dominance.
- **Không giả định accessor luôn là field read đơn giản:** record có thể khai báo accessor tường minh; record pattern gọi accessor để lấy component. Fixture nên giữ accessor thuần, và nếu production accessor có thể ném lỗi hoặc có logic đặc biệt, hãy test hành vi đó riêng.
- **Giữ test độc lập:** mỗi test tự tạo input, không dùng chung object mutable khiến thứ tự chạy test ảnh hưởng kết quả.

## Quy trình kiểm thử record pattern trong dự án Java 21

1. **Xác định shape của dữ liệu.** Liệt kê outer record, nested record, generic component và những component có thể null.
2. **Viết pattern theo cấu trúc cần kiểm tra.** Dùng nested record pattern cho dữ liệu cần deconstruct; dùng `var` hoặc wildcard ở component generic khi chưa cần ràng buộc kiểu cụ thể.
3. **Tách nhánh null và fallback.** Dùng `case null` cho selector null; tạo nhánh tổng quát để xử lý component null hoặc kiểu payload khác.
4. **Viết test khớp hoàn toàn.** Xác nhận từng component được bind đúng vị trí và kết quả nghiệp vụ đúng.
5. **Viết test mismatch.** Bao phủ sai outer type, sai nested type, generic payload khác kiểu và nested record null.
6. **Viết test generic.** Kiểm tra nhiều type argument qua `Record<?>`; không dựa vào type argument không reifiable ở runtime.
7. **Viết test null và guard.** Phân biệt null selector, null component và điều kiện `when` không thỏa.
8. **Kiểm tra dominance và exhaustiveness.** Đặt pattern cụ thể trước pattern rộng; bảo đảm switch expression có các nhánh cần thiết.
9. **Biên dịch theo Java 21.** Dùng JDK 21 hoặc `--release 21`; Record Patterns và Pattern Matching for switch trong các ví dụ này đã ổn định, không cần `--enable-preview`.

Kiểm thử record pattern cần xác nhận cả cấu trúc dữ liệu lẫn cách chương trình phản ứng khi cấu trúc không khớp. Với nested record, kiểm tra từng tầng; với generic record, dùng wildcard và kiểm tra component theo kiểu có thể xác nhận; với null, tách selector null khỏi component null. Bộ test bao phủ các trường hợp này giúp refactor pattern an toàn và làm rõ hợp đồng dữ liệu của ứng dụng Java 21.
