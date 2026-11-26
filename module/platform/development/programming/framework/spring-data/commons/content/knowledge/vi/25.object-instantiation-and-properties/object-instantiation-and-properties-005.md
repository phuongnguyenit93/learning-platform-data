# Java record và canonical constructor

## 1. Vì sao record liên quan đến quá trình ánh xạ?

Khi đọc dữ liệu từ store, Spring Data phải tạo một object Java và cung cấp giá trị cho các thuộc tính của object đó. Với một class mutable, hạ tầng có thể tạo instance rồi gán field hoặc gọi setter. Với Java record, các thành phần trạng thái là final và được thiết lập qua constructor.

Ví dụ:

```java
public record CustomerSummary(String displayName, String email) {
}
```

Record có thể được tạo trực tiếp như sau:

```java
CustomerSummary summary =
        new CustomerSummary("Nguyen An", "an@example.com");
```

Không cần viết setter hoặc constructor không tham số. Constructor nhận toàn bộ record component là điểm quan trọng để Spring Data tái tạo object từ kết quả truy vấn.

Trong Spring Data Commons, metadata về kiểu, thuộc tính và creator giúp hạ tầng xác định cách khởi tạo. Tuy nhiên, record có sử dụng được làm đối tượng persistent hay không còn phụ thuộc module store, mapper và phiên bản thực tế.

Bài sử dụng cú pháp record đã hoàn thiện từ Java 16; các ví dụ có thể đọc theo mức Java 17 trở lên. Cần chọn JDK và bộ Spring Data tương thích cho ứng dụng đang chạy.

## 2. Java tạo ra những gì cho một record?

Xét khai báo:

```java
public record CustomerSummary(String displayName, String email) {
}
```

Hai component là `displayName` và `email`. Java cung cấp những thành phần chính:

- Field lưu trạng thái tương ứng với từng component.
- Accessor `displayName()` và `email()`.
- Canonical constructor có tham số tương ứng với các component.
- `equals`, `hashCode` và `toString` dựa trên trạng thái record, trừ khi được override hợp lệ.

Sử dụng accessor:

```java
String name = summary.displayName();
String email = summary.email();
```

Accessor mặc định không có tên `getDisplayName()` hoặc `getEmail()`. Vì vậy, một công cụ chỉ hỗ trợ quy ước JavaBeans cũ chưa chắc xử lý record đúng. Cần dùng đường mapping và phiên bản có hỗ trợ record.

### Những giới hạn ảnh hưởng đến persistence

Một record:

- Là kiểu final.
- Không có setter mặc định.
- Không tự có constructor không tham số.
- Không cho khai báo thêm instance field ngoài trạng thái do record components xác định.
- Có thể có method, static field, static factory và triển khai interface.
- Không thể được thiết kế như một class entity mutable thông thường cần framework tạo subclass để proxy.

Không nên cố “sửa” một record bằng cách tìm cách gán lại component sau khi tạo instance. Nếu dữ liệu thay đổi, thông thường cần tạo một record mới.

## 3. Canonical constructor là gì?

Canonical constructor là constructor tương ứng đầy đủ với danh sách component của record, theo đúng thứ tự khai báo.

Với record:

```java
public record CustomerSummary(String displayName, String email) {
}
```

chữ ký canonical constructor là:

```java
public CustomerSummary(String displayName, String email)
```

Nếu không khai báo constructor, Java cung cấp constructor thích hợp.

Nếu viết canonical constructor đầy đủ, phải thiết lập trạng thái của các component:

```java
import java.util.Objects;

public record CustomerSummary(String displayName, String email) {

    public CustomerSummary(String displayName, String email) {
        this.displayName =
                Objects.requireNonNull(displayName, "displayName");
        this.email =
                Objects.requireNonNull(email, "email");
    }
}
```

Với một public record, canonical constructor phải có mức truy cập phù hợp; không thể biến nó thành private để ngăn hạ tầng bên ngoài khởi tạo trong khi record vẫn public.

### Tại sao constructor này quan trọng với mapper?

