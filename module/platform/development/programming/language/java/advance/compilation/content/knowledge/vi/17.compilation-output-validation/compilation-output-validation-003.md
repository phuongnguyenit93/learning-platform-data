# Quan sát thông tin dòng, biến cục bộ và tên tham số trong class file Java

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **thông tin debug về dòng nguồn**, **tên và phạm vi biến cục bộ** và **metadata tên tham số method/constructor** trong file `.class`.
2. Sử dụng `javac -g`, `-g:lines`, `-g:vars`, `-g:source`, `-g:none` và `-parameters` đúng mục đích.
3. Kiểm chứng bằng `javap -l`, `javap -v`, `javap -c` và `java`, thay vì chỉ tin rằng các flag đã được áp dụng.
4. Nhận biết `LineNumberTable`, `LocalVariableTable`, `LocalVariableTypeTable`, `SourceFile` và `MethodParameters`, đồng thời hiểu **không phải thuộc tính nào cũng xuất hiện trong mọi file**.
5. Giải thích vì sao Java Reflection có thể biết số lượng/kiểu tham số nhưng trả tên `arg0`, `arg1` khi không có `-parameters`, kể cả khi class có `LocalVariableTable`.
6. Xử lý khác biệt giữa thông tin dùng cho debugger/stack trace, metadata đọc bằng Reflection, generic signature, annotation, tối ưu hóa compiler và class file đã bị biến đổi.
7. Thiết kế quy trình build có thể tái lập và xác minh artifact thực tế, không dựa vào source hoặc thiết lập IDE thay cho class file đang chạy.

Bài thuộc **kiểm chứng đầu ra của quá trình biên dịch Java**. Các ví dụ dùng JDK 17+ và chạy từ terminal, không cần framework hay IDE.

## 1. Thông tin nào thực sự nằm trong file .class?

Source Java chứa những thứ người lập trình quan tâm: tên file, dòng, biến, tên tham số, chú thích, biểu thức. Compiler biến source thành **bytecode và metadata**; không phải mọi chi tiết source đều cần để JVM chạy chương trình.

Xét source:

~~~java
public static String describe(String label, int count) {
    int doubled = count * 2;
    return label + ":" + doubled;
}
~~~

Đây là **method minh họa**, chưa phải class độc lập. Khi biên dịch, JVM cần biết method descriptor, kiểu tham số và thứ tự; nó không bắt buộc cần biết người lập trình đã đặt tên biến `doubled` hay tham số `label` như thế nào.

Do đó cần phân biệt:

| Thông tin | Class-file attribute thường gặp | Công dụng |
| --- | --- | --- |
| Tên source file | `SourceFile` | Hỗ trợ tên file trong diagnostic/stack trace |
| Map bytecode offset → dòng nguồn | `LineNumberTable` | Debugger, stack trace, breakpoint theo dòng |
| Biến cục bộ, tham số, tên và vùng bytecode có hiệu lực | `LocalVariableTable` | Trình gỡ lỗi và phân tích binary |
| Generic signature của biến cục bộ | `LocalVariableTypeTable` khi có | Thông tin generic để trình gỡ lỗi hiển thị kiểu giàu hơn |
| Tên tham số được lưu cho reflection | `MethodParameters` | `java.lang.reflect.Parameter` và một số framework |
| Descriptor của method | Cấu trúc method trong class file | JVM biết **kiểu và thứ tự** tham số ngay cả khi không có tên |
| Generic method/class signature | `Signature` khi cần | Thông tin generic; không đồng nghĩa với debug local names |
| Annotation trên tham số | Runtime-visible/invisible parameter annotation attributes tùy annotation | Tách biệt với tên tham số và bảng biến cục bộ |

Các attribute có thể vắng mặt tùy compiler options, loại declaration, cấu trúc code, target release và công cụ xử lý binary sau biên dịch. Không kết luận “compiler làm sai” chỉ vì một attribute không có trong một method không cần nó.

### 1.1 Dòng code và bytecode không có quan hệ một-một

Một dòng Java có thể tạo nhiều bytecode instructions. Ngược lại, compiler có thể sinh bytecode hỗ trợ thao tác mà source không có một dòng tương ứng rõ ràng.

`LineNumberTable` không chứa toàn bộ văn bản Java, chỉ ghi những cặp **start_pc → line_number** cho các vùng bytecode. Nó thường đủ để JVM mô tả lỗi ở dòng nào, nhưng không cho phép phục dựng toàn bộ source hay chính xác mọi cột/ký tự ban đầu.

### 1.2 Tên biến cục bộ không nằm trong descriptor

Trong JVM, slot local variable có thể được tham chiếu bằng index, ví dụ `iload_2`. Chữ `doubled` có ích với debugger, nhưng bytecode có thể chạy mà không cần biết tên đó. Thông tin tên biến chỉ tồn tại nếu compiler hoặc công cụ khác ghi/giữ attribute thích hợp.

### 1.3 Tên tham số dùng cho reflection là đường metadata khác

`MethodParameters` có thể lưu tên tham số như `label` và `count` trong declaration. Java Reflection sử dụng metadata này, chứ **không tự lấy tên từ `LocalVariableTable`**. Đó là lý do `-g` và `-parameters` giải quyết hai nhu cầu khác nhau.

## 2. Các tùy chọn biên dịch quan trọng

| Tùy chọn `javac` | Ý nghĩa | Thông tin thường có |
| --- | --- | --- |
| Không chỉ định `-g` | Compiler thường ghi dòng và tên file nguồn theo mặc định | `LineNumberTable`, `SourceFile` |
| `-g` | Yêu cầu sinh **toàn bộ thông tin debug** mà compiler hỗ trợ | Dòng, source, tên/phạm vi biến cục bộ |
| `-g:lines` | Chỉ phần debug line | `LineNumberTable` |
| `-g:vars` | Chỉ phần debug local variable | `LocalVariableTable` và metadata liên quan khi cần |
| `-g:source` | Chỉ phần debug source file | `SourceFile` |
| `-g:lines,vars,source` | Chỉ định rõ cả ba nhóm | Dòng, biến, file nguồn |
| `-g:none` | Không sinh thông tin debug được điều khiển bằng `-g` | Không mong có dòng/biến/source debug tables |
| `-parameters` | Lưu **tên tham số của method và constructor** | `MethodParameters` khi phù hợp |

**Điểm phải nhớ:**

- `-g` không đồng nghĩa `-parameters`.
- `-parameters` không tự bật toàn bộ `LineNumberTable` hay `LocalVariableTable`.
- `-g:none -parameters` là một kết hợp có chủ đích: không có debug tables nhưng vẫn có metadata tên tham số.
- `-g:vars` không tự bảo đảm `Parameter.isNamePresent() == true`.
- `--release 17` điều khiển mức ngôn ngữ, API nền tảng và class-file target; nó **không thay thế** các cờ debug/parameter metadata.

