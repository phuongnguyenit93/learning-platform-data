# Giới hạn và rủi ro của `onErrorContinue` trong Reactor

`onErrorContinue` có thể giúp một pipeline Reactor bỏ qua phần tử gây lỗi trong một số toán tử và tiếp tục xử lý các phần tử sau. Cơ chế này hữu ích khi lỗi chỉ thuộc về một phần tử, chẳng hạn một chuỗi không parse được hoặc một bản ghi không hợp lệ. Tuy nhiên, `onErrorContinue` không phải bộ xử lý lỗi tổng quát cho toàn pipeline. Nó chỉ có tác dụng với những toán tử hỗ trợ chiến lược tiếp tục, tác động theo hướng upstream và có thể khiến hành vi của một đoạn pipeline khó nhận ra khi đọc mã.

Chủ đề này thuộc chương **Lỗi và phục hồi** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi quyết định dùng `onErrorContinue`, cần xác định rõ loại lỗi nào được phép bỏ, toán tử nào hỗ trợ, phần tử nào sẽ mất và side effect nào có thể đã xảy ra trước khi lỗi được ném.

## `onErrorContinue` thực sự làm gì?

Trong Reactive Streams, `onError` là tín hiệu kết thúc của một subscription. Khi một Publisher phát `onError`, subscription đó không tiếp tục nhận `onNext`. Tuy nhiên, có một trường hợp khác: một toán tử đang xử lý một phần tử nhận được qua `onNext` và hàm xử lý phần tử đó ném exception. Reactor có cơ chế xử lý lỗi phát sinh trong quá trình xử lý phần tử; một số toán tử có thể tham gia chiến lược tiếp tục, bỏ phần tử lỗi và xử lý phần tử kế tiếp.

`onErrorContinue` cấu hình chiến lược này cho các toán tử upstream có hỗ trợ. Ví dụ:

```java
import reactor.core.publisher.Flux;

Flux.just("10", "20", "bad", "40")
    .map(Integer::parseInt)
    .onErrorContinue(NumberFormatException.class, (error, value) ->
        System.err.println("Skip value=" + value + ": " + error.getMessage())
    )
    .subscribe(System.out::println);
```

Với `map` hỗ trợ chiến lược này, kết quả gồm `10`, `20`, `40`. Phần tử `"bad"` bị bỏ khi `Integer.parseInt` ném `NumberFormatException`. Callback nhận exception và giá trị đầu vào gây lỗi để ứng dụng ghi nhận hoặc đo lường.

Điểm quan trọng là lỗi được tạo ra trong lúc một operator xử lý một phần tử. `onErrorContinue` không lấy một `onError` terminal đã được nguồn phát rồi biến nó thành một phần tử có thể bỏ qua. Nếu nguồn phát `Flux.error(...)`, hoặc một inner Publisher phát terminal error, lỗi đó vẫn cần được xử lý bằng chiến lược phục hồi phù hợp ở cấp Publisher.

## Vị trí của toán tử quyết định phạm vi tác động

`onErrorContinue` có ngữ nghĩa đặc biệt: nó cấu hình hành vi cho các toán tử tương thích ở phía upstream của nó. Nó không cấu hình các toán tử nằm phía downstream.

```java
// Hook nằm sau map: có thể cấu hình map ở upstream.
Flux.just("1", "bad", "3")
    .map(Integer::parseInt)
    .onErrorContinue((error, value) -> logSkipped(value, error));

// Hook nằm trước map: không cấu hình map ở downstream.
Flux.just("1", "bad", "3")
    .onErrorContinue((error, value) -> logSkipped(value, error))
    .map(Integer::parseInt);
```

Trong ví dụ thứ hai, `map` nằm sau hook. Nếu `map` ném exception, hook đứng trước nó không xử lý lỗi đó; lỗi kết thúc subscription. Khi đọc một chuỗi operator, hãy lần theo hướng từ nơi phát sinh lỗi ngược về phía nguồn: hook chỉ có thể ảnh hưởng tới những operator hỗ trợ nằm upstream của vị trí đặt hook.

Vì cơ chế này được truyền qua Context của Reactor, phạm vi thực tế đôi khi rộng hơn một lời gọi `map` nhìn thấy ngay cạnh `onErrorContinue`. Một operator hoặc thư viện được gọi ở upstream có thể chịu ảnh hưởng của chiến lược mà thành phần gọi nó không nhận ra. Đây là lý do mã dùng `onErrorContinue` có thể gây bất ngờ khi pipeline được tái cấu trúc hoặc tái sử dụng trong một ngữ cảnh khác.

