# QueryCreationException hoặc query lookup không tìm thấy triển khai

## 1. Lỗi tạo query khác lỗi không có dữ liệu

Một repository đã được phát hiện vẫn có thể không khởi tạo được vì Spring Data không tìm thấy cách thực thi một phương thức hoặc không tạo được query hợp lệ cho phương thức đó. Ở nhiều đường tích hợp, lỗi xuất hiện dưới dạng `QueryCreationException`, có thể bị bọc trong lỗi tạo bean rồi lỗi dependency của service.

Điều cần chẩn đoán không chỉ là tên exception, mà là ba câu hỏi:

1. Phương thức nào đang được xử lý?
2. Framework dự kiến thực thi nó bằng base implementation, fragment hay query?
3. Nếu đi theo query, chiến lược lookup đang tìm query khai báo hay tạo query từ tên?

Một truy vấn hợp lệ trả về danh sách rỗng hoặc `Optional.empty()` không phải lỗi tạo query. Tương tự, lỗi kết nối hoặc lỗi dữ liệu khi thực thi có thể thuộc giai đoạn khác, dù cuối cùng service cũng không nhận được kết quả.

Trong Spring Data Commons, query method và query lookup là các abstraction dùng chung. Cú pháp truy vấn, từ khóa, mapping, validation và thời điểm tạo query cụ thể vẫn phụ thuộc module như JPA, MongoDB, JDBC hoặc R2DBC.

## 2. Xác định một method đi vào nhánh thực thi nào

Một repository proxy có thể kết hợp nhiều nguồn hành vi:

```text
Lời gọi repository
    -> phương thức cơ sở hoặc khả năng do module cung cấp
    -> implementation fragment tùy chỉnh đã được ghép
    -> default method có phần thân khi phù hợp
    -> query method cần được lookup hoặc tạo
```

Sơ đồ thể hiện các nguồn hành vi, không phải một thuật toán ưu tiên đầy đủ áp dụng cho mọi chữ ký. Composition, phương thức dành riêng và query method có quy tắc nhận diện cụ thể.

Ví dụ:

| Khai báo | Hướng cần kiểm tra |
| --- | --- |
| `findById(id)` kế thừa từ repository cơ sở | Hợp đồng CRUD và implementation của module |
| `findByEmail(email)` | Có thể là derived query hoặc query khai báo |
| Method được gắn `@Query` của module | Query khai báo và chiến lược lookup |
| `loadForTenant(id, tenantId)` thuộc fragment | Fragment có thực sự được phát hiện và ghép không? |
| Default method có thân gọi các method khác | Thân method và các lời gọi bên trong |

Nếu fragment không được ghép, một method mà người viết xem là “đã có implementation” có thể bị xử lý như query method. Khi framework cố suy ra thuộc tính từ tên method tùy chỉnh, lỗi nhận được có thể trông như lỗi derived query.

Vì vậy, đừng đổi tên một nghiệp vụ tùy chỉnh chỉ để parser thôi báo lỗi trước khi xác định nó có nên đi qua parser hay không.

## 3. Hiểu ba chiến lược query lookup

Spring Data định nghĩa các key trong `QueryLookupStrategy.Key`. Khả năng hỗ trợ và cấu hình của từng key cần được xác nhận cho module đang dùng.

| Chiến lược | Ý nghĩa chính | Dạng thất bại đáng chú ý |
| --- | --- | --- |
| `CREATE` | Tạo query từ tên method theo cơ chế của module | Tên, thuộc tính, toán tử hoặc chữ ký không tạo được query |
| `USE_DECLARED_QUERY` | Tìm query đã khai báo theo các cơ chế module hỗ trợ | Không có query khai báo phù hợp hoặc query khai báo không hợp lệ |
| `CREATE_IF_NOT_FOUND` | Tìm query khai báo; nếu không có thì thử tạo từ tên method | Query khai báo lỗi, hoặc nhánh tạo từ tên cũng thất bại |

`CREATE_IF_NOT_FOUND` là lựa chọn mặc định phổ biến trong cấu hình repository Spring Data. Tuy nhiên, cần kiểm tra cấu hình và khả năng thực tế, không suy ra mọi module/API đều hỗ trợ mọi chiến lược giống nhau.

### Không có query khác với có query nhưng query sai

Với nhánh tìm query khai báo, hai tình huống cần phân biệt:

- **Không tìm thấy khai báo:** chiến lược có fallback có thể chuyển sang tạo query từ tên.
- **Tìm thấy khai báo nhưng không tạo/validate được:** không nên kỳ vọng framework bỏ qua query sai rồi âm thầm dùng derived query.

Ví dụ một `@Query` JPA viết sai JPQL vẫn cần được sửa. Fallback không phải cơ chế che lỗi cú pháp của query đã được chọn.

### Ví dụ cấu hình riêng cho JPA

```java
@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackageClasses = CustomerRepository.class,
    queryLookupStrategy = QueryLookupStrategy.Key.USE_DECLARED_QUERY
)
class CustomerRepositoryConfiguration {
}
```

Ví dụ dùng `org.springframework.data.repository.query.QueryLookupStrategy`, lược bỏ các import khác. Class cấu hình phải được nạp và hạ tầng JPA phải được cung cấp phù hợp.

Với cấu hình này, một method có tên suy ra hợp lệ như `findByEmail` vẫn cần query khai báo theo cơ chế được hỗ trợ. Thêm một tên method đúng ngữ pháp không giải quyết yêu cầu của chiến lược `USE_DECLARED_QUERY`.

## 4. Đọc exception từ method tới nguyên nhân cụ thể

Một chuỗi lỗi có thể được hình dung như sau:

```text
Không tạo được service vì thiếu dependency hoạt động được
    -> không tạo được repository
    -> không tạo được query cho một Java method cụ thể
    -> không phân giải được thuộc tính hoặc query khai báo không hợp lệ
```

Tên class exception và số lớp bọc phụ thuộc module cùng đường thực thi. Không cần chuỗi lỗi phải giống chính xác sơ đồ mới bắt đầu chẩn đoán.

Thông tin nên ghi nhận:

- Tên đầy đủ của repository interface.
- Chữ ký method, gồm tham số và kiểu trả về.
- Domain type và module đang xử lý method.
- Query lookup strategy có hiệu lực.
- Query được chọn: annotation, named query hay derived query.
- Nguyên nhân giải thích trực tiếp phần không thể xử lý.

`QueryCreationException` là dấu hiệu thuộc đường tạo query, không phải một chẩn đoán hoàn chỉnh. Đọc cause giúp phân biệt sai property path, thiếu tham số, query language sai hoặc tính năng không được module hỗ trợ.

## 5. Nhánh derived query: tên đúng ý định nhưng có thể sai mô hình

### 5.1. Lỗi chính tả và tên thuộc tính Java

Giả sử model có `email` nhưng method là:

```java
Optional<Customer> findByEamil(String email);
```

Parser không tìm được thuộc tính phù hợp. Lỗi như `PropertyReferenceException` có thể xuất hiện trực tiếp hoặc trong chuỗi nguyên nhân của lỗi tạo query.

Sửa tên theo thuộc tính Java:

```java
Optional<Customer> findByEmail(String email);
```

Nếu dữ liệu được lưu dưới tên `email_address` nhưng Java property là `emailAddress`, derived query vẫn dựa trên `EmailAddress`, không dựa trực tiếp vào tên cột hoặc field lưu trữ.

### 5.2. Đường dẫn lồng nhau và field che khuất

Mô hình có thể đồng thời chứa:

```text
Customer.addressZipCode
Customer.address.zipCode
```

`findByAddressZipCode` có thể được hiểu là thuộc tính trực tiếp khi thuộc tính đó tồn tại. Nếu muốn phân tách rõ đường đi, có thể dùng:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

Một số lỗi xuất hiện vì parser chọn nhánh camel case khác mong muốn, chẳng hạn gặp `addressZip` trước khi xét phần tiếp theo. Không nên chỉ nối thêm từ vào tên method mà không kiểm tra đường dẫn thực tế.

Ngay cả khi parser chấp nhận đường dẫn Java, module vẫn có thể không hỗ trợ truy vấn qua mapping đó. Parse thành công và tạo được query cho datastore là hai mức kiểm tra khác nhau.

### 5.3. Chữ ký không khớp predicate

Ví dụ method yêu cầu hai điều kiện nhưng chỉ có một giá trị:

```java
List<Customer> findByEmailAndStatus(String email);
```

Tên thuộc tính có thể đúng, nhưng chữ ký thiếu dữ liệu cho predicate. Method cần có tham số tương ứng hoặc cần thay đổi yêu cầu truy vấn.

Những trường hợp khác gồm:

- `Between` không có đủ hai giá trị phù hợp.
- `IsNull` bị thêm một tham số predicate không đúng nhu cầu.
- `In` dùng kiểu tham số mà module không chấp nhận.
- Nhầm `Pageable` hoặc `Sort` với giá trị cần bind cho điều kiện.
- Toán tử không phù hợp kiểu thuộc tính hoặc không được store hỗ trợ.

Không phải tất cả lỗi chữ ký đều xuất hiện cùng một exception hoặc cùng thời điểm. Cần đọc nguyên nhân cụ thể của module thay vì chỉ đếm tham số bằng mắt.

## 6. Nhánh query khai báo: kiểm tra đúng ngôn ngữ và đúng annotation

### 6.1. Ví dụ JPA có named parameter

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface CustomerRepository extends JpaRepository<Customer, Long> {

    @Query("""
        select c from Customer c
        where c.tenantId = :tenantId and c.email = :email
        """)
    Optional<Customer> findForTenantByEmail(
        @Param("tenantId") String tenantId,
        @Param("email") String email
    );
}
```

Ví dụ dùng JPQL, giả định entity tên `Customer` có các property tương ứng và Java hỗ trợ text block. Các import còn lại cùng mapping được lược bỏ.

Annotation `@Query` thuộc module cụ thể. Annotation JPA không phải một annotation query dùng chung cho mọi repository MongoDB hoặc R2DBC.

### 6.2. JPQL dùng entity và property, không dùng tên bảng theo SQL

Đoạn sau là SQL, không phải JPQL:

```sql
select * from customer where email_address = :email
```

Nếu đặt nó vào query được cấu hình là JPQL, provider có thể không tạo được query. Có hai hướng thiết kế khác nhau:

- Viết JPQL theo entity name và Java property đúng.
- Chủ động dùng native query khi module hỗ trợ, với cấu hình và mapping kết quả phù hợp.

Đổi sang native query chỉ để tránh lỗi parser không bảo đảm câu SQL đúng. Lỗi schema, tên bảng, cú pháp dialect hoặc mapping kết quả có thể chỉ được phát hiện khi datastore thực thi.

Nếu entity dùng tên tùy chỉnh qua annotation, tên JPQL cần khớp entity name đó. Không suy ra tên entity luôn bằng tên bảng hoặc tên class đơn giản.

### 6.3. Binding tham số cần nhất quán

Kiểm tra tên trong query và `@Param`, số thứ tự của positional parameter, cùng các tham số đặc biệt của repository API. Không trộn các cách bind một cách tùy tiện.

Một refactor đổi tên annotation parameter nhưng giữ nguyên query có thể làm việc tạo query thất bại. Dùng `@Param` rõ ràng trong ví dụ giúp ý định không phụ thuộc việc Java parameter name có được giữ trong artifact hay không.

Kiểu trả về cũng cần phù hợp với hình dạng select. Query trả scalar, entity hay DTO không thể được dùng thay thế nhau chỉ bằng cách sửa chữ ký method. Một số lỗi projection/constructor được phát hiện sớm, số khác chỉ xuất hiện khi có kết quả thực tế.

## 7. Named query không được tìm thấy

Trong Spring Data JPA, một quy ước thường gặp cho named query là tên domain class đơn giản ghép với tên method, chẳng hạn `Customer.findByEmail`. Ứng dụng cũng có thể dùng cách chọn named query tường minh theo API tương ứng.

Ví dụ khai báo JPA:

```java
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = ?1"
)
@Entity
class Customer {
    // ID, property và constructor theo mapping JPA.
}
```

Khi named query không được tìm thấy, cần xem:

1. Tên khai báo có khớp tên mà repository đang tìm không?
2. Entity hoặc nơi khai báo named query có thực sự thuộc persistence unit không?
3. Tài nguyên cấu hình query có nằm trong artifact và vị trí module thực sự nạp không?
4. Repository có đang dùng entity manager factory khác với nơi named query được đăng ký không?
5. Có annotation hoặc cấu hình khác chọn một tên query tường minh không?

Với `USE_DECLARED_QUERY`, thiếu query khai báo là vấn đề cần giải quyết trực tiếp. Với chiến lược có fallback, method có thể tiếp tục chạy bằng derived query, khiến việc thiếu named query khó nhận ra nếu chỉ kiểm tra ứng dụng khởi động.

Nếu nghiệp vụ cần chính query khai báo đó, test nên kiểm tra hành vi và các điều kiện đặc thù của nó. Không chỉ dựa vào việc method có trả dữ liệu.

## 8. Method tùy chỉnh không được nối với fragment

### 8.1. Một method không có `By` có thể vốn không phải derived query

Giả sử repository muốn có nghiệp vụ đọc khách hàng trong tenant:

```java
interface CustomerScopedAccess {
    Optional<Customer> loadForTenant(Long id, String tenantId);
}
```

```java
interface CustomerRepository
        extends JpaRepository<Customer, Long>, CustomerScopedAccess {
}
```

Implementation theo quy ước fragment mặc định có thể là:

```java
class CustomerScopedAccessImpl implements CustomerScopedAccess {

