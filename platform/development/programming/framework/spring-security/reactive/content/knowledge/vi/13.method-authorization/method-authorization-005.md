# @PreFilter, @PostFilter và giới hạn lọc dữ liệu theo kiểu trả về, phiên bản

> **Ngữ cảnh:** Spring Security trong ứng dụng Spring WebFlux, Java 17+, Spring Boot 3.3.x / Spring Security 6.3.x; so sánh rõ với cơ chế method security Servlet/imperative và những điểm phải kiểm tra khi nâng cấp phiên bản. Trọng tâm là **lọc phần tử đầu vào và kết quả**, không nhầm với chặn toàn bộ method hoặc bảo vệ bản ghi tại repository.

## 1. Bài toán: kiểm soát từng phần tử thay vì toàn bộ request

Giả sử service quản lý các báo cáo:

| ID | Chủ sở hữu | Tiêu đề |
|---|---|---|
| R-1 | alice | Báo cáo A |
| R-2 | bob | Báo cáo B |
| R-3 | alice | Báo cáo C |

Alice đã xác thực. Khi gọi `GET /api/reports`, ứng dụng muốn trả **R-1, R-3**, không trả R-2. Khi Alice gửi ba báo cáo trong một yêu cầu thử nghiệm, hệ thống có thể muốn chỉ xử lý những phần tử cô ấy sở hữu.

Spring Security có hai annotation cho kiểu xử lý đó:

- `@PreFilter`: lọc **các phần tử của tham số đầu vào** trước khi logic method nhận chúng.
- `@PostFilter`: lọc **các phần tử của giá trị method trả về** sau khi method cung cấp kết quả, trước khi người gọi nhìn thấy kết quả đã được lọc.

Hai annotation khác với:

- `@PreAuthorize`: quyết định **có cho gọi method hay không**; thường từ chối bằng lỗi access denied khi không đủ quyền.
- `@PostAuthorize`: kiểm tra **kết quả method** và có thể **từ chối toàn bộ kết quả**, không phải cơ chế “xóa từng phần tử”.
- `authorizeExchange`: phân quyền ở lớp HTTP theo URL, method và principal.
- `Flux.filter(...)`, `Flux.filterWhen(...)` hoặc truy vấn repository `findAllByOwnerId(...)`: lọc bằng code nghiệp vụ/reactive ở tầng dữ liệu, không phụ thuộc SpEL annotation.

### Nhìn trực quan

```text
              @PreFilter                       @PostFilter
Input A,B,C -------> Input A,C ---> service ---> Result A,B,C -------> Result A,C
                      (đã lọc)                (method có thể đã lấy tất cả)

@PreAuthorize: từ chối gọi method nếu caller không được phép
@PostAuthorize: từ chối kết quả nếu điều kiện trả về không thỏa
```

**Điểm an toàn cốt lõi:** `@PostFilter` chỉ là một hàng rào sau khi dữ liệu đã được truy xuất. Nếu service tải cả triệu bản ghi rồi mới lọc quyền, rủi ro tải lớn, phân trang sai và logic nội bộ vô tình xử lý dữ liệu ngoài phạm vi vẫn tồn tại. Các chính sách bảo vệ dữ liệu nhạy cảm cần bắt đầu từ truy vấn repository và kiểm quyền đối tượng.

## 2. Annotation và biểu thức SpEL

Hai annotation nằm trong package:

```java
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PostFilter;
```

Ví dụ cơ bản trên kiểu phần tử có thuộc tính `owner`:

```java
@PreFilter("filterObject.owner == authentication.name")
public Collection<Report> process(Collection<Report> reports) {
    // Chỉ những phần tử thỏa expression mới được truyền vào method.
    return reports;
}

@PostFilter("filterObject.owner == authentication.name")
public Collection<Report> listReports() {
    // Method có thể trả đủ các record.
    return repository.findAll();
}
```

**Đây là đoạn minh họa cho method security kiểu imperative/collection, không phải code chạy độc lập trong WebFlux.** Các tài liệu servlet/imperative của Spring Security mô tả những collection-based signature này. Với **reactive method security**, phải kiểm tra đúng interceptor và kiểu Publisher theo phiên bản; đừng bê nguyên signature imperative `Collection<Report>` vào một bean chỉ có `@EnableReactiveMethodSecurity` rồi mặc định nó sẽ hoạt động như một method reactive.

Trong expression:

- `filterObject` là **phần tử hiện đang được đánh giá**, không phải toàn bộ tập kết quả.
- `authentication.name` lấy tên từ `Authentication` đã được Spring Security thiết lập. Với Basic demo thường là username; với JWT có thể là subject khác.
- `hasRole('ADMIN')` kiểm tra role được cấp. Role theo prefix mặc định tương ứng authority `ROLE_ADMIN`.
- `filterObject.owner == authentication.name or hasRole('ADMIN')` cho phép owner hoặc admin.

**Chú ý thuộc tính Java:** Nếu dùng JavaBean `getOwner()`, SpEL `filterObject.owner` có thể truy cập property tương ứng. Nếu dùng record Java, nên xác minh SpEL có thể truy cập record component trên đúng Spring Framework version; để tránh ambiguity, ví dụ chạy được phía dưới khai báo `getOwner()` rõ ràng.

### Lọc không đồng nghĩa từ chối

`@PostFilter` khi gặp phần tử không đạt điều kiện sẽ loại phần tử đó khỏi luồng/tập giá trị mà caller thấy; nó không mặc định phát 403 cho mỗi phần tử bị loại. Nếu toàn bộ phần tử bị loại, người gọi có thể nhận danh sách rỗng hoặc publisher hoàn thành rỗng, tùy kiểu API và phiên bản. Nếu nghiệp vụ yêu cầu **một bản ghi không được phép phải trả 403/404**, hãy dùng cách kiểm quyền cho **đúng đối tượng** (query scoped, `@PostAuthorize` phù hợp, hoặc explicit deny) thay vì phụ thuộc vào việc danh sách trở thành rỗng.

## 3. Các phiên bản method security: Servlet và Reactive không phải một

Trong Spring Security 6, các cơ chế này dùng Spring AOP quanh lời gọi bean nhưng có nhánh interceptor khác nhau.

