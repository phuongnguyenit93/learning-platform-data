# switchMap để chuyển sang công việc mới nhất trong Project Reactor

**Ngữ cảnh:** Spring Framework – Reactive, chủ đề **Biến đổi dữ liệu**. Bài học này tập trung vào `Flux.switchMap(...)` của Project Reactor: mỗi khi nguồn phát một yêu cầu mới, chuyển sang publisher tương ứng với yêu cầu mới nhất và hủy subscription của công việc trước đó nếu nó còn đang chạy.

## 1. Vấn đề: kết quả cũ về sau kết quả mới

Hãy hình dung một giao diện tìm kiếm: người dùng nhập “jav”, rồi sửa thành “java”. Hai lần tìm kiếm có thể mất thời gian khác nhau:

- Yêu cầu “jav” được gửi trước, upstream xử lý chậm.
- Yêu cầu “java” được gửi sau nhưng phản hồi nhanh hơn.
- Nếu cứ nhận tất cả kết quả bất kể thứ tự, kết quả của “jav” có thể đến muộn và ghi đè kết quả của “java”. Giao diện hiển thị dữ liệu không tương ứng với ý định mới nhất của người dùng.

Trong luồng sự kiện cùng một subscription, `switchMap` giúp biểu đạt quy tắc **latest wins**: mỗi sự kiện mới được ánh xạ sang một publisher bên trong (*inner publisher*), rồi hủy subscription bên trong trước đó để chỉ tiếp tục nhận tín hiệu từ công việc đang được chọn.

Ví dụ các cụm từ tìm kiếm `Flux<String>` lần lượt là “jav” và “java”. Mapper tạo một `Mono<SearchResult>` cho từng cụm từ. Khi “java” tới trước khi truy vấn “jav” hoàn tất, `switchMap` hủy subscription của truy vấn “jav” và chuyển sang chờ kết quả “java”.

**Hai giới hạn quan trọng:** `switchMap` không xóa được tín hiệu cũ **đã phát ra cho downstream**; cũng không bảo đảm hủy thành công thao tác từ xa đã bắt đầu hoặc hoàn tác side effect. Nó kiểm soát **subscription và tín hiệu downstream**, không phải một giao thức hủy nghiệp vụ phân tán.

## 2. Cách `Flux.switchMap` hoạt động

API được dùng theo dạng:

```java
Flux<R> output = input.switchMap(value -> publisherFor(value));
```

Ở đây, `input` là `Flux<T>`, hàm mapper nhận mỗi phần tử `T` và trả một `Publisher<? extends R>` (thường là `Mono<R>` hoặc `Flux<R>`). Mỗi lần input phát giá trị mới, operator xử lý như sau:

1. Nhận phần tử mới từ luồng ngoài (*outer Flux*).
2. Dừng theo dõi inner publisher cũ bằng cách **cancel subscription cũ**, nếu còn active.
3. Đăng ký theo dõi inner publisher mới do mapper tạo.
4. Chuyển tiếp tín hiệu từ inner đang active cho subscriber downstream.
5. Khi outer kết thúc, chờ inner hiện tại kết thúc để hoàn tất (trừ khi xuất hiện error/cancellation).

Đây là mô hình khái niệm, không phải bảo đảm thứ tự từng lệnh callback hoặc thread:

```text
Outer Flux:
  term A -------- term B --------------- term C ---- complete
      |               |                      |
      v               v                      v
  inner A         inner B                inner C
  ...đang chờ     ...đang chờ             ...đã xong
      X cancel        X cancel                 |
                                                   
Output:
  [tín hiệu A đã kịp phát nếu có]  [tín hiệu B nếu đã kịp phát]  [tín hiệu C]
```

Nếu A chưa phát kết quả nào trước lúc B đến, downstream không nhận kết quả A. Nếu A **đã phát phần tử A1** trước lúc B xuất hiện, A1 đã được chuyển tiếp và không thể bị thu hồi; chỉ các tín hiệu **sau khi A bị hủy** mới không còn được chuyển tiếp như công việc được chọn.

