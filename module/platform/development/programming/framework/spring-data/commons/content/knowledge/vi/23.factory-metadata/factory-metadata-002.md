# RepositoryMetadata và RepositoryInformation

Một repository Spring Data xuất hiện trong mã ứng dụng dưới dạng interface, nhưng đối tượng được inject thường là proxy do repository factory tạo. Để nối khai báo interface với domain type, định danh, các method CRUD, query method và phần triển khai mở rộng, framework cần thông tin có cấu trúc về repository.

`RepositoryMetadata` và `RepositoryInformation` là hai abstraction trong Spring Data Commons phục vụ việc đó. `RepositoryMetadata` mô tả hợp đồng kiểu của repository. `RepositoryInformation` kế thừa hợp đồng ấy và bổ sung thông tin liên quan đến lớp triển khai cơ sở, cách phân loại method và method đích trong ngữ cảnh factory.

Bài học tập trung vào cách đọc và sử dụng hai interface này để hiểu cơ chế tạo repository, chẩn đoán cấu hình và xây dựng phần mở rộng. Metadata không thay thế mapping của store và không tự cung cấp khả năng truy vấn mà module đang dùng chưa hỗ trợ.

## 1. Hai lớp thông tin cần phân biệt

Có thể bắt đầu bằng hai câu hỏi:

| Câu hỏi | Abstraction phù hợp |
| --- | --- |
| Repository interface này quản lý domain type nào và ID có kiểu gì? | `RepositoryMetadata` |
| Trong cấu hình factory này, method nào thuộc base class, custom implementation hoặc cơ chế query? | `RepositoryInformation` |

Quan hệ kế thừa:

```java
public interface RepositoryInformation extends RepositoryMetadata {
    // Bổ sung thông tin về triển khai và method.
}
```

Vì vậy, một `RepositoryInformation` cũng có thể được dùng ở nơi chỉ cần `RepositoryMetadata`:

```java
RepositoryMetadata metadata = repositoryInformation;
```

Chiều ngược lại không tự hợp lệ. Một đối tượng chỉ được tạo để mô tả interface không mặc nhiên biết base class và các fragment mà một factory thực tế sẽ sử dụng.

Không nên xem đây là hai tên cho cùng một tập dữ liệu, hoặc cố ép một metadata bất kỳ sang `RepositoryInformation` để lấy thêm thông tin chưa được tạo.

## 2. Ví dụ repository dùng trong bài

Giả sử `Customer` là kiểu miền có các thuộc tính Java:

| Thuộc tính | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh |
| `email` | `String` | Email |
| `city` | `String` | Thành phố |
| `createdAt` | `Instant` | Metadata thời gian tạo |

Mapping của `Customer` phải phù hợp với store. Các ví dụ introspection chỉ cần biết kiểu Java; ví dụ sử dụng repository bean thực tế giả định ứng dụng đã có mapping và cấu hình repository hợp lệ.

Một interface cơ sở generic:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BusinessRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

`@NoRepositoryBean` thể hiện interface này là hợp đồng nền, không phải một repository cụ thể cần tạo bean độc lập trong quá trình quét thông thường.

Một fragment mở rộng:

```java
import java.util.List;

public interface CustomerSearch {
    List<Customer> searchActiveByCity(String city);
}
```

Repository cụ thể:

```java
import java.util.List;
import java.util.Optional;

public interface CustomerRepository
        extends BusinessRepository<Customer, Long>, CustomerSearch {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByCity(String city);

    default boolean isSearchTextUsable(String value) {
        return value != null && !value.isBlank();
    }
}
```

Phần phân loại custom method bên dưới giả định `CustomerSearch` có implementation đã được factory phát hiện và ghép vào repository. Chỉ thêm một interface fragment vào `extends` không tự tạo phần triển khai.

Đây là giả định quan trọng: cùng một chữ ký method có thể được xử lý khác nếu composition hoặc cấu hình factory khác. Không dùng riêng tên `searchActiveByCity` để kết luận đó chắc chắn là một derived query hoặc chắc chắn là custom method.

