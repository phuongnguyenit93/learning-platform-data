# Viết fragment dùng chung và kiểm tra thứ tự điều phối

Một repository có thể kết hợp nhiều khả năng: CRUD nền của store, query methods, các executor được hỗ trợ và custom fragment của ứng dụng. Khi mở rộng repository, việc implementation tồn tại chưa đủ; cần biết method được chuyển tới fragment nào và một fragment có thể dùng lại cho những domain nào.

Trong chương **Thực hành tổng hợp** của module **SPRING_DATA_COMMONS**, bài học này xây dựng một fragment tra cứu nhiều ID dùng chung cho hai repository, rồi tạo một xung đột phương thức có kiểm soát để kiểm tra thứ tự điều phối. Bài thực hành liên hệ cơ chế fragment với generic, metadata, CRUD và giới hạn store, đồng thời phân biệt thứ tự ưu tiên implementation với một chuỗi xử lý nghiệp vụ.

## 1. Hợp đồng và phạm vi thực hành

Chọn khả năng `findExistingInOrder`: nhận danh sách ID, trả các entity đang tồn tại theo thứ tự xuất hiện đầu tiên của ID trong đầu vào.

Quy tắc cụ thể:

1. Chỉ xét entity có định danh Long, thuộc tính ID được ánh xạ tên id trong ví dụ JPA.
2. Danh sách đầu vào không được null, không chứa null và có tối đa 200 phần tử trước khi loại trùng.
3. ID trùng chỉ tạo tối đa một entity kết quả.
4. ID không tồn tại bị bỏ qua.
5. Danh sách rỗng trả kết quả rỗng, không cần truy vấn dữ liệu.
6. Kết quả theo thứ tự đầu vào sau khi loại trùng, không dựa vào thứ tự của store.
7. Không thực hiện ghi dữ liệu.

Ví dụ logic:

```text
Đầu vào:       [C, A, missing, B, A]
Kết quả đúng:  [C, A, B]
```

A, B và C là nhãn fixture, không phải các ID cần gán cứng.

### 1.1. Một giới hạn có chủ đích

Fragment này dùng lại được giữa các domain có cùng hợp đồng Long ID của bài. Nó chưa phải thư viện tra cứu cho mọi kiểu ID, composite key hoặc mọi mô hình dữ liệu.

Phần sắp lại thứ tự và kiểm tra đầu vào có thể độc lập với store. Phần tải entity thật được tách thành một gateway; ví dụ gateway sử dụng JPA. Nhờ đó, không gọi một implementation dùng EntityManager là implementation persistence dùng chung cho mọi kho dữ liệu.

## 2. Kiến trúc bài thực hành

```text
ProductRepository hoặc CustomerRepository
                  |
                  v
OrderedLookup<T>
                  |
                  v
OrderedLookupImpl<T>
                  |
                  v
LookupOrdering: kiểm tra, loại trùng, sắp theo ID yêu cầu
                  |
                  v
BatchLookupGateway
                  |
                  v
JpaBatchLookupGateway -> JPA -> database kiểm thử
```

Chọn một store JPA đã được cấu hình, cùng một database kiểm thử riêng cho các entity Product và Customer. Hai entity đều có ID kiểu Long và triển khai một hợp đồng đọc ID nhỏ:

```java
public interface Identified {

    Long getId();
}
```

Domain root của repository vẫn là Product hoặc Customer. Identified chỉ giúp thuật toán lấy ID có kiểu rõ ràng; nó không thay các entity thành một projection tối ưu hoặc một domain root chung.

Các đoạn mã là những thành phần của bài thực hành. Entity mapping, factory fixture và datasource cần được cung cấp trong môi trường thực hành; bài không giả định các tên lớp tự tạo ra một ứng dụng hoàn chỉnh.

## 3. Tạo fragment interface và gateway

### 3.1. Interface dùng lại giữa các repository

