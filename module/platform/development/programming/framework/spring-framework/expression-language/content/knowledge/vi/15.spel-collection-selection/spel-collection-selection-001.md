# Collection selection .?[selectionExpression] trong SpEL

## 1. Collection selection là gì?

Spring Expression Language (SpEL) cung cấp collection selection để lọc một collection theo điều kiện. Selection duyệt các phần tử của nguồn, đánh giá một biểu thức Boolean cho từng phần tử và trả về một collection mới chỉ chứa những phần tử thỏa mãn điều kiện.

Cú pháp cơ bản:

```text
source.?[selectionExpression]
```

Ví dụ, lấy các thành viên có quốc tịch Serbia:

```java
List<?> serbianMembers = parser.parseExpression(
        "members.?[nationality == 'Serbian']")
        .getValue(context, List.class);
```

Trong ví dụ này:

- `members` là collection nguồn.
- `nationality == 'Serbian'` là selection expression.
- SpEL đánh giá điều kiện trên từng thành viên.
- Chỉ các thành viên có điều kiện đúng mới xuất hiện trong kết quả.

Selection không thay đổi collection nguồn. Nó tạo kết quả lọc riêng, vì vậy có thể dùng kết quả để hiển thị, tính toán hoặc tiếp tục xử lý.

## 2. Các dạng selection

SpEL hỗ trợ ba biến thể selection:

| Cú pháp | Ý nghĩa | Kết quả |
|---|---|---|
| `.?[selectionExpression]` | Lấy tất cả phần tử phù hợp. | Collection chứa mọi phần tử được chọn. |
| ".^[selectionExpression]" | Lấy phần tử đầu tiên phù hợp. | Một phần tử hoặc null nếu không có kết quả. |
| ".$[selectionExpression]" | Lấy phần tử cuối cùng phù hợp. | Một phần tử hoặc null nếu không có kết quả. |

Ví dụ với danh sách số:

```java
List<Integer> numbers = List.of(2, 5, 8, 11, 14);
context.setVariable("numbers", numbers);

List<?> allEven = parser.parseExpression(
        "#numbers.?[#this % 2 == 0]")
        .getValue(context, List.class);
// [8, 14]

Integer firstEven = parser.parseExpression(
        "#numbers.^[#this % 2 == 0]")
        .getValue(context, Integer.class);
// 8

Integer lastEven = parser.parseExpression(
        "#numbers.$[#this % 2 == 0]")
        .getValue(context, Integer.class);
// 14
```

Dạng all-match phù hợp khi cần xử lý tất cả kết quả. Dạng first-match và last-match phù hợp khi chỉ cần một phần tử theo thứ tự duyệt của nguồn.

## 3. Selection expression và phần tử hiện tại

Selection expression được đánh giá riêng trên từng phần tử. Trong quá trình đó, phần tử đang xét trở thành active context object. Vì vậy, có thể truy cập property của phần tử trực tiếp:

```text
members.?[nationality == 'Serbian']
```

Biến hệ thống `#this` tham chiếu phần tử hiện tại. Viết tường minh bằng `#this` giúp biểu thức dễ đọc hơn khi có nhiều cấp object hoặc nhiều biến:

```text
members.?[#this.nationality == 'Serbian']
```

Với root object là một đối tượng Society, `#root` vẫn tham chiếu Society ban đầu, còn `#this` trong predicate tham chiếu từng thành viên:

```text
members.?[#this.nationality == #root.preferredNationality]
```

Selection expression cần trả về Boolean. Các phép so sánh và toán tử logic thường được dùng để tạo điều kiện:

```text
orders.?[status == 'PAID' and total >= 100000]
```

Điều kiện có thể gọi property, method hoặc kết hợp nhiều biểu thức SpEL. Hãy bảo đảm các property và method đó có thể được truy cập trên kiểu phần tử.

## 4. Selection trên List, array và Iterable

Selection được hỗ trợ trên:

- Array Java.
- Các kiểu triển khai `java.lang.Iterable`, bao gồm List và Set.
- Map Java.

Với array hoặc Iterable, predicate được đánh giá trên từng phần tử riêng lẻ. Kết quả all-match là một collection chứa các phần tử nguồn được chọn.

Ví dụ với List các Product:

```java
public class Product {
    private String code;
    private BigDecimal price;
    private boolean active;

    public String getCode() {
        return code;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}

List<Product> products = loadProducts();
context.setVariable("products", products);

List<?> activeProducts = parser.parseExpression(
        "#products.?[active]")
        .getValue(context, List.class);

List<?> affordableProducts = parser.parseExpression(
        "#products.?[active and price <= 500]")
        .getValue(context, List.class);
```

Predicate `active` đọc property Boolean của từng Product. Predicate thứ hai kết hợp trạng thái hoạt động và giới hạn giá.

Với array, cú pháp tương tự:

```java
int[] values = {3, 6, 9, 12, 15};
context.setVariable("values", values);

List<?> multiplesOfThree = parser.parseExpression(
        "#values.?[#this % 3 == 0]")
        .getValue(context, List.class);
```

Mặc dù nguồn là array, kết quả selection là collection các phần tử được chọn. Nếu API Java cần array, hãy chuyển đổi kết quả một cách tường minh.

## 5. Lấy phần tử đầu tiên và cuối cùng phù hợp

Dùng `.^[...]` khi cần phần tử đầu tiên thỏa điều kiện và `.$[...]` khi cần phần tử cuối cùng thỏa điều kiện.

Ví dụ lấy đơn hàng đầu tiên có trạng thái PAID:

```java
Order firstPaid = parser.parseExpression(
        "orders.^[status == 'PAID']")
        .getValue(context, Order.class);
```

Lấy đơn hàng PAID cuối cùng trong thứ tự duyệt:

```java
Order lastPaid = parser.parseExpression(
        "orders.$[status == 'PAID']")
        .getValue(context, Order.class);
```

Nếu không có phần tử nào phù hợp, dạng first/last không có phần tử để trả về và kết quả là null. Vì vậy, hãy kiểm tra null trước khi truy cập property tiếp theo:

```text
orders.^[status == 'PAID']?.orderNumber
```

First và last phụ thuộc thứ tự duyệt của nguồn. Với List và array, thứ tự phần tử được xác định. Với Set hoặc Map không bảo đảm encounter order, không nên giả định phần tử đầu/cuối có ý nghĩa ổn định giữa các lần chạy. Nếu thứ tự quan trọng, dùng collection có thứ tự xác định hoặc sắp xếp dữ liệu trước khi selection.

## 6. Selection trên Map

Khi nguồn là Map, SpEL đánh giá selection expression trên từng entry kiểu `java.util.Map.Entry`, không phải trực tiếp trên value. Mỗi entry có hai property:

- `key`: khóa của entry.
- `value`: giá trị của entry.

Dạng all-match giữ lại các cặp key/value phù hợp và trả về một Map mới.

Ví dụ:

```java
Map<String, Integer> inventory = Map.of(
        "PEN", 12,
        "BOOK", 45,
        "BAG", 8,
        "LAMP", 30);

context.setVariable("inventory", inventory);

Map<?, ?> lowStock = parser.parseExpression(
        "#inventory.?[value < 20]")
        .getValue(context, Map.class);
// {PEN=12, BAG=8}
```

Có thể kiểm tra cả key và value:

```text
#inventory.?[key.startsWith('B') and value < 50]
```

Ví dụ lấy các entry có key bắt đầu bằng chữ B và số lượng nhỏ hơn 50.

Với Map, đừng viết predicate như thể `#this` là value thuần. `#this` đại diện Map.Entry; hãy truy cập `key` hoặc `value`:

```text
#inventory.?[#this.value >= 30]
```

Dạng all-match giữ nguyên khóa của các entry được chọn. Khi chỉ cần một kết quả với first/last selection trên Map, hãy kiểm tra kiểu và ý nghĩa của giá trị trả về trong expression cụ thể vì predicate đang làm việc trên Map.Entry.

## 7. Null-safe collection selection

Nếu collection nguồn có thể null, selection thông thường có thể thất bại khi SpEL cố xử lý collection không tồn tại. SpEL hỗ trợ null-safe selection bằng các toán tử:

| Cú pháp | Ý nghĩa |
|---|---|
| `?.?[selectionExpression]` | Selection all-match an toàn khi nguồn null. |
| `?.^[selectionExpression]` | Selection first-match an toàn khi nguồn null. |
| `?.$[selectionExpression]` | Selection last-match an toàn khi nguồn null. |

