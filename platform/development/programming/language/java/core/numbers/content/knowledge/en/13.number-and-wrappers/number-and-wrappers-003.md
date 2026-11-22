# `Character` không kế thừa `Number` dù `char` là kiểu số

## 1. Nghịch lý thường gặp: `char` là integral type, nhưng `Character` không phải `Number`

Java phân chia các kiểu dữ liệu thành **kiểu nguyên thủy (*primitive types*)** và **kiểu tham chiếu (*reference types*)**. Trong nhóm nguyên thủy, `char` được Java Language Specification (JLS) xếp vào **kiểu số nguyên (*integral types*)**, bên cạnh `byte`, `short`, `int` và `long`.

Tuy nhiên, lớp bao (*wrapper class*) của nó — `java.lang.Character` — **không kế thừa `java.lang.Number`**.

Hai mệnh đề sau đều đúng:

1. **`char` là một primitive integral type**: có giá trị số nguyên không dấu từ 0 đến 65.535; tham gia nâng kiểu và phép toán số.
2. **`Character` là một reference type độc lập với `Number`**: nó bọc một đơn vị mã UTF-16; đối tượng `Character` không thể dùng làm một đối tượng `Number`.

Đây không phải mâu thuẫn. **Quan hệ của primitive không quyết định quan hệ kế thừa của wrapper**. `char` và `Character` là hai kiểu khác nhau; việc một lớp “đại diện” cho primitive không có nghĩa nó phải kế thừa cùng một lớp cha với các wrapper số khác.

Ví dụ:

~~~java
char letter = 'A';          // primitive integral, giá trị code unit 65
Character box = letter;     // autoboxing: char -> Character
int code = letter;         // widening primitive: char -> int
~~~

Ba dòng trên là đoạn minh họa, chưa phải class Java chạy độc lập.

Trong khi đó, `Number number = box;` **không biên dịch**: `Character` không là lớp con của `Number`. Việc tự động *unbox* hoặc *box* không cho phép Java tự biến `Character` thành `Integer` rồi gán cho `Number` trong một bước tùy tiện.

## 2. Phân biệt loại kiểu nguyên thủy và hệ phân cấp lớp

### 2.1. Phân loại primitive theo đặc tả Java

Các primitive số của Java gồm:

| Nhóm | Primitive | Ý nghĩa |
|---|---|---|
| **Integral** | `byte` | Số nguyên có dấu 8 bit |
| **Integral** | `short` | Số nguyên có dấu 16 bit |
| **Integral** | `int` | Số nguyên có dấu 32 bit |
| **Integral** | `long` | Số nguyên có dấu 64 bit |
| **Integral** | `char` | Số nguyên **không dấu** 16 bit, biểu diễn một **đơn vị mã UTF-16** |
| **Floating-point** | `float` | Số dấu phẩy động IEEE 754 binary32 |
| **Floating-point** | `double` | Số dấu phẩy động IEEE 754 binary64 |

`boolean` cũng là một primitive nhưng **không thuộc nhóm kiểu số**.

Sự hiện diện của `char` trong *integral types* có ý nghĩa về các quy tắc ngôn ngữ: `char` có thể được mở rộng thành `int`/`long`/`float`/`double` và tham gia nhiều phép toán số học sau khi được nâng kiểu.

Ví dụ:

~~~java
char c = 'A';
int codeUnit = c;            // 65
int nextCodeUnit = c + 1;    // 66, biểu thức có kiểu int
boolean beforeB = c < 'B';   // true
~~~

Đây là minh họa. Java so sánh **giá trị code unit**, không tự áp dụng thứ tự chữ cái theo một ngôn ngữ tự nhiên.

### 2.2. Hệ phân cấp *wrapper classes*

`Number` là **một abstract class** trong `java.lang`. Những lớp như `Byte`, `Short`, `Integer`, `Long`, `Float` và `Double` đều là lớp con của `Number`.

~~~text
java.lang.Object
├── java.lang.Number (abstract class)
│   ├── java.lang.Byte
│   ├── java.lang.Short
│   ├── java.lang.Integer
│   ├── java.lang.Long
│   ├── java.lang.Float
│   └── java.lang.Double
├── java.lang.Character
└── java.lang.Boolean
~~~

