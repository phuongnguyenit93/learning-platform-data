# LineNumberTable, LocalVariableTable và giới hạn khi khôi phục mã nguồn

## 1. Tệp `.class` có thể tiết lộ điều gì về mã nguồn?

Trình biên dịch Java chuyển source code thành **class file** chứa bytecode và các cấu trúc nhị phân theo đặc tả JVM. Class file đủ thông tin để JVM tải, kiểm chứng, liên kết và thực thi một lớp; nó **không phải bản lưu nguyên văn** của tệp `.java`.

Trong class file, những **thuộc tính (attributes) tùy chọn** có thể cung cấp dữ liệu cho công cụ gỡ lỗi, chẳng hạn:

- **`LineNumberTable`**: ánh xạ một số vị trí bytecode của phương thức tới **số dòng mã nguồn**.
- **`LocalVariableTable`**: mô tả **tên biến cục bộ**, kiểu dưới dạng descriptor, vị trí slot và khoảng bytecode biến có hiệu lực.
- **`LocalVariableTypeTable`**: có thể lưu thêm **generic signature** cho một số biến cục bộ có kiểu tổng quát; nó không thay thế `LocalVariableTable`.
- **`SourceFile`**: tên tệp nguồn dùng để mô tả nơi class được biên dịch, thường phục vụ debug/stack trace; đây chỉ là tên, không chứa nội dung tệp.
- **`SourceDebugExtension`** (khi có): có thể mang thông tin ánh xạ nguồn mở rộng do công cụ/ngôn ngữ tạo ra, hữu ích cho tình huống nhiều tầng sinh mã.

Hai bảng đầu là trọng tâm của bài. Sự hiện diện của chúng giúp debugger, IDE và `javap` hiển thị thông tin dễ hiểu hơn, **không làm JVM cần mã nguồn gốc mới thực thi được**. Một class file không có các bảng này vẫn có thể là class file hoàn toàn hợp lệ và chạy đúng.

Cũng cần phân biệt ba hoạt động:

1. **Disassembly**: hiển thị instruction JVM, ví dụ `iload`, `iadd`, `invokevirtual` từ bytecode. Đây là việc `javap -c` thực hiện.
2. **Debugging**: đối chiếu vị trí thực thi với dòng/biến nguồn khi metadata và trạng thái runtime cho phép. Debugger có thể xem dữ liệu đã được JIT/runtime duy trì, nhưng không tạo lại thông tin nguồn vốn chưa từng được lưu.
3. **Decompilation**: suy đoán một đoạn source cấp cao có hành vi tương ứng từ bytecode. Source được decompiler dựng lại **không mặc nhiên là source ban đầu**.

## 2. Các thuộc tính nằm ở đâu trong cấu trúc class file?

Theo JVM class-file format, một class có constant pool, khai báo field/method và các attribute. Mỗi method có thể có một thuộc tính **`Code`** nếu phương thức đó có bytecode. Bên trong `Code` gồm bytecode, thông tin stack/locals, bảng exception handler và danh sách attribute **gắn riêng với đoạn code ấy**.

~~~text
ClassFile
├── constant_pool
├── fields[]
├── methods[]
│   └── method_info
│       └── attributes[]
│           └── Code (nếu method có bytecode)
│               ├── max_stack
│               ├── max_locals
│               ├── code[]                  ← các byte instruction
│               ├── exception_table[]
│               └── attributes[]
│                   ├── LineNumberTable    ← tùy chọn
│                   ├── LocalVariableTable ← tùy chọn
│                   ├── LocalVariableTypeTable (nếu có)
│                   └── StackMapTable/...  ← phục vụ mục đích khác
└── attributes[]
    └── SourceFile (nếu có)
~~~

`LineNumberTable` và `LocalVariableTable` là **nested attribute của `Code`**, nên gắn với **một method cụ thể**, không phải bảng duy nhất áp dụng toàn bộ class. `SourceFile` là thuộc tính của class, không nằm trong `Code`.

