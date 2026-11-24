# Bỏ qua một phần tử lỗi bằng cách đặt phục hồi đúng vị trí

Trong một luồng dữ liệu, một phần tử không hợp lệ đôi khi không nên làm dừng toàn bộ quá trình. Ví dụ, một batch nhập liệu có thể chứa một dòng sai định dạng nhưng các dòng còn lại vẫn cần được xử lý; một luồng sự kiện có thể chứa một bản ghi thiếu trường bắt buộc trong khi những sự kiện khác vẫn hợp lệ. Muốn bỏ qua đúng phần tử lỗi, ta phải đặt logic phục hồi ở đúng phạm vi của phần tử đó.

Trong Project Reactor, lỗi thường là tín hiệu kết thúc: khi một toán tử phát `onError`, subscription kết thúc và các phần tử upstream chưa được xử lý sẽ không tiếp tục đi qua pipeline. `onErrorResume` thay thế phần còn lại của một Publisher đã lỗi; nó không tự quay lại nguồn để thử phần tử kế tiếp. Reactor có `onErrorContinue` để một số toán tử upstream có thể bỏ phần tử gây lỗi và tiếp tục, nhưng hành vi này phụ thuộc toán tử hỗ trợ và phạm vi tác động có thể khó nhìn thấy. Cách dễ kiểm soát hơn cho nhiều tình huống là cô lập từng phần tử thành một inner Publisher rồi phục hồi ngay bên trong inner đó.

Chủ đề này thuộc chương **Lỗi và phục hồi** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi thiết kế phục hồi, hãy xác định lỗi phát sinh ở đâu, phần dữ liệu nào bị ảnh hưởng và liệu các phần tử tiếp theo có thể tiếp tục an toàn hay không.

## Mặc định: lỗi của một toán tử kết thúc subscription

Hãy xét một luồng các chuỗi cần chuyển thành số nguyên:

```java
Flux<String> rawValues = Flux.just("10", "20", "bad", "40");

Flux<Integer> parsed = rawValues
    .map(Integer::parseInt);
```

Khi `map` xử lý `"bad"`, `Integer.parseInt` ném `NumberFormatException`. Reactor chuyển exception thành `onError`; `parsed` kết thúc ngay tại đó. Giá trị `"40"` phía sau không được xử lý trong subscription này.

```text
Nguồn:       10 ── 20 ── bad ── 40 ──|
map(parse):  10 ── 20 ── X
                         lỗi kết thúc luồng
```

Đây là hành vi đúng của Reactive Streams: một subscription kết thúc bằng `onComplete` hoặc `onError`. Muốn tiếp tục với phần tử kế tiếp, cần biến lỗi của từng phần tử thành một kết quả cục bộ trước khi nó trở thành lỗi kết thúc của toàn luồng.

## Đặt `onErrorContinue` sau toán tử có thể gây lỗi

`onErrorContinue` cho phép các toán tử upstream có hỗ trợ cơ chế này bỏ qua phần tử gây lỗi và tiếp tục xử lý những phần tử tiếp theo. Ví dụ:

```java
import reactor.core.publisher.Flux;

Flux.just("10", "20", "bad", "40")
    .map(Integer::parseInt)
    .onErrorContinue((error, value) ->
        System.err.println("Skip value=" + value + ": " + error.getMessage())
    )
    .subscribe(System.out::println);
```

Kết quả dự kiến:

```text
10
20
40
```

Khi `map` xử lý `"bad"`, hook `onErrorContinue` nhận exception và giá trị đầu vào gây lỗi. Vì hook được đặt sau `map`, nó có thể tác động ngược tới toán tử `map` ở upstream. `map` hỗ trợ chế độ tiếp tục này nên phần tử lỗi được bỏ qua và phần tử `"40"` vẫn được xử lý.

Vị trí đặt hook là điểm quan trọng. Nếu đặt `onErrorContinue` trước toán tử có thể lỗi, hook nằm ở phía upstream của toán tử đó và không cấu hình hành vi cho toán tử downstream:

```java
Flux.just("10", "bad", "40")
    .onErrorContinue((error, value) -> logSkipped(value, error))
    .map(Integer::parseInt);
```

