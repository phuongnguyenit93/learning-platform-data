# Optional: `orElse()` đánh giá đối số ngay, `orElseGet()` gọi `Supplier` khi cần

## 1. Vì sao hai phương thức trông giống nhau nhưng chạy khác nhau?

`Optional<T>` biểu diễn một giá trị **có mặt** hoặc **vắng mặt**. Khi cần lấy giá trị hoặc dùng giá trị dự phòng, Java cung cấp hai phương thức:

```java
T orElse(T other)
T orElseGet(Supplier<? extends T> supplier)
```

Hai chữ ký trên là dạng rút gọn từ API `java.util.Optional<T>`: `orElse` nhận **giá trị dự phòng đã được tính**, trong khi `orElseGet` nhận **hành vi cung cấp giá trị dự phòng** qua functional interface `Supplier`.

Điểm khác biệt quan trọng:

- Với `optional.orElse(expensiveFallback())`, Java **đánh giá `expensiveFallback()` trước khi gọi `orElse`**, kể cả khi `optional` đã có giá trị.
- Với `optional.orElseGet(() -> expensiveFallback())`, Java tạo/truyền biểu thức `Supplier`; **thân lambda chỉ chạy khi `optional` rỗng**.
- Nếu `Optional` có giá trị, cả hai đều **trả giá trị đó**, nhưng việc tính đối số của `orElse` có thể đã gây chi phí, side effect hoặc exception.
- Nếu `Optional` rỗng, `orElse` trả giá trị dự phòng đã tính, còn `orElseGet` gọi `Supplier.get()` để tính giá trị dự phòng.

Đây là quy tắc **đánh giá đối số của phương thức trong Java**, không phải ngoại lệ riêng của `Optional`. Java đánh giá các đối số trước khi thực hiện lời gọi phương thức; truyền một lambda cho phép hoãn **phần thân lambda** tới thời điểm API chủ động gọi nó.

## 2. Bảng kết quả chính xác

Giả sử `Optional<String> value` và hàm `fallback()` trả `"backup"` nhưng cũng ghi log:

| Trạng thái `value` | Biểu thức | `fallback()` có chạy? | Giá trị trả về |
| --- | --- | --- | --- |
| `Optional.of("ready")` | `value.orElse(fallback())` | **Có** | `"ready"` |
| `Optional.of("ready")` | `value.orElseGet(() -> fallback())` | **Không** | `"ready"` |
| `Optional.empty()` | `value.orElse(fallback())` | **Có** | `"backup"` |
| `Optional.empty()` | `value.orElseGet(() -> fallback())` | **Có** | `"backup"` |

Vì vậy, **giá trị trả về có thể giống nhau nhưng hành vi thực thi không giống nhau**. Khi fallback chỉ là một hằng số đã có sẵn, khác biệt thường không đáng kể. Khi fallback truy vấn cơ sở dữ liệu, gọi HTTP, đọc file, tạo đối tượng nặng, ghi log hoặc cập nhật thống kê, khác biệt có thể ảnh hưởng hiệu năng và tính đúng đắn.

## 3. Ví dụ Java 17+ chạy được: đối chiếu cả bốn trường hợp

Lưu tệp `OptionalFallbackDemo.java`:

```java
import java.util.Optional;

public class OptionalFallbackDemo {
    private static String fallback(String source) {
        System.out.println("fallback called: " + source);
        return "backup";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");
        Optional<String> empty = Optional.empty();

        System.out.println("1. present + orElse");
        System.out.println("result=" +
                present.orElse(fallback("orElse")));

        System.out.println("2. present + orElseGet");
        System.out.println("result=" +
                present.orElseGet(() -> fallback("orElseGet")));

        System.out.println("3. empty + orElse");
        System.out.println("result=" +
                empty.orElse(fallback("orElse")));

        System.out.println("4. empty + orElseGet");
        System.out.println("result=" +
                empty.orElseGet(() -> fallback("orElseGet")));
    }
}
```

Biên dịch/chạy:

```bash
javac OptionalFallbackDemo.java
java OptionalFallbackDemo
```

Output **chính xác**:

```text
1. present + orElse
fallback called: orElse
result=ready
2. present + orElseGet
result=ready
3. empty + orElse
fallback called: orElse
result=backup
4. empty + orElseGet
fallback called: orElseGet
result=backup
```

Cách đọc log:

1. Ở ca 1, `fallback("orElse")` chạy ngay trước lời gọi `orElse`. Dù đã in `fallback called: orElse`, kết quả vẫn là `ready` vì `Optional` có giá trị.
2. Ở ca 2, `Optional` có giá trị, vì vậy thân `() -> fallback("orElseGet")` không được gọi; không có log fallback.
3. Ở ca 3, `Optional` rỗng nên giá trị dự phòng đã tính được trả về.
4. Ở ca 4, `Optional` rỗng nên `Supplier.get()` được gọi, từ đó chạy `fallback("orElseGet")`.

Không cần chạy code để đoán một nhánh có thực thi: chỉ cần xác định **giá trị đã được tính trước lời gọi** hay **hàm tính giá trị được truyền vào**.

## 4. Thứ tự đánh giá trong Java: nguồn gốc của tính eager

Xét:

```java
String value = optional.orElse(loadDefault());
```

Về ý nghĩa đánh giá, Java làm các công việc sau theo thứ tự:

1. Đánh giá biểu thức nhận lời gọi `optional`.
2. Đánh giá đối số `loadDefault()` để thu được một đối tượng `String` (hoặc thất bại vì exception).
3. Gọi `orElse` với đối số đã có.
4. Bên trong `orElse`, chọn giá trị nằm trong `Optional` nếu có, ngược lại chọn đối số dự phòng.

Cách viết khái niệm:

```java
String computedDefault = loadDefault(); // luôn được gọi
String value = optional.orElse(computedDefault);
```

Hai dòng trên minh họa nguyên nhân eager; chúng không đồng nghĩa hoàn toàn ở mọi ngữ cảnh có đánh giá receiver phức tạp, nhưng với biến `optional` thông thường, chúng cho thấy rõ đối số được tính trước.

Với:

```java
String value = optional.orElseGet(() -> loadDefault());
```

API có thể giữ callback tới lúc cần. Về mặt hành vi, nếu `Optional` rỗng thì mới xảy ra lời gọi tương đương `supplier.get()`, và chính thân lambda sẽ gọi `loadDefault()`. Nếu `Optional` có giá trị, callback không chạy.

Một cách minh họa đơn giản cho phần chọn giá trị (không phải mã nguồn chính thức của JDK):

```java
// Minh họa ý tưởng; biến value đại diện giá trị bên trong Optional.
T orElse(T other) {
    return value != null ? value : other;
}

T orElseGet(Supplier<? extends T> supplier) {
    return value != null ? value : supplier.get();
}
```

Đây là **pseudocode mang kiểu generic** để diễn đạt nhánh lựa chọn, không phải hai phương thức độc lập có thể dán trực tiếp vào một tệp Java. Nó làm rõ rằng `orElse` đã nhận `other` sau khi caller đánh giá đối số, trong khi `orElseGet` có quyền gọi `supplier.get()` có điều kiện.

## 5. Phân biệt đánh giá biểu thức tạo `Supplier` với chạy `Supplier.get()`

Một hiểu nhầm tinh vi là “`orElseGet` khiến **mọi thứ** trong đối số đều lazy”. Điều đúng là: **việc gọi thân Supplier được hoãn**. Nhưng Java vẫn phải đánh giá biểu thức được dùng để tạo hoặc lấy đối tượng `Supplier` trước khi gọi `orElseGet`.

Ví dụ:

```java
optional.orElseGet(makeSupplier());
```

Nếu `makeSupplier()` in log hay khởi tạo tài nguyên, nó vẫn chạy **ngay** để tạo ra đối tượng `Supplier`, kể cả khi `optional` đã có giá trị. Chỉ `get()` của Supplier được gọi khi `Optional` rỗng.

Ngược lại:

```java
optional.orElseGet(() -> makeSupplier().get());
```

Ở đây, **cả lời gọi `makeSupplier()` lẫn `get()` đều nằm trong thân lambda**, nên chúng chỉ chạy khi `Optional` rỗng.

### Chương trình kiểm tra thời điểm tạo và chạy

Tạo `SupplierTimingDemo.java`:

```java
import java.util.Optional;
import java.util.function.Supplier;

public class SupplierTimingDemo {
    private static Supplier<String> makeSupplier() {
        System.out.println("create supplier");
        return () -> {
            System.out.println("invoke supplier");
            return "backup";
        };
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");
        Optional<String> empty = Optional.empty();

        System.out.println("Case A");
        System.out.println(present.orElseGet(makeSupplier()));

        System.out.println("Case B");
        System.out.println(present.orElseGet(
                () -> makeSupplier().get()));

        System.out.println("Case C");
        System.out.println(empty.orElseGet(makeSupplier()));

        System.out.println("Case D");
        System.out.println(empty.orElseGet(
                () -> makeSupplier().get()));
    }
}
```

