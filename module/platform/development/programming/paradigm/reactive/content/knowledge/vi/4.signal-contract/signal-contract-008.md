# Giá trị null và cách biểu diễn dữ liệu thiếu trong Reactive Streams

Trong Java, **null** thường được dùng để biểu thị một giá trị chưa tồn tại. Cách biểu diễn này không phù hợp với hợp đồng tín hiệu của Reactive Streams: một luồng chỉ phát các phần tử dữ liệu khác **null**, hoặc kết thúc mà không phát phần tử nào. Vì vậy, khi đưa dữ liệu từ cơ sở dữ liệu, API hay mã Java cũ vào pipeline reactive, ta phải chuyển trạng thái thiếu dữ liệu thành một biểu diễn rõ ràng trước khi phát tín hiệu.

Bài học này thuộc chương **Hợp đồng tín hiệu** của module **REACTIVE_PROGRAMMING**. Module tập trung vào tư duy reactive qua luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các ví dụ sử dụng **Mono**, **Flux** và những toán tử của Project Reactor để làm rõ cách xử lý dữ liệu thiếu mà vẫn giữ đúng hợp đồng.

## Hợp đồng tín hiệu không có phần tử null

Một **Publisher<T>** giao tiếp với **Subscriber<T>** thông qua các tín hiệu:

1. **onSubscribe(subscription)** thông báo đăng ký.
2. **onNext(value)** phát một phần tử dữ liệu; tín hiệu này có thể xuất hiện không lần nào hoặc nhiều lần.
3. **onError(error)** kết thúc luồng bằng lỗi, hoặc **onComplete()** kết thúc luồng bình thường. Một trong hai tín hiệu kết thúc được gửi tối đa một lần và không có **onNext** nào theo sau.

**null** không phải là một phần tử hợp lệ để gửi qua **onNext**. Quy tắc 2.13 của đặc tả Reactive Streams yêu cầu lời gọi phương thức tín hiệu có tham số **null** phải ném **NullPointerException**. Publisher tuân thủ hợp đồng vì thế không thể dùng **onNext(null)** để báo rằng dữ liệu không tồn tại.

Quy tắc này giúp mọi phần tử trong pipeline có ý nghĩa rõ ràng. Nếu một toán tử nhận được **null**, nó không cần đoán xem đó là dữ liệu hợp lệ, dữ liệu bị thiếu hay lỗi lập trình. Các thư viện reactive có thể kiểm tra và báo lỗi ngay tại ranh giới nơi giá trị **null** xuất hiện.

Ví dụ sau không hợp lệ trong Reactor:

~~~java
Mono<String> name = Mono.just(null); // Ném NullPointerException
~~~

**Mono.just** yêu cầu một giá trị khác **null** ngay khi tạo publisher. Tương tự, một hàm biến đổi trong **map** không được trả về **null**:

~~~java
Mono<String> normalized = Mono.just("  An  ")
    .map(value -> null); // Pipeline kết thúc bằng NullPointerException
~~~

Nếu kết quả biến đổi không có dữ liệu, hãy biểu diễn trạng thái đó bằng **Mono.empty()** hoặc một kiểu dữ liệu tường minh như **Optional**, tùy theo ý nghĩa nghiệp vụ.

## Phân biệt dữ liệu thiếu, luồng rỗng và lỗi

Ba tình huống dưới đây khác nhau về ý nghĩa và tín hiệu:

| Tình huống | Biểu diễn | Tín hiệu quan sát được |
|---|---|---|
| Có dữ liệu | **Mono.just(value)** hoặc phần tử trong **Flux** | **onNext(value)**, sau đó có thể là **onComplete** |
| Không có kết quả theo nghiệp vụ | **Mono.empty()** | **onComplete**, không có **onNext** |
| Không thể lấy kết quả do lỗi | **Mono.error(error)** | **onError(error)** |

**Mono.empty()** không chứa một giá trị **null**. Nó là một publisher hoàn tất bình thường mà không phát phần tử nào. Với **Flux**, **Flux.empty()** cũng hoàn tất mà không phát phần tử; một **Flux** khác có thể phát nhiều phần tử khác **null** trước khi hoàn tất.

Ví dụ, tìm người dùng theo ID có thể trả về một trong hai kết quả:

~~~java
Mono<User> findUser(String id) {
    return repository.findById(id);
}
~~~

