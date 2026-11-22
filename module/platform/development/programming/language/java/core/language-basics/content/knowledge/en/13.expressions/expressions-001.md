# Biểu thức tạo ra giá trị và có kiểu tại thời điểm biên dịch — Java 17+

## 1. Mục tiêu bài học

Trong Java, **biểu thức** (*expression*) là một cấu trúc cú pháp được đánh giá theo các quy tắc của ngôn ngữ. Với biểu thức tạo giá trị, kết quả có **một giá trị** và compiler xác định được **kiểu của biểu thức** trước khi chương trình chạy.

~~~java
int a = 7;
int b = 3;

int sum = a + b;       // Biểu thức a + b có kiểu int, giá trị 10
boolean larger = a > b; // Biểu thức a > b có kiểu boolean, giá trị true
String label = "Java"; // Literal chuỗi có kiểu String, giá trị "Java"
~~~

Ba điểm cần phân biệt:

1. **Kiểu tĩnh (*compile-time type*)**: compiler xác định từ toán hạng, toán tử, khai báo và ngữ cảnh.
2. **Giá trị lúc chạy (*runtime value*)**: kết quả cụ thể khi biểu thức được đánh giá, tùy dữ liệu hiện thời.
3. **Đối tượng thực tế (*runtime object*)**: với biểu thức tham chiếu không null, object mà giá trị tham chiếu trỏ tới có thể thuộc class con của kiểu tĩnh.

Ví dụ `a + b` luôn có kiểu `int` trong các khai báo ở trên; nếu `a` và `b` thay đổi, **giá trị** có thể đổi nhưng **kiểu biểu thức không đổi**.

> Ngoại lệ cần nắm: có lời gọi method kiểu `void` được coi là biểu thức nhưng **không tạo ra một giá trị để dùng tiếp**. Một biểu thức có thể không hoàn tất bình thường nếu ném exception. Vì thế phát biểu “mọi biểu thức đều luôn trả về một giá trị” là quá tuyệt đối.

## 2. Biểu thức khác câu lệnh (*statement*) như thế nào?

Biểu thức tạo giá trị có thể là:

~~~java
42               // Literal int
2 + 3            // Phép cộng int
"Hi".length()    // Method invocation trả int
a > b            // Phép so sánh trả boolean
new StringBuilder("A") // Tạo object, cho giá trị tham chiếu
~~~

Những dòng này là **mảnh biểu thức**, không nhất thiết là những câu lệnh Java độc lập hợp lệ nếu chép nguyên cả dòng vào method.

Câu lệnh (*statement*) diễn đạt một hành động trong luồng thực thi: khai báo biến, gán, rẽ nhánh, vòng lặp, `return`, v.v.

~~~java
int result = 2 + 3;         // Câu lệnh khai báo; initializer là biểu thức
System.out.println(result); // Câu lệnh biểu thức: method invocation
if (result > 4) {           // Câu lệnh if; điều kiện là biểu thức boolean
    System.out.println("ok");
}
~~~

**Không phải mọi biểu thức đều đứng một mình thành câu lệnh được.**

~~~java
// 2 + 3; // Sai: phép cộng đơn thuần không phải statement expression hợp lệ
~~~

Một số nhóm biểu thức **được phép dùng như câu lệnh** (*statement expressions*) là phép gán, tăng/giảm, một số lời gọi method và biểu thức tạo class instance:

~~~java
result = 10;             // Assignment expression dùng làm câu lệnh
result++;                // Increment expression dùng làm câu lệnh
System.out.println(result); // Method invocation dùng làm câu lệnh
new StringBuilder("A");   // Class instance creation expression làm câu lệnh
~~~

**Ghi nhớ:** câu lệnh và biểu thức không phải hai khái niệm đồng nghĩa. Một câu lệnh có thể chứa nhiều biểu thức con.

## 3. Kiểu biểu thức được xác định như thế nào?

Compiler áp dụng các quy tắc kiểu Java, chẳng hạn:

| Biểu thức | Kiểu tĩnh | Ví dụ giá trị |
|---|---|---|
| `10` | `int` | `10` |
| `10L` | `long` | `10` |
| `2.5` | `double` | `2.5` |
| `2.5f` | `float` | `2.5` |
| `'A'` | `char` | UTF-16 code unit `'A'` |
| `true` | `boolean` | `true` |
| `"Java"` | `String` | Văn bản `Java` |
| `a + b` với a,b `int` | `int` | Ví dụ `10` |
| `a > b` với a,b `int` | `boolean` | Ví dụ `true` |
| `"Hi".length()` | `int` | `2` |
| `new int[3]` | `int[]` | Tham chiếu mảng mới |
| `new StringBuilder()` | `StringBuilder` | Tham chiếu object mới |