Chạy:

```bash
javac SupplierTimingDemo.java
java SupplierTimingDemo
```

Output:

```text
Case A
create supplier
ready
Case B
ready
Case C
create supplier
invoke supplier
backup
Case D
create supplier
invoke supplier
backup
```

Case A chứng minh đối số `makeSupplier()` vẫn được đánh giá khi gọi `orElseGet`. Case B chứng minh một lambda có thân chứa `makeSupplier().get()` sẽ hoãn cả hai lời gọi. Với Case C/D, `Optional` rỗng nên `get()` thực sự chạy.

Tương tự, biểu thức trong phần capture của một lambda hoặc method reference có thể được đánh giá khi tạo callback; vì thế cần xem xét **chính xác cái gì nằm bên trong thân callback**. Không được suy từ chữ `Supplier` rằng mọi công việc chuẩn bị bên ngoài callback tự động được trì hoãn.

## 6. Khi fallback nặng, có side effect hoặc có thể ném exception

### 6.1. Chi phí không cần thiết khi đã có dữ liệu

Ví dụ thiết kế dễ gây phí phạm:

```java
String name = findName(userId)
        .orElse(fetchNameFromRemoteService(userId));
```

Đây là **đoạn minh họa**, giả sử `findName(...)` trả `Optional<String>` và `fetchNameFromRemoteService(...)` trả `String`. Trong trường hợp `findName` đã tìm thấy, lệnh gọi service từ xa vẫn xảy ra trước `orElse`.

Cách hợp lý khi chỉ muốn gọi từ xa nếu thiếu:

```java
String name = findName(userId)
        .orElseGet(() -> fetchNameFromRemoteService(userId));
```

Lúc này phần thân lambda chỉ chạy khi `findName` trả `Optional.empty()`.

**Ngoại lệ quan trọng:** nếu fallback chỉ là giá trị cố định hoặc biến đã được tính sẵn, `orElse` thường dễ đọc hơn:

```java
String label = optionalLabel.orElse("Unknown");
```

Không có lời gọi đắt đỏ hoặc side effect nào trong đối số `"Unknown"`. Việc bọc một hằng số thành `() -> "Unknown"` hiếm khi giúp ích.

### 6.2. Side effect dù giá trị dự phòng bị bỏ qua

Giả sử một hàm `nextId()` tăng bộ đếm rồi trả mã. Nếu dùng:

```java
String id = optionalId.orElse(nextId());
```

bộ đếm sẽ tăng **bất kể `optionalId` có giá trị hay không**, bởi `nextId()` được gọi trước. Nếu chỉ muốn tạo mã mới lúc thiếu:

```java
String id = optionalId.orElseGet(() -> nextId());
```

Nếu chủ đích là tăng bộ đếm mỗi lần xử lý, hãy viết side effect đó thành một thao tác tường minh; không nên lén dựa vào quá trình đánh giá đối số fallback.

### 6.3. Exception từ fallback có thể xuất hiện dù `Optional` có giá trị

Nếu `parseDefault()` ném exception, thì:

```java
String result = Optional.of("ready").orElse(parseDefault());
```

sẽ thất bại **trước khi `orElse` được gọi**, dù `Optional` chứa `"ready"`.

Còn:

```java
String result = Optional.of("ready")
        .orElseGet(() -> parseDefault());
```

không chạy `parseDefault()`, vì giá trị đã có. Hai đoạn này giả định có phương thức `parseDefault()` trả `String` và có thể ném unchecked exception; chúng là các đoạn minh họa, không phải tệp Java độc lập.

Lưu ý: `Supplier.get()` trong `java.util.function.Supplier` **không khai báo checked exception**. Nếu fallback gọi code ném checked exception, lambda phải xử lý hoặc chuyển đổi exception theo hợp đồng, hoặc thiết kế một API callback riêng thích hợp. Không thể dùng một lambda ném `IOException` chưa được bắt trực tiếp trong `orElseGet` rồi kỳ vọng compiler chấp nhận.

## 7. Mẫu ví dụ có đếm số lần fallback chạy

