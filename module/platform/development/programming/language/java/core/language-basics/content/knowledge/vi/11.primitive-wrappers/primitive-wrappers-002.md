# Boxing, unboxing và autoboxing trong Java 17+

## 1. Boxing là gì, unboxing là gì?

Java có **kiểu nguyên thủy** (*primitive*) như `int`, `long`, `double`, `boolean` và **lớp bao** (*wrapper class*) tương ứng như `Integer`, `Long`, `Double`, `Boolean`.

- **Boxing**: chuyển **giá trị primitive thành đối tượng wrapper tương ứng**, chẳng hạn `int → Integer`.
- **Unboxing**: lấy **giá trị primitive từ wrapper**, chẳng hạn `Integer → int`.
- **Autoboxing / auto-unboxing**: compiler chấp nhận các chuyển đổi này **ngầm** trong ngữ cảnh được Java cho phép, không bắt bạn gọi hàm chuyển đổi thủ công.

~~~java
int primitive = 42;
Integer boxed = primitive; // Autoboxing: int -> Integer
int restored = boxed;      // Auto-unboxing: Integer -> int

System.out.println(boxed);    // 42
System.out.println(restored); // 42
~~~

Phần trên có thể hình dung:

~~~mermaid
flowchart LR
    A["int: 42"] -->|"boxing"| B["Integer chứa giá trị 42"]
    B -->|"unboxing"| C["int: 42"]
~~~

**Quan trọng:** wrapper là **đối tượng tham chiếu**, không phải một kiểu primitive thứ hai. Hai thứ có thể biểu diễn cùng số nhưng khác nhau về khả năng giữ `null`, API, danh tính đối tượng và chi phí sử dụng.

## 2. Những cặp kiểu được boxing và giới hạn chuyển đổi

Tám cặp primitive → wrapper trong Java 17 là **`byte/Byte`, `short/Short`, `int/Integer`, `long/Long`, `float/Float`, `double/Double`, `char/Character`, `boolean/Boolean`**. `void` không có một giá trị để boxing; lớp `Void` phục vụ một số API riêng.

~~~java
Integer quantity = 7; // int -> Integer.
Long size = 7L;       // long -> Long.
// Long invalid = 7; // Sai: không tự ghép int -> long -> Long khi gán.
~~~

Lưu ý rằng compiler chỉ áp dụng **những chuyển đổi được ngôn ngữ cho phép trong từng ngữ cảnh**, không tự biến một primitive bất kỳ thành wrapper bất kỳ. Sau khi boxing, biến giữ tham chiếu và có thể được gán `null`; primitive thì không.


## 3. Boxing tường minh và autoboxing

Hai cách tạo một giá trị kiểu `Integer` từ một `int`:

~~~java
int value = 12;

Integer automatic = value;          // Autoboxing
Integer explicit = Integer.valueOf(value); // Gọi factory rõ ràng
~~~

Cả hai biến có kiểu `Integer`. Khi cần wrapper nhưng cũng muốn code thể hiện rõ ý định, `Integer.valueOf(int)` là API hữu ích. **Không cần** dùng constructor `new Integer(value)`: các constructor wrapper số kiểu này đã bị deprecated và đánh dấu để loại bỏ; dùng `valueOf` thích hợp hơn.

~~~java
Boolean flag = Boolean.valueOf(true);
Double reading = Double.valueOf(2.5);
Character letter = Character.valueOf('A');
~~~

**Không nên suy từ boxing rằng một object mới chắc chắn được cấp phát mỗi lần.** Java và các wrapper có thể sử dụng object đã được cache hoặc compiler/JVM có thể tối ưu; phần quan trọng cho ứng dụng là **giá trị và ngữ nghĩa**, không phải đếm số lần tạo object bằng mắt.

## 4. Unboxing tường minh và tự động

~~~java
Integer boxed = Integer.valueOf(15);

int automatic = boxed;       // Auto-unboxing
int explicit = boxed.intValue(); // Method lấy primitive

System.out.println(automatic); // 15
System.out.println(explicit);  // 15
~~~

Các wrapper định nghĩa method tương ứng như `longValue()`, `doubleValue()`, `booleanValue()`, `charValue()`, v.v.

