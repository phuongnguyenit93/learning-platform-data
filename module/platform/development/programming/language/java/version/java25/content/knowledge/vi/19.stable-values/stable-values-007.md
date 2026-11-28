# Giới hạn sử dụng trong thư viện và đánh giá thay đổi API khi nâng cấp JDK

## 1. Bối cảnh: Stable Values là API preview, không phải API ổn định

Stable Values được giới thiệu trong Java 25 qua **JEP 502 — Stable Values (Preview)**. Ý tưởng cốt lõi là cho phép một giá trị được khởi tạo trễ, chỉ thiết lập tối đa một lần, sau đó giữ nguyên nội dung để JVM có cơ hội tối ưu như với field `final`.

Tuy nhiên, tên gọi và API đã thay đổi sau JDK 25:

| Phiên bản | JEP và tên API | Trạng thái |
| --- | --- | --- |
| JDK 25 | JEP 502 — `java.lang.StableValue` | Preview lần đầu |
| JDK 26 | JEP 526 — `java.lang.LazyConstant` | Preview lần thứ hai; thay tên và thiết kế API |
| JDK 27 | JEP 531 — `java.lang.LazyConstant` | Preview lần thứ ba; tiếp tục tinh chỉnh API |

**Điểm cần nhớ ở thời điểm hiện tại:** `StableValue` là tên API của JDK 25. Từ JDK 26, API được thay bằng `LazyConstant`. Trong JDK 27, `LazyConstant` vẫn là preview, chưa trở thành API permanent. Vì vậy, bài này giải thích Stable Values trong bối cảnh Java 25, đồng thời chỉ rõ những thay đổi phải xử lý khi nâng JDK. Không xem mã `StableValue` là mã nguồn có thể mang nguyên vẹn sang JDK 26 hoặc 27.

Các ví dụ được chia rõ theo phiên bản:

- Mã `StableValue` chỉ dành cho JDK 25, phải bật preview.
- Mã `LazyConstant` dành cho JDK 26/27, cũng phải bật preview của đúng JDK.
- Khi viết thư viện dùng nhiều JDK, phải xác định rõ phiên bản compile và runtime; không thể giả định preview API tương thích nhị phân xuyên các release.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích giới hạn của `StableValue` trong thư viện và ứng dụng.
2. Phân biệt tính bất biến của holder với tính bất biến của object được giữ.
3. Chọn đúng trường hợp dùng stable value, stable supplier, stable function, stable list hoặc stable map.
4. Nhận diện rủi ro về memory retention, serialization, recursion, blocking và lỗi khởi tạo.
5. Thiết kế ranh giới API để preview type không lan ra public contract.
6. Đánh giá thay đổi từ `StableValue` sang `LazyConstant` qua JDK 26 và JDK 27.
7. Xử lý khác biệt về null, exception, API collection và preview flags khi nâng cấp.
8. Lập kế hoạch migration và kiểm thử thư viện trên từng JDK đích.

## 2. Stable Value giải quyết vấn đề nào?

### 2.1. Khởi tạo sớm bằng final field

Một field `final` thông thường được gán trong constructor hoặc static initializer:

~~~java
public final class ReportService {
    private final ExpensiveCatalog catalog = ExpensiveCatalog.load();

    public Report render(long id) {
        return catalog.find(id);
    }
}
~~~

Cách này dễ hiểu và có lợi cho tối ưu hóa, nhưng `ExpensiveCatalog.load()` luôn chạy khi tạo `ReportService`, kể cả khi instance không bao giờ gọi `render()`.

Với ứng dụng lớn, việc khởi tạo nhiều dependency sớm có thể làm tăng startup time, allocation và kết nối tài nguyên không cần thiết.

### 2.2. Lazy initialization truyền thống

Có thể dùng field mutable cùng synchronized accessor:

~~~java
public final class ReportService {
    private ExpensiveCatalog catalog;

    private synchronized ExpensiveCatalog catalog() {
        if (catalog == null) {
            catalog = ExpensiveCatalog.load();
        }
        return catalog;
    }
}
~~~

Cách này trì hoãn khởi tạo nhưng có các điểm cần cân nhắc:

- Field không còn là `final`.
- Mọi lần gọi accessor có thể phải đi qua synchronization.
- Nếu bỏ synchronization mà không có cơ chế an toàn, nhiều thread có thể tạo nhiều instance.
- Mã truy cập field phải luôn đi qua accessor.
- Double-checked locking cần volatile và quy tắc memory visibility chính xác.

### 2.3. Stable Value: khởi tạo trễ và chỉ thiết lập một lần

Trong JDK 25, `StableValue<T>` là holder có thể chưa có nội dung hoặc đã có nội dung. Khi được thiết lập thành công, nội dung không thể thay đổi.

~~~java
import java.lang.StableValue;

public final class ReportService {
    private final StableValue<ExpensiveCatalog> catalog =
        StableValue.of();

    private ExpensiveCatalog catalog() {
        return catalog.orElseSet(ExpensiveCatalog::load);
    }

    public Report render(long id) {
        return catalog().find(id);
    }
}
~~~

`orElseSet` tính giá trị khi holder chưa được thiết lập, rồi lưu giá trị để các lần truy cập sau dùng lại. Khi nhiều thread cùng gọi, chỉ một supplier được thực thi thành công; các thread cạnh tranh đợi kết quả khởi tạo.

Holder có thể là `final` dù nội dung bên trong được thiết lập sau. JVM có thể tận dụng tính ổn định đó cho tối ưu hóa, nhưng việc constant folding là quyền của JVM và không phải cam kết hiệu năng cho mọi chương trình.
## 3. Phạm vi và giới hạn của API JDK 25

### 3.1. Một holder chỉ lưu một nội dung

`StableValue.of()` tạo một holder chưa được thiết lập. `StableValue.of(value)` tạo holder đã có sẵn nội dung. Các thao tác chính:

| API JDK 25 | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| `StableValue.of()` | Tạo holder chưa có nội dung | Dùng khi cần khởi tạo trễ |
| `StableValue.of(value)` | Tạo holder đã có nội dung | Không còn bước lazy initialization |
| `trySet(value)` | Thử thiết lập nội dung | Trả `true` cho lần thiết lập thành công; các lần sau không thay đổi holder |
| `setOrThrow(value)` | Thiết lập hoặc ném lỗi | Ném `IllegalStateException` nếu đã có nội dung |
| `orElseSet(supplier)` | Lấy nội dung hoặc tính và thiết lập | Supplier thành công được gọi tối đa một lần trong các thread cạnh tranh |
| `orElseThrow()` | Lấy nội dung hoặc ném lỗi nếu chưa có | Dùng sau khi chắc chắn đã thiết lập |
| `orElse(other)` | Lấy nội dung hoặc giá trị thay thế | Không kích hoạt tính toán |
| `isSet()` | Kiểm tra đã thiết lập hay chưa | Chỉ kiểm tra trạng thái, không khởi tạo |

Không dùng `trySet` như một cách bảo đảm chỉ tạo một object. Nếu nhiều thread cùng tạo candidate trước khi gọi `trySet`, mỗi thread vẫn có thể tạo một object; chỉ một candidate thắng cuộc được lưu. Nếu muốn supplier chỉ chạy một lần khi thành công, dùng `orElseSet`.

Ví dụ không tối ưu khi khởi tạo tốn kém:

~~~java
StableValue<Logger> logger = StableValue.of();

Logger getLogger() {
    Logger candidate = Logger.create(); // Có thể tạo ở nhiều thread
    logger.trySet(candidate);
    return logger.orElseThrow();
}
~~~

Dùng supplier để tránh tạo thừa:

~~~java
StableValue<Logger> logger = StableValue.of();

Logger getLogger() {
    return logger.orElseSet(Logger::create);
}
~~~

### 3.2. Stable không đồng nghĩa deep immutable

Holder bảo đảm nội dung được gán tối đa một lần. Nó không tự biến object được giữ thành immutable.

~~~java
StableValue<List<String>> names = StableValue.of();
List<String> mutableNames = new ArrayList<>();

names.setOrThrow(mutableNames);

// Reference trong StableValue không đổi, nhưng object List vẫn mutable.
mutableNames.add("changed");
~~~

Ở ví dụ trên, holder vẫn trỏ đến cùng một List, nhưng nội dung List thay đổi. Vì vậy:

- Chỉ dùng stable value với object có trạng thái bất biến, hoặc object có quy tắc đồng bộ riêng.
- Nếu object được chia sẻ cho nhiều thread, thiết kế mutability và thread safety của object đó độc lập với holder.
- Không dùng stable value để che giấu một object mutable mà các caller có thể thay đổi tùy ý.
- Nếu cần snapshot bất biến, tạo defensive copy hoặc dùng kiểu dữ liệu bất biến trước khi lưu.

Tính ổn định của reference giúp JVM có cơ hội tối ưu đường đọc. Nó không phải cam kết rằng toàn bộ object graph sẽ được constant-fold hoặc không thay đổi.

### 3.3. Supplier, function và collection chỉ phù hợp với miền đầu vào xác định

JDK 25 cung cấp các factory method bậc cao:

| Factory | Cách hoạt động | Giới hạn miền dữ liệu |
| --- | --- | --- |
| `StableValue.supplier(supplier)` | Tính một kết quả khi gọi `get()` lần đầu, rồi cache | Một kết quả |
| `StableValue.intFunction(size, function)` | Cache kết quả cho từng input int | Chỉ input trong `[0, size)` |
| `StableValue.function(inputs, function)` | Cache kết quả cho từng input | Tập `inputs` cố định từ lúc tạo |
| `StableValue.list(size, mapper)` | Tính từng phần tử khi gọi `get(index)` | Kích thước list cố định |
| `StableValue.map(keys, mapper)` | Tính value khi truy cập key lần đầu | Tập key cố định từ lúc tạo |

Ví dụ list có 256 bảng giải mã được tạo theo nhu cầu:

~~~java
private static final List<Decoder> DECODERS =
    StableValue.list(256, DecoderRegistry::create);

static Decoder decoderFor(int opcode) {
    return DECODERS.get(opcode);
}
~~~

Ví dụ map có tập tenant đã biết trước:

~~~java
private static final Set<TenantId> TENANTS = loadKnownTenants();

private static final Map<TenantId, TenantRules> RULES =
    StableValue.map(TENANTS, TenantRules::load);
~~~

Các cấu trúc này không phải cache tổng quát:

- List và map là unmodifiable.
- List có kích thước cố định; index ngoài phạm vi không hợp lệ.
- Map chỉ chấp nhận những key đã khai báo; key ngoài tập sẽ gây lỗi.
- Function chỉ chấp nhận các input nằm trong tập cho phép.
- Không có cơ chế eviction, TTL, refresh hoặc xóa một entry đã tính.
- Mapper/supplier được gọi tối đa một lần thành công cho mỗi holder/index/key.

Nếu dữ liệu có key phát sinh liên tục, cần invalidation, eviction hoặc refresh, hãy dùng cache chuyên dụng như Caffeine hoặc cấu trúc collection có lifecycle phù hợp. Stable collection phù hợp hơn với bảng tra cứu hữu hạn, không đổi trong vòng đời của ứng dụng.

### 3.4. Không có stable Set trong JDK 25

JDK 25 cung cấp stable list và stable map, nhưng không có factory stable set tương ứng. Nếu muốn biểu diễn một tập giá trị tính trễ trong JDK 25, có thể dùng map từ candidate sang kết quả boolean hoặc một abstraction nội bộ. Đừng tự đặt tên một factory không tồn tại trong API.

Ở JDK 27, `Set.ofLazy(...)` được bổ sung trong preview của Lazy Constants để tính membership theo candidate. Đây là một thay đổi API ở release sau, không thể gọi từ code JDK 25.

### 3.5. Mảng chỉ ổn định ở cấp reference

Nếu holder giữ một array, JVM chỉ có thể xem reference tới array là ổn định. Các phần tử của array không tự trở thành stable values.

~~~java
StableValue<Decoder[]> decoders = StableValue.of();
~~~

Việc reference array không đổi không ngăn code sửa `decoders.orElseThrow()[index]`. Nếu cần tính từng phần tử theo nhu cầu và giữ ổn định từng phần tử, dùng stable list hoặc các stable value lồng nhau thay vì một array mutable.

### 3.6. Đệ quy và dependency cycle

