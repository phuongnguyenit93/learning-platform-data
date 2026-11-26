# Chi phí mapping, converter và callback

## 1. Query nhanh vẫn có thể tạo một API chậm

Datastore trả kết quả nhanh chưa có nghĩa ứng dụng đã hoàn tất việc đọc dữ liệu. Sau khi nhận dữ liệu thô, driver và tầng mapping còn phải giải mã, tạo đối tượng, gán thuộc tính, chuyển đổi kiểu và thực hiện các callback được cấu hình. Khi trả nhiều bản ghi hoặc nhiều field, các bước nhỏ này có thể cộng thành lượng CPU và bộ nhớ đáng kể.

Ở chiều ghi, entity cũng có thể đi qua callback, auditing, chuyển đổi và tạo biểu diễn lưu trữ trước khi driver gửi yêu cầu. Nếu một converter hoặc callback gọi thêm repository hay dịch vụ ngoài, đường ghi còn phát sinh I/O mà số lần gọi `save()` không thể hiện được.

Trong Spring Data Commons, cần hiểu ba trách nhiệm:

- **Mapping** nối mô hình đối tượng với cấu trúc mà module lưu trữ sử dụng, bao gồm metadata, khởi tạo đối tượng và truy cập thuộc tính.
- **Converter** chuyển một giá trị hoặc đối tượng từ kiểu nguồn sang kiểu đích theo cấu hình chuyển đổi.
- **Callback** tham gia một giai đoạn được module hỗ trợ trong vòng đời đọc/ghi, có thể kiểm tra hoặc thay đổi đối tượng.

Các cơ chế dùng chung không làm đường thực thi của JPA, MongoDB, JDBC và R2DBC giống nhau. Khi phân tích hiệu năng, phải xác định module, API và đường thao tác thực tế.

## 2. Xác định mapping và callback nằm ở đâu

### 2.1. Đường đọc khái quát

```text
Datastore thực thi
    -> driver nhận và giải mã dữ liệu
    -> module chuyển dữ liệu lưu trữ sang giá trị/đối tượng
    -> tạo entity, DTO hoặc projection theo cơ chế tương ứng
    -> callback sau chuyển đổi nếu đường đọc có hỗ trợ
    -> ứng dụng tiếp tục xử lý
    -> serialize response nếu có
```

Một callback hay event trên dữ liệu thô có thể xuất hiện ở giai đoạn khác tùy module. Sơ đồ không phải hợp đồng thứ tự chung cho mọi repository.

Mapping cũng không luôn đồng nghĩa với tạo một đối tượng mới cho mọi lần đọc. Chẳng hạn, JPA provider có thể tương tác với persistence context và entity đã được quản lý. Các module khác có converter và cách materialize riêng.

### 2.2. Đường ghi khái quát

```text
Đối tượng miền
    -> callback trước chuyển đổi nếu được hỗ trợ
    -> chuyển sang cấu trúc lưu trữ
    -> callback trước ghi nếu được hỗ trợ
    -> driver thực hiện ghi
    -> callback sau ghi nếu được hỗ trợ
    -> transaction hoàn tất tại ranh giới quản lý nó
```

Trong MongoDB, có thể gặp các interface như `BeforeConvertCallback`, `BeforeSaveCallback` hoặc `AfterSaveCallback` theo API của module. Với JPA, entity lifecycle và auditing listener đi qua cơ chế của JPA/provider; không gắn nguyên một callback MongoDB vào entity JPA rồi kỳ vọng cùng hành vi.

Một callback sau ghi không tự chứng minh giao dịch ngoài đã commit. Đo tới callback đó cũng chưa chắc đã bao gồm thời gian hoàn tất transaction.

## 3. Mapping tốn chi phí gì?

### 3.1. Metadata và truy cập thuộc tính

Tầng mapping cần biết kiểu miền, tên thuộc tính, kiểu ID, version, constructor hoặc factory được sử dụng và cách các field liên hệ với dữ liệu lưu trữ. Nhiều metadata có thể được xây dựng rồi tái sử dụng, thay vì phân tích toàn bộ class cho mỗi bản ghi.

Không nên mặc định mọi lần gán field đều dùng reflection thuần. Một số cơ chế có thể dùng instantiator hoặc property accessor được tạo tối ưu khi mô hình và môi trường đáp ứng điều kiện. Cách hoạt động cụ thể phụ thuộc module, phiên bản và hình dạng class.

