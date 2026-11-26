# Stream<T>, xử lý lười và tài nguyên cơ sở dữ liệu

## Mục tiêu bài học

Một phương thức repository trả về `Stream<T>` có thể cho phép ứng dụng xử lý kết quả lần lượt, nhưng đồng thời giữ tài nguyên của kho dữ liệu trong suốt quá trình đọc. Thiết kế đúng cần trả lời ba câu hỏi: dữ liệu được đọc khi nào, ai đóng stream và tài nguyên còn hợp lệ đến thời điểm nào.

Sau bài học, bạn có thể:

- Phân biệt stream từ một collection với stream do truy vấn repository cung cấp.
- Giải thích xử lý lười của pipeline Java và giới hạn của khái niệm này ở tầng cơ sở dữ liệu.
- Tiêu thụ và đóng stream trong phạm vi tài nguyên, transaction phù hợp.
- Nhận diện những thao tác làm tăng bộ nhớ hoặc kéo dài thời gian giữ connection.
- Chọn cách xử lý theo khả năng thực tế của module Spring Data đang sử dụng.

Bài thuộc chương **Luồng và wrapper** của module **SPRING_DATA_COMMONS**. Trọng tâm là hợp đồng repository và cách sử dụng kiểu trả về dùng chung. Những chi tiết về JPA, cursor hay driver được nêu rõ theo phạm vi; Commons không làm mọi kho dữ liệu có cùng hành vi.

## 1. Stream là một pipeline xử lý, không phải một danh sách

`java.util.stream.Stream<T>` biểu diễn một chuỗi phần tử đi qua các phép biến đổi. Nó không phải collection để truy cập ngẫu nhiên theo chỉ số hay duyệt đi duyệt lại.

Cần phân biệt hai cách nhận stream:

```java
List<Invoice> invoices = repository.findByTenantId(tenantId);
Stream<Invoice> stream = invoices.stream();
```

và:

```java
Stream<Invoice> stream =
        repository.findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                tenantId, "OPEN", currency);
```

Trong đoạn đầu, repository đã trả về một `List`. Việc gọi `stream()` chỉ tạo pipeline trên dữ liệu của danh sách đó; nó không biến truy vấn vừa chạy thành một cursor đọc dần.

Trong đoạn sau, phương thức repository được khai báo trả `Stream<Invoice>`. Khi module hỗ trợ, việc duyệt có thể sử dụng cơ chế đọc tăng dần của store. Không phải mọi module Spring Data đều hỗ trợ kiểu trả về này. Xem [hợp đồng streaming query của Spring Data Commons](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-streaming).

### 1.1. Những kiểu trông gần nhau nhưng có hợp đồng khác nhau

| Kiểu hoặc cách tạo | Ý nghĩa cần hiểu |
| --- | --- |
| `List<T>` | Kết quả là một collection; có thể duyệt lại danh sách |
| `list.stream()` | Pipeline Java trên collection đã nhận |
| Repository trả `Stream<T>` | Kết quả có thể gắn với tài nguyên truy vấn; người dùng phải quản lý đóng |
| `Streamable<T>` | Abstraction tiện ích của Spring Data cho kết quả có thể duyệt; tên gọi không bảo đảm cursor cơ sở dữ liệu |
| `Flux<T>` từ repository reactive | Hợp đồng reactive riêng, cần module và hạ tầng reactive tương ứng |

Không suy ra đặc tính streaming ở database chỉ từ việc một đối tượng có phương thức `stream()`. Cần xem cả kiểu trả về của query method lẫn implementation phía sau.

## 2. Xử lý lười diễn ra ở tầng nào?

Một pipeline thường có ba phần:

```text
Nguồn dữ liệu
    → intermediate operations: filter, map, limit...
    → terminal operation: forEach, collect, reduce, findFirst...
```

Ví dụ thuần Java:

```java
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("a", "bb", "ccc")
        .filter(value -> value.length() >= 2)
        .map(String::toUpperCase);

// Chưa có yêu cầu duyệt pipeline ở đây.

try (Stream<String> values = pipeline) {
    values.forEach(System.out::println);
}
```

Kết quả:

```text
BB
CCC
```

Các intermediate operation mô tả việc xử lý. Khi terminal operation bắt đầu tiêu thụ, pipeline mới thực hiện phần tính toán cần thiết trên nguồn. `limit` là intermediate operation có thể cắt ngắn; `findFirst` là terminal operation có thể kết thúc sớm. Đây là ngữ nghĩa của Java Stream, trình bày trong [tài liệu package java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html).

### 2.1. Lazy pipeline không có nghĩa là chưa truy cập database

Với stream từ repository, có ít nhất hai mốc khác nhau:

1. Gọi repository để tạo hoặc thực thi truy vấn, nhận một nguồn kết quả.
2. Duyệt nguồn kết quả và áp dụng pipeline Java.

Store, persistence provider và driver quyết định thời điểm gửi truy vấn, mở cursor, tải batch đầu hoặc buffer dữ liệu. Không có quy tắc chung rằng SQL chỉ được gửi khi gọi `forEach`.

Vì vậy, ngay cả khi chưa gọi terminal operation, stream đã nhận vẫn có thể đang sở hữu tài nguyên cần được đóng.

### 2.2. Đọc từng phần tử ở Java không đồng nghĩa mỗi phần tử là một lượt mạng

Giả sử ứng dụng gọi xử lý lần lượt 10.000 hóa đơn. Driver có thể tải nhiều hàng trong một lần rồi cung cấp chúng cho Java từng hàng một.

Cần phân biệt:

- Số phần tử mà pipeline đã xử lý.
- Số hàng driver đã tải vào buffer.
- Số hàng database đã phải đọc hoặc sắp xếp.
- Số lượt trao đổi mạng.

Bốn con số này có thể khác nhau rất nhiều. Một pipeline chỉ xử lý mười phần tử không chứng minh rằng database chỉ làm công việc tương ứng với mười hàng.

## 3. Quy tắc sở hữu: nhận stream tài nguyên thì phải đóng

Stream truy vấn có thể bao bọc cursor và tài nguyên đặc thù của store. Cách sử dụng mặc định nên là `try-with-resources`:

```java
try (Stream<Invoice> invoices =
        repository.findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                tenantId, "OPEN", currency)) {

    invoices.forEach(this::process);
}
```

Phạm vi `try` biểu thị rõ nơi được phép tiêu thụ và nơi kết thúc quyền sở hữu tài nguyên. Khi đóng stream, hạ tầng có cơ hội giải phóng tài nguyên truy vấn; việc trả connection về pool còn phụ thuộc phạm vi transaction và cơ chế quản lý connection.

### 3.1. Terminal operation không thay thế close()

Đọc hết bằng `forEach`, tính `count`, hay nhận kết quả từ `findFirst` không tự tạo một lệnh `close()` cho mọi nguồn stream.

Ví dụ cần quản lý đóng dù chỉ lấy một phần tử:

```java
try (Stream<Invoice> invoices =
        repository.findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                tenantId, "OPEN", currency)) {

    Optional<Invoice> first = invoices.findFirst();
    first.ifPresent(this::process);
}
```

Trường hợp không có hóa đơn phù hợp cũng đi qua cùng cơ chế đóng. Không nên bỏ `try-with-resources` chỉ vì nghĩ kết quả sẽ rỗng hoặc pipeline thường kết thúc sớm.

Java Stream triển khai `AutoCloseable`; stream có nguồn tài nguyên cần được đóng sau sử dụng. Xem [hợp đồng Stream của Java](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html).

### 3.2. Exception không được làm mất bước giải phóng tài nguyên

Nếu `process` ném exception, `try-with-resources` vẫn thực hiện đóng stream khi thoát khối. Đóng stream xử lý vòng đời nguồn dữ liệu; nó không chứng minh công việc nghiệp vụ đã hoàn tất.

Đừng chỉ đặt `close()` ở dòng cuối của đường thành công:

```java
// Không phù hợp với stream nắm giữ tài nguyên:
Stream<Invoice> invoices =
        repository.findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                tenantId, "OPEN", currency);

invoices.forEach(this::process); // Nếu lỗi, dòng close bên dưới bị bỏ qua.
invoices.close();
```

