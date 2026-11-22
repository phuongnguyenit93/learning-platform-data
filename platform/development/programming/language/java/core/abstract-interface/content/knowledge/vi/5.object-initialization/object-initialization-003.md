# Thứ tự khởi tạo thuộc tính, khối khởi tạo và constructor trong Java

## 1. Quy tắc cần nhớ

Khi tạo một đối tượng Java bằng `new`, các thành phần khởi tạo **không chạy theo thứ tự tùy ý**. Đối với một lớp cụ thể có thể khởi tạo, trình tự cốt lõi là:

1. **Khởi tạo lớp (nếu chưa xảy ra):** các bộ khởi tạo `static` cần thiết được thực hiện, với lớp cha được khởi tạo trước lớp con.
2. **Cấp phát đối tượng và đặt giá trị mặc định:** các trường instance có giá trị ban đầu như `0`, `false`, `null`; đó chưa phải giá trị được viết bằng biểu thức khởi tạo trường.
3. **Chạy chuỗi constructor từ lớp con lên lớp cha để tìm điểm bắt đầu:** constructor con gọi `super(...)` hoặc `this(...)`; việc thực thi constructor của tổ tiên diễn ra trước phần khởi tạo instance của lớp con.
4. **Trong từng lớp, sau khi constructor lớp cha kết thúc:** chạy các biểu thức khởi tạo trường instance và các khối khởi tạo instance của lớp hiện tại **theo thứ tự xuất hiện trong mã nguồn**, sau đó chạy phần thân constructor hiện tại.
5. **Hoàn thành lớp con cuối cùng:** khi constructor của lớp được `new` kết thúc, đối tượng mới hoàn tất quá trình khởi tạo thông thường.

Với quan hệ `Parent` → `Child` và không có ủy quyền constructor phức tạp, thứ tự dễ nhớ là:

```text
Khởi tạo static cần thiết (Parent trước Child, một lần mỗi lớp)
    ↓
Cấp phát + giá trị mặc định cho toàn bộ trường instance
    ↓
Object constructor
    ↓
Parent: field initializer / instance initializer block (thứ tự trong mã)
    ↓
Parent: constructor body
    ↓
Child: field initializer / instance initializer block (thứ tự trong mã)
    ↓
Child: constructor body
    ↓
new Child() trả về tham chiếu đối tượng
```

Sơ đồ này diễn tả trường hợp thông thường. Nếu constructor gọi `this(...)`, nó chuyển sang một constructor khác **cùng lớp** trước; các field initializer và instance initializer của lớp đó chỉ chạy **một lần** trên mỗi đối tượng. Ngoài ra, static initializer có thể đã chạy từ một lần sử dụng lớp trước đó; nó **không nhất thiết chạy ngay trong lần `new` đang quan sát**.

## 2. Ba loại thành phần dễ nhầm lẫn

| Thành phần | Ví dụ | Khi nào thực thi? |
| --- | --- | --- |
| Khởi tạo trường instance | `int count = 10;` | Mỗi lần đối tượng của lớp hoặc lớp con được tạo, ở pha khởi tạo instance của lớp khai báo trường |
| Khối khởi tạo instance | `{ count++; }` | Mỗi lần khởi tạo đối tượng, xen với field initializer theo thứ tự xuất hiện trong mã nguồn |
| Constructor | `Example() { ... }` | Chạy khi constructor tương ứng được gọi trong chuỗi khởi tạo đối tượng, sau pha khởi tạo instance của lớp có constructor đó |
| Khởi tạo trường static | `static int limit = 100;` | Khi lớp được khởi tạo, không lặp lại trên từng đối tượng |
| Khối khởi tạo static | `static { ... }` | Trong pha khởi tạo lớp, xen với các static field initializer theo thứ tự xuất hiện trong mã nguồn |

Hai nguyên tắc đặc biệt quan trọng:

- **Các thành phần instance trong cùng một lớp được xen kẽ theo thứ tự văn bản.** Không có quy tắc “khởi tạo hết tất cả field, rồi mới chạy tất cả instance block”. Nếu trong mã một instance block nằm giữa hai field initializer, nó chạy giữa hai initializer đó.
- **Static và instance là hai chuỗi riêng.** Một `static` block đặt cuối tệp không vì thế chạy sau constructor; khi khởi tạo lớp, các thành phần `static` của lớp chạy theo thứ tự tương ứng trước quá trình tạo đối tượng đầu tiên kích hoạt khởi tạo lớp ấy.