Nếu không tìm thấy người dùng, repository có thể trả về **Mono.empty()**. Nếu truy vấn gặp sự cố, publisher phát **onError**. Không nên chuyển cả hai tình huống thành **null**, vì khi đó tầng gọi sẽ mất khả năng phân biệt “không tồn tại” và “không thể truy vấn”.

Khi nghiệp vụ yêu cầu xem trường hợp không tìm thấy là lỗi, có thể chuyển trạng thái rỗng thành lỗi bằng **switchIfEmpty**:

~~~java
Mono<User> requiredUser = repository.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));
~~~

Ngược lại, nếu không tìm thấy là một kết quả bình thường, hãy giữ **Mono.empty()** hoặc cung cấp giá trị thay thế bằng **defaultIfEmpty**:

~~~java
Mono<String> displayName = repository.findDisplayName(id)
    .defaultIfEmpty("Khách");
~~~

Giá trị mặc định cũng phải khác **null**. Dùng **switchIfEmpty** khi cần chuyển sang một publisher khác, chẳng hạn gọi nguồn dự phòng; dùng **defaultIfEmpty** khi chỉ cần một giá trị thay thế trực tiếp.

## Chuyển dữ liệu nullable thành publisher hợp lệ

Mã Java cũ hoặc API bên ngoài có thể trả về **null**. Hãy chuẩn hóa kết quả ngay tại ranh giới tích hợp, trước khi đưa nó vào các toán tử tiếp theo.

### Dùng Mono.justOrEmpty

Khi đã có một giá trị nullable, **Mono.justOrEmpty** chuyển giá trị khác **null** thành **Mono** có một phần tử và chuyển **null** thành **Mono.empty()**:

~~~java
String nickname = legacyUserService.findNickname(userId);

Mono<String> nicknameMono = Mono.justOrEmpty(nickname);
~~~

Cách này phù hợp khi giá trị đã được tính sẵn. Lưu ý lời gọi **findNickname** ở ví dụ trên diễn ra ngay lúc tạo pipeline, vì Java đánh giá đối số trước khi gọi **justOrEmpty**.

### Dùng Mono.fromCallable cho lời gọi cần thực hiện khi subscribe

Nếu việc đọc dữ liệu cần được trì hoãn đến lúc subscribe, có thể dùng **fromCallable**:

~~~java
Mono<User> userMono = Mono.fromCallable(
    () -> legacyDao.findById(userId)
);
~~~

Trong Reactor, nếu **Callable** trả về **null**, **Mono.fromCallable** hoàn tất rỗng. Nếu lời gọi ném exception, pipeline phát **onError**. Nhờ vậy, cả kết quả nullable lẫn lỗi đều được chuyển thành tín hiệu hợp lệ mà không phát **null**.

### Dùng Optional khi trạng thái vắng mặt cần là dữ liệu

Đôi khi tầng nghiệp vụ cần nhận một kết quả duy nhất để mô tả rõ rằng thao tác đã hoàn tất và không tìm thấy dữ liệu. Khi đó, có thể phát một **Optional.empty()** như một phần tử:

~~~java
Mono<Optional<User>> userResult = Mono.fromSupplier(
    () -> Optional.ofNullable(legacyDao.findById(userId))
);
~~~

**Optional.empty()** là một đối tượng Java khác **null**, nên nó có thể được phát hợp lệ qua **onNext**. Cách biểu diễn này khác với **Mono.empty()**:

~~~java
Mono<User> noSignal = Mono.empty();

Mono<Optional<User>> oneSignal =
    Mono.just(Optional.<User>empty());
~~~

**noSignal** hoàn tất mà không phát phần tử. **oneSignal** phát đúng một phần tử là **Optional.empty()**, sau đó hoàn tất. Sự khác biệt này hữu ích khi một API cần phân biệt “không có kết quả được phát” với “đã phát kết quả và kết quả cho biết không có giá trị”.

Hãy chú ý khi dùng **Mono.justOrEmpty** với **Optional**:

~~~java
Mono<User> flattened = Mono.justOrEmpty(Optional.<User>empty());
Mono<Optional<User>> preserved =
    Mono.just(Optional.<User>empty());
~~~

**justOrEmpty(Optional.empty())** chuyển thành **Mono.empty()** và không phát **Optional**. **just(Optional.empty())** giữ nguyên **Optional.empty()** như một phần tử. Chọn cách nào tùy vào hợp đồng mà tầng nhận dữ liệu cần.