## 3. RepositoryMetadata mô tả hợp đồng kiểu

Interface nằm trong package:

```java
import org.springframework.data.repository.core.RepositoryMetadata;
```

Các khả năng thường cần dùng:

| API | Thông tin được trả lời |
| --- | --- |
| `getRepositoryInterface()` | Interface repository được mô tả |
| `getDomainType()` | Domain type gắn với repository |
| `getIdType()` | Kiểu định danh của domain trong hợp đồng repository |
| `getReturnType(method)` | Thông tin kiểu trả về của method trong ngữ cảnh repository |
| `getReturnedDomainClass(method)` | Lớp kết quả sau khi xử lý kiểu bao theo quy tắc framework |
| `getCrudMethods()` | Thông tin về những method CRUD mà metadata xác định |
| `isReactiveRepository()` | Repository có được nhận diện là reactive theo metadata hay không |

Với `CustomerRepository`, các giá trị hợp đồng mong đợi là:

```text
repositoryInterface = CustomerRepository
 domainType         = Customer
 idType             = Long
```

Domain type được suy ra qua chuỗi generic:

```text
CustomerRepository
    -> BusinessRepository<Customer, Long>
    -> CrudRepository<Customer, Long>
```

Đây là lý do không nên chỉ lấy `getGenericInterfaces()[0]` rồi tự ép kiểu phản chiếu để tìm domain type. Interface trung gian, nhiều cấp kế thừa và biến kiểu generic có thể làm cách đọc thủ công đó sai hoặc thiếu thông tin.

Metadata cũng không chứng minh rằng `Customer` đã có mapping hợp lệ, có chỉ mục email hoặc được lưu trong một loại cơ sở dữ liệu cụ thể. Những câu hỏi ấy thuộc cấu hình và metadata của store.

## 4. Lấy RepositoryMetadata từ interface

Khi chỉ cần introspection hợp đồng, có thể dùng API hỗ trợ của Commons:

```java
import org.springframework.data.repository.core.RepositoryMetadata;
import org.springframework.data.repository.core.support.AbstractRepositoryMetadata;

RepositoryMetadata metadata = AbstractRepositoryMetadata.getMetadata(
        CustomerRepository.class);

System.out.println(metadata.getRepositoryInterface().getName());
System.out.println(metadata.getDomainType().getName());
System.out.println(metadata.getIdType().getName());
```

Thao tác này không tạo một repository bean hoàn chỉnh và không thực thi `findByEmail` hay một truy vấn nghiệp vụ. Nó đọc hợp đồng của kiểu repository được cung cấp.

Hai dạng khai báo đáng phân biệt:

- Interface kế thừa cây `Repository<T, ID>`: generic của hợp đồng là nguồn thông tin chính.
- Interface sử dụng `@RepositoryDefinition`: domain class và ID class được khai báo qua annotation tương ứng.

`AbstractRepositoryMetadata.getMetadata(...)` chọn cách đọc metadata thích hợp cho dạng khai báo được hỗ trợ. Không mặc định một interface Java bất kỳ đều là repository hợp lệ để truyền vào đây.

Có thể gặp lớp như `DefaultRepositoryMetadata` khi tìm hiểu framework, nhưng ứng dụng cần xác định đúng dạng hợp đồng trước khi lựa chọn implementation. Dùng API chung để đọc metadata giúp tránh tự giả định rằng mọi repository đều được mô tả bằng cùng một cấu trúc generic trực tiếp.

### Những gì chưa có ở bước này

Kết quả trên chưa phải bằng chứng về:

- Base class thực tế mà một store factory sẽ chọn.
- Fragment implementation đã được phát hiện trong application context.
- Query đã được biên dịch, kiểm tra hoặc thực thi thành công.
- Chiến lược nạp quan hệ, phân trang hoặc projection được store áp dụng.

