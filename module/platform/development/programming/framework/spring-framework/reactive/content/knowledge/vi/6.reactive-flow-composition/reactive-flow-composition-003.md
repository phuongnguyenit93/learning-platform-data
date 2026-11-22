# combineLatest và dữ liệu cập nhật liên tục

**Chủ đề:** Spring Framework Reactive → **Ghép và chia luồng**.

Khi một màn hình cần hiển thị dữ liệu đến từ nhiều nguồn **thay đổi độc lập**, thường không muốn chờ một cặp sự kiện có cùng vị trí hay cùng thời điểm. Ví dụ, giá sản phẩm cập nhật theo giao dịch, tỷ giá cập nhật theo thị trường, trạng thái tồn kho cập nhật từ hệ thống kho. Mỗi khi một nguồn đưa ra thông tin mới, màn hình cần tính lại **ảnh chụp tổng hợp từ các giá trị mới nhất đã biết**.

Trong Project Reactor, `Flux.combineLatest(...)` giải quyết nhu cầu đó: **sau khi mọi nguồn đã phát ít nhất một phần tử, mỗi cập nhật mới của bất kỳ nguồn nào có thể tạo một kết quả tổng hợp mới bằng phần tử mới nhất của từng nguồn**.

Khác biệt cần nhớ ngay: `combineLatest` ghép theo **trạng thái mới nhất ở thời điểm xử lý sự kiện**, không tự đồng bộ thời gian nghiệp vụ, không chờ các nguồn phát cùng lúc và không ghép cặp theo thứ tự như `zip`.

## 1. Vấn đề: nhiều nguồn cập nhật với nhịp khác nhau

Giả sử hai luồng:

- `prices: Flux<Integer>` phát giá mới: 100, 120, 130, 140.
- `currencies: Flux<String>` phát đơn vị tiền: "USD", sau đó "EUR".

Ta muốn một chuỗi hiển thị có định dạng `"giá đơn vị"`.

Xét thứ tự sự kiện xác định sau:

| Bước | Sự kiện mới | Giá mới nhất | Đơn vị mới nhất | `combineLatest` phát ra |
|---:|---|---:|---|---|
| 1 | Giá = 100 | 100 | Chưa có | Chưa phát |
| 2 | Giá = 120 | 120 | Chưa có | Chưa phát |
| 3 | Đơn vị = USD | 120 | USD | **120 USD** |
| 4 | Giá = 130 | 130 | USD | **130 USD** |
| 5 | Đơn vị = EUR | 130 | EUR | **130 EUR** |
| 6 | Nguồn đơn vị hoàn tất | 130 | EUR đã biết | Chưa có kết quả mới |
| 7 | Giá = 140 | 140 | EUR đã biết | **140 EUR** |
| 8 | Nguồn giá hoàn tất | 140 | EUR | Luồng kết quả hoàn tất |

Điểm quan trọng của ví dụ:

1. Trước bước 3, **chưa đủ dữ liệu**: dù giá đã thay đổi hai lần, không thể tạo cặp giá–đơn vị cho đến khi luồng đơn vị phát giá trị đầu tiên.
2. Khi đơn vị phát "USD", operator sử dụng **120**, giá mới nhất, chứ không quay lại phát "100 USD".
3. Bước 4 và 5 đều sinh kết quả mới; không cần đợi nguồn bên kia có cập nhật tương ứng.
4. Khi nguồn đơn vị **đã phát ít nhất một phần tử rồi hoàn tất**, giá trị mới nhất của nó vẫn có thể được dùng trong các tổ hợp đến khi tất cả nguồn hoàn tất.
5. Bản thân tín hiệu `onComplete` không phải một cập nhật giá trị, nên không tự tạo thêm snapshot.

### Sơ đồ thời gian

```text
Thời gian  ──────────────────────────────────────────────────────▶

prices       100       120         130                 140       |
currencies                  USD             EUR    complete
                            ▲
                         đã có ít nhất
                         một giá trị từ
                         mỗi nguồn

combined                    120 USD     130 USD   130 EUR  140 EUR |
                            ▲
                      lần kết hợp đầu tiên
```

Sơ đồ biểu diễn **thứ tự sự kiện**, không ngụ ý khoảng cách thời gian cố định. Khi nhiều source thực sự phát trên các thread khác nhau, thứ tự quan sát có thể khác qua từng lần chạy; đừng dùng ví dụ thời gian để cam kết thứ tự trong hệ thống concurrent thực tế.

## 2. Quy tắc hoạt động của Flux.combineLatest

Với `n` nguồn `S1, S2, ..., Sn`, operator giữ lại giá trị mới nhất đã quan sát ở mỗi nguồn. Diễn biến về mặt khái niệm:

1. **Subscribe** vào các nguồn cần kết hợp, phối hợp demand/backpressure.
2. Chờ đến khi **tất cả nguồn đều có một giá trị đầu tiên**. Chưa đủ dữ liệu thì chưa gọi combinator để phát snapshot hoàn chỉnh.
3. Khi một nguồn `Si` phát item mới, cập nhật giá trị mới nhất của `Si`.
4. Khi đã có đủ các giá trị, gọi hàm `combinator` với bộ giá trị mới nhất hiện có, rồi phát kết quả xuống downstream.
5. Lặp lại khi các nguồn phát tiếp; dừng theo completion, error hoặc cancellation.