Với inner là `Mono`, thường nhận tối đa một kết quả. Với inner là `Flux`, một inner có thể phát nhiều phần tử trước khi có sự kiện mới. Vì vậy **“chỉ nhận kết quả cuối cùng của toàn bộ outer Flux” không phải định nghĩa đúng của `switchMap`**. Định nghĩa đúng là “mỗi khi có phần tử outer mới, chuyển sang inner mới nhất và hủy inner trước đó”.

### 2.1. Nguồn outer có phải chờ inner hoàn thành không?

Không. Đây là khác biệt then chốt với `concatMap`. `switchMap` không trì hoãn đầu vào mới chỉ để đợi công việc cũ. Chính sự xuất hiện của phần tử outer mới làm operator chuyển quyền ưu tiên sang inner mới.

Nếu outer cứ phát liên tục nhanh hơn thời gian hoàn thành của inner, nhiều inner có thể bị hủy trước khi cho ra kết quả. Đó là hành vi hợp lý với **tìm kiếm gợi ý, preview hoặc trạng thái xem mới nhất**, nhưng nguy hiểm nếu từng công việc đều cần hoàn tất.

### 2.2. Subscription, cancellation và công việc thực tế

`switchMap` tạo subscription vào publisher con và gửi tín hiệu hủy (*cancel*) tới subscription cũ khi chuyển. Với publisher hỗ trợ hủy, một timeout, timer hoặc HTTP client có thể ngừng chờ và giải phóng tài nguyên tương ứng. Tuy nhiên:

- Một HTTP request có thể đã tới server; server có thể tiếp tục xử lý dù client hủy chờ response.
- Một hàm JDBC, file I/O hoặc CPU-bound đang chạy theo kiểu blocking có thể không dừng ngay, dù subscription đã bị cancel.
- Một publisher được chia sẻ hoặc cache có thể còn subscriber khác, nên việc hủy một subscriber không bắt buộc dừng nguồn chia sẻ.
- Side effect đã thực hiện như ghi đơn hàng, thanh toán hoặc gửi email không bị hoàn tác chỉ vì `switchMap` chuyển sang inner mới.

Do đó, dùng `switchMap` để **không hiển thị kết quả cũ** là hợp lý; dùng nó như cơ chế **rollback giao dịch, đảm bảo exactly-once hoặc hủy công việc ở hệ thống khác** là sai.

## 3. Ví dụ Java 17+ chạy được, không phụ thuộc vào thời gian

Ví dụ sau chủ động dùng `Mono.never()` để mô tả một tác vụ cũ không bao giờ hoàn thành. Khi phần tử mới xuất hiện, `switchMap` phải hủy tác vụ này; nhờ vậy kết quả và số lần hủy có thể kiểm tra **chính xác**, không phụ thuộc scheduler, mạng hay tốc độ máy.

Tệp `src/main/java/demo/SwitchMapDemo.java`:

```java
package demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class SwitchMapDemo {
    public static void main(String[] args) {
        AtomicInteger cancelledOld = new AtomicInteger();

        Flux<String> results = Flux.just("old", "new")
                .switchMap(query -> {
                    if ("old".equals(query)) {
                        return Mono.<String>never()
                                .doOnCancel(cancelledOld::incrementAndGet);
                    }
                    return Mono.just("result-new");
                });

        List<String> values = results
                .collectList()
                .block(Duration.ofSeconds(3));

        System.out.println("results = " + values);
        System.out.println("cancelled old = " + cancelledOld.get());
    }
}
```

Có thể chạy hàm `main` từ IDE trong một dự án đã có dependency `io.projectreactor:reactor-core`, chẳng hạn dự án Spring Boot có `spring-boot-starter-webflux`. Nếu chạy bằng `javac/java` trực tiếp, cần các JAR `reactor-core` và `reactive-streams` tương thích trong thư mục `lib/`:

```bash
# Linux / macOS, chạy từ thư mục gốc chứa src/ và lib/
javac -cp "lib/*" -d . src/main/java/demo/SwitchMapDemo.java
java -cp ".:lib/*" demo.SwitchMapDemo
```

Với Windows PowerShell, ký tự phân cách classpath của lệnh `java` là dấu chấm phẩy:

```powershell
javac -cp "lib/*" -d . src/main/java/demo/SwitchMapDemo.java
java -cp ".;lib/*" demo.SwitchMapDemo
```

