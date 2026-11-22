# Kiểm tra cải tiến bằng bằng chứng trước và sau

Một nhóm phát triển thấy API liệt kê đơn hàng trả kết quả chậm và quyết định “tối ưu truy vấn”. Sau khi sửa, một lần chạy trên máy cá nhân cho kết quả 120 ms thay vì 400 ms. Nhóm kết luận hiệu năng đã tăng hơn ba lần. Nhưng lần chạy đầu có thể vừa khởi động JVM, lần sau được hưởng cache; dữ liệu truy vấn có thể khác, số người dùng đồng thời khác hoặc phép đo chỉ tính thời gian ở controller mà bỏ qua bước serialize.

**Một cải tiến hiệu năng chỉ đáng tin khi ta chứng minh được điều gì đã thay đổi, đo trong điều kiện có thể so sánh và xác nhận hành vi vẫn đúng.** Đôi khi mã mới nhanh hơn nhưng tiêu tốn nhiều bộ nhớ hơn, làm tăng lỗi dưới tải, hoặc chỉ cải thiện một phép tính rất nhỏ trong khi phần lớn độ trễ đến từ database.

Bài học thuộc chương **Hiệu năng và tài nguyên** của module `CODE_QUALITY_FUNDAMENTALS`, nơi chất lượng mã được xem xét trên ba mục tiêu: **đáng tin cậy, dễ hiểu và dễ thay đổi**. Việc đo lường trước và sau giúp lựa chọn cải tiến dựa trên bằng chứng, phát hiện đánh đổi và tránh duy trì các tối ưu hóa phức tạp mà lợi ích không rõ ràng.

Sau bài học, bạn có thể:

- Viết giả thuyết hiệu năng cụ thể và định nghĩa điều kiện thành công trước khi sửa mã.
- Chọn thước đo đúng cho thời gian phản hồi, thông lượng, CPU, bộ nhớ, I/O, GC và mức sử dụng phụ thuộc.
- Thu thập số liệu **baseline** có thể lặp lại, thay đổi một nguyên nhân có chủ đích và đo lại bằng cùng phương pháp.
- Phân biệt cải thiện thật với sai khác do cache, JIT, dữ liệu, môi trường hoặc tải.
- Dùng ví dụ Java để phát hiện truy vấn N+1, giảm số lần truy cập database và kiểm chứng hành vi.
- Nhận biết giới hạn của microbenchmark, unit test và load test; kết hợp chúng khi phù hợp.
- Quyết định giữ, điều chỉnh hoặc hoàn tác một tối ưu hóa dựa trên lợi ích, rủi ro và chi phí bảo trì.

## 1. “Nhanh hơn” là một kết luận cần điều kiện

Tuyên bố “phiên bản B nhanh hơn phiên bản A” thiếu thông tin nếu không trả lời:

1. **Nhanh hơn ở thao tác nào?** Một phép tìm kiếm trong bộ nhớ, API HTTP, tác vụ xuất báo cáo hay toàn bộ hành trình người dùng?
2. **Với dữ liệu và tải nào?** 100 bản ghi hay 1 triệu bản ghi, một request đơn lẻ hay hàng trăm request mỗi giây?
3. **Theo thước đo nào?** Trung vị độ trễ, p95, thông lượng cực đại, CPU hoặc thời gian batch hoàn tất?
4. **Khác biệt lớn tới mức nào?** 1 ms, 100 ms hay 30% ở p95?
5. **Có giữ đúng hành vi không?** Kết quả, thứ tự, quyền truy cập, giao dịch và cách xử lý lỗi có tương đương?
6. **Cái giá là gì?** Bộ nhớ, số kết nối, độ phức tạp mã, tiền hạ tầng hay độ ổn định dưới tải?

Cùng một thay đổi có thể cải thiện một chỉ số và làm xấu chỉ số khác. Ví dụ cache giảm số truy vấn nhưng sử dụng thêm RAM và có nguy cơ trả dữ liệu cũ. Batch request giảm số lần gọi mạng nhưng có thể tạo response lớn và tăng thời gian chờ của từng phần tử.

Đừng bắt đầu bằng tên giải pháp như “phải thêm cache” hay “phải dùng parallel stream”. Hãy bắt đầu bằng **triệu chứng có thể đo** và một giả thuyết có khả năng bị kiểm chứng là sai.

## 2. Đặt giả thuyết và tiêu chí trước khi tối ưu

Giả sử API `GET /orders?customerId=...` có p95 khoảng 700 ms dưới tải dự kiến. Tracing cho thấy phần lớn thời gian dùng ở việc lấy mặt hàng của từng đơn hàng.

Một giả thuyết tốt:

> Khi một trang có 100 đơn hàng, mỗi đơn đang tạo một truy vấn lấy mặt hàng riêng. Nếu gom phần lấy mặt hàng thành một truy vấn theo danh sách ID, số lượt truy vấn thường giảm từ 101 xuống 2 và p95 của API có thể giảm, miễn là dữ liệu trả về và thứ tự vẫn tương đương.

Đây là **dự đoán**, chưa phải kết quả đã đo. Nó nêu được nguyên nhân, thay đổi dự định và bằng chứng cần tìm.

Có thể đặt một tiêu chí chấp nhận minh họa:

- Dưới workload 40 request/giây trên cùng tập dữ liệu, p95 phải giảm đáng kể và đạt mục tiêu đã thống nhất.
- Số truy vấn lấy dữ liệu cho mỗi trang 100 đơn giảm theo kỳ vọng.
- Không tăng tỷ lệ lỗi và không làm xấu đáng kể p99 hay mức tiêu thụ bộ nhớ.
- Kết quả đơn hàng, mặt hàng, thứ tự và quyền truy cập phải giữ nguyên.

Cần thống nhất **mức thay đổi có ý nghĩa thực tế**. Giảm 2 ms ở một API vốn mất 1 giây có thể chưa đáng tạo thêm bộ nhớ và cấu trúc. Ngược lại, giảm 2 ms cho một bước được gọi hàng triệu lần mỗi phút có thể rất có giá trị.