Tuy vậy, metadata đã cache không xóa chi phí tạo đối tượng, chuyển giá trị và gán thuộc tính cho kết quả thực tế.

### 3.2. Số lượng đối tượng và cấu trúc lồng nhau

Một bản ghi có thể tạo nhiều đối tượng Java:

- Entity hoặc DTO gốc.
- Value object như mã khách hàng, tiền tệ hoặc khoảng thời gian.
- Collection cùng các phần tử bên trong.
- Đối tượng trung gian do converter tạo ra.
- Wrapper hoặc projection proxy tùy dạng kết quả.

Nếu một document chứa nhiều danh sách lồng nhau, số đối tượng được tạo có thể lớn hơn nhiều số document trả về. Tương tự, một mô hình quan hệ có các dữ liệu liên quan được materialize có thể kéo theo nhiều đối tượng ngoài entity gốc.

Chi phí không chỉ là thời gian constructor. Allocation còn tạo áp lực lên heap và garbage collector. Một biến đổi chuỗi tưởng nhỏ nhưng lặp lại trên hàng trăm nghìn giá trị có thể tạo nhiều đối tượng tạm.

### 3.3. Mapping khác serialization

Chuyển dữ liệu từ store sang entity và chuyển entity sang JSON response là hai công việc khác nhau. Nếu đã đo toàn bộ response nhưng chỉ profile repository, có thể bỏ sót chi phí serializer hoặc truy cập thuộc tính sau khi repository trả về.

Ngược lại, timer kết thúc ngay sau khi tạo `Stream` hoặc publisher reactive có thể chưa đo hết mapping. Việc chuyển đổi có thể diễn ra khi tiêu thụ từng phần tử.

## 4. Converter: chi phí nhỏ có thể bị nhân rất nhiều lần

### 4.1. Minh họa một cặp converter đơn giản

Giả sử ứng dụng dùng value object:

```java
record CustomerCode(String value) {
}
```

Ở một module hỗ trợ cơ chế custom conversions tương ứng, có thể biểu diễn mã này bằng chuỗi trong store:

```java
@ReadingConverter
class CustomerCodeReadConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source);
    }
}
```

```java
@WritingConverter
class CustomerCodeWriteConverter
        implements Converter<CustomerCode, String> {

    @Override
    public String convert(CustomerCode source) {
        return source.value();
    }
}
```

Ví dụ dùng `org.springframework.core.convert.converter.Converter` cùng các annotation `org.springframework.data.convert.ReadingConverter` và `WritingConverter`. Cần đăng ký converters bằng cơ chế custom conversions của module đang dùng; không mặc định chỉ khai báo class hoặc bean là mọi store sẽ tự sử dụng nó.

`ReadingConverter` và `WritingConverter` xác định ý định chiều chuyển đổi, không tạo bảo đảm hiệu năng hay transaction. Với JPA, `AttributeConverter` của persistence provider là cơ chế khác; không coi cấu hình converter dùng cho document mapping tự động áp dụng vào entity JPA.

### 4.2. Đếm số lần gọi, không chỉ đếm số entity

Một converter có thể được gọi trên một field, nhiều field hoặc các phần tử của collection. Một số converter nhận cả đối tượng thay vì từng giá trị. Vì vậy, số lần converter chạy không nhất thiết bằng số entity.

Một mô hình ước lượng hữu ích là:

```text
Chi phí phía ứng dụng
    ≈ materialization cơ bản
    + tổng số lần gọi từng converter × chi phí trung bình của nó
    + công việc callback thực sự chạy
    + chi phí allocation/GC và xử lý liên quan
```

Đây là cách suy nghĩ về tỷ trọng, không phải công thức thời gian chính xác. Các phạm vi đo có thể chồng lấp; GC và mô hình bất đồng bộ cũng khiến việc cộng đơn giản không phản ánh mọi tình huống.

Ví dụ, 10.000 entity có một field cần chuyển đổi và 10.000 entity có 50 phần tử lồng nhau cần chuyển đổi là hai workload khác nhau. Đánh giá chỉ bằng số dòng trả về sẽ bỏ qua mức khuếch đại này.

### 4.3. Những việc dễ làm converter đắt lên

