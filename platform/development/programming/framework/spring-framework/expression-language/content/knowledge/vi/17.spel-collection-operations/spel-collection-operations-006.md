# Giữ thứ tự khi lọc và chiếu collection trong SpEL

## Mục tiêu

Khi dùng Spring Expression Language (SpEL) để lọc hoặc biến đổi một collection, thứ tự kết quả phụ thuộc vào thứ tự duyệt của collection nguồn và loại cấu trúc mà toán tử trả về. Với `List` hoặc array, thứ tự phần tử có thể được giữ xuyên suốt selection và projection. Với `Set` hoặc `Map`, cần hiểu rõ iterator order của cấu trúc nguồn; không nên giả định mọi collection đều có thứ tự ổn định.

Ví dụ:

```spel
orders.?[status == 'PAID'].![id]
```

Biểu thức lọc các order có trạng thái `PAID`, sau đó lấy `id` của từng order được giữ lại. Kết quả đi theo thứ tự encounter của collection `orders`. Selection loại bỏ phần tử không phù hợp; projection tạo giá trị tương ứng cho từng phần tử còn lại.

## 1. Thứ tự đến từ collection nguồn

SpEL duyệt collection theo cơ chế iterator hoặc chỉ số mà cấu trúc cung cấp. Selection và projection không tự sắp xếp dữ liệu theo một tiêu chí mới.

| Collection nguồn | Thứ tự duyệt | Ý nghĩa đối với kết quả |
| --- | --- | --- |
| Array | Theo index từ `0` đến cuối | Kết quả đi theo thứ tự phần tử trong array. |
| `List` | Theo thứ tự phần tử của List | Selection giữ thứ tự encounter của các phần tử được chọn; projection tạo kết quả theo cùng thứ tự. |
| `LinkedHashSet` | Theo thứ tự insertion | Kết quả theo thứ tự iterator, thường là thứ tự thêm phần tử. |
| `TreeSet` | Theo comparator/natural ordering | Kết quả theo thứ tự sắp xếp mà Set cung cấp. |
| `HashSet` | Không bảo đảm thứ tự | Không dựa vào vị trí quan sát được để xác định kết quả giữa các lần chạy. |
| `LinkedHashMap` | Theo thứ tự iteration được duy trì bởi Map | Projection duyệt entry theo thứ tự Map cung cấp; xem lưu ý riêng về kết quả selection trên Map. |
| `TreeMap` | Theo thứ tự key của comparator | Projection duyệt entry theo thứ tự key mà Map cung cấp. |
| `HashMap` | Không bảo đảm thứ tự | Không dựa vào thứ tự key/value được quan sát trong một lần chạy. |

Muốn kết quả có thứ tự ổn định, hãy bắt đầu từ một nguồn có thứ tự được định nghĩa rõ ràng, chẳng hạn `ArrayList`, `LinkedHashSet`, `TreeSet`, `LinkedHashMap` hoặc `TreeMap`, tùy theo quy tắc nghiệp vụ.

## 2. Selection giữ thứ tự encounter trên Iterable

Collection selection dùng `.?[condition]` để giữ lại những phần tử mà biểu thức điều kiện trả về `true`:

```spel
orders.?[status == 'PAID']
```

Với array hoặc `Iterable` như `List`, SpEL duyệt nguồn và thêm các phần tử phù hợp vào collection kết quả theo thứ tự encounter. Những phần tử không phù hợp bị bỏ qua; các phần tử còn lại giữ thứ tự tương đối của chúng.

Ví dụ nguồn có thứ tự:

```text
[A: PENDING, B: PAID, C: PAID, D: CANCELLED, E: PAID]
```

Selection:

```spel
orders.?[status == 'PAID']
```

Cho các phần tử theo thứ tự `B, C, E`. Selection không sắp xếp lại chúng theo ID, thời gian hay giá trị của property.

Selection có thể dùng `#this` tường minh để chỉ phần tử đang xét:

```spel
orders.?[#this.status == 'PAID']
```

Ở cấp điều kiện, `#this` là order hiện tại. `#root` vẫn là root object của toàn bộ lần đánh giá nếu cần tham chiếu một ngưỡng hoặc property bên ngoài collection.

## 3. Projection giữ thứ tự phần tử đầu vào

Collection projection dùng `.![expression]` để tính một giá trị cho từng phần tử:

```spel
orders.![id]
```

Với array hoặc `Iterable`, projection tạo một List kết quả theo thứ tự duyệt nguồn. Mỗi phần tử đầu vào tạo ra một kết quả tương ứng, kể cả khi biểu thức con trả về null hoặc hai phần tử cho cùng một giá trị.

