# Đánh dấu thuộc tính hỗ trợ isNew bằng @Transient khi cần

Trong chương **Phát hiện trạng thái** của Spring Data Commons, một entity có thể triển khai `Persistable<ID>` để tự cung cấp kết quả `isNew()`. Khi dùng một cờ hỗ trợ như `newEntity`, cần phân biệt trạng thái điều khiển persistence với dữ liệu nghiệp vụ cần lưu.

`@Transient` giúp loại thuộc tính hỗ trợ khỏi mapping của hạ tầng Spring Data có nhận diện annotation đó. Nó không tự tính toán trạng thái mới, không tự đổi cờ sau khi lưu và không thay thế các callback vòng đời của module.

Điểm dễ nhầm nhất xuất hiện khi dùng property access: phương thức `isNew()` cũng có hình dạng một getter boolean. Nếu không thể hiện rõ ý định loại khỏi persistence, nó có thể được phát hiện như một thuộc tính để lưu thay vì chỉ là phương thức phục vụ chiến lược nhận diện trạng thái.

Bài học tập trung vào abstraction của Commons, sau đó dùng Spring Data MongoDB để minh họa một vòng đời hoàn chỉnh. Phần so sánh JPA được tách rõ vì annotation và cơ chế callback của JPA khác với hạ tầng mapping trực tiếp của Commons.

## 1. Persistable công bố trạng thái mới như thế nào?

Hợp đồng cốt lõi của `Persistable` gồm:

```java
public interface Persistable<ID> {

    ID getId();

    boolean isNew();
}
```

Trong module và đường repository có sử dụng chiến lược này, việc triển khai `Persistable` cho phép Spring Data lấy thông tin mới từ `isNew()` thay vì chỉ suy luận theo giá trị ID hoặc version.

Một nhu cầu thường gặp là ID được ứng dụng gán trước lần lưu đầu:

```text
id = "product-100"
chưa có bản ghi được lưu
```

ID không null chưa thể hiện được đối tượng đã tồn tại. Entity có thể giữ một cờ trong bộ nhớ để trả lời câu hỏi đó:

```java
private boolean newEntity;

@Override
public boolean isNew() {
    return newEntity;
}
```

Từ đây xuất hiện hai trách nhiệm độc lập:

1. Đảm bảo `newEntity` phản ánh đúng vòng đời đối tượng.
2. Đảm bảo cờ hỗ trợ không vô tình trở thành một phần của dữ liệu lưu trữ.

`@Transient` giải quyết ý định của trách nhiệm thứ hai. Trách nhiệm thứ nhất vẫn cần được thiết kế riêng.

## 2. Cờ hỗ trợ không phải thuộc tính nghiệp vụ

Xét một sản phẩm có các giá trị:

| Giá trị | Ý nghĩa | Có cần lưu trong ví dụ? |
| --- | --- | --- |
| `id` | Định danh sản phẩm | Có |
| `name` | Tên sản phẩm | Có |
| `newEntity` | Cờ hỗ trợ cho chiến lược `isNew` | Không |

Cờ này không nói sản phẩm có đang ở giai đoạn “mới ra mắt” hay không. Nó cũng không phải trạng thái như `DRAFT`, `PUBLISHED` hoặc `ARCHIVED`.

Một sản phẩm đã lưu có thể vẫn ở trạng thái nghiệp vụ `DRAFT`, nhưng `isNew()` phải trả false nếu vòng đời persistence đang xem nó là đối tượng đã có.

Ngược lại, một sản phẩm mới chuẩn bị ghi có thể được tạo ngay với trạng thái nghiệp vụ `PUBLISHED`, nhưng điều đó không làm bản ghi tự tồn tại trong kho dữ liệu.

Không dùng cờ nhận diện trạng thái mới làm thuộc tính nghiệp vụ có cùng tên và ý nghĩa mơ hồ. Nếu nghiệp vụ thật sự có một thuộc tính cần lưu, hãy đặt tên riêng và giữ hợp đồng của nó độc lập với `Persistable.isNew()`.

## 3. Annotation nào được dùng?

Với cơ chế mapping Spring Data trực tiếp có hỗ trợ annotation của Commons:

```java
import org.springframework.data.annotation.Transient;
```

Ý định của annotation là loại field hoặc property tương ứng khỏi persistence mapping.

