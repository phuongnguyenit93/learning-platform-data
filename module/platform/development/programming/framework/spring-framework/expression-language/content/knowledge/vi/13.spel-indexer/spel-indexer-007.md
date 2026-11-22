# Indexer cho collection có thể null trong Spring Expression Language

Spring Expression Language (SpEL) dùng toán tử indexer [] để đọc một phần tử từ array, list hoặc map. Ví dụ, items[0] lấy phần tử đầu tiên của list, còn settings['theme'] lấy giá trị theo khóa theme trong map.

Trong ứng dụng thực tế, collection hoặc map có thể chưa được khởi tạo và mang giá trị null. Với indexer thông thường, SpEL không thể truy cập phần tử trên đối tượng null và quá trình đánh giá có thể phát sinh lỗi. Từ Spring Framework 6.2, SpEL hỗ trợ null-safe indexer với cú pháp ?.[]. Cú pháp này cho phép biểu thức trả về null khi đối tượng cần đánh chỉ mục là null.

Cần phân biệt collection null với collection rỗng: null-safe indexer xử lý trường hợp đối tượng đích null; nó không biến một chỉ số không hợp lệ thành kết quả null.

## 1. Indexer thông thường

Indexer đặt biểu thức chỉ số hoặc khóa trong dấu ngoặc vuông:

~~~spel
items[0]
settings['theme']
matrix[1][2]
~~~

Cách truy cập phụ thuộc vào kiểu đối tượng:

| Đối tượng | Cú pháp | Ý nghĩa |
|---|---|---|
| Array | scores[0] | Đọc phần tử đầu tiên |
| List | items[0] | Đọc phần tử tại chỉ số 0 |
| Map | settings['theme'] | Đọc giá trị theo khóa |
| Cấu trúc lồng nhau | matrix[1][2] | Đọc phần tử trong cấu trúc nhiều chiều |

Chỉ số của array và list bắt đầu từ 0. Với map, nội dung trong ngoặc vuông là khóa được dùng để tra cứu.

Ví dụ:

~~~java
List<String> languages =
    Arrays.asList("Java", "Kotlin", "Scala");

Map<String, String> settings = new HashMap<>();
settings.put("theme", "dark");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("languages", languages);
context.setVariable("settings", settings);

ExpressionParser parser = new SpelExpressionParser();

String firstLanguage =
    parser.parseExpression("#languages[0]")
          .getValue(context, String.class);

String theme =
    parser.parseExpression("#settings['theme']")
          .getValue(context, String.class);
~~~

Kết quả là Java và dark.

## 2. Vấn đề khi collection có thể null

Trong ứng dụng thực tế, dữ liệu thường đến từ API, database, cấu hình hoặc object được tạo theo điều kiện. Vì vậy, một property chứa collection có thể chưa được khởi tạo.

Ví dụ:

~~~java
List<String> tags = null;
context.setVariable("tags", tags);
~~~

Nếu đánh giá:

~~~spel
#tags[0]
~~~

SpEL phải truy cập phần tử đầu tiên trên giá trị của #tags. Vì đối tượng đích là null, thao tác index không thể thực hiện và evaluation có thể thất bại.

Tình huống tương tự xảy ra với map:

~~~spel
#settings['theme']
~~~

Nếu #settings là null, SpEL không có map để tra cứu khóa theme.

Điều này khác với map tồn tại nhưng không chứa khóa được yêu cầu. Map không có khóa thường trả về null theo hành vi của Map.get(...); còn map null không thể thực hiện thao tác index.

## 3. Null-safe indexer với cú pháp ?.[ ]

Từ Spring Framework 6.2, SpEL hỗ trợ null-safe indexing. Cú pháp đặt dấu hỏi và dấu chấm ngay trước cặp ngoặc vuông, không có khoảng trắng giữa dấu chấm và ngoặc mở:

~~~spel
#tags?.[0]
#settings?.['theme']
#scores?.[1]
~~~

Nếu đối tượng đứng trước toán tử indexer là null, biểu thức trả về null thay vì cố gắng truy cập phần tử.

Ví dụ:

~~~java
List<String> tags = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("tags", tags);

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#tags?.[0]");

String firstTag =
    expression.getValue(context, String.class);

System.out.println(firstTag);
~~~

Kết quả:

~~~text
null
~~~

Trong trường hợp này:

1. SpEL đọc biến #tags từ EvaluationContext.
2. Giá trị của biến là null.
3. Toán tử null-safe indexer nhận biết đối tượng đích null.
4. SpEL trả về null mà không thực hiện thao tác lấy phần tử.

Null-safe indexer giúp biểu thức xử lý dữ liệu tùy chọn rõ ràng hơn và giảm nhu cầu kiểm tra null bằng mã Java bên ngoài.

## 4. Dùng null-safe indexer với List

Với list, biểu thức thường lấy phần tử theo chỉ số:

~~~spel
#items?.[0]
~~~

Nếu list tồn tại và có phần tử tại chỉ số 0, SpEL trả về phần tử đó. Nếu list là null, SpEL trả về null.

Ví dụ:

~~~java
List<String> items =
    Arrays.asList("Spring", "SpEL");

context.setVariable("items", items);

Expression firstExpression =
    parser.parseExpression("#items?.[0]");

String first =
    firstExpression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Spring
~~~

Có thể dùng cùng một Expression với các giá trị biến khác nhau:

~~~java
context.setVariable("items", null);
String whenNull =
    firstExpression.getValue(context, String.class);

context.setVariable(
    "items",
    Arrays.asList("Spring", "SpEL")
);
String whenPresent =
    firstExpression.getValue(context, String.class);
~~~

Kết quả lần lượt là null và Spring.

Điều này cho thấy biểu thức giữ nguyên, còn giá trị trả về thay đổi theo object được cung cấp trong context.

## 5. Dùng null-safe indexer với Map

Với map, phần nằm trong dấu ngoặc vuông là khóa:

~~~spel
#settings?.['theme']
~~~

Nếu map null, biểu thức trả về null. Nếu map tồn tại, SpEL tra cứu giá trị theo khóa.

Ví dụ:

~~~java
Map<String, String> settings = new HashMap<>();
settings.put("theme", "dark");

context.setVariable("settings", settings);

Expression themeExpression =
    parser.parseExpression("#settings?.['theme']");

String theme =
    themeExpression.getValue(context, String.class);
~~~

Kết quả:

~~~text
dark
~~~

Nếu đổi biến thành null:

~~~java
context.setVariable("settings", null);
~~~

cùng biểu thức trả về null.

Cần phân biệt hai trường hợp:

- Map null: null-safe indexer bỏ qua thao tác truy cập và trả về null.
- Map tồn tại nhưng không có khóa: thao tác tra cứu vẫn được thực hiện và kết quả thường là null theo hợp đồng của Map.

Hai trường hợp có thể cùng cho ra null, nhưng nguyên nhân khác nhau.

## 6. Dùng null-safe indexer với Array

Indexer cũng có thể dùng để đọc phần tử array:

~~~spel
#scores?.[0]
~~~

Ví dụ:

~~~java
Integer[] scores = null;
context.setVariable("scores", scores);

Expression scoreExpression =
    parser.parseExpression("#scores?.[0]");

Integer firstScore =
    scoreExpression.getValue(context, Integer.class);
~~~

Khi array null, kết quả là null. Khi array có phần tử, SpEL trả về phần tử ở chỉ số được yêu cầu.

Null-safe indexer bảo vệ đối tượng array khi nó null. Nó không thay đổi quy tắc chỉ số của array.

## 7. Null-safe indexer không xử lý collection rỗng hoặc chỉ số sai

Đây là điểm rất dễ nhầm lẫn.

Giả sử list tồn tại nhưng không có phần tử:

~~~java
List<String> items = Collections.emptyList();
context.setVariable("items", items);
~~~

Biểu thức:

~~~spel
#items?.[0]
~~~

vẫn có thể phát sinh lỗi index ngoài phạm vi. Lý do là list không null nên SpEL tiếp tục thực hiện indexer; danh sách chỉ đơn giản không có phần tử ở vị trí 0.

