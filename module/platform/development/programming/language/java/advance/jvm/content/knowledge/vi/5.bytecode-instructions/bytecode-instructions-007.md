# `new`, `newarray`, `anewarray` và `multianewarray` khi tạo dữ liệu trong JVM

## 1. Bốn opcode giải quyết bốn tình huống cấp phát

Trong mã nguồn Java, từ khóa `new` xuất hiện cả khi tạo một instance lẫn khi tạo mảng. Nhưng ở **bytecode JVM**, có nhiều lệnh tạo dữ liệu với trách nhiệm khác nhau. Cần phân biệt **từ khóa Java** và **opcode JVM**.

| Biểu thức Java | Opcode cấp phát thường thấy từ `javac` | Thứ được tạo |
| --- | --- | --- |
| `new Person("Lan")` | `new`, tiếp theo `invokespecial` để gọi `<init>` | Một đối tượng instance của class |
| `new int[3]` | `newarray` | Một đối tượng mảng có phần tử `int` |
| `new String[3]` | `anewarray` | Một đối tượng mảng có phần tử tham chiếu `String` |
| `new int[2][3]` | `multianewarray` | Outer array và các mảng con của hai chiều được chỉ định |
| `new int[2][]` | `anewarray` với component type `int[]` | Chỉ outer array; các hàng ban đầu `null` |

Bốn lệnh đều có thể **tạo đối tượng trên heap và đẩy một reference lên operand stack**. Khác biệt nằm ở kiểu đối tượng, cách mã hóa operand, số kích thước mảng được cung cấp và việc có cần gọi constructor instance sau cấp phát hay không.

```text
                      Cú pháp Java dùng new
                                |
             +------------------+------------------+
             |                                     |
      new Person(...)                         new Type[...]
             |                                     |
            new                   +-----------------+-----------------+
                                  |                 |                 |
                            primitive[]       reference[]     nhiều chiều
                                  |                 |                 |
                               newarray         anewarray       multianewarray
```

Đây là cách dịch thường gặp; compiler có thể sinh những chuỗi bytecode hợp lệ khác cho cùng ngữ nghĩa. Vì vậy muốn biết một tệp `.class` thực sự dùng lệnh nào, hãy kiểm tra bằng `javap -c`.

## 2. Mô hình chung: heap, operand stack và constant pool

JVM là máy ảo dựa trên ngăn xếp. Khi cấp phát:

1. Bytecode cung cấp **kiểu cần cấp phát** qua operand mã hóa ngay sau opcode, ví dụ `atype` hoặc một constant-pool index.
2. Những dữ liệu động như **độ dài mảng `count`** được nạp lên **operand stack** trước instruction.
3. Instruction kiểm tra các điều kiện liên quan, cấp phát array/object trong mô hình **heap** và đẩy **reference** kết quả lên operand stack.
4. Instruction tiếp theo như `astore` có thể lưu reference ấy vào một local slot.

Ví dụ:

```text
iconst_3       stack: []  → [3]
newarray int   stack: [3] → [ref(int[3])]
astore_1       stack: [ref(int[3])] → []
               locals[1] giữ reference tới mảng
```

**Mảng không nằm toàn bộ bên trong operand stack.** Stack chỉ chứa giá trị tham chiếu sau cấp phát. Mảng thật có các phần tử, độ dài và kiểu runtime trong vùng dữ liệu dành cho object.

Một số thuật ngữ cần tách:

- **Opcode:** mã thao tác, ví dụ `newarray` hoặc `multianewarray`. Mỗi opcode được mã hóa bằng một byte.
- **Operand bytes:** dữ liệu mã hóa theo sau opcode, chẳng hạn chỉ số constant pool, `atype`, `dimensions`.
- **Operand stack:** những giá trị runtime mà instruction đọc/tiêu thụ, như `count`. `count` **không** nhất thiết nằm trong operand bytes của instruction.
- **Local variables:** các slot trong frame phương thức, thường giữ reference sau lệnh `astore`.
- **Constant pool:** dữ liệu class file có các biểu tượng kiểu mà `new`, `anewarray` và `multianewarray` tham chiếu.

Ví dụ, `newarray int` có operand byte chỉ loại `int`, nhưng **độ dài** là một giá trị `int` ở operand stack. Đây là chỗ người mới học thường nhầm.

## 3. `new` — tạo instance của class

### 3.1. Định dạng JVM

`new` có dạng:

```text
new indexbyte1 indexbyte2
```

