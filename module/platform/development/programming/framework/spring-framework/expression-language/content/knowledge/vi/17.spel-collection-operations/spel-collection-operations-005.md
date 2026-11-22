# Thao tác với map entry, key và value trong SpEL

Trong Spring Expression Language (SpEL), Map không chỉ là cấu trúc để tra cứu một value bằng key. SpEL còn có thể lọc các entry theo key hoặc value, lấy riêng danh sách key/value, và biến mỗi entry thành một cấu trúc dữ liệu khác bằng selection và projection.

Khi selection chạy trên Map, phần tử hiện tại là một Map.Entry nên có thể truy cập hai thuộc tính key và value. Selection giữ lại các cặp key-value phù hợp và trả về một Map. Projection áp dụng biểu thức trên từng entry và trả về một List các kết quả. Hiểu sự khác nhau này giúp chọn đúng thao tác và tránh nhầm hình dạng dữ liệu đầu ra.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Truy cập value của Map bằng key.
- Dùng selection để lọc Map theo key hoặc value.
- Đọc key và value của entry hiện tại bằng key, value hoặc #this.
- Dùng projection để tạo danh sách key, value hoặc dữ liệu tổng hợp.
- Kết hợp selection và projection trong một biểu thức.
- Xử lý key/value null và kiểu dữ liệu không đồng nhất.
- Phân biệt thao tác trên Map với thao tác trên entrySet(), keySet() và values().
- Hiểu thứ tự phần tử kết quả và giới hạn của thao tác inline.

Bạn nên biết cú pháp Map inline, collection selection .?[...], projection .![...] và cách truyền biến vào EvaluationContext.

## 2. Cấu trúc Map và Map.Entry

Map lưu dữ liệu theo cặp key-value. Ví dụ:

~~~java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("BOOK", 12);
stock.put("PEN", 40);
stock.put("BAG", 5);
~~~

Có thể hình dung dữ liệu:

| Key | Value |
|---|---:|
| BOOK | 12 |
| PEN | 40 |
| BAG | 5 |

Mỗi cặp trong Map được biểu diễn bởi một Map.Entry. Entry có hai thành phần:

- key: khóa dùng để tra cứu entry.
- value: dữ liệu được gắn với khóa.

Khi SpEL thực hiện selection hoặc projection trên Map, biểu thức bên trong được đánh giá trên entry hiện tại. Vì vậy có thể dùng trực tiếp key và value:

~~~text
#stock.?[value > 10]
~~~

Hoặc viết tường minh:

~~~text
#stock.?[#this.value > 10]
~~~

Trong predicate, #this đại diện Map.Entry hiện tại.

## 3. Truy cập value theo key

Nếu đã biết key và chỉ cần lấy một value, dùng cú pháp index:

~~~text
#stock['BOOK']
~~~

Khi key nằm trong biến:

~~~text
#stock[#requestedCode]
~~~

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#stock[#code]");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("stock", stock);
context.setVariable("code", "PEN");

Integer quantity =
    expression.getValue(context, Integer.class);
~~~

Kết quả là 40.

Indexing phù hợp khi đã biết key cần tra cứu. Nếu cần tìm nhiều entry theo một điều kiện, selection thường phù hợp hơn.

Cần phân biệt hai trường hợp:

- Key không tồn tại trong Map.
- Key tồn tại nhưng value của nó là null.

Cả hai có thể cho kết quả đọc là null. Nếu ứng dụng cần phân biệt, hãy kiểm tra containsKey(key) trong Java hoặc thực hiện một bước kiểm tra riêng trước khi sử dụng value.

## 4. Selection: lọc Map theo value

Selection dùng cú pháp .?[condition]. Với Map, điều kiện được đánh giá trên từng Map.Entry.

Ví dụ chỉ giữ những mặt hàng có số lượng lớn hơn 10:

~~~text
#stock.?[value > 10]
~~~

Kết quả là một Map mới gồm các entry phù hợp:

~~~text
{
    'BOOK': 12,
    'PEN': 40
}
~~~

Selection trên Map giữ nguyên key và value của các entry được chọn. Kết quả vẫn có cấu trúc Map, không phải List.

Có thể lọc theo một giá trị cụ thể:

~~~text
#stock.?[value == 5]
~~~

Hoặc kết hợp điều kiện:

~~~text
#stock.?[value >= 10 and key != 'PEN']
~~~

Biểu thức này giữ entry có value ít nhất 10 và key khác PEN.