So sánh:

| Trạng thái của đối tượng | Biểu thức | Hành vi |
|---|---|---|
| List là null | #items?.[0] | Trả về null |
| List có phần tử | #items?.[0] | Trả phần tử đầu tiên |
| List rỗng | #items?.[0] | Lỗi do chỉ số ngoài phạm vi |
| List có một phần tử, đọc chỉ số 3 | #items?.[3] | Lỗi do chỉ số ngoài phạm vi |

Null-safe indexer chỉ bảo vệ trường hợp đối tượng đích null. Nó không tự kiểm tra kích thước collection và không biến mọi lỗi index thành null.

### Kiểm tra cả null và rỗng

Nếu ứng dụng muốn nhận null khi list null hoặc rỗng, có thể kiểm tra trước khi đọc phần tử:

~~~spel
#items != null && !#items.isEmpty() ? #items[0] : null
~~~

Toán tử logic && đánh giá ngắn mạch. Khi #items là null, vế sau không được đánh giá; khi list tồn tại nhưng rỗng, nhánh điều kiện trả về null.

Có thể dùng một giá trị mặc định:

~~~spel
#items != null && !#items.isEmpty() ? #items[0] : 'N/A'
~~~

Cách này xử lý cả hai điều kiện null và rỗng theo yêu cầu của ứng dụng.

## 8. Kết hợp null-safe indexer với truy cập property tiếp theo

Một phần tử lấy được từ collection có thể là object và cần đọc tiếp thuộc tính:

~~~spel
#orders?.[0].customer.name
~~~

Nếu #orders là null, phép index an toàn trả về null. Tuy nhiên, phần còn lại của biểu thức vẫn có thể được đánh giá; nếu tiếp tục truy cập customer.name trên null thì có thể phát sinh lỗi.

Vì vậy, cần đặt null-safe operator ở những điểm tiếp tục đi qua object có khả năng null:

~~~spel
#orders?.[0]?.customer?.name
~~~

Trong biểu thức này:

1. #orders?.[0] bảo vệ trường hợp collection orders null.
2. ?.customer bảo vệ trường hợp phần tử đầu tiên null.
3. ?.name bảo vệ trường hợp customer null.

Khi một đoạn trả về null, đoạn truy cập null-safe tiếp theo tiếp tục giữ kết quả null.

Quy tắc này áp dụng rộng hơn cho compound expression: dùng null-safe operator tại từng đoạn đường dẫn có thể null, không chỉ ở vị trí đầu tiên.

## 9. Kết hợp với Elvis để tạo giá trị mặc định

Nếu kết quả index có thể null và ứng dụng muốn thay bằng giá trị mặc định, có thể kết hợp null-safe indexer với Elvis:

~~~spel
#items?.[0] ?: 'N/A'
~~~

Nếu list null, indexer trả về null và Elvis chọn chuỗi N/A. Nếu list có phần tử đầu tiên khác null, kết quả là phần tử đó.

Tuy nhiên, biểu thức này vẫn không xử lý list rỗng: khi list tồn tại nhưng không có phần tử 0, indexer có thể phát sinh lỗi trước khi Elvis được áp dụng.

Nếu cần xử lý cả null và rỗng, hãy dùng điều kiện kiểm tra kích thước như phần trước.

Với map, Elvis có thể phù hợp khi map tồn tại nhưng khóa không có giá trị:

~~~spel
#settings?.['theme'] ?: 'light'
~~~

Biểu thức trả về theme nếu có giá trị khác null; nếu map null hoặc giá trị tra cứu là null, nó trả về light.

## 10. Kết hợp null-safe indexer với biến chỉ số

Indexer có thể nhận biểu thức làm chỉ số thay vì chỉ dùng một số literal:

~~~spel
#items?.[#index]
~~~

Trong đó #index là biến được đăng ký trong EvaluationContext.

Ví dụ:

~~~java
context.setVariable(
    "items",
    Arrays.asList("Java", "Kotlin", "Scala")
);
context.setVariable("index", 1);

