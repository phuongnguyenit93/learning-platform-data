# Vòng đời đối tượng, đặt lại thống kê và việc thay nguồn theo dõi

## Function meter gắn với một đối tượng nguồn cụ thể

Function meter đọc số liệu thông qua các hàm trên một đối tượng nguồn đã được cung cấp lúc đăng ký. Với **FunctionCounter**, hàm đọc trả về một bộ đếm tích lũy; với **FunctionTimer**, các hàm đọc trả về số lần hoàn tất và tổng thời gian tích lũy.

Khi đăng ký meter, Micrometer tạo danh tính meter từ tên, loại và tag, đồng thời giữ tham chiếu đến đối tượng nguồn theo cơ chế của function meter. Các lần thu thập sau đó tiếp tục gọi hàm đọc trên đối tượng đã đăng ký.

Điều này có hệ quả quan trọng đối với vòng đời đối tượng: nếu ứng dụng thay object đang được lưu trong một biến bằng object mới, function meter đã đăng ký không tự động chuyển sang object mới. Nó vẫn đọc object cũ mà builder đã nhận. Việc thay biến tham chiếu ở tầng ứng dụng không thay đổi nguồn của meter.

Vì vậy, khi dùng function meter, cần thiết kế rõ ai sở hữu đối tượng nguồn, đối tượng tồn tại bao lâu, khi nào thống kê được reset và cách thay thế nguồn mà vẫn giữ được semantics của số liệu.

## Vòng đời của đối tượng nguồn

### Giữ tham chiếu mạnh trong suốt thời gian meter cần đọc

Function meter thường sử dụng tham chiếu yếu đến object nguồn. Điều này tránh việc registry vô tình giữ sống một object chỉ vì object đó được đo lường.

Ứng dụng phải giữ tham chiếu mạnh đến object nguồn trong suốt thời gian meter cần hoạt động. Cách phổ biến là lưu object trong field của component hoặc trong một đối tượng quản lý vòng đời.

Ví dụ:

~~~java
@Component
public class CacheMetrics {

    private final CacheStats stats;

    public CacheMetrics(CacheStats stats, MeterRegistry registry) {
        this.stats = stats;

        FunctionCounter.builder(
                "cache.hits",
                stats,
                CacheStats::hitCount
            )
            .register(registry);
    }
}
~~~

Field stats giữ object nguồn sống cùng CacheMetrics. Nếu chỉ tạo object tạm trong constructor, đăng ký function meter rồi không giữ tham chiếu ở đâu khác, garbage collector có thể thu hồi object. Khi đó hàm đọc không còn nguồn dữ liệu; tùy loại function meter và registry, giá trị có thể trở thành NaN hoặc không được xuất như một mẫu hợp lệ.

Không nên dựa vào registry để quản lý vòng đời object nghiệp vụ. Component hoặc thư viện sở hữu thống kê phải chịu trách nhiệm giữ object sống đủ lâu.

### Meter đã đăng ký vẫn gắn với object ban đầu

Ví dụ sau minh họa một lỗi thường gặp:

~~~java
CacheStats currentStats = cache.stats();

FunctionCounter.builder(
        "cache.hits",
        currentStats,
        CacheStats::hitCount
    )
    .register(registry);

// Sau này cache được thay thế.
currentStats = replacementCache.stats();
~~~

Sau phép gán cuối, biến currentStats trỏ đến object mới. Tuy nhiên, FunctionCounter đã đăng ký vẫn gắn với object cũ được truyền vào builder. Nếu object cũ còn sống, meter tiếp tục đọc số liệu cũ; nếu object cũ bị thu hồi, meter có thể không còn đọc được giá trị.

Điều này khác với việc một Gauge đọc một field thông qua supplier đóng trên một holder ổn định. Với function meter, cần chủ động cung cấp một đối tượng trung gian ổn định nếu nguồn có thể thay đổi.

## Không reset bộ đếm tích lũy trong cùng vòng đời meter

### FunctionCounter cần giá trị không giảm

