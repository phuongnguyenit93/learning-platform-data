# Giới hạn biểu diễn cấu trúc lồng nhau trong CSV

## 1. CSV là định dạng bảng, không phải định dạng cây

CSV (Comma-Separated Values) biểu diễn dữ liệu dưới dạng các bản ghi gồm những trường được phân tách bằng dấu phân cách. Một file thường có một dòng header và nhiều dòng dữ liệu:

~~~csv
id,name,city
U-10,Lan,Da Nang
U-11,Minh,Hue
~~~

Mỗi cột đại diện cho một thuộc tính có cùng ý nghĩa ở tất cả các dòng. Mỗi dòng là một bản ghi. Cấu trúc cơ bản của CSV là **bảng phẳng gồm hàng và cột**.

YAML có mô hình dữ liệu phong phú hơn. Nó biểu diễn trực tiếp:

- Scalar: string, number, boolean, null.
- Mapping: tập các cặp key/value.
- Sequence: danh sách các giá trị.
- Mapping hoặc sequence có thể chứa tiếp mapping và sequence khác.

Ví dụ YAML có thể biểu diễn một đơn hàng với địa chỉ lồng nhau và danh sách mặt hàng:

~~~yaml
orderId: O-200
customer:
  id: C-100
  name: Lan
shippingAddress:
  city: Da Nang
  postalCode: "550000"
items:
  - sku: KB-01
    quantity: 2
  - sku: MS-02
    quantity: 1
~~~

CSV không có khái niệm object con, array, quan hệ cha/con hoặc kiểu dữ liệu riêng cho từng cell. Nó chỉ có các trường văn bản trong mỗi hàng. Vì vậy, khi chuyển cấu trúc YAML lồng nhau sang CSV, ứng dụng phải chọn một cách mã hóa hoặc chuẩn hóa cấu trúc đó.

Không có một phép chuyển đổi YAML sang CSV duy nhất đúng cho mọi dữ liệu. Lựa chọn phụ thuộc vào việc người dùng cần bảng để phân tích, file để trao đổi, hay khả năng khôi phục lại cấu trúc ban đầu.

## 2. Một object lồng nhau không có cột tự nhiên trong CSV

Giả sử mô hình Java:

~~~java
public class Order {
    private String orderId;
    private Customer customer;
    private Address shippingAddress;
    private List<OrderLine> items;
}

public class Customer {
    private String id;
    private String name;
}

public class Address {
    private String city;
    private String postalCode;
}

public class OrderLine {
    private String sku;
    private int quantity;
}
~~~

Các property orderId, customer, shippingAddress và items không cùng một mức cấu trúc. Trong YAML, chúng có thể được biểu diễn tự nhiên thành mapping và sequence. Trong CSV, header phải là một danh sách cột phẳng.

Ví dụ header:

~~~csv
orderId,customer.id,customer.name,shippingAddress.city,shippingAddress.postalCode
~~~

Header này là một quy ước do ứng dụng tự định nghĩa. Dấu chấm không phải cú pháp lồng nhau chuẩn của CSV. Một phần mềm bảng tính có thể coi customer.id là tên cột nguyên vẹn; một parser khác không tự tạo object customer.

Vì thế, nếu dùng tên cột dạng đường dẫn, cả writer và reader phải thống nhất quy tắc:

- Dấu phân cấp là dấu chấm, dấu gạch dưới hay một quy ước khác?
- Làm sao phân biệt key thực sự có dấu chấm với dấu phân cấp?
- Có hỗ trợ nhiều cấp lồng nhau không?
- Nếu property bị thiếu thì tạo object cha hay để null?
- Nếu object cha null thì các cột con biểu diễn thế nào?

CSV không cung cấp câu trả lời cho các câu hỏi này. Chúng thuộc về schema của ứng dụng.

## 3. Mảng lồng nhau khó biểu diễn hơn object

Một array có số phần tử thay đổi theo từng bản ghi:

~~~yaml
orderId: O-200
items:
  - sku: KB-01
    quantity: 2
  - sku: MS-02
    quantity: 1
~~~

