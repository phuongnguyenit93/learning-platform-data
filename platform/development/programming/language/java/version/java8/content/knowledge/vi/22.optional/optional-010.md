# Value-based semantics và so sánh bằng giá trị với Optional trong Java

## 1. Hiểu đúng bản chất value-based của `Optional`

`java.util.Optional<T>` là một kiểu chứa có thể **có** một giá trị khác `null` hoặc **không có** giá trị. Nó giúp API diễn đạt rõ trường hợp “không tìm thấy kết quả” mà không buộc bên gọi phải đoán ý nghĩa của `null`. `Optional` có từ Java 8 và vẫn là một phần của Java hiện đại.

Điểm cần nhớ của bài này: **`Optional` là một value-based class**. Khi hai đối tượng `Optional` bằng nhau theo `equals()`, ứng dụng phải coi chúng là **có thể thay thế cho nhau về giá trị**, thay vì dựa vào việc chúng có cùng địa chỉ hay cùng danh tính đối tượng trong bộ nhớ.

Ví dụ:

```java
Optional<String> first = Optional.of(new String("JAVA"));
Optional<String> second = Optional.of(new String("JAVA"));

boolean sameValue = first.equals(second); // true
```

Hai lời gọi tạo giá trị chứa chuỗi bằng nhau theo `String.equals`. Kết quả so sánh **`Optional.equals`** là `true`; không cần và không nên kiểm tra liệu `first` và `second` có phải cùng một object hay không.

> **Nguyên tắc:** Với `Optional`, hãy hỏi “có giá trị không?” qua `isPresent()`/`isEmpty()` và “hai kết quả có bằng nhau không?” qua `equals()`. Đừng hỏi “hai đối tượng `Optional` có cùng identity không?”.

### 1.1. “Value-based” không có nghĩa gì?

Nó **không** có nghĩa rằng một `Optional` có thể chứa `null` như một giá trị hiện diện. `Optional.of(null)` ném `NullPointerException`; `Optional.ofNullable(null)` tạo trạng thái rỗng.

Nó **không** đảm bảo compiler/JVM sẽ tạo đúng một object cho mỗi lời gọi `Optional.of`, cũng không đảm bảo lúc nào cũng dùng chung một object cho hai giá trị bằng nhau. Một runtime có thể tái sử dụng hoặc tối ưu cách biểu diễn mà không thay đổi hợp đồng về giá trị.

Nó **không** khiến chính đối tượng được chứa trở thành bất biến. Nếu `Optional` chứa một `List` có thể sửa, thay đổi nội dung list vẫn có thể thay đổi kết quả `equals()`/`hashCode()` khi so sánh những `Optional` liên quan.

Nó **không** có nghĩa mọi kiểu chứa trong `Optional<T>` đều tự nhiên so sánh theo nội dung nghiệp vụ. Nếu `T` dùng `Object.equals` mặc định (so sánh identity), `Optional.equals` sẽ sử dụng đúng cách so sánh đó.

## 2. Quy tắc chính thức của `Optional.equals(Object)`

Hai đối tượng được coi là bằng nhau nếu:

1. Đối tượng so sánh cũng là một `Optional`; và
2. **Cả hai đều rỗng**, hoặc **cả hai đều có giá trị và hai giá trị chứa bên trong bằng nhau theo `equals()`**.

Nói cách khác:

```text
Optional.empty()      ~= Optional.empty()            -> true
Optional.of("a")      ~= Optional.of("a")            -> true
Optional.of("a")      ~= Optional.of("b")            -> false
Optional.of("a")      ~= Optional.empty()            -> false
Optional.of("a")      ~= "a"                         -> false
```

Dấu `~=` ở đây **chỉ là ký hiệu minh họa quan hệ bằng nhau theo `equals`**, không phải toán tử Java.

