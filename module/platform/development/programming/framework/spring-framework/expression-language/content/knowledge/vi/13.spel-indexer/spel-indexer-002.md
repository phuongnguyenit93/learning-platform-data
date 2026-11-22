# Indexer trên map theo key

SpEL dùng cú pháp indexer với dấu ngoặc vuông để truy cập phần tử của Map theo key. Thay vì đọc dữ liệu theo vị trí như với List hoặc array, biểu thức cung cấp key để lấy giá trị tương ứng trong map.

Cú pháp này hữu ích khi dữ liệu được tổ chức thành các cặp key-value, chẳng hạn cấu hình, thuộc tính mở rộng, thông tin người dùng, metadata hoặc kết quả trả về từ một API. Key có thể là chuỗi, số hoặc một object có kiểu phù hợp với key của Map. Hiểu rõ kiểu key và cách xử lý key không tồn tại giúp biểu thức tránh đọc nhầm hoặc ghi nhầm dữ liệu.

## 1. Cú pháp truy cập Map theo key

Cú pháp cơ bản:

~~~text
#settings['region']
#settings['language']
#settings['timeout']
~~~

Trong ví dụ, settings là biến chứa Map trong EvaluationContext. Nội dung giữa cặp ngoặc vuông là biểu thức xác định key. Dấu nháy đơn tạo string literal, vì vậy 'region' là một key kiểu String.

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Map<String, Object> settings = new HashMap<>();
settings.put("region", "ap-southeast-1");
settings.put("language", "vi");
settings.put("timeout", 30);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("settings", settings);

Expression expression =
        parser.parseExpression("#settings['region']");

String region = expression.getValue(context, String.class);

System.out.println(region); // ap-southeast-1
~~~

SpEL đánh giá biểu thức #settings để lấy Map, sau đó dùng key 'region' để lấy value. Giá trị trả về của indexer là value được lưu dưới key đó.

Hãy dùng dấu ngoặc vuông khi mục tiêu là truy cập một key cụ thể của Map. Cách viết này thể hiện rõ thao tác tra cứu key-value và tránh nhầm với truy cập property của một Java object.

## 2. Key là một biến động

Key không bắt buộc phải là literal cố định. Có thể đặt key trong biến của EvaluationContext rồi dùng biến đó bên trong indexer.

~~~java
Map<String, Object> settings = new HashMap<>();
settings.put("region", "ap-southeast-1");
settings.put("language", "vi");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("settings", settings);
context.setVariable("selectedKey", "language");

Expression expression =
        parser.parseExpression("#settings[#selectedKey]");

Object value = expression.getValue(context);

System.out.println(value); // vi
~~~

Ở đây #selectedKey được đánh giá trước để lấy chuỗi language, sau đó Map được tra cứu bằng key đó. Cách làm này hữu ích khi key phụ thuộc vào request, lựa chọn người dùng hoặc một giá trị được tính từ phần khác của biểu thức.

Có thể dùng một biến để chọn key mà không phải tạo một chuỗi biểu thức mới cho từng key. Điều này giúp tái sử dụng Expression và giữ dữ liệu đầu vào tách khỏi cú pháp SpEL.

## 3. Key có thể là kết quả của một biểu thức

Nội dung trong ngoặc vuông được đánh giá như một biểu thức SpEL. Vì vậy, key có thể được tạo từ một biến, property hoặc kết quả của phép tính.

~~~text
#settings[#prefix + 'Region']
#settings[#request.locale]
#settings[#selectedKeys[0]]
~~~

Ví dụ:

~~~java
Map<String, String> labels = new HashMap<>();
labels.put("message.vi", "Xin chào");
labels.put("message.en", "Hello");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("labels", labels);
context.setVariable("locale", "vi");

Expression expression = parser.parseExpression(
        "#labels['message.' + #locale]"
);

String message = expression.getValue(context, String.class);
~~~

Biểu thức tạo key message.vi bằng cách nối chuỗi message. với giá trị của biến locale. Map trả về giá trị tương ứng với key vừa tạo.

Khi key được tính toán, hãy kiểm tra giá trị cuối cùng và kiểu dữ liệu của nó. Một key sai chính tả hoặc khác kiểu vẫn có thể dẫn đến kết quả không tìm thấy phần tử dù Map đang chứa dữ liệu gần giống.

## 4. Phân biệt key String với key số

