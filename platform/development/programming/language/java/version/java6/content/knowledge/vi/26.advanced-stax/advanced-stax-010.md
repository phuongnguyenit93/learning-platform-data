# StAX nâng cao: Đánh giá bộ nhớ, tốc độ và vòng đời tài nguyên

## Mục tiêu học tập

**StAX (Streaming API for XML)** là API đọc và ghi XML theo luồng thuộc module chuẩn **java.xml**. Thông qua **XMLStreamReader** hoặc **XMLEventReader**, chương trình có thể xử lý lần lượt các sự kiện XML thay vì phải tạo sẵn toàn bộ cây DOM. Nhưng **“streaming” không có nghĩa tự động ít RAM, nhanh nhất hoặc không bao giờ rò tài nguyên**.

Muốn đánh giá đúng StAX trong một hệ thống Java, cần trả lời đồng thời ba nhóm câu hỏi:

1. **Bộ nhớ:** JVM sử dụng bao nhiêu heap, tạo bao nhiêu đối tượng, giữ lại bao nhiêu dữ liệu, peak heap/GC ra sao? Ứng dụng có vô tình gom tất cả XML vào String, DOM hoặc collection không?
2. **Tốc độ:** Mỗi giây xử lý được bao nhiêu XML documents/items/MB? Độ trễ p50/p95/p99 ra sao? Thời gian đang đo là riêng parser hay còn gồm đọc file, network, XML validation, object mapping và output?
3. **Vòng đời tài nguyên:** InputStream/Reader, XMLStreamReader/XMLEventReader, XMLStreamWriter/XMLEventWriter, OutputStream/Writer và temporary files được sở hữu, đóng và giải phóng đúng cả khi thành công, lỗi, timeout hoặc hủy tác vụ không?

Bài học này đi sâu vào **đo và lý giải**, không chỉ minh họa một lời gọi XML parser. Sau bài, bạn có thể:

- Hiểu **đặc tính streaming** của XMLStreamReader và XMLEventReader cũng như các tình huống vô tình materialize cả tài liệu.
- Phân biệt **latency, throughput, heap used snapshot, peak heap, allocation rate, GC pauses, RSS/native memory và số resources đang mở**.
- Thiết kế một phép so sánh công bằng giữa **cursor-based XMLStreamReader** và **event-based XMLEventReader**, có cùng input, semantic result và điều kiện chạy.
- Biết giới hạn của **System.nanoTime()** và **MemoryMXBean.getHeapMemoryUsage().getUsed()**: hữu ích cho demo nhưng không đủ để kết luận benchmark.
- Hiểu vai trò của **OpenJDK JMH**, **Java Flight Recorder (JFR)**, **JDK Mission Control (JMC)** và OS/resource metrics trong performance profiling hiện hành.
- Biết khi nào **getElementText(), getText(), getTextCharacters(), isCoalescing, DOM, StringWriter** tạo/copy nhiều dữ liệu hơn mong muốn.
- Quản lý ownership/close/flush giữa StAX parser/writer và underlying streams, không dựa vào provider tự đóng nguồn.
- Xây **XMLInputFactory** có cấu hình từ chối DTD và external entities, kết hợp quota về số bytes, elements, depth, attributes và text.
- Biên dịch/chạy ví dụ Java 17+ tạo **5.000 item XML** ra temporary UTF-8 file, đọc bằng cả hai StAX styles, so sánh checksum/stats, kiểm tra cleanup và đo thời gian/heap snapshot.
- Nhận biết những kết quả **deterministic** của chương trình và những con số **phụ thuộc môi trường**, tránh quảng bá một số đo đơn lẻ như quy luật.

**Phạm vi hiện hành:** Các APIs trong ví dụ đều còn áp dụng với **Java 17+**, thuộc **java.xml** và **java.management**. Chương trình đã biên dịch và chạy trên **OpenJDK 24.0.2** với **javac --release 17**. Các công cụ profiling được đề cập đều là hướng thực hành hiện nay, không dùng cơ chế lỗi thời/legacy.

## 1. Vì sao StAX có thể tiết kiệm bộ nhớ?

Với một XML document có hàng triệu bản ghi:

~~~xml
<items>
  <item id="0">
    <name>Đà Nẵng &amp; Việt Nam 😀</name>
    <qty>0</qty>
  </item>
  <item id="1">
    <name>Đà Nẵng &amp; Việt Nam 😀</name>
    <qty>1</qty>
  </item>
</items>
~~~

Một parser dạng DOM thường xây dựng **cây node objects** cho document, lưu lại các elements/attributes/text cho đến khi ứng dụng giải phóng references. Với dữ liệu lớn, cây có thể tốn nhiều heap hơn dung lượng XML trên disk do object overhead, strings, nodes, references và metadata.

StAX cho phép cách làm khác:

~~~text
File / InputStream / Reader
             │
             ▼
XMLInputFactory → XMLStreamReader
             │
             ▼
     next() / getElementText()
             │
             ▼
  Xử lý một item / một event
             │
             ├── Counter / aggregate / sink
             │
             └── Bỏ reference tới item đã xử lý
             │
             ▼
      Item tiếp theo
~~~

Nếu chương trình chỉ giữ **parser buffers + trạng thái tầng phần tử + dữ liệu item hiện tại + một vài counters**, mức dữ liệu cần giữ **có thể không tăng tuyến tính theo toàn bộ kích thước tài liệu**.

Nhưng câu “StAX có O(1) memory” là **khẳng định quá mức**. Bộ nhớ thực tế còn phụ thuộc:

- Độ sâu XML và namespace/element contexts mà parser phải theo dõi.
- Kích thước một **text node/leaf element**: getElementText() có thể tạo String rất lớn.
- Buffer của InputStream/Reader/charset decoder/provider.
- Có bật coalescing, replacement of entities hoặc validation không.
- App có giữ List/Map của mọi item hoặc StringBuilder dài không.
- Kích thước buffers ở downstream, ví dụ message queue hoặc network sink.
- JDK/provider, GC, concurrency, streaming transformations và XML schema semantics.

**Mô hình đúng là: streaming có thể giới hạn lượng dữ liệu ứng dụng giữ cùng lúc, nếu cả pipeline được thiết kế streaming.**

### 1.1. So sánh các lựa chọn

| Cách đọc | Biểu diễn | Bộ nhớ có thể gặp | Đặc điểm tốc độ |
| --- | --- | --- | --- |
| **XMLStreamReader** | Cursor, next/getter | Parser buffers + dữ liệu xử lý hiện tại | Low-level; tránh tạo XMLEvent object ở app, nhưng phải đo |
| **XMLEventReader** | Iterator của XMLEvent objects | Parser buffers + event objects và dữ liệu app giữ | Dễ dùng cho event transformation, có thể thêm allocations |
| **DOM DocumentBuilder** | Cây Document/Node | Có thể tăng theo số nodes toàn tài liệu | Thuận tiện random access, có overhead cây |
| **Đọc XML thành String rồi parse** | String toàn document + parser data | Ít nhất phải chứa nội dung String (ngoài buffers) | Đơn giản XML nhỏ, dễ làm tăng peak heap |
| **Streaming Reader + List mọi item** | StAX nhưng giữ các DTOs | Tăng theo số items đã đọc | Mất ưu thế bounded retention |
| **Streaming Reader + bounded sink** | StAX, downstream xử lý từng item | Có thể kiểm soát heap theo in-flight data | Phù hợp dữ liệu lớn nếu I/O và backpressure đúng |

Đừng kết luận XMLStreamReader **luôn** nhanh hơn XMLEventReader hoặc DOM trên mọi payload/provider. Với XML rất nhỏ, thời gian khởi tạo factory/JIT/I/O có thể áp đảo. DOM có thể phù hợp khi cần duyệt ngẫu nhiên nhiều lần trên cây nhỏ.

### 1.2. Quy mô dữ liệu cần đánh giá

Một phép thử 5 KB XML không đại diện cho một payload 5 GB. Nên có nhiều bộ dữ liệu với các đặc điểm khác nhau:

- **Rất nhiều elements nhỏ**: kiểm tra overhead của event objects và per-node processing.
- **Một element có text rất dài**: phát hiện getElementText/StringBuilder và memory pressure.
- **Depth lớn**: kiểm tra parser stack, application recursion và depth limits.
- **Attributes/namespaces nhiều**: kiểm tra chi phí lookup/metadata.
- **CDATA/entity/Unicode/emoji**: kiểm tra correctness, decoder và text splitting.
- **XML hợp lệ/không hợp lệ**: lỗi giữa luồng phải đóng tài nguyên đúng.
- **Input từ disk vs memory vs network**: có các bottlenecks khác nhau.

