# Số lượt truy cập, số bản ghi và dung lượng dữ liệu thực tế

## 1. Một lần gọi repository có thể tạo nhiều loại chi phí

Trong chương **Hiệu năng** của **SPRING_DATA_COMMONS**, không nên đánh giá truy cập dữ liệu chỉ bằng số phương thức repository được gọi. Các abstraction như CRUD, derived queries, Page, Slice, projection và scrolling mô tả hợp đồng ở tầng Java; lượng công việc thực tế còn phụ thuộc module, mapping, driver và store.

Một lời gọi có thể kéo theo:

- Truy vấn lấy nội dung.
- Truy vấn đếm hoặc kiểm tra tồn tại.
- Các lần tải quan hệ khi ánh xạ hay serialize.
- Những đợt lấy thêm dữ liệu từ cursor.
- Chuyển đổi và materialize nhiều đối tượng hơn dữ liệu API cần.
- Truyền các field lớn dù ứng dụng chỉ sử dụng vài field nhỏ.

Cần quan sát ít nhất ba trục:

~~~text
Số lượt tương tác với store
Số bản ghi được xét, trả về và materialize
Dung lượng được truyền, cấp phát và trả cho client
~~~

Tối ưu một trục không bảo đảm hai trục còn lại cùng giảm. Một truy vấn duy nhất vẫn có thể đọc quá nhiều dữ liệu; một projection nhỏ vẫn có thể lặp lại hàng chục lần.

## 2. Định nghĩa đơn vị đo trước khi so sánh

Từ “lượt truy cập” dễ bị dùng cho những việc khác nhau:

| Ký hiệu | Đại lượng | Ví dụ |
| --- | --- | --- |
| C_repository | Số lời gọi API repository trong phạm vi đo | Một lần gọi findByStatus |
| Q_command | Số thao tác truy vấn/command logic gửi xuống store | SELECT nội dung, COUNT, truy vấn tải quan hệ |
| R_roundtrip | Số lượt trao đổi qua mạng theo cách đo của driver/protocol | Thực thi command và các lần lấy thêm cursor |
| N_examined | Số đơn vị dữ liệu engine phải kiểm tra | Hàng, document hoặc index entry theo metric của engine |
| N_returned | Số hàng/document trả từ store | 50 hàng nội dung và các kết quả phụ |
| N_materialized | Số đối tượng được tạo hoặc nạp ở tầng ứng dụng | Entity, quan hệ, projection, value object |
| N_api | Số phần tử nghiệp vụ trả cho client | 50 dòng hóa đơn |
| B_store | Dung lượng truyền giữa store và ứng dụng | Payload thực sự tại ranh giới được đo |
| B_api | Dung lượng phản hồi ứng dụng gửi cho client | JSON trước hoặc sau nén, phải ghi rõ |
| H_allocated | Bộ nhớ được cấp phát để xử lý request | Entity, buffer, chuỗi, DTO và serializer |

Q_command không nhất thiết bằng R_roundtrip. Một cursor có thể cần nhiều đợt lấy dữ liệu cho cùng một truy vấn. Cơ chế batching và protocol cũng làm quan hệ giữa command và lượt mạng thay đổi.

N_examined phải có đơn vị rõ. Một engine có thể báo riêng index entries examined và documents examined. Không gộp chúng rồi gọi tất cả là “số bản ghi trả về”.

N_returned và N_materialized cũng khác nhau. Một hàng kết quả join có thể chứa dữ liệu cho nhiều đối tượng, còn nhiều hàng có thể được hợp nhất thành cùng một aggregate root.

### Đặt ranh giới đo

Ví dụ một phạm vi phù hợp là:

~~~text
Từ lúc nhận request danh sách hóa đơn
đến khi hoàn tất serialize phản hồi.
~~~

Nếu chỉ đo quanh lời gọi repository, bạn có thể bỏ qua các truy vấn phát sinh sau đó khi mapper hoặc serializer truy cập quan hệ.

Nếu đo cả request, cần tách các truy cập ngoài store đang phân tích, chẳng hạn cache, dịch vụ ngoài và ghi log nghiệp vụ. Mỗi con số phải có cùng phạm vi trước khi được so sánh.

