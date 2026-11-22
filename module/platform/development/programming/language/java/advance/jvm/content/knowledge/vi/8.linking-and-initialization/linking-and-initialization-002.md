# Verification của JVM: kiểm tra định dạng, luồng điều khiển và an toàn kiểu

Trước khi một phương thức Java được thực thi, JVM phải có cơ sở tin rằng bytecode **hợp lệ về cấu trúc** và **không thể sử dụng operand stack, local variables hoặc object references sai kiểu theo những điều kiện tĩnh mà đặc tả quy định**. Đây là trách nhiệm của **class-file verification** — một phần quan trọng của giai đoạn **linking** trong vòng đời tải, liên kết và khởi tạo lớp.

Chẳng hạn, source Java hợp lệ không cho phép lấy một `int` đem dùng như một `String` tùy tiện. Nhưng JVM còn có thể nhận class files do trình tạo bytecode, thư viện instrumentation hoặc class loader cung cấp; nó **không thể mặc định tin tưởng rằng tệp `.class` đã qua `javac`**. Verifier kiểm tra các ràng buộc liên quan để phát hiện các lớp code lỗi, bị biến đổi sai hoặc có trạng thái không hợp lệ **trước khi** chúng được phép sử dụng theo ngữ nghĩa JVM.

Bài này giải thích đầy đủ ba lớp ý tưởng:

1. **Format checking:** tệp class có đúng cấu trúc nhị phân, constant pool, attributes và các giới hạn định dạng không?
2. **Static/structural constraints và control-flow checking:** bytecode có instruction, branch target, exception handler, đường đi và operand-stack shape hợp lệ không?
3. **Type safety:** trên **mọi đường đi khả dĩ** tới một instruction, verifier có thể chứng minh local variables, operand stack, tham số, receiver và giá trị trả về tương thích kiểu hay không?

Chúng ta còn xem **`StackMapTable`**, sự khác biệt `ClassFormatError` / `VerifyError`, ví dụ Java 17 chạy được và cách kiểm tra thực tế bằng `javap`.

## 1. Verification đứng ở đâu trong vòng đời JVM?

Mô hình khái niệm trong *Java Virtual Machine Specification* (JVMS):

```text
Bytecode / class representation
          │
          ▼
     Loading (tạo class/interface representation)
          │
          ▼
        Linking
          ├── Verification
          │      ├── kiểm tra định dạng class file
          │      ├── kiểm tra ràng buộc mã JVM
          │      └── kiểm tra kiểu và control flow
          ├── Preparation
          │      └── chuẩn bị storage và giá trị mặc định cho static fields
          └── Resolution
                 └── giải tham chiếu ký hiệu theo yêu cầu runtime
          │
          ▼
     Initialization
          └── thực thi class initialization method <clinit>
              khi có và khi JVM cần theo quy tắc
          │
          ▼
   Code được thực thi bởi interpreter/JIT
```

Đây là **trật tự khái niệm**, không phải yêu cầu mọi class đều được resolve toàn bộ trước khi bắt đầu chạy chương trình. JVMS cho phép **resolution có thể diễn ra theo nhu cầu**, còn quá trình tải/liên kết lớp liên quan khác có thể đan xen. Một implementation cũng có thể tổ chức/hoãn một số công việc kiểm tra theo các quy tắc đặc tả, nhưng **không được bỏ qua kết quả verification bắt buộc**.

### 1.1. Phân biệt verification, preparation, resolution, initialization

| Giai đoạn | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Loading** | JVM nhận diện và tạo biểu diễn của class/interface bằng class loader nào? | Loader tìm bytes của `app.Example` |
| **Verification** | Class file và mã bên trong có hợp lệ về dạng và type state? | `iload` không được đọc slot đang mang reference |
| **Preparation** | Static fields được chuẩn bị theo quy tắc VM ra sao? | `static int count` có giá trị chuẩn bị mặc định 0, trước initialization |
| **Resolution** | Một symbolic reference chỉ tới class/field/method thực nào? | `invokevirtual` có method reference cần giải |
| **Initialization** | Chạy code khởi tạo static của class khi bắt buộc? | `static { System.out.println("init"); }` |

**Không nhầm:** verifier **không chạy các nhánh `if` để thử xem chương trình cho ra kết quả gì**. Nó phân tích metadata và **trạng thái kiểu trừu tượng**. Việc lệnh gọi tìm được phương thức thực tại runtime còn liên quan tới resolution/linking; `NoSuchMethodError` vì thiếu method không đơn giản đồng nghĩa với một `VerifyError` do sai kiểu operand stack.

## 2. Lớp thứ nhất: format checking của tệp `.class`

Một class file có định dạng xác định, bắt đầu bằng `CAFEBABE` và có các trường `minor_version`, `major_version`, `constant_pool`, `access_flags`, `this_class`, `super_class`, danh sách field/method và các attributes.

```text
ClassFile
├── magic                  // phải là 0xCAFEBABE
├── minor_version
├── major_version
├── constant_pool_count
├── constant_pool[]
├── access_flags
├── this_class / super_class / interfaces[]
├── fields[]
├── methods[]
└── attributes[]
     └── Code attribute của phương thức có bytecode
          ├── max_stack
          ├── max_locals
          ├── code_length / code[]
          ├── exception_table[]
          └── attributes[]  (ví dụ StackMapTable)
```

Trong **format checking**, JVM phải nhận ra class-file structure hợp lệ: không thiếu bytes, không có dữ liệu rác bất hợp lệ ở cuối, magic đúng, các trường có index và độ dài hợp lệ, các predefined attributes phù hợp ràng buộc của chúng. Vấn đề class-file format cũng liên quan version tương thích của JVM.

Ví dụ lỗi định dạng cần nghĩ tới:

- Tệp `.class` bị cắt cụt khi copy, thiếu bytes của constant pool.
- `attribute_length` không khớp với kích thước thực của một attribute đã được định nghĩa.
- Một `constant_pool` entry chứa tag không hợp lệ cho định dạng/phiên bản được công nhận.
- Chỉ số tới constant pool chỉ đến loại mục không đúng tại vị trí bắt buộc.
- Cấu trúc `Code` attribute trái quy tắc định dạng của class-file version.

**Format checking và bytecode verification có liên quan nhưng không phải cùng khái niệm.** Dù cả hai đều góp phần kiểm tra tính toàn vẹn trước khi sử dụng class, một tệp có cấu trúc nhị phân hoàn chỉnh vẫn có thể chứa code **sai kiểu**.

### 2.1. `major.minor` không phải trạng thái kiểu

Class file `61.0` tương ứng Java 17 thông thường. Một JVM Java 11 có thể từ chối vì major của class quá mới — lỗi phiên bản, không phải bài toán xem `iadd` có đủ hai `int` trên stack hay không.

Class format preview dùng quy tắc minor đặc biệt `65535` ở những release phù hợp; cờ `--enable-preview` chỉ có ý nghĩa riêng với release tương ứng, **không** bỏ qua format checking/type verification và **không** cho phép chạy tùy tiện class files có version cao hơn.

### 2.2. Kết quả lỗi định dạng

`ClassFormatError` là lỗi tiêu biểu khi class-file representation bị hỏng về định dạng. `UnsupportedClassVersionError` báo class file có version không được JVM hỗ trợ hoặc tình huống version/preview không hợp lệ.

Đừng chỉ dựa vào một từ trong stack trace để “chữa” bằng `--enable-preview`, nâng heap hoặc thêm dependency. Phải nhìn **loại lỗi**, thông điệp version/constant-pool/attribute liên quan và artifact class thực sự được nạp.

## 3. Lớp thứ hai: cấu trúc instruction và luồng điều khiển

Mỗi method có bytecode mang các instruction, operands, nhánh và exception handlers. Verifier cùng các ràng buộc cấu trúc cần đảm bảo luồng thực thi không nhảy vào **giữa một instruction**, không đọc operand không tồn tại và không tạo đường đi trái quy tắc bytecode.

### 3.1. Control-flow graph (CFG)

Một method có thể được nhìn dưới dạng **basic blocks** — dãy instruction với điểm vào điều khiển xác định. Các cạnh đi theo:

- Đường tuần tự tới opcode tiếp theo.
- Các lệnh nhảy có điều kiện như `ifeq`, `if_icmpge`.
- `goto` và các target của `tableswitch` / `lookupswitch`.
- Các đường có thể chuyển sang **exception handler** khi instruction ở vùng protected phát sinh exception.
- Return hoặc throw để kết thúc đường bình thường/bất thường, không có successor tuần tự thông thường.

Ví dụ Java:

```java
static int choose(boolean yes, int value) {
    int result;
    if (yes) {
        result = value + 1;
    } else {
        result = value - 1;
    }
    return result;
}
```

CFG ý tưởng:

```text
                 [start]
                    │
                 test yes
                 /      \
              true      false
               │          │
         result = v+1  result = v-1
               │          │
               └────┬─────┘
                    ▼
            [join: result is int]
                    │
               return result
```

Cả hai đường dẫn đặt `result` thành **`int`** trước điểm nhập lại. Vì vậy instruction tải nó lên operand stack để `ireturn` có type state hợp lệ.

Đoạn này là **một phương thức minh họa**, không phải file tự chạy; ví dụ chương trình độc lập nằm ở mục 8.

### 3.2. Một branch target phải hợp lệ

Đối với bytecode branch:

- Target phải nằm trong `code[]` của chính phương thức.
- Target phải là **đầu của một instruction**, không phải byte operand hay padding.
- Switch instructions có encoding riêng (bao gồm alignment, default và jump offsets).
- Exception handler `handler_pc` cũng phải trỏ tới opcode đầu hợp lệ; các range bảo vệ trong `exception_table` phải thỏa quy tắc.
- Control flow và type state tại các join phải tương thích, không chỉ “địa chỉ có tồn tại”.

Ví dụ giả lập:

```text
0: bipush 100   // opcode ở 0, toán hạng immediate ở byte 1
2: istore_0

Sai: goto tới byte 1
Đúng về ranh giới opcode: goto tới byte 0 hoặc 2 (vẫn cần đúng kiểu/flow)
```

Đây là sơ đồ **bytecode không hợp lệ** để giải thích; không thể tạo “goto byte 1” bằng cú pháp Java source hợp lệ thông thường. Khi instrument class files, dùng thư viện bytecode xử lý đúng branch offsets thay vì tự sửa bytes bằng find/replace.

### 3.3. Độ sâu operand stack phải nhất quán ở điểm nhập

Giả sử bytecode trừu tượng có hai đường tới cùng nhãn `L`:

```text
path A: stack = [int]
path B: stack = []
L: ireturn
```

Không thể để `ireturn` nhận **hai trạng thái có số operand khác nhau** tùy đường đến; không có bảo đảm luôn có một `int` tại điểm `L`.

Một lỗi khác:

```text
path A: stack = [int]
path B: stack = [reference-to-String]
L: ireturn
```

Hai đường có cùng số **phần tử** nhưng **kiểu không nhất quán** cho `ireturn`. Verifier không được chấp nhận một branch state mà ở đó instruction yêu cầu `int` nhưng có thể nhận object reference.

**Không phải** mọi nhánh phải có cùng stack state ở tất cả instruction. Chỉ những nơi luồng điều khiển hội tụ/điều kiện typing yêu cầu tương thích mới cần trạng thái thích hợp; mỗi basic block có thể dùng operand stack theo cách riêng.

