# Nullability, giá trị mặc định và dữ liệu không đủ để dựng entity

Một truy vấn có thể chạy thành công ở kho dữ liệu nhưng vẫn không tạo được entity hợp lệ. Dòng dữ liệu đã tồn tại, document đã được đọc, song constructor cần một giá trị mà kết quả không cung cấp, hoặc giá trị nhận được là `null` trong khi domain không cho phép.

Bài học thuộc chương **Khởi tạo và gán thuộc tính** của **Spring Data Commons**. Trọng tâm là hợp đồng giữa dữ liệu nguồn, cơ chế mapping và object được tạo. Các ví dụ liên hệ với CRUD, projection và auditing, đồng thời phân biệt abstraction của Commons với hành vi cụ thể của từng module lưu trữ.

Sau bài học, bạn có thể xác định một giá trị thiếu có hợp lệ không, chọn đúng nơi áp dụng mặc định và tránh dựng một entity có vẻ đầy đủ từ dữ liệu thực tế chỉ là một phần.

## 1. Phân biệt bốn tình huống trước khi sửa constructor

Bốn trạng thái sau không có cùng ý nghĩa:

| Trạng thái | Ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| Không tìm thấy bản ghi | Không có dòng hoặc document mang ID cần tìm | API biểu diễn việc không có kết quả như thế nào? |
| Có bản ghi nhưng thiếu thuộc tính trong dữ liệu được đọc | Query chỉ chọn `id`, `sku`, bỏ `quantity` | Có đang dùng kết quả từng phần để dựng entity đầy đủ không? |
| Có thuộc tính nhưng giá trị là `null` | Document có `quantity: null` hoặc cột SQL chứa `NULL` | Domain có cho phép chưa biết số lượng không? |
| Có giá trị cụ thể | `quantity = 0`, `description = ""` | Giá trị đó hợp lệ theo nghiệp vụ hay không? |

Ở SQL, một cột không nằm trong tập kết quả khác với một cột được chọn và có giá trị `NULL`. Ở document store, một field không tồn tại khác với field tồn tại và mang giá trị null. Tuy vậy, adapter và converter có thể chuyển các trạng thái nguồn khác nhau thành cùng một giá trị Java hoặc xử lý chúng theo những quy tắc riêng.

Vì thế, không suy ra rằng constructor luôn phân biệt được “không được chọn” với “được chọn nhưng null”. Nếu cần giữ sự khác biệt ấy, phải thể hiện nó trong hợp đồng đọc dữ liệu hoặc read model và dùng khả năng tương ứng của store.

Đặc biệt:

```text
Không có bản ghi              != Có bản ghi nhưng không dựng được entity
Không biết quantity           != quantity bằng 0
Không có description          != description là chuỗi rỗng
Thiếu dữ liệu do projection   != Domain cho phép dữ liệu đó vắng mặt
```

## 2. Nullability là hợp đồng giữa nhiều tầng

Một thuộc tính có thể bị ràng buộc ở nhiều nơi:

1. **Kiểu dữ liệu của ngôn ngữ:** `int` không biểu diễn null; `Integer` có thể biểu diễn null. Kotlin phân biệt `String` với `String?`.
2. **Hợp đồng domain:** một SKU có thể bắt buộc khác null và không rỗng, dù kiểu Java `String` tự nó vẫn cho phép null.
3. **Metadata và cơ chế của framework:** annotation nullability, creator metadata, converter và cấu hình repository có các vai trò riêng.
4. **Schema của kho dữ liệu:** ràng buộc `NOT NULL`, validation của document hoặc quy tắc tương tự.
5. **Hợp đồng truy vấn:** kết quả có thực sự cung cấp những thuộc tính cần thiết không?

Không có một annotation duy nhất tự đồng bộ toàn bộ năm tầng này.

Ví dụ, một cột có ràng buộc `NOT NULL` không giúp một query đã bỏ cột đó khỏi tập kết quả cung cấp lại giá trị cho constructor. Một field Java có annotation mô tả non-null cũng không tự sửa các document cũ đang thiếu field.

Nếu những tầng này mâu thuẫn, cần sửa đúng hợp đồng: schema, dữ liệu cũ, query, kiểu object hoặc creator. Nới constructor để nhận mọi dữ liệu có thể làm lỗi biến mất trước mắt nhưng khiến object không còn diễn đạt đúng nghiệp vụ.