Ví dụ:

```text
Input:  [Order(id=12), Order(id=7), Order(id=21)]
Output: [12, 7, 21]
```

Biểu thức:

```spel
orders.![id]
```

Projection không tự sort thành `[7, 12, 21]`. Nếu cần sắp xếp, phải thực hiện một bước sort rõ ràng ở Java hoặc cung cấp collection đã được sắp xếp làm đầu vào.

## 4. Kết hợp selection và projection

Để vừa lọc vừa chuyển đổi, có thể nối hai toán tử:

```spel
orders.?[status == 'PAID'].![id]
```

Quy trình là:

1. Duyệt `orders` theo thứ tự nguồn.
2. Đánh giá điều kiện `status == 'PAID'` trên từng order.
3. Giữ các order thỏa điều kiện theo thứ tự encounter.
4. Đánh giá `id` trên từng order đã giữ.
5. Tạo List kết quả theo cùng thứ tự.

Ví dụ nguồn:

```text
[Order(12, PAID), Order(7, PENDING), Order(21, PAID), Order(4, CANCELLED)]
```

Kết quả:

```text
[12, 21]
```

Đây là thứ tự của hai order phù hợp trong nguồn, không phải thứ tự tăng dần của ID.

Nếu muốn lọc theo một property rồi chiếu nhiều giá trị, projection expression có thể tạo inline list cho mỗi phần tử:

```spel
orders.?[status == 'PAID'].![{id, customer.name, total}]
```

Kết quả là một List chứa các list con, mỗi list con mô tả một order được chọn. Projection lồng nhau không tự flatten kết quả.

## 5. Phân biệt thứ tự, lọc và sắp xếp

Selection, projection và sorting là ba thao tác khác nhau:

| Thao tác | SpEL hoặc Java | Tác dụng lên thứ tự |
| --- | --- | --- |
| Selection | `items.?[condition]` | Loại phần tử không phù hợp; giữ thứ tự encounter của phần tử được giữ trên Iterable. |
| Projection | `items.![expression]` | Biến đổi từng phần tử; giữ thứ tự encounter của kết quả trên Iterable. |
| Sorting | Java `List.sort`, `Stream.sorted` hoặc collection đã sắp xếp | Sắp xếp theo comparator/tiêu chí được chỉ định. |

SpEL không có một toán tử collection sort chuyên biệt tương ứng với `.?[]` hoặc `.![...]`. Nếu yêu cầu là “lọc rồi sắp xếp”, hãy thực hiện sorting rõ ràng trong Java sau khi lọc, hoặc chuẩn bị một collection đã sắp xếp trước khi truyền vào SpEL.

Ví dụ Java dùng comparator:

```java
List<Order> paidOrders = orders.stream()
        .filter(order -> "PAID".equals(order.getStatus()))
        .sorted(Comparator.comparing(Order::getCreatedAt)
                .thenComparing(Order::getId))
        .toList();
```

Hoặc dùng SpEL để lọc/chiếu trên `paidOrders` sau khi Java đã sắp xếp:

```spel
paidOrders.![id]
```

Việc xác định tiêu chí tie-breaker như `createdAt` rồi `id` giúp thứ tự kết quả có thể dự đoán khi nhiều phần tử có cùng giá trị chính.

## 6. First selection và last selection phụ thuộc thứ tự nguồn

SpEL có các toán tử selection để lấy phần tử phù hợp đầu tiên hoặc cuối cùng:

```spel
orders.^[status == 'PAID']
orders.$[status == 'PAID']
```

`.^[...]` tìm phần tử phù hợp đầu tiên theo thứ tự duyệt nguồn; `.$[...]` tìm phần tử phù hợp cuối cùng theo thứ tự duyệt nguồn. Vì vậy, khái niệm “đầu tiên” và “cuối cùng” chỉ có ý nghĩa ổn định khi collection nguồn có thứ tự ổn định.

Ví dụ với List:

```text
[A: PENDING, B: PAID, C: PAID, D: CANCELLED]
```

- `orders.^[status == 'PAID']` chọn `B`.
- `orders.$[status == 'PAID']` chọn `C`.

Nếu nguồn là `HashSet`, không nên dùng first/last như một quy tắc nghiệp vụ vì iterator order không được bảo đảm. Hãy sắp xếp hoặc chuyển nguồn sang cấu trúc có thứ tự trước khi dùng các toán tử này.

## 7. Lưu ý riêng khi selection hoặc projection trên Map