```java
import java.util.List;

public interface OrderedLookup<T extends Identified> {

    List<T> findExistingInOrder(Class<T> domainType, List<Long> ids);
}
```

Tham số `Class<T>` làm domain type ở lần gọi trở nên tường minh. Ví dụ repository đã ràng buộc T là Product sẽ nhận Product.class theo hợp đồng kiểu của phương thức.

Đây là một lựa chọn thiết kế để không cần lưu domain hiện tại vào một field mutable dùng chung hoặc tự suy từ lớp proxy. Không sử dụng raw type để truyền một class tùy ý vượt qua hợp đồng generic.

### 3.2. Gateway tải dữ liệu

```java
import java.util.List;

public interface BatchLookupGateway {

    <T extends Identified> List<T> loadByIds(
            Class<T> domainType, List<Long> ids);
}
```

Gateway trả các entity tìm thấy, không cam kết cùng thứ tự với danh sách ID. Thuật toán thứ tự sẽ nằm ở thành phần riêng.

Gateway của ví dụ chỉ hỗ trợ những entity đáp ứng hợp đồng mapping đã nêu. Với ID tổng hợp, tên thuộc tính khác hoặc store khác, cần một implementation và phép kiểm chứng tương ứng.

## 4. Viết thuật toán chung có thể kiểm thử riêng

```java
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

@Component
public class LookupOrdering {

    private final BatchLookupGateway gateway;

    public LookupOrdering(BatchLookupGateway gateway) {
        this.gateway = gateway;
    }

    public <T extends Identified> List<T> load(
            Class<T> domainType, List<Long> ids, boolean reverse) {
        if (domainType == null || ids == null) {
            throw new IllegalArgumentException("Thiếu domain hoặc danh sách ID");
        }
        if (ids.size() > 200) {
            throw new IllegalArgumentException("Tối đa 200 ID cho mỗi lần gọi");
        }

        LinkedHashSet<Long> uniqueIds = new LinkedHashSet<>();
        for (Long id : ids) {
            if (id == null) {
                throw new IllegalArgumentException("ID không được null");
            }
            uniqueIds.add(id);
        }
        if (uniqueIds.isEmpty()) {
            return List.of();
        }

        List<T> loaded = gateway.loadByIds(
                domainType, new ArrayList<>(uniqueIds));
        Map<Long, T> byId = new HashMap<>();
        for (T entity : loaded) {
            if (entity == null || entity.getId() == null
                    || !uniqueIds.contains(entity.getId())) {
                throw new IllegalStateException("Gateway trả dữ liệu ngoài hợp đồng");
            }
            if (byId.putIfAbsent(entity.getId(), entity) != null) {
                throw new IllegalStateException("Gateway trả lặp cùng một ID");
            }
        }

        List<Long> requestedOrder = new ArrayList<>(uniqueIds);
        if (reverse) {
            Collections.reverse(requestedOrder);
        }

        List<T> result = new ArrayList<>();
        for (Long id : requestedOrder) {
            T entity = byId.get(id);
            if (entity != null) {
                result.add(entity);
            }
        }
        return List.copyOf(result);
    }
}
```

Các quyết định đáng chú ý:

- LinkedHashSet loại trùng nhưng giữ thứ tự đầu vào.
- Store chỉ nhận tập ID cần tải; kết quả không được giả định có thứ tự.
- Không dùng một field như currentDomain để giữ trạng thái của lần gọi.
- Tham số reverse phục vụ biến thể thứ hai trong thí nghiệm điều phối.
- Không tải toàn bộ bảng rồi lọc trong bộ nhớ.

Đây là một thuật toán có giới hạn kích thước theo hợp đồng bài thực hành. Nếu một use case cần hàng nghìn ID, phải thiết kế riêng batching, giới hạn tham số và semantics khi đọc nhiều đợt, thay vì bỏ giới hạn một cách tùy tiện.