## 2. Đo đúng loại chỉ số, tránh diễn giải nhầm

### 2.1. Latency và throughput

**Latency:** thời gian để xử lý một document hoặc một request. Nên quan tâm phân bố **p50/p95/p99**, không chỉ một số trung bình.

**Throughput:** documents/s, items/s hoặc MB/s trong một khoảng đo đủ dài. Khi báo MB/s, cần ghi rõ **MB hệ 10 hay MiB hệ 2** và kích thước được tính theo **bytes thực** của input hay theo số ký tự XML đã decode.

Ví dụ:

~~~text
Input bytes:          50_000_000 bytes
Completed items:      1_000_000 items
Elapsed wall time:    2.5 seconds

Throughput bytes/s = 50_000_000 / 2.5 = 20_000_000 bytes/s
Throughput items/s = 1_000_000 / 2.5 = 400_000 items/s
~~~

Đây chỉ là **số tính minh họa**, không phải benchmark đã đo của StAX. Nếu XML được nén qua network, phải xác định đang đo bytes trước hay sau giải nén.

### 2.2. Heap used, peak heap và allocation khác nhau

| Chỉ số | Ý nghĩa | Điều nó không tự chứng minh |
| --- | --- | --- |
| **Heap used snapshot** | Dung lượng heap đang được JVM báo tại một thời điểm | Không phải peak heap, không phải tổng bytes allocated |
| **Before-after heap delta** | Chênh lệch hai snapshots | Có thể nhỏ/âm do GC dù tạo rất nhiều objects |
| **Peak heap trong quá trình** | Giá trị lớn nhất được quan sát theo một phương pháp sampling | Phụ thuộc sampling interval và GC |
| **Allocated bytes/op** | Số bytes objects được cấp phát trên mỗi operation | Không đồng nghĩa với retained heap |
| **Allocation rate** | Bytes allocated/s | Cao không nhất thiết là leak |
| **Retained live set** | Đối tượng vẫn được giữ sống qua references | Không thể suy từ hai snapshots tùy ý |
| **GC pauses** | Thời gian dừng do GC | Cần phân tích cùng workload và collector |
| **Process RSS/native/direct** | Memory OS giữ cho process và native buffers | Không chỉ là Java heap |

Ví dụ một parser tạo 500 MB đối tượng tạm thời rồi GC thu hồi trước snapshot cuối: **heapAfter - heapBefore có thể bằng 0 hoặc âm**, dù allocation rate đã cao.

Ngược lại, heap delta +20 MB sau một lần đọc không tự chứng minh memory leak; đó có thể là objects còn sống tạm thời hoặc GC chưa chạy. Cần xem **retained references**, live set sau những cycles hoạt động, allocation profiling và GC trends.

### 2.3. Dùng System.nanoTime đúng cách

~~~java
// Mảnh minh họa, operation do caller cung cấp.
long start = System.nanoTime();
performXmlWork();
long elapsedNanos = System.nanoTime() - start;
double milliseconds = elapsedNanos / 1_000_000.0;
~~~

**System.nanoTime()** phù hợp đo **elapsed time** trong cùng JVM. Nó không cho wall-clock timestamp, không dùng để so sánh trực tiếp giá trị tuyệt đối giữa processes/machines.

**Một lần đo không phải benchmark đáng tin.** JIT warmup, GC, OS scheduling, CPU frequency, disk cache và provider initialization có thể làm các lần chạy khác nhau đáng kể.

### 2.4. MemoryMXBean để quan sát nhanh

~~~java
long before = java.lang.management.ManagementFactory
        .getMemoryMXBean().getHeapMemoryUsage().getUsed();

// Chạy workload.

long after = java.lang.management.ManagementFactory
        .getMemoryMXBean().getHeapMemoryUsage().getUsed();

long snapshotDelta = after - before;
~~~

`before` và `after` là **hai lần lấy snapshot heap used**. Không dùng snapshotDelta để xếp hạng parser “ít RAM nhất” hoặc quảng bá như **peak memory**. Dùng JFR/heap profiler/OS counters khi cần bằng chứng thực sự.

### 2.5. Cách đọc một kết quả benchmark

Một báo cáo có giá trị cần nêu:

~~~text
JDK:                 version + vendor + GC flags
OS / CPU / RAM:      mô tả máy
StAX provider:       implementation/version
Input:               XML dataset, size bytes, depth, item count
XML settings:        DTD/entities/coalescing/namespace
I/O mode:            bytes in RAM, local SSD, network...
Warmup:              iterations/duration
Measurement:         iterations/forks, concurrency
Latency:             median, p95/p99 + units
Throughput:          docs/s, items/s, MiB/s
Allocations:         bytes/op and/or bytes/s
Heap/GC:             peak/live set/GC pause evidence
Resources:           open handles, closure on success/failure
Correctness:         same semantic result for compared methods
~~~

Nếu thiếu input/provider, chỉ nói “XMLStreamReader xử lý 2 ms” sẽ rất khó tái lập, và càng khó so sánh với một phương án khác.

## 3. Vòng đời tài nguyên trong StAX

### 3.1. Các resource owners khác nhau

Một pipeline có thể giữ nhiều resources:

~~~text
Files.newInputStream(path) ──── InputStream (owner: application)
          │
          ▼
XMLInputFactory.createXMLStreamReader(input)
          │
          ▼
XMLStreamReader (owner: parser scope)
          │
          ▼
Xử lý events / item
          │
          ▼
XMLStreamReader.close()   <─ đóng reader theo API
          │
          ▼
InputStream.close()       <─ application đóng nguồn của mình
~~~

Một output pipeline:

~~~text
Files.newOutputStream(path) ─── OutputStream (owner: application)
          │
          ▼
XMLOutputFactory.createXMLStreamWriter(output, "UTF-8")
          │
          ▼
XMLStreamWriter (owner: writer scope)
          │
          ▼
writeStartDocument → elements → writeEndDocument
          │
          ▼
XMLStreamWriter.flush() / close()
          │
          ▼
OutputStream.close()      <─ application đóng sink của mình
~~~

**Nguyên tắc ownership:** ai mở **InputStream/OutputStream** thì phải bảo đảm chúng được đóng, kể cả khi parser/writer có gọi close hoặc provider chủ động đóng nguồn trong một số trạng thái.

### 3.2. Parser.close có đóng underlying source không?

Theo Javadoc Java SE hiện hành, **XMLStreamReader.close() và XMLEventReader.close() giải phóng tài nguyên parser nhưng không có trách nhiệm đóng underlying input source**. Vì thế **không dựa vào parser.close() để thay cho InputStream.close()**.

Lưu ý thực tế: một provider có thể giải phóng hoặc đóng underlying stream khi đọc tới cuối, trong error path hoặc lúc nội bộ dọn resources. Trong quá trình thử nghiệm trên OpenJDK 24.0.2, stream wrapper đã thấy `close()` được gọi trước khi owner scope kết thúc. Vì vậy **thời điểm stream bị đóng không phải thứ nên hardcode vào logic dùng chung đa providers**. Dù provider có đóng trước hay không, **try-with-resources của application vẫn bảo đảm gọi close trên stream mà nó sở hữu**.

Không viết test cho production bắt buộc `sourceStillOpenAfterParserClose=true` trên mọi provider; test quan trọng là **source được đóng đầy đủ khi thoát owner scope**, không có handles bị leak.

### 3.3. Writer.close không có nghĩa đóng output sink

`XMLStreamWriter.close()` giải phóng writer resources; tài liệu interface nói nó **không đóng underlying output stream**. Tương tự, đừng mặc định `XMLEventWriter.close()` thay `Writer/OutputStream.close()` do application sở hữu.

Ví dụ:

~~~java
// Mảnh minh họa với Path path.
try (java.io.OutputStream output =
        java.nio.file.Files.newOutputStream(path)) {
    XMLStreamWriter xml = XMLOutputFactory.newFactory()
            .createXMLStreamWriter(output, "UTF-8");
    try {
        xml.writeStartDocument("UTF-8", "1.0");
        xml.writeStartElement("report");
        xml.writeCharacters("Xin chào");
        xml.writeEndElement();
        xml.writeEndDocument();
        xml.flush();
    } finally {
        xml.close();
    }
}
~~~

