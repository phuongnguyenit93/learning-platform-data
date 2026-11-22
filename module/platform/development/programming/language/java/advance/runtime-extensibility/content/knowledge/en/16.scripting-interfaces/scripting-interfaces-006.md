# Thiết kế API Java được đưa vào kịch bản với quyền hạn tối thiểu

Ứng dụng Java có thể cho phép các đoạn **kịch bản (script)** tính toán quy tắc, tạo báo cáo, tùy biến quy trình hoặc gọi một số chức năng được host cung cấp. Một cách tích hợp phổ biến là đưa đối tượng Java vào môi trường script, để script gọi phương thức của đối tượng ấy. Ví dụ: script chỉ được phép đọc danh sách ghi chú thuộc tenant hiện tại và tạo một ghi chú mới, **không** được nhận toàn bộ `DataSource`, `EntityManager`, `ApplicationContext`, `HttpClient`, `ClassLoader` hay quyền truy cập filesystem.

Câu hỏi thiết kế cốt lõi là: **đối tượng nào được công bố, từng phương thức cấp quyền gì, ai xác thực quyền và giới hạn tài nguyên, và động cơ script có thật sự ngăn script đi vòng qua API đó không?**

Phương châm: **cung cấp các capability nhỏ, theo tác vụ; mặc định không cấp quyền; kiểm tra ở phía Java mỗi lần gọi; và không nhầm interface hẹp với sandbox an toàn.**

## 1. Xác định mô hình tin cậy trước khi viết API

Có ít nhất ba trường hợp khác nhau:

| Nguồn script | Mức tin cậy | Cách tiếp cận |
|---|---|---|
| Script do nhóm phát triển viết, review và triển khai cùng ứng dụng | Tương đương mã nội bộ sau khi đã kiểm soát quy trình phát hành | API hẹp giúp giảm coupling và lỗi vận hành; vẫn kiểm soát logic và version |
| Script do quản trị viên/đối tác cấu hình trong sản phẩm | Tin cậy **một phần**; có thể sai hoặc vượt phạm vi dự định | Capability riêng, kiểm tra tenant/quyền, kiểm toán, quota, hạn chế engine host interop |
| Script do người dùng không tin cậy gửi lên | Đầu vào **không tin cậy** | Không xem `Bindings` hay interface Java là ranh giới bảo mật; dùng môi trường thực thi cô lập và gateway kiểm soát capability |

**Phân biệt “giới hạn API” với “sandbox”:**

- Interface Java nhỏ chỉ mô tả những thao tác ứng dụng **muốn** công bố.
- Script engine có thể cho phép truy cập Java class, reflection, method có sẵn, global bindings, runtime internals hoặc thư viện khác. Nếu vậy, script **không cần** đi qua interface mà bạn dự tính.
- Mã chạy cùng JVM có thể dùng cùng heap, thread, process identity và quyền hệ điều hành, trừ khi có một cơ chế cô lập thực sự. `ClassLoader`/JPMS không phải sandbox cho mã không tin cậy.
- Một engine cấm host interop có thể giúp thu hẹp quyền truy cập theo cấu hình cụ thể, nhưng phải kiểm tra chính xác phiên bản/engine và toàn bộ đường thoát (callbacks, objects, globals, imports, native access). Chỉ gọi `engine.put("api", facade)` không chứng minh sandbox.
- Với script không tin cậy, nên chạy trong **tiến trình/container cô lập**, có giới hạn CPU, bộ nhớ, thời gian, mạng, filesystem, secrets; chỉ trao đổi với host qua giao thức yêu cầu đã được xác thực.

**Bài này chủ yếu thiết kế bề mặt capability Java và cách đưa vào script.** Biện pháp cô lập ở mức hệ điều hành là tầng bảo vệ bổ sung bắt buộc khi mô hình đe dọa yêu cầu, chứ không thể thay bằng việc viết interface đẹp.

## 2. Khác nhau giữa API nghiệp vụ và quyền truy cập vào host

Một tích hợp quá rộng dễ thấy:

```java
// Minh họa thiết kế KHÔNG NÊN dùng cho script hạn chế quyền:
bindings.put("app", applicationContext);
bindings.put("database", dataSource);
bindings.put("fileSystem", fileService);
bindings.put("http", httpClient);
```

Đoạn trên chỉ minh họa ý tưởng, **không phải chương trình chạy độc lập**. Việc đưa service tổng quát vào script thường gây rủi ro:

- `applicationContext` cho phép lấy thêm bean/service ngoài mục đích đã được phê duyệt.
- `dataSource` hoặc repository tổng quát có thể đọc/sửa nhiều bảng, bỏ qua tầng phân quyền nghiệp vụ.
- `fileService` với đường dẫn tùy ý mở cửa cho path traversal, đọc secrets hoặc ghi file ngoài phạm vi.
- `httpClient` nhận URL tùy ý có thể tạo yêu cầu tới endpoint nội bộ hoặc tài nguyên nhạy cảm (SSRF).
- Trả về entity có quan hệ lazy, object manager hoặc đối tượng runtime có thể để lộ nhiều chức năng hơn ý định ban đầu.

Thay vào đó, công bố API theo **động từ nghiệp vụ có phạm vi rõ ràng**:

```text
Script
  |
  +-- notesRead.list(limit)
  +-- notesRead.find(id)
  |
  +-- notesWrite.add(text)    [chỉ khi được cấp quyền]
  |
  X-- database.query(sql)
  X-- files.read(path)
  X-- http.request(url)
  X-- runtime.getClassLoader()
```

Bề mặt API tốt **không** chỉ là interface `NotesService` chứa mọi thao tác rồi kiểm tra bằng cờ `admin`. Hãy tách các capability độc lập để script chỉ nhận chức năng được phép ở lượt thực thi hiện tại.

## 3. Thiết kế capability hẹp và theo nguyên tắc deny-by-default

### 3.1. Hợp đồng đầu vào/đầu ra

Ví dụ cho nghiệp vụ ghi chú:

| Capability | Phương thức | Quyền được cấp | Giới hạn |
|---|---|---|---|
| `NotesRead` | `list(int limit)` | Xem ghi chú **của tenant hiện tại** | `1 <= limit <= 5` trong demo |
| `NotesRead` | `find(String id)` | Tra cứu **một ID thuộc tenant hiện tại** | Không lộ liệu ID có tồn tại ở tenant khác |
| `NotesWrite` | `add(String text)` | Tạo ghi chú **cho tenant hiện tại** | Validate text, hạn mức ghi và audit |
| **Không công bố** | `deleteAll()` | Không có | Không expose phương thức nguy hiểm |
| **Không công bố** | `findByTenant(String tenantId)` | Không có | Tenant do host quyết định, không do script đưa vào |
| **Không công bố** | `executeSql(String sql)` | Không có | Không truyền lệnh SQL tùy ý |

Một script chỉ đọc phải nhận **reader**, không mặc định nhận writer. Nếu cần ghi, host chỉ cấp **writer trong bối cảnh đã được ủy quyền**; bên triển khai writer vẫn kiểm tra quota, phạm vi và điều kiện nghiệp vụ.

API trả về các **DTO nhỏ và bất biến** (record chứa String/số/boolean, danh sách bất biến), thay vì entity/repository/`Connection` hoặc object chứa handle, callback, stream mở. DTO chỉ nên gồm những trường script thực sự cần. Không tiết lộ token, cấu hình bí mật, đường dẫn máy chủ hoặc đối tượng principal đầy đủ.

### 3.2. Thông tin quyền phải do host tạo

Không làm:

```java
// SAI: script được quyết định tenant của dữ liệu.
List<NoteView> listNotes(String tenantId);
```

Nên tạo capability đã gắn với context được xác thực:

```java
// Ý tưởng: host dựng context từ request đã xác thực,
// sau đó cung cấp API không cho script truyền tenantId.
NotesRead read = capabilityFactory.readFor(authenticatedTenant);
```

Hai đoạn là **minh họa hợp đồng**. `authenticatedTenant` không được lấy từ biến tự khai báo trong script; `capabilityFactory` chỉ là tên minh họa cho lớp host thực tế.

Một execution context đáng tin cậy thường gồm: `runId`, `actorId`, `tenantId`, tập operation được cấp, hạn mức và deadline. Nguyên tắc quan trọng là **mọi phương thức có quyền thực hiện side effect đều tự kiểm tra context tại thời điểm gọi**, không coi việc đưa object vào `Bindings` là bước phân quyền đủ dùng cho cả vòng đời.

### 3.3. Quyền tối thiểu theo bốn chiều

1. **Hành động**: cho phép đọc, ghi mới hay gửi event, không tự mở rộng sang xóa/chuyển quyền/quản trị.
2. **Dữ liệu**: tenant, owner, tập ID, field nào đọc được; áp dụng ngay trong truy vấn repository ở phía host.
3. **Tài nguyên**: số lần gọi, số bản ghi, byte dữ liệu, thời gian, concurrency, budget external API.
4. **Thời gian**: capability có hiệu lực trong một lượt chạy hoặc thời gian ngắn; có cơ chế thu hồi, và không sử dụng lại object gắn quyền cũ giữa các request.