| Biểu thức Java | Kết quả | Lý do |
| --- | --- | --- |
| `Optional.of("a").equals(Optional.of("a"))` | `true` | Chuỗi được chứa bằng nhau. |
| `Optional.of("a").equals(Optional.of("b"))` | `false` | Giá trị chứa khác nhau. |
| `Optional.empty().equals(Optional.ofNullable(null))` | `true` | Cả hai đều rỗng. |
| `Optional.of("a").equals(Optional.empty())` | `false` | Một bên hiện diện, một bên rỗng. |
| `Optional.of(7).equals(OptionalInt.of(7))` | `false` | `Optional<Integer>` khác lớp `OptionalInt`. |
| `Optional.of("a").equals("a")` | `false` | `Optional` không bằng trực tiếp giá trị chứa. |

Ví dụ này sử dụng `java.util.Optional` và `java.util.OptionalInt`. Các biểu thức đều độc lập, có thể chạy trong method sau khi import hai lớp.

### 2.1. So sánh hai `Optional` có kiểu tham số khác nhau

Kiểu generic `T` của Java chủ yếu được xử lý theo cơ chế type erasure; phương thức `equals(Object)` kiểm tra đối tượng thực tế. Hai `Optional` rỗng có thể bằng nhau theo `equals()` dù hai biến có kiểu generic khác nhau:

```java
Optional<String> emptyName = Optional.empty();
Optional<Integer> emptyAge = Optional.empty();

boolean bothEmpty = emptyName.equals(emptyAge); // true
```

Tuy nhiên, điều đó **không** có nghĩa hai trường dữ liệu thuộc hai miền nghiệp vụ khác nhau có thể dùng thay thế nhau trong thiết kế API. So sánh phải có ngữ nghĩa nghiệp vụ; `Optional<String>` và `Optional<Integer>` không phải hai kiểu có thể tùy tiện gán cho nhau.

### 2.2. Giá trị bọc bên trong quyết định kết quả

`Optional.equals` **ủy quyền việc so sánh giá trị hiện diện** cho `equals` của đối tượng bên trong. Ví dụ `String` so sánh chuỗi ký tự; một DTO tùy biến không override `equals` sẽ thường kế thừa `Object.equals`, dẫn tới hai DTO có nội dung giống nhau vẫn khác nhau nếu là hai instance khác nhau.

Một cách diễn giải thực tế:

```text
Optional<CustomerId>.equals(...)
    |
    +-- cả hai có dữ liệu?
    |       |
    |       +-- có: gọi equals của CustomerId bên trong
    |       +-- không: cả hai rỗng thì bằng nhau
    |
    +-- không so sánh identity của chính Optional
```

Khi cần so sánh theo mã khách hàng, hãy định nghĩa `equals/hashCode` đúng cho lớp giá trị `CustomerId` hoặc dùng một kiểu bất biến có hợp đồng so sánh rõ ràng. `Optional` không thể tự đoán những trường nào của DTO phải tham gia so sánh.

## 3. Vì sao tuyệt đối không dựa vào `==` để so sánh `Optional`?

Toán tử `==` với **reference** kiểm tra **cùng tham chiếu**, không kiểm tra hai `Optional` chứa dữ liệu bằng nhau. Chỉ vì cách triển khai hiện tại đôi khi tái sử dụng một instance, phép so sánh identity có thể tình cờ trả `true`; điều đó không phải hợp đồng API.

**Không dùng:**

```java
Optional<String> a = Optional.of("JAVA");
Optional<String> b = Optional.of("JAVA");

// SAI về thiết kế: kết quả phụ thuộc identity của wrapper.
// if (a == b) { ... }

// SAI: không có bảo đảm Optional.empty() là singleton.
// if (a == Optional.<String>empty()) { ... }
```

**Đúng:**

```java
boolean equalResults = a.equals(b);
boolean absent = !a.isPresent();         // Java 8+
boolean present = b.isPresent();          // Java 8+
```

`Optional.isEmpty()` (nếu muốn viết `a.isEmpty()`) được bổ sung từ **Java 11**, không tồn tại trong Java 8 gốc. Ví dụ chạy đầy đủ ở mục 7 dùng `isPresent()` để giữ tương thích Java 8.

### 3.1. `Optional.empty()` không có hợp đồng singleton

