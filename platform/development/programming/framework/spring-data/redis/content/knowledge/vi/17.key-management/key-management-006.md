# Duyệt và xóa theo nhóm trong phạm vi namespace với Spring Data Redis

## 1. Bài toán và mục tiêu

Trong một ứng dụng sử dụng Spring Data Redis, nhiều loại dữ liệu có thể cùng tồn tại trong một Redis database: cache sản phẩm, trạng thái phiên, dữ liệu tạm của đơn hàng, khóa chống xử lý trùng, bộ đếm và dữ liệu của các tenant. Khi cần dọn dữ liệu của **một nhóm cụ thể**, ta phải xác định chính xác các khóa thuộc nhóm trước khi xóa.

Ví dụ, hệ thống quản lý đơn hàng lưu các khóa:

```text
shop:orders:v1:tenant:42:state:OPEN:1001
shop:orders:v1:tenant:42:state:OPEN:1002
shop:orders:v1:tenant:42:state:DONE:1003
shop:orders:v1:tenant:73:state:OPEN:2001
shop:products:v1:item:1001
```

Yêu cầu: dọn nhóm đơn `OPEN` của tenant `42`. Chỉ hai khóa đầu tiên là đối tượng xử lý; khóa `DONE`, tenant `73` và nhóm `products` phải được giữ nguyên.

Bài học tập trung vào ba thao tác:

1. Thiết kế **namespace** (tiền tố tên khóa) đủ cụ thể để phân định quyền sở hữu dữ liệu.
2. Duyệt dần các khóa thuộc namespace bằng `SCAN MATCH` thay vì quét chặn toàn bộ keyspace bằng `KEYS`.
3. Xóa theo lô bằng `UNLINK` hoặc `DEL`, có kiểm soát phạm vi, tải hệ thống và thay đổi dữ liệu đồng thời.

**Giới hạn của kỹ thuật:** Redis không có khái niệm thư mục hay namespace vật lý như một hệ thống tệp. Namespace chỉ là quy ước đặt tên; Redis xử lý mỗi tên khóa như một chuỗi độc lập. Vì thế, việc chọn đúng tiền tố và mẫu tìm kiếm là trách nhiệm của ứng dụng.

## 2. Thiết kế namespace để có thể chọn đúng nhóm

Một quy ước nên phản ánh ứng dụng, miền dữ liệu, phiên bản và các chiều phân nhóm cần quản lý:

```text
<application>:<domain>:<version>:tenant:<tenantId>:state:<state>:<entityId>
```

Trong ví dụ:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Ứng dụng và domain | `shop:orders` | Phân biệt với các miền dữ liệu khác |
| Phiên bản | `v1` | Cho phép thay đổi cấu trúc hoặc dọn phiên bản cũ |
| Tenant | `tenant:42` | Cô lập dữ liệu theo đơn vị sử dụng |
| Trạng thái | `state:OPEN` | Nhóm khóa cần thao tác |
| Định danh | `1001` | Phân biệt từng khóa |

Tiền tố của nhóm cần xóa là:

```text
shop:orders:v1:tenant:42:state:OPEN:
```

Mẫu duyệt là tiền tố đó cộng với ký tự `*`:

```text
shop:orders:v1:tenant:42:state:OPEN:*
```

Dấu `:` cuối tiền tố rất quan trọng. Nếu tìm `...:state:OPEN*`, mẫu có thể khớp cả `OPEN_ARCHIVED` hoặc `OPENED`. Tiền tố càng chặt chẽ thì nguy cơ xóa lẫn dữ liệu càng thấp.

### Không đưa chuỗi tùy ý vào mẫu tìm kiếm

Trong Redis, `MATCH` sử dụng cú pháp *glob*: `*` khớp nhiều ký tự, `?` khớp một ký tự, `[abc]` khớp một ký tự nằm trong tập được chỉ định. Do đó, nếu `tenantId` do người dùng nhập chứa ký tự đặc biệt thì phép duyệt có thể mở rộng ngoài ý muốn.

