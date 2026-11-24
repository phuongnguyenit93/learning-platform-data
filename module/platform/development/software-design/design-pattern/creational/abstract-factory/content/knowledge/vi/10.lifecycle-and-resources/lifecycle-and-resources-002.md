# Xác định quyền sở hữu và nơi chịu trách nhiệm đóng tài nguyên

## 1. Vấn đề vòng đời trong Abstract Factory

**Abstract Factory** cho phép một client tạo ra các sản phẩm thuộc cùng một họ mà không phụ thuộc lớp triển khai cụ thể. Ví dụ, `LocalExportFactory` tạo bộ `LocalReportWriter` và `LocalAssetStore` để xuất báo cáo ra đĩa; `CloudExportFactory` tạo `CloudReportWriter` và `CloudAssetStore` để xuất báo cáo lên dịch vụ đám mây.

Các sản phẩm có thể nắm giữ **tài nguyên cần giải phóng**: file handle, stream, kết nối mạng, transaction, session hoặc một lượt mượn kết nối từ pool. Abstract Factory giải quyết *sản phẩm nào được tạo ra*, nhưng **không tự động quyết định ai được phép đóng các tài nguyên ấy**.

Nếu không có hợp đồng sở hữu rõ ràng, client có thể:

- Quên đóng stream do factory trả về, khiến file hoặc kết nối bị rò rỉ.
- Đóng connection pool đang được nhiều sản phẩm khác dùng, gây lỗi khi chạy.
- Đóng cùng một tài nguyên hai lần vì cả factory và client đều nghĩ mình là chủ sở hữu.
- Đóng sản phẩm theo thứ tự sai, làm sản phẩm khác không thể hoàn tất hoặc ghi dữ liệu đệm.
- Để factory tạo dở nhiều sản phẩm rồi ném ngoại lệ, khiến tài nguyên đã mở trước đó không được giải phóng.

Bài học thuộc chương **Vòng đời và tài nguyên**, tập trung vào cách **xác định quyền sở hữu và nơi chịu trách nhiệm đóng tài nguyên** khi triển khai Abstract Factory: viết hợp đồng rõ ràng, đặt thao tác đóng đúng phạm vi, xử lý các đường lỗi và kiểm thử được những quy tắc đó.

## 2. Phân biệt tạo ra, sử dụng và sở hữu

Ba khái niệm dễ bị nhầm lẫn:

| Khái niệm | Câu hỏi tương ứng | Ví dụ |
| --- | --- | --- |
| **Nơi tạo** (creator) | Ai cấp phát hoặc mở tài nguyên? | `CloudExportFactory` mở một `CloudReportWriter` |
| **Nơi sử dụng** (consumer/borrower) | Ai gọi phương thức trên tài nguyên? | `ReportExporter` gọi `writer.write(...)` |
| **Chủ sở hữu** (owner) | Ai quyết định thời điểm giải phóng và chịu trách nhiệm đóng? | Phương thức `export()` sở hữu writer đã nhận và đóng sau khi xuất xong |

**Người tạo không nhất thiết là chủ sở hữu sau khi trả về.** Factory có thể *chuyển giao quyền sở hữu* cho caller qua phương thức `openWriter()`. Ngược lại, một factory được tiêm sẵn kết nối dùng chung chỉ *mượn* kết nối đó; việc factory tạo ra nhiều product wrapper không cho phép nó tự đóng kết nối gốc.

Các từ cần xuất hiện trong hợp đồng API:

- **Owned:** Bên nhận có trách nhiệm `close()` khi không dùng nữa.
- **Borrowed:** Bên nhận chỉ được sử dụng trong thời hạn đã thỏa thuận; không đóng tài nguyên gốc.
- **Shared:** Nhiều bên dùng chung; cần một chủ sở hữu cấp cao hơn hoặc cơ chế quản lý vòng đời như pool, lease, reference counting.
- **Transferred:** Quyền đóng được chuyển rõ ràng từ bên giao sang bên nhận; bên giao không tiếp tục đóng cùng tài nguyên.