## 4. Lớp thứ ba: type safety trên operand stack và local variables

Verifier xem **kiểu trừu tượng** của từng giá trị. Nó không cần biết `x = 12` hay `x = 99` tại runtime; nó cần chứng minh `x` ở vị trí đó là giá trị có **verification type** tương ứng với opcode.

Ví dụ:

| Instruction | Tiền điều kiện kiểu chủ yếu | Hành động |
| --- | --- | --- |
| `iload n` | Local `n` chứa giá trị thuộc int-family phù hợp | Đẩy `int` lên operand stack |
| `aload n` | Local `n` chứa reference phù hợp | Đẩy reference lên stack |
| `iadd` | Hai giá trị `int` ở đỉnh stack | Pop hai `int`, push kết quả `int` |
| `ladd` | Hai giá trị `long` category 2 | Pop hai `long`, push một `long` |
| `getfield` | Objectref tương thích với field resolution/access; field có descriptor hợp lệ | Pop receiver và push field value |
| `putfield` | Receiver cùng field value có type tương thích | Ghi field với type hợp lệ |
| `invokestatic` | Đủ arguments, các kiểu tương ứng method descriptor | Tiêu thụ arguments, đưa return value lên stack nếu non-`void` |
| `invokevirtual` | Có objectref receiver và các arguments thích hợp | Thực hiện lời gọi instance |
| `ireturn` | Return descriptor cho phép int-family và stack có `int` | Kết thúc bình thường, trả int-family value |
| `areturn` | Return descriptor là reference type, reference ở stack tương thích | Trả reference bình thường |

Bảng trên chỉ là **mô tả điều kiện kiểu chính**; mỗi opcode trong JVMS có các quy tắc chi tiết hơn về access, uninitialized values, constant pool và trạng thái frame.

### 4.1. Vì sao không thể dùng `int` như `String`?

Hãy tưởng tượng bytecode giả:

```text
iconst_1
invokevirtual java/lang/String.length:()I
```

Lệnh `invokevirtual` cần **objectref receiver** tương thích, nhưng operand stack chỉ có `int`. Mã bytecode đó **không hợp lệ về type safety**; verifier có thể từ chối bằng `VerifyError`. Không có một “ép kiểu ngầm từ int sang String” chỉ vì hai giá trị có thể tình cờ cùng kích thước máy.

### 4.2. Local-variable array có type state theo đường đi

Một local slot có thể được tái sử dụng cho giá trị khác sau khi biến cũ không còn cần thiết, nhưng ở **mọi instruction sử dụng**, verifier phải chứng minh slot có type hợp lệ trên mọi đường tới đó.

Mô hình lỗi:

```text
if condition:
    istore_2       // slot 2 là int
else:
    astore_2       // slot 2 là reference

join:
    iload_2        // không thể chứng minh luôn là int
```

Mã giả này không phải Java source được phép. Compiler Java thông thường sinh code tránh trạng thái sai như vậy. Nhưng bytecode generator có thể tạo class không an toàn nếu không tính type state khi hợp nhất luồng.

### 4.3. `long` và `double`: category 2

`long` và `double` là giá trị **category 2**:

- Trong local-variable array, mỗi giá trị chiếm **hai slots liên tiếp**; `lload n`/`dload n` truy xuất từ index **thấp hơn**.
- Trên operand stack, một `long`/`double` chiếm **hai đơn vị độ sâu**, nhưng là một giá trị logic duy nhất.
- Không được dùng `pop` (vốn thao tác một category-1 value) để loại bỏ “một nửa” `long`; cần opcode phù hợp như `pop2`.
- Ghi vào slot thứ hai của cặp local có thể vô hiệu hóa giá trị category 2 bắt đầu ở slot đầu.

Ví dụ method `static long plusOne(long input)` nhận `input` ở local slots **0–1** và kết thúc bằng `lreturn`; không có hai tham số `int` chỉ vì dùng hai slots.

## 5. `StackMapTable` và verification bằng type checking

Từ class-file **version 50.0 (Java 6)** trở lên, JVMS quy định verifier sử dụng **verification by type checking** với thông tin stack-map frames. Class-file version thấp hơn 50.0 dùng cơ chế **verification by type inference** theo đặc tả legacy; với version đúng **50.0**, có ngoại lệ tương thích cho phép implementation fallback trong điều kiện được JVMS nêu. Đối với class files Java 17 (`61.0`), cần tư duy theo **type checking/`StackMapTable`**, không trông chờ JVM tự suy kiểu theo kiểu cũ cho bytecode sai metadata.

Một `StackMapTable` là **attribute nằm bên trong `Code` attribute** của method; nó giúp verifier kiểm tra các trạng thái kiểu ở các **điểm điều khiển quan trọng**, đặc biệt basic-block entries.

### 5.1. Stack-map frame ghi gì?

Với một bytecode offset, stack-map frame mô tả kiểu trừu tượng của:

- Các local-variable slots cần biết tại điểm đó.
- Các giá trị trên operand stack tại điểm đó.
- Thông tin đặc biệt liên quan đến object chưa khởi tạo, khi cần.

Các verification types có thể gồm:

| Verification type | Ý nghĩa |
| --- | --- |
| `Integer` | Dạng int-family trong type system của verifier |
| `Float` | Giá trị float |
| `Long` | Giá trị long, độ rộng category 2 |
| `Double` | Giá trị double, độ rộng category 2 |
| `Null` | Giá trị null reference |
| `Object(className)` | Reference có loại class/array thích hợp |
| `UninitializedThis` | Receiver của constructor chưa hoàn tất initialization |
| `Uninitialized(offset)` | Object chưa khởi tạo, gắn với instruction `new` tại offset đó |
| `Top` | Thông tin top/unusable theo quy tắc verification type system, **không** phải Java class tên `Top` |