Ví dụ với field hỗ trợ:

```java
@Transient
private boolean newEntity;
```

Ví dụ với phương thức `isNew()` khi property access có thể phát hiện nó:

```java
@Override
@Transient
public boolean isNew() {
    return newEntity;
}
```

Việc đánh dấu getter transient không làm Java ngừng gọi được phương thức đó. Spring Data vẫn có thể sử dụng hợp đồng `Persistable.isNew()` để nhận diện trạng thái, trong khi thuộc tính tương ứng không được xem là dữ liệu cần ghi.

Đây là hai đường sử dụng khác nhau:

```text
Đường nhận diện trạng thái:
    gọi Persistable.isNew()

Đường ánh xạ dữ liệu:
    loại thuộc tính hỗ trợ đã được đánh dấu transient
```

Không cần biến giá trị trả về của `isNew()` thành một cột hoặc trường lưu mới để chiến lược hoạt động.

## 4. Field access và property access ảnh hưởng vị trí đặt annotation

### 4.1. Khi truy cập qua field

Nếu mapping làm việc với field hỗ trợ, cần loại đúng field đó:

```java
@Transient
private boolean newEntity;
```

Đánh dấu một getter khác không phải lúc nào cũng đủ để loại một field có tên riêng khỏi metadata mà module đang sử dụng. Cần kiểm tra cấu hình và vị trí khai báo thực tế.

### 4.2. Khi truy cập qua property

Hình dạng getter boolean của JavaBeans thường là:

```java
public boolean isSomething() {
    return something;
}
```

Theo cách đặt tên đó, `isNew()` có thể biểu thị một property tên `new`. Tên vật lý cuối cùng còn phụ thuộc naming strategy và module.

Nếu dùng property access, phải chú ý chính phương thức này:

```java
@Override
@Transient
public boolean isNew() {
    return newEntity;
}
```

Chỉ đặt annotation trên field `newEntity` không tự làm rõ mọi thuộc tính có thể được phát hiện từ getter `isNew()`, vì tên logic của field và property có thể khác nhau.

### 4.3. Khi mô hình có cả hai điểm cần loại

Trong một lớp có field `newEntity` và phương thức `isNew()`, có thể đánh dấu cả field hỗ trợ lẫn getter theo ý định rõ ràng:

```java
@Transient
private boolean newEntity;

@Override
@Transient
public boolean isNew() {
    return newEntity;
}
```

Cách này không có nghĩa phải gắn annotation lên mọi phương thức của entity. Chỉ những khai báo thực sự phục vụ trạng thái hỗ trợ và có khả năng tham gia mapping mới cần được loại.

| Điểm được mapping xem xét | Vị trí cần thể hiện ý định |
| --- | --- |
| Field hỗ trợ `newEntity` | Field đó |
| Property từ `isNew()` | Getter `isNew()` |
| Getter hỗ trợ khác, như `isNewEntity()` | Đánh giá và loại getter đó nếu không phải dữ liệu cần lưu |
| Thuộc tính nghiệp vụ thực sự | Giữ mapping theo hợp đồng nghiệp vụ, không loại chỉ vì nó là boolean |

Tránh thêm nhiều getter cho cùng một cờ nếu chúng không có mục đích rõ ràng. Mỗi accessor mới có thể tạo thêm một điểm mà hạ tầng dựa trên property cần xem xét.

## 5. @Transient không quản lý vòng đời cờ

Xét mẫu rút gọn:

```java
@Transient
private boolean newEntity = true;

@Override
public boolean isNew() {
    return newEntity;
}
```

Nếu không có cơ chế chuyển trạng thái:

- Đối tượng có thể vẫn báo mới sau khi đã lưu.
- Đối tượng đọc lại có thể được khởi tạo với cờ true.
- Lần gọi lưu tiếp theo có thể đi vào đường tạo mới ngoài ý định.

Annotation chỉ loại dữ liệu khỏi mapping. Nó không có nghĩa:

```text
sau save → tự gán false
sau load → tự gán false
```

Vòng đời mong muốn trong một mô hình dùng cờ thường là:

| Thời điểm | `isNew()` mong muốn |
| --- | --- |
| Tạo đối tượng mới trong ứng dụng | `true` |
| Đọc đối tượng đã có từ kho dữ liệu | `false` |
| Sau thao tác lưu thành công theo callback đã chọn | `false` |
| Thất bại hoặc rollback | Phải đánh giá trạng thái thực tế, không tự suy từ annotation |

