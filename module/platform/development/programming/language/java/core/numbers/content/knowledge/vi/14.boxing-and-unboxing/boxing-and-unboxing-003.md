# NullPointerException khi unbox giá trị null trong Java

Trong Java, **unboxing** là thao tác chuyển đối tượng wrapper, chẳng hạn `Integer`, `Long`, `Double`, thành giá trị nguyên thủy tương ứng `int`, `long`, `double`. Khi đối tượng wrapper là `null`, **không có giá trị nguyên thủy nào để lấy ra**. Nếu Java thực hiện unboxing trên giá trị đó, chương trình ném **`NullPointerException` (NPE)** tại thời điểm chạy.

Ví dụ ngắn nhất:

```java
Integer quantity = null;
int count = quantity; // NullPointerException khi chạy.
```

Dòng gán nhìn như một phép chuyển kiểu tự động hợp lệ. Nó **biên dịch thành công**, nhưng khi chạy tương đương về ý nghĩa với việc gọi phương thức lấy giá trị của wrapper, chẳng hạn `quantity.intValue()`; lời gọi đó không thực hiện được trên tham chiếu `null`.

Điểm khó của bài này là **unboxing thường diễn ra ngầm**: không cần viết `intValue()`; các toán tử `+`, `++`, `==`, toán tử ba ngôi, phép truyền tham số hoặc việc lấy dữ liệu từ collection đều có thể kích hoạt nó.

Bài học thuộc phần **Boxing và unboxing** trong **Java core – numbers**. Mục tiêu là hiểu chính xác **khi nào xảy ra unboxing**, vì sao NPE xuất hiện, cách phân biệt dữ liệu thiếu với số 0 và cách thiết kế API an toàn.

## 1. Boxing, unboxing và sự khác biệt giữa primitive với wrapper

| Primitive | Wrapper tương ứng | Có thể bằng `null`? | Ví dụ |
| --- | --- | --- | --- |
| `byte` | `Byte` | Primitive: không; wrapper: có | `Byte b = null;` |
| `short` | `Short` | Primitive: không; wrapper: có | `Short s = null;` |
| `int` | `Integer` | Primitive: không; wrapper: có | `Integer n = null;` |
| `long` | `Long` | Primitive: không; wrapper: có | `Long n = null;` |
| `float` | `Float` | Primitive: không; wrapper: có | `Float f = null;` |
| `double` | `Double` | Primitive: không; wrapper: có | `Double d = null;` |
| `char` | `Character` | Primitive: không; wrapper: có | `Character c = null;` |
| `boolean` | `Boolean` | Primitive: không; wrapper: có | `Boolean b = null;` |

`Integer` không chỉ là tên khác của `int`:

- Biến `int` lưu một giá trị nguyên; nó không thể có giá trị `null`.
- Biến `Integer` là một **tham chiếu đến đối tượng**. Tham chiếu này có thể là `null`.
- **Boxing** chuyển một giá trị nguyên thủy thành wrapper, ví dụ `Integer boxed = 7;`.
- **Unboxing** lấy giá trị nguyên thủy từ wrapper, ví dụ `int value = boxed;`.
- Boxing một primitive hợp lệ không tạo ra `null`, nhưng wrapper nhận từ tham số, cơ sở dữ liệu, map hoặc DTO có thể là `null`.

```java
int count = 7;
Integer boxed = count;     // Autoboxing.
int unboxed = boxed;       // Auto-unboxing, an toàn vì boxed khác null.
```

So sánh với:

```java
Integer boxed = null;
int unboxed = boxed;       // NPE tại lúc unboxing.
```

**NPE không phải lỗi do số vượt giới hạn** và không liên quan đến `Integer.MIN_VALUE`, tràn số hay precision. Đây là lỗi **truy cập giá trị của một tham chiếu không trỏ tới đối tượng**.

### 1.1. Tại sao trình biên dịch không từ chối?

Kiểu tĩnh của `boxed` là `Integer`, vốn hợp lệ để chuyển sang `int`. Trình biên dịch không thể mặc định mọi `Integer` đều khác `null` vào lúc chạy. Ví dụ, giá trị có thể đến từ tham số, kết quả hàm hoặc một nhánh điều kiện.

```java
static int consume(Integer value) {
    return value; // Biên dịch được; chỉ ném NPE nếu value là null lúc chạy.
}
```