## 5. Cài đặt gateway JPA đúng phạm vi

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Repository
public class JpaBatchLookupGateway implements BatchLookupGateway {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public <T extends Identified> List<T> loadByIds(
            Class<T> domainType, List<Long> ids) {
        if (ids.isEmpty()) {
            return List.of();
        }

        String entityName = entityManager.getMetamodel()
                .entity(domainType).getName();

        return entityManager.createQuery(
                "select e from " + entityName + " e where e.id in (:ids)",
                domainType)
                .setParameter("ids", ids)
                .getResultList();
    }
}
```

Ví dụ dùng entity name lấy từ metamodel, còn danh sách ID được bind thành tham số. Phần đường dẫn e.id dựa trên giả định mapping của bài; không áp dụng nguyên xi cho entity có tên thuộc tính ID khác.

Cần một persistence unit và transaction manager phù hợp. Nếu có nhiều store hoặc nhiều datasource, cấu hình gateway để chọn đúng tài nguyên. `readOnly = true` diễn đạt ý định đọc, không tự tạo một bảo đảm chung rằng mọi hệ lưu trữ cấm ghi hoặc trả cùng một snapshot.

Query với IN không được dùng làm nguồn thứ tự kết quả. LookupOrdering mới là nơi thực hiện hợp đồng C, A, B của ví dụ.

## 6. Thêm dấu vết điều phối cho bài thực hành

Để phân biệt “kết quả có vẻ đúng” với “đúng implementation đã được gọi”, dùng một probe nhỏ trong môi trường thực hành:

```java
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;

@Component
public class DispatchProbe {

    private final ConcurrentLinkedQueue<String> calls =
            new ConcurrentLinkedQueue<>();

    public void record(String fragment) {
        calls.add(fragment);
    }

    public List<String> snapshot() {
        return List.copyOf(calls);
    }

    public void clear() {
        calls.clear();
    }
}
```

Probe là công cụ quan sát của bài, không phải dữ liệu auditing nghiệp vụ. Các test sử dụng cùng probe phải được cô lập, không chạy đồng thời rồi clear dấu vết của nhau. Khi đưa thiết kế vào ứng dụng, có thể thay bằng cơ chế quan sát phù hợp hoặc bỏ instrumentation không cần thiết.

Fragment chính:

```java
import java.util.List;

public class OrderedLookupImpl<T extends Identified>
        implements OrderedLookup<T> {

    private final LookupOrdering ordering;
    private final DispatchProbe probe;

    public OrderedLookupImpl(LookupOrdering ordering, DispatchProbe probe) {
        this.ordering = ordering;
        this.probe = probe;
    }

    @Override
    public List<T> findExistingInOrder(Class<T> domainType, List<Long> ids) {
        probe.record("ordered");
        return ordering.load(domainType, ids, false);
    }
}
```

Implementation không giữ T của một repository vào một trạng thái thay đổi. Domain được truyền vào mỗi lần gọi và được kiểm tra theo mapping của gateway.

## 7. Ghép cùng một fragment vào hai repository

```java
import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long>, OrderedLookup<Product> {
}
```

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>, OrderedLookup<Customer> {
}
```

Cấu hình thực hành phải đăng ký:

- Mapping của Product và Customer, cả hai triển khai Identified.
- Repository factory của module JPA.
- Các bean LookupOrdering, DispatchProbe và JpaBatchLookupGateway.
- Implementation fragment OrderedLookupImpl trong phạm vi discovery phù hợp.

Với convention mặc định, tên implementation được ghép từ tên **fragment interface** và postfix Impl. Vì vậy, OrderedLookup tương ứng OrderedLookupImpl, không phải bắt buộc ProductRepositoryImpl và CustomerRepositoryImpl.

Theo [mô hình custom repository fragment](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html), nhiều repository có thể dùng cùng fragment. Các class implementation cần nằm trong cơ chế discovery hoặc đăng ký phù hợp; component scan cho helper bean và discovery của fragment cần được phân biệt.

