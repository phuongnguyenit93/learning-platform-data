# Tránh findAll hoặc chuyển toàn bộ stream thành collection ngoài nhu cầu

## 1. Giới hạn phải xuất phát từ nhu cầu của use case

Trong chương **Hiệu năng** của **SPRING_DATA_COMMONS**, một lỗi thường gặp là lấy toàn bộ dữ liệu qua repository rồi mới lọc, sắp xếp hoặc giới hạn ở Java. Lỗi tương tự xuất hiện khi một nguồn stream được chuyển thành collection chỉ để thuận tiện cho bước xử lý tiếp theo.

Các abstraction Repository, CRUD, phân trang và scrolling cung cấp nhiều cách diễn đạt nhu cầu. Tuy nhiên, kiểu trả về Iterable, Stream hoặc Flux không tự chứng minh truy vấn đã có giới hạn hoặc bộ nhớ được giữ ở mức nhỏ.

Trước khi chọn API, hãy hỏi:

- Cần một giá trị, một phần tử, một trang hay toàn bộ tập dữ liệu?
- Điều kiện nào có thể được thực hiện ngay tại store?
- Có thật sự cần giữ tất cả phần tử cùng lúc không?
- Nếu phải duyệt toàn bộ, có thể xử lý và giải phóng từng phần không?
- Giới hạn kết quả có phải một phần hợp đồng sản phẩm hay chỉ là biện pháp cắt dữ liệu tùy ý?

Mục tiêu là đọc lượng dữ liệu cần thiết và chọn cách tiêu thụ phù hợp, không phải cấm findAll hoặc mọi thao tác collect trong mọi trường hợp.

## 2. Phân biệt bốn quyết định độc lập

~~~text
Phạm vi dữ liệu:       Những bản ghi nào cần đọc?
Giới hạn kết quả:      Cần tối đa bao nhiêu bản ghi?
Biểu diễn dữ liệu:     Cần những field nào?
Cách tiêu thụ:         Giữ toàn bộ hay xử lý dần?
~~~

Một giải pháp chỉ thay đổi một quyết định có thể chưa đủ.

| Thay đổi | Điều có thể cải thiện | Điều chưa được bảo đảm |
| --- | --- | --- |
| List sang Stream | Có thể xử lý dần | Store không còn trả toàn bộ dữ liệu |
| Entity sang projection | Có thể giảm field và object graph | Số bản ghi được giới hạn |
| findAll sang query có filter | Thu hẹp tập dữ liệu | Tập phù hợp đủ nhỏ để đưa vào RAM |
| Thêm paging/limit ở query | Giới hạn phần kết quả | Query không phải xét nhiều dữ liệu ở store |
| Bỏ collectList/toList | Giảm giữ dữ liệu ở consumer | Driver, ORM hoặc sink không buffer |

Để có hiệu quả, cần xem toàn bộ đường đi từ query đến đầu ra cuối cùng.

## 3. Vì sao stream sau findAll thường đã quá muộn?

Với CrudRepository, findAll trả về Iterable. Đoạn mã sau tạo Java Stream từ Iterable:

~~~java
import java.util.List;
import java.util.stream.StreamSupport;

List<Invoice> selected = StreamSupport
        .stream(repository.findAll().spliterator(), false)
        .filter(invoice -> invoice.getStatus() == InvoiceStatus.PAID)
        .limit(50)
        .toList();
~~~

Java Stream đánh giá pipeline theo cơ chế riêng, nhưng findAll đã được gọi để tạo nguồn. Nếu module đã tải toàn bộ kết quả khi thực hiện findAll, filter và limit phía Java không quay lại sửa query của store.

Tương tự, với một API trả List:

~~~java
List<Invoice> selected = allInvoices.stream()
        .filter(invoice -> invoice.getStatus() == InvoiceStatus.PAID)
        .limit(50)
        .toList();
~~~

Pipeline này có thể chỉ duyệt một phần List, nhưng toàn bộ List đã tồn tại. Nó không giải quyết chi phí đọc và materialize đã xảy ra.

Không nên suy ra rằng mọi Iterable đều tải sẵn hoặc mọi Iterable đều lazy. Hành vi thực tế phụ thuộc implementation. Điểm quan trọng là **Java limit không phải hợp đồng giới hạn query ở store**.

