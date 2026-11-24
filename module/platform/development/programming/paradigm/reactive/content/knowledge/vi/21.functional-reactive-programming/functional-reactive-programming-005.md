# Đọc đồng thời nhiều giá trị phụ thuộc và lỗi cập nhật trung gian

Trong lập trình phản ứng hàm (Functional Reactive Programming — FRP), một giá trị có thể được xem là kết quả của những giá trị đầu vào thay đổi theo thời gian. Ví dụ, màn hình tổng quan cần thông tin người dùng, quyền truy cập và cấu hình hiển thị; một báo giá phụ thuộc vào giá sản phẩm và mức giảm giá; trạng thái đơn hàng phụ thuộc vào nhiều nguồn sự kiện.

Khi các giá trị đến từ nhiều Publisher, ứng dụng cần kết hợp chúng để tạo một kết quả mới. Project Reactor cung cấp các toán tử như `Mono.zip` và `Flux.combineLatest` cho việc này. Tuy nhiên, cách kết hợp ảnh hưởng trực tiếp đến tính nhất quán của kết quả. Một pipeline có thể phát ra trạng thái trung gian được tính từ một giá trị mới và một giá trị cũ, dù từng nguồn riêng lẻ đều phát dữ liệu đúng.

Bài học này phân biệt việc đọc đồng thời các nguồn độc lập với việc kết hợp các luồng thay đổi liên tục, giải thích vì sao cập nhật trung gian xuất hiện và trình bày cách giữ tính nhất quán khi nhiều giá trị thuộc cùng một thay đổi nghiệp vụ.

Các kiểu `UserProfile`, `Permission`, `Dashboard`, `Price`, `Discount`, `Quote` và các client trong ví dụ là kiểu miền minh họa do ứng dụng định nghĩa.

## 1. Kết hợp nhiều nguồn độc lập bằng Mono.zip

Một trường hợp phổ biến là tải một lần nhiều dữ liệu độc lập để tạo một kết quả tổng hợp. Ví dụ, màn hình tổng quan cần hồ sơ người dùng và danh sách quyền. Hai yêu cầu không phụ thuộc kết quả của nhau nên có thể được đăng ký cùng lúc:

~~~java
record Dashboard(UserProfile profile, Set<Permission> permissions) {}

Mono<Dashboard> dashboard =
    Mono.zip(
        userClient.loadProfile(userId),
        permissionClient.loadPermissions(userId),
        Dashboard::new
    );
~~~

`Mono.zip` đăng ký các nguồn Mono và đợi mỗi nguồn phát một giá trị. Khi đã có đủ giá trị, hàm kết hợp tạo một `Dashboard`. Với các client reactive như WebClient hoặc R2DBC, mỗi yêu cầu thường bắt đầu khi được subscribe và có thể tiến hành bất đồng bộ cùng lúc; pipeline không cần chờ yêu cầu thứ nhất hoàn tất rồi mới bắt đầu yêu cầu thứ hai.

Việc zip subscribe các nguồn không có nghĩa Reactor tự tạo một thread riêng cho từng nguồn. Nếu một nguồn gọi API chặn, nó có thể chặn luồng đang subscribe trước khi nguồn tiếp theo được đăng ký. Hãy chuyển từng lời gọi chặn sang scheduler phù hợp:

~~~java
import java.util.Set;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<UserProfile> profile = Mono.fromCallable(
        () -> legacyUserClient.loadProfile(userId)
    )
    .subscribeOn(Schedulers.boundedElastic());

Mono<Set<Permission>> permissions = Mono.fromCallable(
        () -> legacyPermissionClient.loadPermissions(userId)
    )
    .subscribeOn(Schedulers.boundedElastic());

Mono<Dashboard> dashboard = Mono.zip(profile, permissions, Dashboard::new);
~~~

Với API reactive không chặn, thường không cần thêm scheduler chỉ để gọi zip. Chọn scheduler theo đặc tính của nguồn và công việc, không xem nó là cơ chế tạo tính nhất quán dữ liệu.

Hàm kết hợp nên là hàm thuần: nhận các giá trị đầu vào và tạo kết quả, không thực hiện thêm I/O hoặc thay đổi trạng thái dùng chung. Điều này làm kết quả dễ dự đoán và kiểm thử.

Nếu nguồn thứ hai cần kết quả của nguồn thứ nhất, hai nguồn không độc lập và không nên ghép bằng zip chỉ để biểu diễn quan hệ phụ thuộc. Dùng `flatMap`:

~~~java
Mono<OrderDetails> details =
    orderClient.loadOrder(orderId)
        .flatMap(order ->
            customerClient.loadCustomer(order.customerId())
                .map(customer -> new OrderDetails(order, customer))
        );
~~~

Ở đây, yêu cầu tải khách hàng chỉ có thể được tạo sau khi đã biết customerId từ đơn hàng. `flatMap` thể hiện đúng quan hệ tuần tự đó.

### Đọc đồng thời không đồng nghĩa với một snapshot giao dịch

Dù hai Mono được subscribe cùng lúc, điều đó không bảo đảm chúng đọc cùng một phiên bản dữ liệu ở cơ sở dữ liệu. Ví dụ, hồ sơ người dùng có thể được đọc trước khi một giao dịch cập nhật quyền hoàn tất, trong khi danh sách quyền được đọc sau giao dịch. Kết quả zip khi ấy hợp lệ theo từng nguồn nhưng không nhất thiết là một snapshot nhất quán.

Nếu nghiệp vụ yêu cầu tất cả giá trị thuộc cùng một snapshot, cần bảo đảm ở tầng dữ liệu: dùng một truy vấn tổng hợp, một transaction với isolation phù hợp, một snapshot/version chung hoặc API trả về toàn bộ trạng thái trong một phản hồi. `Mono.zip` chỉ kết hợp các kết quả; nó không tạo transaction phân tán giữa các nguồn.

## 2. Kết hợp các giá trị thay đổi liên tục bằng Flux.combineLatest

Với các nguồn phát cập nhật liên tục, một lần đọc đơn lẻ không đủ. Ví dụ, giá sản phẩm và mức giảm giá đều thay đổi theo thời gian. Mỗi khi một nguồn phát giá trị mới, ứng dụng muốn tính lại báo giá dựa trên giá trị mới nhất của cả hai nguồn.

`Flux.combineLatest` lưu giá trị gần nhất của từng nguồn. Khi tất cả nguồn đã phát ít nhất một giá trị, mỗi lần một nguồn phát cập nhật mới, toán tử kết hợp giá trị mới đó với giá trị gần nhất của các nguồn còn lại.

~~~java
record Price(BigDecimal amount) {}
record Discount(BigDecimal rate) {}
record Quote(BigDecimal finalAmount) {}

Flux<Quote> quotes = Flux.combineLatest(
    priceUpdates,
    discountUpdates,
    (price, discount) -> new Quote(
        price.amount().multiply(BigDecimal.ONE.subtract(discount.rate()))
    )
);
~~~

Giả sử giá ban đầu là 100 và tỷ lệ giảm là 10%, báo giá là 90. Khi giá thay đổi thành 120, `combineLatest` lập tức tính lại bằng giá mới và mức giảm gần nhất. Khi mức giảm tiếp tục thay đổi thành 15%, toán tử lại tính báo giá với mức giảm mới.

Đặc điểm quan trọng:

- Toán tử cần ít nhất một giá trị ban đầu từ mỗi nguồn trước khi có thể tạo kết quả.
- Sau khi đã có giá trị ban đầu, mỗi lần một nguồn phát cập nhật đều có thể tạo một kết quả mới.
- Giá trị của nguồn không phát cập nhật được giữ làm giá trị mới nhất cho lần kết hợp tiếp theo.
- Toán tử không yêu cầu các nguồn phát cùng tốc độ hoặc cùng số lượng phần tử.

Đây là hành vi phù hợp cho các giá trị trạng thái độc lập, ví dụ nhiệt độ mới nhất và ngưỡng cảnh báo mới nhất. Nó cũng là nguyên nhân khiến trạng thái trung gian xuất hiện khi nhiều nguồn thực ra đang cùng mô tả một thay đổi nghiệp vụ.

## 3. Lỗi cập nhật trung gian (glitch)

Một glitch xảy ra khi pipeline phát kết quả từ một tổ hợp giá trị chưa nhất quán về mặt nghiệp vụ. Hiện tượng thường xuất hiện khi một thay đổi logic cần cập nhật nhiều nguồn riêng biệt, nhưng các nguồn phát theo những thời điểm khác nhau.

Giả sử một giao dịch cập nhật đồng thời giá sản phẩm và tỷ lệ giảm:

- Trạng thái trước giao dịch: giá 100, giảm 10%.
- Trạng thái sau giao dịch: giá 120, giảm 15%.