Java không tự chèn giá trị mặc định 0 khi unboxing `null`, vì làm vậy sẽ **đánh đồng “không có dữ liệu” với “giá trị bằng 0”**.

## 2. Những thao tác trực tiếp gây unboxing null

### 2.1. Gán cho biến nguyên thủy

```java
Integer optionalCount = null;
// int count = optionalCount; // Khi chạy: NPE.
```

Vế trái `int` đòi giá trị nguyên thủy, nên Java phải unbox vế phải.

### 2.2. Gọi method có tham số nguyên thủy

```java
static void printCount(int count) {
    System.out.println(count);
}

// Integer nullableCount = null;
// printCount(nullableCount); // NPE trước khi thân printCount chạy.
```

Lời gọi `printCount(nullableCount)` yêu cầu chuyển `Integer` sang `int` để truyền tham số. Exception xảy ra **khi đánh giá đối số**, trước khi hàm có cơ hội tự kiểm tra giá trị.

Thiết kế hai API khác nhau:

```java
static void acceptRequiredCount(int count) {
    // Không có null: caller phải cung cấp số nguyên.
}

static void acceptNullableCount(Integer count) {
    if (count == null) {
        // Xử lý trạng thái thiếu.
        return;
    }
    int primitive = count;
    // ...
}
```

Nếu dữ liệu bắt buộc, dùng primitive ở biên sau khi đã validate giúp giảm rủi ro NPE ở các tầng sau. Nếu thiếu dữ liệu là trạng thái hợp lệ, API nhận wrapper nhưng phải có nhánh xử lý riêng.

### 2.3. Gọi trực tiếp intValue()

```java
Integer number = null;
// int value = number.intValue(); // NPE.
```

Đây là unboxing **tường minh**. Cách viết không tạo ra ngoại lệ khác với unboxing ngầm; bản chất là cùng việc cố lấy giá trị từ tham chiếu `null`.

## 3. Phép số học tự động unbox toán hạng wrapper

Một biểu thức trông đơn giản như:

```java
Integer quantity = null;
int total = quantity + 1; // NPE.
```

vẫn phải thực hiện unboxing để toán tử `+` nhận giá trị số. Tương tự với phép trừ, nhân, chia, lấy phần dư và các biểu thức dùng phép toán số nguyên.

```java
Integer amount = null;

// int a = amount * 2; // NPE.
// int b = amount / 2; // NPE.
// int c = amount % 2; // NPE.
// boolean positive = amount > 0; // NPE.
```

Khi `amount` là `null`, không có phép toán nguyên thủy nào thực sự được thực hiện trước khi exception phát sinh. Đừng nhầm với trường hợp `amount` hợp lệ nhưng số chia bằng 0: đó có thể là `ArithmeticException` sau khi unboxing thành công.

### 3.1. ++, -- và gán kết hợp cũng unbox

```java
Integer count = null;
// count++; // NPE.
// ++count; // NPE.
// count += 1; // NPE.
```

Các toán tử cập nhật yêu cầu lấy giá trị hiện tại của wrapper, thực hiện phép tăng/giảm hoặc phép cộng, rồi boxing giá trị mới vào biến tham chiếu. Nếu giá trị cũ là `null`, thao tác bị chặn ngay ở bước unboxing.

Một ví dụ không null:

```java
Integer count = 3;
count++;                // Unbox 3, cộng 1, box Integer 4.
System.out.println(count); // 4
```

Điểm quan trọng: `Integer` không tự trở thành kiểu primitive chỉ vì dùng `++`. Biến vẫn có kiểu wrapper và có thể được gán `null` ở một thời điểm khác.

### 3.2. Wrapper từ phép toán không làm biểu thức “an toàn với null”

```java
Integer a = 10;
Integer b = null;

// Integer result = a + b; // NPE khi unbox b.
```

Dù biến nhận có kiểu `Integer`, **toán tử cộng số học** trên `Integer` sẽ unbox toán hạng, tính toán theo numeric promotion rồi box kết quả nếu cần. Wrapper ở biến kết quả **không** khiến phép cộng biết xử lý `null`.

## 4. So sánh bằng: vì sao Integer == Integer có thể không unbox?

Đây là bẫy ngược lại: có trường hợp `==` **không** unbox. Phải xét **kiểu của cả hai toán hạng**, không chỉ nhìn tên toán tử.

