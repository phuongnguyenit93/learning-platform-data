# Tách dữ liệu đọc khỏi đầu vào ghi để tránh lưu entity thiếu dữ liệu

Một DTO danh sách sản phẩm chỉ có `id`, `name` và `price` là một kết quả đọc hợp lý. Nhưng nếu dùng ba giá trị đó để dựng lại entity rồi gọi `save`, ứng dụng có thể gửi một trạng thái thiếu `sku`, `tenantId`, mô tả, tồn kho hoặc metadata xuống kho dữ liệu.

Lỗi nằm ở việc coi dữ liệu đã được rút gọn để đọc là một trạng thái đầy đủ để ghi. Projection động làm việc chọn hình dạng kết quả linh hoạt hơn, nhưng không cung cấp ngữ nghĩa cập nhật từng phần và không khôi phục các thuộc tính chưa được đọc.

Trong Spring Data Commons, cần tách hợp đồng projection, hợp đồng lệnh ghi và hợp đồng repository. Cách lưu cuối cùng phụ thuộc module và store: JPA có persistence context, merge và dirty checking; các kho khác có cơ chế update, replacement hoặc thao tác từng trường riêng.

Sau bài học, bạn có thể:

- Giải thích vì sao projection và DTO đọc không nên được dùng như entity đầy đủ để lưu.
- Thiết kế kiểu đầu vào ghi chỉ biểu diễn ý định được phép thực hiện.
- Cập nhật entity trong transaction mà vẫn giữ các thuộc tính ngoài phạm vi lệnh.
- Phân biệt trường không được gửi, trường được gửi với null và giá trị mặc định của Java.
- Kết hợp kiểm tra version, quy tắc nghiệp vụ và auditing theo đúng cơ chế store.
- Kiểm chứng dữ liệu đã lưu lại thay vì chỉ kiểm tra DTO trả về.

## 1. Ba loại dữ liệu có trách nhiệm khác nhau

Giả sử domain sản phẩm có các thuộc tính:

| Thuộc tính | Vai trò |
|---|---|
| `id` | Định danh |
| `tenantId` | Phạm vi sở hữu dữ liệu |
| `sku` | Mã sản phẩm có quy tắc riêng |
| `name`, `price` | Thông tin danh mục có thể được sửa qua một use case |
| `description` | Nội dung tùy chọn, có thể lớn |
| `stock` | Tồn kho, được thay đổi bởi use case kho hàng |
| `active` | Trạng thái theo quy trình nghiệp vụ |
| `version` | Kiểm soát cập nhật đồng thời nếu store/mapping hỗ trợ |
| Metadata auditing | Thông tin tạo và sửa theo cấu hình |

Từ cùng một domain có thể có ba kiểu dữ liệu:

| Loại | Mục đích | Có nên chứa mọi thuộc tính không? |
|---|---|---|
| DTO/projection đọc | Trả đúng dữ liệu cần hiển thị hoặc xử lý | Thường chỉ chứa một phần |
| Command/DTO ghi | Mô tả một hành động hợp lệ của người dùng hoặc hệ thống | Chỉ chứa đầu vào của hành động đó |
| Entity/document lưu trữ | Biểu diễn trạng thái theo mapping của module | Tuân theo mô hình lưu trữ và vòng đời của store |

Ví dụ, lệnh sửa tên và giá không cần nhận tồn kho, tenant hay ngày tạo từ client. Những thuộc tính đó có thể vẫn tồn tại trong entity và phải được giữ theo quy tắc tương ứng.

Tách kiểu dữ liệu giúp người đọc code nhận ra ranh giới này. Tuy nhiên, đặt tên khác nhau chưa đủ: service và mapper vẫn phải thực hiện đúng ngữ nghĩa cập nhật.

## 2. Projection động chỉ lựa chọn hình dạng đọc

### 2.1. DTO đọc bằng record

Ví dụ dùng Java record:

```java
import java.math.BigDecimal;

public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {}
```

Một DTO chi tiết hơn:

```java
import java.math.BigDecimal;

public record ProductDetails(
    Long id,
    String sku,
    String name,
    BigDecimal price,
    String description,
    boolean active,
    Long version
) {}
```

Các record là ví dụ class-based projection. Việc khởi tạo chúng từ query phụ thuộc module, constructor và mapping được hỗ trợ. Không chỉ thay một kiểu trả về là mọi query tùy ý sẽ tự ánh xạ được.

### 2.2. Repository minh họa trong Spring Data JPA

