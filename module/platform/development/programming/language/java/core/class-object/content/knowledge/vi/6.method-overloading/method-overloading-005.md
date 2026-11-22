# Thứ tự xét chuyển kiểu, boxing và varargs khi nạp chồng phương thức Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một lời gọi như `f(5)` có thể phù hợp nhiều overload, nhưng compiler phải chọn theo **quy tắc xác định**, không theo cảm giác “kiểu nào gần nhất”.
- Nêu đúng **ba pha** xét khả năng áp dụng phương thức theo Java Language Specification (JLS): **strict invocation** (không boxing/unboxing), **loose invocation** (cho phép boxing/unboxing) và **variable arity invocation** (varargs).
- Phân biệt **primitive widening**, **reference widening**, **boxing**, **unboxing**, **unboxing rồi primitive widening**, và những chuỗi chuyển kiểu không được dùng ngầm trong lời gọi.
- Giải thích vì sao **fixed-arity overload có thể được chọn trước varargs** ngay khi nó cần boxing, và vì sao một phương thức khai báo `...` đôi khi được xét **ngay pha fixed arity**.
- Dự đoán chính xác overload được chọn hoặc lỗi **ambiguous method call**, kể cả khi truyền `null`, array, wrapper type, hoặc một giá trị primitive.
- Đọc thông báo lỗi `no suitable method found`, `reference ... is ambiguous`, sửa lời gọi hoặc thiết kế overload rõ ràng hơn.

## 1. Vì sao cần một thứ tự xét overload?

Cho hai khai báo:

~~~java
static String choose(long value) {
    return "long";
}

static String choose(Integer value) {
    return "Integer";
}
~~~

Trong cùng một lớp, cả hai đều mang tên `choose` nhưng có kiểu tham số khác nhau, nên **nạp chồng phương thức** (*method overloading*) là hợp lệ.

Lời gọi `choose(5)` có đối số literal kiểu `int`. Java có thể:

- Chuyển `int` sang `long` bằng **primitive widening**.
- Chuyển `int` sang `Integer` bằng **boxing**.

Vậy overload nào được chọn? **`choose(long)`**. Nguyên nhân không phải vì kiểu `long` “giống số nguyên hơn” theo cách trực giác; nguyên nhân là Java tìm phương thức áp dụng qua **nhiều pha**, và primitive widening được xét ở pha sớm hơn boxing.

Nguyên tắc chính là:

> Khi Java tìm được ít nhất một phương thức áp dụng trong một pha, nó **không chuyển sang pha muộn hơn** chỉ để tìm một overload có vẻ hấp dẫn hơn.

Trong pha đã được chọn, compiler lại xét **phương thức cụ thể nhất** (*most specific*). Hai lớp quy tắc này cần được phân biệt: **chọn pha áp dụng** trước, **chọn phương thức cụ thể nhất trong pha đó** sau.

Chú ý: việc **khai báo nhiều overload** và việc **chọn overload ở một lời gọi** là hai bài toán khác nhau. Các ví dụ trong bài tập trung vào overload resolution tại **thời điểm biên dịch**. Sau khi một instance method được chọn, việc xác định implementation override ở runtime là bước khác.

## 2. Ba pha của overload resolution

Trong JLS, khi xét lời gọi có tên phương thức và danh sách đối số, compiler xác định các phương thức tiềm năng có thể truy cập, sau đó xét khả năng áp dụng theo thứ tự:

| Pha | Tên trong JLS | Cho phép những gì ở mức chính? | Ví dụ điển hình |
| --- | --- | --- | --- |
| **1** | Strict invocation applicability | Fixed arity; identity, primitive widening, reference widening, những quy tắc tương ứng cho generic inference; **không cần boxing/unboxing** | `int` → `long`; `String` → `Object` |
| **2** | Loose invocation applicability | Fixed arity; thêm **boxing/unboxing** và các chuỗi chuyển đổi được quy định, chẳng hạn boxing rồi reference widening, unboxing rồi primitive widening | `int` → `Integer`; `int` → `Object`; `Integer` → `long` |
| **3** | Variable arity applicability | Nếu hai pha trước không có phương thức áp dụng, xét cách gọi **varargs** với số lượng đối số biến đổi; từng phần tử phải có kiểu phù hợp | `sum(1, 2, 3)` cho `sum(int...)` |

**Thứ tự xét là 1 → 2 → 3.** Java không mặc nhiên “cộng điểm” cho tất cả chuyển đổi rồi chọn phương thức có tổng điểm thấp nhất. Nếu pha 1 đã có ứng viên áp dụng, pha 2 và 3 sẽ không được dùng để tranh quyền với pha 1.

Với mỗi pha:

1. Tập ứng viên còn phụ thuộc **tên, số lượng/thứ tự tham số, tính truy cập, generic type inference** và dạng lời gọi.
2. Compiler chọn phương thức **most-specific** trong các phương thức áp dụng của pha đó.
3. Nếu không tìm được lựa chọn duy nhất theo quy tắc, lời gọi có thể **mơ hồ** và báo lỗi biên dịch.
4. Nếu pha 1 không có ứng viên áp dụng, mới xét pha 2; nếu pha 2 cũng không có, mới xét pha 3.

Việc “pha sớm thắng pha muộn” **không có nghĩa** kiểu tham số của mọi ứng viên trong pha sớm luôn hẹp hơn hay gần giá trị hơn các ứng viên ở pha muộn. Đó là chính sách ưu tiên để bảo vệ tính tương thích của những lời gọi Java đã có từ trước khi boxing và varargs được bổ sung.

