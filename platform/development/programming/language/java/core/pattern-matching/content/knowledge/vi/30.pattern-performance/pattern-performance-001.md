# Chi phí runtime của type check trong Java Pattern Matching

## 1. Type check có “đắt” không?

Trong Java, kiểm tra kiểu ở runtime xuất hiện khi dùng `instanceof`, cast (`(SomeType) object`), type pattern (`instanceof SomeType value`), hoặc khi `switch` cần phân loại selector theo kiểu. Với **record pattern**, Java còn có thể phải đọc các component thông qua accessor, kiểm tra tiếp nested pattern và đánh giá guard `when`.

Câu trả lời đúng cho “type check có đắt không?” không phải một số nanosecond cố định:

- Một kiểm tra kiểu đơn giản thường có đường thực thi rất ngắn trên JVM đã tối ưu, và **không tự tạo đối tượng mới** chỉ vì dùng `instanceof`.
- Nhưng một luồng xử lý thực tế có thể gồm **nhiều kiểm tra**, các nhánh rẽ, đọc object/record component, gọi accessor do người dùng định nghĩa, guard có logic tốn kém, tạo chuỗi kết quả hoặc phát sinh allocation.
- HotSpot JIT có thể tối ưu, inline, hoán đổi cách biểu diễn hoặc loại bỏ một số kiểm tra khi chứng minh được tính đúng đắn. Điều được quan sát ở bytecode không nhất thiết bằng chi phí của mã máy ở trạng thái đã warm-up.
- Tốc độ còn phụ thuộc **phân bố subtype thực tế**, độ sâu của pattern, tính dự đoán của nhánh, tình trạng cache, JDK/JVM, hardware, các điểm deoptimization và áp lực GC.
- `sealed` và exhaustive `switch` cung cấp **đảm bảo về kiểu ở compile time**, không phải cam kết rằng runtime dispatch có chi phí bằng 0.

Vì thế, với phần lớn application code, ưu tiên **semantics, tính rõ ràng và cấu trúc domain hợp lý**. Chỉ kết luận một cách viết nhanh hơn khi đã đo **workload có đại diện** bằng công cụ như JMH và/hoặc profiler.

**Phạm vi phiên bản:** `instanceof` có type pattern là tính năng chuẩn từ Java 16. Record patterns (JEP 440) và pattern matching cho `switch` (JEP 441) là tính năng chuẩn từ **Java 21**, không cần `--enable-preview`. Bài sử dụng JDK 21 trở lên và đề cập đến HotSpot như một ví dụ implementation phổ biến, không đồng nhất mọi JVM.

Sau bài học, bạn có thể phân biệt chi phí **kiểm tra kiểu**, **bóc tách record**, **guard**, **case selection** và **code trong case**, thiết kế thử nghiệm đúng, tránh suy luận hiệu năng từ số dòng Java hay bytecode đơn thuần.

## 2. Cần đo cái gì? Năm phần của một thao tác pattern

Xét đoạn minh họa:

```java
// event có kiểu Object hoặc một interface chung:
switch (event) {
    case Text(String text) when text.length() >= 4 ->
        processLongText(text);
    case Text(String text) ->
        processShortText(text);
    default ->
        processOther(event);
}
```

Nếu đây là một `switch statement` dùng pattern matching, có thể phân tích các công việc runtime theo các lớp sau:

1. **Lấy selector:** Đọc hoặc tính `event`. Nếu viết `switch (loadEvent())`, chi phí `loadEvent()` không phải chi phí thuần của type check.
2. **Kiểm tra tính tương thích kiểu:** Xác định object có khớp `Text` hay không. Các test đối với `null` và subtype cũng thuộc giai đoạn phân loại.
3. **Deconstruction của record:** Nếu pattern `Text(String text)` khớp record bên ngoài, runtime cần giá trị component để tiếp tục matching. Với record patterns, accessor có thể được gọi để lấy component. Accessor được ghi đè có thể chứa logic tùy ý, thậm chí ném exception.
4. **Guard:** `text.length() >= 4` được xét khi pattern liên quan đã khớp. Một guard đơn giản khác hoàn toàn với guard truy vấn database hoặc gọi hàm phức tạp.
5. **Phần thân case:** `processLongText(...)` có thể có I/O, allocation hoặc khóa đồng bộ. Khi so sánh hai cách dispatch, không nên nhầm chi phí này với riêng phép kiểm tra kiểu.

Hai chương trình có cùng type check nhưng khác body có thể chênh thời gian rất lớn; ngược lại cùng body nhưng guard khác nhau cũng không đo được chi phí của type check “thuần”.

### Bảng phân tách chi phí

