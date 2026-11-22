# Đối chiếu read/write consistency với yêu cầu nghiệp vụ trong Apache Cassandra

## 1. Vì sao cần chọn consistency theo nghiệp vụ?

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**: dữ liệu của một partition được sao chép lên nhiều node, còn bảng thường được thiết kế từ những truy vấn cần phục vụ. Khi ứng dụng ghi một trạng thái đơn hàng rồi đọc lại, câu hỏi không chỉ là truy vấn có nhanh không, mà còn là **bản đọc có phải nhìn thấy bản ghi vừa được xác nhận hay không**, khi một node hoặc cả trung tâm dữ liệu gặp sự cố thì phải xử lý thế nào.

Cassandra cho phép chọn **consistency level (CL) riêng cho từng thao tác đọc/ghi**. CL xác định cần bao nhiêu replica tham gia phản hồi để coordinator coi thao tác là thành công. CL không thay đổi số lượng replica được cấu hình, cũng không tự tạo giao dịch ACID xuyên nhiều partition. Chọn CL là đánh đổi có chủ đích giữa **mức mới của dữ liệu, độ sẵn sàng và độ trễ**.

Hãy xét hệ thống thương mại điện tử với các luồng sau:

- **Danh mục sản phẩm:** vài giây chậm cập nhật thường chấp nhận được; ưu tiên đọc nhanh.
- **Trạng thái đơn hàng:** sau khi API xác nhận chuyển sang `SHIPPED`, màn hình tra cứu trong cùng vùng cần đọc được thay đổi vừa ghi.
- **Giữ chỗ tồn kho:** hai yêu cầu đồng thời không được cùng giành một đơn vị tồn kho.
- **Thanh toán và sổ cái:** cần các bất biến giao dịch nghiêm ngặt trên nhiều thực thể; điều chỉnh CL của Cassandra đơn thuần không giải quyết được yêu cầu này.

Mục tiêu của bài là chuyển những câu diễn đạt nghiệp vụ như trên thành **RF, write CL, read CL, serial CL (nếu có LWT), phạm vi datacenter và chính sách xử lý lỗi** có thể kiểm thử.

## 2. Phân biệt replication factor, consistency level và phạm vi datacenter

Giả sử một partition có **replication factor** `RF = 3` trong datacenter `dc1`. Ba replica có thể chứa dữ liệu của partition đó. Khi ghi, coordinator gửi mutation tới các replica phù hợp; khi đọc, coordinator liên hệ đủ replica theo CL, đối chiếu các bản trả về khi cần và chọn giá trị theo cơ chế hòa giải của Cassandra.

| Thuật ngữ | Ý nghĩa thực tế | Không nên hiểu nhầm |
| --- | --- | --- |
| `RF` | Số bản sao của một partition theo cấu hình keyspace, thường khai báo theo từng DC với `NetworkTopologyStrategy` | Không phải số replica bắt buộc xác nhận mỗi truy vấn |
| Write CL (`W`) | Số replica cần xác nhận ghi để client được báo thành công | Ghi thành công không đồng nghĩa mọi replica đã cập nhật |
| Read CL (`R`) | Số replica cần đáp ứng đọc theo CL | Không phải câu lệnh SQL khóa toàn bộ dữ liệu |
| `LOCAL_*` | Xét replica thuộc datacenter địa phương của coordinator | Không bảo đảm DC khác đã thấy bản ghi |
| Regular consistency | Quorum/ONE/ALL… cho các lệnh đọc và ghi thông thường | Không tuần tự hóa các cập nhật đồng thời |
| Serial consistency | `SERIAL`/`LOCAL_SERIAL` cho giai đoạn Paxos của lightweight transaction (LWT) | Không thay thế regular CL của chính lệnh LWT |

Những CL thường gặp:

| CL | Điều kiện xác nhận | Phù hợp khi / lưu ý |
| --- | --- | --- |
| `ANY` | **Chỉ ghi**: có thể được xác nhận bằng một hint dù chưa có replica thực sự lưu mutation | Ưu tiên nhận ghi trong sự cố; nguy cơ chưa đọc được ngay và có thể mất nếu hint không được chuyển tới replica; tránh dùng cho dữ liệu quan trọng |
| `ONE`, `TWO`, `THREE` | Có lần lượt 1, 2, 3 replica đáp ứng | Đơn giản trong một DC; phải kiểm tra RF có đủ lớn |
| `LOCAL_ONE` | Một replica tại DC địa phương | Độ trễ đọc/ghi thấp; bản nhìn thấy có thể cũ |
| `QUORUM` | Quá nửa **tổng số replica** của partition trên các DC | Với RF 3+3, cần 4 phản hồi; thường tốn đường truyền liên DC |
| `LOCAL_QUORUM` | Quá nửa số replica của partition **trong DC địa phương** | Lựa chọn phổ biến cho ứng dụng đa DC cần nhất quán trong vùng |
| `EACH_QUORUM` | **Chỉ ghi**: quá nửa replica tại **từng DC** | Đòi hỏi các DC đều khả dụng, đổi lấy xác nhận ghi ở mỗi vùng |
| `ALL` | Mọi replica cần đáp ứng | Giảm khả năng thành công khi một replica lỗi/chậm; không biến ghi thường thành giao dịch tuyến tính |
| `SERIAL`, `LOCAL_SERIAL` | Mức nhất quán của giai đoạn tuần tự hóa LWT bằng Paxos; `LOCAL_SERIAL` giới hạn phạm vi DC | Dùng cùng regular CL khi `IF ...`, `IF NOT EXISTS` nhằm giải quyết tranh chấp đồng thời |

**Cách tính quorum:** với `RF = N` trong phạm vi được xét, quorum là `floor(N / 2) + 1`. Ví dụ `RF(dc1) = 3` thì `LOCAL_QUORUM = 2`; nếu `RF(dc1) = 3` và `RF(dc2) = 3` thì `QUORUM = 4`, còn `LOCAL_QUORUM` tại mỗi DC vẫn là 2.

### Quy tắc giao nhau giữa read và write

Trong **một phạm vi replica chung**, khi `R + W > RF`, tập replica phục vụ đọc và tập đã xác nhận ghi chắc chắn có ít nhất một phần tử giao nhau. Với `RF = 3`:

| Write CL | Read CL | `W + R > 3`? | Nhận xét |
| --- | --- | --- | --- |
| `ONE` (1) | `ONE` (1) | Không | Đọc có thể rơi vào replica chưa thấy ghi mới |
| `TWO` (2) | `TWO` (2) | Có | Có giao nhau, chịu được một replica không khả dụng cho mỗi thao tác riêng lẻ |
| `QUORUM` (2) | `QUORUM` (2) | Có | Tương đương 2+2 trong một DC có RF 3 |
| `ALL` (3) | `ONE` (1) | Có | Đọc rẻ hơn nhưng một replica lỗi có thể làm ghi thất bại |
| `ONE` (1) | `ALL` (3) | Có | Ghi dễ thành công hơn nhưng đọc rất nhạy với lỗi replica |

Quy tắc này hữu ích để chọn một cấu hình **đọc được lần ghi đã xác nhận trong điều kiện bình thường**, với cùng tập replica, không có cập nhật cạnh tranh và không có sai lệch bất thường về timestamp. Đây **không phải** lời hứa tuyến tính hóa cho mọi lịch sử đồng thời: Cassandra hòa giải các cell theo timestamp (last-write-wins), còn xung đột, xóa bằng tombstone, retry hoặc đồng hồ lệch vẫn cần được thiết kế và vận hành đúng. Với **nhiều DC**, không thể cộng tùy tiện `W` ở DC này với `R` ở DC khác: `LOCAL_QUORUM` của `dc1` và `LOCAL_QUORUM` của `dc2` không bảo đảm hai tập replica giao nhau.

## 3. Bắt đầu từ hợp đồng dữ liệu, rồi mới chọn CL

Trước khi đặt `CONSISTENCY LOCAL_QUORUM`, hãy mô tả rõ bốn điều:

1. **Độ mới cần thiết:** đọc có thể chậm 1–5 giây, hay phải phản ánh bản ghi đã xác nhận ngay trong cùng vùng?
2. **Phạm vi:** client luôn đọc/ghi cùng DC hay được tự do chuyển vùng? Có nhiều vùng cùng sửa một khóa không?
3. **Hành vi khi lỗi:** ưu tiên trả lỗi để tránh đọc cũ, hay cho phép đọc cũ/ghi xếp hàng nhằm giữ dịch vụ hoạt động? Có thể cho người dùng thấy trạng thái `PENDING` không?
4. **Ràng buộc đồng thời:** chỉ cần thấy phiên bản mới nhất, hay cần điều kiện “chỉ cập nhật nếu version hiện tại bằng 7”, hoặc giao dịch qua nhiều khóa?

Từ đó lập bảng quyết định, ví dụ với `RF = 3` mỗi DC và ứng dụng ưu tiên truy cập một DC gần người dùng:

| Luồng nghiệp vụ | Mức chấp nhận dữ liệu cũ | Gợi ý write / read CL | Kiểm soát bổ sung |
| --- | --- | --- | --- |
| Hiển thị danh mục, bộ lọc không quan trọng | Chấp nhận trễ ngắn | `LOCAL_ONE` / `LOCAL_ONE` | Cache TTL, cập nhật bất đồng bộ, theo dõi độ trễ đồng bộ |
| Hồ sơ người dùng vừa chỉnh sửa | Không muốn đọc cũ trong cùng vùng | `LOCAL_QUORUM` / `LOCAL_QUORUM` | Client bám cùng DC, retry có kiểm soát, xử lý ghi đồng thời |
| Tra cứu trạng thái đơn hàng | Ưu tiên thấy thay đổi đã xác nhận | `LOCAL_QUORUM` / `LOCAL_QUORUM` | Ghi/đọc theo `order_id`, đồng bộ hóa quy tắc chuyển trạng thái |
| Thu thập sự kiện có thể gửi lại | Có thể đồng bộ trễ | `LOCAL_ONE` / `LOCAL_ONE` tùy ngân sách mất dữ liệu | Event ID chống trùng, retry/buffer bền vững, giám sát replica lag |
| Giữ chỗ tồn kho trên một SKU | Không chấp nhận ghi đè cạnh tranh | Regular CL phù hợp + `LOCAL_SERIAL` cho LWT trong một vùng ghi | `IF` theo version, chỉ một vùng chịu trách nhiệm cho khóa; kiểm tra kết quả `[applied]` |
| Sổ cái, chuyển tiền nhiều tài khoản | Không chấp nhận lệch số dư hay ghi một nửa | **Không có cặp CL thông thường nào đủ** | Dùng hệ giao dịch ACID/kiến trúc chuyên biệt, sau đó đẩy dữ liệu phục vụ tra cứu sang Cassandra nếu cần |

Đây là **điểm xuất phát để benchmark và kiểm thử sự cố**, không phải cấu hình mặc định an toàn cho mọi dự án. `LOCAL_ONE` có thể phù hợp về độ trễ nhưng độ bền của ghi và chất lượng khôi phục phải được đánh giá theo RPO. `LOCAL_QUORUM` thường tốn thêm thời gian chờ và có thể trả timeout khi chưa đủ replica; nếu muốn độ trễ p99 thấp cần đo trên topology và tải thực tế.

## 4. Ví dụ: đặt cấu hình cho trạng thái đơn hàng

Giả sử dịch vụ có hai datacenter `dc1`, `dc2`, mỗi nơi ba replica cho keyspace. Tên DC phải khớp tên thực tế trong cluster. Ứng dụng đọc/ghi trạng thái đơn hàng chủ yếu tại `dc1`, với mỗi truy vấn theo `order_id`.

```sql
CREATE KEYSPACE commerce
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};

CREATE TABLE commerce.order_status_by_id (
  order_id uuid PRIMARY KEY,
  status text,
  version int,
  updated_at timestamp
);
```

Bảng được thiết kế cho truy vấn **theo khóa phân vùng `order_id`**. CL không sửa được một truy vấn thiếu partition key, `ALLOW FILTERING` quá nặng, partition quá lớn hay hot partition; tối ưu read/write consistency phải đi cùng thiết kế bảng theo truy vấn.

