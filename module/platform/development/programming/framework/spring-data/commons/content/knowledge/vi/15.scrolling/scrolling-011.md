# Đánh giá scrolling so với phân trang offset trên tập dữ liệu lớn

Một màn hình quản trị cần chuyển tới trang 5 và một job cần đọc hết một triệu bản ghi có thể cùng dùng repository, nhưng có yêu cầu truy cập rất khác nhau. Cơ chế phù hợp cho màn hình chưa chắc phù hợp cho job chạy hàng giờ.

Trong Spring Data Commons, `Pageable`, `Page`, `Slice`, `ScrollPosition` và `Window` cung cấp các abstraction để mô tả những cách truy cập này. Commons định nghĩa hợp đồng; module Spring Data cụ thể chuyển hợp đồng đó thành truy vấn cho kho dữ liệu. Vì vậy, đánh giá hiệu năng phải đi từ nhu cầu sử dụng, kiểu position và truy vấn thực tế, thay vì chỉ nhìn tên kiểu trả về.

Sau bài học này, bạn có thể:

- Phân biệt phân trang offset, offset scrolling và keyset scrolling.
- Giải thích vì sao chi phí đọc một trang sâu có thể tăng mạnh dù kích thước trang không đổi.
- Thiết kế phép so sánh công bằng giữa các cách đọc.
- Đánh giá đồng thời độ trễ, tổng công việc, bộ nhớ và tính nhất quán.
- Chọn hợp đồng repository phù hợp với giao diện, tác vụ xuất dữ liệu và xử lý hàng loạt.

## 1. Xác định đúng các phương án đang so sánh

### 1.1. Phân trang bằng offset

Với số trang bắt đầu từ 0 và kích thước trang `k`, vị trí bắt đầu thường được biểu diễn bằng:

```text
offset = pageNumber × k
```

Ví dụ, trang 900 có kích thước 1.000 tương ứng offset 900.000. Ứng dụng yêu cầu một đoạn trong tập kết quả đã lọc và sắp xếp.

Trong kho quan hệ, SQL minh họa có thể là:

```sql
SELECT id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at ASC, id ASC
LIMIT :batchSize OFFSET :offset;
```

Cú pháp giới hạn và cách thực thi tùy hệ quản trị. Điểm quan trọng là hệ thống cần xác định đoạn sau một số lượng phần tử đã bỏ qua; một index phù hợp không nhất thiết biến việc nhảy qua hàng trăm nghìn phần tử thành thao tác chi phí cố định.

### 1.2. Offset scrolling

Offset scrolling tiếp tục bằng một `OffsetScrollPosition` và nhận từng `Window`. Nó thuận tiện cho vòng lặp đọc tuần tự, nhưng vị trí tiếp tục vẫn dựa trên số lượng phần tử đứng trước.

Đổi kiểu trả về từ `Page<T>` sang `Window<T>` có thể bỏ nhu cầu tổng số bản ghi. Nếu vẫn dùng offset position, chi phí tìm vị trí ở sâu chưa tự biến mất.

### 1.3. Keyset scrolling

Keyset scrolling tiếp tục từ giá trị các khóa tại một ranh giới đã đọc. Với thứ tự:

```text
createdAt ASC, id ASC
```

và ranh giới `(lastCreatedAt, lastId)`, điều kiện tiếp tục về phía sau có dạng:

```text
createdAt > lastCreatedAt
OR (createdAt = lastCreatedAt AND id > lastId)
```

SQL minh họa:

```sql
SELECT id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
       created_at > :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id > :lastId)
  )
ORDER BY created_at ASC, id ASC
LIMIT :batchSize;
```

Bộ khóa mô tả ranh giới theo thứ tự truy vấn. Nó không phải số trang, không phải offset và cũng không chỉ là id nếu thứ tự cần nhiều thuộc tính.

### 1.4. Các abstraction giải quyết những nhu cầu khác nhau

| Hợp đồng | Thông tin kết quả | Cách tiếp tục điển hình | Điểm cần đánh giá |
|---|---|---|---|
| `Page<T>` với `Pageable` | Nội dung, thông tin phân trang và tổng | Số trang hoặc offset | Có thể phát sinh truy vấn đếm, cộng chi phí đọc sâu |
| `Slice<T>` với `Pageable` | Nội dung và thông tin còn đoạn sau | Pageable tiếp theo | Tránh yêu cầu tổng, nhưng vẫn thường dựa trên offset |
| `Window<T>` với offset position | Nội dung, `hasNext`, vị trí tiếp tục | Offset do window cung cấp | Hợp đồng cuộn tuần tự, vẫn chịu đặc tính của offset |
| `Window<T>` với keyset position | Nội dung, `hasNext`, vị trí chứa khóa | Bộ khóa do window cung cấp | Cần thứ tự phù hợp, trích xuất được khóa và hỗ trợ từ module |

