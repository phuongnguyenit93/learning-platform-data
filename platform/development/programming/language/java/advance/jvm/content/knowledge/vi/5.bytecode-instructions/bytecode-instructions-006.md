# `tableswitch` và `lookupswitch`: cách JVM biểu diễn lệnh `switch`

Khi thấy câu lệnh hoặc biểu thức `switch` trong Java, bạn đang đọc **cú pháp ngôn ngữ**. Khi mở tệp `.class` bằng `javap -c`, bạn có thể thấy hai opcode chuyên dụng của JVM: **`tableswitch`** và **`lookupswitch`**. Chúng đều chọn một nhánh dựa trên một giá trị `int`, nhưng lưu các nhánh theo hai cấu trúc khác nhau.

- **`tableswitch`** lưu bảng nhảy cho **mọi giá trị nguyên trong một đoạn liên tục** từ `low` đến `high`.
- **`lookupswitch`** lưu **danh sách các cặp `match → target`** đã sắp xếp tăng dần theo khóa.

Sự khác nhau giải thích vì sao switch với case gần nhau thường dùng `tableswitch` còn case thưa thường dùng `lookupswitch`. Đây là **xu hướng tối ưu hóa của trình biên dịch**, không phải lời hứa rằng Java Language Specification bắt buộc chọn opcode nào cho một đoạn mã nguồn nhất định.

Bài học tập trung vào cơ chế bytecode, cách đọc dữ liệu bằng `javap`, xử lý `default`, các giá trị khuyết, biểu diễn ở class file, và các giới hạn khi suy luận từ mã Java. Ví dụ chạy được với **Java 17+**.

## 1. Đi từ `switch` của Java đến lệnh JVM

Mã Java:

```java
static int level(int code) {
    return switch (code) {
        case 1 -> 10;
        case 2 -> 20;
        case 3 -> 30;
        default -> -1;
    };
}
```

Đây là **đoạn phương thức minh họa**, không phải chương trình độc lập. Trong file `.class` do `javac` tạo, JVM không còn xử lý từ khóa `case` hay `->` của Java source. Nó thực thi bytecode do compiler sinh ra, thường theo chuỗi:

```text
load biến/tham số chứa khóa
        │
        ▼
  operand stack: [int key]
        │
        ▼
  tableswitch HOẶC lookupswitch
        │
        ├─ case phù hợp → lệnh tại target tương ứng
        └─ không phù hợp → lệnh tại target default
                │
                ▼
     thực thi mã của nhánh rồi tiếp tục/trả về
```

**Cả hai opcode đều tiêu thụ một giá trị loại `int` ở đỉnh operand stack.** Chúng không trực tiếp nhận `String`, `enum`, `long` hay một đối tượng tùy ý làm khóa. Nếu switch Java có kiểu khác, trình biên dịch phải áp dụng bước chuyển đổi/ánh xạ hoặc sinh một cấu trúc điều khiển khác.

### 1.1. So sánh nhanh

| Tiêu chí | `tableswitch` | `lookupswitch` |
| --- | --- | --- |
| Opcode | **170**, hexadecimal `0xaa` | **171**, hexadecimal `0xab` |
| Khóa trên operand stack | Một `int` | Một `int` |
| Dữ liệu chính | `low`, `high`, rồi `high-low+1` offsets | `npairs`, rồi `npairs` cặp `match, offset` |
| Giá trị được mô tả | Mọi số nguyên trong đoạn `[low, high]` | Chỉ các khóa `match` đã liệt kê |
| Case không khai báo | Mục bảng có thể trỏ tới nhánh mặc định | Không có cặp match, dùng nhánh mặc định |
| Truy cập bảng về mặt thiết kế | Kiểm tra cận rồi index bằng `key-low` | Tìm một khóa trong danh sách match |
| Độ dài dữ liệu | Theo **độ rộng của đoạn khóa** | Theo **số khóa được liệt kê** |
| Tình huống compiler thường chọn | Các case tương đối dày | Các case cách xa nhau |

Hai lệnh **không ghi sẵn kết quả của từng case**; chúng ghi **địa chỉ nhảy tương đối** tới những bytecode thực thi thân nhánh. Nhiều khóa khác nhau có thể cùng nhảy tới một target.

## 2. `tableswitch`: bảng nhảy theo đoạn khóa liên tục

Với các case `3, 4, 5, 6`:

```java
static String classify(int code) {
    return switch (code) {
        case 3 -> "THREE";
        case 4 -> "FOUR";
        case 5 -> "FIVE";
        case 6 -> "SIX";
        default -> "UNKNOWN";
    };
}
```

Compiler có thể tổ chức một bảng:

```text
index value   jump-table index   bytecode target
3             0                  case 3
4             1                  case 4
5             2                  case 5
6             3                  case 6
other         —                  default
```

Mô tả bytecode điển hình khi dùng `tableswitch`:

