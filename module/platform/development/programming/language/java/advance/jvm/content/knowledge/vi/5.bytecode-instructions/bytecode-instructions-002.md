# Nạp hằng số và chuyển dữ liệu giữa biến cục bộ với operand stack trong JVM

Trong Java Virtual Machine (JVM), nhiều biểu thức Java được thực hiện bằng một chuỗi thao tác rất cụ thể: **đẩy hằng số lên operand stack**, **nạp giá trị từ local variables lên stack**, thực hiện phép tính hoặc gọi phương thức, rồi **lưu kết quả từ stack về local variables**. Nếu hiểu các lệnh này, bạn có thể đọc kết quả `javap -c`, theo dõi từng giá trị trong một JVM frame và phân biệt được thao tác ở mức bytecode với câu lệnh Java.

Bài học tập trung vào nhóm bytecode **constant loading** (`iconst_*`, `bipush`, `sipush`, `ldc`, `ldc_w`, `ldc2_w`...), **local load/store** (`iload`/`istore`, `lload`/`lstore`...), chỉ số slot, giá trị 1 hoặc 2 slot, lệnh `wide` và `iinc`. Mốc tài liệu là **JVMS Java SE 17**. Mã ví dụ sử dụng Java 17+, và những opcode do `javac` chọn sẽ được phân biệt với quy tắc bắt buộc của đặc tả.

## 1. Khung thực thi: locals và operand stack thuộc về *mỗi lần gọi phương thức*

Một lần gọi phương thức JVM tạo một **frame** chứa hai vùng quan trọng:

- **Local variable array**: các ô (slot) đánh chỉ số từ `0`, chứa tham số, receiver `this` (đối với instance method) và các giá trị cục bộ/tạm. Mảng này truy cập theo **index**.
- **Operand stack**: ngăn xếp LIFO chứa toán hạng và kết quả trung gian. Phần lớn lệnh số học lấy toán hạng từ đỉnh stack và đẩy kết quả trở lại.
- **`max_locals` và `max_stack`** trong `Code` attribute của phương thức xác định số slot locals và độ sâu tối đa của operand stack. Đây là giới hạn **theo frame**, không phải dung lượng heap hay toàn bộ Java thread stack.

Sơ đồ luồng dữ liệu thường gặp:

```text
Local variables                     Operand stack (đáy → đỉnh)
slot 0: a = 4                          []
slot 1: b = 5                          []
      | iload_0                          [4]
      | iload_1                          [4, 5]
      | iadd                             [9]
      | istore_2                         []
slot 2: sum = 9   <---------------------+
```

`iload_0` không lấy giá trị “ra khỏi” local: nó **sao chép giá trị** từ slot 0 lên stack. Ngược lại, `istore_2` **lấy giá trị từ đỉnh stack** để gán vào slot 2, vì vậy stack giảm độ sâu. Local slot 0 vẫn là 4, slot 1 vẫn là 5 sau phép cộng.

Một method có nhiều lần gọi đồng thời (nhiều thread hoặc đệ quy) sẽ có **các frame riêng**. Không được hiểu local slot 0 là biến toàn cục chia sẻ giữa các lần gọi.

### Một giá trị có thể chiếm một hoặc hai slot

| Loại tính toán JVM | Độ rộng category | Độ sâu operand stack khi đẩy một giá trị | Local slot cần dùng |
| --- | --- | ---: | ---: |
| `int`, `float`, `reference` | Category 1 | 1 | 1 |
| `long`, `double` | Category 2 | 2 | 2 |
| `byte`, `short`, `char`, `boolean` khi thao tác tính toán bằng bytecode | Thường theo `int` (category 1) | 1 | 1 cho local kiểu tính toán tương ứng |

`long`/`double` là **một giá trị logic** nhưng cần hai slot theo mô hình JVM; không phải hai số độc lập để code tùy ý đọc riêng từng nửa. Trên operand stack, các lệnh thao tác stack như `dup`, `dup2`, `pop`, `pop2` phải tôn trọng phân loại category này.

## 2. Các cách đẩy hằng số trực tiếp lên operand stack

JVM có một số opcode ngắn cho các hằng số phổ biến, giúp bytecode nhỏ hơn khi không cần truy cập constant pool.