`Page` không bắt buộc thực hiện một count query riêng trong mọi lần gọi: hạ tầng có thể suy ra tổng ở một số trường hợp. Ngược lại, đổi sang `Slice` không bảo đảm truy vấn nhanh nếu phần truy xuất dữ liệu chính vẫn đắt.

Không đồng nhất `Window` với keyset. Muốn đánh giá đúng, phải ghi rõ position đầu vào và cơ chế truy vấn của module.

## 2. Tại sao đọc sâu bằng offset có thể tốn kém?

### 2.1. Kích thước phản hồi nhỏ không đồng nghĩa lượng công việc nhỏ

Một truy vấn trả 1.000 dòng ở offset 900.000 có thể phải đi qua khoảng 901.000 mục đủ điều kiện để tìm và trả đoạn yêu cầu. Số dòng ứng dụng nhận chỉ phản ánh đầu ra, chưa phản ánh số mục index hoặc bản ghi kho dữ liệu đã xem xét.

Lượng công việc thực tế còn phụ thuộc:

- Độ chọn lọc của điều kiện lọc.
- Index và quan hệ của index với thứ tự yêu cầu.
- Chi phí đọc bản ghi đầy đủ sau khi tìm được khóa.
- Sort bổ sung, bộ nhớ làm việc và khả năng tràn ra đĩa.
- Join, phép tính, ánh xạ entity và tải quan hệ liên quan.
- Cache, phân vùng, phân mảnh hoặc xử lý phân tán của kho dữ liệu.

Vì thế, câu “offset 900.000 luôn đọc đúng 901.000 dòng vật lý” là quá mạnh. Đây là một mô hình giải thích chi phí thường gặp, không phải cam kết kế hoạch thực thi.

### 2.2. Đọc hết dữ liệu làm chi phí bỏ qua lặp lại

Giả sử có `N` bản ghi, mỗi lần lấy `k` bản ghi và `N = p × k`. Các offset khi đọc hết lần lượt là:

```text
0, k, 2k, ..., (p - 1)k
```

Trong mô hình mỗi lần phải đi qua phần bị bỏ qua, tổng số mục cần đi qua xấp xỉ:

```text
k × (1 + 2 + ... + p)
= k × p × (p + 1) / 2
```

Với một triệu bản ghi, mỗi lần lấy 1.000 bản ghi:

```text
p = 1.000 lần đọc
Tổng công việc theo mô hình = 500.500.000 lượt đi qua mục
```

Con số này là minh họa tính lặp của công việc, không phải kết quả benchmark, số I/O vật lý hay số dòng luôn được tải vào ứng dụng.

Keyset với index thích hợp có thể tìm ranh giới rồi đọc đoạn tiếp theo, giúp tổng lượng dữ liệu phải duyệt gần hơn với lượng kết quả cần xử lý. Tuy nhiên, mỗi truy vấn vẫn có chi phí tìm kiếm, lọc, truyền dữ liệu và ánh xạ; không nên khẳng định mọi truy vấn keyset luôn có độ phức tạp hay độ trễ cố định.

### 2.3. Ba vị trí phải được đo riêng

| Vị trí thử nghiệm | Offset minh họa | Số mục đi qua trong mô hình đơn giản để trả 1.000 dòng |
|---|---:|---:|
| Đầu tập dữ liệu | 0 | 1.000 |
| Giữa tập dữ liệu | 500.000 | 501.000 |
| Cuối tập dữ liệu | 999.000 | 1.000.000 |

Chỉ đo trang đầu thường che mất vấn đề của offset. Ngược lại, chỉ đo một trang rất sâu cũng chưa thể hiện chi phí toàn bộ phiên đọc hoặc sự thuận tiện khi người dùng cần nhảy trang.

## 3. Điều kiện để keyset có cơ hội hoạt động tốt

### 3.1. Thứ tự phải xác định đầy đủ

Nếu nhiều đơn hàng có cùng `createdAt`, chỉ sắp theo thời điểm chưa đủ để xác định một ranh giới duy nhất. Thêm một khóa phân xử, chẳng hạn `id`:

```text
createdAt ASC, id ASC
```

Bộ khóa phải chứa các thành phần mà module cần để tái lập ranh giới. Những module hỗ trợ keyset có thể bổ sung định danh để hoàn thiện thứ tự; khai báo thứ tự tường minh giúp người đọc và người thiết kế index hiểu hợp đồng đang dùng.

Không coi id có khoảng trống là lỗi. Keyset so sánh giá trị theo thứ tự, không cần id liên tục.

### 3.2. Giá trị khóa cần sử dụng được trong so sánh