CSV yêu cầu mỗi hàng có một tập cột xác định. Không có cột tự nhiên nào đại diện cho một danh sách có độ dài tùy ý.

Một số cách mã hóa thường gặp:

1. Dàn phẳng thành nhiều cột cố định như item1Sku, item1Quantity, item2Sku, item2Quantity.
2. Tạo nhiều hàng, mỗi hàng tương ứng một item và lặp lại thông tin order.
3. Tách thành file orders.csv và order_items.csv có khóa liên kết.
4. Lưu toàn bộ danh sách dưới dạng JSON trong một cell.
5. Dùng một định dạng có cấu trúc như YAML hoặc JSON thay cho CSV.

Mỗi lựa chọn đánh đổi giữa khả năng đọc bằng spreadsheet, truy vấn, kích thước file, khả năng mở rộng và khả năng khôi phục dữ liệu.

## 4. Cách 1: Flatten object thành các cột

Flattening chuyển các field con thành các cột phẳng. Ví dụ:

~~~csv
orderId,customerId,customerName,shippingCity,shippingPostalCode
O-200,C-100,Lan,Da Nang,550000
O-201,C-101,Minh,Hue,530000
~~~

DTO phẳng:

~~~java
public class FlatOrder {
    private String orderId;
    private String customerId;
    private String customerName;
    private String shippingCity;
    private String shippingPostalCode;

    // getters/setters
}
~~~

Khi đọc CSV, ứng dụng có thể chuyển DTO phẳng thành domain object:

~~~java
Order toOrder(FlatOrder row) {
    Customer customer = new Customer();
    customer.setId(row.getCustomerId());
    customer.setName(row.getCustomerName());

    Address address = new Address();
    address.setCity(row.getShippingCity());
    address.setPostalCode(row.getShippingPostalCode());

    Order order = new Order();
    order.setOrderId(row.getOrderId());
    order.setCustomer(customer);
    order.setShippingAddress(address);
    return order;
}
~~~

Flattening dễ làm việc với spreadsheet và công cụ phân tích dạng bảng. Nó cũng phù hợp khi cấu trúc lồng nhau có độ sâu nhỏ và các field tương đối ổn định.

Giới hạn:

- Schema phải biết trước các field con.
- Thêm một field lồng nhau có thể làm thay đổi header.
- Object null và object rỗng có thể khó phân biệt.
- Array có độ dài thay đổi không thể flatten tự nhiên thành số cột cố định.
- Tên cột có thể dài và dễ trùng khi nhiều object con có field cùng tên.

Nếu hai object con đều có field name, nên đặt tên cột có ngữ cảnh như customerName và supplierName, thay vì tạo hai cột name không rõ nguồn.

## 5. Cách 2: Flatten theo đường dẫn

Thay vì đặt tên cột theo quy ước camelCase, có thể dùng đường dẫn:

~~~csv
orderId,customer.id,customer.name,shippingAddress.city,shippingAddress.postalCode
O-200,C-100,Lan,Da Nang,550000
~~~

Đường dẫn thể hiện nguồn gốc của từng field và giúp giữ tên gần với mô hình Java/YAML. Tuy nhiên, CSV vẫn chỉ coi customer.id là tên cột. Để tái tạo object, cần một schema mapping:

~~~java
Map<String, String> columns = Map.of(
        "customer.id", "customerId",
        "customer.name", "customerName",
        "shippingAddress.city", "shippingCity",
        "shippingAddress.postalCode", "shippingPostalCode"
);
~~~

Đây chỉ là ví dụ về bảng ánh xạ; ứng dụng phải định nghĩa cách đọc/ghi và xử lý path. Nếu tên property có ký tự phân cách, cần escape hoặc dùng metadata riêng để tránh mơ hồ.

Flatten theo path hữu ích với object có độ sâu biết trước. Nó không giải quyết được array động; một cột items.0.sku, items.1.sku chỉ phù hợp khi giới hạn số phần tử và chấp nhận schema thay đổi theo độ dài lớn nhất.

## 6. Cách 3: Mỗi phần tử array thành một hàng

Với quan hệ một-nhiều, có thể lặp lại thông tin cha trên mỗi hàng:

~~~csv
orderId,customerName,shippingCity,itemSku,itemQuantity
O-200,Lan,Da Nang,KB-01,2
O-200,Lan,Da Nang,MS-02,1
O-201,Minh,Hue,USB-03,5
~~~

Mỗi hàng đại diện cho một order item. orderId nhận diện đơn hàng; các cột itemSku và itemQuantity mô tả phần tử con.

Ưu điểm:

- Dễ lọc và tổng hợp theo item.
- Không cần cell chứa JSON.
- Số hàng có thể tăng theo số item.
- Phù hợp với spreadsheet và công cụ phân tích dạng bảng.

Nhược điểm:

- Dữ liệu cha bị lặp.
- Một order không có item cần quy ước riêng để vẫn thể hiện được.
- Khi import, phải nhóm các hàng theo orderId để tái tạo array.
- Nếu thông tin cha khác nhau giữa các hàng cùng orderId, phải phát hiện xung đột thay vì chọn tùy tiện.
- Thứ tự item cần một cột sequence/index nếu thứ tự là một phần của hợp đồng.

Ví dụ thêm cột itemIndex:

~~~csv
orderId,itemIndex,itemSku,itemQuantity
O-200,0,KB-01,2
O-200,1,MS-02,1
~~~

Không nên giả định thứ tự hàng trong mọi hệ thống downstream luôn được bảo toàn. Nếu thứ tự quan trọng, hãy biểu diễn nó thành dữ liệu.

## 7. Cách 4: Chuẩn hóa thành nhiều file CSV có khóa liên kết

Khi có nhiều quan hệ một-nhiều hoặc nhiều object con, nên tách dữ liệu thành các bảng riêng. Ví dụ:

orders.csv:

~~~csv
orderId,customerId,shippingCity,shippingPostalCode
O-200,C-100,Da Nang,550000
O-201,C-101,Hue,530000
~~~

customers.csv:

~~~csv
customerId,customerName
C-100,Lan
C-101,Minh
~~~

order_items.csv:

~~~csv
orderId,itemIndex,sku,quantity
O-200,0,KB-01,2
O-200,1,MS-02,1
O-201,0,USB-03,5
~~~

Các file liên kết bằng khóa:

~~~text
customers.customerId
        ^
        |
orders.customerId

orders.orderId
        ^
        |
order_items.orderId
~~~

Cách này gần với mô hình quan hệ trong cơ sở dữ liệu. Nó giảm lặp dữ liệu và hỗ trợ nhiều item mà không cần số cột cố định.

Khi đọc lại:

1. Đọc customers và tạo map theo customerId.
2. Đọc orders và gắn customer theo customerId.
3. Đọc order_items, nhóm theo orderId.
4. Sắp xếp item theo itemIndex nếu thứ tự có ý nghĩa.
5. Kiểm tra khóa ngoại bị thiếu hoặc trùng.

Nhiều file CSV không tự tạo thành một transaction. Nếu một file được cập nhật nhưng file khác chưa được ghi xong, bộ dữ liệu có thể không nhất quán. Khi xuất nhiều file, nên dùng thư mục staging hoặc manifest có trạng thái để chỉ công bố cả bộ sau khi ghi thành công.

## 8. Cách 5: Nhúng JSON vào một cell CSV

Nếu cần giữ một object hoặc array có cấu trúc tùy ý, có thể lưu JSON trong một cột:

~~~csv
orderId,customerName,itemsJson
O-200,Lan,"[{""sku"":""KB-01"",""quantity"":2},{""sku"":""MS-02"",""quantity"":1}]"
~~~

CSV bên ngoài vẫn là bảng phẳng. Giá trị của itemsJson là một chuỗi; chuỗi đó chứa JSON riêng và phải được escape theo quy tắc CSV.

Ưu điểm:

- Giữ được object/array lồng nhau.
- Không cần tạo số cột cố định cho array.
- Có thể dùng Jackson để parse JSON cell thành JsonNode hoặc POJO.
- Dễ bổ sung field con mà không cần đổi header CSV.

Nhược điểm:

- Người dùng spreadsheet khó lọc hoặc chỉnh sửa từng field bên trong JSON.
- Phải parse hai tầng: CSV trước, JSON trong cell sau.
- JSON cell có thể lớn và làm file khó đọc.
- Cần quy định encoding, version và validation cho JSON bên trong.
- Không phải công cụ CSV nào cũng xử lý tốt cell rất dài hoặc chứa nhiều dòng.

Ví dụ:

~~~java
JsonNode items = mapper.readTree(itemsJson);
List<OrderLine> lines = mapper.readerForListOf(OrderLine.class)
        .readValue(items);
~~~

Trong thực tế, có thể dùng readValue trực tiếp vào kiểu list:

~~~java
List<OrderLine> lines = mapper.readValue(
        itemsJson,
        new TypeReference<List<OrderLine>>() {}
);
~~~

Khi ghi CSV, hãy để CsvMapper thực hiện quoting cho cell JSON. Không tự thay dấu ngoặc kép trong JSON bằng tay rồi lại đưa qua CSV writer; điều đó dễ tạo double-escaping hoặc dữ liệu không thể parse lại.

## 9. Cách 6: Dùng một chuỗi phân cách trong cell

Một số file lưu danh sách đơn giản bằng cách nối các giá trị:

~~~csv
orderId,tags
O-200,"priority;gift;fragile"
~~~

Đây là quy ước riêng của ứng dụng, không phải array native trong CSV. Nếu một tag có dấu chấm phẩy, hoặc tag rỗng, việc tách chuỗi sẽ trở nên mơ hồ trừ khi định nghĩa thêm escaping.

Ví dụ:

~~~text
["priority", "gift;wrap", "fragile"]
~~~

Không thể dùng split(";") đơn giản để khôi phục chính xác ba phần tử. Cần một grammar riêng cho list trong cell, hoặc chọn JSON-in-cell hay bảng phụ.

Quy tắc phân cách nội bộ còn tạo hai tầng escaping:

1. Escape delimiter của list bên trong cell.
2. Escape dấu quote, delimiter và newline theo CSV bên ngoài.

Nếu dữ liệu có thể chứa ký tự tùy ý, JSON thường là lựa chọn rõ ràng hơn chuỗi phân cách tự chế.

## 10. CSV không có kiểu dữ liệu null thống nhất

CSV thường được đọc như văn bản. Một cell trống có thể mang nhiều ý nghĩa:

- Giá trị chuỗi rỗng.
- Giá trị null.
- Giá trị bị thiếu trong nguồn.
- Giá trị không được cung cấp.
- Giá trị chưa biết.

Ví dụ:

~~~csv
id,phone
U-10,
U-11,""
U-12,NULL
~~~

Không có quy tắc chung buộc mọi parser phải hiểu ba dạng trên là ba trạng thái khác nhau. Một số thư viện xem cell trống và chuỗi rỗng là cùng một giá trị; chuỗi NULL có thể là dữ liệu văn bản bình thường.

Nếu cần phân biệt:

- Chọn sentinel rõ ràng, chẳng hạn \\N hoặc một token đã được dành riêng.
- Quy định cách escape nếu dữ liệu thật có thể bằng sentinel đó.
- Có thể thêm cột presence như phoneProvided.
- Hoặc dùng định dạng hỗ trợ null/missing tường minh như JSON/YAML.

Jackson CSV có thể cấu hình null value trong schema theo phiên bản module. Hãy cấu hình cùng một quy tắc ở writer và reader, đồng thời test cell trống, chuỗi rỗng, sentinel và field thiếu. Đừng mặc định rằng CSV tự bảo toàn sự khác biệt giữa null và empty string.

## 11. CSV quoting không phải nested serialization

CSV có quy tắc quoting cho field chứa delimiter, dấu quote hoặc newline. Ví dụ:

~~~csv
id,description
P-1,"Keyboard, wireless"
P-2,"He said ""hello"""
P-3,"Line one
Line two"
~~~

Quoting giúp một giá trị văn bản chứa dấu phẩy hoặc dấu xuống dòng vẫn nằm trong một cell. Nó không tạo ra object hoặc array lồng nhau.

