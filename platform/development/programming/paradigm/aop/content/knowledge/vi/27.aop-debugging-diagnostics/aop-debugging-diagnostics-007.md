# Đặt điểm dừng trong advice, mã gốc và cơ chế gọi tiếp trong AOP

## 1. Tại sao cần đặt breakpoint ở ba nơi?

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), **pointcut** chọn các **join point**, còn **advice** bổ sung hành vi tại các join point đó. **Weaving** kết hợp aspect với mã chương trình ở thời điểm biên dịch, sau biên dịch hoặc khi nạp lớp. Việc debug trở nên khó hơn một lời gọi Java thông thường vì nhiều advice có thể bao lấy cùng một join point.

Muốn giải thích chính xác một ca lỗi, cần quan sát riêng:

1. **Trong advice:** điều kiện pointcut có khớp không, các biến bind có giá trị gì, nhánh nào đang chạy?
2. **Trong mã gốc:** thân phương thức nghiệp vụ đã chạy hay chưa, nhận tham số nào, trả kết quả gì hoặc ném lỗi gì?
3. **Ở cơ chế gọi tiếp (`proceed(...)`):** `around advice` có cho phép thực thi tiếp không, chuyển đối số nào, chạy bao nhiêu lần và trả về hoặc ném ngoại lệ ra sao?

**Breakpoint trong `around advice` không tự chứng minh thân mã gốc đã chạy.** Một `around` có thể return/throw trước khi gọi `proceed`. Ngược lại, breakpoint trong mã gốc không nói lên mọi advice đã chạy trước đó.

Các ví dụ sử dụng **AspectJ code-style** để minh họa cơ chế AOP dệt mã nói chung. File `.aj` cần compiler/weaver hỗ trợ; debugger có thể hiển thị các helper synthetic do bytecode weaving sinh ra, tùy IDE và phiên bản công cụ.

## 2. Những vị trí breakpoint quan trọng

| Nơi đặt breakpoint | Ý nghĩa chính | Cần kiểm tra thêm |
| --- | --- | --- |
| Dòng đầu `before advice` | Pointcut chọn join point và advice bắt đầu | Mã gốc đã chạy hay chưa |
| Dòng đầu `around advice` | Luồng đã tới lớp bao quanh | `proceed` có được gọi không |
| Ngay **trước** `proceed` | Giá trị/nhánh trước lúc tiếp tục | Còn advice nào nằm bên trong |
| Trong thân phương thức gốc | Thân gốc thật sự được thực thi | Tham số có bị thay đổi không |
| Ngay **sau** `proceed` | Đường tiếp tục đã trả về bình thường | Kết quả có bị biến đổi tiếp không |
| `catch`/`finally` trong around | Theo dõi đường lỗi và dọn dẹp | Lỗi bị ném lại hay bị chặn |
| `after returning` | Join point kết thúc bình thường | Giá trị trả về đã được bind đúng |
| `after throwing` | Join point kết thúc bằng exception phù hợp | Lỗi thoát từ tầng nào |
| `after` kiểu finally | Join point kết thúc theo cả hai đường | Đừng nhầm với `after returning` |
| Dòng sau lời gọi ở caller | Caller nhận điều khiển và kết quả | Không chạy nếu exception thoát ra |

`before`, `after returning`, `after throwing` và `after` không có cú pháp `proceed` để gọi tiếp như `around`. Các lời khuyên này có vai trò vòng đời khác nhau. Khi nhiều advice cùng khớp, thứ tự thật sự tùy **precedence** và mô hình triển khai; không suy đoán thứ tự chỉ từ cách viết source.

## 3. `proceed(...)` không chỉ là lời gọi Java thường

Trong **AspectJ code-style**, `proceed(...)` là cấu trúc đặc biệt bên trong `around advice`. Nó tiếp tục phần còn lại của phép tính ở join point, có thể đi qua advice khác rồi mới tới thân gốc. Với nhiều around, `proceed` của advice ngoài thường kích hoạt advice trong.

```text
caller
  |
around A: trước proceed
  |
proceed A --------------------+
                              |
                       advice B (nếu có)
                              |
                        mã gốc
                              |
                           return
                              |
around A: sau proceed <-------+
  |
caller
```