FunctionCounter đại diện cho bộ đếm tích lũy. Giá trị mà hàm đọc trả về cần không giảm trong vòng đời của meter.

Giả sử một cache có 1.000 hit. FunctionCounter đọc 1.000. Sau khi cache bị invalidate, thư viện tạo lại thống kê và hit count bắt đầu từ 0. Lần thu thập tiếp theo, FunctionCounter đọc 0. Giá trị đã giảm từ 1.000 xuống 0, phá vỡ semantics của một bộ đếm tích lũy.

Backend có thể xem mức giảm là counter reset, nhưng không phải backend nào cũng diễn giải giống nhau và dashboard có thể cho kết quả khó hiểu. Đặc biệt, nếu reset xảy ra mà không có ranh giới vòng đời rõ ràng, tốc độ và tổng số có thể bị sai.

Nếu cần đo số hit kể từ khi cache mới được tạo, hãy xem đó là một meter theo vòng đời cache. Nếu cần tổng số hit xuyên suốt nhiều lần thay cache, phải duy trì một bộ đếm tích lũy ở lớp quản lý cao hơn.

### FunctionTimer cũng cần count và total time tích lũy

FunctionTimer đọc count và tổng thời gian từ cùng một đối tượng thống kê. Cả hai giá trị phải phản ánh cùng tập thao tác và không giảm trong vòng đời meter.

Nếu count bị reset về 0 nhưng total time vẫn giữ tổng cũ, trung bình suy ra từ hai giá trị trở nên vô nghĩa. Nếu total time bị reset nhưng count không reset, thời lượng trung bình có thể giảm đột ngột. Nếu cả hai reset cùng lúc, backend vẫn có thể nhận một counter giảm và xem đó là reset.

Vì vậy, không nên reset bộ thống kê của FunctionTimer trong khi meter cùng danh tính vẫn được sử dụng, trừ khi đã thiết kế rõ cách biểu diễn vòng đời mới.

## Các chiến lược khi thống kê cần được đặt lại

Khi đối tượng nguồn cần reset hoặc thay thế, chọn chiến lược dựa trên câu hỏi mà metrics cần trả lời.

### 1. Giữ bộ tích lũy liên tục ở bên ngoài đối tượng có thể reset

Nếu dashboard cần tổng số xuyên suốt vòng đời ứng dụng, hãy duy trì một accumulator ổn định. Đối tượng cache hoặc client có thể được thay thế, nhưng accumulator tiếp tục cộng dồn các giá trị từ từng thế hệ nguồn.

Ví dụ, một lớp quản lý có thể nhận sự kiện hit/miss từ các cache instance và cập nhật bộ đếm tích lũy của chính nó. FunctionCounter đọc bộ đếm này thay vì đọc trực tiếp thống kê của cache đang thay đổi.

Cách này phù hợp khi ứng dụng kiểm soát được các sự kiện hoặc có thể lấy snapshot cuối cùng của nguồn cũ trước khi thay thế.

### 2. Dùng holder ổn định để trỏ đến nguồn hiện tại

Nếu cần function meter luôn đọc thống kê của object hiện hành, hãy đăng ký meter trên một holder sống lâu. Các hàm đọc của function meter nhận holder và truy cập nguồn hiện tại thông qua holder.

Một holder đơn giản:

~~~java
public final class CacheStatsHolder {
    private volatile CacheStats current;

    public CacheStatsHolder(CacheStats initial) {
        this.current = initial;
    }

    public CacheStats current() {
        return current;
    }

    public void replace(CacheStats next) {
        this.current = next;
    }

    public double hitCount() {
        return current.hitCount();
    }
}
~~~

Đăng ký function meter trên holder:

~~~java
FunctionCounter.builder(
        "cache.hits",
        holder,
        CacheStatsHolder::hitCount
    )
    .baseUnit("hits")
    .register(registry);
~~~

Meter luôn giữ cùng một holder; khi holder chuyển sang CacheStats mới, hàm đọc lấy giá trị từ nguồn hiện tại.