Tài liệu `Optional.empty()` nhấn mạnh: **không được giả định mọi lời gọi trả về cùng một instance**. Một số JDK có thể trả về cùng một object cho các Optional rỗng, nhưng chỉ nên dựa vào **trạng thái rỗng**:

```java
Optional<String> nothing = Optional.empty();
boolean empty = !nothing.isPresent();          // true
boolean sameValue = nothing.equals(
    Optional.<String>empty());                 // true
```

Không kiểm tra `nothing == Optional.empty()`. Hai phương thức `equals` và `isPresent` thể hiện đúng ý định, không phụ thuộc chi tiết triển khai.

## 4. Tránh mọi thao tác dựa vào identity của `Optional`

Tính chất value-based không dừng ở toán tử `==`. Theo tài liệu Java về value-based classes, ứng dụng không nên dựa vào những thao tác nhạy cảm với identity vì behavior có thể thay đổi ở các phiên bản JVM tương lai.

| Thao tác | Vì sao không nên dùng cho `Optional` | Thay thế |
| --- | --- | --- |
| `a == b`, `a != b` | Kiểm tra cùng tham chiếu, không phải cùng nội dung. | `a.equals(b)` hoặc `Objects.equals(a, b)` (khi thật sự cần xử lý tham chiếu null). |
| `System.identityHashCode(optional)` | Phản ánh identity, không đại diện cho giá trị chứa. | `optional.hashCode()` nếu cần hash theo giá trị. |
| `synchronized(optional)` | Không có quyền sở hữu monitor đáng tin cậy trên đối tượng value-based. | Dùng đối tượng khóa riêng có vòng đời và identity được kiểm soát. |
| `new IdentityHashMap<Optional<...>, ...>()` | Bản đồ so sánh key theo `==` thay vì `equals`. | Thường dùng `HashMap` với khóa nghiệp vụ có `equals/hashCode` rõ ràng. |
| Suy luận từ việc JVM cấp phát hoặc tái sử dụng instance | API không cam kết object riêng hay object dùng chung. | Chỉ dựa vào trạng thái và giá trị hiện diện. |

Với khóa đồng bộ, nên dùng một đối tượng riêng:

```java
private final Object lock = new Object();

// Bên trong method được điều phối bởi đối tượng chứa lock:
synchronized (lock) {
    // Thao tác cần đồng bộ.
}
```

Đây là **snippet cấu trúc lớp**, không phải chương trình Java độc lập. Không dùng `Optional` làm lock: JVM hiện đại có thể cảnh báo về việc đồng bộ trên lớp value-based; tài liệu API lưu ý các hành vi đồng bộ như vậy có thể không ổn định hoặc thất bại ở phiên bản tương lai.

Lưu ý `equals/hashCode` theo giá trị không có nghĩa `Optional` nên là khóa mặc định trong mọi bản đồ. Dùng **khóa nghiệp vụ thực** (mã khách hàng, ID, SKU) thường rõ hơn nhiều so với `Map<Optional<ID>, ...>`.

## 5. Hợp đồng `hashCode()` của `Optional`

`Optional.hashCode()` được định nghĩa bằng **hash code của giá trị chứa** khi có dữ liệu; với Optional rỗng, nó trả **`0`**.

```java
Optional<String> first = Optional.of("JAVA");
Optional<String> second = Optional.of(new String("JAVA"));
Optional<String> empty = Optional.empty();

boolean sameHash = first.hashCode() == second.hashCode(); // true
boolean emptyHashIsZero = empty.hashCode() == 0;           // true
```

Điều này đáp ứng hợp đồng chung của Java: nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` cũng phải `true`. Chiều ngược lại **không** bắt buộc: hai object có hash code bằng nhau chưa chắc bằng nhau, do hash collision.

### 5.1. `HashSet` minh họa so sánh bằng giá trị

```java
Set<Optional<String>> values = new HashSet<>();
values.add(Optional.of("JAVA"));
values.add(Optional.of(new String("JAVA")));
values.add(Optional.empty());
values.add(Optional.<String>empty());