Khi thiết kế keyset scrolling qua repository, nên dùng các thuộc tính sort không null và kiểm tra yêu cầu cụ thể của module. Null có quy tắc sắp xếp và so sánh khác nhau giữa các kho, nên không thể suy điều kiện tiếp tục chỉ bằng dấu `>` hoặc `<` thông thường.

Các khóa cũng cần giữ đúng kiểu và độ chính xác. Làm tròn timestamp khi lưu cursor có thể làm thay đổi ranh giới; đổi số nguyên lớn sang dạng số không giữ đủ độ chính xác cũng có thể làm sai kết quả.

### 3.3. Projection phải cung cấp khóa cần thiết

Một projection chỉ có `totalAmount` chưa đủ để tạo position cho thứ tự `createdAt, id`. Các thuộc tính cần trích xuất phải hiện diện trong kết quả theo cơ chế mapping của module.

Có thể dùng projection nội bộ gồm khóa và các trường cần xử lý, sau đó ánh xạ sang DTO công khai. Cần đo chi phí của phương án thực tế, vì việc trả entity lớn so với projection nhỏ có thể tạo khác biệt lớn hơn riêng cơ chế tiếp tục.

### 3.4. Index phải phục vụ cả phạm vi lọc và thứ tự

Với truy vấn lọc theo tenant, trạng thái và sắp theo thời điểm, id, một index ứng viên trong kho quan hệ là:

```sql
CREATE INDEX idx_purchase_order_scroll
ON purchase_order (tenant_id, status, created_at, id);
```

Đây là ứng viên để đánh giá, không phải công thức tối ưu cho mọi schema. Phân bố dữ liệu, điều kiện phạm vi, chiều sort, collation, join và các truy vấn khác có thể thay đổi lựa chọn phù hợp.

Cần kiểm tra kế hoạch thực thi cho cả lần đầu lẫn lần tiếp tục. Một biểu thức `OR` đúng về logic chưa bảo đảm bộ tối ưu sẽ chọn đường truy cập tốt nhất.

### 3.5. Hỗ trợ thuộc module kho dữ liệu

Spring Data Commons định nghĩa `KeysetScrollPosition` và `Window`; nó không cung cấp một thuật toán truy vấn áp dụng nguyên vẹn cho mọi store.

Trước khi chọn giải pháp, xác minh trong module và phiên bản dự án:

- Có hỗ trợ scrolling ở loại repository đang dùng không?
- Derived query, query tự khai báo và custom repository có cùng mức hỗ trợ không?
- Kiểu sort, projection và mapping hiện tại có lấy được khóa không?
- Hạ tầng sử dụng keyset predicate, cursor riêng của store hay một cơ chế khác?

Không suy rằng một phương thức trả `Window<T>` tự khai báo đã đủ để framework thực thi đúng cho mọi loại query.

## 4. Ví dụ repository: cùng tập dữ liệu, hai hợp đồng truy cập

Ví dụ sau đặt trong Spring Data JPA, với giả định module và phiên bản đang dùng hỗ trợ scrolling cho derived query bên dưới. Domain `PurchaseOrder` đã được ánh xạ và repository scanning đã được cấu hình.

Các thuộc tính dùng trong ví dụ:

| Thuộc tính | Kiểu Java | Vai trò |
|---|---|---|
| `id` | `Long` | Định danh duy nhất, không null |
| `tenantId` | `String` | Phạm vi tenant |
| `status` | `String` | Bộ lọc nghiệp vụ |
| `createdAt` | `Instant` | Khóa sort không null; ứng dụng giữ ổn định trong phiên đọc |
| `totalAmount` | `BigDecimal` | Dữ liệu cần xử lý |

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    Window<PurchaseOrder>
    findFirst200ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
        String tenantId,
        String status,
        ScrollPosition position
    );
}
```

`JpaRepository` thuộc module JPA; `Page`, `Pageable`, `ScrollPosition` và `Window` là các abstraction dùng chung. Ví dụ này minh họa cách một module cụ thể triển khai những abstraction đó, không khẳng định mọi repository của mọi store hỗ trợ chữ ký tương tự.

### 4.1. Phân trang offset cho một trang cụ thể

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
);

Page<PurchaseOrder> page = repository.findByTenantIdAndStatus(
    tenantId,
    status,
    PageRequest.of(4, 200, sort)
);
```

Đây là trang số 4 theo chỉ số bắt đầu từ 0, tương ứng trang thứ 5 khi hiển thị cho người dùng. Lời gọi phù hợp khi giao diện cần truy cập theo số trang và metadata tổng.

### 4.2. Đọc tuần tự bằng keyset