Không đoán kiểu từ tên biến hoặc hình thức giá trị in ra. Hãy xem **kiểu khai báo toán hạng, loại literal, chữ ký method** và **ngữ cảnh chuyển kiểu**.

Sơ đồ suy luận:

~~~mermaid
flowchart TD
    A["Biểu thức Java"] --> B["Xác định kiểu toán hạng / chữ ký / literal"]
    B --> C["Áp dụng toán tử và quy tắc chuyển kiểu"]
    C --> D["Kiểu tĩnh tại compile time"]
    D --> E["Compiler kiểm tra ngữ cảnh sử dụng"]
    E --> F["Khi chạy: đánh giá và tạo giá trị nếu hoàn tất bình thường"]
~~~

Sơ đồ mô tả quá trình **logic về kiểu và đánh giá**, không phải sơ đồ nội bộ bắt buộc của JVM.

## 4. Biểu thức số học: kiểu không nhất thiết bằng kiểu biến nhận

~~~java
int a = 7;
int b = 2;

int whole = a / b;       // Biểu thức int / int: kiểu int, giá trị 3
double alsoWhole = a / b; // Vẫn tính int: giá trị 3, sau đó đổi thành 3.0
double fractional = (double) a / b; // double / double: giá trị 3.5

System.out.println(whole);      // 3
System.out.println(alsoWhole);  // 3.0
System.out.println(fractional); // 3.5
~~~

**Tại sao `alsoWhole` không thành 3.5?** Phép chia `a / b` được thực hiện theo kiểu của **biểu thức** (`int`); chỉ sau đó kết quả `3` mới widening sang `double` để gán.

Phần `(double) a / b` khiến phép chia được tiến hành theo `double` ngay từ đầu, từ đó giữ phần lẻ.

**Không dùng kiểu biến đích để suy ngược phép tính đã xảy ra**. Với `var`, kiểu cũng được suy ra từ initializer:

~~~java
var result = a / b; // result có kiểu int
~~~

Không có chuyện `var` làm biểu thức tự chọn kiểu rộng hơn.

## 5. Numeric promotion: byte, short, char thường nâng thành int

Một phép cộng bình thường giữa hai biến `byte` tạo biểu thức kiểu `int`:

~~~java
byte left = 100;
byte right = 20;

int sum = left + right; // Kết quả biểu thức là int
System.out.println(sum); // 120

// byte invalid = left + right; // Lỗi compile: int không tự thu hẹp về byte
~~~

Điểm quan trọng:

- Cả hai biến là `byte`, nhưng quy tắc **binary numeric promotion** nâng lên `int` trước khi cộng.
- Compiler không tự suy ra “vì kết quả 120 vừa byte nên kiểu biểu thức sẽ là byte”.
- Muốn chuyển về byte cần cast phù hợp **và** tự kiểm tra giới hạn dữ liệu nếu không cho phép tràn.

Với `char`:

~~~java
char letter = 'A';
int nextCodeUnit = letter + 1; // Kết quả là int, giá trị 66
char nextLetter = (char) nextCodeUnit;
System.out.println(nextLetter); // B
~~~

Với một toán hạng `double`, biểu thức số học hỗn hợp thường được nâng tới `double`:

~~~java
double mixed = 7 + 0.5;
System.out.println(mixed); // 7.5
~~~

Không có widening/narrowing primitive số học từ hoặc sang `boolean`.

## 6. Kiểu tại compile time không bảo đảm tránh overflow

~~~java
long wrong = 2_000_000_000 + 2_000_000_000;
long right = 2_000_000_000L + 2_000_000_000;

System.out.println(wrong); // -294967296
System.out.println(right); // 4000000000
~~~

Ở dòng đầu:

1. Hai literal đều kiểu `int`.
2. Biểu thức `int + int` có kiểu `int` và **tràn** trong phép cộng.
3. Sau đó giá trị `int` bị tràn mới đổi sang `long` để gán.

Dòng thứ hai có toán hạng đầu kiểu `long`, nên phép cộng có kiểu `long` từ đầu.