| Mục | Imperative/Servlet | Reactive/WebFlux |
|---|---|---|
| Bật method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Ngữ cảnh principal | Thường `SecurityContextHolder` với thread-bound strategy | `ReactiveSecurityContextHolder` trong Reactor Context |
| Giá trị method thông dụng | `Report`, `List<Report>`, `Collection<Report>`, `Stream<Report>` | `Mono<Report>`, `Flux<Report>`, publisher/reactive types được hỗ trợ |
| Pre-filter interceptor | `PreFilterAuthorizationMethodInterceptor` | `PreFilterAuthorizationReactiveMethodInterceptor` |
| Post-filter interceptor | `PostFilterAuthorizationMethodInterceptor` | `PostFilterAuthorizationReactiveMethodInterceptor` |
| Filter target | Method argument/filterable elements | Reactive argument/Publisher theo hỗ trợ của implementation |
| Filter result | Collection, array, map, stream của method | Publisher được interceptor xử lý theo phiên bản; phải kiểm thử wrapper/element |
| Rủi ro | In-memory scan, eager loading, proxy/self-invocation | Mất Reactor Context, wrapper type, deferred subscription, vẫn có scan/over-fetch |

### 3.1 Thay đổi quan trọng theo phiên bản

- **Spring Security 5.8:** tài liệu và Javadoc ghi nhận các interceptor reactive chuyên biệt `PreFilterAuthorizationReactiveMethodInterceptor` và `PostFilterAuthorizationReactiveMethodInterceptor` (Since 5.8). Cơ chế `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` đưa vào hướng AuthorizationManager.
- **Spring Security 6.0 trở đi:** cơ chế AuthorizationManager là mặc định của `@EnableReactiveMethodSecurity`; trong dự án mới có thể dùng `@EnableReactiveMethodSecurity`. Khi migrate từ bản cũ, xác nhận không đồng thời kích hoạt bộ interceptor cũ.
- **Spring Security 6.3/6.5:** tài liệu reactive liệt kê `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` và các interceptor reactive. Tài liệu cũng nêu method được bảo vệ trong ví dụ reactive cần trả `org.reactivestreams.Publisher` (ví dụ `Mono`, `Flux`) để tích hợp Reactor Context. **Sự tồn tại của annotation/interceptor không tự chứng minh mọi kiểu đối số, wrapper, stream hay biểu thức đều được hỗ trợ giống Servlet.**
- **Spring Security 7.x:** vẫn có tài liệu method security reactive và các interceptor tương ứng, nhưng API, điều kiện trả kiểu, cấu hình SpEL và hành vi chuyên biệt có thể thay đổi theo bản patch. Khi nâng cấp phải kiểm tra tài liệu **đúng version** và chạy lại test, không suy từ ví dụ version 6.3.

Nguồn chính thức để kiểm tra:

- Reactive method security Spring Security 6.3: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Reactive method security Spring Security 6.5: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Javadoc `PreFilterAuthorizationReactiveMethodInterceptor` bản 6.3.8: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/authorization/method/PreFilterAuthorizationReactiveMethodInterceptor.html
- Javadoc `PostFilterAuthorizationReactiveMethodInterceptor` bản 6.3.x: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html
- Tài liệu Servlet cho loại collection/map/stream: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html

**Đừng chỉ tra tài liệu “current” không cố định version**: ở thời điểm hiện tại trang mặc định có thể hướng tới Spring Security 7.x, không khớp app dùng Spring Boot 3.3.x.

### 3.2 Bật đúng annotation trên cấu hình reactive

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfiguration {
    // SecurityWebFilterChain và nguồn Authentication ở đây.
}
```

Đây là mảnh code cần các import:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
```

Cả request-level và method-level đều cần thiết. `@EnableReactiveMethodSecurity` không thay thế `SecurityWebFilterChain`; `@EnableWebFluxSecurity` một mình cũng không bật các annotation method security.

Trong một hệ thống WebFlux, **không dùng `@EnableMethodSecurity` của Servlet để hy vọng các method `Flux`/`Mono` được xử lý theo ReactiveSecurityContextHolder**. Các loại proxy/interceptor và context cần phù hợp.

## 4. Kiểu tham số của @PreFilter và giới hạn thường gặp

`@PreFilter` đánh giá expression trên từng phần tử **trước khi method xử lý đầu vào**.

### 4.1 Collection/array/map/stream trong method security imperative

Theo tài liệu Spring Security Servlet, những ví dụ sau là pattern hợp lệ khi method security imperative được bật:

```java
@PreFilter("filterObject.owner == authentication.name")
Collection<Report> update(Collection<Report> reports);

@PreFilter("filterObject.owner == authentication.name")
Collection<Report> update(Report[] reports);

@PreFilter("filterObject.value.owner == authentication.name")
Collection<Report> update(Map<String, Report> reports);

@PreFilter("filterObject.owner == authentication.name")
Collection<Report> update(Stream<Report> reports);
```

