# Line number, local variable metadata và giới hạn liên hệ bytecode với mã nguồn

Khi quan sát một tệp `.class` bằng `javap`, ta thường thấy những dòng như `LineNumberTable`, `LocalVariableTable` hoặc `MethodParameters` bên cạnh lệnh `iload`, `invokevirtual`, `return`. Các bảng này giúp debugger, stack trace và công cụ instrumentation **liên hệ mã thực thi với mã nguồn**, nhưng **không phải bản sao mã nguồn** và không tạo ánh xạ chính xác một-một giữa Java và bytecode.

Bài này tập trung vào ba câu hỏi thực hành:

1. Một **bytecode index (BCI)** ứng với dòng Java nào, và khi nào không thể xác định?
2. Một **local-variable slot** tại một khoảng bytecode có tên/kiểu gì, và metadata đó có nói được giá trị đang lưu không?
3. Tại sao instrumentation, compiler, tối ưu hóa hoặc việc lược bỏ thông tin debug khiến một công cụ không thể tái tạo nguyên vẹn mã Java ban đầu?

## 1. Bức tranh: từ source đến cấu trúc class file

```text
DebugMetadataDemo.java
       |
       | javac
       v
DebugMetadataDemo.class
  ClassFile
  ├─ constant_pool
  ├─ fields[]
  ├─ methods[]
  │    ├─ method_info (tên, descriptor, flags, ...)
  │    │    ├─ Code
  │    │    │    ├─ bytecode[] (mỗi lệnh bắt đầu tại một BCI)
  │    │    │    ├─ exception_table
  │    │    │    ├─ LineNumberTable       [tùy chọn]
  │    │    │    ├─ LocalVariableTable    [tùy chọn]
  │    │    │    ├─ LocalVariableTypeTable[tùy chọn]
  │    │    │    └─ StackMapTable         [khi định dạng yêu cầu]
  │    │    └─ MethodParameters          [tùy chọn, thuộc method_info]
  │    └─ ...
  └─ attributes[]
       ├─ SourceFile                    [tùy chọn]
       └─ SourceDebugExtension          [tùy chọn]
```

Các thuộc tính trên **khác vị trí và khác nhiệm vụ**. `LineNumberTable` và hai bảng local-variable là metadata của `Code` thuộc một phương thức cụ thể. `SourceFile` và `SourceDebugExtension` nằm ở cấp class. `MethodParameters` nằm ở cấp `method_info`, độc lập với `Code` và bảng local-variable.

Một phương thức `native` hay `abstract` không có `Code` nên cũng không có các bảng con của `Code`. Một class file có thể **không chứa metadata debug** mà bytecode vẫn chạy đúng, miễn cấu trúc/logic của lớp hợp lệ.

| Thuộc tính | Chứa thông tin gì? | Dùng vào việc gì? | **Không** bảo đảm điều gì? |
|---|---|---|---|
| `SourceFile` | Tên tệp nguồn, ví dụ `DebugMetadataDemo.java` | Gợi ý tệp nguồn cho debugger/stack trace | Không lưu đường dẫn tuyệt đối hay nội dung tệp |
| `SourceDebugExtension` | Dữ liệu mở rộng do trình biên dịch/công cụ gắn vào, có thể chứa bản đồ nguồn | Ánh xạ cho mã được sinh ra/từ ngôn ngữ khác nếu công cụ hiểu định dạng | Không phải lớp Java nào cũng có, không mặc định có SMAP |
| `LineNumberTable` | Các cặp `start_pc → line_number` | Định vị dòng mã nguồn tại các vị trí bytecode | Không cho cột, biểu thức, thứ tự source gốc hay ánh xạ một-một |
| `LocalVariableTable` | Khoảng BCI, tên, descriptor và slot của biến cục bộ | Hiển thị tên/kiểu biến trong phạm vi debug | Không chứa giá trị biến lúc chạy; không nhất thiết chứa mọi biến |
| `LocalVariableTypeTable` | Signature generic của một số biến cục bộ | Hiển thị `List<String>` thay vì chỉ `List` | Không phục hồi generic ở runtime hay thay đổi type erasure |
| `MethodParameters` | Metadata tham số hình thức của phương thức/constructor | Phục vụ reflection, ví dụ `Parameter.getName()` | Không mô tả biến cục bộ trong body |