Trong `cqlsh`, có thể thử chính sách regular CL cho phiên thao tác:

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO commerce.order_status_by_id
  (order_id, status, version, updated_at)
VALUES
  (11111111-1111-1111-1111-111111111111, 'CREATED', 1, toTimestamp(now()));

SELECT status, version, updated_at
FROM commerce.order_status_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
```

Khi ghi và đọc đều `LOCAL_QUORUM` ở `dc1`, mỗi thao tác cần ít nhất hai replica tại `dc1` phản hồi. Nếu ghi đã được xác nhận rồi đọc cùng DC, các tập quorum giao nhau. Nhưng nếu dịch vụ chuyển sang `dc2` trước khi `dc2` nhận cập nhật, một lần đọc `LOCAL_QUORUM` tại `dc2` **vẫn có thể trả giá trị cũ**. Thiết kế failover phải xác định rõ liệu chấp nhận trễ đồng bộ, có cần ngừng ghi, đối soát, hay cần một cơ chế sở hữu vùng ghi.

### Khi có hai yêu cầu cập nhật đồng thời: LWT

Giả sử hai worker cùng muốn đổi phiên bản trạng thái từ 1 sang 2. Hai câu `UPDATE` thông thường tại `LOCAL_QUORUM` không thực thi điều kiện “chỉ một worker thắng”. Với cùng một partition, có thể dùng **lightweight transaction (LWT)**:

```sql
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY LOCAL_SERIAL;

UPDATE commerce.order_status_by_id
SET status = 'PAID', version = 2, updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-1111-1111-111111111111
IF version = 1;
```

Kết quả có cột `[applied]`: `true` nghĩa là cập nhật điều kiện thành công, `false` nghĩa là điều kiện không còn đúng; nhánh `false` **không được** coi như cập nhật thành công. LWT dùng Paxos, tăng số vòng giao tiếp và độ trễ, do đó chỉ áp dụng nơi có tranh chấp cần kiểm soát. Với `LOCAL_SERIAL`, hãy quy định **một DC chịu trách nhiệm các cập nhật cạnh tranh cho cùng khóa**; nếu điều kiện phải giữ trên toàn cụm đa DC, xem xét `SERIAL`, chính sách điều phối ghi toàn cục và chi phí/khả năng chịu lỗi của nó. LWT theo một partition không tạo giao dịch nguyên tử trên nhiều partition.

### Áp dụng CL cho từng statement từ Java

Ví dụ dưới sử dụng API của Java Driver 4.x (`com.datastax.oss.driver.api`). `CqlSession` đã được tạo với local datacenter và keyspace/contact point phù hợp, và nên được tái sử dụng thay vì mở kết nối cho mỗi request.

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class OrderStatusRepository {
    private final CqlSession session;

    public OrderStatusRepository(CqlSession session) {
        this.session = session;
    }

    public boolean moveFromCreatedToPaid(UUID orderId) {
        SimpleStatement conditionalUpdate = SimpleStatement.builder(
                "UPDATE commerce.order_status_by_id " +
                "SET status = ?, version = ? WHERE order_id = ? IF version = ?")
            .addPositionalValues("PAID", 2, orderId, 1)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
            .build();

        ResultSet result = session.execute(conditionalUpdate);
        return result.wasApplied();
    }

    public String findStatus(UUID orderId) {
        SimpleStatement lookup = SimpleStatement.builder(
                "SELECT status FROM commerce.order_status_by_id WHERE order_id = ?")
            .addPositionalValue(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        var row = session.execute(lookup).one();
        return row == null ? null : row.getString("status");
    }
}
```

Mã trả về `false` khi điều kiện CAS không được áp dụng; ở lớp nghiệp vụ nên đọc lại version hiện tại rồi quyết định báo xung đột hay tính toán lại. Nếu request **timeout**, không thể suy ra thao tác chắc chắn chưa xảy ra; cần truy vấn trạng thái theo ID/version hoặc một quy trình đối soát trước khi gửi lại thao tác không idempotent. Với tải cao, ưu tiên prepared statement, cấu hình timeout/retry có chủ đích và thu thập metric theo statement.