## 5. Selection theo key

Vì entry hiện tại cung cấp key, có thể lọc Map theo nội dung khóa.

Ví dụ chỉ giữ các key bắt đầu bằng chữ B:

~~~text
#stock.?[key.startsWith('B')]
~~~

Có thể dùng #this để làm rõ rằng startsWith được gọi trên key của entry:

~~~text
#stock.?[#this.key.startsWith('B')]
~~~

Nếu key có thể null, hãy đặt kiểm tra null trước khi gọi method:

~~~text
#stock.?[key != null and key.startsWith('B')]
~~~

AND short-circuit bảo đảm startsWith chỉ được gọi khi key khác null.

Key của Map runtime không nhất thiết phải là String. Nếu Map có key kiểu số, enum hoặc object tùy chỉnh, hãy dùng phép so sánh và method phù hợp với kiểu thực tế. Không gọi startsWith trên key không phải chuỗi.

## 6. Kết hợp điều kiện key và value

Có thể lọc theo nhiều thuộc tính của cùng một entry:

~~~text
#stock.?[key.startsWith('B') and value >= 10]
~~~

Map chỉ giữ các entry có key bắt đầu bằng B và số lượng ít nhất 10.

Có thể dùng OR:

~~~text
#stock.?[key == 'BOOK' or value == 5]
~~~

Và phủ định:

~~~text
#stock.?[not (key == 'BAG')]
~~~

Khi điều kiện có nhiều AND/OR, hãy đặt dấu ngoặc để thể hiện nhóm logic:

~~~text
#stock.?[(key == 'BOOK' or key == 'PEN') and value > 10]
~~~

Điều này làm rõ rằng key phải thuộc một trong hai lựa chọn và value vẫn phải lớn hơn 10.

## 7. Projection: lấy danh sách key hoặc value

Projection dùng cú pháp .![expression]. Với Map, biểu thức được áp dụng cho từng Map.Entry và kết quả là một List.

Lấy toàn bộ key:

~~~text
#stock.![key]
~~~

Kết quả:

~~~text
{'BOOK', 'PEN', 'BAG'}
~~~

Lấy toàn bộ value:

~~~text
#stock.![value]
~~~

Kết quả:

~~~text
{12, 40, 5}
~~~

Trong hai ví dụ trên, kết quả là List theo thứ tự duyệt entry của Map nguồn. Projection không trả về Map vì mỗi entry đã được biến thành một giá trị đơn.

Có thể viết rõ bằng #this:

~~~text
#stock.![#this.key]
~~~

~~~text
#stock.![#this.value]
~~~

Dùng key và value trực tiếp thường gọn hơn; #this hữu ích khi expression có nhiều tầng hoặc cần tránh nhầm với biến/property khác.

## 8. Kết hợp selection và projection

Một quy trình phổ biến là lọc entry trước, sau đó lấy key hoặc value của những entry còn lại.

Ví dụ lấy key của các mặt hàng có số lượng lớn hơn 10:

~~~text
#stock.?[value > 10].![key]
~~~

Các bước:

1. Selection lọc Map và giữ các entry có value > 10.
2. Projection chạy trên Map kết quả.
3. Mỗi entry được biến thành key.
4. Kết quả cuối cùng là List key.

Lấy value của những key bắt đầu bằng B:

~~~text
#stock.?[key.startsWith('B')].![value]
~~~

Nếu cần giữ cả key và value, hãy dừng sau selection để nhận Map. Nếu cần danh sách key/value để hiển thị hoặc xử lý tiếp, hãy dùng projection.

## 9. Tạo cấu trúc đầu ra cho từng entry

Projection có thể tạo một Map inline cho mỗi entry. Ví dụ:

~~~text
#stock.![{'code': key, 'quantity': value}]
~~~

Kết quả là một List các Map nhỏ:

~~~text
[
    {'code': 'BOOK', 'quantity': 12},
    {'code': 'PEN', 'quantity': 40},
    {'code': 'BAG', 'quantity': 5}
]
~~~

Có thể tính thêm trường trong value:

~~~text
#stock.![{
    'code': key,
    'quantity': value,
    'lowStock': value < 10
}]
~~~

Cách này hữu ích khi tạo dữ liệu trình bày hoặc một cấu trúc trung gian nhỏ. Nếu output có schema cố định được dùng ở nhiều nơi, hãy cân nhắc DTO có kiểu trong Java thay vì List<Map<String, Object>>.