Các trường khai báo nhưng không có initializer, như `int count;`, cũng nhận giá trị mặc định ngay khi bộ nhớ đối tượng được chuẩn bị. Chúng không có một bước gán trong thứ tự field initializer của mã nguồn, trừ khi được gán trong block/constructor.

## 3. Thí nghiệm 1: thứ tự field initializer, instance block và constructor của cùng lớp

Chương trình hoàn chỉnh dưới đây chạy được với Java 17 trở lên.

**Tệp `Main.java`:**

```java
public class Main {
    private int first = mark("1. initialize first", 10);

    {
        System.out.println("2. instance block A; first = " + first);
    }

    private int second = mark("3. initialize second", 20);

    {
        System.out.println("4. instance block B; second = " + second);
    }

    Main() {
        System.out.println("5. constructor; first = "
                + first + ", second = " + second);
    }

    private int mark(String message, int value) {
        System.out.println(message);
        return value;
    }

    public static void main(String[] args) {
        new Main();
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác:**

```text
1. initialize first
2. instance block A; first = 10
3. initialize second
4. instance block B; second = 20
5. constructor; first = 10, second = 20
```

Giải thích:

1. Bộ nhớ của `Main` đã được chuẩn bị; `first` và `second` ban đầu đều có giá trị mặc định `0`.
2. Field initializer của `first` gọi `mark(...)`, in dòng 1 rồi trả về `10`.
3. Khối instance A chạy ở đúng vị trí được khai báo, thấy `first == 10` và in dòng 2.
4. Field initializer của `second` chạy tiếp, in dòng 3 và gán `20`.
5. Khối instance B in dòng 4; cuối cùng phần thân `Main()` in dòng 5.

Hàm `mark` chỉ giúp nhìn rõ thứ tự; bản thân phương thức này không được Java gọi tự động. Java gọi **biểu thức khởi tạo** chứa `mark`.

**Thử thay đổi:** di chuyển khối B lên trước khai báo `second` và thay việc đọc `second` trong khối bằng một lời gọi phương thức đọc giá trị `second`. Khi đó nó có thể quan sát giá trị mặc định `0`. Trong Java, việc tham chiếu trực tiếp một trường instance bằng tên đơn giản ở một initializer nằm trước khai báo trường đó còn có thể gặp quy tắc **illegal forward reference**; đó là kiểm tra về mã nguồn, khác với hiện tượng trường chưa được gán giá trị mong muốn.

## 4. Giá trị mặc định tồn tại trước khi initializer chạy

Đây là điểm quyết định để hiểu những đầu ra gây bất ngờ: tất cả trường instance của đối tượng đều có giá trị mặc định trước khi chuỗi constructor xử lý initializer.

| Kiểu trường | Giá trị mặc định |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` tương ứng với kiểu |
| `float`, `double` | `0.0` tương ứng với kiểu |
| `char` | `'\u0000'` (ký tự NUL) |
| `boolean` | `false` |
| Kiểu tham chiếu như `String`, mảng, đối tượng | `null` |

**Ví dụ độc lập, tệp `Main.java`:**

```java
public class Main {
    private int observed = readLater();
    private int later = 42;

    private int readLater() {
        return later;
    }

    Main() {
        System.out.println("observed = " + observed);
        System.out.println("later = " + later);
    }

    public static void main(String[] args) {
        new Main();
    }
}
```

Chạy `javac -encoding UTF-8 Main.java` rồi `java Main`:

```text
observed = 0
later = 42
```

Khi biểu thức `observed = readLater()` được thực thi, trường `later` đã tồn tại nhưng **chưa đến lượt** biểu thức `later = 42`. Phương thức `readLater()` đọc giá trị mặc định `0`; sau đó `later` mới được gán `42`. Đây là hành vi hợp lệ và nhất quán.

Lưu ý: ví dụ gọi qua một phương thức để minh họa giá trị mặc định. Viết trực tiếp `private int observed = later;` trước khai báo `later` có thể bị lỗi `illegal forward reference`; không nên nhầm lỗi đó với quy tắc giá trị mặc định.

## 5. Thí nghiệm 2: có kế thừa thì lớp cha khởi tạo instance trước lớp con

