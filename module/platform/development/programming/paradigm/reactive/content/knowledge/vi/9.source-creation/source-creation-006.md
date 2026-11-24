# Phát từng phần tử theo nhu cầu bằng bộ sinh trạng thái

Khi tạo một nguồn reactive, đôi khi dữ liệu không có sẵn trong một collection để chuyển thành Flux. Thay vào đó, nguồn cần tính giá trị kế tiếp từ trạng thái hiện tại: đếm số lần, sinh chuỗi số, đọc lần lượt từng bản ghi từ cursor hoặc thực hiện một máy trạng thái nhỏ. Nếu muốn mỗi lần downstream yêu cầu dữ liệu thì nguồn chỉ tạo một phần tử, Reactor cung cấp Flux.generate.

Flux.generate là cách tạo nguồn đồng bộ, có trạng thái và tuân thủ nhu cầu của Reactive Streams. Bộ sinh được gọi theo từng lượt; mỗi lượt chỉ được phát tối đa một phần tử hoặc một tín hiệu kết thúc. Cách này phù hợp với thuật toán tuần tự mà giá trị tiếp theo phụ thuộc vào trạng thái trước đó. Trong module REACTIVE_PROGRAMMING, nó giúp nối việc tạo nguồn với hợp đồng Publisher–Subscriber, backpressure và cách quản lý vòng đời của pipeline.

## 1. Flux.generate dùng để làm gì?

Flux.generate tạo một Flux bằng một hàm sinh được gọi tuần tự để tạo tín hiệu. Mỗi lần hàm được gọi, nó nhận một SynchronousSink<T>. Hàm có thể phát một phần tử bằng next, kết thúc bình thường bằng complete hoặc kết thúc lỗi bằng error.

Đặc điểm quan trọng:

- Bộ sinh là đồng bộ: lời gọi tạo phần tử hoàn tất trước khi lượt sinh tiếp theo diễn ra.
- Mỗi lượt gọi chỉ được phát tối đa một tín hiệu: một onNext, onComplete hoặc onError.
- Bộ sinh có thể giữ trạng thái giữa các lượt để quyết định phần tử tiếp theo.
- Flux.generate tuân thủ nhu cầu: nó không tạo và phát vô hạn phần tử vượt quá lượng downstream đã yêu cầu.
- Khi có state supplier, mỗi subscription nhận trạng thái ban đầu riêng.

Ví dụ đơn giản tạo một dãy số:

    Flux<Integer> numbers = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state);
            return state + 1;
        }
    );

Nguồn này phát 1, 2, 3, ... theo nhu cầu. Nó không tạo sẵn toàn bộ dãy số; mỗi lần cần thêm phần tử, generator dùng state hiện tại, phát giá trị đó rồi trả về state kế tiếp.

## 2. Ba phần của bộ sinh có trạng thái

Overload có trạng thái và hàm cleanup có dạng khái quát:

    Flux.generate(
        stateSupplier,
        generator,
        stateConsumer
    );

Ba phần có trách nhiệm khác nhau:

| Thành phần | Kiểu khái quát | Trách nhiệm |
|---|---|---|
| stateSupplier | Callable<S> | Tạo trạng thái ban đầu cho mỗi subscription |
| generator | BiFunction<S, SynchronousSink<T>, S> | Đọc trạng thái hiện tại, phát một tín hiệu và trả về trạng thái kế tiếp |
| stateConsumer | Consumer<S> | Dọn dẹp hoặc xử lý trạng thái khi luồng kết thúc hay bị hủy |

State supplier được gọi khi một subscriber đăng ký. Vì vậy, hai subscriber của cùng một Flux có thể bắt đầu từ hai trạng thái độc lập. Generator nhận state hiện tại và sink; nó có thể phát một giá trị hoặc tín hiệu kết thúc rồi trả về state mới. State consumer được gọi khi sequence kết thúc hoặc subscription bị hủy, phù hợp để đóng tài nguyên được tạo cùng trạng thái.

Không có state supplier thì có thể dùng overload đơn giản khi generator không cần giữ trạng thái riêng. Tuy nhiên, với thuật toán phụ thuộc vào kết quả trước, state supplier và state transition làm cho vòng đời của nguồn rõ ràng hơn.

