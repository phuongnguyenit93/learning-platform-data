# Stream, callback, auditing và thời điểm truy cập tài nguyên

## 1. Vì sao thời điểm thực thi quan trọng?

Một lời gọi repository có thể trả về trước khi ứng dụng đọc hết dữ liệu, trước khi provider gửi toàn bộ thay đổi xuống kho, hoặc trước khi giao dịch commit. Vì vậy, việc đặt `@Transactional` gần một lời gọi `save()` hay một phương thức trả về `Stream<T>` chưa đủ để xác định tài nguyên còn sử dụng được ở đâu và dữ liệu đã bền vững lúc nào.

Trong chương Ranh giới giao dịch của Spring Data Commons, cần nối bốn câu hỏi:

1. Đoạn mã nào thực sự kích hoạt đọc hoặc ghi dữ liệu?
2. Tài nguyên như cursor, connection, session hoặc persistence context do ai quản lý?
3. Callback và auditing chạy tại giai đoạn nào của đường truy cập đó?
4. Giao dịch đã kết thúc chưa khi ứng dụng tiếp tục xử lý kết quả hoặc phát sinh tác dụng phụ?

Spring Data Commons cung cấp các abstraction dùng chung như repository, entity callback và auditing metadata. Việc mở cursor, flush, hỗ trợ transaction và kích hoạt từng callback do module cùng datastore cụ thể quyết định. Transaction management thuộc Spring Framework và cơ chế tích hợp của từng module; không thể suy ra một hành vi giao dịch thống nhất chỉ từ việc repository kế thừa cùng một interface.

## 2. Phân biệt các mốc thường bị nhầm lẫn

| Mốc | Ý nghĩa | Chưa đủ để kết luận |
| --- | --- | --- |
| Gọi phương thức repository | Bắt đầu một thao tác theo hợp đồng của repository | Toàn bộ dữ liệu đã được tải vào bộ nhớ |
| Nhận `Stream<T>` | Có đối tượng để duyệt kết quả | Mọi phần tử đã được đọc và tài nguyên đã được đóng |
| Callback trước chuyển đổi hoặc trước lưu | Đang ở một bước của quy trình mapping/ghi được module hỗ trợ | Có thể thực hiện mọi truy vấn phụ hoặc đã có commit |
| `save()` trả về | Lời gọi lưu đã trả kết quả theo semantics của module | Giao dịch ngoài cùng đã commit |
| Flush trong JPA | Đồng bộ các thay đổi đang chờ xuống cơ sở dữ liệu | Giao dịch đã commit và không thể rollback |
| Commit thành công | Transaction manager hoàn tất commit cho các tài nguyên tham gia | Email, HTTP hoặc kho dữ liệu khác cũng thành công |
| Đóng stream | Kết thúc sử dụng và giải phóng tài nguyên stream theo implementation | Transaction chắc chắn đã commit |

Flush là khái niệm nổi bật trong JPA. Không nên áp nguyên mô hình persistence context và flush của JPA cho MongoDB, JDBC, Redis hoặc các module reactive.

Cũng cần phân biệt **vòng đời đối tượng Java** với **vòng đời tài nguyên lưu trữ**. Entity hoặc đối tượng stream vẫn còn được tham chiếu không có nghĩa session, cursor hoặc connection phía dưới còn dùng được.

## 3. `Stream<T>`: xử lý trì hoãn có thể kéo dài nhu cầu tài nguyên

### 3.1. Tạo pipeline chưa phải duyệt hết dữ liệu

Với Java Stream, các thao tác trung gian như `filter()` và `map()` xây dựng pipeline. Việc duyệt diễn ra khi có terminal operation như `forEach()`, `count()` hoặc `collect()`; mức độ duyệt còn phụ thuộc thao tác và khả năng tối ưu của nguồn stream.

Khi nguồn dữ liệu đến từ repository, tùy module, stream có thể gắn với cursor hoặc các tài nguyên của cơ chế truy cập dữ liệu. Một phần công việc có thể được thực hiện ngay khi gọi phương thức, phần còn lại diễn ra lúc đọc phần tử. Vì vậy, không được mặc định rằng truy vấn chỉ bắt đầu tại terminal operation hoặc luôn hoàn tất trước khi repository trả về.

```text
Mở phạm vi tài nguyên/giao dịch nếu cần
    -> gọi repository
    -> nhận Stream
    -> gắn filter/map
    -> terminal operation đọc các phần tử
    -> đóng Stream
    -> hoàn tất giao dịch ở ranh giới sở hữu nó
```