**Stdout chính xác:**

```text
results = [result-new]
cancelled old = 1
```

Tại sao?

1. `Flux.just("old", "new")` là nguồn lạnh đồng bộ. Khi có subscriber do `block(...)` kích hoạt, nó phát “old”, rồi “new”.
2. “old” tạo `Mono.never()`. Tác vụ này đã có subscription nhưng không phát giá trị, không tự kết thúc.
3. “new” được phát tiếp. `switchMap` hủy subscription “old” một lần, khiến `doOnCancel` tăng counter.
4. Inner mới `Mono.just("result-new")` phát một giá trị và hoàn tất; `collectList()` thu được duy nhất phần tử đó.
5. Hết outer và inner cuối cùng đã hoàn tất, `block(...)` trả danh sách để in kết quả.

**Để kiểm tra giả thiết**, thay `switchMap` bằng `concatMap` trong ví dụ trên thì pipeline không thể chờ “old” hoàn thành để xử lý phần tử kế tiếp theo cùng cách; `Mono.never()` sẽ khiến ví dụ hết hạn `block(Duration...)` và ném exception. Không chạy biến thể đó rồi kỳ vọng stdout giống bản gốc.

Đây là **minh họa cancellation ở cấp subscription**, không mô phỏng một HTTP request thật. Khi dùng I/O thực tế, phải đo và theo dõi việc cancel có giải phóng được connection/worker hay không.

## 4. So sánh `map`, `flatMap`, `concatMap` và `switchMap`

Cả bốn thường xuất hiện trong xử lý dữ liệu với Reactor, nhưng phục vụ mục đích khác nhau.

| Operator | Mapper trả về | Cách xử lý nhiều phần tử outer | Phù hợp với |
| --- | --- | --- | --- |
| `map` | Giá trị thông thường `R` | Biến đổi đồng bộ từng phần tử, không tự tạo subscription tới một publisher con | Chuyển DTO, chuẩn hóa chuỗi, tính giá trị đơn giản |
| `flatMap` | Publisher `Mono/Flux` | Cho phép nhiều inner hoạt động đồng thời; kết quả có thể xen kẽ, không giữ thứ tự outer theo mặc định | Các I/O độc lập đều cần kết quả |
| `concatMap` | Publisher `Mono/Flux` | Xử lý inner theo thứ tự, thường đợi inner hiện tại hoàn tất rồi mới chuyển sang inner tiếp theo | Tác vụ phải chạy/được phát theo thứ tự và không được bỏ |
| `switchMap` | Publisher `Mono/Flux` | Khi có phần tử outer mới, hủy inner trước và chuyển sang inner mới nhất | Tìm kiếm trực tiếp, xem trước, refresh dữ liệu mới nhất |
| `flatMapSequential` | Publisher `Mono/Flux` | Có thể subscribe nhiều inner đồng thời nhưng sắp phát kết quả theo thứ tự outer, với chi phí đệm dữ liệu | Cần đồng thời hóa công việc mà vẫn giữ thứ tự kết quả |

Các ví dụ ý nghĩa:

- **Cần lưu đủ mọi thay đổi nghiệp vụ:** thường không dùng `switchMap`; một sự kiện bị bỏ có thể là mất dữ liệu. Cân nhắc `concatMap` hoặc cơ chế queue durable tùy yêu cầu.
- **Gọi độc lập API giá và API tồn kho:** dùng `Mono.zip` hoặc `flatMap` khi cả hai kết quả cần được tính; `switchMap` chỉ thích hợp nếu request mới khiến dữ liệu từ request trước trở nên không còn hữu ích.
- **Người dùng chuyển nhanh giữa các hồ sơ:** `switchMap` phù hợp nếu chỉ muốn hiển thị dữ liệu của hồ sơ hiện đang được chọn.
- **Xử lý thanh toán/ghi đơn hàng:** không dùng `switchMap` chỉ vì sự kiện mới xuất hiện; từng lệnh phải được xử lý theo contract nghiệp vụ, kể cả khi client ngắt kết nối.