### 7.1. Phép thử dùng lại

Chuẩn bị Product A, B, C và Customer X, Y. Lưu lại ID thật được trả về từ các lần tạo fixture.

Gọi:

```java
products.findExistingInOrder(Product.class, productIds);
customers.findExistingInOrder(Customer.class, customerIds);
```

Cần xác nhận:

- Lần gọi Product chỉ trả Product mong muốn.
- Lần gọi Customer chỉ trả Customer mong muốn.
- Hai lần gọi tuân theo cùng quy tắc loại trùng, bỏ ID thiếu và giữ thứ tự.
- Không có trạng thái domain từ lần gọi trước làm ảnh hưởng lần sau.

ID số trùng nhau ở hai bảng là tình huống có ích để kiểm chứng domainType thực sự được dùng đúng, thay vì một implementation vô tình cố định Product.

## 8. Tạo xung đột có kiểm soát để quan sát ưu tiên

Thêm một fragment có cùng chữ ký, nhưng trả thứ tự đảo ngược:

```java
import java.util.List;

public interface ReverseOrderedLookup<T extends Identified> {

    List<T> findExistingInOrder(Class<T> domainType, List<Long> ids);
}
```

```java
import java.util.List;

public class ReverseOrderedLookupImpl<T extends Identified>
        implements ReverseOrderedLookup<T> {

    private final LookupOrdering ordering;
    private final DispatchProbe probe;

    public ReverseOrderedLookupImpl(
            LookupOrdering ordering, DispatchProbe probe) {
        this.ordering = ordering;
        this.probe = probe;
    }

    @Override
    public List<T> findExistingInOrder(Class<T> domainType, List<Long> ids) {
        probe.record("reverse");
        return ordering.load(domainType, ids, true);
    }
}
```

Hai repository thí nghiệm chỉ khác thứ tự fragment:

```java
public interface ProductOrderedFirstRepository
        extends CrudRepository<Product, Long>,
                OrderedLookup<Product>,
                ReverseOrderedLookup<Product> {
}
```

```java
public interface ProductReverseFirstRepository
        extends CrudRepository<Product, Long>,
                ReverseOrderedLookup<Product>,
                OrderedLookup<Product> {
}
```

Hai fragment có cùng method signature và return type tương thích, nên khai báo Java hợp lệ. Khi repository được ghép, Spring Data sử dụng thứ tự fragment để phân giải implementation phù hợp; custom implementation còn có ưu tiên cao hơn implementation nền và repository aspect theo mô hình được tài liệu mô tả.

### 8.1. Kỳ vọng cho đầu vào đã chọn

Với đầu vào `[C, A, missing, B, A]`:

| Repository | Kết quả kỳ vọng | Dấu vết fragment kỳ vọng |
| --- | --- | --- |
| ProductOrderedFirstRepository | C, A, B | ordered |
| ProductReverseFirstRepository | B, A, C | reverse |

Đây là các kỳ vọng của bài thực hành, cần được kiểm chứng trên cấu hình và phiên bản đang chạy. Không phải số liệu đã thu được từ một lần thực thi tại đây.

## 9. Kiểm tra qua repository proxy thật

Các assertion sau dùng JUnit Jupiter. Giả định fixture đã tạo aId, bId, cId và một missingId chắc chắn không tồn tại; hai repository cùng DispatchProbe đã được inject trong test context JPA thật.

```java
List<Long> request = List.of(cId, aId, missingId, bId, aId);

probe.clear();
List<Product> first = orderedFirst.findExistingInOrder(
        Product.class, request);

assertEquals(List.of(cId, aId, bId),
        first.stream().map(Product::getId).toList());
assertEquals(List.of("ordered"), probe.snapshot());

probe.clear();
List<Product> second = reverseFirst.findExistingInOrder(
        Product.class, request);

assertEquals(List.of(bId, aId, cId),
        second.stream().map(Product::getId).toList());
assertEquals(List.of("reverse"), probe.snapshot());
```

