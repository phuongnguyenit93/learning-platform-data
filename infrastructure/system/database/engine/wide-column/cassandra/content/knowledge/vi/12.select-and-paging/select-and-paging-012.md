# Phân trang bằng paging state và giới hạn truy cập tiến trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Cassandra trả kết quả `SELECT` lớn theo **các trang của giao thức** thay vì đẩy toàn bộ vào một response.
2. Phân biệt **page size**, `LIMIT`, `PER PARTITION LIMIT` và số bản ghi hiển thị trên một trang của API.
3. Sử dụng `paging state` để **tiếp tục đúng truy vấn đã chạy** và hiểu rõ giới hạn **chỉ đi tới trang kế tiếp**.
4. Viết code Java Driver 4.x theo cả hai kiểu: `ResultSet` đồng bộ tự fetch và `AsyncResultSet` tải trang tường minh.
5. Xây API trả `nextPageToken`, giữ nguyên query và bind values, tránh bỏ sót dòng khi chưa xử lý hết trang.
6. Giải thích tại sao paging state không hỗ trợ tự nhiên “trang 37”, “trang trước” hoặc `OFFSET`, và khi nào keyset cursor là lựa chọn tốt hơn.
7. Thiết kế an toàn khi có thay đổi dữ liệu, TTL, replica chưa hội tụ, retry, yêu cầu đa tenant và token do client cung cấp.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Apache Cassandra là cơ sở dữ liệu wide-column phân tán: partition key xác định nơi lưu dữ liệu, clustering columns xác định thứ tự các dòng trong một partition, còn replication và consistency quyết định điều kiện phục vụ đọc. Phân trang giúp ứng dụng Java không phải nhận toàn bộ kết quả trong một response, **nhưng không sửa một truy vấn có đường đọc sai hoặc quét quá nhiều partition**.

## 1. Vì sao có paging và tại sao gọi là truy cập tiến?

Giả sử một tài khoản có hàng chục nghìn sự kiện trong một ngày. API cần xem lịch sử, nhưng màn hình chỉ hiển thị khoảng hai mươi dòng mỗi lần.

Nếu lấy tất cả cùng lúc:

```sql
-- Không nên trả toàn bộ lịch sử lớn cho một request HTTP.
SELECT happened_at, event_id, event_type, summary
FROM event_history_by_user_day
WHERE user_id = ?
  AND event_day = ?;
```

Ứng dụng có thể phải nhận nhiều dữ liệu hơn khả năng hiển thị, tốn băng thông, bộ nhớ, chuyển đổi đối tượng, và tạo response quá lâu. Native protocol của Cassandra hỗ trợ **paging**: server trả kết quả thành các đợt, kèm trạng thái để tiếp tục khi còn dữ liệu.

```text
Client / Java Driver                          Cassandra
        |                                         |
        |--- SELECT + page size 2 -------------->|
        |<-- rows của page 1 + paging state S1 --|
        |                                         |
        |--- cùng SELECT + S1 ------------------>|
        |<-- rows của page 2 + paging state S2 --|
        |                                         |
        |--- cùng SELECT + S2 ------------------>|
        |<-- page 3, hết dữ liệu -----------------|
        |
        +--> nextPageToken = null
```

`Paging state` là một **giá trị opaque**: ứng dụng **không giải mã để đoán vị trí**, không tính toán `S2` từ `S1`, và không coi nó là ID của một hàng. Nó được tạo cho việc **tiếp tục câu truy vấn hiện tại về phía trước**. Muốn có trang tiếp theo, thông thường phải đi qua trang trước để lấy được trạng thái của trang tiếp theo.

**Truy cập tiến (forward-only)** có nghĩa:

- Có thể lấy **trang kế tiếp** từ paging state hiện tại.
- Không có token “lùi một trang” được Cassandra tự trả cho truy vấn trước.
- Không có truy cập ngẫu nhiên hiệu quả kiểu “tới ngay trang 37” chỉ dựa vào số trang.
- Có thể **lưu các token trang trước ở ứng dụng** để thực hiện lại truy vấn tới những điểm đã biết, nhưng đó là quản lý lịch sử token của ứng dụng, không phải native backward paging.

Đây là khác biệt quan trọng so với trải nghiệm phân trang theo số trang của nhiều hệ SQL quan hệ.

## 2. Page size, LIMIT, PER PARTITION LIMIT và trang UI khác nhau thế nào?

| Khái niệm | Phạm vi ảnh hưởng | Không đồng nghĩa với |
| --- | --- | --- |
| **Page size** (ví dụ `setPageSize(20)`) | Mục tiêu số dòng trả về trong **mỗi lần fetch** của Cassandra | Tổng số dòng; số partition; giới hạn row scan |
| **`LIMIT 100`** | Tối đa 100 dòng **trong toàn bộ kết quả** của câu CQL | 100 dòng trên **mỗi** network page |
| **`PER PARTITION LIMIT 2`** | Tối đa 2 dòng **mỗi partition** được chọn | 2 partition hoặc 2 dòng tổng |
| **Trang UI 20 bản ghi** | Chính sách hiển thị của ứng dụng | Một page giao thức luôn đúng 20 dòng |
| **Paging state** | Vị trí tiếp tục **cùng câu truy vấn** | `OFFSET`, page number hay cursor theo khóa nghiệp vụ |

Ví dụ:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = ?
  AND event_day = ?
