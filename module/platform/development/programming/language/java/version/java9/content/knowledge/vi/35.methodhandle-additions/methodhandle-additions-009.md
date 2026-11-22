# Kiểm tra MethodType của từng bước kết hợp MethodHandle trong Java

## Mục tiêu

Trong nhóm **MethodHandle mở rộng**, việc kết hợp nhiều method handle đòi hỏi kiểm tra chính xác chữ ký ở từng bước. **MethodType** mô tả kiểu trả về và danh sách kiểu tham số của một lời gọi. Mỗi MethodHandle có một MethodType cố định, có thể đọc bằng phương thức **type()**.

Khi ghép các handle bằng những combinator như **filterArguments()**, **filterReturnValue()**, **collectArguments()**, **foldArguments()**, **guardWithTest()** hoặc **permuteArguments()**, kiểu đầu ra của bước trước phải tương thích với kiểu đầu vào mà bước sau yêu cầu. Một pipeline có thể hợp lệ ở từng handle riêng lẻ nhưng thất bại tại điểm ghép vì sai kiểu trả về, sai vị trí tham số, sai thứ tự hoặc khác biệt giữa kiểu primitive và wrapper.

Cách làm an toàn là xác định MethodType ban đầu, tính kiểu mong đợi sau mỗi combinator, gọi **type()** để kiểm tra kết quả thực tế và chỉ dùng **asType()** khi thật sự muốn thêm một bước chuyển đổi kiểu.

## 1. MethodType mô tả chữ ký của MethodHandle

Một MethodType chứa:

- Kiểu trả về của lời gọi.
- Số lượng tham số.
- Kiểu của từng tham số theo đúng thứ tự.

Ví dụ:

```java
MethodType type = MethodType.methodType(
        String.class, int.class, boolean.class);
```

Chữ ký này có nghĩa là phương thức nhận một int và một boolean, rồi trả về String:

```text
(int, boolean)String
```

Một số MethodType thường gặp:

| MethodType | Ý nghĩa |
|---|---|
| ()void | Không nhận tham số, không trả về giá trị |
| ()int | Không nhận tham số, trả về int |
| (String)int | Nhận String, trả về int |
| (int, int)int | Nhận hai int, trả về int |
| (Object)String | Nhận Object, trả về String |

MethodType phân biệt chính xác primitive và reference type. Các kiểu int, long, boolean khác Integer, Long, Boolean. String khác Object. Số lượng tham số và thứ tự tham số cũng là một phần của chữ ký.

Các phương thức hữu ích:

```java
MethodType type = handle.type();

Class<?> returnType = type.returnType();
int count = type.parameterCount();
Class<?> firstParameter = type.parameterType(0);

List<Class<?>> parameters = type.parameterList();
```

MethodType là immutable. Các phương thức như **changeReturnType()**, **changeParameterType()**, **insertParameterTypes()** và **dropParameterTypes()** tạo MethodType mới thay vì sửa đối tượng hiện có.

## 2. Tạo và kiểm tra MethodType ngay từ đầu

Khi tìm một method handle bằng Lookup, MethodType truyền vào phải mô tả đúng phương thức cần tìm.

Ví dụ tìm static method nhận String và trả int:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle parser = lookup.findStatic(
        Parser.class,
        "parse",
        MethodType.methodType(int.class, String.class));
```

Sau khi tìm được handle, luôn có thể kiểm tra lại:

```java
MethodType actual = parser.type();
MethodType expected =
        MethodType.methodType(int.class, String.class);

if (!actual.equals(expected)) {
    throw new IllegalStateException(
            "Unexpected MethodType: " + actual);
}
```

Với instance method, MethodHandle tạo bởi **findVirtual()** có thêm receiver làm tham số đầu tiên của handle. Ví dụ, một instance method String transform(int) của lớp Worker có handle type là **(Worker, int)String**. Cần tính receiver này khi kiểm tra các bước kết hợp tiếp theo.

Nếu method được tìm không tồn tại, Lookup có thể ném **NoSuchMethodException**. Nếu caller không có quyền truy cập, có thể ném **IllegalAccessException**. Kiểu trả về hoặc tham số sai trong descriptor cũng khiến việc tìm handle thất bại.

## 3. Kiểm tra sau từng combinator

Không chỉ kiểm tra handle ban đầu và handle cuối cùng. Hãy đặt một điểm kiểm tra sau mỗi bước ghép. Khi pipeline dài, điều này giúp xác định chính xác combinator nào tạo ra chữ ký ngoài dự kiến.

Một helper đơn giản:

```java
static MethodHandle checkType(
        String step,
        MethodHandle handle,
        MethodType expected) {

    MethodType actual = handle.type();

    if (!actual.equals(expected)) {
        throw new IllegalStateException(
                step + ": expected " + expected
                        + " but got " + actual);
    }

    return handle;
}
```

Cách gọi:

```java
MethodHandle next = checkType(
        "after filterArguments",
        combined,
        MethodType.methodType(int.class, String.class));
