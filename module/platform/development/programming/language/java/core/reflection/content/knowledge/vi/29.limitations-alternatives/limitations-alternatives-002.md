# Tên biến cục bộ và thông tin debug không phải API Core Reflection thông thường

## 1. Vấn đề: Reflection thấy được gì trong một phương thức?

Giả sử một phương thức Java có **tham số** `owner`, `amount` và **biến cục bộ** `fee`, `label`:

~~~java
public static int compute(String owner, int amount) {
    int fee = amount / 10;
    String label = owner + ":" + fee;
    return label.length();
}
~~~

Có ba câu hỏi rất khác nhau:

1. **Phương thức nhận những kiểu tham số nào?** Core Reflection trả lời bằng `Method.getParameterTypes()`, `getGenericParameterTypes()`, `getParameterCount()`.
2. **Tên khai báo của tham số là gì?** `Method.getParameters()` trả về các `Parameter`, nhưng tên gốc `owner`, `amount` chỉ đáng tin khi class file có metadata tương ứng, thường do `javac -parameters` tạo.
3. **Trong thân phương thức có các biến cục bộ nào, tên và giá trị của chúng là gì?** **Không có API `Method.getLocalVariables()` trong Core Reflection**. Tên `fee`, `label` có thể được compiler ghi trong thông tin debug tùy chọn của bytecode, nhưng API `java.lang.reflect` thông thường không cung cấp danh sách đó và cũng không cho đọc giá trị local của một stack frame đang chạy.

Sự khác nhau này quan trọng khi viết công cụ inspector, serializer, dependency injection, framework gọi method động, debugger hoặc công cụ phân tích bytecode. Người học cần tách rõ **cấu trúc của class**, **chữ ký phương thức**, **metadata debug** và **trạng thái stack frame tại một thời điểm**.

Bài học chỉ tập trung vào Java Core và giới hạn Reflection; các công cụ bytecode/debug chuyên dụng được giới thiệu để chọn giải pháp khi cần, không triển khai debugger hoàn chỉnh.

## 2. Field, tham số và biến cục bộ là ba loại dữ liệu khác nhau

| Thành phần | Khai báo điển hình | Nơi tồn tại/ý nghĩa | API phù hợp |
| --- | --- | --- | --- |
| **Instance field** | `private String name;` trong class | Trạng thái của một object | `Class.getDeclaredFields()`, `Field.get(obj)` theo quyền |
| **Static field** | `static int counter;` trong class | Trạng thái gắn với class | `Class.getDeclaredFields()`, `Field.get(null)` theo quyền |
| **Formal parameter** | `String owner, int amount` trong khai báo method | Đầu vào được khai báo trong **chữ ký method/constructor** | `Executable.getParameters()`, `Parameter`, `Method.getParameterTypes()` |
| **Local variable** | `int fee = ...;` trong thân method | Biến theo phạm vi ngôn ngữ trong thân method; có thể được biểu diễn tại local slot/stack hoặc tối ưu hóa | Không có API Core Reflection thông thường để liệt kê/đọc như `Field` |
| **Temporary value** | Giá trị trung gian trong phép tính bytecode | Không nhất thiết có tên source hoặc vị trí lưu ổn định | Công cụ bytecode/debug đặc thù, nếu có bằng chứng phù hợp |

**`Field` chỉ mô tả field**, không đại diện cho `int fee` hay `String label` trong method. Do đó, `getDeclaredFields()` không phải giải pháp “quét tất cả biến” trong class.

**`Parameter` mô tả tham số được khai báo của một `Executable`** (`Method` hoặc `Constructor`), không mô tả mọi local variable trong thân method. Dù biến `fee` được dùng để tính toán, nó không xuất hiện trong `getParameters()`.

**Một runtime local cũng không tương đương một “ô nhớ cố định”.** JVM có khái niệm local-variable array của mỗi frame, nhưng việc ánh xạ tên biến source vào slot phụ thuộc compiler, phạm vi bytecode, tối ưu hóa và thông tin debug tùy chọn; không thể suy ra một cách phổ quát từ API Reflection.

## 3. Core Reflection truy cập metadata tham số đến đâu?

Ví dụ API:

~~~java
Method method = Example.class.getDeclaredMethod(
        "compute", String.class, int.class);

Class<?>[] types = method.getParameterTypes();
Parameter[] parameters = method.getParameters();
~~~