### Phân biệt mục tiêu với số đo

| Loại thông tin | Ví dụ | Vai trò |
| --- | --- | --- |
| Mục tiêu nghiệp vụ | 95% request trong tải mục tiêu hoàn tất dưới 300 ms | Xác định chất lượng người dùng cần |
| Giả thuyết kỹ thuật | Giảm 101 truy vấn xuống 2 bằng batch fetch | Giải thích vì sao thay đổi có thể có ích |
| Chỉ số quan sát | p50, p95, p99, query count, database CPU | Kiểm chứng giả thuyết và đánh đổi |
| Điều kiện so sánh | Cùng dữ liệu, tải, phiên bản JVM, tài nguyên | Giúp kết quả có ý nghĩa |
| Hàng rào an toàn | Không sai dữ liệu, không tăng lỗi hoặc OOM | Ngăn cải tiến hiệu năng phá chất lượng khác |

Không nên đưa con số mục tiêu của ví dụ thành chuẩn cho mọi hệ thống. Độ trễ chấp nhận được của API tương tác khác một công việc tổng hợp dữ liệu chạy nền.

## 3. Chọn đúng chỉ số cho loại hiệu năng đang xét

### Độ trễ và phân vị

**Latency** là khoảng thời gian một thao tác mất để hoàn tất, ví dụ từ lúc server nhận request đến lúc gửi xong response theo điểm đo đã định. Nếu đo từ client, độ trễ còn bao gồm một phần mạng và các tầng trung gian.

- `p50`: khoảng 50% các quan sát có độ trễ không lớn hơn giá trị phân vị này.
- `p95`: khoảng 95% các quan sát không lớn hơn mức này; hữu ích để thấy trải nghiệm nhóm request chậm.
- `p99`: cho biết phần đuôi chậm hơn nữa, nhưng có thể biến động mạnh khi số mẫu ít.

**Trung bình không thay thế được phân vị.** Một số request rất chậm có thể gây ảnh hưởng lớn cho người dùng dù trung bình trông ổn.

Không so sánh p95 từ 50 request ở bản cũ với p95 từ 100.000 request ở bản mới mà bỏ qua sai khác về độ tin cậy và mẫu tải. Cũng không lấy trung bình số học của p95 theo từng phút rồi gọi đó là p95 của toàn bộ request; phân vị cần được tính từ phân phối hoặc histogram có thể gộp đúng cách.

### Thông lượng và mức bão hòa

**Throughput** là số công việc hoàn tất trong một đơn vị thời gian: request/giây, bản ghi/phút hay job/giờ. **Saturation** là mức tài nguyên đang tiệm cận giới hạn: CPU bận, connection pool chờ, hàng đợi dài hoặc thread bị chặn.

Một thay đổi có thể làm p95 tốt hơn ở mức 10 request/giây nhưng không giúp hệ thống chịu được 200 request/giây. Ngược lại, tăng song song có thể nâng thông lượng tổng nhưng tăng độ trễ của một request dưới mức tải cao.

### Tài nguyên và độ tin cậy

| Chỉ số | Khi nào quan trọng | Cần tránh hiểu sai |
| --- | --- | --- |
| p50/p95/p99 latency | API tương tác, trải nghiệm người dùng | Phải biết điểm bắt đầu/kết thúc phép đo |
| Throughput | Khả năng phục vụ tổng | Không đánh đồng “server trả nhiều hơn” với “từng người nhanh hơn” |
| CPU time/utilization | Tối ưu tính toán, tải CPU | CPU thấp có thể vì thread đang chờ I/O |
| Allocation rate, heap, GC pauses | Áp lực bộ nhớ, thời gian dừng GC | Heap thấp không có nghĩa phân bổ ít |
| Số query, thời gian SQL, connection wait | API phụ thuộc database | Ít query hơn chưa chắc tổng SQL nhanh hơn |
| Network calls/bytes | Chi phí kết nối, gọi dịch vụ ngoài | Gọi ít lần có thể trả payload lớn hơn |
| Queue depth, active workers | Tác vụ nền và tải đồng thời | Queue rỗng có thể do từ chối request |
| Tỷ lệ lỗi và timeout | Độ tin cậy dưới tải | Nhanh hơn vì bỏ qua công việc hoặc trả lỗi là kết quả sai |

Để chọn chỉ số, hỏi “nút thắt nào đang giới hạn yêu cầu?” trước khi quyết định dùng profiler CPU, DB query logs, tracing hay load test.

## 4. Xây dựng baseline trước khi sửa mã

**Baseline** là bộ số đo của phiên bản hiện tại trong điều kiện được mô tả rõ. Nếu không ghi baseline, sau khi sửa rất dễ so sánh với trí nhớ hoặc với một lần chạy ngẫu nhiên.

Một baseline tối thiểu nên ghi:

- **Phiên bản:** commit hoặc build ID đang chạy, cấu hình và cách khởi động.
- **Môi trường:** CPU, bộ nhớ, JVM/JDK, pool kết nối, database và các phụ thuộc liên quan.
- **Tập dữ liệu:** số đơn hàng, mặt hàng mỗi đơn, phân bố kích thước, chỉ mục và trạng thái cache.
- **Workload:** tỷ lệ các loại request, tốc độ đến, số kết nối/luồng client và thời lượng đo.
- **Cách đo:** điểm bắt đầu/kết thúc latency, cách thu histogram, công cụ và thời điểm thu.
- **Kết quả:** latency, throughput, lỗi và tài nguyên trên nhiều lần chạy.

Nếu một thay đổi được thực hiện trên cùng máy, hãy cố giữ các điều kiện khác ổn định. Nếu cần đổi môi trường (ví dụ nâng JDK hoặc tăng số CPU), coi đó là một yếu tố thay đổi riêng và không quy toàn bộ chênh lệch cho bản sửa thuật toán.

### Các loại workload cần phân biệt

Một tập dữ liệu “100 đơn hàng” chưa đủ đại diện. Có thể cần kiểm tra:

- **Trường hợp điển hình:** trang 20–100 đơn, mỗi đơn có vài mặt hàng.
- **Trường hợp nặng hợp lệ:** nhiều mặt hàng, nhiều dòng dữ liệu hoặc bộ lọc khó.
- **Trường hợp rỗng:** không có đơn, không có mặt hàng; tránh thêm query thừa.
- **Tải đồng thời:** nhiều client gọi cùng lúc, có thể cùng dùng một pool.
- **Điều kiện lạnh và ấm:** cache/bộ nhớ/JIT chưa được làm nóng so với trạng thái ổn định.

Không nên chọn dữ liệu nhỏ nhất chỉ vì đo dễ. Một tối ưu hóa chỉ có lợi ở dữ liệu rất lớn cần được đánh giá cùng chi phí ở trường hợp thường xuyên hơn.

## 5. Tình huống Java: phát hiện truy vấn N+1

Giả sử mỗi yêu cầu trả một trang đơn hàng và danh sách mặt hàng của từng đơn. Repository cung cấp các thao tác sau:

```java
import java.util.List;

record Order(long id, String customerId) {}
record OrderItem(long id, long orderId, String sku, int quantity) {}
record OrderView(Order order, List<OrderItem> items) {}

interface OrderRepository {
    List<Order> findPageByCustomer(String customerId, int pageSize);
    List<OrderItem> findItemsForOrder(long orderId);
    List<OrderItem> findItemsForOrders(List<Long> orderIds);
}
```

Trong phiên bản đầu, code duyệt từng đơn để lấy mặt hàng:

```java
final class OrderReader {
    private final OrderRepository repository;

    OrderReader(OrderRepository repository) {
        this.repository = repository;
    }

    List<OrderView> loadBefore(String customerId, int pageSize) {
        List<Order> orders =
                repository.findPageByCustomer(customerId, pageSize);

        return orders.stream()
                .map(order -> new OrderView(
                        order,
                        repository.findItemsForOrder(order.id())))
                .toList();
    }
}
```

Nếu `findPageByCustomer` thực hiện một query và mỗi lần `findItemsForOrder` thực hiện thêm một query, một trang có `N` đơn hàng cần khoảng `1 + N` lần truy vấn. Với `N = 100`, đó là **101 query** theo mô hình giả định.

Vấn đề này thường gọi là **N+1 query**. Dưới tải, các chuyến đi qua mạng tới database, việc mượn connection và chi phí xử lý truy vấn có thể cộng dồn.

Nhưng **không được kết luận N+1 chỉ từ vòng lặp**. Repository có thể cache, dùng batch fetch hoặc ORM có cơ chế tải khác. Trước khi sửa, cần đo số statement và thời gian SQL thực sự tại ranh giới database.

### Vì sao chỉ nhìn thời gian controller có thể bỏ sót nguyên nhân?

Giả sử tracing cho thấy:

```text
HTTP request:             710 ms
  ├─ xác thực/quyền:       15 ms
  ├─ truy vấn đơn hàng:    35 ms
  ├─ lặp lấy item:        580 ms
  ├─ tạo DTO/serialize:   45 ms
  └─ phần còn lại:        35 ms
```

Các con số này **chỉ là minh họa để đọc trace**, không phải kết quả của một hệ thống đã đo. Chúng gợi ý phần lấy item có thể là điểm đáng tối ưu, nhưng vẫn phải xác nhận trace bao gồm những khoảng thời gian nào và có chồng lấn khi xử lý bất đồng bộ hay không.

## 6. Phiên bản cải tiến: lấy dữ liệu theo lô và giữ nguyên hành vi

Một hướng thay đổi là lấy trang đơn hàng trước, sau đó truy vấn danh sách mặt hàng cho **tập ID của trang đó**:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

final class BatchedOrderReader {
    private final OrderRepository repository;

    BatchedOrderReader(OrderRepository repository) {
        this.repository = repository;
    }

