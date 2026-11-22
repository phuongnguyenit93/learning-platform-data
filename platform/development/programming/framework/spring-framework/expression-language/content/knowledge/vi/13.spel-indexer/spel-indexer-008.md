# Null-safe collection selection và index access trong SpEL

## 1. Vì sao cần null-safe access?

Spring Expression Language (SpEL) có thể đọc phần tử của List, array hoặc Map bằng index/key; đồng thời có thể lọc và biến đổi phần tử trong collection bằng selection và projection. Các thao tác này thường xuất hiện trong đường dẫn object có thể chưa được khởi tạo, dữ liệu tùy chọn hoặc kết quả truy vấn có thể là null.

Từ Spring Framework 6.2, SpEL hỗ trợ null-safe operator cho index access, collection selection và projection. Các cú pháp này cho phép biểu thức trả về null khi chính target collection, Map hoặc array là null.

Những dạng chính:

| Thao tác | Cú pháp thông thường | Cú pháp null-safe |
|---|---|---|
| Index access | `items[0]` | `items?.[0]` |
| Map key access | `settings['theme']` | `settings?.['theme']` |
| Selection: mọi phần tử khớp | `items.?[condition]` | `items?.?[condition]` |
| Selection: phần tử khớp đầu tiên | `items.^[condition]` | `items?.^[condition]` |
| Selection: phần tử khớp cuối cùng | `items.$[condition]` | `items?.$[condition]` |
| Projection | `items.![expression]` | `items?.![expression]` |

Dấu `?.` được đặt ngay sau target và trước thao tác index, selection hoặc projection. Phần biểu thức trong ngoặc vuông vẫn giữ cú pháp SpEL thông thường.

## 2. Null-safe index access

Index access dùng dấu ngoặc vuông để lấy phần tử theo vị trí hoặc theo key. Với List và array, index thường là số nguyên bắt đầu từ 0; với Map, index là key.

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", Arrays.asList(72, 85, 91));

Expression expression = parser.parseExpression("#scores?.[0]");
Integer firstScore = expression.getValue(context, Integer.class);

System.out.println(firstScore); // 72
~~~

Khi `scores` có giá trị, biểu thức `#scores?.[0]` hoạt động như index access thông thường. Khi `scores` là null, toán tử null-safe trả về null thay vì cố lấy phần tử đầu tiên từ một target không tồn tại.

~~~java
context.setVariable("scores", null);

Object firstScore = parser.parseExpression("#scores?.[0]")
        .getValue(context);

System.out.println(firstScore); // null
~~~

Có thể dùng cùng cú pháp với array:

~~~java
context.setVariable("codes", new String[] {"A-01", "B-02"});

String firstCode = parser.parseExpression("#codes?.[0]")
        .getValue(context, String.class);
~~~

Và với Map:

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("theme", "dark");
context.setVariable("settings", settings);

String theme = parser.parseExpression("#settings?.['theme']")
        .getValue(context, String.class);
~~~

Null-safe index access chỉ xử lý trường hợp target là null. Nó không tự kiểm tra index có nằm trong giới hạn hay không. Nếu List rỗng mà truy cập `[0]`, hoặc index vượt quá kích thước List/array, phép đánh giá vẫn có thể thất bại. Với Map, một key không tồn tại thường cho kết quả null, nhưng điều đó khác với target Map là null.

## 3. Selection: lọc các phần tử phù hợp

Selection dùng để chọn phần tử trong collection dựa trên một điều kiện. Cú pháp thông thường là `.?[condition]`; cú pháp null-safe là `?.?[condition]`.

Ví dụ lọc các điểm số đạt từ 80 trở lên:

~~~java
List<Integer> scores = Arrays.asList(55, 82, 91, 67);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.?[#this >= 80]");

List<?> passedScores = expression.getValue(context, List.class);
System.out.println(passedScores); // [82, 91]
~~~

Trong predicate:

- `#this` là phần tử hiện tại đang được kiểm tra.
- `#root` vẫn tham chiếu root object của evaluation context.
- Biểu thức sau `?.?` phải tạo ra điều kiện Boolean để quyết định phần tử có được giữ lại hay không.

Nếu target collection là null:

~~~java
context.setVariable("scores", null);

Object passedScores = parser.parseExpression(
        "#scores?.?[#this >= 80]").getValue(context);

System.out.println(passedScores); // null
~~~

Nếu target là collection rỗng nhưng không null, selection trả về collection rỗng. Vì vậy, cần phân biệt hai trạng thái: null target cho kết quả null; collection rỗng được xử lý như collection có zero phần tử và cho kết quả selection rỗng.

## 4. Selection phần tử khớp đầu tiên

Khi chỉ cần phần tử đầu tiên thỏa điều kiện, dùng toán tử `.^[]`. Dạng null-safe là `?.^[]`.

~~~java
List<Integer> scores = Arrays.asList(55, 82, 91, 67);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.^[#this >= 80]");

Integer firstPassed = expression.getValue(context, Integer.class);
System.out.println(firstPassed); // 82
~~~

SpEL duyệt collection theo thứ tự của nó và trả về phần tử đầu tiên thỏa predicate. Đây là kết quả đơn, không phải collection chứa tất cả phần tử phù hợp.

Nếu target `scores` là null, `#scores?.^[...]` trả về null. Nếu target không null nhưng không có phần tử nào khớp, phép first-selection cũng không tìm được phần tử và trả về null. Do đó, nếu ứng dụng cần phân biệt “collection không tồn tại” với “không có phần tử phù hợp”, hãy kiểm tra target riêng trong Java hoặc biểu thức phù hợp.

## 5. Selection phần tử khớp cuối cùng

Khi cần phần tử cuối cùng thỏa điều kiện, dùng toán tử `.$[]`. Dạng null-safe là `?.$[]`.

~~~java
List<Integer> scores = Arrays.asList(55, 82, 91, 67);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.$[#this >= 80]");

Integer lastPassed = expression.getValue(context, Integer.class);
System.out.println(lastPassed); // 91
~~~

Selection đầu tiên và cuối cùng đều trả về một phần tử, hoặc null nếu không tìm thấy phần tử thỏa điều kiện. Kết quả phụ thuộc vào thứ tự iteration của collection. Với collection không có thứ tự ổn định, khái niệm “đầu tiên” và “cuối cùng” cũng không nên được coi là một thứ tự nghiệp vụ cố định.

Nếu chỉ cần mọi phần tử khớp điều kiện, hãy dùng `?.?[]`; nếu chỉ cần một phần tử theo vị trí đầu/cuối, dùng `?.^[]` hoặc `?.$[]`.

## 6. Projection: biến đổi từng phần tử

Projection áp dụng một biểu thức lên từng phần tử của collection và tạo collection kết quả. Cú pháp thông thường là `.![expression]`; dạng null-safe là `?.![expression]`.

Ví dụ nhân đôi từng điểm số:

~~~java
List<Integer> scores = Arrays.asList(10, 20, 30);

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", scores);

Expression expression =
        parser.parseExpression("#scores?.![#this * 2]");

List<?> doubled = expression.getValue(context, List.class);
System.out.println(doubled); // [20, 40, 60]
~~~

Trong projection, `#this` là phần tử hiện tại. Biểu thức sau `?.!` được đánh giá một lần cho mỗi phần tử và các kết quả được đưa vào collection mới.

Có thể projection property từ các object:

~~~java
public class Person {
    private String name;

    public Person(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}

List<Person> people = Arrays.asList(
        new Person("Lan"),
        new Person("Minh"));

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("people", people);

Expression expression =
        parser.parseExpression("#people?.![name]");

List<?> names = expression.getValue(context, List.class);
System.out.println(names); // [Lan, Minh]
~~~

Nếu `people` là null, null-safe projection trả về null. Nếu `people` là collection rỗng, projection trả về collection rỗng. Null-safe operator ở target không tự bảo vệ property bên trong từng phần tử; nếu một phần tử có thể null hoặc property lồng nhau có thể null, hãy dùng null-safe access ở chính đường dẫn phần tử đó.

Ví dụ khi property `address` của từng Person có thể null:

~~~text
#people?.![address?.city]
~~~

`?.!` bảo vệ collection `people`; `address?.city` bảo vệ property `address` của từng phần tử.

## 7. Kết hợp selection và projection

Có thể lọc collection trước rồi chuyển đổi những phần tử còn lại. Ví dụ chỉ lấy tên của những người đang hoạt động:

~~~java
Expression expression = parser.parseExpression(
        "#people?.?[active]?.![name]");
~~~

Các bước thực hiện:

1. `#people?.?` lọc collection nếu target không null.
2. Predicate `active` được đánh giá trên từng phần tử hiện tại.
3. `?.!` projection tên của các phần tử đã được chọn.

Dùng null-safe operator ở từng bước khi kết quả bước trước có thể là null. Một toán tử null-safe chỉ bảo vệ target ngay trước thao tác của nó; nó không tự biến toàn bộ phần còn lại của expression thành null-safe.

Có thể kết hợp với index access khi muốn lấy một phần tử từ kết quả đã lọc:

~~~text
(#people?.?[active])?.[0]
~~~

Dấu ngoặc giúp phân nhóm kết quả selection trước khi thực hiện index access. Nếu collection ban đầu null, selection trả về null và null-safe index access tiếp theo cũng trả về null. Nếu collection không null nhưng không có phần tử phù hợp, kết quả selection là collection rỗng; truy cập index 0 vẫn có thể phát sinh lỗi vì không có phần tử ở vị trí đó.

## 8. Áp dụng với Map, List và array

SpEL hỗ trợ index access và selection/projection trên các cấu trúc collection phù hợp:

| Cấu trúc | Truy cập phần tử | Ví dụ null-safe |
|---|---|---|
| List | Index bắt đầu từ 0 | `#items?.[0]` |
| Array | Index bắt đầu từ 0 | `#codes?.[1]` |
| Map | Tra cứu theo key | `#settings?.['theme']` |
| Collection | Selection | `#items?.?[#this.active]` |
| Collection | Projection | `#items?.![#this.name]` |

Với Map, indexer dùng key thay vì vị trí. Selection trên Map có ngữ nghĩa riêng vì phần tử được duyệt là entry; khi viết predicate, cần dùng đúng cách truy cập key/value mà expression context cung cấp. Ví dụ trong một số trường hợp, có thể truy cập giá trị entry qua biến `value` hoặc biểu thức tương ứng với entry đang xét. Không nên áp dụng máy móc predicate dành cho List vào Map.

Với List và array, index là vị trí. Truy cập ngoài giới hạn vẫn là lỗi dù target đã được bảo vệ null-safe. Với collection không null nhưng rỗng, selection/projection xử lý collection rỗng; index access không có phần tử để trả về.

## 9. Null-safe operator không bảo vệ toàn bộ chuỗi truy cập

Một nhầm lẫn phổ biến là nghĩ rằng chỉ cần đặt `?.` ở đầu đường dẫn thì mọi thao tác phía sau đều an toàn. Thực tế, mỗi null-safe operator chỉ bảo vệ thao tác ngay sau nó.

Ví dụ:

~~~text
#people?.[0].name
~~~

Nếu `people` là null, `?.[0]` trả về null; phần `.name` tiếp theo vẫn có thể cố truy cập property trên null và gây lỗi.

Cách viết an toàn hơn nếu phần tử đầu tiên cũng có thể null:

~~~text
#people?.[0]?.name
~~~

Tương tự, với selection/projection:

~~~text
#people?.?[active]?.![address?.city]
~~~

- `?.?` bảo vệ collection gốc khi selection.
- `?.!` bảo vệ kết quả selection nếu kết quả đó null.
- `address?.city` bảo vệ property address của từng phần tử đang projection.

Hãy phân tích expression thành từng bước và đặt null-safe operator ở mỗi ranh giới dữ liệu có thể null.

## 10. Phân biệt null, collection rỗng và không tìm thấy phần tử

Ba trường hợp này có ý nghĩa khác nhau:

| Trạng thái | Null-safe index | Selection nhiều phần tử | Projection |
|---|---|---|---|
| Target là null | `null` | `null` | `null` |
| Target là collection rỗng | Index không có phần tử, có thể lỗi | Collection rỗng | Collection rỗng |
| Target có phần tử nhưng predicate không khớp | Phụ thuộc index được yêu cầu | Collection rỗng | Projection vẫn trả kết quả cho các phần tử |
| First/last selection không tìm thấy | Không áp dụng | `null` | Không áp dụng |

Đặc biệt, first-selection `?.^[]` và last-selection `?.$[]` trả về một phần tử đơn, nên khi không có phần tử phù hợp, kết quả là null. Nếu cần một collection kết quả, dùng selection đầy đủ `?.?[]`.

Ứng dụng có thể cần xử lý riêng collection null và collection rỗng. Ví dụ, null có thể có nghĩa “chưa tải dữ liệu”, còn collection rỗng có nghĩa “đã tải và không có phần tử”. Đừng tự động thay null bằng collection rỗng nếu hai trạng thái mang ý nghĩa nghiệp vụ khác nhau.

## 11. Dùng trong @Value và cấu hình Spring

SpEL null-safe selection/projection/index access có thể được dùng tại những điểm cấu hình Spring hỗ trợ expression, chẳng hạn `@Value`:

~~~java
@Component
public class ScoreSummary {
    @Value("#{scoreProvider.scores?.?[#this >= 80]}")
    private List<Integer> passedScores;
}
~~~

Ví dụ trên dùng bean có tên `scoreProvider` và property `scores` làm target collection. Khi property này là null, toán tử null-safe selection trả về null. Với cấu hình collection phức tạp, việc đưa dữ liệu vào bean rồi xử lý bằng Java thường rõ ràng và dễ kiểm tra hơn.

Một cách khác là đánh giá expression trực tiếp trong Java với `EvaluationContext`, như các ví dụ ở trên. Cách này giúp kiểm soát root object, variables và kiểu kết quả rõ ràng.

## 12. Phiên bản Spring Framework

Null-safe index access và null-safe collection selection/projection là khả năng được bổ sung trong Spring Framework 6.2. Nếu ứng dụng đang chạy phiên bản cũ hơn, parser có thể không nhận diện các dạng cú pháp `?.[]`, `?.?[]`, `?.^[]`, `?.$[]` hoặc `?.![]`.

Khi expression báo lỗi cú pháp, hãy kiểm tra phiên bản Spring Framework thực tế trên classpath, đặc biệt nếu dự án dùng Spring Boot dependency management. Không nên chỉ nâng một module `spring-expression` lên phiên bản khác với các module Spring còn lại; hãy để Spring Boot BOM hoặc Spring Framework BOM quản lý phiên bản đồng bộ.

Với ứng dụng chưa thể nâng cấp, có thể kiểm tra null trong Java trước khi đánh giá expression, hoặc dùng conditional expression phù hợp với những cú pháp được phiên bản đang chạy hỗ trợ.

## 13. Lỗi thường gặp

**Đặt sai vị trí dấu hỏi**

Index null-safe viết `target?.[index]`; selection viết `target?.?[predicate]`; projection viết `target?.![expression]`. Dấu `?.` phải đứng giữa target và toán tử tương ứng.

**Nghĩ rằng index out-of-range được bỏ qua**

Null-safe index chỉ xử lý target null. Index vượt giới hạn của List/array vẫn có thể phát sinh lỗi evaluation.

**Nhầm null với collection rỗng**

Null-safe selection trên target null trả về null. Selection trên collection rỗng trả về collection rỗng. Hai kết quả khác nhau và có thể ảnh hưởng đến logic tiếp theo.

**Quên bảo vệ các bước tiếp theo**

`?.` không làm cho toàn bộ chuỗi truy cập phía sau tự động an toàn. Hãy dùng thêm null-safe operator khi phần tử hoặc property tiếp theo cũng có thể null.

**Dùng predicate không trả về Boolean**

Selection cần predicate Boolean. Điều kiện không phù hợp có thể khiến expression thất bại khi đánh giá.

**Dùng nhầm selection và projection**

Selection lọc và giữ lại các phần tử phù hợp. Projection biến đổi mỗi phần tử thành một giá trị mới. `?.?[]` và `?.![]` có mục đích khác nhau.

**Dùng cú pháp mới trên Spring cũ**

Các dạng null-safe cho index, selection và projection yêu cầu Spring Framework 6.2 trở lên. Hãy xác nhận version runtime nếu parser không nhận cú pháp.

## 14. Ví dụ tổng hợp

Ví dụ sau lọc các điểm đạt yêu cầu, lấy điểm đạt đầu tiên và biến đổi toàn bộ điểm thành nhãn. Cùng một context có thể được đánh giá với collection bình thường hoặc null:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("scores", Arrays.asList(55, 82, 91, 67));

Expression passedExpression =
        parser.parseExpression("#scores?.?[#this >= 80]");
Expression firstPassedExpression =
        parser.parseExpression("#scores?.^[#this >= 80]");
Expression labelExpression =
        parser.parseExpression("#scores?.!['Score: ' + #this]");
Expression firstExpression =
        parser.parseExpression("#scores?.[0]");

List<?> passed = passedExpression.getValue(context, List.class);
Integer firstPassed = firstPassedExpression.getValue(context, Integer.class);
List<?> labels = labelExpression.getValue(context, List.class);
Integer firstScore = firstExpression.getValue(context, Integer.class);

System.out.println(passed);      // [82, 91]
System.out.println(firstPassed); // 82
System.out.println(labels);      // [Score: 55, Score: 82, Score: 91, Score: 67]
System.out.println(firstScore);  // 55

context.setVariable("scores", null);

Object safeIndex = firstExpression.getValue(context);
Object safeSelection = passedExpression.getValue(context);
Object safeProjection = labelExpression.getValue(context);

System.out.println(safeIndex);      // null
System.out.println(safeSelection);  // null
System.out.println(safeProjection); // null
~~~

Các expression được parse một lần và có thể đánh giá lại sau khi cập nhật variable. Khi `scores` là null, mỗi thao tác null-safe trả về null. Khi collection tồn tại, index access lấy phần tử theo vị trí, selection lọc phần tử, first-selection lấy một phần tử phù hợp và projection tạo collection mới.

## 15. Ghi nhớ

- Null-safe index access: `target?.[index]`.
- Null-safe selection tất cả phần tử: `target?.?[predicate]`.
- Null-safe selection phần tử đầu tiên: `target?.^[predicate]`.
- Null-safe selection phần tử cuối cùng: `target?.$[predicate]`.
- Null-safe projection: `target?.![expression]`.
- Các cú pháp null-safe collection/index này yêu cầu Spring Framework 6.2 trở lên.
- Null target trả về null; collection rỗng vẫn là collection rỗng; index vượt giới hạn vẫn có thể lỗi.
- Null-safe operator chỉ bảo vệ target ngay trước thao tác, vì vậy cần đặt thêm `?.` ở các chặng sau có thể null.
- Selection lọc phần tử; projection biến đổi phần tử; first/last selection trả về một phần tử đơn.
- Dùng `#this` để tham chiếu phần tử hiện tại trong predicate hoặc projection.
