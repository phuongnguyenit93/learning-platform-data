# TypeCodec, generic type và cấu trúc collection/UDT

> **Chương:** Java driver cơ bản  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình wide-column. Java driver phải chuyển kiểu dữ liệu CQL sang Java đúng cách, đồng thời tôn trọng partition key, bảng thiết kế theo truy vấn, replication, consistency level, compaction, repair và hành vi xử lý lỗi.

## 1. Vì sao mapping kiểu dữ liệu là một phần của tính đúng đắn?

Một ứng dụng Java đọc một hàng Cassandra:

- Cột **tags** là **set<text>**.
- Cột **quantities** là **map<text, int>**.
- Cột **shipping_address** là một **UDT (User-Defined Type)**.
- Cột **created_at** là **timestamp**.

Nếu lập trình viên lấy tất cả dưới dạng chuỗi, tự phân tích nội dung bằng cách tách dấu phẩy, hoặc ép một **Map<String, Integer>** thành **Map<String, String>**, ứng dụng có thể gặp lỗi kiểu, mất thông tin hoặc ghi sai dữ liệu. Vấn đề rõ hơn với **collection lồng nhau**: do Java xóa thông tin kiểu generic lúc chạy (*type erasure*), riêng **Map.class** không mô tả được kiểu của key và value bên trong.

Java driver 4.x sử dụng **TypeCodec** để chuyển đổi giữa giá trị nhị phân theo CQL protocol và kiểu Java. Cơ chế **GenericType** mang theo kiểu Java có tham số như **List<String>**, **Set<UUID>** hay **Map<String, List<UUID>>** để driver chọn codec phù hợp.

Mục tiêu bài học:

1. Hiểu trách nhiệm của **TypeCodec**, **GenericType** và codec registry.
2. Đọc/ghi các kiểu CQL đơn giản và collection có kiểu an toàn.
3. Ánh xạ **UDT** từ CQL sang **UdtValue** rồi sang mô hình ứng dụng khi cần.
4. Xử lý collection lồng nhau, **frozen**, giá trị **null** và **UNSET** đúng ngữ nghĩa.
5. Biết khi nào nên tạo **custom codec**, cách đăng ký và kiểm thử.
6. Tránh dùng collection/UDT quá lớn, tránh lỗi đọc/ghi trong hệ Cassandra phân tán và Java service.

Ví dụ tập trung vào **API Java driver 4.x** với namespace **com.datastax.oss.driver.api**. Phiên bản dependency, hỗ trợ Java/JDK và cấu hình cluster cụ thể phải được đối chiếu với bản driver/server đang dùng.

## 2. Ba tầng: CQL type, Java type và codec

CQL là ngôn ngữ truy vấn của Cassandra. Một cột CQL có kiểu đã khai báo trong schema. Phía Java có nhiều kiểu có thể biểu diễn dữ liệu tương ứng; codec làm cầu nối.

~~~mermaid
flowchart LR
    A["CQL schema: map<text, int>"] --> B["TypeCodec"]
    B --> C["Java: Map<String, Integer>"]
    D["Binary value theo native protocol"] <--> B
    E["GenericType<Map<String, Integer>>"] --> B
    F["Codec registry của driver"] --> B
~~~

### 2.1. TypeCodec làm gì?

Một **TypeCodec<T>** mô tả ánh xạ giữa:

- **CQL DataType**, ví dụ **text**, **uuid**, **list<text>** hoặc **frozen<address>**.
- **Java GenericType<T>**, ví dụ **String**, **UUID**, **List<String>**.
- Cách **encode** Java value thành dạng byte để gửi qua native protocol.
- Cách **decode** byte nhận từ Cassandra thành Java value.
- Cách **parse/format** giá trị dạng CQL literal khi có nhu cầu.

Codec không thay đổi kiểu của cột trong database. Nếu schema là **map<text, int>** thì tạo custom codec **không biến cột thành JSON, BLOB hoặc một bảng quan hệ**; nó chỉ thay cách Java nhìn/ghi giá trị thuộc kiểu CQL đó.

### 2.2. GenericType làm gì?

Với **String.class**, Java đã có thông tin kiểu cơ bản. Nhưng **List<String>.class** không tồn tại: do type erasure, runtime class thường chỉ là **List.class**. **GenericType** là một *type token* giữ lại tham số generic.

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<String> textType = GenericType.of(String.class);

GenericType<List<String>> tagsType =
    new GenericType<List<String>>() {};

GenericType<Map<String, List<UUID>>> nestedType =
    new GenericType<Map<String, List<UUID>>>() {};
~~~

Các biểu thức **new GenericType<...>() {}** tạo anonymous subclass để giữ thông tin kiểu cụ thể. Cách này đặc biệt hữu ích khi cấu trúc có **nhiều tầng generic** hoặc cần chọn codec đúng trong một registry có nhiều lựa chọn.

### 2.3. Codec registry chọn codec như thế nào?

Khi thực thi câu lệnh prepared và gọi **set/get**, driver biết kiểu CQL của cột/biến bind từ metadata của statement hoặc row. Driver kết hợp **kiểu CQL** với **kiểu Java mong muốn** để tìm codec trong registry. Phần lớn kiểu phổ thông và collection có thể dùng codec mặc định; kiểu domain riêng có thể cần đăng ký codec mới.

~~~text
Cột CQL + kiểu Java được yêu cầu
              |
              v
       Codec registry
              |
      Có codec phù hợp?
          /         \
        Có           Không
        |              |
      Encode/       CodecNotFoundException
      decode        hoặc lỗi mapping tương ứng
~~~

**Không dựa vào việc ép kiểu sau khi đọc** để sửa thiếu codec. Một lỗi **CodecNotFoundException** thường báo rằng driver không tìm được đường chuyển đổi phù hợp giữa **DataType CQL** và **GenericType Java** được yêu cầu. Cần kiểm tra schema, kiểu Java và registry, không chỉ cast kết quả.

## 3. Mapping thông dụng giữa CQL và Java