Giả sử `Product` là entity JPA có các thuộc tính như bảng ở phần trước, đã được ánh xạ và repository scanning đã được cấu hình:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {

    <T> List<T> findFirst50ByTenantIdOrderByIdAsc(
        String tenantId,
        Class<T> projectionType
    );

    <T> Optional<T> findProjectedByTenantIdAndId(
        String tenantId,
        Long id,
        Class<T> projectionType
    );

    Optional<Product> findByTenantIdAndId(
        String tenantId,
        Long id
    );
}
```

Sử dụng các hình dạng đọc:

```java
List<ProductSummary> rows = repository
    .findFirst50ByTenantIdOrderByIdAsc(
        tenantId,
        ProductSummary.class
    );

ProductDetails details = repository
    .findProjectedByTenantIdAndId(
        tenantId,
        productId,
        ProductDetails.class
    )
    .orElseThrow();
```

Tham số `Class<T>` cho phép lựa chọn kiểu projection theo hợp đồng phương thức. Nó không mang ý nghĩa “đối tượng được trả về có thể dùng làm đầu vào save”.

Ứng dụng nên chọn các kiểu đọc mà use case cho phép. Không coi tên class do client gửi lên là cơ chế phân quyền hoặc một hợp đồng cập nhật.

### 2.3. Dữ liệu không xuất hiện trong DTO không có nghĩa là null ở store

`ProductSummary` không có `description`. Vì vậy, từ một instance của record này, ứng dụng không biết mô tả hiện tại là null, chuỗi rỗng hay nội dung dài.

Tương tự, DTO không có `stock` không có nghĩa tồn kho bằng 0. Không có `active` không có nghĩa sản phẩm phải bị vô hiệu hóa.

Đó là thiếu thông tin trong hình dạng đọc, không phải một chỉ thị thay đổi dữ liệu.

## 3. Vì sao dựng entity từ DTO đọc rồi save có thể nguy hiểm?

### 3.1. Một anti-pattern điển hình

Đoạn mã sau minh họa trên một entity có setter:

```java
Product partial = new Product();
partial.setId(summary.id());
partial.setName(summary.name());
partial.setPrice(summary.price());

repository.save(partial);
```

Các thuộc tính còn lại nhận giá trị mặc định của đối tượng mới hoặc giá trị do constructor thiết lập. Chúng không tự được lấy từ bản ghi đã tồn tại.

Nếu hạ tầng coi đối tượng là trạng thái của một entity hiện có, những giá trị thiếu đó có thể tham gia quá trình cập nhật. Nếu hạ tầng coi nó là entity mới, thao tác có thể trở thành insert hoặc thất bại vì trùng định danh/ràng buộc. Cả hai đều khác ý định “chỉ sửa tên và giá”.

### 3.2. `save` không phải hợp đồng patch chung

`CrudRepository.save` không định nghĩa một quy tắc chung rằng thuộc tính null sẽ được bỏ qua hoặc thuộc tính không gán sẽ giữ nguyên trong store.

| Cơ chế | Điều cần hiểu |
|---|---|
| JPA `persist` | Áp dụng cho entity được nhận diện là mới theo cơ chế repository/provider |
| JPA `merge` | Có thể sao chép trạng thái của đối tượng detached sang instance được quản lý |
| Lưu document | Có thể ghi trạng thái document theo mapping, thay vì chỉ những trường người dùng có ý sửa |
| Update theo từng field | Có tập trường, điều kiện và ngữ nghĩa riêng của thao tác update |

Không suy rằng “có id thì chắc chắn chỉ update vài field”. Cơ chế nhận diện mới/cũ còn có thể liên quan version, `Persistable` hoặc cấu hình của module.

Trong JPA, cần phân biệt một thuộc tính lazy mà provider biết là chưa được fetch với một thuộc tính null trên entity tự dựng. Chúng không phải cùng một dạng trạng thái. Không thể tái tạo dấu vết quản lý của ORM chỉ bằng cách bỏ gán một setter.

### 3.3. Giá trị mặc định có thể trông hợp lệ

Một DTO hoặc entity có trường primitive có thể mang `0` hoặc `false` dù đầu vào không gửi gì. Các giá trị này đôi khi vẫn hợp lệ về kiểu và vượt qua kiểm tra null.

Ví dụ, vô tình gán `stock = 0` nguy hiểm hơn một lỗi dễ nhận ra khi thiếu giá. Vì vậy, cần xác định thuộc tính nào lệnh ghi thực sự sở hữu và không sao chép giá trị ngoài phạm vi đó.

### 3.4. Chỉ thêm annotation tối ưu SQL không khôi phục thông tin đã mất

Một cơ chế như dynamic update của ORM có thể thay đổi cột được đưa vào SQL theo trạng thái dirty mà provider theo dõi. Nó không biết rằng null từ một đối tượng tự dựng có nghĩa “không được đọc” hay “không có ý sửa”.

Nếu quá trình merge hoặc mapper đã biến giá trị thiếu thành một thay đổi thực sự, tối ưu SQL không tự sửa lại ý định nghiệp vụ. Cần giải quyết tại hợp đồng đầu vào và cách cập nhật.

## 4. Thiết kế command cho một hành động ghi cụ thể

Giả sử use case chỉ sửa tên và giá. Có thể định nghĩa:

```java
import java.math.BigDecimal;

