# Collection projection `.![projectionExpression]` trong SpEL

## Mục tiêu

Collection projection cho phép một collection cung cấp lần lượt từng phần tử để SpEL đánh giá một biểu thức con. Kết quả là một collection mới chứa giá trị được tính cho từng phần tử nguồn. Cú pháp là `.![projectionExpression]`.

Projection thường dùng để chuyển danh sách object thành danh sách property, tạo chuỗi hiển thị, tính một giá trị cho mỗi phần tử hoặc trích xuất dữ liệu từ map. Ví dụ, `members.![placeOfBirth.city]` tạo danh sách thành phố nơi các member sinh ra.

Điểm cần phân biệt: projection biến đổi từng phần tử và giữ một kết quả cho mỗi phần tử nguồn; selection (`.?[...]`) lọc các phần tử thỏa điều kiện. Projection không tự loại bỏ phần tử có kết quả null hoặc các giá trị trùng nhau.

## 1. Cú pháp cơ bản

```spel
members.![name]
members.![placeOfBirth.city]
members.![name.toUpperCase()]
```

Với mỗi phần tử trong `members`, SpEL đánh giá biểu thức nằm trong `![...]`. Nếu `members` là danh sách ba member, `members.![name]` tạo danh sách gồm ba tên theo cùng thứ tự duyệt của nguồn.

Ví dụ Java:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(society);

Expression expression = parser.parseExpression("members.![placeOfBirth.city]");
List<?> cities = expression.getValue(context, List.class);
```

Giả sử hai member lần lượt sinh tại Smiljan và Idvor, kết quả là `['Smiljan', 'Idvor']`. Projection trả về collection kết quả mới; nó không thay đổi collection `members` ban đầu.

## 2. Active object bên trong projection

Trong biểu thức projection, `#this` là phần tử hiện tại đang được xử lý. Ở cấp ngoài, `#root` vẫn trỏ đến root object ban đầu của lần đánh giá.

```spel
members.![#this.name]
members.![#this.placeOfBirth.city]
members.![#this.score >= #root.minimumScore]
```

- `#this.name` đọc tên của member hiện tại.
- `#this.placeOfBirth.city` đi từ member hiện tại đến thành phố nơi sinh.
- `#root.minimumScore` đọc ngưỡng trên root object, trong khi `#this.score` là điểm của member đang được xử lý.

Trong projection đơn giản, property có thể viết không cần `#this`, ví dụ `members.![name]`. Dùng `#this` tường minh sẽ giúp dễ đọc hơn khi biểu thức có nhiều cấp object hoặc cần phân biệt phần tử hiện tại với root object.

## 3. Projection trên array, Iterable và Map

SpEL hỗ trợ projection trên array, mọi kiểu triển khai `java.lang.Iterable` và `java.util.Map`.

| Nguồn | Projection | Kết quả |
| --- | --- | --- |
| Array | `names.![toUpperCase()]` | Collection chứa chuỗi đã chuyển thành chữ hoa. |
| `List` | `members.![name]` | Danh sách tên theo thứ tự list. |
| `Set` | `members.![name]` | Danh sách kết quả theo thứ tự iterator của Set. |
| `Map` | `officers.![value.name]` | Danh sách tên lấy từ value của từng entry. |

Với `Set` hoặc một collection không đảm bảo thứ tự, thứ tự kết quả phụ thuộc vào iterator của nguồn. Nếu thứ tự là một phần của yêu cầu nghiệp vụ, hãy dùng nguồn có thứ tự ổn định, chẳng hạn `List` hoặc `LinkedHashSet`.

### Projection trên Map

Khi projection chạy trên `Map`, biểu thức con được đánh giá trên từng entry, tức đối tượng `java.util.Map.Entry`. Hai property quan trọng là `key` và `value`:

```spel
officers.![key]
officers.![value]
officers.![value.name]
officers.![key + ' -> ' + value.name]
```

Kết quả projection trên Map là một `List` gồm các giá trị được tính từ từng entry; nó không phải một Map mới. Nếu cần giữ lại key/value dưới dạng map, hãy tạo cấu trúc đó ở Java hoặc dùng một API/helper phù hợp.

Ví dụ Java:

```java
Expression expression = parser.parseExpression("officers.![key + ' -> ' + value.name]");
List<?> labels = expression.getValue(context, List.class);
```

Thứ tự các kết quả phản ánh thứ tự duyệt của Map. Với `HashMap`, không nên giả định thứ tự ổn định; dùng `LinkedHashMap` hoặc một Map có thứ tự nếu cần.

## 4. Projection khác Selection