Nếu cần các thông tin về triển khai repository, phải đọc `RepositoryInformation` từ ngữ cảnh factory thích hợp.

## 5. Kiểu trả về của method khác domain type của repository

Một repository quản lý `Customer` nhưng method của nó có thể trả `Optional<Customer>`, danh sách, page, projection hoặc một giá trị scalar.

Xét method:

```java
Optional<Customer> findByEmail(String email);
```

Có ba câu hỏi khác nhau:

```java
import java.lang.reflect.Method;

Method method = CustomerRepository.class.getMethod(
        "findByEmail", String.class);

Class<?> rawReturnType = method.getReturnType();
Class<?> repositoryDomainType = metadata.getDomainType();
Class<?> returnedClass = metadata.getReturnedDomainClass(method);
```

Trong ví dụ:

| Giá trị | Kết quả điển hình |
| --- | --- |
| `rawReturnType` | `Optional` |
| `repositoryDomainType` | `Customer` |
| `returnedClass` | `Customer` |

`getReturnType(method)` cung cấp thông tin kiểu của framework để xử lý generic trong ngữ cảnh repository. Nó khác với `Method.getReturnType()`, vốn chỉ trả về một `Class<?>` của kiểu thô.

Với các kiểu bao được hỗ trợ, framework có thể xác định kiểu phần tử thay vì coi `List` hoặc `Page` là domain type. Tuy nhiên, không viết một quy tắc tự bóc mọi lớp generic tùy ý rồi cho rằng nó giống cách Spring Data nhận diện mọi kiểu trả về.

### Khi method trả projection

Ví dụ một interface đầu ra:

```java
public interface CustomerCard {
    String getEmail();
    String getCity();
}
```

Một method có thể khai báo `List<CustomerCard>` nếu cơ chế truy vấn và store hỗ trợ projection đó. Domain type của repository vẫn là `Customer`, trong khi kiểu phần tử được khai báo cho kết quả là `CustomerCard`.

Vì vậy, không dùng `getReturnedDomainClass(method)` như một tên khác của `getDomainType()`. Với projection hoặc scalar, hai khái niệm có thể khác nhau. Metadata về kiểu cũng chưa bảo đảm phép ánh xạ projection sẽ thành công trên mọi store.

Điều này đặc biệt hữu ích khi xây công cụ introspection: cần ghi riêng repository domain, kiểu bao và kiểu kết quả, thay vì gộp tất cả thành một cột “entity”.

## 6. RepositoryInformation bổ sung thông tin triển khai

Interface nằm trong package:

```java
import org.springframework.data.repository.core.RepositoryInformation;
```

Ngoài những API kế thừa từ `RepositoryMetadata`, các API quan trọng gồm:

| API | Công dụng |
| --- | --- |
| `getRepositoryBaseClass()` | Lớp triển khai cơ sở của repository trong ngữ cảnh được mô tả |
| `isBaseClassMethod(method)` | Method có thuộc phần xử lý của base class hay không |
| `isCustomMethod(method)` | Method có được nhận diện thuộc phần triển khai custom hay không |
| `isQueryMethod(method)` | Method có được nhận diện là query method hay không |
| `getQueryMethods()` | Tập method được nhận diện cho cơ chế query |
| `getTargetClassMethod(method)` | Method đích tương ứng mà thông tin triển khai xác định |

Tên “custom method” trong API không có nghĩa là mọi method do lập trình viên tự viết trong interface. Một `findByEmail` được khai báo bởi ứng dụng vẫn có thể là query method để framework xử lý, không phải custom implementation method.

Ngược lại, `searchActiveByCity` có thể được fragment triển khai trực tiếp. Khi composition hợp lệ nhận diện phần triển khai đó, nó không cần được diễn giải thành derived query chỉ vì tên trông giống một câu tìm kiếm.

