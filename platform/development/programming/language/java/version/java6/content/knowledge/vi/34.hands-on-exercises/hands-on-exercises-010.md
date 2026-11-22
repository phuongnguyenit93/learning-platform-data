# Thực hành: Xử lý XML lớn bằng StAX với giới hạn tài nguyên

## Giới thiệu và mục tiêu

Khi ứng dụng Java cần xử lý XML chứa hàng nghìn đến hàng triệu phần tử, việc dựng cả cây DOM hoặc tích lũy mọi record vào một `List` có thể tiêu thụ nhiều RAM. **StAX (Streaming API for XML)** cho phép ứng dụng tự kéo sự kiện XML tuần tự bằng `XMLStreamReader.next()`, xác minh schema và xử lý từng item mà không giữ toàn bộ tài liệu.

**Nhưng streaming không đồng nghĩa an toàn tuyệt đối.** XML không tin cậy có thể chứa DTD/external entities, text cực dài, hàng triệu phần tử rỗng, attributes khổng lồ, depth bất thường, compressed bombs và network streams không kết thúc. Vì vậy bài này kết hợp **XXE hardening, input byte cap, event/record/depth/attribute/text quotas, thời gian, schema validation, resource ownership và transaction boundary**.

Sau khi học, bạn có thể:

1. Chọn StAX thay vì DOM khi dữ liệu quá lớn để giữ dạng cây.
2. Hiểu luồng `START_DOCUMENT`, `START_ELEMENT`, `CHARACTERS`, `CDATA`, `SPACE`, `END_ELEMENT`, `DTD`, `ENTITY_REFERENCE` và `END_DOCUMENT`.
3. Cấu hình `XMLInputFactory` chặn DTD/external entity resolution theo hướng dẫn hiện hành của OWASP và Oracle.
4. Viết một `InputStream` wrapper từ chối tài liệu vượt **maxBytes** trước khi parser tiếp tục đọc.
5. Giới hạn `maxRecords`, `maxEvents`, `maxDepth`, `maxAttributes`, `maxAttributeChars`, `maxFieldChars`, `maxTextChars` và `maxMillis`.
6. Dùng `getTextCharacters()`, `getTextStart()`, `getTextLength()` để tránh nối text không giới hạn.
7. Duy trì một state machine chỉ giữ một item XML tại một thời điểm.
8. Kiểm tra cấu trúc XML, namespace, thứ tự fields, type và giá trị dữ liệu trước khi chấp nhận record.
9. Xử lý lỗi quota, XMLStreamException, file bị cắt, I/O và timeouts.
10. Đóng **cả reader và underlying stream** trong đường thành công/lỗi.
11. Chạy ví dụ Java 17+ tạo và nhập **10.000 records**, nhận 15 dòng stdout xác định.
12. Thiết kế ingestion thật với bounded batching, backpressure, staging, idempotency và rollback.
13. Nhận biết giới hạn nội tại: **một StAX provider có thể buffer text token trước khi trả event**, do đó app-level quotas không phải bằng chứng heap luôn O(1).

**Nền tảng:** `javax.xml.stream` thuộc module **`java.xml`**, là API chuẩn vẫn còn hỗ trợ trong Java 17 và Java SE 26. Ví dụ được **biên dịch và chạy trên OpenJDK 24.0.2 bằng `javac --release 17`**. Bài chỉ dùng kiến thức và thiết lập còn áp dụng, không dựa vào cấu hình bảo mật mặc định của những parser legacy.

---

## 1. Bài toán XML lớn và cách giải quyết

Input mẫu:

~~~xml
<catalog>
  <item id="1">
    <name>Java</name>
    <amount>12</amount>
  </item>
  <item id="2">
    <name>Java</name>
    <amount>12</amount>
  </item>
</catalog>
~~~

Nếu mã đọc toàn bộ file:

~~~java
// PHẢN VÍ DỤ cho XML rất lớn.
String xml = java.nio.file.Files.readString(path);
java.util.List<String> allItems = new java.util.ArrayList<>();
~~~

bộ nhớ ứng dụng có thể tăng theo kích thước tài liệu. Mặt khác, có thể dùng StAX để:

~~~text
Nguồn InputStream
        │
        ▼
Byte cap, network I/O timeout
        │
        ▼
XMLInputFactory đã harden
        │
        ▼
XMLStreamReader.next()
        │
        ▼
Event counter, depth, attribute checks
        │
        ▼
Bounded text accumulator của một item
        │
        ▼
Validate và xử lý item khi END_ELEMENT
        │
        ▼
Xóa state item và tiếp tục
~~~

Về mặt ứng dụng, số item không làm tăng kích thước List vì không có List. Tuy nhiên, parser cũng có buffer riêng; với một token quá dài, parser có thể đã allocate dữ liệu trước khi quota của ứng dụng được kiểm tra. **Bảo vệ nhiều tầng** là bắt buộc nếu XML đến từ client/đối tác không tin cậy.

### 1.1. DOM, SAX và StAX

| Công cụ | Mô hình | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| DOM | Dựng tree | Truy cập ngẫu nhiên và sửa node | Giữ cây trong bộ nhớ |
| SAX | Push callbacks | Xử lý tuần tự, tránh cả cây | Parser điều khiển nhịp callback |
| StAX | Pull events | Ứng dụng chủ động gọi next(), dễ phối hợp backpressure | Tự xây state machine, vẫn phải harden |
 
Không có công cụ nào tự bảo đảm an toàn trước mọi XML DoS. DOM có thể hoàn toàn hợp lý cho XML nhỏ; StAX thuận tiện cho tài liệu lớn cần xử lý tuần tự; SAX cũng phù hợp nếu handler không giữ cả tài liệu.

### 1.2. StAX là pull parser

~~~java
XMLStreamReader reader = factory.createXMLStreamReader(input);
while (reader.hasNext()) {
    int event = reader.next();
    // Xử lý event hiện tại.
}
~~~

Trên `XMLStreamReader` event hiện tại tồn tại ngay sau khi tạo reader (thường là START_DOCUMENT). Vì vậy một parser tổng quát có thể bắt đầu với `getEventType()`, rồi gọi `next()` khi chưa đến END_DOCUMENT. Không được ngầm cho rằng một lần next tương ứng một record hoặc một đoạn text trọn vẹn.

---

## 2. Threat model: XML hợp lệ vẫn có thể tiêu tốn tài nguyên

### 2.1. XXE và DTD

~~~xml
<!DOCTYPE catalog [
  <!ENTITY external SYSTEM "file:///some/local/file">
]>
<catalog>&external;</catalog>
~~~

Nếu resolver được phép tải entity, nó có thể truy cập local files hoặc network. XXE có thể gây local file disclosure, SSRF hoặc cạn tài nguyên. Với bài toán không cần DTD, cấu hình **cấm DTD processing** và **cấm external entities** là đúng hướng; resolver cũng từ chối mọi external reference.