## 3. Theo dõi toàn bộ đường đi của dữ liệu

~~~mermaid
flowchart LR
    A[Request] --> B[Service]
    B --> C[Repository]
    C --> D[Driver và store]
    D --> E[Hàng hoặc document]
    E --> F[Mapping và conversion]
    F --> G[Entity hoặc projection]
    G --> H[DTO và serializer]
    H --> I[Response]
    G -. tải quan hệ .-> D
~~~

Các điểm có thể phát sinh chi phí:

1. Store quét hoặc tìm dữ liệu theo index.
2. Driver nhận kết quả, có thể theo nhiều batch.
3. Mapping tạo object graph và thực hiện conversion.
4. Mapper đọc thêm quan hệ.
5. Serializer có thể tiếp tục truy cập thuộc tính.
6. Response được mã hóa và có thể được nén.

Trong mô hình reactive hoặc streaming, nhiều bước có thể chồng lấp theo thời gian. Vì vậy, không cộng mọi duration đo được ở các tầng như thể chúng đều độc lập.

Một span repository bao trùm span driver đã chứa thời gian của driver. Cộng cả hai sẽ đếm trùng.

## 4. Ví dụ: API trả 50 hóa đơn nhưng tải nhiều hơn 50 dòng

Giả sử giao diện chỉ cần:

~~~text
ID hóa đơn, số hóa đơn, thời điểm tạo, tổng tiền.
~~~

Entity Invoice còn chứa ghi chú dài, dữ liệu mở rộng và một quan hệ Customer. Service lấy 50 hóa đơn rồi mapper đọc tên khách hàng, trong một cấu hình mà việc đó gây thêm truy vấn cho từng khách hàng.

Các giả định minh họa:

- Một query nội dung trả 50 hóa đơn.
- Có một query đếm tổng số hóa đơn phù hợp.
- 50 hóa đơn tham chiếu 50 khách hàng khác nhau.
- Mỗi khách hàng được tải bằng một query bổ sung.
- Mỗi hóa đơn truyền khoảng 32 KiB dữ liệu.
- Mỗi khách hàng truyền khoảng 2 KiB dữ liệu.
- Một dòng projection cần khoảng 256 byte.

Đây là số liệu giả định để phân tích, không phải kết quả đo của dự án.

### Ba phương án

| Phương án | Q_command theo giả định | Dữ liệu trả về từ các query nội dung | Payload nội dung ước tính |
| --- | --- | --- | --- |
| Page entity, tải từng customer | 1 nội dung + 1 count + 50 customer = 52 | 50 invoice + 50 customer | Khoảng 1,66 MiB |
| Page projection đủ field | 1 nội dung + 1 count = 2 | 50 dòng projection | Khoảng 12,5 KiB |
| Slice projection có một hàng nhìn trước | 1 nội dung | 51 dòng projection được lấy để xác định còn dữ liệu | Khoảng 12,75 KiB |

Các con số payload chưa cộng header, metadata, kết quả scalar của count và chi tiết protocol. Chúng cũng chưa nói payload có được nén hay không.

Trong bảng:

~~~text
50 × 32 KiB + 50 × 2 KiB = 1700 KiB ≈ 1,66 MiB
50 × 256 byte = 12800 byte = 12,5 KiB
51 × 256 byte = 13056 byte = 12,75 KiB
~~~

Một KiB bằng 1024 byte; một MiB bằng 1024 KiB. Cần phân biệt với KB/MB thập phân khi ghi báo cáo.

### Đừng biến ví dụ thành cam kết của framework

Bảng trên giả định cách triển khai và dữ liệu cụ thể:

- Page không phải lúc nào cũng thực hiện count query.
- Slice không có cùng chiến lược nhìn trước ở mọi module.
- Cache hoặc batch fetching có thể thay đổi số query quan hệ.
- Projection không phải lúc nào cũng giảm field vật lý như mong đợi.
- R_roundtrip có thể khác Q_command.

Chỉ dùng số đo thực tế để kết luận một triển khai đang có chi phí bao nhiêu.

