# 19.5. Breakpoint, stepping, stack frame, biến cục bộ và điều kiện có debug information

Khi debug Java, một breakpoint giúp **tạm dừng thực thi tại một vị trí được JVM/debugger hỗ trợ**, rồi kiểm tra call stack, biến cục bộ, object và trạng thái các thread. Nhưng debugger không “đọc trực tiếp” các dòng source đang mở trong IDE để thực thi: JVM chạy **bytecode của những class thực sự đã được nạp**. Khả năng liên kết bytecode trở lại source, dừng ở một dòng và hiển thị tên biến phụ thuộc vào **debug information trong `.class`**, phiên bản class, đường dẫn source và trạng thái runtime.

Bài học này phân biệt **breakpoint, step into/over/out, stack frame, local variable** và giải thích chính xác **khi nào cần thông tin debug**. Ví dụ chạy bằng Java 17+ với `javac`, `javap` và `jdb`; IDE như IntelliJ IDEA, Eclipse hay VS Code có giao diện khác nhưng nguyên lý dựa trên Java Platform Debugger Architecture (JPDA) tương tự.

## 1. Mô hình tư duy: source code, bytecode, debugger, JVM

Một luồng debug điển hình:

```text
DebugFrameDemo.java
       │ javac (có/không có -g)
       ▼
DebugFrameDemo.class
  ├─ bytecode + method/field descriptors (để thực thi)
  ├─ SourceFile (nếu có)
  ├─ LineNumberTable (nếu có)
  └─ LocalVariableTable / LocalVariableTypeTable (nếu có)
       │
       ▼
JVM chạy class đã nạp ─── JDWP/JVMTI ─── debugger (IDE / jdb)
      │ suspend thread                        │
      └── stack frame, bytecode location ──────┘ hiển thị dòng/biến
```

JPDA có ba thành phần liên quan:

- **JDI — Java Debug Interface:** API cho debugger điều khiển và truy vấn JVM, thread, breakpoint, stack frame, variable.
- **JDWP — Java Debug Wire Protocol:** giao thức liên lạc giữa debugger và JVM đang được debug, thường dùng socket trong remote attach.
- **JVMTI — JVM Tool Interface:** giao diện ở phía runtime cho agent/debugger thực hiện nhiều thao tác quan sát/điều khiển.

IDE thường bọc các API này thành nút **Resume**, **Step Into**, **Step Over**, **Step Out**, **Frames**, **Variables**, **Evaluate Expression**. Tên nút và phím tắt khác nhau giữa các IDE, nên không đoán phím tắt là tiêu chuẩn Java.

**Phân biệt cốt lõi:** file source mới nhất trên máy bạn không nhất thiết tương ứng với `.class` JVM đang chạy. Debugger có thể tô đậm dòng source “đúng tên” nhưng mapping đã lệch sau một lần build/deploy không đồng bộ. Khi trạng thái vô lý, hãy kiểm tra **bytecode đang được nạp** và debug attributes trước khi nghi JVM tính toán sai.

## 2. Breakpoint là gì và các loại thường dùng?

Breakpoint là một điều kiện khiến debugger yêu cầu VM **báo sự kiện và/hoặc suspend** khi tiến trình thực thi đến vị trí phù hợp. Một source-line breakpoint thường được ánh xạ thành **vị trí bytecode (code index) trong method**, nhờ `LineNumberTable`. Không phải mọi dòng source đều có lệnh thực thi riêng.

| Loại breakpoint | Khi phát sinh | Dùng để làm gì | Lưu ý |
| --- | --- | --- | --- |
| **Line breakpoint** | Khi một thread đến vị trí bytecode tương ứng một dòng source. | Xem giá trị biến trước/sau một thao tác cụ thể. | Cần line mapping và code thực thi; comment, import, khai báo không sinh code thường không đặt được. |
| **Method entry breakpoint** | Khi method phù hợp được gọi. | Bắt đầu theo dõi một method mà chưa biết dòng cụ thể. | Có thể hoạt động khi thiếu line mapping, nhưng nhiều call gây overhead lớn. |
| **Conditional breakpoint** | Khi đạt vị trí và biểu thức điều kiện đúng. | Dừng chỉ cho trường hợp như `orderId == 42`. | Biểu thức được debugger đánh giá; có thể tốn CPU, invoke code, gây side effect hoặc exception. |
| **Exception breakpoint** | Khi loại exception được throw (theo cấu hình caught/uncaught). | Tìm điểm phát sinh lỗi thay vì chỉ thấy nơi bắt lỗi. | Exception có thể throw thường xuyên như luồng điều khiển bình thường. |
| **Field watchpoint** | Khi đọc/ghi một field được theo dõi (nếu debugger/VM hỗ trợ). | Tìm chỗ thay đổi state bất ngờ. | Không giống watch local variable; chi phí có thể cao. |
| **Logpoint/tracepoint của IDE** | Khi chạm vị trí và IDE ghi thông tin thay vì dừng (theo cấu hình). | Điều tra nhiều request mà ít gián đoạn. | Vẫn có chi phí instrumentation/evaluate và có nguy cơ lộ dữ liệu nhạy cảm. |

Một breakpoint **không bảo đảm chỉ dừng một lần**: một dòng trong vòng lặp có thể được chạy hàng nghìn lần, nhiều thread có thể đi qua cùng method, và một class có thể được nạp nhiều lần bởi các class loader khác nhau.

### Breakpoint có thể không dừng vì sao?

- **Class chưa được nạp:** debugger có thể đánh dấu breakpoint là pending/deferred rồi gắn khi class tương ứng được load.
- **Dòng không thực thi:** dòng comment, import, khai báo hoặc code bị compiler loại bỏ không có bytecode location tương ứng.
- **Thiếu/mất line debug info:** thiếu `LineNumberTable` khiến không thể ánh xạ chính xác source line.
- **Source khác class đã deploy:** line 25 trong source hiện tại là code khác so với class đang chạy.
- **Class loader hoặc module khác:** cùng tên class có thể tồn tại ở nhiều loader; breakpoint gắn sai bản.
- **Chưa đi qua đường code:** điều kiện `if` sai, method không được gọi, thread đã kết thúc.
- **Filter/condition/suspend policy:** IDE đặt điều kiện không khớp, đang disable breakpoint hoặc chỉ dừng thread khác.
- **Build optimization/instrumentation:** bytecode biến đổi bởi agent, obfuscator, build tool hoặc generated code làm location không tương ứng kỳ vọng.