ORDER BY happened_at DESC, event_id DESC
LIMIT 100;
```

Nếu Java Driver có page size `20`, Cassandra có thể trả kết quả qua nhiều lần fetch, nhưng **tổng kết quả không vượt `LIMIT 100`**. Ngược lại, nếu dữ liệu chỉ có 6 dòng thì tổng vẫn là 6, không có chuyện server sinh cho đủ 20 hay 100.

**Page size là một gợi ý**, không phải cam kết cứng rằng mỗi response luôn đúng N dòng. Server có thể trả ít hơn hoặc nhiều hơn một chút do các điều kiện của giao thức/thực thi. Do đó một API bắt buộc “đúng 20 dòng trên mỗi trang UI” cần chính sách **buffering, overfetch hoặc cursor ứng dụng** riêng; không nên giả định mỗi trang native protocol có cardinality chính xác.

**Cảnh báo:** Tăng `setPageSize` không khiến `WHERE` thiếu partition key trở nên hợp lệ. Giảm page size không sửa được `ALLOW FILTERING` hoặc việc đọc hàng trăm partition không cần thiết.

## 3. Lab CQL: một partition có sáu sự kiện

### 3.1. Tạo keyspace và bảng

Giả sử ứng dụng lưu sự kiện cho **mỗi người dùng/ngày**, sắp theo mới nhất trước.

```sql
-- SimpleStrategy/RF=1 chỉ dùng trong lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_paging_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_paging_lab;

CREATE TABLE IF NOT EXISTS event_history_by_user_day (
    user_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((user_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id DESC);
```

Các thành phần khóa:

| Thành phần | Vai trò | Ảnh hưởng phân trang |
| --- | --- | --- |
| `(user_id, event_day)` | Composite partition key | Giới hạn truy vấn ở một partition của một người dùng/ngày. |
| `happened_at` | Clustering column thứ nhất | Duyệt theo thời gian mới nhất trước. |
| `event_id` | Clustering column thứ hai | Phân biệt sự kiện trùng timestamp để thứ tự xác định. |
| `event_type`, `summary` | Regular columns | Dữ liệu hiển thị; không tham gia tính token hay sắp xếp khóa. |

### 3.2. Nạp tám dòng, trong đó sáu dòng ở partition chính

```sql
-- User A, ngày 20/11: sáu sự kiện.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem danh sach'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Mo chi tiet'
);

-- Hai sự kiện cùng timestamp: không được dùng timestamp duy nhất làm cursor.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Thanh toan'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'SHIP', 'Da gui hang'
);

INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 13:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGOUT', 'Dang xuat'
);

-- User A/ngày 21: partition khác.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 07:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGIN', 'Ngay moi'
);

-- User B/ngày 20: partition thứ ba.
INSERT INTO event_history_by_user_day
    (user_id, event_day, happened_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 08:30:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'User B'
);
```

Tập dữ liệu mẫu có **8 dòng ở 3 partition**. Truy vấn chính theo User A/ngày 20 lấy **6 dòng**, theo thứ tự clustering:

| Thứ tự | `happened_at` UTC | `event_id` (đuôi) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 13:00 | `...0006` | `LOGOUT` |
| 2 | 12:00 | `...0005` | `SHIP` |
| 3 | 10:00 | `...0004` | `PAY` |
| 4 | 10:00 | `...0003` | `CLICK` |
| 5 | 09:00 | `...0002` | `VIEW` |
| 6 | 08:00 | `...0001` | `LOGIN` |

Hai dòng lúc `10:00` được phân biệt bằng `event_id`. Chạy lại `INSERT` trên cùng full primary key là **upsert**, không tạo dòng trùng khóa. Con số chỉ đúng khi lab chưa có dữ liệu khác hoặc ghi/xóa đồng thời.

## 4. Xem trang bằng cqlsh: phân biệt công cụ và CQL

Trong `cqlsh` có lệnh điều khiển hiển thị/nhận trang, ví dụ:

```sql
-- Đây là lệnh của cqlsh, không phải cú pháp SELECT của CQL.
PAGING 2;

SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY happened_at DESC, event_id DESC;

PAGING OFF;
```

Với page size mục tiêu là hai, các trang **thường** xuất hiện như:

```text
Page 1: LOGOUT/0006, SHIP/0005
Page 2: PAY/0004, CLICK/0003
Page 3: VIEW/0002, LOGIN/0001
```

Lệnh `PAGING` là tính năng của **cqlsh**, còn `paging state` là trạng thái ở giao thức/driver. Không nhầm lời nhắc “more” của terminal với một API paging token do ứng dụng Java quản lý.

Để chỉ lấy tối đa ba dòng **trong toàn truy vấn**:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY happened_at DESC, event_id DESC
LIMIT 3;
```

`LIMIT 3` không có nghĩa mỗi page gồm ba dòng; nó đặt trần cho **tập kết quả hoàn chỉnh** của câu `SELECT`.

## 5. Java Driver 4.x: phân trang đồng bộ tự động

Java Driver 4.x có hai cách xử lý chính:

- `session.execute(...)` trả `ResultSet`. Khi vòng lặp đồng bộ đi qua ranh giới page, driver **tự yêu cầu trang tiếp theo**. Một vòng lặp tưởng như xử lý “một trang” có thể vô tình đọc hết lịch sử.
- `session.executeAsync(...)` trả `CompletionStage<AsyncResultSet>`. `currentPage()` chỉ duyệt những dòng của **trang hiện tại**, và `fetchNextPage()` phải được gọi tường minh khi cần.

### 5.1. Vòng lặp đồng bộ: tiện nhưng có thể đọc hết các trang

Ví dụ Java 17, Java Driver 4.x, giả định `CqlSession session` kết nối keyspace `cassandra_paging_lab`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare("""
    SELECT happened_at, event_id, event_type
    FROM event_history_by_user_day
    WHERE user_id = ?
      AND event_day = ?
    ORDER BY happened_at DESC, event_id DESC
    """);