Tùy chọn và mặc định có thể phụ thuộc compiler implementation. Với các lệnh trong bài, `javac` là compiler đi kèm JDK 17+.

### 2.1 `-g` có lưu giá trị runtime của biến không?

Không. `LocalVariableTable` chứa metadata như **tên, kiểu và phạm vi sống tương ứng vùng bytecode**, không chứa giá trị của biến trong từng thời điểm chạy. Giá trị chỉ tồn tại khi chương trình thực thi, ở stack frame/heap theo mô hình JVM và tối ưu hóa của runtime.

Debugger có thể tận dụng metadata để hiển thị tên/kiểu và cố đọc giá trị đang tồn tại tại điểm dừng. Nhưng nếu biến đã hết phạm vi, bị optimized out, hoặc frame đã thay đổi, giá trị có thể không còn quan sát được.

### 2.2 `-parameters` có biến Java thành ngôn ngữ hỗ trợ named arguments không?

Không. Java không cho phép gọi method theo tên tham số như:

~~~java
// Đây là cú pháp Java KHÔNG HỢP LỆ:
describe(label: "job", count: 3);
~~~

Đoạn trên chỉ minh họa cú pháp **không hợp lệ**, không đưa vào project biên dịch.

`-parameters` phục vụ metadata: reflection, công cụ dependency injection, web binding, serialization và một số framework có thể tận dụng tên tham số. Nó không đổi cú pháp gọi method, signature bytecode hay cách Java overload resolution hoạt động.

## 3. Chuẩn bị ví dụ Java 17+ có thể chạy

Tạo một thư mục mới, ví dụ:

~~~text
classfile-metadata-demo/
├── DebugInfoDemo.java
└── out/
    ├── default/
    ├── debug/
    ├── vars/
    ├── params/
    ├── all/
    └── none/
~~~

Chỉ cần một file nguồn Java; các output directories được tách để **không trộn class file từ những lần biên dịch khác nhau**.

Kiểm tra công cụ:

~~~bash
javac -version
java -version
javap -version
~~~

Nếu muốn quan sát tương thích Java 17 trên JDK mới hơn, dùng `--release 17` trong các lệnh. Nếu `javac` báo không hỗ trợ release 17, kiểm tra JDK hiện dùng.

### 3.1 Tạo output directories

**Linux/macOS Bash/Zsh:**

~~~bash
mkdir -p out/default out/debug out/vars out/params out/all out/none
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/default, out/debug, out/vars, out/params, out/all, out/none | Out-Null
~~~

Từ đây, mọi lệnh được chạy tại thư mục gốc chứa `DebugInfoDemo.java`.

### 3.2 Mã nguồn hoàn chỉnh — DebugInfoDemo.java

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public final class DebugInfoDemo {

    private DebugInfoDemo() {
    }

    public static String describe(String label, int count) {
        int doubled = count * 2;
        String result = label + ":" + doubled;
        return result;
    }

    public static void main(String[] args) throws Exception {
        System.out.println(describe("job", 3));

        Method method = DebugInfoDemo.class.getDeclaredMethod(
                "describe", String.class, int.class);

        for (Parameter parameter : method.getParameters()) {
            System.out.println(
                    "parameter=" + parameter.getName()
                    + ", present=" + parameter.isNamePresent());
        }
    }
}
~~~

Đây là **chương trình độc lập** dành cho Java 17+.

- `describe` có hai tham số `label` và `count`.
- Biến cục bộ `doubled`, `result` được dùng thực tế nên có ý nghĩa trong bảng tên biến khi compile với `-g`.
- `main` in một kết quả nghiệp vụ ổn định, sau đó dùng Reflection lấy method `describe(String,int)`.
- `getDeclaredMethod(...)` dùng kiểu tham số và tên method để tìm declaration; nó không yêu cầu tên tham số được lưu.
- `Parameter.getName()` có thể trả tên nguồn thật hoặc tên tổng hợp `arg0`, `arg1`.
- `isNamePresent()` mới là cách rõ ràng để kiểm tra tên có metadata hợp lệ; không dựa vào việc chuỗi có bắt đầu `arg` hay không.

## 4. Thí nghiệm A — Biên dịch mặc định, quan sát dòng nguồn

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d out/default DebugInfoDemo.java
java -cp out/default DebugInfoDemo
~~~

Stdout của chương trình nếu không bật `-parameters`:

~~~text
job:6
parameter=arg0, present=false
parameter=arg1, present=false
~~~

`job:6` được tạo từ `count=3` và `doubled=6`. Hai tên `arg0`, `arg1` là fallback do Reflection cung cấp khi thông tin tên không hiện diện, **không phải bằng chứng source code đã đặt tên hai tham số như vậy**.

### 4.1 Xem LineNumberTable

~~~bash
javap -classpath out/default -l -p DebugInfoDemo
~~~

`-l` cho `javap` hiển thị bảng dòng nguồn và biến cục bộ **nếu có**; `-p` cho xem cả member private. Trong output mặc định của `javac`, bạn thường thấy các mục `LineNumberTable` cho method có bytecode.

Kiểm tra thêm:

~~~bash
javap -classpath out/default -v -p DebugInfoDemo
~~~

`-v` là verbose, hiển thị constant pool, attributes, code và chi tiết metadata. Tìm:

~~~text
SourceFile:
LineNumberTable:
~~~

Đây là **các nhãn cần tìm**, không phải toàn bộ output `javap`. Thứ tự constant-pool index, offset, số dòng và cách in từng thuộc tính thay đổi theo source/phiên bản compiler.

### 4.2 Vì sao không thấy LocalVariableTable?

Mặc định `javac` thông thường sinh thông tin dòng/file nguồn nhưng **không yêu cầu toàn bộ local-variable debug info**. Bởi vậy `javap -l` có thể hiển thị `LineNumberTable` nhưng không có `LocalVariableTable` chứa `doubled` hay `result`.

Không nhầm điều này với biến không tồn tại. Program đã sử dụng biến khi chạy; chỉ là tên biến **không được lưu dưới dạng metadata debug**.

### 4.3 Reflection nhận tên tham số hay không?

Chương trình đã trả `present=false`. Vì vậy runtime không có metadata tên tham số nguồn theo cách mà `java.lang.reflect.Parameter` tin cậy. Compiler vẫn biết `describe` nhận `String` và `int`; thông tin kiểu nằm trong method descriptor và được Reflection cung cấp.

**Kết luận A:** metadata dòng mặc định không kéo theo metadata local variable hoặc tên tham số reflection.