Ví dụ:

```java
String expression =
        "members?.?[nationality == 'Serbian']";

List<?> selected = parser.parseExpression(expression)
        .getValue(context, List.class);
```

Nếu `members` là null, null-safe selection trả về null thay vì cố duyệt collection. Nếu `members` là collection rỗng, kết quả là collection rỗng. Hai tình huống này khác nhau:

| Nguồn | Selection thông thường | Null-safe selection |
|---|---|---|
| Collection có phần tử | Lọc theo predicate. | Lọc theo predicate. |
| Collection rỗng | Collection kết quả rỗng. | Collection kết quả rỗng. |
| Nguồn null | Có thể phát sinh lỗi khi thao tác trên null. | Trả về null. |

Null-safe selection chỉ bảo vệ khi chính collection nguồn null. Nó không tự bảo vệ property bên trong từng phần tử. Nếu phần tử có thể null, cần kiểm tra hoặc dùng safe navigation trong predicate:

```text
members?.?[#this?.nationality == 'Serbian']
```

Nếu sau selection còn truy cập property của kết quả first-match, hãy tiếp tục dùng safe navigation:

```text
members?.^[nationality == 'Serbian']?.name
```

Toán tử safe navigation phải được áp dụng ở mỗi đoạn có thể nhận null trong một compound expression. Safe navigation trên collection không tự làm cho toàn bộ chuỗi truy cập phía sau trở nên an toàn.

## 8. Selection khác Projection như thế nào?

Selection và projection đều duyệt collection, nhưng mục đích khác nhau:

| Tính năng | Cú pháp | Kết quả |
|---|---|---|
| Selection | `.?[predicate]` | Giữ lại phần tử nguồn thỏa điều kiện. |
| Projection | `.![expression]` | Tạo phần tử kết quả từ biểu thức áp dụng trên từng phần tử nguồn. |

Ví dụ, selection giữ lại các Product đang hoạt động:

```text
products.?[active]
```

Projection lấy code của tất cả Product:

```text
products.![code]
```

Có thể kết hợp selection trước, projection sau:

```text
products.?[active].![code]
```

Kết quả là danh sách code của các Product đang hoạt động. Selection quyết định phần tử nào được giữ lại; projection quyết định giá trị nào được tạo ra từ phần tử đó.

Nếu muốn chỉ lấy một vài phần tử rồi biến đổi, có thể kết hợp first/last selection với property access:

```text
products.^[active and price < 100]?.code
```

## 9. Ví dụ kiểm thử bằng Java và JUnit

Một kiểm thử tốt nên xác nhận trường hợp có nhiều phần tử phù hợp, không có phần tử phù hợp, first/last và collection rỗng.

