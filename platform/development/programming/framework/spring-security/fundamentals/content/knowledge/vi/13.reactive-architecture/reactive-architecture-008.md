# Không gọi `block()` hoặc `subscribe()` thủ công trong luồng bảo mật reactive

> **Chủ đề:** Kiến trúc reactive — Spring Security fundamentals (WebFlux, Reactor). Quy tắc này áp dụng cho code chạy trong quá trình xử lý HTTP request, đặc biệt là xác thực, phân quyền và `WebFilter` bảo mật. Ví dụ sử dụng Java 17+ và API Spring Security WebFlux/Spring Reactor.

## 1. Quy tắc cốt lõi và lý do

Trong luồng xử lý request của Spring WebFlux, **hãy trả về một `Mono`/`Flux` mô tả toàn bộ công việc bảo mật** để WebFlux/Spring Security quản lý việc subscribe. Không gọi `block()` để lấy kết quả đồng bộ và không gọi `subscribe()` chỉ để khởi động thao tác bất đồng bộ bên trong filter, authentication manager, authorization manager hoặc service mà chúng sử dụng.

Luồng tư duy đúng:

```text
HTTP request
  → SecurityWebFilterChain / các WebFilter
  → xác thực (Publisher) → kiểm tra quyền (Publisher)
  → chỉ khi được phép mới chuyển sang xử lý tiếp
  → trả Mono<Void> / Mono<Response> cho WebFlux
  → runtime subscribe ở ranh giới xử lý request
```

Một `Mono<T>` thường **lười thực thi**: việc gọi hàm tạo `Mono` chưa đồng nghĩa với việc hoàn tất xác thực. Kết quả, lỗi, hủy yêu cầu và Reactor `Context` phải đi trong **cùng một chuỗi Publisher** được trả về cho framework. Vì vậy, việc “lấy kết quả ngay” bằng `block()` và “chạy nền cho nhanh” bằng `subscribe()` đều phá vỡ mô hình xử lý cần có của security pipeline theo những cách khác nhau.

## 2. Vì sao `block()` sai trong luồng bảo mật?

`block()` đăng ký một subscription và **chờ đồng bộ** cho đến khi Publisher hoàn thành. Trong một request reactive, hậu quả có thể gồm:

- **Chặn luồng xử lý sự kiện:** nếu event-loop phải chờ I/O, năng lực phục vụ nhiều request giảm mạnh; một quyết định quyền chậm có thể giữ luồng quá lâu.
- **Lỗi ngay trên luồng non-blocking:** Reactor có thể ném `IllegalStateException` với thông báo dạng `block()/blockFirst()/blockLast() are blocking, which is not supported in thread ...` khi gọi trên thread được đánh dấu non-blocking. Không nên phụ thuộc vào việc lỗi này luôn xuất hiện; nếu chưa bị phát hiện, việc chặn luồng vẫn là vấn đề.
- **Tách vòng đời khỏi pipeline ban đầu:** `block()` tự tạo subscription khác với subscription mà WebFlux quản lý; có thể thực thi lại Publisher *cold*, tạo thêm truy vấn/kiểm tra quyền hoặc làm khó việc phối hợp context.
- **Khó kiểm soát timeout, lỗi và hủy:** luồng phản hồi HTTP không còn được mô tả hoàn toàn bằng chuỗi toán tử reactive.

**Sai — kiểm tra quyền rồi chờ kết quả trực tiếp bên trong `WebFilter`:**

```java
// Trích đoạn minh họa: tokenVerifier.isValid(exchange) trả Mono<Boolean>.
Boolean valid = tokenVerifier.isValid(exchange).block(); // KHÔNG làm trong WebFlux filter
if (Boolean.TRUE.equals(valid)) {
    return chain.filter(exchange);
}
exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
return exchange.getResponse().setComplete();
```

Việc code “chạy được trên máy dev” hoặc thỉnh thoảng không ném exception **không chứng minh nó an toàn** dưới tải thực tế.

## 3. Vì sao `subscribe()` thủ công cũng sai?

`subscribe()` thường trả về ngay một `Disposable`, tạo **subscription riêng**. Đây không phải cách diễn đạt “hãy xác thực xong rồi mới cho qua”. Nếu filter trả về `chain.filter(exchange)` ngay sau khi tự `subscribe()`, việc kiểm tra có thể chưa hoàn tất khi request được chuyển tiếp.

**Sai — xác thực diễn ra ngoài chuỗi trả về:**

```java
// Trích đoạn minh họa bên trong WebFilter.filter(...).
tokenVerifier.isValid(exchange).subscribe(valid -> {
    if (!valid) {
        exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
    }
});
return chain.filter(exchange); // Có thể chạy trước khi kết quả kiểm tra xuất hiện.
```

Các rủi ro chính:

1. **Race condition và khả năng bỏ qua quyết định bảo mật:** request có thể đi tiếp hoặc response đã được gửi trước khi callback xác thực chạy.
2. **Lỗi nằm ở subscription khác:** exception không tự đi vào chuỗi trả về từ `filter`; logic xử lý lỗi của WebFlux/Spring Security khó quan sát hoặc không xử lý lỗi đó như mong muốn.
3. **Mất quan hệ hủy và thời gian sống:** khi client ngắt kết nối hoặc request timeout, subscription tự tạo không được ghép vào việc hủy của Publisher trả về; thao tác vẫn có thể tiếp diễn.
4. **Mất bối cảnh bảo mật/trace:** `ReactiveSecurityContextHolder` dùng Reactor `Context` gắn với subscriber. Một `subscribe()` riêng không mặc nhiên thừa hưởng ngữ cảnh subscriber của request.
5. **Khó kiểm thử:** test kiểm tra `Mono<Void>` trả về có thể báo hoàn thành dù công việc bảo mật riêng vẫn chưa xong.

`subscribe()` **không đồng nghĩa với `block()`**: nó không nhất thiết chặn thread. Lỗi cốt lõi là tạo một luồng thực thi tách khỏi chuỗi mà framework cần kiểm soát. Ngay cả `subscribe(errorHandler)` cũng không giải quyết việc mất thứ tự, context và vòng đời.

## 4. Cách đúng: ghép thao tác bảo mật bằng toán tử Reactor

Các toán tử thường dùng:

| Nhu cầu | Cách diễn đạt phù hợp |
|---|---|
| Chuyển giá trị đồng bộ, không phát sinh I/O | `map` |
| Gọi hàm trả `Mono`/`Flux` rồi chờ kết quả trong cùng pipeline | `flatMap` |
| Chỉ tiếp tục sau khi một `Mono<Void>` hoàn tất | `then` / `thenReturn` |
| Từ chối nếu không có kết quả xác thực | `switchIfEmpty` hoặc `defaultIfEmpty` phù hợp kiểu |
| Ghi log/metric đồng bộ mà không thay dữ liệu | `doOnNext`, `doOnError`, `doFinally` |
| Xử lý lỗi có chủ đích trong chuỗi | `onErrorResume` hoặc ánh xạ sang lỗi bảo mật phù hợp |

**Ví dụ hoàn chỉnh về *composition* của `WebFilter`** (tệp `TokenGateFilter.java`; cần dependency Spring WebFlux và Reactor, còn `TokenVerifier` phải được ứng dụng cung cấp implementation):

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class TokenGateFilter implements WebFilter {
    private final TokenVerifier tokenVerifier;

    public TokenGateFilter(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        return tokenVerifier.isValid(exchange)
                .defaultIfEmpty(false)
                .flatMap(valid -> {
                    if (valid) {
                        return chain.filter(exchange);
                    }
                    exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
                    return exchange.getResponse().setComplete();
                });
    }

    public interface TokenVerifier {
        Mono<Boolean> isValid(ServerWebExchange exchange);
    }
}
```

**Giải thích chính xác:**

- `isValid(exchange)` trả về `Mono<Boolean>`; chưa kiểm tra tức thì khi tạo `Mono`.
- `defaultIfEmpty(false)` tránh trường hợp Publisher hoàn tất rỗng khiến filter không đưa ra quyết định.
- `flatMap` chọn **một** nhánh sau khi có kết quả. Nếu `true`, trả `chain.filter(exchange)`; nếu `false`, đặt HTTP 401 và hoàn tất response. Không mở nhánh xử lý request trước khi biết kết quả.
- Lỗi từ `isValid` không bị “nuốt” trong callback tách rời; nó truyền trong pipeline để lớp xử lý lỗi có thể quyết định phản hồi thích hợp.
- Chính WebFlux sẽ subscribe vào `Mono<Void>` được trả về; filter **không** tự gọi `subscribe()` hay `block()`.

Đây là ví dụ dạy cách ghép Publisher, **không phải triển khai xác thực token hoàn chỉnh**: ứng dụng thật cần chính sách xác thực, xử lý lỗi, vị trí filter và phân quyền nhất quán trong `SecurityWebFilterChain`. Thông thường nên dùng cơ chế tích hợp sẵn như `AuthenticationWebFilter`, `ReactiveAuthenticationManager` và cấu hình `ServerHttpSecurity` thay vì tự tạo một cơ chế bảo mật cạnh tranh với Spring Security.

## 5. Giữ `SecurityContext` đúng trong reactive pipeline

Trong stack Servlet, nhiều API bảo mật dựa vào `ThreadLocal`. Với WebFlux, một request có thể chuyển thread; **không giả định `SecurityContextHolder.getContext()` của Servlet chứa danh tính request reactive**. Spring Security reactive truyền context qua **Reactor `Context`**. API đọc thích hợp là `ReactiveSecurityContextHolder.getContext()`, và Publisher này phải được nối vào luồng request.

**Ví dụ — endpoint lấy tên người dùng từ reactive security context** (tệp `WhoAmIController.java` trong ứng dụng đã cấu hình WebFlux + Spring Security):

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public Mono<String> whoAmI() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
    }
}
```

