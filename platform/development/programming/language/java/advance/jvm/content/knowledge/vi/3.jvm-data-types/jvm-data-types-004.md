# Giá trị null, kiểu lớp, kiểu giao diện và kiểu mảng trong JVM

## 1. Mục tiêu: hiểu đúng các giá trị tham chiếu

Trong JVM, kiểu dữ liệu phục vụ việc biểu diễn giá trị, kiểm tra tính hợp lệ của bytecode và thực thi chương trình. Một phân biệt nền tảng là **giá trị nguyên thủy** (*primitive value*) và **giá trị tham chiếu** (*reference value*).

Ví dụ:

```java
int count = 3;                 // giá trị primitive int
String title = "JVM";          // biến có kiểu tham chiếu tới String
Runnable task = () -> {};     // tham chiếu qua kiểu giao diện
int[] numbers = {1, 2, 3};    // mảng cũng là đối tượng và giá trị biến là tham chiếu
String missing = null;        // giá trị tham chiếu null đặc biệt
```

Trong **đặc tả JVM (JVMS §2.4)**, ba nhóm kiểu tham chiếu (*reference types*) là:

1. **Kiểu lớp (*class types*)**: mô tả các đối tượng thuộc một lớp, chẳng hạn `java.lang.String`.
2. **Kiểu giao diện (*interface types*)**: cho phép tham chiếu đối tượng có lớp hiện thực giao diện, chẳng hạn `java.lang.Runnable`.
3. **Kiểu mảng (*array types*)**: mô tả đối tượng mảng, chẳng hạn `int[]` hoặc `String[][]`.

Giá trị tham chiếu có thể là tham chiếu tới một đối tượng tương ứng hoặc **giá trị đặc biệt `null`**. JVM không thêm “kiểu JVM thứ tư mang tên null” vào ba nhóm trên. Ở cấp **ngôn ngữ Java**, đặc tả JLS nói đến một **null type** đặc biệt dành cho biểu thức `null`; kiểu này không có tên để viết khai báo biến và cần phân biệt với phân loại reference types trong JVMS.

Mục tiêu sau bài học: giải thích đối tượng nào có thể được giữ trong biến lớp/giao diện/mảng, vì sao `null` hợp lệ ở các vị trí tham chiếu, bytecode nào liên quan, khi nào xuất hiện `NullPointerException`, `ClassCastException`, `ArrayStoreException` và vì sao `int[]` là kiểu tham chiếu dù phần tử của nó là `int`.

## 2. Từ kiểu nguồn Java tới giá trị mà JVM thao tác

Xét:

```java
String message = "hello";
Object any = message;
CharSequence readable = message;
```

Đối tượng chuỗi được tạo/quản lý trong runtime; ba biến có thể cùng tham chiếu đến **một đối tượng** dù kiểu khai báo khác nhau. Một biến kiểu tham chiếu **không chứa bản sao toàn bộ đối tượng**. Khi gán `any = message`, chương trình sao chép *giá trị tham chiếu* theo mô hình ngôn ngữ, không tự sao chép nội dung chuỗi.

Từ “tham chiếu” không đồng nghĩa với “địa chỉ bộ nhớ thô mà lập trình viên có thể đọc ra và tính toán”. Đặc tả JVM không buộc mọi triển khai biểu diễn reference bằng cùng một dạng con trỏ vật lý. Các trình biên dịch/runtime còn có thể tối ưu nội bộ, nhưng ngữ nghĩa quan sát được phải tuân thủ hợp đồng Java.

### Kiểu khai báo và kiểu thực tế khác nhau

```java
Object value = "Java";
```

- **Kiểu tĩnh** của biến `value` là `Object`; compiler kiểm tra các thao tác được phép trên biến này dựa vào kiểu tĩnh.
- **Kiểu runtime** của đối tượng đang được tham chiếu là `String`.
- Có thể kiểm tra runtime bằng `value instanceof String` hoặc `value.getClass()` nếu tham chiếu khác `null`.
- Nếu gán `value = null`, không có đối tượng nào đứng sau tham chiếu đó để hỏi `getClass()`.

Phân biệt này giải thích vì sao cùng một đối tượng có thể được xem qua kiểu lớp cha, giao diện hoặc kiểu `Object`, nhưng phép ép kiểu sai chỉ phát hiện ở runtime.

### Đối tượng nằm ở đâu?

Trong mô hình JVM, đối tượng và mảng được cấp phát trên **heap**. Những vị trí chứa giá trị tham chiếu có thể là biến cục bộ của frame, trường đối tượng, trường `static` hoặc phần tử của mảng tham chiếu. Cách bố trí máy thật, tối ưu và tổ chức bộ nhớ cụ thể phụ thuộc bản triển khai JVM.

Sơ đồ khái niệm:

```text
Biến cục bộ              Heap (khái niệm)
-------------------      -----------------------
String a -----------+---> đối tượng String "JVM"
Object b -----------+
String c = null ----X     (không có đối tượng cho c)
```

Gán một biến bằng `null` chỉ thay đổi tham chiếu ở vị trí đó. Nó **không trực tiếp hủy** đối tượng đã từng được tham chiếu; đối tượng có thể còn được tham chiếu từ nơi khác, và tính có thể thu hồi do cơ chế reachability/garbage collection quyết định.

## 3. Giá trị `null`: có thể xuất hiện ở đâu và ý nghĩa ra sao?