int distinctResults = values.size(); // 2
```

`HashSet` dùng `hashCode` và `equals` để nhận diện phần tử trùng lặp. Hai Optional chứa `"JAVA"` được coi là bằng nhau; hai Optional rỗng cũng bằng nhau. Như vậy chỉ có **hai giá trị phân biệt** về mặt tập hợp: có `JAVA` và rỗng.

Ví dụ là minh họa hợp đồng equals/hashCode, **không phải lời khuyên biến `Optional` thành kiểu khóa cho mọi model**. Theo tài liệu API, `Optional` được thiết kế chủ yếu để làm **kiểu trả về của phương thức** khi cần biểu diễn việc không có kết quả.

### 5.2. Bên trong là đối tượng có thể thay đổi thì sao?

`Optional` không có phương thức đổi giá trị chứa, nhưng nó **không tạo bản sao sâu** của một object mutable. Ví dụ:

```java
List<String> mutable = new ArrayList<>();
Optional<List<String>> wrapped = Optional.of(mutable);

int before = wrapped.hashCode();
mutable.add("JAVA");
int after = wrapped.hashCode();

boolean changed = before != after; // true trong ví dụ này
```

Vì `ArrayList.hashCode()` dựa trên nội dung list, thêm `"JAVA"` có thể khiến hash code của Optional thay đổi. Không sửa nội dung của đối tượng được dùng như khóa trong `HashMap` hoặc phần tử trong `HashSet` khi thay đổi đó ảnh hưởng `equals/hashCode`; cấu trúc hash có thể không tìm lại phần tử như mong đợi.

Đây không phải vấn đề “Optional chưa đủ value-based” mà là tính chất của **giá trị được chứa**. Khi cần khóa ổn định, dùng giá trị bất biến có `equals/hashCode` xác định.

## 6. So sánh với `OptionalInt`, `OptionalLong` và `OptionalDouble`

Java cũng cung cấp các dạng chuyên biệt cho primitive: `OptionalInt`, `OptionalLong`, `OptionalDouble`. Chúng là những kiểu value-based riêng, biểu diễn “không có giá trị” hoặc “có một primitive tương ứng”.

| Kiểu | Ví dụ hiện diện | So sánh khi có dữ liệu |
| --- | --- | --- |
| `Optional<Integer>` | `Optional.of(7)` | Dựa vào `Integer.equals`. |
| `OptionalInt` | `OptionalInt.of(7)` | So sánh hai `int` được chứa. |
| `OptionalLong` | `OptionalLong.of(7L)` | So sánh hai `long` được chứa. |
| `OptionalDouble` | `OptionalDouble.of(7.0)` | Dựa trên `Double.compare`. |

**Chúng không thay thế được cho nhau qua `equals`**: `Optional.of(7).equals(OptionalInt.of(7))` trả `false` vì đó là hai lớp khác nhau.

### 6.1. Hai trường hợp đặc biệt của `OptionalDouble`

Theo API, `OptionalDouble.equals` sử dụng quy tắc `Double.compare` cho các giá trị có mặt. Vì vậy:

```java
boolean nanEqual = OptionalDouble.of(Double.NaN)
    .equals(OptionalDouble.of(Double.NaN)); // true

boolean signedZeroEqual = OptionalDouble.of(-0.0)
    .equals(OptionalDouble.of(+0.0));       // false