Trong pipeline này, `map` nằm sau hook. Lỗi phát sinh trong `map` không được hook đứng trước cấu hình để bỏ qua; lỗi vẫn kết thúc subscription. Quy tắc đọc pipeline là: nếu sử dụng `onErrorContinue`, đặt nó sau toán tử upstream có thể ném lỗi và xác nhận toán tử đó hỗ trợ cơ chế tiếp tục.

### Phạm vi và giới hạn của `onErrorContinue`

`onErrorContinue` không phải một bộ bắt mọi exception ở mọi nơi. Nó chỉ áp dụng cho những toán tử upstream có hỗ trợ chế độ tiếp tục khi lỗi phát sinh trong quá trình xử lý một phần tử. Không nên giả định mọi operator, mọi Publisher bên ngoài hoặc mọi callback đều hỗ trợ hành vi này.

Một số giới hạn cần nhớ:

- Hook tác động tới các toán tử hỗ trợ ở phía upstream của nó; phạm vi có thể rộng hơn một biểu thức `map` khiến người đọc khó nhận ra.
- Nó không biến lỗi từ nguồn thành lỗi có thể bỏ qua một cách tổng quát. Ví dụ, lỗi kết nối hoặc lỗi terminal do Publisher nguồn phát vẫn có thể kết thúc luồng.
- Nó không phải cơ chế khôi phục cho lỗi trong callback của Subscriber cuối cùng.
- Nếu callback xử lý lỗi tự ném exception, pipeline có thể kết thúc bằng lỗi mới hoặc phát sinh lỗi bị drop tùy ngữ cảnh.
- Nếu bỏ qua phần tử làm mất tính nhất quán của dữ liệu, việc pipeline tiếp tục có thể tạo kết quả nghiệp vụ sai.

Vì phạm vi tác động của `onErrorContinue` có thể khó theo dõi khi pipeline dài, Reactor khuyến nghị cân nhắc xử lý lỗi cục bộ trong inner Publisher. Cách này thể hiện rõ phần tử nào được phục hồi và tránh làm thay đổi ngầm hành vi của các operator khác ở upstream.

## Phục hồi riêng từng phần tử bằng `flatMap` hoặc `concatMap`

Để cô lập lỗi, hãy chuyển mỗi phần tử đầu vào thành một Publisher riêng. Đặt `onErrorResume` bên trong Publisher đó để chỉ thay thế kết quả của phần tử hiện tại:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> rawValues = Flux.just("10", "20", "bad", "40");

Flux<Integer> parsed = rawValues.concatMap(raw ->
    Mono.fromCallable(() -> Integer.parseInt(raw))
        .onErrorResume(NumberFormatException.class, error -> {
            System.err.println("Skip value=" + raw + ": " + error.getMessage());
            return Mono.empty();
        })
);
```

Mỗi `raw` tạo ra một `Mono` độc lập. Nếu parse thành công, Mono phát một số nguyên. Nếu parse thất bại, `onErrorResume` bên trong inner Mono chuyển lỗi đó thành `Mono.empty()`. Inner Publisher kết thúc bình thường mà không phát giá trị; `concatMap` tiếp tục với phần tử nguồn kế tiếp. Kết quả vẫn chứa `10`, `20`, `40`.

Sơ đồ phạm vi phục hồi:

```text
raw:       10       bad       40
            |        |         |
            v        v         v
          Mono     Mono      Mono
          parse    parse     parse
            |        |         |
          value    empty     value
            \        |        /
             +---- concatMap ----> 10, 40
```

`concatMap` đăng ký và chờ inner Publisher hiện tại hoàn tất trước khi chuyển sang phần tử tiếp theo. Cách này giữ thứ tự đầu vào và giới hạn việc xử lý đồng thời. Nếu mỗi phần tử độc lập và có thể xử lý song song, dùng `flatMap`:

```java
Flux<Integer> parsedConcurrently = rawValues.flatMap(raw ->
    Mono.fromCallable(() -> Integer.parseInt(raw))
        .onErrorResume(NumberFormatException.class, error -> Mono.empty())
);
```

`flatMap` có thể phát kết quả theo thứ tự hoàn tất của các inner Publisher, không nhất thiết theo thứ tự đầu vào. Nếu cần giới hạn số phần tử xử lý đồng thời, truyền `concurrency` phù hợp cho overload của `flatMap`, ví dụ `flatMap(mapper, 8)`. Không nên mở concurrency quá lớn khi mỗi inner Publisher gọi dịch vụ bên ngoài hoặc giữ tài nguyên.

### Vì sao không đặt `onErrorResume` ở ngoài `flatMap`?

Vị trí bên ngoài xử lý lỗi của toàn chuỗi `flatMap`, không phải riêng từng inner Publisher:

```java
Flux<Integer> stopsAtFirstBadItem = rawValues
    .concatMap(raw -> Mono.fromCallable(() -> Integer.parseInt(raw)))
    .onErrorResume(NumberFormatException.class, error -> Mono.empty());
