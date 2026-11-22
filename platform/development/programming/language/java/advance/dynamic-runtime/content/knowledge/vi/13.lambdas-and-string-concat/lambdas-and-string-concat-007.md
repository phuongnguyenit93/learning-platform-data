# 13.7 StringConcatFactory, recipe và đối số hằng trong phép nối chuỗi động

Trong Java hiện đại, biểu thức nối chuỗi như `"User=" + name + "; n=" + count` có thể được compiler biên dịch thành một **chỉ thị `invokedynamic`** thay vì chuỗi lệnh `new StringBuilder().append(...).toString()` viết tường minh. Bootstrap thường được dùng cho những call site này là **`java.lang.invoke.StringConcatFactory`**. Nó dựng `CallSite` và `MethodHandle` biểu diễn thao tác ghép chuỗi dựa trên **chữ ký của các đối số động**, một **recipe** mô tả thứ tự ghép và các **đối số hằng** từ bootstrap khi cần.

Điểm quan trọng nhất:

- `\u0001` (ký tự điều khiển **U+0001**) trong recipe là **một đối số động**: giá trị được cung cấp **mỗi lần invoke**.
- `\u0002` (ký tự điều khiển **U+0002**) trong recipe là **một đối số hằng**: giá trị được cung cấp **khi liên kết/bootstrap**.
- Mọi ký tự khác trong recipe là **literal text** sẽ xuất hiện nguyên vị trí khi ghép.
- **Số lần xuất hiện U+0001 phải bằng số tham số của `concatType`**; **số U+0002 phải bằng số phần tử trong `constants`**. Không khớp → `StringConcatException` khi gọi factory.
- `CallSite.type()` và `CallSite.getTarget().type()` phải đúng `MethodType` của phép nối. Các bootstrap constants **không nằm trong danh sách tham số runtime** của handle.

Bài này đi từ sơ đồ liên kết tới cú pháp recipe, demo Java 17+ chạy được, lỗi kiểm tra kiểu/placeholder, cách dùng `javap` để xem recipe thực trong class file, và các lưu ý tối ưu hóa.

## 1. Hai giai đoạn khác nhau: linkage và invocation

~~~text
Mã Java:       return "User=" + name + "; n=" + count;
                                 |
                                 v
javac (thường dùng invokedynamic với Java 9+)
                                 |
                                 v
Bytecode: invokedynamic ... (String,int)String
          BootstrapMethods -> StringConcatFactory.makeConcatWithConstants
          recipe ví dụ: "User=\\u0001; n=\\u0001"
                                 |
                    LẦN ĐẦU LINK SITE
                                 v
JVM truyền Lookup, tên, MethodType, recipe và static constants
                                 |
             StringConcatFactory tạo CallSite + target MethodHandle
                                 |
                    JVM xác minh target type
                                 |
                        LẦN GỌI RUNTIME
                                 v
       target("Lan", 7) -----> "User=Lan; n=7"
       target("An",  3) -----> "User=An; n=3"
~~~

**Linkage** là giai đoạn factory được gọi với `MethodType`, recipe, constants để tạo phép nối chuyên biệt. **Invocation** là giai đoạn handle nhận giá trị động thực tế rồi tạo chuỗi. Factory không chạy lại mỗi lần gọi cùng một call site đã liên kết để ghép chuỗi từ đầu; nó tạo khả năng ghép chuỗi để tái sử dụng.

Việc compiler có dùng `invokedynamic` hay không là chi tiết chiến lược sinh bytecode, không phải quy tắc Java bắt buộc cho mọi biểu thức. Với ví dụ `javac --release 17` ở phần dưới, có thể **quan sát thực tế** một `invokedynamic` và recipe bằng `javap`. Kết quả biểu thức vẫn phải phù hợp semantics nối chuỗi của Java Language Specification (JLS).

## 2. Hai API chính của StringConcatFactory

~~~java
public static CallSite makeConcat(
        MethodHandles.Lookup lookup,
        String name,
        MethodType concatType) throws StringConcatException;

public static CallSite makeConcatWithConstants(
        MethodHandles.Lookup lookup,
        String name,
        MethodType concatType,
        String recipe,
        Object... constants) throws StringConcatException;
~~~

Đây là **chữ ký API** được rút từ Java SE 17; không phải định nghĩa hàm để tự copy vào ứng dụng.

| Tham số | Ý nghĩa |
| --- | --- |
| `lookup` | `Lookup` đại diện cho ngữ cảnh caller. Theo Javadoc factory cần **full privilege access**; JVM cấp lookup thích hợp khi dùng làm bootstrap của `invokedynamic`. |
| `name` | Tên symbolic của call site. **Factory không dùng tên này để quyết định cách nối**; khi thật sự link `invokedynamic`, JVM lấy nó từ `NameAndType` của instruction. |
| `concatType` | Chữ ký của **target/call site**, gồm kiểu và số lượng **đối số động**, cùng return type. |
| `recipe` | Chỉ có ở `makeConcatWithConstants`; chuỗi mô tả literal và placeholder U+0001/U+0002. |
| `constants` | Các giá trị bootstrap tĩnh tương ứng từng U+0002; không biến thành tham số của `MethodHandle` khi invoke. |

### `makeConcat`: mọi đầu vào là đối số động

`makeConcat(lookup, name, concatType)` không nhận recipe hoặc bootstrap constants. Khi gọi target, nó nối tất cả đối số theo thứ tự từ trái sang phải, theo quy tắc String conversion. Những trường hợp biên được Javadoc nêu:

- Không có input: kết quả là chuỗi rỗng `""`.
- Một input: kết quả là biểu diễn chuỗi của input theo JLS string conversion.
- Từ hai input trở lên: chuyển từng input thành chuỗi và nối lần lượt, không tự chèn dấu phân cách.

Ví dụ `concatType=(String,int)String`, target nhận `("Lan",7)` và trả `"Lan7"`. Nếu muốn thêm `"User="`, `"; n="` hoặc dấu cách cố định, bạn phải truyền chúng như **dynamic args** hoặc dùng `makeConcatWithConstants`.

### `makeConcatWithConstants`: recipe chỉ đường ghép

`makeConcatWithConstants` thêm recipe, cho phép biểu diễn phần tĩnh **trong recipe** hoặc bằng **bootstrap constants**. Target vẫn chỉ nhận các **dynamic args** được đếm bởi U+0001. Chẳng hạn:

~~~text
concatType = (String,int)String
recipe     = "ID=" + U+0001 + "; label=" + U+0002 + "; n=" + U+0001
constants  = ["STATIC"]

runtime    = ("X", 7)
result     = "ID=X; label=STATIC; n=7"
~~~

Số U+0001: **2**, bằng parameter count `2`. Số U+0002: **1**, bằng length `constants=1`. Dù recipe có một static constant, `target.type()` vẫn là `(String,int)String`, không phải `(String,String,int)String`.

## 3. Recipe là chuỗi có hai marker đặc biệt, không phải expression parser

`StringConcatFactory` quét recipe từ **trái sang phải**; mỗi ký tự mang một trong ba ý nghĩa:

| Ký tự trong recipe | Giá trị Unicode | Nguồn nội dung | Khi nào cung cấp? |
| --- | --- | --- | --- |
| `\u0001` | U+0001 (SOH) | **Dynamic argument** kế tiếp, theo thứ tự tham số trong `concatType` | **Mỗi lần target được invoke** |
| `\u0002` | U+0002 (STX) | **Static constant** kế tiếp, theo thứ tự trong `constants` | **Khi bootstrap/liên kết** |
| Các ký tự khác | Ví dụ `U`, `s`, `e`, `r`, `=`, dấu cách, `:` | Literal character chính nó | Được nhúng vào recipe |

Recipe **không** có khái niệm tự tính biểu thức, biến tên `name` hoặc hỗ trợ escape marker bằng dấu backslash. Nếu xuất hiện U+0001/U+0002, chúng **luôn** được hiểu là placeholder. Ký hiệu `\u0001` trong tài liệu là cách *hiển thị mã điều khiển*; trong một `String recipe` thực, vị trí đó phải chứa ký tự Java `char` có giá trị 1. Tương tự với U+0002/giá trị 2.

Để Java source minh bạch và tránh vô tình đưa ký tự điều khiển không nhìn thấy vào editor, có thể viết:

~~~java
char ARG = (char) 1;     // U+0001: đối số động
char CONST = (char) 2;   // U+0002: hằng bootstrap

String recipe = "ID=" + ARG + "; label=" + CONST + "; n=" + ARG;
~~~

Đây là **đoạn mã minh họa** bên trong method, không phải file độc lập. Java compiler tạo chuỗi thực sự chứa U+0001/U+0002, và factory sẽ phân tích nó khi liên kết. Trong source cũng có thể dùng literal Java `"\u0001"` / `"\u0002"`, nhưng dùng phép ép `(char)1` giúp việc đọc code và tránh ký tự invisible trở nên dễ dàng.

### 3.1. Cách đọc recipe từng ký tự

~~~text
Recipe: "ID="  \u0001  "; label="  \u0002  "; n="  \u0001
             |                     |                   |
             v                     v                   v
         arg #0 "X"          constant #0        arg #1 7
                                "STATIC"
                         |
                         v
Kết quả: "ID=X; label=STATIC; n=7"
~~~

Đối số động thứ nhất và thứ hai được **tiêu thụ theo thứ tự**, không theo tên. Hai placeholder U+0001 giống nhau về ký hiệu nhưng đại diện **hai vị trí argument khác nhau**. Nếu muốn lặp lại cùng một input trong kết quả, bạn phải thiết kế chữ ký/recipe và cách cung cấp giá trị cho phù hợp; factory không có cú pháp như `{0}` để tự lặp lại parameter số 0. Nó không phải `MessageFormat`.

### 3.2. Literal text, static constant và dynamic argument là ba cách khác nhau

Ví dụ muốn ghép `"prefix:"` với giá trị `name`:

1. **Literal trong recipe**: `"prefix:" + ARG`. `prefix:` xuất hiện trực tiếp trong recipe.
2. **Static constant**: `CONST + ARG`, với `constants[0]="prefix:"`. Prefix truyền lúc linkage, không nằm trong target parameter list.
3. **Dynamic argument**: `ARG + ARG` và `concatType=(String,String)String`, invoke với `("prefix:", name)` mỗi lần.

Ba dạng có thể tạo cùng chuỗi đầu ra nhưng có **shape và chi phí** khác nhau: dynamic argument được truyền ở từng lần gọi; static constant là dữ liệu của bootstrap; literal recipe là thành phần ký tự trực tiếp.

**Không dùng U+0001 hoặc U+0002 làm một ký tự literal trần trong recipe.** Hai ký tự này là marker được dành riêng. Nếu thực sự muốn ghép một control character U+0001/U+0002 như dữ liệu, đưa nó vào một **constant string** rồi chèn qua U+0002 (hoặc truyền nó qua dynamic argument). Ví dụ chương trình dưới đây tạo một hằng `"[" + ARG + "/" + CONST + "]"` và đưa cả chuỗi ấy vào một static constant, nên marker nằm **trong giá trị hằng**, không bị parse lại như recipe.

