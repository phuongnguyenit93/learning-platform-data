# @AccessType, @ReadOnlyProperty và ý nghĩa được store áp dụng

## 1. Metadata chung không đồng nghĩa với hành vi lưu trữ giống nhau

Spring Data Commons cung cấp các abstraction và annotation dùng chung cho nhiều module Spring Data. Trong số đó, hai annotation thường xuất hiện khi xây dựng mô hình ánh xạ là:

```java
import org.springframework.data.annotation.AccessType;
import org.springframework.data.annotation.ReadOnlyProperty;
```

Chúng trả lời hai câu hỏi khác nhau:

- `@AccessType`: hạ tầng ánh xạ truy cập giá trị thuộc tính bằng field hay bằng accessor?
- `@ReadOnlyProperty`: thuộc tính có được đưa vào quá trình ghi dữ liệu do mapper hỗ trợ annotation này thực hiện hay không?

Commons mô tả metadata. Module kho dữ liệu, mapping converter và đường thực thi cụ thể quyết định metadata đó ảnh hưởng thế nào đến thao tác lưu trữ.

Ví dụ, việc bỏ một thuộc tính khỏi câu SQL `UPDATE` và việc bỏ một field khỏi document dùng để thay thế toàn bộ bản ghi có thể dẫn đến kết quả rất khác nhau. Không thể chỉ nhìn tên annotation để kết luận dữ liệu cũ trong store chắc chắn được giữ nguyên.

Mục tiêu của bài là đọc đúng metadata, chọn đúng cơ chế truy cập và kiểm tra tác động trên store đang dùng.

## 2. Hai chiều ánh xạ và hai loại “đọc”

Trước hết cần xác định chiều dữ liệu:

```text
Chiều nạp:
Store → giá trị được giải mã → constructor/property accessor → object

Chiều lưu:
Object → mapper lấy giá trị → bản ghi/document/câu lệnh → Store
```

Từ “đọc” dễ gây nhầm vì có thể chỉ:

1. Đọc một bản ghi từ database để tạo object.
2. Đọc giá trị từ object để chuẩn bị ghi vào database.

Trong bài:

- **Nạp từ store** là chiều database → object.
- **Ghi xuống store** là chiều object → database.
- **Field access** và **property access** là cách mapper làm việc với object Java, không phải cách database đọc ổ đĩa hoặc sử dụng index.

Một field được đánh dấu `@ReadOnlyProperty` vẫn có thể được nạp từ store. Annotation này không mang nghĩa “mapper không được phép gán giá trị vào field Java”.

## 3. @AccessType: chọn field access hoặc property access

### 3.1. Hai kiểu truy cập

```java
@AccessType(AccessType.Type.FIELD)
```

Với field access, mapper làm việc trực tiếp với field theo cơ chế accessor mà hạ tầng mapping sử dụng.

```java
@AccessType(AccessType.Type.PROPERTY)
```

Với property access, mapper sử dụng accessor của thuộc tính, chẳng hạn getter và setter phù hợp, trong những bước cần truy cập thuộc tính.

| Câu hỏi | Field access | Property access |
| --- | --- | --- |
| Lấy giá trị object khi ghi xuống store | Lấy từ field | Gọi getter phù hợp |
| Gán thuộc tính sau khi tạo object | Gán field nếu thuộc tính cho phép | Gọi setter hoặc cơ chế accessor phù hợp |
| Logic trong setter có nhất thiết chạy không? | Không nên kỳ vọng | Có thể chạy khi mapper thực hiện bước population qua setter |
| Logic trong getter có thể ảnh hưởng dữ liệu được lưu không? | Getter không quyết định giá trị của field access | Có, nếu mapper lấy giá trị qua getter đó |
| Có tự thay đổi tên cột hoặc field trong store không? | Không | Không |

Trong mô hình mapping của Commons, field access thường là lựa chọn mặc định. Cần kiểm tra cấu hình và module thực tế nếu mô hình có annotation khác, thuộc tính kế thừa hoặc accessor đặc biệt.

Không nên hiểu “trực tiếp” là bắt buộc dùng một lệnh reflection nhất định. Framework có thể tạo accessor tối ưu hoặc dùng cơ chế khác để thực hiện cùng ngữ nghĩa truy cập.