| Lệnh bytecode | Giá trị đẩy lên stack | Loại | Ghi chú |
| --- | --- | --- | --- |
| `aconst_null` | Tham chiếu `null` | Reference, category 1 | Không tạo object |
| `iconst_m1` | `-1` | `int` | Opcode riêng cho âm một |
| `iconst_0` … `iconst_5` | `0` … `5` | `int` | Sáu opcode cho int nhỏ |
| `lconst_0`, `lconst_1` | `0L`, `1L` | `long`, category 2 | Đẩy một giá trị dài chiếm hai slot |
| `fconst_0` … `fconst_2` | `0.0f`, `1.0f`, `2.0f` | `float` | Ba hằng số float có sẵn |
| `dconst_0`, `dconst_1` | `0.0d`, `1.0d` | `double`, category 2 | Hai hằng số double có sẵn |
| `bipush n` | Số nguyên từ `-128` đến `127` | `int` | Immediate **signed 8-bit**, được sign-extend thành int |
| `sipush n` | Số nguyên từ `-32768` đến `32767` | `int` | Immediate **signed 16-bit**, được sign-extend thành int |

Điểm quan trọng: chữ **byte** trong `bipush` mô tả độ rộng *immediate operand trong tệp class*, **không** có nghĩa opcode này đẩy giá trị Java `byte` lên stack. Cả `bipush` và `sipush` đều đẩy **`int`**.

Ví dụ các hiệu ứng stack, với ký hiệu phần bên trái là stack trước lệnh:

```text
[]             -- iconst_3   --> [3]
[]             -- bipush 7   --> [7]
[]             -- sipush 300 --> [300]
[12]           -- iconst_2   --> [12, 2]
[12, 2]        -- iadd       --> [14]
[]             -- lconst_1   --> [1L]  // một giá trị long = hai slot
[]             -- aconst_null --> [null]
```

Trong ví dụ này, `iadd` yêu cầu hai giá trị `int` trên đỉnh stack; nó lấy chúng ra rồi đẩy tổng `int`. Việc `sipush 300` có operand mã hóa bằng hai byte không làm cho kết quả trở thành kiểu `short`. Tương tự, `lconst_1` không phải hai phần tử `int` có thể cộng bằng `iadd`.

### Giá trị vượt các immediate nhỏ thì sao?

Khi giá trị không phù hợp opcode immediate, compiler có thể chọn lệnh truy cập **run-time constant pool**, ví dụ `ldc` hoặc `ldc2_w`. Sự lựa chọn opcode giữa các cách biểu diễn hợp lệ phụ thuộc compiler; hằng số xuất hiện trong source không đảm bảo phải được đưa lên operand stack ở runtime (compiler có thể thực hiện constant folding hoặc tối ưu code).

## 3. `ldc`, `ldc_w` và `ldc2_w`: đọc dữ liệu từ run-time constant pool

Run-time constant pool gắn với class chứa các constant và symbolic references được định nghĩa qua cấu trúc constant pool trong tệp `.class`. Ba opcode dùng **index** vào constant pool:

| Lệnh | Operand chỉ số | Các loại thường nạp | Số byte của lệnh tính cả opcode |
| --- | --- | --- | ---: |
| `ldc index` | Chỉ số `u1` không dấu, tối đa 255 | `int`, `float`, `String` reference, `Class` reference, method type/handle hoặc dynamic constant category 1 | 2 |
| `ldc_w indexbyte1 indexbyte2` | Chỉ số `u2` không dấu, tối đa 65535 | Tương tự `ldc`; chỉ **khác độ rộng index** | 3 |
| `ldc2_w indexbyte1 indexbyte2` | Chỉ số `u2` không dấu | `long`, `double` hoặc dynamic constant tương ứng category 2 | 3 |

- `ldc_w` **không** có nghĩa “load giá trị 64-bit”; chữ `_w` ám chỉ **wider constant-pool index**. Nó có thể nạp `int`, `float` hoặc reference giống `ldc`.
- `ldc2_w` được sử dụng cho các giá trị `long`/`double` ngoài những hằng số có opcode riêng; không tồn tại opcode chuẩn tên `ldc2` có index 8-bit.
- `String` literal được nạp thành **reference** trỏ tới đối tượng `String` tương ứng; `ldc` không phải phép sao chép từng ký tự lên operand stack.
- Với constant `Class`, method handle/type hoặc **dynamic constant**, quá trình resolution có thể xảy ra và phát sinh lỗi liên kết theo đặc tả. Đừng coi mọi `ldc` chỉ là “đọc một số đã lưu” theo nghĩa đơn giản.
- `ldc` có thể nạp constant category 1 được tính động (`CONSTANT_Dynamic`); `ldc2_w` có thể nạp dynamic constant `long`/`double`. Không phải Java source bình thường nào cũng trực tiếp biểu diễn được các constant này; chúng có thể đến từ compiler/library tạo bytecode.

Ví dụ theo lựa chọn `javac` Java 17 thông dụng:

```text
iconst_5               // int 5
bipush 100             // int 100
sipush 300             // int 300
ldc #N                 // int 40000 từ constant pool
ldc2_w #M              // long 5000000000 từ constant pool
ldc #K                 // String "JVM" từ constant pool
```

