# Kiểm thử dữ liệu rỗng, giới hạn số học và kiểu kết quả trong Java 11

**Chủ đề cha:** Tiện ích dữ liệu  
**Mục tiêu:** Thiết kế bài kiểm thử bao phủ dữ liệu thiếu/rỗng, các giá trị sát giới hạn kiểu số và kiểu kết quả mà API cam kết trả về. Các ví dụ sử dụng Java 11 và những API vẫn còn phù hợp trên JDK hiện đại.

Một hàm chạy đúng với đầu vào “bình thường” chưa đủ để đáng tin cậy. Các lỗi khó phát hiện thường xuất hiện ở những vùng ranh giới: chuỗi `null` khác chuỗi rỗng, phép cộng `int` tràn âm thầm, phép chia nguyên làm mất phần thập phân, hoặc hàm trả về `OptionalDouble.empty()` khi không có dữ liệu. Điều cần kiểm thử là **hợp đồng dữ liệu và hành vi**, bao gồm cả kết quả hợp lệ lẫn lỗi được dự kiến.

## 1. Học xong cần làm được gì?

1. Phân biệt `null`, chuỗi rỗng, chuỗi chỉ có whitespace, collection rỗng và `Optional.empty()`; xác định cách xử lý từng trường hợp.
2. Viết ca kiểm thử cho **giá trị nhỏ nhất, lớn nhất, ngay sát biên và vượt biên** của `int`/`long`; nhận diện overflow, chuyển kiểu và chia nguyên.
3. Dùng `Math.addExact`, `Math.multiplyExact`, `Math.toIntExact`, `BigInteger` và `BigDecimal` đúng mục đích.
4. Phân biệt kiểu trả về `int`, `long`, `double`, `BigDecimal`, `Optional<T>` và `OptionalDouble`; kiểm thử cả kiểu và ý nghĩa của giá trị.
5. Kiểm tra NaN/Infinity, độ chính xác số thực và quy tắc so sánh `BigDecimal`.
6. Tạo và chạy một bộ kiểm thử không phụ thuộc thư viện ngoài bằng `javac --release 11`; biết chuyển cùng ma trận ca kiểm thử vào bộ kiểm thử tự động của dự án.

## 2. Tư duy kiểm thử: đầu vào, hợp đồng và kiểu kết quả

Với mỗi hàm, xác định trước bốn phần:

| Thành phần | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| Miền đầu vào | `null` có hợp lệ không? Khoảng trắng có ý nghĩa không? Có giới hạn độ lớn không? | `parseLabel(null)` là lỗi lập trình; `parseLabel("   ")` là không có nhãn |
| Giá trị thành công | Giá trị nào được coi hợp lệ? Có cần chuẩn hóa? | `parseLabel(" An ")` tạo `Optional.of("An")` |
| Không có kết quả | Biểu diễn bằng giá trị nào? | `Optional.empty()` hay `OptionalDouble.empty()`, không phải `null` |
| Đầu vào/lập luận không hợp lệ | Ném exception nào, hay trả lỗi có kiểu? | `Math.toIntExact` ném `ArithmeticException` khi vượt miền `int` |

Trước khi viết test, hãy chọn rõ giữa **“không có kết quả là hợp lệ”** và **“đầu vào sai hợp đồng”**. Hai trường hợp này không nhất thiết có cùng hành vi. Ví dụ, một chuỗi toàn khoảng trắng có thể được xem là “không có nhãn”; còn gọi API với tham số `null` trái hợp đồng có thể cần `NullPointerException` hoặc lỗi validation riêng.

Không nên viết kiểm thử dựa trên giả định “mọi loại rỗng đều giống nhau”; chính sách phải bắt nguồn từ yêu cầu của API và nghiệp vụ.

## 3. Phân biệt chính xác các dạng dữ liệu rỗng

### 3.1 Chuỗi `null`, `isEmpty()` và `isBlank()`

| Đầu vào | `s == null` | `s.isEmpty()` | `s.isBlank()` | Diễn giải |
|---|---|---|---|---|
| `null` | `true` | Ném `NullPointerException` nếu gọi | Ném `NullPointerException` nếu gọi | Không có đối tượng `String` |
| `""` | `false` | `true` | `true` | Chuỗi độ dài 0 |
| `"   "` | `false` | `false` | `true` | Có ký tự, toàn whitespace |
| `"\t\n"` | `false` | `false` | `true` | Tab và LF là whitespace |
| `" An "` | `false` | `false` | `false` | Có nội dung |
| `"A\nB"` | `false` | `false` | `false` | Chuỗi nhiều dòng có nội dung |

`String.isBlank()` có từ Java 11, dùng `Character.isWhitespace`. Đây là một quy tắc Unicode cụ thể; không đồng nghĩa với mọi ký tự trông giống khoảng trắng. `String.strip()` cũng dựa trên quy tắc whitespace và có từ Java 11. Nếu dữ liệu bắt buộc tuân thủ cách chuẩn hóa Unicode/không gian ký tự riêng của nghiệp vụ, cần kiểm thử các ký tự thực tế mà hệ thống nhận.