```text
iload_0
tableswitch { // 3 to 6
    3: <target case 3>
    4: <target case 4>
    5: <target case 5>
    6: <target case 6>
    default: <target default>
}
```

**Các nhãn `<target ...>` là ký hiệu giải thích**, không phải các bytecode offsets thực tế; `javap` sẽ hiển thị số offset của chương trình đã biên dịch.

### 2.1. Thuật toán ở mức ngữ nghĩa lệnh

Khi `tableswitch` thực thi:

1. Lấy và loại bỏ một `int index` khỏi operand stack.
2. Nếu `index < low` hoặc `index > high`, chọn offset `default`.
3. Ngược lại, tính **`position = index - low`** và lấy offset tại vị trí đó trong jump table.
4. Cộng offset đã chọn với **địa chỉ opcode `tableswitch`** để xác định địa chỉ lệnh đích.
5. Tiếp tục thực thi ở địa chỉ lệnh đích.

Mã giả:

```text
key = pop_int()
if (key < low || key > high) {
    relativeOffset = defaultOffset
} else {
    relativeOffset = jumpOffsets[key - low]
}
nextPc = switchOpcodePc + relativeOffset
```

Đây là mô tả **ngữ nghĩa**, không áp đặt JVM/JIT phải hiện thực bằng đúng chuỗi phép tính máy đó.

### 2.2. Case bị khuyết vẫn phải có mục bảng

Giả sử source chỉ có `1, 3, 5`:

```java
static String oddLabel(int x) {
    return switch (x) {
        case 1 -> "ONE";
        case 3 -> "THREE";
        case 5 -> "FIVE";
        default -> "OTHER";
    };
}
```

Nếu compiler chọn `tableswitch` với `low = 1`, `high = 5`, nó phải có **5 entries**, dù source chỉ có 3 case:

```text
key:         1        2         3         4         5
entry:   case 1    default   case 3    default   case 5
```

Các case bị khuyết **không có một nhánh Java riêng**; các entries tương ứng có thể trỏ tới cùng target `default`. Đây là chi tiết quan trọng khi ước lượng kích thước bảng: `high-low+1` có thể lớn hơn nhiều so với số case.

**Ví dụ cực đoan:** nếu chỉ có case `1` và `1_000_000`, `tableswitch` phải bao phủ khoảng **1 triệu entries** nếu chọn cùng đoạn này. Vì lãng phí, compiler thường nghiêng về `lookupswitch` hoặc phương án khác.

### 2.3. Kích thước phần dữ liệu của `tableswitch`

Định dạng của instruction:

```text
tableswitch (1 byte opcode: 0xaa)
  0..3 byte padding
  default (4 byte signed offset)
  low     (4 byte signed int)
  high    (4 byte signed int)
  jump offsets[high - low + 1]   (4 byte mỗi offset)
```

Với `N = high-low+1`:

```text
total bytes = 1 + padding + 12 + 4*N
```

Đây là **độ dài lệnh trong bytecode**, chưa tính mã các case sau bảng và metadata khác của class file. Ví dụ `low=3, high=6` có `N=4`, nên dùng **29 đến 32 byte** cho bản thân instruction, tùy 0–3 byte padding.

`low` và `high` phải thỏa `low <= high`. Mọi đích nhảy trong bảng và `default` phải trỏ tới **opcode của lệnh hợp lệ trong chính phương thức**.

## 3. `lookupswitch`: danh sách khóa thưa và các cặp match–offset

Ví dụ:

```java
static String sparse(int code) {
    return switch (code) {
        case -100 -> "NEGATIVE";
        case 7 -> "SEVEN";
        case 10_000 -> "BIG";
        default -> "OTHER";
    };
}
```

Nếu dùng `lookupswitch`, bytecode lưu chỉ **ba khóa xuất hiện**:

```text
match        relative jump target
-100         case -100
7            case 7
10000        case 10000
(default)    default
```

Phần trình bày tương ứng trong `javap -c` thường giống:

```text
iload_0
lookupswitch { // 3
    -100: <target NEGATIVE>
       7: <target SEVEN>
   10000: <target BIG>
 default: <target OTHER>
}
```

Khác với `tableswitch`, không có entries cho các số giữa `7` và `10000`. Vì thế cấu trúc này thường tiết kiệm dung lượng khi phạm vi khóa rộng nhưng số case ít.

### 3.1. Ngữ nghĩa của `lookupswitch`

Khi JVM thực thi:

1. Pop một khóa `int` từ operand stack.
2. Tìm giá trị `match` bằng khóa trong danh sách cặp đã lưu.
3. Nếu thấy match, lấy offset đi kèm; nếu không, lấy `default`.
4. Đích nhảy bằng **địa chỉ opcode `lookupswitch` + offset đã chọn**.
5. Tiếp tục từ opcode tại đích.

```text
key = pop_int()
pair = lookup_match(key)
relativeOffset = pair.found ? pair.offset : defaultOffset
nextPc = switchOpcodePc + relativeOffset
```

