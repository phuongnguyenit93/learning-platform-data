# Cân nhắc lưu kết quả hàm và điều kiện để không làm sai hành vi

Trong thiết kế theo hàm (*functional design*), một phép tính có thể được gọi lại nhiều lần với cùng đầu vào. Nếu phép tính tốn CPU, cấp phát bộ nhớ hoặc phải thực hiện một thuật toán phức tạp, **lưu kết quả để tái sử dụng** — thường gọi là *memoization* — có thể giảm công việc lặp lại. Nhưng không phải hàm nào cũng được phép cache.

Điều quan trọng không phải chỉ là “cùng tham số thì cache được” mà là: **thay lời gọi tính toán bằng một giá trị đã lưu có giữ nguyên hành vi mà người dùng và phần còn lại của chương trình quan sát được hay không?** Nếu đầu ra phụ thuộc thời gian, trạng thái bên ngoài, thông tin phiên đăng nhập, cấu hình thay đổi hoặc tác dụng phụ bắt buộc, cache sai có thể biến một chương trình đúng thành chương trình sai.

Ví dụ ý tưởng:

~~~java
int first = expensiveSquare(4);  // Tính ra 16.
int second = expensiveSquare(4); // Cũng cho 16 nếu hàm ổn định.
~~~

Nếu `expensiveSquare` thật sự chỉ phụ thuộc số 4 và không có tác dụng phụ bắt buộc, lần gọi thứ hai có thể nhận lại 16 từ cache. Trái lại, một hàm `getStock("SKU-1")` đọc tồn kho hiện tại từ cơ sở dữ liệu **không** thể được cache mãi chỉ vì tham số SKU không đổi.

Mục tiêu của bài là hiểu **khi nào memoization hợp lệ, chọn khóa và giá trị cache đúng, xử lý thay đổi dữ liệu, đồng thời, lỗi và bộ nhớ**, đồng thời giữ thiết kế dễ kiểm thử.

## 1. Memoization, caching và tính trong suốt tham chiếu

Một hàm toán học thuần `f(x)` có thể được thay bằng kết quả `y = f(x)` ở bất kỳ chỗ nào mà không làm thay đổi ý nghĩa chương trình. Tính chất này liên quan tới **referential transparency** (*tính trong suốt tham chiếu*).

Ví dụ hàm:

~~~java
static int square(int n) {
    return Math.multiplyExact(n, n);
}
~~~

Với `n = 4`, nó luôn cho 16; với đầu vào khiến phép nhân tràn `int`, nó luôn ném `ArithmeticException` theo cùng quy tắc. Hàm không đọc đồng hồ, mạng hay biến mutable bên ngoài. Vì thế việc memoize **các kết quả thành công** có thể tương đương về giá trị trả về.

**Memoization** thường là cache kết quả theo **đối số của một hàm**, ngay gần chỗ tính. **Caching** là khái niệm rộng hơn: có thể cache HTTP response, kết quả truy vấn, đối tượng nghiệp vụ hay tập dữ liệu dùng chung giữa nhiều thành phần. Cả hai đều cần trả lời các câu hỏi về tính hợp lệ, scope, hết hạn và vô hiệu hóa dữ liệu.

Luồng xử lý cơ bản:

~~~text
Gọi f(x)
   |
   v
Tạo khóa cache K(x)
   |
   +---- Có entry hợp lệ? ---- Có ----> Dùng kết quả đã lưu
   | 
   Không
   |
   v
Tính f(x)
   |
   v
Quyết định có lưu kết quả hay không
   |
   v
Trả kết quả cho caller
~~~

“Có entry” **không** tự đồng nghĩa “entry còn đúng”. Một bản cache có thể tồn tại nhưng đã lỗi thời, thuộc quyền của người dùng khác hoặc dùng cấu hình cũ. Quy tắc kiểm tra hợp lệ phải phản ánh hợp đồng nghiệp vụ.

### Câu hỏi quyết định

Giả sử có hai lần gọi `f(x)` tại thời điểm khác nhau. Hãy tự hỏi:

1. Có phải **mọi dữ liệu ảnh hưởng kết quả** đều được biểu diễn trong `x` hoặc trong một ngữ cảnh bất biến tương ứng?
2. Kết quả có được phép tái sử dụng theo thời gian, phiên người dùng và quyền truy cập?
3. Lời gọi có **side effect** bắt buộc phải thực hiện mỗi lần không?
4. Đối số và giá trị trả về có thể bị thay đổi qua tham chiếu không?
5. Khi một phép tính thất bại hoặc trả `null`, chính sách cache là gì?
6. Bộ nhớ, chi phí lưu/tra cứu và yêu cầu truy cập đồng thời có hợp lý không?

Nếu câu trả lời còn mơ hồ, chưa đủ căn cứ để đặt cache vào hàm.

## 2. Hàm thuần và ranh giới của “cùng input”

Một **pure function** có hai đặc điểm quan trọng:

- Không có tác dụng phụ có thể quan sát được: không tự sửa database, tăng biến đếm nghiệp vụ, gửi email, ghi file hay thay đổi trạng thái chương trình.
- Với cùng đầu vào có ý nghĩa, trả **cùng kết quả**, không phụ thuộc trạng thái bên ngoài không được mô tả trong tham số.

Ví dụ tốt:

~~~java
static long subtotal(long unitPriceCents, int quantity) {
    return Math.multiplyExact(unitPriceCents, (long) quantity);
}
~~~

Đầu ra được xác định bởi hai giá trị đầu vào, theo ngữ nghĩa và giới hạn `long` của phép nhân có kiểm tra tràn.

Những trường hợp **không thuần hoặc chỉ thuần trong phạm vi điều kiện**:

~~~java
// Không thuần: thời gian hiện tại thay đổi.
Instant currentTime() {
    return Instant.now();
}

// Không thuần: random generator có trạng thái.
int nextRoll(Random random) {
    return random.nextInt(1, 7);
}

// Không thuần: nguồn ngoài có thể thay đổi.
long currentBalance(String accountId) {
    return repository.loadBalance(accountId);
}
~~~

Đây là **mã minh họa**, không phải chương trình độc lập; cần imports và một đối tượng `repository` thích hợp. Các hàm này có thể là lựa chọn hoàn toàn đúng cho nghiệp vụ, nhưng không thể cache chỉ dựa vào tham số tường minh rồi giả định tương đương.

### Phụ thuộc ẩn làm cache sai

Một phép tính có thể trông như hàm thuần:

~~~java
long finalPrice(String sku) {
    return priceCatalog.get(sku) * currentExchangeRate;
}
~~~

Nhưng kết quả phụ thuộc cả danh mục giá và tỷ giá hiện tại. Nếu cache theo `sku` trong khi dữ liệu thay đổi, kết quả bị cũ.

Cách thiết kế dễ kiểm soát hơn là đẩy phụ thuộc thành dữ liệu đầu vào rõ ràng:

~~~java
record PriceInput(long baseCents, int quantity, int taxBasisPoints) {}

static long taxCents(PriceInput in) {
    long subtotal = Math.multiplyExact(in.baseCents(), in.quantity());
    return Math.multiplyExact(subtotal, in.taxBasisPoints()) / 10_000L;
}
~~~

Mã này là phép toán số học xác định theo `PriceInput`. Tuy nhiên, **chính sách làm tròn, thuế và tràn số** vẫn phải được định nghĩa theo nghiệp vụ. Không được đổi sang phép tính khác chỉ vì thuận tiện cho cache.

Đầu vào đóng gói đầy đủ giúp cache dễ kiểm tra hơn. Nhưng nếu logic tính thuế hoặc phiên bản quy định thay đổi trong khi cache vẫn sống, phiên bản thuật toán/cấu hình cũng có thể cần là một phần của khóa hoặc cần vô hiệu hóa cache.

## 3. Memoize bằng `Map.computeIfAbsent()`

Trong Java, cách viết ngắn để cache các kết quả không null theo khóa:

~~~java
Map<Integer, Integer> cache = new HashMap<>();

Function<Integer, Integer> memoizedSquare =
        n -> cache.computeIfAbsent(n, k -> Math.multiplyExact(k, k));
~~~

Đây là đoạn minh họa trong **ngữ cảnh tuần tự**, cần `Map`, `HashMap`, `Function`. `computeIfAbsent` chỉ gọi mapping function khi khóa đang không gắn với một giá trị khác null; nếu mapping function trả kết quả khác null, Map lưu kết quả để dùng lại.

Trong môi trường đa luồng, `HashMap` thường **không an toàn** cho nhiều thread cùng sửa/tra cứu. Không dùng đoạn trên như cache chia sẻ giữa các lời gọi song song nếu không có cơ chế đồng bộ.

### Khi dùng chung nhiều thread

Có thể thay bằng `ConcurrentHashMap`:

~~~java
ConcurrentHashMap<Integer, Integer> cache = new ConcurrentHashMap<>();

Function<Integer, Integer> memoizedSquare =
        n -> cache.computeIfAbsent(n, k -> Math.multiplyExact(k, k));
~~~

`ConcurrentHashMap.computeIfAbsent` có hợp đồng cập nhật nguyên tử cho mỗi key khi tính mapping. Nó phù hợp với tình huống nhiều thread dùng chung cache; nếu một giá trị đã lưu, các lời gọi sau nhận lại kết quả đó.

Điều đó **không** giải quyết mọi bài toán về cache:

- Cache vẫn có thể chứa **kết quả đã lỗi thời** nếu nguồn phụ thuộc bên ngoài thay đổi.
- Map vẫn có thể phát triển **không giới hạn** nếu không có chính sách sức chứa.
- Nếu hàm tính chậm, các thao tác liên quan có thể chịu contention. Mapping function nên ngắn và không tự gây vòng lặp cập nhật cùng map.
- Nếu cache lưu object mutable, nhiều caller có thể cùng nhận **chính một tham chiếu** rồi sửa nó.
- **Không** cache tác dụng phụ chỉ vì `computeIfAbsent` tránh tính trùng.

### Vì sao hàm tính không nên sửa lại chính Map?

Mapping function dùng trong `computeIfAbsent` nên tập trung vào tạo giá trị cho key được yêu cầu. Không thực hiện cập nhật đệ quy lên cùng Map trong mapping function; đặc biệt với `ConcurrentHashMap`, cập nhật đệ quy gây lỗi hoặc bế tắc tùy tình huống/hợp đồng.

