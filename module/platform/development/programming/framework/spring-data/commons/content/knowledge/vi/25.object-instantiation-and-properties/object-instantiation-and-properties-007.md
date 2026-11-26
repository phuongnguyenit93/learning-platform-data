# Truy cập field, accessor và thuộc tính dẫn xuất

Trong chương **Khởi tạo và gán thuộc tính** của **SPRING_DATA_COMMONS**, bài này giải thích cách cơ chế mapping đọc và gán giá trị qua field, getter/setter hoặc accessor của hạ tầng. Từ đó, ta phân biệt được thuộc tính lưu trữ với thuộc tính tính toán, thiết kế đối tượng immutable và tránh phụ thuộc vào setter không được gọi.

Ví dụ xuyên suốt gồm thông tin liên hệ và hàng tồn kho. Một trường cần được giữ nguyên như dữ liệu đã lưu; một trường được xử lý qua setter; một giá trị tổng được tính từ đơn giá và số lượng. Cách truy cập và chính sách lưu của từng thuộc tính phải được chọn có chủ đích.

## 1. Phạm vi của cơ chế mapping

Các quy tắc ở đây áp dụng cho module Spring Data tự triển khai object mapping, chẳng hạn MongoDB hoặc Spring Data Relational. Spring Data JPA giao việc mapping entity cho JPA provider; cần dùng quy tắc và annotation của JPA khi làm việc với entity JPA. Phạm vi này được nêu trong [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html).

Các class Java trong bài minh họa mô hình miền. Chúng chưa bao gồm cấu hình kết nối, repository cụ thể hoặc converter cho một kho dữ liệu. Muốn thực hành đọc/ghi, cần chọn module và bổ sung ánh xạ phù hợp.

Trong các ví dụ:

- `@Id`, `@Transient` và `@AccessType` được import từ `org.springframework.data.annotation`.
- Mỗi class public nằm trong file Java riêng tương ứng.
- Constructor nhận tham số cần có metadata tên tham số phù hợp, chẳng hạn biên dịch với `-parameters`.
- Việc chuyển kiểu dữ liệu từ kho vẫn thuộc trách nhiệm converter của module.

Không suy rằng một cơ chế gán thuộc tính dùng được đồng nghĩa mọi kho hỗ trợ cùng truy vấn, kiểu khóa hoặc chiến lược cập nhật.

## 2. Phân biệt field, property và hai nghĩa của accessor

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Field | Biến thành viên thực sự nằm trong class | `private String displayName` |
| Thuộc tính miền | Một thành phần trạng thái hoặc thông tin của đối tượng | Tên hiển thị của khách hàng |
| Persistent property | Thuộc tính được hạ tầng mapping quản lý bằng metadata | Tên, kiểu, field, getter, setter, chính sách truy cập |
| Java accessor | Phương thức dùng để đọc hoặc thay đổi thuộc tính | `getDisplayName()`, `setDisplayName(...)` |
| Accessor của hạ tầng | Đối tượng trung gian giúp framework truy cập thuộc tính | `PersistentPropertyAccessor<T>` |

Không phải mọi phương thức bắt đầu bằng `get` đều cần trở thành dữ liệu lưu trữ. Ngược lại, một field private không có setter public vẫn có thể được mapper quản lý.

Metadata `PersistentProperty` có thể cung cấp field, getter, setter hoặc wither tương ứng; một số thành phần có thể không tồn tại. Xem [PersistentProperty API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PersistentProperty.html).

Hai câu hỏi cần trả lời riêng:

1. Thuộc tính này có thuộc mô hình persistence không?
2. Nếu có, framework truy cập giá trị qua đường nào?

`@Transient` liên quan câu hỏi thứ nhất. `@AccessType` liên quan câu hỏi thứ hai. Đổi từ field access sang property access không tự loại thuộc tính khỏi dữ liệu lưu.

## 3. Vị trí của việc gán thuộc tính trong quá trình đọc