## 3. SynchronousSink và quy tắc một tín hiệu mỗi lượt

SynchronousSink<T> là đối tượng mà Reactor đưa cho generator để phát tín hiệu. Trong một lần gọi generator, chỉ được phát tối đa một tín hiệu:

- sink.next(value) phát một phần tử.
- sink.complete() kết thúc bình thường.
- sink.error(error) kết thúc do lỗi.

Không gọi next hai lần trong cùng một lượt generator. Cũng không gọi next rồi complete trong cùng lượt. Nếu cần phát nhiều phần tử từ một callback hoặc xử lý nguồn callback bất đồng bộ, hãy chọn API tạo nguồn khác phù hợp thay vì ép nhiều tín hiệu vào Flux.generate.

Giá trị null không được phát qua Reactive Streams. Nếu không có giá trị, hãy biểu diễn bằng cách kết thúc luồng, dùng một kiểu dữ liệu biểu thị sự vắng mặt hoặc chọn mô hình nguồn phù hợp; không gọi sink.next(null).

Generator được gọi tuần tự. Điều này giúp state transition dễ suy luận: state trả về từ lượt trước trở thành state đầu vào của lượt sau. Không nên lưu cùng một state mutable vào biến dùng chung cho nhiều subscription, bởi như vậy các subscriber có thể can thiệp lẫn nhau.

## 4. Ví dụ: bộ đếm có điểm kết thúc

Ví dụ sau tạo ba số đếm ngược. State là số còn lại. Khi state lớn hơn 0, generator phát số hiện tại rồi trả về state giảm một. Khi state bằng 0, generator gửi onComplete.

    import reactor.core.publisher.Flux;

    Flux<Integer> countdown = Flux.generate(
        () -> 3,
        (remaining, sink) -> {
            if (remaining == 0) {
                sink.complete();
                return remaining;
            }

            sink.next(remaining);
            return remaining - 1;
        },
        remaining -> log.info("Generator stopped at {}", remaining)
    );

    countdown.subscribe(
        value -> log.info("Received {}", value),
        error -> log.error("Countdown failed", error),
        () -> log.info("Countdown completed")
    );

Với subscriber mặc định yêu cầu dữ liệu không giới hạn, luồng phát lần lượt 3, 2, 1 rồi generator được gọi thêm một lượt để phát onComplete. State consumer nhận state cuối để ghi log hoặc dọn dẹp.

Kết quả minh họa:

    Received 3
    Received 2
    Received 1
    Generator stopped at 0
    Countdown completed

Điểm đáng chú ý là generator không tự chạy hết dãy ngay khi Flux được khai báo. Việc tạo nguồn là lazy; công việc chỉ bắt đầu khi có subscription và demand.

## 5. Nhu cầu điều khiển số lượt sinh

Flux.generate tuân thủ backpressure của Reactive Streams. Khi subscriber yêu cầu n phần tử, generator có thể được gọi để tạo tối đa n phần tử onNext cho nhu cầu đó. Khi nhu cầu hữu hạn đã được tiêu thụ, nguồn không tiếp tục phát thêm phần tử cho subscriber cho đến khi có request mới.

