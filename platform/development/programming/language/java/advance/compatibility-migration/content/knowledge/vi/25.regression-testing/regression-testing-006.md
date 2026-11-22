# Kiểm thử dữ liệu đã lưu từ phiên bản trước

Khi nâng JDK, framework hoặc thư viện trong **Java Advance Compatibility Migration**, phần lớn nhóm phát triển tập trung vào việc code mới có biên dịch, test và khởi động được không. Nhưng dữ liệu của hệ thống **không bắt đầu lại từ đầu** sau khi triển khai: database vẫn chứa bản ghi từ nhiều năm trước; cache có thể giữ giá trị do binary cũ tạo; message broker còn event đang chờ; object storage lưu file/JSON/XML; session và job checkpoints có thể tồn tại qua một lần rollout.

Một phiên bản mới có thể ghi và đọc dữ liệu **do chính nó tạo ra** rất tốt, nhưng không đọc được dữ liệu đã lưu bởi phiên bản trước. Ví dụ, đổi serializer hoặc tên Java class khiến một serialized object không còn khôi phục được; nâng ORM làm entity mapping không tương thích với một trạng thái cũ; chuyển từ `javax.*` sang `jakarta.*` làm annotation/provider khác; thay charset/timezone/định dạng ngày giờ có thể làm giá trị giải mã bị lệch dù chương trình không ném exception.

Bài **Kiểm thử dữ liệu đã lưu từ phiên bản trước** thuộc chương **Kiểm thử hồi quy**. Trọng tâm là xây bộ **legacy data fixtures** (mẫu dữ liệu có nguồn gốc từ bản cũ), định nghĩa **hợp đồng đọc và ý nghĩa dữ liệu**, kiểm tra phiên bản mới trên snapshot thực tế đã làm sạch thông tin nhạy cảm, và thử cả các chiều tương thích cần cho rolling deployment hoặc rollback.

Mục tiêu không phải “đọc được mọi byte bằng mọi phiên bản”, mà là trả lời được câu hỏi có kiểm chứng: **dữ liệu nào được cam kết hỗ trợ, bằng cách nào nó được đọc/diễn giải, trong thời gian nào và bằng bằng chứng gì trước khi rollout?**

## 1. Vì sao lưu dữ liệu làm migration khó hơn compile?

Một test chỉ chạy với dữ liệu mới thường có vòng đời:

~~~text
Phiên bản mới -> Ghi dữ liệu mới -> Đọc bằng phiên bản mới -> PASS
~~~

Nhưng thực tế khi nâng hệ thống:

~~~text
Phiên bản cũ --ghi nhiều tháng/năm--> Dữ liệu tồn tại lâu dài
                                             |
                                             v
                                      Phiên bản mới đọc
                                             |
                                      +------+------+
                                      |             |
                                  Diễn giải đúng  Thất bại/sai âm thầm
~~~

Chỉ thay đổi library/JDK cũng có thể tác động:
- Cách mã hóa/giải mã JSON, XML, CSV, Java serialization, Avro, Protobuf.
- Tên class đầy đủ, `serialVersionUID`, field types hoặc constructor khi deserialize.
- Entity mappings, identifier/sequence, Hibernate dialect và behavior của JDBC driver.
- Cách xử lý `null`, missing field, default value và unknown enum.
- Timestamp/timezone, decimal precision, encoding và normalization.
- Binary schemas, compressed formats, encryption metadata và key rotation.
- Classloader, module access và runtime provider discovery.
- Java EE/Jakarta namespace hoặc JPA/JAXB/Validation implementation.
- Consumer compatibility khi hai bản ứng dụng cùng chạy hoặc phải rollback.

**Không phải mọi điểm trên đều là lỗi JDK.** Nhiều lỗi do framework/serializer/ORM đổi theo đợt migration; cần ghi phiên bản của tất cả thành phần để phân biệt nguyên nhân.

## 2. Xác định “dữ liệu đã lưu” gồm những gì

Dữ liệu tồn tại ở nhiều lớp hơn bảng database.

| Nơi lưu | Ví dụ | Vấn đề dễ xảy ra |
|---|---|---|
| Database quan hệ | Bảng orders, invoices, audit logs | Schema/column type, defaults, ORM mapping |
| Document database | JSON/BSON documents | Missing/unknown fields, polymorphic types |
| Object storage | JSON/XML/CSV/Parquet, file đính kèm | Charset, parser, format version |
| Cache | Redis keys, serialized objects | Serializer/class name và TTL |
| Message broker | Kafka topic, JMS queue, DLQ | Event/schema version, replay, consumer |
| Session store | HTTP sessions, distributed session | Java serialization, class identity |
| Search index | Documents/index metadata | Analyzer, mapping, reindex requirement |
| Job checkpoint | Cursor, offset, batch state | Resume không bỏ sót/lặp xử lý |
| Local files | Config snapshots, CSV exports | Default charset, line endings, date |
| Backup/archive | DB dumps, migration snapshots | Khả năng khôi phục bằng runtime mới |
| External partner payload | File/batch/event được gửi từ trước | Backward wire compatibility |

Mỗi nguồn có **retention khác nhau**. Một API có thể chỉ cần đọc event 7 ngày gần đây nhưng báo cáo thuế cần đọc hồ sơ cũ nhiều năm. Không đặt tất cả vào cùng một “hết hạn tương thích” nếu hợp đồng lưu trữ khác nhau.

### 2.1. Inventory theo producer, reader và format

Một bảng kiểm kê gợi ý:

| Dataset/artifact | Ai từng ghi | Ai sẽ đọc | Format/schema | Retention | Trường hợp quan trọng |
|---|---|---|---|---|---|
| `orders` DB | Service v1, Hibernate cũ | Service v2 | SQL schema v1–v3 | Nhiều năm | Giá, status, thời điểm |
| `order-events` | Producer v1 | Consumer v1/v2 | JSON v1, Avro v2 | Theo topic policy | Replay, duplicate |
| `user-session` Redis | Web v1 | Web v2 | Serialized session | Vài giờ/ngày | Login/session continuity |
| Object-store invoices | Batch v1 | Reporting v2 | CSV/XML | Theo pháp lý | Charset, decimal |
| Batch checkpoint | Worker v1 | Worker v2 | JSON/properties | Đến khi job xong | Resume/idempotency |

Cần ghi **producer version thực**, không chỉ tên công cụ. Dữ liệu có thể đã được tạo bởi nhiều release với cùng một schema name nhưng mapping khác nhau.

## 3. Định nghĩa hợp đồng tương thích cần kiểm thử

Từ “backward compatible” có thể được hiểu theo nhiều nghĩa. Với dữ liệu lưu trữ, nên định nghĩa theo **chiều đọc/ghi**.

| Tình huống | Câu hỏi | Ý nghĩa |
|---|---|---|
| **New reader / old data** | V2 đọc và hiểu dữ liệu do V1 tạo? | Đường chính của bài học |
| Old reader / new data | V1 đọc được dữ liệu do V2 tạo? | Quan trọng khi rollback/rolling deployment |
| New writer / old reader | V2 có tạo payload mà consumer cũ hiểu? | Cần khi producer và consumer nâng độc lập |
| New reader / mixed data | V2 đọc được bản ghi từ nhiều generation? | Cần cho data store tồn tại lâu |
| Rewritten old data / new reader | Sau backfill, V2 đọc đúng không? | Cần cho migration dữ liệu |
| Rewritten data / rollback | Khi rollback, V1 còn đọc được không? | Quyết định rollback có an toàn |
| Replay old event | V2 xử lý event cũ và giữ idempotency? | DLQ, event sourcing, recovery |

**Tương thích đọc ngược** không mặc nhiên bao gồm **tương thích ghi ngược**. Một bản mới có thể hiểu các field cũ nhưng ngay sau khi ghi lại bản ghi, bản cũ không còn đọc được.

### 3.1. Lập ma trận producer-reader

Ví dụ nếu tồn tại V1, V2 và V3:

| Dữ liệu được tạo bởi | Reader V1 | Reader V2 | Reader V3 |
|---|---|---|---|
| Writer V1 | Baseline | **Bắt buộc PASS** | **Bắt buộc PASS** nếu còn retention |
| Writer V2 | PASS khi cần rollback | Baseline V2 | **Bắt buộc PASS** |
| Writer V3 | Thường không bắt buộc nếu đã bỏ V1; xem contract | PASS khi rollback V2 | Baseline V3 |

Không nhất thiết mọi ô đều PASS; **phải định nghĩa ô nào là hợp đồng**. Nếu có một ranh giới forward-only, công bố rõ release nào bắt đầu không rollback được và dữ liệu nào cần backup/transform.