## Chỉ một số toán tử hỗ trợ chiến lược tiếp tục

Không phải mọi operator đều có thể bỏ một phần tử và tiếp tục an toàn. Một số operator Reactor có xử lý lỗi theo từng phần tử, chẳng hạn các operator ánh xạ hoặc lọc tương thích. Các operator khác có thể không hỗ trợ chiến lược này, hoặc lỗi có thể phát sinh ở một nơi không có khái niệm “phần tử hiện tại” để bỏ.

| Nguồn gốc lỗi | `onErrorContinue` có phải lựa chọn phù hợp? | Lý do |
|---|---|---|
| Hàm `map` parse một phần tử và ném `NumberFormatException` | Có thể, nếu operator hỗ trợ và hook nằm downstream của `map` | Có một phần tử cụ thể gây lỗi trong quá trình xử lý `onNext` |
| Predicate của một operator xử lý phần tử ném exception | Phụ thuộc operator hỗ trợ chiến lược | Cần kiểm tra hợp đồng của operator cụ thể |
| Publisher nguồn phát `onError` do mất kết nối | Không | Đây là terminal signal từ nguồn, không phải lỗi xử lý một phần tử trong operator |
| Inner Publisher trong `flatMap` phát `onError` | Thường không nên dùng `onErrorContinue` để xử lý | Inner Publisher đã phát terminal signal; hãy phục hồi inner Publisher đó |
| Callback cuối trong `subscribe` ném exception | Không | Đây là lỗi ở consumer cuối, không phải lỗi của operator upstream đang chuyển phần tử |
| Side effect đã xảy ra rồi phần xử lý mới ném exception | Không thể tự hoàn tác | Bỏ phần tử không rollback side effect đã thực hiện |

Khi cần biết một operator cụ thể có hỗ trợ `onErrorContinue` hay không, hãy kiểm tra tài liệu API và hành vi của phiên bản Reactor trong dự án. Không suy luận rằng một operator hỗ trợ chỉ vì nó nằm trong cùng một pipeline với `map`.

## Rủi ro khi dùng như một cơ chế bắt lỗi chung

### Có thể che giấu lỗi lập trình hoặc lỗi hạ tầng

Nếu dùng callback tổng quát mà không lọc loại lỗi, các exception đáng lẽ phải làm pipeline thất bại cũng có thể bị xử lý như lỗi phần tử. Ví dụ, `NumberFormatException` do dữ liệu sai định dạng có thể được phép bỏ qua; `IllegalStateException` do trạng thái hệ thống sai hoặc lỗi lập trình thường cần được báo lên.

Có thể giới hạn loại exception được xử lý:

```java
Flux.just("10", "bad", "30")
    .map(Integer::parseInt)
    .onErrorContinue(NumberFormatException.class, (error, value) ->
        recordInvalidInput(value, error)
    );
```

Các lỗi không thuộc `NumberFormatException` không được callback này xử lý theo bộ lọc đã chọn và có thể tiếp tục truyền thành lỗi terminal. Việc giới hạn loại lỗi làm rõ chính sách, nhưng vẫn cần xác nhận operator upstream có hỗ trợ chiến lược tiếp tục.

### Phần tử bị bỏ có thể làm sai tính nhất quán nghiệp vụ

Một pipeline có thể hoàn tất bình thường sau khi bỏ một phần tử, nhưng “hoàn tất” không đồng nghĩa dữ liệu đã đầy đủ. Nếu phần tử bị bỏ là một giao dịch, một thay đổi số dư hoặc một sự kiện kiểm soát tồn kho, việc tiếp tục có thể tạo trạng thái sai.

Ví dụ, nếu một bước tính tổng bỏ qua dòng giao dịch sai định dạng, tổng kết quả sẽ không còn đại diện cho toàn bộ dữ liệu đầu vào. Hãy quyết định theo nghiệp vụ xem lỗi dữ liệu có thể loại bỏ, cần đưa vào dead-letter stream, hay phải dừng batch để điều tra.

### Side effect không được rollback

`onErrorContinue` bỏ phần tử tại operator gây lỗi; nó không hoàn tác những side effect đã xảy ra trước thời điểm exception. Nếu hàm xử lý đã gửi email, ghi một phần dữ liệu hoặc gọi dịch vụ ngoài rồi mới ném lỗi, việc bỏ phần tử có thể để lại trạng thái dở dang.