### 2.1. Sơ đồ tư duy

~~~text
Lời gọi method: f(arg1, arg2, ...)
            |
            v
Có method áp dụng theo FIXED ARITY,
không boxing/unboxing?  -- Có --> Chọn most-specific pha 1
            |
          Không
            v
Có method áp dụng theo FIXED ARITY,
cho phép boxing/unboxing? -- Có --> Chọn most-specific pha 2
            |
          Không
            v
Có method VARARGS áp dụng
với variable arity?      -- Có --> Chọn most-specific pha 3
            |
          Không
            v
        Lỗi: không có method áp dụng
~~~

Đây là sơ đồ học tập rút gọn. JLS còn có các ràng buộc về generic inference, tính phù hợp của biểu thức lambda/method reference, và quy tắc chọn phương thức cụ thể nhất. Đừng dùng sơ đồ thay thế toàn bộ đặc tả khi gặp generic overload phức tạp.

## 3. Pha 1: fixed arity và strict invocation

Ở **pha 1**, compiler tìm phương thức có **số tham số cố định phù hợp số đối số** và cho phép những chuyển đổi nghiêm ngặt, chủ yếu:

- **Identity conversion**: `int` → `int`; `String` → `String`.
- **Primitive widening**: `byte` → `short`/`int`/`long`...; `int` → `long`/`float`/`double`; `float` → `double`.
- **Reference widening**: `String` → `Object`, `ArrayList<String>` → các supertype tương ứng hợp lệ.
- Các quy tắc inference/checking đi kèm với generic methods theo ngữ cảnh.

**Boxing (`int` → `Integer`) và unboxing (`Integer` → `int`) không làm một phương thức trở thành ứng viên của pha 1.**

Ví dụ:

~~~java
static String calc(long x) { return "long"; }
static String calc(double x) { return "double"; }
~~~

`calc(10)` với literal kiểu `int` có hai ứng viên trong pha 1: `calc(long)` và `calc(double)`. Java chọn **`calc(long)`**: ở đây `long` có thể widening thành `double`, nên overload `long` được coi cụ thể hơn trong so sánh này.

Nếu bổ sung `calc(int)`:

~~~java
static String calc(int x) { return "int"; }
~~~

thì `calc(10)` chọn `calc(int)` theo nguyên tắc cụ thể nhất trong pha 1; không phải vì compiler chỉ nhìn overload đầu tiên trong tệp. **Thứ tự khai báo method trong source không quyết định overload được chọn.**

### 3.1. Primitive widening là gì?

Bảng các chuyển đổi mở rộng nguyên thủy thường cần nhớ:

| Từ kiểu | Có thể widening sang |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

`boolean` không được chuyển sang kiểu số. Không có primitive widening từ `char` sang `short`, từ `short` sang `char`, từ `double` sang `float`, hoặc từ `int` sang `byte`.

**Widening không phải cam kết không mất độ chính xác**: một số số nguyên lớn chuyển sang dấu chấm động như `float` có thể bị làm tròn. Quy tắc overload vẫn sử dụng tính hợp lệ của chuyển kiểu theo ngôn ngữ, không dựa trên việc giá trị hiện tại có giữ nguyên chính xác hay không.

### 3.2. Reference widening không cần boxing

Ví dụ:

~~~java
static String display(Object x) { return "Object"; }
static String display(CharSequence x) { return "CharSequence"; }
~~~

`display("Java")` có kiểu đối số `String`; `String` là subtype của cả `Object` lẫn `CharSequence`. Hai overload đều áp dụng pha 1, nhưng `CharSequence` cụ thể hơn `Object`, nên kết quả là `"CharSequence"`.

Nếu đối số là biến khai báo `Object value = "Java";`, lời gọi `display(value)` lại chọn `display(Object)` vì overload được quyết định bằng **kiểu tĩnh `Object`**, không dựa vào lớp `String` của đối tượng ở runtime.

## 4. Pha 2: fixed arity có boxing và unboxing

Khi **không có phương thức nào áp dụng trong pha 1**, compiler chuyển sang pha 2. Các chuyển đổi thường gặp:

- **Boxing**: `int` → `Integer`, `long` → `Long`, `boolean` → `Boolean`…
- **Unboxing**: `Integer` → `int`, `Long` → `long`…
- **Boxing rồi widening reference**: `int` → `Integer` → `Number` hoặc `Object`.
- **Unboxing rồi widening primitive**: `Integer` → `int` → `long`/`double`, khi đích cho phép.

Pha 2 vẫn áp dụng theo **fixed arity**: một phương thức đòi ba tham số không tự nhận một hay bốn đối số chỉ vì có boxing.

### 4.1. Widening được xét trước boxing

Giả sử:

~~~java
static String choose(long value) { return "long"; }
static String choose(Integer value) { return "Integer"; }
~~~

Với `choose(5)`:

1. Đối số `5` có kiểu `int`.
2. Pha 1: `choose(long)` áp dụng nhờ `int` → `long`.
3. `choose(Integer)` cần boxing, không áp dụng ở pha 1.
4. Compiler đã có ứng viên pha 1, nên **không cần xét pha 2**.
5. Phương thức được chọn là `choose(long)`, dù có một overload nhận wrapper `Integer`.