Đây là **verification types**, không đồng nghĩa Java Reflection types hoặc runtime values. Ví dụ source `boolean`/`byte`/`char`/`short` thường được biểu diễn qua `Integer` verification type ở nhiều vị trí bytecode.

### 5.2. Không phải một stack-map frame cho từng instruction

Compiler không cần viết một `StackMapTable` entry cho **mọi opcode**. Ý đồ của format là các frames xuất hiện tại điểm đầu các basic blocks cần có trạng thái được xác nhận; verifier áp dụng **type transitions** để suy trạng thái sau từng instruction từ trạng thái đầu block.

Các dạng tiết kiệm dung lượng:

- `same_frame`: state cục bộ giữ nguyên, operand stack rỗng ở điểm áp dụng.
- `same_locals_1_stack_item_frame`: local state giữ nguyên, stack có một item.
- `append_frame` / `chop_frame`: thêm/bớt thông tin về locals.
- `full_frame`: mô tả toàn bộ locals và stack state cần thiết.

Đó là **các dạng encoding của stack-map entries**, không phải lệnh bytecode chạy ở runtime như `iadd` hoặc `goto`.

### 5.3. Nếu không thấy `StackMapTable` thì sao?

Theo JVMS, class file từ version 50.0 trở lên **có thể không có attribute `StackMapTable` được ghi tường minh**; khi đó nó được hiểu tương đương một **implicit StackMapTable có số entries bằng 0**. Điều đó **không** đồng nghĩa verifier bị vô hiệu hóa.

Một phương thức tuyến tính không có join phức tạp có thể hợp lệ với ít hoặc không có entries. Ngược lại, một phương thức có branch targets cần frame phù hợp mà class file bỏ thiếu thông tin bắt buộc có thể bị từ chối bằng `VerifyError`, ví dụ thông điệp mang ý nghĩa “Expecting a stackmap frame at branch target”.

### 5.4. Việc đọc StackMapTable từ `javap`

```bash
javac --release 17 VerificationDemo.java
javap -c -v -p VerificationDemo
```

Trong output, tìm các khối:

```text
Code:
  stack=..., locals=..., args_size=...
  ...
StackMapTable: number_of_entries = ...
  frame_type = ...
```

`number_of_entries`, `frame_type` và offsets thực tế phụ thuộc class đã biên dịch và compiler; **không được đoán chúng từ số dòng Java source**.

## 6. Bài toán join: “an toàn trên MỌI đường đi”

Verifier phải kiểm tra những state đi vào một block nhất định thỏa **kiểu và độ sâu operand stack** mà block đòi hỏi. Nó không chỉ chạy thử một nhánh “có vẻ đúng”.

Mô hình hợp lệ:

```text
                 test
               /      \
path A: stack=[int]   path B: stack=[int]
               \      /
                 join
                 ireturn
```

Hai state đều cho phép `ireturn` với `int`.

Mô hình không hợp lệ:

```text
                 test
               /      \
path A: stack=[int]   path B: stack=[String ref]
               \      /
                 join
                 ireturn    // không bảo đảm có int
```

Nếu source Java thực tế viết:

```java
static int f(boolean flag) {
    int x;
    if (flag) {
        x = 10;
    } else {
        x = 20;
    }
    return x;
}
```

`javac` sẽ tạo bytecode hợp lệ và stack-map metadata thích hợp. Nó không sửa sai bằng cách “tự ép String thành int” nếu bytecode generator cố tạo đường vào không nhất quán.

### 6.1. Join của reference types không nhất thiết giữ đúng class cụ thể

Ví dụ một nhánh cung cấp reference kiểu `String`, nhánh kia kiểu `StringBuilder`; chương trình có thể hợp lệ nếu code ở điểm join chỉ đòi **một common supertype** (chẳng hạn `Object`), theo quy tắc assignability của verification type system.

```java
static int describe(boolean asText) {
    Object value;
    if (asText) {
        value = "x";
    } else {
        value = new StringBuilder("y");
    }
    return value.toString().length();
}
```

Đây là **phương thức minh họa**. Source khai báo `Object` nên compiler tạo bytecode mà join không cần biết object cụ thể là `String` hay `StringBuilder`, chỉ cần một reference type tương thích để gọi `Object.toString()`.

**Không kết luận** rằng mọi đường branch phải có cùng runtime class chính xác. Cái cần chứng minh là **assignability và frame type state hợp lệ theo instruction ở đích**.

## 7. Constructor và tham chiếu chưa khởi tạo

Một trong những vai trò quan trọng của verifier là ngăn code dùng object **trước khi instance initialization hoàn tất**.

Ví dụ source:

```java
Object obj = new Object();
```

Bytecode minh họa:

```text
new java/lang/Object       // tạo uninitialized reference
dup
invokespecial java/lang/Object.<init>:()V
astore_1                   // lưu reference đã được khởi tạo
```

Trong verifier type system, reference ngay sau `new` có dạng **`Uninitialized(offset)`** liên hệ với bytecode offset của instruction tạo ra nó. Khi `<init>` được gọi hợp lệ và hoàn tất, trạng thái được cập nhật để có thể sử dụng như reference đã khởi tạo.

Với constructor của chính class, local slot 0 có thể bắt đầu bằng **`UninitializedThis`** và phải tuân thủ các quy tắc liên quan tới lời gọi `this(...)` hoặc `super(...)`.

**Sai về bytecode:** lấy uninitialized reference và gọi bừa một instance method như `toString()`, hoặc trả reference đó theo cách trái quy tắc, trước khi constructor hợp lệ hoàn tất. Loại lỗi này không thể được “hợp pháp hóa” chỉ bằng cast hoặc sửa tên constant pool.