### 3.3. Một stream chỉ dùng cho một lần tiêu thụ

Sau khi đã thực hiện terminal operation, không sử dụng lại cùng pipeline:

```java
// Sai về vòng đời sử dụng:
long total = invoices.count();
invoices.forEach(this::process);
```

Nếu cần cả số lượng và xử lý kết quả, hãy thiết kế một lượt xử lý phù hợp hoặc dùng truy vấn đếm riêng. Hai truy vấn độc lập còn cần được xét về tính nhất quán khi dữ liệu thay đổi.

Không xem một biến `Stream<T>` là một collection được cache để chia sẻ cho nhiều nơi.

## 4. Ví dụ: xuất hóa đơn trong một phạm vi tài nguyên rõ ràng

Phần này minh họa một ứng dụng **Spring Data JPA imperative** đã có cấu hình repository, transaction manager và entity `Invoice`. Java dùng mức ngôn ngữ 17 để khai báo record.

Mô hình nghiệp vụ:

```text
Invoice
├── id: Long
├── tenantId: String
├── status: String
├── currency: String
└── amount: BigDecimal
```

Giả sử entity được mapping hợp lệ, có getter tương ứng và các thuộc tính cần xuất không null. Query chỉ lấy hóa đơn `OPEN` của đúng tenant và loại tiền đã chọn.

### 4.1. Khai báo query method

```java
import java.util.stream.Stream;

import org.springframework.data.repository.Repository;

public interface InvoiceRepository extends Repository<Invoice, Long> {

    Stream<Invoice> findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
            String tenantId,
            String status,
            String currency);
}
```

`Repository` là abstraction chung. Cách tạo truy vấn và cách cấp stream do module JPA thực hiện trong ví dụ này.

Bộ lọc nằm trong query method, còn `OrderByIdAsc` xác định thứ tự của nguồn kết quả. Không dựa vào thứ tự lưu trữ tự nhiên để quyết định thứ tự xuất.

### 4.2. Tách dữ liệu xuất khỏi entity

```java
import java.math.BigDecimal;

public record InvoiceLine(
        Long id,
        String currency,
        BigDecimal amount) {

    public static InvoiceLine from(Invoice invoice) {
        return new InvoiceLine(
                invoice.getId(),
                invoice.getCurrency(),
                invoice.getAmount());
    }
}
```

DTO chỉ chứa các giá trị cần xuất. Không đưa proxy quan hệ lazy vào DTO rồi kỳ vọng nó còn đọc được sau khi persistence context đã kết thúc.

### 4.3. Tiêu thụ bên trong service

```java
import java.util.Objects;
import java.util.function.Consumer;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceExportService {

    private final InvoiceRepository repository;

    public InvoiceExportService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public void exportOpen(
            String tenantId,
            String currency,
            Consumer<InvoiceLine> sink) {

        Objects.requireNonNull(sink, "sink");

        try (Stream<Invoice> invoices =
                repository
                        .findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                                tenantId, "OPEN", currency)) {

            invoices.map(InvoiceLine::from)
                    .forEachOrdered(sink);
        }
    }
}
```

Hợp đồng của ví dụ:

- Tenant được xác định bởi tầng ứng dụng và truyền vào truy vấn.
- Caller gọi service qua Spring bean có transaction interception hoạt động.
- `sink` xử lý đồng bộ từng DTO trước khi trả quyền điều khiển.
- Service sở hữu stream repository và đóng nó.
- Caller sở hữu tài nguyên của `sink`, chẳng hạn writer của tệp xuất.
- Lỗi từ `sink` được truyền ra; ví dụ không âm thầm bỏ qua một hóa đơn.

`forEachOrdered` sử dụng thứ tự gặp phần tử của stream nếu có. Nguồn ví dụ đã khai báo sắp xếp theo id; không dùng toán tử Java để thay thế yêu cầu sắp xếp trong truy vấn.

Đây là cấu trúc vòng đời, không phải bảo đảm rằng mọi lần xuất lớn đều dùng bộ nhớ cố định. Tác động của entity và persistence context được xét ở phần sau.

