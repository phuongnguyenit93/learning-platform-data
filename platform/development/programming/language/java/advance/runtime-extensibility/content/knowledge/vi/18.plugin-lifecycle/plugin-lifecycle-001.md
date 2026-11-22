# Thiết kế các trạng thái phát hiện, xác minh, khởi tạo, hoạt động, dừng và lỗi trong vòng đời plugin Java

## 1. Vì sao plugin cần một mô hình trạng thái?

Plugin là phần mở rộng được host khám phá và gọi thông qua hợp đồng API chung. Một plugin có thể là class được đăng ký bằng Java SPI (`ServiceLoader`), một named module được đưa vào `ModuleLayer`, hoặc một JAR được host nạp bằng class loader riêng. Trong cả ba trường hợp, việc **tìm thấy class** không đồng nghĩa plugin **đã sẵn sàng nhận yêu cầu**.

Hệ thống cần trả lời chính xác:

- Host đã **phát hiện** được plugin hay chưa?
- Plugin đã được **xác minh** về danh tính, phiên bản, cấu hình, capability và dependency chưa?
- Plugin đã được **khởi tạo** tài nguyên, nhận cấu hình và service từ host chưa?
- Plugin đã **hoạt động** và có thể nhận lệnh mới chưa?
- Plugin đang **dừng** hay đã giải phóng tài nguyên xong?
- Plugin đang **lỗi** vì nguyên nhân nào, và có cần thực hiện cleanup/rollback không?

Nếu chỉ dùng biến `boolean loaded`, host rất dễ gặp các lỗi như gọi plugin trước khi cấu hình xong, đưa một instance lỗi vào registry, tiếp nhận request mới khi shutdown, chạy `stop` hai lần hoặc giữ thread/class loader cũ sau khi nâng cấp.

**Giải pháp:** thiết kế một *finite-state machine* (máy trạng thái hữu hạn) có **trạng thái rõ ràng, chuyển trạng thái hợp lệ, điều kiện gác (*guards*), sự kiện kích hoạt và hành động cleanup**. Bài này tập trung vào sáu pha cốt lõi theo vòng đời: **phát hiện → xác minh → khởi tạo → hoạt động → dừng**, với nhánh **lỗi** có thể phát sinh từ nhiều pha.

> Các tên trạng thái trong bài là **thiết kế của host/plugin manager**, không phải một enum chuẩn được Java tự tạo. `ServiceLoader`, `ModuleLayer` và `ClassLoader` không quản lý sẵn những trạng thái nghiệp vụ này.

## 2. Một mô hình trạng thái tối thiểu nhưng đầy đủ

Có thể đặt tên các trạng thái:

| Trạng thái | Ý nghĩa | Được phép nhận request nghiệp vụ? |
| --- | --- | --- |
| `DISCOVERED` — Đã phát hiện | Host có một đối tượng provider/metadata được tìm thấy, chưa xác minh toàn bộ điều kiện hoạt động | Không |
| `VERIFIED` — Đã xác minh | Danh tính, contract, policy, cấu hình và dependency cần thiết đã qua bước kiểm tra phù hợp | Không |
| `INITIALIZED` — Đã khởi tạo | Plugin được cấp context/tài nguyên ban đầu; chưa được kích hoạt để xử lý request | Không |
| `ACTIVE` — Hoạt động | `start` và readiness check thành công; plugin đã được publish vào dispatcher/registry | **Có** |
| `STOPPING` — Đang dừng | Host chặn request mới, thực hiện dọn dẹp, hủy listener và giải phóng tài nguyên | Không |
| `STOPPED` — Đã dừng | Cleanup hoàn tất theo hợp đồng; instance không còn được tái sử dụng tùy tiện | Không |
| `FAILED` — Lỗi | Một chuyển trạng thái/hoạt động đã thất bại; phải lưu nguyên nhân và quyết định cleanup/khôi phục | Không |

Trong production, nên thêm `DISCOVERING`, `VERIFYING`, `INITIALIZING`, `STARTING` và **`QUIESCING`** (đã ngừng nhận request mới, đang chờ request cũ kết thúc) nếu các thao tác này kéo dài hoặc bất đồng bộ. Bảng trên mô hình hóa các **mốc đã hoàn thành** để ví dụ dễ quan sát.

### 2.1. Sơ đồ trạng thái

```text
       [quét artifact / SPI / module finder]
                       │
             tìm được provider
                       ▼
                  DISCOVERED
                       │ verify + policy checks
                       ▼
                   VERIFIED
                       │ initialize / inject context
                       ▼
                  INITIALIZED
                       │ start + readiness succeeds
                       ▼
                    ACTIVE ───────────► xử lý request
                       │                       │
                       └──── stop requested ◄──┘
                               │
                               ▼
                            STOPPING
                               │ cleanup succeeds
                               ▼
                            STOPPED

  DISCOVERED / VERIFIED / INITIALIZED / ACTIVE
                   │ có lỗi
                   ▼
                 FAILED
                   │ ghi nguyên nhân, cleanup phần đã cấp phát
                   ▼
                STOPPING
                   ├── cleanup thành công ──► STOPPED
                   └── cleanup thất bại  ──► FAILED (terminal/needs intervention)
```

Ở đây `FAILED` có thể là **trạng thái tạm để bắt đầu cleanup** hoặc **trạng thái cuối nếu cleanup không thành công**. Phải lưu riêng **lịch sử lỗi** (`lastFailure`, `hadFailure`, timestamp, stage) vì sau khi cleanup thành công đối tượng có thể chuyển thành `STOPPED`; nếu chỉ nhìn trạng thái cuối sẽ mất thông tin rằng lần khởi động vừa thất bại.

Trong hệ thống dùng hot reload, **không nên** tự động chuyển `STOPPED → ACTIVE` trên cùng object nếu implementation không hỗ trợ tái khởi động. Phương án an toàn mặc định là **tạo instance mới** và chạy lại quy trình xác minh/khởi tạo.

### 2.2. Sự kiện và điều kiện chuyển trạng thái