```

Điều này **khác** phép so sánh primitive `double` bằng `==` trong hai tình huống trên: `Double.NaN == Double.NaN` là `false`, còn `-0.0 == +0.0` là `true`. Không dùng `==` trên bản thân `OptionalDouble`; cả hai cách đều không mang cùng ý nghĩa với `OptionalDouble.equals`.

### 6.2. Tránh đánh đồng các kiểu Optional

`OptionalInt` không phải `Optional<Integer>` chỉ vì cả hai cùng diễn đạt một số `int`. `OptionalInt` cung cấp `getAsInt()`, `orElse(int)`, `isPresent()`; `Optional<Integer>` dùng `get()` và các phương thức cho object. Nếu API trả về primitive, kiểu chuyên biệt giúp giảm nhu cầu boxing trong việc mô hình hóa kết quả; nếu nghiệp vụ cần object generic, `Optional<T>` là lựa chọn hợp lệ và vẫn được hỗ trợ.

## 7. Chương trình Java hoàn chỉnh: kiểm chứng so sánh theo giá trị

Chương trình độc lập dưới đây biểu diễn trường hợp hai `Optional` chứa chuỗi bằng nhau, hai Optional rỗng, `HashSet` loại phần tử trùng, kiểu nội dung tự định nghĩa, các Optional primitive và tình huống `NaN`/`signed zero`.

Tạo file **OptionalValueSemanticsDemo.java**. Mã chỉ sử dụng cú pháp/API từ Java 8 trở lên, không gọi API mới hơn như `Optional.isEmpty()` (Java 11).

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.Set;

public class OptionalValueSemanticsDemo {
    static final class CustomerId {
        private final String code;

        CustomerId(String code) {
            this.code = Objects.requireNonNull(code, "code");
        }

        @Override
        public boolean equals(Object other) {
            if (!(other instanceof CustomerId)) {
                return false;
            }
            CustomerId that = (CustomerId) other;
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    public static void main(String[] args) {
        Optional<String> a = Optional.of(new String("JAVA"));
        Optional<String> b = Optional.of(new String("JAVA"));
        Optional<String> missing = Optional.empty();
        Optional<String> nullSource = Optional.ofNullable(null);

        System.out.println("Hai Optional cung gia tri: "
            + a.equals(b));
        System.out.println("HashCode cua hai Optional bang nhau: "
            + (a.hashCode() == b.hashCode()));
        System.out.println("Hai Optional rong: "
            + missing.equals(nullSource));
        System.out.println("Co gia tri khac rong: "
            + a.equals(missing));
        System.out.println("Optional khac gia tri chua: "
            + a.equals("JAVA"));
        System.out.println("Optional rong co hashCode 0: "
            + (missing.hashCode() == 0));

        Set<Optional<String>> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(missing);
        set.add(nullSource);
        System.out.println("So gia tri trong HashSet: " + set.size());

        Optional<CustomerId> id1 = Optional.of(new CustomerId("C-7"));
        Optional<CustomerId> id2 = Optional.of(new CustomerId("C-7"));
        System.out.println("CustomerId co equals theo ma: "
            + id1.equals(id2));

        System.out.println("OfNullable null la rong: "
            + !nullSource.isPresent());
        System.out.println("OptionalInt so 7: "
            + OptionalInt.of(7).equals(OptionalInt.of(7)));
        System.out.println("Optional khac OptionalInt: "
            + Optional.of(7).equals(OptionalInt.of(7)));
        System.out.println("OptionalDouble NaN bang nhau: "
            + OptionalDouble.of(Double.NaN)
                .equals(OptionalDouble.of(Double.NaN)));
        System.out.println("OptionalDouble -0.0 khac +0.0: "
            + !OptionalDouble.of(-0.0)
                .equals(OptionalDouble.of(+0.0)));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 OptionalValueSemanticsDemo.java
java OptionalValueSemanticsDemo
```

**Kết quả stdout chính xác:**

```text
Hai Optional cung gia tri: true
HashCode cua hai Optional bang nhau: true
Hai Optional rong: true
Co gia tri khac rong: false
Optional khac gia tri chua: false
Optional rong co hashCode 0: true
So gia tri trong HashSet: 2
CustomerId co equals theo ma: true
OfNullable null la rong: true
OptionalInt so 7: true
Optional khac OptionalInt: false
OptionalDouble NaN bang nhau: true
OptionalDouble -0.0 khac +0.0: true
```

### 7.1. Giải thích những kết quả quan trọng