`#N`, `#M`, `#K` là **chỉ số minh họa**, không phải số bắt buộc. Chỉ số thật phụ thuộc thứ tự nội dung trong constant pool mà compiler tạo.

### Vì sao một dòng source không tương ứng một `ldc`?

`static final int LIMIT = 100;` có thể là **compile-time constant** và được compiler nhúng trực tiếp tại nơi sử dụng. Một biểu thức chỉ gồm constant có thể được tính trước, khiến bytecode không còn opcode cộng/nhân tương ứng. Khi quan sát bytecode, chỉ kết luận về **class file đang xem**; hợp đồng ngôn ngữ vẫn nằm ở JLS và ngữ nghĩa opcode nằm ở JVMS.

## 4. Lệnh nạp local variables lên operand stack

Các lệnh `load` lấy giá trị trong **local-variable array của frame hiện tại** rồi **đẩy bản sao của giá trị lên operand stack**.

| Loại JVM | Dạng chỉ số tường minh | Dạng viết tắt cho index 0–3 | Hiệu ứng |
| --- | --- | --- | --- |
| `int` | `iload index` | `iload_0` … `iload_3` | Locals[index] → stack (1 slot) |
| `long` | `lload index` | `lload_0` … `lload_3` | Locals[index,index+1] → stack (2 slot) |
| `float` | `fload index` | `fload_0` … `fload_3` | Locals[index] → stack (1 slot) |
| `double` | `dload index` | `dload_0` … `dload_3` | Locals[index,index+1] → stack (2 slot) |
| Reference | `aload index` | `aload_0` … `aload_3` | Locals[index] → stack (1 slot) |

Một số quy tắc quan trọng:

1. `iload_0` là một opcode riêng có **chỉ số 0 ngầm định**; `iload 0` sử dụng thêm một byte operand cho index. Hai cách có cùng ngữ nghĩa, khác encoding.
2. `lload_2` bắt đầu ở **slot 2**, chiếm slot **2 và 3**, rồi đẩy một giá trị `long` dùng hai slot lên stack.
3. Các slot locals phải chứa **kiểu hợp lệ** theo trạng thái verification. `iload` không thể tùy tiện đọc reference, `aload` không thể đọc `int`, và không được dùng giá trị local chưa được gán hợp lệ.
4. Các kiểu Java `byte`, `short`, `char`, `boolean` trong nhiều thao tác local được JVM biểu diễn qua **`int`** và lệnh `iload`. Khi cần bảo đảm giá trị nằm trong miền hẹp, compiler có thể phát sinh chuyển đổi như `i2b`, `i2s`, `i2c`.
5. `aload_0` trong method instance **thường** nạp `this` vì receiver ở local slot 0; trong method `static`, slot 0 có thể chứa tham số đầu tiên thay vì `this`.

Không suy luận rằng `iload_1` nghĩa là “nạp tham số thứ hai” trong mọi method: receiver ẩn và các tham số category 2 làm thay đổi thứ tự **slot**.

## 5. Lệnh lưu từ operand stack về local variables

`store` làm thao tác ngược `load`: **pop giá trị đỉnh stack** và lưu vào vị trí được đánh index trong local variables.

| Loại JVM | Dạng chỉ số tường minh | Dạng viết tắt index 0–3 | Hiệu ứng |
| --- | --- | --- | --- |
| `int` | `istore index` | `istore_0` … `istore_3` | stack pop (int) → locals[index] |
| `long` | `lstore index` | `lstore_0` … `lstore_3` | stack pop (long) → locals[index,index+1] |
| `float` | `fstore index` | `fstore_0` … `fstore_3` | stack pop (float) → locals[index] |
| `double` | `dstore index` | `dstore_0` … `dstore_3` | stack pop (double) → locals[index,index+1] |
| Reference | `astore index` | `astore_0` … `astore_3` | stack pop (reference) → locals[index] |

Ví dụ biểu thức `int result = a + b;` trong một method có thể được chuyển thành:

```text
iload_0     // [] → [a]
iload_1     // [a] → [a, b]
iadd        // [a, b] → [a+b]
istore_2    // [a+b] → []; locals[2] nhận a+b
```

Ở đây, `istore_2` **không** trả kết quả từ method: chỉ ghi biến cục bộ. Để trả `int`, bytecode có thể tiếp tục `iload_2` rồi `ireturn`. Một compiler khác có thể bỏ hẳn store/load trung gian và trả kết quả trực tiếp mà vẫn đúng nghĩa Java.

