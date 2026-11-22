# Ranh giới tin cậy: Giới hạn đối tượng, đường dẫn và dịch vụ ứng dụng chủ trao cho phần mở rộng

## 1. Vấn đề cốt lõi: host không nên trao toàn bộ quyền của mình

Trong hệ thống Java có **extension/plugin**, host thường cung cấp cho phần mở rộng các khả năng như đọc template, xem một phần cấu hình, gọi dịch vụ nghiệp vụ, phát sự kiện hoặc lưu kết quả. Phần mở rộng có thể được nạp thông qua `ServiceLoader`, custom `ClassLoader`, `ModuleLayer` hoặc factory.

Sai lầm nguy hiểm là đưa thẳng cho plugin những object có quyền rộng: `ApplicationContext`, `DataSource`, `Path` tới thư mục gốc, `HttpClient`, `ExecutorService`, service locator, raw credential hoặc registry toàn ứng dụng. Khi đó extension có thể tiếp tục lần theo các public method, callback và object mà host vô tình trả về để tiếp cận tài nguyên **không liên quan tới nhiệm vụ**.

Mục tiêu của bài là thiết kế **trust boundary** dựa trên nguyên tắc **least authority / least privilege**:

- Chỉ trao **đúng thao tác** cần cho công việc đã phê duyệt.
- Chỉ truy cập **đúng dữ liệu, resource, tenant và đường dẫn**.
- Mỗi lần sử dụng được kiểm tra **phạm vi, hạn mức, vòng đời và quyền hiện tại**.
- Không trao các object có thể truy xuất tiếp quyền quản trị hay bí mật của host.
- Có quy trình **thu hồi, audit, cleanup** khi plugin bị tắt hoặc thay phiên bản.
- Không nhầm cấu trúc API hẹp với **sandbox cho mã Java độc hại**.

Điểm cuối đặc biệt quan trọng: nếu extension Java không tin cậy chạy **trong cùng JVM với host**, nó vẫn có thể thử dùng trực tiếp API hệ thống như `java.nio.file.Files`, `Socket`, reflection hoặc native library theo quyền của tiến trình. Façade hẹp chỉ giới hạn **quyền host chủ động trao qua tham số**, không loại bỏ ambient authority. Với mã đối kháng cần tiến trình riêng, quyền OS, policy network, quota và IPC rõ ràng.

### 1.1. Sơ đồ ủy quyền đúng phạm vi

```text
              HOST (trusted application)
    +---------------------------------------------+
    | authenticated identity, plugin generation   |
    | tenant, permissions, secrets, config        |
    | internal DataSource, file root, HTTP client |
    | pricing and other privileged services      |
    +---------------------------------------------+
            |  issue only approved capabilities
            v
       HostAccess facade
       +----------------------------------+
       | readNote("welcome.txt")          |
       | quote(units: 1..10)              |
       | authorize, validate, audit       |
       | revoke/cleanup (host side only)  |
       +----------------------------------+
            |
            v
       Extension / plugin
       +----------------------------------+
       | run(HostAccess)                  |
       | does not receive raw root Path,  |
       | DataSource or PricingService     |
       +----------------------------------+
```

Đây là mô hình **trao quyền API tối thiểu cho extension hợp tác**. Không coi việc extension không nhìn thấy một field private trong interface là bằng chứng nó không thể làm điều tương đương qua JDK hoặc runtime khi chạy cùng process.

### 1.2. Sáu câu hỏi cần trả lời trước khi cấp object

| Câu hỏi | Điều cần xác định |
| --- | --- |
| **Ai nhận quyền?** | Plugin ID, phiên bản, generation, tenant, principal do host xác thực |
| **Được làm gì?** | Read, write, lookup, publish, schedule, transfer hay quản trị |
| **Trên dữ liệu nào?** | Logical IDs, allowlist, cây thư mục, record ownership, service/topic |
| **Với giới hạn gì?** | Byte limit, kết nối, rate, concurrency, CPU/time và số request |
| **Trong bao lâu?** | Một invocation, session, generation, lease hoặc cho tới revoke |
| **Ai kiểm tra và audit?** | Façade/service ở phía host tại thời điểm thực thi, không chỉ khi khởi tạo plugin |

Những câu trả lời này là một phần của **hợp đồng extension** và nên được thể hiện thành API, metadata cấu hình, policy thực thi cùng bộ kiểm thử. Một object reference bị trao ra có thể được giữ lâu trong field/static cache; vì vậy việc “cấp một lần” không tự ràng buộc vòng đời sử dụng.

## 2. Giới hạn object graph, không chỉ tên kiểu

Một method Java trả về object có thể mở đường tới những object khác. Nếu plugin nhận một interface có vẻ hẹp nhưng interface lại chứa `getRawService()`, `getDelegate()`, `getApplicationContext()`, `getConnection()` hoặc `getRootPath()`, việc che giấu bằng abstraction ban đầu không còn nhiều ý nghĩa.

### 2.1. Những reference không nên trao vô điều kiện

