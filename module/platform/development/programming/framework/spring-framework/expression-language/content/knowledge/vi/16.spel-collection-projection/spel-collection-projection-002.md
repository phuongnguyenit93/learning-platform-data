# Biến #this trong projection của SpEL

## 1. Projection và vai trò của #this

Spring Expression Language (SpEL) hỗ trợ collection projection để áp dụng một biểu thức con lên từng phần tử của một nguồn collection và tạo ra collection kết quả mới.

Cú pháp:

```text
source.![projectionExpression]
```

Trong projection, SpEL đánh giá `projectionExpression` lần lượt trên từng phần tử. Biến hệ thống `#this` luôn tham chiếu đối tượng hiện đang được đánh giá. Vì vậy, bên trong projection, `#this` chính là phần tử hiện tại.

Ví dụ, chuyển danh sách tên thành chữ hoa:

```java
List<String> names = List.of("Ada", "Grace", "Linus");
context.setVariable("names", names);

List<?> upperNames = parser.parseExpression(
        "#names.![#this.toUpperCase()]")
        .getValue(context, List.class);

// ["ADA", "GRACE", "LINUS"]
```

Mỗi lần projection chạy, `#this` trỏ đến một phần tử khác nhau: lần lượt là `"Ada"`, `"Grace"` và `"Linus"`. Method `toUpperCase()` được gọi trên phần tử hiện tại và kết quả của từng lần gọi được đưa vào collection mới.

Có thể bỏ `#this` khi truy cập trực tiếp property hoặc method của phần tử:

```text
#names.![toUpperCase()]
```

Tuy nhiên, viết tường minh `#this` giúp nhận biết rõ đối tượng nhận lời gọi, đặc biệt khi biểu thức có nhiều cấp object hoặc projection lồng nhau.

## 2. Phân biệt #this và #root

SpEL luôn cung cấp hai biến hệ thống:

| Biến | Ý nghĩa | Trong projection |
|---|---|---|
| `#this` | Đối tượng hiện tại đang được đánh giá; các tên không có tiền tố cũng được giải quyết trên đối tượng này. | Thay đổi theo từng phần tử được projection duyệt. |
| `#root` | Root context object ban đầu được truyền cho EvaluationContext hoặc `getValue()`. | Luôn giữ nguyên object gốc, không đổi theo phần tử. |

Ví dụ, root object là một Inventor có tên và danh sách phát minh. Ta muốn tạo câu mô tả cho từng phát minh:

```java
Inventor tesla = new Inventor("Nikola Tesla");
tesla.setInventions(
        "Telephone repeater",
        "Tesla coil transformer");

ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();

String expression =
        "#root.inventions.![#root.name + ' invented the ' + #this + '.']";

List<?> descriptions = parser.parseExpression(expression)
        .getValue(context, tesla, List.class);

// [
//   "Nikola Tesla invented the Telephone repeater.",
//   "Nikola Tesla invented the Tesla coil transformer."
// ]
```

Trong biểu thức:

- `#root.inventions` truy cập danh sách phát minh trên Inventor gốc.
- `#root.name` luôn lấy tên của Inventor gốc.
- `#this` trong projection lần lượt là từng chuỗi phát minh.
- Mỗi lần đánh giá tạo một câu mô tả mới.

Nếu thay `#root.name` bằng `#this.name`, biểu thức sẽ cố đọc property `name` trên phần tử hiện tại. Nhưng phần tử hiện tại ở đây là String phát minh, không phải Inventor, nên biểu thức không đúng với mô hình dữ liệu.

## 3. Truy cập property của phần tử hiện tại

Projection thường dùng để lấy một property từ từng object:

```java
List<Inventor> members = loadMembers();
context.setVariable("members", members);

List<?> names = parser.parseExpression(
        "#members.![#this.name]")
        .getValue(context, List.class);
```

Nếu mỗi Inventor có một PlaceOfBirth, có thể lấy thành phố sinh của tất cả thành viên:

```text
#members.![#this.placeOfBirth.city]
```

Dạng ngắn tương đương:

```text
#members.![placeOfBirth.city]
```

Trong projection, tên property không có tiền tố được giải quyết trên `#this`. Vì vậy, `placeOfBirth.city` và `#this.placeOfBirth.city` có cùng ý nghĩa khi biểu thức đang đánh giá một Inventor.

Có thể kết hợp property với method và phép tính:

```text
#products.![#this.code.toUpperCase()]
#products.![#this.price * 1.08]
#members.![#this.name + ' (' + #this.nationality + ')']
```

Kết quả mỗi phần tử là giá trị của expression con, không nhất thiết cùng kiểu với phần tử nguồn. Ví dụ, projection từ List<Product> có thể trả về List<String> nếu expression con lấy mã sản phẩm.

