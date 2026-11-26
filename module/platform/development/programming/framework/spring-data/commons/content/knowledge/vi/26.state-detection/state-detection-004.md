# Kiểu nguyên thủy, kiểu bao và giá trị null hoặc 0

Khi gọi `save`, một repository thường phải quyết định đối tượng đang được xem là mới hay đã tồn tại. Quyết định này có thể dựa trên identifier, version hoặc một chiến lược do ứng dụng cung cấp. Vì vậy, lựa chọn giữa `long` và `Long` không chỉ là chi tiết cú pháp Java: nó ảnh hưởng đến những trạng thái mà metadata có thể biểu diễn.

Một field `long` luôn có giá trị số và mặc định là `0`. Một field `Long` có thể là `null`, `0L` hoặc một giá trị khác. Trong các chiến lược nhận diện trạng thái của Spring Data, ba trường hợp này không nhất thiết có cùng ý nghĩa.

Bài học tập trung vào cách phân biệt chúng, thứ tự xem xét ID và version, cùng ranh giới giữa chiến lược dùng chung của Commons với cách một module cụ thể như Spring Data JPA áp dụng việc nhận diện entity mới.

## 1. “Được xem là mới” không phải kết quả kiểm tra cơ sở dữ liệu

Nhận diện trạng thái thường là phép đánh giá metadata và giá trị đang nằm trong đối tượng:

```text
Kiểu entity + metadata + giá trị hiện tại
                  ↓
           Quyết định isNew
                  ↓
      Module chọn đường persistence
```

Nó không mặc nhiên tương đương với:

```text
SELECT ... để kiểm tra bản ghi có tồn tại hay không
```

Ví dụ:

- Một đối tượng có ID được ứng dụng gán trước vẫn có thể chưa từng được lưu.
- Một đối tượng có ID bằng `0` có thể đại diện cho một bản ghi hợp lệ nếu miền dữ liệu cho phép.
- Một đối tượng có version `null` có thể được chiến lược nhận diện xem là mới, dù cơ sở dữ liệu đã có một bản ghi trùng ID.
- Một đối tượng vừa được tạo bằng `new` không nhất thiết được repository nhận diện là mới.

Vì vậy, cần tách hai câu hỏi:

| Câu hỏi | Nguồn trả lời |
| --- | --- |
| Chiến lược của repository đang xem đối tượng này là mới không? | Metadata, kiểu Java và giá trị property |
| Bản ghi có thực sự tồn tại trong store không? | Trạng thái dữ liệu thực tế và kết quả thao tác với store |

Một kết quả `isNew = true` không bảo đảm insert thành công. Ràng buộc duy nhất, cạnh tranh đồng thời hoặc dữ liệu trùng vẫn có thể khiến thao tác bị từ chối.

## 2. Java biểu diễn những trạng thái nào?

### 2.1. Primitive không có trạng thái null

```java
public class PrimitiveState {

    private long id;
    private long version;
}
```

Nếu không được gán giá trị khác, các instance field này là `0`. Không thể dùng chúng để phân biệt:

- Chưa từng được cấp một giá trị.
- Được cấp có chủ đích giá trị `0`.

Lưu ý đây là quy tắc với field. Biến cục bộ Java phải được gán trước khi sử dụng; nó không tự có giá trị mặc định để ứng dụng đọc.

### 2.2. Wrapper có thêm trạng thái vắng giá trị

```java
public class BoxedState {

    private Long id;
    private Long version;
}
```

Nếu không được gán, các field này là `null`.

Với `Long`, các trạng thái sau khác nhau:

```java
Long absent = null;
Long explicitZero = 0L;
Long assigned = 42L;
```

`null` biểu diễn chưa có giá trị tham chiếu. `0L` biểu diễn một giá trị số cụ thể đã hiện diện.

Autoboxing không làm `0L` trở thành `null`. Ngược lại, unboxing `null` sang `long` gây lỗi:

```java
Long absent = null;

// Nếu thực thi, dòng này ném NullPointerException:
long value = absent;
```

### 2.3. Đừng nhầm quy tắc Java với quy tắc nghiệp vụ

Java cho phép `Long` mang giá trị `0L` hoặc số âm. Miền nghiệp vụ có chấp nhận các giá trị đó làm ID không là câu hỏi riêng.

Tương tự, việc repository dùng `0` làm dấu hiệu chưa được cấp ID cho một primitive không có nghĩa mọi cơ sở dữ liệu đều cấm ID bằng `0`.

## 3. Nhận diện bằng ID: long và Long không tương đương

Trong chiến lược nhận diện theo identifier thường gặp của Spring Data, identifier kiểu tham chiếu được xem là chưa có giá trị khi nó là `null`. Với identifier primitive dạng số được hỗ trợ, giá trị `0` được dùng như dấu hiệu mới.

Bảng sau áp dụng khi quyết định thực sự dựa trên ID, không bị version hoặc một chiến lược khác thay thế:

| Kiểu khai báo ID | Giá trị ID | Được xem là mới theo nhận diện ID |
| --- | --- | --- |
| `long` | `0L` | Có |
| `long` | `42L` | Không |
| `long` | `-1L` | Không chỉ vì là số âm |
| `Long` | `null` | Có |
| `Long` | `0L` | Không |
| `Long` | `42L` | Không |
| `String` | `null` | Có |
| `String` | `"0"` | Không |
| `String` | `""` | Không chỉ vì là chuỗi rỗng |

Chuỗi rỗng có thể bị validation hoặc store từ chối. Nhưng “không phải ID hợp lệ theo domain” và “được nhận diện là entity mới” là hai phép đánh giá khác nhau.

### Ví dụ đối chiếu

```java
package com.example.state;

import org.springframework.data.annotation.Id;

public class PrimitiveIdItem {

    @Id
    private long id;

    private String name;

    public PrimitiveIdItem(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }
}
```

```java
package com.example.state;

import org.springframework.data.annotation.Id;

public class BoxedIdItem {

    @Id
    private Long id;

    private String name;

    public BoxedIdItem(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }
}
```

Với một module nhận diện annotation Commons và sử dụng chiến lược ID này:

```java
PrimitiveIdItem first = new PrimitiveIdItem(0L, "First");
BoxedIdItem second = new BoxedIdItem(null, "Second");
BoxedIdItem third = new BoxedIdItem(0L, "Third");
```

`first` và `second` mang dấu hiệu mới theo ID; `third` không có dấu hiệu mới theo cùng quy tắc.

Việc đổi kiểu từ `long` sang `Long` nhưng giữ initializer `0L` không bảo toàn ngữ nghĩa “chưa có ID”. Nếu mục tiêu là biểu diễn chưa được cấp ID, wrapper nên giữ `null` cho trạng thái đó.

## 4. Khi version được ưu tiên, không còn chỉ nhìn ID

Hạ tầng metadata của Commons có chiến lược nhận diện dựa trên version trước, rồi mới dùng identifier khi không có version phù hợp theo chiến lược đó. Entity triển khai `Persistable` là một trường hợp khác và được thảo luận riêng ở phần sau.

Đối với chiến lược mặc định của persistent entity trong Commons:

- Nếu có version property được nhận diện, giá trị version được dùng để quyết định.
- Nếu không có version property, chiến lược dùng ID.
- Giá trị `null` thể hiện trạng thái mới.
- Với property kiểu số primitive được hỗ trợ, giá trị `0` thể hiện trạng thái mới.
- Một giá trị không null của kiểu tham chiếu, kể cả wrapper số bằng `0`, không có cùng ý nghĩa với null.

Điểm dễ nhầm là: “version trước, ID sau” không có nghĩa cứ thấy version `null` thì bỏ qua nó để nhìn tiếp ID. Version `null` có thể đã đủ để kết luận mới.

### Bảng cho chiến lược metadata Commons