## 3. Ví dụ entity bất biến có thuộc tính bắt buộc và tùy chọn

Giả sử ứng dụng dùng một module có hỗ trợ cơ chế constructor mapping tương ứng. Entity có hợp đồng:

| Thuộc tính | Hợp đồng |
| --- | --- |
| `id` | Có thể null khi tạo mới và chờ store cấp định danh, nếu chiến lược ID của ứng dụng hỗ trợ |
| `sku` | Bắt buộc, không null và không chỉ gồm khoảng trắng |
| `quantity` | Bắt buộc, không null và không âm |
| `description` | Có thể null vì không phải mặt hàng nào cũng có mô tả |

Ví dụ Java:

```java
import java.beans.ConstructorProperties;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;

public final class InventoryItem {

    @Id
    private final String id;
    private final String sku;
    private final Integer quantity;
    private final String description;

    @PersistenceCreator
    @ConstructorProperties({"id", "sku", "quantity", "description"})
    public InventoryItem(
            String id,
            String sku,
            Integer quantity,
            String description) {
        this.id = id;
        this.sku = Objects.requireNonNull(sku, "sku is required");
        this.quantity = Objects.requireNonNull(quantity, "quantity is required");
        this.description = description;

        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity must not be negative");
        }
    }

    public static InventoryItem createNew(String sku) {
        return new InventoryItem(null, sku, 0, null);
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public String getDescription() {
        return description;
    }
}
```

Đây là ví dụ hợp đồng object và creator, không phải cấu hình hoàn chỉnh cho mọi store. Module cụ thể vẫn cần entity mapping, converter và cấu hình kho dữ liệu phù hợp. Đặc biệt, không dùng ví dụ này để suy ra rằng một entity JPA có thể bỏ qua mọi yêu cầu khởi tạo của JPA provider.

`@PersistenceCreator` thể hiện constructor dự kiến dùng cho persistence trong hạ tầng hỗ trợ annotation này. `@ConstructorProperties` cung cấp tên các thuộc tính tương ứng với đối số. Chúng không làm null trở thành một giá trị hợp lệ cho `sku` hay `quantity`.

### 3.1. Tạo mới khác với khôi phục từ dữ liệu

`createNew("SKU-42")` chủ động chọn số lượng ban đầu bằng 0. Đây là quyết định nghiệp vụ cho thao tác tạo mới.

Constructor dùng để khôi phục object không tự thay null bằng 0. Nếu một bản ghi đã tồn tại nhưng không cung cấp được `quantity`, nó không đủ dữ liệu để biểu diễn một `InventoryItem` đầy đủ theo hợp đồng trên.

Sự tách biệt này tránh suy luận sai:

```text
Hàng mới bắt đầu với quantity = 0
                    không suy ra
Mọi dữ liệu cũ thiếu quantity đều có quantity = 0
```

Nếu doanh nghiệp xác nhận số lượng của toàn bộ dữ liệu cũ phải được hiểu là 0, hãy thể hiện quyết định ấy bằng một chiến lược tương thích hoặc migration rõ ràng.

### 3.2. ID null không có cùng ý nghĩa ở mọi thời điểm

ID null trong object mới có thể hợp lệ theo chiến lược sinh ID. ID thiếu vì query không chọn khóa của một bản ghi đã tồn tại lại là vấn đề khác.

Không coi một entity đọc thiếu ID là entity mới một cách vô thức. Cơ chế nhận biết entity mới có thể dựa trên ID, version hoặc chiến lược riêng của store; thiếu những giá trị này có thể làm một lần `save` sau đó đi theo đường không mong muốn.

## 4. Primitive, wrapper và annotation nullability

### 4.1. Primitive không biểu diễn được “chưa biết”

Nếu thuộc tính là:

```java
private final int quantity;
```

thì object chỉ biểu diễn một số nguyên. Nó không thể biểu diễn null để phân biệt “chưa biết” với 0.

Khi dữ liệu nguồn thiếu hoặc null, module có thể từ chối việc cấp giá trị cho primitive, bỏ qua một bước gán hoặc xử lý theo một quy tắc chuyển đổi cụ thể. Không mặc định rằng Spring Data Commons luôn chuyển null thành 0.