## 5. Transaction phải bao trùm lúc tiêu thụ, không chỉ lúc tạo stream

Với JPA trong ví dụ trên, service giữ transaction trong khi mở, duyệt và đóng stream:

```text
Bắt đầu transaction
    → gọi repository
    → nhận stream
    → duyệt, ánh xạ, đưa dữ liệu sang sink
    → đóng stream
Kết thúc transaction
```

Query method do ứng dụng khai báo trong Spring Data JPA không tự có toàn bộ cấu hình transaction mặc định của các phương thức CRUD kế thừa. Đặt ranh giới tại service giúp biểu thị đơn vị công việc. Xem [transactionality của Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html).

### 5.1. Bẫy trả stream ra ngoài service

```java
@Transactional(readOnly = true)
public Stream<Invoice> openInvoices(String tenantId, String currency) {
    return repository
            .findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                    tenantId, "OPEN", currency);
}
```

Nếu transaction của lời gọi này là transaction ngoài cùng, nó kết thúc khi phương thức trả về. Caller nhận một pipeline chưa tiêu thụ nhưng nguồn dữ liệu có thể không còn hợp lệ lúc caller bắt đầu duyệt.

Đặt `@Transactional` chỉ trên phương thức repository cũng không tự mở rộng transaction đến hết quá trình caller sử dụng đối tượng trả về.

Một API cố ý chuyển quyền sở hữu stream cho caller vẫn có thể được thiết kế, nhưng phải quy định cả phạm vi tài nguyên lẫn transaction cần duy trì. Chỉ thêm chú thích “caller phải close” chưa giải quyết vòng đời transaction.

### 5.2. Bẫy trả pipeline từ một khối đã đóng

```java
// Sai: nguồn đã bị đóng trước khi caller tiêu thụ.
public Stream<InvoiceLine> openLines(
        String tenantId, String currency) {

    try (Stream<Invoice> invoices =
            repository
                    .findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
                            tenantId, "OPEN", currency)) {

        return invoices.map(InvoiceLine::from);
    }
}
```

`map` không tách dữ liệu khỏi nguồn ngay lập tức. Đối tượng trả về vẫn phụ thuộc pipeline vừa bị đóng.

Nếu cần trả dữ liệu độc lập khỏi nguồn, có thể materialize một tập kết quả **đã giới hạn phù hợp** thành DTO bên trong phạm vi tài nguyên. Với dữ liệu lớn, cân nhắc xử lý đồng bộ qua callback hoặc chia công việc thành các cửa sổ.

### 5.3. Annotation cần được thực thi bởi hạ tầng Spring

Trong chế độ proxy thông thường, việc một phương thức trong cùng đối tượng gọi trực tiếp phương thức khác của nó không tự tạo transaction interception mới.

Ví dụ, thêm `@Transactional` lên `exportOpen` rồi gọi `this.exportOpen(...)` từ một phương thức không có transaction không tạo ra cùng hiệu quả như lời gọi qua proxy.