Giả định entity không tự điều khiển `isNew`, và version trong bảng là version property được chiến lược Commons nhận diện:

| ID | Kiểu version | Giá trị version | Kết luận theo chiến lược này |
| --- | --- | --- | --- |
| `42L` | `Long` | `null` | Mới |
| `42L` | `Long` | `0L` | Không mới |
| `42L` | `Long` | `3L` | Không mới |
| `42L` | `long` | `0L` | Mới |
| `42L` | `long` | `3L` | Không mới |
| `null` | `Long` | `0L` | Không mới theo version; ID null vẫn có thể gây lỗi ở bước khác |

Hàng cuối không phải một trạng thái nên tạo ra. Nó cho thấy chiến lược tin vào property được chọn, không tự sửa một đối tượng có các dấu hiệu mâu thuẫn.

### Không tự khởi tạo wrapper version thành 0

```java
@org.springframework.data.annotation.Version
private Long version = 0L;
```

Với chiến lược xem version wrapper null là mới, initializer này đã làm mất dấu hiệu chưa được cấp version.

Nếu module chịu trách nhiệm khởi tạo version khi insert, hãy để nó thực hiện công việc đó. Không tự gán version chỉ để “đỡ bị null” mà chưa xét hợp đồng của module.

## 5. Spring Data JPA có quy tắc riêng với primitive version

Không được áp dụng nguyên bảng Commons phía trên cho mọi repository JPA.

Spring Data JPA dùng thông tin entity theo tích hợp JPA. Trong chiến lược mặc định thường dùng:

1. Nếu entity có version property kiểu không primitive thích hợp, xem xét giá trị version: `null` biểu thị entity mới.
2. Nếu không có version như vậy, nhận diện dựa trên identifier.
3. Primitive version không được dùng làm dấu hiệu mới theo cách “version bằng 0”, vì `0` có thể là phiên bản ban đầu hợp lệ của một entity JPA đã được lưu.

Nếu entity triển khai `Persistable`, việc nhận diện có thể được giao cho `isNew()` thay vì thuật toán mặc định đó.

### Đối chiếu trong JPA

| ID | Khai báo version JPA | Giá trị version | Cơ sở nhận diện mặc định |
| --- | --- | --- | --- |
| `"SKU-100"` | `Long version` | `null` | Version cho biết mới |
| `"SKU-100"` | `Long version` | `0L` | Version cho biết không mới |
| `"SKU-100"` | `long version` | `0L` | Bỏ qua primitive version cho mục đích này; ID đã có giá trị |
| `null` | `long version` | `0L` | Dựa vào ID null để nhận diện mới |

Điểm khác biệt quan trọng:

```text
Primitive version = 0
    ├── Chiến lược PersistentEntity mặc định của Commons:
    │       có thể là dấu hiệu mới khi version property được dùng
    └── Nhận diện mặc định của Spring Data JPA:
            không lấy primitive version 0 làm dấu hiệu mới;
            chuyển sang xem xét ID
```

Không có một quy tắc “mọi `@Version long` bằng 0 đều mới” áp dụng cho toàn hệ sinh thái.

## 6. Ví dụ JPA với ID được ứng dụng gán và version nullable

Giả định ứng dụng đã cấu hình Spring Data JPA, provider, datasource và transaction manager. Các ví dụ JPA dùng namespace `jakarta.persistence`; mỗi kiểu public nằm trong file cùng tên.

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.util.Objects;

@Entity
@Table(name = "catalog_item")
public class CatalogItem {

    @Id
    @Column(name = "item_id", length = 64)
    private String id;

    @Version
    private Long version;

    private String name;

    protected CatalogItem() {
    }

    public CatalogItem(String id, String name) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        this.id = id;
        this.name = Objects.requireNonNull(name);
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }
}
```

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CatalogItemRepository
        extends JpaRepository<CatalogItem, String> {
}
```

Khi tạo:

```java
CatalogItem item = new CatalogItem("SKU-100", "Notebook");
CatalogItem saved = repository.save(item);
```

Trước khi lưu:

- ID đã có giá trị do ứng dụng gán.
- Version vẫn là `null`.
- Chiến lược JPA mặc định có thể nhận diện entity là mới dựa trên nullable version.

Nếu đổi `Long version` thành `long version`, giá trị mặc định trở thành `0`. Spring Data JPA không dùng primitive version làm dấu hiệu mới như trên; ID đã có giá trị sẽ ảnh hưởng đến việc chọn nhánh persistence.

Không cần tự gán `version = 1L` trước lần lưu đầu tiên. Giá trị ban đầu và cơ chế tăng version thuộc hợp đồng của provider/store.

### Version có trách nhiệm nghiệp vụ persistence riêng

`@Version` trước hết phục vụ optimistic locking. Khả năng hỗ trợ nhận diện entity mới là một phần của tích hợp, không phải lý do để thêm một field version giả mà không hiểu tác động của nó.

Nếu mô hình cần version để chống ghi đè đồng thời, nullable wrapper là một lựa chọn hữu ích trong nhiều trường hợp. Nếu không dùng version và ID luôn được gán trước, có thể cần một chiến lược nhận diện khác thay vì lạm dụng giá trị `0`.

## 7. Nhận diện trạng thái ảnh hưởng đường save, không bảo đảm một câu SQL

Ở Spring Data JPA, nhận diện entity mới thường quyết định chọn `EntityManager.persist(...)` hay `EntityManager.merge(...)`.

| Quyết định | Nhánh JPA thường được chọn | Điều chưa thể kết luận |
| --- | --- | --- |
| Mới | `persist` | Insert chắc chắn thành công hoặc SQL đã chạy ngay |
| Không mới | `merge` | Chắc chắn chỉ có một câu UPDATE |
| Chiến lược tùy chỉnh | Theo kết quả chiến lược và implementation repository | Mọi store có cùng thuật toán |

`merge` không đồng nghĩa với một lệnh SQL UPDATE trực tiếp và không phải một cơ chế upsert có ngữ nghĩa đồng nhất cho mọi tình huống. Kết quả phụ thuộc trạng thái entity, ID, version, dữ liệu thực tế và provider.

Thời điểm SQL thực thi còn liên quan đến flush và transaction. Một lỗi có thể xuất hiện khi flush hoặc commit thay vì ngay tại dòng `save`.

Ngoài ra, instance trả về từ `save` có thể khác instance đầu vào. Hãy dùng giá trị trả về khi cần tiếp tục làm việc với trạng thái đã được persistence xử lý.

Với MongoDB, JDBC hoặc module khác, đường insert/update và cơ chế version có thể khác. Cần kiểm tra hợp đồng của đúng module, không suy ra từ tên `CrudRepository.save`.

## 8. Khi ID được gán trước: Persistable diễn đạt ý định rõ hơn sentinel

Một ID như UUID hoặc mã nghiệp vụ thường có giá trị ngay khi tạo đối tượng. Nếu không có nullable version thích hợp, nhận diện chỉ theo ID có thể xem đối tượng là không mới.

`Persistable<ID>` cho phép entity cung cấp:

- `getId()`: identifier.
- `isNew()`: trạng thái mới theo hợp đồng do ứng dụng duy trì.

Ví dụ riêng cho JPA:

```java
package com.example.catalog;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import java.util.Objects;
import org.springframework.data.domain.Persistable;

@Entity
@Table(name = "assigned_id_item")
public class AssignedIdItem implements Persistable<String> {

    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    protected AssignedIdItem() {
    }

    public AssignedIdItem(String id, String name) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        this.id = id;
        this.name = Objects.requireNonNull(name);
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }

    @PostLoad
    @PostPersist
    void markNotNew() {
        this.newEntity = false;
    }
}
```

Đây là mẫu dành cho entity được JPA quản lý:

- Đối tượng mới tạo có cờ `true`, dù ID đã được gán.
- Entity được tải qua JPA được chuyển về cờ `false`.
- Sau sự kiện persist tương ứng, cờ được chuyển về `false`.
- Cờ không được ánh xạ thành cột nhờ annotation JPA phù hợp.

Không sao chép `@PostLoad` và `@PostPersist` sang module không có lifecycle JPA rồi mong cờ được cập nhật. Module khác cần cơ chế callback tương ứng hoặc một thiết kế khác.

### Không trả về true mãi mãi

```java
@Override
public boolean isNew() {
    return true;
}
```

Cách này không phải một giải pháp tổng quát cho ID gán trước. Nó có thể khiến những lần lưu sau tiếp tục đi theo đường dành cho entity mới và gây lỗi trùng định danh hoặc hành vi không phù hợp.

Ngược lại, trả về `false` ngay khi ID khác null tái tạo chính vấn đề của ID gán trước.

### Callback không đồng nghĩa với commit thành công

`@PostPersist` có thể xảy ra trước khi transaction commit. Nếu transaction rollback, object trong bộ nhớ vẫn có thể đã đổi cờ hoặc được gán thông tin persistence, dù bản ghi không được lưu bền vững.

Không tái sử dụng máy móc một instance sau lỗi persistence rồi giả định cờ của nó phản ánh chính xác cơ sở dữ liệu. Luồng retry cần quyết định rõ việc tạo lại đối tượng, tải lại trạng thái hoặc quản lý lại lifecycle.

`Persistable` cũng không tự cung cấp optimistic locking. Nếu cần chống cập nhật đồng thời, vẫn phải thiết kế cơ chế version hoặc cơ chế tương ứng của store.

## 9. Null bị biến thành 0 ở biên ứng dụng

Một chiến lược nhận diện đúng vẫn có thể nhận đầu vào sai nếu DTO hoặc mapper làm mất thông tin.

### Primitive trong DTO không phân biệt được thiếu giá trị với 0

```java
public class ItemRequest {

    private long id;

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }
}
```

Ở cấp object Java, khi field chưa được gán, `id` là `0`. Không còn một trạng thái null để biết giá trị đã được cung cấp hay chưa.

Quy tắc binding còn tùy cấu hình serializer/deserializer. Nhưng một primitive field tự nó không thể giữ thêm trạng thái “vắng giá trị”.

### Mapper có thể làm mất dấu hiệu mới

```java
Long incomingId = null;

// Đây là thay đổi ngữ nghĩa, không chỉ là đổi biểu diễn.
Long mappedId = incomingId == null ? 0L : incomingId;
```

Nếu entity đích dùng `Long`, `mappedId = 0L` không còn là trạng thái ID null. Theo chiến lược ID wrapper, entity không được nhận diện là mới chỉ dựa trên ID này.

Một default trong builder, giá trị mặc định của schema trao đổi dữ liệu hoặc thao tác copy property cũng có thể gây vấn đề tương tự.

### Tách ý định create và update

Một thiết kế API có thể tách dữ liệu tạo mới khỏi dữ liệu cập nhật:

```java
public record CreateItemRequest(String name) {
}
```

```java
public record UpdateItemRequest(Long id, String name) {

    public UpdateItemRequest {
        if (id == null) {
            throw new IllegalArgumentException("id is required for update");
        }
    }
}
```

Ví dụ này chưa áp đặt ID phải dương. Nếu domain cấm `0` hoặc số âm, hãy thêm validation theo quy tắc domain.

Với create dùng ID do store sinh, mapper không cần tự tạo ID `0L`. Với create dùng ID do ứng dụng gán, hãy chọn chiến lược nhận diện phù hợp với loại ID đó.

Đối với update, việc có ID không chứng minh bản ghi tồn tại. Luồng nghiệp vụ cần xác định rõ nếu bản ghi không tồn tại thì báo lỗi, tạo mới hay thực hiện hành vi khác.