Canonical constructor cung cấp một đường tạo object có đủ trạng thái:

```text
Kết quả truy vấn
    → chuyển đổi giá trị theo metadata
    → tham số displayName, email
    → canonical constructor
    → CustomerSummary
```

Mapper không cần tạo object rỗng rồi tìm setter cho từng component.

Đây là cơ sở để một record phù hợp với mô hình constructor binding. Nó không tự bảo đảm mọi store hoặc mọi cơ chế ORM đều hỗ trợ record làm entity.

## 4. Compact constructor: cùng canonical constructor, cú pháp ngắn hơn

Có thể viết logic kiểm tra bằng compact constructor:

```java
import java.util.Objects;

public record CustomerSummary(String displayName, String email) {

    public CustomerSummary {
        displayName =
                Objects.requireNonNull(displayName, "displayName").trim();
        email =
                Objects.requireNonNull(email, "email").trim();

        if (displayName.isEmpty()) {
            throw new IllegalArgumentException(
                    "displayName must not be blank");
        }
    }
}
```

Compact constructor không có danh sách tham số viết tường minh. Trong phần thân, tên `displayName` và `email` là các tham số constructor tương ứng với record components.

Ở cuối quá trình thực thi thành công, Java thực hiện việc gán các giá trị tham số vào field của record.

Ví dụ:

```java
CustomerSummary summary =
        new CustomerSummary("  Nguyen An  ", " an@example.com ");

System.out.println(summary.displayName()); // Nguyen An
System.out.println(summary.email());       // an@example.com
```

### Điều cần nhớ khi viết compact constructor

- Có thể kiểm tra tham số và gán lại biến tham số.
- Không gán trực tiếp `this.displayName = ...` trong compact constructor.
- Không đọc accessor rồi kỳ vọng field đã nhận giá trị tham số ngay từ đầu phần thân.
- Không khai báo thêm một canonical constructor đầy đủ cùng chữ ký bên cạnh compact constructor.

Compact constructor không phải một constructor bổ sung dùng riêng cho nghiệp vụ. Nó chính là một cách khai báo canonical constructor; logic của nó sẽ chạy khi mapper sử dụng constructor này để đọc dữ liệu.

## 5. Constructor validation cũng chạy khi nạp dữ liệu

Giả sử compact constructor không chấp nhận tên rỗng:

```java
public CustomerSummary {
    if (displayName == null || displayName.isBlank()) {
        throw new IllegalArgumentException(
                "displayName must not be blank");
    }
}
```

Quy tắc không chỉ áp dụng cho code:

```java
new CustomerSummary("", "an@example.com");
```

Nó cũng có thể làm thất bại quá trình nạp một bản ghi cũ có `displayName` rỗng.

### Ba trường hợp phải phân biệt

| Trường hợp | Điều xảy ra ở constructor | Hệ quả cần xem xét |
| --- | --- | --- |
| Tạo object mới trong ứng dụng | Kiểm tra dữ liệu đầu vào nghiệp vụ | Có thể từ chối yêu cầu không hợp lệ |
| Nạp dữ liệu cũ từ store | Kiểm tra dữ liệu đã lưu trước đây | Có thể làm truy vấn thất bại vì dữ liệu lịch sử |
| Dựng DTO từ kết quả truy vấn | Kiểm tra dữ liệu được chọn hoặc tính toán | Có thể từ chối kết quả có null từ join hoặc biểu thức |

Nếu việc khởi tạo thất bại, mapper có thể bọc nguyên nhân trong một exception ánh xạ, chẳng hạn `MappingInstantiationException`. Cần xem nguyên nhân gốc thay vì chỉ kết luận “record không được hỗ trợ”.

### Chuẩn hóa cũng thay đổi dữ liệu quan sát được

Nếu compact constructor tự `trim` tên, object sau khi đọc có thể khác chuỗi gốc trong store.

Một lần đọc rồi lưu lại có thể khiến dữ liệu được chuẩn hóa ngay cả khi tầng nghiệp vụ không chủ động chỉnh sửa tên. Chỉ đặt logic đó trong constructor khi đây là chủ đích của mô hình.

