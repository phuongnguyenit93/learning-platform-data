# Ràng buộc bộ lọc từ web bằng QuerydslBinderCustomizer

## 1. Vì sao cần tùy chỉnh binding?

Spring Data Web hỗ trợ chuyển query parameter trên HTTP request thành một Querydsl `Predicate`. Khi controller nhận `Predicate` cùng `@QuerydslPredicate`, người dùng có thể gửi bộ lọc qua URL mà không cần tạo một repository method riêng cho từng tổ hợp điều kiện.

Tuy nhiên, không nên mặc định cho client lọc trên mọi thuộc tính của Entity. Một Entity có thể chứa password hash, trạng thái nội bộ, tenant ID, ghi chú riêng hoặc những trường không được phép công khai. Ngoài ra, cách so khớp mặc định có thể không đúng yêu cầu tìm kiếm của API.

`QuerydslBinderCustomizer` cho phép định nghĩa rõ:

- Thuộc tính nào được phép nhận filter từ request.
- Cách so khớp cho từng property hoặc cho cả một kiểu dữ liệu.
- Một giá trị được xử lý riêng hay nhiều giá trị được gom thành điều kiện `IN`.
- Những property cần loại khỏi binding.

Binder là ranh giới chuyển đổi filter HTTP thành predicate. Nó không thay thế xác thực người dùng, phân quyền, validation nghiệp vụ hoặc giới hạn phân trang.

## 2. Luồng xử lý từ HTTP tới repository

Luồng tổng quát:

```text
HTTP query parameters
        |
        v
@QuerydslPredicate argument resolver
        |
        v
QuerydslBindings + QuerydslBinderCustomizer
        |
        v
Querydsl Predicate
        |
        v
QuerydslPredicateExecutor.findAll(predicate, pageable)
        |
        v
JPA provider -> SQL -> database
```

Spring Data Web đọc các query parameter, chuyển giá trị sang kiểu Java phù hợp rồi dùng Querydsl bindings để tạo predicate. Repository triển khai `QuerydslPredicateExecutor<T>` có thể thực thi predicate đó.

`QuerydslBinderCustomizer` thường được triển khai ngay trên repository interface. Spring Data Web có thể tìm customizer của repository tương ứng với domain type khi xây predicate cho `@QuerydslPredicate`.

## 3. Điều kiện nền tảng

Để dùng cơ chế này, dự án cần:

- Spring Data JPA và Spring Data Web support.
- Querydsl JPA cùng annotation processor tương thích với phiên bản JPA/provider.
- Các lớp Q được sinh từ Entity, ví dụ `QCustomer`.
- Repository mở rộng `QuerydslPredicateExecutor<Customer>`.
- Spring MVC có Querydsl predicate argument resolver; trong cấu hình Spring thuần, bật `@EnableSpringDataWebSupport`. Với Spring Boot, kiểm tra web auto-configuration của phiên bản dự án để tránh đăng ký resolver trùng.

Ví dụ dưới đây dùng Jakarta Persistence như các ứng dụng Spring Boot 3+. Dự án Spring Boot 2 dùng namespace `javax.persistence` và cần bộ Querydsl artifact/annotation processor tương ứng. Không trộn Querydsl Jakarta và Querydsl javax trong cùng một build.

Q type như `QCustomer` được sinh trong quá trình build bởi annotation processor. Nếu IDE báo không tìm thấy Q class, kiểm tra cấu hình annotation processing, source set chứa generated sources và việc build đã chạy processor chưa.

## 4. Repository triển khai QuerydslBinderCustomizer

Giả sử Entity `Customer` có các thuộc tính `id`, `firstName`, `lastName`, `email`, `status`, `tenantId` và `passwordHash`.