## 5. Thí nghiệm B — Bật -g để nhìn biến cục bộ

Biên dịch lại **từ source gốc** sang output riêng:

~~~bash
javac --release 17 -encoding UTF-8 -g -d out/debug DebugInfoDemo.java
javap -classpath out/debug -l -p DebugInfoDemo
~~~

Trong method `describe`, `javap` sẽ có mục `LocalVariableTable`, với các hàng chỉ ra tên như:

~~~text
label
count
doubled
result
~~~

Đây là **các tên cần tìm trong bảng**, không phải bốn dòng stdout hay toàn bộ output chính xác. Bảng thật thường có các cột `Start`, `Length`, `Slot`, `Name` và `Signature`.

Một số quan sát:

- Trong method static `describe`, các tham số và biến cục bộ dùng các local variable slots theo JVM.
- Tên `label` và `count` có thể xuất hiện trong `LocalVariableTable` khi bật `-g`.
- Tên `doubled` và `result` có thể xuất hiện cùng phạm vi bytecode nơi chúng hợp lệ.
- `LocalVariableTable` không thay `MethodParameters`; hai nguồn metadata có mục đích khác nhau.

### 5.1 Thử chạy bản -g

~~~bash
java -cp out/debug DebugInfoDemo
~~~

Stdout vẫn là:

~~~text
job:6
parameter=arg0, present=false
parameter=arg1, present=false
~~~

Đây là thí nghiệm quan trọng: **`-g` cho debugger tên biến, nhưng Reflection vẫn không nhận tên tham số nguồn** khi không có `-parameters`. Không có mâu thuẫn; chúng đọc những class-file attributes khác nhau.

### 5.2 Bảng LocalVariableTable nói gì?

Một hàng `LocalVariableTable` biểu diễn đại ý:

~~~text
Start   Length   Slot   Name       Signature
...     ...      ...    doubled    I
...     ...      ...    result     Ljava/lang/String;
~~~

Dấu `...` ở đây có nghĩa **offset bytecode thay đổi theo compiler**, không phải dòng output bắt buộc; bảng chỉ mô tả dạng thông tin.

- `Start` và `Length` xác định khoảng bytecode mà entry có ý nghĩa.
- `Slot` là local variable index trong frame JVM.
- `Name` là tên được compiler lưu.
- `Signature` ở bảng này thường là descriptor kiểu, ví dụ `I` cho `int` hoặc `Ljava/lang/String;` cho `String`.
- Với method instance, slot 0 thường là `this`; với method static, không có `this` parameter của instance.
- Hai biến có phạm vi sống không chồng lấn có thể tái sử dụng cùng một slot; không suy luận rằng mỗi tên biến luôn chiếm slot riêng toàn bộ thời gian.

Đừng biến offset trong `LocalVariableTable` thành số dòng nguồn. Chúng mô tả **vùng bytecode**, còn `LineNumberTable` liên hệ bytecode với dòng Java.

### 5.3 LocalVariableTypeTable liên quan generic type

Với code có biến cục bộ generic (ví dụ `List<String>`) và khi compiler lưu thông tin phù hợp, có thể thấy `LocalVariableTypeTable` để biểu diễn generic signature giàu hơn raw descriptor trong `LocalVariableTable`.

Điều này **không** có nghĩa mọi class phải có `LocalVariableTypeTable` sau `-g`. Nếu method không có biến local generic cần signature bổ sung, attribute đó có thể vắng mặt.

`LocalVariableTypeTable` phục vụ local debug metadata; đừng nhầm nó với method/class `Signature` dùng mô tả generic declaration.

## 6. Thí nghiệm C — Chỉ lưu tên biến bằng -g:vars

Biên dịch:

~~~bash
javac --release 17 -encoding UTF-8 -g:vars -d out/vars DebugInfoDemo.java
javap -classpath out/vars -l -p DebugInfoDemo
~~~

Bạn sẽ tìm thấy `LocalVariableTable` cho code phù hợp. Nhưng vì chỉ yêu cầu `vars`, **không nên trông chờ `LineNumberTable` hoặc `SourceFile` được bật qua nhóm debug khác**.

Để sinh đầy đủ ba nhóm theo cách tường minh:

~~~bash
javac --release 17 -encoding UTF-8 -g:lines,vars,source -d out/vars DebugInfoDemo.java
~~~

Lệnh cuối ghi lại output ở cùng thư mục `out/vars`, nên chỉ chạy nó **sau khi đã kiểm tra bản -g:vars**, hoặc dùng một thư mục mới nếu muốn giữ nguyên hai phiên bản để so sánh. Nó minh họa cú pháp phối hợp tên nhóm; không phải bước cần thực hiện để hoàn tất thí nghiệm C.

### 6.1 Dùng từng nhóm debug riêng

| Flag | Câu hỏi muốn trả lời |
| --- | --- |
| `-g:lines` | Có thể liên hệ bytecode với dòng source không? |
| `-g:source` | Có lưu thông tin tên source file không? |
| `-g:vars` | Có tên/phạm vi local variables để debug không? |
| `-g:lines,vars,source` | Có thể có cả ba loại thông tin không? |
| `-g:none` | Khi bỏ debug metadata, output/stack trace thay đổi ra sao? |

Đây là những lựa chọn của **compiler**, không phải chỉ định `javap` cần ẩn/hiện gì. `javap` chỉ đọc attribute thực sự có trong class file.

## 7. Thí nghiệm D — Bật -parameters để Reflection nhìn thấy tên

Biên dịch output riêng:

~~~bash
javac --release 17 -encoding UTF-8 -parameters -d out/params DebugInfoDemo.java
java -cp out/params DebugInfoDemo
~~~

Stdout:

~~~text
job:6
parameter=label, present=true
parameter=count, present=true
~~~

Dòng đầu không đổi vì hành vi chạy method không phụ thuộc tên tham số. Hai dòng sau đổi vì `MethodParameters` lưu tên declaration.

### 7.1 Kiểm chứng MethodParameters bằng javap

~~~bash
javap -classpath out/params -v -p DebugInfoDemo
~~~

Tìm trong method `describe`:

~~~text
MethodParameters:
  Name                           Flags
  label
  count
~~~

Đây là **trích đoạn mang tính định hướng**, không bảo đảm khoảng trắng/cột output luôn giống hệt. Điều quan trọng là tên `label` và `count` thuộc mục `MethodParameters` của method `describe`.

Mục `MethodParameters` có thể chứa cả các flags mô tả synthetic/mandated parameters tùy declaration; đừng giả định mọi class/method đều chỉ có các tham số người viết thấy trong source.

### 7.2 Tại sao -parameters không thay thế -g?

Hãy chạy:

~~~bash
javap -classpath out/params -l -p DebugInfoDemo
~~~

Trong ví dụ dùng `-parameters` mà không `-g`, bạn thường **không** có `LocalVariableTable` cho biến `doubled` và `result`, bởi `-parameters` không yêu cầu compiler lưu tên local variables. Mục `MethodParameters` được xem bằng `javap -v` chứ không phải suy ra từ `javap -l`.

Trường hợp điển hình:

- Reflection in `label` và `count`.
- Debugger chưa chắc thấy tên `doubled` và `result` nếu không có `LocalVariableTable`.
- Stack trace vẫn có thể có line number vì debug lines mặc định vẫn được sinh bởi javac.

**Kết luận D:** metadata tên tham số cho Reflection độc lập với debug info của local variables.

## 8. Thí nghiệm E — Kết hợp -g và -parameters

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 -g -parameters -d out/all DebugInfoDemo.java
javap -classpath out/all -v -p DebugInfoDemo
java -cp out/all DebugInfoDemo
~~~

Trong class file bạn có thể kiểm chứng:

- `SourceFile` cho tên source.
- `LineNumberTable` cho bytecode-line mapping.
- `LocalVariableTable` cho các biến `doubled`, `result` và thông tin local phù hợp.
- `MethodParameters` cho tên `label`, `count`.

Stdout:

~~~text
job:6
parameter=label, present=true
parameter=count, present=true
~~~

Đây là lựa chọn thuận tiện khi đang **debug bằng tên local variables** và đồng thời muốn **framework/reflection đọc được tên tham số nguồn**.

### 8.1 Việc gì không được thay đổi bởi các flag này?

Đối với code `DebugInfoDemo` được biên dịch cùng cấp Java:

- Kết quả nghiệp vụ `job:6` không đổi.
- Kiểu tham số của `describe(String,int)` không đổi.
- Java method invocation không trở thành named-argument call.
- `-g` và `-parameters` không đưa giá trị biến runtime vào class file.
- `-parameters` không thêm một tham số runtime mới vào method.
- Các attributes bổ sung có thể làm class file lớn hơn, nhưng không phải bằng chứng thuật toán chạy nhanh/chậm hơn theo một công thức cố định.

## 9. Thí nghiệm F — -g:none nhưng vẫn có -parameters

Một phép thử rất hữu ích để chứng minh tính độc lập:

~~~bash
javac --release 17 -encoding UTF-8 -g:none -parameters -d out/none DebugInfoDemo.java
java -cp out/none DebugInfoDemo
javap -classpath out/none -v -p DebugInfoDemo
~~~

Stdout:

~~~text
job:6
parameter=label, present=true
parameter=count, present=true
~~~

`-g:none` yêu cầu loại bỏ metadata debug thuộc nhóm `-g`; tuy nhiên `-parameters` vẫn yêu cầu compiler lưu thông tin tên tham số. Vì thế có thể thấy `MethodParameters` nhưng không có `LineNumberTable`, `LocalVariableTable` và `SourceFile` do debug flags.

Nếu bạn cần bản hoàn toàn không yêu cầu debug metadata **và cũng không giữ tên tham số nguồn**, có thể biên dịch riêng:

~~~bash
javac --release 17 -encoding UTF-8 -g:none -d out/none DebugInfoDemo.java
~~~

**Lưu ý:** lệnh cuối ghi đè artifact trong `out/none` đã tạo bởi `-g:none -parameters`. Chỉ chạy nó sau khi đã quan sát và ghi lại bản trước, hoặc đổi output sang thư mục khác nếu muốn giữ cả hai để so sánh.

Sau khi biên dịch lại **không có `-parameters`**, Reflection sẽ trở về `arg0`/`arg1` và `isNamePresent()==false`.

## 10. Tổng hợp kết quả sáu cấu hình

| Output | Flag | `LineNumberTable` | `LocalVariableTable` | `MethodParameters` cho `describe` | Reflection names |
| --- | --- | --- | --- | --- | --- |
| `out/default` | Mặc định | Có (thường) | Không (thường) | Không | `arg0`, `arg1` |
| `out/debug` | `-g` | Có | Có | Không | `arg0`, `arg1` |
| `out/vars` | `-g:vars` | Không theo yêu cầu flag | Có | Không | `arg0`, `arg1` |
| `out/params` | `-parameters` | Có (mặc định) | Không (mặc định) | Có | `label`, `count` |
| `out/all` | `-g -parameters` | Có | Có | Có | `label`, `count` |
| `out/none` | `-g:none -parameters` | Không | Không | Có | `label`, `count` |

Bảng mô tả mục tiêu kiểm chứng với **javac chuẩn của JDK 17+**, source `DebugInfoDemo` và các lệnh cụ thể. Không coi đây là quy luật cho mọi tool sinh/biến đổi class file (Kotlin, Scala, obfuscator, bytecode instrumentation, ahead-of-time compiler...). Khi cần chắc chắn, dùng `javap` trên **artifact cuối cùng**.

Nếu đã chạy lệnh ghi đè `out/vars` hoặc `out/none` ở các mục trước, cần compile lại cấu hình ban đầu của cột đó rồi mới dùng bảng để so sánh.

## 11. Kiểm tra từng thuộc tính bằng javap

### 11.1 `javap -l`: bảng dòng và biến cục bộ

~~~bash
javap -l -p -classpath out/all DebugInfoDemo
~~~

`-l` yêu cầu hiển thị line/local-variable tables của class khi có. Với source/flag phù hợp, bạn thấy thông tin theo từng method.

**Không nên chỉ dùng `javap -l` để kiểm tra `MethodParameters`.** Bảng đó được thể hiện rõ trong verbose output.

### 11.2 `javap -v`: xem attributes và method metadata

~~~bash
javap -v -p -classpath out/all DebugInfoDemo
~~~

Tìm các nhãn:

~~~text
SourceFile
LineNumberTable
LocalVariableTable
MethodParameters
~~~

`-v` cũng in constant pool, method descriptors, class flags, bytecode metadata và nhiều attributes khác. Thông tin xuất hiện tùy class.

### 11.3 `javap -c`: bytecode giúp hiểu slot và instruction

~~~bash
javap -c -p -classpath out/all DebugInfoDemo
~~~

Trong method `describe`, có thể thấy instruction liên quan tham số và phép nhân (ví dụ `iload_1`, phép nhân với số 2) và ghép chuỗi theo cơ chế compiler JDK hiện dùng. Không cố định instruction sequence vì compiler có thể triển khai nối chuỗi khác nhau, đặc biệt trên các JDK hiện đại có `invokedynamic`.

`javap -c` trả bytecode, **không phải decompiler tái tạo chính xác Java source**. Kết hợp `-c` với `-l`/`-v` để liên hệ bytecode offsets, line map và tên local variables.