Base class cũng là khái niệm khác với proxy class. Trong một cấu hình JPA thông thường, base class có thể là `SimpleJpaRepository`, nhưng ứng dụng có thể thay base class và store khác có implementation khác. Không hard-code tên lớp này như một hợp đồng chung của Spring Data Commons.

## 7. Phân loại method trong ví dụ

Với repository và fragment đã cấu hình hợp lệ như phần đầu, có thể diễn giải các method như sau:

| Method | Vai trò thông thường trong ví dụ |
| --- | --- |
| `findById` kế thừa từ CrudRepository | Method CRUD do base implementation xử lý |
| `save` kế thừa từ CrudRepository | Method CRUD do base implementation xử lý |
| `findByEmail` | Query method được cơ chế truy vấn của store xử lý |
| `findByCity` | Query method được cơ chế truy vấn của store xử lý |
| `searchActiveByCity` | Custom method do fragment đã đăng ký triển khai |
| `isSearchTextUsable` | Default method có phần thân Java trong interface |

Bảng là mô tả của cấu hình minh họa, không phải thuật toán phân loại mọi method chỉ bằng tiền tố tên.

Có thể kiểm tra method cụ thể:

```java
Method method = CustomerRepository.class.getMethod(
        "findByEmail", String.class);

System.out.println(information.isBaseClassMethod(method));
System.out.println(information.isCustomMethod(method));
System.out.println(information.isQueryMethod(method));
```

Với `information` lấy từ factory thích hợp, các câu trả lời phản ánh thông tin mà framework đã xây dựng cho repository đó.

### Những trường hợp cần đọc ngữ cảnh thật

Khi redeclare method CRUD, thêm annotation truy vấn đặc thù, thay base class hoặc có fragment chồng lên một method nền, không tự áp đặt quy tắc rằng các nhãn trên luôn là một phân hoạch độc quyền. Cần kiểm tra thông tin và hành vi của đúng factory cùng phiên bản đang dùng.

Default method có phần thân Java không tự trở thành derived query chỉ vì được nhìn thấy qua reflection. Nếu phần thân default gọi một query method khác, lời gọi bên trong đó vẫn có thể thực thi truy vấn; hai cấp xử lý không nên bị gộp làm một.

Bridge method và các chi tiết sinh bởi compiler cũng là lý do nên dùng API phân loại của framework thay vì đếm toàn bộ `getMethods()` rồi coi mỗi method là một query nghiệp vụ riêng.

## 8. Lấy RepositoryInformation từ factory bean

Trong ứng dụng Spring, repository thường là sản phẩm của một `FactoryBean`. Tên bean bình thường trả sản phẩm repository; tiền tố `&` dùng để lấy chính factory bean đó.

Ví dụ giả định bean repository có tên `customerRepository`:

```java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.data.repository.core.RepositoryInformation;
import org.springframework.data.repository.core.support.RepositoryFactoryInformation;

static RepositoryInformation repositoryInformation(
        BeanFactory beanFactory,
        String repositoryBeanName) {

    Object factoryBean = beanFactory.getBean("&" + repositoryBeanName);

    if (!(factoryBean instanceof RepositoryFactoryInformation<?, ?> factory)) {
        throw new IllegalStateException(
                "Bean không cung cấp RepositoryFactoryInformation");
    }

    return factory.getRepositoryInformation();
}
```

Sử dụng:

```java
RepositoryInformation information = repositoryInformation(
        beanFactory,
        "customerRepository");

System.out.println(information.getRepositoryInterface().getName());
System.out.println(information.getDomainType().getName());
System.out.println(information.getRepositoryBaseClass().getName());
```

Ví dụ dùng pattern matching của `instanceof`, giả định Java 17 trở lên. `beanFactory` là BeanFactory của application context chứa repository.

Cần dùng đúng tên bean đã được cấu hình. Tên mặc định, alias, cách đăng ký và việc có nhiều repository đều có thể làm một chuỗi hard-code không còn đúng với ứng dụng khác.

