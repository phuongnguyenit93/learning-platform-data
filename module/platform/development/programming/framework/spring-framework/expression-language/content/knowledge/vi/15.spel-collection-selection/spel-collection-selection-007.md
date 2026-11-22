# Selection trên list, map và collection khác nhau

Spring Expression Language (SpEL) cung cấp toán tử selection để lọc phần tử của một collection theo điều kiện. Thay vì lấy toàn bộ dữ liệu rồi lọc trong Java, biểu thức có thể chọn trực tiếp những phần tử thỏa mãn một predicate.

Selection có ba dạng chính:

- **.?[condition]**: lấy tất cả phần tử thỏa điều kiện.
- **.^[condition]**: lấy phần tử đầu tiên thỏa điều kiện.
- **.$[condition]**: lấy phần tử cuối cùng thỏa điều kiện.

Cách viết predicate phụ thuộc cấu trúc nguồn dữ liệu. Với list và các collection chứa object, điều kiện được đánh giá trên từng phần tử. Với map, điều kiện được đánh giá trên từng entry và có thể truy cập key cùng value. Hiểu sự khác biệt này giúp tránh viết sai predicate hoặc giả định sai kiểu kết quả.

## 1. Selection hoạt động như thế nào?

### 1.1. Lọc tất cả phần tử

Toán tử selection tổng quát có cú pháp:

~~~java
collection.?[selectionExpression]
~~~

SpEL duyệt các phần tử của nguồn và đánh giá selectionExpression cho từng phần tử. Những phần tử có kết quả Boolean true được giữ lại.

Ví dụ, giả sử root object có list orders:

~~~java
orders.?[total > 100]
~~~

Biểu thức trả về những đơn hàng có total lớn hơn 100.

Có thể đánh giá bằng parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext(report);

List<?> selected = parser
        .parseExpression("orders.?[total > 100]")
        .getValue(context, List.class);
~~~

Ví dụ giả định orders là một collection có thể duyệt và mỗi phần tử có property total phù hợp.

### 1.2. #this là phần tử đang được xét

Trong predicate, **#this** đại diện cho phần tử hiện tại mà selection đang kiểm tra.

Ví dụ:

~~~java
orders.?[#this.total > 100]
~~~

Cách viết này tương đương với việc truy cập property total trực tiếp trong predicate:

~~~java
orders.?[total > 100]
~~~

Dùng #this giúp biểu thức rõ hơn khi predicate có nhiều cấp truy cập hoặc khi cần phân biệt phần tử hiện tại với root object.

**#root** vẫn đại diện cho root object của EvaluationContext, còn **#this** thay đổi theo phần tử đang được xử lý trong selection. Hai biến này không có cùng ý nghĩa.

Ví dụ:

~~~java
orders.?[#this.customerId == #root.currentCustomerId]
~~~

Ở đây, #this là từng order; #root là object gốc chứa danh sách orders và currentCustomerId.

### 1.3. Kết quả rỗng

Nếu không có phần tử nào thỏa predicate, selection dạng **.?[...]** trả về collection rỗng (hoặc map rỗng nếu nguồn là map). Đây là kết quả hợp lệ, không phải lỗi parse.

Ứng dụng cần phân biệt:

- Không có phần tử phù hợp: kết quả rỗng.
- Nguồn collection là null: cần xử lý null theo cấu hình và cách viết biểu thức.
- Predicate truy cập property không tồn tại hoặc gọi method thất bại: có thể phát sinh lỗi evaluate.

Không nên coi một kết quả rỗng là bằng chứng dữ liệu đầu vào bị lỗi. Nó chỉ cho biết không có entry nào vượt qua điều kiện.

## 2. Selection trên List

### 2.1. Lọc object trong list

List thường chứa các object có property rõ ràng. Ví dụ:

~~~java
orders.?[status == 'PAID']
~~~

Biểu thức chọn tất cả order có status là PAID.

Có thể kết hợp nhiều điều kiện:

~~~java
orders.?[
    status == 'PAID' && total >= 100
]
~~~

Mỗi phần tử chỉ được chọn khi cả hai điều kiện đều đúng.

Nếu điều kiện truy cập một property có thể null, hãy bảo vệ truy cập bằng null check và tận dụng đánh giá ngắn mạch:

~~~java
orders.?[
    customer != null && customer.active
]
~~~

Khi customer null, vế sau không được đánh giá.

### 2.2. Lọc list số hoặc chuỗi

Predicate có thể làm việc trực tiếp với giá trị phần tử:

~~~java
numbers.?[#this > 10]
~~~

~~~java
names.?[#this.startsWith('A')]
~~~

Ví dụ đầu giữ lại các số lớn hơn 10. Ví dụ thứ hai giữ lại các chuỗi bắt đầu bằng chữ A.

Nếu phần tử có thể null, không gọi method trực tiếp mà chưa kiểm tra:

~~~java
names.?[#this != null && #this.startsWith('A')]
~~~

Điều kiện null đứng trước để tránh gọi startsWith trên giá trị null.

### 2.3. Lấy phần tử đầu tiên và cuối cùng

Ngoài lọc tất cả phần tử, SpEL có thể lấy phần tử đầu tiên hoặc cuối cùng thỏa predicate:

~~~java
orders.^[status == 'PAID']
~~~

~~~java
orders.$[status == 'PAID']
~~~

- **.^[...]** tìm phần tử đầu tiên thỏa điều kiện theo thứ tự duyệt.
- **.$[...]** tìm phần tử cuối cùng thỏa điều kiện theo thứ tự duyệt.

Hai toán tử này trả về một phần tử phù hợp, không phải collection chứa tất cả kết quả. Nếu không tìm thấy phần tử, kết quả là null.

Thứ tự duyệt có ý nghĩa. Với List, thứ tự phần tử thường được xác định bởi vị trí trong list. Với collection khác, thứ tự phụ thuộc implementation và hợp đồng của collection đó. Không nên dùng first/last để diễn đạt “mới nhất” hoặc “lớn nhất” nếu dữ liệu chưa được sắp xếp theo tiêu chí tương ứng.

Nếu cần phần tử có total lớn nhất, hãy sắp xếp hoặc tính toán theo tiêu chí đó ở Java, hoặc chuẩn bị dữ liệu có thứ tự trước khi dùng selection.

### 2.4. Selection không phải Projection

Selection và projection giải quyết hai nhu cầu khác nhau:

- **Selection** lọc phần tử và giữ nguyên phần tử được chọn.
- **Projection** biến đổi mỗi phần tử thành một giá trị hoặc cấu trúc khác.

Ví dụ selection:

~~~java
orders.?[total > 100]
~~~

Kết quả vẫn là các order.

Ví dụ projection:

~~~java
orders.![customerName]
~~~

Kết quả là các customerName tương ứng, không còn là các order ban đầu.

Có thể kết hợp hai toán tử:

~~~java
orders.?[status == 'PAID'].![id]
~~~

Biểu thức lọc order đã thanh toán rồi lấy id của từng order. Nên dùng selection trước để giới hạn phần tử cần xử lý, sau đó projection để tạo dữ liệu đầu ra.

## 3. Selection trên Map

### 3.1. Predicate được đánh giá trên Map.Entry

Khác với list, map chứa các cặp key-value. Khi selection trên map, SpEL đánh giá predicate trên từng entry (kiểu Java Map.Entry).

Hai property quan trọng có thể truy cập trong predicate là:

- **key**: khóa của entry hiện tại.
- **value**: giá trị tương ứng với khóa.

Ví dụ map lưu số lượng theo mã sản phẩm:

~~~java
inventory.?[value > 0]
~~~

Biểu thức giữ lại những entry có value lớn hơn 0.

Có thể truy cập rõ ràng hơn:

~~~java
inventory.?[#this.value > 0]
~~~

Trong predicate này, #this là entry đang được xét, #this.key là key và #this.value là value.

### 3.2. Lọc theo key

Nếu điều kiện phụ thuộc vào key:

~~~java
settings.?[key.startsWith('feature.')]
~~~

Biểu thức giữ lại các entry có key bắt đầu bằng feature.

Có thể kết hợp key và value:

~~~java
settings.?[
    key.startsWith('feature.')
    && value == true
]
~~~

Ví dụ này chọn những feature có giá trị Boolean true.

Nếu key hoặc value có thể null, hãy kiểm tra null trước khi gọi method hoặc so sánh theo quy tắc mong muốn:

~~~java
settings.?[
    key != null && key.startsWith('feature.')
]
~~~

### 3.3. Kết quả selection trên Map

Với map, selection dạng **.?[...]** trả về một map mới chứa các entry được chọn. Key và value của entry được giữ lại; predicate không biến map thành list value.

Ví dụ:

~~~java
{
    'A100': 10,
    'B200': 0,
    'C300': 25
}.?[value > 0]
~~~

Kết quả là map chứa các entry A100 và C300.

Điều này quan trọng khi lấy kết quả trong Java. Nếu nguồn là map, hãy nhận kết quả theo Map và kiểm tra kiểu key/value:

~~~java
Map<?, ?> available = parser
        .parseExpression("inventory.?[value > 0]")
        .getValue(context, Map.class);
~~~

Không nên ép kết quả map selection thành List chỉ vì predicate đang duyệt từng entry. Selection giữ cấu trúc map cho trường hợp nguồn map.

### 3.4. Lấy entry đầu tiên hoặc cuối cùng phù hợp

Map cũng có thể dùng first/last selection:

~~~java
inventory.^[value > 0]
~~~

~~~java
inventory.$[value > 0]
~~~

Predicate được đánh giá trên từng entry. Kết quả là entry đầu tiên hoặc cuối cùng phù hợp theo thứ tự duyệt của map. Nếu cần sử dụng kết quả như một entry, hãy xử lý theo kiểu Map.Entry phù hợp hoặc chuyển đổi nó ở tầng Java theo hợp đồng của ứng dụng.

Với HashMap, không nên giả định thứ tự duyệt ổn định hoặc có ý nghĩa nghiệp vụ. Nếu cần first/last có ý nghĩa xác định, hãy dùng map có thứ tự phù hợp như LinkedHashMap hoặc sắp xếp dữ liệu trước khi đánh giá.

## 4. Selection trên các Collection khác

### 4.1. Collection và Iterable

Selection không chỉ dành cho List. Nó có thể được dùng với các collection có thể duyệt (Iterable), chẳng hạn:

- List: có thứ tự và truy cập theo index.
- Set: bảo đảm tính duy nhất theo equals/hashCode; thứ tự phụ thuộc implementation.
- Queue hoặc Deque: có quy tắc duyệt theo implementation.
- Các kiểu Collection tùy chỉnh triển khai Iterable.

Ví dụ với Set:

~~~java
activeUsers.?[enabled]
~~~

Hoặc với các phần tử số:

~~~java
scores.?[#this >= 80]
~~~

Selection duyệt các phần tử và giữ lại những phần tử thỏa predicate. Đừng giả định kết quả luôn giữ đúng implementation cụ thể của nguồn, ví dụ LinkedHashSet hoặc TreeSet. Nếu ứng dụng cần kiểu collection đầu ra cụ thể, hãy chuyển đổi rõ ràng trong Java.

### 4.2. Khác biệt về thứ tự

Thứ tự của kết quả phụ thuộc thứ tự duyệt nguồn:

| Nguồn | Đặc điểm thứ tự | Lưu ý khi selection |
|---|---|---|
| ArrayList | Theo vị trí phần tử | Kết quả theo thứ tự list |
| LinkedList | Theo thứ tự liên kết | Kết quả theo thứ tự duyệt |
| LinkedHashSet | Theo thứ tự thêm vào | Có thể dựa vào thứ tự duyệt đã xác định |
| TreeSet | Theo comparator | Kết quả theo thứ tự comparator |
| HashSet | Không bảo đảm thứ tự ổn định | Không dùng first/last cho ý nghĩa nghiệp vụ |
| LinkedHashMap | Theo thứ tự duyệt được duy trì | Map selection giữ các entry phù hợp |
| HashMap | Không bảo đảm thứ tự duyệt ổn định | Không suy luận first/last theo thời gian hoặc độ ưu tiên |

Selection không tự sắp xếp dữ liệu. Nó chỉ lọc theo thứ tự mà nguồn cung cấp.

### 4.3. Array và dữ liệu không phải Collection

Selection được thiết kế cho collection có thể duyệt và map. Nếu dữ liệu nguồn là Java array, không nên mặc định rằng mọi cấu hình/phiên bản SpEL xử lý array giống List hoặc Iterable.

Khi cần selection trên array, cách rõ ràng là chuyển array thành collection phù hợp trong Java rồi đặt collection đó vào context:

~~~java
List<String> names = Arrays.asList(nameArray);
context.setVariable("names", names);
~~~

Sau đó dùng:

~~~java
#names.?[#this.startsWith('A')]
~~~

Cách này làm rõ kiểu dữ liệu đầu vào và giúp kiểm soát việc copy hoặc thay đổi collection.

## 5. Kết hợp selection với root object và biến context

Selection thường được dùng trên property của root object:

~~~java
orders.?[total > #minimum]
~~~

Trong đó #minimum là biến context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(report);

context.setVariable("minimum", 100);
~~~

Predicate dùng #this cho phần tử hiện tại và dùng #root hoặc biến context để tham chiếu dữ liệu bên ngoài:

~~~java
orders.?[
    #this.customerId == #root.currentCustomerId
    && #this.total >= #minimum
]
~~~

Cách này giúp biểu thức tách rõ:

- Dữ liệu của phần tử hiện tại.
- Dữ liệu toàn cục trong root object.
- Tham số được cung cấp riêng qua context.

Chỉ đưa vào context những biến cần thiết và đã được xác thực. Không nên đặt một object lớn hoặc service có nhiều quyền chỉ để cung cấp một giá trị đơn giản cho predicate.

## 6. Null và lỗi khi selection

### 6.1. Nguồn collection có thể null

Nếu property collection có thể null, biểu thức selection trực tiếp có thể không hoạt động như khi nguồn là một collection hợp lệ. Có thể kiểm tra null trước:

~~~java
orders != null ? orders.?[total > 100] : {}
~~~

Ví dụ trên phù hợp khi orders là list và nhánh mặc định là list rỗng. Nếu nguồn là map, dùng map rỗng:

~~~java
settings != null ? settings.?[value == true] : {:}
~~~

Không dùng **{}** làm mặc định cho map vì **{}** là inline list rỗng.

Nếu phiên bản Spring đang dùng hỗ trợ safe selection, có thể cân nhắc cú pháp safe navigation kết hợp selection. Hãy xác nhận phiên bản và kiểm thử hành vi với nguồn null trước khi đưa vào biểu thức dùng chung.

### 6.2. Phần tử null trong collection

Một collection có thể chứa phần tử null. Predicate cần kiểm tra trước khi truy cập property:

~~~java
users.?[
    #this != null && #this.enabled
]
~~~

Nếu không có null guard, việc đọc enabled trên phần tử null có thể phát sinh lỗi evaluate.

### 6.3. Property hoặc method không tồn tại

Selection không bắt lỗi property hoặc method. Ví dụ:

~~~java
users.?[unknownProperty == true]
~~~

Nếu phần tử không có property unknownProperty và accessor không thể giải quyết nó, việc đánh giá có thể thất bại. Selection không tự động bỏ qua phần tử lỗi.

Hãy kiểm tra model và predicate. Nếu mỗi phần tử có kiểu khác nhau, cần chuẩn hóa dữ liệu hoặc viết điều kiện theo kiểu thực tế.

### 6.4. Phân biệt kết quả rỗng và lỗi

| Kết quả/tình huống | Ý nghĩa |
|---|---|
| Collection selection trả về rỗng | Không có phần tử thỏa predicate |
| Map selection trả về map rỗng | Không có entry thỏa predicate |
| First/last selection trả về null | Không tìm thấy phần tử phù hợp |
| ParseException | Cú pháp selection không hợp lệ |
| EvaluationException | Predicate hoặc truy cập dữ liệu thất bại |

Ứng dụng nên xử lý từng trường hợp theo ý nghĩa riêng. Không nên bắt mọi EvaluationException rồi trả về collection rỗng, vì điều đó có thể che giấu lỗi sai tên property hoặc lỗi logic.

## 7. Chi phí và cách viết predicate hiệu quả

Selection phải đánh giá predicate trên các phần tử của nguồn. Với một collection có n phần tử, chi phí duyệt cơ bản thường tăng theo số phần tử, cộng thêm chi phí của predicate.

Ví dụ:

~~~java
orders.?[
    customer != null
    && customer.active
    && total >= #minimum
]
~~~

Predicate đơn giản và truy cập property cần thiết thường dễ kiểm soát hơn một biểu thức gọi nhiều method hoặc thực hiện nhiều phép tính lặp lại.

Một số nguyên tắc:

- Giới hạn số phần tử collection trước khi đưa vào context.
- Đặt null check trước phần truy cập phụ thuộc để tận dụng short-circuit.
- Tránh gọi method tốn tài nguyên hoặc có tác dụng phụ trong predicate.
- Không lặp lại cùng một phép tính phức tạp cho mọi phần tử nếu có thể chuẩn bị trước.
- Nếu cần sort, group hoặc join dữ liệu phức tạp, thực hiện trong Java hoặc tầng truy vấn chuyên dụng.
- Không dùng first/last như một cách thay thế cho việc sắp xếp theo tiêu chí nghiệp vụ.

Với dữ liệu lớn, hãy cân nhắc lọc ngay tại database hoặc repository thay vì tải toàn bộ collection về rồi selection trong bộ nhớ.

## 8. Ví dụ hoàn chỉnh: List và Map

Giả sử ứng dụng có dữ liệu:

~~~java
public record Product(
        String code,
        boolean active,
        int stock
) {
}

public class InventoryReport {

    private final List<Product> products;
    private final Map<String, Integer> stockByWarehouse;

    public InventoryReport(
            List<Product> products,
            Map<String, Integer> stockByWarehouse) {
        this.products = products;
        this.stockByWarehouse = stockByWarehouse;
    }

    public List<Product> getProducts() {
        return products;
    }

    public Map<String, Integer> getStockByWarehouse() {
        return stockByWarehouse;
    }
}
~~~

Tạo context:

~~~java
InventoryReport report = new InventoryReport(
        List.of(
                new Product("P-01", true, 10),
                new Product("P-02", false, 0),
                new Product("P-03", true, 25)
        ),
        Map.of(
                "HCM", 10,
                "HN", 0,
                "DN", 25
        )
);

StandardEvaluationContext context =
        new StandardEvaluationContext(report);

ExpressionParser parser = new SpelExpressionParser();
~~~

Lọc sản phẩm đang hoạt động:

~~~java
List<?> activeProducts = parser
        .parseExpression("products.?[active]")
        .getValue(context, List.class);
~~~

Lấy sản phẩm đầu tiên có tồn kho lớn hơn 10:

~~~java
Object firstAvailable = parser
        .parseExpression("products.^[stock > 10]")
        .getValue(context);
~~~

Lọc các kho còn hàng:

~~~java
Map<?, ?> availableWarehouses = parser
        .parseExpression("stockByWarehouse.?[value > 0]")
        .getValue(context, Map.class);
~~~

Kết quả map giữ các key HCM và DN cùng value tương ứng. Nếu cần lấy một kho cụ thể, hãy truy cập key sau khi selection hoặc dùng truy cập map trực tiếp.

## 9. Kiểm thử selection

Nên kiểm thử cả kết quả đầy đủ, first/last, nguồn rỗng, không có kết quả và dữ liệu null.

Ví dụ với List:

~~~java
List<Integer> numbers = List.of(5, 10, 15, 20);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("numbers", numbers);

List<?> selected = parser
        .parseExpression("#numbers.?[#this >= 10]")
        .getValue(context, List.class);

assertEquals(List.of(10, 15, 20), selected);

Integer first = parser
        .parseExpression("#numbers.^[#this >= 10]")
        .getValue(context, Integer.class);

assertEquals(10, first);

Integer last = parser
        .parseExpression("#numbers.$[#this >= 10]")
        .getValue(context, Integer.class);

assertEquals(20, last);
~~~

Ví dụ với Map:

~~~java
Map<String, Integer> stock = Map.of(
        "HCM", 10,
        "HN", 0,
        "DN", 25
);

context.setVariable("stock", stock);

Map<?, ?> available = parser
        .parseExpression("#stock.?[value > 0]")
        .getValue(context, Map.class);

assertEquals(2, available.size());
assertEquals(10, available.get("HCM"));
assertEquals(25, available.get("DN"));
~~~

Ngoài các trường hợp trên, nên kiểm thử:

- Collection rỗng.
- Map rỗng.
- Không có phần tử nào thỏa predicate.
- Phần tử null trong collection.
- Map có key hoặc value null.
- Collection có thứ tự và collection không bảo đảm thứ tự.
- Predicate truy cập property không tồn tại.
- Collection lớn sát giới hạn đầu vào.

Kiểm thử theo kiểu nguồn rất quan trọng: list selection và map selection không có cùng kiểu kết quả. Không chỉ kiểm tra số lượng phần tử; hãy xác nhận cả kiểu và nội dung kết quả.

## 10. Tổng kết

Selection trong SpEL lọc dữ liệu theo predicate và có ba dạng chính:

- **.?[...]** lấy tất cả phần tử hoặc entry thỏa điều kiện.
- **.^[...]** lấy phần tử hoặc entry đầu tiên phù hợp.
- **.$[...]** lấy phần tử hoặc entry cuối cùng phù hợp.

Với List và các collection Iterable, predicate được đánh giá trên từng phần tử; kết quả là tập hợp các phần tử được chọn. Với Map, predicate được đánh giá trên Map.Entry thông qua key và value, và selection tổng quát trả về một map chứa các entry phù hợp.

Hãy nhớ dùng #this cho phần tử hiện tại, #root cho root object, kiểm tra null trước khi truy cập property và không giả định collection có thứ tự nếu implementation không bảo đảm. Selection phù hợp cho bộ lọc gọn trong bộ nhớ; với dữ liệu lớn hoặc logic phức tạp, hãy lọc ở tầng Java hoặc database để kiểm soát chi phí tốt hơn.