```java
Flux<Order> processed = orders
    .map(order -> {
        auditService.recordAttempt(order); // side effect đã xảy ra
        validateAndEnrich(order);          // có thể ném exception
        return order;
    })
    .onErrorContinue((error, order) -> logRejected(order, error));
```

Nếu `validateAndEnrich` thất bại, lời gọi `recordAttempt` vẫn đã diễn ra. Không nên xem `onErrorContinue` như transaction hoặc cơ chế bù trừ. Hãy tách validation thuần khỏi side effect, dùng transaction ở ranh giới thích hợp hoặc thiết kế thao tác idempotent và có bước bù trừ rõ ràng.

### Callback xử lý lỗi cũng có thể thất bại

Callback truyền cho `onErrorContinue` nên ngắn, an toàn và không ném exception. Nếu callback ghi log, gửi metric hoặc ghi dead-letter mà chính thao tác đó thất bại, lỗi mới có thể làm thay đổi kết quả pipeline hoặc bị xử lý như lỗi bị drop tùy ngữ cảnh. Không nên giả định lỗi trong callback được tự động bỏ qua an toàn.

Nếu việc lưu bản ghi lỗi là bắt buộc, hãy thiết kế riêng độ tin cậy của dead-letter path. Chỉ tăng counter có thể không đủ để đáp ứng yêu cầu kiểm toán; ngược lại, gọi một hệ thống lưu trữ blocking trực tiếp trong callback có thể làm chậm thread đang phát tín hiệu.

## `onErrorContinue` không tương đương `onErrorResume`

Hai operator có phạm vi và mục đích khác nhau:

| Operator | Vai trò | Phạm vi phục hồi |
|---|---|---|
| `onErrorContinue` | Cho operator upstream tương thích bỏ phần tử gây lỗi khi xử lý `onNext` và tiếp tục | Một phần tử tại operator hỗ trợ; phạm vi được cấu hình ngược về upstream |
| `onErrorResume` | Khi Publisher phát lỗi, chuyển sang Publisher dự phòng | Thay thế phần còn lại của Publisher đã lỗi |
| `onErrorMap` | Chuyển một loại exception thành exception khác | Vẫn là lỗi terminal, chỉ thay đổi loại hoặc ngữ nghĩa exception |
| `doOnError` | Quan sát lỗi, ghi log hoặc metric | Không phục hồi; lỗi tiếp tục truyền xuống |
| `onErrorComplete` | Chuyển lỗi thành hoàn tất bình thường | Kết thúc luồng hiện tại, không tiếp tục phần tử nguồn phía sau |

Ví dụ `onErrorResume` đặt sau một chuỗi parse không thể tự tiếp tục phần tử sau phần tử lỗi:

```java
Flux.just("10", "bad", "30")
    .map(Integer::parseInt)
    .onErrorResume(NumberFormatException.class, error -> Flux.empty());
```

Khi `"bad"` gây lỗi, Publisher upstream đã kết thúc. `onErrorResume` thay phần còn lại bằng Flux rỗng; `"30"` không được xử lý. Nếu muốn phục hồi riêng phần tử, hãy tạo inner Publisher cho mỗi phần tử rồi đặt `onErrorResume` bên trong inner đó.

## Cách rõ ràng hơn: phục hồi cục bộ trong `flatMap` hoặc `concatMap`

Với nhiều tình huống, cách dễ hiểu và an toàn hơn là cô lập công việc của từng phần tử:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<Integer> parsed = Flux.just("10", "bad", "30")
    .concatMap(raw ->
        Mono.fromCallable(() -> Integer.parseInt(raw))
            .onErrorResume(NumberFormatException.class, error -> {
                recordInvalidInput(raw, error);
                return Mono.empty();
            })
    );
```

Mỗi phần tử tạo một `Mono` riêng. Nếu parse thành công, Mono phát một số nguyên. Nếu parse thất bại, `onErrorResume` bên trong Mono chuyển lỗi đó thành `Mono.empty()`. `concatMap` tiếp tục đăng ký inner Publisher cho phần tử tiếp theo và giữ thứ tự đầu vào.

Nếu các phần tử độc lập và có thể xử lý đồng thời, dùng `flatMap` với giới hạn concurrency phù hợp:

```java
Flux<Integer> parsed = Flux.just("10", "bad", "30")
    .flatMap(raw ->
        Mono.fromCallable(() -> Integer.parseInt(raw))
            .onErrorResume(NumberFormatException.class, error -> Mono.empty()),
        8
    );