Không nên dùng constructor để gọi repository khác, gửi request mạng hoặc thực hiện tác dụng phụ. Constructor có thể được gọi cho nhiều object trong một truy vấn và phải phù hợp với quá trình tái tạo dữ liệu.

## 6. Cách Spring Data nhìn record khi khởi tạo

Với mapping implementation có hỗ trợ record, canonical constructor là đường khởi tạo mặc định quan trọng của record. Thông thường không cần thêm `@PersistenceCreator` chỉ để xác nhận constructor hiển nhiên này.

Có thể hình dung luồng đọc:

1. Store trả về dữ liệu.
2. Converter giải mã và chuyển đổi giá trị.
3. Metadata xác định các thuộc tính và creator được sử dụng.
4. Giá trị thuộc tính được đưa vào các tham số constructor.
5. Constructor tạo record hoàn chỉnh.
6. Các bước xử lý sau đọc, nếu module có, tiếp tục trên object được tạo.

### 6.1. Tên thuộc tính và tên trong store

Tên tham số canonical constructor gắn với record components. Tên này mô tả thuộc tính Java, không nhất thiết trùng tên cột hoặc field trong store.

Ví dụ:

```text
Tên field trong store: display_name
Tên thuộc tính Java:  displayName
Tham số constructor:  displayName
```

Một mapper hỗ trợ annotation đổi tên sẽ thực hiện ánh xạ giữa tên store và thuộc tính Java trước khi dựng object.

Không đổi tên tham số constructor thành tên cột một cách tùy tiện để “khớp SQL”, vì constructor record phải tương ứng với cấu trúc record hợp lệ.

### 6.2. Thứ tự tham số không phải thứ tự cột tùy ý

Java định nghĩa thứ tự canonical constructor theo thứ tự record components.

Nhưng mapper không nên được hiểu như cơ chế “lấy cột thứ nhất truyền vào tham số thứ nhất” cho mọi đường đọc. Việc ràng buộc có thể dựa trên metadata, tên thuộc tính, alias hoặc quy tắc riêng của query.

Với DTO constructor expression, thứ tự biểu thức trong query lại phải phù hợp constructor được gọi. Cần phân biệt hai cơ chế thay vì suy một quy tắc chung cho mọi loại truy vấn.

### 6.3. Metadata tên tham số

Constructor mapping của class thông thường có thể phụ thuộc thông tin tên tham số mà quá trình biên dịch hoặc annotation cung cấp.

Record còn có metadata về các components, và đường hỗ trợ record có thể khai thác thông tin này. Không mặc định rằng mọi record đều phải thêm `@ConstructorProperties` hoặc giải quyết bằng `-parameters`.

Nếu gặp lỗi nhận diện tham số, cần kiểm tra phiên bản, loại projection, mapper thực tế và artifact đã biên dịch. Không áp dụng hướng xử lý của một class thông thường cho record mà chưa xác định nguyên nhân.

## 7. Constructor bổ sung và factory nghiệp vụ

Một record có thể có constructor bổ sung, nhưng constructor đó phải chuyển tiếp đến constructor khác của cùng record để cuối cùng thiết lập đủ trạng thái.

```java
public record CustomerSummary(String displayName, String email) {

    public CustomerSummary(String displayName) {
        this(displayName, null);
    }
}
```

Trong ví dụ này:

- Constructor hai tham số là canonical constructor.
- Constructor một tham số là constructor tiện dụng.
- Nếu canonical constructor cấm email null, constructor tiện dụng trên sẽ không còn hợp lệ về hành vi.

Với record được mapper hỗ trợ, không nên thêm no-arg constructor chỉ vì nghĩ persistence luôn cần object rỗng.

### Factory cho việc tạo mới không đồng nghĩa persistence creator

Ví dụ factory:

```java
public static CustomerSummary withoutEmail(String displayName) {
    return new CustomerSummary(displayName, null);
}
```