UUID userId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

BoundStatement request = prepared.bind(userId, day)
    .setPageSize(2);

ResultSet rs = session.execute(request);
for (Row row : rs) {
    // Khi hết page hiện tại, driver có thể tự fetch page kế tiếp.
    System.out.printf("%s %s%n",
        row.getInstant("happened_at"),
        row.getString("event_type"));
}
```

Vòng lặp có thể in **cả sáu dòng**, mặc dù `setPageSize(2)`. Page size không phải `LIMIT 2` và không phải cam kết vòng lặp chỉ xử lý một network response.

Đây là mẫu hợp lý cho batch nhỏ cần duyệt hết kết quả, nhưng **không** nên dùng nguyên xi trong endpoint muốn trả đúng một page rồi dừng.

### 5.2. Lấy đúng những dòng hiện có mà không tự fetch

Trong `ResultSet` đồng bộ, có thể dùng `getAvailableWithoutFetching()` để biết số dòng **đang sẵn** mà không phải fetch page sau. Nếu muốn lưu paging state tại ranh giới page, lấy state và xử lý hết page đang có:

```java
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

ResultSet rs = session.execute(request);

// Lưu vị trí bắt đầu của PAGE KẾ TIẾP.
PagingState next = rs.getExecutionInfo().getSafePagingState();

// Bắt buộc xử lý hết page hiện tại trước khi dùng 'next'.
while (rs.getAvailableWithoutFetching() > 0) {
    Row row = rs.one();
    if (row == null) {
        break;
    }
    System.out.println(row.getUuid("event_id"));
}

String nextToken = next == null ? null : next.toString();
```

**Bẫy rất quan trọng:** `getSafePagingState()` của execution info đại diện cho **trang sau page hiện tại**, không đại diện cho dòng cuối mà ứng dụng vừa xử lý. Nếu bạn lưu state ấy rồi chỉ xử lý **một trong hai dòng** của page hiện tại, request sau bắt đầu ở page tiếp theo và **bỏ mất dòng còn lại**.

Thực hiện kiểu đồng bộ bằng `getAvailableWithoutFetching()` cũng cần cẩn thận với thời điểm lấy `ExecutionInfo` và chính sách prefetch của driver. Khi mục tiêu chính là tự điều khiển từng trang, API bất đồng bộ `AsyncResultSet` thường dễ thể hiện ranh giới rõ hơn.

## 6. Java Driver 4.x: từng trang tường minh bằng AsyncResultSet

### 6.1. Chỉ xử lý currentPage()

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

BoundStatement bound = prepared.bind(userId, day)
    .setPageSize(2);

CompletionStage<AsyncResultSet> pageFuture =
    session.executeAsync(bound);

CompletionStage<Void> firstPageOnly = pageFuture.thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getString("event_type"));
    }
    System.out.println("Con trang sau? " + page.hasMorePages());
});
```

Không gọi `fetchNextPage()` thì đoạn code trên **chỉ duyệt trang hiện tại**. Nó không âm thầm tải mọi trang như vòng lặp trên `ResultSet` đồng bộ.

### 6.2. Duyệt hết tất cả trang một cách bất đồng bộ

Với công việc batch **chủ động muốn đọc hết** một partition hữu hạn, có thể nối các futures:

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

static CompletionStage<Long> countRowsByPages(
        AsyncResultSet page, long countSoFar) {
    long count = countSoFar;
    for (Row row : page.currentPage()) {
        count++;
        // Trong ứng dụng thật: xử lý Row một cách có giới hạn tài nguyên.
    }

    if (!page.hasMorePages()) {
        return CompletableFuture.completedFuture(count);
    }
    final long nextCount = count;
    return page.fetchNextPage()
        .thenCompose(next -> countRowsByPages(next, nextCount));
}

// Khi gọi trong một method có session, bound:
CompletionStage<Long> total =
    session.executeAsync(bound)
        .thenCompose(page -> countRowsByPages(page, 0L));
```

Với dữ liệu mẫu, `total` hoàn tất với giá trị **6**. Ví dụ chỉ minh họa vòng lặp theo protocol page; `countRowsByPages` **không** thay thế trực tiếp `SELECT COUNT(*)` trong mọi bài toán thống kê, và không nên quét partition lớn trong request HTTP chỉ để đếm tổng.

### 6.3. Lấy paging state từ trang bất đồng bộ

```java
import com.datastax.oss.driver.api.core.cql.PagingState;

