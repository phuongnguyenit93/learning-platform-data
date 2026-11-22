# Khởi tạo đệ quy đối tượng con, List, Map và mảng bằng constructor binding trong Spring Framework

**Constructor binding** là cách Spring Framework tạo một đối tượng Java từ dữ liệu đầu vào bằng cách khớp các giá trị với **tham số constructor**, chuyển đổi kiểu và gọi constructor. Khi một tham số lại là đối tượng hoặc container phức tạp, Spring có thể tiếp tục xây dựng các giá trị ở bên trong: **đối tượng con, `List`, `Map` và mảng**. Đó là ý nghĩa của **khởi tạo đệ quy** (recursive construction).

Đây là chủ đề thuộc luồng **gắn dữ liệu qua constructor**, dùng cơ chế `DataBinder.construct(...)` (Spring Framework 6.1+) và tích hợp `@ModelAttribute` của Spring MVC. Phân biệt nó với property binding qua setter và với việc deserialize JSON của `@RequestBody`.

Ví dụ và khái niệm dùng Java 17+ và Spring Framework 6.2.x. Các dạng payload được mô tả là request parameter, query parameter hoặc form-urlencoded, trong đó **tên trường** chỉ ra đường dẫn vào cấu trúc Java. Dữ liệu từ client luôn phải được kiểm tra kiểu, độ lớn, tính hợp lệ và quyền nghiệp vụ.

## 1. Một request có thể xây dựng cả cây đối tượng như thế nào?

Xét dữ liệu của một form tạo đơn hàng:

```text
recipient.name=Lan
recipient.address.city=Ha Noi
items[0].sku=PEN
items[0].quantity=2
items[1].sku=BOOK
items[1].quantity=4
pickupPoints[office].city=Da Nang
pickupPoints[home].city=Hue
tags[0]=gift
tags[1]=urgent
```

Ta muốn tạo object bất biến như sau:

```java
public record Address(String city) {}

public record Recipient(String name, Address address) {}

public record LineItem(String sku, int quantity) {}

public record OrderInput(
    Recipient recipient,
    List<LineItem> items,
    Map<String, Address> pickupPoints,
    String[] tags
) {}
```

Đây là **khai báo loại dữ liệu minh họa**; để lưu thành các file Java độc lập, mỗi `public record` phải nằm trong file cùng tên và có import `java.util.List`/`java.util.Map`. Ví dụ runnable đầy đủ ở mục 7 đặt record vào cùng một class.

Sau khi constructor binding thành công, cấu trúc mong muốn:

```text
OrderInput
├─ recipient: Recipient
│  ├─ name = "Lan"
│  └─ address: Address
│     └─ city = "Ha Noi"
├─ items: List<LineItem>
│  ├─ [0] LineItem(sku="PEN", quantity=2)
│  └─ [1] LineItem(sku="BOOK", quantity=4)
├─ pickupPoints: Map<String, Address>
│  ├─ "office" -> Address(city="Da Nang")
│  └─ "home"   -> Address(city="Hue")
└─ tags: String[]
   ├─ [0] "gift"
   └─ [1] "urgent"
```

Trong luồng constructor binding, Spring **không cần một instance `OrderInput` ban đầu** và không bắt buộc các nested record phải có constructor rỗng hoặc setter. Nó phải biết cấu trúc kiểu, tên tham số constructor và các giá trị liên quan. Spring tạo lần lượt các object cần thiết để truyền làm **tham số cho constructor của object cha**. Nếu không có dữ liệu phù hợp cho một nhánh tùy chọn, nhánh đó có thể vắng mặt thay vì được tạo vô điều kiện.

## 2. Hai hình thức binding phải phân biệt

| Khía cạnh | Constructor binding | Property binding |
| --- | --- | --- |
| Đối tượng gốc | Được xây dựng mới bằng data constructor | Thường là instance đã có; có thể được tạo bằng constructor không tham số trước đó |
| Điểm nhận dữ liệu | Tham số constructor, dựa theo tên | JavaBeans property qua setter hoặc field access được cấu hình |
| Object con | Có thể tạo đệ quy theo data constructor | Có thể đi theo nested path và auto-grow nếu điều kiện cho phép |
| Record / lớp immutable | Phù hợp | Không thể tự ý ghi các field bất biến sau khi tạo |
| `List`, `Map`, mảng | Có thể tạo từ indexed keys hoặc conversion thích hợp | Có thể gán/mở rộng các property có thể ghi |
| API Spring Core | `DataBinder.construct(ValueResolver)` | `DataBinder.bind(PropertyValues)` |
| Rủi ro chính | Constructor nhận quá nhiều tham số/graph quá lớn; thiếu dữ liệu, lỗi conversion | Mass assignment qua setter/field, tự tăng index/path không kiểm soát |

