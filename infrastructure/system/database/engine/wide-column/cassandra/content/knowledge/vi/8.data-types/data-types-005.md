# blob, boolean, inet và ánh xạ dữ liệu nhị phân/địa chỉ trong Apache Cassandra

Trong Apache Cassandra, ba kiểu `blob`, `boolean` và `inet` giải quyết ba bài toán khác nhau: **lưu byte nguyên gốc**, **biểu diễn đúng/sai**, và **lưu địa chỉ IP dưới dạng có cấu trúc**. Chúng thường xuất hiện trong bảng sự kiện API, telemetry, audit, quản lý phiên kết nối, checksum, hoặc metadata của tệp.

Bài thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Module học kiến trúc wide-column phân tán, khóa phân vùng, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, replication, compaction, repair, xử lý lỗi và tích hợp Java. Khi chọn ba kiểu trên, cần đồng thời trả lời: **giá trị có ý nghĩa gì, ứng dụng Java biểu diễn ra sao, dữ liệu sẽ được truy vấn theo partition/clustering key nào, và những thao tác retry hay cập nhật sẽ ảnh hưởng đến tính đúng đắn như thế nào?**

## 1. Tổng quan nhanh

| Kiểu CQL | Giá trị được biểu diễn | Java Driver 4.x thường dùng | Trường hợp phù hợp | Không thay thế được |
|---|---|---|---|---|
| `blob` | Chuỗi byte nhị phân, không tự diễn giải encoding | `ByteBuffer` | Digest SHA-256, mã hóa nhị phân nhỏ, ảnh thu nhỏ nhỏ có giới hạn, header/protocol bytes | Object storage, bộ giải mã JSON/UTF-8, lược đồ file lớn |
| `boolean` | Hai giá trị `true`/`false` khi cột có giá trị | `boolean`/`Boolean` tùy null handling | Cờ trạng thái, kết quả kiểm tra, điều kiện bật/tắt | Trạng thái nhiều bước hoặc trạng thái chưa biết |
| `inet` | Một địa chỉ IPv4 hoặc IPv6 | `InetAddress` | IP nguồn, IP đích, địa chỉ node/service được ghi như giá trị IP | Hostname, URL, subnet/CIDR, dải địa chỉ |

Một số giá trị dễ nhầm:

- `0x4f4b` là **literal nhị phân** trong CQL, gồm hai byte hex `4f` và `4b`. Các byte đó tình cờ là ASCII của chữ “OK”, nhưng kiểu `blob` không coi đây là chuỗi văn bản.
- `true` là giá trị **boolean**. Chuỗi `'true'`, số `1` và giá trị `null` không đồng nghĩa với `true`.
- `'203.0.113.24'` là một ví dụ **IPv4**, `'2001:db8::24'` là ví dụ **IPv6** dùng dải địa chỉ dành cho tài liệu. Chúng phù hợp để minh họa một cột `inet`, nhưng `'api.example.com'` là hostname, không phải địa chỉ IP literal.
- `inet` hỗ trợ cả IPv4 và IPv6; không cần tạo hai cột riêng chỉ vì có hai họ địa chỉ.

Các kiểu dữ liệu quyết định **ngữ nghĩa giá trị**, còn khả năng tìm kiếm như “lấy 100 request gần nhất của tenant” hoặc “tìm request theo IP trong ngày” phụ thuộc trước tiên vào **primary key và bảng được thiết kế theo truy vấn**.

## 2. Kiểu blob: lưu đúng byte, không tự biết nội dung

### 2.1. blob là gì?

`blob` (*binary large object*) biểu diễn chuỗi byte. Khác với `text`/`varchar` là chuỗi Unicode UTF-8, một giá trị `blob` không có thông tin mặc định về **charset**, MIME type, định dạng dữ liệu hay quy tắc decode.

Ví dụ:

~~~cql
CREATE TABLE tiny_binary_samples_by_id (
    sample_id uuid PRIMARY KEY,
    format_code text,
    payload blob
);

INSERT INTO tiny_binary_samples_by_id
    (sample_id, format_code, payload)
VALUES
    (11111111-1111-4111-8111-111111111111, 'RAW', 0x004f4bff);

SELECT format_code, payload
FROM tiny_binary_samples_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Giá trị `0x004f4bff` chứa bốn byte: `00`, `4f`, `4b`, `ff`. Không nên tự động giải mã cả bốn byte thành UTF-8: `ff` đứng độc lập không phải một byte UTF-8 hợp lệ.

CQL dùng tiền tố `0x` cho literal hex của `blob`. Một byte có **hai chữ số hex**, nên ký hiệu `0x004f4bff` là **4 byte**, không phải tám byte. Khi truy cập bằng Java Driver, ứng dụng làm việc với `ByteBuffer` và phải chủ động quyết định có decode thành văn bản hay không.

### 2.2. Byte gốc, text UTF-8, Base64 và hex khác nhau

Cùng một dữ liệu nhị phân có thể có nhiều biểu diễn:

| Biểu diễn | Ví dụ cho hai byte `4f 4b` | Vai trò |
|---|---|---|
| Byte nhị phân | `4f 4b` | Dữ liệu thực sự, lưu dưới `blob` |
| Literal CQL hex | `0x4f4b` | Cách viết dữ liệu nhị phân trong câu lệnh CQL |
| Base64 | `T0s=` | Cách chuyển byte sang chữ để truyền qua giao thức chỉ nhận text |
| ASCII/UTF-8 text | `OK` | Diễn giải những byte này thành văn bản theo charset được chọn |

**Base64 là encoding truyền tải, không phải mã hóa bảo mật.** Nếu API gửi `"T0s="` (Base64), Java cần decode thành hai byte trước khi bind vào `blob`. Nếu lưu nguyên chuỗi `"T0s="` vào `text`, giá trị được lưu là bốn ký tự, không phải hai byte gốc.

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] raw = new byte[] { 0x4f, 0x4b };

String asText = new String(raw, StandardCharsets.UTF_8); // "OK"
String asBase64 = Base64.getEncoder().encodeToString(raw); // "T0s="

byte[] decoded = Base64.getDecoder().decode(asBase64);
ByteBuffer payload = ByteBuffer.wrap(decoded);
~~~

Đối với dữ liệu JSON, XML, log hay tên người dùng cần đọc hiểu trực tiếp, `text`/`varchar` thường có ý nghĩa hơn `blob`; dùng `blob` khi **chính byte gốc** quan trọng. Nếu yêu cầu bảo toàn chính xác byte nhưng dữ liệu là văn bản, cần tài liệu hóa charset, normalization và cách xử lý chuỗi không hợp lệ.

### 2.3. Nên lưu gì bằng blob?

Các giá trị tương đối nhỏ, có kích thước giới hạn, ví dụ:

- **Digest/hash** của nội dung (`SHA-256` là 32 byte), dùng để kiểm tra tính toàn vẹn hoặc làm khóa tra cứu theo digest.
- **Signature bytes**, trường giao thức nhị phân, dữ liệu cảm biến được serialize theo giao thức có phiên bản.
- **Payload mẫu nhỏ** phục vụ debug khi chính sách vận hành cho phép và đã có giới hạn kích thước.
- **Binary identifier** do hệ khác cấp, nếu không phải ID có kiểu CQL phù hợp hơn (như `uuid`).

Một digest chỉ chứa **kết quả băm**, không cho phép khôi phục dữ liệu nguồn. Hash có rủi ro va chạm về mặt toán học, dù SHA-256 đủ mạnh cho nhiều mục tiêu kỹ thuật; nếu ứng dụng dùng digest làm nhận diện duy nhất có ý nghĩa pháp lý hoặc tài chính, cần chính sách kiểm tra/tránh trùng phù hợp.

Ngược lại, **không nên mặc định đưa video, ảnh độ phân giải lớn, file sao lưu hoặc tài liệu nhiều MB/GB vào một cell `blob`**. Cassandra là hệ thống phục vụ truy vấn có partition key và dữ liệu dạng hàng/cột; object storage thường phù hợp hơn cho file lớn. Mô hình phổ biến là Cassandra lưu `object_uri text`, `content_type text`, `size_bytes bigint`, `sha256 blob` cùng trạng thái và metadata truy vấn, còn file gốc ở kho đối tượng.

Các lợi ích của việc tách file lớn gồm giảm áp lực bộ nhớ/GC trên client, giảm truyền qua coordinator/replica, tránh row/partition quá lớn, và đơn giản hóa việc stream/range download. Quyết định cuối cùng vẫn phải dựa trên SLA và tải đo được.

## 3. Java ByteBuffer: vùng dữ liệu phải được xử lý đúng

### 3.1. Ánh xạ blob ↔ ByteBuffer

Với Apache Cassandra Java Driver 4.x, phương thức phổ biến là:

- Ghi: `BoundStatementBuilder.setByteBuffer(index, ByteBuffer)`.
- Đọc: `Row.getByteBuffer("payload")`.
- Kiểm tra thiếu dữ liệu: `row == null` hoặc `row.isNull("payload")`.

`ByteBuffer` có các thuộc tính **position, limit, capacity**. Phần byte đang có hiệu lực để đọc thường là đoạn từ `position` (bao gồm) đến `limit` (không bao gồm), có độ dài `remaining()`.

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

byte[] source = new byte[] { 0x00, 0x4f, 0x4b, (byte) 0xff };
ByteBuffer buffer = ByteBuffer.wrap(source);
buffer.position(1); // Bỏ qua byte đầu tiên.

System.out.println(buffer.remaining()); // 3
// Phần byte còn lại là: 4f 4b ff

ByteBuffer view = buffer.duplicate();
byte[] remaining = new byte[view.remaining()];
view.get(remaining);

System.out.println(Arrays.toString(remaining));
// [79, 75, -1] vì Java byte có dấu.
~~~

Hệ quả quan trọng:

1. **Đừng mặc định `buffer.array()` luôn dùng được.** Direct buffer, read-only buffer hoặc slice có thể không cung cấp array, và array gốc có thể chứa cả vùng dữ liệu ngoài `position..limit`.
2. **Đừng tự ý thay đổi `position` của buffer mà caller còn dùng.** Có thể dùng `duplicate()`/ `asReadOnlyBuffer()` để đọc trên một view độc lập về vị trí.
3. **Đừng sửa mảng/buffer đã bind khi thao tác ghi bất đồng bộ còn sử dụng nó.** `ByteBuffer.wrap(byte[])` chia sẻ nội dung với mảng đầu vào. Nếu cần snapshot, hãy sao chép byte trước khi bind.
4. Nếu dữ liệu là văn bản UTF-8, ứng dụng phải decode bằng charset xác định và xác định rõ hành vi khi gặp byte không hợp lệ.

### 3.2. Sao chép byte phòng việc mutation

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

static ByteBuffer snapshot(byte[] original) {
    byte[] copy = Arrays.copyOf(original, original.length);
    return ByteBuffer.wrap(copy).asReadOnlyBuffer();
}

static byte[] copyRemaining(ByteBuffer input) {
    ByteBuffer view = input.duplicate();
    byte[] bytes = new byte[view.remaining()];
    view.get(bytes);
    return bytes;
}
~~~

Đây là ví dụ cho payload **đã được kiểm tra giới hạn kích thước**. Không đọc toàn bộ file rất lớn vào `byte[]` chỉ để tạo một `ByteBuffer`; hãy dùng object storage hoặc cơ chế streaming chuyên dụng theo nhu cầu.

### 3.3. Hash nội dung trước khi lưu

~~~java
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

static ByteBuffer sha256(byte[] bytes) throws NoSuchAlgorithmException {
    byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
    // SHA-256 có 32 byte.
    return ByteBuffer.wrap(digest);
}
~~~

Nếu lưu `sha256 blob`, mọi ứng dụng cần băm **cùng tập byte gốc**. Một file JSON có nội dung tương đương nhưng khác khoảng trắng hoặc thứ tự key sẽ cho digest khác khi băm byte thô. Hash không thay thế được quyết định về canonicalization của định dạng.

## 4. boolean: đúng/sai và trường hợp chưa biết

CQL `boolean` biểu diễn **`true`** và **`false`**. Cột không có giá trị có thể được đọc là **`null`**, mang nghĩa khác với false nếu nghiệp vụ yêu cầu phân biệt “chưa xử lý” với “đã xử lý và thất bại”.

Ví dụ:

~~~cql
CREATE TABLE verification_by_request (
    request_id uuid PRIMARY KEY,
    passed boolean,
    verifier text,
    checked_at timestamp
);

INSERT INTO verification_by_request (request_id, passed, verifier, checked_at)
VALUES (22222222-2222-4222-8222-222222222222, true,
        'risk-service', '2026-11-21T02:00:00Z');

INSERT INTO verification_by_request (request_id, passed, verifier, checked_at)
VALUES (33333333-3333-4333-8333-333333333333, false,
        'risk-service', '2026-11-21T02:01:00Z');
~~~

Phân biệt:

| Trạng thái nghiệp vụ | Giá trị `passed` | Ý nghĩa |
|---|---|---|
| Đã kiểm tra và đạt | `true` | Kết quả xác nhận đạt |
| Đã kiểm tra và không đạt | `false` | Kết quả xác nhận không đạt |
| Chưa kiểm tra / chưa có kết quả | Cột vắng mặt hoặc `null` | Chưa có giá trị boolean để kết luận |

Cassandra không có khái niệm “boolean nullable có default false” chỉ nhờ khai báo `boolean`. Nếu cần **trạng thái có nhiều bước** như `QUEUED`, `RUNNING`, `APPROVED`, `REJECTED`, `EXPIRED`, một cột `state text` với danh mục hợp lệ hoặc mô hình trạng thái khác sẽ diễn đạt tốt hơn.

**Cẩn trọng khi cập nhật:** trong Cassandra, ghi `null` rõ ràng vào cột thường được hiểu là **xóa giá trị**, tạo tombstone. Bỏ qua không ghi cột hoặc dùng cơ chế **UNSET** của driver có ý nghĩa khác với ghi `null`. Nếu ứng dụng muốn giữ giá trị cũ khi một trường không được cung cấp trong patch request, không nên bind `null` như một cách diễn đạt “không thay đổi”.

### 4.1. boolean trong Java

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

Row row = session.execute(
    "SELECT passed FROM verification_by_request "
  + "WHERE request_id = 22222222-2222-4222-8222-222222222222"
).one();

if (row == null || row.isNull("passed")) {
    // Chưa có dòng hoặc cột chưa có giá trị.
} else {
    boolean passed = row.getBoolean("passed");
    // passed có thể là true hoặc false.
}
~~~

`Row.getBoolean()` trả kiểu primitive `boolean`, không biểu diễn được `null`; kiểm tra `isNull` trước khi đọc nếu cần trạng thái ba nhánh.