**Nhớ phân biệt:** `switchMap` không đồng nghĩa với `flatMap` “nhanh hơn”. Nó **thay đổi ngữ nghĩa kết quả** bằng cách từ bỏ các inner cũ, nên chỉ đúng nếu công việc cũ được phép không có kết quả hiển thị.

## 5. Ví dụ Spring WebFlux: tìm kiếm trực tiếp theo luồng từ khóa

Giả sử ứng dụng có một **Flux<String> chứa các thay đổi từ khóa thuộc cùng phiên tương tác**. Từ khóa có thể đến qua WebSocket, một phiên streaming hoặc một adapter trong tầng ứng dụng. Với mỗi từ khóa, service gọi một HTTP API tìm kiếm bằng `WebClient` rồi tạo một bản chụp kết quả. Đây là tình huống `switchMap` giải quyết đúng: ý định tìm kiếm mới thay thế ý định cũ.

Đoạn mã sau là **class service hoàn chỉnh trong một ứng dụng Spring Boot/WebFlux**, cần một upstream HTTP tại `http://localhost:8081/search?q=...` trả danh sách JSON item phù hợp; nó không phải ứng dụng standalone có hàm `main`. Dùng Java 17+ và các dependency `spring-boot-starter-webflux`, `spring-context` theo quản lý phiên bản của dự án.

Tệp `src/main/java/demo/LiveSearchService.java`:

```java
package demo;

import java.time.Duration;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class LiveSearchService {
    private final WebClient catalogClient;

    public LiveSearchService(WebClient.Builder builder) {
        this.catalogClient = builder
                .baseUrl("http://localhost:8081")
                .build();
    }

    public Flux<SearchSnapshot> search(Flux<String> terms) {
        return terms
                .map(String::trim)
                .distinctUntilChanged()
                .switchMap(term -> {
                    if (term.isBlank()) {
                        return Mono.just(
                                new SearchSnapshot(term, List.of(), false));
                    }

                    return Mono.delay(Duration.ofMillis(250))
                            .then(Mono.defer(() -> catalogClient.get()
                                    .uri(uriBuilder -> uriBuilder
                                            .path("/search")
                                            .queryParam("q", term)
                                            .build())
                                    .retrieve()
                                    .bodyToFlux(Item.class)
                                    .collectList()
                                    .map(items -> new SearchSnapshot(
                                            term, items, false))))
                            .timeout(Duration.ofSeconds(2))
                            .onErrorResume(error -> Mono.just(
                                    new SearchSnapshot(
                                            term, List.of(), true)));
                });
    }

    public record Item(String id, String name) {}

    public record SearchSnapshot(
            String term,
            List<Item> items,
            boolean failed) {}
}
```

Cách service hoạt động:

1. `map(String::trim)` chuẩn hóa chuỗi; `distinctUntilChanged()` bỏ các từ khóa trùng nhau **liên tiếp**.
2. `switchMap` nhận **mọi thay đổi khác biệt**, bao gồm cả việc xóa trống ô tìm kiếm, để ngay lập tức hủy inner cũ. Nếu người dùng xóa từ khóa, một `SearchSnapshot` rỗng được phát ra. **Không đặt `filter(term -> !term.isBlank())` trước `switchMap`** nếu việc xóa từ khóa phải hủy truy vấn cũ, vì như thế sự kiện xóa trống sẽ không đến được `switchMap`.
3. `Mono.delay(250 ms)` đặt *khoảng chờ yên tĩnh* **bên trong inner**. Nếu từ khóa tiếp tục thay đổi trước 250 ms, `switchMap` hủy cả timer lẫn inner cũ, nên chưa gửi request cũ ra mạng. Không cần Thread.sleep hay chặn luồng.
4. `Mono.defer(...)` bảo đảm phần dựng HTTP publisher diễn ra khi timer hoàn tất và vẫn còn subscription. `WebClient` hỗ trợ luồng I/O non-blocking; `bodyToFlux(Item.class).collectList()` tạo **một snapshot** cho mỗi lần tìm kiếm thay vì phát từng item làm giao diện lẫn nhiều đợt dữ liệu.
5. `timeout(2 s)` giới hạn thời gian chờ; `onErrorResume(...)` chuyển lỗi của **một truy vấn cụ thể** thành snapshot có `failed=true` để luồng từ khóa có thể tiếp tục. Không nhầm lỗi với danh sách kết quả trống hợp lệ: `failed` giúp phía hiển thị phân biệt. Trong sản phẩm thật, cần log/metrics, phân loại lỗi trước khi fallback và không để dữ liệu quan trọng bị mất dấu.
6. Khi một từ khóa mới tới, `switchMap` hủy subscription của inner trước; kết quả từ inner cũ sau thời điểm hủy không còn được dùng cho luồng output. Nếu inner cũ đã phát snapshot trước đó, snapshot ấy đã tồn tại trong downstream và chỉ snapshot mới tiếp tục cập nhật giao diện.