**Điểm rất quan trọng:** Spring MVC mặc định có thể thực hiện **cả hai** dạng binding đối với model attribute phù hợp. Việc dùng record hoặc constructor có tham số giải quyết phần khởi tạo nhưng chưa tự động quy định chế độ property binding cho mọi loại target. Nếu cần constructor binding theo kiểu declarative, cấu hình `setDeclarativeBinding(true)` ở binder; property binding khi đó chỉ hoạt động nếu đã khai báo `allowedFields`.

Không dùng `@RequestBody` như một từ đồng nghĩa: `@RequestBody` thường được deserialize bởi `HttpMessageConverter` (ví dụ Jackson cho JSON), có cơ chế tạo object và tên field khác với form parameter của `@ModelAttribute`.

## 3. Spring quyết định constructor và tìm tên tham số ra sao?

### 3.1. Điều kiện để khởi tạo

Theo tài liệu Spring, lớp đích nên có một public data constructor hoặc một non-public constructor duy nhất có tham số. Nếu lớp có nhiều constructor, constructor mặc định (nếu có) có thể được chọn. Để tránh mơ hồ, DTO dùng một constructor chính rõ ràng; record là ví dụ lý tưởng.

```java
public record ProductLine(String sku, int quantity) {}
```

Đối với record trên, constructor tương ứng với hai component `sku` và `quantity`. Spring tra tên đó trong dữ liệu đầu vào rồi chuyển `"2"` sang `int` trước khi gọi constructor.

Với class Java tự viết:

```java
public final class ProductLine {
    private final String sku;
    private final int quantity;

    public ProductLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String sku() { return sku; }
    public int quantity() { return quantity; }
}
```

Trong project Java thông thường, compile với metadata tên tham số constructor (ví dụ `javac -parameters` hoặc Maven compiler `<parameters>true</parameters>`) để Spring biết tên `sku`, `quantity`. Một số loại class còn hỗ trợ metadata khác như `@ConstructorProperties`. Nếu thiếu tên tham số, Spring không thể tự suy đoán tên từ ý nghĩa của field.

### 3.2. Luồng xử lý đệ quy

Mô hình khái niệm:

```text
DataBinder(target=null, objectName="orderInput")
    |
    +-- setTargetType(OrderInput)
    |
    +-- construct(ValueResolver)
            |
            +-- Xác định data constructor của OrderInput
            |
            +-- Đọc tham số "recipient" -> Recipient
            |       +-- "recipient.name" -> String
            |       +-- "recipient.address" -> Address
            |                +-- "recipient.address.city" -> String
            |                +-- new Address(city)
            |       +-- new Recipient(name, address)
            |
            +-- Đọc tham số "items" -> List<LineItem>
            |       +-- "items[0].sku", "items[0].quantity"
            |       +-- new LineItem(...)
            |       +-- "items[1].sku", "items[1].quantity"
            |       +-- new LineItem(...)
            |       +-- tập hợp các item vào List
            |
            +-- Đọc "pickupPoints" -> Map<String, Address>
            |       +-- key "office" -> new Address(...)
            |       +-- key "home" -> new Address(...)
            |
            +-- Đọc "tags" -> String[]
            |       +-- "tags[0]" -> "gift"
            |       +-- "tags[1]" -> "urgent"
            |
            +-- new OrderInput(recipient, items, pickupPoints, tags)
    |
    +-- getTarget() / getBindingResult()
```

Đây là luồng giải thích **quan hệ phụ thuộc khi tạo object**, không phải mã nguồn trình tự reflection chi tiết hay một cam kết mỗi bước sẽ được thực thi đúng thứ tự trong mọi phiên bản Spring. Ý tưởng là để gọi constructor cha, Spring phải chuẩn bị được từng tham số; tham số phức tạp lại được dựng từ tên đường dẫn của dữ liệu con.

### 3.3. Vai trò của `DataBinder.ValueResolver`

Để constructor binding ngoài web, `DataBinder.construct(...)` nhận một `ValueResolver` có hai trách nhiệm:

```java
Object resolveValue(String name, Class<?> type);
Set<String> getNames();
```

- `resolveValue(name, type)` trả giá trị thô cho tên đang tìm, ví dụ `"items[0].quantity"` → `"2"`. Trả `null` nếu không có giá trị cho đúng tên.
- `getNames()` cung cấp tập tất cả tên field. Spring có thể nhận biết rằng không có giá trị trực tiếp ở `"recipient"` nhưng vẫn có những đường dẫn con như `"recipient.address.city"`, từ đó quyết định có cần xây dựng cấu trúc nested hay không.
- `type` là kiểu mục tiêu mà resolver có thể dùng để phân giải; implementation đơn giản có thể trả raw strings và để `DataBinder` chuyển đổi.
- Đây là một giao diện **phục vụ tra dữ liệu đầu vào**, không phải nơi tự viết logic gọi constructor cho từng class.