### 3.1. `null` không phải số không, chuỗi rỗng hay đối tượng `Null`

`null` biểu thị **không có đối tượng/mảng đang được tham chiếu** tại vị trí đó. Nó khác hẳn:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `null` | Không tham chiếu tới đối tượng |
| `0` | Giá trị số nguyên bằng không |
| `""` | Tham chiếu tới đối tượng `String` có độ dài 0 |
| `new int[0]` | Tham chiếu tới mảng `int` hợp lệ với `length == 0` |
| `new Object()` | Tham chiếu tới một đối tượng vừa tạo |

Một mảng dài 0 vẫn là **một đối tượng mảng có thật**, có kiểu runtime và có thể gọi `getClass()`. `null` thì không thể truy cập thành viên hay hỏi lớp runtime.

### 3.2. `null` tương thích với vị trí có kiểu tham chiếu

```java
String text = null;
Runnable runnable = null;
Object object = null;
String[] strings = null;
int[] integers = null;
```

Các khai báo trên hợp lệ. `int[]` là **kiểu mảng/tham chiếu**, còn `int` là primitive; vì thế `int[] a = null` hợp lệ nhưng `int x = null` là lỗi biên dịch.

Chú ý khác biệt giữa `null` và mảng có phần tử mang giá trị mặc định:

```java
String[] names = new String[2];
System.out.println(names == null); // false
System.out.println(names[0]);      // null
```

Biến `names` chứa tham chiếu tới **một mảng có thật**. Hai slot của mảng `String[]` ban đầu chứa **null reference**.

### 3.3. Giá trị mặc định và definite assignment

Các **trường đối tượng**, **trường static** và **phần tử mảng kiểu tham chiếu** được khởi tạo mặc định bằng `null` khi đối tượng/lớp/mảng được khởi tạo theo quy tắc tương ứng. Ví dụ:

```java
class Account {
    String owner;             // giá trị mặc định null
    static Object cache;      // giá trị mặc định null
}
```

Ngược lại, biến cục bộ phải được gán chắc chắn trước khi đọc, theo quy tắc *definite assignment* của trình biên dịch Java:

```java
// Minh họa lỗi biên dịch (không phải chương trình độc lập):
String unassigned;
// System.out.println(unassigned); // lỗi: variable might not have been initialized
```

Không nên suy luận rằng “biến cục bộ kiểu tham chiếu luôn mặc định bằng `null`”; ràng buộc ở ngôn ngữ Java ngăn đọc biến chưa được gán trong tình huống trên. Ngoài ra, `var x = null;` không đủ thông tin để suy luận một kiểu biến cục bộ hợp lệ; muốn chủ động cho phép null, hãy khai báo kiểu rõ ràng.

### 3.4. `null`, phép so sánh và `instanceof`

```java
Object a = null;
Object b = null;
System.out.println(a == b);           // true
System.out.println(a instanceof Object); // false
```

Toán tử `==` trên hai giá trị tham chiếu so sánh chúng có cùng tham chiếu hay không (hoặc cùng là `null`). `null instanceof BấtKỳKiểuThamChiếuPhùHợp` luôn **false**: không có đối tượng để kiểm tra kiểu runtime.

Phép ép kiểu tham chiếu của `null` hợp lệ và trả lại `null`:

```java
String name = (String) null;
System.out.println(name == null); // true
```

Điều này khác với ép kiểu một đối tượng **không phải null** sang kiểu không tương thích, có thể ném `ClassCastException`.

### 3.5. Dereference của `null`

Các thao tác cần đối tượng thật sẽ thất bại nếu đối tượng đích là `null`. Ví dụ:

```java
String s = null;
// s.length(); // NullPointerException tại runtime
```

Những tình huống điển hình:

- Gọi phương thức instance hoặc truy cập trường instance qua tham chiếu null.
- Đọc/ghi phần tử mảng null và đọc `array.length` qua mảng null.
- Thực hiện unboxing trên wrapper có giá trị null, ví dụ `Integer boxed = null; int n = boxed;`.
- Một số thao tác khác yêu cầu tham chiếu khác null.

**Không phải mọi thao tác liên quan `null` đều lỗi.** Gán `null`, so sánh `== null`, `instanceof` và ép kiểu tham chiếu đối với `null` có ngữ nghĩa hợp lệ. Cần phân biệt kiểm tra/di chuyển một reference với thao tác thực sự cần đối tượng.

### 3.6. `null` trong overload và thiết kế API

Hai overload không liên quan nhau về độ đặc hiệu có thể khiến lời gọi với `null` trở nên **mơ hồ lúc biên dịch**:

```java
// Minh họa cấu trúc: không dùng như chương trình độc lập.
void select(String value) {}
void select(Integer value) {}

// select(null); // lỗi biên dịch: reference to select is ambiguous
select((String) null); // chọn overload nhận String
```

Đây là vấn đề **chọn phương thức lúc compile-time** dựa trên kiểu của biểu thức, không phải `NullPointerException`.

Khi một API yêu cầu giá trị không null, nên ghi rõ hợp đồng và kiểm tra ở ranh giới phù hợp:

```java
import java.util.Objects;

static String normalize(String input) {
    Objects.requireNonNull(input, "input");
    return input.trim();
}
```

Đoạn trên là **mã minh họa phương thức**, không phải một chương trình độc lập. `requireNonNull` ném `NullPointerException` có thông điệp xác định nếu caller truyền null; đây là lỗi chủ động, dễ xác định nguyên nhân hơn so với dereference sâu trong chương trình.