| Thành phần | Việc cần quan sát | Nguyên tắc diễn giải |
| --- | --- | --- |
| `instanceof SomeType` | Kiểm tra kiểu động của reference | Thường rẻ nhưng không có số ns chung cho mọi JVM |
| `checkcast` hoặc biến pattern được ràng buộc | Bảo đảm tham chiếu có kiểu cần dùng | JIT có thể tận dụng type information và bỏ kiểm tra trùng khi hợp lệ |
| `switch` với type patterns | Chọn một nhánh cho kiểu/giá trị | Hình thức lowering và machine code là chi tiết implementation |
| `Record(T x)` | Kiểm tra record và lấy component | Có thể gọi accessor; chi phí accessor không tự bằng 0 |
| Nested record pattern | Kiểm tra thêm record/component ở các cấp | Đường khớp và đường không khớp có số thao tác khác nhau |
| `when predicate` | Kiểm tra điều kiện bổ sung | Chi phí tùy biểu thức; guard chỉ có ý nghĩa khi pattern khớp |
| Tạo chuỗi, boxing, stream, logging trong body | Hành vi nghiệp vụ/bên tiêu thụ | Thường không được gộp vào “chi phí type check” khi phân tích |

Không biến bảng này thành một công thức cộng thời gian cố định: JIT có thể inline và tối ưu xuyên qua nhiều bước, làm ranh giới trong mã máy khác với sơ đồ source.

## 3. `instanceof`, type pattern và cast hoạt động như thế nào?

### 3.1. Kiểm tra kiểu động

`instanceof` trả `true` khi reference khác null và đối tượng có thể được kiểm tra theo kiểu được chỉ định; các subtype phù hợp cũng được chấp nhận. Ví dụ:

```java
// Đoạn minh họa:
Object value = "java";
boolean text = value instanceof CharSequence; // true
boolean number = value instanceof Number;      // false
boolean missing = null instanceof String;      // false
```

JVM phải phân biệt kiểu runtime của object với kiểu cần kiểm tra. Cách thực hiện chi tiết phụ thuộc JVM; trong HotSpot có metadata về lớp/interface và những đường kiểm tra được tối ưu. Không nên giả định tất cả `instanceof` đều có cùng số phép so sánh, hoặc độ phức tạp/độ trễ bất biến cho mọi cấu trúc kế thừa.

### 3.2. Type pattern không nhất thiết là “hai kiểm tra”

`if (value instanceof String text)` kết hợp kiểm tra kiểu và ràng buộc biến `text`:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

So với code cũ:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Cả hai có cùng mục tiêu: bảo đảm `value` là `String` trước khi sử dụng. Không kết luận bản pattern “nhanh gấp đôi” vì bớt một dòng cast, cũng không kết luận “chậm gấp đôi” vì bytecode có thể chứa cả `instanceof` lẫn `checkcast`. Compiler/JIT có thể tận dụng sự thật rằng một kiểm tra thành công đã xác lập kiểu.

**Điểm chính:** Type pattern cải thiện flow scoping và loại bỏ nhu cầu cast thủ công trong source; lợi ích hiệu năng phải được đo, không suy ra từ độ ngắn của cú pháp.

### 3.3. `getClass() == T.class` không thay thế trực tiếp `instanceof`

`obj.getClass() == SomeClass.class` kiểm tra **đúng lớp runtime**, không nhận các subclass; `obj instanceof SomeClass` chấp nhận những subtype phù hợp. Hơn nữa, `obj.getClass()` sẽ ném `NullPointerException` khi `obj` null, còn `null instanceof SomeClass` trả false.

Dù một microbenchmark đôi lúc cho thấy so sánh class bằng nhau rẻ hơn trong một trường hợp cụ thể, **không thay `instanceof` bằng `getClass()` nếu semantics đòi nhận subtype**. Đổi logic nghiệp vụ để lấy vài ns không phải tối ưu đúng.

## 4. Type pattern trong switch có phải luôn nhanh hơn if/else?

Hai phương thức có thể biểu đạt cùng thuật toán phân loại:
- Chuỗi `if (event instanceof ...)`.
- `switch (event)` với type/record patterns và guard.

Không có quy tắc Java Language Specification nào bảo đảm pattern `switch` nhanh hơn `if` trên mọi input/JDK.

### Những yếu tố thường làm kết quả khác nhau

**Phân bố đầu vào:** Nếu 95% message thuộc case đầu, một chuỗi `if/else` đặt nhánh phổ biến trước có thể có hành vi khác với workload mỗi subtype xuất hiện ngang nhau. CPU branch predictor, profile của JVM và cách compiler bố trí code đều có thể ảnh hưởng.

**Số subtype và tính ổn định của call site:** Hai subtype ổn định, hàng chục subtype biến đổi liên tục, hoặc một subtype mới vừa được load đều có thể làm việc tối ưu khác nhau. Không suy ra từ số `case` rằng runtime luôn quét tuyến tính toàn bộ danh sách.