| Công việc trong converter | Chi phí hoặc hệ quả |
| --- | --- |
| Parse nhiều lần cùng một chuỗi | CPU và đối tượng tạm |
| Biên dịch regex cho từng giá trị | Lặp lại công việc có thể chuẩn bị trước |
| Serialize sang JSON rồi parse lại để đổi kiểu | Tạo nhiều lớp trung gian và allocation |
| Đọc file, gọi HTTP hoặc repository | Thêm I/O vào đường mapping |
| Tạo formatter hoặc cấu hình lớn mỗi lần | Chi phí khởi tạo lặp |
| Log đầy đủ từng giá trị | Format chuỗi, I/O và lượng log lớn |
| Dùng cache không giới hạn theo giá trị đầu vào | Tăng bộ nhớ và khó quản lý vòng đời |

Không phải mọi biến đổi đều cần loại bỏ. Một converter có trách nhiệm bảo vệ ý nghĩa kiểu dữ liệu có thể hoàn toàn hợp lý. Mục tiêu là bỏ công việc lặp không cần thiết và đặt I/O ở nơi có ranh giới rõ hơn.

## 5. Giữ converter đơn giản và an toàn khi dùng đồng thời

Converter thường được tái sử dụng qua hạ tầng Spring. Không nên giữ request hiện tại, tenant hiện tại hoặc entity đang xử lý trong một field mutable của converter để dùng lại ở lần gọi sau.

Các hướng thực hành phù hợp gồm:

- Dùng chuyển đổi xác định từ đầu vào sang đầu ra khi có thể.
- Tách việc chuẩn bị cấu hình bất biến khỏi xử lý từng giá trị.
- Dùng thành phần chia sẻ an toàn giữa thread; không mặc định mọi formatter hoặc bộ tính toán đều thread-safe.
- Hạn chế chuỗi biến đổi qua nhiều định dạng trung gian.
- Giữ chính sách null, giá trị không hợp lệ, đơn vị và múi giờ rõ ràng.

Ví dụ, `Pattern` đã biên dịch có thể được chia sẻ phù hợp, nhưng `Matcher` cho một lần xử lý không nên được dùng chung tùy tiện. Tương tự, chọn formatter bất biến an toàn giữa thread dễ kiểm soát hơn việc tái sử dụng một formatter mutable mà không đồng bộ.

Nếu cân nhắc cache kết quả chuyển đổi, phải đánh giá số giá trị phân biệt, kích thước cache, khả năng thay đổi cấu hình và phạm vi tenant. Không dùng cache toàn cục cho dữ liệu phụ thuộc người dùng hoặc tenant mà key không bao phủ ngữ cảnh đó.

### Không đánh đổi ý nghĩa dữ liệu để giảm CPU

Bỏ parse chính xác để dùng chuỗi thô, làm tròn tiền sớm hoặc đổi múi giờ ngầm có thể tạo sai lệch nghiệp vụ. Test chuyển đổi cần xác nhận các giá trị đại diện và trường hợp biên, không chỉ xác nhận tốc độ.

Cũng không mặc định `write(read(value))` phải luôn trả đúng từng byte ban đầu. Một hệ thống có thể chủ đích chuẩn hóa biểu diễn, nhưng sự chuẩn hóa đó phải được định nghĩa. Điều cần giữ là ý nghĩa dữ liệu theo hợp đồng đã chọn.

## 6. Callback: mức khuếch đại phụ thuộc công việc bên trong

### 6.1. Callback thuần CPU vẫn có thể đáng kể

Một callback chuẩn hóa một field ngắn thường khác hoàn toàn callback sắp xếp hàng nghìn phần tử, tính hash lớn hoặc xây lại toàn bộ metadata tìm kiếm mỗi lần lưu.

Ví dụ riêng cho Spring Data MongoDB:

```java
@Component
class CustomerCodeNormalizer implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(Customer customer, String collection) {
        String code = customer.getCode();
        if (code != null) {
            customer.setCode(code.strip().toUpperCase(Locale.ROOT));
        }
        return customer;
    }
}
```

Ví dụ dùng `BeforeConvertCallback` trong gói `org.springframework.data.mongodb.core.mapping.event`, giả định `Customer` mutable có getter/setter và quy tắc mã nghiệp vụ yêu cầu dạng chữ hoa đó. Đây không phải quy tắc chuẩn hóa áp dụng cho mọi loại dữ liệu.