Đây là đoạn minh họa cần các import `java.lang.reflect.Method` và `java.lang.reflect.Parameter` cùng class `Example` chứa method tương ứng; ví dụ runnable đầy đủ nằm ở phần sau.

Những API đáng nắm:

| API | Trả về | Điều không thể suy ra |
| --- | --- | --- |
| `Method.getName()` | Tên method | Không cho tên các biến trong thân method |
| `Method.getParameterCount()` | Số tham số được mô tả trong method descriptor | Không cho tên local |
| `Method.getParameterTypes()` | Các `Class<?>` ứng với kiểu tham số runtime | Không giữ đầy đủ generic arguments |
| `Method.getGenericParameterTypes()` | Metadata kiểu generic được khai báo khi có | Không phải metadata local variables |
| `Method.getParameters()` | Mảng `Parameter` theo thứ tự tham số | Không có nghĩa tên khai báo luôn được lưu |
| `Parameter.getName()` | Tên tham số từ metadata nếu có; có thể là tên tổng hợp `arg0`, `arg1` | Không bảo đảm là tên trong mã nguồn |
| `Parameter.isNamePresent()` | `true` nếu class file có tên cho tham số đó trong **MethodParameters** | Không chứng minh thông tin debug của local có mặt |
| `Parameter.getType()` | Kiểu thô runtime của tham số | Không cho giá trị local |
| `Parameter.isSynthetic()`, `isImplicit()` | Cờ mô tả tham số do compiler tạo/ngầm định nếu được ghi nhận | Không phải phép đo mọi biến tạm trong thân method |

**Quy tắc an toàn:** chỉ hiển thị `getName()` như tên tham số gốc khi `isNamePresent()` trả **true**. Nếu `false`, có thể nhận `arg0`, `arg1`… theo vị trí. Các tên này hữu ích cho hiển thị fallback nhưng không nên xem là hợp đồng nghiệp vụ ổn định.

Cờ `-parameters` dành riêng cho việc lưu tên tham số phương thức/constructor trong class file để Reflection đọc. Không suy từ việc stack trace có số dòng rằng tên tham số đã được lưu.

## 4. Ví dụ Java 17+ có thể chạy và so sánh hai cách biên dịch

Lưu nguyên văn chương trình thành **LocalNameDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class LocalNameDemo {
    public static int compute(String owner, int amount) {
        int fee = amount / 10;
        String label = owner + ":" + fee;
        return label.length();
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        Method method = LocalNameDemo.class.getDeclaredMethod(
                "compute", String.class, int.class);

        System.out.println("method=" + method.getName());
        System.out.println("parameters=" + method.getParameterCount());

        for (Parameter p : method.getParameters()) {
            System.out.println("param=" + p.getName()
                    + ", present=" + p.isNamePresent());
        }

        System.out.println(
                "return=" + method.getReturnType().getSimpleName());
        System.out.println("result=" + compute("Lan", 20));
    }
}
~~~

**Lượt A — biên dịch với cấu hình `javac` mặc định, không bật `-parameters`:**

~~~bash
javac -encoding UTF-8 LocalNameDemo.java
java LocalNameDemo
~~~

Đầu ra của class được biên dịch **không có MethodParameters chứa tên tham số**:

~~~text
method=compute
parameters=2
param=arg0, present=false
param=arg1, present=false
return=int
result=5
~~~

**Lượt B — biên dịch lại cùng tệp với `-parameters`:**

~~~bash
javac -encoding UTF-8 -parameters LocalNameDemo.java
java LocalNameDemo
~~~

Đầu ra:

~~~text
method=compute
parameters=2
param=owner, present=true
param=amount, present=true
return=int
result=5
~~~

`result=5` vì `fee=20/10=2`, chuỗi `"Lan:2"` có năm ký tự.

Trong cả hai lượt, **Core Reflection vẫn nhận đúng số lượng và kiểu tham số**, vẫn tìm được method bằng `getDeclaredMethod("compute", String.class, int.class)`, và `compute` vẫn chạy như nhau. Thứ thay đổi là **tên tham số được lưu trong class file và hiển thị qua Parameter**.

Quan trọng hơn, dù đã bật `-parameters`, chương trình **không có** một lệnh `method.getLocalVariables()` để liệt kê `fee`, `label` qua Reflection. Đây là hai biến nằm **trong thân method**, khác vị trí metadata của `owner`, `amount`.

