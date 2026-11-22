# Giữ kiểu kết quả và thứ tự phần tử sau projection trong Spring Expression Language

Spring Expression Language (SpEL) hỗ trợ projection để biến đổi từng phần tử của một collection thành một giá trị mới. Cú pháp projection là \`![...]\`. Biểu thức bên trong được đánh giá lần lượt trên từng phần tử nguồn, và các giá trị thu được được gom vào một collection kết quả mới.

Khi dùng projection, cần hiểu rõ hai đặc điểm:

- **Kiểu kết quả:** projection tạo một danh sách kết quả (List), không giữ nguyên kiểu collection ban đầu như Set hoặc Map.
- **Thứ tự:** các giá trị được tạo theo thứ tự duyệt phần tử nguồn. Với List và array, thứ tự vị trí được giữ; với Map hoặc Set, thứ tự phụ thuộc vào quy tắc iteration của implementation đang dùng.

Nắm được hai đặc điểm này giúp dự đoán chính xác kiểu dữ liệu, vị trí phần tử và hành vi khi kết quả được truyền sang bước xử lý tiếp theo.

## 1. Projection là gì?

Projection là thao tác ánh xạ một biểu thức lên từng phần tử của collection. Cú pháp tổng quát:

~~~spel
collection.![expression]
~~~

Dấu chấm truy cập thao tác trên collection; dấu chấm than mở đầu projection; phần trong ngoặc vuông là biểu thức được đánh giá trên mỗi phần tử.

Ví dụ, nếu có danh sách tên:

~~~spel
#names.![#this.toUpperCase()]
~~~

SpEL lần lượt lấy từng tên, gọi \`toUpperCase()\`, rồi đưa kết quả vào danh sách mới.

Nếu nguồn là:

~~~text
["ana", "minh", "linh"]
~~~

kết quả là:

~~~text
["ANA", "MINH", "LINH"]
~~~

Projection không sửa từng phần tử nguồn chỉ vì nó tạo ra collection kết quả. Tuy nhiên, nếu biểu thức bên trong projection gọi phương thức có tác dụng phụ hoặc thực hiện phép gán, những thao tác đó vẫn có thể thay đổi object được tham chiếu.

## 2. Phân biệt Projection và Selection

Hai thao tác có hình thức gần giống nhưng mục tiêu khác nhau:

| Thao tác | Cú pháp | Mục đích | Kết quả |
|---|---|---|---|
| Selection | \`?[condition]\` | Giữ lại phần tử thỏa điều kiện | Collection con |
| Projection | \`![expression]\` | Biến đổi từng phần tử thành giá trị mới | List kết quả |

Ví dụ với danh sách số:

~~~spel
#numbers.?[#this > 2]
#numbers.![#this * 10]
~~~

Nếu nguồn là \`[1, 2, 3, 4]\`:

- Selection trả về các phần tử thỏa điều kiện: \`[3, 4]\`.
- Projection tính biểu thức cho từng phần tử: \`[10, 20, 30, 40]\`.

Selection có thể làm giảm số phần tử vì nó lọc. Projection thông thường tạo một kết quả cho mỗi phần tử đầu vào, kể cả khi hai phần tử tạo ra cùng một giá trị.

## 3. Kiểu kết quả của Projection

Projection tạo một danh sách kết quả mới. Điều này có nghĩa kiểu collection nguồn không được giữ nguyên.

| Kiểu nguồn | Kết quả projection |
|---|---|
| List | List chứa giá trị được chiếu |
| Set / Iterable | List chứa giá trị được chiếu |
| Array | List chứa giá trị được chiếu |
| Map | List chứa kết quả đánh giá trên từng entry |

Ví dụ, projection trên Set không trả về Set chỉ vì nguồn là Set. Kết quả là List, do đó hai phần tử nguồn khác nhau có thể tạo ra hai giá trị bằng nhau và cả hai vẫn xuất hiện trong kết quả.

Tương tự, projection trên Map không trả về Map giữ nguyên các khóa. Kết quả là một List các giá trị do biểu thức projection tạo ra. Nếu muốn giữ khóa, cần đưa khóa vào chính biểu thức projection hoặc tạo cấu trúc map mong muốn bằng logic phù hợp.

Trong Java, nên nhận kết quả dưới dạng List khi biết expression sử dụng projection:

~~~java
Object value = expression.getValue(context);

if (value instanceof List<?> projected) {
    // Xử lý danh sách kết quả.
}
~~~

Kiểu phần tử cụ thể phụ thuộc vào biểu thức projection và dữ liệu runtime. API \`getValue()\` trả về Object, vì vậy mã Java có thể kiểm tra hoặc chuyển đổi kết quả theo hợp đồng ứng dụng.

## 4. Projection trên List giữ thứ tự phần tử

List có thứ tự duyệt xác định. Projection đánh giá các phần tử theo thứ tự đó và đặt kết quả tương ứng vào cùng vị trí trong danh sách mới.

Ví dụ:

~~~java
List<String> names =
    Arrays.asList("ana", "minh", "linh");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("names", names);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#names.![#this.toUpperCase()]");

List<?> result = (List<?>) expression.getValue(context);
System.out.println(result);
~~~

Kết quả:

~~~text
[ANA, MINH, LINH]
~~~

Ánh xạ vị trí:

| Vị trí nguồn | Giá trị nguồn | Giá trị sau projection |
|---:|---|---|
| 0 | ana | ANA |
| 1 | minh | MINH |
| 2 | linh | LINH |

Phần tử ở vị trí 0 của nguồn tạo ra phần tử ở vị trí 0 của kết quả; quy tắc này tiếp tục cho các vị trí sau.

Nếu biểu thức projection tạo ra giá trị trùng nhau, các giá trị trùng vẫn được giữ:

~~~spel
#numbers.![#this % 2]
~~~

Với nguồn \`[1, 3, 2, 4]\`, kết quả là \`[1, 1, 0, 0]\`. Projection không tự loại bỏ phần tử trùng lặp.

## 5. Projection trên Array

SpEL cũng hỗ trợ projection trên array. Kết quả vẫn là List và thứ tự được giữ theo thứ tự chỉ số của array.

Ví dụ:

~~~java
Integer[] scores = {80, 95, 70};

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("scores", scores);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#scores.![#this + 5]");

List<?> adjusted =
    (List<?>) expression.getValue(context);
~~~

Kết quả:

~~~text
[85, 100, 75]
~~~

Các phần tử được xử lý theo chỉ số 0, 1, 2. Kết quả không phải array Integer mới mà là List chứa các giá trị được chiếu.

Nếu ứng dụng cần array làm đầu ra, có thể chuyển List kết quả sang array trong Java sau khi đánh giá.

## 6. Projection trên Set và các Iterable khác

Projection hoạt động trên các đối tượng Iterable. Với Set, thứ tự kết quả đi theo thứ tự mà Set cung cấp khi duyệt.

Điều này có ý nghĩa khác nhau tùy implementation:

- LinkedHashSet giữ thứ tự chèn, vì vậy projection đi theo thứ tự chèn.
- TreeSet duyệt theo thứ tự do comparator hoặc thứ tự tự nhiên quy định.
- HashSet không cam kết một thứ tự duyệt ổn định; không nên dựa vào vị trí kết quả cố định giữa các lần chạy.

Ví dụ:

~~~java
Set<String> tags = new LinkedHashSet<>();
tags.add("backend");
tags.add("java");
tags.add("spring");

context.setVariable("tags", tags);

Expression expression =
    parser.parseExpression("#tags.![#this.toUpperCase()]");

List<?> result =
    (List<?>) expression.getValue(context);
~~~

Kết quả theo thứ tự duyệt của LinkedHashSet:

~~~text
[BACKEND, JAVA, SPRING]
~~~

Nguồn là Set nhưng kết quả là List. Nếu thứ tự nghiệp vụ quan trọng, hãy chọn implementation nguồn có thứ tự được xác định rõ hoặc sắp xếp dữ liệu trước khi projection.

## 7. Projection trên Map: kết quả là List các entry projection

Với Map, SpEL đánh giá biểu thức projection trên từng entry. Đối tượng hiện tại trong mỗi lượt là một \`Map.Entry\`, vì vậy có thể truy cập \`key\` và \`value\`.

Ví dụ:

~~~java
Map<String, Integer> prices = new LinkedHashMap<>();
prices.put("keyboard", 750);
prices.put("mouse", 250);
prices.put("monitor", 3000);

context.setVariable("prices", prices);
~~~

Lấy danh sách khóa:

~~~spel
#prices.![key]
~~~

Kết quả:

~~~text
[keyboard, mouse, monitor]
~~~

Lấy danh sách giá trị:

~~~spel
#prices.![value]
~~~

Kết quả:

~~~text
[750, 250, 3000]
~~~

Tính giá sau khi tăng 10 phần trăm:

~~~spel
#prices.![value * 1.10]
~~~

Kết quả là List các giá trị được tính từ từng entry.

Vì projection trên Map trả về List, các khóa không tự động được giữ trong kết quả. Nếu cần cả khóa và giá trị, biểu thức có thể tạo một object trung gian chứa hai thành phần hoặc ứng dụng có thể xử lý entry trong Java để xây dựng Map đích.

## 8. Thứ tự projection trên Map phụ thuộc iteration order

Projection trên Map duyệt các entry theo thứ tự mà \`entrySet()\` của Map cung cấp. SpEL giữ thứ tự duyệt đó trong List kết quả.

| Map implementation | Thứ tự duyệt thường gặp | Thứ tự trong List projection |
|---|---|---|
| LinkedHashMap | Thứ tự chèn | Theo thứ tự chèn |
| TreeMap | Thứ tự khóa theo comparator | Theo thứ tự khóa |
| HashMap | Không được bảo đảm ổn định | Theo iteration order của lần duyệt |

Ví dụ:

~~~java
Map<String, Integer> values = new LinkedHashMap<>();
values.put("first", 10);
values.put("second", 20);
values.put("third", 30);

context.setVariable("values", values);

Expression expression =
    parser.parseExpression("#values.![value * 2]");

List<?> result =
    (List<?>) expression.getValue(context);
~~~

Kết quả:

~~~text
[20, 40, 60]
~~~

Nếu đổi LinkedHashMap thành HashMap, không nên giả định thứ tự luôn là \`[20, 40, 60]\` theo đúng thứ tự chèn. Giá trị vẫn được chiếu theo từng entry, nhưng thứ tự phụ thuộc vào iteration order của implementation.

Khi thứ tự kết quả là một phần của hợp đồng nghiệp vụ, hãy chọn loại Map có thứ tự xác định.

## 9. Projection tạo một kết quả cho mỗi phần tử

Projection thông thường không lọc phần tử. Mỗi phần tử đầu vào được dùng để đánh giá biểu thức projection và tạo một phần tử đầu ra.

Ví dụ:

~~~spel
#names.![#this.length()]
~~~

Với nguồn \`["Ana", "Minh", "Linh"]\`, kết quả là \`[3, 4, 4]\`.

Các đặc điểm cần nhớ:

- Số phần tử kết quả thường bằng số phần tử nguồn.
- Hai đầu vào khác nhau có thể tạo cùng một giá trị đầu ra; cả hai kết quả vẫn được giữ.
- Nếu biểu thức projection trả về null cho một phần tử, vị trí tương ứng trong List kết quả có thể chứa null.
- Projection không tự flatten collection lồng nhau.

Ví dụ projection trả về collection:

~~~spel
#groups.![members]
~~~

Mỗi phần tử đầu ra có thể là một collection members. Kết quả khi đó là List chứa các collection con, không phải một collection đã được nối phẳng.

Nếu cần loại bỏ phần tử theo điều kiện, hãy dùng selection hoặc kết hợp các thao tác phù hợp.

## 10. Giá trị null trong projection

Cần phân biệt collection nguồn null, phần tử nguồn null và giá trị projection null.

### Collection nguồn null

Projection thông thường trên collection null không thể duyệt phần tử. Từ Spring Framework 6.2, có thể dùng null-safe projection:

~~~spel
#products?.![name]
~~~

Nếu products null, biểu thức trả về null. Cú pháp null-safe projection là \`?.![]\`, khác với null-safe indexer \`?.[]\` và null-safe selection \`?.?[]\`.

### Phần tử nguồn null

Null-safe projection không tự bảo vệ từng phần tử. Nếu collection chứa null và biểu thức truy cập property trực tiếp, evaluation có thể thất bại.

Có thể dùng null-safe navigation trong biểu thức con:

~~~spel
#products.![#this?.name]
~~~

Khi phần tử hiện tại null, biểu thức con trả về null; vị trí đó được giữ trong danh sách kết quả.

### Biểu thức projection trả về null

Nếu phần tử tồn tại nhưng thuộc tính được chiếu có giá trị null, projection vẫn có thể đưa null vào kết quả. Projection không tự loại bỏ những giá trị null này.

## 11. Phân biệt projection với selection và thao tác sắp xếp

Projection và selection đều tạo collection kết quả nhưng có mục đích khác nhau:

| Thao tác | Cú pháp | Hành vi | Số lượng phần tử |
|---|---|---|---|
| Projection | \`![expression]\` | Biến đổi mỗi phần tử | Một kết quả cho mỗi phần tử được duyệt |
| Selection | \`?[condition]\` | Giữ phần tử thỏa điều kiện | Có thể ít hơn nguồn |
| First selection | \`^[condition]\` | Lấy phần tử phù hợp đầu tiên | Tối đa một |
| Last selection | \`$[condition]\` | Lấy phần tử phù hợp cuối cùng | Tối đa một |

Projection không phải là thao tác sắp xếp. Nó giữ thứ tự duyệt của nguồn, nhưng không tự sắp xếp theo giá trị mới.

Nếu cần sắp xếp, hãy thực hiện thao tác sort phù hợp trong Java hoặc cung cấp collection đã có thứ tự trước khi projection.

## 12. Kiểu kết quả và cách nhận trong Java

Projection tạo List mới, bất kể nguồn là List, Set, array hay Map. Kiểu phần tử trong List phụ thuộc vào biểu thức projection.

Ví dụ:

~~~java
Expression expression =
    parser.parseExpression("#products.![name]");

Object value = expression.getValue(context);

if (value instanceof List<?> names) {
    for (Object name : names) {
        System.out.println(name);
    }
}
~~~

Nếu biết kiểu kết quả mong đợi, có thể khai báo kiểu trong mã Java sau khi kiểm tra hợp đồng dữ liệu. Java generic không được SpEL bảo đảm tự động chỉ từ cú pháp expression; \`getValue()\` tổng quát trả về Object.

Đối với một biểu thức projection trên Map, đừng ép kết quả thành Map chỉ vì nguồn là Map. Kết quả projection là List các giá trị được tạo từ entry.

## 13. Ví dụ hoàn chỉnh: giữ thứ tự và kiểu kết quả

Giả sử ứng dụng có các Product và muốn tạo danh sách nhãn theo thứ tự ban đầu:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Chuẩn bị dữ liệu:

~~~java
List<Product> products = Arrays.asList(
    new Product("Keyboard", new BigDecimal("750000")),
    new Product("Mouse", new BigDecimal("250000")),
    new Product("Monitor", new BigDecimal("3000000"))
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("products", products);
~~~

Projection:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#products.![name + ' - ' + price]"
);

List<?> labels =
    (List<?>) expression.getValue(context);
~~~

Kết quả theo đúng thứ tự nguồn:

~~~text
[
  "Keyboard - 750000",
  "Mouse - 250000",
  "Monitor - 3000000"
]
~~~

Nguồn là List nên thứ tự phần tử được giữ theo index. Kết quả là List mới chứa String, còn các Product nguồn vẫn là những object ban đầu.

## 14. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Projection giữ nguyên kiểu collection nguồn.**  
Projection tạo List mới. Set, array hoặc Map không làm cho kết quả tự động trở thành cùng kiểu nguồn.

**Nhầm lẫn 2: Projection tự sắp xếp kết quả.**  
Projection giữ thứ tự duyệt nguồn. Muốn sắp xếp phải thực hiện riêng.

**Nhầm lẫn 3: Projection loại bỏ giá trị trùng hoặc null.**  
Projection không tự loại bỏ chúng. Mỗi phần tử nguồn tạo một kết quả tương ứng; kết quả null và giá trị trùng có thể được giữ.

**Nhầm lẫn 4: Projection trên Map trả về Map.**  
Projection trên Map đánh giá từng Map.Entry và tạo List kết quả. Khóa chỉ được giữ nếu biểu thức chiếu khóa hoặc một cấu trúc chứa khóa.

**Nhầm lẫn 5: Null-safe projection bảo vệ cả phần tử null.**  
Null-safe projection bảo vệ collection nguồn khi chính collection null. Phần tử null cần được xử lý trong biểu thức con.

## 15. Ghi nhớ

- Projection dùng cú pháp \`collection.![expression]\` để biến đổi từng phần tử.
- Projection trên List, Set, Iterable, array hoặc Map tạo một List kết quả.
- Với List và array, thứ tự nguồn được giữ; với Map và Set, thứ tự kết quả theo iteration order của implementation.
- Projection tạo một kết quả cho mỗi phần tử hoặc entry được duyệt; giá trị trùng và null không tự bị loại bỏ.
- Projection không tự flatten collection lồng nhau và không sắp xếp kết quả.
- Với Map, biểu thức projection được đánh giá trên từng entry; có thể truy cập key và value.
- Null-safe projection dùng \`?.![]\` từ Spring Framework 6.2, còn null-safe selection dùng \`?.?[]\`.
- Cần phân biệt collection null, phần tử null và giá trị projection null.
- Khi nhận kết quả trong Java, hãy nhớ \`getValue()\` trả về Object và projection tạo List.

Khi thiết kế projection, hãy xác định kiểu nguồn, thứ tự iteration, biểu thức tạo giá trị cho từng phần tử và kiểu List mà mã Java sẽ nhận. Điều đó giúp kết quả ổn định và tránh giả định sai về kiểu hoặc thứ tự dữ liệu.