### Lọc tại Java có thể làm sai cả hành vi

Giả sử API cần 50 hóa đơn đã thanh toán mới nhất. Lấy 50 hóa đơn bất kỳ rồi lọc PAID ở Java có thể chỉ còn vài phần tử, đồng thời bỏ qua những hóa đơn PAID nằm ngoài 50 hàng ban đầu.

Thứ tự thao tác đúng cần được diễn đạt ở query:

~~~text
Lọc đúng tập → Sắp xếp đúng → Giới hạn kết quả.
~~~

Không thay bằng:

~~~text
Lấy một tập tùy ý → Cắt bớt → Lọc và sắp xếp sau.
~~~

## 4. Chọn repository method theo câu hỏi cần trả lời

| Nhu cầu | Hợp đồng phù hợp để cân nhắc |
| --- | --- |
| Có tồn tại dữ liệu phù hợp không? | existsBy... |
| Có bao nhiêu dữ liệu phù hợp? | countBy... hoặc cơ chế đếm phù hợp |
| Tìm theo ID | findById |
| Lấy một tập nhỏ có giới hạn rõ | First/Top hoặc query có limit được module hỗ trợ |
| Giao diện có trang và tổng số | Page |
| Giao diện chỉ cần biết còn phần tiếp theo | Slice |
| Duyệt tuần tự theo window | Window và scrolling nếu module hỗ trợ |
| Đọc dữ liệu lớn theo dòng | Stream, reactive publisher hoặc cursor phù hợp |
| Tính tổng hoặc nhóm dữ liệu | Aggregation tại store nếu phù hợp |

Ví dụ, không cần tạo một collection chỉ để hỏi có dữ liệu hay không:

~~~java
boolean hasPaidInvoices =
        repository.existsByTenantIdAndStatus(
                tenantId, InvoiceStatus.PAID);
~~~

Hợp đồng này cho phép implementation thực hiện một phép kiểm tra tồn tại phù hợp. Không mặc định mọi store đều tạo cùng một dạng query hoặc có cùng chi phí.

Tương tự, count không cần ứng dụng materialize mọi entity, nhưng phép đếm vẫn có thể tốn công ở store. Khi tổng số chính xác không phải yêu cầu, đừng thêm nó chỉ vì có sẵn API.

### Không cắt dữ liệu âm thầm

Nếu sản phẩm cần tất cả kết quả, thay findAll bằng findFirst100 không tự hoàn thành yêu cầu. Cần thiết kế phân trang, scrolling hoặc export để lấy đủ dữ liệu.

Nếu sản phẩm chỉ cần 100 kết quả đầu, phải có thứ tự và mô tả rõ giới hạn đó. “100 kết quả đầu” không đồng nghĩa “tất cả kết quả”.

## 5. Ví dụ query có filter, sort và giới hạn

Giả sử Invoice có các property tenantId, status, createdAt, id, invoiceNumber và total. Một projection phục vụ danh sách:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public interface InvoiceRow {
    Long getId();
    String getInvoiceNumber();
    Instant getCreatedAt();
    BigDecimal getTotal();
}
~~~

Repository minh họa:

~~~java
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface InvoiceRepository extends Repository<Invoice, Long> {

    boolean existsByTenantIdAndStatus(
            String tenantId,
            InvoiceStatus status);

    long countByTenantIdAndStatus(
            String tenantId,
            InvoiceStatus status);

    List<InvoiceRow> findFirst100ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
            String tenantId,
            InvoiceStatus status);

    Slice<InvoiceRow> findByTenantIdAndStatus(
            String tenantId,
            InvoiceStatus status,
            Pageable pageable);
}
~~~

Đây là khai báo minh họa cho module hỗ trợ những dạng truy vấn tương ứng, không phải cam kết mọi store hỗ trợ toàn bộ từ khóa hoặc kiểu trả về.

Phương thức First100 diễn đạt giới hạn ngay trong hợp đồng repository. Projection diễn đạt các field cần đọc. Hai việc này giải quyết những loại chi phí khác nhau.