session.executeAsync(bound).thenAccept(page -> {
    for (Row row : page.currentPage()) {
        System.out.println(row.getString("event_type"));
    }

    PagingState state = page.hasMorePages()
        ? page.getExecutionInfo().getSafePagingState()
        : null;

    String nextToken = state == null ? null : state.toString();
    System.out.println("nextToken co? " + (nextToken != null));
});
```

Thư viện có hai biểu diễn:

- `getPagingState()`: dạng **raw** `ByteBuffer`, không có lớp kiểm tra an toàn bổ sung của driver.
- `getSafePagingState()`: dạng `PagingState`, chứa cơ chế phát hiện sử dụng lại state với sai query/bind values.

Tên `safe` ở đây nói tới **kiểm tra tính tương ứng truy vấn**, **không** phải bảo mật mật mã chống sửa token từ client. Nội dung token vẫn phải được bảo vệ khi đi qua HTTP.

## 7. Dựng API forward-only trả nextPageToken

Giả sử endpoint:

```text
GET /users/{userId}/events?day=2026-11-20
GET /users/{userId}/events?day=2026-11-20&pageToken=...
```

Request đầu không có `pageToken`: bắt đầu từ đầu kết quả. Response trả dữ liệu cùng token cho trang kế tiếp nếu còn. Request sau gửi lại **cùng user/day/query**, chỉ thêm paging state.

### 7.1. Mẫu response ứng dụng

```json
{
  "items": [
    {
      "happenedAt": "2026-11-20T13:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000006",
      "eventType": "LOGOUT"
    },
    {
      "happenedAt": "2026-11-20T12:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000005",
      "eventType": "SHIP"
    }
  ],
  "nextPageToken": "<opaque-token-issued-by-server>"
}
```

Đây là **ví dụ cấu trúc JSON**, không phải một token paging state thật. Không thể tự đoán hoặc bịa token từ `happenedAt`/`eventId`. Khi hết dữ liệu, trả `nextPageToken: null` hoặc bỏ trường tùy hợp đồng API.

### 7.2. Mã Java hoàn chỉnh về logic lấy một page

Ví dụ Java 17 và Java Driver 4.x. Để code ngắn và dễ đọc, phần ký/xác thực token HTTP được mô tả ở mục 8, **chưa triển khai** trong hàm minh họa này; không dùng token thô trực tiếp trong endpoint production.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

record EventItem(Instant happenedAt, UUID eventId, String eventType) {}
record EventPage(List<EventItem> items, String nextPageToken) {}

static CompletionStage<EventPage> loadOnePage(
        CqlSession session,
        PreparedStatement prepared,
        UUID userId,
        LocalDate day,
        String previousPageToken) {

    // Query và bind values phải nhất quán qua các page.
    BoundStatement statement = prepared.bind(userId, day)
        .setPageSize(2);

    if (previousPageToken != null && !previousPageToken.isBlank()) {
        // CHỈ dùng trực tiếp trong lab; production phải verify
        // chữ ký/HMAC/AEAD và ràng buộc tenant, expiry trước khi parse.
        PagingState previous = PagingState.fromString(previousPageToken);
        statement = statement.setPagingState(previous);
    }

    return session.executeAsync(statement).thenApply(page -> {
        List<EventItem> items = new ArrayList<>();
        for (Row row : page.currentPage()) {
            items.add(new EventItem(
                row.getInstant("happened_at"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }

        PagingState next = page.hasMorePages()
            ? page.getExecutionInfo().getSafePagingState()
            : null;
        String rawNextToken = next == null ? null : next.toString();

        // Production: wrap rawNextToken bằng token được ký/mã hóa,
        // gắn userId, day, query version, expiry; không trả raw.
        return new EventPage(List.copyOf(items), rawNextToken);
    });
}
```

Cách sử dụng:

```java
PreparedStatement listQuery = session.prepare("""
    SELECT happened_at, event_id, event_type
    FROM event_history_by_user_day
    WHERE user_id = ?
      AND event_day = ?
    ORDER BY happened_at DESC, event_id DESC
    """);

UUID userId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

CompletionStage<EventPage> first =
    loadOnePage(session, listQuery, userId, day, null);

// Sau khi có response: giữ nextPageToken, gửi lại token ấy
// với cùng userId và day để lấy trang tiếp theo.
```

**Điểm cần bảo đảm trong ứng dụng thật:**

1. `loadOnePage` chỉ đọc `currentPage()`, không gọi `fetchNextPage()`, nên không chủ động tải tất cả các trang.
2. `PagingState.fromString` và `setPagingState(PagingState)` bảo toàn kiểu state của driver; `setPagingState` có kiểm tra state khớp statement đã bind.
3. Khi `hasMorePages()` sai hoặc state trả về null, `nextPageToken` là null.
4. Query string, bind values, projection và logic lọc/`ORDER BY` **không được đổi** giữa hai request dùng chung state.
5. Không xem `setPageSize(2)` là cam kết chính xác hai dòng trong mọi response. Nếu UI yêu cầu số lượng tuyệt đối, cần xây policy trang ứng dụng.
6. Mã trên **chưa an toàn cho token HTTP chưa tin cậy**, vì lớp xác thực chưa được triển khai. Chỉ dùng trực tiếp với token được bảo vệ trong hệ thống tin cậy/lab.

### 7.3. Một truy vấn mới không được mượn state của truy vấn cũ

Giả sử request đầu:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = ? AND event_day = ?;
```

Request sau đổi sang:

```sql
SELECT happened_at, event_id, event_type, summary
FROM event_history_by_user_day
WHERE user_id = ? AND event_day = ?;
```

Dù cùng người dùng/ngày, **projection đã đổi, query string đã đổi**. Không lấy paging state của truy vấn trước đưa sang truy vấn sau. Tương tự, token của User A/ngày 20 không dành cho User B/ngày 20 hoặc User A/ngày 21.

Ngay cả khi các câu lệnh có ý nghĩa “gần giống”, state gắn với **câu lệnh cụ thể và các tham số**. Khi phát hành phiên bản API/query mới, nên kiểm soát phiên bản token và cách xử lý token cũ.

## 8. An toàn của paging state khi dùng trên HTTP

Paging state không được thiết kế như một **vé ủy quyền** cho người dùng cuối. Theo API của Java Driver, lớp `PagingState` “safe wrapper” dựa trên cơ chế kiểm tra tương ứng query, **không có chữ ký mật mã mạnh**; kiểm tra nội bộ không thay thế HMAC hay mã hóa xác thực.

### 8.1. Những rủi ro phải phòng

- Người dùng sửa token hoặc dùng token của người khác.
- Token của tenant A bị gửi vào endpoint của tenant B.
- Client gửi token rất dài, sai định dạng hoặc đã hết hạn.
- Token cũ được dùng sau khi schema/query/driver protocol thay đổi.
- Token lộ trong URL, access log, analytics, browser history hoặc bản chụp lỗi.
- Server cho phép request chuyển `user_id`, `event_day` hay điều kiện lọc trong khi tái sử dụng token.

Một thiết kế an toàn có thể tạo lớp bao quanh:

```text
PagingState.toString()     -- trạng thái opaque của driver
          |
          v
