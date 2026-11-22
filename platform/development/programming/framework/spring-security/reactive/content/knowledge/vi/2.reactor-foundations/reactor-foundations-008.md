# Ảnh hưởng của lỗi, hủy đăng ký và backpressure đến tác vụ bảo mật trong Spring Security Reactive

## 1. Tại sao đây là một chủ đề bảo mật?

Trong Spring WebFlux, xác thực, phân quyền, truy vấn dữ liệu, phát phản hồi và ghi nhận sự kiện thường được nối thành các luồng **Mono** hoặc **Flux**. Luồng không chỉ trả về giá trị; nó còn có tín hiệu lỗi, tín hiệu hủy đăng ký và cơ chế điều phối nhu cầu dữ liệu (**backpressure**). Các tín hiệu này quyết định tác vụ bảo mật đã thực sự chạy, hoàn thành, bị dừng hay đang gây áp lực lên tài nguyên.

Ví dụ:

- Dịch vụ kiểm tra quyền bị lỗi. Nếu lập trình viên thay lỗi bằng giá trị “cho phép”, dữ liệu bí mật có thể bị lộ.
- Client đóng kết nối khi API vừa ghi một phần dữ liệu. Thao tác bảo mật hoặc audit nối ở cuối luồng có thể không chạy đến bước đó.
- Một Flux phát quá nhanh hoặc xử lý quá nhiều request song song. Việc kiểm tra quyền, giải mã token hay lưu audit có thể bị nghẽn, làm cạn tài nguyên dù chính sách quyền là đúng.

**Mục tiêu của bài:** hiểu ngữ nghĩa Reactor để giữ nguyên nguyên tắc **không cấp quyền khi chưa có quyết định hợp lệ (fail closed)**, xử lý hủy an toàn, và kiểm soát tài nguyên khi lưu lượng cao.

## 2. Nền tảng: vòng đời của một Publisher

Mono phát tối đa một giá trị; Flux có thể phát nhiều giá trị. Sau khi có **subscribe**, Subscriber nhận Subscription và điều phối dữ liệu với **request(n)**. Trong một luồng bình thường:

~~~text
subscribe
   |
   v
onSubscribe(Subscription)
   |
   +-- request(n) --> onNext(value) ... --> onComplete
   |
   +-- request(n) --> onNext(value) ... --> onError(error)
   |
   +-- cancel()   --> yêu cầu ngừng luồng, giải phóng tài nguyên
~~~

Các ý quan trọng:

1. **onNext** mang dữ liệu; **onComplete** đánh dấu hoàn thành bình thường; **onError** đánh dấu luồng thất bại. onComplete và onError loại trừ nhau và kết thúc chuỗi tín hiệu tới Subscriber.
2. **cancel()** là lệnh hủy Subscription, không phải một onError hoặc onComplete được gửi xuống Subscriber. Trong Reactor, **doFinally** có thể quan sát cả ON_COMPLETE, ON_ERROR và CANCEL.
3. **request(n)** cho biết số phần tử downstream đang sẵn sàng nhận. Nó được truyền ngược về upstream nhưng có thể được các operator biến đổi theo cách riêng.
4. Publisher thường **lazy**: mô tả Mono/Flux chưa đồng nghĩa tác vụ đã chạy. Việc subscribe mới kích hoạt xử lý; có thể có nhiều lần subscribe và nhiều lần thực thi.
5. **Reactor Context** mang dữ liệu theo chuỗi subscriber, bao gồm SecurityContext mà Spring Security Reactive sử dụng. Không nên coi ThreadLocal trên thread hiện tại là nguồn sự thật của danh tính khi pipeline đổi thread.

Bảng phân biệt:

| Tín hiệu/trạng thái | Kết quả luồng | Rủi ro bảo mật cần xét |
| --- | --- | --- |
| onComplete | Đã kết thúc bình thường | Chỉ ghi nhận thành công nếu toàn bộ thao tác bắt buộc đã hoàn tất |
| onError | Kết thúc vì lỗi | Không đổi lỗi kiểm tra quyền thành kết quả được phép; xử lý HTTP và log an toàn |
| cancel() | Downstream ngừng quan tâm/đã hủy | Audit cuối luồng có thể không chạy; ghi dữ liệu từ xa có thể vẫn đã xảy ra |
| request(n) | Cho phép nhận tối đa n phần tử theo nhu cầu tại điểm này | Không nhầm backpressure với rate limiting hay giới hạn chi phí tác vụ |
| timeout | Thường phát lỗi cho downstream và hủy nguồn phía trước | Có thể gây CANCEL ở nhánh trước timeout; không nên dùng timeout để tự mặc định cấp quyền |