## Khi cần phân biệt thuộc tính không có, null tường minh và có giá trị

**Optional<T>** biểu diễn hai trạng thái: có giá trị hoặc không có giá trị. Nhưng một số giao thức cần phân biệt ba trạng thái:

- **Missing:** thuộc tính không xuất hiện trong dữ liệu đầu vào.
- **Explicit null:** thuộc tính có xuất hiện và được đặt thành **null**.
- **Present:** thuộc tính có xuất hiện với một giá trị cụ thể.

Ví dụ, trong một yêu cầu cập nhật hồ sơ, thuộc tính **nickname** bị lược bỏ có thể mang nghĩa “giữ nguyên tên hiện tại”, còn **nickname: null** có thể mang nghĩa “xóa tên hiện tại”. Nếu chuyển cả hai thành **Optional.empty()**, thông tin nghiệp vụ quan trọng sẽ bị mất.

Có thể mô hình hóa ba trạng thái bằng một kiểu dữ liệu riêng. Ví dụ dưới đây dùng sealed interface và record của Java 17:

~~~java
import java.util.Objects;

public sealed interface FieldValue<T>
        permits FieldValue.Missing,
                FieldValue.ExplicitNull,
                FieldValue.Present {

    record Missing<T>() implements FieldValue<T> {}

    record ExplicitNull<T>() implements FieldValue<T> {}

    record Present<T>(T value) implements FieldValue<T> {
        public Present {
            Objects.requireNonNull(value, "value");
        }
    }
}
~~~

Kiểu **Present** chủ động từ chối **null**. Vì cả ba trạng thái đều là các đối tượng khác **null**, chúng có thể được phát như những phần tử bình thường của Reactive Streams.

Khi đọc một cây JSON bằng Jackson, có thể kiểm tra thuộc tính trước khi tạo phần tử:

~~~java
Mono<FieldValue<String>> nickname = Mono.fromSupplier(() -> {
    if (!json.has("nickname")) {
        return new FieldValue.Missing<>();
    }

    JsonNode value = json.get("nickname");
    if (value == null || value.isNull()) {
        return new FieldValue.ExplicitNull<>();
    }

    return new FieldValue.Present<>(value.asText());
});
~~~

**Mono.fromSupplier** phát một **FieldValue** khác **null** cho cả ba trường hợp. Publisher chỉ hoàn tất rỗng nếu chính supplier không tạo ra phần tử theo cách xử lý riêng của nó; ở ví dụ này, mỗi nhánh đều trả về một đối tượng trạng thái. Tầng nghiệp vụ có thể xử lý từng trạng thái mà không cần dùng **null** làm tín hiệu ngầm.

## Chọn toán tử theo ý nghĩa của dữ liệu thiếu

Các toán tử thường gặp có hành vi khác nhau khi upstream không phát phần tử:

| Toán tử | Hành vi khi upstream rỗng | Trường hợp sử dụng |
|---|---|---|
| **defaultIfEmpty(value)** | Phát giá trị mặc định rồi hoàn tất | Có giá trị dự phòng đơn giản |
| **switchIfEmpty(publisher)** | Đăng ký publisher thay thế | Đọc nguồn dự phòng hoặc chuyển thành lỗi |
| **filter(predicate)** | Nếu không phần tử nào vượt qua điều kiện, kết quả rỗng | Loại phần tử không thỏa điều kiện |
| **flatMap(mapper)** | Mapper có thể trả về **Mono.empty()** | Một bước xử lý hợp lệ nhưng không tạo kết quả |
| **onErrorResume(mapper)** | Chỉ chạy khi có **onError** | Phục hồi từ lỗi theo chính sách nghiệp vụ |

Không nên nhầm **onErrorResume** với **switchIfEmpty**. Một publisher rỗng đã hoàn tất bình thường nên không kích hoạt xử lý lỗi. Ngược lại, lỗi không tự biến thành một kết quả rỗng.

Ví dụ, tìm tên hiển thị và dùng tên mặc định khi không có kết quả:

~~~java
Mono<String> displayName = repository.findDisplayName(userId)
    .filter(name -> !name.isBlank())
    .switchIfEmpty(Mono.defer(() -> settings.defaultDisplayName()));
~~~