Sơ đồ này **chỉ minh họa các lớp liên quan**, không liệt kê toàn bộ các lớp con khác của `Number` như `BigInteger`, `BigDecimal` hoặc các lớp đếm nguyên tử. `Character` và `Boolean` trực tiếp nằm ngoài nhánh `Number`.

| Primitive | Wrapper | Wrapper kế thừa `Number`? |
|---|---|---|
| `byte` | `Byte` | Có |
| `short` | `Short` | Có |
| `int` | `Integer` | Có |
| `long` | `Long` | Có |
| `float` | `Float` | Có |
| `double` | `Double` | Có |
| `char` | `Character` | **Không** |
| `boolean` | `Boolean` | **Không** |

`Character` vẫn có thể được lưu trong một biến kiểu `Object`, và nó hiện thực `Comparable<Character>` cùng các giao diện liên quan, nhưng **nó không phải một `Number`**.

## 3. Mục đích của `Number` và `Character` khác nhau

### 3.1. `Number` cung cấp giao diện chuyển đổi số

`Number` định nghĩa các phương thức như:

- `intValue()`
- `longValue()`
- `floatValue()`
- `doubleValue()`
- `byteValue()`
- `shortValue()`

Chúng cho phép mã làm việc với một **đối tượng số** mà không cần biết lớp cụ thể khi chỉ muốn rút ra một giá trị primitive. Một số phép chuyển đổi có thể mất phần thập phân, tràn/thu hẹp hoặc mất chính xác tùy kiểu gốc và kiểu đích; **`Number` không cam kết mọi phương thức luôn giữ giá trị chính xác**.

Ví dụ:

~~~java
Number integer = Integer.valueOf(65);
Number decimal = Double.valueOf(12.5);

int a = integer.intValue(); // 65
int b = decimal.intValue(); // 12: cắt phần thập phân về 0
~~~

Đây là đoạn minh họa. `Number` không có phương thức `charValue()` chung bắt buộc cho mọi lớp con.

### 3.2. `Character` bọc một đơn vị mã UTF-16

`Character` cung cấp `charValue()` để lấy ra primitive `char` và các phương thức liên quan ký tự Unicode, chẳng hạn:

- `Character.isDigit(...)`: kiểm tra ký tự/chữ số Unicode theo đặc tả API.
- `Character.isLetter(...)`: phân loại chữ cái Unicode.
- `Character.getNumericValue(...)`: trả **giá trị số theo thuộc tính Unicode** khi có, không phải luôn là code unit.
- `Character.digit(..., radix)`: diễn giải ký tự thành chữ số theo cơ số nếu hợp lệ.
- `Character.isHighSurrogate(...)`, `isLowSurrogate(...)`, `toChars(...)`: hỗ trợ làm việc với UTF-16 và code points.

Cách hiểu đúng là: **`Character` quản lý ý nghĩa văn bản và code unit**, còn `Number` là lớp cha của những kiểu đối tượng cung cấp chuyển đổi primitive số.

Ví dụ, `'A'` mang **giá trị code unit là 65**, nhưng `Character.getNumericValue('A')` là **10**, do `A` có giá trị chữ số 10 trong các hệ cơ số từ 11 trở lên. Hai giá trị này giải quyết **hai câu hỏi khác nhau**.

Không được coi `Character.getNumericValue(c)` là phép thay thế chung cho `(int) c`. Với chữ số `'7'`, `(int) '7'` bằng **55** (code unit), còn `Character.getNumericValue('7')` bằng **7** (giá trị số của chữ số).

## 4. Boxing `char` tạo `Character`, không tạo `Number`

**Autoboxing** là chuyển đổi từ primitive sang lớp bao tương ứng khi ngữ cảnh cho phép:

~~~java
char primitive = 'A';
Character wrapper = primitive; // boxing char -> Character
Object asObject = primitive;   // boxing Character rồi widening reference Object
~~~

Trong cả hai trường hợp cần boxing, đối tượng thu được là **`Character`**. Java không box `char` trực tiếp thành `Integer`.

Đối chiếu:

~~~java
int primitiveInt = 65;
Integer integerWrapper = primitiveInt; // int -> Integer
Number asNumber = primitiveInt;        // int -> Integer -> Number
~~~

