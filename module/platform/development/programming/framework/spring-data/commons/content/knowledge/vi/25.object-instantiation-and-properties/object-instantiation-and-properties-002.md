# Quy tắc chọn constructor hoặc static factory

Trong chương **Khởi tạo và gán thuộc tính** của **SPRING_DATA_COMMONS**, bài này giải thích cách Spring Data chọn điểm khởi tạo đối tượng khi ánh xạ dữ liệu đã lưu trở lại mô hình miền. Trọng tâm là constructor, static factory và annotation `@PersistenceCreator`.

Hiểu quy tắc này giúp thiết kế đối tượng immutable, tránh constructor được chọn ngoài ý muốn và phân biệt lỗi chọn creator với lỗi thiếu dữ liệu đầu vào. Đây là nền tảng để đọc đúng kết quả truy vấn từ repository, kể cả khi truy vấn, phân trang hay sắp xếp đã chạy thành công.

## 1. Phạm vi: cơ chế object mapping nào đang tạo đối tượng?

Cơ chế trình bày ở đây dành cho các module Spring Data tự triển khai object mapping, chẳng hạn MongoDB và Spring Data Relational. Spring Data JPA giao việc ánh xạ entity cho JPA provider; không áp nguyên các quy tắc này cho entity JPA. Phạm vi này được nêu trong [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html).

Trong bài, **creator** là constructor hoặc static factory được dùng để tạo instance từ dữ liệu lưu trữ. Nó khác với:

- Constructor mà mã ứng dụng chủ động gọi bằng `new`.
- Constructor được Spring IoC chọn để inject một bean.
- Hàm tạo mà thư viện JSON chọn để đọc request.
- Một factory nghiệp vụ được ứng dụng gọi để tạo bản ghi mới.

Các ví dụ Java là những mô hình độc lập nhằm minh họa quy tắc. Muốn đọc hoặc ghi thực tế, vẫn cần module lưu trữ, cấu hình converter, ánh xạ và dữ liệu tương ứng. Ví dụ dùng `record` yêu cầu JDK hỗ trợ Java records.

## 2. Thứ tự chọn creator cho lớp Java

Với trường hợp thông thường, thứ tự được mô tả trong [quy tắc object creation của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/object-mapping.html) là:

| Thứ tự | Điều kiện | Creator được chọn |
| --- | --- | --- |
| 1 | Có đúng một static factory được đánh dấu `@PersistenceCreator` | Static factory đó |
| 2 | Chỉ có một constructor | Constructor duy nhất |
| 3 | Có nhiều constructor và đúng một constructor được đánh dấu `@PersistenceCreator` | Constructor được đánh dấu |
| 4 | Kiểu là Java record | Canonical constructor |
| 5 | Có constructor không tham số | Constructor không tham số; bỏ qua các constructor khác |

Bảng này giả định cấu hình creator hợp lệ. Đánh dấu nhiều ứng viên không phải một cách yêu cầu mapper tự chọn ứng viên phù hợp nhất.

Các ví dụ tiếp theo là thiết kế riêng để phân tích từng nhánh. Không ghép tất cả constructor và annotation của các ví dụ vào cùng một lớp.

## 3. Một constructor: thường không cần annotation lựa chọn

Giả sử đối tượng lưu thông tin khách hàng:

~~~java
package com.acme.mapping;

import java.time.Clock;
import java.time.Instant;

import org.springframework.data.annotation.Id;

public final class CustomerSnapshot {

    @Id
    private final String id;
    private final String displayName;
    private final Instant createdAt;

    public CustomerSnapshot(
            String id,
            String displayName,
            Instant createdAt) {
        this.id = id;
        this.displayName = displayName;
        this.createdAt = createdAt;
    }