**Type hierarchy:** Một sealed hierarchy giúp compiler hiểu tập subtype, nhưng không đồng nghĩa `switch` phải được dịch thành một bảng nhảy hằng số như `switch(int)`. Java compiler/JVM có quyền dùng những cơ chế dispatch phù hợp. Trong các bản JDK hiện đại, pattern switch có thể dùng `invokedynamic` với bootstrap cho type-based switch; điều đó không tự nói lên chi phí sau JIT.

**Nhiều case của cùng subtype:** Guard có thể tách một subtype thành nhiều nhánh. Nếu guard đầu không áp dụng, case khác vẫn có thể được đánh giá. Chi phí tổng không chỉ có type check.

**Kiểu của body:** Nếu mỗi nhánh gọi nhiều method hoặc tạo object, dispatch có thể là phần rất nhỏ của tổng chi phí. Đừng chọn lại toàn bộ mô hình domain chỉ dựa trên thời gian của một check rẻ.

### Thứ tự case phải đúng semantics trước

Các case tổng quát có thể **dominate** case cụ thể và bị javac từ chối:

```java
// Ví dụ cố ý sai khi đặt trong cùng switch:
case CharSequence value -> handleText(value);
case String text -> handleString(text); // dominated
```

Dù muốn nhánh phổ biến đứng trước, **không được phá quy tắc dominance của pattern switch**. Với guard, đặt case có điều kiện trước case không guard khi cần:

```java
case Text(String text) when text == null -> ...;
case Text(String text) -> ...;
```

Đừng đổi thứ tự để “tối ưu” nếu làm thay đổi kết quả hoặc gây lỗi biên dịch.

## 5. Record pattern: chi phí không dừng ở type check

Type pattern và record pattern làm những công việc khác nhau.

```java
// Đoạn minh họa, value có kiểu Object:
boolean isText = value instanceof Text;
boolean deconstructed = value instanceof Text(String s);
```

Dòng đầu chỉ cần xác định kiểu của object. Dòng thứ hai còn yêu cầu giá trị record component `s` để hoàn tất matching. Theo ngữ nghĩa Java 21, khi deconstruct record, accessor tương ứng có thể được gọi.

Với nested pattern:

```java
// Đoạn minh họa, value có kiểu Object:
boolean wrapped =
    value instanceof Wrapper(Text(String s));
```

Runtime cần record `Wrapper` ngoài khác null, component `value` phải khớp record `Text` bên trong, rồi component `String s` được ràng buộc theo quy tắc pattern. Nếu component nested record bằng null, nested record pattern không khớp bình thường. Nếu accessor của record bị override và có chi phí cao hoặc ném exception, hành vi sẽ khác nhiều so với kiểm tra kiểu thuần.

**Lưu ý:** Deconstruction bằng record pattern không bắt buộc “tạo một object mới để chứa tuple”; pattern thường chỉ ràng buộc các giá trị component. Nhưng code do người dùng đặt trong accessor hoặc body vẫn có thể allocate. Ngôn ngữ không hứa rằng một record pattern bất kỳ là zero-cost.

## 6. Ví dụ Java 21 đầy đủ: so logic trước, rồi quan sát các bước

Ví dụ dưới đây **không đo ns/op**. Nó kiểm tra hai cách phân loại có cùng kết quả, ghi đếm số lần guard được gọi và số lần record accessor tùy chỉnh được đánh giá. Đây là bằng chứng về **hành vi quan sát được của chương trình này**, không phải benchmark throughput.

Tạo file **`TypeCheckRuntimeCostDemo.java`**:

```java
public class TypeCheckRuntimeCostDemo {
    sealed interface Event permits Text, Quantity, Wrapper {}

    record Text(String text) implements Event {}
    record Quantity(int amount) implements Event {}
    record Wrapper(Text value) implements Event {}

    record Traced(String value) {
        static int reads;

        @Override
        public String value() {
            reads++;
            return value;
        }
    }

    static int guardCalls;

    static boolean longText(String value) {
        guardCalls++;
        return value.length() >= 4;
    }

    static String bySwitch(Event event) {
        return switch (event) {
            case Text(String s) when s == null -> "TEXT_NULL";
            case Text(String s) when longText(s) -> "TEXT_LONG";
            case Text(String s) -> "TEXT_SHORT";

            case Quantity(int amount) when amount < 0 -> "NEGATIVE";
            case Quantity(int amount) -> "QUANTITY";

            case Wrapper(Text(String s)) -> "WRAPPED";
            case Wrapper(var value) -> "WRAPPER_EMPTY";

            case null -> "NULL";
        };
    }

    static String byIf(Event event) {
        if (event == null) return "NULL";

        if (event instanceof Text(String s)) {
            if (s == null) return "TEXT_NULL";
            if (longText(s)) return "TEXT_LONG";
            return "TEXT_SHORT";
        }

        if (event instanceof Quantity(int amount)) {
            return amount < 0 ? "NEGATIVE" : "QUANTITY";
        }

        if (event instanceof Wrapper(Text(String s))) {
            return "WRAPPED";
        }
        if (event instanceof Wrapper(var value)) {
            return "WRAPPER_EMPTY";
        }

        throw new AssertionError("Unknown subtype");
    }

    static int cases;

    static void verify(Event event) {
        guardCalls = 0;
        String viaSwitch = bySwitch(event);
        int switchGuards = guardCalls;

        guardCalls = 0;
        String viaIf = byIf(event);
        int ifGuards = guardCalls;

        if (!viaSwitch.equals(viaIf) || switchGuards != ifGuards) {
            throw new AssertionError("Implementations differ");
        }

        cases++;
        System.out.println(viaSwitch + " | guards=" + switchGuards);
    }

    public static void main(String[] args) {
        verify(new Text("java"));
        verify(new Text("go"));
        verify(new Text(null));
        verify(new Quantity(-2));
        verify(new Quantity(3));
        verify(new Wrapper(new Text("x")));
        verify(new Wrapper(new Text(null)));
        verify(new Wrapper(null));
        verify(null);

        Object probe = new Traced("yes");
        System.out.println("typeOnly="
            + (probe instanceof Traced)
            + ", reads=" + Traced.reads);
        System.out.println("deconstruct="
            + (probe instanceof Traced(String s) && !s.isEmpty())
            + ", reads=" + Traced.reads);

        Object other = new Object();
        System.out.println("wrongType="
            + (other instanceof Traced(String s))
            + ", reads=" + Traced.reads);

        System.out.println("CASES=" + cases);
    }
}
```