## 4. Quy tắc quan trọng: dữ liệu mẫu phải đến từ phiên bản cũ

Một bài test như sau không đủ:

~~~java
// Sai mục tiêu: V2 vừa ghi vừa đọc cùng format của chính nó.
byte[] bytes = new V2Serializer().write(new Order("ord-1"));
Order result = new V2Serializer().read(bytes);
assertEquals("ord-1", result.id());
~~~

Nó chỉ kiểm tra round-trip của V2, **không có bằng chứng V2 đọc được bytes của V1**.

Cách đúng:

~~~text
Ứng dụng/serializer V1 đã pin
           |
           v
Tạo legacy fixture bằng dữ liệu test có kiểm soát
           |
           v
Lưu bytes/file/DB snapshot + checksum + producer metadata
           |
           v
Ứng dụng V2 chỉ đọc (hoặc migrate bản copy) fixture đó
           |
           v
Assert giá trị nghiệp vụ + invariants + lỗi/edge cases
~~~

### 4.1. Nguồn fixture đáng tin

Có thể lấy từ:
1. **Bản release cũ thực sự**: dùng test harness V1 ghi JSON/CSV/binary/DB rows với synthetic data.
2. **Snapshot staging đã được xây trên schema cũ**: giữ nguyên định dạng và metadata.
3. **Bản sao dữ liệu production được ẩn danh và kiểm soát**: chỉ khi policy cho phép, tạo subset có tính đại diện, không đưa PII vào Git.
4. **Event lịch sử đã được sanitize**: giữ schema headers và keys quan trọng, không làm sai encoding.
5. **Các edge cases cố định** từng gây lỗi: null, unknown enum, timestamp DST, record thiếu field.
6. **Database dump đã pin version**: restore vào môi trường test cách ly.

Mọi fixture cần metadata:
- Producer application commit/release và JDK vendor/build.
- Serializer/ORM/library version nếu ảnh hưởng format.
- Schema version (nếu có).
- Cách tạo và loại dữ liệu synthetic/sanitized.
- Hash/checksum và định dạng file.
- Expected business interpretation.
- Retention/support policy của dataset đó.

### 4.2. Không “cập nhật snapshot” bằng code mới một cách tự động

Khi một golden test thất bại, tránh chạy lệnh regenerate fixtures bằng V2 rồi commit ngay. Việc này có thể biến **regression thật** thành test xanh vì expected data đã bị sửa theo implementation mới.

Nếu contract được thay đổi có chủ đích:
- Giữ fixture lịch sử để kiểm các reader còn phải hỗ trợ.
- Ghi decision/ticket thay contract.
- Thêm fixture/schema version mới.
- Cập nhật expected semantics qua review độc lập với writer implementation.
- Chỉ loại fixture cũ khi hết support window và có quyết định rõ.

## 5. Cấu trúc bộ fixtures trong repository

Ví dụ bố trí:

~~~text
src/test/resources/
  legacy-data/
    README.md
    manifest.json
    json/
      v1-order-basic.json
      v1-order-missing-optional.json
      v1-order-unknown-field.json
      v1-order-unicode.json
    xml/
      v1-invoice.xml
    binary/
      v1-order.ser
    events/
      v1-order-created.json
      v1-order-cancelled.json
    sql/
      schema-v1.sql
      dataset-v1.sql
~~~

Ví dụ `manifest.json`:

~~~json
{
  "fixtureSet": "orders-legacy-2026-11",
  "producer": {
    "appVersion": "1.12.4",
    "jdk": "17",
    "serializer": "jackson-legacy-release",
    "schemaVersion": 1
  },
  "origin": "synthetic-data-generated-by-v1",
  "fixtures": [
    {
      "path": "json/v1-order-basic.json",
      "case": "basic-paid-order",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256"
    },
    {
      "path": "binary/v1-order.ser",
      "case": "java-serialization-legacy-object",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256"
    }
  ]
}
~~~

Manifest là một **mẫu quản lý dữ liệu test**, không phải standard bắt buộc. SHA256 phải được tính trên **file bytes thật**, không điền một chuỗi giả trong bộ fixture chính thức.

### 5.1. Expected result là ý nghĩa nghiệp vụ

Ví dụ `v1-order-basic.json` chứa:

~~~json
{
  "orderId": "00001234",
  "amount": "125.50",
  "currency": "VND",
  "createdAt": "2024-10-26T21:30:00+07:00",
  "status": "PAID",
  "legacyChannel": "BRANCH"
}
~~~

Các invariants:
- Order ID phải giữ **leading zeros**, không bị ép sang số 1234.
- Amount phải là 125.50 theo đơn vị hợp đồng; không làm tròn/scale sai.
- Currency là VND, không tự chuyển sang một default mới.
- Timestamp biểu thị đúng **instant** và timezone/offset semantics.
- Trạng thái PAID vẫn mang ý nghĩa đã thanh toán, không bị map sang trạng thái mới sai.
- `legacyChannel` nếu bị loại khỏi domain model thì phải có policy rõ: bỏ qua, map sang field mới hoặc lưu lại phục vụ audit.

**Không chỉ so sánh rằng JSON parse được.** Phải assert dữ liệu được diễn giải đúng.

## 6. Ví dụ JUnit 5: đọc JSON do V1 tạo

Để test một file JSON cũ, dùng fixture đã được đóng băng. Ví dụ kiểm tra các giá trị cần bảo toàn mà không phụ thuộc domain mapping mới:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class LegacyOrderJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsLegacyOrderWithoutChangingMeaning() throws Exception {
        try (InputStream in = getClass().getResourceAsStream(
                "/legacy-data/json/v1-order-basic.json")) {

            assertNotNull(in, "Missing immutable legacy fixture");
            JsonNode root = mapper.readTree(in);

            assertEquals("00001234", root.path("orderId").asText());
            assertEquals("VND", root.path("currency").asText());
            assertEquals("PAID", root.path("status").asText());

            BigDecimal amount =
                    new BigDecimal(root.path("amount").asText());
            assertEquals(0, amount.compareTo(new BigDecimal("125.50")));

            Instant actualInstant =
                    OffsetDateTime.parse(
                        root.path("createdAt").asText()
                    ).toInstant();
            assertEquals(
                    Instant.parse("2024-10-26T14:30:00Z"),
                    actualInstant
            );
        }
    }
}
~~~

Đoạn này cần dependencies JUnit 5 và Jackson Databind phù hợp với build. Đây là test **đọc và kiểm một phần meaning của file JSON**. Trong ứng dụng thật còn phải chạy qua **actual V2 deserializer/mapper/business service** để xác minh đường đọc production, không chỉ test một JSON parser độc lập.

### 6.1. Khi amount scale cũng là hợp đồng

`BigDecimal.compareTo` so giá trị số học, nhưng `BigDecimal.equals` còn xét scale. Nếu hệ thống billing yêu cầu format đúng hai chữ số thập phân, cần assert riêng:

~~~java
BigDecimal amount = new BigDecimal("125.50");

assertEquals(0, amount.compareTo(new BigDecimal("125.5")));
assertEquals(2, amount.scale());
assertEquals("125.50", amount.toPlainString());
~~~

Không nên biến amount sang `double` để test tiền tệ; giá trị decimal có thể bị sai do biểu diễn nhị phân. Nếu dữ liệu lưu ở minor units (cent/đơn vị nhỏ nhất), ghi rõ conversion và rounding policy của từng currency.

### 6.2. JSON missing và null là hai trạng thái khác nhau

Ví dụ:

~~~json
{
  "orderId": "ord-1",
  "discountCode": null
}
~~~

khác với:

~~~json
{
  "orderId": "ord-1"
}
~~~

ở một số contract. Jackson `JsonNode` có thể phân biệt:
- `root.has("discountCode")`: field tồn tại.
- `root.get("discountCode").isNull()`: field có explicit JSON null.
- `root.path("discountCode").isMissingNode()`: không có field.

Khi nâng mapper/framework, đừng tự coi missing và null giống nhau nếu chúng có ý nghĩa “chưa áp dụng”, “xóa dữ liệu” hoặc “không thay đổi”.

## 7. Test đường đọc production, không chỉ thư viện parser

Một test cấp parser là cần thiết nhưng chưa đủ. Với application, data đi qua:

~~~text
Legacy bytes
    |
    v
Storage client / JDBC / Kafka consumer
    |
    v
Decoder / codec
    |
    v
DTO / Entity mapping
    |
    v
Validation / normalization
    |
    v
Business rules
    |
    v
API output / side effect / decision
~~~

Nếu production dùng Jackson mix-ins, custom serializer, Spring MessageConverter hoặc Hibernate AttributeConverter, test dùng `new ObjectMapper()` riêng có thể không phản ánh config thật.

