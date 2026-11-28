# Wrapper, autoboxing và unboxing an toàn

Java có tám kiểu dữ liệu nguyên thủy như `int`, `long`, `double` và `boolean`. Khi một API cần làm việc với đối tượng, chẳng hạn collection hoặc generic, Java cung cấp các lớp bao tương ứng: `Integer`, `Long`, `Double`, `Boolean` và những lớp còn lại. Trình biên dịch có thể tự chuyển đổi giữa giá trị nguyên thủy và đối tượng wrapper thông qua **autoboxing** và **unboxing**.

Các chuyển đổi này giúp mã nguồn gọn hơn, nhưng cũng có thể che giấu việc tạo và lấy giá trị từ đối tượng. Đặc biệt, wrapper có thể mang giá trị `null`, trong khi kiểu nguyên thủy không thể. Nếu một wrapper `null` bị unbox, chương trình ném `NullPointerException` (NPE). Bài học này trình bày cách dùng wrapper trong Java 27, nhận biết các chuyển đổi ngầm và xử lý null có chủ đích.

## 1. Tám lớp wrapper của Java

Mỗi kiểu nguyên thủy có một lớp wrapper tương ứng trong package `java.lang`:

| Kiểu nguyên thủy | Lớp wrapper | Phương thức lấy giá trị nguyên thủy |
| --- | --- | --- |
| `boolean` | `Boolean` | `booleanValue()` |
| `byte` | `Byte` | `byteValue()` |
| `short` | `Short` | `shortValue()` |
| `char` | `Character` | `charValue()` |
| `int` | `Integer` | `intValue()` |
| `long` | `Long` | `longValue()` |
| `float` | `Float` | `floatValue()` |
| `double` | `Double` | `doubleValue()` |

Đây là tám lớp wrapper được Java Language Specification quy định cho boxing và unboxing. `Void` không phải lớp wrapper thứ chín cho một giá trị nguyên thủy có thể boxing; nó đại diện cho kiểu `void` trong một số API phản chiếu.

Các lớp wrapper có những đặc điểm quan trọng:

- Là lớp tham chiếu (`reference type`), có thể lưu trong biến kiểu `Object`, collection và các cấu trúc generic.
- Là lớp `final` và đối tượng wrapper là bất biến (immutable): giá trị bên trong không thay đổi sau khi tạo.
- Có thể nhận `null`, vì biến wrapper lưu tham chiếu đến đối tượng.
- Các wrapper số `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` kế thừa `Number`; `Boolean` và `Character` không kế thừa `Number`.
- Các wrapper là value-based classes. Hãy sử dụng giá trị của chúng để so sánh, không dựa vào danh tính đối tượng hoặc dùng chúng làm khóa đồng bộ hóa.

Ví dụ, `int` không thể nhận `null`, nhưng `Integer` có thể:

```java
int quantity = 0;
Integer optionalQuantity = null;

quantity = 5;
optionalQuantity = 5;
```

Sự khác biệt này hữu ích khi `null` biểu thị dữ liệu chưa được cung cấp, chưa biết hoặc không áp dụng. Nếu miền nghiệp vụ luôn yêu cầu một con số hợp lệ, kiểu nguyên thủy thường diễn đạt ý định tốt hơn.

## 2. Boxing và autoboxing

**Boxing** là chuyển một giá trị nguyên thủy thành đối tượng wrapper tương ứng. Khi trình biên dịch tự thực hiện chuyển đổi này, ta gọi là **autoboxing**.

Ví dụ:

```java
int score = 95;
Integer boxedScore = score; // Autoboxing: int -> Integer
```

Trình biên dịch xử lý tương đương với việc gọi factory phù hợp để tạo hoặc lấy wrapper biểu diễn giá trị. Có thể viết rõ ràng bằng `Integer.valueOf`:

```java
int score = 95;
Integer boxedScore = Integer.valueOf(score);
```

Autoboxing cũng xuất hiện khi truyền đối số cho phương thức nhận wrapper, trả về wrapper hoặc thêm phần tử vào collection:

```java
import java.util.ArrayList;
import java.util.List;

public class BoxingExample {
    static void printScore(Integer score) {
        System.out.println(score);
    }

    static Integer defaultScore() {
        return 100;
    }

    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();
        scores.add(90);              // int -> Integer

        printScore(95);              // int -> Integer khi gọi phương thức
        Integer score = defaultScore();

        System.out.println(scores);
        System.out.println(score);
    }
}
```