Biên dịch/chạy với JDK 21 trở lên:

```bash
javac --release 21 TypeCheckRuntimeCostDemo.java
java TypeCheckRuntimeCostDemo
```

**Stdout chính xác:**

```text
TEXT_LONG | guards=1
TEXT_SHORT | guards=1
TEXT_NULL | guards=0
NEGATIVE | guards=0
QUANTITY | guards=0
WRAPPED | guards=0
WRAPPED | guards=0
WRAPPER_EMPTY | guards=0
NULL | guards=0
typeOnly=true, reads=0
deconstruct=true, reads=1
wrongType=false, reads=1
CASES=9
```

### 6.1. Hai cách phân loại cho cùng kết quả

`verify` gọi `bySwitch` và `byIf` với **cùng một Event**, so giá trị trả về và số lần guard được gọi. Nếu khác, chương trình ném `AssertionError` thay vì in “PASS” giả.

Chín giá trị bao phủ:
- Text dài: `Text("java")`.
- Text ngắn: `Text("go")`.
- Text có component null: `Text(null)`.
- Số âm và không âm: `Quantity(-2)`, `Quantity(3)`.
- Wrapper chứa Text thông thường và Text có component null.
- Wrapper có component record con null.
- Selector `Event` bằng null.

Trong `Text(null)`, case `Text(String s) when s == null` được chọn; guard `longText(s)` không được gọi. Trong `Text("java")` và `Text("go")`, guard được đánh giá một lần mỗi đường xử lý; case long hoặc case short được chọn tùy kết quả.

**Chú ý:** `Wrapper(new Text(null))` vẫn khớp nested `Text(String s)`: tại vị trí component khai báo `String`, pattern unconditional có thể ràng buộc null. Ngược lại `Wrapper(null)` không khớp nested record pattern `Text(...)` và vào case `Wrapper(var value)`.

### 6.2. Type-only không gọi record accessor; deconstruction có thể gọi

Phần `Traced` là một record riêng có accessor được override để tăng biến đếm:

```java
record Traced(String value) {
    static int reads;

    @Override
    public String value() {
        reads++;
        return value;
    }
}
```

- `probe instanceof Traced` chỉ kiểm tra kiểu, nên `reads=0`.
- `probe instanceof Traced(String s)` yêu cầu bóc tách record và gọi accessor của `Traced`; sau lần đó `reads=1`.
- `other instanceof Traced(String s)` thất bại ngay vì `other` không phải `Traced`; accessor không bị gọi, số lần đọc vẫn là 1.

Bài học **không** phải “record pattern luôn chậm hơn đúng một lần gọi hàm”. Khi accessor đơn giản, JIT có thể inline; khi accessor có side effect, hành vi không thể tùy tiện biến mất; khi nested pattern không khớp sớm, những bước về sau không cần thực hiện. Hãy xem số lần gọi ở đây là **một công cụ minh họa công việc thêm**, không phải đơn vị thời gian.

### 6.3. Guard có thể áp đảo chi phí type check

`longText` chỉ gọi `String.length()` và tăng counter. Nếu thay bằng tra cứu mạng, phân tích regex phức tạp hoặc tạo các object phụ, thời gian của guard có thể lớn hơn rất nhiều so với kiểm tra kiểu. Nên giữ guard rõ ràng, không có side effect không cần thiết, và tránh lặp logic tốn kém ở các case.

### 6.4. Đây không phải benchmark hiệu năng