Mặc dù dữ liệu này nằm trong `.class`, nó **không phải instruction có tác dụng lên thuật toán Java**. JVM có thể sử dụng hoặc cung cấp dữ liệu cho công cụ debug; việc có hay không có metadata không biến `if`, `for` hoặc `return` thành thuật toán khác.

Bên cạnh đó:

- **`StackMapTable`** hỗ trợ kiểm chứng kiểu ở những điểm bytecode liên quan. Đây không phải danh sách tên biến nguồn và không thay thế LocalVariableTable.
- **`Exceptions`** mô tả những exception được khai báo ở cấp phương thức; không chứa cách viết nguyên văn `throws` trong source.
- **`Signature`** có thể ghi generic signature của class/field/method; generic source không vì vậy được phục dựng đầy đủ.
- **`MethodParameters`** có thể chứa tên và flags của **tham số method**, tùy compiler option như `javac -parameters`; nó **khác** `LocalVariableTable`.

## 3. LineNumberTable: ánh xạ vị trí bytecode tới dòng nguồn

Một entry của `LineNumberTable` gồm hai giá trị ý nghĩa:

| Trường | Ý nghĩa |
| --- | --- |
| `start_pc` | Offset bytecode tính từ đầu mảng `code[]` của **method hiện tại** |
| `line_number` | Số dòng nguồn mà compiler liên hệ với bytecode bắt đầu từ vị trí ấy |

Ví dụ **minh họa** (offset/dòng do compiler quyết định, không phải một output `javap` được cam kết cho mọi phiên bản):

~~~text
LineNumberTable:
  line 10: 0
  line 11: 4
  line 12: 9
~~~

Cách đọc: instruction bắt đầu tại offset 0 được gắn với dòng 10; offset 4 gắn dòng 11; offset 9 gắn dòng 12. Những instruction giữa các mốc có thể được debugger liên hệ với mốc dòng phù hợp theo bảng và vị trí thực thi.

**LineNumberTable không phải bản đồ một-một giữa dòng nguồn và instruction:**

- Một dòng Java có thể sinh **nhiều instruction**.
- Một statement hoặc biểu thức có thể trải qua **nhiều dòng**.
- Nhiều instruction có thể được liên hệ với **cùng một dòng**.
- Compiler có thể chọn hoặc bỏ qua mốc dòng tùy cách sinh bytecode.
- Code được sinh tổng hợp hoặc do compiler biến đổi có thể có ánh xạ dòng khác trực giác từ source.
- Bảng chứa **số dòng**, không chứa chữ trong dòng, indentation, comment, tên biến hoặc cột ký tự.

### Tác dụng với stack trace

Khi exception được ghi thành stack trace, JVM/runtime có thể dùng tên class, tên method, `SourceFile` và `LineNumberTable` để báo, ví dụ:

~~~text
at demo.DebugInfoDemo.compute(DebugInfoDemo.java:7)
~~~

Đây chỉ là **ví dụ định dạng**, không phải dòng stack trace khẳng định sẽ xuất hiện trong chương trình thực hành bên dưới. Con số `7` chỉ là số dòng nguồn khi metadata cho phép xác định. Nếu không có thông tin dòng, stack trace có thể hiển thị dạng `Unknown Source`, hoặc còn tên file nhưng không có số dòng, tùy metadata và cách biểu diễn.

Có `LineNumberTable` **không đảm bảo** luôn xác định đúng một câu lệnh nguồn cho mọi PC. Với compiler sinh code, lambda, `switch`, inline ở runtime, instrumentation, hoặc mã từ ngôn ngữ khác, các mốc dòng có thể không khớp kỳ vọng của người debug.

## 4. LocalVariableTable: tên, kiểu, slot và phạm vi tồn tại