### 11.4 `javap -p` không làm lộ thông tin không tồn tại

`-p` (tương đương cách yêu cầu xem private members) giúp hiển thị cả constructor private của demo và các member không public. Nó không “phục hồi” tên local variable hay parameter name nếu class file không lưu những tên ấy.

Nếu bạn không thấy `MethodParameters`, `LocalVariableTable` hoặc `SourceFile`, hãy kiểm tra **compiler options, output directory và artifact** trước khi kết luận `javap` sai.

## 12. Stack trace và LineNumberTable

Khi chương trình ném exception, JVM có thể dùng metadata class file để in tên source file và số dòng. Điều này thường dựa trên `SourceFile` và `LineNumberTable`. Nếu thiếu thông tin, stack trace có thể chỉ hiện tên class/method và mô tả như `Unknown Source`.

### 12.1 Ví dụ ExceptionTraceDemo.java

~~~java
public final class ExceptionTraceDemo {
    public static void main(String[] args) {
        crash();
    }

    private static void crash() {
        throw new IllegalStateException("boom");
    }
}
~~~

Chạy với output riêng:

~~~bash
javac --release 17 -encoding UTF-8 -d out/default ExceptionTraceDemo.java
java -cp out/default ExceptionTraceDemo
~~~

Chương trình cố ý ném exception. Nội dung stderr sẽ có `IllegalStateException: boom` và stack frame cho `crash`/`main`, thường kèm tên file và line khi metadata có mặt. **Không cố định toàn bộ stack trace** vì file path, số dòng và định dạng có thể khác nếu source được sửa.

Sau đó thử:

~~~bash
javac --release 17 -encoding UTF-8 -g:none -d out/none ExceptionTraceDemo.java
java -cp out/none ExceptionTraceDemo
~~~

Lần này stack trace thường thiếu tên file/line vì các debug attributes không được sinh, và có thể hiển thị `Unknown Source`.

Lưu ý: hai lệnh trên dùng output đã có của `DebugInfoDemo` nhưng tạo **một class tên khác**. Không làm thay đổi `DebugInfoDemo.class`; dù vậy khi cần kiểm chứng chính xác một artifact, tốt nhất dùng output directory tách biệt cho từng phép thử lớn.

### 12.2 LineNumberTable không phải source map hoàn hảo

Ngay cả khi có thông tin dòng:

- Một dòng nguồn có thể sinh nhiều bytecode instructions.
- Nhiều biểu thức trên cùng một dòng có thể được gắn cùng line.
- Compiler có thể sinh code hỗ trợ cấu trúc ngôn ngữ mà không có mapping hoàn hảo từng ký tự.
- JIT có thể inline hoặc tối ưu hóa trong runtime; debugging values/frames phụ thuộc khả năng JVM tái cấu trúc trạng thái.
- Stack trace có thể không thể hiện mọi frame trong mọi tình huống chạy/tối ưu hóa hoặc lỗi asynchronous theo cùng một cách.

Vì vậy, `LineNumberTable` là thông tin debug hữu ích, không phải bản sao toàn bộ source.

## 13. Tên tham số, Reflection và constructor

### 13.1 API Reflection quan trọng

Một `java.lang.reflect.Parameter` có:

- `getName()`: chuỗi tên mà Reflection cung cấp.
- `isNamePresent()`: liệu tên thực sự hiện diện trong metadata class file theo API.
- `getType()`: kiểu raw của tham số.
- `getParameterizedType()`: thông tin generic type khi có.
- `isSynthetic()`, `isImplicit()`: một số thông tin đặc biệt của tham số do ngôn ngữ/compiler sinh.
- `getAnnotations()`: runtime-visible annotations trên tham số nếu có.

`isNamePresent()` quan trọng hơn so sánh tên với `arg0`: mã nguồn hợp lệ **có thể thật sự đặt tên một parameter là `arg0`**. Chỉ nhìn chuỗi không cho biết nó đến từ metadata hay fallback.

### 13.2 Method và constructor đều có parameter metadata

`-parameters` yêu cầu lưu tên tham số cho method và constructor khi phù hợp. Ví dụ một constructor:

~~~java
public final class Order {
    private final String id;

