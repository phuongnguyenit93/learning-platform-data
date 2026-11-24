# BaseSubscriber và kiểm soát nhu cầu nhận dữ liệu

## Vì sao cần kiểm soát demand ở subscriber?

Trong Reactive Streams, subscriber không chỉ nhận dữ liệu mà còn quyết định lượng dữ liệu mình sẵn sàng tiếp nhận. Sau khi nhận `Subscription` qua `onSubscribe`, subscriber gọi `request(n)` để yêu cầu thêm tối đa `n` phần tử hoặc gọi `cancel()` khi không còn cần dữ liệu. Cơ chế này tạo nền tảng cho backpressure: bên tiêu thụ biểu đạt năng lực xử lý, còn publisher phải tôn trọng lượng demand đã được yêu cầu.

Trong Project Reactor, các overload `subscribe` tiện dụng thường yêu cầu không giới hạn. Cách này phù hợp với pipeline nhỏ, nguồn hữu hạn hoặc trường hợp bên nhận có thể xử lý mọi phần tử. Khi cần kiểm soát số phần tử theo từng bước, theo lô hoặc theo điều kiện nghiệp vụ, Reactor cung cấp `BaseSubscriber<T>` để cài đặt hành vi của subscriber một cách tường minh.

`BaseSubscriber` là một lớp cơ sở triển khai subscriber theo API Reactor. Bạn ghi đè các hook vòng đời như `hookOnSubscribe`, `hookOnNext`, `hookOnError`, `hookOnComplete`, `hookOnCancel` và `hookFinally`, sau đó gọi `request(n)` hoặc `cancel()` tại thời điểm phù hợp. Cách này hữu ích khi subscriber cần điều tiết dữ liệu theo năng lực xử lý, nhưng cũng đòi hỏi hiểu rõ demand được cộng dồn và cách toán tử trung gian chuyển tiếp yêu cầu.

## Subscription và demand tại ranh giới subscriber

Một subscription bắt đầu khi publisher gọi `onSubscribe(subscription)`. Từ thời điểm đó, subscriber có thể yêu cầu dữ liệu. `request(n)` nhận một số nguyên dương kiểu `long`; mỗi `onNext` tiêu thụ một đơn vị demand hữu hạn. Các lần gọi request được cộng dồn. Nếu tổng demand vượt giới hạn biểu diễn của `long`, nó được xem như `Long.MAX_VALUE`, tức nhu cầu không giới hạn.

Publisher không được phát nhiều `onNext` hơn lượng demand còn lại. Tuy nhiên, publisher có thể phát ít hơn nếu nguồn chưa có dữ liệu hoặc kết thúc sớm. `onComplete` và `onError` là tín hiệu kết thúc, không tiêu thụ một đơn vị demand như `onNext`.

Ví dụ, nếu subscriber gọi `request(3)` rồi gọi tiếp `request(2)` trước khi nhận đủ dữ liệu, tổng nhu cầu là năm phần tử. Sau mỗi `onNext`, demand còn lại giảm một. Subscriber không cần gọi `request(1)` cho từng phần tử nếu đã yêu cầu một lô đủ lớn; chỉ cần bổ sung demand khi đã xử lý một phần lô hoặc khi có thêm năng lực tiêu thụ.

Demand được đo tại ranh giới giữa publisher và subscriber. Nếu pipeline có `filter`, `buffer`, `flatMap` hoặc `publishOn`, số phần tử nguồn được yêu cầu có thể khác số phần tử subscriber cuối yêu cầu. `BaseSubscriber` kiểm soát demand ở subscription của chính nó; các toán tử trung gian vẫn có thể điều chỉnh demand, prefetch hoặc giữ dữ liệu trong hàng đợi.

## Cấu trúc cơ bản của BaseSubscriber

Một subscriber tùy chỉnh thường cần thực hiện ba việc:

1. Khởi tạo lượng demand ban đầu trong `hookOnSubscribe`.
2. Xử lý từng phần tử trong `hookOnNext`, rồi quyết định khi nào yêu cầu thêm dữ liệu.
3. Xử lý lỗi, hoàn tất hoặc hủy trong các hook vòng đời tương ứng.

Ví dụ sau yêu cầu một phần tử mỗi lần và chủ động dừng sau khi nhận giá trị `5`:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