**Kiến trúc cần đúng chỗ:** service nhận `Flux<String> terms` đại diện cho **một luồng sự kiện**. Nếu giao diện gửi từng HTTP GET độc lập và mỗi lần Spring tạo một controller invocation riêng, việc đặt `switchMap` bên trong từng invocation **không tự động hủy request của invocation trước**, vì chúng không nằm chung một outer Flux/subscription. Với hệ thống dùng HTTP GET độc lập, bên phát request (ví dụ luồng tìm kiếm phía frontend) phải điều phối latest-wins, hoặc ứng dụng cần một channel/server-side stream chung có vòng đời rõ ràng.

**Không khuyến khích** dùng `subscribe()` bên trong method `search(...)` chỉ để “bắt đầu” request. Hãy trả publisher cho subscriber ở ranh giới thích hợp (WebFlux, WebSocket handler hoặc consumer của stream), để framework/consumer kiểm soát lifecycle, error và cancellation.

### 5.1. Tại sao đặt debounce bên trong hay bên ngoài `switchMap` lại khác?

Hai cách sau trông giống nhau nhưng có khoảng thời gian hủy khác:

**Cách A – debounce trước, chỉ switch sau khi từ khóa ổn định:**

```java
Flux<SearchSnapshot> a = terms
        .debounce(Duration.ofMillis(250))
        .switchMap(term -> searchMono(term));
```

**Cách B – switch ngay, delay việc khởi tạo tìm kiếm ở inner:**

```java
Flux<SearchSnapshot> b = terms
        .switchMap(term ->
                Mono.delay(Duration.ofMillis(250))
                        .then(Mono.defer(() -> searchMono(term))));
```

Hai đoạn đều chỉ là **mã minh họa**, cần `terms` và `searchMono(String)` do ứng dụng cung cấp. Với A, sự kiện mới chưa đi tới `switchMap` cho đến khi vượt qua `debounce`: trong khoảng đợi 250 ms, truy vấn trước đó **có thể vẫn đang active**. Với B, `switchMap` nhận thay đổi ngay và hủy inner cũ lập tức; timer của inner mới chờ 250 ms rồi mới chạy tìm kiếm.

Cách nào đúng tùy yêu cầu UX: có muốn giữ kết quả cũ đến khi query mới ổn định không; có cần hủy I/O cũ ngay khi gõ ký tự mới không; có cần cập nhật ngay khi ô nhập trở thành trống không. Không coi `debounce` và `switchMap` là hai tên khác nhau cho cùng chức năng.

## 6. Theo dõi hủy và xử lý lỗi đúng cách

### 6.1. Quan sát `doOnCancel` và `doFinally`

Để debug cancellation ở inner publisher:

```java
return terms.switchMap(term ->
        searchMono(term)
                .doOnCancel(() ->
                        log.debug("Cancelled search: {}", term))
                .doFinally(signal ->
                        log.debug("Finished search {} with {}", term, signal)));
```

Đây là **đoạn minh họa trong service**, các biến `terms`, `searchMono`, `log` cần do ứng dụng định nghĩa. `doOnCancel` được gọi khi subscriber hủy publisher; `doFinally` nhận `SignalType.CANCEL`, `ON_COMPLETE` hoặc `ON_ERROR` để nhận diện kiểu kết thúc. **Có sự kiện CANCEL không chứng minh HTTP server đã dừng xử lý**; đó là tín hiệu tại publisher đang quan sát. Với tracing, cũng cần correlation ID/từ khóa ở ngữ cảnh phù hợp để không trộn log giữa nhiều người dùng.