    public Order(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
~~~

Đây là **class Java độc lập** đặt trong `Order.java`, không phải class có `main`. Có thể kiểm tra bằng `javap -v -p Order` sau khi compile với `-parameters`.

Ví dụ driver `ConstructorProbe.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorProbe {
    public static void main(String[] args) throws Exception {
        Constructor<Order> c =
                Order.class.getDeclaredConstructor(String.class);

        for (Parameter p : c.getParameters()) {
            System.out.println(
                    p.getName() + ":" + p.isNamePresent());
        }
    }
}
~~~

Biên dịch cả hai source vào output mới:

~~~bash
javac --release 17 -encoding UTF-8 -parameters -d out/all Order.java ConstructorProbe.java
java -cp out/all ConstructorProbe
~~~

Stdout:

~~~text
id:true
~~~

Nếu compiler không lưu tên tham số, Reflection thường in `arg0:false`. Điều đó không ngăn constructor nhận `String` và tạo object.

### 13.3 Synthetic, implicit và mandated parameters

Một số cấu trúc Java có tham số ẩn hoặc tham số do compiler thêm, ví dụ:

- Constructor của non-static inner class có thể cần tham số biểu diễn outer instance.
- Constructor của enum có các tham số phục vụ tên và ordinal nội bộ.
- Các compiler khác nhau có thể sinh bridge/synthetic methods.
- Record constructors và cấu trúc ngôn ngữ đặc biệt có quy tắc riêng.

Khi phân tích các method/constructor này, không nên mặc định số lượng/tên tham số trong bytecode luôn giống đúng với source declaration mà bạn nhìn thấy. Dùng `Parameter.isImplicit()`, `isSynthetic()`, `Method.isBridge()` và các class-file flags phù hợp, đồng thời kiểm tra thực nghiệm.

**Không cần áp dụng những ngoại lệ này cho method `describe(String,int)`** trong demo: đó là một static method bình thường có đúng hai tham số do người viết khai báo.

### 13.4 Tên tham số không phải annotations hoặc generic metadata

- `-parameters` lưu tên; nó không tự quyết định `@Retention(RUNTIME)`.
- `Parameter.getAnnotations()` phụ thuộc annotation retention và class-file attributes liên quan.
- Generic signature của method có đường metadata khác, không phải `LocalVariableTable` hay `MethodParameters`.
- Việc thấy tên tham số không chứng minh code có validation annotations, doc comments hoặc giá trị default argument.

Đừng dùng `MethodParameters` để suy diễn thông tin mà class file chưa lưu.

## 14. Dùng -g:vars có lấy được tên tham số Reflection không?

Đây là một nhầm lẫn đặc biệt thường gặp. Hãy so sánh:

~~~bash
javac --release 17 -g -d out/debug DebugInfoDemo.java
java -cp out/debug DebugInfoDemo
~~~

với:

~~~bash
javac --release 17 -parameters -d out/params DebugInfoDemo.java
java -cp out/params DebugInfoDemo
~~~

Trong lần thứ nhất:

- Debugger/`javap -l` có thể thấy tên tham số như local variables trong `LocalVariableTable`.
- Reflection vẫn có thể trả `arg0`/`arg1` và `isNamePresent()==false`.

Trong lần thứ hai:

- Reflection trả `label`/`count` với `isNamePresent()==true`.
- Debug local names như `doubled`/`result` không được mặc định sinh chỉ vì có `-parameters`.

Hai công cụ nhìn vào **hai loại class-file attributes khác nhau**. Một số framework trước đây từng có cơ chế cố đọc local variable debug information để suy ra tên tham số, nhưng đừng nhầm các cơ chế tùy framework ấy với hợp đồng của Java Reflection `Parameter.isNamePresent()`.

## 15. IDE, Gradle, Maven và sự khác biệt cấu hình build

Trong IDE, nút Build/Run có thể dùng compiler setting riêng hoặc delegate sang Gradle/Maven. Vì vậy IDE hiển thị tên tham số không chứng minh binary phát hành đã biên dịch với `-parameters`. Debugger có thể tìm local variable names từ output của IDE, trong khi artifact build CI đã bị bỏ debug tables.

### 15.1 Gradle Groovy DSL

Ví dụ trong `build.gradle` của project Java:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
    options.debug = true
}
~~~

Đây là cấu hình Gradle Java plugin, **không phải chương trình Java độc lập**.

- `-parameters` yêu cầu compiler lưu parameter names.
- `options.debug = true` yêu cầu debug information; cách Gradle cụ thể truyền compiler arguments phụ thuộc phiên bản và cấu hình task.
- Nếu cần giới hạn debug info theo nhóm (lines/vars/source), xem compiler args của task và bảo đảm không có cờ xung đột.
- Với multi-project Gradle, kiểm tra các task tương ứng của từng module; đừng giả định chỉ một file build áp dụng cho toàn bộ artifacts.

Ví dụ Kotlin DSL trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
    options.debug = true
}
~~~

Đây cũng là **snippet cấu hình**, cần Gradle Java plugin phù hợp và JavaCompile task.

### 15.2 Maven Compiler Plugin

Trong `pom.xml`, một dạng cấu hình Maven Compiler Plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <parameters>true</parameters>
                <debug>true</debug>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là đoạn cấu hình trong **POM đầy đủ**; plugin và phiên bản cần hỗ trợ các phần tử được dùng. `parameters` và `debug` tương ứng hai nhu cầu khác nhau. Maven có thể có property/plugin configuration hoặc profile ghi đè; nên xem effective config.

### 15.3 Đừng chỉ nhìn sourceCompatibility hoặc release

`--release 17` hữu ích cho tính tương thích source/API/class-file, nhưng nó không tự chứng nhận `MethodParameters` có mặt. Một dự án cần runtime Java 17 **và** reflection parameter names thì phải kiểm tra đồng thời release và cờ `-parameters`.

### 15.4 Quy trình xác nhận artifact cuối

1. Xác định compiler/JDK thực tế dùng bởi IDE, Gradle, Maven hay CI.
2. Ghi chính xác compiler options.
3. Biên dịch ra **output directory sạch**.
4. Mở class/JAR **sẽ được phát hành** bằng `javap -v -p` và `javap -l`.
5. Kiểm tra `LineNumberTable`, `LocalVariableTable`, `MethodParameters` trên method quan tâm.
6. Chạy Reflection test bằng classpath trỏ đúng artifact cuối.
7. Nếu có obfuscation/shading/instrumentation, xem lại artifact **sau khi biến đổi**.
8. Tránh suy diễn từ class file của một build cũ nằm ở thư mục khác.

Một JAR có thể chứa class đã biên dịch với flags khác nhau, đặc biệt khi ghép nhiều module hoặc third-party dependencies. Kết luận “toàn bộ JAR có tên tham số” chỉ hợp lý nếu đã kiểm tra những class quan trọng.

## 16. Khi class file bị obfuscate hoặc strip metadata

Các công cụ shrink/obfuscate/bytecode transform có thể thay đổi tên class/method/field, xóa debug attributes, hoặc giữ/xóa `MethodParameters` tùy rules. Vì vậy output từ `javac -g -parameters` chưa chắc giữ nguyên metadata sau packaging.

### 16.1 Những hệ quả có thể quan sát

- Mất `LineNumberTable`: stack trace không còn số dòng nguồn hữu ích.
- Mất `SourceFile`: thiếu tên source file trong frame.
- Mất `LocalVariableTable`: debugger không đọc được tên local variables đã khai báo.
- Mất `MethodParameters`: Reflection `isNamePresent()` có thể trở lại false, framework phụ thuộc parameter name có thể lỗi.
- Tên class/member bị đổi: stack trace có thể khó đọc nếu không có mapping deobfuscation.

**Không phải mọi tool đều xóa các attribute theo cùng mặc định.** Đọc rule/tài liệu của chính tool, rồi kiểm chứng binary sau biến đổi bằng `javap`.

### 16.2 Metadata và quyền riêng tư

Tên local variable/parameter có thể tiết lộ một phần thuật ngữ nội bộ, logic kinh doanh hoặc tên miền dữ liệu. Nhưng bỏ debug info **không phải biện pháp bảo vệ bí mật**: bytecode vẫn có thể được phân tích và constants có thể còn trong class file.

Đừng lưu password/API key trong source rồi trông cậy `-g:none` để “che” chúng. Không đưa secrets vào artifact client khi không cần thiết.

### 16.3 Trade-off

Giữ metadata hỗ trợ stack trace/debugging và một số framework; lược bớt có thể giảm kích thước binary và lượng thông tin source lộ ra. Cấu hình nên dựa trên nhu cầu vận hành thực tế, chứ không mặc định “release build luôn phải xóa hết debug info” hoặc “mọi class đều bắt buộc bật -g”.

## 17. Các trường hợp ngoại lệ khi quan sát metadata

### 17.1 Source biên dịch không phải Java

Class file của Kotlin, Scala hoặc ngôn ngữ JVM khác có thể có thông tin dòng/biến/parameter theo quy tắc compiler riêng. Không giả định `javac -g` đã được dùng chỉ vì nhìn thấy `LineNumberTable`.

### 17.2 Generated code

Annotation processor có thể tạo Java source và compiler tạo class tương ứng. Thông tin dòng có thể trỏ vào **generated source**, không phải file do người dùng trực tiếp viết. Nếu cần source map ngược về declaration gốc, công cụ build/processor phải duy trì metadata phù hợp; `LineNumberTable` không tự biết quy tắc sinh mã.

### 17.3 Lambda và synthetic methods

Java compiler có thể tạo synthetic methods để triển khai lambda hoặc các cấu trúc ngôn ngữ. Những method này không nhất thiết ánh xạ một-một với source method do người viết khai báo. Metadata debug và tên tham số của synthetic method không nhất thiết giống ý nghĩa của declaration nguồn.

### 17.4 Compiler tối ưu hóa và phạm vi local variables

`LocalVariableTable` đánh dấu khoảng bytecode, không diễn tả mọi thời điểm runtime chính xác như một timeline giá trị. Các biến có thể tái sử dụng local slots hoặc bị tối ưu hóa ở runtime. Debugger có thể không hiển thị một biến ngoài phạm vi sống hoặc không thể lấy giá trị sau JIT optimization.

### 17.5 Có MethodParameters nhưng không có LineNumberTable

Đây **không phải file lỗi**. Nó có thể là kết quả hợp lệ của `-g:none -parameters`, hoặc do post-processing. Reflection có thể biết tên tham số ngay cả khi stack trace không có source line.

### 17.6 Có LineNumberTable nhưng không có tên tham số

Cũng hoàn toàn bình thường. Đây là trạng thái thường gặp của `javac` mặc định: stack trace có line number, nhưng Reflection `isNamePresent()==false` cho method không được biên dịch với `-parameters`.

## 18. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Reflection in `arg0`, `arg1` | Thiếu `MethodParameters` | Compile với `-parameters`, kiểm tra `javap -v` |
| `-g` rồi Reflection vẫn `isNamePresent=false` | Nhầm `LocalVariableTable` với `MethodParameters` | Thêm `-parameters`, compile sạch |
| `javap -l` không thấy tên local variables | Không có `-g:vars`/`-g` hoặc method không có metadata phù hợp | Kiểm tra `-g` và artifact |
| `javap -v` không thấy `SourceFile` | `-g:none`, `-g:vars` hoặc stripping | Build với `-g:source`/`-g` nếu cần |
| Stack trace hiện `Unknown Source` | Không có thông tin source/line tương ứng | Kiểm tra `SourceFile` và `LineNumberTable` |
| Một file có `MethodParameters`, file khác không | Khác compiler task/module/tool | Kiểm tra build options từng module |
| Debugger không xem được một biến | Scope, slot reuse, optimization hoặc thiếu debug info | Kiểm tra `LocalVariableTable` và điểm dừng |
| `javap` cho thấy khác với IDE | IDE và CLI đang dùng output khác nhau | Kiểm tra đường dẫn class/JAR thật |
| Biên dịch lại nhưng vẫn thấy metadata cũ | Output cũ/classpath thứ tự sai | Biên dịch ra thư mục mới, `javap -classpath` chính xác |
| Tên constructor parameter khác mong đợi | Synthetic/implicit parameters hoặc generated code | Dùng `Parameter.isSynthetic/isImplicit` và inspect binary |
| Class bị obfuscate mất tên | Post-processing xóa/đổi attributes | Dùng `javap` trên artifact sau obfuscation |
| `-g:vars` có tên `label` nhưng runtime vẫn `arg0` | Local variable metadata không phải reflection parameter metadata | Dùng `-parameters` |
| `javap` không thấy class | Sai classpath root hoặc qualified class name | Kiểm tra `-classpath` và file `.class` |
| JVM chạy được dù không có debug info | Debug attributes không thiết yếu cho thực thi bytecode | Không coi việc chạy được là bằng chứng có metadata |

### 18.1 Cách xác định class đang được JVM nạp

Trong tình huống có nhiều JAR/outputs cùng tên class, hãy xem classpath và thông tin class loading. Với HotSpot/JDK 17+, ví dụ:

~~~bash
java -Xlog:class+load=info -cp out/all DebugInfoDemo
~~~

Lệnh có thể in rất nhiều dòng log chứa tên class và nguồn nạp; chi tiết log phụ thuộc implementation. Hãy tìm `DebugInfoDemo` và đường dẫn binary, không dùng toàn bộ log làm output cố định.

### 18.2 Không nhầm việc xem metadata với sửa lỗi runtime

Một program có thể compile, chạy và trả đúng kết quả nhưng không có line names/local names. Ngược lại, file có đầy đủ debug tables vẫn có thể chứa bug hoặc thiếu dependency runtime. `javap` giúp **kiểm chứng những gì compiler đã ghi**, không bảo đảm tính đúng nghiệp vụ.

## 19. Câu hỏi thường gặp

### Q1. Vì sao `javap -l` có line nhưng không có local variables?

Vì mặc định `javac` thường sinh line/source info, còn tên local variables cần `-g` hoặc `-g:vars`. Kiểm tra lại flags và binary.

### Q2. `-parameters` có dùng cho private methods không?

Có thể lưu tên tham số của method/constructor bất kể access level khi phù hợp. Dùng `javap -v -p` để kiểm tra member private. Reflection vẫn cần quyền truy cập và quy tắc module tương ứng nếu muốn **invoke** private method; việc đọc metadata không tự cấp quyền thực thi.

### Q3. `isNamePresent()==false` nghĩa là parameter type cũng bị mất?

Không. Method descriptor vẫn xác định types và thứ tự. Reflection có thể biết số lượng/types mà không biết tên source.

### Q4. Có thể khôi phục tên biến chính xác từ bytecode không?

Không bảo đảm. Nếu compiler không lưu tên trong `LocalVariableTable` hoặc metadata tương tự, một decompiler có thể suy đoán tên, nhưng không thể đảm bảo khôi phục tên gốc.

### Q5. Có cần bật `-g` cho framework web dùng parameter binding?

Phụ thuộc framework. Với Java Reflection tiêu chuẩn, `-parameters` là cách trực tiếp để `Parameter.isNamePresent()` đúng. Framework khác có thể có cơ chế riêng. Không coi `-g` là thay thế chắc chắn cho `-parameters`.

### Q6. Có thể dùng `-parameters` đồng thời với `-g:none` không?

Có. Thí nghiệm F minh họa rằng parameter metadata có thể còn dù debug info bị loại bỏ.

### Q7. LocalVariableTable có lưu tên của mọi biến?

Không nhất thiết. Nó lưu entry phù hợp do compiler tạo và flag cho phép; tối ưu hóa, phạm vi sống, loại method và bytecode post-processing ảnh hưởng những gì còn thấy. Không có đảm bảo mọi declaration source có một entry đơn nhất, bất biến.

### Q8. Tại sao `getParameters()` trả hai object dù không có `-parameters`?

Vì method descriptor chứa hai kiểu tham số. `-parameters` cần để lưu tên/metadata bổ sung chứ không quyết định số lượng tham số.

## 20. Bài tập có đáp án

### Bài 1 — Dự đoán Reflection khi chỉ bật -g

Lệnh:

~~~bash
javac --release 17 -g -d out/debug DebugInfoDemo.java
java -cp out/debug DebugInfoDemo
~~~

**Đáp án:** `job:6` và hai dòng `parameter=arg0, present=false`; `parameter=arg1, present=false`. `-g` chủ yếu tạo line/source/local-variable debugging metadata, không tự tạo `MethodParameters`.

### Bài 2 — Dự đoán Reflection khi chỉ bật -parameters

~~~bash
javac --release 17 -parameters -d out/params DebugInfoDemo.java
java -cp out/params DebugInfoDemo
~~~

**Đáp án:** `parameter=label, present=true`; `parameter=count, present=true`. Metadata tên tham số được lưu; tên biến `doubled`/`result` chưa mặc định có trong LocalVariableTable nếu không bật `-g`.

### Bài 3 — Kiểm tra bảng dòng nguồn

Bạn cần xác minh class `DebugInfoDemo` có `LineNumberTable`. Lệnh nào thích hợp?

**Đáp án:** `javap -classpath out/default -l -p DebugInfoDemo` hoặc `javap -v -p -classpath out/default DebugInfoDemo`. Chỉ xem source `.java` không chứng minh class file đã lưu line metadata.

### Bài 4 — Khác nhau giữa source line và bytecode offset

`LocalVariableTable` có `Start=...`, `Length=...`; đó có phải là số dòng Java không?

**Đáp án:** Không. Chúng mô tả vùng bytecode có hiệu lực của biến. `LineNumberTable` mới ánh xạ từ bytecode position đến dòng source.

### Bài 5 — Bật cả debug và tham số

Cần hỗ trợ debugger xem tên local variables, đồng thời Reflection đọc tên tham số. Chọn cờ?

**Đáp án:** `-g -parameters` (hoặc `-g:lines,vars,source -parameters`). Sau compile phải xác minh bằng `javap -l/-v` và `Parameter.isNamePresent()`.

### Bài 6 — Vì sao stack trace thiếu số dòng?

Class được compile với `-g:none`. Vì sao stack trace thiếu line/source?

**Đáp án:** Compiler không lưu debug line/source attributes mà stack trace dùng để liên hệ bytecode với source. Chương trình vẫn có thể chạy bình thường.

### Bài 7 — Constructor

Biên dịch `Order` và `ConstructorProbe` với `-parameters`. Driver in gì?

**Đáp án:** `id:true` vì constructor parameter `id` được lưu trong metadata. Nếu không có cờ đó, ví dụ thông thường sẽ in `arg0:false`.

### Bài 8 — Tránh nhầm binary

`javap -v` thấy `MethodParameters` nhưng ứng dụng vẫn in `arg0`. Các bước điều tra?

**Đáp án:** Xác nhận cả `javap` và `java` dùng cùng class/JAR, đúng classpath root và thứ tự. Kiểm tra có class trùng tên, stale output hoặc bytecode transform không; dùng class-loading log khi cần.

### Bài 9 — Tác động của obfuscation

Một JAR đã qua shrinker không còn `LocalVariableTable`, trong khi output ban đầu có. Bạn có thể kết luận compiler không dùng `-g` không?

**Đáp án:** Không. Shrinker có thể xóa metadata. Kiểm tra artifact trước và sau transformation cùng rule của tool.

### Bài 10 — Metadata bảo mật

`-g:none` có bảo vệ hoàn toàn secrets trong bytecode không?

**Đáp án:** Không. Nó chỉ yêu cầu bỏ debug attributes; constants hoặc code logic còn có thể bị đọc từ class file. Không nhúng secrets vào artifact.

## 21. Checklist tự kiểm chứng

- [ ] Tôi biết `-g` và `-parameters` có mục đích khác nhau.
- [ ] Tôi đã biên dịch cùng một source vào output **riêng** cho từng cấu hình.
- [ ] Tôi dùng `javap -l` để quan sát `LineNumberTable` và `LocalVariableTable`.
- [ ] Tôi dùng `javap -v` để tìm `MethodParameters`.
- [ ] Tôi biết `SourceFile` và `LineNumberTable` hỗ trợ stack trace/debugger.
- [ ] Tôi phân biệt bytecode offset, local slot và dòng nguồn.
- [ ] Tôi đã xác minh Reflection với `getName()` và `isNamePresent()`.
- [ ] Tôi hiểu vì sao `-g` không đủ cho Java Reflection parameter names.
- [ ] Tôi đã thử `-g:none -parameters` để chứng minh tính độc lập.
- [ ] Tôi không suy ra tên biến/parameter từ stdout của chương trình.
- [ ] Tôi biết metadata có thể bị thay đổi bởi build tool/obfuscator.
- [ ] Tôi kiểm tra artifact **cuối cùng** thay vì chỉ kiểm tra source.
- [ ] Tôi hiểu debug metadata không chứa giá trị runtime và không thay đổi cú pháp gọi method.
- [ ] Tôi không nhầm sự có mặt của debug attributes với tính đúng của ứng dụng.

## Tài liệu tham khảo

- [Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-g`, `-g:...`, `-g:none`, `-parameters`.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): các tùy chọn `-l`, `-v`, `-c`, `-p`.
- [Java SE 17 — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): `getName()`, `isNamePresent()`.
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): `LineNumberTable`, `LocalVariableTable`, `MethodParameters` và các attributes khác.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): Reflection method metadata.

## Kết luận

**Có dòng nguồn, có tên biến cục bộ và có tên tham số là ba khả năng riêng biệt của class file.** `-g`/`-g:...` điều khiển debug information, còn `-parameters` cho phép lưu metadata tham số để Java Reflection đọc tên nguồn qua `Parameter.isNamePresent()`. Hãy kiểm tra `javap -l/-v` trên đúng binary, xác minh bằng chương trình Reflection chạy với đúng classpath, và lưu ý rằng post-processing có thể thay đổi những attributes ấy. Khi hiểu sự khác nhau giữa `LineNumberTable`, `LocalVariableTable` và `MethodParameters`, bạn sẽ chẩn đoán tốt hơn các tình huống stack trace thiếu dòng, debugger thiếu local names hoặc framework không lấy được tên tham số.