## 2. `LineNumberTable`: BCI ↔ dòng nguồn

### 2.1. BCI là gì?

**Bytecode index** là **offset tính theo byte** từ đầu mảng `code[]` của **một phương thức**, không phải số thứ tự lệnh trong source, không phải địa chỉ máy CPU và không phải số dòng Java. Các opcode có thể dài khác nhau nên không phải mỗi lần tăng BCI một đơn vị là sang một instruction mới.

Ví dụ `javap -c` hiển thị:

```text
  0: iload_0
  1: iload_1
  2: iadd
  3: istore_2
  4: iload_2
  5: ireturn
```

Các số `0`–`5` là vị trí bytecode của phương thức cụ thể. Nếu sau này một công cụ chèn instruction, offset của các instruction theo sau có thể đổi; offset không phải danh tính bền vững của một biểu thức nguồn.

### 2.2. Cấu trúc và ý nghĩa của từng entry

Theo JVM Specification, một entry của `LineNumberTable` có:

```text
start_pc     = offset bắt đầu phần code gắn với một dòng nguồn
line_number  = số dòng trong source file tương ứng
```

Giả sử nguồn có:

```java
public static int add(int left, int right) {
    int total = left + right; // dòng 3, nếu khai báo class ở dòng 1
    return total;             // dòng 4
}
```

Một bản `javac` thông thường có thể tạo:

```text
LineNumberTable:
  line 3: 0
  line 4: 4
```

Nghĩa là bytecode từ vị trí `0` bắt đầu phần tương ứng dòng 3, còn từ `4` bắt đầu phần tương ứng dòng 4. **Không phải** `line 3` chỉ chiếm đúng một opcode, cũng không phải mọi instruction đều có entry riêng. Khi debugger chọn dòng cho một BCI, nó phải diễn giải các điểm đánh dấu và quy tắc của công cụ; đừng tự suy một ánh xạ hoàn hảo theo cú pháp Java.

### 2.3. Các giới hạn rất dễ nhầm

- **Một dòng có thể tạo nhiều instruction:** `int total = left + right;` dẫn tới tải hai biến, cộng, lưu kết quả. Các BCI đó vẫn có thể cùng thuộc một dòng.
- **Một dòng có thể xuất hiện ở nhiều vị trí bytecode:** vòng lặp, điều kiện, câu lệnh ghép và cách compiler sắp mã có thể tạo nhiều đoạn code liên quan cùng dòng.
- **Một biểu thức có thể trải nhiều dòng:** việc chọn điểm đánh dấu là quyết định của compiler, không phản ánh mọi token hay cột trong file.
- **Compiler có thể thêm code không có source riêng:** bridge/synthetic methods, lambda, enum/record scaffolding, desugaring và các hỗ trợ do compiler tạo ra không nhất thiết có dòng Java riêng cho từng instruction.
- **Không có bảo đảm có bảng:** `LineNumberTable` là metadata tùy chọn; `javac -g:none` có thể loại bỏ bảng này mà hành vi phương thức không đổi.
- **Không có đường dẫn file từ bảng:** phải kết hợp với `SourceFile` hoặc thông tin ngoài class file để tìm file; tên file đơn thuần chưa đủ xác nhận đúng phiên bản source.
- **Không xác định thứ tự hay cấu trúc Java ban đầu:** từ cùng một bytecode có thể dựng ra nhiều biểu thức nguồn tương đương.

Một số API debugger trả về thông báo “không có thông tin dòng” khi class file không chứa dữ liệu đủ dùng. Kể cả khi có dòng, bước qua source bằng debugger có thể trông như “nhảy” qua các dòng do compiler gom/tách mã.

## 3. `LocalVariableTable`: tên và phạm vi của biến cục bộ