### 3.2. Ví dụ field access

```java
import org.springframework.data.annotation.AccessType;

import java.util.Locale;

@AccessType(AccessType.Type.FIELD)
public class ProductCode {

    private String sku;

    public ProductCode() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = normalize(sku);
    }

    private static String normalize(String value) {
        if (value == null) {
            throw new IllegalArgumentException("sku must not be null");
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
```

Nếu mapper khởi tạo object bằng constructor không tham số rồi gán `sku` bằng field access, logic `normalize` trong setter không phải một bước bắt buộc của quá trình nạp.

Giả sử store có giá trị `" ab-10 "`. Object có thể nhận chính giá trị này qua field, mặc dù lời gọi `setSku(" ab-10 ")` từ code ứng dụng sẽ tạo ra `"AB-10"`.

Đây là lý do không nên đặt một invariant bắt buộc của domain chỉ trong setter rồi mặc định mọi đường nạp dữ liệu đều đi qua setter đó.

### 3.3. Override cho một thuộc tính

Giữ nguyên class ở trên và thay khai báo field bằng:

```java
@AccessType(AccessType.Type.PROPERTY)
private String sku;
```

Annotation trên thuộc tính cho phép thay đổi lựa chọn truy cập của thuộc tính đó so với lựa chọn chung trên class, khi mapper sử dụng metadata này.

Với constructor không tham số và cặp accessor thích hợp, bước population qua setter sẽ chuẩn hóa giá trị:

```text
Giá trị từ store: " ab-10 "
    → setSku(...)
    → Giá trị trong object: "AB-10"
```

Khi ghi, getter trả lại `"AB-10"`. Một lần nạp rồi lưu có thể vì vậy biến đổi dữ liệu, ngay cả khi code nghiệp vụ không chủ động sửa SKU.

Sự biến đổi này có thể là chủ đích, nhưng phải được thiết kế và kiểm chứng. Không nên dùng setter ánh xạ để âm thầm “sửa” dữ liệu lịch sử nếu ứng dụng cần giữ nguyên giá trị gốc.

### 3.4. Chú ý getter có tính toán hoặc tác dụng phụ

Getter dùng cho property access nên có hành vi dễ dự đoán:

```java
public String getSku() {
    return sku;
}
```

Một getter vừa đọc vừa thay đổi trạng thái có thể gây khó đoán khi mapper gọi nhiều lần:

```java
// Tránh dùng làm accessor ánh xạ.
public String getSku() {
    this.sku = this.sku + "-READ";
    return this.sku;
}
```

Getter trả về chuỗi định dạng hiển thị cũng có thể làm dữ liệu lưu khác dữ liệu domain mong muốn. Ví dụ, getter trả giá tiền kèm ký hiệu tiền tệ không thích hợp làm accessor của một thuộc tính numeric.

Nếu cần giá trị chỉ để hiển thị, hãy tách khỏi thuộc tính persistent hoặc đánh dấu không tham gia mapping bằng cơ chế phù hợp, thay vì thay đổi ngữ nghĩa getter của thuộc tính đang lưu.

## 4. @AccessType không thay thế chiến lược tạo object

Quá trình nạp entity thường có hai bước cần phân biệt:

1. Chọn constructor hoặc factory phù hợp để tạo instance.
2. Population các thuộc tính còn lại, nếu cần.

Một giá trị được truyền trực tiếp vào persistence constructor không bắt buộc phải đi qua setter, kể cả khi có accessor cho thuộc tính đó.

Với object immutable, framework có thể phải tạo instance mới, dùng constructor hoặc wither theo khả năng mapping của module. Chỉ thêm `@AccessType(PROPERTY)` không tự sinh setter và không làm một thuộc tính immutable trở thành mutable.

Do đó, khi phân tích hành vi hãy đặt các câu hỏi:

- Mapper đã chọn constructor hoặc factory nào?
- Thuộc tính nào được cung cấp ngay trong bước tạo object?
- Thuộc tính nào còn cần population?
- Field, setter hoặc wither có đáp ứng yêu cầu của đường population đó không?

