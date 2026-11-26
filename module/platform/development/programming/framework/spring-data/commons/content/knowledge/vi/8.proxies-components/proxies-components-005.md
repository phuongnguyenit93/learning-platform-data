# Thứ tự điều phối khi nhiều thành phần cùng có một phương thức

Một repository Spring Data có thể được cấu thành từ implementation chuẩn của store, các thành phần mở rộng do module cung cấp và nhiều fragment tùy chỉnh. Khi nhiều thành phần cùng có một phương thức phù hợp, repository proxy phải xác định nơi thực thi lời gọi.

Trong cơ chế composition của Spring Data, fragment tùy chỉnh được ưu tiên hơn implementation base và các repository aspect tương ứng. Khi nhiều custom fragment cùng đóng góp một chữ ký phương thức, thứ tự khai báo fragment là một phần quan trọng của hợp đồng điều phối: fragment phù hợp được đặt trước sẽ được chọn trước.

Bài học thuộc chương **Proxy và thành phần**, trình bày cách đọc thứ tự này, tạo ví dụ có thể quan sát và tránh nhầm lẫn giữa chọn implementation với chuỗi interceptor, truy vấn khai báo hoặc quy tắc default method của Java.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt repository proxy, fragment, implementation base và interceptor bao quanh lời gọi.
- Dự đoán kết quả khi hai fragment cùng có một phương thức.
- Giải thích vì sao fragment có thể ghi đè một phương thức CRUD chuẩn.
- Nhận ra việc chọn một fragment không có nghĩa mọi fragment đều được gọi.
- Phân biệt trùng implementation của một fragment với trùng phương thức giữa hai fragment.
- Thiết kế kiểm tra điều phối có ý nghĩa và giữ rõ các giới hạn theo module store.

## 2. Một repository không nhất thiết chỉ có một target đơn giản

Xét một repository được tạo từ các phần:

```text
Repository interface
        |
        v
Repository proxy
        |
        +-- xử lý lời gọi và các interceptor liên quan
        |
        v
Composition của các implementation
        +-- custom fragment A
        +-- custom fragment B
        +-- thành phần mở rộng của module, nếu có
        +-- implementation base của store
```

Implementation base cung cấp những thao tác chuẩn mà module hỗ trợ. Custom fragment bổ sung hoặc thay thế hành vi cho những phương thức nhất định. Thành phần mở rộng của module có thể cung cấp một nhóm khả năng khác, chẳng hạn executor truy vấn tương ứng khi được cấu hình.

Trong tài liệu Spring Data, có thể gặp thuật ngữ **repository aspect** cho những thành phần khả năng được đưa vào repository. Không nên mặc định thuật ngữ này có cùng vai trò với một Spring AOP advice ghi log hoặc đo thời gian.

Cần tách hai câu hỏi:

1. Lời gọi được bao quanh bởi những xử lý nào, chẳng hạn giao dịch hoặc chuyển đổi exception?
2. Implementation nào thực hiện phương thức mà repository đang điều phối?

Một lời gọi có thể đi qua nhiều interceptor nhưng chỉ chọn một implementation fragment để thực thi phần thân phương thức đó.

## 3. Quy tắc ưu tiên trong composition

Với một phương thức được nhận diện là implementation method và có các fragment tùy chỉnh phù hợp, có thể đọc thứ tự như sau:

| Nhóm | Cách hiểu |
| --- | --- |
| Custom fragment | Có ưu tiên cao hơn implementation base và repository aspect tương ứng |
| Nhiều custom fragment cùng phù hợp | Thứ tự khai báo fragment quyết định fragment được xét trước |
| Thành phần do module cung cấp | Được phối hợp theo repository factory và composition của module |
| Implementation base | Cung cấp hành vi chuẩn khi phương thức được định tuyến tới base và không bị custom fragment phù hợp ghi đè |

Quy tắc quan trọng nhất cho mã ứng dụng là **custom fragment đứng trước có thể quyết định hành vi khi chữ ký trùng nhau**.

