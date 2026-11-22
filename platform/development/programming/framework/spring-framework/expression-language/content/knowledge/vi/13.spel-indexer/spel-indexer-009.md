# Chọn indexer hay property theo mô hình dữ liệu

Trong Spring Expression Language (SpEL), có hai cách thường dùng để đi sâu vào dữ liệu: **property access** bằng dấu chấm và **indexer** bằng dấu ngoặc vuông. Cả hai đều có thể xuất hiện trong cùng một biểu thức, nhưng chúng mô tả hai cách tổ chức dữ liệu khác nhau.

- Dùng **property** khi đang đọc một thuộc tính có tên của object, chẳng hạn customer, address hoặc status.
- Dùng **indexer** khi đang lấy phần tử theo vị trí, key hoặc chỉ số, chẳng hạn phần tử đầu tiên của List, một key trong Map hoặc một ký tự trong String.

Quyết định đúng dựa trên mô hình dữ liệu và ý nghĩa của thao tác. Một tên thuộc tính ổn định của domain object nên được thể hiện như property; một tập dữ liệu được tra cứu theo key hoặc vị trí nên được truy cập bằng indexer.

## 1. Hai cách truy cập và ý nghĩa của chúng

### 1.1. Property access — truy cập thuộc tính có tên

Property access dùng dấu chấm:

~~~text
#order.customer.address.city
~~~

Biểu thức bắt đầu từ biến order, sau đó đọc property customer, address và city. Mỗi property là một phần có tên trong mô hình object.

Ví dụ JavaBean:

~~~java
public class Order {
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }
}

public class Customer {
    private String status;

    public String getStatus() {
        return status;
    }
}
~~~

Các expression sau đọc những property tương ứng:

~~~text
#order.customer
#order.customer.status
~~~

SpEL phân giải property thông qua các PropertyAccessor trong EvaluationContext. Với JavaBean thông thường, property thường được đọc qua getter. Property có thể đến từ accessor tùy chỉnh nếu ứng dụng đăng ký accessor đó.

Property access phù hợp khi tên trường có ý nghĩa trong domain model và được xác định bởi kiểu object. Khi class đổi tên property hoặc thay đổi kiểu dữ liệu trả về, expression dùng property đó cũng cần được cập nhật.

### 1.2. Indexer — truy cập phần tử theo key hoặc vị trí

Indexer dùng dấu ngoặc vuông:

~~~text
#items[0]
#settings['region']
~~~

Ý nghĩa của phần bên trong ngoặc phụ thuộc vào kiểu dữ liệu:

- Với List hoặc array, index là vị trí phần tử, thường bắt đầu từ 0.
- Với Map, expression trong ngoặc là key dùng để tìm value.
- Với String, index có thể lấy ký tự tại vị trí tương ứng.
- Với object có IndexAccessor phù hợp, indexer có thể truy cập dữ liệu theo quy ước của accessor đó.

Ví dụ:

~~~java
context.setVariable("items", List.of("A", "B", "C"));
context.setVariable("settings", Map.of("region", "ap-southeast-1"));
~~~

Các expression:

~~~text
#items[0]
#settings['region']
~~~

lần lượt trả về phần tử đầu tiên của list và value ứng với key region trong map.

## 2. Chọn theo cấu trúc dữ liệu

| Mô hình dữ liệu | Cách truy cập thường dùng | Ví dụ |
| --- | --- | --- |
| JavaBean hoặc domain object | Property | **#order.customer.name** |
| Java record | Property theo component | **#customer.address.city** |
| Map | Indexer theo key | **#attributes['priority']** |
| List | Indexer theo vị trí | **#orders[0]** |
| Array | Indexer theo vị trí | **#scores[2]** |
| String | Indexer theo vị trí ký tự | **#code[0]** |
| Object có IndexAccessor | Indexer theo hợp đồng accessor | **#document['title']** |