Kiểu của key là một phần của danh tính key trong Map. Một Map có thể chứa key String "1001" và key Integer 1001 như hai phần tử khác nhau.

Ví dụ:

~~~java
Map<Object, String> values = new HashMap<>();
values.put("1001", "string key");
values.put(1001, "integer key");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("values", values);

Object stringValue = parser.parseExpression(
        "#values['1001']"
).getValue(context);

Object integerValue = parser.parseExpression(
        "#values[1001]"
).getValue(context);
~~~

Hai biểu thức tra cứu hai key có kiểu khác nhau. Không nên mặc định rằng SpEL sẽ tự chuyển mọi key sang String hoặc Integer theo ý người viết.

Với Map có key là Integer, có thể dùng literal số:

~~~text
#codes[1001]
~~~

Với Map có key là enum hoặc một kiểu object khác, hãy truyền biến có đúng kiểu key:

~~~java
context.setVariable("statusKey", OrderStatus.ACTIVE);

Expression expression =
        parser.parseExpression("#statusLabels[#statusKey]");
~~~

Việc tìm thấy phần tử phụ thuộc vào quy tắc equals() và hashCode() của kiểu key cũng như key thực tế được lưu trong Map. Với key là object tự định nghĩa, hãy đảm bảo implementation equals/hashCode ổn định và nhất quán.

## 5. Truy cập Map lồng nhau

Một Map có thể chứa value là Map khác. Có thể nối nhiều indexer để truy cập sâu vào cấu trúc key-value.

Ví dụ cấu hình:

~~~java
Map<String, Object> mail = new HashMap<>();
mail.put("host", "smtp.example.com");
mail.put("port", 587);

Map<String, Object> config = new HashMap<>();
config.put("mail", mail);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("config", config);

Expression expression = parser.parseExpression(
        "#config['mail']['host']"
);

String host = expression.getValue(context, String.class);
~~~

SpEL thực hiện hai bước tra cứu: trước hết lấy value của key mail từ config, sau đó lấy key host trong Map con. Mỗi tầng đều phải trả về một object có thể được index theo cách tiếp theo.

Có thể truy cập sâu hơn:

~~~text
#config['mail']['smtp']['host']
#config['features']['checkout']['enabled']
~~~

Nếu một key trung gian không tồn tại hoặc value tại đó là null, biểu thức tiếp tục index có thể phát sinh lỗi. Với cấu trúc lồng sâu, nên kiểm tra từng tầng hoặc chuẩn hóa dữ liệu trước khi đánh giá.

## 6. Phân biệt key không tồn tại với value null

Khi Map không chứa key, thao tác tra cứu thông thường trả về null. Nhưng null cũng có thể là value được lưu hợp lệ trong Map. Vì vậy, chỉ kiểm tra kết quả indexer bằng null không đủ để phân biệt hai tình huống.

Ví dụ:

~~~java
Map<String, Object> values = new HashMap<>();
values.put("presentNull", null);

System.out.println(values.containsKey("presentNull")); // true
System.out.println(values.containsKey("missing"));     // false
~~~

Nếu cần phân biệt, hãy dùng containsKey():

~~~text
#settings.containsKey('region')
~~~

Có thể kiểm tra key trước khi đọc:

~~~text
#settings.containsKey('region') and #settings['region'] != null
~~~

Do AND có short-circuit, nếu key không tồn tại thì vế phải không được đánh giá. Cách này tránh đọc tiếp value khi điều kiện đầu tiên đã false.

Với Map lồng nhau, hãy kiểm tra từng tầng trước khi index tầng tiếp theo. Ví dụ:

~~~text
#config.containsKey('mail') and #config['mail'] != null
~~~

Sau khi xác nhận mail tồn tại và khác null, mới đánh giá biểu thức đọc host. Nếu cần kiểm tra nhiều tầng trong một rule, hãy nhóm điều kiện bằng ngoặc để thể hiện rõ thứ tự.

## 7. Dùng indexer để cập nhật value trong Map

Indexer không chỉ dùng để đọc. Khi EvaluationContext và Map cho phép ghi, có thể gán value cho một key:

~~~java
Map<String, Object> settings = new HashMap<>();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("settings", settings);

Expression assignment = parser.parseExpression(
        "#settings['theme'] = 'dark'"
);

assignment.getValue(context);

System.out.println(settings.get("theme")); // dark
~~~