| Trạng thái hiện tại | Sự kiện | Điều kiện thành công | Trạng thái tiếp theo | Hành động |
| --- | --- | --- | --- | --- |
| Chưa có instance | `provider discovered` | SPI/registry tìm và tạo được instance cần thiết | `DISCOVERED` | Gắn ID, artifact và thông tin provenance |
| `DISCOVERED` | `verify` | ID, API/version, policy, metadata và dependency hợp lệ | `VERIFIED` | Ghi kết quả xác minh |
| `VERIFIED` | `initialize` | Context và tài nguyên khởi tạo được cấp thành công | `INITIALIZED` | Giữ ownership/resource handles |
| `INITIALIZED` | `start` | Start và readiness hoàn tất | `ACTIVE` | Chỉ lúc này publish để nhận request |
| `ACTIVE` | `stop requested` | Ngừng nhận request mới; công việc đang chạy được xử lý theo policy | `STOPPING` | Quiesce và cleanup |
| `STOPPING` | `cleanup completed` | Tài nguyên do plugin sở hữu đã được giải phóng | `STOPPED` | Gỡ tham chiếu/registry |
| Bất kỳ pha chưa kết thúc | `operation failed` | Có lỗi xác minh, khởi tạo, start hoặc invocation nghiêm trọng | `FAILED` | Giữ exception/cause, không dispatch |
| `FAILED` | `cleanup requested` | Có thể thực hiện cleanup an toàn trên trạng thái từng phần | `STOPPING` | Dọn tài nguyên đã mở |
| `STOPPING` | `cleanup failed` | Exception khi dừng | `FAILED` | Ghi lỗi cleanup và escalation |

**Quan trọng:** Không có provider nào được tìm thấy là **kết quả của bước discovery**, có thể được báo thành `NOT_FOUND` ở cấp yêu cầu/registry mà **không tạo một instance plugin để gắn `DISCOVERED`**. Một provider được khai báo nhưng không thể nạp hoặc khởi tạo có thể gây `ServiceConfigurationError` hoặc lỗi JVM liên quan; đó không phải `Optional.empty()` bình thường.

## 3. Những bất biến (invariants) phải bảo vệ

Một state machine tốt không chỉ có tên trạng thái; nó có các quy tắc luôn đúng:

1. **Chỉ `ACTIVE` mới được nhận request mới.** `DISCOVERED`/`VERIFIED`/`INITIALIZED` chưa đủ; `FAILED` và `STOPPING` phải từ chối.
2. **Không publish sớm.** Registry/dispatcher chỉ được nhìn thấy instance sau khi `start` và readiness thành công; nếu `start` ném lỗi, instance không được publish.
3. **Mỗi bước chỉ thực hiện theo thứ tự cho phép.** Không có `DISCOVERED → ACTIVE` nếu cần verify và initialize.
4. **Lỗi phải giữ nguyên nhân gốc.** Không biến mọi lỗi thành “plugin không tồn tại”; giữ phase, stack/cause và mã lỗi có ý nghĩa.
5. **Cleanup được gọi trên cả thành công lẫn thất bại.** Đặc biệt khi `initialize`/`start` đã mở một phần tài nguyên rồi ném lỗi.
6. **Cleanup cần an toàn khi gọi nhiều lần theo hợp đồng** (idempotent hoặc có cơ chế chống gọi lặp ở manager). Plugin không được để `stop` lặp gây double-close nguy hiểm.
7. **STOPPED là trạng thái kết thúc của instance** trong mô hình mặc định. Muốn chạy lại hãy tạo instance mới thay vì tái sử dụng object có state khó đoán.
8. **Quyết định chuyển trạng thái phải nguyên tử** khi nhiều thread cùng yêu cầu dừng, chạy request hoặc báo lỗi. Một biến enum không tự giải quyết *race condition* nếu không có synchronization/atomic protocol.
9. **Tài nguyên thuộc ai, người đó đóng.** Host đóng executor/loader do host tạo; plugin đóng stream/listener/connection của plugin; tránh cả hai cùng đóng một resource mà không có contract.
10. **Có thể truy vết lịch sử:** trạng thái cuối `STOPPED` không xóa thông tin đã từng `FAILED`, số lần thử khởi động, thời gian cleanup và kết quả cuối.

### 3.1. Trạng thái khác sự kiện, khác health

- **Trạng thái (`State`):** hiện tại plugin đang ở mốc vòng đời nào, ví dụ `ACTIVE`.
- **Sự kiện (`Event`):** điều xảy ra thúc đẩy chuyển trạng thái, ví dụ `START_SUCCEEDED`, `STOP_REQUESTED`.
- **Health/readiness:** kết quả kiểm tra khả năng phục vụ tại một thời điểm. Plugin có thể thuộc `ACTIVE` nhưng trở thành *unhealthy* vì backend tạm thời mất kết nối; host phải định chính sách đưa khỏi routing hoặc chuyển sang failure/quiescing.
- **Desired state:** mục tiêu do operator đặt, ví dụ `ENABLED`/`DISABLED`; nó không tương đương trạng thái thực tế. Operator có thể muốn enabled nhưng plugin đang `FAILED`.

Nếu chỉ dùng một enum để trộn bốn khái niệm, host sẽ khó giải quyết tình huống crash, restart, thay version hoặc dependency của plugin bị lỗi.

## 4. Phát hiện: từ artifact đến `DISCOVERED`

### 4.1. Discovery có thể diễn ra theo nhiều lớp

Plugin có thể được phát hiện bằng:

- **Java SPI**: `ServiceLoader.load(Extension.class)` phát hiện implementation đã đăng ký trong `META-INF/services` hoặc khai báo JPMS `provides`.
- **Artifact registry/manifest**: host quét thư mục JAR/module repository, nhận metadata về plugin ID, version, dependency, capability.
- **JPMS**: `ModuleFinder` quan sát module artifact; `Configuration.resolve(...)` giải quyết module graph; `ModuleLayer` định nghĩa module runtime.
- **Class loader riêng**: host cấu hình URL/class loader/module layer rồi tìm lớp theo hợp đồng.

Đó là các lựa chọn kỹ thuật, không phải các trạng thái `ACTIVE`. Chẳng hạn `ServiceLoader.findFirst()` có thể trả `Optional<Extension>` chứa một instance mới, nhưng **constructor đã chạy không đồng nghĩa `start()` đã được gọi**.

### 4.2. Cẩn thận với mã chạy trong bước khám phá

Khi `ServiceLoader` tạo instance, constructor hoặc static initializer có thể chạy. Vì vậy discovery không nhất thiết hoàn toàn “không có side effect”. Nếu muốn xác minh metadata trước khi tạo instance, host có thể đọc manifest của artifact/registry hoặc làm việc với `ServiceLoader.Provider<S>` và `type()` trước `get()`; dù vậy nạp class/metadata vẫn có thể phát sinh lỗi. **Class loader không phải sandbox**, nên không chạy plugin không tin cậy với quyền của tiến trình chính mà thiếu ranh giới an toàn.

### 4.3. Phân biệt vắng mặt với lỗi provider

```java
Optional<Extension> found =
    ServiceLoader.load(Extension.class).findFirst();

if (found.isEmpty()) {
    System.out.println("Không có extension provider");
}
```