- Opcode là **`0xbb`**.
- Hai byte đi sau tạo thành **constant-pool index unsigned 16-bit**.
- Entry được tham chiếu là `CONSTANT_Class_info` mô tả class sẽ được instantiate.
- Instruction không tiêu thụ `count` như các lệnh tạo mảng.
- Khi thành công, nó cấp phát một instance rồi đẩy **reference với trạng thái chưa hoàn tất khởi tạo** theo quy tắc verifier.

Ví dụ mã nguồn:

```java
final class Person {
    final String name;

    Person(String name) {
        this.name = name;
    }
}

// Minh họa bên trong một phương thức:
Person p = new Person("Lan");
```

Bytecode minh họa:

```text
new           #k     // class Person
dup
ldc           #s     // String "Lan"
invokespecial #m     // Method Person."<init>":(Ljava/lang/String;)V
astore_1
```

Các chỉ số `#k`, `#s`, `#m` và local slot là **placeholder minh họa**, không phải đầu ra byte-for-byte cố định của mọi `javac`.

### 3.2. Tại sao `new` không đồng nghĩa với gọi constructor?

Cần tách ba bước:

1. **Cấp phát instance:** `new` tạo object và các trường có giá trị mặc định theo mô hình JVM.
2. **Khởi tạo class:** nếu class chưa được khởi tạo và quy tắc yêu cầu, JVM thực hiện class initialization, trong đó có các khối `static` phù hợp.
3. **Khởi tạo instance:** `invokespecial` thường gọi `<init>` để hoàn tất constructor; compiler bảo đảm gọi super-constructor và các hoạt động initialization theo quy tắc Java.

Nếu constructor ném ngoại lệ, biểu thức `new Person(...)` không kết thúc bình thường. Verifier theo dõi **uninitialized reference** và không cho dùng nó tùy tiện như một instance đã khởi tạo.

### 3.3. Tại sao thường xuất hiện `dup`?

`invokespecial <init>` tiêu thụ receiver cùng các tham số trên operand stack. Nhưng biểu thức `new Person("Lan")` vẫn cần trả về reference tới object sau constructor. `dup` thường được dùng để giữ lại một reference cho bước lưu kết quả:

```text
new Person          → [uninitializedRef]
dup                 → [uninitializedRef, uninitializedRef]
ldc "Lan"           → [uninitializedRef, uninitializedRef, "Lan"]
invokespecial <init>→ [initializedRef]   (khi thành công)
astore_1            → []                 (local 1 giữ reference)
```

Đây là sơ đồ stack điển hình, không phải quy tắc rằng mọi phép cấp phát đều phải đi qua cùng một dãy lệnh.

### 3.4. `new` không dùng để tạo interface, abstract instance hoặc mảng

Không thể trực tiếp instantiate interface hoặc abstract class:

```java
// Các dòng sau chỉ minh họa lỗi biên dịch:
// Runnable r = new Runnable();
// java.lang.Number n = new java.lang.Number();
```

Mảng `int[]` và `String[]` cũng không được tạo bằng cách dùng opcode `new` hướng tới một array class như instance bình thường. Chúng có những opcode tạo mảng riêng.

Nếu class file sinh không đúng và yêu cầu instantiate class không phù hợp, có thể gặp `InstantiationError` hoặc những lỗi liên kết/xác minh liên quan. Với Java source thông thường, nhiều trường hợp bị compiler chặn sớm.

## 4. `newarray` — tạo mảng primitive một chiều

### 4.1. Định dạng và hiệu ứng stack

```text
newarray atype
```

- Opcode byte: **`0xbc`**.
- `atype`: một byte biểu thị **primitive component type**.
- Operand stack **trước lệnh**: phải có một giá trị `int` là `count`.
- Instruction lấy `count`, tạo **một mảng primitive** và đẩy reference của mảng.
- Nếu `count < 0` thì ném `NegativeArraySizeException`.

```text
iconst_3       stack []  → [3]
newarray int   stack [3] → [ref(int[3])]
```

### 4.2. Bảng đầy đủ các giá trị `atype`

| Giá trị | Tên trong JVMS | Primitive component type | Mã nguồn ví dụ |
| ---: | --- | --- | --- |
| 4 | `T_BOOLEAN` | `boolean` | `new boolean[2]` |
| 5 | `T_CHAR` | `char` | `new char[2]` |
| 6 | `T_FLOAT` | `float` | `new float[2]` |
| 7 | `T_DOUBLE` | `double` | `new double[2]` |
| 8 | `T_BYTE` | `byte` | `new byte[2]` |
| 9 | `T_SHORT` | `short` | `new short[2]` |
| 10 | `T_INT` | `int` | `new int[2]` |
| 11 | `T_LONG` | `long` | `new long[2]` |