Không bật tắt breakpoint ngẫu nhiên để chữa lỗi. Đọc thông báo “verified/unverified”, xác nhận PID, classpath/module-path, class loader và kiểm tra `javap` trên **artifact thực sự được dùng để chạy**.

## 3. Stepping: Step Into, Step Over, Step Out và Resume

Khi JVM đã tạm dừng ở breakpoint, các thao tác stepping giúp theo dõi đường chạy:

| Thao tác | Ý nghĩa đơn giản | Câu hỏi phù hợp |
| --- | --- | --- |
| **Step Into** | Tiến tới bước source tiếp theo, có thể đi vào method được gọi. | “Lời gọi này làm gì bên trong?” |
| **Step Over** | Chạy qua lời gọi method ở dòng hiện tại, rồi dừng ở bước kế tiếp trong **frame hiện tại** nếu có. | “Giá trị thay đổi ra sao sau khi method trả về?” |
| **Step Out** | Tiếp tục đến khi **method của frame hiện tại** trả về, rồi dừng ở caller khi có thể. | “Điểm gọi nhận kết quả nào?” |
| **Resume/Continue** | Tiếp tục đến breakpoint/exception/sự kiện dừng kế tiếp. | “Có còn tái hiện ở vị trí này không?” |
| **Run to Cursor** (IDE) | Đặt mục tiêu chạy đến vị trí được chọn, có điều kiện công cụ hỗ trợ. | “Bỏ qua những dòng không liên quan.” |

Trong `jdb`:

- `step` tương đương với tiến tới dòng kế tiếp, **có thể vào method khác**.
- `next` tiến tới dòng kế tiếp trong **frame hiện tại**.
- `cont` tiếp tục chạy.
- `step up` (trong các phiên bản `jdb` hỗ trợ) thực hiện cho tới khi method hiện tại trả về; dùng `help` của chính `jdb` để xác nhận.

**Không hiểu Step Over là “không thực thi method được gọi”**. Method vẫn chạy đầy đủ, có thể I/O, ném exception, spawn thread, chạm breakpoint khác hoặc gây side effect; debugger chỉ không đi vào từng dòng method ấy theo chế độ step-over.

Cũng không nên hiểu **Step Out** là “bỏ qua phần code còn lại”. Những statement còn lại vẫn được thực thi cho đến khi method trả về hoặc bị exception/unwind.

### Vì sao bấm Step Into nhưng không vào dòng mình muốn?

Có thể dòng hiện tại có **nhiều lời gọi** và debugger bước vào lời gọi được thực thi trước; lời gọi là native, thư viện bị filter; compiler tạo bridge/synthetic method; lambda/method reference đi qua code được sinh; hoặc source mapping chỉ có một dòng cho nhiều bytecode instructions. Nhiều IDE hỗ trợ **Smart Step Into** để chọn lời gọi cụ thể, nhưng đó là tính năng của IDE, không phải cú pháp chung của Java.

Khi stack trace hiện `lambda$...`, `access$...`, `$Proxy...` hoặc generated frame, cần hiểu compiler/framework có thể sinh phương thức/class trung gian. Điều này không nhất thiết báo lỗi; hãy kiểm tra logic thực tế và debug mapping.

## 4. Stack frame: “đang ở phương thức nào, do ai gọi?”

Mỗi Java thread có call stack của riêng mình. Khi một method được gọi, runtime tạo một **stack frame** tương ứng với lần gọi đó. Frame chứa trạng thái thực thi cần thiết, bao gồm local-variable slots, operand stack và thông tin để trả về caller; debugger trình bày những dữ liệu truy cập được ở frame đang tạm dừng.

Ví dụ:

```text
Thread "main" tại breakpoint trong calculateSubtotal(...)
┌────────────────────────────────────────────┐
│ frame #0: DebugFrameDemo.calculateSubtotal │ ← frame hiện tại
│           quantity=3, price=7, raw=21       │
├────────────────────────────────────────────┤
│ frame #1: DebugFrameDemo.main               │ ← caller
│           quantity=3, price=7               │
└────────────────────────────────────────────┘
```

*Đây là sơ đồ minh họa sau khi `raw` đã được gán; không phải output cố định của `jdb`.*

- **Top frame** là method đang thực thi hoặc đang bị dừng, thường gần nhất với breakpoint.
- **Caller frame** là nơi method hiện tại được gọi; có thể xem biến của frame caller nếu metadata có sẵn.
- **Chọn frame** trong debugger chỉ đổi bối cảnh bạn đang xem/evaluate; không tự làm JVM quay ngược thời gian.
- Một method có thể xuất hiện nhiều lần ở các frame khác nhau do **đệ quy**, mỗi lần có local values riêng.
- **Local variable** là của **một lần thực thi method** (một frame), khác với field thuộc object hoặc static field thuộc class.

Khi thread resume, stack tiến triển: frame có thể biến mất khi method trả về, exception unwind stack hoặc tiếp tục vào method mới. Không giữ một đối tượng `StackFrame`/biến JDI cũ rồi dùng sau khi thread đã resume; JDI có thể báo `InvalidStackFrameException`.

### “Stack frame” khác “Java stack trace” như thế nào?

**Stack frame đang tạm dừng** là snapshot của một vị trí thực thi có thể xem locals nếu có metadata. **Stack trace được log từ exception** thường chủ yếu là tên class/method, source file và line (nếu có); nó **không in mọi biến cục bộ**. Một exception stack trace không phải heap dump, cũng không phải lịch sử mọi lần method đã được gọi.