Với `choose(Integer.valueOf(5))`, đối số đã có kiểu tĩnh `Integer`; overload `choose(Integer)` áp dụng pha 1 bằng identity conversion. Nó thắng `choose(long)`, vốn cần unboxing rồi widening ở pha 2.

**Không có quy tắc “primitive luôn thắng wrapper” trong mọi lời gọi.** Quyết định phụ thuộc kiểu biểu thức đối số và pha có ứng viên.

### 4.2. Boxing và widening reference có thể cùng xuất hiện

Ví dụ:

~~~java
static String select(Object x) { return "Object"; }
static String select(Integer x) { return "Integer"; }
~~~

`select(7)` không có ứng viên pha 1 vì `int` không phải subtype tham chiếu của `Object` hoặc `Integer`, và hai overload đều cần boxing. Ở pha 2:

- `select(Object)` áp dụng nhờ `int` → `Integer` → `Object`.
- `select(Integer)` áp dụng nhờ `int` → `Integer`.

Trong cùng pha, `Integer` cụ thể hơn `Object`, nên **`select(Integer)` được chọn**.

Không được tổng quát hóa rằng “pha 2 chọn overload sử dụng ít bước chuyển đổi nhất”; quan hệ **most-specific** mới quyết định lựa chọn trong trường hợp này.

### 4.3. Unboxing rồi primitive widening

Giả sử chỉ có:

~~~java
static void consume(long value) {
    System.out.println(value);
}
~~~

Một biểu thức kiểu `Integer` như `Integer boxed = 12;` có thể truyền vào `consume(boxed)` bằng chuỗi **`Integer` → `int` → `long`**. Đây là chuyển đổi cho phép ở pha loose invocation.

Nếu biến `boxed` là `null`, phép unboxing ném `NullPointerException` ở runtime. **Việc compiler chấp nhận kiểu không có nghĩa giá trị runtime luôn an toàn.**

### 4.4. Không có mọi chuỗi chuyển kiểu tùy ý

Điểm dễ sai nhất là giả định:

> “`int` có thể thành `long`, `long` có thể boxing thành `Long`, vậy một đối số `int` tự truyền được vào tham số `Long`.”

Suy luận này **sai** đối với lời gọi method thông thường. Method invocation conversion **không cho phép widening primitive rồi boxing** thành wrapper khác theo chuỗi đó.

~~~java
static void receive(Long value) {
    System.out.println(value);
}

// Đặt trong một method:
// receive(7);  // Sai: int không tự chuyển thành Long
// receive(7L); // Đúng: literal long có thể boxing thành Long
~~~

Nếu giá trị ban đầu là `int n = 7;`, có thể viết `receive((long) n)` để compiler thực hiện boxing sau một phép cast biểu thức tường minh; hoặc `receive(Long.valueOf(n))` để chuyển có chủ đích.

Tương tự, **narrowing primitive rồi boxing** không tự diễn ra: `byte` method parameter không nhận trực tiếp literal `int` chỉ vì giá trị nằm trong miền byte.

~~~java
static void tiny(byte value) {
    System.out.println(value);
}

// Trong một method:
// tiny(10);         // Không hợp lệ: int -> byte là narrowing
// tiny((byte) 10);  // Hợp lệ vì có cast tường minh
~~~

**Phân biệt với gán biến:** `byte small = 10;` là phép gán hằng `int` với quy tắc assignment conversion riêng; điều đó không khiến `tiny(10)` tự hợp lệ.

## 5. Pha 3: variable arity invocation (varargs)

Phương thức varargs có dạng **tham số cuối cùng** là `T... values`. Trong thân method, tham số này là **mảng `T[]`**; khi lời gọi dùng variable arity, Java có thể nhận 0 hoặc nhiều giá trị riêng lẻ cho phần cuối.

~~~java
static String join(String separator, String... items) {
    return String.join(separator, items);
}
~~~

Các lời gọi phù hợp về số lượng/kiểu:

~~~java
join(",");                         // Phần items có 0 giá trị
join(",", "A");                    // 1 giá trị
join(",", "A", "B");               // 2 giá trị
join(",", new String[] {"A","B"}); // Một đối số mảng String[]
~~~

**Điểm then chốt:** pha 3 chỉ được thử **nếu không có phương thức áp dụng ở cả pha 1 lẫn pha 2**. Một overload fixed arity có thể thắng lời gọi biến độ dài dù fixed arity đó phải dùng boxing.

### 5.1. Boxing có thể được ưu tiên trước varargs

Xem các khai báo:

~~~java
static String route(Object value) { return "Object"; }
static String route(int... values) { return "varargs"; }
~~~

Lời gọi `route(5)` với đối số `int`:

- `route(Object)` **không áp dụng ở pha 1**, nhưng áp dụng ở **pha 2** thông qua boxing `int` → `Integer` và widening reference → `Object`.
- `route(int...)` không nhận một `int` như **một `int[]`** trong pha fixed arity; nó chỉ áp dụng khi pha 3 xét các phần tử varargs.
- Vì pha 2 đã có ứng viên, compiler chọn **`route(Object)`**.

Ngược lại, `route(5, 6)` có hai đối số, nên overload `route(Object)` một tham số không áp dụng. Pha 3 xét `route(int...)` với hai phần tử `int`, nên chọn overload varargs.