Không có mã `T_STRING` hay `T_OBJECT` trong bảng này. Nếu component type là reference, ta cần cơ chế tạo mảng reference.

### 4.3. Phần tử ban đầu có gì?

Khi cấp phát một array object, các phần tử được thiết lập **giá trị mặc định của kiểu thành phần**:

| Mảng | Giá trị mặc định phần tử |
| --- | --- |
| `int[]`, `byte[]`, `short[]` | 0 |
| `long[]` | `0L` |
| `float[]` | `0.0f` |
| `double[]` | `0.0d` |
| `boolean[]` | `false` |
| `char[]` | ký tự `'\u0000'` |

`new int[3]` có một object mảng với ba phần tử `0`. Nó **không** tạo ba instance của lớp wrapper `Integer` và không có constructor cho mỗi primitive element.

Mặc dù phần tử là primitive, **bản thân mảng là một object**: `Object o = new int[3];` hợp lệ; `int[]` có `length` và có kiểu runtime.

## 5. `anewarray` — tạo mảng có phần tử reference

### 5.1. Định dạng

```text
anewarray indexbyte1 indexbyte2
```

- Opcode byte: **`0xbd`**.
- Hai operand bytes tạo constant-pool index tới `CONSTANT_Class_info` mô tả **component type**.
- Operand stack cung cấp `count` kiểu `int`.
- Kết quả là một **reference array** có độ dài `count`.
- Tất cả phần tử ban đầu mang **giá trị null**, chưa tham chiếu tới instance nào.

Ví dụ:

```java
String[] names = new String[3];
Runnable[] jobs = new Runnable[3];
Number[] values = new Number[3];
```

`Runnable` là interface và `Number` là abstract class, nhưng mảng của chúng vẫn hợp lệ: các slot chỉ chứa **reference**, không bắt buộc phải tạo instance của component type.

### 5.2. Cấp phát mảng không gọi constructor của phần tử

```java
Person[] people = new Person[2];
System.out.println(people[0] == null); // true
```

**Đoạn code là minh họa**, giả định một class `Person` đã được khai báo. Câu lệnh đầu tạo **một mảng gồm hai reference slot**, không tạo hai đối tượng `Person`.

Muốn có instance thực, cần cấp phát riêng:

```java
people[0] = new Person("Lan");
people[1] = new Person("Minh");
```

Tạo `Person[]` không tự kích hoạt class initialization của `Person` chỉ vì class đó là component type. Class có thể được load/resolve theo runtime, nhưng **class loading khác class initialization**, và việc instantiate một `Person` thực mới là một tình huống kích hoạt initialization khi cần.

### 5.3. Component type của `anewarray` có thể là array type

Ví dụ quan trọng:

```java
int[][] rows = new int[2][];
```

Ở đây **component type trực tiếp** của outer array là **`int[]`**, tức một **reference type**. Vì vậy compiler thường dùng `anewarray` tham chiếu constant-pool array class descriptor `[I`:

```text
iconst_2
anewarray #k   // class "[I" tức int[]
```

Kết quả:

```text
rows --> [null, null]         // outer array length = 2
           |     |
           X     X            // chưa có mảng hàng
```

Việc kiểu nguồn là `int[][]` **không có nghĩa tự động dùng `multianewarray`**; biểu thức chỉ cấp phát một tầng mảng.

Nếu sau đó:

```java
rows[0] = new int[] {1, 2};
rows[1] = new int[] {3};
```

thì hai mảng `int[]` mới được tạo riêng, thông thường bằng `newarray int`. Cách này còn tạo ra các **jagged arrays** có độ dài hàng khác nhau.

## 6. `multianewarray` — cấp phát nhiều chiều

### 6.1. Định dạng instruction

```text
multianewarray indexbyte1 indexbyte2 dimensions
```

- Opcode byte: **`0xc5`**.
- Hai byte tiếp theo chỉ tới constant-pool entry mô tả **array type**, ví dụ `[[I`.
- Byte `dimensions` quy định **số chiều được cấp phát** trong instruction.
- Operand stack phải chứa đúng **số lượng giá trị `int` tương ứng với `dimensions`**.
- Khi thành công, JVM cấp phát outer array và những mảng con thuộc các chiều được yêu cầu, rồi đẩy **reference tới outer array** lên stack.