## 5. Phân tích sự cố trước khi chốt chính sách

| Tình huống | Ảnh hưởng với RF 3, `LOCAL_QUORUM` ghi/đọc tại một DC | Hành động ứng dụng |
| --- | --- | --- |
| Một replica tại DC bị mất hoặc phản hồi chậm | Hai replica còn lại có thể đủ quorum; độ trễ có thể tăng | Theo dõi latency, timeout, tiến độ hồi phục |
| Hai replica tại cùng DC không khả dụng | Không đủ quorum địa phương; ghi/đọc ở CL này có thể lỗi | Trả lỗi có kiểm soát, không âm thầm hạ CL khi nghiệp vụ không chấp nhận dữ liệu cũ |
| Ghi được báo thành công nhưng client mất kết nối trước khi nhận phản hồi | Client không biết chắc ghi đã áp dụng hay chưa | Sử dụng request ID, thao tác idempotent, read-back hoặc đối soát |
| `dc1` đã xác nhận, client chuyển ngay sang `dc2` | `LOCAL_QUORUM` ở `dc2` có thể thấy dữ liệu cũ | Ràng buộc vùng truy cập hoặc quy trình failover và đồng bộ |
| Nhiều writer ghi cùng một cell | Thứ tự cuối cùng phụ thuộc timestamp và cơ chế hòa giải | Thiết kế version/CAS hoặc giới hạn writer theo partition |
| Replica bỏ lỡ mutation rồi trở lại | Dữ liệu có thể lệch tạm thời; hints/read repair chỉ hỗ trợ một phần | Thiết lập lịch repair và giám sát tiến độ, không coi compaction là repair |

**Không hạ CL tự động chỉ để biến lỗi thành thành công.** Ví dụ write `LOCAL_QUORUM` timeout rồi fallback xuống `LOCAL_ONE` có thể làm API trả thành công trong khi điều kiện nhìn thấy ghi đã xác nhận không còn đúng. Nếu sản phẩm chọn chế độ degraded, phải mô tả rõ hợp đồng mới (chẳng hạn “đã nhận yêu cầu, đang xử lý”), cách đối soát và cách phục hồi.

### Vai trò của hints, repair, read repair và compaction

- **Hinted handoff** giúp chuyển các mutation mà replica tạm thời bỏ lỡ trong cửa sổ nhất định. Hint không thay thế một bản sao dữ liệu đã bền vững, và không bảo đảm hội tụ trong mọi thời gian mất kết nối.
- **Read repair** có thể sửa sai lệch được phát hiện trong những phần dữ liệu được đọc theo cơ chế áp dụng của phiên bản/cấu hình Cassandra. Không thể chỉ dựa vào traffic đọc để sửa mọi partition.
- **Anti-entropy repair** (ví dụ vận hành `nodetool repair` theo quy trình của cluster) giúp các replica đồng bộ dữ liệu bỏ lỡ; đặc biệt quan trọng với dữ liệu có xóa/tombstone và chính sách giữ tombstone.
- **Compaction** gộp SSTable, tổ chức lại dữ liệu lưu trữ và xử lý tombstone theo điều kiện an toàn; nó **không** thay thế việc đồng bộ replica. Chọn chiến lược compaction dựa trên kiểu ghi/đọc/TTL; không coi đây là nút vặn trực tiếp của consistency level.

Các cơ chế này liên quan đến độ bền và khả năng phục hồi theo thời gian, nhưng không sửa được việc chọn sai CL hoặc ghi đồng thời không có quy tắc.

## 6. Phương pháp kiểm thử và đo lường

Để xác nhận lựa chọn, dựng môi trường có RF và topology gần sản xuất, dùng khóa phân vùng, kích thước bản ghi và tỷ lệ read/write thực tế. Giữ riêng các kết quả theo DC và theo CL.