| Object host đưa trực tiếp | Quyền/rủi ro phát sinh | Tốt hơn nên trao |
| --- | --- | --- |
| `ApplicationContext` / service locator | Tìm mọi bean và subsystem | Façade một số method được duyệt |
| `DataSource` hoặc raw JDBC `Connection` | Truy vấn/sửa dữ liệu ngoài tenant; tự mở transaction | Phương thức nghiệp vụ scoped tenant và operation |
| Root `Path`, `File`, `FileSystem` | Tìm/mở tệp ngoài danh sách mục tiêu | Logical resource name và API đọc/ghi có allowlist |
| `HttpClient`, HTTP gateway gọi URL bất kỳ | SSRF, rò token, egress không kiểm soát | `fetchApprovedCatalog(catalogId)` hoặc service gateway |
| `ExecutorService` / scheduler global | Submit công việc không hạn mức, sống qua unload | `scheduleApprovedJob(spec)` có quota, cancellation |
| Event bus tổng quát | Nghe hoặc phát mọi topic | Scoped publisher/subscriber theo topic, tenant |
| Mutable config, `Map` chứa secret | Sửa dữ liệu chung, đọc credential | Immutable snapshot; opaque secret capability rất hẹp |
| `ClassLoader`, `ModuleLayer.Controller` | Can thiệp loading/graph khi không cần | API host ở tầng nghiệp vụ |
| Object domain mutable | Thay đổi state host qua getter/alias | Immutable DTO và defensive copy |
| Logger có writer/storage quyền cao | Ghi logs nhạy cảm, tạo tải lớn | Host logging façade với schema/quota |

**Không nên thiết kế API kiểu `invoke(serviceName, methodName, args)`** để gọi tùy ý. Đây là cách gói lại service locator dưới tên khác, đẩy authorization thành bài toán khó không cần thiết.

### 2.2. API façade theo capability

Chẳng hạn plugin chỉ được đọc một tài liệu và tính giá cho số lượng hợp lệ:

```java
public interface HostAccess {
    String readNote(String relativeName) throws java.io.IOException;
    int quote(int units);
}
```

Đây là **đoạn interface minh họa**, không phải một tệp Java chạy độc lập. `HostAccess` nói rõ hai thao tác; nó **không** đưa ra `getRootPath()`, `getPricingService()` hoặc `getAnyBean()`.

So sánh:

```java
// Quyền quá rộng nếu plugin không thực sự cần:
void initialize(java.nio.file.Path appRoot,
                javax.sql.DataSource dataSource);

// Hợp đồng có phạm vi hẹp hơn:
void initialize(HostAccess access);
```

Đây là hai method signatures **minh họa**; chúng cần được đặt trong class/interface phù hợp nếu muốn biên dịch. API hẹp chỉ hiệu quả khi implementation **thực sự kiểm tra input và context**, không đơn giản forward tới raw service.

### 2.3. Cẩn thận với đối tượng trả về

- `List.copyOf(list)` và `Map.copyOf(map)` giúp snapshot container bất biến, nhưng là **shallow copy**: phần tử hoặc value mutable vẫn có thể bị đổi.
- `Collections.unmodifiableList(original)` cấm sửa qua wrapper nhưng có thể tiếp tục phản ánh thay đổi từ list gốc.
- Java `record` không tự deep-copy `byte[]`, `Map<String, MutableItem>` hoặc object nội bộ.
- Trả một `InputStream` hoặc `Iterator` trên DB cursor/transaction có thể kéo dài quyền truy cập và giữ resource sống quá lifecycle; phải quy định byte limit, time limit, close ownership.
- Đừng trả `Connection`, `Statement`, `ClassLoader`, `Class<?>` hoặc dynamic proxy lộ delegate nếu nhiệm vụ chỉ cần một giá trị.
- Với secret, không đưa credentials ra ngoài rồi kỳ vọng plugin “không đọc”; API nên thực hiện tác vụ cần secret ở host, trả kết quả tối thiểu.

Nếu extension cần đọc một vài field, tốt hơn trả DTO immutable đã được lọc theo policy. Khi DTO chứa object lồng nhau, bảo đảm defensive copies hoặc immutable data structures tới hết boundary.

### 2.4. Interface cùng class identity giữa host và plugin

Nếu host và implementation plugin được nạp bằng class loader khác nhau, shared contract `HostAccess`, request/response DTO, callback và exception phải có **một định nghĩa runtime thống nhất**. Thường đặt API ở loader cha, plugin phụ thuộc vào API đó và không gói lại một bản sao. Hai class có cùng binary name nhưng được định nghĩa bởi các class loader khác nhau không phải cùng runtime type.

Cần tách quyền truy cập qua façade khỏi việc điều khiển class loading: plugin không cần được cấp `URLClassLoader` chỉ để host có thể gọi `run(HostAccess)`.

## 3. Xác thực danh tính và phạm vi quyền ở phía host

Một capability có thể gắn với:

- Plugin ID/version/generation mà host chọn.
- Tenant/user/session đã được xác thực từ môi trường host.
- Resource scope (allowed note IDs, record IDs, event topics).
- Tập method/operation được cho phép.
- Quota, concurrency, deadline, thời gian hết hạn.
- Cơ chế revoke, audit context và trace ID.