**Lưu ý thứ tự:** `s.isBlank()` không an toàn khi `s == null`. Nếu API chấp nhận null, kiểm tra trước. Nếu null là lỗi, dùng `Objects.requireNonNull(s, "s")` để thể hiện rõ hợp đồng.

Ví dụ API phân biệt null (lỗi) với nhãn trắng (không có kết quả):

```java
static Optional<String> parseLabel(String raw) {
    Objects.requireNonNull(raw, "raw");
    String normalized = raw.strip();
    return normalized.isBlank()
            ? Optional.empty()
            : Optional.of(normalized);
}
```

Đây là **đoạn phương thức** cần đặt trong một class và import `java.util.Objects`, `java.util.Optional`; chương trình chạy độc lập hoàn chỉnh nằm ở mục 8.

Trong chính sách này, `parseLabel(null)` ném `NullPointerException`; `parseLabel("")` và `parseLabel("  ")` trả `Optional.empty()`; `parseLabel(" An ")` trả `Optional.of("An")`. Một API khác có thể dùng `Optional.ofNullable(raw)` để coi null là vắng mặt, nhưng đó là **quyết định hợp đồng khác** và cần ca kiểm thử khác.

### 3.2 Collection, Stream và Optional rỗng

- `List.of()` tạo một danh sách không có phần tử (`isEmpty() == true`). Một danh sách **rỗng** khác với tham chiếu danh sách `null`.
- `List.of(null)` ném `NullPointerException`: các collection factory `of` không cho phép phần tử `null`. Không được dùng ví dụ này để biểu diễn “danh sách có một mục rỗng”.
- `Stream.empty()` là stream không có phần tử. `findFirst()` trả `Optional.empty()`; `count()` trả `0L` có kiểu `long`.
- `Optional.empty()` là **một đối tượng Optional hợp lệ** biểu thị không có giá trị. Không trả về `null` ở nơi khai báo kiểu `Optional<T>`; `Optional.of(null)` ném `NullPointerException`.
- `Optional.isEmpty()` (có từ Java 11) trả `true` khi không có giá trị, đối nghĩa với `isPresent()`. Nó không cho phép gọi method trên bản thân biến Optional đang là `null`.
- `IntStream.empty().average()` trả `OptionalDouble.empty()`. Chỉ gọi `getAsDouble()`/`orElseThrow()` khi đã xác định chính sách cho trường hợp trống.

**Ví dụ ý nghĩa kiểu kết quả:**

```java
List<Integer> values = List.of();
OptionalDouble average = values.stream()
        .mapToInt(Integer::intValue)
        .average();
System.out.println(average.isEmpty()); // true
```

Đây là **trích đoạn trong một phương thức** với import `List`, `OptionalDouble`; ví dụ đầy đủ ở mục 8.

### 3.3 Trạng thái rỗng phải được kiểm thử theo ngữ cảnh

Với hàm nhận chuỗi, tối thiểu thử `null`, `""`, chuỗi chỉ có khoảng trắng, chuỗi bình thường và chuỗi có whitespace ở đầu/cuối. Với hàm nhận danh sách, thử `null`, danh sách rỗng, một phần tử, nhiều phần tử và phần tử `null` nếu API cho phép nhận danh sách có null.

Với kết quả trả về `Optional`, kiểm tra cả **nhánh có giá trị** và **nhánh không có giá trị**. Đừng chỉ kiểm tra `isPresent()` mà quên xác minh giá trị bên trong, hoặc chỉ kiểm tra nhánh thành công rồi để `NoSuchElementException` xuất hiện bất ngờ khi rỗng.

Khi muốn tạo giá trị mặc định tốn tài nguyên, cần phân biệt `optional.orElse(expensiveFallback())` (biểu thức mặc định được tính trước khi gọi) với `optional.orElseGet(() -> expensiveFallback())` (chỉ gọi supplier khi Optional rỗng).

## 4. Giới hạn số nguyên: kiểm thử sát biên và tràn số

Trong Java 11, `int` là số nguyên có dấu 32 bit, `long` là số nguyên có dấu 64 bit. Hai miền giá trị cố định:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|
| `int` | -2.147.483.648 (`Integer.MIN_VALUE`) | 2.147.483.647 (`Integer.MAX_VALUE`) |
| `long` | -9.223.372.036.854.775.808 (`Long.MIN_VALUE`) | 9.223.372.036.854.775.807 (`Long.MAX_VALUE`) |