Đừng đánh đồng “script nhìn thấy phương thức” với “script được phép thực hiện phương thức”. Một kiểm tra quyền được lưu bên trong service/gateway và được thực hiện lặp lại tại ranh giới thao tác là điểm quan trọng cho defense in depth.

## 4. Ví dụ Java 17 chạy được: chỉ công bố reader/writer có phạm vi

Ví dụ này tập trung vào **Java API phía host**. Nó **không cần JavaScript engine**: `main` đóng vai một lượt gọi thử từ môi trường script để kiểm tra hợp đồng và stdout trên JDK 17. Trong ứng dụng thật, host mới quyết định có đưa `NotesRead` và `NotesWrite` vào script hay không.

Các chính sách:

- Reader tự cố định tenant `acme`, không có hàm tìm theo tenant do script chỉ định.
- `find` trả `Optional.empty()` cho ID ở tenant khác **giống như ID không tồn tại**, tránh tiết lộ sự tồn tại qua phản hồi.
- `list` chỉ cho tối đa 5 bản ghi.
- Writer chỉ có `add`; kiểm tra input, số lượt ghi và tự gắn tenant khi lưu.
- DTO `NoteView` là Java record chứa hai String; dữ liệu nội bộ `StoredNote` không bị trả trực tiếp.

Lưu thành **`ScriptApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class ScriptApiDemo {

    private record StoredNote(String id, String tenant, String text) {}

    // DTO bất biến: chỉ dữ liệu được phép trả cho script.
    public record NoteView(String id, String text) {}

    public interface NotesRead {
        List<NoteView> list(int limit);
        Optional<NoteView> find(String id);
    }

    public interface NotesWrite {
        String add(String text);
    }

    // Giả lập kho dữ liệu phía host, không công bố cho script.
    private static final class Store {
        final List<StoredNote> notes = new ArrayList<>(List.of(
                new StoredNote("n1", "acme", "Alpha"),
                new StoredNote("n2", "other", "Private")));
        int sequence = 3;
    }

    private static final class ScopedRead implements NotesRead {
        private final Store store;
        private final String tenant;

        ScopedRead(Store store, String tenant) {
            this.store = store;
            this.tenant = tenant;
        }

        @Override
        public List<NoteView> list(int limit) {
            if (limit < 1 || limit > 5) {
                throw new IllegalArgumentException("LIMIT_OUT_OF_RANGE");
            }
            return store.notes.stream()
                    .filter(n -> tenant.equals(n.tenant()))
                    .limit(limit)
                    .map(n -> new NoteView(n.id(), n.text()))
                    .toList();
        }

        @Override
        public Optional<NoteView> find(String id) {
            if (id == null || !id.matches("n[0-9]+")) {
                throw new IllegalArgumentException("INVALID_ID");
            }
            return store.notes.stream()
                    .filter(n -> tenant.equals(n.tenant())
                            && id.equals(n.id()))
                    .findFirst()
                    .map(n -> new NoteView(n.id(), n.text()));
        }
    }

    private static final class ScopedWrite implements NotesWrite {
        private final Store store;
        private final String tenant;
        private int remainingWrites;

        ScopedWrite(Store store, String tenant, int writeBudget) {
            this.store = store;
            this.tenant = tenant;
            this.remainingWrites = writeBudget;
        }

        @Override
        public String add(String text) {
            if (remainingWrites == 0) {
                throw new SecurityException("WRITE_BUDGET_EXCEEDED");
            }
            if (text == null || text.isBlank() || text.length() > 40) {
                throw new IllegalArgumentException("INVALID_TEXT");
            }

            String id = "n" + store.sequence++;
            store.notes.add(new StoredNote(id, tenant, text.trim()));
            remainingWrites--;
            return id;
        }
    }

    public static void main(String[] args) {
        Store store = new Store();

        // Trong ứng dụng thật: tenant phải lấy từ host đã xác thực.
        NotesRead read = new ScopedRead(store, "acme");
        NotesWrite write = new ScopedWrite(store, "acme", 1);

        System.out.println("before=" + read.list(5));
        System.out.println("otherTenant=" + read.find("n2").isPresent());

        try {
            write.add("  ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        System.out.println("created=" + write.add("Beta"));
        System.out.println("after=" + read.list(5));

        try {
            write.add("Gamma");
        } catch (SecurityException ex) {
            System.out.println("blocked=" + ex.getMessage());
        }
    }
}
```