Điều kiện hợp lệ: `dimensions` ít nhất **1** và không được vượt **số chiều/rank của array type**. `multianewarray` hỗ trợ cả việc cấp phát một phần số chiều, không buộc số chiều cấp phát bằng tổng rank.

### 6.2. Hai chiều primitive: `new int[2][3]`

```java
int[][] matrix = new int[2][3];
```

Bytecode thông thường:

```text
iconst_2
iconst_3
multianewarray #k, 2  // class "[[I"
```

Mô phỏng operand stack, đỉnh ở bên phải:

```text
[]        → [2]       → [2, 3]
                            |
                            | multianewarray [[I, dimensions=2
                            v
                       [ref(matrix)]
```

Object graph:

```text
matrix --> [ref hàng 0, ref hàng 1]      outer int[][] length 2
                |           |
                v           v
             [0,0,0]     [0,0,0]         mỗi int[] length 3
```

Có **ba array objects**: một outer array và hai mảng con. Đây là **mảng của các mảng**, không phải cam kết phải có một khối bộ nhớ primitive liên tục như ma trận native.

### 6.3. Hai chiều reference: `new String[2][3]`

```java
String[][] labels = new String[2][3];
```

Biểu thức thường dùng `multianewarray` với array type descriptor `[[Ljava/lang/String;` và `dimensions = 2`. Sau cấp phát:

- Outer array có length 2, các phần tử trỏ tới hai `String[]` đã cấp phát.
- Mỗi hàng `String[]` có length 3.
- Sáu slot `String` reference ban đầu đều **null**.
- **Không có sáu instance `String` được tự động tạo ra**.

### 6.4. Chỉ cấp phát một phần tổng rank

```java
int[][][] cube = new int[2][3][];
```

**Rank là 3** nhưng **số chiều được cấp phát là 2**. `javac` có thể dùng:

```text
iconst_2
iconst_3
multianewarray #k, 2  // class "[[[I"
```

Object graph ban đầu:

```text
cube  (length 2)
  ├── cube[0] (length 3) : [null, null, null]
  └── cube[1] (length 3) : [null, null, null]
```

Đã tạo **ba array objects**, nhưng **chưa có object `int[]` nào** ở cấp cuối. Các slot tham chiếu tới hàng sâu hơn còn null. Sau đó có thể làm:

```java
cube[0][0] = new int[] {7, 8};
```

Điểm then chốt: operand `dimensions` = 2 **không nói rằng outer array dài 2**. Nó nói có **hai chiều được cấp phát**. Độ dài 2 và 3 trong ví dụ đã nằm trên **operand stack**.

### 6.5. Không chỉ áp dụng cho primitive

`multianewarray` dùng được với array types nhiều chiều có component primitive hoặc reference:

```java
int[][] a = new int[2][3];
Object[][] b = new Object[2][3];
String[][][] c = new String[2][3][4];
```

Trong trường hợp reference component, các phần tử cuối cùng ban đầu null; trong trường hợp primitive component, chúng giữ default value của primitive.

## 7. Bảng so sánh chính xác

| Thuộc tính | `new` | `newarray` | `anewarray` | `multianewarray` |
| --- | --- | --- | --- | --- |
| Opcode byte | `0xbb` | `0xbc` | `0xbd` | `0xc5` |
| Operand bytes | 2-byte constant-pool index | 1-byte `atype` | 2-byte constant-pool index | 2-byte index + 1-byte dimensions |
| Input trên operand stack | Không có array length | Một `int` count | Một `int` count | `dimensions` giá trị `int` count |
| Object cấp phát | Instance class | Primitive array | Reference array | Outer array và các tầng mảng chỉ định |
| Giá trị đẩy lên stack | Uninitialized reference theo verifier | Array reference | Array reference | Outer-array reference |
| Giá trị ban đầu của phần tử | Default fields, rồi constructor hoàn tất | Primitive defaults | Null reference | Defaults và references tới các subarrays |
| Cần `<init>` cho kết quả? | Theo mô hình tạo instance thông thường: có | Không | Không | Không |

**Lưu ý về chữ “uninitialized”:** sau `new` object đã được cấp phát. Trạng thái `uninitialized reference` là trạng thái **xác minh bytecode** để bảo đảm constructor được gọi hợp lệ, không có nghĩa object hoàn toàn không có bộ nhớ.

**Lưu ý về số chiều:** `newarray` tạo mảng primitive một tầng; `anewarray` tạo một tầng có component là reference, nên tầng đó vẫn có thể mang kiểu `int[][]`. `multianewarray` có thể cấp phát nhiều tầng trong một instruction.