## 5. Đo số lượt truy cập: không dừng ở số lời gọi Java

Xét một đoạn mã dạng:

~~~java
Page<Invoice> page = repository.findByStatus(status, pageable);

List<InvoiceDto> result = page.getContent().stream()
        .map(invoice -> new InvoiceDto(
                invoice.getId(),
                invoice.getInvoiceNumber(),
                invoice.getCustomer().getDisplayName(),
                invoice.getTotal()))
        .toList();
~~~

Đây là mã minh họa; domain, DTO và mapping phải được định nghĩa theo module cụ thể.

Service chỉ gọi repository một lần, nhưng getCustomer hoặc việc đọc field bên trong customer có thể kích hoạt tải dữ liệu tùy mapping và trạng thái của entity.

Để phát hiện N+1, cần quan sát cả:

~~~text
Query gốc
Query phụ trong mapper
Query phụ trong serializer
Truy vấn metadata như count
~~~

Không phải mọi trường hợp truy cập quan hệ đều tạo N query. Cache, eager loading, batch fetching hoặc dữ liệu đã có trong persistence context có thể thay đổi hành vi. Vấn đề là phải đo đường chạy thật với fixture đủ lớn và trạng thái được kiểm soát.

### Một cách đọc dấu hiệu

Giữ nguyên cấu trúc request, tăng kích thước trang từ 10 lên 20 rồi 50:

| Kích thước trang | Số query minh họa |
| --- | --- |
| 10 | 12 |
| 20 | 22 |
| 50 | 52 |

Mẫu tăng gần tuyến tính này gợi ý một query bổ sung trên mỗi phần tử. Nó là dấu hiệu để điều tra, chưa thay thế việc xác định query và điểm gọi cụ thể.

Nếu query count được tối ưu hoặc quan hệ có dùng lại customer, dãy số có thể khác. Đừng yêu cầu mọi lỗi N+1 phải tạo đúng công thức N + 2.

## 6. Phân biệt số bản ghi quét, trả về và hiển thị

Giả sử endpoint trả đúng 50 hóa đơn.

### Trường hợp lọc không hiệu quả

Store có thể phải xét nhiều hàng hoặc document mới tìm được 50 kết quả phù hợp. N_api bằng 50 không chứng minh N_examined nhỏ.

Một chỉ báo đơn giản, khi các đơn vị đo tương thích và N_returned lớn hơn 0, là:

~~~text
Tỷ lệ xét/trả = N_examined / N_returned
~~~

Tỷ lệ cao là tín hiệu cần đọc kế hoạch thực thi, điều kiện lọc và index. Nó không tự chứng minh query sai; một số nghiệp vụ hợp lệ cần xử lý nhiều dữ liệu.

Với query trả về 0 phần tử, báo N_examined riêng thay vì tạo một tỷ lệ chia cho 0 hoặc gán giá trị tùy ý.

### Trường hợp join làm tăng số hàng

50 hóa đơn có trung bình 10 chi tiết mỗi hóa đơn. Một query join có thể trả khoảng 500 hàng kết quả trước khi ORM hợp nhất root entity.

Nếu cùng join thêm một collection độc lập có 3 phần tử mỗi hóa đơn, một hình dạng join hợp lệ có thể tạo khoảng:

~~~text
50 × 10 × 3 = 1500 hàng
~~~

Khả năng thực thi, giới hạn mapping và cách xử lý của provider phải được kiểm tra; không phải mọi kiểu fetch nhiều collection đều được cho phép.

Dù ứng dụng cuối cùng nhận 50 root entity, dữ liệu lặp ở mức hàng vẫn có thể đã đi qua mạng và bộ giải mã. Root entity được deduplicate không đồng nghĩa payload vật lý cũng được loại lặp.

### Query đếm có thể trả một hàng nhưng làm nhiều việc

Một count query thường trả một giá trị scalar. Điều đó không có nghĩa engine chỉ kiểm tra một hàng.

Cần tách:

~~~text
Số hàng kết quả của count: thường rất nhỏ.
Lượng dữ liệu engine phải xử lý để tính count: phụ thuộc query và store.
~~~

Không suy ra chi phí count từ kích thước response của nó.

