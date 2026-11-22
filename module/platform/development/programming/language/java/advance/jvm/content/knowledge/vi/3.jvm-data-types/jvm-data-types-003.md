# `long`, `double` và hai vị trí trong mảng biến cục bộ của JVM

Trong Java, `long` và `double` đều có kích thước logic **64 bit**. Nhưng khi xem bytecode bằng `javap`, bạn sẽ thấy điều khác dễ gây ngạc nhiên: một tham số `long` hoặc `double` dùng **hai vị trí liên tiếp** (two local-variable slots) trong frame của phương thức. Nếu tham số đầu tiên là `long`, tham số tiếp theo của phương thức `static` thường bắt đầu tại **chỉ số 2**, không phải 1.

Đây là quy tắc của **Java Virtual Machine Specification (JVMS)** dành cho cấu trúc biến cục bộ trong frame, không phải quy tắc “hai biến Java” hay khẳng định chính xác rằng JVM vật lý dành hai ô RAM cố định. Hiểu đúng sẽ giúp đọc `iload`, `lload`, `dload`, `max_locals`, các tham số bytecode và thông báo verifier.

## 1. Phân biệt kích thước giá trị và số vị trí JVM

| Kiểu Java | Độ rộng giá trị theo ngữ nghĩa | Loại tính toán của JVM | Số local-variable slots khi nằm trong frame |
| --- | --- | --- | --- |
| `boolean`, `byte`, `short`, `char` | Theo kiểu Java tương ứng; một số được xử lý bằng `int` ở mức bytecode | **Category 1**, chủ yếu là `int` | **1** |
| `int` | 32 bit | **Category 1** | **1** |
| `float` | 32 bit | **Category 1** | **1** |
| `reference` (ví dụ `String`) | Không nên suy ra kích thước con trỏ vật lý từ bytecode | **Category 1** | **1** |
| **`long`** | **64 bit**, số nguyên có dấu | **Category 2** | **2** |
| **`double`** | **64 bit**, IEEE 754 double precision | **Category 2** | **2** |

**Category 1/2** là phân loại dùng trong **mô hình thực thi của JVM**. Với category 2, giá trị `long`/`double` có đơn vị độ sâu **2** trên operand stack và dùng **2 vị trí** trong mảng local variables. Giá trị vẫn là **một** `long`/`double`, không phải hai `int` độc lập.

Ví dụ:

```java
long distance = 9_000_000_000L;
double ratio = 0.75;
int attempts = 3;
```

Trong source có **ba biến**. Tại một thời điểm khi cả ba cùng cần local slots, chúng cần **2 + 2 + 1 = 5 vị trí** trong local-variable array, chưa tính receiver `this`, tham số khác, dữ liệu tạm khác và khả năng tái sử dụng slot.

**Không nhầm với**:

- **Heap:** trường `long` trong object hoặc phần tử `long[]` không “chiếm hai phần tử mảng”. Quy tắc hai slot đang bàn thuộc **local-variable array của frame**.
- **Bộ nhớ vật lý:** một slot là khái niệm đánh chỉ số mà bytecode truy cập; JVM có quyền dùng thanh ghi CPU, native stack hoặc tối ưu hóa nội bộ. Không được kết luận “mỗi slot chiếm đúng 4 byte RAM thực”.
- **Số bit của primitive:** `double` vẫn là một giá trị floating-point 64-bit, dù có hai local-variable slots.

## 2. Frame và local-variable array là gì?

Mỗi lần JVM gọi một phương thức Java, mô hình thực thi tạo một **frame** gắn với lời gọi đó. Một frame gồm:

1. **Local-variable array:** giữ tham số và biến cục bộ cần dùng bằng các chỉ số 0, 1, 2, ...
2. **Operand stack:** nơi các lệnh bytecode đưa giá trị vào, lấy toán hạng ra và trả kết quả.
3. Thông tin phục vụ dynamic linking, kết quả trả về và cơ chế thực thi phương thức.

Độ dài local-variable array của phương thức được chỉ định bằng **`max_locals`** trong `Code` attribute của class file. `max_locals` là **số vị trí (slot)** cần có, không phải số biến được khai báo trong source. `max_stack` là độ sâu tối đa của operand stack tính theo **đơn vị độ sâu**.