Trong Spring MVC, framework đã cung cấp resolver phù hợp cho dữ liệu HTTP. Khi gọi `DataBinder` trực tiếp, người viết ứng dụng tự cung cấp resolver như ví dụ đầy đủ bên dưới.

## 4. Quy tắc tên trường cho object, List, Map và array

| Dữ liệu gửi lên | Constructor argument đích | Ý nghĩa |
| --- | --- | --- |
| `recipient.name=Lan` | `recipient.name` | Tham số `name` của object `Recipient` |
| `recipient.address.city=Ha Noi` | `recipient.address.city` | Constructor `Address(city)` lồng trong `Recipient` |
| `items[0].sku=PEN` | `items` kiểu `List<LineItem>` | Phần tử List vị trí 0, tham số `sku` |
| `items[1].quantity=4` | `items` kiểu `List<LineItem>` | Phần tử thứ hai, tham số `quantity` được chuyển sang số |
| `tags[0]=gift` | `tags` kiểu `String[]` | Phần tử mảng tại index 0 |
| `pickupPoints[office].city=Da Nang` | `pickupPoints` kiểu `Map<String, Address>` | Giá trị object của entry khóa `office` |
| `settings[locale]=vi` | `settings` kiểu `Map<String, String>` | Entry Map với key `locale` và value `vi` |

Quy tắc cần nhớ:

1. **Dấu chấm** trong tên field phân cấp object: `recipient.address.city`.
2. **Dấu ngoặc vuông chứa số** biểu thị chỉ số trong `List` hoặc array: `items[0]`, `tags[1]`. Index thường bắt đầu từ 0.
3. **Dấu ngoặc vuông chứa key** biểu thị một entry của `Map`: `settings[locale]`. `Map` không phải List có thứ tự index.
4. Phần tên trước dấu ngoặc phải khớp **tham số constructor**, kể cả phân biệt chữ hoa/chữ thường.
5. Không thêm `orderInput.` vào đầu field khi argument có tên `@ModelAttribute("orderInput")`; đây là tên model attribute ở Spring MVC, không phải thuộc tính nằm trong object.
6. Khi form được gửi qua URL/HTTP, ký tự `[` và `]` phải được encode đúng quy tắc HTTP; dùng thư viện xây dựng form thay vì tự nối chuỗi.
7. Với key Map có ký tự đặc biệt, đường dẫn cần cú pháp được parser hỗ trợ (chẳng hạn dạng quoted key khi thích hợp). Tránh tự dựng property path từ key không tin cậy.

## 5. Tạo object con qua constructor

Ví dụ:

```java
public record Address(String city, String postalCode) {}

public record Recipient(String name, Address address) {}
```

Input:

```text
recipient.name=Lan
recipient.address.city=Ha Noi
recipient.address.postalCode=10000
```

Bởi `Recipient` cần `Address` trong constructor, Spring xử lý các trường của `Address` để dựng `new Address("Ha Noi", "10000")`, sau đó dùng nó khi dựng `Recipient`. Không cần `Recipient.setAddress(...)` hoặc `Address.setCity(...)`.

**Vì sao có thể xây đệ quy?** Spring nhìn thấy `Recipient` là một kiểu object có data constructor và các field có tiền tố `recipient.`; khi xử lý tham số `address`, các giá trị có tiền tố `recipient.address.` cho biết cách xây object đó. Cơ chế này phụ thuộc khả năng xác định constructor/parameter names, convert kiểu, và việc Spring nhận diện kiểu là đối tượng cần dựng thay vì scalar.

Nếu request chỉ có:

```text
recipient.name=Lan
```

thì không nên giả định `Address` chắc chắn được tạo với mọi field null. Khi không có các tên con, Spring có thể xem argument con là thiếu; khi có một số tên con nhưng thiếu trường bắt buộc, object có thể được tạo với giá trị thiếu hoặc binder ghi lỗi tùy kiểu/constructor. Thiết kế DTO và validation phải làm rõ những field nào bắt buộc.

**Lồng quá sâu** có thể khiến graph khó validate, khó hiểu và tạo ra chi phí xử lý lớn. Nên giữ DTO đầu vào có độ sâu hợp lý và kiểm soát payload ngay tại biên ứng dụng.

## 6. Tạo `List` từ input có chỉ số

### 6.1. List các record

Với `List<LineItem> items` và:

```text
items[0].sku=PEN
items[0].quantity=2
items[1].sku=BOOK
items[1].quantity=4
```

Spring nhận biết tham số container `items` và các index 0, 1 từ tập tên của `ValueResolver`, rồi có thể tạo các phần tử `LineItem` bằng constructor của chúng. Chuỗi `"4"` được chuyển thành `int 4` theo khả năng conversion hiện có.

Không có yêu cầu bắt buộc `LineItem` có setter hoặc constructor không tham số nếu constructor binding dùng data constructor phù hợp.

### 6.2. List primitive/scalar