public record ChangeProductInfo(
    String name,
    BigDecimal price,
    Long expectedVersion
) {
    public ChangeProductInfo {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm bắt buộc");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Giá phải không âm");
        }
        if (expectedVersion == null) {
            throw new IllegalArgumentException("Version bắt buộc");
        }
    }
}
```

Đây là command của một hành động, không phải trạng thái thay thế toàn bộ sản phẩm. Trong hệ thống thực tế, có thể dùng Bean Validation hoặc cơ chế kiểm tra đầu vào tương ứng, đồng thời giữ quy tắc domain ở nơi phù hợp.

Command không nhận `tenantId`, `stock`, `active` hoặc metadata auditing chỉ vì các thuộc tính đó có trong entity. Định danh và phạm vi thao tác có thể được truyền riêng từ đường request và ngữ cảnh đã kiểm tra quyền.

`expectedVersion` biểu diễn phiên bản mà bên gửi dựa vào khi sửa. Nó không phải yêu cầu gán trực tiếp version của entity sang giá trị client cung cấp.

### 4.1. Tách create, thay đổi và chuyển trạng thái

Các lệnh có thể khác nhau:

```text
CreateProduct
ChangeProductInfo
ChangeProductDescription
AdjustStock
ActivateProduct
```

Mỗi lệnh có dữ liệu bắt buộc, quyền và quy tắc riêng. Không cần tạo một command khổng lồ chứa mọi trường để rồi đoán trường nào đang có ý nghĩa trong từng endpoint.

Một API có thể dùng PUT hoặc PATCH theo hợp đồng tài nguyên đã định nghĩa, nhưng không được đồng nhất phương thức HTTP với hành vi mặc định của `save`. Service vẫn phải chuyển đầu vào thành các thay đổi domain rõ ràng.

## 5. Ví dụ JPA: tải entity trong transaction và sửa đúng thuộc tính

### 5.1. Đặt quy tắc cập nhật ở domain

Phần hành vi sau thuộc entity `Product` trong ví dụ:

```java
public void changeCatalogInfo(String newName, BigDecimal newPrice) {
    if (newName == null || newName.isBlank()) {
        throw new IllegalArgumentException("Tên sản phẩm bắt buộc");
    }
    if (newPrice == null || newPrice.signum() < 0) {
        throw new IllegalArgumentException("Giá phải không âm");
    }

    this.name = newName.strip();
    this.price = newPrice;
}
```

Entity có một thuộc tính version được JPA quản lý, ví dụ:

```java
@jakarta.persistence.Version
private Long version;
```

Đây là annotation của JPA. Với store khác, cần dùng cơ chế và annotation version tương ứng, không sao chép mapping JPA một cách máy móc.

### 5.2. Service quản lý ranh giới ghi

```java
import java.util.Objects;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;

    public ProductCommandService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ProductDetails changeInfo(
            String tenantId,
            Long productId,
            ChangeProductInfo command) {

        Product product = repository
            .findByTenantIdAndId(tenantId, productId)
            .orElseThrow();

        if (!Objects.equals(
                product.getVersion(),
                command.expectedVersion())) {
            throw new OptimisticLockingFailureException(
                "Sản phẩm đã thay đổi"
            );
        }

        product.changeCatalogInfo(command.name(), command.price());

        repository.flush();

        return new ProductDetails(
            product.getId(),
            product.getSku(),
            product.getName(),
            product.getPrice(),
            product.getDescription(),
            product.isActive(),
            product.getVersion()
        );
    }
}
```

Ví dụ giả định service được gọi qua Spring proxy, transaction manager JPA phù hợp đã được cấu hình và entity có các getter nêu trên. Việc chuyển lỗi không tìm thấy hoặc xung đột sang response thuộc tầng API.

Các thuộc tính ngoài lệnh không bị dựng lại từ một DTO thiếu trường. Entity được tải trong transaction, sau đó chỉ hành vi sửa tên và giá được gọi.

### 5.3. Vì sao ví dụ không gọi save?

Trong trường hợp JPA này, entity được quản lý bởi persistence context trong transaction hiện tại. Thay đổi được provider theo dõi và đồng bộ khi flush/commit; không cần dựng một entity khác để lưu lại.

`flush()` trong ví dụ chủ động đồng bộ thay đổi trước khi tạo DTO kết quả, để quan sát lỗi và version sau bước đồng bộ theo cơ chế provider. Flush không phải commit: transaction vẫn có thể rollback hoặc thất bại ở bước kết thúc.

Việc không cần save ở đây là hệ quả của vòng đời entity JPA được quản lý. Với repository của store khác, có thể cần save hoặc một thao tác update tường minh; phải dùng đúng hợp đồng của module.

Cách này cũng không yêu cầu eager-load mọi quan hệ trong toàn bộ object graph. Điều quan trọng là entity và phần trạng thái cần thiết được quản lý đúng, thay vì tự tạo một bản thay thế từ dữ liệu đọc đã rút gọn.

### 5.4. Hai lớp kiểm soát version

So sánh `expectedVersion` với version hiện tại phát hiện bên gửi đang sửa từ một bản đọc cũ. Sau đó, cơ chế `@Version` của JPA tiếp tục bảo vệ tình huống một transaction khác cập nhật sau lúc service đã đọc.

Chỉ so sánh version trong Java rồi update không có điều kiện tương ứng tại store vẫn có thể gặp race condition. Ngược lại, nếu bỏ thông tin version mà client đã đọc, việc tải bản mới rồi ghi đè có thể không nhận ra ý định của client đã dựa trên dữ liệu cũ.

Không gán version do client gửi vào entity để “làm khớp”. Version là dữ liệu dùng để kiểm tra điều kiện, còn tiến trình cập nhật version phải theo cơ chế đã chọn.

## 6. Cập nhật từng phần phải giữ được ý nghĩa của “không gửi”

### 6.1. Ba trạng thái khác nhau

Với một trường tùy chọn như `description`, hợp đồng patch có thể quy định:

| Đầu vào | Ý nghĩa |
|---|---|
| Không có trường `description` | Giữ nguyên mô tả hiện có |
| Có trường với giá trị null | Xóa mô tả nếu nghiệp vụ cho phép |
| Có trường với giá trị chuỗi | Thay mô tả bằng chuỗi đã kiểm tra |

Với trường bắt buộc như tên sản phẩm, trường được gửi với null có thể phải bị từ chối. Không dùng một quy tắc “null luôn là giữ nguyên” cho mọi thuộc tính và mọi hành động.

DTO đọc bị thiếu getter không thuộc ba trạng thái của một lệnh patch. Nó chỉ biểu diễn hình dạng đọc đã được chọn; không được dùng việc thiếu dữ liệu đó để suy ý định ghi.

### 6.2. Một kiểu nội bộ để giữ thông tin hiện diện

Có thể dùng một kiểu như sau để biểu diễn trạng thái sau khi đã parse request:

```java
public record FieldChange<T>(boolean supplied, T value) {