```java
public interface CustomerRepository extends
        JpaRepository<Customer, Long>,
        QuerydslPredicateExecutor<Customer>,
        QuerydslBinderCustomizer<QCustomer> {

    @Override
    default void customize(QuerydslBindings bindings, QCustomer root) {
        // Chỉ cho phép các trường được liệt kê bên dưới.
        bindings.excludeUnlistedProperties(true);
        bindings.including(
            root.firstName,
            root.lastName,
            root.email,
            root.status
        );

        // Tìm tên theo chuỗi con, không phân biệt hoa thường.
        bindings.bind(String.class)
            .first((StringPath path, String value) ->
                path.containsIgnoreCase(value)
            );

        // Email phải khớp chính xác.
        bindings.bind(root.email)
            .first((path, value) -> path.eq(value));

        // Nhiều status được chuyển thành điều kiện IN.
        bindings.bind(root.status)
            .all((path, values) -> Optional.of(path.in(values)));
    }
}
```

Đây là phần khai báo cốt lõi; cần import `QCustomer` đã được sinh, `QuerydslBindings`, `QuerydslBinderCustomizer`, `QuerydslPredicateExecutor`, `StringPath` và `Optional` tương ứng.

`customize` nhận `bindings` và Q root đại diện cho Entity. `bindings.including(...)` kết hợp với `excludeUnlistedProperties(true)` tạo allow-list: chỉ `firstName`, `lastName`, `email` và `status` được dùng để tạo predicate từ request.

Binding theo kiểu `String.class` áp dụng quy tắc tìm chuỗi cho các property String được phép. Binding riêng `root.email` đặt quy tắc cụ thể cho email. Ví dụ dùng equality cho email, trong khi tên được tìm theo chuỗi con không phân biệt hoa thường.

## 5. Allow-list và deny-list

Với endpoint công khai, allow-list thường an toàn và dễ kiểm soát hơn:

```java
bindings.excludeUnlistedProperties(true);
bindings.including(root.firstName, root.lastName, root.status);
```

Khi bật `excludeUnlistedProperties(true)`, chỉ các property được đưa vào danh sách `including` mới được bind. Một property mới được thêm vào Entity sẽ không tự động trở thành filter HTTP.

Nếu dự án chủ động cho phép hầu hết property và chỉ cần loại vài trường, có thể dùng deny-list:

```java
bindings.excluding(root.passwordHash, root.tenantId);
```

Deny-list dễ bị bỏ sót khi Entity được mở rộng. Với API bên ngoài hoặc Entity chứa dữ liệu nhạy cảm, allow-list giúp review bề mặt filter rõ ràng hơn. Không đưa `passwordHash`, token, role nội bộ, audit field hoặc tenant ID vào allow-list chỉ vì chúng có trong Q type.

Việc một parameter không được bind không có nghĩa request đã được phân quyền. Quy tắc bảo mật vẫn phải được thực thi ở service/query layer.

## 6. Binding theo kiểu và binding theo property

Có hai phạm vi tùy chỉnh chính:

- **Theo kiểu:** `bindings.bind(String.class)` áp dụng cùng quy tắc cho các property cùng kiểu được phép bind.
- **Theo property:** `bindings.bind(root.email)` áp dụng quy tắc riêng cho một property cụ thể.

Ví dụ, tên và thành phố tìm theo chuỗi con nhưng email phải khớp chính xác:

```java
bindings.bind(String.class)
    .first((StringPath path, String value) -> path.containsIgnoreCase(value));

bindings.bind(root.email)
    .first((path, value) -> path.eq(value));
```

Binding theo property hữu ích khi một trường có semantics khác với phần còn lại. Tránh áp dụng `containsIgnoreCase` cho mọi String nếu có trường cần exact match, mã định danh, trạng thái hoặc chuỗi có quy tắc nghiệp vụ riêng.

## 7. first và all: một giá trị hay nhiều giá trị?

`first(...)` tạo binding từ giá trị đầu tiên được gửi cho parameter. `all(...)` nhận tập giá trị của parameter để xây dựng một predicate từ tất cả giá trị.

Ví dụ:

```java
bindings.bind(root.status)
    .all((path, values) -> Optional.of(path.in(values)));
```

Request:

```http
GET /customers?status=ACTIVE&status=VIP
```

Binding trên tạo predicate tương đương:

```text
status IN (ACTIVE, VIP)
```