Ứng dụng lưu giá và mức giảm ở hai Publisher độc lập. Khi giá phát phiên bản mới trước, `combineLatest` có thể tính báo giá bằng giá 120 và mức giảm cũ 10%. Sau đó, khi mức giảm phát phiên bản mới, nó tính lại bằng 120 và 15%.

~~~mermaid
sequenceDiagram
    participant P as Price Publisher
    participant D as Discount Publisher
    participant C as combineLatest
    participant U as Downstream

    P->>C: price = 100
    D->>C: discount = 10%
    C->>U: quote = 90
    Note over P,D: Một giao dịch cập nhật cả hai giá trị
    P->>C: price = 120
    C->>U: quote = 108 (trạng thái trung gian)
    D->>C: discount = 15%
    C->>U: quote = 102 (trạng thái cuối)
~~~

Báo giá 108 không phải kết quả của giao dịch trước hoặc sau. Nó là kết quả của hai phiên bản khác nhau. Nếu downstream hiển thị ngay, gửi thông báo hoặc ghi kết quả ra hệ thống khác, trạng thái trung gian có thể bị hiểu nhầm là một kết quả nghiệp vụ hợp lệ.

Đây không phải lỗi tính toán của `combineLatest`. Toán tử thực hiện đúng hợp đồng: mỗi khi một nguồn thay đổi, nó kết hợp giá trị mới với giá trị mới nhất mà nó đang biết từ các nguồn khác. Nó không biết rằng hai cập nhật thuộc cùng một giao dịch và cần được công bố nguyên tử.

## 4. Mô phỏng glitch bằng TestPublisher

Có thể tạo tình huống cập nhật riêng lẻ một cách xác định bằng `TestPublisher`:

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

record Versioned<T>(long revision, T value) {}
record QuoteCandidate(long priceRevision, long discountRevision,
                      BigDecimal price, BigDecimal discount) {}

@Test
void combineLatestCoThePhatTrangThaiTrungGian() {
    TestPublisher<Versioned<BigDecimal>> prices = TestPublisher.create();
    TestPublisher<Versioned<BigDecimal>> discounts = TestPublisher.create();

    Flux<QuoteCandidate> candidates = Flux.combineLatest(
        prices.flux(),
        discounts.flux(),
        (price, discount) -> new QuoteCandidate(
            price.revision(),
            discount.revision(),
            price.value(),
            discount.value()
        )
    );

    StepVerifier.create(candidates)
        .then(() -> {
            prices.next(new Versioned<>(1, new BigDecimal("100")));
            discounts.next(new Versioned<>(1, new BigDecimal("0.10")));
        })
        .expectNextMatches(candidate ->
            candidate.priceRevision() == 1
                && candidate.discountRevision() == 1
        )
        .then(() -> prices.next(
            new Versioned<>(2, new BigDecimal("120"))
        ))
        .expectNextMatches(candidate ->
            candidate.priceRevision() == 2
                && candidate.discountRevision() == 1
        )
        .then(() -> discounts.next(
            new Versioned<>(2, new BigDecimal("0.15"))
        ))
        .expectNextMatches(candidate ->
            candidate.priceRevision() == 2
                && candidate.discountRevision() == 2
        )
        .thenCancel()
        .verify();
}
~~~

Phép thử cho thấy lần cập nhật giá tạo ra một candidate mang revision 2 của giá và revision 1 của mức giảm. Khi mức giảm chuyển sang revision 2, candidate tiếp theo mới có hai revision trùng nhau.

Revision giúp phát hiện trạng thái trộn phiên bản. Nó không tự ngăn glitch; ứng dụng cần quyết định candidate nào được phép đi tiếp.

## 5. Dùng version để chỉ phát tổ hợp nhất quán

Nếu mỗi nguồn phát một giá trị cho mọi revision nghiệp vụ, có thể lọc các tổ hợp có cùng revision:

~~~java
record VersionedValue<T>(long revision, T value) {}
record ConsistentQuote(long revision, BigDecimal amount) {}

Flux<ConsistentQuote> consistentQuotes = Flux.combineLatest(
        priceVersions,
        discountVersions,
        (price, discount) -> {
            if (price.revision() != discount.revision()) {
                return Optional.<ConsistentQuote>empty();
            }

            BigDecimal amount = price.value().multiply(
                BigDecimal.ONE.subtract(discount.value())
            );

            return Optional.of(
                new ConsistentQuote(price.revision(), amount)
            );
        }
    )
    .filter(Optional::isPresent)
    .map(candidate -> candidate.orElseThrow());
