# Lắp ghép decorator và danh sách chiến lược với thứ tự rõ ràng

Trong **Dependency Injection (DI)**, việc truyền dependency qua constructor giúp tách nơi sử dụng khỏi nơi tạo đối tượng. Tuy nhiên, khi một use case có **nhiều chiến lược (strategies)** và cần **bọc thêm hành vi bằng decorator**, câu hỏi quan trọng không chỉ là “inject interface nào?” mà còn là:

- Các chiến lược được xét theo **thứ tự nào**?
- Có **chọn chiến lược đầu tiên phù hợp**, hay chạy **tất cả chiến lược**?
- Decorator nằm **bên ngoài hay bên trong** lớp khác?
- Ai quyết định thứ tự và làm sao kiểm thử được nó?
- Việc lắp ghép có giữ nguyên ý nghĩa khi chuyển từ **Java thuần** sang **DI container** không?

Bài thực hành này tập trung vào **lắp ghép có thứ tự và quan sát được**. Ta sẽ dùng Java 17, constructor injection và một **composition root** để tạo một chuỗi decorator bao quanh một bộ lựa chọn chiến lược theo thứ tự. Sau đó viết kiểm thử bằng fake, cố ý đổi thứ tự để thấy thay đổi, và phân tích những đánh đổi về scope, tính quyết định và vòng đời.

> **Mục tiêu:** không dùng thứ tự ngẫu nhiên của việc quét class, đăng ký bean hay duyệt map để quyết định nghiệp vụ. Thứ tự phải nằm trong một cấu hình hoặc cấu trúc rõ ràng, được kiểm tra và có test bảo vệ.

## 1. Phân biệt hai loại thứ tự

Ta có một hệ thống báo giá vận chuyển. Có ba chính sách:

1. **EXPRESS:** dùng cho đơn yêu cầu giao nhanh.
2. **REMOTE:** dùng cho đơn ở vùng xa khi không có quy tắc ưu tiên cao hơn.
3. **STANDARD:** quy tắc mặc định cho mọi đơn còn lại.

Một đơn vừa ở vùng xa vừa yêu cầu giao nhanh **khớp cả EXPRESS và REMOTE**. Nếu chọn *chiến lược đầu tiên phù hợp* (*first match wins*), thứ tự là **quy tắc nghiệp vụ**:

```text
Danh sách chiến lược, từ ưu tiên cao tới thấp:

  [0] EXPRESS  ─ supports(express == true)
  [1] REMOTE   ─ supports(zone == REMOTE)
  [2] STANDARD ─ supports(any shipment)

             Shipment
                │
                ▼
         EXPRESS supports?
             │     │
           có│     └─không─► REMOTE supports?
             ▼                     │       │
       tính giá EXPRESS           có       └─không─► STANDARD
                                   ▼                  │
                              tính giá REMOTE         ▼
                                                   tính giá
                                                   STANDARD
```

Tại đây, **STANDARD là catch-all và phải ở cuối**. Nếu đặt nó ở đầu, mọi đơn sẽ dùng STANDARD; hai chiến lược phía sau trở thành mã chết.

Loại thứ tự thứ hai nằm trong **chuỗi decorator**. Giả sử muốn cộng một khoản phí xử lý cố định 2.000 VND và ghi log số tiền khách thực sự thấy.

```text
Trace(HandlingFee(FirstMatchEngine(strategies)))
  │          │
  │          └── cộng 2.000 VND vào báo giá
  └── ghi lại số tiền đã gồm phí xử lý
```

Nếu đổi thành `HandlingFee(Trace(FirstMatchEngine(...)))`, **tổng tiền trả về vẫn có thể giống nhau** nhưng log của decorator Trace **chưa bao gồm phí xử lý**. Đây là thay đổi hành vi quan sát được.

| Loại thứ tự | Quyết định | Hệ quả nếu đổi |
|---|---|---|
| Danh sách strategies | Quy tắc nào được thử trước? | Có thể chọn implementation khác và tính giá khác |
| Decorator nesting | Hành vi bọc diễn ra ở lớp nào? | Log, metrics, retry, validation và kết quả có thể thay đổi |
| Thứ tự lifecycle | Consumer nào dừng trước dependency? | Có thể sử dụng resource đã đóng nếu shutdown sai |

Bài này chủ yếu luyện **hai loại đầu**; loại thứ ba được nhắc tới khi xét trách nhiệm của composition root.

## 2. Xác định contract trước khi lắp graph

Ta tách phần **chọn thuật toán** khỏi phần **bọc hành vi**.

Contract chiến lược:

```java
interface RateStrategy {
    String id();
    boolean supports(Shipment shipment);
    long calculate(Shipment shipment);
}
```

`supports(...)` quyết định chiến lược có áp dụng được không; `calculate(...)` trả phí theo chiến lược đã chọn. `id()` hỗ trợ log, test và kiểm tra không trùng đăng ký.

Contract của use case báo giá:

```java
interface QuoteService {
    Quote quote(Shipment shipment);
}
```

Bộ chọn chiến lược `FirstMatchQuoteService` **implements `QuoteService`**. Các decorator cũng **implements `QuoteService`**, nên có thể bọc một service bằng một service khác mà caller không phải đổi API.

```text
                  QuoteService
                       ▲
       ┌───────────────┼─────────────────┐
       │               │                 │
FirstMatchQuoteService │            TraceDecorator
                       │                 │
                 HandlingFeeDecorator ───┘
                       │            mỗi decorator
                       │            giữ delegate:
                       └──────────► QuoteService
```

Điểm cần hiểu: **Decorator dùng cùng contract với đối tượng được bọc**. Strategy lại là contract của một **thuật toán lựa chọn được**. Hai mẫu làm những việc khác nhau; cùng dùng constructor injection nhưng không thay thế cho nhau.

### Đặt bất biến của bài thực hành