### 2.2. XML quá nhiều elements

Một file có hàng triệu `<item>` hoặc hàng triệu empty elements khiến CPU/time cao dù textChars gần bằng 0. Vì thế `maxTextChars` đơn lẻ không đủ; cần `maxEvents`, `maxRecords`, input bytes và giới hạn runtime toàn hệ thống.

### 2.3. XML quá sâu

~~~xml
<a><b><c><d><e><f>...</f></e></d></c></b></a>
~~~

Depth lớn có thể gây overhead parser hoặc làm ứng dụng đệ quy tràn stack. Code bài dùng **bộ đếm depth**, không build tree; khi vượt `maxDepth`, nó từ chối ngay.

### 2.4. Text token và attributes quá lớn

`<name>` chứa một triệu ký tự sẽ tiêu thụ memory nếu `StringBuilder` tích lũy không giới hạn. `<item>` có hàng nghìn attributes cũng tốn parser resources. Đặt `maxFieldChars`, `maxTextChars`, `maxAttributes`, `maxAttributeChars`, và khi cần **provider-specific XML processing limits**. Input byte cap là phòng tuyến trước khi parser có thể tiêu thụ quá nhiều bytes.

### 2.5. Compressed bomb và slow input

Một file gzip nhỏ có thể giải nén thành XML rất lớn; network peer cũng có thể gửi từng byte rất chậm. Đặt quota trên **decompressed XML stream** bên cạnh compressed bytes/ratio; set **network read/response timeouts** bên ngoài StAX; dùng cancellation và concurrent-jobs limit. Không tin `Content-Length` đơn thuần.

---

## 3. Ma trận quota

Trong ví dụ, cấu hình `Limits` có các giới hạn sau:

| Quota | Giá trị demo | Đơn vị | Chặn ở đâu |
| --- | ---: | --- | --- |
| `maxBytes` | 1.000.000 | raw XML bytes | Bounded InputStream |
| `maxRecords` | 10.000 | item elements | START_ELEMENT item |
| `maxEvents` | 120.000 | XML events | Mỗi vòng parse |
| `maxTextChars` | 100.000 | UTF-16 chars | Mọi text event |
| `maxDepth` | 3 | nesting levels | START_ELEMENT |
| `maxAttributes` | 1 | attributes/element | START_ELEMENT |
| `maxAttributeChars` | 8 | UTF-16 chars/value | Khi đọc attribute |
| `maxFieldChars` | 16 | UTF-16 chars/field | Trước append |
| `maxMillis` | 60.000 | milliseconds | Sau mỗi event |

Đây là **ngưỡng minh họa của XML `<catalog>`**, không phải các con số mặc định phù hợp với mọi dịch vụ. Một schema hóa đơn phức tạp có thể cần nhiều attributes hơn, nhưng vẫn phải có hạn mức được đánh giá theo SLA, request concurrency và memory/CPU budget.

**Một quota không thay thế quota khác:**

- `maxBytes` không kiểm soát số ký tự tạo ra bởi entity expansion nếu parser cho phép DTD.
- `maxTextChars` không kiểm soát hàng triệu elements không có text.
- `maxDepth` không kiểm soát attribute count.
- `maxRecords` không kiểm soát text rất dài trong một item.
- `maxMillis` kiểm tra sau mỗi event, **không ngắt `next()` đang block** vì mạng.
- `maxFieldChars` kiểm tra trước StringBuilder.append nhưng **parser có thể đã buffer token**.

Khi có nhiều request đồng thời, per-document caps cần thêm **global concurrency/memory limits**.

### 3.1. Giới hạn và overflow

Một phép cộng `used + current > limit` có thể overflow nếu used/current quá lớn. Nên so theo dạng:

~~~java
if (current > limit - used) {
    throw new LimitExceeded("quota");
}
~~~

Cách này chỉ hợp lệ khi contract đã bảo đảm `limit >= used` và các giá trị không âm. Trong production, validate toàn bộ Limits là positive trước khi dùng.

### 3.2. Không để tài liệu tự xin thêm quota

Input `<catalog maxRecords="999999999">` không được phép quyết định chính quota của server. Giới hạn phải đến từ **server configuration, authenticated account policy, resource budgets và schema contract**.

---

## 4. Cấu hình XMLInputFactory an toàn

### 4.1. Built-in default provider

~~~java
XMLInputFactory factory = XMLInputFactory.newDefaultFactory();
~~~

`newDefaultFactory()` tồn tại từ Java 9, chọn system-default **built-in implementation** thay vì dựa vào provider lookup của `newFactory()/newInstance()`. Điều đó giúp ví dụ Java17+ dễ tái lập. Nếu dùng provider khác trong thực tế, phải xác minh hardening, behavior và memory limits riêng.

### 4.2. Tắt DTD và external entities

