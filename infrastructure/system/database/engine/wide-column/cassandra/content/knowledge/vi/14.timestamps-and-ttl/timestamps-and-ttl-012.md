# Giới hạn thời hạn hoặc mốc thời gian hết hạn theo phiên bản Apache Cassandra

## 1. Bài toán: vì sao một TTL hợp lệ về mặt số học vẫn có thể bị từ chối?

**Apache Cassandra** là cơ sở dữ liệu **wide-column phân tán**. Với dữ liệu cần lưu trong thời gian hữu hạn, ứng dụng có thể chỉ định **time to live (TTL)** trong câu `INSERT`/`UPDATE` hoặc cấu hình `default_time_to_live` cho bảng. TTL được khai báo bằng **số giây** và áp dụng cho các cell được ghi.

Tuy nhiên, **TTL không chỉ bị giới hạn bởi giá trị số nguyên mà CQL nhận được**. Cassandra còn phải biểu diễn **thời điểm hết hạn tuyệt đối** trong metadata nội bộ. Ở các dòng phiên bản sử dụng biểu diễn thời điểm hết hạn bị giới hạn bởi mốc Unix time 32-bit, một TTL quá dài có thể yêu cầu ngày hết hạn nằm **sau mốc mà định dạng lưu trữ hỗ trợ**.

Ví dụ, một hệ thống muốn giữ dữ liệu 20 năm:

```sql
-- Không chạy câu này trên production: chỉ minh họa yêu cầu retention.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (11111111-1212-4121-8121-111111111111, 'long-lived')
USING TTL 630720000;
```

`630720000` giây xấp xỉ 20 năm (nếu tính 365 ngày/năm). Với môi trường có giới hạn expiration tại **19/01/2038**, yêu cầu này **không còn hợp lệ** khi chạy từ những năm gần mốc 2038, dù số `630720000` vẫn nằm trong giới hạn số nguyên 32-bit.

**Đề bài của bài học:** phân biệt **giới hạn giá trị TTL**, **giới hạn thời điểm hết hạn**, và **hành vi khi vượt giới hạn theo phiên bản/cấu hình**; đồng thời xây dựng cách kiểm tra an toàn trong CQL, Java Driver và vận hành cluster.

> **Quan trọng về tính tương thích:** Các mốc và chính sách trong bài được trình bày theo cơ chế giới hạn expiration thường được tài liệu hóa ở nhiều bản Cassandra 3.x/4.x. **Không giả định mọi bản Cassandra, bản phân phối tương thích Cassandra và bản vá đều có cùng giới hạn/hành vi.** Khi triển khai phải đối chiếu phiên bản đang chạy, tài liệu tương ứng và cấu hình thực tế.

## 2. Ba loại thời gian không được nhầm lẫn

Trong chương **Timestamp và TTL**, người học cần phân biệt:

| Thuộc tính | Đơn vị / biểu diễn | Dùng để làm gì? | Liên quan tới giới hạn expiration ra sao? |
|---|---|---|---|
| `USING TTL N` | Số **giây** sống thêm | Đặt hạn sống cho phiên bản cell mới | Cassandra phải tính ngày hết hạn từ thời gian ghi và `N` |
| `default_time_to_live` | Số **giây**, giá trị bảng | TTL mặc định cho cell ghi mới | Ghi không có TTL riêng cũng chịu kiểm tra expiration |
| **Mutation/write timestamp** | Epoch **micro giây** (số nguyên 64-bit) | Phân xử phiên bản cùng cell bằng **last-write-wins** | Không phải mốc dùng để cộng TTL trong bài toán này |
| Cột CQL kiểu `timestamp` | Epoch **mili giây** (64-bit) | Lưu ngày/giờ nghiệp vụ | Có thể chứa mốc xa tương lai mà TTL expiration không hỗ trợ |
| **Expiration/local deletion time** | Mốc thời gian nội bộ ở mức giây | Xác định khi nào cell hết hạn và tuổi metadata xóa | Có thể chịu giới hạn biểu diễn phụ thuộc phiên bản |
| `ttl(column)` | Số **giây còn lại** | Quan sát TTL của cell đang sống | Giúp kiểm chứng TTL thực tế sau ghi; không cho biết chính sách toàn cluster |

Đặc biệt: **cột CQL `timestamp` có thể lưu một ngày sau năm 2038 không có nghĩa cell được phép có TTL kết thúc sau 2038 ở mọi phiên bản Cassandra.**

Một ví dụ hợp lệ về mặt ngữ nghĩa:

```sql
INSERT INTO retention_demo_by_id (item_id, payload, business_deadline)
VALUES (
    22222222-1212-4121-8121-222222222222,
    'has a business deadline',
    '2045-01-01T00:00:00Z'
)
USING TTL 3600;
```