| Bất biến | Quy tắc kiểm tra |
|---|---|
| Danh sách strategies có thứ tự | Tạo bằng `List.of(...)` theo ưu tiên cụ thể |
| Danh sách không rỗng | Constructor của bộ chọn từ chối danh sách rỗng |
| Mỗi chiến lược có ID riêng | Constructor từ chối ID rỗng/trùng |
| Chỉ một chiến lược được tính phí | Dừng ngay sau lần `supports(...)` đầu tiên trả `true` |
| Không có quy tắc phù hợp | Ném lỗi rõ, không tự chọn một implementation ngầm |
| Giá không âm | Contract `Quote` kiểm tra bất biến |
| Phí xử lý không âm | Constructor của decorator kiểm tra giá trị |
| Trace quan sát số tiền cuối | Trace được đặt **bên ngoài** HandlingFee |
| Dữ liệu request không ở singleton | `Shipment` được truyền theo lời gọi `quote(...)` |
| Composition root quyết định thứ tự | Không có gọi `new` hay registry lookup tùy ý trong business caller |

Đây là các tiêu chí chấp nhận có thể biến thành test, không chỉ là một sơ đồ đẹp.

## 3. Tại sao dùng `List` thay vì một tập hợp không có thứ tự?

Chữ ký constructor của bộ lựa chọn là:

```java
FirstMatchQuoteService(List<RateStrategy> strategies)
```

Ở đây `List` có vai trò **mang thứ tự ưu tiên**. Thứ tự là một phần của contract.

- `List.of(express, remote, standard)` biểu diễn rõ thứ tự và không thể thêm/xóa phần tử sau khi tạo.
- `List.copyOf(input)` lưu một snapshot để caller không thể thay đổi thứ tự phía sau lưng service.
- Không nên lấy danh sách có ý nghĩa ưu tiên từ một `HashSet` hoặc một `HashMap.values()` rồi giả định có thứ tự ổn định.
- `LinkedHashMap` có thứ tự chèn, nhưng nếu nghiệp vụ là *thử lần lượt*, `List` thường diễn đạt ý nghĩa rõ hơn; một map có thể phù hợp hơn khi **tra theo khóa chính xác** thay vì ưu tiên.
- Nếu cấu hình đến từ YAML/JSON/database, composition root phải **parse, sắp theo trường ưu tiên minh bạch, kiểm tra xung đột**, rồi mới tạo `List`.

Một DI container có thể inject collection các bean, nhưng **thứ tự mặc định không nên được xem là quy tắc nghiệp vụ**. Khi dùng cơ chế thứ tự của framework (priority/order/qualifier), cần biết phiên bản, hợp đồng sắp xếp và cách xử lý giá trị trùng; nên có kiểm thử composition chứng minh thứ tự cuối cùng.

## 4. Ví dụ Java 17 hoàn chỉnh

Ta sẽ xây một graph như sau:

```text
Composition root
   │
   ├── new ExpressRate()
   ├── new RemoteRate()
   ├── new StandardRate()
   │
   └── new FirstMatchQuoteService(
              List.of(express, remote, standard)
          )
                   │
                   ▼
          HandlingFeeDecorator(+2.000 VND)
                   │
                   ▼
             TraceDecorator(events)
                   │
                   ▼
              Caller / main
```

Để đọc đúng sơ đồ, các mũi tên phần decorator ở đây thể hiện **thứ tự lắp từ trong ra ngoài**: root tạo engine trước, bọc fee, rồi bọc trace. Khi thực thi, caller đi vào trace trước, sau đó fee, rồi engine.

