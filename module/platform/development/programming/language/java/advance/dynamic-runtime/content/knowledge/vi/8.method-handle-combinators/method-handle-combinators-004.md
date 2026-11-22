# 8.4 Biến đổi đầu vào bằng `filterArguments` và đầu ra bằng `filterReturnValue`

**Ngữ cảnh:** Java Advance → dynamic-runtime → 8. Kết hợp lời gọi.

`MethodHandle` không chỉ là một cách gọi phương thức thay cho Reflection. Java cho phép ghép các `MethodHandle` thành **adapter**, nghĩa là tạo một handle có chữ ký phù hợp với dữ liệu phía gọi, tự thực hiện xử lý trước/sau rồi mới gọi handle đích. Hai combinator cơ bản nhất cho việc này là:

- **`MethodHandles.filterArguments(target, pos, filters...)`**: xử lý **đầu vào** trước khi gọi `target`; mỗi filter biến đổi đúng **một** đối số.
- **`MethodHandles.filterReturnValue(target, filter)`**: xử lý **kết quả đầu ra** sau khi `target` chạy; cũng hỗ trợ target trả `void` và filter trả `void`.

Hai API này đặc biệt hữu ích khi kết nối dữ liệu từ JSON/cấu hình/UI vào một hàm nghiệp vụ nhận kiểu chặt chẽ, đổi cách biểu diễn kết quả, hoặc tạo pipeline cho framework mà không cần viết một lớp adapter riêng cho từng trường hợp. Bài này trình bày cơ chế, quy tắc kiểu, thứ tự thực thi, lỗi và chương trình Java 17 kiểm chứng.

## 1. Tư duy bằng `MethodType` và pipeline

Giả sử logic nghiệp vụ là:

```java
static long total(int quantity, long unitCents) {
    return Math.multiplyExact((long) quantity, unitCents);
}
```

Đây là **snippet của phương thức**, chưa phải chương trình chạy độc lập. `MethodType` của target tương ứng:

```text
(int,long)long
```

Nhưng lớp giao diện trả số lượng và đơn giá dưới dạng chuỗi `String`, ví dụ `" 2 "` và `" 1500 "`. Ta muốn API động nhận `(String,String)`, chuyển chuỗi số lượng thành `int`, chuyển chuỗi đơn giá thành `long`, gọi `total` rồi đổi số xu thành chuỗi kết quả.

```text
Dữ liệu từ caller:           (" 2 ", " 1500 ")
                                   |
                      filterArguments(target, 0,
                                      parseQuantity, parsePrice)
                                   |
               (int quantity, long unitCents) = (2, 1500)
                                   |
                          total(2, 1500)
                                   |
                             long = 3000
                                   |
                    filterReturnValue(..., format)
                                   |
                      "total=3000 cents"
```

Ta có ba thành phần chức năng:

| Thành phần | Chữ ký `MethodType` | Vai trò |
| --- | --- | --- |
| `target = total` | `(int,long)long` | Xử lý nghiệp vụ |
| `parseQuantity` | `(String)int` | Đổi đối số số 0 |
| `parsePrice` | `(String)long` | Đổi đối số số 1 |
| `filteredInputs` | `(String,String)long` | Adapter sau khi lọc đầu vào |
| `format` | `(long)String` | Đổi kết quả trả về |
| `pipeline` | `(String,String)String` | Adapter hoàn chỉnh caller sẽ gọi |

**Điểm then chốt:** Các combinator tạo `MethodHandle` **mới** và chữ ký được tính ở lúc ghép. Chúng không sửa khai báo `total(int,long)`, không đổi bytecode của method gốc và không tự chọn một overload khác lúc chạy. Handle gốc vẫn hoạt động với `(int,long)long`.

## 2. `filterArguments`: biến đổi một hoặc nhiều đối số

Chữ ký API:

```java
static MethodHandle filterArguments(
        MethodHandle target, int pos, MethodHandle... filters)
```

Từ trái sang phải, mỗi filter không null thuộc phần tử thứ `i` trong `filters` sẽ áp dụng cho **tham số `pos + i`** của `target`. `pos` bắt đầu từ **0**. Những đối số không nằm trong đoạn filter được truyền nguyên vẹn tới target.

### Quy tắc tương thích kiểu chính xác

Nếu target có tham số tại vị trí `k` là kiểu `A`, filter tại vị trí đó **phải có đúng một tham số** và trả về **chính xác kiểu `A`**:

```text
target: (P0, ..., A, ..., Pn) -> R
filter:             V -> A
adapter: (P0, ..., V, ..., Pn) -> R
```

`V` là kiểu input mà phía caller sẽ truyền cho adapter. Kiểu trả về của filter **phải đồng nhất** với kiểu tham số `A` của target theo `Class<?>`, không chỉ "có thể convert bằng Java". Ví dụ:

| Tham số của target | Filter | Kết quả |
| --- | --- | --- |
| `int` | `(String)int` | Hợp lệ, adapter nhận `String` ở vị trí đó |
| `long` | `(String)long` | Hợp lệ |
| `Number` | `(String)Number` | Hợp lệ |
| `long` | `(String)int` | **Không hợp lệ khi ghép**, dù `int` có thể widen thành `long` |
| `Integer` | `(String)int` | **Không hợp lệ khi ghép**, dù `int` có thể boxing thành `Integer` |
| `String` | `(String,String)String` | **Không hợp lệ**, filter có hai tham số thay vì một |
| `int` | `()int` | **Không hợp lệ**, filter không có tham số |

Như vậy `filterArguments` **không tự thực hiện `asType`**, không tự widening, boxing hoặc đổi wrapper để sửa chữ ký filter sai. Nếu bạn thực sự muốn một chuyển đổi hợp lệ bằng cơ chế `asType`, hãy thích nghi **filter** có chủ đích trước khi truyền nó vào combinator; tốt hơn nữa là dùng filter có kiểu khớp trực tiếp để làm rõ hợp đồng.

### Vị trí `pos` và số lượng filter

Ví dụ target `(int,long)long`:

```java
// parseQuantity: (String)int
// parsePrice:    (String)long
MethodHandle both = MethodHandles.filterArguments(
        target, 0, parseQuantity, parsePrice);
// both.type(): (String,String)long

MethodHandle onlyPrice = MethodHandles.filterArguments(
        target, 1, parsePrice);
// onlyPrice.type(): (int,String)long
```

Hai đoạn là **snippet** khi đã có ba biến `MethodHandle` được tạo hợp lệ. Tham số đầu `pos=1` nghĩa là "bắt đầu tại đối số thứ hai", không phải "filter thứ hai". `pos + filters.length` không được vượt `target.type().parameterCount()`; nếu vượt sẽ ném `IllegalArgumentException` ngay khi dựng adapter.

### Filter `null` khác đối số `null`

Một **phần tử `null` trong mảng `filters`** biểu thị **identity filter**: đối số tương ứng giữ nguyên, không cần gọi một handle để xử lý. Ví dụ:

```java
MethodHandle keepQuantity = MethodHandles.filterArguments(
        target, 0, (MethodHandle) null, parsePrice);
// (int,String)long: đối số 0 giữ nguyên int, đối số 1 đổi String -> long
```

Nếu mọi phần tử filter đều `null` hoặc không truyền filter, API có thể trả nguyên `target`. Tuy nhiên, **mảng `filters` của chính lời gọi không được `null`**; ví dụ `(MethodHandle[]) null` dẫn đến `NullPointerException`. Cũng đừng nhầm với **giá trị đối số `null` lúc gọi pipeline**: nếu `parsePrice` nhận `String` mà code bên trong gọi `raw.strip()`, giá trị `null` vẫn có thể gây `NullPointerException`. Combinator không tự thay thế, validate hay xử lý `null`.

### Thứ tự thực thi và side effects

Javadoc Java 17 bảo đảm các input filter chạy **từ trái sang phải**, sau đó mới gọi target:

```text
filter[0](argument[pos])
filter[1](argument[pos+1])
...
target(all filtered and untouched arguments)
```

Nếu filter ở trước ném exception thì filter ở sau và target **không chạy**. Vì thế khi một filter thực hiện validation, đọc cấu hình hay ghi log, thứ tự filter có ý nghĩa. Ưu tiên pure functions để việc ghép dễ hiểu; đừng dựa vào side effects không cần thiết.

**Giới hạn quan trọng:** `filterArguments` chỉ thay **kiểu từng vị trí**, không tự thêm/xóa số tham số và không truyền đồng thời nhiều tham số vào một filter. Nếu một phép chuẩn hóa cần **hai** input để sinh **một** giá trị, xem `collectArguments` hoặc `foldArguments` theo chữ ký phù hợp.

## 3. `filterReturnValue`: hậu xử lý kết quả target

Chữ ký:

```java
static MethodHandle filterReturnValue(
        MethodHandle target, MethodHandle filter)
```

Nếu target trả một giá trị kiểu `R`, filter **phải có đúng một tham số kiểu `R`**, rồi có thể trả một kiểu mới `V`:

```text
target:  (A0, A1, ..., An) -> R
filter:                      R -> V
adapter: (A0, A1, ..., An) -> V
```

Ví dụ target `(int,long)long` và `format` có kiểu `(long)String`, kết quả:

```text
filterReturnValue(target, format) : (int,long)String
```

Khi caller invoke adapter, **target chạy trước**, lấy kết quả và truyền nó làm một đối số của filter; giá trị trả ra từ filter sẽ là kết quả cuối của adapter. `filterReturnValue` **không đổi danh sách kiểu tham số của target**.