    List<OrderView> loadAfter(String customerId, int pageSize) {
        List<Order> orders =
                repository.findPageByCustomer(customerId, pageSize);

        if (orders.isEmpty()) {
            return List.of();
        }

        List<Long> orderIds = orders.stream()
                .map(Order::id)
                .toList();

        Map<Long, List<OrderItem>> itemsByOrder =
                repository.findItemsForOrders(orderIds).stream()
                        .collect(Collectors.groupingBy(OrderItem::orderId));

        return orders.stream()
                .map(order -> new OrderView(
                        order,
                        List.copyOf(itemsByOrder.getOrDefault(
                                order.id(), List.of()))))
                .toList();
    }
}
```

Nếu repository thực hiện **một query cho trang** và **một query cho tất cả mặt hàng**, số query theo giả định giảm từ `1 + N` còn `2` khi trang có dữ liệu. Với trang rỗng, chỉ còn query lấy trang, không gọi truy vấn mặt hàng.

Tác dụng cụ thể:

1. Giảm số lần gọi qua ranh giới ứng dụng–database.
2. Tập hợp item theo `orderId` trong một `Map` để dựng kết quả nhanh hơn.
3. Giữ thứ tự đơn hàng theo danh sách `orders` đã lấy.
4. Trả danh sách item rỗng cho đơn không có mặt hàng thay vì `null`.

**Không nên dùng số query làm đại diện duy nhất cho hiệu năng.** Một truy vấn `IN` lớn có thể tốn tài nguyên, trả nhiều dòng và làm tăng bộ nhớ Java. Trang cần giới hạn kích thước; repository có thể phải chia batch theo giới hạn tham số của database. Cũng cần chỉ định thứ tự item trong SQL nếu giao diện hoặc hợp đồng yêu cầu item có thứ tự ổn định.

### Ranh giới đúng của thay đổi

Các phương thức repository thực tế phải dùng **tham số có bind**, không nối trực tiếp chuỗi từ client vào SQL. Truy vấn batch phải tiếp tục áp kiểm tra phạm vi dữ liệu/quyền truy cập như bản cũ. Nếu dữ liệu bị chỉnh đồng thời giữa hai query, cần xem xét transaction, mức cô lập và kỳ vọng nhất quán của API.

`List.copyOf` tạo danh sách không thể chỉnh sửa qua API, khác với một repository trước đây có thể trả danh sách mutable. Nếu khả năng chỉnh sửa là phần hợp đồng công khai, phải xem xét tương thích. Mã chỉ nhanh hơn mà thay đổi hành vi hoặc quyền truy cập là **một thay đổi chưa đạt yêu cầu**.

## 7. Kiểm tra tính đúng trước khi so sánh hiệu năng

Một test theo hành vi có thể xác nhận hai phiên bản tạo cùng kết quả trong tình huống được kiểm soát. Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;

class OrderReaderTest {
    static final class FakeRepository implements OrderRepository {
        int singleItemCalls;
        int batchItemCalls;

        private final List<Order> orders = List.of(
                new Order(1L, "C-1"),
                new Order(2L, "C-1"));

        private final List<OrderItem> items = List.of(
                new OrderItem(10L, 1L, "SKU-A", 2),
                new OrderItem(11L, 1L, "SKU-B", 1));

        @Override
        public List<Order> findPageByCustomer(
                String customerId, int pageSize) {
            return orders.stream().limit(pageSize).toList();
        }

        @Override
        public List<OrderItem> findItemsForOrder(long orderId) {
            singleItemCalls++;
            return items.stream()
                    .filter(item -> item.orderId() == orderId)
                    .toList();
        }

        @Override
        public List<OrderItem> findItemsForOrders(List<Long> orderIds) {
            batchItemCalls++;
            return items.stream()
                    .filter(item -> orderIds.contains(item.orderId()))
                    .toList();
        }
    }

    @Test
    void batchVersionPreservesOrderAndItemContent() {
        FakeRepository beforeRepo = new FakeRepository();
        FakeRepository afterRepo = new FakeRepository();

        List<OrderView> before =
                new OrderReader(beforeRepo).loadBefore("C-1", 100);
        List<OrderView> after =
                new BatchedOrderReader(afterRepo).loadAfter("C-1", 100);

        assertEquals(before, after);
        assertEquals(2, beforeRepo.singleItemCalls);
        assertEquals(1, afterRepo.batchItemCalls);
        assertTrue(after.get(1).items().isEmpty());
    }
}
```

Test này chỉ cho thấy **tính tương đương trên bộ dữ liệu giả** và sự khác biệt trong số lời gọi repository. Nó **không phải phép đo thời gian**, cũng không chứng minh bản triển khai SQL thật chỉ thực hiện đúng hai query. Muốn xác nhận SQL, cần integration test với database hoặc bộ đo số statement ở tầng JDBC/ORM.

Bổ sung các trường hợp quan trọng: trang rỗng; nhiều item/trùng SKU; item cần thứ tự; trang có giới hạn; dữ liệu nhiều tenant; kết quả dưới cập nhật đồng thời và lỗi database. Cần kiểm tra cả response HTTP nếu API có hợp đồng serialization hoặc phân trang.

Đặt việc xác nhận hành vi **trước khi tuyên bố cải tiến hiệu năng**. Mã trả thiếu dữ liệu thường nhanh, nhưng không được coi là tối ưu hóa hợp lệ.

## 8. Thiết kế thí nghiệm trước–sau công bằng

Một quy trình thực tế có thể đi theo thứ tự:

### Bước 1: Chọn một câu hỏi đo được

Ví dụ: “Batch fetch có giảm p95 của API liệt kê trang 100 đơn ở mức 40 request/giây mà không tăng tỷ lệ lỗi không?”

Không trộn cùng lúc việc thay query, nâng phiên bản JVM, đổi connection pool và mở thêm instance. Nếu thay nhiều yếu tố, kết quả khó quy về một nguyên nhân.

### Bước 2: Chốt phiên bản và dữ liệu

Lưu commit/build của hai phiên bản, cấu hình, schema và snapshot dữ liệu thử. Thống nhất tỷ lệ trang rỗng, trang đủ 100 đơn và số item mỗi đơn. Tránh thay dữ liệu giữa lúc chạy nếu mục tiêu là so sánh thuật toán trên cùng đầu vào.

### Bước 3: Giữ môi trường và workload có thể so sánh

Sử dụng cùng giới hạn CPU/RAM, JDK, pool kết nối, chỉ mục và database. Nếu hệ thống tự co giãn hoặc có dịch vụ dùng chung, ghi nhận các tác động này. Khởi tạo load generator với **tốc độ request đến đã xác định**, không chỉ “chạy càng nhanh càng tốt” nếu mục tiêu là so độ trễ tại cùng tải.

### Bước 4: Làm nóng và đo nhiều lần

Java có JIT compiler, cơ chế class loading, cache và GC. Một phép đo ngay khi vừa khởi động có thể phản ánh khởi động lạnh nhiều hơn hiệu năng ổn định. Hãy ghi rõ phần warm-up, khoảng đo và trạng thái cache cần kiểm tra.

Chạy mỗi phiên bản nhiều lần trong điều kiện tương đương. Có thể xen kẽ thứ tự A–B–A/B khi phù hợp để phát hiện sự thay đổi do môi trường theo thời gian. Đừng chỉ chọn lần chạy đẹp nhất.

### Bước 5: Thu số liệu ở nhiều tầng

Cùng một lần đo nên thu tối thiểu:

- Latency p50/p95/p99 và phân phối theo route/loại request.
- RPS hoàn tất, mã phản hồi, timeout và tỷ lệ lỗi.
- Số SQL statement, tổng thời gian SQL, connection wait.
- CPU, heap/allocation rate, GC, queue hoặc thread nếu có liên quan.

Mỗi chỉ số cần được thu **cùng khoảng thời gian** với workload để có thể diễn giải mối liên hệ.

### Bước 6: Kiểm tra khác biệt và tính ổn định

So sánh mức chênh lệch, độ biến động giữa các lần chạy và xem có hồi quy ở trường hợp nào không. Một cải thiện p50 nhưng p99 xấu đi có thể không đạt yêu cầu nếu người dùng nhạy với độ trễ đuôi.