**Compiler biết kiểu biểu thức nhưng không tự chứng minh biểu thức số học đáp ứng miền nghiệp vụ.** Nếu cần phát hiện tràn int, có thể dùng `Math.addExact(int, int)` khi phù hợp: method ném `ArithmeticException` nếu tổng vượt miền int.

## 7. So sánh và logic: kiểu boolean

Toán tử so sánh số trả `boolean`:

~~~java
int a = 7;
int b = 3;
boolean greater = a > b;
boolean equal = a == b;

System.out.println(greater); // true
System.out.println(equal);   // false
~~~

Toán tử logic `&&`, `||` cho kết quả kiểu `boolean`, đồng thời **short-circuit** khi kết quả đã xác định:

~~~java
int divisor = 0;
boolean safe = divisor != 0 && 10 / divisor > 1;

System.out.println(safe); // false, không chia cho 0
~~~

Nếu toán hạng đầu `divisor != 0` là false, Java **không đánh giá** phần `10 / divisor > 1`. Điều này cho thấy **có kiểu tĩnh** không đồng nghĩa mọi biểu thức con được thực thi trong tất cả các lượt chạy.

**Cú pháp `if` yêu cầu biểu thức điều kiện kiểu `boolean`** (hoặc `Boolean` được unbox thích hợp), không chấp nhận số nguyên như điều kiện:

~~~java
// if (1) { ... } // Lỗi compile: int không phải boolean
if (a > b) {
    System.out.println("a lớn hơn b");
}
~~~

## 8. Nối chuỗi cũng là biểu thức có kiểu String

Toán tử `+` vừa có thể cộng số vừa có thể nối String. Ngữ nghĩa phụ thuộc kiểu toán hạng và thứ tự đánh giá.

~~~java
int a = 7;
int b = 3;

System.out.println("result=" + a + b);   // result=73
System.out.println("result=" + (a + b)); // result=10
~~~

`+` kết hợp trái:

- `"result=" + a + b` bắt đầu từ String → nối String từng bước.
- `"result=" + (a + b)` thực hiện phép cộng số trong ngoặc trước, rồi nối kết quả 10.

Bảng đối chiếu:

| Biểu thức | Kiểu tĩnh | Giá trị |
|---|---|---|
| `7 + 3` | `int` | `10` |
| `"7" + 3` | `String` | `"73"` |
| `"result=" + 7 + 3` | `String` | `"result=73"` |
| `"result=" + (7 + 3)` | `String` | `"result=10"` |

Java **không tự phân tích chuỗi số** để biến `"7" + "3"` thành phép cộng 10. Muốn biến văn bản thành số phải sử dụng API như `Integer.parseInt` và xử lý dữ liệu sai định dạng.

## 9. Lời gọi method: kiểu biểu thức theo chữ ký trả về

~~~java
static int twice(int value) {
    return value * 2;
}

// Trong main:
int answer = twice(6);
System.out.println(answer); // 12
~~~

Biểu thức `twice(6)` có kiểu **`int`**, do method `twice` khai báo trả `int`. Compiler không cần chạy method để biết kiểu ấy.

Tương tự:

~~~java
var length = "Java".length(); // Suy ra int
var message = String.valueOf(123); // Suy ra String
~~~

Nếu method khai báo trả kiểu `Object`, thì **kiểu tĩnh của biểu thức gọi method là `Object`**, dù object trả về lúc chạy có thể là `String`:

~~~java
static Object makeText() {
    return "Java";
}

// Trong main:
Object value = makeText(); // Kiểu biểu thức makeText() là Object
System.out.println(value.toString()); // Java
// value.length(); // Lỗi compile: Object không khai báo length()
~~~

**Không dùng giá trị thực tế lúc chạy để đoán quyền gọi method tại compile time.** Kiểu tham chiếu tĩnh là hợp đồng mà compiler sử dụng.

## 10. Kiểu tĩnh của tham chiếu và class thật ở runtime

~~~java
class Animal {
    String sound() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }

    void fetch() {}
}
~~~

Trong một method:

~~~java
Animal pet = new Dog();

System.out.println(pet.sound()); // woof
// pet.fetch(); // Lỗi compile: kiểu tĩnh Animal không có fetch()
~~~

Giải thích:

- Biểu thức `new Dog()` có kiểu tĩnh `Dog` và tạo tham chiếu tới một instance `Dog`.
- Biến `pet` có kiểu khai báo **`Animal`**, nhận tham chiếu ấy qua widening reference conversion.
- Khi viết `pet.sound()`, compiler cho phép gọi vì `Animal` khai báo `sound()`; lúc chạy, **dynamic dispatch** chọn implementation override trong `Dog`.
- `pet.fetch()` không biên dịch vì kiểu tĩnh `Animal` không có method `fetch()`, dù object thật là Dog.

**Kiểu tĩnh** kiểm soát thành viên có thể truy cập; **class runtime** quyết định implementation của method instance được override.

## 11. Overload chọn theo kiểu tĩnh ở compile time

~~~java
static void describe(Object value) {
    System.out.println("Object overload");
}

static void describe(String value) {
    System.out.println("String overload");
}
~~~

Với:

~~~java
Object value = "Java";
String text = "Java";

describe(value); // Object overload
describe(text);  // String overload
~~~

Hai biến có thể trỏ **đến cùng một String object**, nhưng compiler chọn overload dựa trên **kiểu tĩnh của đối số**:

- `value` có kiểu `Object`: chọn `describe(Object)`.
- `text` có kiểu `String`: chọn `describe(String)`.

**Đừng nhầm overload resolution với override dispatch:**

| Cơ chế | Quyết định chính | Thời điểm |
|---|---|---|
| **Overload**: nhiều method cùng tên, tham số khác | Chữ ký áp dụng theo kiểu tĩnh đối số | Compile time |
| **Override**: class con định nghĩa lại method instance | Implementation theo object runtime | Runtime |

Kiểu của một biểu thức có thể được compiler quyết định sớm, nhưng điều đó không có nghĩa Java bỏ qua tính đa hình khi thực thi.

## 12. Biểu thức gán cũng có kiểu và giá trị

Phép gán `=` là một biểu thức: nó cập nhật biến và cho giá trị thuộc kiểu của biến bên trái.

~~~java
int count = 1;
int result = (count = 4) + 2;
System.out.println(count);  // 4
System.out.println(result); // 6
~~~

Tương tự, `++count` và `count++` có giá trị biểu thức lần lượt sau/trước khi tăng biến. Đây là các ví dụ cho thấy **kiểu tĩnh và giá trị** không mô tả hết hành vi lúc chạy: biểu thức còn có thể đổi trạng thái. Khi thao tác cập nhật không cần nằm trong phép tính, hãy tách ra thành câu lệnh riêng.

## 13. Biểu thức điều kiện `?:` có quy tắc xác định kiểu

~~~java
boolean enabled = true;
double selected = enabled ? 1 : 2.5;
System.out.println(selected); // 1.0
~~~

Nhánh được chọn quyết định **giá trị runtime**, còn trường hợp biểu thức điều kiện số học `int`/`double` này có kiểu `double` theo quy tắc numeric conditional expression. Không suy ra kiểu từ nhánh được chạy. Với biểu thức điều kiện tham chiếu, Java còn có các quy tắc target typing/poly expression; không có quy tắc chung “luôn chọn kiểu rộng nhất”.

## 14. Ép kiểu và phép chuyển đổi sau khi biết kiểu biểu thức

~~~java
double reading = 7.9;

int truncated = (int) reading; // Cast double -> int
System.out.println(truncated); // 7
~~~

Biểu thức `(int) reading` có kiểu `int`, khác với `reading` có kiểu `double`. Cast yêu cầu chuyển đổi hợp lệ; với giá trị hữu hạn trong miền, chuyển từ double sang int **cắt phần lẻ theo hướng về 0**, không làm tròn gần nhất.

Một tình huống khác:

~~~java
int value = 130;
byte small = (byte) value;
System.out.println(small); // -126
~~~

Kết quả `(byte) value` có kiểu `byte` nhưng không giữ nguyên giá trị 130, vì thu hẹp số nguyên có thể làm mất dữ liệu.

**Phân biệt ba thứ:**

- **Type checking:** compiler xác định và kiểm tra loại giá trị có thể sử dụng.
- **Conversion:** Java có thể biến đổi biểu diễn/giá trị để phù hợp kiểu đích.
- **Business validation:** chương trình phải tự kiểm tra kết quả có phù hợp yêu cầu hay không.

`(int) reading` đúng cú pháp không bảo đảm thao tác này đúng với số tiền, số lượng hoặc phép đo đòi hỏi phần lẻ.