Expression expression =
    parser.parseExpression("#items?.[#index]");

String language =
    expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Kotlin
~~~

Null-safe operator bảo vệ collection khi collection null. Giá trị index vẫn phải hợp lệ với collection tại thời điểm đánh giá. Nếu index âm hoặc vượt phạm vi, lỗi index vẫn có thể xảy ra.

## 11. Phiên bản Spring Framework và khả năng tương thích

Null-safe indexer ?.[] được hỗ trợ từ Spring Framework 6.2. Nếu ứng dụng chạy phiên bản cũ hơn, parser có thể không hiểu cú pháp này.

Trong phiên bản chưa hỗ trợ, có thể kiểm tra null trước khi index:

~~~spel
#items != null ? #items[0] : null
~~~

Nếu cần xử lý thêm collection rỗng:

~~~spel
#items != null && !#items.isEmpty() ? #items[0] : null
~~~

Khi nâng cấp framework hoặc chia sẻ biểu thức giữa nhiều ứng dụng, cần xác định phiên bản Spring thực tế để chọn cú pháp tương thích.

## 12. Ví dụ hoàn chỉnh trong Java

Ví dụ sau minh họa một list có thể null, sử dụng indexer an toàn và cung cấp giá trị mặc định:

~~~java
List<String> labels = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("labels", labels);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#labels?.[0] ?: 'No label'"
);

String result =
    expression.getValue(context, String.class);

System.out.println(result);
~~~

Kết quả:

~~~text
No label
~~~

Nếu thay list null bằng list có phần tử:

~~~java
context.setVariable(
    "labels",
    Arrays.asList("Primary", "Secondary")
);
~~~

đánh giá lại cùng Expression sẽ trả về:

~~~text
Primary
~~~

Expression được phân tích một lần và tái sử dụng; giá trị trả về phụ thuộc vào dữ liệu hiện có trong context.

## 13. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Null-safe indexer làm list rỗng trả về null.**  
Nó chỉ bảo vệ khi chính đối tượng đích null. List rỗng vẫn không có phần tử ở chỉ số 0.

**Nhầm lẫn 2: Dùng ?.[] là không cần kiểm tra index.**  
Chỉ số vẫn phải hợp lệ khi collection tồn tại.

**Nhầm lẫn 3: Một null-safe operator bảo vệ toàn bộ biểu thức.**  
Trong compound expression, các đoạn truy cập tiếp theo vẫn cần null-safe operator nếu đối tượng trung gian có thể null.

**Nhầm lẫn 4: Elvis tự xử lý mọi lỗi index.**  
Elvis xử lý giá trị null; nó không bắt exception do index ngoài phạm vi.

**Nhầm lẫn 5: Null-safe indexer có trong mọi phiên bản SpEL.**  
Cú pháp ?.[] cần Spring Framework 6.2 trở lên. Với phiên bản cũ, dùng điều kiện kiểm tra null và kích thước.

## 14. Ghi nhớ

- Indexer [] đọc phần tử array/list theo chỉ số hoặc map theo khóa.
- Null-safe indexer ?.[] trả về null khi đối tượng đích là null.
- Null-safe indexing được hỗ trợ từ Spring Framework 6.2.
- Collection tồn tại nhưng rỗng hoặc chỉ số ngoài phạm vi vẫn có thể gây lỗi.
- Với map, khóa không tồn tại thường trả về null theo hành vi tra cứu map.
- Có thể kết hợp null-safe indexer với property access tiếp theo, nhưng phải bảo vệ từng đoạn đường dẫn có thể null.
- Elvis có thể thay kết quả null bằng giá trị mặc định, nhưng không bắt lỗi index.
- Nếu cần xử lý cả null và rỗng, hãy kiểm tra null và isEmpty() trước khi đọc phần tử.

Khi dùng indexer với dữ liệu tùy chọn, hãy xác định rõ collection có thể null hay rỗng, chỉ số có hợp lệ không, và các thuộc tính tiếp theo có thể null không. Chọn cú pháp bảo vệ phù hợp cho từng trường hợp để biểu thức trả về kết quả dễ dự đoán.