## 8. Ví dụ Java 17+ hoàn chỉnh có stdout xác định

Tạo tệp **`AllocationDemo.java`** với nội dung:

```java
import java.util.Arrays;

public final class AllocationDemo {
    static final class Item {
        static {
            System.out.println("Item class initialized");
        }

        final String name;

        Item(String name) {
            this.name = name;
            System.out.println("Item constructor: " + name);
        }
    }

    public static void main(String[] args) {
        Item[] slots = new Item[2];
        System.out.println("item-array first is null: " + (slots[0] == null));

        Item item = new Item("Lan");
        slots[0] = item;
        System.out.println("instance: " + slots[0].name);

        int[] counts = new int[3];
        counts[1] = 7;
        System.out.println("primitive array: " + Arrays.toString(counts));

        String[] labels = new String[2];
        labels[0] = "JVM";
        System.out.println("reference array: " + Arrays.toString(labels));

        int[][] matrix = new int[2][3];
        matrix[1][2] = 9;
        System.out.println("matrix: " + Arrays.deepToString(matrix));

        int[][] jagged = new int[2][];
        jagged[0] = new int[] {4};
        System.out.println("partial second row null: " + (jagged[1] == null));
        System.out.println("jagged first row: " + Arrays.toString(jagged[0]));

        System.out.println("int component: "
                + counts.getClass().getComponentType().getName());

        try {
            int[] impossible = new int[-1];
            System.out.println(impossible.length);
        } catch (NegativeArraySizeException ex) {
            System.out.println("negative length rejected");
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac --release 17 AllocationDemo.java
java AllocationDemo
```

**Stdout chính xác trong lần chạy thông thường:**

```text
item-array first is null: true
Item class initialized
Item constructor: Lan
instance: Lan
primitive array: [0, 7, 0]
reference array: [JVM, null]
matrix: [[0, 0, 0], [0, 0, 9]]
partial second row null: true
jagged first row: [4]
int component: int
negative length rejected
```

### Phân tích output

**`item-array first is null: true`:** `new Item[2]` tạo một array object, chưa tạo instance `Item` và chưa tự kích hoạt class initialization của `Item` vì đây chỉ là component type của mảng.

**`Item class initialized`:** xuất hiện khi chương trình lần đầu active-use `Item` bằng biểu thức `new Item("Lan")`, khiến class được khởi tạo khi cần.

**`Item constructor: Lan`:** xuất hiện khi constructor của instance chạy. Điều này cho thấy khác biệt giữa **class initialization** và **instance initialization**.

**`primitive array: [0, 7, 0]`:** `newarray int` tạo ba phần tử zero trước khi code gán `counts[1] = 7`.

**`reference array: [JVM, null]`:** `anewarray` tạo các reference slots ban đầu null. Sau đó `labels[0]` trỏ tới một `String`.

**`matrix: [[0, 0, 0], [0, 0, 9]]`:** outer array và hai mảng hàng đã được cấp phát; code thay đúng một phần tử primitive.

**`partial second row null: true`:** `new int[2][]` chưa cấp phát mảng hàng thứ hai.

**`int component: int`:** `getComponentType()` phản ánh primitive component type thực tế của `counts`; bản thân `counts` vẫn là reference tới một array object.

**`negative length rejected`:** độ dài âm hợp lệ ở biểu thức số nhưng không hợp lệ để cấp phát mảng, nên phát sinh `NegativeArraySizeException` và được bắt trong chương trình.

## 9. Dùng `javap` để nhìn opcode thực

Sau khi biên dịch:

```bash
javap -c -p AllocationDemo
```

Cờ `-c` in bytecode của phương thức, `-p` hiển thị thêm các thành viên không public. Muốn xem constant pool, descriptor và `Code` attribute:

```bash
javap -v -p AllocationDemo
```

Tìm trong `main` những nhóm instruction phù hợp:

| Mã nguồn | Opcode nên tìm |
| --- | --- |
| `new Item[2]` | `anewarray`, component type `AllocationDemo$Item` |
| `new Item("Lan")` | `new`, `dup`, `invokespecial <init>` |
| `new int[3]` | `newarray int` |
| `new String[2]` | `anewarray java/lang/String` |
| `new int[2][3]` | `multianewarray [[I, 2` |
| `new int[2][]` | `anewarray [I` |
| `new int[] {4}` | `newarray int` rồi lưu phần tử |
| `new int[-1]` | nạp giá trị `-1` rồi `newarray int` |