Một giới hạn khác: gán một local category 2 (`long`/`double`) làm thay đổi trạng thái hợp lệ của cả cặp slot nó chiếm. Các phép store đè lên một phần cặp slot category 2 có thể khiến giá trị category 2 trước đó không còn đọc được hợp lệ. Vì vậy mọi code tự tạo/sửa bytecode phải đồng bộ **loại và phạm vi sống của local slots**, không chỉ nhìn số index.

### `max_locals` khác số biến viết bằng tên

- Method `static int add(int a, int b)`: `a` ở slot 0, `b` ở slot 1, nếu lưu kết quả vào biến mới thì có thể dùng slot 2.
- Method `int add(int b)` là instance: `this` ở slot 0, `b` ở slot 1.
- Method `static long add(long a, long b)`: `a` chiếm slot 0–1, `b` chiếm slot 2–3. Kết quả lưu thêm `long` có thể cần slot 4–5.
- Compiler có thể **tái sử dụng** một slot sau khi giá trị cũ hết phạm vi cần thiết hoặc tạo slot cho giá trị trung gian không có tên trong source.

Trong `javap -v`, dòng `stack=..., locals=..., args_size=...` tóm tắt thông tin frame; `args_size` là cách `javap` trình bày số slot dành cho các tham số JVM của method (bao gồm receiver cho method instance và hai slot cho mỗi `long`/`double`), chứ **không** phải một trường riêng của cấu trúc `Code_attribute`.

## 6. Ví dụ Java 17 chạy được: constant → stack → local → phép toán

Tạo file **`LocalStackFlow.java`**:

```java
public class LocalStackFlow {
    public static int calculate(int input) {
        int increased = input + 7;
        int result = increased + 40_000;
        return result;
    }

    public static long addLong(long first, long second) {
        long sum = first + second;
        return sum;
    }

    public static String label() {
        return "JVM";
    }

    public static void main(String[] args) {
        System.out.println("calculate=" + calculate(2));
        System.out.println("long=" + addLong(20L, 22L));
        System.out.println("label=" + label());
    }
}
```

Biên dịch và chạy trên JDK có `javac` hỗ trợ Java 17:

```bash
javac --release 17 -g LocalStackFlow.java
java LocalStackFlow
javap -c -v -p LocalStackFlow
```

**Stdout của lệnh `java LocalStackFlow`**:

```text
calculate=40009
long=42
label=JVM
```

### Đọc method `calculate(int)` qua `javap`

Với `javac` Java 17 thông thường, phần opcode đáng chú ý có thể xuất hiện như sau (chỉ trích method này, bỏ qua các mục metadata khác):

```text
public static int calculate(int);
  Code:
    stack=2, locals=3, args_size=1
       0: iload_0
       1: bipush        7
       3: iadd
       4: istore_1
       5: iload_1
       6: ldc           #...   // int 40000
       8: iadd
       9: istore_2
      10: iload_2
      11: ireturn
```

Dấu `#...` ở trên đại diện cho **một index constant pool**, không phải toàn văn output có thể copy để thực thi. Bytecode index `0, 1, 3, 4, ...` là **offset tính theo byte**, không phải số lệnh. `bipush 7` chiếm hai byte; `ldc` với index một byte cũng chiếm hai byte.

| BCI / opcode | Local variables (slot 0, 1, 2) | Operand stack, đáy → đỉnh | Số slot trên stack |
| --- | --- | --- | ---: |
| Trước `iload_0` | `[2, -, -]` | `[]` | 0 |
| Sau `iload_0` | `[2, -, -]` | `[2]` | 1 |
| Sau `bipush 7` | `[2, -, -]` | `[2, 7]` | 2 |
| Sau `iadd` | `[2, -, -]` | `[9]` | 1 |
| Sau `istore_1` | `[2, 9, -]` | `[]` | 0 |
| Sau `iload_1` | `[2, 9, -]` | `[9]` | 1 |
| Sau `ldc 40000` | `[2, 9, -]` | `[9, 40000]` | 2 |
| Sau `iadd` | `[2, 9, -]` | `[40009]` | 1 |
| Sau `istore_2` | `[2, 9, 40009]` | `[]` | 0 |
| Sau `iload_2` | `[2, 9, 40009]` | `[40009]` | 1 |
| `ireturn` | Frame sắp trả về | Trả `40009` cho caller | — |

Dấu `-` ở bảng nghĩa là local chưa có giá trị cần dùng theo đường đi minh họa, không phải giá trị Java `null`. Độ sâu lớn nhất **2 slot**, nên `max_stack=2` hợp lý cho method này; cần **3 slots locals** (input/increased/result), nên `max_locals=3`.

Lưu ý: đây là **một cách biên dịch**. Compiler được phép biến đổi hoặc loại bỏ local trung gian, thay đổi việc nạp hằng số miễn code kết quả tuân theo JLS/JVMS. Khi học quy tắc lệnh, hãy kiểm tra bytecode thực tế từ chính compiler đang dùng.