Một stable function hoặc stable collection không hỗ trợ mapper gọi lại chính nó cho cùng input/index/key khi giá trị đó đang được tính. Trường hợp này ném `IllegalStateException`.

Ví dụ dependency cycle:

~~~java
static final Supplier<A> A_VALUE =
    StableValue.supplier(() -> new A(B_VALUE.get()));

static final Supplier<B> B_VALUE =
    StableValue.supplier(() -> new B(A_VALUE.get()));
~~~

Khi khởi tạo A cần B và khởi tạo B lại cần A, quá trình không có thứ tự hoàn tất hợp lệ. Thiết kế dependency graph theo hướng không có vòng lặp; nếu hai thành phần cần tham chiếu lẫn nhau, dùng một bước wiring/initialization rõ ràng thay vì đệ quy supplier.

## 4. Giới hạn vận hành và thiết kế khi dùng StableValue

### 4.1. Supplier có thể thất bại và được thử lại

Trong JDK 25, nếu supplier của `orElseSet` ném unchecked exception, exception được chuyển tới caller và nội dung không được thiết lập. Lần gọi sau có thể thử tính toán lại.

Đây là hành vi khác với một cache lỗi vĩnh viễn. Ví dụ:

~~~java
private static final StableValue<Schema> SCHEMA =
    StableValue.of();

static Schema schema() {
    return SCHEMA.orElseSet(() -> {
        return Schema.loadFromDisk();
    });
}
~~~

Nếu lần tải đầu tiên thất bại do file tạm thời chưa sẵn sàng, lần gọi sau có thể thử lại. Nhưng điều đó cũng có nghĩa supplier có thể chạy nhiều lần nếu mỗi lần đều thất bại.

Vì vậy:

- Supplier nên có side effect được kiểm soát.
- Không thực hiện thao tác không idempotent mà không có cơ chế chống lặp.
- Phân biệt lỗi tạm thời có thể retry với lỗi cấu hình không thể khắc phục.
- Nếu cần retry có backoff, giới hạn số lần hoặc circuit breaker, triển khai chính sách đó bên ngoài stable value.

Đừng nhầm “tối đa một lần thành công” với “supplier chỉ được gọi đúng một lần trong mọi tình huống”.

### 4.2. Nhiều thread cạnh tranh và tác vụ khởi tạo bị treo

Các thao tác thiết lập và đọc thành công có quan hệ happens-before. Thread đọc thành công sẽ nhìn thấy nội dung đã được thiết lập an toàn.

Khi nhiều thread cùng gọi `orElseSet`:

- Một supplier được chọn để tính giá trị.
- Các thread khác chờ cho tới khi có kết quả hoặc supplier thất bại.
- Khi thành công, các thread sau đọc cùng nội dung.
- Nếu supplier thất bại, holder vẫn unset và lần gọi sau có thể thử lại.

Stable value không cung cấp timeout hoặc cancellation cho supplier. Nếu supplier bị block vô hạn do network, database hoặc lock, các caller khác chờ cùng holder cũng có thể bị block.

Không dùng stable value để thực hiện một lần gọi remote không có timeout. Hãy cấu hình timeout ở HTTP/RPC/JDBC client; nếu việc khởi tạo cần retry hoặc refresh theo thời gian, dùng một thành phần quản lý lifecycle rõ ràng hơn.

### 4.3. Nội dung được giữ mạnh và không có thao tác clear

Stable value không có API unset, remove hoặc evict. Khi holder đã được thiết lập, nó giữ strong reference tới nội dung. Nếu holder còn reachable, nội dung cũng còn reachable.

Ví dụ một thư viện giữ cache lớn trong static field:

~~~java
private static final StableValue<ModelIndex> INDEX =
    StableValue.of();

static ModelIndex index() {
    return INDEX.orElseSet(ModelIndex::loadAll);
}
~~~

Nếu `ModelIndex` chứa hàng triệu entry, dữ liệu đó sẽ được giữ trong suốt vòng đời của holder và classloader chứa holder. Đây có thể là memory retention ngoài dự kiến.

Không dùng StableValue cho:

- Cache cần giới hạn dung lượng hoặc eviction.
- Dữ liệu có TTL hoặc cần refresh.
- Cấu hình thay đổi trong runtime.
- Session/request/user state có vòng đời ngắn.
- Nội dung nhạy cảm cần xóa khỏi bộ nhớ theo chính sách.
- Resource cần close/release hoặc được thay thế sau khi kết nối mất.

Dùng stable value cho dữ liệu có vòng đời gần bằng vòng đời holder, thường là dependency hoặc bảng tra cứu bất biến của ứng dụng.

### 4.4. Không Serializable

`StableValue`, stable suppliers, stable functions và stable collections trong JDK 25 không triển khai `Serializable`.

Không đưa trực tiếp các đối tượng này vào:

- Java object serialization.
- Session replication dựa trên serialization.
- Distributed cache yêu cầu serialize object.
- DTO hoặc public data model cần truyền qua process boundary.
- Cơ chế lưu trạng thái ứng dụng xuống file.

Nếu cần truyền nội dung, serialize giá trị đã được tính bằng một DTO/representation riêng. Không serialize holder để mong khôi phục trạng thái khởi tạo lazy ở process khác.

### 4.5. Không dùng StableValue làm monitor

Triển khai `StableValue` được phép đồng bộ trên chính instance của nó. Vì vậy, code ứng dụng không nên dùng holder làm monitor:

~~~java
synchronized (stable) {
    // Không nên khóa trên StableValue
}
~~~

Việc khóa trực tiếp hoặc gián tiếp trên holder có thể xung đột với synchronization nội bộ và gây deadlock. Dùng một private lock object riêng nếu cần phối hợp thêm trạng thái bên ngoài.

### 4.6. Không mặc định constant folding sẽ xảy ra

JVM có thể loại bỏ các lần đọc stable value đã thiết lập nếu nó chứng minh được reference tới holder là constant. Một trường hợp điển hình là holder được lưu trong field `static final`.

~~~java
private static final StableValue<RoutingTable> ROUTING =
    StableValue.of();

static RoutingTable routingTable() {
    return ROUTING.orElseSet(RoutingTable::load);
}
~~~