```

Đối chiếu bằng **equals()** giúp kiểm tra cả kiểu trả về, số lượng tham số, kiểu từng tham số và thứ tự. Nếu chỉ in type ra console mà không so sánh, sai lệch có thể bị bỏ sót trong log dài.

## 4. Các quy tắc kiểu của combinator thường dùng

### filterArguments()

Combinator này chèn một hoặc nhiều filter trước các tham số tương ứng của target.

Với mỗi vị trí được lọc:

- Kiểu trả về của filter phải khớp kiểu tham số tương ứng của target.
- Các tham số của filter thay thế tham số target đó trong MethodType mới.
- Kiểu trả về của handle kết quả giữ nguyên kiểu trả về của target.

Ví dụ target là (String)int và filter là (String)String. Filter chuyển đổi đầu vào String trước khi target chạy. Kết quả vẫn có type (String)int.

```java
MethodHandle normalizedParser =
        MethodHandles.filterArguments(
                parser, 0, normalizer);

System.out.println(normalizedParser.type());
// (String)int
```

Nếu filter trả về kiểu không khớp tham số target ở vị trí đó, combinator không thể tạo pipeline theo chữ ký yêu cầu.

### filterReturnValue()

Combinator này nối một filter vào giá trị trả về của target:

- Tham số của filter phải nhận kiểu trả về của target.
- Các tham số của handle kết quả giống target.
- Kiểu trả về của handle kết quả là kiểu trả về của filter.

Ví dụ target (String)int và formatter (int)String tạo thành handle (String)String:

```java
MethodHandle formatted =
        MethodHandles.filterReturnValue(
                normalizedParser, formatter);

System.out.println(formatted.type());
// (String)String
```

Nếu target trả void, filter phải là một handle không tham số; kết quả giữ các tham số target và dùng kiểu trả về của filter.

### collectArguments()

Combinator này đưa kết quả của một handle vào một vị trí tham số của target:

- Kiểu trả về của filter phải khớp kiểu tham số target tại vị trí được chọn.
- Các tham số của filter được đưa vào MethodType kết quả tại vị trí đó.
- Các tham số target khác vẫn được giữ theo thứ tự.

Ví dụ target nhận (int, String)String và filter nhận (String)int. Khi collectArguments tại vị trí 0, kết quả nhận (String, String)String: tham số String đầu tiên được đưa qua filter thành int, tham số String thứ hai tiếp tục đi vào target.

Với filter trả void, filter được thực hiện như bước phụ và các tham số target tại vị trí ghép vẫn được giữ. Vì vậy, cần kiểm tra chính xác MethodType sau khi tạo thay vì suy luận chỉ từ số lượng tham số.

### foldArguments()

Combinator này kết hợp một bước tính toán với target, đưa kết quả của combiner vào target theo quy tắc của overload được chọn. Các tham số đầu vào có thể được dùng chung giữa combiner và target.

Có hai overload chính: **foldArguments(target, combiner)** và **foldArguments(target, pos, combiner)**. Vị trí pos ảnh hưởng đến nhóm tham số được combiner tiêu thụ và vị trí nhận kết quả trong target.

Do quy tắc phụ thuộc overload và kiểu trả về của combiner, hãy xác định chữ ký của cả hai handle, tạo kết quả, rồi kiểm tra ngay **result.type()**. Không dùng foldArguments chỉ dựa trên cảm giác rằng combiner chạy trước target; thứ tự tham số cũng là một phần của hợp đồng.

### guardWithTest()

Combinator này chọn một trong hai target dựa trên kết quả boolean của test:

- Test phải trả boolean.
- Các tham số của test phải khớp phần đầu danh sách tham số của target.
- Target và fallback phải có cùng MethodType.
- Handle kết quả có MethodType bằng target.

Ví dụ test (String)boolean, target (String)String và fallback (String)String tạo ra kết quả (String)String:

```java
MethodHandle guarded = MethodHandles.guardWithTest(
        test, target, fallback);