Nếu key chưa tồn tại, phép gán có thể thêm một entry mới vào Map mutable. Nếu key đã tồn tại, value tương ứng được thay thế.

Có thể dùng Expression.setValue để tách đường dẫn key khỏi giá trị mới:

~~~java
Expression theme = parser.parseExpression(
        "#settings['theme']"
);

theme.setValue(context, "light");
~~~

Cả hai cách đều thay đổi Map. Khả năng ghi phụ thuộc Map có hỗ trợ sửa đổi hay không và context có property/indexer access cho phép ghi hay không. Map bất biến hoặc Map chỉ đọc có thể từ chối thao tác và phát sinh exception.

Hãy nhớ rằng gán vào Map là thay đổi trạng thái object. Nếu Map được chia sẻ hoặc dùng làm cấu hình chung, thay đổi có thể ảnh hưởng đến các phần khác của ứng dụng.

## 8. Dùng Map key trong điều kiện và biểu thức kết hợp

Giá trị lấy từ Map có thể được dùng trực tiếp trong so sánh, phép toán hoặc điều kiện logic.

~~~text
#settings['retryCount'] > 3
#settings['region'] == 'ap-southeast-1'
#settings['enabled'] == true
#settings['price'] * #settings['quantity']
~~~

Ví dụ:

~~~java
Map<String, Object> orderData = new HashMap<>();
orderData.put("price", new BigDecimal("19.90"));
orderData.put("quantity", new BigDecimal("3"));

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orderData", orderData);

Expression expression = parser.parseExpression(
        "#orderData['price'] * #orderData['quantity']"
);

BigDecimal total = expression.getValue(context, BigDecimal.class);
~~~

Trong trường hợp này, Map lưu dữ liệu theo key và biểu thức tính tổng từ hai value. Kiểu số của value ảnh hưởng đến phép toán và kiểu kết quả. Nếu Map chứa Object, hãy đảm bảo các value có kiểu phù hợp với phép tính mà biểu thức thực hiện.

Với dữ liệu không đồng nhất, nên kiểm tra kiểu trước hoặc chuyển đổi dữ liệu ở tầng Java. Không nên giả định mọi value trong Map đều là số chỉ vì một vài entry hiện tại có kiểu BigDecimal.

## 9. Map key và property access là hai cách truy cập khác nhau

Map lưu dữ liệu theo key, còn Java object thường cung cấp dữ liệu qua property hoặc getter. Với Map, cú pháp indexer thể hiện rõ key cần tra cứu:

~~~text
#settings['region']
~~~

Với object có property region, cách viết thông thường là:

~~~text
#profile.region
~~~

Không nên thay indexer bằng property access chỉ vì key của Map trông giống tên thuộc tính. Dấu ngoặc vuông giúp thể hiện rằng chuỗi region là một key trong Map.

Sự phân biệt này đặc biệt quan trọng khi cấu trúc dữ liệu đến từ JSON hoặc API. Một object JSON có thể được chuyển thành Map; khi đó các trường JSON trở thành key-value entry. Nếu dữ liệu được chuyển thành DTO Java, chúng lại được truy cập qua property tương ứng.

## 10. Kết hợp Map với List và object

Map có thể chứa List, array hoặc object khác. SpEL cho phép kết hợp indexer Map với indexer theo vị trí hoặc property access.

Ví dụ cấu trúc dữ liệu:

~~~java
Map<String, Object> response = new HashMap<>();
response.put("items", List.of(
        Map.of("sku", "A-01"),
        Map.of("sku", "B-02")
));

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("response", response);
~~~

Có thể đọc SKU đầu tiên:

~~~text
#response['items'][0]['sku']
~~~

Đường dẫn gồm ba bước: lấy key items trong Map ngoài, lấy phần tử ở vị trí 0 của List, rồi lấy key sku trong Map con.

Với cấu trúc kết hợp nhiều collection, hãy tách đường dẫn thành từng bước khi debug. Nếu một bước trả về null hoặc một kiểu không hỗ trợ indexer tiếp theo, lỗi thường xuất hiện tại bước sau chứ không nhất thiết ở key đầu tiên.

## 11. Map và các loại triển khai

Cú pháp indexer của SpEL làm việc với Map interface, vì vậy có thể dùng các implementation phổ biến như:

- HashMap: tra cứu key thông qua hashCode/equals, không đảm bảo thứ tự lặp.
- LinkedHashMap: giữ thứ tự chèn entry.
- TreeMap: sắp xếp key theo comparator hoặc thứ tự tự nhiên.
- EnumMap: dùng enum làm key, phù hợp với tập key enum cố định.
- Map bất biến: phù hợp cho dữ liệu chỉ đọc, không chấp nhận ghi.

Cách tra cứu theo key vẫn dựa trên hợp đồng của Map. Khác biệt giữa các implementation ảnh hưởng đến thứ tự, hiệu năng, khả năng null key và khả năng cập nhật.

Nếu biểu thức chỉ đọc, hãy cân nhắc cung cấp Map không thể sửa đổi hoặc một bản sao chỉ đọc. Nếu biểu thức cần ghi, hãy xác nhận Map thực sự hỗ trợ thao tác đó và object không bị chia sẻ ngoài phạm vi dự kiến.

## 12. Kiểm soát dữ liệu và an toàn khi dùng Map trong SpEL

Map thường chứa dữ liệu linh hoạt, có thể đến từ request, JSON, cấu hình hoặc database. Vì vậy, key và value có thể thiếu, sai kiểu hoặc do nguồn bên ngoài kiểm soát.

Một số nguyên tắc thực hành:

1. Xác định rõ kiểu key và kiểu value của Map.
2. Dùng string literal có dấu nháy đơn cho key String.
3. Dùng biến có kiểu phù hợp khi key là số, enum hoặc object tùy chỉnh.
4. Kiểm tra containsKey và null trước khi truy cập sâu.
5. Chuẩn hóa dữ liệu đầu vào trước khi đánh giá biểu thức.
6. Chỉ cho phép ghi vào Map khi use case yêu cầu.
7. Không đưa Map chứa bí mật hoặc dữ liệu nội bộ không cần thiết vào context.
8. Dùng EvaluationContext hạn chế nếu biểu thức có thể được chỉnh sửa bởi người không tin cậy.

Đặc biệt, không nên xem việc dùng Map thay cho entity là một biện pháp bảo mật tự động. Nếu Map chứa toàn bộ thông tin nhạy cảm, biểu thức vẫn có thể đọc các key đó khi context cho phép.

## 13. Chẩn đoán lỗi khi index Map

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Kết quả trả về null | Key không tồn tại hoặc value thực sự là null | Dùng containsKey để phân biệt |
| Không tìm thấy key dù nhìn thấy cùng ký tự | Kiểu key thực tế khác kiểu trong biểu thức | Kiểm tra class của key |
| Truy cập Map lồng nhau bị lỗi | Một tầng trung gian không tồn tại hoặc null | Kiểm tra từng key theo thứ tự |
| Gán key thất bại | Map bất biến hoặc accessor không cho phép ghi | Kiểm tra implementation và quyền ghi |
| Key động không đúng | Biến hoặc biểu thức tạo key trả về giá trị khác mong đợi | In hoặc kiểm tra giá trị key trước khi tra cứu |
| Value không dùng được trong phép toán | Value có kiểu không tương thích | Kiểm tra runtime type và chuyển đổi |
| Biểu thức đọc nhầm property | Dùng dấu chấm thay vì indexer cho Map | Dùng cú pháp map['key'] rõ ràng |

Khi debug, có thể kiểm tra Map trực tiếp trong Java trước khi đánh giá SpEL: in keySet, kiểm tra containsKey và lấy class của key/value. Sau đó đánh giá một biểu thức indexer đơn giản trước khi nối nhiều tầng hoặc thêm phép toán.

## 14. Ghi nhớ

Indexer trên Map dùng dấu ngoặc vuông và key để lấy value, ví dụ #settings['region']. Key có thể là literal, biến hoặc kết quả của một biểu thức. Kiểu key rất quan trọng: String "1001" và Integer 1001 là hai key khác nhau.

Có thể nối nhiều indexer để truy cập Map lồng nhau hoặc kết hợp Map với List và object. Nếu key không tồn tại, kết quả tra cứu thường là null; hãy dùng containsKey khi cần phân biệt key thiếu với value null. Indexer cũng có thể ghi value nếu Map và EvaluationContext cho phép.

Hãy xác định kiểu key/value, kiểm tra các tầng dữ liệu trước khi truy cập sâu, và chỉ cấp quyền ghi khi thật sự cần. Cách dùng indexer rõ ràng giúp biểu thức SpEL làm việc với dữ liệu key-value linh hoạt mà vẫn dễ hiểu và kiểm soát.