Cấu trúc này tạo điều kiện cho JVM tối ưu, nhưng không bảo đảm mọi lần gọi đều được constant-fold. Tối ưu phụ thuộc JIT, profile, code path và phiên bản JVM.

Không chọn API chỉ vì kỳ vọng JIT sẽ loại bỏ toàn bộ overhead. Hãy benchmark trên JDK đích với workload đại diện, đo cả startup, allocation, throughput và latency.

## 5. Ranh giới thư viện: không để preview API lan ra public contract

### 5.1. Preview API ảnh hưởng cả compile lẫn runtime

`StableValue` của JDK 25 là preview API. Mã dùng nó phải:

- Compile bằng JDK 25 với `--enable-preview`.
- Chạy bằng JDK 25 với `--enable-preview`.
- Không mặc định chạy được bằng JDK 26/27 chỉ vì class file đã được build thành công.
- Chấp nhận rằng tên, method và semantics có thể thay đổi hoặc preview bị loại bỏ ở release sau.

Ví dụ compile và chạy một ứng dụng JDK 25:

~~~bash
javac --release 25 --enable-preview -d out src/com/acme/LibraryDemo.java
java --enable-preview -cp out com.acme.LibraryDemo
~~~

Nếu một thư viện dùng preview API trong implementation, ứng dụng tích hợp vẫn phải đáp ứng yêu cầu runtime của preview class. Nếu public signature của thư viện chứa `StableValue`, `Supplier` trả về `StableValue`, hoặc một kiểu preview khác, người dùng thư viện còn phải compile code của họ với đúng preview API.

### 5.2. Giữ preview type ở implementation boundary

Không nên thiết kế public API như sau:

~~~java
public interface ConfigurationProvider {
    StableValue<Configuration> configuration();
}
~~~

Người dùng thư viện bị phụ thuộc trực tiếp vào tên và lifecycle của preview type. Khi JDK 26 đổi sang `LazyConstant`, signature trên không còn biên dịch.

Nếu đang thử nghiệm preview API trong thư viện nội bộ, hãy che giấu nó sau kiểu Java thông thường:

~~~java
public interface ConfigurationProvider {
    Configuration configuration();
}
~~~

Implementation của thư viện có thể dùng cơ chế lazy initialization riêng bên trong, còn caller chỉ thấy kiểu ổn định của thư viện. Cách đóng gói này giới hạn phạm vi thay đổi source code. Tuy nhiên, nếu implementation vẫn tham chiếu preview API thì runtime vẫn phải bật preview của đúng JDK; che giấu type không loại bỏ yêu cầu đó.

Với thư viện phân phối rộng, đặc biệt thư viện nền tảng hoặc thư viện được dùng bởi nhiều ứng dụng, chỉ dùng preview API khi có lý do rõ ràng và chấp nhận được ma trận runtime tương ứng. Nếu thư viện phải chạy trên nhiều JDK release bằng cùng một artifact, cơ chế Java ổn định như initialization-on-demand holder, field `final`, hoặc một implementation memoization được kiểm thử có thể phù hợp hơn.

### 5.3. Không phát hành một binary rồi giả định StableValue tồn tại ở mọi JDK

`java.lang.StableValue` có trong JDK 25, nhưng JDK 26 đã thay bằng `java.lang.LazyConstant`. Đây không phải một rename có alias tương thích: binary hoặc source tham chiếu `StableValue` không thể dùng nguyên trạng trên JDK 26.

Khi thư viện hỗ trợ nhiều JDK, chọn chiến lược rõ ràng:

1. **Baseline ổn định:** dùng Java API không preview trong artifact chung.
2. **Artifact theo JDK:** phát hành biến thể được compile/test riêng cho từng JDK đích nếu thực sự cần API preview.
3. **Module triển khai tùy chọn:** cô lập phần dùng preview vào module không bắt buộc cho người dùng không bật preview.
4. **Nâng cấp có kiểm soát:** cập nhật source, compiler flags, runtime flags, test matrix và tài liệu phát hành cùng lúc.

Không dựa vào việc chỉ đổi tên import để hoàn thành migration. Semantics về null, lỗi và collection cũng thay đổi giữa các phiên bản.

### 5.4. Public contract nên mô tả giá trị, không mô tả holder

Thay vì để caller quyết định khi nào holder được thiết lập, cung cấp phương thức nghiệp vụ:

~~~java
public final class GeoService {
    public GeoIndex index() {
        return indexProvider.get();
    }
}
~~~

Caller biết nó nhận `GeoIndex`; caller không cần biết implementation đang dùng `StableValue`, `LazyConstant`, holder class hay một cơ chế khác.

Điều này giúp thư viện thay implementation theo JDK mà không làm thay đổi API người dùng. Nếu cần kiểm soát refresh, failure, timeout hoặc eviction, hãy biểu diễn các khả năng đó trong contract riêng thay vì ép chúng vào một holder chỉ-set-once.

## 6. Đánh giá thay đổi API từ JDK 25 tới JDK 27

### 6.1. Bảng migration

| Khía cạnh | JDK 25 — JEP 502 | JDK 26 — JEP 526 | JDK 27 — JEP 531 |
| --- | --- | --- | --- |
| Tên type | `StableValue<T>` | `LazyConstant<T>` | `LazyConstant<T>` |
| Factory đơn | `StableValue.of()` / `of(value)` | `LazyConstant.of(supplier)` | `LazyConstant.of(supplier)` |
| Đọc giá trị | `orElseThrow()` / `orElse()` / `orElseSet()` | `get()` | `get()` |
| Kiểm tra đã khởi tạo | `isSet()` | `isInitialized()` | Không còn method này |
| Ghi giá trị trực tiếp | `trySet()` / `setOrThrow()` | Không có API ghi thủ công tương ứng | Không có |
| Supplier cache | `StableValue.supplier(...)` | Dùng `LazyConstant.of(...)` | Dùng `LazyConstant.of(...)` |
| Lazy list/map | `StableValue.list(...)` / `map(...)` | `List.ofLazy(...)` / `Map.ofLazy(...)` | `List.ofLazy(...)` / `Map.ofLazy(...)` |
| Lazy set | Không có factory tương ứng | Chưa có | `Set.ofLazy(...)` |
| Preview | Có | Có | Có |

JDK 26 không chỉ đổi tên type. Nó chuyển mô hình từ holder có thao tác thiết lập/đọc trạng thái sang một lazy constant được tạo cùng computing function và đọc bằng `get()`.