Các generic type hiện tại phải dùng kiểu tham chiếu. Vì vậy, `List<int>` không hợp lệ; hãy dùng `List<Integer>`:

```java
List<Integer> scores = new ArrayList<>();
scores.add(80); // Boxing tự động
scores.add(90);
```

Khi một API cần lưu giá trị nguyên thủy trong cấu trúc generic, wrapper là cách biểu diễn tiêu chuẩn của Java.

## 3. Unboxing

**Unboxing** là lấy giá trị nguyên thủy từ một đối tượng wrapper. Khi trình biên dịch tự thực hiện chuyển đổi này, ta gọi là **unboxing** hoặc *auto-unboxing*.

```java
Integer boxedScore = Integer.valueOf(95);
int score = boxedScore; // Unboxing: Integer -> int
```

Viết tường minh, phép chuyển đổi tương đương với:

```java
int score = boxedScore.intValue();
```

Unboxing có thể xảy ra khi gán cho biến nguyên thủy, truyền đối số cho phương thức nhận kiểu nguyên thủy, trả kết quả từ phương thức hoặc thực hiện biểu thức số học:

```java
static int normalize(Integer value) {
    return value; // Unboxing khi trả về int
}

Integer quantity = 4;
int total = quantity + 6; // Unboxing quantity trước phép cộng
```

Một ví dụ với collection:

```java
List<Integer> scores = List.of(70, 80, 90);

int firstScore = scores.get(0); // Integer -> int
int total = scores.get(0) + scores.get(1);
```

`List.get` trả về `Integer`; khi gán hoặc cộng vào biến `int`, Java unbox giá trị. Nếu phần tử là `null`, các biểu thức đó có thể ném NPE.

### Những biểu thức dễ kích hoạt unboxing

| Biểu thức | Chuyển đổi có thể xảy ra |
| --- | --- |
| `int n = integerValue;` | `Integer` thành `int` |
| `methodTakingInt(integerValue);` | `Integer` thành `int` |
| `integerValue + 1` | Unbox trước khi cộng |
| `integerValue++` | Unbox, tăng giá trị, rồi box kết quả |
| `if (booleanValue)` | `Boolean` thành `boolean` |
| `switch (integerValue)` | Unbox giá trị selector của switch |

Không phải mọi lần dùng wrapper đều tạo ra unboxing. Ví dụ `System.out.println(integerValue)` có thể gọi overload nhận `Object`; nó không cần chuyển wrapper thành `int` chỉ để in ra.

## 4. Rủi ro NPE khi unboxing giá trị null

Đây là lỗi phổ biến nhất khi dùng wrapper. Theo JLS 5.1.8, unboxing một tham chiếu `null` ném `NullPointerException`.

```java
Integer quantity = null;
int total = quantity; // Ném NullPointerException
```

Lỗi không nhất thiết xuất hiện tại dòng gán. Nó có thể nằm trong một biểu thức trông rất bình thường:

```java
Integer stock = null;

int nextStock = stock + 1; // NPE khi unbox stock
stock++;                   // NPE khi unbox stock

Boolean enabled = null;
if (enabled) {              // NPE khi unbox enabled
    System.out.println("Enabled");
}
```

Các toán tử so sánh cũng có thể kích hoạt unboxing:

```java
Integer retryCount = null;

if (retryCount > 0) { // NPE
    System.out.println("Retrying");
}
```

Khi wrapper có thể null, hãy quyết định rõ null có ý nghĩa gì trước khi dùng nó trong phép toán hoặc điều kiện.

## 5. Các cách unboxing an toàn

### 5.1. Kiểm tra null trước khi lấy giá trị

Khi null có ý nghĩa riêng và cần xử lý theo nhánh nghiệp vụ, kiểm tra null trước khi unbox:

```java
Integer stock = findStock();

if (stock == null) {
    System.out.println("Chưa có dữ liệu tồn kho");
} else {
    int available = stock;
    System.out.println("Số lượng: " + available);
}
```

Với `Boolean` có ba trạng thái (true, false và chưa xác định), hãy giữ cả ba trạng thái:

```java
Boolean approved = loadApproval();

if (approved == null) {
    System.out.println("Chưa có quyết định");
} else if (approved) {
    System.out.println("Đã chấp thuận");
} else {
    System.out.println("Đã từ chối");
}
```

Sau nhánh kiểm tra `approved == null`, điều kiện `else if (approved)` mới an toàn để unbox.

### 5.2. Dùng giá trị mặc định khi nghiệp vụ cho phép