## 4. Projection trên array, Iterable và Map

Projection được hỗ trợ trên:

- Array Java.
- Các kiểu triển khai `java.lang.Iterable`, như List và Set.
- Map Java.

Với array hoặc Iterable, `#this` lần lượt là từng phần tử. Kết quả là một List chứa giá trị expression con tương ứng với từng phần tử.

Ví dụ với array số nguyên:

```java
int[] values = {2, 4, 6};
context.setVariable("values", values);

List<?> doubled = parser.parseExpression(
        "#values.![#this * 2]")
        .getValue(context, List.class);

// [4, 8, 12]
```

Với Map, SpEL đánh giá projection expression trên từng entry kiểu `java.util.Map.Entry`. Trong trường hợp này, `#this` là entry hiện tại, có thể truy cập `key` và `value`.

```java
Map<String, Integer> scores = Map.of(
        "Ada", 95,
        "Grace", 91);

context.setVariable("scores", scores);

List<?> labels = parser.parseExpression(
        "#scores.![#this.key + ': ' + #this.value]")
        .getValue(context, List.class);

// ["Ada: 95", "Grace: 91"] (thứ tự phụ thuộc Map)
```

Một projection trên Map trả về List các giá trị được tính từ mỗi entry, không trả về Map mới. Nếu cần giữ cặp key/value, hãy đưa key vào giá trị kết quả hoặc dùng selection khi mục tiêu là lọc các entry mà vẫn giữ cấu trúc Map.

## 5. #this trong projection lồng nhau

Một projection có thể chứa projection khác. Mỗi lần bước vào projection bên trong, `#this` chuyển sang phần tử hiện tại của collection bên trong.

Giả sử một Company có nhiều Department, mỗi Department có danh sách Employee. Muốn tạo danh sách tên nhân viên theo từng phòng ban:

```text
#root.departments.![#this.name + ': ' + #this.employees.![#this.name]]
```

Cách đánh giá:

1. Projection ngoài duyệt từng Department. Khi đó `#this` là Department hiện tại.
2. `#this.name` đọc tên phòng ban trước khi xử lý projection bên trong.
3. `#this.employees` lấy danh sách nhân viên của Department đó.
4. Projection bên trong duyệt danh sách nhân viên; trong projection này, `#this` là Employee hiện tại.
5. `#this.name` bên trong projection trong đọc tên Employee.

Kết quả là một List lồng nhau: mỗi phần tử ngoài tương ứng với một Department và chứa tên phòng ban cùng danh sách tên nhân viên của phòng ban đó.

Điểm quan trọng: `#this` không phải một biến cố định trỏ vào phần tử ngoài cùng. Nó đại diện cho context object hiện tại tại vị trí expression đang được đánh giá. Khi đi vào projection lồng nhau, `#this` thay đổi theo collection trong.

Nếu cần truy cập root object từ bên trong projection lồng nhau, dùng `#root`. Nếu cần dùng lại một object cha không phải root sau khi đã đi vào projection con, hãy thiết kế biểu thức để lấy giá trị cha trước khi chuyển context, hoặc đưa giá trị cần thiết vào một variable có tên trong EvaluationContext. Không giả định `#this` vẫn giữ object cha bên ngoài.

## 6. Kết hợp #this với biến đã đăng ký

Biến trong EvaluationContext dùng cú pháp `#variableName`. Chúng hữu ích khi projection cần so sánh phần tử hiện tại với một giá trị bên ngoài collection.

Ví dụ, chỉ lấy tên các thành viên có quốc tịch trùng với biến `#targetNationality`:

```java
context.setVariable("members", loadMembers());
context.setVariable("targetNationality", "Serbian");

List<?> matchingNames = parser.parseExpression(
        "#members.?[#this.nationality == #targetNationality].![#this.name]")
        .getValue(context, List.class);
```

Trong biểu thức này:

- `#members` là collection nguồn.
- Trong selection, `#this` là từng Inventor đang được kiểm tra.
- `#targetNationality` là biến cố định lấy từ EvaluationContext.
- Trong projection sau selection, `#this` là từng Inventor được giữ lại.
- `#this.name` tạo giá trị tên cho mỗi Inventor.

Biến có tên giúp tránh nhầm lẫn giữa root object, phần tử hiện tại và dữ liệu tham chiếu bên ngoài. Tên biến và tên function trong EvaluationContext dùng chung namespace, vì vậy tránh đặt trùng tên.

## 7. Projection khác Selection

Projection và selection đều duyệt collection nhưng thực hiện hai nhiệm vụ khác nhau:

| Đặc điểm | Projection | Selection |
|---|---|---|
| Cú pháp | `.![expression]` | `.?[predicate]` |
| Mục tiêu | Biến đổi từng phần tử thành một giá trị. | Lọc và giữ lại phần tử thỏa điều kiện. |
| Biểu thức con | Có thể trả về String, số, object, null hoặc kiểu khác. | Cần trả về Boolean. |
| Kiểu kết quả | List các giá trị expression con. | Collection con; với Map, giữ các entry được chọn. |

Ví dụ projection lấy tên:

```text
#members.![#this.name]
```

Ví dụ selection lấy những người có quốc tịch Serbia:

```text
#members.?[#this.nationality == 'Serbian']
```

Có thể kết hợp selection rồi projection:

```text
#members.?[#this.nationality == 'Serbian'].![#this.name]
```

Expression đầu tiên lọc thành viên; expression thứ hai chuyển mỗi thành viên được giữ lại thành tên. Kết quả cuối cùng là List<String> theo thứ tự của các phần tử đã chọn.

Projection không loại bỏ phần tử chỉ vì expression con trả về null. Nếu nguồn có ba phần tử và expression con trả về lần lượt `"A"`, null và `"C"`, kết quả vẫn có ba vị trí. Nếu muốn loại bỏ phần tử, hãy selection trước hoặc lọc kết quả trong Java.

## 8. Null-safe projection và property null

Nếu collection nguồn có thể null, có thể dùng null-safe projection:

```text
#members?.![#this.name]
```

Khi `members` null, kết quả của phép projection null-safe là null. Khi `members` là collection rỗng, kết quả là collection rỗng. Đây là hai tình huống khác nhau, nên caller cần xử lý đúng.

Null-safe projection chỉ bảo vệ collection nguồn. Nếu một phần tử có thể null hoặc property lồng nhau có thể null, cần dùng safe navigation ở đúng đoạn:

```text
#members?.![#this?.placeOfBirth?.city]
```

Trong ví dụ:

- `#members?.!` bảo vệ collection nguồn.
- `#this?.placeOfBirth` bảo vệ trường hợp phần tử hiện tại null.
- `?.city` bảo vệ trường hợp placeOfBirth null.

Safe navigation không tự làm an toàn mọi phần còn lại của một compound expression. Hãy đặt `?.` tại từng đoạn mà object trung gian có thể null.

Nếu projection expression trả về null cho một phần tử, giá trị null đó vẫn là một phần tử trong collection kết quả. Null-safe projection không có nghĩa là lọc bỏ các giá trị null.

## 9. Kiểm thử #this trong projection bằng Java