Cần một factory, creator hoặc callback tương ứng để thiết lập các giá trị này. Cơ chế cụ thể phụ thuộc module lưu trữ.

## 6. Ví dụ hoàn chỉnh với Spring Data MongoDB

Ví dụ sau dùng property access để thể hiện rõ nguy cơ phát hiện `isNew()` như một thuộc tính. Ứng dụng giả định đã cấu hình MongoDB, component scanning và repository scanning cho package `com.example.catalog`.

Thiết kế vòng đời:

- Factory `create` tạo đối tượng mới với cờ true.
- Creator dùng khi đọc dữ liệu thiết lập cờ false.
- Callback sau lưu thiết lập cờ false trên kết quả thao tác.
- Field hỗ trợ và getter `isNew()` đều được loại khỏi mapping.

### 6.1. Entity có ID do ứng dụng gán

```java
package com.example.catalog;

import org.springframework.data.annotation.AccessType;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.mongodb.core.mapping.Document;

import java.util.Objects;

@Document("products")
@AccessType(AccessType.Type.PROPERTY)
public class Product implements Persistable<String> {

    private final String id;
    private String name;

    @Transient
    private boolean newEntity;

    // Đường tái tạo từ dữ liệu đã lưu.
    @PersistenceCreator
    public Product(String id, String name) {
        this(id, name, false);
    }

    // Constructor nội bộ không phải creator được chọn cho persistence.
    private Product(String id, String name, boolean newEntity) {
        this.id = Objects.requireNonNull(id, "id must not be null");
        this.name = Objects.requireNonNull(
                name, "name must not be null");
        this.newEntity = newEntity;
    }

    public static Product create(String id, String name) {
        return new Product(id, name, true);
    }

    @Override
    @Id
    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = Objects.requireNonNull(
                newName, "newName must not be null");
    }

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }

    public void markNotNew() {
        this.newEntity = false;
    }
}
```

Có ba điểm cần chú ý:

1. `newEntity` không là tham số của creator persistence. Giá trị của nó được suy từ đường tái tạo, không lấy từ một trường trong document.
2. Getter `getId()` vẫn được giữ trong mapping và được đánh dấu ID. Không loại ID chỉ vì nó cũng xuất hiện trong interface `Persistable`.
3. `markNotNew()` là hành vi đổi cờ, không phải getter property phục vụ lưu trữ.

Creator được chọn nhận đủ các giá trị persistent trong ví dụ là `id` và `name`. Tên tham số constructor cần có metadata phù hợp với cấu hình biên dịch hoặc cơ chế creator được module hỗ trợ.

### 6.2. Callback sau lưu của MongoDB

```java
package com.example.catalog;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductAfterSaveCallback
        implements AfterSaveCallback<Product> {

    @Override
    public Product onAfterSave(
            Product entity,
            Document document,
            String collection) {
        entity.markNotNew();
        return entity;
    }
}
```

Đây là callback riêng của Spring Data MongoDB cho đường đồng bộ trong ví dụ. Không chép nguyên interface callback này sang JDBC hoặc JPA và kỳ vọng cùng một cơ chế đăng ký.

Đường đọc trong ví dụ dùng creator để tạo entity với cờ false. Một thiết kế khác có thể thiết lập trạng thái sau đọc bằng callback chuyển đổi của module. Nếu chọn hướng đó, phải bảo đảm callback được đăng ký và thực sự chạy ở đường đọc đang dùng.

### 6.3. Repository và cách sử dụng

```java
package com.example.catalog;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {
}
```

Trong một service đã inject repository:

```java
Product draft = Product.create("product-100", "Spring Data Guide");

// draft.getId() != null
// draft.isNew() == true

Product saved = productRepository.save(draft);

// Với callback đã được đăng ký và chạy thành công:
// saved.isNew() == false

Product loaded = productRepository.findById(saved.getId())
        .orElseThrow();

// Creator persistence thiết lập trạng thái đối tượng đã có:
// loaded.isNew() == false

loaded.rename("Spring Data Guide - Revised");
Product updated = productRepository.save(loaded);
```

Dữ liệu mong muốn trong document gồm các thuộc tính persistent như ID và tên. Nó không cần có `newEntity` hoặc property từ `isNew()`.