Đừng suy luận “có `new` ở đâu thì nơi đó luôn phải `close`”: với tài nguyên được trả về cho caller, **hợp đồng chuyển giao** mới quyết định trách nhiệm.

### 2.1. Đóng một lease khác với đóng tài nguyên gốc

Giả sử product dùng một kết nối lấy từ pool:

- `ReportWriter.close()` trả **lease** về pool và giải phóng buffer của riêng writer.
- `CloudPool.close()` đóng **pool** và các kết nối vật lý thuộc pool.
- Đóng writer **không đồng nghĩa** đóng cả pool; đóng pool khi writer còn dùng là sai vòng đời.

Với thư viện khác, phương thức `close()` trên handle có thể kết thúc kết nối thực. Luôn đọc hợp đồng của thư viện để biết close giải phóng **đối tượng nào**, không giả định theo tên gọi.

## 3. Lập sơ đồ quyền sở hữu theo phạm vi

Với ứng dụng xuất báo cáo, có ba phạm vi chính:

1. **Application scope:** Thành phần khởi tạo ứng dụng (composition root/bootstrap) sở hữu `CloudPool` dùng suốt vòng đời ứng dụng.
2. **Operation scope:** Mỗi lần gọi `ReportExporter.export()` sở hữu các product handle `AssetStore` và `ReportWriter` do factory trả về.
3. **Borrowed dependency:** `CloudExportFactory` mượn pool; `ReportExporter` mượn factory. Cả hai được sử dụng nhưng không tự đóng pool hoặc factory.

~~~mermaid
flowchart TB
    Root["Bootstrap / composition root"] -->|"sở hữu và đóng khi shutdown"| Pool["CloudPool dùng chung"]
    Root -->|"tạo và truyền vào"| Factory["CloudExportFactory"]
    Factory -.->|"chỉ mượn pool"| Pool
    Client["ReportExporter.export()"] -.->|"mượn factory"| Factory
    Client -->|"sở hữu và đóng sau export"| Assets["CloudAssetStore (handle)"]
    Client -->|"sở hữu và đóng sau export"| Writer["CloudReportWriter (handle)"]
    Factory -.->|"tạo sản phẩm cùng họ"| Assets
    Factory -.->|"tạo sản phẩm cùng họ"| Writer
    Assets -.->|"mượn lease từ"| Pool
    Writer -.->|"mượn lease từ"| Pool
~~~

**Quy tắc chính:** Mỗi tài nguyên cần **một chủ sở hữu có quyền đóng** tại một thời điểm. Nhiều đối tượng có thể cùng sử dụng, nhưng việc đóng phải được điều phối bởi hợp đồng vòng đời. Chủ sở hữu của wrapper hoặc lease có thể khác chủ sở hữu của tài nguyên vật lý bên dưới.

### 3.1. Bảng xác định nơi chịu trách nhiệm đóng

| Tài nguyên | Ai tạo/cấp | Chủ sở hữu khi sử dụng | Nơi đóng | Thời điểm đóng |
| --- | --- | --- | --- | --- |
| `AssetStore` cho một lần export | Concrete factory | Phạm vi `export()` | `try-with-resources` trong `export()` | Sau khi hoàn tất hoặc xảy ra lỗi |
| `ReportWriter` cho một lần export | Concrete factory | Phạm vi `export()` | `try-with-resources` trong `export()` | Trước `AssetStore` nếu writer còn cần asset khi finalize |
| Lease của kết nối dùng bởi writer | Pool cấp qua factory/product | Writer đang giữ lease | `ReportWriter.close()` theo hợp đồng sản phẩm | Khi writer kết thúc |
| `CloudPool` dùng chung | Bootstrap | Bootstrap | `try-with-resources`/shutdown hook tại bootstrap | Sau khi tất cả công việc dùng pool kết thúc |
| `CloudExportFactory` chỉ mượn pool | Bootstrap | Bootstrap quản lý tham chiếu | Không có hành động đóng riêng nếu factory không sở hữu resource | Ngừng dùng khi bootstrap dừng |
| Factory **tự tạo và sở hữu** pool | Concrete factory | Factory | `OwnedCloudExportFactory.close()` | Sau khi tất cả product/session phụ thuộc đã đóng |