### Với `addLong(long,long)`: hai giá trị nhưng bốn slots

Trong method `static` này:

```text
locals:
  slot 0-1 : first  = 20L
  slot 2-3 : second = 22L
  slot 4-5 : sum    = 42L (sau lstore)

operand stack:
  []                         ban đầu
  [20L]                      sau lload_0         (2 slot)
  [20L, 22L]                 sau lload_2         (4 slot)
  [42L]                      sau ladd            (2 slot)
  []                         sau lstore 4        (0 slot)
  [42L]                      sau lload 4         (2 slot)
  []                         sau lreturn
```

`max_stack` của dạng trên là **4**, `max_locals` là **6**. Đừng đếm `[20L, 22L]` thành “hai slots”: đó là **hai giá trị category 2**, tổng cộng bốn slots.

`label()` minh họa nạp String literal bằng `ldc` vào operand stack rồi trả về bằng `areturn`; JVM thao tác trên **reference** chứ không chèn từng byte UTF-8 của chuỗi vào stack.

## 7. Ví dụ về tham số, `this` và vị trí local không liên tiếp

File độc lập **`ParameterSlots.java`**:

```java
public class ParameterSlots {
    private final int base;

    public ParameterSlots(int base) {
        this.base = base;
    }

    public long combine(int count, long amount, double ignored) {
        long result = amount + count + base;
        return result;
    }

    public static void main(String[] args) {
        ParameterSlots value = new ParameterSlots(5);
        System.out.println("combined=" + value.combine(2, 30L, 0.5));
    }
}
```

Lệnh:

```bash
javac --release 17 -g ParameterSlots.java
java ParameterSlots
javap -c -p ParameterSlots
```

**Stdout của `java`**:

```text
combined=37
```

Trong **instance method** `combine(int,long,double)`, chỉ số locals ban đầu được xác định theo descriptor, dù biến `ignored` không xuất hiện trong thân method:

| Slot | Nội dung tại đầu method |
| --- | --- |
| 0 | Reference `this` |
| 1 | `count` (`int`) |
| 2 và 3 | `amount` (`long`) |
| 4 và 5 | `ignored` (`double`) |
| 6 và 7 | Có thể được compiler dùng cho `result` (`long`) |

Lệnh `iload_1` lấy `count`; `lload_2` lấy `amount`; `aload_0` lấy `this` để đọc field `base` qua `getfield`; một kết quả `long` có thể được lưu bằng `lstore 6`. Các vị trí tham số là bắt buộc theo quy ước invocation; local tạm cho `result` và chuỗi opcode cụ thể do compiler quyết định.

Các ví dụ có `long`/`double` cho thấy vì sao `lload_2` **không phải** “load tham số thứ ba” và vì sao không thể tính `max_locals` chỉ bằng số tham số viết trong Java source.

## 8. `iinc` cập nhật local mà không đi qua operand stack

`iinc index, const` là opcode đặc biệt thực hiện cộng một immediate **signed byte** vào một local variable kiểu `int`. Nó cập nhật locals tại `index` **trực tiếp**; operand stack **không thay đổi**.

Ví dụ minh họa bytecode cho biến cục bộ `int counter`:

```text
locals[1] = 8;  stack = []
iinc 1, 1
locals[1] = 9;  stack = []
```

So sánh phép tăng viết thành load/add/store:

```text
iload_1       // [] → [8]
iconst_1      // [8] → [8, 1]
iadd          // [8, 1] → [9]
istore_1      // [9] → []; locals[1] = 9
```

Hai chuỗi có thể tương đương về kết quả trong một ngữ cảnh đơn giản, nhưng `iinc` chỉ áp dụng cho **local int** và có operand immediate theo encoding. Không có opcode `linc` tương đương cho `long`, và việc cập nhật field/array không diễn ra bằng `iinc`.

Ví dụ Java:

```java
public static int next(int value) {
    value++;
    return value;
}
```

Đây là **đoạn method minh họa**, đặt trong một class để biên dịch. `javac` Java 17 thường sinh `iinc 0, 1` rồi `iload_0` và `ireturn`. Nếu `value == Integer.MAX_VALUE`, phép tăng nguyên wrap thành `Integer.MIN_VALUE`; `iinc` không ném exception do overflow.

## 9. `wide`: mở rộng chỉ số local và immediate của `iinc`

Các lệnh `iload index`/`istore index` ở dạng thường có **index 8 bit** không dấu. Khi cần tham chiếu local slot index lớn hơn 255, JVM dùng prefix **`wide`** với index **16 bit**. `wide` hỗ trợ các nhóm load/store locals, `ret` cũ và `iinc`; nó không phải một opcode phổ dụng mở rộng mọi lệnh.