Để khép kín:
1. Tạo một test với codec được inject từ application context V2.
2. Đọc fixture qua code path mà production dùng.
3. Assert domain invariants và mapping.
4. Nếu là message consumer, assert idempotency và state changes.
5. Nếu là database, assert query/transaction semantics.
6. Nếu là file, test charset, header và schema version.
7. Dùng contract/integration tests với dependency thật hoặc bản thay thế có hành vi kiểm soát được.

### 7.1. Chọn test boundary phù hợp

| Boundary | Phát hiện được | Bỏ sót |
|---|---|---|
| JsonNode/parser unit | JSON syntax, field representation | DTO mapping và business logic |
| DTO deserializer unit | Jackson annotations/converter behavior | Database/runtime services |
| Repository integration | JDBC/ORM mapping, SQL schema | End-to-end HTTP/message behavior |
| Consumer integration | Message headers, codec, business event mapping | Producer release compatibility nếu không replay |
| End-to-end staging | Runtime, configuration, services, database | Trường hợp hiếm nếu fixtures thiếu |

Nên dùng nhiều boundary thay vì đặt mọi rủi ro vào một end-to-end suite lớn, chậm và khó chẩn đoán.

## 8. Kiểm thử Java native serialization

Java serialization qua `ObjectOutputStream`/`ObjectInputStream` là một trường hợp đặc biệt: object stream có thể chứa tên class, `serialVersionUID`, field descriptors và serialized object graph. Khi nâng JDK/framework hoặc đổi class:
- Class bị đổi package/name có thể không còn được nạp.
- `serialVersionUID` không tương thích có thể gây `InvalidClassException`.
- Field thêm/bớt/đổi kiểu ảnh hưởng deserialization.
- `readObject`, `readResolve`, `writeReplace` hoặc `Externalizable` logic thay đổi.
- Proxy, inner class, enum và collection implementation có giới hạn riêng.
- Classloader/module rules có thể khiến stream cũ không load được.

### 8.1. serialVersionUID và class identity

Ví dụ model có thể serializable:

~~~java
package com.example.archive;

import java.io.Serializable;

public final class LegacyInvoice implements Serializable {
    private static final long serialVersionUID = 2L;

    private String invoiceId;
    private long amountMinor;

    public String getInvoiceId() {
        return invoiceId;
    }

    public long getAmountMinor() {
        return amountMinor;
    }
}
~~~

`serialVersionUID` giúp kiểm tra compatibility của serializable class khi deserialize, nhưng **giữ nguyên UID không bảo đảm giữ behavior** nếu field semantics hoặc `readObject` đã đổi. Đồng thời, đổi package làm tên class khác; chỉ giữ UID của class mới không khiến `ObjectInputStream` tự hiểu class cũ.

Không được tự đổi `serialVersionUID` chỉ để ép JVM “nhận” dữ liệu khi không hiểu object graph.

### 8.2. Test đọc stream cũ

Một ví dụ test với fixture `v1-invoice.ser` do bản V1 thực sự ghi:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.archive.LegacyInvoice;
import java.io.InputStream;
import java.io.ObjectInputStream;
import org.junit.jupiter.api.Test;

class LegacySerializationTest {
    @Test
    void loadsV1InvoiceStream() throws Exception {
        try (InputStream raw = getClass().getResourceAsStream(
                "/legacy-data/binary/v1-invoice.ser")) {

            assertNotNull(raw, "Missing V1 serialized fixture");

            try (ObjectInputStream in = new ObjectInputStream(raw)) {
                Object value = in.readObject();

                assertInstanceOf(LegacyInvoice.class, value);
                LegacyInvoice invoice = (LegacyInvoice) value;
                assertEquals("INV-2024-001", invoice.getInvoiceId());
                assertEquals(12550L, invoice.getAmountMinor());
            }
        }
    }
}
~~~

Ví dụ minh họa JUnit 5 dùng `assertInstanceOf` của phiên bản hỗ trợ API đó. Đây là bài test **chỉ đọc fixture synthetic, nguồn tin cậy trong repository test**. Không áp dụng cách đọc deserialization không kiểm soát cho dữ liệu từ network hoặc bên ngoài.

### 8.3. Cảnh báo bảo mật khi deserialize

**Native Java deserialization của dữ liệu không tin cậy có thể nguy hiểm** và đã là nguồn nhiều lỗ hổng. Nếu ứng dụng hiện đọc object stream từ cache/message/external input:
- Ưu tiên thay bằng format có schema rõ và reader được thiết kế an toàn.
- Đặt input size limits và allowlist type phù hợp.
- Cân nhắc `ObjectInputFilter` (JEP 290 và các cơ chế lọc nối tiếp theo runtime).
- Kiểm tra classpath có các gadget chains nguy hiểm không.
- Không coi filter đơn lẻ là bằng chứng an toàn.
- Không đưa binary fixtures lấy từ nguồn không tin cậy vào test runner với quyền cao.

Mẫu filter minh họa cho một luồng **chỉ** chứa class trong package đã biết:

~~~java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=500;maxbytes=1048576;"
      + "com.example.archive.*;java.base/*;!*"
);
in.setObjectInputFilter(filter);
~~~

Đây là cấu hình **minh họa**, không phải allowlist bảo mật được xác nhận cho một object graph cụ thể. Filter patterns, collections, arrays và types cần được thiết kế/kiểm chứng cho runtime, dữ liệu và threat model thực tế. Nếu ứng dụng không còn cần Java serialization, loại bỏ cơ chế này có thể an toàn và dễ bảo trì hơn duy trì tương thích vô thời hạn.

### 8.4. Đừng trộn Java serialization với JSON compatibility

`serialVersionUID` không có ý nghĩa với JSON thuần, Avro hoặc Protobuf, trừ khi format/application code tự dùng nó. Ngược lại, việc JSON DTO giữ tên field giống cũ không giúp Java `ObjectInputStream` đọc class đã đổi package.

Mỗi format cần **schema/identity/compatibility policy riêng**.

## 9. Kiểm thử database records cũ

Database là nơi dữ liệu cũ tồn tại lâu và thường có nhiều trạng thái legacy:
- `NULL` trước đây được phép nhưng code mới assume non-null.
- Một enum/string status cũ không còn trong Java enum mới.
- Số decimal/float có rounding khác.
- Timestamp có timezone hoặc không timezone.
- Một foreign key bị thiếu từ dữ liệu cũ.
- JSON column có schema cũ.
- Cột đã được rename/drop nhưng dữ liệu chưa backfill.
- ORM mapping mới dùng default constructor, records hoặc custom converter khác.
- Query mới dùng join/filter làm mất các row cũ.

### 9.1. Test trên bản sao schema và dữ liệu đã pin

Quy trình:

~~~text
Legacy schema + legacy rows (synthetic/sanitized)
                    |
                    v
Restore vào DB test độc lập
                    |
                    v
Apply migration scripts versioned
                    |
                    v
New application repository/ORM đọc
                    |
                    v
Assert dữ liệu + business invariants
                    |
                    v
Optional: write/read/rollback compatibility checks
~~~

Không chạy thử migration script mang tính phá hủy trên database production chỉ để “xem có hoạt động không”. Dùng bản sao có quyền hạn, retention và masking phù hợp.

### 9.2. Schema fixture ví dụ

Giả sử V1 đã có bảng:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(32) PRIMARY KEY,
    amount_minor BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    external_ref VARCHAR(64)
);

INSERT INTO orders
  (order_id, amount_minor, currency, status, created_at, external_ref)
VALUES
  ('00001234', 12550, 'VND', 'PAID',
   TIMESTAMP '2024-10-26 14:30:00', 'legacy-42'),
  ('00001235', 0, 'VND', 'CANCELLED',
   TIMESTAMP '2024-10-26 15:00:00', NULL);
~~~

Đây là dataset minh họa. Trong hệ thật, **TIMESTAMP không có timezone** không tự chứng minh đó là UTC; interpretation phải theo contract của producer/database session cũ. Nếu V1 ghi local time, V2 phải có quy tắc chuyển phù hợp trước khi coi timestamp là một instant.

### 9.3. Test cả bản ghi tồn tại từ trước và bản ghi mới

Trong test dùng DB độc lập:
1. Nạp schema V1 và rows do V1 tạo.
2. Apply các migrations mà V2 sẽ chạy.
3. Khởi động repository/ORM V2.
4. Đọc rows cũ theo ID và assert fields.
5. Ghi một row mới bằng V2.
6. Query lại bằng V2.
7. Nếu rollback vẫn được yêu cầu, dùng reader V1 để thử đọc **cả row cũ và row mới**.
8. Kiểm tra row counts, duplicate keys, constraints, transaction behavior.
9. Đánh giá behavior khi V2 update row cũ rồi V1 đọc lại.

