# Thiết kế API cursor và bảo vệ token phân trang

Khi xây dựng REST API trên **Apache Cassandra** bằng **Spring Data Cassandra**, một câu hỏi phổ biến là: *“Làm thế nào trả 25 sự kiện mới nhất và cho client lấy tiếp trang sau mà không quét lại dữ liệu?”* Cách phân trang bằng số trang và offset quen thuộc ở một số cơ sở dữ liệu quan hệ không phù hợp với đặc điểm lưu trữ theo **partition key** và **clustering columns** của Cassandra.

Một API theo **cursor** trả về dữ liệu của trang hiện tại và một **token tiếp tục** (continuation token) để khách hàng yêu cầu trang kế tiếp. Java Driver của Cassandra có **paging state** hỗ trợ tiếp tục thực thi một truy vấn CQL, nhưng paging state không phải một bằng chứng phân quyền và **không nên được trả nguyên dạng như một token đáng tin cậy**. Ứng dụng cần ràng buộc nó với đúng truy vấn, người dùng, phạm vi tenant, hạn dùng và bảo vệ tính toàn vẹn của token.

Bài thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_CASSANDRA**. Nội dung tập trung vào thiết kế hợp đồng API, cách lấy paging state, lựa chọn projection, HMAC/AES-GCM, xác thực/ủy quyền, xử lý dữ liệu thay đổi giữa các trang và phân trang qua nhiều partition. Các ví dụ dùng Java Driver 4.x và Spring Boot/Spring Data Cassandra tương thích; khi triển khai cần đối chiếu chữ ký API của phiên bản đang chạy.

## 1. Vì sao nên dùng cursor thay vì page number?

Trong hệ quan hệ, một API đôi khi nhận:

~~~text
GET /orders?page=200&size=25
~~~

và chuyển thành kiểu truy vấn có `LIMIT`/`OFFSET`. Cassandra không cung cấp một phép **nhảy ngẫu nhiên tới hàng thứ 5.001** với cùng mô hình và chi phí dự đoán được. Các hàng được lưu theo partition; muốn tiếp tục đọc, driver thường dùng một **paging state** do Cassandra trả về.

Một hợp đồng phù hợp hơn:

~~~text
GET /v1/events?day=2026-11-25&limit=25
GET /v1/events?cursor=<token-trang-sau>
~~~

| Cơ chế | Ý nghĩa | Nhược điểm cần cân nhắc |
| --- | --- | --- |
| Page number/offset | Client yêu cầu trực tiếp trang N | Cassandra không có offset ngẫu nhiên tương đương hệ quan hệ |
| **Cursor/paging state** | Tiếp tục từ trạng thái truy vấn trước | Phải giữ truy vấn/parameter tương thích và bảo vệ token |
| Keyset/seek pagination | Tiếp tục sau bộ khóa sắp xếp đã trả | Cần khóa thứ tự duy nhất và điều kiện range CQL hợp lệ |
| Phân trang nhiều partition | Ứng dụng quản lý nhiều nguồn/trang con | Cần giới hạn fan-out, merge thứ tự và trạng thái tiếp tục |

**Cursor không phải snapshot giao dịch.** Nếu có ghi/xóa hoặc TTL hết hạn giữa hai yêu cầu, các trang có thể không phản ánh một ảnh chụp bất biến của tập dữ liệu. Cursor chỉ hỗ trợ **tiếp tục đọc theo một quy tắc xác định**.

## 2. Thiết kế bảng trước khi thiết kế cursor

Giả sử API cần hiển thị **những sự kiện mới nhất của một tenant trong một ngày**, mỗi trang có nhiều nhất khoảng 25 hàng. Bảng Cassandra được tổ chức theo đúng truy vấn này:

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS activity_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    status      text,
    payload     text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id DESC
);
~~~

Trong đó:

- `(tenant_id, event_day)` là **composite partition key**. API cần biết đầy đủ hai giá trị để đọc một partition.
- `occurred_at` và `event_id` là **clustering columns**, cho thứ tự mới nhất trước và tránh hai sự kiện cùng thời điểm bị trùng khóa.
- `payload` có thể lớn, trong khi màn hình danh sách chỉ cần mã, loại và trạng thái. Đây là lý do chọn **projection** thay vì `SELECT *`.

Ví dụ giả định datacenter tên `dc1` và replication factor 3; phải dùng topology/replication phù hợp cluster thực tế. Schema production nên được tạo qua migration, không phụ thuộc vào startup của mỗi instance.

Truy vấn danh sách:

~~~sql
SELECT occurred_at, event_id, event_type, status
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?;
~~~

Câu CQL trên **không có `LIMIT` cố định** trong ví dụ phân trang bằng driver: ứng dụng dùng page size để nhận dữ liệu từng đợt và tiếp tục bằng paging state. Nếu áp dụng thêm `LIMIT 100`, cần hiểu rằng toàn bộ truy vấn sẽ **không bao giờ trả quá 100 hàng**, dù client tiếp tục xin nhiều trang.

**Cẩn thận:** page size không làm một partition khổng lồ trở thành nhỏ. Nếu một tenant/ngày có quá nhiều sự kiện, cần đánh giá partition size, traffic, TTL/tombstone và có thể thêm bucket giờ hoặc shard vào partition key.

## 3. Projection và tính ổn định của câu truy vấn

Với cùng một bảng, hai truy vấn dưới đây có chi phí đọc và payload khác nhau:

~~~sql
-- Trang danh sách: dữ liệu nhỏ, cố định các cột cần thiết.
SELECT occurred_at, event_id, event_type, status
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?;