Sơ đồ minh họa một chuỗi có thứ tự xác định, không bảo đảm thứ tự của mọi hệ thống.

Các trường hợp đặc biệt:

- **`proceed` trả về bình thường:** lệnh ngay sau nó trong advice được thực thi và có thể đọc/sửa kết quả.
- **`proceed` ném ngoại lệ:** lệnh sau nó bị bỏ qua trừ khi có `catch`; `finally` vẫn chạy theo ngữ nghĩa Java.
- **Không có `proceed`:** thân join point tiếp theo có thể bị bỏ qua hoàn toàn vì around đã return hoặc throw.
- **Có nhiều `proceed`:** thân gốc có thể chạy nhiều lần trong một lần gọi của caller, nếu chuỗi advice cho phép.
- **`proceed` nhận tham số khác:** giá trị thân gốc nhận được có thể khác tham số lúc caller gọi.

Một debugger sử dụng **Step Into** tại `proceed` có thể đi vào helper, closure hoặc advice bên trong trước khi đến thân gốc. Vì vậy, phải đặt breakpoint trực tiếp trong thân gốc để kiểm chứng phần tính toán đã chạy.

## 4. Ví dụ hoàn chỉnh có thể biên dịch và debug

Ví dụ sử dụng Java 17+, AspectJ compiler (`ajc`) tương thích và `aspectjrt.jar`. `before`/`after` chọn `main` còn `around` chọn `Worker.doubleValue`; các loại advice này không cùng tranh một join point nên thứ tự minh họa rõ ràng.

### 4.1. `src/demo/Main.java`

```java
package demo;

public class Main {
    public static void main(String[] args) {
        int input = args.length == 0 ? 3 : Integer.parseInt(args[0]);
        System.out.println("main entered");

        Worker worker = new Worker();
        int result = worker.doubleValue(input);

        System.out.println("main result=" + result);
    }
}

class Worker {
    int doubleValue(int value) {
        System.out.println("worker value=" + value);
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return value * 2;
    }
}
```

### 4.2. `src/demo/TraceAspect.aj`

```aspectj
package demo;

public aspect TraceAspect {
    before(): execution(void demo.Main.main(String[])) {
        System.out.println("before main");
    }

    after(): execution(void demo.Main.main(String[])) {
        System.out.println("after main");
    }

    pointcut doubling(int value):
        execution(int demo.Worker.doubleValue(int))
        && args(value);

    int around(int value): doubling(value) {
        System.out.println("around enter=" + value);

        try {
            int result = proceed(value);
            System.out.println("around returned=" + result);
            return result;
        } finally {
            System.out.println("around finally");
        }
    }
}
```

Giải thích:

- `execution(void demo.Main.main(String[]))` chọn việc **thực thi** `main`, do đó `before main` chạy lúc vào và `after main` chạy khi kết thúc.
- `execution(int demo.Worker.doubleValue(int))` chọn việc **thực thi** phương thức `doubleValue`. `args(value)` bind tham số vào advice.
- `proceed(value)` tiếp tục phép tính và trả về số nguyên nếu thành công. Dòng `around returned=...` chỉ xuất hiện trên đường return bình thường.
- Khối `finally` bảo đảm dòng `around finally` được thực thi khi `proceed` trả về hoặc ném exception trong cơ chế unwind thông thường.
- Nhánh `value < 0` cung cấp ca lỗi để thử exception breakpoint và xác nhận dòng sau `proceed` bị bỏ qua.

### 4.3. Biên dịch và chạy có thông tin debug

Giả sử `ajc` đã được cài trên PATH và `aspectjrt.jar` đặt ở thư mục chạy lệnh.

**Windows PowerShell:**

```powershell
ajc -17 -g -preserveAllLocals -showWeaveInfo -d out -classpath "aspectjrt.jar" src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out;aspectjrt.jar" demo.Main
```

**Linux/macOS:**

```bash
ajc -17 -g -preserveAllLocals -showWeaveInfo -d out -classpath aspectjrt.jar src/demo/Main.java src/demo/TraceAspect.aj
java -cp "out:aspectjrt.jar" demo.Main
```