Công thức khái niệm:

```text
latest = [last(S1), last(S2), ..., last(Sn)]

onNext(Si, value):
    latest[i] = value
    if mọi nguồn đã có giá trị:
        downstream.onNext(combinator(latest))
```

Đây là **pseudocode giải thích**, không phải API nội bộ đầy đủ. Reactor còn xử lý request, prefetch, hàng đợi, hủy, lỗi và đồng bộ tín hiệu; không giả định mảng `latest` là bộ nhớ chung an toàn để ứng dụng tự sửa.

**Kết quả là `Flux<R>`**, bởi một nguồn có thể phát nhiều cập nhật và khiến tổ hợp phát nhiều snapshot. Không cần số lượng item của các nguồn bằng nhau. Nguồn nhanh có thể cập nhật liên tục trong khi nguồn chậm giữ nguyên giá trị mới nhất.

### Không phải “đã có giá trị” là “dữ liệu còn mới”

Giá trị mới nhất là **mới nhất mà operator đã nhận**, không bảo đảm mới về thời gian thực. Nếu luồng tỷ giá im lặng một giờ, `combineLatest` vẫn có thể kết hợp giá cập nhật với tỷ giá từ một giờ trước.

Vì vậy, khi nghiệp vụ yêu cầu độ mới:

- Gắn thời điểm quan sát (`observedAt`), mã phiên bản hoặc sequence number vào dữ liệu.
- Kiểm tra độ trễ và khoảng cách thời gian giữa các nguồn trước khi phát một snapshot được coi là hợp lệ.
- Xác định chính sách cho nguồn im lặng, ngắt kết nối, hoặc không phát initial state.
- Nếu muốn cảnh báo khi dữ liệu tự trở nên stale chỉ vì thời gian trôi qua, cần **timer/heartbeat hoặc timeout**: `combineLatest` không tự chạy lại combinator khi đồng hồ thay đổi.

## 3. Phân biệt combineLatest, zip và merge

Ba operator đều xử lý nhiều publisher nhưng giải những bài toán khác nhau.

| Operator | Quy tắc chính | Khi nào thích hợp |
|---|---|---|
| **`Flux.combineLatest`** | Khi đã có ít nhất một item từ mỗi nguồn, phát tổ hợp mới mỗi khi một nguồn có item mới | Dashboard, trạng thái cập nhật độc lập, form có nhiều trường |
| **`Flux.zip`** | Ghép phần tử theo **vị trí**: item thứ 1 của A với item thứ 1 của B, item thứ 2 với item thứ 2... | Ghép hai chuỗi kết quả tương ứng theo thứ tự |
| **`Flux.merge`** | Đẩy từng item của các nguồn vào chung một luồng khi chúng tới, không kết hợp các giá trị thành tuple | Hợp nhất event đồng dạng từ nhiều nguồn |

Giả sử A phát `A1, A2, A3` và B phát `B1, B2`:

```text
zip:
  (A1, B1), (A2, B2)
  Không có B3 để ghép A3; theo điều kiện hoàn tất, không phát thêm cặp.

combineLatest (nếu sự kiện lần lượt A1, A2, B1, A3, B2):
  (A2, B1), (A3, B1), (A3, B2)

merge (cùng một thứ tự sự kiện):
  A1, A2, B1, A3, B2
```

`zip` cần dữ liệu tương ứng từng vị trí; `combineLatest` có thể **dùng lại cùng một giá trị** của B nhiều lần khi A thay đổi. `merge` không xây dựng snapshot có đủ trường từ hai nguồn; muốn biết event từ nguồn nào, hãy gắn nhãn/tag vào item trước khi merge.

**Không thể thay `combineLatest` bằng `zip`** trong một màn hình giá và tỷ giá cập nhật không cùng tốc độ: nếu giá mới xuất hiện nhưng tỷ giá chưa có bản cập nhật mới, `zip` có thể tiếp tục đợi, còn `combineLatest` có thể cập nhật màn hình bằng tỷ giá đã biết.

## 4. Các overload thường gặp của Flux.combineLatest

Project Reactor cung cấp nhiều overload. Ví dụ với **hai nguồn khác kiểu**:

```java
Flux<Integer> prices = ...;
Flux<String> currencies = ...;

Flux<String> display = Flux.combineLatest(
        prices,
        currencies,
        (price, currency) -> price + " " + currency
);
```

**Snippet** này cần các biến `prices`, `currencies` là publisher thực tế. Lambda hai tham số nhận giá trị đúng kiểu `Integer` và `String`, trả một `String` không null.

Với **ba nguồn khác kiểu**, có thể dùng overload với `Function<Object[], R>`:

```java
Flux<Integer> prices = ...;
Flux<String> currencies = ...;
Flux<Boolean> available = ...;

Flux<String> display = Flux.combineLatest(
        prices,
        currencies,
        available,
        values -> {
            Integer price = (Integer) values[0];
            String currency = (String) values[1];
            Boolean inStock = (Boolean) values[2];

            return price + " " + currency +
                    (inStock ? " | còn hàng" : " | hết hàng");
        }
);
```