Không nên tin danh tính do plugin tự khai báo. Ví dụ:

```java
// Rủi ro nếu plugin có thể tự cung cấp "admin":
internalService.listRecords(pluginSuppliedTenantId);

// Hướng hợp đồng tốt hơn:
HostAccess scoped = hostPolicy.issue(authenticatedTenant, pluginGeneration);
scoped.readNote("welcome.txt");
```

Đây là **pseudocode kiến trúc**: `internalService`, `hostPolicy` và `authenticatedTenant` không phải biến JDK định nghĩa. Host phải ràng buộc tenant vào capability của chính mình rồi áp dụng authorization khi truy cập dữ liệu, không tin `tenantId` nằm trong request payload của plugin.

### 3.1. Hạn chế các thao tác quyền khác nhau

Quyền đọc một file không đồng nghĩa quyền **liệt kê thư mục, xem metadata tất cả file, ghi, xóa, đổi tên hoặc đăng ký watcher**. Với dữ liệu, quyền `readById` không đồng nghĩa `listAll` hay `searchAllTenants`. Với event bus, quyền publish topic A không đồng nghĩa subscribe topic A hay publish topic B.

Có thể tách interface để tránh tự mở quyền:

```java
interface ApprovedReader {
    String read(String logicalName) throws java.io.IOException;
}

interface ApprovedPublisher {
    void publish(String topic, byte[] payload);
}
```

Đây chỉ là **đoạn API minh họa**; implementation cần kiểm tra policy/tenant/topic/bytes. Không phải cứ đặt tiền tố “Approved” là tự được bảo vệ.

### 3.2. Chống confused deputy

**Confused deputy** là tình huống plugin có quyền thấp dùng host có quyền cao để làm việc ngoài phạm vi. Ví dụ `readAnyUri("file:///sensitive/config")` được host thực thi với quyền đọc file của chính host rồi trả dữ liệu cho plugin.

Giảm thiểu bằng logical resource ID thay vì URI tùy ý, kiểm tra operation/resource/tenant ngay tại boundary, không truyền raw token và giới hạn quyền process/gateway thật sự. Kiểm soát tại bước khám phá plugin **không đủ** nếu mỗi request sau đó có thể chứa đường dẫn hoặc ID mới.

## 4. Giới hạn đường dẫn được phép truy cập

Đường dẫn là đầu vào nhạy cảm vì có absolute path, `..` traversal, symbolic link, mount point, case folding và race khi filesystem thay đổi.

### 4.1. Ưu tiên logical name hơn raw Path

Nếu plugin chỉ cần tài liệu “welcome”, host nên nhận `"welcome"` hoặc `"welcome.txt"` và tự ánh xạ tới thư mục allowlisted. Không nên đưa absolute root path tới plugin hoặc cho phép gửi mọi file URI.

Quy trình tối thiểu cho một đường dẫn tương đối:

1. Host tự chọn `root` và lấy đường dẫn thực/canonical bằng `root.toRealPath()`.
2. Parse input bằng `Path.of(name)`, từ chối null/blank, path sai cú pháp, absolute path.
3. Tạo candidate bằng `rootReal.resolve(requested).normalize()`.
4. So sánh đường dẫn theo **cấu trúc Path**: `candidate.startsWith(rootReal)`; không kiểm tra bằng `candidate.toString().startsWith(rootText)`.
5. Áp dụng allowlist **tên logic** cụ thể hoặc resource ID đã cấp, không mặc định mọi file trong root đều hợp lệ.
6. Trước khi mở, lấy `candidate.toRealPath()` và xác nhận đường dẫn thực vẫn thuộc root được phép để giảm rủi ro symlink escape.
7. Xem thêm file type, maximum size, quyền OS, byte limit, timeout và cách cleanup stream/handle.
8. Audit kết quả theo resource ID và operation, không lộ full system path trong lỗi trả cho plugin.

Ví dụ kiểm tra:

```java
Path rootReal = root.toRealPath();
Path requested = Path.of(relativeName);
if (requested.isAbsolute()) throw new SecurityException("absolute path");
Path candidate = rootReal.resolve(requested).normalize();
if (!candidate.startsWith(rootReal)) throw new SecurityException("outside root");
Path real = candidate.toRealPath();
if (!real.startsWith(rootReal)) throw new SecurityException("symlink outside root");
```

Đây là **mã minh họa cần thêm import/biến và IOException handling**; phần 8 có chương trình hoàn chỉnh.

`Path.startsWith` so theo các thành phần path (phù hợp file-system provider). Trong khi đó kiểm tra chuỗi `"/data/app-backup".startsWith("/data/app")` trả true dù `/data/app-backup` là thư mục khác.

### 4.2. Normalize và real path vẫn chưa đủ chống TOCTOU

`normalize` xử lý `.`/`..` ở mức cú pháp, **không** tự nhận diện symlink/hard link/mount. `toRealPath()` truy theo đường dẫn vật lý ở thời điểm kiểm tra, nhưng nếu có process khác sửa symlink/tệp **sau bước check** và **trước bước open/read**, ứng dụng vẫn có thể chịu lỗi **time-of-check to time-of-use (TOCTOU)**.