Số nguyên nguyên thủy trong Java **không tự ném exception khi phép cộng/trừ/nhân tràn miền**. Kết quả sẽ theo ngữ nghĩa số nguyên có dấu được định nghĩa của Java, có thể thành số âm hoặc giá trị không mong muốn. Do đó, kiểm thử cần bao gồm **ngay sát biên hợp lệ** và **vượt biên một đơn vị**, thay vì chỉ số 0 hoặc số nhỏ.

### 4.1 Kiểm thử phép toán chính xác

`Math.addExact(a, b)`, `Math.subtractExact(a, b)`, `Math.multiplyExact(a, b)` và `Math.toIntExact(longValue)` ném `ArithmeticException` nếu kết quả không nằm trong miền tương ứng. Những phương thức này còn được dùng rộng rãi trên các JDK hiện đại vì giúp thể hiện yêu cầu **không chấp nhận overflow**.

```java
int valid = Math.addExact(Integer.MAX_VALUE - 1, 1);
int invalid = Math.addExact(Integer.MAX_VALUE, 1);
// Lệnh thứ hai ném ArithmeticException.
```

Trường hợp hợp lệ cần assert kết quả `Integer.MAX_VALUE`. Trường hợp vượt biên cần assert **đúng loại exception**; không kiểm thử theo kiểu “có lỗi gì đó là được”.

**Các ca biên gợi ý:**

| Phép toán | Input | Kỳ vọng |
|---|---|---|
| `Math.addExact` | `Integer.MAX_VALUE - 1` và `1` | `Integer.MAX_VALUE` |
| `Math.addExact` | `Integer.MAX_VALUE` và `1` | `ArithmeticException` |
| `Math.subtractExact` | `Integer.MIN_VALUE` và `1` | `ArithmeticException` |
| `Math.multiplyExact` | `Integer.MAX_VALUE` và `2` | `ArithmeticException` |
| `Math.toIntExact` | `(long) Integer.MAX_VALUE` | `Integer.MAX_VALUE` |
| `Math.toIntExact` | `(long) Integer.MAX_VALUE + 1` | `ArithmeticException` |
| `Integer.parseInt` | `"2147483647"` | `Integer.MAX_VALUE` |
| `Integer.parseInt` | `"2147483648"` | `NumberFormatException` |

Chính sách lỗi thay đổi theo hàm: `Math.toIntExact` ném `ArithmeticException`, còn `Integer.parseInt` với chuỗi vượt miền `int` ném `NumberFormatException`. Nếu hệ thống dùng các hàm bọc quanh, hãy kiểm thử hợp đồng thực tế của tầng bọc đó.

### 4.2 Mở rộng kiểu **trước** khi thực hiện phép tính

```java
long wrong = Integer.MAX_VALUE + 1;
long right = (long) Integer.MAX_VALUE + 1;
```

Biểu thức gán vào `wrong` được tính dưới dạng `int` trước nên tràn thành `-2147483648`, rồi mới chuyển sang `long`. Biểu thức `right` ép kiểu toán hạng đầu tiên sang `long` trước khi cộng, nên kết quả là `2147483648L`.

Đây là lý do khi hàm cần trả về tổng/số lượng có thể vượt `int`, thay đổi **kiểu biến nhận kết quả** là chưa đủ: phải kiểm tra kiểu của **biểu thức tính toán**. Nếu cả `long` cũng không đủ, dùng `BigInteger` thay vì kỳ vọng primitive mở rộng vô hạn.

### 4.3 Giá trị âm nhỏ nhất và trị tuyệt đối

`Math.abs(Integer.MIN_VALUE)` **trả lại `Integer.MIN_VALUE`**, tức vẫn âm, vì trị tuyệt đối dương `2147483648` không biểu diễn được bằng `int`. Không nên kiểm thử với kỳ vọng “`Math.abs` luôn không âm”.

Nếu miền ứng dụng thực sự cần trị tuyệt đối của mọi `int`, có thể chuyển thành `long` **trước**:

```java
long magnitude = Math.abs((long) Integer.MIN_VALUE);
// magnitude == 2147483648L
```

Không có kiểu nguyên thủy có dấu rộng hơn `long` để bảo toàn trị tuyệt đối của mọi `long`; `BigInteger.valueOf(Long.MIN_VALUE).abs()` là lựa chọn phù hợp nếu cần độ lớn đó.

## 5. Chia nguyên, kết quả số thực và giá trị đặc biệt

### 5.1 Phép chia và làm tròn

- `7 / 2` có hai toán hạng `int`, kết quả `int` là `3` vì phần lẻ bị cắt.
- `7 / 2.0` có toán hạng `double`, kết quả `double` là `3.5`.
- `-7 / 2` cho `-3` trong chia nguyên Java: làm tròn về 0.
- `Math.floorDiv(-7, 2)` cho `-4`: làm tròn xuống âm vô cực.
- `7 / 0` (phép chia nguyên với số chia 0) ném `ArithmeticException`; phép chia `double` cho 0 có thể tạo Infinity hoặc NaN.

