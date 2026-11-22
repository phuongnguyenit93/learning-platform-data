# Inline list được tối ưu thành constant collection khi có thể trong SpEL

## Mục tiêu

SpEL cho phép khai báo một danh sách ngay trong biểu thức bằng cú pháp `{...}`. Danh sách inline có thể chứa literal, biểu thức, hoặc các danh sách inline lồng nhau. Khi toàn bộ phần tử của danh sách là hằng số, SpEL có thể tạo một constant list và tái sử dụng giá trị đó giữa các lần đánh giá, thay vì tạo một danh sách mới mỗi lần.

Đây là tối ưu ở cấp biểu thức: nó giảm công việc dựng collection và lượng object rác được tạo ra khi cùng một expression được đánh giá nhiều lần. Muốn tận dụng tối ưu này, cần hiểu phần tử nào được xem là constant, phần tử nào phụ thuộc runtime và khi nào nên sao chép kết quả để làm việc với một collection có thể thay đổi.

## 1. Cú pháp inline list

Inline list dùng dấu ngoặc nhọn `{}` và phân tách các phần tử bằng dấu phẩy:

```spel
{1, 2, 3, 4}
{'red', 'green', 'blue'}
{true, false, null}
```

Khi đánh giá, SpEL trả về một đối tượng Java `List`. `{}` biểu diễn một danh sách rỗng.

Ví dụ Java:

```java
ExpressionParser parser = new SpelExpressionParser();

List<?> numbers = parser.parseExpression("{1, 2, 3, 4}")
        .getValue(List.class);

List<?> colors = parser.parseExpression("{'red', 'green', 'blue'}")
        .getValue(List.class);
```

Inline list phù hợp khi danh sách là một phần của rule, cấu hình hoặc biểu thức. Nếu dữ liệu đã nằm trong một property hoặc collection của ứng dụng, có thể truy cập trực tiếp property đó thay vì chép lại dữ liệu vào expression.

## 2. Danh sách lồng nhau

Phần tử của inline list có thể là một inline list khác. Cú pháp này tạo ra cấu trúc nhiều cấp:

```spel
{{'a', 'b'}, {'x', 'y'}}
```

Kết quả là một `List` có hai phần tử, mỗi phần tử là một `List` gồm hai chuỗi. Ví dụ:

```java
Expression expression = parser.parseExpression("{{'a', 'b'}, {'x', 'y'}}");
List<?> matrix = expression.getValue(List.class);

List<?> firstRow = (List<?>) matrix.get(0);
String firstValue = (String) firstRow.get(0); // "a"
```

Nested list hữu ích cho các cấu hình nhỏ có dạng nhóm, bảng hoặc ma trận. Nếu cấu trúc lớn, thay đổi thường xuyên hoặc cần kiểm tra kiểu dữ liệu chặt chẽ, nên quản lý dữ liệu trong Java configuration hoặc object chuyên biệt.

## 3. Khi nào SpEL tạo constant list?

SpEL kiểm tra cấu trúc các phần tử của inline list. Nếu mọi phần tử đều là constant, hoặc là những inline list lồng nhau mà bản thân chúng cũng chỉ chứa constant, SpEL có thể tạo một constant list đại diện cho node biểu thức.

Ví dụ các danh sách có thể được xem là constant:

```spel
{1, 2, 3}
{'READ', 'WRITE', 'DELETE'}
{true, false, null}
{{'a', 'b'}, {'x', 'y'}}
```

Trong các ví dụ này, giá trị của từng phần tử không phụ thuộc root object, biến, method hoặc dữ liệu runtime. Các danh sách lồng nhau cũng chỉ chứa giá trị cố định, nên toàn bộ cấu trúc có thể được tạo như một constant value.

Constant list được tạo một cách lazy ở lần đánh giá đầu tiên cần giá trị đó, sau đó được giữ lại trong node biểu thức để các lần `getValue()` tiếp theo tái sử dụng. Nhờ vậy, SpEL tránh dựng lại cùng một collection ở mỗi lần đánh giá.

Đây là tối ưu của AST/evaluation trong SpEL, không đồng nghĩa với việc phải bật SpEL bytecode compiler. Constant-list optimization có thể được áp dụng khi expression được đánh giá theo cơ chế thông dịch thông thường.

## 4. Khi nào danh sách không phải constant?

Nếu một phần tử phụ thuộc vào dữ liệu runtime, toàn bộ inline list chứa phần tử đó không thể được xem là constant. SpEL cần đánh giá phần tử động và tạo kết quả danh sách phù hợp với lần đánh giá hiện tại.

Ví dụ:

```spel
{#primary, #secondary}
{1, #limit, 3}
{customer.name, 'UNKNOWN'}
{#service.nextId(), #service.nextId()}
```

Các biểu thức trên sử dụng biến, property của object hoặc lời gọi method. Kết quả có thể thay đổi theo evaluation context hoặc theo trạng thái của object/method, vì vậy không thể cache toàn bộ list như một constant.

