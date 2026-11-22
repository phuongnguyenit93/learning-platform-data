# `boolean` chỉ có `true` và `false` trong Java

> **Java core — language-basics / Kiểu nguyên thủy**  
> **Môi trường:** JDK 17 trở lên, không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu hai giá trị của `boolean` nguyên thủy, cách tạo biểu thức điều kiện, toán tử logic và *short-circuit*; phân biệt `boolean` với `Boolean` có thể là `null`.

## 1. Kiểu `boolean` biểu diễn điều kiện đúng hoặc sai

Trong Java, `boolean` là **kiểu nguyên thủy** (*primitive type*) chỉ có **hai giá trị hợp lệ**:

- `true`: đúng.
- `false`: sai.

~~~java
boolean isReady = true;
boolean isClosed = false;
isReady = false; // Hợp lệ: giá trị mới vẫn là boolean.
~~~

Hai từ `true` và `false` là **boolean literal** trong mã nguồn Java. Chúng không phải chuỗi `"true"`/`"false"`, và Java **không** coi số `1` là đúng hay số `0` là sai.

~~~java
// Các dòng cố ý SAI, không đưa vào chương trình chạy:
// boolean ok = 1;       // int không gán được cho boolean.
// boolean no = 0;       // int không được ngầm chuyển thành boolean.
// boolean text = "true"; // String khác boolean.
// boolean missing = null; // primitive boolean không nhận null.
~~~

Một biến kiểu `boolean` không thể giữ giá trị thứ ba như “chưa biết”. Khi cần trạng thái chưa xác định, hãy dùng kiểu tham chiếu `Boolean` có khả năng chứa `null` và xử lý riêng trạng thái đó.

## 2. Biểu thức trả về `boolean`

Kết quả so sánh và phép logic thường có kiểu `boolean`:

~~~java
int age = 20;
boolean adult = age >= 18;       // true
boolean exactly20 = age == 20;  // true
boolean notAdult = !adult;      // false
boolean eligible = adult && exactly20; // true
~~~

Những phép toán thường dùng:

| Nhóm | Toán tử | Ví dụ và kết quả |
| --- | --- | --- |
| Phủ định | `!` | `!true` → `false` |
| VÀ ngắn mạch | `&&` | `true && false` → `false` |
| HOẶC ngắn mạch | `\|\|` | `true \|\| false` → `true` |
| XOR logic | `^` | `true ^ false` → `true` |
| So sánh bằng/khác | `==`, `!=` | `true == false` → `false` |
| So sánh số | `<`, `<=`, `>`, `>=` | `5 > 3` → `true` |

Bảng chân trị đơn giản:

| `a` | `b` | `a && b` | `a \|\| b` | `a ^ b` |
| --- | --- | --- | --- | --- |
| false | false | false | false | false |
| false | true | false | true | true |
| true | false | false | true | true |
| true | true | true | true | false |

Các phép `&&`, `||`, `!` cần toán hạng phù hợp với ngữ cảnh boolean. Java không cho cộng hai giá trị boolean hoặc dùng toán tử `<`/`>` để so thứ tự `true` và `false`.

## 3. Điều kiện `if`, `while` phải là boolean

Java yêu cầu **biểu thức điều kiện** thực sự có kiểu `boolean` (hoặc `Boolean` có thể unbox thành boolean):

~~~java
int quantity = 3;

if (quantity > 0) {
    System.out.println("Co hang");
}
~~~

Đầu ra là `Co hang`. Không viết `if (quantity)` như trong các ngôn ngữ coi mọi số khác 0 là đúng:

~~~java
// if (quantity) { } // Sai: quantity là int, không phải boolean.
// if (1) { }        // Sai: literal số 1 không phải điều kiện boolean.
~~~

**Mẹo dễ đọc:** Khi biến `active` đã là `boolean`, dùng `if (active)` hoặc `if (!active)` thường rõ hơn `if (active == true)` hay `if (active == false)`.

## 4. `&&`/`||` ngắn mạch; `&`/`|` không ngắn mạch

Với `a && b`, nếu `a` là `false` thì Java **không đánh giá `b`**: kết quả đã chắc chắn false. Với `a || b`, nếu `a` là `true` thì Java **không đánh giá `b`**: kết quả đã chắc chắn true. Đó là *short-circuit*.

Ngược lại, khi toán hạng là boolean, `&` và `|` **đánh giá cả hai vế**. `^` cũng không ngắn mạch. Khác biệt này đặc biệt quan trọng nếu vế phải gọi method có tác dụng phụ hoặc có thể gây exception.

Ví dụ an toàn khi tham chiếu có thể `null`:

~~~java
String name = null;
boolean nonEmpty = name != null && !name.isEmpty();
System.out.println(nonEmpty); // false, không gọi name.isEmpty().
~~~

Không thay `&&` bằng `&` trong trường hợp đó: vế phải có thể vẫn được đánh giá và gây `NullPointerException`.

## 5. Chương trình Java 17+ runnable

Tạo tệp **BooleanDemo.java**:

~~~java
public final class BooleanDemo {
    private static boolean sharedFlag;
    private static int checks;

    private static boolean probe() {
        checks++;
        return true;
    }