Lưu **toàn bộ** đoạn mã sau thành `OrderedCompositionDemo.java`, chạy bằng JDK 17 trở lên.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class OrderedCompositionDemo {

    enum Zone {
        LOCAL, REMOTE
    }

    // Dữ liệu của từng yêu cầu: không giữ trong service dùng chung.
    record Shipment(
            String orderId, Zone zone,
            int weightKg, boolean express) {
        Shipment {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                    "orderId must not be blank");
            }
            Objects.requireNonNull(zone, "zone");
            if (weightKg <= 0) {
                throw new IllegalArgumentException(
                    "weightKg must be positive");
            }
        }
    }

    // Giữ tên chiến lược đã thắng để dễ kiểm tra lựa chọn.
    record Quote(String selectedStrategy, long amountVnd) {
        Quote {
            if (selectedStrategy == null
                    || selectedStrategy.isBlank()) {
                throw new IllegalArgumentException(
                    "selectedStrategy must not be blank");
            }
            if (amountVnd < 0) {
                throw new IllegalArgumentException(
                    "amountVnd must not be negative");
            }
        }
    }

    interface RateStrategy {
        String id();
        boolean supports(Shipment shipment);
        long calculate(Shipment shipment);
    }

    static final class ExpressRate implements RateStrategy {
        @Override
        public String id() {
            return "EXPRESS";
        }

        @Override
        public boolean supports(Shipment shipment) {
            return shipment.express();
        }

        @Override
        public long calculate(Shipment shipment) {
            return Math.addExact(
                30_000L,
                Math.multiplyExact(
                    shipment.weightKg(), 7_000L));
        }
    }

    static final class RemoteRate implements RateStrategy {
        @Override
        public String id() {
            return "REMOTE";
        }

        @Override
        public boolean supports(Shipment shipment) {
            return shipment.zone() == Zone.REMOTE;
        }

        @Override
        public long calculate(Shipment shipment) {
            return Math.addExact(
                20_000L,
                Math.multiplyExact(
                    shipment.weightKg(), 4_000L));
        }
    }

    static final class StandardRate implements RateStrategy {
        @Override
        public String id() {
            return "STANDARD";
        }

        @Override
        public boolean supports(Shipment shipment) {
            return true; // catch-all: composition root phải đặt cuối.
        }

        @Override
        public long calculate(Shipment shipment) {
            return Math.addExact(
                10_000L,
                Math.multiplyExact(
                    shipment.weightKg(), 2_000L));
        }
    }

    interface QuoteService {
        Quote quote(Shipment shipment);
    }

    // Chọn đúng chiến lược đầu tiên phù hợp, không chạy tất cả.
    static final class FirstMatchQuoteService implements QuoteService {
        private final List<RateStrategy> strategies;

        FirstMatchQuoteService(List<RateStrategy> strategies) {
            Objects.requireNonNull(strategies, "strategies");
            if (strategies.isEmpty()) {
                throw new IllegalArgumentException(
                    "At least one strategy is required");
            }

            // Snapshot bất biến để caller không thay đổi thứ tự.
            this.strategies = List.copyOf(strategies);

            Set<String> ids = new HashSet<>();
            for (RateStrategy strategy : this.strategies) {
                String id = strategy.id();
                if (id == null || id.isBlank()) {
                    throw new IllegalArgumentException(
                        "Strategy id must not be blank");
                }
                if (!ids.add(id)) {
                    throw new IllegalArgumentException(
                        "Duplicate strategy id: " + id);
                }
            }
        }

        @Override
        public Quote quote(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");

            for (RateStrategy strategy : strategies) {
                if (strategy.supports(shipment)) {
                    long amount = strategy.calculate(shipment);
                    return new Quote(strategy.id(), amount);
                }
            }

            throw new IllegalStateException(
                "No rate strategy matches " + shipment.orderId());
        }
    }

    // Decorator 1: bổ sung phí xử lý cố định.
    static final class HandlingFeeDecorator implements QuoteService {
        private final QuoteService delegate;
        private final long feeVnd;

        HandlingFeeDecorator(QuoteService delegate, long feeVnd) {
            this.delegate = Objects.requireNonNull(
                delegate, "delegate");
            if (feeVnd < 0) {
                throw new IllegalArgumentException(
                    "feeVnd must not be negative");
            }
            this.feeVnd = feeVnd;
        }

        @Override
        public Quote quote(Shipment shipment) {
            Quote base = delegate.quote(shipment);
            return new Quote(
                base.selectedStrategy(),
                Math.addExact(base.amountVnd(), feeVnd));
        }
    }

    // Decorator 2: ghi nhận đường đi, không thay đổi giá.
    static final class TraceDecorator implements QuoteService {
        private final QuoteService delegate;
        private final List<String> events;

        TraceDecorator(
                QuoteService delegate, List<String> events) {
            this.delegate = Objects.requireNonNull(
                delegate, "delegate");
            this.events = Objects.requireNonNull(
                events, "events");
        }

        @Override
        public Quote quote(Shipment shipment) {
            Objects.requireNonNull(shipment, "shipment");
            events.add("enter " + shipment.orderId());

            try {
                Quote result = delegate.quote(shipment);
                events.add("success "
                    + result.selectedStrategy() + " "
                    + result.amountVnd());
                return result;

            } catch (RuntimeException failure) {
                events.add(
                    "failure " + failure.getClass().getSimpleName());
                throw failure; // Không biến lỗi thành báo giá giả.
            }
        }
    }

    // Composition root: quyết định cả danh sách lẫn thứ tự bọc.
    static QuoteService compose(List<String> events) {
        List<RateStrategy> strategies = List.of(
            new ExpressRate(),
            new RemoteRate(),
            new StandardRate()
        );

        QuoteService firstMatch =
            new FirstMatchQuoteService(strategies);

        QuoteService withFee =
            new HandlingFeeDecorator(firstMatch, 2_000L);

        return new TraceDecorator(withFee, events);
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();
        QuoteService quotes = compose(events);

        System.out.println(quotes.quote(
            new Shipment("A", Zone.REMOTE, 2, true)));

        System.out.println(quotes.quote(
            new Shipment("B", Zone.REMOTE, 2, false)));

        System.out.println(quotes.quote(
            new Shipment("C", Zone.LOCAL, 2, false)));

        events.forEach(System.out::println);
    }
}
```

Biên dịch và chạy:

```bash
javac OrderedCompositionDemo.java
java OrderedCompositionDemo
```

Kết quả dự kiến:

```text
Quote[selectedStrategy=EXPRESS, amountVnd=46000]
Quote[selectedStrategy=REMOTE, amountVnd=30000]
Quote[selectedStrategy=STANDARD, amountVnd=16000]
enter A
success EXPRESS 46000
enter B
success REMOTE 30000
enter C
success STANDARD 16000
```

Các phép tính:

| Đơn | Điều kiện | Chiến lược thắng | Giá gốc | Phí xử lý | Kết quả |
|---|---|---|---:|---:|---:|
| A | REMOTE và express | EXPRESS do ưu tiên trước | 44.000 | 2.000 | 46.000 VND |
| B | REMOTE, không express | REMOTE | 28.000 | 2.000 | 30.000 VND |
| C | LOCAL, không express | STANDARD | 14.000 | 2.000 | 16.000 VND |

Trong ví dụ, tiền dùng `long` theo số VND nguyên, các phép cộng/nhân sử dụng `Math.addExact`, `Math.multiplyExact` để phát hiện tràn. Hệ thống tiền tệ thật cần quy tắc làm tròn, thuế và chính sách hạn mức phù hợp.

## 5. Đọc graph và lời gọi theo đúng chiều

Khi **tạo graph**, composition root đi từ thành phần sâu nhất ra ngoài:

```text
Bước tạo:

  strategies
      ↓
  FirstMatchQuoteService
      ↓
  HandlingFeeDecorator
      ↓
  TraceDecorator  ← đối tượng đưa cho caller
