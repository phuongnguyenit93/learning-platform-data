# findAll, findAllById và giới hạn khi đọc tập dữ liệu lớn

Spring Data JPA cung cấp findAll() để đọc toàn bộ entity mà repository quản lý và findAllById(Iterable<ID>) để đọc các entity có ID nằm trong tập đầu vào. Hai method thuận tiện cho CRUD thông thường, nhưng có thể gây tốn bộ nhớ, nhiều SQL hoặc chậm khi dữ liệu lớn.

Khi thiết kế luồng đọc, cần biết chính xác method trả về gì, có bảo đảm thứ tự hay không, cách xử lý ID không tồn tại và thời điểm entity được quản lý trong persistence context. Với tập dữ liệu lớn, hãy chọn phân trang, Slice, projection, streaming hoặc keyset theo nhu cầu thực tế.

Bài này dùng Spring Data JPA 3.x và Spring Boot 3.x. Các ví dụ repository kế thừa JpaRepository.

## 1. findAll() đọc những gì?

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Gọi:

```java
List<Customer> customers = customerRepository.findAll();
```

findAll() trả về danh sách tất cả entity mà query của repository nhìn thấy theo mapping và các filter đang áp dụng. Với JpaRepository trong Spring Data 3.x, kiểu trả về là List<T>. Nếu dùng CrudRepository ở các phiên bản/API cũ hơn, hợp đồng cơ bản có thể trả Iterable<T>; hãy kiểm tra interface mà repository đang kế thừa.

Method này không nhận Pageable nên không giới hạn số bản ghi. Nếu bảng có vài chục nghìn hoặc vài triệu dòng, toàn bộ kết quả có thể được tải vào bộ nhớ ứng dụng. Các entity được load trong transaction thường được quản lý bởi persistence context, làm tăng thêm bộ nhớ và chi phí dirty checking.

findAll() phù hợp khi:

- Bảng nhỏ và giới hạn dữ liệu đã được kiểm soát.
- Công cụ quản trị cần hiển thị toàn bộ danh sách nhỏ.
- Dữ liệu cấu hình có số lượng ít.
- Test hoặc tác vụ đơn giản cần một tập dữ liệu nhỏ.

Không nên gọi findAll() trong API danh sách có thể tăng trưởng không giới hạn, tác vụ đồng bộ toàn bộ dữ liệu lớn hoặc job chạy định kỳ trên bảng giao dịch lớn.

## 2. findAll(Sort) và thứ tự kết quả

findAll() không cam kết thứ tự bản ghi. Nếu nghiệp vụ cần thứ tự ổn định, truyền Sort:

```java
List<Customer> customers = customerRepository.findAll(
    Sort.by(Sort.Direction.ASC, "id")
);
```

Tên thuộc tính trong Sort là property Java của entity, ví dụ id, createdAt hoặc name. Không truyền tên cột SQL nếu tên property khác tên column.

Sắp xếp theo một thuộc tính không duy nhất có thể tạo thứ tự không ổn định giữa các bản ghi có cùng giá trị. Khi phân trang hoặc xử lý theo lô, nên thêm khóa duy nhất làm tiêu chí cuối:

```java
Sort sort = Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
);
```

Thứ tự createdAt rồi id giúp phân biệt các bản ghi có cùng thời điểm tạo. Tuy vậy, findAll(Sort) vẫn tải toàn bộ danh sách; Sort chỉ thay đổi thứ tự, không giảm số bản ghi hay bộ nhớ.

## 3. findAllById() hoạt động thế nào?

findAllById nhận một Iterable chứa các ID và trả về những entity có ID tương ứng:

```java
List<Long> ids = List.of(10L, 20L, 30L);

List<Customer> customers =
        customerRepository.findAllById(ids);
```

Với JpaRepository trong Spring Data 3.x, kết quả là List<T>. Những ID không tồn tại sẽ bị bỏ qua; method không tạo placeholder và cũng không tự ném lỗi chỉ vì thiếu một ID.

Ví dụ database chỉ có customer 10 và 30, lời gọi với 10, 20, 30 trả về hai entity tương ứng với 10 và 30.