Đây có thể là API nghiệp vụ của ứng dụng. Nó không mặc nhiên trở thành creator mà Spring Data dùng để tái tạo dữ liệu đã lưu.

Annotation `@PersistenceCreator` thể hiện lựa chọn creator khi cần cấu hình tường minh theo cơ chế được hỗ trợ. Không gắn annotation này vào một factory chỉ vì factory có tên dễ đọc.

Đặc biệt, một factory tạo mới có thể:

- Gán ID bằng null.
- Đặt trạng thái mặc định.
- Bỏ qua timestamp hoặc version đã có.
- Chỉ nhận một phần dữ liệu.

Những hành vi đó thường không phù hợp với việc đọc lại một bản ghi đã tồn tại.

Nếu muốn thay đổi creator, phải kiểm tra quy tắc phát hiện creator của phiên bản và module đang dùng, đồng thời bảo đảm đường tái tạo giữ đủ trạng thái persistent.

## 8. Ví dụ record làm document trong Spring Data MongoDB

Phần này minh họa một module có hỗ trợ ánh xạ record. Không coi đây là mẫu entity áp dụng nguyên trạng cho mọi store.

### 8.1. Model

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public record CustomerDocument(
        @Id String id,
        @Field("display_name") String displayName,
        String email,
        boolean active) {

    public CustomerDocument {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "displayName must not be blank");
        }

        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException(
                    "email must not be blank");
        }
    }

    public static CustomerDocument newCustomer(
            String displayName,
            String email) {
        return new CustomerDocument(null, displayName, email, true);
    }

    public CustomerDocument withId(String newId) {
        return new CustomerDocument(
                newId,
                displayName,
                email,
                active);
    }

    public CustomerDocument deactivate() {
        return new CustomerDocument(
                id,
                displayName,
                email,
                false);
    }
}
```

Các điểm đáng chú ý:

- `id` được phép null để biểu diễn object mới trước khi store cấp ID.
- Các thuộc tính bắt buộc được kiểm tra trong compact constructor.
- `display_name` là tên field store, còn thuộc tính Java vẫn là `displayName`.
- `newCustomer` phục vụ tạo mới, không được đánh dấu là persistence creator.
- `withId` trả về record mới, giữ nguyên các component còn lại.
- `deactivate` cũng tạo object mới, không sửa object hiện có.

Annotation đặt trên record component có thể được Java truyền tới các thành phần được sinh tương ứng theo target của annotation. Tuy nhiên, khả năng mapper sử dụng metadata đó vẫn cần phù hợp phiên bản module.

### 8.2. Repository

```java
package com.example.customer;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<CustomerDocument, String> {
}
```

Giả định ứng dụng đã cấu hình Spring Data MongoDB và phát hiện repository này.

### 8.3. Luôn sử dụng kết quả trả về từ save

```java
CustomerDocument draft =
        CustomerDocument.newCustomer(
                "Nguyen An",
                "an@example.com");

CustomerDocument saved = repository.save(draft);

System.out.println(saved.id());
```

Với model immutable, hạ tầng có thể cần tạo một instance mới khi gán ID sinh tự động hoặc thay đổi thuộc tính do persistence quản lý.

Method `withId` cung cấp một đường tạo bản sao cho ID khi hạ tầng accessor của module nhận diện và sử dụng cơ chế này. Một đường mapping khác có thể tái tạo object qua constructor.

Trong mọi trường hợp, code gọi nên sử dụng instance do `save` trả về. Không kỳ vọng biến `draft` đã bị sửa tại chỗ:

```java
// Không dùng cách này để lấy trạng thái sau lưu.
repository.save(draft);
String id = draft.id();
```

Nếu muốn cập nhật trạng thái nghiệp vụ:

```java
CustomerDocument inactive = saved.deactivate();
CustomerDocument persisted = repository.save(inactive);
```

Không thể gán:

```java
// Không hợp lệ với record.
// saved.active = false;
// saved.setActive(false);
```

### 8.4. Null ID khác với dữ liệu bắt buộc bị thiếu

Không nên kiểm tra “mọi component đều phải khác null” một cách máy móc.

Một ID được store cấp có thể cần null trước lần lưu đầu tiên. Timestamp auditing hoặc version cũng có thể chưa có ở thời điểm ứng dụng tạo object mới.

Ngược lại, tên hoặc email có thể là invariant nghiệp vụ bắt buộc.

Phải thiết kế constructor dựa trên vòng đời thực tế của object, gồm tạo mới, đọc lại và nhận dữ liệu do store hoặc callback cung cấp. Record không tự cung cấp các giai đoạn khởi tạo riêng chỉ vì field là metadata persistence.

## 9. Record làm DTO projection

Record thường phù hợp với kết quả truy vấn chỉ chứa một phần dữ liệu:

```java
package com.example.customer;