Ví dụ cell:

~~~csv
O-200,"{""city"":""Da Nang"",""postalCode"":""550000""}"
~~~

CSV parser chỉ trả về một chuỗi cell có nội dung JSON. Ứng dụng phải gọi JSON parser riêng để hiểu object bên trong.

Không nên tự nối CSV bằng dấu phẩy:

~~~java
String row = orderId + "," + customerName + "," + itemsJson;
~~~

Nếu customerName hoặc itemsJson có dấu phẩy, quote hoặc newline, kết quả có thể sai định dạng. Dùng CsvMapper hoặc thư viện CSV để xử lý escaping.

## 12. CSV trong Jackson: CsvMapper và CsvSchema

Jackson cung cấp module jackson-dataformat-csv. CsvMapper kế thừa nền tảng Databind nhưng dùng schema dạng bảng để đọc và ghi các cột.

Dependency Maven:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.dataformat</groupId>
    <artifactId>jackson-dataformat-csv</artifactId>
</dependency>
~~~

Nên dùng Jackson BOM để căn chỉnh phiên bản CSV module với Core và Databind.

Tạo mapper và schema:

~~~java
import com.fasterxml.jackson.dataformat.csv.CsvMapper;
import com.fasterxml.jackson.dataformat.csv.CsvSchema;

CsvMapper csvMapper = new CsvMapper();

CsvSchema schema = CsvSchema.builder()
        .addColumn("orderId")
        .addColumn("customerName")
        .addColumn("shippingCity")
        .addColumn("shippingPostalCode")
        .build()
        .withHeader();
~~~

CsvSchema định nghĩa các cột, thứ tự và một số quy tắc CSV như header, delimiter và null representation. Schema không tự suy ra một cây object tùy ý từ các dấu chấm trong tên cột.

## 13. Đọc và ghi DTO phẳng bằng CsvMapper

DTO:

~~~java
public class FlatOrder {
    private String orderId;
    private String customerName;
    private String shippingCity;
    private String shippingPostalCode;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public String getShippingCity() {
        return shippingCity;
    }

    public void setShippingCity(String shippingCity) {
        this.shippingCity = shippingCity;
    }

    public String getShippingPostalCode() {
        return shippingPostalCode;
    }

    public void setShippingPostalCode(String shippingPostalCode) {
        this.shippingPostalCode = shippingPostalCode;
    }
}
~~~

Đọc nhiều hàng:

~~~java
try (MappingIterator<FlatOrder> rows = csvMapper
        .readerFor(FlatOrder.class)
        .with(schema)
        .readValues(inputStream)) {

    while (rows.hasNextValue()) {
        FlatOrder row = rows.nextValue();
        // Chuyển row thành domain object hoặc xử lý trực tiếp.
    }
}
~~~

Ghi nhiều hàng:

~~~java
try (SequenceWriter writer = csvMapper
        .writer(schema)
        .writeValues(outputStream)) {

    for (FlatOrder row : rows) {
        writer.write(row);
    }
}
~~~

Với cách này, mỗi FlatOrder tương ứng một dòng và mỗi property tương ứng một cột. Cấu trúc phẳng là chủ ý của DTO, giúp schema dễ kiểm soát.

## 14. Chuyển đổi giữa domain object và CSV row

Không cần ép domain object lồng nhau trở thành CSV DTO. Có thể viết adapter hai chiều:

~~~java
FlatOrder toCsvRow(Order order) {
    FlatOrder row = new FlatOrder();
    row.setOrderId(order.getOrderId());

    if (order.getCustomer() != null) {
        row.setCustomerName(order.getCustomer().getName());
    }

    if (order.getShippingAddress() != null) {
        row.setShippingCity(order.getShippingAddress().getCity());
        row.setShippingPostalCode(
                order.getShippingAddress().getPostalCode()
        );
    }

    return row;
}
~~~

Chiều đọc:

~~~java
Order toDomain(FlatOrder row) {
    Order order = new Order();
    order.setOrderId(row.getOrderId());

    if (row.getCustomerName() != null) {
        Customer customer = new Customer();
        customer.setName(row.getCustomerName());
        order.setCustomer(customer);
    }

    if (row.getShippingCity() != null
            || row.getShippingPostalCode() != null) {
        Address address = new Address();
        address.setCity(row.getShippingCity());
        address.setPostalCode(row.getShippingPostalCode());
        order.setShippingAddress(address);
    }

    return order;
}
~~~

Adapter cần quy định cách phân biệt object cha null với object cha tồn tại nhưng tất cả field con đều rỗng. Nếu CSV không có cột presence hoặc sentinel, hai trạng thái có thể không thể khôi phục khác nhau.

## 15. Không nên giả định CsvMapper tự flatten mọi POJO

CsvMapper cần schema cột phẳng. Một POJO có property là object con hoặc List không tự nhiên biến thành một tập cột có cấu trúc như YAML.

Có thể dùng các kỹ thuật như @JsonUnwrapped trong một số mapper/format để làm phẳng property, nhưng kết quả với CSV phụ thuộc cách introspection và CsvSchema được xây dựng. Không nên coi @JsonUnwrapped là giải pháp tổng quát cho array lồng nhau hoặc schema động.

Nếu dùng annotation để flatten, hãy:

- Kiểm tra schema được tạo có đúng các cột mong muốn không.
- Định nghĩa prefix/suffix để tránh tên cột trùng.
- Kiểm thử cả serialization và deserialization.
- Xử lý riêng null parent và field con bị thiếu.
- Không dùng cách này cho collection độ dài tùy ý.

Với hợp đồng CSV lâu dài, DTO phẳng cùng CsvSchema tường minh thường dễ hiểu và ổn định hơn việc dựa vào một graph POJO phức tạp.

## 16. Đặt delimiter, header và thứ tự cột

CSV không nhất thiết dùng dấu phẩy. Một số hệ thống dùng dấu chấm phẩy hoặc tab. CsvSchema có thể xác định delimiter:

~~~java
CsvSchema schema = CsvSchema.builder()
        .addColumn("orderId")
        .addColumn("customerName")
        .addColumn("shippingCity")
        .build()
        .withColumnSeparator(';')
        .withHeader();
~~~

Thứ tự cột trong CsvSchema là một phần của hợp đồng. Không nên phụ thuộc thứ tự property ngẫu nhiên từ reflection hoặc thứ tự field trong source.

Khi trao đổi với spreadsheet, cần thống nhất:

- Dấu phân cách.
- Encoding, thường là UTF-8.
- Có header hay không.
- Quy tắc newline.
- Quy tắc quote và escape.
- Cách biểu diễn null.
- Format số, ngày giờ và decimal.
- Locale của người dùng hoặc hệ thống nhập.

CSV không có metadata chuẩn bên trong file để tự mô tả tất cả các quy tắc này. Có thể cung cấp schema/manifest đi kèm.

## 17. YAML phù hợp khi cần giữ cấu trúc lồng nhau

Nếu mục tiêu là lưu trữ hoặc trao đổi dữ liệu có object, array, null và kiểu scalar rõ ràng, YAML thường biểu diễn trực tiếp hơn CSV.

Ví dụ cùng dữ liệu:

~~~yaml
orderId: O-200
customer:
  id: C-100
  name: Lan
shippingAddress:
  city: Da Nang
  postalCode: "550000"
items:
  - sku: KB-01
    quantity: 2
  - sku: MS-02
    quantity: 1
~~~

YAML có thể giữ:

- Cấu trúc object con.
- Danh sách có độ dài tùy ý.
- Null và các kiểu scalar theo quy tắc YAML.
- Cấu trúc có nhiều cấp mà không cần tự đặt tên cột.

Jackson YAML module cung cấp YAMLMapper để đọc/ghi YAML bằng mô hình Databind:

~~~java
import com.fasterxml.jackson.dataformat.yaml.YAMLMapper;

YAMLMapper yamlMapper = new YAMLMapper();
Order order = yamlMapper.readValue(yaml, Order.class);
String output = yamlMapper.writeValueAsString(order);
~~~

