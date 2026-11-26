# Kiểm thử fragment, xung đột phương thức và repository đa store

## 1. Một repository proxy có thể ghép từ nhiều thành phần

Một repository không nhất thiết chỉ gồm CRUD và derived queries. Nó có thể kết hợp implementation cơ sở của module, các khả năng bổ sung và một hoặc nhiều fragment do ứng dụng cung cấp. Khi có nhiều datastore, còn phải xác định repository đó được factory nào tạo và sử dụng hạ tầng của store nào.

Vì vậy, kiểm thử cần trả lời riêng các câu hỏi:

1. Logic bên trong fragment có đúng không?
2. Spring Data có phát hiện và ghép đúng fragment vào repository proxy không?
3. Nếu nhiều thành phần cung cấp cùng một chữ ký, lời gọi được chuyển tới đâu?
4. Khi nhiều store cùng xuất hiện, repository có gắn đúng module, mapping và tài nguyên không?

Spring Data Commons cung cấp mô hình repository composition và các abstraction dùng chung. Entity mapping, truy vấn, transaction và cách thực thi thao tác vẫn phụ thuộc module như JPA, MongoDB, JDBC hoặc R2DBC. Một test vượt qua ở JPA không tự chứng minh cùng thiết kế sẽ chạy đúng ở MongoDB.

## 2. Phân biệt các mức kiểm thử

| Mức kiểm thử | Bằng chứng cung cấp | Điều chưa chứng minh |
| --- | --- | --- |
| Unit test implementation fragment | Kiểm tra đầu vào, xử lý nghiệp vụ và tương tác với dependency | Fragment đã được repository factory phát hiện |
| Test composition với repository thật | Proxy chuyển lời gọi tới đúng implementation | Mọi truy vấn trong fragment đúng trên datastore |
| Integration test cho từng store | Mapping, truy vấn và thao tác ghi/đọc của store hoạt động | Cấu hình đồng thời nhiều store không nhập nhằng |
| Test context đa store | Các repository cùng khởi tạo và được nối đúng hạ tầng | Có transaction nguyên tử xuyên mọi store |
| Test luồng nghiệp vụ đa store | Tác dụng và lỗi giữa các bước được xử lý theo thiết kế | Mọi đường lỗi bên ngoài phạm vi test đều đã được bao phủ |

Mock repository ở tầng service hữu ích để kiểm tra service gọi đúng API. Nó không kiểm tra cơ chế ghép fragment, thứ tự ưu tiên hoặc việc chọn repository factory. Nếu mục tiêu là kiểm thử các cơ chế đó, phải gọi bean repository thật trong cấu hình phù hợp.

## 3. Kiểm thử logic của một fragment độc lập

### 3.1. Hợp đồng fragment và dependency

Ví dụ ứng dụng cho phép tìm khách hàng trong phạm vi tenant. Fragment kiểm tra tenant, chuẩn hóa khoảng trắng của tiền tố và bỏ qua truy vấn nếu không có nội dung tìm kiếm:

```java
record CustomerSummary(Long id, String name) {
}

interface CustomerSearch {
    List<CustomerSummary> searchVisible(String tenantId, String prefix);
}

interface CustomerSearchOperations {
    List<CustomerSummary> findVisibleByPrefix(
        String tenantId, String prefix
    );
}
```

```java
class CustomerSearchImpl implements CustomerSearch {

    private final CustomerSearchOperations operations;

    CustomerSearchImpl(CustomerSearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public List<CustomerSummary> searchVisible(
            String tenantId, String prefix) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenant");
        }

        String normalized = prefix == null ? "" : prefix.strip();
        if (normalized.isEmpty()) {
            return List.of();
        }

        return operations.findVisibleByPrefix(tenantId, normalized);
    }
}
```

`CustomerSearchOperations` là dependency do ứng dụng định nghĩa, không phải API của Spring Data Commons. Implementation của dependency này cần dùng truy vấn phù hợp với store thực tế và áp dụng điều kiện tenant đúng cách.

Việc truyền tenant vào fragment chưa thay thế kiểm tra quyền truy cập. Service hoặc cơ chế bảo mật vẫn phải xác nhận người gọi được phép truy cập tenant đó.