Không xem `computeIfAbsent` như một hệ thống caching hoàn chỉnh có TTL, quota, thống kê, circuit breaker hay refresh tự động: JDK `ConcurrentHashMap` **không cung cấp sẵn những chính sách đó**.

## 4. Ví dụ Java 17+ có kiểm chứng hành vi

Chương trình sau minh họa ba nội dung:

1. Memoization của phép tính số theo key `Integer`.
2. Khóa nhiều thuộc tính bằng một `record` bất biến.
3. Kết quả `null` không được lưu bởi `ConcurrentHashMap.computeIfAbsent`.

Lưu tệp **`MemoizationDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.stream.Stream;

public class MemoizationDemo {
    record TaxInput(long subtotalCents, int taxBasisPoints) {}

    public static void main(String[] args) {
        AtomicInteger computations = new AtomicInteger();
        ConcurrentHashMap<Integer, Integer> squares = new ConcurrentHashMap<>();
        Function<Integer, Integer> square = n -> squares.computeIfAbsent(n, k -> {
            computations.incrementAndGet();
            return Math.multiplyExact(k, k);
        });

        System.out.println("results=" + Stream.of(4, 4, 5, 4).map(square).toList());
        System.out.println("computations=" + computations.get());
        System.out.println("cache=" + new TreeMap<>(squares));

        ConcurrentHashMap<TaxInput, Long> taxCache = new ConcurrentHashMap<>();
        Function<TaxInput, Long> tax = input -> taxCache.computeIfAbsent(input,
                k -> Math.multiplyExact(k.subtotalCents(), k.taxBasisPoints()) / 10_000L);
        System.out.println("tax1=" + tax.apply(new TaxInput(10_000L, 800)));
        System.out.println("tax2=" + tax.apply(new TaxInput(10_000L, 800)));
        System.out.println("tax3=" + tax.apply(new TaxInput(10_000L, 500)));
        System.out.println("taxKeys=" + taxCache.size());

        AtomicInteger misses = new AtomicInteger();
        Map<String, String> missingCache = new ConcurrentHashMap<>();
        Function<String, String> nullable = k -> missingCache.computeIfAbsent(k, key -> {
            misses.incrementAndGet();
            return null;
        });
        System.out.println("missing1=" + nullable.apply("unknown"));
        System.out.println("missing2=" + nullable.apply("unknown"));
        System.out.println("missingCalls=" + misses.get());
        System.out.println("missingSize=" + missingCache.size());
    }
}
~~~

Biên dịch/chạy bằng JDK 17:

~~~bash
javac MemoizationDemo.java
java MemoizationDemo
~~~

**Stdout chính xác:**

~~~text
results=[16, 16, 25, 16]
computations=2
cache={4=16, 5=25}
tax1=800
tax2=800
tax3=500
taxKeys=2
missing1=null
missing2=null
missingCalls=2
missingSize=0
~~~

Phân tích:

- `Stream.of(4, 4, 5, 4)` có bốn phần tử, nhưng việc tính bình phương được thực hiện cho hai key phân biệt là 4 và 5. List đầu ra vẫn giữ bốn vị trí của nguồn.
- `computations` là **bộ đếm minh họa số lần thực hiện thuật toán**, không phải một tác dụng phụ nghiệp vụ bắt buộc. Nếu người gọi cần một side effect xảy ra ở mọi lời gọi, memoization **không tương đương**; chính ví dụ này cho thấy số lần gọi lõi bị thay đổi.
- `new TreeMap<>(squares)` dùng để in cache theo thứ tự key xác định; `ConcurrentHashMap` không cam kết thứ tự khi in trực tiếp.
- Hai `TaxInput(10_000L,800)` là hai record có giá trị bằng nhau, nên dùng cùng một cache key và nhận 800 cent. `TaxInput(10_000L,500)` tạo key khác, cho 500 cent. Nếu bỏ `taxBasisPoints` khỏi key thì có nguy cơ dùng sai thuế suất.
- `missingCache` không nhận giá trị `null` từ mapping function. Hai lần hỏi `"unknown"` đều thực hiện phép lookup thử, nên `missingCalls=2` và kích thước cache vẫn 0.

Mã đã được biên dịch với `javac --release 17` và chạy thực tế để kiểm chứng toàn bộ stdout. Nó không dựa vào thời gian đo, thứ tự thực thi song song hay giá trị random nên kết quả có thể so khớp chính xác.

## 5. Khóa cache phải biểu diễn đầy đủ đầu vào ảnh hưởng kết quả

Có thể xem cache như một ánh xạ:

~~~text
cacheKey -> cachedResult
~~~

Điều kiện cần: **nếu hai lời gọi dùng cùng cache key, thì chúng phải được phép dùng cùng kết quả** theo hợp đồng của ứng dụng. Câu này mạnh hơn việc hai đối số “trông giống nhau”.

Ví dụ tính giá cuối cùng cần các thuộc tính:

~~~java
record PriceKey(
        String sku,
        String currency,
        String customerTier,
        int discountBasisPoints,
        long priceCatalogVersion
) {}
~~~

Đây là **đoạn khai báo kiểu minh họa**. Việc cần từng trường phải dựa trên luật giá thực tế. Nếu bỏ `customerTier` mà giá ưu đãi phụ thuộc hạng khách hàng, cache sẽ đưa giá của hạng này cho hạng khác. Nếu bỏ `priceCatalogVersion` mà danh mục giá đổi, cache có thể lỗi thời.

### Record làm key

Java record tự sinh `equals`/`hashCode` dựa trên các component (với ngữ nghĩa của từng kiểu thành phần). Nó thường phù hợp để tạo value-based cache key:

~~~java
record TaxKey(long subtotalCents, int rateBasisPoints) {}

TaxKey first = new TaxKey(10_000L, 800);
TaxKey second = new TaxKey(10_000L, 800);

boolean same = first.equals(second); // true
~~~

Tuy nhiên, record **không tự deep-immutable hóa** các object mà component tham chiếu. Nếu record chứa `List` mutable, mảng `byte[]`, object cấu hình có trạng thái hoặc một collection thay đổi được, key vẫn có thể không ổn định.

### Vì sao key mutable nguy hiểm?

Ví dụ chống chỉ định:

~~~java
// Không dùng object có hashCode phụ thuộc trạng thái mutable làm Map key:
List<String> key = new ArrayList<>(List.of("A"));
Map<List<String>, Integer> cache = new HashMap<>();
cache.put(key, 10);
key.add("B");
// Hash/equality của key có thể đã thay đổi sau khi lưu.
// cache.get(key) không còn bảo đảm tìm được entry cũ đúng như mong muốn.
~~~

Đây là đoạn minh họa trong một phương thức với các import `List`, `ArrayList`, `Map`, `HashMap`. Sửa object làm khóa sau khi lưu có thể phá giả định của hash-based Map. Cách đúng là dùng value type bất biến hoặc snapshot key (ví dụ `List.copyOf` với phần tử immutable) trước khi lưu.

Đối với key chứa mảng, `equals` mặc định của mảng so sánh tham chiếu, không so nội dung; phải thiết kế value object/so sánh phần tử một cách tường minh nếu nội dung mảng là định danh logic.

## 6. Kết quả cache phải có hợp đồng an toàn về mutability

Giả sử hàm trả `List<String>`, và cache giữ trực tiếp List đó:

~~~java
Map<String, List<String>> cache = new HashMap<>();

List<String> result = cache.computeIfAbsent("team-A",
        key -> new ArrayList<>(List.of("An", "Binh")));
result.add("Chi"); // Đã thay đổi chính object đang nằm trong cache.
~~~

Đây là đoạn minh họa, không phải API khuyến nghị. Lời gọi sau cho cùng key có thể nhận List đã bị sửa. Nếu nghiệp vụ kỳ vọng mỗi lần gọi cho một danh sách độc lập, caching bằng cách trả **cùng tham chiếu mutable** là thay đổi hành vi.

Một số chiến lược:

- **Value immutable:** giữ dữ liệu trả về là `String`, `Integer`, record có component bất biến, hoặc cấu trúc bất biến thật sự. Trả lại cùng value object thường ít rủi ro hơn.
- **Unmodifiable snapshot:** nếu phần tử phù hợp, lưu `List.copyOf(computedList)`; không thể `add/remove` trên List trả về, nhưng vẫn cần xét các **phần tử bên trong** có mutable không.
- **Defensive copy:** giữ bản cache không sửa được hoặc bản riêng; mỗi lần gọi trả `new ArrayList<>(cached)` khi contract yêu cầu caller nhận collection mutable độc lập.
- **Deep copy khi cần:** với object graph có các node mutable, bản sao nông chưa bảo vệ dữ liệu. Cần thiết kế giá trị immutable hoặc sao chép theo domain.

Không tự thay API từ “trả List mutable mới mỗi lần” thành “trả List unmodifiable dùng chung” chỉ để tối ưu, nếu khách hàng có quyền sửa kết quả. **Tính tương thích hành vi** bao gồm cả khả năng sửa và danh tính object khi hợp đồng cho phép quan sát.

## 7. Side effect làm memoization không còn tương đương

Xét:

~~~java
int processPayment(String paymentId) {
    paymentGateway.charge(paymentId);
    auditLogger.record(paymentId);
    return 1;
}
~~~

Đây là **mã minh họa**, không phải chương trình độc lập. Nếu cache theo `paymentId` và bỏ qua các lần gọi tiếp theo, thao tác thanh toán hoặc ghi audit có thể **không diễn ra**. Với nghiệp vụ thanh toán, tránh tính lặp lại có thể là yêu cầu đúng, nhưng phải được thể hiện bằng **idempotency key, giao thức giao dịch và lưu trạng thái thanh toán**, không được ngầm thay bằng memoization một hàm có side effect.

Những side effect thường bị bỏ sót:

1. Ghi nhật ký audit hoặc tăng bộ đếm bắt buộc.
2. Cập nhật "last accessed" hoặc ghi telemetry có yêu cầu nghiệp vụ.
3. Phát sự kiện, gửi thông báo, gửi email.
4. Truy cập database với khóa đọc có tác dụng đồng bộ hoặc kiểm tra quyền tại thời điểm truy cập.
5. Đọc random, đồng hồ, số thứ tự tự tăng.
6. Thay đổi trạng thái nội bộ của object được gọi.

Ngay cả khi **giá trị trả về** giống nhau, giảm số lượt chạy cũng có thể đổi hành vi người dùng quan sát được. Cần tách phần tính toán thuần ra khỏi phần có side effect trước khi cache:

~~~text
Lời gọi nghiệp vụ
   |
   +--> Kiểm tra quyền / audit / thao tác bắt buộc (mỗi lần theo hợp đồng)
   |
   +--> Tính toán thuần expensive(input) (có thể memoize nếu điều kiện đúng)
   |
   +--> Trả kết quả theo contract
~~~

Không tự coi logging chỉ là “tác dụng phụ không quan trọng”: có hệ thống bắt buộc ghi log để tuân thủ. Việc có được phép giảm số lần log phải là quyết định nghiệp vụ.

## 8. Thời gian, dữ liệu ngoài và chính sách vô hiệu hóa

Memoization của pure function thường có thể sống cùng vòng đời function, nhưng nhiều cache nghiệp vụ chỉ hợp lệ **trong một khoảng thời gian hoặc phiên bản dữ liệu**.

Ví dụ:

~~~java
long stock(String sku) {
    return warehouseRepository.currentStock(sku);
}
~~~

Kết quả phụ thuộc trạng thái kho, nên cùng `sku` ở hai thời điểm có thể khác nhau. Cache vô thời hạn sẽ sai. Các chiến lược phổ biến:

| Chiến lược | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| Không cache | Phải luôn đọc giá trị mới nhất | Tốn chi phí nguồn |
| TTL (hết hạn sau thời gian) | Chấp nhận dữ liệu cũ trong một cửa sổ xác định | TTL không đảm bảo freshness tuyệt đối |
| Invalidate khi nguồn đổi | Có tín hiệu cập nhật đáng tin | Dễ bỏ sót hoặc trễ sự kiện |
| Version trong key | Dữ liệu có revision rõ | Key cũ vẫn tiêu thụ bộ nhớ |
| Cache theo request | Chỉ cần tái sử dụng trong một yêu cầu | Không chia sẻ cache giữa các request |
| Cache theo phiên / tenant | Tái sử dụng trong một phạm vi quyền rõ | Phải quản lý scope và giải phóng |
| Snapshot bất biến | Kết quả xác định bởi một revision ổn định | Cần cơ chế tạo/giữ snapshot |

**TTL là một thỏa thuận về độ cũ chấp nhận được**, không phải bằng chứng dữ liệu luôn đúng. Nếu tồn kho hoặc giá phải chính xác tại thời điểm ra quyết định giao dịch, một cache ngắn cũng có thể không đủ; phải dùng giao thức đọc/ghi và kiểm tra nhất quán phù hợp.

Khi đổi thuật toán, cấu hình thuế, locale hay version dữ liệu, cần xem entry cũ có còn hợp lệ không. Cập nhật code mà vẫn giữ cache persistent theo key cũ có thể dẫn tới sử dụng kết quả của một phiên bản thuật toán khác.

## 9. Cache scope và quyền truy cập: cùng key kỹ thuật chưa đủ

Giả sử hai người cùng hỏi `getDiscount("SKU-1")`, nhưng mức giảm phụ thuộc tư cách thành viên. Nếu cache chỉ theo SKU, người dùng khác có thể nhận thông tin sai hoặc nhạy cảm.

Điều kiện chia sẻ cache giữa caller:

- Kết quả có **thật sự độc lập với danh tính, quyền và tenant** không?
- Key có bao gồm mọi thuộc tính ngữ cảnh cần thiết không?
- Entry có thể tồn tại lâu hơn thời gian quyền truy cập còn hợp lệ không?
- Có yêu cầu kiểm tra authorization **mỗi lần gọi** không, kể cả khi cache hit?
- Cache có lưu dữ liệu cá nhân, token hoặc bí mật cần bảo vệ/vô hiệu hóa không?

Không nên đặt thông tin nhạy cảm trực tiếp vào khóa log, URL hay các công cụ quan sát chỉ để tiện cache. Có thể dùng ID nội bộ không tiết lộ bí mật và phân vùng cache phù hợp với mô hình quyền.

**Quan trọng:** cache hit không được trở thành đường vòng bỏ qua kiểm tra quyền truy cập nếu chính sách đòi kiểm tra quyền tại mỗi request. Tách bước authorization ra khỏi phần pure computation có thể cache.

## 10. Cache `null`, kết quả vắng mặt và ngoại lệ

### `ConcurrentHashMap` không cho giá trị null

`ConcurrentHashMap` không nhận `null` làm key hoặc value. Với `computeIfAbsent`, nếu mapping function trả `null` thì không tạo mapping mới:

~~~java
ConcurrentHashMap<String, String> cache = new ConcurrentHashMap<>();

String first = cache.computeIfAbsent("missing", key -> null);
String second = cache.computeIfAbsent("missing", key -> null);
// Cả hai đều null và key "missing" không được ghi vào Map.
~~~

Đây là đoạn minh họa, cần import `ConcurrentHashMap`. Nếu việc truy vấn không có kết quả rất tốn kém, hai lần gọi liên tiếp có thể vẫn phải tìm lại dữ liệu.

### Negative caching khi nghiệp vụ cho phép

Muốn biểu diễn rõ **“đã tìm và chắc chắn không có dữ liệu”**, có thể lưu một value không null bao bọc trạng thái:

~~~java
ConcurrentHashMap<String, Optional<String>> cache = new ConcurrentHashMap<>();

Optional<String> result = cache.computeIfAbsent(
        "missing",
        key -> Optional.empty()
);
~~~

Đoạn này cần import `ConcurrentHashMap` và `Optional`. `Optional.empty()` là một **object value không null**, nên có thể được lưu; nó biểu diễn kết quả không có giá trị. Nhưng negative caching cũng cần chính sách hết hạn: dữ liệu “không tồn tại” hôm nay có thể được tạo vào ngày mai.

### Ngoại lệ có được cache hay không?

Nếu mapping function trong `computeIfAbsent` ném `RuntimeException` hoặc `Error`, mapping không được tạo mới bởi lần gọi thất bại. Lần gọi sau có thể thử tính lại và ném lỗi tiếp.

Đối với lỗi transient (mạng timeout, rate limit), thử lại có thể hữu ích nhưng cũng có nguy cơ tạo tải lớn. Với lỗi deterministic (đầu vào không hợp lệ), có thể cân nhắc validation sớm hoặc cache một trạng thái lỗi **nếu hợp đồng cho phép**, thay vì vô tình thay đổi ngoại lệ.

Cần phân biệt:

- **Không có kết quả hợp lệ** — một trạng thái dữ liệu.
- **Không tìm thấy** — có thể là kết quả nghiệp vụ và có thể thay đổi theo thời gian.
- **Lỗi tạm thời** — không tương đương dữ liệu không có.
- **Lỗi vĩnh viễn của đầu vào** — nên được xác thực và biểu diễn rõ ràng.

Không cache mọi exception mãi mãi dưới một “giá trị lỗi” chung: điều đó có thể làm hệ thống không phục hồi sau sự cố tạm thời.

## 11. Đồng thời: cache an toàn không đồng nghĩa hàm được cache là an toàn

Dùng `ConcurrentHashMap` giúp quản lý mapping từ nhiều thread. Nó **không** làm một hàm có side effect trở nên thuần, không bảo vệ object mutable được trả ra và không sửa stale data.

Ví dụ:

~~~java
ConcurrentHashMap<String, MutableResult> cache =
        new ConcurrentHashMap<>();

MutableResult a = cache.computeIfAbsent("A", this::compute);
MutableResult b = cache.get("A");

// a và b có thể là cùng một đối tượng mutable.
~~~

Đây là **mã minh họa**, `MutableResult` và `compute` là thành phần do ứng dụng định nghĩa. Nếu nhiều thread sửa `a` và `b`, race có thể xuất hiện bên trong object dù map thread-safe.

### `computeIfAbsent` không phải cơ chế khóa toàn hệ thống

Trong một JVM, `ConcurrentHashMap.computeIfAbsent` cho cơ chế tính/ghi nguyên tử theo key theo hợp đồng. Nhưng nếu ứng dụng có nhiều instance hoặc process, mỗi instance có Map riêng; cùng một công việc vẫn có thể được tính đồng thời ở các node khác nhau.

Nếu **chỉ được phép một lần** thực hiện side effect trên toàn hệ thống, cần một giao thức idempotency/transaction/coordination tương ứng. Đừng dùng local memoization như thay thế cho tính đúng của giao dịch phân tán.

Với tác vụ asynchronous, cache `CompletableFuture<R>` có thể giúp chia sẻ công việc đang thực hiện trong một phạm vi, nhưng phải thiết kế xử lý hủy, timeout, lỗi, xóa entry thất bại và chia sẻ quyền sử dụng future. Đây là một bài toán lifecycle phức tạp hơn cache kết quả số nguyên.

### Parallel Stream và memoization

~~~java
List<Integer> values = source.parallelStream()
        .map(memoizedFunction)
        .toList();
~~~

Đây là đoạn minh họa với `source` và `memoizedFunction` được định nghĩa trước. Nếu cache dùng `HashMap` thường và lambda cùng cập nhật map, có nguy cơ data race. Dùng implementation thread-safe thích hợp khi nhiều thread cùng truy cập.

Cũng cần lưu ý Stream có **lazy evaluation** và có thể tối ưu việc không gọi một số behavioral parameter trong những pipeline thích hợp. Nếu người gọi yêu cầu đúng số lần thực thi một side effect, không nên gắn side effect vào `map` rồi dựa vào việc cache hay không để đảm bảo số lần gọi.

## 12. Kích thước cache, eviction và chi phí thực

Cache giúp tránh tính lại, nhưng cũng tiêu tốn:

- Bộ nhớ để lưu key, value và metadata.
- Chi phí hash, so sánh key, khóa/đồng bộ và quản lý thời gian sống.
- Thời gian xây dựng entry, giữ dữ liệu theo thời gian, áp lực garbage collector.
- Chi phí invalidation hoặc cập nhật đồng bộ với nguồn.

Một `ConcurrentHashMap` lưu mọi đầu vào từng thấy có thể tăng không giới hạn. Khi không gian key lớn (user ID, request ID, timestamp…), tỷ lệ tái sử dụng thấp, cache dễ **tốn nhiều hơn tiết kiệm**.

Những câu hỏi nên đặt trước khi bật cache:

1. Chi phí tính lại lớn đến mức nào?
2. Một key được gọi lặp lại bao nhiêu lần trong cửa sổ hữu ích?
3. Số key độc nhất và kích thước một entry là bao nhiêu?
4. Cache sống trong một request, một thread, một JVM hay cả hệ thống?
5. Kết quả có hạn sử dụng hay bị invalidation theo event/version không?
6. Khi bộ nhớ chật, có thể bỏ entry cũ rồi tính lại mà không phá hợp đồng không?
7. Cần đo latency, throughput, hit rate, miss rate và memory/GC như thế nào?

JDK `ConcurrentHashMap` là concurrent map, **không tự cung cấp TTL, giới hạn số entry hoặc chính sách eviction**. Nếu hệ thống cần những tính năng đó, có thể dùng thư viện caching chuyên dụng được đánh giá phù hợp hoặc tự thiết kế chính sách với kiểm thử đầy đủ; không nên tự thêm TTL vụng về vào các phép toán nhiều thread.

### Không cache chỉ vì sợ gọi hàm nhiều lần

Hàm rất rẻ như `n -> n + 1` có thể còn nhanh hơn chi phí hash/map lookup. Với phần tử hầu như không bao giờ lặp, memoization chỉ tăng memory. Hiệu quả cần dựa vào **tỷ lệ hit và chi phí tính thực tế**, không phải giả định “Map lookup luôn rẻ”.

## 13. Kiểm thử tính tương đương hành vi

Trước khi chấp nhận cache, hãy định nghĩa rõ những gì **phải giống** giữa phiên bản gốc và phiên bản memoized. Các nhóm test có giá trị:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Cùng đầu vào nhiều lần | Giá trị trả về đúng, bỏ qua tính lại chỉ khi được phép |
| Hai đầu vào khác nhau | Không bị chung key ngoài ý muốn |
| Nhiều record có giá trị bằng nhau | `equals/hashCode` khiến chúng dùng cùng key hợp lệ |
| Đầu vào mutable | Không bị thay đổi sau khi đưa vào cache hoặc có snapshot đúng |
| Kết quả mutable | Caller không thể phá cache hoặc có bản sao độc lập theo contract |
| Cập nhật dữ liệu nguồn | Invalidation/version/TTL áp dụng đúng |
| Không tìm thấy | Policy về negative caching rõ ràng |
| Mapping function trả null | Không nhầm với một entry đã cache |
| Mapping function ném lỗi | Không che lỗi hoặc cache sai trạng thái |
| Concurrent callers | Không có race trong map và value, kết quả đúng |
| Quyền/tenant khác nhau | Không dùng lại dữ liệu vượt phạm vi cho phép |
| Dữ liệu lớn/key nhiều | Không tăng memory vô hạn |
| Đổi cấu hình/thuật toán | Entry cũ không được dùng khi đã hết hiệu lực |

Một quy trình test tốt có thể bao gồm:

1. Chạy phép tính gốc và phép tính cache trên bộ đầu vào giống nhau, so sánh **giá trị và ngoại lệ theo hợp đồng**.
2. Gọi lại cùng key nhiều lần; dùng instrumentation không ảnh hưởng kết quả nghiệp vụ để quan sát cache hit/miss.
3. Chủ động thay đổi từng thuộc tính ảnh hưởng kết quả để kiểm tra key có đủ chiều dữ liệu.
4. Mô phỏng cập nhật cấu hình/nguồn và kiểm tra invalidation.
5. Với đồng thời, chạy test nhiều thread và các công cụ phát hiện race thích hợp; kết quả chạy một lần thành công không phải bằng chứng an toàn.
6. Đo bằng benchmark có warm-up, dữ liệu đại diện; nếu dùng JMH, tránh dead-code elimination và đo cả chi phí cấp phát/GC.

**Đừng coi việc đầu ra của một lần chạy bằng nhau là chứng minh cache không đổi hành vi.** Trạng thái bảo mật, thời điểm cập nhật, lỗi, object identity và tác dụng phụ có thể chỉ lộ ra sau nhiều request hoặc giữa nhiều thread.

## 14. Một số mẫu thiết kế an toàn hơn

### Mẫu A: tách pure computation khỏi I/O

~~~text
Lớp service:
  1. Đọc dữ liệu mới nhất / kiểm tra quyền theo nghiệp vụ.
  2. Chuyển thành input snapshot bất biến.
  3. Gọi pureCalculation(snapshot), có thể memoize với key đầy đủ.
  4. Ghi audit / phát sự kiện nếu mỗi request bắt buộc phải làm.
~~~

Phần tính thuần có thể cache mà không bỏ qua các bước cần chạy theo hợp đồng service. Nếu snapshot đổi phiên bản, key hoặc invalidation phải thay đổi tương ứng.

### Mẫu B: request-scoped cache

Trong một request duy nhất, cùng một phép tính hay lookup bất biến trong phạm vi request có thể dùng Map cục bộ, giảm nguy cơ stale giữa các request và giảm nhu cầu đồng bộ nhiều thread. Nhưng nếu request có các công việc chạy song song, Map cục bộ vẫn có thể cần thread-safety tùy cách chia sẻ.

### Mẫu C: versioned key

~~~java
record CalculationKey(String productId, long ruleVersion, int quantity) {}
~~~

Khi `ruleVersion` đổi, key mới không truy cập nhầm entry cũ. Tuy nhiên, entry cũ cần được dọn để tránh memory leak; versioning không tự là eviction.

### Mẫu D: kết quả immutable hoặc defensive copy

Cache giữ immutable value. Nếu caller cần List mutable mới, trả một bản copy sau khi đọc cache. Cần xét cả nội dung phần tử; `new ArrayList<>(cached)` chỉ sao chép **các tham chiếu**, không deep-copy từng object.

### Mẫu E: không memoize ở hot path nếu lookup đắt hơn phép tính

Với phép toán đơn giản và dữ liệu hầu như duy nhất, việc không có cache là một lựa chọn chủ động và đúng. Có thể chỉ tối ưu khi có profile và test thể hiện lợi ích.

## 15. Các lỗi phổ biến và cách nhận diện

**Cache một hàm phụ thuộc thời gian:** `Instant.now()`, ngày hệ thống, “giá hiện hành” hay “trạng thái hiện tại” không ổn định theo key cũ. Cần đưa thời điểm/snapshot vào mô hình hoặc chấp nhận TTL có giới hạn rõ.

**Quên một tham số quyết định kết quả:** Chỉ cache theo `sku` nhưng giá còn phụ thuộc currency, khách hàng và version bảng giá. Khóa cache thiếu trường dẫn đến trả sai kết quả giữa các ngữ cảnh.

**Dùng key mutable:** Sửa object sau khi đưa vào hash map có thể khiến entry không còn tìm được. Dùng key bất biến có `equals/hashCode` ổn định.

**Trả cùng một mutable object:** Caller A sửa List đã cache khiến Caller B nhận dữ liệu biến đổi. Ưu tiên immutable value hoặc defensive copy theo contract.

**Nhầm null với chưa tính:** `computeIfAbsent` không lưu null trong `ConcurrentHashMap`. Nếu muốn nhớ “không tìm thấy”, dùng một value biểu diễn rõ trạng thái vắng mặt và chính sách expiration.

**Cache mọi exception:** Một timeout tạm thời không nên biến thành “không có dữ liệu” vĩnh viễn. Cần phân loại lỗi và thiết kế retry/backoff.

**Dùng `HashMap` cùng với `parallelStream()`:** Nhiều thread cập nhật map thường có race. Dùng đồng bộ hoặc `ConcurrentHashMap` đúng hợp đồng, đồng thời xem xét trạng thái của value.

**Gắn cache vào hàm có side effect:** Gửi email, thanh toán, audit hoặc increment counter nghiệp vụ có thể cần xảy ra mỗi lượt; cache hit bỏ qua chúng. Hãy tách tác dụng phụ khỏi pure calculation.

**Cache toàn cục không có giới hạn:** Dữ liệu đầu vào có cardinality lớn có thể làm heap tăng mãi. Thiết kế quota, eviction, TTL hoặc scope ngắn hơn.

**Cho rằng kết quả deterministic luôn cache được:** Một hàm có thể luôn trả `true` nhưng đồng thời ghi audit mỗi lần. Giá trị deterministic không đủ; phải xét toàn bộ hành vi quan sát được.

**Dùng cache để "chữa" kết quả không thuần:** Nếu hàm trả dữ liệu khác nhau do phụ thuộc ẩn, cache chỉ che giấu vấn đề. Trước tiên xác định phụ thuộc và contract dữ liệu.

## 16. Checklist quyết định trước khi lưu kết quả hàm

| Câu hỏi | Nếu câu trả lời là "không" hoặc "chưa rõ" |
| --- | --- |
| Hàm có đầu ra ổn định với đầy đủ input? | Chưa nên cache theo key hiện tại |
| Hàm không có side effect bắt buộc? | Tách phần thuần; giữ side effect đúng mỗi lần |
| Key bao gồm mọi thuộc tính và version ảnh hưởng kết quả? | Bổ sung key hoặc cơ chế invalidation |
| Key bất biến, `equals/hashCode` ổn định? | Chụp snapshot/đổi kiểu key |
| Value có thể chia sẻ an toàn? | Trả immutable value hoặc defensive copy |
| Có chính sách cho `null` và missing? | Thiết kế value bao trạng thái |
| Có chính sách cho exception/retry? | Phân biệt lỗi transient, permanent và lỗi input |
| Cache có scope và quyền truy cập đúng? | Phân vùng theo tenant/request hoặc không cache |
| Cache đáp ứng thread-safety cần thiết? | Chọn Map/concurrency model phù hợp |
| Có quy tắc hết hạn và giới hạn bộ nhớ? | Bổ sung lifecycle/eviction |
| Có dữ liệu đo chứng minh lợi ích? | Cân nhắc không cache |

**Kết luận:** Memoization là một kỹ thuật rất hữu ích khi **phần tính toán thuần, đầu vào đầy đủ và bất biến, kết quả có thể tái sử dụng**. Để tránh làm sai hành vi, không được chỉ dựa vào việc hai lời gọi có cùng tham số tường minh. Phải kiểm tra **phụ thuộc ẩn, tác dụng phụ, object mutability, quyền truy cập, dữ liệu lỗi thời, `null`/ngoại lệ, đồng thời và vòng đời bộ nhớ**. Chỉ lưu kết quả khi thay phép tính bằng cache hit vẫn đáp ứng đúng hợp đồng của hệ thống.