**Hai lớp tài nguyên được giải phóng theo thứ tự writer rồi stream**. Nếu XML output rất lớn, không giữ một `StringWriter` để lưu hết trong heap chỉ để sau đó ghi ra file.

### 3.4. XMLStreamReader/XMLEventReader không phải AutoCloseable trong target Java 17

Trong Java 17, các StAX reader/writer interfaces được dùng trong ví dụ **không tự implement AutoCloseable để sử dụng trực tiếp trong try-with-resources**. Vì thế có thể dùng:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    XMLStreamReader xml = inputFactory.createXMLStreamReader(input, "UTF-8");
    try {
        // Đọc tất cả dữ liệu cần thiết.
    } finally {
        xml.close();
    }
}
~~~

Đây là **mảnh minh họa**; cần imports/variables tương ứng. Cách trên có nhược điểm: nếu body ném XMLStreamException, rồi xml.close cũng ném, finally có thể che lỗi ban đầu. Trong production, có thể dùng **AutoCloseable adapter** để try-with-resources giữ primary failure và suppressed close failure:

~~~java
// Mảnh minh họa helper trong Java 17+.
final class StaxReaderOwner implements AutoCloseable {
    private final XMLStreamReader reader;

    StaxReaderOwner(XMLStreamReader reader) {
        this.reader = reader;
    }

    @Override
    public void close() throws XMLStreamException {
        reader.close();
    }
}

// Mảnh minh họa sử dụng.
try (InputStream input = Files.newInputStream(path);
     StaxReaderOwner owner = new StaxReaderOwner(
             factory.createXMLStreamReader(input, "UTF-8"))) {
    // Các lệnh parser qua reference do caller đã giữ nếu cần.
}
~~~

Với helper trên, ứng dụng vẫn phải có reference tới XMLStreamReader để đọc; wrapper chịu trách nhiệm close ở đúng thời điểm. Trong code production thực tế, bạn có thể thiết kế owner vừa expose reader vừa implement AutoCloseable, nhưng không bắt buộc mọi lesson demo có thêm abstraction này.

**Không gọi System.gc() để “giải phóng InputStream”**. GC không phải cơ chế đóng tài nguyên I/O deterministically. Close đúng ở mọi luồng thực thi là trách nhiệm application.

### 3.5. Các đường lỗi quan trọng

Kiểm thử cleanup khi:

- XML malformed gây XMLStreamException giữa parse.
- DTD bị từ chối.
- Underlying file/network read trả IOException hoặc timeout.
- Downstream consumer dừng giữa chừng.
- Parser/writer.close cũng báo lỗi.
- Writer không ghi được vì disk đầy hoặc client disconnect.
- Tác vụ bị cancel/interrupt.
- XML document quá lớn hoặc vượt depth/text quotas.

Đừng chỉ test thành công rồi kết luận không rò handles.

## 4. Tối ưu cấp phát và giữ dữ liệu

### 4.1. XMLStreamReader: đọc cursor, tránh tạo DTOs không cần thiết

Với `XMLStreamReader`, bạn có thể duyệt:

~~~java
while (xml.hasNext()) {
    int event = xml.next();
    if (event == XMLStreamConstants.START_ELEMENT) {
        // Xử lý cấu trúc theo current event.
    } else if (event == XMLStreamConstants.CHARACTERS) {
        // Lấy text khi thực sự cần.
    }
}
~~~

Cursor API cho phép truy cập thuộc tính ngay tại event hiện tại mà không tạo một `XMLEvent` object ở application code. Javadoc mô tả XMLStreamReader là lựa chọn low-level hiệu quả, nhưng **chỉ số allocations cụ thể còn do implementation quyết định**.

### 4.2. XMLEventReader: thuận lợi cho event transformations

`XMLEventReader.nextEvent()` trả event object. `XMLEventFactory` và `XMLEventWriter` làm việc theo event-oriented pipeline rất rõ ràng:

~~~java
while (events.hasNext()) {
    XMLEvent e = events.nextEvent();
    if (e.isStartElement()) {
        String local = e.asStartElement().getName().getLocalPart();
        // Tùy ứng dụng, xử lý event.
    }
}
~~~

**Có thể** có thêm allocation/virtual dispatch so với cursor, nhưng **không hardcode “chậm hơn x lần”**. Những tối ưu nội bộ/provider và mức độ phức tạp của logic xử lý đều ảnh hưởng. Nếu application đang cần transform/copy events, dùng event reader có thể giúp giảm mã chuyển đổi, đem lại hiệu quả tổng thể tốt hơn.

### 4.3. getElementText() tạo String của cả leaf

`XMLStreamReader.getElementText()` tiện khi con trỏ ở START_ELEMENT và element đó chỉ chứa text:

~~~java
String text = xml.getElementText();
// Sau thành công, con trỏ ở END_ELEMENT tương ứng.
~~~

Nó trả **toàn bộ text của leaf** thành String đã coalesced. Nếu một `<blob>` chứa 200 MB text, bạn có thể đang tạo một String rất lớn, dù phần khác của chương trình dùng StAX.

Với text dài, có thể dùng `next()` và xử lý các `CHARACTERS`/`CDATA` events lần lượt (cần duy trì depth/element scope đúng). **Không giả định mỗi leaf chỉ có một CHARACTERS event**.

### 4.4. getTextCharacters() và buffer lifetime

`XMLStreamReader.getTextCharacters()` có thể trả một char array nội bộ. Các giá trị `getTextStart()`/`getTextLength()` chỉ ra vùng hợp lệ. Buffer này **chỉ dùng trong current event**, không sửa và không giữ reference sau khi `next()` làm parser tiến trạng thái.

~~~java
// Mảnh minh họa tại một CHARACTERS event.
char[] chars = xml.getTextCharacters();
int offset = xml.getTextStart();
int length = xml.getTextLength();

for (int i = offset; i < offset + length; i++) {
    // Xử lý chars[i] ngay trong event; không cache mảng.
}
~~~

Lưu ý UTF-16: một Unicode code point ngoài BMP như **😀** có thể gồm **hai Java char units**. Nếu đo “số ký tự”, phải nói rõ đếm **UTF-16 code units**, **Unicode code points** hay **grapheme clusters**; chúng khác nhau. Demo sẽ dùng **UTF-16 char units và tổng char values** chỉ để kiểm tra kết quả nhất quán, không phải cryptographic checksum.

### 4.5. IS_COALESCING ảnh hưởng workload

`XMLInputFactory.IS_COALESCING` có thể hợp nhất text/CDATA segments. Có thể làm application xử lý đơn giản hơn, nhưng cũng có thể làm buffer text lớn hơn. Cần:

- Định nghĩa rõ workload và dữ liệu XML.
- Đo với coalescing on/off trên provider thật khi phù hợp.
- Vẫn xử lý text fragmentation theo API contract.
- Không suy coalescing luôn nhanh hơn.
- Với `getElementText`, phương thức tự trả coalesced text bất kể giá trị IS_COALESCING.

Một performance test thay đổi đồng thời cả provider, coalescing và application logic sẽ không cô lập được tác động nào gây khác biệt.

### 4.6. Không để StringBuilder/List biến stream thành materialization

Ví dụ làm mất lợi thế streaming:

~~~java
// Mã minh họa điều cần tránh với dữ liệu lớn.
List<String> allNames = new ArrayList<>();
while (xml.hasNext()) {
    int event = xml.next();
    if (event == XMLStreamConstants.START_ELEMENT
            && "name".equals(xml.getLocalName())) {
        allNames.add(xml.getElementText());
    }
}
// allNames giữ toàn bộ dữ liệu.
~~~

Nếu chỉ cần tổng số item, tổng lượng, checksum hoặc một output stream, hãy giữ counters và xử lý item xong thì bỏ reference. Nếu cần dedup hoặc join lớn, dùng một bounded cache, database index hoặc external storage theo thiết kế, không gom vô hạn vào JVM heap.

## 5. Phương pháp so sánh đúng và công bằng

### 5.1. Cùng input, cùng semantic work

Để so **XMLStreamReader vs XMLEventReader**, cả hai phải:

- Đọc **cùng một XML file/bytes**.
- Dùng security policy tương đương.
- Trích **cùng dữ liệu nghiệp vụ** (items count, name chars, quantity sum...).
- Không để một phương pháp chỉ đếm tags trong khi phương pháp kia validate/mapping toàn bộ.
- Đóng resources đúng.
- Không đo việc generate input ở một nhánh nhưng không ở nhánh còn lại.
- Kiểm tra kết quả **bằng nhau** trước khi xem timings.

