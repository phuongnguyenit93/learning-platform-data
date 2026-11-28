# Tránh chu trình khởi tạo và công việc có thể chặn vô hạn

## Mục tiêu

Sau bài học này, bạn có thể:

- Nhận diện chu trình phụ thuộc trực tiếp và gián tiếp giữa các `LazyConstant`.
- Hiểu vì sao chu trình có thể làm `get()` ném `IllegalStateException` hoặc tạo deadlock giữa nhiều luồng.
- Thiết kế dependency graph một chiều để khởi tạo trễ an toàn.
- Tránh đặt thao tác mạng, cơ sở dữ liệu hoặc chờ khóa không giới hạn trong computing function.
- Hiểu giới hạn của timeout, interruption và cancellation đối với `LazyConstant.get()`.
- Tách việc khởi tạo holder khỏi việc thực thi tác vụ bất đồng bộ dài hạn.

## 1. Vì sao chu trình và tác vụ chặn là rủi ro?

`LazyConstant<T>` được thiết kế để tính một giá trị ở lần gọi `get()` đầu tiên, sau đó giữ nguyên giá trị đã tạo. Computing function chạy trên luồng gọi `get()`. Nếu nhiều luồng cùng truy cập một holder chưa khởi tạo, chỉ một luồng chạy function; các luồng còn lại chờ kết quả.

Thiết kế này phù hợp với những giá trị có thể tạo một lần và có thời gian khởi tạo hữu hạn, chẳng hạn parser, metadata hoặc cấu hình bất biến. Nó có rủi ro khi computing function:

- Gọi ngược lại chính holder đang khởi tạo, trực tiếp hoặc qua một chuỗi phụ thuộc.
- Gọi một LazyConstant khác mà cuối cùng quay lại holder ban đầu.
- Chờ mạng, cơ sở dữ liệu, file, khóa hoặc một tác vụ khác mà không có giới hạn thời gian.
- Giữ khóa trong lúc gọi `get()` của một holder khác, tạo thứ tự khóa không nhất quán giữa các luồng.

Một chu trình có thể làm khởi tạo thất bại. Một thao tác chặn vô hạn có thể khiến cả luồng đang khởi tạo lẫn những luồng khác chờ cùng holder không thể tiếp tục. API không cung cấp timeout hoặc cancellation cho `get()`.

## 2. Chu trình trực tiếp và gián tiếp

### Chu trình trực tiếp

Một computing function không được gọi lại `get()` của chính LazyConstant mà nó đang khởi tạo:

~~~java
private static final LazyConstant<String> NAME =
    LazyConstant.of(LazyCycleExample::createName);

private static String createName() {
    return "service-" + NAME.get();
}
~~~

Khi `NAME.get()` được gọi lần đầu, function `createName()` chạy. Function gọi tiếp `NAME.get()` trong khi lần khởi tạo đầu tiên chưa hoàn tất. JDK phát hiện việc gọi đệ quy và ném `IllegalStateException`. Holder không được khởi tạo thành công.

### Chu trình gián tiếp qua nhiều holder

Một chu trình thường khó nhận ra hơn khi mỗi thành phần có vẻ chỉ phụ thuộc vào một thành phần khác:

~~~java
final class LazyCycleExample {
    private static final LazyConstant<ConfigA> A =
        LazyConstant.of(LazyCycleExample::createA);

    private static final LazyConstant<ConfigB> B =
        LazyConstant.of(LazyCycleExample::createB);

    private static ConfigA createA() {
        return new ConfigA(B.get());
    }

    private static ConfigB createB() {
        return new ConfigB(A.get());
    }
}
~~~

Giả sử ứng dụng gọi `A.get()`:

1. LazyConstant `A` bắt đầu tính `ConfigA`.
2. `createA()` gọi `B.get()`, nên `B` bắt đầu tính `ConfigB`.
3. `createB()` gọi lại `A.get()`.
4. Việc khởi tạo `A` đang diễn ra trên cùng luồng, nên JDK phát hiện đệ quy và ném `IllegalStateException`.

Trong trường hợp này, `A` và `B` đều chưa có giá trị được khởi tạo thành công. Các lần gọi sau có thể thử chạy computing function lại; chu trình chưa được sửa thì lỗi sẽ lặp lại.

## 3. Chu trình giữa nhiều luồng có thể tạo deadlock