Nên kiểm tra từng thành phần động theo quy ước nghiêm ngặt, chẳng hạn chỉ cho phép chữ, số, dấu gạch dưới và dấu gạch ngang. Không nhận trực tiếp một `pattern` tùy ý từ HTTP request để thực thi việc xóa nhóm. Cũng cần phân biệt rõ namespace dùng để quản lý dữ liệu cache với namespace chứa dữ liệu nguồn nghiệp vụ: việc xóa cache có thể phục hồi được, còn việc xóa dữ liệu nguồn thường phải theo cơ chế nghiệp vụ và kiểm soát riêng.

## 3. Vì sao nên dùng SCAN thay cho KEYS?

Hai lệnh đều có khả năng lọc tên khóa theo mẫu, nhưng cách hoạt động khác nhau:

| Tiêu chí | `KEYS pattern` | `SCAN cursor MATCH pattern COUNT n` |
|---|---|---|
| Cách lấy kết quả | Trả về toàn bộ danh sách phù hợp trong một lệnh | Duyệt tăng dần qua nhiều lệnh và một cursor |
| Tác động khi keyspace lớn | Có thể chặn Redis trong lúc tìm kiếm, tạo kết quả lớn | Phân bổ công việc theo từng lượt, phù hợp hơn cho vận hành |
| Bộ nhớ ở client | Có thể phải chứa danh sách rất lớn | Có thể xử lý từng khóa hoặc từng lô nhỏ |
| Tính nhất quán | Phản ánh một lần thực thi lệnh | Không phải ảnh chụp bất biến khi keyspace thay đổi |
| Ứng dụng thông thường | Chẩn đoán có kiểm soát trên dữ liệu nhỏ | Công việc bảo trì, duyệt và xóa nhóm |

Ví dụ Redis CLI:

```redis
SCAN 0 MATCH shop:orders:v1:tenant:42:state:OPEN:* COUNT 500
```

Redis trả về **cursor mới** và một danh sách khóa. Client tiếp tục dùng cursor vừa trả về, kể cả khi danh sách của một lượt là rỗng. Chỉ kết thúc lượt duyệt đầy đủ khi cursor quay về `0`.

`COUNT 500` là gợi ý lượng công việc cho mỗi lượt, **không** bảo đảm có đúng 500 khóa trả về. `MATCH` lọc trên các khóa đã được quét ở mỗi lượt; một mẫu khớp rất ít khóa vẫn có thể cần nhiều lượt quét toàn bộ keyspace. Tổng độ phức tạp của một vòng `SCAN` đầy đủ vẫn phụ thuộc vào kích thước tập khóa đang duyệt.

**Các bảo đảm cần nhớ của SCAN:**

- Một vòng duyệt có thể trả lại **cùng một khóa nhiều lần**; thao tác theo sau cần có tính lặp lại an toàn.
- Khóa xuất hiện hoặc biến mất trong lúc duyệt có thể được thấy hoặc bị bỏ qua.
- Một vòng duyệt hoàn tất sẽ thấy các khóa tồn tại liên tục từ đầu đến cuối vòng, nhưng không tạo ra ảnh chụp nhất quán tại một thời điểm.
- Một lượt trả về danh sách rỗng chưa có nghĩa là đã duyệt xong.

`SCAN` thích hợp cho xử lý dọn dẹp có thể chạy lại. Nếu bài toán yêu cầu một tập khóa **chính xác, cố định, không bỏ sót** trong bối cảnh có nhiều tác vụ ghi đồng thời, cần thêm cơ chế phối hợp với bên ghi dữ liệu hoặc duy trì chỉ mục nhóm riêng.

## 4. Duyệt khóa bằng StringRedisTemplate

Với tên khóa là chuỗi UTF-8 thông thường, `StringRedisTemplate` giúp tránh nhầm lẫn với cách tuần tự hóa key của một `RedisTemplate` cấu hình khác. Spring Data Redis có API `scan(ScanOptions)` trả về một `Cursor<String>`; cursor phải được đóng sau khi dùng.