## 7. Dung lượng dữ liệu cần đo ở đúng ranh giới

Cùng một request có thể có nhiều con số dung lượng hợp lệ:

| Ranh giới | Đại lượng cần ghi rõ |
| --- | --- |
| Store → driver | Payload protocol, có hoặc không tính header/nén |
| Driver → mapping | Dữ liệu đã giải mã và các buffer |
| Trong heap | Entity graph, DTO, chuỗi và object trung gian |
| Ứng dụng → client | JSON hoặc định dạng khác trước/sau nén |
| Hạ tầng mạng | Byte thực truyền theo công cụ đang dùng |

Một response JSON nhỏ không chứng minh ứng dụng đã tải ít dữ liệu từ store. Entity có thể chứa field lớn bị bỏ khi serialize nhưng vẫn đã được truyền và materialize.

Ngược lại, giảm B_store không bảo đảm H_allocated giảm cùng tỷ lệ. Một biểu diễn lưu trữ ngắn có thể được chuyển thành nhiều object hoặc chuỗi trong Java.

### Ước lượng trước khi đo

Có thể dùng:

~~~text
B_payload ≈ tổng trên từng loại bản ghi
            (số lượng × kích thước truyền trung bình của loại đó)
~~~

Đây là ước lượng để tìm khu vực đáng chú ý, không thay thế số đo. Nó chưa phản ánh đầy đủ:

- Dữ liệu biến thiên theo từng bản ghi.
- Dữ liệu lặp do join.
- Protocol metadata.
- Nén.
- Biểu diễn kiểu dữ liệu.
- Cursor batching.

Không dùng kích thước một entity rỗng hoặc một JSON mẫu nhỏ làm đại diện cho toàn bộ dữ liệu sản xuất.

## 8. Dùng projection để giảm dữ liệu cần lấy

Nếu giao diện chỉ cần vài thuộc tính, có thể diễn đạt hợp đồng đọc bằng projection:

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
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface InvoiceRepository extends Repository<Invoice, Long> {

    Page<Invoice> findByStatus(
            InvoiceStatus status,
            Pageable pageable);

    Slice<InvoiceRow> findByStatusOrderByCreatedAtDescIdDesc(
            InvoiceStatus status,
            Pageable pageable);
}
~~~

Ví dụ giả định domain có các property tương ứng và module hỗ trợ kiểu truy vấn, projection, paging đã khai báo. Nếu gọi phương thức thứ hai với Pageable không có sort bổ sung, thứ tự tĩnh trong tên phương thức thể hiện createdAt DESC, id DESC.

Lợi ích mong muốn là chỉ lấy dữ liệu cần cho dòng danh sách. Để chứng minh điều đó, cần xem query hoặc command thực tế và lượng dữ liệu trả về.

### Những điểm projection chưa tự bảo đảm

- Projection lồng nhau có thể kéo theo join hoặc tải quan hệ rộng hơn.
- Open projection có biểu thức có thể hạn chế khả năng tối ưu field.
- Một custom implementation có thể vẫn tải entity đầy đủ rồi mới chuyển đổi.
- Converter hoặc mapping có thể tạo thêm dữ liệu trung gian.
- Thông tin sort hoặc keyset có thể yêu cầu field không hiển thị.

Projection là công cụ mô tả nhu cầu dữ liệu, không phải bằng chứng đo lường rằng store luôn trả đúng số byte tối thiểu.

## 9. Page, Slice và scrolling thay đổi chi phí thế nào?

### Page khi sản phẩm cần tổng số

Page cung cấp nội dung cùng metadata về tổng số phần tử/trang. Để có tổng số, implementation có thể cần count query, nhưng cũng có những trường hợp suy ra được mà không chạy count.

Nếu UI thực sự cần tổng số chính xác, phải tính chi phí đó vào endpoint. Nếu chỉ cần nút “xem tiếp”, có thể cân nhắc hợp đồng khác.

Không đổi Page thành Slice chỉ để giảm một query mà bỏ qua yêu cầu của sản phẩm.

### Slice khi chỉ cần biết còn dữ liệu