**Các `match` phải được sắp xếp tăng dần theo giá trị số nguyên có dấu.** Đây là **ràng buộc của class-file format**, không chỉ là lựa chọn trình bày của `javap`. JVM hoặc implementation có thể khai thác tính có thứ tự để tìm kiếm hiệu quả, nhưng **JVMS không bắt buộc** một thuật toán tìm kiếm cụ thể như binary search.

### 3.2. Kích thước dữ liệu của `lookupswitch`

```text
lookupswitch (1 byte opcode: 0xab)
  0..3 byte padding
  default (4 byte signed offset)
  npairs  (4 byte signed int, không âm)
  match_0 (4 byte signed int), offset_0 (4 byte signed int)
  match_1 (4 byte signed int), offset_1 (4 byte signed int)
  ...
```

Với `P = npairs`:

```text
total bytes = 1 + padding + 8 + 8*P
```

Với 3 case, instruction chiếm **33–36 byte**, tùy padding. Một `tableswitch` bao phủ khoảng một triệu giá trị rõ ràng không phải lựa chọn lưu trữ tiết kiệm trong tình huống này.

`npairs` có thể bằng 0 trong định dạng lệnh hợp lệ theo JVMS. Trường hợp đó không có match pair; mọi khóa đi theo nhánh `default`. Tuy nhiên compiler Java bình thường không nhất thiết sinh ra một `lookupswitch` như thế cho source switch rỗng.

## 4. Vì sao các lệnh cần padding 0–3 byte?

Bytecode là luồng opcode và operands có độ dài biến thiên. Hai lệnh `tableswitch` và `lookupswitch` đặc biệt vì **các trường 32-bit bên trong phải bắt đầu tại địa chỉ chia hết cho 4, tính từ đầu mã của phương thức**.

- Sau **1 byte opcode** có thể có **0, 1, 2 hoặc 3 byte đệm**.
- Byte đầu của trường `default` phải ở offset chia hết cho 4 trong mảng `Code.code[]`.
- Việc đệm căn chỉnh **các operands nội bộ**, không yêu cầu địa chỉ opcode của switch chia hết cho 4.
- Các số 32-bit của hai instruction được mã hóa big-endian theo định dạng JVM.
- Các byte padding không phải case mới hay target; khi đọc file nhị phân phải bỏ qua chính xác số byte đệm.

Nếu opcode bắt đầu tại chỉ số `p` trong mảng code, số padding:

```text
padding = (4 - ((p + 1) % 4)) % 4
```

Ví dụ:

| Opcode bắt đầu ở `p` | Offset ngay sau opcode | Padding | `default` bắt đầu |
| ---: | ---: | ---: | ---: |
| 0 | 1 | 3 | 4 |
| 1 | 2 | 2 | 4 |
| 2 | 3 | 1 | 4 |
| 3 | 4 | 0 | 4 |
| 4 | 5 | 3 | 8 |

Tất cả offsets ở bảng tính **từ đầu bytecode của phương thức**, không phải từ đầu toàn tệp `.class`. Không được dùng địa chỉ tuyệt đối của file để tính padding.

### 4.1. Đích nhảy là offset tương đối từ OPCODE switch

Đây là lỗi phổ biến khi tự viết disassembler:

```text
Nếu tableswitch/lookupswitch opcode bắt đầu tại code offset 12
và một jump offset có giá trị +40
→ đích là code offset 52

KHÔNG phải:
  12 + 1 + số padding + 40
  hay vị trí ngay sau toàn instruction + 40
```

Ngay cả khi `default` là giá trị âm, địa chỉ đích vẫn được tính **switchOpcodePc + signedOffset**. Mọi target được tính ra phải là **vị trí bắt đầu opcode hợp lệ thuộc phương thức đó**, không được trỏ vào giữa operand, padding hoặc instruction khác.

Điều này đặc biệt quan trọng khi instrumentation sửa bytecode: thêm/bớt một lệnh trước switch có thể đổi padding; thay cấu trúc switch còn đòi cập nhật offsets, các nhánh khác và frame verification metadata liên quan.

## 5. Compiler chọn `tableswitch` hay `lookupswitch` như thế nào?

Với các `case` nguyên, một tiêu chí tự nhiên là **mật độ của tập khóa**:

```text
rangeSize = maxCase - minCase + 1
caseCount = số giá trị case riêng biệt
density = caseCount / rangeSize
```

Nếu `rangeSize` gần `caseCount`, bảng nhảy ít có khoảng trống. Nếu `rangeSize` rất lớn mà `caseCount` nhỏ, việc lưu offsets cho từng giá trị trong đoạn sẽ lãng phí bộ nhớ class file.

Về chi phí **chỉ của bản thân instruction** và bỏ qua padding:

```text
tableswitch: 1 + 12 + 4 * rangeSize
lookupswitch: 1 + 8 + 8 * caseCount
```