Dạng minh họa:

```text
iload 12          // chỉ số 12 dùng operand 1 byte
wide iload 300    // chỉ số 300 dùng operand 2 byte
iinc 7, -3        // index 1 byte; const signed 1 byte
wide iinc 300, 1000 // index 2 byte; const signed 2 byte
```

**Đây là mnemonic minh họa format**, không phải đoạn `javap` lấy từ một file xác định. Khi mã hóa thành bytes, `wide` là một prefix có opcode riêng đứng trước opcode được phép mở rộng.

- Với `wide iload`, `wide istore` và các load/store khác, chỉ số local thành `u2` (0–65535, nhưng còn phải nằm trong `max_locals`).
- Với `wide iinc`, cả index là `u2` và immediate là số nguyên **signed 16-bit**.
- `wide` **không** làm `int` thành `long`, không làm operand stack rộng hơn và không mở rộng một constant-pool index: việc đó là nhiệm vụ `ldc_w`.

Thêm một lưu ý thực tế: chương trình source có rất nhiều biến cục bộ có thể khiến compiler sinh `wide`, nhưng compiler có thể tái sử dụng local slots. Số biến trong source không tự xác định sự xuất hiện của prefix này.

## 10. Nạp/lưu local khác với đọc/ghi field và array

Có ba nơi thường bị gọi chung là “biến” khi đọc Java source, nhưng opcode khác nhau:

| Trong source | Nhóm opcode đại diện | Đối tượng chứa dữ liệu |
| --- | --- | --- |
| Biến cục bộ hoặc tham số | `iload`/`istore`, `aload`/`astore`, v.v. | Local-variable array của frame |
| Trường instance | `getfield`/`putfield` | Một object được chỉ ra bằng reference |
| Trường static | `getstatic`/`putstatic` | Field static của class/interface |
| Phần tử array | `iaload`/`iastore`, `aaload`/`aastore`, `baload`/`bastore`... | Array object và index |

Ví dụ, với `int[] a`, `a[0] = 9` **không** được thực hiện bằng `istore_0` trừ trường hợp compiler đang gán 9 cho *biến local* nào đó. Array store cần reference tới array, index và giá trị trên operand stack, rồi dùng `iastore`.

Tương tự, lệnh `aload_0` thường đẩy `this`; để đọc `this.base`, bytecode cần thêm `getfield`. `aload`/`astore` thao tác **reference**, không tự copy toàn bộ trạng thái object.

### Ví dụ minh họa array, với luồng stack

Giả sử locals slot 0 chứa reference tới `int[]` và muốn ghi phần tử đầu tiên bằng 9:

```text
[]                     // operand stack ban đầu
aload_0                // [arrayRef]
iconst_0               // [arrayRef, 0]
bipush 9               // [arrayRef, 0, 9]
iastore                // []; arrayRef[0] = 9
```

`iastore` lấy ra ba toán hạng từ stack; `istore` chỉ lấy một giá trị `int` rồi ghi vào local. Sự khác biệt này rất quan trọng khi xem trace hoặc tính `max_stack`.

## 11. `dup`, `pop` và hậu quả với độ sâu operand stack

Không phải mọi lệnh thao tác stack đều làm số học hoặc truy cập local. Một số lệnh thay đổi **cách giá trị nằm trên stack**:

- `pop` bỏ một giá trị **category 1** ở đỉnh.
- `pop2` bỏ một giá trị category 2 **hoặc** hai giá trị category 1 ở đỉnh, tùy cấu hình hợp lệ.
- `dup` nhân đôi giá trị category 1 ở đỉnh.
- `dup2` có các dạng hợp lệ để nhân đôi một giá trị category 2 hoặc cặp giá trị category 1.
- `swap` đổi chỗ hai giá trị category 1 ở đỉnh; không dùng để tùy ý hoán đổi một `long` và một `int`.

Ví dụ, biểu thức có cả gán và sử dụng kết quả có thể cần `dup` để **vừa lưu vào một local/field vừa giữ một bản giá trị trên stack**. Đọc opcode mà không theo dõi stack sẽ rất dễ nhầm hai bản sao thành hai object khác nhau; với reference, `dup` sao chép **tham chiếu**, không tạo object mới.

## 12. Kiểu dữ liệu, verification và lỗi liên quan

JVM verifier kiểm tra rằng code trong method có các đường control flow và kiểu stack/locals hợp lệ theo class-file version tương ứng. Những ví dụ bytecode **không hợp lệ** về kiểu:

```text
aconst_null
iadd                  // sai: iadd cần hai int

iconst_1
lstore_0              // sai: lstore cần một long category 2

iload_1               // sai nếu slot 1 chưa có giá trị int hợp lệ
```