Ví dụ `ProductCode` ở phần trước cố ý có constructor không tham số và field có thể thay đổi để làm rõ sự khác biệt giữa field access và setter access. Không nên áp dụng nguyên xi kết luận “setter chắc chắn được gọi” cho mọi record hoặc entity immutable.

Một constructor bảo vệ invariant có thể hữu ích cho domain, nhưng việc lựa chọn persistence constructor và khả năng tái tạo object vẫn cần phù hợp module đang dùng.

## 5. @ReadOnlyProperty: nạp được, bỏ khỏi chiều ghi do mapper quản lý

Khai báo:

```java
@ReadOnlyProperty
private java.math.BigDecimal lineTotal;
```

Ý nghĩa dự kiến trong một mapping implementation hỗ trợ annotation:

- Thuộc tính vẫn là một phần của mô hình ánh xạ để có thể nhận giá trị đọc từ store.
- Mapper không sử dụng thuộc tính này như một thuộc tính cần ghi xuống store.
- Việc sửa giá trị trong object không tạo nghĩa vụ cho mapper ghi nó vào database.

Đây là lựa chọn phù hợp cho những thuộc tính do database hoặc một tiến trình khác quản lý, nếu store và đường ghi cụ thể áp dụng đúng ngữ nghĩa cần thiết.

### 5.1. Điều annotation không tự cung cấp

`@ReadOnlyProperty` không tự:

- Tạo generated column, default value hoặc trigger.
- Tính giá trị sau mỗi lần gọi setter.
- Gọi lại database để lấy giá trị vừa được sinh.
- Biến field Java thành `final`.
- Chặn code ứng dụng gọi setter.
- Ngăn một câu SQL thủ công hoặc native client sửa dữ liệu.
- Thiết lập quyền truy cập database.
- Bảo đảm field cũ được giữ nguyên khi thao tác lưu thay thế cả document.

Nếu database không có giá trị để trả về hoặc truy vấn không chọn cột tương ứng, annotation không tự tạo ra một giá trị có ý nghĩa.

### 5.2. So sánh với các khái niệm gần giống

| Khai báo hoặc cơ chế | Nội dung chính | Có thay thế trực tiếp @ReadOnlyProperty không? |
| --- | --- | --- |
| `@ReadOnlyProperty` của Spring Data | Loại thuộc tính khỏi chiều ghi do mapper hỗ trợ quản lý, vẫn có thể nạp từ store | Đây là ngữ nghĩa đang xét |
| `@Transient` của Spring Data | Loại thuộc tính khỏi mapping thông thường | Không; thường cũng không nạp thuộc tính đó từ dữ liệu persistent |
| Field `final` | Ràng buộc gán giá trị của Java | Không; field final vẫn có thể là một thuộc tính persistent |
| Không có public setter | Hạn chế API sửa đổi từ code gọi | Không; field access hoặc constructor mapping vẫn có thể dùng thuộc tính |
| `@Transactional(readOnly = true)` | Thuộc tính của transaction theo transaction manager và hạ tầng sử dụng | Không; không phải mapping annotation của một field |
| `@Column(insertable = false, updatable = false)` của JPA | Cấu hình ghi cột do JPA provider quản lý | Là cơ chế JPA riêng, không phải annotation Commons có thể thay thế tùy ý |
| Quyền chỉ đọc trong database | Hạn chế thao tác của tài khoản ở phía database | Không; đây là cơ chế thực thi quyền của store |

Đặc biệt, không ghép `@Transient` với `@ReadOnlyProperty` rồi mong nhận được một field “được đọc nhưng không ghi”. Nếu thuộc tính đã bị loại khỏi mapping, mục tiêu nạp nó từ store cũng có thể không còn được đáp ứng.

## 6. Kết hợp hai annotation: hai trục độc lập

Ví dụ:

```java
@AccessType(AccessType.Type.PROPERTY)
@ReadOnlyProperty
private java.time.Instant generatedAt;
```

Có thể đọc metadata như sau:

1. Khi cần làm việc với thuộc tính theo cơ chế accessor, dùng property access.
2. Khi mapper quyết định các thuộc tính tham gia ghi, thuộc tính này bị loại khỏi chiều ghi nếu module hỗ trợ `@ReadOnlyProperty`.
3. Khi nạp giá trị từ store, mapper vẫn có thể cần constructor hoặc setter phù hợp để đưa giá trị vào object.