So sánh này hữu ích để hiểu trade-off về **bytecode size**, nhưng **không phải công thức bắt buộc** để quyết định compiler sẽ dùng instruction nào. Compiler có thể xét nhiều yếu tố hoặc dùng heuristic riêng; sự lựa chọn thay đổi giữa phiên bản/toolchain hoặc khi có tối ưu hóa khác.

Chẳng hạn với case `1, 2, 3, 4`:

- `rangeSize = 4`, `caseCount = 4`.
- `tableswitch` có phần dữ liệu dày và ít lỗ trống.
- Compiler `javac` thường chọn `tableswitch`.

Với case `-100, 7, 10000`:

- `rangeSize = 10101`, `caseCount = 3`.
- `tableswitch` sẽ cần hơn mười nghìn offsets.
- Compiler `javac` thường chọn `lookupswitch`.

**Không có “ngưỡng 50%” hoặc “trên 5 case luôn dùng tableswitch” được Java Language Specification bảo đảm.** Kết luận chắc chắn cho class đang chạy phải đến từ **bytecode thực tế**.

### 5.1. `tableswitch` có nhất thiết nhanh hơn?

Không thể khẳng định “mỗi `tableswitch` luôn nhanh hơn mỗi `lookupswitch`” trong chương trình thật:

- `tableswitch` hỗ trợ tra cứu theo chỉ số, nhưng có thể làm instruction lớn nếu vùng khóa rộng.
- `lookupswitch` tiết kiệm dữ liệu với khóa thưa nhưng cần tìm match.
- JVM interpreter có thể thực thi trực tiếp hai lệnh theo cách triển khai riêng.
- **JIT compiler** có thể chuyển chúng thành machine-code jump tables, các phép so sánh có nhánh, cây quyết định hoặc cách khác.
- Hiệu năng thực phụ thuộc độ phân bố khóa, cache, branch prediction, lượng mã, profile runtime và mã trong từng nhánh.

Vì vậy khi tối ưu ứng dụng, dùng profiler/benchmark phù hợp; không viết code rối để ép opcode nếu chưa chứng minh lợi ích. Trong source, ưu tiên `switch` dễ hiểu và chính xác trước.

## 6. Ví dụ Java 17+: hai biểu diễn trong cùng chương trình

Tạo tệp **`SwitchOpcodesDemo.java`**:

```java
public class SwitchOpcodesDemo {

    static String dense(int value) {
        return switch (value) {
            case 1 -> "ONE";
            case 2 -> "TWO";
            case 3 -> "THREE";
            case 4 -> "FOUR";
            default -> "OTHER";
        };
    }

    static String sparse(int value) {
        return switch (value) {
            case -100 -> "NEGATIVE";
            case 7 -> "SEVEN";
            case 10_000 -> "BIG";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("dense(3) = " + dense(3));
        System.out.println("dense(8) = " + dense(8));
        System.out.println("sparse(7) = " + sparse(7));
        System.out.println("sparse(5) = " + sparse(5));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 SwitchOpcodesDemo.java
java SwitchOpcodesDemo
```

**Stdout xác định:**

```text
dense(3) = THREE
dense(8) = OTHER
sparse(7) = SEVEN
sparse(5) = OTHER
```

Hai phương thức đều trả kết quả theo ngữ nghĩa Java; không có khác biệt bắt buộc về hành vi bên ngoài. Khác biệt đáng chú ý nằm ở cách compiler chọn lưu bảng nhảy trong bytecode.

### 6.1. Dùng `javap` kiểm tra chính xác

```bash
javap -c -p SwitchOpcodesDemo
```

Với `javac` JDK 17 và hình dạng case này, thông thường:

- Phương thức `dense` có `tableswitch` bao phủ **1 đến 4**.
- Phương thức `sparse` có `lookupswitch` với **3 cặp match** mang khóa **-100, 7, 10000**.
- Phần thân mỗi case có các thao tác đẩy `String` literal và `areturn`; tùy compiler có thể có thêm nhánh/metadata khác.
- `javap` sẽ in địa chỉ opcode/target cụ thể. Không tự đặt số offset trước khi xem output từ compiler đã dùng.

Một bản trích **minh họa các trường khóa, không phải toàn bộ dump với offsets cố định**:

```text
dense(int):
  iload_0
  tableswitch { // 1 to 4
       1: <ONE>
       2: <TWO>
       3: <THREE>
       4: <FOUR>
  default: <OTHER>
  }

sparse(int):
  iload_0
  lookupswitch { // 3
      -100: <NEGATIVE>
         7: <SEVEN>
     10000: <BIG>
   default: <OTHER>
  }
```

Đọc dump theo cách sau:

1. **`iload_0`:** đưa tham số `int value` lên operand stack.
2. **`tableswitch` / `lookupswitch`:** pop khóa, chọn một target.
3. **Target `case`:** tải chuỗi tương ứng rồi trả về.
4. **Target `default`:** tải `"OTHER"` rồi trả về.
5. Kiểm tra offsets được in để thấy các target thực nằm **sau instruction switch**, dù instruction đó dài hơn một byte.