**Chú ý:** `Number.intValue()` và các method chuyển số trên những wrapper khác có thể kết hợp cả **unboxing và thay đổi kiểu số học**, tùy class. Đừng giả định `doubleValue()`, `intValue()` giữ toàn bộ thông tin của một giá trị lớn hoặc có phần thập phân.

Trong phép toán số học thông thường, wrapper được **unbox** để tham gia tính toán:

~~~java
Integer one = 10;
Integer two = 20;

int total = one + two;
System.out.println(total); // 30
~~~

Ở đây `one + two` có kiểu `int`, không phải phép cộng hai “object Integer” theo kiểu nạp chồng toán tử.

## 5. Rủi ro lớn nhất: wrapper có thể null

Primitive `int` **không giữ được `null`**, nhưng một biến `Integer` có thể:

~~~java
Integer missing = null;
System.out.println(missing == null); // true
~~~

Cố auto-unbox `missing` gây **`NullPointerException` tại runtime**:

~~~java
Integer missing = null;

try {
    int count = missing; // Compile hợp lệ; chạy thì unboxing null
    System.out.println(count);
} catch (NullPointerException ex) {
    System.out.println("unboxing null failed");
}
~~~

Đầu ra:

~~~text
unboxing null failed
~~~

Một số bẫy tương tự:

~~~java
Integer quantity = null;
// int next = quantity + 1; // Unboxing null -> NullPointerException

Boolean permitted = null;
// if (permitted) { ... }    // Auto-unboxing null -> NullPointerException
~~~

**Thực hành an toàn:**

- Nếu dữ liệu **không được phép thiếu**, dùng primitive hoặc kiểm tra null ở ranh giới input.
- Nếu dữ liệu có thể **vắng mặt**, dùng wrapper cùng chính sách xử lý null rõ ràng.
- Khi chỉ cần kiểm tra có null, viết `boxed == null` mà **không unbox**.
- Không lạm dụng giá trị mặc định `0` để che một input thực sự chưa có.

Ví dụ policy mặc định:

~~~java
Integer maybeCount = null;
int count = maybeCount != null ? maybeCount : 0;
System.out.println(count); // 0
~~~

Đây là một **quyết định nghiệp vụ có chủ đích**, không phải hành vi mặc định của Java. Tránh dùng mặc định 0 nếu 0 và “chưa nhập” là hai trạng thái khác nhau.

## 6. Nơi unboxing thay đổi cách hiểu toán tử `==`

~~~java
Integer first = Integer.valueOf(1000);
Integer sameValue = Integer.valueOf(1000);
int primitive = 1000;

System.out.println(first.equals(sameValue)); // true: so giá trị.
System.out.println(first == primitive);      // true: unboxing, so int.
~~~

**`Integer == Integer`** so tham chiếu; **`Integer == int`** unbox và so số, có thể ném NPE nếu wrapper null. Với hai wrapper có thể null, `Objects.equals(a, b)` thường đúng mục tiêu so giá trị; với wrapper khác kiểu, `Integer.valueOf(5).equals(Long.valueOf(5L))` vẫn là false.

Wrapper cache khiến `==` trên số nhỏ đôi lúc trả true; không phụ thuộc điều đó để kiểm tra cùng số. Chi tiết về `NaN`, signed zero, cache và hợp đồng so sánh thuộc hai bài equality/cache kế tiếp. Ở đây điều quan trọng là biết **phép toán nào buộc unbox**, không đánh đồng các trường hợp `==`.


## 7. Wrapper là immutable: `Integer++` không sửa object

Các lớp wrapper chuẩn như `Integer`, `Double`, `Boolean` là **bất biến** (*immutable*): không có thao tác thay giá trị nguyên thủy bên trong một instance đã tạo.

~~~java
Integer count = 5;
Integer before = count;

count++;

System.out.println(count);  // 6
System.out.println(before); // 5
~~~

Ý nghĩa của `count++` (ở mức hành vi) là:

1. Unbox `count` từ `Integer` thành `int`.
2. Cộng thêm 1 theo quy tắc số học của `int`.
3. Box kết quả thành `Integer`.
4. Gán giá trị tham chiếu kết quả lại vào biến `count`.

Điều này **không** sửa instance mà biến `before` vẫn tham chiếu.