JDK 27 tiếp tục loại bỏ `orElse()` và `isInitialized()` khỏi `LazyConstant`, đồng thời thêm lazy set. Không viết code mới trên JDK 27 dựa vào hai method đã bị loại khỏi API.

### 6.2. Ví dụ tương đương theo từng JDK

**JDK 25 — StableValue:**

~~~java
private static final StableValue<Settings> SETTINGS =
    StableValue.of();

static Settings settings() {
    return SETTINGS.orElseSet(Settings::load);
}
~~~

**JDK 26 và JDK 27 — LazyConstant:**

~~~java
private static final LazyConstant<Settings> SETTINGS =
    LazyConstant.of(Settings::load);

static Settings settings() {
    return SETTINGS.get();
}
~~~

Ví dụ JDK 26/27 phải compile và chạy bằng preview flags của đúng release. JDK 25 không có type `LazyConstant`; JDK 26/27 không còn type `StableValue`.

### 6.3. API trạng thái bị loại bỏ ở JDK 27

Trong JDK 26, có thể dùng `isInitialized()` để kiểm tra trạng thái và `orElse(fallback)` để đọc nội dung nếu đã khởi tạo mà không kích hoạt tính toán.

Hai method này bị bỏ trong JDK 27. Vì thế, nếu logic ứng dụng đang phụ thuộc vào việc quan sát trạng thái lazy mà không kích hoạt initialization, cần thiết kế lại:

- Nếu chỉ cần lấy giá trị, gọi `get()` và chấp nhận việc khởi tạo.
- Nếu cần biết trạng thái vì mục đích nghiệp vụ, quản lý trạng thái đó bằng một abstraction riêng của ứng dụng.
- Không dùng `toString()` như API kiểm tra trạng thái; nó chỉ phục vụ debug và format là implementation-dependent.
- Không tái tạo `orElse` bằng cách giữ một cờ mutable không đồng bộ với trạng thái khởi tạo.

Đặc biệt, không nên để public contract của thư viện phụ thuộc vào `isInitialized()` hoặc `orElse()` của preview JDK 26, vì các method này không còn trong JDK 27.

## 7. Những khác biệt ngữ nghĩa quan trọng khi nâng JDK

### 7.1. Null: JDK 25 cho phép, LazyConstant không cho phép

Trong JDK 25, nội dung của `StableValue` có thể là `null`. Có thể dùng `isSet()` để phân biệt holder chưa được thiết lập với holder đã được thiết lập thành `null`.

Ví dụ:

~~~java
StableValue<String> value = StableValue.of();
value.setOrThrow(null);

if (value.isSet()) {
    // Holder đã được thiết lập, dù nội dung là null.
}
~~~

Từ JDK 26, `LazyConstant` không thể chứa `null`. Nếu computing function trả về `null`, `get()` ném `NullPointerException`. JDK 27 biểu diễn trường hợp này bằng trạng thái lỗi và `NoSuchElementException` có cause là `NullPointerException`.

Nếu giá trị nghiệp vụ có thể vắng mặt, dùng `Optional` làm nội dung:

~~~java
private static final LazyConstant<Optional<Settings>> SETTINGS =
    LazyConstant.of(() -> Optional.ofNullable(Settings.loadOrNull()));

static Optional<Settings> settings() {
    return SETTINGS.get();
}
~~~

Đây là thay đổi cần kiểm tra khi chuyển dữ liệu hoặc logic từ `StableValue<T>` sang `LazyConstant<T>`. Không giả định rằng một supplier có thể trả null như trước.

### 7.2. Supplier thất bại: retry trong JDK 25/26, trạng thái lỗi trong JDK 27

Khác biệt quan trọng nhất nằm ở cách xử lý unchecked exception từ supplier:

| Trường hợp | JDK 25 — `StableValue` | JDK 26 — `LazyConstant` | JDK 27 — `LazyConstant` |
| --- | --- | --- | --- |
| Supplier ném unchecked exception | Exception được chuyển cho caller; holder vẫn unset | Exception được chuyển cho caller; constant vẫn chưa initialized | Constant chuyển sang error state; `get()` ném `NoSuchElementException` có cause |
| Lần gọi tiếp theo | Có thể thử supplier lại | Có thể thử computing function lại | Không chạy computing function lần nữa; `get()` tiếp tục ném `NoSuchElementException` |
| Supplier trả null | Có thể lưu null | `NullPointerException`; không có nội dung null | `NoSuchElementException` có cause là `NullPointerException`; không có nội dung null |
| Đệ quy vào chính holder | `IllegalStateException` | `IllegalStateException` | `NoSuchElementException` có cause là `IllegalStateException` |

JDK 27 thay đổi retry semantics: một lỗi khởi tạo được ghi lại thành error state của lazy constant. Những lần gọi sau không tự thử lại.

Điều này có ảnh hưởng trực tiếp đến thư viện:

- Nếu lỗi có thể tạm thời, đừng giả định gọi `get()` lần hai sẽ thử lại.
- Nếu cần retry, thực hiện retry có giới hạn bên trong computing function trước khi nó kết thúc bằng exception.
- Nếu muốn thử lại sau khi constant đã chuyển sang error state, cần tạo một instance mới theo lifecycle có chủ đích; không có API reset trên `LazyConstant`.
- Đưa metrics/logging vào computing function để ghi nhận nguyên nhân lỗi ban đầu; các lần `get()` sau không chạy lại supplier để tái hiện lỗi gốc.

### 7.3. Collection factories chuyển từ StableValue sang Java Collections

JDK 25 có:

~~~java
List<Decoder> decoders =
    StableValue.list(256, DecoderRegistry::create);

Map<TenantId, TenantRules> rules =
    StableValue.map(knownTenants, TenantRules::load);
~~~

Từ JDK 26, lazy list/map được đưa vào Java Collections Framework:

~~~java
List<Decoder> decoders =
    List.ofLazy(256, DecoderRegistry::create);

Map<TenantId, TenantRules> rules =
    Map.ofLazy(knownTenants, TenantRules::load);
~~~

JDK 27 bổ sung lazy set:

~~~java
Set<Feature> enabledFeatures =
    Set.ofLazy(candidateFeatures, FeatureRegistry::isEnabled);