Với async (`CompletableFuture`, executor, reactive chains), worker đang chạy callback có **stack của worker đó**. Method đã submit task từ thread khác có thể đã kết thúc hoặc đang chờ; nó không tự động nằm dưới callback trong call stack. Muốn nối logical call chain qua thread, sử dụng trace/correlation ID, async stack tooling hoặc instrumentation phù hợp, không chỉ nhìn `where` của một thread.

## 5. Biến cục bộ (local variables) và phạm vi quan sát

Để debug `int subtotal` hoặc `String customerId`, cần phân biệt:

| Dữ liệu | Nằm ở đâu về mặt ngữ nghĩa | Cách debug thường gặp |
| --- | --- | --- |
| **Parameter** của method | Đầu vào của một lần gọi/frame. | Mở frame hiện tại; tên parameter có thể cần `LocalVariableTable` để debugger hiển thị đúng. |
| **Local variable** | Khai báo trong method/block, có phạm vi và thời điểm sống. | `Variables`/`locals`, nhưng phải ở code location nơi biến được coi là visible. |
| **Instance field** | Thuộc một object Java. | Mở `this` hoặc object reference rồi xem field; không phải “local” theo nghĩa này. |
| **Static field** | Thuộc class, dùng chung qua các instance theo class-loader identity. | Xem field qua class/debugger; có thể liên quan nhiều thread. |
| **Captured variable** của lambda | Giá trị/reference được capture khi tạo lambda theo quy tắc Java. | Có thể xuất hiện dưới field/synthetic structure, không nhất thiết như local trực tiếp. |
| **Operand stack/slot tạm** | Trạng thái bytecode nội bộ. | Không nhất thiết có tên source; debugger không thể hiện như local Java. |

Một local có **lexical scope** trong Java source, nhưng metadata `LocalVariableTable` mô tả **phạm vi code index** để debugger biết tên, kiểu và slot tương ứng. Khi dừng **trước dòng gán đầu tiên**, biến có thể chưa được khởi tạo hoặc chưa được báo visible; sau khi `next` qua dòng đó, biến mới có giá trị có thể xem.

Đừng coi mọi giá trị hiển thị là “đã được tính xong”. Nếu debugger dừng ở đầu dòng:

```java
int total = compute(subtotal);
```

thì `total` có thể **chưa được gán**. Cần `next` để chạy statement, sau đó mới kiểm tra giá trị `total`. Không sửa local trong debugger mà quên rằng việc sửa sẽ thay đổi đường chạy; nhiều IDE cho phép `Set Value` chỉ khi JDI/VM hỗ trợ và biến đang ở vị trí hợp lệ.

### Vì sao IDE báo “Variable not available” hoặc `AbsentInformationException`?

Các trường hợp khác nhau cần xử lý khác nhau:

1. **Thiếu debug-info về local:** file `.class` không có `LocalVariableTable`; JDI `StackFrame.visibleVariables()` có thể ném `AbsentInformationException`.
2. **Biến chưa vào scope hoặc đã ra scope:** code location hiện tại không thuộc phạm vi hợp lệ của biến.
3. **Đã đi qua lời gọi hoặc thread resume:** frame trước đó đã bị hủy/không còn hợp lệ.
4. **Đang ở native frame:** không có local-variable table Java như method bytecode thông thường.
5. **Compiler/JIT/lambda instrumentation:** debugger không có mapping rõ ràng đến một biểu thức source; tên có thể được tối ưu/diễn giải khác hoặc không đánh giá được.
6. **Source/artifact lệch:** local tên `discount` trong source mới chưa tồn tại ở bytecode cũ.

Thiếu local metadata không đồng nghĩa **JVM không có giá trị nội bộ**. Nó có nghĩa giao diện debugger không có đủ thông tin tin cậy để ánh xạ slot bytecode sang **tên source** ở vị trí đó.

## 6. Debug information trong class file: ba nhóm cần nhớ

`javac` có thể nhúng các thuộc tính debug bổ sung vào `.class`:

| Thành phần | Vai trò | Ảnh hưởng thực tế |
| --- | --- | --- |
| `SourceFile` | Tên tệp source ban đầu (ví dụ `DebugFrameDemo.java`). | Giúp debugger/stack trace xác định source file; **không chứa nguyên file source**. |
| `LineNumberTable` | Ánh xạ bytecode offsets sang line numbers trong source. | Giúp line breakpoint, stepping và stack trace có số dòng. |
| `LocalVariableTable` (và đôi khi `LocalVariableTypeTable`) | Ánh xạ slot thành tên/kiểu/phạm vi của local và parameter. | Giúp `locals`/Variables hiển thị tên và giá trị trong frame hiện tại. |
| `MethodParameters` | Tên và flags của formal parameters cho reflection khi được biên dịch với `-parameters`. | **Không thay thế `LocalVariableTable`** để xem mọi biến local. |

Các thuộc tính như `SourceFile`, `LineNumberTable`, `LocalVariableTable` là **thông tin tùy chọn** trong class file. `-g:none` vẫn tạo ra class có bytecode, methods, fields và những metadata bắt buộc để JVM thực thi; nó không “xóa tên method” hay biến code thành bí ẩn tuyệt đối.

### `javac` mặc định khác `javac -g`

Điểm đặc biệt quan trọng ở **Oracle/OpenJDK javac 17**:

- **Mặc định không thêm `-g`:** compiler thường ghi **`lines` và `source`**, nhưng **không ghi local variable debug information**.
- **`-g`:** ghi đầy đủ `lines,vars,source`, gồm thông tin local variables.
- **`-g:lines,source`:** ghi line number và source file nhưng không yêu cầu local-variable info.
- **`-g:vars`:** ghi thông tin local variables, nhưng **không đồng thời yêu cầu line numbers/source file**; không phù hợp nếu muốn source-line debugging đầy đủ.
- **`-g:none`:** không ghi nhóm debug information đó.
- **`-parameters`:** bổ sung metadata tên formal method parameters để reflection đọc; **không thay `-g`**.

Đối với build cần debug từng dòng và inspect variables, chọn **`javac -g`** (hoặc `-g:lines,vars,source`) trên artifact test/staging. Nếu chỉ chạy `javac Demo.java`, line breakpoint có thể hoạt động nhưng `locals` trong `jdb` không đủ thông tin tên local.