```

Khi **chạy một request**, lời gọi đi từ ngoài vào trong rồi trả kết quả theo chiều ngược:

```text
                       quote(shipment)
                            │
                            ▼
                 TraceDecorator.enter
                            │
                            ▼
                 HandlingFeeDecorator
                            │
                            ▼
                  FirstMatchQuoteService
                            │
                            ▼
                  chiến lược đầu tiên hỗ trợ
                            │
                      tính giá gốc
                            │
                            ▼
                    cộng phí xử lý
                            │
                            ▼
               TraceDecorator.success
                            │
                            ▼
                   return Quote cuối
```

Đó là lý do cách viết:

```java
QuoteService quoteService = new TraceDecorator(
    new HandlingFeeDecorator(
        new FirstMatchQuoteService(strategies),
        2_000L
    ),
    events
);
```

có thể khó đọc khi số decorator tăng. Tạo các biến `firstMatch`, `withFee` rồi `traced` như phần `compose(...)` thường dễ review hơn.

Một điều quan trọng: decorator **không phải danh sách handler độc lập**. Chúng **bọc lồng** quanh một delegate, còn danh sách `RateStrategy` là **tập lựa chọn** bên trong. Nhầm hai loại cấu trúc này dễ khiến người học cho rằng mỗi strategy là một decorator hoặc mọi strategy sẽ cùng tính phí.

## 6. Đổi thứ tự strategies sẽ làm điều gì?

Thử đổi `compose(...)` thành:

```java
List<RateStrategy> strategies = List.of(
    new StandardRate(),
    new ExpressRate(),
    new RemoteRate()
);
```

Do `StandardRate.supports(...)` luôn trả `true`, **mọi request đều được STANDARD chọn**. EXPRESS và REMOTE không còn cơ hội chạy.

Nếu chỉ đổi EXPRESS và REMOTE:

```java
List<RateStrategy> strategies = List.of(
    new RemoteRate(),
    new ExpressRate(),
    new StandardRate()
);
```

Đơn A vừa express vừa REMOTE sẽ được **REMOTE** chọn thay vì EXPRESS. Giá trước phí xử lý đổi từ 44.000 xuống 28.000 VND.

Đây không phải là lỗi cú pháp, cũng không phải lỗi compiler. Cả hai cách wiring đều tạo graph hợp lệ về kiểu Java, nhưng **ngữ nghĩa nghiệp vụ khác nhau**. Vì thế thứ tự cần được thể hiện công khai trong composition root và bảo vệ bằng test.

### Có cần tự động sắp theo điểm ưu tiên?

Có thể, nếu số lượng chiến lược lớn hoặc lấy từ plugin:

```java
record RuleRegistration(
    int priority,
    RateStrategy strategy
) {}
```

Composition root có thể sắp `List<RuleRegistration>` theo `priority` rồi tạo danh sách chiến lược. Khi làm vậy, cần quy định rõ:

- Điểm **nhỏ hơn hay lớn hơn** có ưu tiên cao hơn?
- Có cho phép **hai rule trùng điểm** không? Nếu có, tie-breaker là gì?
- Catch-all được bảo đảm ở cuối bằng cách nào?
- ID chiến lược có duy nhất không?
- Có test khi thay đổi cấu hình hoặc khi thêm plugin không?

Đối với ba chiến lược của bài thực hành, `List.of(...)` khai báo thứ tự trực tiếp **đơn giản hơn** một registry hay annotation sắp thứ tự. Không nên tạo một hệ thống priority động khi yêu cầu chưa cần.

## 7. Đổi thứ tự decorator sẽ làm điều gì?

Graph hiện tại:

```java
QuoteService service = new TraceDecorator(
    new HandlingFeeDecorator(firstMatch, 2_000L),
    events
);
```

Trace là lớp **ngoài cùng**. Vì vậy log thành công ghi giá sau khi cộng phí xử lý.

Nếu đổi thành:

```java
QuoteService service = new HandlingFeeDecorator(
    new TraceDecorator(firstMatch, events),
    2_000L
);
```

Giá trả cho caller vẫn là giá gốc cộng 2.000 VND, nhưng Trace nằm **trong** decorator tính phí. Nó ghi giá gốc, chưa cộng phí:

| Lắp ghép | Giá caller nhận với đơn C | Dòng Trace |
|---|---:|---|
| `Trace(Fee(Core))` | 16.000 VND | `success STANDARD 16000` |
| `Fee(Trace(Core))` | 16.000 VND | `success STANDARD 14000` |

Trong bài toán nghiệp vụ, log được thiết kế là **số tiền cuối cùng khách nhìn thấy**, nên `Trace(Fee(Core))` là cách đặt phù hợp hơn. Nếu mục đích là ghi phí gốc để phân tích rule, thứ tự còn lại có thể hợp lý — nhưng cần đặt tên metrics/log và contract cho đúng.

Những chuỗi bọc khác có hậu quả lớn hơn:

```text
Metrics(Retry(RemoteClient))
Retry(Metrics(RemoteClient))
```

Cách thứ nhất thường đếm **một thao tác logic** (bao gồm nhiều lần thử); cách thứ hai có thể đếm **từng lần gọi remote**. Nếu dùng retry với thao tác có tác dụng phụ, phải có giới hạn thời gian, idempotency và chính sách lỗi phù hợp. **Không nên đổi thứ tự bọc chỉ vì thấy code gọn hơn.**

### Thứ tự trả về và thứ tự xử lý lỗi

Decorator có thể thực hiện logic **trước**, **sau** hoặc **trong `finally`** quanh lời gọi delegate. Do đó:

- Khi đi vào, decorator ngoài cùng chạy phần *before* trước.
- Khi trả về bình thường, decorator trong cùng chạy phần *after* trước.
- Khi có exception, các `catch` và `finally` xử lý theo quan hệ lồng nhau.
- Decorator bắt lỗi rồi trả fallback có thể làm thay đổi việc các decorator phía ngoài quan sát “thành công” hay “thất bại”.

Ở bài này, `TraceDecorator` chỉ catch `RuntimeException` để ghi một dòng failure và **ném lại cùng exception**. Nó không tự chọn giá dự phòng. `HandlingFeeDecorator` chỉ cộng phí nếu delegate đã trả `Quote` hợp lệ. Các trách nhiệm rõ và có thể test được.

## 8. Kiểm thử bằng fake: xác nhận thứ tự và dừng sớm

Không nên chỉ test giá cuối cùng. Hai strategy khác nhau có thể vô tình tính ra cùng giá, hoặc cả hai cùng bị gọi nhưng chỉ kết quả cuối được giữ. Ta cần xác minh **thứ tự thăm dò**, **số lần tính phí**, **short-circuit** và **trace decorator**.

Lưu `OrderedCompositionCheck.java` cạnh file demo:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

public final class OrderedCompositionCheck {

    // Fake strategy ghi được cả supports() và calculate().
    static final class RecordingStrategy
            implements OrderedCompositionDemo.RateStrategy {

        private final String id;
        private final Predicate<OrderedCompositionDemo.Shipment> matcher;
        private final long amount;
        private final List<String> events;

        RecordingStrategy(
                String id,
                Predicate<OrderedCompositionDemo.Shipment> matcher,
                long amount,
                List<String> events) {
            this.id = id;
            this.matcher = matcher;
            this.amount = amount;
            this.events = events;
        }

        @Override
        public String id() {
            return id;
        }

        @Override
        public boolean supports(OrderedCompositionDemo.Shipment s) {
            events.add("supports:" + id);
            return matcher.test(s);
        }

        @Override
        public long calculate(OrderedCompositionDemo.Shipment s) {
            events.add("calculate:" + id);
            return amount;
        }
    }

    private static void expect(
            List<String> actual, List<String> expected) {
        if (!actual.equals(expected)) {
            throw new AssertionError(
                "Expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        List<String> checks = new ArrayList<>();

        var express = new RecordingStrategy(
            "EXPRESS", OrderedCompositionDemo.Shipment::express,
            100L, checks);

        var remote = new RecordingStrategy(
            "REMOTE",
            s -> s.zone() == OrderedCompositionDemo.Zone.REMOTE,
            200L, checks);

        var standard = new RecordingStrategy(
            "STANDARD", s -> true, 300L, checks);

        var engine = new OrderedCompositionDemo.FirstMatchQuoteService(
            List.of(express, remote, standard));

        var both = new OrderedCompositionDemo.Shipment(
            "A", OrderedCompositionDemo.Zone.REMOTE, 2, true);

        // 1. Cùng khớp EXPRESS và REMOTE: rule đầu thắng.
        var first = engine.quote(both);

        if (!"EXPRESS".equals(first.selectedStrategy())
                || first.amountVnd() != 100L) {
            throw new AssertionError("Wrong first-match selection");
        }
        expect(checks, List.of(
            "supports:EXPRESS", "calculate:EXPRESS"));

        // 2. EXPRESS không khớp, REMOTE được thử tiếp.
        checks.clear();
        engine.quote(new OrderedCompositionDemo.Shipment(
            "B", OrderedCompositionDemo.Zone.REMOTE, 2, false));

        expect(checks, List.of(
            "supports:EXPRESS",
            "supports:REMOTE",
            "calculate:REMOTE"));

        // 3. Chỉ STANDARD khớp.
        checks.clear();
        engine.quote(new OrderedCompositionDemo.Shipment(
            "C", OrderedCompositionDemo.Zone.LOCAL, 2, false));

        expect(checks, List.of(
            "supports:EXPRESS",
            "supports:REMOTE",
            "supports:STANDARD",
            "calculate:STANDARD"));

        // 4. Kiểm tra composition thật và giá sau decorator.
        List<String> trace = new ArrayList<>();
        var app = OrderedCompositionDemo.compose(trace);

        var quote = app.quote(both);
        if (!"EXPRESS".equals(quote.selectedStrategy())
                || quote.amountVnd() != 46_000L) {
            throw new AssertionError("Wrong composed result");
        }
        expect(trace, List.of(
            "enter A", "success EXPRESS 46000"));

        // 5. Đổi thứ tự decorator: giá giống, trace khác.
        List<String> insideTrace = new ArrayList<>();
        var traceInsideFee =
            new OrderedCompositionDemo.HandlingFeeDecorator(
                new OrderedCompositionDemo.TraceDecorator(
                    new OrderedCompositionDemo.FirstMatchQuoteService(
                        List.of(new RecordingStrategy(
                            "ONLY", s -> true, 100L,
                            new ArrayList<>()))),
                    insideTrace),
                2_000L);

        var finalQuote = traceInsideFee.quote(both);

        if (finalQuote.amountVnd() != 2_100L) {
            throw new AssertionError("Fee was not added");
        }
        expect(insideTrace, List.of(
            "enter A", "success ONLY 100"));

        // 6. Không rule nào phù hợp: báo lỗi rõ, log failure.
        List<String> noMatchTrace = new ArrayList<>();
        var noMatch = new OrderedCompositionDemo.TraceDecorator(
            new OrderedCompositionDemo.FirstMatchQuoteService(
                List.of(new RecordingStrategy(
                    "NEVER", s -> false, 1L,
                    new ArrayList<>()))),
            noMatchTrace);

        boolean rejected = false;
        try {
            noMatch.quote(both);
        } catch (IllegalStateException expected) {
            rejected = expected.getMessage()
                .contains("No rate strategy");
        }

        if (!rejected) {
            throw new AssertionError("No-match was not rejected");
        }
        expect(noMatchTrace, List.of(
            "enter A", "failure IllegalStateException"));

        // 7. Cấu hình trùng ID phải được phát hiện lúc lắp.
        boolean duplicatesRejected = false;
        try {
            new OrderedCompositionDemo.FirstMatchQuoteService(
                List.of(
                    new RecordingStrategy(
                        "SAME", s -> true, 1L, new ArrayList<>()),
                    new RecordingStrategy(
                        "SAME", s -> false, 2L, new ArrayList<>())
                ));
        } catch (IllegalArgumentException expected) {
            duplicatesRejected = true;
        }
        if (!duplicatesRejected) {
            throw new AssertionError(
                "Duplicate strategy IDs were accepted");
        }

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac OrderedCompositionDemo.java OrderedCompositionCheck.java
java OrderedCompositionCheck
```

