# Sealed và generics trong mô hình miền

## 1. Bài toán thiết kế: số trường hợp hữu hạn, dữ liệu của mỗi trường hợp có kiểu riêng

Trong Java 17, **sealed class/interface** và **generics** giải quyết hai câu hỏi khác nhau nhưng bổ sung rất tốt cho nhau:

- **Sealed:** Một miền dữ liệu cho phép *những kiểu con nào*? Ai được quyền bổ sung một trường hợp mới?
- **Generics:** Một trường hợp hợp lệ đang *mang loại dữ liệu nào*? Trình biên dịch có thể kiểm tra các giá trị được truyền qua API đến đâu?

Giả sử ứng dụng thương mại điện tử có các thao tác:

1. Tìm một đơn hàng theo mã, trả về `Order` nếu tìm thấy.
2. Tra cứu khách hàng, trả về `Customer` nếu tìm thấy.
3. Tính số tiền của một đơn hàng, trả về `Long`.

Mỗi thao tác có thể **thành công** hoặc **thất bại**, nhưng dữ liệu thành công khác nhau. Ta muốn diễn đạt:

```text
Outcome<T>                        T = kiểu dữ liệu của kết quả thành công
│
├── Success<T>                    chứa value có kiểu T
│
└── Failure<T>                    chứa thông tin lỗi

Outcome<Order>                    kết quả tra cứu đơn hàng
Outcome<Customer>                 kết quả tra cứu khách hàng
Outcome<Long>                     kết quả tính số tiền
```

Đây là bài toán điển hình của mô hình miền: **đóng số trường hợp được phép xảy ra**, đồng thời **giữ kiểu tĩnh của payload** xuyên suốt các lớp service, domain và adapter.

Java 17 đã chuẩn hóa sealed classes/interfaces (JEP 409). Trong bài này, các ví dụ chỉ dùng tính năng ngôn ngữ **ổn định trên JDK 17**, không phụ thuộc vào preview.

## 2. Vì sao một mô hình thiếu sealed hoặc thiếu generics dễ gây lỗi?

### 2.1. Chỉ dùng `Object`: kết quả có kiểu mơ hồ

Một API quá tổng quát có thể trả về:

```java
record OperationResult(boolean success, Object value, String error) {
}
```

Những trạng thái sau đều có thể được tạo:

```java
new OperationResult(true, "không phải Order", null);
new OperationResult(false, new Object(), null);
new OperationResult(true, null, "vừa thành công vừa lỗi");
```

Caller phải ép kiểu từ `Object`, tự kiểm tra `success` rồi suy diễn `value` và `error` có được phép cùng hiện diện hay không. Tập trạng thái có thể tạo lớn hơn tập trạng thái nghiệp vụ hợp lệ.

### 2.2. Chỉ dùng generic interface mở: payload có kiểu, tập trường hợp chưa được kiểm soát

```java
interface Outcome<T> {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String reason) implements Outcome<T> {
}
```

Đoạn này đã giữ được kiểu giá trị thành công. Tuy nhiên, một thư viện hoặc đoạn mã khác có thể tự khai báo:

```java
record Unexpected<T>(Object content) implements Outcome<T> {
}
```

Nếu miền thực sự chỉ có hai nhánh `Success` và `Failure`, interface mở không bảo đảm được quy tắc đó tại thời điểm biên dịch.

### 2.3. Kết hợp sealed và generics để làm rõ hợp đồng

```java
sealed interface Outcome<T> permits Success, Failure {
}

record Success<T>(T value) implements Outcome<T> {
}

record Failure<T>(String reason) implements Outcome<T> {
}
```

Ở đây:

1. `Outcome<T>` giới hạn **những direct subtypes** được phép: chỉ `Success` và `Failure`.
2. `T` cho biết kiểu của payload trong nhánh thành công.
3. `Success<T>` và `Failure<T>` đều thực hiện cùng hợp đồng `Outcome<T>`.
4. Hai record là những kiểu `final` ngầm định; do đó các nhánh không thể bị kế thừa tiếp.

Ví dụ, `Success<Order>` là một trường hợp hợp lệ của `Outcome<Order>`, nhưng `Success<String>` **không thể** được gán vào biến `Outcome<Order>`.

**Lưu ý:** `permits Success, Failure` liệt kê **class/record được phép làm kiểu con**, không liệt kê từng kiểu tham số hóa như `Success<Order>` hay `Success<Customer>`. Danh sách `permits` kiểm soát *cấu trúc kế thừa*, còn generics kiểm soát *kiểu của dữ liệu*.

## 3. Ví dụ đầy đủ: `Outcome<T>` với thao tác `map` và `fold`

Một mô hình kết quả hữu ích không chỉ dừng ở việc khai báo hai nhánh. Ta còn muốn:

- Trả về giá trị `Order`, `Customer`, `Long` theo hợp đồng kiểu tĩnh.
- **Biến đổi** giá trị thành công từ `T` sang `U` mà không làm mất nhánh thất bại.
- **Xử lý** một kết quả bằng hai hàm, mỗi hàm dành cho một trường hợp.
- Không bắt caller ép kiểu từ `Object`.

### 3.1. Mã hoàn chỉnh trên Java 17