## 15. `var` quan sát được kiểu compile time từ initializer

~~~java
var count = 10;           // int
var title = "Java";       // String
var average = 10 / 4;     // int: giá trị 2
var preciseAverage = 10.0 / 4; // double: giá trị 2.5
~~~

`var` **không tạo biến kiểu động**: nó suy luận kiểu tĩnh của biểu thức khởi tạo.

~~~java
var count = 10;
// count = "ten"; // Lỗi biên dịch: count đã có kiểu int
~~~

Một điểm nên nhớ:

~~~java
// var unknown = null; // Không hợp lệ: null literal không cung cấp kiểu suy luận
String knownType = null;  // Hợp lệ: kiểu được khai báo tường minh
~~~

Java có khái niệm kiểu của `null` literal và các ngữ cảnh target typing; nhưng bản thân `var unknown = null` không có đủ thông tin cho một kiểu biến cục bộ có thể suy luận hợp lệ.

Với generic:

~~~java
var names = java.util.List.of("Lan", "An"); // List<String>
System.out.println(names.get(0).length()); // 3
// names.add(123); // Lỗi compile: Integer không phải String
~~~

Không nhầm **kiểm tra kiểu tĩnh** với **khả năng thay đổi collection tại runtime**. `List.of` tạo danh sách không sửa được; thử thêm phần tử hợp kiểu String vẫn có thể ném `UnsupportedOperationException` lúc chạy.

## 16. Khi có kiểu nhưng không có giá trị dùng được

Lời gọi method khai báo `void` có thể hoàn tất bình thường nhưng không cho giá trị để gán:

~~~java
System.out.println("Hello"); // Hợp lệ như một statement expression
// int n = System.out.println("Hello"); // Sai kiểu: lời gọi trả void
~~~

Một biểu thức kiểu `int` cũng có thể **không trả được kết quả runtime** nếu ném ngoại lệ, chẳng hạn `10 / denominator` với `denominator == 0`. Kiểu được compiler kiểm tra, còn thành công hoặc thất bại xảy ra khi đánh giá; những side effect trước lỗi không tự động được hoàn tác.

## 17. Ví dụ Java 17 đầy đủ, chạy được

Tạo file chính xác **`ExpressionValueTypeDemo.java`**:

~~~java
public final class ExpressionValueTypeDemo {
    private ExpressionValueTypeDemo() {}

    static class Animal {
        String sound() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String sound() {
            return "woof";
        }

        void fetch() {
            System.out.println("fetch");
        }
    }

    static int twice(int value) {
        return value * 2;
    }

    static void describe(Object value) {
        System.out.println("overload=Object");
    }

    static void describe(String value) {
        System.out.println("overload=String");
    }