Ý nghĩa các cờ: `-g` sinh debug symbols (line, vars, source); `-preserveAllLocals` cố giữ các biến cục bộ để inspect; `-showWeaveInfo` giúp xác nhận advice được dệt vào lớp/điểm nối nào. Nếu hệ thống build của IDE tạo một bản class Java chưa dệt, cần sửa cấu hình để Debug dùng **output của `ajc`**.

**Stdout kỳ vọng** khi chạy mặc định, input `3`:

```text
before main
main entered
around enter=3
worker value=3
around returned=6
around finally
main result=6
after main
```

Với `demo.Main -1`, các dòng **stdout** trước khi lỗi thoát ra là:

```text
before main
main entered
around enter=-1
worker value=-1
around finally
after main
```

JVM còn in stack trace `IllegalArgumentException: negative` lên stderr; dòng stderr có thể hiển thị xen kẽ stdout tùy terminal. Hai dòng `around returned=...` và `main result=...` không xuất hiện vì `proceed` không trả về bình thường.

## 5. Quy trình breakpoint theo thứ tự dễ kiểm chứng

Đặt các điểm dừng vào **dòng có lệnh thực thi** trong mã nguồn:

| Mã | Vị trí | Giá trị hoặc hành vi cần quan sát |
| --- | --- | --- |
| BP1 | `before`: dòng in `before main` | Advice `before` bắt đầu |
| BP2 | `Main.main`: dòng in `main entered` | Bắt đầu mã gốc `main` |
| BP3 | `around`: dòng in `around enter=...` | Around match; `value=3` |
| BP4 | `around`: dòng `int result = proceed(value);` | Trước khi gọi tiếp; tham số `value=3` |
| BP5 | `Worker.doubleValue`: dòng in `worker value=...` | Thân gốc được gọi với `value=3` |
| BP6 | `around`: dòng in `around returned=...` | `proceed` quay về; `result=6` |
| BP7 | `around`: dòng in `around finally` | Dọn dẹp ở cả đường return/throw |
| BP8 | `Main.main`: dòng in `main result=...` | Caller nhận `result=6` |
| BP9 | `after`: dòng in `after main` | Kết thúc join point `main` |

Dùng **Resume** liên tiếp trên đường input dương để kiểm tra BP1 → BP9. Ở mỗi breakpoint, ghi **thread**, **call stack**, **frame đang chọn**, **binding trong advice**, **tham số tại thân gốc** và **giá trị trả về**. Biến `value` trong advice và biến `value` của phương thức gốc không phải cùng local variable dù cùng tên.

Với input `-1`, bật **Exception Breakpoint** trên `IllegalArgumentException`: breakpoint trong `Worker` cho thấy dữ liệu gây lỗi; BP6 và BP8 không dừng; BP7 và BP9 vẫn chạy khi tiếp tục. Nếu debugger hỗ trợ cả “caught” và “uncaught”, cần chọn chế độ mong muốn để tránh bỏ sót lỗi bị advice xử lý.

### 5.1. Step Into, Step Over và Step Out

- **Step Into** ngay tại `proceed(value)`: có thể chuyển vào helper/around khác, không nhất thiết chạm `Worker` ngay. Giữ BP5 để xác minh.
- **Step Over** tại `proceed(value)`: vẫn thực thi toàn bộ lời gọi tiếp và có thể dừng tại BP5; nếu trả về bình thường, dừng ở lệnh tiếp theo trong advice.
- **Step Out** trong `Worker`: có thể trở lại helper hoặc frame của aspect, không hẳn trở thẳng về `Main`.
- **Continue/Resume**: giảm phụ thuộc vào debug mapping của các synthetic frame.
- **Conditional breakpoint**: chỉ dừng khi `value == 7`, hoặc hit count thứ N, hữu ích với join point được gọi rất nhiều lần.

Nếu debugger không hỗ trợ breakpoint ở `.aj` hoặc hiển thị *unverified*, hãy kiểm tra plugin/integration, debug symbols, thời điểm dệt, line number table và artifact đang chạy trước khi chỉnh pointcut.