**Điều kiện để so sánh đúng:** biên dịch lại thật sự cùng class vào thư mục đang chạy và không dùng file `.class` cũ trong classpath. Các build tool/IDE có thể bật `-parameters` hoặc các tùy chọn compiler theo cấu hình dự án; trong bài thực hành này dùng trực tiếp `javac` với tùy chọn như ghi ở trên.

## 5. Thông tin debug trong bytecode: LocalVariableTable

Class file có thể chứa các attribute tùy chọn phục vụ debug. Với tên biến cục bộ, thành phần thường gặp là **LocalVariableTable** nằm trong thuộc tính **Code** của method.

Một entry của **LocalVariableTable** chứa thông tin như:

| Trường | Ý nghĩa |
| --- | --- |
| `start_pc` | Offset bytecode bắt đầu vùng sống được mô tả |
| `length` | Độ dài vùng bytecode nơi entry có ý nghĩa |
| `name_index` | Tham chiếu tên biến trong constant pool |
| `descriptor_index` | Tham chiếu mô tả kiểu JVM của biến |
| `index` | Slot trong local-variable array của frame |

Đây là **metadata gắn với một vùng bytecode**, không phải một tập giá trị luôn tồn tại và truy cập được từ object **Method**. Cùng một slot có thể được sử dụng lại cho biến khác khi phạm vi sống không chồng lên nhau; một biến trong source có thể không có entry phù hợp trong bytecode được tối ưu hoặc biến đổi.

Ngoài **LocalVariableTable**, class file có thể có **LocalVariableTypeTable** để mô tả chữ ký kiểu generic của một số biến. Sự xuất hiện của những bảng này phụ thuộc compiler, chế độ sinh debug và các bước biến đổi class file.

Các loại metadata hay bị lẫn:

| Attribute/cơ chế | Thông tin | Cách tạo/đọc phổ biến |
| --- | --- | --- |
| **MethodParameters** | Tên và cờ một số tham số method/constructor | `javac -parameters`; `Executable.getParameters()` |
| **LocalVariableTable** | Tên/kiểu/slot/vùng bytecode của local, có thể gồm tham số | `javac -g:vars` hoặc `-g`; xem `javap -l`, bytecode parser, debugger |
| **LocalVariableTypeTable** | Signature kiểu generic cho một số local variable | Debug metadata khi được phát hành |
| **LineNumberTable** | Ánh xạ bytecode offset sang dòng nguồn | `javac` debug lines; debugger và stack trace có thể tận dụng |
| **SourceFile** | Tên tệp nguồn | Debug source metadata |
| **StackMapTable** | Thông tin kiểu dùng cho bytecode verification | **Không** phải danh sách tên local source |

Những bảng này **không thay thế nhau**. Đặc biệt, **`-g:vars` không làm `Parameter.isNamePresent()` thành true** theo hợp đồng API `Parameter`: phương thức đó kiểm tra thông tin tên được khai báo qua **MethodParameters**, không dùng LocalVariableTable để tái tạo tên tham số.

## 6. Tùy chọn javac: -parameters khác -g:vars thế nào?

| Lệnh biên dịch | Tên tham số qua Core Reflection | LocalVariableTable |
| --- | --- | --- |
| `javac LocalNameDemo.java` | Thông thường `arg0`, `arg1`, `isNamePresent=false` | Mặc định `javac` không bật thông tin debug local variables |
| `javac -parameters LocalNameDemo.java` | `owner`, `amount`, `isNamePresent=true` | Không vì thế tự yêu cầu `LocalVariableTable` |
| `javac -g:vars LocalNameDemo.java` | Vẫn không có tên tham số qua `Parameter.isNamePresent()` nếu thiếu `-parameters` | Có thông tin debug local theo khả năng compiler |
| `javac -parameters -g:vars LocalNameDemo.java` | Có tên tham số | Có metadata local |
| `javac -g LocalNameDemo.java` | Không tự tương đương `-parameters` | Sinh đầy đủ thông tin debug, gồm local variables |
| `javac -g:none -parameters LocalNameDemo.java` | Vẫn có tên tham số nhờ `-parameters` | Không yêu cầu debug local variables |

**Lưu ý:** `-g:vars` chỉ chọn metadata cho local variables; nếu cần đồng thời số dòng/tệp nguồn, dùng `-g` hoặc tổ hợp phù hợp như `-g:lines,vars,source`.