Việc lấy factory có thể làm quá trình khởi tạo liên quan diễn ra nếu bean chưa sẵn sàng. Không nhầm introspection này với một lời gọi nghiệp vụ đọc bản ghi, nhưng cũng không giả định nó luôn tách biệt khỏi mọi bước bootstrap, kiểm tra query hoặc chuẩn bị tài nguyên của store.

### Vì sao không gọi repository.getClass()?

```java
Class<?> runtimeClass = repository.getClass();
```

Giá trị này có thể là class proxy do Spring tạo. Nó không tự cho biết domain type theo generic đã giải quyết, base class được cấu hình hay tập fragment composition.

Không ép proxy về một base implementation cụ thể để lấy thông tin. Repository contract, lớp proxy và target implementation là các lớp khái niệm khác nhau; `RepositoryInformation` giúp quan sát chúng ở mức abstraction phù hợp hơn.

## 9. Duyệt query method và tìm method đích

Một hàm chẩn đoán đơn giản:

```java
static void describeRepository(RepositoryInformation information) {
    System.out.println("Interface: "
            + information.getRepositoryInterface().getName());
    System.out.println("Domain: "
            + information.getDomainType().getName());
    System.out.println("ID: "
            + information.getIdType().getName());
    System.out.println("Base: "
            + information.getRepositoryBaseClass().getName());

    information.getQueryMethods().forEach(method -> {
        System.out.println("Query method: " + method.toGenericString());
        System.out.println("Returned class: "
                + information.getReturnedDomainClass(method).getName());
    });
}
```

`getQueryMethods()` phục vụ việc quan sát những method được nhận diện cho cơ chế query. Nó không phải danh sách mọi method public của proxy và cũng không phải danh sách các query đã được chạy trên dữ liệu.

Thông tin này có ích để giải thích vì sao một method được framework xem như query cần xử lý. Nó không tự cung cấp SQL, pipeline tài liệu, query plan hoặc số lần gọi thực tế.

### getTargetClassMethod để làm gì?

Có thể bắt đầu từ một method CRUD của hợp đồng:

```java
import java.lang.reflect.Method;
import org.springframework.data.repository.CrudRepository;

Method exposed = CrudRepository.class.getMethod(
        "findById", Object.class);

Method target = information.getTargetClassMethod(exposed);

System.out.println(exposed.toGenericString());
System.out.println(target.toGenericString());
```

Tham số phản chiếu là `Object.class` vì ID trong chữ ký generic của `CrudRepository` bị xóa kiểu ở cấp method phản chiếu đó. Không lấy `Long.class` để tìm chính method generic gốc chỉ vì repository cụ thể dùng ID kiểu Long.

Method đích có thể giúp nối chữ ký được công bố với method triển khai mà framework tìm được. Với method được xử lý bởi cơ chế query, không suy luận rằng lúc nào cũng tồn tại một method Java cụ thể trong base class chứa phần thân truy vấn đó. Tùy trường hợp, kết quả tra cứu có thể vẫn là method được cung cấp hoặc method tương ứng theo composition.

Không dùng kết quả này để tự gọi `Method.invoke` nhằm thay thế toàn bộ proxy dispatch. Transaction advice, interceptor truy vấn, default method và fragment composition có các trách nhiệm mà một lần reflection invoke trực tiếp không tự tái tạo.

## 10. Vai trò của hai abstraction trong vòng đời factory

Có thể hình dung các bước khái niệm như sau:

```text
Repository interface
    -> đọc domain type, ID type và hợp đồng method
    -> RepositoryMetadata

Cấu hình store + base class + fragments/composition
    -> bổ sung thông tin triển khai và phân loại method
    -> RepositoryInformation

Factory và các thành phần hỗ trợ
    -> chuẩn bị target, query handling và proxy
    -> repository bean cho ứng dụng sử dụng
```

Sơ đồ mô tả trách nhiệm, không cam kết một thứ tự lời gọi nội bộ bất biến giữa mọi phiên bản hoặc mọi store factory.