### 7.1. An toàn kiểu không có nghĩa không thể gặp `NullPointerException`

Verifier chứng minh **hình thức và kiểu** chứ không phải mọi điều kiện runtime. Nếu receiver type là reference hợp lệ nhưng **giá trị là null**, `invokevirtual` vẫn có thể ném `NullPointerException` khi chạy.

Tương tự, verifier không đảm bảo:

- Mảng luôn có index trong giới hạn (`ArrayIndexOutOfBoundsException`).
- Phép chia nguyên không bao giờ dùng 0 (`ArithmeticException`).
- Chương trình không hết heap (`OutOfMemoryError`).
- Hai thread không xảy ra race condition hoặc deadlock.
- Cast từ `Object` sang `String` luôn thành công ở runtime (`ClassCastException`).
- SQL query hoặc logic nghiệp vụ cho kết quả đúng.

**“Type-safe bytecode” không đồng nghĩa “error-free application”.**

## 8. Ví dụ Java 17+ chạy được: theo dõi branch, handler và category 2

Tạo file **`VerificationDemo.java`**:

```java
public class VerificationDemo {

    static int choose(boolean positive, int value) {
        int result;
        if (positive) {
            result = value + 1;
        } else {
            result = value - 1;
        }
        return result;
    }

    static int safeDivide(int numerator, int denominator) {
        try {
            return numerator / denominator;
        } catch (ArithmeticException ex) {
            return -1;
        }
    }

    static long plusOne(long value) {
        return value + 1L;
    }

    public static void main(String[] args) {
        System.out.println("choose true = " + choose(true, 4));
        System.out.println("choose false = " + choose(false, 4));
        System.out.println("divide = " + safeDivide(10, 0));
        System.out.println("long = " + plusOne(41L));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 VerificationDemo.java
java VerificationDemo
```

**Stdout xác định:**

```text
choose true = 5
choose false = 3
divide = -1
long = 42
```

Tại `choose(true,4)`, `result=4+1=5`; tại `choose(false,4)`, `result=4-1=3`. `safeDivide(10,0)` phát sinh `ArithmeticException` tại `idiv` và catch trả `-1`; `plusOne(41L)` dùng arithmetic category-2 và trả `42L`.

### 8.1. Những gì bytecode thể hiện

```bash
javap -c -p VerificationDemo
javap -v -p VerificationDemo
```

Khi đọc **`choose(boolean,int)`**, dự kiến thấy logic như:

```text
iload_0                 // boolean được xử lý theo int-family
ifeq ELSE
  iload_1
  iconst_1
  iadd
  istore_2
  goto JOIN
ELSE:
  iload_1
  iconst_1
  isub
  istore_2
JOIN:
  iload_2
  ireturn
```

Đây là **sơ đồ opcode không kèm offset** để giải thích, không phải nguyên văn output `javap`; trong output thật nhãn `ELSE`/`JOIN` là số bytecode offsets. Cả hai nhánh đều đưa `int` vào local 2 trước `iload_2`.

Ở **`safeDivide(int,int)`**, tìm `idiv`, một **Exception table** với `Class java/lang/ArithmeticException` và đoạn handler nhận exception reference qua `astore` rồi `ireturn` giá trị `-1`. Khi vào handler, operand stack đã được reset thành **một reference đến ngoại lệ** — khác với flow bình thường trả một `int`.

Ở **`plusOne(long)`**, thường thấy:

```text
lload_0
lconst_1
ladd
lreturn
```

`long value` là một giá trị category 2 tại local slots 0–1. `ladd` và `lreturn` đòi state thuộc loại `long` thích hợp; không thể thay `lreturn` bằng `ireturn` rồi mong verifier tự chuyển kiểu.

### 8.2. Quan sát `StackMapTable` của các nhánh

Dùng:

```bash
javap -v -p VerificationDemo
```

Tìm `StackMapTable` trong phần của `choose` và `safeDivide`. Ở branch target và handler, các stack-map entries giúp mô tả trạng thái types:

- Ở điểm vào nhánh `else`: tham số `positive` và `value` có kiểu thích hợp, stack rỗng theo cách bố trí bytecode thường dùng.
- Ở `JOIN`: local `result` là `int` trên mọi đường hợp lệ, có thể được `iload` và `ireturn`.
- Ở handler `ArithmeticException`: operand stack tại handler có một exception reference, không phải hai toán hạng `int` còn sót từ `idiv`.

Số entry, dạng frame và offset cụ thể do compiler quyết định. `javap -v` thể hiện **class metadata**, không phải JVM đang tự ghi lại live stack của một lời gọi đã chạy.

## 9. Exception handler là một cạnh control-flow đặc biệt

`exception_table` nằm trong `Code` attribute, có các trường:

```text
start_pc, end_pc, handler_pc, catch_type
```

- Handler bảo vệ vùng **`[start_pc, end_pc)`** (start-inclusive, end-exclusive).
- `handler_pc` trỏ tới instruction đầu handler.
- `catch_type` trỏ tới exception class phù hợp hoặc bằng **0** để match mọi Throwable.
- Các entries được xem theo **thứ tự**; entry đầu tiên phù hợp với pc/type được dùng.

Ở điểm vào handler, JVM đặt operand stack thành **một exception object reference**, xóa những operands cũ trong frame đó. Đây là nguyên tắc quan trọng cho kiểm tra type state tại handler.

Ví dụ lỗi thiết kế bytecode:

```text
TRY:                  // đẩy hai int trước phép tính
  iload_0
  iload_1
  idiv                // có thể ném ArithmeticException

HANDLER:
  iadd                // SAI: không có sẵn hai int ở handler entry
```