~~~

Các collection lazy là unmodifiable và có miền phần tử/key xác định. Chúng không thay thế `ConcurrentHashMap`, cache có eviction hoặc cấu trúc dữ liệu cập nhật động.

Cần kiểm tra lại null behavior: collection factory của Java Collections tuân theo các giới hạn null của collection factory tương ứng. Đừng giả định mapper có thể trả null chỉ vì mapper của stable collection JDK 25 đã cho phép.

### 7.4. Không có tương đương trực tiếp cho mọi thao tác ghi của StableValue

JDK 25 cho phép tạo holder unset, rồi chủ động gọi `trySet` hoặc `setOrThrow` để thiết lập từ một luồng khác. `LazyConstant` được thiết kế theo cách khác: factory nhận computing function ngay lúc tạo, và lần `get()` đầu tiên thực hiện khởi tạo.

Nếu thư viện dùng `trySet` để nhận giá trị từ callback bên ngoài, migration không chỉ đổi tên method. Hãy xem lại ownership của dữ liệu:

- Nếu giá trị đã có sẵn, dùng field `final` hoặc factory tạo object đã hoàn tất.
- Nếu giá trị cần tính trễ từ supplier, dùng `LazyConstant.of`.
- Nếu giá trị đến bất đồng bộ từ callback/event, giữ một abstraction concurrency phù hợp với lifecycle đó; không ép nó vào lazy constant chỉ đọc.
- Nếu cần nhiều lần cập nhật, dùng cấu trúc mutable/thread-safe có contract rõ ràng.

## 8. Giới hạn của LazyConstant hiện hành trong JDK 27

### 8.1. Khởi tạo chạy trên thread gọi get()

Trong JDK 27, `LazyConstant.get()` gọi computing function trên thread đầu tiên truy cập constant khi nó chưa được khởi tạo. Các thread khác cạnh tranh cùng constant phải chờ cho tới khi khởi tạo hoàn tất hoặc thất bại.

Điều này có hai hệ quả:

- Lần gọi `get()` đầu tiên có thể chịu toàn bộ latency của việc tạo object.
- Nếu computing function bị block vô hạn, các thread khác gọi cùng constant cũng có thể bị block vô hạn.

Không đặt một truy vấn database không giới hạn thời gian, HTTP call hoặc thao tác chờ lock vào computing function. Nếu cần lazy initialization của dữ liệu remote, cấu hình timeout và chính sách retry rõ ràng, hoặc dùng một component quản lý asynchronous lifecycle riêng.

### 8.2. Interrupt không hủy việc khởi tạo

JDK 27 quy định interrupt của thread tính toán không hủy `LazyConstant.get()`. `get()` không xóa interrupt status và không ném `InterruptedException` chỉ vì thread bị interrupt.

Vì vậy, lazy constant không phải cơ chế quản lý task có cancellation. Nếu tác vụ khởi tạo cần timeout, cancellation hoặc shutdown hook, quản lý các hành vi đó ở service/lifecycle layer trước khi công bố giá trị bất biến.

### 8.3. Error state giữ nguyên trên cùng instance

Khi computing function của JDK 27 ném unchecked exception, lazy constant chuyển sang error state. Lần gọi đầu nhận `NoSuchElementException` có cause là exception ban đầu; các lần sau tiếp tục nhận `NoSuchElementException` và computing function không chạy lại.

Không lưu một thao tác có lỗi tạm thời vào static lazy constant nếu ứng dụng cần retry sau đó. Một lazy constant phù hợp với giá trị chỉ cần xác định một lần; dữ liệu có thể lỗi tạm thời và cần phục hồi phải có cơ chế lifecycle khác.

### 8.4. LazyConstant không phải cache có eviction hoặc reload

`LazyConstant` giữ nội dung sau khi khởi tạo và strongly references nội dung đó. Không có API xóa nội dung, reset trạng thái, refresh hoặc eviction.

Không dùng nó thay thế:

- Cache dữ liệu người dùng có TTL.
- Cache truy vấn có key động và giới hạn dung lượng.
- Kết nối cần đóng/mở lại.
- Cấu hình có thể reload khi vận hành.
- Resource phụ thuộc tenant hoặc request.
- Nội dung cần xóa khi người dùng đăng xuất hoặc khi quyền truy cập thay đổi.

Nếu object được giữ có resource như socket, thread, file handle hoặc native memory, cần quản lý close/dispose ở một lifecycle component khác. Lazy constant không tự giải phóng nội dung khi nhu cầu nghiệp vụ kết thúc.

### 8.5. Lazy constant không làm object trở nên immutable hoặc Serializable

`LazyConstant` không thay đổi trạng thái nội bộ của object được giữ. Ví dụ, nó có thể giữ một `ArrayList` mutable; reference được khởi tạo một lần nhưng list vẫn có thể thay đổi.

`LazyConstant` cũng không triển khai `Serializable`. Nếu cần serialize, chỉ serialize nội dung sau khi đã chuyển nó sang DTO hoặc representation được hỗ trợ.

Đối với array, constant reference không làm từng phần tử trở thành constant. Dùng `List.ofLazy` hoặc các lazy value lồng nhau khi cần tính từng phần tử theo nhu cầu.

### 8.6. Không đồng bộ trực tiếp trên LazyConstant

Triển khai có thể đồng bộ trên chính instance `LazyConstant`. Tránh dùng nó làm monitor:

~~~java
synchronized (SETTINGS) {
    // Không dùng LazyConstant làm lock của ứng dụng.
}
~~~

Dùng private lock object riêng nếu có một giao thức đồng bộ khác. Đồng thời tránh dependency cycle trong static initialization; chu trình khởi tạo class và lazy constant có thể dẫn tới lỗi initialization.

### 8.7. Điều kiện để JVM tối ưu như constant

JVM có thể constant-fold nội dung của lazy constant đã khởi tạo khi reference tới constant nằm trong đường truy cập mà JVM có thể chứng minh ổn định, chẳng hạn:

- Một field `static final` trỏ trực tiếp tới lazy constant.
- Một chuỗi field đáng tin cậy từ `static final` tới lazy constant, như record field hoặc final instance field trong hidden class.