final class StepSubscriber extends BaseSubscriber<Integer> {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        System.out.println("Đăng ký xong, yêu cầu phần tử đầu tiên");
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Đã nhận: " + value);

        if (value == 5) {
            cancel();
            return;
        }

        request(1);
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Nguồn hoàn tất bình thường");
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.err.println("Nguồn gặp lỗi: " + error.getMessage());
    }

    @Override
    protected void hookOnCancel() {
        System.out.println("Subscriber đã hủy việc nhận dữ liệu");
    }
}

Flux.range(1, 10).subscribe(new StepSubscriber());
```

Subscriber chỉ yêu cầu một phần tử tại một thời điểm. Sau khi xử lý giá trị nhỏ hơn `5`, nó bổ sung một đơn vị demand. Khi nhận `5`, nó gọi `cancel()` và không yêu cầu thêm. Vì subscription bị hủy, subscriber không nhận `onComplete` từ nguồn; hook `hookOnCancel` được gọi để phản ánh việc hủy. Nếu tín hiệu đang được xử lý đồng thời với thời điểm hủy, callback cần an toàn với tình huống cạnh tranh.

Trong ví dụ, `Flux.range` là nguồn đồng bộ có thể tôn trọng demand. Khi `request(1)` được gọi, nguồn có thể phát `onNext` ngay trong luồng gọi request. Vì vậy, không nên giả định mỗi lần request luôn tạo một tác vụ bất đồng bộ hoặc callback sẽ đến sau khi phương thức request trả về.

## Yêu cầu theo lô thay vì từng phần tử

Yêu cầu từng phần tử giúp kiểm soát chính xác nhưng tạo nhiều lần gọi `request`. Với một subscriber xử lý được một nhóm phần tử, có thể yêu cầu theo lô để giảm chi phí điều phối. Ví dụ sau yêu cầu bốn phần tử ban đầu, xử lý đủ một nhóm rồi mới bổ sung bốn phần tử tiếp theo:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

final class BatchSubscriber extends BaseSubscriber<Integer> {
    private static final int BATCH_SIZE = 4;
    private int receivedInBatch;

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(BATCH_SIZE);
    }

    @Override
    protected void hookOnNext(Integer value) {
        process(value);
        receivedInBatch++;

        if (receivedInBatch == BATCH_SIZE) {
            receivedInBatch = 0;
            request(BATCH_SIZE);
        }
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.err.println("Lỗi xử lý luồng: " + error.getMessage());
    }

    @Override
    protected void hookOnComplete() {
        System.out.println("Đã nhận hết dữ liệu");
    }

    @Override
    protected void hookFinally(SignalType signalType) {
        System.out.println("Kết thúc subscription: " + signalType);
    }

    private void process(Integer value) {
        System.out.println("Đang xử lý: " + value);
    }
}

Flux.range(1, 10).subscribe(new BatchSubscriber());
```

Ở đây, demand được bổ sung sau mỗi bốn phần tử đã xử lý. Nguồn chỉ có mười phần tử nên nhóm cuối có hai phần tử; sau đó nguồn hoàn tất mà không cần đủ một nhóm mới. Subscriber không được giả định mọi lô đều đầy đủ, vì nguồn có thể kết thúc hoặc lỗi giữa một lô.

Nếu công việc xử lý mỗi phần tử kéo dài, chỉ yêu cầu lô tiếp theo sau khi đã xử lý xong lô hiện tại sẽ giới hạn lượng dữ liệu subscriber nhận thêm. Tuy nhiên, ví dụ trên xử lý đồng bộ ngay trong `hookOnNext`. Nếu xử lý cần gọi API bất đồng bộ, hãy biểu diễn thao tác đó trong cùng pipeline bằng `flatMap` và giới hạn concurrency; không gọi `subscribe()` lồng bên trong hook để tạo một luồng công việc tách rời khỏi subscription đang quản lý.

## Các hook vòng đời cần biết