Không nhầm `-g` của compiler với `-agentlib:jdwp` của Java launcher: **`-g` quyết định thông tin được đóng gói khi biên dịch**, còn **JDWP agent** mở khả năng debugger gắn vào **JVM đang chạy**. Hai lựa chọn bổ sung nhau, không thay thế nhau.

## 7. Java 17+ — chương trình thực hành breakpoint, frame và locals

Lưu thành tệp **`DebugFrameDemo.java`**:

```java
public final class DebugFrameDemo {
    private static final int DELIVERY_FEE = 5;

    public static void main(String[] args) {
        int quantity = 3;
        int unitPrice = 7;

        int subtotal = calculateSubtotal(quantity, unitPrice);
        int total = addDeliveryFee(subtotal);

        System.out.println("total=" + total);
    }

    private static int calculateSubtotal(int quantity, int unitPrice) {
        int raw = quantity * unitPrice;
        int discount = quantity >= 3 ? 2 : 0;
        int afterDiscount = raw - discount;

        return afterDiscount;
    }

    private static int addDeliveryFee(int subtotal) {
        int total = subtotal + DELIVERY_FEE;
        return total;
    }
}
```

Phép tính xác định: `3 × 7 = 21`, giảm `2` còn `19`, cộng phí `5` thành `24`.

Biên dịch với **đầy đủ debug information** và chạy bình thường (JDK 17+):

```bash
mkdir -p out
javac -g -d out DebugFrameDemo.java
java -cp out DebugFrameDemo
```

**Stdout chính xác:**

```text
total=24
```

Nếu chương trình không in `total=24` khi chạy ngoài debugger, hãy kiểm tra đúng classpath và file source trước khi debug; tránh dùng debugger để che lỗi do chạy nhầm artifact.

### 7.1. Debug bằng IDE

Trong IDE Java bất kỳ có hỗ trợ JDWP/JDI:

1. Mở project chứa source, đảm bảo dùng **JDK 17+** và build ra đúng class đang chạy. Bật chế độ debug và tạm dừng tại dòng `int raw = quantity * unitPrice;`.
2. Khi dừng ở đầu dòng, kiểm tra `quantity=3`, `unitPrice=7` trong **frame `calculateSubtotal`**. `raw` có thể chưa được gán, tùy position.
3. Nhấn **Step Over** một lần để thực thi gán `raw`, rồi kiểm tra `raw=21`.
4. Step Over tiếp qua `discount` và `afterDiscount`; tại vị trí sau các dòng tương ứng, kiểm tra `discount=2` và `afterDiscount=19`.
5. Dùng **Step Out** để trở về `main`: thấy `subtotal=19` sau khi lời gọi hoàn tất.
6. Ở dòng gọi `addDeliveryFee(subtotal)`, dùng **Step Into** để vào method, kiểm tra `subtotal=19`; Step Over để tính `total=24`; Step Out về `main` rồi Resume.
7. Mở **Frames/Call Stack** khi dừng trong `calculateSubtotal`; chọn `main` để xem local của caller, sau đó quay về frame hiện tại.

Thời điểm một biến trở nên visible phụ thuộc source line/bytecode location; không tự kết luận giá trị “sai” vì debugger vẫn đang dừng **trước** phép gán. Nếu IDE dừng ở dòng kế tiếp hoặc chỉ bước tới một breakpoint đã gắn, xem cấu hình step filters và compiler mapping.

### 7.2. Debug bằng `jdb` và JDWP trên localhost

Nếu muốn thấy debugger ở terminal, dùng **hai terminal** trên **máy thử nghiệm**. Terminal 1 khởi chạy JVM với JDWP, tạm dừng trước khi vào `main`:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 \
  -cp out DebugFrameDemo
```

- `transport=dt_socket`: debugger kết nối qua socket.
- `server=y`: JVM mở socket lắng nghe.
- `suspend=y`: JVM chờ debugger kết nối/cho phép tiếp tục trước khi thực thi `main`.
- `address=127.0.0.1:5005`: chỉ lắng nghe loopback IPv4 của máy này, tránh mở cổng debug ra mạng.

Terminal 2 kết nối bằng **jdb của JDK**, trỏ source path về thư mục có `DebugFrameDemo.java`:

```bash
jdb -attach 127.0.0.1:5005 -sourcepath .
```

Sau khi kết nối, tại prompt của `jdb` nhập từng lệnh (đây **không phải** lệnh Bash):

```text
stop in DebugFrameDemo.calculateSubtotal
cont
where
locals
print quantity
print unitPrice
next
locals
print raw
up
locals
down
cont
```

Ý nghĩa:
- `stop in ...` đặt **method entry breakpoint** (có thể deferred cho đến lúc class được nạp).
- `cont` cho tiến trình chạy đến breakpoint đó.
- `where` in Java stack trace của **thread đang dừng**.
- `locals` xem các local/parameter đang visible nếu `-g` đã cung cấp metadata.
- `print quantity`, `print unitPrice` xem giá trị của biến trong frame hiện tại.
- `next` chạy qua statement đang dừng và dừng ở vị trí source tiếp theo trong frame phù hợp; sau đó `raw` dự kiến là `21`.
- `up`/`down` (khi có trong `help` của bản `jdb`) chọn frame caller/callee để đọc bối cảnh, **không làm code thực thi lùi lại**.
- `cont` tiếp tục cho chương trình hoàn tất và in `total=24`.

Output của **`jdb`** (prompt, thread id, line number, thứ tự message) phụ thuộc JDK và session; không đưa ra một log output cố định. Đối với method breakpoint vừa vào `calculateSubtotal`, bạn có thể xem `quantity` và `unitPrice` trước, còn `raw` chỉ nên kiểm tra **sau** khi bước qua dòng gán.

Nếu muốn thực hành **line breakpoint**, thay `stop in ...` bằng dạng `stop at DebugFrameDemo:<line-number>` với số dòng **thực tế** trong source của bạn. Ví dụ không khóa cứng số dòng vì thêm/bớt comment có thể làm số dòng thay đổi. `jdb` hỗ trợ phương thức `stop in Class.method` và dòng `stop at Class:line` theo tài liệu JDK 17.

**Bảo mật:** JDWP là giao diện điều khiển JVM rất nhạy cảm. Chỉ dùng trên môi trường kiểm soát, bind loopback, không public port hay chuyển tiếp cổng không bảo vệ. Một debugger có thể đọc thông tin nhạy cảm, tạm dừng thread hoặc thay đổi trạng thái trong JVM. Không dùng `address=*:5005` trên production chỉ để tiện kết nối.

## 8. Tự kiểm tra `-g` bằng `javap`

Để biết file `.class` có metadata gì, dùng `javap` thay vì đoán từ IDE. Dùng **cùng source** nhưng biên dịch vào các thư mục riêng để không ghi đè:

```bash
mkdir -p build/default build/full build/none build/partial