Vì vậy **đừng tuyên bố** `normalize + toRealPath + startsWith` tạo sandbox an toàn tuyệt đối. Các biện pháp tăng cường:

- Đảm bảo quyền OS không cho untrusted code thay đổi các directory components mà host tin cậy.
- Nếu threat model có writer đối kháng, ưu tiên truy cập tương đối với **directory handle** có quyền hạn rõ ràng; `SecureDirectoryStream` hữu ích **khi filesystem provider hỗ trợ**.
- Quy định symlink được cho phép hay bị cấm. `NOFOLLOW_LINKS` ở final path một mình không bảo đảm mọi parent component và mọi race đã được xử lý.
- Với ghi file, xét riêng create-only, overwrite, atomic move, race, quota, ownership và cleanup; không copy nguyên thuật toán đọc sang ghi.
- Xét case-insensitive filesystem, drive-letter/UNC Windows, Unicode normalization, hardlinks, mount point và network file systems theo môi trường deploy.
- Giới hạn kích thước, thời gian và số handle được mở; file hợp lệ vẫn có thể rất lớn hoặc gây I/O stall.
- Nếu yêu cầu an toàn trước mã độc hại, dữ liệu nhạy cảm phải nằm **ngoài quyền đọc của OS identity mà worker plugin sử dụng**.

### 4.3. Allowlist logic mới là giới hạn nghiệp vụ

Nếu plugin chỉ cần `welcome.txt`, từ chối `private.txt` ngay khi kiểm tra allowlist sẽ tốt hơn việc thử đọc rồi chờ `NoSuchFileException`. Một allowlist các file ID là chính sách nghiệp vụ, còn kiểm tra canonical path và filesystem là lớp bảo vệ đường dẫn.

Đừng trả thông báo lỗi cho plugin kiểu “file có tồn tại nhưng bạn không được đọc”. Điều đó có thể biến API thành oracle để liệt kê file. Lỗi phía plugin nên tối thiểu, trong khi log nội bộ có đủ dữ liệu debug và kiểm toán theo quyền.

### 4.4. Không trả Path/URI tùy ý chỉ vì nó là giá trị

`Path` bản thân chỉ mô tả địa chỉ, nhưng extension đang chạy với quyền của host có thể dùng địa chỉ đó để truy cập file trực tiếp. Trả root path hoặc đường dẫn secret là vô tình mở thêm thông tin và công cụ bypass façade. Tốt hơn dùng logical ID và trả content/DTO có giới hạn, hoặc opaque handle được host quản lý cả lifetime.

## 5. Giới hạn dịch vụ ứng dụng chủ

Dịch vụ nội bộ có thể có nhiều method hơn chức năng plugin thực sự cần. Ví dụ một pricing service có method xem giá, thay bảng giá, sửa policy giảm giá và quản lý cache; extension chỉ nên gọi một operation tra cứu/tính giá đã được kiểm soát.

```text
Plugin                 Host façade                 Internal service
   | quote(3)               |                             |
   |----------------------->| check active/tenant/quota    |
   |                        | validate units in 1..10     |
   |                        | calculatePrice(3)           |
   |                        |---------------------------->|
   |                        |<----------------------------|
   |<-----------------------| return minimal result        |
```

### 5.1. Kiểm tra tại từng operation

Một façade nghiệp vụ nên xác nhận:

- Người yêu cầu/plugin generation vẫn được phép sử dụng dịch vụ.
- Operation hiện tại thuộc tập capabilities cho phép.
- Resource/tenant thuộc phạm vi được cấp; user ID không được tin từ payload plugin.
- Tham số có schema hợp lệ, length/range hợp lệ, chống injection.
- Output giới hạn trường, số record, bytes và sensitivity.
- Request time/quota/rate/concurrency được kiểm soát, có timeout và rejection policy.
- Side effects tuân transaction/idempotency/audit.
- Handle cũ đã revoke thì không tiếp tục forward lệnh.
- Lỗi trả về không chứa secret, connection string, stacktrace nội bộ hoặc full path.

Ví dụ `quote(units)` trong phần 8 chỉ cho `1..10`. Đó là **input range policy**, chưa phải total budget/rate limit; bài toán quota thực cần counter/identity theo time window và source of truth phù hợp (đặc biệt nếu chạy nhiều process).

### 5.2. Đặc biệt cẩn trọng với DB và secrets

Không cấp `DataSource`/`Connection` chỉ để plugin gọi một truy vấn có sẵn. Thay bằng `findAllowedDocument(id)`, `calculateApprovedQuote(request)` hoặc domain service có kiểm tra tenant row ownership trong lớp có đặc quyền.

Không đặt API `getSecret(name)` nếu mục tiêu chỉ cần ký thông điệp: host có thể cung cấp `signApprovedPayload(payload)` hoặc một token capability phạm vi rất hẹp mà không trả raw secret. Hạn chế secret theo tenant, mục đích, TTL, rotation và audit.