Slice tập trung vào phần nội dung và khả năng có phần kế tiếp. Một triển khai thường lấy thêm dữ liệu nhìn trước để xác định hasNext.

Điều đó có thể làm N_returned lớn hơn N_api một lượng nhỏ. Phải kiểm tra module đang dùng và đo thay vì giả định công thức cố định cho tất cả store.

### Offset và keyset scrolling

Offset sâu có thể khiến store phải đi qua nhiều dữ liệu trước khi trả window hiện tại. Payload trả về có thể vẫn nhỏ trong khi N_examined hoặc công việc nội bộ tăng.

Keyset có thể giảm công việc tiếp nối khi có sort, khóa cursor và index phù hợp. Nó không tự giảm kích thước từng bản ghi hoặc làm mọi query nhanh hơn.

Cần đo riêng:

~~~text
Window đầu
Window ở vị trí sâu
Tập có nhiều giá trị sort trùng
Filter có độ chọn lọc khác nhau
~~~

Keyset còn yêu cầu kiểm soát các sort key, giá trị null và khả năng hỗ trợ của module. Một chiến lược scrolling hiệu quả vẫn có thể chậm nếu mỗi window tải nhiều field lớn hoặc quan hệ không cần thiết.

## 10. Ít query hơn chưa chắc tốt hơn

Giả sử có hai phương án tải 50 hóa đơn cùng một số dữ liệu liên quan:

~~~text
A: Nhiều query nhỏ.
B: Một query join rất rộng.
~~~

Phương án B có thể giảm số lần chờ mạng nhưng tăng:

- Số hàng lặp.
- Tổng byte nhận.
- Công việc sort hoặc join.
- Chi phí materialization và deduplication.
- Áp lực heap.

Một phương án trung gian có thể là lấy root theo trang rồi tải một nhóm dữ liệu liên quan theo các ID cần thiết. Tuy nhiên, vẫn phải xét giới hạn tham số, kích thước tập ID, thứ tự kết quả và hợp đồng của store.

Không mặc định findAllById luôn tương đương đúng một câu lệnh IN hoặc luôn trả kết quả theo thứ tự đầu vào.

### Cân nhắc độ trễ mạng

Với các thao tác tuần tự, mỗi thao tác có một chi phí giao tiếp cố định, nhiều lượt nhỏ có thể tạo tổng độ trễ lớn.

Có thể dùng Q nhân chi phí cố định mỗi lượt làm ước lượng ban đầu trong mô hình đơn giản. Nhưng không cộng thời gian query đã bao gồm mạng và server thêm một lần nữa, và không áp dụng phép cộng tuần tự cho các công việc thực sự chạy đồng thời.

Kết luận cần dựa vào latency thực tế, Q_command, R_roundtrip, byte và mức sử dụng tài nguyên, thay vì một con số query count.

## 11. Ghi nhiều dữ liệu cũng cần phân biệt API và thao tác vật lý

Một lời gọi saveAll không phải cam kết rằng tất cả dữ liệu được ghi bằng một batch vật lý duy nhất.

Tùy module, mapping và trạng thái entity, có thể phát sinh:

- Kiểm tra tồn tại hoặc nhận diện đối tượng mới.
- Nhiều thao tác insert/update.
- Cấp ID.
- Ghi các thành phần aggregate hoặc quan hệ.
- Callback, conversion và auditing.
- Truy vấn bổ sung từ logic tùy biến.
- Đồng bộ theo batch hoặc từng phần.

Vì vậy, với đường ghi, cần ghi rõ:

~~~text
Số đối tượng đầu vào
Số thao tác ghi vật lý
Số thao tác đọc phát sinh
Kích thước mỗi batch
Dung lượng truyền
Ranh giới transaction
~~~

Một batch lớn có thể giảm lượt trao đổi nhưng tăng bộ nhớ, thời gian giữ tài nguyên hoặc độ lớn rollback. Kích thước batch cần được chọn theo phép đo và giới hạn store.

Không coi việc saveAll trả về đủ đối tượng là bằng chứng rằng batching đã hoạt động.

## 12. Stream và reactive không tự giảm toàn bộ dữ liệu