### Bước 7: Quyết định và lưu bằng chứng

Ghi lại kết quả, điều kiện thử, mã nguồn thay đổi, các giới hạn chưa đo và lý do quyết định giữ hay không giữ giải pháp. Việc này giúp người bảo trì sau này hiểu **vì sao cấu trúc hiện tại tồn tại**.

## 9. Ví dụ đọc bảng số liệu trước và sau

Bảng sau là **số liệu hoàn toàn giả định để luyện cách phân tích**, không phải kết quả đo từ chương trình Java ở trên.

Giả sử mỗi phiên bản được chạy 5 lần; mỗi lần warm-up 5 phút, đo 10 phút, với cùng dữ liệu và tải tạo 40 request/giây. Bảng lấy kết quả điển hình đã tổng hợp theo cùng quy tắc cho cả hai phiên bản.

| Chỉ số tại cùng workload | Trước (A) | Sau (B) | Diễn giải |
| --- | ---: | ---: | --- |
| Latency p50 | 170 ms | 90 ms | Request điển hình hoàn tất nhanh hơn |
| Latency p95 | 710 ms | 240 ms | Nhóm request chậm cải thiện rõ |
| Latency p99 | 1.300 ms | 420 ms | Phần đuôi độ trễ cũng cải thiện |
| Query mỗi trang 100 đơn | 101 | 2 | Khớp giả thuyết nếu không có cache/batch ẩn |
| DB CPU utilization | 65% | 46% | Giảm tải database tại điều kiện thử |
| Allocation/request | 1,4 MiB | 1,8 MiB | Chi phí cấp phát tăng, cần xem lý do |
| Tỷ lệ lỗi | 0,1% | 0,1% | Không thấy tăng trong bài đo giả định |

Với p95, mức giảm tuyệt đối là `710 − 240 = 470 ms`. Mức giảm tương đối:

\[
\frac{710-240}{710}\times100\%\approx66{,}2\%.
\]

Đây là cải thiện có ý nghĩa **nếu** phương pháp đo, tập dữ liệu và tải thực sự tương đương. Cùng lúc, cấp phát mỗi request tăng từ 1,4 lên 1,8 MiB. Có thể bản batch tạo thêm danh sách và map trong bộ nhớ; cần kiểm tra xem áp lực GC hoặc bộ nhớ có trở nên đáng ngại ở tải cao hơn không.

Không nên viết “cải thiện 66,2% hiệu năng toàn hệ thống”. Chỉ số trên nói rõ **p95 của API tại workload đã thử giảm khoảng 66,2%**. Nó không chứng minh throughput cực đại tăng cùng tỷ lệ, không bảo đảm trên tập dữ liệu khác và không đại diện cho mọi endpoint.

### Hai dấu hiệu cần điều tra trước khi kết luận

**Một:** số query giảm như kỳ vọng, nhưng p95 không giảm. Khi đó có thể vấn đề nằm ở serialize, locking, connection, network hoặc batch query quá nặng. Hãy tìm nút thắt mới thay vì khẳng định tối ưu đã thành công chỉ vì ít query.

**Hai:** p95 giảm nhưng allocation tăng mạnh và p99 xấu đi ở mức 200 request/giây. Có thể chiến lược batch đang tiêu nhiều bộ nhớ, gây GC hoặc bão hòa. Cần so sánh thêm ở các mức tải khác trước khi chọn triển khai sản xuất.

## 10. Chênh lệch quan sát được có phải cải thiện thật?

Các phép đo hiệu năng có nhiễu. Một số nguồn thường gặp:

- **JIT và class loading:** mã Java ban đầu chưa được tối ưu hóa giống lúc chạy ổn định.
- **GC:** thời điểm và số lần dừng khác nhau giữa các lượt đo.
- **Cache:** bộ nhớ ứng dụng, ORM, query cache, buffer cache database, cache hệ điều hành.
- **Dữ liệu:** số record, phân bố giá trị, mức phân mảnh và kế hoạch truy vấn thay đổi.
- **Nền hệ thống:** tiến trình khác chiếm CPU, disk, network hoặc tài nguyên cloud dùng chung.
- **Tải:** tỷ lệ request và số lượng client thực tế khác nhau.
- **Công cụ đo:** sampling, overhead của profiler, lỗi đồng hồ và cách tính phân vị.

Một khác biệt nhỏ hơn độ dao động giữa các lần chạy chưa đủ để kết luận. Có thể báo cáo từng lần đo, trung vị của các lần chạy, khoảng giá trị quan sát được và khi phù hợp dùng khoảng tin cậy hoặc kỹ thuật thống kê tương ứng.

Ví dụ giả định:

```text
p95 (ms) — năm lần chạy trên cùng điều kiện

A: 704, 718, 690, 713, 709
B: 236, 245, 240, 251, 238
```

Hai nhóm rõ ràng khác nhau hơn mức dao động bên trong từng nhóm, nhưng vẫn cần xác nhận cùng cách thu mẫu và tránh sự khác biệt môi trường có hệ thống. Với thay đổi chỉ từ 300 ms xuống 297 ms trong khi mỗi lần chạy dao động ±20 ms, bằng chứng có thể chưa đủ.

**Không biến tương quan thành nhân quả** chỉ bằng việc thấy một biểu đồ đi xuống. Một phép đo đáng tin cần gắn khác biệt với thay đổi đang thử, trong điều kiện đủ kiểm soát và có thể lặp lại.

## 11. Microbenchmark với JMH: đo một thuật toán trong bộ nhớ

Khi câu hỏi là “hai thuật toán Java có chi phí khác nhau thế nào theo kích thước đầu vào?”, một microbenchmark phù hợp hơn việc bấm đồng hồ quanh một lần gọi.