-- Chi tiết: payload có thể lớn, đọc theo full primary key.
SELECT occurred_at, event_id, event_type, status, payload
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
~~~

Projection giúp giảm lượng dữ liệu mạng và chi phí giải mã Java cho trang danh sách. Trong Spring Data Cassandra, có thể biểu diễn projection bằng DTO/interface hoặc truy vấn chọn cột rõ ràng qua `CassandraTemplate`/repository; khi cần **paging state tường minh**, Java Driver là một lựa chọn trực tiếp.

Tuy nhiên, **paging state của truy vấn danh sách không thể tùy ý tái dùng cho truy vấn chi tiết**. Thay đổi projection, điều kiện, thứ tự, keyspace, binding hoặc cách xây CQL có thể khiến continuation không còn hợp lệ. Hãy coi một mẫu CQL ổn định là một **phiên bản hợp đồng truy vấn** của cursor.

| Thành phần của query | Có nên thay khi dùng cursor cũ? | Lý do |
| --- | --- | --- |
| Tenant, event day | **Không** | Thay đổi partition được truy vấn |
| Bộ lọc và giá trị bind | **Không** | Tập kết quả khác |
| Projection/SELECT columns | **Không** | Câu CQL và cách giải mã kết quả khác |
| Cách sắp xếp/clustering | **Không** | Vị trí tiếp tục không còn cùng ý nghĩa |
| Page size | Nên cố định trong một cursor | Hợp đồng API ổn định, đơn giản hóa kiểm soát |
| Phiên bản query/schema | Cần tương thích | Migration có thể làm paging state không còn dùng được |

Do đó, thay vì cho client tùy chọn đổi filter ở trang tiếp, API sẽ phát **cursor gắn với tập điều kiện ban đầu**. Nếu client muốn đổi filter, hãy tạo một truy vấn đầu tiên mới.

## 4. Hợp đồng REST API theo cursor

Một thiết kế đơn giản:

~~~http
GET /v1/events?day=2026-11-25&limit=25
Authorization: Bearer <access-token>
~~~

Server **lấy tenant từ danh tính/quyền truy cập đã xác thực**, không cho client tùy ý tự sửa tenant qua cursor. Response:

~~~json
{
  "data": [
    {
      "eventId": "550e8400-e29b-41d4-a716-446655440000",
      "occurredAt": "2026-11-25T08:30:00Z",
      "eventType": "ORDER_PAID",
      "status": "PROCESSED"
    }
  ],
  "page": {
    "limit": 25,
    "nextCursor": "v1.k1.eyJ2IjoxLC4uLn0.ZGVtbw",
    "hasMore": true
  }
}
~~~

`nextCursor` ở đây chỉ là **chuỗi mô phỏng định dạng**, không phải token hợp lệ được ký. Trong hệ thống thật, nó được tạo từ trạng thái paging trả về, metadata truy vấn và chữ ký/mã hóa.

Trang tiếp theo:

~~~http
GET /v1/events?cursor=<opaque-next-cursor>
Authorization: Bearer <access-token>
~~~

Server xác minh token, so khớp danh tính/quyền truy cập hiện tại, khôi phục tham số truy vấn và tiếp tục. Nếu hết dữ liệu:

~~~json
{
  "data": [],
  "page": {
    "limit": 25,
    "nextCursor": null,
    "hasMore": false
  }
}
~~~

**Quy ước khuyến nghị:**

1. Client coi `nextCursor` là **opaque string**: không parse, không sửa, không suy luận nội dung.
2. Không truyền đồng thời một cursor và các filter mới có ý nghĩa khác. Nếu cần chấp nhận cả hai, server phải kiểm tra khớp tuyệt đối.
3. Giới hạn `limit` ở server, chẳng hạn mặc định 25 và cho phép từ 1 đến 100; không chấp nhận con số vô hạn.
4. Trang cuối trả `nextCursor: null`, không phát lại cursor cũ.
5. API có thể trả ít hơn kích thước trang ở một số tình huống; **không dùng số hàng trả về đơn thuần để kết luận hết dữ liệu**, mà dựa vào trạng thái tiếp tục.
6. Token có hạn dùng ngắn, ví dụ 15 phút, theo yêu cầu sản phẩm và thời gian một phiên duyệt dữ liệu; đây là chính sách ứng dụng chứ không phải giới hạn cố định của Cassandra.

## 5. Paging state trong Java Driver 4.x

Java Driver hỗ trợ page size và paging state cho một câu CQL đã được chuẩn bị. Một lượt đọc theo một partition thường có luồng:

~~~text
HTTP request đầu tiên
      |
      v
PreparedStatement + bind(tenant, day) + pageSize
      |
      v
Cassandra trả page A + paging state A
      |
      v
Ứng dụng trả data A + cursor được bảo vệ

HTTP request tiếp theo + cursor
      |
      v
Xác minh cursor, khôi phục đúng tenant/day/query
      |
      v
BoundStatement + paging state A
      |
      v
Cassandra trả page B + paging state B (hoặc hết)
~~~

**Paging state không phải số thứ tự hàng.** Đây là dữ liệu tiếp tục mang ý nghĩa đối với truy vấn/driver/server; không sửa byte bên trong, không so sánh hai trạng thái như các offset và không dùng token của truy vấn A cho truy vấn B.

### Mã Java đọc một page theo async driver API

Ví dụ Java 17 với `CqlSession` và `AsyncResultSet`; code chỉ tập trung vào truy vấn Cassandra, **chưa phải controller có kiểm tra quyền và ký token**:

~~~java
import java.nio.ByteBuffer;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatementBuilder;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public record EventSummary(
        UUID eventId, Instant occurredAt,
        String eventType, String status) {}

public record RawPage(
        List<EventSummary> items, ByteBuffer nextState) {}

public final class EventPageReader {
    private final CqlSession session;
    private final PreparedStatement query;

    public EventPageReader(CqlSession session) {
        this.session = session;
        this.query = session.prepare("""
            SELECT occurred_at, event_id, event_type, status
            FROM activity_ks.events_by_tenant_day
            WHERE tenant_id = ? AND event_day = ?
            """);
    }

    public CompletionStage<RawPage> readOnePage(
            UUID tenantId,
            LocalDate day,
            int pageSize,
            ByteBuffer previousState) {

        BoundStatementBuilder statement = query.boundStatementBuilder()
                .setUuid(0, tenantId)
                .setLocalDate(1, day)
                .setPageSize(pageSize);

        if (previousState != null) {
            statement.setPagingState(previousState.asReadOnlyBuffer());
        }

        return session.executeAsync(statement.build())
                .thenApply(page -> {
                    List<EventSummary> events = new ArrayList<>();
                    for (Row row : page.currentPage()) {
                        events.add(new EventSummary(
                            row.getUuid("event_id"),
                            row.getInstant("occurred_at"),
                            row.getString("event_type"),
                            row.getString("status")
                        ));
                    }

                    ByteBuffer nextState = null;
                    if (page.hasMorePages()) {
                        ByteBuffer state =
                            page.getExecutionInfo().getPagingState();
                        if (state != null) {
                            nextState = state.asReadOnlyBuffer();
                        }
                    }
                    return new RawPage(events, nextState);
                });
    }
}
~~~

Lưu ý triển khai:

- Các `record` được trình bày riêng để dễ đọc; khi tạo mã nguồn thực tế, đặt mỗi public type vào file phù hợp.
- Dùng một `PreparedStatement` cố định theo mẫu truy vấn, không gọi `prepare()` ở mỗi HTTP request.
- `currentPage()` chỉ duyệt **trang hiện tại**; đừng gọi `fetchNextPage()` nếu mục tiêu mỗi HTTP request chỉ trả một trang.
- Khi `hasMorePages()` không còn đúng, `nextState` phải là `null` và API trả `nextCursor: null`.
- `ByteBuffer` là dữ liệu nhị phân; khi đóng gói token cần sao chép các byte còn lại của buffer và mã hóa Base64URL, không tự biến buffer thành chuỗi UTF-8.
- Tên method lấy state và cách bind state cần được kiểm tra theo API của đúng phiên bản Driver 4.x; dữ liệu state không được diễn giải bằng logic nghiệp vụ.
- Mã chưa có validation kích thước trang, phân quyền, xử lý lỗi hoặc bảo vệ token: các phần này thuộc lớp API phía ngoài.

Ví dụ sao chép state mà không thay đổi vị trí của buffer gốc:

~~~java
ByteBuffer view = rawPage.nextState().asReadOnlyBuffer();
byte[] stateBytes = new byte[view.remaining()];
view.get(stateBytes);
String encoded = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(stateBytes);
~~~

Chỉ chạy đoạn trên khi `nextState() != null`. State đã Base64URL **chưa an toàn để trao cho client nếu không được bảo vệ**: Base64 là encoding chứ không phải chữ ký hay mã hóa bí mật.

## 6. Vì sao không nên trả trực tiếp raw paging state?

Một số ví dụ trên mạng chỉ lấy state của driver, Base64URL encode rồi gửi:

~~~text
nextCursor = base64url(driverPagingState)
~~~

Cách này thiếu lớp bảo vệ của **hợp đồng API**. Client có thể gửi chuỗi bất kỳ, tráo token của người khác hoặc dùng token cho một query khác. Ngay cả khi driver từ chối một paging state không hợp lệ, **driver không thay thế xác thực và ủy quyền của ứng dụng**.

Các yêu cầu cần thỏa mãn:

| Rủi ro | Cơ chế bảo vệ |
| --- | --- |
| Client sửa paging state/filter/tenant | Chữ ký HMAC hoặc authenticated encryption cho toàn bộ payload |
| Dùng cursor của người khác | Gắn cursor với identity/tenant và **so khớp lại sau khi xác thực request** |
| Dùng cursor cho query khác | Ràng buộc query ID, projection, filter, sort và page size |
| Cursor tồn tại quá lâu | Có `issuedAt`/`expiresAt`, giới hạn TTL ở ứng dụng |
| Token quá lớn hoặc dữ liệu hỏng | Giới hạn byte đầu vào, định dạng, version; reject trước khi decode nặng |
| Token lộ qua logs/analytics | Không log giá trị đầy đủ; hạn chế lưu trong URL, proxy và telemetry |
| Secret ký bị lộ/đổi | Key ID, rotation, lưu khóa trong secret manager |
| Người dùng đã bị thu hồi quyền | Kiểm tra authorization **mỗi lần** dùng cursor; không chỉ tin vào claim cũ |

**Nguyên tắc:** chữ ký chống **sửa đổi token**, không ngăn việc **đọc** payload. Nếu cursor chứa ID nhạy cảm, paging state hoặc chi tiết bộ lọc không được phép lộ, dùng **authenticated encryption** như AES-GCM thay vì chỉ HMAC.

## 7. Những dữ liệu cần đóng gói trong cursor

Một payload logic minh họa:

~~~json
{
  "v": 1,
  "queryId": "events-by-tenant-day-summary-v1",
  "subject": "principal-opaque-id",
  "tenantId": "550e8400-e29b-41d4-a716-446655440000",
  "eventDay": "2026-11-25",
  "filtersHash": "base64url-sha256-of-canonical-filters",
  "pageSize": 25,
  "pagingState": "base64url-driver-paging-state",
  "issuedAt": 1795590000,
  "expiresAt": 1795590900
}
~~~

Thời điểm ở đây minh họa số **giây Unix epoch** cho metadata của cursor; chúng không phải write timestamp của Cassandra. Trong triển khai thật, `issuedAt`/`expiresAt` phải được tính từ đồng hồ server với thời hạn hợp lệ. Nếu dùng HMAC, JSON sau Base64URL **không được giữ bí mật**.

Giải thích các field:

| Field | Tác dụng |
| --- | --- |
| `v` | Phiên bản cấu trúc token để parser biết cách đọc |
| `queryId` | Phiên bản cố định của mẫu CQL và projection |
| `subject` | Ràng buộc với chủ thể đã xác thực; dùng identifier ổn định, tránh thông tin cá nhân không cần thiết |
| `tenantId` | Giới hạn phạm vi partition/tenant |
| `eventDay` | Giữ nguyên bucket ngày đã truy vấn |
| `filtersHash` | Phát hiện thay đổi bộ lọc/sort/các lựa chọn ảnh hưởng tập kết quả |
| `pageSize` | Ngăn client nâng size ở trang sau hoặc dùng sai query settings |
| `pagingState` | Byte state của driver, được encode để truyền |
| `issuedAt`, `expiresAt` | Khống chế thời gian sống của continuation |

Không nhất thiết mọi token phải chứa nguyên mọi tham số. Có thể chỉ chứa một **query fingerprint** và khóa tra cứu tới bản ghi state phía server; trade-off là phải duy trì storage với TTL, đồng bộ giữa instance và cơ chế dọn dẹp.

### Canonicalization bộ lọc

Nếu API có filter loại sự kiện, ngày, trạng thái hoặc cách sắp xếp, hash nên được tạo từ **biểu diễn chuẩn hóa và có phiên bản**:

~~~text
queryId: events-by-tenant-day-summary-v1
tenant: 550e8400-e29b-41d4-a716-446655440000
day: 2026-11-25
eventTypes: [ORDER_PAID, ORDER_SHIPPED] (đã sort)
sort: occurred_at_desc,event_id_desc
projection: summary_v1
pageSize: 25
~~~

Thứ tự của tập filter, tên trường, định dạng ngày, locale và kiểu dữ liệu cần có quy tắc cố định để **hai request tương đương cho cùng fingerprint**. Nếu bộ lọc phụ thuộc user, tenant và role, tính hợp lệ của request hiện tại vẫn phải được kiểm tra lại.

## 8. Ký cursor bằng HMAC-SHA256

Một cách phổ biến để bảo vệ **tính toàn vẹn** là tạo chuỗi:

~~~text
v1.<key-id>.<base64url(payload-json)>.<base64url(hmac-sha256)>
~~~

Chữ ký cần bao phủ **version, key ID và toàn bộ payload đã mã hóa**, không chỉ paging state. Key ID được dùng để tìm khóa phù hợp trong một danh sách khóa được phép, còn chính key ID cũng nằm trong phần được ký.

Ví dụ Java minh họa phần **ký và xác minh tính toàn vẹn**; payload JSON được serialize bằng cơ chế riêng trước đó và **chỉ được parse sau khi xác minh**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class CursorHmac {
    private static final Base64.Encoder ENC =
        Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DEC =
        Base64.getUrlDecoder();

    private CursorHmac() {}

    public static String sign(
            byte[] payloadJson, String keyId, byte[] secret)
            throws GeneralSecurityException {
        String body = "v1." + keyId + "." +
            ENC.encodeToString(payloadJson);
        return body + "." + ENC.encodeToString(mac(body, secret));
    }

    public static byte[] verify(
            String token, Map<String, byte[]> keyring)
            throws GeneralSecurityException {
        if (token == null || token.length() > 8192) {
            throw new SecurityException("Cursor không hợp lệ");
        }
        String[] parts = token.split("\\.", -1);
        if (parts.length != 4 || !"v1".equals(parts[0])) {
            throw new SecurityException("Cursor không hợp lệ");
        }

        byte[] secret = keyring.get(parts[1]);
        if (secret == null) {
            throw new SecurityException("Cursor không hợp lệ");
        }

        String body = parts[0] + "." + parts[1] + "." + parts[2];
        byte[] actual = DEC.decode(parts[3]);
        byte[] expected = mac(body, secret);
        if (!MessageDigest.isEqual(actual, expected)) {
            throw new SecurityException("Cursor không hợp lệ");
        }
        return DEC.decode(parts[2]);
    }

    private static byte[] mac(String body, byte[] secret)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return hmac.doFinal(
            body.getBytes(StandardCharsets.US_ASCII));
    }
}
~~~

Đây là **mã minh họa phần chữ ký**, chưa phải toàn bộ bộ giải mã cursor production. Khi dùng phải bổ sung kiểm tra độ dài từng field sau giải mã, schema JSON, `issuedAt`/`expiresAt`, query ID, filter fingerprint, page size, issuer/audience nếu cần, subject/tenant và quyền truy cập hiện tại. Bắt lỗi `IllegalArgumentException` của Base64 và trả lỗi API chung, không để stack trace hoặc payload bị phản chiếu ra response.