1. Hai giá trị `new String("JAVA")` có nội dung như nhau. `Optional.equals` dựa vào `String.equals` nên trả `true`, bất kể cách cấp phát đối tượng `Optional`.
2. Với `a.equals(b) == true`, `a.hashCode() == b.hashCode()` cũng đúng theo hợp đồng hash; Optional rỗng có hash code bằng `0`.
3. `Optional.empty()` và `Optional.ofNullable(null)` đều không chứa giá trị, nên bằng nhau. Chúng **không** bằng một Optional hiện diện, cũng không bằng trực tiếp chuỗi bên trong.
4. `HashSet` còn hai phần tử phân biệt vì trùng lặp được xử lý theo equals/hashCode; không so sánh identity của Optional.
5. Lớp `CustomerId` tự định nghĩa `equals/hashCode` theo `code`. Do đó hai Optional chứa hai CustomerId có cùng mã so sánh bằng nhau.
6. `OptionalInt.of(7)` bằng một OptionalInt khác cũng chứa `7`, nhưng không bằng `Optional<Integer>` chứa `7`.
7. `OptionalDouble` đối xử với `NaN` như hai giá trị bằng nhau theo `Double.compare`, đồng thời phân biệt `-0.0` và `+0.0`.

## 8. Bắt đầu đúng từ `of`, `ofNullable` và `empty`

Ba factory method cơ bản:

```java
Optional<String> hasName = Optional.of("Alice");      // Có giá trị
Optional<String> absent = Optional.empty();           // Không có
Optional<String> fromMaybeNull = Optional.ofNullable(
    findNullableName());                              // Có hoặc không
```

Trong đoạn minh họa, `findNullableName()` là hàm giả định trả `String` hoặc `null`; nó không được định nghĩa trong snippet. Cách chọn:

- `Optional.of(value)`: dùng khi **biết chắc value khác null**, và muốn báo lỗi nếu giả định sai.
- `Optional.ofNullable(value)`: dùng khi đầu vào **có thể null** và muốn biểu diễn null thành trạng thái rỗng.
- `Optional.empty()`: dùng khi **chủ động trả về “không có kết quả”**.

Không tạo biến `Optional` rồi gán `null` cho chính biến đó:

```java
Optional<String> result = null; // Sai về thiết kế API

// Đúng:
Optional<String> result2 = Optional.empty();
```

Theo tài liệu `Optional`, một biến có kiểu Optional **không nên bản thân là `null`**. Trạng thái vắng mặt là `Optional.empty()`.

## 9. Lấy và chuyển đổi giá trị: phân biệt “bằng nhau” với “có dữ liệu”

Hai câu hỏi độc lập:

- **Presence:** `optional.isPresent()` (Java 8+) hoặc `optional.isEmpty()` (Java 11+) trả lời có giá trị hay không.
- **Equality:** `optionalA.equals(optionalB)` trả lời hai Optional có cùng ngữ nghĩa giá trị hay không.

Khi cần dùng dữ liệu, ưu tiên thao tác có hợp đồng xử lý rỗng, không mặc định gọi `get()`:

```java
Optional<String> name = Optional.ofNullable(input);

// Chọn giá trị dự phòng:
String displayed = name.orElse("Unknown");

// Chỉ tính giá trị dự phòng khi Optional rỗng:
String lazy = name.orElseGet(() -> expensiveFallback());

// Chuyển đổi khi giá trị có mặt:
Optional<Integer> length = name.map(String::length);

// Kiểm tra khi có dữ liệu:
name.ifPresent(value -> System.out.println(value));
```

Đây là snippet cần biến `input` và hàm `expensiveFallback()` do ứng dụng cung cấp. **`orElse(x)` tính đối số `x` trước khi gọi phương thức**, trong khi `orElseGet(supplier)` chỉ chạy supplier khi Optional rỗng. Hai method này phục vụ lấy giá trị, không dùng để kiểm tra hai Optional có bằng nhau hay không.

Nếu `map` trả `null` thì kết quả là `Optional.empty()`; khi `flatMap` mapper phải trả một `Optional` **khác null**. Không tạo `Optional<Optional<T>>` nếu pipeline có thể trả thẳng một Optional bằng `flatMap`. Nếu không có dữ liệu, `get()` sẽ ném `NoSuchElementException`; nên có chính sách dự phòng hoặc ném lỗi có ý nghĩa bằng `orElseThrow(...)`.