Trong prepared statement, dùng `setBoolean(index, value)`. Nếu ứng dụng nhận `Boolean` có thể null, phải quyết định nghiệp vụ trước khi bind: ghi true, false, xóa trường hay giữ nguyên giá trị cũ. Không vô tình chuyển `null` thành false bằng giá trị mặc định của Java.

### 4.2. boolean và thiết kế partition key

Không nên chọn **một cột boolean duy nhất** làm partition key cho bảng lớn: toàn bộ dữ liệu chỉ có hai giá trị khóa thường gặp, tạo rất ít partition, dễ gây phân vùng khổng lồ và hotspot.

Nếu truy vấn là “lấy những giao dịch thất bại của một tenant trong một ngày”, hãy thiết kế bảng theo `tenant_id`, bucket thời gian và trạng thái (nếu cần), thay vì suy luận rằng mọi câu `WHERE passed = false` đều hiệu quả chỉ vì `passed` là boolean.

**Không dùng `ALLOW FILTERING` như một phương án mặc định** để tìm tất cả dòng có cờ false trên cluster lớn. Điều kiện trên một cột không thuộc khóa/chỉ mục phù hợp có thể yêu cầu quét nhiều dữ liệu.

## 5. inet: địa chỉ IPv4 và IPv6 có cấu trúc

### 5.1. Khi nào dùng inet thay text?

Kiểu `inet` lưu một địa chỉ IP, có thể là IPv4 (32 bit) hoặc IPv6 (128 bit). Khác với `text`, nó có ngữ nghĩa **địa chỉ IP**, giúp ứng dụng và driver đọc/ghi qua kiểu `InetAddress`.

~~~cql
CREATE TABLE endpoints_by_service (
    service_id uuid,
    endpoint_id uuid,
    ip_address inet,
    port int,
    protocol ascii,
    PRIMARY KEY ((service_id), endpoint_id)
);

INSERT INTO endpoints_by_service
    (service_id, endpoint_id, ip_address, port, protocol)
VALUES
    (44444444-4444-4444-8444-444444444444,
     55555555-5555-4555-8555-555555555555,
     '2001:db8::24', 443, 'TCP');

INSERT INTO endpoints_by_service
    (service_id, endpoint_id, ip_address, port, protocol)
VALUES
    (44444444-4444-4444-8444-444444444444,
     66666666-6666-4666-8666-666666666666,
     '203.0.113.24', 8443, 'TCP');
~~~

Lưu ý: `inet` chỉ chứa địa chỉ IP. Để mô hình hóa một endpoint thực tế còn cần **port** (0–65535 theo quy tắc ứng dụng), **protocol**, và có thể thêm **hostname**, **environment** hoặc thông tin chứng chỉ. `inet` không thay thế cả một URL hoặc socket address.

Nếu nguồn dữ liệu là `https://api.example.com:443`, không thể ép toàn bộ URL vào `inet`. Nếu cần lưu hostname và tra DNS động, nên có cột `host_name text` riêng, vì một hostname có thể trỏ đến nhiều địa chỉ IP và kết quả DNS thay đổi theo thời gian.

### 5.2. inet không biểu diễn subnet, CIDR hoặc IP range

| Đầu vào | Dùng `inet` trực tiếp? | Cách diễn đạt phù hợp |
|---|---|---|
| `203.0.113.24` | Có | Một địa chỉ IPv4 |
| `2001:db8::24` | Có | Một địa chỉ IPv6 |
| `203.0.113.0/24` | Không | Một mạng CIDR: lưu `network_address` + `prefix_length` hoặc chuỗi/ràng buộc có xử lý riêng |
| `api.example.com` | Không | Hostname trong `text` |
| `203.0.113.24:443` | Không | IP `inet` và port `int` riêng |
| Một dải từ IP A đến IP B | Không dưới dạng một giá trị `inet` | Mô hình start/end IP hoặc prefix, thuật toán kiểm tra vùng ở ứng dụng |

Truy vấn dạng “địa chỉ IP này thuộc mạng /24 nào?” thường cần xử lý subnet ở ứng dụng hoặc thiết kế bảng/khóa theo prefix chuẩn hóa. `inet` không tự cung cấp toán tử chọn tất cả IP thuộc CIDR như một hệ thống định tuyến chuyên dụng.

### 5.3. Chuẩn hóa IP và sự khác biệt IPv4/IPv6

IPv6 có thể có nhiều **biểu diễn văn bản tương đương** do cách rút gọn các nhóm hex và số 0. Khi dữ liệu là một IP thực sự, `inet` giúp làm việc với giá trị IP đã parse thay vì phụ thuộc định dạng hiển thị người gửi.

Tuy nhiên, các địa chỉ như IPv4 thuần và **IPv4-mapped IPv6** không nên bị tự động coi là cùng một thực thể trong nghiệp vụ nếu chưa có quy tắc chuẩn hóa. Hệ thống cần quyết định có chấp nhận IPv4-mapped IPv6 hay không, có giữ nguyên họ địa chỉ hay không, và cách mô hình proxy/NAT.