Đây không phải quy tắc sắp xếp toàn bộ bean trong container theo tên. Cũng không phải một cam kết rằng mọi interceptor, default method và query method đều nằm chung một danh sách có thể đọc bằng thứ tự `extends`.

Ví dụ chính trong bài dùng phương thức abstract được thực hiện bởi custom fragments. Điều đó giúp quan sát trực tiếp cơ chế composition.

## 4. Ví dụ: hai fragment cùng có `describe`

Giả sử mô hình `Customer` được mapping cho MongoDB và repository dùng `MongoRepository`. Các kiểu public dưới đây đặt trong file riêng, cùng package `example.customer.repository`, trừ mô hình miền được import.

### 4.1. Fragment phục vụ mô tả hiển thị

```java
package example.customer.repository;

public interface DisplayDescription {
    String describe(String customerId);
}
```

Implementation theo quy ước hậu tố `Impl` của fragment:

```java
package example.customer.repository;

public class DisplayDescriptionImpl implements DisplayDescription {
    @Override
    public String describe(String customerId) {
        return "display:" + customerId;
    }
}
```

### 4.2. Fragment phục vụ mô tả kiểm tra

```java
package example.customer.repository;

public interface AuditDescription {
    String describe(String customerId);
}
```

Implementation:

```java
package example.customer.repository;

public class AuditDescriptionImpl implements AuditDescription {
    @Override
    public String describe(String customerId) {
        return "audit:" + customerId;
    }
}
```

Hai phương thức có cùng tên, cùng kiểu tham số và cùng kiểu trả về. Java cho phép repository kế thừa các khai báo abstract tương thích như vậy.

### 4.3. Repository khai báo fragment theo một thứ tự

```java
package example.customer.repository;

import example.customer.model.Customer;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String>,
                DisplayDescription,
                AuditDescription {
}
```

Khi các implementation đã được phát hiện và composition được tạo đúng, lời gọi:

```java
String result = repository.describe("c-001");
```

có kết quả mong đợi:

```text
display:c-001
```

`DisplayDescription` được khai báo trước `AuditDescription` trong nhóm custom fragment, nên implementation phù hợp của nó được chọn trước.

Việc `MongoRepository` xuất hiện trước trong dòng `extends` không có nghĩa base implementation được ưu tiên trước custom fragment. Cần đọc theo cơ chế composition của Spring Data, không chỉ như một danh sách mọi interface Java được ưu tiên từ trái sang phải.

### 4.4. Đổi thứ tự hai fragment

Nếu thay phần khai báo của cùng repository bằng:

```java
public interface CustomerRepository
        extends MongoRepository<Customer, String>,
                AuditDescription,
                DisplayDescription {
}
```

thì kết quả mong đợi đổi thành:

```text
audit:c-001
```

Đây là phương án thay thế cho khai báo trước, không phải yêu cầu tạo thêm một repository cùng tên.

Thay đổi thứ tự fragment có thể thay đổi hành vi runtime mà không làm lỗi biên dịch. Vì vậy, với chữ ký trùng có chủ đích, thứ tự kế thừa cần được xem như một quyết định thiết kế có ảnh hưởng.

## 5. Điều kiện để ví dụ thực sự đi qua repository proxy

Việc tự tạo `new DisplayDescriptionImpl()` rồi gọi `describe` chỉ kiểm tra implementation đó. Nó không kiểm tra Spring Data đã phát hiện và sắp xếp fragment như thế nào.

Để quan sát composition trong một ứng dụng thực hành cần:

- Store module và bộ dependency tương thích.
- Domain được mapping phù hợp.
- Repository scanning được kích hoạt cho package repository.
- Fragment implementation được nhận diện theo quy ước hoặc cấu hình tương ứng.
- Hạ tầng store cần thiết để tạo repository.
- Lời gọi đi qua bean repository do Spring Data cung cấp.

Một mô hình MongoDB tối thiểu để minh họa metadata:

```java
package example.customer.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private String id;

    private String name;

    protected Customer() {
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Một cấu hình kích hoạt có thể là:

```java
import example.customer.repository.CustomerRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(basePackageClasses = CustomerRepository.class)
public class CustomerRepositoriesConfiguration {
}
```

Cấu hình giả định template/client MongoDB phù hợp đã có và lớp cấu hình được context nạp. Phương thức `describe` trong ví dụ trả chuỗi để quan sát điều phối; nó không thực hiện thao tác đọc/ghi document.

Nếu dự án đổi hậu tố tìm implementation hoặc đăng ký implementation tường minh, cần bảo đảm các fragment được ghép đúng trước khi phân tích thứ tự gọi.

## 6. Chọn một implementation không có nghĩa gọi cả hai

Ở khai báo `DisplayDescription` trước, luồng khái quát là:

```text
repository.describe("c-001")
        -> tìm implementation phù hợp theo composition
        -> chọn DisplayDescriptionImpl.describe
        -> trả "display:c-001"
```

Không mặc định có luồng:

```text
DisplayDescriptionImpl.describe
        -> AuditDescriptionImpl.describe
        -> ghép hai kết quả
```

Fragment thứ hai không tự được gọi để bổ sung tác dụng phụ hoặc kết quả cho cùng một lời gọi.

Điều này quan trọng khi tên fragment tạo cảm giác nó là một bước bắt buộc. Nếu một fragment thực hiện kiểm tra hoặc ghi audit mà nằm sau một fragment khác có cùng chữ ký, không thể dựa vào việc nó được khai báo trong repository để kết luận bước đó luôn chạy.

Nếu nghiệp vụ cần cả mô tả hiển thị và ghi nhận kiểm tra, có thể:

- Dùng hai phương thức có tên rõ vai trò, chẳng hạn `describeForDisplay` và `describeForAudit`.
- Viết service điều phối hai thao tác.
- Viết một implementation kết hợp có dependency tới các thành phần riêng và gọi chúng tường minh.
- Dùng advice phù hợp nếu nhu cầu thật sự là hành vi bao quanh lời gọi, với cấu hình và phạm vi rõ ràng.

Chọn giải pháp theo ý nghĩa hành vi, không theo mong muốn tận dụng một xung đột chữ ký.

## 7. Không có fallback tự động khi fragment đã được chọn

Một số suy luận dễ sai:

| Hành vi của fragment được chọn | Điều không được mặc định |
| --- | --- |
| Trả `null` | Proxy sẽ thử fragment tiếp theo |
| Ném `UnsupportedOperationException` | Proxy sẽ chuyển sang base implementation |
| Ném lỗi truy cập dữ liệu | Một fragment khác tự thực hiện lại thao tác |
| Chỉ ghi log rồi trả về | Phần thân base method vẫn sẽ chạy sau đó |

Khi một implementation phù hợp đã được chọn và thực thi, kết quả hoặc exception của đường thực thi đó được xử lý theo cơ chế repository/proxy. Composition không tự hiểu `null` là “tôi không xử lý được, mời thử thành phần kế tiếp”.

Nếu cần fallback, phải định nghĩa điều kiện và triển khai nó tường minh. Khi fallback có thao tác ghi, còn cần xem một phần công việc đã xảy ra hay chưa để tránh thực hiện lặp ngoài ý muốn.

Tương tự, không coi thứ tự fragment là một cơ chế thử lại khi lỗi. Retry và lựa chọn implementation là hai quyết định khác nhau.

## 8. Custom fragment có thể ghi đè phương thức CRUD chuẩn

Một nhu cầu phổ biến là thêm quy tắc quanh thao tác `save`. Fragment có thể khai báo chữ ký tương ứng:

```java
public interface CustomizedSave<T> {
    <S extends T> S save(S entity);
}
```

Repository lựa chọn fragment:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String>,
                CustomizedSave<Customer> {
}
```

Trong phương án này cần có implementation của `CustomizedSave` được ghép đúng. Chữ ký `save` phù hợp cho phép custom fragment được ưu tiên hơn phương thức base tương ứng.