~~~java
final Integer limit = 5;
// limit++; // Lỗi biên dịch: cố gán lại biến final
~~~

Dùng `int` cho phép đếm/tính toán liên tục khi không cần null hoặc API kiểu tham chiếu, giúp tránh boxing/unboxing không cần thiết.

## 8. Boxing trong lời gọi phương thức và overload

Compiler áp dụng quy tắc thích ứng kiểu đối số trong **method invocation context**. Ví dụ:

~~~java
static void acceptInteger(Integer value) {
    System.out.println("Integer=" + value);
}

// Trong main:
acceptInteger(7); // Autoboxing int -> Integer
~~~

Ở ví dụ này `acceptInteger(7)` hợp lệ vì method nhận `Integer` và đối số là `int`.

Một overload dễ nhầm:

~~~java
static void choose(long value) {
    System.out.println("long");
}

static void choose(Integer value) {
    System.out.println("Integer");
}
~~~

Gọi:

~~~java
choose(7);                   // In long
choose(Integer.valueOf(7));  // In Integer
~~~

Khi đối số là `int`, widening primitive từ `int` sang `long` được xét trong giai đoạn phù hợp trước boxing. Khi đối số đã là `Integer`, overload nhận đúng `Integer` là phù hợp nhất ở ví dụ này.

Không phải quy tắc tổng quát “primitive luôn tốt hơn wrapper”: Java xét **toàn bộ các overload và kiểu đối số**, bao gồm strict/loose invocation, subtype, boxing/unboxing, varargs và tính cụ thể giữa các method.

### Một chuyển đổi KHÔNG hợp lệ

~~~java
static void acceptLongBox(Long value) {}

// acceptLongBox(7);  // Không compile: int không tự widening rồi boxing sang Long
acceptLongBox(7L);    // Compile: long -> Long bằng boxing
~~~

Một phương pháp học tốt là luôn hỏi: **kiểu của biểu thức truyền vào là gì?** Literal `7` mặc định `int`, còn `7L` là `long`.

## 9. Boxing, unboxing và numeric promotion trong biểu thức

Với số học, wrapper thường được unbox rồi áp dụng numeric promotion của Java:

~~~java
Byte small = (byte) 100;
Short additional = (short) 20;

int result = small + additional; // byte/short -> int
System.out.println(result); // 120
~~~

`small + additional` **không** tạo kết quả kiểu `Byte` hoặc `Short`: Java unbox rồi nâng kiểu số học thành `int`.

~~~java
Integer count = 10;
long wider = count; // Integer -> int (unboxing) -> long (widening)
System.out.println(wider); // 10
~~~

Cách này hợp lệ; trái lại Java không cho phép mọi chuỗi widening và boxing đảo chiều như `Long n = 10;`.

Lưu ý nếu kết quả số học xảy ra overflow **trước** boxing, việc gán sang wrapper rộng hơn cũng không cứu kết quả:

~~~java
Integer max = Integer.MAX_VALUE;
long wrong = max + 1;         // int overflow trước
long correct = (long) max + 1; // Unboxing/cast thành long trước

System.out.println(wrong);   // -2147483648
System.out.println(correct); // 2147483648
~~~

Khi viết phép tính, hãy xem **kiểu toán hạng tại thời điểm cộng**, không chỉ kiểu của biến nhận.

## 10. Boxing/unboxing tại ranh giới collection

Với Java 17, generic yêu cầu kiểu tham chiếu: `List<Integer>` hợp lệ, còn `List<int>` không hợp lệ. Quan sát chính xác **vị trí chuyển kiểu**:

~~~java
java.util.List<Integer> numbers = new java.util.ArrayList<>();
numbers.add(2); // int -> Integer khi thêm
numbers.add(3);

int sum = 0;
for (int n : numbers) { // Integer -> int khi lấy từng phần tử
    sum += n;
}
System.out.println(sum); // 5
~~~

Nếu collection có phần tử `null`, vòng lặp dùng biến `int` có thể ném `NullPointerException` ngay khi lấy phần tử. `List.of(...)` không cho phép phần tử null, trong khi một số collection khác có thể cho phép. Xác nhận hợp đồng null trước khi dựa vào unboxing.

## 11. Parsing là thao tác khác boxing