Một tham số `List<Integer> scores` có thể nhận các key:

```text
scores[0]=10
scores[1]=20
scores[2]=30
```

Từng phần tử cần được chuyển từ chuỗi thành `Integer`. Generic `List<Integer>` giúp framework biết loại phần tử; khai báo raw `List` khiến thông tin kiểu bị mất, có thể gây hạn chế conversion và dựng phần tử.

Cần phân biệt ba cách gửi dữ liệu:

- Nhiều indexed keys: `scores[0]=10`, `scores[1]=20`.
- Một giá trị chứa danh sách: `scores=10,20`, nếu có converter/editor phù hợp cho kiểu đích.
- Nhiều giá trị cùng một tên `scores`, nếu HTTP value resolver và conversion hỗ trợ đúng tình huống.

Spring hỗ trợ constructor binding collection từ **một chuỗi phù hợp** hoặc từ **indexed keys**; không có nghĩa mọi loại record/Map phức tạp đều có thể biến từ một chuỗi CSV.

### 6.3. Index thưa, trùng hoặc quá lớn

Với `items[2].sku=BOOK` nhưng thiếu index 0 và 1, không được suy luận rằng constructor binding tự tạo chính xác một phần tử tương ứng với index 2 rồi rút gọn List xuống size 1. Indexed input có thể dẫn tới vị trí trống hoặc xử lý không mong muốn, phụ thuộc phiên bản/cấu hình. Phía UI nên phát sinh index liên tiếp khi cần List có thứ tự; phía server cần validate kích thước và từng item.

Index như `items[999999]` có thể gây áp lực bộ nhớ/CPU nếu được xử lý vô hạn. Đừng chỉ dựa vào `setAutoGrowCollectionLimit(...)` như một giới hạn chung cho tất cả constructor binding: Javadoc và hành vi có thể khác theo nhánh/phiên bản. Áp dụng giới hạn request ở web server/gateway, quy tắc giới hạn số dòng, mức index tối đa và validation sau tạo. Index trong List **không phải** ID persisted; ID nghiệp vụ phải xác thực lại.

## 7. Tạo `Map` với khóa và giá trị object

Với `Map<String, Address> pickupPoints`:

```text
pickupPoints[office].city=Da Nang
pickupPoints[home].city=Hue
```

Constructor binding có thể tạo các object `Address` dưới mỗi entry của `Map` và truyền Map đó cho constructor của `OrderInput`.

- `office`, `home` là **key**, không phải số thứ tự.
- Kiểu `String` của key và `Address` của value cần được mô tả rõ qua generic để binding hoạt động như kỳ vọng.
- Với `Map<String, Integer> stock`, một key `stock[pen]=12` cần conversion `"12"` → `Integer 12`.
- Với `Map<Long, String>`, ngoài value, key `"42"` còn cần conversion sang `Long`; hỗ trợ chi tiết phụ thuộc converter/type metadata.
- Không dựa vào thứ tự duyệt `HashMap` để xác định entry thứ nhất, thứ hai; `Map` diễn tả tập quan hệ key-value, không phải danh sách item theo vị trí.
- Không mặc định Spring chấp nhận mọi key tùy ý như `metadata[role]`; **ứng dụng** phải quyết định key nào thuộc hợp đồng đầu vào.

Một Map chứa object lồng nhau cũng có thể có cấu trúc như `Map<String, List<LineItem>>`. Đây là tổ hợp hợp lệ ở mức kiểu Java; mức hỗ trợ chính xác của indexed path, conversion và nested construction cần kiểm thử với phiên bản Spring ứng dụng. Đừng khẳng định mọi hình dạng generic lồng nhau phức tạp đều tự động dựng thành công.

## 8. Tạo mảng trong constructor binding

Ví dụ tham số constructor `String[] tags`:

```text
tags[0]=gift
tags[1]=urgent
```

Spring có thể tạo mảng với các giá trị tương ứng rồi truyền nó vào constructor. Mảng Java có kích thước cố định đối với **một instance**, nhưng trong constructor binding, mảng được **tạo ra** với số phần tử phù hợp để làm đối số; không yêu cầu tạo mảng rỗng trước đó rồi tăng kích thước bằng setter.

Với `int[] quantities`, các giá trị thô `"2"`, `"4"` phải chuyển thành số nguyên. Với `Address[] addresses`, các tên `addresses[0].city` và `addresses[1].city` có thể chỉ ra các record cần dựng ở từng vị trí. Lỗi conversion hoặc constructor có thể phát sinh nếu giá trị không hợp lệ.

Mảng thường phù hợp với input nhỏ, có thứ tự và kiểu thành phần xác định. `List<T>` linh hoạt hơn khi biểu mẫu thêm/xóa dòng và cần thao tác collection. Cả hai đều phải giới hạn số phần tử từ client.

## 9. Ví dụ hoàn chỉnh: Java 17 + Spring `DataBinder.construct`