    public static CustomerSnapshot register(
            String id,
            String displayName,
            Clock clock) {
        return new CustomerSnapshot(
                id,
                displayName,
                clock.instant()
        );
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Lớp có một constructor nhận `id`, `displayName`, `createdAt`. Phương thức `register` không được đánh dấu làm persistence creator, nên sự tồn tại của nó không làm constructor mất vai trò.

Ở thiết kế này, hai đường tạo đối tượng có mục đích khác nhau:

| Đường gọi | Nguồn của createdAt |
| --- | --- |
| Ứng dụng gọi `register(..., clock)` | Thời điểm do nghiệp vụ chọn qua Clock |
| Mapper phục hồi đối tượng | Giá trị đã được lưu và chuyển đổi sang Instant |

Nếu snapshot đã lưu có `createdAt` là thời điểm của tháng trước, việc đọc lại không được tự thay bằng thời điểm hiện tại. Factory nghiệp vụ và đường phục hồi được tách rõ để tránh sai lệch đó.

Các field final đều có giá trị từ constructor. Điều này làm trạng thái sau khởi tạo dễ kiểm soát, nhưng chưa giải quyết yêu cầu về metadata tên tham số; phần 8 trình bày yêu cầu ấy.

## 4. Nhiều constructor: chỉ định constructor dành cho persistence

Một constructor thuận tiện cho nghiệp vụ có thể không nhận đầy đủ trạng thái đã lưu:

~~~java
package com.acme.mapping;

import org.springframework.data.annotation.PersistenceCreator;

public final class BookingSnapshot {

    private final String id;
    private final String status;
    private final int seats;

    public BookingSnapshot(String id, int seats) {
        this(id, "PENDING", seats);
    }

    @PersistenceCreator
    public BookingSnapshot(String id, String status, int seats) {
        this.id = id;
        this.status = status;
        this.seats = seats;
    }

    public String getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public int getSeats() {
        return seats;
    }
}
~~~

Với dữ liệu `id = "B-7"`, `status = "CONFIRMED"`, `seats = 2`, constructor ba tham số thể hiện đúng đường phục hồi: giữ trạng thái `CONFIRMED` thay vì áp giá trị mặc định `PENDING`.

Annotation không làm constructor hai tham số biến mất. Mã Java vẫn có thể gọi constructor đó để tạo booking mới theo quy ước của ứng dụng.

Metadata của constructor được chọn được Spring Data biểu diễn bằng `PreferredConstructor`; API này phân biệt constructor được chọn tường minh bởi `@PersistenceCreator` với constructor không tham số. Xem [PreferredConstructor API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PreferredConstructor.html).

### Điều không nên suy ra từ số lượng tham số

Giả sử lớp có hai constructor:

~~~java
public BookingSnapshot(String id, int seats) { /* ... */ }

public BookingSnapshot(String id, String status, int seats) { /* ... */ }
~~~

Nếu bỏ annotation, không nên cho rằng constructor ba tham số sẽ được chọn chỉ vì nó dài hơn hoặc tên tham số trùng dữ liệu hơn.

Khi thiết kế đã có nhiều đường khởi tạo, hãy quyết định rõ đường nào dùng cho dữ liệu lưu trữ. Annotation lựa chọn creator thể hiện quyết định đó ngay trong mã nguồn.

Một cách khác là giữ một constructor đầy đủ và chuyển các biến thể nghiệp vụ thành static factory không đánh dấu. Cách này làm số constructor ít thay đổi hơn khi bổ sung use case.

## 5. Static factory: đánh dấu đường phục hồi có tên rõ ràng

Static factory cho phép biểu đạt một đường tạo đối tượng bằng tên phương thức, thay vì chỉ bằng danh sách tham số:

~~~java
package com.acme.mapping;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

import org.springframework.data.annotation.PersistenceCreator;

public final class TaskSnapshot {

    private final String id;
    private final String state;
    private final Instant createdAt;

    private TaskSnapshot(
            String id,
            String state,
            Instant createdAt) {
        this.id = Objects.requireNonNull(id, "id");
        this.state = Objects.requireNonNull(state, "state");
        this.createdAt = Objects.requireNonNull(createdAt, "createdAt");
    }

    @PersistenceCreator
    public static TaskSnapshot rehydrate(
            String id,
            String state,
            Instant createdAt) {
        return new TaskSnapshot(id, state, createdAt);
    }

    public static TaskSnapshot open(String id, Clock clock) {
        return new TaskSnapshot(id, "OPEN", clock.instant());
    }

    public String getId() {
        return id;
    }

    public String getState() {
        return state;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Trong thiết kế này:

- `rehydrate` nhận trạng thái đã có, giữ nguyên giá trị cần phục hồi.
- `open` thể hiện quy tắc tạo task mới: trạng thái ban đầu là `OPEN`.
- Constructor private gom việc gán field và kiểm tra null.

Tên `rehydrate` chỉ là tên do ứng dụng chọn. Vai trò persistence creator đến từ annotation, không đến từ một danh sách tên như `of`, `from` hoặc `create`.

Spring Data có kiểu metadata riêng là `FactoryMethod` để biểu diễn factory được dùng khi ánh xạ dữ liệu thành đối tượng. Xem [FactoryMethod API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/FactoryMethod.html).

### Không biến factory phục hồi thành một use case tạo mới

Giả sử task đã lưu có trạng thái `DONE`. Nếu factory phục hồi luôn trả:

~~~java
return new TaskSnapshot(id, "OPEN", Instant.now());
~~~

thì thao tác đọc đã làm mất trạng thái và thời điểm gốc, dù đối tượng vẫn được tạo thành công.

Đường phục hồi nên tập trung tái lập trạng thái và kiểm tra những bất biến thật sự cần thiết. Không nên tự phát sinh thông báo, gọi thanh toán hoặc ghi một bản ghi mới chỉ vì đối tượng vừa được materialize.

Việc phục hồi có thể xảy ra nhiều lần cho cùng một dữ liệu: một lần cho màn hình danh sách, một lần cho màn hình chi tiết, hoặc trong một tác vụ nền. Side effect trong creator sẽ bị gắn với số lần đọc thay vì một hành động nghiệp vụ rõ ràng.

## 6. Constructor không tham số: một nhánh fallback có hệ quả riêng

Xét một kiểu mutable có hai constructor và không có annotation lựa chọn:

~~~java
package com.acme.mapping;

public class MutableContact {

    private String id;
    private String displayName;

    public MutableContact() {
    }

    public MutableContact(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Theo nhánh fallback trong bảng, mapper chọn constructor không tham số. Constructor hai tham số không được chọn chỉ vì có vẻ nhận đủ trạng thái hơn.

Ngay sau khi constructor không tham số kết thúc, `id` và `displayName` vẫn chưa có dữ liệu. Việc hoàn thiện đối tượng còn phụ thuộc bước gán thuộc tính của mapper và quy tắc access của module.

Ví dụ cho thấy một thay đổi tưởng nhỏ có thể ảnh hưởng đường khởi tạo: lớp ban đầu chỉ có constructor hai tham số, sau đó được thêm constructor không tham số để phục vụ một thư viện khác. Mô hình creator đã khác trước.

Có thể lựa chọn một trong các hướng sau tùy nhu cầu:

- Đánh dấu constructor đầy đủ bằng `@PersistenceCreator`.
- Giữ một constructor persistence duy nhất và dùng factory cho biến thể nghiệp vụ.
- Chủ động dùng đường không tham số với mô hình mutable và cơ chế gán thuộc tính phù hợp.

Không thêm constructor rỗng như một cách sửa mọi lỗi mapping. Nếu lỗi thực sự nằm ở tên tham số, chuyển đổi kiểu hoặc thiếu trường dữ liệu, constructor rỗng có thể chỉ chuyển lỗi sang bước khác.

## 7. Java record: hiểu vai trò của canonical constructor

Một record có canonical constructor ứng với toàn bộ record components:

~~~java
package com.acme.mapping;

public record ItemSnapshot(
        String id,
        String label,
        long revision) {

    public ItemSnapshot(String id, String label) {
        this(id, label, 0L);
    }
}
~~~

Record trên có thêm một constructor tiện dụng, nhưng không có constructor hay factory nào được đánh dấu để thay thế đường mặc định. Canonical constructor vẫn nhận đủ `id`, `label`, `revision`.

Nếu dữ liệu đã lưu có `revision = 8`, constructor hai tham số không phải lý do để mapper tự thay bằng `0`.

Nếu định nghĩa compact canonical constructor, phần thân của nó vẫn là mã thực thi khi canonical constructor được gọi:

~~~java
package com.acme.mapping;

public record LabelSnapshot(String id, String label) {

    public LabelSnapshot {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("label must not be blank");
        }
    }
}
~~~

Nếu dữ liệu cũ có label rỗng, quy tắc mới trong compact constructor có thể làm thao tác đọc thất bại. Đây là hệ quả của validation trong mô hình, không phải bằng chứng rằng record buộc phải có constructor rỗng.

Khi thay đổi bất biến của record hoặc lớp immutable, cần đánh giá dữ liệu lịch sử. Có thể cần migration, chính sách xử lý dữ liệu không hợp lệ hoặc phiên bản mô hình tương thích.

Quy tắc của record trong bài không thay thế quy tắc riêng dành cho Kotlin. Kotlin có primary constructor và cơ chế tham số mặc định; không suy trực tiếp hành vi default của Kotlin sang Java.

## 8. Chọn creator và gắn giá trị tham số là hai vấn đề khác nhau

Một creator được chọn đúng vẫn có thể không gọi được nếu mapper không xác định được đầu vào.

Có thể tách quá trình đọc thành chuỗi trách nhiệm:

~~~text
Dữ liệu từ kho
  → nhận diện thuộc tính và chuyển đổi giá trị
  → xác định giá trị từng tham số creator
  → gọi constructor hoặc static factory đã chọn
  → hoàn thiện thuộc tính còn lại nếu cần
~~~

Sơ đồ là mô hình giải thích trách nhiệm, không phải cam kết mọi converter đều thực hiện đúng một thứ tự nội bộ giống nhau.

### 8.1. Dùng tên thuộc tính miền làm điểm nối

Với thuộc tính `displayName`, tham số creator nên mang tên `displayName`. Nếu tên cột hoặc field trong kho khác tên Java, metadata ánh xạ của module chịu trách nhiệm nối hai phía.

Ví dụ riêng cho Spring Data Relational:

~~~java
package com.acme.mapping;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profile")
public final class CustomerProfileRow {

    @Id
    private final Long id;

    @Column("display_name")
    private final String displayName;

    public CustomerProfileRow(Long id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Trong mô hình này, cột `display_name` được ánh xạ vào thuộc tính Java `displayName`. Tham số constructor tiếp tục dùng tên Java `displayName`; không đổi nó thành `display_name` chỉ để giống tên cột.

Annotation `@Column` trong ví dụ thuộc Spring Data Relational, không phải `jakarta.persistence.Column`. Phạm vi và ý nghĩa ánh xạ được mô tả tại [Mapping của Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html).

Tương tự, nếu module document dùng một annotation đổi tên field, cần dùng đúng annotation và quy tắc của module đó.

### 8.2. Metadata tên tham số phải có sau khi biên dịch

Nhìn thấy tên đẹp trong source Java chưa chứng minh runtime đọc được tên ấy.

Với lớp Java thông thường, nên cấu hình biên dịch giữ tên tham số bằng tùy chọn `-parameters`. Việc này quan trọng cho cả constructor lẫn static factory dựa vào tên tham số. Cần áp dụng cho artifact chứa mô hình miền, kể cả khi mô hình đến từ thư viện riêng.

Một khả năng khác cho constructor là cung cấp `@ConstructorProperties`:

~~~java
package com.acme.mapping;

import java.beans.ConstructorProperties;

public final class NamedSnapshot {

    private final String id;
    private final String displayName;

    @ConstructorProperties({"id", "displayName"})
    public NamedSnapshot(String storedId, String label) {
        this.id = storedId;
        this.displayName = label;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Danh sách annotation mô tả tương ứng theo thứ tự: tham số thứ nhất gắn với `id`, tham số thứ hai gắn với `displayName`. Đây là metadata về tên, không phải một chỉ thị chọn constructor giữa nhiều constructor.

`@ConstructorProperties` chỉ áp dụng cho constructor, không gắn nó lên static factory. Xem [ConstructorProperties của Java](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/beans/ConstructorProperties.html).

Với factory `rehydrate` ở phần 5, giữ metadata tên tham số của method là lựa chọn phù hợp. Tránh dùng các tên như `arg0`, `value1` rồi kỳ vọng mapper hiểu đó là thuộc tính nào.

### 8.3. Tham số creator không phải dependency được inject tùy ý

Theo hợp đồng `@PersistenceCreator`, tham số phải liên hệ với persistent property hoặc có cách cung cấp giá trị tường minh như `@Value` theo cơ chế hỗ trợ. Xem [PersistenceCreator API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/PersistenceCreator.html).

Do đó, không đánh dấu factory nghiệp vụ sau rồi kỳ vọng `Clock` được inject như vào một service:

~~~java
// Phác thảo không phù hợp nếu clock không phải thuộc tính được ánh xạ:
//
// @PersistenceCreator
// public static TaskSnapshot open(String id, Clock clock) {
//     return new TaskSnapshot(id, "OPEN", clock.instant());
// }
~~~

Một bean `Clock` có trong application context không tự biến thành giá trị của tham số creator này.

Nếu dùng biểu thức `@Value`, phải kiểm tra cú pháp và nguồn dữ liệu theo module cụ thể. Bài này không cần biểu thức để giải quyết lựa chọn creator.

## 9. Dữ liệu thiếu, null và kiểu đầu vào

Cần phân biệt ít nhất ba tình huống:

| Tình huống | Câu hỏi cần giải quyết |
| --- | --- |
| Không tìm được tên thuộc tính cho tham số | Metadata tên tham số và mô hình persistent property có đúng không |
| Có thuộc tính nhưng nguồn dữ liệu không cung cấp giá trị | Truy vấn, dữ liệu lịch sử và chính sách của converter xử lý thế nào |
| Có giá trị nhưng không chuyển sang kiểu tham số được | Kiểu lưu trữ, converter và kiểu Java có tương thích không |

Ví dụ creator nhận `Instant createdAt`, nhưng nguồn lưu trữ chứa chuỗi không chuyển đổi được. Thêm `@PersistenceCreator` không sửa được dữ liệu thời gian sai định dạng.

Nếu creator yêu cầu một giá trị không null và bên trong gọi `Objects.requireNonNull`, dữ liệu null sẽ khiến việc khởi tạo thất bại. Không nên diễn giải mọi lỗi từ constructor thành “Spring Data không tìm thấy constructor”.

Với primitive như `long revision`, không thể truyền null như một tham chiếu Java thông thường. Không mặc định rằng mọi mapper sẽ thay trường thiếu bằng số không. Hành vi còn phụ thuộc nguồn giá trị và converter của module.

Với một truy vấn chỉ trả về một phần dữ liệu, cần kiểm tra kiểu kết quả có còn đòi những tham số không được cung cấp hay không. Một DTO chuyên cho màn hình danh sách thường biểu đạt dữ liệu ít trường rõ ràng hơn việc phục hồi nửa vời một aggregate yêu cầu đủ trạng thái.

Cũng không suy rằng giá trị mặc định của field luôn được giữ nguyên. Nếu constructor hoặc bước gán thuộc tính nhận giá trị từ dữ liệu, giá trị khởi tạo trong source có thể không quyết định kết quả cuối cùng.

## 10. Các annotation dễ bị nhầm vai trò

| Annotation hoặc cơ chế | Vai trò cần phân biệt |
| --- | --- |
| `@PersistenceCreator` | Chỉ định creator cho cơ chế mapping Spring Data hỗ trợ |
| `@ConstructorProperties` | Mô tả quan hệ tham số constructor với tên thuộc tính |
| `@Autowired` | Liên quan đến dependency injection của Spring bean |
| `@Bean` | Đăng ký đối tượng vào Spring application context |
| `@JsonCreator` | Liên quan đến cách Jackson tạo đối tượng |
| `@Id` | Đánh dấu định danh theo cơ chế mapping, không chọn constructor |

Một class có thể được nhiều framework sử dụng, nhưng không vì thế mà các framework chia sẻ cùng một thuật toán lựa chọn creator.

Nếu một thư viện JSON yêu cầu thêm constructor hoặc annotation, cần xem thay đổi ấy có ảnh hưởng tới lựa chọn của Spring Data hay không. Đôi khi tách DTO giao tiếp và mô hình persistence giúp hai hợp đồng ít tác động qua lại hơn.

Tương tự, constructor do công cụ sinh mã tạo ra vẫn là một phần của class sau biên dịch. Khi bật thêm tính năng sinh constructor, cần đánh giá số lượng và annotation của các constructor thực tế, không chỉ nhìn phần source viết tay.

## 11. Không khai báo creator mâu thuẫn

Các cấu hình sau cần được sửa ở thiết kế:

- Hai constructor cùng được đánh dấu `@PersistenceCreator`.
- Nhiều static factory cùng được đánh dấu cho một kiểu mà không có một lựa chọn duy nhất.
- Đánh dấu một instance method rồi coi nó là static factory.
- Creator có tham số không liên hệ với mô hình persistent và không có nguồn giá trị hợp lệ.
- Factory không trả về một instance hợp lệ của kiểu đang được phục hồi.

Không sử dụng thứ tự viết method trong file, tên method đứng trước theo bảng chữ cái hoặc thứ tự xuất hiện trong reflection để giải quyết những cấu hình ấy.

Nếu một lớp có cả constructor lẫn static factory được đánh dấu, nên làm rõ và đơn giản hóa chỉ định để người đọc nhận diện một đường phục hồi chủ đích. Không cần dựa vào một tổ hợp annotation khó hiểu khi một creator rõ ràng đã đáp ứng yêu cầu.

Ngoài việc chọn được creator, mapper còn cần khả năng truy cập và thực thi nó trong môi trường runtime. Hạn chế truy cập, cấu trúc inner class hoặc cơ chế module của Java có thể là những vấn đề riêng. Không đồng nhất “không đủ điều kiện dùng tối ưu sinh mã” với “chắc chắn không ánh xạ được”; cũng không dùng quyền truy cập rộng như một cách chữa mọi lỗi.

## 12. Creator phải giữ được ý nghĩa của dữ liệu đã lưu

Một creator đúng về mặt kỹ thuật vẫn có thể sai về mặt nghiệp vụ.

Xét một snapshot đơn hàng đã lưu:

~~~text
id        = ORD-24
status    = PAID
createdAt = một thời điểm đã xảy ra
~~~

Đường phục hồi hợp lý phải giữ được trạng thái `PAID` và thời điểm gốc, trừ khi hệ thống có một chính sách chuyển đổi dữ liệu rõ ràng.

Những thao tác cần cân nhắc kỹ trong constructor hoặc factory phục hồi gồm:

- Sinh lại định danh.
- Đặt lại trạng thái về mặc định của đối tượng mới.
- Tính lại thời điểm tạo bằng đồng hồ hiện tại.
- Ghi nhận người tạo từ người đang đọc dữ liệu.
- Áp quy tắc mới không tương thích với dữ liệu lịch sử.
- Tạo side effect bên ngoài quá trình khởi tạo đối tượng.

Auditing có vòng đời và cấu hình riêng theo module. Không dùng creator như một cách thay thế hạ tầng auditing, vì đọc lại đối tượng không đồng nghĩa với tạo mới đối tượng trong kho dữ liệu.

Lựa chọn creator cũng không quyết định chiến lược nhận diện entity mới, khóa lạc quan hoặc ngữ nghĩa insert/update. Đó là những trách nhiệm khác dù có thể cùng sử dụng metadata của mô hình.

## 13. Cách chẩn đoán lỗi theo từng lớp trách nhiệm

Khi một thao tác repository không đọc được đối tượng, có thể đi theo trình tự:

1. Xác định module nào thực sự materialize kiểu kết quả.
2. Liệt kê các constructor và static factory thực tế của class.
3. Xác định creator được kỳ vọng theo bảng quy tắc.
4. Kiểm tra annotation và metadata tên tham số của creator ấy.
5. Đối chiếu từng tham số với thuộc tính persistent và tên lưu trữ đã ánh xạ.
6. Kiểm tra dữ liệu nguồn cùng các phép chuyển đổi kiểu.
7. Kiểm tra exception do chính mã constructor hoặc factory ném ra.
8. Nếu khởi tạo đã xong, kiểm tra riêng bước gán thuộc tính còn lại.

Không chỉ dựa vào thông báo lỗi ngoài cùng. Exception có thể bị bọc; nguyên nhân bên trong mới cho biết đó là thiếu tên tham số, chuyển đổi thất bại hay một bất biến miền bị vi phạm.

Phương thức derived query, phân trang hoặc sắp xếp quyết định cách lấy tập kết quả. Chúng không làm cho một constructor không hợp lệ trở nên hợp lệ. Nếu truy vấn trả đúng dữ liệu nhưng không tạo được đối tượng, cần xử lý hợp đồng mapping ở lớp mô hình.

Đối với JPA, quay lại quy tắc của JPA provider và ánh xạ entity tương ứng thay vì thêm `@PersistenceCreator` theo suy đoán.

## 14. Các tình huống cần kiểm chứng khi áp dụng

Bảng dưới là kế hoạch kiểm chứng cho người học, chưa phải kết quả chạy thử của bài:

| Mô hình | Điều cần xác nhận khi đọc qua mapper thực |
| --- | --- |
| Một constructor và một factory nghiệp vụ không đánh dấu | Dữ liệu đi qua constructor persistence |
| Hai constructor, một constructor được đánh dấu | Giá trị đã lưu không bị thay bằng mặc định của constructor tiện dụng |
| Một factory tĩnh được đánh dấu | Factory phục hồi được sử dụng và nhận đúng các thuộc tính |
| Lớp mutable có constructor rỗng và constructor đầy đủ | Đường không tham số và bước gán thuộc tính hoạt động như dự kiến |
| Record có constructor tiện dụng | Revision đã lưu được giữ khi dùng canonical constructor |
| Tên cột khác tên thuộc tính | Giá trị được ánh xạ vào đúng tham số Java |
| Dữ liệu lịch sử thiếu trường hoặc có null | Hành vi lỗi hoặc chính sách tương thích đúng yêu cầu |
| Có nhiều creator được đánh dấu | Cấu hình mơ hồ được phát hiện, không phụ thuộc thứ tự tình cờ |

Gọi trực tiếp `new CustomerSnapshot(...)` chỉ kiểm tra được constructor Java. Gọi trực tiếp `TaskSnapshot.rehydrate(...)` chỉ kiểm tra được phần thân factory. Những lời gọi ấy chưa chứng minh mapper lựa chọn đúng creator.

Muốn xác nhận lựa chọn của framework, cần đọc một bản ghi đại diện qua converter hoặc repository của module đang dùng. Dữ liệu kiểm chứng nên có trạng thái và thời điểm khác mặc định, để phát hiện trường hợp vô tình gọi đường tạo mới.

## 15. Bài thực hành: tách tạo mới và phục hồi

Thiết kế `SubscriptionSnapshot` có bốn thuộc tính: `id`, `planCode`, `status`, `activatedAt`.

Yêu cầu:

1. Đường nghiệp vụ tạo subscription mới đặt trạng thái ban đầu theo quy tắc ứng dụng.
2. Đường phục hồi giữ nguyên trạng thái và thời điểm đã lưu.
3. Chỉ có một chỉ định persistence creator rõ ràng.
4. Mọi tham số phục hồi có nguồn từ thuộc tính persistent tương ứng.
5. Không đưa service hoặc repository vào danh sách tham số creator để chờ inject.
6. Khi thêm một constructor tiện dụng, giải thích được nó có làm thay đổi đường chọn creator hay không.

Dùng dữ liệu mẫu có trạng thái `ACTIVE` và thời điểm kích hoạt trong quá khứ để kiểm chứng. Nếu đọc lại thành trạng thái ban đầu hoặc thời điểm hiện tại, cần sửa đường phục hồi thay vì coi việc tạo được instance là đã đúng.