**Không nên hiểu “varargs bị xét cuối” thành “mọi method có dấu `...` đều chỉ xét ở pha 3”.** Một varargs method cũng có thể được gọi ở dạng fixed arity khi truyền đúng một mảng tương thích.

### 5.2. Varargs cũng được xét như mảng ở pha 1 hoặc 2

`void route(int... values)` có tham số hình thức thực tế kiểu `int[]`. Với lời gọi `route(new int[] {1, 2})`:

- Có **một** đối số `int[]`.
- Method `route(int...)` được xét **như method nhận `int[]` ở fixed arity**; nó đã phù hợp ở pha 1.
- Nếu cùng tồn tại overload `route(Object)`, cả hai áp dụng pha 1 (mảng `int[]` là kiểu tham chiếu subtype của `Object`).
- `int[]` cụ thể hơn `Object`, vì vậy overload `route(int...)` được chọn.

Trong trường hợp có thể gọi fixed arity, compiler không cần tạo thêm mảng chứa một phần tử là mảng; mảng đã được truyền làm một đối số.

Dấu `...` chỉ được dùng ở **tham số cuối**, và một phương thức chỉ được khai báo nhiều nhất một varargs parameter. `sum(int... values, int mode)` là cú pháp sai. Cũng không thể khai báo đồng thời `sum(int... values)` và `sum(int[] values)` trong cùng lớp để tạo hai overload, vì chúng có chữ ký tương ứng dạng `sum(int[])`.

## 6. Ví dụ hoàn chỉnh: kiểm chứng ba pha bằng stdout

Lưu vào **`OverloadPhasesDemo.java`**:

~~~java
public class OverloadPhasesDemo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static String pick(Object value) {
        return "Object";
    }

    static String pick(Integer value) {
        return "Integer";
    }

    static String route(Object value) {
        return "Object";
    }

    static String route(int... values) {
        return "varargs:" + values.length;
    }

    static String prefer(long value) {
        return "long";
    }

    static String prefer(int... values) {
        return "varargs:" + values.length;
    }

    static String numeric(long value) {
        return "long";
    }

    static String numeric(float value) {
        return "float";
    }

    public static void main(String[] args) {
        System.out.println("choose(5)=" + choose(5));
        System.out.println("choose(Integer)=" + choose(Integer.valueOf(5)));
        System.out.println("pick(5)=" + pick(5));
        System.out.println("route(5)=" + route(5));
        System.out.println("route(5,6)=" + route(5, 6));
        System.out.println("route(array)=" + route(new int[] {5, 6}));
        System.out.println("prefer(5)=" + prefer(5));
        System.out.println("prefer()=" + prefer());
        System.out.println("numeric(5)=" + numeric(5));
    }
}
~~~

Chạy bằng Java 17+ trong thư mục chứa tệp:

~~~bash
javac OverloadPhasesDemo.java
java OverloadPhasesDemo
~~~

Kết quả:

~~~text
choose(5)=long
choose(Integer)=Integer
pick(5)=Integer
route(5)=Object
route(5,6)=varargs:2
route(array)=varargs:2
prefer(5)=long
prefer()=varargs:0
numeric(5)=long
~~~

Giải thích từng dòng:

| Lời gọi | Pha tạo ứng viên được chọn | Overload được chọn và nguyên nhân |
| --- | --- | --- |
| `choose(5)` | 1 | `choose(long)`: `int` widening thành `long`; không cần boxing |
| `choose(Integer.valueOf(5))` | 1 | `choose(Integer)`: đối số đã là `Integer`; `choose(long)` cần unboxing |
| `pick(5)` | 2 | `pick(Integer)`: cả `Integer`, `Object` chỉ áp dụng sau boxing; `Integer` cụ thể hơn |
| `route(5)` | 2 | `route(Object)`: boxing + widening reference; `int...` cần variable arity ở pha 3 |
| `route(5,6)` | 3 | `route(int...)`: hai phần tử `int`; overload `Object` chỉ nhận một đối số |
| `route(new int[]{5,6})` | 1 | `route(int...)` như fixed arity `int[]`, cụ thể hơn `Object` |
| `prefer(5)` | 1 | `prefer(long)`: widening, áp dụng trước varargs |
| `prefer()` | 3 | `prefer(int...)`: nhận 0 phần tử, `prefer(long)` cần một đối số |
| `numeric(5)` | 1 | `numeric(long)`: cả `long`, `float` nhận được `int`, nhưng `long` cụ thể hơn |

Ở đây một vài overload **được chọn trong pha 2** và **pha 3**, dù cả chương trình cùng chứa các phương thức có tên trùng nhau. Điều đó cho thấy quy tắc phải áp dụng **riêng từng lời gọi**, dựa trên kiểu tĩnh và số lượng đối số của chính lời gọi ấy.

### 6.1. Cẩn thận với kiểu tĩnh thay vì kiểu runtime

Với `pick(Object)` và `pick(Integer)`:

~~~java
Object x = Integer.valueOf(5);
System.out.println(pick(x));
~~~

Đoạn này được đặt trong `main` của `OverloadPhasesDemo`; kết quả là:

~~~text
Object
~~~

Compiler dùng **kiểu khai báo `Object` của biến `x`**, nên chọn `pick(Object)`. Nó không nhìn đối tượng runtime là `Integer` rồi chọn lại overload. Nếu cần gọi overload nhận `Integer`, lập trình viên phải có biểu thức mang kiểu tĩnh tương thích, ví dụ `Integer x = 5;`.