**Lưu ý:** doFinally đặt ở hai vị trí khác nhau có thể thấy hai SignalType khác nhau. Chẳng hạn khi timeout hủy upstream và phát TimeoutException xuống downstream, upstream có thể quan sát CANCEL còn phần downstream quan sát ON_ERROR. Khi đo metric phải ghi rõ quan sát ở vị trí nào trong pipeline.

## 3. Lỗi (onError) tác động thế nào đến xác thực và phân quyền?

### 3.1. Lỗi làm dừng luồng, nhưng operator phục hồi có thể thay thế kết quả

Một lỗi từ ReactiveAuthenticationManager, nơi truy xuất khóa xác minh JWT, dịch vụ policy, hay kho dữ liệu dùng để kiểm tra owner/tenant sẽ đi theo onError nếu không được xử lý. Operator **onErrorResume**, **onErrorReturn**, **onErrorComplete** có thể thay thế hoặc nuốt tín hiệu lỗi. Đây là tính năng hữu ích cho xử lý nghiệp vụ thông thường nhưng rất nguy hiểm nếu áp dụng rộng quanh quyết định an ninh.

Ví dụ **sai, fail open**:

~~~java
// Minh họa lỗi: mất kết nối policy service lại được hiểu là có quyền.
Mono<Boolean> allowed = permissionService.canRead(user, documentId)
        .onErrorReturn(true);

// Sau đó code thấy true và phát tài liệu dù policy chưa xác nhận.
~~~

Ví dụ **an toàn hơn, fail closed**:

~~~java
// Minh họa tích hợp; các service và biến là thành phần của ứng dụng.
Mono<Boolean> allowed = permissionService.canRead(user, documentId)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Authorization decision unavailable")));

// Lỗi kỹ thuật vẫn là lỗi; false vẫn bị từ chối.
return allowed.flatMapMany(granted -> {
    if (!granted) {
        return Flux.error(new AccessDeniedException("Access denied"));
    }
    return Flux.defer(() -> documentRepository.readForUser(user, documentId));
});
~~~

**Điều kiện phải đúng trong ví dụ:** canRead trả Mono<Boolean> với true/false rõ ràng; Mono.empty không được hiểu là true. **AccessDeniedException** là kiểu của Spring Security. Đoạn trên không phải file Java độc lập; nó minh họa logic bên trong một service đã có các đối tượng tương ứng.

Không biến mọi lỗi kỹ thuật thành HTTP 403: một policy service hỏng có thể cần trả 503 hoặc 500 được xử lý an toàn, nhưng **không được trả dữ liệu khi quyết định chưa thành công**. Phân biệt lỗi xác thực (thường 401), từ chối quyền (thường 403) và lỗi hệ thống; hành vi HTTP thực tế còn tùy entry point và cấu hình exception handler.

### 3.2. Không vô tình thay đổi thứ tự bảo vệ dữ liệu

**Nguyên tắc:** kiểm tra quyền trước khi bắt đầu phát tài nguyên được bảo vệ. Dùng thenMany chỉ khi publisher kiểm tra quyền có hợp đồng: **hoàn thành chỉ khi được phép, phát lỗi khi từ chối**.

~~~java
// Pseudocode: requireReadAccess trả Mono<Void>, lỗi khi không có quyền.
return permissionService.requireReadAccess(user, documentId)
        .thenMany(Flux.defer(() ->
                documentRepository.streamReadableItems(user, documentId)));
~~~

Ngược lại, nếu requireReadAccess trả Mono.empty để biểu thị “không được phép” thì thenMany vẫn chạy khi Mono hoàn thành: đó là lỗi thiết kế giao kèo, không phải cơ chế bảo vệ. Nếu dùng Mono<Boolean>, luôn kiểm tra true/false tường minh như ví dụ trước.

Đừng phát các phần tử bí mật trước rồi mới kiểm tra quyền ở cuối Flux. Nếu đã gửi một phần dữ liệu qua HTTP streaming, lỗi xảy ra sau đó không thể thu hồi byte đã gửi.

### 3.3. Retry có thể lặp lại nhiều công việc

**retry** và **retryWhen** thường tạo subscription mới khi nguồn lỗi. Một lần retry có thể chạy lại truy vấn, xác thực, log hoặc hành động ghi nếu pipeline đặt chúng bên trong nguồn được subscribe lại.