Đây là đoạn minh họa cần import và interface. `Optional.empty()` thể hiện không có provider sau khi duyệt bình thường. Provider được đăng ký hỏng hoặc không thể tạo có thể làm `ServiceLoader` ném `ServiceConfigurationError`. Không nên bắt mọi lỗi rồi trả `Optional.empty()`; làm vậy che cấu hình sai.

Nếu có nhiều providers, `findFirst()` không bảo đảm chọn đúng bản mong muốn. Host cần chọn theo ID/capability/version/priority, xác minh chính sách rồi mới tạo/kích hoạt plugin. Việc lựa chọn provider cũng **không tự quản lý dependency hoặc vòng đời**.

## 5. Xác minh: `DISCOVERED → VERIFIED`

Bước **verify** phải xác minh điều kiện để plugin **được phép thử khởi tạo**, không chỉ kiểm tra class implement đúng interface.

### 5.1. Những thứ nên kiểm tra

| Nhóm | Câu hỏi |
| --- | --- |
| Danh tính | Plugin ID hợp lệ, không trùng? Tên/nguồn artifact rõ ràng? |
| Tính toàn vẹn/nguồn | JAR có nguồn đáng tin, checksum/chữ ký được xác thực nếu policy yêu cầu? |
| Contract/API | Plugin dùng đúng interface/binary API, minimum host version và class identity? |
| Phiên bản | Plugin/dependency version thỏa compatibility matrix? |
| Phụ thuộc | Có đủ module/JAR, host services và plugin phụ thuộc ở trạng thái cần thiết? |
| Cấu hình | Các key bắt buộc, secret handles, đường dẫn namespace và schema hợp lệ? |
| Capability/permission | Plugin có được bật trong môi trường hiện tại? Tính năng yêu cầu có được cấp? |
| Policy | Giới hạn tenant, giới hạn CPU/memory, quyền truy cập mạng/filesystem nếu hệ thống hỗ trợ? |

Không thể mặc định một lời gọi `plugin.verify()` đơn lẻ sẽ tự kiểm tra **tất cả** điều trên. Chúng cần sự phối hợp giữa plugin manager, metadata và những dịch vụ bảo mật/cấu hình của host.

### 5.2. Xác minh trước khi cấp quyền

Nếu xác minh phụ thuộc vào metadata trong JAR, nên kiểm tra những thứ có thể kiểm tra **trước khi tạo instance/chạy code**. Các dữ liệu do chính plugin khai báo có thể thiếu hoặc không đáng tin nếu plugin đến từ nguồn lạ. Tách rõ:

1. **Pre-instantiation checks** của host: định danh artifact, chữ ký, manifest, compatibility, dependency graph.
2. **Post-instantiation validation** của plugin: kiểm tra cấu hình hoặc capability yêu cầu sau khi được cấp một context tối thiểu.

Không dùng class loader để thay thế OS sandbox cho mã độc. Một JAR có quyền thực thi code trong JVM không tự trở nên an toàn khi nó đã qua module resolution.

### 5.3. Xác minh lỗi thì sao?

Nếu thiếu dependency bắt buộc, ID xung đột, API không tương thích hoặc cấu hình không hợp lệ, manager:

- Ghi `FAILED` và nguyên nhân ở pha verify (hoặc loại artifact trước khi tạo plugin instance).
- Không gọi `initialize`/`start`, không đưa plugin vào registry nhận request.
- Dọn các tài nguyên đã thực sự mở trong discovery/validation; không assume chưa có gì cần cleanup.
- Truyền thông tin lỗi có thể hành động: plugin ID, version, dependency thiếu, nguồn artifact, stage.

## 6. Khởi tạo: `VERIFIED → INITIALIZED`, rồi kích hoạt `ACTIVE`

### 6.1. Tách constructor, initialize và start

Có ít nhất ba mốc rất dễ bị gộp:

- **Constructor/provider creation:** JVM tạo object; cố gắng giữ nhẹ, không mở connection hay spawn thread nặng.
- **`initialize(context)`:** host truyền cấu hình, logger, repository, service facade và resource handles; plugin chuẩn bị trạng thái.
- **`start()`:** plugin đăng ký listener hoặc chạy thành phần cần thiết; hoàn tất readiness; từ đây manager mới cho phép nhận request.

Tại lúc `initialize` hoàn thành, trạng thái là `INITIALIZED`, chưa phải `ACTIVE`. Host có thể gọi thêm readiness check trong `start` hoặc tách thành pha `STARTING` nếu cần.

### 6.2. Thiết kế một plugin context

```java
public record PluginContext(
    java.util.logging.Logger logger,
    java.nio.file.Path configDirectory,
    java.time.Clock clock) {
}
```

Đây là đoạn **minh họa API**, có thể cần điều chỉnh visibility/ownership trong dự án. Thay vì để plugin tự đoán thư mục làm việc hoặc truy cập singleton toàn cục, host cấp dependency qua context. Context không nên trao cho plugin quyền lớn hơn nhu cầu. Secret có thể cấp qua một interface quản lý secret; không nhét token vào log hay lỗi.

### 6.3. Khởi tạo một phần và rollback

Một chuỗi thực tế:

```text
initialize
  ├── mở connection pool  [OK]
  ├── tạo executor         [OK]
  ├── đăng ký listener     [FAILED]
  └── return               [không tới]
```

Plugin đã **thất bại trước khi đạt `INITIALIZED`** nhưng hai resource đầu vẫn tồn tại. Manager phải gọi cleanup qua contract an toàn khi khởi tạo một phần. Implementation cũng nên dùng `try/finally` hoặc `try-with-resources` ở bên trong `initialize` để dọn ngay tài nguyên đã tạo trước khi ném lỗi.

Nên ghi rõ trong interface: `stop()` (hoặc `close()`) **phải an toàn** nếu `initialize()` chưa được gọi, gọi chưa thành công, `start()` lỗi giữa chừng, hoặc stop đã chạy trước đó. Nếu không bảo đảm được, plugin manager phải theo dõi chính xác các resource handles và gọi cleanup dựa trên mốc cấp phát.

## 7. Hoạt động: chỉ `ACTIVE` mới nhận yêu cầu

Khi plugin đã sẵn sàng:

1. `start()` hoàn tất, readiness check thành công.
2. Manager chuyển trạng thái sang `ACTIVE`.
3. Plugin được đưa vào dispatch registry (phải phối hợp nguyên tử với trạng thái).
4. Request mới có thể được gửi đến implementation.