Tương tự `filterArguments`, kiểu tham số của output filter phải **khớp chính xác** kiểu trả về target. Ví dụ target trả `long` mà filter nhận `String` hoặc `int` sẽ ném `IllegalArgumentException` **ở bước ghép**, không tự parse, unbox hay widen.

### Hai trường hợp đặc biệt liên quan `void`

**Trường hợp A — target trả `void`:** Không có giá trị nào để đưa vào output filter. Khi đó filter **phải nhận 0 tham số**, có thể trả về kiểu mới:

```text
target:  (long)void
filter:  ()String
adapter: (long)String
```

Nghĩa là gọi target để thực hiện công việc, sau đó gọi một phương thức không đối số và trả kết quả của phương thức đó. Đây không phải cơ chế "nhận `null` từ target `void`"; filter **không nhận tham số nào**.

**Trường hợp B — filter trả `void`:** Target có giá trị `R`, filter nhận `R` để quan sát/log/gửi kết quả nhưng không trả giá trị mới:

```text
target:  (int,long)long
filter:  (long)void
adapter: (int,long)void
```

Trường hợp này có thể hữu ích cho logging/auditing khi phía caller chỉ cần side effect. Lưu ý khi làm vậy, caller sẽ **mất** giá trị trả về gốc qua adapter, dù target vẫn tính nó bên trong.

Với cả hai trường hợp, nếu target ném exception thì output filter **không chạy**. Nếu output filter ném exception, exception đó được truyền tới caller; API không tự bọc kiểu `InvocationTargetException` như `Method.invoke` trong Core Reflection.

## 4. Ghép hai chiều: xử lý input trước, output sau

Từ các `MethodHandle` thành phần:

```java
MethodHandle filteredInputs = MethodHandles.filterArguments(
        target, 0, parseQuantity, parsePrice);

MethodHandle pipeline = MethodHandles.filterReturnValue(
        filteredInputs, format);
```

Về mặt ý nghĩa, `pipeline` tương đương logic sau (đây là **pseudo-code** minh họa, không phải đoạn Java độc lập):

```java
String pipeline(String quantityText, String priceText) {
    int quantity = parseQuantity(quantityText);
    long price = parsePrice(priceText);
    long cents = total(quantity, price);
    return format(cents);
}
```

Chữ ký adapter cuối là `(String,String)String`. Caller không cần biết target yêu cầu `int` và `long` hay format trả kiểu gì, miễn là giao kèo cuối cùng `MethodType` đã được thiết kế đúng.

Sự kết hợp có thể **lồng nhiều lớp**, ví dụ `filterReturnValue(filterArguments(...), format)`. Tuy nhiên, mỗi lớp vẫn có kiểm tra kiểu độc lập, nên hãy in `.type()` ngay sau mỗi bước khi debug. Điều này nhanh hơn việc đoán tại sao `invokeExact` thất bại.

## 5. Chương trình Java 17 hoàn chỉnh: kiểm chứng input filter, output filter, `void` và lỗi