Biên dịch/chạy bằng **JDK 17+**:

```bash
javac -encoding UTF-8 ScriptApiDemo.java
java ScriptApiDemo
```

Stdout đã kiểm tra với JDK có hỗ trợ Java 17:

```text
before=[NoteView[id=n1, text=Alpha]]
otherTenant=false
invalid=INVALID_TEXT
created=n3
after=[NoteView[id=n1, text=Alpha], NoteView[id=n3, text=Beta]]
blocked=WRITE_BUDGET_EXCEEDED
```

**Giải thích:**

- `before` chỉ chứa `n1` của tenant `acme`; dữ liệu `n2` thuộc tenant `other` không xuất hiện.
- `otherTenant=false` chứng minh lookup bằng ID `n2` không làm lộ nội dung hoặc xác nhận ID của tenant khác.
- Một text toàn khoảng trắng bị từ chối trước khi tạo dữ liệu; không tiêu hao hạn mức ghi.
- `created=n3` và `after` chứng minh một thao tác ghi hợp lệ được gắn với tenant hiện tại.
- Khi đã dùng hết một quyền ghi, lời gọi tiếp theo bị từ chối.

**Ranh giới của ví dụ:** dữ liệu nằm trong `ArrayList`, mã giả lập chỉ chạy một thread và quota là một số nguyên trong instance. Đây **không phải** repository, authorization framework hay sandbox production. Trong hệ thống nhiều luồng/nhiều instance, quyền truy cập, ID, số lượng ghi và quota phải được kiểm soát **nguyên tử** trong transaction/store/gateway; không cấp quyền bằng biến cục bộ dễ bị nhân bản hoặc dùng lại ngoài lượt chạy.

**Quan trọng:** ngay cả khi chỉ đưa object dưới kiểu `NotesRead` vào một script engine, điều đó **không đảm bảo** engine không thể introspect lớp triển khai, truy cập `getClass()` hoặc sử dụng khả năng Java interop khác. Việc giới hạn Java interface mô tả API được phê duyệt; để chống script độc hại cần kiểm soát cơ chế gọi host và quyền thực thi ở tầng engine/tiến trình.

## 5. Đưa capability vào kịch bản qua javax.script: chỉ là cơ chế binding

`javax.script` (JSR 223, module `java.scripting`) có `ScriptEngine`, `ScriptEngineManager` và `Bindings`. Cơ chế này cho phép ứng dụng truyền giá trị vào môi trường kịch bản, nhưng **không mặc nhiên cung cấp sandbox**.

Đoạn sau là **mã minh họa trong phương thức** với các biến `engine`, `scriptSource`, `notesRead`, `notesWrite` và `canWrite` đã được host cung cấp:

```java
Bindings bindings = engine.createBindings();
bindings.put("notesRead", notesRead);

if (canWrite) {
    bindings.put("notesWrite", notesWrite);
}

Object result = engine.eval(scriptSource, bindings);
```

Muốn dùng cần import `javax.script.Bindings`, `javax.script.ScriptEngine`, `javax.script.ScriptException` và chọn/khởi tạo một engine phù hợp. Đây là **ví dụ cho script đã được tin cậy và engine được cấu hình/đánh giá riêng**, không phải biện pháp bảo vệ script không tin cậy.

### 5.1. Lưu ý quan trọng về engine và Java 17

- **JDK 17 không còn Nashorn JavaScript engine đi kèm** (Nashorn được loại khỏi JDK từ phiên bản 15). Vì vậy `new ScriptEngineManager().getEngineByName("JavaScript")` có thể trả `null` nếu ứng dụng chưa đưa một script engine phù hợp vào classpath/module path.
- JSR 223 là API tích hợp; quy tắc host access, class lookup, reflection, thread behavior, timeouts và những builtin khả dụng **phụ thuộc vào engine cụ thể**, không thể suy ra chỉ từ `Bindings`.
- Nếu sử dụng engine bên ngoài (ví dụ một JS engine tương thích JSR 223 hoặc runtime scripting khác), phải đọc tài liệu của **đúng engine/phiên bản** và cấu hình host access theo allowlist. Đừng giả định rằng mọi engine tôn trọng Java interface dưới dạng giới hạn quyền.
- `engine.createBindings()` tạo map binding cho một lượt đánh giá, nhưng các **global bindings, objects được engine giữ lại, thư viện/extension và bộ nhớ engine tái sử dụng** vẫn có thể ảnh hưởng tới isolation. Không tái sử dụng engine/context giữa những tenant khác nhau nếu không có bảo đảm isolation rõ ràng.
- `engine.eval(...)` có thể ném `ScriptException`; một script còn có thể trigger các lỗi runtime từ Java capability được gọi. Phân biệt lỗi script với `PERMISSION_DENIED` hoặc lỗi hạ tầng.