Ví dụ với danh sách số:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class CollectionSelectionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void selectsAllMatchingValues() {
        var context = new StandardEvaluationContext();
        context.setVariable("numbers", List.of(2, 5, 8, 11, 14));

        List<?> result = parser.parseExpression(
                "#numbers.?[#this % 2 == 0]")
                .getValue(context, List.class);

        assertEquals(List.of(2, 8, 14), result);
    }

    @Test
    void selectsFirstAndLastMatchingValues() {
        var context = new StandardEvaluationContext();
        context.setVariable("numbers", List.of(2, 5, 8, 11, 14));

        Integer first = parser.parseExpression(
                "#numbers.^[#this > 5]")
                .getValue(context, Integer.class);

        Integer last = parser.parseExpression(
                "#numbers.$[#this > 5]")
                .getValue(context, Integer.class);

        assertEquals(8, first);
        assertEquals(14, last);
    }

    @Test
    void returnsEmptyCollectionWhenNoElementMatches() {
        var context = new StandardEvaluationContext();
        context.setVariable("numbers", List.of(2, 4, 6));

        List<?> result = parser.parseExpression(
                "#numbers.?[#this > 10]")
                .getValue(context, List.class);

        assertTrue(result.isEmpty());
    }
}
```

Với Map, nên kiểm tra cả số entry còn lại và key/value:

```java
@Test
void selectsMapEntriesByValue() {
    var context = new StandardEvaluationContext();
    context.setVariable("inventory", Map.of(
            "PEN", 12,
            "BOOK", 45,
            "BAG", 8));

    Map<?, ?> result = parser.parseExpression(
            "#inventory.?[value < 20]")
            .getValue(context, Map.class);

    assertEquals(2, result.size());
    assertEquals(12, result.get("PEN"));
    assertEquals(8, result.get("BAG"));
}
```

Null-safe selection nên có test riêng cho nguồn null và nguồn rỗng để bảo đảm caller hiểu đúng hai kết quả khác nhau.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Selection không lọc được | Predicate không trả về Boolean hoặc property sai tên. | Kiểm tra predicate trên một phần tử đơn lẻ. |
| Kết quả là List nhưng mong đợi Map | Nguồn không phải Map hoặc đang selection trên Iterable. | Kiểm tra kiểu nguồn trước khi chọn. |
| Predicate Map không tìm thấy key | Đang truy cập nhầm entry; Map predicate dùng `key` và `value`. | Dùng `key`, `value` hoặc `#this.key`, `#this.value`. |
| First/last trả null | Không có phần tử phù hợp. | Kiểm tra điều kiện và xử lý null trước khi truy cập tiếp. |
| First/last không ổn định | Nguồn không có thứ tự duyệt xác định. | Dùng List/array hoặc collection có thứ tự rõ ràng. |
| Selection trên nguồn null phát sinh lỗi | Dùng `.?[]` với collection có thể null. | Dùng null-safe selection `?.?[]`. |
| Phần tử null gây lỗi trong predicate | Collection có phần tử null và predicate truy cập property trực tiếp. | Lọc null hoặc dùng safe navigation trên `#this`. |
| Selection làm mất dữ liệu nguồn? | Nhầm kết quả lọc với thao tác sửa collection. | Selection tạo collection kết quả; nếu cần cập nhật nguồn, thực hiện riêng bằng Java. |
| Nhầm selection với projection | Dùng predicate để mong nhận một giá trị biến đổi. | Dùng `.![...]` cho projection. |
| Kết quả Map không đúng mong đợi | Predicate đang chạy trên Map.Entry, không phải value thuần. | Kiểm tra cả `key` và `value` trong điều kiện. |

## 11. Quy trình thiết kế và kiểm thử selection

1. Xác định kiểu nguồn là array, Iterable hay Map.
2. Xác định muốn lấy tất cả, phần tử đầu tiên hay phần tử cuối cùng.
3. Viết predicate Boolean đơn giản cho một phần tử trước, sau đó mới áp dụng lên collection.
4. Dùng `#this` khi cần chỉ rõ phần tử hiện tại; với Map, dùng `key` và `value`.
5. Kiểm tra nguồn rỗng, không có kết quả phù hợp và nguồn null.
6. Nếu thứ tự có ý nghĩa, xác nhận collection nguồn có thứ tự duyệt ổn định.
7. Nếu phần tử có thể null, bảo vệ các property được đọc trong predicate.
8. Dùng projection riêng nếu cần biến đổi phần tử sau khi lọc.
9. Kiểm thử kết quả và kiểu trả về với cùng EvaluationContext và root object như môi trường ứng dụng.

## 12. Ghi nhớ

- `.?[predicate]` lấy tất cả phần tử phù hợp; ".^[predicate]" lấy phần tử đầu tiên; ".$[predicate]" lấy phần tử cuối cùng.
- Selection hỗ trợ array, Iterable và Map.
- Với array/Iterable, predicate được đánh giá trên từng phần tử; với Map, predicate được đánh giá trên Map.Entry.
- Map entry cung cấp property `key` và `value`; all-match selection trả về Map chứa các entry phù hợp.
- `#this` tham chiếu phần tử hoặc entry đang được đánh giá; `#root` vẫn tham chiếu root object ban đầu.
- Predicate phải tạo ra Boolean.
- First/last phụ thuộc thứ tự duyệt; tránh dựa vào thứ tự không được bảo đảm của Set/Map.
- Null-safe selection dùng `?.?`, `?.^` và `?.$`; nguồn null trả về null, còn nguồn rỗng trả về collection rỗng.
- Selection giữ phần tử nguồn; projection `.![...]` tạo giá trị mới từ mỗi phần tử.
- Kiểm thử cả nguồn null, rỗng, không có match, nhiều match và phần tử null nếu mô hình dữ liệu cho phép.

## Tài liệu tham khảo

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Safe Navigation and Safe Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Selection AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Selection.html)