### 3.2. Unit test những điều kiện quan trọng

Ví dụ dùng JUnit Jupiter, Mockito và AssertJ; các import thông dụng được lược bỏ:

```java
class CustomerSearchImplTest {

    private final CustomerSearchOperations operations =
        mock(CustomerSearchOperations.class);

    private final CustomerSearchImpl fragment =
        new CustomerSearchImpl(operations);

    @Test
    void rejectsMissingTenantBeforeQuerying() {
        assertThrows(
            IllegalArgumentException.class,
            () -> fragment.searchVisible(" ", "Lan")
        );

        verifyNoInteractions(operations);
    }

    @Test
    void skipsQueryForBlankPrefix() {
        assertThat(fragment.searchVisible("tenant-a", "  "))
            .isEmpty();

        verifyNoInteractions(operations);
    }

    @Test
    void passesTenantAndNormalizedPrefix() {
        var expected = List.of(new CustomerSummary(7L, "Lan"));
        when(operations.findVisibleByPrefix("tenant-a", "Lan"))
            .thenReturn(expected);

        var actual = fragment.searchVisible("tenant-a", "  Lan  ");

        assertThat(actual).containsExactlyElementsOf(expected);
        verify(operations).findVisibleByPrefix("tenant-a", "Lan");
    }
}
```

Những test này bảo vệ chính sách không truy vấn khi thiếu dữ liệu và cách truyền điều kiện xuống dependency. Chúng chưa chứng minh truy vấn thật có lọc tenant. Integration test cần thêm hai khách hàng giống tên nhưng khác tenant để phát hiện việc dependency bỏ quên điều kiện đó.

Không cần dựng toàn bộ ứng dụng để kiểm tra các quy tắc thuần Java này. Đồng thời, không nên coi việc gọi trực tiếp `new CustomerSearchImpl(...)` là bằng chứng Spring Data đã ghép fragment thành công.

## 4. Kiểm thử phát hiện implementation và repository composition

Một repository có thể khai báo fragment cùng CRUD:

```java
interface CustomerRepository
        extends CrudRepository<Customer, Long>, CustomerSearch {
}
```

Theo quy ước fragment thông thường, interface `CustomerSearch` đi cùng implementation `CustomerSearchImpl` khi dùng hậu tố mặc định `Impl`. Hậu tố có thể được cấu hình khác; package, tên bean và cấu hình scan cũng ảnh hưởng việc tìm implementation.

Test composition nên:

1. Nạp repository factory của module cần kiểm tra.
2. Đăng ký domain mapping, hạ tầng và dependency của fragment.
3. Để cơ chế phát hiện fragment mà ứng dụng thực sự sử dụng tham gia.
4. Inject `CustomerRepository`, rồi gọi `searchVisible()` qua proxy đó.
5. Xác nhận hành vi của fragment và kết quả truy vấn cần thiết.

Nếu test tự tạo một proxy bằng factory rồi truyền implementation trực tiếp, nó có thể kiểm tra composition nhưng chưa kiểm tra được quy ước tìm implementation qua package scanning. Cần ghi rõ mục tiêu để tránh bỏ sót phần cấu hình mà production dựa vào.

Với Spring Boot và JPA, test slice như `@DataJpaTest` có thể dùng cho repository JPA nếu scan, entity mapping và các dependency tùy chỉnh được cấu hình đầy đủ. Không giả định test slice tự tìm mọi service ngoài phạm vi của nó; có thể cần import cấu hình hoặc cung cấp dependency test một cách tường minh.

Mô hình fragment là giao diện mở rộng được triển khai rồi ghép vào repository. Không nên nhầm nó với việc chỉ đặt một lớp có tên giống repository cộng hậu tố và mặc định rằng mọi phương thức tùy chỉnh đều được nối đúng. Test cần bám vào kiểu composition mà ứng dụng đã chọn.

## 5. Xung đột phương thức: trước hết phân loại đúng

