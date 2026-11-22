# Tạo `Optional` thay thế bằng `or` và `Supplier`

Từ Java 9, `Optional<T>` có phương thức `or(Supplier<? extends Optional<? extends T>> supplier)`. Phương thức này cho phép cung cấp một `Optional` thay thế khi `Optional` hiện tại rỗng. Vì supplier chỉ được gọi khi cần fallback, ta có thể nối nhiều nguồn tra cứu mà không phải tự kiểm tra `isPresent()` ở từng bước.

Ý tưởng chính: mỗi nguồn tra cứu trả về `Optional<T>`. Ta gọi `.or(...)` để chuyển sang nguồn tiếp theo khi nguồn trước không có giá trị. Cuối chuỗi, kết quả vẫn là một `Optional<T>` để chương trình quyết định cách xử lý.

## 1. `Supplier` là gì?

`Supplier<T>` là functional interface trong `java.util.function`. Nó đại diện cho một tác vụ không nhận đối số và cung cấp một giá trị kiểu `T` khi gọi `get()`.

```java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

Trong thực tế, ta thường truyền lambda hoặc method reference:

```java
Supplier<String> messageSupplier = () -> "Giá trị dự phòng";
Supplier<Optional<String>> optionalSupplier = () -> Optional.of("Giá trị dự phòng");
```

Hai supplier trên có kiểu trả về khác nhau. Supplier thứ nhất trả về `String`; supplier thứ hai trả về `Optional<String>`. Sự khác biệt này quyết định nên dùng `orElseGet(...)` hay `or(...)`.

## 2. Cú pháp và ý nghĩa của `Optional.or`

```java
Optional<T> alternative = optional.or(supplier);
```

Kiểu chữ ký tổng quát trong Java là:

```java
public Optional<T> or(
    Supplier<? extends Optional<? extends T>> supplier
);
```

Quy tắc thực thi:

1. Nếu `optional` đang có giá trị, `or` trả về chính `Optional` hiện tại; supplier không được gọi.
2. Nếu `optional` rỗng, `or` gọi `supplier.get()` và trả về `Optional` do supplier cung cấp.
3. Supplier phải trả về một `Optional` khác null. Nếu `get()` trả về null, phương thức ném `NullPointerException`.
4. Đối tượng supplier truyền vào cũng phải khác null; truyền supplier null sẽ ném `NullPointerException`.
5. Nếu supplier ném exception, exception đó được truyền ra nơi gọi.

`or` không lấy giá trị bên trong Optional. Kết quả của nó vẫn là `Optional<T>`, vì vậy có thể tiếp tục gọi `or(...)`, `map(...)`, `flatMap(...)`, `orElse(...)` hoặc các phương thức Optional phù hợp khác.

## 3. Ví dụ cơ bản

```java
Optional<String> username = Optional.empty();

Optional<String> result = username.or(
    () -> Optional.of("guest")
);

System.out.println(result.orElse("unknown"));
```

Kết quả:

```text
guest
```

`username` rỗng nên lambda được thực thi. Lambda trả về `Optional.of("guest")`, vì vậy `result` chứa giá trị `guest`.

Nếu Optional ban đầu đã có giá trị:

```java
Optional<String> username = Optional.of("alice");

Optional<String> result = username.or(
    () -> Optional.of("guest")
);

System.out.println(result.orElse("unknown"));
```

Kết quả:

```text
alice
```

Supplier không được gọi vì `username` đã có giá trị. Đây là đặc điểm lazy của fallback trong `or`.

## 4. Nối nhiều nguồn tra cứu bằng `or`

Một ứng dụng có thể tra cứu dữ liệu từ nhiều nguồn theo thứ tự ưu tiên: bộ nhớ đệm, cơ sở dữ liệu chính, rồi nguồn dự phòng. Mỗi hàm tra cứu trả về `Optional<T>`; nếu không tìm thấy, hàm trả về `Optional.empty()`.

```java
Optional<User> user = findInCache(id)
    .or(() -> findInDatabase(id))
    .or(() -> findInBackup(id));
```

Cách viết này diễn đạt rõ thứ tự ưu tiên:

1. Dùng kết quả từ cache nếu có.
2. Nếu cache rỗng, mới tra cơ sở dữ liệu.
3. Nếu cơ sở dữ liệu cũng rỗng, mới tra nguồn dự phòng.
4. Nếu cả ba đều rỗng, kết quả cuối cùng là `Optional.empty()`.

Supplier cho mỗi bước chỉ được gọi khi tất cả bước trước đó chưa cung cấp giá trị. Nhờ vậy, nguồn có chi phí cao không bị truy cập khi đã tìm thấy kết quả ở nguồn ưu tiên cao hơn.

### Vì sao supplier phải trả về Optional?

`or` được thiết kế để thay thế một Optional rỗng bằng một Optional khác. Do đó supplier phải có kiểu trả về Optional. Nếu hàm dự phòng chỉ trả về `User`, dùng `orElseGet(...)` để lấy một `User` thay thế sau khi Optional rỗng.

Ví dụ:

```java
Optional<User> user = findUser(id)
    .or(() -> findUserInArchive(id));
