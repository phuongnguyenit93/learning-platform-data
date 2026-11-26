# Chọn constructor bằng @PersistenceCreator khi cần

Trong chương **DTO và projection động** của module **SPRING_DATA_COMMONS**, class-based projection dùng một kiểu DTO để biểu diễn các giá trị đọc từ repository. Khi DTO có nhiều constructor, cần làm rõ constructor nào mô tả dữ liệu của projection, thay vì để các overload phục vụ tiện ích làm mờ hợp đồng đọc.

**Dùng `@PersistenceCreator` trên constructor cần Spring Data nhận diện khi việc chọn constructor không còn đơn nghĩa.** Annotation này giải quyết việc chỉ định creator; tên tham số, kiểu dữ liệu và cách truy vấn cung cấp đối số vẫn phải phù hợp. Việc tạo instance thực tế còn phụ thuộc module store và loại truy vấn.

## 1. Constructor tham gia vào projection như thế nào?

Với DTO projection, constructor không chỉ là một cách gọi `new`. Chữ ký constructor còn mô tả các giá trị mà kiểu kết quả cần nhận.

Giả sử một domain type `Customer` đã được ánh xạ và có các property:

| Property | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Mã khách hàng |
| `fullName` | `String` | Tên hiển thị |
| `email` | `String` | Email liên hệ |
| `active` | `boolean` | Trạng thái hoạt động |
| `internalNote` | `String` | Ghi chú nội bộ không cần cho danh sách liên hệ |

DTO danh sách liên hệ cần ba giá trị:

```text
CustomerContactDto(Long id, String fullName, String email)
```

Cần phân biệt ba việc:

| Việc cần xác định | Câu hỏi |
| --- | --- |
| Chọn constructor | Constructor nào là hợp đồng tạo DTO cho projection? |
| Xác định dữ liệu đầu vào | Cần các property nào từ domain hoặc query? |
| Truyền đối số | Giá trị nào đi vào tham số nào, với kiểu dữ liệu nào? |

Chọn đúng constructor không tự hoàn thành hai việc còn lại.

Spring Data mô tả class-based projection bằng các kiểu giá trị được khởi tạo qua constructor; khi store tối ưu lượng dữ liệu đọc, tên tham số constructor có thể được dùng để xác định các thuộc tính cần lấy. Xem [Class-based Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.dtos).

Khác với interface projection, ở đây kết quả là instance của DTO. Không cần tạo một proxy interface để cung cấp các getter cho DTO đó.

## 2. Khi nào cần @PersistenceCreator?

`@PersistenceCreator` thuộc package:

```java
import org.springframework.data.annotation.PersistenceCreator;
```

Đây là marker annotation của Spring Data để chỉ định constructor hoặc factory method được ưu tiên trong cơ chế có hỗ trợ creator metadata. Xem [API PersistenceCreator](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/PersistenceCreator.html).

Trong phạm vi DTO projection, lựa chọn thực tế thường là:

| Hình dạng kiểu DTO | Hướng xử lý |
| --- | --- |
| Class chỉ có một constructor phù hợp | Thường không cần thêm annotation chỉ để chọn constructor |
| Class có nhiều constructor phục vụ các nhu cầu khác nhau | Đánh dấu constructor dùng cho projection |
| Java record thông thường | Canonical constructor đã thể hiện các component; thường không cần annotation |
| Class có cả constructor rỗng và constructor nhận dữ liệu | Làm rõ constructor nhận dữ liệu khi dùng cơ chế suy luận DTO |
| Truy vấn đã có constructor expression rõ ràng | Vẫn phải kiểm tra hợp đồng đối số của biểu thức; annotation không thay biểu thức đó |

Không áp dụng quy tắc “constructor có nhiều tham số nhất luôn được chọn”. Cũng không dựa vào thứ tự khai báo constructor trong mã nguồn.

Trong cơ chế khám phá constructor Java của Commons, có các nhánh nhận diện constructor được đánh dấu, constructor rỗng và các ứng viên khác. Có thể xem [PreferredConstructorDiscoverer](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/mapping/model/PreferredConstructorDiscoverer.java). Đối với projection, nên chủ động biểu đạt ý định thay vì dựa vào một fallback không phục vụ nhu cầu đọc.

Đặc biệt, thêm một constructor rỗng không phải cách bảo đảm Spring Data sẽ chọn constructor nhận đủ dữ liệu. Nó có thể làm việc suy luận hợp đồng constructor thay đổi theo đường xử lý đang dùng.

## 3. DTO có nhiều constructor: đánh dấu đúng một đường tạo