Một số module không hỗ trợ repository method trả về `Stream<T>`, hoặc hỗ trợ nhưng có yêu cầu khác về transaction và cursor. Khả năng này phải được xác nhận cho module đang dùng; khai báo chữ ký Java không tự tạo ra hỗ trợ từ datastore.

### 3.2. Terminal operation không tự đóng stream

Không nên kỳ vọng `count()`, `findFirst()` hoặc `forEach()` tự gọi `close()` cho stream tài nguyên. Đặc biệt, thao tác dừng sớm như `findFirst()` có thể chỉ đọc một phần kết quả nhưng tài nguyên vẫn cần được giải phóng.

Dùng `try-with-resources` để thể hiện rõ chủ sở hữu:

```java
try (Stream<Customer> customers = repository.streamAllByActiveTrue()) {
    return customers
        .map(Customer::getEmail)
        .filter(Objects::nonNull)
        .count();
}
```

Đoạn mã minh họa việc đóng tài nguyên, chưa tự xác lập transaction. Nếu module yêu cầu giao dịch khi duyệt stream, cần đặt toàn bộ khối này trong ranh giới giao dịch phù hợp.

Stream thường chỉ được tiêu thụ một lần. Muốn thực hiện một truy vấn khác sau đó thì gọi lại repository hoặc thiết kế truy vấn khác; không tái sử dụng stream đã đóng.

### 3.3. Ranh giới giao dịch phải bao quanh việc tiêu thụ

Ví dụ sau dành cho một ứng dụng **Spring Data JPA** có repository streaming được hỗ trợ. Ví dụ lược bỏ import và mapping của `Customer`:

```java
interface CustomerRepository extends Repository<Customer, Long> {
    Stream<Customer> streamAllByActiveTrue();
}
```

```java
@Service
class CustomerScanService {

    private final CustomerRepository customers;

    CustomerScanService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public long countActiveCustomersWithEmail() {
        try (Stream<Customer> stream = customers.streamAllByActiveTrue()) {
            return stream
                .map(Customer::getEmail)
                .filter(Objects::nonNull)
                .count();
        }
    }
}
```

Giả định phương thức được gọi từ một bean khác qua transaction proxy, transaction manager đúng đã được chọn và repository tham gia cùng transaction đó. Với cấu hình mặc định và khi không tham gia giao dịch ngoài, trình tự thường là mở giao dịch, gọi thân phương thức, duyệt và đóng stream, rồi hoàn tất giao dịch.

Nếu đã có giao dịch ngoài và phương thức tham gia giao dịch đó, commit thực sự có thể xảy ra sau khi phương thức này trả về. Nếu gọi nội bộ trong cùng đối tượng khi dùng cơ chế proxy thông thường, annotation có thể không được áp dụng như mong đợi.

Ví dụ đếm ở trên nhằm minh họa vòng đời. Với yêu cầu chỉ cần đếm dữ liệu theo điều kiện có thể biểu diễn bằng truy vấn, một count query tại datastore thường phù hợp hơn việc tải từng entity về Java.

`readOnly = true` thể hiện mục đích và có thể được transaction manager/provider sử dụng để tối ưu. Nó không phải cơ chế bất biến đối tượng Java hay bảo đảm thống nhất rằng mọi kho dữ liệu đều cấm ghi.

### 3.4. Bẫy trả stream ra khỏi service

```java
@Transactional(readOnly = true)
public Stream<Customer> openActiveCustomers() {
    return customers.streamAllByActiveTrue();
}
```

Trong quản lý transaction imperative theo proxy, giao dịch do phương thức này mở thường được hoàn tất khi phương thức trả về. Caller tiêu thụ stream sau đó có thể gặp tài nguyên đã đóng hoặc lỗi yêu cầu transaction đang hoạt động. Rủi ro còn tồn tại dù caller có đóng stream sau khi dùng.

Trường hợp có transaction ngoài bao quanh cả lời gọi lẫn việc duyệt có thể khác. Vì vậy, vấn đề là hợp đồng sở hữu không rõ: ai giữ transaction và ai đóng stream?

Các cách thiết kế thường dễ kiểm soát hơn:

- Tiêu thụ stream trong service sở hữu giao dịch và trả về kết quả đã tính.
- Trả DTO hoặc một trang dữ liệu đã materialize, đồng thời cân nhắc kích thước bộ nhớ và truy vấn phát sinh.
- Với API cố ý trả stream, mô tả và thực thi rõ trách nhiệm transaction cùng trách nhiệm đóng ở caller.

Đối với `Page<T>` hoặc `Slice<T>`, phần kết quả truy vấn trang thường đã được lấy khi trả về, nhưng thuộc tính lazy của entity bên trong vẫn có thể cần persistence context. Chuyển sang DTO trong ranh giới thích hợp giúp tránh việc serializer vô tình truy cập lazy data sau đó; cách này vẫn cần chọn đúng các trường và truy vấn phù hợp.

## 4. Không chuyển tài nguyên transaction sang thread khác một cách ngầm định

Một stream repository không nên bị đổi sang `.parallel()` chỉ để tăng tốc mà chưa xem xét khả năng thread safety và vòng đời tài nguyên. Connection, cursor hoặc persistence context không mặc nhiên dùng an toàn giữa nhiều thread. Trong mô hình imperative phổ biến, transaction context được gắn với thread thực thi và không tự lan sang executor hoặc `CompletableFuture` mới.

```java
// Mẫu dễ gây lỗi nếu các tác vụ cần session/transaction của caller.
try (Stream<Customer> stream = customers.streamAllByActiveTrue()) {
    stream.forEach(customer -> executor.submit(() -> process(customer)));
}
```

Khi khối `try` kết thúc, stream có thể đã đóng trong khi các tác vụ vẫn chưa chạy xong. Nếu `process()` truy cập quan hệ lazy hoặc dùng entity gắn với persistence context ban đầu, tài nguyên cần thiết có thể không còn hợp lệ.

Nếu cần xử lý song song, có thể đọc ID hoặc DTO độc lập theo lô, rồi để mỗi tác vụ mở phạm vi truy cập riêng qua một service phù hợp. Cần giới hạn số tác vụ theo sức chứa connection pool và datastore; việc tạo nhiều thread không làm tăng vô hạn khả năng phục vụ của kho dữ liệu.

Đọc theo stream cũng không tự bảo đảm bộ nhớ không tăng. Trong JPA, persistence context có thể giữ các entity đã đọc. Khi xử lý dữ liệu lớn, cần xem fetch size, quản lý persistence context, phân lô hoặc truy vấn theo mốc khóa tùy provider và yêu cầu. Không áp dụng việc clear/detach tùy tiện nếu còn thay đổi đang chờ hoặc đối tượng vẫn cần được quản lý.

## 5. Entity callback: mốc trong quy trình lưu, không phải mốc commit

### 5.1. Callback phụ thuộc module và đường thao tác

Spring Data có cơ chế entity callback để tham gia các giai đoạn như chuyển đổi, lưu hoặc đọc ở những module có tích hợp. Tên interface, chữ ký và thời điểm được hỗ trợ phải xét theo module cụ thể.

Ví dụ dưới đây dành riêng cho **Spring Data MongoDB**, sử dụng `BeforeConvertCallback` trong gói `org.springframework.data.mongodb.core.mapping.event`:

```java
@Component
class CustomerCodeNormalizer implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(Customer customer, String collection) {
        if (customer.getCode() != null) {
            customer.setCode(customer.getCode().trim());
        }
        return customer;
    }
}
```

Ví dụ giả định `Customer` là đối tượng mutable có getter/setter phù hợp. Callback chuẩn hóa mã trước khi chuyển đối tượng sang dạng lưu trữ. Nó không tạo unique index, không xác nhận quyền của người dùng và không chứng minh transaction đã commit.

Với đối tượng immutable, callback có thể cần trả về một đối tượng thay thế theo hợp đồng của interface. Không nên chỉ tính một bản sao mới rồi bỏ qua giá trị trả về mà đường ghi cần sử dụng.

Spring Data JPA có đường tích hợp lifecycle của JPA và auditing listener; không nên lấy interface callback của MongoDB gắn vào entity JPA rồi kỳ vọng nó được gọi tương tự.

### 5.2. `BeforeSave` và `AfterSave` cần được hiểu theo phạm vi của thao tác

Một callback sau lưu, nếu module hỗ trợ, thể hiện một mốc sau bước lưu trong đường xử lý đó. Nếu vẫn đang nằm trong transaction ngoài, một thao tác sau callback vẫn có thể thất bại và làm giao dịch rollback.