Lệnh bytecode đọc/ghi **slot** trong local-variable array của stack frame, chẳng hạn `iload_0` hoặc `istore_2`. Bytecode **không cần tên Java** như `left`, `right`, `total`: tên đó thường chỉ có trong debug metadata.

### 3.1. Một entry gồm năm trường

```text
start_pc          // bytecode offset bắt đầu phạm vi
length            // độ dài phạm vi tính bằng bytecode bytes
name_index        // tên biến trong constant pool
descriptor_index  // descriptor kiểu JVM, ví dụ I hoặc Ljava/lang/String;
index             // slot trong local-variable array của frame
```

Khoảng hiệu lực là **[start_pc, start_pc + length)**: gồm đầu, không gồm cuối. Ví dụ:

```text
LocalVariableTable:
  Start  Length  Slot  Name   Signature
      0       6     0  left   I
      0       6     1  right  I
      4       2     2  total  I
```

Đây là một kết quả **minh họa điển hình** từ phương thức `add` đơn giản, có thể thay đổi theo compiler/phiên bản/cách tối ưu:

- Tại BCI `0`, slot `0` được gắn nhãn `left`, slot `1` gắn nhãn `right`.
- Biến `total` chỉ có entry bắt đầu từ BCI `4`. Tại BCI `2`, **không được suy** rằng đã có thể xem `total` như một biến nguồn đã tồn tại.
- `I` là field descriptor JVM cho `int`; `Ljava/lang/String;` là ví dụ descriptor của tham chiếu `String`.
- Bảng **không lưu số `5` hay bất kỳ giá trị biến thực tế nào**. Giá trị chỉ có trong frame lúc chạy hoặc được suy qua mô phỏng bytecode, không nằm trong `LocalVariableTable`.

### 3.2. Slot không đồng nghĩa một biến nguồn cố định

- Với **phương thức instance**, slot `0` thông thường chứa `this`; tham số tiếp theo bắt đầu sau đó. Với **phương thức static**, không có `this` ngầm định, nên tham số đầu tiên có thể ở slot `0`.
- `long` và `double` tiêu thụ **hai slot liên tiếp**; các kiểu còn lại thường dùng một slot. Vì vậy chỉ số slot không trùng thứ tự tham số nguồn nếu có kiểu hai slot.
- Compiler có thể **tái sử dụng slot** cho hai biến nguồn khác nhau có phạm vi sống không chồng nhau. Hai entry có thể cùng `index` nhưng khác `start_pc/length` và tên.
- Một tên có thể xuất hiện nhiều entry ở các scope khác nhau. Ngược lại, biến có thể bị lược bỏ hoặc scope bị rút ngắn/tách ra vì code generation.
- `max_locals` trong `Code` là kích thước cần thiết của mảng slot khi thực thi, **không** phải số dòng trong `LocalVariableTable`.
- Khi bị thiếu metadata, `iload_2` vẫn chạy bình thường; debugger chỉ kém khả năng nói slot `2` tương ứng biến nguồn nào.

**Quy tắc đọc đúng:** phải xét đồng thời **phương thức + BCI hiện tại + slot + khoảng hiệu lực** trước khi gắn một tên local cho một giá trị. Không đọc riêng `Slot 2 = total` rồi áp cho mọi BCI và mọi lần chạy.

### 3.3. `LocalVariableTypeTable` và generic type

`LocalVariableTable` dùng descriptor JVM, chịu **type erasure**. Nếu nguồn có:

```java
java.util.List<String> names = java.util.List.of("An", "Binh");
```

Dữ liệu kiểu có thể được trình bày theo hai mức:

```text
LocalVariableTable:
  Name = names
  Descriptor = Ljava/util/List;

LocalVariableTypeTable:
  Name = names
  Signature = Ljava/util/List<Ljava/lang/String;>;
```

`LocalVariableTypeTable` có các thông tin scope/slot tương tự bảng local-variable thông thường, nhưng dùng **generic signature** thay vì descriptor đã xóa type parameter. Bảng này chỉ hữu ích khi compiler phát sinh thông tin generic liên quan và không có tác dụng buộc JVM giữ riêng “`List<String>`” so với “`List<Integer>`” khi chạy.