public record CustomerSummary(
        String displayName,
        String email) {
}
```

Ví dụ mở rộng repository ở phần trước:

```java
package com.example.customer;

import org.springframework.data.repository.CrudRepository;

import java.util.List;

public interface CustomerRepository
        extends CrudRepository<CustomerDocument, String> {

    List<CustomerSummary> findByActiveTrue();
}
```

Đây là ví dụ class-based projection, áp dụng khi module và phiên bản hỗ trợ đường truy vấn tương ứng.

Canonical constructor cho mapper biết DTO cần `displayName` và `email`. Không cần setter để dựng kết quả.

### 9.1. DTO không phải entity rút gọn có thể lưu tùy ý

`CustomerSummary` không có ID và không giữ đủ trạng thái của `CustomerDocument`. Nó là một kiểu kết quả khác.

Không nên:

1. Query thiếu một số field của document.
2. Dựng entity record với giá trị thiếu hoặc mặc định.
3. Lưu lại entity đó như thể có đầy đủ dữ liệu.

Tùy store, thao tác lưu có thể làm mất hoặc ghi đè dữ liệu chưa được nạp. DTO riêng giúp thể hiện rõ kết quả chỉ dùng để đọc.

### 9.2. Phân trang và sắp xếp

Khi module hỗ trợ projection kết hợp phân trang, có thể khai báo dạng:

```java
Page<CustomerSummary> findByActiveTrue(Pageable pageable);
```

Đây là một khai báo thay thế hoặc bổ sung theo chữ ký phù hợp, với các import `Page` và `Pageable` của Spring Data.

Canonical constructor chỉ quyết định cách dựng từng phần tử DTO. Nó không tự tạo count query hoặc làm cho store hỗ trợ mọi cơ chế phân trang.

Tên sort vẫn phải phù hợp model truy vấn, chẳng hạn `displayName`; không chuyển thành chuỗi `"displayName()"` chỉ vì accessor của record có dấu ngoặc khi gọi trong Java.

### 9.3. JPA DTO projection khác với JPA entity

Một record có thể được dùng làm DTO trong constructor expression phù hợp:

```jpql
select new com.example.customer.CustomerSummary(
    c.displayName,
    c.email
)
from Customer c
where c.active = true
```

Ở đây `Customer` là entity JPA riêng; `CustomerSummary` là object kết quả được tạo bằng constructor.

Không nên từ đó kết luận rằng chính record có thể thay trực tiếp entity JPA thông thường. Record là final, không có constructor không tham số mặc định và không phù hợp các yêu cầu của mô hình entity JPA thông thường.

Nếu provider có hỗ trợ record ở vai trò embeddable hoặc cơ chế mở rộng khác, phải xem riêng khả năng và phiên bản của provider. Hỗ trợ DTO không đồng nghĩa hỗ trợ entity.

## 10. Thiếu dữ liệu, null và giá trị mặc định

Record không tự giải quyết những khác biệt giữa schema và model Java.

### 10.1. Thêm component mới

Giả sử model cũ:

```java
public record CustomerSummary(String displayName, String email) {
}
```

Model mới:

```java
public record CustomerSummary(
        String displayName,
        String email,
        String preferredLanguage) {
}
```

Cần xác định các kết quả cũ hoặc document cũ cung cấp gì cho `preferredLanguage`.

Có thể đặt default có chủ đích:

```java
public CustomerSummary {
    if (preferredLanguage == null) {
        preferredLanguage = "vi";
    }
}
```

Default này chỉ hữu ích nếu đường mapping có thể truyền null vào tham số. Nếu câu truy vấn, converter hoặc schema thất bại trước khi gọi constructor thì logic trong constructor không có cơ hội chạy.

Việc thêm component cũng thay đổi canonical constructor và có thể ảnh hưởng query projection, code gọi và tương thích giữa các phiên bản ứng dụng.

### 10.2. Primitive và wrapper

So sánh:

```java
public record AccountFlags(boolean enabled) {
}
```

với:

```java
public record AccountFlags(Boolean enabled) {
}
```

`boolean` không thể biểu diễn null. `Boolean` có thể biểu diễn trạng thái “chưa biết” hoặc “chưa có dữ liệu”.

Không giả định field store bị thiếu hoặc null luôn được chuyển thành `false`. Đường conversion và constructor binding có thể từ chối giá trị hoặc xử lý theo quy tắc riêng.

Cần chủ động chọn:

- Schema bảo đảm luôn có giá trị.
- Wrapper cho phép biểu diễn dữ liệu thiếu.
- Converter hoặc constructor cung cấp default đã được thiết kế.

Đối với số lượng, số tiền và thời điểm, cũng cần phân biệt “không có dữ liệu” với `0` hoặc một timestamp mặc định.

### 10.3. Query có join hoặc biểu thức

DTO record có component bắt buộc nhưng query dùng outer join có thể nhận null. Compact constructor cấm null khi đó sẽ làm quá trình dựng DTO thất bại.

Kiểu dữ liệu của biểu thức cũng phải phù hợp constructor. Ví dụ kết quả tổng hợp numeric có thể cần conversion cụ thể, không thể chỉ dựa vào việc tên component giống tên alias.

## 11. Record chỉ bất biến ở cấu trúc tham chiếu

Các component của record là final, nhưng object được tham chiếu có thể vẫn mutable.

Ví dụ:

```java
import java.util.List;