Không chỉ test “migration SQL đã chạy không lỗi”; code mới còn có thể diễn giải row sai.

### 9.4. Ví dụ repository regression test

Ví dụ Java/JDBC test đọc giá trị legacy sau khi test setup đã restore schema/fixtures:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

class LegacyOrdersJdbcTest {
    private final DataSource dataSource;

    LegacyOrdersJdbcTest(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Test
    void readsOldOrderWithoutLosingIdentifier() throws Exception {
        String sql =
                "SELECT order_id, amount_minor, currency, status "
              + "FROM orders WHERE order_id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, "00001234");

            try (ResultSet rs = statement.executeQuery()) {
                assertTrue(rs.next());
                assertEquals("00001234", rs.getString("order_id"));
                assertEquals(12550L, rs.getLong("amount_minor"));
                assertEquals("VND", rs.getString("currency"));
                assertEquals("PAID", rs.getString("status"));
                assertFalse(rs.next());
            }
        }
    }
}
~~~

Đây là **test outline**; `DataSource` phải được test framework cung cấp/inject (ví dụ Spring integration test hoặc test fixture), không phải cứ tạo class là JUnit tự inject constructor. Điều đáng chú ý: `javax.sql.DataSource` là **API Java SE JDBC** nên vẫn giữ tên đó khi ứng dụng chuyển Jakarta EE. Không tự thay thành một `jakarta.sql.DataSource` không tồn tại.

### 9.5. Dùng database thật hoặc version đủ đại diện

Một in-memory database khác engine có thể:
- Khác quy tắc SQL type/precision.
- Khác timezone, collation và ordering.
- Khác transaction isolation/locking.
- Khác JSONB/array type.
- Khác index/dialect behavior.

Với thay đổi ORM/JDBC, test bằng **cùng database engine và version gần production** (ví dụ container độc lập) thường giá trị hơn chỉ test bằng H2 nếu production là PostgreSQL/Oracle/MSSQL.

## 10. Schema migration theo expand–migrate–contract

Khi deployment có nhiều phiên bản cùng tồn tại, thay schema trực tiếp bằng drop/rename có thể làm bản cũ không chạy được.

Mô hình:

~~~text
EXPAND
  Thêm cột/bảng/index mới theo cách backward-compatible
        |
        v
MIGRATE
  Backfill dữ liệu cũ, đổi app readers/writers có kiểm soát
        |
        v
VERIFY
  Test dữ liệu lịch sử, mixed versions, invariants
        |
        v
CONTRACT
  Chỉ bỏ schema cũ khi không còn consumer và rollback window
~~~

### 10.1. Ví dụ thêm trường mới mà không phá row cũ

Giả sử V2 thêm `completed_at`:

~~~sql
ALTER TABLE orders
    ADD COLUMN completed_at TIMESTAMP NULL;
~~~

Các row V1 có giá trị `NULL` ở cột mới. V2 phải xử lý chúng đúng, ví dụ:
- Với order đã PAID, có policy backfill timestamp hay không?
- Không được giả định `completed_at` luôn non-null ngay khi deploy.
- Nếu cần NOT NULL, phải hoàn thành backfill và xác minh trước khi thêm constraint.
- Nếu V1 vẫn ghi row mới trong rolling deployment, cơ chế backfill phải xử lý **các row phát sinh đồng thời**.

**Không tạo giá trị “2026-01-01” giả cho toàn bộ lịch sử chỉ để vượt NOT NULL** nếu nó làm sai báo cáo, audit hoặc SLA.

### 10.2. Kiểm thử migration đúng thứ tự

Khi dùng Flyway/Liquibase hoặc tool tương tự:
- Pin migration script versions.
- Restore V1 snapshot rồi apply đúng migration sequence.
- Kiểm tra idempotency ở mức tool quy định và rollback policy.
- Assert số row, keys, constraints, data semantics.
- Kiểm tra index creation/locking và giới hạn downtime.
- Chạy V2 đọc dữ liệu sau migrate.
- Nếu mixed deployment, thử V1/V2 cùng đọc/ghi theo cửa sổ hỗ trợ.

Không suy từ “Flyway applied successfully” rằng dữ liệu business-level đã đúng.

## 11. JSON: thay đổi mapper/framework có thể thay ý nghĩa

JSON không chứa Java class descriptors theo mặc định, nhưng application serializer có thể thay:
- Tên property do naming strategy.
- Default visibility/field detection.
- Null inclusion hoặc absent-field handling.
- Enum encoding: tên/string/ordinal.
- Dates: numeric epoch, ISO-8601, timezone/offset.
- BigDecimal representation.
- Unknown properties: reject hoặc ignore.
- Polymorphic type metadata.
- Custom annotations/mix-ins.
- Constructor/record support.
- Module registration như `JavaTimeModule`.

### 11.1. Những fixture JSON bắt buộc cân nhắc

| Tình huống | Fixture legacy | Kết quả kỳ vọng |
|---|---|---|
| Field optional vắng | Không có `discountCode` | Giữ default semantics V1 |
| Explicit null | `discountCode: null` | Không bị hiểu thành empty string nếu khác nghĩa |
| Unknown field | Có trường V1 không còn ở V2 | Ignore/log/reject theo contract |
| Unknown enum | `status: "ON_HOLD_LEGACY"` | Mapping an toàn, không crash hoặc default sai |
| Large integer | ID `9007199254740993` ở dạng số | Không mất precision qua JS/JSON bridge |
| Decimal | `"125.50"` hoặc `125.50` | Không làm tròn/đổi scale ngoài policy |
| Date/time | Offset khác UTC, ngày DST | Giữ instant/local meaning |
| Unicode | Tiếng Việt, emoji, tổ hợp dấu | Không mojibake/normalize sai |
| Polymorphism | Type discriminator V1 | Chọn subtype an toàn, đã cho phép |
| Collection | Empty, null, duplicates | Mapping đúng semantics |
| Nested schema | Objects/arrays sâu | Không mất/trộn fields |
| Old defaults | Field V1 từng vắng | New code không tự tạo behavior sai |

### 11.2. Unknown enum nên có policy rõ

Ví dụ V1 từng ghi trạng thái `WAITING_APPROVAL` nhưng V2 dùng `PENDING_REVIEW`. Có thể:
- Map có chủ đích bằng adapter.
- Giữ trạng thái legacy và xử lý như một state riêng.
- Từ chối nếu hợp đồng đã không còn hỗ trợ và có data migration đi trước.
- Đưa vào dead-letter/reconciliation flow với alert.

Không dùng `catch (Exception) { return PAID; }` hoặc tự map mọi trạng thái lạ thành trạng thái thành công. Đây là lỗi **tính đúng đắn dữ liệu**, không chỉ tương thích cú pháp.

### 11.3. JSON polymorphic type metadata

Nếu V1 lưu tên Java class trong JSON, ví dụ:

~~~json
{
  "@class": "com.example.legacy.payment.CardPayment",
  "amount": "125.50"
}
~~~

đổi package/class có thể phá deserialization. Ngoài ra, polymorphic type deserialization có rủi ro bảo mật nếu cho phép tùy ý type từ dữ liệu không tin cậy.

Hướng xử lý:
- Ưu tiên stable discriminator thuộc schema, ví dụ `type: "CARD"`, thay vì tên class nội bộ.
- Dùng allowlist/subtype registry rõ.
- Migrate old discriminator qua adapter được kiểm soát.
- Không bật default typing rộng để “đọc hết dữ liệu cũ”.
- Test negative cases và input ngoài whitelist.

## 12. Charset và Unicode sau khi nâng JDK

File/CSV/text được lưu với charset mặc định của JVM cũ có thể bị đọc khác khi nâng JDK hoặc chuyển OS/container.

**JEP 400** chuẩn hóa default charset là UTF-8 từ JDK 18 trong nhiều hoàn cảnh thông thường, với những ngoại lệ/cơ chế tương thích có điều kiện. Vì vậy code dùng `new String(bytes)` hoặc `FileReader` không chỉ rõ charset có nguy cơ diễn giải dữ liệu cũ sai nếu trước đây dùng một charset khác.

### 12.1. Không dùng charset mặc định cho format lâu dài

Tránh:

~~~java
String text = new String(bytes); // Phụ thuộc default charset
~~~

Thay bằng charset theo **format contract**:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

byte[] bytes = Files.readAllBytes(Path.of("legacy-export.csv"));

String utf8Text = new String(bytes, StandardCharsets.UTF_8);

// Nếu legacy format thực sự dùng Windows-1252:
// Charset legacy = Charset.forName("windows-1252");
// String legacyText = new String(bytes, legacy);
~~~

