# Chi phí tra cứu và quản lý bộ nhớ đệm annotation

## 1. Cache giải quyết phần công việc nào?

Một công cụ có thể lặp lại cùng thao tác cho hàng nghìn yêu cầu: tìm phương thức, đọc annotation, lấy thuộc tính, kiểm tra cấu hình, rồi dựng thông tin xử lý. Nếu cấu trúc lớp và chính sách đọc không đổi, phần **phân tích metadata** này có thể được dùng lại.

Không nên gom mọi chi phí vào một câu “reflection luôn chậm”. Cần tách các bước:

| Công việc | Ví dụ | Có thể lưu lại gì? |
| --- | --- | --- |
| Tìm phần tử | `getDeclaredMethod`, duyệt `getDeclaredMethods` | Đối tượng mô tả hoặc kết quả phân tích |
| Đọc annotation | `getDeclaredAnnotation` | Annotation hoặc metadata đã chuyển đổi |
| Diễn giải | Kiểm tra đường dẫn, loại bỏ mục không phù hợp, sắp xếp | Kế hoạch xử lý đã xác thực |
| Thực thi với dữ liệu hiện tại | Đọc giá trị đối tượng, kiểm tra yêu cầu | Thường phải làm lại theo từng đầu vào |

Các phương thức reflection có hợp đồng về kết quả, không hứa một chi phí thời gian cố định cho mọi JVM. Cache của ứng dụng cũng không thay đổi hợp đồng đọc annotation. [API AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

Một cache hữu ích thường lưu **kết quả phân tích phù hợp mục đích sử dụng**, thay vì chỉ thêm một bản sao của từng lời gọi lấy annotation. Ví dụ, lưu danh sách tuyến xử lý đã kiểm tra và sắp xếp có thể tránh cả vòng quét lẫn bước diễn giải.

## 2. Đổi thời gian lấy bộ nhớ và độ phức tạp

Gọi `S` là chi phí phân tích một lớp, `L` là chi phí lấy kết quả từ cache, `N` là số lần cần metadata. Với mô hình đơn giản một luồng và không vô hiệu hóa:

```text
Không cache:             N × S
Có cache sau lần đầu:    S + N × L
```

Đây là mô hình suy luận, không phải số đo. Nó chưa tính cấp phát, tranh chấp luồng, thu gom rác và chi phí lưu metadata. Nếu mỗi lớp chỉ được dùng một lần, cache có thể giữ thêm dữ liệu mà gần như không tiết kiệm công việc. Nếu ứng dụng gặp nhiều lớp động khác nhau, số mục cũng có thể tăng dù mỗi lớp chỉ lưu một lần.

Trước khi tối ưu, hãy xác định:

- Phần phân tích nào đang lặp?
- Có bao nhiêu lớp/phần tử khác nhau?
- Metadata được dùng lại bao nhiêu lần?
- Kết quả phụ thuộc thêm vào cấu hình hay phiên bản chính sách nào?
- Ai sở hữu cache và khi nào cache hết cần thiết?

## 3. Khóa cache phải giữ đúng ngữ nghĩa tra cứu

### Dùng Class thay vì chỉ dùng tên lớp

Hai lớp có cùng tên nhị phân nhưng được định nghĩa bởi hai class loader khác nhau là hai kiểu khác nhau tại lúc chạy. Khóa chỉ là `"com.example.Service"` có thể trộn metadata của hai bản triển khai. Với dữ liệu theo lớp, `Class<?>` là lựa chọn thể hiện được danh tính lúc chạy. [JVMS §5.3](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3)

Nếu lưu theo phương thức, chỉ tên `"handle"` chưa đủ vì phương thức có thể nạp chồng. Cần giữ chữ ký và lớp khai báo, hoặc dùng đối tượng `Method` theo thiết kế phù hợp.

### Chính sách đọc cũng là một phần của khóa

Kết quả `getAnnotation`, `getDeclaredAnnotation` và `getAnnotationsByType` có thể khác nhau. Nếu một cache trộn kết quả các chế độ này, khóa phải phân biệt chế độ. Cũng cần phân biệt đọc annotation khai báo với đọc annotation trên kiểu sử dụng. [Các chế độ đọc AnnotatedElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)

Một cách giảm độ phức tạp là để **mỗi đối tượng cache có một chính sách cố định**: cùng kiểu annotation, cùng quy tắc kế thừa và cùng thuật toán phân tích. Khi chính sách khác, dùng cache khác thay vì ngầm tái sử dụng mục cũ.

### Lưu cả kết quả “không có”

Nếu một lớp không có annotation phù hợp mà lần nào cũng bị quét lại, cache chưa giải quyết trường hợp này. Có thể lưu danh sách rỗng hay một giá trị đại diện rõ nghĩa.

Với `ConcurrentHashMap`, không dùng `null` làm giá trị vì map không chấp nhận nó; hàm `computeIfAbsent` trả `null` cũng không tạo mục. Khi cần lưu kết quả không tìm thấy, có thể dùng `Optional` hoặc một đối tượng kết quả riêng. [API ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

## 4. Ví dụ ClassValue: phân tích một lần và tái sử dụng

`ClassValue<T>` gắn một giá trị được tính khi cần với một `Class`. Nó thích hợp cho dữ liệu có đơn vị khóa là lớp; không cần tự dựng map toàn cục theo tên lớp. [API ClassValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassValue.html)

Ví dụ dưới đây chỉ phân tích các phương thức khai báo trực tiếp có `@Endpoint`, dựng danh sách metadata bất biến và sắp xếp theo chữ ký. Nó không điều phối lời gọi phương thức, không xử lý kế thừa và không đo thời gian.

Lưu thành **AnnotationCacheDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class AnnotationCacheDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Endpoint {
        String value();
        int priority() default 0;
    }

    public record EndpointInfo(
            String signature, String path, int priority) {
    }

    public static final class EndpointCache {
        private final AtomicInteger scanAttempts =
                new AtomicInteger();

        private final ClassValue<List<EndpointInfo>> plans =
                new ClassValue<>() {
                    @Override
                    protected List<EndpointInfo> computeValue(
                            Class<?> type) {
                        scanAttempts.incrementAndGet();
                        return scan(type);
                    }
                };

        public List<EndpointInfo> describe(Class<?> type) {
            return plans.get(type);
        }

        public void invalidate(Class<?> type) {
            plans.remove(type);
        }

        public int scanAttempts() {
            return scanAttempts.get();
        }

        private static List<EndpointInfo> scan(Class<?> type) {
            List<EndpointInfo> result = new ArrayList<>();

            for (Method method : type.getDeclaredMethods()) {
                if (method.isSynthetic() || method.isBridge()) {
                    continue;
                }

                Endpoint endpoint =
                        method.getDeclaredAnnotation(Endpoint.class);
                if (endpoint == null) {
                    continue;
                }

                if (!endpoint.value().startsWith("/")) {
                    throw new IllegalStateException(
                            "path must start with / on "
                                    + method.getName());
                }

                String parameters = Stream.of(
                            method.getParameterTypes())
                        .map(Class::getTypeName)
                        .collect(Collectors.joining(","));

                String signature = method.getName()
                        + "(" + parameters + ")";

                result.add(new EndpointInfo(
                        signature,
                        endpoint.value(),
                        endpoint.priority()));
            }

            result.sort(Comparator.comparing(
                    EndpointInfo::signature));
            return List.copyOf(result);
        }
    }

    static class Service {
        @Endpoint(value = "/orders", priority = 2)
        void list() {
        }

        @Endpoint("/orders/detail")
        void detail(String id) {
        }
    }

    static class EmptyService {
        void health() {
        }
    }

    public static void main(String[] args) {
        EndpointCache cache = new EndpointCache();

        List<EndpointInfo> first =
                cache.describe(Service.class);
        for (EndpointInfo info : first) {
            System.out.println(info.signature()
                    + " -> " + info.path()
                    + ",priority=" + info.priority());
        }
        System.out.println("afterFirst=" + cache.scanAttempts());

        List<EndpointInfo> second =
                cache.describe(Service.class);
        System.out.println("sameSnapshot=" + (first == second));
        System.out.println("afterSecond=" + cache.scanAttempts());

        System.out.println("emptySize="
                + cache.describe(EmptyService.class).size());
        cache.describe(EmptyService.class);
        System.out.println("afterEmptyTwice="
                + cache.scanAttempts());

        cache.invalidate(Service.class);
        cache.describe(Service.class);
        System.out.println("afterInvalidate="
                + cache.scanAttempts());

        try {
            second.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("modifiable=false");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 AnnotationCacheDemo.java
java AnnotationCacheDemo
```

Kết quả chuẩn trong lần chạy một luồng này:

```text
detail(java.lang.String) -> /orders/detail,priority=0
list() -> /orders,priority=2
afterFirst=1
sameSnapshot=true
afterSecond=1
emptySize=0
afterEmptyTwice=2
afterInvalidate=3
modifiable=false
```

Giải thích:

- Lần đầu với `Service` quét metadata; lần thứ hai lấy cùng kết quả đã gắn với lớp.
- `EmptyService` tạo danh sách rỗng. Lần đọc tiếp không quét lại.
- `invalidate(Service.class)` bỏ liên kết của lớp đó; lần đọc sau phân tích lại.
- `List.copyOf` cùng record chỉ chứa chuỗi và số tạo kết quả không cho bên gọi sửa.
- `priority` được lưu nhưng thứ tự ví dụ cố ý theo chữ ký, không theo priority.
- Bộ đếm chỉ ghi nhận số lần hàm phân tích được gọi, **không chứng minh hệ số tăng tốc**.

Cache không giữ đối tượng nghiệp vụ `Service` và không lưu trạng thái của một yêu cầu. Dữ liệu trong `EndpointInfo` là bản chiếu metadata phục vụ mục đích cụ thể.

## 5. Đồng thời: không giả định computeValue chỉ chạy đúng một lần

Khi nhiều luồng cùng gọi `ClassValue.get` cho một lớp chưa có giá trị, có thể có nhiều lần gọi `computeValue` cạnh tranh; một giá trị được liên kết và trả về theo hợp đồng của `ClassValue`. Vì vậy không dùng hàm tính như một điểm thực hiện tác dụng phụ cần “đúng một lần”, chẳng hạn đăng ký dịch vụ bên ngoài. [ClassValue: tính giá trị khi cạnh tranh](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassValue.html)

Trong ví dụ, quét cùng một lớp nhiều lần vẫn tạo kết quả tương đương. `AtomicInteger` chỉ là công cụ quan sát, nên giá trị bộ đếm khi có cạnh tranh không được khẳng định bằng stdout một luồng.

Cần giữ hai điều riêng:

- Cơ chế lấy/lưu mục phải đúng khi nhiều luồng dùng chung.
- Đối tượng kết quả cũng phải an toàn để chia sẻ.

Dùng một map an toàn theo luồng không tự làm một `ArrayList` giá trị có thể thay đổi trở nên an toàn. Xây hoàn chỉnh kết quả trước khi đưa vào cache, rồi ưu tiên metadata bất biến. Nếu metadata chứa mảng hay collection lồng, cần bảo vệ cả phần bên trong; bọc danh sách ngoài là chưa đủ.

Nếu hàm tính ném lỗi, không nên coi lớp đó đã được lưu thành công. Với lỗi cấu hình cố định, ứng dụng có thể chọn phát hiện sớm khi khởi động; không âm thầm trả kế hoạch rỗng để làm biến mất lỗi.

## 6. Quản lý bộ nhớ và vòng đời class loader

Cache tồn tại lâu có thể giữ `Class`, `Method`, `Field`, kiểu annotation hoặc các đối tượng liên quan đến class loader. Ví dụ suy luận đường tham chiếu cần xem xét:

```text
đối tượng sống lâu
    → map cache
    → khóa Class hoặc giá trị Method
    → lớp và class loader liên quan
```

Nếu ứng dụng có nạp lại plugin hoặc tạo nhiều class loader, một map toàn cục không dọn mục có thể giữ những cấu trúc đáng lẽ đã hết cần thiết. Việc dỡ lớp phụ thuộc vòng đời class loader và không được bảo đảm xảy ra ngay tại một thời điểm cụ thể. [JLS §12.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7)

| Cách quản lý | Điểm cần quyết định |
| --- | --- |
| Cache thuộc một ứng dụng/plugin | Bỏ toàn bộ cache khi chủ sở hữu kết thúc; tránh để nơi sống lâu hơn giữ nó |
| `ConcurrentHashMap<Class<?>, ...>` | Tự quản lý số mục và việc xóa; map giữ tham chiếu mạnh |
| `ClassValue<Metadata>` | Phù hợp metadata gắn với lớp; không cần tự giữ một bảng khóa lớp toàn cục |
| Cache có giới hạn số mục | Quyết định dung lượng, đẩy mục và chấp nhận tính lại |

`ClassValue` không phải bộ cache có giới hạn dung lượng theo LRU hay hết hạn theo thời gian. Nó cũng không sửa những tham chiếu khác do ứng dụng giữ bên ngoài. Nếu sao chép mọi metadata đã đọc vào một danh sách toàn cục khác, vẫn cần xem lại vòng đời danh sách đó.

### Vì sao WeakHashMap không tự giải quyết mọi vấn đề?

`WeakHashMap` giữ khóa yếu nhưng giữ giá trị bằng tham chiếu mạnh. Nếu giá trị trỏ ngược về khóa, chẳng hạn metadata chứa một `Method` thuộc chính lớp khóa, đường tham chiếu qua giá trị có thể giữ khóa sống. Map này cũng không tự đồng bộ hóa cho nhiều luồng. [API WeakHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/WeakHashMap.html)

Vì vậy, thay tên kiểu map chưa đủ; phải kiểm tra cả đồ thị tham chiếu và cách dùng đồng thời. Không viết kiểm thử khẳng định mục yếu chắc chắn biến mất ngay sau một lời gọi `System.gc()`: thời điểm thu gom không phải hợp đồng của cache.

## 7. Khi nào cần vô hiệu hóa cache?

Với lớp đã nạp và chính sách phân tích cố định, metadata thường được tái sử dụng suốt vòng đời đó. Tuy nhiên, kết quả dẫn xuất có thể phụ thuộc cấu hình thay đổi ngoài lớp.

Ví dụ, nếu đường dẫn annotation được ghép với một tiền tố cấu hình, chỉ khóa bằng `Class` không đủ khi tiền tố đổi. Có thể:

- Chỉ cache phần metadata thuần từ lớp; ghép cấu hình hiện tại ở bước sau.
- Tạo cache mới cho mỗi phiên bản chính sách/cấu hình.
- Vô hiệu hóa mục liên quan theo cơ chế rõ ràng của ứng dụng.

Trong ví dụ, `remove` chỉ bỏ liên kết cho những lần lấy tiếp theo; các bên đã giữ `first` hay `second` vẫn giữ bản metadata cũ. Nó không biến đổi các bản đã phát ra và không chờ mọi luồng dừng dùng bản cũ. Nếu cần chuyển đổi chính sách đồng bộ trên toàn hệ thống, ứng dụng phải thiết kế ranh giới phiên bản riêng.

Không thêm thời gian hết hạn tùy ý chỉ vì cache “nên có TTL”. Với dữ liệu cố định theo lớp, TTL có thể làm lặp phân tích mà không cải thiện tính đúng. Ngược lại, không giữ kết quả chứa cấu hình thay đổi mãi mãi chỉ vì annotation gốc không đổi.

## 8. Đo lợi ích đúng câu hỏi

Đo một vòng lặp bằng `System.nanoTime()` rồi kết luận tỷ lệ tăng tốc dễ bị ảnh hưởng bởi khởi động JVM, tối ưu JIT, mã không được dùng và thứ tự chạy các trường hợp.

Khi cần microbenchmark, JMH là công cụ OpenJDK dành cho việc xây dựng và chạy benchmark JVM. Hãy dùng cấu hình benchmark đúng thay vì sao chép số liệu từ một máy khác. [Dự án OpenJDK JMH](https://github.com/openjdk/jmh)

Một thiết kế đo nên tách:

1. **Lần đầu:** tính metadata cho lớp chưa có mục.
2. **Đã có mục:** lấy và sử dụng metadata đã tính.
3. **Luồng xử lý đầy đủ:** so sánh cùng hành vi với/không cache.
4. **Nhiều lớp:** xem bộ nhớ khi số lớp tăng.
5. **Nhiều luồng:** xem ảnh hưởng cạnh tranh lúc tạo mục và lúc đọc.

Đảm bảo kết quả benchmark được sử dụng để tránh mã bị tối ưu bỏ. Có warmup, các lần chạy độc lập và thông tin JDK/môi trường. Báo cả thời gian, lượng cấp phát và điều kiện đo khi chúng có liên quan; không diễn giải bộ đếm quét của ví dụ thành thông lượng.

### Tự kiểm tra

1. Bỏ dòng `invalidate` trong chương trình: bộ đếm cuối thay đổi thế nào?
2. Gọi `describe(EmptyService.class)` nhiều lần: vì sao danh sách rỗng cũng đáng được cache?
3. Thêm phương thức nạp chồng `list(String)`: tại sao chỉ tên `list` không đủ làm danh tính phương thức?
4. Để hai cache có chính sách đọc khác nhau dùng chung một map chỉ khóa bằng lớp: mô tả trường hợp kết quả bị trộn sai.
5. Nếu cache trả `ArrayList` có thể sửa, một bên gọi xóa phần tử sẽ ảnh hưởng những bên nào?
6. Nếu metadata chứa trạng thái yêu cầu hiện tại thay vì cấu hình cố định, vì sao việc chia sẻ nó giữa các yêu cầu làm sai kết quả?