    public FieldChange {
        if (!supplied && value != null) {
            throw new IllegalArgumentException(
                "Trường không được gửi không mang giá trị"
            );
        }
    }

    public static <T> FieldChange<T> absent() {
        return new FieldChange<>(false, null);
    }

    public static <T> FieldChange<T> supplied(T value) {
        return new FieldChange<>(true, value);
    }
}
```

Ba giá trị nội bộ tương ứng là:

```java
FieldChange<String> keep = FieldChange.absent();
FieldChange<String> clear = FieldChange.supplied(null);
FieldChange<String> replace = FieldChange.supplied("Mô tả mới");
```

Kiểu này không tự khiến JSON binding phân biệt được absent và null. Tầng parse/adapter cần đọc sự hiện diện của field, kiểm tra kiểu dữ liệu và tạo đúng trạng thái. Command cũng cần bảo đảm đối tượng `FieldChange` không bị null ngoài hợp đồng.

Ở service, sau khi đã tải entity và kiểm tra version, có thể áp dụng:

```java
FieldChange<String> change = command.description();

if (change.supplied()) {
    product.changeDescription(change.value());
}
```

Đây là đoạn trích áp dụng patch; `command` là command riêng cho mô tả, và `changeDescription` là hành vi domain có quy tắc cho null, độ dài và nội dung.

Nếu trường absent, không gọi hành vi thay đổi mô tả. Nếu được gửi với null, domain quyết định có được xóa hay không.

### 6.3. Vì sao một số cách làm đơn giản chưa đủ?

- Một thuộc tính `String description` thông thường có thể thành null cả khi không gửi lẫn khi gửi null, tùy binding.
- `Optional<String>` theo cách dùng phổ biến không tự cung cấp đầy đủ ba trạng thái hiện diện, xóa và thay thế.
- Bỏ qua mọi giá trị null trong mapper làm khó việc xóa hợp lệ một trường tùy chọn.
- Gán mọi giá trị null vào entity có thể xóa nhầm dữ liệu không được gửi.
- Primitive như `boolean` và `int` còn có giá trị mặc định dễ bị nhầm với đầu vào thật.

Do đó, chọn một hợp đồng patch cụ thể rồi bảo toàn thông tin qua các tầng. Không dùng mapper để đoán lại điều mà tầng parse đã làm mất.

## 7. Mapper chỉ chuyển dữ liệu, không quyết định quyền sửa

### 7.1. Mapper từ read DTO sang entity không biết trạng thái còn thiếu

Một mapper có thể sinh code hợp lệ về kiểu nhưng vẫn sai về ngữ nghĩa:

```text
ProductSummary
    → tạo Product mới
    → gán id, name, price
    → các trường khác nhận mặc định
    → save