Để trực tiếp quan sát cấu trúc trong bytecode, hãy chạy lần lượt:

~~~bash
javac -encoding UTF-8 -parameters -g LocalNameDemo.java
javap -v -p LocalNameDemo
javap -c -l -p LocalNameDemo
~~~

Trong `javap -v`, tìm vùng **MethodParameters** của method **compute**; trong phần **Code** của method, tìm **LocalVariableTable**. `javap -l` giúp liệt kê thông tin dòng và bảng local khi có. Dạng rút gọn minh họa sau cho thấy ý tưởng, **không phải bản sao nguyên vẹn tất cả dòng output**:

~~~text
MethodParameters:
  Name    Flags
  owner
  amount

LocalVariableTable:
  Start  Length  Slot  Name    Signature
  ...
  ...           ...   owner   Ljava/lang/String;
  ...           ...   amount  I
  ...           ...   fee     I
  ...           ...   label   Ljava/lang/String;
~~~

Các số `Start`, `Length`, `Slot` phụ thuộc bytecode compiler tạo ra. Không viết test dựa trên số slot và offset giả định ổn định giữa các bản JDK hoặc các tùy chọn compiler.

**Giải thích quan trọng:** nhìn thấy `fee` và `label` bằng công cụ đọc class file chứng minh bytecode có **metadata debug** về chúng. Điều đó **không tạo thêm phương thức** `getLocalVariables()` cho đối tượng Reflection **Method**, và **không có nghĩa có thể đọc giá trị của chúng từ mọi thời điểm hoặc thread**.

## 7. Tên biến và giá trị biến đang chạy là hai bài toán riêng

### Đọc tên biến từ class file

Một công cụ phân tích bytecode có thể đọc bảng **LocalVariableTable** nếu bảng tồn tại. Nó cần giải mã cấu trúc class file và ánh xạ local slot với phạm vi bytecode; đây là công việc của công cụ class-file/bytecode chứ không phải thao tác `Field.get`.

Nếu class được biên dịch thiếu debug metadata, đã bị strip, obfuscate hoặc biến đổi, tên local gốc có thể không còn. **Không thể bảo đảm khôi phục chính xác tên trong source chỉ từ bytecode**. Công cụ decompiler đôi khi đặt tên phỏng đoán; đó không phải tên gốc được chứng minh.

### Đọc giá trị local trong lúc phương thức đang thực thi

Giá trị runtime của local gắn với **stack frame** và thời điểm thực thi, không phải thuộc tính của class hay instance. Debugger cần dừng/quan sát đúng thread và frame rồi dùng cơ chế debug/VM thích hợp; nó còn phụ thuộc khả năng JVM, thông tin debug, trạng thái tối ưu hóa, phạm vi biến và quyền/khả năng kết nối.

Ví dụ trong debugger, `fee` có thể quan sát được khi execution đang dừng tại dòng sử dụng nó. Nhưng nếu method đã return, frame tương ứng không còn để lấy giá trị local như một field của object. `Method` không thể đọc lại giá trị `fee` chỉ nhờ biết tên method.

**Stack trace** cũng không phải dữ liệu local: `StackTraceElement` có tên class, method, tệp nguồn/dòng khi khả dụng, nhưng không chứa tên và giá trị mọi biến cục bộ. `StackWalker` cho khả năng duyệt frame metadata nâng cao, không phải API đọc tất cả local như debugger.

### Công cụ chuyên dụng khi thật sự cần

| Nhu cầu | Hướng công cụ | Giới hạn cần hiểu |
| --- | --- | --- |
| Hiển thị tên/kiểu tham số public API | Core Reflection `Method.getParameters()` + `-parameters` | Metadata tùy chọn, cần kiểm tra `isNamePresent()` |
| Phân tích danh sách local trong bytecode | `javap`, class-file parser; thư viện ASM khi dự án cần | Không bảo đảm debug metadata tồn tại |
| Dừng chương trình và xem stack frame/local | **JDI/JDWP**, IDE debugger | Có thể thiếu thông tin, giá trị phụ thuộc trạng thái frame, có quyền và phiên debug |
| Instrumentation/agent/VM tooling | **JVMTI**, agent chuyên dụng hoặc công cụ quan sát thích hợp | Phạm vi kỹ thuật cao, phụ thuộc năng lực VM và chính sách triển khai |
| Theo dõi giá trị phục vụ nghiệp vụ | Logging/tracing/telemetry do code chủ động xuất ra | Thiết kế dữ liệu cần ghi; tránh thu thập thông tin nhạy cảm |