Sort có thêm id để phân định các hóa đơn cùng createdAt. Không dựa vào thứ tự chèn hoặc thứ tự trả về ngẫu nhiên.

### Kiểm soát page size

Khi nhận kích thước trang từ client, service cần xác định miền hợp lệ:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

if (requestedSize < 1 || requestedSize > 200) {
    throw new IllegalArgumentException(
            "Kích thước trang phải nằm trong khoảng 1..200");
}

if (pageNumber < 0) {
    throw new IllegalArgumentException("Số trang không được âm");
}

PageRequest request = PageRequest.of(
        pageNumber,
        requestedSize,
        Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

Slice<InvoiceRow> result =
        repository.findByTenantIdAndStatus(
                tenantId, InvoiceStatus.PAID, request);
~~~

Giới hạn 200 là lựa chọn minh họa của ứng dụng, không phải mặc định của Spring Data.

Không để một đường gọi vô tình chuyển thành unpaged nếu hợp đồng chỉ cho phép truy vấn có giới hạn. Đồng thời, giới hạn page size không giải quyết mọi chi phí của offset rất sâu; cần đánh giá scrolling khi use case phù hợp.

## 6. Khi chuyển kết quả thành collection là hợp lý

Collection hữu ích khi thuật toán thực sự cần tập dữ liệu trong bộ nhớ, hoặc khi hợp đồng trả về một danh sách nhỏ đã được giới hạn.

Ví dụ:

~~~text
Một trang tối đa 50 dòng → chuyển thành DTO List để trả API.
Một window tối đa 500 dòng → tạo batch gửi sang hệ thống khác.
Một bảng cấu hình có giới hạn được quản lý → nạp làm snapshot.
~~~

Các điều kiện cần có:

1. Giới hạn được xác định và thực thi.
2. Kích thước mỗi phần tử được đánh giá.
3. Các object liên quan không làm tập nhỏ trở thành object graph rất lớn.
4. Các tầng tiếp theo không cộng dồn nhiều batch vào một collection toàn cục.

Tên phương thức hoặc kiểu List không chứng minh tập dữ liệu nhỏ. Giới hạn phải xuất phát từ query, dữ liệu có ràng buộc thực tế hoặc hợp đồng được kiểm soát.

### Collection hữu hạn khác với toàn bộ dữ liệu không giới hạn

~~~java
List<InvoiceDto> rows = slice.getContent().stream()
        .map(this::toDto)
        .toList();
~~~

Nếu slice đã có kích thước hợp lệ, thao tác này khác bản chất với việc collect toàn bộ một query không giới hạn.

Tuy nhiên, toDto vẫn có thể tải quan hệ hoặc tạo dữ liệu lớn. Cần kiểm tra cả mapping sang DTO, không chỉ số phần tử đầu vào.

## 7. Stream.toList không làm mất dữ liệu nhưng có thể làm mất lợi ích bộ nhớ

Stream là mô hình xử lý, không phải cam kết rằng dữ liệu sẽ không bao giờ được giữ lại.

~~~java
try (Stream<Invoice> invoices = repository.openInvoiceStream(tenantId)) {
    List<Invoice> all = invoices.toList();
    processAll(all);
}
~~~

openInvoiceStream là tên API ứng dụng minh họa; cách khai báo query streaming phụ thuộc module.

Ở đây, mọi phần tử vẫn được thu vào List trước khi processAll bắt đầu. Nếu mục tiêu ban đầu là xử lý dữ liệu lớn mà không giữ tất cả, lợi ích đó đã bị mất ở terminal operation.

Các thao tác tương tự cần xem xét:

- collect(toList()) hoặc collect(toSet()).
- toArray().
- collect(toMap()) trên toàn bộ dữ liệu.
- groupingBy với các nhóm chứa toàn bộ phần tử.
- Tự thêm từng phần tử vào một List bên ngoài.

Không phải mọi collect đều giữ toàn bộ dữ liệu. Một phép đếm, tổng hợp nhỏ hoặc grouping với trạng thái hữu hạn có đặc điểm bộ nhớ khác. Cần phân tích trạng thái được giữ, không chỉ nhìn tên API.

### Thao tác trung gian cũng có thể giữ nhiều dữ liệu

| Thao tác | Đặc điểm cần xem xét |
| --- | --- |
| sorted | Thường cần giữ dữ liệu trước khi phát kết quả đã sắp |
| distinct | Cần nhớ các giá trị đã gặp; bộ nhớ phụ thuộc số giá trị khác nhau |
| groupingBy với danh sách | Có thể giữ gần toàn bộ phần tử trong các nhóm |
| groupingBy với counting | Giữ trạng thái theo số nhóm, không nhất thiết theo số phần tử |
| map/filter | Có thể xử lý dần, nhưng hàm bên trong vẫn có thể buffer hoặc truy cập dữ liệu |
| limit | Có thể dừng tiêu thụ sớm, nhưng không bảo đảm store chưa đọc/prefetch thêm |

Một pipeline stream không có toList vẫn có thể tốn nhiều bộ nhớ nếu có sorted, distinct hoặc một sink tích lũy dữ liệu.

## 8. Tiêu thụ stream trong phạm vi tài nguyên hợp lệ

Với module hỗ trợ query trả Stream, cần biết stream có giữ cursor, connection hoặc session hay không. Stream nên được đóng theo hợp đồng của module, thường bằng try-with-resources.

Ví dụ service imperative:

~~~java
@Transactional(readOnly = true)
public void exportInvoices(
        String tenantId,
        Consumer<InvoiceRow> sink) {

    try (Stream<InvoiceRow> rows =
            repository.streamForExport(tenantId)) {
        rows.forEachOrdered(sink);
    }
}
~~~

streamForExport là phương thức cần được triển khai hoặc khai báo bằng query streaming mà module cụ thể hỗ trợ. Các kiểu Consumer và Stream thuộc java.util.function và java.util.stream; annotation transaction cần cấu hình Spring transaction tương ứng.

Đoạn mã diễn đạt ý định:

- Mở nguồn dữ liệu.
- Tiêu thụ trong phạm vi phù hợp.
- Đóng stream dù xử lý thành công hay có exception.

Không trả một stream từ một phương thức rồi kết thúc phạm vi transaction trước khi bên gọi tiêu thụ, nếu stream cần tài nguyên của transaction đó.

Terminal operation không thay thế việc đóng stream. Việc toList hoặc findFirst kết thúc không tự chứng minh cursor đã được đóng.

### Transaction dài và sink chậm

Nếu sink ghi qua mạng hoặc xử lý chậm, stream có thể giữ tài nguyên trong thời gian dài. Một transaction bao quanh toàn bộ export không phải lựa chọn mặc định cho mọi hệ thống.

Cần đánh giá:

- Thời gian giữ connection hoặc cursor.
- Timeout.
- Mức nhất quán cần thiết.
- Ảnh hưởng của client ngắt kết nối.
- Khả năng phục hồi sau khi đã xử lý một phần.

Không gọi parallel tùy ý trên stream gắn với tài nguyên của một session/transaction. Việc đổi thread không tự làm driver hoặc persistence context an toàn cho truy cập đồng thời.

## 9. Đặc biệt với ORM: không collect vẫn có thể giữ entity

Với JPA, persistence context có thể giữ tham chiếu đến các entity đã được quản lý. Vì vậy, duyệt nhiều entity bằng Stream mà không thêm chúng vào List vẫn có thể làm bộ nhớ tăng.

readOnly có thể ảnh hưởng cách provider tối ưu, nhưng không phải cam kết phổ quát rằng mọi đối tượng được giải phóng ngay sau mỗi bước.

Những lựa chọn cần cân nhắc:

- Dùng projection hoặc DTO phù hợp cho tác vụ chỉ đọc.
- Xử lý theo window/chunk.
- Chọn ranh giới persistence context phù hợp.
- Cấu hình fetch và driver dựa trên phép đo.

Nếu dùng clear hoặc detach, phải hiểu tác động đến entity đang sửa, quan hệ lazy và dữ liệu chưa đồng bộ. Không thêm clear vào vòng lặp như một cách sửa bộ nhớ mà bỏ qua ngữ nghĩa persistence.

Projection cũng cần được xác minh trên query thật. Một implementation tải entity đầy đủ rồi mới tạo projection có đặc điểm khác với query thực sự chọn ít field.

## 10. Duyệt toàn bộ bằng window nhưng không tích lũy toàn bộ

Nếu yêu cầu thật sự là export mọi hóa đơn phù hợp, có thể chia thành window. Với module hỗ trợ scrolling:

~~~java
Window<InvoiceRow>
findFirst500ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
        String tenantId,
        InvoiceStatus status,
        ScrollPosition position);