- Với **đọc thuần túy**, retry có giới hạn, timeout và điều kiện lỗi chọn lọc đôi khi phù hợp.
- Với **đăng nhập**, retry vô hạn có thể làm tăng tải dịch vụ danh tính, gây khóa tài khoản hoặc làm lệch audit.
- Với **ghi tiền/giao dịch/phân quyền**, retry sau timeout có thể lặp thao tác mà lần đầu đã thực hiện. Cần idempotency key, ranh giới transaction và chiến lược đối soát.
- Không retry mọi AccessDeniedException: quyền bị từ chối không phải lỗi tạm thời cần thử liên tục.

Một lời gọi trả lỗi không đồng nghĩa tác dụng phụ của hệ thống ngoài chưa xảy ra. Timeout hoặc mất kết nối chỉ cho biết client chưa thấy kết quả cuối cùng.

### 3.4. Đặt handler tại đúng lớp

- Xác thực: giữ lỗi xác thực theo đường xử lý của Spring Security, không che thành một principal giả.
- Phân quyền: giữ trạng thái từ chối, không dùng fallback trả secret hoặc bỏ qua item thất bại.
- Nghiệp vụ: có thể xử lý lỗi kỹ thuật có chọn lọc, trả lỗi có kiểm soát mà không tiết lộ credential, stack trace hay dữ liệu nội bộ.
- Lập trình reactive: tránh **onErrorContinue** trong pipeline bảo mật vì cơ chế bỏ qua phần tử bị lỗi dễ làm mất một kiểm tra bắt buộc hoặc tạo kết quả không nhất quán.
- Quan sát: **doOnError** phù hợp để tăng counter/ghi log ngắn, nhưng không tự phục hồi luồng. Không log raw token, mật khẩu hay dữ liệu nhạy cảm.

## 4. Hủy đăng ký (cancellation) và tác vụ bảo mật

### 4.1. Khi nào xảy ra cancel?

- Client đóng kết nối hoặc hủy tải stream.
- Một operator như **take(n)** đã nhận đủ phần tử và hủy phần còn lại upstream.
- **timeout** hủy nguồn xử lý chậm, trong khi nhánh downstream nhận TimeoutException.
- **switchMap** hủy tác vụ trước khi có giá trị mới; thao tác tìm kiếm có thể bị thay thế.
- Hủy theo vòng đời request hoặc giải phóng subscription.

Cancel nói rằng bên nhận không tiếp tục yêu cầu dữ liệu. Nó **không** có nghĩa mọi thao tác bên ngoài đã rollback, mọi thread đã bị ngắt hoặc mọi I/O chắc chắn dừng ngay lập tức. Một lệnh đã gửi tới database, message broker hoặc API bên ngoài có thể vẫn hoàn tất.

### 4.2. Chọn hook quan sát đúng

~~~java
Flux<Event> stream = eventService.findEvents()
        .doOnComplete(() -> metrics.recordCompleted())
        .doOnError(error -> metrics.recordFailed())
        .doOnCancel(() -> metrics.recordCancelled())
        .doFinally(signalType -> metrics.recordTerminal(signalType));
~~~

Đoạn minh họa sử dụng đối tượng Event, eventService, metrics thuộc ứng dụng. **doOnComplete** không chạy trên nhánh onError hoặc cancel; **doOnError** không chạy trên cancel. **doFinally** quan sát cả ba kiểu kết thúc và cho biết SignalType. Callback này dùng tốt cho metric nhẹ, không nên đặt I/O blocking trên event loop.

**Quan trọng:** doFinally chạy khi luồng đã phát tín hiệu kết thúc xuống downstream, nên với luồng bất đồng bộ việc quan sát side effect trong test ngay sau khi downstream hoàn thành có thể cần cơ chế đồng bộ phù hợp. Cũng không được coi callback doFinally là cam kết durable audit.

### 4.3. Đừng đặt audit bắt buộc ở một bước có thể bị bỏ qua

Mẫu sai:

~~~java
// Sai nếu việc ghi audit là nghĩa vụ bắt buộc.
return protectedService.process(request)
        .flatMap(result -> auditService.persistSuccess(result)
                .thenReturn(result));
~~~

Nếu client hủy trong lúc process chạy, bước flatMap phía sau có thể chưa được subscribe; auditSuccess không chạy. Gọi auditService bên trong doFinally rồi tự subscribe cũng không bảo đảm thành công, đồng thời tạo công việc tách rời vòng đời request, khó kiểm soát lỗi và ngữ cảnh bảo mật.