| Hook | Khi được gọi | Công việc phù hợp |
|---|---|---|
| `hookOnSubscribe(Subscription)` | Khi subscriber nhận subscription | Thiết lập demand ban đầu hoặc hủy ngay nếu không cần dữ liệu |
| `hookOnNext(T)` | Khi có một phần tử theo demand | Xử lý phần tử và bổ sung demand khi phù hợp |
| `hookOnError(Throwable)` | Khi publisher kết thúc do lỗi | Ghi nhận lỗi, cập nhật trạng thái hoặc giải phóng trạng thái riêng của subscriber |
| `hookOnComplete()` | Khi publisher hoàn tất bình thường | Hoàn tất tác vụ tổng hợp hoặc thông báo kết thúc |
| `hookOnCancel()` | Khi chính `BaseSubscriber` hủy subscription, chẳng hạn qua `cancel()` hoặc `dispose()` | Phản ứng với cancellation do subscriber này khởi tạo |
| `hookFinally(SignalType)` | Sau khi subscription kết thúc bằng complete, error hoặc cancel | Dọn dẹp chung, ghi metric và ghi nhận loại kết thúc |

`hookOnCancel` chỉ liên quan đến hủy. `hookFinally` phù hợp khi cần một điểm dọn dẹp chung cho mọi kiểu kết thúc; tham số `SignalType` cho biết kết thúc do `ON_COMPLETE`, `ON_ERROR` hay `CANCEL`. Nếu cả `hookOnCancel` và `hookFinally` cùng giải phóng một tài nguyên, thao tác cleanup cần idempotent để tránh giải phóng hai lần.

`BaseSubscriber` có hành vi mặc định yêu cầu không giới hạn trong hook đăng ký mặc định. Khi ghi đè `hookOnSubscribe`, bạn chịu trách nhiệm gọi `request(n)` hoặc `requestUnbounded()` nếu muốn nhận dữ liệu. Nếu không phát sinh demand, nguồn không phát `onNext` cho subscriber; nó vẫn có thể gửi tín hiệu kết thúc như lỗi hoặc hoàn tất tùy trạng thái nguồn.

## Chuyển sang nhu cầu không giới hạn

Có trường hợp ban đầu cần kiểm soát chặt, nhưng sau một điều kiện nhất định subscriber có thể tiếp nhận toàn bộ dữ liệu còn lại. `requestUnbounded()` biểu đạt nhu cầu không giới hạn, tương đương yêu cầu `Long.MAX_VALUE`:

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

final class WarmupSubscriber extends BaseSubscriber<Integer> {
    private int inspected;

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(3);
    }

    @Override
    protected void hookOnNext(Integer value) {
        inspected++;
        System.out.println("Kiểm tra: " + value);

        if (inspected == 3) {
            requestUnbounded();
        } else {
            request(1);
        }
    }
}

Flux.range(1, 20).subscribe(new WarmupSubscriber());
```

Subscriber kiểm tra ba phần tử đầu theo demand hữu hạn, sau đó chuyển sang nhận phần còn lại mà không cần gọi request từng đợt. Chỉ dùng cách này khi bên nhận thực sự có khả năng xử lý lượng dữ liệu còn lại và nguồn có giới hạn hợp lý. `requestUnbounded()` loại bỏ giới hạn demand tại subscriber này; nó không làm cho nguồn vô hạn tự hoàn tất và cũng không giới hạn bộ nhớ của các toán tử tích lũy.

## Kiểm soát cancellation từ BaseSubscriber

`BaseSubscriber` cung cấp `cancel()` để hủy subscription hiện tại. Có thể gọi trong hook khi đã đủ dữ liệu, khi điều kiện nghiệp vụ không còn đúng hoặc khi subscriber không thể tiếp tục xử lý. Cancellation truyền ngược qua các toán tử đến publisher nguồn.

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

final class ThresholdSubscriber extends BaseSubscriber<Integer> {
    private final int threshold;

    ThresholdSubscriber(int threshold) {
        this.threshold = threshold;
    }

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Nhận: " + value);
        if (value >= threshold) {
            cancel();
        } else {
            request(1);
        }
    }
}

Flux.range(1, 100).subscribe(new ThresholdSubscriber(7));
```

Khi nhận giá trị đạt ngưỡng, subscriber hủy nguồn và không yêu cầu thêm. Điều này có thể giúp dừng việc đọc hoặc phát dữ liệu tiếp theo. Tuy nhiên, cancellation chỉ là yêu cầu dừng subscription; một thao tác I/O đang chạy ở thư viện bên ngoài có thể không dừng tức thì nếu adapter không liên kết cancellation với API hủy thực tế.