```

`flatMap` có thể phát kết quả theo thứ tự hoàn tất của inner Publisher thay vì thứ tự đầu vào. Tham số `8` giới hạn số inner Publisher đang được đăng ký đồng thời; hãy chọn giới hạn theo tài nguyên thực tế của công việc. Nếu thứ tự là yêu cầu bắt buộc, ưu tiên `concatMap` hoặc một operator có bảo toàn thứ tự.

Ưu điểm của phục hồi cục bộ là phạm vi nhìn thấy ngay trong mapper. Người đọc có thể xác định chính xác phần tử nào được thử, loại lỗi nào được xử lý và Publisher dự phòng trả về gì. Cách này cũng tránh cấu hình ngầm các operator upstream khác.

## Khi nào vẫn có thể cân nhắc `onErrorContinue`?

`onErrorContinue` có thể hữu ích trong một pipeline ngắn, cục bộ, nơi:

- Lỗi phát sinh trong một operator đã xác nhận hỗ trợ chiến lược tiếp tục.
- Lỗi chỉ liên quan tới phần tử hiện tại, không phải lỗi terminal của nguồn.
- Chính sách bỏ phần tử được nghiệp vụ chấp nhận.
- Callback có thể ghi nhận lỗi an toàn và không gây side effect khó kiểm soát.
- Phạm vi hook được giới hạn, dễ đọc và được kiểm thử.

Ngay cả trong trường hợp đó, hãy ghi chú vì sao bỏ phần tử là hợp lệ và vì sao operator được chọn hỗ trợ hành vi này. Nếu pipeline có nhiều operator, nhiều nguồn hoặc được đóng gói thành thư viện dùng lại, phục hồi cục bộ thường dễ bảo trì hơn.

## Kiểm thử các giới hạn và hành vi thực tế

Không nên chỉ kiểm tra rằng pipeline hoàn tất. Cần kiểm tra phần tử nào bị bỏ, lỗi nào vẫn truyền xuống và phần tử sau lỗi có được xử lý hay không.

### Kiểm thử operator hỗ trợ và vị trí hook

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OnErrorContinueTest {
    @Test
    void continuesForInvalidElementInMap() {
        Flux<Integer> result = Flux.just("1", "bad", "3")
            .map(Integer::parseInt)
            .onErrorContinue(NumberFormatException.class,
                (error, value) -> { /* record rejected value */ });

        StepVerifier.create(result)
            .expectNext(1, 3)
            .verifyComplete();
    }

    @Test
    void hookBeforeMapDoesNotConfigureDownstreamMap() {
        Flux<Integer> result = Flux.just("1", "bad", "3")
            .onErrorContinue(NumberFormatException.class,
                (error, value) -> { /* hook is upstream of map */ })
            .map(Integer::parseInt);

        StepVerifier.create(result)
            .expectNext(1)
            .expectError(NumberFormatException.class)
            .verify();
    }
}
```

Test đầu xác nhận `map` tương thích với chiến lược tiếp tục trong vị trí được cấu hình. Test thứ hai xác nhận hook nằm trước `map` không cấu hình operator downstream. Những test này nên chạy với phiên bản Reactor mà ứng dụng thực sự sử dụng.

### Kiểm thử lỗi terminal của nguồn

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> sourceFailure = Flux.concat(
    Flux.just(1, 2),
    Flux.error(new IllegalStateException("source disconnected"))
).onErrorContinue((error, value) -> recordSkipped(value, error));

StepVerifier.create(sourceFailure)
    .expectNext(1, 2)
    .expectError(IllegalStateException.class)
    .verify();
```

Nguồn phát một terminal error. Không có phần tử `onNext` cụ thể nào gây lỗi tại operator để bỏ qua, nên `onErrorContinue` không biến lỗi nguồn thành hoàn tất bình thường.

### Kiểm thử phục hồi cục bộ

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Flux<Integer> perElement = Flux.just("1", "bad", "3")
    .concatMap(raw -> Mono.fromCallable(() -> Integer.parseInt(raw))
        .onErrorResume(NumberFormatException.class, error -> Mono.empty()));

StepVerifier.create(perElement)
    .expectNext(1, 3)
    .verifyComplete();
```