Đây cũng là snippet; chưa có nguồn dữ liệu hoàn chỉnh. Vị trí trong `Object[]` tương ứng **thứ tự publisher truyền vào**. Cast đúng kiểu, kiểm tra index và giữ hàm kết hợp ngắn gọn. Với dữ liệu nghiệp vụ, nên trả `record`/DTO có trường rõ nghĩa thay vì ghép chuỗi.

Một overload tổng quát:

```java
Flux<Result> combined = Flux.combineLatest(
        listOfPublishers,
        values -> transform(values)
);
```

Ở đây `listOfPublishers` và `transform` là thành phần giả định; cách dùng thật còn phụ thuộc kiểu generic. Các overload cho `Iterable` hoặc varargs hỗ trợ tùy chỉnh `prefetch`. `prefetch` là **nhu cầu yêu cầu trước từ từng upstream**, không phải số bản ghi business phải giữ hoặc cam kết mọi event được hiển thị.

Không truyền `null` làm kết quả combinator. Trong Reactor, phần tử `onNext` không được là null; nếu hàm kết hợp trả null hoặc ném ngoại lệ, luồng kết quả có thể kết thúc bằng `onError`.

## 5. Ví dụ Java 17+ có thể chạy: cập nhật bằng Sinks.Many

Để thấy đúng thứ tự phát mà không dựa vào `Thread.sleep` hay lịch chạy scheduler, ví dụ dùng **Sinks** tạo hai nguồn event thủ công. Các lệnh `tryEmitNext` chạy tuần tự trên main thread, không có race giữa các nguồn trong demo.

Cấu trúc thư mục:

```text
combine-latest-demo/
├── pom.xml
└── src/main/java/demo/CombineLatestDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>combine-latest-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/CombineLatestDemo.java`:

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

public class CombineLatestDemo {

    private static <T> void emit(Sinks.Many<T> sink, T item) {
        Sinks.EmitResult result = sink.tryEmitNext(item);
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("Emission failed: " + result);
        }
    }

    private static void complete(Sinks.Many<?> sink) {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("Completion failed: " + result);
        }
    }

    public static void main(String[] args) {
        Sinks.Many<Integer> prices =
                Sinks.many().multicast().directBestEffort();

        Sinks.Many<String> currencies =
                Sinks.many().multicast().directBestEffort();

        Flux<String> snapshots = Flux.combineLatest(
                prices.asFlux(),
                currencies.asFlux(),
                (price, currency) -> price + " " + currency
        );

        snapshots.subscribe(
                value -> System.out.println("snapshot=" + value),
                error -> System.out.println("error=" + error.getMessage()),
                () -> System.out.println("complete")
        );

        System.out.println("price=100");
        emit(prices, 100);

        System.out.println("price=120");
        emit(prices, 120);

        System.out.println("currency=USD");
        emit(currencies, "USD");

        System.out.println("price=130");
        emit(prices, 130);

        System.out.println("currency=EUR");
        emit(currencies, "EUR");

        System.out.println("currency complete");
        complete(currencies);

        System.out.println("price=140");
        emit(prices, 140);

        System.out.println("price complete");
        complete(prices);
    }
}
```

Cần JDK 17+ và Maven. Trong thư mục `combine-latest-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CombineLatestDemo
```

**Standard output dự kiến của chương trình** (không tính log của Maven):

```text
price=100
price=120
currency=USD
snapshot=120 USD
price=130
snapshot=130 USD
currency=EUR
snapshot=130 EUR
currency complete
price=140
snapshot=140 EUR
price complete
complete
```

Giải thích từng giai đoạn:

1. Hai `Sinks.Many` là nguồn phát sự kiện chủ động. `asFlux()` cho phép Reactor dùng chúng như nguồn `Flux`.
2. `snapshots.subscribe(...)` đăng ký trước khi phát các sự kiện; overload `subscribe` có consumer `onNext`, `onError`, `onComplete`. Cách subscribe này mặc định yêu cầu dữ liệu không giới hạn, phù hợp demo nhỏ.
3. `price=100` và `price=120` chưa có snapshot vì `currencies` chưa phát bất kỳ item nào.
4. Khi currency = USD, giá gần nhất là 120, nên snapshot đầu tiên là `120 USD`.
5. Giá và currency thay đổi riêng rẽ; mỗi cập nhật tiếp theo kết hợp với giá trị mới nhất của nguồn còn lại.
6. Khi nguồn currency kết thúc sau EUR, tổ hợp **vẫn giữ EUR** để kết hợp với giá 140 từ nguồn giá.
7. Chỉ sau khi nguồn price cũng complete, luồng kết quả mới in `complete`.
8. Hàm `emit`/`complete` kiểm tra `Sinks.EmitResult` để tránh bỏ qua việc phát thất bại.

### Vì sao dùng directBestEffort trong ví dụ?

`Sinks.many().multicast().directBestEffort()` phát item tới những subscriber đang có demand; một subscriber chậm có thể bỏ lỡ item. Nó **không phát lại các item cũ cho subscriber đến muộn** và có thể trả lỗi khi không có subscriber/demand. Trong chương trình này chỉ có một subscriber đăng ký trước, yêu cầu không giới hạn và các nguồn phát tuần tự nên các lần `tryEmitNext` thành công.

Trong ứng dụng thật, lựa chọn sink phụ thuộc chính sách **mất dữ liệu, buffering, độ trễ, nhiều subscriber và reconnect**. Không dùng `directBestEffort` làm hàng đợi đảm bảo lưu vĩnh viễn mọi event nghiệp vụ.

**Ranh giới của ví dụ:** đây là chương trình Reactor Core đầy đủ, không cần Spring Boot. Giá và đơn vị được phát thủ công, minh họa đúng cơ chế `combineLatest`; không tự kết nối cơ sở dữ liệu hoặc feed thị trường.

## 6. combineLatest với nguồn cập nhật liên tục và nguồn cấu hình

Không phải mọi nguồn đều cần chạy vô hạn.

### 6.1. Một nguồn cấu hình phát một lần, một nguồn cập nhật nhiều lần

```java
Mono<String> currency = Mono.just("USD");
Flux<Integer> prices = Flux.just(100, 110, 120);