Ví dụ so sánh việc tìm ID trùng bằng cách dò tuyến tính nhiều lần và bằng cách xây `HashSet`. Cả hai phải làm **cùng một công việc**; bản dùng set cần tính cả chi phí tạo set nếu trong sản phẩm set cũng được tạo mỗi lần gọi.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class MembershipBenchmark {
    @Param({"100", "1000"})
    public int size;

    private List<String> requestedIds;
    private List<String> allowedIds;

    @Setup(Level.Trial)
    public void setup() {
        requestedIds = new ArrayList<>();
        allowedIds = new ArrayList<>();

        for (int i = 0; i < size; i++) {
            requestedIds.add("ID-" + i);
            if (i % 2 == 0) {
                allowedIds.add("ID-" + i);
            }
        }
    }

    @Benchmark
    public int linearSearch() {
        int matches = 0;
        for (String requested : requestedIds) {
            if (allowedIds.contains(requested)) {
                matches++;
            }
        }
        return matches;
    }

    @Benchmark
    public int hashSetSearch() {
        Set<String> lookup = new HashSet<>(allowedIds);
        int matches = 0;
        for (String requested : requestedIds) {
            if (lookup.contains(requested)) {
                matches++;
            }
        }
        return matches;
    }
}
```

Đây là **mẫu benchmark JMH cần dependency và runner JMH của dự án**; đoạn mã không tự chạy chỉ bằng `java MembershipBenchmark.java`. Khi thực hiện, cấu hình warm-up, các vòng đo, fork JVM và tham số benchmark phù hợp. Không dùng kết quả của một lần chạy để kết luận.

Cả hai phương thức trả số lượng ID được chấp nhận, nên có thể kiểm tra chúng cho cùng kết quả trước khi đo. JMH xử lý nhiều cạm bẫy của phép đo JVM như khởi động, lặp lại và việc compiler loại bỏ công việc không quan sát được tốt hơn đo thủ công một lần bằng `System.nanoTime()`.

### Những điều microbenchmark không thể trả lời

JMH không cho biết API thực dưới tải có nhanh hơn không nếu thời gian chủ yếu nằm ở database, mạng hoặc serialization. Mẫu kiểm tra membership trong bộ nhớ cũng có thể nhanh hơn nhưng tiêu thêm bộ nhớ cho set. Kết luận cần được xác thực ở cấp cao hơn, gần với workload sản xuất.

Một thay đổi nhỏ có lợi trong `@Benchmark` vẫn có thể không cải thiện độ trễ đầu cuối. Hãy xác định **tỷ lệ thời gian** mà phần đó chiếm trước khi dành nhiều công tối ưu.

## 12. Phân tích nút thắt trước khi chọn giải pháp

Tối ưu phần không chiếm nhiều thời gian thường cho lợi ích hạn chế. Nếu một request mất 1 giây, trong đó 900 ms đợi database và 10 ms tính toán Java, làm phép tính nhanh gấp đôi chỉ tiết kiệm tối đa khoảng 5 ms nếu mọi phần khác giữ nguyên.

Có thể dùng một sơ đồ lập luận:

```text
Triệu chứng: p95 cao
        |
        v
Quan sát trace + metrics + profile
        |
        +-- Chủ yếu chờ database? -> query plan, N+1, index, lock
        |
        +-- Chủ yếu CPU? ---------> algorithm, profiler, JMH nếu cần
        |
        +-- Chủ yếu GC/bộ nhớ? ---> allocation, object lifetime, heap
        |
        +-- Chủ yếu chờ mạng? ----> số call, payload, timeout, batching
        |
        +-- Chủ yếu chờ queue? ---> concurrency, capacity, backpressure
        |
        v