## 4. Kiểu lớp (*class type*)

### 4.1. Biến kiểu lớp tham chiếu tới một instance tương thích

Khi khai báo:

```java
Number number = Integer.valueOf(42);
Object object = number;
```

`Number` và `Object` đều là kiểu lớp. Đối tượng runtime là instance của `Integer`, vốn là lớp con của `Number` và `Object`. Các phép gán từ kiểu cụ thể hơn sang kiểu cha được phép khi có quan hệ kiểu phù hợp (*widening reference conversion*).

Kiểu lớp không nhất thiết là lớp cụ thể có thể dùng trực tiếp với `new`:

- Một lớp **trừu tượng** như `Number` vẫn là một kiểu lớp hợp lệ cho biến, tham số và kiểu trả về.
- Không thể `new Number()` vì đó là lớp abstract.
- Giá trị vẫn có thể đến từ đối tượng của lớp con cụ thể, chẳng hạn `Integer`.

**Lớp vs. giá trị tham chiếu:** kiểu `String` mô tả nhóm đối tượng phù hợp; biến `String s` chỉ chứa một giá trị tham chiếu tại một thời điểm, có thể là `null`.

### 4.2. Lớp khai báo và lớp runtime quyết định điều gì?

```java
Object value = "hello";
```

Compiler chỉ cho phép gọi trực tiếp phương thức được biết qua kiểu tĩnh `Object` (trừ khi có ép kiểu hoặc cơ chế ngôn ngữ khác). Ví dụ `value.toString()` hợp lệ còn `value.length()` không hợp lệ khi chưa kiểm tra và chuyển kiểu.

Dùng pattern matching cho `instanceof` (hợp lệ từ Java 17):

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Điều kiện true vì runtime object là `String`; biến `text` được compiler kiểm tra là kiểu `String` trong phạm vi nhánh tương ứng. Nếu `value == null`, điều kiện false.

Ép kiểu tham chiếu:

```java
Object value = "hello";
String ok = (String) value;         // hợp lệ ở runtime
// Integer bad = (Integer) value;  // ClassCastException ở runtime
```

Dòng gây lỗi đã được chú thích để ví dụ còn lại hợp lệ. Nếu runtime phát hiện đối tượng không tương thích với target class/interface, thao tác cast sẽ thất bại.

### 4.3. `java.lang.Object` trong hệ phân cấp

`Object` là lớp cha gốc của các lớp Java thông thường và là kiểu có thể chứa tham chiếu tới các đối tượng Java, bao gồm đối tượng mảng:

```java
Object object = new Object();
Object text = "a";
Object array = new int[3];
```

Nhưng không được đồng nhất primitive với reference: `int` là primitive, còn `Integer` là class wrapper. `Object boxed = 5;` hợp lệ nhờ **autoboxing** từ `int` thành đối tượng wrapper tương ứng; không có nghĩa `int` tự biến thành một loại class JVM.

## 5. Kiểu giao diện (*interface type*)

### 5.1. Biến giao diện chứa tham chiếu tới đối tượng hiện thực hợp đồng

Một interface định nghĩa hợp đồng mà lớp có thể hiện thực. Ví dụ:

```java
interface Named {
    String name();
}

final class Person implements Named {
    private final String value;

    Person(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }
}
```

Các đoạn khai báo trên là **mã minh họa nhiều kiểu top-level**, cần đặt vào các tệp Java phù hợp khi dùng trong dự án thật. Có thể dùng:

```java
Named named = new Person("Lan");
System.out.println(named.name()); // Lan
```

`Named` là **kiểu khai báo** của biến; đối tượng thực tế là instance của `Person`. Lời gọi `named.name()` được thực thi theo triển khai áp dụng cho đối tượng runtime. Trong class file, lời gọi qua interface thường tương ứng với opcode `invokeinterface`; lời gọi phương thức instance qua lớp thường dùng `invokevirtual` khi thích hợp. Đây là chi tiết mô hình JVM, không phải lời hứa rằng mọi lời gọi Java luôn tạo đúng cùng một opcode sau mọi tối ưu của compiler/runtime.

### 5.2. Vì sao interface là kiểu tham chiếu dù không tự tạo instance?

Không thể viết `new Named()` khi `Named` là interface thông thường. Tuy vậy, biến `Named` có thể chứa:

- Tham chiếu tới đối tượng của lớp bất kỳ hiện thực `Named`.
- Giá trị `null`.
- Đối tượng của lớp con kế thừa triển khai `Named` nếu phù hợp.

Interface không phải bản sao của đối tượng; nó là **cách biểu diễn khả năng/quan hệ kiểu** của đối tượng. Một đối tượng có thể được tham chiếu qua nhiều interface khác nhau.

```java
Runnable r = () -> System.out.println("run");
Object sameObject = r;
```

Cả `r` và `sameObject` có thể giữ tham chiếu tới cùng một object runtime. `r.run()` gọi hàm triển khai; `sameObject.run()` không hợp lệ tại compile-time vì kiểu tĩnh `Object` không khai báo `run()`.

### 5.3. Interface không loại bỏ kiểm tra runtime

```java
Object candidate = "text";
System.out.println(candidate instanceof Runnable); // false
```