Đây là **chữ ký minh họa**, không phải class Java chạy được; tài liệu hỗ trợ `Stream` với điều kiện stream chưa bị đóng. Đối với map, phần tử `filterObject` thường là **entry**, nên lấy `filterObject.value.owner` thay vì coi bản thân entry là report. Khi có nhiều argument có thể lọc, dùng `filterTarget` để chỉ rõ tham số (cùng với cấu hình cho phép resolve tên tham số).

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "reports")
Collection<Report> update(String tenantId, Collection<Report> reports);
```

Trong thực tế, khi chọn theo tên biến, cần kiểm tra compiler parameter metadata hoặc dùng cơ chế khai báo tên tham số được Spring Security hỗ trợ. Không biến tên code thành một dependency ngầm rồi quên kiểm thử sau build.

### 4.2 Flux<T> không phải List<T>

Một `Flux<Report>` mô tả **luồng phát các Report**, có thể chưa thực sự chạy khi method tạo `Flux`. Trong Spring Security 6.x có interceptor reactive dành cho các filter annotation, nên cần kiểm thử đúng nhánh reactive.

Chữ ký mục tiêu có ý nghĩa “kiểm từng phần tử khi Flux được subscribe”:

```java
@PreFilter("filterObject.owner == authentication.name")
public Flux<Report> preview(Flux<Report> input) {
    return input;
}
```

Đoạn này cần bean được Spring proxy, `@EnableReactiveMethodSecurity`, Reactor Context có authentication và **bản Spring Security hỗ trợ lọc Flux argument như kỳ vọng**. Đừng suy rằng đặt `@PreFilter` lên `List<Report>` trong cùng reactive bean luôn có đúng kết quả; đây là giới hạn cần xác nhận bằng test integration theo version.

Nếu version hoặc kiểu đặc biệt không hoạt động như mong đợi, cách **tường minh và dễ dự đoán** là tự viết pipeline reactive bằng owner/tenant đã xác minh:

```java
Flux<Report> previewOwned(
        Flux<Report> input, String trustedUsername) {
    return input.filter(
        report -> trustedUsername.equals(report.getOwner()));
}
```

Đây là method minh họa; **trustedUsername phải lấy từ Authentication đã xác thực**, không lấy từ query param/body/header do client gửi. Dùng `flatMap`/`filterWhen` khi quyết định cần truy vấn quyền bất đồng bộ.

### 4.3 Mono<List<T>> khác Flux<T>

`Mono<List<Report>>` phát ra **một đối tượng List**, trong khi `Flux<Report>` phát ra từng `Report`. Việc có container bên trong Mono không làm annotation tự “đi sâu” một cấp vào list:

```java
Mono<List<Report>> wrapped = repository.findAll().collectList();
// Publisher phát 1 giá trị List<Report>.
// Không tự đồng nghĩa Flux<Report> hay Collection<Report> trực tiếp.
```

Một `@PreFilter` đặt lên `Mono<List<Report>>` cũng không thể giả định nó lọc từng `Report` của List theo cơ chế giống `Flux<Report>`. Tùy version, interceptor có thể xem payload là một object, không hỗ trợ wrapper, hoặc có xử lý riêng; **hãy kiểm thử, không đoán**.

Khi cần xử lý phần tử, ưu tiên pipeline tường minh:

```java
Flux<Report> items = inputMono
    .flatMapMany(Flux::fromIterable)
    .filter(report -> trustedUsername.equals(report.getOwner()));
```

Cũng có thể trả về `Mono<List<Report>>` sau khi lọc:

```java
Mono<List<Report>> owned =
    inputMono.flatMapMany(Flux::fromIterable)
        .filter(r -> trustedUsername.equals(r.getOwner()))
        .collectList();
```

Nhưng nếu source đã tải toàn bộ dữ liệu trước khi vào `inputMono`, chi phí over-fetch vẫn còn. Khi có repository reactive, truy vấn sẵn theo owner/tenant trước sẽ tốt hơn.

### 4.4 Một tham số scalar không phải collection

`@PreFilter` là filter theo **phần tử**; với tham số scalar như `Long orderId` hoặc `String tenant`, đừng dùng nó như cách diễn đạt “deny nếu không thuộc user”. Hãy dùng `@PreAuthorize(...)` hoặc kiểm quyền trong service/repository.

### 4.5 Bảo mật khi lọc đầu vào

Việc âm thầm loại phần tử không đủ quyền khỏi input có thể gây vấn đề nghiệp vụ: client gửi 10 mục, server chỉ xử lý 7 mà vẫn trả thành công, gây hiểu nhầm hoặc mở đường gửi batch lặp. Với thao tác **ghi dữ liệu**, thường an toàn và rõ ràng hơn là:

- Xác minh quyền toàn bộ batch trước transaction.
- Nếu có bất kỳ phần tử ngoài phạm vi: trả lỗi 403/422 phù hợp.
- Nếu business cố ý cho phép partial success: trả kết quả chi tiết từng item, audit chính xác, idempotency và transaction policy tường minh.

Không dùng `@PreFilter` để lặng lẽ xóa item ngoài quyền rồi trả `200 OK` nếu hợp đồng API yêu cầu all-or-nothing.

## 5. Kiểu trả về của @PostFilter: khả năng và cạm bẫy

### 5.1 Method trả Collection trực tiếp

Trong **imperative method security**, Spring Security 6.x hỗ trợ lọc:

- `Collection<Report>` như `List` hoặc `Set`.
- `Report[]` array.
- `Map<K, Report>` với expression phù hợp cho entry.
- `Stream<Report>` khi stream vẫn mở.

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Report> allReports() {
    return repository.findAll();
}
```

Ví dụ trên là **mảnh method imperative**. Nếu repository trả 500.000 bản ghi rồi annotation giữ 5 bản ghi, vẫn trả chi phí đọc 500.000 bản ghi. Dùng truy vấn scoped theo owner/tenant cho production.

### 5.2 Method trả Flux<Report>

Đây là dạng tự nhiên trong WebFlux: `Flux<Report>` phát nhiều phần tử và có thể thực hiện lọc khi subscriber đọc dữ liệu:

```java
@PostFilter(
    "filterObject.owner == authentication.name or hasRole('ADMIN')")
public Flux<Report> list() {
    return Flux.just(
        new Report("R-1", "alice", "Alpha"),
        new Report("R-2", "bob", "Beta"),
        new Report("R-3", "alice", "Gamma"));
}
```

Đây là **method minh họa**, cần class bean, model và annotation bật đúng. Các interceptor reactive tồn tại trong Spring Security 6.3 và hướng tới kết quả publisher, nhưng **hành vi chính xác cần test với bản patch/dependency thực tế**. Ở mục 7 sẽ có ví dụ cùng ý tưởng và WebTestClient cho kết quả owner/admin.

Nếu phiên bản được chọn không filter đúng `Flux<Report>` như mong đợi, **không được bỏ qua lỗi rồi đưa API vào production**; chuyển sang filter tường minh bằng `Flux.filter/filterWhen` hoặc repository query theo principal.

### 5.3 Method trả Mono<Report>

`Mono<Report>` phát tối đa một `Report`. Không nên dùng `@PostFilter` để thể hiện “trả 403 khi owner sai” vì filter có thể tạo **Mono.empty()** thay vì phát access-denied; một controller có thể biến empty thành response không như bạn kỳ vọng. Với bản ghi đơn, chọn rõ policy:

```java
public Mono<Report> readVisible(String id, String trustedUsername) {
    return repository.findByIdAndOwner(id, trustedUsername)
        .switchIfEmpty(Mono.error(
            new AccessDeniedException("Not allowed")));
}
```