Chi phí của callback được trả khi đường ghi tương ứng kích hoạt nó. Nếu cùng phép chuẩn hóa còn được lặp trong constructor, service, converter và serializer, cần xem mỗi tầng có thực sự cần làm lại hay không.

Với đối tượng immutable, callback có thể phải trả một đối tượng thay thế theo hợp đồng API. Khi đó cần tính cả allocation và tránh tạo bản sao nhiều tầng mà không có giá trị nghiệp vụ.

### 6.2. Callback có I/O có thể tạo N+1

Giả sử callback trước lưu gọi repository để tìm thông tin người dùng cho mỗi entity. Một lệnh lưu nhiều entity có thể trở thành:

```text
entity 1 -> lookup người dùng -> ghi
entity 2 -> lookup người dùng -> ghi
entity 3 -> lookup người dùng -> ghi
...
```

Số round trip phụ có thể tăng theo số entity, tùy đường thực thi và khả năng cache thực tế. Chi phí này không phải một phần bắt buộc của callback abstraction; nó đến từ implementation đã thêm công việc vào lifecycle.

Nếu dữ liệu bổ sung dùng chung cho một đơn vị công việc, có thể đọc hoặc xác định một lần ở service, rồi truyền ngữ cảnh phù hợp vào quy trình. Nếu cần dữ liệu khác nhau cho từng entity, có thể xem xét đọc theo lô và tra cứu trong một cấu trúc có giới hạn, nhưng phải giữ đúng độ nhất quán và quyền truy cập.

Không inject chính repository cuối cùng vào callback rồi lưu lại cùng loại entity một cách không kiểm soát. Điều này có thể gây vòng lặp callback, phụ thuộc vòng hoặc thêm nhiều lần ghi.

### 6.3. Đổi callback sang bất đồng bộ không tự giữ nguyên hành vi

Nếu callback quyết định dữ liệu cần ghi, đưa công việc đó ra một executor rồi để thao tác lưu tiếp tục có thể khiến dữ liệu được ghi trước khi biến đổi hoàn tất. Transaction context và tài nguyên cũng không tự đi theo thread mới trong mô hình imperative.

Cần phân biệt công việc thuộc đường ghi bắt buộc với thông báo có thể xử lý sau. Công việc sau commit hoặc outbox có vòng đời và bảo đảm riêng; không thay callback đồng bộ bằng một tác vụ chạy nền chỉ để giảm timer của `save()`.

## 7. Auditing cũng nằm trên đường cần đo

Auditing có thể lấy thời gian từ nguồn thời gian được cấu hình và lấy chủ thể qua `AuditorAware` hoặc cơ chế reactive tương ứng. Chi phí phụ thuộc implementation, không chỉ số field annotation trên entity.

Các trường hợp thường gặp:

| Cách cung cấp metadata | Điều cần đánh giá |
| --- | --- |
| Lấy ID chủ thể đã có trong ngữ cảnh | Chi phí truy cập ngữ cảnh và tính đúng của scope |
| Tải entity người dùng cho mỗi lần auditing | Số query phụ, vòng phụ thuộc và mapping bổ sung |
| Lấy thời gian từ nguồn bên ngoài mỗi entity | Độ trễ và khả năng lỗi của I/O |
| Cập nhật nhiều field audit với converter riêng | Số lần chuyển đổi và allocation |

Nếu chỉ cần định danh người thực hiện, một ID ổn định đã có sẵn có thể đơn giản hơn tải toàn bộ entity người dùng trong mỗi callback. Tuy nhiên, thay đổi kiểu audit field cần được thiết kế theo mapping và yêu cầu nghiệp vụ, không chỉ theo hiệu năng.

Ngữ cảnh actor dùng lại trong một request hoặc batch phải có phạm vi rõ. Không cache một auditor toàn cục rồi dùng cho nhiều người dùng. Với reactive, việc lấy actor cần theo cơ chế ngữ cảnh phù hợp, không mặc định thread-local imperative luôn đúng.

Một timestamp đã được điền không chứng minh commit thành công. Khi so sánh trước/sau tối ưu, phải giữ đúng thời điểm lifecycle, chính sách tạo/sửa và kết quả auditing mà hệ thống yêu cầu.