Tham chiếu runtime tới `String` không trở thành `Runnable` chỉ vì programmer muốn ép kiểu. Ép kiểu sang interface không được hỗ trợ bởi đối tượng có thể ném `ClassCastException`. `null` thì cast được sang interface nhưng không thể gọi phương thức của interface khi vẫn null.

Kiểu **giao diện** trong JVM còn xuất hiện trong kiểm tra kiểu, descriptor, quy tắc assignability và liên kết phương thức. Tính đa hình chỉ hoạt động khi đối tượng thực tế phù hợp hợp đồng.

## 6. Kiểu mảng (*array type*): phần tử có thể là primitive hoặc reference

### 6.1. Mọi mảng Java đều là đối tượng

```java
int[] numbers = new int[3];
String[] words = new String[3];
```

Cả `int[]` và `String[]` đều là **reference type** và đều tham chiếu tới **đối tượng mảng**. Sự khác biệt là **kiểu thành phần** (*component type*):

- `int[]` có component type `int` (primitive). Mỗi slot chứa một giá trị `int`.
- `String[]` có component type `String` (reference). Mỗi slot chứa giá trị tham chiếu tới `String` hoặc `null`.
- `String[][]` có component type `String[]` (cũng là một kiểu mảng); phần tử của mảng ngoài là các tham chiếu tới mảng trong.

Đối tượng mảng có **độ dài cố định** kể từ khi tạo. `array.length` trả số phần tử, còn `array.length = 7` là lỗi biên dịch. Muốn tăng sức chứa linh hoạt, xem xét các collection như `ArrayList` khi yêu cầu phù hợp.

### 6.2. Giá trị mặc định của các phần tử

| Khai báo | Kiểu phần tử | Giá trị mặc định |
| --- | --- | --- |
| `new int[2]` | `int` | `0` |
| `new boolean[2]` | `boolean` | `false` |
| `new double[2]` | `double` | `0.0` |
| `new String[2]` | `String` | `null` |
| `new Runnable[2]` | `Runnable` | `null` |
| `new int[2][]` | `int[]` (kiểu tham chiếu) | `null` |

Nếu `String[] array = null;` thì bản thân biến không trỏ tới mảng nào. Nếu `String[] array = new String[2];` thì có mảng thật với hai phần tử ban đầu là null. Đây là hai trạng thái khác nhau.

### 6.3. Mảng một chiều, nhiều chiều và jagged array

```java
int[][] grid = new int[2][3];
```

`grid` tham chiếu tới một mảng bên ngoài gồm hai phần tử kiểu `int[]`; mỗi phần tử trỏ tới một mảng `int` độ dài 3.

```text
grid ──> [ ref hàng 0 | ref hàng 1 ]
              |             |
              v             v
           [0,0,0]       [0,0,0]
```

Mảng nhiều chiều Java là **mảng của các mảng**. Các hàng có thể dài khác nhau:

```java
int[][] ragged = new int[2][];
ragged[0] = new int[] {1};
ragged[1] = new int[] {2, 3, 4};
```

Ở thời điểm sau `new int[2][]` nhưng trước khi gán hai hàng, mỗi phần tử `ragged[0]` và `ragged[1]` đều là `null`. Cố truy cập `ragged[0].length` lúc này sẽ dẫn đến `NullPointerException`.

### 6.4. Mảng là đối tượng, thuộc về phân cấp đặc biệt

Mọi đối tượng mảng Java đều có `Object` là superclass trực tiếp theo mô hình runtime của Java và thực hiện hai marker interface `java.lang.Cloneable` và `java.io.Serializable`. Ví dụ:

```java
Object value = new int[] {1, 2};
Cloneable cloneable = (Cloneable) value;
java.io.Serializable serializable = (java.io.Serializable) value;
```

Các phép cast trong ví dụ thành công vì giá trị runtime là mảng. Tuy nhiên, `int[]` **không phải** `Object[]`: phần tử của `int[]` là số nguyên primitive, không phải tham chiếu object. Mã sau không biên dịch:

```java
// Minh họa lỗi kiểu (dòng chủ ý được chú thích):
// Object[] array = new int[3]; // incompatible types
```

Ngược lại, `String[]` có thể được gán cho `Object[]` vì các mảng **có phần tử tham chiếu** hỗ trợ quan hệ hiệp biến có điều kiện (phần dưới).

### 6.5. Mảng giữ kiểu thành phần runtime

Mảng tham chiếu **ghi nhớ kiểu thành phần runtime** để JVM kiểm tra phép ghi vào phần tử. Vì vậy `Object[] view = new String[2]` hợp lệ, nhưng đối tượng thực vẫn là `String[]` và JVM không cho ghi một `Integer` vào slot đó.

Có thể quan sát:

```java
Object a = new String[2];
Object b = new int[2];
System.out.println(a.getClass().isArray()); // true
System.out.println(b.getClass().isArray()); // true
```

`a.getClass().getComponentType()` phản ánh `String.class`, còn `b.getClass().getComponentType()` phản ánh `int.class`. Kiểm tra runtime chỉ thực hiện được khi tham chiếu khác `null`.

## 7. Array covariance và `ArrayStoreException`

Quan hệ **covariance** của mảng tham chiếu có nghĩa: khi `Sub` là subtype của `Super`, thì `Sub[]` có thể sử dụng ở nơi chấp nhận `Super[]`, theo quy tắc kiểu tương ứng.

```java
String[] actual = new String[2];
Object[] view = actual;    // hợp lệ tại compile-time
view[0] = "hello";        // hợp lệ tại runtime
// view[1] = 123;         // biên dịch được, nhưng ném ArrayStoreException
```