Flux<String> labels = Flux.combineLatest(
        currency,
        prices,
        (unit, price) -> price + " " + unit
);
```

Đây là snippet trong project có Reactor Core. `currency` phát một giá trị và complete. Giá trị "USD" vẫn dùng được để kết hợp các giá tiếp theo từ `prices` cho tới khi `prices` hoàn tất. Vì các nguồn ví dụ chạy đồng bộ khi subscribe, **đừng dựa vào một thứ tự event cụ thể chỉ từ đoạn khai báo này**; kết quả cuối cùng và cách subscribe chịu ảnh hưởng thời điểm phát thực tế. Với yêu cầu thứ tự kiểm thử chính xác, dùng nguồn điều khiển được như `Sinks` trong mục 5.

Nếu cấu hình thay đổi liên tục, nó nên là `Flux<ConfigUpdate>` để kết quả được tạo lại khi cấu hình có phiên bản mới.

### 6.2. Seed giá trị ban đầu cho nguồn chưa có event

`combineLatest` **chưa thể phát khi thiếu giá trị đầu tiên của bất kỳ nguồn nào**. Nếu UI cần hiện ngay, có thể seed giá trị nghiệp vụ có thật:

```java
Flux<String> currencyUpdates = ...;

Flux<String> currencyWithInitial =
        currencyUpdates.startWith("USD");
```

Đây là snippet. `startWith("USD")` cấp giá trị đầu trước khi stream các thay đổi; nó không tự xác minh "USD" còn đúng tại thời điểm kết nối. Chỉ seed giá trị **đã biết và được chấp nhận** theo nghiệp vụ. Nếu không có trạng thái ban đầu đáng tin cậy, xử lý loading/unknown và timeout thay vì bịa ra giá trị để tạo snapshot.

Một lựa chọn khác là nguồn hot `Sinks.many().replay().latest()` để subscriber mới có thể nhận **phần tử gần nhất mà sink lưu lại**. Nhưng replay không thay thế persistence, snapshot nhất quán hoặc kiểm soát độ mới; khi tiến trình restart, trạng thái trong bộ nhớ không tự sống sót.

### 6.3. Kết hợp hai luồng update của cùng một đối tượng

```java
record PriceUpdate(String sku, long amount, long version) { }
record StockUpdate(String sku, int quantity, long version) { }
record ProductView(String sku, long amount, int quantity) { }

Flux<PriceUpdate> priceUpdates = ...;
Flux<StockUpdate> stockUpdates = ...;

Flux<ProductView> views = Flux.combineLatest(
        priceUpdates,
        stockUpdates,
        (price, stock) -> new ProductView(
                price.sku(), price.amount(), stock.quantity())
);
```

**Snippets minh họa:** các nguồn `priceUpdates`/`stockUpdates` phải được khai báo trong code thực; `record` yêu cầu Java 16+.

Điều kiện ngầm ở đây: **hai nguồn phải nói về cùng một SKU**. Nếu một source phát giá SKU-A còn source kia phát tồn kho SKU-B, `combineLatest` **không tự join theo khóa**, và code trên sẽ tạo dữ liệu sai. Với nhiều key, cần phân vùng/join theo key phù hợp hoặc giữ snapshot map theo key rồi phát model đã kiểm tra tính nhất quán.

## 7. Vòng đời: nguồn chưa có item, đã complete, lỗi hoặc không bao giờ phát

### Trường hợp A: mọi nguồn đã có item

Khi tất cả đã phát lần đầu, `combineLatest` có thể phát tổ hợp. Mỗi `onNext` tiếp theo của một nguồn có thể kích hoạt thêm snapshot. Một phần tử từ A có thể được dùng trong **nhiều snapshot** cùng phần tử B, C khác nhau.

### Trường hợp B: một nguồn complete mà chưa phát item nào

Nếu một nguồn `Flux.empty()` (hoặc `Mono.empty()`) hoàn tất **trước khi phát item**, tổ hợp không thể tạo một bộ dữ liệu đầy đủ. Luồng kết hợp có thể hoàn tất rỗng; không tự sinh một giá trị mặc định hay `null` cho nguồn đó.

```java
Flux<String> combined = Flux.combineLatest(
        Flux.<Integer>empty(),
        Flux.just("USD"),
        (price, currency) -> price + " " + currency
);
// Không có tổ hợp hợp lệ từ nguồn giá rỗng.
```

Đây là snippet. Nếu empty thực sự mang nghĩa “không có giá”, cần quyết định rõ trả màn hình loading, thông báo không có dữ liệu, hoặc áp dụng fallback hợp lệ từ dữ liệu nghiệp vụ.

### Trường hợp C: một nguồn đã phát rồi complete

Nguồn đã complete nhưng từng phát item vẫn để lại giá trị mới nhất để những nguồn khác sử dụng. Luồng combined hoàn tất khi các nguồn cần thiết đều hoàn tất, hoặc bị kết thúc sớm bởi lỗi/cancellation tương ứng.

Không nên đánh đồng `onComplete` của **một** source với `onComplete` của toàn bộ combined Flux.

### Trường hợp D: một nguồn không bao giờ phát item đầu tiên

Một nguồn kiểu `Flux.never()` không phát `onNext` hay terminal signal. Nếu không có lỗi hoặc nhánh kết thúc khác, `combineLatest` có thể chờ mãi vì **không đủ giá trị đầu tiên**.

Đối với HTTP hoặc dashboard, hãy định nghĩa chiến lược khi thiếu dữ liệu: deadline, timeout, trạng thái loading, fallback xác thực, health check hoặc thông báo sự cố. Đừng cho rằng subscription sẽ tự hoàn tất.

### Trường hợp E: một nguồn phát lỗi

Một `onError` chưa được xử lý của bất kỳ nguồn nào thường làm kết quả `combineLatest` **kết thúc bằng lỗi và hủy các nguồn còn lại**. Không tự bỏ qua lỗi rồi tiếp tục hiển thị giá trị như thể dữ liệu mới vẫn đáng tin.

```java
Flux<String> source = remoteUpdates()
        .onErrorResume(error -> fallbackUpdates(error));