    private final EntityManager entityManager;

    CustomerScopedAccessImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public Optional<Customer> loadForTenant(Long id, String tenantId) {
        return entityManager.createQuery("""
                select c from Customer c
                where c.id = :id and c.tenantId = :tenantId
                """, Customer.class)
            .setParameter("id", id)
            .setParameter("tenantId", tenantId)
            .getResultList()
            .stream()
            .findFirst();
    }
}
```

Ví dụ lược bỏ import; `EntityManager` thuộc persistence API phù hợp và phải được nối đúng persistence unit. Kết quả được lấy thành list rồi mới tạo stream Java trong bộ nhớ. Model giả định ID duy nhất; kiểm tra quyền truy cập vẫn thuộc trách nhiệm thiết kế nghiệp vụ.

### 8.2. Nếu implementation không được ghép

Khi `CustomerScopedAccessImpl` không được tìm thấy hoặc không được ghép đúng, framework có thể xử lý `loadForTenant` như query method. Với nhánh tạo từ tên, thông báo có thể nói không tìm được một property suy ra từ tên method. Với nhánh chỉ dùng query khai báo, lỗi có thể là không có query khai báo tương ứng.

Điểm cần kiểm tra là:

- Repository có thực sự kế thừa interface fragment không?
- Implementation có implement đúng interface và chữ ký không?
- Tên cùng hậu tố có khớp cấu hình fragment không?
- Package và runtime classpath có cho phép phát hiện implementation không?
- Có nhiều implementation hoặc bean name gây lựa chọn ngoài ý định không?
- Dependency của implementation có được tạo đúng không?

Đừng đổi `loadForTenant` thành một tên derived query rất dài chỉ để che việc fragment không được phát hiện. Nếu chọn chuyển hẳn sang derived query hoặc `@Query`, đó phải là quyết định thiết kế có chủ đích và được kiểm chứng lại.

Cũng không mặc định thêm `@Repository` lên bất kỳ class nào là repository composition sẽ tự nối đúng. Quy tắc phát hiện fragment và cấu hình module mới quyết định đường ghép thực tế.

## 9. Query nội dung đúng nhưng count query sai

Một method trả `Page<T>` có thể cần query đếm để cung cấp metadata tổng. Với query phức tạp, việc tạo hoặc kiểm tra count query có thể là nơi thất bại, dù query lấy nội dung trông hợp lệ.

Ví dụ JPA có thể khai báo hai phần rõ ràng:

```java
@Query(
    value = "select c from Customer c where c.status = :status",
    countQuery = "select count(c) from Customer c where c.status = :status"
)
Page<Customer> findPageForStatus(
    @Param("status") String status,
    Pageable pageable
);
```

Ví dụ đơn giản nhằm chỉ ra hai query cần nhất quán. Với join, distinct, grouping hoặc native query, cần xác định tổng đang đếm đơn vị nghiệp vụ nào. Một count query chạy được nhưng đếm sai vẫn là lỗi.

Nếu giao diện chỉ cần biết còn dữ liệu tiếp hay không, `Slice` có thể là hợp đồng khác phù hợp. Tuy nhiên, không đổi `Page` sang `Slice` chỉ để bỏ một count query đang sai khi sản phẩm vẫn cần tổng chính xác.

## 10. Thời điểm lỗi và khác biệt theo store

| Giai đoạn | Lỗi có thể gặp | Hướng xác nhận |
| --- | --- | --- |
| Tạo repository hoặc query object | Không tìm query khai báo, property path sai, chữ ký không phù hợp | Đọc method và lookup strategy |
| Validation của provider | JPQL, kiểu select hoặc mapping không hợp lệ | Đọc cause thuộc provider và model |
| Lần gọi đầu khi bootstrap trì hoãn | Query chưa được tạo sớm | Gọi method liên quan trong test phù hợp |
| Thực thi ở datastore | SQL/native syntax, collection/schema, quyền hoặc kết nối | Xem thao tác thực tế và lỗi store |
| Đọc và chuyển kết quả | DTO constructor, converter hoặc kiểu trả về không phù hợp | Kiểm thử với kết quả có dữ liệu |

Không phải mọi lỗi query đều là `QueryCreationException`. Một số query được tạo thành công nhưng chỉ sai khi thực thi với dữ liệu hoặc datastore thật.

Với repository reactive, lỗi thực thi có thể chỉ được phát ra khi publisher được subscribe. Tạo được `Mono`/`Flux` chưa chứng minh query chạy thành công. Với bootstrap lazy ở mô hình khác, lỗi cũng có thể được dời đến lần gọi đầu.

Một từ khóa được parser Commons nhận diện không bảo đảm query creator của mọi store hỗ trợ nó. Cần phân biệt lỗi ngữ pháp tên, lỗi mapping và giới hạn khả năng của module để chọn cách sửa phù hợp.

## 11. Quy trình chẩn đoán theo bằng chứng

### Bước 1: Khoanh đúng method

Lấy chữ ký method từ exception, xác nhận repository và domain type. Nếu có nhiều store, xác định factory nào đang xử lý nó.

### Bước 2: Xác định nguồn implementation mong muốn

Method thuộc CRUD, fragment, default method hay query? Nếu fragment đáng ra xử lý nhưng query lookup lại xuất hiện, kiểm tra composition trước.

### Bước 3: Xác nhận lookup strategy có hiệu lực

Đọc cấu hình thực sự được nạp. Đừng suy ra chiến lược chỉ từ một class cấu hình có trong source nhưng đang bị profile hoặc phạm vi scan loại bỏ.

### Bước 4: Theo đúng nhánh được chọn

Với derived query, kiểm tra property path, từ khóa, tham số và kiểu trả về. Với query khai báo, kiểm tra annotation đúng module, named query, cú pháp, binding và mapping kết quả.

### Bước 5: Phân biệt thiếu khai báo với khai báo sai

Thiếu query có thể cho phép fallback; query đã được chọn nhưng không hợp lệ cần sửa tại nguồn. Không dựa vào fallback để lờ lỗi.

### Bước 6: Tái hiện trong phạm vi nhỏ phù hợp

Dùng repository và model liên quan cùng hạ tầng store kiểm thử cần thiết. Giữ dữ liệu có thể chứng minh các điều kiện quan trọng như tenant, trạng thái và cardinality.

### Bước 7: Kiểm chứng cả khởi tạo và hành vi

Context hoặc repository được tạo thành công chỉ là một mốc. Gọi method với dữ liệu đại diện để kiểm tra kết quả, tham số và trường hợp biên. Với method trả `Page`, kiểm tra cả nội dung và tổng.

## 12. Kiểm thử giúp phân biệt nguyên nhân

### Parser test cho tên method

Có thể dùng `PartTree` để kiểm tra tên và đường dẫn Java trong một test đơn vị:

```java
assertThrows(
    PropertyReferenceException.class,
    () -> new PartTree("findByTenantIdAndEamil", Customer.class)
);
```

Ví dụ dùng API parser của Spring Data Commons và JUnit Jupiter, giả định model có `tenantId` và `email`. Test này không validate JPQL, không tìm named query và không chứng minh fragment được ghép.

### Repository integration test

Với JPA, test slice như `@DataJpaTest` có thể giúp xác nhận query và mapping nếu model, scan và hạ tầng phù hợp. Với store khác, dùng cơ chế kiểm thử của module tương ứng.

Dữ liệu đối chứng nên có hai khách hàng cùng email ở hai tenant để phát hiện query quên tenant. Nếu method trả một phần tử, cần xác định dữ liệu nào là duy nhất; nhiều kết quả khi thực thi là vấn đề cardinality, không nhất thiết là lỗi query lookup.

Với query phân trang, có thể kiểm tra:

```java
assertThat(page.getContent())
    .extracting(Customer::getId)
    .containsExactlyElementsOf(expectedIds);

