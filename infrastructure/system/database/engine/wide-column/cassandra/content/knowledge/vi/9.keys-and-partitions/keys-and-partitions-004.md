# CLUSTERING ORDER BY và truy vấn theo khoảng

Trong Apache Cassandra, dữ liệu được phân phối giữa các node theo **partition key**, nhưng các hàng **bên trong mỗi phân vùng** được tổ chức theo **clustering columns**. Thuộc tính CQL `CLUSTERING ORDER BY` quy định chiều sắp xếp mặc định của các clustering columns. Kết hợp với điều kiện khoảng trên clustering key, ta có thể đọc nhanh các bản ghi gần nhất, lịch sử sự kiện theo giờ hoặc một lát cắt thời gian mà không phải sắp xếp toàn bộ tập dữ liệu trên ứng dụng.

Đây là một phần của tư duy **thiết kế bảng theo truy vấn** trong mô hình wide-column phân tán. Cần phân biệt rõ: partition key giúp tìm đúng phân vùng; clustering key cùng thứ tự của nó giúp tìm và duyệt các hàng trong phân vùng ấy. `CLUSTERING ORDER BY` không thay đổi số replica, token hay mức nhất quán đọc/ghi của Cassandra.

Sau bài học, bạn có thể:

- Định nghĩa `CLUSTERING ORDER BY` trong `CREATE TABLE`, hiểu ý nghĩa của `ASC` và `DESC`.
- Dự đoán thứ tự hàng trong một phân vùng khi có một hoặc nhiều clustering columns.
- Viết các truy vấn CQL dùng `=`, `>=`, `>`, `<=`, `<` trên clustering columns.
- Phân biệt thứ tự lưu theo schema với `ORDER BY` trong câu `SELECT`.
- Nhận biết truy vấn vượt quy tắc tiền tố clustering key, phạm vi partition key và các trường hợp cần mô hình dữ liệu khác.
- Áp dụng truy vấn khoảng bằng prepared statement từ Java.

## 1. Phân vùng và thứ tự bên trong phân vùng

Xét yêu cầu của hệ thống thu thập dữ liệu cảm biến: **đọc 20 bản đo mới nhất của một thiết bị trong một ngày** và **đọc các bản đo từ 08:00 đến trước 09:00**. Một thiết bị có thể sinh nhiều bản ghi cùng thời điểm, nên cần thêm định danh sự kiện.

Ta thiết kế bảng:

```sql
CREATE TABLE measurements_by_device_day (
    tenant_id       text,
    device_id       uuid,
    event_day       date,
    measured_at     timestamp,
    measurement_id  uuid,
    temperature     double,
    battery_percent int,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        measured_at,
        measurement_id
    )
) WITH CLUSTERING ORDER BY (
    measured_at DESC,
    measurement_id ASC
);
```

Ba nhóm cột có vai trò khác nhau:

| Nhóm | Cột | Trách nhiệm |
| --- | --- | --- |
| Partition key ghép | `(tenant_id, device_id, event_day)` | Chọn **một phân vùng logic** cho một thiết bị của một tenant trong một ngày. |
| Clustering column thứ nhất | `measured_at` | Nhóm hàng theo thời điểm, sắp từ **mới đến cũ** nhờ `DESC`. |
| Clustering column thứ hai | `measurement_id` | Phân biệt các bản đo trùng thời điểm; sắp **tăng dần** khi `measured_at` bằng nhau. |
| Cột thường | `temperature`, `battery_percent` | Chứa giá trị bản đo, không tham gia xác định vị trí và thứ tự clustering. |

Với một partition key cố định, dữ liệu được sắp theo khóa clustering **theo thứ tự từ trái sang phải**. Nếu có cùng `measured_at`, Cassandra dùng `measurement_id` để phân biệt và quyết định thứ tự phụ.

```text
Partition ('acme', device-01, 2026-11-21)

  measured_at           measurement_id    temperature
  2026-11-21 08:45:00   ...0002           37.9
  2026-11-21 08:45:00   ...0008           38.0
  2026-11-21 08:30:00   ...0001           37.7
  2026-11-21 08:00:00   ...0005           37.5

              measured_at DESC
                 |
                 +-- tại cùng thời điểm: measurement_id ASC
```