System.out.println(guarded.type());
// (String)String
```

Nếu target và fallback khác kiểu trả về hoặc khác kiểu tham số, không thể ghép thành một nhánh có chữ ký thống nhất.

### permuteArguments()

Combinator này đổi thứ tự, lặp lại hoặc bỏ qua tham số đầu vào khi chuyển chúng tới target.

- MethodType mới phải có cùng kiểu trả về với target.
- Mảng reorder có một phần tử cho mỗi tham số target.
- Mỗi chỉ số chỉ ra tham số trong MethodType mới sẽ cấp dữ liệu cho tham số target tương ứng.
- Kiểu tại vị trí được chọn phải khớp kiểu tham số target.

Ví dụ target (String, String)String có thể được tạo thành handle (String, String, String)String với reorder {2, 0}. Handle kết quả nhận ba String, dùng tham số thứ ba làm đối số đầu tiên của target và tham số thứ nhất làm đối số thứ hai; tham số thứ hai của handle kết quả không được dùng.

### catchException()

Combinator này tạo handle bắt một loại exception từ target rồi chuyển sang handler:

- Kiểu trả về của handler phải khớp kiểu trả về của target.
- Tham số đầu tiên của handler phải nhận được loại exception đã chọn.
- Các tham số tiếp theo của handler tương ứng với phần đầu danh sách tham số của target.
- Handle kết quả giữ MethodType của target.

Đọc kỹ chữ ký handler khi chỉ cần một phần tham số target. Nếu handler nhận sai loại exception hoặc trả về sai kiểu, bước kết hợp sẽ thất bại.

## 5. Khác biệt giữa kiểm tra chính xác và thích nghi kiểu

Một điểm dễ nhầm là **MethodType chính xác** và **MethodType có thể chuyển đổi** không phải một khái niệm.

### asType()

**asType()** tạo một handle adapter có MethodType mới nếu các chuyển đổi tham số và kết quả được phép:

```java
MethodType genericType =
        MethodType.methodType(Object.class, Object.class);

MethodHandle generic = formatted.asType(genericType);

System.out.println(generic.type());
// (Object)Object
```

Trong ví dụ, adapter nhận Object, chuyển đầu vào sang String để gọi handle gốc, rồi trả kết quả String dưới dạng Object. Handle gốc vẫn giữ MethodType ban đầu; chỉ handle adapter có type mới.

Chuyển đổi reference có thể cần cast khi chạy. Boxing và unboxing cũng có thể được áp dụng cho primitive/wrapper. Nếu giá trị runtime không phù hợp, lời gọi có thể ném ClassCastException hoặc NullPointerException. Nếu không tồn tại chuyển đổi hợp lệ, **asType()** ném WrongMethodTypeException.

### explicitCastArguments()

**explicitCastArguments()** cho phép một tập chuyển đổi tường minh rộng hơn so với asType trong một số trường hợp primitive. Chỉ dùng khi thật sự muốn semantics ép kiểu đó và đã kiểm tra trường hợp biên. Nó không thay thế việc thiết kế MethodType đúng cho các combinator.

### invokeExact() và invoke()

**invokeExact()** yêu cầu descriptor tại call site khớp chính xác với MethodType của handle. Kiểu tham số và kiểu trả về tại biểu thức gọi đều tham gia descriptor.

```java
String result =
        (String) formatted.invokeExact(" 21 ");