## 4. Tương quan giữa MethodType, CallSite và số marker

Ví dụ:

~~~java
MethodType signature = MethodType.methodType(
        String.class, String.class, int.class);
// (String,int)String

CallSite site = StringConcatFactory.makeConcatWithConstants(
        MethodHandles.lookup(),
        "concat",
        signature,
        "ID=" + (char) 1 + "; kind=" + (char) 2 + "; count=" + (char) 1,
        "STATIC");
~~~

Đây là các statement minh họa trong method xử lý `StringConcatException`. Sau thành công:

~~~text
site.type()                 = (String,int)String
site.getTarget().type()     = (String,int)String
site.dynamicInvoker().type()= (String,int)String

dynamic marker count        = 2
bootstrap constant count    = 1
invokeExact arguments       = (String,int)
~~~

`MethodType` thuộc target **không chứa** `String recipe` hoặc các bootstrap constants. Recipe và constants phục vụ **linkage**, không nằm trên operand stack của lần gọi target.

Bất biến `CallSite`: khi site đã được tạo hợp lệ, `site.getTarget().type().equals(site.type())`. Khi dùng với một `invokedynamic` thực, JVM còn xác minh kiểu CallSite đó khớp descriptor được ghi trong class file. `StringConcatFactory` tạo một target phù hợp với `concatType` nếu factory thành công; không nên tự giả định target trả một kiểu khác rồi để JVM tự ép.

### Return type không bắt buộc chính xác `String.class`

Javadoc dùng điều kiện **“return type in concatType is assignable from String”**. Vì `String` implement `CharSequence` và kế thừa `Object`, các kiểu trả về như `String.class`, `CharSequence.class` hoặc `Object.class` là hợp lệ nếu thỏa các điều kiện khác. Đây là **ràng buộc hướng assignability**, không phải “chỉ chấp nhận String.class”.

Một ví dụ đã kiểm tra được:

~~~java
MethodType wideType = MethodType.methodType(Object.class, String.class);
CallSite site = StringConcatFactory.makeConcat(
        MethodHandles.lookup(), "concat", wideType);
Object actual = site.dynamicInvoker().invokeExact("hi");
// actual.equals("hi") == true
// site.type() == (String)Object
~~~

Ví dụ này là đoạn statement với một method `throws Throwable`. Dù **descriptor** nói trả `Object`, object thực sự tạo ra là chuỗi `String`; method handle có type đúng `(String)Object`. Ngược lại, `void.class` **không** là supertype của String, nên `(String)void` không hợp lệ để mô tả target nối chuỗi.

### Giới hạn tham số: **200 parameter slots**, không phải 200 ký tự

Theo Javadoc, số **parameter slots** trong `concatType` không được quá **200**. Loại `long` và `double` chiếm **hai JVM slots**; những tham số dạng `int`, `float` hoặc reference thường chiếm một slot. Do đó “200 slots” **không** có nghĩa luôn chấp nhận 200 tham số `long`, và càng không liên quan tới chiều dài chuỗi kết quả.

JVM còn có giới hạn cấu trúc class file đối với số slot của method invocation (mốc tổng quát 255), nên StringConcatFactory dành khoảng trống cho một số chiến lược triển khai và ấn định ngưỡng 200. Với phép nối cực lớn, tách thành các phép nối nhỏ hơn theo cấu trúc mà compiler/JIT hỗ trợ; đừng cố vượt ngưỡng bằng cách chèn placeholder tùy ý.

## 5. Các ràng buộc recipe cần kiểm trước khi tạo CallSite

| Điều kiện | Cách kiểm | Ví dụ đúng | Ví dụ sai |
| --- | --- | --- | --- |
| Tham số động | `count(U+0001) == concatType.parameterCount()` | Type `(String,int)String` với 2 marker `ARG` | Type có 2 tham số nhưng recipe có 1 `ARG` |
| Hằng bootstrap | `count(U+0002) == constants.length` | Recipe có 1 `CONST` và 1 constant | Recipe có 0 `CONST` nhưng truyền `"extra"` |
| Return type | `concatType.returnType().isAssignableFrom(String.class)` | `String`, `Object` | `void`, `int` |
| Kích thước method | `concatType.parameterSlotCount <= 200` (theo semantics descriptor JVM) | 2 tham số `String,int` dùng 2 slot | 201 tham số `int` dùng 201 slots |
| Quyền lookup | `lookup` có full privilege theo hợp đồng factory | `MethodHandles.lookup()` trong code ứng dụng bình thường | `publicLookup()` không đáp ứng yêu cầu full privilege |
| Null đầu vào | `lookup`/`name`/`concatType`/`recipe`/`constants` thích hợp không null; static constants không được null | `constants={"STATIC"}` | Static constant `null` qua marker `CONST` |

Khi gọi **trực tiếp** `StringConcatFactory.makeConcatWithConstants(...)` từ Java code, những mismatch kiểu/đếm thường ném **`StringConcatException`**; đầu vào null liên quan có thể ném **`NullPointerException`**. Nếu lỗi xảy ra **trong bootstrap của một `invokedynamic` thực**, JVM có thể chuyển lỗi linkage non-`Error` thành **`BootstrapMethodError`**, nên phải phân biệt lỗi API trực tiếp và lỗi instruction đang được liên kết.