Ví dụ dịch vụ chỉ xem trước một phần các khóa thuộc nhóm:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderKeyBrowser {

    private static final String ROOT = "shop:orders:v1:";
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private final StringRedisTemplate redis;

    public OrderKeyBrowser(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> previewOpenOrders(String tenantId, int maxResults) {
        validateSegment(tenantId);

        if (maxResults < 1 || maxResults > 200) {
            throw new IllegalArgumentException("maxResults must be 1..200");
        }

        String prefix = ROOT + "tenant:" + tenantId + ":state:OPEN:";
        ScanOptions options = ScanOptions.scanOptions()
                .match(prefix + "*")
                .count(500)
                .build();

        List<String> keys = new ArrayList<>();

        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext() && keys.size() < maxResults) {
                String key = cursor.next();

                // Phòng trường hợp thay đổi cấu trúc mẫu ngoài dự kiến.
                if (key.startsWith(prefix)) {
                    keys.add(key);
                }
            }
        }

        return keys;
    }

    private static void validateSegment(String value) {
        if (value == null || !SAFE_SEGMENT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
    }
}
```

Ví dụ:

```java
List<String> sample = browser.previewOpenOrders("42", 20);
sample.forEach(System.out::println);
```

Phương thức trả về **tối đa 20 tên khóa để xem trước**, không trả về số lượng chính xác của cả nhóm. Dừng cursor sớm ở giới hạn này là chấp nhận được cho tính năng xem trước; tuyệt đối không dùng kích thước danh sách để suy ra tổng số khóa tồn tại.

Đối với `RedisTemplate<K, V>` với bộ serializer khác, phải xác định đúng serializer của key. Không tự giải mã hoặc xóa `byte[]` bằng cách suy luận tên chuỗi nếu key thực tế được lưu theo định dạng nhị phân.

## 5. Xóa nhóm theo lô với SCAN và UNLINK

Sau bước xem trước, một tác vụ bảo trì có thể tiếp tục duyệt và xóa từng lô. Trong Redis:

- `DEL key [key ...]` xóa key và giải phóng bộ nhớ đồng bộ; thời gian giải phóng một số cấu trúc dữ liệu lớn có thể tạo độ trễ.
- `UNLINK key [key ...]` tách key khỏi keyspace, rồi giải phóng bộ nhớ ở tác vụ nền của Redis. Đây thường là lựa chọn phù hợp cho dọn cache nhiều khóa trên Redis hỗ trợ `UNLINK` (Redis 4.0 trở lên).
- Hai lệnh đều trả về **số key thực sự được gỡ bỏ**, có thể thấp hơn số key yêu cầu vì key đã hết hạn, đã bị xóa hoặc bị trả lại trùng trong lần quét.

Ví dụ dưới đây áp dụng cho **Redis độc lập hoặc Redis Sentinel**, nơi một lệnh xóa nhiều key được gửi đến cùng một Redis server. Nhóm có phạm vi cố định là tenant và trạng thái đơn hàng.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderKeyCleanupService {

    private static final String ROOT = "shop:orders:v1:";
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private static final int SCAN_COUNT_HINT = 500;
    private static final int UNLINK_BATCH_SIZE = 200;

    private final StringRedisTemplate redis;

    public OrderKeyCleanupService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /**
     * Chỉ gọi từ tác vụ bảo trì đã được xác thực và giới hạn quyền.
     * Trả về số khóa thực tế được gỡ bỏ, không phải số khóa đã quét.
     */
    public long deleteOrderStateGroup(String tenantId, String state) {
        String prefix = groupPrefix(tenantId, state);

        ScanOptions options = ScanOptions.scanOptions()
                .match(prefix + "*")
                .count(SCAN_COUNT_HINT)
                .build();

        List<String> batch = new ArrayList<>(UNLINK_BATCH_SIZE);
        long removed = 0;

        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext()) {
                String key = cursor.next();

                // Kiểm tra lại toàn bộ tiền tố thuộc quyền xử lý.
                if (!key.startsWith(prefix)) {
                    continue;
                }

                batch.add(key);

                if (batch.size() >= UNLINK_BATCH_SIZE) {
                    removed += unlinkBatch(batch);
                    batch.clear();
                }
            }
        }

        if (!batch.isEmpty()) {
            removed += unlinkBatch(batch);
        }

        return removed;
    }

    private long unlinkBatch(List<String> keys) {
        Long count = redis.unlink(List.copyOf(keys));
        if (count == null) {
            throw new IllegalStateException("UNLINK returned no count");
        }
        return count;
    }

    private static String groupPrefix(String tenantId, String state) {
        validateSegment(tenantId, "tenantId");
        validateSegment(state, "state");
        return ROOT + "tenant:" + tenantId + ":state:" + state + ":";
    }

    private static void validateSegment(String value, String field) {
        if (value == null || !SAFE_SEGMENT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid " + field);
        }
    }
}
```