# Mặc định: thường có lines và source, không có vars
javac -d build/default DebugFrameDemo.java

# Ghi đầy đủ line/source/local variable debug info
javac -g -d build/full DebugFrameDemo.java

# Không ghi những debug attributes đó
javac -g:none -d build/none DebugFrameDemo.java

# Chỉ source + line number
javac -g:lines,source -d build/partial DebugFrameDemo.java
```

Kiểm tra từng artifact:

```bash
javap -l -p -classpath build/default DebugFrameDemo
javap -l -p -classpath build/full DebugFrameDemo
javap -l -p -classpath build/none DebugFrameDemo
javap -l -p -classpath build/partial DebugFrameDemo

# Khi muốn xem đầy đủ attributes và bytecode location:
javap -v -p -classpath build/full DebugFrameDemo
```

Dự kiến về loại metadata (không phải số dòng cố định):

| Build | `SourceFile` | `LineNumberTable` | `LocalVariableTable` | Tác động khi debug |
| --- | --- | --- | --- | --- |
| `javac` mặc định trên JDK 17 | Có | Có | Thường **không** | Line breakpoint/stack trace có line; `locals` có thể thiếu tên biến. |
| `javac -g` | Có | Có | Có | Thuận tiện cho line stepping, inspect local/parameters. |
| `javac -g:none` | Không | Không | Không | Method breakpoint có thể vẫn khả dụng; không thể tin cậy map line hoặc tên biến. |
| `javac -g:lines,source` | Có | Có | Không | Có line, thiếu local variable metadata. |
| `javac -g:vars` | Không yêu cầu | Không yêu cầu | Có | Có tên local nhưng source-line breakpoint vẫn thiếu mapping nếu không có `lines`. |

`javap -l` chủ yếu in **line và local variable tables**, còn `javap -v` liệt kê thêm thuộc tính lớp như `SourceFile`. Trong output full debug, tìm các phần:

```text
LineNumberTable:
  line ...: ...
LocalVariableTable:
  Start  Length  Slot  Name          Signature
  ...    ...     ...   quantity      I
  ...    ...     ...   unitPrice     I
  ...    ...     ...   raw           I
```

Các dấu `...` là placeholder mô tả cấu trúc, **không phải output copy nguyên** từ một file đã chạy. Số start/length/slot và line number phải xem từ artifact thật.

### Những điều `javap` cho biết và không cho biết

`LineNumberTable` lưu mapping PC → line trong một method, không khôi phục **toàn bộ source code**. `LocalVariableTable` lưu tên, kiểu, slot và phạm vi bytecode, không phải log giá trị biến qua thời gian. `SourceFile` là tên file, **không chứa nội dung source**. Do đó cần giữ source tương ứng với build để IDE mở đúng dòng.

Bộ biên dịch khác `javac` (Kotlin, Scala, Groovy), các bước bytecode weaving, obfuscation, shrink hoặc ProGuard có thể thay đổi debug attributes và tên. Hãy kiểm tra class **sau bước build cuối** chứ không chỉ class trung gian của `javac`. Nếu có obfuscation, giữ mapping file một cách an toàn.

## 9. `-parameters` không tương đương thông tin local trong debugger

`javac -parameters` tạo thuộc tính `MethodParameters` để Java Reflection API có thể lấy **tên tham số** của method/constructor, ví dụ `Executable.getParameters()`. Nhưng nó không lưu tên của biến `int raw` trong thân method.

Có thể biên dịch:

```bash
javac -parameters -g:none -d build/none DebugFrameDemo.java
javap -v -p -classpath build/none DebugFrameDemo
```

Trong build này, `MethodParameters` có thể xuất hiện cho method có tham số dù `LineNumberTable` và `LocalVariableTable` bị tắt. Nghĩa là một framework reflection có thể thấy tên tham số nhưng IDE không nhất thiết có đủ dữ liệu để làm line breakpoint và xem `raw`. Ngược lại, `-g` giúp debugger local nhưng không tự bảo đảm mọi reflection API báo `isNamePresent() == true` nếu không dùng `-parameters`.

Nếu mục tiêu là **both reflection và full source debugging** trong môi trường thử nghiệm, có thể dùng:

```bash
javac -g -parameters -d out DebugFrameDemo.java
```

Không nên thay đổi cờ compile mù quáng trong production build; debug metadata có thể làm file lớn hơn và khiến việc xem nội bộ dễ hơn khi ai đó lấy được artifact, dù bản thân nó không biến Java bytecode thành dữ liệu bí mật.

## 10. Điều kiện breakpoint: chọn đúng thời điểm và tránh side effect

Một conditional breakpoint có thể dùng biểu thức như:

```java
quantity == 3 && unitPrice == 7
```

Đây là **biểu thức đặt trong UI cấu hình conditional breakpoint của IDE**, không phải chương trình độc lập. Khi code chạy đến vị trí, IDE chỉ quyết định suspend nếu điều kiện đúng theo cơ chế của debugger.

Các điểm cần cân nhắc:

- Điều kiện phải dùng **biến đang visible ở frame/breakpoint**. Nếu gắn ở đầu `main` thì `quantity` chưa được khai báo/gán, biểu thức có thể chưa evaluate được.
- Một điều kiện trên line nóng chạy hàng triệu lần có thể gây overhead rất lớn vì debugger phải đánh giá mỗi lần gặp.
- Không gọi method có side effect như `order.setStatus(...)` hoặc `repository.save(...)` trong conditional breakpoint.
- Ngay cả getter tưởng vô hại có thể lazy-load, lock hoặc gọi mạng; ưu tiên biểu thức thuần, field/primitive/simple comparisons.
- Điều kiện có thể ném exception (`null`, index out of bounds) khiến debugger không dừng như kỳ vọng; xem log lỗi evaluation của IDE.
- Không log/hiển thị token, password hoặc PII nếu debug production data.

**Hit-count breakpoint** (“dừng ở lượt thứ N”) phù hợp hơn khi muốn xem một iteration cụ thể. **Exception breakpoint** phù hợp nếu muốn bắt nơi `throw` diễn ra; điều kiện chỉ đúng cho một input cụ thể. Không nên mặc định dùng conditional breakpoint ở mọi vòng lặp.

Với `jdb` JDK 17, các lệnh `stop at` và `stop in` là hình thức cơ bản. Khả năng “conditional breakpoint” tiện lợi phụ thuộc debugger/IDE, đừng giả định cú pháp `stop ... if ...` luôn được `jdb` hỗ trợ.

## 11. Exception breakpoint: caught khác uncaught

Java có thể ném và bắt exception trong cùng request. Chỉ đặt breakpoint ở câu lệnh `catch` chưa chắc cho biết **gốc tạo exception** nằm ở đâu. Debugger có chế độ dừng khi một exception thuộc loại quan tâm được **throw**, kể cả nếu cuối cùng nó được bắt, tùy cấu hình “caught/uncaught”.

Ví dụ độc lập `ParseDebugDemo.java`:

```java
public final class ParseDebugDemo {
    public static void main(String[] args) {
        try {
            parsePositive("0");
        } catch (IllegalArgumentException ex) {
            System.out.println("handled=" + ex.getMessage());
        }
    }