Cũng không kết luận ngược lại rằng thấy `quantity == 0` chứng minh store đã lưu 0. Trong một mô hình mutable, field primitive có giá trị khởi tạo Java bằng 0 và có thể chưa từng được gán từ dữ liệu, tùy đường mapping thực tế.

### 4.2. Wrapper cho phép biểu diễn null, nhưng chưa định nghĩa nghiệp vụ

Dùng `Integer` cho phép biểu diễn trạng thái thiếu. Domain vẫn phải quyết định trạng thái đó có hợp lệ không.

Trong ví dụ `InventoryItem`, `Integer` giúp hợp đồng đầu vào diễn đạt được trường hợp null và constructor chủ động từ chối nó. Trong một read model hiển thị tình trạng “chưa kiểm kê”, `Integer quantity` có thể được phép null nếu ý nghĩa được mô tả rõ.

Không đổi `int` thành `Integer` chỉ để ngừng báo lỗi rồi bỏ qua mọi chỗ sử dụng có thể unbox null.

### 4.3. Annotation không phải phép biến đổi dữ liệu

Annotation như `@Nullable` hoặc một hệ annotation non-null mô tả hợp đồng và có thể được công cụ hay framework hỗ trợ phân tích hoặc kiểm tra. Hành vi cụ thể phụ thuộc hệ annotation, phiên bản và vị trí áp dụng.

Không mặc định rằng một annotation non-null trên field sẽ:

- Sinh giá trị thay thế khi kho dữ liệu trả null.
- Tự thực thi mọi validation khi đọc object.
- Tạo ràng buộc schema cho tất cả module lưu trữ.
- Kiểm tra toàn bộ các thuộc tính bên trong một object được repository trả về.

Tương tự, Bean Validation như `@NotNull` cần được gọi qua cơ chế validation thích hợp. Không giả định mọi đường đọc của repository tự động chạy Bean Validation trước hoặc sau khi tạo entity.

## 5. Giá trị mặc định có thể nằm ở đâu?

Từ “mặc định” dễ gây nhầm vì nó có thể chỉ nhiều cơ chế khác nhau:

| Nơi đặt mặc định | Khi nào có tác dụng? | Không tự bảo đảm |
| --- | --- | --- |
| Field initializer Java | Khi instance được khởi tạo theo quy tắc Java | Giữ được giá trị nếu constructor hoặc mapper gán đè |
| Factory tạo mới của domain | Khi mã gọi đúng factory đó | Tự áp dụng cho việc đọc dữ liệu đã tồn tại |
| Logic trong persistence constructor | Khi constructor ấy được chọn và thực thi | Phân biệt được missing với explicit null nếu trước đó đã bị gom lại |
| Constructor default của Kotlin | Khi cơ chế Kotlin materialization áp dụng defaulting tương ứng | Có cùng hành vi trên mọi đường tạo object và mọi store |
| Default trong schema | Với những thao tác ghi và điều kiện mà database quy định | Tự bổ sung cột không được chọn trong query hoặc sửa mọi bản ghi cũ |
| Biểu thức trong query hoặc converter | Khi đọc qua đúng query hoặc converter đó | Phù hợp nghiệp vụ cho mọi đường đọc khác |

Chọn nơi đặt mặc định theo ý nghĩa nghiệp vụ và vòng đời dữ liệu, thay vì chọn nơi dễ làm exception biến mất nhất.

### 5.1. Field initializer Java có thể bị gán đè

```java
public final class WorkflowState {

    private String status = "DRAFT";

    public WorkflowState(String status) {
        this.status = status;
    }

    public String getStatus() {
        return status;
    }
}
```

Lời gọi:

```java
new WorkflowState(null).getStatus();
```

trả về null. Initializer đã chạy, nhưng constructor gán đè bằng đối số null.

Một mapper gán thuộc tính sau khởi tạo cũng có thể gán đè initializer. Nếu mapper bỏ qua một thuộc tính vắng mặt thì initializer có thể còn nguyên; đó là hành vi cần xác nhận theo module và đường mapping, không phải một bảo đảm chung cho mọi entity.

### 5.2. Mặc định trong constructor là một quyết định làm mất thông tin

```java
this.quantity = quantity == null ? 0 : quantity;
```