Lý do:

1. Kiểu tĩnh của `view` là `Object[]`, nên compiler cho phép lưu một `Integer` (autoboxing từ số `123`).
2. Đối tượng mảng runtime thực sự là `String[]`.
3. Khi lệnh lưu phần tử tham chiếu chạy, JVM kiểm tra giá trị có hợp lệ với **component type thực tế** của mảng hay không.
4. `Integer` không phải `String` → `ArrayStoreException`.

**Điều quan trọng:** không phải tất cả mảng Java đều có covariance giống nhau. `int[]` không có phép gán như `Object[]`; với các component **primitive**, những mảng khác kiểu primitive không tạo quan hệ subtype bằng widening số. Ví dụ `int[]` không tự chuyển thành `long[]`.

So với generics:

```java
// Minh họa compile-time (dòng không hợp lệ được chú thích):
// java.util.List<Object> objects = new java.util.ArrayList<String>();
```

`List<String>` không là subtype của `List<Object>` (invariance của generic type argument), trong khi `String[]` là subtype của `Object[]`. Cách thiết kế này giúp generics phát hiện nhiều phép ghi sai **khi biên dịch**; mảng có thể phải kiểm tra cả **khi chạy**.

**Rủi ro thực tế:** truyền một `String[]` vào API nhận `Object[]` rồi API ghi giá trị không phải `String` có thể phát sinh `ArrayStoreException` sâu trong chương trình. Khi được phép thay đổi thiết kế, API nên khai báo đúng kiểu thành phần hoặc dùng generic collection với hợp đồng phù hợp.

## 8. Các phép chuyển kiểu, so sánh và lỗi runtime

| Thao tác | Ví dụ | Kết quả / lưu ý |
| --- | --- | --- |
| Widening reference | `Object o = "A";` | Hợp lệ: `String` tương thích với `Object` |
| Interface reference | `CharSequence c = "A";` | Hợp lệ: `String` thực hiện `CharSequence` |
| Null assignment | `String s = null;` | Hợp lệ: biến tham chiếu giữ null |
| Null cast | `String s = (String) null;` | Hợp lệ, kết quả vẫn null |
| Null `instanceof` | `null instanceof String` | `false` |
| Null dereference | `((String) null).length()` | `NullPointerException` |
| Checked downcast | `(String) someObject` | Thành công nếu runtime object phù hợp hoặc null; nếu không có thể `ClassCastException` |
| Reference array upcast | `Object[] a = new String[1];` | Biên dịch được |
| Wrong reference array store | `a[0] = Integer.valueOf(3);` | `ArrayStoreException` nếu a thực là `String[]` |
| Primitive array as object | `Object o = new int[1];` | Hợp lệ vì mảng là đối tượng |
| Primitive array as object array | `Object[] o = new int[1];` | Không biên dịch |
| Read beyond array bounds | `new int[1][1]` (truy cập index 1 ở mảng ngoài) | `ArrayIndexOutOfBoundsException` |
| Negative array size | `new String[-1]` | `NegativeArraySizeException` khi chạy |

**Lưu ý:** phát sinh lỗi còn tùy **biểu thức thực sự được thực thi**. Bảng mô tả ngữ nghĩa của trường hợp tương ứng; không nên hiểu compiler cho phép mọi ví dụ như một chương trình độc lập.

## 9. Ví dụ Java 17+ hoàn chỉnh và stdout chính xác

Tạo một tệp duy nhất **`ReferenceTypesDemo.java`** trong thư mục hiện tại:

```java
import java.io.Serializable;
import java.util.Arrays;

public class ReferenceTypesDemo {
    interface Named {
        String name();
    }

    static final class Student implements Named {
        private final String value;

        Student(String value) {
            this.value = value;
        }

        @Override
        public String name() {
            return value;
        }
    }

    static void report(Named candidate) {
        System.out.println("is null: " + (candidate == null));
        System.out.println("instanceof Named: " + (candidate instanceof Named));
    }

    public static void main(String[] args) {
        Student student = new Student("Lan");
        Object byClass = student;
        Named byInterface = student;

        System.out.println("class: " + (byClass instanceof Student));
        System.out.println("interface call: " + byInterface.name());

        Named missing = null;
        report(missing);

        String[] names = new String[2];
        System.out.println("reference default: " + names[0]);
        names[0] = "Java";
        names[1] = "JVM";
        System.out.println("array: " + Arrays.toString(names));
        System.out.println("length: " + names.length);
        System.out.println("array as Object: " + (names instanceof Object));
        System.out.println("array as Cloneable: " + (names instanceof Cloneable));
        System.out.println("array as Serializable: " + (names instanceof Serializable));

        Object[] wider = names;
        try {
            wider[0] = Integer.valueOf(42);
        } catch (ArrayStoreException exception) {
            System.out.println("array store rejected");
        }
        System.out.println("array after check: " + Arrays.toString(names));

        int[] numbers = new int[2];
        System.out.println("primitive default: " + numbers[0]);
        System.out.println("primitive array as Object: " + (numbers instanceof Object));

        int[][] grid = new int[2][];
        System.out.println("nested row null: " + (grid[0] == null));
        grid[0] = new int[] {1, 2};
        grid[1] = new int[] {3};
        System.out.println("jagged row lengths: "
                + grid[0].length + ", " + grid[1].length);

        String absent = (String) null;
        System.out.println("cast null: " + (absent == null));
        System.out.println("null instanceof Object: " + (absent instanceof Object));

        try {
            absent.length();
        } catch (NullPointerException exception) {
            System.out.println("dereference null rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ReferenceTypesDemo.java
java ReferenceTypesDemo
```