Một đoạn kiểm tra khả năng có engine, **không thực thi script**:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");

if (engine == null) {
    throw new IllegalStateException("SCRIPT_ENGINE_UNAVAILABLE");
}
```

Đoạn này là minh họa, cần import `javax.script.ScriptEngine` và `javax.script.ScriptEngineManager`. **Không tự động cài/tải engine** ở thời điểm request để sửa lỗi; engine và các dependency phải được quản lý, xác minh và triển khai theo quy trình tin cậy.

### 5.2. Nếu script không tin cậy: gửi command thay vì Java object

Kiến trúc phòng thủ mạnh hơn:

```text
Client / script không tin cậy
             |
             v
     Sandbox process
 (không có host Java classpath,
  không secrets, mạng/FS bị giới hạn)
             |
             | JSON/IPC: op + arguments
             v
      Host capability gateway
    - xác thực caller/run/tenant
    - allowlist operation
    - kiểm tra input và quota
    - enforce ACL/row-level scope
    - audit và giới hạn output
             |
             v
        Nghiệp vụ Java
             |
             v
      DTO đã được lọc
```

Ví dụ giao thức yêu cầu:

```json
{"op":"notes.list","args":{"limit":3}}
```

hoặc:

```json
{"op":"notes.add","args":{"text":"Chào nhóm"}}
```

Đây là **ví dụ dữ liệu giao thức**, không phải yêu cầu mạng thực tế trong chương trình demo. Gateway chỉ chấp nhận `op` đã đăng ký. Nó **không** có `className`, `methodName`, `javaExpression` hoặc `url` tùy ý để script yêu cầu host gọi reflection hoặc đọc tài nguyên.

Các quyền tenant/actor được gắn bằng danh tính xác thực trên kênh IPC/session/token giới hạn quyền do **host** kiểm soát, không tin trường `tenantId` tự gửi trong JSON. Với thay đổi dữ liệu có side effect, dùng operation ID/idempotency key và log kiểm toán phù hợp. Nên tránh trả nguyên stack trace hoặc thông tin nội bộ qua gateway.

## 6. Chặn đường mở rộng quyền qua tham số, giá trị trả về và lỗi

### 6.1. Kiểm tra tham số ở mọi lời gọi

API theo nguyên tắc least privilege không nhận các tham số quá tổng quát. Ví dụ:

- Thay `readFile(String path)` bằng `readApprovedTemplate(TemplateId id)`; host map ID sang template đã đăng ký.
- Thay `httpGet(String arbitraryUrl)` bằng `fetchExchangeRate(CurrencyCode code)` qua endpoint cố định.
- Thay `runSql(String sql)` bằng `getSalesTotal(ReportScope scope)` đã kiểm tra phân quyền.
- Thay `sendEmail(String to, String body)` bằng `requestApprovedNotification(RecipientId id, TemplateId template, Variables vars)` với phạm vi gửi và hạn mức.
- Thay `queryUsers(String tenant)` bằng `listVisibleUsers(int limit)`, lấy tenant/actor từ context máy chủ.

Validator phải kiểm tra format/độ dài/range/enums và điều kiện nghiệp vụ. Với tên tài nguyên, hãy tránh ghép trực tiếp chuỗi script vào path, URL hoặc câu lệnh truy vấn. Kiểm tra theo **allowlist** sau khi chuẩn hóa thích hợp; chỉ dùng escaping/parameterized queries như một lớp phòng vệ, không thay cho phân quyền.

### 6.2. Không trả về đối tượng có quyền

Ngay cả khi API chỉ có một phương thức đọc, kiểu trả về có thể mở rộng khả năng thực tế của script:

| Kiểu trả về | Vấn đề | Lựa chọn tốt hơn |
|---|---|---|
| `DataSource` / `Connection` | Toàn quyền truy vấn hoặc transaction không mong muốn | Số liệu hoặc DTO đã tính toán |
| Entity ORM có lazy reference | Có thể lộ graph, trigger truy vấn ngầm | Record/projection bất biến |
| `InputStream` / `Path` / `File` | Vòng đời I/O và thông tin filesystem | Byte/string giới hạn kích thước hoặc ID đã kiểm duyệt |
| `HttpClient` / client SDK | Cho gọi endpoint tùy ý | Hàm nghiệp vụ sử dụng endpoint cố định |
| `Class` / `ClassLoader` | Mở rộng cơ chế reflection/class lookup | Không trả host runtime internals |
| `Throwable` đầy đủ | Có thể chứa stack trace, path, thông tin nhạy cảm | Lỗi đã chuẩn hóa: mã, mô tả an toàn, correlation ID |

Ngay cả DTO “vô hại” vẫn là Java object nếu engine có host interop. Hạn chế của engine phải được cấu hình/kiểm thử độc lập; nếu isolation không đáng tin, **trao đổi qua JSON/IPC** với các kiểu dữ liệu đơn giản.

### 6.3. Không tiết lộ tenant qua phản hồi

Khi tìm một ID không thuộc phạm vi, việc trả lỗi khác nhau “ID tồn tại nhưng không có quyền” và “ID không tồn tại” có thể bị dùng để dò dữ liệu. Nhiều API nên trả cùng `NOT_FOUND` cho hai tình huống, trong khi audit nội bộ vẫn ghi lý do thật. Quyết định chi tiết tùy hợp đồng sản phẩm, nhưng không để script tự truy vấn một namespace dữ liệu rộng rồi lọc ở phía client.

### 6.4. Xử lý side effect và retry

Một lệnh `notes.add` có thể hoàn thành trên server nhưng đường truyền IPC trả timeout. Nếu script tự retry vô hạn, ghi chú có thể bị tạo nhiều lần. Với thao tác side effect cần cân nhắc:

- Idempotency key do host gắn hoặc chấp nhận theo run/request đã xác thực.
- Giới hạn số lần thử, deadline và trạng thái chưa rõ.
- Transaction/unique constraint hoặc deduplication phù hợp.
- Không cho script tùy ý thay principal/tenant khi retry.
- Budget được tiêu hao theo định nghĩa nhất quán: request, tác vụ thành công hay side effect đã commit.

## 7. Quota, thời gian, concurrency và vòng đời

Một API hẹp vẫn có thể bị lạm dụng bằng cách gọi liên tục hoặc yêu cầu quá nhiều dữ liệu. Cần giới hạn **cả bên trong capability lẫn môi trường thực thi**.

| Rủi ro | Chỗ kiểm soát |
|---|---|
| `list(1_000_000)` | Giới hạn `limit` trong API và truy vấn DB; pagination có maximum page |
| Gọi `add` hàng nghìn lần | Quota tại gateway/store và rate limiter theo actor/tenant |
| Vòng lặp vô hạn trong script | Deadline ở sandbox process; giới hạn CPU và khả năng kết thúc tiến trình |
| Tạo object rất lớn | Giới hạn bộ nhớ và output bytes ở process/IPC |
| Truy xuất mạng tùy ý | Network policy/egress allowlist ở sandbox, không inject HTTP client |
| Giữ capability sau khi phiên làm việc kết thúc | Scope theo run, kiểm tra expiry/revocation tại mỗi lần gọi |
| Parallel script race | Quota, transaction và counter an toàn concurrent ở storage/gateway |
| Log chứa bí mật | Redaction, giới hạn field và chính sách retention |

**Không coi `Future.cancel(true)` hoặc `Thread.interrupt()` là cách “giết” mọi script độc hại.** Interrupt thường mang tính hợp tác; mã CPU-bound có thể bỏ qua, và Java thread trong cùng JVM không phải ranh giới giới hạn tài nguyên cứng. Khi cần chặn mã không tin cậy, sử dụng **process isolation và timeout do host/OS kiểm soát**, với chính sách dọn dẹp sau khi kết thúc.

**Không chia sẻ nhầm facade/state giữa lượt chạy.** Một `NotesRead` mang tenant A không nên bị lưu thành global object rồi dùng cho script của tenant B. Khởi tạo capability theo run, đảm bảo instance/cache/thread local không rò dữ liệu và quyền khi pooling engine hoặc worker.

## 8. Phân quyền và kiểm toán theo từng thao tác

Quy trình khuyến nghị cho một lời gọi capability:

```text
script asks notes.add("Beta")
             |
             v