~~~java
int parsed = Integer.parseInt("42");       // String -> int bằng parsing
Integer wrapped = Integer.valueOf("42");   // String -> Integer bằng factory
Integer boxedParsed = Integer.parseInt("42"); // Parsing rồi boxing
~~~

Java không tự parse `String` chỉ vì đích là wrapper (`Integer n = "42";` không biên dịch). Chuỗi không hợp lệ có thể gây `NumberFormatException`; các bài parsing tiếp theo giải thích radix, kiểu trả về và validation.

## 12. Boxing không xóa đặc tính của số thực

~~~java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.valueOf(Double.NaN)
        .equals(Double.valueOf(Double.NaN))); // true
~~~

`Double.equals` còn phân biệt `+0.0` và `-0.0`, khác `==` giữa hai `double`. Đây là **quy tắc equality của wrapper**, không phải sự chuyển đổi boxing sai. Bài so sánh wrapper đi sâu vào NaN, signed zero và cache.

## 13. Khi nào tránh chuyển đổi không cần thiết?

Một phép tính với dữ liệu luôn có mặt thường nên dùng primitive để code dễ hiểu và giảm boxing/unboxing không cần thiết. Khi API/generic yêu cầu reference hoặc `null` có nghĩa nghiệp vụ, wrapper phù hợp nhưng phải bảo vệ nơi unbox. Đừng kết luận mỗi lần boxing chắc chắn cấp phát object, cũng đừng chọn kiểu chỉ dựa vào suy đoán hiệu năng; phân tích yêu cầu trước, đo hiệu năng sau nếu cần.

## 14. Chương trình Java 17 hoàn chỉnh — chạy và đối chiếu

