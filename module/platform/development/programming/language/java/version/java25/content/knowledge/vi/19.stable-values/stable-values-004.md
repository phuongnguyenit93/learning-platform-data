# Tổ chức giá trị ổn định đơn lẻ hoặc theo tập hợp trong phạm vi API preview

> **Chương:** Stable Values
>
> **Phạm vi:** Bài học đặt API **StableValue** của JDK 25 vào đúng bối cảnh phiên bản, sau đó đối chiếu API hiện hành của JDK 27. JEP 502 giới thiệu Stable Values trong Java 25; JDK 26 đổi tên và thiết kế lại thành **LazyConstant** theo JEP 526; JDK 27 tiếp tục preview theo JEP 531 và bổ sung **Set.ofLazy**. Vì vậy, cú pháp StableValue chỉ dùng cho mã cần chạy đúng JDK 25. Ví dụ mới ở phần hiện hành dùng LazyConstant, List.ofLazy, Map.ofLazy và Set.ofLazy.

## 1. Giá trị ổn định giải quyết vấn đề gì?

Một số đối tượng chỉ cần tạo khi ứng dụng thực sự sử dụng, nhưng sau khi tạo thì không cần thay đổi:

- Logger hoặc parser dùng chung cho một component.
- Schema, metadata hay bảng tra cứu được tạo từ cấu hình.
- Client cho một tập vùng hoặc tenant đã biết.
- Bộ xử lý cho từng vị trí trong một pool có kích thước cố định.
- Kết quả tính toán đắt tiền cho một tập đầu vào hữu hạn.

Nếu khai báo **final**, ta có tính bất biến và khả năng tối ưu tốt, nhưng phải khởi tạo ngay trong constructor hoặc static initializer. Nếu dùng field mutable với null-check, ta có thể trì hoãn khởi tạo nhưng phải tự quản lý race, safe publication và khả năng ghi đè ngoài ý muốn.

Ý tưởng của stable value/lazy constant là tách hai thời điểm:

1. Tạo holder ngay khi dựng component.
2. Tính giá trị khi có lần truy cập đầu tiên, sau đó giữ nguyên giá trị đó.

Sau khi đã khởi tạo thành công, holder không cho thay nội dung. JVM có thể xem nội dung đã ổn định như một hằng số và áp dụng tối ưu hóa tương tự field final, trong những điều kiện phù hợp.

**Giá trị ổn định không phải cache tổng quát.** Nó phù hợp với nội dung được tính tối đa một lần và giữ trong suốt vòng đời holder. Dữ liệu cần refresh, eviction, retry có kiểm soát hoặc thay đổi theo request vẫn cần một cache hay cơ chế quản lý trạng thái phù hợp.

## 2. Trạng thái API theo phiên bản Java

Đây là điểm quan trọng nhất khi học chủ đề có tên Stable Values:

| JDK | JEP và tên API | API chính | Cách dùng |
| --- | --- | --- | --- |
| **25** | JEP 502 — Stable Values (Preview) | StableValue, StableValue.supplier, StableValue.list, StableValue.map, StableValue.function, StableValue.intFunction | Chỉ dùng khi biên dịch và chạy đúng JDK 25 với preview bật. |
| **26** | JEP 526 — Lazy Constants (Second Preview) | LazyConstant, List.ofLazy, Map.ofLazy | API được đổi tên và thiết kế lại; không tương thích mã nguồn trực tiếp với StableValue. |
| **27** | JEP 531 — Lazy Constants (Third Preview) | LazyConstant, List.ofLazy, Map.ofLazy, Set.ofLazy | Đây là API hiện hành trong JDK 27; vẫn là preview. |

Từ JDK 26, StableValue không còn là tên API hiện hành. Các ví dụ StableValue.of(), orElseSet(), trySet() hoặc StableValue.list() trong tài liệu Java 25 chỉ có ý nghĩa khi duy trì mã chạy trên JDK 25. Với mã mới nhắm tới JDK 27, dùng LazyConstant và các factory lazy của collection.

### Bật preview cho đúng JDK

Ví dụ biên dịch mã Java 25 có StableValue:

~~~bash
javac --release 25 --enable-preview -d out src/main/java/example/StableValue25Demo.java
java --enable-preview -cp out example.StableValue25Demo
~~~

Ví dụ biên dịch mã JDK 27 có LazyConstant:

~~~bash
javac --release 27 --enable-preview -d out src/main/java/example/LazyConstant27Demo.java
java --enable-preview -cp out example.LazyConstant27Demo
~~~

Compiler và runtime phải cùng phiên bản JDK preview. Preview API có thể đổi hoặc bị loại bỏ ở bản sau; không biên dịch mã preview bằng JDK 25 rồi kỳ vọng chạy nguyên bytecode đó trên JDK 27. Hãy biên dịch lại bằng JDK mục tiêu.

## 3. Mô hình hoạt động của một lazy constant

Một lazy constant có ba trạng thái khái niệm:

~~~text
Chưa khởi tạo
     |
     | lần đầu gọi get()
     v
Đang tính toán
     |
     +---- tính thành công ----> Đã khởi tạo, giữ nguyên giá trị
     |
     +---- lỗi / null ---------> Trạng thái lỗi (JDK 26/27)
~~~

Trong JDK 27, LazyConstant.of(Supplier) tạo một holder chưa khởi tạo. Lần đầu gọi get() sẽ chạy computing function. Nếu thành công, kết quả được lưu và các lần gọi sau trả lại cùng nội dung.

Khi nhiều thread gọi get() đồng thời:

- Chỉ một thread được chọn để chạy computing function.
- Các thread còn lại chờ quá trình khởi tạo kết thúc.
- Khi thành công, các thread quan sát cùng giá trị đã khởi tạo.
- Việc khởi tạo xảy ra trước khi thread khác đọc nội dung theo quan hệ happens-before, nhờ đó object được safe publication.

Computing function chạy trên thread thắng cuộc gọi get(). Nó có thể là request thread, worker thread hoặc thread khởi tạo class; hãy cân nhắc chi phí và hành vi blocking của function.

## 4. Giá trị đơn lẻ trong JDK 27: LazyConstant

Ví dụ một schema đắt tiền chỉ cần tạo khi component xử lý request đầu tiên:

~~~java
import java.lang.LazyConstant;

final class SchemaRegistry {

    private static final LazyConstant<Schema> SCHEMA =
            LazyConstant.of(SchemaRegistry::loadSchema);

    private static Schema loadSchema() {
        // Đọc và phân tích schema một lần.
        return SchemaLoader.load("/schemas/orders.json");
    }

    static Schema schema() {
        return SCHEMA.get();
    }
}
~~~

Khai báo SCHEMA không chạy loadSchema(). Lần đầu gọi schema() mới thực hiện việc tải và phân tích. Các lần truy cập sau dùng giá trị đã khởi tạo.

Để JVM có cơ hội áp dụng constant folding, nên có đường tham chiếu từ field static final tới LazyConstant, trực tiếp hoặc qua các trusted fields mà JDK nhận diện (static final fields, record fields hoặc final instance fields trong hidden classes). Không phải cứ đặt holder vào bất kỳ field final nào là đủ. Tối ưu hóa này là khả năng của JVM, không phải cam kết rằng mọi lần gọi đều được inline hoặc constant-fold.

### 4.1. Lazy constant không làm object trở nên deep immutable

Holder chỉ đảm bảo reference nội dung không bị thay thế sau khi khởi tạo. Object được giữ bên trong vẫn có thể mutable:

~~~java
private static final LazyConstant<List<String>> ALLOWED =
        LazyConstant.of(ArrayList::new);
~~~

Ví dụ trên vẫn trả về một ArrayList có thể thay đổi. Nếu nhiều thread cùng truy cập, việc sửa danh sách vẫn cần thiết kế đồng bộ. Muốn dữ liệu bất biến, hãy trả về collection unmodifiable hoặc một value object bất biến:

~~~java
private static final LazyConstant<List<String>> ALLOWED =
        LazyConstant.of(() -> List.of("READ", "WRITE", "AUDIT"));
~~~

Không nhầm tính ổn định của holder với tính bất biến của object được giữ.

## 5. StableValue trong JDK 25: cú pháp dành cho dự án Java 25

Trong JDK 25, StableValue<T> là một holder có thể được đặt nội dung tối đa một lần. Cách dùng phổ biến là tạo holder chưa có nội dung rồi khởi tạo lười bằng orElseSet():

~~~java
import java.lang.StableValue;

final class LoggerProvider {

    private final StableValue<Logger> logger = StableValue.of();