Cần bảo đảm cấu hình transaction hoạt động và lời gọi đi qua ranh giới bean phù hợp. Xem [cách Spring thực thi @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

## 6. Pipeline Java không tự trở thành truy vấn của store

Xét hai ý định:

```java
// Query đã giới hạn theo tenant, trạng thái và loại tiền.
repository.findByTenantIdAndStatusAndCurrencyOrderByIdAsc(
        tenantId, "OPEN", currency);
```

và:

```java
// Giả sử đây là stream của một query có phạm vi rộng hơn.
invoices.filter(invoice -> "OPEN".equals(invoice.getStatus()))
        .filter(invoice -> currency.equals(invoice.getCurrency()))
        .limit(100);
```

Các lambda trong `filter` chạy trong pipeline Java. Spring Data không tự dịch chúng thành predicate của derived query hay JPQL.

Với cách thứ hai, ứng dụng có thể phải nhận nhiều hóa đơn rồi mới tìm được 100 hóa đơn phù hợp. Driver cũng có thể đã tải thêm dữ liệu trước khi pipeline dừng.

| Yêu cầu | Nên biểu diễn ở đâu khi store hỗ trợ? |
| --- | --- |
| Phạm vi tenant | Điều kiện truy vấn |
| Trạng thái hóa đơn | Điều kiện truy vấn |
| Chỉ lấy một số cột | Projection hoặc lựa chọn trường của query |
| Thứ tự kết quả | Sắp xếp của query |
| Giới hạn số kết quả | Cơ chế limit/paging được module hỗ trợ |
| Chuyển dữ liệu sang định dạng xuất | Tầng ứng dụng sau khi đọc |

Đẩy điều kiện phù hợp xuống store giúp giảm dữ liệu phải truyền. Chuyển định dạng, mã hóa nội dung hoặc ghép một giá trị trình bày vẫn có thể là trách nhiệm hợp lý của pipeline Java.

Không dùng filter ở Java như ranh giới cách ly tenant. Việc truy vấn đúng phạm vi ngay từ nguồn còn tránh đưa dữ liệu tenant khác vào tiến trình xử lý.

### 6.1. limit ở Java và giới hạn query là hai việc khác nhau

`stream.limit(100)` giới hạn số phần tử tiếp tục đi qua pipeline. Nó không mang hợp đồng “đặt giới hạn 100 vào truy vấn database”.

Nếu nghiệp vụ chỉ cần một số lượng nhỏ, dùng cách giới hạn được module hỗ trợ ngay ở query. Không tự ghép mọi kiểu tham số `Limit`, `Pageable` hoặc keyword vào mọi store mà chưa xác định hợp đồng tương ứng.

### 6.2. sorted ở Java không tạo index cho database

Gọi:

```java
invoices.sorted(Comparator.comparing(Invoice::getAmount))
        .limit(100)
        .forEach(this::process);
```

có thể phải tiêu thụ và giữ nhiều phần tử để biết 100 hóa đơn nhỏ nhất trong toàn bộ nguồn. Thao tác trông ngắn gọn nhưng không còn đặc tính xử lý từng hàng với bộ đệm nhỏ.

Nếu cần tìm 100 hóa đơn nhỏ nhất, hãy biểu diễn yêu cầu sort và limit ở query, rồi đánh giá index cùng kế hoạch thực thi phù hợp.

## 7. Streaming không tự bảo đảm bộ nhớ O(1)

Cần xem bộ nhớ tại nhiều tầng:

| Tầng | Ví dụ dữ liệu được giữ |
| --- | --- |
| Driver | Batch dữ liệu hoặc buffer của result set |
| Persistence provider | Entity được quản lý và thông tin phục vụ persistence context |
| Pipeline | Trạng thái của thao tác như `sorted`, `distinct` |
| Ứng dụng | Danh sách gom kết quả, buffer xuất, hàng đợi công việc |

### 7.1. Gom tất cả kết quả sẽ làm mất lợi ích ở đầu ra

```java
try (Stream<Invoice> invoices = openQuery()) {
    List<Invoice> all = invoices.collect(Collectors.toList());
}
```

Nguồn có thể được đọc tăng dần, nhưng biến `all` vẫn giữ toàn bộ phần tử. Nếu mục tiêu là xuất một tệp lớn, tiêu thụ trực tiếp từng dòng thường phù hợp hơn việc tạo một danh sách khổng lồ.

`openQuery()` ở đoạn minh họa đại diện cho phương thức mở query có hợp đồng tài nguyên đã xác định; nó không phải API có sẵn của Spring Data.

### 7.2. Entity JPA có thể được persistence context giữ lại

Trong luồng đọc entity, việc ứng dụng không thêm entity vào `List` chưa chứng minh entity đã được loại khỏi bộ nhớ. Persistence context có thể tiếp tục quản lý chúng trong thời gian transaction tồn tại.

Các hướng thiết kế cần cân nhắc theo provider:

- Query trả DTO hoặc scalar projection được hỗ trợ, tránh materialize entity không cần thiết.
- Chia công việc thành các đơn vị có phạm vi persistence context hữu hạn.
- Dùng API cursor/stream và cấu hình đọc phù hợp của provider khi cần.

Không rải `clear()` hay detach tùy ý vào một transaction đang có công việc khác. Việc thay đổi trạng thái quản lý entity phải gắn với thiết kế cụ thể, đặc biệt khi còn thay đổi chưa được flush.

### 7.3. Fetch size không đồng nghĩa giới hạn tổng kết quả

Fetch size thường liên quan đến cách driver lấy dữ liệu theo đợt; nó không có nghĩa query chỉ được trả tối đa bấy nhiêu hàng.

Hiệu lực của cấu hình phụ thuộc database, driver và provider. Không có một giá trị fetch size chung mà Commons bảo đảm sẽ bật streaming hiệu quả trên mọi hệ thống.

Cần quan sát lượng bộ nhớ, tốc độ đọc và thời gian giữ connection thực tế thay vì chỉ kiểm tra chữ ký `Stream<T>`.

## 8. Thread, parallel và reactive là những quyết định khác

Một stream truy vấn imperative thường được tiêu thụ theo luồng gọi đồng bộ. Chuyển sang parallel không tự tạo nhiều cursor độc lập hoặc chia query cho database.

```java
// Không dùng như một cách mặc định để tăng tốc truy vấn JPA.
invoices.parallel().forEach(this::process);
```

Với JPA, persistence context và transaction gắn với ngữ cảnh thực thi cần được giữ đúng. Xử lý entity ở các thread ngoài phạm vi phù hợp có thể gây lỗi hoặc hành vi không an toàn.

Tương tự, chuyển một stream đang mở sang executor rồi để service trả về làm tách quá trình duyệt khỏi phạm vi đã mở tài nguyên.

Nếu công việc cần chạy nền, hãy thiết kế để worker mở và tiêu thụ truy vấn trong phạm vi tài nguyên của chính nó. Nếu cần xử lý CPU song song, có thể tách các batch DTO hữu hạn rồi xử lý độc lập, đồng thời kiểm soát kích thước hàng đợi.

`Stream<T>` của Java cũng không cung cấp hợp đồng backpressure hay I/O không chặn như một repository reactive. Việc bọc stream blocking vào kiểu reactive không tự thay driver và nguồn truy vấn thành reactive.

## 9. Transaction dài và nguồn tiêu thụ chậm

Giả sử một lần xuất có 300.000 dòng, còn `sink` gửi từng dòng qua một dịch vụ mạng chậm. Stream có thể giữ tài nguyên truy vấn trong suốt thời gian chờ.

Các chi phí cần đánh giá từ thiết kế này:

- Connection có thể bị giữ lâu, làm giảm số connection còn phục vụ request khác.
- Transaction kéo dài có thể tăng chi phí quản lý phiên bản hoặc ảnh hưởng khóa, tùy database và isolation.
- Cursor hoặc transaction có thể hết thời gian chờ trước khi xử lý xong.
- Lỗi ở dòng gần cuối làm việc khởi động lại toàn bộ trở nên đắt.

`readOnly = true` là một phần cấu hình transaction, không phải cam kết rằng transaction không giữ tài nguyên hoặc dữ liệu luôn là một snapshot bất biến.

Khi công việc cần nghỉ giữa các đợt, tiếp tục sau lỗi hoặc tách khỏi tốc độ của client, có thể dùng các trang/cửa sổ hữu hạn. Keyset scrolling là một lựa chọn khi module hỗ trợ và thứ tự đáp ứng yêu cầu. Cách này cần thiết kế mốc tiếp tục; nó không tự xuất hiện từ một Java Stream.

Sự khác nhau cốt lõi:

```text
Stream tài nguyên:
    giữ một nguồn đang mở trong lúc duyệt

Đọc theo cửa sổ:
    nhận một nhóm hữu hạn
    → kết thúc phạm vi đọc của nhóm
    → xử lý
    → đọc nhóm tiếp theo
```

Mỗi cách có yêu cầu nhất quán và chi phí riêng; chọn theo đơn vị công việc thực tế.

## 10. Lỗi giữa chừng: đóng tài nguyên và khôi phục nghiệp vụ

Giả sử service đã chuyển 700 dòng sang tệp rồi dòng 701 gặp lỗi chuyển đổi.

`try-with-resources` bảo đảm thực hiện bước đóng khi thoát phạm vi. Nhưng 700 dòng đã ghi không tự biến mất chỉ vì transaction database rollback.

Tương tự, nếu `sink` đã gọi một dịch vụ ngoài, transaction JPA không tự hoàn tác tác động ở dịch vụ đó.

Cần phân biệt:

| Vấn đề | Điều cần thiết kế |
| --- | --- |
| Giải phóng nguồn truy vấn | Đóng stream đúng phạm vi |
| Hoàn tất tệp xuất | Cơ chế tệp tạm, đánh dấu hoàn tất hoặc thay thế kết quả phù hợp |
| Gửi lại sau lỗi | Khóa idempotency hoặc cách nhận diện phần tử đã xử lý |
| Tiếp tục một tác vụ lớn | Checkpoint và thứ tự ổn định theo cơ chế đọc được chọn |
| Đọc lại cùng tập dữ liệu | Yêu cầu về mốc thời gian, snapshot hoặc isolation |

Không mặc định retry toàn bộ pipeline là an toàn. Lần truy vấn sau có thể nhìn thấy dữ liệu khác, còn đầu ra trước lỗi vẫn tồn tại.

Đây cũng là lý do ví dụ `Consumer<InvoiceLine>` cần hợp đồng rõ: nó xử lý đồng bộ, nhưng việc hoàn tác đầu ra là trách nhiệm của quy trình xuất.

## 11. Khả năng chung và chi tiết theo loại kho dữ liệu

| Ngữ cảnh | Điều có thể dùng từ bài này | Điều cần xác định riêng |
| --- | --- | --- |
| Repository imperative hỗ trợ `Stream<T>` | Quyền sở hữu stream, đóng tài nguyên và một lần tiêu thụ | Cách thực thi query và tài nguyên nền |
| Spring Data JPA | Ranh giới service và transaction trong ví dụ | Provider, driver, fetch behavior, persistence context |
| Spring Data MongoDB imperative | Có query method trả Stream đọc và chuyển đổi khi duyệt | Vòng đời cursor, session và cấu hình phù hợp |
| Module không hỗ trợ query trả Stream | Các kiến thức pipeline Java vẫn hữu ích | Chọn return type hoặc API đọc được module hỗ trợ |
| Repository reactive | Thiết kế vòng đời theo API reactive | Subscription, cancellation và hạ tầng reactive của module |

Spring Data MongoDB có ví dụ query method `Stream<Person> findAllBy()` để đọc và chuyển đổi phần tử khi duyệt. Đây là khả năng của module cụ thể, không phải bằng chứng rằng mọi repository đều dùng cùng cơ chế. Xem [query methods của Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html).

Không mang yêu cầu transaction của ví dụ JPA áp dụng nguyên xi cho mọi document store. Ngược lại, không vì một store có thể dùng cursor ngoài transaction kiểu JPA mà bỏ qua transaction cần thiết trong ứng dụng JPA.

## 12. Thực hành quan sát vòng đời

Các tình huống dưới đây giúp phân biệt việc pipeline cho ra kết quả với việc tài nguyên được quản lý đúng.

| Tình huống | Điều cần quan sát |
| --- | --- |
| Query không trả phần tử | Phạm vi đóng vẫn được thực hiện |
| Đọc hết kết quả | Tài nguyên truy vấn được giải phóng sau khi thoát phạm vi |
| Chỉ gọi `findFirst` | Stream vẫn được đóng dù còn dữ liệu chưa tiêu thụ |
| Callback ném exception | Bước đóng vẫn chạy, lỗi không bị nuốt |
| Service trả stream rồi transaction kết thúc | Xác định lỗi vòng đời khi bắt đầu duyệt ở caller |
| Chuyển sang `collect(toList())` với dữ liệu lớn | Phân biệt nguồn đọc dần với bộ nhớ đầu ra |
| Sink xử lý chậm | Theo dõi thời gian giữ connection và transaction |
| Truy cập quan hệ từ entity trong `map` | Quan sát truy vấn phụ và dữ liệu bị tải thêm |

### 12.1. Mô phỏng cơ chế close bằng Java thuần

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);
Optional<Integer> first;