Tạo file **`FilterPipelineDemo.java`** trong một thư mục riêng. Chương trình không cần dependency ngoài JDK; dùng `--release 17` để buộc biên dịch theo API/ngôn ngữ Java 17.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class FilterPipelineDemo {
    static int parseQuantity(String raw) {
        System.out.println("input.quantity");
        int value = Integer.parseInt(raw.strip());
        if (value <= 0) throw new IllegalArgumentException("quantity must be positive");
        return value;
    }

    static long parsePrice(String raw) {
        System.out.println("input.price");
        long value = Long.parseLong(raw.strip());
        if (value < 0) throw new IllegalArgumentException("price cannot be negative");
        return value;
    }

    static long total(int quantity, long unitCents) {
        System.out.println("target.total");
        return Math.multiplyExact((long) quantity, unitCents);
    }

    static String format(long cents) {
        System.out.println("output.format");
        return "total=" + cents + " cents";
    }

    static void report(long cents) {
        System.out.println("target.report=" + cents);
    }

    static String afterVoid() {
        System.out.println("output.afterVoid");
        return "reported";
    }

    static void audit(long cents) {
        System.out.println("output.audit=" + cents);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle target = lookup.findStatic(FilterPipelineDemo.class, "total",
                MethodType.methodType(long.class, int.class, long.class));
        MethodHandle quantity = lookup.findStatic(FilterPipelineDemo.class, "parseQuantity",
                MethodType.methodType(int.class, String.class));
        MethodHandle price = lookup.findStatic(FilterPipelineDemo.class, "parsePrice",
                MethodType.methodType(long.class, String.class));
        MethodHandle formatter = lookup.findStatic(FilterPipelineDemo.class, "format",
                MethodType.methodType(String.class, long.class));

        MethodHandle filteredInputs = MethodHandles.filterArguments(target, 0, quantity, price);
        MethodHandle pipeline = MethodHandles.filterReturnValue(filteredInputs, formatter);
        System.out.println("target.type=" + target.type());
        System.out.println("input.type=" + filteredInputs.type());
        System.out.println("pipeline.type=" + pipeline.type());
        System.out.println("pipeline.result=" + (String) pipeline.invokeExact(" 2 ", " 1500 "));

        MethodHandle priceOnly = MethodHandles.filterArguments(target, 1, price);
        System.out.println("priceOnly.type=" + priceOnly.type());
        System.out.println("priceOnly.result=" + (long) priceOnly.invokeExact(3, "7"));

        MethodHandle keepFirst = MethodHandles.filterArguments(target, 0,
                (MethodHandle) null, price);
        System.out.println("null-filter.type=" + keepFirst.type());

        try {
            MethodHandles.filterArguments(target, 0, price);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrong-input-filter=IllegalArgumentException");
        }

        try {
            MethodHandles.filterReturnValue(target, quantity);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrong-output-filter=IllegalArgumentException");
        }

        try {
            String unused = (String) pipeline.invokeExact("not-a-number", "1");
        } catch (NumberFormatException expected) {
            System.out.println("parse-failure=NumberFormatException");
        }

        MethodHandle report = lookup.findStatic(FilterPipelineDemo.class, "report",
                MethodType.methodType(void.class, long.class));
        MethodHandle afterVoid = lookup.findStatic(FilterPipelineDemo.class, "afterVoid",
                MethodType.methodType(String.class));
        MethodHandle voidTarget = MethodHandles.filterReturnValue(report, afterVoid);
        System.out.println("voidTarget.type=" + voidTarget.type());
        System.out.println("voidTarget.result=" + (String) voidTarget.invokeExact(5L));

        MethodHandle audit = lookup.findStatic(FilterPipelineDemo.class, "audit",
                MethodType.methodType(void.class, long.class));
        MethodHandle voidFilter = MethodHandles.filterReturnValue(target, audit);
        System.out.println("voidFilter.type=" + voidFilter.type());
        voidFilter.invokeExact(2, 3L);
    }
}
```

Từ thư mục chứa file vừa tạo:

```bash
javac --release 17 -encoding UTF-8 FilterPipelineDemo.java
java FilterPipelineDemo
```

**Stdout chính xác:**

```text
target.type=(int,long)long
input.type=(String,String)long
pipeline.type=(String,String)String
input.quantity
input.price
target.total
output.format
pipeline.result=total=3000 cents
priceOnly.type=(int,String)long
input.price
target.total
priceOnly.result=21
null-filter.type=(int,String)long
wrong-input-filter=IllegalArgumentException
wrong-output-filter=IllegalArgumentException
input.quantity
parse-failure=NumberFormatException
voidTarget.type=(long)String
target.report=5
output.afterVoid
voidTarget.result=reported
voidFilter.type=(int,long)void
target.total
output.audit=6
```

### Phân tích theo thứ tự thực thi

1. `target.type()` là `(int,long)long`. `filteredInputs.type()` là `(String,String)long` sau khi lọc hai vị trí; `pipeline.type()` là `(String,String)String` sau khi lọc kết quả.
2. Khi gọi `pipeline.invokeExact(" 2 ", " 1500 ")`, log ghi **`input.quantity` rồi `input.price`**. Hai filter chạy trái sang phải; `strip()` loại khoảng trắng, `Integer.parseInt`/`Long.parseLong` đổi kiểu; target nhân `2 * 1500` thành `3000`.
3. `target.total` xuất hiện **trước** `output.format`. Formatter đổi `long 3000` thành chuỗi `"total=3000 cents"` và adapter trả chuỗi đó.
4. `priceOnly` dùng `pos=1`, không thay kiểu tham số đầu. Nó có chữ ký `(int,String)long`; lời gọi `priceOnly.invokeExact(3, "7")` thực thi filter đơn giá, rồi cho kết quả `21`.
5. `keepFirst` dùng một filter `null` để giữ nguyên `int` ở vị trí đầu; đối số thứ hai vẫn được đổi `String → long`. Type của nó cũng là `(int,String)long`.
6. `filterArguments(target, 0, price)` cố dùng filter trả `long` cho tham số đầu target kiểu `int`. Adapter bị từ chối **ngay lúc dựng** bằng `IllegalArgumentException`.
7. `filterReturnValue(target, quantity)` cũng sai vì `target` trả `long` nhưng `quantity` nhận `String`. Nó cũng lỗi ngay lúc dựng.
8. Với `"not-a-number"`, `parseQuantity` được gọi trước rồi ném `NumberFormatException`. Vì thế **không có** log `input.price`, `target.total` hay `output.format` ở lượt này. Exception đi thẳng về caller qua `invokeExact`.
9. `voidTarget` biến `(long)void` thành `(long)String`. Log cho thấy target `report` chạy, sau đó filter không tham số `afterVoid` chạy; kết quả cuối là `"reported"`.
10. `voidFilter` biến `(int,long)long` thành `(int,long)void`. Target vẫn thực thi để tính `6`, rồi `audit(long)` nhận `6` và log ra, nhưng caller không nhận kết quả `long` nữa.

Chương trình dùng các dòng `(String) pipeline.invokeExact(...)` và `(long) priceOnly.invokeExact(...)` có chủ đích: `invokeExact` yêu cầu **chữ ký tĩnh tại call site** khớp chính xác return type và parameter types của handle. Nếu muốn gọi linh hoạt hơn, có thể cân nhắc `invoke` (cho một số chuyển đổi hợp lệ) hoặc `asType`, nhưng đó là một cơ chế thích nghi kiểu **khác** với chính hai filter đang học.

## 6. Quy tắc kiểu chi tiết và cách chọn combinator

### 6.1 Input filter phải là unary, output filter nhìn đúng kết quả

Ký hiệu:

```text
T target(P0, P1, ..., Pn)
Pj filter_j(Vj)
U resultFilter(T)