Nếu null thực sự có nghĩa là dùng giá trị mặc định, có thể dùng toán tử ba ngôi:

```java
Integer requestedPageSize = loadPageSize();
int pageSize = requestedPageSize != null ? requestedPageSize : 20;
```

Hoặc dùng `Objects.requireNonNullElse`:

```java
import java.util.Objects;

Integer requestedPageSize = loadPageSize();
int pageSize = Objects.requireNonNullElse(requestedPageSize, 20);
```

`requireNonNullElse` trả về giá trị đầu tiên nếu khác null; nếu không, trả về giá trị mặc định khác null. Phương thức này phù hợp khi việc thay null bằng mặc định là đúng với quy tắc nghiệp vụ. Không nên tự động thay mọi null bằng `0` hoặc `false`, vì như vậy có thể biến dữ liệu thiếu thành dữ liệu hợp lệ nhưng sai nghĩa.

### 5.3. Dùng Objects.requireNonNull khi giá trị bắt buộc

Nếu một phương thức bắt buộc nhận wrapper có giá trị, hãy xác thực ngay tại ranh giới API. `Objects.requireNonNull` tạo NPE với thông điệp rõ ràng:

```java
import java.util.Objects;

static int calculateDiscount(Integer percent) {
    int checkedPercent = Objects.requireNonNull(
        percent,
        "percent must not be null"
    );

    return checkedPercent;
}
```

Cách này làm lỗi xuất hiện gần nơi dữ liệu không hợp lệ đi vào chương trình, thay vì để nó lan tới một phép toán khác.

### 5.4. Dùng OptionalInt, OptionalLong hoặc OptionalDouble

Khi một kết quả số có thể không tồn tại và không cần giữ đối tượng wrapper, Java cung cấp các kiểu chuyên biệt:

- `OptionalInt` cho `int`.
- `OptionalLong` cho `long`.
- `OptionalDouble` cho `double`.

Ví dụ:

```java
import java.util.OptionalInt;

static OptionalInt findAge(String name) {
    if ("An".equals(name)) {
        return OptionalInt.of(28);
    }
    return OptionalInt.empty();
}

OptionalInt age = findAge("An");
int actualAge = age.orElse(-1);
```

`orElse` yêu cầu chương trình cung cấp giá trị thay thế nếu kết quả rỗng. Nếu việc không có giá trị là một trạng thái cần xử lý riêng, hãy dùng `isPresent`, `ifPresent` hoặc `orElseThrow` theo nhu cầu. `OptionalInt` không nhận `null`; nó biểu diễn trạng thái có hoặc không có một giá trị `int`.

`Optional<Integer>` vẫn là kiểu hợp lệ khi API cần làm việc với generic hoặc kết hợp với các kiểu tham chiếu khác. Chọn loại Optional theo hợp đồng API và ý nghĩa dữ liệu, không chuyển đổi máy móc mọi wrapper thành Optional chuyên biệt.

## 6. So sánh wrapper đúng cách

### 6.1. `==` so sánh tham chiếu khi cả hai toán hạng là wrapper

Với hai biến `Integer`, toán tử `==` kiểm tra chúng có tham chiếu đến cùng một đối tượng hay không. Nó không phải phép so sánh giá trị tổng quát.

```java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first == second);      // Không bảo đảm true
System.out.println(first.equals(second)); // true
```

Kết quả `==` có thể thay đổi tùy cơ chế cache và cách tạo wrapper. JLS bảo đảm một số kết quả boxing của các hằng trong những phạm vi nhất định có thể dùng cùng tham chiếu; `Integer.valueOf` luôn cache các giá trị từ -128 đến 127 và có thể cache thêm giá trị ngoài phạm vi này. Quy tắc cache không phải cơ sở để so sánh dữ liệu.

Hãy dùng `equals` để so sánh giá trị của hai wrapper cùng loại:

```java
Integer expected = 1000;
Integer actual = readValue();

if (expected.equals(actual)) {
    System.out.println("Giá trị khớp");
}
```

Nếu một trong hai tham chiếu có thể null, dùng `Objects.equals`:

```java
import java.util.Objects;

Integer expected = null;
Integer actual = readValue();

if (Objects.equals(expected, actual)) {
    System.out.println("Hai giá trị bằng nhau, kể cả khi cùng null");
}
```

### 6.2. `==` có thể unbox nếu một toán hạng là primitive

Khi một toán hạng là kiểu nguyên thủy, Java có thể unbox wrapper trước khi so sánh:

```java
Integer count = 10;
int expected = 10;

System.out.println(count == expected); // true: Integer được unbox
```

Nhưng nếu wrapper là null, phép so sánh có thể ném NPE:

```java
Integer count = null;
System.out.println(count == 0); // NPE do unboxing
```

Để mã rõ ràng, hãy kiểm tra null trước hoặc dùng `Objects.equals` khi cần so sánh hai giá trị tham chiếu.

### 6.3. Wrapper khác loại không bằng nhau theo equals

Các lớp wrapper chỉ so sánh bằng `equals` với đối tượng cùng loại:

```java
Integer integerValue = 10;
Long longValue = 10L;

System.out.println(integerValue.equals(longValue)); // false
```

Nếu cần so sánh hai kiểu số khác nhau, hãy chuyển chúng về một kiểu chung với phạm vi và độ chính xác phù hợp. Ví dụ, với số nguyên nằm trong miền `long`:

```java
Integer integerValue = 10;
Long longValue = 10L;

boolean sameValue = integerValue != null
    && longValue != null
    && integerValue.longValue() == longValue.longValue();
```

Không nên đổi mọi giá trị sang `double` để so sánh số nguyên lớn: `double` không thể biểu diễn chính xác mọi giá trị `long`. Với số thập phân cần tính chính xác, chẳng hạn tiền tệ, dùng `BigDecimal` với quy tắc scale và rounding được xác định rõ.

## 7. Wrapper trong collection, map và Stream API

### 7.1. Collection có thể chứa wrapper null

Collection generic dùng wrapper và một số collection cho phép phần tử null:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> measurements = new ArrayList<>();
measurements.add(12);
measurements.add(null); // Có thể biểu diễn dữ liệu bị thiếu
measurements.add(18);
```

Khi duyệt collection, hãy quyết định null có được chấp nhận không:

```java
for (Integer measurement : measurements) {
    if (measurement == null) {
        System.out.println("Bỏ qua phép đo bị thiếu");
        continue;
    }

    int value = measurement;
    System.out.println(value);
}
```

Nếu collection không được phép có null, hãy xác thực dữ liệu tại nơi thêm phần tử hoặc khi nhận dữ liệu từ bên ngoài.

### 7.2. Cẩn thận với Map.get

`Map.get(key)` có thể trả về null khi không có mapping; một số loại Map cũng cho phép lưu key với giá trị null. Do đó, kết quả null có thể mang hai ý nghĩa: key không tồn tại hoặc key tồn tại nhưng giá trị null.

```java
Map<String, Integer> retryLimits = new HashMap<>();
retryLimits.put("payment", null);

Integer limit = retryLimits.get("payment");
if (retryLimits.containsKey("payment")) {
    // Key tồn tại; limit vẫn có thể là null.
} else {
    // Key không tồn tại.
}
```

Nếu nghiệp vụ cần phân biệt hai trường hợp này, hãy dùng `containsKey` trước khi unbox. `getOrDefault` chỉ thay giá trị mặc định khi key không có mapping; nếu key được ánh xạ tới null, kết quả vẫn có thể là null.

### 7.3. Chuyển Stream wrapper thành primitive stream

`Stream<Integer>` làm việc với đối tượng wrapper. Khi cần tính toán số học, `mapToInt`, `mapToLong` và `mapToDouble` chuyển thành các primitive stream chuyên biệt:

```java
List<Integer> scores = List.of(70, 80, 90);

int total = scores.stream()
    .mapToInt(Integer::intValue)
    .sum();
```

Nếu stream chứa null, `Integer::intValue` sẽ ném NPE. Khi null có nghĩa là dữ liệu bị thiếu và quy tắc nghiệp vụ cho phép bỏ qua, lọc trước khi unbox:

```java
List<Integer> scores = java.util.Arrays.asList(70, null, 90);

int total = scores.stream()
    .filter(java.util.Objects::nonNull)
    .mapToInt(Integer::intValue)
    .sum();
```

Nếu null là dữ liệu không hợp lệ, hãy phát hiện lỗi thay vì âm thầm loại bỏ:

```java
int total = scores.stream()
    .mapToInt(value -> java.util.Objects.requireNonNull(
        value,
        "score must not be null"
    ))
    .sum();