| Trường hợp | Bản chất | Nơi kiểm tra phù hợp |
| --- | --- | --- |
| Hai fragment có cùng tên và cùng chữ ký tương thích | Có nhiều implementation ứng viên trong composition | Test lời gọi qua repository proxy |
| Fragment có chữ ký trùng phương thức cơ sở như `save` | Có chủ đích hoặc vô tình override hành vi cơ sở | Test fragment được gọi và kiểm tra semantics lưu |
| Hai phương thức cùng tên nhưng khác tham số hợp lệ | Overload, chưa chắc là xung đột | Test đúng chữ ký được gọi |
| Cùng chữ ký nhưng kiểu trả về không tương thích | Lỗi hệ thống kiểu Java | Compiler phát hiện trước khi chạy Spring |
| Các generic method có cùng erasure nhưng không override hợp lệ | Xung đột khai báo Java | Compiler và thiết kế interface |
| Hai bean cùng vai trò dependency | Nhập nhằng dependency injection | Test context và qualifier/cấu hình bean |
| Hai store cùng nhận một repository không rõ phạm vi | Nhập nhằng chọn factory hoặc scan | Test cấu hình đa store |

Không gom tất cả vào một lỗi “Spring chọn nhầm method”. Một xung đột không thể biên dịch không được giải quyết bằng thứ tự fragment. Tương tự, `@Qualifier` có thể chọn dependency nhưng không thay thế quy tắc dispatch bên trong repository proxy.

## 6. Kiểm thử thứ tự ưu tiên giữa hai fragment

### 6.1. Dùng kết quả phân biệt để quan sát dispatch

Có thể tạo fixture tối thiểu trong source set test:

```java
interface PrimaryRoute {
    String routingSource();
}

interface SecondaryRoute {
    String routingSource();
}

class PrimaryRouteImpl implements PrimaryRoute {
    @Override
    public String routingSource() {
        return "primary";
    }
}

class SecondaryRouteImpl implements SecondaryRoute {
    @Override
    public String routingSource() {
        return "secondary";
    }
}
```

```java
interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PrimaryRoute,
                SecondaryRoute {
}
```

Trong mô hình repository fragments của Spring Data, các fragment tùy chỉnh được ghép theo thứ tự khai báo; thứ tự này được dùng để phân giải trường hợp nhiều fragment cùng đóng góp một chữ ký. Với khai báo trên, test cần xác nhận `PrimaryRoute` là đường được chọn.

```java
@Test
void usesFirstDeclaredMatchingFragment() {
    assertThat(customerRepository.routingSource())
        .isEqualTo("primary");
}
```

Test giả định `customerRepository` được inject từ context thật, hai implementation được phát hiện theo cấu hình test và `Customer` có mapping hợp lệ cho module. Nếu gọi trực tiếp `PrimaryRouteImpl`, assertion không kiểm tra được dispatch.

Có thể tạo repository fixture thứ hai với thứ tự `SecondaryRoute, PrimaryRoute` để xác nhận kết quả đổi thành `secondary`. Hai fixture nên nằm trong phạm vi scan test riêng, tránh để repository phụ và implementation thử nghiệm đi vào cấu hình ứng dụng.

### 6.2. Không biến thứ tự thành quy tắc nghiệp vụ ngầm

Khi thay đổi thứ tự interface có thể đổi hành vi, cần có test mô tả rõ implementation mong muốn. Tuy vậy, nếu hai phương thức thực chất là hai nghiệp vụ khác nhau, đặt tên khác hoặc tách API thường giúp giảm phụ thuộc vào quy tắc ưu tiên.

Một marker như `routingSource()` chỉ chứng minh đường dispatch trong fixture. Nó không chứng minh truy vấn thật được gửi đến database hoặc collection đúng. Để kiểm tra điều đó, cần thao tác dữ liệu có thể đối chiếu ở store thực tế.

## 7. Fragment override CRUD cần kiểm thử rộng hơn một lời gọi

Fragment tùy chỉnh có ưu tiên cao hơn implementation cơ sở và các repository aspect khi giải quyết phương thức phù hợp. Vì vậy, một fragment khai báo `save` có thể thay đổi đường thực thi của CRUD.

Ví dụ hợp đồng generic cần khớp với phương thức định override:

```java
interface ValidatedSave<T> {
    <S extends T> S save(S entity);
}
```

```java
interface CustomerRepository
        extends CrudRepository<Customer, Long>, ValidatedSave<Customer> {
}
```