```

Ở đây call site có type (String)String. Nếu truyền Object hoặc nhận kết quả bằng kiểu khác mà không tạo adapter, có thể gặp WrongMethodTypeException.

**invoke()** cho phép thích nghi kiểu theo quy tắc chuyển đổi của MethodHandle. **invokeWithArguments()** thuận tiện khi có danh sách Object động, nhưng thường kém tường minh và không nên dùng để che giấu lỗi chữ ký trong pipeline được biết trước.

## 6. Quy trình kiểm tra từng bước kết hợp

Với một pipeline thực tế, hãy kiểm tra theo trình tự:

1. Xác định chính xác phương thức gốc và MethodType của nó.
2. Liệt kê từng filter, combiner, test, fallback hoặc handler cùng MethodType riêng.
3. Với mỗi combinator, xác định vị trí tham số được tiêu thụ, kiểu trả về cần khớp và kiểu tham số mới.
4. Tạo handle mới bằng đúng combinator.
5. Gọi type() ngay sau bước đó.
6. So sánh với MethodType mong đợi bằng equals().
7. Nếu cần chuyển đổi, tạo adapter bằng asType() thành một bước riêng và kiểm tra lại type().
8. Kiểm tra call site của invokeExact() có descriptor chính xác.
9. Chạy các trường hợp dữ liệu bình thường, biên và lỗi để phát hiện lỗi cast hoặc exception khi gọi.

Có thể biểu diễn pipeline trong một bảng:

| Bước | Handle | MethodType mong đợi |
|---|---|---|
| 1 | Parser ban đầu | (String)int |
| 2 | Sau filterArguments | (String)int |
| 3 | Sau filterReturnValue | (String)String |
| 4 | Sau guardWithTest | (String)String |
| 5 | Sau asType | (Object)Object |

Nếu một bước có type khác với dự kiến, dừng tại bước đó. Đừng tiếp tục ghép các combinator sau vì lỗi có thể chỉ lộ ra ở một điểm gọi xa hơn.

## 7. Ví dụ Java hoàn chỉnh: kiểm tra MethodType sau từng bước

Chương trình dưới đây xây dựng một pipeline gồm chuẩn hóa chuỗi, parse số, định dạng kết quả và chọn nhánh bằng guardWithTest. Sau mỗi bước, helper kiểm tra MethodType chính xác. Cuối cùng, ví dụ tạo adapter Object và một handle đổi thứ tự tham số bằng permuteArguments.

Tạo tệp **MethodTypeCompositionDemo.java**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class MethodTypeCompositionDemo {
    private static String normalize(String text) {
        return text == null ? "" : text.trim();
    }

    private static int parse(String text) {
        return Integer.parseInt(text);
    }

    private static String format(int value) {
        return "value=" + value;
    }

    private static boolean isPositiveText(String text) {
        try {
            return Integer.parseInt(normalize(text)) >= 0;
        } catch (NumberFormatException exception) {
            return false;
        }
    }

    private static String rejected(String text) {
        return "rejected: " + text;
    }

    private static String join(String first, String second) {
        return first + "|" + second;
    }

    private static MethodHandle checkType(
            String step,
            MethodHandle handle,
            MethodType expected) {
        MethodType actual = handle.type();
        if (!actual.equals(expected)) {
            throw new IllegalStateException(
                    step + ": expected " + expected + " but got " + actual);
        }
        System.out.println(step + ": " + actual);
        return handle;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle normalizer = lookup.findStatic(
                MethodTypeCompositionDemo.class, "normalize",
                MethodType.methodType(String.class, String.class));
        MethodHandle parser = lookup.findStatic(
                MethodTypeCompositionDemo.class, "parse",
                MethodType.methodType(int.class, String.class));
        MethodHandle formatter = lookup.findStatic(
                MethodTypeCompositionDemo.class, "format",
                MethodType.methodType(String.class, int.class));
        MethodHandle test = lookup.findStatic(
                MethodTypeCompositionDemo.class, "isPositiveText",
                MethodType.methodType(boolean.class, String.class));
        MethodHandle fallback = lookup.findStatic(
                MethodTypeCompositionDemo.class, "rejected",
                MethodType.methodType(String.class, String.class));

        MethodHandle normalizedParser = checkType(
                "after filterArguments",
                MethodHandles.filterArguments(parser, 0, normalizer),
                MethodType.methodType(int.class, String.class));

        MethodHandle pipeline = checkType(
                "after filterReturnValue",
                MethodHandles.filterReturnValue(normalizedParser, formatter),
                MethodType.methodType(String.class, String.class));

        MethodHandle guarded = checkType(
                "after guardWithTest",
                MethodHandles.guardWithTest(test, pipeline, fallback),
                MethodType.methodType(String.class, String.class));

        MethodHandle adapted = checkType(
                "after asType",
                guarded.asType(MethodType.methodType(Object.class, Object.class)),
                MethodType.methodType(Object.class, Object.class));

        System.out.println("positive: " + (String) guarded.invokeExact(" 21 "));
        System.out.println("negative: " + (String) guarded.invokeExact("-4"));
        System.out.println("invalid: " + (String) guarded.invokeExact("abc"));
        System.out.println("adapted: "
                + (Object) adapted.invokeExact((Object) " 7 "));

        MethodHandle join = lookup.findStatic(
                MethodTypeCompositionDemo.class, "join",
                MethodType.methodType(String.class, String.class, String.class));
        MethodType permutedType = MethodType.methodType(
                String.class, String.class, String.class, String.class);
        MethodHandle permuted = checkType(
                "after permuteArguments",
                MethodHandles.permuteArguments(join, permutedType, 2, 0),
                permutedType);

        System.out.println("permuted: "
                + (String) permuted.invokeExact("first", "unused", "third"));
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 -Xlint:all MethodTypeCompositionDemo.java
java MethodTypeCompositionDemo
```