```

Đây vẫn là anti-pattern ở phần đầu, dù mapping được viết tay hay được thư viện sinh ra.

Mapper không biết `stock` cần giữ nguyên, `active` phải đổi theo quy trình hay `description` bị thiếu vì màn hình không hiển thị. Những quyết định đó thuộc hợp đồng ghi và domain.

### 7.2. Cập nhật trên đối tượng hiện có cũng cần whitelist

Mapping vào một entity đã tải có thể là một phần giải pháp, nhưng cần xác định đúng các thuộc tính mà command được phép sửa.

Ví dụ, một tiện ích copy property thường chỉ tác động lên các property tương ứng. Nó không tự xóa những property hoàn toàn không có trong nguồn, nhưng có thể gán null vào property trùng tên hoặc sao chép một giá trị ngoài phạm vi nếu DTO quá rộng.

Với use case nhỏ, gọi các phương thức domain tường minh thường dễ xem xét:

```java
product.changeCatalogInfo(command.name(), command.price());
```

Nếu dùng mapper để cập nhật đối tượng hiện có, cấu hình rõ danh sách field, chính sách null và các field bỏ qua. Không để `id`, `tenantId`, metadata tạo hoặc version do client điều khiển lọt vào một phép copy chung.

### 7.3. Collection và quan hệ cần lệnh riêng

Một DTO chi tiết có thể chỉ chứa vài phần tử của quan hệ để phục vụ hiển thị. Gán danh sách đó trở lại entity có thể bị hiểu là thay toàn bộ collection.

Với mapping có cascade hoặc orphan removal, việc thay collection có thể gây thay đổi hoặc xóa phần tử không có trong DTO. Cần phân biệt rõ:

```text
Thêm một phần tử
Xóa một phần tử theo định danh
Sửa một phần tử
Thay thế toàn bộ tập phần tử
Không tác động đến tập phần tử
```

Không dùng một danh sách đọc bị rút gọn làm lệnh thay thế toàn bộ quan hệ. Ngay cả DTO đầy đủ cho màn hình cũng có thể không chứa dữ liệu mà thao tác ghi cần kiểm tra.

## 8. Áp dụng theo đúng khả năng của từng store

### 8.1. JPA: ưu tiên entity được quản lý cho thay đổi domain

Ví dụ service ở phần trước dựa trên transaction, entity được quản lý và optimistic locking. Query tải entity phải có hợp đồng phù hợp với use case; không dựng lại entity từ projection.

Không cần biến mọi thuộc tính lazy thành eager chỉ để sửa tên và giá. Cần đọc những dữ liệu mà quy tắc nghiệp vụ yêu cầu và để provider quản lý trạng thái còn lại theo mapping.

Nếu dùng một query update trực tiếp hoặc bulk update, đường đi có thể bỏ qua việc gọi phương thức domain và callback entity. Persistence context cũng có thể giữ trạng thái cũ sau một update thực hiện ngoài vòng đời entity đang quản lý.

Vì vậy, query update trực tiếp cần có cách giữ ràng buộc, version, auditing và tính nhất quán của context phù hợp; nó không phải thay thế tự động cho service domain.

### 8.2. Document store: entity đúng kiểu chưa chắc có dữ liệu đầy đủ

Một query MongoDB có thể chọn chỉ một số field rồi ánh xạ vào kiểu domain. Đối tượng trả về có đúng class nhưng không có đủ trạng thái của document gốc.

Gọi save trên đối tượng này không nên được hiểu ngầm là chỉ patch những field đã đọc. Cơ chế lưu có thể ghi document theo trạng thái mapping của đối tượng, dẫn tới mất hoặc thay đổi các field không được tải như mong muốn.

Hai hướng thiết kế cần cân nhắc là:

- Đọc trạng thái theo hợp đồng ghi phù hợp, áp dụng thay đổi rồi lưu với cơ chế kiểm soát đồng thời được hỗ trợ.
- Dùng thao tác update từng field của store, có điều kiện định danh, phạm vi và version.

Với cách thứ hai, ý nghĩa logic có thể là:

```text
Điều kiện:
  id đúng
  tenantId đúng
  version bằng expectedVersion