Phát hiện đệ quy không thay thế việc thiết kế thứ tự phụ thuộc an toàn giữa các luồng.

Xét hai holder `A` và `B`, trong đó supplier của `A` gọi `B.get()`, còn supplier của `B` gọi `A.get()`. Nếu hai luồng bắt đầu cùng lúc:

~~~text
Thread 1                         Thread 2
---------                        ---------
A.get() bắt đầu khởi tạo          B.get() bắt đầu khởi tạo
A supplier gọi B.get()            B supplier gọi A.get()
Chờ B hoàn tất                    Chờ A hoàn tất
         \\                       //
          \\____ chờ lẫn nhau ____//
~~~

Mỗi luồng đang thực hiện computing function của một holder và chờ holder còn lại. Đây là một thứ tự chờ vòng tròn có thể dẫn tới deadlock. Với implementation đồng bộ trên từng holder, tình huống này có thể khiến mỗi luồng giữ khóa của mình trong khi chờ khóa của holder kia. API không cam kết phát hiện hoặc phá vỡ mọi chu trình phụ thuộc giữa các luồng; không nên trông chờ kiểm tra recursive invocation giải quyết được trường hợp này.

Javadoc cũng lưu ý implementation được phép đồng bộ trên chính đối tượng `LazyConstant`. Vì vậy:

- Không dùng holder làm monitor: tránh `synchronized (MY_CONSTANT)`.
- Không giữ một khóa ứng dụng trong lúc gọi `get()` nếu supplier có thể cần khóa khác.
- Không tạo các supplier phụ thuộc chéo theo thứ tự khác nhau ở những luồng khác nhau.
- Thiết kế thứ tự khởi tạo thống nhất và loại bỏ dependency cycle trước khi chạy đồng thời.

## 4. Thiết kế dependency graph không có chu trình

Hãy biểu diễn quan hệ phụ thuộc theo hướng: A → B nghĩa là computing function của A gọi `B.get()`. Đồ thị cần có hướng một chiều và không có đường quay lại node ban đầu.

Ví dụ hợp lệ:

~~~mermaid
flowchart TD
    S[Settings] --> R[Repository]
    S --> C[Cache]
    R --> V[Service]
    C --> V
~~~

Cả `Repository` và `Cache` cùng phụ thuộc vào `Settings`; `Service` sử dụng hai thành phần đó. Không có thành phần nào gọi ngược lên `Service`.

~~~java
final class Components {
    private static final LazyConstant<Settings> SETTINGS =
        LazyConstant.of(Settings::load);

    private static final LazyConstant<Repository> REPOSITORY =
        LazyConstant.of(() -> new Repository(SETTINGS.get()));

    private static final LazyConstant<Cache> CACHE =
        LazyConstant.of(() -> new Cache(SETTINGS.get()));

    private static final LazyConstant<Service> SERVICE =
        LazyConstant.of(() -> new Service(REPOSITORY.get(), CACHE.get()));

    static Service service() {
        return SERVICE.get();
    }
}
~~~

Các kiểu `Settings`, `Repository`, `Cache` và `Service` là thành phần minh họa. Khi gọi `service()`, các dependency được tạo theo thứ tự cần thiết. Nhiều nhánh có thể cùng dùng một holder chung mà không tạo chu trình.

Nếu hai component cần gọi qua lại sau khi được tạo, hãy tách phần điều phối chung thành một abstraction thứ ba, hoặc dùng một cơ chế dependency injection có hỗ trợ rõ ràng cho quan hệ tham chiếu đó. Tránh để constructor của A gọi B.get() trong khi constructor của B lại gọi A.get().

## 5. Phân biệt chu trình LazyConstant với chu trình khởi tạo class

LazyConstant có thể được khai báo trong field static mà không tính nội dung ngay. Tuy nhiên, nếu static initializer gọi `get()`, supplier có thể chạy trong khi class vẫn đang được khởi tạo.

Ví dụ về kiểu thiết kế dễ gây vấn đề:

~~~java
final class ServiceRegistry {
    static final LazyConstant<Service> SERVICE =
        LazyConstant.of(Service::new);

    static final Registry REGISTRY =
        Registry.create(SERVICE.get());
}
~~~