Nếu plugin đang chạy cùng process có ambient access tới environment variables hoặc config files, chỉ che getter của façade không đủ chống kẻ tấn công. Cần đảm bảo worker/plugin process không sở hữu secrets ngoài phạm vi.

### 5.3. HTTP gateway và SSRF

Nếu extension cần gọi dữ liệu online, API `fetchAnyUrl(url)` là rủi ro lớn. Một HTTP gateway của host nên dùng service ID/endpoint allowlist và kiểm tra:

- Scheme, hostname, port, path và method được phép.
- DNS resolution, private/loopback/link-local/metadata addresses theo threat model.
- Redirect destination qua mỗi hop, không cho redirect bỏ qua chính sách.
- Timeout, max response bytes, content type, retry limit.
- Secret/token injection đúng đích, không đính kèm host token vào URL không được duyệt.
- Network egress ở mức OS/gateway; không chỉ kiểm tra chuỗi URL.

Một request có hostname trong allowlist nhưng DNS hoặc redirect về endpoint nội bộ có thể gây SSRF nếu không kiểm tra thực sự. Vì vậy policy dùng URL string không phải điều kiện đủ.

### 5.4. Event bus, scheduler và callbacks

Tránh trao raw `ExecutorService` hoặc toàn bộ event bus; extension có thể giữ thread, tạo task không giới hạn, subscribe topic nhạy cảm hoặc còn callback sau unload. Thay bằng façade `scheduleApprovedJob(spec)`, `publishApprovedEvent(topic, payload)` với namespace, quota, cancellation và ownership theo generation.

Mọi listener, thread context class loader, stream và task phải được host theo dõi; khi stop plugin cần unregister/cancel/close theo deadline. Không gọi arbitrary plugin code trong khi giữ khóa global registry nếu điều đó gây deadlock hoặc gây nghẽn yêu cầu khác.

## 6. Vòng đời và cơ chế thu hồi capability

Reference đã trao có thể được extension giữ trong field/static cache. Vì vậy policy cần có **revoke** thực thi ở mỗi operation, không chỉ xóa capability khỏi registry.

Một state machine gợi ý:

```text
CREATED -> ACTIVE -> REVOKING -> REVOKED
             |            |
             |            +-- new admissions rejected
             |            +-- in-flight complete/cancel according to policy
             |
             +-- operations validate permissions and lifetime
```

Đây là **mô hình nghiệp vụ**, không phải class có sẵn của JDK. Khi revoke, phải quyết định liệu in-flight operations được hoàn tất, bị hủy hợp tác hay chờ timeout, đặc biệt nếu hoạt động gồm I/O hoặc transaction.

### 6.1. Vì sao chỉ dùng volatile flag không đủ?

Trình tự có race:

```text
Thread A: sees active == true
Thread B: active = false; closes service
Thread A: uses service after it was closed
```

`volatile` cải thiện visibility, không làm check-and-enter nguyên tử. Có thể dùng **lifecycle gate** với read/write lock hoặc active leases/reference count và condition. Mục tiêu là phối hợp **admission + actual use + revoke/close**.

Demo ở phần 8 dùng `ReentrantReadWriteLock`: mỗi operation lấy read lock trong suốt việc thực hiện; `revoke` lấy write lock và chuyển cờ active. Vì write lock chờ các read locks được nhả, sau khi revoke hoàn tất không còn operation façade cũ đang chạy trong gate. **Trade-off:** I/O treo có thể làm revoke treo; giải pháp production cần deadline, cancellation và tránh lock upgrade read → write từ callback.

### 6.2. Generation, tenant và cleanup

Khi plugin phiên bản mới được nạp, nên tạo capability mới cho **generation** mới, không tái dùng reference đã revoke của thế hệ cũ. Registry/callback hoặc thread pool phải dọn reference tới class loader và instance cũ để GC có cơ hội thu hồi.

Nếu một tài nguyên do host sở hữu (DB pool, scheduler, shared cache), plugin không được `close()` nó. Khi plugin có tài nguyên private, hợp đồng phải ghi ai đóng, khi nào đóng và xử lý exception ra sao. “Quyền truy cập được revoke” cũng không tự xóa mọi dữ liệu mà plugin đã đọc hoặc bản sao nó đã tạo trước đó.

## 7. ClassLoader, ModuleLayer và giới hạn bảo mật thực tế

`ClassLoader` tạo namespace và class identity, giúp version isolation; `ModuleLayer` giúp quản lý named modules, reads/exports/opens. Nhưng chúng không tự cấp sandbox để giới hạn mọi file, DB, network hoặc native operation.

Không nên dựa vào `SecurityManager` như kiến trúc cô lập plugin mới trên JDK hiện đại. Ranh giới mạnh với **mã không tin cậy** thường đòi hỏi:

```text
Host process (secrets, internal DB, privileged services)
       |
       | IPC with explicit request schema and auth
       | per-operation authorization + audit + quotas
       v
Plugin worker process (separate OS identity)
  - restricted filesystem mounts/ACL
  - controlled network egress
  - memory/CPU/time limits
  - no direct host secrets
  - kill/restart/revoke via host
```