Payload: {
  pagingState, principal/tenant, userId, day,
  queryVersion, pageSizePolicy, issuedAt, expiresAt
}
          |
          v
AEAD (mã hóa xác thực) hoặc HMAC + kiểm tra định dạng
          |
          v
Token API ngắn hạn gửi tới client

Request tiếp:
  xác thực -> kiểm tra expiry/identity/query/scope
  -> lấy pagingState -> PagingState.fromString(...)
  -> setPagingState vào BoundStatement tương ứng
```

**Không xem code trên là giao thức bảo mật đã được triển khai.** Khi áp dụng thực tế, hãy dùng thư viện crypto uy tín, quản lý khóa, luân phiên khóa và chống replay nếu nghiệp vụ yêu cầu. Nếu không muốn gửi token opaque ra ngoài, có thể lưu paging state phía server và trả **mã tham chiếu ngắn hạn** cho client.

### 8.2. Xử lý token không hợp lệ

Quy tắc ứng dụng:

1. Xác thực người dùng và kiểm tra quyền xem `userId` trước khi truy vấn Cassandra.
2. Giới hạn độ dài token, kiểm tra định dạng và xác thực chữ ký/mã hóa xác thực.
3. Kiểm tra tenant, ngày, query version và thời hạn; không để input HTTP tự thay các ràng buộc này.
4. Xử lý `IllegalArgumentException`/lỗi parsing/token mismatch thành lỗi API có kiểm soát (ví dụ HTTP 400), không retry Cassandra vô hạn.
5. Không ghi nguyên token hoặc dữ liệu nhạy cảm vào access log/traces.
6. Không khẳng định “token còn hạn là dữ liệu còn y như trước”; paging state **không phải snapshot**.

Nếu state không còn dùng được sau thay đổi hạ tầng, API nên có thông báo rõ để người dùng **bắt đầu lại từ trang đầu**, thay vì âm thầm đổi query rồi dùng token sai.

## 9. Vì sao không hỗ trợ ngẫu nhiên trang N hoặc quay về trang trước?

Với mỗi page, Cassandra trả trạng thái **của trang tiếp theo**, không phải một bộ chỉ số page number:

```text
Start --> page 1 --S1--> page 2 --S2--> page 3 --S3--> page 4
                       ^
                       |
                muốn page 3?
                phải có S2
```

Muốn vào thẳng page 37 mà chỉ biết số `37` và `pageSize = 20`, Cassandra không có `SELECT ... OFFSET 720` hiệu quả để nhảy tới dòng 721. Có thể:

- **Lưu lịch sử paging tokens**: ứng dụng giữ `S1`, `S2`, ... sau khi từng trang đã được truy cập. Khi quay lại, dùng token tương ứng (và **cùng query**). Cần kiểm soát bộ nhớ, expiry, quyền và dữ liệu thay đổi.
- **Đi lại từ đầu**: fetch/skip các trang trước để tới page mong muốn. Chi phí tăng theo số dòng phải bỏ qua.
- **Đổi mô hình trải nghiệm**: nút “Xem thêm” hoặc cuộn vô hạn thường phù hợp với paging state hơn giao diện đánh số trang ngẫu nhiên.
- **Dùng keyset cursor**: khi có một thứ tự theo khóa ổn định và API muốn ranh giới nghiệp vụ rõ ràng.

Java Driver có utility `OffsetPager` để **mô phỏng** việc lấy trang thứ N bằng cách chạy query từ đầu và bỏ qua dữ liệu. Nó **không phải `OFFSET` native của Cassandra** và không loại bỏ chi phí tuyến tính. Nếu dùng, cần giới hạn cứng số trang tối đa mà client được yêu cầu.

### 9.1. “Previous” không phải phép đảo của paging state

Trang trước là một tính năng **ở tầng ứng dụng**. Nếu client giữ token trước khi tải trang hiện tại, có thể request lại page trước bằng token ấy, nhưng kết quả vẫn phụ thuộc dữ liệu và consistency tại lần đọc lại.

Đừng lấy `S3` rồi cố “trừ một” để ra `S2`, cũng đừng giả định state chứa offset có thể đọc và sửa. **Paging state opaque, forward-only.**

### 9.2. Phân trang trên nhiều partition phức tạp hơn một partition

```sql
SELECT event_day, happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Truy vấn này xét **hai partition**, vì `event_day` là thành phần cuối của composite partition key. Paging state của nó có thể tiếp tục một truy vấn nhiều partition, nhưng:

- Clustering order chỉ tạo thứ tự **bên trong từng partition**, không phải cam kết timeline toàn cục theo giờ/ngày.
- State không tiết lộ cách phân chia những page theo ranh giới partition và không nên bị giải mã để suy luận.
- `LIMIT` không thay thế giới hạn số partition ứng viên trong `IN`.
- Mỗi request tiếp tục phải giữ **cùng danh sách ngày theo cùng query/bind values**.

Nếu nghiệp vụ cần “20 sự kiện mới nhất trên nhiều ngày”, cần định nghĩa cách lấy top-N xuyên bucket (merge kết quả có giới hạn hoặc bảng theo truy vấn), chứ không suy từ paging state rằng đã có thứ tự toàn cục.

## 10. So sánh paging state với keyset cursor theo clustering key

Đối với bảng lab, thứ tự trong một partition là:

```text
(happened_at DESC, event_id DESC)
```