Tuy nhiên, holder đơn giản này chỉ an toàn về mặt thay nguồn nếu giá trị mới vẫn tuân thủ semantics tích lũy. Nếu cache mới bắt đầu hit count từ 0, FunctionCounter sẽ đọc một giá trị nhỏ hơn trước đó. Holder đã giải quyết việc đổi object, nhưng chưa giải quyết việc reset số liệu.

Để giữ counter đơn điệu, holder cần cộng dồn phần cuối của nguồn cũ và phần tăng của nguồn mới, hoặc nguồn mới phải tiếp tục một bộ đếm tích lũy từ giá trị trước đó.

### 3. Giữ offset khi thay thế nguồn

Nếu cần tổng số xuyên suốt nhiều thế hệ object, có thể lưu offset đã tích lũy từ các nguồn cũ. Khi nguồn cũ ngừng nhận cập nhật, chụp giá trị cuối của nó, cộng vào offset, rồi chuyển holder sang nguồn mới.

Ví dụ minh họa cho một nguồn thống kê có count tích lũy:

~~~java
public final class CumulativeStatsHolder {
    private CacheStats current;
    private long completedOffset;

    public CumulativeStatsHolder(CacheStats initial) {
        this.current = initial;
    }

    public synchronized void replaceAfterQuiescence(CacheStats next) {
        completedOffset += current.hitCount();
        current = next;
    }

    public synchronized double hitCount() {
        return completedOffset + current.hitCount();
    }
}
~~~

Phương thức replaceAfterQuiescence chỉ được gọi sau khi nguồn cũ đã ngừng nhận cập nhật. Điều kiện này tránh bỏ sót một hit đến đúng lúc chụp giá trị cuối. Trong hệ thống đồng thời, cần cơ chế quiesce, khóa hoặc snapshot nhất quán do thư viện cung cấp trước khi thay thế.

Với FunctionTimer, cần giữ offset cho cả count và total time. Cả hai offset phải được cộng từ cùng một thế hệ nguồn và cùng tập thao tác đã hoàn tất. Nếu yêu cầu snapshot count và total time nhất quán tuyệt đối, nguồn thống kê cần cung cấp cơ chế snapshot phù hợp; hai hàm đọc riêng có thể được gọi ở hai thời điểm thu thập khác nhau.

Không dùng offset để che giấu việc nguồn thống kê bị cập nhật sai. Offset chỉ có ý nghĩa khi có ranh giới vòng đời rõ và có thể lấy snapshot cuối đáng tin cậy.

### 4. Dùng Gauge khi giá trị được phép reset

Nếu điều cần quan sát là số hit kể từ lần reset gần nhất, giá trị hiện tại của một thế hệ cache hoặc số tác vụ đang hoạt động, và việc giảm về 0 là một phần của nghiệp vụ, Gauge có thể đúng semantics hơn FunctionCounter.

Gauge mô tả trạng thái hiện tại; nó không hứa hẹn giá trị tăng đơn điệu. Dashboard phải diễn giải số đo là trạng thái của nguồn hiện tại, không phải tổng tích lũy qua toàn bộ vòng đời ứng dụng.

### 5. Tạo meter riêng cho từng vòng đời có giới hạn

Đôi khi nghiệp vụ thực sự cần phân biệt các thế hệ nguồn. Có thể dùng một chiều tag biểu diễn tập thế hệ hữu hạn, chẳng hạn active/standby hoặc primary/secondary, nếu các giá trị đó có ý nghĩa ổn định.

Không dùng UUID, timestamp hoặc số thứ tự tăng mãi làm tag cho từng lần thay object. Mỗi giá trị tag mới tạo ra một time series mới và có thể làm cardinality tăng không giới hạn.

Nếu meter cũ không còn cần thiết, có thể gỡ meter khỏi registry theo API và lifecycle phù hợp rồi đăng ký lại meter mới. Cách này làm thay đổi vòng đời time series; backend có thể thấy counter bắt đầu lại và dashboard phải xử lý reset hoặc khoảng trống dữ liệu. Chỉ dùng khi chủ đích là bắt đầu một chuỗi đo mới và đã kiểm soát việc gỡ, đăng ký lại cũng như truy vấn.