**Không có bảo đảm kết quả giữ thứ tự của Iterable đầu vào.** Không viết code giả định phần tử đầu tiên trong kết quả luôn ứng với ID đầu tiên đã truyền. Nếu cần đúng thứ tự đầu vào, phải tự sắp xếp lại sau khi truy vấn hoặc dùng một truy vấn có ORDER BY phù hợp.

```java
List<Long> requestedIds = List.of(30L, 10L, 20L);

List<Customer> found =
        customerRepository.findAllById(requestedIds);

Map<Long, Customer> byId = found.stream()
        .collect(Collectors.toMap(Customer::getId, Function.identity()));

List<Customer> inRequestedOrder = requestedIds.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();
```

Ví dụ trên giữ thứ tự của danh sách đầu vào và bỏ qua ID không tồn tại. Nếu đầu vào có ID lặp lại, kết quả sắp xếp lại cũng sẽ lặp entity tương ứng theo từng lần xuất hiện trong danh sách yêu cầu. Nếu nghiệp vụ không cần lặp, hãy chuẩn hóa input thành tập ID duy nhất trước khi truy vấn.

## 4. findAllById không phải truy vấn phân trang

findAllById chỉ nhận tập ID; nó không nhận Pageable hoặc Sort. Khi truyền một tập ID lớn, provider thường phải tạo truy vấn với điều kiện theo các ID, chẳng hạn IN (...). Tùy provider và database, có thể phát sinh giới hạn số bind parameter, kích thước SQL hoặc chi phí parse query.

Ví dụ không nên truyền hàng trăm nghìn ID trong một lần:

```java
List<Long> allIds = loadAllIdsFromExternalSource();

List<Customer> customers =
        customerRepository.findAllById(allIds);
```

Cách xử lý là chia input thành các lô nhỏ và xử lý từng lô:

```java
public void processIds(List<Long> ids) {
    int batchSize = 500;

    for (int start = 0; start < ids.size(); start += batchSize) {
        int end = Math.min(start + batchSize, ids.size());

        List<Long> batchIds = ids.subList(start, end);

        List<Customer> batch =
                customerRepository.findAllById(batchIds);

        processBatch(batch);
    }
}
```

500 chỉ là giá trị minh họa. Chọn batch size dựa trên giới hạn bind parameter của database, độ dài SQL, driver và lượng dữ liệu mỗi entity. Một số provider có thể xử lý collection parameter theo cách riêng; hãy quan sát SQL thực tế và kiểm thử trên database đích.

Chia input thành lô giúp giới hạn số ID trong từng query. Nếu processBatch giữ lại tất cả entity vào một collection lớn, tổng bộ nhớ vẫn có thể tăng theo kích thước toàn bộ dữ liệu. Hãy xử lý xong từng lô rồi giải phóng tham chiếu nếu không cần giữ lại.

## 5. findAllById có thể trả thiếu dữ liệu mà không báo lỗi

Theo hợp đồng method, ID không tồn tại được bỏ qua. Vì vậy, nếu nghiệp vụ yêu cầu mọi ID đầu vào đều phải tồn tại, ứng dụng phải tự kiểm tra:

```java
List<Long> requestedIds = List.of(10L, 20L, 30L);

List<Customer> found =
        customerRepository.findAllById(requestedIds);

Set<Long> foundIds = found.stream()
        .map(Customer::getId)
        .collect(Collectors.toSet());

List<Long> missingIds = requestedIds.stream()
        .filter(id -> !foundIds.contains(id))
        .distinct()
        .toList();

if (!missingIds.isEmpty()) {
    throw new IllegalArgumentException(
        "Customers not found: " + missingIds
    );
}
```

Cách này phù hợp khi danh sách ID có kích thước vừa phải. Với input rất lớn, hãy kiểm tra theo từng batch và tổng hợp số lượng/ID thiếu theo yêu cầu nghiệp vụ, tránh giữ cả tập entity lớn trong bộ nhớ chỉ để xác minh.

Nếu ID đầu vào đến từ request người dùng, cũng cần kiểm tra quyền truy cập. Tồn tại trong database không đồng nghĩa người gọi có quyền đọc entity đó.

## 6. Vì sao đọc toàn bộ entity tốn bộ nhớ?

Khi gọi findAll(), ứng dụng có thể phải giữ đồng thời:

1. Danh sách tham chiếu tới tất cả entity.
2. Object graph của từng entity đã được tải.
3. Trạng thái quản lý trong persistence context.
4. Các collection/association được nạp eager hoặc bị truy cập trong quá trình xử lý.
5. Bộ nhớ tạm cho kết quả query, DTO hoặc bước chuyển đổi tiếp theo.

Một entity có vài field đơn giản có thể khá nhỏ, nhưng một danh sách lớn với quan hệ và collection có thể chiếm nhiều bộ nhớ hơn dự kiến. Nếu code gọi getter của quan hệ LAZY cho từng entity, còn có thể phát sinh N+1 query.

@Transactional(readOnly = true) có thể giúp provider/transaction manager tối ưu một số thao tác đọc, nhưng không tự biến findAll() thành streaming và không bảo đảm toàn bộ entity không được giữ trong persistence context.

Không giải quyết vấn đề bộ nhớ chỉ bằng cách tăng heap. Hãy giảm số bản ghi đọc mỗi lần, chọn projection và kiểm soát vòng đời persistence context.

## 7. Dùng Pageable khi cần phân trang

JpaRepository hỗ trợ findAll(Pageable):

```java
Pageable pageable = PageRequest.of(
    0,
    100,
    Sort.by(Sort.Direction.ASC, "id")
);

Page<Customer> page =
        customerRepository.findAll(pageable);
```

PageRequest.of(pageNumber, pageSize, sort) sử dụng page number bắt đầu từ 0. Ví dụ trên lấy trang đầu tiên với tối đa 100 entity, sắp xếp theo id tăng dần.

Các thông tin hữu ích trong Page:

- getContent(): danh sách entity của trang hiện tại.
- getNumber(): số trang hiện tại.
- getSize(): kích thước trang yêu cầu.
- getNumberOfElements(): số phần tử thực tế trong trang.
- getTotalElements(): tổng số bản ghi phù hợp.
- getTotalPages(): tổng số trang.
- hasNext(): còn trang tiếp theo hay không.

Ví dụ API có thể trả DTO:

```java
Page<CustomerResponse> response = customerRepository
        .findAll(pageable)
        .map(customer -> new CustomerResponse(
            customer.getId(),
            customer.getName()
        ));
```

map() chuyển nội dung trang sang DTO và giữ metadata phân trang. Không nên trả entity trực tiếp nếu API chỉ cần vài trường, vì serialization có thể truy cập quan hệ lazy, gây N+1 hoặc lỗi ngoài transaction.

Page thường cần thêm count query để tính tổng số phần tử. Với bảng lớn và bộ lọc phức tạp, count query có thể tốn kém đáng kể.

## 8. Dùng Slice khi không cần tổng số bản ghi

Nếu giao diện chỉ cần biết có trang tiếp theo hay không, dùng Slice:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Slice<Customer> findByActiveTrue(Pageable pageable);
}
```

Service:

```java
Slice<Customer> slice = customerRepository.findByActiveTrue(
    PageRequest.of(
        0,
        100,
        Sort.by(Sort.Direction.ASC, "id")
    )
);

List<Customer> content = slice.getContent();
boolean hasNext = slice.hasNext();
```

Slice thường lấy thêm một phần tử để xác định còn dữ liệu tiếp theo, tránh count toàn bộ tập kết quả như Page. Đây là lựa chọn hữu ích cho nút "Tải thêm" hoặc cuộn danh sách.

Page phù hợp khi giao diện cần tổng số bản ghi và số trang. Slice phù hợp khi chỉ cần nội dung hiện tại và tín hiệu tiếp tục. Cả hai đều giới hạn số entity mỗi lần đọc.

## 9. Offset pagination có giới hạn ở trang sâu

PageRequest dùng offset pagination. Trang đầu có offset nhỏ; khi người dùng chuyển đến trang rất sâu, database có thể phải bỏ qua một số lượng lớn hàng trước khi trả kết quả.

Ví dụ:

```java
Pageable deepPage = PageRequest.of(
    10000,
    100,
    Sort.by(Sort.Direction.ASC, "id")
);
```

Offset của trang này là 1.000.000 hàng. Dù database có index, việc bỏ qua lượng hàng lớn vẫn có thể tốn chi phí. Khi dữ liệu liên tục được thêm/xóa, offset pagination còn có thể khiến bản ghi bị lặp hoặc bị bỏ qua giữa các lần gọi trang.

Với danh sách lớn, hãy cân nhắc keyset/seek pagination: thay vì yêu cầu "bỏ qua một triệu dòng", yêu cầu "lấy các dòng có khóa lớn hơn khóa cuối cùng đã đọc". Cần có thứ tự ổn định và index hỗ trợ.

## 10. Keyset pagination theo khóa ổn định

Ví dụ bảng Customer có id tăng dần. Có thể lấy từng lô tiếp theo:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findTop500ByIdGreaterThanOrderByIdAsc(Long lastId);
}
```