    public static void main(String[] args) {
        boolean enabled = true;
        boolean blocked = false;
        boolean allowed = enabled && !blocked;

        System.out.println("allowed=" + allowed);
        System.out.println("notAllowed=" + !allowed);
        System.out.println("comparison=" + (5 > 3));

        if (allowed) {
            System.out.println("branch=entered");
        }

        boolean skipAnd = false && probe();
        boolean skipOr = true || probe();
        System.out.println("shortCircuit=" + skipAnd + ","
                + skipOr + ",checks=" + checks);

        boolean eagerAnd = false & probe();
        System.out.println("eagerAnd=" + eagerAnd + ",checks=" + checks);
        System.out.println("xor=" + (true ^ false));

        boolean[] flags = new boolean[2];
        System.out.println("fieldDefault=" + sharedFlag);
        System.out.println("arrayDefault=" + flags[0]);

        Boolean unknown = null;
        System.out.println("wrapperNull=" + (unknown == null));
        System.out.println("parseTrue=" + Boolean.parseBoolean("TrUe"));
        System.out.println("parseOne=" + Boolean.parseBoolean("1"));
    }
}
~~~

Chạy từ thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 BooleanDemo.java
java BooleanDemo
~~~

**Expected output chính xác:**

~~~text
allowed=true
notAllowed=false
comparison=true
branch=entered
shortCircuit=false,true,checks=0
eagerAnd=false,checks=1
xor=true
fieldDefault=false
arrayDefault=false
wrapperNull=true
parseTrue=true
parseOne=false
~~~

Giải thích: `enabled && !blocked` cho true. Hai lời gọi `probe()` ở biểu thức `false && ...` và `true || ...` đều bị bỏ qua nên `checks` vẫn là 0; `false & probe()` **vẫn gọi `probe()`**, làm `checks` thành 1 dù kết quả AND là false. Mảng và field `boolean` mới được khởi tạo mặc định bằng false. `Boolean.parseBoolean("TrUe")` nhận chuỗi không phân biệt hoa/thường; chuỗi `"1"` **không** được hiểu là true.

## 6. `boolean` khác `Boolean` ở chỗ nào?

| Tiêu chí | `boolean` | `Boolean` |
| --- | --- | --- |
| Bản chất | Kiểu nguyên thủy | Lớp wrapper tham chiếu |
| Giá trị của biến đã gán | `true` hoặc `false` | `Boolean.TRUE`, `Boolean.FALSE` hoặc `null` |
| Field chưa khởi tạo tường minh | `false` | `null` |
| Phần tử của mảng mới | `false` trong `boolean[]` | `null` trong `Boolean[]` |
| Dùng làm điều kiện | Trực tiếp | Java unbox về `boolean`; nếu `null` có thể ném `NullPointerException` |

Không nhầm “field có mặc định” với **biến cục bộ chưa gán**. Chẳng hạn, `boolean ready; System.out.println(ready);` trong method không hợp lệ vì `ready` chưa được *definitely assigned*. Nếu biến cục bộ đã gán, nó vẫn chỉ giữ true/false.

Với dữ liệu nhập dạng chuỗi, `Boolean.parseBoolean(text)` chỉ cho true khi `text` bằng `"true"` (không phân biệt hoa/thường); những chuỗi khác, kể cả `"1"`, `"yes"` hoặc `null`, cho false. Nếu cần báo lỗi khi dữ liệu không hợp lệ, hãy **tự kiểm tra đầu vào** thay vì coi mọi giá trị parse ra false đều là người dùng chọn false.

## 7. Lỗi phổ biến và bài tập

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| `boolean b = 1;` | Java không ngầm quy đổi số thành boolean |
| `if (number)` với `number` kiểu `int` | Phải viết một biểu thức boolean, ví dụ `number != 0` |
| `boolean b = "false";` | Chuỗi khác với literal `false` |
| `Boolean b = null; if (b) { ... }` | Tự unbox `null` có thể ném `NullPointerException` |
| Thay `&&` bằng `&` khi cần bảo vệ null | `&` vẫn đánh giá vế phải |
| Nhầm `Boolean.parseBoolean("yes")` với true | Kết quả là false |

**Bài tập 1.** Dự đoán `!false`, `true && false`, `true || false` và `true ^ true`. Giải thích qua bảng chân trị.

**Bài tập 2.** Tạo biến `int amount = 0;` và một biến `boolean hasAmount = amount > 0;`. Thử đưa trực tiếp `amount` vào điều kiện `if` để xem lỗi compile.

**Bài tập 3.** Trong `BooleanDemo.java` đổi `false && probe()` thành `true && probe()`, rồi dự đoán `checks` ngay sau hai biểu thức short-circuit và sau biểu thức `&`.

**Bài tập 4.** Viết kiểm tra `String value = null;` bằng `value != null && !value.isBlank()`. Dự đoán điều gì xảy ra nếu dùng `&` thay cho `&&`.

**Bài tập 5.** Tạo `Boolean unknown = null;` rồi thử `Boolean.TRUE.equals(unknown)` để so sánh an toàn mà không unbox một giá trị null.

### Ghi nhớ

**`boolean` chỉ có `true` và `false`; Java không có quy tắc “số 0 là false, số khác 0 là true”.** Phép so sánh sinh boolean, `if`/`while` cần điều kiện boolean, `&&`/`||` có short-circuit. `Boolean` là **wrapper tham chiếu** có thể mang `null`, vì vậy đừng đồng nhất nó với primitive `boolean`.