Thiết kế theo yêu cầu nghiệp vụ:

1. **Metric/telemetry best effort:** đếm lỗi, cancel và latency bằng doFinally/doOnCancel; giữ callback không blocking, tránh dữ liệu nhạy cảm.
2. **Audit của quyết định quyền trước khi phát dữ liệu:** nối audit vào pipeline *trước* nguồn phát; chỉ cho phép bắt đầu đọc dữ liệu sau khi bước audit bắt buộc hoàn thành. Nếu bị hủy trước đó, dữ liệu không nên được gửi.
3. **Audit gắn với thao tác ghi đã commit:** dùng transaction và **transactional outbox** hoặc cơ chế server-side bền vững tương đương. Sự kiện audit phải liên kết với commit nghiệp vụ, độc lập chuyện HTTP client còn kết nối.
4. **Dọn dẹp tài nguyên:** dùng cơ chế đóng tài nguyên được thiết kế cho error/cancel, như **using**, **usingWhen** hoặc API transaction tương ứng; kiểm tra semantics của cleanup bất đồng bộ. Không hiểu “cancel đã được gửi” là “mọi cleanup chắc chắn xong”.

Cần phân biệt **access attempt**, **authorization decision**, **business commit** và **response delivered**. Đây là bốn sự kiện khác nhau, nhất là khi timeout, retry hoặc client disconnect.

### 4.4. Tránh mất SecurityContext do tự subscribe

Trong Spring Security Reactive, danh tính của request được truyền qua Reactor Context. Nếu bên trong handler tự gọi subscribe() cho một publisher audit/kiểm tra quyền, ta tạo subscription riêng với vòng đời và khả năng truyền Context khác. Nó có thể không nhận đúng thông tin người dùng hoặc lỗi bị bỏ qua.

Hãy **trả về** hoặc **kết hợp** Mono/Flux để framework quản lý subscription; khi cần tác vụ bền vững ngoài request, truyền thông tin nghiệp vụ cần thiết một cách rõ ràng vào message/event đã xác thực và thiết kế worker tin cậy riêng.

## 5. Backpressure ảnh hưởng gì đến bảo mật?

### 5.1. Backpressure thực sự điều khiển phần tử, không điều khiển mọi loại tải

Trong Reactive Streams, Subscriber yêu cầu n phần tử qua request(n); nguồn và operator hợp tác để không đẩy quá nhu cầu tại giao diện đó. Có thể có operator **prefetch** hoặc buffering nên lượng công việc upstream khác lượng dữ liệu cuối cùng đang hiển thị.

Ví dụ một Flux chỉ được yêu cầu 2 phần tử: nguồn như Flux.range sẽ phát 2 phần tử rồi chờ request tiếp. Nhưng một tác vụ phía trước có thể đang chiếm kết nối, CPU, queue hoặc đã tạo side effect.

Backpressure **không đồng nghĩa**:

- Giới hạn số request HTTP mỗi giây (rate limiting).
- Giới hạn số lần xác thực sai hoặc credential stuffing.
- Giới hạn bytes/CPU của một request.
- Ngăn mọi publisher không tuân thủ demand, API blocking hoặc client phát dữ liệu quá nhanh.
- Quyền được truy cập tài nguyên; đó là việc của authorization.

### 5.2. Tải bất thường là vấn đề bảo mật và độ sẵn sàng

Khi endpoint kết hợp truy vấn dữ liệu, policy checks và audit cho từng phần tử, độ đồng thời lớn có thể làm cạn connection pool hoặc tạo hàng đợi vô hạn. Điều này có thể dẫn tới từ chối dịch vụ (**DoS**) hoặc mất khả năng kiểm soát an ninh khi chương trình bắt đầu bỏ log/kiểm tra để “cứu hiệu năng”.

Các công cụ cần dùng đúng mục đích:

| Cơ chế | Tác dụng | Giới hạn/cảnh báo |
| --- | --- | --- |
| request(n), luồng hỗ trợ backpressure | Điều tiết phần tử dựa trên nhu cầu downstream | Không thay rate limit của request HTTP |
| **flatMap(mapper, concurrency)** | Giới hạn số publisher con được subscribe cùng lúc | Cần xem prefetch, queue và độ nặng từng publisher |
| **concatMap** | Xử lý tuần tự, giữ thứ tự nguồn | Throughput thấp hơn; không miễn trừ timeout |
| **limitRate** | Chia nhỏ/batch nhu cầu upstream | Chỉ điều phối request, không cấp hạn ngạch tài khoản |
| **onBackpressureBuffer** có giới hạn | Bộ đệm có biên và chính sách tràn rõ ràng | Buffer không giới hạn có thể làm cạn heap |
| **onBackpressureError** | Phát lỗi khi nguồn không thể đáp ứng áp lực | Phải phân biệt lỗi tải và lỗi quyền |
| **onBackpressureDrop/Latest** | Bỏ bớt sự kiện khi consumer chậm | Không dùng để bỏ qua quyết định quyền hoặc sự kiện audit bắt buộc |
| Gateway rate limit, quota, giới hạn kích thước, timeout | Kiểm soát khả năng bị lạm dụng theo client/tài khoản/hệ thống | Cần cấu hình, giám sát và chính sách chống né giới hạn |

**Đặc biệt:** nếu mỗi item phải được kiểm tra quyền, đừng dùng cách bỏ item lỗi hoặc bỏ bản ghi kiểm tra cho “nhanh hơn”. Bất cứ mục nào đi qua nhánh được phép vẫn phải qua bước kiểm soát tương ứng. Dữ liệu truy vấn nên được lọc theo principal/tenant ngay tại nguồn, tránh nạp mọi bản ghi rồi lọc ở UI.

### 5.3. Giới hạn concurrency của tác vụ chi phí cao

~~~java
// Minh họa: tasks là Flux<TaskId>, policyService là API phản ứng bất đồng bộ.
// Tối đa 8 tác vụ xử lý bên trong flatMap được subscribe đồng thời.
return tasks.flatMap(taskId ->
        policyService.checkAndLoadForUser(user, taskId),
        8);
~~~

Điều kiện: **checkAndLoadForUser** chỉ trả dữ liệu sau khi kiểm tra quyền hoàn tất; lỗi/từ chối không được fallback thành dữ liệu. Với tác vụ ghi, cần giải quyết thứ tự xử lý và idempotency trước khi thêm retry hoặc tăng concurrency.

Một Flux ngốn ít phần tử không nhất thiết nhẹ: một phần tử có thể kích hoạt truy vấn lớn, xác minh mật mã nặng hoặc gọi API bên ngoài. Cần đồng thời đo số request, số tác vụ đang chạy, kích thước phản hồi và thời gian xử lý.

## 6. Ví dụ Java 17+ chạy được: ba tín hiệu trong Reactor

Ví dụ dưới dùng **Project Reactor** trực tiếp để tách ngữ nghĩa Reactor khỏi framework HTTP. Nó mô phỏng quyết định quyền và kiểm tra bằng **StepVerifier**; sau đó mới nối tư duy này với Spring Security WebFlux ở mục 7. Demo không thay thế cấu hình authentication/authorization của Spring Security.

Cấu trúc:

~~~text
reactor-security-signals/
├── settings.gradle
├── build.gradle
└── src/main/java/example/SecuritySignalDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'reactor-security-signals'
~~~

**build.gradle** (Gradle 8+, JDK 17+)

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.12'
    implementation 'io.projectreactor:reactor-test:3.6.12'
}

application {
    mainClass = 'example.SecuritySignalDemo'
}
~~~

**src/main/java/example/SecuritySignalDemo.java**

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

public final class SecuritySignalDemo {

    public static void main(String[] args) {
        // 1. Policy service lỗi: không được trả dữ liệu nhạy cảm.
        Mono<String> protectedRead =
                Mono.<Boolean>error(new IllegalStateException("policy unavailable"))
                    .flatMap(allowed -> allowed
                            ? Mono.just("secret")
                            : Mono.<String>error(new SecurityException("denied")));

        StepVerifier.create(protectedRead)
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "policy unavailable".equals(error.getMessage()))
                .verify();

        System.out.println("PASS 1: policy error did not reveal data");

        // 2. Subscriber chỉ nhận hai item rồi hủy.
        AtomicInteger emitted = new AtomicInteger();
        AtomicInteger cancelled = new AtomicInteger();