Hai cách được gọi liên tiếp, có reset counter và tạo output chuỗi. Thời gian của `System.out.println`, string concatenation, khởi tạo đối tượng, class loading và warm-up không được tách riêng. Kết quả ở trên chứng minh **cùng semantics đối với các ca thử**, hoàn toàn không chứng minh `switch` nhanh hơn hay chậm hơn `if`.

## 7. HotSpot/JIT có thể thay đổi chi phí runtime như thế nào?

Java source được biên dịch thành bytecode, rồi JVM có thể thực thi/biên dịch động các đoạn nóng. Trong HotSpot, các tối ưu quan trọng có thể gồm:

- **Inlining:** Loại bỏ phần overhead của những method call nhỏ khi phù hợp, kể cả accessor record hoặc helper guard.
- **Redundant type-check elimination:** Khi compiler suy luận hoặc chứng minh một giá trị đã có kiểu phù hợp, một số kiểm tra trùng có thể biến mất trong machine code.
- **Type profiling và devirtualization:** JVM quan sát kiểu runtime tại các call site và tối ưu những đường phổ biến, với cơ chế bảo toàn semantics khi giả thiết không còn đúng.
- **Escape analysis/scalar replacement:** Allocation của các đối tượng liên quan có thể được tối ưu nếu compiler chứng minh được phạm vi sử dụng; đây không phải cam kết cho mọi record hay mọi pattern.
- **Branch optimization:** Cách tổ chức các nhánh sau biên dịch, local profile và hành vi CPU branch predictor ảnh hưởng đến performance trên tập dữ liệu cụ thể.

Các tối ưu này làm cho “đếm số lệnh trong source” hoặc “thấy một opcode `checkcast`” không đủ để suy ra latency của luồng xử lý nóng.

### Cold path, warm-up, steady state và deoptimization

- **Cold start:** Lần đầu chạy có thể bao gồm tải class, bootstrap, interpreter và compiler activity.
- **Warm-up:** Code chạy đủ nhiều để JIT thu thập profile và tối ưu. Không có số vòng warm-up cố định hợp lệ cho mọi chương trình.
- **Steady state:** Đo trong điều kiện chạy ổn định hơn, nhưng vẫn chịu tác động GC, CPU frequency, contention và dữ liệu.
- **Deoptimization:** Nếu giả thiết runtime của optimized code không còn đúng (ví dụ phân bố kiểu thay đổi), JVM có thể quay về đường thực thi khác rồi tối ưu lại.

Một benchmark dùng đúng một object `Text` lặp đi lặp lại dễ khiến JVM tối ưu theo một profile cực hẹp; kết quả có thể không phản ánh một hệ thống thực nhận đủ các subtype. Ngược lại, trộn ngẫu nhiên quá nhiều kiểu mà production không bao giờ gặp cũng cho workload thiếu đại diện.

### Inspect bytecode: hữu ích nhưng không phải đồng hồ đo

Có thể xem bytecode của chương trình sau khi biên dịch:

```bash
javap -c -p TypeCheckRuntimeCostDemo
```

Ở JDK hiện đại, bạn có thể thấy `instanceof`, `checkcast`, hoặc các cơ chế như `invokedynamic` cho pattern switch. Hình thức bytecode phụ thuộc phiên bản/compiler, và máy ảo có thể tối ưu khác đáng kể khi chạy nóng.

**Không** lấy “nhiều bytecode instruction hơn” làm bằng chứng tốc độ chậm hơn tương ứng. `javap` giúp hiểu translation, trong khi JMH/profiler mới giúp quan sát runtime behavior.

## 8. Chi phí liên quan null, nhánh rẽ và dữ liệu đầu vào

### 8.1. Null-check không giống record deconstruction

`null instanceof T` là false. Một `switch` nhận `null` cần case hoặc chính sách xử lý thích hợp; `default` đơn lẻ không đồng nghĩa bắt null trong pattern switch.

Null handling có thể chỉ là kiểm tra đơn giản, nhưng quan trọng nhất là **semantics**. Đừng bỏ `case null` để “tăng tốc” nếu đầu vào null được yêu cầu xử lý.

### 8.2. Type distribution và branch prediction

Nếu dữ liệu luôn đi vào cùng nhánh, CPU có thể dự đoán luồng điều khiển thuận lợi hơn so với dữ liệu phân bố khó đoán. Nhưng điều này còn phụ thuộc cách compiler/JIT hạ `switch` thành code máy, bố trí nhánh và loại workload.

Bởi vậy benchmark nên thử ít nhất:
- Phần lớn input thuộc một subtype.
- Các subtype xuất hiện tương đối cân bằng.
- Guard thường đúng so với guard thường sai.
- Trường hợp non-match và null nếu production thực sự có.

Đừng so hai giải pháp với những phân bố khác nhau rồi kết luận do cú pháp.

### 8.3. Độ sâu của record pattern