## 8. Giảm khối lượng mapping trước khi tối ưu từng phép gán

### 8.1. Chỉ lấy dữ liệu cần thiết khi API cho phép

Nếu màn hình chỉ cần ID và tên, nạp entity có nhiều field lớn rồi chuyển thành DTO có thể tạo công việc thừa. Projection hoặc query chọn field phù hợp có thể giảm dữ liệu truyền và số giá trị phải materialize.

Ví dụ hợp đồng danh sách:

```java
interface CustomerListView {
    Long getId();
    String getName();
}
```

```java
interface CustomerRepository extends Repository<Customer, Long> {
    Slice<CustomerListView> findByTenantIdAndActiveTrue(
        String tenantId, Pageable pageable
    );
}
```

Ví dụ chỉ có ý nghĩa trên module hỗ trợ query/projection tương ứng và với model đã mapping đúng. Projection không tự bảo đảm store chỉ đọc đúng hai field trong mọi trường hợp. Projection mở, thuộc tính lồng nhau và query creator có thể giới hạn khả năng tối ưu.

Chuyển entity thành DTO sau khi đã nạp đầy đủ không nhất thiết giảm được chi phí đọc và mapping ban đầu. Nó vẫn có giá trị ở biên API, nhưng cần quan sát query thực tế để biết đã bỏ được công việc nào.

### 8.2. Giới hạn số phần tử và kích thước collection

Phân trang, đọc theo lô hoặc truy vấn theo mốc khóa có thể giới hạn số đối tượng đang xử lý. Thứ tự ổn định và điều kiện tiếp tục phải phù hợp với dữ liệu cùng khả năng module.

Streaming giảm nhu cầu giữ toàn bộ kết quả ở ứng dụng nếu được sử dụng đúng, nhưng vẫn trả chi phí chuyển đổi cho từng phần tử thực sự đọc. Một converter đắt không trở nên rẻ chỉ vì nó chạy trong stream.

Với JPA, persistence context có thể giữ entity đã đọc. Nếu thiết kế dựa vào bộ nhớ có giới hạn, cần xem cả cơ chế quản lý đối tượng của provider, không chỉ tránh `collect()` ở mã ứng dụng.

## 9. Bulk operation và truy cập thấp hơn có semantics riêng

Một bulk update trực tiếp có thể nhanh hơn việc đọc và lưu từng entity vì không tạo cùng số đối tượng và round trip. Tuy nhiên, đường đó có thể không kích hoạt cùng callback, auditing hoặc kiểm tra version theo từng entity.

Trước khi đổi đường ghi, cần trả lời:

1. Field nào trước đây được converter hoặc callback tạo ra?
2. Callback nào bảo vệ bất biến bắt buộc?
3. Audit field và version sẽ được cập nhật bằng cách nào?
4. Lỗi một phần và kết quả cập nhật được biểu diễn ra sao?
5. Đối tượng đã được quản lý trong bộ nhớ có trở nên cũ không?

Cũng không mặc định bulk API hoàn toàn bỏ mọi mapping. Một số API vẫn dùng metadata hoặc converter để ánh xạ field và giá trị, nhưng không thực hiện đầy đủ lifecycle của từng đối tượng. Phải xét chính API đang dùng.

`saveAll()` không phải cam kết một bulk operation hoặc một lần callback duy nhất cho toàn bộ tập. Cách triển khai phụ thuộc module và trạng thái entity. Chỉ số số lần gọi method Java không đủ để kết luận có bao nhiêu lần chuyển đổi hoặc ghi thực tế.

## 10. Đo đúng CPU, allocation và I/O phát sinh

### 10.1. Đặt câu hỏi trước khi chọn công cụ

| Câu hỏi | Bằng chứng cần thu |
| --- | --- |
| Có bao nhiêu đối tượng được tạo? | Allocation profile và số phần tử/field thực tế |
| Converter nào chiếm CPU? | CPU profile với call stack của converter |
| Callback có gọi thêm store không? | Trace hoặc query log gắn với cùng đơn vị công việc |
| Có chi phí ngoài repository không? | Timer đến sau mapping/serialization cần quan sát |
| Thay đổi có giảm bộ nhớ thật không? | Allocation, GC và heap dưới workload tương đương |
| Đường ghi đã hoàn tất chưa? | Thời gian và lỗi tại transaction/commit hoặc mức xác nhận tương ứng |