Nếu nguồn sở hữu listener, timer, cursor hoặc kết nối, nguồn cần gắn cleanup với vòng đời subscription. Với nguồn tạo bằng `Flux.create`, có thể dùng `FluxSink.onCancel` hoặc `onDispose`; với tài nguyên đồng bộ hoặc bất đồng bộ, cân nhắc `using` hoặc `usingWhen`. `BaseSubscriber.cancel()` không tự đóng mọi tài nguyên bên ngoài nếu publisher không cung cấp hành vi cleanup đó.

## BaseSubscriber không thay thế các toán tử điều tiết

`BaseSubscriber` điều khiển demand ở ranh giới subscriber. Trong pipeline có toán tử trung gian, demand có thể được chuyển tiếp hoặc điều chỉnh. Ví dụ, `filter` có thể yêu cầu thêm phần tử upstream để bù cho những phần tử bị loại bỏ; `buffer(10)` cần nhiều phần tử nguồn để tạo một phần tử dạng danh sách; `publishOn` có thể prefetch và giữ phần tử trong hàng đợi.

```java
import java.util.List;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 100)
    .filter(number -> number % 10 == 0)
    .buffer(2)
    .doOnRequest(n -> System.out.println("Demand tại vị trí này: " + n))
    .subscribe(new BaseSubscriber<List<Integer>>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(1); // Yêu cầu một batch.
        }

        @Override
        protected void hookOnNext(List<Integer> batch) {
            System.out.println("Batch: " + batch);
            request(1);
        }
    });
```

Trong ví dụ, subscriber yêu cầu các phần tử dạng `List<Integer>` ở cuối pipeline, mỗi lần một batch. `buffer(2)` cần hai số đã qua filter để tạo một danh sách; `filter` có thể phải kiểm tra nhiều số nguồn hơn để tìm đủ hai số chia hết cho mười. Demand mà subscriber phát ra không phải số lượng phần tử nguồn ban đầu cần đọc.

`limitRate(n)` có thể điều chỉnh các đợt yêu cầu được chuyển upstream; `onBackpressureBuffer`, `onBackpressureDrop` và các toán tử liên quan định nghĩa chính sách khi nguồn không thể tạm dừng phát theo demand. Các toán tử này giải quyết những khía cạnh khác nhau. `BaseSubscriber` cho biết bên nhận muốn bao nhiêu; toán tử điều tiết hoặc buffer quyết định cách nhu cầu được phối hợp với nguồn và hàng đợi.

## Nguồn hot và giới hạn của request

Với nguồn cold có hỗ trợ backpressure như `Flux.range`, publisher có thể phát theo nhu cầu. Với nguồn hot hoặc API callback bên ngoài, sự kiện có thể xuất hiện độc lập với tốc độ subscriber yêu cầu. Khi adapter không thể tạm dừng nguồn, chỉ giảm demand ở subscriber không đủ để ngăn dữ liệu đến.

Trong trường hợp đó, cần chọn chính sách overflow khi tạo nguồn, ví dụ `Flux.create` với `BUFFER`, `DROP`, `LATEST` hoặc `ERROR`, tùy ngữ nghĩa dữ liệu. Mỗi chiến lược có đánh đổi:

- `BUFFER` giữ sự kiện chờ xử lý nhưng cần giới hạn và giám sát bộ nhớ; hàng đợi không giới hạn có thể tăng vô hạn.
- `DROP` bỏ sự kiện khi downstream chưa thể nhận; phù hợp nếu sự kiện bị bỏ có thể chấp nhận.
- `LATEST` giữ giá trị mới nhất, hữu ích cho trạng thái cập nhật liên tục khi giá trị cũ không còn quan trọng.
- `ERROR` báo lỗi khi không thể chuyển tiếp theo chính sách; phù hợp khi mất dữ liệu không được chấp nhận và cần xử lý sự cố rõ ràng.

Không nên cho rằng `request(1)` buộc một message broker hoặc event listener chỉ phát đúng một sự kiện. Khả năng điều tiết ở tầng nguồn phụ thuộc API adapter và giao thức bên ngoài. Cần kiểm tra liệu client có hỗ trợ pause/resume, prefetch có giới hạn, acknowledgement hoặc cơ chế backpressure riêng hay không.

## BaseSubscriber là đối tượng cho một subscription