Đừng publish plugin khi vẫn `INITIALIZED` hoặc đang `STARTING`. Đừng dùng `if (plugin != null)` để quyết định chạy, vì **instance tồn tại chưa có nghĩa nó hoạt động**.

### 7.1. Lỗi xử lý request: tất cả có làm plugin FAILED không?

Không nhất thiết. Hãy phân biệt:

- **Lỗi nghiệp vụ có thể phục hồi:** đầu vào không hợp lệ, yêu cầu không được hỗ trợ, timeout riêng một request. Có thể trả lỗi request và giữ plugin `ACTIVE`.
- **Lỗi sức khỏe/sự cố hệ thống:** connection pool hỏng, worker thread chết, context sai, state internal corrupt. Manager có thể chuyển `FAILED` hoặc `QUIESCING` tùy policy và health check.
- **Lỗi nghiêm trọng của JVM:** như `OutOfMemoryError` hoặc một số `LinkageError`; không nên bắt `Throwable` rồi giả vờ plugin vẫn hoạt động bình thường.

Plugin manager cần **error policy** tường minh: lỗi nào chỉ ảnh hưởng một request, lỗi nào cần circuit breaker, lỗi nào bắt buộc dừng plugin.

### 7.2. Đồng thời và request đang chạy

Production thường có thread A xử lý request và thread B nhận lệnh dừng:

```text
Thread A:  [kiểm tra ACTIVE] ───► [đang xử lý] ───► [trả kết quả]
Thread B:                      [STOP REQUESTED] ─► [dọn resource]
```

Nếu B đóng connection trong khi A vẫn dùng, request có thể thất bại hoặc làm hỏng dữ liệu. Giải pháp là protocol kiểu **quiescing**:

```text
ACTIVE
   │ khóa cổng request mới (atomic)
   ▼
QUIESCING ── chờ inflight=0 / deadline ──► STOPPING
                                           │
                                           ▼
                                        STOPPED
```

Dispatcher cần cấp một *lease/in-flight token* chỉ khi trạng thái còn `ACTIVE`, tăng bộ đếm request đang chạy **trong cùng critical section** với kiểm tra state. Khi request hoàn tất, giảm đếm và đánh thức shutdown. Khi đóng cổng, không request mới nào nhận lease, rồi host đợi số đang chạy về 0 hoặc đạt deadline theo chính sách. Chỉ sau đó mới dọn tài nguyên mà request đang dùng.

**Không đủ** nếu chỉ dùng hai thao tác rời `if (state == ACTIVE)` rồi `inFlight++`, vì `STOPPING` có thể xen vào ở giữa. `volatile State` giúp thấy giá trị mới nhưng **không biến hai thao tác thành một transition nguyên tử**.

## 8. Dừng: `ACTIVE/FAILED → STOPPING → STOPPED`

Một quy trình shutdown tốt có các bước:

1. Đánh dấu `QUIESCING` hoặc `STOPPING` và rút instance khỏi danh sách nhận request mới.
2. Đợi/hủy các request còn chạy theo deadline có kiểm soát.
3. Gỡ listener, scheduler task, callback, metric hooks, event subscriptions và các object đăng ký vào host.
4. Đóng connection, stream, file watcher, executor/thread, temporary files và handles mà plugin sở hữu.
5. Cắt tham chiếu từ registry, cache, `ThreadLocal`/TCCL nếu những tham chiếu này do host/plugin tạo.
6. Nếu host tạo `URLClassLoader`, cân nhắc `close()` sau khi không còn sử dụng. **Không** cho rằng `close()` tự dừng thread hoặc bảo đảm unload class.
7. Ghi kết quả cleanup, trạng thái cuối và nguyên nhân lỗi nếu từng có.

Nếu `stop()` bị gọi lặp, có hai cơ chế bảo vệ bổ sung:

- **Plugin idempotent:** `stop()` lặp an toàn, không gửi double-delete hoặc đóng tài nguyên không đúng chủ sở hữu.
- **Manager once-only guard:** đảm bảo cùng lifecycle instance chỉ khởi động một lần và cleanup được lên lịch một lần. Trong hệ thống bất đồng bộ, guard nên dùng atomic compare-and-set hoặc lock thích hợp.

### 8.1. Dừng theo thứ tự phụ thuộc

Giả sử `ReportingPlugin` cần `StoragePlugin` để flush dữ liệu. Khi khởi động:

```text
Storage → Reporting
```

Khi dừng, đảo thứ tự:

```text
Reporting → Storage
```

Mặc dù `ServiceLoader` tìm được cả hai provider, nó không giải quyết thứ tự này. Plugin manager cần dependency graph. Nếu Storage đã stop trước Reporting, bước flush trong Reporting có thể thất bại hoặc mất dữ liệu.

### 8.2. Đóng class loader khác dừng plugin

Thay JAR và gọi `ServiceLoader.reload()` chỉ làm `ServiceLoader` quên cache provider; nó **không** thay bytecode đã được nạp trong loader hiện tại, không gọi `stop` và không tự đóng tài nguyên. Hot reload cần instance/loader mới, xác minh tương thích, khởi động, chuyển traffic, quiesce instance cũ, stop, xóa callback/thread/caches rồi dọn loader cũ.

Layer/class loader chỉ giúp kiến trúc nạp mã, **không** tự quản lý lifecycle nghiệp vụ.

## 9. Lỗi: cách thiết kế `FAILED` không che khuất nguyên nhân

`FAILED` cần có **thông tin đi kèm**, không chỉ một nhãn enum.

Một bản ghi có thể gồm:

```text
pluginId: echo
pluginVersion: 1.4.0
phase: STARTING
state: FAILED
errorCode: START_FAILED
message: Backend unavailable
timestamp: 2026-11-01T10:00:00Z
retryable: false  (theo policy của host)
cleanupStatus: PENDING
```

Đây chỉ là **dữ liệu minh họa**, không phải log của demo bên dưới. Khi cleanup hoàn tất, có thể thấy `state=STOPPED` nhưng `lastFailure` và `cleanupStatus=COMPLETED` vẫn được lưu để người vận hành biết lần chạy đã lỗi.

### 9.1. Bảng lỗi và phản ứng