Đây là pseudocode Java minh họa: cần repository, `AccessDeniedException`, import `Mono`; 403/404 còn tùy chính sách API và exception handler. Nếu một record **không tồn tại**, không nên mặc định trả 403 tiết lộ điều gì; thiết kế response chống enumeration và kiểm quyền data-level.

### 5.4 Method trả Mono<List<Report>>

Đừng nhìn type bên ngoài `Mono` và nghĩ annotation tự iterate toàn bộ List. Đặc biệt, không nên **khẳng định chắc chắn** `@PostFilter("filterObject.owner...")` hoạt động giống `List<Report>` trả trực tiếp; điều này phụ thuộc interceptor reactive/phiên bản.

Mẫu rõ ràng, ít phụ thuộc version:

```java
public Mono<List<Report>> listVisible(String trustedUsername) {
    return repository.findAllByOwner(trustedUsername)
        .collectList();
}
```

Với database R2DBC, việc query theo owner nên được thực hiện tại repository; sau đó controller có thể chọn trả `Flux<Report>` hoặc `Mono<List<Report>>` theo API contract.

### 5.5 Mono<Void>, void, Optional và scalar DTO

Bảng phân tích thực dụng:

| Return type | `@PostFilter` có ý nghĩa “loại từng record” không? | Lựa chọn đáng tin |
|---|---|---|
| `Flux<Report>` | Có nghĩa ở cấp **phần tử phát ra** khi interceptor reactive tương ứng hỗ trợ | Viết integration test theo version; ưu tiên query scoped |
| `Mono<Report>` | Chỉ có tối đa một phần tử để giữ/bỏ, không là policy 403 mặc định | `@PostAuthorize` được xác nhận hỗ trợ hoặc explicit access check |
| `Mono<List<Report>>` | Không mặc nhiên unwrap List để lọc từng Report | `flatMapMany/filter/collectList` hoặc repository query |
| `Mono<Map<String,Report>>` | Không mặc nhiên xem map entries như `Map` trực tiếp trong Servlet | Chuyển rõ thành `Flux<Map.Entry<...>>` nếu cần và test |
| `Mono<Void>` | Không có phần tử dữ liệu để lọc | `@PreAuthorize` hoặc authorization trong service |
| `void` / `Report` trả trực tiếp | Không phù hợp giả định reactive method trả Publisher | Dùng method imperative đúng context hoặc chuyển API |
| `List<Report>` trực tiếp | Có support trong **imperative**; không suy ra reactive | `@EnableMethodSecurity` trong đúng stack hoặc query scoped |
| `Stream<Report>` trực tiếp | Imperative filter khi Stream còn mở | Tránh dùng Stream DB bên ngoài transaction; với WebFlux dùng Flux |

### 5.6 Sau lọc vẫn có thể lộ dữ liệu ở nơi khác

`@PostFilter` không đảo ngược side effect đã xảy ra trong method: metrics chi tiết, cache, log, callback, sự kiện hay ghi dữ liệu bên ngoài vẫn có thể đã xử lý phần tử “bị xóa khỏi response”. Nó chỉ quản lý **những giá trị caller nhận** tại boundary được interceptor áp dụng. Không dùng làm ranh giới dữ liệu duy nhất trong hệ thống multi-tenant.

## 6. Lọc dữ liệu theo cơ chế Reactor: cách thay thế ổn định

Trong phần lớn ứng dụng WebFlux, lọc theo owner/tenant có thể viết ngay tại repository hoặc pipeline:

```java
public Flux<Report> reportsForCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMapMany(auth ->
            reportRepository.findByOwner(auth.getName()));
}
```

Đây là mảnh code cần repository/reactive SecurityContext và identity mapping thật. `findByOwner` phải dùng truy vấn có điều kiện owner đã xác minh, không phải nhận owner từ request. Với JWT multi-issuer, `auth.getName()` chưa chắc là user ID ổn định; cần ánh xạ source identity → internal ID đáng tin.

Lọc thêm bằng predicate:

```java
public Flux<Report> onlyOwned(
        Flux<Report> incoming, String trustedUsername) {
    return incoming.filter(
        report -> trustedUsername.equals(report.getOwner()));
}
```

Nếu quyền phải kiểm DB một cách non-blocking:

```java
public Flux<Report> allowed(
        Flux<Report> incoming, String trustedUserId) {
    return incoming.filterWhen(report ->
        permissions.canRead(trustedUserId, report.getId()));
}
```

Hai method trên là **mảnh code**; `permissions` là reactive service được định nghĩa ở ứng dụng. Khi `canRead` lỗi, để lỗi lan ra hoặc xử lý fail-closed; **không `onErrorReturn(true)`**. `filterWhen` có thể kích hoạt nhiều kiểm tra bất đồng bộ; giới hạn concurrency/buffer theo API Reactor và tải thật.

### 6.1 Khi nào ưu tiên query scoped thay vì post-filter?

| Trường hợp | Ưu tiên |
|---|---|
| Dataset nhỏ, giá trị đã được load cho mục đích khác, muốn thêm defense-in-depth | Có thể thêm `@PostFilter`/`filter` nếu đã test |
| Tìm kiếm có `page/size`, `sort`, `count` | Lọc ở repository trước phân trang; nếu lọc sau, metadata có thể sai |
| Dữ liệu đa tenant, dữ liệu riêng tư | `WHERE tenant_id = ? AND owner_id = ?`/RLS/permission join |
| Flux kéo theo nhiều I/O hoặc API streaming dài | Filter càng gần nguồn càng tốt; lưu ý backpressure, hủy, resource |
| Quyền phụ thuộc bản ghi và bên thứ ba | Dùng reactive authorization service, timeout, limit concurrency |
| Batch update cần all-or-nothing | Validate toàn bộ item và transaction, không âm thầm bỏ item |

`@PostFilter` không phải cơ chế thay thế query parameterized, database row-level security (RLS) hoặc service-level authorization.

## 7. Ví dụ Spring Boot 3.3 + WebFlux chạy được với test

Demo tập trung vào filtering ở service bean và phản hồi HTTP. Để giúp tách vấn đề annotation khỏi business rule, service có **hai nhóm endpoint**: các endpoint có `@PostFilter`/`@PreFilter` nhằm quan sát interceptor reactive; một endpoint có filter **tường minh** làm baseline ổn định. Test cho phép kiểm xem phiên bản đang dùng xử lý Flux đúng hay không; nếu không, đó là lỗi hỗ trợ cần giải quyết trước khi coi cấu hình bảo vệ dữ liệu.