| CQL | Java thường dùng trong driver 4.x | Ghi chú |
|---|---|---|
| **text, varchar, ascii** | **String** | Khác biệt về miền ký tự vẫn do kiểu CQL quy định |
| **boolean** | **Boolean** | Trường nullable nên dùng wrapper thay vì primitive khi cần phân biệt null |
| **tinyint, smallint, int, bigint** | **Byte, Short, Integer, Long** | Không giả định kiểu số luôn được widening tự động theo mong muốn |
| **float, double** | **Float, Double** | Lưu ý sai số số thực |
| **decimal** | **BigDecimal** | Phù hợp tiền tệ/giá trị thập phân với quy tắc làm tròn nghiệp vụ |
| **varint** | **BigInteger** | Không ép về Long nếu giá trị vượt phạm vi |
| **uuid, timeuuid** | **UUID** | Timeuuid có ngữ nghĩa thời gian riêng |
| **timestamp** | **Instant** | Timestamp lưu độ chính xác mili giây; thống nhất UTC khi sử dụng |
| **date** | **LocalDate** | Không có múi giờ/giờ trong giá trị date |
| **time** | **LocalTime** | Thời gian trong ngày, không có ngày |
| **blob** | **ByteBuffer** | Quản lý vị trí buffer khi đọc/ghi; không dùng cho object vô hạn |
| **list<text>** | **List<String>** | Collection có thứ tự |
| **set<uuid>** | **Set<UUID>** | Không xem là danh sách có thứ tự nghiệp vụ |
| **map<text, int>** | **Map<String, Integer>** | Cần cả kiểu key lẫn value |
| **UDT** | **UdtValue** | Có thể dùng custom codec để ánh xạ sang class domain |

Bảng trình bày các ánh xạ phổ biến, không phải toàn bộ các codec CQL/Java được hỗ trợ. Nếu cột có giá trị **null**, getter trả về reference null hoặc cần kiểm tra **row.isNull(...)** theo ngữ cảnh. Không tự chuyển null thành chuỗi **"null"** khi dữ liệu nghiệp vụ phân biệt hai trạng thái.

### 3.1. Đừng nhầm kiểu thời gian

- **timestamp** biểu diễn một thời điểm; Java thường dùng **Instant**, nên giữ cùng quy tắc UTC.
- **date** chỉ biểu diễn một ngày; Java dùng **LocalDate**, không tự gắn timezone vào ngày đó.
- **time** là giờ trong ngày; Java dùng **LocalTime**, không gắn ngày tùy tiện.
- Khi API Java dùng **Instant** độ chính xác nanosecond, ghi thành CQL timestamp có thể mất phần nhỏ hơn mili giây; cần biết yêu cầu chính xác của ứng dụng.

Ví dụ:

~~~java
import java.time.Instant;
import java.time.LocalDate;

Instant happenedAt = Instant.parse("2026-11-21T03:05:00Z");
LocalDate eventDay = LocalDate.of(2026, 11, 21);
~~~

**Định tuyến phân vùng không liên quan trực tiếp đến codec**, nhưng sai kiểu hoặc tính sai **event_day** có thể ghi sự kiện sang một partition khác, làm truy vấn theo khóa phân vùng không tìm thấy dữ liệu.

## 4. Schema ví dụ: collection và UDT trong một bảng wide-column

Để thực hành, xây bảng phục vụ truy vấn: **“lấy các đơn hàng mới nhất của một khách hàng trong một ngày”**. Dữ liệu tăng dài theo thời gian được chia bucket theo **ngày**, thay vì cho mọi đơn hàng vào một partition vô hạn.