**Bảo vệ khóa bí mật:** không hard-code secret trong source code hoặc lưu cạnh token. Lấy khóa HMAC đủ mạnh từ secret manager/KMS hoặc biến môi trường được kiểm soát, quản lý phân quyền truy cập. Đặt `keyId` theo một **allowlist**, không biến giá trị này thành đường dẫn filesystem hay URL để tự động tải khóa từ bên ngoài.

### HMAC khác AES-GCM ở điểm nào?

| Phương án | Bảo vệ chống sửa đổi | Giấu nội dung payload | Khi nào phù hợp |
| --- | --- | --- | --- |
| Base64URL thuần | **Không** | Không | Chỉ encoding nội bộ, không dùng làm token tin cậy |
| HMAC-SHA256 | **Có** nếu triển khai đúng | **Không** | Cursor không chứa thông tin cần giữ bí mật |
| AES-GCM với nonce duy nhất | **Có** qua authentication tag | **Có** | Cursor có paging/filter metadata nhạy cảm |
| ID ngẫu nhiên tra state server-side | Phụ thuộc kiểm soát ID + storage/auth | Không lộ payload trực tiếp | Muốn dễ thu hồi và quản lý state tập trung |

Nếu dùng **AES-GCM**, phải tạo nonce mới theo mỗi lần mã hóa bằng nguồn ngẫu nhiên an toàn, không bao giờ tái sử dụng nonce với cùng khóa; bảo vệ version/key ID bằng associated data (AAD) và xác thực tag trước khi parse nội dung. Không tự thiết kế mã hóa riêng hoặc dùng AES-CBC không kèm xác thực.

## 9. Quy trình xác minh cursor trên mỗi request

Sau khi nhận một cursor, server nên thực hiện theo thứ tự:

1. **Xác thực HTTP request**; lấy subject/tenant và quyền hiện tại từ hệ thống xác thực.
2. **Giới hạn kích thước chuỗi token**, số segment và kích thước giải mã trước khi xử lý tốn tài nguyên.
3. Đọc version/key ID ở mức tối thiểu, tìm khóa từ **keyring cho phép**, xác minh HMAC hoặc giải mã xác thực AES-GCM.
4. **Chỉ sau khi xác thực tính toàn vẹn**, parse payload theo schema có giới hạn độ dài/kiểu dữ liệu.
5. Kiểm tra token chưa hết hạn, không dùng trước thời điểm phát hành, phiên bản query còn được hỗ trợ.
6. Đối chiếu subject/tenant với danh tính được xác thực và **kiểm tra authorization lại**. Token đúng chữ ký không đồng nghĩa người dùng vẫn có quyền.
7. Kiểm tra limit, projection, sort, filter fingerprint, bucket và mọi tham số bắt buộc của query.
8. Khôi phục paging state từ Base64URL với giới hạn byte, bind vào **mẫu CQL tương ứng với queryId**, rồi thực thi.
9. Đọc trang hiện tại, tạo cursor mới từ paging state tiếp theo, ký/mã hóa và trả cho client.

Không nhận thông tin tenant từ payload và cho phép nó **ghi đè** tenant của người dùng đang xác thực. Có thể dùng payload như dữ liệu yêu cầu đã được bảo vệ, nhưng **phạm vi thực thi** phải bị giới hạn bởi principal/quyền hiện hành.

Một số lỗi HTTP hợp lý:

| Tình huống | Hướng trả lỗi |
| --- | --- |
| Token sai định dạng/chữ ký | `400 Bad Request` với mã lỗi ứng dụng chung, không tiết lộ secret |
| Token hết hạn hoặc queryId không còn hỗ trợ | `400`/`410` theo hợp đồng API; hướng dẫn client tải lại từ trang đầu |
| Đã bị thu hồi quyền tenant | `403 Forbidden` (hoặc chính sách `404` phù hợp để tránh lộ tài nguyên) |
| Cassandra timeout/unavailable | `503` hoặc lỗi hạ tầng phù hợp; không phát cursor giả |
| Truy vấn/paging state không còn hợp lệ sau thay đổi schema | Trả lỗi cursor không còn dùng được, yêu cầu bắt đầu lại |

Tránh dùng `500` không có thông tin cho mọi lỗi của client, nhưng cũng không để lộ chi tiết paging state, key ID nội bộ hoặc CQL chứa dữ liệu nhạy cảm trong thông báo lỗi.

## 10. Key rotation, replay và khả năng thu hồi

Một cursor hợp lệ thường có thể được **dùng lại** trước khi hết hạn để đọc lại cùng một vị trí. HMAC không biến nó thành token chỉ dùng một lần. Điều này là hành vi có thể chấp nhận đối với một API đọc nếu đã xác thực/ủy quyền và giới hạn tài nguyên.

Tuy nhiên cần quyết định rõ:

- **Replay:** cho phép dùng lại cursor hay yêu cầu one-time? One-time cần lưu trạng thái đã dùng phía server, không đạt được chỉ bằng HMAC.
- **Hạn dùng:** ngắn hơn thời gian mà ứng dụng có thể duy trì tương thích query/schema; không đặt “vô hạn” theo thói quen.
- **Key rotation:** ký token mới bằng key ID hiện hành, tạm giữ khóa cũ trong thời gian token cũ còn hợp lệ, sau đó gỡ bỏ.
- **Thu hồi tức thì:** nếu cần vô hiệu hóa toàn bộ token của một phiên/người dùng trước expiry, cần cơ chế server-side như revocation epoch hoặc tra cứu phiên, ngoài việc kiểm tra authorization.
- **Nhiều instance:** cùng token phải được xác minh đúng trên mọi instance; phân phối keyring/cấu hình nhất quán và quản lý clock skew.
- **Rate limiting:** giới hạn số trang/giây, số yêu cầu song song và số bucket được đọc, kể cả token có chữ ký hợp lệ.