Cell `business_deadline` lưu mốc năm 2045 **như dữ liệu nghiệp vụ**, nhưng TTL của cell chỉ là **3.600 giây kể từ lần ghi**. Đừng dùng kiểu dữ liệu `timestamp` để suy ra khả năng biểu diễn expiration metadata.

## 3. Mốc 2038 và biểu diễn Unix time 32-bit

Với một biểu diễn **số nguyên 32-bit có dấu tính bằng giây kể từ Unix epoch**, giá trị dương lớn nhất là:

```text
2^31 - 1 = 2_147_483_647 giây
          = 2038-01-19T03:14:07Z
```

Mốc này thường được gọi là **vấn đề năm 2038** (*Year 2038 problem*). Những bản Cassandra sử dụng giới hạn kiểu này cho thời điểm hết hạn cần xử lý tình huống:

```text
thời điểm server dùng để tính expiration + TTL yêu cầu
                  > mốc expiration biểu diễn được
```

Minh họa:

```text
                                  2038-01-19 03:14:07 UTC
                                            |
       ngày ghi                             | GIỚI HẠN
          |                                 |
          +--------- TTL ngắn ------------->|  còn trong khoảng hỗ trợ
          |
          +----------------- TTL rất dài --------------------> vượt giới hạn
```

Khi vượt giới hạn, Cassandra **không thể lưu đúng ngày hết hạn mà client yêu cầu** theo biểu diễn hạn chế đó. Một số phiên bản có **chính sách từ chối request hoặc cắt ngắn hạn tại mốc tối đa**. Chính sách và tên cấu hình cụ thể phải được xác minh trên bản Cassandra đang vận hành.

### Không tồn tại một “TTL tối đa 20 năm” bất biến

Nếu hệ thống bị giới hạn bởi mốc tuyệt đối `2038-01-19T03:14:07Z`, **TTL tối đa tính từ thời điểm hiện tại giảm theo từng giây**.

Ví dụ số học, giả sử đồng hồ nguồn thời gian chuẩn đang ở `2038-01-18T03:14:07Z`, tức đúng **86.400 giây** trước mốc trên:

| TTL yêu cầu | Ngày hết hạn dự kiến | Trong giới hạn? |
|---|---|---|
| `3600` giây | Trước mốc 23 giờ | Có |
| `86400` giây | Đúng mốc biên | Tại ranh giới; cần xét quy tắc thực tế và biên an toàn |
| `86401` giây | Sau mốc 1 giây | Không nếu bị giới hạn ở mốc 32-bit này |

Vì vậy đừng hard-code một hằng “20 năm” thành TTL tối đa cho mọi năm, mọi môi trường. Cần suy từ **thời điểm ghi hiện tại, giới hạn phiên bản và khoảng an toàn**.

## 4. Giới hạn kiểu số và giới hạn ngày hết hạn là hai tầng khác nhau

Một giá trị TTL phải qua ít nhất hai câu hỏi:

1. **Có hợp lệ về mặt cú pháp/kiểu số?** CQL TTL biểu diễn bằng giây; giá trị số âm bị từ chối, và kiểu giá trị số cũng có giới hạn.
2. **Ngày hết hạn có hợp lệ trong định dạng lưu trữ và chính sách server?** Dù số TTL nằm trong khoảng giá trị cho phép, `serverNow + ttlSeconds` vẫn có thể vượt mốc expiration hỗ trợ.

Ví dụ:

| Đầu vào | Ý nghĩa / rủi ro |
|---|---|
| `USING TTL 3600` | 1 giờ; thường là trường hợp dễ kiểm soát |
| `USING TTL 0` | **Không áp dụng TTL** cho phiên bản cell mới; không phải “hết hạn ngay” |
| `USING TTL -5` | TTL âm: không hợp lệ |
| `USING TTL 630720000` | Xấp xỉ 20 năm; có thể vượt giới hạn ngày hết hạn tùy năm ghi/phiên bản |
| `USING TTL 2147483647` | Số lớn nhất của signed 32-bit; **không** đồng nghĩa giá trị này dùng được trong thực tế |
| `USING TTL 630720000000` | Rất có thể nhầm **mili giây** thành **giây**, đồng thời vượt phạm vi số/expiration |

**Dấu hiệu lỗi đơn vị:** Java `Duration.toMillis()` trả **mili giây**, trong khi CQL `USING TTL ?` cần **giây**. Với 30 ngày, giá trị đúng là `30 × 24 × 3600 = 2592000` giây; nếu truyền nhầm mili giây sẽ thành `2592000000`, vượt nhiều giới hạn và không mang ý nghĩa retention mong muốn.

## 5. Chính sách khi ngày hết hạn vượt giới hạn: REJECT và CAP

Ở những bản Cassandra có hỗ trợ cấu hình `expiration_date_overflow_policy`, thường gặp các chế độ:

| Chính sách | Hành vi khái niệm khi expiration vượt giới hạn | Rủi ro vận hành |
|---|---|---|
| `REJECT` | Từ chối mutation yêu cầu ngày hết hạn không biểu diễn được | Ứng dụng phải xử lý lỗi, nhưng tránh âm thầm thay đổi retention |
| `CAP` | Giới hạn/cắt ngắn expiration về mốc tối đa được hỗ trợ, thường kèm cảnh báo | Dữ liệu có thể **hết hạn sớm hơn** thời gian client yêu cầu |
| `CAP_NOWARN` | Giới hạn tương tự CAP nhưng không phát cùng mức cảnh báo | Việc cắt ngắn có thể **khó được phát hiện** nếu không đo giám sát |

Tên chế độ và sự tồn tại của cấu hình **phụ thuộc vào phiên bản hoặc bản phân phối**. Không chép nguyên dòng `expiration_date_overflow_policy` vào mọi `cassandra.yaml` nếu chưa xác nhận nó được phiên bản tương ứng nhận diện. Cũng không mặc định giá trị **mặc định** giống nhau trên mọi cluster.

Ví dụ nghiệp vụ yêu cầu lưu hồ sơ 15 năm, nhưng cluster giới hạn expiration chỉ còn khoảng 11 năm:

- Với **REJECT**, ghi có thể báo lỗi ngay. Đây là tín hiệu để điều chỉnh retention hoặc nâng cấp/đổi kiến trúc.
- Với **CAP**, ghi có thể thành công nhưng expiration bị giới hạn. Nếu ứng dụng tưởng dữ liệu chắc chắn sống đủ 15 năm, sẽ phát sinh **vi phạm yêu cầu lưu trữ**.
- Với **CAP_NOWARN**, sự khác biệt có thể chỉ lộ ra khi so TTL quan sát, metrics hoặc kiểm toán chính sách.

**Đặc biệt nguy hiểm:** không được dùng CAP như một cách biến dữ liệu thành “không bao giờ hết hạn”. CAP có thể làm nhiều bản ghi được gắn **chung một mốc hết hạn xa**, gây rủi ro mất dữ liệu hàng loạt khi mốc đó tới, và có thể tăng áp lực tombstone/compaction.

## 6. Phân biệt TTL mặc định của bảng và TTL do câu lệnh chỉ định

Một bảng có `default_time_to_live = 0` nghĩa là **không có TTL mặc định**. Khi đặt thành số dương, Cassandra áp dụng TTL cho các cell mới được ghi nếu câu lệnh không dùng `USING TTL`.

```sql
CREATE TABLE IF NOT EXISTS retention_demo_by_id (
    item_id uuid PRIMARY KEY,
    payload text,
    business_deadline timestamp
) WITH default_time_to_live = 86400;
```

Với bảng này:

```sql
-- 1. Dùng TTL mặc định: 86.400 giây = 1 ngày.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    33333333-1212-4121-8121-333333333333,
    'default-retention'
);

-- 2. TTL riêng 1 giờ ưu tiên hơn TTL mặc định.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    44444444-1212-4121-8121-444444444444,
    'short-retention'
)
USING TTL 3600;

-- 3. TTL 0 cho phiên bản mới: không có TTL.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    55555555-1212-4121-8121-555555555555,
    'persistent'
)
USING TTL 0;
```

Nếu mutation thắng theo timestamp, ba cell `payload` có các chính sách: 1 ngày, 1 giờ và không TTL. Điều đáng chú ý là **cả `default_time_to_live` và `USING TTL` đều phải tuân giới hạn expiration của server**. Việc không viết `USING TTL` trong câu CQL **không né được giới hạn** nếu bảng đang có TTL mặc định quá dài.

Đổi TTL mặc định bằng `ALTER TABLE` chỉ tác động **các mutation về sau**, không tự tính lại ngày hết hạn của cell cũ:

```sql
ALTER TABLE retention_demo_by_id
WITH default_time_to_live = 604800;
```

Lần ghi mới không có TTL riêng sẽ dùng 7 ngày. Các cell đã được ghi theo 1 ngày, 1 giờ hay không TTL **không tự bị viết lại**.

## 7. Thực hành an toàn: quan sát TTL thay vì cố tình tạo expiration lỗi

Để học cơ chế mà không phụ thuộc chính sách overflow của cluster, hãy bắt đầu từ TTL ngắn trong keyspace thử nghiệm.

```sql
-- Dùng UUID mới, tránh giá trị/tombstone từ thử nghiệm trước.
INSERT INTO retention_demo_by_id (item_id, payload)
VALUES (
    66666666-1212-4121-8121-666666666666,
    'ttl-120-seconds'
)
USING TTL 120;

SELECT payload,
       writetime(payload) AS write_timestamp_us,
       ttl(payload) AS remaining_seconds
FROM retention_demo_by_id
WHERE item_id = 66666666-1212-4121-8121-666666666666;
```

Kỳ vọng:

- `remaining_seconds` là số dương gần **120**, giảm dần theo thời gian.
- `write_timestamp_us` là epoch **micro giây**; nó khác hoàn toàn TTL.
- Sau khi hết hạn, `payload` không còn là cell sống để quan sát. CQL không trả “TTL âm”.

Với môi trường thử nghiệm cô lập đã **xác nhận phiên bản và overflow policy**, có thể tạo case lỗi/cắt ngắn theo hướng dẫn kiểm thử của đội vận hành. **Không chạy lệnh TTL cực lớn trên production** chỉ để xem server phản hồi; nếu policy CAP, bạn có thể vô tình tạo dữ liệu sống hàng năm hoặc đến sát mốc biên.

### Kiểm tra thông tin phiên bản và schema

Các truy vấn đọc-only tham khảo trong CQL:

```sql
-- Phiên bản release mà node đang kết nối báo về.
SELECT release_version FROM system.local;

-- Thay demo_ks bằng keyspace thực tế đang thử nghiệm.
SELECT keyspace_name, table_name, default_time_to_live,
       gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'demo_ks'
  AND table_name = 'retention_demo_by_id';
```

`system.local` cho biết phiên bản **node hiện đang được kết nối**, không chứng minh toàn cluster đồng nhất nếu đang rolling upgrade. Nên đối chiếu thông tin tất cả node và bản phân phối, đồng thời kiểm tra tài liệu `cassandra.yaml` đúng phiên bản để biết hỗ trợ/giá trị thực tế của `expiration_date_overflow_policy`.

## 8. Khi triển khai nhiều phiên bản: kiểm tra ở đâu?

Một cluster có thể vận hành **rolling upgrade** trong một khoảng thời gian. Một ứng dụng Java lại có thể nối vào các coordinator khác nhau qua load balancing. Nếu giới hạn, policy hoặc cơ chế expiration **khác nhau giữa các phiên bản**, cùng một yêu cầu TTL cực dài có thể gặp hành vi khác nhau trong giai đoạn chuyển đổi.

Trình tự kiểm tra tương thích nên gồm:

1. Xác định **phiên bản Cassandra cụ thể trên từng node** (kể cả bản vá và bản phân phối).
2. Đọc tài liệu/ghi chú nâng cấp đúng phiên bản về **TTL, expiration timestamp, Year 2038, overflow policy và định dạng SSTable**.
3. Kiểm tra **config thực tế** trên từng node theo quy trình quản trị. Không giả định mọi node đã nhận config mới.
4. Đối chiếu **TTL mặc định của bảng** và tất cả đường ghi `USING TTL` từ các ứng dụng/đường import.
5. Kiểm tra giới hạn qua **canary trong môi trường staging cùng phiên bản**, dùng TTL bảo thủ và các test biên theo phép tính, không cần tạo bản ghi 30 năm trên production.
6. Xác minh chiến lược **rollback và backup** nếu việc thay đổi policy có thể làm dữ liệu hết hạn sớm hoặc mutation bị từ chối.

**Không có một bảng “Cassandra 3.x = X, 4.x = Y, 5.x = Z” đáng tin cậy nếu không xét bản vá và tài liệu đúng deployment.** Học viên nên hiểu nguyên nhân ở tầng định dạng thời gian và quy trình xác minh, thay vì ghi nhớ một giới hạn phiên bản có thể lỗi thời.

### Mốc phiên bản và thay đổi semantics

Khi một phiên bản mới thay đổi cách biểu diễn timestamp expiration hoặc chính sách xử lý overflow, việc chuyển từ phiên bản cũ **không được mặc định là sẽ tự kéo dài TTL của cell đã ghi trước đó**. Metadata expiration đã lưu có thể tiếp tục mang giới hạn/giá trị của thời điểm ghi cũ. Cần đọc hướng dẫn nâng cấp, tương thích SSTable và test dữ liệu nhập từ phiên bản trước.

## 9. Ví dụ số học: tính TTL tối đa động, không hard-code “20 năm”

Nếu một deployment thực sự giới hạn thời điểm expiration bởi signed epoch seconds `2_147_483_647`, giới hạn số học tại một thời điểm được tính:

```text
maxExpirationEpochSeconds = 2_147_483_647
nowEpochSeconds            = thời điểm UTC hiện tại của nguồn đáng tin cậy
safetyMarginSeconds        = biên dự phòng cho clock skew/độ trễ xử lý

maxSafeTtlSeconds =
    maxExpirationEpochSeconds
    - nowEpochSeconds
    - safetyMarginSeconds
```

Với ví dụ **giả định** ở `2038-01-18T03:14:07Z`:

```text
maxExpirationEpochSeconds = 2_147_483_647
nowEpochSeconds           = 2_147_397_247
rawHeadroomSeconds        = 86_400
safetyMarginSeconds       = 300
maxSafeTtlSeconds         = 86_100
```