| Pha | Lỗi mẫu | Phản ứng đề xuất |
| --- | --- | --- |
| Discovery | Không có provider | Trả “không tìm thấy” ở cấp host; có thể dùng fallback theo policy |
| Discovery | Descriptor SPI sai, không tạo được provider | Báo `ServiceConfigurationError`/classload failure, không coi là “không có” |
| Verify | Sai API version, thiếu dependency, ID trùng | Đánh dấu lỗi hoặc từ chối artifact, không khởi tạo |
| Initialize | File cấu hình lỗi, tạo connection một phần | Không publish; dọn phần đã mở, giữ nguyên nhân |
| Start | Đăng ký listener thất bại, readiness timeout | `FAILED`, rollback/dừng, không chuyển `ACTIVE` |
| Active | Input không hợp lệ | Trả lỗi riêng request, có thể vẫn `ACTIVE` |
| Active | Internal state corrupt hoặc dependency mất kéo dài | Quiesce/`FAILED` theo policy, tránh dispatch mới |
| Stop | Resource close throw | Tiếp tục dọn các resource khác khi có thể; ghi lỗi cleanup; escalation |
| Hot reload | Version mới start thất bại | Giữ phiên bản cũ hoạt động nếu chưa switch; cleanup bản mới |

### 9.2. Có nên retry từ `FAILED`?

Không tự động gọi lại `start()` trên object cũ khi không biết nó đã khởi tạo bao nhiêu tài nguyên. Một policy an toàn mặc định:

```text
FAILED instance
   → best-effort cleanup
   → STOPPED (giữ failure history)
   → đợi backoff/policy
   → DISCOVER instance MỚI
   → VERIFY → INITIALIZE → START
```

Nếu plugin hỗ trợ restart cùng instance, điều này phải được hợp đồng API quy định rõ và được test với mọi bước lỗi/tài nguyên. Mọi retry phải giới hạn số lần, có backoff và tránh lặp vô hạn khi dependency vẫn sai.

## 10. Ví dụ Java 17+ chạy được: state machine rõ ràng với SPI

Ví dụ gồm:

- **`Extension`**: contract chung và một record chứa option do host cấp.
- **`EchoExtension`**: provider được đăng ký bằng Java SPI; cho phép mô phỏng `start()` thành công hoặc thất bại.
- **`Main`**: host dùng `ServiceLoader.findFirst()` để khám phá, sau đó điều phối `VERIFIED → INITIALIZED → ACTIVE`, và dù thành công hay lỗi cũng cleanup qua `STOPPING → STOPPED`.

Ví dụ cố ý dùng **một thread, một provider, một lần chạy** để state transitions và stdout hoàn toàn xác định. Nó không mô phỏng concurrency/quiescing production và không phải sandbox.

### 10.1. Cấu trúc thư mục

```text
demo/
├── src/
│   └── demo/
│       ├── api/
│       │   └── Extension.java
│       ├── impl/
│       │   └── EchoExtension.java
│       └── host/
│           └── Main.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.api.Extension
```

### 10.2. Contract: `src/demo/api/Extension.java`

```java
package demo.api;

public interface Extension {
    record Options(boolean failStart) {}

    String id();
    void verify() throws Exception;
    void initialize(Options options) throws Exception;
    void start() throws Exception;
    String invoke(String value) throws Exception;
    void stop() throws Exception;
}
```

**Ý nghĩa contract:**

- `verify` kiểm tra điều kiện mà provider có thể tự xác minh; host còn phải thực hiện các policy checks bên ngoài.
- `initialize` cấp options/context và chuẩn bị tài nguyên.
- `start` kích hoạt plugin; chỉ khi thành công host mới chuyển sang `ACTIVE`.
- `invoke` chỉ được gọi khi ACTIVE.
- `stop` có trách nhiệm cleanup và **phải an toàn** cả khi `initialize` hoặc `start` chưa hoàn thành. Demo cho phép gọi lặp.

Trong ví dụ `Options.failStart` là cờ kiểm thử lỗi, không phải một kiến trúc config đầy đủ. Trong ứng dụng thực tế nên thay bằng `PluginContext` typed, logger, config, host services và policy hạn chế quyền.

### 10.3. Implementation: `src/demo/impl/EchoExtension.java`

```java
package demo.impl;

import demo.api.Extension;
import java.util.Objects;

public final class EchoExtension implements Extension {
    private Options options;
    private boolean active;

    public EchoExtension() {
    }

    @Override
    public String id() {
        return "echo";
    }

    @Override
    public void verify() {
        if (!"echo".equals(id())) {
            throw new IllegalStateException("invalid plugin id");
        }
    }

    @Override
    public void initialize(Options options) {
        this.options = Objects.requireNonNull(options);
    }

    @Override
    public void start() {
        if (options == null) {
            throw new IllegalStateException("not initialized");
        }
        if (options.failStart()) {
            throw new IllegalStateException("start refused");
        }
        active = true;
    }

    @Override
    public String invoke(String value) {
        if (!active) {
            throw new IllegalStateException("plugin not active");
        }
        return "ECHO: " + value;
    }

    @Override
    public void stop() {
        active = false;
        options = null;
        System.out.println("[plugin] cleanup called");
    }
}
```

`stop()` chỉ reset state trong demo, nhưng được viết để **không cần `start()` thành công**. Điều này cho phép host cleanup sau tình huống `start refused`. Trong plugin thật, `stop()` phải đóng chính xác các resource đã được cấp phát và tránh double-close.

Trạng thái `active` ở implementation chỉ là guard minh họa, **không phải đồng bộ hóa thread-safe**. Manager sở hữu trạng thái vòng đời có tính chính thức; plugin có thể tự bảo vệ method của mình như lớp phòng thủ thứ hai.

### 10.4. Host/manager: `src/demo/host/Main.java`