```java
import java.util.function.Consumer;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

public final class OrderScanner {
    private final OrderRepository repository;

    public OrderScanner(OrderRepository repository) {
        this.repository = repository;
    }

    public void scan(
            String tenantId,
            String status,
            Consumer<PurchaseOrder> process) {

        ScrollPosition position = ScrollPosition.keyset();

        while (true) {
            Window<PurchaseOrder> window = repository
                .findFirst200ByTenantIdAndStatusOrderByCreatedAtAscIdAsc(
                    tenantId,
                    status,
                    position
                );

            if (window.isEmpty()) {
                break;
            }

            for (PurchaseOrder order : window) {
                process.accept(order);
            }

            if (!window.hasNext()) {
                break;
            }

            position = window.positionAt(window.size() - 1);
        }
    }
}
```

Vòng lặp lấy position tại phần tử cuối đã xử lý, giữ nguyên tenant, status và sort. Position là ranh giới loại trừ: lần tiếp tục không bắt đầu lại từ chính phần tử đó theo hợp đồng cuộn tương ứng.

Kiểm tra rỗng trước khi lấy `positionAt`. Không dùng index bằng `window.size()`, và không suy `hasNext` chỉ từ việc số phần tử bằng kích thước giới hạn.

Ví dụ chưa định nghĩa transaction, checkpoint hay khả năng xử lý lại sau lỗi. Những cơ chế đó thuộc thiết kế job và phải được bổ sung theo yêu cầu nghiệp vụ.

### 4.3. So sánh offset scrolling trong module có hỗ trợ

Khi cùng phương thức `Window` hỗ trợ cả hai loại position, có thể bắt đầu một phiên riêng bằng:

```java
ScrollPosition position = ScrollPosition.offset();
```

Sau đó tiếp tục bằng position của window trong chính phiên đó. Không đổi qua lại giữa keyset và offset giữa phiên đọc.

Vị trí offset ban đầu và một offset cụ thể có ý nghĩa khác nhau: dùng factory ban đầu để bắt đầu từ đầu, tránh tự gán một offset rồi vô tình bỏ qua phần tử ranh giới. Khi tiếp tục, ưu tiên position mà `Window` đã tạo.

Cặp so sánh `Window + offset` và `Window + keyset` giúp tách ảnh hưởng của cơ chế tiếp tục khỏi ảnh hưởng của count query trong `Page`.

## 5. Thiết kế một phép đo công bằng

### 5.1. Đặt câu hỏi đo trước khi chạy

Ba câu hỏi sau cần ba cách đo khác nhau:

1. Người dùng mở trang đầu hoặc một trang cụ thể mất bao lâu?
2. Một lần lấy tiếp ở sâu trong tập dữ liệu có độ trễ bao nhiêu?
3. Đọc hết tập dữ liệu cần tổng thời gian và tài nguyên bao nhiêu?

Keyset có lợi thế tự nhiên ở truy cập tiếp nối khi đã có cursor. Nếu người dùng chỉ đưa số trang 900 mà chưa có cursor, ứng dụng phải tìm ranh giới theo một cách khác hoặc đi qua các cửa sổ trước. Không được lấy sẵn cursor miễn phí rồi kết luận keyset cũng đáp ứng nhảy trang với cùng chi phí.

### 5.2. Giữ tương đương các yếu tố chính

| Yếu tố | Cách giữ tương đương |
|---|---|
| Dữ liệu | Cùng tập dữ liệu, phân bố giá trị sort và số bản ghi đủ điều kiện |
| Phạm vi | Cùng tenant, trạng thái và các điều kiện nghiệp vụ |
| Thứ tự | Cùng thuộc tính, chiều sort và khóa phân xử |
| Đầu ra | Cùng entity hoặc cùng projection, cùng trường được tải |
| Kích thước | Cùng giới hạn mỗi lần lấy |
| Hạ tầng | Cùng index, cấu hình kết nối và tài nguyên |
| Xử lý | Cùng công việc nghiệp vụ, hoặc tách riêng thời gian truy xuất |
| Mức đồng thời | Cùng số phiên và cùng tải nền |
| Cache | Phân biệt các kịch bản cache đã ấm và dữ liệu ít được cache |

Nếu một bên trả entity kèm nhiều quan hệ còn bên kia trả ba trường, kết quả đo phản ánh cả chiến lược tải dữ liệu. Nếu một bên chạy count còn bên kia không chạy, cần báo riêng chi phí count.

### 5.3. Chia các nhóm thử nghiệm

Một kế hoạch thực tế có thể gồm:

- Dữ liệu nhỏ để xác nhận hành vi ở quy mô thông thường.
- Dữ liệu lớn, đủ làm lộ chi phí đọc sâu.
- Nhiều bản ghi trùng giá trị sort chính, nhằm kiểm tra khóa phân xử.
- Tenant có ít dữ liệu và tenant có rất nhiều dữ liệu.
- Filter chọn lọc cao và filter chọn lọc thấp.
- Dữ liệu tĩnh để so sánh hiệu năng cơ bản.
- Dữ liệu có thêm, sửa, xóa để đánh giá hành vi dưới tải cập nhật.