Không nhầm `LocalVariableTypeTable` với `Signature` attribute của chính lớp, trường hoặc phương thức; chúng có mức gắn kết khác nhau.

## 4. `SourceFile`, `SourceDebugExtension` và `MethodParameters`

### 4.1. `SourceFile` là tên, không phải mã nguồn

Một class file biên dịch từ `DebugMetadataDemo.java` có thể chứa:

```text
SourceFile: "DebugMetadataDemo.java"
```

Điều này giúp stack trace hiển thị dạng `DebugMetadataDemo.java:12` khi còn dữ liệu dòng. Nhưng thuộc tính đó **không lưu nội dung file**, vị trí Git, đường dẫn tuyệt đối hay commit. Nhiều class file có thể cùng khai báo một `SourceFile`. Nếu đang chạy artifact A nhưng mở source của artifact B, line number có thể “đúng định dạng” nhưng trỏ sang dòng sai.

### 4.2. `SourceDebugExtension` phục vụ ánh xạ nguồn mở rộng

Các công cụ sinh Java/bytecode từ template hoặc ngôn ngữ khác **có thể** gắn thông tin bổ sung như bản đồ nguồn nhiều tầng, ví dụ theo SMAP/JSR 45. Công cụ đọc phải hiểu định dạng bên trong; JVM không mặc nhiên biến metadata mở rộng thành một bản sao mã nguồn. Khi không có attribute này, không được tự suy ra file nguồn thứ hai.

### 4.3. `MethodParameters` khác hoàn toàn `LocalVariableTable`

`MethodParameters` là metadata trên `method_info` về **formal parameters** của method/constructor, gồm tên (nếu có) và flags liên quan. Với `javac`:

- `-parameters` yêu cầu xuất metadata để Java Reflection đọc tên parameter từ `Executable.getParameters()`.
- `-g` yêu cầu đầy đủ debug info, bao gồm local-variable information, nhưng **không thay thế** nhiệm vụ của `-parameters` cho reflection.
- `-g:none -parameters` có thể vẫn giữ `MethodParameters`, dù không có line/source/local-variable debug tables.
- `-g:lines,vars,source` chỉ định loại debug info; mặc định `javac` thường sinh **line number** và **source file**, không sinh toàn bộ thông tin local-variable.

Do đó, một framework muốn lấy tên tham số formal từ reflection cần kiểm tra `Parameter.isNamePresent()`; không thể coi tên trong `LocalVariableTable` là nguồn bảo đảm cho Java Reflection.

## 5. Thí nghiệm Java 17+: biên dịch, xem bytecode và quan sát thiếu metadata

Tạo một tệp tên **`DebugMetadataDemo.java`** (không khai báo `package`) với toàn bộ nội dung:

```java
public final class DebugMetadataDemo {
    public static int add(int left, int right) {
        int total = left + right;
        return total;
    }

    public static void main(String[] args) throws Exception {
        System.out.println(add(2, 3));
        var method = DebugMetadataDemo.class.getMethod(
                "add", int.class, int.class);
        var first = method.getParameters()[0];
        System.out.println(first.getName() + ":" + first.isNamePresent());
    }
}
```

Chương trình dùng Java Reflection tiêu chuẩn và không cần thư viện ngoài. `throws Exception` chỉ để ví dụ xử lý việc `getMethod` có thể báo checked exception nếu đổi tên/phương thức; với tệp trên, phương thức `add` tồn tại và là `public static`.

### Lần A — đủ debug metadata **và** tên tham số Reflection

Chạy trong thư mục chứa tệp (JDK 17+ có đủ `javac`, `java`, `javap`):

```shell
javac -g -parameters DebugMetadataDemo.java
java DebugMetadataDemo
javap -c -l -v -p DebugMetadataDemo
```

**Stdout chính xác của lệnh `java DebugMetadataDemo`:**

```text
5
left:true
```

Trong output rất dài của `javap`, tìm `public static int add(int, int)`. Những phần sau là **trích minh họa** của `javac` thông thường, không phải toàn bộ output:

```text
Code:
   0: iload_0
   1: iload_1
   2: iadd
   3: istore_2
   4: iload_2
   5: ireturn
LineNumberTable:
  line 3: 0
  line 4: 4
LocalVariableTable:
  Start  Length  Slot  Name   Signature
      0       6     0  left   I
      0       6     1  right  I
      4       2     2  total  I
MethodParameters:
  Name   Flags
  left
  right
```

Các số BCI và phạm vi ở bảng trên minh họa cách đọc, có thể khác nếu đổi source/compiler. `MethodParameters` là attribute của phương thức nên không nhất thiết in liền ngay bên dưới `LocalVariableTable` trong output thực tế. `javap -c` hiển thị instructions, `-l` hiển thị bảng dòng/biến, `-v` thêm chi tiết class file/attributes, `-p` hiển thị cả thành viên không public.

### Lần B — bỏ debug metadata, **giữ** tên tham số Reflection

Biên dịch lại **cùng tệp**, ghi đè `.class` cũ trong thư mục thí nghiệm:

```shell
javac -g:none -parameters DebugMetadataDemo.java
java DebugMetadataDemo
javap -c -l -v -p DebugMetadataDemo
```

Stdout của chương trình vẫn:

```text
5
left:true
```

Tuy `LineNumberTable`, `LocalVariableTable` và `SourceFile` từ `javac` không còn, `MethodParameters` vẫn có nhờ `-parameters`; vì vậy Reflection tiếp tục thấy tên `left`. Câu lệnh `add` vẫn cho kết quả `5`: debug metadata không phải điều kiện thực thi phép cộng.

### Lần C — bỏ cả debug metadata lẫn metadata tên tham số

```shell
javac -g:none DebugMetadataDemo.java
java DebugMetadataDemo
javap -c -l -v -p DebugMetadataDemo
```

**Stdout chính xác của chương trình:**

```text
5
arg0:false
```

Lúc này `Parameter.getName()` dùng tên suy diễn `arg0` khi không có tên thật, và `isNamePresent()` trả `false`. Đây là ví dụ rõ ràng rằng **không có tên source ≠ không có bytecode chạy được**.

**Lưu ý về cách chạy:** ba lần `javac` lần lượt thay tệp `DebugMetadataDemo.class` trong chính thư mục thí nghiệm. Nếu đang dùng một build tool hoặc classpath khác, hãy chắc chắn `java`/`javap` đang đọc **đúng bản .class vừa tạo**, tránh kết luận sai vì đọc nhầm artifact.

### Thí nghiệm phụ — thấy giới hạn của line number khi có exception

Thay `add` trong cùng file bằng:

```java
public static int add(int left, int right) {
    return left / right;
}
```

Để tạo lỗi có chủ đích, đổi lời gọi trong `main` thành `add(2, 0)` (mã này là **chỉnh sửa của thí nghiệm phụ**, không áp dụng đồng thời với stdout `5` bên trên). Khi chạy bản có `-g`, stack trace thường có dạng:

```text
Exception in thread "main" java.lang.ArithmeticException: / by zero
    at DebugMetadataDemo.add(DebugMetadataDemo.java:<line>)
    at DebugMetadataDemo.main(DebugMetadataDemo.java:<line>)
```

Ký hiệu `<line>` ở đây là chỗ minh họa; số thực phụ thuộc số dòng sau khi bạn chỉnh source. Khi biên dịch lại bằng `-g:none`, trace có thể hiển thị `Unknown Source`. Phép chia sai vẫn sinh cùng loại exception; thay đổi là **khả năng định vị source**, không phải semantics của `idiv`.

## 6. Mapping có thể đúng ở mức dòng mà vẫn sai về “câu lệnh Java”

Giả sử một phương thức chứa:

```java
int x = read();
int y = normalize(x) + validate(x);
return y;
```

Một compiler có thể đặt một hoặc nhiều điểm line cho bytecode của mỗi dòng, nhưng **không thể suy ngược đầy đủ** rằng có hai lời gọi `normalize` và `validate` trong biểu thức thứ hai chỉ từ `LineNumberTable`. Muốn hiểu biểu thức, công cụ còn phải phân tích opcode, operand stack, control flow và constant pool; ngay cả vậy, tên biến source hoặc dạng cú pháp gốc có thể không còn.