### 6.2. Quan sát class-file version riêng với opcode

`--release 17` tạo bytecode theo target Java 17. Kiểm tra:

```bash
javap -v -p SwitchOpcodesDemo
```

Các dòng version kỳ vọng:

```text
minor version: 0
major version: 61
```

Bản thân `tableswitch` và `lookupswitch` **không phải preview features**. Chúng là các opcode đã có từ các thế hệ JVM trước. Vì vậy không cần `--enable-preview` để chạy switch biểu thức Java 17 hợp lệ trong ví dụ.

## 7. Với case lỗ trống, `default` và nhiều case chung thân thì sao?

### 7.1. Không có `default` tường minh trong switch statement

Một `switch statement` có thể hợp lệ mà không khai báo nhánh `default`:

```java
static void printIfKnown(int value) {
    switch (value) {
        case 1:
            System.out.println("ONE");
            break;
        case 2:
            System.out.println("TWO");
            break;
    }
}
```

Đoạn này là một phương thức minh họa. Trong class file, **cả `tableswitch` lẫn `lookupswitch` luôn có trường `default offset`** theo định dạng lệnh. Khi source không có `default`, compiler có thể trỏ default tới code **sau switch**, để bỏ qua toàn bộ các nhánh.

**Không có `default` trong Java source** không có nghĩa **bytecode switch instruction thiếu operand default**.

### 7.2. Nhiều nhãn case dùng cùng target

```java
static String category(int x) {
    return switch (x) {
        case 1, 2, 3 -> "SMALL";
        case 100 -> "LARGE";
        default -> "OTHER";
    };
}
```

Compiler có thể cho các khóa 1/2/3 cùng nhảy tới đoạn code sinh chuỗi `SMALL`. Dữ liệu ở bảng có **nhiều khóa** nhưng target trùng nhau; JVMS không yêu cầu từng case có một đoạn mã mới.

Trong `tableswitch`, nhiều entries có thể mang cùng offset; trong `lookupswitch`, nhiều cặp `match` khác nhau có thể có offset giống nhau.

### 7.3. `fall-through` trong switch statement cổ điển

```java
static int countFlags(int x) {
    int result = 0;
    switch (x) {
        case 1:
            result += 1;
        case 2:
            result += 2;
            break;
        default:
            result = -1;
    }
    return result;
}
```

- `countFlags(1)` trả **3**, vì sau case 1 luồng điều khiển **đi tiếp** vào case 2.
- `countFlags(2)` trả **2**.
- `countFlags(3)` trả **-1**.

`tableswitch`/`lookupswitch` chỉ quyết định **đích nhảy ban đầu**, còn **fall-through** do các lệnh tuần tự sau target quyết định. Chính trình biên dịch quản lý bố trí thân nhánh và `goto`/`break`; opcode switch không có một “flag fall-through” riêng.

### 7.4. Switch expression và `yield`

Switch expression (Java 14+) yêu cầu sinh ra một **giá trị**. Với arrow cases, compiler thường đặt giá trị nhánh trên operand stack và đi tới điểm hội tụ hoặc return. Nếu dùng khối `{ ... yield value; }`, `yield` là cú pháp source, không phải opcode bytecode có tên `yield`.

```java
static int points(int n) {
    return switch (n) {
        case 1 -> 10;
        case 2 -> {
            int value = 20;
            yield value;
        }
        default -> -1;
    };
}
```

`tableswitch` hoặc `lookupswitch` vẫn chỉ nhảy theo khóa nguyên; chúng **không quyết định trực tiếp giá trị trả về**. Giá trị do bytecode ở target nhánh tạo ra.

## 8. Switch trên kiểu nào? Vì sao không phải lúc nào có opcode switch?

Hai opcode nhận **`int`**. Nhưng Java hỗ trợ các dạng switch phong phú hơn.

| Switch source | Cách biểu diễn/giới hạn thường gặp |
| --- | --- |
| `int` / `byte` / `short` / `char` | Có thể trực tiếp dùng `tableswitch` hoặc `lookupswitch` trên khóa kiểu `int` của JVM |
| `Integer`, `Byte`, `Short`, `Character` | Thường unbox (và chuyển kiểu phù hợp) để dùng khóa `int`; `null` có thể gây `NullPointerException` trong switch truyền thống |
| `enum` | Compiler chuyển giá trị enum thành khóa nguyên (có thể qua mapping synthetic hoặc ordinal) rồi chọn nhánh |
| `String` | Compiler thường dùng `hashCode()`, `equals()` và một/nhiều switch trên giá trị nguyên; không có opcode `stringswitch` |
| Switch pattern (Java 21+ chuẩn) | Có thể dùng `invokedynamic`/bootstrap runtime matching và các nhánh integer sau đó; không thể suy một opcode cố định chỉ từ từ khóa `switch` |
| `long`, `float`, `double` thông thường ở Java 17 | Không phải kiểu selector được cho phép cho switch theo Java 17 |