Một factory được phép tối ưu cách thực thi mà không đổi kết quả. Không nên phụ thuộc vào subclass cụ thể của `CallSite` mà factory trả, trừ khi API cam kết. Hãy dùng `site.getTarget()`/`site.dynamicInvoker()` và so `site.type()` với `concatType`.

## 6. Dynamic `null`, static `null` và string conversion

### 6.1. Dynamic argument `null` hợp lệ

Theo Javadoc, một argument tại U+0001 có thể là `null`. Khi nối chuỗi, reference `null` được chuyển thành literal `"null"` theo JLS String Conversion:

~~~java
MethodType type = MethodType.methodType(
        String.class, String.class, int.class);
CallSite site = StringConcatFactory.makeConcat(
        MethodHandles.lookup(), "concat", type);
String out = (String) site.dynamicInvoker().invokeExact((String) null, 0);
// out.equals("null0") == true
~~~

Đoạn minh họa dùng `(String)null` để call-site type chính xác với `(String,int)String`; nếu viết literal `null` không có cast trong các tình huống signature-polymorphic phức tạp, compiler có thể không suy ra đúng type của argument `invokeExact`.

### 6.2. Static constant `null` bị từ chối

Với `makeConcatWithConstants`, **static constant được đưa vào recipe không được null** theo Java SE 17 API. Ví dụ:

~~~java
MethodType noArgs = MethodType.methodType(String.class);
String recipe = String.valueOf((char) 2);
StringConcatFactory.makeConcatWithConstants(
        MethodHandles.lookup(), "concat", noArgs, recipe, new Object[] { null });
~~~

Đây là snippet **cố ý gây `NullPointerException` tại factory**; nó không có nghĩa String concatenation thông thường cấm null. Cần phân biệt **đối số động null** (cho phép và tạo chuỗi `"null"`) với **static bootstrap constant null** (không hợp lệ với API này). Dùng `new Object[]{null}` khi minh họa để truyền **một phần tử constant có giá trị null**, không phải truyền cả mảng varargs null.

### 6.3. Chuyển object sang String

Các dynamic values được chuyển thành chuỗi theo semantics JLS `5.1.11` và phép cộng chuỗi `15.18.1`:

- Primitive `int=7` → `"7"`, `boolean=true` → `"true"`, v.v.
- Reference tới `String` → chính nội dung chuỗi đó.
- Reference `null` → `"null"`.
- Reference tới object khác → chuyển thành chuỗi theo contract tương ứng của object; không nên giả định mọi `toString()` đều rẻ hoặc không có side effects.

Với static constant, Javadoc nói factory **có thể** thực hiện String conversion của constant, gồm gọi `toString()` khi cần, **một lần** tại linkage. Đừng đặt side effects của `toString()` thành logic ứng dụng: thời điểm và chiến lược tối ưu hóa có thể làm những giả định đó khó bảo đảm. Nếu cần tính giá trị ở mỗi invocation, dùng **dynamic argument U+0001**, không dùng bootstrap constant.

## 7. Java 17+ hoàn chỉnh: hai factory, recipe, hằng và các lỗi có chủ đích