Map khác với Iterable thông thường vì mỗi phần tử duyệt là một entry gồm `key` và `value`, đồng thời selection và projection trả về các kiểu kết quả khác nhau:

- Selection trên Map đánh giá điều kiện trên từng `Map.Entry` và trả về Map gồm các entry phù hợp. Đừng giả định implementation của Map kết quả giữ nguyên thứ tự của Map nguồn; nếu thứ tự quan trọng, hãy kiểm tra và chuẩn hóa kết quả ở Java.
- Projection trên Map đánh giá biểu thức trên từng entry và trả về List các giá trị chiếu. List này theo thứ tự duyệt entry của Map nguồn.

Ví dụ:

```spel
officers.?[value.active == true]
officers.![key]
officers.![value.name]
officers.![key + ' -> ' + value.name]
```

Selection giữ các cặp key/value phù hợp trong kết quả Map. Projection chỉ tạo một List kết quả; key không được giữ như cấu trúc Map trừ khi biểu thức đưa key vào chính giá trị được chiếu.

Nếu cần vừa lọc Map vừa tạo một danh sách nhãn có thứ tự từ nguồn Map, có thể chiếu trực tiếp các entry hoặc chuyển entry set sang một List có thứ tự trong Java trước khi đánh giá. Nếu cần một Map có thứ tự cụ thể sau selection, hãy tạo `LinkedHashMap`/`TreeMap` theo yêu cầu ở tầng Java.

## 8. Duplicates và null không tự bị loại bỏ

Selection và projection không phải thao tác distinct:

- Nếu nguồn List có hai phần tử bằng nhau, selection có thể giữ cả hai.
- Nếu hai phần tử khác nhau được chiếu thành cùng một giá trị, projection giữ cả hai kết quả.
- Nếu projection expression trả về null cho một phần tử, vị trí kết quả tương ứng vẫn có giá trị null.
- Selection chỉ giữ/bỏ phần tử theo kết quả điều kiện; nó không tự loại duplicate trong phần tử được giữ.

Ví dụ:

```spel
members.![nationality]
```

Nếu ba member có quốc tịch `VN`, `VN`, `SG`, kết quả là `[VN, VN, SG]`, không tự chuyển thành `[VN, SG]`. Nếu muốn loại trùng, dùng `distinct()` ở Java Stream hoặc một cấu trúc Set có semantics phù hợp, đồng thời xác định thứ tự cần giữ.

## 9. Kết quả mới và collection nguồn

Selection và projection tạo collection kết quả; chúng không sort hoặc sửa collection nguồn. Tuy nhiên, nếu kết quả chứa object tham chiếu từ nguồn, các object đó không được deep-copy.

Ví dụ:

```spel
orders.?[status == 'PAID']
orders.![#this]
```

Selection trả về các order phù hợp; projection trả về List chứa tham chiếu đến các order. Thay đổi cấu trúc List kết quả không làm thay đổi cấu trúc List nguồn, nhưng thay đổi trạng thái một object Order được tham chiếu vẫn tác động đến chính object đó.

Nếu cần một snapshot độc lập, hãy tạo bản sao hoặc chiếu sang DTO/value object bất biến ở tầng ứng dụng. Đừng dùng projection trả về `#this` như một deep copy.

## 10. Null-safe selection và projection

Với Spring Framework 6.2 trở lên, có thể dùng null-safe selection và projection khi chính collection nguồn có thể null:

```spel
orders?.?[status == 'PAID']
orders?.![id]
```

Nếu `orders` là null, kết quả null-safe tương ứng là null. Nếu collection tồn tại, thứ tự duyệt và quy tắc selection/projection vẫn áp dụng như bình thường.

Null-safe operator không tự xử lý mọi property null bên trong từng phần tử. Nếu `status` hoặc object lồng nhau có thể null, hãy viết điều kiện/biểu thức con an toàn, chẳng hạn:

```spel
orders?.?[#this?.customer?.active == true].![id]
```

Nếu cần một collection rỗng thay cho null, có thể dùng Elvis operator:

```spel
(orders?.?[status == 'PAID']) ?: {}
```

Trong ví dụ này, `{}` là inline empty list. Hãy chọn chính sách null rõ ràng: null có thể có nghĩa là “không có dữ liệu”, trong khi empty list có nghĩa là “đã đánh giá và không có phần tử”.

## 11. Tái sử dụng expression và context

Expression có thể parse một lần rồi đánh giá trên các root object/context khác nhau:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "orders.?[status == #status].![id]");

StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("status", "PAID");