Tạo file **SealedGenericDemo.java**:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class SealedGenericDemo {

    // T xác định loại dữ liệu của nhánh thành công.
    sealed interface Outcome<T> permits Success, Failure {

        <U> Outcome<U> map(Function<? super T, ? extends U> mapper);

        <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super ErrorInfo, ? extends R> onFailure
        );
    }

    record ErrorInfo(String code, String message) {
        public ErrorInfo {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(message, "message");
            if (code.isBlank() || message.isBlank()) {
                throw new IllegalArgumentException("Lỗi phải có mã và thông báo");
            }
        }
    }

    // Nhánh thành công có payload kiểu T.
    record Success<T>(T value) implements Outcome<T> {
        public Success {
            Objects.requireNonNull(value, "value");
        }

        @Override
        public <U> Outcome<U> map(
                Function<? super T, ? extends U> mapper
        ) {
            Objects.requireNonNull(mapper, "mapper");
            U mapped = Objects.requireNonNull(
                    mapper.apply(value), "mapped value"
            );
            return new Success<>(mapped);
        }

        @Override
        public <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super ErrorInfo, ? extends R> onFailure
        ) {
            Objects.requireNonNull(onSuccess, "onSuccess");
            Objects.requireNonNull(onFailure, "onFailure");
            return onSuccess.apply(value);
        }
    }

    // T là kiểu kết quả kỳ vọng; nhánh này chỉ mang thông tin lỗi.
    record Failure<T>(ErrorInfo error) implements Outcome<T> {
        public Failure {
            Objects.requireNonNull(error, "error");
        }

        @Override
        public <U> Outcome<U> map(
                Function<? super T, ? extends U> mapper
        ) {
            Objects.requireNonNull(mapper, "mapper");
            return new Failure<>(error);
        }

        @Override
        public <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super ErrorInfo, ? extends R> onFailure
        ) {
            Objects.requireNonNull(onSuccess, "onSuccess");
            Objects.requireNonNull(onFailure, "onFailure");
            return onFailure.apply(error);
        }
    }

    record Order(String id, long amountInCents) {
        public Order {
            Objects.requireNonNull(id, "id");
            if (id.isBlank() || amountInCents < 0) {
                throw new IllegalArgumentException("Đơn hàng không hợp lệ");
            }
        }
    }

    static Outcome<Order> findOrder(String id) {
        if ("O-100".equals(id)) {
            return new Success<>(new Order("O-100", 125_000L));
        }
        return new Failure<>(
                new ErrorInfo("ORDER_NOT_FOUND", "Không tìm thấy " + id)
        );
    }

    public static void main(String[] args) {
        for (String id : List.of("O-100", "O-999")) {
            Outcome<Order> found = findOrder(id);

            // Chỉ biến đổi payload thành công.
            Outcome<Long> amount = found.map(Order::amountInCents);

            String message = amount.fold(
                    cents -> "Số tiền: " + cents + " cents",
                    error -> "Lỗi " + error.code() + ": " + error.message()
            );

            System.out.println(message);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```shell
java -version
javac --release 17 SealedGenericDemo.java
java SealedGenericDemo
```

Kết quả:

```text
Số tiền: 125000 cents
Lỗi ORDER_NOT_FOUND: Không tìm thấy O-999
```

Ví dụ cố ý sử dụng **record lồng bên trong class** để toàn bộ mã chạy trong một file. Trong dự án thực tế, có thể tách từng loại ra file riêng và đặt đúng package/module.

### 3.2. `map` giữ lại ý nghĩa của nhánh lỗi

Chữ ký:

```java
<U> Outcome<U> map(Function<? super T, ? extends U> mapper);
```

thể hiện việc chuyển một `Outcome<T>` thành `Outcome<U>`.

- Nếu đối tượng là `Success<T>`, `mapper` biến đổi `value: T` thành `U`, kết quả là `Success<U>`.
- Nếu đối tượng là `Failure<T>`, không có giá trị thành công để biến đổi; kết quả là `Failure<U>` mang cùng thông tin lỗi.

Ví dụ:

```java
Outcome<Order> order = new Success<>(
        new Order("O-101", 50_000L)
);

Outcome<Long> total = order.map(Order::amountInCents);
```

Ở đây `Order::amountInCents` là hàm từ `Order` sang `Long`. Trình biên dịch suy ra `U = Long`. Không cần ép kiểu và không cần lưu payload vào `Object`.

Lớp `Failure<T>` vẫn có tham số `T` dù không chứa trường kiểu `T` vì nó phải thuộc về cùng một kiểu kết quả. Chẳng hạn `Failure<Order>` có nghĩa là **thao tác kỳ vọng trả về Order nhưng đã thất bại**.

Thiết kế này là một lựa chọn hữu ích, không phải quy tắc Java bắt buộc. Một số thư viện sẽ tách kiểu lỗi thành một tham số generic thứ hai hoặc dùng API xử lý lỗi khác. Mục đích của sealed/generics vẫn là làm rõ miền và hợp đồng kiểu.

### 3.3. `fold` gom cách xử lý hai nhánh vào một API

Chữ ký:

```java
<R> R fold(
        Function<? super T, ? extends R> onSuccess,
        Function<? super ErrorInfo, ? extends R> onFailure
);
```

Người gọi đưa vào hai hàm; kết quả cuối có kiểu `R`. Mỗi record tự thực thi nhánh đúng của nó. Ví dụ:

```java
String label = findOrder("O-100").fold(
        order -> order.id() + " đã tìm thấy",
        error -> error.code() + " - " + error.message()
);
```

Trong nhánh thành công, lambda nhận đúng kiểu `Order`, nên có thể gọi `order.id()`. Trong nhánh thất bại, lambda nhận `ErrorInfo`. Cách này giảm nhu cầu rải `instanceof` khắp các lớp sử dụng kết quả.

**Giới hạn cần hiểu:** `fold` là một API xử lý hai trường hợp do người thiết kế tự khai báo; Java không tự sinh ra nó từ `sealed`. Các kiểu con được phép phải cài đặt hợp đồng này. Nếu mô hình sau này bổ sung nhánh mới, cần xem lại ý nghĩa của `fold`, kiểm thử các hành vi và quyết định có cần thêm nhánh xử lý hay không.

## 4. Vì sao generics quan trọng khi đặt sealed trong domain model?

### 4.1. Tránh nhầm dữ liệu giữa các use case

Giả sử có:

```java
record Customer(String id, String name) {
}

Outcome<Order> orderResult = findOrder("O-100");
Outcome<Customer> customerResult =
        new Success<>(new Customer("C-1", "An"));
```

Việc gán `customerResult` vào một biến `Outcome<Order>` là lỗi biên dịch. Sealed một mình không phát hiện sai loại payload; tham số generic `T` mới tạo được ràng buộc này.

### 4.2. Khai báo API theo nhu cầu dữ liệu thực tế

Một repository hoặc domain service có thể định nghĩa:

```java
interface OrderLookup {
    Outcome<Order> findById(String id);
}

interface CustomerLookup {
    Outcome<Customer> findById(String id);
}
```

Cả hai dùng chung bộ trường hợp thành công/thất bại, nhưng người sử dụng không cần biết một kết quả sẽ chứa kiểu `Object` nào. Kiểu trả về mô tả rõ ràng hợp đồng của từng use case.

### 4.3. Kết hợp generic với record

Một record có thể có tham số kiểu:

```java
record Page<T>(List<T> items, int totalItems) {
    public Page {
        items = List.copyOf(items);
        if (totalItems < items.size()) {
            throw new IllegalArgumentException("totalItems không hợp lệ");
        }
    }
}
```

Sau đó:

```java
Outcome<Page<Order>> orders =
        new Success<>(new Page<>(
                List.of(new Order("O-102", 10_000L)),
                1
        ));
```

Đây là một **kiểu generic lồng nhau**: `Outcome` biểu diễn kết quả, `Page` biểu diễn dữ liệu phân trang, còn `Order` là entity/value thuộc miền.

`List.copyOf` tạo bản danh sách không sửa được qua API và từ chối phần tử `null`. Tuy nhiên, nếu phần tử là đối tượng có trạng thái mutable thì vẫn cần cân nhắc sao chép hoặc bảo vệ các đối tượng bên trong. Record không mặc nhiên bất biến sâu.

## 5. Sealed type có nhiều tham số generic: kiểu thành công và kiểu lỗi

Trong ví dụ đầu, mọi lỗi đều dùng `ErrorInfo`. Ở hệ thống lớn, từng use case có thể muốn mã hóa **kiểu lỗi** để compiler phân biệt lỗi nghiệp vụ với dữ liệu sai định dạng.

Ta có thể khai báo `DomainResult<T, E>`, trong đó:

- `T` là kiểu dữ liệu khi thành công.
- `E` là kiểu của lỗi nghiệp vụ khi thất bại.

Ví dụ:

```java
sealed interface DomainError permits OrderNotFound, InvalidOrder {
}

record OrderNotFound(String orderId) implements DomainError {
}

record InvalidOrder(String reason) implements DomainError {
}

sealed interface DomainResult<T, E extends DomainError>
        permits Ok, Err {
}

record Ok<T, E extends DomainError>(T value)
        implements DomainResult<T, E> {
}

record Err<T, E extends DomainError>(E error)
        implements DomainResult<T, E> {
}
```

Khi áp dụng:

```java
DomainResult<Order, OrderNotFound> loaded =
        new Err<>(new OrderNotFound("O-404"));

DomainResult<Order, InvalidOrder> checked =
        new Err<>(new InvalidOrder("Số tiền âm"));
```

Trong mô hình này, `E extends DomainError` là **bounded type parameter**. Nó bảo đảm kiểu lỗi thuộc miền `DomainError`. Nếu đội phát triển cần kết quả có thể chứa nhiều loại lỗi, có thể chọn một kiểu lỗi chung đã được thiết kế:

```java
DomainResult<Order, DomainError> result =
        new Err<>(new OrderNotFound("O-404"));
```

**Phân biệt hai hàng rào bảo vệ:**

1. `DomainError` là sealed và có các nhánh `OrderNotFound`, `InvalidOrder`, nên giới hạn các loại lỗi trực tiếp.
2. `E extends DomainError` không cho phép dùng tùy ý `String`, `Exception` hay một class không phải `DomainError` làm kiểu lỗi.

Việc chọn một `E` thật hẹp (ví dụ `OrderNotFound`) có thể hữu ích cho phương thức đơn giản, nhưng cũng khiến chữ ký phức tạp nếu use case có nhiều lỗi. Trong API công khai, hãy cân bằng độ chính xác kiểu với khả năng đọc và sử dụng.

**Lưu ý về tính bất biến kiểu:** `DomainResult<Order, OrderNotFound>` không tự động là `DomainResult<Order, DomainError>`. Java generics **invariant**, dù `OrderNotFound implements DomainError`. Phần dưới sẽ giải thích cách nhận dữ liệu khi cần linh hoạt.

## 6. Sealed và generics kiểm soát hai loại mở rộng khác nhau

### 6.1. `permits` không chứa tham số kiểu cụ thể

Không thể viết một danh sách như:

```java
// KHÔNG hợp lệ: permits yêu cầu tên các kiểu con, không phải
// những lần áp dụng tham số generic.
sealed interface Outcome<T>
        permits Success<Order>, Success<Customer> {
}
```

Muốn giới hạn `T` theo một miền, hãy dùng **bounded type parameter**:

```java
sealed interface DomainEntity permits OrderEntity, CustomerEntity {
}

record OrderEntity(String id) implements DomainEntity {
}

record CustomerEntity(String id) implements DomainEntity {
}

static <T extends DomainEntity> T requireEntity(T entity) {
    return java.util.Objects.requireNonNull(entity);
}
```

`T extends DomainEntity` nói rằng kiểu payload phải thuộc tập kiểu tương thích với `DomainEntity`. Còn `DomainEntity` sealed xác định giới hạn kế thừa trực tiếp.

Điều này **không** ép `T` phải đúng một tên class trong `permits`: `T` có thể chính là `DomainEntity` (kiểu cha) và một hierarchy có nhánh `non-sealed` vẫn có thể được mở rộng gián tiếp. Nếu cần kiểm soát loại dữ liệu chặt hơn, hãy thiết kế cấu trúc miền và API tương ứng thay vì kỳ vọng ràng buộc generic tự giải quyết mọi trường hợp.

### 6.2. `final`, `sealed` và `non-sealed` vẫn có ý nghĩa với generic subtype

Ví dụ:

```java
sealed interface DataEvent<T> permits SavedEvent, ChangeEvent {
}

record SavedEvent<T>(T entity) implements DataEvent<T> {
}

non-sealed interface ChangeEvent<T> extends DataEvent<T> {
}

record UpdatedEvent<T>(T entity) implements ChangeEvent<T> {
}
```

`DataEvent` chỉ có hai direct permitted subtypes: `SavedEvent` và `ChangeEvent`. `SavedEvent` là record nên dừng kế thừa tại đó. Nhưng `ChangeEvent` là `non-sealed`, cho phép các kiểu con khác triển khai nó, rồi gián tiếp trở thành `DataEvent`.

Nếu quy tắc nghiệp vụ yêu cầu **tập trường hợp hoàn toàn hữu hạn**, không nên mở một nhánh bằng `non-sealed` nếu không có lý do. Tính generic không làm thay đổi quy tắc này.

### 6.3. Vị trí các kiểu con vẫn bị ràng buộc

Trong Java 17:

- Sealed type thuộc **named module** chỉ được cho phép direct subclass trong cùng **named module**.
- Sealed type thuộc **unnamed module** chỉ được cho phép direct subclass trong cùng **package**.

Đây là ràng buộc của sealed, không phụ thuộc vào việc class/interface có generic hay không. Với codebase chia module, hãy kiểm tra ranh giới kiến trúc trước khi biến một interface thành sealed.

## 7. Variance và wildcard: dùng `Outcome<T>` qua nhiều cấp kiểu

Java generics mặc định **không hiệp biến (invariant)**. Nếu `CustomerEntity implements DomainEntity`, hai kiểu `Outcome<CustomerEntity>` và `Outcome<DomainEntity>` vẫn khác nhau.

```java
Outcome<CustomerEntity> customer =
        new Success<>(new CustomerEntity("C-1"));

// KHÔNG hợp lệ:
// Outcome<DomainEntity> entity = customer;
```

Nếu chỉ cần **đọc** kết quả với góc nhìn của kiểu cha, có thể dùng wildcard:

```java
static void printEntity(Outcome<? extends DomainEntity> outcome) {
    String text = outcome.fold(
            entity -> "Entity: " + entity,
            error -> "Lỗi: " + error.message()
    );
    System.out.println(text);
}
```

Đoạn này dựa trên `Outcome` từ ví dụ hoàn chỉnh và `DomainEntity` đã định nghĩa ở trên. Nó chấp nhận `Outcome<CustomerEntity>`, `Outcome<OrderEntity>` và các trường hợp có kiểu payload là subtype của `DomainEntity`.

```java
printEntity(new Success<>(new CustomerEntity("C-1")));
```

Vì `? extends DomainEntity` chưa cho biết **subtype cụ thể**, caller chỉ có thể dựa an toàn vào những hợp đồng có trên `DomainEntity`. Không thể tự coi payload là `CustomerEntity` hoặc tự thêm một payload tùy ý vào cấu trúc có kiểu không xác định.

### 7.1. Ý nghĩa `? super T` và `? extends U` trong `map`

Chữ ký:

```java
<U> Outcome<U> map(Function<? super T, ? extends U> mapper);
```

dùng cả hai chiều của wildcard:

- `? super T`: hàm có thể **nhận** giá trị kiểu `T` hoặc một kiểu cha phù hợp. Ví dụ mapper nhận `Object` vẫn có thể xử lý `Order`.
- `? extends U`: hàm có thể **trả** một giá trị kiểu `U` hoặc kiểu con của `U`.

Đây là một biểu hiện của nguyên tắc *Producer Extends, Consumer Super* (PECS), áp dụng cho vị trí dữ liệu đi vào/đi ra khỏi một API generic.

Không phải method generic nào cũng cần wildcard phức tạp. Chỉ thêm độ linh hoạt này khi nó phản ánh những tình huống sử dụng thực tế và vẫn giữ chữ ký dễ hiểu.

### 7.2. Không dùng raw type để né compiler

Tránh:

```java
// Không nên:
Outcome result = new Success<>("abc");
```

`Outcome` ở đây là **raw type**; trình biên dịch không còn bảo vệ kiểu `T` như mong muốn. Raw type có thể gây cảnh báo unchecked và đưa lỗi đến runtime.

Ưu tiên:

```java
Outcome<String> result = new Success<>("abc");
```

Nếu thực sự không biết kiểu payload, `Outcome<?>` diễn đạt điều đó rõ hơn raw `Outcome`, nhưng lúc sử dụng bạn chỉ có thể dựa vào kiểu `Object` hoặc một giới hạn đã biết.

## 8. Type erasure: sealed không làm generic payload có mặt đầy đủ tại runtime

Generics trong Java chủ yếu được kiểm tra ở **compile time**. Sau biên dịch, nhiều thông tin tham số generic chịu cơ chế **type erasure**.

Ví dụ:

```java
Outcome<Order> order = new Success<>(new Order("O-1", 100L));
Outcome<String> text = new Success<>("hello");
```

Ở runtime, cả hai đều có thể là đối tượng của class `Success`. Runtime không tự phân biệt chúng như hai class độc lập `Success<Order>` và `Success<String>`.

Điều này dẫn đến các giới hạn:

### 8.1. Không dùng `instanceof` với kiểu tham số hóa không reifiable

```java
Object any = new Success<>("hello");

// KHÔNG hợp lệ nếu kiểm tra runtime kiểu tham số hóa cụ thể:
// if (any instanceof Success<String>) { ... }

if (any instanceof Success<?> success) {
    Object value = success.value();
    System.out.println(value);
}
```

`Success<?>` là cách kiểm tra được kiểu thực tế `Success` mà không giả vờ runtime biết tham số cụ thể. Giá trị đọc từ `success.value()` ở ví dụ này chỉ có thể coi như `Object`.

Khi đã có `Outcome<Order>` tại compile time, hãy tận dụng API kiểu mạnh (`map`, `fold`) thay vì tự kiểm tra class rồi ép kiểu unchecked.

### 8.2. Không overload chỉ khác tham số generic

Hai overload này có cùng chữ ký sau type erasure và không thể khai báo song song:

```java
// KHÔNG hợp lệ khi cùng nằm trong một class:
// void handle(Outcome<Order> result) { }
// void handle(Outcome<Customer> result) { }
```

Có thể đặt tên phương thức riêng theo use case, nhận thêm token kiểu dữ liệu khi cần, hoặc thiết kế API polymorphic phù hợp.

### 8.3. Reflection của sealed khác với reflection của generic type

Java 17 hỗ trợ đọc thông tin cấu trúc sealed bằng `Class`:

```java
System.out.println(Outcome.class.isSealed());

for (Class<?> child : Outcome.class.getPermittedSubclasses()) {
    System.out.println(child.getSimpleName());
}
```

Với ví dụ ở trên, các kiểu được phép là `Success` và `Failure`. Reflection này cho biết **những class được phép kế thừa**, không phải danh sách các lần sử dụng `Outcome<Order>`, `Outcome<String>` và những tham số kiểu khác.

Do đó, không thể dựa vào `permits` hoặc `getPermittedSubclasses()` để kiểm chứng tự động kiểu payload của một đối tượng đã deserialize mà không có thêm cơ chế thích hợp.

## 9. Xử lý sealed generic result trong Java 17

### 9.1. `instanceof` pattern đã ổn định

Java 17 hỗ trợ pattern matching for `instanceof` (chuẩn hóa từ Java 16). Ví dụ với kiểu không biết trước tham số cụ thể:

```java
static String describeUnknown(Object candidate) {
    if (candidate instanceof Success<?> success) {
        return "Success: " + success.value();
    }
    if (candidate instanceof Failure<?> failure) {
        return "Failure: " + failure.error().code();
    }
    return "Không phải Outcome được hỗ trợ";
}
```

Đoạn này không biết `T` của `Success` là gì; cách đọc an toàn là thông qua `Object`. Trong code đã biết `Outcome<Order>`, dùng `fold` giúp giữ kiểu `Order` rõ ràng hơn.

### 9.2. Pattern matching for switch chưa ổn định trên Java 17

Một số bài viết về sealed types dùng:

```java
// Minh họa cú pháp thuộc giai đoạn sau Java 17; không dùng làm
// ví dụ Java 17 ổn định:
// return switch (outcome) {
//     case Success<?> s -> "...";
//     case Failure<?> f -> "...";
// };
```

Trong **JDK 17**, pattern matching for switch mới là **preview**. Tính năng này được chuẩn hóa ở **Java 21**; record patterns cũng không phải tính năng ổn định của Java 17. Vì vậy, bài học và ứng dụng cần biên dịch bằng `--release 17` nên dùng `instanceof` pattern, đa hình hoặc một API như `fold` tùy mục tiêu.

Với chuỗi `if`/`instanceof`, Java 17 **không tự kiểm tra tính đầy đủ (exhaustiveness)** dựa trên danh sách subtype được sealed. Sealed kiểm soát quyền **kế thừa trực tiếp**, không tự chứng minh rằng mọi nhánh nghiệp vụ trong chương trình đã được xử lý.

### 9.3. Đa hình là cách giảm phụ thuộc vào phân nhánh

Ví dụ `fold` ở phần 3 cho phép mỗi nhánh `Success`/`Failure` tự gọi hàm tương ứng. Với logic gần với từng kiểu con, có thể định nghĩa phương thức trừu tượng trong sealed interface và để các kiểu con tự thực hiện.

Không phải mọi xử lý đều nên đẩy vào domain object. Nếu logic thuộc tầng HTTP, giao diện, lưu trữ hoặc tích hợp, hãy giữ xử lý ở lớp phù hợp để mô hình miền không phụ thuộc không cần thiết vào adapter.

## 10. Thiết kế kiểu lỗi: khi nào dùng một generic, khi nào dùng hai?

Hai hình thức phổ biến có đặc điểm khác nhau:

| Mô hình | Ví dụ | Điểm mạnh | Điểm cần cân nhắc |
|---|---|---|---|
| Một tham số `T` | `Outcome<Order>` | Chữ ký ngắn, dễ sử dụng, các lỗi cùng chuẩn | Kiểu lỗi ít chi tiết ở cấp API |
| Hai tham số `T, E` | `DomainResult<Order, DomainError>` | Thể hiện cả payload thành công lẫn lỗi trong kiểu tĩnh | API, factory và kiểu trả về phức tạp hơn |
| Hai tham số với lỗi hẹp | `DomainResult<Order, OrderNotFound>` | Chỉ rõ lỗi mà một use case dự kiến tạo | Có thể khó kết hợp nhiều bước xử lý tạo các lỗi khác nhau |

Ví dụ, pipeline gồm tra cứu, kiểm tra nghiệp vụ và thanh toán có thể sinh nhiều loại lỗi. Nếu ép mỗi phương thức dùng `E` cực kỳ hẹp, việc kết hợp kết quả có thể yêu cầu thiết kế thêm toán tử chuyển kiểu lỗi (`mapError`, `flatMap`, hoặc hàm kết hợp tương ứng). Khi đó, việc dùng một `DomainError` sealed chung có thể phù hợp hơn.

Sealed và generics là **công cụ diễn đạt**, không tự cung cấp cơ chế giao dịch, retry, exception handling hoặc validation. Các hành vi này vẫn phải được thiết kế theo yêu cầu nghiệp vụ.

## 11. Quan hệ với `Optional<T>`, exception và null

`Optional<T>` đã có từ Java 8, hữu ích khi một giá trị **có thể vắng mặt**, ví dụ tra cứu tùy chọn:

```java
java.util.Optional<Order> findOptionalOrder(String id);
```

Nhưng `Optional.empty()` không thể tự nói rõ **vì sao** thao tác thất bại: không tìm thấy, đầu vào sai, bị từ chối nghiệp vụ hay hết quyền truy cập.

`Outcome<T>` có thể làm rõ hai trường hợp thành công/thất bại với payload lỗi. Ngược lại, nếu API chỉ cần thể hiện giá trị có/không và không có ý nghĩa phân loại lỗi, `Optional<T>` thường gọn hơn.

Exception vẫn hữu ích cho những tình huống nên dùng luồng xử lý ngoại lệ, đặc biệt lỗi không thể phục hồi trong phạm vi gọi hoặc các lỗi hạ tầng. Việc dùng một kiểu kết quả sealed không có nghĩa mọi exception đều phải được bắt và chuyển sang `Failure` một cách máy móc.

Về `null`: generics không mặc định cấm `null`. Ví dụ `Success<String>(null)` là cú pháp có thể viết được nếu constructor không kiểm tra. Trong ví dụ hoàn chỉnh, `Objects.requireNonNull` là **quyết định thiết kế** nhằm không cho phép `Success` mang payload null.

## 12. Sealed generics và ranh giới serialization/API

Mô hình sealed generic thường xuất hiện ở các tầng service/domain, nhưng khi dữ liệu ra ngoài tiến trình qua JSON, message broker hoặc lưu trữ, cần quan tâm:

1. **Type erasure:** `Outcome<Order>` không tự mang đầy đủ kiểu `Order` trong mọi thao tác runtime hoặc deserialize.
2. **Discriminator:** phía nhận có thể cần trường phân biệt `SUCCESS`/`FAILURE` hoặc schema rõ ràng để biết cần tạo loại nào.
3. **Versioning:** khi bổ sung một permitted subtype mới, client cũ có thể chưa biết cách đọc hoặc xử lý nó.
4. **Generic payload:** serializer phải biết chính xác kiểu của payload hoặc có metadata/sơ đồ dữ liệu phù hợp; không mặc định runtime có đủ thông tin từ `T`.
5. **Ràng buộc framework:** thư viện JSON, JPA, validator hoặc mapping cần có phiên bản hỗ trợ Java 17/record/sealed theo tính năng thực tế đang dùng.

Một hợp đồng JSON bên ngoài có thể được thiết kế:

```json
{
  "kind": "SUCCESS",
  "data": {
    "id": "O-100",
    "amountInCents": 125000
  }
}
```

Và trường hợp lỗi:

```json
{
  "kind": "FAILURE",
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "Không tìm thấy O-999"
  }
}
```

Đây chỉ là **minh họa hợp đồng API**; Java sealed không tự áp đặt hình dạng JSON hoặc tự sinh discriminator. Cần cấu hình serializer, kiểm tra nội dung đầu vào không đáng tin cậy và quyết định chiến lược tương thích khi API thay đổi.

Record phù hợp với nhiều DTO/value object, nhưng không phải lựa chọn mặc định cho mọi entity JPA có lifecycle, proxy và yêu cầu thay đổi trạng thái. Khi tích hợp framework, nên phân tách **mô hình nghiệp vụ**, **DTO** và **entity lưu trữ** theo yêu cầu của từng tầng.

## 13. Rủi ro khi mở rộng mô hình sau này

Giả sử `Outcome<T>` lúc đầu chỉ có `Success`/`Failure`. Sau đó nghiệp vụ cần thêm trường hợp **đang chờ xử lý**:

```java
sealed interface Outcome<T> permits Success, Failure, Pending {
}

record Pending<T>(String trackingId) implements Outcome<T> {
}
```

Từ góc nhìn miền, việc này thay đổi ý nghĩa hợp đồng của mọi `Outcome<T>`. Nếu interface có method `fold` chỉ nhận hai hàm, cách xử lý `Pending` phải được thiết kế lại. Những cách thường gặp:

- Mở rộng `fold` thành ba hàm và cập nhật implementation cùng mọi caller.
- Giữ kết quả của một giai đoạn chỉ có hai trường hợp, mô hình trạng thái bất đồng bộ/chờ xử lý ở một kiểu miền khác.
- Đổi API theo cách tương thích có chủ đích, ví dụ version mới hoặc bộ biến đổi hợp đồng riêng.

Không nên tự gán `Pending` thành `Failure` chỉ để tận dụng chữ ký cũ nếu nghiệp vụ không xem chờ xử lý là thất bại.

Một thay đổi nhỏ ở danh sách `permits` có thể là **breaking change về ngữ nghĩa**, kể cả khi biên dịch ở một số vị trí vẫn thành công. Với một thư viện được nhiều module dùng, hãy xem việc thêm/bớt nhánh là thay đổi hợp đồng cần đánh giá, cập nhật tài liệu và kiểm thử.

## 14. Những lỗi thiết kế thường gặp

| Tình huống | Vì sao cần tránh | Hướng thiết kế phù hợp |
|---|---|---|
| `Result<Object>` dùng cho mọi use case | Mất thông tin kiểu payload và dễ ép kiểu sai | Khai báo `Result<Order>`, `Result<Customer>`... |
| Sealed interface nhưng một nhánh `non-sealed` mở tùy ý | Tập trường hợp gián tiếp không còn thực sự đóng | Dùng record/`final` ở nhánh lá khi miền cần hữu hạn |
| Dùng `permits` như thể có thể hạn chế `T` | `permits` giới hạn class con trực tiếp, không giới hạn kiểu generic được thay thế | Dùng generic bound hoặc API riêng cho nhóm payload |
| Gán `Result<Child>` cho `Result<Parent>` | Generics invariant | Dùng wildcard phù hợp cho API chỉ đọc, hoặc thiết kế thao tác chuyển đổi |
| Dùng raw `Result` | Mất kiểm tra kiểu, dễ phát sinh warning và lỗi runtime | Khai báo tham số kiểu hoặc `Result<?>` nếu chưa biết kiểu |
| Kiểm tra `instanceof Success<Order>` trên `Object` | Type erasure làm tham số kiểu không reifiable | Dùng `Success<?>` hoặc API kiểu mạnh |
| Nhầm sealed với kiểm tra giá trị hợp lệ | Sealed chỉ kiểm soát kế thừa | Constructor validation, bất biến miền và kiểm thử |
| Nhầm record là bất biến sâu | Field có thể tham chiếu object mutable | Defensive copy hoặc thiết kế immutable các thành phần |
| Dùng pattern switch như cú pháp Java 17 ổn định | Pattern matching for switch ở Java 17 là preview | Dùng `instanceof` pattern, đa hình hoặc `fold` |
| Cố dùng generic result thay cho mọi exception | Làm phức tạp API và có thể che lỗi hệ thống | Phân biệt lỗi nghiệp vụ dự kiến và lỗi bất thường |
| Serialize mà không có hợp đồng phân loại nhánh | Phía nhận có thể không biết subtype và kiểu payload | Thiết kế discriminator/schema/versioning rõ ràng |

## 15. Lộ trình thực hành thiết kế mô hình miền với sealed và generics

### Bài tập 1 — Kết quả xác thực người dùng

Thiết kế:

```text
AuthenticationResult<T>
├── Authenticated<T>(T principal)
├── AuthenticationRejected<T>(reason)
└── AdditionalVerification<T>(challengeId)
```

Yêu cầu:

1. Khai báo sealed interface và ba record generic, các nhánh là những trường hợp trực tiếp được cho phép.
2. `principal` của nhánh thành công phải có kiểu `T`.
3. Viết một service trả về `AuthenticationResult<UserPrincipal>`.
4. Viết hàm trình bày kết quả bằng `instanceof` pattern trong Java 17 hoặc một hợp đồng `fold` phù hợp ba nhánh.
5. Cân nhắc liệu nhánh xác minh bổ sung có phải kết quả cuối cùng của thao tác, hay thuộc một mô hình workflow riêng.

### Bài tập 2 — Hai tham số kiểu và lỗi nghiệp vụ

Tạo `InventoryResult<T, E extends InventoryError>` với hai nhánh `Available` và `Unavailable`; `InventoryError` là sealed interface chứa `OutOfStock` và `InvalidSku`.

Yêu cầu:

1. Viết các khai báo kiểu tương thích JDK 17, không bật preview.
2. Tạo kết quả `InventoryResult<Product, InventoryError>` cho cả thành công và thất bại.
3. Thử gán `InventoryResult<Product, OutOfStock>` cho `InventoryResult<Product, InventoryError>`; giải thích lý do compiler không cho phép.
4. Xác định khi nào nên dùng kiểu lỗi chung và khi nào kiểu lỗi hẹp có ích.

### Bài tập 3 — Biến đổi kết quả mà không bỏ mất lỗi

Dùng `Outcome<T>` ở phần 3, xây dựng pipeline:

```text
findOrder(id)
  -> Outcome<Order>
  -> map(Order::amountInCents)
  -> Outcome<Long>
  -> map(cents -> cents > 100_000L)
  -> Outcome<Boolean>
```

Thử với một ID tồn tại và một ID không tồn tại. Giải thích vì sao mapper không chạy ở nhánh `Failure`, và thông tin lỗi vẫn có mặt khi kiểu thành công đổi từ `Order` sang `Boolean`.

### Bài tập 4 — Kiểm tra giới hạn sealed và type erasure

1. Thử tạo `record Skipped<T>(String reason) implements Outcome<T>` mà không khai báo trong `permits`; đọc thông báo lỗi biên dịch.
2. Thử khai báo `if (obj instanceof Success<Order>)` khi `obj` có kiểu `Object`; tìm lý do bị từ chối.
3. Đổi thành `if (obj instanceof Success<?> s)`; xác định kiểu có thể đọc an toàn từ `s.value()`.
4. Gọi `Outcome.class.getPermittedSubclasses()`; phân biệt thông tin class được phép và thông tin generic type argument.

### Bài tập 5 — Quyết định kiến trúc

Cho một nền tảng cho phép đối tác tự viết thêm plugin xuất báo cáo. Mỗi plugin có thể trả dữ liệu khác nhau và có thể bổ sung loại kết quả tùy theo tính năng plugin.

Hãy phân biệt **ranh giới nào nên đóng bằng sealed** (ví dụ kết quả điều phối chuẩn do platform sở hữu), **ranh giới nào phải mở** (ví dụ SPI của plugin), và **ranh giới nào cần generic** (ví dụ loại dữ liệu mà plugin trả về). Giải pháp tốt có thể dùng cả sealed interface lẫn interface mở ở những cấp khác nhau.

## 16. Tự đánh giá sau bài học

Bạn nắm được chủ đề khi có thể trả lời các câu hỏi:

1. Sealed kiểm soát subtype khác gì với generics kiểm soát payload?
2. Vì sao `Outcome<Order>` không thể gán cho `Outcome<Object>` hoặc ngược lại?
3. Vì sao `Failure<T>` có thể mang tham số `T` dù không có field kiểu `T`?
4. `map` cần giữ nguyên lỗi nhưng thay đổi kiểu `T` thành `U` như thế nào?
5. `fold` khác việc viết liên tiếp nhiều `if`/`instanceof` ở điểm nào?
6. `E extends DomainError` kiểm tra điều gì, còn sealed `DomainError` kiểm tra điều gì?
7. Vì sao `permits Success<Order>` không hợp lệ?
8. Type erasure ảnh hưởng ra sao đến `instanceof`, overload và deserialize generic payload?
9. Vì sao cần cân nhắc khi bổ sung một nhánh kết quả mới?
10. Cách xử lý nào trong bài chạy ổn định trên Java 17, và cú pháp pattern switch thuộc phiên bản nào?

## 17. Tài liệu tham khảo

- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): quyết định thiết kế và quy tắc sealed được chuẩn hóa trong Java 17.
- [Java Language Specification — Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html): generic types, type parameters, type erasure, sealed classes/interfaces và các quy tắc kế thừa.
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/): API của `Class`, `Function`, `Objects`, `List` và các kiểu Java SE 17.
- [dev.java — Learn Java](https://dev.java/learn/): tài liệu học ngôn ngữ Java, generics, records và thiết kế đối tượng.

Khi thiết kế một miền dữ liệu, hãy bắt đầu bằng câu hỏi **“Hệ thống cho phép những trường hợp nào, và mỗi trường hợp mang dữ liệu gì?”**. Sealed giúp giới hạn các trường hợp hợp lệ; generics giúp mỗi trường hợp có payload đúng kiểu. Kết hợp hai công cụ này làm hợp đồng miền rõ hơn, giảm ép kiểu và tạo cơ sở an toàn để tiếp tục phát triển ứng dụng Java 17.