Test này xác nhận cách thay thế thường dễ kiểm soát hơn: lỗi được xử lý bên trong Publisher ứng với phần tử lỗi và nguồn ngoài tiếp tục phát các phần tử còn lại.

## Checklist khi review mã dùng `onErrorContinue`

Trước khi chấp nhận một pipeline có `onErrorContinue`, hãy trả lời được các câu hỏi sau:

1. Exception được ném trong operator nào và khi operator đó xử lý phần tử nào?
2. Operator đó có hỗ trợ chiến lược tiếp tục trong phiên bản Reactor đang dùng không?
3. Hook được đặt downstream của operator gây lỗi để cấu hình đúng phạm vi chưa?
4. Có thể phân biệt lỗi dữ liệu dự kiến với lỗi lập trình hoặc lỗi hạ tầng không?
5. Phần tử bị bỏ có làm mất dữ liệu hoặc phá vỡ invariant nghiệp vụ không?
6. Có side effect nào đã xảy ra trước khi exception được ném và cần bù trừ không?
7. Callback xử lý lỗi có an toàn luồng, không blocking và không ném exception không?
8. Có metric, log hoặc dead-letter path để biết số phần tử đã bị bỏ không?
9. Có test cho lỗi phần tử, lỗi terminal của nguồn, vị trí hook và phần tử tiếp theo không?

Nếu không trả lời rõ được những câu hỏi này, hãy chuyển sang phục hồi cục bộ trong inner Publisher hoặc để lỗi truyền xuống theo đúng chính sách của ứng dụng.

## Những lỗi thiết kế thường gặp

**Coi `onErrorContinue` là catch-all.** Nó không xử lý mọi loại lỗi và không thể biến mọi terminal signal thành phần tử có thể bỏ qua.

**Đặt hook trước operator gây lỗi.** Hook không cấu hình các operator downstream. Vị trí trong chuỗi quyết định phạm vi tác động.

**Giả định tất cả operator đều hỗ trợ.** Chỉ những operator tương thích mới có thể bỏ phần tử và tiếp tục. Hãy kiểm tra API và kiểm thử với phiên bản Reactor thực tế.

**Dùng hook ở phạm vi rộng.** Chiến lược có thể ảnh hưởng các operator upstream trong một đoạn pipeline hoặc thư viện dùng chung, khiến hành vi khó dự đoán khi tái cấu trúc.

**Bỏ qua lỗi mà không đánh giá side effect.** Việc bỏ phần tử không rollback lời gọi dịch vụ, ghi dữ liệu hoặc thao tác đã xảy ra trước exception.

**Nuốt lỗi hạ tầng như lỗi dữ liệu.** Chỉ xử lý loại exception đã được nghiệp vụ cho phép; lỗi kết nối, timeout hoặc trạng thái hệ thống sai thường cần chiến lược riêng.

**Không kiểm thử vị trí và loại lỗi.** Một test chỉ xác nhận pipeline hoàn tất không chứng minh các lỗi quan trọng vẫn được truyền xuống đúng cách.

## Tự kiểm tra

1. `onErrorContinue` xử lý loại lỗi nào và vì sao nó không thể biến một `Flux.error(...)` thành luồng tiếp tục bình thường?
2. Vì sao hook đặt sau `map` có thể ảnh hưởng `map`, còn hook đặt trước `map` thì không?
3. Điều gì quyết định một operator có thể tham gia chiến lược `onErrorContinue`?
4. Những rủi ro nào xuất hiện nếu callback `onErrorContinue` được dùng cho cả lỗi dữ liệu và lỗi hạ tầng?
5. Vì sao bỏ một phần tử không đồng nghĩa với rollback side effect?
6. Khi nào phục hồi bằng `onErrorResume` bên trong `flatMap` hoặc `concatMap` dễ kiểm soát hơn?
7. Cần những test nào để chứng minh hook không nuốt lỗi terminal của nguồn?

`onErrorContinue` là công cụ chuyên biệt cho lỗi phát sinh khi operator tương thích xử lý một phần tử. Khi giới hạn đúng phạm vi và kiểm thử rõ ràng, nó có thể hữu ích; nếu cần chính sách phục hồi dễ hiểu, cục bộ và ổn định hơn, hãy đặt `onErrorResume` trong Publisher ứng với từng phần tử.