~~~

Khi giá chuyển sang revision 2 nhưng mức giảm vẫn là revision 1, candidate bị loại. Khi mức giảm phát revision 2, tổ hợp mới được phát.

Cách này chỉ đúng khi các nguồn đều phát giá trị có revision tương ứng cho mỗi lần cập nhật logic. Nếu mức giảm không thay đổi trong giao dịch mới và vì thế không phát revision mới, bộ lọc có thể loại mọi candidate cho đến khi cả hai nguồn có cùng revision. Trong trường hợp đó, cần phát một snapshot có revision chung hoặc dùng một mô hình cập nhật tổng hợp.

Version cũng cần được tạo từ cùng một ranh giới nghiệp vụ. Nếu mỗi service tự tăng revision độc lập, hai số revision bằng nhau không chứng minh rằng dữ liệu thuộc cùng một snapshot. Có thể dùng transaction ID, sequence chung hoặc version của aggregate.

## 6. Ưu tiên một luồng snapshot cho thay đổi nguyên tử

Nếu nhiều trường phải thay đổi như một đơn vị nghiệp vụ, cách rõ ràng nhất là phát một snapshot bất biến chứa toàn bộ trường liên quan.

~~~java
record PricingSnapshot(
    long revision,
    BigDecimal unitPrice,
    BigDecimal discountRate
) {}

Flux<Quote> quotes = pricingSnapshots
    .map(snapshot -> new Quote(
        snapshot.unitPrice().multiply(
            BigDecimal.ONE.subtract(snapshot.discountRate())
        )
    ));
~~~

Một phần tử `PricingSnapshot` chứa cả giá và mức giảm của cùng một revision. Khi có giao dịch mới, nguồn phát một snapshot mới; downstream tính toán một lần từ bộ giá trị nhất quán đó.

Mô hình này tránh việc downstream quan sát nửa đầu của một cập nhật nhiều trường. Nó cũng giúp log, replay và kiểm thử dễ dàng hơn vì mỗi phần tử thể hiện một trạng thái hoàn chỉnh.

Nếu nguồn dữ liệu ban đầu chỉ phát các thay đổi riêng lẻ, hãy gom chúng ở ranh giới transaction trước khi phát snapshot. Ví dụ, tầng domain có thể xử lý tất cả thay đổi của một transaction, cập nhật aggregate trong một bước và phát một `PricingSnapshot`. Việc chỉ nối `scan` lên các event rời rạc không tự giải quyết glitch: nếu transaction phát hai event riêng, `scan` vẫn có thể phát trạng thái sau event thứ nhất rồi trạng thái sau event thứ hai.

## 7. Khi nào dùng zip thay vì combineLatest?

`zip` và `combineLatest` đều kết hợp nhiều Publisher, nhưng ý nghĩa khác nhau:

| Tiêu chí | `zip` | `combineLatest` |
|---|---|---|
| Cách ghép | Ghép phần tử thứ nhất với phần tử thứ nhất, thứ hai với thứ hai... | Ghép mỗi cập nhật với giá trị mới nhất của các nguồn còn lại. |
| Cần mỗi nguồn có giá trị ban đầu? | Cần phần tử tương ứng ở từng nguồn để tạo tuple tiếp theo. | Cần ít nhất một giá trị từ mọi nguồn để tạo kết quả đầu tiên. |
| Nguồn phát nhanh/chậm khác nhau | Giá trị nhanh hơn có thể phải chờ trong queue để ghép đúng vị trí. | Giá trị mới nhất được thay thế; nguồn khác không cần phát cùng số lượng. |
| Dùng phù hợp | Ghép các phần tử có quan hệ theo vị trí hoặc theo lượt. | Tạo trạng thái từ các giá trị hiện hành độc lập. |
| Rủi ro | Ghép sai nếu vị trí thứ n ở các nguồn không đại diện cùng một nghiệp vụ; queue có thể tăng. | Phát trạng thái trộn phiên bản nếu các nguồn cập nhật cùng giao dịch nhưng không nguyên tử. |

Ví dụ, hai luồng kết quả của cùng một danh sách công việc theo thứ tự có thể ghép bằng `zip` nếu phần tử thứ n thực sự thuộc cùng một công việc. Hai luồng trạng thái nhiệt độ và ngưỡng cảnh báo thường phù hợp với `combineLatest` vì mỗi thay đổi cần dùng giá trị mới nhất của luồng còn lại.

