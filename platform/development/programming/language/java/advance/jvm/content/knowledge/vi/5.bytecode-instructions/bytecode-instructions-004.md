# Nhóm lệnh `pop`, `dup`, `swap` và ràng buộc kích thước giá trị trong JVM

Java Virtual Machine (JVM) dùng **operand stack** trong mỗi stack frame để giữ các toán hạng và kết quả trung gian khi chạy bytecode. Các lệnh `pop`, `pop2`, `dup`, `dup_x1`, `dup_x2`, `dup2`, `dup2_x1`, `dup2_x2` và `swap` thay đổi **thứ tự hoặc số bản sao giá trị** trên operand stack. Chúng không trực tiếp cộng số, gọi phương thức hay cấp phát đối tượng.

Điều quan trọng nhất: các opcode này phải tôn trọng **computational type category**. Một giá trị `long` hoặc `double` thuộc **category 2**, còn `int`, `float` và reference thuộc **category 1**. Vì thế, `pop` không thể lấy một `long` trực tiếp; `swap` không hoán đổi một `double` với một `int`; và `dup2` có thể sao chép **một giá trị category 2 hoặc hai giá trị category 1**.

## 1. Operand stack thuộc về một lần gọi phương thức

Khi JVM thực thi một method, nó có frame riêng gồm **local variables**, **operand stack** và thông tin phụ trợ. Bytecode đọc local variables hoặc tạo hằng số rồi đẩy giá trị lên operand stack; một lệnh khác có thể lấy các giá trị trên cùng để tính toán, gọi method hoặc ghi field.

```text
Mô hình frame (không phải bố cục RAM vật lý)

Local variables              Operand stack
slot 0: int a = 2             TOP ┌───────────────┐
slot 1: int b = 3                 │      3        │ ← giá trị trên cùng
                                 ├───────────────┤
                                 │      2        │
                                 └───────────────┘
                                      bottom

iload_0   → đẩy 2
iload_1   → đẩy 3
iadd      → lấy hai int, đẩy 5
```

Các hình trong bài đọc stack theo thứ tự **từ trái qua phải = từ dưới lên trên**:

```text
..., value3, value2, value1
                        ↑
                       TOP
```

Dấu `...` tượng trưng cho phần stack sâu hơn không bị lệnh thay đổi. `value1` luôn là giá trị trên cùng trước khi thao tác. Những tên `value1`, `value2` biểu diễn **giá trị logic**, không phải tên biến Java hay byte vật lý.

**`pop` của operand stack khác `Stack.pop()` trong Java Collections.** Ở đây chúng ta học JVM instruction từ class file. Không có phương thức Java chuẩn `dup()` hay `swap()` để người lập trình thao tác trực tiếp lên operand stack trong mã nguồn Java. Compiler chọn bytecode dựa trên cấu trúc nguồn.

## 2. Category 1 và category 2: quy tắc quyết định lệnh hợp lệ

| Loại giá trị trên operand stack | Category | Độ rộng theo mô hình stack | Ví dụ |
| --- | --- | --- | --- |
| `int` | 1 | 1 đơn vị stack (slot/word trong mô hình) | `42`, nhiều phép toán với `byte`, `short`, `char`, `boolean` |
| `float` | 1 | 1 đơn vị | `2.5f` |
| Reference | 1 | 1 đơn vị | Tham chiếu `String`, object, array, kể cả `null` |
| `long` | 2 | 2 đơn vị | `42L` |
| `double` | 2 | 2 đơn vị | `2.5d` |
| `returnAddress` lịch sử | 1 | 1 đơn vị | Gắn với `jsr`/`ret`, không có kiểu khai báo Java tương ứng |

**Category là khái niệm của JVM instruction set**, không khẳng định reference của một JVM 64-bit nhất thiết chiếm 4 hay 8 byte trên RAM. Các kiểu nguyên thủy `byte`, `short`, `char` thường đi qua các phép tính theo dạng `int`; `boolean` không có tập lệnh tính toán số học độc lập. Cũng không thể kết luận object “nằm ở stack”: operand stack giữ **giá trị reference** đến object, không chứa nguyên object theo nghĩa sao chép tất cả field.

Phân biệt hai cách đếm:

- **Số giá trị logic**: `long` là **một giá trị**, hai `int` là **hai giá trị**.
- **Số đơn vị độ rộng**: một `long` chiếm **hai đơn vị**; hai `int` cũng tổng cộng **hai đơn vị**.

Đây là lý do `pop2` và `dup2` có hai kiểu sử dụng hợp lệ. Hậu tố `2` diễn tả **tổng độ rộng tính theo category**, không luôn là “hai object” hay “hai giá trị”.

## 3. `pop` và `pop2`: bỏ kết quả không sử dụng

### `pop` — bỏ đúng một giá trị category 1

```text
Trước: ..., value1
Sau:   ...

Điều kiện: value1 là category 1.
Opcode: pop (0x57)
```

Ví dụ hợp lệ: bỏ một `int`, `float` hoặc reference vừa có trên stack. **Không hợp lệ** nếu `value1` là `long` hoặc `double`, bởi chúng là category 2.

### `pop2` — bỏ tổng cộng hai đơn vị độ rộng

```text
Form 1: hai giá trị category 1
Trước: ..., value2(cat1), value1(cat1)
Sau:   ...

Form 2: một giá trị category 2
Trước: ..., value(cat2)
Sau:   ...

Opcode: pop2 (0x58)
```

`pop2` không được dùng để lấy “nửa trên” của `long` hay `double`. Category 2 luôn là **một giá trị không thể bị xé đôi** bởi nhóm lệnh này.

### Tình huống compiler dùng `pop` và `pop2`

Trong Java source, việc gọi một phương thức trả giá trị rồi **không dùng kết quả** là hợp lệ:

```java
intResult();    // bỏ giá trị int trả về
longResult();   // bỏ giá trị long trả về
```

Đây là các dòng **minh họa đặt trong một method có định nghĩa `intResult()` và `longResult()` phù hợp**, chưa phải chương trình chạy độc lập. Với bytecode do `javac` thông thường tạo, lệnh gọi trả `int` được theo sau bởi `pop`, còn lệnh gọi trả `long` được theo sau bởi `pop2`. Trường hợp method trả `void` không có giá trị trả về để bỏ bằng `pop`.

```text
invokestatic ... intResult:()I
pop
invokestatic ... longResult:()J
pop2
```

Dấu `...` thay cho chỉ mục/names trong constant pool, đây là **minh họa bytecode**, không phải một listing phải giống hệt mọi compiler.

## 4. `dup` và `dup2`: sao chép giá trị trên stack

### `dup` — nhân đôi đúng một category 1

```text
Trước: ..., value1(cat1)
Sau:   ..., value1, value1

Opcode: dup (0x59)
```

`dup` không dùng trực tiếp được với `long` hay `double`. Nếu `value1` là **reference**, hai vị trí stack sau `dup` chứa hai **bản sao giá trị tham chiếu tới cùng object**, không tạo object thứ hai. Nếu `value1` là `int`, hai vị trí giữ cùng giá trị số tại thời điểm thao tác.

Một mẫu compiler phổ biến khi xử lý biểu thức `new Box()`:

```text
new Box
dup
invokespecial Box.<init>:()V
```

Đây là bytecode **minh họa**. `new` đẩy một reference tới object đang trong trạng thái chưa khởi tạo đầy đủ; `dup` giữ thêm bản sao để sau `invokespecial` gọi constructor, biểu thức vẫn có reference kết quả để sử dụng. Verifier còn quản lý trạng thái reference chưa khởi tạo và các ràng buộc constructor. Không nên xem chuỗi trên là cách tùy ý dùng object chưa được khởi tạo.

### `dup2` — sao chép hai category 1 hoặc một category 2

```text
Form 1 (hai cat1):
Trước: ..., value2(cat1), value1(cat1)
Sau:   ..., value2, value1, value2, value1

Form 2 (một cat2):
Trước: ..., value(cat2)
Sau:   ..., value, value

Opcode: dup2 (0x5C)
```

Đối với hai category 1, `dup2` **giữ nguyên thứ tự** cặp giá trị được nhân đôi. Đối với một `long`, nó tạo hai bản sao **toàn bộ giá trị `long`**, không thành bốn giá trị độc lập.