```

Đây là snippet với hai hàm giả định trả `Flux<String>`. Cách xử lý cụ thể tùy loại lỗi: có thể retry có giới hạn với backoff, chuyển sang nguồn dự phòng đáng tin, hoặc báo trạng thái unhealthy. Không mặc định dùng `onErrorComplete()` vì nó có thể biến sự cố thành một source complete và khiến tổ hợp giữ **giá trị cũ** không còn hợp lệ.

### Trường hợp F: downstream hủy

Khi subscriber hủy (ví dụ người dùng đóng SSE hoặc ứng dụng hủy subscription), subscription tới các nguồn có thể bị hủy. Việc hủy không bảo đảm side effect bên ngoài đã bắt đầu được hoàn tác. Với `Sinks` dùng chung, việc một subscriber hủy không đồng nghĩa sink toàn cục bị hủy đối với mọi subscriber khác.

## 8. Thực tế Spring WebFlux: cập nhật liên tục cho SSE

Spring WebFlux có thể trả `Flux<DTO>` qua một endpoint để stream dữ liệu theo thời gian. Với Server-Sent Events (SSE), trình duyệt hoặc client có thể giữ kết nối và nhận các snapshot mới.

Ví dụ sau là **một controller hợp lệ** cho ứng dụng Spring Boot đã có `spring-boot-starter-webflux`. Hai nguồn dùng `Flux.interval` để mô phỏng nhịp cập nhật khác nhau, không kết nối feed thật:

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class LiveDashboardController {

    @GetMapping(path = "/dashboard/live",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<DashboardSnapshot> live() {
        Flux<Long> fastTicks = Flux.interval(Duration.ofSeconds(1));
        Flux<Long> slowTicks = Flux.interval(Duration.ofSeconds(3));

        return Flux.combineLatest(
                fastTicks,
                slowTicks,
                DashboardSnapshot::new
        );
    }

    public record DashboardSnapshot(long fastTick, long slowTick) { }
}
```

Luồng xử lý khi client kết nối:

1. WebFlux subscribe vào publisher được trả về.
2. Timer nhanh phát một phần tử mỗi khoảng một giây; timer chậm mỗi ba giây.
3. **Chưa có snapshot** cho đến khi cả hai timer phát giá trị đầu tiên.
4. Sau đó mỗi tick từ nguồn nào cũng kết hợp với giá trị tick gần nhất của nguồn còn lại.
5. WebFlux mã hóa các `DashboardSnapshot` và gửi qua kết nối SSE. Khi client đóng kết nối, subscription thường bị hủy.

Không cam kết timestamp, số lượng sự kiện đúng từng giây hoặc thứ tự cụ thể khi timer trùng thời điểm: scheduler và tình trạng hệ thống ảnh hưởng thời điểm quan sát. `Flux.interval` cũng có chính sách khi downstream không đủ demand; đừng xem nó là nguồn tick không bao giờ mất dữ liệu.

**Đây không phải ứng dụng độc lập:** cần Spring Boot main class, server, dependency và môi trường chạy. Khi dùng nguồn thật, thay `fastTicks`/`slowTicks` bằng những `Flux` nhận sự kiện giá, tồn kho, cảnh báo... và kiểm soát trạng thái đầu tiên, key, lỗi, reconnect, giới hạn kết nối và tài nguyên.

### Kiến trúc tổng quát

```text
price events ─────┐
                  ├── combineLatest ── map -> DashboardSnapshot ── SSE client
stock events ─────┘                        │
                                          └── distinctUntilChanged (nếu phù hợp)
```