Không nên dùng `zip` như một cách chữa glitch nếu các luồng cập nhật không có cùng nhịp. Nếu giá phát năm lần nhưng mức giảm chỉ phát một lần, `zip` chỉ ghép được một cặp rồi chờ mức giảm tiếp theo; các giá trị còn lại có thể phải nằm chờ. Quan trọng hơn, ghép theo vị trí không chứng minh hai giá trị thuộc cùng transaction.

## 8. Xử lý lỗi khi kết hợp nhiều nguồn

Với `Mono.zip`, nếu một nguồn phát lỗi, phép kết hợp mặc định kết thúc bằng lỗi và hủy các nguồn còn lại đang hoạt động. Nếu một nguồn hoàn tất rỗng trước khi có giá trị, kết quả zip cũng có thể hoàn tất rỗng vì không thể tạo tuple đầy đủ.

~~~java
Mono<Dashboard> dashboard = Mono.zip(
        userClient.loadProfile(userId),
        permissionClient.loadPermissions(userId),
        Dashboard::new
    )
    .onErrorMap(error ->
        new DashboardLoadException("Không thể tải dữ liệu tổng quan", error)
    );
~~~

Nếu cần chờ các nguồn khác kết thúc trước khi phát lỗi, có thể dùng `Mono.zipDelayError`:

~~~java
Mono<Dashboard> dashboard = Mono.zipDelayError(
    userClient.loadProfile(userId),
    permissionClient.loadPermissions(userId),
    Dashboard::new
);
~~~

Nếu một nguồn có thể rỗng nhưng nghiệp vụ có giá trị mặc định, hãy xử lý rõ trước khi zip:

~~~java
Mono<Preferences> preferences =
    preferenceClient.load(userId)
        .defaultIfEmpty(Preferences.defaults());

Mono<Dashboard> dashboard = Mono.zip(
    userClient.loadProfile(userId),
    preferences,
    Dashboard::new
);
~~~

Chỉ dùng giá trị mặc định nếu trạng thái thiếu dữ liệu thực sự có nghĩa đó. Nếu hồ sơ người dùng bắt buộc phải tồn tại, nên chuyển empty thành lỗi miền bằng `switchIfEmpty`.

Với `Flux.combineLatest`, lỗi từ một nguồn làm luồng kết hợp kết thúc bằng lỗi. Có thể phục hồi lỗi ở từng nguồn trước khi kết hợp, nhưng cần xác định giá trị dự phòng có đại diện cho một trạng thái hợp lệ hay không. Dùng một giá trị mặc định giả có thể làm downstream tính toán và phát ra một kết quả trông hợp lệ dù dữ liệu thật đang thiếu.

Ví dụ, nếu dịch vụ giảm giá lỗi, có thể phát một trạng thái rõ ràng như `DiscountStatus.unavailable()` thay vì giả định tỷ lệ giảm bằng 0 mà không thông báo. Khi cần phân biệt giá trị, lỗi và trạng thái đang tải, hãy biểu diễn chúng bằng một kiểu kết quả miền thay vì chỉ dùng giá trị số.

## 9. Đừng nhầm scheduler với tính nguyên tử

Chuyển mỗi nguồn sang scheduler riêng có thể làm các yêu cầu I/O tiến hành đồng thời, nhưng không bảo đảm các cập nhật được công bố nguyên tử:

~~~java
Flux<Quote> quotes = Flux.combineLatest(
    priceUpdates.subscribeOn(Schedulers.parallel()),
    discountUpdates.subscribeOn(Schedulers.parallel()),
    this::calculateQuote
);
~~~

Scheduler quyết định nơi công việc được thực thi. Nó không tạo transaction giữa hai Publisher, không đồng bộ version và không loại bỏ trạng thái trung gian. Thậm chí, việc các nguồn phát trên các thread khác nhau khiến thứ tự cập nhật quan sát được thay đổi theo lịch thực thi.

Nếu cần một thứ tự cập nhật nhất quán, hãy tuần tự hóa ở ranh giới aggregate hoặc phát snapshot bất biến. Chỉ dùng scheduler để chọn nơi thực hiện công việc phù hợp, chẳng hạn chuyển API chặn sang `boundedElastic` hoặc tách bước tính toán CPU phù hợp; đừng dựa vào scheduler để đảm bảo tính nhất quán dữ liệu.

## 10. Kiểm thử kết quả tổng hợp và lỗi trung gian

Kiểm thử cần bao phủ cả kết quả cuối lẫn những trạng thái mà pipeline có thể phát trên đường đi.