```

Trong ví dụ này, cả `findUser` và `findUserInArchive` đều trả về `Optional<User>`. Không cần tự bọc thêm `Optional.of(...)` nếu hàm tra cứu đã trả về Optional.

## 5. Phân biệt `or`, `orElse` và `orElseGet`

Ba phương thức đều có thể xử lý trường hợp Optional rỗng, nhưng kiểu dữ liệu trả về và cách cung cấp fallback khác nhau.

| Phương thức | Supplier/đối số | Kiểu kết quả | Khi nào tính fallback? |
| --- | --- | --- | --- |
| `or(...)` | `Supplier<? extends Optional<? extends T>>` | `Optional<T>` | Chỉ gọi `get()` khi Optional hiện tại rỗng |
| `orElse(value)` | Một giá trị `T` | `T` | Biểu thức đối số được tính trước khi gọi phương thức |
| `orElseGet(supplier)` | `Supplier<? extends T>` | `T` | Chỉ gọi `get()` khi Optional hiện tại rỗng |

### `or`

Dùng khi nguồn thay thế cũng trả về Optional và ta muốn tiếp tục xử lý chuỗi Optional:

```java
Optional<String> value = findPrimary()
    .or(() -> findSecondary())
    .or(() -> findDefault());
```

### `orElse`

Dùng khi đã có sẵn giá trị mặc định:

```java
String value = findPrimary().orElse("default");
```

Đối số của `orElse` được đánh giá trước khi lời gọi `orElse` diễn ra. Nếu biểu thức tạo giá trị mặc định tốn chi phí hoặc có side effect, công việc đó vẫn xảy ra ngay cả khi Optional đang có giá trị.

### `orElseGet`

Dùng khi supplier trả về trực tiếp giá trị cần lấy, thay vì một Optional:

```java
String value = findPrimary().orElseGet(() -> loadDefaultValue());
```

`loadDefaultValue()` chỉ được gọi khi Optional rỗng. Supplier của `orElseGet` có kiểu trả về `T`, còn supplier của `or` phải trả về `Optional`.

### Chọn phương thức nào?

- Cần chuyển sang một hàm tra cứu khác trả về Optional: dùng `or`.
- Cần giá trị mặc định đã có sẵn: dùng `orElse`.
- Cần tạo giá trị mặc định một cách lazy: dùng `orElseGet`.
- Cần giữ kết quả dưới dạng Optional để tiếp tục `map`, `flatMap` hoặc `or`: dùng `or`.

## 6. Phân biệt `or` với `flatMap`

`or` và `flatMap` đều có thể nhận hàm trả về Optional, nhưng chúng giải quyết hai tình huống khác nhau:

- `flatMap` chạy khi Optional **có giá trị** và chuyển giá trị đó qua một hàm có thể trả về Optional khác.
- `or` chạy supplier khi Optional **rỗng** để cung cấp một Optional thay thế.

Ví dụ:

```java
Optional<Address> address = findUser(id)
    .flatMap(User::findAddress)
    .or(() -> findDefaultAddress());