Nếu các phần tử mới **không làm thay đổi giá trị hiển thị**, `distinctUntilChanged()` trên DTO có `equals` phù hợp có thể bỏ snapshot trùng liên tiếp. Nhưng nếu mỗi event phải được audit hay đếm chính xác, **đừng dùng distinct**: hai event trùng giá trị có thể vẫn là hai sự kiện khác nhau về mặt nghiệp vụ.

### Nguồn hot và nguồn cold trong WebFlux

- **Cold source:** mỗi subscription có thể khởi động công việc hoặc bộ timer riêng. Trong ví dụ `Flux.interval`, mỗi client tạo subscription với nhịp của riêng mình.
- **Hot shared source:** nhiều client có thể cùng nhận các event đã được đẩy từ hệ thống qua sink/message broker. Subscriber đến muộn có thể **không thấy các event trước đó** nếu nguồn không replay.
- **combineLatest state riêng theo subscription:** mỗi subscriber giữ diễn biến latest mà subscriber đó thực sự quan sát. Hai client kết nối lệch thời gian có thể khác nhau cho đến khi nhận đủ initial data.

Với dashboard production, nên xác định rõ **cách client mới nhận snapshot đầu tiên**: fetch snapshot hiện tại, replay item mới nhất, hoặc dùng endpoint snapshot + stream delta với chiến lược tránh race giữa snapshot và subscription.

## 9. Độ mới, tính nhất quán và sự kiện đến muộn

Một nhầm lẫn lớn là coi snapshot `combineLatest` là một phép đọc transaction đồng nhất của mọi hệ thống. Thực tế, nó ghép **giá trị mới nhất đã quan sát** từ từng nguồn; các nguồn có thể dùng clock khác nhau, chậm mạng khác nhau và cập nhật theo transaction khác nhau.

Ví dụ:

```text
Price: version=12, observedAt=10:02:05, amount=100
Stock: version= 8, observedAt=10:01:20, quantity=3

combineLatest -> Price v12 + Stock v8
```

Snapshot ở trên hợp lệ theo **ngữ nghĩa latest-observed** nhưng có thể không đủ nhất quán nếu nghiệp vụ yêu cầu cùng một transaction/version.

Các chiến lược:

1. **Gắn metadata:** mỗi item có `id`/key, `version`, `observedAt`, `source`. Không chỉ phát số trần nếu cần kiểm soát freshness.
2. **Kiểm tra trước khi hiển thị:** nếu `Duration.between(oldTime, Instant.now())` vượt ngưỡng, gắn nhãn stale hoặc từ chối dùng dữ liệu cũ.
3. **Chống cập nhật đến trễ:** một event được nhận sau chưa chắc có phiên bản nghiệp vụ mới hơn; cần lọc theo sequence/version tại từng source nếu yêu cầu latest **theo version**, không chỉ latest **theo arrival**.
4. **Nếu cần nhất quán transaction:** yêu cầu API/snapshot có version đồng bộ, event time window, correlation ID hoặc cơ chế giao dịch tương ứng; `combineLatest` một mình không thực hiện join theo khóa, window hay transaction.
5. **Kiểm soát nhịp UI:** có thể lấy mẫu/giảm tần suất snapshot khi quá nhiều cập nhật, nhưng hiểu rằng làm thế có thể bỏ qua trạng thái trung gian.

Một DTO minh họa:

```java
import java.time.Instant;

record PriceEvent(String sku, long price, long version, Instant observedAt) { }
record StockEvent(String sku, int quantity, long version, Instant observedAt) { }
record ViewState(String sku, long price, int quantity,
                 Instant priceSeenAt, Instant stockSeenAt) { }

// Các nguồn cần cùng SKU, và event đã được lọc phiên bản nghiệp vụ.
Flux<ViewState> states = Flux.combineLatest(
        priceUpdates,
        stockUpdates,
        (price, stock) -> new ViewState(
                price.sku(),
                price.price(),
                stock.quantity(),
                price.observedAt(),
                stock.observedAt()
        )
);
```

Đây là snippet; `priceUpdates`, `stockUpdates` cần khai báo `Flux<PriceEvent>`/`Flux<StockEvent>` trong ứng dụng. Nó minh họa dữ liệu cần giữ để kiểm tra consistency; **chưa tự kiểm tra cùng SKU hay độ mới**.

## 10. Backpressure, prefetch và tốc độ cập nhật

`combineLatest` giữ trạng thái latest, nhưng **không có nghĩa “không bao giờ có hàng đợi” hoặc “mọi sự kiện đều được lưu”**.