Mỗi `BaseSubscriber` nên được tạo mới cho một lần đăng ký. Không dùng lại cùng một instance cho nhiều publisher hoặc nhiều subscription độc lập. Lớp này giữ trạng thái subscription hiện tại; khi được đăng ký lần nữa, subscription trước có thể bị hủy để tránh một subscriber nhận tín hiệu từ nhiều nguồn cùng lúc.

Ví dụ, hãy tạo subscriber mới trong mỗi lần subscribe:

```java
Flux<Integer> source = Flux.range(1, 5);

source.subscribe(new StepSubscriber());
source.subscribe(new StepSubscriber());
```

Hai instance có demand và vòng đời riêng. Nếu dùng chung một đối tượng subscriber, trạng thái đếm lô, điều kiện hủy và subscription có thể ảnh hưởng lẫn nhau. Khi cần chia sẻ một lần thực thi cho nhiều bên nhận, hãy dùng cơ chế multicast như `share()` hoặc `publish()` thay vì tái sử dụng một `BaseSubscriber`.

## Những lỗi thường gặp khi điều khiển demand

- **Ghi đè `hookOnSubscribe` nhưng quên gọi `request`:** không có demand nên subscriber không nhận `onNext`. Hãy yêu cầu một lượng ban đầu hoặc gọi `requestUnbounded()` có chủ đích.
- **Gọi `request(0)` hoặc số âm:** vi phạm hợp đồng Reactive Streams. Chỉ yêu cầu số dương.
- **Yêu cầu thêm trước khi xử lý xong lô hiện tại:** demand tích lũy, có thể khiến nhiều phần tử hơn dự kiến được gửi đến subscriber.
- **Cho rằng request ở subscriber là số phần tử nguồn phải đọc:** các toán tử filter, buffer, flatMap và publishOn có thể thay đổi quan hệ demand.
- **Dùng request nhỏ để kiểm soát một nguồn hot không hỗ trợ backpressure:** nguồn vẫn có thể phát; cần chính sách overflow hoặc cơ chế pause/resume ở adapter.
- **Xử lý I/O chặn trực tiếp trong `hookOnNext`:** callback giữ thread phát tín hiệu và có thể làm chậm hoặc nghẽn pipeline. Dùng publisher bất đồng bộ và giới hạn concurrency cho công việc I/O.
- **Gọi `subscribe()` lồng bên trong hook:** tạo subscription tách rời, khó phối hợp lỗi, demand và cancellation. Hãy ghép publisher bằng toán tử trong cùng pipeline.
- **Dùng lại một BaseSubscriber cho nhiều nguồn:** trạng thái subscription và bộ đếm có thể bị ghi đè. Tạo instance riêng cho mỗi subscription.
- **Xem cancellation như hoàn tất bình thường:** `cancel()` không phát `onComplete`; dùng `hookOnCancel` hoặc `hookFinally` để xử lý vòng đời.

## Cách chọn mức demand phù hợp

Khi triển khai subscriber tùy chỉnh, hãy bắt đầu từ khả năng xử lý thực tế của bên nhận. Nếu mỗi phần tử cần xử lý ngay và chi phí thấp, yêu cầu từng phần tử hoặc một lô nhỏ. Nếu xử lý theo batch, chọn kích thước lô phù hợp với giới hạn API lưu trữ và bộ nhớ. Nếu công việc được thực hiện bất đồng bộ, giới hạn số tác vụ in-flight bằng các toán tử như `flatMap` thay vì chỉ tăng demand liên tục.

Theo dõi demand tại các ranh giới bằng `doOnRequest`, đồng thời quan sát số phần tử đang chờ, prefetch, buffer và thời gian xử lý. Kiểm tra hành vi khi nguồn hoàn tất sớm, phát lỗi, bị hủy hoặc phát nhanh hơn khả năng tiêu thụ. Với nguồn hot, xác nhận chính sách overflow và cơ chế dừng ở tầng adapter.

`BaseSubscriber` giúp biến năng lực tiêu thụ thành các yêu cầu cụ thể. Khi dùng đúng, subscriber có thể nhận theo từng phần tử hoặc từng lô, chủ động dừng khi đủ dữ liệu và phối hợp tốt hơn với nguồn. Khi kết hợp với hiểu biết về toán tử trung gian, backpressure và vòng đời tài nguyên, ứng dụng Reactor kiểm soát được lượng công việc đang hoạt động mà vẫn giữ đúng hợp đồng Reactive Streams.