Metadata của interface là đầu vào quan trọng để framework biết repository quản lý kiểu nào. Thông tin triển khai giúp framework nhận diện các method cần xử lý theo cơ chế query, method nền và phần mở rộng.

`RepositoryInformation` không phải toàn bộ proxy pipeline. Nó cung cấp thông tin để các thành phần khác làm việc; việc tạo query, mở transaction, ánh xạ kết quả và truy cập kho dữ liệu vẫn thuộc các thành phần tương ứng.

Khi viết repository factory hoặc phần mở rộng theo store, nên lấy thông tin từ API mà extension point cung cấp. Không tự dựng một lớp information giả định base class và composition chỉ để có giá trị cho công cụ quan sát, vì nó có thể không phản ánh repository bean thật.

## 11. Phân biệt với metadata của entity và store

Từ “metadata” xuất hiện ở nhiều tầng trong Spring Data:

| Abstraction | Đối tượng được mô tả | Câu hỏi điển hình |
| --- | --- | --- |
| `RepositoryMetadata` | Hợp đồng repository | Repository quản lý Customer và ID Long hay kiểu nào khác? |
| `RepositoryInformation` | Repository trong ngữ cảnh triển khai | Method nào được xem là query, custom hoặc base method? |
| `EntityInformation` | Thông tin hỗ trợ thao tác trên domain object | Lấy ID hoặc xác định đối tượng mới theo cơ chế nào? |
| `PersistentEntity` và mapping metadata liên quan | Cấu trúc domain được mapping | Thuộc tính nào là ID, version hoặc được mapping theo store? |

`metadata.getIdType()` trả kiểu ID trong hợp đồng repository, không đọc ID của một instance Customer. `metadata.getDomainType()` cũng không trả tên bảng hay collection.

Tương tự, trường `createdAt` có thể tham gia auditing ở tầng mapping và entity lifecycle. Hai interface repository trong bài không tự mô tả toàn bộ cấu hình auditing hoặc cập nhật giá trị thời gian cho entity.

Một công cụ chẩn đoán có thể cần kết hợp nhiều tầng metadata, nhưng nên ghi rõ nguồn của từng thông tin. Nếu cần tên cột, tên collection, chiến lược ID hoặc thuộc tính auditing, phải dùng API mapping phù hợp của module, không suy từ tên repository.

## 12. Những tình huống chẩn đoán thực tế

### Domain type hoặc ID type không như mong đợi

Đọc `getRepositoryInterface()`, `getDomainType()` và `getIdType()` trên repository cụ thể. Kiểm tra hợp đồng generic đã được khai báo có đủ thông tin hay không.

Các interface raw hoặc base generic chưa gắn kiểu cụ thể có thể làm việc xác định domain thất bại hoặc thiếu ý nghĩa cần thiết cho factory. Đặt `@NoRepositoryBean` cho hợp đồng nền phù hợp và dùng repository cụ thể có kiểu đầy đủ.

Không sửa metadata bằng cách ghi đè một giá trị quan sát được ở nơi khác; cần sửa nguồn khai báo hoặc cấu hình tạo repository.

### Method đáng lẽ là fragment lại bị xem như query

Kiểm tra fragment implementation có thực sự được phát hiện và ghép vào composition không. Sau đó đọc `isCustomMethod` và `isQueryMethod` trong thông tin của factory thực tế.

Một method tự đặt tên nghiệp vụ nhưng không có implementation phù hợp có thể bị cơ chế query xem xét, dẫn đến lỗi phân tích tên hoặc dựng query ở store. Đổi tên method chỉ để tránh lỗi không giải quyết việc thiếu fragment nếu yêu cầu ban đầu là thực thi code custom.

### Base class khác dự kiến

Đọc `getRepositoryBaseClass()` thay vì nhìn tên class proxy. Kiểm tra cấu hình store hoặc base repository class đã được áp dụng cho đúng nhóm repository.