Nested pattern có thể yêu cầu nhiều mức kiểm tra và accessor hơn so với type-only match. Tuy vậy, matching thất bại sớm thường không cần tiếp tục kiểm tra những thành phần sâu. Số mức lồng, null distribution, accessor và guard đều quan trọng.

Đừng viết nested pattern quá sâu chỉ để giảm số dòng code nếu code khó đọc hoặc có dữ liệu phức tạp. Có thể tách thành một case type pattern rồi gọi method xử lý rõ ràng, **miễn là giữ nguyên semantics**.

### 8.4. GC và allocation là vấn đề khác

`instanceof` không tự allocate một object chỉ để trả boolean. Record pattern cũng không mặc nhiên tạo một record khác khi bóc tách component. Nhưng body có thể tạo chuỗi/DTO, boxing, collection hoặc exception; hơn nữa các object đầu vào thường đã được khởi tạo trước matching.

Khi profiling, xem allocation rate và GC để biết chi phí chính có thực sự nằm ở dispatch hay ở việc tạo/xử lý dữ liệu. Một microbenchmark tạo object mới trong mỗi lần gọi có thể chủ yếu đo allocation thay vì type check.

## 9. So sánh với polymorphism và interface dispatch

Một lựa chọn khác là đưa behavior lên type:

```java
// Đoạn minh họa về thiết kế, không ghép vào chương trình phần 6:
interface Describable {
    String describe();
}

final class TextMessage implements Describable {
    private final String text;

    TextMessage(String text) {
        this.text = text;
    }

    @Override
    public String describe() {
        return "TEXT:" + text;
    }
}
```

Bên gọi dùng `message.describe()` thay vì `switch` phân loại kiểu để tạo thông điệp.

Về performance:
- Virtual/interface dispatch cũng có chi phí runtime, nhưng JIT có thể inline/devirtualize trong những điều kiện phù hợp.
- Một chuỗi `instanceof` hoặc pattern switch cũng có thể được tối ưu mạnh.
- Kết quả phụ thuộc type profile, số implementation, behavior của các method và runtime data.
- Chuyển sang polymorphism **không** bảo đảm tăng tốc; nó thường được chọn trước hết vì encapsulation và owner của behavior.

**Thiết kế trước, tối ưu có chứng cứ sau:** Nếu mỗi consumer copy cùng một business rule bằng `switch`, ưu tiên tập trung logic vào domain method/service để bảo trì. Nếu operation là mapping bên ngoài của một sealed hierarchy, pattern `switch` có thể rất phù hợp. Chỉ so tốc độ nếu profiler cho thấy dispatch thật sự là điểm nóng.

## 10. Benchmark đúng bằng JMH thay vì vòng lặp nanoTime thủ công

### 10.1. Vì sao microbenchmark ngây thơ dễ sai?

Mã như sau có thể cho kết quả đánh lừa:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    boolean ok = fixedValue instanceof Text;
}
System.out.println(System.nanoTime() - start);
```

Compiler có thể loại bỏ các phép tính không được sử dụng, tối ưu type đã biết, hoặc đo phần lớn overhead của loop/JIT warm-up. Trong một số trường hợp, biến `ok` cục bộ còn không bao giờ được đọc. Kết quả không thể được xem là “chi phí thật của `instanceof`”.

Các vấn đề khác: timing ngắn, class loading, CPU throttling, GC, benchmark code được biên dịch khác code production, constant folding, inlining và thiếu fork độc lập.

### 10.2. JMH: benchmark có warm-up, forks và kết quả quan sát được

**JMH (Java Microbenchmark Harness)** là bộ công cụ OpenJDK dành cho microbenchmark trên JVM. JMH không phải thư viện chuẩn đi kèm JDK: project cần khai báo dependency/plugin hoặc archetype JMH phù hợp.

Một skeleton JMH minh họa cùng workload cho hai kiểu phân nhánh:

```java
// File TypeCheckBenchmark.java trong project đã cấu hình JMH.
// Phụ thuộc ngoài JDK: org.openjdk.jmh:jmh-core và
// annotation processor org.openjdk.jmh:jmh-generator-annprocess.
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Fork(2)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@State(Scope.Thread)
public class TypeCheckBenchmark {
    sealed interface E permits A, B {}
    record A(int n) implements E {}
    record B(int n) implements E {}

    @Param({"50_50", "90_10"})
    public String mix;