Không nên dựa vào tính khó đoán của paging state như một biện pháp bảo mật. Cursor là **capability tiếp tục truy vấn**, không thay cho access token hoặc quyền truy cập dữ liệu.

## 11. Dữ liệu thay đổi giữa các trang có gây trùng/lọt hàng không?

Có thể. Xét những sự kiện được sắp theo `occurred_at DESC, event_id DESC`:

~~~text
Trang 1 (lúc T1): E9 E8 E7 E6
                         ^ vị trí tiếp tục

Giữa T1 và T2:
  - Một sự kiện E10 mới được thêm;
  - E7 bị xóa hoặc hết TTL;
  - Một event cũ được nạp muộn vào vị trí sắp xếp trước/sau cursor.

Trang 2 (lúc T2): đọc trên dữ liệu đã thay đổi
~~~

Paging state **không khóa dữ liệu, không tạo snapshot transaction đa request** và không ngăn ghi/xóa/TTL. Tùy biến động, một khách hàng có thể nhìn thấy một số phần tử bị lặp hoặc không thấy một số phần tử mới xuất hiện trong quá trình duyệt.

Giải pháp giảm tác động:

1. **Khóa sắp xếp ổn định và duy nhất:** dùng `(occurred_at, event_id)` thay vì chỉ timestamp có thể trùng.
2. **Giới hạn thời điểm trên:** ở trang đầu, lưu `upperBound`/as-of và chỉ đọc sự kiện không vượt mốc đó (nếu CQL, clustering và yêu cầu nghiệp vụ cho phép).
3. **Idempotency ở client/service:** có thể deduplicate theo `eventId` nếu UI yêu cầu, song phải cân đối bộ nhớ và tính đúng.
4. **Thời gian sống cursor ngắn:** giảm cửa sổ dữ liệu thay đổi.
5. **Sự kiện bất biến hoặc snapshot riêng:** nếu cần xuất báo cáo với tập dữ liệu không đổi, dùng cơ chế snapshot/export được thiết kế riêng, không hứa hẹn snapshot bằng Cassandra paging state.

Ngay cả khi đặt `upperBound`, **xóa/TTL và các ghi đến muộn** vẫn có thể ảnh hưởng tính đầy đủ. Nếu API cần bảo đảm đúng tuyệt đối “mỗi hàng đúng một lần tại một thời điểm”, cần đặc tả consistency mạnh hơn và kiến trúc phù hợp; cursor thông thường không tạo ra bảo đảm đó.

## 12. Phân trang vượt nhiều ngày hoặc nhiều partition

Bảng `events_by_tenant_day` chia theo ngày. API “đọc lịch sử 30 ngày mới nhất” sẽ truy cập **nhiều partition**. Một paging state của driver dành cho:

~~~text
tenant=A, event_day=2026-11-25
~~~

không thể đem dùng cho:

~~~text
tenant=A, event_day=2026-11-24
~~~

vì tham số query đã thay đổi. Ứng dụng cần điều phối ở tầng service.

Một cách đơn giản khi duyệt ngày từ mới đến cũ:

~~~text
Danh sách ngày: 25/11 -> 24/11 -> 23/11 -> ...

Đang đọc ngày 25:
  - Nếu còn paging state của ngày 25, tiếp tục chính ngày đó.
  - Nếu đã hết, chuyển sang ngày 24 và bắt đầu với state rỗng.
  - Lặp cho tới khi đạt số hàng cần trả hoặc hết phạm vi ngày.
~~~

Cursor của ứng dụng khi đó có thể lưu:

~~~json
{
  "v": 2,
  "queryId": "events-multi-day-v1",
  "tenantId": "550e8400-e29b-41d4-a716-446655440000",
  "fromDay": "2026-11-01",
  "toDay": "2026-11-25",
  "currentDay": "2026-11-24",
  "currentPartitionState": "base64url-or-null",
  "pageSize": 25,
  "expiresAt": 1795590900
}
~~~

Payload phải tiếp tục được ký/mã hóa và ràng buộc với quyền truy cập. Nếu có nhiều shard chạy song song hoặc cần **merge thứ tự toàn cục**, cursor có thể phải giữ trạng thái đọc của từng nguồn và các hàng đang đệm (buffer), hoặc lưu state phía server. Đây là bài toán phức tạp hơn nhiều so với bọc một paging state.

**Giới hạn chi phí:** đặt ngưỡng số ngày/partition/shard được phép truy cập, deadline request, concurrency, page size và tổng số hàng. Không để một cursor hợp lệ nhưng quá rộng gây fan-out vô hạn.

### Keyset pagination là lựa chọn khác, không phải raw paging state

Nếu thiết kế muốn một cursor độc lập với byte state của driver, có thể lưu khóa cuối của hàng:

~~~text
lastOccurredAt = 2026-11-25T08:30:00Z
lastEventId    = 550e8400-e29b-41d4-a716-446655440000
~~~

Sau đó đọc các hàng **sau** khóa đó theo đúng thứ tự clustering, bằng các điều kiện range/tuple CQL được Cassandra version hỗ trợ. Đừng tự chuyển một cặp khóa thành điều kiện `OR` kiểu SQL mà không xác minh CQL. Với thời gian trùng nhau, phải dùng cả `event_id` làm tie-breaker.