Dòng này hợp lệ về Java, nhưng nó gộp “không có số lượng” và “số lượng bằng 0”. Nếu thiếu dữ liệu có thể do query sai hoặc do hệ thống chưa kiểm kê, việc gộp hai trạng thái sẽ che mất thông tin.

Chỉ dùng khi nghiệp vụ đã xác định rõ null phải được hiểu là 0 trong đúng ngữ cảnh. Nếu cần giữ trạng thái chưa biết, dùng một kiểu hoặc read model biểu đạt được trạng thái ấy.

### 5.3. Mặc định trong schema chủ yếu là hợp đồng ghi

Một cột có default bằng 0 thường phục vụ việc insert trong những điều kiện database quy định, chẳng hạn cột được bỏ khỏi câu lệnh insert. Không mặc định rằng truyền explicit `NULL` cũng được thay bằng default; hành vi đó phụ thuộc database và schema.

Đặc biệt, default của schema không tự bổ sung `quantity` cho kết quả:

```sql
SELECT id, sku
FROM inventory_item
WHERE id = :id
```

Câu query không chọn `quantity`. Kể cả mọi dòng trong bảng đều có số lượng hợp lệ, tập kết quả này vẫn không cung cấp nó để dựng entity đầy đủ.

## 6. Kotlin: nullable và constructor default có ý nghĩa riêng

Với cơ chế materialization hỗ trợ Kotlin của Spring Data, tham số có giá trị mặc định có thể được để cho Kotlin áp dụng default khi datastore không cung cấp giá trị hoặc trả null theo đường mapping được hỗ trợ.

Ví dụ:

```kotlin
import org.springframework.data.annotation.Id

data class CustomerProfile(
    @Id val id: String?,
    val displayName: String,
    val locale: String = "vi",
    val nickname: String? = null
) {
    init {
        require(displayName.isNotBlank())
        require(locale.isNotBlank())
    }
}
```

Trong đường Kotlin mapping có hỗ trợ defaulting:

- `displayName` không nullable và không có default. Thiếu giá trị hợp lệ có thể làm việc tạo object thất bại.
- `locale` không nullable nhưng có default `"vi"`. Cơ chế defaulting có thể dùng giá trị đó khi dữ liệu nguồn không cung cấp giá trị hoặc trả null.
- `nickname` là nullable, có default null, nên việc không có biệt danh phù hợp với hợp đồng.
- Chuỗi rỗng hoặc toàn khoảng trắng vẫn là một giá trị khác null. Nó không tự kích hoạt default; logic `init` trong ví dụ chủ động từ chối.

Không áp dụng kết luận trên cho mọi lời gọi Java reflection, mọi serializer hoặc JPA provider chỉ vì đối tượng được viết bằng Kotlin. Cần đúng đường materialization có hỗ trợ metadata và defaulting của Kotlin.

Defaulting cũng có thể làm mất phân biệt giữa missing và explicit null. Nếu một field null mang ý nghĩa khác với field không tồn tại, không chọn constructor default trước khi xác nhận hợp đồng dữ liệu đó.

## 7. Query từng phần nên trả về kiểu từng phần

Một lý do phổ biến của dữ liệu không đủ là tối ưu query bằng cách chỉ chọn vài thuộc tính nhưng vẫn khai báo trả về entity đầy đủ.

Ví dụ, màn hình chỉ cần ID và SKU:

```sql
SELECT id, sku
FROM inventory_item
ORDER BY sku
```

Nếu kết quả này được đưa vào creator yêu cầu cả `quantity`, hạ tầng phải đối mặt với dữ liệu thiếu. Tùy module, việc mapping có thể thất bại hoặc tạo ra trạng thái từng phần; không được coi đó là một entity đầy đủ dùng an toàn cho mọi thao tác.

Một kiểu kết quả phù hợp hơn, với Java hỗ trợ record, là:

```java
public record InventoryLabel(String id, String sku) {
}
```

Hoặc dùng interface projection nếu module và loại query hỗ trợ:

```java
public interface InventoryLabelView {
    String getId();
    String getSku();
}
```

Cách khai báo query và mapping DTO hoặc projection phải theo khả năng của module lưu trữ. Không giả định mọi store hỗ trợ mọi kiểu projection hoặc mọi cú pháp query như nhau.