Stream hoặc Flux có thể giúp xử lý dần thay vì giữ toàn bộ kết quả trong bộ nhớ ứng dụng. Điều này không tự chứng minh:

- Store chỉ xét ít bản ghi.
- Driver chỉ lấy đúng một bản ghi mỗi lần.
- Không có prefetch hoặc buffer.
- Query không tải field dư.
- Mỗi phần tử không kích hoạt truy vấn phụ.

Fetch size, batch size, demand và buffering là những khái niệm liên quan nhưng không đồng nhất. Cách chúng tác động phụ thuộc driver và module.

Với reactive, backpressure có thể kiểm soát luồng tiêu thụ trong những phạm vi được hỗ trợ. Nó không tự biến một điều kiện lọc kém thành truy vấn dùng index hiệu quả.

Khi đo một pipeline, phải thực sự subscribe và chờ xử lý kết thúc. Chỉ đo thời gian tạo publisher không đo được thời gian truy cập dữ liệu.

Với stream hoặc cursor cần đóng tài nguyên, phạm vi đo cũng phải bao gồm việc tiêu thụ và giải phóng phù hợp.

## 13. Quy trình đo có thể lặp lại

### Bước 1: Chọn use case cụ thể

Ví dụ:

~~~text
Lấy 50 hóa đơn đã thanh toán,
sort theo createdAt DESC, id DESC,
trả bốn field và không cần tổng số.
~~~

Mô tả rõ filter, sort, dữ liệu cần trả và mức nhất quán. Đây là cơ sở để đánh giá một tối ưu có giữ đúng hành vi hay không.

### Bước 2: Chuẩn bị dữ liệu có hình dạng thực tế

Không chỉ chuẩn bị đủ số lượng root. Cần mô phỏng:

- Field nhỏ và field lớn.
- Phân bố giá trị filter.
- Quan hệ ít/nhiều phần tử.
- Nhiều root dùng chung một đối tượng liên quan hoặc mỗi root dùng một đối tượng khác.
- Dữ liệu ở đầu và sâu trong thứ tự duyệt.

Fixture quá nhỏ dễ khiến quét toàn bộ hoặc N+1 trông vẫn nhanh.

### Bước 3: Xác định trạng thái cache và vòng đời tài nguyên

Tách các tình huống có ý nghĩa:

- Cache hoặc persistence context đã có dữ liệu.
- Cache ứng dụng chưa có dữ liệu.
- Store đã có dữ liệu trong bộ nhớ đệm hay chưa, nếu có thể kiểm soát và quan sát.

Không gọi tất cả là “cold” nếu chỉ xóa một tầng cache. Không cần cưỡng ép xóa mọi cache cho mọi phép đo; cần ghi rõ điều kiện thực tế.

### Bước 4: Thu thập nhiều loại bằng chứng

| Nguồn quan sát | Dùng để hiểu |
| --- | --- |
| Trace theo request | Truy cập phát sinh ở service, mapper và serializer |
| Log/query statistics của module hoặc driver | Query/command và các lần thực thi |
| Kế hoạch thực thi của store | Index, scan, sort, join và lượng công việc |
| Metric hoặc instrumentation ở ranh giới truyền tải | Byte gửi/nhận theo định nghĩa của công cụ |
| Profiling CPU và allocation | Chi phí mapping, conversion, DTO và serialization |
| Kích thước phản hồi | B_api theo encoding và điều kiện nén |

Log câu lệnh không tự cho biết đầy đủ byte trên mạng. Kích thước JSON cũng không phải phép đo B_store.

Nếu chạy cơ chế phân tích thực thi có thực sự thực thi query, phải hiểu tác dụng của công cụ trên workload đang đo. Không nhầm kế hoạch ước lượng với số lượng đã quan sát khi thực thi.

### Bước 5: Đổi một yếu tố có ý nghĩa và đo lại

Ví dụ chuyển entity sang projection, hoặc bỏ nhu cầu count khi hợp đồng API cho phép.

Giữ các điều kiện khác đủ tương đồng để giải thích kết quả. Đo cả tính đúng đắn lẫn chi phí; một query nhanh vì bỏ mất điều kiện nghiệp vụ không phải tối ưu thành công.