**Lưu ý:** các username/password bên dưới chỉ dùng trong test/localhost. Spring Boot 3.3.13 và Spring Security 6.3 tương ứng được dùng làm **mốc học API**, không phải khuyến nghị triển khai production năm 2026.

### 7.1 Cấu trúc

```text
webflux-filter-method-security/
  settings.gradle
  build.gradle
  src/main/java/example/filter/FilterApplication.java
  src/main/java/example/filter/SecurityConfiguration.java
  src/main/java/example/filter/Report.java
  src/main/java/example/filter/ReportService.java
  src/main/java/example/filter/ReportController.java
  src/test/java/example/filter/ReportMethodSecurityTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-filter-method-security'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.filter'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-aop` được khai báo tường minh để làm rõ cơ chế Spring AOP proxy của method security. Application dùng user store in-memory, không có DB ngoài. Không thêm MVC starter.

### 7.2 Application

**src/main/java/example/filter/FilterApplication.java**

```java
package example.filter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterApplication.class, args);
    }
}
```

### 7.3 Authentication và bật method security reactive

**src/main/java/example/filter/SecurityConfiguration.java**

```java
package example.filter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-alice-only"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("dev-bob-only"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("dev-admin-only"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Phân tích:

- `@EnableReactiveMethodSecurity` đăng ký cơ chế Spring AOP cho method annotations; method phải thuộc bean Spring được gọi qua proxy.
- `anyExchange().authenticated()` ở HTTP layer yêu cầu một principal xác thực; method-level lọc chỉ tiếp tục giảm dữ liệu mà caller thấy.
- `httpBasic` dùng username/password in-memory. Mật khẩu hash bằng BCrypt; không dùng user/password demo trong production.
- `csrf(withDefaults())` giữ CSRF bật. POST/PUT/DELETE qua browser có thể cần token CSRF; test POST ở mục 7.7 thêm token bằng Spring Security Test. Không tắt CSRF chỉ vì đang học prefilter.

### 7.4 Model có JavaBean getter cho SpEL

**src/main/java/example/filter/Report.java**

```java
package example.filter;

public record Report(String id, String owner, String title) {

    public String getOwner() {
        return owner;
    }