public record OrderSnapshot(String orderNumber, List<String> tags) {
}
```

Code gọi có thể giữ một list bên ngoài rồi thay đổi nó sau khi tạo record. Tham chiếu `tags` không đổi, nhưng nội dung list đổi.

Có thể phòng tránh bằng defensive copy:

```java
import java.util.List;
import java.util.Objects;

public record OrderSnapshot(String orderNumber, List<String> tags) {

    public OrderSnapshot {
        Objects.requireNonNull(orderNumber, "orderNumber");
        tags = List.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }
}
```

`List.copyOf` tạo danh sách không cho sửa cấu trúc qua API thông thường và không chấp nhận phần tử null. Nếu dữ liệu store có null trong danh sách, constructor có thể thất bại khi nạp.

Đây vẫn không phải deep copy của mọi phần tử. Nếu list chứa các object mutable, trạng thái bên trong phần tử vẫn có thể thay đổi.

Khi record dùng làm value object hoặc DTO kết quả truy vấn, phải xem xét cả kiểu component chứ không chỉ từ khóa `record`.

## 12. Equality, ID và phiên bản dữ liệu

Mặc định `equals` và `hashCode` của record dựa trên toàn bộ components.

Với `CustomerDocument`:

```java
CustomerDocument before =
        new CustomerDocument(null, "Nguyen An", "an@example.com", true);

CustomerDocument after =
        new CustomerDocument("id-1", "Nguyen An", "an@example.com", true);