Không dùng việc nhìn thấy một giá trị false trong kết quả Java làm bằng chứng duy nhất rằng cờ đã được loại khỏi document. Cần kiểm tra cả mapping và dữ liệu thực tế khi tích hợp.

## 7. Callback sau lưu không đồng nghĩa sau commit

Trong ví dụ, callback đổi cờ sau khi module xử lý thao tác lưu tương ứng. Nếu thao tác đang ở trong một transaction lớn hơn, thời điểm đó không tự đồng nghĩa transaction đã commit.

Có thể xảy ra chuỗi:

```text
entity báo mới
→ thao tác ghi chạy
→ callback đổi cờ thành false
→ một bước khác gây lỗi
→ transaction rollback
```

Đối tượng Java vẫn có thể giữ cờ false dù transaction không tạo được bản ghi bền vững. `@Transient` không làm thay đổi trong bộ nhớ tự rollback cùng cơ sở dữ liệu.

Không tái sử dụng một entity từ transaction thất bại rồi mặc định cờ còn đúng. Khi retry, cần tái tạo hoặc đọc lại trạng thái theo hợp đồng của ca sử dụng và tình trạng dữ liệu thực tế.

Ngược lại, nếu thao tác thất bại trước khi callback sau lưu chạy, callback đó chưa có cơ hội chuyển cờ. Điều này vẫn không đủ để kết luận mọi dạng lỗi mạng hoặc lỗi xác nhận ghi đều bảo đảm chưa có dữ liệu được ghi.

Cờ trong bộ nhớ là một phần của chiến lược nhận diện đối tượng; nó không phải nhật ký commit phân tán hoặc bằng chứng chắc chắn về kết quả của một lần ghi chưa xác định.

## 8. Tránh yêu cầu persistence cung cấp một thuộc tính đã loại

Một cấu hình dễ mâu thuẫn là:

```java
@Transient
private boolean newEntity;

@PersistenceCreator
public Product(String id, String name, boolean newEntity) {
    // ...
}
```

Nếu `newEntity` không thuộc dữ liệu persistent, không nên mặc định bộ ánh xạ sẽ tìm được một giá trị lưu để truyền vào tham số đó. Chỉ đánh dấu field transient không tự tạo một nguồn giá trị thay thế cho constructor.

Trong ví dụ hoàn chỉnh, constructor có ba tham số vẫn tồn tại nhưng là đường nội bộ; creator được chọn chỉ nhận `id` và `name`, rồi tự xác định false cho đối tượng đọc lại.

Khi thiết kế immutable entity hoặc factory, giữ rõ hai nguồn thông tin:

```text
Thông tin lấy từ dữ liệu lưu:
    id, name, các thuộc tính nghiệp vụ

Thông tin suy từ đường tạo đối tượng:
    đây là đối tượng mới do ứng dụng tạo
    hay đối tượng được khôi phục từ kho dữ liệu
```

Nếu thực sự cần một giá trị hỗ trợ được tính bởi cơ chế đặc biệt của module, phải cấu hình nguồn giá trị đó rõ ràng. Không xem `@Transient` là cơ chế cấp giá trị constructor.

## 9. JPA dùng annotation và callback của JPA

Đối với entity JPA, thuộc tính không lưu thường dùng:

```java
import jakarta.persistence.Transient;
```

Không mặc định rằng `org.springframework.data.annotation.Transient` thay thế annotation JPA cho entity do JPA provider quản lý.

Ví dụ rút gọn cho một entity JPA dùng field access:

```java
package com.example.catalog;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Transient;
import org.springframework.data.domain.Persistable;

@Entity
public class JpaProduct implements Persistable<String> {

    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    protected JpaProduct() {
    }

    public JpaProduct(String id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
```

Trong ví dụ này, `@Id` đặt trên field xác định hướng field access theo mapping JPA thông thường. Annotation transient trên field loại cờ khỏi dữ liệu lưu; annotation trên `isNew()` cũng biểu đạt rõ đây là phương thức hỗ trợ, không phải dữ liệu nghiệp vụ.

`@PostLoad` xử lý đối tượng được JPA provider đọc lại; `@PostPersist` chuyển cờ sau bước persist tương ứng. Cả hai đều không phải một cam kết rằng mọi transaction bao quanh đã commit. Lưu ý về rollback và tái sử dụng đối tượng vẫn còn nguyên.