Luồng xử lý:

```java
@Transactional(readOnly = true)
public void processAllCustomers() {
    Long lastId = 0L;

    while (true) {
        List<Customer> batch =
                repository.findTop500ByIdGreaterThanOrderByIdAsc(lastId);

        if (batch.isEmpty()) {
            break;
        }

        processBatch(batch);

        lastId = batch.get(batch.size() - 1).getId();
    }
}
```

Mỗi truy vấn bắt đầu sau ID cuối của batch trước. Database có thể tận dụng index trên primary key và không phải bỏ qua offset ngày càng lớn.

Ví dụ giả định ID dương và dữ liệu được sắp xếp theo ID tăng dần. Với UUID ngẫu nhiên hoặc tiêu chí sắp xếp không duy nhất, cần chọn cursor khác. Nếu sắp xếp theo createdAt, hãy thêm id làm tie-breaker:

```sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
ORDER BY created_at ASC, id ASC
```

Keyset pagination không tự bảo đảm snapshot nhất quán cho toàn bộ job nếu dữ liệu liên tục thay đổi. Hãy xác định phạm vi dữ liệu, ví dụ chốt mốc thời gian hoặc ID tối đa lúc bắt đầu, nếu nghiệp vụ cần xử lý một tập ổn định. Spring Data có Scroll API với Window và ScrollPosition ở các phiên bản phù hợp; kiểm tra hỗ trợ của phiên bản Spring Data JPA đang dùng và giới hạn của loại query.

## 11. Projection giúp giảm dữ liệu đọc

Nếu màn hình chỉ cần ID và tên, không cần load toàn bộ entity cùng association. Dùng interface projection:

```java
public interface CustomerSummary {
    Long getId();
    String getName();
}
```

Repository:

```java
List<CustomerSummary> findByActiveTrueOrderByIdAsc();
```

Với tập lớn, kết hợp Pageable:

```java
Page<CustomerSummary> findByActiveTrue(Pageable pageable);
```

Hoặc dùng DTO projection:

```java
public record CustomerSummaryDto(Long id, String name) {
}
```

JPQL constructor expression:

```java
@Query("""
    select new com.example.customer.CustomerSummaryDto(
        c.id,
        c.name
    )
    from Customer c
    where c.active = true
    order by c.id
    """)
List<CustomerSummaryDto> findActiveSummaries();
```

Projection chỉ chọn các cột cần thiết, giảm dữ liệu truyền qua JDBC và tránh tạo entity managed cho các kết quả DTO. Tuy nhiên, List projection không phân trang vẫn có thể trả về rất nhiều dòng. Kết hợp projection với Page, Slice hoặc batch cursor khi tập dữ liệu lớn.

## 12. Streaming kết quả