Đặt DTO minh họa trong package `com.example.read`:

```java
package com.example.read;

import org.springframework.data.annotation.PersistenceCreator;

public final class CustomerContactDto {

    private final Long id;
    private final String fullName;
    private final String email;

    @PersistenceCreator
    public CustomerContactDto(
            Long id,
            String fullName,
            String email) {

        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public CustomerContactDto(Long id, String fullName) {
        this(id, fullName, null);
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
```

Class có hai constructor hợp lệ trong Java:

- Constructor ba tham số thể hiện dữ liệu đầy đủ của góc nhìn liên hệ.
- Constructor hai tham số phục vụ mã ứng dụng khi chưa cung cấp email; nó không phải hợp đồng đọc danh sách liên hệ trong ví dụ.

Annotation nằm trên constructor ba tham số để thể hiện constructor cần được nhận diện cho projection. Chỉ đánh dấu một creator có chủ đích trong thiết kế này.

Các getter giúp bên sử dụng đọc dữ liệu, nhưng không thay thế chữ ký constructor khi framework đang suy luận đầu vào từ constructor. Việc có đủ getter không làm cho hai overload tự trở thành một hợp đồng duy nhất.

### Annotation không thay đổi lời gọi new của Java

Mã ứng dụng vẫn có thể gọi:

```java
CustomerContactDto local =
        new CustomerContactDto(7L, "Linh Nguyen");
```

Ở đây Java chọn overload hai tham số theo lời gọi đã viết. `@PersistenceCreator` không chuyển lời gọi đó sang một overload khác.

Điều tương tự áp dụng cho lời gọi thủ công từ mapper hoặc factory của ứng dụng. Annotation cung cấp metadata cho cơ chế Spring Data có sử dụng nó; nó không thay quy tắc overload resolution của ngôn ngữ Java.

### Constructor nên giữ hợp đồng ánh xạ dễ hiểu

Constructor nhận dữ liệu nên có tên và kiểu tham số rõ ràng, rồi gán chúng vào trạng thái DTO. Tránh đưa thao tác gọi dịch vụ, truy vấn thêm dữ liệu hoặc các tác động phụ vào constructor chỉ để tạo kết quả đọc.

Nếu constructor có kiểm tra dữ liệu, cần xác định rõ các giá trị null hoặc giá trị không hợp lệ có thể đến từ nguồn. Một exception do chính constructor ném ra là vấn đề dữ liệu hoặc quy tắc khởi tạo, không nhất thiết là lỗi chọn constructor.

## 4. Dùng cùng DTO trong projection cố định và projection động

Giả sử `Customer` là domain type trong package repository hiện tại, có các property ở mục 1. Repository được đặt trong ứng dụng đã cấu hình một store hỗ trợ dạng projection này:

```java
import java.util.List;

import com.example.read.CustomerContactDto;

import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {

    List<CustomerContactDto> findByActiveTrueOrderByIdAsc();

    <T> List<T> findByActiveTrueOrderByIdAsc(Class<T> projectionType);
}
```

Hai lời gọi minh họa:

```java
List<CustomerContactDto> fixed =
        repository.findByActiveTrueOrderByIdAsc();

List<CustomerContactDto> dynamic =
        repository.findByActiveTrueOrderByIdAsc(
                CustomerContactDto.class);
```

Ở phương thức đầu, kiểu DTO đã có trong chữ ký. Ở phương thức thứ hai, bên gọi cung cấp `Class<T>` để chọn kiểu kết quả lúc gọi. Cơ chế projection động được mô tả trong [Dynamic Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projection.dynamic).

Trong cả hai trường hợp, `CustomerContactDto` vẫn phải có hợp đồng tạo đối tượng phù hợp. Truyền `CustomerContactDto.class` không chỉ định một overload constructor cụ thể, cũng không bỏ qua yêu cầu về tên và kiểu tham số.

Với dữ liệu giả định:

```text
id       = 7
fullName = "Linh Nguyen"
email    = "linh@example.test"
active   = true
```

Hợp đồng projection mong muốn truyền các giá trị tương ứng vào constructor ba tham số. Việc query có được thu hẹp thành đúng ba thuộc tính hay không cần được xác nhận ở store, loại query và phiên bản dự án; annotation tự nó không phải một phép đo hoặc bảo đảm tối ưu.

## 5. Tên tham số, kiểu và thứ tự là các yêu cầu riêng

### Tên tham số cần đọc được khi framework suy luận property