Khi chuyển vào handler, stack là `[exceptionRef]`, vì vậy `iadd` ở đầu handler không có hai `int` tương thích. Một handler hợp lệ thường bắt đầu với `astore` để lấy reference, sau đó tự tính giá trị cần trả.

## 10. Các lỗi Verification thường gặp với bytecode generator

| Lỗi bytecode | Vì sao không an toàn/hợp lệ? |
| --- | --- |
| `iadd` chỉ có một `int` trên stack | Stack underflow / thiếu toán hạng |
| `iadd` gặp `String` reference | Sai operand types |
| `iload_2` khi local slot 2 không chắc có `int` trên mọi đường | Sử dụng local chưa có type state phù hợp |
| Branch vào byte operand của instruction khác | Target không phải ranh giới opcode |
| Hai đường join có stack heights không tương thích | Không có trạng thái đầu block hợp lệ |
| `ireturn` từ method trả `long` | Return opcode/type trái method descriptor |
| `invokevirtual` với receiver là `int` | Receiver phải là reference tương thích |
| Gọi method với số lượng/kiểu arguments khác descriptor | Operand stack không cung cấp đúng types |
| `lload` từ cặp slots đã bị ghi đè | Không còn giá trị `long` hợp lệ tại index |
| Dùng uninitialized object reference như object đã khởi tạo | Vi phạm quy tắc initialization của `new`/`<init>` |
| Handler bắt đầu bằng opcode yêu cầu hai `int` | Handler entry stack có một exception reference |
| Sửa branch offsets nhưng không cập nhật stack maps | StackMapTable không còn nhất quán với CFG mới |

**Đừng thử tạo các lỗi này bằng Java source bình thường:** `javac` chủ động tạo code hợp lệ hoặc từ chối source không đúng kiểu. Những lỗi này thường có ý nghĩa khi xem bytecode đã bị sửa, code do compiler/transformer khác tạo hoặc class file bị hỏng.

## 11. `VerifyError`, `ClassFormatError` và các lỗi liên kết khác

| Loại lỗi | Bối cảnh thường gặp | Cần điều tra |
| --- | --- | --- |
| **`ClassFormatError`** | Dữ liệu class file không đáp ứng định dạng nhị phân/attributes | Artifact có bị hỏng, constant pool hoặc lengths sai? |
| **`UnsupportedClassVersionError`** | Class-file version/preview không được runtime hỗ trợ | `java -version`, major/minor, flags preview |
| **`VerifyError`** | Bytecode hoặc type state không thỏa verification rules | Opcodes, branch targets, StackMapTable, exception table |
| **`NoClassDefFoundError`** | Class cần dùng không được định nghĩa/tìm thấy trong hoàn cảnh tương ứng | Classpath/module path, dependency, init error trước đó |
| **`NoSuchMethodError` / `NoSuchFieldError`** | Symbolic reference không tìm thấy member mong đợi khi resolution | Version JAR và binary compatibility |
| **`IllegalAccessError`** | Access check/linkage trái quyền truy cập runtime | Visibility, modules, nestmate, phiên bản artifact |
| **`ExceptionInInitializerError`** | Static initialization `<clinit>` thất bại theo những điều kiện tương ứng | Code khởi tạo static và nguyên nhân bên trong |
| **`ClassCastException` / `NullPointerException`** | Type cast hoặc reference value sai khi đang thực thi | Dữ liệu/runtime logic; không tự suy verifier thất bại |

Bảng trên là **định hướng chẩn đoán**; lỗi cụ thể còn phụ thuộc class loader, thời điểm phát hiện và implementation. `VerifyError`/`ClassFormatError` thuộc nhóm lỗi liên quan tính hợp lệ class file, nhưng không phải mọi lỗi chương trình đều do verifier.

### 11.1. Một thông báo `VerifyError` không có nghĩa JDK “không hỗ trợ Java source”

Nếu code Java 17 có thể biên dịch bằng `javac --release 17` nhưng ở runtime thấy `VerifyError` trong một lớp của thư viện, hãy kiểm tra:

1. Runtime thực sự đang nạp **file `.class` nào** (có bản copy trong nhiều JAR không?).
2. Lớp đó có bị Java agent/instrumentation transformer chỉnh lại không?
3. Transformer có cập nhật **branch offsets, `StackMapTable` và exception handler ranges** không?
4. `java -version` và build target có đúng không?
5. Lỗi chỉ xảy ra sau khi nâng JDK hay đổi phiên bản framework/bytecode library?

Không nên mặc định lỗi do số lượng heap nhỏ hoặc dùng `--enable-preview` để “né” verification. Bật preview không hợp pháp hóa bytecode sai.

## 12. Giới hạn của verifier: điều nó KHÔNG chứng minh

Verifier được thiết kế để bảo đảm **các ràng buộc type và structure của JVM**, nhưng không phải công cụ chứng minh chương trình đúng mọi mặt.

| Điều verifier có thể bảo vệ ở mức tĩnh | Điều vẫn phải xử lý tại runtime hoặc ở ứng dụng |
| --- | --- |
| Instruction nhận operand có loại hợp lệ | `NullPointerException` khi reference hợp lệ nhưng value null |
| Một local được đọc với type phù hợp | Logic nghiệp vụ tính sai dù types đúng |
| Branch target hợp lệ và frame join an toàn | Deadlock hoặc race condition giữa threads |
| Return opcode phù hợp method descriptor | Dữ liệu đầu vào vượt giới hạn business |
| Quy tắc object initialization hợp lệ | `ClassCastException` khi downcast thực tế thất bại |
| Operand stack không bị mất cân bằng sai quy tắc | `OutOfMemoryError` khi không đủ memory |
| Basic class-file structure đủ hợp lệ để dùng | SQL injection, phân quyền ứng dụng hoặc lỗ hổng logic |