YAML cũng có các đặc điểm riêng như indentation, scalar typing, alias/anchor và quy tắc an toàn khi parse. Dùng YAML không có nghĩa bỏ qua validation hoặc giới hạn tài nguyên. Nếu dữ liệu cần tương tác bằng spreadsheet hoặc truy vấn theo từng cột, CSV vẫn có ưu thế.

## 18. Chọn định dạng theo mục đích sử dụng

| Nhu cầu | Định dạng/cách biểu diễn phù hợp |
|---|---|
| Phân tích dữ liệu bằng spreadsheet | CSV phẳng |
| Bảng có object con với số field cố định | Flatten CSV |
| Quan hệ một-nhiều cần lọc/tổng hợp | Nhiều CSV liên kết bằng khóa |
| Cần giữ array lồng nhau trong một dòng | JSON-in-cell nếu người dùng chấp nhận |
| Cấu hình có object và list nhiều cấp | YAML |
| API trao đổi object/array | JSON thường tự nhiên hơn |
| Cần khôi phục chính xác cấu trúc lồng nhau | YAML/JSON hoặc schema CSV có adapter rõ ràng |
| Báo cáo cho người dùng cuối | CSV với cột được chọn theo mục tiêu báo cáo |

Không nên chọn CSV chỉ vì file dễ mở. Nếu người dùng cần tái tạo object graph, phải tính cả chi phí adapter, schema version và xử lý null/array.

## 19. Round-trip không tự bảo toàn cấu trúc

Một round-trip là:

~~~text
Domain object
      |
      v
CSV row(s)
      |
      v
CSV parser
      |
      v
Domain object mới
~~~

Để round-trip chính xác, cần giữ đủ thông tin:

- Mọi field lồng nhau được ánh xạ sang cột nào?
- Array được tách thành nhiều hàng hay lưu trong cell?
- Thứ tự array được giữ bằng cột index nào?
- Object null và object rỗng phân biệt ra sao?
- String rỗng, null và field thiếu có khác nhau không?
- Số lớn, decimal và ngày giờ được format thế nào?
- Các hàng cùng parent được nhóm theo khóa nào?
- Có thể có hai object cha cùng ID không?

Nếu bỏ các thông tin này, chuyển đổi CSV có thể mất dữ liệu hoặc không thể tái tạo duy nhất object ban đầu. Đây không phải lỗi của Jackson; đó là giới hạn của schema bảng đã chọn.

## 20. Kiểm thử chuyển đổi cấu trúc lồng nhau

Nên kiểm thử cả giá trị thông thường và trường hợp biên:

| Ca | Dữ liệu | Điều cần xác nhận |
|---|---|---|
| T01 | Object con có đủ field | Flatten và unflatten giữ giá trị |
| T02 | Object con null | Có phân biệt với object rỗng không |
| T03 | Object con rỗng | Các cột con rỗng được hiểu thế nào |
| T04 | Array có nhiều phần tử | Thứ tự và số lượng được giữ |
| T05 | Array rỗng | Có biểu diễn được order không có item không |
| T06 | String có dấu phẩy/quote/newline | CSV quoting đúng |
| T07 | JSON-in-cell | Hai tầng parse/serialize round-trip đúng |
| T08 | Null và empty string | Sentinel/contract được áp dụng nhất quán |
| T09 | Field mới trong object con | Schema CSV có được version hóa không |
| T10 | Hai hàng có cùng parent key nhưng parent fields khác nhau | Import phát hiện dữ liệu mâu thuẫn |
| T11 | Hàng item không có parent | Phát hiện khóa ngoại thiếu |
| T12 | Header thiếu hoặc sai thứ tự | Reader xử lý theo schema đã công bố |

Ví dụ kiểm thử JSON-in-cell:

~~~java
String itemsJson = mapper.writeValueAsString(
        List.of(
                new OrderLine("KB-01", 2),
                new OrderLine("MS-02", 1)
        )
);

List<OrderLine> restored = mapper.readValue(
        itemsJson,
        new TypeReference<List<OrderLine>>() {}
);

assertEquals(2, restored.size());
assertEquals("KB-01", restored.get(0).getSku());
~~~