Không nhầm khái niệm **kiểu Java của biểu thức switch** với **loại dữ liệu đầu vào của instruction JVM**. String và enum có thể là switch Java hợp lệ nhưng không có nghĩa `tableswitch` tự so sánh chuỗi hoặc đối tượng enum.

### 8.1. Switch trên `String` thường cần bước tra cứu khác

Ví dụ Java 17:

```java
static int stringCode(String text) {
    return switch (text) {
        case "ON" -> 1;
        case "OFF" -> 0;
        default -> -1;
    };
}
```

`javac` có thể sinh code dựa trên hash của chuỗi, sau đó kiểm tra `equals` để xử lý **hash collisions** đúng ngữ nghĩa. Một hoặc nhiều opcode switch trên khóa `int` có thể xuất hiện trong mã kết quả, nhưng **không suy luận trực tiếp vị trí nhánh từ giá trị hash** như thể hash là duy nhất.

Nếu `text == null` trong switch `String` Java 17 thông thường, thao tác với selector có thể ném `NullPointerException`. Với pattern switch phiên bản mới, quy tắc `case null` có thể khác. Phải xem **version và hình thức switch cụ thể** trước khi đưa kết luận về `null`.

### 8.2. Switch trên enum không cần opcode cho kiểu đối tượng

Enum Java có các hằng có tên, nhưng JVM switch instructions vẫn nhận `int`. Compiler có thể tạo mã ánh xạ ordinal → mã trường hợp; chi tiết codegen là lựa chọn của compiler, và binary compatibility khi enum thay đổi cũng phụ thuộc cách mã được biên dịch.

Không nên chỉnh reorder enum nhằm “ép tableswitch” khi chưa kiểm tra ảnh hưởng nghiệp vụ và binary compatibility.

## 9. Mã máy JIT có giữ nguyên kiểu jump table không?

`javap` cho thấy **bytecode trước khi JVM tối ưu hóa runtime**, không phải chắc chắn là các lệnh máy CPU thực sự thực thi.

Sau khi JVM nhận profile, JIT compiler có thể:

- Dùng jump table máy cho nhóm case dày.
- Tạo một chuỗi so sánh/rẽ nhánh cho các khóa thưa.
- Sắp xếp lại nhánh dựa trên profile, inline thân case hoặc đơn giản hóa code.
- Loại bỏ switch khi compiler suy ra khóa là một hằng tại vị trí gọi.
- Thực thi theo interpreter trước rồi dùng compiled machine code sau.

Không có bảo đảm 1–1 rằng `tableswitch` thành “một lệnh CPU” hoặc `lookupswitch` nhất thiết luôn dùng binary search ở runtime. **Bytecode là hợp đồng ngữ nghĩa với JVM**; chiến lược chạy thật tùy JVM/JIT/CPU.

Nếu muốn đo, benchmark phải có đủ warm-up, nhiều đầu vào và tránh constant folding/dead-code elimination. Với Java, một framework như JMH thường thích hợp hơn viết một vòng `System.nanoTime()` ngắn rồi kết luận opcode nào nhanh hơn.

## 10. Bytecode verifier và tính hợp lệ của bảng nhảy

Khi tự sinh hoặc chỉnh sửa class file (ASM, Byte Buddy, instrumentation), không thể tùy ý đưa dữ liệu vào opcode switch.

### 10.1. Các bất biến quan trọng

Đối với **`tableswitch`**:

- Operand stack phải có một khóa `int` phù hợp.
- `low <= high`.
- Phải có đúng **`high - low + 1`** jump offsets.
- Các offsets, kể cả `default`, phải dẫn đến **đầu một instruction opcode hợp lệ thuộc phương thức hiện tại**.
- Vùng padding phải được đặt đúng để trường `default` thẳng hàng bốn byte theo offset của code array.

Đối với **`lookupswitch`**:

- Operand stack phải có một khóa `int` phù hợp.
- `npairs >= 0`; số cặp dữ liệu khớp với `npairs`.
- Các giá trị `match` phải **tăng nghiêm ngặt theo số nguyên có dấu**, không xếp theo chuỗi văn bản.
- Mỗi offset phải trỏ tới opcode hợp lệ trong phương thức, không trỏ vào giữa instruction hoặc padding.
- Padding phải đặt đúng trước `default`.

Ngoài định dạng, các nhánh sau khi merge còn phải có trạng thái operand stack, local variables và `StackMapTable` nhất quán theo quy tắc verification của class file tương ứng.

### 10.2. Một lỗi offset khi chèn logging

Giả sử một agent thêm bytecode logging ngay trước `tableswitch`:

```text
Trước:
  ... bytecode
  tableswitch (opcode ở offset p; padding theo p)

Sau khi chèn 1–3 byte:
  ... bytecode mới
  tableswitch (opcode ở offset p + delta; có thể đổi padding)
```