```

Ở đây `flatMap` tìm địa chỉ từ người dùng nếu tìm thấy người dùng. Nếu không có địa chỉ, hoặc không có người dùng, Optional kết quả rỗng và `or` mới gọi `findDefaultAddress()`.

Không dùng `or` để biến đổi giá trị đang có; dùng `map` hoặc `flatMap` cho mục đích đó.

## 7. Ví dụ hoàn chỉnh chạy với Java 9 trở lên

Chương trình sau mô phỏng ba nguồn dữ liệu theo thứ tự ưu tiên. Mỗi nguồn trả về Optional, và `or` chỉ gọi nguồn tiếp theo khi nguồn trước rỗng. Phần cuối còn kiểm tra supplier có được gọi khi Optional đã có giá trị hay không.

```java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class Main {
    private static Optional<String> lookup(Map<String, String> source, String key) {
        return Optional.ofNullable(source.get(key));
    }

    private static Optional<String> resolve(
            String key,
            Map<String, String> primary,
            Map<String, String> secondary,
            Map<String, String> defaults) {
        return lookup(primary, key)
            .or(() -> lookup(secondary, key))
            .or(() -> lookup(defaults, key));
    }

    public static void main(String[] args) {
        Map<String, String> primary = Map.of("alpha", "primary");
        Map<String, String> secondary = Map.of("beta", "secondary");
        Map<String, String> defaults = Map.of("gamma", "default");

        System.out.println(resolve("alpha", primary, secondary, defaults).orElse("missing"));
        System.out.println(resolve("beta", primary, secondary, defaults).orElse("missing"));
        System.out.println(resolve("gamma", primary, secondary, defaults).orElse("missing"));
        System.out.println(resolve("delta", primary, secondary, defaults).orElse("missing"));

        AtomicInteger supplierCalls = new AtomicInteger();
        Optional<String> present = Optional.of("existing").or(() -> {
            supplierCalls.incrementAndGet();
            return Optional.of("fallback");
        });
        System.out.println(present.get());
        System.out.println(supplierCalls.get());
    }
}
```

Lưu thành `Main.java`, biên dịch và chạy với JDK 9 trở lên:

```bash
javac --release 9 Main.java
java Main
```

Stdout chính xác:

```text
primary
secondary
default
missing
existing
0
```

Giải thích:

1. `alpha` có ngay trong nguồn chính nên kết quả là `primary`.
2. `beta` không có trong nguồn chính, supplier của nguồn phụ được gọi và trả về `secondary`.
3. `gamma` chỉ có trong nguồn mặc định nên hai supplier trước đó được gọi trước khi tìm thấy `default`.
4. `delta` không có ở cả ba nguồn nên chuỗi `or` vẫn trả về Optional rỗng; `orElse("missing")` cung cấp chuỗi hiển thị.
5. Optional `present` đã có `existing`; supplier fallback không được gọi, vì vậy bộ đếm vẫn là `0`.

## 8. Quy tắc null, exception và tính lazy

`Optional` được thiết kế để biểu diễn có hoặc không có giá trị, vì vậy các phương thức fallback cần tuân theo hợp đồng rõ ràng:

- Không truyền supplier null cho `or`; lời gọi sẽ ném `NullPointerException`.
- Supplier được gọi khi Optional hiện tại rỗng. Supplier phải trả về một Optional không null.
- Nếu supplier trả về `Optional.empty()`, kết quả vẫn rỗng và một lời gọi `or` tiếp theo có thể tiếp tục thử nguồn khác.
- Nếu supplier trả về null thay vì Optional, `or` ném `NullPointerException`.
- Nếu supplier ném exception, exception được truyền ra ngoài; `or` không tự bắt hoặc chuyển exception thành Optional rỗng.
- Không dùng supplier để sửa đổi nguồn dữ liệu đang được xử lý hoặc tạo side effect khó kiểm soát.

Ví dụ supplier tiếp tục trả về rỗng:

```java
Optional<String> result = Optional.<String>empty()
    .or(Optional::empty)
    .or(() -> Optional.of("last resort"));
```

Kết quả cuối cùng chứa `last resort` vì supplier đầu tiên trả về Optional rỗng, nên bước `or` tiếp theo được thực hiện.

## 9. Lỗi thường gặp

1. **Supplier trả về giá trị thường thay vì Optional.** `or` yêu cầu supplier trả về Optional; nếu chỉ cần trả về `String`, hãy dùng `orElseGet`.
2. **Nhầm `or` với `orElse`.** `or` trả về Optional, còn `orElse` lấy giá trị bên trong hoặc giá trị thay thế.
3. **Nhầm kiểu Supplier.** `or` nhận `Supplier<Optional<T>>` theo dạng tổng quát; `orElseGet` nhận supplier trả về `T`.
4. **Gọi `Optional.of(supplier.get())` khi supplier có thể trả null.** `Optional.of(null)` ném `NullPointerException`; nếu đang chuyển giá trị có thể null thành Optional, dùng `Optional.ofNullable(...)`.
5. **Supplier trả về null.** Với `or`, kết quả supplier phải là một Optional không null; dùng `Optional.empty()` khi không tìm thấy.
6. **Cho rằng supplier luôn được gọi.** Supplier chỉ được thực thi khi Optional hiện tại rỗng; nếu Optional có giá trị, fallback không chạy.
7. **Dùng `or` để biến đổi giá trị đã có.** Dùng `map` hoặc `flatMap` để biến đổi; `or` chỉ cung cấp lựa chọn thay thế khi rỗng.
8. **Đặt công việc tốn chi phí trong đối số `orElse`.** Đối số được tính trước lời gọi; dùng `orElseGet` nếu cần trì hoãn tạo một giá trị thường, hoặc `or` nếu cần trì hoãn một Optional thay thế.
9. **Bắt exception trong mọi supplier rồi trả Optional.empty mà không cân nhắc nghiệp vụ.** Chỉ chuyển lỗi thành trạng thái không có kết quả khi đó thật sự là quy tắc nghiệp vụ; lỗi hệ thống hoặc lỗi lập trình cần được xử lý riêng.

## 10. Ghi nhớ

1. `Optional.or(...)` được bổ sung từ Java 9.
2. `or` nhận `Supplier` trả về Optional và trả về một Optional.
3. Supplier chỉ được gọi khi Optional hiện tại rỗng; supplier truyền vào phải khác null.
4. Supplier phải trả về Optional khác null; có thể trả `Optional.empty()` để cho phép thử nguồn tiếp theo.
5. Nối nhiều lời gọi `or` giúp tạo chuỗi fallback theo thứ tự ưu tiên mà không cần lặp lại `isPresent()`.
6. `orElse` trả về giá trị và nhận đối số được tính trước; `orElseGet` trả về giá trị từ Supplier được gọi lazy; `or` trả về Optional thay thế.
7. Dùng `flatMap` để biến đổi giá trị đang có thành Optional; dùng `or` để tìm lựa chọn thay thế khi không có giá trị.