# Toán tử gán và tác dụng phụ lên object đích trong Spring Expression Language

Spring Expression Language (SpEL) không chỉ đọc dữ liệu và tính toán. Nó còn có thể ghi giá trị vào thuộc tính của đối tượng khi biểu thức đích có thể ghi (writable). Khả năng này được thực hiện bằng toán tử gán \`=\` hoặc API \`Expression.setValue(...)\`.

Khi một phép gán được đánh giá, trạng thái của object đích có thể thay đổi. Thay đổi đó tồn tại sau lần đánh giá và có thể được nhìn thấy từ những phần khác của ứng dụng đang giữ cùng tham chiếu đến object.

Để sử dụng đúng tính năng này, cần phân biệt phép gán với phép so sánh, hiểu biểu thức đích nào có thể ghi, và biết khi nào lời gọi đánh giá có thể tạo tác dụng phụ (side effect).

## 1. Toán tử gán trong SpEL

SpEL dùng dấu bằng đơn \`=\` để gán một giá trị cho một biểu thức đích có thể ghi.

Ví dụ:

~~~spel
status = 'PAID'
~~~

Biểu thức này yêu cầu đặt giá trị \`PAID\` vào thuộc tính \`status\` của đối tượng hiện tại, nếu thuộc tính đó có thể ghi.

Cần phân biệt hai toán tử:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| \`=\` | Gán giá trị vào đích | \`status = 'PAID'\` |
| \`==\` | So sánh hai giá trị có bằng nhau không | \`status == 'PAID'\` |

Phép so sánh chỉ kiểm tra điều kiện và tạo ra giá trị Boolean. Phép gán thay đổi trạng thái của đích. Nhầm lẫn hai cú pháp này có thể khiến biểu thức làm thay đổi object ngoài ý muốn.

## 2. Gán thuộc tính bằng Expression.setValue

Cách tường minh để ghi giá trị là phân tích biểu thức chỉ đến thuộc tính, sau đó gọi \`setValue\`.

Giả sử có lớp Order:

~~~java
public class Order {
    private String status;

    public Order(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Ứng dụng có thể thay đổi trạng thái như sau:

~~~java
Order order = new Order("PENDING");

ExpressionParser parser = new SpelExpressionParser();
Expression statusExpression = parser.parseExpression("status");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

// Ghi giá trị vào thuộc tính status của order.
statusExpression.setValue(context, "PAID");

System.out.println(order.getStatus());
~~~

Kết quả:

~~~text
PAID
~~~

Trong ví dụ:

1. \`order\` được đặt làm root object của context.
2. Biểu thức \`status\` xác định thuộc tính cần ghi trên root object.
3. \`setValue(context, "PAID")\` yêu cầu SpEL ghi giá trị mới.
4. Khi đọc lại \`order.getStatus()\`, ứng dụng thấy trạng thái đã thay đổi.

\`setValue\` là API chuyên biệt cho việc gán giá trị vào đích của một Expression. Cách này giúp ý định ghi dữ liệu thể hiện rõ trong mã Java.

## 3. Gán trực tiếp bằng toán tử = trong biểu thức

SpEL cũng cho phép đặt phép gán ngay trong chuỗi biểu thức. Khi biểu thức gán được đánh giá bằng \`getValue\`, thao tác ghi sẽ được thực hiện.

~~~java
Order order = new Order("PENDING");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

ExpressionParser parser = new SpelExpressionParser();

Expression assignment =
    parser.parseExpression("status = 'PAID'");

// Việc đánh giá biểu thức này thực hiện phép gán.
assignment.getValue(context);

System.out.println(order.getStatus());
~~~

Kết quả:

~~~text
PAID
~~~

Đây là điểm quan trọng: một lời gọi có tên \`getValue\` thông thường được dùng để lấy giá trị, nhưng nếu biểu thức chứa phép gán thì quá trình đánh giá cũng có thể thay đổi object đích.

Vì vậy, khi đọc mã SpEL, không thể chỉ dựa vào tên phương thức Java để kết luận rằng lần đánh giá là thao tác chỉ đọc. Cần xem cả nội dung biểu thức.

## 4. Object đích là gì?

Object đích là đối tượng hoặc vị trí mà phép gán tác động đến. Nó thường được xác định thông qua root object hoặc một đường dẫn thuộc tính.

### 4.1. Gán thuộc tính trên root object

Nếu context được tạo với một Order:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

thì biểu thức:

~~~spel
status = 'PAID'
~~~

nhắm đến thuộc tính \`status\` của \`order\`.

Có thể dùng tên thuộc tính đơn giản vì root object là đối tượng hiện tại.

### 4.2. Gán thuộc tính lồng nhau

Giả sử Order có một Customer, và Customer có thuộc tính name. Khi các đối tượng trung gian tồn tại và đường dẫn có thể ghi, biểu thức có thể nhắm đến thuộc tính lồng nhau:

~~~spel
customer.name = 'Linh'
~~~

Nếu root object là Order, SpEL đi theo đường dẫn:

~~~text
Order
  |
  +-- customer
        |
        +-- name  <-- giá trị được gán
~~~

Phép gán tác động lên thuộc tính \`name\` của object Customer mà Order đang tham chiếu. Nó không thay thế toàn bộ Order.

Nếu \`customer\` là null, không thể truy cập thuộc tính \`name\` theo cách thông thường. Ứng dụng phải bảo đảm object trung gian tồn tại hoặc sử dụng cơ chế khởi tạo phù hợp được cấu hình cho SpEL.

### 4.3. Gán phần tử collection hoặc map

Indexer cũng có thể xác định vị trí đích nếu loại dữ liệu và accessor hỗ trợ ghi:

~~~spel
items[0] = 'updated'
settings['theme'] = 'dark'
~~~

Ví dụ thứ nhất ghi vào phần tử đầu tiên của collection có thể thay đổi. Ví dụ thứ hai ghi giá trị cho khóa \`theme\` của map có thể thay đổi.

Khả năng ghi phụ thuộc vào loại collection, chỉ số hoặc khóa hợp lệ, và cơ chế truy cập được cấu hình. Một collection không thể thay đổi hoặc một vị trí không hợp lệ có thể khiến phép gán thất bại.

## 5. Khi nào một biểu thức có thể ghi?

Không phải mọi Expression đều là đích ghi hợp lệ. Biểu thức cần chỉ đến một thuộc tính hoặc vị trí mà SpEL có thể cập nhật.

Các điều kiện thường gặp:

- Đường dẫn thuộc tính phải được giải quyết thành công.
- Đối tượng trung gian trên đường dẫn phải tồn tại khi cần truy cập.
- PropertyAccessor hoặc cơ chế truy cập tương ứng phải hỗ trợ thao tác ghi.
- Thuộc tính phải có setter hoặc cơ chế ghi mà accessor hỗ trợ.
- Giá trị mới phải tương thích với kiểu đích hoặc có thể chuyển đổi bởi TypeConverter.
- Collection hoặc map phải cho phép cập nhật nếu phép gán nhắm đến phần tử của chúng.

Ví dụ, nếu lớp Order chỉ có getter cho \`status\` và không có cơ chế ghi được accessor hỗ trợ, việc gán có thể thất bại.

Một số cách tạo context có chủ đích giới hạn quyền ghi. \`SimpleEvaluationContext.forReadOnlyDataBinding()\` phù hợp với trường hợp chỉ đọc; \`SimpleEvaluationContext.forReadWriteDataBinding()\` hỗ trợ data binding đọc và ghi. Lựa chọn context ảnh hưởng đến những thao tác mà biểu thức có thể thực hiện.

## 6. Tác dụng phụ lên object đích

Tác dụng phụ là thay đổi trạng thái bên ngoài giá trị mà một biểu thức trả về. Với phép gán SpEL, tác dụng phụ quan trọng nhất là object đích bị thay đổi.

Ví dụ:

~~~java
Order order = new Order("PENDING");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

parser.parseExpression("status = 'PAID'").getValue(context);

// Đọc lại object sau khi đánh giá.
String currentStatus = order.getStatus();
~~~

Sau phép gán, \`currentStatus\` là \`PAID\`.

Điều này xảy ra vì context giữ tham chiếu đến chính object \`order\`. SpEL ghi vào object đó; nó không tự tạo một bản sao Order rồi trả về bản sao đã thay đổi.

### 6.1. Thay đổi được nhìn thấy qua các tham chiếu khác

Giả sử hai biến Java cùng trỏ đến một object:

~~~java
Order firstReference = order;
Order secondReference = order;
~~~

Sau khi SpEL thay đổi \`status\` qua context chứa \`firstReference\`, việc đọc \`secondReference.getStatus()\` cũng nhìn thấy giá trị mới. Cả hai biến đều tham chiếu cùng một object trong bộ nhớ.

Do đó, phép gán trong SpEL có thể ảnh hưởng đến logic chạy sau đó, kể cả ở một thành phần khác đang giữ tham chiếu đến cùng object.

### 6.2. Setter có thể thực hiện thêm logic

Khi accessor ghi thuộc tính thông qua setter, setter của ứng dụng có thể thực hiện các hành động khác ngoài việc lưu giá trị:

~~~java
public void setStatus(String status) {
    validateStatus(status);
    this.status = status;
    this.updatedAt = Instant.now();
}
~~~

Nếu SpEL gọi cơ chế ghi sử dụng setter này, những thay đổi như cập nhật \`updatedAt\` hoặc kiểm tra trạng thái cũng có thể xảy ra. Tác dụng phụ khi đó đến từ cả thao tác gán và logic được thực hiện bên trong setter.

Không nên giả định một phép gán thuộc tính luôn chỉ thay đổi đúng một trường dữ liệu.

## 7. Gán thuộc tính lồng nhau: tác động lên object nào?

Xét cấu trúc:

~~~text
Order
  |
  +-- customer ------> Customer
                         |
                         +-- name
~~~

Với biểu thức:

~~~spel
customer.name = 'Linh'
~~~

SpEL sử dụng Order làm root object, đọc thuộc tính customer để lấy tham chiếu đến Customer, rồi ghi giá trị vào name của Customer.

Sau khi đánh giá:

- Tham chiếu customer bên trong Order vẫn trỏ đến object Customer đó.
- Thuộc tính name của Customer mang giá trị mới.
- Những nơi khác đang tham chiếu cùng Customer cũng nhìn thấy thay đổi.

Phân biệt rõ đối tượng gốc và đối tượng đích giúp tránh hiểu nhầm rằng phép gán thuộc tính lồng nhau đã thay thế toàn bộ root object.

## 8. Chuyển đổi kiểu khi gán

Kiểu dữ liệu của giá trị gán cần tương thích với kiểu thuộc tính đích. EvaluationContext có TypeConverter để hỗ trợ những chuyển đổi được phép.

Ví dụ, nếu thuộc tính đích là một kiểu số và giá trị đưa vào là chuỗi biểu diễn số, việc chuyển đổi có thể thành công tùy converter và cấu hình:

~~~java
Expression priceExpression =
    parser.parseExpression("price");

priceExpression.setValue(context, "125000");
~~~

Nếu kiểu đích là BigDecimal và converter hỗ trợ chuyển đổi từ String sang BigDecimal, thuộc tính có thể nhận giá trị tương ứng.

Tuy nhiên, không phải mọi chuỗi đều chuyển được thành mọi kiểu. Giá trị không hợp lệ hoặc không có converter phù hợp có thể khiến thao tác ghi thất bại.

Để tránh lỗi runtime, nên cung cấp giá trị đúng kiểu khi có thể và không dựa vào chuyển đổi ngầm nếu quy tắc dữ liệu cần rõ ràng.

## 9. Phân biệt setValue và toán tử gán trong getValue

Cả hai cách đều có thể thay đổi object đích, nhưng ý định sử dụng khác nhau:

| Cách viết | Mục đích | Ví dụ |
|---|---|---|
| \`Expression.setValue(context, value)\` | Ghi giá trị vào biểu thức đích | \`parseExpression("status").setValue(context, "PAID")\` |
| \`getValue(context)\` với biểu thức gán | Đánh giá một biểu thức có chứa phép gán | \`parseExpression("status = 'PAID'").getValue(context)\` |
| \`getValue(context)\` với biểu thức đọc | Đọc hoặc tính giá trị | \`parseExpression("status == 'PAID'").getValue(context)\` |

Khi mã Java thực hiện cập nhật dữ liệu một cách tường minh, \`setValue\` thường làm ý định rõ hơn. Khi biểu thức cần chứa logic gán như một phần của cú pháp, có thể sử dụng toán tử \`=\`.

Cần lưu ý rằng \`getValue\` không bảo đảm biểu thức chỉ đọc. Nếu nội dung biểu thức có phép gán hoặc lời gọi phương thức có tác dụng phụ, object và trạng thái ứng dụng vẫn có thể thay đổi.

## 10. Ví dụ hoàn chỉnh: cập nhật object rồi đọc lại kết quả

Giả sử có lớp Order:

~~~java
public class Order {
    private String status;
    private BigDecimal total;

    public Order(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Ứng dụng muốn cập nhật trạng thái và sau đó kiểm tra giá trị mới:

~~~java
Order order = new Order(
    "PENDING",
    new BigDecimal("750000")
);

ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

// Biểu thức đích chỉ đến thuộc tính status.
Expression statusExpression =
    parser.parseExpression("status");

// Ghi giá trị mới vào object đích.
statusExpression.setValue(context, "PAID");

// Đánh giá biểu thức đọc sau khi cập nhật.
Expression checkExpression =
    parser.parseExpression("status == 'PAID'");

Boolean paid =
    checkExpression.getValue(context, Boolean.class);

System.out.println(order.getStatus());
System.out.println(paid);
~~~

Kết quả:

~~~text
PAID
true
~~~

Luồng xử lý:

1. Order được tạo với trạng thái PENDING.
2. StandardEvaluationContext giữ Order làm root object.
3. statusExpression xác định thuộc tính cần ghi.
4. setValue ghi PAID vào object.
5. checkExpression đọc trạng thái hiện tại và so sánh với PAID.
6. Kết quả Boolean là true.

Ví dụ chứng minh rằng thay đổi do SpEL thực hiện vẫn tồn tại khi đánh giá một biểu thức khác trên cùng context và object.

## 11. Kiểm soát tác dụng phụ và chọn context phù hợp

Khả năng ghi của SpEL hữu ích cho data binding, cấu hình và các quy tắc cập nhật có kiểm soát. Tuy nhiên, nếu biểu thức được lấy từ nguồn không đáng tin cậy, việc cho phép ghi tùy ý có thể làm thay đổi dữ liệu nghiệp vụ ngoài dự kiến.

Một số nguyên tắc thực tế:

- Dùng context chỉ đọc nếu biểu thức chỉ cần truy vấn dữ liệu.
- Chỉ bật khả năng ghi khi ứng dụng thực sự cần cập nhật thuộc tính.
- Giới hạn root object và những thuộc tính mà biểu thức có thể truy cập.
- Cân nhắc các PropertyAccessor, MethodResolver và BeanResolver tùy chỉnh.
- Tránh cho biểu thức không đáng tin cậy gọi các phương thức có tác dụng phụ hoặc truy cập bean nhạy cảm.
- Kiểm tra giá trị đầu vào và kiểu đích trước khi ghi dữ liệu.

SimpleEvaluationContext cung cấp các chế độ data binding có giới hạn, bao gồm chế độ chỉ đọc và đọc-ghi. StandardEvaluationContext có nhiều khả năng cấu hình hơn và cần được thiết lập phù hợp với phạm vi sử dụng.

## 12. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Phép gán chỉ tạo ra một giá trị mới mà không đổi object.**  
Phép gán vào thuộc tính có thể cập nhật chính object đang được tham chiếu trong context.

**Nhầm lẫn 2: Root object luôn là object được thay thế.**  
Khi gán customer.name, SpEL ghi vào thuộc tính name của Customer mà root object tham chiếu. Root object không tự động bị thay thế.

**Nhầm lẫn 3: getValue luôn là thao tác chỉ đọc.**  
Biểu thức có toán tử gán hoặc lời gọi phương thức gây tác dụng phụ vẫn có thể thay đổi trạng thái trong lúc getValue chạy.

**Nhầm lẫn 4: Mọi thuộc tính đều có thể ghi.**  
Đích phải hỗ trợ ghi thông qua accessor và object phải đáp ứng các điều kiện cần thiết. Context chỉ đọc hoặc object không có cơ chế ghi phù hợp có thể từ chối thao tác.

**Nhầm lẫn 5: Chuyển đổi kiểu luôn thành công.**  
TypeConverter chỉ chuyển đổi được những trường hợp được hỗ trợ. Giá trị không tương thích có thể gây lỗi.

**Nhầm lẫn 6: null luôn biểu thị thất bại.**  
null có thể là giá trị trả về hợp lệ. Cần phân biệt nó với exception trong parsing hoặc evaluation.

## 13. Ghi nhớ

- Thành phần cơ bản như literal, thuộc tính, biến và lời gọi phương thức có thể cung cấp giá trị cho biểu thức lớn hơn.
- Biểu thức được đánh giá trong EvaluationContext với root object, biến và các cơ chế truy cập phù hợp.
- Giá trị trả về có thể là Number, String, Boolean, object, collection, map hoặc null.
- \`Expression.setValue(...)\` ghi giá trị vào một đích có thể ghi.
- Toán tử gán \`=\` cũng có thể tạo tác dụng phụ khi biểu thức chứa phép gán được đánh giá bằng \`getValue(...)\`.
- Thay đổi thuộc tính có thể được nhìn thấy qua mọi tham chiếu đến cùng object.
- Setter và các accessor tùy chỉnh có thể thực hiện thêm logic khi ghi.
- Chọn context phù hợp để kiểm soát khả năng đọc, ghi và gọi phương thức của biểu thức.

Khi dùng SpEL để cập nhật dữ liệu, hãy xác định rõ object đích, đường dẫn thuộc tính, cơ chế ghi và kiểu giá trị. Sau đó kiểm tra trạng thái object sau evaluation để hiểu đầy đủ tác dụng phụ của biểu thức.
