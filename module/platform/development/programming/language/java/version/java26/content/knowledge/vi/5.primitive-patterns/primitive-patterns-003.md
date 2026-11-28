# Bài toán chuyển đổi số có kiểm tra độ chính xác

## Mục tiêu

Sau bài học này, bạn có thể:

- Nhận biết khi một phép chuyển kiểu số có thể làm mất phạm vi, độ chính xác hoặc dấu.
- Phân biệt widening conversion với việc chuyển đổi thực sự chính xác.
- Dùng primitive patterns của JDK 26 để thử nghiệm kiểm tra chuyển đổi an toàn trong phạm vi preview.
- Phân tích các trường hợp chuyển `int` sang `byte`, `double` sang `int` và `long` sang `double`.
- Viết cách kiểm tra ổn định cho ứng dụng production mà không phụ thuộc preview feature.

## 1. Bài toán thực tế

Một hệ thống nhận giá trị số từ API, file CSV, cảm biến hoặc cơ sở dữ liệu. Dữ liệu nguồn có thể là `long`, `double` hoặc một kiểu tổng quát, trong khi trường đích chỉ lưu được `byte`, `int` hay `long`.

Ví dụ:

- Mã trạng thái cần lưu bằng `byte`, nhưng dữ liệu đầu vào là `int`.
- Số lượng nhận từ JSON là `double`, trong khi nghiệp vụ yêu cầu số nguyên `int`.
- Một ID lớn được chuyển từ `long` sang `double` để tính toán hoặc hiển thị, nhưng phải biết có mất chữ số hay không.

Ép kiểu trực tiếp có thể làm thay đổi dữ liệu mà không ném exception. Nếu ứng dụng ghi giá trị đã bị cắt hoặc làm tròn vào cơ sở dữ liệu, lỗi có thể lan sang báo cáo, tính tiền hoặc quyết định nghiệp vụ.

Mục tiêu của bài toán là chỉ chuyển đổi khi giá trị đích biểu diễn được giá trị nguồn theo tiêu chí chính xác đã chọn. Nếu không, chương trình phải từ chối, yêu cầu xử lý khác hoặc giữ kiểu nguồn.

## 2. Hiểu đúng widening và narrowing conversion

Java có hai nhóm chuyển đổi primitive thường gặp:

- **Widening primitive conversion:** chuyển sang kiểu có miền biểu diễn rộng hơn theo quy tắc của Java, ví dụ `int` sang `long`, `int` sang `float`, `long` sang `double`.
- **Narrowing primitive conversion:** chuyển sang kiểu có miền biểu diễn hẹp hơn, ví dụ `int` sang `byte`, `double` sang `int`, `long` sang `int`.

Tên “widening” không có nghĩa là luôn giữ nguyên mọi bit thông tin. Một số chuyển đổi widening vẫn có thể mất độ chính xác:

| Chuyển đổi | Có luôn chính xác? | Lý do |
|---|---|---|
| `int` → `long` | Có | Mọi giá trị `int` đều biểu diễn được chính xác bằng `long`. |
| `int` → `double` | Có | Độ chính xác của `double` đủ biểu diễn chính xác mọi giá trị `int`. |
| `float` → `double` | Có | Mọi giá trị `float` đều biểu diễn chính xác trong `double`. |
| `int` → `float` | Không | `float` chỉ có 24 bit độ chính xác significand; số nguyên lớn có thể bị làm tròn. |
| `long` → `double` | Không | `double` có 53 bit độ chính xác significand; không phải mọi số nguyên 64 bit đều biểu diễn chính xác. |
| `int` → `byte` | Chỉ khi nằm trong [-128, 127] | Ngoài miền này, các bit cao bị loại bỏ và kết quả có thể đổi dấu. |
| `double` → `int` | Chỉ khi hữu hạn, nằm trong miền `int` và không có phần lẻ | Phép cast thông thường cắt phần lẻ và xử lý giá trị ngoài miền theo quy tắc đặc biệt. |

Ví dụ về narrowing:

~~~java
int source = 2345323;
byte result = (byte) source;
System.out.println(result); // 107
~~~