### 4.1. Hai toán hạng đều là Integer: so sánh tham chiếu

```java
Integer left = null;
Integer right = null;

System.out.println(left == right); // true: cùng là null.
```

Ở đây, cả hai toán hạng có **kiểu tham chiếu `Integer`**. `==` thực hiện so sánh tham chiếu, không cần unboxing. Vì vậy hai giá trị `null` được coi là cùng tham chiếu `null` và không ném NPE.

Nhưng so sánh tham chiếu không phải cách chuẩn để so **giá trị số** của hai wrapper:

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true
// a == b so sánh identity, không phải một hợp đồng so sánh giá trị.
```

Các trường hợp cache wrapper có thể làm `==` tình cờ đúng; không dựa vào điều đó để quyết định hai số có bằng nhau không.

### 4.2. Một bên là primitive: có unboxing

```java
Integer left = null;

// boolean same = left == 0; // NPE.
```

Vì vế phải `0` là primitive `int`, Java áp dụng quy tắc numeric promotion/unboxing để so sánh số. `left` phải trở thành `int`; nếu là `null` thì NPE.

Bảng phân biệt:

| Biểu thức | Có unboxing? | Hành vi |
| --- | --- | --- |
| `Integer a = null, b = null; a == b` | Không | `true` (so sánh tham chiếu) |
| `Integer a = null; a == 0` | Có | NPE |
| `Integer a = null; a < 0` | Có | NPE |
| `Integer a = null; Objects.equals(a, null)` | Không | `true` |
| `Integer a = null; a.equals(0)` | Không có bước unboxing bắt buộc | NPE do **gọi method trên receiver null** |
| `Integer a = 5; int n = 5; a == n` | Có | `true` sau unboxing |

Có ít nhất **hai đường đi dẫn đến NPE** cần phân biệt: một là **unboxing null**, hai là **gọi phương thức của đối tượng null**, chẳng hạn `a.equals(...)`. Chúng cùng ném `NullPointerException` nhưng có nguyên nhân trực tiếp khác nhau.

### 4.3. Chọn cách so sánh

- Với **hai wrapper có thể null**, dùng `Objects.equals(a, b)` nếu muốn null-safe và so giá trị theo hợp đồng `equals`.
- Với wrapper bắt buộc không null, validate trước rồi unbox; từ đó có thể dùng phép so sánh số học.
- Không dùng `==` giữa hai `Integer` để thay thế `equals`; nó so identity, có thể chịu ảnh hưởng caching.
- `Objects.equals(Integer.valueOf(1), Long.valueOf(1L))` là `false` vì hai wrapper có kiểu khác nhau. Muốn so **giá trị số khác kiểu**, hãy chọn quy tắc chuyển đổi tường minh sau khi kiểm tra null và miền giá trị.

## 5. Toán tử ba ngôi ?: có thể unbox dù biến nhận là wrapper

Toán tử điều kiện `condition ? expression1 : expression2` xác định **kiểu của biểu thức kết quả** từ hai nhánh, không đơn giản dựa vào kiểu biến nhận. Khi một nhánh là wrapper số và nhánh kia là primitive, quy tắc chọn kiểu có thể khiến wrapper phải unbox.

```java
Integer nullable = null;
boolean chooseNullable = true;

// int result = chooseNullable ? nullable : 0; // NPE nếu chọn nhánh nullable.
```

Nếu hai nhánh có kiểu `Integer` và `int` như trên, kết quả số học là `int`, nên nhánh `nullable` phải unbox khi được chọn.

Điều dễ gây ngạc nhiên là thay đổi biến nhận thành wrapper **không nhất thiết giúp tránh**:

```java
Integer nullable = null;
boolean chooseNullable = true;