Hai dòng cuối là **hai cách thiết kế thay thế**; cần chọn một hợp đồng thống nhất trong hệ thống, tránh cùng lúc để bootstrap và factory đều cho rằng mình sở hữu pool.

## 4. Thiết kế hợp đồng sản phẩm và factory

Ví dụ Java dưới đây dùng hai họ sản phẩm: **Local** và **Cloud**. Mỗi họ gồm `AssetStore` (lưu ảnh) và `ReportWriter` (ghi báo cáo tham chiếu ảnh). Tham chiếu ảnh từ Local có thể là đường dẫn tệp; của Cloud có thể là URI. Ghép nhầm một store Local với writer Cloud có thể tạo báo cáo chứa tham chiếu không hợp lệ.

Định nghĩa các abstract product và abstract factory:

~~~java
import java.io.IOException;

interface AssetStore extends AutoCloseable {
    // Mở bởi factory, quyền sở hữu handle được giao cho caller.
    String save(String name, byte[] bytes) throws IOException;

    @Override
    void close() throws IOException;
}

interface ReportWriter extends AutoCloseable {
    // Writer phải hiểu tham chiếu do AssetStore cùng họ tạo ra.
    void write(String text, String assetRef) throws IOException;

    @Override
    void close() throws IOException;
}

interface ExportFactory {
    // Mỗi lần gọi trả về một handle mới; caller phải close().
    AssetStore openAssets() throws IOException;
    ReportWriter openWriter() throws IOException;
}

record ExportPayload(String text, byte[] logoBytes) {}
~~~

Các interface trên **không buộc factory phải extends `AutoCloseable`**. Vì sao? Việc đóng factory chỉ hợp lý nếu bản thân factory sở hữu tài nguyên hoặc phạm vi quản lý phải giải phóng. Một factory đơn thuần mượn pool do bootstrap sở hữu có thể không có gì cần đóng.

Hợp đồng cần ghi rõ ngoài kiểu dữ liệu:

- Hai phương thức `open...()` chuyển quyền sở hữu **handle** cho caller.
- `AssetStore` và `ReportWriter` của cùng một factory phải tương thích.
- `close()` trên product giải phóng tài nguyên **thuộc product**; không tự đóng pool mượn từ nơi khác.
- Sau khi đóng handle, không tiếp tục dùng nó; nếu API có yêu cầu đóng nhiều lần an toàn, phải quy định và kiểm tra riêng. `AutoCloseable` không bảo đảm mọi implementation đều idempotent.
- Vòng đời factory hoặc pool phải bao trùm toàn bộ lượt sử dụng product phụ thuộc nó.

## 5. Đặt thao tác đóng ở cấp phương thức sử dụng

`ReportExporter` nhận factory từ bên ngoài qua constructor. Nó không tạo và không sở hữu factory; mỗi lần `export`, nó **nhận quyền sở hữu** hai product handle mới.

~~~java
import java.io.IOException;
import java.util.Objects;

final class ReportExporter {
    private final ExportFactory factory; // borrowed dependency