Ví dụ với biến:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("{#primary, #secondary}");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("primary", "READ");
context.setVariable("secondary", "WRITE");

List<?> first = expression.getValue(context, List.class);

context.setVariable("primary", "VIEW");
List<?> second = expression.getValue(context, List.class);
```

Lần đánh giá đầu tạo danh sách có `READ` và `WRITE`; lần sau lấy giá trị mới từ context và tạo kết quả có `VIEW` và `WRITE`. Expression đã parse có thể tái sử dụng, nhưng các giá trị động vẫn được đánh giá theo context của từng lần gọi.

## 5. Danh sách lồng nhau có phần tử động

Quy tắc constant áp dụng đệ quy cho cấu trúc lồng nhau. Nếu tất cả phần tử của mỗi list con đều constant, list cha cũng có thể constant. Chỉ cần một nhánh chứa biểu thức runtime thì list cha không còn là constant toàn phần.

```spel
{{'a', 'b'}, {'x', 'y'}}
```

Toàn bộ cấu trúc là constant.

```spel
{{'a', #currentValue}, {'x', 'y'}}
```

List con đầu tiên có biến `#currentValue`, nên nó không phải constant. List ngoài cũng không thể được cache như một constant list hoàn chỉnh.

Điều này quan trọng khi xây dựng các bảng cấu hình nhiều cấp: một literal nhỏ được trộn với biến hoặc property động cũng khiến toàn bộ list chứa nó phải được đánh giá lại.

## 6. Dùng inline list trong Java và Spring configuration

Trong Java, parse expression một lần rồi đánh giá khi cần:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression permissionsExpression = parser.parseExpression(
        "{'READ', 'WRITE', 'DELETE'}");

List<?> permissions = permissionsExpression.getValue(List.class);
```

Trong Spring, inline list cũng có thể xuất hiện trong `@Value`. Vì `@Value` dùng cặp `#{...}` để bao quanh SpEL, dấu ngoặc nhọn của inline list tạo thành một cặp lồng nhau:

```java
@Component
public class AccessConfiguration {

    @Value("#{{'READ', 'WRITE', 'DELETE'}}")
    private List<String> permissions;
}
```

Ở đây cặp ngoài `#{...}` là delimiter của SpEL trong annotation; cặp trong `{...}` là cú pháp inline list. Kết quả được chuyển vào property `permissions` theo cơ chế type conversion của Spring.

Nếu expression cần root object hoặc biến, hãy cung cấp chúng qua `EvaluationContext` khi dùng API SpEL trực tiếp. Không nối dữ liệu người dùng vào source expression để tạo danh sách; truyền dữ liệu qua biến hoặc property có kiểu rõ ràng.

## 7. Constant list và việc thay đổi collection

Constant list là giá trị được SpEL cache và tái sử dụng cho cùng node expression. Vì thế, không nên xem kết quả constant list như một collection mới, độc lập cho mỗi lần gọi `getValue()`.

Đặc biệt, không nên thay đổi nội dung danh sách trả về từ một constant expression. Nếu caller thêm, xóa hoặc thay phần tử trên object được tái sử dụng, các lần đánh giá sau có thể quan sát thấy trạng thái đã bị thay đổi. API cũng không nên phụ thuộc vào việc collection đó có cho phép mutation hay không.

Nếu cần một danh sách mutable để xử lý riêng, hãy tạo bản sao ở phía Java:

```java
Expression expression = parser.parseExpression("{'READ', 'WRITE'}");
List<?> evaluated = expression.getValue(List.class);

List<Object> mutableCopy = new ArrayList<>(evaluated);
mutableCopy.add("ADMIN");
```

`mutableCopy` là collection mới do ứng dụng sở hữu; việc thay đổi nó không làm thay đổi constant value được giữ trong expression.

Với inline list có phần tử động, mỗi lần đánh giá sẽ tạo kết quả theo các giá trị runtime hiện tại. Dù vậy, nếu cần chỉnh sửa danh sách, vẫn nên xác định rõ ownership và tạo bản sao khi danh sách không thuộc quyền sở hữu của caller.

## 8. Constant list không phải immutable domain model

Từ “constant” ở đây mô tả việc SpEL nhận diện và cache giá trị của node biểu thức. Không nên suy ra rằng phần tử hoặc collection chắc chắn bất biến theo hợp đồng API của Java.

Ví dụ, một danh sách chứa object tham chiếu có thể có object mutable bên trong. Nếu phần tử là object được giữ làm constant reference, thay đổi trạng thái bên trong object đó là vấn đề khác với việc SpEL dựng lại list. Vì vậy:

- Ưu tiên literal bất biến như String, số, Boolean và null cho danh sách constant.
- Không đưa object mutable vào một cấu trúc mà ứng dụng dự định xem như cấu hình bất biến.
- Nếu cần dữ liệu có thể chỉnh sửa, hãy tạo object hoặc collection mới ở tầng ứng dụng.
- Không dùng constant inline list làm nơi lưu trạng thái giữa các request.

## 9. Phân biệt inline list, array initializer và collection từ biến

Ba cách tạo hoặc lấy collection có mục đích khác nhau:

| Cách viết | Kết quả | Khi nên dùng |
| --- | --- | --- |
| `{1, 2, 3}` | Java `List` | Danh sách nhỏ được mô tả trực tiếp trong expression. |
| `new int[]{1, 2, 3}` | Java array `int[]` | Cần array với kiểu phần tử cụ thể. |
| `items` hoặc `#items` | Collection đã tồn tại trong root object/context | Dữ liệu do ứng dụng quản lý và có thể thay đổi độc lập với expression. |

Inline list không tự tạo ra Java array. Nếu API cần `int[]`, dùng array construction hoặc chuyển đổi kiểu có chủ đích ở tầng ứng dụng.

## 10. Tái sử dụng expression và hiệu năng

Parse một expression một lần rồi tái sử dụng thường hiệu quả hơn việc parse lại cùng một chuỗi ở mọi request:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression fixedPermissions = parser.parseExpression(
        "{'READ', 'WRITE', 'DELETE'}");

for (int i = 0; i < 100; i++) {
    List<?> permissions = fixedPermissions.getValue(List.class);
    // sử dụng như dữ liệu chỉ đọc
}
```

Với constant inline list, SpEL còn có thể tái sử dụng constant value thay vì tạo list mới ở mỗi lần đánh giá. Với inline list chứa biến hoặc property runtime, các phần tử động vẫn phải được đánh giá và danh sách kết quả được dựng theo lần gọi.

Đừng biến mọi collection thành inline list chỉ để kỳ vọng tối ưu. Nếu dữ liệu lớn, lấy từ database, thay đổi thường xuyên hoặc được chia sẻ giữa nhiều thành phần, hãy để ứng dụng quản lý nó bằng collection hoặc service phù hợp. Tối ưu constant list hữu ích nhất cho các tập giá trị nhỏ, cố định và thuộc về chính expression.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Mong đợi list thay đổi nhưng kết quả giữ nguyên | Expression chỉ chứa literal nên SpEL cache constant list. | Dùng biến/property động nếu giá trị phải thay đổi theo context; không cố dùng constant expression để lưu trạng thái. |
| Thay đổi list ảnh hưởng lần đánh giá sau | Caller đã mutate một constant value được expression tái sử dụng. | Xem kết quả constant list là chỉ đọc; tạo `new ArrayList<>(result)` trước khi sửa. |
| Danh sách không được tối ưu thành constant | Có ít nhất một phần tử là biến, property, method call hoặc expression runtime. | Xác định phần tử động; đây là hành vi cần thiết nếu giá trị phụ thuộc runtime. |
| List cha không constant dù nhiều phần tử là literal | Một list con lồng nhau chứa phần tử động. | Kiểm tra toàn bộ cấu trúc lồng nhau; một nhánh động khiến list cha không constant toàn phần. |
| `@Value` không parse được inline list | Nhầm delimiter `#{...}` của annotation với `{...}` của list. | Dùng dạng lồng nhau như `@Value("#{{'READ', 'WRITE'}}")`. |
| API cần array nhưng nhận được List | `{...}` tạo Java List. | Dùng `new int[]{...}` hoặc chuyển đổi rõ ràng sang kiểu array cần thiết. |
| Expression cho kết quả khác giữa các request | Biến hoặc root object thay đổi theo EvaluationContext. | Dùng context đúng cho từng request; parse expression có thể tái sử dụng nhưng dữ liệu runtime phải được cung cấp riêng. |

## Ghi nhớ

- `{...}` tạo Java `List`; `{}` là danh sách rỗng.
- Inline list có thể lồng nhau để biểu diễn cấu trúc nhiều cấp.
- Nếu tất cả phần tử đều là constant, kể cả các inline list con chỉ chứa constant, SpEL có thể tạo và cache một constant list.
- Constant list được tạo lazy khi cần và tái sử dụng giữa các lần đánh giá, giúp giảm công việc dựng collection và garbage.
- Biến, property hoặc method call làm danh sách phụ thuộc runtime; các giá trị đó được đánh giá lại khi expression chạy.
- Một nhánh động trong list con khiến cấu trúc list cha không còn constant toàn phần.
- Constant mô tả tối ưu nội bộ của expression, không phải cam kết rằng collection là immutable.
- Hãy coi kết quả constant list là chỉ đọc; tạo bản sao mutable nếu cần thay đổi.
- `{...}` trả về List; `new int[]{...}` tạo array.
- Parse expression một lần và tái sử dụng; để dữ liệu thay đổi nằm trong context hoặc object do ứng dụng quản lý.

## Tài liệu tham khảo

- [Spring Framework Reference — Inline Lists](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/inline-lists.html)
- [Spring Framework API — InlineList](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/InlineList.html)
- [Spring Framework source — InlineList](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/ast/InlineList.java)