// Integer result = chooseNullable ? nullable : 0;
// Vẫn có thể NPE vì phép điều kiện đã có kiểu int trước khi boxing vào Integer.
```

Nếu ý định là **giữ trạng thái thiếu**, hãy làm hai nhánh cùng có kiểu tham chiếu `Integer`:

```java
Integer nullable = null;
boolean chooseNullable = true;
Integer result = chooseNullable ? nullable : null;
// result == null; không unbox.
```

Hoặc tốt hơn, viết rõ nhánh nghiệp vụ:

```java
Integer result;
if (chooseNullable) {
    result = nullable;
} else {
    result = Integer.valueOf(0);
}
```

**Không cần sợ mọi toán tử ba ngôi**: chỉ nhánh được chọn được đánh giá khi chạy. Nhưng quy tắc xác định **kiểu biểu thức chung** có thể khiến giá trị wrapper của nhánh đó bị unbox.

## 6. Map, DTO, JDBC và dữ liệu thiếu

### 6.1. Map.get có thể trả null

```java
Map<String, Integer> counts = new HashMap<>();
Integer found = counts.get("missing"); // null khi không có mapping.
```

Nếu tiếp tục:

```java
// int n = counts.get("missing"); // NPE do unboxing null.
```

Kết quả `Map.get` thường là wrapper, vì Java collections không chứa trực tiếp primitive. Nếu key không tồn tại, `get` trả `null` theo hợp đồng. Một `HashMap` còn có thể lưu mapping từ key sang **giá trị null**.

### 6.2. getOrDefault không luôn thay thế giá trị null

```java
Map<String, Integer> counts = new HashMap<>();
counts.put("present-null", null);

int missing = counts.getOrDefault("missing", 7); // 7
// int present = counts.getOrDefault("present-null", 7); // NPE.
```

`Map.getOrDefault(key, defaultValue)` dùng giá trị mặc định khi **không có mapping cho key**. Nếu key có mapping tới `null`, phương thức trả `null` đó, không nhất thiết áp dụng default. Gán trực tiếp cho `int` khi đó gây NPE.

Cần phân biệt ba trạng thái theo hợp đồng:

| Trạng thái | `containsKey(key)` | `get(key)` |
| --- | --- | --- |
| Key không tồn tại | `false` | `null` |
| Key tồn tại, value là null | `true` | `null` |
| Key tồn tại, value là 0 | `true` | `Integer.valueOf(0)` |

Nếu số 0 và không có dữ liệu mang ý nghĩa khác nhau, **không gộp chúng chỉ để tránh NPE**.

### 6.3. Từ database/JSON/DTO

Một trường số tùy chọn trong DTO có thể được biểu diễn bằng `Integer` hoặc `Long`. Khi nguồn trả `null`, wrapper chứa null; sau đó một phép toán hoặc phép gán về primitive có thể làm chương trình ném NPE.

Ví dụ class DTO:

```java
final class OrderInput {
    Integer quantity; // Có thể null nếu nguồn không cung cấp giá trị.
}
```

`quantity == null` không có nghĩa là `quantity == 0`. Tùy đặc tả:
- **Bắt buộc:** báo lỗi validation khi vắng mặt trước khi tính.
- **Tùy chọn có mặc định 0:** áp dụng mặc định rõ ràng tại ranh giới nhập liệu.
- **Tùy chọn mà thiếu mang nghĩa riêng:** giữ wrapper hoặc mô hình dữ liệu thể hiện trạng thái thiếu.

Khi làm việc với JDBC, cần hiểu cột SQL `NULL`, phương thức đọc dữ liệu và kiểm tra `wasNull()` nếu API trả kiểu primitive; không suy diễn rằng mọi phép đọc SQL NULL sẽ tự tạo wrapper null đúng ý định.

## 7. Mảng wrapper và stream dễ phát sinh NPE

### 7.1. Mảng wrapper khởi tạo với các phần tử null

```java
Integer[] wrappers = new Integer[3];
// wrappers[0], wrappers[1], wrappers[2] đều null.

// int first = wrappers[0]; // NPE khi unbox.