```

Với dữ liệu số không cần null, dùng `int[]` và `IntStream` hoặc `long[]` và `LongStream` giúp tránh boxing không cần thiết:

```java
int[] values = {10, 20, 30};
int total = java.util.Arrays.stream(values).sum();
```

## 8. Chọn primitive hay wrapper

Hãy chọn kiểu dữ liệu theo ý nghĩa và cách sử dụng của dữ liệu:

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Biến đếm, vòng lặp, phép tính nội bộ luôn có giá trị | `int`, `long`, `double` |
| Thuộc tính có thể chưa được cung cấp hoặc không áp dụng | Wrapper như `Integer`, `Boolean` |
| Phần tử trong `List`, `Set`, `Map` generic | Wrapper như `Integer` |
| API trả về số có thể không tồn tại | `OptionalInt`, `OptionalLong`, `OptionalDouble` hoặc Optional phù hợp hợp đồng API |
| Mảng số lớn dùng cho tính toán | `int[]`, `long[]`, `double[]` |
| Luồng tính toán trên số nguyên | `IntStream`, `LongStream` |
| Số thập phân cần độ chính xác thập phân | `BigDecimal` |

Ví dụ, trong vòng lặp xử lý nhiều phần tử, dùng biến primitive làm bộ tích lũy:

```java
int total = 0;
for (int score : primitiveScores) {
    total += score;
}
```

Nếu nguồn là `List<Integer>`, hãy kiểm tra null theo hợp đồng dữ liệu rồi chuyển sang primitive trước khi thực hiện nhiều phép tính.

Autoboxing không có nghĩa mọi phép chuyển đổi luôn cấp phát một đối tượng mới: Java cho phép tái sử dụng một số giá trị wrapper và JVM có thể tối ưu trong lúc thực thi. Tuy vậy, dùng wrapper trong vòng lặp lớn vẫn có thể làm tăng chi phí bộ nhớ, boxing/unboxing và áp lực garbage collection. Khi hiệu năng quan trọng, hãy đo bằng workload thực tế và ưu tiên primitive trong đường xử lý số học nóng.

Wrapper không thay đổi quy tắc số học của kiểu nguyên thủy bên trong. Ví dụ `Integer` vẫn có miền giá trị của `int`; phép cộng vượt miền vẫn tràn số:

```java
int value = Integer.MAX_VALUE;
int overflowed = value + 1; // Tràn số theo quy tắc int
```

Nếu cần phát hiện tràn số, dùng `Math.addExact`, `Math.subtractExact` hoặc `Math.multiplyExact`:

```java
int safeTotal = Math.addExact(Integer.MAX_VALUE, 1); // ArithmeticException
```

## 9. Chuyển đổi từ String sang wrapper

Khi đọc dữ liệu từ file, biến môi trường hoặc request, hãy chọn phương thức parse theo kiểu kết quả cần nhận.

```java
String text = "250";

int primitiveValue = Integer.parseInt(text);       // Kết quả int
Integer wrapperValue = Integer.valueOf(text);      // Kết quả Integer
```

`parseInt` phù hợp khi cần tính toán với primitive. `valueOf` phù hợp khi API cần wrapper. Nếu chuỗi null, rỗng, sai định dạng hoặc nằm ngoài miền `int`, các phương thức này ném `NumberFormatException`. Hãy xác thực dữ liệu đầu vào và xử lý lỗi ở ranh giới nhận dữ liệu.

Với boolean:

```java
boolean enabled = Boolean.parseBoolean("true");
Boolean boxedEnabled = Boolean.valueOf("true");
```

`Boolean.parseBoolean` trả về `true` khi chuỗi biểu diễn `true` không phân biệt hoa thường; các chuỗi khác trả về `false`. Nếu ứng dụng cần từ chối giá trị sai định dạng như `"yes"` hoặc `"on"`, hãy xác thực chuỗi theo quy tắc đầu vào của ứng dụng trước khi chuyển đổi.

Không dùng các constructor wrapper như `new Integer(10)` hoặc `new Boolean("true")` trong mã mới. Những constructor này đã deprecated từ Java 9. Dùng autoboxing, `valueOf` hoặc phương thức `parse...` tương ứng.

## 10. Ví dụ tổng hợp: xử lý wrapper có thể null

Ví dụ sau mô tả một API nhận số lượng tùy chọn. Khi không có số lượng, chương trình báo thiếu dữ liệu; khi có giá trị, chương trình xác thực miền giá trị trước khi tính toán.

```java
import java.util.Objects;
import java.util.OptionalInt;