~~~

Projection ở ví dụ đã có createdAt và id, là những khóa dùng để sort. Keyset còn yêu cầu các giá trị khóa và khả năng hỗ trợ phù hợp, bao gồm việc xử lý null.

Vòng lặp điều phối minh họa:

~~~java
public void exportByWindow(
        String tenantId,
        InvoiceStatus status,
        ExportSink sink) {

    ScrollPosition position = ScrollPosition.keyset();

    while (true) {
        Window<InvoiceRow> window = repository
                .findFirst500ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                        tenantId, status, position);

        if (window.isEmpty()) {
            if (window.hasNext()) {
                throw new IllegalStateException(
                        "Window rỗng nhưng vẫn báo có phần tiếp theo");
            }
            return;
        }

        for (InvoiceRow row : window.getContent()) {
            sink.write(row);
        }

        if (!window.hasNext()) {
            return;
        }

        position = window.positionAt(window.size() - 1);
    }
}
~~~

ExportSink là abstraction ứng dụng, cần có hợp đồng về việc hoàn tất ghi, buffer và xử lý lỗi. Nó không phải API của Spring Data Commons.

Vòng lặp không thêm các window vào một List tổng. Ranh giới transaction cho mỗi lần lấy dữ liệu hoặc toàn bộ phiên duyệt phải được thiết kế theo store và yêu cầu nhất quán.