Những hàng của ngày khác hoặc thiết bị khác nằm ở phân vùng logic khác; `CLUSTERING ORDER BY` **không tạo ra thứ tự toàn cục giữa các phân vùng**.

## 2. `CLUSTERING ORDER BY` được khai báo và hoạt động thế nào?

Cú pháp dùng trong `CREATE TABLE`:

```sql
CREATE TABLE sample_events (
    account_id uuid,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (account_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Ở ví dụ này `account_id` là partition key **đơn**. Hai clustering columns `occurred_at` và `event_id` được sắp theo hai chiều khác nhau.

Nếu **không khai báo** `CLUSTERING ORDER BY`, Cassandra mặc định sắp các clustering columns theo **`ASC`**:

```sql
-- Mặc định occurred_at ASC, event_id ASC:
CREATE TABLE sample_events_asc (
    account_id uuid,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (account_id, occurred_at, event_id)
);
```

Ý nghĩa:

- `ASC`: giá trị nhỏ đứng trước giá trị lớn theo comparator của **kiểu dữ liệu** cột.
- `DESC`: giá trị lớn đứng trước giá trị nhỏ theo comparator đó.
- Với timestamp, `DESC` thường phù hợp khi giao diện cần dữ liệu mới nhất trước.
- Với nhiều clustering columns, tiêu chí của cột đứng sau chỉ có ý nghĩa khi các cột đứng trước bằng nhau.

**Lưu ý về “thứ tự lưu”:** Cassandra dùng kiến trúc LSM với memtable và nhiều SSTable; một phân vùng có thể xuất hiện trong nhiều SSTable. Vì thế, “được sắp theo clustering key” là quy tắc thứ tự logic được Cassandra dùng khi truy xuất và hợp nhất dữ liệu, **không** có nghĩa toàn bộ phân vùng luôn nằm liên tục trong một tệp duy nhất.

`CLUSTERING ORDER BY` là thuộc tính schema gắn với cách tổ chức khóa. Muốn đổi thiết kế clustering key/thứ tự lưu sau khi bảng đã tồn tại, thông thường cần tạo bảng mới phù hợp, chuyển dữ liệu và chuyển luồng đọc/ghi; không nên coi đây là tùy chọn có thể thay đổi linh hoạt theo từng yêu cầu.

## 3. Đọc theo thứ tự mặc định: không cần `ORDER BY`

Với bảng `measurements_by_device_day`, câu truy vấn sau đã trả các bản đo theo thứ tự clustering đã khai báo trong phân vùng:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

Kết quả bắt đầu bằng các hàng có `measured_at` lớn nhất. Nếu hai hàng có cùng thời điểm, `measurement_id ASC` phân biệt thứ tự của chúng.

Ở đây:

1. Ba điều kiện bằng chọn **đầy đủ partition key**.
2. `CLUSTERING ORDER BY (measured_at DESC, measurement_id ASC)` xác định thứ tự mặc định.
3. `LIMIT 20` giới hạn số hàng kết quả, nên thích hợp cho một danh sách bản đo gần nhất của **một phân vùng**.

Không cần thêm `ORDER BY measured_at DESC` chỉ để có thứ tự trùng với schema. Trong tình huống truy vấn lớn, hiệu quả thực tế còn phụ thuộc số tombstone, kích thước phân vùng, cache, SSTable và cách đọc, nhưng việc chọn đúng partition key vẫn là bước nền tảng.

### Dùng `ORDER BY` trong `SELECT` khi cần đảo chiều

CQL có `ORDER BY` trong `SELECT`, nhưng nó bị ràng buộc bởi **clustering columns**. Với bảng đã khai báo `measured_at DESC, measurement_id ASC`, có thể yêu cầu duyệt theo **thứ tự ngược hoàn toàn**:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
ORDER BY measured_at ASC, measurement_id DESC
LIMIT 20;
```

Lúc này các bản đo cũ nhất của ngày xuất hiện trước; khi trùng thời điểm, `measurement_id` được duyệt theo chiều ngược lại.

Với một bảng có nhiều clustering columns, hướng sắp xếp mà `SELECT ORDER BY` yêu cầu phải tương thích với thứ tự clustering của schema, hoặc **đảo ngược toàn bộ các hướng**. Không thể tự do chọn chiều cho từng cột hoặc sắp xếp theo một cột thường như `temperature`.