    Logger logger() {
        return logger.orElseSet(
                () -> Logger.getLogger(LoggerProvider.class.getName()));
    }
}
~~~

orElseSet() đảm bảo supplier được thực hiện thành công tối đa một lần kể cả khi nhiều thread truy cập đồng thời. Nếu supplier ném unchecked exception, exception được truyền về caller và holder vẫn chưa có nội dung; lần gọi sau có thể thử tính lại.

### 5.1. Các thao tác của StableValue trong JDK 25

| API JDK 25 | Ý nghĩa |
| --- | --- |
| StableValue.of() | Tạo holder chưa có nội dung. |
| StableValue.of(value) | Tạo holder đã có nội dung. |
| isSet() | Kiểm tra holder đã được đặt nội dung chưa. |
| trySet(value) | Thử đặt nội dung; trả true nếu thread hiện tại đặt thành công. |
| setOrThrow(value) | Đặt nội dung hoặc ném IllegalStateException nếu đã được đặt. |
| orElseSet(supplier) | Trả nội dung; nếu chưa có thì tính và đặt bằng supplier. |
| orElseThrow() | Lấy nội dung hoặc ném NoSuchElementException nếu chưa đặt. |
| orElse(other) | Lấy nội dung nếu đã đặt, nếu chưa thì trả giá trị thay thế. |

Không dùng isSet() rồi tự tạo object và gọi trySet() nếu mục tiêu là chỉ tạo đúng một instance. Hai thread có thể cùng tạo hai object trước khi một thread thắng thao tác set. Dùng orElseSet() nếu chi phí tạo object hoặc side effect phải xảy ra tối đa một lần.

### 5.2. Stable supplier

JDK 25 có thể gói holder bên trong Supplier:

~~~java
private final Supplier<Logger> logger =
        StableValue.supplier(
                () -> Logger.getLogger(LoggerProvider.class.getName()));

Logger logger() {
    return logger.get();
}
~~~

Stable supplier lưu kết quả của supplier gốc ở lần get() đầu tiên thành công. Cách này tiện khi muốn truy cập bằng get() mà không phải viết accessor dùng orElseSet().

Các ví dụ ở phần này chỉ dành cho source code chạy trên JDK 25. Khi chuyển lên JDK 26 hoặc 27, đổi sang LazyConstant.of(...) và get() như phần 4; không giữ lại tên StableValue trong mã mới.

## 6. Tổ chức nhiều giá trị theo tập hợp

Một ứng dụng có thể có nhiều thành phần chỉ được dùng trong một số luồng nghiệp vụ. Khởi tạo tất cả khi startup làm tăng thời gian khởi động và có thể tạo nhiều object không bao giờ được dùng.

Lazy collection giữ trước cấu trúc và tập khóa/vị trí, nhưng chỉ tính từng phần tử khi phần tử đó được truy cập. Mỗi phần tử hoặc key được tính tối đa một lần khi thành công.

### 6.1. Danh sách lazy trong JDK 27

List.ofLazy(size, computingFunction) tạo danh sách unmodifiable có kích thước cố định. Phần tử tại index được tính ở lần đầu gọi get(index):

~~~java
import java.util.List;

final class CodecRegistry {

    private static final int SLOT_COUNT = 4;

    private static final List<Codec> CODECS =
            List.ofLazy(SLOT_COUNT, CodecFactory::createForSlot);

    static Codec codec(int slot) {
        return CODECS.get(slot);
    }
}
~~~

Ví dụ này chỉ tạo codec cho slot thực sự được truy cập. Các lần truy cập cùng index dùng lại kết quả đã khởi tạo. List.ofLazy không cho thêm, xóa hoặc thay phần tử; kích thước được xác định lúc tạo list.

### 6.2. Map lazy trong JDK 27

Map.ofLazy(keys, computingFunction) tạo map unmodifiable với tập key cố định. Value của mỗi key chỉ được tính khi gọi get(key) hoặc truy cập view cần value:

~~~java
import java.util.Map;
import java.util.Set;

enum Region {
    APAC, EUROPE, AMERICAS
}

final class RegionalClients {

    private static final Set<Region> REGIONS =
            Set.of(Region.APAC, Region.EUROPE, Region.AMERICAS);

    private static final Map<Region, ApiClient> CLIENTS =
            Map.ofLazy(REGIONS, ApiClientFactory::forRegion);