Các lý do mất thông tin phổ biến:

1. **Phép biến đổi không đối xứng:** nhiều source constructs tạo bytecode tương đương. `for` có thể biểu diễn giống `while`; dấu ngoặc, comment, khoảng trắng, tên biến có thể bị mất.
2. **Compiler sinh mã bổ sung:** lambda qua `invokedynamic`, bridge methods cho generic/override, synthetic accessor trong một số target/compiler, xử lý resource/exception và các cấu trúc khác tạo code không trùng một câu lệnh source độc lập.
3. **Tối ưu hóa và biến đổi:** javac/bytecode transformer/JIT có thể gộp, tách, di chuyển hoặc loại bỏ code. **JIT machine code** còn là một tầng khác với BCI; source mapping ở class file không trực tiếp là địa chỉ native.
4. **Line chỉ có độ phân giải dòng:** đặt breakpoint tại hai biểu thức nằm cùng một dòng có thể không tách được chỉ bằng `LineNumberTable`.
5. **Slot được tái sử dụng:** chỉ nhìn opcode `iload_1` không chứng minh slot `1` luôn mang một tên/kiểu Java cụ thể ở mọi BCI.
6. **Artifact và source lệch phiên bản:** source checkout khác commit hoặc class loader nạp bản JAR khác làm line number gợi sai đoạn source.
7. **Thông tin generic chỉ là signature:** `LocalVariableTypeTable` không phục hồi runtime value/type thực hay danh tính mọi object trong collection.

**Kết luận kỹ thuật của phần này:** class file thường đủ để JVM thực thi và verifier kiểm tra type safety; source-debug metadata giúp gắn nhãn một số vị trí nhưng **không bảo đảm tái tạo AST, tên biến, comment, biểu thức và file gốc chính xác**.

## 7. Ý nghĩa với instrumentation: giữ mapping khi chèn bytecode

Một agent có thể chèn probe trước lời gọi service:

```text
Trước:
  BCI 0  ... đọc tham số
  BCI 4  ... gọi service
  BCI 7  ... return

Sau khi chèn probe:
  BCI 0  ... probe trước service
  BCI 5  ... đọc tham số
  BCI 9  ... gọi service
  BCI 12 ... return
```

Đây là **sơ đồ minh họa**, không phải output `javap` cụ thể. Nếu giữ nguyên bảng `start_pc` của bytecode cũ trong khi code đã đổi offset, debugger/stack trace có thể hiển thị dòng không phù hợp hoặc class file có metadata không hợp lệ. Công cụ biến đổi cần quản lý tương quan BCI cũ–mới và các vùng sống của biến.

Khi thiết kế instrumentation:

- **Gắn probe với ý nghĩa ổn định** (tên class/method + descriptor + thông tin source hiện có) thay vì coi BCI ban đầu là định danh bất biến.
- **Chỉ chọn line từ metadata có thật.** Nếu thiếu `LineNumberTable`, báo “không biết dòng” thay vì bịa số dòng dựa vào opcode.
- **Dịch chuyển/cập nhật phạm vi** `start_pc` và `length` của `LocalVariableTable`/`LocalVariableTypeTable` khi chèn/xóa instruction ảnh hưởng vị trí/scope.
- **Bảo toàn hoặc chủ động thiết kế attribution cho probe:** bytecode mới có thể không đại diện một source line mới; một probe trước/giữa phương thức không nên gây hiểu nhầm rằng source có sẵn câu lệnh đó.
- **Đừng sửa tay mỗi bảng độc lập:** branch targets, exception handler ranges và `StackMapTable` có ràng buộc khác; dùng thư viện class-file transformation có hỗ trợ cập nhật offset/frame và kiểm tra kết quả.
- **Phân biệt `StackMapTable` với debug tables:** `StackMapTable` phục vụ type verification, còn `LineNumberTable`/`LocalVariableTable` phục vụ công cụ gỡ lỗi; mất debug info thường vẫn chạy được, nhưng làm sai verification frames có thể gây `VerifyError`.
- **Xác định đúng class loader và class version:** nếu nhiều class loader có bản `com.example.Service` khác nhau, metadata của một bản không áp chính xác cho bản kia.
- **Lưu provenance:** lưu build hash/commit, tên class loader, class-file hash hoặc artifact version và chiến lược source lookup để điều tra production không dùng nhầm source.