Tạo file **`ConcatRecipeDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.Arrays;

public final class ConcatRecipeDemo {
    static final char ARG = (char) 1;
    static final char CONST = (char) 2;

    static String compiled(String name, int n) {
        return "User=" + name + "; n=" + n;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType sig = MethodType.methodType(String.class, String.class, int.class);

        // 1. makeConcat: tat ca deu la dynamic arguments.
        CallSite simple = StringConcatFactory.makeConcat(lookup, "arbitrary", sig);
        String simpleResult = (String) simple.dynamicInvoker().invokeExact("Lan", 7);
        System.out.println("simple type = " + simple.type());
        System.out.println("simple = " + simpleResult);

        // 2. makeConcatWithConstants: literal text + hai dynamic markers.
        String recipe = "User=" + ARG + "; n=" + ARG;
        CallSite withText = StringConcatFactory.makeConcatWithConstants(
                lookup, "unusedName", sig, recipe);
        System.out.println("recipe result = " +
                (String) withText.dynamicInvoker().invokeExact("Lan", 7));

        // 3. Mot static constant duoc chen vao giua hai dynamic arguments.
        String withConstant = "ID=" + ARG + "; label=" + CONST + "; n=" + ARG;
        CallSite c = StringConcatFactory.makeConcatWithConstants(
                lookup, "concat", sig, withConstant, "STATIC");
        System.out.println("with constants type = " + c.type());
        System.out.println("with constants = " +
                (String) c.dynamicInvoker().invokeExact("X", 7));

        // 4. Can in ky tu U+0001/U+0002 that: truyen qua static constant.
        MethodType single = MethodType.methodType(String.class, String.class);
        String escapedRecipe = "literal=" + CONST + "; arg=" + ARG;
        CallSite escaped = StringConcatFactory.makeConcatWithConstants(
                lookup, "concat", single, escapedRecipe,
                "[" + ARG + "/" + CONST + "]");
        String literal = (String) escaped.dynamicInvoker().invokeExact("x");
        System.out.println("reserved characters preserved = " +
                literal.equals("literal=[" + ARG + "/" + CONST + "]; arg=x"));

        // 5. Khong co dynamic args; static constants khong thanh args cua target.
        MethodType noArgs = MethodType.methodType(String.class);
        CallSite empty = StringConcatFactory.makeConcat(lookup, "concat", noArgs);
        System.out.println("zero-args is empty = " +
                ((String) empty.dynamicInvoker().invokeExact()).isEmpty());
        CallSite constantsOnly = StringConcatFactory.makeConcatWithConstants(
                lookup, "concat", noArgs, "Hello, " + CONST, "world");
        System.out.println("constants only = " +
                (String) constantsOnly.dynamicInvoker().invokeExact());

        // 6. Return type Object hop le vi Object la supertype cua String.
        CallSite wide = StringConcatFactory.makeConcat(
                lookup, "concat", MethodType.methodType(Object.class, String.class));
        Object wideResult = wide.dynamicInvoker().invokeExact("hi");
        System.out.println("Object return = " + wide.type());
        System.out.println("Object actual String = " + wideResult.equals("hi"));

        // 7. Dynamic null la hop le va duoc chuyen thanh chuoi "null".
        String nullResult = (String) simple.dynamicInvoker().invokeExact((String) null, 0);
        System.out.println("dynamic null = " + nullResult);

        // 8. Dem sai dynamic markers.
        try {
            StringConcatFactory.makeConcatWithConstants(
                    lookup, "concat", sig, "only " + ARG);
        } catch (StringConcatException ex) {
            System.out.println("dynamic markers mismatch = " +
                    ex.getClass().getSimpleName());
        }

        // 9. Dem sai constant markers.
        try {
            StringConcatFactory.makeConcatWithConstants(
                    lookup, "concat", sig, recipe, "extra");
        } catch (StringConcatException ex) {
            System.out.println("constant markers mismatch = " +
                    ex.getClass().getSimpleName());
        }

        // 10. Return type void khong the nhan ket qua String.
        try {
            StringConcatFactory.makeConcat(lookup, "concat",
                    MethodType.methodType(void.class, String.class));
        } catch (StringConcatException ex) {
            System.out.println("void result mismatch = " +
                    ex.getClass().getSimpleName());
        }

        // 11. Static constant null.
        try {
            StringConcatFactory.makeConcatWithConstants(
                    lookup, "concat", noArgs, String.valueOf(CONST),
                    new Object[] { null });
        } catch (NullPointerException ex) {
            System.out.println("null static constant = " +
                    ex.getClass().getSimpleName());
        }

        // 12. Vuot qua 200 parameter slots.
        try {
            Class<?>[] types = new Class<?>[201];
            Arrays.fill(types, int.class);
            StringConcatFactory.makeConcat(
                    lookup, "concat", MethodType.methodType(String.class, types));
        } catch (StringConcatException ex) {
            System.out.println("201 parameter slots = " +
                    ex.getClass().getSimpleName());
        }

        // 13. Phep noi + that duoc javac bien dich thanh invokedynamic.
        System.out.println("javac concat = " + compiled("Lan", 7));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ConcatRecipeDemo.java
java ConcatRecipeDemo
~~~

**`stdout` chính xác đã được thử trên JDK 24, biên dịch với `--release 17`:**

~~~text
simple type = (String,int)String
simple = Lan7
recipe result = User=Lan; n=7
with constants type = (String,int)String
with constants = ID=X; label=STATIC; n=7
reserved characters preserved = true
zero-args is empty = true
constants only = Hello, world
Object return = (String)Object
Object actual String = true
dynamic null = null0
dynamic markers mismatch = StringConcatException
constant markers mismatch = StringConcatException
void result mismatch = StringConcatException
null static constant = NullPointerException
201 parameter slots = StringConcatException
javac concat = User=Lan; n=7
~~~

Ví dụ đã được biên dịch và chạy với JDK 24 ở chế độ `--release 17`. Lựa chọn `--release 17` hạn chế source/API về Java SE 17; điều này khác với khẳng định đã chạy trực tiếp trên một JVM 17. Các result strings, exception class names và method types ở trên đã được kiểm tra bằng việc chạy chương trình.

### 7.1. Diễn giải sáu dòng đầu

`makeConcat` nhận `("Lan",7)` nên trả `"Lan7"`. Không có dấu cách hay dấu phân cách vì factory đơn giản không có recipe.

`withText` nhận cùng hai dynamic args nhưng có recipe `"User=" + ARG + "; n=" + ARG` nên trả `"User=Lan; n=7"`; factory chèn literal text mà không cần tạo hai dynamic input mới.

`c` có cùng `MethodType=(String,int)String` nhưng recipe còn có `CONST` và static constant `"STATIC"`. Chữ `STATIC` không phải là đối số thứ ba khi invoke; kết quả `ID=X; label=STATIC; n=7` chứng minh nó được giữ trong phần liên kết.

### 7.2. Vì sao reserved characters không bị nhầm thành marker?

Trong `escapedRecipe`, chỉ có **một** U+0002 để đưa vào một constant string và **một** U+0001 cho dynamic `"x"`. Constant string chứa thật hai control characters ở giữa `[` và `]`, nhưng **giá trị hằng không được parse như recipe mới**. Kiểm tra bằng `String.equals` tránh in ký tự điều khiển vô hình lên console, nên output dễ xác minh là `true`.

### 7.3. Zero dynamic inputs và return type rộng

`empty` có target type `()String`, trả `""`. `constantsOnly` vẫn có target type `()String` vì recipe chỉ dùng một U+0002, không dùng U+0001; output là `Hello, world`. `wide` có target type `(String)Object` và trả object thực mang nội dung `"hi"`; ví dụ chứng minh return type **có thể là supertype của String**.

### 7.4. Các lỗi được bắt đúng giai đoạn

Các `try/catch` mô phỏng lỗi **khi gọi factory trực tiếp**, chưa phải lỗi liên kết một invokedynamic instruction thực:

- Recipe chứa 1 dynamic marker, type có 2 tham số → `StringConcatException`.
- Recipe không có static marker nhưng constants có 1 phần tử → `StringConcatException`.
- Return type `void` không nhận được kết quả `String` → `StringConcatException`.
- Static constant null → `NullPointerException`.
- 201 parameter slots, vượt ngưỡng 200 → `StringConcatException`.

Chương trình chỉ bắt những exception được chủ động tạo; các lỗi khác vẫn lộ ra thay vì bị catch `Throwable` tùy tiện. Đây là cách tốt để viết test cho các hợp đồng API.

## 8. Đọc bytecode: chứng minh compiler đã sinh invokedynamic thật

Chạy tiếp từ thư mục chứa class file:

~~~bash
javap -c -p ConcatRecipeDemo
javap -v -p ConcatRecipeDemo
~~~

Ở bản build `javac --release 17` đã kiểm tra, method `compiled` có bytecode dạng:

~~~text
static java.lang.String compiled(java.lang.String, int);
    Code:
       0: aload_0
       1: iload_1
       2: invokedynamic #7,  0
          // InvokeDynamic #0:makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
       7: areturn
~~~

**Số index** `#7`, `#0` và vị trí dòng có thể khác theo compiler/JDK, vì đó là tham chiếu vào constant pool, không phải API ổn định. Phần `BootstrapMethods` tương ứng (rút gọn để thấy cấu trúc) sẽ có:

~~~text
BootstrapMethods:
  0: ... REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants
    Method arguments:
      ... User=\u0001; n=\u0001
~~~

Ở đây `\u0001` là cách `javap` trình bày ký tự điều khiển trong recipe. Nó không phải hai ký tự `\` và `u` trong kết quả nối, mà biểu diễn placeholder cho dynamic arguments.

### 8.1. Ba thứ **không** được nhầm trong `javap`

| Thứ quan sát | Ví dụ | Vai trò |
| --- | --- | --- |
| Descriptor **của instruction** | `(Ljava/lang/String;I)Ljava/lang/String;` | Đúng hai dynamic args `String` và `int`; kiểu trả về `String` |
| Signature **của bootstrap** | `(Lookup,String,MethodType,String,Object[])CallSite` ở metadata method reference | Chữ ký method Java cung cấp linkage, **không phải** signature của việc nối chuỗi runtime |
| Recipe **static bootstrap argument** | `"User=\u0001; n=\u0001"` | Hướng dẫn chèn literal và argument theo thứ tự |

Để xem phương thức thật sự được compiler link, phải tìm dòng `invokedynamic` **nằm trong body `compiled`**, rồi theo `InvokeDynamic #...` đến `BootstrapMethods`. Mã `main` cũng chứa các phép nối chuỗi trong lệnh `System.out.println`, vì vậy có thể có **nhiều dòng invokedynamic khác**. Đừng lấy recipe của một call site khác để giải thích method `compiled`.

Một khác biệt then chốt: lời gọi Java như `StringConcatFactory.makeConcatWithConstants(lookup,...,recipe)` trong `main` là **gọi factory trực tiếp**, không tự sinh instruction `invokedynamic` ứng với chính `CallSite` bạn đang tạo. Instruction thật trong chương trình xuất hiện khi compiler sinh cho biểu thức `"User=" + name + "; n=" + n` (và có thể các phép nối khác). Đây là hai cách tiếp cận khác nhau để hiểu cùng API.

## 9. Lỗi phân biệt theo ba thời điểm

| Thời điểm | Ví dụ | Loại lỗi thường gặp | Cách nghĩ đúng |
| --- | --- | --- | --- |
| **Gọi factory trực tiếp** | Recipe thiếu U+0001, thừa U+0002, return `void`, >200 slots | `StringConcatException` | API từ chối **mô tả phép nối** sai |
| **Gọi factory trực tiếp** | Truyền recipe null hoặc static constant null | `NullPointerException` | Input null không hợp lệ với factory |
| **JVM linkage của invokedynamic** | Bootstrap ném non-`Error`, không trả CallSite hợp lệ hoặc target type không khớp descriptor | `BootstrapMethodError` theo quy tắc JVMS | Lỗi khi liên kết **instruction** |
| **Gọi MethodHandle** | `invokeExact` site mong đợi `(String)String` nhưng handle là `(Object)String` | `WrongMethodTypeException` | Sai **call-site type** khi invoke |
| **Runtime String conversion** | Method conversion của một object có logic lỗi | Exception từ conversion theo đường thực thi | Không đồng nhất với mismatch recipe |
| **Cơ chế khác** | `IllegalAccessException` khi tự lookup thành viên khác | Lỗi access lookup riêng | Không phải lỗi parse recipe |

Với `MethodHandle.invokeExact`, cả kiểu **tham số và kiểu kết quả** tại Java call-site phải **khớp chính xác** với `MethodHandle.type()`. Đừng giả định vì `String` là subtype của `Object` thì một `invokeExact` có thể tự đổi descriptor. Nếu cần đổi kiểu một cách hợp lệ, tạo adapter bằng `asType`, nhưng đó là lựa chọn của code gọi, không phải tính năng tự động sửa recipe.

`StringConcatException` kế thừa `ReflectiveOperationException`, là checked exception có thể phát sinh khi dựng phép nối. Trong chương trình demo, `main throws Throwable` bao phủ các lỗi của factory và `MethodHandle.invokeExact`.

## 10. Khi nào đặt hằng trong recipe, lúc nào dùng U+0002?

Đặt thẳng literal trong recipe thường là cách ngắn nhất cho dấu phân cách và văn bản đơn giản như `"User="` hoặc `"; n="`. U+0002 hữu ích khi cần cung cấp hằng **như một bootstrap argument riêng**:

- Một chuỗi hằng dài hoặc được tái sử dụng trong metadata/constant pool thay vì trải mọi ký tự trực tiếp vào recipe.
- Một hằng chứa ký tự U+0001 hoặc U+0002, vốn không thể nhúng nguyên nghĩa literal trực tiếp vào recipe.
- Một hằng có kiểu constant-pool phù hợp, được factory chuyển thành biểu diễn chuỗi khi liên kết; hãy kiểm tra hợp đồng `toString`, null và kích thước bootstrap arguments.
- Những chương trình sinh bytecode/DSL compiler chủ động chọn recipe shape để cân bằng số kiểu phép nối được tạo, số bootstrap constants và hiệu năng của runtime.

Cần cân nhắc API Note của `StringConcatFactory`: chiến lược advanced có thể cho bytecode invocation hiệu quả hơn chút ít trong một số trường hợp nhưng cũng có thể tạo **nhiều shape chuyên biệt** hơn ở runtime. Không phải “đưa mọi phần tĩnh vào U+0002” là mặc nhiên tối ưu hơn việc để literal trong recipe.

**Không dùng bootstrap constants làm kho dữ liệu mutable cho mỗi invocation.** Chúng được cung cấp ở linkage, được phép factory xử lý/convert tại thời điểm ấy. Khi dữ liệu cần thay đổi theo người dùng, request hoặc giao dịch, hãy truyền vào **dynamic argument U+0001**.

### Hằng trong class file khác với biến `final` trong mã nguồn

Từ “constant” trong bài này nói về **static arguments của bootstrap** được biểu diễn trong metadata class file theo rules của JVM. Nó không đồng nghĩa mọi object tham chiếu bởi biến Java `final` đều có thể nhét làm bootstrap constant trong một `invokedynamic` tùy ý. Class file có những loại constant được cho phép (như string, số nguyên/thực, method handle, method type, class, và những cấu trúc dynamic constant thích hợp); phải tuân thủ quy tắc của constant pool và `BootstrapMethods`.

Trong đoạn Java gọi API **trực tiếp**, bạn có thể truyền runtime object qua varargs theo chữ ký phương thức Java, nhưng điều đó **không chứng minh** nó biểu diễn được như một static bootstrap argument trong class file sinh ra theo chuẩn. Khi tự phát sinh `invokedynamic` bytecode, cần chọn đúng loại static argument được JVM hỗ trợ.

## 11. String conversion và thứ tự đánh giá có khác `+` thông thường không?

Hợp đồng của StringConcatFactory gắn với quy tắc **String conversion** (JLS `5.1.11`) và **String Concatenation Operator `+`** (JLS `15.18.1`). Những giá trị được chuyển thành chuỗi, rồi kết hợp theo thứ tự từ trái qua phải. Tuy vậy, không được suy ra từ đây rằng biểu thức đối số Java có thể được đánh giá tuỳ thứ tự:

~~~java
String output = "A=" + first() + ", B=" + second();
~~~

Đây là một ví dụ **minh họa**, cần định nghĩa `first()` và `second()`. Theo ngữ nghĩa Java, các biểu thức con được đánh giá theo thứ tự được ngôn ngữ quy định. Compiler dù dùng một `invokedynamic` cuối cùng vẫn phải giữ hành vi quan sát được của chương trình, bao gồm thứ tự side effects của việc đánh giá operand.

**Không đồng nhất** thứ tự đánh giá biểu thức với thứ tự factory parse recipe: recipe quy định **nơi đặt giá trị đã có**, trong khi Java evaluation order quy định **khi nào các giá trị runtime được tính** trước khi instruction được gọi. Đây là hai tầng khác nhau.

Với `char` và Unicode: recipe chứa các `char` UTF-16; hai marker là hai code units U+0001/U+0002. Các ký tự Unicode khác trong recipe được giữ theo chuỗi mã UTF-16 của Java. Nếu cần literal control character, truyền qua constant hoặc dynamic arg như ví dụ thay vì cố “escape bằng dấu gạch chéo” trong recipe.

## 12. Chọn StringConcatFactory hay StringBuilder?

### Khi bạn viết Java business code

Thông thường hãy viết biểu thức đơn giản:

~~~java
String message = "User=" + name + "; n=" + count;
~~~

Compiler/JVM tự chọn chiến lược ghép phù hợp. **Không cần và không nên** tự gọi `StringConcatFactory` cho mọi phép nối chuỗi; đó là API cấp thấp cho compiler, code generator, bytecode runtime hoặc framework cần tạo call site động. Với các phép append trong vòng lặp phức tạp hoặc cần kiểm soát dung lượng, một `StringBuilder` chủ động vẫn dễ dùng hơn. Đo hiệu năng thực tế thay vì mặc định factory nhanh hơn trong mọi workload.

### Khi bạn xây dựng compiler hoặc runtime

`StringConcatFactory` hợp lý nếu:

- Bạn sinh `invokedynamic` cho các biểu thức nối chuỗi trong một DSL.
- Bạn biết trước `MethodType` của các operand nhưng **không biết runtime values** cho đến lúc gọi.
- Bạn muốn pre-bind literal/static constants mà không tăng arity của target.
- Bạn cần bảo toàn hợp đồng liên kết JVM, với target type khớp descriptor của instruction.
- Bạn có test bytecode/constant pool/recipe shape và kiểm tra `StringConcatException`/`BootstrapMethodError` ở các tầng.