Nếu use case thực sự cần một `InventoryItem` hoàn chỉnh, query phải cung cấp đủ dữ liệu mà creator và phần gán thuộc tính yêu cầu. Với mô hình bốn thuộc tính ở bài này, hình dạng kết quả đầy đủ tương ứng là:

```sql
SELECT id, sku, quantity, description
FROM inventory_item
WHERE id = :id
```

Hai đoạn SQL chỉ minh họa khác biệt về dữ liệu được chọn; chúng không phải cú pháp truy vấn dùng chung cho mọi Spring Data repository.

### 7.1. Không save một object từng phần như thể nó đầy đủ

Nếu một entity bị đọc thiếu thuộc tính rồi được lưu lại, việc ghi có thể làm mất dữ liệu hoặc có hành vi không mong đợi tùy store, trạng thái quản lý entity và API ghi.

Ví dụ, `quantity` chưa được đọc không có nghĩa người dùng muốn cập nhật nó thành null hoặc 0. Nếu mục tiêu là sửa một thuộc tính, hãy dùng một luồng cập nhật phù hợp: đọc trạng thái đầy đủ rồi thay đổi theo domain, hoặc dùng thao tác cập nhật tường minh mà module hỗ trợ.

DTO cho màn hình giúp tách rõ “dữ liệu cần hiển thị” với “trạng thái entity đủ để thực hiện thay đổi”.

## 8. Không tìm thấy và không dựng được phải được xử lý khác nhau

Với một repository cung cấp:

```java
Optional<InventoryItem> findById(String id);
```

cần phân biệt:

- Không có bản ghi tương ứng: hợp đồng `Optional` biểu diễn bằng `Optional.empty()`.
- Có dữ liệu nhưng thiếu `quantity` bắt buộc hoặc constructor từ chối `sku`: đây là lỗi materialization hoặc hợp đồng dữ liệu, không phải “không tìm thấy”.

Không bắt mọi lỗi đọc rồi trả `Optional.empty()` để làm API có vẻ ổn định. Người gọi sẽ không phân biệt được một ID không tồn tại với một bản ghi đang bị lỗi dữ liệu hoặc một query đang map sai.

Cũng không mặc định rằng entity có thuộc tính `Optional<Integer>` sẽ khiến converter tự tạo `Optional.empty()` cho mọi giá trị thiếu. `Optional` ở biên phương thức repository và kiểu thuộc tính bên trong entity là hai hợp đồng khác nhau; hỗ trợ mapping thuộc tính phải được xác nhận theo module.

Thông báo lỗi và lớp exception bọc ngoài có thể khác theo store và phiên bản. Khi chẩn đoán, cần xem nguyên nhân gốc: thiếu tên tham số, thiếu property, null cho tham số bắt buộc, chuyển đổi kiểu thất bại hay constructor ném lỗi nghiệp vụ.

## 9. Dữ liệu cũ, schema evolution và mặc định có chủ đích

Giả sử phiên bản đầu của hệ thống chưa có `quantity`, phiên bản mới yêu cầu nó. Dữ liệu cũ không tự trở thành hợp lệ chỉ vì mã Java đã thêm field.

Có thể cân nhắc những hướng sau theo nghiệp vụ:

| Hướng xử lý | Phù hợp khi | Điều phải làm rõ |
| --- | --- | --- |
| Backfill hoặc migration | Có quy tắc xác định giá trị đúng cho dữ liệu cũ | Nguồn giá trị, phạm vi dữ liệu và cách kiểm tra kết quả |
| Đọc tương thích có thời hạn | Cần một giai đoạn chuyển đổi giữa các phiên bản | Mặc định áp dụng cho trạng thái nào và khi nào bỏ logic tương thích |
| Cho phép trạng thái chưa biết | Domain thật sự có trường hợp chưa có giá trị | Kiểu dữ liệu và các nghiệp vụ xử lý trạng thái đó |
| Từ chối bản ghi không hợp lệ | Không có cách suy ra giá trị an toàn | Cách phát hiện và sửa dữ liệu tại nguồn |

Không tự bịa một con số chỉ để constructor chạy được. Ví dụ, số lượng bằng 0 có thể khiến hệ thống hiểu sai rằng hàng đã hết, trong khi thực tế chỉ là chưa có dữ liệu kiểm kê.