Mỗi entry `LocalVariableTable` được mô tả bằng các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `start_pc` | Offset bytecode nơi khoảng hiệu lực của biến bắt đầu |
| `length` | Số byte trong khoảng hiệu lực được mô tả |
| `name_index` | Chỉ số constant pool trỏ đến tên biến |
| `descriptor_index` | Chỉ số constant pool trỏ đến descriptor của kiểu biến |
| `index` | Chỉ số **local-variable slot** trong frame của method |

Khoảng hiệu lực được mô tả bởi `[start_pc, start_pc + length)`, tính theo offset bytecode. Không được đọc `length` là số ký tự, số dòng Java, số lần biến được dùng hoặc số byte mà object chiếm trong heap.

Ví dụ mô tả gần với `javap -l` (dòng/offset là minh họa, không phải kết quả cố định):

~~~text
LocalVariableTable:
  Start  Length  Slot  Name      Signature
      0      14     0  input     I
      4      10     1  doubled   I
      9       5     2  result    I
~~~

- `input`, `doubled`, `result` là **tên nguồn compiler đã lưu**, không phải những giá trị số thực của chúng khi chương trình chạy.
- `Signature` trong đầu ra `javap` của bảng trên hiển thị **descriptor** như `I`, `Ljava/lang/String;`; đây không có nghĩa bảng `LocalVariableTable` tự lưu toàn bộ generic type.
- `Slot` xác định ô logic trong local-variable array của một **frame method**; nó **không phải địa chỉ stack trong RAM**.
- Trên method instance, slot 0 thường giữ `this`; trên method `static` không có `this`.
- `long` và `double` dùng **hai local-variable slot liên tiếp** theo quy tắc frame JVM; nhiều kiểu khác, gồm reference, dùng một slot.

### Scope ở source và khoảng bytecode

Hai biến có cùng tên trong các scope tách biệt có thể sử dụng **cùng local slot ở hai khoảng sống không giao nhau**. Một compiler có thể tái sử dụng slot dù tên và kiểu khác nhau; nếu đọc `index = 2` ở hai entry khác nhau thì không thể kết luận đó là **một biến nguồn**.

Ngược lại, source có thể khai báo một biến nhưng compiler phân bổ, tái sắp xếp hoặc loại bỏ cách biểu diễn vật lý khi tối ưu. LocalVariableTable phản ánh metadata của **class file đã được phát hành**, không phải ảnh chụp trạng thái register/stack của JIT ở thời điểm T.

### LocalVariableTypeTable và generic

Ví dụ Java:

~~~java
java.util.List<String> words = java.util.List.of("JVM");
~~~

Với class file có đủ debug metadata, `LocalVariableTable` có thể mô tả descriptor của `words` là `Ljava/util/List;`. `LocalVariableTypeTable` có thể lưu thêm generic signature như `Ljava/util/List<Ljava/lang/String;>;` để debugger hiểu kiểu tổng quát. Thông tin ấy **tùy chọn** và không phục dựng đầy đủ mọi biểu thức generic hay cách suy luận kiểu nguồn.

Không nhầm `LocalVariableTypeTable` với **`Signature` attribute** của field/method/class, hoặc `StackMapTable` hỗ trợ verification; tên tương tự nhưng mục đích và vị trí khác nhau.

## 5. Thực hành Java 17+: có và không có debug metadata

Tạo tệp **`src/demo/DebugInfoDemo.java`** với toàn bộ nội dung:

~~~java
package demo;

public final class DebugInfoDemo {
    static int compute(int input) {
        int doubled = input * 2;
        int result = doubled + 3;
        return result;
    }

    public static void main(String[] args) {
        int answer = compute(4);
        System.out.println("Result=" + answer);
    }
}
~~~

Biên dịch với JDK 17+; tạo hai thư mục đầu ra riêng trước:

~~~bash
mkdir out-debug
mkdir out-minimal
javac --release 17 -g:lines,vars,source -d out-debug src/demo/DebugInfoDemo.java
javac --release 17 -g:none -d out-minimal src/demo/DebugInfoDemo.java
~~~