try (Stream<Integer> numbers = Stream.of(10, 20, 30)
        .onClose(() -> closed.set(true))) {

    first = numbers.findFirst();
}

System.out.println(first.orElseThrow()); // 10
System.out.println(closed.get());        // true
```

Ví dụ cho thấy `onClose` được gọi khi stream được đóng. Nó minh họa cấu trúc tài nguyên, không chứng minh một driver database đã đóng cursor đúng cách.

Hợp đồng các close handler nằm trong [BaseStream.onClose và BaseStream.close](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/BaseStream.html). Với tích hợp database, cần quan sát bằng công cụ của provider, driver hoặc connection pool phù hợp.

## 13. Câu hỏi tự kiểm tra

### Câu 1: Chuyển List thành Stream

Ứng dụng gọi repository trả `List<Invoice>`, sau đó gọi `list.stream()`. Việc này có giúp database trả dữ liệu qua cursor thay cho danh sách vừa nhận không?

**Trả lời:** Không. Pipeline được tạo trên collection đã có. Muốn dùng streaming query phải có API và implementation của module hỗ trợ.

### Câu 2: Chưa có terminal operation

Đã nhận stream từ repository nhưng chưa gọi `forEach`. Có thể bỏ qua đóng vì “chưa chạy query” không?

**Trả lời:** Không. Lazy của pipeline Java không bảo đảm chưa mở tài nguyên database. Stream đã nhận cần nằm trong phạm vi quản lý đóng.

### Câu 3: Chỉ lấy phần tử đầu tiên

`findFirst()` đã trả kết quả. Có còn cần `try-with-resources` không?

**Trả lời:** Có với stream tài nguyên. Kết thúc sớm việc tiêu thụ không thay thế việc đóng nguồn.

### Câu 4: Service có @Transactional

Service transactional trả về `Stream<Invoice>`; controller mới duyệt. Annotation đó đã đủ chưa?

**Trả lời:** Chưa. Nếu transaction kết thúc khi service trả về thì quá trình duyệt diễn ra ngoài phạm vi cần thiết. Hãy tiêu thụ bên trong đơn vị công việc hoặc thiết kế rõ phạm vi mà caller duy trì.

### Câu 5: Giới hạn 100 dòng

Pipeline `filter(...).limit(100)` có cam kết query database chỉ đọc 100 hàng phù hợp không?

**Trả lời:** Không. Filter và limit đang chạy ở Java; store có thể phải cung cấp nhiều dữ liệu hơn. Đặt điều kiện và giới hạn phù hợp tại query khi được hỗ trợ.

### Câu 6: Không giữ List là đủ tiết kiệm bộ nhớ?

Ứng dụng chỉ `forEach` entity nên có thể khẳng định bộ nhớ không tăng theo số hàng không?

**Trả lời:** Không. Cần xem buffer của driver, persistence context, trạng thái pipeline và dữ liệu mà callback giữ lại.

### Câu 7: Rollback và đầu ra ngoài database

Dòng 701 lỗi sau khi 700 dòng đã được gửi sang hệ thống khác. Transaction rollback có tự xóa 700 dòng đó không?

**Trả lời:** Không. Đóng stream và rollback database không tự hoàn tác tác động bên ngoài. Quy trình cần chính sách khôi phục hoặc idempotency riêng.

## Những điểm cần nhớ

- Stream từ repository có thể gắn với tài nguyên đang mở; dùng phạm vi đóng rõ ràng.
- Tính lười của pipeline không xác định toàn bộ thời điểm query hoặc cách driver tải dữ liệu.
- Tiêu thụ trong khi tài nguyên và transaction cần thiết còn hiệu lực.
- Đặt điều kiện, sort, projection và giới hạn ở tầng truy vấn khi phù hợp; pipeline Java không tự được dịch thành query.
- Đánh giá bộ nhớ ở cả driver, persistence context, pipeline và đầu ra.
- Chọn streaming, đọc theo cửa sổ hoặc reactive theo khả năng module và yêu cầu của tác vụ.