## 10. So sánh Optional và so sánh nghiệp vụ không nhất thiết là một

`Optional.equals` được định nghĩa rõ, nhưng đôi khi nghiệp vụ yêu cầu phép so sánh khác so với `equals` của kiểu bên trong.

Ví dụ, tên người dùng `"Alice"` và `"alice"` khác nhau theo `String.equals`. Nếu nghiệp vụ yêu cầu không phân biệt chữ hoa/thường, hãy **lấy/chuẩn hóa giá trị** một cách có chủ đích, không dùng `==` để so sánh hai Optional:

```java
Optional<String> firstName = Optional.of("Alice");
Optional<String> secondName = Optional.of("alice");

boolean sameIgnoringCase =
    firstName.isPresent() && secondName.isPresent()
        && firstName.get().equalsIgnoreCase(secondName.get());
// true, vì đã kiểm tra presence trước khi get().
```

Đây là snippet chạy được trong method khi đã import `Optional`. Tuy nhiên, so sánh bằng `equalsIgnoreCase` **không tự động** thay đổi hợp đồng `Optional.equals`; nếu cần khóa nghiệp vụ không phân biệt hoa/thường, hãy thiết kế key chuẩn hóa và `equals/hashCode` thống nhất thay vì gán những quy tắc khác nhau tại từng nơi sử dụng.

Nếu đối tượng chứa là DTO có nhiều trường, hãy quyết định **trường nào tạo ra danh tính nghiệp vụ**. Một `CustomerId` chỉ chứa mã bất biến có thể là khóa tốt hơn toàn bộ DTO có trạng thái có thể thay đổi.

## 11. Những lỗi hay gặp và cách sửa

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `optA == optB` | So sánh reference, không phải nội dung. | `optA.equals(optB)`. |
| `opt == Optional.empty()` | Dựa vào singleton không được cam kết. | `!opt.isPresent()` (Java 8) hoặc `opt.isEmpty()` (Java 11+). |
| `synchronized(opt)` | Dùng monitor của value-based instance. | Lock độc lập có identity được kiểm soát. |
| `System.identityHashCode(opt)` | Hash theo identity, không theo giá trị. | `opt.hashCode()` khi cần băm giá trị. |
| `Optional.of(null)` | Ném `NullPointerException`. | `Optional.ofNullable(possiblyNull)` nếu null nghĩa là vắng mặt. |
| `Optional<String> opt = null` | Đánh mất mô hình hóa absence. | Trả `Optional.empty()` khi không có kết quả. |
| `Optional.of(dtoA).equals(Optional.of(dtoB))` luôn `true` vì “nội dung giống” | DTO có thể chưa định nghĩa `equals`. | Thiết kế `equals/hashCode` hoặc so sánh thuộc tính nghiệp vụ. |
| Đổi mutable object đang dùng trong khóa hash | `hashCode` có thể thay đổi; map/set không tìm được như cũ. | Khóa bất biến, quản lý ownership. |
| So sánh `OptionalInt` với `Optional<Integer>` | Là hai kiểu đối tượng khác nhau. | So giá trị primitive có kiểm tra present nếu nghiệp vụ yêu cầu. |
| Gọi `get()` chỉ để test rỗng | Ném exception khi absent. | `isPresent/isEmpty` hoặc xử lý bằng `map/orElse...`. |
| Dùng `Optional.isEmpty()` trong code cần tương thích Java 8 | `isEmpty` chỉ xuất hiện từ Java 11. | `!isPresent()` cho mã Java 8. |

### 11.1. Không lạm dụng “value-based” để tối ưu sai

Không tính toán dựa trên việc `Optional.of(...)` có tạo object trên heap hay không; Java API không cam kết chi tiết cấp phát và trình tối ưu JIT có thể thay đổi. Nếu hiệu năng quan trọng, hãy đo bằng benchmark phù hợp. Không biến `Optional` thành singleton hay lock để “tiết kiệm object”. Sử dụng `Optional` khi cần diễn đạt **có hoặc không có một kết quả**, và chọn cấu trúc dữ liệu khác khi nó thể hiện nghiệp vụ rõ hơn.