Với **JDI** (Java Debug Interface), debugger có thể truy vấn local-variable metadata từ method và đọc giá trị ở stack frame khi hợp lệ; thiếu debug metadata có thể dẫn đến **AbsentInformationException**. Đây là API riêng cho debug, **không đồng nghĩa Core Reflection dùng trong ứng dụng thông thường**.

## 8. Hạn chế thực tế đối với tool sinh tự động

### Đừng dựa vào tên tham số khi chưa xác minh

Nếu viết router gọi method theo tên tham số, trình biên dịch không bật `-parameters` có thể chỉ cho `arg0`, `arg1`. Điều này đặc biệt dễ xảy ra khi thư viện được biên dịch ngoài tầm kiểm soát hoặc build pipeline không nhất quán.

Khi tên tham số quan trọng cho hợp đồng API, hãy:
1. Quy định rõ cờ compile cho source bạn kiểm soát.
2. Dùng `Parameter.isNamePresent()` để phát hiện thiếu metadata.
3. Xác định fallback hoặc báo lỗi cấu hình rõ ràng; không đoán tên tham số từ vị trí.
4. Cân nhắc annotation khai báo key ổn định (ví dụ annotation tự định nghĩa) khi đó thực sự là hợp đồng dữ liệu.

### Đừng biến debug metadata thành API hợp đồng

`LocalVariableTable` được thiết kế cho mục đích debug và có thể thiếu hoặc khác giữa các bản build. Không dùng `fee` hay `label` như key ổn định trong serializer, cấu hình, JSON hoặc giao diện người dùng.

Đổi tên local không làm thay đổi chữ ký method theo cách Reflection dùng để tra cứu `getDeclaredMethod`; nhưng nếu một tool phụ thuộc tên từ bytecode debug thì tool đó trở nên mong manh. Một compiler có thể loại bỏ hoặc thay đổi local khi tối ưu hóa, instrumentation cũng có thể viết lại metadata.

### Đừng kết luận metadata phản ánh tất cả source

Một local trong source có thể bị chia phạm vi, gộp slot hoặc không xuất hiện như một biến riêng biệt có thể quan sát. Một số biến do compiler sinh ra cũng có thể xuất hiện, trong khi biến từ source không còn tên. Chỉ dùng những gì class file thực tế ghi nhận; không khẳng định đầy đủ.

### Không cố truy cập local bằng setAccessible(true)

`AccessibleObject.setAccessible(true)` liên quan đến kiểm tra quyền truy cập **member Reflection** như field/method/constructor trong phạm vi được phép; nó không tạo API truy vấn local của một stack frame. Không có `Field` cho biến `fee` để áp dụng `Field.get`.

## 9. Các nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng | Cách kiểm chứng |
| --- | --- | --- |
| “`getDeclaredFields()` thấy mọi biến trong class” | Chỉ field được khai báo trên class đó; không liệt kê biến bên trong method | So sánh danh sách Field với source có `fee`, `label` |
| “`getParameters()` trả tên local variable” | Nó trả formal parameter của method/constructor | Xem `owner`, `amount` so với `fee`, `label` |
| “Có `-g` tức là `Parameter.isNamePresent()` chắc chắn true” | `-g` và `-parameters` là hai cơ chế metadata khác nhau | Compile hai cấu hình rồi chạy chương trình |
| “`-parameters` lưu tất cả biến cục bộ” | Nó lưu metadata tên tham số, không bật bảng debug local theo mục đích đó | Dùng `javap -v -p` |
| “`LocalVariableTable` có tên thì `Method` đọc được giá trị local” | Metadata bytecode khác dữ liệu một frame runtime | Kiểm tra API thực tế của `java.lang.reflect.Method` |
| “Stack trace sẽ cho tất cả local values” | Stack trace chứa vị trí gọi/metadata frame, không có danh sách giá trị local | In `new Exception().getStackTrace()` |
| “`arg0` là chắc chắn tên tác giả đặt” | Thường là tên fallback khi thiếu MethodParameters | Kiểm tra `isNamePresent()` |
| “Decompiler luôn khôi phục chính xác tên source” | Có thể tạo tên suy đoán khi thiếu debug metadata | So sánh class biên dịch với `-g:none` và `-g` |

## 10. Thực hành theo trình tự