Một `save(Customer)` không nên bị mặc định là đã thay thế hoàn toàn mọi lời gọi generic `<S extends T> S save(S entity)`. Cần hiểu chữ ký, generic erasure và composition thực tế, rồi kiểm thử qua repository interface.

Những hành vi quan trọng cần xác nhận:

- Quy tắc validation chạy khi gọi `repository.save()`.
- Dữ liệu hợp lệ vẫn được ghi đúng một lần theo thiết kế.
- Kết quả trả về, ID và version mới được sử dụng đúng.
- Mapping, callback và auditing cần thiết vẫn tham gia đường ghi được chọn.
- Lỗi được truyền ra đúng và transaction hoàn tất theo yêu cầu.
- Các phương thức khác như `saveAll()` có hành vi được xác định riêng.

Không tự suy ra rằng override `save()` sẽ bắt được mọi thao tác bên trong implementation cơ sở của `saveAll()`. Lời gọi nội bộ và cách provider triển khai có thể không đi qua repository proxy theo cách người viết kỳ vọng.

Tránh inject chính repository cuối cùng vào fragment rồi gọi lại `repository.save()` để “ủy quyền” xuống base implementation. Lời gọi có thể quay lại fragment, gây đệ quy hoặc phụ thuộc vòng. Đường ủy quyền nên được thiết kế rõ bằng thành phần truy cập store phù hợp hoặc cơ chế mở rộng repository được module hỗ trợ.

Nếu cần áp dụng một thay đổi cho toàn bộ repository, custom base repository có thể là cơ chế khác với fragment. Test của cơ chế đó cần xác nhận factory thực sự dùng base class đã cấu hình; test một fragment riêng không thay thế được bước này.

## 8. Repository đa store và chế độ cấu hình nghiêm ngặt

Khi nhiều repository factory của các module cùng có mặt, Spring Data có thể đi vào chế độ cấu hình repository nghiêm ngặt để xác định repository thuộc store nào. Những tín hiệu quan trọng gồm interface đặc thù module và annotation trên domain type.

Ví dụ tổ chức rõ store:

```java
interface JpaCustomerRepository
        extends JpaRepository<JpaCustomerRow, Long>, JpaCustomerLookup {
}

interface MongoCustomerRepository
        extends MongoRepository<MongoCustomerDocument, String>,
                MongoCustomerLookup {
}
```

Ở đây, `JpaCustomerLookup` và `MongoCustomerLookup` là hai fragment khác nhau, có implementation và dependency theo từng store. Cùng một hợp đồng nghiệp vụ ở tầng service vẫn có thể được giữ thông qua adapter hoặc application port, mà không bắt một fragment tùy ý truy cập cả hai hạ tầng.

Mô hình lưu trữ cũng nên rõ ràng:

```java
@jakarta.persistence.Entity
class JpaCustomerRow {
    @jakarta.persistence.Id
    Long id;

    String tenantId;
    String email;
}
```

```java
@org.springframework.data.mongodb.core.mapping.Document("customers")
class MongoCustomerDocument {
    @org.springframework.data.annotation.Id
    String id;

    String tenantId;
    String email;
}
```

Các lớp trên chỉ minh họa cách nhận diện store; phần constructor, accessor và cấu hình mapping chi tiết được lược bỏ. Kiểu ID trong ví dụ cũng là lựa chọn của mô hình, không phải yêu cầu mọi entity JPA phải dùng `Long` hay mọi document phải dùng `String`.

Một repository chỉ kế thừa `CrudRepository` dùng chung có thể chưa đủ tín hiệu để xác định store nếu domain metadata cũng nhập nhằng. Gắn cả annotation JPA và MongoDB lên cùng domain type có thể khiến việc phân loại dựa vào annotation không rõ ràng. Không nên dùng các annotation chồng lấn rồi dựa vào thứ tự scan như một cơ chế routing.

### Interface cơ sở dùng chung cần `@NoRepositoryBean`

```java
@NoRepositoryBean
interface SharedRepository<T, ID> extends CrudRepository<T, ID> {
}
```

Annotation này cho biết interface cơ sở không phải repository cụ thể cần được tạo bean. Nó không tự chọn JPA, MongoDB hay transaction manager cho các interface con. Các repository cụ thể vẫn cần được gắn store một cách rõ ràng.