Không dựa vào thứ tự log giữa nhiều scheduler để khẳng định chính xác thứ tự mạng. Dùng metrics: số sự kiện mới, số inner start, cancel, complete/error, thời gian chờ, connection pool và số request thực gửi.

### 6.2. Lỗi của inner có thể kết thúc cả outer Flux

Nếu một inner phát `onError` mà không được xử lý, operator có thể phát lỗi xuống downstream và **kết thúc toàn bộ luồng**. Với typeahead, điều này có thể khiến một lỗi upstream đơn lẻ làm mất khả năng tiếp tục nhận các từ khóa sau. Nếu nghiệp vụ muốn giữ stream hoạt động, nên xử lý lỗi **bên trong từng inner**, như ví dụ `onErrorResume` trong `switchMap`, để biến lỗi thành một trạng thái hiển thị có thể phân biệt.

Tuy vậy, không bắt mọi `Throwable` rồi làm như tìm kiếm không có kết quả: lỗi xác thực, cấu hình sai, schema sai hay bug lập trình có thể cần chính sách khác. Thiết kế logging, alerting và fallback theo contract API.

### 6.3. `retry` có thể tái tạo công việc

Khi retry một publisher lạnh, Reactor thường **resubscribe** vào nguồn. Điều này có thể gửi lại HTTP request, tạo lại I/O hoặc lặp side effect. Với tìm kiếm thuần đọc, retry hữu hạn có backoff có thể chấp nhận nếu giới hạn tải và latency; với ghi dữ liệu, phải xét idempotency, giao dịch và tính an toàn khi retry.

`switchMap` có thể hủy một inner đang retry; nếu upstream không thực thi hủy, các nỗ lực cũ vẫn có thể dùng tài nguyên. Không dựa vào cancellation để thay thế timeout, concurrency limit và circuit breaker.

## 7. Hủy subscription không đồng nghĩa hủy toàn bộ nghiệp vụ

Đặt công việc đúng nhóm quyết định:

| Kiểu công việc | Có nên bỏ inner cũ khi input mới đến? | Lý do |
| --- | --- | --- |
| Preview ảnh, tìm kiếm gợi ý, lọc danh sách theo ô nhập | Thường có | Kết quả cũ không còn liên quan tới trạng thái giao diện hiện tại |
| Xem chi tiết đối tượng đang chọn, bản đồ theo vị trí mới | Có thể | Chỉ muốn hiển thị đối tượng/vị trí mới nhất |
| Polling trạng thái chỉ để cập nhật màn hình | Có thể | Số lần lấy dữ liệu cũ không quan trọng nếu chỉ cần snapshot mới |
| Ghi đơn hàng, thanh toán, gửi email | Thường không | Mỗi lệnh là một side effect có nghĩa vụ hoàn thành, cần tracking và idempotency |
| Xử lý sự kiện sổ cái, đồng bộ thay đổi không được mất | Không | Bỏ inner đồng nghĩa nguy cơ mất nghiệp vụ |
| Tác vụ CPU nặng đã chạy | Chỉ khi có cơ chế hủy thực sự | Cancellation của reactive subscription không buộc CPU task dừng ngay |

Với một API lưu trạng thái như “đổi theme giao diện”, vẫn phải suy nghĩ nếu server nhận hai lệnh và thực thi song song: hủy chờ lệnh cũ trên client **không bảo đảm** lệnh cũ không đến server hoặc không chạy sau lệnh mới. Nếu thứ tự cập nhật thực sự quan trọng, server phải có version/check-and-set, sequence, idempotency key hoặc cơ chế đồng bộ thích hợp.

**Quy tắc ra quyết định:** `switchMap` phù hợp khi **có thể không sử dụng kết quả của công việc cũ**. Điều đó khác với tuyên bố **công việc cũ chắc chắn chưa/không xảy ra**.

## 8. Kiểm thử hành vi bằng Reactor Test

Ngoài nhìn log, nên viết test chứng minh hai thuộc tính: inner cũ được gửi cancellation, còn downstream chỉ nhận kết quả inner mới nếu inner cũ chưa kịp phát.