## 6. `call` và `execution` tạo breakpoint ở vị trí khác nhau

Trong AspectJ:

- `call(int demo.Worker.doubleValue(int))`: chọn vị trí **gọi phương thức** trong `Main.main`, miễn mã caller nằm trong phạm vi dệt.
- `execution(int demo.Worker.doubleValue(int))`: chọn thời điểm **thân phương thức được thực thi** trong `Worker`.

```text
Main.main:
  result = worker.doubleValue(input)
           ^ shadow cho call
                     |
                     v
Worker.doubleValue:
  ^ shadow cho execution
  [breakpoint ở dòng thân phương thức]
```

Nếu caller không được dệt, `call` có thể không áp dụng dù `execution` trong callee đã được dệt. Hai pointcut có thể khác nhau ở số join point và ngữ nghĩa; không đổi loại chỉ để dễ debug. Nếu advice ở `call` bị dừng trước khi `Worker` vào thân, đó là hợp lý.

## 7. Khi around có nhiều tầng, bỏ qua hoặc nhân đôi gọi tiếp

### 7.1. Nhiều around và thứ tự precedence

Giả sử aspect A là lớp ngoài và B là lớp trong theo precedence đã xác minh:

```text
Caller
  -> around A: before
       -> proceed A
            -> around B: before
                 -> proceed B
                     -> thân gốc
                 <- around B: after
       <- around A: after
  <- Caller
```

`proceed` của A vào B trước khi đến gốc. Breakpoint ở synthetic helper không có nghĩa thân gốc đã bị gọi lặp; cần đếm lần vào `Worker`. Khi có nhiều advice, xác minh cấu hình precedence và trình dệt trước khi kết luận.

### 7.2. Short-circuit: không gọi `proceed`

Đoạn sau **thay thế riêng** cho around trong ví dụ, không thêm cạnh around cũ:

```aspectj
int around(int value):
    execution(int demo.Worker.doubleValue(int)) && args(value) {
    if (value == 0) {
        return 0;
    }
    return proceed(value);
}
```

Nếu input `0`, breakpoint nhánh return dừng nhưng breakpoint ở thân gốc không dừng, do advice đã trả kết quả mà không tiếp tục. Điều này có thể là thiết kế hợp lệ (cache/short-circuit) hoặc lỗi nghiệp vụ; phải xác nhận yêu cầu.

### 7.3. Đổi đối số khi gọi tiếp

```aspectj
int around(int value):
    execution(int demo.Worker.doubleValue(int)) && args(value) {
    return proceed(value + 1);
}
```

Nếu caller truyền `3`, thân gốc nhận `4` và trả `8`. Khi debug, đối chiếu tham số ở ba nơi: caller, around và thân gốc. Trong AspectJ code-style, tham số `proceed(...)` gắn với binding của advice; các phong cách khai báo advice khác có quy tắc ánh xạ tham số khác nhau, không sao chép cơ học.

### 7.4. Gọi `proceed` nhiều lần

```aspectj
int around(int value):
    execution(int demo.Worker.doubleValue(int)) && args(value) {
    int first = proceed(value);
    int second = proceed(value);
    return first + second;
}
```

Với `value=3`, thân `Worker` được gọi hai lần, mỗi lần cho `6`, kết quả caller là `12`. Nếu tính toán có side effect như ghi cơ sở dữ liệu hoặc thanh toán, điều này có thể không chấp nhận được. Breakpoint trong mã gốc và số lượt hit cho biết tình huống gọi tiếp nhiều lần.

## 8. Gỡ lỗi exception và đường trả về

```text
around -> proceed(...)
             |
             +-- bình thường --> dòng sau proceed -> finally
             |
             +-- throw -------> catch nếu có -> finally
```

Nếu exception thoát khỏi `proceed`, dòng ngay sau `proceed` không chạy. Nếu around **bắt lỗi và trả về giá trị thay thế**, các advice khác ở tầng ngoài có thể quan sát kết thúc bình thường; vì vậy, ý nghĩa “returning” hoặc “throwing” phụ thuộc join point và precedence chính xác.

