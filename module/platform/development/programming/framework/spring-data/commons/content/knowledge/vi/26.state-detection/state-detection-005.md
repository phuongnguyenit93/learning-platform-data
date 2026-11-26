# Persistable<T> và isNew

Một entity có ID chưa chắc đã được lưu. Điều này thường gặp khi ứng dụng tự cấp UUID, mã nghiệp vụ hoặc một định danh khác trước khi gọi repository. Nếu cơ chế phát hiện trạng thái chỉ nhìn ID khác null, nó có thể coi object vừa được tạo là object đã tồn tại.

`Persistable` cho phép entity chủ động cung cấp câu trả lời cho câu hỏi “object này có được xem là mới ở đường xử lý persistence hiện tại không?”. Đổi lại, ứng dụng phải duy trì câu trả lời ấy đúng trong suốt vòng đời tạo mới, đọc lại và lưu dữ liệu.

Bài học thuộc chương **Phát hiện trạng thái** của **Spring Data Commons**. Trọng tâm là hợp đồng `Persistable` và `isNew()`, cách mở rộng hành vi repository bằng metadata trạng thái, cùng những giới hạn khác nhau giữa các module lưu trữ.

## 1. Tham số kiểu là kiểu ID

Interface được dùng trong ứng dụng nằm ở package:

```java
org.springframework.data.domain.Persistable
```

Dạng rút gọn của hợp đồng là:

```java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
```

Trong cách viết `Persistable<T>`, tham số `T` là **kiểu của định danh**, không phải kiểu entity. Vì vậy, một entity có ID kiểu `String` triển khai:

```java
public class AssignedItem implements Persistable<String> {
    // ...
}
```

Không viết `Persistable<AssignedItem>` chỉ vì lớp entity tên là `AssignedItem`.

Hai phương thức đảm nhận hai việc khác nhau:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getId()` | Trả về định danh của object theo hợp đồng entity |
| `isNew()` | Cung cấp kết quả phát hiện trạng thái mới cho hạ tầng có hỗ trợ `Persistable` |

Tùy chiến lược cấp ID, `getId()` có thể trả null trước khi lưu. Với ID do ứng dụng cấp, nó có thể khác null ngay khi object vừa được tạo. Kiểu annotation nullability trên API phụ thuộc phiên bản; không suy ra trạng thái chỉ từ việc chữ ký rút gọn trong bài không hiển thị annotation.

## 2. isNew không phải một câu truy vấn tồn tại

`isNew()` là một quyết định trạng thái do object hoặc chiến lược của ứng dụng cung cấp. Nó không tự hỏi database xem bản ghi đã tồn tại chưa.

Cần phân biệt:

```text
Có ID                       khác với Đã được lưu
isNew() == false            khác với Đã xác nhận bản ghi đang tồn tại
isNew() == true             khác với Đã đặt trước thành công một ID trong database
Object bị sửa dữ liệu       khác với Object mới
Object đang managed bởi JPA khác với Kết quả duy nhất có thể suy ra từ isNew()
```

Ví dụ:

```java
String id = java.util.UUID.randomUUID().toString();
AssignedItem item = AssignedItem.create(id, "Mặt hàng mới");
```

Object này đã có ID nhưng chưa được lưu. Ngược lại, một entity đọc từ kho dữ liệu vẫn là entity đã tồn tại dù thuộc tính nghiệp vụ của nó vừa bị thay đổi trong bộ nhớ.

`isNew()` cũng không thay thế trạng thái managed hoặc detached của JPA, dirty checking, optimistic locking hay kiểm tra quyền cập nhật. Đó là các cơ chế khác, có thể cùng tham gia một thao tác lưu.

## 3. Khi triển khai Persistable, ứng dụng nhận thêm trách nhiệm

Ở những đường repository hoặc mapping hỗ trợ cơ chế này, Spring Data ủy quyền việc xác định entity mới cho `Persistable.isNew()` thay vì chỉ áp dụng chiến lược metadata mặc định tại đường đó.

Chiến lược mặc định có thể xem ID, thuộc tính version hoặc metadata khác theo module. Không nên mô tả mọi store bằng một công thức duy nhất như “ID null là mới, ID khác null là cũ”.

Khi chủ động triển khai `Persistable`, cần trả lời đầy đủ:

1. Object vừa được tạo có trả true không?
2. Object được đọc từ store có trả false không?
3. Sau một lần lưu mới, khi nào trạng thái chuyển thành false?
4. Nếu save trả về một instance khác, ứng dụng tiếp tục dùng instance nào?
5. Nếu thao tác ghi hoặc transaction thất bại, object trong bộ nhớ còn phù hợp để dùng lại không?

Spring Data Commons định nghĩa hợp đồng chung. Nó không cung cấp một phép chuyển cờ duy nhất, tự động đúng cho mọi module, mọi callback và mọi kiểu transaction.

### 3.1. Tại sao chỉ kiểm tra ID đôi khi không đủ?

Một implementation như sau vẫn phụ thuộc hoàn toàn vào ID:

```java
@Override
public boolean isNew() {
    return id == null;
}
```

Nó có thể phù hợp với một chiến lược ID cụ thể, nhưng không giải quyết trường hợp ứng dụng cấp ID trước khi lưu. Khi đó, object mới có ID khác null sẽ trả false.

Nếu chiến lược mặc định của module đã đáp ứng đúng nhu cầu, không cần triển khai `Persistable` chỉ để lặp lại cùng một phép kiểm tra. Chỉ chọn abstraction này khi ứng dụng có một hợp đồng trạng thái rõ ràng để cung cấp.

## 4. Thiết kế vòng đời trước khi viết cờ

Với ID do ứng dụng cấp, một mô hình thường dùng là:

```text
Factory tạo entity mới
        |
        v