Đây là **các fragment cố ý sai để minh họa verification**, tuyệt đối không phải chương trình chạy được. Lỗi kiểu/stack có thể dẫn tới `VerifyError`; tệp class hỏng cấu trúc có thể dẫn tới `ClassFormatError`. Những lỗi này khác `NullPointerException` hoặc `ArithmeticException` phát sinh khi **code hợp lệ** đang thực thi.

Những quy tắc cần giữ khi đọc/tạo bytecode:

1. Phải có đủ operand theo đúng **thứ tự và loại** cho opcode tiếp theo.
2. Các nhánh hội tụ cần tương thích về **loại stack/locals**; `StackMapTable` có thể hỗ trợ verifier xác nhận.
3. Không được load local trước khi nó được gán hợp lệ trên đường thực thi đi tới lệnh ấy.
4. `max_stack` phải đủ cho mọi đường thực thi; `max_locals` phải bao trùm tất cả index và cặp index+1 của category 2.
5. Khi chuyển kiểu nhỏ, nhớ `byte`/`short`/`char` được tính dưới dạng `int` và có thể có `i2b`/`i2s`/`i2c` khi cần thu hẹp.
6. Với `long`/`double`, một giá trị logic có hai slot; không thể truy cập “nửa trên” bằng `iload` để giả làm số `int`.

Một giá trị `null` được `aconst_null` đẩy lên operand stack là **reference hợp lệ**. Chỉ khi dùng nó trong các thao tác yêu cầu object thực (ví dụ dereference qua `getfield`/`invokevirtual`) mới có thể gặp `NullPointerException`; bản thân `aconst_null` không ném lỗi.

## 13. Đọc kết quả `javap` theo một quy trình nhất quán

Sử dụng `javap -c -v -p FileName` để xem method bytecode và metadata liên quan. Khi gặp một đoạn không hiểu:

1. **Xác định đúng method descriptor**: static hay instance, tham số nào chiếm một/hai slot, có receiver `this` không.
2. **Đọc `stack=..., locals=..., args_size=...`**: `max_stack` là độ sâu slot lớn nhất; `max_locals` là số slot được cấp cho locals; `args_size` là số slot đối số mà `javap` diễn giải.
3. **Khởi tạo bảng locals**: đặt slot cho receiver và các tham số theo descriptor. Đánh dấu slot chưa khởi tạo/không hợp lệ.
4. **Đi theo BCI**: với `iconst_*`/`bipush`/`ldc`, đẩy giá trị; với `iload`, sao chép từ local; với `istore`, pop về local.
5. **Giữ đúng category 1/2** khi đếm stack, đặc biệt với `lload`, `dload`, `lstore`, `dstore`.
6. **Theo dõi thao tác tính toán, gọi, array, field và return**: chúng tiêu thụ/đẩy số lượng operand khác nhau.
7. **Đối chiếu các nhánh và handler**: một đường đi có thể không giống đường đi “thẳng” của output; handler bắt đầu với exception reference trên operand stack.
8. **Phân biệt observation và specification**: compiler có thể chọn opcode khác cho cùng source, nhưng ngữ nghĩa của từng opcode thực thi được JVMS quy định.

### Bảng đối chiếu nhanh

| Nếu thấy trong `javap` | Đọc như sau | Điều không nên suy ra |
| --- | --- | --- |
| `iconst_2` | Đẩy int 2 lên stack | Có một biến Java tên “2” |
| `bipush 100` | Đẩy int 100 từ immediate 8-bit | Nó đẩy một `byte` Java lên stack |
| `ldc #17` | Nạp một constant category 1 qua pool index 17 | Index 17 có nghĩa giá trị hằng số 17 |
| `ldc_w #300` | Nạp qua index 16-bit | Giá trị vừa nạp có kích thước 64 bit |
| `ldc2_w #42` | Nạp `long`/`double` hoặc dynamic constant tương ứng | Chữ 42 chính là giá trị `long` |
| `iload_0` | Sao chép int từ local slot 0 lên stack | Nó xóa slot 0 |
| `istore_1` | Pop int từ stack vào local slot 1 | Nó trả kết quả cho caller |
| `lload_2` | Load long bắt đầu ở slot 2–3 | Long có hai số nguyên độc lập |
| `iinc 1, 1` | Tăng local int slot 1, không thay operand stack | Nó tương đương với phép tăng field |
| `wide iload 300` | Mở rộng encoding của local index | Mở rộng giá trị int thành long |
| `aload_0; getfield` | Nạp reference, rồi đọc field của object | `aload_0` tự đọc toàn bộ object |
| `iaload` | Đọc phần tử array `int` | Đọc local variable bằng `iload` |

