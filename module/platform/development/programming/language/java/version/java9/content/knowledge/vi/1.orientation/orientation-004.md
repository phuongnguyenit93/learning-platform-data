# Kiến thức cần có về generic, Stream, ngoại lệ và đa luồng

Bốn chủ đề này bổ trợ cho nhau trong Java hiện đại: generic giúp biểu diễn kiểu dữ liệu an toàn; Stream giúp xử lý dữ liệu theo pipeline; ngoại lệ giúp truyền đạt và xử lý lỗi có cấu trúc; đa luồng giúp thực hiện nhiều tác vụ đồng thời mà vẫn giữ dữ liệu nhất quán.

**Phạm vi phiên bản:** Các khái niệm và ví dụ chính dùng Java 17 trở lên. Phần virtual thread được đánh dấu riêng vì cần Java 21 trở lên. Nội dung tập trung vào API và cách dùng vẫn phù hợp trong các ứng dụng Java hiện nay.

## Mục tiêu học tập

Sau bài này, bạn cần có thể:

- Khai báo và sử dụng generic class, generic method, bounded type và wildcard.
- Chọn đúng giữa \`? extends T\` và \`? super T\`, hiểu nguyên tắc PECS.
- Đọc, tạo và tối ưu một Stream pipeline; biết khi nào không nên dùng parallel stream.
- Phân biệt checked exception, unchecked exception và Error; thiết kế cách xử lý lỗi có ngữ cảnh.
- Quản lý tác vụ đồng thời bằng ExecutorService, Future và CompletableFuture.
- Nhận diện race condition, vấn đề visibility, deadlock và chọn cơ chế đồng bộ phù hợp.

## 1. Generic: an toàn kiểu dữ liệu và tái sử dụng

### 1.1. Generic giải quyết vấn đề gì?

Generic cho phép một lớp, interface hoặc method làm việc với nhiều kiểu dữ liệu mà vẫn giữ kiểm tra kiểu tại thời điểm biên dịch. Thay vì lưu mọi thứ dưới dạng Object rồi ép kiểu thủ công, ta khai báo kiểu tham số như T, E, K hoặc V.

Ví dụ:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
~~~

Trình biên dịch biết phần tử của danh sách là String. Nếu thêm một Integer vào danh sách, lỗi được phát hiện khi biên dịch thay vì chờ đến lúc chạy. Generic cũng làm rõ hợp đồng của API: List<String> biểu thị danh sách chuỗi, Map<Long, User> biểu thị ánh xạ từ mã Long sang User.

Tên tham số kiểu chỉ là quy ước, không phải từ khóa bắt buộc:

- T: một kiểu tổng quát.
- E: phần tử trong collection.
- K và V: key và value.
- R: kiểu kết quả.

### 1.2. Generic class và generic method

Generic class nhận kiểu tại lúc tạo đối tượng. Ví dụ, Box<T> có thể chứa một giá trị thuộc kiểu T:

~~~java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = Objects.requireNonNull(value);
    }

    T get() {
        return value;
    }
}

Box<String> textBox = new Box<>("Java");
Box<Integer> numberBox = new Box<>(21);
~~~

Mỗi đối tượng sử dụng kiểu cụ thể riêng. Với Box<String>, phương thức get() trả về String mà không cần ép kiểu.

Generic method khai báo tham số kiểu ngay trước kiểu trả về:

~~~java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("values must not be empty");
    }
    return values.get(0);
}

String language = first(List.of("Java", "Kotlin"));
Integer number = first(List.of(10, 20, 30));
~~~

Trình biên dịch thường suy luận T từ đối số, vì vậy không cần truyền kiểu một cách tường minh trong lời gọi thông thường.

### 1.3. Bounded type parameter

Khi một thuật toán cần các khả năng cụ thể của kiểu, hãy giới hạn tham số kiểu bằng extends:

~~~java
static <T extends Number> double sum(List<T> values) {
    return values.stream()
            .mapToDouble(Number::doubleValue)
            .sum();
}
~~~

T trong ví dụ phải là Number hoặc lớp con của Number, nên có thể gọi doubleValue(). Nếu cần nhiều giới hạn, dùng dấu &: ví dụ T extends Number & Comparable<T>. Trong khai báo nhiều giới hạn, nếu có lớp thì lớp phải đứng trước các interface.

### 1.4. Wildcard và nguyên tắc PECS

Generic trong Java có tính bất biến (invariant). List<Integer> không phải là kiểu con của List<Number>, dù Integer là kiểu con của Number. Nếu cho phép gán như vậy, mã có thể thêm một Double vào danh sách vốn chỉ dành cho Integer.

Wildcard giúp API chấp nhận một họ kiểu liên quan:

- List<? extends Number>: danh sách cung cấp giá trị thuộc Number hoặc lớp con. Có thể đọc phần tử như Number, nhưng không thể thêm một giá trị Number tùy ý vì kiểu cụ thể bên dưới chưa biết.
- List<? super Integer>: danh sách nhận Integer hoặc lớp cha của Integer. Có thể thêm Integer; khi đọc, kiểu an toàn chung chỉ là Object.
- List<?>: danh sách của một kiểu chưa biết. Có thể đọc như Object; không thể thêm phần tử thông thường.

PECS là cách nhớ nhanh: Producer Extends, Consumer Super. Dùng extends khi tham số chủ yếu cung cấp dữ liệu cho hàm; dùng super khi tham số chủ yếu nhận dữ liệu từ hàm.

~~~java
static double sumNumbers(List<? extends Number> values) {
    return values.stream().mapToDouble(Number::doubleValue).sum();
}

static void addDefaultScores(List<? super Integer> destination) {
    destination.add(80);
    destination.add(90);
}
~~~

sumNumbers có thể nhận List<Integer>, List<Double> hoặc List<BigDecimal>. addDefaultScores có thể nhận List<Integer>, List<Number> hoặc List<Object>.

### 1.5. Type erasure và giới hạn cần biết

Java dùng type erasure: phần lớn thông tin tham số kiểu được xóa khi biên dịch, sau đó thay bằng kiểu giới hạn hoặc Object. Điều này giúp generic tương thích với hệ sinh thái Java trước khi generic xuất hiện, nhưng dẫn đến một số giới hạn:

- Không thể tạo đối tượng trực tiếp bằng new T() vì JVM không biết T cụ thể ở thời điểm chạy.
- Không thể dùng kiểu nguyên thủy làm tham số kiểu; dùng Integer, Long, Double và các wrapper tương ứng.
- Không thể kiểm tra instanceof List<String>; có thể kiểm tra instanceof List<?> rồi kiểm tra từng phần tử nếu nghiệp vụ yêu cầu.
- Không thể tạo trực tiếp mảng generic như new T[10].
- Không thể overload hai method chỉ khác nhau ở tham số kiểu đã bị xóa nếu chữ ký sau erasure trùng nhau.

Tránh raw type như List không có tham số kiểu và tránh ép kiểu unchecked. Nếu cần tạo đối tượng hoặc kiểm tra kiểu lúc chạy, hãy truyền Class<T>, factory hoặc một abstraction có kiểu rõ ràng vào API.

## 2. Stream API: xử lý dữ liệu theo pipeline

### 2.1. Cấu trúc một Stream pipeline

Stream mô tả một chuỗi thao tác trên nguồn dữ liệu. Một pipeline thường có ba phần:

1. **Nguồn:** Collection, mảng, generator hoặc một Stream khác.
2. **Intermediate operations:** thao tác trung gian như filter, map, flatMap, distinct, sorted, limit. Chúng thường lazy, nghĩa là chưa chạy cho đến khi có terminal operation.
3. **Terminal operation:** thao tác kết thúc như toList, collect, count, reduce, forEach, findFirst hoặc anyMatch.

Ví dụ:

~~~java
List<String> result = products.stream()
        .filter(product -> product.price() >= 100)
        .map(Product::name)
        .sorted()
        .toList();
~~~

Pipeline chỉ được thực thi khi gọi toList(). Stream không phải Collection và không lưu trữ dữ liệu. Một Stream đã được tiêu thụ bởi terminal operation thì không được dùng lại; nếu cần xử lý lần nữa, hãy tạo Stream mới từ nguồn.

### 2.2. Các thao tác thường dùng

| Thao tác | Mục đích |
| --- | --- |
| filter | Giữ phần tử thỏa điều kiện |
| map | Biến đổi mỗi phần tử thành một giá trị khác |
| flatMap | Biến đổi rồi làm phẳng các Stream lồng nhau |
| distinct | Loại phần tử trùng theo equals/hashCode |
| sorted | Sắp xếp theo thứ tự tự nhiên hoặc Comparator |
| limit / skip | Giới hạn hoặc bỏ qua một số phần tử |
| reduce | Kết hợp phần tử thành một kết quả |
| collect | Gom dữ liệu thành collection hoặc cấu trúc khác |
| anyMatch / allMatch / noneMatch | Kiểm tra điều kiện và có thể dừng sớm |
| findFirst / findAny | Lấy một phần tử phù hợp |

map phù hợp khi một phần tử đầu vào tạo ra một phần tử đầu ra. flatMap phù hợp khi một phần tử tạo ra nhiều phần tử, chẳng hạn làm phẳng List<List<String>> thành một Stream<String>.

Với số nguyên hoặc số thực, IntStream, LongStream và DoubleStream có thể tránh boxing không cần thiết. Các thao tác như sum, average, min và max có sẵn trên primitive stream.

### 2.3. Gom nhóm và tạo kết quả

Collectors cung cấp cách gom dữ liệu thường gặp:

~~~java
Map<String, Long> countByCategory = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.counting()
        ));

Map<Boolean, List<Product>> byAvailability = products.stream()
        .collect(Collectors.partitioningBy(Product::available));
~~~

groupingBy gom phần tử theo key; partitioningBy chia thành hai nhóm theo điều kiện boolean. Có thể kết hợp downstream collector như counting, mapping, summingInt hoặc toSet để tạo cấu trúc kết quả cần thiết.

Stream.toList() (Java 16+) trả về danh sách không sửa đổi được. Nếu cần một ArrayList có thể thay đổi, dùng:

~~~java
List<Product> mutable = products.stream()
        .filter(Product::available)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

### 2.4. Quy tắc để Stream dễ đoán

- Ưu tiên lambda và method reference ngắn, có ý nghĩa rõ ràng.
- Predicate và mapper nên stateless, không thay đổi trạng thái dùng chung.
- Tránh dùng peek để thực hiện nghiệp vụ hoặc ghi dữ liệu; peek chỉ hữu ích cho quan sát/debug có kiểm soát.
- Không sửa collection nguồn trong lúc pipeline đang duyệt nguồn đó.
- Không dùng side effect để truyền kết quả giữa các bước; hãy dùng map, reduce hoặc collector.
- Chỉ dùng forEach khi mục đích thực sự là thực hiện hành động cuối cùng; nếu cần tạo danh sách, dùng toList hoặc collect.
- Nếu cần giữ thứ tự gặp ban đầu, chọn thao tác phù hợp và chú ý khác biệt giữa forEach và forEachOrdered.

### 2.5. Khi nào dùng parallel stream?

parallelStream() có thể xử lý các phần dữ liệu độc lập trên nhiều luồng, nhưng không tự động làm chương trình nhanh hơn. Chi phí chia dữ liệu, điều phối, đồng bộ và ghép kết quả có thể lớn hơn lợi ích.

Chỉ cân nhắc parallel stream khi dữ liệu đủ lớn, công việc chủ yếu tốn CPU, mỗi phần tử xử lý độc lập, thao tác không phụ thuộc thứ tự và đã đo hiệu năng bằng dữ liệu gần với thực tế. Tránh dùng cho tác vụ I/O blocking, collection nhỏ, logic có side effect hoặc thao tác đòi hỏi thứ tự nghiêm ngặt. Nếu cần kiểm soát số luồng, vòng đời tác vụ hoặc hủy tác vụ, dùng ExecutorService hoặc API concurrency phù hợp thay vì dựa vào parallel stream.

## 3. Ngoại lệ: mô tả và xử lý lỗi

### 3.1. Phân biệt các nhóm ngoại lệ

Cây kiểu lỗi quan trọng trong Java bắt đầu từ Throwable:

- **Error:** vấn đề nghiêm trọng ở JVM hoặc môi trường chạy. Ứng dụng thông thường không nên bắt Error để tiếp tục hoạt động như không có chuyện gì.
- **Exception:** nhóm ngoại lệ ứng dụng có thể cần xử lý.
- **Checked exception:** ngoại lệ không thuộc RuntimeException. Trình biên dịch yêu cầu method bắt hoặc khai báo throws. IOException là ví dụ phổ biến.
- **Unchecked exception:** RuntimeException và các lớp con. Không bắt buộc khai báo; thường dùng cho đối số không hợp lệ, trạng thái không phù hợp hoặc lỗi lập trình.

Chọn loại ngoại lệ theo hợp đồng của API và khả năng xử lý ở tầng gọi. Không dùng exception như luồng điều khiển thông thường cho trường hợp dự kiến và phổ biến.

### 3.2. try, catch, finally và truyền lỗi

try chứa đoạn có thể phát sinh ngoại lệ; catch xử lý loại ngoại lệ phù hợp; finally dùng cho phần dọn dẹp cần chạy sau try/catch. Nếu không xử lý được, hãy truyền lỗi lên tầng có đủ ngữ cảnh để quyết định.

~~~java
try {
    int quantity = Integer.parseInt(input);
    validateQuantity(quantity);
} catch (NumberFormatException exception) {
    throw new IllegalArgumentException("Quantity must be an integer", exception);
} catch (IllegalArgumentException exception) {
    logger.warn("Invalid quantity: {}", input, exception);
    throw exception;
}
~~~

Bắt ngoại lệ cụ thể trước ngoại lệ tổng quát. Khi bọc một ngoại lệ bằng ngoại lệ khác, giữ nguyên cause để không mất stack trace và nguyên nhân ban đầu. Chỉ bắt khi có thể khôi phục, bổ sung ngữ cảnh hữu ích hoặc chuyển đổi sang hợp đồng lỗi của tầng hiện tại. Tránh catch rỗng hoặc chỉ ghi log rồi tiếp tục với trạng thái không hợp lệ.

Có thể bắt nhiều loại ngoại lệ không có quan hệ kế thừa trực tiếp bằng multi-catch:

~~~java
try {
    loadConfiguration();
} catch (IOException | SecurityException exception) {
    reportConfigurationFailure(exception);
}
~~~

### 3.3. try-with-resources

Dùng try-with-resources cho tài nguyên triển khai AutoCloseable, chẳng hạn stream I/O, reader, writer, connection hoặc statement:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    return reader.lines().toList();
}
~~~

Tài nguyên được đóng tự động khi thoát khối, kể cả khi có ngoại lệ; tài nguyên khai báo sau được đóng trước. Nếu phần thân và thao tác close cùng phát sinh lỗi, lỗi trong lúc close được giữ dưới dạng suppressed exception. Cách này giúp quản lý tài nguyên rõ ràng hơn việc tự đóng trong finally.

### 3.4. Ngoại lệ tùy chỉnh và thông điệp có ích

Tạo ngoại lệ riêng khi domain cần một loại lỗi có ý nghĩa rõ ràng cho tầng gọi. Ví dụ:

~~~java
public final class InsufficientBalanceException extends RuntimeException {
    public InsufficientBalanceException(String message) {
        super(message);
    }

    public InsufficientBalanceException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Thông điệp nên cho biết thao tác hoặc dữ liệu nào không hợp lệ, nhưng không đưa mật khẩu, token hay dữ liệu bí mật vào log. Giữ cause khi chuyển đổi lỗi. Dùng checked exception khi hợp đồng thực sự yêu cầu bên gọi xử lý hoặc khai báo; dùng unchecked exception khi việc xử lý thường thuộc tầng cao hơn hoặc biểu thị vi phạm điều kiện đầu vào/trạng thái.

Không trả về null hoặc một giá trị mặc định giả để che giấu lỗi nếu điều đó khiến tầng gọi không thể phân biệt thành công với thất bại. Nếu một kết quả có thể vắng mặt hợp lệ, cân nhắc Optional hoặc kiểu kết quả rõ ràng.

## 4. Đa luồng và đồng thời

### 4.1. Concurrency, parallelism và race condition

Concurrency (đồng thời) là khả năng nhiều tác vụ cùng tiến triển trong một khoảng thời gian; parallelism (song song) là nhiều tác vụ thực sự chạy cùng lúc trên các lõi xử lý khác nhau. Một chương trình có thể đồng thời mà không chạy song song.

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự xen kẽ giữa các luồng. Ví dụ, hai luồng cùng thực hiện count++ có thể cùng đọc một giá trị rồi ghi đè kết quả của nhau. Một thao tác nhìn có vẻ đơn giản vẫn có thể gồm nhiều bước đọc-sửa-ghi.

### 4.2. Chọn cơ chế bảo vệ dữ liệu

- **Immutability:** ưu tiên đối tượng bất biến; sau khi tạo, trạng thái không thay đổi nên dễ chia sẻ giữa các luồng.
- **Thread confinement:** giữ dữ liệu chỉ trong một luồng nếu có thể; tránh chia sẻ trạng thái không cần thiết.
- **synchronized:** bảo vệ vùng tới hạn, bảo đảm chỉ một luồng vào vùng khóa tại một thời điểm và tạo quan hệ visibility giữa các thao tác dùng cùng monitor.
- **volatile:** bảo đảm các luồng nhìn thấy giá trị cập nhật và các quy tắc ordering liên quan; volatile không làm thao tác ghép như count++ trở thành atomic.
- **AtomicInteger / AtomicLong / LongAdder:** dùng cho bộ đếm và cập nhật nguyên tử phù hợp. LongAdder hữu ích khi nhiều luồng cập nhật bộ đếm cạnh tranh cao và cần tổng hợp giá trị.
- **ConcurrentHashMap:** dùng khi nhiều luồng cần truy cập/cập nhật map. Với nghiệp vụ nhiều bước, vẫn phải thiết kế thao tác nguyên tử hoặc khóa phù hợp.

Nếu một bất biến gồm nhiều trường phải luôn thay đổi cùng nhau, bảo vệ toàn bộ thao tác bằng cùng một khóa hoặc thiết kế API nguyên tử. Không dựa vào volatile cho một chuỗi đọc-sửa-ghi.

### 4.3. Quản lý tác vụ bằng ExecutorService

Thay vì tự tạo và quản lý Thread cho từng tác vụ, thường nên giao tác vụ cho ExecutorService. Executor quản lý việc thực thi và tái sử dụng worker thread. submit nhận Runnable hoặc Callable; Future cho phép lấy kết quả, chờ hoàn tất hoặc yêu cầu hủy.

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
try {
    Future<Integer> result = executor.submit(() -> calculateTotal());
    Integer total = result.get();
} finally {
    executor.shutdown();
}
~~~

get() có thể chặn luồng gọi cho đến khi tác vụ hoàn tất và có thể ném ExecutionException hoặc InterruptedException. Trong ứng dụng thực tế, hãy xác định timeout khi phù hợp, xử lý lỗi tác vụ, giới hạn hàng đợi/tài nguyên và đóng executor đúng vòng đời. shutdown() ngừng nhận tác vụ mới nhưng cho phép tác vụ đã nhận hoàn tất; awaitTermination() có thể dùng để chờ trong thời hạn. Chỉ dùng shutdownNow() khi cần yêu cầu dừng sớm và tác vụ có thiết kế hỗ trợ hủy.

Khi bắt InterruptedException, đừng nuốt tín hiệu ngắt. Nếu tầng hiện tại không thể truyền tiếp ngoại lệ, thường cần khôi phục trạng thái ngắt bằng Thread.currentThread().interrupt() rồi kết thúc hoặc chuyển trạng thái phù hợp.

### 4.4. CompletableFuture cho chuỗi xử lý bất đồng bộ

CompletableFuture phù hợp khi cần ghép các bước bất đồng bộ:

~~~java
CompletableFuture<String> nameFuture =
        CompletableFuture.supplyAsync(() -> loadUser(userId), executor)
                .thenApply(User::name)
                .exceptionally(exception -> "Unknown user");
~~~

thenApply biến đổi kết quả; thenCompose nối một bước bất đồng bộ khác; thenCombine ghép hai kết quả độc lập; exceptionally cung cấp kết quả thay thế khi có lỗi; handle cho phép xử lý cả kết quả lẫn lỗi. Khi cần kiểm soát tài nguyên, hãy truyền executor phù hợp thay vì mặc định chạy mọi tác vụ trên common pool. Chú ý rằng ngoại lệ trong pipeline có thể được bọc trong CompletionException khi đọc kết quả.

### 4.5. Virtual thread trong Java 21+

Java 21 cung cấp virtual thread như một lựa chọn nhẹ cho ứng dụng có rất nhiều tác vụ chờ I/O. Có thể tạo executor theo mô hình một virtual thread cho mỗi tác vụ:

~~~java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> result = executor.submit(() -> "done");
    System.out.println(result.get());
}
~~~

Virtual thread giúp tăng khả năng phục vụ nhiều tác vụ blocking đồng thời với chi phí thấp hơn platform thread trong nhiều tình huống. Chúng không làm một phép tính CPU-bound chạy nhanh hơn và không loại bỏ giới hạn của database, HTTP service, file descriptor hoặc connection pool. Vẫn cần giới hạn tải lên dependency và xử lý timeout, cancellation, back-pressure phù hợp.

### 4.6. Lỗi thiết kế đồng thời thường gặp

- Chia sẻ mutable state giữa nhiều luồng mà không có cơ chế bảo vệ.
- Giữ khóa quá lâu hoặc gọi code bên ngoài khi đang giữ khóa.
- Lấy khóa theo thứ tự khác nhau ở các luồng, tạo nguy cơ deadlock.
- Chờ Future.get() bên trong cùng một executor có quá ít worker, khiến các tác vụ phụ thuộc không còn worker để chạy.
- Dùng thread pool không giới hạn hoặc tạo quá nhiều tác vụ mà không kiểm soát tài nguyên.
- Bỏ qua InterruptedException hoặc giả định việc cancel luôn dừng tác vụ ngay lập tức.
- Cho rằng synchronized, volatile, atomic và concurrent collection có thể thay thế lẫn nhau; mỗi công cụ giải quyết một loại vấn đề khác nhau.

## 5. Ví dụ tổng hợp có thể chạy

Ví dụ sau minh họa generic class, generic method, wildcard PECS, Stream, ngoại lệ unchecked và tác vụ đồng thời. Mã dùng Java 17, không cần thư viện ngoài.

Lưu nội dung thành CoreJavaConceptsDemo.java:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CoreJavaConceptsDemo {
    record Product(String name, int price) {}

    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = Objects.requireNonNull(value);
        }

        T get() {
            return value;
        }
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("values must not be empty");
        }
        return values.get(0);
    }

    static double sum(List<? extends Number> values) {
        return values.stream().mapToDouble(Number::doubleValue).sum();
    }

    static void addDefaults(List<? super Integer> target) {
        target.add(80);
        target.add(90);
    }

    static int requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        return value;
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        Box<String> box = new Box<>("Java");
        System.out.println("generic=" + box.get());
        System.out.println("generic-first=" + first(List.of("Java", "Kotlin")));

        List<Integer> numbers = List.of(1, 2, 3);
        System.out.println("generic-sum=" + sum(numbers));
        List<Number> destination = new ArrayList<>();
        addDefaults(destination);
        System.out.println("generic-sink=" + destination);

        List<Product> products = List.of(
                new Product("Keyboard", 120),
                new Product("Mouse", 40),
                new Product("Monitor", 250)
        );
        List<String> names = products.stream()
                .filter(product -> product.price() >= 100)
                .map(Product::name)
                .toList();
        System.out.println("stream=" + String.join(", ", names));

        try {
            requirePositive(-1);
        } catch (IllegalArgumentException exception) {
            System.out.println("exception=" + exception.getMessage());
        }

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = executor.submit(() -> 20);
            Future<Integer> second = executor.submit(() -> 22);
            System.out.println("concurrency=" + (first.get() + second.get()));
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CoreJavaConceptsDemo.java
java CoreJavaConceptsDemo
~~~

Kết quả stdout:

~~~text
generic=Java
generic-first=Java
generic-sum=6.0
generic-sink=[80, 90]
stream=Keyboard, Monitor
exception=value must be positive
concurrency=42
~~~

Kết quả trên ổn định vì chương trình chỉ cộng kết quả của hai Callable đã hoàn tất; thứ tự worker thực thi không ảnh hưởng tổng cuối cùng.

## 6. Cách chọn công cụ trong thực tế

| Nhu cầu | Công cụ nên cân nhắc |
| --- | --- |
| Collection có kiểu phần tử rõ ràng | Generic như List<T>, Map<K, V> |
| Hàm nhận dữ liệu từ nhiều kiểu con | Wildcard extends |
| Hàm đưa dữ liệu vào một cấu trúc | Wildcard super |
| Lọc, biến đổi, gom nhóm dữ liệu | Stream và Collectors |
| Xử lý lỗi có thể khôi phục hoặc chuyển tầng | Exception phù hợp với hợp đồng API |
| Tác vụ nền cần kết quả hoặc trạng thái hoàn tất | ExecutorService và Future |
| Chuỗi tác vụ bất đồng bộ có phụ thuộc | CompletableFuture |
| Chia sẻ bộ đếm hoặc map giữa nhiều luồng | Atomic/LongAdder hoặc ConcurrentHashMap |
| Nhiều tác vụ blocking I/O trên Java 21+ | Virtual thread, kèm giới hạn tải dependency |

Khi thiết kế, hãy ưu tiên kiểu dữ liệu cụ thể và API có hợp đồng rõ ràng. Dùng Stream để biểu đạt phép biến đổi dữ liệu; dùng vòng lặp thông thường nếu logic có nhiều nhánh, trạng thái hoặc cần dừng từng bước rõ ràng. Dùng ngoại lệ cho tình huống thất bại; không che giấu lỗi bằng giá trị giả. Với đồng thời, giảm chia sẻ trạng thái trước khi thêm khóa; sau đó chọn đúng cơ chế theo yêu cầu atomicity, visibility và vòng đời tác vụ.

## 7. Checklist tự đánh giá

- [ ] Giải thích được vì sao List<Integer> không thể gán cho List<Number>.
- [ ] Viết được generic class, generic method và bounded type parameter.
- [ ] Chọn đúng extends hoặc super theo PECS.
- [ ] Giải thích được type erasure và các giới hạn chính của generic.
- [ ] Phân biệt intermediate operation và terminal operation của Stream.
- [ ] Biết khi nào dùng map, flatMap, reduce và Collectors.
- [ ] Giải thích được vì sao parallel stream không luôn nhanh hơn.
- [ ] Phân biệt checked exception, unchecked exception và Error.
- [ ] Dùng try-with-resources và giữ nguyên cause khi chuyển đổi lỗi.
- [ ] Giải thích được race condition, visibility và atomicity.
- [ ] Phân biệt tác dụng của synchronized, volatile và atomic class.
- [ ] Quản lý vòng đời ExecutorService và xử lý interruption.
- [ ] Chọn CompletableFuture hoặc virtual thread theo đặc điểm tác vụ.