```

Hai record này không bằng nhau vì ID khác nhau.

Tương tự, thay đổi trạng thái `active` cũng tạo giá trị khác theo equality mặc định.

Điều này phù hợp với nhiều DTO và value object, nhưng có thể khác kỳ vọng “hai entity có cùng ID thì được xem là cùng thực thể”.

Cần cân nhắc khi:

- Dùng record persistent làm key của map hoặc phần tử set.
- So sánh object trước và sau `save`.
- Cache kết quả theo toàn bộ object.
- Thêm component version hoặc timestamp.
- Override equality theo một quy tắc domain riêng.

Record giúp viết ít code, nhưng không tự quyết định identity semantics cho aggregate.

## 13. Liên hệ với auditing, read-only và Query by Example

### 13.1. Auditing và thuộc tính do store quản lý

Nếu record có `createdAt`, `updatedAt` hoặc `version`, hạ tầng cần một đường tạo object có giá trị đã cập nhật.

Phải kiểm tra module hỗ trợ cập nhật object immutable thế nào: constructor, wither hoặc callback trả instance mới. Chỉ thêm annotation auditing không chứng minh mọi combination record–store đều hoạt động.

Tương tự, một component read-only có thể được truyền vào constructor khi nạp từ store nhưng bị loại khỏi chiều ghi trong mapping hỗ trợ annotation. Nó không có nghĩa constructor được phép bỏ hẳn tham số đó.

Không cấm null ở constructor nếu vòng đời hợp lệ có giai đoạn thuộc tính chưa được store hoặc auditing cung cấp.

### 13.2. Query by Example

Một probe cho Query by Example cũng là object cần được tạo hợp lệ. Record không cần no-arg constructor để làm probe, nhưng constructor bắt buộc có thể khiến việc biểu diễn điều kiện tìm kiếm một phần trở nên khó khăn.

Ví dụ:

- Constructor bắt buộc email khác null, trong khi tìm kiếm chỉ cần tên.
- Component primitive có giá trị mặc định nhưng người dùng không có ý định lọc theo nó.
- Constructor chuẩn hóa chuỗi làm thay đổi probe trước khi matcher xử lý.

Nếu cần bỏ qua thuộc tính không tham gia điều kiện, phải cấu hình matcher phù hợp với khả năng module. Không tự nới lỏng mọi invariant của domain record chỉ để phục vụ một biểu mẫu tìm kiếm.

Một request DTO riêng và một bước tạo truy vấn tường minh có thể diễn đạt nhu cầu tìm kiếm tốt hơn trong trường hợp đó.

## 14. Kịch bản kiểm chứng phù hợp

### 14.1. Kiểm tra logic constructor

Tạo record trực tiếp để kiểm tra:

- Dữ liệu hợp lệ được giữ hoặc chuẩn hóa đúng.
- Null và giá trị không hợp lệ được xử lý đúng chính sách.
- Factory tạo mới giữ các default mong muốn.
- Method trả bản sao không làm mất các component còn lại.
- Collection được bảo vệ theo mức bất biến yêu cầu.

Các kiểm tra này chỉ xác minh logic Java. Chúng không chứng minh mapper đang dùng canonical constructor đúng.

### 14.2. Kiểm tra đọc từ store

Dùng store thực tế hoặc môi trường integration phù hợp:

1. Chuẩn bị bản ghi có tên field khác tên Java nếu model dùng annotation đổi tên.
2. Đọc qua repository hoặc template đang dùng.
3. Xác nhận các components nhận đúng giá trị.
4. Xác nhận validation hoặc normalization của constructor có hành vi dự kiến.
5. Thử một bản ghi thiếu field mới.
6. Thử một bản ghi có null không hợp lệ và quan sát nguyên nhân lỗi.

Không chỉ dùng dữ liệu được tạo bằng chính record hợp lệ, vì cách đó có thể bỏ sót vấn đề tương thích với dữ liệu lịch sử.

### 14.3. Kiểm tra save và projection

Với record persistent:

1. Tạo object mới có ID chưa được cấp.
2. Gọi `save` và giữ kết quả trả về.
3. Kiểm tra ID và các metadata được cập nhật.
4. Đọc lại để xác nhận dữ liệu authoritative.
5. Tạo bản sao thay đổi một thuộc tính và lưu.
6. Kiểm tra các thuộc tính không thay đổi vẫn được giữ đúng.

Với DTO projection:

1. Chỉ chọn dữ liệu mà DTO cần.
2. Kiểm tra tên hoặc alias và kiểu giá trị phù hợp constructor.
3. Kiểm tra kết quả có null từ các trường hợp truy vấn hợp lệ.
4. Nếu có phân trang, kiểm tra nội dung và metadata trang theo khả năng store.

Không dùng thành công của DTO projection làm bằng chứng record persistent cũng được hỗ trợ.

## 15. Lỗi thường gặp

| Biểu hiện | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Mapper không tạo được record | Phiên bản hoặc đường mapping chưa hỗ trợ, hoặc creator không được nhận diện | Xác định mapper và bộ dependency thực tế |
| Lỗi khởi tạo nhưng constructor đã được tìm thấy | Validation, null hoặc conversion thất bại | Xem nguyên nhân gốc và dữ liệu đầu vào |
| Bị yêu cầu setter trong một đường xử lý | Hạ tầng đang dùng cơ chế bean mutable hoặc không nhận diện record | Chọn đường hỗ trợ constructor mapping hoặc đổi loại model |
| Record đọc được từ store nhưng không tạo mới được | Constructor cấm ID hoặc metadata null trước lưu | Thiết kế lại invariant theo vòng đời persistence |
| ID vẫn null sau khi gọi save | Code dùng instance cũ hoặc đường cập nhật immutable chưa phù hợp | Dùng kết quả trả về và kiểm tra cơ chế cấp ID |
| DTO thiếu dữ liệu dù tên giống field store | Tên Java, alias và tên store bị nhầm | Kiểm tra metadata đổi tên và loại query |
| Constructor tiện dụng gây hiểu nhầm | Factory/constructor tạo mới bị dùng như persistence creator | Tách mục đích và kiểm tra creator được chọn |
| Nạp dữ liệu cũ bị lỗi sau khi thêm component | Schema, default hoặc nullability chưa được xử lý | Lập kế hoạch tương thích và migration |
| Collection bên trong record vẫn đổi | Record chỉ bảo vệ tham chiếu component | Defensive copy và xem xét độ mutable của phần tử |
| Record làm DTO được nhưng không làm entity JPA được | Nhầm constructor projection với entity lifecycle | Giữ entity JPA phù hợp và dùng record cho DTO |

## 16. Bài thực hành

Xây dựng một record `BookDocument` cho một module store có hỗ trợ record, với:

- ID có thể chưa có trước lần lưu đầu tiên.
- Tiêu đề bắt buộc.
- Năm xuất bản có chính sách rõ ràng khi dữ liệu thiếu.
- Danh sách tag không bị thay đổi từ list bên ngoài.
- Một method tạo bản sao đổi tiêu đề.

Sau đó tạo DTO record `BookSummary` chỉ chứa tiêu đề và năm xuất bản.

Thực hiện:

1. Xác định canonical constructor của từng record.
2. Viết compact constructor với validation có chủ đích.
3. Tách factory tạo mới khỏi đường tái tạo dữ liệu đã lưu.
4. Lưu một object mới và dùng instance trả về.
5. Đọc lại bản ghi để kiểm tra constructor binding.
6. Chuẩn bị dữ liệu lịch sử thiếu năm xuất bản và xác minh chính sách.
7. Query ra `BookSummary` bằng cơ chế projection mà module hỗ trợ.
8. Giải thích vì sao DTO không cần setter và vì sao điều này không đủ để kết luận record là entity hợp lệ cho mọi store.

Kết quả đạt yêu cầu khi phân biệt được ba vấn đề: cấu trúc record của Java, creator được Spring Data sử dụng, và khả năng lưu trữ cụ thể của module.

Canonical constructor là đường hình thành đầy đủ trạng thái của record. Compact constructor giúp thêm kiểm tra mà vẫn giữ đường tạo object đó. Khi dùng với Spring Data, cần thiết kế constructor cho cả dữ liệu mới lẫn dữ liệu được nạp, sử dụng instance trả về sau lưu và chọn đúng vai trò record theo store.