CPU thấp nhưng latency cao có thể là chờ I/O, pool hoặc khóa. Ngược lại, CPU và allocation cao sau khi store đã trả dữ liệu là tín hiệu cần xem mapping và xử lý ứng dụng. Không dùng duy nhất thời gian query phía server để kết luận phần còn lại đều là converter.

### 10.2. Quan sát số lần gọi mà không làm lệch phép đo

Counter hoặc timer cho từng converter/callback có thể giúp xác định tần suất, nhưng instrumentation cũng có chi phí. Log từng field trên workload lớn có thể tự trở thành nút thắt.

Có thể dùng profiler, sampling hoặc metric tổng hợp phù hợp để giảm nhiễu. Nếu một converter được bọc để đo, cần giữ đúng generic type, chiều đọc/ghi và đăng ký của nó; wrapper cấu hình sai có thể khiến framework không còn chọn converter như trước.

Không cộng các timer lồng nhau rồi coi là tổng thời gian độc lập. Timer callback có thể đã bao gồm query phụ hoặc converter khác mà nó gọi.

### 10.3. Tách microbenchmark khỏi phép đo tích hợp

Microbenchmark, chẳng hạn dùng JMH, có thể giúp so hai cách parse hoặc chuyển đổi trên cùng tập giá trị. Cần tính đến warm-up, JIT và việc kết quả phải được sử dụng để không bị tối ưu bỏ.

Integration benchmark mới cho thấy converter được gọi bao nhiêu lần trong mapping thật, callback nào tham gia và có query phụ hay không. Một tối ưu nhanh hơn trong microbenchmark chưa chắc cải thiện API nếu phần đó chỉ chiếm tỷ lệ nhỏ.

Với reactive, đo pipeline được subscribe và tiêu thụ theo mục tiêu thực tế. Với stream, đo cả quá trình duyệt và đóng tài nguyên. Đo thời gian tạo một đối tượng đại diện cho công việc chưa thực hiện là không đủ.

## 11. Thiết kế phép so sánh trước và sau

Một phép so sánh cần giữ tương đương:

- Dữ liệu đầu vào, số phần tử và độ sâu cấu trúc lồng nhau.
- Field đầu ra và kết quả nghiệp vụ.
- Các callback, audit field và kiểm tra version bắt buộc.
- Transaction, mức xác nhận ghi và điều kiện kết nối.
- Cache, warm-up và mức đồng thời.

Nên báo cả latency, throughput, CPU, allocation và tỷ lệ lỗi theo mục tiêu. Nếu chỉ tăng throughput bằng cách bỏ validation hoặc bỏ audit, phải nhận diện đó là thay đổi semantics.

Các tập dữ liệu nên có giá trị thông thường, null khi hợp lệ, giá trị dài và cấu trúc lớn phù hợp thực tế. Một converter nhanh với chuỗi ngắn có thể có hành vi khác khi gặp chuỗi dài hoặc dữ liệu không hợp lệ.

Khi đo callback có truy cập store, tách thời gian xử lý tại ứng dụng khỏi I/O bổ sung nếu có thể. Không quy toàn bộ thời gian callback cho chi phí dispatch của cơ chế callback.

## 12. Phân tích một tác vụ đồng bộ khách hàng

### Hiện trạng minh họa

Một tác vụ đọc nhiều khách hàng rồi lưu sang mô hình khác. Mỗi khách hàng có nhiều mã phân loại và metadata. Triệu chứng gồm CPU cao, nhiều GC và số query lớn hơn dự kiến.

Quan sát cần thực hiện:

1. Đếm số khách hàng và tổng số mã phân loại thực sự được chuyển đổi.
2. Kiểm tra converter có parse hoặc serialize lại cùng dữ liệu không.
3. Kiểm tra callback có tải thông tin actor hoặc cấu hình cho từng entity không.
4. Xác định đối tượng nào bị giữ lại qua nhiều lô.
5. Đo riêng thời gian store, mapping và hoàn tất ghi.

### Các thay đổi có thể xem xét theo bằng chứng