`Number asNumber = primitiveInt;` hợp lệ nhờ **boxing `int → Integer` rồi widening reference `Integer → Number`**.

Nhưng đoạn sau **không hợp lệ** (các dòng đã comment để bài vẫn hợp lệ về cú pháp):

~~~java
char c = 'A';
Character wrapper = c;

// Number invalid1 = wrapper; // lỗi: Character không phải Number
// Number invalid2 = c;       // lỗi: char không tự box thành Number
// Integer invalid3 = c;      // lỗi: không tự widen char thành int rồi box Integer
~~~

Thứ tự chuyển đổi tự động của Java có giới hạn. Không nên suy từ `int number = c;` hợp lệ rằng `Integer integer = c;` cũng hợp lệ.

Nếu thật sự cần biểu diễn **giá trị số của code unit** dưới dạng `Number`, hãy chuyển `char` thành `int` trước:

~~~java
char c = 'A';
int numericCodeUnit = c;
Number n = numericCodeUnit; // int -> Integer -> Number, giá trị 65
// Hoặc: Number n = (int) c;
~~~

`n` ở đây là một đối tượng `Integer` có giá trị 65, **không phải** `Character`. Việc chuyển đổi này chỉ bảo tồn **giá trị số của một code unit**, chưa nói điều gì về “chữ số” hay toàn bộ Unicode code point.

## 5. Unboxing `Character` có thể kết hợp widening primitive

Ở chiều ngược lại, `Character` có thể *unbox* về `char`, và sau đó primitive `char` có thể **widen** sang `int`, `long`, `float` hoặc `double` trong ngữ cảnh cho phép:

~~~java
Character wrapped = Character.valueOf('A');

char codeUnit = wrapped;     // unbox -> char
int asInt = wrapped;         // unbox char rồi widen -> int
long asLong = wrapped;       // unbox char rồi widen -> long
double asDouble = wrapped;   // unbox char rồi widen -> double
~~~

Đoạn minh họa này hợp lệ. Tuy nhiên, **`Character` không vì thế kế thừa `Number`**. Sự khác nhau là:

- **Chuyển đổi primitive**: định nghĩa bởi hệ thống kiểu ngôn ngữ Java.
- **Kế thừa lớp**: định nghĩa bởi quan hệ `extends`/`implements` của các reference type.

Nếu `wrapped` bằng `null`, biểu thức cần **unboxing** sẽ ném `NullPointerException`, kể cả khi sau đó muốn widen về `int`. Ví dụ `Character absent = null; int value = absent;` ném NPE khi chạy. Bọc trong `Object` cũng không giúp nó trở thành `Number`.

Không nên ép `(Number) (Object) wrapped` để “né lỗi biên dịch”: nếu đối tượng runtime vẫn là `Character`, phép cast tới `Number` sẽ ném `ClassCastException`.

## 6. Ví dụ Java 17+: chứng minh hierarchy và boxing

Tạo tệp `CharacterHierarchyDemo.java`:

~~~java
public class CharacterHierarchyDemo {
    public static void main(String[] args) {
        char letter = 'A';
        Character wrapped = letter;
        Object object = wrapped;

        System.out.println("primitiveChar=" + (int) letter);
        System.out.println("wrapperType="
                + wrapped.getClass().getSimpleName());
        System.out.println("isCharacter=" + (object instanceof Character));
        System.out.println("isNumber=" + (object instanceof Number));
        System.out.println("isComparable=" + (object instanceof Comparable));

        int codeUnit = wrapped;
        Number number = codeUnit;

        System.out.println("numberType="
                + number.getClass().getSimpleName());
        System.out.println("numberValue=" + number.intValue());
        System.out.println("letterCharValue=" + wrapped.charValue());

        System.out.println("charSuperclass="
                + Character.class.getSuperclass().getSimpleName());
        System.out.println("integerSuperclass="
                + Integer.class.getSuperclass().getSimpleName());
    }
}
~~~

Dùng JDK 17 trở lên:

~~~bash
javac CharacterHierarchyDemo.java
java CharacterHierarchyDemo
~~~

Đầu ra:

~~~text
primitiveChar=65
wrapperType=Character
isCharacter=true
isNumber=false
isComparable=true
numberType=Integer
numberValue=65
letterCharValue=A
charSuperclass=Object
integerSuperclass=Number
~~~

`object instanceof Number` trả `false` vì object runtime thật sự là `Character`. Sau khi chuyển `char` sang `int` rồi box vào `Number`, đối tượng runtime trở thành `Integer`; do đó `number.intValue()` trả 65.

`Character.class.getSuperclass()` trả `Object.class`, còn `Integer.class.getSuperclass()` trả `Number.class`. Đây là bằng chứng trực tiếp về **quan hệ lớp**, khác với quy tắc kiểu primitive.

## 7. `Number` trong API, generics và collection

Java generics chỉ nhận **reference types** làm tham số kiểu: `List<Character>` và `List<Number>` hợp lệ; `List<char>` hoặc `List<int>` **không hợp lệ**.

Một collection `List<Number>` nhận các đối tượng thuộc `Number`, nhưng **không nhận `Character`**:

~~~java
import java.util.ArrayList;
import java.util.List;

List<Number> numbers = new ArrayList<>();
numbers.add(Integer.valueOf(65));
numbers.add(Double.valueOf(1.25));

// numbers.add(Character.valueOf('A')); // lỗi biên dịch
// numbers.add('A');                     // không tự box char thành Number
~~~

Đây là đoạn minh họa, chưa phải tệp chạy độc lập.

Nếu muốn giữ **ký tự**, hãy dùng `List<Character>`:

~~~java
List<Character> chars = List.of('A', '7');
~~~

Nếu muốn giữ **giá trị số của code unit**, chuyển sang `int` và dùng `List<Integer>` hoặc `List<Number>`:

~~~java
char c = 'A';
List<Number> codeUnits = new ArrayList<>();
codeUnits.add((int) c); // boxing Integer; giá trị 65
~~~

**Cảnh báo về generics:** `List<Character>` không phải `List<Number>`, và `List<Integer>` cũng không phải `List<Number>` do tính bất biến (*invariance*) của generics, dù `Integer` là một `Number`. Nếu API chỉ **đọc** các số, có thể thiết kế `List<? extends Number>`, nhưng wildcard này cũng **không nhận `List<Character>`**.

### Ví dụ Java 17+ độc lập: collection đúng kiểu