Xét hai lớp `Parent` và `Child`. Mỗi lớp có field initializer, instance block và constructor.

**Tệp `Main.java`:**

```java
class Parent {
    int parentValue = trace("1. Parent field", 10);

    {
        System.out.println("2. Parent instance block");
    }

    Parent() {
        System.out.println("3. Parent constructor");
    }

    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }
}

class Child extends Parent {
    int childValue = trace("4. Child field", 20);

    {
        System.out.println("5. Child instance block");
    }

    Child() {
        // super(); được trình biên dịch chèn ngầm tại đây trong Java 17.
        System.out.println("6. Child constructor");
    }
}

public class Main {
    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("7. values = "
                + child.parentValue + ", " + child.childValue);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác:**

```text
1. Parent field
2. Parent instance block
3. Parent constructor
4. Child field
5. Child instance block
6. Child constructor
7. values = 10, 20
```

Điểm then chốt là constructor `Child()` gọi constructor `Parent()` trước. Khi `Parent()` thực sự thực thi, Java chạy các instance initializer của `Parent` theo thứ tự xuất hiện rồi mới đến phần thân `Parent()`. Sau khi phần của cha xong, Java mới chạy các initializer của `Child` rồi phần thân `Child()`.

Nếu `Parent` còn kế thừa một lớp khác, trình tự khởi tạo instance tiếp tục đi từ tổ tiên cao hơn xuống lớp con. Thông thường constructor của `Object` là điểm đầu của chuỗi này; ví dụ không in bước của `Object`.

### Khi constructor cha nhận tham số

Nếu `Parent` chỉ khai báo `Parent(String name)`, constructor `Child` phải gọi constructor cha phù hợp, ví dụ `super("Mimi");`. Java **không tự sinh ra** constructor không tham số trong `Parent` khi lớp đó đã có constructor do lập trình viên khai báo. Việc thiếu lời gọi `super(...)` phù hợp gây lỗi biên dịch về constructor, không thay đổi quy tắc thứ tự khởi tạo.

Trong Java 17, lời gọi `super(...)` hoặc `this(...)` tường minh phải là statement đầu tiên của constructor; hai lệnh này không thể xuất hiện đồng thời để gọi trực tiếp trong cùng một constructor.

## 6. Thí nghiệm 3: `this(...)` không làm chạy initializer hai lần

Một lớp có thể có nhiều constructor. Khi một constructor gọi `this(...)`, nó **ủy quyền** cho constructor khác của cùng lớp. Phần field initializer và instance block vẫn chỉ cần chạy **một lần** cho đối tượng đang được tạo.

**Tệp `Main.java`:**

```java
class Sample {
    private int value = report("1. field initializer");

    {
        System.out.println("2. instance block");
    }

    Sample() {
        this(5);
        System.out.println("4. no-arg constructor body");
    }

    Sample(int number) {
        System.out.println("3. int constructor body: " + number);
    }

    private static int report(String message) {
        System.out.println(message);
        return 100;
    }
}

public class Main {
    public static void main(String[] args) {
        new Sample();
    }
}
```

Chạy `javac -encoding UTF-8 Main.java` và `java Main`:

```text
1. field initializer
2. instance block
3. int constructor body: 5
4. no-arg constructor body
```

Trình tự thực tế:

1. `new Sample()` chọn constructor không tham số.
2. Câu lệnh đầu tiên của constructor ấy là `this(5)`, chuyển tới `Sample(int)`.
3. Vì `Sample(int)` không gọi một constructor cùng lớp khác, nó thực hiện lời gọi `super()` ngầm, rồi các instance initializer của `Sample` chạy theo thứ tự khai báo, sau đó phần thân `Sample(int)`.
4. Quyền điều khiển quay về `Sample()` và chạy phần còn lại của constructor này.

Không có lần thứ hai in `field initializer` hoặc `instance block`. Một chuỗi `this(...)` phải kết thúc ở constructor gọi `super(...)` (tường minh hoặc ngầm định), không được tạo vòng lặp gọi constructor vô tận.

## 7. Thí nghiệm 4: static initializer và instance initializer khác nhau ra sao?

`static` thuộc về **lớp**, không thuộc riêng một đối tượng. Các biểu thức khởi tạo `static` field và khối `static` được thực thi theo thứ tự xuất hiện trong mỗi lớp **khi lớp được khởi tạo**. Khi lớp con được khởi tạo, Java đảm bảo các lớp cha thích hợp đã được khởi tạo trước.

Trong khi đó, initializer instance chạy lại cho **mỗi đối tượng** mới.

**Tệp `Main.java`:**

```java
class Parent {
    static int sharedParent = log("Parent static field");