Chương trình sau xác nhận `orElseGet` không lưu cache kết quả fallback. Mỗi lần gọi trên `Optional.empty()` sẽ gọi Supplier một lần nữa. Tạo `OptionalCounterDemo.java`:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalCounterDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        Optional<String> empty = Optional.empty();
        Optional<String> present = Optional.of("stored");

        System.out.println(
                present.orElseGet(() -> "generated-" +
                        calls.incrementAndGet()));
        System.out.println("calls=" + calls.get());

        System.out.println(
                empty.orElseGet(() -> "generated-" +
                        calls.incrementAndGet()));
        System.out.println(
                empty.orElseGet(() -> "generated-" +
                        calls.incrementAndGet()));
        System.out.println("calls=" + calls.get());
    }
}
```

Chạy:

```bash
javac OptionalCounterDemo.java
java OptionalCounterDemo
```

Output:

```text
stored
calls=0
generated-1
generated-2
calls=2
```

`Optional` là một container mô tả có hay không có giá trị; gọi `orElseGet` không biến giá trị dự phòng thành dữ liệu được nhớ bên trong `Optional`. Nếu cần một fallback được tính tối đa một lần, đó là yêu cầu **memoization/cache** riêng của ứng dụng. `AtomicInteger` ở ví dụ chỉ để minh họa và đếm lời gọi rõ ràng; không có ý nghĩa rằng `orElseGet` tự làm việc bất đồng bộ.

## 8. `Supplier`, lambda và method reference

`Supplier<T>` là functional interface có phương thức:

```java
T get();
```

Nó không nhận đối số. Điều này phù hợp với mô hình: **khi thiếu giá trị, hãy yêu cầu một hàm cung cấp giá trị**.

Một cách viết:

```java
String name = optionalName.orElseGet(() -> loadDefaultName());
```

Nếu đã có một phương thức không tham số có chữ ký tương thích, có thể dùng method reference:

```java
String name = optionalName.orElseGet(this::loadDefaultName);
```

Đây là đoạn mã trong **instance method** của lớp có phương thức `loadDefaultName()` trả `String`; nó không phải file Java độc lập.

Với static method có thể dùng `SomeClass::loadDefaultName`. Chú ý method reference tạo hàm, chứ không gọi method fallback ngay, miễn biểu thức receiver đã được đánh giá hợp lệ. Nếu receiver của bound method reference được tính bằng một lời gọi tốn kém, phần xác định receiver có thể vẫn diễn ra ngay; hãy xem xét biểu thức thật của từng trường hợp.

So sánh:

```java
// Sai mục đích lazy: gọi phương thức ngay để lấy String.
optionalName.orElse(loadDefaultName());

// Đúng lazy: gọi phương thức chỉ khi thiếu.
optionalName.orElseGet(() -> loadDefaultName());

// Tương đương về thời điểm gọi loadDefaultName đối với
// receiver bình thường đã có:
optionalName.orElseGet(this::loadDefaultName);
```

Nếu fallback phụ thuộc giá trị đầu vào ngoài `Optional`, lambda có thể capture biến `final` hoặc effectively final:

```java
String fallbackCode = "GUEST";
String code = optionalCode.orElseGet(() -> fallbackCode);
```

Trường hợp này cho thấy capture, nhưng vì giá trị `fallbackCode` đã có sẵn và rẻ, `optionalCode.orElse(fallbackCode)` cũng phù hợp. Hãy lựa chọn dựa vào **chi phí và side effect thực tế**.

## 9. Các trường hợp với `null` và `Optional.empty()`

`Optional.of(null)` ném `NullPointerException` ngay ở thời điểm tạo. Dùng `Optional.ofNullable(value)` khi nguồn có thể là `null`; nó trả `Optional.empty()` nếu đối số là `null`.

Hai phương thức fallback có thể trả `null`:

```java
Optional<String> missing = Optional.empty();