Tạo tệp `CharacterCollectionsDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CharacterCollectionsDemo {
    static int sumAsInt(List<? extends Number> values) {
        int sum = 0;
        for (Number value : values) {
            sum += value.intValue();
        }
        return sum;
    }

    public static void main(String[] args) {
        List<Character> characters = List.of('A', '7');
        List<Integer> codeUnits = new ArrayList<>();
        List<Integer> digitValues = new ArrayList<>();

        for (Character c : characters) {
            codeUnits.add((int) c.charValue());
            digitValues.add(Character.getNumericValue(c));
        }

        System.out.println("characters=" + characters);
        System.out.println("codeUnits=" + codeUnits);
        System.out.println("digitValues=" + digitValues);
        System.out.println("codeUnitSum=" + sumAsInt(codeUnits));
        System.out.println("numericValueSum=" + sumAsInt(digitValues));
    }
}
~~~

~~~bash
javac CharacterCollectionsDemo.java
java CharacterCollectionsDemo
~~~

Đầu ra:

~~~text
characters=[A, 7]
codeUnits=[65, 55]
digitValues=[10, 7]
codeUnitSum=120
numericValueSum=17
~~~

Lớp `sumAsInt` minh họa API chấp nhận `List<? extends Number>`; ta phải đưa vào `List<Integer>` chứ không đưa `List<Character>`. Chương trình còn chứng minh rằng **mã số UTF-16** và **giá trị số của chữ số/ký tự Unicode** khác nhau.

**Lưu ý:** `sumAsInt` cộng `int` thông thường, nên ví dụ chỉ dùng dữ liệu nhỏ; nếu xử lý giá trị lớn, cần chọn kiểu/kiểm tra tràn và chính sách chuyển `Number.intValue()` thích hợp. Mã này không phải hàm cộng chính xác cho mọi lớp con của `Number`, đặc biệt `BigDecimal` có phần lẻ hoặc `Long` quá lớn.

## 8. Vì sao `Character` không cung cấp `intValue()` như `Number`?

`Character` có phương thức `charValue()` vì nhiệm vụ của nó là lưu và truy xuất **một UTF-16 code unit**. Nếu muốn lấy số nguyên, Java đã cung cấp **widening conversion `char → int`**:

~~~java
char letter = 'A';
int codeUnit = letter; // 65
~~~

Và nếu muốn một số có ý nghĩa về **chữ số**, dùng API khác:

~~~java
int unitA = (int) 'A';                    // 65
int numericA = Character.getNumericValue('A'); // 10
int digitA16 = Character.digit('A', 16); // 10
int digitA10 = Character.digit('A', 10); // -1, A không là chữ số cơ số 10

int unit7 = (int) '7';                    // 55
int numeric7 = Character.getNumericValue('7'); // 7
~~~

Đây là minh họa.

Phương thức `Character.getNumericValue` có thể trả `-1` khi ký tự không có giá trị số, hoặc `-2` khi giá trị số không biểu diễn được bằng số nguyên không âm kiểu `int` theo quy ước API. `Character.digit(ch, radix)` dùng tập chữ số phù hợp cơ số đã chỉ định và trả `-1` khi không hợp lệ.

Vì vậy, không thể có một phương thức chung `Number.intValue()` trên `Character` mà luôn diễn đạt đúng “giá trị số” trong mọi mục đích văn bản:

- **Mã UTF-16 của `'A'`** là 65.
- **Giá trị chữ số của `'A'` trong cơ số 16** là 10.
- **Giá trị chữ số của `'A'` trong cơ số 10** là không hợp lệ.
- **Ý nghĩa ngôn ngữ** của `'A'` là một ký tự chữ cái, không phải số lượng 65.

Việc giữ các API tách biệt giúp lập trình viên chọn ý nghĩa mà bài toán thật sự yêu cầu.

## 9. `char` là code unit UTF-16, không phải mọi Unicode code point

Một lý do khác để không đối xử `Character` như một số tổng quát: primitive `char` luôn đúng **16 bit**, nhưng Unicode có các mã điểm lớn hơn `0xFFFF`. Mã điểm ngoài **Basic Multilingual Plane (BMP)** cần **hai đơn vị mã UTF-16** (*surrogate pair*), không thể lưu trọn trong một `char` hoặc một `Character`.

Ví dụ emoji 😀 có mã điểm `U+1F600` và được lưu trong chuỗi UTF-16 bằng **hai** code unit:

- High surrogate: `0xD83D`.
- Low surrogate: `0xDE00`.

`String.length()` đếm code unit, không đếm mã điểm Unicode hoặc số ký tự hiển thị. Nếu muốn tính toán dựa trên mã điểm, hãy dùng `int` và API `codePointAt`/`codePoints`.

### Ví dụ Java 17+ chạy độc lập: một code point có hai `Character`

Tạo tệp `CharacterUnicodeDemo.java`:

~~~java
public class CharacterUnicodeDemo {
    public static void main(String[] args) {
        String smile = new String(Character.toChars(0x1F600));

        char high = smile.charAt(0);
        char low = smile.charAt(1);
        int codePoint = smile.codePointAt(0);
        Number numericCodePoint = codePoint;

        System.out.println("utf16Units=" + smile.length());
        System.out.println("codePoints="
                + smile.codePointCount(0, smile.length()));
        System.out.printf("high=%04X%n", (int) high);
        System.out.printf("low=%04X%n", (int) low);
        System.out.println("validPair="
                + Character.isSurrogatePair(high, low));
        System.out.printf("codePoint=U+%X%n", codePoint);
        System.out.println("numericCodePoint="
                + numericCodePoint.intValue());
    }
}
~~~

~~~bash
javac CharacterUnicodeDemo.java
java CharacterUnicodeDemo
~~~

Đầu ra:

~~~text
utf16Units=2
codePoints=1
high=D83D
low=DE00
validPair=true
codePoint=U+1F600
numericCodePoint=128512
~~~

Lưu ý `numericCodePoint` trong ví dụ thuộc kiểu `Number` vì **mã điểm đã được biểu diễn bằng primitive `int` rồi box thành `Integer`**. Nó không phải một đối tượng `Character`. `Character.isSurrogatePair` được dùng để giải thích sự ghép cặp hai code unit, không phải phương thức của `Number`.

**Một ký tự cảm nhận của người dùng (grapheme cluster)** đôi khi còn gồm nhiều mã điểm Unicode kết hợp, nên ngay cả `String.codePointCount` cũng không nhất thiết bằng số ký tự hiển thị.

## 10. Lỗi ép kiểu và kiểm tra bằng `instanceof`

Nếu có một biến `Object` đến từ API tổng quát, bạn có thể kiểm tra kiểu runtime:

~~~java
Object value = Character.valueOf('A');

boolean character = value instanceof Character; // true
boolean number = value instanceof Number;       // false
~~~

Đây là minh họa. Điều kiện `value instanceof Number` không tự chuyển kiểu; nó chỉ kiểm tra đối tượng runtime có thuộc hệ phân cấp `Number` hay không.

Thử ép kiểu theo đường vòng:

~~~java
Object value = Character.valueOf('A');
// Number n = (Number) value; // biên dịch được, nhưng ném ClassCastException
~~~

`(Number) value` về mặt cú pháp hợp lệ vì biến nguồn là `Object`, nhưng đối tượng runtime là `Character`, không phải `Number`; khi thực thi cast sẽ ném `ClassCastException`. **Không nên** sử dụng cast để “biến Character thành Number”.

Nếu API nhận nhiều loại đối tượng và bạn muốn chuyển `Character` thành code unit dạng số, hãy kiểm tra từng kiểu:

~~~java
static int toCodeUnit(Object value) {
    if (value instanceof Character c) {
        return c.charValue(); // widening char -> int
    }
    throw new IllegalArgumentException("Expected Character");
}
~~~

Đây là một **phương thức minh họa** có thể đặt trong class. Nó sử dụng pattern matching cho `instanceof` có sẵn từ Java 16, nên phù hợp Java 17+. Nó minh họa **chuyển giá trị**, không thay đổi phân cấp kế thừa của đối tượng đầu vào.

## 11. Các lỗi phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`char` là số nên `Character extends Number`.” | Không: primitive integral type và hierarchy reference type là hai cơ chế khác nhau. |
| “`Number n = 'A';` hợp lệ vì `'A'` có giá trị 65.” | Không: autoboxing `char` tạo `Character`, không tạo `Integer`. |
| “`Object obj = 'A';` tạo `Integer`.” | Không: đối tượng được box là `Character`. |
| “`int code = characterWrapper;` không hợp lệ vì wrapper không phải Number.” | Vẫn hợp lệ: unbox `Character → char` rồi widen `char → int`. |
| “`Integer number = characterWrapper;` sẽ tự widen và box.” | Không có chuyển đổi tự động kết hợp theo cách đó; hãy unbox/widen rõ ràng. |
| “`Character` có `intValue()` như `Number`.” | Không: dùng `charValue()` để lấy code unit hoặc các API Unicode nếu cần giá trị chữ số. |
| “`Character.getNumericValue('A')` bằng 65.” | Sai: nó trả 10; `(int) 'A'` mới bằng 65. |
| “`List<Number>` nhận mọi wrapper primitive.” | Không: `Character` và `Boolean` không thuộc `Number`. |
| “`List<Integer>` có thể gán vào `List<Number>`.” | Không: generics bất biến; có thể dùng `List<? extends Number>` cho API đọc phù hợp. |
| “Một `Character` có thể chứa mọi Unicode code point.” | Không: `Character` bọc một UTF-16 code unit; mã điểm ngoài BMP cần hai code unit. |
| “Cast `Object` chứa `Character` sang `Number` sẽ chuyển được mã.” | Không: ném `ClassCastException` khi chạy. |

## 12. Khi nào dùng `Character`, `Integer` hoặc `Number`?

**Chọn `char`/`Character`** khi thao tác một code unit UTF-16, ví dụ so sánh dấu phân cách `':'`, lưu ký tự BMP đơn giản hoặc dùng API nhận `char`. `Character` phù hợp khi ngữ cảnh yêu cầu tham chiếu, generics hoặc cho phép `null`; `char` tránh boxing khi chỉ cần primitive.

**Chọn `int`/`Integer`** khi thao tác **giá trị số của code unit**, mã điểm Unicode hoặc một số nguyên thông thường vừa miền. Khi xử lý Unicode code point, API kiểu `int` rộng hơn `char` và có thể chứa `U+1F600`. Nhưng cần phân biệt code point với các đơn vị mã UTF-16 và grapheme cluster.

**Chọn `Number`** khi API thực sự cần đa hình giữa các **đối tượng số**, chẳng hạn nhận cả `Integer` và `Double` để đọc dưới dạng primitive theo hợp đồng rõ ràng. `Number` là abstraction rộng, không tự cung cấp số học chính xác phổ quát hoặc đảm bảo các phép chuyển đổi không mất dữ liệu.

**Chọn `String`** cho văn bản hoàn chỉnh (tên, câu, từ, biểu tượng), thay vì cố ép mỗi đơn vị `char` thành một `Number`. Nếu cần chuyển dữ liệu Unicode sang byte, sử dụng charset như UTF-8; primitive cast không phải mã hóa ký tự.

### Checklist trước khi chuyển giữa “ký tự” và “số”

1. Giá trị đang là **primitive `char`** hay **object `Character`**?
2. Mục tiêu là **mã đơn vị UTF-16**, **mã điểm Unicode**, hay **giá trị chữ số**?
3. Có đang dùng API/collection chỉ nhận `Number` không? Nếu có, hãy biểu diễn số bằng `int`/`Integer` theo ý nghĩa thích hợp.
4. Có `null` ở wrapper không? Unboxing có thể ném `NullPointerException`.
5. Có code point ngoài BMP không? Một `Character` sẽ không chứa trọn mã điểm ấy.
6. Có nguy cơ mất dữ liệu khi cast sang `byte`/`short` hoặc đổi thành `float` không? Kiểm tra miền và yêu cầu chính xác.
7. Kiểm tra ở cả **thời điểm biên dịch** (gán/overload/generics) và **thời điểm chạy** (`instanceof`/`ClassCastException`).

## 13. Tự kiểm tra kiến thức

1. `char` được xếp vào nhóm primitive nào trong Java? Miền giá trị của nó?
2. `Character` kế thừa trực tiếp từ lớp nào? `Integer` kế thừa trực tiếp từ lớp nào?
3. Tại sao `Number n = Character.valueOf('A');` không biên dịch?
4. Tại sao `int code = Character.valueOf('A');` có thể biên dịch, dù `Character` không phải `Number`?
5. `(int) '7'` khác `Character.getNumericValue('7')` ra sao?
6. Muốn thêm mã code unit của `'A'` vào `List<Number>`, bạn phải làm gì?
7. Vì sao emoji `U+1F600` không lưu trong một `Character` duy nhất?
8. `Object o = Character.valueOf('A');` thì `o instanceof Number` là `true` hay `false`? Vì sao?
9. `Character c = null; int n = c;` thất bại khi biên dịch hay khi chạy?
10. Có thể dùng `Number.intValue()` để xử lý tất cả số thực mà không mất dữ liệu không?

**Đáp án gợi ý:** (1) Kiểu nguyên thủy integral, 0..65535. (2) `Object` và `Number`. (3) `Character` không nằm dưới `Number`. (4) Unboxing `Character → char` rồi widening `char → int`. (5) 55 (code unit) so với 7 (giá trị chữ số). (6) Chuyển `char` thành `int` trước rồi box `Integer`, ví dụ `numbers.add((int) 'A')`. (7) Nó cần hai code unit surrogate của UTF-16. (8) `false`. (9) Biên dịch được nhưng ném `NullPointerException` khi unbox. (10) Không; phép chuyển `Number.intValue()` có thể mất phần thập phân hoặc vượt miền đích.

**Ghi nhớ:** **`char` là một kiểu số nguyên nguyên thủy**, nhưng **`Character` không kế thừa `Number`**. Primitive numeric promotion, autoboxing/unboxing, kế thừa lớp và ý nghĩa Unicode là **những cơ chế độc lập**. Khi cần số, chuyển **giá trị `char`** sang `int`/`Integer` một cách có chủ ý; khi cần ký tự, giữ `Character` hoặc dùng `String`/API Unicode phù hợp.