    ReportExporter(ExportFactory factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    void export(ExportPayload payload) throws IOException {
        // AssetStore được mở trước để sống lâu hơn ReportWriter.
        try (AssetStore assets = factory.openAssets();
             ReportWriter writer = factory.openWriter()) {

            String assetRef = assets.save("logo.png", payload.logoBytes());
            writer.write(payload.text(), assetRef);
        }
        // Java gọi writer.close() trước, rồi assets.close().
        // Cả hai vẫn được close nếu khối try ném ngoại lệ.
    }
}
~~~

Đây là một **ranh giới ownership** rõ ràng: ngay khi `openAssets()` thành công, biến `assets` nằm trong phạm vi do `try-with-resources` quản lý. Nếu `openWriter()` lỗi khi tạo, Java vẫn đóng `assets` đã khởi tạo thành công. Nếu `write()` lỗi, Java vẫn thử đóng writer và assets.

**Thứ tự đóng là thứ tự ngược lại lúc khai báo.** Ở ví dụ này `ReportWriter.close()` có thể phải flush báo cáo và còn cần `AssetStore` tồn tại, vì vậy khai báo assets trước writer để writer đóng trước assets. Thứ tự hợp lý khác nhau theo dependency thực tế; không có quy tắc luôn đóng writer trước store cho mọi ứng dụng.

### 5.1. Nơi đóng pool được dùng chung

Giả sử bootstrap khởi tạo pool và truyền vào concrete factory:

~~~java
// Mã minh họa ở composition root; các lớp Cloud* là adapter
// của hệ thống cụ thể, không phải lớp có sẵn của Java.
try (CloudPool pool = CloudPool.open(configuration)) {
    ExportFactory factory = new CloudExportFactory(pool);
    ReportExporter exporter = new ReportExporter(factory);

    exporter.export(payloadA);
    exporter.export(payloadB);
}
// Pool chỉ đóng sau khi cả hai lần export đã hoàn tất
// và các product handle của chúng đều đã được giải phóng.
~~~

`CloudExportFactory` và các product có thể giữ *tham chiếu mượn* tới pool. Bản thân `ReportExporter` không gọi `pool.close()`, vì pool còn phục vụ các lần export khác.

Nếu concrete factory **tự tạo pool**, có thể định nghĩa một lớp factory sở hữu tài nguyên và implements `AutoCloseable`. Khi đó nơi tạo factory (ví dụ bootstrap) phải gọi `factory.close()` lúc shutdown. Hợp đồng cần nói rõ factory có cho phép đóng khi còn product đang mở hay không: từ chối đóng, đợi các operation hoàn tất, hoặc đóng các session đang hoạt động. Không mặc định rằng `factory.close()` sẽ tự tìm và đóng mọi product đã từng trả về.

## 6. Tình huống nào yêu cầu ai đóng?

Trước khi viết một factory mới, trả lời những câu hỏi sau và ghi vào API documentation:

| Câu hỏi | Quyết định thiết kế cần có |
| --- | --- |
| Product được trả về là handle mới hay singleton dùng chung? | Handle mới thường chuyển quyền đóng cho caller; singleton cần chủ sở hữu ở scope cao hơn |
| Product có mượn tài nguyên gốc không? | `close()` của product chỉ giải phóng lease/phần riêng, không đóng tài nguyên gốc mượn |
| Có bao nhiêu operation dùng chung tài nguyên? | Dùng owner dài hạn cho shared pool và scope ngắn cho từng operation |
| Product nào còn cần product khác lúc finalize? | Đặt thứ tự khởi tạo/đóng bảo đảm dependency còn sống đủ lâu |
| Ai xử lý lỗi khi tạo được một phần họ sản phẩm? | Bên mở dở handle phải cleanup; caller đóng mọi handle đã nhận thành công |
| Task có thể chạy bất đồng bộ hay đồng thời không? | Owner đợi task hoàn tất hoặc hủy/cancel và join an toàn trước khi đóng |
| Thay concrete factory theo cấu hình/theme/tenant thế nào? | Đóng operation/handle của họ cũ theo hợp đồng trước khi giải phóng các dependency của họ cũ |
| Ai xử lý lỗi từ `close()`? | Quy định ghi log, propagate và kiểm tra suppressed exceptions; tránh che mất lỗi chính |

Một heuristic hữu ích: **owner thường trùng với phạm vi sử dụng nhỏ nhất có thể biết chắc tài nguyên không còn cần nữa**. Tuy nhiên, shared pool có nhiều consumer, vì thế owner thường nằm ở bootstrap/application scope.

## 7. Đường lỗi và cleanup đúng trách nhiệm

### 7.1. Factory mở dở sản phẩm rồi lỗi

Giả sử `CloudReportWriter` cần mở file đệm tạm và lấy một connection lease. Nếu mở file đệm thành công nhưng lấy lease thất bại, phương thức `CloudExportFactory.openWriter()` **chưa trả về writer nào cho caller**. Caller không có đối tượng để đóng file đệm. Concrete factory phải tự cleanup tài nguyên trung gian trước khi ném exception.

Ví dụ mã tạo sản phẩm có cleanup từng phần:

~~~java
ReportWriter openWriter() throws IOException {
    // Các lớp TemporaryBuffer, FactoryLease, CloudReportWriter
    // là adapter minh họa. Factory giữ ownership đến khi
    // constructor trả về thành công.
    TemporaryBuffer buffer = TemporaryBuffer.open();
    FactoryLease lease = null;

    try {
        lease = pool.borrowLease();
        // Contract: constructor không tự đóng tham số nếu ném lỗi.
        // Chỉ sau khi tạo thành công, writer sở hữu buffer và lease.
        return new CloudReportWriter(buffer, lease);
    } catch (IOException | RuntimeException cause) {
        if (lease != null) {
            try {
                lease.close();
            } catch (Exception closeError) {
                cause.addSuppressed(closeError);
            }
        }
        try {
            buffer.close();
        } catch (Exception closeError) {
            cause.addSuppressed(closeError);
        }
        throw cause;
    }
}
~~~

Đoạn trên cleanup **cả buffer và lease** nếu factory chưa tạo xong writer, đồng thời giữ lại lỗi gốc khi bước đóng cũng thất bại. Nó dựa trên contract rằng constructor chỉ nhận quyền sở hữu khi **trả về thành công**. Nếu thư viện cụ thể chuyển ownership ngay khi gọi constructor, phải tuân theo quy ước đó và tránh đóng lại resource đã được constructor tiếp nhận.

Một phương án dễ kiểm toán hơn là factory giữ các tài nguyên trong các scope đóng tự động, rồi **chuyển quyền sở hữu sau khi khởi tạo thành công** qua đối tượng trung gian/transfer API được định nghĩa rõ. Với mọi phương án, phải đảm bảo resource chỉ được đóng bởi một bên sau điểm chuyển giao.

### 7.2. Exception trong nghiệp vụ và exception lúc đóng

Với `try-with-resources`:

- Nếu `writer.write()` ném ngoại lệ và `writer.close()` cũng lỗi, exception từ `write()` được giữ làm lỗi chính; lỗi đóng xuất hiện trong `getSuppressed()`.
- Java vẫn thử đóng các resource còn lại theo thứ tự ngược, dù một lệnh close trước đó lỗi.
- Nếu phần thân không lỗi mà close lỗi, ngoại lệ của close có thể trở thành ngoại lệ được ném ra.
- Nếu một tài nguyên chưa khởi tạo thành công, chỉ các tài nguyên **đã khởi tạo** mới được scope tự động đóng.

Đừng dùng `finally { resource.close(); }` thiếu kiểm soát khi có nhiều resource phụ thuộc nhau: một exception từ close có thể làm mất nguyên nhân ban đầu hoặc ngăn resource kế tiếp được đóng.

Khi ghi log lỗi, cần xem cả exception chính lẫn suppressed exceptions nếu sự cố cleanup quan trọng. Không nuốt mọi lỗi đóng chỉ để luồng nghiệp vụ trông như thành công: có tài nguyên như writer chỉ hoàn tất flush khi `close()`.

### 7.3. Tài nguyên dùng chung và thao tác bất đồng bộ

Ví dụ xuất báo cáo trên thread khác:

~~~java
// Không đóng pool ngay sau submit nếu task vẫn đang chạy.
CompletableFuture<Void> task = CompletableFuture.runAsync(() -> {
    try {
        exporter.export(payload);
    } catch (IOException cause) {
        throw new CompletionException(cause);
    }
}, executor);

// Phạm vi sở hữu pool chỉ kết thúc sau khi task đã hoàn tất
// (hoặc được hủy và xác nhận không còn sử dụng tài nguyên).
task.join();
~~~

Đoạn trên minh họa **thứ tự vòng đời**; cần import `CompletableFuture` và `CompletionException` từ `java.util.concurrent`, đồng thời bắt ngoại lệ do `join()` báo nếu operation thất bại. Trong hệ thống thật, nên theo dõi tất cả task còn hoạt động, xử lý cancellation và shutdown của executor theo contract trước khi đóng dependency dùng chung.

Nếu product không thread-safe, không cho nhiều thread dùng một instance product chỉ vì chúng được tạo ra từ cùng factory. Một mẫu thường an toàn là chia sẻ **pool thread-safe** ở application scope và tạo **handle riêng cho từng operation**.

## 8. Kiểm thử ownership thay vì chỉ kiểm thử hành vi sản phẩm

Với Abstract Factory, kiểm thử rằng `CloudFactory` tạo đúng `CloudReportWriter` là cần thiết nhưng chưa đủ. Cần xác minh mọi đường kết thúc sẽ giải phóng tài nguyên đúng scope và không làm ảnh hưởng các sản phẩm đang dùng chung dependency.

### 8.1. Ma trận kiểm thử vòng đời

| Mã | Tình huống | Kết quả cần quan sát |
| --- | --- | --- |
| **OWN-01** | Export thành công | Writer và AssetStore đều được đóng đúng một lần |
| **OWN-02** | Không mở được writer sau khi mở assets | Assets vẫn được đóng; không cố đóng writer chưa được trả về |
| **OWN-03** | `save()` hoặc `write()` lỗi | Cả product handle đã mở đều được đóng; lỗi nghiệp vụ vẫn được báo |
| **OWN-04** | `writer.close()` lỗi | Vẫn thử đóng assets; lỗi đóng được giữ/lộ rõ |
| **OWN-05** | Hai lần export dùng chung pool | Đóng product của lần đầu không làm pool đóng hoặc gây lỗi cho lần sau |
| **OWN-06** | Factory trả về hai product cùng họ | Cả hai cùng thao tác được với asset reference hợp lệ, không trộn Local/Cloud |
| **OWN-07** | Chuyển từ Cloud sang Local | Kết thúc handle/session Cloud trước khi giải phóng tài nguyên Cloud phụ thuộc |
| **OWN-08** | Khởi tạo product thất bại giữa chừng | Factory dọn mọi resource nội bộ chưa chuyển giao |
| **OWN-09** | Có task bất đồng bộ khi shutdown | Không close shared dependency khi task vẫn sử dụng |

### 8.2. Kiểm thử thứ tự đóng bằng factory giả

Ví dụ dưới sử dụng các interface và `ReportExporter` ở phần trước. Fixture ghi lại các hành động để xác nhận **từng resource được mở, dùng và đóng đúng thứ tự** mà không cần kết nối Cloud thật.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class ResourceOwnershipTest {
    static class RecordingFactory implements ExportFactory {
        final List<String> events;
        final boolean failOpeningWriter;

        RecordingFactory(List<String> events, boolean failOpeningWriter) {
            this.events = events;
            this.failOpeningWriter = failOpeningWriter;
        }

        @Override
        public AssetStore openAssets() {
            events.add("open-assets");
            return new AssetStore() {
                @Override
                public String save(String name, byte[] bytes) {
                    events.add("save");
                    return "asset://logo";
                }

                @Override
                public void close() {
                    events.add("close-assets");
                }
            };
        }

        @Override
        public ReportWriter openWriter() throws IOException {
            events.add("open-writer");

            if (failOpeningWriter) {
                throw new IOException("cannot open writer");
            }

            return new ReportWriter() {
                @Override
                public void write(String text, String assetRef) {
                    events.add("write");
                }

                @Override
                public void close() {
                    events.add("close-writer");
                }
            };
        }
    }

    @Test
    void success_closes_writer_before_assets() throws IOException {
        List<String> events = new ArrayList<>();
        var exporter = new ReportExporter(
            new RecordingFactory(events, false)
        );

        exporter.export(new ExportPayload("Report", new byte[] {1}));

        assertEquals(List.of(
            "open-assets",
            "open-writer",
            "save",
            "write",
            "close-writer",
            "close-assets"
        ), events);
    }

    @Test
    void opening_writer_failure_still_closes_assets() {
        List<String> events = new ArrayList<>();
        var exporter = new ReportExporter(
            new RecordingFactory(events, true)
        );

        IOException failure = assertThrows(IOException.class, () ->
            exporter.export(new ExportPayload("Report", new byte[] {1}))
        );

        assertEquals("cannot open writer", failure.getMessage());
        assertEquals(List.of(
            "open-assets",
            "open-writer",
            "close-assets"
        ), events);
    }
}
~~~

Hai test trên chứng minh behavior của `try-with-resources` ở tầng client. Chúng **không** chứng minh concrete `CloudExportFactory` quản lý lease/pool đúng. Hãy bổ sung integration test dùng factory thật hoặc fake pool có bộ đếm `borrow()`/`release()`/`close()` để xác nhận **product close trả lease**, **bootstrap close pool**, và **pool không bị đóng sớm**.

### 8.3. Kiểm thử trên hai họ sản phẩm

Với mỗi concrete factory (Local, Cloud), chạy bộ kiểm thử hợp đồng giống nhau:

1. Mở cả hai loại product và xác nhận chúng tương thích; lưu asset rồi ghi report với reference được tạo ra.
2. Đóng cả hai và kiểm tra không còn handle/lease sở hữu bởi operation.
3. Tiêm lỗi vào từng bước mở, sử dụng và đóng; xác nhận resource đã mở được cleanup.
4. Nếu factory dùng shared pool, mở hai operation nối tiếp và một lần song song trong phạm vi được hỗ trợ; chứng minh một operation không kết thúc resource của operation kia.

Việc hai họ có cơ chế tài nguyên khác nhau không làm thay đổi **bất biến ownership** mà client cần tuân theo. Tuy nhiên, assertion về leak phải sử dụng counter/hook do implementation hoặc thư viện cho phép, tránh suy từ số object Java chưa được garbage collect.

## 9. Những lỗi thiết kế hay gặp

### “Factory tạo thì factory phải tự đóng mọi product”

Không nhất thiết. Factory thường **chuyển quyền sở hữu handle** ngay khi trả về, vì client biết chính xác khi nào một operation kết thúc. Nếu factory âm thầm giữ danh sách mọi product để đóng ở shutdown, nó có thể giữ tài nguyên quá lâu, làm tăng memory footprint và số file handle hoặc connection đang mở.

Nếu yêu cầu là factory quản lý toàn bộ session, hãy biểu diễn rõ bằng `ExportSession extends AutoCloseable` do factory tạo, với hợp đồng session sở hữu các product trong đó. Khi đó client sở hữu **session**, thay vì tự đóng từng product, và session chịu trách nhiệm teardown theo dependency order.

### “Tất cả cùng dùng pool nên đóng product sẽ đóng pool”

Sai khi pool được mượn. Product close chỉ nên trả lease hoặc giải phóng state của product. Đóng pool phải do owner ở scope dài hơn thực hiện. Nếu tài nguyên gốc được tạo riêng cho product và thuộc độc quyền product, close product có thể đóng luôn tài nguyên gốc; cần phân biệt hai trường hợp bằng contract.

### “Java có GC nên không cần close”

Garbage collector quản lý bộ nhớ heap, không bảo đảm giải phóng kịp thời file handle, socket hoặc transaction. Đối với resource có vòng đời hữu hạn, dùng cơ chế close xác định và test được.

### “Gọi close nhiều lần luôn an toàn”

`AutoCloseable` không tự cam kết mọi implementation cho phép gọi close nhiều lần an toàn. Hãy thiết kế single owner, ngăn double-close, và chỉ yêu cầu idempotent nếu đây là một phần của hợp đồng product.

### “Đóng factory trước, product sẽ tự xử lý”

Nếu product còn lệ thuộc pool do factory sở hữu, đóng factory trước có thể khiến lệnh flush, commit hoặc release của product thất bại. Phân rã dependency và đóng theo thứ tự phù hợp, thường là **operation/product trước, shared dependency sau**.

## 10. Checklist khi review code

- [ ] Mọi phương thức factory trả về resource đều mô tả **owned** hay **borrowed**.
- [ ] Với từng resource, có một owner cụ thể và một điểm close rõ ràng.
- [ ] Caller đóng các product handle đã nhận, kể cả khi bước tiếp theo thất bại.
- [ ] Factory tự dọn những resource đã mở nhưng chưa chuyển giao khi khởi tạo product lỗi.
- [ ] Product close không tự ý đóng shared dependency mà nó mượn.
- [ ] Thứ tự đóng bảo đảm dependency còn sống trong lúc flush/finalize.
- [ ] Bootstrap/owner chỉ đóng shared pool sau khi các operation phụ thuộc đã hoàn tất.
- [ ] Các lỗi trong use/close đều được xử lý và quan sát đúng hợp đồng.
- [ ] Test có kiểm tra thành công, lỗi khi tạo giữa chừng, lỗi khi sử dụng, lỗi close và trường hợp dùng chung.
- [ ] Khi thêm một họ sản phẩm mới, vẫn áp dụng cùng quy tắc sở hữu cho các abstract product.

## 11. Bài tập thực hành

Ứng dụng thanh toán sử dụng `PaymentFactory` để tạo hai sản phẩm cùng họ: `PaymentGateway` và `ReceiptWriter`. Có hai concrete factory: `SandboxPaymentFactory` và `ProductionPaymentFactory`. Cả hai cùng mượn một `HttpClientPool` do bootstrap khởi tạo. Một lệnh thanh toán chạy trong một operation; biên lai chỉ được viết sau khi xác nhận giao dịch.

**Yêu cầu:**

1. Xác định ai sở hữu factory, pool, gateway handle và receipt writer handle; đặt thao tác close ở scope phù hợp.
2. Thiết kế thứ tự tạo/đóng nếu `ReceiptWriter.close()` phải gửi biên lai qua gateway đang mở.
3. Cho biết cleanup phải diễn ra ở đâu khi factory đã tạo được gateway nhưng chưa tạo được receipt writer.
4. Liệt kê ba test cần có khi một trong hai lệnh `charge()` và `writeReceipt()` ném exception.
5. Phân tích vì sao không nên để một gateway close toàn bộ `HttpClientPool` dùng chung.

**Gợi ý:** Bootstrap sở hữu pool; lớp điều phối thanh toán mượn factory và sở hữu các handle được trả về cho mỗi operation. Nếu receipt writer cần gateway để hoàn tất, mở gateway trước writer để đóng writer trước gateway. Caller đóng gateway nếu bước tạo writer thất bại; factory đóng tài nguyên nội bộ chưa chuyển giao. Cần test đường thành công, thất bại khi tạo một phần, lỗi trong nghiệp vụ hoặc close, đồng thời kiểm tra pool vẫn dùng được cho operation tiếp theo.

## 12. Ghi nhớ

Trong Abstract Factory, **việc tạo đúng họ sản phẩm** và **quản lý vòng đời đúng** là hai trách nhiệm liên quan nhưng khác nhau. Hãy xác định resource nằm ở scope nào, ai thực sự sở hữu nó và lúc nào owner biết chắc nó không còn được dùng. Factory có thể chuyển quyền sở hữu product handle cho caller hoặc giữ quyền sở hữu shared dependency, tùy hợp đồng thiết kế. Đóng đúng nơi, đúng thứ tự và trên cả đường lỗi giúp các họ sản phẩm cộng tác an toàn mà không rò rỉ hoặc đóng nhầm tài nguyên.