Các dạng trong bảng là **tên instruction/dữ liệu dự kiến**, không phải trích nguyên văn output với constant-pool index hoặc bytecode offset cố định. Compiler/JDK cụ thể quyết định những chỉ số và cách bố trí lệnh.

### Đọc output `new` và `anewarray`

Ví dụ minh họa:

```text
new        #k    // class AllocationDemo$Item
anewarray  #m    // class java/lang/String
```

`#k` và `#m` là **constant-pool indexes**. Hai operand bytes sau opcode dùng để truy cập thông tin class, không phải địa chỉ heap hay số phần tử.

Trong cả hai trường hợp, operand bytes không trực tiếp lưu độ dài mảng; `new` không cần count, còn `anewarray` lấy count từ operand stack.

### Đọc output `multianewarray`

```text
multianewarray #k, 2  // class "[[I"
```

- `#k` xác định kiểu array `int[][]`, descriptor `[[I`.
- Số **2** sau dấu phẩy cho biết **số chiều cần cấp phát**, không phải chiều dài mảng.
- Hai kích thước thật **2** và **3** của `new int[2][3]` đã được đẩy lên operand stack trước instruction.
- Instruction trả **một reference đến outer array**.

Nếu mã nguồn là `new int[4][7]`, operand `dimensions` vẫn là **2**, mặc dù độ dài thực là 4 và 7.

## 10. Đọc descriptor để hiểu component type và rank

Descriptor của JVM là cách mã hóa **kiểu**, không bao gồm độ dài mảng:

| Java type | JVM descriptor |
| --- | --- |
| `int` | `I` |
| `boolean` | `Z` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `int[][]` | `[[I` |
| `int[][][]` | `[[[I` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |

Mỗi ký tự `[` thêm một chiều. Tuy nhiên, **component type trực tiếp** của `int[][]` là `int[]` chứ không phải `int`. Do đó:

```java
int[][] rows = new int[2][];
```

có thể dùng `anewarray` vì phần tử outer array thuộc kiểu reference `int[]`. Ngược lại:

```java
int[] row = new int[2];
```

dùng `newarray` vì phần tử trực tiếp là primitive `int`.

Phân biệt:

- **Rank:** tổng số chiều của array type.
- **Allocated dimensions:** số chiều thực sự được cấp phát trong lần chạy.
- **Component type:** kiểu phần tử **trực tiếp** của một array object.
- **Length:** số phần tử thực tế của một array object khi chạy.

Ví dụ `new int[2][3][]` có rank 3, hai allocated dimensions, outer array length 2 và component type trực tiếp của outer array là `int[][]`.

## 11. Mảng có độ dài 0, âm và quá lớn

### Độ dài 0 vẫn tạo một array object hợp lệ

```java
int[] a = new int[0];
String[] b = new String[0];
int[][] c = new int[0][5];
```

Các reference `a`, `b`, `c` đều **khác null** khi cấp phát thành công. `c` là outer array độ dài 0; không có hàng nào để truy cập `c[0]`. Mảng độ dài 0 khác với một reference bằng null.

### Độ dài âm: `NegativeArraySizeException`

```java
// Biểu thức hợp lệ về cú pháp, sẽ ném khi thực thi:
int[] bad = new int[-1];
```

`newarray`, `anewarray` và `multianewarray` kiểm tra các count mảng theo ngữ nghĩa của từng opcode. Nếu một kích thước cần cấp phát là âm, chương trình không được cấp phát thành công rồi trả về một mảng “nửa hoàn tất” làm kết quả.

### Bộ nhớ không vô hạn

Có thể gặp `OutOfMemoryError` ngay cả khi mọi count đều không âm, do giới hạn heap, số object cần tạo, giới hạn kích thước mảng hoặc tài nguyên hệ thống.

`new int[10000][10000]` có thể cần một outer array và **10.000 inner arrays**, không phải chỉ một mảng đơn. Những cấu trúc thưa có thể dùng `new int[10000][]` để cấp phát hàng khi thật sự cần, nhưng phải xử lý các hàng chưa có object và đang null.

Không đoán một giới hạn độ dài mảng chung cho mọi JVM chỉ dựa vào khả năng biểu diễn của `int`; triển khai và cấu hình runtime còn ảnh hưởng.

## 12. Các opcode đọc/ghi mảng sau cấp phát

Các opcode cấp phát chỉ tạo đối tượng. Đọc/ghi phần tử sử dụng các lệnh khác:

| Mảng/thao tác | Opcode |
| --- | --- |
| `int[]` đọc/ghi phần tử | `iaload` / `iastore` |
| `long[]` đọc/ghi phần tử | `laload` / `lastore` |
| `double[]` đọc/ghi phần tử | `daload` / `dastore` |
| Mảng reference đọc/ghi phần tử | `aaload` / `aastore` |
| Lấy độ dài array | `arraylength` |

Xét:

```java
int[][] rows = new int[2][];
rows[0] = new int[] {5};
rows[0][0] = 7;
```

- `rows[0] = ...` ghi **reference `int[]`** vào outer array, nên dùng nhóm **`aastore`**.
- `rows[0][0] = 7` ghi **primitive int** vào inner array, nên dùng nhóm **`iastore`**.

Ngay cả mảng của mảng primitive cũng là mảng reference ở tầng ngoài. Không quyết định opcode store chỉ dựa trên primitive sâu nhất.

Với mảng reference có covariance:

```java
Object[] values = new String[1];
// values[0] = Integer.valueOf(7); // biên dịch được, nhưng ArrayStoreException
```

Phần tử của `String[]` ở runtime chỉ có thể giữ reference phù hợp với `String` (hoặc null), nên phép ghi qua một biến `Object[]` không loại bỏ kiểm tra kiểu runtime.

## 13. Vì sao object arrays không tự initialize class component?

Cần phân biệt:

1. **Class loading/resolution:** runtime biết thông tin/định nghĩa kiểu cần sử dụng.
2. **Class initialization:** chạy các static initializers của class khi active use yêu cầu.
3. **Instance initialization:** constructor tạo trạng thái của object sau `new`.
4. **Array initialization:** thiết lập giá trị mặc định cho các slot của array object.

`new Widget[2]` chỉ yêu cầu **một mảng có component type `Widget`**, không khởi tạo hai `Widget`. Nó không tự gọi constructor và không tự kích hoạt class initialization của `Widget` chỉ vì component type.

`new Widget()` khác: đây là active use khiến class cần được khởi tạo nếu chưa, rồi chạy constructor thích hợp.

Lưu ý: class/array resolution có thể gây các hoạt động tải lớp hoặc lỗi liên kết, nhưng không nên đánh đồng việc **biết một kiểu** với việc **chạy static initializer** của kiểu đó.

## 14. Các lỗi hiểu sai thường gặp

1. **“Nguồn có `new` thì bytecode chỉ có opcode `new`.”** Sai. Mảng dùng opcode khác.
2. **“`newarray` tạo được `String[]` với một `atype` nào đó.”** Sai. `atype` chỉ dành cho tám primitive types.
3. **“`anewarray` tạo sẵn mọi object phần tử.”** Sai. Các phần tử reference ban đầu null.
4. **“`new int[2][]` tạo hai hàng rỗng.”** Sai. Nó tạo outer array; các hàng là null.
5. **“`multianewarray #k, 2` có nghĩa outer array dài 2.”** Sai. Số 2 cuối là allocated dimensions.
6. **“`int[][]` luôn được tạo bằng `multianewarray`.”** Sai. `new int[2][]` thường dùng `anewarray`.
7. **“`new` đã gọi constructor, `invokespecial` là thừa.”** Sai. Hai instruction phục vụ hai giai đoạn riêng.
8. **“Primitive array không phải object.”** Sai. `int[]` là một reference type và một array object.
9. **“`new int[0]` tương đương null.”** Sai. Đó là array object có length 0.
10. **“Các count của mảng nằm bên trong operand bytes của `anewarray`.”** Sai. Count ở operand stack; operand bytes của `anewarray` chứa constant-pool index.
11. **“`multianewarray` cấp phát đủ mọi chiều trong descriptor.”** Sai. Nó chỉ cấp phát `dimensions` chiều được chỉ định.
12. **“Array 2D luôn là một khối primitive liên tục.”** Sai theo mô hình Java: mảng của các mảng.
13. **“Mảng của interface không hợp lệ.”** Sai. `Runnable[]` hợp lệ dù không instantiate trực tiếp `Runnable`.
14. **“Một object được cấp phát nghĩa là toàn bộ quá trình khởi tạo instance đã thành công.”** Sai. Constructor có thể ném exception.
15. **“Có lỗi khi cấp phát mảng thì phải là `VerifyError`.”** Sai. Kích thước âm hoặc thiếu bộ nhớ là những lỗi runtime riêng; verifier xử lý ràng buộc class file và kiểu.

