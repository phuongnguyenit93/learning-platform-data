# Đối chiếu source với bytecode bằng javap

Khi Java source được biên dịch, javac chuyển các câu lệnh, biểu thức và khai báo thành bytecode trong class file. Bytecode là dạng lệnh trung gian mà JVM nạp, kiểm tra và thực thi. Dùng javap để đọc bytecode và metadata giúp đối chiếu một đoạn source với những instruction mà compiler đã tạo ra.

Việc đối chiếu này hữu ích khi debug lỗi, tìm hiểu cách compiler xử lý một cấu trúc ngôn ngữ, kiểm tra lời gọi method, phân tích nhánh điều khiển hoặc xác minh artifact trước khi phát hành. Kết quả không phải bản dịch ngược chính xác của source: nhiều chi tiết trình bày đã mất, và compiler có thể sinh thêm cấu trúc không viết trực tiếp trong mã nguồn.

## 1. Source, bytecode và JVM liên hệ thế nào?

Quy trình cơ bản:

1. Developer viết source trong tệp `.java`.
2. `javac` phân tích cú pháp, kiểm tra kiểu và biên dịch source.
3. Compiler tạo class file `.class`, chứa bytecode và các attributes.
4. JVM nạp class file, kiểm tra bytecode, liên kết các tham chiếu và thực thi.
5. Trong lúc chạy, JIT compiler có thể tối ưu các đoạn code nóng thành mã máy.

Source mô tả ý định ở mức ngôn ngữ Java. Bytecode thể hiện các thao tác ở mức JVM như nạp biến, đọc field, gọi method, so sánh, nhảy, tạo object và trả kết quả.

Cần phân biệt hai giai đoạn tối ưu:

- `javac` chuyển source thành bytecode và có thể thực hiện một số biến đổi ở thời điểm biên dịch.
- JIT compiler tối ưu dựa trên hành vi thực tế lúc runtime, chẳng hạn inline method hoặc loại bỏ nhánh không cần thiết.

Vì vậy, bytecode từ `javap` không phải mã máy cuối cùng mà CPU chắc chắn sẽ thực thi.

## 2. Chuẩn bị source có thể đối chiếu

Tạo cấu trúc dự án:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── TraceExample.java
└── out/
~~~

Nội dung `src/com/example/TraceExample.java`:

~~~java
package com.example;

public class TraceExample {
    private static int adjust(int value) {
        if (value < 0) {
            return -value;
        }
        return value * 2;
    }