Field `REGISTRY` gọi `SERVICE.get()` ngay trong quá trình khởi tạo class. Nếu constructor hoặc factory tiếp tục truy cập class khác có static initializer quay lại `ServiceRegistry`, có thể xuất hiện chu trình khởi tạo class. Theo quy tắc khởi tạo class của Java, chu trình như vậy có thể dẫn đến lỗi khởi tạo hoặc quan sát trạng thái chưa hoàn tất tùy quan hệ giữa các luồng.

Cách tổ chức tốt hơn là giữ static initializer đơn giản, chỉ khai báo holder và gọi `get()` từ phương thức được gọi sau khi các class liên quan đã khởi tạo xong. Với đồ thị phụ thuộc phức tạp, dùng một composition root hoặc container chịu trách nhiệm tạo và nối các component theo thứ tự rõ ràng.

Không nên coi việc chuyển mọi field sang `LazyConstant` là cách tự động giải quyết vòng phụ thuộc trong static initialization.

## 6. Không đặt công việc có thể chặn vô hạn trong supplier

Supplier của LazyConstant chạy ngay trên luồng gọi `get()`. Nếu supplier thực hiện I/O đồng bộ, luồng gọi sẽ phải chờ thao tác đó hoàn tất:

~~~java
private static final LazyConstant<RemoteConfig> CONFIG =
    LazyConstant.of(() -> RemoteConfig.loadFromServer());
~~~

Nếu `loadFromServer()` chờ mạng vô hạn, lần gọi `CONFIG.get()` đầu tiên cũng có thể chờ vô hạn. Những luồng khác gọi `CONFIG.get()` trong thời gian đó sẽ bị chặn chờ cùng lần khởi tạo.

Các thao tác cần đặc biệt thận trọng:

- HTTP request không có request timeout hoặc connect timeout.
- Truy vấn cơ sở dữ liệu không có query timeout, socket timeout hoặc giới hạn pool.
- Đọc file hoặc stream từ thiết bị có thể ngừng phản hồi.
- Chờ khóa, semaphore, queue hoặc latch không có deadline.
- Chờ một future mà tác vụ nền có thể không bao giờ hoàn tất.
- Gọi service khác trong lúc service đó đang phụ thuộc ngược lại vào component hiện tại.

Nếu giá trị có thể tải từ nguồn bên ngoài, hãy đặt timeout ở chính API thực hiện I/O. Ví dụ với HTTP Client:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .build();

HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(5))
    .GET()
    .build();
~~~

Connect timeout giới hạn thời gian thiết lập kết nối; request timeout giới hạn thời gian thực hiện request theo hợp đồng của HTTP Client. Khi dùng trong supplier, hãy xử lý các checked exception của thao tác I/O theo quy ước ứng dụng và không nuốt lỗi.

Timeout của thao tác nền giúp computing function có cơ hội kết thúc hoặc thất bại trong thời gian hữu hạn. Nó không phải timeout của `LazyConstant.get()`; chính supplier phải gọi API có timeout phù hợp.

## 7. Interruption không phải cancellation của LazyConstant

`LazyConstant.get()` không có overload nhận `Duration`, deadline hoặc token hủy. Theo Javadoc JDK 26:

- Computing function chạy trên luồng gọi `get()`.
- Khi nhiều luồng tranh nhau khởi tạo, chỉ một luồng chạy function; các luồng khác bị chặn cho đến khi có kết quả.
- Interruption không hủy quá trình khởi tạo của LazyConstant.
- Nếu computing function bị chặn vô hạn, các luồng khác dùng cùng holder cũng có thể bị chặn vô hạn.
- API không cung cấp timeout hoặc cancellation cho quá trình khởi tạo.

Điều này có nghĩa là không nên trông chờ `Thread.interrupt()` hoặc hủy một tác vụ đang gọi `get()` để tự động dừng supplier. Nếu thao tác bên dưới hỗ trợ interruption, supplier cần xử lý đúng exception và khôi phục trạng thái interrupt theo quy ước Java:

~~~java
private static RemoteConfig loadConfig() {
    try {
        return remoteClient.fetchWithTimeout();
    } catch (InterruptedException error) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Tải cấu hình bị gián đoạn", error);
    } catch (IOException error) {
        throw new UncheckedIOException(error);
    }
}
~~~

`remoteClient.fetchWithTimeout()` là hàm minh họa, cần có timeout ở tầng client. Việc khôi phục interrupt giữ lại tín hiệu cho code gọi phía trên; exception được chuyển thành unchecked vì `Supplier.get()` không khai báo checked exception.