Tạo đúng tệp **`BoxingUnboxingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class BoxingUnboxingDemo {
    private BoxingUnboxingDemo() {}

    static void choose(long value) {
        System.out.println("choose=long");
    }

    static void choose(Integer value) {
        System.out.println("choose=Integer");
    }

    static void acceptLongBox(Long value) {
        System.out.println("Long wrapper=" + value);
    }

    public static void main(String[] args) {
        int primitive = 42;
        Integer boxed = primitive;
        int restored = boxed;
        System.out.println("boxed=" + boxed);
        System.out.println("unboxed=" + restored);
        System.out.println("explicit=" + boxed.intValue());

        Boolean flag = true;
        Character letter = 'A';
        System.out.println("wrappers=" + flag + "," + letter);

        Integer first = Integer.valueOf(1000);
        Integer alias = first;
        Integer sameValue = Integer.valueOf(1000);
        System.out.println("identity alias=" + (first == alias));
        System.out.println("equal values=" + first.equals(sameValue));
        System.out.println("boxed vs primitive=" + (first == 1000));

        Integer counter = 5;
        Integer snapshot = counter;
        counter++;
        System.out.println("incremented=" + counter);
        System.out.println("snapshot=" + snapshot);

        Integer missing = null;
        System.out.println("missing=" + (missing == null));
        System.out.println("null-safe equals="
                + Objects.equals(missing, Integer.valueOf(5)));
        try {
            int failed = missing;
            System.out.println(failed);
        } catch (NullPointerException ex) {
            System.out.println("unboxing null=NullPointerException");
        }

        Integer boxedInt = 10;
        long widened = boxedInt;
        System.out.println("unbox widen=" + widened);

        choose(7);
        choose(Integer.valueOf(7));
        acceptLongBox(7L);

        List<Integer> values = new ArrayList<>();
        values.add(2);
        values.add(3);
        int total = 0;
        for (int value : values) {
            total += value;
        }
        System.out.println("list=" + values);
        System.out.println("list sum=" + total);

        Integer a = Integer.valueOf("42");
        int b = Integer.parseInt("42");
        System.out.println("parsed wrappers=" + a + "," + b);

        Integer number = Integer.valueOf(5);
        Long bigger = Long.valueOf(5L);
        System.out.println("different wrapper classes="
                + number.equals(bigger));

        Double nan1 = Double.valueOf(Double.NaN);
        Double nan2 = Double.valueOf(Double.NaN);
        Double plusZero = Double.valueOf(0.0);
        Double minusZero = Double.valueOf(-0.0);
        System.out.println("boxed NaN equals=" + nan1.equals(nan2));
        System.out.println("boxed zero equals="
                + plusZero.equals(minusZero));
        System.out.println("primitive zero equals=" + (0.0 == -0.0));
    }
}
~~~

**Yêu cầu:** cài JDK 17+, terminal đang ở thư mục chứa tệp source. Không cần Maven, Gradle hay thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BoxingUnboxingDemo.java
java -cp . BoxingUnboxingDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BoxingUnboxingDemo.java
java -cp . BoxingUnboxingDemo
~~~

**Expected output chính xác:**

~~~text
boxed=42
unboxed=42
explicit=42
wrappers=true,A
identity alias=true
equal values=true
boxed vs primitive=true
incremented=6
snapshot=5
missing=true
null-safe equals=false
unboxing null=NullPointerException
unbox widen=10
choose=long
choose=Integer
Long wrapper=7
list=[2, 3]
list sum=5
parsed wrappers=42,42
different wrapper classes=false
boxed NaN equals=true
boxed zero equals=false
primitive zero equals=true
~~~

**Các điểm cần quan sát:**

1. `Integer boxed = primitive` và `int restored = boxed` cho thấy autoboxing/unboxing.
2. `first == alias` true vì hai biến giữ cùng tham chiếu; `first.equals(sameValue)` true vì bằng **giá trị**. Không dựa vào cache wrapper để dự đoán identity của `first` và `sameValue`.
3. `Integer counter++` tạo kết quả mới sau unboxing/cộng/boxing; `snapshot` giữ giá trị 5.
4. Unboxing `missing` gây `NullPointerException`, được bắt để chương trình tiếp tục.
5. `choose(7)` chọn overload `long`, còn `choose(Integer.valueOf(7))` chọn overload `Integer`.
6. `List<Integer>` nhận số primitive qua boxing và vòng lặp dùng `int` lấy giá trị qua unboxing.
7. `Double.equals` so NaN và signed zero khác `==` primitive.

## 15. Các lỗi thường gặp và cách khắc phục

| Lỗi / ngộ nhận | Vì sao sai? | Cách xử lý |
|---|---|---|
| `Integer` và `int` hoàn toàn tương đương | Một bên là tham chiếu có thể null, một bên primitive | Chọn theo hợp đồng dữ liệu/API |
| `int value = nullableInteger;` luôn an toàn | Unboxing null gây `NullPointerException` | Kiểm tra null hoặc thiết kế primitive bắt buộc |
| `if (Boolean.TRUE.equals(flag))` và `if (flag)` luôn giống nhau | `flag = null` khiến cách sau lỗi | Dùng policy null rõ ràng |
| `Integer a == Integer b` để so số | So identity, kết quả bị cache gây nhiễu | Dùng `equals`/`Objects.equals` |
| `Integer a == int b` là so object identity | Một toán hạng primitive kích hoạt unboxing | Chỉ dùng khi wrapper chắc chắn không null |
| `Integer a = 5; a++` sửa object cũ | Wrapper immutable | Biến `a` được gán tham chiếu kết quả mới |
| `Long n = 7;` | Không tự nối int -> long -> Long | Viết `Long n = 7L;` |
| `List<int>` trong Java 17 | Generic không nhận primitive type argument | Dùng `List<Integer>` |
| Vòng `for (int n : values)` có phần tử Integer null | Unboxing null ngay khi lặp | Kiểm tra dữ liệu/nullable elements |
| Dùng wrapper trong vòng lặp nặng mà không đo đạc | Boxing có thể tăng chi phí object và GC | Cân nhắc primitive, array và benchmark |
| `Integer n = "42";` | String không tự chuyển thành wrapper | `Integer.valueOf("42")` |
| `Integer.valueOf(5).equals(Long.valueOf(5L))` trả true | `equals` của Integer không đổi kiểu wrapper | Chọn phép chuyển số phù hợp nếu cần so số khác kiểu |
| `Double.equals` hoàn toàn giống `==` số thực | NaN và signed zero có quy tắc khác | Xác định rõ semantics equality |

### Những điều boxing KHÔNG làm

Boxing **không**:

- Tự biến `String` thành kiểu số.
- Bảo đảm mọi lần boxing đều cấp phát object mới.
- Ngăn lỗi overflow trong phép cộng primitive.
- Cho phép truyền/gán tự động qua mọi chuỗi widening, narrowing, boxing.
- Xóa khả năng `NullPointerException` khi unbox wrapper.
- Khiến `==` trên hai wrapper tự chuyển thành phép so nội dung.

## 16. Bài tập có đáp án

### Bài A — nhận dạng boxing và unboxing

~~~java
int n = 10;
Integer wrapped = n;
int back = wrapped;
System.out.println(back);
~~~

**Đáp án:** in `10`. Phép gán `n → wrapped` là autoboxing, `wrapped → back` là unboxing.

### Bài B — wrapper có null

~~~java
Integer value = null;
// int n = value;
System.out.println(value == null);
~~~

**Đáp án:** in `true`; nếu chạy dòng comment, sẽ gặp `NullPointerException` khi unboxing. Compile vẫn có thể thành công khi dòng đó được bật, vì lỗi xảy ra lúc chạy.

### Bài C — biến wrapper tăng một đơn vị

~~~java
Integer a = 3;
Integer b = a;
a++;
System.out.println(a);
System.out.println(b);
~~~

**Đáp án:**

~~~text
4
3
~~~

Wrapper bất biến nên `a++` không sửa giá trị object mà `b` đang trỏ.

### Bài D — cùng số khác wrapper

~~~java
Integer n = Integer.valueOf(5);
Long l = Long.valueOf(5L);
System.out.println(n.equals(l));
~~~

**Đáp án:** `false`. `Integer.equals` không so theo kiểu số học khác wrapper.

### Bài E — overload

~~~java
static void f(long n) { System.out.println("long"); }
static void f(Integer n) { System.out.println("Integer"); }

// Trong main:
f(7);
f(Integer.valueOf(7));
~~~

**Đáp án:**

~~~text
long
Integer
~~~

### Bài F — collection wrapper

~~~java
java.util.List<Integer> nums = java.util.List.of(2, 3);
int sum = 0;
for (int n : nums) {
    sum += n;
}
System.out.println(sum);
~~~

**Đáp án:** `5`. Các phần tử kiểu `Integer` được unbox khi gán vào biến vòng lặp kiểu `int`.

## 17. Checklist tổng kết

- [ ] Phân biệt rõ primitive `int` với wrapper `Integer`.
- [ ] Biết boxing/autoboxing chuyển primitive sang wrapper, unboxing lấy primitive.
- [ ] Kể đủ tám cặp primitive-wrapper có giá trị.
- [ ] Hiểu wrapper có thể `null`, primitive tương ứng không thể.
- [ ] Không unbox wrapper null khi làm toán, `if`, so sánh với primitive hoặc vòng lặp.
- [ ] Dùng `equals` hoặc `Objects.equals` khi muốn so **giá trị wrapper**.
- [ ] Biết `==` giữa hai wrapper so **identity**, còn wrapper với primitive có thể unbox.
- [ ] Hiểu caching làm `==` trên hai wrapper khó dùng để so giá trị.
- [ ] Hiểu `Integer++` là unbox → tính toán → box → gán lại; wrapper immutable.
- [ ] Nắm ảnh hưởng boxing/unboxing đến overload và numeric promotion.
- [ ] Biết `Long n = 7;` không tương đương `Long n = 7L;`.
- [ ] Biết tại sao generic như `List<Integer>` dùng wrapper.
- [ ] Phân biệt `parseInt` với `valueOf`.
- [ ] Nhớ khác biệt của `Double.equals` với `==` primitive cho NaN và signed zero.
- [ ] Biên dịch/chạy `BoxingUnboxingDemo.java` bằng `javac`/`java` Java 17+ và đối chiếu toàn bộ đầu ra.

**Kết luận:** **Boxing** biến giá trị nguyên thủy thành wrapper; **unboxing** lấy lại primitive; **autoboxing** cho phép Java thực hiện chuyển đổi đó ngầm ở những ngữ cảnh xác định. Tính tiện lợi này cần đi kèm kỷ luật xử lý `null`, phép so sánh, overload, độ chính xác và chi phí hiệu năng. Hãy ưu tiên primitive cho tính toán bắt buộc có giá trị, dùng wrapper khi API/generic hoặc dữ liệu có thể vắng mặt thật sự đòi hỏi.