Thay đổi:
  đặt name mới
  đặt price mới
  tăng version theo chính sách
  cập nhật metadata sửa theo chính sách
```

Trong MongoDB, đặt field thành null và xóa field khỏi document là hai thao tác khác nhau. Hợp đồng “xóa mô tả” cần quyết định dùng giá trị null hay bỏ field, rồi query đọc phải xử lý tương ứng.

### 8.3. Kho quan hệ với update có điều kiện

Một SQL minh họa cho cập nhật có điều kiện:

```sql
UPDATE product
SET name = :name,
    price = :price,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND version = :expectedVersion;
```

Các cột khác không nằm trong tập gán của thao tác này. Tuy nhiên, service vẫn phải kiểm tra dữ liệu đầu vào và quy tắc nghiệp vụ, còn database cần các ràng buộc tương ứng khi cần.

Số bản ghi tác động phải được kiểm tra. Không có bản ghi khớp có thể do định danh, phạm vi hoặc version không còn hợp lệ; cách báo lỗi phụ thuộc hợp đồng ứng dụng.

Đây là ví dụ logic SQL, không phải API patch chung của Spring Data Commons. Với R2DBC hoặc module khác, cần dùng query/template/repository fragment được hỗ trợ. Không áp dụng giả định JPA dirty checking cho một đối tượng thông thường được tải bởi mọi store.

### 8.4. Cập nhật từng field không tự bảo đảm mọi invariant

Nếu quy tắc giá phụ thuộc trạng thái sản phẩm, một update chỉ có điều kiện version chưa thay thế việc kiểm tra quy tắc đó. Có thể cần thêm điều kiện, transaction hoặc thao tác nguyên tử phù hợp của store.

Tương tự, đổi tồn kho cần cơ chế riêng để tránh lost update hoặc số âm. Đó là lý do `AdjustStock` nên là hành động có quy tắc, thay vì một field tình cờ xuất hiện trong command sửa tên.

Khi chọn update tường minh để tránh đọc nhiều dữ liệu, phải mang các điều kiện nghiệp vụ cần thiết sang thiết kế đó. Đừng loại bỏ bước kiểm tra chỉ vì SQL hoặc command ngắn hơn.

## 9. Metadata, auditing và cập nhật đồng thời

### 9.1. Tách metadata do hệ thống quản lý khỏi dữ liệu người dùng nhập

Thông tin tạo, người tạo, tenant hoặc định danh có thể không được phép sửa trong use case này. Metadata sửa và version lại có thể phải thay đổi khi cập nhật thành công.

Do đó, kỳ vọng sau một lệnh sửa tên và giá không phải “mọi field khác đều giữ nguyên tuyệt đối”:

| Nhóm thuộc tính | Kỳ vọng ví dụ |
|---|---|
| `name`, `price` | Nhận giá trị mới hợp lệ |
| `sku`, `tenantId`, `stock`, `active`, `description` | Giữ theo hợp đồng use case |
| Metadata tạo | Giữ nguyên |
| Metadata sửa | Cập nhật theo cấu hình/chính sách |
| `version` | Do cơ chế kiểm soát đồng thời quản lý |

Auditing không khôi phục các field nghiệp vụ bị ghi mất. Nó chỉ quản lý những metadata được cấu hình và được lifecycle tương ứng kích hoạt.

### 9.2. Query update riêng có thể cần quản lý metadata riêng

Nếu thao tác không đi qua callback hoặc lifecycle auditing đã cấu hình, phải xác định cách ghi thời điểm sửa, người sửa và version trong chính đường update đó.

Không giả định mọi lệnh SQL, template update hoặc driver command tự kích hoạt cùng callback như save entity. Cần xác minh khả năng thực tế của module và phương thức đang dùng.

### 9.3. Tách kiểu đọc/ghi không tự giải quyết lost update

Hai người có thể cùng đọc version `v`. Người thứ nhất cập nhật thành công. Người thứ hai vẫn gửi một command hợp lệ về mặt shape, nhưng dựa trên dữ liệu cũ.

Nếu không kiểm tra version hoặc điều kiện đồng thời thích hợp, người thứ hai vẫn có thể ghi đè thay đổi của người thứ nhất ở các field thuộc lệnh.

Không thử lại một xung đột bằng cách âm thầm thay `expectedVersion` bằng version mới rồi gửi lại cùng ý định. Có thể cần cho người dùng tải lại hoặc thực hiện quy trình hòa giải theo nghiệp vụ.

## 10. Luồng giao diện dùng DTO đọc nhưng gửi command ghi

Một luồng chỉnh sửa có thể là:

```text
Đọc ProductSummary cho danh sách
    ↓ chọn sản phẩm