Mapper trước hết tạo instance qua creator đã chọn. Các thuộc tính còn lại được hoàn thiện sau đó; thuộc tính đã được creator nhận không được mặc định gán lại. Với thuộc tính cần hoàn thiện, cơ chế hỗ trợ wither hoặc bản sao cho immutable, setter khi dùng property access và gán field khi phù hợp. Định danh được ưu tiên nếu chưa được creator nhận. Xem [Property population](https://docs.spring.io/spring-data/commons/reference/object-mapping.html#mapping.property-population).

Có thể hình dung bằng các trách nhiệm:

~~~text
Dữ liệu từ kho
  → chuyển đổi và giải quyết đầu vào cho creator
  → tạo instance
  → hoàn thiện những thuộc tính chưa được creator nhận
  → trả đối tượng sau cùng
~~~

Điều quan trọng là **không có bảo đảm mọi thuộc tính đều đi qua setter**.

Một setter tồn tại trong source không chứng minh mapper sử dụng nó. Ngay cả khi property access được cấu hình, thuộc tính đã có giá trị qua constructor có thể không cần bước gán tiếp theo.

Thứ tự nêu trên cũng không phải hợp đồng để viết setter phụ thuộc tùy ý vào trạng thái của các field khác. Khi setter được gọi trong giai đoạn hoàn thiện, đối tượng có thể chưa đủ mọi thuộc tính còn lại.

## 4. Ví dụ đối chiếu field access và property access

### 4.1. Mô hình có hai đường truy cập

~~~java
package com.acme.mapping;

import org.springframework.data.annotation.AccessType;
import org.springframework.data.annotation.AccessType.Type;
import org.springframework.data.annotation.Id;

public class CustomerContact {

    @Id
    private final String id;

    @AccessType(Type.PROPERTY)
    private String displayName;

    private String email;

    public CustomerContact(String id) {
        this.id = id;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName =
                displayName == null ? null : displayName.strip();
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email == null ? null : email.strip();
    }
}
~~~

Hai setter đều có logic bỏ khoảng trắng ở đầu và cuối. Tuy nhiên, chỉ `displayName` được chỉ định property access.

Theo hợp đồng `@AccessType`, mặc định là field access; có thể chọn `FIELD` hoặc `PROPERTY`. Annotation có thể đặt trên kiểu hoặc thành phần được hỗ trợ. Xem [AccessType API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/AccessType.html).

Ở ví dụ:

- `id` được constructor nhận.
- `displayName` còn cần được hoàn thiện và sử dụng setter theo cấu hình.
- `email` còn cần được hoàn thiện và giữ chính sách field access mặc định.

### 4.2. Giá trị có thể khác nhau dù setter trông giống nhau

Giả sử nguồn dữ liệu cung cấp:

~~~text
id          = "C-14"
displayName = "  Lan  "
email       = "  lan@example.com  "
~~~

Khi được materialize theo cấu hình trên:

| Thuộc tính | Đường nhận giá trị | Giá trị trong đối tượng |
| --- | --- | --- |
| `id` | Constructor | `"C-14"` |
| `displayName` | Setter | `"Lan"` |
| `email` | Field | `"  lan@example.com  "` |

Setter `setEmail` vẫn hữu ích cho lời gọi chủ động của mã ứng dụng, nhưng nó không trở thành đường gán mặc định của mapper chỉ vì tồn tại.

Nếu việc chuẩn hóa email là một bất biến bắt buộc, thiết kế này chưa bảo đảm bất biến cho mọi đường tạo đối tượng. Cần đặt chính sách vào nơi bao phủ đúng các đường vào, hoặc chủ động thống nhất constructor và đường truy cập.

### 4.3. Thêm tham số constructor có thể thay đổi đường xử lý

Xét một biến thể **thay constructor hiện tại** bằng:

~~~java
public CustomerContact(
        String id,
        String displayName,
        String email) {
    this.id = id;
    this.displayName = displayName;
    this.email = email;
}
~~~

Đây là thay thế constructor, không phải yêu cầu thêm một constructor overload vào ví dụ trước.

Nếu constructor này được dùng làm creator, `displayName` đã được nhận và gán ngay tại bước khởi tạo. Không nên kỳ vọng setter sau đó sẽ tự chạy để bỏ khoảng trắng.

Nếu muốn cùng một quy tắc ở cả hai đường, có thể:

- Đưa phép chuẩn hóa thuần túy vào một hàm dùng chung.
- Gọi hàm đó từ constructor và phương thức thay đổi có chủ đích.
- Hoặc xác định rằng persistence phải giữ nguyên dữ liệu, còn chuẩn hóa chỉ xảy ra khi thực hiện nghiệp vụ mới.

Lựa chọn cuối cùng tùy ý nghĩa dữ liệu. Việc đọc dữ liệu cũ rồi tự chuẩn hóa có thể là thay đổi trạng thái ngoài dự kiến.

## 5. Getter cũng có thể tác động tới giá trị được ghi

Property access không chỉ liên quan setter. Khi lấy giá trị của một persistent property theo đường accessor, getter phải phản ánh đúng giá trị mà hợp đồng persistence mong đợi.

Ví dụ một getter dùng cho hiển thị:

~~~java
public String getDisplayName() {
    return "Khách hàng: " + displayName;
}
~~~

Nếu getter này nằm trên một persistent property dùng property access, chuỗi thêm tiền tố có thể trở thành giá trị mapper đọc để ghi. Getter không còn chỉ là việc trình bày thông tin lên giao diện.

Thiết kế rõ hơn là giữ getter trạng thái đơn giản và tách phần hiển thị:

~~~java
public String getDisplayName() {
    return displayName;
}

@org.springframework.data.annotation.Transient
public String getDisplayLabel() {
    return "Khách hàng: " + displayName;
}
~~~

Getter phục vụ mapping nên có ý nghĩa ổn định, chi phí phù hợp và tránh side effect. Không đặt thao tác gửi thông báo, tăng bộ đếm nghiệp vụ hoặc ghi dữ liệu vào getter.

Cũng cần tránh getter âm thầm truy vấn kho dữ liệu. Một thao tác serialize, ghi entity hoặc dựng màn hình danh sách có thể gọi getter nhiều lần, làm chi phí và số lượng truy vấn khó dự đoán.

Logic validation ở setter cũng cần được xem xét tương tự. Nếu setter bắt buộc hai thuộc tính khác đã được gán xong, một lần materialize theo thứ tự khác có thể làm validation thất bại dù bản ghi hoàn chỉnh là hợp lệ.

## 6. Accessor của hạ tầng và đối tượng immutable

Với đối tượng immutable, “gán một thuộc tính” không nhất thiết sửa instance hiện tại. Có thể tạo một instance mới chứa giá trị thay thế.

Ví dụ:

~~~java
package com.acme.mapping;

import org.springframework.data.annotation.Id;

public final class StockEntry {

    @Id
    private final Long id;

    private final String sku;
    private final int quantity;

    public StockEntry(Long id, String sku, int quantity) {
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
    }

    public StockEntry withId(Long id) {
        return new StockEntry(id, this.sku, this.quantity);
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Lời gọi Java thông thường:

~~~java
StockEntry original = new StockEntry(null, "BOOK-01", 3);
StockEntry identified = original.withId(42L);

// original.getId() vẫn là null.
// identified.getId() là 42L.
~~~

Wither phải giữ các thuộc tính không đổi. Nếu `withId` quên truyền `quantity`, việc cập nhật định danh có thể làm mất dữ liệu khác.

`PersistentPropertyAccessor` có thể giữ instance mới sau khi thực hiện thay đổi. Hợp đồng yêu cầu lấy đối tượng hiện hành qua `getBean()`; tham chiếu có thể thay đổi giữa các lần cập nhật. Xem [PersistentPropertyAccessor API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PersistentPropertyAccessor.html).

Ví dụ minh họa ở tầng hạ tầng, với metadata và id property đã được lấy đúng từ cùng mô hình:

~~~java
PersistentPropertyAccessor<StockEntry> accessor =
        metadata.getPropertyAccessor(original);

accessor.setProperty(idProperty, 42L);

StockEntry updated = accessor.getBean();
~~~

Các kiểu `PersistentPropertyAccessor` và metadata thuộc `org.springframework.data.mapping`. Đây là phác thảo sử dụng API metadata, không phải mã service cần viết cho mọi repository.

Ứng dụng gọi repository thường chỉ cần dùng đúng kết quả trả về:

~~~java
StockEntry saved = stockRepository.save(candidate);
~~~

Biến `stockRepository` trong đoạn trên giả định đã được inject với kiểu repository thích hợp. Hợp đồng `CrudRepository.save` yêu cầu tiếp tục sử dụng instance trả về vì thao tác lưu có thể thay instance. Xem [CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

Có wither không có nghĩa kho dữ liệu tự sinh được ID hoặc mọi thao tác đều gọi wither. Chiến lược định danh, khả năng chuyển đổi và đường cập nhật vẫn phụ thuộc module.

## 7. Thuộc tính dẫn xuất tính theo trạng thái hiện tại

Thuộc tính dẫn xuất là giá trị có thể tính từ thông tin khác. Ví dụ giá trị hàng tồn kho:

~~~text
stockValue = unitPrice × quantity
~~~

Nếu chỉ cần giá trị này trong ứng dụng, có thể tính khi gọi getter và không lưu riêng:

~~~java
package com.acme.mapping;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

public final class InventoryItem {

    @Id
    private final String id;

    private final BigDecimal unitPrice;
    private final int quantity;

    public InventoryItem(
            String id,
            BigDecimal unitPrice,
            int quantity) {
        this.id = id;
        this.unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");

        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }

        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must not be negative");
        }

        this.quantity = quantity;
    }

    public String getId() {
        return id;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    @Transient
    public BigDecimal getStockValue() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

Ví dụ sử dụng:

~~~java
InventoryItem item = new InventoryItem(
        "BOOK-01",
        new BigDecimal("125000"),
        3
);

BigDecimal stockValue = item.getStockValue();
// Giá trị số là 375000.
~~~

Ở thiết kế này:

- Nguồn dữ liệu là `unitPrice` và `quantity`.
- Không có field cache `stockValue`.
- Getter thể hiện phép tính thuần túy.
- Annotation nêu rõ giá trị này không thuộc dữ liệu persistence.

Constructor từ chối giá âm và số lượng âm. Điều đó cũng có nghĩa dữ liệu lịch sử vi phạm quy tắc có thể không đọc được; cần xử lý dữ liệu hoặc chính sách tương thích khi đưa mô hình vào hệ thống thực tế.

`@Transient` của Spring Data loại thuộc tính khỏi cơ chế persistence. Nó độc lập với từ khóa `transient` phục vụ Java Serialization. Xem [Transient API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Transient.html).

Không suy rằng annotation này đồng thời ẩn giá trị khỏi JSON, log hoặc giao diện. Mỗi cơ chế có hợp đồng riêng.

## 8. Giá trị dẫn xuất được lưu như một snapshot

Có trường hợp cần lưu kết quả tính toán: làm báo cáo, truy vấn nhanh hoặc giữ kết quả của một quy tắc nghiệp vụ tại thời điểm trước.

Khi đó, giá trị dẫn xuất trở thành một phần trạng thái persistence có chủ đích:

~~~java
package com.acme.mapping;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;

public final class ValuationSnapshot {

    @Id
    private final String id;

    private final BigDecimal unitPrice;
    private final int quantity;
    private final BigDecimal total;

    public ValuationSnapshot(
            String id,
            BigDecimal unitPrice,
            int quantity,
            BigDecimal total) {
        this.id = id;
        this.unitPrice = unitPrice;
        this.quantity = quantity;
        this.total = total;
    }

    public static ValuationSnapshot capture(
            String id,
            BigDecimal unitPrice,
            int quantity) {
        BigDecimal total =
                unitPrice.multiply(BigDecimal.valueOf(quantity));

        return new ValuationSnapshot(
                id,
                unitPrice,
                quantity,
                total
        );
    }

    public String getId() {
        return id;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Factory `capture` thể hiện phép tính khi chụp snapshot mới. Constructor đầy đủ cho phép phục hồi giá trị `total` đã lưu.

Ví dụ cố ý tách hai chính sách:

| Hành động | Chính sách với total |
| --- | --- |
| Chụp snapshot mới | Tính từ dữ liệu đầu vào |
| Đọc snapshot đã lưu | Nhận kết quả đã lưu |
| Đổi công thức nghiệp vụ | Không mặc định viết lại snapshot cũ |

Trong hệ thống thực tế, cần bổ sung validation và xác định snapshot bất biến đến mức nào. Nếu cho phép cập nhật đơn giá hoặc số lượng, phải có chính sách đồng bộ `total`.

Nếu mọi bản ghi phải tuân theo cùng một công thức hiện hành, dữ liệu dư thừa tạo thêm một ràng buộc nhất quán. Các đường ghi như repository, template, bulk update và tác vụ nhập dữ liệu đều cần được xét.

Với tổng tiền có thuế, chiết khấu hoặc quy tắc làm tròn, một phép nhân đơn giản có thể chưa đủ. Cần lưu hoặc xác định các đầu vào và phiên bản quy tắc cần thiết để giải thích snapshot.

## 9. Bẫy: field final được tính trong constructor nhưng vẫn là persistent property

Một thiết kế dễ gây lỗi:

~~~java
package com.acme.mapping;

import java.math.BigDecimal;

public final class BrokenStockTotal {

    private final BigDecimal unitPrice;
    private final int quantity;
    private final BigDecimal total;

    public BrokenStockTotal(BigDecimal unitPrice, int quantity) {
        this.unitPrice = unitPrice;
        this.quantity = quantity;
        this.total =
                unitPrice.multiply(BigDecimal.valueOf(quantity));
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Constructor đã gán `total` theo góc nhìn Java. Tuy nhiên, `total` không có trong danh sách tham số creator và không được loại khỏi persistence.

Mapper không mặc định phân tích phần thân constructor để biết field này đã được tính đúng. Nếu nó cần phục hồi `total` như một persistent property, thiết kế không có setter, wither hoặc tham số tương ứng để thay thế giá trị một cách rõ ràng.

Các hướng sửa phải dựa trên ý nghĩa dữ liệu:

| Ý nghĩa mong muốn | Hướng thiết kế |
| --- | --- |
| Total luôn được tính từ trạng thái hiện tại | Getter tính toán, loại thuộc tính khỏi persistence |
| Total là kết quả cần giữ nguyên từ kho | Đưa total vào creator đầy đủ |
| Total là cache nội bộ không lưu | Loại field cache khỏi persistence và quản lý vòng đời cache |
| Chủ động tính lại dù kho còn giá trị cũ | Thiết kế chính sách phục hồi và migration rõ ràng |

Trong trường hợp đặc biệt, creator có thể nhận tham số của thuộc tính nhưng ứng dụng chủ động tính lại giá trị thay vì sử dụng dữ liệu đã lưu. Đây phải là quyết định tường minh: đối tượng trong bộ nhớ có thể khác dữ liệu mà kho dùng để lọc hoặc sắp xếp.

Không dùng khả năng sửa field final bằng reflection như nền tảng cho thiết kế. Một mô hình có constructor đầy đủ hoặc chính sách không lưu rõ ràng dễ kiểm chứng hơn.

## 10. Giá trị tính toán không tự trở thành khả năng truy vấn

“Thuộc tính dẫn xuất” và “derived query” là hai khái niệm khác nhau:

- Thuộc tính dẫn xuất nói về cách tính giá trị.
- Derived query nói về cách hạ tầng phân tích tên phương thức repository để tạo truy vấn.

Getter `getStockValue()` trong `InventoryItem` là mã Java. Nó không tự trở thành một biểu thức nhân được thực thi trong kho dữ liệu.

Do đó, không tự suy rằng các thao tác sau hoạt động chỉ vì getter tồn tại:

~~~java
// Không phải cam kết được hỗ trợ:
// findByStockValueGreaterThan(...)
// Sort.by("stockValue")
~~~

Tương tự, một thuộc tính không lưu không tự trở thành điều kiện Query by Example trong kho. Cần xem chính xác module hỗ trợ những thuộc tính và phép toán nào.

Nếu muốn lọc hoặc sắp xếp theo giá trị tính toán, các lựa chọn có thể gồm:

- Truy vấn có biểu thức hoặc aggregation mà kho hỗ trợ.
- Cột hoặc field dẫn xuất được lưu và đồng bộ.
- Một read model hoặc projection được thiết kế cho nhu cầu đó.
- Tính trong ứng dụng khi tập dữ liệu nhỏ và phạm vi xử lý cho phép.

Không xem các lựa chọn là tương đương về chi phí và tính đúng đắn. Chẳng hạn, đọc một trang 20 dòng rồi sắp xếp theo getter trong Java chỉ sắp xếp 20 dòng ấy; nó không tạo ra trang đầu tiên có giá trị lớn nhất trong toàn bộ tập kết quả.

Một getter dẫn xuất trong projection có thể hữu ích cho trình bày, nhưng không chứng minh kho đã lọc, tính tổng hoặc sắp xếp theo chính giá trị ấy.

## 11. Không để cache dẫn xuất bị lệch khỏi nguồn

Giả sử mô hình mutable lưu cả ba field:

~~~text
unitPrice
quantity
cachedStockValue
~~~

Nếu chỉ tính cache trong constructor, lời gọi thay đổi quantity sau đó có thể làm cache cũ:

~~~text
Ban đầu: quantity = 2, cachedStockValue = 200
Sau sửa: quantity = 5, cachedStockValue vẫn = 200
~~~

Thêm `@Transient` cho cache chỉ giải quyết chuyện không lưu cache; annotation không tự tính lại cache khi đầu vào thay đổi.

Các lựa chọn thường rõ ràng hơn:

- Tính trực tiếp trong getter nếu chi phí thấp.
- Dùng đối tượng immutable và tạo lại mọi trạng thái liên quan khi thay đổi.
- Gom thay đổi nghiệp vụ vào một phương thức duy trì đầy đủ bất biến.
- Nếu dùng cache, có cơ chế vô hiệu hóa hoặc cập nhật tại mọi đường thay đổi.

Không dựa vào setter để duy trì cache nếu mapper có thể gán trực tiếp field hoặc constructor nhận toàn bộ dữ liệu. Cần kiểm chứng tất cả đường tạo và thay đổi, kể cả đường persistence.

Giá trị phụ thuộc thời gian hiện tại, người dùng hoặc locale còn có vấn đề riêng. Một nhãn hiển thị theo ngôn ngữ không nên được coi là trạng thái persistence ổn định chỉ vì ứng dụng có getter cho nó.

## 12. Chi tiết runtime và giới hạn của abstraction

Accessor của hạ tầng có thể được tối ưu bằng mã sinh ở runtime; việc truy cập field private không nhất thiết đi qua setter public. Quyền truy cập, cấu trúc class và môi trường Java ảnh hưởng đường thực thi.

Không nên đưa tỷ lệ tăng tốc cố định vào quyết định thiết kế của ứng dụng. Nếu mapping là điểm nghẽn thực tế, cần đo trên module, dữ liệu và runtime đang dùng.

Các nguyên tắc thiết kế vẫn giữ nguyên:

- Cung cấp đường phục hồi có đủ dữ liệu cần thiết.
- Giữ field và getter của cùng một persistent property có ý nghĩa nhất quán.
- Dùng annotation đúng namespace và đúng mục đích.
- Không mặc định việc thiếu setter làm thuộc tính không được lưu.
- Không mặc định việc có setter làm setter luôn được gọi.
- Với immutable, giữ và sử dụng instance sau cùng.

Nếu kế thừa làm superclass và subclass có các field cùng tên, cần xem xét xung đột metadata và ý nghĩa dữ liệu. Dùng tên khác nhau thường rõ hơn việc kỳ vọng field hoặc setter của một lớp tự đại diện cho cả hai phần trạng thái.

Một thuộc tính được auditing hoặc kho quản lý cũng cần đường nhận giá trị phù hợp. Đặt annotation auditing lên một field không tự giải quyết mọi giới hạn của constructor, wither và khả năng gán giá trị.

## 13. Kế hoạch kiểm chứng và cách chẩn đoán

Các tình huống dưới đây là kế hoạch cho người học, chưa phải kết quả chạy thử kèm bài:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| CustomerContact dùng cấu hình ban đầu | DisplayName đi qua setter, email giữ đường field |
| Creator nhận displayName trực tiếp | Không dựa vào một lần gọi setter bổ sung |
| Getter dùng property access có biến đổi | Giá trị mapper ghi đúng hợp đồng đã chọn |
| Gọi withId | Các thuộc tính khác được giữ và instance cũ không bị sửa |
| Accessor tạo bản sao | Lấy instance sau cùng qua getBean |
| Getter stockValue không lưu | Dữ liệu ghi không có thuộc tính tính toán này |
| Snapshot lưu total | Đọc lại giữ giá trị total đã lưu |
| Đổi quantity trong mô hình mutable | Không để cache dẫn xuất trở nên lỗi thời |
| Lọc hoặc sắp xếp theo giá trị tính toán | Thực hiện ở đúng tầng và đúng phạm vi dữ liệu |

Cần kiểm tra cả chiều đọc và chiều ghi. Một đối tượng nhìn đúng sau `findById` chưa chứng minh dữ liệu được ghi đúng, nhất là khi getter có biến đổi.

Có thể chẩn đoán theo từng câu hỏi:

1. Thuộc tính có thực sự được đăng ký trong mô hình persistence không?
2. Nó đã được creator nhận chưa?
3. Metadata chọn field hay property access?
4. Nếu immutable, có wither hoặc đường tạo bản sao phù hợp không?
5. Đối tượng được kiểm tra có phải instance sau cùng không?
6. Giá trị sai xuất phát từ dữ liệu lưu, chuyển đổi kiểu hay logic accessor?
7. Nếu là thuộc tính dẫn xuất, hệ thống mong tính lại hay giữ snapshot?

Gọi trực tiếp setter chỉ chứng minh setter chạy đúng. Để xác nhận mapper sử dụng setter, cần materialize qua converter hoặc repository của module đã chọn.

Khi kiểm tra thuộc tính không lưu, hãy quan sát dữ liệu thực sự được ghi bằng cơ chế phù hợp của kho. Không chỉ dựa vào JSON từ API, vì JSON serialization và persistence là hai đường khác nhau.

## 14. Bài thực hành: mô hình dòng hàng

Thiết kế `OrderLine` có `id`, `unitPrice`, `quantity` và một nhãn hiển thị.

Yêu cầu:

1. Chọn rõ field access hoặc property access cho từng thuộc tính lưu.
2. Không phụ thuộc vào setter để thực thi một quy tắc mà creator có thể bỏ qua.
3. Cung cấp `lineTotal` tính theo trạng thái hiện tại và loại nó khỏi persistence.
4. Tạo một mô hình snapshot riêng nếu cần giữ tổng đã chốt theo quy tắc cũ.
5. Với ID immutable, cung cấp đường phục hồi hoặc thay thế giá trị phù hợp và giữ đúng instance trả về.
6. Giải thích cách lọc, sắp xếp toàn bộ tập dữ liệu theo tổng tiền nếu nghiệp vụ yêu cầu.

Dùng một bản ghi có khoảng trắng trong nhãn và một tổng snapshot khác giá trị tính theo công thức hiện tại. Hai dữ kiện này giúp quan sát đúng đường accessor và phát hiện việc vô tình thay đổi ý nghĩa dữ liệu khi đọc lại.