Một host API façade vẫn rất hữu ích với trusted plugins: giảm coupling, tránh sai sót, giảm quyền vô tình, kiểm soát dữ liệu tenant và giúp thay implementation. Nhưng để chống lại code đối kháng, OS/process boundary phải thực sự giới hạn những thao tác không đi qua façade.

## 8. Ví dụ Java 17+ chạy được: HostAccess hẹp, đường dẫn có allowlist, quota và revoke

Demo sau xây một **host port** `HostAccess` chỉ có `readNote` và `quote`. Implementation `ScopedAccess` chứa root path thực, danh sách file cho phép và `PricingService` nội bộ, nhưng chỉ host biết những đối tượng này. `SampleExtension` gọi port mà không nhận nguyên `Path` hoặc service.

Demo tạo một thư mục tạm để chạy được độc lập. Nó kiểm tra một tác vụ được phép, path traversal, file không nằm trong allowlist, request quá hạn mức và lời gọi sau revoke.

**Giới hạn đã biết:** để đơn giản, code dùng `toRealPath()` trước `Files.readString()` và **không giải quyết hoàn toàn TOCTOU nếu attacker có quyền đổi symlink/tệp giữa hai bước**. Nó cũng không chặn code Java độc hại gọi filesystem trực tiếp ngoài interface. Không dùng chương trình này làm sandbox.

Lưu tệp với tên **`HostBoundaryDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class HostBoundaryDemo {
    public interface HostAccess {
        String readNote(String relativeName) throws IOException;
        int quote(int units);
    }

    public interface Extension {
        String run(HostAccess access) throws IOException;
    }

    private static final class PricingService {
        private int quote(int units) {
            return Math.multiplyExact(units, 5);
        }
    }

    private static final class ScopedAccess implements HostAccess {
        private final Path rootReal;
        private final Set<String> allowedFiles = Set.of("welcome.txt");
        private final PricingService pricing = new PricingService();
        private final ReentrantReadWriteLock gate = new ReentrantReadWriteLock();
        private boolean active = true;

        ScopedAccess(Path root) throws IOException {
            this.rootReal = root.toRealPath();
        }

        private void checkActive() {
            if (!active) throw new SecurityException("capability revoked");
        }

        @Override
        public String readNote(String name) throws IOException {
            Lock read = gate.readLock();
            read.lock();
            try {
                checkActive();
                if (name == null || name.isBlank()) {
                    throw new SecurityException("invalid path");
                }
                final Path requested;
                try {
                    requested = Path.of(name);
                } catch (InvalidPathException ex) {
                    throw new SecurityException("invalid path", ex);
                }
                if (requested.isAbsolute()) {
                    throw new SecurityException("absolute path denied");
                }
                Path candidate = rootReal.resolve(requested).normalize();
                if (!candidate.startsWith(rootReal)) {
                    throw new SecurityException("outside root");
                }
                String logical = rootReal.relativize(candidate)
                        .toString().replace('\\', '/');
                if (!allowedFiles.contains(logical)) {
                    throw new SecurityException("file not allowlisted");
                }
                Path real = candidate.toRealPath();
                if (!real.startsWith(rootReal) || !Files.isRegularFile(real)) {
                    throw new SecurityException("unsafe target");
                }
                return Files.readString(real, StandardCharsets.UTF_8);
            } finally {
                read.unlock();
            }
        }

        @Override
        public int quote(int units) {
            Lock read = gate.readLock();
            read.lock();
            try {
                checkActive();
                if (units < 1 || units > 10) {
                    throw new SecurityException("units outside policy");
                }
                return pricing.quote(units);
            } finally {
                read.unlock();
            }
        }

        void revoke() {
            Lock write = gate.writeLock();
            write.lock();
            try {
                active = false;
            } finally {
                write.unlock();
            }
        }
    }

    private static final class SampleExtension implements Extension {
        @Override
        public String run(HostAccess access) throws IOException {
            return access.readNote("welcome.txt") + " | " + access.quote(3);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("boundary-demo-");
        try {
            Files.writeString(dir.resolve("welcome.txt"),
                    "Hello, plugin", StandardCharsets.UTF_8);
            ScopedAccess access = new ScopedAccess(dir);
            Extension plugin = new SampleExtension();
            System.out.println("allowed: " + plugin.run(access));

            try {
                access.readNote("../outside.txt");
                System.out.println("path traversal: allowed");
            } catch (SecurityException expected) {
                System.out.println("path traversal: denied");
            }

            try {
                access.readNote("private.txt");
                System.out.println("unlisted file: allowed");
            } catch (SecurityException expected) {
                System.out.println("unlisted file: denied");
            }

            try {
                access.quote(100);
                System.out.println("excess request: allowed");
            } catch (SecurityException expected) {
                System.out.println("excess request: denied");
            }

            access.revoke();
            try {
                access.quote(2);
                System.out.println("revoked: allowed");
            } catch (SecurityException expected) {
                System.out.println("revoked: denied");
            }
        } finally {
            Files.deleteIfExists(dir.resolve("welcome.txt"));
            Files.deleteIfExists(dir);
        }
    }
}
```