Với `first`, các giá trị lặp tiếp theo không tham gia binding đó. Với `all`, định nghĩa rõ ý nghĩa của nhiều giá trị: `IN`, khoảng thời gian, hoặc một biểu thức khác. Không dùng `all` chỉ để gom dữ liệu nếu nghiệp vụ không có semantics cụ thể.

Nếu endpoint chỉ chấp nhận một giá trị nhưng request gửi nhiều giá trị, hãy quyết định cách xử lý và kiểm thử rõ ràng; không để hành vi phụ thuộc ngầm vào thứ tự query parameter.

## 8. Ví dụ controller nhận Predicate từ request

```java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public Page<Customer> search(
            @QuerydslPredicate(root = Customer.class) Predicate predicate,
            @PageableDefault(size = 20, sort = "id") Pageable pageable) {
        return repository.findAll(predicate, pageable);
    }
}
```

`@QuerydslPredicate(root = Customer.class)` yêu cầu Spring Data tạo predicate cho domain type `Customer`. Repository có `QuerydslBinderCustomizer<QCustomer>` để định nghĩa các binding. `Pageable` được xử lý riêng bởi Spring Data Web; `page`, `size` và `sort` không phải property filter thông thường trong Querydsl predicate.

Ví dụ request:

```http
GET /customers?firstName=an&email=lan%40example.com&status=ACTIVE&status=VIP&page=0&size=20&sort=id,desc
```

Với repository ở trên:

- `firstName=an` tìm tên có chứa `an`, không phân biệt hoa thường.
- `email=lan@example.com` tìm email khớp chính xác.
- Hai giá trị `status` được kết hợp bằng `IN`.
- `page`, `size` và `sort` được dùng để phân trang/sắp xếp.

Trong API thực tế, nên map Entity sang DTO thay vì serialize toàn bộ Entity. Điều này tránh vô tình trả các field nội bộ hoặc khởi tạo association LAZY khi serialize.

## 9. Bật Spring Data Web support

Trong cấu hình Spring thuần, có thể bật hỗ trợ argument resolver bằng:

```java
@Configuration
@EnableSpringDataWebSupport
public class WebConfiguration {
}
```

Với Spring Boot, Spring Data Web thường được cấu hình qua auto-configuration khi các dependency phù hợp có mặt. Hãy kiểm tra cấu hình cụ thể của phiên bản Spring Boot/Spring Data đang dùng; không đăng ký thủ công một resolver thứ hai nếu auto-configuration đã cung cấp.

Nếu `@QuerydslPredicate` không được resolve và controller nhận lỗi thiếu argument resolver, kiểm tra dependency Spring Data Web, Querydsl classpath và cấu hình web support trước khi sửa repository customizer.

## 10. Bind property lồng nhau và quan hệ

Q type có thể biểu diễn property path lồng nhau. Ví dụ nếu `Customer` có một association `address` và `Address` có `city`, có thể bind path phù hợp:

```java
bindings.including(root.address.city);
bindings.bind(root.address.city)
    .first((path, value) -> path.containsIgnoreCase(value));
```

Đoạn này giả định `address` là persistent path được Querydsl sinh trong QCustomer, ví dụ `@Embedded` hoặc association được mapping hợp lệ. Với association, query có thể tạo JOIN; kiểm tra SQL và index nếu filter được dùng thường xuyên.

Cần thận trọng khi expose đường dẫn qua quan hệ to-many như `orders.items.productCode`. Join collection có thể nhân hàng root, làm truy vấn phức tạp và ảnh hưởng count/pagination. Không bind sâu toàn bộ graph chỉ vì Q type cho phép truy cập path. Với điều kiện tồn tại trên collection, một predicate EXISTS được xây dựng rõ trong service/custom repository thường dễ kiểm soát hơn.

## 11. Binding không thay thế validation

Query parameter là dữ liệu không tin cậy. Conversion Service có thể chuyển chuỗi sang enum, số, UUID hoặc thời gian; nếu không chuyển được, request có thể bị từ chối khi argument được resolve. Tuy nhiên, chuyển kiểu thành công không có nghĩa giá trị hợp lệ theo nghiệp vụ.

Cần xác định:

- Chuỗi tìm kiếm có độ dài tối đa.
- Danh sách status có bao nhiêu phần tử được chấp nhận.
- Khoảng ngày có hợp lệ và không vượt quá thời gian cho phép.
- Page size tối đa.
- Sort property nào được phép.
- Filter nào cần quyền đặc biệt.

Ví dụ `status=UNKNOWN` có thể không chuyển được thành enum. `size=100000` có thể tạo truy vấn quá nặng nếu không giới hạn. Hãy kiểm tra input và chuẩn hóa giá trị ở web/service layer; không trông chờ QuerydslBinderCustomizer làm toàn bộ validation.

## 12. Binding không thay thế authorization

Allow-list chỉ quyết định property nào client có thể dùng để lọc. Nó không bảo đảm user chỉ nhìn thấy dữ liệu họ được phép truy cập.

Ví dụ hệ thống multi-tenant phải luôn áp dụng tenant hiện tại từ security context, không nhận tenant ID do client tự gửi làm ranh giới bảo mật:

```java
QCustomer customer = QCustomer.customer;

BooleanBuilder secured = new BooleanBuilder();
secured.and(requestPredicate);
secured.and(customer.tenantId.eq(currentTenantId));

Page<Customer> page = repository.findAll(secured, pageable);
```

Đây là phần minh họa cho service layer; `currentTenantId` phải lấy từ principal/security context đã xác thực. Nếu không có request filter, vẫn phải áp dụng điều kiện tenant. Không cho phép client bỏ hoặc ghi đè predicate phân quyền bằng cách gửi parameter khác.

Không bind `tenantId`, `ownerId`, `role`, `isAdmin` hoặc trạng thái nội bộ như filter công khai để rồi coi đó là cơ chế bảo vệ. Authorization phải do server áp đặt và được kiểm thử độc lập.

## 13. Sort là một bề mặt input riêng

`Pageable` được resolve tách khỏi Querydsl Predicate. Vì vậy `QuerydslBinderCustomizer` không tự giới hạn các trường client có thể gửi trong `sort`.

Ví dụ:

```http
GET /customers?sort=createdAt,desc&sort=lastName,asc
```

Chỉ cho phép sort theo các property được API hỗ trợ. Có thể chuẩn hóa/allow-list Sort trong service hoặc cấu hình `SortHandlerMethodArgumentResolver` phù hợp. Không nối trực tiếp chuỗi sort từ request vào JPQL/native SQL và không dùng `JpaSort.unsafe` với nội dung client gửi.

Thêm khóa duy nhất làm tie-breaker nếu phân trang cần thứ tự ổn định, ví dụ `createdAt DESC, id DESC`. Kiểm tra property sort là tên property Java hoặc alias được query hỗ trợ, không phải tên cột vật lý.

## 14. Khi nào nên dùng QuerydslBinderCustomizer và khi nào không?

| Trường hợp | Hướng xử lý |
| --- | --- |
| Trang tìm kiếm GET có vài filter đơn giản, mỗi filter ánh xạ rõ vào property | `@QuerydslPredicate` + `QuerydslBinderCustomizer` |
| Muốn dùng contains-ignore-case cho String hoặc exact match cho một field | Binding theo kiểu/property |
| Cho phép nhiều giá trị enum và muốn `IN` | Binding `all(...)` |
| Điều kiện AND/OR lồng nhau theo quy tắc nghiệp vụ | Xây predicate trong service bằng Querydsl |
| Filter phụ thuộc quyền user, tenant hoặc dữ liệu được phép xem | Kết hợp predicate server-side trong service |
| Join collection, aggregate, subquery hoặc projection phức tạp | Querydsl query/custom repository rõ ràng |
| Request có cấu trúc phức tạp, cần validation nhiều trường | Search DTO rồi chuyển thành Querydsl predicate |

Binder rất hữu ích cho filter HTTP dạng key/value. Khi API có nhiều điều kiện phụ thuộc lẫn nhau, một request DTO có validation rõ và service tự xây predicate có thể dễ kiểm soát hơn việc để mọi query parameter tự động trở thành điều kiện.