Controller trả Publisher cho WebFlux; Spring Security đã có cơ hội gắn security context vào subscription khi request đi qua chain. Giá trị mặc định trên chỉ áp dụng khi không đọc được `Authentication`; tên và quyền thực tế còn phụ thuộc cấu hình anonymous authentication của ứng dụng.

Đừng viết kiểu sau trong service bảo mật:

```java
ReactiveSecurityContextHolder.getContext()
        .subscribe(ctx -> audit(ctx.getAuthentication()));
return Mono.empty();
```

Callback `audit` trở thành tác vụ tách rời, không đảm bảo đã hoàn tất trước response, không được request chờ đợi, và dễ lệch bối cảnh. Nếu `audit` là thao tác bất đồng bộ trả `Mono<Void>`, hãy ghép bằng `flatMap`/`then` vào Publisher chính; nếu chỉ là log đồng bộ nhẹ, có thể dùng `doOnNext`/`doOnEach` tại điểm thích hợp.

## 6. Thứ tự xác thực, phân quyền, chuyển tiếp request

Đường đi hợp lệ cần có quan hệ phụ thuộc rõ ràng:

```text
Lấy chứng thực / token
  └─> Xác minh chứng thực (Mono)
        ├─ lỗi hoặc không hợp lệ → từ chối / xử lý lỗi
        └─ hợp lệ → tạo / nạp Authentication
                     └─> kiểm tra quyền với tài nguyên (Mono)
                           ├─ không đủ quyền → 403 / AccessDenied
                           └─ đủ quyền → chain.filter(exchange)
```

Mã bảo mật thực tế có thể giao khâu xác thực và authorization cho các filter có sẵn; sơ đồ diễn tả **thứ tự bắt buộc về mặt logic**, không yêu cầu mọi bước nằm trong một filter tự viết. `401 Unauthorized` thường dành cho yêu cầu chưa được xác thực hoặc chứng thực không hợp lệ; `403 Forbidden` thường dành cho danh tính đã xác thực nhưng không được phép truy cập. Các entry point và access-denied handler của Spring Security quyết định phản hồi cuối cùng theo cấu hình.

**Không dùng `doOnNext` để khởi chạy một kiểm tra bất đồng bộ:**

```java
// SAI: checkPermission(...) trả Mono<Boolean> nhưng không được ghép vào chain.
return loadAccount(id)
        .doOnNext(account -> checkPermission(account).subscribe())
        .flatMap(this::showAccount);
```

**Ghép kiểm tra quyền để không thể “đi tiếp trước”:**

```java
// Trích đoạn bên trong service trả Mono<AccountView>.
// Các hàm loadAccount, checkPermission, showAccount là API của ứng dụng.
return loadAccount(id)
        .flatMap(account -> checkPermission(account)
                .flatMap(allowed -> allowed
                        ? showAccount(account)
                        : Mono.error(new AccessDeniedException("Forbidden"))));
```

Ví dụ cuối cần import `org.springframework.security.access.AccessDeniedException` và kiểu ứng dụng tương ứng; đây là trích đoạn, không phải một lớp Java độc lập. Nếu kết quả quyền có thể là `Mono.empty()`, phải xác định rõ chính sách mặc định từ chối (ví dụ `defaultIfEmpty(false)`) để không vô tình bỏ qua nhánh.

## 7. Gặp thư viện đồng bộ thì xử lý thế nào?

“Không dùng `block()` trong request reactive” **không có nghĩa mọi API đồng bộ đều tự động biến thành non-blocking**. Nếu code gọi JDBC, HTTP client đồng bộ, file I/O hoặc SDK chặn thread, chỉ quấn nó bằng `Mono.just(...)` vẫn chạy công việc chặn ngay lúc tạo giá trị.

Ưu tiên đầu tiên là dùng API reactive thật sự: Spring WebClient, driver reactive phù hợp, hoặc nguồn trả `Mono`/`Flux`. Nếu buộc phải tích hợp thư viện cũ, cô lập phần chặn thread qua `Mono.fromCallable(...)` kết hợp `subscribeOn(Schedulers.boundedElastic())`; sau đó **vẫn trả Publisher** cho chain, không tự subscribe hay block.