Nếu entity JPA dùng property access, vị trí annotation phải được thiết kế nhất quán theo quy tắc JPA. `jakarta.persistence.Access` và `org.springframework.data.annotation.AccessType` là những cơ chế thuộc hai ngữ cảnh khác nhau; không thay thế chúng chỉ vì tên gần giống.

## 10. Phân biệt với transient của Java và JSON serialization

Có ba câu hỏi khác nhau:

1. Thuộc tính có được lưu trong kho dữ liệu không?
2. Thuộc tính có tham gia Java serialization không?
3. Thuộc tính có xuất hiện trong JSON của API không?

| Cơ chế | Mục tiêu chính |
| --- | --- |
| `org.springframework.data.annotation.Transient` | Mapping của hạ tầng Spring Data có hỗ trợ |
| `jakarta.persistence.Transient` | Persistence mapping của JPA |
| Từ khóa Java `transient` | Java serialization; framework mapping có thể có quy tắc riêng |
| Cấu hình hoặc annotation JSON tương ứng | JSON serialization/deserialization theo thư viện đang dùng |

Đánh dấu một thuộc tính transient cho persistence không nên được dùng làm hợp đồng rằng mọi thư viện JSON đều sẽ ẩn nó. Một getter `isNew()` vẫn cần được đánh giá riêng trong thiết kế DTO hoặc cấu hình JSON nếu API không muốn công bố thông tin đó.

Tương tự, một cờ không xuất hiện trong JSON chưa chứng minh nó không được ghi vào cơ sở dữ liệu. Mỗi đường cần đúng cơ chế cấu hình của nó.

## 11. Khi không cần thêm cờ isNew

Không phải entity nào cũng cần triển khai `Persistable` và giữ một boolean riêng. Các chiến lược mặc định dựa trên ID hoặc version có thể đã diễn đạt đúng vòng đời.

Ví dụ, ở module dùng một thuộc tính version boxed làm dấu hiệu mới, version null có thể phân biệt đối tượng chưa lưu với đối tượng đã có ngay cả khi ID được ứng dụng gán trước.

Nếu đã dùng một chiến lược đơn giản như vậy và nó đáp ứng yêu cầu, thêm cờ riêng tạo thêm trách nhiệm:

- Cập nhật cờ sau lưu.
- Khôi phục đúng trạng thái sau đọc.
- Giữ cờ đúng khi tạo bản sao hoặc retry.
- Loại cờ khỏi mapping ở đúng vị trí.

Chỉ thêm cơ chế tùy biến khi có lý do cụ thể. Khi `Persistable` đã được chọn, cũng không được giả định một version null sẽ tự sửa kết quả của `isNew()` nếu implementation của phương thức đó đang trả sai.

Loại cờ bằng `@Transient` không tắt optimistic locking. Ngược lại, việc có một cờ `isNew` không tự bổ sung kiểm tra version cho mô hình chưa có cơ chế concurrency phù hợp.

## 12. DTO, sao chép đối tượng và các đường tạo khác

Một mô hình dùng cờ có thể đúng ở repository nhưng sai ở một mapper hoặc factory khác:

```text
Đọc entity đã có
→ chuyển sang DTO
→ dựng lại bằng factory create(...)
→ cờ true
→ lưu lại như đối tượng mới
```

`@Transient` không ngăn lỗi này vì nó không quyết định factory nào được gọi.

Cần phân biệt đường tạo mới và đường xử lý cập nhật trong service. Khi cập nhật một entity đã tồn tại, có thể đọc entity rồi áp dụng thay đổi, hoặc dùng một đường khôi phục được thiết kế đầy đủ metadata cần thiết.

Nếu cần phát hiện client đang dùng dữ liệu cũ, vẫn phải có hợp đồng concurrency riêng, chẳng hạn expected version. Cờ `isNew` chỉ phân biệt ý định trạng thái mới và đã có; nó không thay thế điều kiện kiểm tra dữ liệu cũ.

Với bản sao immutable, phương thức tạo bản sao cũng phải giữ hoặc chuyển cờ đúng ý định. Một lần đổi tên không nên vô tình biến một entity đã lưu thành một entity mới chỉ vì constructor mặc định luôn gán true.