Nếu chỉ sao chép nguyên operands cũ, cấu trúc switch có thể bị lệch; các offset nhảy và các cấu trúc phụ thuộc code layout khác cũng phải được tính lại.

Trong thực hành, nên dùng bytecode library đã hiểu cấu trúc switch và tính toán frame/offset phù hợp. Khi gặp `VerifyError` hoặc `ClassFormatError` sau instrumentation, kiểm tra việc alignment, target và type state thay vì quy lỗi cho logic `switch` của Java source.

## 11. Quan sát khi gỡ lỗi và tối ưu hóa

Các lệnh hữu ích:

```bash
# Biên dịch ví dụ theo Java 17
javac --release 17 SwitchOpcodesDemo.java

# Xem instruction và nhãn target
javap -c -p SwitchOpcodesDemo

# Xem thêm max_stack, max_locals, StackMapTable, version...
javap -v -p SwitchOpcodesDemo

# Thực thi để kiểm tra hành vi observable
java SwitchOpcodesDemo
```

Quy trình đọc:

1. Tìm đúng phương thức `dense`/`sparse` và bytecode tương ứng; không lẫn `main` với phương thức cần phân tích.
2. Xác minh opcode switch xuất hiện sau lệnh đẩy selector (ví dụ `iload_0`).
3. Với `tableswitch`, ghi `low`, `high`, case còn thiếu và đích `default`.
4. Với `lookupswitch`, ghi `npairs`, danh sách khóa đã sort và đích `default`.
5. Theo target tới các lệnh sinh giá trị/chạy side effects/`goto`/`return`, không dừng ở đoạn bảng nhảy.
6. Nếu mục tiêu là hiệu năng, dùng profiling/benchmark; nếu mục tiêu là lỗi, đối chiếu bytecode thực tế và JVM/spec.

### 11.1. Bảng phân tích triệu chứng

| Dấu hiệu | Hướng kiểm tra |
| --- | --- |
| `javap` không có `tableswitch` dù case liền kề | Compiler heuristic, switch được tối ưu thành chuỗi `if`/`goto` hoặc hình thức khác |
| Có `tableswitch` nhưng trong source thiếu một số case | Các mục bị khuyết có thể cùng trỏ tới `default` |
| Switch trên String nhưng thấy `lookupswitch` theo số nguyên | Đó có thể là lookup theo hash, phải kiểm tra `equals` và các nhánh xử lý collision |
| Các case có thứ tự khác với source | `lookupswitch` lưu match theo thứ tự tăng dần; bố trí body có thể khác thứ tự khai báo |
| Branch đích nhìn như một số byte offset khó hiểu | `javap` hiển thị địa chỉ tương đối đầu phương thức; trong class file offsets của switch tính từ opcode |
| Class bị từ chối sau khi bytecode instrumentation | Kiểm tra số entry, offset, padding, `StackMapTable` và quy tắc verification |
| Switch chậm dù có `tableswitch` | Profiler để xác nhận thời gian nằm ở lookup, thân case, boxing, I/O hay cache/branch effects |
| Benchmark giữa Java versions cho kết quả khác nhau | JIT, compiler, layout, profile, options và môi trường phần cứng có thể khác |

## 12. Những hiểu nhầm thường gặp

1. **“`switch` trong Java luôn dịch thành một opcode switch.”** Sai. Compiler có thể dùng `tableswitch`, `lookupswitch` hoặc kết hợp các instruction khác, đặc biệt với `String`, enum và pattern switch.
2. **“`tableswitch` chứa đúng số case viết trong source.”** Sai. Nó phải có một entry cho **mọi giá trị trong `low..high`**, kể cả khoảng trống.
3. **“`lookupswitch` có thể lưu match pairs theo thứ tự tùy ý.”** Sai. JVMS yêu cầu các `match` được sắp xếp tăng dần.
4. **“`default` của bytecode có thể bỏ đi nếu source không khai báo.”** Sai. Cả hai instruction luôn chứa offset `default`.
5. **“Switch jump offset tính từ cuối instruction.”** Sai. Offset được cộng với **địa chỉ opcode switch**.
6. **“Các bytes padding nằm trong bảng case.”** Sai. Chúng chỉ phục vụ căn chỉnh dữ liệu 32-bit của instruction.
7. **“`tableswitch` chỉ dùng được khi mọi case trong đoạn đều khai báo.”** Sai. Các mục bị khuyết có thể trỏ tới `default`.
8. **“`lookupswitch` luôn sử dụng binary search.”** Sai. JVMS mô tả ngữ nghĩa; thuật toán tra cứu là tùy implementation.
9. **“`tableswitch` chắc chắn nhanh hơn `lookupswitch`.”** Sai khi suy rộng tới JVM/JIT và workload cụ thể; cần đo.
10. **“`long` hay `double` có thể là khóa của hai instruction.”** Sai. Chúng pop một **`int`** từ operand stack; switch Java 17 không cho dùng các kiểu này làm selector thông thường.
11. **“Thứ tự case trên source bắt buộc bằng thứ tự mã máy.”** Sai. Compiler/JIT được phép bố trí khác nhưng phải giữ đúng hành vi.
12. **“`fall-through` được bật bằng một flag trong `tableswitch`.”** Sai. Fall-through xuất phát từ luồng lệnh sau target, không phải metadata opcode.