        Flux<Integer> protectedStream = Flux.range(1, 100)
                .doOnNext(value -> emitted.incrementAndGet())
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        cancelled.incrementAndGet();
                    }
                });

        StepVerifier.create(protectedStream, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        if (emitted.get() != 2 || cancelled.get() != 1) {
            throw new AssertionError("Cancel state mismatch");
        }
        System.out.println("PASS 2: cancelled after two items");

        // 3. Nhu cầu đi từng đợt; nguồn đồng bộ tôn trọng request(n).
        AtomicInteger seen = new AtomicInteger();
        Flux<Integer> limited = Flux.range(1, 5)
                .doOnNext(value -> seen.incrementAndGet());

        StepVerifier.create(limited, 0)
                .expectSubscription()
                .thenRequest(1).expectNext(1)
                .thenRequest(2).expectNext(2, 3)
                .thenRequest(2).expectNext(4, 5)
                .verifyComplete();

        if (seen.get() != 5) {
            throw new AssertionError("Backpressure count mismatch");
        }
        System.out.println("PASS 3: demand 1+2+2 delivered five items");
    }
}
~~~

Chạy trong thư mục dự án:

~~~bash
gradle run
~~~

Đầu ra từ **chương trình demo** (bỏ qua log chuẩn của Gradle):

~~~text
PASS 1: policy error did not reveal data
PASS 2: cancelled after two items
PASS 3: demand 1+2+2 delivered five items
~~~

Giải thích:

- **Trường hợp 1:** policy source phát onError; flatMap không được gọi nên chuỗi "secret" không được phát.
- **Trường hợp 2:** StepVerifier yêu cầu đúng 2 phần tử rồi cancel; Flux.range đồng bộ tôn trọng nhu cầu, doFinally ghi nhận CANCEL một lần.
- **Trường hợp 3:** không có yêu cầu vô hạn; nguồn chỉ được phát 1, tiếp theo 2, tiếp theo 2 phần tử.

Trong hệ thống thực tế, I/O bất đồng bộ, operator có prefetch và tác vụ ngoài process làm phép đo phức tạp hơn. Demo chứng minh ngữ nghĩa trên nguồn đồng bộ, không khẳng định cancellation luôn rollback database hoặc request(n) luôn tương đương số công việc I/O.

## 7. Áp dụng vào Spring Security WebFlux

### 7.1. Đặt cổng phân quyền trước Flux trả dữ liệu

Một service reactive có thể tổ chức như sau:

~~~java
// Đoạn minh họa tích hợp, không phải chương trình Java độc lập.
// canReadAccount: Mono<Boolean>; false => cấm, empty => chưa có quyết định.
// Dùng Authentication đã lấy từ Spring Security, không lấy username tự khai.
public Flux<DocumentDto> documents(Authentication principal, String accountId) {
    return permissionService.canReadAccount(principal, accountId)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("No authorization decision")))
            .flatMapMany(allowed -> {
                if (!allowed) {
                    return Flux.error(new AccessDeniedException("Forbidden"));
                }
                return Flux.defer(() ->
                        documentRepository.findReadableByPrincipalAndAccount(
                                principal.getName(), accountId));
            });
}
~~~

Các kiểu **DocumentDto**, service và repository phải được định nghĩa trong ứng dụng; AccessDeniedException thuộc Spring Security. Truy vấn phía repository phải thực thi đúng phạm vi được phép, không chỉ tin accountId do client gửi. Nếu policy trả lỗi kỹ thuật, đoạn này không xuất dữ liệu. Trước khi đưa vào production, bảo vệ endpoint bằng SecurityWebFilterChain và/hoặc reactive method security thích hợp.

Khi dùng **@EnableReactiveMethodSecurity** và **@PreAuthorize**, Spring Security dựa trên Reactor Context để thực hiện quyết định bảo mật trong pipeline Mono/Flux. Nếu dùng operator tạo subscription riêng hoặc tự quản lý context, cần kiểm tra ngữ cảnh thực tế bằng integration test.

### 7.2. Với streaming response, tính thời điểm là rất quan trọng

~~~text
Client ---- HTTP request ----> SecurityWebFilterChain
                                   |
                              Xác thực
                                   |
                              Phân quyền
                                   |
                         Bắt đầu Flux dữ liệu
                                   |
                       item1 -> item2 -> item3 ...
                                   |
                        client cancel / lỗi
~~~

- **Trước item đầu tiên:** lỗi policy/permission có thể ngăn hoàn toàn việc phát dữ liệu. HTTP status còn có thể được ánh xạ thành 401/403/5xx tùy handler và thời điểm response commit.
- **Sau khi đã phát item1/item2:** nếu phát sinh lỗi, không thể “thu hồi” byte đã gửi; response có thể đã committed và khó thay đổi mã HTTP. Với dữ liệu nhạy cảm, ưu tiên kiểm tra quyền trước stream và hạn chế stream qua nhiều ranh giới quyền chưa được kiểm tra.
- **Khi client disconnect:** upstream có thể bị cancel; không hiểu response incomplete là thao tác nghiệp vụ đã rollback. Audit giao dịch phải nằm ở ranh giới commit bền vững.
- **Khi nguồn quá chậm:** timeout, cancellation và retry cần được thiết kế theo độ an toàn của thao tác; tăng retry vô hạn có thể làm quá tải chính hệ thống bảo mật.