Một benchmark có số nhanh nhưng kết quả sai là vô ích. Vì thế bài này yêu cầu summary của hai reader bằng nhau trước khi in metrics.

### 5.2. Tách parser-only và end-to-end

**Parser-only:** input bytes trong memory hoặc nguồn có I/O được kiểm soát; ít bị disk cache/network thay đổi. Nhưng nếu đưa toàn bộ file vào byte[] để tạo parser, **tổng memory footprint của pipeline** đã chứa file nên không thể xem đây là phép đo bounded-memory end-to-end.

**End-to-end:** mở file, decode charset, parse, map dữ liệu, đẩy xuống sink, đóng resources. Đây là dữ liệu quan trọng để tối ưu sản phẩm, nhưng timing sẽ gồm file I/O/cache, OS scheduling, potentially network latency, downstream backpressure.

Nếu application đọc XML từ remote HTTP response, throughput có thể bị giới hạn chủ yếu bởi network chứ không phải parser. Đừng ưu tiên đổi XMLStreamReader sang XMLEventReader nếu vấn đề thực tế là upstream chậm.

### 5.3. Warmup, GC, JIT, forks

Một phép thử ngắn chỉ chạy một lần dễ sai do:

- JIT compilation chưa warmed up.
- Class loading và provider discovery.
- Filesystem cache chưa warmed up.
- GC xảy ra ở một nhánh.
- CPU thermal throttling hoặc thread scheduling.
- Một phương pháp luôn chạy sau phương pháp khác, được hưởng cache.

**JMH (Java Microbenchmark Harness)** là công cụ từ dự án **OpenJDK Code Tools**, phù hợp với microbenchmarks vì cung cấp warmup, measurement iterations, forks và harness kiểm soát. Tài liệu dự án khuyên dùng Maven archetype để thiết lập JMH đúng, và nhấn mạnh vẫn cần thiết kế benchmark hợp lý.

**Không nên coi `System.nanoTime()` trong một `main()` ngắn là thí nghiệm thống kê chính thức.** Demo sử dụng nó để học cách đo và quan sát variability; nếu muốn kết luận hiệu năng, chuyển phần parser operation vào JMH và báo cáo phân bố kết quả sau nhiều forks trên dữ liệu đã kiểm soát.

### 5.4. Không bỏ qua CPU/JVM flags

Cần ghi lại:

- Java version/vendor, JDK/JRE mode và StAX provider version.
- JVM heap limits `-Xms`, `-Xmx`, GC collector và logging.
- CPU, số cores, topology, hệ điều hành, filesystem.
- XML input sizes và content distribution.
- Warmup/measurement cycles và thread count.
- Bảo mật XML factory properties.
- Cách xử lý text (`getElementText` vs event text accumulation).
- Có kích hoạt JFR/profiler hay logging nặng trong lúc đo không.

So sánh hai lần với các flags khác nhau có thể phản ánh GC hoặc JIT hơn là lựa chọn StAX reader.

## 6. Java Flight Recorder, GC logs và bộ nhớ thực

### 6.1. JFR/JMC cho câu hỏi “RAM đi đâu?”

**Java Flight Recorder** ghi lại các sự kiện JVM hữu ích cho CPU, allocations, GC, I/O, threads và pauses. **JDK Mission Control** cho phép phân tích các recordings để tìm hotspots, đối tượng được cấp phát nhiều và thời gian chờ I/O.

Với workload StAX cần quan tâm:

- **Allocations:** `XMLEvent` objects, Strings, char[]/byte[], DTOs, caches.
- **GC:** number/frequency of collections, pause times, old-gen pressure.
- **File read/write:** thời gian chờ disk, tổng bytes/file.
- **Socket read/write:** network-bound XML consumption.
- **CPU samples:** parser hot methods, XML validation, charset decoding.
- **Memory:** used heap trend, native buffers và RSS.

**JFR có overhead**, phụ thuộc recording settings và workload. Oracle lưu ý rằng một số heap-statistics options có thể kích hoạt GC lớn làm méo phép đo, nên không bật mọi profiling option một cách mù quáng trong latency benchmark.

### 6.2. Ví dụ lệnh JFR

~~~bash
java -XX:StartFlightRecording=filename=stax-run.jfr,settings=profile -cp . StaxResourceMetricsDemo
~~~

Mảnh lệnh này **minh họa cách chạy JFR với một Java program**. Output `stax-run.jfr` xuất hiện trong thư mục chạy nếu runtime hỗ trợ và quá trình thu thập hoàn tất; để đo một workload dài, cần thiết kế duration, dump policy và file size phù hợp.

Có thể dùng công cụ `jfr` đi cùng JDK:

~~~bash
jfr summary stax-run.jfr
~~~

Với input demo chỉ vài nghìn item và chương trình hoàn thành rất nhanh, JFR có thể không thu đủ samples để diễn giải hotspots. Với profiling thật, dùng workload chạy đủ lâu hoặc lập một JMH/integration load test có thời lượng và concurrency được kiểm soát. Không ghi file JFR chứa dữ liệu nhạy cảm vào thư mục công khai.

### 6.3. Theo dõi GC

Dùng JDK hỗ trợ unified logging:

~~~bash
java -Xlog:gc* -cp . StaxResourceMetricsDemo
~~~

Nếu chạy với heap nhỏ:

~~~bash
java -Xms64m -Xmx64m -Xlog:gc* StaxResourceMetricsDemo
~~~

Các tham số GC chỉ là ví dụ để quan sát; đừng khẳng định 64 MiB là lựa chọn phù hợp cho mọi payload hay mọi GC. Để benchmark, chọn một cấu hình hợp lý, giữ cố định giữa các nhánh và ghi version/flags.

**Không tự ép `System.gc()` trước/sau mỗi iteration rồi nghĩ mình đã đo allocation chính xác.** Explicit GC có thể thay đổi workload, không phản ánh hệ thống production và làm mất khả năng so sánh thời gian parser thuần.

### 6.4. Đọc allocated bytes/op bằng công cụ chuyên dụng

Khi cần số **allocated bytes/op** đáng tin hơn, có thể dùng:

- **JMH GC profiler** cho benchmark allocations khi môi trường hỗ trợ.
- **JFR allocation profiling** để tìm classes và call sites.
- **Java Mission Control** để xem allocation hotspots.
- **JVM-specific ThreadMXBean allocation counters** khi được hỗ trợ (không phải thông tin portable bắt buộc của tất cả JVM).

Không thay **allocated bytes** bằng hai lần gọi **getHeapMemoryUsage().getUsed()**.

## 7. Ví dụ Java 17+ hoàn chỉnh: ghi 5.000 item, đọc hai kiểu và đo tài nguyên

Chương trình **StaxResourceMetricsDemo.java** sử dụng **chỉ thư viện đi kèm JDK**. Nó không cần Maven, Gradle, database hay file XML do bạn chuẩn bị.

Quy trình:

1. Tạo một temporary file được quản lý trong hệ thống.
2. Dùng **XMLOutputFactory + XMLStreamWriter** ghi 5.000 `<item>` thành XML UTF-8; phần `<name>` chứa dấu tiếng Việt, dấu `&` và emoji.
3. Dùng `TrackedOutput` để xác minh writer.close không thay owner close của OutputStream.
4. Warmup hai lần đọc bằng **XMLStreamReader** và **XMLEventReader**; không xem warmup là benchmark.
5. Dùng `System.nanoTime()` ghi elapsed time của từng parse operation.
6. Gọi `MemoryMXBean` trước và sau từng operation để quan sát **heap snapshots**, không suy peak memory.
7. Đọc bằng **cursor**: `getElementText()` cho leaf name/qty, giữ counters mà không lưu toàn bộ items.
8. Đọc bằng **events**: thu từng Characters event theo current element, không gom toàn document; có một StringBuilder nhỏ cho giá trị qty.
9. Xác nhận cả hai trả cùng Summary về item count, tổng UTF-16 units, tổng char values và tổng quantity.
10. Đóng XML reader và InputStream do app sở hữu, kể cả khi parse lỗi.
11. In kết quả deterministic lẫn hai dòng runtime-dependent metrics.
12. Xóa temporary XML file trong `finally`, không để lại output dở.

**Giới hạn cố ý:** Đây là một **micro-experiment sư phạm**, không phải JMH benchmark chính thức. `getHeapMemoryUsage` chỉ cung cấp snapshots, elapsed time gồm tạo parser/đọc file và không tách GC/OS cache. Tính đúng đắn và cleanup được test độc lập với việc xếp hạng tốc độ.