Đo nhiều lần, xác định giai đoạn warm-up và ghi rõ cách lấy mẫu. Không dùng một lần gọi duy nhất để kết luận về độ trễ đuôi hoặc khả năng phục vụ đồng thời.

### 5.4. Tách các thành phần chi phí

```text
Thời gian phản hồi một lần lấy
  = đợi tài nguyên/kết nối
  + thực thi truy vấn nội dung
  + truy vấn đếm nếu có
  + truyền dữ liệu
  + ánh xạ kết quả
  + xử lý bổ sung của ứng dụng
```

Tổng thời gian đọc hết còn bao gồm mọi lần lấy và công việc giữa các lần lấy. Nếu xử lý mỗi dòng gọi một dịch vụ chậm, lợi ích giảm thời gian truy vấn có thể nhỏ trong độ trễ cuối cùng nhưng vẫn đáng kể đối với tải database.

Ghi cả thời gian truy xuất và thời gian toàn bộ tác vụ giúp giải thích kết quả đó.

## 6. Những chỉ số cần thu thập

### 6.1. Độ trễ và thông lượng

- Độ trễ từng lần lấy tại đầu, giữa và cuối tập dữ liệu.
- Trung vị, p95, p99 của những nhóm phép đo tương đương.
- Tổng thời gian đọc hết.
- Số bản ghi xử lý thành công mỗi giây.
- Số truy vấn nội dung, truy vấn đếm và truy vấn phụ.

Không trộn độ trễ của trang đầu với trang rất sâu rồi chỉ báo một số trung bình. Đường độ trễ theo vị trí thường thể hiện vấn đề offset rõ hơn.

### 6.2. Công việc của kho dữ liệu

Tùy hệ thống quan sát được, theo dõi:

- Số dòng hoặc mục index đã xem xét so với số kết quả trả về.
- CPU, số lần đọc, cache hit và thời gian chờ I/O.
- Sort bổ sung, bộ nhớ sort và lượng dữ liệu tràn ra đĩa.
- Kế hoạch truy vấn và thay đổi kế hoạch theo tham số.
- Tài nguyên hoặc request được tính phí trong kho dữ liệu quản lý.

Một truy vấn nhanh nhờ cache vẫn có thể tạo lượng CPU lớn và giảm khả năng phục vụ đồng thời. Ngược lại, giảm số mục phải duyệt chưa bảo đảm cải thiện đáng kể nếu điểm nghẽn nằm ở mạng hoặc xử lý sau truy vấn.

### 6.3. Bộ nhớ và tài nguyên ứng dụng

`Window` giới hạn nội dung một lần lấy, nhưng tổng bộ nhớ còn phụ thuộc cách ứng dụng giữ dữ liệu.

Các tình huống cần kiểm tra:

- Vòng lặp gom mọi window vào một `List` lớn.
- Hàng đợi xử lý bất đồng bộ tăng không có giới hạn.
- Persistence context giữ nhiều entity trong transaction kéo dài.
- Tải quan hệ gây N+1 hoặc materialize dữ liệu lớn.
- Giữ kết nối hoặc transaction lâu hơn dự kiến.

Không thể suy rằng “đang dùng scrolling nên bộ nhớ chắc chắn chỉ bằng một window”. Cũng không nên tùy tiện `clear` persistence context khi còn thay đổi chưa được quản lý; vòng đời entity và transaction cần thiết kế rõ.

## 7. Đọc kết quả benchmark mà không kết luận quá mức

### 7.1. Mẫu báo cáo không chứa số đo giả

| Phương án | Độ trễ đầu tập | Độ trễ giữa tập | Độ trễ cuối tập | Tổng thời gian | Count query | Ghi chú kế hoạch |
|---|---|---|---|---|---|---|
| `Page` + offset | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Ghi số thực tế | Ghi từ hệ thống |
| `Slice` + offset | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Ghi số thực tế | Ghi từ hệ thống |
| `Window` + offset | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Ghi số thực tế | Ghi từ hệ thống |
| `Window` + keyset | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Ghi số thực tế | Ghi từ hệ thống |

Với từng dòng, ghi rõ module, phiên bản, loại query, dữ liệu, index, kích thước window, projection và mức đồng thời. Những con số mô hình ở phần trước không được đưa vào bảng như kết quả thực nghiệm.

### 7.2. Một số cách diễn giải thường gặp