Một frame chỉ tồn tại cho lời gọi tương ứng trong mô hình JVM. Các frame đang hoạt động thuộc một JVM thread; nếu phương thức đệ quy, mỗi lần gọi có **frame riêng** với local variables riêng. Khác với heap, local-variable array không phải một bảng biến toàn cục chia sẻ giữa mọi thread.

### 2.1. Bắt đầu từ index 0

Các local variables được đánh chỉ số liên tiếp: `0`, `1`, `2`, ... `max_locals - 1`. Với bytecode tải `lload 0`, số `0` là **chỉ số bắt đầu** của cặp slot chứa giá trị `long`. Giá trị đó chiếm cả slot `0` lẫn `1`.

Ví dụ theo mô hình đặc tả:

```text
Local-variable array
Index:   0         1         2         3         4
       ┌─────────┬─────────┬─────────┬─────────┬─────────┐
       │    long value     │   double value    │   int   │
       │ bắt đầu index 0   │ bắt đầu index 2   │ index 4 │
       └─────────┴─────────┴─────────┴─────────┴─────────┘
           ↑                   ↑                     ↑
        lload 0             dload 2              iload 4
```

Giá trị `long` **chỉ được truy xuất bằng index thấp hơn của cặp**, tức `0`; tương tự `double` bằng `2`. Index `1` hoặc `3` **không phải một giá trị riêng** mà bạn có thể dùng `iload` hoặc `lload` để đọc phần còn lại.

### 2.2. Index của `long` không bắt buộc là số chẵn

Quy tắc là **hai vị trí liên tiếp**, không phải “phải bắt đầu tại số chẵn”. Một `long` hợp lệ có thể ở `1` và `2` (ví dụ tham số đầu của instance method sau `this`), hoặc `3` và `4`. JVM Specification **không bắt buộc căn chỉnh 64-bit theo index chẵn** trong local-variable array.

## 3. Vì sao slot kế tiếp phải bỏ qua?

Xem khai báo:

```java
static void report(long count, double price, int batch) {
    // ...
}
```

Vì là phương thức `static`, tham số bắt đầu từ index 0:

| Biến tham số | Kiểu | Vị trí trong frame |
| --- | --- | --- |
| `count` | `long` | **0 và 1**; đọc bằng `lload 0` |
| `price` | `double` | **2 và 3**; đọc bằng `dload 2` |
| `batch` | `int` | **4**; đọc bằng `iload 4` |

Cách tính index kế tiếp:

```text
start = 0                // static method: tham số đầu tiên
count: [0, 1]            // long  → dịch +2
price: [2, 3]            // double → dịch +2
batch: [4]               // int → dịch +1
next free index >= 5
```

Mảng local variables phải đủ chứa tham số tới slot 4, nên riêng các tham số yêu cầu **ít nhất 5 slots**. Nếu body có thêm biến `double` còn cần slot tại 5 và 6, `max_locals` ít nhất là 7.

**Quan trọng:** `count` là **một tham số**, dù cần hai slot. Khi API Java reflection trả `Method.getParameterCount()` cho phương thức trên, kết quả là **3**, không phải 5. Việc đếm tham số nguồn/reflection và việc đánh index local slots là hai hệ quy chiếu khác nhau.

### 3.1. Phương thức instance: slot 0 dành cho `this`

Đối với phương thức instance:

```java
double calculate(long count, double price, int batch) {
    return count * price + batch;
}
```

Receiver `this` nằm ở **index 0**; tham số thật bắt đầu từ 1:

| Vị trí | Nội dung |
| --- | --- |
| 0 | `this` — reference tới object nhận lời gọi |
| 1, 2 | `count` — một `long` |
| 3, 4 | `price` — một `double` |
| 5 | `batch` — một `int` |

Như vậy, cùng ba kiểu tham số `long, double, int`, phương thức instance cần **ít nhất 6 slots** để truyền receiver và tham số, còn phương thức `static` chỉ cần 5 slots cho tham số. Trong bytecode của instance method, `lload_1` (không phải `lload_0`) sẽ tải `count`.