### Đầu ra cũng phải xử lý dần

Thiết kế sau vẫn giữ toàn bộ đầu ra:

~~~text
Lấy từng window
  → thêm mọi dòng vào StringBuilder hoặc List tổng
    → cuối cùng mới ghi ra client.
~~~

Nếu mục tiêu là bộ nhớ có giới hạn, sink cũng cần buffer có giới hạn hoặc ghi dần theo định dạng phù hợp.

Một window có 500 phần tử không bảo đảm tổng bộ nhớ nhỏ khi sink tích lũy hàng triệu dòng.

### Checkpoint và chạy lại

Nếu tác vụ kéo dài, có thể lưu tiến độ sau khi sink xác nhận phần dữ liệu đã được xử lý theo hợp đồng.

Cần xử lý khoảng hở giữa “đã ghi đầu ra” và “đã lưu checkpoint”. Có thể có phần tử được xử lý lại khi retry; sink có thể cần tính idempotent.

Không tự coi cursor là một snapshot cố định. Dữ liệu chèn, xóa hoặc đổi sort key giữa các lần gọi có thể ảnh hưởng kết quả. Nếu cần export một ảnh chụp nhất quán, phải thiết kế cơ chế tương ứng với store.

## 11. Reactive: collectList khác với tiêu thụ có kiểm soát

Một nguồn Flux không tự bảo đảm kết quả sẽ không bị gom lại:

~~~java
return repository.findAll()
        .filter(this::matches)
        .collectList();
~~~

Ở đây:

- Filter thực hiện phía ứng dụng, không tự được đẩy vào query.
- collectList giữ toàn bộ kết quả đi qua filter.
- Query nguồn vẫn có thể không có giới hạn.

Nếu repository và module hỗ trợ, nên diễn đạt filter, sort và giới hạn bằng query phù hợp.

### take và limitRate giải quyết những việc khác nhau

- take có thể giới hạn số phần tử consumer nhận và hủy phần còn lại.
- Điều đó không tự bảo đảm store chưa xét nhiều dữ liệu hoặc driver chưa prefetch.
- limitRate điều chỉnh nhịp request trong pipeline, không phải giới hạn tổng số phần tử nghiệp vụ.

Khi cần tối đa 100 kết quả, hãy kiểm soát giới hạn ở hợp đồng query nếu module cho phép, thay vì chỉ thêm take(100) sau một findAll không giới hạn rồi coi mọi chi phí đã được loại bỏ.