```

Khi `"bad"` gây lỗi, inner Mono phát `onError`; `concatMap` chuyển lỗi đó xuống downstream và kết thúc chuỗi. `onErrorResume` bên ngoài thay thế toàn bộ phần còn lại bằng `Mono.empty()` được chuyển thành Publisher rỗng. `"40"` không được xử lý vì nguồn đã bị hủy sau lỗi. Để bỏ riêng phần tử lỗi, hãy đặt `onErrorResume` bên trong mapper, ngay trên inner Publisher đại diện cho phần tử đó.

| Vị trí phục hồi | Phạm vi được thay thế | Phần tử tiếp theo có được xử lý? |
|---|---|---|
| `onErrorResume` sau toàn bộ `map`/`concatMap` | Toàn bộ Publisher upstream đã lỗi | Thường không; nguồn đã kết thúc do lỗi |
| `onErrorResume` bên trong inner Publisher của `flatMap`/`concatMap` | Chỉ công việc ứng với phần tử hiện tại | Có, nếu inner thay lỗi bằng kết quả kết thúc bình thường |
| `onErrorContinue` sau operator hỗ trợ | Phần tử gây lỗi tại operator upstream hỗ trợ chế độ tiếp tục | Có, trong phạm vi hỗ trợ của operator |

## Chọn bỏ qua, thay thế hay đánh dấu phần tử lỗi

Bỏ qua phần tử lỗi không phải lúc nào cũng là chính sách tốt nhất. Có ba lựa chọn phổ biến:

1. **Bỏ qua:** trả về `Mono.empty()` nếu phần tử không thể sử dụng và không cần tạo đầu ra thay thế.
2. **Thay bằng giá trị dự phòng:** trả về một giá trị có ý nghĩa nghiệp vụ, chẳng hạn một bản ghi mang trạng thái `INVALID`.
3. **Giữ kết quả có trạng thái lỗi:** phát một kiểu kết quả như `Either`, `Result` hoặc record chứa dữ liệu gốc và lỗi để bước sau quyết định.

Ví dụ thay phần tử lỗi bằng một kết quả có trạng thái:

```java
record ParseResult(String raw, Integer value, String error) {
    static ParseResult success(String raw, int value) {
        return new ParseResult(raw, value, null);
    }

    static ParseResult failure(String raw, Throwable error) {
        return new ParseResult(raw, null, error.getMessage());
    }
}