`this` không phải một local variable do lập trình viên khai báo bằng cú pháp `long`/`double`, nhưng là receiver cần có trong frame của instance method theo quy tắc gọi phương thức JVM.

## 4. Quy tắc ghi đè nửa sau của một cặp slot

JVMS còn có một chi tiết quan trọng khi hiểu bytecode hoặc viết bytecode thủ công:

- Một `long`/`double` được đặt ở index `n` sẽ chiếm **n và n+1**.
- Chỉ có thể **load** toàn bộ giá trị category 2 qua index `n`.
- Có thể thực hiện **store** một giá trị khác vào index `n+1`, nhưng việc đó **làm giá trị `long`/`double` bắt đầu ở `n` không còn hợp lệ để sử dụng**.

Minh họa khái niệm:

```text
Ban đầu:
slot 0 ─┐
        ├── long value L (đọc bằng lload 0)
slot 1 ─┘

Sau khi istore 1:
slot 0 ─── dữ liệu cũ không còn tạo thành long hợp lệ
slot 1 ─── int value M

Sau đó lload 0 không còn hợp lệ theo kiểu trạng thái local variables.
```

Đây **không phải kỹ thuật cắt `long` thành hai nửa để đọc dữ liệu**, cũng không phải cách truy cập từng 32 bit. Với bytecode không nhất quán, bộ kiểm tra kiểu/verifier có thể từ chối class (ví dụ `VerifyError`). Bytecode hợp lệ chỉ load category-2 value sau khi cặp slot đã được thiết lập theo trạng thái kiểu đúng.

Trình biên dịch có thể **tái sử dụng slot** khi hai biến không đồng thời cần sống. Vì vậy không thể lấy tổng số biến từng xuất hiện trong source nhân kích thước để suy ra chính xác `max_locals`.

## 5. Các lệnh bytecode dành cho local variables

| Thao tác | Với `int` (1 slot) | Với `long` (2 slots) | Với `double` (2 slots) |
| --- | --- | --- | --- |
| Tải local lên operand stack | `iload index` | `lload index` | `dload index` |
| Lưu từ operand stack xuống local | `istore index` | `lstore index` | `dstore index` |
| Dạng rút gọn index 0…3 | `iload_0`…`iload_3` | `lload_0`…`lload_3` | `dload_0`…`dload_3` |
| Trả giá trị khỏi phương thức | `ireturn` | `lreturn` | `dreturn` |
| Phép cộng | `iadd` | `ladd` | `dadd` |

Ví dụ `lload_0` đọc **một giá trị `long` trải trên slot 0–1**. Nó **không** đọc `slot 0` rồi cần một `lload_1` riêng. Cũng vậy, `dstore 5` ghi một `double` bắt đầu tại index 5, sử dụng slot 5–6.

Một số opcode hỗ trợ thao tác theo index lớn qua tiền tố `wide`, nhưng `wide` là cơ chế **mở rộng kích thước toán hạng chỉ số của lệnh**, không phải từ khóa chỉ `long`/`double` và cũng không thay đổi quy tắc hai slot.

### 5.1. `lconst`, `dconst` và `ldc2_w`

JVM có những lệnh tải hằng phù hợp: `lconst_0`, `lconst_1` cho hai giá trị `long` nhỏ; `dconst_0`, `dconst_1` cho `double` 0.0 và 1.0; với nhiều hằng `long`/`double` khác, trình biên dịch thường dùng `ldc2_w` để tải từ constant pool. Sau đó mới dùng `lstore`/`dstore` nếu cần lưu giá trị đó vào local variables.

Ví dụ `long x = 10L;` có thể tạo bytecode `ldc2_w` rồi `lstore` tùy chỉ số; đừng dự đoán rằng nó luôn dùng một lệnh `lconst_10` (opcode đó **không tồn tại**).

## 6. Hai slot local khác operand stack như thế nào?

Ở **local-variable array**, một `long`/`double` chiếm **hai local-variable slots liên tiếp**. Nhưng ở **operand stack** (ngăn xếp toán hạng), nó là **một giá trị category 2** làm độ sâu của stack tăng **hai đơn vị**. Không có quyền tách nó thành hai giá trị category 1 một cách tùy tiện.

