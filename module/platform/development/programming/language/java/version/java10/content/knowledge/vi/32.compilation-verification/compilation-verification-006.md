# Quan hệ giữa `var` và bytecode có kiểu tĩnh (Java 10+)

## 1. Câu trả lời cốt lõi

Từ **Java 10 (JEP 286 — Local-Variable Type Inference)**, ta có thể viết:

~~~java
var count = 40;
~~~

thay cho:

~~~java
int count = 40;
~~~

Nhưng **`var` không tạo ra biến kiểu động**. Trình biên dịch `javac` xác định kiểu từ biểu thức khởi tạo ngay **lúc biên dịch**; trong ví dụ trên, kiểu của `count` chính xác là `int`. Khi sinh bytecode, compiler dùng các lệnh và tham chiếu kiểu bình thường của JVM, chẳng hạn `istore`, `iload`, `iadd` và kiểu `I` trong metadata gỡ lỗi. **Không tồn tại một kiểu dữ liệu JVM tên `var`** hay một opcode “`var`” dành riêng cho Local-Variable Type Inference.

Bài thuộc nhóm **Biên dịch và kiểm chứng**, module **Java 10**. Nó tập trung vào mối liên hệ giữa:
- Kiểu suy luận ở source code;
- Kiểm tra kiểu tĩnh của compiler;
- Các bytecode instructions và type descriptors trong file `.class`;
- Thông tin gỡ lỗi **LocalVariableTable**, **LocalVariableTypeTable**;
- **Bytecode verification** của JVM và giới hạn về generic erasure.

Nội dung được trình bày theo Java 10 và các JDK hiện đại (JDK 17, 21, 25). Ví dụ có thể biên dịch bằng JDK 17+ với `--release 10`, để quan sát bytecode tương thích với Java 10 mà không cần một JDK 10 đã cũ.

### Bạn sẽ hiểu được gì?

1. Tại sao `var` là **suy luận kiểu tại compile time**, không phải kiểu động như biến trong JavaScript.
2. Tại sao sau khi suy luận, kiểu local variable **không tự thay đổi theo các lần gán**.
3. Vì sao những lệnh bytecode như `istore`, `aload`, `invokevirtual` và method descriptors vẫn gắn với kiểu.
4. Tại sao `javap` không cho thấy một “runtime type `var`”.
5. Khi nào `var` và một khai báo tường minh cho ra bytecode tương đương về thao tác.
6. Khi nào **kiểu suy luận cụ thể hơn một kiểu cha được ghi tường minh**, làm overload resolution và bytecode của lời gọi khác nhau.
7. Generic type inference diễn ra trước **type erasure**, còn JVM sử dụng erased types để thực thi.
8. Vai trò của compiler và bytecode verifier khác nhau ra sao.
9. Cách quan sát bằng `javac -g`, `javap -c`, `javap -v`, `javap -s`.
10. Những giới hạn của `var` và các lỗi biên dịch thường gặp.

**Kết luận ngay từ đầu:** `var` giúp viết source code ngắn hơn khi kiểu có thể được compiler suy ra. **Java vẫn là ngôn ngữ có kiểu tĩnh**. Bytecode và JVM không phải “đoán kiểu của `var` khi chương trình chạy”.

## 2. Hình dung luồng từ source code tới JVM

~~~text
Java source
    │
    ├── var count = 40;
    ├── var name = "Lan";
    └── var total = count + 2;
    │
    ▼
javac: Phân tích cú pháp và suy luận kiểu
    │
    ├── count : int
    ├── name  : String
    └── total : int
    │
    ▼
javac: Type checking / overload resolution
    │
    ├── Kiểm tra các phép gán, toán tử, method calls
    ├── Từ chối kiểu không tương thích
    └── Chọn đúng overload, thực hiện conversion cần thiết
    │
    ▼
Class file (.class)
    │
    ├── Bytecode instructions: iload, istore, iadd, aload, ...
    ├── Method/field descriptors: I, Ljava/lang/String;, ...
    ├── Constant pool và các symbolic references
    └── Metadata gỡ lỗi tùy chọn: local variable types/names
    │
    ▼
JVM: Load → Verify → Link → Execute / JIT
    │
    ├── Verifier kiểm tra type safety của bytecode
    ├── Interpreter/JIT thực thi các instructions
    └── Object ở runtime vẫn có lớp thật của nó
~~~

Quan sát quan trọng:
- **Suy luận kiểu của `var` thuộc về Java compiler**, không phải trình bytecode verifier.
- **Verifier kiểm tra bytecode có hợp lệ về kiểu hay không**, chứ không lặp lại cú pháp nguồn hay cố suy ra `var`.
- Local variables được lưu trong **slots** của frame; bytecode có các lệnh tương ứng loại giá trị.
- Runtime object có class identity thật; điều đó **không làm kiểu khai báo của biến local trở thành dynamic**.

**Hai nghĩa của từ “type inference” cần tách biệt:** JEP 286 là suy luận **kiểu Java ở cấp source**. JVM Specification đôi khi cũng nói về **type inference trong thuật toán verification cũ hoặc các quy tắc phân tích frame**; đó là hoạt động kiểm chứng file `.class`, **không phải tính năng `var` của Java 10**.

## 3. `var` thực sự là gì trong ngôn ngữ Java?

`var` là một **reserved type name**, không phải keyword thông thường. Nó được dùng thay vị trí viết kiểu trong những khai báo local variable hợp lệ. Trình biên dịch dùng kiểu của **initializer** để xác định một kiểu tĩnh.

Ví dụ:

~~~java
var number = 10;                         // int
var big = 10L;                           // long
var ready = true;                        // boolean
var title = "Java";                      // String
var value = Integer.valueOf(7);          // Integer
var items = new java.util.ArrayList<String>();
                                        // ArrayList<String>