Cần định nghĩa rõ quy tắc làm tròn nghiệp vụ. Khi tính số trang, phân nhóm, phí hay chỉ số, **không tự thay** phép chia nguyên bằng `double` hoặc `Math.floorDiv` mà chưa đối chiếu ý nghĩa mong muốn.

### 5.2 NaN, Infinity và độ chính xác nhị phân

`double` và `float` là số thực dấu phẩy động nhị phân, không thể biểu diễn chính xác mọi số thập phân. Kiểm thử tránh giả định phép tính với số thực luôn có kết quả đúng từng bit. Khi kiểm tra số gần đúng, lựa chọn dung sai phải căn cứ độ lớn dữ liệu và yêu cầu, không dùng một epsilon tùy tiện cho mọi phép tính.

```java
boolean nan = Double.isNaN(0.0 / 0.0);       // true
boolean infinite = Double.isInfinite(1.0 / 0.0); // true
boolean finite = Double.isFinite(2.5);       // true
```

`Double.NaN == Double.NaN` trả `false`. Để kiểm tra NaN, dùng `Double.isNaN`; để xác nhận số hữu hạn, dùng `Double.isFinite`. Kiểu trả về của các phép kiểm tra này là `boolean`.

### 5.3 `BigDecimal` và `BigInteger` khi miền số yêu cầu

Với dữ liệu tiền tệ hay phép tính thập phân cần độ chính xác theo hợp đồng, sử dụng `BigDecimal` với đầu vào thập phân dưới dạng chuỗi hoặc một cách chuyển đổi phù hợp:

```java
BigDecimal sum = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
boolean exact = sum.compareTo(new BigDecimal("0.3")) == 0;
```

`exact` là `true`. Tránh tạo giá trị decimal nghiệp vụ bằng `new BigDecimal(0.1)` vì tham số `0.1` đã là giá trị `double` xấp xỉ. Khi dùng `BigDecimal.divide` với kết quả thập phân vô hạn tuần hoàn, cần khai báo scale/`RoundingMode` phù hợp nếu không muốn phép chia ném `ArithmeticException`.

**So sánh `BigDecimal`:**

- `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả `false` vì `equals` xét cả giá trị và scale.
- `new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0` trả `true` vì so sánh độ lớn số học.
- Khi kiểm thử **giá trị số** không quan tâm scale, có thể dùng `compareTo`; khi hợp đồng bao gồm số chữ số thập phân, phải kiểm tra cả `scale()`/biểu diễn theo yêu cầu.

`BigInteger` dùng cho số nguyên vượt phạm vi `long`; `BigDecimal` dùng cho số thập phân có độ chính xác/scale cần quản lý. Hai kiểu đều là object; phép toán trả object mới và không làm thay đổi đối tượng cũ. Kiểm thử nên xác minh **kiểu trả về** và các giá trị tương ứng, không chỉ in kết quả để nhìn.

## 6. Kiểu kết quả là một phần của hợp đồng API

Kiểu mà một phương thức công bố quyết định cách phía gọi xử lý kết quả. Một số ví dụ thực tế trên Java 11:

| Khai báo / API | Kiểu kết quả | Trường hợp đặc biệt cần kiểm thử |
|---|---|---|
| `String.isBlank()` | `boolean` | `""`, whitespace, chuỗi có chữ, `null` ở nơi gọi |
| `String.lines()` | `Stream<String>` | Chuỗi rỗng tạo stream rỗng; sau khi thu thập là danh sách |
| `Collection.isEmpty()` | `boolean` | Collection rỗng và đối tượng null |
| `Stream.count()` | `long` | Stream rỗng trả `0L` |
| `IntStream.sum()` | `int` | Dữ liệu cộng có thể tràn `int` |
| `IntStream.average()` | `OptionalDouble` | Stream rỗng trả `OptionalDouble.empty()` |
| `Stream.findFirst()` | `Optional<T>` | Không phần tử trả `Optional.empty()` |
| `Math.addExact(int,int)` | `int` hoặc ném `ArithmeticException` | Sát/vượt `Integer.MAX_VALUE` |
| `Math.toIntExact(long)` | `int` hoặc ném `ArithmeticException` | Dữ liệu vượt miền `int` |
| `BigDecimal.add(BigDecimal)` | `BigDecimal` | Scale/kết quả số thập phân |
| `Integer.parseInt(String)` | `int` hoặc ném `NumberFormatException` | Chuỗi sai định dạng, vượt miền |

**Ba kiểu dễ nhầm:**

1. `Optional<String>` mang ý nghĩa “có thể có hoặc không có chuỗi”.
2. `OptionalDouble` là dạng chuyên biệt cho primitive `double`; phải lấy giá trị qua `orElse(...)`, `orElseThrow()` hoặc kiểm tra trạng thái. Không coi `OptionalDouble.empty()` là số `0.0`.
3. `double` có thể chứa NaN/Infinity; “có một giá trị `double`” **không đồng nghĩa** với “có số hữu hạn hợp lệ theo nghiệp vụ”.

Không cố dùng `null`, chuỗi `""`, số `0` và `Optional.empty()` thay thế cho nhau. Ví dụ trung bình thực sự bằng `0.0` là kết quả **hợp lệ**, khác hoàn toàn không có phần tử để tính trung bình.

### Sự khác biệt giữa kiểu lúc biên dịch và giá trị lúc chạy

Java kiểm tra kiểu tĩnh. Từ Java 10, `var` giúp suy luận kiểu biến cục bộ; nó không làm kiểu trở thành dynamic:

```java
var average = List.of(2, 4).stream()
        .mapToInt(Integer::intValue)
        .average();