Không tự chọn UTF-8 khi dữ liệu V1 thật sự được ghi bằng một charset khác. Cần xác định từ producer version, header/BOM, tài liệu format, test fixture hoặc dữ liệu gốc đã kiểm chứng.

### 12.2. Golden fixture Unicode

Cân nhắc các dữ liệu như:
- Tên tiếng Việt có dấu: `Đặng Thị Ánh`.
- Emoji và surrogate pairs.
- Dấu kết hợp Unicode (NFD) so với dạng dựng sẵn (NFC).
- Dữ liệu có BOM, CRLF/LF.
- Ký tự `€`, `£`, `\u0000` nếu format cho phép.
- Text dài và ký tự ngoài Basic Multilingual Plane.

Mục tiêu là bảo toàn **giá trị nghiệp vụ/biểu diễn đã cam kết**, không phải luôn normalize chuỗi tùy ý. Unicode normalization có thể ảnh hưởng signature/hash, search và equality.

## 13. Ngày giờ và timezone

Dữ liệu thời gian là một nhóm regression nổi bật:
- `java.util.Date` và `Calendar` so với `java.time`.
- `LocalDateTime` không mang timezone.
- `Instant` đại diện một mốc thời gian.
- `OffsetDateTime` có offset cố định.
- `ZonedDateTime` có region/timezone rules.
- JVM default timezone khác giữa local/container.
- tzdb được cập nhật qua JDK releases.
- JDBC driver/ORM thay cách bind timestamp.

### 13.1. Cùng chuỗi chưa chắc cùng thời điểm

Ví dụ:

~~~text
2024-10-26T21:30:00+07:00
2024-10-26T14:30:00Z
~~~

là cùng một instant. Nếu record là **giờ hẹn địa phương**, có thể cần bảo toàn local time và timezone region thay vì chỉ instant. Contract phải nói rõ ngữ nghĩa field.

### 13.2. Test các trường hợp biên

- Giờ trùng hoặc không tồn tại do DST ở vùng có DST.
- Epoch 0 và timestamps trước 1970.
- Offset khác UTC.
- Mốc cuối tháng, leap year.
- `LocalDate` theo calendar day khác timestamp.
- SQL `TIMESTAMP WITHOUT TIME ZONE` so với `WITH TIME ZONE`.
- Trường hợp JDK/tzdb mới làm thay đổi quy tắc vùng.

Một fixture được tạo bởi V1 ở JDK/OS cũ và đọc trên V2 JDK mới sẽ giúp phát hiện tác động của timezone defaults mà test dữ liệu do V2 tự tạo không thấy.

## 14. Số học, tiền tệ và precision

Dữ liệu cũ có thể chứa:
- `DECIMAL(p,s)` trong SQL.
- Decimal strings trong JSON.
- `long` minor units.
- `double`/`float` cho legacy metrics.
- Currency conversions với rounding policy.
- Large integers vượt phạm vi JavaScript safe integer.

### 14.1. Test cả giá trị và quy tắc làm tròn

Nếu V1 ghi `125.50` nhưng V2 chuyển thành `125.5`, numeric value bằng nhau nhưng format/scale có thể khác với một hợp đồng về hóa đơn. Nếu V2 dùng `double` rồi chuyển lại sang `BigDecimal` sai cách, lỗi rounding có thể xuất hiện ở giá trị biên.

Nên có fixtures:
- `0`, số âm nếu hợp đồng cho phép.
- Số cực lớn và cực nhỏ.
- Nhiều chữ số thập phân.
- Boundary rounding (ví dụ giữa hai minor units).
- Currency có zero hoặc ba decimal minor units.
- Tổng nhiều dòng bằng invoice total theo policy.

Không sửa dữ liệu cũ chỉ để đạt một cách biểu diễn mới nếu business/invoice/audit contract yêu cầu giữ nguyên.

## 15. Avro, Protobuf và schema evolution

Với event streaming hoặc lưu binary data, format có schema thường hỗ trợ evolution nhưng **không phải mọi thay đổi schema đều an toàn**.

### 15.1. Avro

Avro dùng writer schema và reader schema để giải mã theo quy tắc schema resolution. Khi thêm field, khả năng đọc cũ/mới phụ thuộc default và compatibility rules của schema registry hoặc consumer.

Ví dụ schema Avro V1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amountMinor", "type": "long" }
  ]
}
~~~

V2 thêm một field optional với default rõ:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amountMinor", "type": "long" },
    {
      "name": "source",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Việc có default có thể hỗ trợ reader V2 đọc dữ liệu writer V1 theo resolution rules phù hợp, nhưng **phải test thật với writer schema/reader schema đúng version và subject compatibility policy**. Không kết luận mọi schema changes khác cũng an toàn.

### 15.2. Protobuf

Protobuf sử dụng field numbers làm identity. Quy tắc quan trọng:
- Không tùy tiện reuse field number đã dùng cho ý nghĩa khác.
- Khi xóa field, có thể `reserved` number/name để tránh reuse.
- Cẩn thận khi đổi wire type hoặc numeric representation.
- Unknown fields có thể được giữ hoặc mất tùy runtime/language/transform path.
- Optional/presence semantics khác nhau theo syntax/version.
- Enum values mới cần consumer policy xử lý unknown.

Ví dụ:

~~~proto
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
  string currency = 3;
}
~~~

Nếu V2 thêm field 4, giữ lại 1–3 với semantics cũ. Không tự đổi `amount_minor = 2` thành `amount_major = 2` chỉ vì cùng wire type; đó là phá business contract dù decoder vẫn parse được.

### 15.3. Schema Registry checks chưa đủ

Một schema registry có thể báo compatibility PASS ở mức schema, nhưng vẫn cần kiểm:
- Business semantic mappings.
- Defaults thực tế khi field vắng.
- Consumers đã deploy và schema IDs trong message headers.
- Producer/consumer serialization configuration.
- Replay event cũ từ retention/DLQ.
- Idempotency, exactly-once/at-least-once assumptions.
- Authentication/authorization và data masking.

**Schema-compatible không đồng nghĩa behavior-compatible**.

## 16. Kafka/JMS, DLQ và event replay

Một V2 consumer có thể nhận event mới tốt nhưng fail khi replay V1 event từ 30 ngày trước. Test nên lấy một corpus event cũ do V1 tạo, gồm headers và payload, sau đó replay vào consumer V2 trong môi trường cách ly.

### 16.1. Những điều cần assert

- Consumer nhận đúng key, headers, schema ID và partition semantics.
- Payload decode được mà không làm mất field cần thiết.
- Domain event mapping đúng.
- Event cũ không bị xử lý hai lần khi replay.
- Không tạo duplicate invoices/payments.
- Poison messages được đưa vào DLQ với thông tin đủ chẩn đoán.
- Consumer lag không tăng vô hạn.
- Error/timeout/retry/backoff policy có kiểm soát.
- Trace/metrics phân biệt legacy event version.

Một replay thành công ở parser nhưng tạo hai bản ghi thanh toán vẫn là **regression nghiêm trọng**.

### 16.2. Test offset/checkpoint cũ

Batch/stream processors có thể lưu:
- Kafka offsets.
- Last processed event ID.
- Checkpoint state được serialize.
- Watermarks/windows.
- Retry queue/delayed jobs.

Khi nâng JDK/library, phải kiểm tra **resume từ checkpoint V1**:
1. Tạo checkpoint bằng V1.
2. Dừng có kiểm soát.
3. Khởi động V2 với checkpoint đó.
4. Assert không bỏ sót hoặc lặp business state transitions.
5. Thử failure/restart ở vài ranh giới transaction.

Không chỉ kiểm consumer chạy được từ offset mới nhất; production có thể resume từ một checkpoint tồn tại trước migration.

## 17. Cache và HTTP session giữa hai phiên bản

Dữ liệu cache thường bị xem là “có thể xóa”, nhưng không phải cache nào cũng vô hại khi invalidation:
- User sessions.
- Checkout/cart state.
- Idempotency keys.
- Distributed locks.
- Rate-limit counters.
- Long-running job state.
- Reference data cache chứa serializer-specific classes.

### 17.1. Các lựa chọn chuyển tiếp

| Phương án | Khi phù hợp | Rủi ro/đổi chác |
|---|---|---|
| V2 đọc được cache V1 | Cần giữ session/state qua rollout | Phải hỗ trợ codec/type identity cũ |
| Versioned cache keys | Hai phiên bản chạy song song | Tăng memory và cache misses |
| Invalidate có chủ đích | Dữ liệu có thể tái tạo an toàn | Cold-start thundering herd, logout |
| Dual-read rồi rewrite | Chuyển dần store | Race conditions, write amplification |
| External session schema độc lập Java class | Cần ổn định dài hạn | Chi phí refactor và format governance |