filterArguments  -> adapter(..., Vj, ...) returns T
filterReturnValue -> adapter(P0, ..., Pn) returns U
```

Nếu `resultFilter` chỉ nhận `Object` nhưng target trả `String`, `filterReturnValue` **không tự widening reference `String → Object`** để chấp nhận nó. Cần filter có đúng kiểu `(String)U` hoặc chủ động `asType` khi thích hợp.

Tương tự, target tham số `long` và filter trả `int` không hợp lệ với `filterArguments`, dù gọi phương thức Java thường cho phép truyền `int` vào `long`. Combinator được định nghĩa dựa trên **`MethodType` chính xác**, không thực hiện Java overload resolution như trình biên dịch.

### 6.2 Filter đổi đầu vào hay đổi đầu ra?

| Nhu cầu | API thích hợp | Ví dụ |
| --- | --- | --- |
| Đổi một đối số trước khi target chạy | `filterArguments` | `String → int` trước `total(int,...)` |
| Đổi nhiều đối số liền kề, mỗi cái bằng **một filter unary** | `filterArguments(target, pos, f1, f2)` | `(String,String) → (int,long)` |
| Giữ một vị trí không đổi giữa các filter | Phần tử `null` trong `filters` | `(int,String) → (int,long)` |
| Đổi kiểu của kết quả | `filterReturnValue` | `long → String` |
| Chỉ chạy tác vụ sau target `void` | `filterReturnValue` với filter `()R` | `(long)void → (long)String` |
| Quan sát kết quả rồi bỏ giá trị cuối | `filterReturnValue` với filter `(T)void` | `(int,long)long → (int,long)void` |
| Một phép xử lý dùng **nhiều** đầu vào cùng lúc | `collectArguments` / `foldArguments` | `(String,String) → DomainObject` |
| Đổi chữ ký bằng các chuyển đổi JVM được phép | `MethodHandle.asType` (kiểm tra quy tắc riêng) | Thích nghi một handle theo `MethodType` khác |
| Thêm đối số giả hoặc bind sẵn hằng số | `dropArguments` / `insertArguments` | Bỏ qua một tham số hoặc cố định đơn giá |

Đừng chọn `filterArguments` để lọc toàn bộ danh sách thành một `List`; API này giữ số vị trí và yêu cầu từng filter unary. Cũng đừng dùng `filterReturnValue` để thử chèn tham số bổ sung cho target; nó chỉ thay kiểu kết quả và thực hiện hậu xử lý.

### 6.3 Chuyển đổi reference và primitive là trách nhiệm của filter

Ví dụ chuẩn hóa dữ liệu đầu vào:

```java
static int parsePositiveQuantity(String raw) {
    int n = Integer.parseInt(raw.strip());
    if (n <= 0) throw new IllegalArgumentException("Quantity must be > 0");
    return n;
}
```

Đây là **snippet phương thức**, không phải chương trình độc lập. Nếu `raw` là `null`, đoạn code gây `NullPointerException`; nếu chuỗi không phải số, gây `NumberFormatException`; nếu số không dương, gây `IllegalArgumentException`. Combinator không tự thay nghĩa của ba lỗi ấy. Với đầu vào tùy ý từ người dùng, cần thiết kế validation, thông báo lỗi và xử lý `null` phù hợp ở tầng ứng dụng.

Có thể xây nhiều bộ lọc cùng kiểu input như `String -> int` (parse và validate) hoặc `String -> String` (trim, chuẩn hóa mã); nhưng nếu pipeline chứa nhiều bước riêng rẽ cho **cùng một đối số**, phải **ghép các filter** thành một handle unary có kiểu đúng trước khi đưa vào `filterArguments`. Không thể đặt nhiều filter liên tiếp cùng `pos` và mong chúng tự tạo chuỗi xử lý cho một tham số.

## 7. Side effects, exceptions và kiểm soát giá trị trả về

### 7.1 Nếu một mắt xích lỗi, những bước còn lại có chạy không?

| Nơi xảy ra lỗi | Những bước có thể đã chạy | Bước không chạy |
| --- | --- | --- |
| Filter đầu vào đầu tiên ném exception | Chỉ filter đó (và mã nó đã thực hiện) | Filter đầu vào sau, target, output filter |
| Filter đầu vào thứ hai ném exception | Các filter trước và filter đang lỗi | Target và output filter |
| Target ném exception | Tất cả input filter đã hoàn tất, target đã bắt đầu | Output filter |
| Output filter ném exception | Input filters và target đã hoàn tất, output filter đã bắt đầu | Không có bước hậu xử lý tiếp theo trong chính adapter đó |
| Sai chữ ký khi **dựng** adapter | Không chạy filter/target | Toàn pipeline chưa được tạo |

Vì các input filter chạy trái sang phải, có thể thấy side effects của filter đầu tiên dù filter thứ hai thất bại. Điều này quan trọng với giao dịch, ghi file, thanh toán hoặc các xử lý không idempotent: không nên coi cả pipeline tự động là một transaction atomic chỉ vì nó được biểu diễn bằng một `MethodHandle`.

### 7.2 Phân biệt lỗi cấu hình và lỗi khi gọi

| Lỗi | Xuất hiện ở giai đoạn nào? | Cách kiểm tra |
| --- | --- | --- |
| `IllegalArgumentException` | Dựng `filterArguments`/`filterReturnValue` với chữ ký filter sai, `pos` vượt phạm vi, số filter không khớp | So sánh `target.type()`, `filter.type()`, `pos` trước khi ghép |
| `NullPointerException` | Truyền target/filter `null` không được phép, hoặc filter thực thi dereference một input `null` | Phân biệt lỗi **tạo adapter** và lỗi từ logic filter |
| `WrongMethodTypeException` | `invokeExact` có chữ ký call-site không khớp handle cuối | In `pipeline.type()` và xét kiểu tĩnh/return cast của lệnh gọi |
| `NumberFormatException` | Một filter parse chuỗi không hợp lệ | Validate và phân loại lỗi dữ liệu ở ranh giới input |
| `ArithmeticException` | Ví dụ target dùng `Math.multiplyExact` bị tràn số | Kiểm tra miền đầu vào, precision và overflow |
| `IllegalAccessException` / `NoSuchMethodException` | Tạo handle gốc bằng `Lookup.findStatic`/`findVirtual` | Xét quyền của `Lookup` và `MethodType` chính xác |
| Exception do target/filter ném | Trong lúc pipeline chạy | Exception được đưa tới caller của handle; không mặc nhiên bọc trong `InvocationTargetException` |

**Bẫy thường gặp:** Khi gọi `Method.invoke` trong Java Reflection, exception do method đích ném thường được bọc bằng `InvocationTargetException`. Khi `MethodHandle.invokeExact` chạy, exception từ target hoặc filter thường **đi thẳng** tới caller. Vì vậy không sao chép máy móc một `catch (InvocationTargetException)` từ code Reflection sang code MethodHandle.

### 7.3 Nullability và các kiểu đầu vào

Một filter `(String)int` có thể nhận `null` ở mức chữ ký vì `String` là reference, nhưng **code của filter** quyết định hành vi. Nếu return type của filter là primitive `int`, filter không thể trả `null`; nó cần trả một giá trị `int` hoặc ném exception. `filterReturnValue` cũng vậy: filter nhận `long` primitive không thể nhận `null` vì target trả primitive; còn filter nhận kiểu reference có thể xử lý `null` theo hợp đồng.

Nên ghi rõ null policy thay vì dựa vào "reflection tự chuyển `null` thành mặc định". Nếu cần default, tạo một filter chuyển `null` thành giá trị hợp lệ; nếu cần báo lỗi, check `Objects.requireNonNull` với thông báo rõ ràng.

## 8. Hiệu năng, readability và ranh giới quyền truy cập

`filterArguments` và `filterReturnValue` tạo các adapter có cấu trúc rõ ràng. JVM/JIT có thể tối ưu các chuỗi MethodHandle ổn định, nhưng **không bảo đảm mọi pipeline nhanh hơn code Java thông thường**. Tối ưu cần đo theo workload thực tế, xem kích thước pipeline, sự ổn định kiểu call-site, việc phân bổ bộ nhớ và độ đắt của filter. Không lập luận dựa trên một số nanosecond tùy tiện.

Một số nguyên tắc thiết kế:

1. **Xây adapter một lần, tái sử dụng nếu cấu hình ổn định.** Không tạo lại tất cả các handle cho mỗi bản ghi nếu cùng hợp đồng.
2. **Đặt tên và phân loại từng bước.** Ví dụ `parseQuantity`, `parsePrice`, `total`, `format` rõ nghĩa hơn một chuỗi filter ẩn danh khó debug.
3. **Kiểm tra `MethodType` tại ranh giới.** Sau mỗi bước ghép, gọi `.type()` và kiểm tra với hợp đồng mong đợi trong test.
4. **Tách validation với side effects nguy hiểm.** Input filter có thể bị gọi trước khi phát hiện lỗi ở input filter tiếp theo.
5. **Không biến MethodHandle thành cách vượt visibility.** `Lookup.findStatic`/`findVirtual` vẫn kiểm tra quyền khi lấy handle; `filterArguments` và `filterReturnValue` không tự cấp `private` hoặc sửa module `exports`/`opens`.
6. **Bảo đảm thread-safety của code bên trong filter.** Handle có thể dùng lại trên nhiều thread, nhưng filter truy cập mutable state hoặc formatter không thread-safe vẫn cần thiết kế đồng bộ riêng.
7. **Không nhầm adapter với validation framework đầy đủ.** Những filter này chỉ diễn tả biến đổi; hợp đồng nghiệp vụ và báo lỗi cho người dùng vẫn thuộc trách nhiệm code của ứng dụng.

**Lưu ý về varargs:** Kết quả của `filterArguments` và `filterReturnValue` **không giữ tính variable-arity** của target. Nếu trước đó một method handle là varargs collector, adapter sinh ra có fixed arity; nếu thật sự cần varargs collector ở API cuối, hãy đánh giá `asVarargsCollector` theo chữ ký cuối cùng. Không dựa vào `...` trong source của phương thức Java để suy ra việc combinator tự sắp xếp lại số đối số.

## 9. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| "`filterArguments` chạy sau target vì tên nó có `Arguments`." | Nó chạy **trước** target để chuẩn bị đối số. |
| "`filterReturnValue` đổi tất cả tham số input." | Nó chỉ hậu xử lý return; input của target giữ nguyên. |
| "Filter nhận `String` và trả `int` có thể đi thẳng vào tham số `long`." | Không; return type filter phải **đúng `long`** (hoặc phải thích nghi filter trước). |
| "`pos=1` lọc phần tử đầu tiên." | Chỉ số bắt đầu 0; `pos=1` lọc đối số thứ hai của target. |
| "Thêm hai filter vào cùng vị trí nghĩa là hai bước nối tiếp cho một input." | Mỗi phần tử `filters` áp dụng **một vị trí liên tiếp khác nhau** của target. |
| "Filter `null` có nghĩa khi invoke truyền đối số `null`." | Filter `null` là **identity**; giá trị đầu vào null là một khái niệm riêng. |
| "Target trả `void` thì `filterReturnValue` bất hợp lệ." | Có thể dùng filter không tham số `()R` chạy sau target. |
| "Output filter bắt buộc phải trả giá trị." | Filter có thể trả `void`, tạo adapter trả `void`. |
| "Filter thất bại thì output filter vẫn chạy để cleanup." | Không; nếu pipeline thất bại trước bước hậu xử lý, output filter **không được gọi**. |
| "Thêm filter tự mở quyền để gọi private method." | Không; access checks của `Lookup` vẫn áp dụng khi tạo target/filter handle. |
| "`invokeExact` luôn tự boxing hoặc đổi kiểu giống `Method.invoke`." | Nó yêu cầu chữ ký tĩnh của call-site khớp chính xác kiểu handle. |
| "Ghép filter luôn giữ varargs collector." | Các adapter này có fixed arity; varargs cần xử lý riêng. |

## 10. Tự kiểm tra và luyện tập

**Câu 1.** `target` có kiểu `(int,long)double`, còn `f0` là `(String)int` và `f1` là `(String)long`. Chữ ký của `filterArguments(target, 0, f0, f1)` là gì?

**Đáp án:** `(String,String)double`. Hai kiểu tham số được thay tại vị trí 0 và 1; kiểu trả về `double` không đổi.

**Câu 2.** Với cùng target, `filterArguments(target, 1, f1)` có chữ ký gì?

**Đáp án:** `(int,String)double` vì chỉ vị trí 1 chuyển từ `long` sang `String`.

**Câu 3.** Target `(int)long` và filter `(String)int`: có thể dùng `filterReturnValue(target, filter)` không?

**Đáp án:** Không. Output filter phải nhận `long` vì target trả `long`; filter được nêu nhận `String`.

**Câu 4.** Target `(int)void`, filter `()String`: có thể dùng `filterReturnValue` không? Kiểu adapter là gì?

**Đáp án:** Có. Filter không nhận tham số và chạy sau khi target trả về; adapter là `(int)String`.

**Câu 5.** Target `(String)String`, filter hậu xử lý `(String)void`: kiểu adapter là gì?

**Đáp án:** `(String)void`. Filter nhận kết quả `String` rồi không trả giá trị cho caller.

**Câu 6.** Có ba input filters ở vị trí 0, 1, 2. Filter thứ hai ném `IllegalArgumentException`. Filter thứ ba và target có chạy không?

**Đáp án:** Không. Filter thứ nhất đã chạy, filter thứ hai thất bại, thực thi dừng và truyền exception về caller.

**Câu 7.** Target có tham số `long`, filter `(String)int`. Gọi `filterArguments` báo `IllegalArgumentException` dù Java có widening `int → long`. Vì sao?

**Đáp án:** Combinator yêu cầu **return type của filter bằng chính parameter type của target**; nó không thực hiện implicit widening. Sửa filter thành `(String)long` hoặc thích nghi hợp lệ một cách tường minh.

**Câu 8.** `filterArguments(target, 0, null, f1)` khác `filterArguments(target, 0, f0, f1)` thế nào?

**Đáp án:** Ở dạng đầu, vị trí 0 được giữ nguyên và chỉ vị trí 1 được lọc; ở dạng sau, cả hai đối số đều được lọc. `null` trong mảng filters biểu diễn identity, không phải input null.

**Câu 9.** Khi target trả `long` và `format` nhận `long`, code gọi `(String) pipeline.invokeExact(...)` vẫn báo `WrongMethodTypeException`. Cần kiểm tra gì?

**Đáp án:** Kiểu cuối `pipeline.type()` và kiểu tĩnh của **mọi đối số** tại lệnh gọi, cộng với cast/return context của `invokeExact`. Lỗi có thể do call-site truyền `int` thay `long`, hoặc đặt return context khác `String` dù filter đúng.

**Câu 10.** Khi cần filter xử lý cả `quantity` và `unitPrice` để tạo một `Order`, `filterArguments` có làm được bằng một filter `(String,String)Order` không?

**Đáp án:** Không trực tiếp. `filterArguments` yêu cầu mỗi filter **unary** cho một tham số cụ thể. Xem `collectArguments` hoặc `foldArguments` để ghép nhiều input.

**Câu 11.** Có thể dùng `filterReturnValue` làm "finally block" chạy ngay cả khi target ném exception không?

**Đáp án:** Không. Nếu target ném exception, output filter không chạy. Cleanup theo cả nhánh thành công và thất bại cần cơ chế khác thích hợp, ví dụ `tryFinally` trong `MethodHandles` hoặc xử lý lỗi ở lớp ứng dụng.

**Câu 12.** Nếu sau khi tạo adapter, ta sửa biến cục bộ `target` thành handle khác, adapter đã tạo có tự đổi đích không?

**Đáp án:** Không. Adapter đã nắm giữ tham chiếu đến target handle được truyền lúc tạo; gán lại biến Java không sửa cấu trúc adapter đó.

## 11. Ghi nhớ

- `filterArguments`: **đầu vào → unary filters trái sang phải → target**, có thể thay kiểu các đối số, nhưng không đổi return type và không thay số vị trí.
- `filterReturnValue`: **target → output filter → caller**, giữ danh sách tham số, có thể thay kiểu return; hỗ trợ target `void` và filter `void` theo chữ ký riêng.
- **Kiểu phải khớp chính xác:** filter đầu vào trả đúng kiểu tham số target; filter đầu ra nhận đúng kiểu kết quả target. Không có overload resolution hay widening ngầm ở bước ghép.
- **Dùng `MethodType` để kiểm soát:** `target.type()`, `filter.type()`, `adapter.type()` giúp xác định lỗi từ đầu.
- **Exception truyền theo chuỗi thực thi:** filter/target ném exception thì bước phía sau dừng; khi gọi qua `MethodHandle` không tự bọc `InvocationTargetException`.
- **`null` trong `filters` là identity filter**, không phải quy tắc xử lý input `null`.
- **Ghép đúng công cụ:** biến đổi từng input bằng `filterArguments`, hậu xử lý output bằng `filterReturnValue`; dùng `collectArguments`/`foldArguments` cho filter cần nhiều input.
- **Giữ quyền truy cập đúng phạm vi:** combinator xử lý call flow, không cấp quyền để truy cập class/method ngoài `Lookup` hiện có.

### Tài liệu chính thức (Java 17)

- [Oracle Java SE 17 — `MethodHandles.filterArguments` và `filterReturnValue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Oracle Java SE 17 — `MethodHandle.invokeExact` / `asType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Oracle Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)