Đoạn test sau là class JUnit 5 có thể dùng trong project đã có `reactor-test`, `reactor-core` và JUnit Jupiter. Tệp `src/test/java/demo/SwitchMapTest.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SwitchMapTest {
    @Test
    void cancelsPreviousInnerAndKeepsLatest() {
        AtomicInteger cancelled = new AtomicInteger();

        Flux<String> result = Flux.just("first", "second")
                .switchMap(term -> {
                    if ("first".equals(term)) {
                        return Mono.<String>never()
                                .doOnCancel(cancelled::incrementAndGet);
                    }
                    return Mono.just("second-result");
                });

        StepVerifier.create(result)
                .expectNext("second-result")
                .verifyComplete();

        assertEquals(1, cancelled.get());
    }
}
```

JUnit cần `org.junit.jupiter:junit-jupiter`, còn `StepVerifier` cần `io.projectreactor:reactor-test` trên test classpath; trong Spring Boot dự án có thể khai báo các dependency test theo BOM của dự án. Chạy bằng `./gradlew test` hoặc trình chạy JUnit của IDE. Test đồng bộ này có kết quả xác định, không phụ thuộc `Thread.sleep(...)`.

Với nghiệp vụ tìm kiếm cần đo thời gian 250 ms, dùng `StepVerifier.withVirtualTime(...)` và khởi tạo publisher trong supplier mà API yêu cầu; nhờ virtual time có thể khẳng định chính xác hành vi timer/debounce/switch mà không chờ đồng hồ thật. Với client HTTP thực, dùng mock server và assertions về request/cancellation phù hợp; **không mặc định rằng việc client cancel đồng nghĩa server sẽ không nhận request**.

Để kiểm thử công việc có side effect, thêm assertion về số lần gọi upstream, số lần retry, trạng thái cuối trên server và những cập nhật bị cấm. Kiểm thử tín hiệu Reactor không đủ để bảo đảm tính nhất quán nghiệp vụ ngoài process.

## 9. Những lỗi thường gặp

### 9.1. Nhầm `switchMap` với “lấy phần tử cuối cùng”

`switchMap` có thể cho ra dữ liệu từ inner trước khi outer phát phần tử mới. Nếu chỉ cần **phần tử cuối của một Flux hữu hạn sau khi nó hoàn thành**, có thể xem `last()` hoặc `takeLast(...)` tùy nhu cầu, nhưng các toán tử này có contract khác về thời điểm hoàn thành và cách giữ dữ liệu. `switchMap` là cách **đổi công việc đang được theo dõi** theo input, không phải phép chọn phần tử cuối chung.

### 9.2. Dùng `switchMap` cho một outer Flux không có sự kiện mới

Nếu outer chỉ phát đúng một phần tử, `switchMap` không thể “chuyển sang công việc mới hơn” vì không có phần tử tiếp theo. Với `Mono` xử lý đơn lẻ, `flatMap` thường đủ; `switchMap` hữu ích khi thật sự có **chuỗi thay đổi** qua thời gian.

### 9.3. Lọc mất tín hiệu hủy

Nếu dùng:

```java
terms.filter(term -> !term.isBlank())
     .switchMap(term -> searchMono(term));
```

thì việc người dùng xóa trống ô tìm kiếm **không tạo sự kiện đến `switchMap`**, khiến inner cũ có thể tiếp tục đến khi nhận từ khóa khác. Nếu xóa trống cần hủy tác vụ và phát kết quả rỗng, hãy đưa logic đó vào mapper của `switchMap` thay vì lọc trước.

### 9.4. Cho rằng từ khóa mới luôn hủy upstream server ngay

Operator gửi cancellation cho inner subscription. Ở mạng, kết nối, database, driver và server còn nhiều lớp; một số vẫn thực hiện và ghi kết quả. Cần timeout, giới hạn resource và cơ chế bảo vệ side effect phù hợp. Không thực hiện các nghiệp vụ không thể bỏ bằng `switchMap`.

### 9.5. Bỏ qua hot source, cache và share

Với cold publisher, cancellation thường có thể ngăn source tiếp tục phát tới subscriber đó. Với hot publisher hoặc `cache()`/`share()`, upstream có thể còn chạy vì subscriber khác hoặc vì cache. Một nguồn `Sinks.Many` nóng cũng có thể phát event trước subscription hoặc nhanh hơn downstream xử lý. Hãy kiểm tra thực tế cancellation và policy replay/buffer của nguồn thay vì dự đoán từ riêng tên operator.