Đặt giả thuyết cụ thể -> thay đổi -> đo lại
```

Với một phép đo, cần phân biệt **wall-clock time** (thời gian trôi qua) với **CPU time** (thời gian CPU thực thi). Một lời gọi HTTP có thể mất 500 ms wall-clock nhưng tiêu rất ít CPU vì thread chủ yếu chờ.

Số lượng request đồng thời cũng thay đổi hình dạng nút thắt. Ở tải thấp, thao tác chậm do latency từng lời gọi; ở tải cao, connection pool và hàng đợi có thể trở thành nguyên nhân lớn nhất.

### Chú ý giới hạn lợi ích

Nếu phần cần cải tiến chỉ chiếm 20% tổng thời gian, dù làm nó nhanh vô hạn, tổng thời gian lý thuyết vẫn chỉ có thể giảm tối đa 20% khi mọi thứ khác giữ nguyên. Đây là trực giác của **định luật Amdahl**, hữu ích để kiểm tra liệu mục tiêu cải tiến có thực tế hay không.

Tỷ lệ thời gian lấy từ trace chỉ là ước lượng cho workload đó; khi thay đổi thuật toán, nút thắt có thể chuyển sang nơi khác. Không nên dùng một tỷ lệ duy nhất để dự đoán mọi mức tải.

## 13. Hiệu năng và tài nguyên thường đánh đổi lẫn nhau

Một phiên bản nhanh hơn có thể dùng nhiều tài nguyên hơn:

- **Cache:** giảm độ trễ đọc nhưng tăng RAM, chi phí vô hiệu hóa và nguy cơ dữ liệu cũ.
- **Batching:** giảm số lần gọi DB/mạng nhưng tăng lượng dữ liệu giữ trong một lần và có thể tăng thời gian chờ để gom batch.
- **Song song hóa:** giảm thời gian xử lý khi có tài nguyên rảnh, nhưng tăng thread, cạnh tranh và áp lực pool.
- **Tạo index database:** tăng tốc truy vấn đọc nhưng tốn dung lượng và có chi phí ghi/cập nhật.
- **Precompute:** giảm tính toán lúc đọc nhưng tăng chi phí cập nhật và nguy cơ kết quả không đồng bộ.
- **Streaming:** giảm bộ nhớ đỉnh nhưng có thể tăng số thao tác I/O hoặc thời gian xử lý tổng.

Vì vậy, báo cáo chỉ “p95 giảm 60%” là chưa đủ nếu tác vụ mới đòi gấp bốn lần RAM hoặc làm hỏng dữ liệu cạnh tranh.

Một bảng quyết định có thể đặt **lợi ích, chi phí và rủi ro** cạnh nhau:

| Lựa chọn | Lợi ích kỳ vọng | Chi phí/rủi ro cần đo |
| --- | --- | --- |
| Batch fetch item | Ít round trip tới DB | Payload lớn, RAM và query plan |
| Thêm cache theo ID | Ít truy vấn lặp | Memory, invalidation, stale data |
| Tăng thread pool | Có thể tăng throughput khi còn tài nguyên | Context switching, connection pool, queue |
| Dùng thuật toán có cấu trúc dữ liệu tốt hơn | Giảm CPU khi dữ liệu lớn | Allocation và chi phí xây cấu trúc |
| Chuyển báo cáo sang job nền | API trả nhanh, kiểm soát tải | Trạng thái job, queue, lưu trữ, trải nghiệm chờ |

Không tự chọn giải pháp có bảng lợi ích dài nhất; cần số đo trên nhu cầu và môi trường thực.

## 14. Kiểm chứng sau triển khai: canary và quan sát thực tế

Kết quả trên máy thử có thể khác sản xuất do dữ liệu, network, cache, phân bố tải và phụ thuộc ngoài. Với thay đổi ảnh hưởng đáng kể, có thể triển khai theo giai đoạn:

1. **Đặt ngưỡng bảo vệ:** lỗi, timeout, p95/p99, CPU, bộ nhớ, DB load và các chỉ số nghiệp vụ liên quan.
2. **Triển khai canary:** một phần nhỏ lưu lượng dùng phiên bản mới, có khả năng hoàn tác nhanh.
3. **So sánh cùng cửa sổ thời gian:** cân nhắc khác biệt người dùng, request mix và tài nguyên giữa canary/control.
4. **Kiểm tra tính đúng:** không chỉ latency mà cả dữ liệu kết quả, số đơn hoàn tất và lỗi nghiệp vụ.
5. **Tăng dần lưu lượng:** chỉ khi số liệu đủ ổn định; theo dõi trong thời gian đại diện cho chu kỳ tải.
6. **Ghi quyết định:** giữ, điều chỉnh hoặc rollback khi vượt ngưỡng.

Canary hữu ích vì cùng thời điểm giảm ảnh hưởng của một số biến môi trường, nhưng **không tự tạo một thí nghiệm công bằng**. Nếu canary nhận khách hàng ít dữ liệu hơn hoặc được đặt trên máy mạnh hơn, số đo chênh lệch vẫn có thể do khác biệt đó.

Nếu hai phiên bản dùng chung database, một thay đổi có thể ảnh hưởng cả nhóm control. Cần ghi nhận các hiệu ứng liên đới trước khi suy luận nguyên nhân.

### Đo đúng thứ người dùng quan tâm

Giảm latency của một endpoint chưa chắc cải thiện thời gian hoàn tất hành trình người dùng. Ví dụ trang đơn hàng còn phụ thuộc thêm một API báo giá vận chuyển hoặc việc render trên trình duyệt. Có thể cần kết hợp số liệu backend với chỉ số trải nghiệm thực tế.

Tương tự, tăng throughput mà làm tăng tỷ lệ lỗi hoặc giảm độ chính xác của dữ liệu không phải thành công.

## 15. Các cách “tối ưu” dễ gây kết luận sai

**Chỉ đo một lần.** Kết quả chịu ảnh hưởng ngẫu nhiên của JIT, cache, GC và tải nền; cần lặp lại.

**Thay nhiều thứ rồi so sánh.** Nếu vừa thêm cache, đổi SQL và tăng CPU, không thể biết nguyên nhân chính. Tách thay đổi khi có thể.

**So dữ liệu khác nhau.** Bản trước xử lý 1.000 bản ghi, bản sau chỉ xử lý 100 bản ghi thì kết quả không chứng minh mã mới nhanh hơn.

**Lấy thời gian chạy unit test làm benchmark.** Unit test dùng để kiểm tra hành vi; thời gian test còn bị ảnh hưởng fixture, JIT và framework. Dùng phép đo được thiết kế cho hiệu năng.

**Chỉ tối ưu p50.** Nhóm request chậm có thể tệ hơn; cần xem p95/p99 và lỗi phù hợp với mục tiêu.

**Chỉ đếm query hoặc dòng mã.** Query ít hơn có thể nặng hơn; mã ngắn hơn có thể dùng nhiều bộ nhớ hơn.

**Tắt validation, logging quan trọng hoặc cơ chế an toàn để “nhanh hơn”.** Nếu làm thay đổi hợp đồng và rủi ro, đó không phải so sánh tương đương.

**Tăng cache không giới hạn.** Hit rate có thể tăng nhưng bộ nhớ, thời gian GC và rủi ro dữ liệu cũ cũng tăng. Cần quota/TTL/eviction phù hợp.

**So thông lượng ở hai mức tải khác nhau.** Một hệ thống nhận 100 RPS và một hệ thống nhận 50 RPS không thể so trực tiếp độ trễ nếu không nêu rõ tải.

**Bỏ qua chi phí tối ưu hóa trong mã nguồn.** Nếu lợi ích rất nhỏ còn code mới tạo thêm nhiều tầng, cấu hình và trạng thái, tổng chất lượng bảo trì có thể giảm.

**Tin chỉ số giả lập thay cho sản xuất.** Test và benchmark là bằng chứng quan trọng trong ngữ cảnh đã kiểm soát, nhưng không thể đại diện hoàn toàn cho mọi điều kiện thực tế.

## 16. Mẫu báo cáo trước–sau cho một thay đổi

Một báo cáo ngắn nhưng đủ kiểm chứng có thể theo cấu trúc:

```text
Vấn đề:
  GET /orders p95 cao khi trả trang có nhiều đơn hàng.

Giả thuyết:
  Repository gọi một truy vấn items cho mỗi order (N+1).

Thay đổi:
  Tải items theo danh sách order IDs, nhóm kết quả theo orderId.