## 13. Tự kiểm tra (có đáp án)

**Câu 1.** Với `tableswitch low=-2, high=2`, bảng jump offsets có bao nhiêu entry, dù source chỉ có case `-2, 0, 2`?

**Đáp án:** `2 - (-2) + 1 = 5` entries cho `-2,-1,0,1,2`. Hai giá trị không khai báo có thể trỏ tới `default`.

**Câu 2.** `lookupswitch` có các keys `9, -10, 100`. Chúng phải được lưu theo thứ tự nào?

**Đáp án:** `-10, 9, 100` (tăng dần theo `int` có dấu); thứ tự source không quyết định thứ tự cặp match trong bytecode.

**Câu 3.** Nếu `tableswitch` opcode nằm ở code offset 10, cần mấy byte padding để `default` bắt đầu tại offset chia hết cho 4?

**Đáp án:** Sau opcode là 11; cần **1 byte** để `default` bắt đầu ở offset 12.

**Câu 4.** Một `lookupswitch` ở offset 12 có một relative jump offset `-8`. Địa chỉ target là bao nhiêu?

**Đáp án:** `12 + (-8) = 4`, miễn offset 4 đúng là đầu opcode hợp lệ trong cùng phương thức.

**Câu 5.** Vì sao `switch` trên String trong bytecode có thể hiển thị `lookupswitch` nhưng JVM không có khóa chuỗi?

**Đáp án:** Compiler đã biến so khớp chuỗi thành bước dùng khóa nguyên (ví dụ hash), phối hợp so sánh `equals` để bảo toàn ngữ nghĩa kể cả collision. `lookupswitch` chỉ làm việc với `int`.

**Câu 6.** Với ba khóa `1, 2, 3`, `javac` bắt buộc sinh `tableswitch` không?

**Đáp án:** Không. Mật độ cao làm `tableswitch` thường phù hợp, nhưng JVMS/JLS không buộc compiler dùng một opcode cụ thể.

**Câu 7.** Câu lệnh switch thiếu `default` trong source có thể tạo bytecode `tableswitch` thiếu trường `default` không?

**Đáp án:** Không. Trường `default` là bắt buộc trong định dạng instruction; compiler trỏ nó tới đường điều khiển phù hợp, chẳng hạn đoạn code sau switch.

**Câu 8.** Vì sao chỉ nhìn `javap -c` không đủ kết luận hiệu năng switch trên một bản HotSpot cụ thể?

**Đáp án:** `javap` hiển thị bytecode; HotSpot/JIT có thể biên dịch/biến đổi thành machine code khác. Cần dữ liệu workload/profiler/benchmark.

## 14. Kết nối kiến thức: source, class file và runtime

```text
Java source switch
        │
        ▼
javac chọn chiến lược lowering
        │
        ├─ bảng dày      → tableswitch (low..high + offsets)
        ├─ khóa thưa     → lookupswitch (sorted match-offset pairs)
        └─ kiểu phức tạp → chuyển đổi/so sánh/dispatch khác
        │
        ▼
.class — bytecode có jump offsets hợp lệ, padding đúng
        │
        ▼
JVM verifier / interpreter / JIT
        │
        ▼
Hành vi quan sát được theo ngữ nghĩa Java
```

**Ghi nhớ:** `tableswitch` đánh index vào một đoạn khóa nguyên; `lookupswitch` tìm match trong danh sách khóa nguyên đã sắp xếp. Cả hai pop một `int`, có target `default` bắt buộc, mã hóa jump offsets tương đối với **địa chỉ opcode switch** và cần padding cho các operands 32-bit. Cách một `switch` trong source được biểu diễn phụ thuộc compiler; cách chạy thật có thể tiếp tục được JIT tối ưu hóa.

### Tài liệu tham khảo

- [JVMS Java SE 17, 6.5 — tableswitch](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.tableswitch): định dạng, jump table, `low/high`, `default` và offsets.
- [JVMS Java SE 17, 6.5 — lookupswitch](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.lookupswitch): `npairs`, thứ tự match, cơ chế dispatch.
- [JVMS Java SE 17, 2.11 — Instruction set summary](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11): opcode operands và yêu cầu padding.
- [JVMS Java SE 17, 3.10 — Compiling Switches](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-3.html#jvms-3.10): minh họa chuyển switch Java thành `tableswitch`/`lookupswitch`.
- [JVMS Java SE 17, 4.9 — Constraints on Java Virtual Machine Code](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.9): các ràng buộc cấu trúc/nhảy.
- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): cách xem bytecode.