## Thay nguồn theo dõi mà không làm sai danh tính meter

### Đăng ký trùng tên và tag không tự thay nguồn

Meter trong registry được định danh bằng tên, loại và tag. Nếu đăng ký một FunctionCounter mới với cùng danh tính như meter cũ, registry thường trả về meter đã có thay vì thay thế function đọc và object nguồn.

Do đó, gọi builder lần nữa với object mới nhưng cùng tên/tag không phải cơ chế cập nhật nguồn. Meter cũ có thể tiếp tục đọc object cũ.

Nếu nguồn thay đổi theo vòng đời ứng dụng, hãy chọn một trong hai cách:

- Giữ một holder ổn định và để function đọc truy cập nguồn hiện tại, đồng thời bảo toàn giá trị tích lũy nếu semantics yêu cầu.
- Quản lý rõ việc remove meter cũ và đăng ký meter mới như một vòng đời mới, chấp nhận reset series và cập nhật dashboard tương ứng.

Không đăng ký meter mới cho mỗi lần thay object mà không kiểm soát danh tính. Điều đó có thể tạo meter trùng, hoặc registry bỏ qua nguồn mới vì meter cùng ID đã tồn tại.

### Thay thế object và giữ nguyên ý nghĩa đo

Trước khi thay nguồn, cần xác định:

1. Object mới có đại diện cho cùng đại lượng nghiệp vụ không?
2. Giá trị ban đầu của object mới là 0 hay một snapshot đã có?
3. Các cập nhật vào object cũ đã dừng hoàn toàn chưa?
4. Có cần cộng giá trị cũ vào tổng tích lũy không?
5. Function meter có tiếp tục giữ cùng tên và tag không?
6. Backend có nhìn thấy một counter reset hay một series mới không?

Nếu không trả lời được các câu hỏi này, việc thay object có thể làm dashboard hiển thị một chuỗi số liệu sai ngữ nghĩa dù code vẫn chạy bình thường.

## Vòng đời trong Spring Boot

Trong Spring Boot, component thường giữ đối tượng thống kê và đăng ký function meter trong constructor hoặc phương thức khởi tạo phù hợp. Khi application context dừng, component và registry cũng kết thúc vòng đời.

Ví dụ:

~~~java
@Component
public class StorageStatsMetrics {

    private final OperationStats stats;

    public StorageStatsMetrics(
            OperationStats stats,
            MeterRegistry registry
    ) {
        this.stats = stats;

        FunctionTimer.builder(
                "storage.operation",
                stats,
                OperationStats::count,
                OperationStats::totalTimeNanos,
                TimeUnit.NANOSECONDS
            )
            .description("So lan va tong thoi gian thao tac storage")
            .register(registry);
    }
}
~~~

Field stats giữ object nguồn sống cùng component. Nếu StorageStats là bean singleton, object thường tồn tại cùng application context. Nếu bean có scope ngắn hoặc được thay thế động, phải kiểm soát rõ thời điểm meter ngừng đọc nguồn cũ và chuyển sang nguồn mới.

Không nên đăng ký function meter mỗi khi một request hoặc một tác vụ bắt đầu. Đăng ký meter một lần cho mỗi danh tính ổn định; các lần cập nhật thống kê thuộc về object nguồn.

Khi application context dừng, cần để Spring quản lý lifecycle của exporter và các thành phần thống kê. Nếu nguồn được đóng hoặc reset trước khi registry ngừng scrape, function meter có thể đọc một object đã kết thúc hoặc số liệu đã bị reset. Thứ tự shutdown nên dừng thu thập hoặc ngừng cập nhật nguồn theo cách có kiểm soát trước khi giải phóng object.

## Đồng bộ khi cập nhật và thay thế nguồn

Function meter có thể đọc đồng thời với luồng nghiệp vụ cập nhật object. Các hàm đọc cần nhanh, an toàn đa luồng và không có tác dụng phụ.