### 11.2. Optional chủ yếu dành cho giá trị trả về

`Optional` rất phù hợp với các API như:

```java
Optional<CustomerId> findCustomerIdByEmail(String email);
```

Đây là chữ ký hàm minh họa; `CustomerId` là class ở ví dụ mục 7. Nó diễn đạt rằng email có thể không ánh xạ đến khách hàng nào.

Đừng mặc định biến mọi field, tham số constructor hay tập hợp thành Optional. Chẳng hạn, `List<Optional<CustomerId>>` thường khiến mô hình phức tạp nếu ý nghĩa dữ liệu chỉ là danh sách khách hàng đã tìm được; chỉ dùng khi từng vị trí có ý nghĩa “không có giá trị”. `Optional` là lựa chọn API hợp lệ, không phải sự thay thế máy móc cho mọi nullable field.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Hai lời gọi `Optional.of("x")` có chắc trả về cùng một reference không?

**Đáp án:** không có cam kết. `equals` trả `true` do cùng giá trị chuỗi; `==` không phù hợp làm tiêu chí so sánh.

**Câu 2.** `Optional.empty()` có luôn là một singleton không?

**Đáp án:** tài liệu không bảo đảm. Kiểm tra absence bằng `isPresent/isEmpty`, so sánh kết quả bằng `equals`.

**Câu 3.** Nếu `Optional.of(user1).equals(Optional.of(user2))` trả `false` dù hai người dùng có cùng ID, phải sửa gì?

**Đáp án:** kiểm tra `equals` của kiểu `User`. Nếu nghiệp vụ cần so theo ID, định nghĩa equality đúng hoặc so trực tiếp các ID; không sửa bằng cách dùng `==` cho Optional.

**Câu 4.** Vì sao hashCode của hai Optional bằng nhau chưa đủ kết luận hai Optional bằng nhau?

**Đáp án:** hash code có thể va chạm. Phải kiểm tra `equals`.

**Câu 5.** Tại sao không dùng `Optional` làm monitor lock?

**Đáp án:** đây là value-based class, không bảo đảm danh tính đối tượng riêng hay monitor ổn định cho đồng bộ; các hành vi dựa trên identity có thể không đoán trước hoặc thay đổi theo JVM.

**Câu 6.** `OptionalDouble.of(Double.NaN)` so với một OptionalDouble chứa `NaN` khác bằng `equals` cho kết quả gì?

**Đáp án:** `true` do `Double.compare`. `OptionalDouble.of(-0.0)` với `OptionalDouble.of(+0.0)` trả `false`.

**Câu 7.** Hai Optional rỗng có kiểu `Optional<String>` và `Optional<Integer>` có bằng nhau theo `equals` không?

**Đáp án:** có, nếu cả hai cùng rỗng. Điều này không có nghĩa chúng gán chéo kiểu trong Java hay tương đương về ý nghĩa nghiệp vụ.

## 13. Tài liệu tham khảo chính thức

Các API và hợp đồng trong bài có từ Java 8 hoặc được bổ sung ở các phiên bản sau như đã ghi rõ; chúng vẫn được hỗ trợ trong Java hiện đại:

- [`Optional<T>` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): value-based class, hợp đồng `equals/hashCode`, `empty` không bảo đảm singleton, `isPresent` và `isEmpty`.
- [Value-based classes — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/ValueBased.html): đặc điểm identity và các thao tác nên tránh, bao gồm identity equality và synchronization.
- [`OptionalInt` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html): phiên bản primitive `int`.
- [`OptionalLong` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html): phiên bản primitive `long`.
- [`OptionalDouble` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalDouble.html): equality dựa vào `Double.compare`.
- [`Double` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html): quy tắc `NaN`, `-0.0`, `+0.0` và `Double.compare`.