`dup`/`dup2` thường xuất hiện khi compiler cần giữ giá trị của một biểu thức cho **hai mục đích**: vừa gán cho field/array element, vừa để biểu thức gán có kết quả; hoặc vừa làm toán hạng của lệnh tiếp theo, vừa cần giữ bản sao cho kết quả trả về. Không được kết luận source thực hiện deep copy object chỉ từ một opcode `dup`.

## 5. `swap`: đảo vị trí hai category 1

```text
Trước: ..., value2(cat1), value1(cat1)
Sau:   ..., value1, value2

Opcode: swap (0x5F)
```

**Cả hai giá trị phải là category 1.** Các trường hợp sau là không hợp lệ với `swap`:

```text
..., long(cat2), int(cat1)    → không được swap
..., int(cat1), double(cat2) → không được swap
..., long(cat2), long(cat2)  → không được swap
```

Một reference là category 1 nên có thể tham gia `swap` với một `int` nếu việc xếp lại còn đáp ứng yêu cầu kiểu của các lệnh kế tiếp. Tuy nhiên **hợp lệ riêng về category chưa đủ để toàn bộ phương thức hợp lệ**: verifier còn kiểm tra kiểu thực, control-flow và các phép dùng sau đó.

Khi cần sắp xếp lại stack có `long`/`double`, compiler có thể dùng tổ hợp lệnh tải/lưu local variables hoặc các dạng `dup*_x*` hợp lệ, tùy ngữ cảnh. Không có opcode `swap2` tiêu chuẩn trong tập lệnh JVM để đơn giản “đảo mọi cặp giá trị 64 bit”.

## 6. Vì sao có `dup_x1`, `dup_x2`, `dup2_x1`, `dup2_x2`?

`dup` hoặc `dup2` chỉ tạo bản sao **ngay trên cùng**. Với biểu thức gán phức tạp, compiler có thể cần **đặt bản sao ở dưới các toán hạng khác** đang có trên operand stack. Nhóm có hậu tố `_x1`/`_x2` phục vụ điều đó.

Quy ước đọc sơ đồ:

- **cat1**: giá trị category 1 (một đơn vị).
- **cat2**: giá trị category 2 (hai đơn vị).
- `value1`: top của operand stack trước lệnh.
- Dấu `→`: thay đổi stack; vế phải vẫn viết theo thứ tự **dưới → trên**.
- Các giá trị chưa có trên sơ đồ (phần `...`) không đổi.

### 6.1. `dup_x1`: một dạng hợp lệ

Yêu cầu **hai giá trị trên cùng đều là category 1**.

```text
..., value2(cat1), value1(cat1)
→
..., value1, value2, value1

Opcode: dup_x1 (0x5A)
```

Nó sao chép `value1` rồi **chèn bản sao xuống dưới `value2`**. Nếu `value2` là một `double`, không được dùng `dup_x1`.

### 6.2. `dup_x2`: hai dạng hợp lệ

```text
Form 1: ba cat1
..., value3(cat1), value2(cat1), value1(cat1)
→
..., value1, value3, value2, value1

Form 2: một cat2 ở dưới một cat1
..., value2(cat2), value1(cat1)
→
..., value1, value2, value1

Opcode: dup_x2 (0x5B)
```

Giá trị được nhân đôi luôn là **top `value1` category 1**. Hai đơn vị ở dưới nó có thể là **hai cat1** hoặc **một cat2**. Không được thay `value1` bằng `long` rồi cho rằng hậu tố `x2` sẽ tự hợp thức hóa.

### 6.3. `dup2_x1`: hai dạng hợp lệ

```text
Form 1: ba cat1
..., value3(cat1), value2(cat1), value1(cat1)
→
..., value2, value1, value3, value2, value1

Form 2: một cat1 dưới một cat2
..., value2(cat1), value1(cat2)
→
..., value1, value2, value1

Opcode: dup2_x1 (0x5D)
```

Ở form 1, sao chép **cặp** `value2, value1` (cả hai cat1). Ở form 2, sao chép **một giá trị cat2** `value1`. Chúng được chèn vào dưới `value3` hoặc `value2` tương ứng; không tráo thứ tự bên trong cặp được sao chép.

### 6.4. `dup2_x2`: bốn dạng hợp lệ