Một application context có thể chứa nhiều repository factory hoặc nhiều module. Không giả định mọi repository đều dùng cùng base implementation chỉ vì cùng kế thừa CrudRepository.

### Danh sách query method không giống getMethods()

Điều này có thể là bình thường vì các method CRUD, custom, default và chi tiết compiler không đều thuộc nhóm query method. Cần so sánh theo vai trò và cấu hình thay vì theo tổng số method public.

Nếu công cụ introspection cần hiển thị mọi method, hãy tách phần chữ ký phản chiếu với phần phân loại do framework cung cấp. Không tự biến method chưa được hiểu thành query chỉ vì nó xuất hiện trong reflection.

## 13. Tái sử dụng và cache thông tin đúng ngữ cảnh

Nên coi metadata đọc được như thông tin chỉ đọc. Hai interface này không phải nơi để đăng ký thêm fragment, đổi domain type hay sửa base class của một repository đang hoạt động.

Nếu cần cache kết quả quan sát trong một application context ổn định, khóa cache phải nhận diện được repository và ngữ cảnh liên quan. Chỉ dùng domain class làm khóa có thể không đủ: nhiều repository có thể cùng quản lý một domain nhưng có interface, composition hoặc cấu hình khác nhau.

Một khóa có thể dựa trên tên bean hoặc repository interface kết hợp với phạm vi factory/context của công cụ. Khi context được tạo lại hoặc cấu hình thay đổi, không dùng lại thông tin triển khai cũ như thể nó vẫn mô tả bean mới.

Cũng không chia sẻ một `RepositoryInformation` từ factory của store này để áp đặt cách phân loại cho một repository tương tự ở store khác. Hợp đồng Commons tạo điểm truy cập thống nhất, không xóa khác biệt trong implementation.

## 14. Những lỗi thường gặp

| Cách hiểu hoặc cách làm | Vấn đề | Cách điều chỉnh |
| --- | --- | --- |
| RepositoryMetadata và RepositoryInformation là cùng một mức thông tin | Bỏ qua base class và composition | Tách hợp đồng kiểu với thông tin triển khai |
| Lấy domain từ repository.getClass() | Nhận class proxy thay vì hợp đồng repository | Dùng metadata theo interface hoặc thông tin từ factory |
| Tự đọc interface generic đầu tiên | Không xử lý đầy đủ kế thừa và biến kiểu | Dùng API metadata của Commons |
| Mọi method do ứng dụng khai báo đều là custom method | Nhầm query method với custom implementation | Dùng phân loại trong RepositoryInformation |
| Tên bắt đầu bằng find luôn phải là derived query | Có thể là base method, default hoặc được custom xử lý | Kiểm tra ngữ cảnh và method thực tế |
| getReturnedDomainClass luôn bằng getDomainType | Projection hoặc scalar có kiểu kết quả khác | Ghi riêng domain repository và kiểu kết quả |
| getQueryMethods là danh sách truy vấn đã chạy | Đây là thông tin phân loại, không phải thống kê thực thi | Dùng cơ chế quan sát runtime nếu cần số lần truy vấn |
| Lấy bean không có dấu & rồi ép về factory | Đang lấy sản phẩm repository | Truy cập đúng factory bean trong context phù hợp |
| Có metadata nghĩa là mapping và mọi query hợp lệ | Metadata không thay thế kiểm tra store | Phân biệt introspection hợp đồng với bootstrap và thực thi |
| Cache information chỉ bằng domain class | Nhiều repository hoặc factory có thể khác nhau | Giữ khóa và vòng đời theo repository/context |

Khi cần hiểu một repository, hãy bắt đầu từ interface, domain type và ID type, rồi chuyển sang base class và phân loại method của factory thực tế. Cách đọc theo hai lớp này giúp chẩn đoán lỗi generic, fragment và query handling rõ ràng, đồng thời giữ đúng ranh giới giữa abstraction Commons với khả năng của từng store.