Flux<ParseResult> results = rawValues.concatMap(raw ->
    Mono.fromCallable(() -> ParseResult.success(raw, Integer.parseInt(raw)))
        .onErrorResume(NumberFormatException.class, error ->
            Mono.just(ParseResult.failure(raw, error))
        )
);
```

Pipeline vẫn phát một kết quả cho mỗi phần tử đầu vào. Phần tử sai định dạng được giữ lại dưới dạng `ParseResult.failure`, nhờ đó ứng dụng có thể ghi báo cáo lỗi hoặc gửi dữ liệu lỗi sang một luồng xử lý riêng. Cách này phù hợp khi cần kiểm toán hoặc đối soát số lượng bản ghi đã nhận.

Không nên thay lỗi bằng một giá trị mặc định như `0` nếu `0` là dữ liệu hợp lệ và downstream không thể phân biệt giá trị thật với giá trị thay thế. Nếu cần fallback, hãy dùng kiểu dữ liệu thể hiện rõ trạng thái hoặc gắn metadata cho kết quả.

## Chỉ phục hồi loại lỗi dự kiến

Khi bỏ qua phần tử, hãy giới hạn loại exception được xử lý. Ví dụ, `NumberFormatException` có thể biểu thị dữ liệu đầu vào sai định dạng; `IllegalStateException` từ một thành phần bên dưới có thể biểu thị lỗi lập trình hoặc trạng thái hệ thống không hợp lệ. Bắt mọi `Throwable` rồi trả `Mono.empty()` có thể che giấu lỗi nghiêm trọng.

```java
Mono<Record> parseRecord(String line) {
    return Mono.fromCallable(() -> parser.parse(line))
        .onErrorResume(InvalidRecordException.class, error -> {
            auditInvalidLine(line, error);
            return Mono.empty();
        });
}
```

Lỗi dữ liệu được dự kiến sẽ bị bỏ qua sau khi ghi nhận. Những lỗi khác tiếp tục truyền xuống downstream và kết thúc luồng. Nếu việc ghi audit cũng thất bại, cần quyết định rõ lỗi audit có được phép làm hỏng pipeline hay không; đừng âm thầm nuốt lỗi phụ nếu hệ thống yêu cầu dấu vết đầy đủ.

## Phân biệt lỗi khi xử lý phần tử với lỗi của nguồn

Phục hồi từng phần tử phù hợp với lỗi phát sinh khi xử lý một giá trị cụ thể, chẳng hạn parse, validate hoặc chuyển đổi. Nó không tự giải quyết lỗi terminal của nguồn như mất kết nối, timeout hoặc broker đóng subscription.

| Loại lỗi | Ví dụ | Hướng xử lý thường dùng |
|---|---|---|
| Lỗi dữ liệu của một phần tử | Chuỗi không parse được, trường bắt buộc thiếu | Phục hồi trong inner Publisher hoặc `onErrorContinue` nếu operator hỗ trợ |
| Lỗi của một lời gọi độc lập cho từng phần tử | Một lần gọi API tra cứu thất bại | `onErrorResume` bên trong inner Publisher; có thể fallback hoặc bỏ phần tử |
| Lỗi terminal của nguồn | Kết nối stream bị đóng, broker phát lỗi | `retry`, `onErrorResume` ở cấp nguồn hoặc kết thúc pipeline theo chính sách |
| Lỗi lập trình/hạ tầng | Null ngoài dự kiến, cấu hình sai, database không khả dụng | Thường cần truyền lỗi, alert hoặc dừng xử lý; không tự động bỏ qua |

Nếu một lời gọi API nằm trong `flatMap`, có thể phục hồi riêng lời gọi đó để các phần tử khác tiếp tục. Nhưng nếu chính Publisher nguồn của `flatMap` phát `onError`, mapper không còn nhận phần tử mới; lỗi cần được xử lý ở cấp nguồn.

## Ghi nhận phần tử bị bỏ và giữ khả năng quan sát

Một pipeline bỏ qua dữ liệu mà không ghi nhận có thể trông như chạy thành công dù đã mất một phần đầu vào. Nên theo dõi số phần tử lỗi, loại lỗi, nguồn dữ liệu và mã tương quan; tránh ghi toàn bộ payload nhạy cảm vào log.

```java
AtomicLong skipped = new AtomicLong();

Flux<Integer> parsed = rawValues.concatMap(raw ->
    Mono.fromCallable(() -> Integer.parseInt(raw))
        .onErrorResume(NumberFormatException.class, error -> {
            skipped.incrementAndGet();
            log.warn("Invalid numeric input; sourceId={}", sourceId(raw));
            return Mono.empty();
        })
);
```

Metric `skipped` giúp phát hiện khi tỷ lệ dữ liệu lỗi tăng đột biến. Trong hệ thống cần đối soát, nên ghi bản ghi lỗi vào dead-letter stream hoặc kho lưu trữ riêng thay vì chỉ tăng counter. Nếu việc ghi dead-letter thất bại, hãy xác định liệu pipeline chính phải dừng hay có một cơ chế bền vững khác.

## Kiểm thử hành vi phục hồi bằng `StepVerifier`

Kiểm thử cần chứng minh phần tử lỗi bị bỏ đúng phạm vi và phần tử sau nó vẫn được xử lý. Ví dụ với `onErrorResume` trong inner Publisher:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PerElementRecoveryTest {
    @Test
    void skipsOnlyTheInvalidItem() {
        Flux<String> source = Flux.just("10", "bad", "30");

        Flux<Integer> result = source.concatMap(raw ->
            Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(NumberFormatException.class, error -> Mono.empty())
        );

        StepVerifier.create(result)
            .expectNext(10, 30)
            .verifyComplete();
    }
}
```