isNew = true
        |
        | Ghi mới theo đường persistence của module
        | Cập nhật trạng thái tại lifecycle point đã chọn
        v
isNew = false

Đọc entity đã tồn tại từ store
        |
        v
isNew = false
```

Cờ này là metadata của vòng đời persistence, không phải trạng thái nghiệp vụ như `DRAFT`, `APPROVED` hoặc `ARCHIVED`.

Một đơn hàng đang ở trạng thái nghiệp vụ `DRAFT` có thể đã được lưu nhiều lần và phải trả `isNew() == false`. Ngược lại, một object vừa được tạo có thể mang trạng thái nghiệp vụ khác nhưng vẫn chưa được lưu.

### 4.1. Trạng thái cần ổn định khi chỉ đọc

Hạ tầng có thể hỏi `isNew()` nhiều lần, chẳng hạn ở repository và ở một thành phần auditing có sử dụng phát hiện trạng thái. Không có hợp đồng rằng phương thức chỉ được gọi đúng một lần cho mỗi lần save.

Vì vậy, tránh implementation có tác dụng phụ:

```java
@Override
public boolean isNew() {
    boolean result = newEntity;
    newEntity = false;
    return result;
}
```

Chỉ việc kiểm tra đã làm thay đổi kết quả lần sau. Một lần log hoặc một callback có thể khiến repository đi theo nhánh khác.

`isNew()` nên là một phép đọc nhanh, ổn định trong cùng trạng thái vòng đời và không thực hiện I/O.

## 5. Ví dụ dùng factory tạo mới và persistence constructor khôi phục

Ví dụ sau phù hợp để minh họa một module có hỗ trợ constructor mapping và `Persistable`. Nó tách đường tạo mới với đường khôi phục object đã có trong store.

```java
import java.beans.ConstructorProperties;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;

public final class AssignedItem implements Persistable<String> {

    @Id
    private final String id;
    private final String label;

    @Transient
    private boolean newEntity;

    @PersistenceCreator
    @ConstructorProperties({"id", "label"})
    private AssignedItem(String id, String label) {
        this.id = Objects.requireNonNull(id, "id is required");
        this.label = Objects.requireNonNull(label, "label is required");
        this.newEntity = false;
    }