1. **Thử đọc sau ghi:** ghi ở `dc1`, chờ phản hồi rồi đọc ngay tại `dc1` và `dc2`; lặp dưới tải để đo độ trễ và tỷ lệ stale read, phân biệt rõ CL đọc/ghi.
2. **Thử mất replica:** lần lượt làm không khả dụng một rồi hai replica của cùng DC trong môi trường thử; đo success rate và p95/p99 read/write latency ở `LOCAL_ONE`, `LOCAL_QUORUM`.
3. **Thử write timeout:** gây lỗi sau khi một phần replica nhận ghi; xác nhận ứng dụng không coi timeout là “chưa ghi”, không tự tạo sự kiện trùng và có đường đối soát.
4. **Thử ghi cạnh tranh:** hai worker cùng cập nhật một `order_id`; so sánh cập nhật thường với `IF version = ?`, kiểm tra đúng một lệnh LWT được `[applied] = true` khi cùng kỳ vọng một version.
5. **Thử chuyển vùng:** dừng đường truyền giữa hai DC, ghi trong vùng được phép, mô phỏng đọc/failover vùng khác; đối chiếu chính sách RPO, khả năng nhất quán và quy trình khôi phục đã công bố.
6. **Theo dõi sau test:** đo timeout, unavailable, read/write latency, speculative/retry activity, tombstone/partition size, trạng thái replica, repair và mức độ chênh lệch dữ liệu thực tế.

Không có “số giây stale” cố định chỉ từ việc đặt `LOCAL_ONE`, cũng không có bảo đảm availability chỉ từ công thức quorum. Kết quả chịu ảnh hưởng bởi phân bố replica, độ trễ mạng, tải, phiên bản Cassandra, chiến lược truy vấn và cách driver xử lý lỗi.

## 7. Bảng quyết định nhanh

Trước khi đưa một luồng nghiệp vụ vào production, hãy trả lời các câu sau:

| Câu hỏi | Nếu câu trả lời là… | Hướng xử lý |
| --- | --- | --- |
| Chấp nhận đọc cũ ngắn hạn? | Có | Đánh giá `LOCAL_ONE` và cơ chế cache/đối soát |
| Cần thấy ghi vừa xác nhận trong cùng DC? | Có | Ưu tiên cặp CL có `R + W > RF` trong cùng phạm vi, thường `LOCAL_QUORUM`/`LOCAL_QUORUM` với RF 3 |
| Client có thể chuyển DC ngay sau ghi? | Có | Không dựa riêng vào hai `LOCAL_QUORUM`; xác định quyền sở hữu ghi, cơ chế failover hoặc quorum toàn vùng nếu đáp ứng yêu cầu |
| Nhiều request tranh chấp cùng một khóa? | Có | Dùng điều kiện và LWT theo partition nếu chi phí phù hợp; xét phạm vi `SERIAL`/`LOCAL_SERIAL` |
| Phải cập nhật nguyên tử trên nhiều partition? | Có | Thiết kế lại ranh giới giao dịch hoặc chọn hệ lưu trữ hỗ trợ transaction cần thiết |
| Không đủ replica để đạt CL đã cam kết? | Có | Trả lỗi/cảnh báo và thực hiện quy trình degraded đã được nghiệp vụ chấp nhận, thay vì âm thầm hạ CL |

**Bài tập áp dụng:** Với `RF(dc1) = RF(dc2) = 3`, API cập nhật địa chỉ giao hàng tại `dc1` với `LOCAL_QUORUM`; ứng dụng di động có thể đọc ngay ở `dc2` với `LOCAL_QUORUM`. Hãy giải thích vì sao vẫn có thể đọc địa chỉ cũ, đề xuất hai chính sách xử lý (ví dụ bám vùng và chấp nhận failover có đối soát), rồi mô tả một phép thử mô phỏng đứt liên kết hai DC để kiểm chứng lời hứa với người dùng. Nếu địa chỉ phải được đọc nhất quán toàn cầu sau mọi cập nhật, hãy xem cả chi phí của quorum liên DC và nhu cầu điều phối writer.

**Ghi nhớ:** Consistency là một phần của **hợp đồng API**. Xác định nghiệp vụ chấp nhận dữ liệu cũ đến đâu và chịu lỗi thế nào, chọn RF/CL đúng phạm vi, dùng LWT cho tranh chấp thật sự, kiểm thử failover và bảo trì repair. Đừng dùng consistency level để bù cho thiết kế partition key, quy trình retry hay yêu cầu giao dịch sai mô hình.