    public static void main(String[] args) {
        int a = 7;
        int b = 3;
        int sum = a + b;
        boolean greater = a > b;
        System.out.println("sum=" + sum);
        System.out.println("greater=" + greater);

        int whole = a / 2;
        double widenedAfter = a / 2;
        double fractional = (double) a / 2;
        System.out.println("int division=" + whole);
        System.out.println("widen after division=" + widenedAfter);
        System.out.println("double division=" + fractional);

        byte small = 10;
        int promoted = small + 1;
        System.out.println("promoted byte expression=" + promoted);
        System.out.println("mixed expression=" + (a + 0.5));

        System.out.println("concat=" + a + b);
        System.out.println("grouped=" + (a + b));

        int assigned = 1;
        int assignmentResult = (assigned = 4) + 2;
        System.out.println("assignment target=" + assigned);
        System.out.println("assignment result=" + assignmentResult);
        int before = ++assigned;
        int after = assigned++;
        System.out.println("prefix value=" + before);
        System.out.println("postfix value=" + after);
        System.out.println("after increment=" + assigned);

        boolean chooseFirst = true;
        double selected = chooseFirst ? 1 : 2.5;
        System.out.println("conditional selected=" + selected);

        int methodResult = twice(6);
        System.out.println("method expression=" + methodResult);

        Object object = "Java";
        String text = "Java";
        describe(object);
        describe(text);
        System.out.println("object toString=" + object.toString());
        System.out.println("text length=" + text.length());

        Animal pet = new Dog();
        System.out.println("virtual sound=" + pet.sound());

        int[] numbers = {2, 4};
        System.out.println("array element=" + numbers[1]);

        var inferred = "Hi".length();
        System.out.println("var inferred int=" + inferred);

        Integer boxed = 10;
        int unboxedSum = boxed + 2;
        System.out.println("wrapper arithmetic=" + unboxedSum);

        int divisor = 0;
        boolean guarded = divisor != 0 && 10 / divisor > 1;
        System.out.println("short circuit=" + guarded);

        long overflowFirst = 2_000_000_000 + 2_000_000_000;
        long longFirst = 2_000_000_000L + 2_000_000_000;
        System.out.println("overflow first=" + overflowFirst);
        System.out.println("long first=" + longFirst);

        System.out.println("void call completed");
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên. Mở terminal trong thư mục chứa `ExpressionValueTypeDemo.java`. Không cần Maven, Gradle hoặc thư viện ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ExpressionValueTypeDemo.java
java -cp . ExpressionValueTypeDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ExpressionValueTypeDemo.java
java -cp . ExpressionValueTypeDemo
~~~

**Exact expected output:**

~~~text
sum=10
greater=true
int division=3
widen after division=3.0
double division=3.5
promoted byte expression=11
mixed expression=7.5
concat=73
grouped=10
assignment target=4
assignment result=6
prefix value=5
postfix value=5
after increment=6
conditional selected=1.0
method expression=12
overload=Object
overload=String
object toString=Java
text length=4
virtual sound=woof
array element=4
var inferred int=2
wrapper arithmetic=12
short circuit=false
overflow first=-294967296
long first=4000000000
void call completed
~~~

### Kiểm tra từng nhóm kết quả

- `sum`, `greater`: biểu thức số học tạo `int`, biểu thức so sánh tạo `boolean`.
- Ba dòng phép chia: cùng các giá trị liên quan nhưng **kiểu biểu thức tại lúc chia** quyết định giữ hay bỏ phần lẻ.
- `small + 1`: toán hạng `byte` được nâng thành `int`.
- `concat=73` so với `grouped=10`: kiểu toán hạng String đổi ý nghĩa phép `+`.
- `(assigned = 4) + 2`: phép gán là expression có giá trị; prefix/postfix có thời điểm cập nhật khác nhau.
- `conditional selected=1.0`: biểu thức `?:` số học có kiểu `double`.
- `describe(object)` và `describe(text)`: overload chọn theo **kiểu tĩnh**.
- `pet.sound()`: method override thực thi theo **object Dog** tại runtime.
- `var inferred int=2`: `var` suy ra kiểu `int` từ return type `length()`.
- `short circuit=false`: nhánh chia cho 0 không bị đánh giá.
- Hai dòng overflow: toán tử cộng có kiểu `int` hoặc `long` trước khi gán vào biến `long`.

## 18. Lỗi thường gặp và cách sửa

| Ngộ nhận / lỗi | Nguyên nhân | Cách đúng |
|---|---|---|
| `2 + 3;` là câu lệnh hợp lệ độc lập | Không phải mọi expression là statement expression | Gán, sử dụng kết quả hoặc đặt trong ngữ cảnh phù hợp |
| `double avg = 7 / 2;` cho 3.5 | Phép chia `int / int` trả `int` | `(double) 7 / 2` |
| `byte result = byteA + byteB;` | Numeric promotion trả `int` | Dùng `int` hoặc cast có kiểm tra |
| `long total = intA + intB;` luôn tránh tràn | int cộng trước khi gán | Widen toán hạng trước phép cộng |
| `"sum=" + 7 + 3` cho `sum=10` | Nối String từ trái sang phải | `"sum=" + (7 + 3)` |
| `Object x = "Java"; x.length()` | Kiểu tĩnh Object không có length | Chọn String ở khai báo hoặc cast có kiểm tra |
| `var n = 1;` tự đổi thành long khi cần | `var` suy ra int cố định | Khởi tạo bằng `1L` hoặc khai báo long |
| `Integer i = null; int x = i + 1;` | Unboxing null ở runtime | Kiểm tra null trước |
| `if (10)` hợp lệ vì số khác 0 | Java yêu cầu boolean | Viết điều kiện như `10 != 0` |
| `int n = System.out.println("x");` | Method có return type void, không trả giá trị | Gọi làm câu lệnh riêng |
| `n = 0; 10 / n` được compiler chặn | Kiểu hợp lệ nhưng giá trị runtime sai | Kiểm tra mẫu số khác 0 |
| Nghĩ class runtime quyết định overload | Overload phân giải theo kiểu tĩnh | Đọc kiểu khai báo biểu thức đối số |
| Nghĩ kiểu tĩnh ngăn method override | Method instance có dispatch động | Tách overload và override |

**Mẹo debug:** khi một biểu thức cho kết quả không như dự đoán, hãy phân tích theo thứ tự **(1) kiểu từng toán hạng → (2) quy tắc chuyển kiểu/toán tử → (3) kiểu biểu thức → (4) giá trị lúc chạy → (5) chuyển đổi khi gán**.

## 19. Bài tập có đáp án

### Bài A — phép chia và kiểu biểu thức

~~~java
int a = 9;
int b = 4;
double x = a / b;
double y = (double) a / b;
System.out.println(x);
System.out.println(y);
~~~

**Đáp án:**

~~~text
2.0
2.25
~~~

Phép `a / b` có kiểu `int`; cast toán hạng đầu trước khi chia làm biểu thức `double`.

### Bài B — numeric promotion

~~~java
byte value = 12;
var result = value + 1;
System.out.println(result);
~~~

**Đáp án:** in `13`, biến `result` có kiểu **int**, không phải byte.

### Bài C — toán tử `+` và String

~~~java
System.out.println("value=" + 2 + 3);
System.out.println("value=" + (2 + 3));
~~~

**Đáp án:**

~~~text
value=23
value=5
~~~

### Bài D — kiểu tĩnh và overload

~~~java
static void show(Object value) { System.out.println("Object"); }
static void show(String value) { System.out.println("String"); }

// Trong main:
Object a = "X";
String b = "X";
show(a);
show(b);
~~~

**Đáp án:**

~~~text
Object
String
~~~

### Bài E — biểu thức gán có giá trị

~~~java
int n = 1;
int x = (n = 5) * 2;
System.out.println(n);
System.out.println(x);
~~~

**Đáp án:**

~~~text
5
10
~~~

### Bài F — khi expression có kiểu nhưng không có giá trị dùng được

Tại sao dòng này lỗi?

~~~java
// int n = System.out.println("Hello");
~~~

**Đáp án:** `println` có kiểu trả về `void`; lời gọi có thể dùng làm statement expression nhưng **không tạo giá trị `int` để gán**.

## 20. Checklist cuối bài

- [ ] Phân biệt biểu thức và câu lệnh Java.
- [ ] Biết kiểu của biểu thức được compiler xác định từ toán hạng, toán tử và chữ ký API.
- [ ] Hiểu giá trị runtime có thể thay đổi dù kiểu tĩnh vẫn cố định.
- [ ] Nhận biết literal `int`, `long`, `double`, `float`, `char`, `boolean`, `String`.
- [ ] Không nhầm kiểu biến nhận với kiểu của phép tính trung gian.
- [ ] Hiểu numeric promotion và integer division.
- [ ] Biết biểu thức so sánh/logic có kiểu boolean; `&&`/`||` short-circuit.
- [ ] Phân biệt phép cộng số và phép nối String.
- [ ] Biết method invocation có kiểu theo chữ ký trả về; `void` không cung cấp giá trị gán được.
- [ ] Phân biệt static type của tham chiếu với runtime class của object.
- [ ] Hiểu overload compile-time và override runtime.
- [ ] Biết phép gán, `++`, `--` có kết quả expression và tác dụng phụ.
- [ ] Hiểu biểu thức điều kiện `?:` có kiểu theo các quy tắc ngôn ngữ.
- [ ] Biết `var` suy luận kiểu tĩnh từ initializer.
- [ ] Nhớ compiler chặn sai kiểu nhưng không đảm bảo không có exception/overflow.
- [ ] Biên dịch và chạy `ExpressionValueTypeDemo.java`, đối chiếu từng dòng exact expected output.

**Kết luận:** Biểu thức Java không chỉ “làm ra một kết quả”: Java gán cho chúng **kiểu tĩnh tại compile time**, từ đó kiểm tra toán tử, phép gán, lời gọi method và truy cập thành viên. Giá trị thực tế được tính khi chạy và có thể phụ thuộc dữ liệu, nhánh đánh giá hoặc object runtime. Hiểu hai lớp **kiểu tĩnh** và **giá trị runtime** là nền tảng để đọc, dự đoán và sửa lỗi biểu thức Java 17+.