```java
// Trích đoạn minh họa trong phương thức trả Mono<Boolean>.
// legacyAcl.isAllowed(...) là lời gọi đồng bộ có thể chặn thread.
return Mono.fromCallable(() -> legacyAcl.isAllowed(userId, resourceId))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **giải pháp chuyển tiếp có giới hạn**, không làm API đồng bộ trở thành I/O không chặn. Phải giới hạn tải, cân nhắc timeout, tài nguyên thread và độ an toàn của thư viện cũ. Không dùng `publishOn`/`subscribeOn` như cách hợp thức hóa `block()` trong filter; và không dời tất cả xử lý xác thực sang scheduler chỉ vì “reactive”. Việc tính hash mật khẩu tốn CPU cũng cần cân nhắc tài nguyên riêng, nhưng không nên lẫn nó với việc chờ I/O bằng `block()`.

## 8. Những trường hợp `block()` / `subscribe()` có thể xuất hiện hợp lệ

- **Ranh giới chương trình điều khiển:** một CLI `main` hoặc công cụ migration hoàn toàn đồng bộ đôi khi dùng `block()` để nhận kết quả trước khi thoát. Ngữ cảnh đó khác event-loop WebFlux.
- **Bài test:** `StepVerifier` hoặc test harness đăng ký Publisher để kiểm tra tín hiệu, lỗi, hoàn tất và ngữ cảnh. Kiểm thử không phải lý do đem `block()` vào production filter.
- **Consumer cấp cao sở hữu lifecycle:** runtime WebFlux, message consumer có cơ chế quản lý start/stop, hoặc tác vụ được thiết kế độc lập có thể subscribe ở ranh giới rõ ràng. Người viết filter/request security thông thường **không sở hữu ranh giới này**.

Quy tắc thực hành: **Nếu phương thức của bạn trả `Mono`/`Flux` cho Spring WebFlux/Security, hãy ghép công việc vào giá trị trả về; để framework sở hữu subscription.**

## 9. Cách kiểm thử và nhận biết lỗi

Dùng `StepVerifier` (dependency `reactor-test`) hoặc kiểm thử tích hợp `WebTestClient` để kiểm tra **Publisher được trả về**, không chỉ kiểm tra callback bên ngoài. Các ca có ý nghĩa:

| Tình huống | Kết quả mong đợi |
|---|---|
| Xác minh token hoàn tất trễ | Request không đi tới handler trước khi kết quả xác minh có mặt |
| Token sai hoặc kết quả quyền là `false` | Từ chối phù hợp, không gọi bước xử lý được bảo vệ |
| Nguồn xác minh hoàn tất rỗng | Mặc định từ chối hoặc chính sách rõ ràng, không tự bỏ qua kiểm tra |
| Nguồn xác minh phát lỗi | Lỗi đi trong Publisher và được handler bảo mật xử lý |
| Client hủy/timeout | Không có tác vụ `subscribe()` riêng nằm ngoài vòng đời được kiểm soát |
| Request có danh tính | `ReactiveSecurityContextHolder` đọc đúng context trong pipeline |
| Tải đồng thời | Không chặn event-loop, không dựa vào thứ tự chạy tình cờ |

Dấu hiệu cần tìm khi review: `.block()`, `.blockOptional()`, `.blockFirst()`, `.blockLast()`, `.toFuture().get()`/`join()` hoặc `.subscribe()` nằm trong `WebFilter`, `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, reactive controller hoặc service chúng gọi. Chúng không phải lúc nào cũng là lỗi ở mọi nơi; hãy xem **ai sở hữu subscription và phương thức nào đang trả Publisher**. Đặc biệt cảnh giác với `subscribe()` nằm trong `doOnNext`, `map`, listener hoặc callback xác thực.

## 10. Checklist trước khi hoàn thiện một luồng bảo mật reactive

1. Tất cả bước xác thực, truy vấn user, kiểm tra quyền, audit cần được chờ đều nằm trong **Publisher trả về**.
2. Không có `block()` hoặc lời gọi chờ đồng bộ tương đương trên event-loop của request.
3. Không có `subscribe()` thủ công tạo công việc bảo mật tách khỏi request.
4. Quyết định từ chối được phát ra **trước** `chain.filter(exchange)` / xử lý tài nguyên; trạng thái 401/403 do cấu hình phù hợp quyết định.
5. Giá trị rỗng, lỗi, hủy và timeout có hành vi rõ ràng; không mặc định cho phép khi thiếu kết quả.
6. Security context được lấy qua chuỗi reactive, không giả định `ThreadLocal` sẽ theo request qua mọi thread.
7. Tích hợp thư viện chặn thread được thay bằng client reactive hoặc cô lập có kiểm soát; test có trường hợp tải/delay thực tế.

**Ghi nhớ:** với Spring Security WebFlux, bảo mật phải là **một phần của Publisher mà request đang chờ**. `flatMap`, `then` và các toán tử reactive diễn đạt thứ tự, lỗi và ngữ cảnh; `block()` và `subscribe()` thủ công bên trong pipeline làm mất các bảo đảm đó.