Quy trình điều tra: đặt exception breakpoint tại vị trí `throw` gốc, kiểm tra `catch`/`finally` trong around, kiểm tra `after throwing` và `after returning` nếu có, cuối cùng xác nhận caller nhận kết quả hay exception. Chỉ nhìn breakpoint sau call ở caller có thể bỏ qua lỗi đã được xử lý trong advice.

## 9. Vì sao debugger không dừng như kỳ vọng?

### 9.1. Advice không dừng nhưng mã gốc vẫn chạy

Kiểm tra (1) chữ ký và loại `call`/`execution`, overload, `within`, `if`, `cflow` và binding; (2) thông tin `-showWeaveInfo` xác nhận có woven shadow; (3) output class thực thi có phải phiên bản **đã dệt**; (4) debugger đã bind breakpoint vào class thật; (5) class loader và phạm vi cấu hình load-time weaving; (6) điều kiện động của pointcut có đang false.

### 9.2. Advice dừng nhưng mã gốc không dừng

Có thể quanh join point short-circuit trước `proceed`, quanh tầng trong không gọi tiếp, `proceed` ném exception, hoặc breakpoint đang nằm ở overload/class không được thực thi. Đặt ba breakpoint trước `proceed`, trong thân gốc và sau `proceed` để tách nguyên nhân.

### 9.3. Thân gốc dừng nhiều lần

Kiểm tra số lần `proceed`, đệ quy, retry, vòng lặp, các thread/caller khác nhau và breakpoint ở phương thức dùng chung. Đối chiếu **call stack và thread** thay vì kết luận ngay weaving đã chèn trùng advice.

### 9.4. Debugger nhảy vào synthetic helper hoặc dòng không như source

Weaver có thể sinh helper/closure và biến đổi dòng bytecode. Điều chỉnh bộ lọc Step Into nếu IDE hỗ trợ, dùng breakpoint cố định, kiểm tra **line numbers** và **bytecode sau dệt**:

```bash
javap -classpath out -c -l -p demo.Worker
javap -classpath out -c -l -p demo.Main
```

`-c` in bytecode; `-l` in thông tin debug theo line/local; `-p` hiển thị thành viên không public. Đừng dựa vào tên helper cụ thể vì trình dệt và phiên bản có thể thay đổi. Nếu mã nguồn khác bytecode đang chạy, rebuild/reweave rồi restart debugger khi cần.

## 10. Weaving time, source mapping và các biến ngữ cảnh

| Cách dệt | Điều quan trọng khi debug |
| --- | --- |
| **Compile-time** | `ajc` tạo class đã dệt; IDE phải chạy đúng output đó |
| **Post-compile** | Runtime phải dùng artifact đã dệt, không dùng bản class gốc còn trong classpath |
| **Load-time** | Weaver/agent phải được kích hoạt trước khi class liên quan được load và dùng đúng class loader |

Nguồn `.aj` tồn tại trong IDE chưa bảo đảm advice đã được weave. Giữ **source, symbols, class output và debugger session** từ cùng một lần build. Hot-swap Java thông thường có thể không thay thế được các biến đổi cấu trúc của bytecode dệt.

Trong AspectJ advice, có thể xem metadata join point bằng `thisJoinPointStaticPart`, `thisJoinPoint.getSignature()`, `thisJoinPoint.getArgs()`, `thisJoinPoint.getThis()`, `thisJoinPoint.getTarget()` tùy loại join point. `getThis()` hoặc `getTarget()` có thể `null` ở ngữ cảnh thích hợp. Không nhầm `this` của instance aspect với đối tượng nghiệp vụ của join point. Expression evaluation có thể thực thi getter/`toString()` gây side effect, I/O hoặc khóa; ưu tiên inspect biến cục bộ thuần.

## 11. Debug an toàn ở đường nóng và đa luồng

AOP có thể chặn những phương thức được gọi hàng triệu lần; dừng mọi breakpoint làm thay đổi lịch luồng và có thể che race condition. Sử dụng **conditional breakpoint**, **hit count**, **thread filter**, **logpoint/tracepoint** (nếu IDE hỗ trợ), và **exception breakpoint** để tập trung vào ca lỗi. Biểu thức điều kiện trong debugger nên thuần, đơn giản và không làm thay đổi đối tượng.