public class SafeWrapperExample {
    static int calculateTotal(Integer quantity, int unitPrice) {
        int checkedQuantity = Objects.requireNonNull(
            quantity,
            "quantity must not be null"
        );

        if (checkedQuantity < 0) {
            throw new IllegalArgumentException("quantity must not be negative");
        }

        return Math.multiplyExact(checkedQuantity, unitPrice);
    }

    static OptionalInt parseQuantity(String text) {
        if (text == null || text.isBlank()) {
            return OptionalInt.empty();
        }

        return OptionalInt.of(Integer.parseInt(text));
    }

    public static void main(String[] args) {
        Integer quantityFromRequest = 3; // Có thể null trong dữ liệu thực

        if (quantityFromRequest == null) {
            System.out.println("Request chưa cung cấp số lượng");
        } else {
            int total = calculateTotal(quantityFromRequest, 50);
            System.out.println("Tổng tiền: " + total);
        }

        OptionalInt parsed = parseQuantity("4");
        int quantity = parsed.orElse(0);
        System.out.println("Số lượng đã parse: " + quantity);
    }
}
```

Điểm cần chú ý:

1. `Integer` ở ranh giới API có thể null, nên chương trình kiểm tra trước khi tính toán.
2. `Objects.requireNonNull` xác nhận giá trị bắt buộc và đưa ra thông điệp lỗi cụ thể.
3. Sau khi xác thực, chương trình dùng `int` cho phép tính.
4. `Math.multiplyExact` phát hiện tràn số thay vì âm thầm trả về kết quả sai.
5. `OptionalInt` biểu diễn kết quả parse có hoặc không có giá trị mà không cần dùng `null` làm trạng thái rỗng.

## 11. Những lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| NPE tại phép cộng hoặc gán | Wrapper null bị unbox | Kiểm tra null, xác thực hoặc dùng giá trị mặc định đúng nghiệp vụ |
| Dùng `==` để so sánh hai wrapper | So sánh danh tính tham chiếu | Dùng `equals` hoặc `Objects.equals` |
| So sánh `Integer` với `Long` bằng `equals` | Hai đối tượng khác lớp | Chuyển về kiểu số chung an toàn trước khi so sánh |
| `List<int>` không biên dịch | Generic không nhận kiểu nguyên thủy | Dùng `List<Integer>` |
| Stream ném NPE ở `mapToInt` | Phần tử wrapper null bị unbox | Xác thực hoặc lọc null theo ý nghĩa dữ liệu |
| Dùng `new Integer(...)` | Constructor wrapper đã deprecated | Dùng `valueOf`, `parseInt` hoặc autoboxing |
| Phép tính số nguyên cho kết quả âm hoặc sai | Tràn miền `int`/`long` | Chọn kiểu đủ rộng hoặc dùng `Math.*Exact` |
| Dùng wrapper làm monitor `synchronized` | Wrapper là value-based, identity không được bảo đảm | Dùng một đối tượng khóa riêng (`private final Object lock`) |

## 12. Nguyên tắc thực hành

- Dùng kiểu nguyên thủy cho dữ liệu luôn bắt buộc có giá trị và các phép tính thường xuyên.
- Dùng wrapper khi cần lưu trong generic, collection hoặc khi null có ý nghĩa nghiệp vụ.
- Nhận biết các vị trí autoboxing/unboxing trong phép gán, lời gọi hàm, biểu thức số học và điều kiện.
- Kiểm tra null trước mọi thao tác có thể unbox; không dựa vào giá trị mặc định ngầm.
- Dùng `Objects.equals` để so sánh wrapper có thể null và `equals` để so sánh giá trị cùng kiểu.
- Không dùng `==` để so sánh giá trị của hai wrapper và không đồng bộ hóa trên wrapper.
- Dùng `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` khi muốn biểu diễn kết quả primitive có thể vắng mặt.
- Chọn primitive stream cho xử lý số học lớn khi không cần giữ null.
- Tránh constructor wrapper đã deprecated; dùng factory hoặc chuyển đổi chuẩn của Java.
- Xác định chính sách overflow, độ chính xác và giá trị mặc định theo nghiệp vụ.

## Tài liệu tham khảo

- [Java Language Specification 27 — §5.1.7 Boxing Conversion và §5.1.8 Unboxing Conversion](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html)
- [Java SE 27 API — Integer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Integer.html)
- [Java SE 27 API — Character](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html)
- [Java SE 27 API — Boolean](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Boolean.html)
- [Java SE 27 API — Objects](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html)
- [Java SE 27 API — OptionalInt](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalInt.html)
- [Java SE 27 API — IntStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 27 API — Value-based Classes](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