Ví dụ này thực sự dùng **constructor binding**, không gọi setter hay `binder.bind(...)`. Nó chứng minh đồng thời:

1. `Recipient` và `Address` được dựng từ nested path.
2. `List<LineItem>` được tạo từ index 0 và 1.
3. `Map<String, Address>` được tạo từ khóa `home`, `office` và nested value.
4. `String[]` nhận các phần tử đánh index.
5. Chuỗi `"2"` và `"4"` được chuyển thành `int`.
6. `BindingResult` được kiểm tra sau `construct`.

### 9.1. Cấu trúc dự án

```text
constructor-graph-demo/
├── pom.xml
└── src/main/java/example/ConstructorGraphDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>constructor-graph-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.ConstructorGraphDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/ConstructorGraphDemo.java`:

```java
package example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.core.ResolvableType;
import org.springframework.validation.DataBinder;

public class ConstructorGraphDemo {

    public record Address(String city) {}

    public record Recipient(String name, Address address) {}

    public record LineItem(String sku, int quantity) {}

    public record OrderInput(
        Recipient recipient,
        List<LineItem> items,
        Map<String, Address> pickupPoints,
        String[] tags
    ) {}

    public static void main(String[] args) {
        Map<String, Object> input = new LinkedHashMap<>();

        input.put("recipient.name", "Lan");
        input.put("recipient.address.city", "Ha Noi");

        input.put("items[0].sku", "PEN");
        input.put("items[0].quantity", "2");
        input.put("items[1].sku", "BOOK");
        input.put("items[1].quantity", "4");

        input.put("pickupPoints[office].city", "Da Nang");
        input.put("pickupPoints[home].city", "Hue");

        input.put("tags[0]", "gift");
        input.put("tags[1]", "urgent");

        DataBinder binder = new DataBinder(null, "orderInput");
        binder.setTargetType(ResolvableType.forClass(OrderInput.class));

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> targetType) {
                return input.get(name);
            }

            @Override
            public Set<String> getNames() {
                return input.keySet();
            }
        });

        if (binder.getBindingResult().hasErrors()) {
            throw new IllegalStateException(
                "Constructor binding failed: " + binder.getBindingResult()
            );
        }

        OrderInput order = (OrderInput) binder.getTarget();
        if (order == null) {
            throw new IllegalStateException("No target was constructed");
        }

        System.out.println(
            order.recipient().name() + " / "
                + order.recipient().address().city()
        );
        System.out.println("items=" + order.items().size());
        System.out.println(
            "item2=" + order.items().get(1).sku() + ":"
                + order.items().get(1).quantity()
        );
        System.out.println(
            "pickup=" + order.pickupPoints().get("office").city()
        );
        System.out.println("tags=" + Arrays.toString(order.tags()));
        System.out.println(
            "errors=" + binder.getBindingResult().hasErrors()
        );
    }
}
```

Chạy từ thư mục `constructor-graph-demo`:

```bash
mvn -q compile exec:java
```

`stdout` dự kiến khi binder dựng thành công object graph (không tính log Maven nếu môi trường in thêm):

```text
Lan / Ha Noi
items=2
item2=BOOK:4
pickup=Da Nang
tags=[gift, urgent]
errors=false
```

**Giải thích đầu ra:**

- Hai record `Recipient` và `Address` cùng được tạo từ các giá trị có tiền tố `recipient.`; `Lan / Ha Noi` là dữ liệu sau khi constructor đệ quy.
- `items.size() == 2`; phần tử thứ hai là `LineItem("BOOK", 4)`, chứng minh Spring đã convert giá trị chuỗi `"4"` thành `int`.
- `pickupPoints.get("office").city()` đọc object được dựng ở map key `office`.
- `Arrays.toString(tags)` cho biết mảng nhận đúng hai phần tử theo index.
- `errors=false` thể hiện các giá trị trong kịch bản này hợp lệ cho constructor và conversion, **không thay thế** validation nghiệp vụ.

Các nested record của `ConstructorGraphDemo` đều là `public`, có data constructor rõ ràng; không có setter. `ValueResolver.getNames()` trả đủ các tên input, cho phép Spring phát hiện cả nested và indexed paths. `spring-context` chứa/transitively cung cấp các thư viện Spring cần cho `DataBinder` và conversion.

Nếu ví dụ chạy sai trên một phiên bản Spring khác, trước tiên kiểm tra phiên bản thực dùng, metadata constructor, cú pháp path, conversion, và `BindingResult`; đừng tự đổi sang `bind(PropertyValues)` vì như vậy sẽ chuyển bài học sang property binding.

## 10. Dùng trong Spring MVC với `@ModelAttribute`

Trong Spring MVC, framework tạo `WebDataBinder` và cung cấp `ValueResolver` dựa trên request; handler thường không cần tự gọi `construct`. Ví dụ:

```java
@RestController
class OrderController {

    @InitBinder("orderInput")
    void configure(WebDataBinder binder) {
        binder.setDeclarativeBinding(true);
    }

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    String create(
        @Valid @ModelAttribute("orderInput") OrderInput form,
        BindingResult errors
    ) {
        if (errors.hasErrors()) {
            return "INVALID";
        }
        return form.recipient().name() + " / "
            + form.items().size();
    }
}
```

Đây là **mã tích hợp**, giả định các record `OrderInput`/`Recipient`/`LineItem`/`Address` có thể dùng trong controller và đã cấu hình web, imports, validator. Request form với các tên key như mục 1 có thể được Spring gắn qua data constructor của các record.

Các điểm phải phân biệt:

- `@ModelAttribute("orderInput")` đặt **tên model attribute** để binder tìm/tạo target. Tên tham số con vẫn là `recipient.name`, `items[0].sku`, ...
- `@InitBinder("orderInput")` chỉ áp dụng cho binder của attribute tương ứng.
- `setDeclarativeBinding(true)` cho phép constructor binding, còn setter/property binding chỉ được thực hiện khi có `allowedFields` được khai báo. Điều này tránh vô tình gán thêm field có setter ngoài DTO đã thiết kế.
- `@Valid` cần provider Jakarta Bean Validation và constraint phù hợp mới kiểm tra nội dung. Nó không mặc nhiên kiểm tra số lượng, chiều sâu hay quyền truy cập.
- `BindingResult` phải đặt **ngay sau** tham số `@ModelAttribute` nếu handler muốn xử lý lỗi binding/validation. Có những lỗi tạo instance hoặc cấu hình nghiêm trọng vẫn có thể phát sinh exception.
- Với controller REST muốn nhận JSON, dùng `@RequestBody` và cấu hình JSON phù hợp: đó là luồng deserialize khác.

### 10.1. Đổi tên tham số constructor bằng `@BindParam`

Nếu HTML form gửi `recipient.postal-code=10000` nhưng tham số constructor Java tên `postalCode`, có thể dùng annotation:

```java
public record Recipient(
    String name,
    @BindParam("postal-code") String postalCode
) {}
```

Khi dùng kiểu này trong một object cha có tham số `recipient`, path của input sẽ là `recipient.postal-code`. Đây là **ví dụ thay thế thiết kế record Recipient**, không thể chép đồng thời vào demo mục 9 vốn khai báo `Recipient(name, Address address)`. `@BindParam` nằm ở `org.springframework.web.bind.annotation.BindParam` trong Spring MVC/WebFlux; API `DataBinder` thuần ngoài web có thể cấu hình `setNameResolver(...)` để hỗ trợ cách đặt tên tùy biến. Không suy luận rằng mọi `ValueResolver` tự biết tên alias nếu chưa có NameResolver phù hợp.

## 11. Kiểm soát lỗi conversion, thiếu dữ liệu và validation

### 11.1. Lỗi chuyển kiểu của phần tử con

Ví dụ:

```text
items[0].sku=PEN
items[0].quantity=abc
```

`LineItem.quantity` là `int`. Không có conversion hợp lệ từ `"abc"` sang `int`, nên binder có thể đăng ký lỗi cho đường dẫn `items[0].quantity`, thường với mã như `typeMismatch`. Kiểm tra `getBindingResult().getFieldErrors()` để lấy thông tin lỗi nếu binder đã thu thập được.

Không khẳng định rằng `getTarget()` sẽ luôn khác null sau bất kỳ lỗi conversion nào. Tài liệu Spring chỉ bảo đảm target được đặt nếu tạo thành công; một lỗi cấu hình/constructor cũng có thể ngăn việc tạo target. Với endpoint, đừng gọi service trên target thiếu/không hợp lệ.

### 11.2. Validation phải đệ quy theo mô hình

Một input DTO khai báo constraint ví dụ:

```java
public record Address(
    @NotBlank String city
) {}

public record LineItem(
    @NotBlank String sku,
    @Min(1) int quantity
) {}

public record OrderInput(
    @Valid Recipient recipient,
    @NotEmpty @Size(max = 20) List<@Valid LineItem> items,
    @Size(max = 5) Map<String, @Valid Address> pickupPoints,
    @Size(max = 5) String[] tags
) {}
```

Đây là **fragment minh họa annotation**, cần import `jakarta.validation.Valid` và `jakarta.validation.constraints.*`, lớp `Recipient` có cấu trúc tương thích, cùng provider Bean Validation ở runtime. `@Valid` trên object/element khai báo cascade vào nested object; chỉ có `@Valid` ở parameter của controller sẽ không luôn kiểm tra field bên trong khi quan hệ cascade không được đánh dấu.

Phân biệt:

| Vấn đề | Biện pháp phù hợp |
| --- | --- |
| `items[0].quantity=abc` | Type conversion; binding error |
| `items[0].quantity=-2` | Chuyển thành số được, nhưng cần `@Min(1)` hoặc validator nghiệp vụ |
| `items` trống | `@NotEmpty` nếu bắt buộc có item |
| `items` có hơn 20 phần tử | `@Size(max=20)` và giới hạn input/index trước khi cấp phát |
| `pickupPoints` chứa key lạ | Whitelist key/validator riêng ở tầng ứng dụng |
| `recipient.address.city` rỗng | Constraint trên field + `@Valid` cascade |
| `items[0].sku` tham chiếu sản phẩm không thuộc tài khoản | Authorization và kiểm tra service |

Các constraint kiểm tra sau khi object được bind; chúng không mặc nhiên giới hạn số lượng key request được parser chấp nhận trước đó.

### 11.3. Trường thiếu không đồng nghĩa lỗi conversion

Nếu thiếu `recipient.address.city`, không có chuỗi nào để convert. Spring có thể dựng object với dữ liệu thiếu hoặc coi argument là thiếu theo kiểu và quy tắc lựa chọn constructor. Muốn bắt buộc có thành phố, thêm constraint `@NotBlank`/`@NotNull` theo kiểu dữ liệu và bảo đảm cascade validation; tránh kỳ vọng binder tự kiểm tra toàn bộ điều kiện nghiệp vụ.

Với primitive `int`, giá trị thiếu có thể khó phân biệt với giá trị 0 sau một số đường xử lý; trong DTO đầu vào nên cân nhắc `Integer` và `@NotNull` nếu muốn phân biệt thiếu giá trị với nhập 0.

## 12. An toàn và giới hạn khi khởi tạo graph phức tạp

Constructor binding giúp giảm nguy cơ setter binding không kiểm soát, nhưng client vẫn có thể đặt rất nhiều key trỏ vào các constructor arguments mà DTO chấp nhận. Hãy coi kích thước graph và tên Map key là input không đáng tin.

Các nguyên tắc:

1. **Tạo DTO đầu vào riêng.** Chỉ khai báo các tham số constructor được phép đến từ client; tránh đưa `role`, `unitPrice`, `approved`, `ownerId`, `creditLimit` vào DTO chỉ vì entity domain có các trường đó.
2. **Giới hạn số phần tử trước binding.** Giới hạn tổng bytes/request parameters, chiều dài tên trường, số lượng field, index lớn nhất, độ sâu nested path. Không dùng riêng `@Size` sau bind để thay cho giới hạn cấp phát trước bind.
3. **Whitelist Map keys.** Nếu chỉ chấp nhận `office` và `home`, từ chối `pickupPoints[admin]` hoặc key không nằm trong quy ước. Kiểm tra số key, kiểu key và độ dài key.
4. **Không dùng List index làm ID nghiệp vụ.** `items[2]` chỉ là vị trí do client gửi, không chứng minh bản ghi database có ID 2 hay user có quyền sửa nó.
5. **Kiểm tra toàn bộ record lồng nhau.** `@Valid` cascade, constraint từng element và validator liên trường phải được áp dụng theo hợp đồng.
6. **Kiểm tra lỗi trước side effects.** Chỉ lưu/cập nhật sau khi binding/validation và authorization đều thành công.
7. **Chỉ bật property binding khi thật sự cần.** `setDeclarativeBinding(true)` hoặc allowlist chặt giúp tránh dữ liệu bên ngoài đi qua setter sau khi object đã được tạo.
8. **Không coi `setAllowedFields(...)` là một allowlist cho constructor arguments.** API đó áp dụng chủ yếu với property binding; chính thiết kế constructor/DTO quyết định tham số nào có thể được nhận qua constructor binding.
9. **Không mặc định giới hạn auto-grow của property binding bảo vệ mọi nhánh constructor binding.** Kiểm tra contract theo phiên bản đang dùng và đặt giới hạn tại request/application.
10. **Kiểm thử input bất thường.** Thử index âm, index rất lớn, index không liên tiếp, Map key lạ, nested object thiếu trường, array rỗng, phần tử có giá trị sai kiểu và request quá lớn.

Nếu client cần cập nhật entity đã tồn tại, một chiến lược an toàn là nhận DTO immutable bằng constructor, kiểm tra quyền/trạng thái, rồi áp dụng các giá trị được phép qua service hoặc phương thức nghiệp vụ của entity. Không để form tự quyết định mọi field của đối tượng persisted.

## 13. Các lỗi thiết kế và cách chẩn đoán

### 13.1. Spring không tìm được tham số constructor

**Triệu chứng:** object con rỗng/thiếu hoặc lỗi khi dựng dữ liệu mặc dù request có key hợp lý.

**Kiểm tra:** Tên record component có khớp key không? Class Java thường có metadata tham số (`-parameters`) không? Constructor có mơ hồ không? Có `@BindParam`/`NameResolver` tương ứng nếu tên HTML khác Java không?