// Kiểu suy ra là OptionalDouble, không phải double.
```

Khi xây dựng API, hãy đặt tên, kiểu trả về và chính sách lỗi nhất quán. Đừng trả `Object` chỉ để né quyết định giữa “có giá trị / không có giá trị / lỗi”, vì người dùng API sẽ phải tự kiểm tra và ép kiểu ở runtime.

## 7. Lập ma trận kiểm thử theo lớp tương đương và giá trị biên

Chọn ca kiểm thử từ **nhóm hành vi** và **rìa của miền giá trị**. Ma trận ban đầu có thể như sau:

| Mục tiêu | Ca hợp lệ | Ca biên / rỗng | Ca lỗi hoặc khác kiểu |
|---|---|---|---|
| Chuẩn hóa nhãn | `"  An  "` → `"An"` | `""`, `" \t\n"` → `Optional.empty()` | `null` → `NullPointerException` theo hợp đồng |
| Trung bình `IntStream` | `[2, 4]` → `OptionalDouble` chứa `3.0` | `[]` → `OptionalDouble.empty()` | Danh sách chứa null → lỗi nếu không cho phép |
| Cộng `int` chính xác | `MAX_VALUE - 1 + 1` → `MAX_VALUE` | `0 + 0`, `MIN_VALUE + 0` | `MAX_VALUE + 1` → `ArithmeticException` |
| Chuyển `long` → `int` | `MAX_VALUE` giữ nguyên | `MIN_VALUE` giữ nguyên | `MAX_VALUE + 1L` → `ArithmeticException` |
| Parse `int` | `"0"`, `"-1"`, `"2147483647"` | `"-2147483648"` | `"2147483648"` → `NumberFormatException` |
| Chia nguyên | `7 / 2 == 3` | `-7 / 2 == -3` | Chia nguyên cho `0` → `ArithmeticException` |
| Số thực đặc biệt | `2.5` hữu hạn | `0.0 / 0.0` là NaN | `1.0 / 0.0` là Infinity |
| `BigDecimal` | `0.1 + 0.2 == 0.3` theo `compareTo` | `1.0` và `1.00` bằng nhau về giá trị | `equals` phân biệt scale |

Với giá trị biên, nên kiểm tra cả **ngay trước**, **ngay tại** và **ngay sau** ngưỡng nếu kiểu cho phép biểu diễn giá trị đó. Khi trường hợp vượt ngưỡng không thể biểu diễn bằng chính kiểu tham số, dựng bằng kiểu rộng hơn để thử bước chuyển đổi hoặc parser, chẳng hạn `(long) Integer.MAX_VALUE + 1` hay chuỗi `"2147483648"`.

Với kết quả có kiểu `Optional`, xác minh cả phần tử có mặt và ý nghĩa của giá trị. Với exception, xác minh **đúng exception** và rằng điều kiện gây lỗi đúng là điều kiện đang kiểm thử. Không dùng `catch (Exception ignored)` để khiến mọi lỗi đều được tính là “đạt”.

## 8. Chương trình Java 11 chạy được: 20 ca kiểm thử biên

Ví dụ dưới đây không yêu cầu Maven, Gradle hay thư viện kiểm thử ngoài. Phương thức `check` ném `AssertionError` khi điều kiện sai; `checkThrows` yêu cầu một loại exception cụ thể. Đây là cách để ví dụ **luôn kiểm tra khi chạy**: lệnh `assert` của Java mặc định có thể bị tắt nếu không truyền `-ea`, nên không dựa vào nó để tạo kết quả demo.

Lưu thành file **`DataBoundaryTests.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalDouble;

public class DataBoundaryTests {
    private static int checks = 0;

    static Optional<String> parseLabel(String raw) {
        Objects.requireNonNull(raw, "raw");
        String normalized = raw.strip();
        return normalized.isBlank()
                ? Optional.empty()
                : Optional.of(normalized);
    }

    static OptionalDouble average(List<Integer> values) {
        Objects.requireNonNull(values, "values");
        return values.stream().mapToInt(Integer::intValue).average();
    }