Giá trị 2.345.323 không thể biểu diễn bằng `byte`. Phép cast vẫn chạy và chỉ giữ các bit thấp, tạo ra kết quả 107. Tương tự, ép `double` sang `int` sẽ cắt phần lẻ về phía 0; `(int) 2.9` là 2 và `(int) -2.9` là -2.

Khi chuyển `double` sang kiểu nguyên, `NaN` được chuyển thành 0; số vô cực hoặc giá trị quá lớn được đưa về giá trị cực đại hoặc cực tiểu của kiểu đích. Các quy tắc này không tự phát sinh exception. Vì vậy, kiểm tra trước khi cast là cần thiết nếu nghiệp vụ yêu cầu giữ nguyên giá trị.

## 3. Primitive patterns trong JDK 26 kiểm tra điều gì?

Primitive patterns mở rộng pattern matching để biểu diễn phép thử chuyển đổi giữa các kiểu primitive. Ví dụ:

~~~java
int value = 120;

if (value instanceof byte b) {
    System.out.println("Có thể chuyển chính xác sang byte: " + b);
} else {
    System.out.println("Không thể biểu diễn chính xác bằng byte");
}
~~~

Trong ngữ cảnh này, `instanceof byte b` không kiểm tra class của một object. Nó kiểm tra xem giá trị primitive có thể được chuyển sang `byte` mà không mất thông tin hay không. Nếu điều kiện đúng, pattern variable `b` chứa giá trị đã chuyển đổi.

Một ví dụ khác:

~~~java
double value = 42.0;

if (value instanceof int whole) {
    System.out.println("Số nguyên chính xác: " + whole);
} else {
    System.out.println("Không thể chuyển chính xác sang int");
}
~~~

Với `42.0`, phép thử thành công vì giá trị có thể biểu diễn chính xác bằng `int`. Với `42.25`, phép thử thất bại vì chuyển sang `int` sẽ làm mất phần lẻ. Giá trị ngoài miền `int`, `NaN` và vô cực cũng không phải là các giá trị có thể chuyển chính xác sang `int`.

Điểm quan trọng: primitive pattern vừa kiểm tra khả năng chuyển đổi, vừa cung cấp biến đã được chuyển đổi khi thành công. Nó không biến một phép cast có mất dữ liệu thành phép cast an toàn.

## 4. Ví dụ: kiểm tra số nguyên trước khi lưu vào byte

Giả sử trường `statusCode` chỉ lưu các giá trị từ -128 đến 127. Dữ liệu đầu vào là `int`.

~~~java
static void saveStatus(int value) {
    if (value instanceof byte status) {
        persist(status);
    } else {
        reject("Status code vượt miền byte: " + value);
    }
}
~~~

`persist` và `reject` là các hàm nghiệp vụ minh họa. Khi `value` nằm trong miền `byte`, pattern thành công và biến `status` đã có kiểu `byte`. Nếu không, chương trình đi vào nhánh từ chối thay vì lưu một giá trị đã bị wrap.

Có thể mở rộng thành switch để chọn kiểu lưu nhỏ nhất có thể biểu diễn giá trị:

~~~java
static String smallestIntegerType(int value) {
    return switch (value) {
        case byte b -> "byte: " + b;
        case short s -> "short: " + s;
        case int i -> "int: " + i;
    };
}
~~~

Với `value = 100`, nhánh `byte` được chọn. Với `value = 200`, nhánh `short` được chọn. Với giá trị ngoài miền `short`, nhánh `int` được chọn.

Thứ tự nhãn có ý nghĩa. Mọi giá trị `byte` đều có thể chuyển chính xác sang `short`, và mọi giá trị `short` đều có thể chuyển chính xác sang `int`. Vì vậy, đặt kiểu rộng hơn trước có thể làm các nhãn hẹp hơn phía sau bị compiler báo lỗi do bị pattern trước chiếm hết. Hãy đặt kiểu hẹp trước, kiểu rộng sau; pattern `int` là nhánh bao phủ cuối cùng.

## 5. Ví dụ: kiểm tra double có thể chuyển chính xác sang int

Một API có thể trả số lượng dưới dạng số thập phân. Nghiệp vụ chỉ chấp nhận số nguyên không vượt miền `int`.

~~~java
static void processQuantity(double value) {
    if (value instanceof int quantity) {
        process(quantity);
    } else {
        reject("Số lượng không phải int chính xác: " + value);
    }
}
~~~