Đoạn khai báo chỉ thể hiện hợp đồng và cơ chế ghi đè. Nó chưa cung cấp thuật toán lưu dữ liệu. Implementation phải thực hiện kiểm tra, thao tác persistence và trả kết quả phù hợp với mục tiêu của ứng dụng.

### 8.1. Khớp phương thức là vấn đề chữ ký, không chỉ tên

Cần đối chiếu:

- Tên phương thức.
- Danh sách và kiểu tham số.
- Generic và cách phương thức được ánh xạ trên domain cụ thể.
- Kiểu trả về tương thích theo quy tắc Java và API repository.

Không đổi thành `save(Object value)` hoặc một phương thức gần giống rồi mặc định nó ghi đè đúng thao tác mà bên gọi dùng. Với generic, cần đặc biệt chú ý erasure, bridge method và chữ ký hợp đồng gốc.

Dùng `@Override` ở implementation để trình biên dịch hỗ trợ kiểm tra phần implementation. Sau đó vẫn cần xác nhận composition của repository bằng một lời gọi thực tế.

### 8.2. Ghi đè nghĩa là chịu trách nhiệm về semantics

Nếu custom implementation thay đường lưu, cần đánh giá:

- Cách xác định thực thể mới hoặc đã tồn tại.
- ID, version và kết quả trả về sau lưu.
- Callback, auditing và converter liên quan.
- Giao dịch và cơ chế kiểm soát cập nhật cạnh tranh.
- Cách xử lý lỗi.

Một implementation gọi trực tiếp API store có thể có khác biệt so với base repository. Không nên tự coi nó là bản sao tương đương của mọi hành vi base nếu chưa xác định rõ đường thực thi.

Việc ghi đè `save` cũng không mặc định ghi đè `saveAll`, các thao tác cập nhật đặc thù hoặc mọi đường ghi khác. Nếu quy tắc phải áp dụng cho toàn bộ dữ liệu, hãy liệt kê các đường ghi cần được bao phủ.

## 9. Tránh gọi lại cùng proxy để tìm “base method”

Giả sử custom fragment xử lý `save` và lại gọi `repository.save(entity)` trên chính bean repository được inject vào nó.

Luồng có thể trở thành:

```text
repository.save
    -> custom fragment save
        -> repository.save
            -> custom fragment save
                -> ...
```

Đây là quay lại cùng cơ chế điều phối, không phải cách yêu cầu “gọi phần base tiếp theo”. Hậu quả có thể là đệ quy, vấn đề tạo bean hoặc hành vi không mong muốn.

Nếu cần ủy quyền, hãy dùng dependency có trách nhiệm rõ ràng, chẳng hạn một thành phần persistence riêng hoặc API thao tác store phù hợp. Với JPA có thể liên quan `EntityManager`; với MongoDB có thể liên quan `MongoOperations`. Semantics và giao dịch phải được thiết kế theo store.

Nếu nhu cầu là thay hành vi base cho nhiều repository, có thể cần cơ chế custom repository base class thay vì lắp một chuỗi fragment giả làm cơ chế `super`.

Cách mở rộng cụ thể phụ thuộc module. Không có một lời gọi “fragment tiếp theo” phổ quát mà chỉ cần gọi lại repository interface là đạt được.

## 10. Repository aspect khác với interceptor bao quanh lời gọi

Một module có thể cung cấp thành phần thực hiện một nhóm phương thức mở rộng. Trong composition, custom implementation có ưu tiên cao hơn các repository aspect tương ứng, theo cơ chế Spring Data hỗ trợ.

Trong khi đó, advice giao dịch, exception translation hoặc tracing có thể bao quanh quá trình gọi. Chúng không phải mặc định là các ứng viên thay nhau trả kết quả cho cùng một method trong danh sách fragment.

```text
Advice/interceptor bao quanh lời gọi
    -> điều phối phương thức
        -> implementation được chọn
    <- kết quả hoặc exception
<- xử lý sau lời gọi nếu cơ chế advice áp dụng
```

Do đó:

- Fragment được chọn không làm mọi interceptor khác tự biến mất.
- Advice chạy trước không đồng nghĩa implementation fragment của nó có ưu tiên cao hơn.
- `@Order` trên một thành phần AOP không mặc định thay đổi thứ tự custom fragment theo khai báo repository.
- Thay đổi fragment cần được kiểm tra cùng cấu hình giao dịch và tài nguyên thực tế khi hành vi có ghi dữ liệu.

Cần xem đúng cơ chế đang được cấu hình trước khi áp dụng một quy tắc thứ tự.

## 11. Default method và query method có đường xử lý riêng

### 11.1. Default method trước hết chịu quy tắc Java

Nếu hai interface không liên quan cung cấp cùng một default method xung đột, Java thường yêu cầu interface hoặc lớp kế thừa giải quyết xung đột bằng một khai báo phù hợp.

Không thể chờ Spring Data dùng thứ tự fragment để sửa một quan hệ kế thừa mà mã Java chưa biên dịch được.

Trong repository proxy, default method có cơ chế xử lý riêng. Không nên coi phần thân default method như một custom fragment implementation được tự xếp theo cùng quy tắc của ví dụ `describe`.

Nếu muốn hành vi được thay thế qua fragment, một abstract method cùng fragment implementation rõ ràng thường dễ suy luận hơn việc pha trộn nhiều default body và implementation trùng chữ ký.

### 11.2. Derived query và annotation query cần được phân loại đúng

Một phương thức chưa có implementation có thể được module xem là query method và xử lý bằng derived query hoặc truy vấn khai báo.

Khi có custom implementation phù hợp, phương thức có thể thuộc đường implementation composition. Nhưng các annotation truy vấn tường minh và metadata của module cũng tham gia việc phân loại và thực thi.

Không dùng bảng ưu tiên fragment để kết luận mọi phương thức có `@Query` hoặc mọi default method đều luôn bị fragment thay thế. Với trường hợp kết hợp như vậy, phải đối chiếu cơ chế của module và bộ phiên bản đang dùng.

Một thiết kế dễ kiểm tra nên chọn rõ: phương thức này do custom implementation chịu trách nhiệm, hay do cơ chế truy vấn chịu trách nhiệm. Tránh gán nhiều ý định điều phối chồng lên cùng một chữ ký khi không có nhu cầu cụ thể.

## 12. Hai loại mơ hồ cần xử lý khác nhau

### 12.1. Hai fragment khác nhau cùng đóng góp phương thức

Ví dụ `DisplayDescription` và `AuditDescription` đều có `describe(String)`. Đây là vấn đề thứ tự composition giữa hai fragment đã được xác định.

Trong phạm vi đó, thứ tự khai báo custom fragment là căn cứ để dự đoán implementation được chọn.

### 12.2. Một fragment có nhiều implementation candidate

Ví dụ chỉ có một interface `DisplayDescription`, nhưng có nhiều lớp hoặc bean khiến cơ chế tìm implementation không xác định được candidate mong muốn.

Đây là bài toán **phát hiện và gắn implementation cho một fragment**. Cần xem quy ước tên, phạm vi tìm kiếm, bean name và cấu hình đăng ký mà module hỗ trợ.

Đổi vị trí `DisplayDescription` trong `extends` không tự nói Spring phải chọn lớp nào trong nhiều implementation của chính nó.

| Câu hỏi | Cơ chế cần xem |
| --- | --- |
| Fragment A dùng implementation nào? | Discovery và đăng ký implementation |
| Fragment A hay B xử lý method trùng? | Thứ tự composition của fragment |
| Service nhận repository bean nào? | Injection, qualifier hoặc lựa chọn bean |
| Advice nào bao quanh lời gọi? | Cấu hình AOP và thứ tự interceptor tương ứng |

Phân biệt các câu hỏi này giúp tránh dùng `@Primary` hoặc đổi tên bean để giải một vấn đề thực ra nằm ở thứ tự fragment.

## 13. Kiểm tra thứ tự điều phối bằng kết quả quan sát được

Với ví dụ `describe`, một kiểm tra có ý nghĩa cần lấy bean repository thật và xác nhận kết quả:

```java
assertEquals("display:c-001", repository.describe("c-001"));
```

Lời khẳng định này giả định cấu hình dùng thứ tự `DisplayDescription`, rồi `AuditDescription`. Nếu thiết kế cố ý đổi thứ tự, kỳ vọng phải đổi theo hợp đồng mới.

Nếu cần chứng minh fragment thứ hai không được gọi, có thể cung cấp một cơ chế ghi nhận lời gọi trong fixture kiểm thử, chẳng hạn một recorder được inject. Tránh suy ra từ việc kết quả đúng rằng mọi tác dụng phụ không mong muốn đều chắc chắn vắng mặt.

Những tình huống nên cân nhắc theo nhu cầu:

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Hai custom fragment trùng method | Implementation được chọn đúng thứ tự đã thiết kế |
| Fragment đứng trước ném lỗi | Không tự chạy fallback sang fragment sau ngoài hợp đồng |
| Custom fragment ghi đè `save` | Đường tùy chỉnh thực sự được gọi và semantics ghi đúng |
| Method thuộc base không bị ghi đè | Hành vi chuẩn vẫn hoạt động phù hợp |
| Có nhiều implementation candidate | Cấu hình chọn đúng implementation hoặc báo mơ hồ rõ ràng |
| Có advice hoặc giao dịch liên quan | Hành vi bao quanh và ranh giới tài nguyên vẫn đáp ứng yêu cầu |

Không chỉ kiểm tra tên lớp proxy hoặc số interface mà proxy triển khai. Những thông tin đó chưa cho biết implementation nào thực hiện lời gọi.

Tương tự, unit test tạo trực tiếp một fragment chỉ xác nhận logic của fragment đó. Nó không thay thế kiểm tra cấu hình composition.

## 14. Quy trình chẩn đoán lời gọi đi nhầm thành phần

### Bước 1: Xác định phương thức bên gọi thực sự sử dụng

Ghi tên, kiểu tham số, generic và kiểu interface mà nơi gọi nhìn thấy. Phân biệt overload với một method thật sự trùng chữ ký.

### Bước 2: Liệt kê các thành phần có implementation phù hợp

Bao gồm custom fragment, base implementation và thành phần mở rộng của module liên quan. Kiểm tra default method hoặc annotation query nếu chúng có mặt.

### Bước 3: Kiểm tra discovery trước khi kiểm tra thứ tự

Xác nhận mỗi fragment đã gắn đúng implementation. Một lớp có tên gần giống nhưng không được ghép vào repository sẽ không tham gia điều phối.

### Bước 4: Đọc thứ tự khai báo custom fragment

Nếu nhiều fragment cùng phù hợp, xác định fragment nào đứng trước. Xem việc đổi thứ tự có phải thay đổi hành vi có chủ đích không.

### Bước 5: Kiểm tra các đường ủy quyền

Tìm lời gọi quay lại chính repository proxy, fallback được giả định hoặc việc một fragment chỉ ghi log nhưng không thật sự gọi thành phần tiếp theo.

### Bước 6: Kiểm tra kết quả và tác dụng phụ

Quan sát kết quả, exception và những thao tác dữ liệu cần thiết. Với ghi dữ liệu, kiểm tra cả giao dịch, version, auditing hoặc callback nếu nghiệp vụ phụ thuộc vào chúng.

## 15. Thiết kế để thứ tự có ý nghĩa rõ ràng

Không phải mọi xung đột cần bị loại bỏ. Ghi đè `save` có chủ đích là một ví dụ hợp lệ. Điều cần tránh là xung đột vô tình mang hai ý nghĩa nghiệp vụ khác nhau.

Một số lựa chọn:

| Nhu cầu | Thiết kế nên cân nhắc |
| --- | --- |
| Thay một thao tác base | Custom fragment có chữ ký phù hợp và implementation đầy đủ |
| Hai thao tác có ý nghĩa khác nhau | Hai tên method rõ vai trò |
| Cần chạy nhiều bước theo thứ tự | Service hoặc implementation điều phối tường minh |
| Cần ghi log/đo thời gian bao quanh | Advice phù hợp với phạm vi và quy tắc rõ ràng |
| Cần thay base cho nhiều repository | Cơ chế repository base class của module |
| Chỉ muốn tái sử dụng một vài tiện ích | Thành phần dùng chung được gọi trực tiếp khi phù hợp |