Ví dụ dùng StepVerifier để kiểm tra một generator vô hạn theo từng đợt:

    import reactor.core.publisher.Flux;
    import reactor.test.StepVerifier;

    Flux<Integer> sequence = Flux.generate(
        () -> 1,
        (current, sink) -> {
            sink.next(current);
            return current + 1;
        }
    );

    StepVerifier.create(sequence, 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .thenCancel()
        .verify();

Verifier bắt đầu với demand bằng 0 nên chưa có phần tử nào được yêu cầu. thenRequest(2) cho phép hai phần tử đầu, rồi thenRequest(3) cho phép thêm ba phần tử. Nguồn vô hạn được hủy sau phần tử thứ năm. Ví dụ cho thấy generator chỉ tạo phần tử khi có nhu cầu, và cancellation dừng việc sinh tiếp.

Demand giới hạn số phần tử phát xuống subscriber; nó không có nghĩa mọi công việc trong generator đều miễn phí. Nếu mỗi lượt thực hiện tính toán nặng hoặc I/O chặn, thời gian xử lý một phần tử vẫn có thể dài. Cần xem xét bản chất của generator và scheduler thực thi nó.

### 5.1. Nguồn hữu hạn và thời điểm nhận tín hiệu hoàn tất

Với generator hữu hạn, bộ sinh thường cần một lượt gọi để nhận ra trạng thái đã hết và gọi sink.complete(). Ví dụ countdown ở trên phát giá trị 1 rồi trả state 0; lượt kế tiếp mới gửi onComplete.

Vì vậy, nếu downstream chỉ yêu cầu đúng số phần tử cuối cùng và không yêu cầu thêm, generator có thể chưa được gọi thêm để phát hiện điều kiện kết thúc. Subscriber có thể cần request tiếp để quan sát terminal signal, hoặc cancel nếu không còn quan tâm đến nguồn. Đây là lý do cần hiểu sự khác nhau giữa số phần tử đã yêu cầu và thời điểm generator kiểm tra trạng thái kết thúc.

Với subscriber thông thường yêu cầu không giới hạn, lượt kiểm tra kết thúc diễn ra ngay sau phần tử cuối và subscriber nhận onComplete. Với consumer điều khiển demand thủ công, hãy thiết kế và kiểm thử cả trường hợp demand vừa đủ phần tử cuối.

## 6. State supplier tạo trạng thái riêng cho từng subscriber

Một Flux có thể được subscribe nhiều lần. Nếu state được tạo ở ngoài generator và dùng chung, các subscriber có thể tiếp tục từ cùng một biến đã bị thay đổi. State supplier tránh tình huống này bằng cách tạo trạng thái ban đầu mới cho mỗi subscription.

Ví dụ:

    Flux<Integer> perSubscriberCounter = Flux.generate(
        () -> 1,
        (current, sink) -> {
            sink.next(current);
            return current + 1;
        }
    );

    perSubscriberCounter.take(3).subscribe(
        value -> log.info("Subscriber A: {}", value)
    );

    perSubscriberCounter.take(3).subscribe(
        value -> log.info("Subscriber B: {}", value)
    );

Mỗi subscriber bắt đầu từ 1 và nhận 1, 2, 3. take(3) hủy subscription sau ba phần tử; subscription thứ hai tạo state riêng và không tiếp tục từ 4 của subscriber thứ nhất.

Với state phức tạp, ưu tiên một đối tượng chỉ thuộc về subscription đó. State immutable giúp việc chuyển đổi dễ kiểm tra, còn state mutable có thể tiết kiệm cấp phát nhưng cần bảo đảm không bị chia sẻ sai cách.

## 7. Dùng generator để đọc tuần tự từ cursor

Một ứng dụng có thể cần đọc dữ liệu tuần tự từ cursor hoặc iterator. State của generator giữ cursor hiện tại; mỗi lượt sinh lấy tối đa một bản ghi. Khi hết dữ liệu, generator phát onComplete. State consumer đóng cursor khi sequence kết thúc hoặc bị hủy.

Ví dụ dưới đây giả định RowCursor là abstraction do ứng dụng định nghĩa, có hasNext(), next() và close():

    interface RowCursor {
        boolean hasNext();
        Row next();
        void close();
    }

    Flux<Row> rows = Flux.generate(
        () -> repository.openCursor(),
        (cursor, sink) -> {
            if (cursor.hasNext()) {
                sink.next(cursor.next());
            } else {
                sink.complete();
            }
            return cursor;
        },
        RowCursor::close
    );

State supplier mở cursor riêng cho mỗi subscriber. Generator đọc tối đa một bản ghi mỗi lượt. State consumer đóng cursor khi luồng hoàn tất hoặc bị hủy, giúp quản lý tài nguyên gắn với vòng đời subscription.

Đây là ví dụ về API đồng bộ. Nếu openCursor(), hasNext() hoặc next() thực hiện I/O chặn, không chạy chúng trên event loop. Có thể chuyển quá trình subscribe và nguồn đồng bộ sang boundedElastic:

    Flux<Row> rowsOnWorker =
        rows.subscribeOn(Schedulers.boundedElastic());

subscribeOn đặt quá trình thực thi nguồn trên scheduler phù hợp cho tác vụ blocking. Nó không biến cursor thành API bất đồng bộ và cũng không bảo đảm một thư viện JDBC có thể dừng ngay lập tức khi cancel. Hãy hiểu khả năng hủy của cursor và bảo đảm close() giải phóng tài nguyên an toàn.

## 8. State transition: chọn mutable hay immutable?

Generator có thể dùng state mutable hoặc immutable. Cả hai đều hợp lệ nếu state thuộc riêng một subscription và generator chỉ cập nhật nó theo một trình tự rõ ràng.

| Cách lưu state | Ví dụ | Ưu điểm | Điều cần chú ý |
|---|---|---|---|
| Immutable | Trả về số đếm mới hoặc record mới | Dễ theo dõi thay đổi, ít trạng thái bị sửa tại chỗ | Có thể tạo thêm đối tượng |
| Mutable | Cập nhật field hoặc phần tử trong mảng | Giảm cấp phát với state nhỏ hoặc cấu trúc phức tạp | Không chia sẻ giữa subscriber; cleanup phải dùng đúng đối tượng |

Ví dụ state immutable:

    record RangeState(int current, int end) {}

    Flux<Integer> range = Flux.generate(
        () -> new RangeState(1, 4),
        (state, sink) -> {
            if (state.current() > state.end()) {
                sink.complete();
                return state;
            }

            sink.next(state.current());
            return new RangeState(state.current() + 1, state.end());
        }
    );

Mỗi lượt trả về RangeState mới, nên không có field nào bị sửa tại chỗ. Ví dụ state mutable có thể dùng một đối tượng chứa cursor và cập nhật vị trí đọc. Khi dùng mutable, không lưu đối tượng đó trong biến static hoặc chia sẻ cho nhiều subscription.

## 9. Xử lý lỗi trong generator

Lỗi có thể xảy ra khi tính giá trị kế tiếp, đọc nguồn dữ liệu hoặc chuyển trạng thái. Nếu generator không thể tiếp tục, nó có thể gửi lỗi qua sink.error(error). Reactor cũng chuyển ngoại lệ phát sinh trong state supplier hoặc generator thành lỗi của publisher.

Ví dụ:

    Flux<Integer> parsedNumbers = Flux.generate(
        () -> 0,
        (state, sink) -> {
            try {
                int value = readNextValue(state);
                sink.next(value);
                return state + 1;
            } catch (EndOfInputException end) {
                sink.complete();
                return state;
            } catch (Exception error) {
                sink.error(error);
                return state;
            }
        }
    );

Ở đây EndOfInputException biểu thị nguồn đã hết nên generator hoàn tất bình thường. Lỗi khác kết thúc luồng bằng onError. Không nên dùng một ngoại lệ chung để biểu thị cả hết dữ liệu lẫn lỗi hệ thống nếu hai tình huống cần được xử lý khác nhau.

Nếu lỗi có thể phục hồi, có thể đặt toán tử như onErrorResume ở downstream để chuyển sang nguồn dự phòng. Tuy nhiên, một generator đã phát onError là kết thúc; không thể tiếp tục dùng cùng subscription như thể lỗi chưa xảy ra.

## 10. Giới hạn của Flux.generate

Flux.generate phù hợp với nguồn đồng bộ, tuần tự, mỗi lượt tạo tối đa một phần tử. Không nên dùng nó cho mọi loại nguồn.

- Nếu callback bất đồng bộ có thể phát nhiều sự kiện độc lập, hãy cân nhắc Flux.create hoặc API tích hợp callback phù hợp.
- Nếu cần đẩy dữ liệu từ một producer đồng bộ nhưng có thể phát nhiều phần tử trong một lần đăng ký, hãy chọn cơ chế tạo nguồn cho phép nhiều lần phát.
- Nếu thao tác đọc chặn, hãy chuyển nó khỏi event loop bằng scheduler phù hợp hoặc dùng driver bất đồng bộ.
- Nếu nguồn cần lưu lịch sử hoặc phát lại cho subscriber đến muộn, hãy chọn cơ chế replay hoặc một kho lưu trữ sự kiện thay vì chỉ dùng generator.

Không gọi sink.next nhiều lần trong cùng một lượt generator để mô phỏng một nguồn push. Quy tắc một tín hiệu mỗi lượt là một phần của hợp đồng của API này.

## 11. Kiểm thử generator

StepVerifier giúp kiểm tra các giá trị, tín hiệu kết thúc và cancellation mà không cần chạy một ứng dụng đầy đủ.

Kiểm tra dãy hữu hạn:

    StepVerifier.create(countdown)
        .expectNext(3, 2, 1)
        .verifyComplete();

Kiểm tra generator vô hạn và nhu cầu hữu hạn:

    StepVerifier.create(sequence, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(1)
        .expectNext(2)
        .thenCancel()
        .verify();

Kiểm tra state cleanup khi hủy:

    AtomicBoolean closed = new AtomicBoolean();

    Flux<Integer> resourceBacked = Flux.generate(
        () -> new CursorState(),
        (state, sink) -> {
            sink.next(state.nextValue());
            return state;
        },
        state -> {
            state.close();
            closed.set(true);
        }
    );

    StepVerifier.create(resourceBacked)
        .expectNextCount(2)
        .thenCancel()
        .verify();

    assert closed.get();

Trong bài kiểm thử thực tế, dùng assertion của JUnit hoặc thư viện kiểm thử để xác nhận closed. Ví dụ giả định CursorState có nextValue() và close(); phần quan trọng là state consumer được gọi khi subscription bị hủy.

## 12. Những lỗi thường gặp

**Phát nhiều hơn một tín hiệu trong một lượt.** SynchronousSink chỉ cho phép một next hoặc một terminal signal mỗi lần generator được gọi. Hãy chia công việc thành các lượt sinh.

**Dùng chung state cho nhiều subscriber.** Tạo state trong state supplier để mỗi subscription có vòng đời độc lập.

**Giữ tài nguyên mà không cleanup.** Nếu state mở cursor, file hoặc kết nối, cung cấp state consumer để đóng khi complete hoặc cancel.

**Đặt I/O blocking trên event loop.** Generator chạy đồng bộ; thao tác chặn trong generator sẽ chặn thread thực thi nó. Chuyển nguồn blocking sang boundedElastic hoặc dùng API không chặn.

**Nhầm request với số lần generator luôn được gọi trước.** Demand giới hạn số phần tử onNext được phát. Generator hữu hạn có thể cần lượt tiếp theo để phát hiện trạng thái kết thúc, vì vậy hãy kiểm tra cả trường hợp subscriber chỉ yêu cầu đúng số phần tử cuối.

**Bỏ qua lỗi và trạng thái kết thúc.** Phân biệt hết dữ liệu với lỗi thật; dùng complete cho trường hợp kết thúc bình thường và error cho trường hợp thất bại.

## 13. Checklist thiết kế nguồn bằng bộ sinh trạng thái

Trước khi dùng Flux.generate, hãy xác định:

1. Trạng thái tối thiểu nào cần giữ để tính phần tử tiếp theo?
2. State supplier có tạo state mới cho mỗi subscriber không?
3. Mỗi lượt generator có phát tối đa một tín hiệu không?
4. Điều kiện kết thúc bình thường và điều kiện lỗi được phân biệt rõ chưa?
5. Nếu state giữ tài nguyên, state consumer có đóng nó khi complete hoặc cancel không?
6. Generator có thực hiện I/O blocking hoặc tính toán kéo dài không?
7. Demand hữu hạn có thể làm trì hoãn lượt kiểm tra kết thúc hay cleanup không?
8. StepVerifier đã kiểm tra giá trị, backpressure, terminal signal và cancellation chưa?

Flux.generate là công cụ phù hợp khi nguồn có thể mô tả như một máy trạng thái đồng bộ: nhận state, phát một phần tử hoặc tín hiệu kết thúc, rồi trả về state tiếp theo. Khi kết hợp state riêng cho từng subscription, nhu cầu downstream và cleanup theo vòng đời, ta có thể tạo nguồn dữ liệu tuần tự, có kiểm soát và dễ kiểm thử trong các pipeline reactive Java.