Bảng này là quy tắc định hướng. Nếu ứng dụng đăng ký PropertyAccessor hoặc IndexAccessor tùy chỉnh, khả năng truy cập có thể mở rộng. Hãy xem cấu hình EvaluationContext và accessor đang được dùng trước khi giả định một cú pháp luôn hoạt động với mọi kiểu object.

## 3. Khi nào nên dùng property?

Dùng property khi dữ liệu là một phần có tên và có ý nghĩa ổn định trong object.

Ví dụ:

~~~java
class Invoice {
    private Customer customer;
    private BigDecimal total;
    private String status;

    public Customer getCustomer() {
        return customer;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Expression:

~~~text
#invoice.customer.name
#invoice.total
#invoice.status
~~~

Cách viết này thể hiện trực tiếp domain model: invoice có customer, total và status. Người đọc không cần biết thứ tự field hay vị trí lưu trữ bên trong object.

Property phù hợp trong các trường hợp:

1. **Domain object có cấu trúc rõ ràng:** customer, account, shippingAddress, status.
2. **JavaBean hoặc record:** các thuộc tính được xác định bởi getter hoặc component.
3. **Biểu thức nghiệp vụ:** kiểm tra trạng thái, quyền sở hữu hoặc một giá trị thuộc object.
4. **Cấu hình có tên:** đọc một property từ bean hoặc object cấu hình.
5. **Đường dẫn lồng nhau ổn định:** ví dụ order.customer.address.city.

Không nên dùng indexer chỉ vì một property tình cờ được lưu ở vị trí cố định trong cấu trúc nội bộ. Nếu dữ liệu mang tên và có ý nghĩa trong domain, property access làm rõ ý định hơn.

## 4. Khi nào nên dùng indexer?

Dùng indexer khi dữ liệu được tổ chức như một tập hợp có thể tra cứu bằng key hoặc vị trí.

### 4.1. Map — tra cứu theo key

Map phù hợp khi các phần tử được xác định bằng key thay vì tên property cố định của một class:

~~~java
Map<String, Object> attributes = new HashMap<>();
attributes.put("priority", "HIGH");
attributes.put("source", "WEB");

context.setVariable("attributes", attributes);
~~~

Truy cập bằng indexer:

~~~text
#attributes['priority']
#attributes['source']
~~~

Key có thể là biểu thức động:

~~~text
#attributes[#attributeName]
~~~

Nếu attributeName có giá trị priority, expression tương đương với việc lấy key priority.

Dùng Map indexer khi:

- Key đến từ cấu hình hoặc dữ liệu runtime.
- Tập key không cố định tại thời điểm biên dịch.
- Dữ liệu là metadata hoặc thuộc tính mở rộng.
- Cần truy cập key có ký tự đặc biệt hoặc không phải tên identifier thông thường.

Không nên giả định rằng key trong Map có thể luôn được truy cập bằng dấu chấm. Cú pháp rõ ràng và có ý nghĩa chuẩn cho Map là indexer với key đặt trong ngoặc vuông.

### 4.2. List — truy cập theo vị trí

List phù hợp khi thứ tự phần tử có ý nghĩa:

~~~java
context.setVariable("steps", List.of("validate", "approve", "publish"));
~~~

Expression:

~~~text
#steps[0]
#steps[1]
#steps[2]
~~~

Index bắt đầu từ 0. Phần tử đầu tiên ở vị trí 0, phần tử thứ hai ở vị trí 1.

Dùng List indexer khi cần lấy phần tử theo vị trí đã xác định hoặc theo index được tính trong expression:

~~~text
#steps[#currentIndex]
~~~

Nếu cần tìm phần tử theo thuộc tính nghiệp vụ thay vì vị trí, hãy cân nhắc selection operator hoặc xử lý bằng Java service. Một index cố định sẽ dễ trở nên sai khi thứ tự dữ liệu thay đổi.

### 4.3. Array — truy cập phần tử theo index

Array cũng dùng indexer:

~~~java
int[] scores = {70, 85, 92};
context.setVariable("scores", scores);
~~~

Expression:

~~~text
#scores[0]
#scores[2]
~~~

Dùng array khi dữ liệu thực sự được cung cấp dưới dạng array hoặc API yêu cầu kiểu đó. Không cần chuyển array thành object property chỉ để truy cập một phần tử.

### 4.4. String — lấy ký tự theo vị trí

SpEL hỗ trợ indexer trên String để truy cập ký tự:

~~~java
context.setVariable("code", "AB12");
~~~

Expression:

~~~text
#code[0]
#code[1]
~~~

Indexer này phù hợp với thao tác dựa trên vị trí ký tự, chẳng hạn đọc ký tự đầu của mã. Nếu cần xử lý Unicode supplementary character hoặc quy tắc ký tự người dùng nhìn thấy, hãy cân nhắc khác biệt giữa Java char, code point và grapheme cluster; một chỉ số ký tự không nhất thiết tương ứng với một ký tự hiển thị.

## 5. Kết hợp property và indexer trong cùng một đường dẫn

Trong dữ liệu thực tế, object thường chứa collection hoặc Map. Khi đó, một property path có thể xen kẽ dấu chấm và dấu ngoặc vuông.

Ví dụ:

~~~text
#order.customer.address.city
#order.lines[0].product.name
#order.attributes['priority']
~~~

Cách đọc:

- order là variable.
- customer, address và city là các property lồng nhau.
- lines là property trả về một collection; [0] lấy phần tử đầu tiên.
- product và name tiếp tục là property của phần tử vừa lấy.
- attributes là property trả về Map; ['priority'] lấy value theo key.

Một cấu trúc dữ liệu khác:

~~~text
#response.data['orders'][0].customer.address.city
~~~

SpEL lần lượt đọc property data, lấy key orders trong Map, lấy phần tử đầu tiên của List, rồi truy cập customer, address và city.

Khi đọc expression dài, hãy xác định kiểu dữ liệu sau từng bước. Dấu chấm có nghĩa là truy cập property của object hiện tại; dấu ngoặc vuông có nghĩa là truy cập phần tử bằng indexer trên giá trị hiện tại.

## 6. Trường hợp Map key và object property dễ bị nhầm

Xét hai mô hình:

~~~java
class Customer {
    private String name;

    public String getName() {
        return name;
    }
}

Map<String, Object> attributes = new HashMap<>();
attributes.put("name", "Linh");
~~~

Với Customer, name là property có tên:

~~~text
#customer.name
~~~

Với Map, name là key:

~~~text
#attributes['name']
~~~

Cả hai expression có thể trả về chuỗi Linh, nhưng chúng dựa trên hai cơ chế khác nhau:

- Property access yêu cầu accessor phân giải property name trên object.
- Map indexer tìm value ứng với key trong Map.

Dùng indexer cho Map giúp thể hiện rõ dữ liệu đang được tra cứu bằng key. Điều này đặc biệt quan trọng khi key được tạo động:

~~~text
#attributes[#requestedField]
~~~

Nếu requestedField thay đổi theo request, expression vẫn truy cập được key tương ứng mà không cần định nghĩa một JavaBean property cho từng key.

Ngược lại, nếu object có một thuộc tính domain ổn định, không nên biến nó thành Map chỉ để truy cập bằng chuỗi key. Kiểu dữ liệu có tên rõ ràng giúp compiler, IDE và người đọc hiểu được cấu trúc.

## 7. Indexer trên object tùy chỉnh

Mặc định, indexer thường được dùng với các kiểu dữ liệu có cấu trúc được SpEL hỗ trợ như Map, List, array và String. Với kiểu dữ liệu riêng, ứng dụng có thể cung cấp một IndexAccessor để định nghĩa cách đọc hoặc ghi bằng cú pháp dấu ngoặc vuông.

Từ Spring Framework 6.2, SpEL có API IndexAccessor dành cho mục đích này. Ví dụ, ứng dụng có thể định nghĩa một kiểu Document hỗ trợ truy cập trường theo key:

~~~text
document['title']
document['metadata']
~~~

Cách truy cập cụ thể phụ thuộc vào IndexAccessor được đăng ký trong EvaluationContext. Không nên giả định rằng một object bất kỳ có thể dùng indexer chỉ vì nó có method get(int) hoặc get(String). Cần có accessor tương ứng hoặc kiểu đó phải thuộc nhóm được SpEL hỗ trợ trực tiếp.

Tương tự, PropertyAccessor cho phép mở rộng cách SpEL phân giải property có tên. Hai SPI này giải quyết hai mô hình truy cập khác nhau:

| SPI | Cú pháp biểu thức | Mục đích |
| --- | --- | --- |
| PropertyAccessor | **object.property** | Đọc/ghi property có tên |
| IndexAccessor | **object[index]** | Đọc/ghi phần tử theo key hoặc index |

Khi xây dựng accessor tùy chỉnh, cần xác định rõ kiểu target được hỗ trợ, kiểu index hợp lệ, hành vi khi key không tồn tại, quyền đọc/ghi và cách xử lý null. Accessor phải phản ánh hợp đồng dữ liệu của ứng dụng, không nên tạo ra cú pháp mơ hồ giữa property và key.

## 8. Null, key không tồn tại và index ngoài phạm vi

### 8.1. Object trung gian có thể null

Property path hoặc indexer có thể thất bại nếu object nhận là null:

~~~text
#order.customer.address.city
#order.lines[0]
#settings['region']
~~~

Nếu order null, không thể đọc customer. Nếu lines null, không thể lấy phần tử đầu tiên. Nếu settings null, không thể tra key region.

Với property access, dùng safe-navigation operator ở các điểm có thể null:

~~~text
#order?.customer?.address?.city
~~~

Với indexer, Spring Framework 6.2 bổ sung safe-navigation cho indexing bằng cú pháp **?.[]**:

~~~text
#order?.lines?.[0]
#settings?.['region']
~~~

Cú pháp null-safe indexing phụ thuộc phiên bản framework. Nếu dự án dùng phiên bản cũ hơn, hãy kiểm tra hỗ trợ thực tế và xử lý null bằng điều kiện hoặc helper Java trước khi index.

### 8.2. Key không tồn tại trong Map

Khi key không có trong Map, kết quả tra cứu thường là null:

~~~text
#settings['missingKey']
~~~

Có thể kết hợp Elvis để cung cấp giá trị mặc định:

~~~text
#settings['region'] ?: 'ap-southeast-1'
~~~

Điều này phù hợp khi key là tùy chọn. Nếu key bắt buộc, nên xác thực dữ liệu và báo lỗi rõ ràng thay vì âm thầm thay bằng giá trị mặc định.

### 8.3. Index nằm ngoài giới hạn

Với List hoặc array, index phải nằm trong phạm vi hợp lệ:

~~~text
#items[0]
#items[10]
~~~

Nếu collection không có phần tử ở vị trí được yêu cầu, việc đánh giá có thể ném exception. Indexer không tự động chuyển một index sai thành null.

Trước khi dùng index động, hãy bảo đảm index hợp lệ hoặc kiểm tra kích thước bằng logic Java. Ví dụ, nếu cần lấy phần tử đầu tiên khi danh sách không rỗng, có thể tạo một helper trả về null khi danh sách rỗng rồi kết hợp với Elvis.

### 8.4. Phân biệt null-safe và bounds-safe

Safe navigation bảo vệ trường hợp object nhận là null. Nó không có nghĩa là index luôn hợp lệ.

Ví dụ:

~~~text
#items?.[0]
~~~

Expression này xử lý items null theo cơ chế null-safe indexing của phiên bản hỗ trợ. Nhưng nếu items là một List rỗng, index 0 vẫn nằm ngoài phạm vi và có thể gây lỗi.

Null safety và kiểm tra giới hạn là hai điều kiện riêng biệt.

## 9. Dùng property hay indexer trong các điểm tích hợp của Spring?

SpEL xuất hiện trong nhiều annotation và module. EvaluationContext do từng integration point cung cấp quyết định root object, biến và bean reference có sẵn. Cách chọn property hay indexer vẫn dựa trên kiểu dữ liệu đang được truy cập.

### 9.1. Cache key

Nếu tham số là domain object có property ID:

~~~java
@Cacheable(cacheNames = "orders", key = "#order.customer.id")
public OrderSummary summarize(Order order) {
    // ...
}
~~~

Nếu tham số chứa Map metadata:

~~~java
@Cacheable(cacheNames = "reports", key = "#request.attributes['reportType']")
public Report generate(ReportRequest request) {
    // ...
}
~~~

Ví dụ đầu truy cập property lồng nhau. Ví dụ sau đọc một key động trong Map attributes. Không nên chọn indexer chỉ để né việc định nghĩa property trên domain object.

### 9.2. Method Security

Có thể kiểm tra property của object:

~~~java
@PreAuthorize("#document.owner.id == authentication.principal.id")
public Document read(Document document) {
    // ...
}
~~~

Nếu quyền được xác định bởi metadata trong Map:

~~~java
@PreAuthorize("#document.attributes['visibility'] == 'PUBLIC'")
public Document read(Document document) {
    // ...
}
~~~

Expression phải phù hợp với cấu trúc thật của Document. Nếu owner là object có kiểu rõ ràng, dùng property. Nếu visibility là một key trong Map metadata, dùng indexer.

Với dữ liệu không tin cậy, không nên cho phép người dùng tự do gửi expression có thể đọc mọi property hoặc gọi mọi method. Hãy giới hạn EvaluationContext và accessor theo đúng phạm vi mà tính năng cần.

## 10. Selection và projection khi cần lọc collection

Indexer lấy phần tử theo vị trí cụ thể. Nếu mục tiêu là lọc hoặc biến đổi toàn bộ collection theo property của từng phần tử, SpEL có selection và projection operators.

Ví dụ lấy tất cả đơn hàng có tổng tiền từ 1000 trở lên:

~~~text
#orders.?[total >= 1000]
~~~

Lấy danh sách tên khách hàng từ collection đơn hàng:

~~~text
#orders.![customer.name]
~~~

Hai thao tác này khác với indexer:

- **#orders[0]** lấy một phần tử theo vị trí.
- **#orders.?[condition]** lọc các phần tử thỏa điều kiện.
- **#orders.![expression]** tạo collection kết quả từ biểu thức trên từng phần tử.

Nếu cần phần tử đầu tiên thỏa điều kiện, có thể dùng selection dạng first:

~~~text
#orders.^[total >= 1000]
~~~

Nếu cần phần tử cuối cùng thỏa điều kiện:

~~~text
#orders.$[total >= 1000]
~~~

Hãy chọn cú pháp theo ý định: lấy theo vị trí thì dùng indexer; tìm theo điều kiện thì dùng selection; chuyển đổi từng phần tử thì dùng projection.

## 11. Tiêu chí quyết định nhanh

Khi viết một expression mới, có thể tự hỏi:

1. **Dữ liệu là một object có thuộc tính được đặt tên?** Dùng property access, ví dụ customer.address.city.
2. **Dữ liệu là một Map được tra theo key?** Dùng indexer, ví dụ attributes['priority'].
3. **Dữ liệu là List hoặc array và vị trí có ý nghĩa?** Dùng indexer, ví dụ items[0].
4. **Key hoặc index được xác định tại runtime?** Dùng indexer với một expression làm key/index, ví dụ attributes[#fieldName].
5. **Cần tìm phần tử theo điều kiện thay vì vị trí?** Dùng selection operator hoặc Java service.
6. **Object có thể null?** Dùng safe navigation tại từng bước có thể null; kiểm tra riêng index ngoài phạm vi.
7. **Object là kiểu tùy chỉnh?** Kiểm tra PropertyAccessor hoặc IndexAccessor đã được đăng ký chưa.

Một nguyên tắc thực tế: dùng property để mô tả cấu trúc có tên của object; dùng indexer để mô tả thao tác tra cứu trong cấu trúc có key hoặc vị trí. Đừng chọn cú pháp chỉ vì nó ngắn hơn nếu ý nghĩa dữ liệu không tương ứng.

## 12. Kiểm thử expression với các cấu trúc khác nhau

Có thể dùng một parser và EvaluationContext để kiểm tra hai cách truy cập:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customer", customer);
context.setVariable("attributes", Map.of("priority", "HIGH"));
context.setVariable("items", List.of("A", "B"));

String customerName = parser
        .parseExpression("#customer.name")
        .getValue(context, String.class);

String priority = parser
        .parseExpression("#attributes['priority']")
        .getValue(context, String.class);

String firstItem = parser
        .parseExpression("#items[0]")
        .getValue(context, String.class);
~~~

Các expression trên kiểm tra:

- property name được phân giải trên object customer;
- Map indexer lấy value theo key priority;
- List indexer lấy phần tử tại vị trí 0.

Trong test thực tế, nên bao gồm cả key không tồn tại, index ngoài giới hạn, object trung gian null và hành vi của accessor tùy chỉnh nếu ứng dụng có dùng. Với annotation như @Cacheable hoặc @PreAuthorize, cần test tại đúng integration point để bảo đảm context cung cấp dữ liệu như mong đợi.

## 13. Những lỗi thường gặp

1. **Dùng dấu chấm cho Map key mà không có accessor hỗ trợ:** hãy dùng cú pháp indexer với key trong ngoặc vuông.
2. **Dùng index cố định cho dữ liệu có thứ tự thay đổi:** nếu cần tìm theo ID hoặc điều kiện, hãy tìm theo key hoặc dùng selection.
3. **Nhầm indexer với property:** items[0] là truy cập phần tử; items.size() là lời gọi method trên object.
4. **Quên index bắt đầu từ 0:** phần tử đầu tiên của List/array nằm ở index 0.
5. **Không kiểm tra index ngoài phạm vi:** safe navigation không bảo đảm index hợp lệ.
6. **Giả định object tùy chỉnh luôn hỗ trợ indexer:** cần IndexAccessor hoặc hỗ trợ tích hợp tương ứng.
7. **Không xử lý null ở các bước trung gian:** dùng safe navigation đúng vị trí và xác định rõ fallback.
8. **Dùng cấu trúc dữ liệu động cho domain field cố định:** property có tên rõ ràng thường dễ bảo trì hơn Map key.
9. **Cho phép expression truy cập quá rộng:** giới hạn accessor và EvaluationContext nếu expression đến từ nguồn không tin cậy.

## 14. Ghi nhớ nhanh

- Dấu chấm **.** truy cập property có tên trên object.
- Dấu ngoặc vuông **[]** truy cập Map key, List/array index, String index hoặc dữ liệu do IndexAccessor cung cấp.
- JavaBean và record thường phù hợp với property access.
- Map phù hợp với indexer vì dữ liệu được tra theo key, kể cả key động.
- List và array dùng indexer theo vị trí, bắt đầu từ 0.
- Một expression có thể xen kẽ property và indexer, ví dụ order.lines[0].product.name.
- Dùng **?.** cho property null-safe; Spring Framework 6.2 hỗ trợ null-safe indexing bằng **?.[]**.
- Null-safe không đồng nghĩa bounds-safe; index ngoài phạm vi vẫn có thể lỗi.
- Dùng selection để tìm phần tử theo điều kiện và projection để biến đổi collection.
- PropertyAccessor và IndexAccessor cho phép mở rộng cách truy cập, nhưng phải được cấu hình trong EvaluationContext.
- Chọn cú pháp theo mô hình dữ liệu và ý nghĩa nghiệp vụ, không chỉ theo độ ngắn của expression.

## 15. Tài liệu tham khảo chính thức

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Properties, Arrays, Lists, Maps and Indexers](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html)
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — EvaluationContext and Property Accessors](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — IndexAccessor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/IndexAccessor.html)