String first = missing.orElse(null);
String second = missing.orElseGet(() -> null);
```

Cả `first` và `second` đều là `null`. Đây là các dòng code đặt trong phương thức có import `java.util.Optional`. Lựa chọn fallback không biến một kết quả `null` thành `Optional` mới; kiểu trả về của `orElse`/`orElseGet` vẫn là `T`, không phải `Optional<T>`.

Tránh truyền `null` làm chính đối tượng `Supplier`:

```java
Optional.<String>empty().orElseGet(null);
```

Ví dụ này **biên dịch nhưng ném `NullPointerException`** khi chạy vì phải gọi `get()` trên tham chiếu `null`. Với `Optional` có giá trị, implementation có thể không truy cập đến Supplier; đừng dùng điều đó làm cớ thiết kế API truyền Supplier `null`.

Phân biệt giữa `orElseGet` và `Optional.or(...)`:

- `orElseGet(Supplier<? extends T>)` cung cấp **giá trị `T`** khi thiếu và trả kết quả kiểu `T`.
- `or(Supplier<? extends Optional<? extends T>>)` (Java 9+) cung cấp **một `Optional` thay thế** khi thiếu và tiếp tục trả `Optional<T>`.

Với cả hai, callback được gọi khi rỗng, nhưng mục đích và kiểu trả về khác nhau. Không sử dụng `orElseGet` để trả `Optional<T>` rồi vô tình tạo `Optional<Optional<T>>`.

## 10. So sánh với các phương thức khác và tránh hiểu sai

| Phương thức | Kết quả | Điểm khác biệt |
| --- | --- | --- |
| `orElse(other)` | `T` | Biểu thức đối số `other` được đánh giá **trước** khi gọi phương thức |
| `orElseGet(supplier)` | `T` | `supplier.get()` chỉ được gọi khi `Optional` rỗng |
| `orElseThrow()` | `T` | Lấy giá trị khi có, ném `NoSuchElementException` khi rỗng |
| `orElseThrow(exceptionSupplier)` | `T` | Chỉ tạo exception qua Supplier khi rỗng rồi ném exception |
| `or(optionalSupplier)` | `Optional<T>` | Chỉ yêu cầu `Optional` khác khi rỗng |
| `ifPresent(action)` | `void` | Chỉ chạy `Consumer` khi có giá trị; không tạo giá trị fallback |

Ví dụ:

```java
String name = optionalName.orElseThrow(
        () -> new IllegalStateException("Missing name"));
```

Việc tạo `IllegalStateException` ở trong lambda **chỉ xảy ra khi thiếu giá trị**. So sánh với `orElseGet`: một bên dùng Supplier tạo giá trị thay thế, bên kia dùng Supplier tạo exception cần ném.

Không nhầm `Optional` với `Stream`. Những quy tắc như stream pipeline *lazy* hay short-circuit của `Predicate.and` là vấn đề API khác. Quyết định ở đây căn cứ chính xác vào **chữ ký và hợp đồng của `orElse`/`orElseGet`**.

## 11. Chọn cách viết theo yêu cầu thực tế

**Dùng `orElse` khi:**

- Giá trị dự phòng là literal, enum, constant hoặc object đã có, ví dụ `orElse("UNKNOWN")`.
- Đối số rẻ, không có side effect đáng kể; đọc code rõ ràng hơn việc dựng một callback.
- Bạn **cố ý** muốn biểu thức đối số được đánh giá bất kể `Optional` đã có hay chưa. Trường hợp này cần diễn đạt rõ mục đích; thường viết side effect thành dòng riêng sẽ dễ hiểu hơn.

**Dùng `orElseGet` khi:**

- Fallback có thể tốn CPU, I/O, cấp phát tài nguyên hoặc gọi remote service.
- Fallback có side effect và chỉ được phép chạy nếu giá trị thật sự thiếu.
- Fallback có thể ném unchecked exception và chỉ nên xảy ra trong nhánh rỗng.
- Fallback phải được tính theo dữ liệu sẵn có ở thời điểm gọi; một lambda hoặc method reference cung cấp đúng hành vi cần chạy.

**Không lạm dụng `orElseGet`:** `orElseGet(() -> "UNKNOWN")` không sai, nhưng không đem lại lợi ích rõ ràng so với `orElse("UNKNOWN")`. Ngược lại, `orElse(new LargeObject(...))` có thể tạo đối tượng không cần dùng nếu `Optional` có giá trị; trường hợp này cần cân nhắc callback.

Hiệu năng thực tế còn phụ thuộc độ phức tạp của fallback, số lần phần tử có mặt/rỗng và tối ưu JVM. Không tuyên bố rằng lambda luôn nhanh hơn hoặc chậm hơn: hãy chọn theo **hợp đồng thực thi** trước, sau đó mới đo đạc nếu hiệu năng là vấn đề.

## 12. Lỗi phổ biến cần tránh

1. **Tưởng `orElse(expensive())` chỉ gọi `expensive()` khi `Optional.empty()`.** Sai: đối số được đánh giá trước, kể cả với `Optional.of(value)`.
2. **Tưởng truyền `makeSupplier()` vào `orElseGet` làm `makeSupplier()` lazy.** Sai: lời gọi tạo Supplier vẫn diễn ra ngay; chỉ `Supplier.get()` được điều khiển bởi `orElseGet`.
3. **Bỏ qua side effect của fallback.** Tăng bộ đếm, ghi log, gọi HTTP hoặc ghi DB có thể xảy ra dù giá trị dự phòng bị bỏ qua nếu viết với `orElse`.
4. **Bỏ qua exception của đối số.** Một fallback throw trong `orElse` có thể chặn chương trình trước khi method `orElse` có cơ hội chọn giá trị hiện hữu.
5. **Nhầm `Supplier<T>` với `T`.** `orElseGet` cần đối tượng Supplier, không cần giá trị từ `supplier.get()` được gọi sớm. Ví dụ `orElseGet(() -> fallback())` khác `orElse(fallback())`.
6. **Cho rằng `orElseGet` lưu cache fallback.** Không có cache do API này cung cấp; nếu gọi nhiều lần trên empty, Supplier có thể chạy nhiều lần.
7. **Dùng `Optional.of(null)`.** Gây `NullPointerException`; cân nhắc `ofNullable` khi giá trị đầu vào có thể rỗng.
8. **Dùng `orElseGet(null)`.** Khi rỗng sẽ không thể gọi `get()`; luôn cung cấp một Supplier hợp lệ.
9. **Lẫn kiểu trả về.** `orElseGet` trả `T`; `or` trả `Optional<T>`. Khi cần chuỗi xử lý tiếp tục ở dạng Optional, dùng API phù hợp.
10. **Dùng method reference mà không kiểm tra cách xác định receiver.** Phần thân được hoãn nhưng biểu thức dùng để chọn receiver cho bound method reference có thể đã được đánh giá sớm.

## 13. Bài tập tự kiểm tra

Giả sử có:

```java
static String generate() {
    System.out.println("generate");
    return "guest";
}
```

Với đoạn đặt trong một phương thức:

```java
Optional<String> a = Optional.of("admin");
Optional<String> b = Optional.empty();