Kết quả dự kiến:

```text
PASS
```

### Những gì test thực sự chứng minh

| Nhánh kiểm thử | Điều được xác minh |
|---|---|
| A khớp hai rule | EXPRESS được thử đầu, REMOTE không bị gọi |
| B chỉ khớp REMOTE | Engine thử EXPRESS, rồi REMOTE, và dừng |
| C chỉ khớp STANDARD | STANDARD được xét sau hai chiến lược ưu tiên |
| Composition thật | Phí 2.000 được cộng, Trace thấy giá cuối |
| Đổi thứ tự bọc | Giá cuối có thể giống nhưng log quan sát khác |
| Không rule nào khớp | Ném lỗi thay vì âm thầm chọn mặc định |
| Trùng ID | Lỗi cấu hình được phát hiện tại constructor engine |

Đây là **unit test của chính sách điều phối và composition**. Trong ứng dụng có HTTP client hoặc database, cần thêm integration test cho chiến lược tương ứng và kiểm tra vòng đời tài nguyên. Fake chứng minh thứ tự gọi, nhưng không tự chứng minh chính sách vận chuyển thực tế đúng với hợp đồng khách hàng.

## 9. “Chọn một” khác với “chạy tất cả”

Cùng một `List<Strategy>` có thể mang các ý nghĩa khác nhau. Trước khi viết vòng lặp, cần ghi rõ:

| Mô hình | Ý nghĩa | Khi nào dừng? | Ví dụ |
|---|---|---|---|
| **First match wins** | Chọn một chiến lược phù hợp có ưu tiên cao nhất | Ngay khi tìm thấy rule khớp | Tính phí vận chuyển |
| **All applicable** | Chạy mọi rule áp dụng | Sau khi duyệt hết hoặc theo fail-fast policy | Nhiều kiểm tra độc lập |
| **Pipeline** | Mỗi bước nhận đầu ra của bước trước | Theo pipeline hoặc khi bước lỗi | Chuẩn hóa → xác thực → biến đổi |
| **Chain of Responsibility** | Mỗi handler có thể xử lý hoặc chuyển tiếp | Khi handler xử lý hoặc hết chuỗi | Định tuyến request |
| **Best score** | Chấm điểm rồi chọn phương án tốt nhất | Sau khi so sánh đủ candidate | Chọn thuật toán tối ưu hóa |

Ở ví dụ chính, **tuyệt đối không gọi `calculate(...)` cho mọi strategy rồi chỉ chọn giá cuối**. Ta cần dừng ngay khi một `supports(...)` trả true.

Với một hệ thống validation, yêu cầu có thể khác: chạy tất cả validator để trả về **danh sách toàn bộ lỗi**. Khi đó list vẫn có thứ tự, nhưng engine cần aggregate kết quả; **không nên dùng lại first-match engine chỉ vì có thể nhận một `List`**.

## 10. Composition root chịu trách nhiệm điều gì?

Thứ tự và ownership nên tập trung ở **composition root**:

```java
List<RateStrategy> strategies = List.of(
    new ExpressRate(),
    new RemoteRate(),
    new StandardRate()
);

QuoteService core = new FirstMatchQuoteService(strategies);
QuoteService withFee = new HandlingFeeDecorator(core, 2_000L);
QuoteService traced = new TraceDecorator(withFee, events);
```

Mã này là “bản đồ” của graph. Đổi thứ tự, thêm strategy hay bọc decorator mới là thay đổi có thể review tại một ranh giới.

Một số nguyên tắc:

1. **Service không tự tạo strategy.** Nó nhận danh sách qua constructor.
2. **Decorator không tự tìm delegate từ global container.** Nó nhận `QuoteService` cụ thể.
3. **Caller không tự cấu hình những bước bên trong graph**. Nó chỉ gọi `quote(shipment)`.
4. **Danh sách được snapshot** khi tạo engine, tránh caller mutate ưu tiên giữa request.
5. **Không thêm một Registry tổng quát** chỉ để lắp ba chiến lược.
6. **Giữ scope thích hợp**: chiến lược bất biến có thể dùng chung, còn dữ liệu của request đi qua method.

Điều kiện về thứ tự có thể được xác minh bằng **composition test** như mục 8 và, nếu cấu hình phức tạp, bằng validation ngay trước khi mở listener nhận công việc.

### Khi nào container phù hợp?

Nếu ứng dụng lớn có hàng chục chiến lược đăng ký theo module, một DI container có thể giúp tìm, tạo và inject collection. Nhưng cần quy định **cụ thể** cách sắp thứ tự và cách chọn các implementation:

- Registration/qualifier nào được chọn?
- Annotation/order field có quy tắc so sánh rõ không?
- Có duplicate priority không?
- Có profile hoặc module nào khiến một strategy không được đăng ký?
- Các decorator được lắp theo thứ tự nào?
- Bean nào singleton, request-scoped hoặc transient?
- Container đóng bean nào lúc shutdown, theo hợp đồng nào?

Việc “container đã khởi động” không bảo đảm thứ tự từ plugin/registration luôn đúng về nghiệp vụ. **Test trên graph thực tế sau composition** vẫn cần thiết.

## 11. Scope, thread safety và lifecycle trong chuỗi bọc