Các trường hợp cần phân biệt:

| Giá trị nguồn | Kết quả kiểm tra `instanceof int` | Lý do |
|---|---|---|
| `42.0` | Thành công | Giá trị nguyên và nằm trong miền `int`. |
| `42.25` | Thất bại | Chuyển sang `int` sẽ bỏ phần lẻ. |
| `2147483648.0` | Thất bại | Vượt `Integer.MAX_VALUE`. |
| `NaN` | Thất bại | Không phải giá trị nguyên hữu hạn. |
| `POSITIVE_INFINITY` | Thất bại | Không biểu diễn được bằng `int`. |

`process` và `reject` là hàm minh họa. Trong ứng dụng thực tế, nhánh thất bại có thể trả HTTP 400, ghi nhận dữ liệu không hợp lệ hoặc đưa thông điệp vào hàng đợi xử lý thủ công.

Đừng dùng `Math.round(value)` như một phép kiểm tra chính xác. `Math.round` chủ động làm tròn và trả một số nguyên gần nhất; nó không xác nhận giá trị nguồn vốn đã là số nguyên.

## 6. Ví dụ: long sang double và giới hạn 2^53

Kiểu `double` có 53 bit độ chính xác significand (bao gồm bit ẩn đối với số chuẩn hóa). Vì vậy, mọi số nguyên trong miền từ `-2^53` đến `2^53` đều biểu diễn chính xác, nhưng ngoài miền này có những số nguyên không thể biểu diễn riêng biệt.

~~~java
long exact = 9_007_199_254_740_992L;     // 2^53
long inexact = 9_007_199_254_740_993L;  // 2^53 + 1

if (exact instanceof double d) {
    System.out.println("Chuyển chính xác: " + d);
}

if (inexact instanceof double d) {
    System.out.println("Chuyển chính xác: " + d);
} else {
    System.out.println("double không giữ được chính xác ID: " + inexact);
}
~~~

Giá trị `2^53 + 1` nằm giữa hai giá trị `double` có thể biểu diễn liên tiếp ở vùng đó; chuyển sang `double` sẽ làm tròn thành một giá trị lân cận. Nếu ID, số tài khoản hoặc khóa định danh cần giữ nguyên, không chuyển sang `double` chỉ để tiện tính toán hay hiển thị. Hãy giữ `long` hoặc biểu diễn ID dưới dạng chuỗi.

## 7. Exactness và quy tắc của switch

JDK 26 tiếp tục hoàn thiện định nghĩa về chuyển đổi luôn chính xác (unconditionally exact) và quy tắc dominance của các nhãn pattern trong `switch`.

Có hai khái niệm hữu ích:

- **Type-based unconditionally exact:** chuyển đổi luôn chính xác với mọi giá trị của kiểu nguồn, ví dụ `float` sang `double`, `byte` sang `short`, `int` sang `double`.
- **Value-based unconditionally exact:** một chuyển đổi không luôn chính xác với mọi giá trị của kiểu nguồn, nhưng compiler biết một hằng số cụ thể chuyển đổi không mất thông tin, ví dụ hằng số `42` từ `int` sang `byte`.

Sự phân biệt này giúp compiler xác định pattern nào có thể bao phủ hoặc làm pattern khác trở nên không thể đạt tới. Ví dụ, `case int i` bao phủ mọi giá trị `int`, do đó không thể đặt một pattern `case byte b` sau nó. Với các hằng số và chuyển đổi có thể chứng minh chính xác, compiler cũng có thể phát hiện nhãn bị pattern trước chiếm.

Đừng cố ghi nhớ một thứ tự tùy ý cho mọi trường hợp. Hãy xác định tập giá trị mà mỗi pattern có thể khớp, sau đó đặt pattern hẹp trước pattern rộng và để nhánh bao phủ cuối cùng ở cuối switch. Nếu compiler báo dominance hoặc switch không exhaustive, đọc thông báo lỗi và kiểm tra quan hệ chuyển đổi giữa kiểu selector và kiểu pattern.

## 8. Trạng thái preview trong Java 26 và quyết định sử dụng hiện nay