| Câu lệnh/mong muốn | Có phù hợp với bảng ví dụ? | Giải thích |
| --- | --- | --- |
| Không viết `ORDER BY` | Có | Dùng mặc định `measured_at DESC, measurement_id ASC`. |
| `ORDER BY measured_at ASC, measurement_id DESC` | Có | Đảo ngược toàn bộ thứ tự clustering. |
| `ORDER BY measured_at DESC, measurement_id DESC` | Không | Chỉ đảo một cột, không tương ứng thứ tự schema hoặc thứ tự ngược toàn bộ. |
| `ORDER BY temperature DESC` | Không | `temperature` là cột thường, không phải clustering column. |
| Sắp xếp toàn bộ thiết bị trong hệ thống theo `measured_at` | Không trực tiếp | Thứ tự clustering chỉ có phạm vi bên trong từng phân vùng. |

Việc truy vấn theo chiều ngược với cách lưu có thể có chi phí khác nhau theo phiên bản Cassandra và tình trạng dữ liệu. Nếu cùng lúc cần hai chiều ở quy mô lớn, hãy đo trên tải thực tế trước khi quyết định.

## 4. Truy vấn theo khoảng trên clustering column

**Range query** là truy vấn với một hoặc nhiều điều kiện bất đẳng thức như `>`, `>=`, `<`, `<=`, dùng để lấy một đoạn giá trị trong một phân vùng đã được xác định.

### Một khoảng thời gian đóng–mở

Để lấy các bản đo từ **08:00:00 (kể cả)** đến **09:00:00 (không kể)** ngày 21/11/2026, theo giờ UTC:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at >= '2026-11-21T08:00:00Z'
  AND measured_at <  '2026-11-21T09:00:00Z';
```

Đây là khoảng **`[08:00, 09:00)`**. Chọn cách viết đóng–mở giúp hai khoảng kế tiếp `[08:00, 09:00)` và `[09:00, 10:00)` không cùng chứa một bản đo đúng 09:00:00.

Cassandra có thể khoanh vùng đoạn clustering keys tương ứng trong **một phân vùng**, rồi trả về theo thứ tự clustering của bảng. Điều kiện `measured_at >= ...` không làm kết quả tự chuyển sang thứ tự tăng dần: thứ tự mặc định ở đây vẫn là `DESC`.

### Khoảng trên cột thứ hai: phải cố định tiền tố

Với hai clustering columns `(measured_at, measurement_id)`, Cassandra sắp theo **measured_at trước**, sau đó mới theo `measurement_id`.

Có thể chọn các bản đo trong một thời điểm xác định và giới hạn `measurement_id`:

```sql
SELECT measured_at, measurement_id, temperature
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at = '2026-11-21T08:45:00Z'
  AND measurement_id >= 00000000-0000-0000-0000-000000000010;
```

Ở đây `measured_at` được cố định bằng `=`, nên Cassandra có thể xét dải giá trị `measurement_id` trong phần của clustering key đó. Giá trị UUID minh họa chỉ dùng để diễn tả toán tử so sánh theo kiểu dữ liệu; trong thực tế, nên chọn `measurement_id` và mục tiêu truy vấn sao cho phép so sánh có ý nghĩa nghiệp vụ.

Không thể lược bỏ `measured_at` rồi lọc `measurement_id` theo khoảng như thể cột thứ hai được đánh chỉ mục độc lập:

```sql
-- Thiếu clustering column đứng trước measurement_id:
SELECT *
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measurement_id >= 00000000-0000-0000-0000-000000000010;
```

Đường truy cập khóa chính không hỗ trợ truy vấn trên như một đoạn clustering liên tục. Khi thiết kế nhiều clustering columns, hãy đưa cột thường được lọc theo khoảng **lên trước**, và dùng các clustering columns phía sau để phân biệt hàng hoặc đáp ứng kiểu truy vấn khác.

### Quy tắc tiền tố clustering columns

Với khóa clustering `(c1, c2, c3)`, cách sử dụng phổ biến trong CQL là:

- Ràng buộc **`c1 = ...`** trước khi lọc `c2`.
- Ràng buộc **`c1 = ... AND c2 = ...`** trước khi lọc `c3`.
- Có thể dùng khoảng trên **cột clustering kế tiếp** sau chuỗi các điều kiện bằng.
- Sau khi đã dùng khoảng trên một cột, các cột phía sau không còn hoạt động như những dải độc lập theo cùng đường truy cập đơn giản.

Cassandra có thêm một số cú pháp/trường hợp truy vấn tuple clustering; chúng cần xét theo phiên bản và cú pháp cụ thể, không làm mất quy tắc tổ chức dữ liệu theo tiền tố đã khai báo.

## 5. Một ví dụ đầy đủ với cửa sổ thời gian

Giả sử một ứng dụng giám sát cần trả trang đầu của đồ thị nhiệt độ:

- Tenant: `acme`.
- Thiết bị: `327a71e9-f562-4b54-94b9-2138a9e30b12`.
- Bucket ngày: `2026-11-21` (được tính theo UTC).
- Khoảng UTC: `[08:00, 09:00)`.
- Giới hạn: 100 bản đo.

CQL tương ứng:

```sql
SELECT measured_at, measurement_id, temperature, battery_percent
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND measured_at >= '2026-11-21T08:00:00Z'
  AND measured_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