Nếu converter biên dịch lại cùng regex, chuẩn bị phần cấu hình bất biến một lần bằng cách an toàn giữa thread. Nếu callback truy vấn cùng actor cho mọi entity, xác định ngữ cảnh actor một lần trong phạm vi tác vụ phù hợp. Nếu chỉ cần một số field để đồng bộ, xem query/projection giảm dữ liệu materialize.

Nếu lượng dữ liệu lớn, đọc và ghi theo lô có giới hạn. Không tạo một collection kết quả cuối chứa toàn bộ entity nếu mục tiêu là xử lý và giải phóng từng lô.

Mỗi thay đổi cần giữ đúng quy tắc mã phân loại, tenant, metadata audit và cách xử lý lỗi. Nếu chuyển sang bulk API, phải thiết kế tường minh các field mà trước đây callback chịu trách nhiệm.

### Điều không nên kết luận sớm

Không thể kết luận “reflection là nguyên nhân” chỉ vì tác vụ dùng mapping framework. CPU có thể đang nằm trong parse JSON tùy chỉnh, chuẩn hóa chuỗi hoặc serialize log. Tương tự, nhiều query có thể do callback của ứng dụng, không phải do converter bắt buộc phải truy cập database.

## 13. Những lỗi tối ưu thường gặp

| Cách làm | Vấn đề |
| --- | --- |
| Cache mọi kết quả converter trong map toàn cục | Bộ nhớ không giới hạn, sai scope hoặc dữ liệu cũ |
| Dùng formatter mutable dùng chung để giảm allocation | Có thể gây lỗi khi nhiều thread cùng truy cập |
| Bỏ validation hoặc giảm độ chính xác khi parse | Tăng tốc bằng cách đổi ý nghĩa dữ liệu |
| Chạy callback ghi dữ liệu trên executor rồi không chờ | Thay đổi thứ tự, ranh giới transaction và kết quả lưu |
| Chỉ đo query server | Bỏ sót mapping, callback, truyền dữ liệu và serialization |
| Chỉ đo thời gian tạo stream/publisher | Chưa đo phần công việc chạy khi tiêu thụ |
| Dùng bulk rồi kỳ vọng đầy đủ callback từng entity | Không xác định lại lifecycle của đường ghi mới |
| Gọi repository từ converter để làm giàu dữ liệu | Đưa I/O khó quan sát vào đường chuyển đổi có thể lặp nhiều lần |
| Tối ưu từng phép gán trước khi giảm field không dùng | Bỏ qua nguồn công việc thừa lớn hơn |

## 14. Bài tập vận dụng

Một repository trả 5.000 khách hàng. Mỗi khách hàng có 20 value object cần converter. Converter thực hiện parse JSON trung gian và log từng giá trị. Callback trước lưu tải lại cùng cấu hình tenant cho từng khách hàng. Tác vụ hiện tại đo thời gian quanh query server rồi cho rằng database đã đủ nhanh nên framework mapping là nguyên nhân duy nhất.

Hãy xây dựng phương án phân tích và tối ưu:

1. Ước lượng các nguồn khuếch đại số lần converter và callback, đồng thời chỉ ra điều gì cần đo để xác nhận.
2. Tách CPU, allocation và I/O phụ khỏi thời gian query chính.
3. Đề xuất cách loại bỏ công việc lặp mà vẫn giữ đúng chuyển đổi dữ liệu.
4. Xác định phạm vi an toàn để dùng lại cấu hình tenant.
5. Làm rõ cách kiểm chứng audit field, version và kết quả khi đổi sang đọc/ghi theo lô hoặc bulk API.

Một lời giải tốt cần chứng minh công việc nào đã được loại bỏ, công việc nào chỉ bị chuyển sang thời điểm khác và bảo đảm nào vẫn được giữ.

## 15. Điểm cần nhớ

Mapping, converter và callback có chi phí thực, nhưng mức ảnh hưởng phụ thuộc số đối tượng, số lần chuyển đổi và công việc được đặt vào lifecycle. Những lookup hoặc tác dụng phụ bên trong callback có thể tạo nhiều I/O hơn chi phí dispatch của chính cơ chế đó.

Ưu tiên quan sát dữ liệu thực sự materialize, giữ converter đơn giản, làm rõ scope của ngữ cảnh và giảm công việc lặp. Mọi tối ưu phải giữ đúng mapping, auditing, version và ranh giới transaction theo khả năng của module cùng datastore đang sử dụng.