**Stdout chính xác** của chương trình (không phụ thuộc PID hoặc chuỗi thông báo ngoại lệ của JVM):

```text
class: true
interface call: Lan
is null: true
instanceof Named: false
reference default: null
array: [Java, JVM]
length: 2
array as Object: true
array as Cloneable: true
array as Serializable: true
array store rejected
array after check: [Java, JVM]
primitive default: 0
primitive array as Object: true
nested row null: true
jagged row lengths: 2, 1
cast null: true
null instanceof Object: false
dereference null rejected
```

### Giải thích các dòng quan trọng

**`class: true`:** biến `byClass` có kiểu khai báo `Object` nhưng tham chiếu một đối tượng `Student`. `instanceof Student` kiểm tra đối tượng runtime.

**`interface call: Lan`:** biến `byInterface` có kiểu khai báo `Named`; runtime gọi triển khai `name()` của `Student`.

**`is null: true` và `instanceof Named: false`:** kiểu khai báo giao diện cho phép null, nhưng null không đại diện cho một đối tượng hiện thực giao diện.

**`reference default: null`:** các slot của mảng `String[]` được tạo mới bắt đầu bằng null reference.

**`array as Object/Cloneable/Serializable: true`:** các đối tượng mảng tham gia vào phân cấp kiểu đặc biệt.

**`array store rejected`:** kiểm tra ở runtime phát hiện giá trị `Integer` không thể được lưu vào mảng thực tế `String[]`, ngay cả khi biến dùng để ghi có kiểu `Object[]`. Phần tử cũ vẫn được giữ lại vì thao tác không được chấp nhận.

**`primitive array as Object: true`:** bản thân `int[]` là một object, dù giá trị mỗi phần tử là primitive `int`.

**`nested row null: true`:** mảng bên ngoài `new int[2][]` được tạo, nhưng chưa tạo các mảng hàng. Hai hàng được tạo sau đó có độ dài khác nhau.

**`cast null: true` và `null instanceof Object: false`:** cast null hợp lệ, nhưng null không phải instance của `Object`.

**`dereference null rejected`:** lời gọi `absent.length()` cần một đối tượng `String` và gây `NullPointerException`; ví dụ chủ động bắt exception để tiếp tục và giữ stdout rõ ràng.

Bài dùng các lớp nested để bảo đảm **một tệp nguồn độc lập**, với tên tệp trùng tên public class và lệnh chạy đơn giản. Các ví dụ khác trong bài là minh họa rời; ví dụ đầy đủ ở mục này mới được dùng để kiểm chứng stdout liền mạch.

## 10. Bytecode/JVM nhìn các kiểu tham chiếu ra sao?

Mã nguồn Java cung cấp cú pháp giàu ý nghĩa; class file biểu diễn nhiều kiểu dưới dạng **descriptor** và các lệnh thao tác reference.

### 10.1. Descriptor cho kiểu lớp, giao diện và mảng

Ví dụ một số **field descriptor** ở cấp class file:

| Kiểu trong Java | Descriptor JVM | Giải thích |
| --- | --- | --- |
| `int` | `I` | Giá trị primitive `int` |
| `java.lang.String` | `Ljava/lang/String;` | Một class type |
| `java.lang.Runnable` | `Ljava/lang/Runnable;` | Một interface type |
| `int[]` | `[I` | Mảng một chiều của primitive `int` |
| `String[]` | `[Ljava/lang/String;` | Mảng một chiều của `String` |
| `int[][]` | `[[I` | Mảng hai chiều theo nghĩa mảng của mảng `int` |
| `Object[][]` | `[[Ljava/lang/Object;` | Mảng của mảng chứa tham chiếu `Object` |

Quy tắc chính:

- `L<tên-nội-bộ>;` biểu diễn kiểu class hoặc interface; tên nội bộ trong descriptor dùng dấu `/`.
- Mỗi ký tự `[` thêm một chiều mảng.
- Primitive có mã descriptor riêng như `I` cho `int`, `J` cho `long`, `Z` cho `boolean`.

Trong bytecode, **không có “field descriptor của null”** như một reference type độc lập. `null` là một **giá trị reference đặc biệt**, có thể được đẩy lên operand stack bằng lệnh `aconst_null`. Khi xác minh bytecode, JVM có các khái niệm verification type riêng cho null để kiểm tra tính hợp lệ của luồng dữ liệu; không nên đánh đồng chúng với tên kiểu có thể khai báo trong Java.

### 10.2. Những opcode quan trọng

| Opcode / nhóm | Vai trò khái niệm |
| --- | --- |
| `aconst_null` | Đưa một null reference lên operand stack |
| `aload` / `astore` | Nạp/lưu giá trị reference trong biến cục bộ |
| `new` | Tạo đối tượng của kiểu lớp phù hợp |
| `newarray` | Tạo mảng có phần tử primitive |
| `anewarray` | Tạo mảng có phần tử reference |
| `multianewarray` | Tạo mảng nhiều chiều theo số chiều được chỉ định |
| `aaload` / `aastore` | Đọc/ghi phần tử reference của một mảng |
| `iaload` / `iastore` | Đọc/ghi phần tử `int` của mảng |
| `arraylength` | Lấy độ dài mảng |
| `checkcast` | Kiểm tra ép kiểu reference tại runtime |
| `instanceof` | Kiểm tra đối tượng có tương thích một reference type hay không |
| `ifnull` / `ifnonnull` | Nhảy theo điều kiện reference null/khác null |
| `if_acmpeq` / `if_acmpne` | So sánh bằng/khác của hai giá trị reference |
| `invokevirtual` / `invokeinterface` | Thực hiện các dạng lời gọi phương thức instance theo cơ chế thích hợp |