    public static void main(String[] args) {
        int input = args.length == 0 ? 4 : Integer.parseInt(args[0]);
        int result = adjust(input);
        System.out.println("result=" + result);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên và yêu cầu compiler sinh debug information:

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -g -d out src/com/example/TraceExample.java
~~~

Tùy chọn `-g` yêu cầu sinh đầy đủ debug information, bao gồm thông tin source, line number và local variable. `--release 17` chọn cú pháp, bytecode và Java Platform API của Java 17.

Chạy ứng dụng:

~~~powershell
java -cp out com.example.TraceExample
~~~

Kết quả:

~~~text
result=8
~~~

Với đối số `-3`:

~~~powershell
java -cp out com.example.TraceExample -3
~~~

Kết quả:

~~~text
result=3
~~~

Ví dụ này có một nhánh `if`, một phép tính số học, một lời gọi method và một phép nối chuỗi. Những cấu trúc đó giúp quan sát mối liên hệ giữa source và instruction JVM.

## 3. Lệnh javap để xem source tương ứng với bytecode

`javap` đọc class file và hiển thị khai báo, descriptor, bytecode hoặc metadata tùy tùy chọn.

Xem khai báo class:

~~~powershell
javap -classpath out com.example.TraceExample
~~~

Xem bytecode của các method:

~~~powershell
javap -c -classpath out com.example.TraceExample
~~~

Xem bytecode cùng thông tin dòng source:

~~~powershell
javap -c -l -classpath out com.example.TraceExample
~~~

Hiển thị cả private member:

~~~powershell
javap -p -c -l -classpath out com.example.TraceExample
~~~

Xem metadata chi tiết:

~~~powershell
javap -v -p -classpath out com.example.TraceExample
~~~

Ý nghĩa các tùy chọn chính:

| Tùy chọn | Nội dung |
|---|---|
| `-c` | Disassemble bytecode của method |
| `-l` | Hiển thị line number table và local variable table nếu class có lưu |
| `-p` hoặc `-private` | Hiển thị cả field và method private |
| `-s` | Hiển thị descriptor nội bộ của field và method |
| `-v` hoặc `-verbose` | Hiển thị constant pool, class-file version, flags và attributes |
| `-classpath` hoặc `-cp` | Chỉ định nơi tìm class |
| `-sysinfo` | Hiển thị thông tin hệ thống về class đang kiểm tra |

Với bài toán đối chiếu source, thường bắt đầu bằng `-c -l`; khi cần hiểu sâu hơn thì bổ sung `-p`, `-s` hoặc `-v`.

## 4. Đọc bytecode của một method

Chạy:

~~~powershell
javap -c -p -classpath out com.example.TraceExample
~~~

Phần method `adjust` có dạng tương tự:

~~~text
private static int adjust(int);
  Code:
     0: iload_0
     1: ifge          7
     4: iload_0
     5: ineg
     6: ireturn
     7: iload_0
     8: iconst_2
     9: imul
    10: ireturn
~~~

Đối chiếu với source:

~~~java
if (value < 0) {
    return -value;
}
return value * 2;
~~~

| Bytecode | Ý nghĩa | Source tương ứng |
|---|---|---|
| `iload_0` | Đưa biến int ở local slot 0 lên operand stack | Đọc `value` |
| `ifge 7` | Nếu giá trị lớn hơn hoặc bằng 0 thì nhảy đến offset 7 | Kiểm tra điều kiện `value < 0` theo nhánh ngược |
| `iload_0` | Nạp lại giá trị `value` | Dùng `value` trong nhánh âm |
| `ineg` | Đổi dấu số nguyên trên stack | Biểu thức `-value` |
| `ireturn` | Trả về giá trị int | `return -value` |
| `iconst_2` | Đẩy số 2 lên operand stack | Hằng số `2` |
| `imul` | Nhân hai số int trên stack | `value * 2` |
| `ireturn` | Trả kết quả int | `return value * 2` |

Offset là vị trí bytecode trong method, tính theo byte. Số offset, constant-pool index và instruction cụ thể có thể thay đổi khi source hoặc compiler thay đổi. Ví dụ trên minh họa dạng bytecode điển hình; hãy đọc đầu ra từ chính class file của dự án khi cần xác minh.

## 5. Hiểu operand stack và local variable

Bytecode JVM chủ yếu thao tác trên hai vùng dữ liệu của mỗi frame:

- Local variable array lưu tham số và biến cục bộ.
- Operand stack lưu các giá trị trung gian dùng cho phép tính và lời gọi method.

Trong method `static int adjust(int value)`, tham số `value` ở local slot 0. Vì method static không có tham chiếu `this`, slot 0 được dùng ngay cho tham số đầu tiên.

Với instance method, slot 0 thường chứa `this`; các tham số tiếp theo bắt đầu ở slot 1. Kiểu `long` và `double` chiếm hai local variable slots theo mô hình JVM; các kiểu còn lại thường chiếm một slot.

Một số instruction thường gặp:

| Instruction | Chức năng |
|---|---|
| `iload`, `iload_0` | Nạp int từ local variable |
| `istore`, `istore_1` | Ghi int vào local variable |
| `aload`, `aload_0` | Nạp reference từ local variable |
| `astore` | Ghi reference vào local variable |
| `iconst_0`, `bipush`, `sipush`, `ldc` | Đẩy hằng số lên operand stack |
| `iadd`, `isub`, `imul`, `idiv` | Phép toán số nguyên |
| `getfield`, `putfield` | Đọc hoặc ghi instance field |
| `getstatic`, `putstatic` | Đọc hoặc ghi static field |
| `new`, `dup` | Tạo object và nhân đôi reference trên stack |
| `invokevirtual` | Gọi instance method theo dispatch ảo |
| `invokestatic` | Gọi static method |
| `invokespecial` | Gọi constructor hoặc một số lời gọi đặc biệt |
| `invokeinterface` | Gọi method qua interface |
| `invokedynamic` | Gọi hành vi được liên kết qua cơ chế dynamic call site |
| `ireturn`, `areturn`, `return` | Trả giá trị hoặc kết thúc method void |

Khi đọc một chuỗi instruction, hãy theo dõi giá trị được nạp lên stack, instruction tiêu thụ giá trị nào và kết quả được đẩy lại ra sao. Điều này giúp hiểu phép tính hoặc lời gọi method thay vì chỉ nhìn tên lệnh riêng lẻ.

## 6. Đối chiếu nhánh và vòng lặp

Cấu trúc điều khiển trong source thường được biểu diễn bằng các instruction so sánh và nhảy.

### 6.1. Câu lệnh if/else

Source:

~~~java
if (score >= 50) {
    return "pass";
} else {
    return "fail";
}
~~~

Compiler thường tạo một conditional branch như `if_icmpge`, `iflt` hoặc `ifeq`, sau đó dùng `goto` để chuyển tới nhánh phù hợp. Hướng nhảy có thể đảo so với điều kiện source vì compiler chọn bố trí block theo thứ tự thuận tiện.

Khi đối chiếu, đừng giả định `if` luôn trở thành một instruction có tên giống từ khóa. Hãy đọc điều kiện branch, offset đích và instruction trả kết quả của từng nhánh.

### 6.2. Vòng lặp

Source:

~~~java
int total = 0;
for (int i = 0; i < 3; i++) {
    total += i;
}
~~~

Compiler thường chuyển vòng lặp thành:

1. Khởi tạo biến đếm và biến tích lũy trong local slots.
2. So sánh biến đếm với giới hạn.
3. Nhảy ra khỏi vòng lặp khi điều kiện kết thúc đúng.
4. Thực hiện thân vòng lặp và cập nhật biến.
5. Dùng lệnh nhảy quay lại bước kiểm tra.

Trong bytecode, thường thấy các nhánh như `if_icmpge`, `if_icmplt` và `goto`. Source dùng `for`, nhưng bytecode không có instruction tên `for`.

### 6.3. Switch

Tùy biểu thức và các nhãn case, compiler có thể sinh `tableswitch` hoặc `lookupswitch`. `tableswitch` phù hợp với tập giá trị integer liên tiếp hoặc tương đối dày; `lookupswitch` biểu diễn các cặp key/target cho tập khóa thưa hơn.

Xem bytecode để biết compiler đã chọn dạng nào:

~~~powershell
javap -c -classpath out com.example.SwitchExample
~~~

Không nên dự đoán instruction chỉ từ số lượng case; cách bố trí khóa và compiler quyết định dạng được sinh ra.

## 7. Đối chiếu lời gọi method và descriptor

Khi source gọi method, bytecode cần chỉ ra cách JVM tìm và gọi method đó. Các instruction phổ biến gồm `invokevirtual`, `invokestatic`, `invokespecial` và `invokeinterface`.

Ví dụ:

~~~java
int result = adjust(input);
~~~

Trong `main`, lời gọi đến method static `adjust` thường được biểu diễn bằng `invokestatic`. Bytecode cũng có thể chứa descriptor để mô tả kiểu tham số và kiểu trả về.

Dùng `javap -s`:

~~~powershell
javap -s -p -classpath out com.example.TraceExample
~~~

Một số descriptor cơ bản:

| Descriptor | Ý nghĩa |
|---|---|
| `()I` | Không nhận tham số, trả về int |
| `(I)I` | Nhận một int, trả về int |
| `([Ljava/lang/String;)V` | Nhận String array, trả về void |
| `(Ljava/lang/String;)V` | Nhận String, trả về void |
| `()Ljava/lang/String;` | Không nhận tham số, trả về String |

Descriptor là biểu diễn kiểu ở mức JVM. Nó không chứa tên tham số source, và generic type thường bị type erasure trong descriptor method thông thường. Generic signature có thể được lưu riêng trong `Signature` attribute.

## 8. LineNumberTable: nối bytecode với dòng source

Để debugger và công cụ phân tích ánh xạ instruction về dòng source, class file có thể chứa `LineNumberTable`.

Xem bằng:

~~~powershell
javap -l -classpath out com.example.TraceExample
~~~

Đầu ra có thể gồm:

~~~text
LineNumberTable:
  line 5: 0
  line 6: 4
  line 8: 7
~~~

Mỗi entry ánh xạ một bytecode offset tới số dòng source. Trong ví dụ, bytecode bắt đầu tại offset 0 tương ứng một dòng source; offset sau có thể ánh xạ tới dòng khác.

Line table không ghi lại từng ký tự hoặc từng biểu thức source. Nhiều instruction có thể cùng ánh xạ tới một dòng; một dòng source cũng có thể tạo nhiều đoạn bytecode. Vì vậy, đây là ánh xạ phục vụ debug, không phải bản đồ một-một giữa câu lệnh Java và instruction JVM.

Nếu class không có line number information, `javap -l` không thể tự khôi phục số dòng từ bytecode.

## 9. LocalVariableTable và thông tin debug

`LocalVariableTable` có thể chứa tên biến cục bộ, descriptor, slot và phạm vi bytecode mà biến tồn tại.

Ví dụ, khi biên dịch bằng:

~~~powershell
javac -g:source,lines,vars -d out src/com/example/TraceExample.java
~~~

Sau đó kiểm tra:

~~~powershell
javap -l -p -classpath out com.example.TraceExample
~~~

Bạn có thể thấy tên biến như `args`, `input`, `result`, `value` cùng slot và khoảng offset của chúng, nếu compiler lưu các entry tương ứng.

Các tùy chọn debug của javac:

- `-g`: sinh đầy đủ debug information.
- `-g:none`: không sinh debug information.
- `-g:source,lines,vars`: chọn rõ source file, line number và local variable information.

Thông thường compiler mặc định có thể giữ source file và line number nhưng không nhất thiết giữ local variable names. Nếu debugger cần xem tên biến cục bộ, hãy xác nhận build đã sinh `LocalVariableTable`.

Tùy chọn `-parameters` có mục đích khác: nó lưu tên tham số method trong `MethodParameters` attribute để reflection có thể đọc tên tham số. Nó không thay thế `LocalVariableTable`.

## 10. Nhận diện cấu trúc compiler tự sinh

Source và bytecode có thể khác nhau vì compiler sinh thêm các method hoặc attribute cần cho runtime.

| Source construct | Điều có thể thấy trong class file |
|---|---|
| Class không khai báo constructor | Compiler sinh default constructor nếu class cần constructor mặc định |
| Generic inheritance với method override | Có thể có bridge method để duy trì dispatch sau type erasure |
| Lambda expression | Thường dùng `invokedynamic` cùng `BootstrapMethods` |
| Nối chuỗi | JDK mới thường dùng `invokedynamic` và bootstrap method cho string concatenation |
| Enum | Có thể có method và field compiler sinh thêm |
| Inner/nested class | Có metadata như `InnerClasses`, nest attributes hoặc synthetic accessors tùy phiên bản |
| Record | Có `Record` attribute cùng các member được sinh tự động |
| Sealed class | Có `PermittedSubclasses` attribute |
| Try/catch/finally | Có exception table và các block bytecode tương ứng |

Dùng verbose output để xem attributes:

~~~powershell
javap -v -p -classpath out com.example.TraceExample
~~~

Tìm `BootstrapMethods` khi phân tích lambda hoặc string concatenation; tìm `Synthetic`, `Bridge`, `Record`, `PermittedSubclasses` hoặc `Exception table` tùy loại source.

Không phải mọi method compiler sinh đều có cùng tên hoặc hình thức ở mọi phiên bản Java. Hãy kiểm tra artifact thực tế thay vì dựa vào một mẫu bytecode cố định.

## 11. Exception table và try/catch/finally

Source:

~~~java
try {
    work();
} catch (IllegalArgumentException ex) {
    recover();
}
~~~

Compiler biểu diễn vùng bảo vệ và handler trong exception table của attribute `Code`. Exception table chỉ ra phạm vi bytecode được bảo vệ, vị trí handler và kiểu exception cần bắt.

Dùng:

~~~powershell
javap -c -v -p -classpath out com.example.ExceptionExample
~~~

Trong output, tìm phần `Exception table`. Nó giúp xác định instruction nào nằm trong vùng `try`, handler bắt đầu tại offset nào và exception type nào được xử lý.

`finally` có thể được triển khai bằng các đoạn bytecode bổ sung hoặc cơ chế cleanup phù hợp. Với try-with-resources, compiler còn sinh logic gọi `close()` và xử lý suppressed exception. Vì vậy, source ngắn có thể tạo ra bytecode dài hơn đáng kể.

## 12. Kiểm tra class trong JAR hoặc module

Nếu class nằm trong JAR, có thể đưa JAR vào classpath của javap:

~~~powershell
javap -c -l -p -classpath app.jar com.example.TraceExample
~~~

Nếu cần kiểm tra cả thư viện phụ thuộc, trên Windows dùng dấu chấm phẩy:

~~~powershell
javap -c -classpath "app.jar;lib/*" com.example.TraceExample
~~~

Trên Linux/macOS, dùng dấu hai chấm:

~~~bash
javap -c -classpath "app.jar:lib/*" com.example.TraceExample
~~~

Để xác nhận class có trong JAR:

~~~powershell
jar --list --file app.jar
~~~

Với module, có thể chỉ định module path và module:

~~~powershell
javap --module-path mods --module com.example.app com.example.app.Main
~~~

`javap` đọc class file từ artifact được chỉ định. Hãy chắc chắn bạn đang kiểm tra đúng JAR hoặc thư mục output mà ứng dụng thực tế chạy; nếu classpath chứa nhiều bản trùng tên, kết quả từ một artifact khác có thể gây hiểu nhầm.

## 13. Những giới hạn khi đối chiếu source với bytecode

- Bytecode không giữ comment, indentation hoặc cách đặt tên source ban đầu nếu metadata tương ứng không được lưu.
- `LineNumberTable` ánh xạ offset tới dòng, không xác định chính xác từng biểu thức trên dòng đó.
- Tên biến cục bộ chỉ có thể xem nếu compiler sinh `LocalVariableTable`.
- Compiler có thể sinh constructor, bridge method, synthetic member và metadata không xuất hiện trực tiếp trong source.
- Lambda, string concatenation, switch và try-with-resources có thể được biểu diễn bằng nhiều instruction và attribute.
- Bytecode không cho biết toàn bộ tối ưu JIT xảy ra ở runtime.
- Các constant-pool index, offset và instruction sequence có thể thay đổi giữa compiler hoặc phiên bản JDK.

Nếu cần tái tạo source từ class file, decompiler có thể tạo mã Java gần đúng, nhưng tên biến, generic, cấu trúc điều khiển và biểu thức có thể khác source gốc. Không dùng output decompiler như bằng chứng rằng source ban đầu có nội dung y hệt.

## 14. Quy trình đối chiếu trong thực tế

Khi điều tra một method cụ thể:

1. Xác định source revision và artifact được build từ revision đó.
2. Biên dịch với debug information nếu cần line/variable mapping.
3. Dùng `javap -p -c -l` để đọc khai báo, bytecode và line table.
4. Chọn method cần kiểm tra và xác định descriptor của nó.
5. Theo dõi local slot, operand stack, branch target và method invocation.
6. Dùng `javap -v` để xem constant pool, attributes, exception table và bootstrap methods khi cần.
7. Đối chiếu line number với source, lưu ý mapping không phải một-một.
8. Kiểm tra class file và dependency trong đúng JAR/module đang triển khai.
9. Chạy test trên runtime mục tiêu để xác nhận hành vi thực tế.

Không cần phân tích toàn bộ class file nếu chỉ có một câu hỏi cụ thể. Dùng `-c` để hiểu instruction, `-l` để ánh xạ dòng source, `-s` để đọc descriptor và `-v` khi cần metadata sâu hơn.

## 15. Checklist trước khi kết luận

- [ ] Đang kiểm tra đúng class file được ứng dụng sử dụng.
- [ ] Đã xác định source revision và JDK/compiler tạo artifact.
- [ ] Đã biên dịch với debug information nếu cần line hoặc local variable mapping.
- [ ] Đã dùng `javap -c` để xem bytecode của method liên quan.
- [ ] Đã dùng `javap -l` để đối chiếu LineNumberTable.
- [ ] Đã kiểm tra descriptor và member bằng `-s` hoặc `-p` khi cần.
- [ ] Đã xem `-v` nếu cần attributes, exception table hoặc bootstrap methods.
- [ ] Đã phân biệt bytecode do javac sinh với tối ưu JIT lúc runtime.
- [ ] Đã xác nhận hành vi bằng test trên runtime thực tế.

Đối chiếu source với bytecode là cách nhìn trực tiếp cách javac biểu diễn chương trình ở mức JVM. Kết hợp `javap -c` để đọc instruction, `-l` để nối offset với dòng source, và `-v` để xem metadata. Luôn kiểm tra artifact đúng và nhớ rằng ánh xạ source-bytecode có thể nhiều-nhiều, không phải bản dịch từng dòng.