Nếu supplier thất bại và ném exception, LazyConstant vẫn chưa được khởi tạo. Một lần `get()` sau có thể chạy supplier lại. Hãy thiết kế retry có giới hạn và side effect an toàn; không để mọi request liên tục kích hoạt một chuỗi retry không giới hạn.

## 8. Tách việc tạo holder khỏi tác vụ bất đồng bộ dài hạn

Nếu cần khởi chạy công việc nền, supplier có thể chỉ tạo và trả về một handle bất đồng bộ nhanh chóng, thay vì tự chờ công việc hoàn tất. Khi đó LazyConstant giữ handle, còn timeout và cancellation được quản lý ở tầng tác vụ.

Ví dụ minh họa:

~~~java
private static final LazyConstant<CompletableFuture<RemoteConfig>> CONFIG_TASK =
    LazyConstant.of(() ->
        CompletableFuture.supplyAsync(
            RemoteConfig::load,
            configExecutor
        )
    );

static RemoteConfig config(Duration waitLimit)
        throws InterruptedException, ExecutionException, TimeoutException {
    return CONFIG_TASK.get().get(
        waitLimit.toMillis(),
        TimeUnit.MILLISECONDS
    );
}
~~~

`configExecutor` là executor do ứng dụng quản lý và cần có giới hạn tài nguyên phù hợp. Supplier chỉ tạo tác vụ và trả về `CompletableFuture`; `get()` của LazyConstant không chờ tải cấu hình hoàn tất. Phương thức `Future.get(timeout, unit)` giới hạn thời gian chờ của từng caller.

Cần hiểu rõ các đánh đổi:

- LazyConstant chỉ khởi tạo một lần handle `CompletableFuture`; nó không khởi tạo lại future nếu future hoàn tất exceptional.
- Timeout của `Future.get` chỉ kết thúc việc chờ của caller đó. Tác vụ nền có thể vẫn chạy.
- `CompletableFuture.orTimeout` hoàn tất future bằng timeout exception, nhưng không đảm bảo dừng thao tác I/O hoặc mã đang chạy bên dưới. Vì future được chia sẻ trong LazyConstant, đặt timeout trực tiếp lên future chung cũng có thể khiến mọi caller quan sát cùng kết quả timeout.
- Muốn hủy thật sự, cần giữ handle hủy phù hợp và dùng API nền hỗ trợ cancellation; tác vụ phải hợp tác với yêu cầu hủy và đóng tài nguyên đang dùng.
- Executor bị cạn worker hoặc bị shutdown cũng có thể khiến công việc không hoàn tất. Hãy cấu hình queue, pool size, rejection policy và shutdown lifecycle.

Đây là một lựa chọn kiến trúc khi cần tách thời điểm khởi tạo handle khỏi thời điểm nhận kết quả. Không dùng nó nếu yêu cầu là mọi caller phải nhận một giá trị đồng bộ ngay tại `get()` mà không có cơ chế chờ riêng.

## 9. Quan sát trạng thái mà không kích hoạt khởi tạo

`isInitialized()` và `orElse(other)` không gọi computing function. Chúng hữu ích cho quan sát hoặc đường xử lý không muốn chờ:

~~~java
if (CONFIG.isInitialized()) {
    use(CONFIG.get());
} else {
    useFallback();
}
~~~

Tuy nhiên, đây không phải mẫu đồng bộ hóa để bảo đảm holder sẽ vẫn ở trạng thái chưa khởi tạo sau khi kiểm tra. Luồng khác có thể khởi tạo ngay sau khi `isInitialized()` trả về. Nếu cần giá trị, gọi `get()` và chấp nhận ngữ nghĩa chờ của nó. Nếu cần đường không chặn, dùng `orElse(fallback)` và xử lý trường hợp fallback:

~~~java
RemoteConfig current = CONFIG.orElse(DEFAULT_CONFIG);
~~~

`orElse` trả nội dung đã khởi tạo nếu có, nếu chưa thì trả giá trị thay thế; nó không chờ supplier và không kích hoạt supplier. Nhưng fallback không có nghĩa là quá trình khởi tạo đã bị hủy hoặc sẽ không diễn ra sau đó.

## 10. Xử lý lỗi và thử lại có kiểm soát