Test xác nhận `"bad"` không làm dừng phần tử `"30"` và luồng kết thúc bình thường. Nên có thêm test cho fallback dạng `ParseResult.failure`, cho lỗi không thuộc loại được phục hồi và cho thứ tự khi dùng `concatMap`.

Nếu chọn `onErrorContinue`, hãy kiểm thử với đúng operator hỗ trợ và đặt hook ở vị trí dự định dùng trong production:

```java
Flux<Integer> result = Flux.just("10", "bad", "30")
    .map(Integer::parseInt)
    .onErrorContinue((error, value) -> recordSkipped(value, error));

StepVerifier.create(result)
    .expectNext(10, 30)
    .verifyComplete();
```

Test này khóa hành vi mong đợi của pipeline hiện tại, nhưng không chứng minh `onErrorContinue` có thể xử lý lỗi từ mọi operator. Nếu thay đổi pipeline hoặc nâng phiên bản Reactor, hãy kiểm tra lại phạm vi hỗ trợ và cân nhắc chuyển sang phục hồi cục bộ trong inner Publisher.

## Những lỗi thiết kế thường gặp

**Đặt `onErrorResume` sau toàn bộ luồng rồi kỳ vọng phần tử tiếp theo tiếp tục.** Khi lỗi đến đó, Publisher upstream đã kết thúc. Muốn cô lập lỗi từng phần tử, đặt phục hồi bên trong inner Publisher.

**Đặt `onErrorContinue` trước operator gây lỗi.** Hook không cấu hình các toán tử downstream của nó. Nếu dùng cơ chế này, đặt sau operator upstream có hỗ trợ và kiểm thử vị trí thực tế.

**Cho rằng `onErrorContinue` hỗ trợ mọi operator.** Đây là hành vi có điều kiện, phụ thuộc operator. Không dùng nó như một cơ chế bắt lỗi tổng quát.

**Bắt mọi exception rồi bỏ qua.** Cách này có thể che giấu lỗi lập trình hoặc lỗi hạ tầng. Chỉ phục hồi những loại lỗi có chính sách nghiệp vụ rõ ràng.

**Dùng `flatMap` không giới hạn cho công việc chậm.** Nhiều inner Publisher có thể hoạt động đồng thời và giữ tài nguyên. Đặt concurrency phù hợp hoặc dùng `concatMap` nếu cần tuần tự.

**Bỏ phần tử mà không có metric hoặc audit.** Hệ thống có thể âm thầm mất dữ liệu. Ghi nhận số lượng, loại lỗi và mã tương quan phù hợp.

**Nhầm lỗi phần tử với lỗi nguồn.** Phục hồi inner Publisher không thể làm một nguồn đã phát terminal signal tiếp tục phát phần tử mới. Xử lý lỗi nguồn ở cấp phù hợp.

## Tự kiểm tra

1. Vì sao `onErrorResume` đặt sau `map(Integer::parseInt)` không tự bỏ riêng chuỗi lỗi rồi tiếp tục với phần tử kế tiếp?
2. Với `onErrorContinue`, vì sao hook thường được đặt sau operator có thể gây lỗi?
3. Những giới hạn nào khiến `onErrorContinue` không nên được xem là cơ chế phục hồi tổng quát?
4. Vì sao đặt `onErrorResume` bên trong inner Publisher của `concatMap` giúp cô lập lỗi theo từng phần tử?
5. Khi nào nên dùng `flatMap` thay cho `concatMap`, và cần kiểm soát điều gì?
6. Khi nào nên bỏ phần tử, thay bằng fallback hoặc phát một kết quả mang trạng thái lỗi?
7. Làm thế nào kiểm thử rằng phần tử sau phần tử lỗi vẫn được xử lý và luồng hoàn tất bình thường?

Khi đặt phục hồi đúng phạm vi, bạn có thể bỏ một phần tử dữ liệu lỗi mà vẫn giữ luồng xử lý các phần tử hợp lệ, đồng thời tránh che giấu lỗi nguồn hoặc làm thay đổi hành vi của những phần khác trong pipeline Reactor.