Nếu chọn invalidate sessions khi chuyển namespace Java EE/Jakarta, phải xem UX, security, TTL và logout policy. Không giả định một serialized session tạo bởi `javax.servlet` stack cũ sẽ tự khôi phục trong `jakarta.servlet` stack mới.

### 17.2. Tránh mixed-cache poisoning

Khi V1/V2 cùng ghi một key với hai formats khác nhau, app có thể lúc đọc được lúc lỗi. Một phương án là dùng key prefix phiên bản:

~~~text
orders:cache:v1:<orderId>
orders:cache:v2:<orderId>
~~~

Nhưng cần cân nhắc:
- TTL và eviction.
- Cache hit ratio/cold start.
- Nguồn dữ liệu chính (source of truth).
- Invalidations giữa hai namespace.
- Không duplicate dữ liệu nhạy cảm không cần thiết.

Key versioning không giải quyết semantic incompatibility trong database hoặc event log.

## 18. XML, JAXB và Jakarta namespace

Khi chuyển từ Java EE/Jakarta EE 8 sang Jakarta EE 9+, nhiều API enterprise thay namespace Java từ `javax.*` sang `jakarta.*`. Nhưng XML payload namespace URI không tự đổi theo Java package.

Cần phân biệt:
- Java `javax.xml.parsers.*` thuộc Java SE vẫn giữ nguyên.
- JAXB `javax.xml.bind.*` của API cũ có bản Jakarta `jakarta.xml.bind.*`.
- XML namespace URI trong payload là hợp đồng bên ngoài; có thể không đổi.
- JAXB annotations/providers, schema generation và default binding có thể thay khi nâng version.

### 18.1. Test XML fixture V1

Giả sử file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<invoice xmlns="urn:example:invoices:v1" id="INV-0001">
  <amount currency="VND">125.50</amount>
  <issuedAt>2024-10-26T21:30:00+07:00</issuedAt>
</invoice>
~~~

V2 dùng Jakarta XML Binding hoặc XML parser mới phải:
- Giữ và nhận diện `urn:example:invoices:v1` nếu hợp đồng vẫn hỗ trợ.
- Map amount đúng kiểu/scale.
- Parse timestamp theo semantics cũ.
- Không tự đổi wire namespace URI chỉ vì import Java từ `javax.xml.bind` sang `jakarta.xml.bind`.
- Chặn XML external entities/DTD nguy hiểm theo parser/security policy phù hợp.

Nếu V2 xuất XML trong schema mới, cần thêm test cho old reader/new writer theo rollback contract nếu còn yêu cầu.

## 19. Mã hóa và dữ liệu đã ký

Khi dữ liệu cũ được mã hóa hoặc ký:
- JVM/provider có thể thay algorithm availability hoặc defaults.
- Key alias, keystore/truststore format và password policy có thể khác.
- GCM IV/tag length và metadata bắt buộc có thể không được lưu nhất quán.
- Encoding trước khi ký (charset, Unicode normalization, canonical JSON/XML) có thể đổi.
- Certificate chain/trust policy có thể thay theo JDK security update.

### 19.1. Không xem decrypt success là đủ

Với encrypted archived data, test:
1. Khôi phục ciphertext synthetic do V1 tạo với key test riêng.
2. V2 giải mã được bằng **đúng thuật toán, IV, tag và key metadata**.
3. Plaintext trùng golden value.
4. Khi bị sửa ciphertext/tag, verification thất bại.
5. Không log plaintext/key/IV nhạy cảm.
6. Khi key rotation, dữ liệu cũ vẫn có đường giải mã được phê duyệt.

Nếu signature verification thay đổi, test cả valid old signatures và tampered inputs. **Không tắt validation để vượt regression**; có thể là thay đổi security chính đáng cần một migration plan riêng.

## 20. Kiểm thử old-data → new-data migration

Có những thay đổi không thể chỉ đọc trực tiếp data cũ bằng code mới; phải **transform data** trước, ví dụ:
- Tách một field `fullName` thành first/last name có policy.
- Chuyển datetime local thành UTC instants kèm timezone metadata.
- Chuyển amount decimal sang minor units.
- Đổi status enum theo bảng mapping nghiệp vụ.
- Thêm normalized lookup/index.
- Migrate schema document hoặc encryption envelope.

Một data migration đúng cần:
- Script/version và source/target schema rõ.
- Không mất bản ghi/không phát sinh duplicate.
- Preserve invariant tổng tiền, identity, trạng thái.
- Idempotency hoặc retry policy khi chạy lại.
- Progress metrics và checkpoint.
- Error/quarantine channel cho những record không thể map.
- Backup/rollback/forward-only policy.
- Audit/log không rò dữ liệu nhạy cảm.

### 20.1. Invariants cần kiểm tra bằng dữ liệu thật đã làm sạch

| Invariant | Ví dụ |
|---|---|
| Count | Số order trước/sau không giảm ngoài quy tắc loại bỏ |
| Identity | `orderId` có leading zeros không đổi |
| Monetary sum | Tổng amount theo currency không đổi |
| Referential integrity | Foreign keys/links vẫn hợp lệ |
| Status mapping | Mỗi legacy enum chuyển đúng business state |
| Time | Instant/local date/zone đúng theo contract |
| Ordering | Business event sequence không bị đảo |
| Idempotency | Chạy migration lại không nhân đôi records |
| Completeness | Không có record bị bỏ do null/unknown values |
| Data privacy | Token/PII không lộ qua migration logs |

Chỉ dùng checksum của toàn bảng sau migration có thể không phù hợp nếu schema/format đổi có chủ đích. Khi ấy cần **semantic comparison** dựa trên canonicalized business fields.

### 20.2. Không “sửa” dữ liệu legacy một cách im lặng

Một record legacy có trạng thái lạ, amount âm hoặc timestamp không hợp lệ có thể là:
- Dữ liệu hợp lệ theo rule cũ.
- Bug lịch sử đã được chấp nhận.
- Corruption cần xử lý đặc biệt.
- Dữ liệu bị nhập sai và cần reconciliation.

V2 không nên tự sửa thành giá trị hợp lệ mới mà không ghi audit/policy. Cần phân loại và quyết định nghiệp vụ, đặc biệt với tài chính, pháp lý, quyền truy cập và trạng thái giao dịch.

## 21. Kiểm thử forward/backward compatibility khi rolling deployment

Nếu V1/V2 cùng chạy trong một khoảng thời gian:

~~~text
         Shared DB / cache / broker
                  ^
                  |
        +---------+---------+
        |                   |
    App V1                 App V2
    old writer            new writer
    old reader            new reader
~~~

Hai phiên bản có thể đọc và ghi cùng store; vì vậy test “V2 đọc data V1” chỉ là một nửa.

Ma trận cần:
- V1 đọc record do V1 ghi.
- V2 đọc record do V1 ghi.
- V2 đọc record do V2 ghi.
- **V1 đọc record do V2 ghi** khi rollback/rolling deployment yêu cầu.
- V1 và V2 update cùng record trong điều kiện thực tế.
- Race conditions, optimistic locking và transaction/version columns.
- Cache keys, event formats và consumer contract.
- Schema migrations trước/sau deploy.

### 21.1. Expand–migrate–contract áp dụng cả format

V1 chưa biết field `newStatus`:
1. Giai đoạn expand: V2 thêm field optional, reader V1 phải tolerate hoặc V2 không ghi field mới cho old readers.
2. Giai đoạn migrate: backfill/mapping có kiểm soát; cả hai reader hoạt động.
3. Giai đoạn contract: chỉ bỏ field cũ khi không còn reader V1 và hết rollback window.

Không đổi nghĩa của một field đang được V1 sử dụng chỉ vì database cho phép update.

### 21.2. Forward-only migration cần quyết định rõ

Nếu V2 ghi dữ liệu mà V1 không thể đọc và business đã chấp nhận không rollback trực tiếp:
- Ghi rõ thời điểm cutover.
- Có backup/snapshot trước đó.
- Có kế hoạch khôi phục hoặc roll-forward.
- Hạn chế canary/mixed deployment.
- Thử failover và backup restore trên staging.
- Không tuyên bố “rollback có thể” chỉ vì còn Docker image cũ.

## 22. Tổ chức test pipeline với fixture và runtime matrix

Một pipeline migration có thể chia thành:

~~~text
Stage 1: Compile + unit tests
      |
      v
Stage 2: Legacy fixture reader tests
      |
      v
Stage 3: DB migration from V1 snapshot
      |
      v
Stage 4: Message replay / cache-session tests
      |
      v
Stage 5: Cross-version read/write matrix
      |
      v
Stage 6: Production-like integration + canary
~~~