**filter** có thể làm cho publisher trở nên rỗng nếu tên là chuỗi trắng. **switchIfEmpty** khi đó đăng ký nguồn dự phòng. **Mono.defer** giúp chỉ tạo publisher dự phòng khi nhánh này thực sự được dùng.

Với **flatMap**, hãy trả về publisher rỗng nếu một bước xử lý không có kết quả:

~~~java
Mono<Profile> profile = repository.findUser(userId)
    .flatMap(user -> {
        if (!user.isActive()) {
            return Mono.empty();
        }
        return profileRepository.findByUserId(user.id());
    });
~~~

Ở đây, người dùng không hoạt động dẫn đến không có profile được phát. Nếu cần giữ lý do “không hoạt động” như dữ liệu để tầng sau xử lý, hãy phát một kiểu kết quả tường minh thay vì dùng **Mono.empty()**.

**filter(Objects::nonNull)** không phải cách sửa một publisher đã vi phạm hợp đồng. Nếu upstream đã gọi **onNext(null)**, lỗi xảy ra tại ranh giới tín hiệu trước khi **filter** có cơ hội kiểm tra phần tử. Hãy chuẩn hóa dữ liệu nullable trước khi tạo publisher, bằng **justOrEmpty**, **fromCallable**, **Optional** hoặc một kiểu trạng thái riêng.

## Kiểm thử sự khác biệt giữa rỗng và Optional.empty

**StepVerifier** của Reactor Test giúp kiểm tra chính xác số phần tử và tín hiệu kết thúc. Hai kiểm thử sau thể hiện hai hợp đồng khác nhau:

~~~java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();

StepVerifier.create(Mono.just(Optional.<String>empty()))
    .expectNext(Optional.empty())
    .verifyComplete();
~~~

Kiểm thử thứ nhất xác nhận publisher hoàn tất mà không phát phần tử. Kiểm thử thứ hai xác nhận publisher phát một **Optional.empty()** rồi mới hoàn tất. Có thể kiểm tra thêm trường hợp dữ liệu nullable từ **Callable**:

~~~java
StepVerifier.create(
        Mono.fromCallable(() -> (String) null)
    )
    .verifyComplete();
~~~

Và kiểm tra rằng mapper trả về **null** bị báo lỗi:

~~~java
StepVerifier.create(
        Mono.just("value").map(value -> (String) null)
    )
    .expectError(NullPointerException.class)
    .verify();
~~~

Các kiểm thử này bảo vệ hợp đồng của pipeline ở những ranh giới dễ phát sinh lỗi: dữ liệu nullable từ mã cũ, phép biến đổi trả về **null**, và sự khác nhau giữa không phát phần tử với phát một đối tượng biểu diễn sự vắng mặt.

## Nguyên tắc áp dụng trong pipeline thực tế

Khi thiết kế pipeline reactive, hãy xác định rõ ý nghĩa của việc thiếu dữ liệu trước khi chọn kiểu biểu diễn:

1. Dùng **Mono.empty()** khi nghiệp vụ nói rằng không có kết quả và việc hoàn tất rỗng là đủ thông tin.
2. Dùng **Mono.error(...)** khi thao tác thất bại hoặc dữ liệu không tồn tại phải được xem là lỗi.
3. Dùng **Optional<T>** khi trạng thái có hoặc không có giá trị cần được phát như một phần tử dữ liệu.
4. Dùng kiểu trạng thái riêng như **FieldValue<T>** khi cần giữ khác biệt giữa thuộc tính bị lược bỏ, thuộc tính null tường minh và thuộc tính có giá trị.
5. Chuẩn hóa **null** ngay tại ranh giới với thư viện, API hoặc mã Java cũ; không để **null** đi sâu vào các toán tử.
6. Kiểm thử cả số lượng phần tử lẫn tín hiệu kết thúc để bảo đảm pipeline giữ đúng ý nghĩa của dữ liệu.

Trong Reactive Streams, dữ liệu thiếu được thể hiện bằng cấu trúc của luồng hoặc bằng một đối tượng miền khác **null**. Khi lựa chọn biểu diễn dựa trên ý nghĩa nghiệp vụ, Publisher và Subscriber có thể trao đổi dữ liệu nhất quán, các toán tử xử lý được trạng thái rỗng một cách dự đoán được, và lỗi thật sự vẫn được giữ riêng qua **onError**.