```java
package demo.host;

import demo.api.Extension;
import java.util.Objects;
import java.util.Optional;
import java.util.ServiceLoader;

public final class Main {
    enum State {
        DISCOVERED,
        VERIFIED,
        INITIALIZED,
        ACTIVE,
        STOPPING,
        STOPPED,
        FAILED
    }

    static final class Lifecycle {
        private final Extension plugin;
        private State state = State.DISCOVERED;
        private boolean hadFailure;
        private boolean cleanupAttempted;
        private boolean runCalled;

        Lifecycle(Extension plugin) {
            this.plugin = Objects.requireNonNull(plugin);
            System.out.println("[host] state: " + state);
        }

        void run(boolean failStart) {
            if (runCalled) {
                throw new IllegalStateException(
                    "Lifecycle already used");
            }
            runCalled = true;

            try {
                // 1. VERIFIED: host policy + plugin-side checks.
                if (!plugin.id().matches("[a-z][a-z0-9-]*")) {
                    throw new IllegalArgumentException(
                        "invalid plugin ID");
                }
                plugin.verify();
                moveTo(State.VERIFIED);

                // 2. INITIALIZED: inject the test context.
                plugin.initialize(new Extension.Options(failStart));
                moveTo(State.INITIALIZED);

                // 3. ACTIVE only after start completes.
                plugin.start();
                moveTo(State.ACTIVE);

                System.out.println("[host] result: "
                    + plugin.invoke("Java"));
            } catch (Exception error) {
                hadFailure = true;
                moveTo(State.FAILED);
                System.out.println(
                    "[host] error: " + error.getMessage());
            } finally {
                shutdown();
                System.out.println(
                    "[host] had failure: " + hadFailure);
            }
        }

        private void shutdown() {
            if (cleanupAttempted) {
                return;
            }
            cleanupAttempted = true;

            moveTo(State.STOPPING);
            try {
                // Contract: stop is safe even after partial start.
                plugin.stop();
                moveTo(State.STOPPED);
            } catch (Exception error) {
                hadFailure = true;
                moveTo(State.FAILED);
                System.out.println(
                    "[host] cleanup error: " + error.getMessage());
            }
        }

        private void moveTo(State next) {
            boolean allowed = switch (state) {
                case DISCOVERED ->
                    next == State.VERIFIED
                    || next == State.FAILED
                    || next == State.STOPPING;
                case VERIFIED ->
                    next == State.INITIALIZED
                    || next == State.FAILED
                    || next == State.STOPPING;
                case INITIALIZED ->
                    next == State.ACTIVE
                    || next == State.FAILED
                    || next == State.STOPPING;
                case ACTIVE ->
                    next == State.FAILED
                    || next == State.STOPPING;
                case FAILED -> next == State.STOPPING;
                case STOPPING ->
                    next == State.STOPPED
                    || next == State.FAILED;
                case STOPPED -> false;
            };

            if (!allowed) {
                throw new IllegalStateException(
                    "Illegal transition: " + state + " -> " + next);
            }
            state = next;
            System.out.println("[host] state: " + state);
        }
    }

    public static void main(String[] args) {
        if (args.length > 1
                || (args.length == 1
                    && !args[0].equals("fail-start"))) {
            throw new IllegalArgumentException(
                "Usage: Main [fail-start]");
        }

        // SPI discovery. Without a provider, no Lifecycle is created.
        Optional<Extension> found =
            ServiceLoader.load(Extension.class).findFirst();

        if (found.isEmpty()) {
            System.out.println("[host] no provider discovered");
            return;
        }

        Lifecycle manager = new Lifecycle(found.orElseThrow());
        manager.run(args.length == 1);
    }
}
```

**Ý nghĩa các guard trong host:**

- `Lifecycle` bắt đầu ở `DISCOVERED` **sau** khi SPI trả instance hợp lệ. Nếu không có provider, không tạo `Lifecycle`.
- `moveTo` xác minh mọi cạnh của đồ thị trạng thái. Các chuyển không hợp lệ ném `IllegalStateException` để phát hiện lỗi lập trình.
- `runCalled` ngăn dùng lại cùng manager theo cách ngẫu nhiên.
- `ACTIVE` chỉ được ghi sau khi `plugin.start()` trả về thành công; `invoke` nằm sau đó.
- `catch (Exception)` ghi failure và chuyển `FAILED`; `finally` gọi `shutdown` ngay cả khi `verify`, `initialize`, `start` hoặc `invoke` ném exception.
- `cleanupAttempted` ngăn gọi cleanup nhiều lần từ host; implementation `stop()` vẫn cần hỗ trợ cleanup an toàn khi khởi tạo một phần.
- `hadFailure` lưu lại lịch sử thất bại **ngay cả khi trạng thái cuối là `STOPPED`**.

Đây là một mô hình **đồng bộ, đơn luồng**. Nếu các thao tác diễn ra trên nhiều thread, `runCalled`, `state`, `cleanupAttempted` và `hadFailure` cần được bảo vệ bằng lock/CAS, và shutdown phải tính đến request inflight. Không copy mã demo rồi coi nó là một plugin manager production thread-safe.

Một giới hạn khác: lỗi quá nghiêm trọng thuộc `Error` (ví dụ lỗi JVM/linkage) không được bắt bởi `catch (Exception)`; chương trình không giả vờ có thể phục hồi mọi sự cố. `ServiceConfigurationError` trong bước discovery cũng xảy ra **trước** khi tạo manager và cần xử lý ở ranh giới host phù hợp.

### 10.5. SPI descriptor

**`resources/META-INF/services/demo.api.Extension`**

```text
demo.impl.EchoExtension
```

Với classpath SPI, tên file phải là fully qualified name của interface, còn nội dung là tên class triển khai. Descriptor phải đóng **bên trong JAR provider** dưới đúng `META-INF/services`. Host chỉ phụ thuộc vào `demo.api.Extension`, không import `EchoExtension`.

### 10.6. Biên dịch/đóng JAR và chạy trên Windows PowerShell

Tại thư mục `demo`, yêu cầu **JDK 17+**:

```powershell
New-Item -ItemType Directory -Force build/host, build/plugin | Out-Null

# Host chứa contract và Lifecycle manager, chưa chứa provider.
javac -encoding UTF-8 -d build/host src/demo/api/Extension.java src/demo/host/Main.java

# Provider được compile riêng, tham chiếu cùng API của host.
javac -encoding UTF-8 -cp build/host -d build/plugin src/demo/impl/EchoExtension.java

# Đóng SPI descriptor vào JAR plugin.
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/demo.api.Extension build/plugin/META-INF/services/demo.api.Extension
jar --create --file build/echo-plugin.jar -C build/plugin .

# Trường hợp KHÔNG có provider trong runtime classpath.
java -cp build/host demo.host.Main

# Trường hợp có provider và start THÀNH CÔNG.
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main

# Trường hợp có provider nhưng start THẤT BẠI.
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main fail-start
```

Trên Windows, dấu `;` ngăn cách các phần tử classpath. Với Linux/macOS, đổi thành dấu `:`, ví dụ `java -cp 'build/host:build/echo-plugin.jar' demo.host.Main`, và thay những lệnh tạo/copy file PowerShell bằng `mkdir -p`, `cp` tương ứng.

### 10.7. Kết quả chạy chính xác: không có provider

Lệnh:

```powershell
java -cp build/host demo.host.Main
```

Stdout:

```text
[host] no provider discovered
```

Đây là **kết quả discovery không có ứng viên**. Không có instance nên không có `DISCOVERED`, `FAILED` hay `STOPPED` của một plugin cụ thể. Host có thể chọn thông báo, disable tính năng hoặc fallback theo chính sách.

### 10.8. Kết quả chạy chính xác: luồng thành công

Lệnh:

```powershell
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main
```

Stdout:

```text
[host] state: DISCOVERED
[host] state: VERIFIED
[host] state: INITIALIZED
[host] state: ACTIVE
[host] result: ECHO: Java
[host] state: STOPPING
[plugin] cleanup called
[host] state: STOPPED
[host] had failure: false
```

Có hai điều dễ kiểm chứng:

1. `result: ECHO: Java` chỉ xuất hiện **sau** khi trạng thái `ACTIVE` đã được ghi.
2. `cleanup called` nằm **giữa `STOPPING` và `STOPPED`**; host không tuyên bố đã dừng trước khi `plugin.stop()` hoàn tất.

### 10.9. Kết quả chạy chính xác: start thất bại và cleanup

Lệnh:

```powershell
java -cp 'build/host;build/echo-plugin.jar' demo.host.Main fail-start
```

Stdout:

```text
[host] state: DISCOVERED
[host] state: VERIFIED
[host] state: INITIALIZED
[host] state: FAILED
[host] error: start refused
[host] state: STOPPING
[plugin] cleanup called
[host] state: STOPPED
[host] had failure: true
```

Lần chạy lỗi **không có `ACTIVE`**, vì `plugin.start()` ném `IllegalStateException("start refused")`. Dù vậy, `finally` vẫn dọn tài nguyên. Trạng thái cuối là `STOPPED` nhưng `had failure: true` nhắc rằng plugin không từng sẵn sàng nhận request trong lần chạy này.

**Đây là sự khác biệt giữa lỗi và dừng:** `FAILED` ghi nhận sự cố; `STOPPING/STOPPED` ghi nhận tiến độ cleanup. Không nên mất một trong hai thông tin.

### 10.10. Điều ví dụ không giả định

- Không tự cài hot reload hoặc gỡ class đã nạp khỏi JVM.
- Không coi `ServiceLoader` là dependency resolver hay plugin lifecycle manager.
- Không đảm bảo an toàn khi nhiều thread đồng thời gọi invoke/stop.
- Không xử lý tất cả lỗi ngoài `Exception` hoặc bảo đảm khôi phục JVM sau lỗi hệ thống.
- Không tự phát hiện plugin không tin cậy theo chính sách chữ ký/OS quyền; bước verify ở demo chỉ kiểm tra ID và method mẫu.
- Không tự retry trên cùng instance sau `FAILED`.

Mỗi giới hạn trên cần chính sách và kiểm thử riêng trong ứng dụng thật.

## 11. Thiết kế nâng cao cho production: event-driven state machine

Khi plugin có bước start bất đồng bộ, nên phân biệt **lệnh yêu cầu chuyển** và **sự kiện hoàn thành**:

```text
DISCOVERED
   │ VERIFY_REQUESTED
   ▼
VERIFYING
   ├── VERIFY_SUCCEEDED → VERIFIED
   └── VERIFY_FAILED    → FAILED

VERIFIED
   │ INITIALIZE_REQUESTED
   ▼
INITIALIZING
   ├── INITIALIZE_SUCCEEDED → INITIALIZED
   └── INITIALIZE_FAILED    → FAILED

INITIALIZED
   │ START_REQUESTED
   ▼
STARTING
   ├── READY  → ACTIVE
   └── ERROR  → FAILED

ACTIVE
   │ STOP_REQUESTED
   ▼
QUIESCING ── inflight=0 hoặc deadline ──► STOPPING
                                          ├── STOP_OK → STOPPED
                                          └── STOP_ERR → FAILED
```

Nếu `start` trả về một `CompletionStage`, đừng đổi `STARTING → ACTIVE` ngay lúc nhận future; chỉ đổi khi hoàn tất thành công và readiness check đạt yêu cầu. Nếu future thất bại hay bị timeout, chuyển `FAILED`/cleanup và bỏ qua callback đến muộn theo phiên/generation đã hủy.

### 11.1. Số phiên (generation) để tránh callback cũ

Giả sử plugin version 1 đang stop, version 2 bắt đầu. Callback bất đồng bộ từ version 1 tới sau khi version 2 đã ACTIVE có thể cập nhật nhầm registry. Nên gắn transition với `pluginId + generation/version + instanceId`, và chỉ chấp nhận callback nếu nó còn là **generation hiện hành**.

Ví dụ trạng thái phải được liên kết với **instance cụ thể**, không lưu chỉ một `Map<String, State>` mà không kiểm tra instance ID trong khi nhiều bản được bật song song.

### 11.2. Atomic transition và publish

Một protocol production thường có:

1. Khóa/atomic CAS chuyển state nếu state hiện tại đúng kỳ vọng.
2. Ghi sự kiện và nguyên nhân với sequence number/timestamp.
3. Publish/unpublish registry một cách đồng bộ với việc chuyển state.
4. Không cho request mới nhận lease sau khi quiescing bắt đầu.
5. Giữ callback cleanup một lần cho một instance và kiểm tra generation.

Ví dụ guard dạng **pseudocode** (không phải Java code hoàn chỉnh):

```text
acquireRequestLease():
  lock
    require state == ACTIVE
    inFlight += 1
  unlock
  return lease whose close() decrements inFlight

beginStop():
  lock
    if state == ACTIVE:
      state = QUIESCING
      unpublish from dispatcher
    else:
      follow transition policy
  unlock
  wait for inFlight == 0 or deadline
  state = STOPPING
  cleanup()
```

Đây là phác thảo thuật toán. Khi triển khai thật, không nên giữ lock trong lúc chờ I/O hoặc gọi code plugin có thể block/re-enter host; phải xét deadlock, timeout và interrupt policy. Sau timeout, có thể vẫn còn code plugin đang chạy, nên không được giả định an toàn tuyệt đối khi đóng resource dùng chung; ứng dụng cần isolation/cancellation strategy phù hợp.

### 11.3. Persistence và crash recovery

Nếu host restart giữa `INITIALIZING` hoặc `STOPPING`, trạng thái in-memory sẽ mất. Cần phân biệt:

- **Runtime state**: trạng thái object cụ thể trong JVM đang sống.
- **Durable desired state**: plugin nào operator yêu cầu bật/tắt, version và policy được lưu.
- **Recovery state**: dấu vết lần khởi động trước nếu hệ thống cần audit/compensation.

Sau restart, không thể đơn giản khôi phục object `ACTIVE` từ database; JVM phải tạo instance mới, resolve dependency, verify, initialize, start và kiểm tra readiness lại. Với plugin có side effects bên ngoài, cần idempotency keys/compensation để tránh chạy tác vụ hai lần.

## 12. Chiến lược thử nghiệm và quan sát vòng đời

### 12.1. Ma trận test theo trạng thái