Ví dụ `checkcast java/lang/String` là opcode có **type safety hợp lệ** khi đầu vào là object reference, nhưng nếu object thật là `Integer` thì **runtime** có thể ném `ClassCastException`. Verifier không được yêu cầu đoán mọi object thực sẽ có dynamic type gì.

Tương tự, array stores còn có runtime checks theo đặc tả với những trường hợp tương ứng; bytecode verification không thay thế mọi kiểm tra động.

## 13. Làm việc với ASM, Byte Buddy và Java agents

Khi viết bytecode generator hoặc transformer, vấn đề thực tế lớn nhất là **giữ tương thích giữa control-flow graph và stack-map frames**. Một phép chỉnh tưởng như đơn giản — chèn logging vào đầu method, thêm `try/catch`, thay opcode, mở rộng `switch` — có thể:

- Dịch bytecode offsets và branch targets.
- Đổi vị trí basic-block entry.
- Đổi trạng thái operand stack hoặc local-variable types tại điểm join.
- Làm `max_stack` hoặc `max_locals` không đủ.
- Làm exception table hoặc frame offsets không phù hợp code mới.
- Đụng tới quy tắc uninitialized reference quanh `new`/`<init>`.

Checklist để sửa an toàn:

1. Xác định class-file version và method descriptor trước khi biến đổi.
2. Duy trì type state chính xác của operand stack/locals khi chèn instruction.
3. Xây lại/cập nhật jump labels, try/catch ranges và stack-map entries theo tool được hỗ trợ.
4. Đảm bảo `max_stack` và `max_locals` đủ cho mọi đường đi có thể thực thi.
5. Không đụng trái quy tắc uninitialized object hoặc monitor.
6. Chạy tests trên đúng JDK target, bao gồm các nhánh và exception paths.
7. Dùng `javap -c -v` quan sát class file **sau biến đổi**, không chỉ bản `javac` ban đầu.

Một số thư viện như ASM có tính năng tự tính toán stack-map frames/max stack khi cấu hình phù hợp, nhưng phải tuân thủ hướng dẫn phiên bản cụ thể; không có lựa chọn “tự fix mọi bytecode sai” cho mọi biến đổi.

**Không nên** tắt verifier như một cách khắc phục sự cố production. Đây là một phần quan trọng trong các đảm bảo an toàn của mô hình JVM; thay vào đó hãy sửa class-file/transformer/toolchain không hợp lệ.

## 14. Ba bước đọc một lỗi thật

### Tình huống A: `VerifyError: Bad type on operand stack`

Hướng chẩn đoán:

- Tìm class và method mà lỗi nêu, xác định instruction/offset.
- Đọc `javap -c -v -p ClassName` của artifact đang được nạp.
- Kiểm tra opcode tại offset, `StackMapTable` type state và các branch dẫn tới đó.
- Đối chiếu method descriptor và type of receiver/arguments.

Không kết luận “JVM runtime data chứa sai kiểu vì race”; thường cần điều tra **bytecode/type state**.

### Tình huống B: `VerifyError: Expecting a stackmap frame at branch target`

Đặc biệt hay gặp khi tool chèn `goto` hoặc thêm một basic block mà không cập nhật `StackMapTable`. Cần kiểm tra offsets/frames của class-file version đang dùng. Thêm một frame tại vị trí dự đoán mà không phân tích state có thể tiếp tục lỗi; nên dùng generator có khả năng tính frame hợp lệ.

### Tình huống C: `ClassFormatError` vì malformed attribute

Lỗi có thể bắt nguồn từ công cụ đóng gói/transformer ghi sai attribute length hay constant pool. Kiểm tra artifact bytes đầu vào và chương trình sinh class, không chỉ `java -version`. Nếu class đã bị truncate, không thể xử lý bằng `catch` trong `main` vì lỗi có thể xuất hiện trước lúc method cần chạy được nạp.

## 15. Các nhầm lẫn hay gặp

1. **“`javac` biên dịch được là JVM không cần verification.”** Sai. JVM có thể nhận bytecode từ nhiều nguồn và phải thực hiện kiểm tra theo hợp đồng class-file/linking.
2. **“Verification và initialization là một.”** Sai. Verification kiểm tra hợp lệ, initialization chạy code `<clinit>` theo điều kiện riêng.
3. **“JVM verifier chạy mọi nhánh với dữ liệu mẫu.”** Sai. Nó phân tích cấu trúc và **trạng thái kiểu trừu tượng**, không chạy test cases.
4. **“Thấy `StackMapTable` thì đó là live Java stack trace.”** Sai. Đây là metadata phục vụ type checking tại các bytecode offsets.
5. **“Mỗi instruction bắt buộc phải có stack-map frame riêng.”** Sai. Frames thể hiện các điểm trạng thái cần thiết; nhiều instruction được kiểm tra bằng type transitions.
6. **“Không có `StackMapTable` tường minh thì chắc chắn lớp không được verify.”** Sai. Với version 50+ có quy tắc implicit zero-entry stack map.
7. **“Join chỉ cần cùng chiều dài operand stack, bất kể types.”** Sai. Types còn phải tương thích.
8. **“Mọi reference trên hai nhánh phải cùng runtime class.”** Sai. Assignability có thể cho phép common supertype thích hợp.
9. **“`iadd` có thể cộng hai `Object` vì chúng có địa chỉ máy.”** Sai. Opcode `iadd` yêu cầu `int`.
10. **“`long` dùng một local slot như `int`.”** Sai. `long`/`double` dùng hai local slots, là category 2.
11. **“`new` tạo object có thể gọi instance method bất kỳ ngay trước `<init>`.”** Sai. Uninitialized references bị ràng buộc.
12. **“`VerifyError` đồng nghĩa Java source syntax sai.”** Sai. Compiler có thể đã thành công, còn bytecode đã bị transform/malformed.
13. **“`--enable-preview` làm JVM bỏ qua kiểm tra type safety.”** Sai. Cờ chỉ bật preview features được hỗ trợ đúng release.
14. **“Verifier đảm bảo không bao giờ có `NullPointerException`.”** Sai. Null là điều kiện runtime.
15. **“Verifier sửa bytecode hỏng trong lúc load.”** Sai. Nếu bytecode không thỏa ràng buộc, class bị từ chối; không có cam kết JVM tự chỉnh source/offsets.
16. **“Lỗi JIT compilation là `VerifyError`.”** Không nhất thiết. Verification là một bước ngữ nghĩa riêng với JIT optimization/runtime execution.
17. **“Một lỗi metadata `StackMapTable` có thể giải bằng tăng `-Xmx`.”** Sai. Đây là vấn đề class-file/type-state, không phải thiếu heap.