Đây là trường hợp dễ sai nhất; cần **đọc category của từng giá trị** trước khi vẽ stack.

```text
Form 1: bốn cat1
..., value4(cat1), value3(cat1), value2(cat1), value1(cat1)
→
..., value2, value1, value4, value3, value2, value1

Form 2: hai cat1 ở dưới một cat2
..., value3(cat1), value2(cat1), value1(cat2)
→
..., value1, value3, value2, value1

Form 3: một cat2 ở dưới hai cat1
..., value3(cat2), value2(cat1), value1(cat1)
→
..., value2, value1, value3, value2, value1

Form 4: hai cat2
..., value2(cat2), value1(cat2)
→
..., value1, value2, value1

Opcode: dup2_x2 (0x5E)
```

Tương tự `dup2`, phần được sao chép ở top có tổng độ rộng **hai đơn vị**: **hai cat1** hoặc **một cat2**. Phần nằm dưới cũng có tổng độ rộng **hai đơn vị**: hai cat1 hoặc một cat2. Bốn cách phối hợp hợp lệ sinh ra **bốn form** trên.

### Bảng tổng hợp opcode và điều kiện

| Instruction | Opcode (hex) | Phần top bắt buộc | Ý nghĩa |
| --- | --- | --- | --- |
| `pop` | `57` | 1 cat1 | Bỏ một giá trị |
| `pop2` | `58` | 2 cat1 **hoặc** 1 cat2 | Bỏ hai đơn vị |
| `dup` | `59` | 1 cat1 | Sao chép top |
| `dup_x1` | `5A` | 2 cat1 | Sao chép top xuống dưới một cat1 |
| `dup_x2` | `5B` | 3 cat1 **hoặc** cat2 + cat1 | Sao chép top xuống dưới hai đơn vị |
| `dup2` | `5C` | 2 cat1 **hoặc** 1 cat2 | Sao chép hai đơn vị top |
| `dup2_x1` | `5D` | 3 cat1 **hoặc** cat1 + cat2 | Sao chép hai đơn vị top, chèn dưới một cat1 |
| `dup2_x2` | `5E` | Bốn dạng ở mục 6.4 | Sao chép hai đơn vị top, chèn dưới hai đơn vị |
| `swap` | `5F` | 2 cat1 | Đổi thứ tự hai giá trị |

**Lưu ý:** biểu thức “hai đơn vị” là độ rộng theo mô hình JVM, không phải số phần tử của collection, số byte, hoặc thao tác lên hai biến Java. Các thứ tự trong bảng điều kiện được hiểu **từ dưới lên trên**, còn sơ đồ đầy đủ mới xác định chính xác `value1` nằm ở đâu.

## 7. Trường hợp hợp lệ và không hợp lệ: tự suy ra bằng category

Giả sử stack có các giá trị sau; các số chỉ để phân biệt giá trị, không phải bytecode opcode:

| Stack trước lệnh (dưới → trên) | Lệnh | Kết quả / lý do |
| --- | --- | --- |
| `..., int(7)` | `dup` | `..., 7, 7`, hợp lệ |
| `..., long(7L)` | `dup` | **Không hợp lệ**: top cat2 |
| `..., long(7L)` | `dup2` | `..., 7L, 7L`, hợp lệ |
| `..., int(1), int(2)` | `dup2` | `..., 1, 2, 1, 2`, hợp lệ |
| `..., double(2.0)` | `pop` | **Không hợp lệ**: top cat2 |
| `..., double(2.0)` | `pop2` | `...`, hợp lệ |
| `..., int(1), long(2L)` | `pop2` | `..., 1`, hợp lệ vì chỉ lấy top long |
| `..., long(1L), int(2)` | `pop2` | **Không hợp lệ**: không thể lấy top int và nửa long |
| `..., int(1), float(2f)` | `swap` | `..., 2f, 1`, hợp lệ về category |
| `..., int(1), long(2L)` | `swap` | **Không hợp lệ**: một toán hạng cat2 |
| `..., long(1L), int(2)` | `dup_x2` | `..., 2, 1L, 2`, form 2 |
| `..., int(1), long(2L)` | `dup2_x1` | `..., 2L, 1, 2L`, form 2 |