Trong ví dụ, `ExpressRate`, `RemoteRate` và `StandardRate` không giữ trạng thái mutable. `FirstMatchQuoteService` lưu danh sách bất biến, `HandlingFeeDecorator` giữ một con số cố định. Các thành phần này có thể được chia sẻ theo graph của demo.

`TraceDecorator` lại ghi vào `ArrayList` do caller tạo. Đây là lựa chọn **chỉ dùng cho demo tuần tự**. Nếu nhiều thread cùng gọi vào service, việc ghi một `ArrayList` không được đồng bộ có thể gây lỗi và mất sự kiện. Production nên sử dụng logger/metrics sink phù hợp với concurrency, tránh log dữ liệu nhạy cảm hoặc ID không cần thiết.

Nếu decorator mở tài nguyên cần đóng, cần phân biệt:

| Tình huống | Ai sở hữu? | Khi nào đóng? |
|---|---|---|
| Một policy thuần tính toán | Không cần đóng | JVM xử lý bộ nhớ |
| HTTP client dùng chung trong strategy | Application root/container theo đăng ký | Sau khi các consumer ngừng dùng |
| Session mở bởi strategy cho một yêu cầu | Scope hoặc caller được factory cấp | Cuối request/transaction |
| Metrics sink dùng chung | Root hoặc lifecycle manager | Sau khi phần còn phụ thuộc đã dừng |
| Executor chạy callback cho decorator | Owner tạo executor | Khi shutdown có stop/drain đúng |

**Inject một `AutoCloseable` vào decorator không tự trao quyền đóng**. Nếu client dùng chung được inject vào ba strategy, một strategy không được tự `close()` client sau mỗi lần tính phí. Ngược lại, session ngắn hạn do factory mở trong một lần gọi cần được đóng bằng `try-with-resources` theo contract của factory.

Với graph có tài nguyên:

```text
Tạo: ClientPool → RateStrategy → FirstMatchEngine → Decorators
Đóng: Decorators/consumer dừng → RateStrategy dừng → ClientPool.close()
```

Trong hệ thống bất đồng bộ, còn phải chặn request mới và chờ những thao tác đang chạy trước khi đóng pool. Thứ tự close không thể suy ra chỉ từ số lượng wrapper; phải dựa vào **quan hệ sử dụng và quyền sở hữu**.

## 12. Trường hợp sai thường gặp

| Cách làm | Hệ quả | Điều chỉnh |
|---|---|---|
| Đặt catch-all strategy đầu danh sách | Những rule còn lại không bao giờ được chọn | Đưa catch-all xuống cuối, có test overlap |
| Duyệt `HashMap.values()` rồi coi là thứ tự ưu tiên | Thứ tự không được diễn đạt đúng contract | Dùng `List` hoặc sort theo priority có tie-breaker |
| Chỉ test số tiền, không test số lần gọi | Có thể gọi dư nhiều strategy | Dùng fake ghi `supports` và `calculate` |
| Dùng mọi strategy rồi chọn kết quả cuối | Sai semantics first-match | Dừng khi gặp lần khớp đầu tiên |
| Đặt Trace bên trong Fee nhưng gọi log là “giá cuối” | Metrics/log sai ý nghĩa | Bọc Trace ngoài Fee hoặc đổi tên chỉ số |
| Chọn thứ tự theo tên class/bean | Phụ thuộc cấu hình ngầm và dễ đổi | Thứ tự business phải được khai báo |
| Chiến lược tự `new` HTTP client mỗi lần tính mà không có ownership | Tốn kết nối, leak | Inject client/factory phù hợp |
| Singleton decorator giữ `currentShipment` | Rò dữ liệu giữa các request | Truyền `Shipment` theo method |
| Decorator bắt mọi exception rồi trả giá 0 | Che lỗi nghiệp vụ và lỗi tích hợp | Chỉ xử lý lỗi có chính sách rõ; giữ failure |
| Container tự tìm mọi rule mà không validate | Có thể thiếu/nhân đôi rule | Kiểm tra ID, coverage, priority và graph |
| Dùng decorator để thực hiện lựa chọn thuật toán | Lẫn hai trách nhiệm khác nhau | Selector/engine chọn; decorator bọc |
| Lắp wrapper rồi không biết tầng nào đo metrics | Khó giải thích số liệu | Vẽ chuỗi từ ngoài vào trong và test |

## 13. Bài tập mở rộng có tiêu chí chấp nhận

### Bài tập 1 — Đổi ưu tiên và dự đoán giá

Thay thứ tự trong `compose(...)` thành REMOTE, EXPRESS, STANDARD. Với đơn A vừa remote vừa express, dự đoán `selectedStrategy` và `amountVnd` sau phí xử lý.

**Đáp án:** REMOTE; 28.000 + 2.000 = **30.000 VND**. Giải thích dựa trên lần `supports(...)` đầu tiên trả true, không phải công thức tính cao hay thấp hơn.

### Bài tập 2 — Thêm quy tắc mới và tránh bị che khuất

Thêm `HeavyRate` áp dụng cho đơn từ 10 kg, phí 50.000 VND + 1.000 VND/kg.

Trước khi lắp, trả lời: đơn vừa express vừa nặng nên ưu tiên EXPRESS hay HEAVY? Đặt `HeavyRate` ở vị trí thể hiện câu trả lời và viết test cho giao điểm đó.

**Tiêu chí chấp nhận:** có yêu cầu ưu tiên được ghi thành câu, có hai test ít nhất cho nặng và nặng+express, không dựa vào thứ tự tự phát.

### Bài tập 3 — Viết decorator giảm giá

Viết `DiscountDecorator` implements `QuoteService`, giảm 10% số tiền. Thử hai cách:

```text
Discount(HandlingFee(Core))
HandlingFee(Discount(Core))
```