Cùng là **reference**, nhưng JVM giữ đủ thông tin kiểu và kiểm tra để không thể tùy tiện coi một mảng `int[]` là `Object[]`. Khi `aastore` chạy, giá trị được lưu phải tương thích với kiểu thành phần **thực tế** của mảng, nếu không sẽ ném `ArrayStoreException`.

`checkcast` có một chi tiết dễ quên: với null reference, nó vẫn **thành công** và giữ null. Còn `instanceof` trả kết quả false với null. Do đó cả hai opcode đều xử lý null khác với việc cố dereference null.

### 10.3. Tự quan sát bytecode bằng công cụ JDK

Sau khi biên dịch chương trình hoàn chỉnh:

```bash
javap -c -p ReferenceTypesDemo
```

`javap` in bytecode các phương thức, trong đó có `main`. Có thể tìm các tên opcode như `instanceof`, `anewarray`, `aastore`, `newarray` và `arraylength` tương ứng với từng phép toán trong mã nguồn. Với lớp nested, lớp thực thi interface sẽ được sinh ra thành class file riêng, ví dụ `ReferenceTypesDemo$Student.class` tùy môi trường và cách liệt kê tên tệp.

**Không dựa vào offset bytecode hoặc thứ tự mọi instruction như một API cố định.** Compiler có thể thay đổi việc biên dịch giữa các phiên bản; các tối ưu thực thi JIT cũng không phải là văn bản bytecode mà `javap -c` hiển thị.

### 10.4. Ba nhóm reference types liên hệ thế nào với kiểm tra kiểu?

- **Class type:** quan hệ lớp con/lớp cha và đối tượng runtime chi phối assignability, cast và dispatch phương thức.
- **Interface type:** runtime kiểm tra đối tượng có hiện thực interface phù hợp; lời gọi có thể liên kết tới implementation của lớp runtime.
- **Array type:** vừa là đối tượng, vừa mang kiểu thành phần và số chiều; JVM phải kiểm tra phép gán và ghi phần tử theo các quy tắc runtime thích hợp.

Vì **`null` không có đối tượng runtime**, nó có thể đi qua nhiều phép gán/cast reference mà không tạo ra một thông tin class runtime cụ thể.

## 11. Các lỗi thường gặp trong thiết kế và debug

### 11.1. Nhầm `null` với giá trị mặc định nghiệp vụ

Một đối tượng `User` có trường `String email = null` không có nghĩa email là chuỗi rỗng; cũng không tự chứng minh “chưa bao giờ gán”, vì một chương trình có thể gán null chủ động. Hợp đồng nghiệp vụ phải tự định nghĩa ý nghĩa của việc thiếu giá trị.

### 11.2. Gọi `equals` trên reference chưa kiểm tra

```java
String input = null;
// input.equals("yes"); // NullPointerException
System.out.println("yes".equals(input)); // false
```

Đảo phía literal có thể hữu ích trong trường hợp đơn giản; với các API khác, nên dùng `Objects.equals(a, b)` khi cần so sánh null-safe. Không nhầm `==` (kiểm tra **cùng tham chiếu**) với `equals` (hợp đồng so sánh do lớp định nghĩa).

### 11.3. Dùng `instanceof` để nghĩ rằng null có một kiểu runtime cụ thể

`String s = null` nói lên **kiểu khai báo** của biến `s`; không có đối tượng String đang tồn tại từ giá trị `s`. `s instanceof String` là false, và `s.getClass()` ném `NullPointerException`.

### 11.4. Ép kiểu mà không kiểm tra loại đối tượng

`Object payload` có thể tham chiếu `String`, `Integer`, mảng hoặc một loại đối tượng khác. Ép `(String) payload` chỉ hợp lệ tại runtime nếu payload null hoặc là đối tượng tương thích `String`. Có thể dùng `instanceof` khi thật sự cần phân nhánh; trong thiết kế API, ưu tiên khai báo kiểu chính xác để giảm cast không cần thiết.

### 11.5. Cho rằng mọi mảng là `Object[]`

`int[]` cũng là Object, nhưng không phải `Object[]`. `Object[]` dùng phần tử reference. Với mảng primitive, chọn đúng kiểu mảng và các overload API tương ứng (ví dụ `Arrays.toString(int[])` khác overload `Arrays.toString(Object[])`).

### 11.6. Quên kiểm tra kiểu khi ghi qua biến mảng cha

`Object[] arr = new String[1]` vẫn trỏ tới mảng String. Biến có kiểu `Object[]` **không thay đổi component type runtime**. Kiểm tra ghi mảng có thể ném `ArrayStoreException`.

### 11.7. Nhầm mảng nhiều chiều với một khối dữ liệu hai chiều cố định