Primitive types in patterns, `instanceof`, and `switch` là **preview feature** trong JDK 26, theo JEP 530 (Fourth Preview). Nó không phải API Java SE ổn định. Để thử nghiệm trên JDK 26, cần bật preview khi biên dịch và chạy:

~~~bash
javac --release 26 --enable-preview PrimitiveConversionPreview.java
java --enable-preview PrimitiveConversionPreview
~~~

Dùng đúng JDK 26 cho cả hai lệnh. Preview được ràng buộc với release cụ thể; file class được biên dịch bằng preview của một release không thể mặc định chạy trên release khác.

**Cập nhật trạng thái quan trọng:** ngày 11/11/2026, nhóm Java thông báo dừng phát triển Primitive Types in Patterns, `instanceof`, and `switch`; draft JEP cho preview tiếp theo sẽ bị rút và tính năng được lên kế hoạch loại bỏ khỏi JDK 28. Vì vậy, dù JDK 26 vẫn có bản preview để học và kiểm chứng, không nên bắt đầu dùng cú pháp này làm nền tảng cho code production hoặc thư viện cần tương thích lâu dài. Nếu code hiện có phụ thuộc vào primitive patterns, hãy lên kế hoạch thay bằng kiểm tra chuyển đổi tường minh trước khi nâng cấp tới release loại bỏ tính năng.

Phần kiến thức về miền giá trị, widening/narrowing và mất độ chính xác vẫn áp dụng cho Java hiện hành. Điều cần tránh là phụ thuộc vào cú pháp preview đã bị rút khỏi lộ trình phát triển.

## 9. Cách viết kiểm tra ổn định cho production

Có thể giải quyết cùng bài toán bằng API và phép kiểm tra Java ổn định, không cần primitive patterns.

### int sang byte

~~~java
static Optional<Byte> toByteExact(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        return Optional.empty();
    }
    return Optional.of((byte) value);
}
~~~

Kiểm tra miền trước khi cast. Khi đã nằm trong [-128, 127], chuyển từ `int` sang `byte` giữ nguyên giá trị.

### double sang int

~~~java
static OptionalInt toIntExact(double value) {
    if (!Double.isFinite(value)
            || value < Integer.MIN_VALUE
            || value > Integer.MAX_VALUE
            || value != Math.rint(value)) {
        return OptionalInt.empty();
    }

    return OptionalInt.of((int) value);
}
~~~

Phương thức này từ chối NaN, vô cực, giá trị ngoài miền và số có phần lẻ. `Math.rint` được dùng để kiểm tra giá trị đã là số nguyên; phép cast chỉ xảy ra sau khi các điều kiện đã được xác nhận.

Nếu miền nghiệp vụ phân biệt `-0.0` với `+0.0`, hãy xử lý dấu zero riêng trước khi chuyển sang kiểu nguyên vì kiểu nguyên không lưu được dấu của zero.

### long sang int

Khi nguồn là `long`, có thể dùng `Math.toIntExact`:

~~~java
static int toIntExact(long value) {
    return Math.toIntExact(value);
}
~~~

Nếu giá trị vượt miền `int`, phương thức ném `ArithmeticException`. Đây là lựa chọn chuẩn cho chuyển đổi `long` sang `int` cần kiểm tra tràn.

### Số thập phân và BigDecimal

Khi dữ liệu đầu vào là số thập phân nghiệp vụ, chẳng hạn tiền hoặc số lượng có phần lẻ, dùng `BigDecimal` và các phương thức `*ValueExact()`:

~~~java
BigDecimal amount = new BigDecimal("123.00");
int wholeAmount = amount.intValueExact();

BigDecimal invalidAmount = new BigDecimal("123.45");
int rejected = invalidAmount.intValueExact(); // ArithmeticException
~~~

`intValueExact()`, `longValueExact()`, `shortValueExact()` và `byteValueExact()` kiểm tra cả phần lẻ lẫn khả năng biểu diễn trong miền kiểu đích. Với dữ liệu đến từ chuỗi thập phân, hãy tạo `BigDecimal` từ chuỗi như `new BigDecimal("0.10")`. Tránh `new BigDecimal(0.10)` vì giá trị `double` đã mang biểu diễn nhị phân gần đúng trước khi được đưa vào `BigDecimal`.

## 10. Bài tập thực hành