    static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    static void checkThrows(Class<? extends Throwable> type,
                            Runnable operation) {
        checks++;
        try {
            operation.run();
        } catch (Throwable actual) {
            if (type.isInstance(actual)) return;
            throw new AssertionError("Unexpected exception: " + actual, actual);
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        check(parseLabel("").isEmpty(), "empty input");
        check(parseLabel(" \t\n").isEmpty(), "whitespace input");
        check(parseLabel("  An  ").orElseThrow().equals("An"), "valid text");
        checkThrows(NullPointerException.class, () -> parseLabel(null));

        check(average(List.of()).isEmpty(), "empty collection");
        check(Double.compare(average(List.of(2, 4)).orElseThrow(), 3.0) == 0,
                "average result");

        check(Math.addExact(Integer.MAX_VALUE - 1, 1) == Integer.MAX_VALUE,
                "upper boundary");
        checkThrows(ArithmeticException.class,
                () -> Math.addExact(Integer.MAX_VALUE, 1));
        checkThrows(ArithmeticException.class,
                () -> Math.toIntExact((long) Integer.MAX_VALUE + 1));
        check(((long) Integer.MAX_VALUE + 1L) == 2147483648L,
                "widen before adding");

        check(new BigDecimal("0.1").add(new BigDecimal("0.2"))
                .compareTo(new BigDecimal("0.3")) == 0, "decimal addition");
        check(Double.isNaN(0.0 / 0.0), "NaN");
        check(Double.isInfinite(1.0 / 0.0), "infinity");

        check(7 / 2 == 3, "integer division");
        check(7 / 2.0 == 3.5, "floating division");
        check(Math.floorDiv(-7, 2) == -4, "negative floor");
        check(!new BigDecimal("1.0").equals(new BigDecimal("1.00")),
                "decimal scale in equals");
        check(new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0,
                "decimal numeric comparison");
        check(Math.abs(Integer.MIN_VALUE) == Integer.MIN_VALUE,
                "abs minimum limitation");
        checkThrows(NumberFormatException.class,
                () -> Integer.parseInt("2147483648"));

        System.out.println("Checks passed: " + checks + " checks");
    }
}
```

Biên dịch bằng JDK 11 hoặc JDK cao hơn có hỗ trợ target 11:

```bash
javac --release 11 -encoding UTF-8 DataBoundaryTests.java
java DataBoundaryTests
```

**Kết quả chính xác đã chạy kiểm chứng:**

```text
Checks passed: 20 checks
```

Nếu bất kỳ điều kiện nào sai, chương trình dừng với `AssertionError`; vì vậy dòng kết quả trên chỉ xuất hiện sau khi đã đi qua cả 20 phép kiểm tra.

### Giải thích thiết kế bộ kiểm thử

- **4 ca đầu:** khẳng định `""`/whitespace và `null` là hai nhóm hành vi khác nhau; dữ liệu hợp lệ sau `strip()` tạo `Optional<String>` có giá trị.
- **2 ca tiếp:** trung bình của danh sách rỗng là `OptionalDouble.empty()`; với `[2, 4]` kết quả là `3.0` thuộc kiểu `double` bên trong `OptionalDouble`.
- **4 ca số nguyên:** kiểm tra đúng ngay tại `Integer.MAX_VALUE`, overflow của `addExact`, chuyển `long` vượt miền `int` và cách mở rộng trước khi cộng.
- **3 ca decimal/float:** kiểm tra `BigDecimal` cộng chính xác, NaN và Infinity.
- **7 ca còn lại:** kiểm tra chia nguyên/chia dấu phẩy động, `Math.floorDiv` với số âm, khác biệt `equals`/`compareTo` của decimal, ngoại lệ của `Math.abs` tại số nguyên nhỏ nhất và lỗi parse vượt giới hạn.

**Giới hạn của ví dụ:** Bộ kiểm thử dùng một hàm `check` rất nhỏ để dễ đọc và chạy độc lập. Trong codebase thực tế, dùng framework kiểm thử của dự án để có báo cáo từng test, setup/teardown, parameterized tests và tích hợp CI. Điều quan trọng là **ma trận ca kiểm thử và hợp đồng kết quả**; framework chỉ là cơ chế chạy/ghi nhận.

## 9. Áp dụng vào kiểm thử tự động trong dự án thật

### 9.1 Bố cục một ca kiểm thử hữu ích

Theo cấu trúc **Arrange – Act – Assert**:

1. **Arrange:** dựng đầu vào, gồm trường hợp rỗng và biên; tránh phụ thuộc dữ liệu môi trường bất định.
2. **Act:** gọi đúng API qua bề mặt public cần kiểm thử.
3. **Assert:** kiểm tra kiểu kết quả, giá trị, trạng thái có/vắng mặt hoặc loại exception; kiểm tra tác dụng phụ nếu có.

Trong JUnit Jupiter, các assertion tương ứng là `assertEquals`, `assertTrue`/`assertFalse`, `assertThrows`; có thể dùng parameterized tests để đưa cả ma trận giá trị biên thành dữ liệu đầu vào. Ví dụ **trích đoạn minh họa trong lớp test có JUnit Jupiter trên test classpath**:

```java
@Test
void additionBeyondMaxThrows() {
    assertThrows(ArithmeticException.class,
            () -> Math.addExact(Integer.MAX_VALUE, 1));
}
```

Đoạn này cần import `org.junit.jupiter.api.Test` và `org.junit.jupiter.api.Assertions.assertThrows`, cùng dependency JUnit tương thích dự án. Nó không phải chương trình độc lập chỉ dùng JDK. Bài chạy độc lập ở mục 8 đã xác nhận hành vi tương ứng mà không cần JUnit.

### 9.2 Bổ sung những ca mà test đẹp thường bỏ sót

- **Thiếu dữ liệu:** `null`, `Optional.empty()`, collection trống, chuỗi rỗng và whitespace phải được test tách biệt theo hợp đồng.
- **Dữ liệu đúng ngay sát biên:** `MIN`, `MAX`, `0`, `-1`, `1`, bước chuyển từ `int` sang `long`, và ngưỡng giá trị quy định riêng.
- **Vượt biên và chuyển kiểu:** overflow, parse ngoài miền, làm tròn, truncation, thu hẹp từ `long` xuống `int`.
- **Đầu ra có cấu trúc:** số 0 khác không có trung bình; danh sách rỗng khác null; `Optional<T>` phải có kiểu phần tử đúng.
- **Số thực:** NaN, ±Infinity, `-0.0` khi có ý nghĩa, sai số so sánh, `BigDecimal` scale/rounding.
- **Đặc tính hệ thống:** thử trên runtime đích thực tế và với thư viện được dùng trong dự án; không suy diễn rằng chỉ biên dịch được trên JDK mới thì hành vi của mọi dependency đều giống trên JDK 11.

Khi tham số số học phải thỏa một bất biến, có thể tăng chất lượng test bằng nhiều tổ hợp có kiểm soát: ví dụ với phép cộng chính xác, nếu `Math.addExact(a,b)` không ném thì kết quả phải bằng kết quả `BigInteger.valueOf(a).add(BigInteger.valueOf(b))` sau khi bảo đảm nằm trong miền `int`. Đây là **định hướng kiểm thử theo tính chất**; cần chọn phạm vi dữ liệu và framework phù hợp khi đưa vào dự án lớn.

### 9.3 Kiểm thử exception có mục đích

Một kiểm thử “bất kỳ exception nào cũng đạt” có thể che lỗi `NullPointerException` phát sinh ngoài ý muốn trước khi code chạm trường hợp overflow. `assertThrows(ArithmeticException.class, ...)` hoặc helper kiểm tra loại lỗi cụ thể giúp phân biệt các nguồn lỗi. Nếu thông điệp exception là một phần của public contract, mới cần so khớp thông điệp; nếu không, ưu tiên loại lỗi/hành vi vì thông điệp có thể khác theo phiên bản và ngữ cảnh.

Hãy để test thất bại có nội dung dễ chẩn đoán: input đang thử, kỳ vọng, giá trị thực tế và quy tắc nghiệp vụ. Tránh kiểm thử lệ thuộc thứ tự ngẫu nhiên của collection không có thứ tự, thời gian thực, locale mặc định hoặc khác biệt encoding khi các yếu tố đó không thuộc yêu cầu.

## 10. Các lỗi thường gặp và cách sửa

| Sai lầm | Tác động | Hướng xử lý |
|---|---|---|
| Xem `null`, `""` và `"   "` là một | Che lỗi hợp đồng và làm test thiếu ca | Tách từng nhóm; dùng `isEmpty`/`isBlank` đúng nghĩa |
| Gọi `isBlank()` trực tiếp trên `null` | `NullPointerException` ngoài dự kiến | Chọn chính sách null và kiểm tra/`requireNonNull` rõ ràng |
| Trả `null` từ phương thức kiểu `Optional<T>` | Người gọi không thể tin cậy kiểu kết quả | Trả `Optional.empty()` khi không có giá trị |
| Gọi `Optional.get()` mà không xét empty | `NoSuchElementException` | Dùng `orElseThrow` có chủ đích, `orElse`, `orElseGet` hoặc xử lý nhánh rỗng |
| Gán phép cộng `int` vào `long` và nghĩ tránh overflow | Overflow xảy ra trước khi gán | Ép kiểu toán hạng trước hoặc dùng phép toán kiểm tra tràn |
| Chỉ kiểm thử giá trị 0 và 1 | Không phát hiện lỗi biên | Thử `MIN/MAX`, sát biên và vượt biên |
| Dùng `Math.abs` và mặc định không âm | `Integer.MIN_VALUE` vẫn âm | Widen trước hoặc dùng số học miền rộng |
| Coi `7 / 2` bằng `3.5` | Phép chia nguyên cắt phần thập phân | Chọn kiểu và quy tắc làm tròn đúng yêu cầu |
| Dùng `double` để so sánh tiền bằng tuyệt đối | Có sai số nhị phân | Dùng `BigDecimal` từ đầu vào thập phân phù hợp |
| So `BigDecimal` bằng `equals` khi chỉ cần giá trị số | Scale khác làm kết quả `false` | Dùng `compareTo == 0` nếu hợp đồng không yêu cầu cùng scale |
| Xem NaN là một số hữu hạn | Validation sai và kết quả downstream bất thường | Dùng `Double.isNaN`/`Double.isFinite` |
| Xem `OptionalDouble.empty()` như số 0 | Nhầm thiếu dữ liệu với trung bình thật bằng 0 | Kiểm tra `isEmpty()`/`isPresent()` |
| Dùng `assert` mặc định để chạy demo test | Assertion bị tắt nếu không có `-ea` | Dùng framework test hoặc kiểm tra chủ động ném `AssertionError` |
| Chỉ test nhánh thành công | Không phát hiện thay đổi hợp đồng lỗi | Kiểm thử đúng exception và kết quả thiếu/vượt biên |

## 11. Bài tự luyện có đáp án

**Bài 1 — dữ liệu rỗng.** Dự đoán `"".isEmpty()`, `" ".isEmpty()` và `" ".isBlank()`.  
**Đáp án:** lần lượt `true`, `false` và `true`. Với `null`, cả `isEmpty` lẫn `isBlank` đều không thể gọi trực tiếp.

**Bài 2 — vắng mặt khác 0.** Một API tính trung bình danh sách số và trả `OptionalDouble`. Kết quả với `[]` và `[0, 0]` khác nhau ra sao?  
**Đáp án:** `[]` → `OptionalDouble.empty()`; `[0, 0]` → `OptionalDouble` chứa `0.0`.

**Bài 3 — tràn và kiểu nhận.** Giá trị của `long x = Integer.MAX_VALUE + 1;` là gì?  
**Đáp án:** `-2147483648L`, vì phép cộng hai `int` đã tràn trước khi mở rộng sang `long`. Viết `(long) Integer.MAX_VALUE + 1` để có `2147483648L`.

**Bài 4 — exception đúng loại.** `Math.toIntExact((long) Integer.MAX_VALUE + 1)` và `Integer.parseInt("2147483648")` có lỗi giống nhau không?  
**Đáp án:** không. Hàm đầu ném `ArithmeticException`; hàm sau ném `NumberFormatException`.

**Bài 5 — so sánh thập phân.** Tại sao `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` trong khi `compareTo(...)` là `0`?  
**Đáp án:** `equals` xét cả giá trị và scale; `compareTo` so sánh thứ tự số học, không phân biệt scale nếu giá trị bằng nhau.

**Bài 6 — tính đúng có giới hạn.** Khi nào `Math.addExact` vẫn không giải quyết được yêu cầu phép cộng?  
**Đáp án:** nếu kết quả hợp lệ theo nghiệp vụ nhưng vượt miền `int` hoặc `long`, `addExact` sẽ ném lỗi; cần chọn kiểu miền rộng hơn (ví dụ `BigInteger`) và điều chỉnh kiểu trả về/hợp đồng.

**Bài 7 — test có khả năng phát hiện lỗi.** Vì sao test chỉ gọi `process(input)` rồi xác nhận “không ném exception” chưa đủ?  
**Đáp án:** hàm có thể trả sai kiểu, mất dữ liệu, overflow âm thầm hoặc trả kết quả vắng mặt không đúng. Phải khẳng định giá trị và trạng thái kết quả dự kiến, đồng thời thêm ca lỗi.

## 12. Tra cứu API Java chính thức

- [Java SE 11 — String](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): `isBlank`, `strip`, `isEmpty`.
- [Java SE 11 — Optional](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Optional.html) và [OptionalDouble](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/OptionalDouble.html): kết quả có thể vắng mặt.
- [Java SE 11 — Math](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, `floorDiv`, `toIntExact`.
- [Java SE 11 — Integer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Integer.html) và [Double](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Double.html): giới hạn và số thực đặc biệt.
- [Java SE 11 — BigInteger](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/math/BigInteger.html) và [BigDecimal](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/math/BigDecimal.html): số lớn, precision và scale.
- [Java SE 11 — IntStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/stream/IntStream.html): `sum`, `average` và kiểu kết quả.

**Nguyên tắc áp dụng lâu dài:** Hãy ghi hợp đồng đầu vào/đầu ra trước khi viết test. Chọn ca rỗng, ca biên, ca vượt biên và ca khác kiểu để kiểm tra điều mà API **hứa hẹn**, không chỉ điều mà chương trình tình cờ làm được với dữ liệu thuận lợi.