    static {
        log("Parent static block");
    }

    int instanceParent = log("Parent instance field");

    {
        log("Parent instance block");
    }

    Parent() {
        log("Parent constructor");
    }

    static int log(String message) {
        System.out.println(message);
        return 1;
    }
}

class Child extends Parent {
    static int sharedChild = log("Child static field");

    static {
        log("Child static block");
    }

    int instanceChild = log("Child instance field");

    {
        log("Child instance block");
    }

    Child() {
        log("Child constructor");
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println("-- first --");
        new Child();
        System.out.println("-- second --");
        new Child();
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout chính xác khi chạy chương trình này trong JVM mới:**

```text
-- first --
Parent static field
Parent static block
Child static field
Child static block
Parent instance field
Parent instance block
Parent constructor
Child instance field
Child instance block
Child constructor
-- second --
Parent instance field
Parent instance block
Parent constructor
Child instance field
Child instance block
Child constructor
```

Ở lần `new Child()` đầu tiên, `Parent` và `Child` chưa được khởi tạo, nên chuỗi static của lớp cha rồi lớp con chạy trước chuỗi instance. Ở lần thứ hai, lớp đã khởi tạo và **không thực hiện lại** các static initializer; mỗi đối tượng mới vẫn chạy lại chuỗi instance và constructor.

Có một ngoại lệ cần hiểu về **thời điểm quan sát**: lớp có thể đã được khởi tạo sớm hơn do một thao tác sử dụng chủ động khác (ví dụ truy cập một static field không phải hằng số tại thời điểm biên dịch, gọi static method hoặc dùng `Class.forName` theo cách khởi tạo lớp). Vì thế, các dòng static sẽ không nhất thiết xuất hiện tại lệnh `new` đầu tiên trong một chương trình lớn. Truy cập một hằng `static final` là biểu thức hằng tại thời điểm biên dịch cũng có quy tắc kích hoạt riêng.

Không nên suy luận thứ tự thực thi `static` và instance từ việc dòng khai báo nào xuất hiện trước trong cả tệp. Hãy xác định **giai đoạn khởi tạo lớp** và **giai đoạn khởi tạo đối tượng** trước, rồi xét thứ tự trong từng giai đoạn.

## 8. Thứ tự gán giá trị nếu cùng một trường được gán nhiều lần

Giá trị cuối của trường là giá trị sau lần gán cuối cùng **trong luồng khởi tạo đã thực sự chạy**.

**Ví dụ độc lập, tệp `Main.java`:**

```java
public class Main {
    private int level = 1;

    {
        level = 2;
    }

    Main() {
        level = 3;
    }

    public static void main(String[] args) {
        System.out.println(new Main().level);
    }
}
```

Kết quả khi chạy `javac -encoding UTF-8 Main.java` và `java Main`:

```text
3
```

Đối tượng nhận `level = 0` mặc định, rồi lần lượt `1` ở field initializer, `2` trong instance block, và `3` trong constructor. Việc đặt giá trị ở constructor thường dùng khi giá trị phụ thuộc tham số lúc tạo đối tượng; field initializer hợp với giá trị mặc định cố định; instance block phù hợp với logic chung giữa các constructor nhưng nên dùng thận trọng vì dễ làm luồng khởi tạo khó đọc.

Với **blank final instance field** (trường `final` không gán ngay tại khai báo), Java yêu cầu trường được gán đúng theo quy tắc definite assignment trước khi constructor hoàn tất. Có thể gán nó trong instance initializer hoặc constructor phù hợp, nhưng không thể tự do ghi đè nhiều lần như ví dụ `level` không có `final`. Giá trị `final` có sẵn initializer tại khai báo thì không được gán lại trong constructor.

## 9. Phương thức override có thể chạy khi trường lớp con còn mặc định

Chú ý một trường hợp dễ sai khi dự đoán thứ tự stdout: nếu constructor `Parent` gọi một phương thức instance có thể override, Java vẫn dispatch đến implementation ở `Child`, dù initializer của `Child` chưa chạy. Giả sử `Child` khai báo `String label = "READY"` và override `describe()` để đọc `label`, còn `Parent()` gọi `describe()`.

| Thời điểm | Giá trị `Child.label` khi `describe()` đọc |
| --- | --- |
| Trong phần thân `Parent()` | `null` (giá trị mặc định, chưa chạy initializer của Child) |
| Sau khi `new Child()` hoàn tất | `"READY"` |

**Thứ tự khởi tạo vẫn giữ nguyên**; chính cơ chế dynamic dispatch khiến logic lớp con chạy sớm. Khi phân tích ví dụ có gọi phương thức từ constructor, hãy thêm bước kiểm tra override vào sơ đồ thứ tự. Bài “Rủi ro gọi phương thức có thể bị ghi đè trong constructor” cung cấp chương trình tái hiện, những kiểu lỗi và hướng thiết kế an toàn.

## 10. Checklist tự dự đoán đầu ra trước khi chạy

Với bài tập yêu cầu tìm thứ tự dòng in khi khởi tạo đối tượng, có thể giải theo quy trình sau:

1. **Xác định lệnh tạo đối tượng và kiểu thực tế sau `new`.** Ví dụ `Parent p = new Child();` vẫn tạo **đối tượng Child**, nên chuỗi khởi tạo của `Child` được dùng.
2. **Xác định những lớp nào chưa được khởi tạo static.** Nếu chưa, thực hiện static initializer theo thứ tự lớp cha trước lớp con; trong mỗi lớp, static field initializer và static block xen kẽ theo mã nguồn.
3. **Tạm ghi giá trị mặc định cho mọi trường instance.** Việc có `int x = 7` không có nghĩa ngay từ đầu `x` đã là `7`.
4. **Vẽ chuỗi `this(...)` / `super(...)`.** Tìm constructor cuối cùng của mỗi chuỗi ủy quyền và phần thân nào sẽ chạy khi các lời gọi quay về.
5. **Ở từng lớp từ cha đến con:** chạy instance field initializer và instance block theo đúng thứ tự xuất hiện, rồi phần thân constructor liên quan.
6. **Nếu một phương thức overridable được gọi**, xét lớp triển khai được chọn bằng dynamic dispatch và trạng thái của các trường **ngay tại thời điểm gọi**.
7. **Tách các đối tượng khác nhau.** Lần `new` mới chạy lại phần instance, nhưng không chạy lại static initializer của lớp đã được khởi tạo.

### Những ngộ nhận thường gặp

- “Field initializer nào cũng chạy trước mọi instance block.” **Sai:** cùng lớp, chúng được xen kẽ theo thứ tự khai báo.
- “Constructor con chạy trước vì `new Child()`.” **Sai:** constructor cha hoàn tất phần khởi tạo của nó trước pha khởi tạo instance và phần thân constructor con.
- “`this(...)` làm gọi hai constructor nên khối instance chạy hai lần.” **Sai:** chỉ có một đối tượng; initializer của lớp chạy một lần, dù nhiều phần thân constructor có thể chạy khi quay về.
- “Static initializer chạy khi mỗi đối tượng được tạo.” **Sai:** chạy một lần trong quá trình khởi tạo lớp, ở thời điểm do quy tắc kích hoạt khởi tạo lớp quyết định.
- “Biểu thức gán trong khai báo field có hiệu lực trước constructor cha.” **Sai:** trường lớp con còn giữ giá trị mặc định khi constructor cha đang chạy.
- “Gọi phương thức override từ constructor cha sẽ thấy lớp con đã sẵn sàng.” **Sai:** ví dụ `label = null` chứng minh trạng thái lớp con có thể chưa hoàn tất.

## 11. Tóm tắt thứ tự thực thi

Hãy luôn phân biệt ba việc: **khởi tạo lớp static**, **chuẩn bị giá trị mặc định cho đối tượng**, và **khởi tạo instance theo chuỗi constructor**. Trong một lớp, field initializer và instance block chạy theo thứ tự xuất hiện trong mã nguồn; phần thân constructor chạy sau chúng. Khi có kế thừa, quá trình instance đi từ cha xuống con. Khi có `this(...)`, phần initializer của lớp chỉ chạy một lần. Nắm vững các quy tắc này giúp dự đoán chính xác stdout, tránh dùng trạng thái chưa khởi tạo và viết constructor dễ bảo trì hơn.