Ví dụ sau xác nhận #this nhận từng phần tử và tạo đúng kết quả theo thứ tự:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class ProjectionThisTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void usesThisForEachCurrentElement() {
        var context = new StandardEvaluationContext();
        context.setVariable("names", List.of("Ada", "Grace", "Linus"));

        List<?> result = parser.parseExpression(
                "#names.![#this.toUpperCase()]")
                .getValue(context, List.class);

        assertEquals(List.of("ADA", "GRACE", "LINUS"), result);
    }

    @Test
    void keepsNullProjectionResultsAsElements() {
        var context = new StandardEvaluationContext();
        context.setVariable("names", List.of("Ada", "", "Linus"));

        List<?> result = parser.parseExpression(
                "#names.![#this == '' ? null : #this.toUpperCase()]")
                .getValue(context, List.class);

        assertEquals(3, result.size());
        assertEquals("ADA", result.get(0));
        assertEquals(null, result.get(1));
        assertEquals("LINUS", result.get(2));
    }
}
```

Test đầu tiên xác nhận projection gọi method trên từng String hiện tại. Test thứ hai xác nhận projection vẫn giữ vị trí của phần tử có expression trả về null.

Có thể kiểm thử root và current object cùng lúc:

```java
@Test
void keepsRootWhileThisChanges() {
    Inventor tesla = new Inventor("Nikola Tesla");
    tesla.setInventions("Telephone repeater", "Tesla coil transformer");

    var context = new StandardEvaluationContext();

    List<?> result = parser.parseExpression(
            "#root.inventions.![#root.name + ' invented ' + #this]")
            .getValue(context, tesla, List.class);

    assertEquals(
            List.of(
                    "Nikola Tesla invented Telephone repeater",
                    "Nikola Tesla invented Tesla coil transformer"),
            result);
}
```

Ở đây, #root giữ Inventor còn #this thay đổi theo từng invention. Đây là cách kiểm thử trực tiếp sự khác nhau giữa hai biến hệ thống.

## 10. Thứ tự và kiểu kết quả

Projection tạo một List chứa kết quả của expression con cho từng phần tử nguồn:

- Với array và List, kết quả đi theo thứ tự phần tử nguồn.
- Với các Iterable khác, thứ tự phụ thuộc iterator của collection.
- Với Map, projection duyệt các entry và tạo List; thứ tự kết quả phụ thuộc thứ tự iteration của Map.
- Nếu expression con trả về null, null được giữ trong List kết quả.
- Kiểu phần tử kết quả được quyết định bởi expression con; projection không tự khai báo generic type.

Ví dụ từ List<Product> sang List<String>:

```text
#products.![#this.code]
```

Ví dụ từ List<Product> sang List<BigDecimal>:

```text
#products.![#this.price]
```

Ví dụ từ Map sang List<String>:

```text
#scores.![#this.key + '=' + #this.value]
```

Khi lấy kết quả bằng Java, `List.class` chỉ mô tả kiểu collection ngoài cùng. Nếu caller cần kiểu generic cụ thể, hãy kiểm soát kiểu của expression con và kiểm tra dữ liệu trả về.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `#this.name` không tìm thấy property | Phần tử hiện tại không phải kiểu có property name. | Kiểm tra kiểu phần tử nguồn và vị trí expression đang chạy. |
| Dùng nhầm #root thay cho #this | #root luôn là root context object, không phải phần tử hiện tại. | Dùng #this cho phần tử đang projection. |
| Dùng nhầm #this để truy cập root | #this đã chuyển sang phần tử hiện tại. | Dùng #root cho object gốc. |
| Projection lồng nhau đọc sai name | #this đổi theo từng cấp projection. | Xác định rõ projection ngoài và projection trong; dùng #root cho root và đánh giá giá trị cha trước khi vào projection con. |
| Projection trả List thay vì Map | Projection trên Map tạo List từ các entry. | Đưa key vào giá trị projection hoặc dùng selection nếu cần giữ Map. |
| Kết quả có null dù mong muốn bỏ phần tử | Projection giữ kết quả null của expression con. | Selection/lọc trước khi projection hoặc lọc kết quả sau đó. |
| Null-safe projection vẫn phát sinh lỗi | Property bên trong phần tử null hoặc object trung gian null. | Dùng safe navigation ở từng đoạn có thể null. |
| Kết quả sai thứ tự | Nguồn là collection không bảo đảm thứ tự iteration. | Dùng nguồn có thứ tự hoặc sắp xếp trước khi projection. |
| Expression không truy cập được biến | Chưa gọi setVariable hoặc tên biến sai. | Đăng ký biến trong EvaluationContext và dùng đúng cú pháp #name. |
| Kết quả không đúng kiểu mong đợi | Expression con trả về kiểu khác hoặc dữ liệu không đồng nhất. | Kiểm tra kiểu từng giá trị và dùng chuyển đổi rõ ràng trong Java khi cần. |

## 12. Quy trình đọc và kiểm thử #this

1. Xác định collection nguồn và kiểu phần tử của nó.
2. Xác định root context object được truyền vào khi đánh giá.
3. Trong projection, xác định #this sẽ là phần tử nào tại từng cấp.
4. Dùng #root khi cần truy cập object gốc bất kể projection đang ở cấp nào.
5. Với projection lồng nhau, ghi rõ thời điểm #this chuyển sang phần tử của collection trong.
6. Kiểm tra property và method mà expression con truy cập có tồn tại trên kiểu phần tử hiện tại.
7. Kiểm tra collection rỗng, phần tử null và property lồng nhau null.
8. Kiểm tra kết quả giữ nguyên số vị trí khi expression con trả về null.
9. Kiểm tra thứ tự và kiểu của List kết quả, nhất là khi nguồn là Set hoặc Map.
10. Dùng test với giá trị đầu ra khác nhau để chứng minh #this đang trỏ đúng phần tử.

## 13. Ghi nhớ

- Projection dùng cú pháp `.![projectionExpression]` và tạo List kết quả từ việc đánh giá expression con trên từng phần tử.
- `#this` là current evaluation object; trong projection, nó là phần tử đang được xử lý.
- `#root` luôn là root context object ban đầu và không thay đổi theo projection.
- Có thể dùng #root và #this cùng lúc để kết hợp dữ liệu gốc với phần tử hiện tại.
- Trong projection lồng nhau, #this chuyển sang phần tử của collection bên trong.
- Projection trên Map đánh giá từng Map.Entry và trả về List; key/value truy cập qua property tương ứng.
- Projection giữ null nếu expression con trả về null; nó không phải thao tác filter.
- Null-safe projection dùng `?.!`; vẫn cần safe navigation cho property hoặc object trung gian có thể null.
- Thứ tự kết quả phụ thuộc thứ tự duyệt của nguồn.
- Kiểm thử riêng root, current element, projection lồng nhau, null và kiểu kết quả.

## Tài liệu tham khảo

- [Spring Framework Reference — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Safe Navigation and Safe Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Projection AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Projection.html)