## 9. Kiểm thử package scan và hạ tầng được tham chiếu

Cấu trúc package tách store giúp giới hạn phạm vi factory:

```text
customer
    jpa
        repository
        model
    mongo
        repository
        model
```

Ví dụ cấu hình tường minh:

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = JpaRepositoryPackage.class,
    entityManagerFactoryRef = "jpaEntityManagerFactory",
    transactionManagerRef = "jpaTransactionManager"
)
class JpaRepositoryConfiguration {
}
```

```java
@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
    basePackageClasses = MongoRepositoryPackage.class,
    mongoTemplateRef = "customerMongoTemplate"
)
class MongoRepositoryConfiguration {
}
```

`JpaRepositoryPackage` và `MongoRepositoryPackage` là marker đặt trong đúng package repository tương ứng. Các bean hạ tầng có tên được tham chiếu phải được cấu hình trong ứng dụng hoặc test. Cấu hình repository scan không tự tạo đầy đủ entity manager factory, mapping context, client hay datastore.

Test context đa store cần xác nhận:

1. Cả hai repository cụ thể tồn tại với kiểu mong muốn.
2. Interface cơ sở không bị tạo thành repository độc lập.
3. Mỗi repository có thể thực hiện thao tác thật trên hạ tầng đúng.
4. Fragment của JPA không vô tình nhận dependency dành cho MongoDB và ngược lại.
5. Các package test fixture không bị scan ngoài phạm vi chủ định.

Nếu cả hai store có implementation cùng tên đơn giản như `CustomerSearchImpl`, cần xét quy tắc đặt tên bean và phát hiện implementation. Tách interface fragment theo store hoặc cấu hình bean tường minh có thể làm ý định rõ hơn. Thứ tự component scan không phải một hợp đồng đáng tin cậy để chọn store.

Ở tầng service, ưu tiên inject kiểu repository cụ thể. Nếu inject một interface nghiệp vụ chung có nhiều implementation, cần lựa chọn rõ bằng qualifier hoặc cấu hình tương ứng. Việc chọn được bean vẫn phải được kiểm chứng bằng hành vi, không chỉ bằng tên bean.

## 10. Dữ liệu đối chứng cho integration test đa store

### 10.1. Mỗi store cần có dữ liệu riêng có thể phân biệt

Ví dụ chuẩn bị dữ liệu với cùng tenant nhưng email khác nhau:

| Store | Dữ liệu dành cho test |
| --- | --- |
| JPA | Khách hàng `only-jpa@example.test` |
| MongoDB | Khách hàng `only-mongo@example.test` |

Luồng kiểm thử nên:

1. Tạo namespace, database hoặc tập dữ liệu test được cách ly phù hợp.
2. Ghi bản ghi JPA qua repository JPA và bảo đảm đạt mốc lưu cần kiểm tra.
3. Ghi document MongoDB qua repository MongoDB.
4. Đọc lại bằng repository tương ứng, tốt nhất từ phạm vi truy cập mới khi mục tiêu là kiểm tra dữ liệu lưu thực tế.
5. Xác nhận mỗi kết quả đúng model và đúng dữ liệu của store đó.
6. Dọn dữ liệu theo định danh thuộc test ở cả hai store.

Chỉ kiểm tra hai biến repository khác null chưa chứng minh kết nối đúng database. Cũng không nên lấy toàn bộ nội dung store rồi kỳ vọng không có bản ghi khác nếu test đang dùng hạ tầng chia sẻ.

Với JPA, persistence context có thể giữ đối tượng đã lưu; flush/clear hoặc một transaction đọc mới có thể cần thiết để tránh chỉ quan sát trạng thái trong bộ nhớ. Với MongoDB, cần cấu hình ghi/đọc phù hợp để kết quả phản ánh mức xác nhận mà test yêu cầu. Không áp dụng nguyên mô hình flush của JPA sang document store.

### 10.2. Dữ liệu tenant giúp phát hiện fragment bỏ điều kiện

Để kiểm tra fragment tìm kiếm, thêm hai bản ghi có cùng tiền tố tên ở `tenant-a` và `tenant-b`. Gọi repository với `tenant-a` rồi kiểm tra chính xác các ID trả về, thay vì chỉ kiểm tra có một kết quả chứa chữ “Lan”.

Test unit với mock chỉ thấy fragment đã truyền tenant. Test này mới chứng minh dependency truy cập store thực sự dùng điều kiện đó. Nếu có lọc trạng thái hiển thị, cần thêm bản ghi cùng tenant nhưng không được phép hiển thị.

### 10.3. Derived query, projection và fragment cần bằng chứng riêng

Một fragment hoạt động không chứng minh các method derived query của cùng repository đều đúng. Ngược lại, CRUD chạy thành công không chứng minh projection của fragment có mapping đúng.

Nếu fragment trả projection, cần kiểm tra từng giá trị nghiệp vụ quan trọng, đặc biệt khi hai store dùng tên field hoặc kiểu ID khác nhau. Với query by example, phân trang hoặc sắp xếp được fragment sử dụng, chỉ kiểm thử các khả năng module thực sự hỗ trợ và thêm thứ tự ổn định khi assertion phụ thuộc vị trí.

## 11. Không suy ra transaction xuyên store từ một annotation

Giả sử service được gắn:

```java
@Transactional("jpaTransactionManager")
public void createCustomerAndReadModel() {
    // Ghi bằng JpaCustomerRepository.
    // Ghi bằng MongoCustomerRepository.
    // Một lỗi nghiệp vụ xảy ra sau đó.
}
```

Annotation này chọn transaction manager JPA. Nó không tự làm thao tác MongoDB tham gia cùng một transaction nguyên tử với cơ sở dữ liệu quan hệ.

Một kịch bản kiểm thử có chủ đích có thể dùng cấu hình không có transaction MongoDB, ghi MongoDB thành công với xác nhận phù hợp, rồi phát sinh lỗi khiến transaction JPA rollback. Sau khi service kết thúc, đọc lại từ các phạm vi độc lập để quan sát: thay đổi JPA có thể đã rollback trong khi document MongoDB vẫn tồn tại.

Mục tiêu là chứng minh phạm vi bảo đảm thực tế của cấu hình đó, không phải đặt một kỳ vọng rollback xuyên store mà hệ thống chưa cung cấp. Nếu nghiệp vụ cần đồng bộ, cần thiết kế rõ cơ chế như outbox, cập nhật read model bất đồng bộ, retry có idempotency hoặc xử lý bù phù hợp.

Test đa store cũng cần dọn dữ liệu đúng phạm vi. Rollback của một test transaction JPA không tự dọn document MongoDB, message hoặc tác dụng phụ ở dịch vụ ngoài.

## 12. Kiểm thử cấu hình sai và nguyên nhân thất bại

Các cấu hình đáng tạo fixture kiểm thử âm gồm:

| Cấu hình sai | Điều cần xác nhận |
| --- | --- |
| Fragment không được phát hiện | Method không có implementation mong muốn; lỗi hoặc hành vi thay thế được nhận biết |
| Hai dependency cùng phù hợp nhưng không chọn bean | Context báo nhập nhằng tại dependency liên quan |
| Repository dùng chung không đủ tín hiệu chọn store | Repository bị bỏ qua hoặc không được tạo như mong muốn theo cơ chế của module |
| Scan package chồng lấn | Không tạo repository bằng factory sai hoặc tạo bean xung đột ngoài ý muốn |
| Tham chiếu sai entity manager factory hoặc template | Context hoặc thao tác thực tế thất bại đúng tại cấu hình cần kiểm tra |
| Model hoặc fragment dùng nhầm store | Mapping, query hoặc hành vi bộc lộ sai phạm vi |

Không phải mọi cấu hình nhập nhằng đều luôn làm context thất bại ngay. Một factory có thể bỏ qua repository mà nó không nhận diện được; hậu quả có thể chỉ xuất hiện khi inject hoặc khi gọi method. Vì vậy, test cần kiểm tra cả sự hiện diện của repository và hành vi mong muốn.

Nếu test kỳ vọng startup failure, phải xác định nguyên nhân thuộc cấu hình đang kiểm tra. Một lỗi kết nối database không sẵn sàng có thể làm test “thất bại như mong đợi” nhưng không chứng minh có xung đột fragment. Có thể dùng công cụ chạy context kiểm thử để thu lỗi và kiểm tra chuỗi nguyên nhân; tránh phụ thuộc toàn bộ message nếu không cần thiết.

Fixture sai nên nằm trong cấu hình test riêng, được import có chủ đích. Không để repository hoặc implementation cố ý sai bị quét vào những test không liên quan.

## 13. Ma trận kiểm thử cho một thiết kế hoàn chỉnh

| Mục tiêu | Ví dụ assertion có giá trị |
| --- | --- |
| Validation fragment | Tenant thiếu gây lỗi trước truy vấn |
| Composition | Gọi method trên repository proxy thực sự đi vào fragment |
| Ưu tiên chữ ký trùng | Kết quả nhận diện đúng fragment theo thứ tự đã chọn |
| Override CRUD | Quy tắc mới chạy, dữ liệu vẫn lưu đúng, lỗi và metadata đúng hợp đồng |
| Mapping từng store | Đọc lại giá trị từ store tương ứng, không chỉ dùng đối tượng còn trong bộ nhớ |
| Routing đa store | Dữ liệu chỉ có ở store JPA/MongoDB được đọc bằng đúng repository |
| Cách ly tenant | Không trả bản ghi cùng tiền tố thuộc tenant khác |
| Transaction | Kết quả khi một bước lỗi khớp phạm vi manager thực sự quản lý |
| Cấu hình sai | Nguyên nhân lỗi hoặc repository bị thiếu đúng với mục tiêu kiểm thử |

Không cần nhân mọi test unit thành test toàn ứng dụng. Chọn mức nhỏ nhất có thể quan sát cơ chế cần chứng minh, rồi bổ sung integration test cho wiring và semantics mà mock không thể xác nhận.

Đối với module reactive, test cần đăng ký vào publisher và chờ kết quả/lỗi bằng công cụ phù hợp. Inject được reactive repository hoặc tạo được `Mono`/`Flux` chưa chứng minh fragment đã thực hiện truy vấn. Callback đồng bộ và reactive, cũng như transaction manager tương ứng, cần được chọn đúng với đường truy cập.

## 14. Bài tập vận dụng

Một ứng dụng có repository JPA và MongoDB, cùng kế thừa một interface `CrudRepository` tổng quát. Domain type được gắn cả annotation JPA lẫn MongoDB. Hai fragment cùng có `save`, một fragment inject chính repository để gọi lại `save`. Test hiện tại chỉ mock repository và xác nhận service gọi phương thức một lần.

Hãy đề xuất bộ kiểm thử và thay đổi thiết kế để làm rõ:

1. Repository nào thuộc store nào và package nào do từng factory quản lý.
2. Fragment nào được ghép, chữ ký nào trùng và implementation nào có ưu tiên.
3. Vì sao lời gọi ủy quyền qua chính repository có nguy cơ đệ quy.
4. Cách chứng minh truy vấn thật cách ly tenant và dùng đúng store.
5. Điều gì xảy ra khi JPA rollback sau khi MongoDB đã ghi thành công.
6. Những cấu hình sai nào cần fixture test riêng và nguyên nhân nào phải quan sát.

Một lời giải tốt phải có cả test hành vi fragment, test composition qua proxy và test dữ liệu trên từng store. Chỉ thêm qualifier hoặc chỉ thấy context khởi tạo thành công chưa đủ để xác nhận toàn bộ thiết kế.

## 15. Điểm cần nhớ

Kiểm thử fragment cần tách logic implementation khỏi cơ chế ghép repository. Khi có chữ ký trùng, phải quan sát lời gọi qua proxy và bảo vệ thứ tự ưu tiên đã chọn. Với repository đa store, cần xác định rõ factory, mapping, dependency và tài nguyên mà mỗi repository sử dụng.

Các abstraction của Spring Data Commons giúp tổ chức API chung; bảo đảm truy vấn, CRUD, projection, auditing và transaction vẫn phải được kiểm chứng trên đường truy cập của module cụ thể. Bộ test có dữ liệu đối chứng và ranh giới cấu hình rõ sẽ phát hiện những lỗi mà mock repository hoặc assertion khác null không thể thấy.