Nếu cần TTL 86.200 giây, hệ thống có **không đủ biên an toàn**, dù chưa vượt mức biên tuyệt đối 86.400. Hành vi đúng nên là **từ chối/đổi chính sách lưu trữ**, không tự rút về 86.100 khi retention là nghĩa vụ nghiệp vụ buộc phải giữ đủ thời gian.

Phép tính trên chỉ dùng khi **đã xác nhận** giới hạn của deployment. Nếu phiên bản hỗ trợ mốc khác, phải thay giới hạn và thuật toán kiểm tra bằng giá trị tương ứng. Không xem `2_147_483_647` là mốc expiration vĩnh viễn của tất cả các bản Cassandra.

## 10. Java Driver 4.x: kiểm tra TTL và expiration trước khi ghi

Trong Java, prepared statement có thể bind TTL như một số nguyên giây. Đoạn mã minh họa một **policy bảo thủ cho cluster được xác nhận có mốc signed-32-bit 2038**; nó không áp dụng mặc định cho mọi cluster và không thay thế kiểm tra phía server.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class SafeTtlWriter {
    // Chỉ dùng khi đã XÁC NHẬN giới hạn này ở deployment cụ thể.
    private static final long MAX_EXPIRATION_EPOCH_SECONDS = 2_147_483_647L;
    private static final long SAFETY_MARGIN_SECONDS = 300L;

    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement insert;

    public SafeTtlWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.insert = session.prepare(
            "INSERT INTO retention_demo_by_id (item_id, payload) " +
            "VALUES (?, ?) USING TTL ?"
        );
    }

    public void saveFor(UUID id, String payload, Duration retention) {
        if (retention.isNegative() || retention.isZero()) {
            throw new IllegalArgumentException("Retention must be positive");
        }

        long seconds = retention.getSeconds();
        if (seconds <= 0 || seconds > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL seconds out of int range");
        }

        long nowSeconds = clock.instant().getEpochSecond();
        long latestAllowedExpiration = MAX_EXPIRATION_EPOCH_SECONDS
            - SAFETY_MARGIN_SECONDS;
        long expiration = Math.addExact(nowSeconds, seconds);
        if (expiration > latestAllowedExpiration) {
            throw new IllegalArgumentException(
                "TTL would exceed supported expiration horizon"
            );
        }

        // Kiểm tra thực tế cuối cùng vẫn do Cassandra quyết định.
        session.execute(insert.bind(id, payload, Math.toIntExact(seconds)));
    }

    public void saveUntil(UUID id, String payload, Instant expiresAt) {
        long wholeSeconds = Duration.between(clock.instant(), expiresAt)
            .getSeconds();
        if (wholeSeconds <= 0) {
            throw new IllegalArgumentException("Already expired");
        }
        saveFor(id, payload, Duration.ofSeconds(wholeSeconds));
    }
}
```

**Các giới hạn cố ý của ví dụ:**

- `MAX_EXPIRATION_EPOCH_SECONDS` chỉ đúng với **deployment đã xác nhận** mốc 2038. Đối với phiên bản hỗ trợ mốc khác, cấu hình hạn phải được cung cấp bằng chính sách tương ứng thay vì giữ hằng số này.
- `Clock` phải đồng bộ với nguồn đáng tin cậy; server xử lý ghi **sau** khi client kiểm tra. Biên an toàn giúp giảm nhưng không loại bỏ hoàn toàn đua thời gian.
- `Duration.getSeconds()` làm tròn theo số giây nguyên; một retention dưới 1 giây sẽ bị từ chối, tránh biến nhầm thành `TTL 0`.
- `USING TTL 0` mang nghĩa **không TTL**, không có nghĩa “hết hạn ngay”. Không dùng nó để biểu diễn một `expiresAt` đã qua.
- Hàm `saveUntil` tính lại thời gian còn lại trước khi gọi `saveFor`; deadline tuyệt đối vẫn cần kiểm tra trong nghiệp vụ nếu hệ thống yêu cầu độ chính xác cao.
- Có thể thêm giới hạn retention **theo sản phẩm/SLA** thấp hơn rất nhiều giới hạn kỹ thuật; API không nên cho phép người gọi tùy ý đặt TTL nhiều năm.

## 11. Nếu retention vượt giới hạn kỹ thuật: không nên làm gì?

Một số “cách chữa nhanh” nguy hiểm:

| Cách làm | Vì sao sai hoặc rủi ro |
|---|---|
| Truyền `Duration.toMillis()` vào `USING TTL` | Nhầm đơn vị, có thể tạo TTL quá dài hoặc lỗi |
| Dùng `USING TTL 0` khi muốn “hết hạn ngay” | TTL 0 = **không TTL**, có thể giữ dữ liệu vô thời hạn |
| Chọn `CAP` để request không báo lỗi | Có thể âm thầm **rút ngắn** retention bắt buộc |
| Tăng `USING TIMESTAMP` tới ngày tương lai | LWW có thể bị “đầu độc”; **không giải quyết** giới hạn expiration |
| Đổi `default_time_to_live` cực lớn và nghĩ là xong | Các lần ghi về sau vẫn phải qua quy tắc expiration của server |
| Cắt TTL thành các lần gia hạn không có kiểm soát | Dễ gặp downtime, missed renewal, race và dữ liệu hết hạn ngoài dự kiến |
| Giảm `gc_grace_seconds` | Chỉ thay thời gian bảo vệ tombstone, **không** mở rộng mốc expiration |

Nếu yêu cầu lưu trữ bắt buộc vượt horizon hỗ trợ, có thể cân nhắc:

1. **Không dùng TTL cho loại dữ liệu đó.** Lưu `expires_at`/`retention_until` như **dữ liệu nghiệp vụ**, với điều kiện rõ ràng ở các đường đọc và một quy trình lưu trữ/xóa được quản lý.
2. **Chọn tầng lưu trữ lưu trữ dài hạn** phù hợp retention/compliance (bao gồm backup, audit, phân quyền và quy trình xóa thực tế).
3. **Nâng cấp hoặc đổi phiên bản/kiến trúc** chỉ sau khi xác minh phiên bản mục tiêu hỗ trợ giới hạn mới và có đường di trú dữ liệu.
4. **Gia hạn có điều phối** chỉ nếu đúng mục tiêu nghiệp vụ và chấp nhận được rủi ro. Phải có owner, monitoring, retry/idempotency, cơ chế phát hiện khi lịch gia hạn thất bại, và không dựa vào TTL đơn thuần như bằng chứng compliance.

Việc lưu `expires_at` mà không có TTL **không tự xóa dữ liệu**. Nếu chọn phương án đó, cần thiết kế **quy trình purge riêng** và chiến lược truy vấn theo partition/time bucket, thay vì quét bảng với `ALLOW FILTERING`.

## 12. TTL dài, tombstone, compaction và repair

Khi cell hết TTL, Cassandra không còn coi nó là giá trị sống. Metadata expiration/tombstone giúp ngăn bản cũ từ replica hoặc SSTable khác tái xuất hiện. **Thu hồi byte vật lý** xảy ra qua compaction khi đủ điều kiện an toàn, không nhất thiết đúng thời điểm TTL kết thúc.

Một TTL bị CAP tới mốc expiration tối đa có thể dẫn tới nhiều cell **hết hạn gần cùng một thời điểm**. Những hệ quả cần xét:

- Nhiều tombstone/expired cells xuất hiện trong một khoảng ngắn khi mốc tới.
- Áp lực **đọc, compaction, dung lượng đĩa và garbage collection tombstone** tăng.
- Replica tạm mất kết nối có thể không nhận được tất cả mutation, nên **repair** và `gc_grace_seconds` vẫn quan trọng để ngăn **zombie data**.
- Hết hạn logic không bảo đảm dữ liệu đã biến mất khỏi **snapshot, backup hoặc SSTable** ngay.

Với workload time-series có thời hạn đồng nhất, có thể cân nhắc **TimeWindowCompactionStrategy (TWCS)** cùng time bucket phù hợp. Nhưng TTL cực dài, write timestamp quá khứ/tương lai, backfill và cập nhật ngẫu nhiên có thể làm các cửa sổ SSTable chồng lấp, cản trở việc dọn dữ liệu. Không chọn compaction strategy chỉ theo một con số TTL.

**Replication factor (RF)** và **consistency level (CL)** là cơ chế khác: `ONE`, `QUORUM`, `ALL` không sửa giới hạn expiration, cũng không thay đổi cách phân xử LWW theo mutation timestamp.

## 13. Thiết kế bảng theo truy vấn khi retention rất dài

Trong Cassandra, nên lựa chọn thiết kế bảng theo **những truy vấn ứng dụng sẽ chạy**, không lấy TTL làm cơ chế sắp xếp.

Giả sử hệ thống lưu giao dịch bất biến cần truy vấn theo khách hàng và tháng:

```sql
CREATE TABLE IF NOT EXISTS audit_events_by_account_month (
    account_id uuid,
    event_month text,
    event_time timeuuid,
    event_type text,
    payload text,
    retention_until timestamp,
    PRIMARY KEY ((account_id, event_month), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

SELECT event_time, event_type, retention_until
FROM audit_events_by_account_month
WHERE account_id = 77777777-1212-4121-8121-777777777777
  AND event_month = '2026-11'
LIMIT 100;
```

Ở đây:

- `event_time` là **clustering key** phục vụ truy vấn lịch sử.
- `retention_until` là **thời điểm nghiệp vụ** có thể nằm xa trong tương lai, độc lập với TTL.
- Nếu yêu cầu lưu giữ dài hơn TTL hỗ trợ, có thể **không đặt TTL** cho loại dữ liệu này và dùng quy trình retention/purge riêng được kiểm soát.
- `event_month` là bucket nhằm giới hạn kích thước partition; chọn kích thước bucket theo lưu lượng thật.
- `timeuuid` hỗ trợ thứ tự theo thành phần thời gian nhưng không giải quyết hoàn toàn clock skew giữa nhiều writer. Nếu thứ tự nghiệp vụ tuyệt đối quan trọng, cần sequence/nguồn điều phối phù hợp.

**Đừng viết `ORDER BY writetime(payload)`** và đừng dùng mutation timestamp như thời điểm retention mặc định: đó là metadata LWW, không phải cấu trúc truy vấn hay hợp đồng lưu trữ.

## 14. Chẩn đoán khi TTL quá dài bị lỗi hoặc bị cắt ngắn

Một checklist phù hợp cho đội Java/Cassandra:

| Hiện tượng | Khả năng | Kiểm tra |
|---|---|---|
| Câu `INSERT USING TTL` bị từ chối dù TTL là số dương | Ngày hết hạn vượt horizon; giá trị TTL không hợp lệ hoặc policy REJECT | Phiên bản node, lỗi server, epoch seconds, TTL yêu cầu, policy |
| Ghi thành công nhưng `ttl(col)` nhỏ hơn nhiều so với TTL yêu cầu | CAP đã giới hạn expiration, hoặc ghi khác đang thắng | Cấu hình overflow, `writetime()`, lịch sử update, replica |
| Cùng request lúc được chấp nhận, lúc lỗi | Khác coordinator/config trong mixed-version cluster hoặc thay đổi policy | Phiên bản/config từng node, routing, logs |
| Dữ liệu được giữ lâu hơn yêu cầu | TTL 0, không TTL, default TTL khác hoặc ghi lặp gia hạn | CQL thực gửi, schema, retry và TTL của cell thắng |
| Dữ liệu hết sớm hơn nghĩa vụ lưu trữ | Policy CAP hoặc ứng dụng tự giới hạn TTL quá thấp | Log TTL tính toán, `retention_until`, giá trị `ttl()` gần lúc ghi |
| `ttl(col) = null` nhưng giá trị còn | Cell không có TTL | `USING TTL 0`, bảng default TTL, lần UPDATE cuối |
| TTL không đổi sau `UPDATE` | Mutation không thắng LWW hoặc chưa đọc được phiên bản mới | `writetime()`, nguồn timestamp, CL/replica |
| Hết TTL nhưng đĩa không giảm | Tombstone/SSTable chưa được compaction dọn an toàn | Compaction, `gc_grace_seconds`, snapshot/backup |

Nên log có cấu trúc: `requestId`, loại nghiệp vụ, `ttlRequestedSeconds`, `expiresAtBusinessUtc`, phiên bản/định tuyến coordinator nếu theo dõi được, timestamp mutation nếu client cấp, và lỗi Cassandra. **Không log token thật, thông tin xác thực hoặc dữ liệu nhạy cảm không cần thiết.**

Để phân biệt CAP với retry/ghi đè, đọc `ttl(col)` **ngay sau lần ghi canary** trên một khóa mới; sau đó đối chiếu kết quả với TTL yêu cầu và thời gian trôi qua. Tuy nhiên không dựa duy nhất vào một phép đọc vì đồng hồ, độ trễ và consistency level có thể làm giá trị quan sát khác đôi chút.

## 15. Quy trình vận hành cho giới hạn expiration theo phiên bản

Khi chuẩn bị nâng TTL retention từ vài ngày lên nhiều năm, nên thực hiện theo thứ tự:

1. **Xác định SLA và retention policy**: cần lưu chính xác tối thiểu bao lâu, được xóa từ khi nào, có yêu cầu pháp lý/audit hay không.
2. **Kiểm kê Cassandra deployment**: phiên bản mọi node, bản phân phối, patch level, metadata/schema, timestamp generator, đồng hồ UTC.
3. **Đọc tài liệu đúng phiên bản**: giới hạn ngày hết hạn, `expiration_date_overflow_policy` nếu có, các thay đổi liên quan Year 2038 và nâng cấp SSTable.
4. **Tính ngày hết hạn cuối cùng** theo nguồn thời gian đáng tin cậy, có biên an toàn cho quá trình ghi.
5. **Chọn hành vi bảo đảm nghĩa vụ**: REJECT thường giúp phát hiện vi phạm retention rõ ràng hơn CAP, nhưng không thay thế kế hoạch xử lý lỗi và phục hồi.
6. **Thử trên staging/canary**: kiểm tra `USING TTL`, `default_time_to_live`, TTL 0, `ttl(col)`, lỗi overflow và thời gian thực tế.
7. **Triển khai với giám sát**: đếm rejected/capped requests, clock skew, tombstone/compaction, repair và mức dùng đĩa.
8. **Có phương án rollback** cho thay đổi cấu hình hoặc schema, không giả định đổi policy sẽ tự sửa metadata TTL của những cell đã ghi.

Những nhiệm vụ quản trị như chỉnh `cassandra.yaml`, cập nhật cluster hoặc đổi compaction strategy cần tuân quy trình có kiểm soát. **Không chỉnh trực tiếp SSTable hay rút ngắn `gc_grace_seconds` để né lỗi expiration.**

## 16. Bài tập tình huống và đáp án

**Câu 1.** Vì sao một TTL khoảng 20 năm có thể hợp lệ về kiểu số nhưng bị từ chối bởi một Cassandra deployment năm 2026?

**Đáp án:** Vì ngày hết hạn dự kiến có thể vượt **mốc expiration tối đa** của phiên bản/định dạng metadata, chẳng hạn mốc signed-32-bit năm 2038, dù `ttlSeconds` vẫn nằm trong phạm vi số nguyên cho phép.

**Câu 2.** Với hệ thống giới hạn ở `2038-01-19T03:14:07Z`, TTL tối đa an toàn ở mọi thời điểm có luôn bằng 20 năm không?

**Đáp án:** Không. Thời gian còn tới mốc giới hạn **giảm dần**, nên TTL tối đa động phải tính từ giờ hiện tại và thêm biên an toàn.

**Câu 3.** Ngày hết hạn bị vượt giới hạn; policy `CAP` có luôn đáp ứng đúng yêu cầu retention 15 năm không?

**Đáp án:** Không. CAP có thể **rút ngắn** ngày hết hạn về mốc hỗ trợ. Nếu retention là nghĩa vụ tối thiểu, việc này có thể vi phạm yêu cầu dù request báo thành công.

**Câu 4.** Nếu cột CQL `timestamp` có thể lưu ngày năm 2045, ta có thể suy ra cell luôn được phép hết TTL vào năm 2045 không?

**Đáp án:** Không. Cột `timestamp` là **dữ liệu nghiệp vụ 64-bit ở mili giây**, không quyết định giới hạn expiration metadata của TTL.

**Câu 5.** `USING TTL 0` có phải cách làm một bản ghi hết hạn ngay khi xác định `expiresAt` đã qua không?

**Đáp án:** Không. TTL 0 nghĩa là **không TTL**. Với đối tượng đã quá hạn, nên từ chối ghi hoặc xử lý xóa/logic nghiệp vụ phù hợp.

**Câu 6.** Câu lệnh `INSERT` không có `USING TTL` nhưng bảng có `default_time_to_live` rất dài. Nó có tránh được giới hạn expiration không?

**Đáp án:** Không. TTL mặc định vẫn được áp dụng cho cell mới và phải chịu kiểm tra giới hạn ngày hết hạn.

**Câu 7.** Một ứng dụng Java sử dụng `Duration.toMillis()` làm tham số `USING TTL ?`. Lỗi là gì?

**Đáp án:** Nhầm **mili giây** với **giây**; cần chuyển đổi `Duration` sang giây hợp lệ, kiểm tra biên và deadline.

**Câu 8.** Một rolling upgrade có node khác phiên bản/config. Có nên tin `SELECT release_version FROM system.local` trên một coordinator là bằng chứng cả cluster đồng nhất không?

**Đáp án:** Không. Truy vấn phản ánh node kết nối; cần kiểm kê phiên bản/config của **tất cả node**.

**Câu 9.** Nếu không thể dùng TTL cho yêu cầu lưu 30 năm, có thể lưu `retention_until timestamp` mà không có TTL không? Điều gì còn thiếu?

**Đáp án:** Có thể lưu hạn nghiệp vụ theo schema phù hợp, nhưng phải có **quy trình retention/purge, backup/audit và kiểm tra hạn** riêng. Cột thời gian tự nó không xóa dữ liệu.

**Câu 10.** Điều gì xảy ra nếu nhiều bản ghi bị CAP về một mốc expiration chung?

**Đáp án:** Chúng có thể **hết hạn tập trung**, tạo tải tombstone/compaction và rủi ro lưu trữ nghiệp vụ không đúng kỳ vọng. CAP không phải cách khắc phục mặc định.

---

**Ghi nhớ:** **Giới hạn giá trị TTL khác với giới hạn mốc thời gian hết hạn**. Ở các phiên bản Cassandra có horizon expiration kiểu signed epoch seconds, **19/01/2038** là một mốc quan trọng, khiến TTL tối đa **giảm theo thời gian**. Hành vi khi vượt mốc có thể là **từ chối hoặc giới hạn thời hạn** tùy phiên bản và `expiration_date_overflow_policy`. Trước khi dùng TTL dài, phải xác minh phiên bản/config thực tế, kiểm tra ở Java và server, không nhầm TTL giây với timestamp milli/micro giây, và không để một policy CAP làm thay đổi nghĩa vụ retention mà không được phát hiện.