## 10. Những trường hợp biên dễ gây kết luận sai

### 10.1. Zero là ID hợp lệ trong hệ thống nguồn

Giả sử dữ liệu nhập từ hệ thống ngoài có một bản ghi mang ID số `0`.

- Nếu Java dùng `long` và chiến lược ID coi zero là mới, trạng thái này bị nhập nhằng với chưa được cấp ID.
- Nếu Java dùng `Long`, giá trị `0L` khác null và có thể biểu diễn ID đã hiện diện.
- Nếu muốn insert một đối tượng có ID gán trước bằng zero, chỉ đổi sang wrapper chưa đủ: cần giải quyết cả nhận diện trạng thái mới.

Không sửa dữ liệu nguồn từ `0` thành `1` chỉ để phù hợp một sentinel chưa được thiết kế rõ.

### 10.2. Wrapper version bằng 0 sau lần lưu đầu tiên

Một version wrapper có thể mang giá trị `0` sau khi được persistence khởi tạo. Điều quan trọng với chiến lược nullable-version là nó đã khác null.

Không kiểm tra:

```java
// Không dùng như quy tắc tổng quát:
boolean fresh = version == null || version == 0L;
```

Cách này có thể đánh đồng phiên bản ban đầu hợp lệ của entity đã lưu với entity chưa lưu.

### 10.3. Bản sao giữ ID nhưng làm mất version

Một mapper tạo bản sao từ entity đã có ID nhưng bỏ version có thể tạo ra tổ hợp:

```text
ID: có giá trị
Version wrapper: null
```

Với chiến lược ưu tiên nullable version, đối tượng có thể bị nhận diện là mới. Nếu mục đích là cập nhật entity hiện có, đây có thể là một lỗi nghiêm trọng trong mapping đầu vào.

Đối với luồng update JPA, tải entity rồi áp dụng thay đổi được cho phép thường giúp giữ rõ identity và trạng thái quản lý. Nếu dùng detached entity hoặc DTO chứa version, cần thiết kế và kiểm tra riêng hợp đồng đó.

### 10.4. ID và version được gán trước rollback

Một đối tượng đã đi qua một phần quá trình lưu có thể giữ ID hoặc version dù transaction cuối cùng thất bại. Nhận diện trạng thái ở lần gọi tiếp theo vẫn đọc giá trị trong bộ nhớ, không tự biết lịch sử rollback.

Đây là lý do cần kiểm tra cả luồng lỗi và retry, thay vì chỉ kiểm tra lần insert thành công.

### 10.5. EXISTS trước SAVE vẫn có race condition

Đọc `existsById` để quyết định tạo hay cập nhật không biến hai thao tác thành một phép quyết định nguyên tử. Một transaction khác có thể thay đổi dữ liệu giữa hai bước.

Ràng buộc duy nhất, optimistic locking và các thao tác nguyên tử của store vẫn cần được sử dụng theo yêu cầu nghiệp vụ.

## 11. Cách phân tích một entity cụ thể

Có thể làm theo trình tự:

1. **Xác định module.** Đây là JPA, JDBC, MongoDB hay repository tùy chỉnh?
2. **Xác định chiến lược.** Có triển khai `Persistable` hoặc cấu hình nhận diện khác không?
3. **Kiểm tra metadata được nhận diện.** ID và version là property nào? Annotation thuộc package nào?
4. **Kiểm tra kiểu khai báo.** `long` khác `Long`; kiểu version có thể quan trọng hơn kiểu ID.
5. **Đọc giá trị ngay trước save.** Đừng chỉ xem giá trị sau constructor nếu mapper hoặc callback còn thay đổi nó.
6. **Áp dụng đúng thứ tự của module.** Có ưu tiên version không? Primitive version có bị bỏ qua cho mục đích nhận diện không?
7. **Phân biệt quyết định với kết quả.** Nhánh persistence được chọn chưa phải bằng chứng dữ liệu đã commit.

Ví dụ ghi chép phục vụ phân tích:

```text
Module: Spring Data JPA
Persistable: không
ID: String, "SKU-100"
Version: Long, null
Chiến lược: nullable version trước ID
Kết luận nhận diện: mới
Nhánh thường chọn: persist
Kết quả insert/commit: phải quan sát riêng
```

Cách ghi này hữu ích hơn một kết luận “ID đã có nên chắc chắn update”.

## 12. Ma trận kiểm chứng khi phát triển ứng dụng

Các trường hợp dưới đây là gợi ý kiểm chứng trong ứng dụng, không phải một quy tắc persistence chung cho mọi store:

| Trường hợp | Điều cần kiểm chứng |
| --- | --- |
| ID `Long = null`, không có version | Được nhận diện mới theo ID |
| ID `Long = 0L`, không có version | Khác null; không bị tự đánh đồng với primitive zero |
| ID `long = 0L`, không có version | Sentinel zero được chiến lược ID áp dụng như dự kiến |
| ID gán trước, version `Long = null` | Chiến lược ưu tiên version nhận diện mới |
| ID gán trước, version `Long = 0L` | Wrapper zero không bị coi là null |
| JPA với version `long = 0L` | Nhận diện chuyển sang xem xét ID theo quy tắc JPA |
| Entity triển khai `Persistable` | Kết quả `isNew()` thực sự điều khiển nhận diện |
| Entity được tải lại | ID, version hoặc cờ lifecycle thể hiện trạng thái sau load đúng |
| Lưu thất bại rồi retry | Không dùng nhầm trạng thái trong bộ nhớ sau rollback |
| Mapper nhận ID/version thiếu | Không tự thay null bằng zero làm đổi ý nghĩa |

Nếu kiểm chứng tích hợp, nên quan sát cả đường persistence, kết quả store và thời điểm lỗi xuất hiện. Một kiểm tra chỉ so sánh giá trị `id == 0` không xác nhận repository đang dùng đúng chiến lược.

Không buộc mọi phép kiểm chứng vào số lượng chính xác câu SQL nếu đó không phải yêu cầu cần bảo đảm. Provider có thể có thêm truy vấn hoặc tối ưu khác mà vẫn giữ đúng hành vi.

## 13. Lựa chọn kiểu dữ liệu có chủ đích

| Nhu cầu | Lựa chọn thường phù hợp | Điều phải giữ |
| --- | --- | --- |
| ID do store sinh, cần biểu diễn chưa có ID | Wrapper như `Long` | Giữ null trước khi được cấp ID |
| Primitive ID theo quy ước zero là chưa gán | `long` | Chấp nhận rằng zero không còn là giá trị ID có thể phân biệt độc lập theo chiến lược đó |
| ID do ứng dụng gán từ đầu | Kiểu ID theo domain | Dùng version hoặc chiến lược new-state phù hợp |
| Version cần trạng thái chưa được persistence khởi tạo | Wrapper version | Không tự thay null bằng zero |
| Entity JPA dùng primitive version | Theo nhu cầu mapping JPA | Không dùng primitive version zero để suy ra entity mới |
| API cần phân biệt thiếu dữ liệu với zero | Wrapper hoặc cấu trúc biểu diễn ý định rõ | Giữ thông tin qua DTO, validation và mapper |

Lựa chọn primitive hay wrapper cần đi cùng hợp đồng nhận diện trạng thái. Một kiểu bao không tự giải quyết mọi trường hợp nếu ứng dụng vẫn khởi tạo nó bằng zero; một primitive không sai nếu sentinel zero là quy ước phù hợp và đã được kiểm chứng.

Điều cần nhớ khi đọc metadata hoặc gọi repository là: `null`, `0` và “bản ghi chưa tồn tại” là ba khái niệm khác nhau. Chiến lược của module quyết định cách liên hệ chúng, còn ứng dụng phải giữ nhất quán ý nghĩa đó từ dữ liệu đầu vào đến transaction lưu trữ.