Spring Data JPA hỗ trợ repository method trả Stream<T> trong các trường hợp phù hợp:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where c.active = true
        order by c.id
        """)
    Stream<Customer> streamActiveCustomers();
}
```

Sử dụng trong transaction và đóng stream:

```java
@Transactional(readOnly = true)
public void processActiveCustomers() {
    try (Stream<Customer> customers =
             repository.streamActiveCustomers()) {

        customers.forEach(this::processCustomer);
    }
}
```

Stream có thể giữ tài nguyên JDBC/result set mở. Vì vậy:

- Phải tiêu thụ stream trong transaction phù hợp.
- Phải đóng stream, tốt nhất bằng try-with-resources.
- Không trả stream ra khỏi service rồi sử dụng sau khi transaction đã kết thúc.
- Kiểm tra fetch size của provider và JDBC driver nếu muốn đọc theo cursor.
- Không giả định Stream<T> luôn bảo đảm dữ liệu được tải từng phần hoặc không chiếm bộ nhớ.

JPA provider có thể vẫn giữ các entity đã đọc trong persistence context. Với stream rất lớn, bộ nhớ có thể tăng dần dù kết quả được tiêu thụ từng phần. Projection/DTO hoặc xử lý theo window/batch có thể phù hợp hơn. Nếu cần clear persistence context định kỳ, phải thiết kế để không detach các entity còn cần dùng và kiểm tra cách provider thực hiện streaming.

## 13. findAllById và streaming có vai trò khác nhau

findAllById phù hợp khi đã có một tập ID cần tra cứu. Streaming phù hợp khi cần duyệt một tập kết quả lớn theo query. Không có một method findAllByIdStream chuẩn trong JpaRepository để thay thế mọi trường hợp.

Nếu nguồn ID rất lớn, chia ID thành lô và gọi findAllById cho từng lô. Nếu mục tiêu là duyệt toàn bộ bảng theo thứ tự, keyset pagination hoặc streaming query thường tự nhiên hơn việc đọc tất cả ID trước rồi gọi findAllById.

Không nên làm hai lượt lớn: đầu tiên findAll ID, sau đó findAllById toàn bộ ID. Cách đó có thể tốn bộ nhớ và query hơn so với một query có filter/projection phù hợp.

## 14. Lazy loading và N+1 khi đọc danh sách

findAll() có thể chỉ phát một query cho bảng chính. Nhưng nếu code duyệt từng entity rồi truy cập association LAZY, provider có thể phát thêm một query cho mỗi entity.

Ví dụ:

```java
List<PurchaseOrder> orders = orderRepository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu có N đơn và mỗi lần truy cập customer tạo thêm query, tổng số query có thể gần N+1. Hãy xác định dữ liệu cần hiển thị và dùng fetch join, EntityGraph hoặc DTO projection cho đúng use case.

Không fetch join collection OneToMany một cách tùy tiện khi phân trang. Join collection có thể nhân bản hàng cha và khiến pagination/count không chính xác hoặc provider phải xử lý trong bộ nhớ. Với danh sách lớn, DTO projection hoặc hai bước phân trang ID rồi tải chi tiết có thể an toàn hơn.

## 15. Transaction và persistence context khi đọc theo lô

Những CRUD read methods kế thừa từ SimpleJpaRepository, chẳng hạn findAll() và findById(), được cấu hình transaction read-only. Các query methods do ứng dụng tự khai báo không tự động có transaction configuration theo mặc định; hãy đặt @Transactional ở service hoặc repository khi cần. Nếu service đã mở @Transactional bao ngoài, repository tham gia transaction hiện tại theo propagation mặc định.

Với xử lý theo lô, cần quyết định transaction bao quanh toàn bộ job hay từng batch:

- Một transaction lớn giữ snapshot/lock và persistence context lâu hơn, có thể tăng bộ nhớ và thời gian giữ connection.
- Transaction từng batch giới hạn tài nguyên và cho phép commit tiến độ theo lô, nhưng dữ liệu có thể thay đổi giữa các batch và job có thể hoàn thành một phần nếu lỗi.
- Nếu nghiệp vụ cần một kết quả nhất quán tại một thời điểm, cần thiết kế isolation/snapshot hoặc mốc dữ liệu phù hợp.

Với thao tác chỉ đọc, @Transactional(readOnly = true) là tín hiệu tối ưu cho transaction manager/provider. Nó không bảo đảm mọi ghi bị chặn, không tự bật streaming và không thay thế việc giới hạn số dòng.

Nếu xử lý entity managed rồi cập nhật từng entity, persistence context có thể tăng theo batch. Có thể flush/clear theo lô khi ghi, nhưng clear detach tất cả entity đang được quản lý. Nếu chỉ đọc và không cần sửa, DTO projection thường giúp giảm chi phí hơn.

## 16. Chọn API theo tình huống

| Nhu cầu | Cách dùng phù hợp | Lưu ý |
|---|---|---|
| Bảng nhỏ, cần toàn bộ | findAll() | Không có giới hạn số dòng |
| Toàn bộ danh sách với thứ tự | findAll(Sort) | Vẫn tải toàn bộ |
| Tra cứu tập ID vừa phải | findAllById(ids) | ID thiếu bị bỏ qua, thứ tự không bảo đảm |
| Danh sách có tổng số trang | findAll(Pageable) trả Page | Có thể cần count query |
| Tải thêm, không cần tổng | Slice<T> | Tránh count toàn bộ |
| Dữ liệu lớn, trang sâu | Keyset/seek pagination | Cần cursor và thứ tự ổn định |
| Duyệt tuần tự theo cursor DB | Stream<T> | Cần transaction, đóng stream, kiểm tra driver/provider |
| Chỉ cần vài cột | Projection/DTO | Kết hợp phân trang/batch |
| Nhiều ID từ nguồn ngoài | findAllById theo từng batch | Chọn batch size theo giới hạn database |

## 17. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| API chậm khi bảng tăng | findAll() tải toàn bộ bản ghi | Dùng Pageable, Slice hoặc keyset |
| OutOfMemoryError | Giữ quá nhiều entity và persistence context | Giới hạn batch, projection, transaction phù hợp |
| Kết quả findAllById thiếu phần tử | Một số ID không tồn tại | So sánh tập ID đầu vào với ID trả về |
| Thứ tự findAllById sai | Method không bảo đảm thứ tự input | Tự sắp xếp theo input hoặc truy vấn có ORDER BY |
| SQL quá lớn hoặc vượt giới hạn bind parameter | Tập ID truyền vào quá lớn | Chia ID thành batch nhỏ |
| Trang sâu ngày càng chậm | Offset lớn | Dùng keyset pagination và index |
| Page query chậm dù nội dung ít | Count query tốn kém | Dùng Slice khi không cần tổng số |
| Stream gây giữ connection lâu | Stream chưa đóng hoặc xử lý quá lâu | try-with-resources và transaction ngắn phù hợp |
| Stream vẫn tốn bộ nhớ | Entity tích lũy trong persistence context hoặc driver không stream thật | Dùng projection/window, kiểm tra fetch size và provider |
| N+1 khi đọc danh sách | Truy cập association lazy từng entity | EntityGraph, fetch join phù hợp hoặc DTO |
| Pagination sai với collection fetch join | Join nhân bản hàng cha | Phân trang ID trước hoặc dùng projection |
| Dữ liệu thay đổi giữa các batch | Nhiều transaction hoặc isolation không tạo snapshot chung | Chốt phạm vi dữ liệu hoặc chọn isolation phù hợp |

## 18. Bài tập thực hành

1. Tạo CustomerRepository và gọi findAll() với bảng nhỏ; quan sát SQL và kiểu kết quả.
2. Gọi findAll(Sort.by("id")) và xác nhận thứ tự ổn định.
3. Gọi findAllById() với một ID tồn tại và một ID không tồn tại; xác nhận ID thiếu bị bỏ qua.
4. Truyền ID theo thứ tự khác database và kiểm tra kết quả không có cam kết giữ thứ tự input.
5. Viết đoạn sắp xếp lại kết quả theo danh sách ID đầu vào.
6. Chia 5.000 ID thành các batch 500 và quan sát kích thước SQL/query.
7. Tạo API Page và Slice; so sánh số query và count query.
8. Tạo keyset query theo id và xử lý lần lượt từng batch.
9. Dùng interface projection để chỉ đọc id/name.
10. Viết repository Stream<T>, dùng try-with-resources trong transaction và quan sát connection lifetime.
11. Đo bộ nhớ khi dùng findAll() so với projection + pagination.
12. Bật SQL log để phát hiện N+1 khi truy cập customer của từng order.

**Nguyên tắc xuyên suốt:** findAll đọc toàn bộ kết quả và không giới hạn bộ nhớ; findAllById tra cứu một tập ID, bỏ qua ID không tồn tại và không bảo đảm thứ tự đầu vào. Khi dữ liệu lớn, hãy giới hạn mỗi lần đọc bằng Page/Slice hoặc keyset, chọn projection để giảm dữ liệu, và chỉ dùng Stream khi transaction, tài nguyên JDBC cùng persistence context được quản lý đúng.