Với giá gốc 10.000 và phí 2.000 VND, kết quả hai cách có giống nhau không? **Đáp án:** 10.800 VND so với 11.000 VND nếu phần giảm tính trên tổng hoặc chỉ trên giá gốc tương ứng, dùng phép chia số nguyên cắt phần dư. Cần xác định rõ discount áp dụng vào thành phần phí nào trong nghiệp vụ thật.

### Bài tập 4 — Quan sát lỗi qua decorator

Tạo strategy fake có `supports(...)` true nhưng `calculate(...)` ném `IllegalStateException("provider failed")`. Bọc bằng `TraceDecorator`. Test cần xác nhận:

- Có dòng `enter ...`.
- Có dòng `failure IllegalStateException`.
- Exception vẫn tới caller, không trả `Quote` giả.
- Những strategy phía sau **không** được thử sau khi strategy đã chọn ném lỗi, trừ khi nghiệp vụ định nghĩa fallback/routing khác.

### Bài tập 5 — Chống thay đổi danh sách sau khi lắp

Tạo một `ArrayList<RateStrategy>`, truyền vào `FirstMatchQuoteService`, rồi gọi `clear()` trên danh sách gốc. Bằng test, chứng minh engine vẫn dùng snapshot đã nhận. Nếu không dùng `List.copyOf(...)`, điều gì có thể xảy ra?

### Bài tập 6 — Tạo các test “không được gọi”

Viết ba fake strategy ghi ID vào danh sách mỗi khi `supports()` chạy, và vào danh sách khác mỗi khi `calculate()` chạy. Khi EXPRESS khớp đầu, assert cả hai danh sách đều **không chứa REMOTE và STANDARD**. Đây là cách kiểm tra short-circuit rõ hơn chỉ so sánh giá.

### Bài tập 7 — Chuyển thứ tự sang cấu hình

Chấp nhận một danh sách ID, ví dụ `["EXPRESS", "REMOTE", "STANDARD"]` từ cấu hình khởi động. Composition root ánh xạ ID sang strategy đã biết, từ chối ID không hỗ trợ và ID trùng. Sau đó xác minh catch-all đứng cuối.

Không viết `ServiceLocator.get(Class<?>)` trong `FirstMatchQuoteService`; phần phân giải ID và xây danh sách thuộc về composition.

### Bài tập 8 — Phân biệt pipeline với first-match

Đổi yêu cầu thành: “phải chạy tất cả rule kiểm tra để trả về danh sách lỗi”. Hãy thiết kế interface `ValidationRule` riêng với `validate(Shipment)` thay vì dùng `RateStrategy.calculate(...)`. Lập test chứng minh mọi rule cần thiết đều chạy theo chính sách, và xác định rõ việc có dừng ở lỗi đầu tiên hay không.

### Bài tập 9 — Thử nghiệm quản lý tài nguyên

Cho `RemoteRate` nhận một `RateClientFactory` và mở một session cho mỗi lời gọi. Viết fake session với bộ đếm `open`/`close`; xác minh session được đóng kể cả khi calculate ném lỗi. Nếu client pool được nhiều strategy dùng chung, ai phải đóng pool khi ứng dụng dừng?

**Gợi ý:** scope xử lý đóng session; root/container sở hữu pool dùng chung. Không cho strategy tự đóng pool sau một yêu cầu.

## 14. Checklist review một composition có thứ tự

Trước khi gửi PR hoặc chuyển sang DI container, kiểm tra:

- [ ] Contract của strategy phân biệt được **điều kiện phù hợp** và **hành động được chọn**.
- [ ] Chính sách **first-match**, **run-all** hay **pipeline** được viết thành yêu cầu rõ.
- [ ] Danh sách có **thứ tự tường minh**; không dựa vào map/set không bảo đảm thứ tự.
- [ ] Catch-all, nếu có, đặt cuối và được test với các trường hợp overlap.
- [ ] ID của strategy không rỗng/không trùng; cấu hình không hợp lệ fail fast.
- [ ] Đã kiểm tra **short-circuit** với fake, không chỉ kết quả cuối.
- [ ] Sơ đồ decorator thể hiện **lớp ngoài/lớp trong** và thứ tự gọi/trả về.
- [ ] Log/metrics đo đúng điều nghiệp vụ cần (giá gốc hay giá cuối, số lần thử hay thao tác logic).
- [ ] Decorator không che lỗi bất ngờ hoặc tạo kết quả thành công giả.
- [ ] Dữ liệu của request đi qua tham số, không giữ ở singleton có state mutable.
- [ ] Mỗi resource có owner rõ; client dùng chung không bị consumer đóng nhầm.
- [ ] Composition root là nơi chọn implementation, sắp thứ tự và lắp chain; test được graph thực tế.

## Ghi nhớ

- **Danh sách chiến lược có thứ tự** biểu diễn ưu tiên lựa chọn; với first-match, rule đầu tiên phù hợp sẽ thắng và các rule sau không được gọi.
- **Decorator có thứ tự bọc**, không phải danh sách “chạy ngẫu nhiên”; đổi lớp ngoài/lớp trong có thể thay đổi metrics, logs, lỗi hoặc phép tính.
- **Composition root** chọn thứ tự strategies và decorator một cách tường minh bằng Java thuần. DI container có thể giúp tạo graph lớn hơn nhưng không thay cho quy tắc ưu tiên nghiệp vụ.
- **Kiểm thử thứ tự bằng fake ghi sự kiện**, gồm `supports`, `calculate`, kết quả, short-circuit và đường lỗi.
- **Chọn kỹ thuật đúng theo trách nhiệm:** Strategy đại diện thuật toán có thể chọn, Decorator bọc hành vi, Factory cấp tài nguyên theo thời điểm, scope/ownership xác định vòng đời.
- **Làm rõ trước khi tối ưu:** thứ tự đúng và có test quan trọng hơn việc giảm vài dòng lắp ghép hoặc thêm nhiều pattern không cần thiết.