Chạy hai class file bằng cùng logic:

~~~bash
java -cp out-debug demo.DebugInfoDemo
java -cp out-minimal demo.DebugInfoDemo
~~~

**Mỗi lệnh in đúng một dòng stdout**:

~~~text
Result=11
~~~

Cả hai bản chạy cùng ý nghĩa vì `-g` thay đổi lượng **debug metadata** compiler đưa vào class, không thay đổi thuật toán cần thiết để tính `4 * 2 + 3`.

### 5.1. Dùng javap đọc phiên bản có debug info

~~~bash
javap -classpath out-debug -c -l -p demo.DebugInfoDemo
javap -classpath out-debug -v -p demo.DebugInfoDemo
~~~

Quan sát:

1. `-c` hiển thị bytecode của `compute` và `main` (như phép nhân, phép cộng, gọi `println`, trả về).
2. `-l` yêu cầu in **line number** và **local variable tables** nếu có.
3. `-p` yêu cầu hiển thị cả thành viên không public; `compute` của ví dụ là package-private.
4. `-v` in thêm thông tin chi tiết như class-file version, constant pool và các `Code` attributes.
5. Với `--release 17`, class file được sinh cho Java 17 có **major version 61**.

Bản `out-debug` được yêu cầu phát hành line number, tên local variable và thông tin source. Bởi vậy trong phần `compute`, bạn có thể tìm thấy những biến như `input`, `doubled`, `result` trong `LocalVariableTable`. Đồng thời `LineNumberTable` ánh xạ những offset bytecode tới các số dòng của tệp bạn vừa tạo. **Số offset và bảng in đầy đủ do compiler quyết định**: hãy đọc kết quả thực tế thay vì chép một bảng ví dụ rồi xem là tiêu chuẩn.

### 5.2. So với phiên bản loại bỏ debug metadata

~~~bash
javap -classpath out-minimal -c -l -p demo.DebugInfoDemo
javap -classpath out-minimal -v -p demo.DebugInfoDemo
~~~

Với `-g:none` của `javac`, class file không mang các thuộc tính debug `LineNumberTable` và `LocalVariableTable` do những tùy chọn `-g` sinh ra. `SourceFile` debug attribute cũng không được yêu cầu ở bản này. Dù vậy, bytecode cần thiết để thực hiện `compute(4)` và gọi `println` vẫn tồn tại; `javap -c` vẫn hiển thị instruction và phương thức, và `java` vẫn chạy được.

Không rút ra kết luận rằng **mọi metadata đã biến mất**: class file vẫn phải có tên class/method, descriptor, constant pool cùng cấu trúc phục vụ runtime; một số attribute khác vẫn cần cho kiểm chứng hoặc tính năng ngôn ngữ.

### 5.3. Phân biệt các công tắc thường dùng

| Tùy chọn javac | Thông tin cần quan sát |
| --- | --- |
| `-g` | Sinh tất cả debug information được hỗ trợ, gồm line, source, vars |
| `-g:lines,vars,source` | Yêu cầu ba nhóm thông tin trên một cách tường minh |
| `-g:lines,source` | Có line/source nhưng không yêu cầu tên local variables |
| `-g:none` | Không sinh debug information |
| `-parameters` | Có thể lưu **tên tham số method** trong `MethodParameters`; khác LocalVariableTable |
| `--release 17` | Nhắm ngữ nghĩa API/platform và class-file target của Java 17; không phải công tắc debug |

`javac` ở chế độ mặc định thường sinh **lines và source** nhưng không sinh **vars**. Khi cần xem chắc chắn tên local variables trong bài tập, dùng `-g:vars` hoặc `-g` theo compiler cụ thể.

## 6. Đọc `javap -v` mà không nhầm metadata với mã chương trình

Khi mở phần `Code`, bạn sẽ thường thấy cấu trúc liên quan:

~~~text
Code:
  stack=..., locals=..., args_size=...
     0: ...
     1: ...
     ...
  LineNumberTable:
    line ...: ...
  LocalVariableTable:
    Start Length Slot Name Signature
    ...
~~~

Đây là **khung trình bày**, không phải output thực của một phiên bản `javac` cụ thể.

- `stack=...` và `locals=...` biểu thị giới hạn operand stack và số local slots **theo frame bytecode**, không phải kích thước native call stack hoặc tổng bộ nhớ chương trình.
- Mã lệnh ở địa chỉ 0, 1, ... là **offset trong `code[]` của method**, không phải địa chỉ RAM.
- Một method abstract hoặc native không có phần `Code` tương ứng, vì vậy không kỳ vọng nó chứa `LineNumberTable`/`LocalVariableTable` như method Java có bytecode.
- Method được tạo bởi compiler (constructor mặc định, bridge, lambda helper, synthetic member...) có thể không có cấu trúc mapping tương ứng với một method nguyên vẹn trong source.

Nếu tên biến nguồn vắng mặt ở `LocalVariableTable`, debugger/decompiler có thể tự đặt tên như `var1`, `local2` hoặc `arg0`. Những tên ấy **là sản phẩm suy đoán hoặc hiển thị của công cụ** nếu không có metadata đáng tin, không chứng minh tệp Java gốc có cùng tên.

## 7. Giới hạn khi khôi phục mã nguồn từ class file

### 7.1. Biên dịch là phép biến đổi nhiều-đầu-vào thành ít thông tin hơn

Nhiều đoạn source khác nhau có thể tạo **bytecode tương đương, thậm chí trùng** sau tối ưu tại thời điểm biên dịch. Ví dụ:

~~~java
int result = 4 + 5;
~~~

và:

~~~java
int result = 9;
~~~

Một Java compiler có thể constant-fold biểu thức `4 + 5` thành hằng `9`. Khi xem bytecode, không có bảo đảm phân biệt người viết từng gõ phép cộng hay hằng trực tiếp. Nếu nguồn có `final int n = 9` hoặc import rút gọn, thông tin nguyên dạng cũng có thể bị compiler chuẩn hóa hay loại bỏ.

Ngay cả khi giữ `LineNumberTable`, hai cách viết trên có thể nằm ở **cùng một dòng** nên chỉ biết mốc dòng không đủ phân biệt cách viết. Có `LocalVariableTable` có thể giữ tên `result`, nhưng không giữ biểu thức `4 + 5` dưới dạng text.

### 7.2. Những thông tin thường mất hoặc biến dạng

| Thông tin ở source | Có thể khôi phục chính xác từ class file? |
| --- | --- |
| Bytecode instruction và descriptor đã biên dịch | **Có**, khi class file hợp lệ và có thể đọc, `javap` xem được cấu trúc thực |
| Tên class/method/field hiện diện trong ABI | Thường **có**, nhưng có thể đã bị obfuscate/rename trước khi nhận file |
| Dòng source gắn với bytecode | **Có một phần** nếu tồn tại LineNumberTable và thông tin tương ứng |
| Tên biến cục bộ | **Có một phần** nếu tồn tại LocalVariableTable và compiler lưu tên |
| Generic type của một số local variable | **Có một phần** nếu có LocalVariableTypeTable và thông tin hợp lệ |
| Tên tham số method | Có thể qua LocalVariableTable hoặc MethodParameters, tùy compiler flags |
| Comment, whitespace, indentation, cách xuống dòng | **Không**, thông thường không được lưu |
| Import statement nguyên văn, alias import, cách đặt qualifier | **Không**; class file thường lưu tham chiếu kiểu đã được compiler giải quyết |
| Biểu thức gốc trước constant folding hoặc desugaring | **Không đảm bảo** |
| Cách viết `for` hay `while`, `switch` ở source | Chỉ có thể **suy luận**; nhiều cấu trúc hạ xuống bytecode tương tự |
| Chính xác tên/ranh giới mọi biến trong source | **Không đảm bảo**; scope/slot có thể bị thay đổi hoặc metadata thiếu |
| Tên file gốc, nội dung tệp `.java` đầy đủ | SourceFile chỉ là tên khi có; **không chứa toàn văn tệp** |