Nếu mục tiêu là đo latency theo phương thức, không nhất thiết cần line number. Nhưng nếu sản phẩm hiển thị “thời gian xử lý của dòng 42” hoặc “giá trị biến `total` tại dòng 42”, công cụ phải nhận biết **thiếu dữ liệu**, **scope của biến**, **bytecode đã bị biến đổi** và độ phân giải giới hạn của line mapping.

## 8. Checklist chẩn đoán khi debugger hoặc stack trace chỉ sai dòng

| Hiện tượng | Điều nên kiểm tra | Diễn giải đúng |
|---|---|---|
| Stack trace ghi `Unknown Source` | `SourceFile`/`LineNumberTable` có trong đúng class đang chạy không? | Không đủ metadata để hiện file/dòng, không chứng minh code không chạy |
| `javap` thấy `iload_2` nhưng không thấy biến `total` | Có `LocalVariableTable` không, BCI hiện tại có nằm trong scope của entry không? | Tên biến vắng mặt hoặc ngoài scope; slot vẫn tồn tại |
| Reflection trả `arg0` | Có biên dịch `-parameters` không; `isNamePresent()` là gì? | `MethodParameters` thiếu tên formal; `-g` không bảo đảm khắc phục |
| Biến generic hiện `java.util.List` | Có `LocalVariableTypeTable` với generic signature không? | Descriptor đã xóa type args, metadata generic có thể bị thiếu |
| Debugger “nhảy” dòng | Xem `LineNumberTable` và bytecode của phương thức, compiler-generated instructions | Mỗi dòng không tương ứng chính xác một instruction |
| Instrumentation khiến stack trace lệch dòng | Bytecode mới và bảng line/scope có được cập nhật không? | Metadata có thể đang mô tả offset cũ |
| Dòng đúng cú pháp nhưng nội dung source khác | So sánh JAR/class bytes với source version/build | Đọc nhầm phiên bản source hoặc class loader |
| Có line number nhưng không debug được biến | Kiểm tra `LocalVariableTable` độc lập với `LineNumberTable` | Hai loại metadata được cấu hình độc lập |

**Quy trình đọc một lỗi instrumentation thực tế:**

1. Chốt định danh **class + method descriptor + defining class loader + artifact/build**.
2. Lấy đúng class bytes đã/đang dùng ở giai đoạn cần điều tra; phân biệt bytecode trên đĩa với bytecode được transformer xuất ra.
3. Dùng `javap -c -l -v -p` trên artifact kiểm soát được để xem BCI, `LineNumberTable`, local scope và các attribute liên quan. Nếu xử lý bytecode trong runtime, dump một bản bytecode được phép để đối chiếu, thay vì mặc định file build là bản JVM đang dùng.
4. Nếu cần tên local, tra `LocalVariableTable` theo **đúng BCI và slot**, không suy từ tham số Reflection hoặc source hiện tại.
5. Kiểm tra mapping bị mất khi biên dịch/obfuscation/instrumentation; nếu không có, chỉ công bố mức kết luận mà metadata thật sự hỗ trợ.

## 9. Những ngộ nhận cần tránh