### 8.1. Cách chạy và stdout

Trên JDK 17+:

```bash
javac --release 17 HostBoundaryDemo.java
java HostBoundaryDemo
```

**Kết quả đã kiểm chứng** khi biên dịch bằng `javac --release 17` và chạy `java`:

```text
allowed: Hello, plugin | 15
path traversal: denied
unlisted file: denied
excess request: denied
revoked: denied
```

Giải thích:

1. **`allowed`:** `readNote("welcome.txt")` được allowlist, `quote(3)` tính `3 × 5 = 15`.
2. **`path traversal`:** sau `normalize()`, `../outside.txt` vượt khỏi root và bị check `Path.startsWith(rootReal)` từ chối.
3. **`unlisted file`:** `private.txt` không có trong `Set.of("welcome.txt")` nên bị từ chối **ngay cả khi tệp đó tồn tại**.
4. **`excess request`:** `quote(100)` không đi tới `PricingService` vì vượt policy `1..10`.
5. **`revoked`:** sau `revoke()`, `active=false` và mọi invocation façade mới bị từ chối dưới lifecycle lock.

### 8.2. Các bất biến có thể kiểm chứng

- `HostAccess` chỉ công bố **hai method**; không có getter cho directory root, `PricingService` hay credential.
- `ScopedAccess` giữ nguyên root, allowlist, policy và state revoke ở phía host.
- `revoke()` không nằm trong `HostAccess`, nên plugin **không được cấp thao tác thu hồi capability của host thông qua interface**.
- Mọi lời gọi façade kiểm tra `active` khi đã lấy read lock; write lock cho revoke ngăn việc đóng state khi operation đang giữ lock.
- Tác vụ hợp lệ không bị chặn bởi việc thiếu thư viện ngoài; chương trình chỉ dùng JDK 17.
- Việc input không chứa traversal và nằm trong allowlist là một lớp bảo vệ, nhưng **không** ngăn arbitrary code dùng phương tiện khác ngoài façade.

### 8.3. Production cần bổ sung những gì?

Ví dụ dùng `Files.readString` (đọc toàn bộ file) mà chưa có byte limit; code thực cần đặt giới hạn file size/streaming, deadline, xử lý close/IOExceptions và root directory permissions. Nếu filesystem bị chỉnh bởi đối tượng đối kháng, cần cơ chế giảm race như directory handle có policy kết hợp OS-level restrictions. Nếu capability xử lý tác vụ dài, read/write gate nên được thay hoặc bổ sung bằng lease/cancellation và timeout phù hợp.

`quote` chỉ giới hạn **tham số từng lời gọi**; chưa phải rate quota tổng, chính sách tenant hay chi phí xử lý phân tán. Production phải dùng authenticated host context và tracking quota. Tên private class không phải ranh giới security đối với mã không tin cậy có ambient process privileges.

## 9. Chẩn đoán lỗi và các anti-pattern

| Tình huống | Nguyên nhân/rủi ro | Cách khắc phục |
| --- | --- | --- |
| Plugin nhận `ApplicationContext` | Có thể truy cập service ngoài phạm vi | Trao façade hẹp theo capability |
| Plugin nhận `Path` root | Có thể biết/truy cập file ngoài mục tiêu | Logical name + host-controlled root |
| Check bằng `String.startsWith` | Có prefix collision | `Path.startsWith` và canonical policy |
| Chỉ dùng `normalize()` | Không đủ chống symlink/mount/race | Check real path + directory handle/OS permissions |
| Trả raw `Connection` | Plugin chạy SQL có đặc quyền của host | API nghiệp vụ và tenant validation |
| Chỉ check lúc inject | Handle sống sau revoke | Authorization mỗi operation + lifecycle gate |
| Plugin quyết định `tenantId` | Giả mạo tenant/confused deputy | Host binds authenticated identity |
| `getRawService()` trong façade | Làm lộ delegate | Trả dữ liệu kết quả, không raw object |
| Trả mutable entity | Plugin sửa state host ngoài control | Deep immutable DTO/defensive copy |
| `fetchAnyUrl` | SSRF và rò token qua redirects | Gateway allowlist + network egress |
| Plugin giữ global executor | Chiếm thread/không dừng sau reload | Scoped scheduler, task quota, cleanup |
| Dựa vào `ClassLoader` như sandbox | Không chặn ambient filesystem/network | Process isolation, OS ACL/network policy |
| Log full path/secret | Lộ metadata/credential | Structured audit tối thiểu và masking |

### 9.1. Chẩn đoán lỗi phân quyền nên theo thứ tự

1. Plugin ID/generation/tenant nào đã nhận capability? Identity có được host xác thực không?
2. Operation hiện tại có nằm trong policy cho plugin này không?
3. Resource ID/path có nằm trong allowlist đúng tenant không?
4. Normalize, real path và symlink resolution xử lý đúng loại filesystem chưa?
5. Quota/TTL/revoke đã thay đổi giữa lúc cấp quyền và gọi chưa?
6. Lỗi từ policy, từ filesystem hay từ service nội bộ? Có cần phân biệt cho logs không?
7. Kết quả hoặc error message có lộ full path, secret hoặc dữ liệu tenant khác không?