    static ApiClient client(Region region) {
        return CLIENTS.get(region);
    }
}
~~~

Map này phù hợp khi tập key biết trước, nhưng việc tạo value có thể trì hoãn. Key ngoài tập đã khai báo không phải một entry được hỗ trợ; hãy kiểm tra key trước khi truy cập nếu input đến từ bên ngoài.

### 6.3. Set lazy trong JDK 27

JDK 27 bổ sung Set.ofLazy(elementCandidates, predicate). Set này nhận tập ứng viên có sẵn, sau đó tính trạng thái membership của từng ứng viên khi có truy vấn contains(element):

~~~java
import java.util.EnumSet;
import java.util.Set;

enum Feature {
    EXPORT, AUDIT, BETA_SEARCH
}

final class FeatureSwitches {

    private static final Set<Feature> ENABLED =
            Set.ofLazy(
                    EnumSet.allOf(Feature.class),
                    FeatureSwitches::isEnabled);

    private static boolean isEnabled(Feature feature) {
        return FeatureConfiguration.read(feature);
    }

    static boolean enabled(Feature feature) {
        return ENABLED.contains(feature);
    }
}
~~~

Set không tính một object mới cho mỗi phần tử. Nó tính kết quả boolean cho câu hỏi một ứng viên có thuộc set hay không. Cấu trúc set là unmodifiable; tập ứng viên được cố định khi tạo.

Nếu predicate ném unchecked exception cho một candidate, trạng thái membership của candidate đó chuyển sang error state. Các lần gọi contains() tiếp theo ném NoSuchElementException và không chạy lại predicate cho candidate đó.

### 6.4. Tương ứng với API Java 25

Trong JDK 25, các collection/function này được tạo qua StableValue:

~~~java
// JDK 25 only
private static final List<Codec> CODECS =
        StableValue.list(4, CodecFactory::createForSlot);

private static final Map<Region, ApiClient> CLIENTS =
        StableValue.map(REGIONS, ApiClientFactory::forRegion);

private static final IntFunction<Codec> CODEC_BY_SLOT =
        StableValue.intFunction(4, CodecFactory::createForSlot);

private static final Function<Region, ApiClient> CLIENT_BY_REGION =
        StableValue.function(REGIONS, ApiClientFactory::forRegion);
~~~

JDK 25 có stable list và stable map, cùng stable IntFunction và Function. JDK 27 chuyển factory list/map sang List/Map, và bổ sung lazy set. Không có StableValue.set(...) trong JDK 25; cũng không nên nhầm Set.ofLazy của JDK 27 với một factory có cùng tên trong API Java 25.

## 7. Bảng chuyển đổi từ StableValue sang API hiện hành

| Mục đích | JDK 25 (JEP 502) | JDK 27 (JEP 531) |
| --- | --- | --- |
| Một giá trị khởi tạo lười | StableValue.of() + orElseSet(supplier) | LazyConstant.of(supplier) + get() |
| Giá trị có sẵn ngay | StableValue.of(value) | LazyConstant.of(() -> value) |
| Supplier cache một kết quả | StableValue.supplier(supplier) | LazyConstant.of(supplier) |
| Danh sách lazy theo index | StableValue.list(size, mapper) | List.ofLazy(size, mapper) |
| Map lazy theo tập key | StableValue.map(keys, mapper) | Map.ofLazy(keys, mapper) |
| Function cache theo tập input | StableValue.function(keys, function) | Map.ofLazy(keys, function) nếu mô hình là tra cứu theo key |
| IntFunction cache theo range | StableValue.intFunction(size, function) | List.ofLazy(size, function) nếu input là index từ 0 đến size - 1 |
| Set membership tính lười | Không có factory tương ứng trong StableValue | Set.ofLazy(candidates, predicate) |

### Khác biệt về xử lý lỗi giữa các thế hệ API

Đây là khác biệt hành vi cần kiểm tra khi migrate:

| Trường hợp | StableValue JDK 25 | LazyConstant / lazy collections JDK 27 |
| --- | --- | --- |
| Supplier ném unchecked exception | Exception được ném cho caller; holder chưa set và có thể thử lại ở lần gọi sau. | Constant/slot/key/candidate chuyển sang error state; lần gọi sau ném NoSuchElementException, không chạy lại computing function. |
| Supplier trả null | StableValue và stable collection JDK 25 cho phép nội dung/phần tử null theo API tương ứng. | LazyConstant, lazy list và lazy map không chấp nhận null; lỗi chuyển sang error state. |
| Nhiều thread cùng khởi tạo | At-most-once cho một lần tính thành công; các thread cạnh tranh chờ kết quả. | Một thread tính; các thread còn lại chờ kết quả hoặc trạng thái lỗi. |