System.out.println(a.orElse(generate()));
System.out.println(a.orElseGet(() -> generate()));
System.out.println(b.orElse(generate()));
System.out.println(b.orElseGet(() -> generate()));
```

Các câu hỏi:

1. Dòng `generate` xuất hiện bao nhiêu lần?
2. Giá trị nào in ra sau mỗi lần gọi?
3. Đổi `a.orElse(generate())` thành `a.orElseGet(() -> generate())` ảnh hưởng output thế nào?
4. Nếu `generate()` gọi một dịch vụ bên ngoài và có thể ném unchecked exception, vì sao việc đổi phương thức có thể ảnh hưởng tính đúng đắn?

**Đáp án:** `generate` xuất hiện **ba lần**, tương ứng với `a.orElse(generate())`, `b.orElse(generate())` và `b.orElseGet(() -> generate())`. Các giá trị được in là `admin`, `admin`, `guest`, `guest` theo thứ tự. Đổi lời gọi đầu tiên sang `orElseGet` làm mất lần gọi `generate` không cần thiết khi `a` có giá trị. Nếu dùng `orElse`, việc gọi dịch vụ có thể gây chi phí/side effect/exception ngoài ý muốn ngay cả khi dữ liệu đã có.

## 14. Quy tắc ghi nhớ

Hãy đọc mỗi biểu thức theo câu hỏi: **“Đối số là giá trị đã tính hay một hàm sẽ tính khi cần?”**

```text
optional.orElse(fallback())
                └── fallback() chạy trước khi orElse được gọi

optional.orElseGet(() -> fallback())
                       └── thân lambda chỉ chạy nếu Optional.empty()

optional.orElseGet(makeSupplier())
                   └── makeSupplier() chạy ngay;
                       supplier.get() chỉ chạy nếu Optional.empty()
```

Khi fallback là giá trị có sẵn, `orElse` đơn giản và hợp lý. Khi fallback là một công việc chỉ cần làm trong trường hợp thiếu dữ liệu, `orElseGet` diễn đạt chính xác ý định và tránh thực thi vô ích. Đây là khác biệt cần nắm khi dùng `Optional` trong Java và thiết kế API nhận hành vi bằng `Supplier`.

**Tham khảo:** Java SE API của `java.util.Optional` (`orElse`, `orElseGet`, `orElseThrow`, `or`), `java.util.function.Supplier`; Java Language Specification §15.7 về thứ tự đánh giá biểu thức và §15.12 về lời gọi phương thức.