Đọc ProductDetails hoặc dữ liệu edit cần thiết, có version
    ↓ người dùng sửa tên và giá
Tạo ChangeProductInfo(name, price, expectedVersion)
    ↓ service tải entity theo phạm vi và kiểm tra
Áp dụng hành vi domain trong cơ chế ghi phù hợp
    ↓
Trả ProductDetails hoặc DTO kết quả mới
```

Không cần gửi lại toàn bộ dữ liệu đã đọc. Client chỉ gửi đầu vào của lệnh cùng thông tin kiểm tra đồng thời theo hợp đồng.

Nếu cho phép sửa ngay từ danh sách, có thể đưa version cần thiết vào DTO danh sách hoặc có một bước lấy thông tin chỉnh sửa. Việc thêm version để kiểm soát đồng thời vẫn không làm DTO danh sách trở thành entity dùng để save.

Nếu UI không hiển thị mô tả, nó không nên gửi null để thay mô tả trừ khi người dùng đã thực hiện hành động xóa theo hợp đồng. Sự khác biệt giữa “không có trên form” và “muốn xóa” phải được giữ từ UI đến service.

Ứng dụng cũng có thể biểu diễn điều kiện version qua cơ chế HTTP phù hợp rồi chuyển sang command nội bộ. Cách truyền điều kiện không thay đổi nhu cầu kiểm tra nó tại ranh giới ghi.

## 11. Kiểm chứng bằng trạng thái đã lưu lại

### 11.1. Chuẩn bị dữ liệu làm lộ việc mất field

Một fixture nên có giá trị nhận biết rõ cho các field ngoài phạm vi lệnh:

```text
sku          = SKU-ALPHA
name         = Tên cũ
price        = một giá cũ hợp lệ
description  = mô tả có nội dung
stock        = 37
active       = true
tenantId     = tenant-a
version      = phiên bản đã đọc
```

Sau khi sửa tên và giá, kiểm tra bản ghi lưu trữ được đọc lại qua một context/lần truy xuất phù hợp:

- Tên và giá mới đã được lưu.
- SKU, mô tả, tồn kho, trạng thái và tenant giữ đúng hợp đồng.
- Không phát sinh một bản ghi mới ngoài ý định.
- Metadata tạo vẫn đúng, metadata sửa và version theo cơ chế đã chọn.

Chỉ kiểm tra DTO trả về là chưa đủ. DTO có thể chứa đúng tên và giá trong bộ nhớ trong khi field khác ở store đã mất hoặc transaction chưa thành công.

### 11.2. Những tình huống cần bảo vệ

| Tình huống | Kết quả cần xác định |
|---|---|
| Sửa tên và giá hợp lệ | Chỉ thay đổi phạm vi lệnh cùng metadata được quản lý |
| Không gửi mô tả trong patch | Giữ nguyên mô tả |
| Gửi null để xóa mô tả | Xóa theo đúng quy ước null/absent của store và nghiệp vụ |
| Gửi null cho tên bắt buộc | Từ chối, không ghi trạng thái lỗi |
| Version cũ | Báo xung đột theo hợp đồng |
| Tenant hoặc phạm vi không hợp lệ | Không cập nhật ngoài phạm vi được phép |
| DTO đọc không có tồn kho | Không tự suy tồn kho bằng 0 |
| Projection quan hệ chỉ có một phần | Không tự thay toàn bộ collection |
| Update tường minh không qua auditing callback | Metadata vẫn được quản lý theo thiết kế riêng |
| Đọc lại sau khi transaction hoàn tất | Trạng thái lưu trữ phù hợp với kết quả công bố |

Với thử nghiệm đồng thời, cần tạo hai lượt đọc cùng version, cho một lượt cập nhật trước rồi xác nhận lượt còn lại bị xử lý như thiết kế. Nếu mọi writer không cùng giữ chính sách version, phải nhận diện giới hạn đó trong hệ thống.

### 11.3. Quan sát câu lệnh ghi là bằng chứng bổ trợ

SQL hoặc command thực tế giúp xác định thao tác là insert, replacement hay update từng field, và có điều kiện version/phạm vi hay không.

Tuy nhiên, đừng chỉ suy từ một SQL có vài cột rằng dữ liệu chắc chắn đúng. Cần kiểm tra giá trị, số bản ghi bị tác động và đọc lại trạng thái sau khi lưu.

Tương tự, một provider có thể tạo SQL cập nhật nhiều cột nhưng vẫn giữ đúng giá trị của entity được quản lý. Số cột trong SQL và sự đúng đắn của ngữ nghĩa ghi là hai khía cạnh phải đánh giá riêng.

## 12. Bài tập vận dụng

### Bài tập 1: Mất tồn kho từ một màn hình danh sách

DTO chỉ có id, tên và giá. Mapper tạo entity mới có `stock = 0`, rồi repository lưu nó. Vì sao thêm `stock` vào DTO đọc không phải cách sửa triệt để?

**Gợi ý lời giải:** Hợp đồng đọc vẫn có thể bỏ các field khác và dữ liệu có thể đã cũ. Cần command riêng cho hành động sửa, tải trạng thái phù hợp hoặc update từng field với điều kiện đúng, không dựng lại entity từ một view đọc.

### Bài tập 2: Bỏ qua mọi null

Một mapper được cấu hình không copy null để tránh mất dữ liệu. Người dùng muốn xóa mô tả bằng null nhưng thao tác không có tác dụng. Thiếu gì trong thiết kế?

**Gợi ý lời giải:** Cần phân biệt absent với null được gửi có chủ đích. Chính sách bỏ null chỉ bảo vệ được một số tình huống, không biểu diễn được đầy đủ ngữ nghĩa patch.

### Bài tập 3: Chỉ kiểm tra version trong Java

Service so sánh version rồi chạy update không có điều kiện version, trong lúc một transaction khác cũng ghi. Lỗ hổng còn lại là gì?

**Gợi ý lời giải:** Có khoảng thời gian giữa đọc/so sánh và ghi. Cần cơ chế kiểm soát đồng thời tại store như optimistic locking hoặc update có điều kiện, phù hợp với module.

### Bài tập 4: Entity được ánh xạ từ document giới hạn field

Một query chỉ chọn id và tên nhưng trả về kiểu `ProductDocument`. Có thể coi đó là trạng thái đầy đủ vì đúng class không?

**Gợi ý lời giải:** Không. Kiểu Java không chứng minh mọi field đã được tải. Lưu lại một document bị rút gọn có thể ghi thiếu trạng thái. Cần hợp đồng tải cho ghi hoặc thao tác update từng field rõ ràng.

### Bài tập 5: Update trực tiếp và auditing

Nhóm chuyển từ thay đổi entity sang một query update trực tiếp để chỉ ghi hai cột. Sau đó thời điểm sửa không còn được cập nhật. Cần kiểm tra điều gì?

**Gợi ý lời giải:** Đường update có thể không đi qua callback auditing cũ. Phải xác định cơ chế metadata, version và quy tắc nghiệp vụ trên đường ghi mới, đồng thời kiểm tra trạng thái sau khi lưu.

## 13. Những điều cần ghi nhớ

- DTO/projection đọc là dữ liệu đã được chọn để nhìn, không phải trạng thái đầy đủ dùng để save.
- Projection động thay đổi hình dạng đọc, không tự tạo ngữ nghĩa patch hoặc quyền sửa dữ liệu.
- Command ghi cần mô tả hành động và các field được phép thay đổi.
- Với JPA, cập nhật entity được quản lý trong transaction giúp giữ trạng thái ngoài phạm vi lệnh mà không dựng lại entity thiếu dữ liệu.
- Với store khác, dùng đúng cơ chế save hoặc update có điều kiện; không dựa vào một quy tắc null chung của Commons.
- Absent, null và giá trị mặc định phải được phân biệt theo hợp đồng đầu vào.
- Version, auditing, quan hệ và invariant cần được quản lý trên mọi đường ghi tương ứng.
- Kiểm chứng bằng dữ liệu đã lưu lại và hành vi đồng thời, không chỉ bằng DTO trả về.