Cách gọi có chủ đích:

```java
long removed = cleanupService.deleteOrderStateGroup("42", "OPEN");
System.out.println("Removed keys: " + removed);
```

Luồng xử lý gồm:

1. Xác thực từng thành phần động và tạo tiền tố có dấu phân cách cuối.
2. Tạo `ScanOptions` để lọc các khóa nằm trong nhóm.
3. Đọc cursor theo từng lượt; không nạp toàn bộ khóa vào một `Set` lớn.
4. Tập hợp tối đa 200 tên khóa, gọi `unlink(Collection<String>)` rồi giải phóng danh sách.
5. Khi cursor kết thúc, xóa lô cuối cùng còn lại và trả về số key được Redis xác nhận đã gỡ.

Giới hạn 200 key là **kích thước mỗi lệnh xóa**, không phải giới hạn số khóa mà cả tác vụ có thể xóa. `COUNT` và kích thước lô là hai tham số độc lập: thứ nhất ảnh hưởng đến cách Redis quét, thứ hai ảnh hưởng đến số khóa được gửi trong một lệnh `UNLINK`. Điều chỉnh bằng đo đạc tải, độ trễ và tốc độ dọn thực tế.

**Lưu ý về lỗi giữa chừng:** Nếu một lệnh `UNLINK` hoặc kết nối gặp lỗi sau khi một số lô đã thành công, lần gọi có thể ném ngoại lệ dù Redis đã xóa một phần dữ liệu. Không thể suy ra “toàn bộ tác vụ chưa chạy” từ ngoại lệ. Hãy ghi tiến độ của job, cho phép chạy lại và coi việc xóa key đã mất là thao tác an toàn.

### Khi nào dùng DEL?

Có thể thay `redis.unlink(keys)` bằng `redis.delete(keys)` khi hệ thống cần `DEL`, ví dụ Redis không hỗ trợ `UNLINK` hoặc cần kiểm soát theo đặc thù hạ tầng. Trên tập dữ liệu lớn, cần đánh giá độ trễ vì `DEL` có thể giải phóng đối tượng đồng bộ. Không nên tăng kích thước lô vô hạn cho cả hai phương án.

## 6. Thử thao tác trên Redis CLI ở môi trường thử nghiệm

Tạo dữ liệu minh họa, dùng tên khóa khớp quy ước của ví dụ:

```redis
SET shop:orders:v1:tenant:42:state:OPEN:1001 "draft-A"
SET shop:orders:v1:tenant:42:state:OPEN:1002 "draft-B"
SET shop:orders:v1:tenant:42:state:DONE:1003 "final-C"
SET shop:orders:v1:tenant:73:state:OPEN:2001 "draft-D"
SET shop:products:v1:item:1001 "product"
```

Xem nhóm cần xử lý:

```redis
SCAN 0 MATCH shop:orders:v1:tenant:42:state:OPEN:* COUNT 100
```

Tiếp tục thực hiện `SCAN` bằng cursor mà Redis trả về cho đến khi cursor trở về `0`. Thứ tự khóa và số lượt duyệt không cố định. Sau khi xác nhận hai khóa đúng nhóm, minh họa lệnh xóa:

```redis
UNLINK shop:orders:v1:tenant:42:state:OPEN:1001 shop:orders:v1:tenant:42:state:OPEN:1002
```

Kiểm tra phạm vi bằng `EXISTS`:

```redis
EXISTS shop:orders:v1:tenant:42:state:OPEN:1001
EXISTS shop:orders:v1:tenant:42:state:DONE:1003
EXISTS shop:orders:v1:tenant:73:state:OPEN:2001
```

Nếu không có tác vụ khác ghi hoặc xóa đồng thời, kết quả kỳ vọng lần lượt là `0`, `1` và `1`. Ví dụ CLI xóa hai khóa được nêu tường minh. **Không** truyền trực tiếp mẫu có dấu `*` cho `UNLINK` hoặc `DEL` với kỳ vọng Redis tự khai triển: các lệnh xóa nhận tên khóa cụ thể, không tự duyệt mẫu.

## 7. An toàn khi nhiều tiến trình cùng ghi dữ liệu

`SCAN` và `UNLINK` không tạo một giao dịch bao trùm cả nhóm. Khi worker khác vẫn đang ghi:

- Một khóa mới tạo **sau** khi cursor đã đi qua vùng tương ứng có thể còn lại.
- Khóa hiện hữu có thể hết TTL hoặc bị xóa trước khi lô xử lý tới, khiến số khóa `UNLINK` gỡ được giảm.
- Một khóa có thể được `SCAN` nhìn thấy, sau đó bị xóa rồi **tạo lại với cùng tên** trước `UNLINK`. Lệnh xóa có nguy cơ loại bỏ giá trị mới.
- Người ghi tiếp tục tạo khóa trong namespace sẽ khiến kết quả dọn không ổn định; một vòng quét không bảo đảm namespace rỗng sau khi xong.

Giải pháp tùy yêu cầu nghiệp vụ:

**Dọn cache theo kiểu “best effort”.** Chấp nhận chạy lại một hoặc nhiều lượt, quản lý tiến độ, dùng TTL, và không dựa vào kết quả quét như một ảnh chụp nguyên tử.

**Dọn namespace cũ sau khi chuyển phiên bản.** Đầu tiên chuyển bên đọc và ghi sang tiền tố mới, ví dụ `shop:orders:v2:`, ngừng ghi vào `v1`, rồi dọn `v1`. Với việc cần chắc chắn không còn tác vụ cũ ghi, hãy xác nhận các tiến trình cũ đã dừng hoặc áp dụng cơ chế chuyển đổi phiên bản có kiểm soát trước khi xóa.

**Xóa nhóm có yêu cầu nhất quán cao.** Thiết kế chỉ mục nhóm được cập nhật cùng luồng ghi/xóa, hàng đợi công việc bảo trì, hoặc cơ chế điều phối khóa/phiên bản và thao tác nghiệp vụ cụ thể. Một khóa phân tán chỉ hữu ích nếu **mọi bên ghi liên quan** đều tuân thủ giao thức đó; bản thân khóa không làm `SCAN` trở nên nguyên tử.

Không dùng tác vụ dọn tên khóa làm cách thay thế việc bảo toàn dữ liệu nguồn hay quy trình xóa dữ liệu có quy định riêng.

## 8. Redis Cluster: chú ý node và hash slot

Redis Cluster phân phối key theo **hash slot**, do đó không nên coi toàn cluster là một keyspace đơn duy nhất có thể quét và xóa bằng một lệnh bất kỳ.

Điểm khác so với ví dụ trên:

- `SCAN` làm việc trên keyspace của node đích. Muốn dọn một namespace có khóa nằm ở nhiều node, phải đảm bảo duyệt các **primary node** đang giữ key tương ứng (Spring Data Redis cung cấp `RedisClusterConnection.scan(RedisClusterNode, ScanOptions)`).
- Một lệnh `UNLINK key1 key2 ...` gửi nhiều key khác hash slot có thể gặp `CROSSSLOT`. Phương án đơn giản là xóa từng key qua cơ chế định tuyến theo key; phương án tối ưu hơn là chia lô theo cùng hash slot trước khi gọi lệnh nhiều key.
- Khi topology thay đổi hoặc có resharding trong lúc dọn, job cần cách chạy lại và tái kiểm tra phạm vi. Không suy ra đã quét đủ toàn cluster chỉ từ một cursor của một node.
- Redis có cú pháp `{...}` để đặt các key vào cùng hash slot; chỉ dùng khi thiết kế cần thao tác nhiều key cùng slot và đã đánh giá nguy cơ phân bố tải không đều. Một tenant lớn bị dồn vào một slot có thể gây nóng node.