    private static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new IllegalArgumentException("must be positive");
        }
        return value;
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -g ParseDebugDemo.java
java ParseDebugDemo
```

**Stdout chính xác:**

```text
handled=must be positive
```

Vì `main` bắt `IllegalArgumentException`, chương trình **hoàn tất bình thường**. Tuy nhiên, nếu debugger được cấu hình break on **caught exceptions**, bạn có thể thấy stack frame tại `throw new IllegalArgumentException(...)` trong `parsePositive` **trước khi** đi vào `catch`.

Trong `jdb`, lệnh `catch java.lang.IllegalArgumentException` cấu hình dừng khi loại exception này được ném. Câu lệnh `ignore java.lang.IllegalArgumentException` hủy việc theo dõi ở debugger; nó **không** khiến JVM bỏ qua exception về mặt chương trình. Trên ứng dụng dùng exception có chủ đích nhiều lần, loại breakpoint này có thể dừng rất thường xuyên; hãy giới hạn scope và dọn breakpoint khi xong.

## 12. Nhiều thread: breakpoint ở thread nào?

Giả sử `main` submit một `Runnable` cho worker. Khi breakpoint trong `run()`/method được gọi bởi worker:

- Call stack của **worker** có các frame executor/`ThreadPoolExecutor` và method đang chạy; `main` đã submit không tự nằm dưới những frame đó.
- Nếu chọn **thread main** trong panel Threads, debugger có thể hiển thị nó đang `Future.get()` hoặc một vị trí khác.
- Local `int jobId` trong frame của worker khác với local của main, dù biến trùng tên hoặc cùng object reference.
- Nếu breakpoint suspend **all threads**, ứng dụng có thể dừng toàn JVM theo policy của debugger, gây timeout ở socket/database/health check; nếu chỉ suspend **event thread**, thread khác tiếp tục thay đổi shared state.

Ví dụ `AsyncDebugDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class AsyncDebugDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> future = pool.submit(() -> doubleValue(4));
            System.out.println("result=" + future.get());
        } finally {
            pool.shutdown();
        }
    }

    private static int doubleValue(int input) {
        int result = input * 2;
        return result;
    }
}
```

Biên dịch/chạy:

```bash
javac -g AsyncDebugDemo.java
java AsyncDebugDemo
```

**Stdout chính xác:**

```text
result=8
```

Đặt breakpoint ở `int result = input * 2;`. Khi worker dừng, xem **Threads** rồi **Frames** của worker; caller của `doubleValue` có thể là phần lambda/`FutureTask`/executor. Thread main có thể đang chờ ở `future.get()`. Đừng cố tìm `main` bên dưới `doubleValue` trong cùng stack của worker.

Với futures/reactive pipelines, một request có thể có **logical call chain** qua nhiều thread/callback; Java stack trace chỉ là call chain đồng bộ của thread tại thời điểm quan sát. Dùng correlation ID/tracing hoặc công cụ async debugger khi cần quan hệ nguồn–đích.

### Debugger đôi khi khiến bug biến mất

Breakpoint thay đổi timing. Thread đang giữ lock bị suspend có thể khiến thread khác timeout; data race có thể không tái hiện vì lịch scheduler đã thay đổi. Với bug concurrency, kết hợp **thread dumps, JFR, logs có correlation ID, kiểm thử stress** thay vì chỉ step bằng tay.

Java 17 dùng platform threads phổ biến; virtual threads là tính năng xuất hiện ở các bản JDK sau. Nếu debug JDK khác, UI/support cho virtual threads có thể khác, nên không áp dụng cứng mọi đặc tính debugger JDK 17 sang một runtime mới mà không kiểm tra.

## 13. JIT, inlining, lambda và generated code làm stepping khác trực giác

JVM HotSpot có JIT có thể inline method hoặc tối ưu đường thực thi. Debugger có thể sử dụng cơ chế runtime để quan sát/tạm dừng và điều chỉnh trạng thái compiled code; tuy nhiên **việc stepping theo source không đồng nghĩa mỗi dòng source là một bước máy đơn nhất**.

Những tình huống dễ gây ngạc nhiên:

- Một dòng source có **nhiều expression** hoặc method calls, `step into` có thể đi vào lời gọi khác với dự đoán.
- Một source line tương ứng nhiều bytecode offsets; stepping có thể dừng lại ở cùng dòng hoặc nhảy qua dòng chỉ khai báo.
- Local chưa khởi tạo hoặc đã hết scope sẽ không còn visible dù tên xuất hiện gần đó trên màn hình.
- Lambda, bridge method, record constructors, generated proxy, framework bytecode có thể tạo những frame/tên method không viết trực tiếp trong source.
- Exception/`finally` và compiler-generated code có thể làm đường điều khiển đi qua những điểm không giống cú pháp nhìn bề ngoài.
- Khi JVM đang ở native method, line/local debugging theo source Java có giới hạn khác.

Nếu cần kiểm tra **bytecode nào đang chạy**, dùng `javap -c -l -p` trên đúng class:

```bash
javap -c -l -p -classpath out DebugFrameDemo
```

Tùy tình huống, thử **Step Into chọn lọc**, tắt step filters với phạm vi hẹp, hoặc breakpoint ở method entry thay vì ép `step` qua hàng trăm library frames. Có thể dùng `-Xint` để nghiên cứu hành vi interpreter trong test nhưng nó làm thay đổi hiệu năng/timing đáng kể; không coi đó là giải pháp mặc định cho bug production.

## 14. Khi có source nhưng không có debug info — vẫn làm được gì?

Trong một bản build với `-g:none`:

- JVM vẫn chạy Java bytecode bình thường; class/method/field descriptors còn để liên kết và thực thi.
- Có thể đặt **method entry breakpoint** hoặc dùng các công cụ quan sát class/method phù hợp, tùy hỗ trợ của JVM/debugger.
- Có thể đọc field của object/static khi có reference và quyền debug; không cần tên mọi local variable trong source.
- Có thể dùng `javap -c -p` để xem bytecode và quyết định điểm quan sát khác, dù không có source line mapping.
- Có thể bổ sung log/JFR/metrics ở bản build khác hoặc tái tạo cùng lỗi trên **staging có `-g`**.

Nhưng không thể lấy lại chính xác toàn bộ tên local, tên file và line mapping **chỉ bằng cách mở đúng source trong IDE** nếu bytecode không chứa thông tin tương ứng. Decompiler có thể dựng **source giả định** để hiểu control flow, không tái tạo được mọi biểu thức/biến gốc và không được coi là bằng chứng các line numbers gốc.

Các IDE có thể cố hiển thị tên tạm (`var1`, `arg0`) hoặc dùng thông tin từ compiler riêng; những tên này không phải lúc nào cũng là tên trong source. Phân biệt “debugger đoán/trình bày được giá trị” với “LocalVariableTable chứng minh tên và scope của biến”.

## 15. Workflow điều tra một breakpoint không khớp code

Khi debugger báo **“No executable code found at line”**, breakpoint không verified hoặc locals bị thiếu:

1. **Kiểm tra chương trình thật:** đúng PID/port, đúng main class, JDK/vendor, version của service và container/pod chưa?
2. **Kiểm tra class được nạp:** classpath/module-path, JAR/module, checksum/version của artifact, class loader. Có phiên bản `DebugFrameDemo` nào khác đang chạy không?
3. **Kiểm tra source:** file source bạn mở có đúng commit/build tương ứng class không? IDE có đang dùng source jar cũ không?
4. **Kiểm tra debug metadata:** chạy `javap -v -l -p` trên file `.class` **đúng build**. Có `SourceFile`, `LineNumberTable`, `LocalVariableTable` không?
5. **Kiểm tra vị trí dừng:** dòng có code thực thi, method có được gọi và condition có true không? Biến đã initialized/in scope chưa?
6. **Kiểm tra trạng thái thread:** đã suspend đúng thread không? Frame đang chọn là frame của method cần xem hay caller?
7. **Kiểm tra setting debugger:** disable breakpoint, suspend policy, class/exception filters, evaluation errors, compiler/IDE step filter.
8. **Thử tối giản:** build test với `javac -g`, chạy trực tiếp bằng `java -cp ...`, đặt method breakpoint, xác nhận locals/stepping rồi mới quay lại môi trường phức tạp.
9. **Đối chiếu hành vi:** nếu bug chỉ xảy ra khi timing tự nhiên, dùng JFR/logging/metrics thay vì thêm hàng chục breakpoint gây thay đổi lịch thread.
10. **Đóng phiên debug:** tháo JDWP nếu không còn cần; không để cổng mở, không lưu screenshot/variables chứa secret trong ticket công khai.

### Bảng quyết định nhanh

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Line breakpoint xám/unbound | `LineNumberTable`, class có load, source đúng build. | Compile `-g`/`-g:lines,source`, xác nhận artifact/line thực thi. |
| `locals` không có hoặc JDI `AbsentInformationException` | `LocalVariableTable` có tồn tại không? | Compile lại `-g` hoặc `-g:vars` với line/source phù hợp; attach đúng JVM. |
| Stack trace ghi `Unknown Source` hoặc không có line | `SourceFile`/`LineNumberTable` trong class. | Kiểm tra build debug info; không chỉ copy source. |
| Biến báo chưa available | Đang trước gán, ngoài scope, hoặc frame khác? | Step Over tới dòng sau gán, chọn đúng frame. |
| Giá trị khác source đang mở | Class/JAR đã deploy có lệch source? | Kiểm tra checksum/artifact, rebuild và redeploy test có kiểm soát. |
| Step Into đi vào thư viện/framework | Method order, compiler synthetic, step filters. | Smart Step Into (nếu IDE có), method breakpoint, chọn frame. |
| Breakpoint dừng nhiều lần/hết sức chậm | Vòng lặp, nhiều thread, conditional evaluation. | Hit count, filter phù hợp, log/JFR ít intrusive. |
| Main đứng ở `future.get()`, worker dừng ở handler | Hai thread có stack riêng. | Chuyển thread trong debugger, dùng trace cho async boundary. |
| Application timeout khi dừng | Breakpoint suspend all/lock/health checks. | Debug trên staging; giới hạn suspend và không pause production. |
| Attach không được | JVM không bật JDWP, sai bind port, network/permission. | Bật trên localhost/test, kiểm tra cổng và cấu hình JDWP an toàn. |

## 16. Lỗi thường gặp và cách sửa cách nghĩ

- **“Có source Java là IDE luôn xem được locals.”** Sai: tên/scope cần metadata của class, nhất là `LocalVariableTable`.
- **“`javac` mặc định luôn chứa tất cả debug info.”** Sai ở JDK 17: mặc định có source/lines, không mặc định local vars.
- **“`-parameters` đủ để xem `int raw` trong debugger.”** Sai: `MethodParameters` cho tên formal parameters qua reflection, không thay LocalVariableTable của locals.
- **“`-g:none` khiến mọi method breakpoint không thể dùng.”** Sai: thiếu line mapping/locals, nhưng method/class metadata vẫn còn.
- **“Step Over không chạy method được gọi.”** Sai: method chạy, chỉ debugger không đi sâu vào từng dòng của frame mới.
- **“Step Out nhảy qua những câu lệnh còn lại.”** Sai: vẫn thực thi đến khi trả về/unwind.
- **“Nếu break ở dòng gán, biến bên trái đã có giá trị mới.”** Sai: thường debugger dừng **trước khi** statement được thực thi.
- **“Stack trace luôn chứa giá trị biến.”** Sai: thông thường chỉ có method/file/line, không phải locals.
- **“Caller của callback async phải hiện trong stack của worker.”** Sai: stack frame theo thread, logical trace qua nhiều thread cần cơ chế riêng.
- **“Breakpoint không hit nghĩa là bug không xảy ra.”** Chưa chắc: breakpoint pending, class khác loader, source khác artifact hoặc condition sai.
- **“Giá trị trong conditional breakpoint luôn an toàn để evaluate.”** Sai: method evaluation có thể có side effect, lock và overhead.
- **“Thread suspend không ảnh hưởng ứng dụng.”** Sai: dễ gây timeout, deadlock và thay đổi timing race.
- **“Remote debug port chỉ là cổng quan sát read-only.”** Sai: JDWP có khả năng điều khiển/sửa trạng thái, phải bảo vệ nghiêm ngặt.
- **“`javap` in source gốc đầy đủ.”** Sai: nó xem bytecode và metadata; `SourceFile` chỉ là tên file.
- **“Debugger có thể đi ngược lại frame đã return chỉ bằng nút Up.”** Sai: Up/Down chỉ chọn **frame vẫn còn trong stack của thread đang dừng**.
- **“Dừng đúng thread là đã hiểu toàn bộ concurrency.”** Sai: shared state/lock/other threads có thể tiếp tục hoặc bị suspend tùy policy.

## 17. Checklist thực hành

Trước phiên debug:
- [ ] Biết **bản build và JVM đang chạy**, đúng source/commit/JAR.
- [ ] Với bài cần locals và source lines, compile bằng `javac -g`; xác minh `javap -v -p` khi nghi thiếu metadata.
- [ ] Phân biệt `SourceFile`, `LineNumberTable`, `LocalVariableTable` và `MethodParameters`.
- [ ] Chọn method/line breakpoint có executable bytecode; hạn chế conditional breakpoint ở hot path.
- [ ] Nếu remote debug, bind loopback trong môi trường thử nghiệm, kiểm soát quyền truy cập, không expose JDWP ra Internet.

Trong phiên debug:
- [ ] Quan sát thread nào bị dừng, suspend event thread hay suspend all.
- [ ] Mở call stack, chọn đúng frame và hiểu caller/callee.
- [ ] Xem parameter/local **sau thời điểm khởi tạo**, đúng lexical scope.
- [ ] Dùng Step Into/Over/Out theo câu hỏi điều tra; nhớ method vẫn thực thi khi Step Over.
- [ ] Với async, quan sát worker thread riêng và dùng correlation/trace khi cần logic xuyên thread.
- [ ] Ghi lại giá trị cần thiết nhưng tránh thông tin bí mật; phân biệt output chương trình với output debugger.

Sau phiên debug:
- [ ] Reproduce bằng test hoặc log/JFR để xác thực giả thuyết trong điều kiện ít intrusive.
- [ ] So sánh trước/sau thay đổi trên **cùng bản build/workload**.
- [ ] Gỡ breakpoint tốn kém, đóng debug session, tắt JDWP nếu không còn cần.
- [ ] Không tự kết luận JVM có lỗi vì source line “nhảy lạ” trước khi kiểm tra bytecode mapping.

**Ghi nhớ:** Breakpoint là **điểm dừng tại bytecode location**, stepping là cách chọn **ranh giới chạy tiếp**, stack frame là bối cảnh **một method invocation trên một thread**, local variables có **scope và lifetime riêng**. Muốn source-line debugging và xem tên locals chính xác, JDK 17 thường cần **`javac -g`**; chỉ mở source trong IDE không tạo lại được metadata bị thiếu từ `.class`. Luôn xác minh artifact, đúng thread/frame, thời điểm gán và tính an toàn của remote debugger.

### Tài liệu tham khảo chính thức

- [Oracle JDK 17 — `javac`: `-g`, `-g:none`, `-g:lines,vars,source` và `-parameters`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle JDK 17 — `javap`: `-l`, `-c`, `-v`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
- [Oracle JDK 17 — `jdb`: method/line breakpoint và `step`/`next`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdb.html)
- [Oracle JDK 17 — JPDA connection / `-agentlib:jdwp`](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html)
- [Oracle — JPDA FAQ: `AbsentInformationException` khi thiếu LocalVariableTable/LineNumberTable](https://www.oracle.com/java/technologies/javase/java-platform-debugger-architecture.html)
- [Oracle JDK 17 — JDI `StackFrame`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdi/com/sun/jdi/StackFrame.html)
- [Java SE 17 JVM Specification — các class-file attributes](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7)