[1] Run còn hợp lệ? actor/tenant xác thực?
             |
             v
[2] Operation notes.add có được cấp?
             |
             v
[3] Validate text + size + schema
             |
             v
[4] Enforce scope, quota, deadline
             |
             v
[5] Thực thi qua service/repository với transaction
             |
             v
[6] Audit + trả DTO / mã lỗi an toàn
```

Một hệ thống có thể theo dõi các trường sau ở server:

```json
{
  "runId": "run-42",
  "scriptId": "invoice-rule-v3",
  "operation": "notes.add",
  "tenant": "acme",
  "decision": "DENIED",
  "reason": "WRITE_BUDGET_EXCEEDED",
  "durationMs": 2
}
```

Đây chỉ là log mẫu; **không cần lưu nội dung ghi chú, SQL, tokens hoặc stack trace** để xác định một quyết định phân quyền. Trường `runId` và `scriptId` nên lấy từ điều phối của host, không từ tên tự khai trong script nếu log dùng cho audit.

Lỗi trả lại cho script nên có hợp đồng rõ ràng:

| Mã lỗi | Ý nghĩa | Phản ứng của script |
|---|---|---|
| `OPERATION_NOT_GRANTED` | Script/run không được phép gọi capability | Dừng hoặc yêu cầu cấu hình quyền, không retry |
| `VALIDATION_FAILED` | Sai kiểu, độ dài hoặc format đầu vào | Sửa tham số |
| `NOT_FOUND` | Tài nguyên không tồn tại trong phạm vi truy cập | Không tự suy đoán ID ở tenant khác |
| `QUOTA_EXCEEDED` | Vượt giới hạn một lượt hoặc tổng theo tenant | Dừng, chờ lượt mới nếu chính sách cho phép |
| `RUN_EXPIRED` | Execution context hết hạn hoặc bị thu hồi | Dừng dùng capability |
| `OPERATION_CONFLICT` | Idempotency/transaction conflict | Theo chính sách nghiệp vụ |
| `SCRIPT_ENGINE_UNAVAILABLE` | Engine không tồn tại hoặc không được phép | Lỗi triển khai; không thay engine tùy ý |
| `SCRIPT_EXECUTION_FAILED` | Script chạy lỗi | Ghi correlation ID, không lộ thông tin host |

Nếu thiếu quyền, phải **fail closed** và không tự động tạo writer với quyền cao hơn, không chuyển sang admin credential để “giúp script chạy xong”.

## 9. Kiểm thử API và ranh giới bảo mật

Có hai nhóm test **khác nhau**: test facade Java có đúng luật nghiệp vụ và test engine/sandbox có thể vượt facade hay không.

| Tình huống kiểm thử | Kết quả mong đợi |
|---|---|
| Reader của tenant A gọi `list(5)` | Chỉ thấy ghi chú A |
| Reader A tìm ID của tenant B | Không trả nội dung B; thường `NOT_FOUND` |
| Script chỉ đọc cố gọi operation ghi | Operation không tồn tại trong capability được cấp hoặc gateway từ chối |
| Gửi `list(0)`, `list(-1)` hoặc `list(1000)` | Từ chối do giới hạn tham số |
| `add(null)`, chuỗi rỗng, nội dung quá dài | Từ chối validation |
| Gọi `add` quá budget | Từ chối, không có side effect bổ sung |
| Cố truyền tenant khác vào yêu cầu | Tenant do host xác định, không thể đổi bằng input script |
| Script bị giữ lại sau khi run hết hạn | Capability không còn thực thi được |
| Engine có reflection/Java class access | Test để chắc chính sách host access thực thi thật; nếu không, không nhận script không tin cậy |
| Khôi phục engine từ pool sang tenant khác | Không còn bindings, globals và capability của tenant cũ |
| Script chạy vòng lặp vô hạn | Sandbox bị kết thúc đúng deadline, không làm treo host |
| Hai yêu cầu ghi đồng thời | Quota/ID/transaction không race hoặc nhân đôi side effect |
| Script đọc file/URL nội bộ ngoài quyền | Bị chặn bởi sandbox OS/network và gateway |
| Lỗi service chứa đường dẫn/secret trong exception | Script nhận mã lỗi an toàn, server log được redacted |
| Script giả mạo `runId`/`tenantId` trong JSON | Host bỏ qua hoặc từ chối, không nâng quyền |
| ScriptEngine bị thiếu trong JDK | Lỗi xác định, không cố chạy code bằng engine khác ngoài allowlist |

Test unit có thể dùng các implementation fake như `Store` ở ví dụ Java; test integration phải chạy trên **đúng engine**, đúng dependency, đúng cấu hình host access và môi trường deployment. Đừng coi test đi qua facade thành công là bằng chứng không thể bypass qua reflection.

## 10. Các lỗi thiết kế thường gặp

1. **Đưa `ApplicationContext` hoặc service container vào script.** Điều đó thường trao nhiều quyền hơn nhu cầu nghiệp vụ.
2. **Chỉ dùng một interface lớn có cờ `isAdmin`.** Tách capability chỉ đọc/ghi và giới hạn quyền theo run sẽ dễ review và thử nghiệm hơn.
3. **Cho script truyền `tenantId`, `userId` hoặc connection string.** Các giá trị quyết định quyền phải xuất phát từ context host đáng tin.
4. **Trả entity ORM, `Path`, `File`, `Connection` hoặc `ClassLoader`.** Object trả về có thể mang chức năng và metadata rộng hơn hợp đồng.
5. **Tin rằng `Bindings.put("api", facade)` là sandbox.** Script engine có thể còn Java interop, global bindings và đường truy cập khác.
6. **Tưởng Java 17 luôn có JavaScript engine.** JDK 17 không còn Nashorn mặc định; cần engine tương thích được quản lý riêng.
7. **Chặn class loading bằng class loader đơn giản rồi tin đã cô lập mã độc.** ClassLoader/JPMS không tự giới hạn mạng, file và CPU của mã cùng JVM.
8. **Giới hạn số phương thức nhưng không giới hạn số lần gọi.** API `list(1)` có thể bị gọi vô tận; phải có budget, deadline và rate limit.
9. **Chỉ kiểm quyền ở lúc cấp facade.** Quyền có thể hết hạn, thu hồi hoặc bị race; enforce tại từng operation/transaction quan trọng.
10. **Chỉ kiểm tra đầu vào trên UI.** Script có thể gọi host API trực tiếp; validation phải nằm ở phía Java/gateway.
11. **Sửa lỗi script bằng cách tự retry thao tác side effect.** Timeout không chứng minh server chưa commit; cần idempotency.
12. **Dùng `Thread.interrupt()` làm ranh giới bảo mật.** Không đủ cho code không hợp tác; cần process isolation và quota OS.
13. **Dùng cùng script engine/context cho nhiều tenant mà không kiểm tra rò state.** Bindings hoặc global objects từ lượt trước có thể bị giữ lại.
14. **Đưa stack trace hoặc secret vào thông điệp trả về.** Trả mã lỗi và correlation ID; chi tiết nhạy cảm chỉ ở log đã kiểm soát.

## 11. Checklist trước khi công bố API cho script

- **Trust model:** script là nội bộ được review, đối tác tin một phần hay mã người dùng không tin cậy?
- **Danh sách operation:** chỉ công bố các động từ nghiệp vụ cần thiết; không cung cấp reflection, SQL, file/HTTP tự do.
- **Quyền nguồn:** host xác định actor, tenant và grant; script không được tùy ý khai báo danh tính.
- **Đầu vào:** schema, kiểu, giới hạn độ dài, bộ lọc và allowlist được thực thi phía host.
- **Đầu ra:** DTO nhỏ, immutable, không chứa privileged host object hoặc dữ liệu không thuộc scope.
- **Kiểm quyền theo lượt gọi:** enforce grant, tenant, thời hạn, quota và transaction mỗi operation.
- **Trạng thái thực thi:** capability không tái sử dụng sai tenant/run; chú ý engine pooling và globals.
- **Đặc tính side effect:** audit, idempotency, retry, conflict và rollback có chính sách rõ ràng.
- **Engine:** version, JS/DSL semantics và host interop được đánh giá/khóa cấu hình.
- **Cô lập:** nếu không tin script, dùng sandbox process/OS, hạn chế mạng, file, secrets, CPU và RAM.
- **Khả năng quan sát:** log kết quả allow/deny, error code, latency, run ID; không ghi payload nhạy cảm.
- **Kiểm thử vượt quyền:** chạy negative tests với script cố truy cập object/operation không được cấp, không chỉ happy path.

### Tài liệu API tham khảo (Java SE 17)

- [ScriptEngine — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [ScriptEngineManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [Bindings — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html)
- [ScriptException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html)

**Kết luận:** thiết kế API Java cho script theo **least privilege** nghĩa là mỗi script chỉ nhận những capability cần thiết cho đúng người dùng/tenant, trong đúng khoảng thời gian và hạn mức; method Java tự kiểm tra đầu vào, phạm vi quyền và tác động. **Một facade tối giản giúp kiểm soát nghiệp vụ, nhưng không phải ranh giới bảo mật độc lập**: với script không tin cậy, phải kết hợp cấu hình engine an toàn với cô lập tiến trình/hệ điều hành và gateway xác thực, kiểm soát từng thao tác.