Trong DTO mẫu, các tên `id`, `fullName` và `email` khớp property của `Customer`. Nếu đổi tham số thành `customerCode`, `label`, `contact` chỉ vì thấy tên đó đẹp hơn, đường suy luận theo tên không tự biết các tên mới tương ứng với property nào.

Triển khai metadata kiểu trả về của Commons khám phá constructor và lấy tên tham số làm các input property cho DTO. Xem [ReturnedType](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/query/ReturnedType.java).

Với class Java thông thường, cần giữ thông tin tên tham số trong kết quả biên dịch khi cơ chế đang dùng cần đọc nó. Tùy chọn compiler `-parameters` lưu tên tham số để reflection có thể lấy lại. Xem [tài liệu javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).

`@PersistenceCreator` không tự bổ sung tên tham số bị thiếu vào bytecode. Có thể đã chọn đúng constructor nhưng vẫn chưa suy luận được các property đầu vào.

### Tên property khác tên cột hoặc field vật lý

Nếu domain property là `fullName` nhưng cột trong cơ sở dữ liệu là `full_name`, không vì vậy đổi tham số constructor DTO thành `full_name` trong ví dụ derived query.

Hãy dùng property của mô hình trong hợp đồng suy luận và để cơ chế mapping của store xử lý tên lưu trữ theo khả năng của nó. Native query là một ngữ cảnh khác, cần xem riêng tên, kiểu và thứ tự kết quả.

### Kiểu tương thích không bảo đảm ý nghĩa đúng

Hai giá trị đều là `String` có thể bị đảo mà vẫn phù hợp chữ ký Java. Constructor đúng về mặt kiểu vẫn có thể nhận sai nội dung nếu biểu thức truy vấn truyền sai thứ tự.

Vì vậy, kiểm tra riêng:

1. Creator có đúng constructor cần dùng không?
2. Tên tham số có biểu đạt đúng dữ liệu trong cơ chế suy luận không?
3. Kiểu và số lượng giá trị có phù hợp không?
4. Thứ tự truyền đối số có đúng với loại truy vấn đang dùng không?

## 6. Phân biệt creator metadata với cách JPA gọi constructor

Với Spring Data JPA, cần phân biệt query được suy ra hoặc được viết lại để tạo DTO với query đã khai báo rõ constructor expression. Tài liệu JPA hướng dẫn dùng `@PersistenceCreator` khi DTO có nhiều constructor; đồng thời nêu rằng query đã có constructor expression thì không tiếp tục được viết lại theo cơ chế DTO đó. Xem [DTO Projections với JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html).

Ví dụ JPA riêng, tiếp tục dùng DTO ở package `com.example.read`:

```java
import java.util.List;

import com.example.read.CustomerContactDto;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;

public interface JpaCustomerContactRepository
        extends Repository<Customer, Long> {

    @Query("""
            select new com.example.read.CustomerContactDto(
                c.id, c.fullName, c.email
            )
            from Customer c
            where c.active = true
            order by c.id
            """)
    List<CustomerContactDto> findActiveContacts();
}
```

Ví dụ dùng Java 17 trở lên cho text block, một JPA entity mang tên `Customer` và các property đã nêu. Tên class DTO đầy đủ trong biểu thức phải khớp package thực tế.

Ở đây biểu thức đã ghi rõ:

```text
new CustomerContactDto(c.id, c.fullName, c.email)
```

Provider phải tìm được constructor phù hợp với các đối số của biểu thức. `@PersistenceCreator` không tự đổi vị trí các biểu thức, không thêm đối số bị thiếu và không biến kiểu không tương thích thành hợp lệ.

### Ví dụ sai ý nghĩa nhưng có thể đúng kiểu

Biểu thức sau đảo email và tên:

```text
new com.example.read.CustomerContactDto(
    c.id, c.email, c.fullName
)
```

Cả hai giá trị sau cùng đều là `String`, nên chữ ký có thể vẫn khớp `(Long, String, String)`. Tuy nhiên, ý nghĩa bị đảo:

| Tham số constructor | Giá trị mong muốn | Giá trị truyền từ biểu thức sai |
| --- | --- | --- |
| `id` | `c.id` | `c.id` |
| `fullName` | `c.fullName` | `c.email` |
| `email` | `c.email` | `c.fullName` |

Đánh dấu constructor đúng không sửa lỗi này. Cần sửa chính biểu thức truy vấn.

Nếu constructor có hai tham số để phục vụ mã ứng dụng, một constructor expression hai đối số cũng không tự được đổi thành ba đối số chỉ vì constructor ba tham số được đánh dấu. Phải xem hợp đồng rõ ràng của biểu thức đang viết.