Xây dựng hàm kiểm tra dữ liệu nhập từ một dịch vụ tính phí. Dịch vụ gửi số tiền dưới dạng `double`, trong khi hệ thống lưu số tiền theo đơn vị cent bằng `long`.

Yêu cầu:

1. Nhận một giá trị `double` đại diện cho số tiền theo đơn vị tiền tệ.
2. Từ chối NaN, vô cực và giá trị âm nếu nghiệp vụ không cho phép.
3. Chuyển sang cent bằng cách nhân với 100.
4. Kiểm tra kết quả có phải số nguyên chính xác và nằm trong miền `long`.
5. Chỉ lưu sau khi kiểm tra thành công; nếu thất bại, trả lỗi có nguyên nhân cụ thể.

Thử các giá trị:

| Đầu vào | Điều cần kiểm tra |
|---|---|
| `12.34` | Giá trị cent dự kiến là 1234. |
| `0.10` | Sai số biểu diễn nhị phân có ảnh hưởng đến phép nhân và kiểm tra hay không? |
| `12.345` | Có phần lẻ của cent, phải áp dụng quy tắc làm tròn nghiệp vụ hay từ chối? |
| `NaN` | Phải bị từ chối. |
| `POSITIVE_INFINITY` | Phải bị từ chối. |
| Giá trị quá lớn | Có vượt miền `long` sau khi nhân 100 không? |

Với hệ thống tài chính, giải pháp phù hợp hơn thường là nhận số tiền dưới dạng chuỗi thập phân hoặc `BigDecimal`, sau đó áp dụng rõ ràng quy tắc scale và rounding của nghiệp vụ. Không dựa vào việc nhân một `double` rồi so sánh với `Math.rint` để thay thế quy tắc làm tròn tiền.

## 11. Checklist khi chuyển đổi số

- [ ] Xác định miền giá trị hợp lệ của kiểu đích.
- [ ] Xác định yêu cầu giữ nguyên giá trị, cho phép làm tròn hay từ chối.
- [ ] Không coi widening conversion là luôn chính xác.
- [ ] Không dùng cast narrowing như một phép xác thực.
- [ ] Xử lý riêng NaN, infinity, số âm và giá trị biên nếu kiểu nguồn là floating point.
- [ ] Với `long` sang `int`, cân nhắc `Math.toIntExact`.
- [ ] Với `BigInteger` hoặc `BigDecimal`, dùng phương thức `*ValueExact()` khi cần phát hiện tràn hoặc phần lẻ.
- [ ] Không đưa primitive patterns của JDK 26 vào code production vì đây là preview đã có thông báo dừng phát triển và kế hoạch loại bỏ.

## Kết luận

Một phép chuyển đổi số an toàn phải xét cả miền giá trị lẫn độ chính xác. Primitive patterns trong JDK 26 minh họa cách kiểm tra liệu một giá trị primitive có thể chuyển sang kiểu đích mà không mất thông tin hay không, nhưng cú pháp này chỉ là preview theo JEP 530. Sau thông báo dừng phát triển ngày 11/11/2026 và kế hoạch loại bỏ khỏi JDK 28, hãy dùng nó như nội dung nghiên cứu về exactness và pattern matching; code production nên kiểm tra miền tường minh, dùng `Math.toIntExact` hoặc các phương thức `BigDecimal/BigInteger.*ValueExact()` ổn định.

## Tài liệu tham khảo

- [JDK 26 – Primitive Types in Patterns, instanceof, and switch](https://docs.oracle.com/en/java/javase/26/language/primitive-types-patterns-instanceof-switch.html)
- [JDK 26 – Safe Casting with instanceof and switch](https://docs.oracle.com/en/java/javase/26/language/safe-casting-instanceof-switch.html)
- [JDK 26 – Dominance and Unconditionally Exact Conversions](https://docs.oracle.com/en/java/javase/26/language/pattern-matching-switch.html)
- [Java Language Specification, Java SE 26 – Chapter 5: Conversions and Contexts](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-5.html)
- [JEP 530 – Primitive Types in Patterns, instanceof, and switch (Fourth Preview)](https://openjdk.org/jeps/530)
- [Withdrawing the Primitive Patterns Preview Feature – Inside Java, 11 November 2026](https://inside.java/2026/11/11/withdraw-primitive-patterns-preview/)