Một decompiler thường dựng code **dễ hiểu và có vẻ giống Java**, nhưng đó là **một lời giải** cho bytecode đã biết, không chứng minh đây là source mà tác giả đã viết.

### 7.3. Compiler biến đổi ngữ nghĩa cấp cao xuống JVM

Những tính năng cấp nguồn có thể bị **lowering/desugaring** khi biên dịch:

- Lambda hoặc method reference có thể gắn với `invokedynamic` và bootstrap methods thay vì tồn tại như biểu thức lambda nguyên văn.
- Try-with-resources được chuyển thành cấu trúc đóng tài nguyên và xử lý exception/suppressed exception, thường dài hơn đáng kể so với cú pháp `try (...)`.
- Enhanced `for` có thể trở thành vòng lặp iterator hoặc truy cập theo index tùy kiểu dữ liệu.
- String switch, enum switch, generic erasure, autoboxing, bridge methods và synthetic method/class đều có thể làm bytecode không còn trùng cấu trúc câu lệnh ban đầu.
- Kotlin, Scala hoặc ngôn ngữ JVM khác có thể tạo state machine, helper class, metadata và tên method không có cú pháp Java nguồn tương đương một-một. **Decompile được Java-like output** không có nghĩa đã khôi phục được source Kotlin/Scala ban đầu.

Ngay cả khi decompiler khôi phục một cách viết Java **biên dịch lại được** và chạy tương đương, comment, tên biến không có trong metadata, ý đồ nghiệp vụ, cấu trúc file/package nguồn và lựa chọn style vẫn có thể khác bản gốc.

### 7.4. Obfuscation và stripping metadata

Công cụ đóng gói/obfuscation có thể đổi tên class, method hoặc field không bắt buộc giữ tên, xóa debug attributes, thay đổi cấu trúc bytecode hoặc tối ưu. Vì vậy một file tải về có thể khác class file được compiler phát hành lần đầu. `LocalVariableTable` có thể bị xóa hoàn toàn hoặc giữ với tên không còn giá trị gốc.

Mất LineNumberTable làm việc đọc stack trace và đặt breakpoint theo dòng khó hơn; mất LocalVariableTable làm debugger khó trình bày tên biến cục bộ. **Không có bảng nào ngăn JVM chạy** nếu class file sau biến đổi vẫn tuân thủ ràng buộc thực thi.

### 7.5. JIT không phải quá trình khôi phục ngược từ source

JVM có thể JIT-compile và tối ưu instruction lúc chạy: inline method, loại bỏ allocation, thay đổi vị trí dữ liệu trong register/stack. Đây là tối ưu **runtime**, tách với class-file debug attributes compiler đã sinh trước đó.

Decompiler thường đọc class file trên đĩa hoặc bytecode đang có; nó **không đọc được toàn văn source ban đầu từ code máy đã JIT tối ưu**. Khi debug ở chế độ tối ưu, một biến nguồn có thể tạm không có giá trị quan sát trực tiếp tại PC được chọn, dù LocalVariableTable vẫn mô tả tên/slot ở mức bytecode. Công cụ debug có thể dùng metadata runtime bổ sung để hiển thị thông tin, nhưng không có cam kết mọi local luôn đọc được.

## 8. Ứng dụng thực tế của hai bảng

### 8.1. Stack trace và điều tra production

Khi lỗi xuất hiện trong log, `LineNumberTable` giúp gắn stack frame tới số dòng nguồn. Điều này hữu ích **chỉ khi nguồn đang xem đúng phiên bản class đã chạy**. Nếu bản production được build từ commit khác hoặc qua instrumentation/obfuscation, dòng 52 trên stack trace không nhất thiết chỉ cùng statement ở checkout hiện tại.