Đây là cơ hội tối ưu của JVM, không phải cam kết rằng mọi accessor sẽ bị inline hoặc mọi lần đọc sẽ biến mất. Đo bằng JMH hoặc benchmark ứng dụng trên đúng JDK và đúng workload trước khi quyết định dựa vào lợi ích hiệu năng.

## 9. Quy trình đánh giá migration cho thư viện

### 9.1. Lập inventory trước khi đổi code

Tìm mọi nơi thư viện dùng API JDK 25:

- `StableValue.of`, `trySet`, `setOrThrow`, `orElseSet`.
- `StableValue.supplier`.
- `StableValue.function` và `intFunction`.
- `StableValue.list` và `map`.
- Public method/constructor/field có type `StableValue`.
- Serialization, reflection hoặc framework binding có thể nhìn thấy holder.

Phân loại theo mục đích:

| Mục đích hiện tại | Hướng migration |
| --- | --- |
| Một giá trị immutable được tạo trễ | `LazyConstant.of(supplier)` và `get()` |
| Supplier cache một kết quả | `LazyConstant<T>` triển khai `Supplier<T>` |
| Bảng tra cứu list có index cố định | `List.ofLazy(size, mapper)` |
| Bảng tra cứu map có tập key cố định | `Map.ofLazy(keys, mapper)` |
| Tính membership từ tập candidate hữu hạn | `Set.ofLazy(candidates, predicate)` trên JDK 27 |
| Nhận giá trị từ callback bên ngoài bằng `trySet` | Thiết kế lại lifecycle; không có setter tương đương trên `LazyConstant` |
| Cache động, có eviction/refresh | Dùng cache/lifecycle component riêng |

### 9.2. Rà soát semantics, không chỉ sửa import

Trước khi thay API, trả lời các câu hỏi:

1. Supplier có thể trả `null` không? Nếu có, chuyển sang `Optional` hoặc kiểu kết quả tường minh.
2. Supplier có thể thất bại tạm thời không? JDK 27 giữ error state; cần quyết định retry trước khi dùng lazy constant.
3. Giá trị có cần refresh hoặc eviction không? Nếu có, không dùng lazy constant.
4. Có caller nào phụ thuộc `isSet`, `isInitialized` hoặc `orElse` không?
5. Có dùng `trySet` để nhận giá trị từ bên ngoài không?
6. List/map có input động hoặc key không biết trước không?
7. Có code serialize holder thay vì serialize nội dung không?
8. Có dependency cycle giữa các lazy constants hoặc static initializer không?
9. Computing function có thể block vô hạn hoặc giữ resource không?
10. Public API có để lộ preview type không?

### 9.3. Ma trận compile và runtime

| Mục tiêu | Compile | Runtime |
| --- | --- | --- |
| JDK 25 với StableValue | `javac --release 25 --enable-preview` | `java --enable-preview` trên JDK 25 |
| JDK 26 với LazyConstant | `javac --release 26 --enable-preview` | `java --enable-preview` trên JDK 26 |
| JDK 27 với LazyConstant | `javac --release 27 --enable-preview` | `java --enable-preview` trên JDK 27 |

Không compile bằng JDK 25 rồi dùng cùng một binary preview cho JDK 26/27. Preview API gắn với release cụ thể. CI nên có job riêng cho từng JDK mà thư viện tuyên bố hỗ trợ.

### 9.4. Kiểm thử bắt buộc trước khi phát hành

- **Concurrency:** nhiều thread đồng thời truy cập cùng holder; xác minh supplier thành công chỉ chạy một lần.
- **Failure:** supplier ném exception ở lần đầu; xác minh retry semantics đúng với JDK đích.
- **Null:** supplier trả null; xác minh contract của JDK đích và cách biểu diễn optional value.
- **Recursion:** supplier tự gọi lại cùng lazy value; xác minh lỗi được xử lý đúng.
- **Dependency graph:** thử các dependency chain và phát hiện circular initialization.
- **Memory:** kiểm tra object lớn có bị giữ lâu hơn dự kiến không.
- **Serialization:** bảo đảm chỉ serialize dữ liệu nghiệp vụ, không serialize holder.
- **Public API:** kiểm tra signature đã loại preview type nếu thư viện cần contract ổn định.
- **Performance:** đo startup, lần truy cập đầu tiên, lần truy cập sau khởi tạo và contention.
- **Runtime flags:** xác minh đúng JDK và preview flag ở môi trường triển khai.

### 9.5. Quyết định có nên dùng hay không

| Điều kiện | Khuyến nghị |
| --- | --- |
| Giá trị immutable, chỉ cần khởi tạo một lần | Có thể dùng lazy constant |
| Startup bị ảnh hưởng bởi dependency chưa cần dùng | Cân nhắc lazy initialization |
| Giá trị có thể thay đổi/reload | Không dùng |
| Supplier cần retry sau lỗi trên JDK 27 | Thiết kế retry bên ngoài hoặc dùng abstraction khác |
| Supplier có I/O blocking không timeout | Không dùng trực tiếp |
| Cần eviction, TTL hoặc key động | Dùng cache chuyên dụng |
| Thư viện cần hỗ trợ nhiều JDK bằng cùng API binary | Tránh public preview type; cân nhắc không dùng preview API nội bộ |
| Hiệu năng chưa được đo | Chưa kết luận có lợi; benchmark trước |

## 10. Bài thực hành: nâng một thư viện từ JDK 25 lên JDK 27

**Tình huống:** thư viện cấu hình dùng `StableValue` để lazy-load settings, cache decoder theo opcode và lưu tenant rules theo tập key biết trước. Thư viện đang nâng runtime từ JDK 25 lên JDK 27.

### Phần A — Kiểm tra API cũ

1. Tìm tất cả reference tới `StableValue`.
2. Ghi lại nơi dùng `orElseSet`, `trySet` và `isSet`.
3. Kiểm tra supplier có thể trả null hoặc ném exception không.
4. Kiểm tra list/map có input cố định không.
5. Xác định có public signature nào lộ `StableValue` không.

**Đạt** khi có danh sách đầy đủ usage và contract hiện tại của từng holder.

### Phần B — Chuyển sang API JDK 27