| Access type | Read-only | Khi mapper chuẩn bị ghi thuộc tính | Khi mapper nạp thuộc tính |
| --- | --- | --- | --- |
| FIELD | Không | Có thể lấy giá trị từ field | Có thể gán field hoặc cấp cho bước tạo object |
| PROPERTY | Không | Có thể lấy giá trị qua getter | Có thể population qua setter hoặc cấp cho bước tạo object |
| FIELD | Có | Bỏ khỏi chiều ghi của mapper hỗ trợ | Vẫn có thể nạp và gán field |
| PROPERTY | Có | Bỏ khỏi chiều ghi của mapper hỗ trợ | Vẫn cần đường nạp tương thích với mô hình object |

Bảng mô tả ý nghĩa metadata, không phải cam kết về thứ tự gọi từng method nội bộ. Một mapper có thể kiểm tra metadata trước rồi không cần gọi getter của thuộc tính đã bị loại khỏi chiều ghi.

Nếu thuộc tính chỉ có getter, không có field có thể gán, không có setter và cũng không được constructor nhận, việc đọc nó từ store có thể không có đường population hợp lệ. `@ReadOnlyProperty` không sửa được thiết kế object thiếu đường khởi tạo đó.

## 7. Ví dụ Spring Data JDBC: cột tổng tiền do database tính

### 7.1. Lược đồ dữ liệu

Giả sử dùng PostgreSQL với bảng sau:

```sql
CREATE TABLE invoice_line (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity integer NOT NULL,
    unit_price numeric(12, 2) NOT NULL,
    line_total numeric(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
```

SQL này dùng cú pháp generated column của PostgreSQL; database khác có thể yêu cầu DDL khác.

Database chịu trách nhiệm tính `line_total`. Ứng dụng ghi số lượng và đơn giá, rồi đọc tổng tiền đã được database tính.

### 7.2. Entity

```java
import org.springframework.data.annotation.AccessType;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.relational.core.mapping.Table;

import java.math.BigDecimal;

@Table("invoice_line")
@AccessType(AccessType.Type.FIELD)
public class InvoiceLine {

    @Id
    private Long id;

    private int quantity;

    private BigDecimal unitPrice;

    @ReadOnlyProperty
    private BigDecimal lineTotal;

    public InvoiceLine() {
    }

    public Long getId() {
        return id;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public BigDecimal getLineTotal() {
        return lineTotal;
    }

    public void setLineTotal(BigDecimal lineTotal) {
        this.lineTotal = lineTotal;
    }
}
```

Ví dụ giả định naming strategy ánh xạ `unitPrice` thành `unit_price` và `lineTotal` thành `line_total`. Nếu ứng dụng có naming strategy khác, cần khai báo tên cột tường minh bằng annotation relational phù hợp.

Setter `setLineTotal` được giữ lại để cho thấy read-only mapping không có nghĩa object Java bất biến. Trong thiết kế domain thực tế, có thể hạn chế API setter nếu không muốn code nghiệp vụ tự sửa giá trị này.

### 7.3. Repository và luồng ghi–đọc

```java
import org.springframework.data.repository.CrudRepository;

public interface InvoiceLineRepository
        extends CrudRepository<InvoiceLine, Long> {
}
```

Đoạn sử dụng, giả định repository đã được Spring Data JDBC cấu hình:

```java
InvoiceLine draft = new InvoiceLine();
draft.setQuantity(4);
draft.setUnitPrice(new java.math.BigDecimal("25.00"));

// Có thể sửa object, nhưng giá trị này không phải nguồn ghi của mapper.
draft.setLineTotal(new java.math.BigDecimal("999.00"));

InvoiceLine saved = repository.save(draft);

InvoiceLine reloaded = repository.findById(saved.getId())
        .orElseThrow(() -> new IllegalStateException("Invoice line not found"));

System.out.println(reloaded.getLineTotal()); // Giá trị số tương ứng 100.00
```

Trong đường ghi JDBC hỗ trợ `@ReadOnlyProperty`, hình dung SQL được rút gọn như sau:

```sql
INSERT INTO invoice_line (quantity, unit_price)
VALUES (?, ?);

UPDATE invoice_line
SET quantity = ?, unit_price = ?
WHERE id = ?;
```