### Với native query, annotation không thay mapping kết quả

Khi dùng truy vấn native, cần kiểm tra các cột kết quả, kiểu Java nhận được và thứ tự hoặc cơ chế result mapping mà JPA/provider hỗ trợ. Nếu dùng `@SqlResultSetMapping`, cấu hình đó vẫn phải đúng.

Không xem `@PersistenceCreator` là cách tự động ánh xạ mọi `Object[]`, tuple hay map bất kỳ thành DTO. Nó chọn hoặc chỉ rõ creator trong đường xử lý có dùng metadata đó; nó không định nghĩa toàn bộ hợp đồng của kết quả native.

## 7. Java record thường làm hợp đồng constructor đơn giản hơn

Nếu DTO chỉ là một tập giá trị, record có thể là lựa chọn gọn:

```java
package com.example.read;

public record CustomerContactRecord(
        Long id,
        String fullName,
        String email) {
}
```

Record thể hiện trực tiếp ba component và canonical constructor tương ứng. Trong trường hợp thông thường này, không cần thêm `@PersistenceCreator` chỉ để xác nhận lại canonical constructor.

Có thể có constructor tiện ích:

```java
package com.example.read;

public record CustomerContactRecord(
        Long id,
        String fullName,
        String email) {

    public CustomerContactRecord(Long id, String fullName) {
        this(id, fullName, null);
    }
}
```

Cơ chế khám phá constructor của Commons có xử lý riêng cho record để nhận diện canonical constructor. Vì vậy, không chuyển máy móc quy tắc cho class nhiều constructor sang kết luận rằng mọi record có overload đều phải đánh dấu thêm creator.

Record không xóa các yêu cầu mapping: tên component, kiểu giá trị và hợp đồng truy vấn vẫn phải phù hợp. Nếu dùng constructor expression tường minh, đối số của biểu thức vẫn cần đúng như với class.

Khi chọn class hay record, cân nhắc nhu cầu của kiểu dữ liệu. Một class có nhiều đường tạo hợp lệ vẫn có thể là thiết kế phù hợp; `@PersistenceCreator` giúp biểu đạt rõ đường tạo dành cho Spring Data khi cần.

## 8. Không trộn quy tắc DTO với mọi cơ chế tạo đối tượng

Spring Data có tài liệu object mapping với quy tắc chọn constructor hoặc static factory cho các module tự thực hiện mapping, chẳng hạn MongoDB, Redis, Cassandra và Relational. Phần tài liệu này nêu rõ JPA ủy quyền việc mapping entity cho JPA provider. Xem [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html).

Điều này quan trọng vì cùng một annotation có thể xuất hiện trong nhiều ngữ cảnh, nhưng không phải mọi ngữ cảnh đều đi qua cùng thuật toán.

| Ngữ cảnh | Điều cần xác định |
| --- | --- |
| DTO projection suy luận từ constructor | Constructor nào và các input property nào được nhận diện |
| JPQL constructor expression | Class, số lượng, kiểu và thứ tự đối số trong biểu thức |
| Native query | Cơ chế mapping kết quả của store/provider |
| Entity materialization ở module tự mapping | Quy tắc creator và property mapping của module |
| Interface projection | Cơ chế proxy/accessor, không phải chọn constructor DTO |
| Tạo Spring bean hoặc đọc JSON | Cơ chế tương ứng của framework đang xử lý đối tượng |

Một số giới hạn thực hành:

- API annotation cho phép đánh dấu factory method, nhưng không suy ra rằng mọi đường DTO projection sẽ gọi static factory đã đánh dấu. Cần kiểm tra cơ chế của module và loại query; ví dụ trong bài dùng constructor.
- Không đặt annotation lên getter rồi mong thay đổi constructor được chọn.
- Không dùng annotation này thay cho quy tắc tạo bean hoặc cấu hình giải tuần tự JSON.
- Không thêm `@Entity` cho DTO chỉ để chữa một lỗi ánh xạ constructor.
- Không suy từ yêu cầu constructor của DTO sang yêu cầu constructor của JPA entity.

Trong ví dụ, mục tiêu là một kiểu kết quả đọc có ba giá trị. Giữ mục tiêu đó rõ ràng sẽ tránh biến DTO thành một đối tượng vừa lưu trữ, vừa tạo bean, vừa làm hợp đồng phản hồi với các đường khởi tạo khó phân biệt.

## 9. Chẩn đoán lỗi theo đúng lớp nguyên nhân

Khi truy vấn trả DTO thất bại, không nên thêm annotation vào mọi constructor. Hãy xác định lỗi thuộc lớp nào:

| Biểu hiện | Câu hỏi cần kiểm tra |
| --- | --- |
| Không suy luận được constructor phù hợp | Có bao nhiêu constructor thực tế? Constructor mong muốn đã được chỉ rõ chưa? |
| Không xác định được property đầu vào | Tên tham số có được giữ khi biên dịch và có khớp domain property không? |
| Không tìm thấy constructor cho query | Số lượng, thứ tự và kiểu đối số của query có đúng không? |
| Kết quả có đủ field nhưng giá trị bị đảo | Các biểu thức cùng kiểu có đang bị đổi vị trí không? |
| Lỗi chỉ xảy ra với native query | Kết quả native và result mapping có phù hợp chữ ký DTO không? |
| Exception xuất phát bên trong constructor | Nguồn dữ liệu có vi phạm kiểm tra hoặc giả định của constructor không? |
| Projection động lỗi còn projection khác chạy được | Kiểu DTO được chọn có hợp đồng creator riêng đúng chưa? |

Một trình tự kiểm tra gọn cho `CustomerContactDto`:

1. Liệt kê constructor mà class thực sự có, kể cả constructor do công cụ sinh mã tạo ra.
2. Xác định constructor ba tham số là đường tạo cần cho projection.
3. Đặt `@PersistenceCreator` duy nhất trên đường tạo đó nếu cần làm rõ việc lựa chọn.
4. Kiểm tra tên `id`, `fullName`, `email` có thể được framework đọc trong cơ chế suy luận đang dùng.
5. Đối chiếu các tên đó với domain property và các biểu thức query.
6. Kiểm tra kiểu dữ liệu, đặc biệt giá trị số, giá trị null và các biểu thức tính toán.
7. Xác định thao tác tạo DTO do Spring Data, JPA constructor expression hay result mapping khác thực hiện.

Đây là trình tự tìm nguyên nhân cho người học khi tích hợp, không phải báo cáo chạy kiểm thử của tài liệu.

### Constructor rỗng không phải thuốc chữa chung

Một DTO đã có constructor nhận dữ liệu không cần thêm constructor rỗng chỉ vì query báo lỗi mapping. Hãy đọc lỗi và xác định đường xử lý trước.

Trong ví dụ, thêm constructor rỗng rồi gán các field thành null sẽ không giúp giải thích vì sao query cần `id`, `fullName` và `email`. Nó còn tạo thêm một trạng thái DTO không mang dữ liệu cần thiết.

### Không che lỗi bằng thay đổi kiểu quá rộng

Nếu getter hoặc field `id` đang dùng `Long`, đừng vội đổi thành `Object` chỉ để tránh lỗi tạo DTO. Hãy kiểm tra query thực tế trả gì và constructor mong đợi gì.

Tương tự, đổi tên tham số thành `arg0`, `arg1` không giải quyết việc thiếu metadata tên. Hợp đồng cần có ý nghĩa theo property; cấu hình biên dịch cần giữ thông tin mà cơ chế suy luận yêu cầu.

## 10. Bài thực hành: một creator rõ ràng cho một góc nhìn đọc

Dùng domain `Customer` với các property ở mục 1 và một store hỗ trợ DTO projection:

1. Tạo `CustomerContactDto` có constructor ba tham số và overload hai tham số như ví dụ.
2. Giải thích vì sao constructor ba tham số là hợp đồng đọc danh sách liên hệ.
3. Đánh dấu đúng constructor bằng `@PersistenceCreator`; xác định import của annotation.
4. Dùng DTO qua phương thức trả kiểu cố định và phương thức projection động nhận `Class<T>`.
5. Xác định cách dự án giữ tên tham số constructor khi biên dịch; không nhầm việc đó với đặt annotation.
6. Nếu dùng JPA, đối chiếu derived query với constructor expression tường minh.
7. Phân tích trường hợp đảo `fullName` và `email` trong constructor expression: vì sao có thể không có lỗi kiểu nhưng vẫn sai dữ liệu?
8. Viết phương án record và giải thích vì sao canonical constructor làm ý định rõ hơn.
9. Phân biệt lỗi chọn creator, lỗi tên property và lỗi thứ tự đối số.

Kết quả cần đạt là một DTO có đường tạo phục vụ projection được nhận diện rõ, cùng hợp đồng dữ liệu đúng cho truy vấn đang dùng. `@PersistenceCreator` là công cụ chỉ định creator khi cần; tính đúng đắn của projection còn nằm ở metadata tham số, dữ liệu nguồn và cơ chế thực thi của từng store.