### Tiêu thụ theo pipeline

~~~java
return repository.findRowsForExport(tenantId)
        .concatMap(row -> sink.write(row))
        .then();
~~~

Đoạn mã giả định findRowsForExport trả Flux và sink.write trả Mono thể hiện hoàn tất thao tác ghi. Cả hai là hợp đồng ứng dụng cần triển khai theo module.

concatMap giúp xử lý tuần tự, nhưng vẫn phải đánh giá prefetch và buffer của toàn pipeline. Nếu dùng xử lý đồng thời, cần giới hạn concurrency và xác định việc thay đổi thứ tự có được chấp nhận không.

collectList vẫn phù hợp khi đầu vào đã có giới hạn đủ nhỏ và API thực sự cần một List. Vấn đề là tập không có giới hạn hoặc vượt nhu cầu, không phải bản thân tên operator.

## 12. Ước lượng bộ nhớ theo trạng thái được giữ

Một mô hình đơn giản:

~~~text
Giữ toàn bộ:
M_peak ≈ N × W + bộ đệm + trạng thái mapping + đầu ra.

Xử lý theo chunk:
M_peak ≈ K × W + bộ đệm + trạng thái mapping còn giữ + đầu ra.
~~~

Trong đó:

- N là tổng số phần tử.
- K là kích thước chunk/window đang giữ.
- W là bộ nhớ trung bình của một phần tử trong biểu diễn đang xét.

W không phải mặc định bằng số byte trong database hoặc JSON. Object graph, chuỗi và metadata Java có chi phí riêng.

Ví dụ giả định W bằng 2 KiB:

~~~text
1.000.000 phần tử × 2 KiB ≈ 1,91 GiB.
500 phần tử × 2 KiB ≈ 0,98 MiB.
~~~

Đây chỉ là phần dữ liệu đang giữ theo mô hình, chưa cộng driver, ORM, sink và object trung gian.

Nếu persistence context hoặc sink vẫn giữ N phần tử, đổi vòng lặp thành window không làm tổng bộ nhớ trở thành K × W.

### Nhiều request cùng lúc

Giới hạn phải được đánh giá cả ở mức đồng thời. Một request giữ lượng dữ liệu chấp nhận được nhưng hàng chục request cùng làm vậy có thể tạo áp lực lớn.

Chọn page size, window size và concurrency dựa trên tổng tải cùng latency, không chỉ trên một lần chạy đơn lẻ.

## 13. Những trường hợp findAll có thể phù hợp

findAll có thể là lựa chọn hợp lý khi tập dữ liệu thực sự nhỏ, được quản lý và cần được sử dụng toàn bộ.

Ví dụ:

- Một bảng mã có ràng buộc vận hành về kích thước.
- Dữ liệu cấu hình cần nạp thành snapshot có giới hạn.
- Fixture kiểm thử cô lập.
- Công cụ nội bộ có phạm vi dữ liệu được xác định rõ.

Cần phân biệt “hiện tại đang ít dữ liệu” với “hợp đồng bảo đảm tập này có giới hạn”. Dữ liệu nghiệp vụ tăng theo thời gian không nên được xem là bảng mã chỉ vì môi trường phát triển đang có vài chục hàng.

Nếu nạp toàn bộ để cache, còn phải xét kích thước snapshot, chu kỳ refresh và việc giữ đồng thời bản cũ/bản mới khi cập nhật.

## 14. Cách xác minh thay đổi có hiệu quả

Một phép đo hữu ích cần đi đến lúc dữ liệu thực sự được tiêu thụ, không chỉ lúc repository trả một đối tượng lazy.

Nên quan sát:

| Chỉ tiêu | Câu hỏi |
| --- | --- |
| Số phần tử trả về | Có đúng giới hạn và đúng điều kiện nghiệp vụ không? |
| Query hoặc command thực tế | Filter, sort, limit có được thực hiện ở store không? |
| Dữ liệu engine phải xử lý | Có scan hoặc offset quá lớn không? |
| Dung lượng truyền | Có tải field lớn không cần thiết không? |
| Allocation và heap theo thời gian | Bộ nhớ tăng theo N hay ổn định theo chunk? |
| Tài nguyên đang giữ | Cursor, connection và transaction tồn tại bao lâu? |
| Buffer ở sink | Đầu ra có đang tích lũy toàn bộ không? |
| Tính đầy đủ khi export | Có thiếu, lặp hoặc dừng sớm không? |