### 9.6. Nhầm `switchMap` với `debounce` hay kiểm soát áp lực

- `debounce` hạn chế số **sự kiện outer** được chuyển tiếp sau khoảng thời gian yên tĩnh.
- `distinctUntilChanged` bỏ các sự kiện **trùng liên tiếp**.
- `switchMap` quản lý **inner subscription mới nhất** khi có sự kiện outer.
- `onBackpressureLatest` áp dụng một chiến lược giữ phần tử mới nhất ở điểm có áp lực demand, nhưng không thay thế ngữ nghĩa hủy các công việc inner của `switchMap`.

Dùng tổ hợp đúng thứ tự theo mục tiêu nghiệp vụ, đồng thời giới hạn lượng I/O, connection pool và kích thước buffer. `switchMap` không phải giải pháp tự động cho mọi nguồn phát quá nhanh.

### 9.7. Quên xử lý lỗi và vòng đời stream

Một lỗi bên trong inner không được phục hồi có thể làm cả output stream kết thúc; một downstream subscriber cancel thì cả outer và inner hiện tại cũng có thể bị hủy. Khi dùng WebSocket hoặc một luồng tương tác dài, cần thiết kế giải phóng tài nguyên, reconnection, tracking request/response, xử lý error và state cuối cùng khi channel đóng.

## 10. Checklist chọn và áp dụng `switchMap`

1. **Ý nghĩa nghiệp vụ:** phần kết quả cũ có thật sự được phép bỏ không? Nếu không, không chọn `switchMap`.
2. **Outer Flux có thật:** chuỗi input mới và cũ có nằm trong cùng stream/subscription không? Mỗi HTTP request độc lập không tạo latest-wins tự động.
3. **Mapper trả publisher lazy:** nên dùng `WebClient`/API bất đồng bộ và tránh `Mono.just(blockingCall())`. Công việc blocking cần được cô lập, không chiếm event-loop.
4. **Trạng thái rỗng có ý nghĩa:** sự kiện clear/empty có phải hủy tìm kiếm đang chạy không? Đừng lọc nó trước operator nếu phải hủy.
5. **Thời điểm chuyển:** chọn debounce trước hay delay bên trong inner tùy muốn hủy ngay hay sau khoảng yên tĩnh.
6. **Chiến lược lỗi:** lỗi tìm kiếm đơn lẻ có nên làm chết toàn bộ luồng? Nếu không, phục hồi riêng từng inner và thể hiện lỗi rõ ràng.
7. **Đo resource và cancel:** quan sát request thực gửi, latency, số inner bị cancel, số work đang thực thi, connection pool và memory.
8. **Tính nhất quán:** nếu công việc đã gửi tới hệ thống khác, cancel không bảo đảm rollback. Side effect quan trọng phải có bảo vệ riêng.
9. **Kiểm thử:** có test cho input thay đổi nhanh, input xóa trống, lỗi inner, kết quả đến sai thứ tự, hủy downstream và giới hạn tải.

## 11. Tổng kết

`Flux.switchMap(mapper)` dành cho **luồng ý định thay đổi**, trong đó mỗi giá trị mới biến công việc cũ thành không còn cần kết quả. Operator ánh xạ mỗi phần tử outer sang publisher bên trong, **hủy inner trước đó khi có phần tử mới**, và tiếp tục phát từ inner mới nhất. Nó khác `flatMap` (giữ các inner đồng thời) và `concatMap` (xử lý từng inner theo thứ tự).

Ứng dụng tiêu biểu là live search, preview và lựa chọn đối tượng trên giao diện. Ba điều phải luôn giữ đúng: **tín hiệu đã phát không bị thu hồi; cancellation không phải rollback; `switchMap` chỉ điều phối các công việc nằm trong cùng outer Flux/subscription**. Khi các điều kiện này phù hợp với nghiệp vụ, `switchMap` giúp diễn đạt trực tiếp nguyên tắc “kết quả của ý định mới nhất được ưu tiên”.