**Quan trọng với log mạng:** địa chỉ IP nhìn thấy tại web server có thể là địa chỉ của **reverse proxy, load balancer hoặc NAT**, không phải IP của thiết bị cuối. Các header như `X-Forwarded-For` chỉ đáng tin khi đi qua chuỗi proxy tin cậy với chính sách parse/ghi rõ ràng. Kiểu `inet` xác nhận dạng địa chỉ, **không xác minh được nguồn gốc** của địa chỉ.

## 6. Java InetAddress: bind và đọc địa chỉ an toàn

Apache Cassandra Java Driver 4.x thường ánh xạ `inet` sang Java `InetAddress`:

- Ghi: `BoundStatementBuilder.setInetAddress(index, value)`.
- Đọc: `Row.getInetAddress("ip_address")`.
- Kiểm tra thiếu: `row.isNull("ip_address")`.

Ví dụ tạo IPv4 mà không cần tra DNS:

~~~java
import java.net.InetAddress;
import java.net.UnknownHostException;

byte[] ipv4Bytes = new byte[] {
    (byte) 203, 0, 113, 24
};

InetAddress ip = InetAddress.getByAddress(ipv4Bytes);
System.out.println(ip.getHostAddress()); // 203.0.113.24
~~~

`InetAddress.getByName(input)` có thể **truy vấn DNS** khi `input` là hostname, nên không phải cách validate “input bắt buộc là IP literal” nếu không có bước kiểm tra riêng. Với nguồn không đáng tin hoặc luồng ingest lớn, hãy dùng parser chỉ chấp nhận IPv4/IPv6 literal và tạo `InetAddress` từ byte đã xác thực; không ngầm thực hiện DNS cho mọi dòng.

Ví dụ kết nối CQL:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetAddress;
import java.util.UUID;

// session là CqlSession đã cấu hình keyspace/cluster ở bên ngoài ví dụ.
UUID serviceId = UUID.fromString("44444444-4444-4444-8444-444444444444");
UUID endpointId = UUID.fromString("55555555-5555-4555-8555-555555555555");

InetAddress address = InetAddress.getByAddress(
    new byte[] {(byte) 203, 0, 113, 24}
);

PreparedStatement ps = session.prepare(
    "INSERT INTO endpoints_by_service "
  + "(service_id, endpoint_id, ip_address, port, protocol) "
  + "VALUES (?, ?, ?, ?, ?)");

BoundStatement bound = ps.boundStatementBuilder()
    .setUuid(0, serviceId)
    .setUuid(1, endpointId)
    .setInetAddress(2, address)
    .setInt(3, 443)
    .setString(4, "TCP")
    .build();

session.execute(bound);
~~~

Khi đọc:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement find = session.prepare(
    "SELECT ip_address, port, protocol "
  + "FROM endpoints_by_service "
  + "WHERE service_id = ? AND endpoint_id = ?");

Row result = session.execute(
    find.bind(serviceId, endpointId)
).one();

if (result != null && !result.isNull("ip_address")) {
    InetAddress stored = result.getInetAddress("ip_address");
    String display = stored.getHostAddress(); // Địa chỉ dạng số để hiển thị.
    int port = result.getInt("port");
}
~~~

`getHostAddress()` trả địa chỉ dạng số. Không gọi `getHostName()` chỉ để format log nếu không muốn nguy cơ tra cứu tên ngược hoặc chờ mạng. Việc log IP còn phải tuân thủ chính sách bảo vệ dữ liệu của hệ thống.

## 7. Bài toán tổng hợp: audit request theo tenant và ngày

Giả sử ứng dụng Java cần đáp ứng truy vấn:

> “Lấy 100 API request gần nhất của một tenant trong một ngày, xem request thành công không, IP nguồn và một mẫu byte nhỏ để chẩn đoán.”

Thiết kế bảng CQL:

~~~cql
CREATE TABLE api_requests_by_tenant_day (
    tenant_id uuid,
    request_day date,
    occurred_at timestamp,
    request_id uuid,
    succeeded boolean,
    client_ip inet,
    payload_preview blob,
    error_code text,
    PRIMARY KEY ((tenant_id, request_day), occurred_at, request_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, request_id ASC);
~~~

Giải thích:

- `(tenant_id, request_day)` là **partition key** kép, gom sự kiện theo tenant/ngày.
- `occurred_at timestamp` là clustering column sắp từ mới đến cũ; `request_id uuid` phân biệt các request có cùng mili giây.
- `succeeded boolean` chỉ kết quả true/false; nếu cần phân biệt pending, hãy định nghĩa trạng thái nghiệp vụ rõ ràng.
- `client_ip inet` lưu một IP đã parse và xác thực nguồn tin cậy.
- `payload_preview blob` là **trích đoạn byte có giới hạn**, không phải toàn bộ file/request lớn.
- `error_code text` có thể vắng mặt với request thành công; kiểm tra null khi đọc.

~~~cql
INSERT INTO api_requests_by_tenant_day (
    tenant_id, request_day, occurred_at, request_id,
    succeeded, client_ip, payload_preview, error_code
) VALUES (
    77777777-7777-4777-8777-777777777777,
    '2026-11-21', '2026-11-21T03:15:00Z',
    88888888-8888-4888-8888-888888888888,
    true, '203.0.113.24', 0x4f4b, null
);

SELECT occurred_at, request_id, succeeded, client_ip,
       payload_preview, error_code
FROM api_requests_by_tenant_day
WHERE tenant_id = 77777777-7777-4777-8777-777777777777
  AND request_day = '2026-11-21'
LIMIT 100;
~~~

Trong ví dụ `payload_preview = 0x4f4b` gồm hai byte dữ liệu; `error_code = null` minh họa cột không có giá trị. Ở nghiệp vụ thực tế, nếu trường không có giá trị, có thể **bỏ cột khỏi INSERT** để tránh ghi tombstone do null rõ ràng. Đây cũng là cách thích hợp khi một yêu cầu không có payload preview.

### 7.1. Viết từ Java với prepared statement

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.net.InetAddress;
import java.nio.ByteBuffer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

UUID tenantId = UUID.fromString("77777777-7777-4777-8777-777777777777");
UUID requestId = UUID.fromString("88888888-8888-4888-8888-888888888888");
Instant occurredAt = Instant.parse("2026-11-21T03:15:00Z");
LocalDate dayUtc = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();

InetAddress clientIp = InetAddress.getByAddress(
    new byte[] {(byte) 203, 0, 113, 24}
);

byte[] previewBytes = new byte[] { 0x4f, 0x4b }; // Dữ liệu có giới hạn.
ByteBuffer preview = ByteBuffer.wrap(previewBytes.clone());

PreparedStatement insert = session.prepare(
    "INSERT INTO api_requests_by_tenant_day "
  + "(tenant_id, request_day, occurred_at, request_id, "
  + " succeeded, client_ip, payload_preview) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement request = insert.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setLocalDate(1, dayUtc)
    .setInstant(2, occurredAt)
    .setUuid(3, requestId)
    .setBoolean(4, true)
    .setInetAddress(5, clientIp)
    .setByteBuffer(6, preview)
    .build();

session.execute(request);
~~~

Ở đây có hai quyết định bảo toàn tính đúng:

1. **Bucket ngày** được tạo từ `occurredAt` theo UTC. Mọi client ghi/đọc phải dùng cùng quy tắc để tránh lưu request vào partition ngày khác nhau vì múi giờ.
2. **`requestId`, `occurredAt` và partition key** được giữ ổn định khi retry. Nếu sau timeout mỗi lần thử lại tạo UUID và timestamp mới, cùng một sự kiện có thể thành nhiều dòng.

Ngay cả khi ghi cùng khóa, cập nhật một cell với giá trị khác nhau chịu quy tắc giải quyết xung đột của Cassandra. **Consistency level** như `LOCAL_QUORUM` quyết định mức xác nhận của replica nhưng không thay thế cơ chế idempotency ở nghiệp vụ.

### 7.2. Đọc và diễn giải dữ liệu

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetAddress;
import java.nio.ByteBuffer;

PreparedStatement select = session.prepare(
    "SELECT request_id, succeeded, client_ip, payload_preview "
  + "FROM api_requests_by_tenant_day "
  + "WHERE tenant_id = ? AND request_day = ? LIMIT 100");

for (Row event : session.execute(select.bind(tenantId, dayUtc))) {
    UUID id = event.getUuid("request_id");

    Boolean succeeded = event.isNull("succeeded")
        ? null : event.getBoolean("succeeded");

    InetAddress ip = event.isNull("client_ip")
        ? null : event.getInetAddress("client_ip");

    byte[] previewCopy = null;
    if (!event.isNull("payload_preview")) {
        ByteBuffer view = event.getByteBuffer("payload_preview").duplicate();
        previewCopy = new byte[view.remaining()];
        view.get(previewCopy);
    }

    // Xử lý sự kiện; không giải mã preview thành text khi chưa biết encoding.
}
~~~

Vì `Boolean` có thể null, ứng dụng phân biệt rõ trạng thái chưa có dữ liệu với thất bại `false`. Với IP, nếu cột vắng mặt thì kiểm tra nguồn dữ liệu và quy tắc xử lý. Với blob, truy cập buffer theo **remaining bytes**, không dựa vào `array()`.

### 7.3. Nếu cần truy vấn theo IP thì sao?

Bảng `api_requests_by_tenant_day` được thiết kế để đọc theo tenant/ngày. Truy vấn “tìm mọi request đến từ IP `203.0.113.24` trên toàn cluster trong ngày” **không có đường truy cập trực tiếp** chỉ vì `client_ip` là `inet`.

Một bảng truy vấn khác có thể được xây dựng khi nghiệp vụ thực sự yêu cầu:

~~~cql
CREATE TABLE request_refs_by_ip_day (
    client_ip inet,
    request_day date,
    occurred_at timestamp,
    request_id uuid,
    tenant_id uuid,
    PRIMARY KEY ((client_ip, request_day), occurred_at, request_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, request_id ASC);
~~~

Nhưng thiết kế này cần kiểm tra **hotspot**: nhiều client có thể cùng xuất hiện dưới một IP proxy/NAT và tạo partition lớn. Khi tải cao, có thể cần bucket giờ, shard hoặc mô hình tìm kiếm khác. Ghi hai bảng cũng cần quy tắc đồng bộ, retry và đối soát vì việc ghi hai partition/bảng không mặc nhiên là một giao dịch nguyên tử đa bảng.

## 8. Những giới hạn vận hành cần biết

### 8.1. BLOB lớn làm nặng đường đọc/ghi và compaction

Kích thước blob tăng đồng nghĩa lượng byte qua client, coordinator và replica tăng. Các hàng có payload lớn làm mất lợi thế đọc chính xác các cột nhỏ, tăng áp lực bộ nhớ, network và disk I/O. Compaction cần xử lý SSTable chứa các giá trị đó; repair cần trao đổi thông tin để giữ replica đồng bộ.

Một quy tắc thực dụng là:

- Chọn mức giới hạn payload rõ ràng ở API, ví dụ chỉ giữ **một trích đoạn vài trăm byte** phục vụ debug.
- Lưu `size_bytes bigint`, `sha256 blob`, `content_type text` và URI cho file ở object storage nếu cần nội dung lớn.
- Tránh lưu dữ liệu nhạy cảm trong payload preview; lọc/loại bỏ bí mật hoặc thông tin nhận dạng theo yêu cầu.
- Quan sát p95/p99 latency, kích thước partition, tombstone và compaction theo workload thật.

Không có kiểu `blob` nào tự giới hạn dung lượng giúp bạn nếu ứng dụng không kiểm soát input.

### 8.2. Xóa, TTL và tombstone

Trong Cassandra, xóa cell, ghi null rõ ràng hoặc dữ liệu hết TTL có thể sinh tombstone, ảnh hưởng chi phí đọc và compaction khi tích tụ. Đối với cột boolean vắng mặt, cập nhật `passed = null` không tương đương với cập nhật `passed = false`. Đối với blob, xóa toàn bộ payload để tiết kiệm dữ liệu cũng cần cân nhắc số tombstone và thời điểm compaction dọn dẹp.

Nếu yêu cầu giữ audit nhiều tháng, định nghĩa TTL/retention từ nhu cầu nghiệp vụ thay vì đặt TTL mặc định rồi vô tình mất nguồn chứng cứ. Nếu cần xóa dữ liệu vì yêu cầu bảo vệ dữ liệu, thiết kế xử lý xóa và replica/backup theo chính sách hệ thống.

### 8.3. Consistency, retry, repair và kiểu dữ liệu

Cassandra **replicate** các giá trị đã ghi dưới dạng bytes/cells, và **repair** giúp replica hội tụ. Chúng không:

- Tự decode `blob` sang đúng UTF-8 khi ứng dụng lưu sai byte.
- Biến `false` thành `null` hoặc ngược lại theo trạng thái nghiệp vụ.
- Tự phân biệt IP cuối và IP của reverse proxy.
- Thêm index để tìm toàn bộ IP khi bảng không khớp mẫu truy vấn.
- Bảo đảm request ghi lại nhiều lần sẽ chỉ tạo một sự kiện nếu mỗi lần sinh một primary key mới.

Do đó, tính đúng đắn phải được bảo đảm ở **hợp đồng dữ liệu + thiết kế khóa + xử lý lỗi Java**. Việc lựa chọn consistency level cần dựa trên SLA và yêu cầu đồng thời, không dùng như cách sửa sai ngữ nghĩa cột.

## 9. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Lưu chuỗi Base64 vào `blob` như văn bản gốc | Nội dung không phải byte ban đầu | Decode Base64 thành `byte[]` rồi bind `ByteBuffer` |
| Tự decode mọi blob thành UTF-8 | Byte ngẫu nhiên có thể không hợp lệ, mất dữ liệu | Chỉ decode khi biết charset/format |
| Dùng `ByteBuffer.array()` để lấy payload | Lỗi với direct/read-only buffer, lấy thừa byte | `duplicate()`, `remaining()`, copy đúng vùng |
| Bind buffer rồi thay đổi mảng trước khi ghi async hoàn tất | Có thể ghi byte không mong muốn | Snapshot dữ liệu hoặc quản lý vòng đời buffer |
| Dùng `blob` lưu file hàng trăm MB như một cell | Tải mạng/bộ nhớ/compaction lớn | Object storage + URI/metadata trong Cassandra |
| Gộp “chưa xử lý” và “không đạt” thành `false` | Mất trạng thái nghiệp vụ | Xử lý `null` riêng hoặc thiết kế state |
| Coi bind `null` là “không đổi” | Có thể xóa cell, tạo tombstone | Bỏ cột/UNSET theo ý nghĩa patch |
| Chọn `boolean` làm partition key duy nhất | Chỉ vài partition khổng lồ | Thiết kế composite key theo tenant/bucket |
| Lưu CIDR `203.0.113.0/24` vào `inet` | Không phải một địa chỉ IP đơn lẻ | Mô hình network prefix riêng |
| Dùng `InetAddress.getByName` với input bất kỳ | Có thể tra DNS thay vì chỉ parse literal | Validate địa chỉ literal trước |
| Coi IP proxy là IP người dùng cuối | Thông tin truy vết sai | Chính sách trusted proxy và parsing IP nguồn |
| Lọc `WHERE client_ip = ...` trên bảng không có key/index phù hợp | Quét dữ liệu tốn kém hoặc truy vấn không hợp lệ | Bảng truy vấn theo IP hoặc cơ chế tìm kiếm thích hợp |

## 10. Bài tập áp dụng

### Bài 1 — Sử dụng kiểu nào?

Hệ thống lưu: ảnh hồ sơ 4 MB, SHA-256 digest của ảnh, cờ “đã được duyệt”, IPv6 của client và một CIDR `2001:db8::/32`.

**Gợi ý:** lưu ảnh trong object storage và giữ URI/metadata; SHA-256 digest bằng `blob` 32 byte; cờ duyệt bằng `boolean` nếu miền chỉ đúng/sai; IP đơn bằng `inet`; CIDR cần mô hình network/prefix riêng, không phải một giá trị `inet`.

### Bài 2 — ByteBuffer bị đọc sai

Một buffer có capacity 1024, `position=100`, `limit=108`. Ứng dụng lấy `buffer.array()` rồi ghi nguyên array vào `blob`.

**Câu hỏi:** Dữ liệu dự kiến là bao nhiêu byte? Ứng dụng có thể ghi nhầm bao nhiêu?

**Đáp án:** dữ liệu hợp lệ theo view là **8 byte**; ghi cả array có thể ghi **1024 byte** (kèm vùng không thuộc payload). Dùng `duplicate()`, `remaining()` và copy 8 byte.

### Bài 3 — Boolean null và false

Một lần request chưa chạy kiểm tra an ninh, nhưng hệ thống gán mặc định `passed=false`. Báo cáo sau đó thống kê “bao nhiêu request bị từ chối”.

**Câu hỏi:** Vì sao báo cáo sai? Chỉnh mô hình thế nào?

**Đáp án:** `false` đang gộp “chưa kiểm tra” vào “không đạt”. Có thể giữ `passed` thiếu giá trị khi chưa đánh giá, thêm `checked_at`, hoặc dùng cột `state` với giá trị `PENDING`, `PASSED`, `FAILED`.

### Bài 4 — Truy vấn theo địa chỉ IP

Ứng dụng lưu `client_ip inet` trong bảng phân vùng theo `tenant_id + request_day`. Người dùng yêu cầu lấy toàn bộ request của IP trong tháng.

**Câu hỏi:** Chỉ đổi `client_ip` thành `text` có giúp truy vấn nhanh hơn không?

**Đáp án:** không. Cần đường truy cập theo IP + bucket phù hợp, hoặc hệ chỉ mục/tìm kiếm có benchmark; phải lưu ý IP NAT/proxy có thể dẫn đến phân vùng nóng.

## 11. Checklist thiết kế blob, boolean và inet

- [ ] Nội dung là **byte nhị phân** thật sự hay chỉ là text/JSON cần lưu dưới dạng UTF-8?
- [ ] Blob đã có **giới hạn byte**, chính sách encoding/decoding và cân nhắc object storage cho file lớn?
- [ ] Dữ liệu Base64/hex ở API có được decode đúng thành byte trước khi bind?
- [ ] Java đã xử lý `ByteBuffer` bằng **remaining/duplicate**, tránh `array()` và mutation nguy hiểm?
- [ ] Với `boolean`, có phân biệt **true / false / chưa có kết quả**, không đồng nhất null với false?
- [ ] PATCH/UPDATE có phân biệt **UNSET/không gửi field** với **ghi null để xóa**?
- [ ] `inet` chỉ nhận IP literal? Hostname, port, URL và CIDR có được mô hình thành thông tin riêng?
- [ ] IP nguồn có được xác định dựa trên **trusted proxy** và chính sách IPv4/IPv6 thống nhất?
- [ ] Các truy vấn thực tế đã có partition key/clustering key tương ứng, bucket và kích thước partition an toàn?
- [ ] Retry ghi sự kiện có sử dụng lại **cùng primary key**, tránh sinh bản ghi trùng?
- [ ] Các Java getters/setters có đúng kiểu (`getByteBuffer`, `getBoolean`, `getInetAddress`) và kiểm tra null?
- [ ] Đã xem xét tombstone, TTL, compaction, repair và nhu cầu lưu giữ dữ liệu theo yêu cầu vận hành?

**Điểm cần nhớ:** `blob` giữ **byte gốc**, `boolean` giữ **kết quả đúng/sai**, `inet` giữ **địa chỉ IP có cấu trúc**. Đúng kiểu dữ liệu giúp tránh mất thông tin, còn **partition key, clustering key, chính sách retry và Java driver** quyết định dữ liệu đó có được ghi/đọc đúng và hiệu quả trong cluster Cassandra hay không.