Stdout chính xác:

```text
after filterArguments: (String)int
after filterReturnValue: (String)String
after guardWithTest: (String)String
after asType: (Object)Object
positive: value=21
negative: rejected: -4
invalid: rejected: abc
adapted: value=7
after permuteArguments: (String,String,String)String
permuted: third|first
```

Kết quả cho thấy mỗi combinator tạo một MethodType có thể dự đoán và kiểm tra được. Pipeline chính nhận String và trả String. Adapter asType mở rộng chữ ký bên ngoài thành Object nhưng không thay đổi handle gốc. permuteArguments tạo một chữ ký ba tham số và chuyển tham số thứ ba cùng tham số thứ nhất tới target.

## 8. Lỗi thường gặp và cách tránh

1. **Chỉ kiểm tra handle đầu tiên và cuối cùng**: sai lệch ở một combinator trung gian sẽ khó truy tìm. Kiểm tra type() sau từng bước.
2. **Nhầm int với Integer**: MethodType phân biệt primitive và wrapper. Dùng đúng kiểu khai báo hoặc tạo adapter rõ ràng.
3. **Sai thứ tự tham số**: cùng số lượng và cùng tập kiểu nhưng thứ tự khác vẫn là MethodType khác.
4. **Nhầm receiver của findVirtual()**: receiver trở thành tham số đầu tiên của handle instance.
5. **Cho rằng filterArguments đổi kiểu trả về**: combinator này giữ kiểu trả về của target; filter phải trả đúng kiểu tham số được lọc.
6. **Cho rằng filterReturnValue giữ kiểu trả về của target**: kiểu trả về mới là kiểu trả về của filter.
7. **Quên target và fallback phải cùng type trong guardWithTest()**: hai nhánh phải có cùng MethodType để tạo một handle thống nhất.
8. **Dùng asType() để che lỗi ghép**: adapter chỉ hợp lý khi muốn chuyển đổi kiểu có chủ đích; nó không sửa sai logic vị trí hoặc số lượng tham số.
9. **Quên descriptor của invokeExact()**: kiểu tĩnh của biểu thức gọi, bao gồm kiểu kết quả, phải khớp chính xác.
10. **Cho rằng in MethodType là đủ**: hãy so sánh với expected type bằng equals() và dừng ngay khi sai.
11. **Bỏ qua lỗi xảy ra khi adapter chạy**: reference cast, unboxing hoặc giá trị null có thể làm phát sinh lỗi ở runtime.
12. **Không kiểm thử dữ liệu lỗi**: filter hoặc test có thể ném exception; hãy thử dữ liệu hợp lệ, rỗng, sai định dạng và giá trị biên.

## Kết luận

MethodType là hợp đồng chữ ký của MethodHandle. Khi kết hợp handle, hãy xác định kiểu trả về và từng tham số ở mỗi bước, áp dụng đúng quy tắc của combinator, rồi kiểm tra **type().equals(expected)** ngay sau khi tạo handle mới.

Giữ việc chuyển đổi kiểu bằng asType() thành bước rõ ràng, phân biệt invokeExact() với invoke(), và đặc biệt chú ý receiver, thứ tự tham số cùng khác biệt primitive/reference. Cách kiểm tra theo từng bước giúp lỗi MethodType được phát hiện tại đúng điểm ghép thay vì xuất hiện muộn khi pipeline chạy.