Nếu ứng dụng sử dụng Redis Cluster, cần triển khai đường duyệt theo cluster và đường xóa theo slot riêng trước khi chạy tác vụ thực tế. Đoạn `OrderKeyCleanupService` ở trên chủ ý chỉ minh họa kết nối Redis độc lập/Sentinel.

## 9. Giảm rủi ro vận hành khi dọn namespace lớn

Một tác vụ xóa số lượng lớn khóa nên có quy trình rõ ràng:

| Biện pháp | Lợi ích và cách áp dụng |
|---|---|
| Chọn tiền tố cụ thể | Cố định ứng dụng, domain, phiên bản và tenant; hạn chế biến đầu vào |
| Xem trước (dry run) | In mẫu và một số khóa mẫu để người vận hành đối chiếu; đây không phải bản kiểm kê đầy đủ |
| Xác nhận phạm vi | Lưu tenant, trạng thái, môi trường và người yêu cầu trước khi cho phép chạy job |
| Hạn mức vận hành | Giới hạn số khóa mỗi lô, tốc độ lệnh và số job đồng thời; có khả năng dừng job |
| Theo dõi tiến độ | Ghi số khóa đã quét, số khóa đã gỡ, thời lượng, lỗi và mẫu nhóm; tránh log dữ liệu nhạy cảm |
| Chạy lại an toàn | Thiết kế job idempotent và xử lý lần xóa trước chỉ hoàn thành một phần |
| Theo dõi tải | Quan sát độ trễ Redis, CPU, mức bộ nhớ và tốc độ cấp phát/giải phóng trong thời gian chạy |
| Quản lý quyền | Chỉ tác vụ được phân quyền mới có thể xóa; nếu phù hợp, giới hạn Redis ACL theo mẫu key |

Với namespace rất lớn, một lời gọi đồng bộ trong luồng HTTP có thể kéo dài quá thời gian xử lý request. Thường nên chuyển sang background job có mã định danh và trạng thái tiến độ, thực thi theo lô và có cơ chế dừng. Không dùng `KEYS` để “đếm trước” trên môi trường đang tải cao; `DBSIZE` đếm toàn database chứ không đếm riêng namespace.

Nếu bắt buộc cần **số lượng key chính xác** trước khi xóa, việc đếm bằng `SCAN` trong môi trường đang ghi đồng thời vẫn có thể bị trùng hoặc thiếu. Nên dùng chỉ mục/metadata có quy ước cập nhật phù hợp, hoặc tạm dừng ghi và kiểm kê trong một giai đoạn được điều phối.

## 10. Khi nào không nên quét namespace?

Duyệt `SCAN MATCH` rất hữu ích khi có nhu cầu dọn định kỳ hoặc điều tra dữ liệu, nhưng không phải luôn là thiết kế tốt nhất cho nghiệp vụ cần truy vấn nhóm thường xuyên.

### Chỉ mục nhóm bằng Redis Set

Có thể duy trì một Set chứa tên các khóa thuộc nhóm:

```text
shop:orders:v1:index:tenant:42:state:OPEN
    -> shop:orders:v1:tenant:42:state:OPEN:1001
    -> shop:orders:v1:tenant:42:state:OPEN:1002
```

Khi ghi key, ứng dụng thêm tên key vào Set bằng `SADD`; khi xóa hoặc đổi nhóm, ứng dụng cập nhật Set tương ứng bằng `SREM`. Khi dọn, duyệt thành viên Set với `SSCAN` rồi xử lý từng key. Cách này tránh phải lọc trên toàn keyspace, nhưng tăng chi phí cập nhật và đòi hỏi giải quyết dữ liệu chỉ mục lỗi thời (chẳng hạn key đã hết TTL nhưng tên vẫn trong Set).

### TTL và versioned namespace