Đối với luồng dài (SSE/WebSocket), quyền có thể thay đổi trong khi kết nối còn sống. Một lần kiểm tra lúc handshake chỉ chứng minh quyền ở thời điểm đó. Nếu nghiệp vụ yêu cầu thu hồi quyền tức thời hoặc phân quyền khác nhau cho từng sự kiện, cần cơ chế tái kiểm tra/thu hồi theo chính sách phù hợp.

## 8. Tình huống trước–sau cần hiểu

### Tình huống A: policy service đang lỗi

**Sai:** dùng onErrorReturn(true), mặc định cho phép vì “service tạm thời unavailable”.

**Đúng:** dừng phát tài liệu và trả lỗi kỹ thuật an toàn, có cảnh báo giám sát. Chính sách truy cập có thể phân biệt 403 và 503 nhưng không để mất khả năng ra quyết định biến thành quyền truy cập.

### Tình huống B: download bị hủy giữa chừng

**Sai:** ghi sự kiện “đã tải thành công” ở doOnNext đầu tiên hoặc chỉ dựa vào HTTP handler được gọi.

**Đúng:** phân biệt started, streamed partially, completed, cancelled. Dùng signal quan sát phù hợp và đo số byte nếu cần. Quyết định quyền/audit bền vững phải thực hiện đúng thời điểm nghiệp vụ yêu cầu, không dựa duy nhất vào việc client nhận hết response.

### Tình huống C: nguồn audit chậm

**Sai:** thêm onBackpressureDrop vào luồng audit bắt buộc để khỏi ảnh hưởng tốc độ, khiến một số hành động không có dấu vết.

**Đúng:** áp dụng queue bền vững, bounded concurrency, áp lực ngược rõ ràng hoặc từ chối/giảm tải request khi không thể đáp ứng audit bắt buộc. Thiết kế phải định nghĩa điều gì xảy ra khi đích audit không khả dụng.

### Tình huống D: đọc 50.000 đối tượng

**Sai:** gọi flatMap không giới hạn cho hàng chục nghìn tác vụ kiểm tra quyền rồi giữ toàn bộ kết quả trong RAM.

**Đúng:** giới hạn concurrency, phân trang hoặc stream có backpressure, truy vấn đã lọc theo tenant/owner, timeout và quota. Nếu đối tượng có quyền riêng, mỗi đối tượng trả ra phải qua kiểm tra thích hợp; không chọn cách bỏ kiểm tra để tăng tốc.

## 9. Kiểm thử đúng các đường kết thúc

Một bài test chỉ kiểm tra HTTP 200 khi thành công là chưa đủ. Tối thiểu nên mô phỏng:

| Trường hợp | Điều phải xác minh |
| --- | --- |
| Không có credential | Không trả dữ liệu cần đăng nhập; response theo entry point |
| Authentication thất bại | Không tạo principal được tin cậy; không phát dữ liệu |
| Policy trả false | 403/AccessDenied theo cấu hình; không gọi nguồn dữ liệu bảo vệ |
| Policy Mono.empty | Không tự coi là cho phép |
| Policy onError hoặc timeout | Không xuất dữ liệu; lỗi được xử lý và quan sát phù hợp |
| Client cancel trước quyết định quyền | Không phát tài liệu; metric cancel được ghi nhận; không giả định audit/commit đã xong |
| Client cancel sau vài item | Không báo “trả hết dữ liệu” sai; không hứa rollback tác dụng phụ bên ngoài |
| retry khi có tác dụng phụ | Không nhân đôi thao tác; idempotency/transaction bảo vệ |
| Subscriber request(1), request(2) | Nguồn hỗ trợ demand không phát vượt số item được yêu cầu ở giao diện kiểm tra |
| Tải đồng thời lớn | In-flight task, bộ đệm, CPU, kết nối và lỗi timeout trong giới hạn thiết kế |
| Dữ liệu đa tenant | Không item nào ngoài tenant/owner hợp lệ đi qua stream |
| Đổi scheduler/context | Principal được lấy đúng từ Reactor Context, không lẫn user giữa request |