Ví dụ một phép cộng `long`:

```java
static long add(long a, long b) {
    return a + b;
}
```

Giả sử dùng thứ tự bytecode điển hình:

```text
Local variables:
  slot 0–1: long a
  slot 2–3: long b

Operand stack:                         độ sâu (đơn vị)
  [empty]                              0
  lload_0  → [a]                       2
  lload_2  → [a, b]                    4
  ladd     → [a+b]                     2
  lreturn  → [empty], trả một long     0
```

Vì hai toán hạng `long` đồng thời nằm trên operand stack, ví dụ này cần **`max_stack >= 4`**. Nó đồng thời cần ít nhất **`max_locals = 4`** cho hai tham số; đây là **hai chỉ số kích thước độc lập**.

Đối với `double`, `dload` và `dadd` tuân theo cùng nguyên tắc category 2. Đừng hình dung JVM cộng “nửa cao” với “nửa thấp” bằng hai lệnh `iadd`: JVM dùng đúng phép toán `dadd`/ `ladd` trên **một giá trị 64-bit có kiểu**.

Một số lệnh thao tác stack có quy tắc category riêng:

- `pop` chỉ loại bỏ một giá trị **category 1**; muốn loại bỏ một giá trị **category 2**, dùng `pop2`.
- `pop2` có thể lấy **một** giá trị category 2 **hoặc hai** giá trị category 1.
- `dup2` có thể nhân đôi **một** giá trị category 2 hoặc **hai** giá trị category 1 trên đỉnh theo hình thức hợp lệ.
- `swap` chỉ hoán đổi hai giá trị category 1; không được dùng để tách hay tráo trực tiếp một `long`/`double` thành hai nửa.

**Ghi nhớ:** operand stack có **đơn vị độ sâu 2**, không có nghĩa category-2 value gồm **hai phần tử độc lập** để `pop`, `swap` hoặc truy cập riêng.

## 7. Chương trình Java 17+ hoàn chỉnh và cách đọc bytecode

Tạo tệp **`SlotDemo.java`**:

```java
public class SlotDemo {

    // static: tham số đầu bắt đầu ở local slot 0.
    static double weighted(long items, double unitPrice, int fee) {
        double total = items * unitPrice + fee;
        return total;
    }

    // instance: local slot 0 là "this".
    double adjust(long items, double unitPrice) {
        double total = items * unitPrice;
        return total;
    }

    public static void main(String[] args) {
        long count = 3L;
        double price = 2.5;
        double result = weighted(count, price, 1);

        System.out.println("result = " + result);
        System.out.println("adjusted = " + new SlotDemo().adjust(4L, 1.25));
    }
}
```

Biên dịch/chạy:

```bash
javac SlotDemo.java
java SlotDemo
```

**Stdout chính xác:**

```text
result = 8.5
adjusted = 5.0
```

Tại `weighted(3L, 2.5, 1)`, kết quả là `3 × 2.5 + 1 = 8.5`. Tại `adjust(4L, 1.25)`, kết quả là `4 × 1.25 = 5.0`. Các giá trị biểu diễn nhị phân chính xác ở ví dụ này nên cách hiển thị ngắn không có sai số làm tròn đáng chú ý.

### 7.1. Mở bytecode bằng công cụ JDK

```bash
# Hiện lệnh bytecode, descriptor và chi tiết Code attribute.
javap -c -v -p SlotDemo

# Nếu muốn debug table tên biến cục bộ dễ đọc hơn:
javac -g SlotDemo.java
javap -c -v -p SlotDemo
```

Trong kết quả hãy tìm phần **`static double weighted(long, double, int)`** và **`Code:`**. Với bytecode thông thường do `javac` sinh từ đoạn trên, sơ đồ slot là:

```text
weighted(long items, double unitPrice, int fee)
(static, không có this)

  index     nội dung
  0, 1      items        (J = long)
  2, 3      unitPrice    (D = double)
  4         fee          (I = int)
  5, 6      total        (D = double)

  max_locals cần ít nhất 7.
  method descriptor: (JDI)D
```

Dãy lệnh bytecode minh họa cho body này:

```text
lload_0       // đọc long ở local 0–1
l2d           // đổi long thành double
dload_2       // đọc double ở local 2–3
dmul          // nhân hai double
iload 4       // đọc int ở local 4
i2d           // đổi int thành double
dadd          // cộng
dstore 5      // lưu total ở local 5–6
dload 5       // tải total
dreturn       // trả double
```

Đây là **phần trích minh họa logic** của các opcode; `javap` thực tế còn hiển thị offset, phần khai báo và metadata khác. Cách chọn từng opcode/slot cho các biến không bắt buộc phải giống tuyệt đối ở mọi compiler/phiên bản; **quy tắc về cặp slots và ý nghĩa opcode là bắt buộc**.

**Giải thích `max_stack`:** trước `dmul`, operand stack chứa hai `double` → độ sâu 4. Trước `dadd`, có hai `double` → độ sâu 4. Với dãy bytecode minh họa, `max_stack` là **4**, còn `max_locals` là **7**. Hai giá trị tình cờ khác nhau theo ví dụ; không có công thức “mỗi `long` khiến `max_stack` luôn bằng `max_locals`”.

### 7.2. Phương thức instance có thêm `this`

`adjust(long, double)` có sơ đồ:

```text
  local 0        this              (reference, 1 slot)
  local 1–2      items             (long, 2 slots)
  local 3–4      unitPrice         (double, 2 slots)
  local 5–6      total             (double, 2 slots)

  max_locals cần ít nhất 7.
  descriptor: (JD)D
```

Trong bytecode, `lload_1` phải dùng index 1 cho `items`; `dload_3` dùng index 3 cho `unitPrice`. Phương thức instance cần thêm slot 0 cho `this`, dù trong descriptor `(JD)D` **không ghi `this` như một tham số tường minh**.

### 7.3. `main` cũng dùng slot cho tham số và biến cục bộ

Ở `main(String[] args)`:

```text
  slot 0        args         (String[] reference)
  slot 1–2      count        (long)
  slot 3–4      price        (double)
  slot 5–6      result       (double)
```

Tại `invokestatic weighted`, việc chuẩn bị tham số `long`, `double`, `int` trên **operand stack** là một thao tác **khác** với nơi lưu chúng trong **local-variable array** của frame `main`. Khi phương thức `weighted` được gọi, frame **mới** có các tham số của chính nó ở index 0–4. Index trong frame của bên gọi không được dùng làm index trong frame của bên được gọi.

## 8. Đọc `Code`, `max_locals` và `LocalVariableTable` đúng cách

Giả sử `javap -v` hiển thị thông tin kiểu:

```text
Code:
  stack=4, locals=7, args_size=3
```

Cần đọc như sau:

- **`stack=4`**: chiều sâu lớn nhất của operand stack, theo đơn vị tính của JVM.
- **`locals=7`**: local-variable array có 7 vị trí, index 0–6.
- **`args_size=3`** là thông tin tóm lược được `javap` trình bày về số đối số theo cách nó báo cáo; **không thay thế quy tắc tính slot**. Để biết vị trí thực, hãy tra descriptor, `static`/instance và các lệnh `lload`/`dload`.
- **`LocalVariableTable`**, nếu tồn tại, dùng cho thông tin debug về các local variables. Một entry của `long`/`double` chỉ ra **index bắt đầu** cùng descriptor `J`/`D`; entry không có nghĩa biến nguồn đã bị tách thành hai biến.
- **`StackMapTable`**, nếu có, là thông tin loại trạng thái dùng để kiểm tra bytecode. Nó không phải bản sao toàn bộ đối tượng runtime đang sống.

Không phải mọi file `.class` đều chứa tên biến nguồn và `LocalVariableTable`; các thông tin debug có thể được bỏ qua khi biên dịch. Chỉ dựa vào tên biến trong `javap` để suy luận slot sẽ thất bại khi thiếu debug metadata. **Opcode và descriptor** đáng tin hơn cho việc hiểu index.

## 9. Tái sử dụng slot theo phạm vi sống