Có thể tạo missingId bằng cách lưu rồi xóa một fixture riêng và đồng bộ thay đổi. Không đoán một số lớn chắc chắn không tồn tại.

Khi kiểm tra thứ tự, phải so sánh List theo thứ tự. So sánh Set chỉ kiểm tra tập phần tử, nên cả hai implementation có thể cùng vượt qua dù đang cần phân biệt chính sách điều phối.

### 9.1. Ba cấp kiểm thử có mục tiêu khác nhau

| Cấp | Nội dung | Điều nó chưa chứng minh |
| --- | --- | --- |
| Unit test LookupOrdering | Đầu vào, loại trùng và thứ tự với gateway giả | Discovery và dispatch của repository |
| Integration test gateway | Query tải đúng entity theo domain và ID | Fragment được ghép đúng |
| Integration test repository proxy | Kết quả cùng dấu vết implementation qua repository thật | Mọi query hoặc mọi store khác cũng có cùng hành vi |

Gọi `new OrderedLookupImpl(...)` để test trực tiếp có thể hữu ích ở cấp unit. Nó không thay được phép thử gọi qua repository proxy khi mục tiêu là kiểm tra composition.

### 9.2. Dữ liệu và probe phải được reset theo phạm vi

Mỗi ca cần fixture riêng hoặc cơ chế reset rõ ràng. Với JPA, cân nhắc flush và clear để tránh đọc nhầm trạng thái chỉ còn trong persistence context.

Probe được clear trước từng đoạn quan sát và các đoạn chạy trong một context thí nghiệm không bị test khác ghi đồng thời. Tính thread-safe của queue không tự tạo cô lập về quyền sở hữu sự kiện giữa nhiều test.

## 10. Thứ tự fragment không phải chuỗi xử lý tự động

Một hiểu nhầm phổ biến:

```text
OrderedLookup -> ReverseOrderedLookup -> CRUD nền
```

Khi cùng chữ ký được nhiều implementation cung cấp, composition chọn implementation thích hợp theo ưu tiên. Nó không tự gọi OrderedLookup rồi gọi tiếp ReverseOrderedLookup để kết hợp hai hành vi.

Dấu vết chỉ có ordered ở repository thứ nhất và chỉ có reverse ở repository thứ hai giúp kiểm chứng điều đó.

### 10.1. Nếu muốn validate rồi mới lưu, phải thiết kế đường phối hợp

Không đặt một fragment Validation và một fragment Audit cùng khai báo save rồi kỳ vọng cả hai tự chạy tuần tự. Nếu cần một chuỗi nghiệp vụ, hãy biểu diễn bằng một service điều phối hoặc một implementation có các collaborator được gọi rõ ràng.

Cũng không dùng `@Order` trên helper bean như một cách thay thế trực tiếp cho thứ tự composition đã khai báo trên repository.

### 10.2. Trùng CRUD cần thận trọng hơn một method mới

Một fragment có thể cố ý cung cấp:

```java
public interface GuardedSave<T> {
    <S extends T> S save(S entity);
}
```

Khi được ghép đúng và chữ ký phù hợp, custom implementation có thể được ưu tiên trước save nền. Đây là một thí nghiệm mở rộng khác với method đọc mới của bài.

Không để custom save gọi lại chính `repository.save(entity)` trên proxy của repository đó để “chuyển tiếp xuống dưới”: nó có thể quay lại custom method và đệ quy. Việc gọi implementation nền hoặc sử dụng persistence API phải được thiết kế theo module, giữ đúng nhận diện entity mới, version và auditing.

Bài cơ sở dùng method mới để quan sát composition mà không thay đổi CRUD. Nếu mở rộng sang override save, cần có ca riêng cho tạo mới, cập nhật và lỗi version.

## 11. Giới hạn dùng chung và metadata invocation