Với count và total time, cập nhật hai giá trị phải mô tả cùng một tập thao tác. Nếu count tăng nhưng total time chưa cộng xong, scrape có thể quan sát một trạng thái trung gian. Dùng snapshot hoặc cơ chế đồng bộ thích hợp nếu yêu cầu nhất quán cao.

Khi thay nguồn, không chỉ đồng bộ phép gán reference. Cần đồng bộ cả việc ngừng cập nhật object cũ, lấy snapshot cuối, cập nhật offset và chuyển sang object mới. Nếu có thao tác vẫn đang chạy trên nguồn cũ, phải quyết định chúng thuộc thế hệ cũ hay mới và bảo đảm chỉ cộng đúng một lần.

Tránh gọi hàm đọc thực hiện lock dài, I/O hoặc tính toán tốn kém. Registry có thể thu thập nhiều meter trong một chu kỳ; một function đọc chậm có thể làm ảnh hưởng toàn bộ quá trình scrape.

## Kiểm thử reset và thay nguồn

### Xác minh FunctionCounter không giảm khi thay thế

Kiểm thử cần chứng minh giá trị mà function meter đọc vẫn tăng hoặc giữ nguyên khi chuyển nguồn. Với holder có offset, có thể kiểm tra logic tích lũy sau khi nguồn cũ đã ngừng cập nhật:

~~~java
CacheStatsHolder holder = new CacheStatsHolder(firstStats);
FunctionCounter counter = FunctionCounter.builder(
        "cache.hits",
        holder,
        CacheStatsHolder::hitCount
    )
    .register(registry);

firstStats.recordHits(10);
assertThat(counter.count()).isEqualTo(10.0);

holder.replaceAfterQuiescence(secondStats);
secondStats.recordHits(3);

assertThat(counter.count()).isEqualTo(13.0);
~~~

Đoạn test minh họa giả định holder cộng giá trị cuối của nguồn cũ vào offset khi thay thế. Không dùng holder chỉ gán current nếu nguồn mới reset về 0 mà vẫn kỳ vọng FunctionCounter giữ tổng tích lũy.

### Kiểm tra FunctionTimer qua nhiều thế hệ

Với FunctionTimer, kiểm tra cả count và total time sau khi thay nguồn:

~~~java
assertThat(functionTimer.count()).isEqualTo(expectedCount);
assertThat(functionTimer.totalTime(TimeUnit.MILLISECONDS))
    .isEqualTo(expectedTotalMillis);
~~~

Nếu nguồn được thay thế, expectedCount và expectedTotalMillis phải bao gồm các giá trị cuối đã chốt của nguồn cũ cộng với các giá trị của nguồn mới. Không chỉ kiểm tra count vì total time có thể bị reset độc lập và làm trung bình sai.

Các tình huống cần bao phủ:

1. Nguồn ban đầu có count và total time bằng 0.
2. Nguồn tích lũy tăng sau mỗi thao tác.
3. Nguồn cũ ngừng cập nhật trước khi lấy snapshot cuối.
4. Thay nguồn mới có giá trị ban đầu bằng 0.
5. Giá trị function meter không giảm sau khi chuyển nguồn nếu vẫn dùng cùng meter tích lũy.
6. Count và total time được cộng dồn cùng tập thao tác.
7. Object cũ được thu hồi sau khi holder chuyển nguồn mà meter vẫn đọc được holder.
8. Reset được biểu diễn bằng Gauge hoặc một vòng đời meter riêng khi phù hợp.
9. Không tạo time series không giới hạn từ tag generation.
10. Exporter và dashboard diễn giải đúng reset hoặc series mới.

Có thể dùng SimpleMeterRegistry để kiểm tra logic nguồn và holder. Với registry exporter, cần kiểm tra backend nhìn thấy counter reset, series mới hoặc giá trị tích lũy theo đúng thiết kế.

## Những sai lầm thường gặp

**Chỉ gán biến sang object mới.** Function meter vẫn đọc object đã truyền lúc đăng ký. Dùng holder ổn định hoặc quản lý lại meter theo lifecycle.