Hai slot dành cho một `long`/`double` không nhất thiết bị giữ tới khi phương thức kết thúc nếu trình biên dịch có thể chứng minh một biến đã hết phạm vi hoặc không còn được dùng.

Ví dụ:

```java
static void reuse() {
    {
        long left = 10L;
        System.out.println(left);
    }
    {
        int right = 3;
        System.out.println(right);
    }
}
```

Về ngữ nghĩa, `left` không còn trong phạm vi khi `right` được dùng. Một compiler có thể tái sử dụng một local slot ở khối thứ hai mà vẫn tạo bytecode hợp lệ. Tuy nhiên, **không có bảo đảm chính xác `javac` mọi phiên bản sẽ chọn một index cố định**, và JIT có thể tiếp tục chuyển giá trị sang thanh ghi/loại bỏ các lưu trữ không cần thiết.

Vì vậy:

- Không suy ra `max_locals` bằng “tổng tất cả biến được khai báo”.
- Không suy ra kích thước stack thực tế của OS bằng `max_locals × 4` byte.
- Không suy ra heap usage hoặc số đối tượng do `long`/`double` sử dụng hai local slots.
- Không coi các slot là **địa chỉ trực tiếp** để đọc/ghi bất kỳ như vùng nhớ kiểu C.

## 10. Vì sao cần verifier và quy tắc category 2?

Bytecode mang kiểu thao tác rõ ràng: `lload` đòi một local value `long` hợp lệ ở **index bắt đầu**; `dload` đòi `double`; `iload` đòi `int`. JVM verifier kiểm tra các điều kiện kiểu/stack cần thiết trước khi code được chấp nhận thực thi theo quy định. Nhờ đó, không thể hợp lệ hóa một chuỗi tùy tiện như “lưu `long` vào 0–1, ghi đè slot 1 bằng `int`, rồi vẫn `lload_0`”.

Một số lỗi có thể xuất hiện khi tự tạo/chỉnh class file:

| Dấu hiệu | Nguyên nhân cần kiểm tra |
| --- | --- |
| `VerifyError` tại lệnh `lload`/`dload` | Local index hoặc kiểu trạng thái tại điểm đó không chứa giá trị category 2 hợp lệ |
| `VerifyError` hoặc mã bị từ chối sau khi ghi vào slot thứ hai | Phần cặp slot còn lại đã làm `long`/`double` bắt đầu ở index cũ mất hiệu lực |
| `VerifyError` liên quan operand stack | Dùng `pop`/`swap` sai category hoặc stack depth/type không nhất quán |
| `ClassFormatError` hoặc lỗi xác minh do `Code` attribute | `max_locals`, `max_stack`, index hoặc cấu trúc class file không thỏa điều kiện hợp lệ |
| Đọc `javap` thấy tham số bị “nhảy index” | Thường là **đúng quy tắc** `long`/`double` chiếm hai slots, không phải compiler bỏ quên một biến |

Tên và thông điệp lỗi cụ thể tùy bản JVM và bytecode. Không tạo ví dụ `VerifyError` bằng Java source hợp lệ thông thường: `javac` sẽ chủ động sinh bytecode đúng quy tắc. Lỗi xác minh kiểu này thường xuất hiện khi class file bị chỉnh sai, bytecode generator/instrumentation bị lỗi hoặc class không tương thích theo cách khác.

## 11. Các nhầm lẫn phổ biến