Nếu cần nullable result trong JDK 27, trả Optional<T> từ computing function thay vì trả null. Nếu cần retry sau lỗi tạm thời, LazyConstant không phải lựa chọn phù hợp: hãy dùng một cache hoặc state machine có chính sách retry rõ ràng.

## 8. Thread safety và safe publication

Stable values/lazy constants giải quyết hai vấn đề khác nhau:

1. **At-most-once initialization:** nhiều thread không tạo ra nhiều nội dung được chấp nhận cho cùng một holder, slot hoặc key.
2. **Safe publication:** việc khởi tạo xảy ra trước khi nội dung được thread khác đọc theo quan hệ happens-before.

Trong JDK 27, LazyConstant.get() đảm bảo khởi tạo nguyên tử và at-most-once. Thread thắng cuộc gọi computing function; các thread còn lại đợi cho đến khi quá trình khởi tạo thành công hoặc chuyển sang error state.

Tuy nhiên:

- Không có timeout hay cancellation tích hợp cho computing function.
- Nếu function block vô thời hạn, các thread khác chờ get() cũng có thể block vô thời hạn.
- Interruption của thread đang tính không hủy việc khởi tạo; get() không ném InterruptedException chỉ vì thread bị interrupt.
- Holder không bảo vệ các thao tác mutate object được trả về sau khi khởi tạo.

Hãy giữ computing function ngắn và có giới hạn. Không đặt một network call không timeout hoặc truy vấn database có thể treo vô thời hạn vào lazy constant dùng chung toàn ứng dụng.

## 9. Tổ chức dependency graph và tránh khởi tạo vòng

Một lazy constant có thể phụ thuộc vào lazy constant khác:

~~~java
private static final LazyConstant<DatabaseConfig> DATABASE =
        LazyConstant.of(DatabaseConfig::load);

private static final LazyConstant<OrderRepository> ORDERS =
        LazyConstant.of(() -> new OrderRepository(DATABASE.get()));
~~~

Khi gọi ORDERS.get(), DATABASE.get() được thực hiện trước nếu database config chưa được khởi tạo. Đây là dependency graph có hướng.

Không tạo chu trình:

~~~text
ServiceA -> ServiceB -> ServiceA
~~~

Nếu computing function gọi lại chính lazy constant đang được tính, API phát hiện recursive initialization và đưa constant vào error state. Các chu trình gián tiếp qua nhiều holder cũng có thể gây lỗi khởi tạo hoặc lỗi class initialization. Hãy thiết kế dependency graph theo một chiều và tách interface/configuration để phá vòng.

## 10. Những giới hạn về collection và bộ nhớ

Lazy collection không phải collection mutable có thể tự nạp key tùy ý:

- List.ofLazy có kích thước cố định; chỉ index hợp lệ mới được tính.
- Map.ofLazy có key set cố định; map không tự thêm key mới.
- Set.ofLazy chỉ tính membership cho các candidate được truyền lúc tạo.
- Các collection lazy là unmodifiable; không dùng add, put, remove để thay đổi chúng.
- JDK 27 lazy collection không cho phép phần tử/value null.
- Các object method như equals, hashCode hoặc toString có thể khiến một số phần tử/value được khởi tạo; đừng gọi chúng một cách vô thức trong logging nóng.

Một lazy constant giữ nội dung bằng strong reference. Khi holder còn reachable, nội dung đã khởi tạo cũng còn reachable. Lazy list/map giữ computing function khi vẫn còn phần tử chưa được tính. Một static lazy holder chứa object lớn có thể giữ object đó suốt vòng đời classloader.

Không dùng lazy collection như cache không giới hạn hoặc cache cần eviction. Với dữ liệu có số key không bị chặn, hãy dùng cache có giới hạn dung lượng, TTL và chính sách tải lại.

## 11. Hiệu năng: tối ưu hóa có điều kiện, không phải cam kết

Sau khi nội dung đã được khởi tạo và không thể thay đổi, JVM có thể loại bỏ các lần đọc holder trong một số điều kiện và thay bằng nội dung đã quan sát (constant folding).