Mỗi stage cung cấp một bằng chứng riêng; không nên chỉ có một test “context loads”.

### 22.1. Matrix test theo JDK và application version

| Reader | JDK | Dữ liệu đầu vào | Test cần pass |
|---|---|---|---|
| V1 | JDK baseline được hỗ trợ | Fixtures V1 | Control/baseline |
| V2 | JDK đích | Fixtures V1 | **Bắt buộc** |
| V2 | JDK đích | Fixtures V2 | New format regression |
| V2 | JDK đích | Fixtures V0/V1 nếu còn retention | Historical compatibility |
| V1 | JDK baseline | Data V2 | Nếu hỗ trợ rollback/mixed deployment |
| V2 | JDK đích | DB snapshot đã apply migrations | Data migration correctness |

**Không chạy một tổ hợp JDK/framework không được hỗ trợ chỉ để lấp bảng**. Nếu một ô không khả thi, ghi rõ lý do, rủi ro và thay thế bằng test/operational policy thích hợp.

### 22.2. Chạy producer cũ khi cần tạo fixture mới

Có thể dùng container/image của V1 hoặc Git tag release V1 trong CI để tạo **synthetic fixtures**. Tuy nhiên:
- Pin image digest/tool versions.
- Tách output khỏi expected golden data đang được review.
- Không tự ghi đè fixtures đã được phê duyệt.
- Dùng synthetic test identities và fake endpoints.
- Có checksum/provenance.
- Không chạy code legacy với production credentials.

Nếu V1 build không còn chạy được trên JDK mới, tạo fixture với **JDK baseline đã được hỗ trợ**, rồi cho V2/JDK đích đọc. Đó chính là mục tiêu của cross-version test.

## 23. Kiểm soát dữ liệu nhạy cảm trong fixtures

Sử dụng snapshot production có thể cải thiện độ đại diện, nhưng gây rủi ro lớn:
- PII, email, địa chỉ, số điện thoại.
- Token, passwords, API keys.
- Payment identifiers, account numbers.
- Health/personal data, transaction histories.
- Internal hostnames/secrets trong serialized object graph.
- Business-sensitive documents.

Biện pháp:
- Ưu tiên **synthetic data tạo bởi V1** khi đủ bao phủ.
- Nếu cần sample thật, dùng quy trình masking/tokenization được phê duyệt.
- Đảm bảo masking giữ **đặc tính format** cần test: length, charset, null, cardinality, type, relationships.
- Dùng test-only keys với encrypted fixtures.
- Tách quyền truy cập và retention.
- Không commit raw production dumps vào Git.
- Không đưa snapshot vào public CI logs/artifacts.
- Ghi provenance và chính sách xóa.

**Ẩn tên người dùng bằng một chuỗi bất kỳ không đủ** nếu dataset còn embedded IDs/metadata có thể tái nhận dạng. Data governance phải được xử lý trước khi lưu fixtures.

## 24. Phép đo và bằng chứng sau migration

Bên cạnh test PASS/FAIL, có thể ghi:
- Số fixtures theo producer/schema version.
- Số fixtures đã đọc hợp lệ.
- Tỷ lệ/loại deserialization failures.
- Số record không map được hoặc bị quarantine.
- Số status legacy chưa được hỗ trợ.
- Checksum/semantic invariant mismatches.
- Replay duplicate counts.
- Database migration progress/rows affected.
- Cache miss/session invalidation rates.
- Thời gian xử lý data cũ và resource usage.

Nếu dữ liệu cũ đọc được nhưng tốc độ chậm hơn nhiều, vẫn có thể là regression quan trọng. Tách **compatibility correctness test** và **performance test** nhưng dùng cùng một corpus có tính đại diện khi phù hợp.

### 24.1. Sự khác nhau giữa kiểm một bản ghi và kiểm toàn tập

Một test một JSON fixture là tín hiệu ban đầu. Hệ thống thực có thể chứa:
- Nhiều schema generations.
- Field combinations hiếm.
- Outliers.
- Records với duplicates hoặc corruption lịch sử.
- Data created at specific JDK patch versions.
- Backfills/partial migrations.

Cần kết hợp:
1. **Golden fixtures** cho các hợp đồng quan trọng.
2. **Property-based/parameterized tests** trong phạm vi schema.
3. **Sanitized representative corpus** được phê duyệt.
4. **Migration/integration tests** với database thật.
5. **Canary monitoring** sau deploy.

Không dùng một mẫu ngẫu nhiên chưa có coverage strategy rồi kết luận mọi dữ liệu cũ đều tương thích.

## 25. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| `InvalidClassException` | `serialVersionUID` hoặc serialized class incompatible | So V1/V2 class descriptors và contract |
| `ClassNotFoundException` khi đọc stream cũ | Class/package đã đổi hoặc thiếu dependency | Migrate data/adapter/versioned codec |
| `NoClassDefFoundError` lúc deserialize | Runtime thiếu class cũ/transitive dependency | Dependency graph hoặc data migration |
| JSON parse pass nhưng domain sai | Defaults, enum, timezone, amount mapping | Assert business invariants |
| Unknown enum exception | Dữ liệu chứa trạng thái V1 không còn | Explicit mapping/legacy policy |
| Missing property thành null | JSON/ORM binding đổi | Schema migration và validation |
| Unicode mojibake | Charset cũ khác UTF-8 | Đọc theo đúng legacy encoding |
| Timestamp lệch giờ | Timezone/JDBC/ORM semantics đổi | Test instant/local time riêng |
| Numeric amount sai | Double/scale/minor unit conversion | BigDecimal và rounding tests |
| Entity không load | JPA/Hibernate/Jakarta mapping mismatch | Provider, annotation, schema |
| Old DB snapshot migrate nhưng thiếu rows | SQL filter/backfill sai | Counts/invariants và reconciliation |
| Cache session không restore | Java serialization/classloader/format mismatch | Versioned schema/invalidation policy |
| Kafka replay tạo duplicates | Idempotency/offset/checkpoint khác | State transition và replay test |
| Avro reader lỗi | Writer/reader schema resolution/default mismatch | Schema compatibility matrix |
| Protobuf parse nhưng sai nghĩa | Reused field number hoặc semantics | Schema history và contract tests |
| V2 đọc V1 pass, rollback fail | V1 không đọc data V2 | Mixed-version tests, forward-only decision |
| Regression chỉ ở production | Corpus test thiếu data generation thật | Sanitized representative fixtures |
| File chữ ký không hợp lệ | Bytes/charset/canonicalization đổi | Signature policy và stable encoding |
| Old encrypted archive không mở | Key/provider/envelope metadata khác | Versioned decryption/test key fixtures |

### 25.1. Không chữa mọi lỗi bằng cách bật lenient mode

Một số workaround dễ làm test xanh nhưng nguy hiểm:
- Ignore mọi unknown type/status.
- Catch deserialization errors rồi trả object mặc định.
- Tắt signature/certificate checks.
- Đổi amount sang `double` cho “dễ parse”.
- Gán timestamp sai thành current time.
- Tắt DB constraints mà không có migration.
- Dùng object deserialization từ dữ liệu không tin cậy.
- Tự động regenerate golden fixtures bằng V2.

Nếu contract chấp nhận được một lớp dữ liệu legacy, hãy viết **explicit adapter có logging, metrics, tests và vòng đời** thay vì mở parser đến mức không còn kiểm soát tính đúng đắn.

## 26. Lộ trình triển khai thực hành

### Bước 1: Chốt phạm vi dữ liệu phải giữ

Xác định tất cả stores/format/schema generations, retention và owner. Phân loại trường hợp cần đọc trực tiếp, cần data migration, có thể invalidate hoặc có forward-only cutover.

### Bước 2: Chụp baseline từ V1

Tạo/gắn synthetic fixtures bằng serializer/ORM/producer V1; lưu bytes và checksum, producer metadata, expected business values. Nếu cần sanitized samples, xử lý theo data security policy.

### Bước 3: Xây ma trận tương thích

Xác định V2 đọc V1 là bắt buộc; V1 đọc V2 có bắt buộc khi rollback/rolling deployment không; các version cũ hơn còn trong retention window hay không.

### Bước 4: Viết test theo từng format

- JSON/XML/CSV fixtures.
- Native serialization nếu còn được sử dụng.
- DB snapshots và SQL/JPA mapping.
- Avro/Protobuf writer-reader schema.
- Event replay/DLQ/checkpoints.
- Cache/session persisted values.
- Encryption/signature nếu liên quan.

### Bước 5: Chạy V2 trên runtime mục tiêu

Pin JDK vendor/build, framework/serializer/ORM versions. Chạy legacy reader tests trên chính môi trường V2 dự kiến deploy. Phân biệt lỗi dữ liệu với lỗi classpath/JVM.