### 13.2. Nhầm `items.quantity` với `items[0].quantity`

List chứa nhiều item; `items.quantity` không xác định item nào. Dùng indexed path đúng như `items[0].quantity`, `items[1].quantity`. Nếu container là `Map`, dùng key như `pickupPoints[office].city`.

### 13.3. Container khai báo thiếu generic

`List` (raw type) hoặc `Map` (raw type) làm mất thông tin kiểu element/key/value. Với graph lồng nhau, khai báo `List<LineItem>`, `Map<String, Address>` hoặc `Address[]` để Spring biết cần convert hoặc dựng phần tử loại nào.

### 13.4. Gọi `bind(...)` thay vì `construct(...)`

`binder.bind(new MutablePropertyValues(...))` là property binding trên target, không tái tạo graph bằng constructor ở ví dụ mục 9. Nếu mục tiêu là kiểm chứng recursive constructor binding, dùng `new DataBinder(null, name)`, `setTargetType(...)` và `construct(...)`. Các lần chạy sau đó cần đọc `getBindingResult()` và `getTarget()`.

### 13.5. Tưởng record tự kiểm tra hợp lệ

Record loại bỏ setter và giúp hình thành object bất biến theo tham chiếu field, nhưng không tự áp `@NotBlank`, `@Size`, giới hạn Map key hoặc authorization. Ngoài ra, record chứa `List`, `Map` hoặc array vẫn có thể giữ tham chiếu tới container mutable. Nếu cần bất biến sâu, cân nhắc copy/kiểm soát container và validation trong constructor, đồng thời tránh đưa raw mutable input ra ngoài.

### 13.6. Tưởng nested construction luôn gọi mọi constructor

Dữ liệu con không có key phù hợp có thể được xem là thiếu; không thể dự đoán object nào được tạo nếu chưa biết constructor, resolver, converter và input. Viết test tập trung vào missing fields, nested paths và kiểu container thực dùng trong sản phẩm.

### 13.7. Dùng index lớn mà không giới hạn

Kiểu `items[1000000].sku` có thể dẫn đến cấp phát/parse quá lớn hoặc lỗi. Cần giới hạn ở tầng HTTP và kiểm tra index, số lượng field trước khi khởi tạo; đừng coi giới hạn dành cho property binding là cơ chế bảo vệ chung.

## 14. Bài tập tự kiểm tra

**Bài 1 — Đọc tên đường dẫn.** Cho `record Customer(Address address)`, `record Address(String city)`. Với `customer.address.city=Hue` và constructor của object cha có tham số `customer`, mô tả các object phải dựng.

**Đáp án:** chuẩn bị giá trị `city="Hue"`, dựng `Address("Hue")`, dùng nó dựng `Customer(address)`, sau đó đưa `Customer` vào constructor của object cha. Không cần setter.

**Bài 2 — Phân biệt index với key.** Cho `List<LineItem> items` và `Map<String, Address> stops`. `items[2].sku` khác `stops[2].city` như thế nào?

**Đáp án:** trong `items[2].sku`, 2 biểu thị vị trí thứ ba của List; trong `stops[2].city`, với `Map<String, Address>`, 2 được hiểu là khóa chuỗi `"2"`. Chỉ số/khóa không xác nhận ID nghiệp vụ.

**Bài 3 — Dự đoán conversion.** `record LineItem(String sku, int quantity)`, input `items[0].quantity=abc`. Có thể chắc chắn Spring tạo `LineItem(..., quantity=0)` hợp lệ không?

**Đáp án:** không. `"abc"` không chuyển thành số nguyên; cần kiểm tra lỗi binding/conversion, không dùng target nếu lỗi. Phải xử lý response hợp lệ và tránh lưu dữ liệu.

**Bài 4 — Tìm lỗ hổng hợp đồng.** Một API dùng `record AdminUpdate(String displayName, String role, Map<String,String> metadata)` cho người dùng thường, rồi cập nhật entity từ mọi field. Rủi ro ở đâu?

**Đáp án:** constructor binding vẫn chấp nhận `role` như một input chính thức và có thể nhận key `metadata[privileged]`; dùng DTO chỉ chứa field được phép, whitelist Map keys và kiểm tra authorization ở service.

## Tài liệu chính thức

- [Spring Framework Reference — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): constructor binding qua `DataBinder.construct`, recursive nested object, indexed `List`, `Map` và mảng.
- [Spring MVC — `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): constructor binding theo request, `@BindParam`, `BindingResult`.
- [Spring MVC — Data Binding and model design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): `declarativeBinding`, property binding và nguyên tắc an toàn.
- [Spring Framework Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `construct`, `setTargetType`, `setDeclarativeBinding`, error handling.
- [Spring Framework Javadoc — DataBinder.ValueResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html): `resolveValue` và `getNames`.