### 7.1. File StaxResourceMetricsDemo.java

~~~java
import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.file.*;
import java.util.Locale;
import javax.xml.XMLConstants;
import javax.xml.stream.*;
import javax.xml.stream.events.XMLEvent;

public final class StaxResourceMetricsDemo {
    static final int ROWS = 5000;
    static final String NAME = "Đà Nẵng & Việt Nam 😀";
    record Summary(int rows, long nameUnits, long nameUnitSum, long qtySum) {}
    record ReadResult(Summary summary, boolean inputClosedAtScopeEnd) {}
    record WriteResult(boolean outputOpenAfterWriterClose,
                       boolean outputClosedAtScopeEnd) {}
    record Trial(ReadResult read, long nanos, long heapBefore, long heapAfter) {
        double ms() { return nanos / 1_000_000.0; }
        long heapDelta() { return heapAfter - heapBefore; }
    }

    static final class TrackedInput extends FilterInputStream {
        boolean closed;
        TrackedInput(InputStream raw) { super(raw); }
        @Override public void close() throws IOException {
            closed = true;
            super.close();
        }
    }
    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;
        TrackedOutput(OutputStream raw) { super(raw); }
        @Override public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static XMLInputFactory safeInputFactory() {
        XMLInputFactory f = XMLInputFactory.newFactory();
        f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
        f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
        f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        f.setXMLResolver((publicId, systemId, base, namespace) -> {
            throw new XMLStreamException("External entity denied");
        });
        return f;
    }

    static WriteResult generate(Path path) throws Exception {
        TrackedOutput out = new TrackedOutput(Files.newOutputStream(path));
        boolean openAfterWriterClose;
        try (out) {
            XMLStreamWriter xml = XMLOutputFactory.newFactory()
                    .createXMLStreamWriter(out, "UTF-8");
            try {
                xml.writeStartDocument("UTF-8", "1.0");
                xml.writeStartElement("items");
                for (int i = 0; i < ROWS; i++) {
                    xml.writeStartElement("item");
                    xml.writeAttribute("id", Integer.toString(i));
                    xml.writeStartElement("name");
                    xml.writeCharacters(NAME);
                    xml.writeEndElement();
                    xml.writeStartElement("qty");
                    xml.writeCharacters(Integer.toString(i % 7));
                    xml.writeEndElement();
                    xml.writeEndElement();
                }
                xml.writeEndElement();
                xml.writeEndDocument();
                xml.flush();
            } finally {
                xml.close();
            }
            openAfterWriterClose = !out.closed;
        }
        return new WriteResult(openAfterWriterClose, out.closed);
    }

    static long codeUnitSum(String value) {
        long total = 0;
        for (int i = 0; i < value.length(); i++) total += value.charAt(i);
        return total;
    }

    static ReadResult cursor(Path path) throws Exception {
        TrackedInput in = new TrackedInput(Files.newInputStream(path));
        int rows = 0;
        long units = 0, sum = 0, qty = 0;
        try (in) {
            XMLStreamReader xml = safeInputFactory()
                    .createXMLStreamReader(in, "UTF-8");
            try {
                while (xml.hasNext()) {
                    int event = xml.next();
                    if (event == XMLStreamConstants.DTD)
                        throw new XMLStreamException("DOCTYPE denied");
                    if (event == XMLStreamConstants.START_ELEMENT) {
                        switch (xml.getLocalName()) {
                            case "name":
                                String value = xml.getElementText();
                                units += value.length();
                                sum += codeUnitSum(value);
                                break;
                            case "qty":
                                qty += Integer.parseInt(xml.getElementText());
                                break;
                            default:
                                break;
                        }
                    } else if (event == XMLStreamConstants.END_ELEMENT
                            && "item".equals(xml.getLocalName())) rows++;
                }
            } finally {
                xml.close();
            }
        }
        return new ReadResult(new Summary(rows, units, sum, qty), in.closed);
    }

    static ReadResult events(Path path) throws Exception {
        TrackedInput in = new TrackedInput(Files.newInputStream(path));
        int rows = 0;
        long units = 0, sum = 0, qty = 0;
        boolean inName = false, inQty = false;
        StringBuilder qtyText = new StringBuilder();
        try (in) {
            XMLEventReader xml = safeInputFactory()
                    .createXMLEventReader(in, "UTF-8");
            try {
                while (xml.hasNext()) {
                    XMLEvent event = xml.nextEvent();
                    if (event.getEventType() == XMLStreamConstants.DTD)
                        throw new XMLStreamException("DOCTYPE denied");
                    if (event.isStartElement()) {
                        String name = event.asStartElement().getName().getLocalPart();
                        if ("name".equals(name)) inName = true;
                        if ("qty".equals(name)) inQty = true;
                    } else if (event.isCharacters()) {
                        String value = event.asCharacters().getData();
                        if (inName) {
                            units += value.length();
                            sum += codeUnitSum(value);
                        } else if (inQty) {
                            qtyText.append(value);
                        }
                    } else if (event.isEndElement()) {
                        String name = event.asEndElement().getName().getLocalPart();
                        if ("name".equals(name)) inName = false;
                        if ("qty".equals(name)) {
                            qty += Integer.parseInt(qtyText.toString());
                            qtyText.setLength(0);
                            inQty = false;
                        }
                        if ("item".equals(name)) rows++;
                    }
                }
            } finally {
                xml.close();
            }
        }
        return new ReadResult(new Summary(rows, units, sum, qty), in.closed);
    }

    interface Action {
        ReadResult run() throws Exception;
    }