**Ưu điểm:** token có thể nhỏ và dễ hiểu hơn, nhất là khi qua nhiều bucket. **Giới hạn:** phải bảo đảm khóa thứ tự là ổn định, predicate CQL hợp lệ, xử lý đúng việc chuyển partition và dữ liệu đến muộn. Vẫn phải ký/mã hóa token và kiểm tra quyền như paging-state cursor.

## 13. Spring Data Repository, CassandraTemplate và projection

Trong Spring Data Cassandra, ta có nhiều đường truy cập:

| Nhu cầu | Công cụ |
| --- | --- |
| CRUD và truy vấn theo khóa đơn giản | `CassandraRepository` |
| Chọn cột/điều kiện có mapping entity | `CassandraTemplate`, `@Query` hoặc projection |
| Reactive pipeline | `ReactiveCassandraRepository`, `ReactiveCassandraTemplate` |
| Kiểm soát page state của driver theo yêu cầu API | `CqlSession` với prepared/bound statement và driver paging API |

Ví dụ repository chọn cột rõ ràng:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("""
        SELECT tenant_id, event_day, occurred_at, event_id,
               event_type, status
        FROM events_by_tenant_day
        WHERE tenant_id = ?0 AND event_day = ?1
        """)
    List<EventRow> findSummaries(
        UUID tenantId, LocalDate eventDay
    );
}
~~~

Đoạn trên minh họa **projection ở mức CQL**, không phải phương án phân trang production cho partition lớn: trả `List` có thể materialize rất nhiều hàng. Khi muốn dùng projection interface/DTO, cần chọn kiểu kết quả và mapping phù hợp với phiên bản Spring Data; chỉ chọn một vài cột CQL rồi tự động map thành entity đầy đủ có thể dẫn đến các thuộc tính thiếu giá trị.

**Page/Slice/Pageable không đồng nghĩa offset SQL:** một số API Spring Data có hỗ trợ phân trang hoặc slice theo driver paging state tùy phiên bản, nhưng không nên giả định `PageRequest.of(1000, 25)` sẽ nhảy trực tiếp đến trang 1000 mà không quét các trang trước. Nếu public API cần token opaque, phải xác định rõ cách framework cung cấp/khôi phục state; đôi khi tích hợp trực tiếp Java Driver đơn giản hơn.

Khi dùng `@Query`, `CassandraTemplate` hay driver, điều kiện `WHERE` vẫn phải phù hợp partition/clustering key. Projection và cursor **không sửa được** truy vấn quét toàn cluster hoặc partition nóng.

## 14. Các lỗi bảo mật và vận hành thường gặp

| Sai lầm | Rủi ro | Biện pháp |
| --- | --- | --- |
| Trả Base64URL(raw paging state) | Không có bảo vệ tính toàn vẹn và scope API | Bọc metadata rồi ký hoặc mã hóa xác thực |
| Tin vào tenantId trong cursor mà bỏ qua auth | Có thể dùng nhầm phạm vi dữ liệu | Xác thực/ủy quyền lại mọi request |
| Ký chỉ pagingState, không ký filter/limit | Có thể thay đổi điều kiện mà chữ ký không phát hiện | Ký toàn bộ thông tin ảnh hưởng query |
| Dùng HMAC rồi nghĩ nội dung được giấu | Base64URL payload có thể đọc được | Dùng AES-GCM nếu cần confidentiality |
| Không giới hạn kích thước token | Tiêu hao bộ nhớ/CPU do input lớn | Chặn trước khi decode/parse |
| Cursor không có expiry | Token cũ sống lâu, khó thu hồi/đổi schema | Có hạn dùng và key rotation |
| Ghi full cursor vào log | Rò rỉ thông tin truy vấn hoặc trạng thái | Redact token, log request ID/metrics |
| Dùng raw state của partition khác | Kết quả lỗi/sai hoặc driver từ chối | Ràng buộc query/parameter và reset state khi đổi partition |
| Lấy `List` toàn bộ rồi cắt 25 hàng | Tốn network và heap, không phải server paging | Đọc một driver page và tạo cursor |
| Hứa “snapshot bất biến” | Ghi/xóa/TTL làm thay đổi các trang | Nêu semantics eventual/changing data rõ ràng |
| Coi `LIMIT` và page size là một | Trang có thể dừng sau tổng limit ngoài mong muốn | Thiết kế limit và fetch size riêng |
| Truy vấn nhiều ngày bằng một raw state | Một state không mô tả nhiều partition đã merge | Cursor cấp ứng dụng quản lý từng bucket/shard |

### Checklist triển khai

- [ ] Schema có partition key, clustering key và thứ tự phù hợp API.
- [ ] Query danh sách chỉ chọn các cột cần thiết; payload lớn được đọc ở endpoint chi tiết.
- [ ] Prepared CQL và bound parameters ổn định trên mọi lần tiếp tục.
- [ ] Server giới hạn page size, số bucket/partition, concurrency và thời gian xử lý.
- [ ] Cursor có query/version, identity/tenant scope, fingerprint filter, paging state và expiry.
- [ ] Tính toàn vẹn được bảo vệ bằng HMAC hoặc AES-GCM; có confidentiality nếu cần.
- [ ] Mọi request đều xác thực và kiểm tra quyền lại.
- [ ] Key rotation, thu hồi quyền, replay và logging/redaction có chính sách rõ.
- [ ] Có kiểm thử token sửa đổi, token hết hạn, đổi tenant/filter, pagination khi dữ liệu thay đổi.
- [ ] Với nhiều ngày/shard, có cursor cấp ứng dụng và giới hạn fan-out.

## 15. Kiểm thử API cursor từ đầu đến cuối