| Quan sát | Cách diễn giải cần kiểm tra |
|---|---|
| Offset chậm dần theo độ sâu | Có thể đang lặp lại công việc duyệt phần bị bỏ qua |
| `Page` chậm nhưng `Slice` nhanh hơn nhiều | Chi phí count có thể chiếm tỷ trọng lớn |
| Keyset chậm ngay từ đầu | Filter, index, sort hoặc ánh xạ có thể là điểm nghẽn |
| Keyset tốt ở một tenant nhưng kém ở tenant khác | Phân bố dữ liệu và kế hoạch theo tham số có thể khác |
| Query nhanh nhưng job vẫn chậm | Công việc nghiệp vụ, tải quan hệ hoặc đợi dịch vụ có thể chi phối |
| Thông lượng tăng nhưng dữ liệu bị bỏ sót | Có thể đã đổi hợp đồng lọc, sort hoặc tiếp tục sai ranh giới |

Một kết luận hữu ích mô tả được điều kiện, chẳng hạn: “Với bộ lọc này, index này và cửa sổ này, keyset giữ độ trễ lấy tiếp ổn định hơn khi đọc sâu”. Tránh biến kết quả đó thành tuyên bố mọi loại scrolling luôn nhanh hơn mọi loại phân trang.

## 8. Tính nhất quán khi dữ liệu thay đổi

### 8.1. Offset có thể bị dịch vị trí

Giả sử dữ liệu theo thứ tự là:

```text
A, B, C, D, E, F
```

Lần đầu lấy ba phần tử: `A, B, C`. Nếu `A` bị xóa trước lần tiếp theo, tập còn:

```text
B, C, D, E, F
```

Bỏ qua ba phần tử trong tập mới sẽ bắt đầu ở `E`, làm `D` bị bỏ lỡ trong phiên này. Ngược lại, thêm một phần tử đứng trước ranh giới có thể khiến một phần tử đã đọc xuất hiện lại ở trang sau.

Đây là hệ quả của việc tiếp tục bằng vị trí đếm trên một tập đang thay đổi.

### 8.2. Keyset giảm dịch vị trí nhưng không tạo snapshot

Nếu ranh giới là giá trị khóa của `C`, việc xóa một phần tử đứng trước `C` không làm thay đổi bộ khóa đó. Trong tình huống này, keyset có thể tiếp tục đúng từ phía sau `C`.

Tuy nhiên, keyset vẫn có thể gặp:

- Bản ghi mới được thêm vào vùng đã đi qua nên phiên hiện tại không đọc nó.
- Bản ghi chưa đọc đổi khóa sort và chuyển sang vùng đã đi qua nên bị bỏ lỡ.
- Bản ghi đã đọc đổi khóa sort và chuyển sang vùng chưa đi qua nên xuất hiện lại.
- Bản ghi thay đổi trạng thái nên gia nhập hoặc rời khỏi tập lọc giữa phiên.
- Bản ghi bị xóa trước khi tác vụ xử lý đến.

Do đó, “không bị dịch offset” không đồng nghĩa “đọc đúng một lần toàn bộ dữ liệu tại thời điểm bắt đầu”.

### 8.3. Auditing không tự làm khóa sort bất biến

`createdAt` có thể phù hợp nếu ứng dụng bảo đảm nó được thiết lập khi tạo và không đổi. Một trường được dùng cho auditing vẫn cần quy tắc nghiệp vụ và lưu trữ phù hợp để giữ tính ổn định.

Trường thời điểm sửa cuối thường thay đổi khi cập nhật. Nếu dùng nó làm khóa sort trong một job đang sửa chính các bản ghi được đọc, cần phân tích sự dịch chuyển ranh giới và phạm vi lọc.

### 8.4. Watermark và snapshot là những thiết kế bổ sung

Một job có thể giữ một điều kiện như `createdAt <= cutoff` trong toàn bộ phiên để giới hạn dữ liệu mới. Điều này hữu ích nhưng không đóng băng cập nhật, xóa hoặc dữ liệu được nhập với thời điểm cũ.

Nếu yêu cầu là một tập dữ liệu chính xác tại một thời điểm, cần chọn cơ chế phù hợp của nguồn, chẳng hạn snapshot, version dữ liệu hoặc tập định danh đã chốt. Transaction dài có thể tạo chi phí riêng; không nên thêm chỉ để làm cho benchmark trông ổn định.

## 9. Cursor và khả năng khôi phục tác vụ

### 9.1. Cursor thuộc một hợp đồng truy vấn

Một cursor có ý nghĩa khi được gắn với:

- Các khóa và kiểu dữ liệu tương ứng.
- Thứ tự và chiều sắp xếp.
- Bộ lọc, tenant và phạm vi truy cập.
- Hướng cuộn và phiên bản hợp đồng nếu cần.