## 7. Varargs vừa là method nhận mảng, vừa hỗ trợ số đối số biến đổi

Lưu ví dụ riêng thành **`VarargsFormsDemo.java`**:

~~~java
public class VarargsFormsDemo {
    static String describe(Object value) {
        return "Object";
    }

    static String describe(String... values) {
        return values == null ? "String...:null"
                : "String...:" + values.length;
    }

    static String label(String name, String... tags) {
        return name + ":" + tags.length;
    }

    public static void main(String[] args) {
        System.out.println(describe("X"));
        System.out.println(describe(new String[] {"A", "B"}));
        System.out.println(describe("A", "B"));
        System.out.println(describe((String[]) null));

        System.out.println(label("no-tags"));
        System.out.println(label("with-tags", "a", "b"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac VarargsFormsDemo.java
java VarargsFormsDemo
~~~

Output:

~~~text
Object
String...:2
String...:2
String...:null
no-tags:0
with-tags:2
~~~

Phân tích:

- `describe("X")`: overload `describe(Object)` được áp dụng fixed arity pha 1 bằng widening reference `String` → `Object`; `describe(String...)` cần variable arity, nên chưa được xét.
- `describe(new String[]{"A","B"})`: biểu thức có kiểu `String[]`; cả `describe(Object)` và `describe(String[])` phù hợp fixed arity pha 1, nhưng `String[]` cụ thể hơn `Object`.
- `describe("A","B")`: hai đối số `String` nên chỉ dạng varargs của `describe(String...)` áp dụng ở pha 3.
- `describe((String[]) null)`: cast xác định đối số mang kiểu `String[]`, chọn overload nhận `String[]` ở fixed arity, nhưng giá trị thực là `null`. Thân method có kiểm tra null nên in `String...:null`.
- `label("no-tags")`: `name` nhận chuỗi, còn phần `tags` có 0 phần tử.
- `label("with-tags","a","b")`: hai phần tử dành cho `tags`.

Nếu bỏ cast và gọi `describe(null)`, trong trường hợp các khai báo này tồn tại, có thể nhận cảnh báo liên quan lời gọi varargs không chính xác và overload nhận `String[]` được chọn theo khả năng áp dụng fixed arity; tránh dựa vào một `null` không chỉ rõ kiểu vì dễ gây hiểu nhầm là “một phần tử null” hay “mảng null”. Nếu thực sự muốn **một phần tử String null**, có thể viết `describe((String) null)` để biểu thị rõ đối số dạng `String`. Khi đó, trong ví dụ có cả `describe(Object)`, kết quả chọn overload sẽ theo các pha áp dụng cố định đã giải thích ở trên.

## 8. Most-specific: phải xét sau khi xác định pha

Giả sử có hai overload:

~~~java
static String display(Object item) {
    return "Object";
}

static String display(CharSequence item) {
    return "CharSequence";
}
~~~

Lời gọi `display("hello")` đưa cả hai overload vào pha 1: `String` widening thành `Object` hoặc `CharSequence`. Vì `CharSequence` là subtype của `Object`, `display(CharSequence)` cụ thể hơn.

Tuy nhiên với:

~~~java
static String h(long x) { return "long"; }
static String h(Integer x) { return "Integer"; }
~~~

`h(5)` không đặt hai overload vào cùng pha để so “most-specific”, bởi `h(long)` đã áp dụng pha 1 còn `h(Integer)` chỉ áp dụng pha 2. **Chọn pha** xảy ra trước **so mức cụ thể**.

### 8.1. Hai overload cùng áp dụng mà không có cái cụ thể nhất

Ví dụ:

~~~java
static void accept(String value) { }
static void accept(Integer value) { }
~~~

Cả hai là phương thức hợp lệ và đều có một tham số tham chiếu. Nhưng lời gọi:

~~~java
// accept(null); // Lỗi biên dịch: reference to accept is ambiguous
~~~

`null` có thể chuyển thành cả `String` và `Integer`, mà hai kiểu này không có quan hệ subtype với nhau. Compiler không chọn tùy ý theo thứ tự khai báo. Nếu API thực sự cần gọi với null, phải chỉ rõ mục đích:

~~~java
accept((String) null);
accept((Integer) null);
~~~

Các dòng trên là đoạn minh họa đặt trong class có hai overload `accept`. **Cast làm rõ kiểu của biểu thức**, không làm `null` trở thành đối tượng không null; thân phương thức vẫn cần tuân thủ hợp đồng xử lý null.

### 8.2. Hai overload varargs có thể mơ hồ

Nếu có:

~~~java
static void log(int... numbers) { }
static void log(Integer... numbers) { }
~~~

Lời gọi `log()` không có đối số cho phần biến độ dài, nên cả hai varargs methods đều có thể áp dụng ở pha 3. Trong trường hợp này Java không chọn được một overload cụ thể nhất và báo **ambiguous method call**.

Hãy viết `log(new int[0])` hoặc `log(new Integer[0])` khi cần chọn rõ phiên bản tương ứng. Đoạn hai khai báo là ví dụ hợp lệ nếu cùng nằm trong lớp; **lời gọi trống mới là chỗ mơ hồ**.

### 8.3. Nếu một pha đã có ứng viên nhưng kết quả mơ hồ

Compiler **không dùng pha 2 hoặc pha 3 để cứu** một lời gọi mơ hồ đã phát sinh trong pha áp dụng trước đó. Trình tự đúng là chọn tập ứng viên của **pha đầu tiên có kết quả áp dụng**, rồi giải quyết most-specific tại đó. Nếu không xác định được duy nhất thì lỗi.

Lý do quan trọng về mặt thiết kế API: thêm một overload khác **không luôn làm lời gọi rõ hơn**; có thể vô tình khiến những lời gọi `null`, lambda hoặc generic expression từng hợp lệ trở nên mơ hồ.

## 9. Generic methods và type inference trong các pha

Với generic method:

~~~java
static <T extends Number> String inspect(T value) {
    return "number";
}
~~~

Gọi `inspect(5)` có thể hợp lệ nhờ boxing `int` thành `Integer` và suy luận `T` tương ứng. Nếu trong cùng lớp còn có overload `inspect(long)`, thì `inspect(5)` có thể chọn `inspect(long)` ở pha 1 trước khi cần phiên bản generic nhận wrapper. Không nên mặc định “generic luôn được ưu tiên” hay “generic luôn bị loại”.

Việc suy luận type parameter còn liên quan đến ràng buộc `extends`, kiểu tĩnh đối số, kiểu kỳ vọng (*target typing*) trong một số biểu thức, lambda và method references. Vì vậy những ví dụ phức tạp có thể không quyết định được chỉ bằng cách đếm số lần boxing.

### 9.1. Generic argument không tạo overload độc lập nếu bị erasure trùng

Hai khai báo sau không thể cùng tồn tại trong một lớp:

~~~java
// Không hợp lệ nếu khai báo đồng thời:
// void use(java.util.List<String> values) { }
// void use(java.util.List<Integer> values) { }
~~~

Lý do là **type erasure** khiến cả hai có cùng dạng tham số thô `List` cho mục đích kiểm tra name clash. Điều này khác với việc một lời gọi cụ thể phải được kiểm tra kiểu đối số. Đừng định nghĩa hai overload chỉ khác `List<String>` và `List<Integer>`.

### 9.2. Không có mọi chuyển đổi generic ngầm định

`List<Integer>` không tự chuyển thành `List<Number>`, dù `Integer` là subtype của `Number`. Java generics thường **invariant**. Nếu chỉ cần đọc các số có thể cân nhắc `List<? extends Number>`; nếu cần thêm giá trị `Integer` có thể xét `List<? super Integer>`. Đây là ràng buộc kiểu độc lập với thứ tự xét boxing và varargs.

## 10. Bốn tình huống dễ nhầm liên quan boxing

### 10.1. `int` không tự thành `Long`

~~~java
static void take(Long number) { }

// take(10);   // Sai: int không tự widening rồi boxing thành Long
take(10L);     // Hợp lệ: long boxing thành Long
~~~

Các dòng minh họa đặt trong class và method thích hợp. Cũng có thể tạo đối tượng bằng `Long.valueOf(10)` nếu cần.

### 10.2. `Integer` có thể unboxing rồi widening thành `long`

~~~java
static void takeLong(long number) {
    System.out.println(number);
}

// Trong method:
Integer value = 5;
takeLong(value);
~~~

Đoạn minh họa hợp lệ. Kiểu đối số `Integer` được chuyển qua `int` rồi widening sang `long` theo loose invocation; chú ý `null` có thể gây NPE khi unboxing.

### 10.3. `int` có thể boxing rồi widening reference thành `Object`

~~~java
static void takeObject(Object object) {
    System.out.println(object);
}

// Trong method:
takeObject(5);
~~~

Lời gọi hợp lệ nhờ `int` → `Integer` → `Object`. Nếu cùng lúc có overload `takeObject(Integer)` thì phải áp dụng quy tắc most-specific trong pha phù hợp; không dựa vào số bước một cách tùy tiện.

### 10.4. Literal số nguyên không tự narrowing khi truyền tham số

~~~java
static void takeByte(byte value) {
    System.out.println(value);
}

// takeByte(5);        // Sai ở lời gọi method: literal có kiểu int
takeByte((byte) 5);    // Hợp lệ: cast biểu thức tường minh
~~~

`byte x = 5;` có thể biên dịch do **quy tắc gán hằng số nguyên** nhưng không thay đổi quy tắc method invocation conversion.

## 11. Tránh xung đột khi thiết kế overload

Quy tắc ba pha giúp giải thích chương trình, nhưng khi thiết kế API, đừng ép người đọc phải tính nhiều pha cho một lời gọi đơn giản.

Các gợi ý thực tế:

1. **Ưu tiên overload có ý nghĩa rõ**: khác số tham số hoặc khác vai trò dữ liệu; nếu chỉ khác primitive/wrapper, cân nhắc có thực sự cần cả hai không.
2. **Tránh overload `String` và `Integer` nếu người gọi hay truyền null**: có thể sinh ambiguity hoặc ý nghĩa khó dự đoán.
3. **Đặt varargs ở vị trí cuối** và mô tả hợp đồng khi nhận 0, 1 hay nhiều phần tử; nếu caller có thể truyền null, cần phân biệt **mảng null** với **mảng chứa phần tử null**.
4. **Không dựa vào cast vô nghĩa** để ép overload khác nếu API có thể được đặt tên rõ ràng hơn; cast có thể che giấu sai kiểu và gây lỗi runtime.
5. **Giữ kiểu tĩnh phản ánh đúng dữ liệu**: biến khai báo `Object` không giúp compiler tự chọn overload `String` dựa trên đối tượng runtime là `String`.
6. **Có kiểm thử hành vi khi thêm overload mới**, nhất là API public đã có người dùng. Một overload được bổ sung có thể thay đổi overload được chọn khi biên dịch lại source code.
7. **Nhớ boxing/unboxing có chi phí và rủi ro null**: ở mã hiệu năng cao, tránh tạo wrapper không cần thiết; ở API nhận `Integer`, quy định rõ có chấp nhận null không.

### 11.1. Một ví dụ gây thay đổi kết quả khi thêm overload

Ban đầu chỉ có:

~~~java
static String parse(long x) {
    return "long";
}
~~~

Lời gọi `parse(5)` chọn `parse(long)`. Nếu sau đó bổ sung:

~~~java
static String parse(int x) {
    return "int";
}
~~~

lời gọi `parse(5)` khi được **biên dịch lại** sẽ chọn `parse(int)` (identity thay vì widening trong cùng pha 1). Mã vẫn có thể biên dịch nhưng hành vi mới khác. Khi thiết kế API, việc thêm overload là thay đổi có thể ảnh hưởng các call sites, nên cần kiểm thử phù hợp.

## 12. Checklist suy luận từng lời gọi

Khi thấy một lời gọi `service.calculate(args...)` và có nhiều overload:

1. **Liệt kê các overload cùng tên có thể truy cập** trong kiểu tĩnh của receiver và các kiểu liên quan.
2. **Xác định kiểu tĩnh của từng đối số**, không đoán từ giá trị runtime. Literal `5` thường là `int`, `5L` là `long`, `Integer.valueOf(5)` là `Integer`.
3. **Đếm số đối số thực sự**: một mảng `new int[]{1,2}` là **một** đối số kiểu `int[]`, khác hai đối số `1,2`.
4. **Xét fixed arity pha 1**: có overload nào khớp mà không boxing/unboxing không? Nếu có, tìm most-specific trong tập đó.
5. **Chỉ khi pha 1 rỗng, xét fixed arity pha 2**: boxing, unboxing và các chuỗi chuyển đổi hợp lệ. Nếu có ứng viên, tìm most-specific.
6. **Chỉ khi cả hai pha rỗng, xét varargs pha 3**: các tham số cố định cần khớp; phần còn lại được xét như các phần tử mảng phù hợp.
7. **Nếu nhiều ứng viên cùng pha**, xét most-specific, generic inference và những quy tắc đặc thù. Nếu không chọn được duy nhất thì lời gọi ambiguous.
8. **Sau khi chọn overload**, mới nghĩ đến thực thi runtime và (nếu là instance method) khả năng dispatch tới bản override; `null`, unboxing và hành vi thân method vẫn có thể gây exception.

Sơ đồ đơn giản có thể kiểm tra nhanh:

~~~text
f(5) với f(long) và f(Integer)
  int -> long (pha 1)      => chọn long
  int -> Integer (pha 2)   => không xét tiếp

f(5) với f(Object) và f(int...)
  int -> Integer -> Object (pha 2) => chọn Object
  int -> phần tử int... (pha 3)    => không xét tiếp

f(new int[]{5}) với f(Object) và f(int...)
  int[] -> Object (pha 1)
  int[] -> int[] (pha 1, dạng fixed arity)
  => chọn f(int...) do int[] cụ thể hơn Object
~~~

## 13. Những lỗi phổ biến và cách sửa

| Nhầm lẫn / lỗi | Giải thích đúng |
| --- | --- |
| “Autoboxing được ưu tiên trước widening.” | Sai. Pha strict có widening được xét trước pha loose có boxing. |
| “Nếu có method `f(Integer)`, `f(5)` luôn chọn nó.” | Chỉ khi không có ứng viên áp dụng ở pha sớm hơn và quy tắc most-specific chọn nó. |
| “Java thử tất cả rồi chọn overload cần ít chuyển đổi nhất.” | Không phải thuật toán ngôn ngữ. Phải xét ba pha và most-specific. |
| “Method varargs luôn bị xét ở pha 3.” | Sai nếu đối số đã là mảng phù hợp: varargs method có thể tham gia pha fixed arity. |
| “Fixed arity luôn thắng varargs theo tên phương thức.” | Cần xét **pha áp dụng** của từng lời gọi và dạng fixed/variable arity của varargs method. |
| “`int` tự thành `Long` nhờ widening rồi boxing.” | Chuỗi widening primitive rồi boxing không được phép ngầm trong method invocation thông thường. |
| “`Integer` không thể truyền vào `long`.” | Có thể unboxing `Integer` → `int`, rồi widening → `long` ở pha loose. |
| “`f(byte)` nhận `f(10)` vì 10 nhỏ.” | Không có narrowing của literal `int` tại method invocation như trong phép gán hằng. |
| “Hai overload `f(String)` và `f(Integer)` sẽ chọn một khi gọi `f(null)`.” | Không: với hai kiểu không có quan hệ subtype tương ứng, lời gọi mơ hồ. |
| “Varargs luôn là một đối số riêng lẻ.” | Ở dạng variable arity, nhiều giá trị có thể được đóng gói vào mảng; ở dạng fixed arity, một mảng sẵn có được truyền trực tiếp. |
| “Compiler chọn overload theo object runtime.” | Chọn overload ở compile time dựa trên kiểu tĩnh; dynamic dispatch chọn override sau đó. |
| “Dùng `List<String>` và `List<Integer>` tạo hai overload hợp lệ.” | Type erasure gây name clash; cần tên/thiết kế API khác. |
| “`null` unboxing được thành `0`.” | Unboxing null gây `NullPointerException` ở runtime. |

## 14. Bài luyện tập tự giải

**Câu 1.** Có `f(long)` và `f(Integer)`. Gọi `f(3)` chọn phương thức nào?  
**Đáp án:** `f(long)`. Literal `3` có kiểu `int`, widening `int` → `long` ở pha 1 nên không xét boxing ở pha 2.

**Câu 2.** Có `f(Object)` và `f(Integer)`. Gọi `f(3)` chọn phương thức nào?  
**Đáp án:** `f(Integer)`. Cả hai cần boxing và áp dụng ở pha 2; `Integer` cụ thể hơn `Object`.

**Câu 3.** Có `f(Object)` và `f(int...)`. Gọi `f(3)` chọn overload nào?  
**Đáp án:** `f(Object)`, do boxing rồi reference widening làm nó áp dụng ở pha 2, trước lời gọi variable arity ở pha 3.

**Câu 4.** Vẫn hai overload ở câu 3, nhưng gọi `f(new int[]{3})` thì sao?  
**Đáp án:** `f(int...)` được chọn ở pha 1 như một lời gọi fixed arity nhận `int[]`; nó cụ thể hơn `f(Object)`.

**Câu 5.** Có `f(long)` và `f(float)`. Gọi `f(3)` chọn gì?  
**Đáp án:** `f(long)`. Cả hai áp dụng ở pha 1, nhưng `long` cụ thể hơn `float` theo primitive widening.

**Câu 6.** Chỉ có `f(Long)`. Gọi `f(3)` có biên dịch không?  
**Đáp án:** Không. `int` không tự widening thành `long` rồi boxing thành `Long`. Dùng `3L`, `(long) 3` hoặc đối tượng `Long` phù hợp.

**Câu 7.** Chỉ có `f(long)`. Truyền biến `Integer value = 3;` vào `f(value)` có hợp lệ không?  
**Đáp án:** Có. Pha loose invocation có thể unboxing `Integer` thành `int` rồi widening thành `long`. Nếu `value == null`, runtime có thể ném NPE.

**Câu 8.** Có `f(String)` và `f(Integer)`. Gọi `f(null)` ra sao?  
**Đáp án:** Lỗi ambiguous. Có thể viết `f((String) null)` hoặc `f((Integer) null)` nếu hợp đồng API thật sự cho phép null.

**Câu 9.** Có `f(int...)` và `f(Integer...)`. Vì sao `f()` có thể mơ hồ?  
**Đáp án:** Cả hai nhận được 0 phần tử ở pha 3, nhưng kiểu mảng/kiểu phần tử không tạo một ứng viên cụ thể nhất duy nhất trong trường hợp đó.

**Câu 10.** Một method `void send(String... parts)` nhận `send(new String[]{"A","B"})` bằng pha nào?  
**Đáp án:** Pha 1, khi xét như lời gọi fixed arity một tham số `String[]`; không cần tạo một mảng varargs mới.

**Câu 11.** Nếu `Object o = Integer.valueOf(1)` và có hai overload `g(Object)`, `g(Integer)`, thì `g(o)` chọn overload nào?  
**Đáp án:** `g(Object)`, vì kiểu tĩnh của biểu thức `o` là `Object`, không phải `Integer`.

**Câu 12.** Một overload pha 1 đang hợp lệ, nhưng trong pha 2 tồn tại overload trả về kiểu mà bên gọi muốn. Java có chuyển sang pha 2 để chọn kiểu trả về đó không?  
**Đáp án:** Không. Return type không tự tạo overload khác cho cùng chữ ký; và compiler không bỏ qua ứng viên pha 1 để tìm overload pha 2 chỉ vì kiểu trả về trông thuận tiện hơn. Generic target typing có các quy tắc riêng, nhưng không đảo thứ tự xét ba pha.

## Tài liệu tham khảo

- [Java Language Specification §15.12.2 — Compile-Time Step 2: Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2), đặc biệt §§15.12.2.2–15.12.2.5 về **strict invocation**, **loose invocation**, **variable arity invocation** và **most-specific**.
- [Java Language Specification §5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.3) để phân biệt các chuyển đổi được phép trong lời gọi với assignment/casting conversion.
- [Java Language Specification §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1), đặc biệt phần tham số biến độ dài.

## Ghi nhớ

Java giải quyết overload theo **thứ tự pha**: **(1) fixed arity với strict invocation**, **(2) fixed arity cho phép boxing/unboxing**, **(3) variable arity cho varargs**. Chỉ khi pha trước không có ứng viên áp dụng, compiler mới xét pha sau; trong pha đã chọn, Java dùng quy tắc **most-specific** chứ không dựa trên độ dài tên hay số lượng phép chuyển đổi tưởng tượng. Vì thế `int` → `long` có thể thắng `int` → `Integer`, boxing thành `Object` có thể thắng một lời gọi varargs, còn varargs method nhận sẵn một mảng có thể tham gia ngay pha 1. Nắm đúng những nguyên tắc này giúp chọn overload nhất quán, hiểu compiler errors và thiết kế API dễ dùng.