~~~

Khi đã xác định được kiểu:
- `number` là `int` trong suốt phạm vi sống của biến local.
- `title` có kiểu tĩnh `String`, kể cả khi gán một `String` khác.
- `value` có kiểu tĩnh `Integer`, không tự “nới” thành `Object` sau một phép gán.
- `items` có kiểu tĩnh `ArrayList<String>`; compiler kiểm tra `add` và `get` theo generics.

Không được suy luận từ các lần gán về sau. Ví dụ:

~~~java
var count = 5;    // int
count = 6;        // hợp lệ
// count = "six"; // lỗi biên dịch: String không thể gán cho int
~~~

Đây là đặc điểm **kiểu tĩnh**. Giá trị của biến có thể thay đổi, **kiểu tĩnh không đổi**.

### `var` không tương đương với `Object`

~~~java
var text = "hello";   // static type: String
Object general = "hello";
~~~

Với `text`, compiler cho phép gọi các phương thức của `String` (ví dụ `length()`). Với `general`, compiler chỉ nhìn thấy những members có sẵn ở `Object` trừ khi bạn thực hiện cast hoặc dùng cơ chế khác.

~~~java
System.out.println(text.length()); // hợp lệ
// general.length();               // lỗi: Object không có length()
~~~

Một chương trình có thể chứa object `String` ở cả hai biến, nhưng **quy tắc truy cập members theo static type** khác nhau.

## 4. Từ kiểu Java tới bytecode: primitive và reference

JVM có hệ thống instruction set theo loại giá trị. Những lệnh thường thấy:

| Giá trị Java | Ví dụ source | Bytecode thường gặp | Diễn giải |
| --- | --- | --- | --- |
| `int` | `var x = 1;` | `istore`, `iload`, `iadd` | Integer arithmetic/local slots |
| `long` | `var x = 1L;` | `lstore`, `lload`, `ladd` | 64-bit long |
| `float` | `var x = 1.0f;` | `fstore`, `fload`, `fadd` | Float |
| `double` | `var x = 1.0;` | `dstore`, `dload`, `dadd` | Double |
| Reference | `var s = "hi";` | `astore`, `aload` | Lưu/tải tham chiếu |
| `boolean` | `var ok = true;` | Thường có các lệnh nhóm `i` | Boolean dùng cơ chế int ở nhiều thao tác VM |

Đây là **minh họa nhóm lệnh**, không có bảo đảm compiler luôn sinh đúng cùng một chuỗi instruction cho từng dòng Java: compiler có thể constant fold, tối ưu thứ tự, dùng opcode rút gọn và lựa chọn các instructions khác tùy biểu thức.

Với primitive `byte`, `short`, `char`, `boolean`, JVM không có bộ số học/local-variable instructions hoàn toàn tách biệt cho từng kiểu nguồn; nhiều thao tác sử dụng các instructions thuộc nhóm `int`. **“Có kiểu tĩnh” không có nghĩa luôn tồn tại đúng một opcode riêng cho từng kiểu Java source.**

### Type descriptors thông dụng

Trong class file, **descriptors** là các chuỗi biểu diễn kiểu:

| Java type | Descriptor |
| --- | --- |
| `int` | `I` |
| `boolean` | `Z` |
| `byte` | `B` |
| `short` | `S` |
| `char` | `C` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `Number` | `Ljava/lang/Number;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `void` (return type) | `V` |

Trong method descriptor:
- `(I)I` là phương thức nhận `int`, trả `int`.
- `(Ljava/lang/String;)V` nhận `String`, không trả giá trị.
- `(Ljava/lang/Number;)V` và `(Ljava/lang/Integer;)V` là **hai descriptors khác nhau**.

Không có descriptor `var`. Nó đã được compiler xử lý **trước khi** file `.class` được tạo.

## 5. Khi nào `var` và khai báo tường minh tương đương?

Hai hàm:

~~~java
static int withVar() {
    var count = 40;
    return count + 2;
}

static int withExplicit() {
    int count = 40;
    return count + 2;
}
~~~

Trong cả hai:
- `count` có kiểu `int`.
- `return` có kiểu `int`.
- Compiler có thể sinh chuỗi thao tác tương đương về ngữ nghĩa: đưa hằng `40` lên stack, lưu vào int local slot, tải lại, cộng `2`, trả `int`.

Một kết quả `javap -c` **điển hình** cho phần thân một trong hai hàm:

~~~text
bipush        40
istore_0
iload_0
iconst_2
iadd
ireturn
~~~

**Các offsets có thể khác ở bản in đầy đủ, và ví dụ trên chỉ minh họa chuỗi lệnh, không phải một cam kết byte-for-byte của mọi compiler**. Các khác biệt như tên method, line numbers, metadata hoặc tối ưu có thể khiến **toàn bộ file class không giống hệt**, ngay cả khi thao tác runtime cho hai thân hàm tương đương.

Nói chính xác hơn: **khi kiểu tĩnh suy luận trùng kiểu tường minh và các biểu thức/semantics khác giữ nguyên**, việc sử dụng `var` không cần một cơ chế “dynamic variable” mới ở JVM. Bytecode được tạo cho những giá trị và lời gọi đã được compiler kiểm tra kiểu.

## 6. Khi nào `var` làm kiểu tĩnh cụ thể hơn một khai báo khác?

Đừng hiểu “`var` có thể thay kiểu tường minh” là **mọi kiểu tường minh đều tương đương**.

Ví dụ:

~~~java
Number wide = Integer.valueOf(7);
var precise = Integer.valueOf(7);
~~~

Kiểu tĩnh:
- `wide`: `Number` do lập trình viên ghi rõ.
- `precise`: `Integer` do compiler suy ra từ `Integer.valueOf(7)`.

Giả sử có hai overload:

~~~java
static void choose(Number value)  { /* ... */ }
static void choose(Integer value) { /* ... */ }
~~~

Khi gọi:

~~~java
choose(wide);    // compile-time chọn choose(Number)
choose(precise); // compile-time chọn choose(Integer)
~~~

**Tại sao?** Java giải quyết overload dựa trên **kiểu tĩnh của biểu thức tại call site**, không đợi đến runtime xem object là lớp gì rồi mới chọn overload.

Bytecode của lời gọi có thể tham chiếu các method descriptors khác nhau:

~~~text
choose:(Ljava/lang/Number;)V
choose:(Ljava/lang/Integer;)V
~~~

Như vậy, **việc thay một kiểu tường minh là kiểu cha bằng `var` có thể làm bytecode của lời gọi khác đi** — vì **kiểu suy luận đã thay đổi overload resolution ở thời điểm biên dịch**, chứ không phải vì `var` gây dynamic dispatch.

### Tách overload với override

- **Overload:** compiler chọn method signature dựa trên static types, ví dụ `choose(Number)` và `choose(Integer)`.
- **Override/virtual dispatch:** với instance methods có thể override, JVM có thể chọn implementation theo runtime class của receiver, nhưng **compile-time vẫn kiểm tra và cố định method signature được gọi**.

`var` **không thay đổi** quy tắc override. Khi gặp `invokevirtual` hoặc `invokeinterface`, runtime polymorphism vẫn hoạt động như trước Java 10.

## 7. Chương trình Java 17+ hoàn chỉnh để quan sát kết quả

Tạo file **VarStaticBytecodeDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarStaticBytecodeDemo {

    static int withVar() {
        var count = 40;
        return count + 2;
    }

    static int withExplicit() {
        int count = 40;
        return count + 2;
    }

    static void choose(Number value) {
        System.out.println("choose=Number");
    }

    static void choose(Integer value) {
        System.out.println("choose=Integer");
    }

    public static void main(String[] args) {
        System.out.println("withVar=" + withVar());
        System.out.println("withExplicit=" + withExplicit());

        Number wide = Integer.valueOf(7);
        var precise = Integer.valueOf(7);

        choose(wide);
        choose(precise);

        var names = new ArrayList<String>();
        names.add("Lan");

        List<String> general = new ArrayList<>();
        general.add("An");

        System.out.println(
                "names=" + names.get(0)
                + ", general=" + general.get(0));

        var flag = true;
        System.out.println("flag=" + flag);
    }
}
~~~

Tất cả cú pháp và API của chương trình đã có trong **Java 10**. Nếu đang có JDK 17+ và muốn sinh bytecode tương thích Java 10:

~~~bash
javac --release 10 -g VarStaticBytecodeDemo.java
java VarStaticBytecodeDemo
~~~

**Stdout chính xác:**

~~~text
withVar=42
withExplicit=42
choose=Number
choose=Integer
names=Lan, general=An
flag=true
~~~

**Giải thích:**
1. `withVar` và `withExplicit` đều cộng `int`, cho `42`.
2. `choose(wide)` gọi overload `Number`, dù object được giữ bên trong là `Integer`.
3. `choose(precise)` gọi overload `Integer`, do compiler suy ra kiểu `Integer` từ initializer.
4. `names` có kiểu tĩnh `ArrayList<String>`; `general` có kiểu tĩnh `List<String>`. Cả hai chứa `String`.
5. `flag` có kiểu `boolean`, không phải kiểu runtime động.

**Tại sao dùng `--release 10`?** Khi chạy trên compiler JDK 17+ có hỗ trợ target đó, `--release 10` giúp kiểm tra Java 10 language rules/API và sinh class file tương thích mức Java 10. File class Java 10 dùng **major version 54**. Cần nhớ: lệnh này không phải cách kiểm thử mọi hành vi runtime của JDK 10, chỉ là thiết lập compile target.

Nếu chỉ quan tâm biên dịch/chạy trên JDK 17+, bạn cũng có thể dùng:

~~~bash
javac -g VarStaticBytecodeDemo.java
java VarStaticBytecodeDemo
~~~

Khi dùng lệnh thứ hai, **class-file version** theo target mặc định của compiler hiện tại, nhưng ý nghĩa `var` vẫn là suy luận kiểu tĩnh.

## 8. Dùng `javap` để kiểm chứng bytecode

`javap` là công cụ đọc cấu trúc của file `.class`; nó **không chạy chương trình** để dò kiểu. Sau khi compile:

~~~bash
javap -c -p VarStaticBytecodeDemo
~~~

Tùy chọn:
- `-c`: disassemble `Code` attribute thành các instructions.
- `-p`: hiển thị tất cả members, kể cả private (ở đây tiện cho tính nhất quán).
- `-l`: hiển thị line và local variable tables nếu tồn tại.
- `-s`: hiển thị internal type signatures/descriptors.
- `-v`: hiển thị thông tin chi tiết class-file attributes và constant pool.

Thử thêm:

~~~bash
javap -c -l -p VarStaticBytecodeDemo
javap -s -p VarStaticBytecodeDemo
javap -v -p VarStaticBytecodeDemo
~~~

### Kiểm tra hai phương thức `withVar` và `withExplicit`

Tìm các methods:

~~~text
static int withVar();
static int withExplicit();
~~~

Bạn có thể thấy những instructions thuộc nhóm sau:

~~~text
bipush 40
istore_0
iload_0
iconst_2
iadd
ireturn
~~~

**Ý nghĩa:**
- `bipush 40`: đưa số nguyên 40 lên operand stack.
- `istore_0`: lưu giá trị int vào local slot số 0.
- `iload_0`: tải từ slot 0.
- `iconst_2`: đưa số 2 vào operand stack.
- `iadd`: cộng hai int.
- `ireturn`: trả một giá trị int.

Trong bytecode thực, `istore_0` không mang chuỗi `count` hoặc `var`; **slot index** giúp định vị giá trị trong method frame. Nếu có debug info, `LocalVariableTable` mới có thể liên hệ slot, phạm vi bytecode, tên `count` và descriptor `I`.

### Kiểm tra hai overload

Tìm những tham chiếu method:

~~~text
choose:(Ljava/lang/Number;)V
choose:(Ljava/lang/Integer;)V
~~~

Trong `main`, các lệnh gọi `invokestatic` cho overload `choose` có thể trỏ tới **hai method descriptors** này. Thông tin này chứng minh compiler đã **chọn signatures ở compile time**.

**Không có một opcode `var` trong class file.** Điều mà JVM biết là kiểu tham số/method descriptors, instruction constraints, operand stacks và local slots.

### Một lệnh `javap` không phải bằng chứng benchmark

Không thể từ việc hai hàm dùng các instruction gần giống nhau suy ra performance luôn bằng nhau trong mọi tình huống. JIT, constant folding, inlining, runtime profiling, CPU và workload có thể ảnh hưởng kết quả. Nhưng `var` tự nó **không thêm cơ chế dynamic typing bắt buộc tại runtime**.

## 9. LocalVariableTable: kiểu ở bytecode có thể nhìn thấy thế nào?

Khi biên dịch với `-g`:

~~~bash
javac --release 10 -g VarStaticBytecodeDemo.java
~~~

compiler có thể phát ra các **thuộc tính debug tùy chọn**, trong đó có `LocalVariableTable`.

Một minh họa ý nghĩa của bảng (vị trí/length phụ thuộc output compiler):

~~~text
LocalVariableTable:
  Start  Length  Slot  Name   Signature
      3       4     0 count  I
~~~

Ở đây:
- **Start/Length:** khoảng instruction offsets mà biến local được gắn với slot.
- **Slot:** chỉ số local variable slot.
- **Name:** tên biến nguồn `count`.
- **Signature** trong cách hiển thị của `LocalVariableTable`: **JVM descriptor**, ở đây `I` = int.

**Bảng này không lưu một kiểu `var` cho JVM.** Nếu tên biến nguồn được giữ, đó là metadata gỡ lỗi; không phải thành phần quyết định dynamic type của local variable.

### Nếu không biên dịch với thông tin local variables?

Thử:

~~~bash
javac --release 10 -g:none VarStaticBytecodeDemo.java
javap -l -p VarStaticBytecodeDemo
java VarStaticBytecodeDemo
~~~

Với `-g:none`, các debug tables như `LocalVariableTable` có thể không được ghi, nhưng chương trình **vẫn chạy đúng như trước**.

Đây là bằng chứng quan trọng:
- `LocalVariableTable` là **optional debug information**.
- JVM không cần phải đọc tên biến nguồn `count` để thực hiện các lệnh `iload/istore`.
- Bytecode verifier có nguồn thông tin kiểu từ **instructions, descriptors và verification frames** theo JVMS, không phụ thuộc LocalVariableTable phải có.

**Cảnh báo khi thực hành:** Lệnh `javac -g:none` sẽ biên dịch lại file `.class` ở cùng vị trí. Nếu muốn xem cả hai variants đồng thời, hãy compile sang hai thư mục output riêng thay vì ghi đè vào cùng class file.

## 10. LocalVariableTypeTable và generic erasure

Generic types là ví dụ dễ gây nhầm nhất. Với:

~~~java
var names = new java.util.ArrayList<String>();
~~~

Compiler suy ra **`ArrayList<String>`**, không phải `ArrayList<Object>`. Nó kiểm tra:

~~~java
names.add("Lan");   // hợp lệ
// names.add(123);  // lỗi biên dịch: Integer không phù hợp String
~~~

Tại JVM class-file level, kiểu reference **erasure** thông thường là:

~~~text
Ljava/util/ArrayList;
~~~

Trong metadata gỡ lỗi, compiler có thể ghi thông tin generic của local variable trong **`LocalVariableTypeTable`**:

~~~text
Ljava/util/ArrayList<Ljava/lang/String;>;
~~~

Hai thuộc tính cần phân biệt:

| Thuộc tính | Nội dung | Có bắt buộc trong class file? |
| --- | --- | --- |
| `LocalVariableTable` | Slot, scope, name và erased descriptor, ví dụ `Ljava/util/ArrayList;` | **Không** |
| `LocalVariableTypeTable` | Generic signature của local dùng parameterized type hoặc type variables | **Không** |
| `Signature` | Generic signature cho những cấu trúc class/member mà JVM spec định nghĩa | Không có nghĩa mọi generic local phải lưu ở đó |
| `StackMapTable` | Verification types/frame states ở các điểm control-flow cần thiết theo phiên bản bytecode | Không phải bảng “tên var”; có thể vắng ở method tuyến tính |

Để xem:

~~~bash
javac --release 10 -g VarStaticBytecodeDemo.java
javap -v -p VarStaticBytecodeDemo
~~~

**Không khẳng định mọi compiler hoặc mọi local variable sẽ đều có một `LocalVariableTypeTable`.** Nó tùy thuộc debug information, kiểu generic và compiler. Khi dữ liệu generic không còn trong class file, chương trình vẫn có thể chạy; trình biên dịch đã thực hiện các kiểm tra source-level từ trước.

### Tại sao Java generics vẫn có kiểu tĩnh dù bị xóa ở bytecode?

- **Compiler:** kiểm tra `ArrayList<String>` chỉ thêm/đọc `String` đúng quy tắc Java.
- **Class file/runtime:** nhiều thông tin generic được **erase** thành raw reference type và casts cần thiết.
- **JVM:** kiểm tra tính an toàn của bytecode references và những type constraints còn được biểu diễn; nó không kiểm tra lại mọi tham số `<String>` như một generic runtime type parameter.

Ví dụ lời gọi `names.get(0)` có thể đi kèm **`checkcast java/lang/String`** trước khi dùng giá trị như `String` khi loại truy cập yêu cầu, bởi `List.get` sau erasure trả `Object`.

**Không suy ra generics là dynamic typing.** Generic constraints phần lớn được compiler đảm bảo ở source level; đó là một kiểu kiểm tra tĩnh, dù runtime generic arguments có thể bị xóa.

## 11. `var` với diamond `<>` ảnh hưởng suy luận kiểu như thế nào?

So sánh:

~~~java
java.util.List<String> strings =
        new java.util.ArrayList<>();

var objects = new java.util.ArrayList<>();
~~~

Ở khai báo đầu, **target type** ở phía trái cung cấp ngữ cảnh giúp diamond `<>` suy ra `String`. Biến có kiểu tĩnh **`List<String>`**.

Ở khai báo thứ hai, không có target type tường minh cho initializer theo cách tương tự. Biểu thức `new ArrayList<>()` thường được suy ra thành **`ArrayList<Object>`** và `objects` có static type ấy.

Do đó:

~~~java
objects.add("Lan"); // hợp lệ
objects.add(123);   // hợp lệ vì element type là Object
~~~

Nhưng đối với `strings`:

~~~java
strings.add("Lan"); // hợp lệ
// strings.add(123); // lỗi biên dịch
~~~

**Kết luận:** `var` không “làm mất kiểu” một cách động. Nó khiến Java áp dụng quy tắc suy luận kiểu ở initializer **không có một khai báo kiểu tường minh làm target** trong tình huống này. Kiểu tĩnh cuối cùng có thể khác so với khai báo có target typing.

Nếu muốn `var` nhưng vẫn giữ `String`, viết:

~~~java
var strings2 = new java.util.ArrayList<String>();
~~~

Lúc đó compiler suy ra **`ArrayList<String>`**.

### Bytecode có khác?

Giữa `ArrayList<String>` và `ArrayList<Object>` thường vẫn dùng **reference descriptor `Ljava/util/ArrayList;`** cho local và cùng class `java.util.ArrayList` ở runtime. Sự khác biệt generic chủ yếu là **compile-time constraints** và có thể ảnh hưởng casts/method calls hoặc metadata debug khi mã nguồn sử dụng các giá trị.

Không dùng một vài instruction giống nhau để kết luận rằng hai khai báo **có cùng static generic type**.

## 12. `var`, subtype, method dispatch và reflection

### 12.1. Static type quyết định members được gọi

~~~java
var list = new java.util.ArrayList<String>();
java.util.List<String> asInterface =
        new java.util.ArrayList<>();
~~~

- `list` có static type `ArrayList<String>`.
- `asInterface` có static type `List<String>`.

Vì vậy, compiler cho phép `list.ensureCapacity(20)` nhưng không cho `asInterface.ensureCapacity(20)` (vì `List` không khai báo method đó).

Bytecode có thể sử dụng các **method references khác nhau** cho một số lời gọi, tùy loại receiver tĩnh/method đã chọn. **Không phải `var` tự sinh dynamic dispatch mới.**

### 12.2. Runtime type không phải static type

~~~java
Number number = Integer.valueOf(7);
~~~

- Static type của `number` là `Number`.
- Runtime class của object có thể là `Integer`.
- Java vẫn có virtual method dispatch theo quy tắc override thông thường.
- Overload signatures được chọn ở compile time.

`var` chỉ ảnh hưởng cách compiler xác định static type ban đầu, không thay đổi bản chất đa hình của Java.

### 12.3. Java Reflection không liệt kê trực tiếp local variables như fields

`Class.getDeclaredFields()` trả về các **fields**, không phải local variables trong body của method. Local variable names và descriptors có thể nằm trong **optional debug attributes**, cần bytecode tools/debugger để xem.

Vì thế:
- Không có một “`var` runtime object” để `Class` reflection đọc.
- Không phải mọi thông tin source-level về locals vẫn được giữ lại.
- Một debugger có thể hiển thị kiểu local nhờ debug metadata và JVM state, nhưng **điều này khác với ngôn ngữ có biến động kiểu**.

## 13. Bytecode verifier kiểm chứng điều gì?

Khi load/link class, JVM thực hiện **verification** theo JVMS. Mục đích là xác nhận bytecode đáp ứng các ràng buộc loại giá trị, control flow, stack/local variable usage và những điều kiện an toàn khác.

Một số nội dung:
- `iadd` nhận các giá trị thích hợp cho integer arithmetic.
- `iload` và `istore` hoạt động với local slots có giá trị thuộc loại thích hợp.
- `aload` và `astore` dùng reference values tương ứng.
- Method invocation phải tuân thủ method descriptors và stack operands phù hợp.
- Branches/exception handlers phải hợp lệ về stack/frame states.
- Quy trình sử dụng **StackMapTable** và verification type states trong class-file versions hiện đại theo quy định JVMS.

**Verifier không xem lại source code để hỏi “biến này dùng `var` hay `int`”.** Nếu class file hợp lệ, verifier phân tích những constraints được **thể hiện trong class file**.

### `StackMapTable` không giống `LocalVariableTable`

- **LocalVariableTable:** metadata gỡ lỗi; có thể chứa tên biến nguồn và descriptor. Có thể bỏ đi mà JVM vẫn chạy.
- **LocalVariableTypeTable:** metadata về generic signatures của locals. Cũng tùy chọn.
- **StackMapTable:** thông tin verification type frames cho những điểm trong bytecode theo JVMS; phục vụ kiểm chứng control flow và operand/local types, **không chứa từ khóa `var`**.

Một method thẳng không có branches có thể **không hiển thị StackMapTable rõ ràng** trong `javap -v`; điều đó không chứng minh JVM bỏ qua type checking. Đừng kết luận sai chỉ vì không thấy một attribute trong ví dụ rất đơn giản.

### Runtime object vẫn có loại thật

Verifier kiểm tra instruction-level type safety; khi Java thực hiện cast hoặc truy cập array, JVM cũng có những **runtime checks** phù hợp. Đây là đặc điểm Java từ lâu, **không phải cái giá phát sinh mới do `var`**.

## 14. Các giới hạn hợp lệ của `var` trong Java 10

`var` chỉ dùng được nơi compiler có thể xác định kiểu local variable theo quy tắc ngôn ngữ.

### Những dạng hợp lệ

~~~java
var n = 10;  // local có initializer

for (var i = 0; i < 3; i++) {
    System.out.println(i);
}

for (var word : java.util.List.of("a", "b")) {
    System.out.println(word);
}

try (var reader = new java.io.StringReader("abc")) {
    System.out.println(reader.read());
}
~~~

Đây là các **đoạn minh họa cú pháp**, không phải một chương trình độc lập chứa đủ class/main/imports. Tất cả cấu trúc được nêu đều hợp lệ trên Java 10 trong ngữ cảnh phương thức cho phép.

### Những dạng không hợp lệ

~~~java
// var x;              // không có initializer
// var x = null;       // không suy ra được kiểu từ null literal
// var x = () -> 1;    // lambda cần target type thích hợp
// var x = String::new;// method reference cần target type
// var x = {1, 2};     // array initializer trần không dùng kiểu này
// var first = 1, second = 2; // không khai báo nhiều biến dạng này
~~~

Đối với lambda:

~~~java
java.util.function.Supplier<Integer> supplier = () -> 1;
~~~

**Supplier<Integer>** cung cấp target functional interface. Không có target type, biểu thức lambda không đủ để compiler suy ra kiểu `var` của local declaration.

### Field và method parameter?

~~~java
class Example {
    // var field = 1; // không hợp lệ: var không dùng cho field

    // void call(var x) {} // không hợp lệ: var không dùng
                           // cho method parameter thông thường
}
~~~

**Cập nhật còn áp dụng:** Java 11 mở rộng việc sử dụng `var` cho **lambda parameters** theo những điều kiện nhất định. Điều này **không làm `var` trở thành kiểu động** và **không cho phép** dùng `var` tùy ý cho fields/method parameters bình thường. Bài này tập trung hành vi local-variable inference của Java 10.

### Không dùng `var` chỉ để ẩn kiểu cần thiết cho người đọc

Ví dụ:

~~~java
var result = process();
~~~

Nếu tên `process()` không nói rõ trả kiểu gì, code có thể khó đọc hơn:

~~~java
OrderSummary result = process();
~~~

Quyết định sử dụng `var` nên dựa trên **khả năng hiểu kiểu và ý nghĩa từ initializer**, không phải cố lược bỏ kiểu trong mọi tình huống.

## 15. Java 10 với `var`: những điều không đổi ở runtime

| Đặc điểm | Với khai báo tường minh | Với `var` |
| --- | --- | --- |
| Suy luận/viết kiểu | Người lập trình nêu kiểu tĩnh | Compiler xác định kiểu tĩnh từ initializer |
| Kiểm tra phép gán | Compile time | Compile time |
| Overload resolution | Static types tại call site | Static types đã được suy ra tại call site |
| Virtual dispatch khi override | Theo runtime receiver type | Không đổi |
| Generic erasure | Có | Không đổi |
| Bytecode verifier | Kiểm tra class file | Kiểm tra class file như bình thường |
| Runtime reflection của locals | Không được Java Reflection cung cấp như fields | Không có cơ chế riêng |
| Bytecode opcode `var` | Không tồn tại | Không tồn tại |
| Runtime variable tự đổi Java static type | Không | Không |
| Optional local debug metadata | Tùy compiler flags | Tương tự |

**Đính chính dễ bỏ sót:** Không thể khẳng định “đổi mọi khai báo thành `var` thì bytecode luôn giống hệt” vì **kiểu suy luận có thể khác kiểu khai báo tường minh trước đó**, từ đó method overload, target typing và inserted casts có thể khác. Chỉ khi **điều kiện type và biểu thức tương đương**, sự thay đổi chủ yếu là ở cách viết source code.

## 16. Thử nghiệm kiểm chứng từng bước

### Bước A — Kiểm tra chương trình chạy đúng

~~~bash
javac --release 10 -g VarStaticBytecodeDemo.java
java VarStaticBytecodeDemo
~~~

So stdout với mẫu ở mục 7. Nếu có lỗi khi `--release 10`, kiểm tra **JDK compiler** đang dùng; một số bản JDK mới về sau có thể không còn hỗ trợ mọi `--release` rất cũ. Khi đó có thể dùng một build JDK phù hợp hoặc compile mặc định trên JDK hiện đại để vẫn kiểm chứng hành vi ngôn ngữ `var`.

### Bước B — Kiểm tra lệnh primitive

~~~bash
javap -c -p VarStaticBytecodeDemo
~~~

Tìm `withVar` và `withExplicit`: cả hai thao tác với `int`, không có `var` instruction.

### Bước C — Kiểm tra method descriptor của overload

~~~bash
javap -s -p VarStaticBytecodeDemo
javap -c -p VarStaticBytecodeDemo
~~~

Tìm `choose:(Ljava/lang/Number;)V` và `choose:(Ljava/lang/Integer;)V`. Lời gọi được compiler quyết định dựa trên static type.

### Bước D — Xem local debug types

~~~bash
javap -v -p VarStaticBytecodeDemo
~~~

Tìm `LocalVariableTable` với tên như `count`, `wide`, `precise`, và những descriptors như `I`, `Ljava/lang/Number;`, `Ljava/lang/Integer;`. Với generic locals, tìm `LocalVariableTypeTable` nếu compiler đã phát ra thông tin cần thiết.

### Bước E — Loại debug info nhưng giữ hành vi

~~~bash
javac --release 10 -g:none VarStaticBytecodeDemo.java
javap -l -p VarStaticBytecodeDemo
java VarStaticBytecodeDemo
~~~

Chương trình vẫn có stdout như mục 7, dù không còn local-variable debug metadata. **Verifier không cần tên biến nguồn để kiểm tra bytecode**.

### Bước F — Tạo lỗi compile để chứng minh static type

Trong một file thử nghiệm riêng:

~~~java
class IncompatibleVarAssignment {
    void run() {
        var count = 10;
        count = "ten"; // compile-time error
    }
}
~~~

Với compiler hỗ trợ `var`:

~~~bash
javac IncompatibleVarAssignment.java
~~~

Lệnh này **dự kiến thất bại biên dịch**; thông điệp chính xác phụ thuộc JDK/compiler nhưng nguyên nhân là **không thể gán String cho int**. JVM chưa chạy chương trình, nên đây là bằng chứng trực tiếp rằng quy tắc static type áp dụng **trước runtime**.

## 17. Một số bẫy khi đọc `javap`

**Bẫy 1 — Không thấy `var` trong bytecode nên nghĩ compiler bỏ qua kiểu.**  
Sai: compiler đã suy luận và kiểm tra kiểu rồi mã hóa thao tác/loại tham chiếu phù hợp.

**Bẫy 2 — Không thấy LocalVariableTable nên tưởng chương trình “mất kiểu”.**  
Sai: đây là optional debug attribute, không phải bắt buộc cho execution hoặc verification.

**Bẫy 3 — Có LocalVariableTypeTable thì JVM thực thi full generics.**  
Sai: generic local signatures phục vụ metadata/debug; generic erasure vẫn áp dụng ở runtime.

**Bẫy 4 — Hai thân hàm giống instructions nghĩa toàn bộ .class files giống byte-for-byte.**  
Sai: method names, constant-pool entries, line tables hoặc metadata có thể khác.

**Bẫy 5 — `Number x = Integer.valueOf(7)` giống hệt `var x = Integer.valueOf(7)` trong mọi lời gọi.**  
Sai: static types khác; overload selection có thể khác.

**Bẫy 6 — JVM dùng `var` để chọn overload theo runtime class.**  
Sai: overload resolution là compile-time. Override dispatch là câu chuyện khác.

**Bẫy 7 — Biến `var` có thể đổi loại sau phép gán.**  
Sai: kiểu tĩnh của local không thay đổi.

**Bẫy 8 — `var x = null` hợp lệ vì null là reference.**  
Sai: null literal không cung cấp một kiểu suy luận phù hợp cho khai báo đó.

**Bẫy 9 — `var` tương đương `Object`.**  
Sai: compiler thường suy ra một kiểu cụ thể hơn.

**Bẫy 10 — `var x = new ArrayList<>()` chắc chắn có `String` vì dự định thêm String sau.**  
Sai: suy luận không dùng các câu lệnh gán/thêm về sau để quyết định type của initializer; thường suy ra `ArrayList<Object>`.

**Bẫy 11 — Cứ compile mặc định trên JDK 25 là class file Java 10.**  
Sai: compile target mặc định thường theo JDK hiện tại; dùng `--release 10` nếu compiler hỗ trợ và cần target Java 10.

**Bẫy 12 — `StackMapTable` chứa tên biến và `var`.**  
Sai: StackMapTable phục vụ verification type states, không phải local variable debug names.

**Bẫy 13 — Dựa vào một `javap -c` để benchmark tốc độ.**  
Sai: cần đo runtime với JIT, workload và môi trường thực.

**Bẫy 14 — Khác kết quả `javap` giữa compiler versions nghĩa `var` không còn static.**  
Sai: compiler có thể thay cách sinh bytecode; ngữ nghĩa static typing của Java không đổi.

## 18. Checklist kiểm tra một bài `var` và bytecode

1. Xác nhận source được compile với **Java 10+ language rules**.
2. Kiểm tra initializer có đủ thông tin suy luận kiểu.
3. Xác định **inferred static type** của từng local.
4. So với khai báo tường minh: **có cùng static type hay là supertype/interface khác?**
5. Kiểm tra compiler chọn overload nào.
6. Xem `javap -c` để hiểu load/store, arithmetic và invocations.
7. Xem `javap -s` để đối chiếu method descriptors.
8. Dùng `javac -g` khi cần xem local-variable debug metadata.
9. Phân biệt LocalVariableTable và LocalVariableTypeTable.
10. Không nhầm generic signatures với runtime generic type enforcement.
11. Không đồng nhất optional debug metadata với yêu cầu bytecode verification.
12. Kiểm tra compile-time errors bằng một ví dụ cố ý sai.
13. Đối chiếu stdout của chương trình runnable.
14. Không khẳng định class files byte-identical chỉ từ tương đồng semantics.
15. Tách overload resolution khỏi virtual method overriding.
16. Dùng `--release` để xác định target level khi phiên bản compiler hỗ trợ.
17. Không suy ra chi phí runtime mới chỉ vì source dùng `var`.
18. Giữ code đọc được: dùng `var` khi kiểu thể hiện rõ qua initializer.

## 19. Câu hỏi tự kiểm tra

**1. `var` có tạo dynamic typing trong Java không?**  
Không. Inferred type được quyết định lúc compile và trở thành static type của local variable.

**2. `var n = 10;` tương đương static type nào?**  
`int`.

**3. Sau `var n = 10;`, có thể gán `n = "ten";` không?**  
Không. Compiler báo type mismatch, JVM chưa cần chạy.

**4. Có opcode `var` trong JVM không?**  
Không. JVM thực hiện instructions thuộc các loại giá trị như `iload`, `istore`, `aload`, `astore`.

**5. Vì sao `Number x = Integer.valueOf(7)` khác `var x = Integer.valueOf(7)`?**  
Static type đầu là `Number`, kiểu suy luận sau là `Integer`; overload resolution có thể khác.

**6. `LocalVariableTable` có phải thành phần bắt buộc để JVM chạy không?**  
Không. Nó là optional debug attribute.

**7. `LocalVariableTypeTable` lưu loại thông tin gì?**  
Generic signature của một số local variables có parameterized/type-variable types, khi compiler phát ra attribute đó.

**8. `StackMapTable` dùng cho mục đích gì?**  
Cung cấp verification type-frame information theo JVMS, không lưu từ khóa source `var`.

**9. Vì sao Java generic type vẫn là static dù runtime có erasure?**  
Compiler kiểm tra constraints ở source level; runtime chủ yếu dùng erased types và các casts/checks phù hợp.

**10. `var list = new ArrayList<>()` luôn được suy ra `ArrayList<String>` không?**  
Không. Nếu không có ngữ cảnh/constructor argument bổ sung, thường là `ArrayList<Object>`.

**11. `var` có dùng cho fields hoặc method parameters thông thường không?**  
Không. Java 11 có một cơ chế riêng dùng `var` trong lambda parameters, không thay quy tắc này.

**12. `javap -c` cho biết gì?**  
Disassembly các bytecode instructions từ class file.

**13. `javap -s` hỗ trợ điều gì?**  
Xem descriptors/signatures của members như method parameters/return types.

**14. `javac -g:none` có khiến `var` bị dynamic hóa không?**  
Không. Nó bỏ debug metadata, không thay Java static typing.

**15. JVM verifier có suy luận `var` như javac không?**  
Không. Nó kiểm tra class-file instructions, frame states và type constraints; không đọc lại cú pháp nguồn.

**16. Hai phương thức dùng `var int` và `int` có luôn sinh class file giống hệt từng byte không?**  
Không thể bảo đảm. Chỉ có thể nói thao tác runtime thường tương đương khi inferred type và biểu thức trùng nhau.

**17. Có thể so sánh bytecode mục tiêu Java 10 bằng JDK mới không?**  
Có, nếu `javac` hỗ trợ `--release 10`; sau đó kiểm tra file class và `major version` tương ứng.

**18. Cách tốt nhất để chứng minh `var` không đổi kiểu khi gán là gì?**  
Tạo một ví dụ gán sai static type và quan sát **lỗi biên dịch**, không cần đợi runtime.

## 20. Tổng kết

- **Java 10 / JEP 286** thêm `var` cho local-variable type inference, **không biến Java thành ngôn ngữ kiểu động**.
- Kiểu local được **suy ra từ initializer ở compile time**, sau đó dùng để kiểm tra phép gán, member access và overload resolution.
- Trong bytecode, JVM sử dụng **typed instructions, local slots và method/field descriptors**, không có `var` runtime instruction hay `var` class-file type.
- `var` và kiểu tường minh **trùng static type** thường dẫn đến thao tác bytecode tương đương; nhưng thay một **supertype tường minh** bằng kiểu suy luận cụ thể hơn có thể thay overload/call descriptors.
- **LocalVariableTable** và **LocalVariableTypeTable** là **optional debug metadata**; thiếu chúng không khiến bytecode mất type safety.
- **Generics** được kiểm tra ở compile time; những kiểu như `ArrayList<String>` thường bị erasure thành `ArrayList` ở runtime, có thể kèm casts và metadata.
- **Bytecode verifier** kiểm tra consistency của class file dựa trên instructions, descriptors và verification frames, **không suy luận lại source `var`**.
- Dùng `javac --release 10 -g`, `javap -c/-s/-v`, stdout chương trình và một ví dụ compile-time error để tự kiểm chứng.
- Khi viết code thật, chọn `var` nếu initializer làm kiểu rõ ràng; nếu static API type cần được cố định hay nâng mức trừu tượng, kiểu tường minh có thể thích hợp hơn.

**Tài liệu chính thức và hiện hành:**
- [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286).
- [OpenJDK Project Amber — Local Variable Type Inference FAQ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md).
- [Oracle Java SE 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html).
- [Dev.java — Using the Var Type Identifier](https://dev.java/learn/language-basics/using-var/).
- [Oracle Java Virtual Machine Specification, Java SE 25 — Chapter 2: Types, Frames, Operand Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html).
- [Oracle JVM Specification, Java SE 25 — Class File Descriptors, LocalVariableTable, LocalVariableTypeTable, StackMapTable và Bytecode Verification](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html).
- [Oracle JVM Specification, Java SE 25 — JVM Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html).
- [Oracle Java SE 25 — javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
- [Oracle Java SE 25 — javap command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html).