Công cụ phù hợp: **StepVerifier** để kiểm tra tín hiệu Reactor, **WebTestClient** để kiểm thử HTTP và security filter, test tích hợp cho database/queue/transaction, và stress test có kiểm soát cho concurrency/backpressure. Trong test cancellation, nên dùng cơ chế đồng bộ chắc chắn thay vì ngủ ngẫu nhiên rồi đoán tác vụ đã dừng.

## 10. Checklist thiết kế cho tác vụ bảo mật reactive

1. **Xác định gate:** dữ liệu được phép rời hệ thống sau khi chính bước nào hoàn thành? Giữ gate trước publisher phát dữ liệu nhạy cảm.
2. **Định nghĩa rõ empty / false / error:** Mono.empty ở dịch vụ chính sách có nghĩa gì? Không ngầm hiểu đó là allow.
3. **Fail closed:** không bao trùm cả nhánh kiểm tra quyền bằng onErrorReturn(true), onErrorComplete hoặc fallback trả secret.
4. **Rà lại retry và timeout:** vị trí operator, số lần thử, tác dụng phụ và idempotency. Biết nguồn nào nhận CANCEL khi downstream timeout.
5. **Theo dõi cả ba đường kết thúc:** complete, error, cancel. Metric nhẹ bằng doFinally; audit bắt buộc cần độ bền tương ứng nghiệp vụ.
6. **Không tự subscribe bừa bãi:** trả Mono/Flux cho WebFlux và giữ Reactor Context, thiết kế riêng các job bền vững nếu thực sự cần.
7. **Bảo vệ từng đối tượng/tenant:** check ở service/data layer; streaming nhiều item có thể cần kiểm soát từng item hoặc truy vấn lọc quyền từ nguồn.
8. **Đặt giới hạn tải:** bounded concurrency, queue/buffer có biên, timeout, request quota, rate limit, payload limit; đo giới hạn thực tế.
9. **Không bỏ rơi quyết định bảo mật:** drop/skip không phù hợp cho authorization hay audit bắt buộc.
10. **Kiểm thử fail/cancel/backpressure:** các nhánh bất thường quan trọng không kém đường thành công.

## 11. Câu hỏi tự kiểm tra

1. Vì sao onErrorReturn(true) ở một Mono<Boolean> kiểm tra quyền là lỗ hổng fail-open?
2. doOnComplete và doFinally khác nhau thế nào khi client hủy stream?
3. TimeoutException ở downstream có thể tương ứng tín hiệu gì phía upstream của timeout?
4. Vì sao hủy một HTTP request không đảm bảo giao dịch database đã rollback?
5. request(2) có bảo vệ endpoint khỏi 10.000 request/s không? Vì sao?
6. Vì sao onBackpressureDrop nguy hiểm khi áp vào audit hoặc authorization bắt buộc?
7. Khi Flux đã gửi vài phần tử nhạy cảm, lỗi kiểm tra quyền đến sau có thu hồi được dữ liệu đó không?
8. Khi retry một lệnh ghi sau timeout, vì sao cần idempotency key hoặc transaction rõ ràng?

**Đáp án gợi ý:** (1) lỗi policy biến thành allow; (2) doOnComplete chỉ trên hoàn thành bình thường, doFinally còn quan sát error/cancel; (3) CANCEL upstream, ON_ERROR downstream; (4) I/O có thể đã bắt đầu/commit và cancel không phải rollback; (5) không, backpressure điều tiết phần tử chứ không đặt rate limit; (6) có thể mất bằng chứng/kiểm tra; (7) không thể thu hồi bytes đã gửi; (8) retry tạo subscription mới, lần đầu có thể đã ghi thành công.

## 12. Tài liệu đối chiếu

- Project Reactor Reference Guide — Handling Errors: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Project Reactor Reference Guide — Backpressure and Reshaping Requests: https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html
- Project Reactor Reference Guide — Testing with StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html

**Kết luận:** Ba tính chất **error**, **cancel** và **backpressure** đều có thể thay đổi lúc nào việc kiểm tra quyền và audit xảy ra, có chạy lại hay bị bỏ dở, và nguồn dữ liệu tiêu tốn bao nhiêu tài nguyên. Hãy thiết kế luồng theo tín hiệu thực tế: quyết định quyền trước dữ liệu, audit đúng mức độ bền nghiệp vụ, giới hạn tải rõ ràng và test đầy đủ các đường kết thúc.