### 9.1. Converter là một ranh giới, không phải nơi che mọi lỗi

Một converter hoặc adapter chuyên biệt có thể chuyển mô hình lưu trữ cũ sang mô hình domain mới. Nếu dùng cách này, quy tắc phải có phạm vi rõ: loại dữ liệu nào được chuyển, giá trị nào được bù và khi nào phải báo lỗi.

Không viết một converter chung biến mọi null thành chuỗi rỗng hoặc số 0 cho mọi thuộc tính. Những thuộc tính khác nhau có thể mang ý nghĩa null hoàn toàn khác nhau.

### 9.2. Mặc định trong query cũng phải theo nghiệp vụ

Trong SQL, một biểu thức như:

```sql
SELECT id, sku, COALESCE(quantity, 0) AS quantity, description
FROM inventory_item
WHERE id = :id
```

chủ động thay null bằng 0 trong kết quả đọc. Nó có thể hữu ích nếu nghiệp vụ quy định như vậy, nhưng cũng làm mất dấu null và không sửa giá trị được lưu trong bảng.

Không coi `COALESCE` là cách mặc định chữa mọi lỗi dựng entity. Với document store hoặc công nghệ khác, cú pháp và khả năng tương ứng khác nhau; Commons không quy định một biểu thức fallback dùng chung cho mọi store.

## 10. Auditing và version không tự bổ sung mọi dữ liệu thiếu

Các thuộc tính auditing như thời điểm tạo hoặc người tạo có thể được hạ tầng auditing thiết lập ở những điểm của vòng đời ghi mà module hỗ trợ, khi auditing được cấu hình đúng.

Điều đó không bảo đảm một bản ghi cũ luôn có giá trị auditing, hoặc một query từng phần tự có đủ dữ liệu cho constructor. Nếu creator bắt buộc `createdAt` nhưng dữ liệu đọc không có nó, một callback chạy sau bước khởi tạo không thể sửa ngược một object chưa được tạo thành công.

Không dùng “thời điểm hiện tại” làm mặc định cho `createdAt` khi đọc dữ liệu cũ nếu chưa có quyết định nghiệp vụ. Nó sẽ biến thông tin lịch sử chưa biết thành một thời điểm có vẻ chính xác.

Tương tự, null của một thuộc tính `@Version` có thể có vai trò trong việc nhận biết entity mới hoặc quản lý optimistic locking, tùy kiểu và module. Không thay null bằng 0 một cách đồng loạt rồi cho rằng hành vi lưu vẫn giữ nguyên.

Cần phân biệt:

```text
Giá trị được hạ tầng tạo khi ghi mới
              khác với
Giá trị bắt buộc phải có khi đọc một bản ghi đã tồn tại
```

Cấu hình auditing, cơ chế cấp ID và versioning phải được xem cùng vòng đời entity thực tế của store.

## 11. Thiết kế kiểm chứng bằng ma trận dữ liệu

Một kiểm thử chỉ tạo object bằng `new` xác nhận constructor, nhưng chưa xác nhận converter hoặc repository đọc dữ liệu ra sao. Ngược lại, một phép đọc thành công chưa chứng minh giá trị mặc định được áp dụng đúng ý nghĩa nghiệp vụ.

Có thể dùng ma trận sau cho mô hình `InventoryItem`, sau khi thiết lập module và dữ liệu thử phù hợp:

| Dữ liệu nguồn hoặc tình huống | Kỳ vọng theo hợp đồng ví dụ |
| --- | --- |
| Có SKU hợp lệ, quantity bằng 5, description có giá trị | Tạo entity với đúng các giá trị |
| Description null | Entity hợp lệ và giữ description null |
| Description vắng mặt trong một store hỗ trợ biểu diễn field vắng | Kiểm tra mapper; nếu chuyển thành null thì phù hợp thuộc tính tùy chọn |
| Quantity bằng 0 | Entity hợp lệ, giữ số 0 |
| Quantity null | Đường đọc phải thể hiện lỗi theo hợp đồng quantity bắt buộc |
| Quantity vắng mặt hoặc không được chọn | Không coi kết quả là entity đầy đủ; kiểm tra hành vi module và sửa shape truy vấn |
| Quantity âm | Invariant của creator từ chối khi đường mapping dùng creator đó |
| SKU null hoặc blank | Creator từ chối khi được sử dụng như cấu hình |
| Không có bản ghi | API `findById` trả empty theo hợp đồng |
| Tạo mới bằng factory của domain | Quantity bằng 0 là mặc định có chủ đích |