## 15. Kiểm thử binding

Viết integration test ở tầng web để xác nhận request thực sự được chuyển thành predicate đúng. Ví dụ các ca nên có:

1. `firstName=an` tìm chuỗi con không phân biệt hoa thường.
2. `email=...` dùng exact match theo binding riêng.
3. `status=ACTIVE&status=VIP` tạo điều kiện `IN`.
4. Parameter không nằm trong allow-list không được đưa vào predicate.
5. Field nhạy cảm như `passwordHash` không thể lọc qua endpoint.
6. Giá trị enum/number/date sai định dạng được xử lý như lỗi request phù hợp.
7. Filter không làm mất điều kiện tenant/owner cố định.
8. `page`, `size`, `sort` được xử lý riêng và có giới hạn.
9. Association filter không tạo duplicate root hoặc count sai.
10. Kết quả được map sang DTO và không trả field nội bộ.

Unit test trực tiếp `customize(...)` có thể kiểm tra cấu hình binding, nhưng không thay thế MockMvc/WebTestClient integration test vì cần xác nhận argument resolver, conversion và repository phối hợp đúng.

## 16. Lỗi thường gặp và cách xử lý

**`@QuerydslPredicate` không được resolve.** Kiểm tra Spring Data Web support, Querydsl dependency và cấu hình argument resolver.

**Repository không áp dụng customizer.** Kiểm tra repository có implement `QuerydslBinderCustomizer<QCustomer>` đúng domain root và controller dùng đúng `root = Customer.class`.

**QCustomer không tồn tại.** Kiểm tra annotation processor và generated sources; không tự viết Q type thay cho code generation.

**Property bị từ chối hoặc không lọc.** Kiểm tra allow-list, tên property Java, kiểu Q path và conversion từ query string.

**String filter tìm chính xác thay vì contains.** Kiểm tra binding type-level/property-level có đang được áp dụng và request dùng đúng tên parameter.

**Nhiều giá trị chỉ lấy một giá trị.** Dùng `all(...)` nếu nghiệp vụ cần xử lý toàn bộ values; `first(...)` chỉ xử lý giá trị đầu.

**Một field mới vô tình được expose.** Dùng `excludeUnlistedProperties(true)` và `including(...)` thay vì chỉ dựa vào deny-list.

**Query chậm hoặc Page có count sai sau khi bind quan hệ.** Kiểm tra JOIN to-many, duplicate root, count, index và cân nhắc EXISTS/custom predicate.

**User có thể đọc dữ liệu tenant khác.** Binder không phải authorization. Thêm predicate tenant/owner từ server và test truy cập chéo tenant.

**Sort không an toàn hoặc không hợp lệ.** Allow-list Sort độc lập với filter binding; không ghép chuỗi sort tùy ý.

## 17. Checklist thiết kế endpoint

- Bật Querydsl web support và xác nhận `@QuerydslPredicate` được resolve.
- Repository mở rộng `QuerydslPredicateExecutor<T>` và triển khai `QuerydslBinderCustomizer<QT>`.
- Dùng allow-list cho các property được phép lọc từ web.
- Tùy chỉnh String, enum, number và multi-value theo semantics nghiệp vụ.
- Dùng `first` cho một giá trị và `all` cho toàn bộ giá trị.
- Chỉ expose nested path khi đã đánh giá join và cardinality.
- Giữ tenant/owner/permission predicates ở server-side.
- Giới hạn page size và allow-list sort riêng.
- Validate độ dài, số lượng và miền giá trị của query parameters.
- Map Entity sang DTO và kiểm thử HTTP-to-predicate trên database phù hợp.

`QuerydslBinderCustomizer` biến query parameter thành bộ lọc có quy tắc rõ ràng. Allow-list giữ bề mặt tìm kiếm nhỏ, binding theo property/type thể hiện đúng cách so khớp, còn authorization và sort vẫn phải được kiểm soát riêng. Kết hợp binder với predicate server-side và integration test giúp endpoint tìm kiếm linh hoạt mà không mở rộng quyền truy vấn ngoài ý muốn.