**Bài 1 — Tên tham số:** chạy `LocalNameDemo` sau khi biên dịch không có `-parameters`, rồi bật cờ này. Ghi lại sự thay đổi của `getName()` và `isNamePresent()`; giải thích vì sao `getParameterCount()` không đổi.

**Bài 2 — Metadata debug:** biên dịch `-g:vars` mà không có `-parameters`. Dùng `javap -v -p` để tìm `LocalVariableTable`; chạy `LocalNameDemo` và giải thích vì sao `Parameter.isNamePresent()` vẫn có thể false.

**Bài 3 — Hai loại metadata cùng xuất hiện:** biên dịch `-parameters -g`, kiểm tra **MethodParameters** và **LocalVariableTable** trong `javap -v`. So sánh `owner`/`amount` với `fee`/`label` ở các bảng khác nhau.

**Bài 4 — Không có debug:** biên dịch `-g:none` rồi kiểm tra bằng `javap -l -p`. Nhận xét những thông tin bị thiếu, và vì sao ứng dụng vẫn chạy đúng dù không có tên local source.

**Bài 5 — Field so với local:** thêm `private int counter;` vào class, dùng `LocalNameDemo.class.getDeclaredFields()`. Chỉ ra field **counter** nhưng không có biến local **fee** hoặc **label**.

**Bài 6 — Thiết kế inspector:** viết hàm nhận `Method`, xuất tên method, danh sách kiểu tham số và tên tham số nếu `isNamePresent()`; nếu thiếu tên, in nhãn **parameter #0**, **parameter #1**. Không phụ thuộc tên fallback như thể đó là tên source.

## 11. Tự kiểm tra kiến thức

**Câu 1.** `Method.getParameters()` và `Class.getDeclaredFields()` có đọc được `fee` trong ví dụ không?  
**Đáp án:** Không. `fee` là local trong thân method; hai API trên mô tả formal parameters và field.

**Câu 2.** Vì sao `getName()` có thể là `arg0` ngay khi tên source là `owner`?  
**Đáp án:** Class file có thể thiếu MethodParameters ghi tên gốc; kiểm tra `isNamePresent()`.

**Câu 3.** Cờ `-parameters` khác `-g:vars` thế nào?  
**Đáp án:** `-parameters` lưu tên formal parameters cho Core Reflection; `-g:vars` lưu thông tin debug local variables trong bytecode.

**Câu 4.** Biết tên `label` từ `javap` có đủ để lấy giá trị hiện tại của nó bằng Reflection không?  
**Đáp án:** Không. Debug metadata không đồng nghĩa một frame đang tồn tại và không tạo API đọc giá trị local trong `java.lang.reflect`.

**Câu 5.** Nếu một framework cần key tên tham số ổn định thì nên làm gì?  
**Đáp án:** Kiểm soát build `-parameters`, xác thực metadata hoặc dùng annotation/metadata hợp đồng tường minh.

**Câu 6.** JDI và JVMTI thuộc cùng cấp API với Reflection thông thường không?  
**Đáp án:** Không. Chúng là cơ chế debugger/VM tooling chuyên biệt với điều kiện hoạt động và quyền riêng.

**Tiêu chí hoàn thành:** bạn giải thích được khác biệt **field – formal parameter – local variable**, chạy hai lần biên dịch cho kết quả `isNamePresent()` khác nhau, nhận diện **MethodParameters** và **LocalVariableTable** khi đọc bytecode, và biết khi nào cần debugger hoặc class-file tooling thay vì cố dùng Reflection.

## 12. Nguồn chuẩn để tra cứu

- [Java SE: `java.lang.reflect.Parameter` và `isNamePresent()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html) — ngữ nghĩa tên tham số theo MethodParameters.
- [Java SE: `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html) — API dùng chung cho Method và Constructor.
- [JDK `javac` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — tùy chọn `-parameters`, `-g`, `-g:vars`.
- [JVMS, Class File Format §4.7](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html) — MethodParameters, LocalVariableTable, LocalVariableTypeTable.
- [Java SE: `com.sun.jdi` package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/package-summary.html) — cơ chế debug ngoài Core Reflection.

Thông tin debug là nguồn dữ liệu hữu ích khi có mặt và được dùng đúng mục đích; **không phải cam kết rằng API Reflection mặc định có thể khôi phục tên hoặc giá trị của mọi local variable trong một phương thức Java**.