Test này kiểm tra phần JSON trong cell. Cần thêm test CSV bao quanh để xác nhận CsvMapper quote và đọc lại chuỗi cell mà không làm hỏng JSON bên trong.

## 21. Các lỗi thiết kế thường gặp

### Cố nhét object vào một cột mà không có format nội bộ

Một giá trị như city=Da Nang;postalCode=550000 là quy ước riêng. Nếu field chứa dấu phân cách, không thể tách an toàn bằng split đơn giản. Dùng JSON-in-cell hoặc schema rõ ràng.

### Tạo một cột cho mỗi vị trí array cố định

item1, item2, item3 giới hạn độ dài array và làm header thay đổi khi có thêm phần tử. Chỉ dùng khi số slot là cố định theo nghiệp vụ.

### Lặp dữ liệu cha nhưng không có khóa nhóm

Nếu không có orderId, không thể biết các hàng nào thuộc cùng một object cha. Dùng khóa ổn định và kiểm tra tính duy nhất.

### Không giữ thứ tự array

Nếu array biểu diễn thứ tự ưu tiên hoặc trình tự xử lý, thêm index/sequence. Không dựa vào thứ tự hàng ngầm định.

### Dùng chuỗi rỗng để biểu diễn mọi trạng thái

Null, empty, missing và not-applicable có thể mang ý nghĩa khác nhau. Quy định sentinel hoặc thêm cột presence.

### Tự nối chuỗi CSV

Tên khách hàng hoặc JSON cell có thể chứa delimiter, quote và newline. Dùng CsvMapper hoặc thư viện CSV để quote đúng.

### Giả định tên cột dạng path tự tạo object

customer.name chỉ là tên cột. Reader cần adapter/schema để ánh xạ về object customer.

### Chỉ test số lượng cột

Một file có đúng header vẫn có thể mất array order, null semantics hoặc quan hệ cha/con. Test phải xác nhận dữ liệu khôi phục.

## 22. Quy trình chọn cách xuất dữ liệu lồng nhau

Trước khi thiết kế CSV, hãy trả lời:

1. Người nhận cần phân tích từng field hay cần tái tạo object gốc?
2. Độ sâu object có cố định không?
3. Array có độ dài tùy ý không?
4. Có quan hệ một-nhiều hoặc nhiều-nhiều không?
5. Có cần giữ thứ tự phần tử không?
6. Null, empty và missing có ý nghĩa khác nhau không?
7. File có được mở bằng spreadsheet không?
8. Có chấp nhận JSON trong một cell không?
9. Schema cột có được version hóa và phân phối kèm file không?
10. Round-trip có phải giữ nguyên toàn bộ dữ liệu hay chỉ một tập field phục vụ báo cáo?

Nếu cấu trúc lồng nhau đơn giản và cố định, flatten có thể phù hợp. Nếu có nhiều phần tử con, hãy cân nhắc nhiều file CSV liên kết bằng khóa. Nếu cần giữ nguyên cấu trúc tùy ý, dùng JSON/YAML hoặc JSON-in-cell với quy ước rõ.

## 23. Kết luận

CSV là định dạng bảng phẳng gồm hàng và cột; nó không có kiểu object, array hoặc quan hệ lồng nhau như YAML. Khi xuất cấu trúc Java/YAML lồng nhau sang CSV, ứng dụng phải chọn cách flatten thành cột, lặp parent thành nhiều hàng, chuẩn hóa thành nhiều file có khóa liên kết hoặc nhúng JSON vào một cell. CsvMapper và CsvSchema giúp đọc/ghi bảng CSV nhưng không tự biến schema phẳng thành object graph tùy ý. Quoting chỉ bảo vệ giá trị cell có delimiter hoặc newline, không tạo nested structure. Muốn round-trip đáng tin cậy, cần định nghĩa rõ null, empty, array order, khóa nhóm, header và schema version. Nếu người nhận cần cấu trúc lồng nhau nguyên vẹn, YAML hoặc JSON thường phù hợp hơn; nếu mục tiêu là phân tích bảng, hãy thiết kế CSV phẳng và adapter chuyển đổi rõ ràng.