Điều kiện so sánh:
  Commit A và B; cùng JDK, CPU/RAM, DB snapshot/index.
  Cùng tỷ lệ trang, 40 RPS, warm-up 5 phút, đo 10 phút.
  Mỗi phiên bản chạy 5 lần và lưu kết quả từng lần.

Bằng chứng:
  Query/request: A ... ; B ...
  p50/p95/p99: A ... ; B ...
  Throughput/error: A ... ; B ...
  DB CPU, allocation, GC: A ... ; B ...

Kiểm tra tính đúng:
  Test đơn hàng rỗng, nhiều item, thứ tự, quyền và lỗi DB.
  Không phát hiện khác biệt kết quả ngoài thay đổi có chủ đích.

Giới hạn:
  Chưa kiểm tra tải lớn hơn ... hoặc cấu hình ...
  Cần đo lại khi dữ liệu tăng gấp ...

Quyết định:
  Giữ/điều chỉnh/hoàn tác, kèm lý do và ngưỡng theo dõi.
```

Chỉ điền số sau khi đã thực sự đo. Những dấu `...` trong mẫu là chỗ dành cho dữ liệu thực tế; không nên biến ví dụ giả định thành “bằng chứng” khi chưa có phép đo.

Điểm mạnh của báo cáo là **khả năng tái hiện lập luận**. Người đọc biết thay đổi nào được đo, trên dữ liệu nào, hiệu quả ra sao và giới hạn của kết luận.

## 17. Bài tập tình huống

### Tình huống A: thay vòng lặp bằng parallel stream

Một nhóm chuyển phép biến đổi danh sách sang `parallelStream()`. Trên máy phát triển với 10.000 phần tử, thời gian giảm từ 200 ms còn 120 ms. Nhưng khi chạy cùng nhiều request, CPU gần 100% và p99 tăng.

Hãy viết giả thuyết ban đầu, các chỉ số cần đo ở mức một thao tác và toàn hệ thống, cùng những điều kiện tải phải giữ cố định. Trong trường hợp nào nên giữ cách xử lý tuần tự?

### Tình huống B: thêm cache cho bảng giá

API tính giá gọi dịch vụ phụ thuộc mỗi lần. Sau khi thêm cache, p95 giảm, nhưng một số khách nhìn thấy giá cũ sau khi cập nhật. Nhóm muốn tuyên bố tối ưu hóa thành công.

Hãy xác định hành vi nghiệp vụ bị thay đổi, cách đo cache hit/miss, latency, RAM, stale data và kế hoạch kiểm tra độ mới dữ liệu. Khi nào cache phù hợp với hợp đồng giá?

### Tình huống C: giảm query nhờ batch

API liệt kê đơn trước đây 101 query, bản sau còn 2. Ở trang 10 đơn, latency giảm rõ; ở trang 1.000 đơn, batch query trả lượng item rất lớn và GC tăng.

Hãy đề xuất tập workload để so sánh, giới hạn phân trang, chỉ số bộ nhớ và cách đọc kết quả theo từng loại trang. Nếu không thể nâng `pageSize` tùy ý, ranh giới này nên được thực thi ở đâu?

### Tình huống D: tối ưu hàm tính thuế

Profiler cho thấy hàm tính thuế chiếm 2% tổng CPU và 1% thời gian request. Nhóm dành một tuần viết lại thành phiên bản nhanh gấp ba trong JMH.

Hãy ước lượng mức ảnh hưởng tối đa lên request khi phần còn lại không đổi, rồi nêu những bằng chứng khác cần có để quyết định có đáng tăng độ phức tạp mã hay không.

### Tình huống E: truy vấn nhanh hơn nhưng database lỗi nhiều

Sau khi tạo index, p95 truy vấn đọc giảm, nhưng thời gian ghi và số lần deadlock tăng vào giờ cao điểm. Hãy đánh giá thành công theo toàn bộ workload thay vì riêng truy vấn đọc, đề xuất các chỉ số trước–sau và điều kiện rollback.

### Tình huống F: đo bằng hai môi trường khác nhau

Phiên bản A được đo trên máy 2 CPU với cơ sở dữ liệu chưa warm-up; B trên máy 8 CPU với buffer cache nóng. B nhanh hơn 70%.

Hãy chỉ ra vì sao chưa thể quy kết chênh lệch cho thay đổi mã. Thiết kế lại thí nghiệm, ghi rõ yếu tố nào cần cố định và phép đo nào có thể kiểm tra giả thuyết.

Với mỗi tình huống, trả lời theo chuỗi: **mục tiêu → giả thuyết → baseline → điều kiện thử → bằng chứng trước/sau → tính đúng và đánh đổi → quyết định**.

## 18. Ghi nhớ

Đánh giá cải tiến hiệu năng bằng bằng chứng là một vòng lặp kỹ thuật có thể kiểm chứng:

1. **Quan sát:** xác định người dùng hoặc thành phần nào đang gặp vấn đề, ở workload nào.
2. **Giả thuyết:** nêu nguyên nhân có thể đo và kết quả kỳ vọng.
3. **Baseline:** đo nhiều lần, ghi rõ môi trường, dữ liệu, tải và cách đo.
4. **Thay đổi:** sửa đúng phần liên quan, giữ hành vi nghiệp vụ.
5. **Đo lại:** dùng cùng phương pháp, xem cả latency, thông lượng, lỗi và tài nguyên.
6. **Đánh giá:** phân biệt cải thiện với nhiễu, kiểm tra hồi quy và chi phí bảo trì.
7. **Theo dõi:** xác minh trong điều kiện thực tế, lưu bằng chứng để quyết định sau này.

**Tối ưu hóa tốt là tối ưu hóa có thể giải thích và chứng minh được.** Mã nhanh hơn nhưng khó hiểu, thiếu kiểm chứng hoặc phá hành vi chưa chắc có chất lượng cao hơn. Bằng chứng trước và sau giúp nhóm giữ những cải tiến thực sự có ích, đồng thời tránh tối ưu vì cảm giác hoặc vì một phép đo thiếu kiểm soát.