- Upstream có thể phát nhanh hơn downstream xử lý; Reactor phải phối hợp request/prefetch và bộ đệm nội bộ theo phiên bản/overload/operator.
- Overload có `prefetch` giúp điều khiển lượng request trước từ **mỗi nguồn**, không phải bảo đảm giới hạn tuyệt đối lượng dữ liệu trong toàn hệ thống.
- Một nguồn hot `Sinks` có chính sách riêng: buffer, drop, replay hoặc fail khi thiếu demand. Chọn sai sink có thể khiến những cập nhật UI bị mất trước khi tới `combineLatest`.
- Hàm combinator chạy với mỗi cơ hội tạo snapshot; nếu tính toán nặng, mã hóa lớn hoặc đụng I/O blocking, nó có thể làm nghẽn pipeline.
- Tần suất update của source nhanh có thể quyết định phần lớn số lần tái tính, dù các source còn lại ít thay đổi.
- Reactor mô tả `combineLatest` là **không phù hợp nếu bạn cần đảm bảo discard/unpropagated-element cleanup chính xác**, vì cùng một item có thể được dùng nhiều lần trong các tổ hợp. Không dùng operator này như một cơ chế lưu trữ đầy đủ mọi event có yêu cầu audit.

Ví dụ giảm các cập nhật quá dày trước khi gửi UI:

```java
Flux<DashboardSnapshot> throttledForDisplay = combinedSnapshots
        .sample(java.time.Duration.ofMillis(250))
        .distinctUntilChanged();
```

Đây là snippet. `sample` chỉ lấy phần tử gần nhất theo nhịp thời gian nhất định; **có chủ đích không bảo toàn toàn bộ thay đổi trung gian**. Phù hợp dashboard có thể chấp nhận cập nhật dạng trạng thái, không phù hợp ledger, thanh toán hay event audit. Nên đo latency và tải thực tế trước khi chọn chu kỳ lấy mẫu.

Nếu downstream cần **mỗi event riêng lẻ**, thiết kế event stream lưu trữ và xử lý tuần tự, chứ không kỳ vọng `combineLatest` trả lại lịch sử tất cả event đã bị gộp.

## 11. Lỗi khi dùng combineLatest trong ứng dụng

### Lỗi 1 — Nghĩ có snapshot ngay khi một nguồn phát đầu tiên

```java
Flux<String> result = Flux.combineLatest(
        priceFlux,
        currencyFlux,
        (price, currency) -> price + " " + currency
);
```

Đây là snippet; nếu `priceFlux` phát mà `currencyFlux` chưa có item, chưa có kết quả. **Cách xử lý:** chuẩn bị initial value đáng tin, hoặc thể hiện loading/unknown và timeout.

### Lỗi 2 — Dùng zip cho dashboard cần dữ liệu latest

`Flux.zip(priceFlux, currencyFlux, ...)` chờ cặp item theo vị trí. Nếu currency im lặng, các price mới không tạo snapshot. **Cách xử lý:** dùng `combineLatest` cho trạng thái mới nhất độc lập; dùng `zip` khi quan hệ theo vị trí là chủ đích.

### Lỗi 3 — Nhầm “latest” với bản mới nhất theo version nghiệp vụ

Một event version 7 tới **sau** version 8 có thể ghi đè latest-observed thành version 7 nếu không có bộ lọc. **Cách xử lý:** xác minh version và thứ tự nghiệp vụ ở từng nguồn.

### Lỗi 4 — Ghép nhầm khóa

`combineLatest` không biết SKU hay user ID. Nó có thể kết hợp giá của SKU-A với số tồn kho SKU-B nếu bạn đưa vào hai stream toàn cục. **Cách xử lý:** định tuyến/partition theo key trước khi kết hợp.

### Lỗi 5 — Chờ vô hạn vì một nguồn không có giá trị đầu tiên

Nếu source B kết nối chậm hoặc không phát dữ liệu, A có thể cập nhật mãi mà không có snapshot. **Cách xử lý:** seed hợp lệ, timeout, báo trạng thái hoặc thay đổi hợp đồng upstream.

### Lỗi 6 — Biến lỗi hạ tầng thành complete rồi giữ dữ liệu cũ

Dùng `onErrorComplete` một cách vô thức có thể khiến tổ hợp tiếp tục hiện tỷ giá cũ như thể còn hợp lệ. **Cách xử lý:** thiết kế trạng thái lỗi, stale, retry/backoff hoặc fail rõ ràng.

### Lỗi 7 — Combinator có side effect nặng

Không gọi gửi email, ghi DB, sleep hoặc truy vấn I/O đồng bộ trong combinator nếu mỗi thay đổi nhỏ có thể kích hoạt tính lại. **Cách xử lý:** biến combinator thành phép tính thuần để dựng DTO; tách side effect thành pipeline được quản lý và giới hạn.

### Lỗi 8 — Dùng mutable object làm latest

Nếu publisher phát một đối tượng rồi code khác **thay đổi trực tiếp object đó** mà không phát `onNext`, `combineLatest` không tự biết dữ liệu thay đổi và không có tín hiệu mới. **Cách xử lý:** sử dụng item bất biến (ví dụ `record`) và phát item mới khi trạng thái thay đổi.

### Lỗi 9 — Nghĩ các client SSE cùng thấy một initial snapshot

Nguồn hot `multicast` không replay mặc định; client đến muộn có thể chưa có bất kỳ giá trị nào của một source. **Cách xử lý:** cấp snapshot ban đầu/replay state thích hợp và định nghĩa reconnect.

### Lỗi 10 — Mong một snapshot có tính nhất quán giao dịch

Giá v12 và kho v8 có thể được ghép với nhau. **Cách xử lý:** version/correlation ID, snapshot từ cùng transaction hoặc join có window phù hợp.

### Lỗi 11 — Nghĩ combineLatest luôn chạy bất đồng bộ