Quy trình chẩn đoán:

1. Xác định đúng artifact/version đang chạy, JDK, classpath/module path và build identifier.
2. Đọc stack trace, tách **stderr** với stdout/log theo thời gian nếu có thể.
3. Kiểm tra class runtime chứa LineNumberTable bằng `javap -v` trên **artifact thực tế**.
4. Mở nguồn ở đúng commit/build; không ghép số dòng của binary A với source B.
5. Nếu artifact đã obfuscate, dùng mapping tương ứng do build cung cấp, nếu được lưu giữ.

### 8.2. Debugger và IDE

Khi bấm “Step Over/Into” hoặc đặt breakpoint ở dòng, debugger dùng mapping từ **dòng nguồn ↔ vị trí thực thi bytecode** theo dữ liệu compiler/runtime. Do LineNumberTable không phải ánh xạ một-một, một breakpoint dòng có thể dừng ở vị trí không đúng trực giác, hoặc không thể đặt khi không có code tương ứng.

LocalVariableTable hỗ trợ hiển thị tên local tại một phạm vi code. Không có bảng này, debugger vẫn có thể kiểm tra field, tham số có metadata riêng, stack/frame và giá trị khác tùy khả năng, nhưng không hứa khôi phục tên local ban đầu. Những thông báo “variable not available” có thể do **scope đã hết, metadata bị thiếu, hoặc runtime tối ưu**, không chỉ một nguyên nhân.

### 8.3. Decompile để hiểu bytecode, không thay thế source control

Decompile có thể giúp:

- Hiểu public API và luồng điều khiển của thư viện thiếu source.
- Nhận ra synthetic/bridge methods hoặc code được compiler sinh.
- Đối chiếu hành vi bytecode với giả định lúc code review.
- Điều tra khác biệt giữa nguồn và binary do build, bytecode instrumentation hoặc obfuscation.

Giới hạn: kết quả decompile **phải được kiểm chứng bằng bytecode và thử nghiệm** trước khi coi là hành vi đáng tin. Khôi phục chính xác file nguồn vẫn cần bản lưu source code tương ứng trong Git/source archive hoặc artifact gốc nếu có.

## 9. Checklist đọc một class file lạ

Với `some-library.jar`, có thể làm việc như sau:

~~~bash
jar tf some-library.jar
javap -classpath some-library.jar -public -s example.pkg.LibraryClass
javap -classpath some-library.jar -c -l -p example.pkg.LibraryClass
javap -classpath some-library.jar -v -p example.pkg.LibraryClass
~~~

`jar tf` liệt kê nội dung archive; `javap -public -s` cho API/descriptor; `-c` xem instruction, `-l` xem bảng line/local nếu có; `-v` kiểm tra version, constant pool và attributes. Thay `example.pkg.LibraryClass` bằng tên class thật có trong JAR.

Nếu các bảng hiện diện, tự hỏi:

- `LineNumberTable` có bao phủ vùng code cần điều tra không? Tên nguồn `SourceFile` là gì?
- `LocalVariableTable` có tên local và phạm vi PC nào? Slot có được dùng lại ở khoảng khác không?
- Có `LocalVariableTypeTable` hoặc `MethodParameters` không? Chúng trả lời **câu hỏi khác** so với LNT/LVT.
- Có dấu hiệu synthetic/bridge method, lambda hoặc compiler transformation không?
- Artifact đã obfuscate/strip hay tương ứng commit/build nào?

Không lấy số offset `javap` rồi coi đó là **địa chỉ vật lý**, không lấy tên local từ decompiler rồi kết luận chắc chắn đó là tên nguồn.

## 10. Những hiểu lầm cần tránh