Selection và projection đều duyệt một collection nhưng giải quyết hai nhu cầu khác nhau:

| Toán tử | Cú pháp | Mục đích | Kết quả |
| --- | --- | --- | --- |
| Selection | `.?[condition]` | Giữ lại các phần tử thỏa điều kiện. | Collection gồm các phần tử nguồn được chọn. |
| Projection | `.![expression]` | Tính một giá trị từ mỗi phần tử. | Collection gồm kết quả của biểu thức con. |

Ví dụ, chỉ lấy tên các member có quốc tịch Serbia:

```spel
members.?[nationality == 'Serbian'].![name]
```

SpEL trước tiên lọc các member có `nationality == 'Serbian'`, sau đó projection lấy `name` từ mỗi member được giữ lại. Kết quả là danh sách tên, không còn là danh sách object member.

Nếu cần giữ cả phần tử có kết quả null, projection vẫn giữ vị trí tương ứng. Nếu cần bỏ các phần tử không thỏa điều kiện, hãy dùng selection trước projection hoặc lọc dữ liệu ở tầng ứng dụng.

## 5. Projection có thể tính toán và gọi method

Biểu thức con không chỉ đọc property. Nó có thể nối chuỗi, tính toán, gọi method hoặc dùng biến trong `EvaluationContext`:

```spel
members.![name.toUpperCase()]
products.![price * #quantity]
members.![name + ' (' + nationality + ')']
members.![#prefix + #this.name]
```

Ví dụ truyền biến từ Java:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("members.![#prefix + #this.name]");

StandardEvaluationContext context = new StandardEvaluationContext(society);
context.setVariable("prefix", "Member: ");

List<?> labels = expression.getValue(context, List.class);
```

`#prefix` là biến được ứng dụng đăng ký; `#this` thay đổi theo từng member. Cùng expression có thể được đánh giá với context khác để tạo kết quả theo dữ liệu runtime.

Vì biểu thức con được chạy cho từng phần tử, method call có thể được thực hiện nhiều lần. Tránh gọi method có side effect như ghi database, gửi message hoặc thay đổi trạng thái trong projection. Nên dùng biểu thức projection cho việc đọc và tính toán có thể dự đoán được.

## 6. Projection lồng nhau

Projection có thể lồng để chuyển đổi cấu trúc nhiều cấp. Ví dụ một danh sách order, mỗi order có danh sách item:

```spel
orders.![items.![productName]]
```

Kết quả là danh sách các danh sách tên sản phẩm: mỗi order tạo ra một list con. Nếu muốn làm phẳng thành một danh sách duy nhất, SpEL projection không tự flatten cấu trúc; hãy dùng stream/flatMap hoặc helper method trong Java.

Có thể kết hợp projection với property navigation ở nhiều cấp:

```spel
orders.![customer.address.city]
departments.![employees.![email]]
```

Trong biểu thức lồng nhau, `#this` đại diện cho phần tử hiện tại tại phạm vi projection đang thực hiện. Khi cần truy cập root object ban đầu, dùng `#root` để tránh nhầm với object ở cấp lồng bên trong.

## 7. Null và safe projection

Nếu collection nguồn là null, projection thông thường không phải cách kiểm tra null. Với Spring Framework 6.2 trở lên, có thể dùng null-safe projection `?.!`:

```spel
members?.![placeOfBirth.city]
```

Nếu `members` là null, biểu thức trả về null thay vì phát sinh lỗi chỉ vì collection nguồn null. Nếu `members` không null, projection hoạt động như bình thường.

Null-safe projection xử lý collection nguồn null; nó không tự xử lý mọi object null bên trong từng phần tử. Nếu một member có thể null hoặc `placeOfBirth` có thể null, dùng safe navigation trong biểu thức con:

```spel
members?.![#this?.placeOfBirth?.city]
```

Khi một phần tử cho ra kết quả null, projection vẫn giữ kết quả null đó trong danh sách. Nó không tự bỏ phần tử như selection.

Với Spring trước 6.2, dùng kiểm tra null tường minh hoặc xử lý collection trong Java trước khi đánh giá projection. Cú pháp `?.!` cần phiên bản framework hỗ trợ.

## 8. Kích thước, thứ tự và kiểu kết quả

Projection thực hiện một phép tính cho mỗi phần tử nguồn. Với array hoặc `Iterable`, kết quả có cùng số phần tử với nguồn; với Map, kết quả có một giá trị cho mỗi entry. Nếu biểu thức con trả về null, giá trị null vẫn chiếm một vị trí.

Những điểm cần nhớ:

- Projection tạo collection kết quả mới và không sửa collection nguồn.
- Các giá trị kết quả có thể là object tham chiếu; nếu projection trả về chính `#this`, các phần tử trong list kết quả vẫn là những object gốc, không phải bản sao sâu.
- Giá trị trùng nhau không tự bị loại bỏ.
- Thứ tự kết quả theo thứ tự duyệt nguồn.
- Với Map, kết quả là List; key không được giữ tự động trong cấu trúc kết quả.

Ví dụ:

```spel
members.![#this]
```

Biểu thức trên tạo một list mới chứa các tham chiếu tới các member hiện có. Thay đổi cấu trúc list kết quả không thay đổi cấu trúc list nguồn, nhưng thay đổi trạng thái một member bên trong vẫn tác động đến chính object đó vì hai bên cùng tham chiếu.

## 9. Tái sử dụng expression

Không cần parse lại cùng một biểu thức mỗi lần projection chạy. Có thể parse một lần rồi đánh giá với root object/context phù hợp:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("members.![name]");

List<?> namesForFirstSociety = expression.getValue(firstContext, List.class);
List<?> namesForSecondSociety = expression.getValue(secondContext, List.class);
```

Expression đã parse có thể tái sử dụng; dữ liệu được projection lấy từ root object và context ở mỗi lần `getValue`. Nếu dùng biến trong context, hãy cung cấp giá trị đúng cho từng lần đánh giá.

Không chia sẻ một `EvaluationContext` mutable giữa nhiều request đồng thời nếu các request có thể thay đổi biến hoặc trạng thái context. Dùng context riêng theo request hoặc lần đánh giá để tránh dữ liệu bị ghi đè.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Dùng `.![]` nhưng muốn lọc phần tử | Projection biến đổi từng phần tử, không kiểm tra điều kiện để loại bỏ phần tử. | Dùng `.?[condition]` trước projection. |
| Projection trên Map không trả về Map | Projection của Map trả về List các kết quả trên từng `Map.Entry`. | Đọc `key` và `value` trong biểu thức; tạo Map mới ở Java nếu cần giữ key. |
| Kết quả có phần tử null | Biểu thức con trả về null hoặc safe navigation gặp property null. | Xử lý null rõ ràng hoặc lọc phần tử bằng selection nếu cần loại bỏ. |
| Collection nguồn null gây lỗi | Đã dùng projection thông thường trên null. | Với Spring 6.2+, dùng `?.!`; nếu phiên bản cũ, kiểm tra null trước. |
| Lỗi khi property bên trong phần tử null | Collection không null nhưng object lồng bên trong null. | Dùng safe navigation trong projection expression, ví dụ `#this?.placeOfBirth?.city`. |
| Thứ tự kết quả không như mong đợi | Collection nguồn không đảm bảo thứ tự iterator. | Dùng collection có thứ tự xác định nếu thứ tự là yêu cầu. |
| Method bị gọi nhiều lần | Projection đánh giá biểu thức con cho mỗi phần tử. | Tránh method có side effect; chuẩn bị dữ liệu trước hoặc dùng helper thuần đọc. |
| Kết quả lồng nhau thay vì một list phẳng | Projection lồng nhau giữ cấu trúc nhiều cấp. | Dùng `flatMap` hoặc helper Java để làm phẳng. |

## Ghi nhớ

- `.![projectionExpression]` đánh giá biểu thức con cho từng phần tử và tạo collection kết quả mới.
- `#this` là phần tử hiện tại; `#root` vẫn là root object ban đầu.
- Projection hỗ trợ array, `Iterable` và `Map`; projection trên Map làm việc với `Map.Entry` và trả về List.
- Dùng `key` và `value` để đọc Map entry trong projection.
- Selection `.?[...]` lọc phần tử; projection `.![...]` biến đổi phần tử.
- Projection giữ một kết quả cho mỗi phần tử nguồn, kể cả khi kết quả là null; nó không tự distinct hoặc filter.
- Projection có thể gọi method và tính toán, nhưng tránh side effect vì biểu thức chạy cho từng phần tử.
- Projection lồng nhau tạo collection lồng nhau; cần helper khác nếu muốn flatten.
- Spring Framework 6.2+ hỗ trợ null-safe projection `?.!` cho collection nguồn null; safe navigation bên trong biểu thức con vẫn cần thiết nếu property của phần tử có thể null.
- Kết quả là collection mới nhưng các object tham chiếu bên trong không được deep-copy.
- Parse expression một lần, tái sử dụng với root object và context phù hợp.

## Tài liệu tham khảo

- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/6.2/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/6.2/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework API — Projection](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/expression/spel/ast/Projection.html)