**Reset count trong cùng vòng đời FunctionCounter.** Giá trị giảm phá vỡ semantics tích lũy và có thể làm rate hoặc tổng số khó hiểu. Dùng accumulator liên tục hoặc Gauge nếu cần giá trị có thể reset.

**Reset count và total time không cùng lúc.** FunctionTimer có thể đọc hai thống kê thuộc hai tập thao tác khác nhau. Cần một lifecycle và snapshot nhất quán.

**Đăng ký lại cùng tên/tag để thay source.** Registry thường tái sử dụng meter cùng danh tính; object mới không tự thay object cũ. Phải dùng holder hoặc remove/register có chủ đích.

**Để object cũ tiếp tục nhận cập nhật sau khi đã chốt offset.** Các cập nhật đó có thể bị mất khỏi tổng tích lũy. Quiesce nguồn cũ trước khi snapshot và chuyển nguồn.

**Không giữ tham chiếu mạnh đến holder hoặc object nguồn.** Function meter có thể mất khả năng đọc khi object bị garbage collector thu hồi. Giữ holder trong component quản lý.

**Dùng tag generation tăng mãi.** Mỗi thế hệ tạo một time series mới và cardinality tăng không giới hạn. Chỉ dùng chiều thế hệ hữu hạn nếu có ý nghĩa nghiệp vụ.

**Coi backend tự xử lý mọi reset.** Cách backend nhận diện và xử lý counter reset khác nhau. Nguồn vẫn phải có semantics rõ ràng.

**Đọc thống kê bằng hàm nặng hoặc có tác dụng phụ.** Scrape có thể chậm hoặc làm thay đổi số liệu. Hàm đọc phải nhẹ và chỉ quan sát.

## Checklist quản lý vòng đời function meter

Trước khi dùng function meter với object có thể thay thế hoặc reset, hãy xác minh:

1. Ai sở hữu object nguồn và giữ nó sống trong suốt vòng đời meter?
2. Function meter đang gắn với object nào?
3. Biến ứng dụng có thể được gán sang object mới mà meter vẫn đọc object cũ không?
4. Giá trị nguồn có giảm hoặc reset trong vòng đời meter không?
5. Nếu reset, số đo cần biểu diễn trạng thái hiện tại hay tổng tích lũy?
6. Có holder hoặc accumulator ổn định để bảo toàn tổng qua các thế hệ không?
7. Nguồn cũ đã ngừng cập nhật trước khi lấy snapshot cuối chưa?
8. FunctionTimer có giữ count và total time cùng một tập thao tác không?
9. Việc thay nguồn có yêu cầu remove/register và chấp nhận counter reset không?
10. Tag generation có tập giá trị hữu hạn không?
11. Hàm đọc có nhẹ, an toàn đa luồng và không có tác dụng phụ không?
12. Kiểm thử có xác nhận giá trị sau reset, thay nguồn và dữ liệu exporter không?

## Kết luận

FunctionCounter và FunctionTimer gắn với đối tượng nguồn đã được truyền khi đăng ký. Thay object trong biến ứng dụng không tự chuyển function meter sang object mới; reset thống kê trong cùng vòng đời cũng có thể làm bộ đếm hoặc tổng thời gian giảm, phá vỡ semantics tích lũy.

Hãy giữ nguồn sống đủ lâu, không reset số liệu tích lũy nếu meter vẫn giữ cùng danh tính, và xác định rõ chiến lược khi thay object. Một holder ổn định có thể chuyển sang nguồn hiện tại; nếu cần tổng liên tục, hãy cộng dồn snapshot cuối của nguồn cũ vào offset trước khi chuyển. Với dữ liệu có thể tăng giảm theo bản chất, dùng Gauge hoặc bắt đầu một vòng đời meter mới có chủ đích. Kiểm thử cả count, total time, tham chiếu đối tượng và đầu ra backend để bảo đảm dashboard tiếp tục phản ánh đúng ý nghĩa nghiệp vụ.