## 15. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** `new long[4]` dùng opcode nào, tạo bao nhiêu object?

**Đáp án:** `newarray` với `atype = T_LONG (11)`; tạo **một mảng `long[]`** gồm bốn phần tử `0L`.

**Câu 2.** `new Runnable[3]` có hợp lệ khi `Runnable` là interface không?

**Đáp án:** Có. `anewarray` tạo một array object với ba null reference slots; nó không tạo instance `Runnable`.

**Câu 3.** `new int[2][3]` thường tạo bao nhiêu array objects?

**Đáp án:** Một outer array và hai `int[]` rows, tổng **ba objects**, thường bằng `multianewarray` với `dimensions=2`.

**Câu 4.** `new int[2][]` tạo bao nhiêu object lúc đầu?

**Đáp án:** **Một outer array**, hai phần tử reference bằng null; compiler thường dùng `anewarray` với component type `int[]`.

**Câu 5.** `multianewarray [[I, 2`: số 2 cuối là gì?

**Đáp án:** Số chiều được cấp phát. Các kích thước thật nằm trên operand stack.

**Câu 6.** `new Person[5]` có chạy constructor `Person()` năm lần không?

**Đáp án:** Không. Mảng chứa năm null references ban đầu.

**Câu 7.** Vì sao `new Person("Lan")` thường đi kèm `dup` và `invokespecial <init>`?

**Đáp án:** `new` cấp phát; `dup` giữ reference làm kết quả biểu thức; `invokespecial` gọi constructor, tiêu thụ receiver/arguments theo quy tắc.

**Câu 8.** `new String[0]` có bằng null không?

**Đáp án:** Không. Nó là object mảng hợp lệ với `length == 0`.

**Câu 9.** Gán `rows[0] = new int[3]` trên `int[][] rows` dùng store primitive hay reference ở mảng ngoài?

**Đáp án:** **Reference store `aastore`**, vì phần tử trực tiếp của `int[][]` là `int[]`.

**Câu 10.** Với `new int[2][3][]`, những chiều nào đã có mảng?

**Đáp án:** Hai chiều đầu. Các reference cần trỏ tới `int[]` ở cấp cuối ban đầu là null.

**Câu 11.** `new int[-1]` sai ở compile-time hay runtime?

**Đáp án:** Biểu thức đúng kiểu; runtime ném `NegativeArraySizeException` khi cấp phát.

**Câu 12.** Tại sao `new int[10000][10000]` có nguy cơ hết heap nhanh?

**Đáp án:** Vì có rất nhiều phần tử và nhiều object mảng con, không chỉ một object; tổng bộ nhớ có thể vượt giới hạn JVM.

## 16. Tổng kết bằng một sơ đồ

```text
new
  operand bytes: constant-pool index cho class
  stack input  : không có độ dài mảng
  stack output : reference tới instance chưa hoàn tất <init>
  ví dụ        : new Person("Lan")

newarray
  operand bytes: atype = một trong tám primitive types
  stack input  : một int count
  stack output : reference tới primitive array
  ví dụ        : new int[3]

anewarray
  operand bytes: constant-pool index cho component reference type
  stack input  : một int count
  stack output : reference tới reference array
  ví dụ        : new String[3], new int[2][]

multianewarray
  operand bytes: constant-pool array type index + dimensions
  stack input  : dimensions giá trị int count
  stack output : reference tới outer array
  ví dụ        : new int[2][3], new String[2][3], new int[2][3][]
```

**Ghi nhớ:** Từ khóa `new` ở mã nguồn là một ý tưởng; các opcode `new`, `newarray`, `anewarray` và `multianewarray` diễn đạt **những hình thức cấp phát khác nhau** ở cấp JVM. Khi đọc `javap`, hãy hỏi: **kiểu được chỉ định ở đâu, số kích thước lấy từ đâu, tạo bao nhiêu array objects và phần tử ban đầu là gì?**

### Tài liệu đặc tả chính thức

- [JVMS 6.5 — new](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.new): cấp phát instance của class.
- [JVMS 6.5 — newarray](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.newarray): `atype` và primitive arrays.
- [JVMS 6.5 — anewarray](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.anewarray): reference arrays.
- [JVMS 6.5 — multianewarray](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.multianewarray): dimensions và cấp phát mảng nhiều chiều.
- [JVMS 4.3 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3): ký hiệu kiểu class, primitive và array.
- [JLS 10 — Arrays](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html): khái niệm, kiểu thành phần và phần tử mảng.
- [`javap` JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): đọc bytecode/constant pool.