    public String getId() {
        return id;
    }
}
```

Record giúp trả JSON gọn. Hai getter làm rõ việc SpEL sử dụng property `owner` và `id`. Đây là DTO cho demo, không chứa dữ liệu nhạy cảm. Trong dự án thật, không để caller tự gán `owner` rồi coi trường đó đã được xác minh.

### 7.5 Service: annotation filter và baseline tường minh

**src/main/java/example/filter/ReportService.java**

```java
package example.filter;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReportService {

    private Flux<Report> sample() {
        return Flux.just(
            new Report("R-1", "alice", "Alpha"),
            new Report("R-2", "bob", "Beta"),
            new Report("R-3", "alice", "Gamma"));
    }

    // Đối tượng trả về: lọc từng Report theo owner hoặc role ADMIN.
    @PreAuthorize("hasRole('USER')")
    @PostFilter(
        "filterObject.owner == authentication.name or hasRole('ADMIN')")
    public Flux<Report> visibleViaAnnotation() {
        return sample();
    }

    // Đối tượng đầu vào: thử lọc Flux<Report> trước khi method xử lý.
    @PreAuthorize("hasRole('USER')")
    @PreFilter(
        "filterObject.owner == authentication.name or hasRole('ADMIN')")
    public Flux<Report> previewViaAnnotation(Flux<Report> input) {
        return input;
    }

    // Baseline không dựa vào @PostFilter: filter theo danh tính
    // lấy trực tiếp từ Reactor Context do Spring Security tạo.
    @PreAuthorize("hasRole('USER')")
    public Flux<Report> visibleExplicitly() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMapMany(auth -> {
                boolean admin = auth.getAuthorities().stream()
                    .anyMatch(a ->
                        "ROLE_ADMIN".equals(a.getAuthority()));

                if (admin) {
                    return sample();
                }
                return sample().filter(
                    r -> auth.getName().equals(r.getOwner()));
            });
    }
}
```

**Lưu ý thiết kế và kiểm thử:**

1. `visibleViaAnnotation()` và `previewViaAnnotation(...)` là hai signature **mục tiêu để kiểm tra reactive filter interceptor** trong Spring Security 6.3.x. Test bên dưới là tiêu chuẩn chấp nhận; nếu không đạt phải sửa implementation hoặc dùng cách tường minh, **không xem annotation là đã bảo vệ data**.
2. `sample()` chỉ tạo một Flux in-memory nên có thể dùng làm demo về điều kiện filter. Với DB/Redis thật, không trả toàn bộ dữ liệu rồi dựa hoàn toàn vào postfilter.
3. `visibleExplicitly()` là baseline xác thực bằng Reactor Context và lọc `Flux<Report>` rõ ràng; tránh việc đoán khả năng của annotation theo wrapper type.
4. `@PreAuthorize` yêu cầu role USER cho cả ba method. Admin trong demo có thêm ROLE_USER, nên có thể đi vào từng method. Nếu admin không có USER, phải sửa expression theo role chính sách.
5. Service là bean riêng khỏi controller: cuộc gọi từ controller đi **qua Spring AOP proxy**. Gọi `this.visibleViaAnnotation()` trong chính ReportService có thể bypass interceptor method security.
6. Đoạn lọc bằng `owner` chỉ dành cho demo; với multi-tenant, cần điều kiện tenant/permission đầy đủ ở DB và xử lý trust boundary.

### 7.6 Controller

**src/main/java/example/filter/ReportController.java**

```java
package example.filter;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/api/reports/annotation")
    public Flux<Report> annotation() {
        return reports.visibleViaAnnotation();
    }

    @GetMapping("/api/reports/explicit")
    public Flux<Report> explicit() {
        return reports.visibleExplicitly();
    }

    @PostMapping("/api/reports/preview")
    public Flux<Report> preview(@RequestBody Flux<Report> input) {
        return reports.previewViaAnnotation(input);
    }

    @GetMapping("/api/public")
    public Flux<String> publicEndpoint() {
        return Flux.just("public");
    }
}
```

Controller trả Publisher để WebFlux quản lý subscription; không tự `block()` hoặc `subscribe()`. Phương thức POST là **preview** không ghi DB, nhưng vẫn là HTTP unsafe method và CSRF được giữ bật để mô phỏng chính sách API stateful. Nếu muốn gửi body JSON array, WebFlux sẽ decode các phần tử theo decoder phù hợp của `Flux<Report>`; client cần `Content-Type: application/json`.

### 7.7 Test tự động bằng WebTestClient

**src/test/java/example/filter/ReportMethodSecurityTest.java**

```java
package example.filter;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReportMethodSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsPublic() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(String.class)
            .contains("public");
    }

    @Test
    void protectedEndpointRejectsAnonymous() {
        client.get().uri("/api/reports/annotation")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void annotationPostFilterForAlice() {
        client.get().uri("/api/reports/annotation")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2)
            .contains(
                new Report("R-1", "alice", "Alpha"),
                new Report("R-3", "alice", "Gamma"));
    }

    @Test
    void annotationPostFilterForAdmin() {
        client.get().uri("/api/reports/annotation")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(3);
    }

    @Test
    void explicitFilteringIsEquivalentForAlice() {
        client.get().uri("/api/reports/explicit")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2);
    }

    @Test
    void preFilterDropsForeignInputForAlice() {
        List<Report> input = List.of(
            new Report("R-1", "alice", "Alpha"),
            new Report("R-2", "bob", "Beta"),
            new Report("R-3", "alice", "Gamma"));

        client.mutateWith(csrf()).post().uri("/api/reports/preview")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2);
    }

    @Test
    void preFilterKeepsAllForAdmin() {
        List<Report> input = List.of(
            new Report("R-1", "alice", "Alpha"),
            new Report("R-2", "bob", "Beta"));

        client.mutateWith(csrf()).post().uri("/api/reports/preview")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2);
    }

    @Test
    void postWithoutCsrfIsDenied() {
        client.post().uri("/api/reports/preview")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(List.of(
                new Report("R-1", "alice", "Alpha")))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy:

```bash
gradle test
```

Đây là **8 test method**. Kết quả kỳ vọng trong môi trường hỗ trợ đúng reactive filter `Flux`: tất cả PASS. Nếu **test về `@PreFilter` hoặc `@PostFilter` thất bại**, phải coi đó là phát hiện tương thích/implementation quan trọng (đặc biệt ở bản minor/patch hoặc method parameter conversion), không bỏ qua. Các test về explicit filtering và 401/CSRF cung cấp baseline để khoanh vùng lỗi.

**Không coi kỳ vọng là bằng chứng đã chạy test:** các ví dụ được soạn và rà soát API, chưa chạy Gradle trên máy trong tài liệu. Trước khi triển khai hãy thực sự chạy `gradle test` với **đúng dependency lockfile**, quan sát stack trace và kiểm tra không có user ngoại phạm vi trong JSON. Nếu bản đã chọn không hỗ trợ filter Flux như ý, thay bằng `filter/filterWhen` hoặc query scoped, rồi cập nhật kiểm thử theo cách mới.

### 7.8 Chạy HTTP thủ công

```bash
gradle bootRun

# Không cần login:
curl -i http://localhost:8080/api/public

# Cần login:
curl -i http://localhost:8080/api/reports/annotation

# Curl CLI sẽ hỏi mật khẩu; nhập dev-alice-only
curl -i -u alice http://localhost:8080/api/reports/annotation

# Curl CLI sẽ hỏi mật khẩu; nhập dev-admin-only
curl -i -u admin http://localhost:8080/api/reports/annotation
```

Với PowerShell, nếu `curl` là alias, sử dụng `curl.exe`. Không ghi mật khẩu vào command-line argument trong tài liệu production. Muốn thử POST có CSRF từ một HTTP client thật, phải có cơ chế cấp token CSRF theo policy và gửi lại qua header/field hợp lệ; `mutateWith(csrf())` chỉ dùng trong test.

## 8. Reactive method security hoạt động qua AOP và Reactor Context

Dù annotation được đặt trên method, Spring Security dùng Spring AOP để “bọc” method của bean. Điều kiện then chốt:

1. **Method thuộc bean do Spring quản lý.** Một object tạo bằng `new ReportService()` ngoài ApplicationContext không được Spring proxy xử lý.
2. **Lời gọi phải đi qua proxy.** `this.someAnnotatedMethod()` (self-invocation) trong cùng class có thể không đi qua interceptor.
3. **Method/reactive type phải tương thích.** Ví dụ `Flux<T>` chạy deferred, Spring Security lấy Authentication từ Reactor Context của subscription, không phải bằng cách đọc ThreadLocal như ứng dụng Servlet.
4. **Authentication phải được thiết lập.** WebFlux Security thường đưa context vào request pipeline; gọi service từ job/test ngoài HTTP cần gắn authentication đúng cách khi kiểm thử.
5. **Thứ tự interceptor quan trọng khi kết hợp.** `@PreAuthorize`, `@PreFilter`, `@PostAuthorize`, `@PostFilter` thuộc các advisor khác nhau. Không mặc định chúng là một phép kiểm duy nhất; kiểm thử thứ tự/lỗi khi vừa lọc vừa deny.
6. **Không tự subscribe trong service.** Trả Publisher để framework xử lý, không gọi `.block()` trên event loop.

Ví dụ đọc Principal đáng tin trong pipeline:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

Đây là method minh họa. Nếu không có security context, Mono có thể rỗng. Không dùng `SecurityContextHolder.getContext()` kiểu ThreadLocal làm nguồn danh tính mặc định trong WebFlux service.

## 9. Test ma trận kiểu trả về và phiên bản

Không thể kiểm tra an toàn chỉ bằng “code compile”. Bởi annotation là AOP và có thể hoạt động khác nhau theo runtime/interceptor, cần test hành vi.

| Trường hợp | Test nên viết | Lỗi cần phát hiện |
|---|---|---|
| `@PreFilter` trên `Flux<Report>` | Input của Alice có record của Bob; output/side effect chỉ chứa Alice | Chưa bật interceptor, publisher không được filter, sai SpEL |
| `@PostFilter` trên `Flux<Report>` | Output từ nguồn có Alice/Bob; Alice chỉ thấy của Alice | Filter chỉ chạm publisher wrapper hoặc không chạy |
| `@PostFilter` trên `Mono<Report>` | Một record thuộc người khác; xác định chính xác empty/deny của version | Nhầm empty response với 403 |
| `@PostFilter` trên `Mono<List<Report>>` | List hai owner; xem annotation có unwrap không hoặc fail | Tưởng filter từng element nhưng không |
| `@PreFilter` với hai input filterable | Dùng `filterTarget`, test đúng tham số được lọc | Filter sai argument |
| `@PreFilter` trên scalar | Khẳng định configuration phản ứng phù hợp hoặc thay `@PreAuthorize` | Dùng sai mục đích annotation |
| `@PostFilter` trên `Map`/`Stream` | Chỉ trong cấu hình/API imperative có tài liệu hỗ trợ | Nhầm nhánh Servlet với Reactive |
| Không có authentication | Endpoint/method bảo vệ từ chối như dự định | Expose dữ liệu qua anonymous/empty |
| ADMIN vs USER | ADMIN nhận đúng policy, USER bị lọc | Role prefix/authorities sai |
| Gọi method từ cùng bean | Test self-invocation có thể bypass | Đặt annotation mà không hề enforce |
| Dataset lớn, phân trang | Kiểm `count`, `hasNext`, sort sau policy | Lọc quá muộn, thiếu/sai page |
| Nâng Spring Security 6.3 → 6.5/7.x | Chạy lại toàn bộ integration suite | Thay đổi signature hoặc type handling |

**Hành vi test phải được “chốt” theo phiên bản đã triển khai**, không chỉ in logs. Đặc biệt, một annotation có thể **tồn tại và compile** nhưng không bảo vệ đúng kiểu return/wrapper mà bạn dự kiến.

### Thao tác kiểm thử khi nâng cấp

1. Ghi rõ version **Spring Boot**, **Spring Security**, **Spring Framework**, **Reactor**, JDK và runtime.
2. Kiểm tra dependency graph/lockfile để phát hiện Spring Security modules lệch version.
3. Đọc reference/Javadoc theo nhánh version tương ứng cho reactive interceptors.
4. Kiểm thử data fixtures có cả record được phép và không được phép, bao gồm empty/error.
5. Test HTTP JSON **và** direct bean invocation qua Spring ApplicationContext (để tránh lỗi serializer che vấn đề).
6. Test quyền trên nhiều tenant, user disabled, role thiếu, token giả, context missing và reactive scheduler boundary.
7. Kiểm tra performance: cả số record DB trả và số record được lọc, latency memory/CPU, khi stream lớn.
8. Chỉ sau khi hành vi bảo vệ được chứng minh bằng test mới xem annotation là guardrail đáng tin của cấu hình đó.

## 10. Bảo vệ thực sự: giới hạn trong DB và phân quyền theo dữ liệu

Trong production, việc lấy `authentication.name` rồi so với `filterObject.owner` chưa đủ cho mọi hệ thống:

- Username có thể thay đổi, không phải internal user ID bền vững.
- Với JWT/OIDC, `Authentication.getName()` có thể ánh xạ từ `sub`; khi có nhiều issuer, `sub` cần ràng buộc issuer và tenant.
- Các record có thể được chia sẻ theo ACL/group/organization, không đơn giản là chủ sở hữu bằng username.
- Một record đã lọc khỏi HTTP response vẫn có thể đã bị đọc/ghi vào cache, telemetry hoặc sự kiện nội bộ.
- Pagination sau filter có thể làm rỗng trang hoặc sai tổng số.
- Loại phần tử âm thầm trong batch ghi có thể trái với transactional semantics.

Ví dụ repository query cho R2DBC:

```java
public interface ReportRepository
        extends ReactiveCrudRepository<ReportEntity, String> {

    Flux<ReportEntity> findAllByTenantIdAndOwnerId(
        String tenantId, String ownerId);
}
```

Đây là **mảnh interface** cần entity/R2DBC mapping đúng, Spring Data dependency và trusted IDs; không chạy độc lập trong demo in-memory. Điểm quan trọng: **ràng buộc tenant/owner ngay trong query**. Nếu quyền phức tạp, dùng security policy/permission service và audit phù hợp; với JPA/JDBC sync cần blocking boundary khi gọi trong WebFlux.

Một mẫu kiểm quyền trước khi truy cập bản ghi:

```java
Mono<ReportDto> loadVisible(
        String reportId, String trustedTenant, String trustedUser) {
    return repository.findByIdAndTenantAndOwner(
            reportId, trustedTenant, trustedUser)
        .map(this::toSafeDto);
}
```

Đoạn này chỉ là **pseudocode Java**; chính sách 403/404 cho bản ghi không tìm thấy, mapping identity và phương thức repository tùy ứng dụng. Nó minh họa rằng bộ lọc an toàn nhất không cần tải record ngoài quyền về bộ nhớ.

## 11. Chẩn đoán lỗi @PreFilter / @PostFilter

### Không thấy lọc gì

- Kiểm tra `@EnableReactiveMethodSecurity` đã được bật trên config đúng context.
- Method có được gọi qua **Spring bean proxy** không, hay `this.method()`/`new`?
- Annotation nằm trên method/implementation mà proxy nhìn thấy chưa? Với interface/class, inspect advisor và điểm đặt method.
- Expression `filterObject.owner` có truy cập được property không?
- Authentication ở Reactor Context là user mong đợi? Có Basic/JWT hợp lệ không?
- Return type là `Flux<Report>` hay `Mono<List<Report>>`? Đừng lẫn.
- Phiên bản Spring Security module đang chạy có cùng phiên bản và support loại Publisher/argument đang dùng không?
- Test có chứa cả record đúng và sai owner không? Nếu chỉ có record đúng, việc filter bị bỏ qua vẫn cho ra test pass.

### Lỗi SpEL hoặc runtime exception

- Với Map, expression thường phải dùng `filterObject.value.owner`.
- Với property Java record, có thể dùng getter rõ ràng hoặc biểu thức được xác minh bằng test.
- Nếu dùng `filterTarget`, xác nhận tên tham số tồn tại trong metadata.
- Nếu dùng reactive expression cần truy vấn DB, không gọi blocking repository từ SpEL trên event-loop; sử dụng reactive authorization phù hợp hoặc xử lý ở service.
- Nếu annotation được viết theo ví dụ Servlet, tra đúng Javadoc `PreFilterAuthorizationReactiveMethodInterceptor`/`PostFilterAuthorizationReactiveMethodInterceptor`.
- Không tự catch mọi lỗi rồi `onErrorReturn(true)` hoặc trả unfiltered data cho client.

### Lọc đúng nhưng API vẫn sai

- `@PostFilter` có thể gây list ngắn bất thường so với metadata pagination.
- Nếu batch chỉ xử lý một phần input, response phải công bố partial success hoặc từ chối batch theo policy.
- Nếu service đã side-effect trước khi lọc, việc loại phần tử khỏi response không đảo ngược side-effect.
- Nếu có stream lớn, lỗi quyền ở cuối stream có thể xảy ra sau khi client đã nhận một phần body; không nên đặt quyền quan trọng ở cuối pipeline.
- Nếu client hỏi một resource duy nhất, trả rỗng không phải lúc nào cũng tương đương 403/404; thiết kế explicit authorization.

## 12. Checklist triển khai thực tế

1. Xác nhận ứng dụng đang dùng WebFlux/reactive, không nhầm cấu hình Servlet.
2. Bật `@EnableReactiveMethodSecurity`, có request-level Security chain và authentication đúng.
3. Chỉ annotate method thuộc Spring bean được gọi qua proxy.
4. Đọc Javadoc/ref đúng Spring Security version, đặc biệt typed support cho reactive pre/post filter.
5. Với `Flux<T>`, viết test **có cả phần tử hợp lệ và không hợp lệ**. Với `Mono<List<T>>`, không suy từ `Flux<T>`.
6. Với single-resource `Mono<T>`, định nghĩa rõ status khi không được phép; đừng tự xem filter empty là deny.
7. Với `@PreFilter` trên batch ghi, xác định all-or-nothing hay partial success, audit và transaction semantics.
8. Bảo vệ data ngay từ repository/query; dùng annotation như defense-in-depth khi phù hợp, không thay cho tenant isolation.
9. Kiểm thử CSRF cho browser/cookie, xử lý credential/role đúng, không tắt security vì test fail.
10. Kiểm tra nguyên nhân khi migration thay interceptor config, classloader, version hoặc target method.
11. Với async jobs, queue, scheduled tasks, xác định Reactor Context/Authentication được truyền như thế nào.
12. Theo dõi latency, DB rows scanned, số record bị lọc, cache/log leak và security exception.
13. Không trả nguyên `Authentication`, password hash, access token hay tenant secret trong dữ liệu/filter logs.
14. Chỉ rollout sau khi integration tests chứng minh server **không bao giờ trả record ngoại phạm vi** cho caller bị hạn chế.

## 13. Bài tập tự luyện

1. Viết `@PreFilter("filterObject.owner == authentication.name")` cho một input collection trong Spring Security **imperative**, rồi viết test phân biệt việc lọc input với việc deny cả method.
2. Viết `@PostFilter` cho `Flux<Report>` trong WebFlux (Spring Security 6.3), test Alice/Bob/Admin và đối chiếu baseline `Flux.filter(...)`.
3. Đổi signature trả thành `Mono<List<Report>>` mà giữ annotation. Kết quả của version bạn đang dùng là gì? Đừng đoán; chứng minh bằng test.
4. Với một method `Mono<Report>`, thiết kế trả 403/404 cho ID không thuộc caller bằng kiểm quyền ở repository/service thay vì chỉ dùng `@PostFilter`.
5. Với `Map<String,Report>` trong method imperative, giải thích vì sao `filterObject.value.owner` khác `filterObject.owner`.
6. Tạo bài test self-invocation: method A gọi `this.annotatedMethod()`. Quan sát vì sao có thể bypass proxy, sau đó tách thành bean khác.
7. Viết query R2DBC có `tenant_id` và `owner_id` để phân trang sau khi lọc quyền; so sánh với `findAll().filter(...)`.
8. Thiết kế API batch write có một record không thuộc user. Chọn **fail entire batch** hoặc **partial success** và định nghĩa response, audit, transaction.
9. Chạy cùng bộ test trên Spring Security 6.3 và 6.5/7.x; ghi rõ thay đổi, không chỉ check biên dịch.
10. Dùng `Flux.filterWhen(...)` với quyền kiểm tra async theo từng record, kiểm soát concurrency và fail closed khi repository lỗi.

## Tóm tắt

- **`@PreFilter`** lọc phần tử **đầu vào** trước khi method xử lý; **`@PostFilter`** lọc phần tử **đầu ra** sau khi method cung cấp kết quả.
- Hai annotation **không tương đương `@PreAuthorize`/`@PostAuthorize`**: lọc thường giữ/bỏ phần tử, trong khi authorize quyết định cấp/từ chối quyền.
- Với Spring Security **Servlet**, có tài liệu hỗ trợ các collection, array, map và stream; với **Reactive/WebFlux** có các interceptor lọc reactive từ Spring Security 5.8, nhưng **kiểu Publisher, wrapper và phiên bản cụ thể phải được kiểm chứng bằng integration test**.
- `Flux<T>`, `Mono<T>` và `Mono<List<T>>` **không phải một kiểu dữ liệu**. Đừng mặc định annotation tự lọc sâu từng phần tử trong wrapper.
- Với dữ liệu nhạy cảm, tenant và batch write, **lọc tại repository + kiểm quyền rõ ràng + test âm tính** luôn quan trọng hơn phụ thuộc một lớp post-filter.

## Tài liệu tham khảo chính thức

1. Spring Security 6.3 — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
2. Spring Security 6.5 — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
3. Spring Security 7.0 — Reactive Method Security (đối chiếu khi nâng cấp): https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/method.html
4. Spring Security 6.3 — PreFilterAuthorizationReactiveMethodInterceptor Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/authorization/method/PreFilterAuthorizationReactiveMethodInterceptor.html
5. Spring Security 6.3 — PostFilterAuthorizationReactiveMethodInterceptor Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html
6. Spring Security 6.5 — Servlet Method Security, hỗ trợ Collection/array/Map/Stream: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
7. Spring Security 6.5 — Reactive Test Support: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
8. Spring Framework — Spring AOP proxy và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