`line_total` không phải cột được ứng dụng gán qua mapper. Database tự tính nó dựa trên `quantity` và `unit_price`.

SQL thực tế có thể khác về quoting, thứ tự cột và cách lấy khóa sinh tự động. Mục tiêu cần kiểm tra là cột read-only không xuất hiện ở vị trí gán giá trị trong câu ghi.

### 7.4. Vì sao cần nạp lại?

Không giả định `save` tự refresh mọi thuộc tính do database sinh. Việc framework cập nhật generated ID cho object không chứng minh rằng các cột tính toán khác cũng đã được nạp lại.

Trong ví dụ:

- Object trước khi lưu đang chứa `lineTotal = 999.00`.
- Database có thể đang chứa tổng tiền `100.00`.
- Nếu đường ghi không reload cột này, object trả về từ `save` có thể vẫn chưa phản ánh giá trị database.
- Lời gọi `findById` tường minh giúp đọc lại giá trị authoritative.

Khi thiết kế service, phải quyết định response cần giá trị từ object hiện có hay giá trị mới nhất từ database. Nếu phải reload, tính thêm chi phí truy vấn và yêu cầu nhất quán trong transaction phù hợp.

Không dùng `@ReadOnlyProperty` để thay thế toàn bộ cơ chế nhận generated value chuyên biệt mà phiên bản hoặc store có thể cung cấp.

## 8. Store quyết định annotation tác động đến thao tác nào

### 8.1. JDBC và R2DBC: kiểm tra cột được ghi và cột được chọn

Trong các đường mapping relational hỗ trợ annotation, một use case điển hình của `@ReadOnlyProperty` là đọc cột do database quản lý nhưng loại cột đó khỏi thao tác ghi do mapper sinh.

Tuy nhiên, cần kiểm tra riêng:

- `INSERT` và `UPDATE` do repository hoặc template sinh.
- Custom query và projection có trả về cột đó hay không.
- Cách nhận generated value sau ghi.
- Các converter hoặc callback tùy biến trong ứng dụng.

Nếu một custom query chỉ chọn `id`, `quantity` và `unit_price`, không nên kỳ vọng mapper tự có thêm `line_total` để gán. Tác động khi thiếu cột còn phụ thuộc loại kết quả và cách khởi tạo object.

R2DBC sử dụng mô hình thực thi reactive. Việc hai module cùng dùng annotation không làm cho một ví dụ JDBC blocking trở thành ví dụ R2DBC có thể sao chép nguyên trạng.

### 8.2. MongoDB: bỏ field khi ghi khác với bảo toàn field trong document

Một mapping converter hỗ trợ `@ReadOnlyProperty` có thể bỏ thuộc tính khỏi document được tạo từ object. Điều quan trọng tiếp theo là thao tác lưu dùng document đó theo cách nào.

Giả sử document hiện tại:

```json
{
  "_id": "p-1",
  "name": "Notebook",
  "externalScore": 87
}
```

Model ánh xạ `externalScore` như read-only. Document chuẩn bị ghi có thể chỉ còn:

```json
{
  "_id": "p-1",
  "name": "Notebook Pro"
}
```

Nếu thao tác cuối cùng **thay thế toàn bộ document**, field không có trong document thay thế có thể bị mất khỏi bản ghi lưu trữ. Nếu thao tác chỉ cập nhật `name` bằng update có chọn lọc, `externalScore` có thể được giữ nguyên.

Vì vậy:

```text
Không đưa field vào document ghi
    ≠
Bảo đảm field cũ trong database được giữ nguyên
```

Với nghiệp vụ cần bảo vệ field do hệ thống ngoài quản lý, phải xem rõ repository/template đang dùng replacement hay update chọn lọc. Không áp dụng suy luận từ `UPDATE` của JDBC cho mọi thao tác `save` document.

### 8.3. JPA: provider quản lý entity mapping

Spring Data JPA sử dụng JPA provider để quản lý phần lớn ánh xạ entity và persistence context.

Đối với entity JPA, cần sử dụng cơ chế mapping của provider, chẳng hạn:

- `jakarta.persistence.Access` để chọn field access hoặc property access trong môi trường dùng Jakarta Persistence.
- `jakarta.persistence.Column(insertable = false, updatable = false)` khi cần cấu hình không ghi một cột.
- Cơ chế generated value hoặc refresh phù hợp provider để đọc giá trị database sinh.

Ứng dụng dùng dòng JPA cũ có thể sử dụng namespace `javax.persistence`; phải theo bộ dependency thực tế.

Không thay `@Access` của JPA bằng `@AccessType` của Commons rồi mặc định Hibernate hoặc provider khác sẽ thay đổi chiến lược truy cập entity. Tương tự, không dùng `@ReadOnlyProperty` như một cam kết tương đương với cấu hình cột JPA.

Cũng cần tránh nhầm `org.springframework.data.annotation.Transient` với annotation transient của JPA khi đang cấu hình entity do provider quản lý.

### 8.4. Các store và đường thao tác khác

Với Cassandra, Redis, Elasticsearch hoặc module khác, hãy kiểm tra mapping implementation của chính module và phiên bản đang dùng. Các câu hỏi quan trọng vẫn giống nhau:

1. Converter có sử dụng metadata Commons này không?
2. Đường đọc và đường ghi có cùng đi qua converter đó không?
3. Thao tác ghi là update một phần, upsert hay replacement?
4. Field bị bỏ qua có được store giữ nguyên, đặt mặc định hoặc xóa bỏ?
5. Query tùy biến, bulk operation hoặc native client có đi qua cùng cơ chế mapping không?

Tên `save` trên repository là abstraction thao tác, không mô tả đầy đủ câu lệnh hoặc giao thức thực thi ở mọi store.

## 9. Không suy rộng sang CRUD, derived query, projection và auditing

### 9.1. CRUD và custom write

Một thuộc tính read-only vẫn có thể là metadata persistent để phục vụ chiều nạp. Điều đó không có nghĩa mọi đường ghi đều bị cấm sửa nó.

Ví dụ, một câu SQL thủ công:

```sql
UPDATE some_table
SET externally_managed_value = ?
WHERE id = ?;
```

không tự bị vô hiệu hóa chỉ vì entity Java đánh dấu field tương ứng bằng `@ReadOnlyProperty`. Database có thể từ chối vì ràng buộc riêng, nhưng đó là một tầng thực thi khác.

Cần áp dụng cùng nguyên tắc với native client hoặc lệnh update xây dựng thủ công: xác định phần nào đi qua mapping converter và phần nào do code tự chỉ định.

### 9.2. Derived query

`@AccessType` không đổi tên thuộc tính mà cơ chế phân tích tên method nhìn thấy. Nó cũng không tự đổi `findBySku` thành truy vấn theo một tên cột khác.

`@ReadOnlyProperty` không có nghĩa thuộc tính bị cấm dùng làm điều kiện tìm kiếm. Khả năng truy vấn vẫn phụ thuộc thuộc tính, tên ánh xạ, kiểu dữ liệu và khả năng store.

Annotation không tự tạo index, không khiến truy vấn theo generated column nhanh hơn và không thêm sự hỗ trợ cho một toán tử mà store chưa có.

### 9.3. Projection

Projection có thể chỉ chọn một phần dữ liệu. Thuộc tính read-only chỉ có thể nhận giá trị nếu dữ liệu kết quả và đường mapping cung cấp được giá trị đó.

Ví dụ, projection chỉ chứa `id` và `quantity` không trở thành projection có `lineTotal` nhờ annotation trên entity gốc.

Cũng cần phân biệt interface projection được dựng từ dữ liệu kết quả với entity được nạp đầy đủ. Không dùng việc một getter projection trả giá trị làm bằng chứng rằng setter của entity đã chạy.

### 9.4. Auditing

Annotation auditing như `@CreatedDate` hoặc `@LastModifiedDate` mô tả metadata phục vụ hạ tầng auditing khi đã được bật và được module hỗ trợ.

Nếu auditing phía ứng dụng gán thời gian vào object nhưng cùng thuộc tính lại bị loại khỏi chiều ghi bởi `@ReadOnlyProperty`, giá trị vừa gán có thể không được lưu qua mapper.

Cần chọn rõ nguồn quản lý:

- Auditing ứng dụng gán và mapper ghi xuống store.
- Database hoặc hệ thống khác quản lý, ứng dụng đọc lại.
- Một thiết kế phối hợp có quy tắc cụ thể và kiểm chứng được.

Không chồng annotation rồi kỳ vọng framework tự suy ra thứ tự ưu tiên nghiệp vụ giữa các nguồn cập nhật.

## 10. Quan sát metadata trước, xác minh thao tác thực tế sau

Khi chẩn đoán, có thể quan sát `PersistentEntity` và `PersistentProperty` do mapping context của store cung cấp.

Ví dụ helper dùng abstraction Commons:

```java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;

public final class MappingMetadataPrinter {

    private MappingMetadataPrinter() {
    }

    public static <T, P extends PersistentProperty<P>> void printProperty(
            PersistentEntity<T, P> entity,
            String propertyName) {

        P property = entity.getPersistentProperty(propertyName);

        if (property == null) {
            throw new IllegalArgumentException(
                    "No mapped property: " + propertyName);
        }

        System.out.println(
                "usePropertyAccess=" + property.usePropertyAccess());
        System.out.println(
                "isWritable=" + property.isWritable());
        System.out.println(
                "isTransient=" + property.isTransient());
    }
}
```

Đầu vào `entity` cần lấy từ mapping context được converter hoặc module store thực tế sử dụng. Không tạo một context tùy ý rồi dùng kết quả của nó để kết luận về mapper khác trong ứng dụng.

Với metadata dự kiến cho `lineTotal` trong ví dụ JDBC:

```text
usePropertyAccess=false
isWritable=false
isTransient=false
```

Kết quả giúp giải thích cách framework nhìn thuộc tính. Nhưng metadata đúng chưa chứng minh câu SQL, document replacement hoặc custom query đã có hành vi mong muốn.

Cần quan sát thêm đầu ra converter, câu lệnh thực thi hoặc dữ liệu đọc lại từ store. Đặc biệt, `isWritable=false` không có nghĩa tài khoản database không có quyền ghi cột đó.

## 11. Kịch bản kiểm chứng có ý nghĩa

### 11.1. Kiểm tra field access và property access

Dùng giá trị store cố ý chưa chuẩn hóa, ví dụ `" ab-10 "`.

Với mô hình mutable và constructor không tham số:

1. Nạp bằng cấu hình field access, ghi nhận giá trị trong object.
2. Chuyển thuộc tính sang property access có setter chuẩn hóa.
3. Nạp lại cùng dữ liệu và so sánh.
4. Ghi object rồi quan sát giá trị thực sự được gửi xuống store.

Bài kiểm chứng phải xác định được mapper có đi qua setter hay không. Chỉ gọi `setSku` từ test rồi kiểm tra kết quả không xác minh được đường mapping.

Không dùng một counter chưa được loại khỏi mapping để đếm số lần gọi setter trong entity, vì counter đó có thể tự trở thành thuộc tính persistent. Nếu cần đo lời gọi, chọn một kỹ thuật quan sát không làm thay đổi mô hình dữ liệu.

### 11.2. Kiểm tra read-only với generated column

Trên bảng `invoice_line`:

1. Tạo object với số lượng `4`, đơn giá `25.00`, tổng tiền giả `999.00`.
2. Gọi `save`.
3. Xác nhận câu ghi không gán `line_total`.
4. Đọc lại và kiểm tra tổng tiền bằng giá trị số `100.00`.
5. Đổi số lượng thành `5`, giữ đơn giá, lưu rồi đọc lại.
6. Kiểm tra tổng tiền bằng giá trị số `125.00`.
7. Phân biệt trạng thái object ngay sau `save` với trạng thái object sau reload.

Khi so sánh `BigDecimal`, chú ý scale nếu phép kiểm tra cần so sánh giá trị số. `100.0` và `100.00` có thể khác nhau theo `equals` dù tương đương về giá trị số.

### 11.3. Kiểm tra bảo toàn field trong store document

Chuẩn bị document có field do hệ thống ngoài quản lý:

1. Đọc document thành object.
2. Đổi một field ứng dụng được phép quản lý.
3. Lưu qua đúng API ứng dụng dự định sử dụng.
4. Đọc raw document từ store.
5. Kiểm tra field ngoài có còn tồn tại và giữ nguyên không.
6. So sánh với đường update có chọn lọc nếu thao tác trước dùng replacement.