Nếu upstream phát đồng bộ thì combinator có thể chạy đồng bộ trong subscription/request path. Chỉ việc dùng `Flux` không tạo thread mới. **Cách xử lý:** hiểu scheduler và tránh blocking trên event-loop; đo đạc khi cần đổi execution context.

### Lỗi 12 — Giả định mọi event trung gian được bảo toàn

Nguồn hot có thể drop dưới áp lực backpressure; việc kết hợp latest cố ý ưu tiên trạng thái cập nhật, không phải ghép đủ mọi event như `zip`. **Cách xử lý:** thiết kế event log khi cần completeness, và phân biệt dữ liệu sự kiện với dữ liệu trạng thái.

## 12. Kiểm tra logic bằng tình huống

**Câu 1:** Nguồn A đã phát 10, 20; B chưa phát gì. Có bao nhiêu snapshot?

→ **0**. Chưa có giá trị đầu tiên từ B.

**Câu 2:** B phát "X". Snapshot nào được tạo đầu tiên?

→ **(20, "X")**, vì 20 là giá trị mới nhất của A.

**Câu 3:** B hoàn tất sau khi phát "X", A phát 30. Có snapshot mới không?

→ **Có**, kết hợp `(30, "X")` nếu subscription vẫn hoạt động. Completion của B không xóa giá trị mới nhất đã có.

**Câu 4:** B hoàn tất rỗng trước khi phát giá trị nào?

→ Không thể tạo bộ giá trị đầy đủ; kết quả có thể hoàn tất mà không phát item.

**Câu 5:** A là bảng giá nhiều SKU, B là tồn kho nhiều SKU. Có thể dùng một `combineLatest(A,B,...)` để ghép đúng từng SKU không?

→ **Không tự động**. Cần bảo đảm hai luồng đã cùng key hoặc thực hiện phân vùng/join theo key.

**Câu 6:** Chỉ thay đổi thời gian hệ thống từ 10:00 sang 10:05, không source nào phát. Combinator có tự chạy lại để đánh dấu stale không?

→ **Không**. Phải có event, timer, timeout hoặc cơ chế kiểm tra freshness bên ngoài.

**Câu 7:** Nguồn A phát 100 lần, B phát một lần. Có nhất thiết 100 tổ hợp đúng kiểu ghép cặp 1–1 không?

→ **Không**. Sau khi B có item đầu, những update A tiếp theo có thể được kết hợp với **cùng** B mới nhất. Số snapshot thực tế còn phụ thuộc thời điểm A/B phát và nhu cầu downstream.

**Câu 8:** Cần lưu toàn bộ giao dịch để kiểm toán. Có nên chỉ giữ output của `combineLatest` không?

→ **Không**. Output là chuỗi snapshot tổng hợp, có thể không chứa mỗi sự kiện đầu vào đúng một lần. Lưu event gốc bằng cơ chế đáng tin cậy theo yêu cầu nghiệp vụ.

## 13. Checklist triển khai dashboard reactive

Khi chuẩn bị dùng `Flux.combineLatest`, hãy tự trả lời:

1. Mỗi nguồn mang **trạng thái** hay **sự kiện**? Nghiệp vụ có thực sự cần latest-observed snapshot?
2. Những nguồn đó có cùng **khóa** không? Có cần partition theo user, product, tenant hoặc entity?
3. Client mới lấy **giá trị đầu tiên** ở đâu? Nguồn có replay hay phải gọi snapshot API?
4. Dữ liệu có thể **stale** không? Đã có timestamp/version/timeout?
5. Nếu một nguồn hoàn tất rỗng, ngắt kết nối hoặc lỗi, UI hiển thị gì?
6. Lựa chọn sink/prefetch/backpressure có phù hợp tốc độ producer và consumer không?
7. Combinator có thuần, nhanh và không blocking I/O không?
8. Có cần bỏ snapshot trùng `distinctUntilChanged` hoặc giảm tốc `sample`, và có chấp nhận bỏ trạng thái trung gian không?
9. Nhiều subscriber có làm phát sinh nhiều kết nối/timer/công việc lặp lại không?
10. Test đã bao gồm **trước initial**, **sau initial**, **nguồn complete**, **empty**, **error**, **late subscriber**, **cancel**, **source nhanh/chậm** chưa?

**Ghi nhớ:** `Flux.combineLatest` dành cho **ảnh chụp kết hợp từ giá trị mới nhất đã nhận ở mỗi nguồn**. Nó chờ **một item đầu tiên từ từng nguồn**, rồi tính lại khi bất kỳ nguồn nào có cập nhật mới. Nó phù hợp dữ liệu cập nhật liên tục như dashboard và trạng thái UI; không tự giải quyết đồng bộ timestamp, join theo khóa, đảm bảo nhận đủ sự kiện hay tính nhất quán giao dịch.

## Tài liệu tham khảo

- Project Reactor — [Flux.combineLatest và các overload (API)](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Which operator do I need? Ghép theo zip hoặc combineLatest](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html).
- Project Reactor — [Sinks: multicast, backpressure, replay](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- Project Reactor — [Backpressure và cách operator thay đổi request](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [WebFlux reactive stack](https://docs.spring.io/spring-framework/reference/web/webflux.html).