Kiểm thử `Mono.zip`:

~~~java
import java.util.Set;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void zipKetHopHaiKetQuaDocLap() {
    Mono<Dashboard> result = Mono.zip(
        Mono.just(new UserProfile("u-1")),
        Mono.just(Set.of(Permission.READ)),
        Dashboard::new
    );

    StepVerifier.create(result)
        .expectNextMatches(dashboard ->
            dashboard.profile().id().equals("u-1")
                && dashboard.permissions().contains(Permission.READ)
        )
        .verifyComplete();
}
~~~

Kiểm thử `combineLatest` cho thấy mỗi nguồn cập nhật đều tạo kết quả mới:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void combineLatestTinhLaiKhiMotNguonThayDoi() {
    Flux<String> result = Flux.combineLatest(
        Flux.just("A", "B"),
        Flux.just("1", "2"),
        (left, right) -> left + right
    );

    StepVerifier.create(result)
        .expectNext("B1", "B2")
        .verifyComplete();
}
~~~

Nguồn đầu tiên phát đồng bộ A rồi B trước khi nguồn thứ hai phát 1 và 2. Khi nguồn thứ hai bắt đầu phát, giá trị mới nhất của nguồn đầu tiên là B; vì vậy kết quả là B1 rồi B2. Đây là một minh họa rõ ràng về việc `combineLatest` giữ giá trị mới nhất, không ghép theo vị trí.

Kiểm thử chính sách revision nên xác nhận candidate có revision không khớp bị loại, còn candidate có revision khớp được phát. Cũng cần kiểm tra trường hợp một nguồn không phát revision mới, một nguồn hoàn tất rỗng và một nguồn phát lỗi để xác minh pipeline không tạo trạng thái giả.

Các trường hợp nên có trong bộ kiểm thử:

- Các Mono độc lập đều có giá trị và tạo đúng aggregate.
- Một Mono lỗi làm kết quả zip lỗi theo chính sách đã chọn.
- Một Mono rỗng được xử lý thành mặc định hoặc lỗi miền.
- `combineLatest` không phát trước khi mọi nguồn có giá trị ban đầu.
- Mỗi cập nhật sau đó kết hợp với giá trị mới nhất của các nguồn còn lại.
- Candidate có version khác nhau không đi đến downstream nếu chính sách yêu cầu cùng revision.
- Snapshot nguyên tử chỉ tạo một kết quả cho mỗi transaction nghiệp vụ.
- Cancellation downstream được truyền đến các nguồn đang hoạt động.

## 11. Quy tắc chọn mô hình kết hợp

Trước khi ghép nhiều Publisher, hãy xác định quan hệ giữa dữ liệu:

| Quan hệ giữa các nguồn | Cách tổ chức |
|---|---|
| Các lần đọc độc lập, mỗi nguồn trả một kết quả | `Mono.zip` |
| Giá trị phụ thuộc vào kết quả của nguồn trước | `flatMap` |
| Nhiều trạng thái thay đổi độc lập, cần dùng giá trị mới nhất | `Flux.combineLatest` |
| Các phần tử ở cùng vị trí đại diện cho cùng một lượt | `zip` |
| Nhiều trường phải cập nhật nguyên tử trong một nghiệp vụ | Một Publisher phát snapshot tổng hợp |
| Nhiều nguồn có version chung và mỗi nguồn phát mọi revision | `combineLatest` kết hợp kiểm tra revision |

Khi dùng `combineLatest`, hãy hỏi liệu mọi tổ hợp giá trị mới nhất đều là trạng thái nghiệp vụ hợp lệ hay không. Nếu câu trả lời là không, cần một ranh giới transaction, snapshot hoặc version chung trước khi phát kết quả. Không nên chỉ lọc hoặc trì hoãn tùy tiện ở downstream mà không xác định rõ chính sách khi thiếu một phần cập nhật.

Kết hợp Publisher là cách xây dựng giá trị từ nhiều nguồn thay đổi. `Mono.zip` phù hợp với các kết quả đơn độc lập; `Flux.combineLatest` phù hợp với trạng thái liên tục được tạo từ các giá trị mới nhất. Lỗi cập nhật trung gian xuất hiện khi một thay đổi logic bị chia thành nhiều lần phát độc lập. Thiết kế snapshot bất biến, version chung và chính sách lỗi rõ ràng giúp pipeline FRP tạo kết quả nhất quán, dễ kiểm thử và đáng tin cậy trong ứng dụng Java reactive.