Nếu duy trì chữ ký trùng giữa nhiều fragment, nên ghi rõ lý do ưu tiên và bảo vệ hành vi đó bằng kiểm tra có ý nghĩa. Việc sắp xếp lại một danh sách interface để “đẹp hơn” có thể làm đổi implementation được chọn.

## 16. Tình huống thực hành

Một repository có `ValidationSave`, `AuditSave` và base CRUD cùng cung cấp `save`. Nhóm kỳ vọng lần lượt kiểm tra, ghi audit rồi lưu dữ liệu chỉ nhờ khai báo cả hai custom fragment.

Theo cơ chế chọn implementation, kỳ vọng này không tự đúng. Fragment phù hợp được ưu tiên có thể xử lý toàn bộ lời gọi, còn fragment sau không được gọi cho cùng method.

Thiết kế cần làm rõ:

1. Bước kiểm tra phải diễn ra trước thao tác nào?
2. Audit phản ánh ý định ghi, ghi thành công hay giao dịch đã hoàn tất?
3. Ai thực hiện thao tác persistence thật?
4. Khi có lỗi, phần nào được rollback hoặc cần xử lý riêng?
5. Nếu có đường `saveAll` hoặc cập nhật trực tiếp, các quy tắc có còn được áp dụng không?

Có thể đặt các bước trong một implementation điều phối hoặc service thích hợp, dùng các thành phần kiểm tra và audit riêng. Khi đó thứ tự được thể hiện bằng lời gọi tường minh, thay vì phụ thuộc một giả định rằng mọi fragment trùng method sẽ tự chạy nối tiếp.

## 17. Câu hỏi tự kiểm tra

### Câu 1

Hai custom fragment cùng có method abstract `describe(String)`. Fragment A được khai báo trước B. Cả hai có được tự gọi cho một lời gọi repository không?

**Gợi ý trả lời:** Không. Trong composition phù hợp, implementation của fragment được ưu tiên được chọn; thứ tự không tự tạo một pipeline gọi cả A và B.

### Câu 2

Fragment được chọn trả `null`. Spring Data có mặc định thử fragment tiếp theo không?

**Gợi ý trả lời:** Không. `null` là kết quả của implementation đó, không phải tín hiệu fallback phổ quát.

### Câu 3

Vì sao custom fragment gọi lại `repository.save` không phải cách gọi base `save`?

**Gợi ý trả lời:** Lời gọi quay lại cùng proxy và có thể được điều phối tới chính fragment đó, gây đệ quy. Cần một đường ủy quyền được thiết kế rõ ràng.

### Câu 4

`@Order` trên một advice có tự thay thứ tự custom fragment trong repository không?

**Gợi ý trả lời:** Không. Thứ tự advice và thứ tự implementation composition là hai cơ chế khác nhau.

### Câu 5

Một fragment có hai implementation candidate. Đổi thứ tự fragment trong `extends` có giải quyết được việc chọn implementation không?

**Gợi ý trả lời:** Không. Cần sửa discovery hoặc đăng ký implementation cho fragment đó trước; sau đó mới xét thứ tự giữa các fragment.

### Câu 6

Một default method xung đột khiến Java không biên dịch. Có thể chờ repository proxy chọn theo thứ tự fragment không?

**Gợi ý trả lời:** Không. Phải giải quyết quy tắc kế thừa default method của Java trước khi có proxy runtime.

### Câu 7

Ghi đè `save` có đủ chứng minh mọi đường ghi đều đã được kiểm tra và auditing giống nhau không?

**Gợi ý trả lời:** Chưa đủ. Phải xác định những đường ghi khác và semantics của implementation được chọn, bao gồm callback, giao dịch và cơ chế của store.