`int[][]` trong Java là mảng chứa tham chiếu tới các mảng `int[]`. Số cột giữa các hàng có thể khác nhau, và một hàng có thể bằng null. Khi duyệt cần kiểm tra hàng null nếu dữ liệu có thể ở trạng thái này.

### 11.8. Nhầm null với giá trị không có trong generic collection

`List<String>` là collection tham chiếu; nhiều triển khai cho phép phần tử null, nhưng không phải mọi collection đều cho phép. Hợp đồng của từng API quyết định. Không dùng `null` làm dấu hiệu “không tìm thấy” nếu cách đó gây mơ hồ giữa “không có kết quả” và “có kết quả với giá trị null”; có thể cân nhắc kiểu kết quả rõ ràng như `Optional` trong các API thích hợp.

### 11.9. Cho rằng mọi lỗi null đều được compiler bắt

Trình biên dịch Java kiểm tra nhiều vấn đề kiểu và definite assignment nhưng không bảo đảm mọi tham chiếu khác null. Java 17 không tự động suy luận không-null cho mọi lối đi của chương trình. Kiểm thử, ràng buộc API và phân tích tĩnh có thể giúp giảm lỗi.

## 12. Bài tập tự kiểm tra có đáp án

**Câu 1.** `int[] a = null;` hợp lệ không? `int a = null;` thì sao?

**Đáp án:** Khai báo thứ nhất hợp lệ vì `int[]` là array/reference type. Khai báo thứ hai không hợp lệ vì `int` là primitive.

**Câu 2.** Vì sao `new String[3]` không bằng `null` dù mọi phần tử ban đầu đều null?

**Đáp án:** Biểu thức tạo **một đối tượng mảng có thật** với độ dài 3; giá trị tham chiếu tới mảng khác null. Chỉ **ba phần tử** của mảng tham chiếu khởi đầu bằng null.

**Câu 3.** Biến `Runnable task = null;` có nghĩa tồn tại một instance của một lớp hiện thực `Runnable` không?

**Đáp án:** Không. `Runnable` là kiểu khai báo; giá trị null không tham chiếu instance nào. `task instanceof Runnable` trả false.

**Câu 4.** Đoạn `Object[] items = new String[1]; items[0] = 7;` có biên dịch không? Chạy ra sao?

**Đáp án:** Biên dịch được nhờ boxing `7` thành `Integer` và khả năng dùng `String[]` như `Object[]`. Khi chạy, thao tác ghi `Integer` vào mảng thực tế `String[]` ném `ArrayStoreException`.

**Câu 5.** `Object data = new int[2];` và `Object[] data = new int[2];` có cùng tính hợp lệ không?

**Đáp án:** Không. Dòng thứ nhất hợp lệ vì mảng là object; dòng thứ hai sai kiểu vì `int[]` không phải `Object[]`.

**Câu 6.** Vì sao `(String) null` hợp lệ mà `((String) null).length()` thất bại?

**Đáp án:** `checkcast` với null reference cho kết quả null; `length()` là lời gọi instance cần đối tượng khác null, nên ném `NullPointerException`.

**Câu 7.** `String[][] values = new String[2][];` có bao nhiêu đối tượng mảng mới ngay sau dòng đó?

**Đáp án:** Có **một đối tượng mảng ngoài** với hai phần tử kiểu `String[]`, ban đầu cả hai là null. Chưa có mảng hàng nào được tạo.

**Câu 8.** Trong ba loại JVM reference type, `String[]` thuộc loại nào, còn `Runnable` thuộc loại nào?

**Đáp án:** `String[]` là **array type**; `Runnable` là **interface type**. `String` là **class type**.

## 13. Ghi nhớ cốt lõi

- JVM phân biệt **primitive** và **reference**; ba nhóm reference type theo JVMS là **class**, **interface** và **array**.
- Biến tham chiếu có thể chứa null, tức **không trỏ tới đối tượng**. JLS có khái niệm **null type** của biểu thức `null`, nhưng đó không phải một nhóm class/interface/array bổ sung của JVM.
- **Kiểu tĩnh** kiểm soát thao tác hợp lệ lúc biên dịch; **kiểu runtime** của đối tượng quyết định kết quả kiểm tra cast/`instanceof` và dispatch tương ứng.
- **Interface reference** có thể trỏ tới instance của lớp hiện thực interface; bản thân interface thông thường không được khởi tạo trực tiếp bằng `new`.
- **Mảng là object** bất kể phần tử primitive hay reference. Mảng reference có slot mặc định null, mảng primitive có giá trị mặc định riêng; mảng nhiều chiều là mảng của các mảng.
- **Array covariance** giúp `String[]` dùng như `Object[]`, nhưng runtime kiểm tra phép ghi và có thể ném `ArrayStoreException`.
- `null` có thể gán, so sánh, cast; chỉ các thao tác yêu cầu đối tượng thật mới có nguy cơ `NullPointerException`.

### Tài liệu đặc tả

- [Java Virtual Machine Specification §2.4: Reference Types and Values (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.4) — phân loại reference types và null reference.
- [JVM Specification §4.3: Descriptors (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3) — descriptor của class, interface và array.
- [JVM Specification §6: JVM Instruction Set (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html) — các opcode liên quan như `aastore`, `checkcast`, `instanceof`.
- [Java Language Specification §4: Types, Values, and Variables (Java SE 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html) — reference types, null type, biến và kiểu.
- [Java Language Specification §10: Arrays (Java SE 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html) — quy tắc mảng, kiểu phần tử và array store checks.