## 14. Mẫu bảng ghi nhận kết quả

Bảng dưới đây là mẫu ngay trong tài liệu, không phải kết quả đã đo:

| Chỉ tiêu | Trước thay đổi | Sau thay đổi | Điều kiện đo |
| --- | --- | --- | --- |
| N_api | Điền số đo | Điền số đo | Cùng một hợp đồng dữ liệu |
| C_repository | Điền số đo | Điền số đo | Phạm vi request đã xác định |
| Q_command | Điền số đo | Điền số đo | Bao gồm query phụ và metadata |
| R_roundtrip | Điền số đo hoặc chưa có | Điền số đo hoặc chưa có | Theo công cụ driver/protocol |
| N_examined | Điền số đo và đơn vị | Điền số đo và đơn vị | Theo engine |
| N_returned | Điền số đo | Điền số đo | Tách nội dung và kết quả phụ nếu cần |
| B_store | Điền byte hoặc chưa có | Điền byte hoặc chưa có | Ghi rõ boundary và nén |
| B_api | Điền byte | Điền byte | Trước/sau nén được xác định |
| H_allocated | Điền số đo hoặc chưa có | Điền số đo hoặc chưa có | Cùng phạm vi profiling |
| Latency p50/p95 | Điền số đo | Điền số đo | Cùng workload và mức đồng thời |

Nếu chưa đo được một đại lượng, ghi “chưa có” thay vì suy diễn từ một metric khác.

Không lấy một lần chạy đơn lẻ làm cơ sở kết luận về p95. Cần số lần quan sát và workload đủ phù hợp, đồng thời kiểm soát ảnh hưởng của warm-up, logging và tải nền.

## 15. Những kết luận sai thường gặp

| Nhận định | Vì sao chưa đủ |
| --- | --- |
| Chỉ gọi repository một lần nên chỉ có một query | Có thể có count, tải quan hệ hoặc query tùy biến |
| Chỉ trả 50 phần tử nên database chỉ đọc 50 hàng | Engine có thể xét nhiều dữ liệu hoặc join tạo nhiều hàng |
| Một query luôn nhanh hơn nhiều query | Có thể tăng byte, nhân hàng và CPU |
| Page luôn chạy đúng hai query | Có thể tối ưu count hoặc phát sinh thêm truy vấn |
| Slice chỉ lấy đúng kích thước trang | Có thể lấy thêm dữ liệu để xác định còn phần tiếp theo |
| Projection luôn chỉ đọc vài cột | Còn phụ thuộc dạng projection và implementation |
| JSON nhỏ thì dữ liệu lấy từ store cũng nhỏ | Field có thể đã được tải rồi mới bỏ khi serialize |
| saveAll nghĩa là một batch | Hợp đồng API không cam kết cùng cách thực hiện vật lý |
| Reactive nghĩa là không buffer | Driver, operator và pipeline có thể buffer/prefetch |
| Query count giảm nghĩa là hiệu năng tăng | Cần đo cả latency, byte, số bản ghi và tài nguyên |

## 16. Bài tập áp dụng

1. Chọn một API danh sách và xác định chính xác các field cần trả.
2. Đếm truy vấn trong toàn bộ request, kể cả mapper và serializer.
3. Tăng kích thước trang để xem query phụ có tăng theo số phần tử không.
4. Phân biệt N_api với N_returned và N_examined bằng bằng chứng của store.
5. Ước lượng payload từ số lượng và kích thước bản ghi, rồi so với phép đo nếu có.
6. So sánh entity với projection trên cùng hợp đồng đọc.
7. Đánh giá nhu cầu tổng số trước khi chọn Page hoặc Slice.
8. Ghi rõ những metric chưa đo được và điều kiện cache, dữ liệu, mức đồng thời.

Một đánh giá hiệu năng có ích cần trả lời đồng thời: ứng dụng tương tác với store bao nhiêu lần, store và mapper xử lý bao nhiêu dữ liệu, và bao nhiêu byte thực sự đi qua các ranh giới. Số lần gọi repository chỉ là một phần của bức tranh đó.