1. **“LineNumberTable lưu code từng dòng.”** Không: nó lưu **offset bytecode và số dòng**, không lưu ký tự trên dòng.
2. **“LocalVariableTable chứa giá trị hiện thời của từng biến.”** Không: nó mô tả metadata tên/descriptor/slot/range; giá trị là trạng thái runtime.
3. **“Có LVT thì compiler phải giữ tên biến sau mọi tối ưu.”** Không: compiler, obfuscator hoặc build pipeline có thể bỏ/thay metadata, và JIT runtime có thể tối ưu state.
4. **“Slot index là địa chỉ RAM.”** Không: đó là index logic của local-variable array trong JVM frame.
5. **“SourceFile đủ để khôi phục source.”** Không: nó thường chỉ lưu tên file, không có văn bản `.java`.
6. **“`javap -c` chính là decompiler ra Java.”** Không: `javap -c` **disassemble JVM instruction**; decompiler phải suy diễn cấu trúc cấp cao.
7. **“Không có debug table thì class không chạy.”** Không: metadata debug là tùy chọn, JVM vẫn thực thi class hợp lệ.
8. **“Một class file sẽ chỉ tương ứng một source Java y hệt.”** Không: nhiều source có thể sinh bytecode tương đương, nhất là sau constant folding/desugaring.
9. **“Generic parameter, lambda, try-with-resources luôn còn nguyên như lúc viết.”** Không: compiler có thể đổi cách biểu diễn mà giữ ngữ nghĩa cần thiết.
10. **“Có stack trace dòng N là biết chắc lỗi ở dòng N của source mới nhất.”** Không: phải đối chiếu build/version và biến đổi class.

## 11. Bài tập tự kiểm tra

1. Một `LineNumberTable` ghi `line 18: 6`. Số 6 là gì? **Offset bytecode trong mảng code[] của method**, không phải cột ký tự hoặc địa chỉ RAM.
2. `LocalVariableTable` ghi `Start=3, Length=8, Slot=1, Name=total, Signature=I`. Dữ liệu đó cho biết giá trị total khi PC=5 không? **Không**; chỉ biết biến được mô tả ở khoảng `[3,11)`, slot 1, kiểu int.
3. Hai entry cùng slot 1 nhưng có khoảng sống khác nhau có nhất thiết là một biến nguồn không? **Không**; compiler có thể dùng lại slot.
4. Dùng `javac -g:none` khiến `java Demo` không chạy nữa không? **Không**, nếu class file vẫn hợp lệ và đủ dependency.
5. Tại sao decompiler không chắc biết người viết gõ `4 + 5` hay `9`? Vì compiler có thể constant-fold cả hai về cùng bytecode.
6. `MethodParameters` và `LocalVariableTable` có thay thế hoàn toàn cho nhau không? **Không**; một bên mô tả metadata parameter, bên kia mô tả các local variables theo vùng code.
7. Tại sao có tên biến trong LVT mà debugger vẫn có thể nói “optimized out”? Vì **metadata bytecode không bảo đảm giá trị đó luôn còn ở một vị trí đọc được sau JIT tối ưu**.
8. Để đối chiếu stack trace production, cần nguồn mới nhất hay **nguồn đúng với build đã chạy**? Cần **đúng build**.

## 12. Tài liệu chuẩn

- JVM Specification Java SE 17, **The Class File Format**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- JVMS §4.7.12, **LineNumberTable Attribute**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.12
- JVMS §4.7.13, **LocalVariableTable Attribute**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.13
- JVMS §4.7.14, **LocalVariableTypeTable Attribute**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.14
- JDK `javap` tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- JDK `javac` options (`-g`, `-parameters`, `--release`): https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html

**Kết luận kỹ thuật:** `LineNumberTable` nối **vị trí bytecode với dòng nguồn**; `LocalVariableTable` nối **scope/slot bytecode với tên và kiểu local variable**. Hai bảng giúp debug, nhưng **không lưu nguyên văn mã nguồn**. Decompiler có thể dựng mã tương đương để tham khảo, chứ không thể từ những metadata ấy bảo đảm khôi phục đúng comment, cấu trúc và câu chữ source Java ban đầu.