```text
Bắt đầu giao dịch ngoài
    -> repository thực hiện đường ghi
    -> callback sau lưu chạy
    -> xử lý nghiệp vụ tiếp theo thất bại
    -> giao dịch rollback theo quy tắc áp dụng
```

Vì vậy, gửi email hoặc gọi HTTP từ callback sau lưu có thể khiến hệ thống bên ngoài nhận thông tin về một thay đổi cuối cùng không được commit. Những tác dụng phụ đó thường không tham gia transaction của datastore.

Các lệnh cập nhật trực tiếp, bulk update hoặc thao tác thấp hơn tầng repository có thể không đi qua cùng chuỗi callback và lifecycle. Ví dụ, bulk update trong JPA không hoạt động như việc tải từng entity rồi sửa từng đối tượng. Không nên đặt một bất biến quan trọng vào callback rồi giả định mọi đường ghi đều tuân thủ mà không kiểm tra.

### 5.3. Tránh làm callback phụ thuộc quá nhiều vào truy cập tài nguyên

Một callback gọi thêm repository có thể gây:

- Nhiều truy vấn phụ khi đang duyệt hoặc ghi hàng loạt.
- Vòng lặp nếu callback lưu lại chính kiểu entity đang xử lý.
- Flush hoặc truy vấn phát sinh tại thời điểm khó dự đoán, tùy provider.
- Tranh chấp connection, khóa hoặc transaction khi mở thêm công việc.
- Khác biệt hành vi giữa thao tác có transaction và thao tác không có transaction.

Callback phù hợp với thay đổi nhỏ, có phạm vi rõ trên đối tượng, chẳng hạn chuẩn hóa trường hoặc gắn metadata đã có sẵn. Nếu cần truy vấn nghiệp vụ phức tạp, nên điều phối ở service để ranh giới và thứ tự tài nguyên được thể hiện rõ.

Khi nhiều callback cùng sửa một trường, cần xác định thứ tự bằng cơ chế ordering được module hỗ trợ. Không nên dựa vào thứ tự khởi tạo bean ngẫu nhiên. Auditing cũng có thể tham gia đường callback hoặc lifecycle, vì vậy việc tự sửa cùng các field audit phải có chính sách nhất quán.

## 6. Auditing ghi nhận tại lifecycle, không phải bằng chứng commit

### 6.1. Ý nghĩa của metadata

Các annotation thường gặp của Spring Data auditing gồm:

```java
class Customer {

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // Các field nghiệp vụ và phần mapping phụ thuộc datastore.
}
```

Đây là minh họa metadata, không phải entity chạy độc lập. Cần bật auditing và cấu hình mapping/listener/callback phù hợp với module. Chỉ thêm annotation chưa bảo đảm các giá trị được tự động điền.

| Metadata | Câu hỏi nó hướng tới | Điều không nên suy ra |
| --- | --- | --- |
| `@CreatedDate` | Đối tượng được ghi nhận là tạo mới vào lúc nào? | Đây là thời điểm commit chính xác của cơ sở dữ liệu |
| `@LastModifiedDate` | Lần ghi nhận sửa đổi trong lifecycle là lúc nào? | Mọi thay đổi trực tiếp ngoài đường auditing đều được theo dõi |
| `@CreatedBy` | Chủ thể tạo được auditing xác định là ai? | Chủ thể đó đã được kiểm tra đầy đủ quyền nghiệp vụ |
| `@LastModifiedBy` | Chủ thể sửa được auditing xác định là ai? | Có một lịch sử bất biến của mọi phiên bản dữ liệu |

Việc xác định entity mới ảnh hưởng đến nhánh xử lý tạo/sửa và các field được điền. Cấu hình auditing cũng có thể ảnh hưởng việc điền metadata sửa đổi ngay khi tạo. Entity có ID gán trước, trường version hoặc cơ chế `Persistable.isNew()` cần được hiểu theo module và cấu hình thực tế.

Auditing hiện tại trên entity thường chỉ giữ một số metadata gần nhất. Nó không tự thay thế event log, bảng lịch sử hoặc hệ thống audit trail đầy đủ.

### 6.2. Lấy chủ thể thực hiện từ ngữ cảnh phù hợp

Một `AuditorAware<String>` có thể cung cấp định danh người thực hiện. Ví dụ sau dùng abstraction của ứng dụng để tránh ràng buộc bài học vào một thư viện xác thực cụ thể:

```java
interface CurrentActor {
    Optional<String> id();
}
```

```java
@Bean
AuditorAware<String> auditorAware(CurrentActor currentActor) {
    return currentActor::id;
}
```

Kiểu `String` cần tương thích với field `@CreatedBy` và `@LastModifiedBy`. Khi không có người dùng đăng nhập, ứng dụng cần quyết định có chủ thể kỹ thuật cho batch job hay cho phép không có auditor. Không nên tự gán một tài khoản người dùng bất kỳ để lấp chỗ trống.

Dùng định danh ổn định đã có trong ngữ cảnh thường dễ kiểm soát hơn việc mỗi lần auditing lại tải toàn bộ entity người dùng từ repository. Truy vấn thêm ngay trong auditing có thể gây chi phí, phụ thuộc vòng đời hoặc tương tác khó lường với đường lưu đang diễn ra.

`AuditorAware` cung cấp thông tin chủ thể, không thay thế authorization. Service vẫn phải kiểm tra quyền thực hiện nghiệp vụ trước khi ghi dữ liệu.

### 6.3. Thời gian audit và kết quả giao dịch có thể khác nhau

Một giao dịch có thể diễn ra như sau:

```text
T1: logic ứng dụng sửa đối tượng
T2: lifecycle/auditing gắn thời gian hoặc người sửa
T3: provider thực hiện ghi/flush theo cơ chế của nó
T4: thao tác khác thất bại
T5: rollback nếu quy tắc giao dịch yêu cầu
```

Thời điểm và thứ tự chi tiết giữa callback với ghi phụ thuộc module; sơ đồ chỉ nhấn mạnh rằng auditing có thể xảy ra trước kết quả cuối cùng của transaction.

Sau rollback, đối tượng Java mà ứng dụng còn giữ có thể vẫn chứa timestamp hoặc auditor đã được gán. Rollback dữ liệu trong kho không tự phục hồi mọi field trong bộ nhớ về giá trị trước đó. Không dùng việc một field audit đã có giá trị để kết luận lưu thành công.

Trong JPA, SQL có thể được trì hoãn đến flush. `save()` trả về chưa đồng nghĩa callback cập nhật, kiểm tra ràng buộc tại cơ sở dữ liệu và commit đều đã hoàn tất. Nếu provider hỗ trợ flush chủ động, flush giúp bộc lộ một số lỗi ghi sớm hơn nhưng vẫn không thay thế commit.

## 7. Domain event và sự kiện sau commit có phạm vi khác callback

Callback entity, lifecycle event, domain event của aggregate và transaction event listener là các cơ chế khác nhau. Chúng có thể xuất hiện trong cùng một luồng xử lý nhưng không có cùng cam kết thời điểm.

Việc một aggregate công bố sự kiện qua cơ chế `@DomainEvents` không tự làm listener trở thành listener sau commit. Nếu yêu cầu chỉ xử lý sau commit thành công, cần dùng cơ chế phù hợp với transaction đang quản lý.

Ví dụ trong ứng dụng imperative dùng transaction manager thích hợp:

```java
@Component
class CustomerRegisteredListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(CustomerRegistered event) {
        // Dùng dữ liệu đã chụp trong event để xử lý sau commit.
    }
}
```

Ví dụ giả định sự kiện được publish trong transaction Spring mà listener có thể tham gia theo cơ chế được hỗ trợ. Với cấu hình mặc định, khi không có transaction phù hợp, listener loại này không được gọi; hành vi có thể thay đổi nếu bật `fallbackExecution`.

Event nên mang ID và các giá trị cần thiết đã được chụp, tránh mang entity rồi kỳ vọng truy cập lazy relationship sau commit. Tài nguyên giao dịch ở giai đoạn này không nên được dùng như một transaction ghi còn mở. Nếu cần ghi dữ liệu mới sau commit, phải xác định ranh giới transaction mới rõ ràng ở một service khác; ví dụ `REQUIRES_NEW` khi phù hợp với transaction manager và yêu cầu thực tế.

`AFTER_COMMIT` cũng không tự bảo đảm giao sự kiện bền vững. Tiến trình có thể dừng sau commit nhưng trước khi email hoặc message được gửi. Nếu thông báo bắt buộc phải được phát lại và theo dõi, có thể dùng transactional outbox: ghi thay đổi nghiệp vụ cùng bản ghi outbox trong một transaction có khả năng bao phủ cả hai, rồi dùng tiến trình riêng gửi và retry. Consumer vẫn cần xử lý khả năng nhận lặp.