**Không nên** mặc định trả “file tồn tại nhưng bị cấm đọc” cho plugin; điều đó có thể tạo thông tin phụ để dò tên file. Log nội bộ có thể ghi mã quyết định, correlation ID và resource logical ID mà không tiết lộ đường dẫn vật lý.

## 10. Ma trận kiểm thử trust boundary

### 10.1. Đường dẫn và tài nguyên

| Input | Điều cần kiểm chứng |
| --- | --- |
| `welcome.txt` trong allowlist | Cho phép khi capability active và file đúng |
| `private.txt` không allowlist | Từ chối dù file có tồn tại |
| `../outside.txt` | Không ra ngoài root |
| Absolute Unix/Windows path | Không dùng để vượt root |
| Prefix sibling của root | Không bị nhầm là child path |
| Symlink trỏ ra ngoài | Canonical check từ chối nếu không có race |
| Symlink thay đổi giữa check/open | Threat model cần directory-handle/OS policy |
| Invalid path/Unicode/case | Provider-specific policy ổn định và có lỗi rõ |
| File cực lớn | Bounded bytes, timeout, không OOM |
| Directory thay vì file | Không được đọc như file thường |
| Revoked capability | Operation mới bị từ chối |
| OS permission bị thay đổi | Không bypass bằng fallback có quyền rộng |

### 10.2. Dịch vụ và object graph

- Extension cố gọi method write/delete nhưng chỉ được read: không có đường truy cập được host cấp hoặc policy từ chối.
- Extension gửi tenant ID giả: không thay đổi bound tenant của host.
- Extension thử lấy raw service/delegate/DataSource/ExecutorService qua getters: API không trả chúng.
- Extension nhận DTO rồi sửa field lồng nhau: không làm đổi mutable state host.
- Extension spam request/payload: rate/size/concurrency quota và rejection policy có hiệu lực.
- Extension dùng service khác sau revoke: mỗi façade operation kiểm tra quyền tại use-time.
- Extension đăng ký listener/task rồi unload: host cleanup mọi registration/thread/resource.
- Extension version mới và cũ đồng tồn tại: quyền/audit theo generation tách biệt.
- Extension thử SSRF qua gateway: allowlist/DNS/redirect/egress chặn.
- Với mã đối kháng: worker không thể truy cập secrets/file/network đã bị OS policy cô lập **kể cả ngoài API host**.

### 10.3. Audit và observability

Nên ghi quyết định tối thiểu:

```text
pluginId=report-extension
generation=42
operation=readNote
resourceId=welcome
decision=DENY
reason=NOT_ALLOWLISTED
traceId=<correlation-id>
```

Đây là **format log minh họa**, không phải output của chương trình Java. Log phải tuân retention, quyền đọc và masking, tránh full absolute path, source nội dung, credentials hoặc request payload chứa dữ liệu nhạy cảm.

## 11. Checklist trước khi cấp quyền cho plugin

1. **Trust model:** extension nội bộ, được kiểm duyệt hay không tin cậy? Nếu đối kháng, OS/process isolation có thật?
2. **Object inventory:** mọi tham số/getter/callback và object reference có quyền rộng đã được xem xét?
3. **Least authority:** chỉ đúng methods cần thiết, không cấp `ApplicationContext`, raw `DataSource`, `Path root` nếu không bắt buộc?
4. **Identity:** host gắn plugin/generation/tenant từ nguồn đáng tin; plugin không tự khai báo quyền?
5. **Resource scope:** operation, logical ID, allowlist và tenant ownership được kiểm tra tại use-time?
6. **Path policy:** xử lý absolute/traversal/prefix/symlink/mount/TOCTOU; OS ACL và filesystem semantics phù hợp?
7. **Service policy:** schema, output filtering, quota, concurrency, timeout, retry, audit và idempotency được xác định?
8. **Data objects:** DTO/collection immutable đúng nghĩa, defensive copy cả nested objects, tránh lộ secrets?
9. **Lifecycle:** revoke, in-flight handling, resource cleanup, listener/task cancellation và generation replacement rõ ràng?
10. **Class identity:** API/SPI shared loader/module đúng, không có copy type gây `ClassCastException`?
11. **Defense in depth:** process identity, filesystem permissions, network egress, secrets separation, IPC hạn chế?
12. **Tests:** cả allow/deny, traversal, symlink race, forged identity, quota, revoke và adversarial behavior?

**Kết luận:** host phải giới hạn **đối tượng**, **đường dẫn** và **dịch vụ** được cấp cho extension bằng façade/capability có chức năng nhỏ, kiểm tra policy ở từng operation, ánh xạ resource từ logical ID và phối hợp revoke theo lifecycle. Các class loader/module chỉ tổ chức code và API boundary; muốn chống lại plugin đối kháng cần bổ sung process isolation và quyền OS, vì một interface hẹp không tự loại bỏ quyền hệ thống mà mã chạy trong cùng JVM có thể sử dụng.