    public static AssignedItem create(String id, String label) {
        AssignedItem item = new AssignedItem(id, label);
        item.newEntity = true;
        return item;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

Những điểm cần đọc đúng:

- `create(...)` là đường tạo mới của ứng dụng nên chủ động bật cờ true.
- Persistence constructor tạo object khôi phục với cờ false. Cách này chỉ đúng khi module thực sự sử dụng creator này cho materialization.
- Cờ không là một tham số bắt buộc trong constructor mapping, vì nó không phải dữ liệu được lưu.
- `markPersisted()` là một phương thức của ứng dụng, không phải callback mà Commons tự tìm và gọi theo tên.
- Ứng dụng vẫn phải tích hợp việc gọi `markPersisted()` tại điểm vòng đời phù hợp với store và transaction.

Đoạn mã không phải một cấu hình hoàn chỉnh cho mọi kho dữ liệu. Store phải có mapping phù hợp, nhận diện creator và sử dụng `Persistable` tại đường lưu đang xét. Không dùng constructor private và annotation Commons ở đây như một cách thay thế mọi quy tắc entity của JPA.

### 5.1. Đường lưu cần xử lý cả kết quả trả về

Về mặt ý tưởng, một đường đồng bộ có thể cần chuyển trạng thái sau khi repository đã hoàn thành thao tác lưu tương ứng:

```java
AssignedItem saved = repository.save(item);
// Tại điểm vòng đời được ứng dụng lựa chọn và kiểm chứng:
saved.markPersisted();
return saved;
```

Đoạn này minh họa trách nhiệm quản lý trạng thái, không cam kết rằng save đã đồng nghĩa transaction commit. Nếu store đã có callback xử lý cờ, không cần lặp lại việc quản lý thủ công mà không có lý do.

`CrudRepository.save(...)` có thể trả về một instance khác với object đầu vào. Instance trả về cũng có thể chứa ID, version hoặc giá trị được cập nhật bởi hạ tầng. Hãy tiếp tục làm việc với kết quả đã lưu; không mặc định rằng cờ và toàn bộ dữ liệu của object đầu vào đã được đồng bộ.

Với ví dụ constructor khôi phục đặt cờ false, các bản sao do mapping tạo cần được hiểu theo đúng đường thực thi. Kiểm thử tích hợp phải xác nhận instance thực tế và thời điểm trạng thái đổi, thay vì suy luận chỉ từ mã factory.

### 5.2. Nếu dùng cờ mặc định true thì phải xử lý sau khi đọc

Một thiết kế khác khởi tạo cờ bằng true:

```java
@Transient
private boolean newEntity = true;
```

Cách này thuận tiện cho đường tạo mới nhưng có một bẫy: materialization cũng có thể tạo instance với cờ true. Nếu không có bước chuyển sau khi đọc, entity lấy từ store vẫn tự nhận là mới.

Khi chọn thiết kế đó, phải có lifecycle callback hoặc cơ chế khôi phục thích hợp để cờ trở thành false trên entity đã được đọc. JPA có một mẫu callback riêng được trình bày ở phần sau; không mang nguyên annotation JPA sang một store khác và kỳ vọng chúng hoạt động.

## 6. @Transient phải phù hợp với hệ mapping

Cờ `newEntity` thường không phải dữ liệu nghiệp vụ cần lưu. Khi dùng property access, phương thức `isNew()` cũng có thể được nhìn như một thuộc tính theo quy tắc truy cập bean.

Vì vậy, cần loại metadata trạng thái này khỏi mapping đúng cách:

| Ngữ cảnh | Cơ chế cần phân biệt |
| --- | --- |
| Mapping của Spring Data sử dụng annotation Commons tương ứng | `org.springframework.data.annotation.Transient` |
| Entity JPA | `jakarta.persistence.Transient` trong hệ JPA dùng Jakarta |
| Java serialization | Keyword `transient` có vai trò riêng |
| JSON hoặc một serializer khác | Có cơ chế cấu hình riêng; persistence transient không tự quyết định mọi hành vi serialization |

Không coi các annotation cùng tên là thay thế cho nhau. Đặc biệt, nếu đã cấu hình property access, hãy bảo đảm `isNew()` không vô tình trở thành property được persistence lưu lại.

Cũng không nên nhận trực tiếp cờ `newEntity` từ request rồi tin nó như quyết định của hạ tầng. Một DTO đầu vào mô tả lệnh tạo hoặc cập nhật giúp ứng dụng chủ động dựng đúng object và trạng thái vòng đời.

## 7. Mẫu riêng cho Spring Data JPA với ID do ứng dụng cấp

Spring Data JPA có thể dùng `Persistable.isNew()` để quyết định gọi `EntityManager.persist(...)` hay `EntityManager.merge(...)` trong implementation repository tiêu chuẩn.

Một mẫu thường dùng đặt cờ transient ban đầu là true và chuyển thành false bằng callback JPA sau khi persist hoặc sau khi load:

```java
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Transient;

import org.springframework.data.domain.Persistable;

@MappedSuperclass
public abstract class AssignedIdEntity<ID> implements Persistable<ID> {

    @Transient
    private boolean newEntity = true;

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    protected void markNotNew() {
        this.newEntity = false;
    }
}
```

Một entity cụ thể có thể cung cấp ID:

```java
import java.util.Objects;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class PurchaseOrder extends AssignedIdEntity<String> {

    @Id
    private String id;

    private String description;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String id, String description) {
        this.id = Objects.requireNonNull(id, "id is required");
        this.description = description;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }
}
```

Ví dụ sử dụng field access qua vị trí `@Id`, có constructor không tham số cho JPA và dùng annotation thuộc `jakarta.persistence`. Dự án dùng hệ dependency khác phải tuân theo đúng API mà bộ JPA của nó hỗ trợ.

Vai trò của các callback:

- `@PostPersist`: chuyển cờ sau sự kiện persist tương ứng của JPA.
- `@PostLoad`: bảo đảm entity đọc từ database không giữ cờ true từ quá trình tạo instance.

Callback của JPA không tự chạy cho một object do ứng dụng tạo bằng `new`, cũng không được Spring Data JDBC hoặc MongoDB tự diễn giải như callback của store đó.

### 7.1. persist và merge không phải hai từ đồng nghĩa với INSERT và UPDATE

Trong repository JPA tiêu chuẩn:

```text
isNew() == true  -> chọn persist
isNew() == false -> chọn merge
```

Không rút gọn thành “true luôn là một câu INSERT ngay lập tức, false luôn là một câu UPDATE”. Thời điểm SQL phụ thuộc persistence context và flush; merge có ngữ nghĩa riêng của JPA và provider.

Với một object có ID nhưng chưa có dòng tương ứng, merge có thể dẫn đến đọc thêm, ghi mới hoặc lỗi tùy mapping, version và quy tắc của provider. Ngược lại, gọi persist cho một ID đã tồn tại có thể gây lỗi ở lúc ghi hoặc flush.

`Persistable` chọn thông tin trạng thái cho đường repository, không viết lại ngữ nghĩa của JPA.

### 7.2. @PostPersist không phải thông báo đã commit

Một callback có thể đổi cờ thành false trong khi transaction còn chưa commit. Nếu transaction rollback sau đó, trạng thái trong bộ nhớ không nhất thiết tự trở lại true.

Không dùng lại một object sau transaction thất bại chỉ vì cho rằng mọi field transient đã được hạ tầng phục hồi. Với một lần thử lại, cần có chiến lược rõ ràng: dựng lại object từ lệnh nghiệp vụ, đọc lại trạng thái cần thiết hoặc điều phối trạng thái theo transaction.

Nếu yêu cầu của ứng dụng là chỉ đánh dấu sau khi commit thành công, phải thiết kế tích hợp transaction tương ứng. Không đổi nghĩa của `@PostPersist` thành “đã bền vững trong database”.

## 8. Khác biệt giữa các module lưu trữ

Commons cung cấp hợp đồng, còn module quyết định kết quả phát hiện trạng thái được sử dụng thế nào.

| Module hoặc ngữ cảnh | Vai trò thường gặp của phát hiện trạng thái | Giới hạn cần nhớ |
| --- | --- | --- |
| Spring Data JPA repository tiêu chuẩn | Chọn persist hoặc merge | SQL, flush, managed state và merge theo JPA/provider |
| Spring Data JDBC | Tham gia lựa chọn đường lưu mới hay cập nhật aggregate | Không có persistence context và dirty checking như JPA |
| Spring Data R2DBC | Tham gia lựa chọn insert hoặc update trên đường save tương ứng | Thực thi reactive và callback theo module |
| Spring Data MongoDB repository tiêu chuẩn | Có thể chọn insert cho entity mới và đường save cho entity không mới | Save không version có thể mang ngữ nghĩa upsert; versioning có quy tắc riêng |
| API insert/update tường minh hoặc custom fragment | Theo implementation cụ thể của API đó | Không mặc định mọi API đều hỏi `isNew()` |

Một entity trả false không có nghĩa mọi store sẽ yêu cầu bản ghi phải tồn tại theo cùng một cách. Đặc biệt, ngữ nghĩa upsert ở một document store không tương đương với merge của JPA hay update của một relational module.

`saveAll(...)` cũng có thể dùng đường batch hoặc tối ưu riêng. Không thiết kế cờ dựa trên giả định mỗi phần tử chắc chắn được gọi qua chính phương thức `save(...)` mà ứng dụng đang quan sát.

Với API reactive, việc tạo một `Mono` hoặc `Flux` chưa đồng nghĩa thao tác ghi đã thực thi thành công. Không đánh dấu entity đã được lưu chỉ vì phương thức vừa trả về publisher. Chuyển trạng thái phải gắn với lifecycle và tín hiệu hoàn thành phù hợp, đồng thời xét transaction reactive nếu có.

## 9. Auditing, version và việc phát hiện trạng thái

### 9.1. Auditing có thể cần biết entity mới hay cũ

Những đường auditing hỗ trợ phát hiện trạng thái có thể dùng thông tin này để phân biệt ghi mới với cập nhật. Khi đó, một cờ sai có thể ảnh hưởng đến cách thiết lập metadata như thời điểm tạo hoặc sửa.

Nếu đổi cờ thành false trước khi auditing cần kiểm tra entity mới, thông tin tạo mới có thể không được xử lý như dự kiến. Nếu entity đã tồn tại vẫn trả true, đường xử lý có thể áp dụng hành vi dành cho entity mới.

Trình tự callback và hành vi auditing phải được kiểm chứng theo module. Không gắn một callback tùy ý rồi giả định nó luôn chạy đúng trước hoặc sau mọi thành phần của store.

### 9.2. Persistable không thay thế optimistic locking

`@Version` và `isNew()` trả lời những câu hỏi khác nhau:

- `isNew()` cung cấp quyết định entity mới tại đường phát hiện trạng thái đang dùng.
- Version hỗ trợ phát hiện cập nhật cạnh tranh ở những module có tính năng tương ứng, và có thể tham gia chiến lược phát hiện trạng thái mặc định.

Khi module đã ủy quyền cho `Persistable`, cần hiểu rằng cờ của ứng dụng phải nhất quán với trạng thái entity; không kỳ vọng version tự sửa một `isNew()` luôn trả sai.

Cũng không tự gán version hoặc reset cờ để né lỗi optimistic locking. Lỗi đó cần được xử lý theo hợp đồng cạnh tranh của nghiệp vụ và store.

## 10. Những implementation sai thường gặp

### 10.1. Luôn trả true

```java
@Override
public boolean isNew() {
    return true;
}
```

Object đọc lại cũng bị coi là mới. Một lần lưu tiếp theo có thể đi vào insert hoặc persist không phù hợp và gặp xung đột định danh.

### 10.2. Luôn trả false

```java
@Override
public boolean isNew() {
    return false;
}
```

Mọi object tạo mới bị đưa vào đường dành cho entity không mới. Một store có thể cập nhật không có dòng tương ứng; một store khác có thể merge hoặc upsert. Việc một thao tác vẫn có vẻ thành công không chứng minh hợp đồng trạng thái là đúng.

### 10.3. Đánh dấu không mới trước khi save

```java
item.markPersisted();
repository.save(item);
```

Cờ đã đổi trước khi repository đưa ra quyết định. Với entity cần ghi mới, thao tác này có thể trực tiếp đưa save vào sai nhánh.

### 10.4. Gọi repository trong isNew

```java
@Override
public boolean isNew() {
    return !repository.existsById(id);
}
```

Thiết kế này làm một phép kiểm tra trạng thái trở thành I/O, có thể tạo thêm nhiều truy vấn và vòng phụ thuộc. Nó cũng không bảo đảm tính nguyên tử:

```text
Luồng A: kiểm tra chưa có ID
Luồng B: kiểm tra chưa có ID
Luồng A: insert
Luồng B: insert với cùng ID
```

Ràng buộc duy nhất, transaction và cơ chế xử lý xung đột của store vẫn cần thiết. Một lần `existsById` trước save không tạo ra một khóa bảo đảm entity sẽ được ghi theo ý muốn.

Nếu use case cần một thao tác upsert hoặc cập nhật có điều kiện, hãy dùng API và hợp đồng cạnh tranh phù hợp thay vì giấu chúng trong `isNew()`.

### 10.5. Copy hoặc deserialize mà quên hợp đồng trạng thái

Một constructor phục hồi, công cụ copy hoặc serializer có thể tạo object với cờ mặc định khác object ban đầu. Hãy quyết định rõ đó là:

- Bản sao của entity đã tồn tại.
- Một entity mới với ID mới.
- Một command hoặc DTO chưa phải entity.

Không dùng cùng một đường copy cho cả ba ý nghĩa rồi trông chờ hạ tầng tự đoán.

## 11. Ma trận ID và isNew

Ma trận này giúp xem trạng thái mà object công bố, không phải một bảng bảo đảm kết quả SQL:

| ID | `isNew()` | Cách diễn giải và điều cần kiểm tra |
| --- | --- | --- |
| Null | true | Có thể là entity mới chờ store cấp ID, nếu chiến lược đó được hỗ trợ |
| Khác null | true | Trường hợp điển hình của entity mới có ID do ứng dụng cấp |
| Khác null | false | Có thể là entity đã tồn tại; cờ không tự chứng minh bản ghi đang có trong store |
| Null | false | Thường đáng kiểm tra vì đường entity không mới thiếu định danh; xử lý cụ thể phụ thuộc store |

Trong ví dụ `AssignedItem`, ID bắt buộc khác null vì ứng dụng chọn chiến lược tự cấp ID. Đó là hợp đồng của ví dụ, không phải yêu cầu chung rằng mọi `Persistable` đều phải có ID ngay khi được tạo.

Nếu metadata version, ID và cờ đang biểu diễn các trạng thái mâu thuẫn, cần quay lại đường tạo hoặc khôi phục object, thay vì sửa từng điều kiện riêng lẻ để ép save chạy.

## 12. Kiểm chứng ở hai tầng

### 12.1. Kiểm thử hợp đồng trong bộ nhớ

Với mô hình factory của bài, các hành vi có ý nghĩa gồm:

```java
AssignedItem item = AssignedItem.create("ITEM-42", "Bàn phím");

assertEquals("ITEM-42", item.getId());
assertTrue(item.isNew());
assertTrue(item.isNew()); // Đọc lại không làm thay đổi trạng thái.

item.markPersisted();

assertFalse(item.isNew());
assertFalse(item.isNew());
```

Các assertion là ví dụ dùng với framework kiểm thử như JUnit. Chúng xác nhận hợp đồng của object, chưa xác nhận repository sử dụng cờ hoặc callback đã được đăng ký đúng.

### 12.2. Kiểm thử tích hợp qua repository và store thật của dự án

Những kịch bản quan trọng:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Tạo mới với ID khác null | Đường lưu phù hợp entity mới được sử dụng |
| Đọc entity đã lưu | Object trả `isNew() == false` |
| Lưu lại entity đã tồn tại | Không vô tình chọn đường ghi mới |
| Save trả về instance khác | Ứng dụng dùng đúng kết quả và trạng thái của nó |
| Ghi bị lỗi hoặc transaction rollback | Không dùng lại trạng thái trong bộ nhớ một cách thiếu kiểm soát |
| Có auditing hoặc version | Metadata được xử lý nhất quán với vòng đời thực tế |
| Hai lần tạo dùng cùng ID | Xung đột được xử lý bởi hợp đồng dữ liệu và store |

Với JPA, nên xác nhận đường đọc thật sự xảy ra. Gọi `findById` trong cùng persistence context có thể trả lại instance đang managed thay vì materialize một instance mới. Muốn kiểm tra `@PostLoad`, cần bố trí kiểm thử để entity được load theo lifecycle dự kiến, chẳng hạn qua một context mới phù hợp.

Với mapping constructor, phải xác nhận hạ tầng thực sự chọn creator dành cho khôi phục. Với reactive API, phải kiểm tra sau khi publisher được thực thi và ở đúng ranh giới transaction.

Không chỉ kiểm tra “save không ném lỗi”. Merge hoặc upsert có thể che một quyết định trạng thái khác với ý định ban đầu; cần xác nhận dữ liệu, trạng thái và đường thực thi có ý nghĩa với module đang dùng.

## 13. Bài tập thực hành

Trong một dự án đã chọn module lưu trữ:

1. Tạo entity có ID do ứng dụng cấp trước khi save.
2. Xác định chiến lược newness mặc định của module và xem nó có phù hợp không.
3. Triển khai `Persistable` với tham số kiểu là kiểu ID.
4. Thiết kế đường tạo mới, đường đọc và điểm chuyển cờ sau ghi; loại cờ khỏi persistence mapping.
5. Kiểm tra entity mới có ID nhưng vẫn trả true, còn entity được đọc lại trả false.
6. Lưu lại entity đã tồn tại và xác nhận không chọn nhầm đường ghi mới.
7. Thử một lỗi ghi hoặc rollback, sau đó giải thích vì sao không được mặc định object trong bộ nhớ đã trở về trạng thái ban đầu.
8. Nếu dùng JPA, kiểm tra cả `@PostPersist` và `@PostLoad`; nếu dùng store khác, chọn lifecycle mechanism của chính module đó.

`Persistable` hữu ích khi ứng dụng biết trạng thái mới theo một hợp đồng rõ ràng hơn phép kiểm tra metadata mặc định. Để dùng đúng, `isNew()` phải phản ánh vòng đời object, được đọc không có tác dụng phụ và luôn được hiểu cùng ngữ nghĩa lưu dữ liệu của store.