## 13. Triệu chứng và cách chẩn đoán

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Document hoặc bảng có thuộc tính `newEntity` ngoài dự kiến | Field hỗ trợ chưa bị loại khỏi mapping |
| Xuất hiện thuộc tính từ getter `isNew()` | Property access đang phát hiện getter chưa được loại |
| Vừa lưu xong vẫn báo mới | Callback chuyển trạng thái chưa có, chưa đăng ký hoặc không chạy ở đường dùng |
| Đọc lại rồi lưu gặp lỗi ID trùng | Đường đọc khởi tạo cờ true, dẫn tới nhận diện mới sai |
| Creator báo thiếu tham số hỗ trợ | Constructor đang đòi giá trị cho thuộc tính đã loại khỏi persistence |
| Entity JPA vẫn cố lưu cờ | Sai import, sai access strategy hoặc annotation đặt sai khai báo |
| Retry sau rollback có trạng thái lạ | Cờ trong bộ nhớ đã đổi nhưng transaction không commit |

Không chỉ chữa triệu chứng bằng cách luôn trả false từ `isNew()`. Cách đó có thể phá đường tạo mới khi ID được gán trước.

Cũng không ép true để giải quyết mọi lỗi cập nhật. Nhận diện mới sai có thể dẫn tới lỗi duplicate key hoặc một đường ghi khác với hợp đồng cần thiết. Hành vi cụ thể phụ thuộc module; false không đồng nghĩa mọi module đều chạy đúng một câu `UPDATE` không có lựa chọn khác.

## 14. Cách kiểm chứng khi tích hợp

Cần kiểm chứng cả mapping lẫn vòng đời:

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Tạo mới bằng factory ứng dụng | `isNew()` là true |
| Lưu qua repository với callback phù hợp | Kết quả trả về được chuyển sang trạng thái đã có |
| Đọc lại từ kho dữ liệu | `isNew()` là false |
| Kiểm tra biểu diễn lưu trữ | Không có field hỗ trợ hoặc property từ `isNew()` ngoài hợp đồng |
| Cập nhật tên rồi lưu lại | Không vô tình đi theo đường tạo mới |
| Chuyển từ field access sang property access | Thuộc tính hỗ trợ vẫn bị loại đúng ý định |
| Transaction rollback | Service không dùng lại cờ trong bộ nhớ như bằng chứng đã commit |
| Mapper dựng lại entity | Giữ đúng ý nghĩa tạo mới hoặc cập nhật |

Một unit test trực tiếp gọi `isNew()` chỉ chứng minh phương thức trả về cờ hiện tại. Nó không chứng minh annotation đã được module nhận diện, callback đã được gọi hoặc dữ liệu lưu không có thuộc tính thừa.

Khi đã từng lưu cờ nhầm, thêm `@Transient` không tự xóa trường cũ khỏi mọi bản ghi. Việc dọn schema hoặc dữ liệu cần được xử lý riêng theo kho dữ liệu và yêu cầu tương thích của ứng dụng.

## 15. Bài tập áp dụng

Một entity `CustomerProfile` triển khai `Persistable<String>`, có field `boolean newProfile = true` và dùng property access. Lớp đã đánh dấu field `newProfile` bằng annotation transient của Commons nhưng chưa đánh dấu `isNew()`. Sau khi đọc lại từ kho dữ liệu, cờ vẫn là true.

Hãy xác định hai vấn đề độc lập và cách sửa:

1. Về mapping, getter `isNew()` vẫn có thể được phát hiện như một property hỗ trợ cần loại.
2. Về vòng đời, không có cơ chế thiết lập trạng thái đã có sau đọc.

Một hướng xử lý là đánh dấu đúng cả field hỗ trợ và getter theo metadata thực tế, sau đó dùng creator hoặc callback phù hợp để đánh dấu đối tượng đã đọc là không mới. Bổ sung cơ chế sau lưu nếu mô hình cần chuyển cờ ở đối tượng được lưu thành công.

Cuối cùng, kiểm tra rằng các thao tác tạo mới, đọc lại và cập nhật đều giữ đúng hợp đồng, đồng thời dữ liệu lưu không chứa thuộc tính hỗ trợ. **Loại khỏi mapping và quản lý đúng trạng thái là hai trách nhiệm riêng; @Transient chỉ làm rõ trách nhiệm thứ nhất.**