Điểm gây nhầm phổ biến ở `pop2`: nếu top là cat2, lệnh **chỉ bỏ một giá trị đó**, bất kể còn bao nhiêu giá trị cat1 ở dưới. Nếu top là cat1 nhưng ngay dưới là cat2, không có form hợp lệ cho `pop2` vì thiếu một cat1 thứ hai trên cùng.

Không thể xử lý giá trị cat2 như hai cat1 bằng cách gọi `pop` hai lần. Category 2 là đơn vị nguyên vẹn đối với các instruction này. Đặc tả JVM quy định những mẫu stack hợp lệ, và **bytecode verifier** dựa vào các mẫu kiểu trong quá trình kiểm tra.

## 8. Tại sao `javac` cần những lệnh này?

Ở Java source, một phép gán có thể đồng thời **tác động nơi lưu giá trị** và **trả về giá trị biểu thức**. Ví dụ `int y = (x = 5);`: phép gán `x = 5` phải để lại một giá trị để gán tiếp vào `y`. Compiler có thể giữ bản sao giá trị trên operand stack thay vì nạp lại từ local variables.

Với phép gán vào field hoặc array, thứ tự stack còn bao gồm **reference của object/array**, index và giá trị mới. Các biến thể `dup_x1`, `dup_x2`, `dup2_x1`, `dup2_x2` cho phép compiler giữ một bản sao của kết quả biểu thức **bên dưới** những toán hạng mà `putfield` hoặc `xastore` cần lấy.

### Ví dụ khái niệm: cập nhật field rồi vẫn giữ giá trị

Giả sử bên trong một phương thức hợp lệ có:

```java
Box box = new Box();
int result = (box.value = 9);
```

Trong một chiến lược biên dịch thông thường, trước `putfield` có `objectref` và `int value` trên stack. Nhưng biểu thức gán còn cần kết quả `9`, do đó compiler có thể dùng `dup_x1`:

```text
Trước: ..., objectref(cat1), value=9(cat1)
dup_x1:
       ..., 9, objectref, 9
putfield Box.value:I:
       ..., 9            // bản sao dùng làm kết quả biểu thức
```

`Box` và `value` ở đây là kiểu/field giả định cho đoạn minh họa; ví dụ chạy được đầy đủ nằm ở mục 9. Sơ đồ chỉ trình bày một **mẫu biên dịch hợp lý**, không bắt mọi compiler hay JIT giữ đúng các lệnh trung gian này.

### Ví dụ khái niệm: gán phần tử mảng

Để thực thi `result = (numbers[index] = 9)`, `iastore` cần ba toán hạng:

```text
..., arrayref(cat1), index(cat1), value=9(cat1)
```

Compiler có thể dùng `dup_x2` (form 1) nhằm giữ bản sao `9`:

```text
Trước:     ..., arrayref, index, 9
dup_x2:    ..., 9, arrayref, index, 9
iastore:   ..., 9
```

Nếu giá trị phần tử là `long` (cat2), chẳng hạn `long[]`, thì việc giữ bản sao của giá trị rộng và chèn dưới `arrayref`, `index` (hai cat1) có thể dùng **`dup2_x2` form 2**:

```text
Trước:      ..., arrayref(cat1), index(cat1), value(cat2)
dup2_x2:    ..., value(cat2), arrayref, index, value(cat2)
lastore:    ..., value(cat2)
```

Vậy sự khác biệt giữa `dup_x2` và `dup2_x2` xuất phát từ **category của giá trị phần tử**, chứ không phải kích thước mảng hay số dấu ngoặc trong source.

## 9. Thực hành Java 17+: sinh bytecode và đọc bằng `javap`

Tạo **một tệp** `StackInstructionDemo.java` với nội dung sau:

```java
public class StackInstructionDemo {
    static class Box {
        int value;
    }

    static int intResult() {
        return 7;
    }

    static long longResult() {
        return 9L;
    }

    static int assignedField(Box box) {
        int result = (box.value = 12);
        return result;
    }

    static int assignedElement(int[] numbers, int index) {
        int result = (numbers[index] = 21);
        return result;
    }

    static long assignedLongElement(long[] numbers, int index) {
        long result = (numbers[index] = 34L);
        return result;
    }

    public static void main(String[] args) {
        intResult();
        longResult();

        Box box = new Box();
        int[] numbers = new int[1];
        long[] longNumbers = new long[1];

        System.out.println("field: " + assignedField(box));
        System.out.println("element: " + assignedElement(numbers, 0));
        System.out.println("long element: "
                + assignedLongElement(longNumbers, 0));
        System.out.println("stored: " + box.value
                + ", " + numbers[0] + ", " + longNumbers[0]);
    }
}
```

Từ thư mục chứa tệp, dùng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 StackInstructionDemo.java
java StackInstructionDemo
```

**Standard output chính xác:**

```text
field: 12
element: 21
long element: 34
stored: 12, 21, 34
```

Các method chỉ trả giá trị đã gán, không dùng luồng chạy phức tạp hay thời gian thực, nên bốn dòng stdout không phụ thuộc JIT. Việc `intResult()` và `longResult()` không có tác dụng phụ quan sát được ở source; tuy vậy compiler tạo bytecode từ các method invocation thông thường và có thể phải bỏ các giá trị trả về không dùng tới.

### 9.1. Xem instruction trong class file

```bash
javap -c -p StackInstructionDemo
javap -c -p 'StackInstructionDemo$Box'
```

Trong **Bash** và **PowerShell**, dấu nháy đơn bảo vệ ký tự `$` trong tên nested class; với **Windows cmd.exe**, hãy dùng dấu nháy kép thay thế. Lệnh thứ hai là tùy chọn để xem lớp `Box`.

Tìm các đoạn bytecode, **không cần khớp tuyệt đối chỉ số offset hay constant pool**:

| Method | Instruction đáng quan sát | Vì sao có thể xuất hiện |
| --- | --- | --- |
| `main` | `invokestatic ... intResult`, `pop` | Bỏ giá trị `int` không dùng |
| `main` | `invokestatic ... longResult`, `pop2` | Bỏ giá trị `long` không dùng |
| `main` | `new`, `dup`, `invokespecial ... Box.<init>` | Giữ tham chiếu object khi gọi constructor |
| `assignedField` | `dup_x1`, `putfield` | Giữ giá trị gán `int` đồng thời ghi field |
| `assignedElement` | `dup_x2`, `iastore` | Giữ giá trị gán `int` đồng thời ghi array element |
| `assignedLongElement` | `dup2_x2`, `lastore` | Giữ giá trị gán `long` (cat2) đồng thời ghi array element |

**Cần đọc kết quả `javap` trên công cụ thật.** Những instruction trong bảng là các mẫu điển hình của `javac` cho mã này, nhưng các trình biên dịch Java hoặc phiên bản/chiến lược tối ưu có thể dùng cách sắp xếp khác mà vẫn hợp lệ. `javap -c` cho thấy **bytecode trong class file**, không phải mã máy mà JIT về sau thực thi.

### 9.2. Diễn giải nhóm thao tác trên field

Với `assignedField(Box box)`, mục tiêu là vừa thực hiện `box.value = 12`, vừa giữ kết quả cho biến `result`. Có thể thấy chuỗi khái niệm:

```text
aload_0            // reference box
bipush 12          // int 12
dup_x1             // ..., ref, 12 → ..., 12, ref, 12
putfield ... value  // tiêu thụ ref, 12; còn 12
istore_1           // gán result
iload_1
ireturn
```

Nó hợp lệ bởi **reference** và **int** đều là category 1. Nếu thay field thành `long`, compiler không được mù quáng dùng cùng `dup_x1` vì top `long` là category 2; cần chọn instruction hợp lệ với dạng stack mới.

### 9.3. Diễn giải `dup2_x2` với mảng `long`

Trước `lastore`, stack có `long[]` reference, index và `long` value:

```text
..., arrayref(cat1), index(cat1), 34L(cat2)
```

`dup2_x2` form 2 làm thành:

```text
..., 34L(cat2), arrayref(cat1), index(cat1), 34L(cat2)
```

Lệnh `lastore` lấy **arrayref, index, long value ở top theo quy tắc toán hạng**; bản sao `34L` phía dưới vẫn là giá trị biểu thức gán. Cách hiểu “dup2 sao chép hai số ở trên” sẽ sai ngay trong trường hợp này vì top chỉ chứa **một** giá trị logic `long`.

## 10. Bytecode verifier ngăn các dạng stack bất hợp lệ

Các instruction trong `.class` phải đáp ứng quy tắc về **số lượng, thứ tự, category và loại giá trị**. JVM verifier kiểm tra dữ liệu kiểu của stack và local variables theo control flow trước khi cho bytecode được thực thi theo điều kiện đặc tả.

Ví dụ **bytecode giả định sai**:

```text
lconst_0   // đẩy một long: category 2
pop        // SAI: pop đòi top category 1
return
```

Đây **không phải source Java hợp lệ** và không được chạy như file `.java`; nó minh họa một class file do bytecode assembler/tool sinh **sai**. Một JVM tuân thủ đặc tả sẽ không coi thao tác đó là hợp lệ; khi xác minh có thể xuất hiện `VerifyError` (thuộc nhóm `LinkageError`). Không nên cố tạo lỗi bằng cách sửa vài byte hex trong class file thực, vì làm thế có thể sinh `ClassFormatError` do hỏng cấu trúc trước khi tới bước verification.

Tương tự:

```text
dconst_0
dup         // SAI: double là category 2
```

và:

```text
iconst_1
lconst_0
swap        // SAI: top là long (category 2)
```

Không có khái niệm “chỉ cảnh báo nhưng JVM tự sửa stack” cho những chuỗi sai category này. Verifier cũng không chỉ xem từng opcode độc lập: dữ liệu trên các nhánh hợp lưu phải có trạng thái stack và kiểu phù hợp; một `ireturn` phải trả giá trị phù hợp với descriptor của method; các lời gọi method và truy cập field cần toán hạng đúng kiểu.

## 11. Stack depth, `max_stack` và nhầm lẫn về bộ nhớ

Trong mỗi `Code` attribute, class file lưu thông tin như **`max_stack`** và **`max_locals`**. `max_stack` biểu diễn **độ sâu tối đa của operand stack tính theo đơn vị độ rộng**, không phải luôn là số lượng giá trị logic trên stack.

Ví dụ, sau một `dup2` với một `long` ở top, hai bản sao `long` chiếm **bốn đơn vị stack** tổng cộng, dù chỉ có **hai giá trị logic**. Nếu mã giữ thêm reference hoặc index phía dưới, các đơn vị tương ứng cũng cộng vào độ sâu.

Có thể xem thông tin do compiler tạo:

```bash
javap -v -p StackInstructionDemo
```

Tìm phần `Code:`, dòng `stack=...` và `locals=...`. Kết quả cụ thể phụ thuộc bytecode thực tế của compiler và method được xem. `max_stack` **không** cho biết lượng bộ nhớ heap, không bằng kích thước JVM thread stack tính theo byte, và không có nghĩa mỗi giá trị cat2 luôn chiếm đúng 8 byte vật lý trong thanh ghi/bộ nhớ của trình biên dịch JIT.

### Giá trị category 2 ở local variables

Với local-variable array, `long` và `double` chiếm **hai chỉ số slot liên tiếp** trong mô hình JVM; reference và `int` chiếm một slot. Quy tắc này liên quan cùng phân loại category, nhưng lệnh `dup2` tác động lên **operand stack**, không nhân đôi các ô local variables. Muốn đọc/ghi local variables có các instruction riêng như `lload`, `lstore`, `iload`, `istore`.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`pop2` luôn xóa hai giá trị.” | Xóa **hai cat1** hoặc **một cat2**. |
| “`dup2` nhân đôi mọi thứ ở top theo hai object.” | Nhân đôi tổng độ rộng hai đơn vị, có thể là **một long/double**. |
| “`dup` của reference tạo object mới.” | Chỉ nhân đôi **giá trị reference**, không gọi `new`. |
| “`swap` dùng được với `long` nếu JVM 64-bit.” | Không; cả hai top value phải là category 1 theo JVM Specification. |
| “Đuôi `_x2` nghĩa là nhân đôi hai lần.” | `_x2` diễn tả chèn bản sao sâu xuống dưới **hai đơn vị**; phạm vi sao chép do `dup` hoặc `dup2` quyết định. |
| “Hai giá trị cat1 tương đương một cat2 trong mọi instruction.” | Chúng có cùng **tổng độ rộng** nhưng khác số lượng giá trị và kiểu; chỉ một số instruction có nhiều form hợp lệ. |
| “Bytecode có `dup` tức là chương trình Java cố ý tạo bản sao để dùng lại.” | Thường là chiến lược compiler giữ kết quả trung gian, chẳng hạn khi gán field, constructor hoặc mảng. |
| “`javap` cho mã CPU cuối cùng.” | Nó giải mã class-file bytecode; JIT và interpreter là bước runtime khác. |
| “Một lệnh hợp lệ về category thì cả method chắc chắn hợp lệ.” | Verifier còn xét loại giá trị, descriptor, init state, độ sâu stack và các nhánh control flow. |

## 13. Bài luyện đọc operand stack

**Bài 1:** Stack `..., int A, int B`; chạy `dup_x1`.  
**Đáp án:** `..., B, A, B`. Hai giá trị đều cat1.

**Bài 2:** Stack `..., long L`; muốn sao chép giá trị `L` cho một bước tính tiếp theo. Chọn `dup` hay `dup2`?  
**Đáp án:** `dup2`; `long` là một giá trị category 2.

**Bài 3:** Stack `..., double D, int I`; chạy `dup_x2`.  
**Đáp án:** `..., I, D, I` theo form 2 vì top là cat1 và giá trị bên dưới là cat2.

**Bài 4:** Stack `..., long L, int I`; chạy `pop2`.  
**Đáp án:** **Không hợp lệ**; top là cat1 nhưng ngay dưới là cat2. `pop2` không chia `long` thành một đơn vị để bỏ.

**Bài 5:** Stack `..., int X, int Y, long L`; chạy `dup2_x2`.  
**Đáp án:** `..., L, X, Y, L` theo form 2. Giá trị `L` cat2 được nhân đôi và chèn dưới hai cat1.

**Bài 6:** Stack `..., long X, long Y`; chạy `dup2_x2`.  
**Đáp án:** `..., Y, X, Y` theo form 4. Cả hai đều cat2; không thể thay bằng `swap`.

**Bài 7:** Sau `new` và trước constructor, compiler dùng `dup` trên reference. Có hai đối tượng được tạo không?  
**Đáp án:** Không. `dup` tạo hai bản sao cùng reference (đang ở trạng thái uninitialized được verifier theo dõi), không thực hiện cấp phát object mới.

**Bài 8:** Vì sao phép gán `long result = (array[index] = 34L)` có thể gắn với `dup2_x2`?  
**Đáp án:** Bản sao của giá trị `long` cần được giữ làm **kết quả biểu thức**, trong khi `lastore` vẫn cần bộ ba `arrayref(cat1), index(cat1), value(cat2)`.

### Tự kiểm tra sau khi học

1. Có phân biệt được **category** với **số giá trị logic** hay không?
2. Có xác định đúng **TOP** là phần bên phải trong ký hiệu `..., value2, value1` không?
3. Với `dup_x2`, có nhớ rằng **giá trị top phải là cat1** ở cả hai form không?
4. Với `dup2_x2`, có phân tích đủ **bốn form** hợp lệ không?
5. Có biết dùng `javap -c -p` để xác minh instruction mà `javac` thực sự tạo không?

**Tài liệu đối chiếu:** *The Java Virtual Machine Specification*, chương **6.5 Instructions** (các mục `pop`, `pop2`, `dup`, `dup_x1`, `dup_x2`, `dup2`, `dup2_x1`, `dup2_x2`, `swap`): https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html. Khi học cú pháp các form, ưu tiên bảng operand stack của đặc tả thay vì đoán từ tên opcode.

Kết luận thực hành: đọc `pop`, `dup`, `swap` bằng cách **xác định category của từng giá trị theo thứ tự từ đáy lên đỉnh**, chọn đúng form instruction rồi viết lại stack sau thao tác. Chỉ khi toàn bộ các biến đổi này hợp lệ về category và các lệnh kế tiếp dùng đúng kiểu thì JVM mới có thể xác minh và thực thi bytecode như dự kiến.