Khi lỗi phụ thuộc timing, kết hợp dữ liệu của debugger với trace/log/JFR/profiler ít can thiệp hơn. Với công việc bất đồng bộ, đừng mặc định các bước ở hai thread thuộc cùng một chuỗi gọi; luôn kiểm tra thread ID và dữ liệu định danh phiên xử lý.

## 12. Các sai lầm thường gặp

- **“Break trong around chứng tỏ thân gốc đã chạy.”** Sai: `proceed` có thể chưa được gọi.
- **“Step Over tại `proceed` bỏ qua thân gốc.”** Sai: lời gọi tiếp vẫn thực thi; chỉ khác cách trình bày stepping.
- **“Step Into tại `proceed` bắt buộc đi thẳng vào phương thức gốc.”** Sai: có thể vào advice khác hoặc helper tổng hợp.
- **“Dòng sau `proceed` luôn chạy.”** Sai nếu có exception hoặc đường điều khiển khác.
- **“`after` đồng nghĩa `after returning`.”** Sai: `after` kiểu finally còn chạy khi ném lỗi.
- **“`call` và `execution` chọn cùng một vị trí.”** Sai: caller và callee khác nhau.
- **“Synthetic frame là bằng chứng mã gốc chạy nhiều lần.”** Không; cần đếm lượt vào thân gốc.
- **“Dùng `this` trong aspect để xác định target là đủ.”** Không; phải xét ngữ cảnh join point và đúng stack frame.
- **“Không hit breakpoint chứng tỏ pointcut sai.”** Có thể chưa dệt, runtime chạy nhầm artifact hoặc thiếu source debug mapping.
- **“Đặt breakpoint vô điều kiện ở mọi advice luôn tốt.”** Quá nhiều điểm dừng có thể làm méo timing và khó nhìn luồng thực.

## 13. Checklist thực hành

1. Xác định pointcut thực sự muốn debug và loại `call`/`execution`.
2. Bảo đảm class đã dệt, đúng nguồn và có debug symbols; kiểm tra `-showWeaveInfo`.
3. Đặt breakpoint tối thiểu **trước `proceed`**, **trong mã gốc**, **sau `proceed`**.
4. Bổ sung breakpoint ở caller trước/sau lời gọi; đánh dấu ca return, throw và finally.
5. Kiểm tra biến bind trong advice và đối số thật của thân phương thức; xác nhận stack frame/thread.
6. Với nhiều around, kiểm tra precedence, tầng gọi tiếp và số lần `proceed` thực thi.
7. Nếu debugger stepping lạ, đọc log dệt và bytecode rồi đối chiếu đúng artifact.
8. Khi lỗi đa luồng hoặc đường nóng, dùng điều kiện/hit count và trace ít can thiệp.
9. Kết luận bằng bằng chứng: **advice nào khớp, thân gốc chạy bao nhiêu lần, kết quả/exception đi đâu**.

**Kết luận:** để hiểu luồng AOP, cần kết hợp breakpoint ở advice, thân mã gốc và vị trí `proceed`, rồi kiểm chứng cả đường trả về bình thường lẫn đường ngoại lệ. Khi thấy mã tổng hợp hoặc thứ tự lạ, hãy xem source map, precedence và bytecode đã dệt trước khi kết luận chương trình chạy sai.

## Tài liệu tham khảo

- AspectJ Programming Guide — ngữ nghĩa advice và `proceed`: https://eclipse.dev/aspectj/doc/latest/progguide/semantics-advice.html
- AspectJ Language — các loại advice, `call` và `execution`: https://eclipse.dev/aspectj/doc/latest/progguide/language.html
- AspectJ Development Guide — `ajc`, `-g`, `-preserveAllLocals` và `-showWeaveInfo`: https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html
- AspectJ annotation-style advice — khác biệt ánh xạ tham số `proceed`: https://eclipse.dev/aspectj/doc/latest/adk15notebook/ataspectj.html