Không dùng cursor của bộ lọc này để tiếp tục bộ lọc khác. Với API công khai, cần kiểm tra cursor theo ngữ cảnh hiện tại và áp dụng lại quyền truy cập; cursor không thay thế kiểm tra quyền.

### 9.2. Checkpoint phải phản ánh phần đã xử lý thành công

Nếu đã đọc 200 phần tử nhưng mới xử lý 50, lưu position của phần tử thứ 200 có thể làm bỏ qua 150 phần tử khi khởi động lại.

Ngược lại, xử lý thành công rồi dừng trước khi lưu checkpoint có thể làm công việc bị thực hiện lại. Tùy yêu cầu, cần xử lý idempotent, transaction phù hợp hoặc cơ chế phối hợp trạng thái.

Khi so sánh tổng thời gian job, tính cả chi phí checkpoint và xử lý lại theo chính sách thực tế. Keyset position giúp xác định ranh giới đọc; nó không tự cung cấp bảo đảm exactly-once cho tác động nghiệp vụ.

## 10. Chọn theo nhu cầu sản phẩm và vận hành

| Nhu cầu | Lựa chọn đáng cân nhắc | Lý do và điều kiện |
|---|---|---|
| Giao diện cần số trang, tổng bản ghi và nhảy trang | `Page` với offset | Hợp đồng phù hợp; đo count và trang sâu |
| Giao diện chỉ cần biết còn dữ liệu sau | `Slice` hoặc `Window` tùy module | Giảm nhu cầu tổng; vẫn phải chọn cơ chế tiếp tục |
| Nút tải thêm, đi tuần tự, không cần tổng | Keyset scrolling | Phù hợp nếu sort, khóa và store hỗ trợ |
| Xuất toàn bộ tập dữ liệu lớn | Keyset hoặc cơ chế quét chuyên biệt của store | Đo tổng công việc và thiết kế tính nhất quán |
| Job tiếp tục sau lỗi | Keyset kèm checkpoint | Cần thêm chính sách xử lý lại và giữ ngữ cảnh truy vấn |
| Dữ liệu nhỏ, số trang ít | Offset | Đơn giản và có thể đáp ứng tốt yêu cầu |
| Sort tùy ý theo biểu thức, khóa nullable hoặc projection thiếu khóa | Đánh giá lại thiết kế | Keyset có thể không phù hợp hoặc không được module hỗ trợ |
| Kho có cursor hoặc scan API chuyên biệt | Cơ chế của module/store tương ứng | Không áp mô hình SQL một cách máy móc |

Có thể kết hợp các hợp đồng trong cùng hệ thống: màn hình quản trị dùng `Page`, còn tác vụ xuất dữ liệu dùng `Window` với keyset. Hai cách đọc vẫn chia sẻ domain và repository abstraction, nhưng tối ưu cho những yêu cầu khác nhau.

## 11. Những lỗi làm phép so sánh sai lệch

### 11.1. Cho rằng bỏ count là đã giải quyết đọc sâu

Đổi `Page` thành `Slice` có thể giảm thời gian đáng kể khi count đắt. Nếu vẫn dùng offset, trang sâu vẫn có thể chậm. Cần đo riêng hai yếu tố.

### 11.2. Cho rằng keyset chỉ cần `id > lastId`

Điều kiện này chỉ phù hợp khi thứ tự và phạm vi thực tế cho phép. Nếu sort chính là thời điểm hoặc độ ưu tiên, phải dùng toàn bộ quan hệ so sánh theo thứ tự đã chọn.

### 11.3. Tăng kích thước window mà không đo tác động

Window lớn giảm số lượt gọi nhưng tăng kích thước phản hồi, bộ nhớ, thời gian giữ tài nguyên và lượng công việc phải xử lý lại nếu lỗi. Window nhỏ giảm chi phí từng lần nhưng tăng overhead.

Nên thử một số kích thước đại diện và đo đồng thời thông lượng, độ trễ, bộ nhớ. Không có một kích thước tối ưu chung cho mọi job.

### 11.4. Đánh đồng scrolling với stream giữ một kết nối

Một vòng lặp gọi repository trả `Window` thực hiện các lần lấy tiếp theo position. Nó không tự đồng nghĩa với một JDBC cursor hoặc một `Stream` giữ tài nguyên liên tục.

Khi so sánh với streaming, phải đánh giá riêng vòng đời kết nối, transaction, cách đóng tài nguyên và chính sách backpressure nếu có.

### 11.5. Dùng mock để kết luận về hiệu năng truy vấn

Một mock trả sẵn `Window` có thể giúp kiểm tra điều kiện dừng và cách chọn position. Nó không chứng minh module sinh đúng predicate, index được sử dụng hay chi phí đọc sâu đã giảm.