Nếu một trang kết thúc ở khóa `(10:00, ...0004)`, có thể yêu cầu các dòng **đứng sau** theo chiều mới nhất trước bằng tuple boundary:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (happened_at, event_id) < (
      '2026-11-20 10:00:00+0000',
      00000000-0000-4000-8000-000000000004
  )
ORDER BY happened_at DESC, event_id DESC
LIMIT 2;
```

Kết quả dự kiến: `CLICK/0003` rồi `VIEW/0002`. So sánh:

| Đặc điểm | Paging state của driver | Keyset cursor |
| --- | --- | --- |
| Cách lưu vị trí | Token opaque của server/driver | Bộ giá trị clustering key cuối trang |
| Truy vấn tiếp | **Giữ nguyên query** và bind values, thêm state | **Thay điều kiện ranh giới** bằng khóa cuối |
| Biết vị trí nghiệp vụ? | Không nên giải mã token | Có, được biểu diễn bằng khóa |
| Đi tới page N bất kỳ | Không hỗ trợ tự nhiên | Không hỗ trợ tự nhiên nếu không biết boundary tương ứng |
| Trang trước | Ứng dụng phải lưu token trước đó | Có thể thiết kế query đảo chiều phù hợp, cần xử lý thứ tự và ranh giới |
| Dòng trùng timestamp | Driver quản lý vị trí trong result set | Phải dùng khóa đầy đủ, ví dụ `(happened_at,event_id)` |
| Dữ liệu thay đổi | Không phải snapshot | Không phải snapshot |
| Giới hạn sử dụng | Gắn chặt query/protocol/state | Gắn với schema, khóa và quy tắc sắp xếp của API |

Hai cách **đều** phù hợp những tình huống khác nhau. Paging state tiện cho “tiếp tục cùng câu truy vấn” không cần tự cài ranh giới. Keyset cursor hữu ích khi API muốn điều hướng theo một **khóa nghiệp vụ ổn định** và có thể quản lý cursor dài hạn hơn, với điều kiện schema/semantics không đổi.

**Không trộn hai cơ chế tùy ý:** Khi thay `WHERE` thành tuple boundary mới, đó là **một câu truy vấn mới**; không được tái sử dụng paging state của câu truy vấn trước như thể query vẫn hệt nhau.

## 11. Dữ liệu thay đổi giữa các trang: không có snapshot

Giả sử lúc tải trang đầu, người dùng thấy:

```text
Page 1: 13:00/id6, 12:00/id5
Page 2: 10:00/id4, 10:00/id3
Page 3: 09:00/id2, 08:00/id1
```

Trong lúc người dùng đọc page 1, hệ thống có thể:

- Ghi thêm một sự kiện mới lúc `14:00`, nằm **trước** những dòng đã đọc.
- Xóa một sự kiện lúc `10:00`, làm page sau có ít dòng hơn.
- TTL hết hạn hoặc một ghi sửa xuất hiện ở replica được chọn.
- Topology/replica load và consistency thay đổi kết quả quan sát được.

**Paging state không cung cấp snapshot transaction** của toàn bộ tập dữ liệu tại thời điểm page 1. Vì vậy:

- Không hứa mỗi lần next đều mang chính xác N dòng.
- Không hứa user xem hết một danh sách đang thay đổi sẽ thấy mọi dòng được tạo trong suốt thời gian duyệt.
- Không dùng paging state để chứng minh một báo cáo tài chính “đúng tại một thời điểm” trên nhiều partition.
- Không coi paging state là cơ chế chống trùng dữ liệu nghiệp vụ hoặc bảo đảm exactly-once.

Nếu cần ổn định hơn, có thể cố định **cửa sổ thời gian dữ liệu** (ví dụ `happened_at < :asOf`), lưu `asOf` trong token API và giữ nguyên nó trong mọi request. Nhưng ngay cả cận `asOf` cũng không tạo snapshot đúng nghĩa nếu có **ghi muộn/backfill, xóa, TTL hoặc replica chưa hội tụ**. Với báo cáo đòi snapshot nghiêm ngặt, cần chiến lược snapshot/CDC/đối soát riêng.

## 12. Hiệu năng và giới hạn tải khi paging

### 12.1. Page size nhỏ không tự làm truy vấn rẻ

| Bối cảnh | Page size nhỏ có giúp gì? | Chưa giải quyết điều gì? |
| --- | --- | --- |
| Một partition vừa, hàng có payload lớn | Giảm số dòng/bytes trong mỗi đợt fetch | Tổng bytes nếu client vẫn duyệt hết |
| Truy vấn `IN` 100 partition | Chia response thành các page | Không giảm 100 partition-key candidates |
| `ALLOW FILTERING` tìm dòng hiếm | Giảm số dòng khớp được trả mỗi đợt | Có thể phải kiểm tra rất nhiều dòng không khớp |
| Nhiều tombstone/TTL | Giảm khối lượng response hiện tại | Không loại bỏ công việc xác định dữ liệu còn sống |
| Đọc từ nhiều replica với consistency cao | Giới hạn response frame | Không bỏ yêu cầu replica/reconciliation |

Điều chỉnh page size là **quyết định trade-off**:

- Rất nhỏ: tăng số request/fetch và overhead network nếu phải duyệt nhiều trang.
- Rất lớn: tăng kích thước response, áp lực bộ nhớ, GC và tail latency.
- Vừa phải: cân bằng latency mỗi trang và throughput, phụ thuộc kích thước dòng, mạng, QPS và yêu cầu UI.

Không có page size tối ưu duy nhất cho mọi workload; cần đo trên dữ liệu có phân bố gần production.

### 12.2. Tối ưu query trước khi tối ưu page size

Ví dụ truy vấn tốt cho danh sách một ngày:

```sql
SELECT happened_at, event_id, event_type
FROM event_history_by_user_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY happened_at DESC, event_id DESC;
```

Nó có full partition key và projection chỉ chọn các cột cần thiết. Nếu dữ liệu rất lớn, cân nhắc bucket nhỏ hơn hoặc clustering range; không dựa vào paging để quét một hot partition khổng lồ mỗi khi người dùng mở màn hình.

### 12.3. Metrics cần theo dõi

| Chỉ số | Câu hỏi trả lời |
| --- | --- |
| p50/p95/p99 latency theo fetch/page | Những page nào chậm bất thường? |
| Rows và bytes mỗi page | Kích thước thực có khác page size mục tiêu không? |
| Số page được fetch trên mỗi request HTTP | Endpoint có vô tình đọc hết kết quả không? |
| Number of in-flight reads, concurrency | Có gây quá tải coordinator/replica không? |
| Timeouts, unavailable, retries | Lỗi do tải, consistency hay cluster health? |
| Tombstone warnings và compaction backlog | Có phải tìm dòng còn sống quá tốn kém? |
| GC/heap của Java và network throughput | Có nên giảm projection/page size không? |

Khi xảy ra lỗi, phân biệt:

1. **InvalidQuery**: query thiếu khóa, `ORDER BY` sai hoặc filter không hợp lệ; không sửa bằng tăng timeout.
2. **Invalid paging state / token mismatch**: token sai query, sai tham số, hỏng hoặc đã hết hạn ở tầng ứng dụng; trả lỗi có kiểm soát, không retry hàng loạt.
3. **Read timeout/unavailable**: kiểm tra replica, consistency, tải, page size, tốc độ đọc và retry policy.
4. **Dữ liệu khác kỳ vọng giữa các trang**: xem ghi/xóa/TTL đồng thời, consistency, paging strategy và các điều kiện ổn định truy vấn.

## 13. Các lỗi thiết kế phân trang thường gặp

| Nhận định hoặc code | Vấn đề | Cách sửa |
| --- | --- | --- |
| `setPageSize(20)` làm query trả tối đa 20 dòng | `ResultSet` đồng bộ có thể tự fetch mọi trang. | Dùng `LIMIT` cho trần tổng hoặc chỉ xử lý `currentPage()`. |
| Lấy paging state nhưng mới xử lý nửa page | State chỉ tới **đầu page tiếp theo**, có nguy cơ bỏ phần chưa xử lý. | Xử lý hết page rồi mới cho client dùng state ấy. |
| Đổi `userId`/`day` và giữ paging state cũ | State gắn với query và bind values cũ. | Chỉ tái sử dụng khi cùng statement/params. |
| Đổi projection/`LIMIT` giữa hai request | Query string/semantics thay đổi. | Khởi động phân trang mới, không mượn token cũ. |
| Tự “sửa” bytes của paging state | Trạng thái opaque, không phải offset dễ tính. | Dùng API của driver, không giải mã tự chế. |
| Lấy trang 50 bằng cách đoán token từ số trang | Không có ánh xạ page number sang paging state. | Giữ lịch sử token, duyệt tới đó hoặc thay UX. |
| `OffsetPager` là `OFFSET` native rất nhanh | Thư viện phải duyệt và bỏ qua dữ liệu trước trang mong muốn. | Đặt trần page number và đo linear cost. |
| `getSafePagingState()` đã bảo mật HTTP token | Lớp safe dùng kiểm tra query, **không** phải chữ ký mạnh. | Wrap token bằng HMAC/AEAD, ràng buộc user/tenant/expiry. |
| Paging cho phép quay về trang trước ngay lập tức | Paging state là hướng tiến. | Ứng dụng lưu token trước hoặc dùng keyset phù hợp. |
| Page size 2 nghĩa protocol luôn trả đúng 2 dòng | Server xem page size như một hint. | Xử lý số dòng thực nhận, thiết kế UI policy riêng. |
| Paging state tạo snapshot bất biến | Ghi/xóa/TTL và consistency vẫn ảnh hưởng kết quả. | Cố định window khi phù hợp và không tuyên bố snapshot. |
| Chỉ chọn `happened_at` cho keyset cursor | Sự kiện cùng timestamp sẽ gây bỏ/lặp. | Lưu cả `happened_at` và `event_id`. |
| Dùng paging để sửa `ALLOW FILTERING` quét rộng | Đường truy vấn vẫn đọc/lọc rộng. | Thiết kế lại khóa, index hoặc tập partition. |
| Retry mọi timeout để có trang tiếp theo | Có thể tạo retry storm, tăng tải và rủi ro xử lý lặp. | Retry có giới hạn, idempotency và backoff. |

## 14. Bài tập tự luyện có đáp án

### Bài 1. Tổng số dòng và số trang

**Đề:** User A/ngày 20 có 6 dòng. Nếu mục tiêu page size là 2 và server mỗi lần thực sự trả đúng 2 dòng, cần bao nhiêu fetch để đọc hết?

**Đáp án:** **3 lần fetch**, mỗi lần 2 dòng. Đây là kết quả theo **giả định server trả đúng 2**; page size ở Cassandra là hint, nên không dùng ba lần như cam kết protocol trong mọi trường hợp.

### Bài 2. Phân biệt LIMIT và page size

**Đề:** Query có `LIMIT 5`, Java Driver đặt `setPageSize(2)`. Có thể trả 5 dòng trên toàn truy vấn không?

**Đáp án:** Có, tối đa **5 dòng**, thường qua nhiều page; `LIMIT 5` không bị thay bởi page size 2. Không có dòng thứ sáu do giới hạn kết quả CQL.

### Bài 3. Vì sao token có thể bỏ một dòng?

**Đề:** Page 1 có 2 dòng. Java đọc dòng đầu, lưu token “trang kế”, trả HTTP và thoát. Request tiếp sau dùng token ấy. Điều gì có thể sai?

**Đáp án:** Dòng thứ hai của page 1 **chưa được xử lý**, nhưng token đã trỏ tới **page 2**. Request tiếp bỏ qua dòng thứ hai. Phải xử lý hết page trước khi xuất token, hoặc tự có cơ chế lưu các dòng chưa xử lý/buffer ở ứng dụng.

### Bài 4. Token của user A có dùng cho user B không?

**Đề:** Client gửi paging state của `(user A, 2026-11-20)` nhưng URL đổi thành `(user B, 2026-11-20)`.

**Đáp án:** **Không được**. Paging state gắn với query/bind values, không thể tái sử dụng cho User B. API còn phải xác thực và kiểm tra quyền trên `userId`, đồng thời xác minh token đã được ký/ràng buộc đúng principal, scope và expiry.

### Bài 5. Về lại trang 2 từ trang 5

**Đề:** UI chỉ còn paging state để tới trang 6. Có thể đảo bytes/token để đi ngược về trang 2 không?

**Đáp án:** Không. State opaque và hướng tiến. Nếu ứng dụng **đã lưu** token dùng để bắt đầu trang 2, có thể chạy lại truy vấn bằng token ấy; nếu không, thường phải lấy lại từ đầu hoặc dùng mô hình cursor/UX khác.

### Bài 6. Paging state hay keyset cursor?

**Đề:** Một API chỉ có nút “Xem thêm” và muốn ít logic cursor. API khác cần ranh giới theo `(happened_at,event_id)` để người dùng tải phần lịch sử cũ, kể cả khi format API thay đổi. Nên chọn gì?

**Đáp án gợi ý:** API “Xem thêm” với **cùng query** phù hợp paging state. API cần ranh giới nghiệp vụ tường minh và chủ động về semantics có thể dùng **keyset cursor** với full clustering key, giới hạn/cửa sổ cố định và policy bảo vệ cursor. Cả hai không tự tạo snapshot hay truy cập ngẫu nhiên O(1) đến trang N.

### Bài 7. Dữ liệu mới trong lúc phân trang

**Đề:** Sau khi user đọc trang đầu, một sự kiện `14:00` được ghi vào partition và đứng trước `13:00` theo `DESC`. Paging state có bảo đảm user sẽ thấy sự kiện mới trong các trang còn lại không?

**Đáp án:** Không. Paging state tiếp tục duyệt cùng truy vấn nhưng **không snapshot** dữ liệu tại thời điểm page 1; một dòng mới đứng trước vị trí đã đi qua có thể không xuất hiện trong các trang sau. Muốn dữ liệu mới, có thể cần làm mới danh sách từ đầu theo policy UI.

## 15. Checklist cho endpoint forward-only

1. **Đường đọc:** `WHERE` có full partition key hoặc tập partition nhỏ được kiểm soát không? Clustering order có phục vụ màn hình không?
2. **Giới hạn:** đã phân biệt `LIMIT` toàn truy vấn, page size và page size của HTTP UI chưa?
3. **Chế độ driver:** đồng bộ `ResultSet` tự fetch hay bất đồng bộ `AsyncResultSet.currentPage()`? Endpoint có vô tình đọc hết không?
4. **Tính đầy đủ:** khi lưu paging state đã xử lý hết page hiện tại chưa? Khi không còn trang, đã trả token null chưa?
5. **Query consistency:** request tiếp có dùng đúng CQL string, bind values, projection, filters và query version không?
6. **An toàn:** có ràng buộc principal/tenant, thời hạn và ký/mã hóa token, chống token hỏng và hạn chế logging không?
7. **Điều hướng:** UX đã chấp nhận forward-only chưa? Nếu có previous/page N, đã có chiến lược lưu token hoặc emulation với giới hạn chi phí chưa?
8. **Thay đổi dữ liệu:** đã nói rõ paging không tạo snapshot và có policy xử lý ghi mới, TTL/xóa và replica chưa hội tụ chưa?
9. **Hiệu năng:** đã đo p95/p99, số page/fetch, bytes, tombstones, timeouts và concurrency với dữ liệu gần thực tế chưa?
10. **Retry:** lỗi query và token sai có được tách khỏi timeout/unavailable? Có backoff và không tự động xử lý lặp ở sink nếu retry không?
11. **Khi cần cursor khác:** nếu cần phân trang theo thời gian ổn định hơn, đã cân nhắc keyset `(happened_at,event_id)`, bucket và cửa sổ truy vấn chưa?

**Ghi nhớ:** `paging state` là **vị trí tiếp tục opaque của một truy vấn cụ thể**; Java Driver hỗ trợ tốt mô hình **“trang kế tiếp”**. Nó không phải `OFFSET`, page number, token bảo mật hoàn chỉnh hay snapshot dữ liệu. Hãy dùng `WHERE` đúng primary key để kiểm soát phạm vi đọc, `page size` để điều tiết fetch, xác thực paging token cho HTTP và giữ nguyên query/bind values qua các lần tiếp tục.

## Tài liệu tham khảo

- [DataStax Java Driver 4.17 — Paging: sync, async, paging state và OffsetPager](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
- [Java Driver 4.17 — ExecutionInfo API: raw và safe paging state](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/ExecutionInfo.html)
- [Java Driver 4.17 — PagingState API: fromString, toString và security warning](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/PagingState.html)
- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT, LIMIT và ORDER BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