    private E[] input;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        input = new E[1024];
        for (int i = 0; i < input.length; i++) {
            boolean chooseA = mix.equals("90_10")
                ? i % 10 != 0
                : i % 2 == 0;
            input[i] = chooseA ? new A(i) : new B(i);
        }
    }

    @Benchmark
    public int withInstanceof() {
        E e = input[(index++) & 1023];
        if (e instanceof A a) return a.n();
        if (e instanceof B b) return b.n();
        throw new AssertionError("Unexpected type");
    }

    @Benchmark
    public int withSwitch() {
        E e = input[(index++) & 1023];
        return switch (e) {
            case A(int n) -> n;
            case B(int n) -> n;
        };
    }
}
```

**Đây là skeleton JMH**, không phải đoạn có thể chạy chỉ bằng `javac` của JDK thuần. Phải cấu hình dependency JMH và annotation processor, chạy qua JMH runner/CI. Không cung cấp số benchmark giả định vì chưa chạy JMH thực tế.

**Những điều skeleton cố gắng kiểm soát:**
- Các đối tượng đầu vào được chuẩn bị tại `@Setup`, tránh đưa allocation của `new A`/`new B` vào phép đo chính.
- Hai benchmark đọc input từ cùng phân bố `50_50` hoặc `90_10`.
- Trả kết quả `int` để JMH có thể quan sát, tránh một biểu thức vô dụng bị loại bỏ.
- Có warm-up và fork; điều kiện chạy nên được ghi kèm JDK, hardware và cấu hình JVM.

**Giới hạn của chính skeleton:** Nó đo **toàn bộ thao tác** gồm tăng index, đọc mảng, phân loại kiểu và đọc component; không phải một phép đo độc lập chỉ của instruction `instanceof`. Cũng cần kiểm soát độ lớn/độ đa dạng input, state effects và xem generated code/profiler nếu chênh lệch quá nhỏ. Các tham số và iteration ở trên chỉ là điểm khởi đầu, không thay tiêu chí thống kê của dự án.

### 10.3. Cách đọc kết quả

Nếu JMH hiển thị `ns/op` hoặc `ops/s`, cần biết đó là **điểm đo cho benchmark cụ thể**, không phải chi phí cố định của feature Java. Nên:
1. So sánh trong cùng môi trường và JDK.
2. Chạy nhiều forks/iterations, xem độ phân tán và confidence interval phù hợp.
3. Tách kết quả theo phân bố subtype và guard.
4. Đảm bảo cả hai implementation đúng cùng semantics, cùng dữ liệu.
5. Thử thêm workload gần production, không chỉ microbenchmark cực nhỏ.
6. Ghi nhận thay đổi sau tối ưu; tránh tối ưu nhầm một phần chiếm tỷ trọng rất nhỏ.

Không kết luận “Java 21 pattern switch nhanh hơn X%” khi không có dữ liệu đo trực tiếp đủ tin cậy.

## 11. Profiling application trước khi refactor

Nếu ứng dụng đang chậm, hãy bắt đầu ở **tầng hệ thống**:
- CPU profile / wall-clock profile: thời gian nằm ở method nào? Có phải dispatch hay body?
- Allocation profile: object/chuỗi/DTO nào được tạo nhiều? Có phải do xử lý sau matching?
- GC và latency: thời gian dừng hoặc tải GC có làm trễ request?
- Phân bố input: subtype nào xuất hiện nhiều, tần suất null/guard hit ra sao?
- JDK và môi trường: JIT tiering, heap, CPU và contention có nhất quán giữa các lần đo không?

Các công cụ có thể dùng: **Java Flight Recorder (JFR)**, **JDK Mission Control (JMC)**, async-profiler, `jcmd` và JMH. Đây là các lựa chọn profiling/benchmark; không cần triển khai tất cả cho một tối ưu nhỏ.

### Một phương pháp tối ưu có trách nhiệm

1. Đưa ra giả thuyết cụ thể, ví dụ “handler kiểm tra lặp 15 subtype trong một hot loop”.
2. Xác minh bằng profiler và thống kê input.
3. Viết test bảo đảm behavior cũ và mới tương đương, gồm null, nested record, guard và exception behavior.
4. Thiết kế benchmark chứa đủ subtype và tần suất hợp lý.
5. Thử **một thay đổi**: tách guard tốn kém, giảm phép deconstruct lặp không cần thiết, cache dữ liệu đã chuẩn hóa, hoặc thay cấu trúc dispatch nếu phù hợp.
6. Đo lại trên cùng môi trường; không giữ thay đổi làm code khó đọc nếu lợi ích không có ý nghĩa thống kê hoặc không cải thiện SLO.

Không cố “tối ưu” `instanceof` bằng cast không kiểm tra hoặc làm mất coverage của sealed switch. Chi phí của bug thường lớn hơn vài phép so kiểu.

## 12. Các hiểu nhầm phổ biến

| Hiểu nhầm | Vấn đề | Cách hiểu đúng |
| --- | --- | --- |
| “`instanceof` là chậm, phải tránh mọi nơi” | Không có bằng chứng cho workload thực | Type check đơn giản thường rẻ; đo khi nó là bottleneck |
| “Pattern switch luôn nhanh hơn if/else” | Cú pháp không bảo đảm thời gian runtime | JIT và phân bố subtype quyết định kết quả |
| “Ít dòng Java tức ít instruction và nhanh hơn” | JIT/bytecode hạ khác source | So behavior và đo runtime, không đếm dòng |
| “Sealed loại hết type checks tại runtime” | Exhaustiveness là kiểm tra tĩnh | Runtime vẫn phân loại object; tối ưu tùy compiler/JVM |
| “Record deconstruction miễn phí” | Có thể gọi accessor và nested patterns | Chi phí phụ thuộc accessor, độ sâu và tối ưu |
| “Guard sai thì compiler thử tiếp miễn phí” | Guard bản thân có chi phí | Guard false chỉ khiến case không được chọn; không coi miễn phí |
| “Một triệu vòng `System.nanoTime` cho số ns chính xác” | Warm-up, DCE, constant folding, OS noise | Dùng JMH với workload hợp lệ |
| “Thấy `invokedynamic` nghĩa là switch chậm” | Bytecode không phải final machine code | JIT có thể tối ưu dynamic linkage |
| “`getClass()==T.class` thay `instanceof T` là an toàn” | Khác semantics với subclass và null | Chỉ đổi khi domain thực sự yêu cầu exact-class check |
| “Record pattern luôn allocate thêm object” | Deconstruction không mặc nhiên tạo tuple | Tìm allocation thực bằng profiler |
| “Không có warning đồng nghĩa tối ưu” | Compiler type-safety không phải performance report | Dùng profiler/JMH riêng |
| “Nếu benchmark khác 1 ns chắc chắn có ý nghĩa” | Nhiễu và khác biệt máy có thể lấn át | Xem variance, confidence và tác động end-to-end |

## 13. Bài tập thực hành

### Bài tập 1 — Kiểm tra semantics trước tốc độ

Chạy `TypeCheckRuntimeCostDemo`. Thêm `Text("")`, `Quantity(0)` và `Wrapper(new Text("long"))`. Dự đoán output và số lần `longText` được gọi. Đảm bảo `bySwitch` và `byIf` vẫn cho cùng kết quả ở mọi ca.

### Bài tập 2 — Kiểm tra short-circuit của nested pattern

Tăng bộ đếm trong accessor của `Wrapper` hoặc tạo một record `TracedWrapper` với accessor riêng. So sánh số lần accessor được gọi khi record ngoài không khớp kiểu, khi component lồng null và khi component đầy đủ. Đừng dùng thời gian thực thi để suy ra số call; hãy dùng counter/assertion như ví dụ.

### Bài tập 3 — Tạo guard có chi phí đáng kể

Thay `longText` bằng một phép tính CPU-bound deterministic trên chuỗi (không I/O), rồi dùng profiler/JMH để xem phần thời gian nằm ở guard hay type dispatch. Không để guard tạo kết quả khác nhau giữa hai implementation khi benchmark.

### Bài tập 4 — So phân bố input

Dùng skeleton JMH chạy cả `50_50` và `90_10` trên cùng JDK/hardware; ghi lại throughput hoặc ns/op cùng độ phân tán. Thử thêm một kịch bản 99% `A`, nhưng không gán kết quả đo ở một workload cho mọi ứng dụng.

### Bài tập 5 — Khác biệt chính xác về kiểu

Tạo `class Base {}` và `class Child extends Base {}`. So sánh `child instanceof Base` với `child.getClass() == Base.class` và trường hợp reference null. Giải thích vì sao chỉ dựa trên benchmark để thay semantics là sai.

### Bài tập 6 — Phân loại chi phí

Cho một `switch` trên sealed hierarchy có record pattern lồng sâu và guard gọi regex. Hãy liệt kê phần chi phí nào thuộc type check, accessor, guard, và body. Đề xuất kế hoạch đo từng phần mà không thay đổi behavior. Nêu ít nhất hai lỗi benchmark bạn sẽ tránh.

## 14. Tổng kết

**Kiểm tra kiểu tại runtime là một thao tác phổ biến và thường rẻ, nhưng chi phí quan sát được của pattern matching có thể đến từ nhiều nguồn:** đánh giá selector, type compatibility, record accessor, nested matching, guard, nhánh rẽ và code trong case. Pattern `instanceof` và pattern `switch` không có thứ tự tốc độ được Java bảo đảm; HotSpot JIT có thể tối ưu cả hai theo profile và workload.

**Thực hành hiệu năng tốt:** bảo toàn semantics, giữ code dễ đọc, xác định hot path bằng profiler, thiết kế JMH đúng, thử phân bố subtype thực tế và xem tác động end-to-end trước khi refactor. Không vì lo ngại chi phí type check mà bỏ mất khả năng type-safety, exhaustive switch hoặc tính rõ ràng của domain model.

## Tài liệu tham khảo

- Java SE 21, Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java SE 21, Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Java Language Specification SE 21, `instanceof` expression (15.20.2): https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Java SE 21, Java Virtual Machine Specification, Instructions `instanceof` và `checkcast`: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JMH — Java Microbenchmark Harness: https://github.com/openjdk/jmh