Đánh giá hiệu năng cần thực hiện với kho và truy vấn tương ứng, cùng dữ liệu có phân bố gần thực tế.

## 12. Bài tập vận dụng

### Bài tập 1: Window nhưng vẫn chậm dần

Một nhóm thay phương thức trả `Page` thành `Window`, bỏ total count và dùng `ScrollPosition.offset()`. Những cửa sổ cuối vẫn chậm hơn nhiều. Giải thích hiện tượng.

**Gợi ý lời giải:** Nhóm đã thay đổi metadata kết quả và có thể giảm count query, nhưng vẫn tiếp tục bằng offset. Chi phí tìm đoạn ở sâu có thể còn nguyên. Cần so sánh thêm keyset trong điều kiện module hỗ trợ.

### Bài tập 2: Đo keyset ở cửa sổ thứ 500

Để so sánh, người thử lấy sẵn cursor của cửa sổ thứ 500 rồi chỉ đo truy vấn kế tiếp. Có thể kết luận keyset nhảy tới cửa sổ thứ 500 nhanh hơn offset không?

**Gợi ý lời giải:** Phép đo cho biết độ trễ lấy tiếp khi đã có ranh giới. Nó chưa tính chi phí tạo cursor, nên không chứng minh khả năng nhảy trang bất kỳ theo số trang. Cần ghi rõ câu hỏi và phạm vi đo.

### Bài tập 3: Tổng số bản ghi là yêu cầu bắt buộc

Giao diện cần tổng số kết quả khớp filter và cho phép nhập số trang. Có nên thay toàn bộ bằng keyset chỉ vì dữ liệu lớn không?

**Gợi ý lời giải:** Cần giữ hoặc thiết kế lại hợp đồng sản phẩm trước. Keyset không tự cung cấp tổng hay ranh giới của trang bất kỳ. Có thể tối ưu count, giới hạn truy cập sâu, lưu ranh giới hoặc dùng giải pháp khác theo nhu cầu thực tế; cần đánh giá chi phí và hành vi cụ thể.

### Bài tập 4: Sort theo thời điểm cập nhật

Job dùng keyset theo `lastModifiedAt ASC, id ASC`, đồng thời cập nhật các bản ghi vừa đọc. Điều gì cần phân tích ngoài hiệu năng?

**Gợi ý lời giải:** Khóa sort có thể thay đổi và đưa bản ghi sang vùng chưa đi qua, làm phát sinh đọc lại hoặc kéo dài tác vụ. Cần xác định tính nhất quán, phạm vi dữ liệu, chính sách cập nhật và cơ chế giới hạn phiên.

### Bài tập 5: Entity so với projection

Keyset trả projection ba trường nhanh gấp nhiều lần offset trả entity kèm tải quan hệ. Kết quả đã tách được lợi ích của keyset chưa?

**Gợi ý lời giải:** Chưa. Cần giữ tương đương đầu ra và chiến lược tải, hoặc báo riêng ảnh hưởng của projection, tải quan hệ và cơ chế tiếp tục. Projection dùng cho keyset cũng phải cung cấp khóa cần thiết.

### Bài tập 6: Không bỏ sót nhưng xử lý trùng

Job tiếp tục đúng keyset, không có bản ghi dịch chuyển khóa, nhưng gửi một tác động nghiệp vụ hai lần sau khi khởi động lại. Điều này có mâu thuẫn với keyset không?

**Gợi ý lời giải:** Không. Có thể tác động đã thành công nhưng checkpoint chưa được lưu. Ranh giới đọc và bảo đảm xử lý nghiệp vụ là hai phần thiết kế cần phối hợp.

## 13. Những điều cần ghi nhớ

- So sánh theo cơ chế tiếp tục: offset pagination, offset scrolling và keyset scrolling có đặc tính khác nhau.
- Tránh kết luận từ kích thước phản hồi; phải xem lượng công việc kho dữ liệu thực hiện để tìm đoạn trả về.
- `Page` có nhu cầu tổng; `Slice` và `Window` tránh hợp đồng tổng nhưng không tự loại bỏ chi phí offset.
- Keyset phù hợp với truy cập tuần tự khi có thứ tự đầy đủ, khóa sử dụng được, projection phù hợp và hỗ trợ từ module.
- Đo đầu, giữa, cuối và toàn bộ tác vụ; tách count, truy vấn nội dung, ánh xạ và xử lý nghiệp vụ.
- Index, phân bố dữ liệu, cache và mức đồng thời quyết định kết quả thực tế.
- Cả offset lẫn keyset đều cần phân tích khi tập dữ liệu thay đổi; keyset không tự tạo snapshot hay exactly-once.
- Chọn theo hợp đồng sản phẩm và vận hành, rồi dùng số đo trên hệ thống tương ứng để xác nhận lựa chọn.