Hãy chú ý vòng đời class loader, lượng shape được sinh, kích thước recipe, phương án reuse/cache và throughput/latency. Factory có thể tối ưu bằng các chiến lược triển khai tùy JDK; **đừng phụ thuộc vào tên class ẩn, đường nội bộ hoặc dạng bytecode riêng**.

## 13. Checklist debug recipe theo thứ tự

1. **Đọc descriptor của invokedynamic:** xác định `MethodType` chính xác, gồm primitive/reference, return type và số/kiểu đối số động.
2. **Đếm U+0001:** bằng chính xác `concatType.parameterCount()`? Mỗi marker tương ứng một argument được truyền khi target chạy.
3. **Đếm U+0002:** bằng chính xác số static bootstrap constants? Hằng theo thứ tự xuất hiện marker.
4. **Kiểm tra return type:** `concatType.returnType().isAssignableFrom(String.class)` phải là `true`; `Object` có thể hợp lệ, `void` không hợp lệ.
5. **Kiểm tra parameter slots:** không vượt 200; nhớ `long` và `double` mỗi tham số chiếm hai slot.
6. **Kiểm tra null:** dynamic null là hợp lệ; static constant null bị từ chối.
7. **Kiểm tra literal control characters:** nếu literal U+0001/U+0002 xuất hiện trong **nội dung** bạn muốn nối, đừng đặt trần trong recipe.
8. **Kiểm tra quyền lookup:** cần full privilege access theo Javadoc factory.
9. **Xác định giai đoạn lỗi:** factory trực tiếp `StringConcatException`, link instruction `BootstrapMethodError`, gọi handle sai type `WrongMethodTypeException`.
10. **Tìm đúng BootstrapMethods entry:** nhiều phép nối có thể sinh nhiều `invokedynamic`; đối chiếu constant-pool index của instruction đang debug.
11. **Không phán đoán performance:** đo benchmark và kiểm tra tối ưu trên JVM thực tế.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Recipe `"A=" + ARG + ", B=" + ARG` có mấy dynamic arguments? Nếu `concatType=(String,int)String` thì hợp lệ không?

**Đáp án:** Có **hai U+0001** tương ứng hai dynamic args; type có hai tham số nên hợp lệ về số placeholder. Kết quả từ `("Lan",3)` là `"A=Lan, B=3"`.

**Câu 2.** Recipe `"A=" + ARG + ", C=" + CONST` có `constants={"fixed"}`, target có cần nhận thêm đối số `"fixed"` khi invoke không?

**Đáp án:** Không. Static constant thuộc linkage. Nếu `concatType=(String)String`, target chỉ nhận một `String` động và trả String.

**Câu 3.** Tại sao không thể nhét ký tự U+0001 trực tiếp vào recipe để nó được in nguyên nghĩa?

**Đáp án:** U+0001 là marker dành riêng cho dynamic argument. Cần truyền literal control character qua **static constant U+0002** hoặc dynamic argument, không đặt trần vào recipe.

**Câu 4.** `concatType=(String)Object` có bị từ chối vì return type không phải `String.class` không?

**Đáp án:** Không. `Object.class.isAssignableFrom(String.class)` là true, nên hợp lệ về return type; đối tượng kết quả vẫn là String.

**Câu 5.** `makeConcatWithConstants` có recipe chứa hai `CONST` nhưng chỉ một hằng trong `constants`. Factory làm gì?

**Đáp án:** `StringConcatException` vì số U+0002 khác số phần tử static constants.

**Câu 6.** Truyền `null` vào vị trí dynamic argument và truyền `null` dưới dạng static constant có cùng hành vi không?

**Đáp án:** Không. Dynamic null chuyển thành `"null"` theo String conversion; static null constant khiến factory ném `NullPointerException` theo hợp đồng API.

**Câu 7.** Nếu factory trực tiếp ném `StringConcatException`, khi một JVM instruction `invokedynamic` chạy với bootstrap tương tự có luôn thấy đúng loại đó ở caller không?

**Đáp án:** Không nhất thiết. Trong liên kết invokedynamic, lỗi non-`Error` của bootstrap thường được JVM bọc thành `BootstrapMethodError`; đây là tầng lỗi khác.

**Câu 8.** 150 tham số `long` có nằm trong 200 parameter slots không?

**Đáp án:** Không. Mỗi `long` chiếm 2 slots, tổng 300, vượt giới hạn StringConcatFactory. (Trong thực tế còn có ràng buộc số slots của JVM descriptor, nên một descriptor chứa 150 `long` có thể không hợp lệ ngay ở tầng khác.)

**Câu 9.** Trong `javap -v`, chữ ký `(Lookup,String,MethodType,String,Object[])CallSite` là chữ ký của target nối chuỗi runtime?

**Đáp án:** Không. Đó là chữ ký của **bootstrap method**. Kiểu target nằm ở descriptor ngay tại instruction `invokedynamic`.

**Câu 10.** Có nên chủ động đưa mọi literal vào U+0002 để đạt performance tốt nhất?

**Đáp án:** Không. Lựa chọn recipe, inline literal và static constants ảnh hưởng số lượng shape sinh ra; cần cân bằng trên workload, và thường để compiler/JDK quyết định cho Java source bình thường.

## Tài liệu chính thức

- [Java SE 17 — StringConcatFactory: makeConcat, makeConcatWithConstants, recipe và linkage invariants](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html)
- [Java SE 17 — StringConcatException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatException.html)
- [Java SE 17 — CallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [JLS Java SE 17 — `5.1.11 String Conversion`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.11)
- [JLS Java SE 17 — `15.18.1 String Concatenation Operator +`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.1)
- [JVMS Java SE 17 — `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS Java SE 17 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