Nếu supplier ném exception hoặc error, LazyConstant không được khởi tạo và lần gọi `get()` sau có thể thử lại. Điều này khác với một future đã được tạo và hoàn tất exceptional, vì future đó vẫn là một giá trị đã được lưu trong LazyConstant.

Khi supplier có thể thất bại tạm thời:

1. Đặt timeout tại client hoặc API nguồn dữ liệu.
2. Giới hạn số lần retry và thời gian backoff.
3. Đảm bảo mỗi lần thử có thể lặp lại an toàn; không tạo giao dịch hoặc tài nguyên trùng lặp.
4. Ghi nhận nguyên nhân lỗi, thời gian khởi tạo và số lần thử.
5. Có đường xử lý fallback hoặc báo lỗi rõ ràng cho caller.
6. Tránh giữ khóa ứng dụng trong khi thực hiện I/O hoặc retry.

Không dùng một vòng lặp retry vô hạn trong supplier. Vì chỉ một luồng chạy supplier và các luồng khác chờ, retry vô hạn có thể biến một lỗi dịch vụ thành điểm nghẽn toàn bộ ứng dụng.

## 11. Checklist thiết kế LazyConstant an toàn

- [ ] Vẽ dependency graph và kiểm tra không có chu trình.
- [ ] Không gọi lại chính holder đang được khởi tạo.
- [ ] Không tạo dependency chéo theo thứ tự khác nhau giữa nhiều luồng.
- [ ] Không đồng bộ trực tiếp trên LazyConstant hoặc giữ khóa ứng dụng khi gọi `get()`.
- [ ] Không gọi `get()` từ static initializer nếu supplier có thể tạo chu trình class initialization.
- [ ] Giữ computing function ngắn, có thời gian kết thúc hữu hạn và ít side effect.
- [ ] Đặt connect timeout, request timeout, query timeout hoặc socket timeout ở tầng I/O.
- [ ] Không coi interruption là cơ chế hủy LazyConstant.
- [ ] Nếu dùng tác vụ nền, quản lý timeout, cancellation, executor và đóng tài nguyên ở tầng tác vụ.
- [ ] Giới hạn retry và bảo đảm supplier an toàn khi chạy lại sau thất bại.
- [ ] Đo thời gian khởi tạo, số luồng chờ, lỗi timeout và số lần retry trong tải thực tế.

## 12. Trạng thái API trong JDK 26

`java.lang.LazyConstant` là **preview API** trong JDK 26 theo JEP 526 (Second Preview). Muốn biên dịch và chạy ví dụ cần dùng JDK 26 và bật `--enable-preview` ở cả compiler lẫn runtime. API có thể thay đổi hoặc bị loại bỏ trong release sau; hãy xác nhận trạng thái của JDK mục tiêu trước khi đưa vào ứng dụng. Nếu production không chấp nhận phụ thuộc preview, dùng cơ chế khởi tạo trễ ổn định phù hợp với vòng đời component và vẫn áp dụng các nguyên tắc về dependency graph, timeout và cancellation đã trình bày ở trên.

## Kết luận

LazyConstant phù hợp với giá trị khởi tạo một lần có dependency rõ ràng và thời gian tính toán hữu hạn. Chu trình trực tiếp hoặc gián tiếp trong cùng quá trình khởi tạo sẽ làm `get()` ném `IllegalStateException`; phụ thuộc chéo giữa nhiều luồng còn có thể tạo deadlock khi các supplier chờ holder của nhau. Supplier chạy trên caller thread, không có timeout hoặc cancellation tích hợp và interruption không tự hủy quá trình khởi tạo. Hãy thiết kế dependency graph không chu trình, tránh I/O chặn trong supplier, đặt timeout ở tầng tài nguyên thực tế và tách công việc bất đồng bộ dài hạn khỏi bước tạo holder.

## Tài liệu tham khảo

- [Java 26 API – LazyConstant: Exception handling, Thread Safety and Implementation Note](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html)
- [Java 26 Core Libraries Guide – Lazy Constants](https://docs.oracle.com/en/java/javase/26/core/lazy-constants.html)
- [JEP 526: Lazy Constants (Second Preview)](https://openjdk.org/jeps/526)
- [Java Language Specification, Java SE 26 – Initialization of Classes and Interfaces](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html)
- [Java 26 API – HttpClient.Builder.connectTimeout](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java 26 API – HttpRequest.Builder.timeout](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