| Test | Kết quả cần xác minh |
| --- | --- |
| Không có provider | Host báo vắng mặt; không tạo state manager cho instance chưa tồn tại |
| Provider hợp lệ | `DISCOVERED → VERIFIED → INITIALIZED → ACTIVE → STOPPING → STOPPED` |
| Verify lỗi | Không gọi initialize/start, cleanup theo contract, giữ cause |
| Initialize lỗi giữa chừng | Không ACTIVE; đóng resource đã cấp phát; không leak |
| Start lỗi | `FAILED`, không dispatch; cleanup hoàn tất |
| Invoke khi `INITIALIZED` | Bị từ chối |
| Invoke khi `ACTIVE` | Được xử lý bình thường |
| Stop khi có request inflight | Không nhận request mới, đợi/hủy theo policy |
| Stop bị gọi hai lần | Không double-close/double-publish event |
| Stop ném exception | Ghi cleanup failure; không mất nguyên nhân lỗi khởi đầu |
| Retry sau FAILED | Tạo instance/generation mới theo policy, không hồi sinh instance hỏng |
| Hai plugin có dependency | Start theo topo order, stop theo thứ tự ngược |
| Hot reload version mới lỗi | Nếu chưa switch, bản cũ vẫn hoạt động; bản mới cleanup |
| Host restart | Không “khôi phục ACTIVE” chỉ từ state cũ; thực thi lại pipeline |

Có thể dùng fake plugin nhận lệnh `failOnVerify`, `failOnInitialize`, `failOnStart`, `failOnInvoke`, `failOnStop` để kiểm thử mọi cạnh; đếm số lần start/stop, giữ list các transitions và assert chính xác thứ tự. Trong test concurrency, dùng latch/barrier thay vì sleep tùy ý để tái lập race giữa request và stop.

### 12.2. Metrics và diagnostics

Những trường đáng ghi:

- Plugin ID, implementation/version, instance/generation, tên loader/module layer nếu có.
- State trước/sau, event, lý do chuyển, timestamp và correlation ID.
- Duration của verify, initialize, start, quiesce, stop.
- Số request inflight, timeouts, exceptions, lần retry và kết quả cleanup.
- Readiness/health độc lập với state lifecycle.
- Last failure cause/code và kết quả dọn tài nguyên ngay cả khi cuối cùng ở `STOPPED`.

Log cần tránh lộ password, token hoặc dữ liệu nhạy cảm trong config/exception. Nếu plugin từ bên thứ ba, host nên chuẩn hóa thông tin công bố thay vì cho plugin tùy ý quyết định thông điệp an toàn.

## 13. Lỗi thiết kế phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ dùng `loaded=true` | Không biết đang validate, initialize hay ACTIVE | Dùng enum state + transition policy |
| Gán ACTIVE ngay khi `ServiceLoader.findFirst()` trả provider | Dẫn tới gọi request trước khi start/readiness | Chỉ publish khi start thành công |
| `DISCOVERED → ACTIVE` mà bỏ verify/init | Mất kiểm soát config/dependency | Guard thứ tự bắt buộc |
| Không có trạng thái FAILED | Lỗi bị che dưới “plugin dừng” hoặc “không tìm thấy” | Giữ cause, stage, error code |
| Bắt mọi `Throwable` rồi fallback | Che JVM/linkage lỗi nghiêm trọng | Phân loại lỗi, xử lý có chủ đích |
| Start thất bại thì bỏ qua cleanup | Rò thread/connection/listener | Cleanup sau partial initialization |
| STOPPED xóa sạch lịch sử lỗi | Khó điều tra vì sao plugin không chạy | Giữ lastFailure/hadFailure |
| Stop nhiều lần từ nhiều thread | Double close, race, deadlock | Idempotent contract + once-only atomic guard |
| Stop đóng resource khi request cũ đang dùng | Request lỗi, mất dữ liệu | Quiesce/inflight leases, deadline |
| Retry cùng object không có quy ước | State/tài nguyên từ lần trước còn tồn tại | Tạo instance mới, backoff và generation |
| Đóng `URLClassLoader` rồi tưởng plugin đã dừng | Thread/callback/class có thể vẫn còn | Stop/cleanup/gỡ reference trước |
| Dựa vào thứ tự SPI để quản lý dependency | Plugin phụ thuộc start trước dependency | Resolve graph, topo start/reverse stop |
| Cho rằng class loader cô lập quyền an toàn | Plugin vẫn có quyền process | Process isolation/OS policy cho mã không tin cậy |

## 14. Checklist khi thiết kế plugin manager

- [ ] Phân biệt discovery result “không có provider” với lỗi cấu hình/nạp provider.
- [ ] Có trạng thái tối thiểu `DISCOVERED`, `VERIFIED`, `INITIALIZED`, `ACTIVE`, `STOPPING`, `STOPPED`, `FAILED`.
- [ ] Các cạnh chuyển có guards; không có bước nhảy tắt, không gọi request ngoài `ACTIVE`.
- [ ] Xác minh danh tính, API/version, dependency, cấu hình, capability và policy trước khi kích hoạt.
- [ ] Constructor nhẹ; initialize và start có ranh giới rõ, rollback được sau lỗi một phần.
- [ ] Registry chỉ publish instance **sau** start/readiness; unpublish trước cleanup.
- [ ] Cleanup có hợp đồng xử lý khi chưa initialize hoặc start thất bại; chống double cleanup.
- [ ] Tách lỗi request có thể phục hồi khỏi lỗi hệ thống bắt buộc `FAILED`.
- [ ] Xử lý quiescing và inflight requests an toàn khi multi-threaded.
- [ ] Khi FAILED, lưu phase, nguyên nhân, kết quả cleanup và lịch sử, kể cả sau STOPPED.
- [ ] Stop theo thứ tự dependency ngược; kiểm tra class loader/callback/thread leaks khi hot reload.
- [ ] Retry có policy, backoff và instance/generation mới; tránh resurrect object hỏng.
- [ ] Có test cho mỗi transition, illegal transition, partial failure, concurrency, timeout và restart.

**Kết luận:** Một plugin **được phát hiện** chưa phải plugin **được xác minh**; plugin **đã khởi tạo** chưa phải plugin **hoạt động**; plugin **đang lỗi** vẫn có thể cần đi qua **dừng** để dọn tài nguyên. Khi state machine có guards, history, ownership và cleanup rõ ràng, host mới có thể vận hành plugin an toàn, nhất là trong hệ thống có nhiều provider, dependency và hot reload.

**Tài liệu Java SE 17 chính thức:** [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html), [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [`URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html), [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).