Test chỉ assert kết quả có 50 phần tử chưa chứng minh store chỉ xét 50 hàng. Ngược lại, store xét nhiều hàng không tự đồng nghĩa phải tăng heap ở ứng dụng theo số hàng đã xét.

### Dữ liệu thử nghiệm phải đủ làm lộ vấn đề

Có thể dùng:

- Nhiều bản ghi không khớp điều kiện.
- Bản ghi có field lớn.
- Quan hệ có nhiều phần tử.
- Kết quả vượt nhiều window.
- Các giá trị sort trùng và trường hợp null theo chính sách.
- Sink xử lý chậm hoặc phát sinh lỗi giữa chừng.

Mock repository không đo được việc tải dữ liệu thật, cursor hoặc buffer của driver. Nó có thể kiểm tra logic điều phối, nhưng các kết luận về truy vấn và bộ nhớ cần bằng chứng tích hợp phù hợp.

## 15. Những lỗi cần tìm khi rà soát code

| Mẫu code hoặc thiết kế | Vấn đề cần kiểm tra | Hướng thay đổi |
| --- | --- | --- |
| findAll rồi filter | Tải dữ liệu ngoài phạm vi | Đưa điều kiện vào query |
| findAll rồi sorted/limit | Sort và giới hạn ở Java sau khi đã tải | Sort/limit tại store nếu phù hợp |
| stream rồi toList để xử lý từng dòng | Giữ toàn bộ dù thuật toán không cần | Tiêu thụ từng phần trong phạm vi tài nguyên |
| groupingBy chứa mọi phần tử | Dữ liệu vẫn nằm trong các nhóm | Aggregation hoặc trạng thái tổng hợp nhỏ hơn |
| findAll để isEmpty | Materialize dữ liệu chỉ để hỏi tồn tại | existsBy hoặc truy vấn tồn tại phù hợp |
| findAll để size | Tải entity chỉ để đếm | countBy khi cần tổng số |
| window rồi addAll vào List tổng | Giới hạn query nhưng không giới hạn bộ nhớ | Xử lý và giải phóng từng window |
| Flux rồi collectList không giới hạn | Gom toàn bộ kết quả | Query có giới hạn hoặc tiêu thụ dần |
| Stream entity dài hạn | ORM có thể giữ entity, connection bị giữ lâu | Projection/chunk và ranh giới phù hợp |
| Sinh toàn bộ chuỗi export trong RAM | Sink phá vỡ mục tiêu xử lý dần | Đầu ra có buffer được kiểm soát |

Không thay API hàng loạt chỉ vì trùng một mẫu. Trước hết cần xác định nhu cầu, giới hạn và trạng thái được giữ trong từng đường chạy.

## 16. Bài tập áp dụng

1. Chọn một đoạn findAll rồi filter/limit và mô tả tập dữ liệu thực sự cần.
2. Viết lại hợp đồng repository để thể hiện filter, sort và giới hạn.
3. Phân biệt trường hợp cần Page, Slice và duyệt toàn bộ.
4. Tìm terminal operation hoặc collection bên ngoài đang giữ toàn bộ stream.
5. Chuyển một tác vụ export sang xử lý theo window hoặc stream có đóng tài nguyên.
6. Kiểm tra cả bộ nhớ của ORM và sink, không chỉ List trong service.
7. Mô phỏng lỗi giữa chừng và xác định phần dữ liệu có thể được xử lý lại.
8. Đo tính đúng đắn, bộ nhớ và thời gian giữ tài nguyên với dữ liệu đủ lớn.

Một thiết kế đọc dữ liệu hiệu quả phải giới hạn những gì không cần đọc và không giữ những gì không cần giữ. Khi toàn bộ dữ liệu thực sự là yêu cầu, cần một đường tiêu thụ có kiểm soát từ repository đến đầu ra cuối cùng.