List<?> paidIds = expression.getValue(context, List.class);
```

Biến `#status` được đọc khi đánh giá; thứ tự kết quả vẫn theo thứ tự duyệt của `orders`. Nếu mỗi request có trạng thái lọc khác nhau, hãy cung cấp context riêng cho request đó.

Không chia sẻ một `EvaluationContext` mutable giữa các request đồng thời nếu các request có thể thay đổi biến. Tách context theo request giúp tránh trường hợp giá trị lọc của request này ghi đè request khác.

## 12. Checklist để giữ thứ tự đúng

Trước khi dùng kết quả trong UI, báo cáo hoặc xử lý nghiệp vụ, hãy xác định:

1. Nguồn là array, List, Set hay Map?
2. Iterator order của nguồn có được đảm bảo không?
3. Đang dùng selection `.?[]`, projection `.![...]`, first `.^[]` hay last `.$[]`?
4. Nếu selection/projection nối tiếp nhau, có cần giữ đúng encounter order của các phần tử nguồn không?
5. Có cần sorting theo tiêu chí nghiệp vụ sau khi lọc không?
6. Nguồn Map có cần giữ key và thứ tự Map sau selection không?
7. Có cần loại duplicate hoặc null không, hay cần giữ nguyên số phần tử?
8. Kết quả có cần snapshot độc lập hay chỉ cần collection chứa các reference gốc?

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Kết quả selection đúng phần tử nhưng sai thứ tự mong đợi | Nguồn là HashSet/HashMap hoặc collection không cam kết iterator order. | Dùng nguồn có thứ tự xác định hoặc chuẩn hóa/sort ở Java trước khi đánh giá. |
| Projection cho kết quả không tăng dần | Projection chỉ biến đổi; nó không sort. | Thực hiện `sorted`/`List.sort` với comparator rõ ràng. |
| First/last selection thay đổi giữa các lần chạy | Dùng `.^[]`/`.$[]` trên nguồn không có thứ tự ổn định. | Cung cấp List đã sắp xếp hoặc collection có order xác định. |
| Map selection trả về cấu trúc không giữ thứ tự mong đợi | Map kết quả không được đảm bảo giữ thứ tự của Map nguồn. | Chuẩn hóa kết quả sang `LinkedHashMap`/`TreeMap` ở Java nếu thứ tự Map là yêu cầu. |
| Map projection làm mất key | Projection trả về List giá trị được chiếu. | Đưa `key` vào biểu thức chiếu hoặc tạo Map mới trong Java. |
| Kết quả còn phần tử trùng hoặc null | Selection/projection không tự distinct hoặc filter null từ projection. | Dùng `distinct`, filter hoặc rule rõ ràng ở tầng Java/SpEL. |
| Kết quả thay đổi khi object nguồn bị cập nhật | Projection có thể giữ tham chiếu đến object gốc. | Chiếu sang DTO/value object hoặc tạo snapshot khi cần độc lập. |
| Null collection gây lỗi | Đang dùng selection/projection thông thường trên null. | Spring 6.2+ dùng `?.?[]` hoặc `?.![]`; nếu cần empty list, kết hợp Elvis. |

## Ghi nhớ

- Selection `.?[]` lọc phần tử; projection `.![...]` biến đổi từng phần tử; hai toán tử này không tự sắp xếp.
- Với array và Iterable có thứ tự, selection giữ thứ tự encounter của phần tử được chọn; projection tạo List theo thứ tự duyệt nguồn.
- List giữ thứ tự phần tử; LinkedHashSet giữ insertion order; TreeSet dùng comparator; HashSet không bảo đảm thứ tự.
- Map có semantics thứ tự riêng; projection trên Map trả về List theo thứ tự entry của nguồn, còn selection trả về Map và không nên giả định thứ tự Map kết quả.
- `.^[]` và `.$[]` xác định phần tử phù hợp đầu/cuối theo thứ tự duyệt nguồn.
- Projection giữ duplicate và kết quả null; muốn distinct/filter phải làm rõ ở một bước riêng.
- SpEL không có toán tử collection sort chuyên biệt; dùng Java comparator/Stream hoặc chuẩn bị collection đã sắp xếp.
- Selection/projection tạo collection kết quả nhưng không deep-copy các object tham chiếu.
- Spring Framework 6.2+ hỗ trợ null-safe selection `?.?[]` và projection `?.![]` khi collection nguồn null.
- Dùng collection có thứ tự xác định và context riêng cho từng request nếu kết quả phải ổn định và có thể tái lập.

## Tài liệu tham khảo

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Java API — List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html)
- [Java API — LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html)
- [Java API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)