    static Trial measure(Action action) throws Exception {
        long before = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        long start = System.nanoTime();
        ReadResult result = action.run();
        long duration = System.nanoTime() - start;
        long after = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        return new Trial(result, duration, before, after);
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempFile("stax-measure-", ".xml");
        try {
            WriteResult writing = generate(temp);
            for (int i = 0; i < 2; i++) {
                cursor(temp);
                events(temp);
            }
            Trial a = measure(() -> cursor(temp));
            Trial b = measure(() -> events(temp));
            Summary summary = a.read().summary();
            if (summary.rows() != ROWS
                    || !summary.equals(b.read().summary()))
                throw new AssertionError("Mismatch between parsers");

            System.out.println("rows=" + summary.rows());
            System.out.println("nameUtf16Units=" + summary.nameUnits());
            System.out.println("nameCodeUnitSum=" + summary.nameUnitSum());
            System.out.println("qtySum=" + summary.qtySum());
            System.out.println("sameSummary=" +
                    summary.equals(b.read().summary()));
            System.out.println("outputOpenAfterWriterClose="
                    + writing.outputOpenAfterWriterClose());
            System.out.println("outputClosedAtScopeEnd="
                    + writing.outputClosedAtScopeEnd());
            System.out.println("cursorInputClosedAtScopeEnd="
                    + a.read().inputClosedAtScopeEnd());
            System.out.println("eventInputClosedAtScopeEnd="
                    + b.read().inputClosedAtScopeEnd());
            System.out.println("elapsedPositive="
                    + (a.nanos() > 0 && b.nanos() > 0));
            System.out.println("heapSnapshotsAvailable="
                    + (a.heapBefore() >= 0 && b.heapBefore() >= 0));
            System.out.printf(Locale.ROOT,
                    "cursorElapsedMs=%.3f heapDeltaBytes=%+d%n",
                    a.ms(), a.heapDelta());
            System.out.printf(Locale.ROOT,
                    "eventElapsedMs=%.3f heapDeltaBytes=%+d%n",
                    b.ms(), b.heapDelta());
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

### 7.2. Lệnh biên dịch và chạy

Lưu file với đúng tên **StaxResourceMetricsDemo.java** và dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 StaxResourceMetricsDemo.java
java StaxResourceMetricsDemo
~~~

Chương trình tạo tệp XML tạm trong thư mục temp của hệ điều hành rồi xóa sau khi chạy. Không cần thư viện ngoài JDK; nếu sandbox không cho phép tạo file tạm, cần chạy trong một thư mục được cấp quyền hoặc điều chỉnh path theo chính sách môi trường.

**Kiểm thử code:** Chương trình đã được biên dịch và chạy thành công trên **OpenJDK 24.0.2** với `javac --release 17`. Thời gian, lượng heap sử dụng và provider behavior của môi trường khác có thể thay đổi.

### 7.3. Stdout: phần xác định và phần phụ thuộc runtime

**11 dòng đầu là kết quả xác định** của dữ liệu test trong chương trình:

~~~text
rows=5000
nameUtf16Units=105000
nameCodeUnitSum=647525000
qtySum=14995
sameSummary=true
outputOpenAfterWriterClose=true
outputClosedAtScopeEnd=true
cursorInputClosedAtScopeEnd=true
eventInputClosedAtScopeEnd=true
elapsedPositive=true
heapSnapshotsAvailable=true
~~~

**Hai dòng cuối là measurements phụ thuộc môi trường**, ví dụ một lần chạy trên OpenJDK 24.0.2:

~~~text
cursorElapsedMs=6.909 heapDeltaBytes=+0
eventElapsedMs=14.542 heapDeltaBytes=+16777216
~~~

**Đừng coi 6.909 ms hay 14.542 ms là kết quả bạn luôn phải thấy**. Phần `heapDeltaBytes` có thể bằng 0, dương hoặc âm tùy GC timing. Hai dòng được kiểm thử bằng **định dạng và kiểu dữ liệu**; chỉ các dòng fixed được so khớp bằng giá trị cụ thể.

**Điều tuyệt đối không được suy:** output trên không chứng minh XMLEventReader luôn chậm hơn XMLStreamReader gần hai lần, cũng không chứng minh XMLEventReader tiêu tốn thêm 16 MiB peak heap. Đây là một lần đọc file ngắn, có JIT/GC/disk cache, và hai snapshots heap không đo allocations hay peak.

### 7.4. Tại sao nameUtf16Units=105000?

Tên **Đà Nẵng & Việt Nam 😀** trong Java chiếm **21 UTF-16 code units**; emoji **😀** chiếm hai units. Có 5.000 item nên:

~~~text
21 UTF-16 code units/item × 5_000 items = 105_000 units
~~~

`nameCodeUnitSum` là tổng giá trị **Java char** qua tất cả names. Nó chỉ là **checksum giản đơn cho demo**, không phải hash an toàn hay bằng chứng đủ mạnh về XML semantic equality trong sản phẩm.

`qtySum=14995` vì các qty được tạo bằng `i % 7`, với i từ 0 đến 4999. Hai readers đều tính ra cùng tổng. `sameSummary=true` xác nhận cả hai đã thực hiện workload phù hợp với các trường được kiểm tra.

### 7.5. Ý nghĩa của các kết quả resource

- **outputOpenAfterWriterClose=true**: trên provider đang thử, XMLStreamWriter.close() không đóng OutputStream wrapper, phù hợp contract.
- **outputClosedAtScopeEnd=true**: sau `try (TrackedOutput out)`, ứng dụng đã bảo đảm output stream được đóng.
- **cursorInputClosedAtScopeEnd=true**, **eventInputClosedAtScopeEnd=true**: InputStreams đều đã đóng khi owner scope kết thúc, bất kể provider có đóng trước trong internal parser path hay không.
- **elapsedPositive=true**: thời gian đo có giá trị dương, không có nghĩa phép đo đã được thống kê đầy đủ.
- **heapSnapshotsAvailable=true**: JVM trả heap values hợp lệ để demo, **không chứng minh leak/peak memory**.

### 7.6. Vì sao demo không giữ mọi item trong List?

Mỗi parser chỉ giữ counters:

~~~text
rows
nameUnits
nameUnitSum
qtySum
~~~

`XMLStreamReader` tạm tạo một String cho mỗi leaf name/qty bằng getElementText nhưng không lưu lâu dài. `XMLEventReader` xử lý từng Characters event, chỉ có một StringBuilder nhỏ dùng lại cho qty. Tổng summary không giữ danh sách 5.000 item.

Đây là hướng **bounded retention**, nhưng không có nghĩa parser/provider không tạo temporary objects. Để biết allocated bytes/op và peak heap, cần JMH/JFR/profile với dataset và concurrency thực.

### 7.7. Giới hạn code mẫu

- XML data là cấu trúc đơn giản, application tự tạo, không có namespace hay mixed content phức tạp.
- Code giả định `<name>` là leaf text và `<qty>` là số; parser không phải một XML schema validator tổng quát.
- Đo một iteration sau hai warmups, không có nhiều forks/measurement windows.
- Timing gồm tạo XMLInputFactory, mở file, parse, đóng resources; không tách từng phase.
- Memory snapshot không phải peak/allocated bytes.
- `System.nanoTime` không đo CPU time trực tiếp.
- Không có quota bytes/depth/attributes; XML source do ứng dụng tự tạo.
- Không đo throughput dưới concurrency hoặc từ network.
- `Files.deleteIfExists(temp)` là cleanup demonstration; production cần giữ primary failure nếu xóa temp file cũng lỗi.
- Không so sánh với DOM hay các XML parsers khác; muốn thêm baseline phải kiểm soát cùng semantic work và security policy.

## 8. Cách chuyển ví dụ thành benchmark có giá trị

### 8.1. Lập bộ dữ liệu và ma trận

| Nhóm | Dữ liệu |
| --- | --- |
| Small XML | Hàng chục KB, chủ yếu startup overhead |
| Medium XML | Vài MB, có nhiều items |
| Large XML | Hàng trăm MB đến GB theo giới hạn môi trường |
| Many tiny elements | Cực nhiều START/END events |
| Large text leaf | Một hoặc vài fields rất dài |
| Deep nested XML | Rất sâu, kiểm tra stack/limits |
| Namespace-heavy | Nhiều QName/attribute bindings |
| Unicode | Tiếng Việt, emoji, special chars |
| Malformed XML | Fail fast + close resources |
| Hostile XML | DTD/external entities blocked |
| Streaming output | Input parse → transform → output, không materialize |

**Phải cùng correctness contract**. Ví dụ một parser chỉ đếm START_ELEMENT trong khi parser khác giải mã text và chuyển đổi DTO sẽ không có workload tương đương.

### 8.2. Bố trí JMH

Trong JMH, xác định rõ:

- **@State** cho dataset/setup với đúng lifecycle.
- **@Setup** để chuẩn bị dữ liệu ngoài vùng đo.
- **@Warmup** và **@Measurement** để thu nhiều iterations.
- **@Fork** để giảm ảnh hưởng JVM state của lượt trước.
- **@Benchmark** chạy operation có cùng semantic result.
- **Blackhole hoặc returning result** để compiler không tối ưu bỏ công việc.
- **@Param** cho dataset sizes / provider / coalescing khi thiết kế phép thử.
- GC allocation profiler khi môi trường hỗ trợ.

Không cần đưa một đoạn JMH code thiếu Maven setup và annotation processor vào README rồi tuyên bố có thể chạy bằng `javac` thuần. Nếu làm benchmark chính thức, theo **OpenJDK JMH official instructions** để tạo project riêng bằng Maven archetype, cài dependencies đúng và chạy generated benchmark jar.

### 8.3. Đối chiếu hai phép đo

Để kết luận hợp lý, cần có:

1. **Correctness assertion** của kết quả parser và escaped Unicode.
2. **Latency distributions** qua nhiều runs/forks, không chỉ một sample.
3. **Throughput** với cùng data volume.
4. **Allocated bytes/op** từ profiler, phân tích classes sinh allocations.
5. **GC pause/allocation rate** trong workload.
6. **Heap peak/live set** theo measurement protocol.
7. **Open file/socket handles** trước, trong và sau batch.
8. **JVM & provider version** và hardware/environment details.
9. **Confidence/variance**, không chỉ giá trị trung bình.
10. **Resource behavior under failure/cancellation**, không chỉ success path.

**Một phương án “nhanh hơn” vài phần trăm nhưng rò FileInputStream dưới lỗi** không phù hợp production. Performance và resource correctness phải được xem cùng nhau.

## 9. Giới hạn dữ liệu và bảo mật XML

### 9.1. XMLInputFactory an toàn

Khi đọc XML từ upload/API/partner, không dùng default parser config rồi tin rằng StAX streaming tự chống XXE.

~~~java
XMLInputFactory f = XMLInputFactory.newFactory();
f.setProperty(XMLInputFactory.SUPPORT_DTD, false);
f.setProperty(XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES, false);
f.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
f.setXMLResolver((publicId, systemId, baseUri, namespace) -> {
    throw new XMLStreamException("External entity denied");
});
~~~

Đây là chính sách được demo áp dụng. Nếu provider không hỗ trợ một security property bắt buộc, **fail closed**, không im lặng bỏ qua `IllegalArgumentException`. Tùy schema/security needs, còn cần từ chối DTD event và áp XML access limits.

### 9.2. Không tin streaming loại bỏ XML bombs

Nếu parser không chặn DTD và entity expansion, một payload nhỏ có thể tạo lượng text khổng lồ. Nếu một XML có hàng triệu nested levels hoặc một text field rất lớn, XMLStreamReader cũng có thể cạn CPU/heap/stack.

**Giới hạn cần có**:

- Bytes đầu vào (kể cả stream không có Content-Length).
- Max element depth.
- Max elements, namespaces và attributes.
- Max text length per element và toàn document.
- Timeout/deadline, cancellation và concurrency.
- Total output bytes khi transform XML.
- Configurable provider-specific entity limits được kiểm chứng.

### 9.3. Giới hạn độ sâu

Với parser dùng `next()` toàn bộ events, có thể kiểm tra độ sâu:

~~~java
int depth = 0;
final int maxDepth = 64;

while (xml.hasNext()) {
    int event = xml.next();
    if (event == XMLStreamConstants.START_ELEMENT) {
        if (++depth > maxDepth) {
            throw new XMLStreamException("XML depth limit exceeded");
        }
    } else if (event == XMLStreamConstants.END_ELEMENT) {
        --depth;
    } else if (event == XMLStreamConstants.DTD) {
        throw new XMLStreamException("DOCTYPE forbidden");
    }
}
~~~

**Mảnh này là một parser loop độc lập với `getElementText()`**. Nếu bạn dùng getElementText() để tiêu thụ END_ELEMENT trong một lần gọi, phải cập nhật logic depth/element scope tương ứng; đừng trộn và đếm lệch.

### 9.4. Giới hạn bytes stream

Với network input không có Content-Length đáng tin, dùng **bounded stream** hoặc một wrapper đếm bytes đọc để từ chối sớm khi vượt quota. Chỉ kiểm tra `Files.size(...)` trước khi parse có thể giúp với file đã xác thực nhưng không đủ nếu nội dung bị thay đổi hoặc luồng đến từ network.

Một parser chỉ dùng heap thấp nhưng chạy vô thời hạn trên XML vô hạn vẫn là vấn đề tài nguyên nghiêm trọng.

## 10. Tài nguyên và hủy tác vụ trong pipeline thật

### 10.1. Pipeline XML streaming tới DB/network

~~~text
Incoming HTTP InputStream
            │
            ▼
        XMLStreamReader
            │
            ▼
      Process current item
            │
            ▼
       Database / Queue / OutputStream
            │
      nếu downstream chậm
            ▼
   Backpressure / bounded queue
            │
            ▼
Close reader and input on completion/error/cancel
~~~

Nếu producer parse nhanh nhưng consumer ghi DB chậm, việc đưa item vào một unbounded queue làm heap tăng liên tục. Đây **không phải lỗi của StAX**, mà là một pipeline có **retention không giới hạn**.

Giải pháp gồm xử lý đồng bộ từng item, bounded queue, backpressure, batch kích thước hợp lý và cancellation token. Khi request đã bị hủy, dừng parser và đóng resources, không cố xử lý hết tài liệu chỉ vì hasNext còn true.

### 10.2. Không giữ parser/stream ngoài scope

Đừng trả **XMLStreamReader** từ repository/helper rồi đóng InputStream trước khi caller thực sự đọc; một reader có state và thường phụ thuộc resource đang mở. Tốt hơn:

- Nhận một **callback/consumer** để xử lý trong owner scope.
- Trả một **DTO/aggregate** đã độc lập với stream.
- Nếu cần async stream, xác định ownership/cancellation/release rõ và không share parser mutable giữa threads.

### 10.3. File descriptors và connection leaks

Đo số handles/file descriptors và pool sockets đang mở qua OS/JVM monitoring. Đặc biệt kiểm tra **steady state sau nhiều vòng thành công và lỗi**. Khi file descriptors tăng mãi trong load test, xem mọi đường `close()` — không dùng heap snapshots đơn độc để tìm I/O leak.

### 10.4. Temporary files

Nếu dùng file staging:

1. Tạo file trong thư mục được phép.
2. Quy định size/retention/permissions.
3. Ghi hoàn chỉnh, đóng writer/stream.
4. Validate thành phẩm khi cần.
5. Publish/rename atomic nếu filesystem hỗ trợ.
6. Cleanup khi thất bại hoặc cancel.
7. Nếu cleanup cũng lỗi, giữ primary exception và log/suppress lỗi cleanup đúng policy.

**XML parser.close không xóa file đầu vào.** Việc delete/retention là trách nhiệm riêng của application.

## 11. Đọc kết quả profiling và tối ưu có cơ sở

| Dấu hiệu quan sát | Nguyên nhân khả dĩ | Hành động kiểm tra |
| --- | --- | --- |
| Heap tăng tuyến tính theo số items | Lưu List/Map/DTOs không giới hạn | Kiểm tra retained references, bounded sink |
| Heap tăng vọt ở một leaf | getElementText/StringBuilder rất lớn | Chuyển sang xử lý text chunks, đặt max text length |
| Allocation rate cao ở event objects | XMLEventReader/event transformations tạo objects | Profile JFR/JMH; cân nhắc cursor nếu cùng semantics |
| CPU cao ở XML parser | Nhiều tiny nodes, validation, namespace work | Profile hot methods, kiểm tra provider/config |
| CPU thấp nhưng wall time cao | File/network I/O hoặc downstream blocking | JFR FileRead/SocketRead, thread states |
| GC pause cao | Allocations lớn, retained set hoặc heap pressure | JFR/GC logs, giảm giữ data, tuning có cơ sở |
| Độ trễ tăng khi concurrency cao | Contention, queue growth, pool saturation | Bounded concurrency, backpressure |
| Thời gian đo dao động mạnh | Warmup/GC/OS scheduling/cache | JMH nhiều forks, kiểm soát setup |
| Files open tăng theo requests | Thiếu InputStream/Reader.close | Kiểm tra owner scopes và error paths |
| XML output không đủ sau lỗi | Writer/OutputStream chưa flush/close hoặc disk full | Atomic staging, validate/publish sau close |
| Kết quả cursor/event khác | Một nhánh bỏ text/CDATA hoặc parse leaf khác | Correctness tests trước performance |
| Test pass JDK này, fail JDK khác | Provider/serializer/coalescing differences | Pin/report versions và integration tests |
| Heap snapshot delta âm | GC xảy ra giữa hai snapshots | Không diễn giải là “allocation âm” |
| Thêm profiler rồi latency tăng | Profiling overhead | Đo baseline/no-profiler, chọn settings hợp lý |
| Memory nhỏ nhưng process RSS lớn | Native buffers/metadata hoặc OS caching | Theo dõi native/process metrics |

### 11.1. Những “tối ưu” cần tránh

- Chỉ vì cursor reader thường hiệu quả hơn mà **thay toàn bộ event pipeline** không đo.
- Tắt security checks hoặc bật DTD để đạt throughput cao hơn với XML không đáng tin.
- Bỏ parsing validation và chỉ đếm thẻ để benchmark “nhanh hơn”.
- Cache `XMLStreamReader` và dùng chung giữa threads để tránh factory overhead.
- Giữ `char[]` từ getTextCharacters sau khi parser tiến event.
- Dùng `System.gc()` như cách dọn file handle hoặc đo peak memory.
- Dùng StringWriter cho output lớn rồi quảng cáo “StAX streaming”.
- Đổi input từ file sang byte[] ở một nhánh mà không đổi nhánh còn lại.
- Đọc XML không có byte/depth/time limits.
- Đóng InputStream ngay sau khi tạo reader nhưng trước khi đọc.
- Coi “không ném exception” đồng nghĩa XML được parse/serialize đúng và an toàn.

## 12. Kiểm thử đúng đắn và vòng đời

| Case | Assertion nên có |
| --- | --- |
| XML nhỏ hợp lệ | Cursor và event trả cùng semantic Summary |
| XML lớn nhiều items | Không giữ List toàn bộ, heap/GC được profile |
| Một text leaf lớn | Giới hạn text, không OOM không kiểm soát |
| Unicode/emoji | Đúng UTF-8, phân biệt char units/code points |
| `&amp;` và escaped markup | Hai readers decode text tương đương |
| CDATA split | Các text events được cộng đủ |
| Empty elements | Xử lý START_ELEMENT/END_ELEMENT đúng |
| Namespace + attributes | So namespaceURI/localName, không raw prefix |
| XML malformed | XMLStreamException, mọi resources được đóng |
| DOCTYPE/external entities | Không đọc file/network, fail closed |
| Vượt bytes/depth quotas | Dừng sớm và cleanup |
| File I/O failure | Primary IOException/XMLStreamException được giữ |
| Parser.close fail | Cleanup exception không che lỗi gốc |
| Output writer.close fail | Underlying sink vẫn được đóng |
| Cancel giữa document | Đóng network/file/pool resources, dừng xử lý |
| Multiple concurrent parses | Parser instance riêng, no shared mutable cursor |
| Test dưới GC/JIT conditions | Report version/flags và measurement variance |
| JMH benchmark | Warmup, forks, accuracy + allocations/op |
| JFR profiling | CPU, allocations, GC pauses, I/O bottlenecks |
| Temp file lifecycle | Không leak file sau pass/fail |
| Production provider | Runtime/version thực tế được test |

### 12.1. Test failure cleanup chủ động

Trong unit/integration tests, nên tạo một **InputStream wrapper đếm close calls**, sau đó ném IOException ở một vị trí được kiểm soát. Kiểm tra rằng owner scope gọi close ngay cả khi `XMLStreamReader.next()` chưa tới END_DOCUMENT.

Tương tự, một **OutputStream wrapper ném IOException sau N bytes** giúp test writer cleanup khi file/network write lỗi. Đây là cách đánh giá **lifecycle**, khác với chỉ đo heap. Không cần mở/đóng socket thật hoặc gây disk-full trên production để test.

### 12.2. Đo khi concurrency tăng

Dùng workload N concurrent parsers và một input data volume cố định, báo:

- Per-request latency distribution, not just aggregate throughput.
- Heap/RSS growth, allocations and GC.
- Open files/sockets/threads.
- Timeout/cancellation behavior.
- Downstream queue size và backpressure.
- Error rates và partial output cleanup.

Một parser chạy nhanh trong single-thread test nhưng tạo rất nhiều temporary objects có thể gây GC pressure mạnh khi N tăng. Đừng chọn theo benchmark đơn luồng nếu sản phẩm hoạt động dưới high concurrency.

## 13. Bài tập tự luyện

1. Chạy demo, giải thích vì sao 5.000 items tạo `nameUtf16Units=105000`.
2. Thay tên bằng một chuỗi chứa nhiều emoji và kiểm tra khác biệt giữa UTF-16 length và code point count.
3. Chạy nhiều lần, ghi timing/heapDelta và chứng minh hai dòng cuối thay đổi.
4. Thử đảo thứ tự đo cursor/event để xem ảnh hưởng JIT/disk cache.
5. Tăng ROWS lên 50.000 và 500.000 trong môi trường có tài nguyên cho phép, đo file size và runtime.
6. Thêm validation với `Files.size(temp)` và báo throughput MiB/s.
7. Thêm warmup/measurement iterations nhưng vẫn ghi rõ đây chưa phải JMH.
8. Chuyển phép đo sang JMH với nhiều forks và output correctness assertion.
9. Dùng JFR xem allocation hotspots trong XMLStreamReader và XMLEventReader.
10. Thử XML text leaf rất lớn, so `getElementText` với xử lý `CHARACTERS` từng event.
11. Thử `XMLInputFactory.IS_COALESCING` true/false, quan sát events và profiling results.
12. Dùng `getTextCharacters` trong current event để giảm một số allocations, không cache buffer.
13. Thêm một bounded queue giữa parser và consumer, đo heap khi consumer chậm.
14. Tạo malformed XML và xác nhận InputStream được đóng trong exception path.
15. Thử InputStream ném IOException giữa chừng và kiểm tra secondary close errors.
16. Tạo XML có DOCTYPE và external entity trỏ tới path giả; xác nhận parser từ chối.
17. Thêm giới hạn maxDepth và maxElementCount, giữ đúng element scope.
18. Dùng XMLOutputFactory ghi thẳng vào file thay vì StringWriter, đo retained heap.
19. Thêm profile với GC logs/JFR, so kết quả với/không có profiler.
20. Tạo response HTTP streaming và kiểm tra hủy request đóng đủ parser/input/output.
21. Thử parser event-driven có `XMLEventReader` rồi copy bằng XMLEventWriter; đo allocations và output correctness.
22. Viết một integration test report có JVM/provider versions, dataset hash, throughput, p95/p99, allocations/op, heap peak và resource handle counts.

## 14. Checklist production

- [ ] Định nghĩa performance goal: latency, throughput, memory, GC và tài nguyên I/O.
- [ ] Tách timing parser-only khỏi timing end-to-end.
- [ ] Hai phương án benchmark xử lý cùng XML và cùng semantic work.
- [ ] Report input bytes, element counts, XML shape, provider/JDK, GC flags và I/O mode.
- [ ] Không coi một lần nanoTime là benchmark thống kê.
- [ ] Dùng JMH có warmup/measure/forks khi đưa ra kết luận về tốc độ.
- [ ] Dùng JFR/JMC/GC logs để tìm allocations, heap/GC/CPU/I/O bottlenecks.
- [ ] Không nhầm heap snapshot delta với peak memory hoặc allocated bytes.
- [ ] XMLStreamReader hoặc XMLEventReader được chọn theo workload thực tế.
- [ ] Tránh giữ toàn bộ XML/DTOs trong StringWriter, StringBuilder hoặc List không giới hạn.
- [ ] Không gọi getElementText trên leaf có kích thước không giới hạn.
- [ ] Kiểm soát việc dùng getTextCharacters và lifetime của parser-owned buffer.
- [ ] XMLInputFactory chặn DTD/external entities; unsupported security settings phải fail closed.
- [ ] Có byte/depth/text/event quotas và cancellation deadlines.
- [ ] InputStream/Reader được đóng theo application ownership.
- [ ] XML parser reader được close dù parse thành công hoặc lỗi.
- [ ] Output writer được flush/close, underlying OutputStream/Writer được đóng riêng.
- [ ] Parser.close không được coi là bảo đảm owner source được giải phóng theo mọi provider.
- [ ] Cleanup failures được xử lý mà không che primary failure.
- [ ] Temporary files được dọn đúng policy, không rò tài nguyên nhạy cảm.
- [ ] Không share một mutable StAX reader/writer instance giữa threads khi không có contract rõ.
- [ ] Resource leaks được kiểm tra qua handles/sockets và fail-path tests, không chỉ heap.
- [ ] XML output được validate/roundtrip khi cần, encoding/declaration nhất quán.
- [ ] Benchmark under concurrency và đúng production provider/runtime đã xác minh.
- [ ] Không tắt các biện pháp an toàn XML để đạt tốc độ “tốt” giả tạo.

## Kết luận

**StAX có thể giảm nhu cầu lưu toàn bộ XML trong bộ nhớ**, nhưng lợi ích chỉ xuất hiện khi **toàn pipeline streaming, không giữ data vô hạn** và một phần tử riêng lẻ không buộc materialize quá lớn. **XMLStreamReader** là API cursor low-level; **XMLEventReader** là API event-oriented thuận tiện; **không thể xếp hạng tốc độ/heap cho mọi hệ thống nếu không đo với cùng semantic workload**.

Hãy dùng **System.nanoTime/MemoryMXBean** để học cách quan sát nhanh, nhưng **không gọi heap delta là allocated bytes hoặc peak heap**. Khi cần quyết định kiến trúc, dùng **JMH** cho phép đo hiệu năng có warmup/forks và **JFR/JMC** cho allocations/GC/CPU/I/O. Cuối cùng, phải xử lý **InputStream/Reader, StAX parser, writer, OutputStream/Writer và temporary files** theo ownership, bảo đảm đóng cả ở success/failure/cancellation. **Hiệu năng tốt mà leak file handles hoặc cho XXE vẫn là thiết kế không đạt yêu cầu.**

**Tài liệu chính thức và nguồn hiện hành:**

- [XMLStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamReader.html)
- [XMLEventReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.xml/javax/xml/stream/XMLEventReader.html)
- [XMLInputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLInputFactory.html)
- [XMLStreamWriter — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLStreamWriter.html)
- [XMLOutputFactory — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.xml/javax/xml/stream/XMLOutputFactory.html)
- [MemoryMXBean — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [MemoryUsage — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html)
- [System.nanoTime — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html#nanoTime())
- [Java Flight Recorder — Oracle Java SE 25 performance troubleshooting](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh/)
- [JAXP Security Guide — Java SE 17](https://docs.oracle.com/en/java/javase/17/security/java-api-xml-processing-jaxp-security-guide.html)