## 14. Các lỗi thường gặp

**Lỗi 1 — Nhầm locals là stack.** Nói “`istore` đưa giá trị lên stack” là ngược: `store` lấy giá trị khỏi operand stack rồi ghi vào local.

**Lỗi 2 — Đếm giá trị, bỏ qua số slot.** `[10L,20L]` là hai giá trị category 2 nhưng sâu **4 slots**, không phải 2. Cần đếm đúng để hiểu `max_stack`.

**Lỗi 3 — Nhầm `ldc_w` với `ldc2_w`.** Một lệnh mở rộng **chỉ số constant pool**; lệnh còn lại nạp hằng kiểu `long`/`double` (hoặc constant động cùng loại).

**Lỗi 4 — Cho rằng `byte` được nạp bằng `bload`.** JVM không có nhóm load locals `bload`; `byte` thường được biểu diễn bằng `int` khi đi qua stack/local.

**Lỗi 5 — Cho rằng local slot index bằng số thứ tự tham số.** `this` ở slot 0 với instance method; `long`/`double` chiếm hai slot nên các index không nhất thiết tăng một cho mỗi tham số.

**Lỗi 6 — Đồng nhất `iload` với `iaload`.** `iload` đọc **locals**; `iaload` đọc **array element** và tiêu thụ array reference cùng index trên stack.

**Lỗi 7 — Giả định mọi hằng số phải xuất hiện qua `ldc`.** Các giá trị nhỏ có `iconst_*`/`bipush`/`sipush`; compiler có thể fold các biểu thức hằng.

**Lỗi 8 — Dùng `wide` với bất kỳ opcode.** Nó chỉ hợp lệ khi đứng trước các opcode được JVMS định nghĩa hỗ trợ, không phải “prefix tăng độ rộng” tổng quát.

**Lỗi 9 — Lấy fragment `javap` làm cam kết compiler.** Một compiler khác có thể tái sử dụng locals, loại bỏ biến tạm hoặc dùng một encoding khác. Hãy học **ngữ nghĩa lệnh** và xác nhận trên class đang phân tích.

## 15. Bài tự kiểm tra

**Câu A.** Một method static có `int x` tại local 0 và `int y` tại local 1. Chuỗi nào tính rồi lưu `x+y` vào local 2?

```text
iload_0
iload_1
iadd
istore_2
```

Sau `istore_2`, stack trở lại rỗng và local 2 chứa tổng.

**Câu B.** `ldc_w #300` và `ldc2_w #300` có cùng ý nghĩa vì index đều là 300?

Không. `ldc_w` có index rộng nhưng nạp constant category 1; `ldc2_w` nạp `long`/`double` category 2. Index giống nhau không cho phép tùy ý đổi opcode.

**Câu C.** Sau `lload_0` và `lload_2`, stack chứa hai `long`. Độ sâu tính theo slot?

**4 slot**.

**Câu D.** `iinc 1, 5` có pop hay push operand stack?

**Không**; nó sửa local `int` slot 1 trực tiếp.

**Câu E.** Trong instance method `m(int a, long b, double c)`, tham số `c` bắt đầu ở local slot mấy?

`this` ở 0, `a` ở 1, `b` ở 2–3, nên `c` bắt đầu ở **slot 4** (chiếm 4–5).

**Câu F.** `bipush 127` đẩy kiểu `byte` hay `int`?

**`int`**, do immediate signed byte được sign-extend trước khi đẩy lên operand stack.

## Tài liệu gốc theo Java SE 17

- [JVMS 2.6 — Frames, local variables, operand stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): mô hình frame của từng lần gọi method.
- [JVMS `2.11.1–`2.11.2 — Types và load/store instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.2): loại category 1/2, nhóm load/store locals và constant loading.
- [JVMS 4.7.3 — Code attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): định nghĩa `max_stack`, `max_locals`, `code_length` và bảng exception.
- [JVMS 6.5 — Descriptions of individual instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): định nghĩa `bipush`, `sipush`, `ldc`, `ldc_w`, `ldc2_w`, `iload`, `istore`, `lload`, `iinc`, `wide`, `dup`, `pop`.
- [JVMS 4.4 — Constant pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4): các dạng constant pool entry.
- [Hướng dẫn `javap` Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): sử dụng `-c`, `-v`, `-p` để phân tích class file thực tế.

**Ghi nhớ:** hằng số được **đẩy lên stack**; `load` sao chép từ locals **lên stack**; `store` pop từ stack **về locals**. Để đọc một instruction chính xác, phải biết **kiểu**, **số slot**, **local index**, **các giá trị hiện có trên operand stack**, và lệnh tiếp theo sẽ lấy/đẩy bao nhiêu giá trị.