~~~sql
-- Điều chỉnh dc1 và RF theo topology môi trường thử nghiệm.
-- Ví dụ RF = 3 cần đủ replica để kiểm thử LOCAL_QUORUM tương tự production.
CREATE KEYSPACE IF NOT EXISTS shop_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TYPE IF NOT EXISTS shop_lab.address (
    line1 text,
    city text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS shop_lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    tags set<text>,
    quantities map<text, int>,
    notes list<text>,
    shipping_address frozen<address>,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

### 4.1. Vai trò từng thành phần

- **(customer_id, order_day)** là **composite partition key**: driver có thể tính routing key/token khi bind đủ hai cột, giúp chọn coordinator thuận lợi nếu metadata/driver hỗ trợ.
- **created_at, order_id** là **clustering columns**: phân biệt và sắp thứ tự các row trong partition.
- **tags** là **set<text>** hữu hạn, ví dụ nhãn “priority” hoặc “mobile”.
- **quantities** là **map<text, int>**, ví dụ mã mặt hàng sang số lượng.
- **notes** là **list<text>**, chỉ phù hợp với số phần tử nhỏ, có giới hạn.
- **shipping_address** là **frozen<address>**: UDT được coi như một giá trị nguyên khối khi ghi/cập nhật.

**Không dùng UDT hoặc collection như một cách lưu mọi lịch sử của khách hàng**. Nếu dữ liệu tăng không giới hạn hoặc cần phân trang từng phần tử, nên biểu diễn thành các row với partition/clustering key phù hợp. Collection quá lớn làm mutation nặng, phát sinh tombstone khi cập nhật/xóa và gây chi phí compaction/repair.

### 4.2. Một hàng CQL để hình dung giá trị

~~~sql
INSERT INTO shop_lab.orders_by_customer_day (
    customer_id, order_day, created_at, order_id,
    tags, quantities, notes, shipping_address
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T03:05:00Z',
    22222222-2222-4222-8222-222222222222,
    {'priority', 'web'},
    {'sku-001': 2, 'sku-002': 1},
    ['paid', 'packed'],
    {line1: '123 Example St', city: 'Hanoi', postal_code: '100000'}
);
~~~

Dữ liệu chỉ là fixture. Địa chỉ, ID và chuỗi minh họa không phải dữ liệu cá nhân thật. Trong ứng dụng Java, ưu tiên **PreparedStatement + bind**, không nối các trường của người dùng vào chuỗi CQL.

## 5. Đọc/ghi collection bằng Java driver 4.x

Các API getter/setter tiện ích thường hỗ trợ **List, Set, Map** khi kiểu phần tử đơn giản.

### 5.1. Đọc collection

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import com.datastax.oss.driver.api.core.cql.Row;

void inspectRow(Row row) {
    Set<String> tags =
        row.getSet("tags", String.class);

    Map<String, Integer> quantities =
        row.getMap("quantities", String.class, Integer.class);

    List<String> notes =
        row.getList("notes", String.class);

    if (tags != null && tags.contains("priority")) {
        System.out.println("Order has priority tag");
    }

    if (quantities != null) {
        System.out.println("Number of distinct SKUs: " +
                           quantities.size());
    }
}
~~~

Phương thức **getSet/getMap/getList** xác định kiểu phần tử cho driver. Tránh dùng **row.getObject("tags")** rồi cast không kiểm soát nếu chương trình thật cần bảo đảm generic types. Với map sai kiểu value, ví dụ cố gọi **getMap("quantities", String.class, String.class)** cho **map<text,int>**, codec phù hợp có thể không tồn tại.

**Giá trị nhận về có thể là null** nếu cột unset ở CQL. Nếu nghiệp vụ muốn collection rỗng, hãy định nghĩa quy tắc chuyển đổi rõ ràng tại tầng service; **null** và **empty set/map/list** không nên bị trộn một cách vô thức.

### 5.2. Ghi collection với bound statement

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

BoundStatement bindCollections(PreparedStatement insert) {
    BoundStatement statement = insert.bind()
        .setSet("tags", Set.of("priority", "web"), String.class)
        .setMap("quantities",
                Map.of("sku-001", 2, "sku-002", 1),
                String.class, Integer.class)
        .setList("notes", List.of("paid", "packed"), String.class);

    return statement;
}
~~~

**Lưu ý:** đoạn này giả định prepared INSERT dùng **named bind markers** tương ứng **tags**, **quantities**, **notes**. Nếu statement chỉ dùng dấu **?**, driver 4.x có thể cho phép truy xuất bằng tên biến gắn với metadata cột trong nhiều trường hợp, nhưng tên có thể không duy nhất hoặc khó đoán khi câu lệnh phức tạp. Với ví dụ đầy đủ bên dưới, ta dùng **vị trí (index)** cho nhất quán.

Driver 4.x thiết kế các statement theo hướng **immutable**: các lời gọi **set...** trả lại một **BoundStatement mới**, cần **gán lại hoặc nối chuỗi**. Gọi setter mà bỏ qua giá trị trả về có thể khiến request được gửi với bind value cũ.

### 5.3. Điều chỉnh collection có thể tạo tombstone

Với collection không **frozen**, có thể cập nhật một phần tùy loại:

~~~sql
UPDATE shop_lab.orders_by_customer_day
SET quantities['sku-001'] = 3
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T03:05:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
~~~

Cập nhật/xóa phần tử có thể phát sinh cell/tombstone cần xử lý khi đọc và compaction. **Đặc biệt với list**, các thao tác sửa index hoặc prepend có tính chất và chi phí khác thêm phần tử nhỏ; đừng coi list như một hàng đợi vô hạn, đặc biệt khi nhiều client cập nhật đồng thời.

## 6. UDT: định nghĩa ở schema, dùng UdtValue trong Java

**UDT (User-Defined Type)** cho phép gom các trường có ý nghĩa thành một cấu trúc CQL có schema, ví dụ **address(line1, city, postal_code)**. UDT không phải JSON tự do: tên và kiểu field được quy định trong **CREATE TYPE**, có metadata trong keyspace.

### 6.1. Lấy metadata của UDT

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

UserDefinedType addressType = session.getMetadata()
    .getKeyspace(CqlIdentifier.fromCql("shop_lab"))
    .flatMap(ks -> ks.getUserDefinedType(
        CqlIdentifier.fromCql("address")))
    .orElseThrow(() ->
        new IllegalStateException("UDT shop_lab.address chưa tồn tại"));
~~~

Biến **session** là một **CqlSession** đã khởi tạo. Trước khi truy cập metadata, phải chắc chắn schema đã được tạo và được các node nhận biết (schema agreement). Nếu tạo UDT rồi ngay lập tức prepare/đọc metadata trong lúc schema chưa lan truyền, có thể gặp lỗi metadata hoặc prepare.

### 6.2. Tạo UdtValue và bind

~~~java
import com.datastax.oss.driver.api.core.data.UdtValue;

UdtValue address = addressType.newValue()
    .setString("line1", "123 Example St")
    .setString("city", "Hanoi")
    .setString("postal_code", "100000");

// Giả sử prepared statement có tham số shipping_address ở index 7.
BoundStatement statement = preparedInsert.bind()
    .setUdtValue(7, address);
~~~

**UdtValue** giữ các field theo kiểu của UDT. Thông thường bạn không cần tự serialize nó thành JSON rồi đưa vào cột **frozen<address>**: driver dùng codec UDT tương ứng để encode.

### 6.3. Đọc UdtValue và kiểm tra null

~~~java
UdtValue shipping = row.getUdtValue("shipping_address");

if (shipping != null) {
    String city = shipping.getString("city");
    String postalCode = shipping.getString("postal_code");
    System.out.println("Shipping city: " + city);
}
~~~

Trong ứng dụng thật, địa chỉ có thể là dữ liệu nhạy cảm; ví dụ in thành phố chỉ nhằm mô tả cách đọc field. Không ghi nguyên UdtValue, địa chỉ hoặc thông tin cá nhân vào log vận hành nếu không có nhu cầu và quyền hợp lệ.

### 6.4. Frozen UDT khác non-frozen UDT

| Cấu trúc | Ngữ nghĩa cần lưu ý | Khi phù hợp |
|---|---|---|
| **frozen<address>** | Được coi như **một giá trị** khi ghi/cập nhật; thường thay cả UDT | Một cấu trúc nhỏ gắn chặt với một row |
| **address** (non-frozen, nếu phiên bản hỗ trợ ngữ nghĩa cần dùng) | Có thể có cách cập nhật field riêng tùy cấu trúc/phiên bản | Khi cần thao tác field có chủ đích |
| **text JSON** | Không có typing UDT trong Cassandra; ứng dụng tự parse/validate | Chỉ khi nghiệp vụ thật sự cần dữ liệu phi cấu trúc và chấp nhận đánh đổi |

UDT không giải quyết vấn đề **partition lớn**: một row có UDT lớn, lặp lại trong nhiều hàng hoặc đổi thường xuyên vẫn tăng tải mutation, SSTable, compaction và repair.

## 7. GenericType với collection lồng nhau

Java generic type erasure khiến **Map.class** không nói được kiểu **String → List<UUID>**. Với cấu trúc lồng nhau, dùng **GenericType** mô tả chính xác kiểu đích.

CQL có thể biểu diễn một map chứa các list đã frozen:

~~~sql
-- Thực hành trên bảng riêng hoặc thêm cột trong môi trường lab.
CREATE TABLE IF NOT EXISTS shop_lab.events_by_group (
    tenant_id uuid,
    bucket_day date,
    group_name text,
    ids_by_kind map<text, frozen<list<uuid>>>,
    PRIMARY KEY ((tenant_id, bucket_day), group_name)
);
~~~

**frozen<list<uuid>>** ở vị trí giá trị map là cách biểu diễn phần tử collection lồng nhau như một giá trị; cú pháp được dùng phải phù hợp phiên bản Cassandra. Dữ liệu lồng nhau vẫn cần **giới hạn số phần tử và kích thước**.

### 7.1. Đọc bằng type token

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<Map<String, List<UUID>>> nestedType =
    new GenericType<Map<String, List<UUID>>>() {};

Map<String, List<UUID>> ids =
    row.get("ids_by_kind", nestedType);
~~~

Ở đây, GenericType giúp registry xác định không chỉ **Map** mà cả kiểu **key = String**, **value = List<UUID>**. Không nên cast thành **Map<String, List<String>>** hoặc dựa vào raw **Map**.

### 7.2. Bind nested value

~~~java
Map<String, List<UUID>> idsByKind = Map.of(
    "order", List.of(UUID.fromString(
        "22222222-2222-4222-8222-222222222222")));

BoundStatement bound = prepared.bind()
    .set(3, idsByKind, nestedType);
~~~

Ví dụ giả định bind index **3** là giá trị **ids_by_kind** và các index khác đã được gán đúng trước khi execute. **Index trong BoundStatement bắt đầu từ 0**; nếu schema hoặc vị trí tham số thay đổi, bind nhầm có thể gây type mismatch hoặc sai dữ liệu.

Trong ứng dụng thực tế, nên dùng prepared statement theo đúng primary key, và xây fixture test cho từng kiểu lồng nhau. Nếu không cần truy vấn từng phần của collection lồng nhau, một cấu trúc đơn giản hơn đôi khi dễ quản lý hơn.

## 8. Đoạn hoàn chỉnh: INSERT và SELECT với collection + UDT

Ví dụ Java Driver 4.x sau minh họa vòng đời: mở session, lấy UDT metadata, prepare statement, bind dữ liệu có kiểu, ghi và đọc lại. Dành cho **môi trường lab** đã tạo schema ở mục 4.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

public class OrderCollectionsUdtDemo {
    public static void main(String[] args) {
        UUID customerId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID orderId = UUID.fromString(
            "22222222-2222-4222-8222-222222222222");
        LocalDate orderDay = LocalDate.of(2026, 11, 21);
        Instant createdAt = Instant.parse("2026-11-21T03:05:00Z");

        // Đổi contact point, DC và bảo mật theo môi trường lab.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            UserDefinedType addressType = session.getMetadata()
                .getKeyspace(CqlIdentifier.fromCql("shop_lab"))
                .flatMap(k -> k.getUserDefinedType(
                    CqlIdentifier.fromCql("address")))
                .orElseThrow();

            UdtValue address = addressType.newValue()
                .setString("line1", "123 Example St")
                .setString("city", "Hanoi")
                .setString("postal_code", "100000");

            PreparedStatement insert = session.prepare(
                "INSERT INTO shop_lab.orders_by_customer_day " +
                "(customer_id, order_day, created_at, order_id, " +
                "tags, quantities, notes, shipping_address) " +
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind()
                .setUuid(0, customerId)
                .setLocalDate(1, orderDay)
                .setInstant(2, createdAt)
                .setUuid(3, orderId)
                .setSet(4, Set.of("priority", "web"), String.class)
                .setMap(5, Map.of("sku-001", 2),
                        String.class, Integer.class)
                .setList(6, List.of("paid"), String.class)
                .setUdtValue(7, address)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);

            PreparedStatement select = session.prepare(
                "SELECT tags, quantities, notes, shipping_address " +
                "FROM shop_lab.orders_by_customer_day " +
                "WHERE customer_id = ? AND order_day = ? " +
                "AND created_at = ? AND order_id = ?");

            Row row = session.execute(
                select.bind(customerId, orderDay, createdAt, orderId)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            if (row == null) {
                throw new IllegalStateException("Không tìm thấy order");
            }

            Set<String> tags = row.getSet("tags", String.class);
            Map<String, Integer> quantities =
                row.getMap("quantities", String.class, Integer.class);
            UdtValue actualAddress =
                row.getUdtValue("shipping_address");

            if (tags == null || !tags.contains("priority")
                    || quantities == null
                    || !Integer.valueOf(2)
                        .equals(quantities.get("sku-001"))
                    || actualAddress == null
                    || !"Hanoi".equals(
                        actualAddress.getString("city"))) {
                throw new IllegalStateException(
                    "Mapping collection/UDT không đúng fixture");
            }

            System.out.println(
                "PASS: mapped collection and UDT correctly");
        }
    }
}
~~~

### 8.1. Điều kiện chạy ví dụ

- **shop_lab**, **address** và bảng đã tồn tại và có schema agreement.
- Contact point phải trỏ vào Cassandra lab và **dc1** đúng tên datacenter.
- Với RF = 3 trong local DC, **LOCAL_QUORUM** cần đủ replica trả lời (thông thường 2/3); một node lab không đáp ứng cấu hình production này. Điều chỉnh RF/CL cho phòng lab và ghi rõ khác biệt.
- Java dùng **Set.of, Map.of, List.of** cần Java 9+; sử dụng dependency driver phù hợp JDK.
- Ví dụ không trình bày TLS/auth để tập trung vào TypeCodec. Hệ thống thật phải cấu hình xác thực và mã hóa kết nối, không tắt bảo mật để chạy ví dụ.
- **PreparedStatement** và **CqlSession** nên được cache/tái sử dụng trong ứng dụng dài hạn; ví dụ mở một session trong main để minh họa độc lập.
- Các UUID và địa chỉ là fixture; retry thực tế nên giữ nguyên orderId thay vì sinh ID mới mỗi lần thử.
- **.one()** trả null nếu không có row, vì vậy luôn kiểm tra tồn tại trước khi gọi getter.

## 9. Custom TypeCodec: khi kiểu Java là domain object

Driver đã có codec cho **String, UUID, Instant, collection, UdtValue** và nhiều kiểu cơ bản. Nếu ứng dụng muốn dùng kiểu Java riêng như **Priority** thay cho String, có thể tạo custom codec ánh xạ CQL **text** sang enum.

**Chỉ tạo custom codec khi mapping thực sự cần dùng rộng rãi.** Nếu chỉ chuyển UdtValue sang DTO ở một service, hàm mapper minh bạch có thể đơn giản và ít rủi ro hơn một codec có ảnh hưởng đến toàn session.

### 9.1. Ví dụ TypeCodec ánh xạ enum

~~~java
import java.nio.ByteBuffer;

import com.datastax.oss.driver.api.core.ProtocolVersion;
import com.datastax.oss.driver.api.core.type.DataType;
import com.datastax.oss.driver.api.core.type.DataTypes;
import com.datastax.oss.driver.api.core.type.codec.TypeCodec;
import com.datastax.oss.driver.api.core.type.codec.TypeCodecs;
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

enum Priority {
    NORMAL, URGENT
}

final class PriorityCodec implements TypeCodec<Priority> {
    private static final GenericType<Priority> JAVA_TYPE =
        GenericType.of(Priority.class);

    @Override
    public GenericType<Priority> getJavaType() {
        return JAVA_TYPE;
    }

    @Override
    public DataType getCqlType() {
        return DataTypes.TEXT;
    }

    @Override
    public ByteBuffer encode(
            Priority value, ProtocolVersion protocolVersion) {
        return TypeCodecs.TEXT.encode(
            value == null ? null : value.name(),
            protocolVersion);
    }

    @Override
    public Priority decode(
            ByteBuffer bytes, ProtocolVersion protocolVersion) {
        String name = TypeCodecs.TEXT.decode(bytes, protocolVersion);
        return name == null ? null : Priority.valueOf(name);
    }

    @Override
    public String format(Priority value) {
        return TypeCodecs.TEXT.format(
            value == null ? null : value.name());
    }

    @Override
    public Priority parse(String literal) {
        String name = TypeCodecs.TEXT.parse(literal);
        return name == null ? null : Priority.valueOf(name);
    }
}
~~~

Codec này **ủy quyền việc mã hóa/giải mã chuỗi và CQL literal** cho **TypeCodecs.TEXT** rồi chuyển String sang enum. Ưu điểm là dùng lại xử lý protocol/escaping từ codec mặc định thay vì tự chuyển charset, tạo ByteBuffer hay tự quote text. Tất cả enum values phải tương thích dữ liệu cũ; **Priority.valueOf** sẽ báo lỗi với giá trị không nhận biết như **"CRITICAL"** nếu enum chưa có phần tử tương ứng.

Một custom codec cho dữ liệu thật phải được kiểm tra với:

- **null**, chuỗi rỗng, Unicode và giá trị enum hợp lệ.
- Dữ liệu không hợp lệ hoặc enum value mới do service khác ghi.
- Các protocol versions được driver/server hỗ trợ.
- Không đột biến **ByteBuffer** đầu vào và không chia sẻ bộ đệm mutable sai cách.
- Encode/decode round-trip, format/parse round-trip, lỗi mapping rõ ràng.
- Tính thread-safe của codec vì session/driver sử dụng đồng thời.
- Tương thích ngược khi rolling deployment nhiều phiên bản ứng dụng.

### 9.2. Đăng ký codec với session

Trong các API builder driver 4.x hỗ trợ cấu hình codec:

~~~java
try (CqlSession session = CqlSession.builder()
        .addContactPoint(
            new java.net.InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc1")
        .addTypeCodecs(new PriorityCodec())
        .build()) {

    // Session sử dụng registry có PriorityCodec đã đăng ký.
    // Cần bảng/cột CQL text tương ứng để bind/get enum.
}
~~~

Việc đăng ký tại session ảnh hưởng chọn codec khi **cặp CQL DataType + Java GenericType** khớp. Cũng có thể có nhiều codec cùng CQL type nhưng Java type khác nhau, như String và Priority. Không tự tạo một codec cho cùng cặp kiểu rồi kỳ vọng driver luôn đoán đúng ý định khi giá trị null hoặc generic bị mất.

### 9.3. Sử dụng custom codec tường minh

Giả sử có cột **priority text** trong bảng thử nghiệm, có thể chọn Java type bằng GenericType:

~~~java
GenericType<Priority> priorityType =
    GenericType.of(Priority.class);

// prepared INSERT/UPDATE đã xác định đúng marker priority.
BoundStatement bound = prepared.bind()
    .set("priority", Priority.URGENT, priorityType);

// Row được đọc từ SELECT có cột priority kiểu text.
Priority value = row.get("priority", priorityType);
~~~

Đây là đoạn cắt rời để minh họa **type-driven codec selection**; cần câu lệnh prepared có marker tên phù hợp, bảng schema và các khóa partition được bind đầy đủ trước khi execute. Trong ứng dụng thật, với một trường chỉ lưu ở một nơi, cân nhắc **row.getString** rồi parse ở lớp domain như một giải pháp đơn giản hơn.

## 10. TypeCodec cho UDT: lựa chọn giữa mapper và custom codec

Bạn có hai cách tiêu biểu để đưa **address UDT** vào domain model Java.

### 10.1. Mapper rõ ràng ở tầng service

Ví dụ class domain đơn giản:

~~~java
record Address(String line1, String city, String postalCode) {}

static Address toAddress(UdtValue value) {
    if (value == null) {
        return null;
    }
    return new Address(
        value.getString("line1"),
        value.getString("city"),
        value.getString("postal_code"));
}

static UdtValue toUdt(
        Address address, UserDefinedType type) {
    if (address == null) {
        return null;
    }
    return type.newValue()
        .setString("line1", address.line1())
        .setString("city", address.city())
        .setString("postal_code", address.postalCode());
}
~~~

**record** yêu cầu Java hỗ trợ records (Java 16+). Trên JDK khác, có thể dùng một immutable class. Đoạn này giả định import **UdtValue** và **UserDefinedType** như mục 6.

Ưu điểm:

- Dễ kiểm thử độc lập và chủ động xử lý field thiếu/null.
- Không can thiệp codec registry.
- Có thể gắn validation nghiệp vụ như độ dài địa chỉ hoặc mã bưu chính.

Nhược điểm: phải gọi mapper ở nơi đọc/ghi, cần tránh trùng lặp nếu nhiều service dùng cùng cấu trúc.

### 10.2. Custom codec UDT cho kiểu domain

Có thể viết codec chuyển **UdtValue ↔ Address** bằng cơ chế codec chuyên biệt hoặc ủy quyền cho codec UDT gốc, tùy API driver. Khi đó cần lấy **UserDefinedType metadata** gắn với keyspace/schema thích hợp, đăng ký codec đúng CQL type và Java GenericType, sau đó dùng **row.get(..., GenericType.of(Address.class))** hoặc setter tương đương.

Với custom UDT codec, lưu ý:

1. **Schema evolution:** thêm/bớt/đổi tên field làm thay đổi mapping. Một codec cứng nhắc có thể lỗi khi node mixed-version hoặc schema mới vừa được áp dụng.
2. **UDT identifier:** cùng tên UDT ở hai keyspace có thể có định nghĩa khác nhau. Không coi mọi UDT tên **address** đều tương đương.
3. **Frozen/non-frozen:** giải quyết ngữ nghĩa cập nhật toàn giá trị hay field ở tầng CQL, không chỉ codec.
4. **Null fields:** UDT có thể có field null; domain model cần quy tắc rõ.
5. **Thread safety:** codec chia sẻ giữa nhiều request, không giữ state tạm cho mỗi request vào instance dùng chung.
6. **Tương thích server/driver:** codec không thay đổi giao thức hay biến schema incompatible thành compatible.

Với người mới, **UdtValue + mapper rõ ràng** thường là điểm bắt đầu tốt. Chỉ nâng lên custom codec khi có lý do đo được và đã xây test round-trip/schema evolution.

## 11. Null, UNSET, empty collection và tác động lên dữ liệu

Bốn trạng thái thường bị lẫn:

| Biểu diễn | Ý nghĩa phổ biến | Điều cần cẩn trọng |
|---|---|---|
| **null** | Không có giá trị; khi ghi theo ngữ nghĩa CQL có thể tạo **tombstone** | Không dùng làm “giữ nguyên” nếu muốn bỏ qua cập nhật |
| **UNSET** trong bind | Với statement có hỗ trợ, marker đó không cập nhật cột tương ứng | Không dùng cho primary key hoặc vị trí server cấm UNSET |
| **Collection rỗng** | Giá trị collection không có phần tử theo ngữ nghĩa kiểu | Khác với một collection có dữ liệu; ngữ nghĩa lưu/đọc chi tiết tùy frozen/non-frozen |
| **Collection null** | Cột không có giá trị | Không tự coi là empty collection nếu nghiệp vụ cần phân biệt |

Java driver hỗ trợ thao tác **setToNull** và **unset** trên các loại statement phù hợp. Ví dụ minh họa một **UPDATE** có named marker:

~~~java
BoundStatement keepTags = preparedUpdate.bind()
    .unset("tags");

BoundStatement clearTags = preparedUpdate.bind()
    .setToNull("tags");
~~~

Hai statement này **không tương đương**: UNSET thường yêu cầu server bỏ qua marker để không thay đổi cột; null có thể là thao tác xóa. Cú pháp và vị trí UNSET hợp lệ phụ thuộc loại CQL statement và phiên bản; phải test với bảng lab trước khi áp dụng.

Một điểm an toàn quan trọng: **BoundStatement immutable**. Nếu viết:

~~~java
BoundStatement original = preparedUpdate.bind();
original.setToNull("tags");  // Bỏ qua giá trị trả về: không cập nhật original!
~~~

Lệnh execute original có thể vẫn giữ marker chưa được bind. Cần viết:

~~~java
BoundStatement corrected =
    original.setToNull("tags");
~~~

Khi xử lý API PATCH từ ứng dụng Java, hãy quy định riêng ba ý nghĩa: **không cung cấp field (không đổi)**, **cung cấp null (xóa)**, **cung cấp giá trị rỗng (giá trị hợp lệ nhưng rỗng)**. Trộn chúng có thể gây xóa dữ liệu và tạo tombstone ngoài ý muốn.

## 12. Những lỗi hay gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| **CodecNotFoundException** | Kiểu CQL không khớp kiểu Java yêu cầu, thiếu custom codec | Xem schema, GenericType, cột/marker và codec registry |
| **ClassCastException** | Cast raw collection hoặc dùng generic không đúng | Dùng getter có kiểu hoặc GenericType chính xác |
| **InvalidTypeException** hoặc lỗi khi bind | Marker nhận kiểu khác schema, field UDT sai tên/kiểu | So metadata của PreparedStatement và CREATE TABLE/TYPE |
| **NullPointerException** sau getUdtValue | Cột UDT null hoặc row không tồn tại | Kiểm tra row == null, row.isNull và UdtValue == null |
| Kết quả **timestamp** sai mốc | Nhầm UTC/timezone hoặc kỳ vọng nano precision | Dùng Instant, fixture ranh giới ngày/giờ, kiểm tra millis |
| Bản ghi không tìm thấy | Tính sai composite partition key hoặc bucket | Đối chiếu customer_id + order_day, routing key và giá trị bind |
| Cập nhật thiếu field | Bỏ qua statement mới trả về bởi setter | Gán lại BoundStatement sau mỗi set/unset |
| **UDT codec** lỗi sau schema migration | Field/UDT metadata thay đổi, cache/driver chưa cập nhật | Kiểm tra schema agreement, type identifiers và mapping |
| Memory/latency tăng vì collection | Collection hoặc mutation quá lớn, cập nhật/xóa lặp lại | Giới hạn phần tử, đo partition size/tombstones, thiết kế row |
| Log xuất dữ liệu nhạy cảm | Log UdtValue/BoundStatement, payload hoặc full query | Redact tại nguồn, log query shape, không log PII |

### 12.1. Quy trình xử lý CodecNotFoundException

1. **Ghi chính xác kiểu CQL** của cột hoặc bind marker: ví dụ **map<text, int>**.
2. **Ghi kiểu Java mà code yêu cầu**: ví dụ **Map<String, String>**, sai với cột trên.
3. Kiểm tra **đã dùng đúng getter/setter**, đặc biệt với generic lồng nhau.
4. Nếu là class domain riêng, kiểm tra **codec đã đăng ký trong đúng CqlSession**, đúng DataType và GenericType.
5. Kiểm tra **schema agreement** nếu lỗi xuất hiện sau CREATE/ALTER TYPE hoặc rolling upgrade.
6. Thêm test chuyển đổi **round-trip** trên schema thực và dữ liệu biên.

Không nên chữa lỗi bằng cách ép toàn bộ thành **text** hoặc sử dụng **ALLOW FILTERING**. Một vấn đề mapping kiểu không liên quan đến việc phải quét nhiều partition.

### 12.2. Chuẩn bị log đủ chẩn đoán mà không lộ dữ liệu

Đối với lỗi codec, có thể ghi **operation name**, keyspace/table, **tên và kiểu cột**, kiểu Java mong muốn, codec class, version driver/server và exception class. Tránh ghi thẳng password, địa chỉ khách hàng, token, collection giá trị thật hoặc UDT của người dùng vào log.

## 13. TypeCodec có liên quan gì đến replication, consistency và performance?

TypeCodec chạy chủ yếu ở **ranh giới client/protocol**: nó chuyển dữ liệu giữa Java và CQL. Sau khi encode, request vẫn được Cassandra định tuyến theo **partition key**; coordinator chọn replica theo topology, replication strategy và CL của request.

~~~mermaid
flowchart LR
    A["Domain Java + GenericType"] --> B["TypeCodec encode"]
    B --> C["BoundStatement + partition key"]
    C --> D["Coordinator và token-aware routing"]
    D --> E["Replica theo RF + CL"]
    E --> F["Commitlog / memtable / SSTable"]
    F --> G["Compaction / repair"]
    G --> H["Đọc trả dữ liệu → TypeCodec decode"]
~~~

Các hệ quả:

- **Codec đúng không cứu được query thiếu partition key.** Cần thiết kế bảng theo access pattern để truy vấn biết partition nào cần đọc.
- **Codec không thay đổi consistency level.** Ghi **LOCAL_QUORUM** có yêu cầu phản hồi replica khác **ONE**, nhưng kiểu dữ liệu trả về Java vẫn theo codec.
- **Codec không bỏ giới hạn mutation/batch/partition.** Map/UDT quá lớn gây buffer, network và I/O pressure dù encode chính xác.
- **Codec không thay thế repair.** Repair đồng bộ replica; ứng dụng phải bảo đảm nó không ghi sai kiểu, sai partition hoặc sai TTL ngay từ đầu.
- **Driver retry có thể gửi lại request.** Khi update collection hoặc tạo row, cần nghĩ về idempotency; dùng orderId/eventId ổn định và tránh logic “tạo UUID mới mỗi lần retry”.
- **Custom codec tốn CPU/GC.** Mapping tạm quá nhiều String/ByteBuffer hoặc copy collection sâu trong mỗi request có thể làm latency tăng. Đo allocation, p95/p99 và số request đồng thời trước khi tối ưu.

### 13.1. Chiến lược collection phù hợp mô hình wide-column

Một collection **tags set<text>** có vài nhãn là hợp lý. Ngược lại, hàng chục nghìn event IDs lồng trong một map theo khách hàng sẽ tăng không giới hạn. Cách khác:

~~~sql
CREATE TABLE IF NOT EXISTS shop_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    category text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

Mỗi sự kiện là một row, phân trang theo clustering key; vẫn cần kiểm soát kích thước partition theo ngày và tốc độ của tenant nóng. Khi đọc nhiều ngày, ứng dụng phải truy vấn nhiều bucket và hợp nhất kết quả có kiểm soát.

## 14. Kiểm thử đúng kiểu dữ liệu, không chỉ kiểm tra kết nối

Bộ test cho TypeCodec/GenericType nên gồm ba cấp:

### Cấp A — Unit test codec/mapping

- Java → encode → decode → Java cho giá trị bình thường.
- Null, empty, Unicode, ký tự đặc biệt, số nguyên min/max, BigDecimal scale và precision thời gian.
- Collection rỗng, collection lớn đến giới hạn ứng dụng, nested generics.
- UDT có field null, field thêm/bớt theo schema migration mô phỏng.
- Dữ liệu enum lạ, value không hợp lệ; exception rõ ràng và không rò rỉ thông tin.
- Đa luồng dùng chung codec (nếu đăng ký một instance trong session).

### Cấp B — Integration test Cassandra lab

- Tạo schema CQL và UDT, đợi schema agreement.
- Prepared INSERT/SELECT với đủ composite partition key và clustering columns.
- Bind/get list/set/map/UDT, kiểm tra **đúng kiểu và giá trị**, không chỉ không có exception.
- Thử **setToNull** và **unset** trên UPDATE phù hợp, kiểm tra ngữ nghĩa dữ liệu.
- Kiểm tra các row có TTL/DELETE và collection updates để không hiểu sai tombstone.
- Thử codec với keyspace/UDT khác tên hoặc schema khác để phát hiện giả định sai.

### Cấp C — Load, rolling upgrade và lỗi phân tán

- Đo p95/p99, allocation rate, GC, CPU driver khi serialize collection/UDT dưới tải.
- Thử page size/concurrency/backpressure với truy vấn trả nhiều row.
- Thử timeout/retry trên một số replica, giữ idempotent event ID.
- Kiểm thử driver/server compatibility, TLS/auth, schema agreement khi ALTER TYPE.
- Theo dõi compaction, repair và kích thước partition khi collection bị cập nhật thường xuyên.
- Xác minh thao tác backup/restore đúng schema UDT, vì snapshot tệp không tự diễn tả hết mục đích của domain mapper Java.

## 15. Bài tập thực hành

### Bài 1 — Chọn đúng Java type

Cho schema:

~~~sql
CREATE TABLE shop_lab.codec_exercise (
    id uuid PRIMARY KEY,
    labels set<text>,
    scores map<text, int>,
    dates list<date>
);
~~~

Hãy viết kiểu Java phù hợp cho ba cột.

**Đáp án gợi ý:** **Set<String>**, **Map<String, Integer>**, **List<LocalDate>**. Không dùng raw Map, và với dates nên dùng LocalDate vì CQL date không có thời gian.

### Bài 2 — GenericType vì sao cần thiết?

Một cột được khai báo **map<text, frozen<list<uuid>>>**. Một lập trình viên dùng **Map.class**, rồi ép về **Map<String, List<UUID>>**.

**Câu hỏi:** Vấn đề với việc mất generic type là gì? Cách đọc nên dùng?

**Đáp án gợi ý:**

~~~java
GenericType<Map<String, List<UUID>>> type =
    new GenericType<Map<String, List<UUID>>>() {};
Map<String, List<UUID>> result =
    row.get("ids_by_kind", type);
~~~

Codec registry cần kiểu đầy đủ; cast raw Map không kiểm tra được kiểu sâu lúc biên dịch và có thể lỗi khi xử lý các phần tử.

### Bài 3 — UDT có giá trị null

Bảng có **shipping_address frozen<address>**, một row không có địa chỉ. Code gọi:

~~~java
String city = row.getUdtValue("shipping_address")
                 .getString("city");
~~~

**Câu hỏi:** Lỗi gì có thể xảy ra? Sửa thế nào?

**Đáp án gợi ý:** **NullPointerException** khi UdtValue null. Kiểm tra row tồn tại và giá trị UDT trước khi truy cập field; phân biệt “chưa có địa chỉ” với chuỗi thành phố rỗng.

### Bài 4 — BoundStatement immutable

~~~java
BoundStatement b = update.bind();
b.setSet("tags", Set.of("vip"), String.class);
session.execute(b);
~~~

**Câu hỏi:** Tại sao request có thể chưa bind tags?

**Đáp án gợi ý:** Setter trả một statement mới; code bỏ qua giá trị trả về. Dùng **b = b.setSet(...)** hoặc nối chuỗi trước execute.

### Bài 5 — Custom enum codec gặp dữ liệu mới

Có custom codec ánh xạ **text** sang enum **NORMAL, URGENT** bằng **Priority.valueOf**. Một service khác ghi chuỗi **CRITICAL**.

**Câu hỏi:** Điều gì xảy ra? Nên thiết kế thay đổi tương thích ra sao?

**Đáp án gợi ý:** Decode có thể báo lỗi vì enum value không tồn tại. Khi triển khai nhiều phiên bản, phải có chiến lược unknown values, giai đoạn cập nhật reader trước writer, test dữ liệu phiên bản cũ/mới và quản lý codec registry.

### Bài 6 — Collection lớn có liên quan TypeCodec không?

Ứng dụng encode thành công một **map<text, text>** chứa 100.000 phần tử rồi ghi trong một row mỗi khách hàng.

**Câu hỏi:** Codec đúng có bảo đảm query và node khỏe không?

**Đáp án gợi ý:** Không. Mutation, collection và partition có thể quá lớn, tạo áp lực CPU/network/RAM và nhiều tombstone khi cập nhật; nên giới hạn dữ liệu, chuyển lịch sử thành row theo partition/bucket và đo compaction/repair.

### Bài 7 — Sai bucket làm mất dữ liệu “ảo”

Java service ghi **order_day** theo UTC, nhưng API đọc dùng LocalDate theo múi giờ địa phương. Sự kiện lúc 23:30 UTC bị truy vấn bằng ngày hôm sau.

**Câu hỏi:** Vấn đề có phải TypeCodec không?

**Đáp án gợi ý:** TypeCodec có thể hoạt động đúng; lỗi là **quy tắc tính partition key** không thống nhất. Cần dùng cùng quy tắc ngày/bucket tại write/read và test các thời điểm ranh giới.

## 16. Checklist khi đưa mapping vào ứng dụng Java

- [ ] Schema CQL và Java mapping được review cùng nhau, kể cả **UDT và nested collection**.
- [ ] Có type token **GenericType** cho generic phức tạp; không dùng raw cast làm giải pháp mặc định.
- [ ] Dùng getter/setter có kiểu như **getMap/setMap, getList/setList, getUdtValue/setUdtValue**.
- [ ] Prepared statement được bind đúng partition key, đúng thứ tự/marker và có routing metadata phù hợp.
- [ ] **BoundStatement immutable** được xử lý đúng: lưu giá trị trả về của setter.
- [ ] Đã định nghĩa rõ ngữ nghĩa **null, UNSET và empty collection**.
- [ ] UDT được lấy từ metadata đúng keyspace, xác minh schema agreement và xử lý null fields.
- [ ] Custom TypeCodec có encode/decode/parse/format, kiểm thử protocol và giá trị lỗi.
- [ ] Không có logging raw UdtValue, secret hoặc payload nhạy cảm.
- [ ] Collection/UDT nhỏ, có giới hạn; dữ liệu phát triển vô hạn là nhiều row theo access pattern.
- [ ] Có fixture test theo partition key, phân phối token, TTL/DELETE và dữ liệu kiểu ngày/giờ.
- [ ] Đã kiểm thử consistency level, retry/idempotency, driver/server compatibility và hiệu năng dưới tải.
- [ ] Backup, compaction và repair được tính trong vận hành nếu cấu trúc dữ liệu thay đổi.

## 17. Tổng kết

**TypeCodec** giải quyết chuyển đổi **CQL DataType ↔ Java value**, còn **GenericType** cho driver biết chính xác kiểu Java, kể cả tham số lồng nhau mà Java type erasure không giữ bằng class token thông thường. **Collection** phù hợp với tập giá trị nhỏ của một hàng; **UDT** mô tả một cấu trúc có schema, được truy cập bằng **UdtValue** hoặc ánh xạ sang domain object bằng mapper/custom codec.

Trong Cassandra, mapping đúng chỉ là một phần của tính đúng đắn. Partition key phải được bind nhất quán, bảng cần thiết kế theo truy vấn, consistency level phải phù hợp replication, và collection/UDT không nên biến thành payload quá lớn làm nặng mutation, compaction hay repair. Với Java driver, lựa chọn an toàn là **prepared/bind có kiểu, kiểm tra null/UNSET, giới hạn dữ liệu, kiểm thử round-trip và kiểm chứng hành vi phân tán** trước khi đưa vào production.