Trong JDK 27, khả năng tối ưu này gắn với đường tham chiếu tin cậy từ static final field tới LazyConstant, hoặc qua một chuỗi field tin cậy được JVM nhận diện. Vì vậy, cách khai báo thường gặp là:

~~~java
private static final LazyConstant<Schema> SCHEMA =
        LazyConstant.of(Schema::load);
~~~

Không nên tuyên bố rằng mọi lần get() đều trở thành hằng số hoặc luôn nhanh hơn field final. Việc tối ưu phụ thuộc vào JVM implementation, vị trí tham chiếu, profile và code thực tế.

Đo hiệu quả theo hai giai đoạn:

1. **Startup/lần truy cập đầu:** xác định chi phí khởi tạo có được trì hoãn đúng như mong muốn không.
2. **Read path sau khởi tạo:** đo throughput và latency sau warmup, đồng thời kiểm tra JIT có thực hiện tối ưu hóa phù hợp không.

Nếu cần so sánh, dùng JMH với workload thực tế, warmup đủ dài, nhiều fork và cùng phiên bản JDK/build. Không dùng một phép đo System.nanoTime() đơn giản để kết luận về constant folding.

## 12. Khi nào nên dùng?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Component chỉ được dùng ở một số luồng, chi phí tạo cao | LazyConstant cho instance dùng chung. |
| Tập vị trí cố định, mỗi vị trí tạo object riêng khi cần | List.ofLazy. |
| Tập key biết trước, value tạo đắt tiền | Map.ofLazy. |
| Tập ứng viên hữu hạn, membership phải đọc từ cấu hình | Set.ofLazy. |
| Giá trị thay đổi theo thời gian hoặc phải refresh | Cache/state holder có cơ chế cập nhật. |
| Kết quả cần retry sau lỗi tạm thời | Cơ chế retry/cache riêng, không dùng LazyConstant terminal error state. |
| Key đầu vào không giới hạn hoặc có eviction | Cache có giới hạn như Caffeine hoặc cơ chế cache của ứng dụng. |

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Compiler báo StableValue không tồn tại trên JDK 27 | API JDK 25 đã được thay bằng LazyConstant từ JDK 26 | Dùng LazyConstant.of(...) và get(). |
| Compiler báo LazyConstant là preview | Chưa bật preview hoặc dùng compiler/runtime không cùng phiên bản | Dùng JDK 27 với --enable-preview khi compile và run. |
| get() ném NoSuchElementException | Computing function trả null, ném unchecked exception hoặc recursive initialization | Kiểm tra cause ở lần lỗi đầu, sửa function; JDK 27 không retry sau error state. |
| Thread khác chờ rất lâu ở get() | Computing function đang block | Đặt timeout ở I/O bên trong và tránh khởi tạo bằng thao tác có thể treo. |
| Object bên trong vẫn bị thay đổi | Holder ổn định nhưng nội dung object mutable | Dùng object immutable hoặc đồng bộ riêng cho state mutable. |
| Lazy list/map tạo quá nhiều object | Phần lớn index/key đều được truy cập hoặc phạm vi collection quá rộng | Thu hẹp tập index/key hoặc dùng cache có giới hạn. |
| Static initialization thất bại | Dependency graph có chu trình | Tách dependency và thiết kế đồ thị khởi tạo một chiều. |
| Memory tăng dù chỉ tạo lazy value | Holder giữ strong reference tới nội dung đã tạo | Kiểm tra vòng đời classloader, static holder và kích thước object được giữ. |
| Dùng Set.ofLazy trên JDK 25 | Factory này chỉ xuất hiện ở JDK 27 | Với Java 25, mô hình membership phải được tổ chức bằng API khác; không giả định có stable set factory. |

## 14. Bài tập thực hành

### Bài A — Lazy constant đơn lẻ

Tạo một LazyConstant<Schema> trong JDK 27. Ghi log trong computing function và gọi get() từ nhiều thread.

**Điều kiện đạt:** computing function chỉ được thực thi một lần khi thành công; các thread quan sát cùng instance đã khởi tạo.

### Bài B — Lazy list

Tạo List.ofLazy(5, mapper) để tạo năm parser. Chỉ truy cập index 0 và 3.