Nếu dữ liệu chỉ có giá trị ngắn hạn, đặt TTL ngay lúc tạo khóa thường đơn giản và an toàn hơn so với job xóa quy mô lớn. Với cache được xây lại từ nguồn khác, chuyển sang namespace theo phiên bản và để bản cũ tự hết hạn có thể giảm công việc duyệt/xóa. Đừng đặt TTL mặc định cho dữ liệu cần tồn tại lâu dài nếu chưa xác định được vòng đời nghiệp vụ.

### Trường hợp xóa chính xác một số key đã biết

Nếu đã có danh sách key cụ thể, gọi `unlink(Collection<String>)` hoặc `delete(Collection<String>)` trực tiếp, không cần `SCAN`. Khi key cần xóa nằm trong một cấu trúc `Hash` hoặc `Set`, dùng thao tác trên field/member (`HDEL`, `SREM`, v.v.) nếu ý định là xóa phần tử, tránh nhầm với việc xóa cả Redis key.

## 11. Những lỗi dễ gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Xóa cả khóa của nhóm khác | Mẫu quá rộng, thiếu dấu `:` cuối prefix, đầu vào chứa ký tự glob | Chuẩn hóa prefix, xác thực segment, đối chiếu dry run |
| Quét được ít khóa hơn dự kiến | `COUNT` bị hiểu là giới hạn tổng, dừng khi trả về danh sách rỗng | Duyệt cursor tới khi kết thúc; nhớ `COUNT` chỉ là gợi ý |
| Sau khi dọn vẫn xuất hiện khóa | Bên ghi vẫn hoạt động, TTL/ghi đồng thời, quét trên một node cluster | Điều phối bên ghi, chạy lại, kiểm tra toàn cluster |
| Kết quả xóa ít hơn số khóa đã thấy | Khóa bị trùng trong `SCAN`, đã hết hạn hoặc bị xóa bởi tiến trình khác | Dùng số `UNLINK` trả về làm số khóa thực xóa |
| Dùng `KEYS` làm Redis tăng độ trễ | Quét và trả về tập khóa lớn trong một lệnh | Dùng `SCAN` và lô nhỏ |
| Lỗi `CROSSSLOT` | Gửi nhiều key từ các slot khác nhau trong Redis Cluster | Nhóm theo slot hoặc xóa từng key qua client cluster |
| Không tìm thấy khóa dù nhìn thấy trong Redis CLI | Khác Redis DB, node, namespace hoặc key serializer | Xác nhận cấu hình kết nối và cách serialize key |
| Job bị ngắt nhưng không rõ đã xóa bao nhiêu | Thao tác gồm nhiều lệnh, mỗi lô thành công riêng | Ghi kết quả từng lô, hỗ trợ retry idempotent |
| Bộ nhớ chưa giảm ngay sau `UNLINK` | Giải phóng bộ nhớ diễn ra bất đồng bộ | Theo dõi tác vụ nền và mức sử dụng bộ nhớ sau một khoảng quan sát phù hợp |

## 12. Ghi nhớ khi áp dụng

Với Spring Data Redis, mô hình thường dùng là **namespace rõ ràng → kiểm tra mẫu → `SCAN` bằng cursor → xử lý/xóa theo lô → quan sát và chạy lại khi cần**. Cần đồng thời phân biệt phạm vi tên khóa với phạm vi hash slot, đếm khóa đã quét với số khóa thực sự bị xóa, và duyệt tăng dần với một ảnh chụp nhất quán.

Mã minh họa phù hợp cho nhóm key cache hoặc dữ liệu tạm được đặt tên theo quy ước, chạy trên Redis độc lập/Sentinel. Khi ứng dụng dùng Redis Cluster, có tải ghi liên tục hoặc cần tính chính xác nghiệp vụ cao, hãy bổ sung cơ chế điều phối và xử lý riêng theo các giới hạn đã nêu.

### Tài liệu tham khảo

- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/)
- [Spring Data Redis — RedisTemplate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/RedisTemplate.html)
- [Spring Data Redis — RedisClusterConnection API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/RedisClusterConnection.html)