1. Thay `StableValue<Settings>` bằng `LazyConstant<Settings>`.
2. Thay `orElseSet` bằng `LazyConstant.of` và `get()`.
3. Thay stable list bằng `List.ofLazy`.
4. Thay stable map bằng `Map.ofLazy`.
5. Nếu cần lazy membership, đánh giá `Set.ofLazy`.
6. Xóa các tham chiếu tới `isInitialized` và `orElse` nếu source từng qua JDK 26.
7. Thêm preview flags đúng JDK 27.

**Đạt** khi source compile với JDK 27 và không còn reference tới `StableValue` hoặc các method preview đã bị loại bỏ.

### Phần C — Kiểm thử failure và null

1. Cho settings loader ném exception lần đầu.
2. Xác minh lazy constant JDK 27 chuyển sang error state.
3. Gọi `get()` lần tiếp theo và xác minh computing function không chạy lại.
4. Cho supplier trả null và xác minh lỗi theo API JDK 27.
5. Nếu nghiệp vụ cần retry, chuyển retry vào computing function hoặc thay abstraction.
6. Nếu nghiệp vụ có giá trị vắng mặt, dùng `Optional`.

**Đạt** khi test phản ánh semantics của JDK 27 thay vì giả định retry như JDK 25/26.

### Phần D — Đánh giá thư viện và hiệu năng

1. Kiểm tra public API không để lộ preview type nếu không cần thiết.
2. Chạy test đa luồng cho decoder và tenant rules.
3. Kiểm tra memory retention của bảng tra cứu.
4. Đo startup và latency lần gọi đầu.
5. Đo latency sau khi lazy constant đã khởi tạo.
6. So sánh với baseline dùng holder class hoặc field final.
7. Ghi rõ JDK build, preview flags và workload.

**Đạt** khi migration có bằng chứng compile/runtime, test semantics và benchmark trên đúng môi trường.

## 11. Checklist sử dụng trong thư viện

### Thiết kế API

- [ ] Preview type không xuất hiện trong public signature nếu cần contract ổn định.
- [ ] Giá trị được giữ có lifecycle gần bằng lifecycle holder.
- [ ] Nội dung immutable hoặc có cơ chế thread safety riêng.
- [ ] Supplier không thực hiện side effect không idempotent.
- [ ] Dependency graph không có vòng lặp.
- [ ] Không dùng holder làm monitor.

### Vận hành

- [ ] Không cần eviction, TTL, refresh hoặc clear.
- [ ] Supplier không block vô hạn.
- [ ] Có timeout cho I/O nếu supplier cần truy cập dịch vụ ngoài.
- [ ] Có xử lý failure semantics theo đúng JDK.
- [ ] Không phụ thuộc serialization của holder.
- [ ] Đã đo memory retention và hiệu năng.

### Nâng cấp JDK

- [ ] Đã thay `StableValue` bằng API phù hợp của release đích.
- [ ] Đã rà soát `orElse` và `isInitialized` bị loại ở JDK 27.
- [ ] Đã kiểm tra null behavior.
- [ ] Đã kiểm tra exception retry/error-state behavior.
- [ ] Đã chuyển stable list/map sang collection factory tương ứng.
- [ ] Đã đánh giá `Set.ofLazy` nếu cần.
- [ ] Đã bật preview đúng release ở compile và runtime.
- [ ] Đã chạy CI trên từng JDK được hỗ trợ.

## 12. Câu hỏi tự đánh giá

1. JEP nào giới thiệu Stable Values trong JDK 25?
2. Vì sao StableValue là preview API và điều đó ảnh hưởng thư viện như thế nào?
3. Khác biệt giữa `trySet` và `orElseSet` là gì?
4. Vì sao `trySet` không bảo đảm supplier/candidate chỉ được tạo một lần?
5. Stable holder có làm object bên trong trở thành deep immutable không?
6. Vì sao stable list/map chỉ phù hợp với miền đầu vào xác định?
7. Tại sao stable value không thay thế cache có TTL hoặc eviction?
8. Điều gì xảy ra khi supplier ném exception trong JDK 25?
9. Vì sao stable values và stable collections không phù hợp làm DTO serialization?
10. Tại sao không nên synchronize trực tiếp trên StableValue?
11. Vì sao constant folding chỉ là khả năng tối ưu, không phải cam kết?
12. JDK 26 thay tên StableValue thành API nào?
13. JDK 27 đã loại bỏ hai method nào của LazyConstant?
14. JDK 27 bổ sung factory lazy collection nào cho Set?
15. Khác biệt null behavior giữa StableValue JDK 25 và LazyConstant JDK 27 là gì?
16. Khác biệt exception behavior giữa JDK 26 và JDK 27 là gì?
17. Vì sao JDK 27 không tự retry sau khi LazyConstant chuyển sang error state?
18. Làm thế nào để biểu diễn giá trị có thể vắng mặt trong LazyConstant?
19. Vì sao public API không nên trả về preview type?
20. Cần kiểm thử những gì trước khi phát hành thư viện dùng LazyConstant?

## 13. Tài liệu tham khảo

- [OpenJDK JEP 502 — Stable Values (Preview)](https://openjdk.org/jeps/502): mục tiêu và thiết kế API Stable Values trong JDK 25.
- [Java SE 25 API — `java.lang.StableValue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StableValue.html): factory methods, thread safety, stable functions/collections, serialization và giới hạn triển khai.
- [Oracle Java 25 Core Libraries — Stable Values](https://docs.oracle.com/en/java/javase/25/core/lazy-constants.html): cách sử dụng stable value, supplier, function, list, map và dependency graph.
- [Oracle — Significant Changes in JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): việc đổi tên/revise API theo JEP 526.
- [OpenJDK JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): thiết kế Lazy Constants trong JDK 26.
- [Java SE 26 API — `java.lang.LazyConstant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html): semantics JDK 26 về null, exception retry, trạng thái và thread safety.
- [OpenJDK JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): thay đổi trong JDK 27.
- [Java SE 27 API — `java.lang.LazyConstant`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API hiện tại, error state, null, interrupt, memory retention và serialization.
- [Java SE 27 API — `List.ofLazy`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): lazy list factory.
- [Java SE 27 API — `Map.ofLazy`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): lazy map factory.
- [Java SE 27 API — `Set.ofLazy`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): lazy set factory được bổ sung trong JDK 27.
- [Oracle — Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): JEP 531 và trạng thái preview hiện tại.