### Bước 6: Test migration/dual-version behavior

Restore database cũ, apply scripts, kiểm invarants; nếu chạy hai phiên bản song song, thử cả V1/V2 đọc/ghi chung; xác định rollback window.

### Bước 7: Đánh giá edge cases và bảo mật

Kiểm null/missing, unknown enum, timezone/DST, decimal/encoding, serialized class names, oversized data, corrupted inputs, untrusted deserialization và signature checks.

### Bước 8: Canary và quan sát thực tế

Theo dõi deserialize errors, invalid data counts, replay failures, cache/session issues và business invariants theo schema version; có khả năng rollback hoặc roll-forward theo kế hoạch.

### Bước 9: Quản lý vòng đời data compatibility

Chỉ loại adapter/reader V1 khi:
- Không còn dữ liệu V1 trong retention **hoặc** dữ liệu đã migrate và xác minh hoàn chỉnh.
- Không còn consumer cần đọc V1.
- Rollback window kết thúc hoặc có chiến lược rollback khác.
- Security/data owners phê duyệt.
- Golden fixtures/test coverage được lưu hoặc đóng theo policy.

## 27. Ví dụ dự án: nâng Orders service từ JDK 17 lên 21

**Bối cảnh minh họa:** Orders service chạy JDK 17, Spring Boot 2.x, sử dụng PostgreSQL và Redis, phát event JSON lên Kafka. Dự kiến nâng lên JDK 21, Spring Boot 3.x/Jakarta và Hibernate major version mới.

### 27.1. Dữ liệu cũ cần hỗ trợ

- PostgreSQL: row từ 2022 trở đi, có `NULL` ở cột discount và status cũ.
- Redis: session/cache do V1 serializer tạo, TTL vài giờ.
- Kafka: event V1 còn trong topic/DLQ có retention.
- Object store: invoice JSON/XML đã lưu nhiều năm.
- Batch: job checkpoints từ V1 có thể khôi phục sau failover.

### 27.2. Bộ kiểm thử đề xuất

| Test | Fixture từ V1 | Kết quả cần chứng minh |
|---|---|---|
| LegacyOrderJsonTest | JSON V1 có amount/time/status | V2 đọc đúng business values |
| LegacyInvoiceXmlTest | XML invoice V1 | Namespace/time/amount không đổi |
| LegacyOrdersDbTest | PostgreSQL snapshot V1 | ORM/JDBC đọc đúng sau migration |
| LegacySessionTest | Redis session V1 synthetic | Restore hoặc invalidate theo policy |
| LegacyKafkaReplayTest | Event V1 + headers | V2 consumer map và process idempotent |
| LegacyCheckpointTest | Checkpoint V1 | V2 resume không skip/duplicate |
| OldReaderNewDataTest | V2 write dưới rollout | V1 đọc được nếu rollback còn yêu cầu |
| SecurityNegativeTests | Tampered/unknown payload | Fail-safe, không deserialize tùy tiện |

### 27.3. Khi một test thất bại

Giả sử JSON V1 có `status="PENDING_SETTLEMENT"` nhưng domain enum V2 chỉ còn `PENDING`/`SETTLED`.

Quy trình:
1. Xác định trạng thái V1 từng có ý nghĩa gì.
2. Không tự map thành `SETTLED` để test pass.
3. Phối hợp owner nghiệp vụ xác định mapping.
4. Cập nhật adapter/migration có version.
5. Thêm fixture và assertion cho cả status hợp lệ/lỗi.
6. Kiểm tra historical records và event replay.
7. Ghi deadline nếu adapter chỉ là biện pháp tạm.
8. Chạy lại test trên JDK/framework target.

### 27.4. Nếu V1/V2 chạy song song

Có thể cần:
- DB expand schema trước.
- V2 dual-read legacy fields và new fields.
- Kafka producer không gửi schema mà consumer V1 không hiểu.
- Versioned Redis cache/session strategy.
- Canary và metric cho legacy decode.
- Chốt mốc forward-only khi không thể rollback.

Một bộ test chỉ chạy với V2 không thay thế được thử nghiệm mixed-version.

## 28. Checklist kiểm thử dữ liệu lịch sử

- [ ] Đã liệt kê các stores: DB, files, object store, broker, cache/session và checkpoints.
- [ ] Đã biết producer versions, serializers, schema histories và retention.
- [ ] Có fixtures **thực sự tạo bởi phiên bản cũ**; không regen bằng V2 khi test fail.
- [ ] Có checksum/provenance và expected business interpretation.
- [ ] Fixtures synthetic hoặc đã sanitize theo policy, không chứa secret/PII.
- [ ] Đã định nghĩa V2-read-V1 và khi cần V1-read-V2.
- [ ] Đã chạy test trên JDK/framework/codec mục tiêu.
- [ ] Đã test qua production reader/mapping path, không chỉ raw parser.
- [ ] Đã test missing/null/unknown fields và enum legacy.
- [ ] Đã test amount precision/scale/minor unit và leading-zero identifiers.
- [ ] Đã test charset/Unicode, ISO dates, timezone và DST edge cases.
- [ ] Nếu dùng Java serialization, đã kiểm `serialVersionUID`, class names và security filters.
- [ ] Không deserialize untrusted bytes bằng Java native serialization mà thiếu kiểm soát.
- [ ] Đã restore DB V1 snapshot trong môi trường độc lập.
- [ ] Đã test migrations, row counts, constraints và domain invariants.
- [ ] Đã dùng database engine đủ đại diện cho production.
- [ ] Đã test Avro/Protobuf writer-reader schema hoặc JSON/XML contract.
- [ ] Đã replay event V1 và kiểm idempotency/DLQ/checkpoints.
- [ ] Đã test cache/session compatibility hoặc invalidation policy.
- [ ] Đã xác minh encryption/signature và không bỏ qua validation.
- [ ] Đã thử dữ liệu V2 bằng V1 reader nếu rollback/rolling deployment cần.
- [ ] Có ngưỡng cảnh báo deserialize failures và business data mismatch.
- [ ] Có plan canary, rollback hoặc forward-only migration được phê duyệt.
- [ ] Có owner cho legacy adapters và điều kiện loại bỏ sau retention.
- [ ] Đã lưu evidence khi kết luận tương thích; không chỉ “test xanh”.

## 29. Tài liệu tham khảo

Các nguồn sau giúp đối chiếu API và quy tắc tương thích theo phiên bản thực dùng:

- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html): serialized class descriptors và compatibility.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): cơ chế ObjectInputFilter.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter context cho dữ liệu serialized.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ JDK 18.
- [Java Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `OffsetDateTime`, `LocalDateTime`.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): JSON serialization và polymorphic type handling.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): writer-reader schema resolution.
- [Protocol Buffers — Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating): field numbers, unknown fields và schema evolution.
- [Flyway Documentation](https://documentation.red-gate.com/fd): versioned DB migrations.
- [Liquibase Documentation](https://docs.liquibase.com/): database change tracking.
- [Testcontainers for Java](https://java.testcontainers.org/): kiểm thử với database/broker containers.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): API/ORM/XML binding migration.
- [PostgreSQL Data Types](https://www.postgresql.org/docs/current/datatype.html): date/time, numeric và storage semantics khi dùng PostgreSQL.

Các đường dẫn là nguồn định hướng. Khi thực hiện migration, dùng **tài liệu của đúng JDK, framework, serializer, database và schema registry versions** đã pin. Không suy từ một release mới rằng cùng behavior được bảo đảm trên release cũ.

## 30. Kết luận

**Kiểm thử dữ liệu đã lưu từ phiên bản trước là bài kiểm tra khả năng giữ hợp đồng của hệ thống qua thời gian.** Một phiên bản mới tự ghi rồi tự đọc thành công chưa chứng minh nó hiểu dữ liệu lịch sử. Cần những fixtures thực sự do phiên bản cũ tạo, có provenance và expected business meanings, để kiểm tra đúng chiều **old writer → new reader**, cùng chiều ngược lại khi rollback hoặc rolling deployment đòi hỏi.

Quy trình vững chắc là **kiểm kê dữ liệu/retention → tạo và đóng băng fixtures V1 → định nghĩa compatibility matrix → kiểm thử codec, ORM, schema, event, cache và checkpoints → xác minh domain invariants → thử mixed-version/rollback → canary và theo dõi lỗi dữ liệu**. Khi những phép thử đó được tích hợp vào regression suite, nhóm có thể nâng Java/Jakarta/framework mà không làm mất khả năng đọc những thông tin đã tích lũy từ phiên bản trước và không đánh đổi tính toàn vẹn dữ liệu để đạt một lần build xanh.