## 10. Xử lý key và value null

Map có thể chứa key null hoặc value null tùy implementation. Vì vậy, predicate nên phản ánh rõ kiểu dữ liệu và chính sách null.

Ví dụ chỉ giữ entry có value khác null và lớn hơn 0:

~~~text
#stock.?[value != null and value > 0]
~~~

Do AND short-circuit, phép so sánh value > 0 chỉ chạy khi value khác null.

Lọc các key khác null:

~~~text
#stock.?[key != null]
~~~

Nếu key là String nhưng có thể null:

~~~text
#stock.?[key != null and key.startsWith('A')]
~~~

Không phải mọi Map implementation đều cho phép key null hoặc value null. Hãy kiểm tra hợp đồng của Map thực tế. Null-safe navigation trên Map receiver cũng là vấn đề riêng: nếu chính biến stock là null, selection thông thường không thể bắt đầu.

Spring Framework 6.2 trở lên hỗ trợ null-safe selection và projection trên collection/map:

~~~text
#stock?.?[value != null and value > 0]
~~~

~~~text
#stock?.![key]
~~~

Với phiên bản trước 6.2, hãy kiểm tra Map khác null trước khi thực hiện selection hoặc projection. Null-safe selection bảo vệ Map receiver; nó không tự sửa key/value null bên trong entry.

## 11. So sánh selection/projection với keySet, values và entrySet

Java Map API cung cấp các view quen thuộc:

- keySet(): tập key.
- values(): collection các value.
- entrySet(): tập Map.Entry.

Trong SpEL, có thể gọi các method này nếu MethodResolver và EvaluationContext cho phép:

~~~text
#stock.keySet()
~~~

~~~text
#stock.values()
~~~

~~~text
#stock.entrySet()
~~~

So sánh cách dùng:

| Nhu cầu | Cách viết SpEL |
|---|---|
| Lấy value của một key đã biết | #stock['BOOK'] |
| Lọc Map theo value | #stock.?[value > 10] |
| Lọc Map theo key | #stock.?[key.startsWith('B')] |
| Lấy danh sách key | #stock.![key] hoặc #stock.keySet() |
| Lấy danh sách value | #stock.![value] hoặc #stock.values() |
| Lấy entry set | #stock.entrySet() |

Selection và projection hữu ích khi cần lọc hoặc biến đổi bằng expression. Các method Java phù hợp khi code cần thao tác collection tổng quát hoặc khi muốn giữ logic trong Java. Việc gọi method còn phụ thuộc quyền trong context; không giả định mọi method đều được phép.

## 12. Thứ tự kết quả và Map implementation

Selection trả về Map kết quả; projection trả về List kết quả. Thứ tự duyệt phụ thuộc vào Map implementation nguồn.

- LinkedHashMap duy trì thứ tự chèn.
- TreeMap duy trì thứ tự theo comparator của key.
- HashMap không bảo đảm thứ tự duyệt ổn định.

Projection giữ thứ tự duyệt của collection nguồn tại thời điểm đánh giá. Nếu thứ tự là yêu cầu nghiệp vụ, hãy chọn Map implementation phù hợp hoặc sắp xếp kết quả rõ ràng trong Java. Đừng dựa vào thứ tự quan sát được từ một HashMap trong một lần chạy.

Selection tạo Map kết quả mới, nhưng value trong kết quả vẫn có thể là cùng object reference với Map nguồn. Đây không phải deep copy. Nếu value là object mutable, thay đổi object đó vẫn có thể ảnh hưởng nơi khác đang giữ cùng tham chiếu.

## 13. Đánh giá bằng Java và EvaluationContext

Ví dụ đầy đủ:

~~~java
Map<String, Integer> stock = new LinkedHashMap<>();
stock.put("BOOK", 12);
stock.put("PEN", 40);
stock.put("BAG", 5);

ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("stock", stock);

Expression filter =
    parser.parseExpression("#stock.?[value > 10]");

Map<?, ?> filtered =
    filter.getValue(context, Map.class);

Expression keys =
    parser.parseExpression("#stock.?[value > 10].![key]");

List<?> selectedKeys =
    keys.getValue(context, List.class);
~~~

filtered là Map giữ entry BOOK và PEN. selectedKeys là List chứa BOOK và PEN theo thứ tự duyệt của LinkedHashMap.

Truyền Map qua biến giúp tách dữ liệu runtime khỏi chuỗi expression. Không cần ghép nội dung Map vào chuỗi SpEL.