Hãy chạy các kịch bản trong môi trường test có Cassandra và Spring Data/Java Driver đúng phiên bản:

1. **Trang đầu:** ghi hơn 25 sự kiện thuộc cùng tenant/ngày; gọi `limit=25`. Kiểm tra số hàng, thứ tự và `nextCursor`.
2. **Trang kế:** gọi API bằng cursor đã trả; xác minh không lặp những hàng đã có trong dữ liệu **không thay đổi** và tiếp tục đúng vị trí.
3. **Trang cuối:** lặp tới hết; `hasMore=false` và `nextCursor=null`.
4. **Cursor giả:** sửa một ký tự ở payload, key ID hoặc signature; server phải từ chối trước khi query Cassandra.
5. **Đổi principal/tenant:** dùng cursor của A trong phiên B; phải bị từ chối, kể cả chữ ký hoàn toàn đúng.
6. **Đổi filter, projection hoặc limit:** yêu cầu mới phải bị từ chối hoặc buộc bắt đầu lại từ trang đầu theo hợp đồng.
7. **Token hết hạn:** dùng token sau `expiresAt`; server trả lỗi có cấu trúc, không cố dùng raw paging state cũ.
8. **Token quá dài/không phải Base64:** server chặn nhanh, không làm tăng CPU hoặc tạo lỗi hạ tầng.
9. **Thay đổi dữ liệu giữa các trang:** insert, delete và TTL; xác nhận hành vi được ghi rõ trong hợp đồng API, không kỳ vọng snapshot.
10. **Schema/version đổi:** thử cursor từ query version cũ; kiểm tra cơ chế tương thích hoặc thông báo tải lại trang đầu.
11. **Nhiều ngày:** tạo dữ liệu qua ranh giới ngày UTC; kiểm tra cursor chuyển sang partition kế tiếp và không dùng nhầm paging state.
12. **Tải lớn:** đo p95/p99, request/replica, tỷ lệ lỗi và kích thước token; giới hạn số cursor request đồng thời.

Một vài chỉ số vận hành nên theo dõi **mà không log token thô**:

| Metric | Ý nghĩa |
| --- | --- |
| `cursor_valid_total` / `cursor_invalid_total` | Chất lượng input và dấu hiệu lạm dụng |
| `cursor_expired_total` | Hạn dùng có phù hợp hành vi người dùng không |
| `cursor_page_latency_ms` | Độ trễ truy vấn theo từng trang |
| `cursor_page_rows` | Số hàng thực tế trả ra |
| `cursor_token_bytes` | Kích thước cursor và nguy cơ vượt giới hạn URL |
| `cursor_partition_fanout` | Số partition/shard được đọc cho một yêu cầu |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không nên expose trực tiếp Base64URL của paging state làm public cursor?

**Đáp án:** Base64URL không chống sửa đổi hoặc ràng buộc token với người dùng/tenant/bộ lọc. Cần đóng gói metadata, ký hoặc mã hóa xác thực và kiểm tra quyền trên mỗi request.

**Câu 2.** Nếu client lấy cursor của tenant A rồi gửi kèm tenant B, server nên làm gì?

**Đáp án:** Từ chối yêu cầu hoặc yêu cầu bắt đầu lại; không dùng state của A cho B, và phải so khớp quyền của principal đang xác thực.

**Câu 3.** Có thể dùng paging state của `event_day=2026-11-25` cho truy vấn `event_day=2026-11-24` không?

**Đáp án:** Không. Paging state gắn với câu CQL và parameter; khi đổi bucket phải bắt đầu state tương ứng của bucket mới.

**Câu 4.** HMAC-SHA256 có che giấu `tenantId` và thông tin filter khỏi người cầm token không?

**Đáp án:** Không. HMAC bảo vệ tính toàn vẹn, còn payload Base64URL vẫn đọc được; muốn giữ bí mật phải dùng mã hóa xác thực như AES-GCM hoặc server-side opaque ID.

**Câu 5.** Dùng `setPageSize(25)` có đồng nghĩa query chỉ đọc tối đa 25 hàng trong toàn bộ vòng đời không?

**Đáp án:** Không. Nó quy định kích thước fetch/page; query có thể còn page sau. Cũng không thay đổi kích thước partition.

**Câu 6.** Cursor có tạo snapshot bất biến giữa những lần gọi không?

**Đáp án:** Không. Ghi mới, xóa, TTL và dữ liệu đến muộn có thể ảnh hưởng kết quả. Nếu cần snapshot chính xác, phải có kiến trúc/kết xuất dữ liệu riêng.

**Câu 7.** API cần lịch sử của 30 ngày. Có thể chỉ lưu một raw driver paging state và đổi `event_day` khi hết một ngày không?

**Đáp án:** Không. Cursor cấp ứng dụng phải quản lý ngày hiện tại, trạng thái của partition đó và phạm vi ngày; khi đổi partition phải bắt đầu state mới. Nếu có nhiều nguồn đồng thời, còn cần quản lý merge và trạng thái của từng nguồn.

---

**Ghi nhớ:** một API cursor tốt trên **Spring Data Cassandra** phải bắt đầu từ **bảng/query theo partition key**, chọn projection nhỏ, lấy từng page bằng driver và dùng paging state **chỉ cho đúng câu CQL cùng tham số**. Public cursor cần được **ký hoặc mã hóa xác thực**, ràng buộc với subject/tenant, filter, projection, page size và expiry; authorization phải được kiểm tra mỗi lần. Cursor giúp tiếp tục truy vấn hiệu quả, **không phải snapshot, không phải access token và không thay thế thiết kế dữ liệu phân tán đúng**.