## 8. Reactive: vòng đời gắn với subscription và Reactor context

Không đồng nhất `Stream<T>` của Java với `Flux<T>` hoặc `Mono<T>`. Với repository reactive, công việc thường được mô tả bằng publisher và được thực hiện khi có subscription; ranh giới transaction phải bao quanh pipeline thực sự chạy bằng transaction manager reactive phù hợp.

Các điểm cần chú ý:

- Trả publisher khỏi một phương thức transactional reactive có thể là thiết kế đúng; mô hình kết thúc giao dịch không giống phương thức imperative trả `Stream`.
- Không gọi `subscribe()` thủ công trong service chỉ để kích hoạt một nhánh công việc rồi trả về publisher khác. Nhánh đó có thể tách khỏi vòng đời và ngữ cảnh giao dịch dự kiến.
- Không dùng `block()` như cách mặc định để đưa repository reactive vào callback đồng bộ. Nó có thể phá mô hình thực thi và gây vấn đề trên thread không cho phép blocking.
- Dùng callback reactive và `ReactiveAuditorAware` nếu module hỗ trợ và đường truy cập đang dùng cần chúng. Thông tin chủ thể thường cần đi qua Reactor context hoặc cơ chế tích hợp phù hợp, không chỉ dựa vào thread-local.
- Việc hoàn tất, lỗi hoặc hủy subscription phải được xem xét khi đánh giá rollback và giải phóng tài nguyên. Chi tiết phụ thuộc operator, transaction manager và driver.

Một subscription kết thúc không có nghĩa mọi tác vụ bất đồng bộ đã tự tách khỏi pipeline cũng hoàn tất. Công việc cần nằm trong cùng vòng đời nên được ghép bằng các operator phù hợp để kết quả và lỗi được quan sát.

## 9. Các mẫu lỗi và hướng sửa

| Mẫu dễ sai | Nguyên nhân | Hướng thiết kế |
| --- | --- | --- |
| Service transactional trả stream để controller duyệt | Việc duyệt xảy ra sau ranh giới transaction của service | Tiêu thụ trong service hoặc đặt hợp đồng sở hữu ở caller rõ ràng |
| Dùng `findFirst()` rồi bỏ stream | Dừng sớm không tự đóng tài nguyên | Dùng `try-with-resources` |
| Dùng `.parallel()` trên stream gắn datastore | Tài nguyên và ngữ cảnh không mặc nhiên an toàn giữa thread | Tách dữ liệu độc lập, giới hạn song song và transaction từng tác vụ |
| Gửi email trong callback sau lưu | Lưu xong một bước chưa đồng nghĩa commit | Xử lý sau commit; dùng outbox khi cần khả năng phát lại bền vững |
| Thấy field audit đã được gán và báo lưu thành công | Auditing có thể chạy trước lỗi ghi hoặc rollback | Dựa vào kết quả của ranh giới giao dịch và phản hồi lỗi |
| Bulk update nhưng kỳ vọng đầy đủ callback/auditing từng entity | Đường ghi có thể bỏ qua lifecycle tương ứng | Quản lý metadata rõ trong lệnh hoặc chọn đường ghi phù hợp |
| Listener sau commit truy cập entity lazy | Entity phụ thuộc tài nguyên đã hết phạm vi sử dụng | Chụp payload cần thiết hoặc đọc lại trong transaction riêng |
| Nhiều repository ở các kho khác nhau nhưng chỉ chọn một manager | Manager không tự bao phủ mọi tài nguyên | Xác định từng phạm vi; thiết kế phối hợp hoặc bù trừ khi cần |

## 10. Phân tích một luồng nghiệp vụ hoàn chỉnh

Giả sử ứng dụng cần kích hoạt khách hàng và gửi thông báo:

1. Service được gọi qua transaction proxy phù hợp.
2. Repository đọc khách hàng trong transaction đó.
3. Service kiểm tra quyền và điều kiện nghiệp vụ.
4. Entity được thay đổi; đường lưu/lifecycle cập nhật metadata audit theo cấu hình.
5. Nếu cần giao thông báo bền vững, service ghi bản ghi outbox trong cùng transaction được hỗ trợ.
6. Provider gửi thay đổi xuống datastore theo cơ chế của nó; các lỗi có thể xuất hiện ở thao tác ghi, flush hoặc commit.
7. Chỉ khi commit thành công mới coi thay đổi nghiệp vụ đã hoàn tất trong phạm vi kho tham gia.
8. Tiến trình outbox đọc thông báo, gửi ra ngoài và ghi nhận kết quả bằng phạm vi giao dịch riêng.