assertThat(page.getTotalElements()).isEqualTo(expectedTotal);
```

Ví dụ chỉ minh họa assertion, giả định thứ tự truy vấn đã được xác định và fixture đã được chuẩn bị. Không cần so sánh toàn bộ SQL sinh ra nếu mục tiêu là hành vi query.

### Context test cho chiến lược lookup

Nếu thiết kế cố ý yêu cầu `USE_DECLARED_QUERY`, có thể tạo cấu hình test riêng chứng minh method thiếu khai báo bị phát hiện. Cần kiểm tra nguyên nhân đúng là thiếu query, không phải database test không sẵn sàng.

Repository fixture cố ý sai nên được cách ly khỏi scan của các test khác. Không để một interface sai làm mọi context kiểm thử thất bại ngoài ý muốn.

## 13. Những cách sửa dễ che nguyên nhân

| Cách sửa | Điều có thể bị che |
| --- | --- |
| Chuyển toàn bộ sang `CREATE_IF_NOT_FOUND` | Named query bắt buộc đang bị thiếu |
| Thêm `@Query` vào method vốn thuộc fragment | Composition vẫn hỏng, logic tùy chỉnh khác chưa được nối |
| Chuyển JPQL sai thành native query mà không kiểm chứng | Lỗi bị dời sang runtime hoặc mapping kết quả |
| Đổi mọi kiểu trả về thành `List` | Cardinality và hợp đồng API bị thay đổi |
| Bật lazy bootstrap để startup qua | Query lỗi chỉ chuyển tới lần gọi đầu |
| Chỉ mock repository trong test | Không chạy query lookup và validation thực tế |
| Mở rộng package scan rất rộng | Có thể thêm cấu hình, repository hoặc implementation ngoài ý định |
| Bắt mọi exception rồi trả danh sách rỗng | Lỗi hệ thống bị hiểu thành không có dữ liệu |

Nên sửa đúng nhánh đang thất bại, giữ nguyên hợp đồng dữ liệu và dùng test phù hợp để xác nhận. Một thay đổi làm ứng dụng khởi động không tự chứng minh truy vấn đang dùng implementation mong muốn.

## 14. Tình huống thực hành

Một repository JPA vừa chuyển sang `USE_DECLARED_QUERY`. Nó có ba method:

1. `findByEmail` trước đây hoạt động bằng derived query nhưng chưa có query khai báo.
2. `findForTenantByEmail` có `@Query`, nhưng dùng tên cột SQL trong JPQL.
3. `loadForTenant` thuộc fragment, nhưng implementation bị chuyển ra ngoài phạm vi phát hiện.

Ba method có thể làm repository thất bại vì ba nguyên nhân khác nhau:

- Method thứ nhất không đáp ứng chiến lược chỉ dùng query khai báo.
- Method thứ hai có query được chọn nhưng nội dung không đúng ngôn ngữ/mapping.
- Method thứ ba đáng ra phải có custom implementation nhưng lại rơi vào query lookup.

Cách xử lý cần quyết định rõ chính sách cho từng method: bổ sung khai báo hoặc chọn chiến lược phù hợp, sửa JPQL, và khôi phục fragment composition. Không có một annotation chung có thể thay thế cả ba quyết định.

## 15. Bài tập vận dụng

Một ứng dụng báo `QueryCreationException` khi tạo repository. Log nêu một method tùy chỉnh và một tên thuộc tính không tồn tại. Nhóm phát triển đề xuất đổi method thành `findBy...`, trong khi thiết kế ban đầu đã có một fragment chứa nghiệp vụ tenant. Đồng thời, một named query cũ đã bị mất khỏi persistence unit và một query phân trang có tổng không đúng.

Hãy xác định:

1. Cần bằng chứng gì để biết method tùy chỉnh đang bị xử lý nhầm thành query method?
2. Khi nào fallback là hành vi hợp lệ, khi nào nó che việc thiếu query khai báo?
3. Cách tách lỗi content query khỏi count query và lỗi dữ liệu trả về.
4. Test nào kiểm tra parser, test nào kiểm tra composition và test nào cần store thật?
5. Vì sao không nên biến mọi lỗi thành danh sách rỗng hoặc chỉ dời lỗi sang lần gọi đầu?

Một lời giải tốt phải lần theo nguồn implementation mong muốn và lookup strategy, rồi chứng minh query cuối cùng thực hiện đúng điều kiện nghiệp vụ.

## 16. Điểm cần nhớ

`QueryCreationException` là điểm bắt đầu để tìm method và nguyên nhân, không phải kết luận rằng mọi lỗi đều do tên method. Query lookup có thể thất bại vì thiếu khai báo, khai báo sai, derived query không hợp lệ hoặc một fragment chưa được ghép khiến method đi sai nhánh.

Chẩn đoán hiệu quả cần xác định nguồn implementation, chiến lược lookup và khả năng module đang dùng. Sau khi repository tạo được, vẫn phải kiểm tra kết quả, binding, cardinality và metadata phân trang trên đường truy cập store thực tế.