- **“Mỗi dòng Java ứng với một bytecode index.”** Sai: line table lưu các điểm đánh dấu; một dòng có thể có nhiều opcode và có thể xuất hiện ở nhiều BCI.
- **“`LineNumberTable` chứa mã nguồn và tên file.”** Sai: chỉ chứa cặp BCI/dòng; tên file là metadata khác và file source phải lấy từ bên ngoài.
- **“`LocalVariableTable` chứa giá trị biến.”** Sai: chứa tên, kiểu descriptor, slot, khoảng áp dụng; giá trị nằm trong frame lúc chạy.
- **“Slot 0 luôn là `this`.”** Sai với phương thức static; slot dùng cho tham số đầu tiên, và cách đánh số còn phụ thuộc kích thước kiểu dữ liệu.
- **“Có `-g` thì Java Reflection biết tên tham số.”** Không bảo đảm: dùng `-parameters`/`MethodParameters` và kiểm tra `isNamePresent()`.
- **“`LocalVariableTypeTable` vô hiệu hóa type erasure.”** Sai: đó là metadata generic cho công cụ, không đổi semantics runtime.
- **“Thiếu `-g` làm bytecode mất logic.”** Sai: thông thường chỉ thiếu debug info, còn code vẫn thực thi.
- **“Instrument code thì có thể giữ nguyên tất cả BCI.”** Không được giả định: chèn/xóa instructions có thể đổi offsets và phạm vi biến, các metadata liên quan phải được xử lý lại.
- **“Stack trace trỏ vào `File.java:42` thì chắc chắn đúng bản source tôi đang mở.”** Sai: cần đối chiếu artifact/version/class loader.
- **“Từ `javap` có thể tái tạo y nguyên Java source.”** Sai: debug tables là thông tin một phần; decompiler suy luận cấu trúc và không thể phục hồi mọi biểu thức, tên/comment/khoảng trắng.

## 10. Câu hỏi tự kiểm tra

1. **Tại sao cùng một dòng Java có thể xuất hiện nhiều lần trong `LineNumberTable`?** Vì nhiều vị trí bytecode/nhánh/vòng lặp hoặc quyết định của compiler có thể cùng gắn với một dòng nguồn; ánh xạ không bắt buộc một-một.
2. **Trong `LocalVariableTable`, `start_pc=4`, `length=2` có áp dụng tại BCI `6` không?** Không. Khoảng là `[4, 6)`; BCI `6` nằm ngoài.
3. **`iload_1` có đủ kết luận slot `1` tên `count` không?** Không. Phải biết phương thức, BCI và entry metadata hợp lệ; tên có thể vắng mặt hoặc slot đã tái sử dụng.
4. **Tại sao `-g:none -parameters` vẫn có thể khiến reflection in `left:true`?** Vì `MethodParameters` của `-parameters` độc lập với debug attributes của `-g`.
5. **Điều gì xảy ra nếu agent chèn 5 byte nhưng không cập nhật line/scope metadata?** Các offset debug có thể không còn khớp bytecode mới; kết quả gỡ lỗi có thể sai và class file có thể không hợp lệ theo các ràng buộc liên quan.
6. **Có thể dựa vào `SourceFile` để xác định Git commit không?** Không. Nó chỉ là tên nguồn được ghi vào class; phải dùng thêm thông tin build/artifact/provenance.
7. **Metadata nào giúp debugger hiện `List<String>` cho biến local?** `LocalVariableTypeTable` khi compiler đã ghi signature tương ứng; `LocalVariableTable` chỉ cho descriptor đã erasure.

## Tài liệu chính thức để đối chiếu

- [Java SE 21 JVM Specification — Chapter 4, Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): ``4.7.10–4.7.14` cho `SourceFile`, `SourceDebugExtension`, `LineNumberTable`, `LocalVariableTable` và `LocalVariableTypeTable`; `4.7.24` cho `MethodParameters`.
- [JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-g`, `-g:lines,vars,source`, `-g:none`, `-parameters`.
- [JDK 21 — javap command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): `-c`, `-l`, `-v`, `-p`.
- [Java SE 21 — java.lang.reflect.Parameter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): `getName()` và `isNamePresent()`.

**Ghi nhớ:** `LineNumberTable` chỉ gắn **vị trí bytecode với dòng**; `LocalVariableTable` gắn **slot và khoảng BCI với tên/descriptor**; `LocalVariableTypeTable` có thể bổ sung **generic signature**; `MethodParameters` phục vụ **tên tham số formal qua reflection**. Tất cả đều cung cấp manh mối cho công cụ quan sát, không phải bản mã nguồn Java đầy đủ.