Nếu bước 6 thất bại và rollback được áp dụng, thay đổi khách hàng cùng bản ghi outbox phải cùng rollback khi chúng thật sự nằm trong một transaction bao phủ cả hai. Nếu nằm ở hai datastore mà transaction manager không điều phối chung, bảo đảm này không còn tự động đúng.

Để đọc một số lượng lớn khách hàng cho công việc đối soát khác, service có thể dùng stream hoặc phân lô. Không nên giữ một stream và transaction đọc mở suốt thời gian chờ từng email hoặc từng HTTP response nếu không có nhu cầu và giới hạn vận hành rõ ràng.

## 11. Cách xác định ranh giới trong thiết kế

Khi đọc một đoạn mã repository, hãy đánh dấu các mốc thay vì chỉ nhìn annotation:

1. **Điểm vào:** lời gọi có đi qua proxy hoặc transaction operator dự kiến không?
2. **Chủ sở hữu:** ai mở và hoàn tất transaction; ai đóng stream/cursor?
3. **Tiêu thụ:** dữ liệu được đọc trong phương thức, trong serializer, trong thread khác hay khi có subscription?
4. **Đường ghi:** thao tác có đi qua mapping, callback và auditing mà thiết kế đang dựa vào không?
5. **Kết quả cuối:** lỗi có thể xuất hiện khi gọi repository, khi duyệt, khi flush hay khi commit?
6. **Tác dụng phụ:** email, message hoặc HTTP có được phối hợp bằng cơ chế phù hợp hay đang xảy ra trước kết quả giao dịch?

Những kịch bản hữu ích để kiểm chứng thiết kế gồm duyệt hết stream, dừng sớm, lỗi giữa lúc duyệt, rollback sau callback, truy cập dữ liệu lazy ngoài service và thao tác batch không đi qua auditing thông thường. Đối với reactive, bổ sung trường hợp lỗi và hủy subscription.

Đây là hướng dẫn kiểm chứng cho người áp dụng, không phải giả định rằng mọi module sẽ có cùng kết quả. Kết quả mong đợi phải xuất phát từ transaction manager, provider, driver và API cụ thể được lựa chọn.

## 12. Bài tập tự phân tích

Xét phương thức sau trong một service imperative:

```java
@Transactional(readOnly = true)
public Stream<Customer> customersForReport() {
    return customers.streamAllByActiveTrue();
}
```

Controller nhận stream, duyệt nó để xuất báo cáo rồi chuyển từng entity sang executor để bổ sung dữ liệu liên quan. Một callback sau lưu ở tác vụ khác đồng thời gửi email và dùng trường `lastModifiedAt` làm bằng chứng thao tác đã hoàn tất.

Hãy xác định:

- Transaction nào bao quanh việc duyệt báo cáo và ai đóng stream.
- Những tài nguyên nào các tác vụ executor có thể đang truy cập sau khi service trả về.
- Vì sao callback sau lưu và timestamp auditing chưa chứng minh commit.
- Cách đổi sang DTO/phân lô hoặc tiêu thụ trong service để làm rõ vòng đời.
- Khi nào listener sau commit là đủ và khi nào cần outbox có khả năng retry.

Một lời giải tốt phải mô tả cả đường thành công lẫn đường lỗi. Việc thêm annotation mà không chỉ ra thời điểm thực thi và quyền sở hữu tài nguyên chưa giải quyết được bài toán.

## 13. Điểm cần nhớ

`Stream` có thể giữ tài nguyên cho đến khi được đóng, nên phạm vi tiêu thụ phải phù hợp với phạm vi truy cập datastore. Callback và auditing thuộc các giai đoạn của đường xử lý, không tự đại diện cho commit. Flush, khi có trong JPA, vẫn khác commit.

Thiết kế repository an toàn bắt đầu từ việc xác định module thực tế, chủ sở hữu transaction, thời điểm dữ liệu được tiêu thụ và nơi phát sinh tác dụng phụ. Các abstraction dùng chung của Spring Data giúp tổ chức mã, còn bảo đảm tài nguyên và giao dịch phải được kiểm tra theo khả năng của từng loại kho dữ liệu.