```

Trình tự thực thi ở mức khái niệm:

```text
1. Đọc tenant_id + device_id + event_day
                    |
                    v
2. Tính token -> xác định tập replica giữ partition
                    |
                    v
3. Trong partition, tìm slice measured_at thuộc [08:00, 09:00)
                    |
                    v
4. Duyệt theo clustering order: measured_at DESC, measurement_id ASC
                    |
                    v
5. Trả tối đa 100 hàng phù hợp
```

Sơ đồ chỉ biểu diễn đường truy cập logic, không mô tả đầy đủ các bước đọc từ memtable/SSTable, giao tiếp giữa replica hoặc mức nhất quán.

### Lấy dữ liệu từ nhiều ngày

Vì `event_day` nằm trong **partition key**, câu hỏi “từ 23:30 ngày 21 đến 00:30 ngày 22” phải bao phủ ít nhất **hai partition key khác nhau**.

Ứng dụng có thể:

1. Truy vấn phân vùng ngày 21 với khoảng `[2026-11-21T23:30Z, 2026-11-22T00:00Z)`.
2. Truy vấn phân vùng ngày 22 với khoảng `[2026-11-22T00:00Z, 2026-11-22T00:30Z)`.
3. Hợp nhất và sắp theo `measured_at` ở ứng dụng nếu cần **một chuỗi kết quả chung**.

`ORDER BY` trên từng câu truy vấn **không tự hợp nhất thứ tự giữa nhiều phân vùng**. Nếu truy vấn xuyên nhiều bucket là nghiệp vụ chính, cần xem xét thêm bảng được thiết kế cho đường truy cập đó và kiểm soát kích thước phân vùng.

## 6. Phân biệt `CLUSTERING ORDER BY` và `SELECT ORDER BY`

| Tiêu chí | `CLUSTERING ORDER BY` | `ORDER BY` của `SELECT` |
| --- | --- | --- |
| Khai báo ở đâu? | Trong `CREATE TABLE ... WITH` | Trong câu lệnh `SELECT` |
| Mục đích | Định nghĩa chiều sắp xếp mặc định của clustering keys trong phân vùng | Yêu cầu chiều duyệt kết quả phù hợp với clustering order |
| Phạm vi | Từng phân vùng của bảng | Kết quả truy vấn đọc trên đường truy cập clustering được hỗ trợ |
| Có dùng cột thường? | Không | Không theo đường truy cập clustering thông thường |
| Thay đổi tùy câu truy vấn? | Không; là cấu hình schema | Có, nhưng phải theo thứ tự được hỗ trợ |
| Sắp thứ tự giữa mọi phân vùng? | Không | Không cung cấp `ORDER BY` toàn cục kiểu SQL quan hệ |

Trong hệ quản trị quan hệ, `ORDER BY created_at DESC` thường là thao tác sắp xếp tập kết quả sau khi truy vấn. Trong Cassandra, bạn nên **dự kiến thứ tự dữ liệu ngay từ thiết kế bảng** để tránh kỳ vọng một lệnh `ORDER BY` bất kỳ có thể giải quyết mọi trường hợp.

Một ví dụ không hợp lệ trong thiết kế này:

```sql
-- temperature không phải clustering column:
SELECT *
FROM measurements_by_device_day
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
ORDER BY temperature DESC;
```

Nếu nghiệp vụ cần “100 bản đo nhiệt độ cao nhất”, hãy cân nhắc bảng chuyên biệt theo khóa sắp xếp nhiệt độ, quy trình tổng hợp hoặc xử lý ở lớp ứng dụng trên lượng dữ liệu đã giới hạn, tùy yêu cầu nhất quán và quy mô.

## 7. Những lỗi hay gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách tiếp cận |
| --- | --- | --- |
| `SELECT` không viết `ORDER BY` nhưng kết quả “ngược” so với ý định | Schema mặc định `ASC` hoặc khai báo chiều clustering khác mong muốn. | Chọn `CLUSTERING ORDER BY` theo truy vấn chính ngay khi thiết kế. |
| Muốn sắp theo `temperature` hoặc cột ngoài clustering key | `ORDER BY` của CQL không phải phép sort tự do trên mọi cột. | Thiết kế bảng/đường truy cập khác hoặc sort tập đã giới hạn ở ứng dụng. |
| Lọc `measurement_id` khi không cố định `measured_at` | Bỏ qua cột tiền tố của clustering key. | Cố định tiền tố phù hợp hoặc đổi thứ tự clustering trong một bảng mới. |
| Tìm theo `measured_at` mà không cung cấp `device_id` và `event_day` | Không xác định được partition key hoàn chỉnh. | Bổ sung khóa, đọc đúng các bucket hoặc tạo bảng phục vụ truy vấn khác. |
| Truy vấn dải thời gian cắt qua nửa đêm nhưng chỉ lấy bucket ngày đầu | `event_day` chia dữ liệu thành các phân vùng ngày. | Tính toàn bộ bucket được bao phủ và hợp nhất kết quả. |
| Dữ liệu timestamp bị thiếu/thừa ở ranh giới | Dùng hai khoảng đóng ở cả hai đầu hoặc xử lý múi giờ không thống nhất. | Dùng khoảng đóng–mở `[start, end)` và chuẩn hóa UTC/bucket. |
| Truy vấn khoảng trả nhiều hàng và độ trễ lớn | Phân vùng quá lớn, slice quá rộng, nhiều tombstone hoặc paging chưa hợp lý. | Rút ngắn khoảng, bucket phù hợp, phân trang, quan sát metrics và compaction. |

### Chú ý với `LIMIT` và phân trang

`LIMIT 100` giới hạn **số hàng kết quả**, không có nghĩa Cassandra chỉ phải đọc đúng 100 ô dữ liệu trên đĩa trong mọi trường hợp. Một dải có tombstone hoặc nhiều SSTable vẫn có thể cần xử lý thêm. Khi thực hiện nhiều lần đọc tiếp theo, nên dùng **paging state** từ Cassandra driver thay vì tự cắt trang bằng cách đoán timestamp cuối cùng: nhiều hàng có thể cùng `measured_at`.

Nếu cần tự xây dựng *cursor* theo khóa, phải bao gồm **đủ clustering columns** để không bỏ sót hoặc lặp các hàng trùng timestamp; quy tắc điều kiện tuple và chiều sắp xếp cần được kiểm tra trên phiên bản CQL đang sử dụng.

## 8. Gọi range query từ Java

Trong ứng dụng Java dùng Cassandra Java Driver 4.x, đặt các giá trị khóa và biên thời gian vào `PreparedStatement`. Ví dụ dùng `Instant` cho cột CQL `timestamp` và `LocalDate` cho cột `date`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class MeasurementRepository {
    private final CqlSession session;
    private final PreparedStatement findInRange;

    public MeasurementRepository(CqlSession session) {
        this.session = session;
        this.findInRange = session.prepare(
            "SELECT measured_at, measurement_id, temperature " +
            "FROM measurements_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND event_day = ? " +
            "AND measured_at >= ? AND measured_at < ? " +
            "LIMIT 100"
        );
    }

    public ResultSet findInRange(
            String tenantId, UUID deviceId, LocalDate eventDay,
            Instant startInclusive, Instant endExclusive) {
        return session.execute(findInRange.bind(
            tenantId, deviceId, eventDay, startInclusive, endExclusive));
    }
}
```