### 11.1. Hợp đồng dùng chung khác implementation persistence dùng chung

OrderedLookup và LookupOrdering chỉ phụ thuộc hợp đồng ID và gateway. JpaBatchLookupGateway dùng JPQL cùng EntityManager, nên thuộc JPA.

Khi đổi store, giữ được thuật toán chưa có nghĩa giữ nguyên gateway. Cần xác minh lại cách truy vấn tập ID, kiểu ID, giới hạn tham số và khả năng của module.

Một fragment dùng chung cũng không tự bảo đảm tenant hoặc quyền truy cập. Nếu entity có phạm vi dữ liệu theo tenant, gateway hoặc hợp đồng tìm kiếm phải mang và thực thi điều kiện đó; bài này giả định tập dữ liệu thực hành đã có phạm vi được xác định.

### 11.2. Vì sao bài truyền Class<T> rõ ràng?

Nếu muốn bỏ tham số này, một hướng nâng cao là sử dụng metadata của lần gọi repository để xác định domain. Spring Data có API invocation context và marker [RepositoryMetadataAccess](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/support/RepositoryMetadataAccess.html) ở các phiên bản hỗ trợ.

Metadata invocation không được expose mặc định vì có chi phí. Việc lấy [RepositoryMethodContext](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/core/RepositoryMethodContext.html) còn yêu cầu đang ở trong lời gọi repository và factory được cấu hình phù hợp.

Không gọi context đó từ một unit test trực tiếp implementation rồi mặc định luôn có dữ liệu. Cũng không bật metadata trên mọi repository chỉ để giải quyết một trường hợp có thể truyền phụ thuộc tường minh đơn giản hơn.

### 11.3. Stateless không tự bảo đảm mọi collaborator đúng

Hai implementation không lưu domain hiện tại vào field là một đặc tính tốt cho tái sử dụng. Gateway, probe và các dependency khác vẫn có vòng đời riêng cần được quản lý.

Nếu sau này bổ sung cache, cần đưa domain cùng điều kiện có ý nghĩa vào cache key. Cache chỉ theo số ID có thể trả nhầm Product và Customer khi hai bảng có cùng ID.

## 12. Bộ ca hoàn thành bài thực hành

| Ca | Kỳ vọng |
| --- | --- |
| Một domain với ID đảo thứ tự | Kết quả theo thứ tự đầu vào, không theo database |
| ID lặp | Mỗi ID tồn tại chỉ xuất hiện một lần |
| ID thiếu | Bị bỏ qua, các phần tử khác vẫn đúng thứ tự |
| Danh sách rỗng | Kết quả rỗng, không cần gọi gateway |
| Null hoặc vượt 200 phần tử | Từ chối đúng hợp đồng đầu vào |
| Product rồi Customer | Không dùng nhầm domain từ lần gọi trước |
| Hai fragment, OrderedLookup trước | Kết quả thường, chỉ dấu vết ordered |
| Đảo thứ tự hai fragment | Kết quả đảo, chỉ dấu vết reverse |
| Sai postfix hoặc implementation ngoài discovery | Ca kiểm tra cho thấy fragment không được ghép như mong muốn |
| CRUD cơ sở | Vẫn lưu và tìm theo ID đúng khi không chủ ý override |

Khi một ca thất bại, xác định cấp lỗi trước: thuật toán, gateway, discovery hay dispatch. Đừng sửa thứ tự interface để che một gateway đang trả sai domain, hoặc mock repository để bỏ qua một fragment chưa được nạp.

Kết quả hoàn chỉnh của bài là một khả năng dùng lại có hợp đồng rõ và một bằng chứng điều phối quan sát được qua repository thật. Người thực hành phải giải thích được method đến implementation nào, tại sao implementation khác không chạy và phần nào cần thay khi chuyển store. Đó là nền để mở rộng repository mà vẫn giữ được tính rõ ràng của CRUD, query và các metadata liên quan.