1. **“`long` có hai slot thì nó là hai biến 32-bit.”** Sai. Nó là **một giá trị `long` category 2**, chiếm hai local-variable slots theo mô hình JVM.
2. **“`lload_1` đọc nửa thứ hai của `lload_0`.”** Sai. Nó bắt đầu đọc một `long` tại index 1 và chỉ hợp lệ nếu có giá trị `long` được thiết lập ở cặp **1–2**.
3. **“Một biến `double` luôn cần 8 byte thực tế trong native stack frame.”** Không thể kết luận chỉ từ JVMS. Cách hiện thực và tối ưu hóa là trách nhiệm JVM.
4. **“Hai slot phải bắt đầu tại index chẵn.”** Sai. `this` ở index 0 khiến tham số `long` đầu của instance method thường bắt đầu tại **1**.
5. **“Phương thức `static` và instance có cùng index tham số.”** Sai. Instance method dành slot 0 cho `this`.
6. **“`max_locals` đếm biến Java.”** Sai. Nó đếm **slot**, cả receiver, tham số và local storage của bytecode; compiler có thể tái sử dụng.
7. **“`max_stack` và `max_locals` đều là số ô trong cùng một mảng.”** Sai. Chúng là hai vùng dữ liệu khác nhau của frame.
8. **“`long[]` có hai phần tử cho mỗi số.”** Sai. Hai slot áp dụng cho local-variable array, không phải chỉ số của Java array.
9. **“Một `long` trên operand stack là hai giá trị `int` để `pop` hai lần.”** Sai. Nó là một giá trị category 2, chỉ thao tác qua opcode phù hợp.
10. **“Dùng `int` thay `long` để tiết kiệm một slot chắc chắn tăng hiệu năng.”** Không có kết luận như vậy. Chọn kiểu theo miền giá trị/độ chính xác; hiệu năng thực cần đo trong workload cụ thể.

## 12. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Phương thức `static void foo(double x, int y, long z)` dùng bao nhiêu slot cho tham số và từng index là gì?

**Đáp án:** `x` dùng **0–1**; `y` dùng **2**; `z` dùng **3–4**. Tổng cần ít nhất **5 slots** để chứa tham số.

**Câu 2.** Nếu đổi `foo` thành instance method với cùng danh sách tham số, index của `z` là bao nhiêu?

**Đáp án:** `this` ở **0**; `x` ở **1–2**; `y` ở **3**; `z` ở **4–5**. Index bắt đầu của `z` là **4**.

**Câu 3.** `static long sum(long a, long b)` chỉ cần trả `a + b`. Nếu operand stack cùng lúc có `a` và `b`, độ sâu tính theo đơn vị là bao nhiêu?

**Đáp án:** **4**: hai giá trị `long`, mỗi giá trị category 2 góp hai đơn vị.

**Câu 4.** Vì sao `lload 2` và `lload 3` không thể tự ý dùng để lấy “hai nửa” của một `long` đã lưu bắt đầu tại index 2?

**Đáp án:** `lload 2` lấy **toàn bộ** giá trị `long` chiếm cặp **2–3**. `lload 3` lại đòi một giá trị `long` hợp lệ bắt đầu ở **3** (tức cặp **3–4**), hoàn toàn khác và không thể dùng nửa sau như một giá trị riêng.

**Câu 5.** Một instance method chứa `long` và `double` khiến `max_locals = 7`. Điều đó có chứng minh có đúng 7 biến source hay 28 byte physical memory?

**Đáp án:** **Không.** `max_locals` là số slots trừu tượng; receiver và giá trị category 2 làm thay đổi số slots, compiler có thể tái sử dụng slots và runtime có quyền chọn biểu diễn tối ưu.

## Kết luận

Trong frame của JVM, `long` và `double` là **giá trị category 2**: mỗi giá trị chiếm **hai local-variable slots liên tiếp**, được đánh địa chỉ bằng **index thấp hơn**; index thứ hai không phải một biến có thể đọc độc lập. Trên operand stack, mỗi giá trị ấy cũng tính **hai đơn vị độ sâu**, dù vẫn là một toán hạng logic. Phân biệt hai vùng dữ liệu, nhớ slot 0 cho `this` ở instance method, và dùng `javap -c -v` để kiểm tra `max_locals` và opcode giúp bạn đọc bytecode đúng mà không suy diễn về bộ nhớ vật lý.

### Tài liệu tham khảo

- [JVMS Java SE 17, §2.6.1 — Local Variables](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.1): quy tắc cặp slot, index thấp hơn, slot thứ hai và tham số instance/`static`.
- [JVMS Java SE 17, §2.6.2 — Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6.2): loại giá trị, độ sâu tính theo đơn vị.
- [JVMS Java SE 17, §2.11.1–2.11.2 — Type Categories và Load/Store](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.1): category 1/2 và opcode truy cập local.
- [JVMS Java SE 17, §4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3): `max_stack`, `max_locals` trong class file.
- [Oracle JDK 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): cách xem bytecode và metadata.