~~~java
factory.setProperty(XMLInputFactory.SUPPORT_DTD, false);
factory.setProperty(
    XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
~~~

Theo OWASP và Oracle JAXP Security Guide, cần **cả hai settings** khi không cần DTD. Nếu một required property không được implementation hỗ trợ, không catch lỗi rồi âm thầm parse XML chưa được bảo vệ: **fail closed**.

### 4.3. XMLResolver từ chối external references

~~~java
factory.setXMLResolver(
    (publicId, systemId, baseURI, namespace) -> {
        throw new XMLStreamException("external resolution forbidden");
    });
~~~

**Không return null để biểu thị deny**; điều đó có thể nhường cho fallback/default resolution của provider.

### 4.4. Kiểm tra settings đã áp dụng

~~~java
if (!Boolean.FALSE.equals(
            factory.getProperty(XMLInputFactory.SUPPORT_DTD))
        || !Boolean.FALSE.equals(
            factory.getProperty(
                XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES))) {
    throw new IllegalStateException("required StAX hardening not applied");
}
~~~

Provider vẫn có thể có bug hoặc semantics khác; cần **security integration tests** trên đúng JVM triển khai.

### 4.5. DTD disabled không đồng nghĩa luôn reject DOCTYPE

OWASP lưu ý một StAX provider có thể **bỏ qua DTD** khi SUPPORT_DTD=false mà không tự phát lỗi. Trong code bài, **nếu xuất hiện DTD event thì chủ động reject**; negative test DTD đã pass trên JDK24. Nhưng điều đó **không chứng minh mọi implementation/JDK đều báo DTD event**.

Nếu business policy yêu cầu **không chấp nhận bất kỳ DOCTYPE nào**, hãy dùng cấu hình deny ở **parser/JDK** được kiểm chứng. JDK hiện hành có property **`jdk.xml.dtd.support=deny`**, nhưng Oracle JAXP Guide nêu quan hệ precedence: khi StAX `SUPPORT_DTD=false` đã set, setting đó có thể được áp dụng trước system DTD property. Đừng copy flag từ JDK mới rồi giả định nó có cùng behavior trên Java17. Test với đúng runtime/provider và XML DTD fixtures.

### 4.6. Đừng copy FEATURE_SECURE_PROCESSING của DOM/SAX sang StAX

`XMLConstants.FEATURE_SECURE_PROCESSING` không phải property bảo mật chung được StAX XMLInputFactory hỗ trợ như DOM/SAX. Hãy dùng StAX properties, resolver, JAXP/provider processing limits và input quotas. Nếu còn dùng XML Schema validation hoặc XSLT, cũng phải harden **SchemaFactory/TransformerFactory** riêng.

---

## 5. Event cursor và xử lý text có giới hạn

### 5.1. Thứ tự events minh họa

~~~xml
<catalog><item id="1"><name>Java</name><amount>12</amount></item></catalog>
~~~

~~~text
START_DOCUMENT
START_ELEMENT catalog
START_ELEMENT item
START_ELEMENT name
CHARACTERS "Java"
END_ELEMENT name
START_ELEMENT amount
CHARACTERS "12"
END_ELEMENT amount
END_ELEMENT item
END_ELEMENT catalog
END_DOCUMENT
~~~

Một parser có thể chia đoạn text thành **nhiều CHARACTERS events**, và có thể phát CDATA riêng. Đừng dựa trên “mỗi field = một event”.

### 5.2. Tránh getElementText với field không có hạn mức

~~~java
// PHẢN VÍ DỤ: tạo String trước khi kiểm tra length.
String note = reader.getElementText();
if (note.length() > maxFieldChars) {
    throw new IllegalArgumentException("too long");
}
~~~

`getElementText()` gom toàn bộ text của một leaf element. Nó hữu ích khi leaf đã biết nhỏ nhưng rủi ro nếu input không tin cậy và quá dài.

Thay thế:

~~~java
int count = reader.getTextLength();
if (count > maxFieldChars - builder.length()) {
    throw new LimitExceeded("maxFieldChars");
}
builder.append(reader.getTextCharacters(),
        reader.getTextStart(), count);
~~~

`getTextCharacters()` trả array transient của **event hiện tại**; không mutate hoặc giữ reference sau khi reader tiến qua event khác. Với từng event, copy **chỉ khi quota còn đủ**.

### 5.3. nextTag khác với next

`nextTag()` bỏ qua whitespace/comments/PI phù hợp và muốn thấy START_ELEMENT/END_ELEMENT. Gặp non-whitespace text có thể ném XMLStreamException. Do đó với tài liệu có field text/mixed content, dùng `next()` và switch events minh bạch hơn.

### 5.4. Text, CDATA, entities và Unicode

- `CHARACTERS`/`CDATA`/`SPACE` đều phải đóng góp vào text quotas.
- `ENTITY_REFERENCE` event được demo reject vì không muốn resolve entity tùy biến.
- Predefined XML references như `&amp;` là một phần XML bình thường; cần kiểm thử cách provider chia text.
- `StringBuilder.length()` và `getTextLength()` đo **UTF-16 code units**, khác với bytes UTF-8 hoặc số Unicode code points. Emoji có thể chiếm hai UTF-16 units.
- Không dùng `getText()` để giữ tất cả text của cả tài liệu.
- Nếu đang đọc một text event rất lớn, parser có thể đã allocate buffer trước application check; cần defense-in-depth.

---

## 6. Thiết kế state machine cho schema thực hành

Bài demo nhận XML dạng:

~~~xml
<catalog>
  <item id="1">
    <name>Java</name>
    <amount>12</amount>
  </item>
</catalog>
~~~

Contract:

1. Chỉ có root `catalog` không attribute.
2. `item` là con trực tiếp root, có đúng một attribute tên `id` và giá trị không blank.
3. `item` có hai field theo thứ tự: `name`, rồi `amount`.
4. Không có namespace ngoài contract, không có tag lạ.
5. `name` là text không blank, giới hạn per-field.
6. `amount` là `int` thập phân không âm.
7. Không cho non-whitespace text ngoài field.
8. Chỉ trả thành công sau khi đọc tới END_DOCUMENT và root đóng đúng.

~~~text
START_DOCUMENT: depth=0
<catalog>: depth=1
<item>: depth=2, openedRecords++
<name>: depth=3, bắt đầu bounded StringBuilder
CHARACTERS/CDATA: kiểm tra quota trước append
</name>: lấy name
<amount>: depth=3
CHARACTERS/CDATA: kiểm tra quota trước append
</amount>: lấy amountText
</item>: validate, parse int, Math.addExact, records++
</catalog>: depth=0 sau END_ELEMENT
END_DOCUMENT: verify rootSeen/rootClosed/depth rồi return
~~~

**Chỉ giữ dữ liệu item hiện tại.** Khi `</item>` hoàn tất, code cộng tổng rồi bỏ state. Nếu hệ thống ghi mỗi record xuống database, phải thiết kế **transaction/staging**, vì file có thể malformed ở cuối sau khi nhiều items đã được ghi.

### 6.1. Không bỏ qua tag lạ âm thầm

~~~xml
<catalog><unexpected/></catalog>
~~~

Ví dụ **reject** thay vì bỏ tag rồi báo import thành công. Nếu business cho phép các extension tags, cần whitelist và skip-subtree parser có quotas vẫn đếm mọi event/depth/text.

### 6.2. Namespace

Demo chỉ cho XML không có namespace để code nhỏ và dễ học. XML thực tế cần validate `QName` gồm **namespace URI + local name**, không chỉ `getLocalName()`. Prefix có thể khác nhưng URI mới là thông tin định danh namespace.

---

## 7. Code Java 17+ đầy đủ và đã kiểm chứng

**Tên file:** `BoundedStaxImport.java`

Source tạo file XML tạm chứa 10.000 items, parse theo stream, kiểm soát quotas, chạy negative cases và dọn file. Không gọi `Files.readAllBytes`, không tạo DOM, không giữ tất cả records trong List.

~~~java
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicLong;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamConstants;
import javax.xml.stream.XMLStreamException;
import javax.xml.stream.XMLStreamReader;

public final class BoundedStaxImport {
    record Limits(long maxBytes, long maxRecords, long maxEvents,
                  long maxTextChars, int maxDepth, int maxAttributes,
                  int maxAttributeChars, int maxFieldChars, long maxMillis) {}

    record Result(long records, long textChars, int maxDepthSeen,
                  long inputBytes, long amountSum) {}

    static final class LimitExceeded extends RuntimeException {
        LimitExceeded(String name) { super(name); }
    }

    static final class CountingLimitedInput extends FilterInputStream {
        private final long maximum;
        long bytes;

        CountingLimitedInput(InputStream delegate, long maximum) {
            super(delegate);
            this.maximum = maximum;
            if (maximum <= 0) throw new IllegalArgumentException("maxBytes");
        }

        @Override public int read() throws IOException {
            int next = in.read();
            if (next < 0) return -1;
            if (bytes >= maximum) throw new LimitExceeded("maxBytes");
            bytes++;
            return next;
        }

        @Override public int read(byte[] b, int off, int len)
                throws IOException {
            if (len == 0) return 0;
            long left = maximum - bytes;
            int requested = (int) Math.min((long) len, left + 1);
            int read = in.read(b, off, requested);
            if (read < 0) return -1;
            if (read > left) throw new LimitExceeded("maxBytes");
            bytes += read;
            return read;
        }

        @Override public long skip(long n) throws IOException {
            byte[] scratch = new byte[4096];
            long skipped = 0;
            while (skipped < n) {
                int read = read(scratch, 0,
                        (int) Math.min(scratch.length, n - skipped));
                if (read < 0) break;
                skipped += read;
            }
            return skipped;
        }
        @Override public boolean markSupported() { return false; }
        @Override public synchronized void mark(int readlimit) {}
        @Override public synchronized void reset() throws IOException {
            throw new IOException("mark/reset disabled");
        }
    }

    static XMLInputFactory hardenedFactory() {
        // Since Java 9, default = built-in provider, not provider lookup.
        XMLInputFactory f = XMLInputFactory.newDefaultFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
            throw new XMLStreamException("external resolution forbidden");
        });
        if (!Boolean.FALSE.equals(f.getProperty(XMLInputFactory.SUPPORT_DTD))
                || !Boolean.FALSE.equals(
                        f.getProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES))) {
            throw new IllegalStateException("required StAX hardening not applied");
        }
        return f;
    }

    static Result parse(InputStream ownedInput, Limits limits) throws Exception {
        long begin = System.nanoTime();
        long records = 0;
        long opened = 0;
        long events = 0;
        long textChars = 0;
        long sum = 0;
        int depth = 0;
        int maxDepthSeen = 0;
        String itemId = null;
        String currentField = null;
        String name = null;
        String amountText = null;
        StringBuilder fieldValue = new StringBuilder();
        boolean rootSeen = false, rootClosed = false;
        boolean seenName = false, seenAmount = false;
        try (CountingLimitedInput input =
                    new CountingLimitedInput(ownedInput, limits.maxBytes())) {
            XMLStreamReader r = null;
            try {
                r = hardenedFactory().createXMLStreamReader(input);
                while (true) {
                    if ((System.nanoTime() - begin) / 1_000_000L >
                            limits.maxMillis()) {
                        throw new LimitExceeded("maxMillis");
                    }
                    events++;
                    if (events > limits.maxEvents()) {
                        throw new LimitExceeded("maxEvents");
                    }
                    int event = r.getEventType();
                    switch (event) {
                        case XMLStreamConstants.DTD ->
                            throw new LimitExceeded("noDTD");
                        case XMLStreamConstants.ENTITY_REFERENCE ->
                            throw new LimitExceeded("noEntityReference");
                        case XMLStreamConstants.START_ELEMENT -> {
                            depth++;
                            if (depth > limits.maxDepth()) {
                                throw new LimitExceeded("maxDepth");
                            }
                            maxDepthSeen = Math.max(maxDepthSeen, depth);
                            String ns = r.getNamespaceURI();
                            if (ns != null && !ns.isEmpty()) {
                                throw new LimitExceeded("unexpectedNamespace");
                            }
                            int attrs = r.getAttributeCount();
                            if (attrs > limits.maxAttributes()) {
                                throw new LimitExceeded("maxAttributes");
                            }
                            for (int j = 0; j < attrs; j++) {
                                if (r.getAttributeValue(j).length()
                                        > limits.maxAttributeChars()) {
                                    throw new LimitExceeded("maxAttributeChars");
                                }
                            }
                            String element = r.getLocalName();
                            if (depth == 1) {
                                if (rootSeen || !"catalog".equals(element)) {
                                    throw new LimitExceeded("invalidRoot");
                                }
                                rootSeen = true;
                                if (attrs != 0) throw new LimitExceeded("rootAttributes");
                            } else if (depth == 2) {
                                if (!"item".equals(element) || currentField != null) {
                                    throw new LimitExceeded("invalidItem");
                                }
                                opened++;
                                if (opened > limits.maxRecords()) {
                                    throw new LimitExceeded("maxRecords");
                                }
                                if (attrs != 1 || !"id".equals(r.getAttributeLocalName(0))) {
                                    throw new LimitExceeded("invalidItemId");
                                }
                                itemId = r.getAttributeValue(0);
                                if (itemId.isBlank()) throw new LimitExceeded("blankId");
                                name = null;
                                amountText = null;
                                seenName = false;
                                seenAmount = false;
                            } else if (depth == 3) {
                                if (attrs != 0 || currentField != null) {
                                    throw new LimitExceeded("invalidField");
                                }
                                if ("name".equals(element) && !seenName && !seenAmount) {
                                    currentField = "name";
                                    seenName = true;
                                } else if ("amount".equals(element) && seenName && !seenAmount) {
                                    currentField = "amount";
                                    seenAmount = true;
                                } else {
                                    throw new LimitExceeded("invalidFieldOrder");
                                }
                                fieldValue.setLength(0);
                            } else {
                                throw new LimitExceeded("unexpectedDepth");
                            }
                        }
                        case XMLStreamConstants.CHARACTERS,
                             XMLStreamConstants.CDATA,
                             XMLStreamConstants.SPACE -> {
                            int count = r.getTextLength();
                            if (count > limits.maxTextChars() - textChars) {
                                throw new LimitExceeded("maxTextChars");
                            }
                            textChars += count;
                            if (currentField != null) {
                                if (count > limits.maxFieldChars()
                                        - fieldValue.length()) {
                                    throw new LimitExceeded("maxFieldChars");
                                }
                                fieldValue.append(r.getTextCharacters(),
                                        r.getTextStart(), count);
                            } else if (!r.isWhiteSpace()) {
                                throw new LimitExceeded("textOutsideFields");
                            }
                        }
                        case XMLStreamConstants.END_ELEMENT -> {
                            String element = r.getLocalName();
                            if (depth == 3) {
                                if (!element.equals(currentField)) {
                                    throw new LimitExceeded("invalidEndField");
                                }
                                if ("name".equals(element)) {
                                    name = fieldValue.toString();
                                } else {
                                    amountText = fieldValue.toString();
                                }
                                fieldValue.setLength(0);
                                currentField = null;
                            } else if (depth == 2) {
                                if (!"item".equals(element) || itemId == null
                                        || !seenName || !seenAmount
                                        || name == null || name.isBlank()
                                        || amountText == null) {
                                    throw new LimitExceeded("incompleteItem");
                                }
                                try {
                                    int amount = Integer.parseInt(amountText);
                                    if (amount < 0) throw new NumberFormatException();
                                    sum = Math.addExact(sum, amount);
                                } catch (NumberFormatException | ArithmeticException e) {
                                    throw new LimitExceeded("invalidAmount");
                                }
                                records++;
                                itemId = null;
                            } else if (depth == 1) {
                                if (!"catalog".equals(element)) {
                                    throw new LimitExceeded("invalidEndRoot");
                                }
                                rootClosed = true;
                            }
                            depth--;
                        }
                        default -> {
                            // START_DOCUMENT, END_DOCUMENT, comments and PI.
                        }
                    }
                    if (event == XMLStreamConstants.END_DOCUMENT) break;
                    if (!r.hasNext()) break;
                    r.next();
                }
                if (!rootSeen || !rootClosed || depth != 0) {
                    throw new LimitExceeded("incompleteDocument");
                }
                return new Result(records, textChars, maxDepthSeen, input.bytes, sum);
            } finally {
                if (r != null) r.close();
            }
        }
    }

    static Result parseText(String xml, Limits limits) throws Exception {
        return parse(new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8)),
                limits);
    }

    static boolean hasMarker(Throwable t, String marker) {
        int guard = 0;
        while (t != null && guard++ < 12) {
            if (t instanceof LimitExceeded && marker.equals(t.getMessage())) return true;
            if (t.getMessage() != null && t.getMessage().contains(marker)) return true;
            if (t instanceof XMLStreamException xse && xse.getNestedException() != null
                    && xse.getNestedException() != t.getCause()) {
                if (hasMarker(xse.getNestedException(), marker)) return true;
            }
            t = t.getCause();
        }
        return false;
    }

    static boolean rejects(Path p, Limits limits, String marker) {
        try {
            parse(Files.newInputStream(p), limits);
            return false;
        } catch (Exception | LinkageError ex) {
            return hasMarker(ex, marker);
        }
    }

    static boolean rejectsText(String xml, Limits limits, String marker) {
        try {
            parseText(xml, limits);
            return false;
        } catch (Exception | LinkageError ex) {
            return hasMarker(ex, marker);
        }
    }

    static Limits standard() {
        return new Limits(
                1_000_000L, 10_000L, 120_000L,
                100_000L, 3, 1, 8, 16, 60_000L);
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("stax-items-", ".xml");
        try {
            try (Writer w = Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                w.write("<catalog>");
                for (int i = 1; i <= 10_000; i++) {
                    w.write("<item id=\"" + i
                            + "\"><name>Java</name><amount>12</amount></item>");
                }
                w.write("</catalog>");
            }
            Limits limits = standard();
            Result result = parse(Files.newInputStream(file), limits);
            System.out.println("records=" + result.records());
            System.out.println("amountSum=" + result.amountSum());
            System.out.println("textChars=" + result.textChars());
            System.out.println("maxDepth=" + result.maxDepthSeen());
            System.out.println("bytesWithinLimit="
                    + (result.inputBytes() <= limits.maxBytes()));

            System.out.println("recordsLimitRejected=" + rejects(file,
                    new Limits(1_000_000, 100, 120_000, 100_000, 3, 1, 8, 16, 60_000),
                    "maxRecords"));
            System.out.println("depthLimitRejected=" + rejects(file,
                    new Limits(1_000_000, 10_000, 120_000, 100_000, 2, 1, 8, 16, 60_000),
                    "maxDepth"));
            System.out.println("textLimitRejected=" + rejects(file,
                    new Limits(1_000_000, 10_000, 120_000, 100_000, 3, 1, 8, 3, 60_000),
                    "maxFieldChars"));
            System.out.println("byteLimitRejected=" + rejects(file,
                    new Limits(100, 10_000, 120_000, 100_000, 3, 1, 8, 16, 60_000),
                    "maxBytes"));
            System.out.println("eventLimitRejected=" + rejects(file,
                    new Limits(1_000_000, 10_000, 100, 100_000, 3, 1, 8, 16, 60_000),
                    "maxEvents"));
            String tooManyAttributes =
                    "<catalog><item id=\"1\" extra=\"x\"><name>Java</name>" +
                    "<amount>12</amount></item></catalog>";
            System.out.println("attributeLimitRejected=" + rejectsText(
                    tooManyAttributes, limits, "maxAttributes"));
            String unexpected =
                    "<catalog><unexpected/></catalog>";
            System.out.println("unexpectedElementRejected=" + rejectsText(
                    unexpected, limits, "invalidItem"));
            String doctype =
                    "<!DOCTYPE catalog [<!ENTITY external SYSTEM " +
                    "\"file:///definitely-not-an-existing-file\">]>" +
                    "<catalog></catalog>";
            System.out.println("doctypeRejected=" + rejectsText(
                    doctype, limits, "noDTD"));
            String malformed =
                    "<catalog><item id=\"1\"><name>Java</name>" +
                    "<amount>12</amount></catalog>";
            boolean malformedRejected;
            try {
                parseText(malformed, limits);
                malformedRejected = false;
            } catch (XMLStreamException ex) {
                malformedRejected = true;
            }
            System.out.println("malformedRejected=" + malformedRejected);
            System.out.println("boundedMemoryModel=true");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

### 7.1. Biên dịch và chạy

Lưu file đúng tên **`BoundedStaxImport.java`**, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 BoundedStaxImport.java
java BoundedStaxImport
~~~

Không cần database/Maven/Gradle. `XMLInputFactory` nằm trong **module `java.xml`**; ứng dụng JPMS cần `requires java.xml` trong `module-info.java`.

### 7.2. Stdout chính xác

~~~text
records=10000
amountSum=120000
textChars=60000
maxDepth=3
bytesWithinLimit=true
recordsLimitRejected=true
depthLimitRejected=true
textLimitRejected=true
byteLimitRejected=true
eventLimitRejected=true
attributeLimitRejected=true
unexpectedElementRejected=true
doctypeRejected=true
malformedRejected=true
boundedMemoryModel=true
~~~

**Đã kiểm chứng thực tế:** `javac 24.0.2 --release 17`, OpenJDK 24.0.2, 15 dòng output khớp chính xác. File XML tạm, Java source/class dùng trong kiểm thử đã được dọn. `boundedMemoryModel=true` chỉ là **nhãn minh họa mô hình giới hạn bộ nhớ ở ứng dụng**, **không phải phép đo heap và không chứng minh O(1) memory của mọi StAX provider**.

---

## 8. Phân tích chương trình

### 8.1. Limits và Result

`Limits` là record chứa quotas. Khi đem vào production, cần validate tất cả quota positive, chống overflow và có policy theo tenant/account; ví dụ demo cố định.

`Result` chỉ giữ năm scalar fields: số records, decoded text chars, max depth, bytes đã đọc, tổng amount. Không giữ 10.000 item objects.

### 8.2. CountingLimitedInput

Ở read(byte[],off,len), wrapper yêu cầu tối đa `remaining + 1` bytes:

~~~java
long left = maximum - bytes;
int requested = (int) Math.min((long) len, left + 1);
int read = in.read(b, off, requested);
if (read > left) throw new LimitExceeded("maxBytes");
bytes += read;
~~~

Nhờ đó input vượt quota bị phát hiện mà không chuyển một lượng bytes khổng lồ cho parser. `read()` và `skip()` cũng được quản lý. Wrapper demo vô hiệu hóa mark/reset để không đọc lại bytes mà làm lệch quota.

Với production, cần kiểm thử thêm **InputStream contract**, validate off/len, negative skip, nguồn blocking và cancellation. Đây là **mẫu học tập** chứ không phải một thư viện general-purpose đã formal verify.

### 8.3. Quota trước khi xử lý

Trong START_ELEMENT:

- Tăng depth, reject nếu quá max.
- Kiểm tra namespace.
- Kiểm tra số attributes và độ dài values.
- Xác định root/item/field đúng schema.
- Khi mở item, tăng opened counter và reject nếu vượt maxRecords.
- Khi mở field, reset StringBuilder.
- Không phát hành record hay gọi database khi schema/quota chưa hợp lệ.

Trong CHARACTERS/CDATA/SPACE:

- Tăng tổng decoded text chars sau khi kiểm tra quota.
- Chỉ append khi đang ở field hợp lệ.
- Reject non-whitespace text ngoài fields.

Trong END_ELEMENT:

- Lấy fieldValue thành name/amountText.
- Khi đóng item: validate, Integer.parseInt, Math.addExact, cộng record.
- Khi đóng root: đánh dấu rootClosed.
- Không giữ collection toàn bộ items.

### 8.4. `Math.addExact` để không wrap tổng số

~~~java
int amount = Integer.parseInt(amountText);
if (amount < 0) throw new NumberFormatException();
sum = Math.addExact(sum, amount);
~~~

Nếu amountText không phải số nguyên hoặc vượt phạm vi int, parser reject. Nếu tổng kiểu long overflow, Math.addExact ném exception và code quy thành invalidAmount. Với số tiền thật, có thể dùng minor currency units hoặc `BigDecimal` với precision/scale policy; tránh dùng `double` để biểu diễn giá tiền.

### 8.5. Close reader và stream

`XMLStreamReader.close()` **giải phóng resources của XML reader nhưng không đóng underlying InputStream** theo Javadoc. Code dùng try-with-resources cho CountingLimitedInput bao quanh try/finally `r.close()`. Với ownership model này, `parse()` **nhận quyền sở hữu và đóng InputStream** dù parse thành công hay thất bại.

Nếu caller sở hữu stream, thiết kế API theo cách khác và ghi contract rõ. Không được ngầm để InputStream mở sau failure (FD/socket leak).

### 8.6. Deadline là kiểm tra hợp tác, không phải hard timeout

`System.nanoTime()` được dùng để đo elapsed milliseconds. Code kiểm tra deadline giữa các events; nó **không thể cắt ngang một `next()`/InputStream.read() đang block**. Khi dùng HTTP/socket, đặt read/response timeout, cancellation và job supervisor ở tầng nguồn.

### 8.7. Chỉ chấp nhận sau khi parse cả tài liệu

Kết quả chỉ được trả sau khi gặp END_DOCUMENT và xác nhận root đã đóng, depth=0. Nếu XML malformed ở cuối, chương trình không trả partial successful Result.

Nhưng nếu adapter production đã ghi DB từng item thì lỗi ở cuối vẫn có thể để lại partial writes. Cần **staging transaction/publish after validation**, hoặc hợp đồng partial import rõ.

---

## 9. Kết quả kiểm thử và ý nghĩa

| Case | Kết quả | Diễn giải |
| --- | --- | --- |
| Valid 10.000 items | records=10000 | Tất cả records được xử lý |
| Tổng | amountSum=120000 | 10.000 × 12 |
| Text | textChars=60000 | Mỗi item 4 + 2 chars |
| Depth | maxDepth=3 | catalog → item → field |
| Bytes | bytesWithinLimit=true | Input nằm dưới 1.000.000 bytes |
| maxRecords=100 | recordsLimitRejected=true | Dừng khi mở item thứ 101 |
| maxDepth=2 | depthLimitRejected=true | Field ở tầng 3 |
| maxFieldChars=3 | textLimitRejected=true | `"Java"` dài 4 |
| maxBytes=100 | byteLimitRejected=true | Quá input size |
| maxEvents=100 | eventLimitRejected=true | Quá nhiều events |
| Item có extra attr | attributeLimitRejected=true | 2 attrs > 1 |
| Unknown tag | unexpectedElementRejected=true | Schema không hợp lệ |
| Input có DTD | doctypeRejected=true | Parser demo/JDK test chặn DTD |
| Malformed closing tag | malformedRejected=true | XMLStreamException |

**Giới hạn của test:** Các cases đã chạy trên JDK 24.0.2, không phải proof về hành vi mọi StAX providers. Cần test runtime thật với DTD/entity fixtures. `boundedMemoryModel=true` chỉ là dòng xác nhận quy ước demo, không có phép đo heap.

### 9.1. Kiểm tra các đường lỗi khác

Khi đưa vào production, bổ sung:

1. Field length ở đúng ngưỡng 16 và ở 17.
2. Byte cap ở đúng file length và file length+1.
3. Nhiều whitespace/CDATA events.
4. `&amp;` và escaped entities chuẩn.
5. Amount âm, nonnumeric, overflow.
6. Root/field thiếu hoặc duplicate.
7. Empty XML và truncated input.
8. Attribute value dài hơn max.
9. Rất nhiều empty tags không có text.
10. Long text token memory pressure.
11. Deep nesting and XML names cực dài.
12. Compressed input ratio.
13. Slow network I/O và cancellation.
14. Nhiều imports đồng thời.
15. Resource close trên exception.

### 9.2. Bảo mật nên được kiểm thử bằng các đầu vào bị giới hạn

Đối với XXE, thử `file:` và HTTP references **trong sandbox không có quyền truy cập bên ngoài**. Không thử tấn công lên production bằng payload không kiểm soát. Mục tiêu test là khẳng định **không có external resource được tải**, không lộ nội dung và process không cạn tài nguyên.

---

## 10. Tích hợp database và backpressure

### 10.1. Callback cho một item

Thay vì cộng amount, importer có thể gọi:

~~~java
// MẢNH MINH HỌA, không thuộc file runnable trên.
interface ItemConsumer {
    void accept(String id, String name, int amount) throws Exception;
}
~~~

Khi đóng `</item>`, sau validation có thể gọi consumer. Nhưng nếu XML lỗi ở cuối, mọi side effects trước đó vẫn tồn tại trừ khi bạn có transaction/staging.

### 10.2. Chính sách import all-or-nothing

Một chiến lược:

~~~text
Open upload → stream parse → validate → write staging rows
       │
       ▼
END_DOCUMENT + all quotas pass?
       ├── NO → rollback/delete staging, report FAILED
       └── YES → publish staging as committed import
~~~

Nếu staging vượt memory/DB budgets, dùng database bounded batch writes chứ không đưa mọi items vào List. Khi số lượng quá lớn để giữ một transaction dài, có thể thiết kế checkpoints/compensation nhưng phải công bố semantics không còn all-or-nothing.

### 10.3. Backpressure

Nếu downstream writer xử lý chậm, parser không nên tiếp tục đưa records vào unbounded queue. Có thể:

- Ghi đồng bộ từng bounded batch.
- Dùng `BlockingQueue` **có dung lượng hữu hạn**.
- Không đọc thêm `next()` nếu queue đầy.
- Có cancellation, timeout và shutdown contract.
- Nếu downstream error, dừng parse và đóng cả stream/reader.

### 10.4. Duplicate IDs

Demo yêu cầu ID không blank nhưng **không kiểm tra trùng ID** vì điều đó có thể cần state tỷ lệ số records. Nếu contract yêu cầu unique IDs:

- Dùng unique constraint trong staging table.
- Dùng disk-backed index.
- Dùng một bounded set nếu maxRecords đủ nhỏ và memory budget có thể chấp nhận.
- Có chính sách rõ cho duplicate: reject, merge hoặc last-wins.

Đừng tạo unbounded HashSet làm mất lợi thế của streaming.

---

## 11. Ngoài parser: compressed files, encoding, concurrency

### 11.1. Compressed bytes vs decompressed bytes

Nếu nguồn là `.gz`:

~~~text
Compressed InputStream
       │
       ▼
Compressed-byte cap (nếu cần)
       │
       ▼
GZIPInputStream
       │
       ▼
Decoded-XML byte cap
       │
       ▼
XMLStreamReader
~~~

Quota decoded-XML byte cap phải nằm **sau** decompressor. Với ZIP phải giới hạn số entries, tổng expanded bytes và compression ratio; không chấp nhận path traversal khi extract archives.

### 11.2. Charset

`maxBytes` đếm bytes trên XML InputStream (sau decompression). `maxTextChars` đếm decoded UTF-16 chars. Một chữ tiếng Việt có thể chiếm nhiều bytes UTF-8 nhưng một char unit, còn emoji có thể hai char units. Đừng dùng hai đơn vị này như thể tương đương.

Nếu input có XML encoding declaration, StAX xử lý theo XML rules; đừng dùng Reader với charset sai rồi tin XML declaration. Nếu ứng dụng chỉ hỗ trợ UTF-8, validate encoding policy phù hợp.

### 11.3. Network timeout

`System.nanoTime()` không thể cancel một blocked socket read; có timeouts ở HTTP client, cancellation hoặc supervisor. Nếu cần hard memory/CPU isolation cho XML không đáng tin ở quy mô lớn, cân nhắc process/container worker riêng với quotas và watchdog.

### 11.4. Concurrency budget

Mỗi XML document có quotas riêng nhưng 100 import jobs song song vẫn tiêu thụ tổng memory/CPU lớn. Có thể dùng semaphore/worker pool có giới hạn và admission control dựa trên total resource budget.

---

## 12. Xử lý lỗi và observability

### 12.1. Phân loại lỗi

| Loại | Ví dụ | Phản hồi mong muốn |
| --- | --- | --- |
| XML syntax | Malformed closing tag | Document rejected |
| Security | DTD/XXE attempt | Rejected and audited |
| Input quota | maxBytes/maxEvents/maxRecords | Quota error code |
| Field quota | maxFieldChars/maxAttributes | Validation/quota error |
| Business data | amount invalid | Validation error |
| I/O | Connection reset/timeout | Transport failure |
| Resource exhaustion | Heap/CPU budget | Job failed/isolated |
| DB writer | Transaction error | Rollback/recovery |

Không biến mọi lỗi thành `malformed XML` rồi bỏ nguyên nhân. Không catch chung mọi Throwable để nuốt `OutOfMemoryError` hoặc các lỗi JVM nghiêm trọng.

### 12.2. XMLStreamException

StAX có thể ném XMLStreamException với line/column location. Dùng metadata đó khi phù hợp nhưng **không in full XML payload hoặc raw secret** trong logs/trả cho client.

### 12.3. Application quota exception

`LimitExceeded` trong ví dụ là **exception riêng**, không phải class chuẩn Java. Trong hệ thống thật, tạo error code có cấu trúc:

~~~text
documentId = ...
reason = MAX_BYTES
configuredLimit = ...
observed = ...
locationLine = ...
retryable = false
~~~

Đừng log full XML/PII. Những quota violations thường là **non-retryable nếu input và policy giữ nguyên**.

### 12.4. Metrics nên có

~~~text
xml.import.started_total
xml.import.succeeded_total
xml.import.rejected_total{reason="MAX_BYTES"}
xml.import.failed_total{reason="IO_ERROR"}
xml.import.bytes_total
xml.import.records_total
xml.import.duration_seconds
xml.import.active_jobs
~~~

Đây chỉ là schema gợi ý, không phải output của demo. Labels phải có cardinality thấp; không dùng userId/uploadId làm metric labels không giới hạn.

---

## 13. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Đọc cả XML bằng Files.readString | Memory tăng theo file | InputStream + StAX |
| Giữ mọi item vào List | Vẫn mất RAM | Xử lý item rồi bỏ |
| Chỉ tin Content-Length | Có thể bị thiếu/giả | Đếm bytes thực đọc |
| Chỉ giới hạn compressed bytes | Decompression bomb | Decoded-byte cap |
| Không tắt DTD | Entity expansion/XXE | SUPPORT_DTD false/deny |
| Chỉ chặn external entities | Internal DTD risks | Không cần DTD thì tắt DTD |
| Resolver return null để từ chối | Default resolution có thể chạy | Ném XMLStreamException |
| Bỏ qua unsupported security setting | Parser chạy chưa harden | Fail closed |
| Tưởng SUPPORT_DTD=false luôn reject DOCTYPE | Provider có thể ignore | Kiểm thử deny policy |
| Dùng DOM FSP flag cho StAX | Sai API semantics | StAX controls |
| getElementText trên text vô hạn | String rất lớn | Chunked bounded reads |
| Giữ getTextCharacters buffer sau next | Dữ liệu transient | Copy bounded ngay trong event |
| Không tính CDATA/SPACE | Bỏ lọt quota | Đếm mọi text events |
| Chỉ đếm records | Nhiều empty tags | Max events/depth |
| Chỉ giới hạn field | Many attributes | Attribute quota |
| Bỏ qua unknown tags | Silent data loss | Schema validation |
| Không check malformed EOF | Partial data coi thành công | Đọc tới END_DOCUMENT |
| Không giới hạn namespace | Confused tag identity | Validate QName/URI |
| Chỉ check deadline giữa events | Read có thể treo | Network timeout/cancel |
| Gọi reader.close mà không close input | Resource leak | TWR owned InputStream |
| Ghi DB rồi mới check quota | Partial external side effects | Validate/staging first |
| Queue downstream vô hạn | Memory tăng | Bounded queue/backpressure |
| Không giới hạn jobs đồng thời | Aggregate OOM | Admission control |
| Nhầm bytes với UTF-16 chars | Quota sai | Đơn vị rõ |
| Nhầm boundedMemoryModel với heap benchmark | False assurance | Load test/measure peak heap |
| Log XML khi lỗi | Lộ PII/credentials | Safe error codes/redaction |

---

## 14. Bài tập tự luyện

1. Biên dịch/chạy `BoundedStaxImport.java`; giải thích 15 dòng stdout.
2. Đổi `maxRecords` thành 9.999, kiểm tra item thứ 10.000 bị từ chối.
3. Đặt `maxBytes` bằng chính kích thước file và kích thước file trừ một.
4. Tạo field name dài 17 UTF-16 chars, xác nhận maxFieldChars=16 bị từ chối.
5. Đọc `<name>Ja<![CDATA[va]]></name>` và kiểm tra ghép đúng Java.
6. Dùng `Ja&amp;va`, kiểm tra XML decoding và text quota.
7. Thêm maxElementNameChars, maxAttributeNameChars cho schema mở rộng.
8. Kiểm tra `maxTextChars` tổng tài liệu và so với per-field quota.
9. Tạo 10.000 empty fields, phân tích event budget.
10. Thử amount âm, không phải số và ngoài int range.
11. Thử item có field lặp, thiếu name hoặc thiếu amount.
12. Thêm namespace URI allowlist và validate QName.
13. Tạo XML sai end tag ở item cuối, xác minh không trả thành công.
14. Thử input stream ném IOException ở giữa quá trình đọc.
15. Kiểm tra source stream được đóng khi parse lỗi.
16. Đo actual peak heap của parser với 1MB long token.
17. Xây một JUnit test cho byte cap ở ngưỡng exact.
18. Thử many attributes để đánh giá provider buffer overhead.
19. Thử DTD có internal/external entity trong sandbox cô lập.
20. Thử HTTP InputStream có read timeout và cancellation.
21. Giải nén gzip rồi áp decoded byte cap.
22. Thiết kế bounded queue giữa parser và batch DB writer.
23. Dùng staging table để chỉ publish sau END_DOCUMENT.
24. Dùng unique DB constraint thay HashSet nếu phải cấm duplicate IDs.
25. Thêm metrics duration/bytes/records/quotaRejectReason.
26. Chạy 10 parallel imports với semaphore và đo aggregate memory.
27. Test Unicode tiếng Việt và emoji để phân biệt bytes, codepoints, UTF-16 units.
28. So sánh DOM/SAX/StAX trên XML 10MB với cùng business logic.
29. Thử thay XMLInputFactory provider và chạy lại security regression tests.
30. Viết runbook xử lý tình trạng gia tăng XML quota rejections trong production.

---

## 15. Checklist đưa vào production

- [ ] Hợp đồng XML schema, namespace và field types được định nghĩa rõ.
- [ ] Không tải cả XML vào String/byte[]/DOM khi kích thước lớn.
- [ ] XMLInputFactory được harden **trước khi** tạo XMLStreamReader.
- [ ] Không cho DTD/external entities khi không cần; resolver reject external.
- [ ] Security settings không được fail silently.
- [ ] Test DOCTYPE policy trên đúng JDK/provider.
- [ ] Có decoded XML input byte cap, không chỉ Content-Length.
- [ ] Có quota cho compressed size/ratio nếu nhận gzip/zip.
- [ ] Có maxRecords, maxEvents và maxDepth.
- [ ] Có maxAttributes và maxAttributeChars.
- [ ] Có maxTextChars và maxFieldChars.
- [ ] Chỉ append text khi quota còn đủ.
- [ ] Không dùng getElementText cho field unbounded.
- [ ] Không giữ getTextCharacters buffer qua events.
- [ ] Không lẫn UTF-16 chars với UTF-8 bytes.
- [ ] Validate root/items/fields/namespace/amount.
- [ ] Reject tag lạ hoặc skip có quota nếu schema cho phép.
- [ ] Chỉ trả success khi hoàn tất END_DOCUMENT.
- [ ] Không phát hành external side effects trước validation/transaction boundary.
- [ ] Có bounded batching và backpressure.
- [ ] Có input/network timeout ngoài cooperative deadline.
- [ ] Có global concurrency budget.
- [ ] Đóng reader và owned InputStream trong mọi path.
- [ ] Logging không chứa full XML, user secrets/PII.
- [ ] Quota errors có safe error codes và audit.
- [ ] Có parser/JAXP-specific limits khi cần.
- [ ] Kiểm thử long token, deep nesting, many attributes và entity payloads.
- [ ] Đo peak memory/GC trên runtime deployment thật.
- [ ] Không khẳng định streaming tự bảo đảm memory O(1).
- [ ] Chạy các positive/negative tests trên Java version đang triển khai.
- [ ] Chỉ dùng những API và security controls Java còn hỗ trợ hiện nay.

## Kết luận

**StAX giúp xử lý XML lớn theo dòng sự kiện**, giảm nhu cầu giữ toàn bộ cây XML. Nhưng bảo vệ tài nguyên phải có **nhiều tầng**: khóa DTD/external references, hạn chế input bytes, events, records, depth, attributes, decoded text và field lengths; kiểm tra thời gian, timeout nguồn và cleanup. Với ingestion có side effects, cần staging/rollback/backpressure để tài liệu lỗi ở cuối không biến thành partial successful import.

Bài demo Java17+ đã **xử lý 10.000 records**, tổng amount 120.000, tổng text 60.000 UTF-16 chars và từ chối đúng các trường hợp vượt quota, cấu trúc bất hợp lệ, DTD, XML malformed; **15 dòng output đã kiểm chứng trên OpenJDK 24.0.2**. Đây là cơ sở để mở rộng, không thay thế security/load tests của parser và infrastructure thực tế.

**Tài liệu chính thức và hướng dẫn hiện hành:**

- [XMLInputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLInputFactory — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLStreamConstants — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamConstants.html)
- [XMLStreamException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamException.html)
- [XMLResolver — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLResolver.html)
- [Oracle JAXP Security Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/security/java-api-xml-processing-jaxp-security-guide.html)
- [OWASP XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html)