**Điều kiện đạt:** chỉ hai parser được tạo; gọi lại cùng index không tạo parser mới; list không cho phép sửa.

### Bài C — Lazy map

Tạo map client theo tập Region cố định bằng Map.ofLazy. Gọi một key nhiều lần và một key khác lần đầu.

**Điều kiện đạt:** mỗi key được tính tối đa một lần; key ngoài tập được khai báo không được coi là entry hợp lệ.

### Bài D — Lazy set membership

Tạo Set.ofLazy từ tập enum candidate. Predicate đọc cấu hình bật/tắt từng feature.

**Điều kiện đạt:** mỗi candidate được đánh giá tối đa một lần và membership không thể thay đổi sau khi đã tính thành công.

### Bài E — So sánh lỗi giữa JDK 25 và JDK 27

Viết hai chương trình nhỏ: một chương trình dùng StableValue.orElseSet() trên JDK 25, chương trình kia dùng LazyConstant.get() trên JDK 27. Cho computing function ném unchecked exception ở lần đầu.

**Điều kiện đạt:** mô tả được khác biệt giữa JDK 25 có thể thử lại sau khi supplier thất bại và JDK 27 chuyển sang error state, không chạy lại computing function.

## 15. Checklist trước khi sử dụng

- [ ] Xác định target JDK: StableValue chỉ dành cho mã Java 25; mã hiện hành dùng LazyConstant của JDK 26/27.
- [ ] Bật preview khi biên dịch và chạy đúng phiên bản JDK.
- [ ] Chọn một giá trị đơn lẻ, list, map hay set membership theo miền đầu vào hữu hạn.
- [ ] Computing function không có side effect lặp lại và có thời gian thực thi được kiểm soát.
- [ ] Không trả null từ LazyConstant hoặc lazy collection JDK 27; dùng Optional nếu cần biểu diễn vắng mặt.
- [ ] Hiểu rằng lỗi khởi tạo JDK 27 trở thành error state và không được retry.
- [ ] Không dùng lazy constant cho dữ liệu cần refresh, eviction hoặc thay đổi.
- [ ] Dùng object immutable hoặc quản lý đồng bộ riêng nếu nội dung mutable.
- [ ] Tránh dependency cycle và recursive initialization.
- [ ] Kiểm tra strong references, memory retention và classloader lifecycle.
- [ ] Không giả định constant folding chắc chắn xảy ra; đo bằng JMH sau warmup.
- [ ] Đọc Javadoc của JDK mục tiêu khi nâng cấp vì API vẫn preview và tiếp tục thay đổi.

## 16. Tài liệu tham khảo

1. [JEP 502 — Stable Values (Preview)](https://openjdk.org/jeps/502): thiết kế StableValue được preview trong JDK 25.
2. [Java SE 25 — StableValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StableValue.html): factory, thao tác set, stable supplier, stable function, list và map.
3. [Oracle Java 25 — Stable Values](https://docs.oracle.com/en/java/javase/25/core/lazy-constants.html): hướng dẫn sử dụng API Stable Values trong JDK 25.
4. [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): thiết kế đổi tên và cập nhật API từ Stable Values trong JDK 26.
5. [Java SE 26 — LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html): API LazyConstant ở lần preview thứ hai.
6. [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): phiên bản preview tiếp theo trong JDK 27.
7. [Java SE 27 — LazyConstant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): of, get, thread safety, failure state và constant folding.
8. [Java SE 27 — List.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): danh sách lazy theo index.
9. [Java SE 27 — Map.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): map lazy theo tập key.
10. [Java SE 27 — Set.ofLazy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): set lazy membership theo tập ứng viên.
11. [Oracle — Preview Language and VM Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-and-vm-features.html): cách bật preview khi biên dịch và chạy.
12. [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận JEP 531 Lazy Constants là Third Preview trong JDK 27.

**Ghi nhớ:** Ý tưởng ổn định hóa một giá trị khởi tạo lười vẫn tiếp tục được phát triển, nhưng tên và hợp đồng API đã thay đổi sau Java 25. Hãy dùng StableValue khi duy trì đúng target JDK 25; với JDK 27, dùng LazyConstant và các factory List.ofLazy, Map.ofLazy, Set.ofLazy. Chỉ áp dụng cho dữ liệu có thể giữ nguyên sau lần tính đầu, và luôn kiểm tra failure state, memory retention cùng chi phí khởi tạo.