Kịch bản này kiểm tra yêu cầu nghiệp vụ “bảo toàn field”, thay vì chỉ kiểm tra “converter không đưa field vào document”.

## 12. Lỗi thường gặp và cách định hướng xử lý

| Biểu hiện | Khả năng cần xem xét | Hướng xử lý |
| --- | --- | --- |
| Setter không chạy khi nạp entity | Field access hoặc constructor mapping | Kiểm tra access type và chiến lược tạo object |
| Giá trị bị trim hoặc đổi chữ hoa sau khi đọc rồi lưu | Setter/getter trong property access biến đổi dữ liệu | Tách chuyển đổi nghiệp vụ khỏi accessor hoặc xác nhận đây là chủ đích |
| Field read-only luôn `null` khi nạp | Query thiếu dữ liệu, tên cột sai hoặc không có đường population | Kiểm tra kết quả query, metadata và constructor/accessor |
| Giá trị database sinh chưa có ngay sau `save` | Đường ghi chưa reload generated property | Reload tường minh hoặc dùng cơ chế nhận generated value được store hỗ trợ |
| Database báo không được gán generated column | Thuộc tính chưa bị loại khỏi đường ghi thực tế | Kiểm tra import annotation, mapper và câu ghi |
| Thêm annotation Commons nhưng entity JPA không đổi hành vi | JPA provider dùng cơ chế mapping riêng | Sử dụng cấu hình JPA tương ứng và xác minh provider |
| Document mất field chỉ đọc sau khi lưu | Document replacement bỏ field khỏi dữ liệu thay thế | Chọn đường update phù hợp với yêu cầu bảo toàn field |
| Auditing cập nhật object nhưng dữ liệu không được lưu | Thuộc tính bị loại khỏi chiều ghi | Chọn lại nguồn quản lý và mapping của thuộc tính |
| Field final vẫn xuất hiện trong dữ liệu ghi | `final` không đồng nghĩa read-only mapping | Dùng metadata đúng với mục tiêu và store |
| Custom update vẫn sửa field read-only | Đường ghi tự chỉ định không bị annotation ràng buộc toàn bộ | Điều chỉnh custom write và ràng buộc store theo yêu cầu nghiệp vụ |

Khi điều tra, luôn ghi rõ phiên bản Commons, module store, loại entity và API thao tác được gọi. Không nâng annotation thành một cam kết toàn hệ thống khi mới kiểm tra một converter.

## 13. Bài thực hành tổng hợp

Thiết kế một mô hình sản phẩm có:

- `sku`: cần quyết định có chuẩn hóa khi nạp hay không.
- `unitPrice`: ứng dụng quản lý.
- `lastCalculatedAt`: database hoặc hệ thống ngoài quản lý.
- Một thuộc tính chỉ dùng hiển thị, không persistent.

Thực hiện:

1. Chọn store và mô tả đường đọc–ghi thực tế.
2. Quyết định field access hay property access cho `sku`, giải thích ảnh hưởng lên dữ liệu lịch sử.
3. Ánh xạ thuộc tính do store quản lý bằng cơ chế được module hỗ trợ.
4. Loại thuộc tính hiển thị khỏi mapping thông thường.
5. Chứng minh dữ liệu từ store được nạp vào đúng thuộc tính.
6. Chứng minh thao tác ghi không gửi giá trị do ứng dụng tự gán cho thuộc tính read-only.
7. Kiểm tra riêng việc giá trị cũ có được bảo toàn trong store.
8. Xác định có cần reload sau ghi để trả response chính xác hay không.

Kết quả đạt yêu cầu khi giải thích được cả ba lớp: metadata Commons mô tả gì, mapper của store thực hiện gì, và database hoặc hệ thống lưu trữ cuối cùng bảo đảm điều gì.

`@AccessType` lựa chọn cách mapper truy cập object. `@ReadOnlyProperty` mô tả một thuộc tính được nạp nhưng loại khỏi chiều ghi trong mapping hỗ trợ annotation. Hành vi cuối cùng phải được đánh giá trên constructor/accessor, converter và thao tác cụ thể của store.