Dùng dữ liệu phân biệt rõ các trạng thái: null, 0, chuỗi rỗng và một giá trị hợp lệ. Không gom chúng thành một fixture duy nhất có tên “empty”.

Với Kotlin, bổ sung các trường hợp field có default bị thiếu, field trả null và field có chuỗi rỗng. Xác nhận hành vi của đúng đường materialization đang sử dụng, thay vì chỉ kiểm tra lời gọi constructor Kotlin trong mã ứng dụng.

Với projection, kiểm tra kiểu trả về đúng và dữ liệu cần cho nó được cung cấp. Không ép projection thành entity chỉ để tái sử dụng một phương thức `save`.

## 12. Trình tự chẩn đoán khi không đủ dữ liệu dựng entity

Đi theo các câu hỏi có thể kiểm chứng:

1. **Có bản ghi hay không?** Tách trạng thái không tìm thấy khỏi lỗi tạo object.
2. **Ai đang tạo object?** Converter của store, cơ chế Commons mapping, JPA provider, DTO mapping của query hay mã trong fragment?
3. **Creator nào được chọn?** Xác định constructor hoặc factory thực tế và thông tin tên tham số của nó.
4. **Dữ liệu nguồn cung cấp gì?** Kiểm tra thuộc tính có được chọn không, có explicit null không và có xảy ra chuyển đổi kiểu không.
5. **Hợp đồng domain yêu cầu gì?** Nullable, không nullable, không rỗng, không âm và mặc định có chủ đích là những điều khác nhau.
6. **Mặc định nào thực sự chạy?** Field initializer, factory, Kotlin default, converter hay database default?
7. **Có đang đọc một phần nhưng yêu cầu một object đầy đủ không?** Nếu có, chọn projection hoặc thay đổi query.
8. **Có vấn đề dữ liệu cũ không?** Cân nhắc migration hoặc đọc tương thích có phạm vi, thay vì che lỗi bằng fallback toàn cục.

Nếu constructor ném lỗi, xem nguyên nhân gốc trước khi thay đổi nullability. Một lỗi “quantity is required” có thể bắt nguồn từ query bỏ cột, không phải bằng chứng rằng domain nên cho phép quantity null.

Nếu object được tạo nhưng quantity bất ngờ bằng 0, kiểm tra xem đó là giá trị được lưu, default của Java, Kotlin default, fallback trong converter hay biểu thức của query. Cùng một kết quả số học có thể xuất phát từ những hợp đồng dữ liệu rất khác nhau.

## 13. Bài tập thực hành

Trong một dự án có module lưu trữ đã cấu hình:

1. Dựng mô hình `InventoryItem` với SKU và quantity bắt buộc, description tùy chọn.
2. Kiểm tra riêng constructor và đường đọc qua repository hoặc converter.
3. Tạo dữ liệu có quantity bằng 0, null và thiếu thuộc tính nếu store cho phép; ghi nhận sự khác biệt ở dữ liệu nguồn và giá trị mapper cung cấp.
4. Thực hiện một query chỉ lấy ID và SKU, trả về DTO hoặc projection tương ứng.
5. Giải thích vì sao query đó không đủ để tạo một entity đầy đủ có quantity bắt buộc.
6. Thêm một factory tạo mới chọn quantity bằng 0, đồng thời giữ persistence creator từ chối quantity null.
7. Nếu dùng Kotlin, thử constructor default trên đúng đường mapping được hỗ trợ và kiểm tra cả null lẫn chuỗi rỗng.
8. Đề xuất cách xử lý dữ liệu cũ thiếu quantity dựa trên ý nghĩa nghiệp vụ, bao gồm trường hợp không thể suy ra giá trị.

Mục tiêu là tạo được object đúng nghĩa, thay vì chỉ tạo được object. Giá trị mặc định chỉ phù hợp khi nó diễn đạt một quyết định rõ ràng; khi dữ liệu thực sự chưa đủ, cần biểu diễn trạng thái thiếu, sửa đường đọc hoặc sửa dữ liệu theo đúng hợp đồng.