Khi gọi, ứng dụng cần bảo đảm `eventDay` được tính theo **cùng quy tắc bucket** đã dùng lúc ghi dữ liệu. Với khoảng qua hai ngày, gọi phương thức cho hai partition keys khác nhau và tổng hợp kết quả. `Instant` là một thời điểm tuyệt đối; chỉ dùng `LocalDate` bucket sau khi đã quy định múi giờ (chẳng hạn UTC) để tránh lệch ngày.

Trong triển khai thực tế, nên tái sử dụng prepared statement, cấu hình page size phù hợp và truyền deadline/timeout theo tải hệ thống. Truy vấn đúng partition key giúp driver xác định routing key để gửi yêu cầu đến coordinator phù hợp trong điều kiện metadata cluster đầy đủ.

## 9. Bài tập tự kiểm tra

Cho bảng đơn hàng:

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    ordered_at timestamp,
    order_id uuid,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        ordered_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
```

Hãy trả lời trước khi xem đáp án:

1. Bảng trả đơn mới nhất hay đơn cũ nhất trước nếu không viết `ORDER BY`?
2. Nếu hai đơn cùng `ordered_at`, cột nào quyết định thứ tự tiếp theo?
3. Muốn lấy đơn trong khoảng `[2026-11-10T00:00Z, 2026-11-11T00:00Z)` của một khách hàng trong tháng 11, điều kiện `WHERE` tối thiểu cần những phần nào?
4. Câu `ORDER BY ordered_at ASC, order_id DESC` có phù hợp không? Câu `ORDER BY ordered_at ASC, order_id ASC` thì sao?
5. Có thể dùng nguyên bảng để truy vấn “mọi đơn hàng của mọi khách hàng trong tenant T, tháng M, sắp theo `ordered_at DESC`” mà vẫn nhận kết quả theo một thứ tự toàn cục không?
6. Nếu một đơn có timestamp trùng đơn khác nhưng `order_id` khác, nó có bị ghi đè không?

**Gợi ý đáp án:**

1. **Mới nhất trước** vì `ordered_at DESC`.
2. `order_id ASC` quyết định thứ tự khi `ordered_at` bằng nhau.
3. Cần `tenant_id = ...`, `customer_id = ...`, `month_bucket = ...` và điều kiện khoảng trên `ordered_at`.
4. `ASC, DESC` là đảo ngược toàn bộ thứ tự schema, nên phù hợp; `ASC, ASC` chỉ đảo cột đầu, không phải thứ tự được hỗ trợ trong mô hình này.
5. **Không trực tiếp**: khóa phân vùng còn chứa `customer_id` và thứ tự clustering chỉ áp dụng trong từng phân vùng.
6. **Không**, vì `order_id` thuộc primary key đầy đủ; hai tổ hợp khóa khác nhau là hai hàng logic.

## 10. Ghi nhớ để thiết kế bảng Cassandra

- `CLUSTERING ORDER BY` được định nghĩa trong schema và áp dụng **trong từng phân vùng**, theo thứ tự các clustering columns.
- Không khai báo thì các clustering columns mặc định được sắp **`ASC`**; `DESC` hữu ích khi truy vấn chính cần các bản ghi mới nhất.
- Muốn truy vấn theo khoảng hiệu quả, cần **đầy đủ partition key** và một dải trên clustering column phù hợp quy tắc tiền tố.
- CQL `SELECT ORDER BY` bị giới hạn bởi clustering order; không dùng để sắp xếp tùy ý theo cột thường hoặc trên toàn cluster.
- Khoảng thời gian **đóng–mở** và quy ước bucket/múi giờ thống nhất giúp tránh mất hoặc trùng bản ghi ở ranh giới.
- Kết hợp clustering order với **bucket thời gian**, thiết kế bảng theo truy vấn và phân trang để kiểm soát độ trễ trong hệ thống Cassandra phân tán.

Nắm vững thứ tự clustering và truy vấn theo khoảng giúp bạn thiết kế các bảng nhật ký, đơn hàng, cảm biến và timeline phù hợp với cách Cassandra thực sự lưu và đọc dữ liệu. Đây cũng là nền tảng để đánh giá hiệu năng đọc/ghi, mức nhất quán, compaction và cách truy vấn từ ứng dụng Java.