## 16. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Với `static int f(boolean b, int n)`, hai nhánh đều gán `int result` rồi return. Vì sao join hợp lệ?

**Đáp án:** Tại join, local slot cho `result` có type `int` hợp lệ trên cả hai đường. `iload` và `ireturn` vì vậy có operand type đúng.

**Câu 2.** Nếu nhánh A để stack `[int]` và nhánh B để stack `[String ref]` rồi đều chạy `iadd`, vấn đề gì?

**Đáp án:** `iadd` yêu cầu **hai `int`**, trong khi cả hai đường đều không đảm bảo đủ kiểu/số toán hạng. State tại join và điều kiện instruction không hợp lệ; bytecode có thể bị từ chối bằng `VerifyError`.

**Câu 3.** `StackMapTable` dùng cho debug tên local variables hay phục vụ verifier?

**Đáp án:** Phục vụ **verification by type checking**, chứa thông tin type state tại những bytecode offsets; không thay thế `LocalVariableTable` cho debug tên biến.

**Câu 4.** Một class 61.0 không có `StackMapTable` hiển thị trong `javap`. Có chắc JVM bỏ qua verification không?

**Đáp án:** Không. JVM hiểu implicit zero-entry stack map khi thiếu attribute; phương thức chỉ hợp lệ nếu đáp ứng những điều kiện verification tương ứng.

**Câu 5.** Vì sao một reference từ `new` chưa được xem như object đã initialized?

**Đáp án:** Verifier theo dõi `Uninitialized(offset)` / `UninitializedThis` và yêu cầu constructor initialization qua `<init>` hợp lệ trước những cách sử dụng bị ràng buộc.

**Câu 6.** Khi exception handler bắt đầu, operand stack chứa những gì?

**Đáp án:** **Một exception reference**, không phải các toán hạng cũ của lệnh đã phát sinh exception.

**Câu 7.** Verifier đã chấp nhận method có `idiv`. Có bảo đảm divisor khác 0 ở runtime?

**Đáp án:** Không. Verifier xác minh kiểu `int` của operands; chia 0 vẫn có thể ném `ArithmeticException` trong lúc chạy.

**Câu 8.** `ClassFormatError` vì tệp class bị truncate và `VerifyError` vì thiếu stack-map frame là một loại lỗi giống nhau hoàn toàn?

**Đáp án:** Không. Một lỗi thuộc **format/data structure**, lỗi kia thuộc **bytecode verification/type-state**; thông điệp cụ thể và bước điều tra khác nhau.

**Câu 9.** Một Java agent vừa thêm `goto`, method không còn verify. Điều nên kiểm tra đầu tiên?

**Đáp án:** Instruction offsets, branch targets, basic-block entries, `StackMapTable` và type states, `max_stack`/`max_locals`; sửa transformer, không tắt verifier.

## 17. Tổng kết luồng phân tích

```text
Class bytes
    │
    ▼
Format check
  ├─ magic, version, constant pool, length, attributes
  └─ không hợp lệ → class bị từ chối
    │ hợp lệ
    ▼
Bytecode / control-flow structure
  ├─ opcode, operands, branch/handler targets
  └─ sai → class bị từ chối
    │ hợp lệ
    ▼
Type checking
  ├─ method descriptor → initial type state
  ├─ StackMapTable → state tại basic block entries
  ├─ instructions → state transitions
  ├─ joins → stack height và type assignability
  ├─ constructors → uninitialized reference constraints
  └─ sai → VerifyError
    │
    ▼
Code có thể được JVM dùng theo các quy tắc loading/linking
    │
    ▼
Runtime checks vẫn tồn tại (null, bounds, casts, memory, ...)
```

**Ghi nhớ:** Verification không chỉ hỏi “class file đọc được không”, mà còn phải xác định **control flow và type state an toàn trên mọi đường đi tới instruction**. `StackMapTable` cung cấp metadata trạng thái kiểu để JVM kiểm tra hiệu quả; `VerifyError` cảnh báo lỗi về code/type constraints, trong khi `ClassFormatError` thiên về cấu trúc class file. Sau khi verification thành công, ứng dụng **vẫn có thể** gặp runtime exception hoặc bug nghiệp vụ. Đó là ranh giới giữa **đảm bảo của VM** và **trách nhiệm của code ứng dụng**.

### Tài liệu tham khảo

- [JVMS Java SE 17 — ClassFile structure (4.1)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 17 — `StackMapTable` attribute (4.7.4)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.4).
- [JVMS Java SE 17 — Format Checking (4.8)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.8).
- [JVMS Java SE 17 — Constraints on JVM Code (4.9)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.9).
- [JVMS Java SE 17 — Verification of class Files (4.10)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10).
- [JVMS Java SE 17 — Linking/Verification (5.4.1)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.1).
- [Oracle Java SE 17 — `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