int[] primitives = new int[3];
// primitives[0], primitives[1], primitives[2] đều là 0.
```

Đây là khác biệt về **giá trị mặc định** của phần tử mảng: wrapper array chứa tham chiếu khởi tạo null, còn primitive array có giá trị nguyên thủy mặc định 0.

Với **biến cục bộ** `int x;` chưa gán, Java không cho đọc ngay: đó là **lỗi biên dịch “variable might not have been initialized”**, không phải biến có mặc định 0. Chỉ field và phần tử mảng mới có giá trị mặc định theo quy tắc khởi tạo.

### 7.2. Stream<Integer> sang IntStream

Một pipeline có `null`:

```java
Stream<Integer> stream = Stream.of(1, null, 3);
// int sum = stream.mapToInt(Integer::intValue).sum(); // NPE.
```

Method reference `Integer::intValue` phải gọi phương thức trên mỗi phần tử; nếu phần tử là null thì NPE.

Nếu **quy tắc nghiệp vụ cho phép bỏ các phần tử thiếu**:

```java
int sum = Stream.of(1, null, 3)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum(); // 4
```

Bỏ giá trị null là **quyết định nghiệp vụ**, không phải mặc định an toàn trong mọi bài toán. Nếu dữ liệu thiếu là lỗi, hãy validate và báo lỗi thay vì lọc bỏ âm thầm, vì số lượng mẫu và tổng có thể bị thay đổi.

## 8. Cách xử lý null trước khi unbox

### 8.1. Kiểm tra trực tiếp: khi null là không hợp lệ

```java
static int requiredQuantity(Integer quantity) {
    if (quantity == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    return quantity; // Unboxing an toàn sau kiểm tra.
}
```

Ưu điểm là nơi báo lỗi gần nguồn dữ liệu và exception mô tả **quy tắc nghiệp vụ**, thay vì để NPE xuất hiện sâu trong phép tính. Hợp đồng có thể chọn loại exception khác nhưng phải nhất quán.

### 8.2. Cho phép mặc định khi null có ý nghĩa “không cung cấp”

```java
Integer quantity = null;
int count = quantity != null ? quantity : 0;
```

Nhánh `quantity` được unbox chỉ khi khác null; còn nhánh mặc định cung cấp giá trị primitive 0. Đoạn này là một ví dụ có chủ đích lựa chọn default.

Java 9+ có:

```java
int count = Objects.requireNonNullElse(quantity, 0);
```

`Objects.requireNonNullElse` trả đối số đầu nếu không null, hoặc giá trị mặc định (phải khác null). Kết quả `Integer` được unbox an toàn khi default là 0.

### 8.3. Optional<Integer>

```java
int count = Optional.ofNullable(quantity).orElse(0);
```

`Optional` có thể hữu ích tại API muốn thể hiện tính tùy chọn, nhưng **không tự hợp thức hóa** việc thay thiếu bằng số 0. Nếu đầu vào thiếu phải báo lỗi:

```java
int count = Optional.ofNullable(quantity)
        .orElseThrow(() -> new IllegalArgumentException("quantity required"));
```

Lúc gọi `orElseThrow`, giá trị `Integer` được trả ra khác null nếu có dữ liệu; nếu không, exception nghiệp vụ phát sinh.

**Không dùng `Optional.get()` mù quáng** rồi hy vọng nó giải quyết null. `Optional.empty().get()` có lỗi riêng (`NoSuchElementException`), và bạn vẫn cần quyết định ngữ nghĩa dữ liệu vắng mặt.

### 8.4. Objects.requireNonNull là phát hiện sớm, không phải cấp mặc định

```java
Integer quantity = null;
// int count = Objects.requireNonNull(quantity, "quantity must not be null");
// Ném NullPointerException có thông điệp do mình cung cấp.
```

`requireNonNull` hữu ích khi muốn **fail fast** và giữ hợp đồng NPE cho tham số bắt buộc. Nó không biến null thành 0 và không phải phương pháp duy nhất; ở biên yêu cầu nghiệp vụ, `IllegalArgumentException` hoặc lỗi validation thường mang ý nghĩa rõ hơn.

## 9. Phân biệt null, zero và dữ liệu không hợp lệ

Một điểm quan trọng khi thiết kế:

- `null`: **không có đối tượng/không có giá trị** trong một vị trí cho phép tham chiếu null.
- `0`: **giá trị số nguyên hợp lệ**, mang ý nghĩa số lượng bằng không.
- Một số âm ở trường số lượng: có thể là giá trị nguyên hợp lệ về kiểu nhưng **sai quy tắc nghiệp vụ**.
- Chuỗi không phải số: lỗi chuyển đổi đầu vào, không phải unboxing null.

Thí dụ API giỏ hàng:

| Đầu vào quantity | Ý nghĩa đề xuất | Cách xử lý |
| --- | --- | --- |
| `null` | Không cung cấp trường bắt buộc | Trả lỗi validation |
| `0` | Có cung cấp nhưng không chọn sản phẩm | Có thể bị từ chối hoặc chấp nhận tùy hợp đồng |
| `3` | Số lượng ba sản phẩm | Hợp lệ nếu giới hạn cho phép |
| `-3` | Âm | Có thể bị từ chối bởi quy tắc nghiệp vụ |

Nếu mặc định `null → 0` ở mọi nơi, hệ thống có thể che giấu lỗi nguồn dữ liệu, khó phát hiện việc field bị bỏ quên trong một lần cập nhật API.

**Thiết kế ưu tiên:** chuyển DTO nullable thành dữ liệu miền đã được validate ngay ở biên, rồi dùng primitive nếu không còn ý nghĩa “thiếu dữ liệu”.

## 10. Chương trình Java 17+ độc lập

Lưu nội dung sau vào file **`NullUnboxingDemo.java`**. Các trường hợp gây lỗi được bắt riêng để chương trình chạy đến hết, giúp quan sát đúng nơi NPE xuất hiện.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.stream.Stream;

public class NullUnboxingDemo {
    static int requiredQuantity(Integer quantity) {
        if (quantity == null) {
            throw new IllegalArgumentException("quantity is required");
        }
        return quantity;
    }

    public static void main(String[] args) {
        Integer boxed = null;

        try {
            int direct = boxed;
        } catch (NullPointerException ex) {
            System.out.println("direct-unbox=NPE");
        }

        try {
            int added = boxed + 1;
        } catch (NullPointerException ex) {
            System.out.println("arithmetic=NPE");
        }

        try {
            boxed++;
        } catch (NullPointerException ex) {
            System.out.println("increment=NPE");
        }

        Integer anotherNull = null;
        System.out.println("wrapper-reference-equality=" +
                (boxed == anotherNull));

        try {
            boolean equalsZero = boxed == 0;
        } catch (NullPointerException ex) {
            System.out.println("primitive-comparison=NPE");
        }

        System.out.println("objects-null-equality=" +
                Objects.equals(boxed, null));

        boolean selectNull = true;
        try {
            int selected = selectNull ? boxed : 0;
        } catch (NullPointerException ex) {
            System.out.println("ternary=NPE");
        }

        Integer retainedNull = selectNull ? boxed : null;
        System.out.println("nullable-ternary=" + retainedNull);

        Integer[] wrappers = new Integer[1];
        try {
            int arrayValue = wrappers[0];
        } catch (NullPointerException ex) {
            System.out.println("wrapper-array=NPE");
        }
        int[] primitives = new int[1];
        System.out.println("primitive-array=" + primitives[0]);

        Map<String, Integer> map = new HashMap<>();
        map.put("present-null", null);
        System.out.println("missing-default=" +
                map.getOrDefault("missing", 7));

        try {
            int present = map.getOrDefault("present-null", 7);
        } catch (NullPointerException ex) {
            System.out.println("mapped-null=NPE");
        }
        System.out.println("mapping-exists=" +
                map.containsKey("present-null"));

        try {
            int streamSum = Stream.of(1, null, 3)
                    .mapToInt(Integer::intValue)
                    .sum();
        } catch (NullPointerException ex) {
            System.out.println("stream=NPE");
        }

        int validSum = Stream.of(1, null, 3)
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("filtered-sum=" + validSum);

        System.out.println("fallback=" +
                Objects.requireNonNullElse(boxed, 0));
        System.out.println("optional-fallback=" +
                Optional.ofNullable(boxed).orElse(5));

        try {
            requiredQuantity(boxed);
        } catch (IllegalArgumentException ex) {
            System.out.println("required-validation=error");
        }
        System.out.println("zero-is-valid-value=" +
                (requiredQuantity(0) == 0));
    }
}
```

Lệnh biên dịch và chạy bằng JDK 17+:

```bash
javac NullUnboxingDemo.java
java NullUnboxingDemo
```

Stdout:

```text
direct-unbox=NPE
arithmetic=NPE
increment=NPE
wrapper-reference-equality=true
primitive-comparison=NPE
objects-null-equality=true
ternary=NPE
nullable-ternary=null
wrapper-array=NPE
primitive-array=0
missing-default=7
mapped-null=NPE
mapping-exists=true
stream=NPE
filtered-sum=4
fallback=0
optional-fallback=5
required-validation=error
zero-is-valid-value=true
```

**Giải thích những kết quả quan trọng:**

1. `direct-unbox`, `arithmetic` và `increment` đều là NPE do unboxing null, dù cú pháp rất khác nhau.
2. `wrapper-reference-equality=true` không có NPE vì `boxed == anotherNull` so sánh **hai tham chiếu `Integer`**.
3. `primitive-comparison=NPE` vì `boxed == 0` đòi unbox `Integer` sang `int`.
4. Toán tử ba ngôi trả về `int` trong biểu thức trộn `Integer` và `int`, gây NPE khi nhánh wrapper null được chọn. Biểu thức hai nhánh tham chiếu `Integer`/`null` giữ được null.
5. Mảng `Integer[]` mới chứa phần tử null; mảng `int[]` mới chứa 0.
6. `getOrDefault` không thay null của một **mapping đang tồn tại**; `containsKey` cho biết đây không phải key bị thiếu.
7. Filter trong stream loại null **vì chương trình chủ ý cho phép bỏ qua** giá trị không có dữ liệu.
8. `requireNonNullElse` và `Optional.orElse` đưa ra giá trị mặc định có chủ đích; `requiredQuantity` ngược lại chủ động từ chối null nhưng chấp nhận giá trị 0.

## 11. Cách xác định dòng code gây NPE

Khi gặp NPE, hãy rà soát **nguồn wrapper** và **ngữ cảnh nguyên thủy**:

1. Nguồn của biến có thể null không? Tham số, kết quả `map.get`, field DTO, mảng wrapper mới, kết quả từ database?
2. Dòng lỗi có phép gán wrapper sang primitive, toán tử số học, `++`/`--`, `+=`, so sánh wrapper với số nguyên hay toán tử ba ngôi hỗn hợp không?
3. Nếu có `.intValue()`, `.longValue()`, `.doubleValue()` hoặc `Integer::intValue`, receiver có thể null không?
4. Wrapper có vừa bị lấy ra khỏi collection không? Giá trị null có phải trạng thái hợp lệ của mapping?
5. NPE có thực sự do unboxing, hay do gọi method như `x.equals(...)` trên receiver null?
6. Nên báo lỗi bắt buộc thiếu dữ liệu, giữ trạng thái null, hay chọn giá trị mặc định?
7. Có thể validate và chuyển sang primitive **một lần tại ranh giới hệ thống** để loại bỏ null khỏi phần tính toán phía sau không?

Với JVM hiện đại, thông điệp NPE có thể chỉ ra biến hoặc thao tác được dereference, nhưng **không nên viết test phụ thuộc chuỗi thông báo NPE**: wording có thể thay đổi theo phiên bản JVM, cách biên dịch và cấu trúc bytecode. Kiểm tra loại exception và kết quả nghiệp vụ thay thế.

### Không nên “chữa” bằng try/catch NullPointerException trên mọi phép tính

Bắt NPE trên toàn bộ pipeline như một đường xử lý dữ liệu bình thường thường che giấu lỗi ở những object khác. Nên kiểm tra null ở nguồn hoặc chuyển đổi có chủ đích trước phép tính. Chỉ dùng `try/catch` khi thật sự có một ranh giới xử lý ngoại lệ hợp lý và có thể nhận biết đúng nguyên nhân.

## 12. Những sai lầm thường gặp

| Nhầm lẫn | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| `Integer x = null; int n = x;` tự lấy 0 | Unboxing null ném NPE | Quy định null là lỗi, optional hoặc default |
| Chỉ có `intValue()` mới gây NPE | Java tự unbox trong toán tử và gọi method | Kiểm tra ngữ cảnh yêu cầu primitive |
| `Integer x=null; x++` khởi tạo thành 1 | `++` phải unbox giá trị cũ trước | Khởi tạo/validate trước cập nhật |
| `Integer x=null; x == 0` là false | So với primitive buộc unbox | `x != null && x == 0` hoặc validation |
| Hai `Integer` so bằng `==` là so giá trị | So tham chiếu và có caching | `Objects.equals` hoặc unbox sau validation |
| `x.equals(y)` an toàn khi x null | Gọi method trên null ném NPE | `Objects.equals(x,y)` |
| `Integer result = condition ? x : 0` chắc chắn giữ null | Kiểu biểu thức có thể là primitive `int` | Đặt nhánh/kiểu chung tường minh |
| `Map.getOrDefault` thay mọi null bằng default | Mapping key→null khác key vắng mặt | Xét `containsKey` hoặc chuẩn hóa theo hợp đồng |
| `Integer[]` mặc định chứa số 0 | Các phần tử mặc định là null | Khởi tạo phần tử hoặc dùng `int[]` |
| `Stream<Integer>.mapToInt` tự bỏ qua null | Chuyển phần tử null bằng `intValue` ném NPE | Filter/validate có chủ đích |
| Thay mọi null bằng 0 là cách sửa chung | Mất phân biệt “thiếu” và “bằng không” | Thiết kế miền dữ liệu rõ ràng |
| `Objects.requireNonNull` cấp giá trị mặc định | Nó ném NPE khi null | Dùng `requireNonNullElse` nếu default phù hợp |
| Tưởng NPE là ArithmeticException | Unboxing null là lỗi tham chiếu | Phân biệt NPE, lỗi miền và lỗi chia cho 0 |

## 13. Bài tập tự kiểm tra

1. **Gán và phép toán.** Dự đoán kết quả của `Integer value=null; int a=value;` và `int b=value+1;`. Vì sao cả hai biên dịch nhưng ném NPE?
2. **So sánh wrapper.** Cho `Integer a=null,b=null;`. Dự đoán `a==b`, `a==0`, `Objects.equals(a,b)` và `a.equals(b)`. Trong mỗi trường hợp, xác định có unboxing không.
3. **Toán tử ba ngôi.** Phân tích `Integer x=null; int y=flag?x:0;` với `flag=true` và `flag=false`. Nếu cần giữ null, viết lại kiểu kết quả và nhánh phù hợp.
4. **Map.** Một `HashMap<String,Integer>` chứa mapping `"a" → null` nhưng không có key `"b"`. `getOrDefault` cho kết quả nào? Khi unbox trực tiếp, trường hợp nào ném NPE?
5. **Mảng.** Vì sao `Integer[] a=new Integer[3]` dễ ném NPE khi tính tổng, còn `int[] b=new int[3]` thì không? Khi nào việc dùng 0 mặc định lại che mất dữ liệu chưa nhập?
6. **Stream.** Viết pipeline tính tổng các phần tử non-null; giải thích vì sao quyết định loại null cần xuất phát từ nghiệp vụ.
7. **Thiết kế API.** Một yêu cầu đặt hàng có `quantity` tùy chọn. Hãy chọn một trong ba hợp đồng: thiếu là lỗi, thiếu là số 0, hoặc thiếu có ý nghĩa riêng. Viết hàm chuyển DTO sang mô hình đã validate.
8. **Test biên.** Tạo unit test cho `requiredQuantity(null)`, `requiredQuantity(0)`, `requiredQuantity(5)`, và trường hợp số âm. NPE có phải kiểu lỗi tốt nhất để trả về từ tầng API không?

## 14. Checklist trước khi đưa code vào production

- Xem `Integer`/`Long`/`Double` như **tham chiếu có thể null**, không phải primitive.
- Xác định rõ các nơi Java tự unbox: gán sang primitive, tham số primitive, toán tử số học, `++`/`--`, phép so sánh với primitive, toán tử ba ngôi hỗn hợp, map/stream/mảng wrapper.
- Trước khi unbox, **kiểm tra null hoặc chuyển thành giá trị mặc định có chủ đích**.
- Không dùng `==` giữa hai wrapper để kiểm tra giá trị số; không gọi `equals` trên receiver có thể null.
- Phân biệt **key vắng mặt**, **mapping null** và **giá trị 0** khi đọc `Map`.
- Đừng giả định mảng wrapper mới có các phần tử 0.
- Nếu đầu vào bắt buộc, validate sớm và cân nhắc chuyển sang primitive cho phần tính toán nội bộ.
- Nếu dữ liệu tùy chọn, giữ wrapper/`Optional` hoặc trạng thái miền tường minh thay vì âm thầm biến null thành 0.
- Viết test cho cả null, 0, giá trị hợp lệ, giá trị ngoài miền và đường chuyển đổi vào primitive.
- Chỉ bắt NPE khi ranh giới xử lý thật sự có ý nghĩa; ưu tiên sửa nơi phát sinh dữ liệu null.

**Kết luận:** `NullPointerException` khi unbox xảy ra không phải vì phép toán số học sai, mà vì Java cần lấy giá trị nguyên thủy từ **một wrapper đang là null**. Cách phòng tránh bền vững là làm rõ ngữ nghĩa dữ liệu thiếu, kiểm tra tại ranh giới và chỉ unbox sau khi biết chắc có giá trị.