## 14. Selection và projection có sửa Map nguồn không?

Selection và projection được dùng để tạo kết quả từ Map nguồn. Chúng không đồng nghĩa với việc cập nhật Map nguồn:

~~~text
#stock.?[value > 10]
~~~

lọc các entry và trả Map kết quả.

~~~text
#stock.![value * 2]
~~~

tạo List các giá trị đã nhân đôi; nó không ghi ngược các giá trị mới vào Map nguồn.

Tuy nhiên, nếu expression bên trong gọi method có tác dụng phụ hoặc thực hiện phép gán trên object mutable, những hành động đó vẫn có thể thay đổi trạng thái. Hãy giữ predicate và projection chỉ đọc khi mục tiêu là truy vấn dữ liệu. Thực hiện cập nhật Map bằng Java với luồng kiểm soát rõ ràng.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy key/value trong predicate | Expression không chạy trên Map hoặc ngữ cảnh hiện tại không phải Map.Entry | Kiểm tra kiểu nguồn và dùng #this.key/#this.value |
| Selection trả về Map thay vì List | Selection giữ lại entry phù hợp | Dùng projection nếu cần List |
| Projection trả List thay vì Map | Projection biến mỗi entry thành một giá trị | Dùng selection nếu cần giữ cặp key-value |
| Gọi startsWith bị lỗi | Key không phải String hoặc key null | Kiểm tra null và kiểu key trước |
| So sánh value lỗi | Value null hoặc kiểu không tương thích | Kiểm tra null và kiểu dữ liệu |
| Kết quả có thứ tự khác dự kiến | Map nguồn không bảo đảm thứ tự | Dùng LinkedHashMap/TreeMap hoặc sắp xếp trong Java |
| Map nguồn null | Selection/projection không thể bắt đầu | Guard Map hoặc dùng null-safe operator trên Spring 6.2+ |
| Thay đổi value ảnh hưởng nơi khác | Value là object reference dùng chung | Tạo bản sao phù hợp hoặc tránh mutation trong expression |

## 16. Bài tập thực hành

1. Tạo Map<String, Integer> chứa mã sản phẩm và số lượng.
2. Dùng selection lấy các entry có value lớn hơn 10.
3. Lọc các key bắt đầu bằng chữ B.
4. Lấy danh sách key bằng projection.
5. Lấy danh sách value bằng projection.
6. Kết hợp selection và projection để lấy key của entry có value lớn hơn một ngưỡng.
7. Tạo List<Map<String, Object>> từ từng entry với code, quantity và lowStock.
8. Thử entry có value null và thêm guard phù hợp.
9. So sánh kết quả của .![key] với keySet().
10. Chạy cùng biểu thức trên HashMap, LinkedHashMap và TreeMap để quan sát thứ tự.
11. Kiểm tra Map null và Map rỗng riêng biệt.
12. Xác nhận selection/projection không ghi ngược value vào Map nguồn.

## 17. Checklist trước khi dùng Map operations

- [ ] Nguồn có thực sự là Map không?
- [ ] Đã phân biệt Map.Entry với key và value đơn lẻ chưa?
- [ ] Đã dùng selection khi muốn giữ cặp key-value chưa?
- [ ] Đã dùng projection khi muốn tạo List kết quả chưa?
- [ ] Predicate có kiểm tra key/value null trước khi gọi method hoặc so sánh không?
- [ ] Kiểu key và value có đúng với phép toán không?
- [ ] Đã xác định thứ tự duyệt của Map implementation chưa?
- [ ] Đã phân biệt Map null với Map rỗng chưa?
- [ ] Có method side effect hoặc phép gán trong predicate/projection không?
- [ ] Đã kiểm thử cả kết quả và kiểu dữ liệu đầu ra chưa?

## 18. Kết luận

Trong SpEL, selection trên Map làm việc với từng Map.Entry: key đại diện khóa và value đại diện dữ liệu. Selection .?[...] giữ lại các entry phù hợp và trả về Map; projection .![...] biến từng entry thành kết quả và trả về List. Có thể lọc theo key/value, lấy riêng key hoặc value, tạo map summary cho từng entry và kết hợp selection với projection. Hãy kiểm soát null, kiểu dữ liệu và thứ tự duyệt, đồng thời giữ các biểu thức truy vấn chỉ đọc. Khi cần cập nhật Map hoặc xử lý phức tạp, Java Map API thường thể hiện ý định rõ ràng hơn.