# Dùng debugger quan sát this, trường, tham số và đối tượng trong Java 17+

> **Module:** Java Core — class/object  
> **Nhóm:** Thiết kế và thực hành  
> **Chủ đề trực tiếp:** Dùng debugger quan sát `this`, trường, tham số và đối tượng  
> **Môi trường:** JDK 17+; hướng dẫn sử dụng debugger của IDE hoặc `jdb` có sẵn trong JDK.

## 1. Kết quả cần đạt

Sau bài học, người học có thể **tạm dừng chương trình tại một câu lệnh cụ thể, chọn stack frame, xem giá trị hiện tại của `this`, fields, parameters, local variables và các objects liên quan**, rồi theo dõi sự thay đổi khi bước qua từng câu lệnh.

Các tình huống quan trọng nhất:

- Trong constructor `Person(String name)`, phân biệt **tham số `name`** với **trường `this.name`**.
- Trong method `account.deposit(int amount)`, thấy `this` trỏ tới **account đang nhận lời gọi**; mỗi lần gọi trên object khác có `this` khác.
- Khi một method nhận tham số có kiểu class, thấy tham số là **bản sao của reference value**: có thể sửa object qua reference đó, nhưng gán tham số sang object mới không đổi biến reference phía caller.
- Thấy **call stack** gồm những methods nào đang hoạt động và biến nào thuộc **frame** nào.
- Biết khi nào dùng **Step Over**, **Step Into**, **Step Out**, **Resume**, **Variables**, **Watches** và **Evaluate Expression**.
- Đọc **object graph** qua debugger: field trỏ tới object nào; hai references có trỏ cùng một instance hay không.
- Tránh hiểu nhầm **static field** là field của riêng từng object, và tránh tin rằng mọi lời gọi getter/toString trong debugger luôn vô hại.
- Dùng `javac -g` để giữ **local variable debug information**, rồi làm một buổi thực hành `jdb` tái lập được không phụ thuộc một IDE duy nhất.

**Debugger cho phép quan sát một lần thực thi cụ thể; nó không tự chứng minh mọi execution khác cũng có cùng dữ liệu hay cùng thứ tự threads.** Phải kết hợp với kiến thức về Java semantics, assertions và tests.

## 2. Debugger khác System.out.println ở điểm nào?

`System.out.println` cung cấp log tại những vị trí đã viết trước. Debugger cho phép đặt một **breakpoint** để tạm dừng ngay trước/sau một bước phù hợp của chương trình, xem các variables hiện có rồi tiếp tục theo từng câu lệnh.

| Nhu cầu | Print/log | Debugger |
| --- | --- | --- |
| Xem một field ở một nơi đã biết | Thêm lệnh print | Chọn stack frame, mở object fields |
| Biết method nào gọi method đang chạy | Thêm log hoặc stack trace | Xem Call Stack/Frames trực tiếp |
| Xem local variable trong method | Phải sửa source/log | Variables pane hoặc `locals` của `jdb` |
| Thấy khác biệt field/parameter trùng tên | Print cả `name` và `this.name` | Cùng một frame, xem cả hai biểu thức |
| Đi vào method được gọi | Chèn thêm log trong method con | Step Into |
| Bỏ qua chi tiết method con | Giảm log thủ công | Step Over |
| Quay về caller | Thêm log sau lời gọi | Step Out |
| Theo dõi mutation object qua nhiều aliases | In nhiều giá trị | Inspect object graph và identity |
| Quan sát thread khác | Tự chèn log thread ID | Threads/Frames pane hoặc `threads` trong `jdb` |
| Lưu thông tin production lâu dài | Có, log/telemetry phù hợp | Không thay logging/monitoring production |

Debugging rất hữu ích khi **học Java Core**, vì có thể quan sát quy tắc thay vì chỉ đọc định nghĩa. Nhưng khi lỗi có race/concurrency hoặc chỉ xuất hiện ở production, breakpoint có thể làm thay đổi timing; cần logs, tests, profiler và các công cụ bổ sung.

## 3. Mô hình tư duy: Stack frame, local, parameter, field và object

Ví dụ:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int amount) {
        int before = value;
        value += amount;
        System.out.println(before + " -> " + value);
    }
}
~~~

Đây là **class fragment**, chưa có `main`.

Giả sử caller có `Counter first = new Counter(10)` và gọi `first.add(3)`. Khi dừng bên trong method `add`, hãy tưởng tượng:

~~~text
Call stack:
  [frame hiện tại] Counter.add(amount=3)
      this ------------> Counter object #A
      amount = 3        | value = 10 (trước phép cộng)
      before = 10       |
  [frame caller] SomeMain.main(...)
      first -----------> cùng Counter object #A

Heap (mô hình minh họa):
  Counter object #A
      value: 10
~~~

**Các quan hệ cần nhớ:**

1. `this` là reference tới **object nhận lời gọi instance method**.
2. `amount` là một **parameter local của invocation hiện tại**, không là field.
3. `before` là **local variable** ở frame hiện tại, tồn tại theo scope/liveness của method.
4. `value` là **instance field** nằm trong object #A; nhiều method calls trên cùng object cùng tác động tới field đó.
5. `first` là biến local của **caller frame**, không phải local của `add`.
6. Debugger hiển thị frames để bạn chọn context. Muốn xem `first`, chuyển về frame caller; muốn xem `amount`, chọn frame `add`.
7. Các nhãn object #A/#B chỉ là ký hiệu giảng giải, **không phải object ID được Java chuẩn bảo đảm hay địa chỉ RAM bắt buộc debugger phải in**.

### 3.1. Field không phải biến local

Một field thuộc instance (`this.value`) tồn tại theo object. Một local variable (`before`) thuộc invocation/scope. Lời gọi method lần thứ hai có local `before` mới, dù vẫn dùng cùng field value.

### 3.2. Tham số cũng là local variable của lần gọi

Mỗi invocation có giá trị tham số riêng. Nếu Java method `add(int amount)` được gọi lần lượt với 3 rồi 5, hai lần gọi không dùng chung một parameter slot mang business state.

### 3.3. Object có thể được nhiều frames tham chiếu

Nếu caller giữ `first` còn callee giữ `this`, hai references có thể trỏ tới cùng object. Debugger hiển thị chúng ở những frames khác nhau nhưng mutation đến cùng heap object.

### 3.4. Không diễn giải ảnh debugger như layout heap tuyệt đối

IDE thường hiển thị fields, references và object labels có dạng riêng. Đây là **giao diện biểu diễn Java values**. JVM có thể tối ưu allocation, field layouts, references và stack maps; đừng coi nhãn object ID hoặc vị trí trong Variables pane là cam kết binary memory layout.

## 4. Chuẩn bị môi trường để debug

Bạn cần một JDK 17 trở lên, không chỉ JRE tối giản, để sử dụng `javac` và `jdb`.

Kiểm tra trong terminal:

~~~bash
java -version
javac -version
jdb -help
~~~

Các lệnh trên là lệnh công cụ; phiên bản cụ thể, help text và exit status phụ thuộc JDK được cài, nên bài này **không đưa một stdout cố định** cho chúng.

### 4.1. Biên dịch có đủ debug information

~~~bash
javac -g -encoding UTF-8 DebuggerBasicsDemo.java
~~~

Flag `-g` yêu cầu compiler sinh thông tin phục vụ debug, gồm **source lines, source file và local variable data** theo lựa chọn thông thường của `javac`.

Mặc định, javac thường đã sinh line number và source file information nhưng **không nhất thiết sinh local variable name tables**. Do vậy khi muốn dùng `jdb locals` hoặc xem parameters bằng tên gốc trong debugger, nên **dùng `-g`**.

Có thể chỉ định chi tiết:

~~~bash
javac -g:lines,vars,source -encoding UTF-8 DebuggerBasicsDemo.java
~~~

Đây là ví dụ flag hợp lệ của `javac`. Với IDEs, hệ thống build thường đã cấu hình debug symbols; hãy kiểm tra build settings nếu thấy local variable names không hiện.

### 4.2. Source phải khớp class file đang chạy

Một lỗi rất thường gặp là sửa file Java nhưng chạy/debug file `.class` cũ. Trước khi bắt đầu, biên dịch lại source đúng và xem classpath/module path IDE đang dùng.

### 4.3. Ưu tiên Debug thay vì Run trong IDE

Trong IntelliJ IDEA, Eclipse, VS Code Java extension hoặc IDE khác, chọn cấu hình **Debug** phù hợp thay vì Run. Đặt breakpoint ở một executable line. Tên nút và phím tắt có thể khác phiên bản/keyboard scheme, nhưng những khái niệm Breakpoints, Frames, Variables và Step commands tương tự nhau.

### 4.4. Một breakpoint không phải câu lệnh chạy một lần trong source

Breakpoint là một yêu cầu từ debugger; nó không trực tiếp sửa Java source semantics như thêm `System.out.println`. Nhưng việc dừng chương trình có thể ảnh hưởng timing, lock contention và các tương tác với threads khác.

## 5. Chương trình hoàn chỉnh 1 — this, field bị che tên và tham số

Tạo tệp **`DebuggerBasicsDemo.java`**:

~~~java
public class DebuggerBasicsDemo {
    static final class Meter {
        private int count;

        Meter(int count) {
            this.count = count;
        }

        int add(int count) {
            int before = this.count;
            this.count = Math.addExact(this.count, count);
            return before;
        }

        int count() {
            return count;
        }
    }

    public static void main(String[] args) {
        Meter first = new Meter(10);
        Meter second = new Meter(100);

        int beforeFirst = first.add(3);
        int beforeSecond = second.add(5);

        System.out.println("First before = " + beforeFirst);
        System.out.println("First now = " + first.count());
        System.out.println("Second before = " + beforeSecond);
        System.out.println("Second now = " + second.count());
        System.out.println("Different objects = " + (first != second));
    }
}
~~~

Biên dịch và chạy bình thường:

~~~bash
javac -g -encoding UTF-8 DebuggerBasicsDemo.java
java DebuggerBasicsDemo
~~~

**Stdout chính xác:**

~~~text
First before = 10
First now = 13
Second before = 100
Second now = 105
Different objects = true
~~~

### 5.1. Constructor parameter che tên field

Trong `Meter(int count)`, biểu thức `count` mặc định trỏ tới parameter. `this.count` trỏ tới field của Meter đang được tạo. Câu lệnh `this.count = count` chép giá trị tham số vào field.

Khi debugger dừng tại constructor, kiểm tra **cả `count` và `this.count`**. Nếu dừng trước câu gán, field `this.count` còn default value 0; sau Step Over câu gán, nó có giá trị 10 hoặc 100.

### 5.2. Cùng tên trong method `add` có hai ý nghĩa

Trong `add(int count)`:

- `count`: số lượng muốn cộng, là **parameter**.
- `this.count`: số đếm hiện tại lưu trên object.
- `before`: local copy của field value trước cập nhật.

Ở invocation `first.add(3)`, nhìn thấy parameter=3, field=10 trước câu update. Ở `second.add(5)`, parameter=5, field=100. Cùng một method body nhưng hai receivers khác nhau.

### 5.3. Điều xảy ra sau Step Over

Đặt breakpoint tại:

~~~java
this.count = Math.addExact(this.count, count);
~~~

Trước execution, `this.count` còn 10/100. Sau khi Step Over đúng dòng đó, field đã thành 13/105. Parameter `count` vẫn 3/5; local `before` vẫn 10/100.

### 5.4. Vì sao `first != second` true?

Hai lần `new Meter` tạo hai object references khác nhau theo semantics chương trình này. `this` ở hai calls không giống nhau, và thay field ở object first không làm field second đổi.

## 6. Thao tác debugger trong IDE: quy trình đọc Variables pane

Với chương trình `DebuggerBasicsDemo`:

1. Mở file, đặt breakpoint ở câu `this.count = Math.addExact(...)` trong `Meter.add`.
2. Chọn **Debug** cho main class `DebuggerBasicsDemo`.
3. Khi chương trình dừng ở breakpoint, nhìn **Call Stack/Frames**. Frame hiện tại là `Meter.add`, caller là `DebuggerBasicsDemo.main`.
4. Trong **Variables**, tìm `this`, parameter `count` và local `before`.
5. Mở rộng `this` để thấy field `count`.
6. Dùng **Evaluate Expression** hoặc Watch để so `count`, `this.count`, `before`, `this == first` nếu biến caller hiện ở frame context phù hợp. `first` thường không visible khi bạn đang chọn frame `Meter.add`; muốn xem `first`, chọn frame `main`.
7. Chọn **Step Over** để chạy phép cộng, nhìn field count mới.
8. Chọn **Resume/Continue** để tới lần gọi `second.add(5)`; so sánh `this` và field.
9. Chọn frame `main` khi chương trình đang dừng, quan sát `first` và `second` cùng tồn tại.
10. Gỡ breakpoint hoặc tiếp tục tới hết chương trình.

**Chú ý:** bước diễn ra trước hay sau side effect phụ thuộc **vị trí breakpoint và line mapping**. Nếu đặt breakpoint trên một statement, nó thường dừng **trước khi statement đó hoàn tất**. Khi một dòng Java biên dịch thành nhiều bytecodes, IDE có thể đưa bạn qua nhiều vị trí tùy stepping mode. Hãy xác nhận bằng việc xem field trước/sau.

### 6.1. Variables pane và Watch expression khác nhau

Variables pane thường liệt kê các variables có thể thấy trong frame cùng object fields. Watch là **biểu thức bạn chủ động yêu cầu đánh giá**, ví dụ `this.count` hoặc `first == second`.

Watch có thể bị đánh giá nhiều lần mỗi lần chương trình dừng; tránh biểu thức có side effects.

### 6.2. Đừng đánh giá tên parameter trong frame caller rồi tưởng nó “mất”

`count` trong `Meter.add` thuộc callee frame; khi chuyển sang `main`, biến ấy không phải local của main. Một số IDE hiển thị symbol ở frame hiện tại, nên phải chọn đúng frame trước khi phân tích.

### 6.3. Object labels trong debugger không phải equals semantics

IDE có thể hiển thị Meter@hash-like-label. Dấu nhãn đó không phải business identity được Java hứa cố định. Muốn kiểm tra có cùng reference, dùng `==` giữa references; muốn kiểm tra giá trị domain, dùng những fields/accessors/equals theo contract.

## 7. Thực hành jdb — debugger dòng lệnh thuộc JDK

Nếu không dùng IDE, có thể dùng **`jdb`** để đặt breakpoint và xem frames/variables.

Biên dịch:

~~~bash
javac -g -encoding UTF-8 DebuggerBasicsDemo.java
~~~

Khởi động:

~~~bash
jdb DebuggerBasicsDemo
~~~

Sau khi jdb khởi chạy và hiện prompt, nhập các lệnh **từng dòng trong jdb**:

~~~text
stop in DebuggerBasicsDemo$Meter.add
run
where
locals
print count
print this.count
print before
next
print this.count
cont
~~~

Đây là **ví dụ thao tác tương tác**. Prompt/debugger diagnostics, line numbers, thread IDs, object IDs và chính xác vị trí dừng **không được xem là stdout cố định**. Cú pháp tên nested class trong bytecode thường dùng dấu `$`: `DebuggerBasicsDemo$Meter`.

### 7.1. `stop in`

`stop in DebuggerBasicsDemo$Meter.add` yêu cầu dừng khi vào method add. Bạn cũng có thể đặt breakpoint theo source line bằng cú pháp `stop at ClassName:lineNumber` nếu biết line mapping.

### 7.2. `run`

Chạy target program trong debug session. Khi breakpoint được chạm, jdb dừng và cho tương tác.

### 7.3. `where`

Hiển thị stack trace của thread/frame hiện tại. Nó giúp biết đang ở `Meter.add` và ai đã gọi từ `main`.

### 7.4. `locals`

Hiển thị local variables/arguments mà debug information và trạng thái frame cho phép. Nếu không thấy tên local, kiểm tra `javac -g`, đúng class file và nơi dừng (trước khi biến được khởi tạo chưa thể đọc giá trị đáng tin).

### 7.5. `print` và `dump`

`print count` đánh giá parameter/local expression; `print this.count` đánh giá field. `dump this` có thể hữu ích khi inspect object fields. Các lệnh đánh giá biểu thức có thể tương tác với application code; chỉ dùng expressions an toàn khi đang tìm lỗi.

### 7.6. `next`, `step`, `step up` và `cont`

- `next`: đi qua lời gọi ở cùng frame (Step Over).
- `step`: đi vào call phù hợp (Step Into).
- `step up`: chạy đến khi rời method hiện tại (Step Out).
- `cont`: tiếp tục cho đến breakpoint/event khác.

Lệnh tương ứng có thể tạm dừng ở điểm khác nhau do source map, bytecode, exception hoặc các threads khác; mô hình ý nghĩa là điều cốt lõi.

### 7.7. Phân biệt Watch trong IDE và `watch` của jdb

Trong IDE, Watch thường là **expression được đánh giá**. Trong `jdb`, lệnh `watch` thường liên quan **field access/modification watchpoints** (ví dụ `watch all Class.field`), **không phải** tạo một Watch-expression pane. Đừng học lệnh của công cụ này rồi áp cho công cụ kia.

### 7.8. Trên Windows PowerShell

Lệnh `jdb DebuggerBasicsDemo` chạy bình thường nếu JDK nằm trong PATH. Chuỗi `DebuggerBasicsDemo$Meter.add` được **gõ bên trong jdb interactive prompt** trong ví dụ, nên không bị PowerShell nội suy như biến. Nếu tự nhúng tên có ký tự `$` vào một shell command, hãy chú ý quoting riêng cho shell.

## 8. Step Over, Step Into, Step Out: nhìn thấy gì?

Giả sử:

~~~java
int total = calculatePrice(quantity, unitPrice);
System.out.println(total);
~~~

Tại breakpoint ở dòng gọi `calculatePrice`:

| Thao tác | Ý nghĩa | Quan sát thường mong đợi |
| --- | --- | --- |
| Step Into | Vào method được gọi | Frame `calculatePrice` và parameters xuất hiện |
| Step Over | Chạy method như một đơn vị rồi dừng ở bước tiếp theo của caller | `total` có giá trị trả về |
| Step Out | Từ trong callee chạy tới khi callee trả về caller | Caller frame trở lại hiện tại |
| Resume | Tiếp tục đến breakpoint/event tiếp theo | Chương trình chạy qua các câu lệnh khác |
| Pause/Suspend | Tạm dừng execution đang chạy | Có thể dừng ở vị trí không đoán trước |
| Run to Cursor | Chạy tới vị trí do người dùng chọn nếu thực thi tới đó | Dùng để bỏ qua bước chi tiết |
| Drop Frame/Restart Frame (nếu IDE hỗ trợ) | Thử quay về frame trước | Có thể **không hoàn tác side effects** đã xảy ra |

### 8.1. Step Into có thể đi vào JDK/library code

Nếu đang debug `Math.addExact`, Step Into có thể vào JDK internals khi source attached và debugger không filter. Nếu mục tiêu là xem object field trước/sau update, Step Over thường phù hợp hơn.

### 8.2. Step Out không “undo” callee

Nó tiếp tục execution cho đến lúc callee return. Những mutations vào heap trong callee vẫn tồn tại; caller tiếp tục với updated object state.

### 8.3. Drop Frame không là transaction rollback

Một số IDE hỗ trợ “Drop Frame” hoặc “Restart Frame”, nhưng gọi methods có side effects, I/O, increments, DB updates trước đó **không tự bị rollback**. Thực hành trên dữ liệu test khi dùng công cụ điều khiển execution mạnh.

### 8.4. Chọn thao tác theo câu hỏi đang tìm

- “Giá trị tham số vào method có đúng không?” → Step Into + xem frame.
- “Phép tính này trả gì?” → Step Over.
- “Ai gọi tôi và giữ object nào?” → Stack + chọn caller frame.
- “Tại sao field đổi giữa hai lines?” → Breakpoint trước/sau mutation, rồi Step Over.
- “Một method khác có side effect không?” → Step Into hoặc method breakpoint.

## 9. `this` trỏ tới object hiện tại, không trỏ tới tên class

Trong instance method:

~~~java
class Wallet {
    private int amount;

    Wallet(int amount) {
        this.amount = amount;
    }

    void topUp(int amount) {
        this.amount += amount;
    }
}
~~~

`this` là reference tới chính Wallet object nhận lời gọi. Nếu có hai wallets A/B, mỗi lần gọi `topUp` có `this` khác nhau.

### 9.1. `this.field` đặc biệt hữu ích khi tên bị shadow

`this.amount` luôn chọn field của receiver. Bare `amount` trong `topUp(int amount)` chọn parameter vì shadowing. Trong debugger, đánh giá cả hai để phát hiện lỗi kiểu:

~~~java
amount = amount + amount;
~~~

Dòng trên chỉ sửa parameter local, không đổi field. Code mong tăng balance thường cần `this.amount = this.amount + amount` hoặc `this.amount += amount`.

### 9.2. Không phải mọi bare name đều là parameter

Nếu không có local/parameter che tên, `amount` trong instance method có thể tự động chỉ field `this.amount`. Để dạy và kiểm tra shadowing rõ ràng, dùng `this.amount` trong source nếu có cùng tên parameter.

### 9.3. Trong constructor, this trỏ tới object đang khởi tạo

Object đã có reference `this` khi body constructor chạy, nhưng subclass fields có thể chưa khởi tạo xong ở một số giai đoạn. Đừng gọi overridable methods từ superclass constructor rồi giả định subclass state đã sẵn sàng.

### 9.4. Static method không có `this`

Trong `public static void main(String[] args)` không có instance receiver. Không thể viết `System.out.println(this)` trực tiếp trong static method. Muốn inspect object, xem local reference như `wallet` hoặc chọn instance frame được gọi từ main.

## 10. Chương trình hoàn chỉnh 2 — bug shadowing và sửa lại

Tệp **`ShadowingDebugDemo.java`**:

~~~java
public class ShadowingDebugDemo {
    static final class Score {
        private int points;

        Score(int points) {
            this.points = points;
        }

        void wrongAdd(int points) {
            points = points + 5; // Chỉ thay parameter.
        }

        void rightAdd(int points) {
            this.points = this.points + points;
        }

        int points() {
            return points;
        }
    }

    public static void main(String[] args) {
        Score score = new Score(10);

        score.wrongAdd(3);
        System.out.println("After wrongAdd = " + score.points());

        score.rightAdd(3);
        System.out.println("After rightAdd = " + score.points());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -g -encoding UTF-8 ShadowingDebugDemo.java
java ShadowingDebugDemo
~~~

**Stdout chính xác:**

~~~text
After wrongAdd = 10
After rightAdd = 13
~~~

### 10.1. Điểm dừng đề xuất

Đặt breakpoint trên `points = points + 5` và trên `this.points = this.points + points`. Tại wrongAdd, theo dõi parameter `points` trước/sau: 3 → 8; field `this.points` vẫn 10.

### 10.2. Tại rightAdd

Parameter `points` là 3; field `this.points` trước dòng update là 10. Sau Step Over, field thành 13. Parameter không tự đổi.

### 10.3. Phát hiện lỗi bằng hai Watches

Thêm hai expressions `points` và `this.points` vào Watches. Nếu chỉ xem một ô tên points mà không biết nó là local hay field, rất dễ hiểu sai nguyên nhân.

### 10.4. Scope của parameter

Sau khi method trả về, frame và parameter `points` biến mất; field của object vẫn chứa trạng thái đã cập nhật. Khi caller xem `score.points()`, nó đọc object field, không đọc tham số cũ.

## 11. Java luôn truyền tham trị — kể cả giá trị là reference

Đây là chủ đề dễ bị debugger làm người học hiểu sai nhất.

Khi gọi:

~~~java
update(myBox);
~~~

và parameter là `Box box`, Java **chép giá trị của reference** `myBox` vào parameter `box` của invocation. Do đó ban đầu hai references trỏ tới **cùng object**. Nhưng **parameter variable** là một biến riêng trong callee.

Hai thao tác hoàn toàn khác:

1. `box.value = 20`: mutate object đang được cả caller/callee tham chiếu; caller thấy thay đổi.
2. `box = new Box(99)`: gán parameter reference sang object khác; caller's variable `myBox` vẫn trỏ object ban đầu.

Đừng gọi Java là “pass-by-reference” chỉ vì mutations qua reference parameters được caller quan sát. Reference **value** được truyền **by value**.

### 11.1. Tại sao cần xem cả Variables của caller và callee?

Trong callee, bạn thấy `box` thay đổi reference sau assignment; trong caller, bạn thấy `myBox` vẫn giữ original object. Chọn hai stack frames khác nhau để so sánh.

### 11.2. Method return cũng không tự đổi caller variable

Một method có thể trả một reference mới; caller chỉ nhận nó nếu **gán lại**:

~~~java
myBox = replace(myBox);
~~~

Nếu gọi `replace(myBox)` mà bỏ result, caller's reference không đổi (trừ khi replace có side effects vào object gốc).

## 12. Chương trình hoàn chỉnh 3 — mutation qua alias và reassign parameter

Tệp **`ReferenceParameterDebugDemo.java`**:

~~~java
public class ReferenceParameterDebugDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(Box parameter) {
        parameter.value += 5;
        System.out.println("Inside changed = " + parameter.value);

        parameter = new Box(999);
        System.out.println("Inside reassigned = " + parameter.value);
    }

    public static void main(String[] args) {
        Box original = new Box(10);
        Box alias = original;

        change(alias);

        System.out.println("Original value = " + original.value);
        System.out.println("Alias value = " + alias.value);
        System.out.println("Still same object = "
                + (original == alias));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g -encoding UTF-8 ReferenceParameterDebugDemo.java
java ReferenceParameterDebugDemo
~~~

**Stdout chính xác:**

~~~text
Inside changed = 15
Inside reassigned = 999
Original value = 15
Alias value = 15
Still same object = true
~~~

### 12.1. Breakpoint số 1: đầu `change`

Ở frame `change`, parameter trỏ cùng Box object với `alias` và `original` trong caller frame. Field `value` ban đầu bằng 10.

### 12.2. Breakpoint số 2: sau `parameter.value += 5`

Field trên original object thành 15. Cả caller references `original` và `alias` đều quan sát được giá trị mới nếu code truy cập sau khi callee trả.

### 12.3. Breakpoint số 3: sau `parameter = new Box(999)`

Callee parameter trỏ tới object mới có value=999. Caller references vẫn trỏ object cũ value=15. Nếu debugger hiển thị object labels, bạn sẽ thấy parameter label đổi, còn caller labels không đổi.

### 12.4. Tên biến không đi theo object

Object không “biết” nó được đặt tên original, alias hay parameter. Đây là tên references trong những frames/scopes khác nhau. Các references có thể trỏ tới cùng heap object hoặc nhiều objects khác nhau.

### 12.5. Debugger cho thấy aliases nhưng không thay semantics truyền tham trị

Tuy cả caller/callee thấy cùng object trong một khoảng thời gian, reference parameter vẫn là **bản sao của reference value**. Đây là lý do reassign parameter không truyền assignment ngược sang caller.

## 13. Object graph: đọc fields tham chiếu trong Variables pane

Khi inspect object, không chỉ đọc primitive fields mà còn mở rộng reference fields:

~~~text
main frame
  order  ---> Order
                id = "O-1"
                customer ---> Customer
                                 name = "Lan"
                lines ------> ArrayList
                                 [0] ---> Line
                                            sku = "BOOK"
                                            qty = 2
~~~

Đây là **sơ đồ giảng giải**. IDE có thể hiển thị cây, nodes, collection size và synthetic internals khác nhau.

### 13.1. Two levels of nesting

Một `Order` giữ `Customer` reference không có nghĩa mọi thuộc tính Customer nằm inline trong Order. Mở rộng nested object để xem riêng Customer fields.

### 13.2. Cẩn thận các vòng tham chiếu

Nếu Parent giữ Child và Child giữ Parent, debugger có thể hiển thị lại cùng object theo vòng. Nó thường có cơ chế chống mở vô hạn, nhưng đừng kết luận có infinite objects chỉ vì cùng một object xuất hiện ở nhiều nhánh.

### 13.3. Một object được hai fields trỏ tới

Nếu `order.billingAddress == order.shippingAddress`, hai fields chia sẻ object. Một mutation qua billingAddress có thể được quan sát qua shippingAddress, nếu Address mutable.

### 13.4. Nơi để kiểm tra identity

Để trả lời “có cùng object không?”, đánh giá `left == right`. Với objects, `==` so reference identity. Đừng dùng `equals` nếu câu hỏi là object identity, vì equals có thể được override để so giá trị.

### 13.5. Cẩn thận tự động gọi toString() trong IDE

Nhiều IDE cho phép tùy chỉnh object display bằng `toString()` hoặc renderers. Điều đó có thể chạy application code tại pause point. Nếu toString làm I/O/lock hoặc mutate state, việc inspect object có thể tạo tác dụng phụ. Chỉ mở rộng raw fields khi muốn đánh giá thuần hơn.

## 14. Chương trình hoàn chỉnh 4 — field tham chiếu, aliasing và defensive copy

Tệp **`ObjectGraphDebugDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ObjectGraphDebugDemo {
    static final class Item {
        String name;

        Item(String name) {
            this.name = name;
        }
    }

    static final class Cart {
        private final List<Item> items;

        Cart(List<Item> items) {
            this.items = new ArrayList<>(items);
        }

        List<Item> items() {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        Item item = new Item("Book");
        List<Item> source = new ArrayList<>();
        source.add(item);

        Cart cart = new Cart(source);

        System.out.println("Same element = "
                + (source.get(0) == cart.items().get(0)));

        item.name = "Notebook";
        System.out.println("Cart item name = "
                + cart.items().get(0).name);

        source.add(new Item("Pen"));
        System.out.println("Source count = " + source.size());
        System.out.println("Cart count = " + cart.items().size());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g -encoding UTF-8 ObjectGraphDebugDemo.java
java ObjectGraphDebugDemo
~~~

**Stdout chính xác:**

~~~text
Same element = true
Cart item name = Notebook
Source count = 2
Cart count = 1
~~~

### 14.1. Vì sao Same element true?

Cart constructor copy **List structure** nhưng giữ **references tới Item objects**. `source.get(0)` và `cart.items().get(0)` vẫn trỏ cùng Item instance.

### 14.2. Vì sao Cart thấy Notebook?

`item.name = "Notebook"` mutate shared Item object. Dù Cart đã copy List, nó chưa deep-copy Item elements.

### 14.3. Vì sao Source count=2, Cart count=1?

Caller thêm một new Item vào source list sau Cart construction. Cart có ArrayList riêng nên structure không đổi. Đây là ví dụ về **shallow copy**.

### 14.4. Debugger cần inspect gì?

- `source`: size và element references.
- `cart`: field `items` trỏ tới một List khác.
- `source.get(0) == cart.items().get(0)`: true.
- `item.name` qua cả hai paths: cùng giá trị.
- Step qua `source.add(...)`: source list đổi, cart list không đổi.

### 14.5. Giá trị khi thiết kế domain objects

Quan sát object graph giúp phát hiện getter trả mutable internal collection hoặc constructor chỉ copy structure trong khi có mutable elements. Bảo vệ object invariants cần ownership rõ, không chỉ fields private.

## 15. Static field khác instance field khi xem debugger

Một `static` field thuộc **class**, không thuộc riêng mỗi instance. Debugger IDE thường có mục **Static Fields** riêng hoặc cho phép đánh giá `ClassName.field`. `this` chỉ có ý nghĩa trong instance frame.

Ví dụ:

~~~java
class Ticket {
    static int created;
    final int id;

    Ticket() {
        created++;
        id = created;
    }
}
~~~

Khi hai tickets được tạo theo thứ tự, `Ticket.created` dùng chung và đạt 2. Fields `ticket1.id` và `ticket2.id` thuộc mỗi object, có thể lần lượt là 1 và 2.

### 15.1. Đừng tìm static field dưới đúng một object rồi tưởng nó là state riêng

Một số IDE hiển thị static members trong object view để tiện, nhưng semantics vẫn là class-level state. Hãy đánh giá `Ticket.created` thay vì `ticket1.created` để thể hiện ý nghĩa đúng.

### 15.2. Static method không có receiver `this`

Trong `main`, có thể xem `Ticket.created` nhưng không có `this`. Muốn xem instance id, kiểm tra biến `first` hoặc `second`.

### 15.3. Shared static fields cũng có race conditions

Nếu nhiều threads cùng tăng `created++` không đồng bộ, có thể mất updates. Debugger dừng các threads có thể che race; dùng concurrent-safe design khi cần, không kết luận chỉ bằng một lần debug.

## 16. Chương trình hoàn chỉnh 5 — static vs instance fields

Tệp **`StaticInstanceDebugDemo.java`**:

~~~java
public class StaticInstanceDebugDemo {
    static final class Ticket {
        static int created;

        final int id;
        int uses;

        Ticket() {
            created++;
            id = created;
        }

        void use() {
            uses++;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket();
        Ticket second = new Ticket();

        first.use();
        first.use();
        second.use();

        System.out.println("Created = " + Ticket.created);
        System.out.println("First ID = " + first.id);
        System.out.println("Second ID = " + second.id);
        System.out.println("First uses = " + first.uses);
        System.out.println("Second uses = " + second.uses);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g -encoding UTF-8 StaticInstanceDebugDemo.java
java StaticInstanceDebugDemo
~~~

**Stdout chính xác:**

~~~text
Created = 2
First ID = 1
Second ID = 2
First uses = 2
Second uses = 1
~~~

### 16.1. Điều nên nhìn khi debugger dừng ở `use()`

`this` lần lượt trỏ first/second. `this.uses` thay riêng trên receiver. `Ticket.created` không đổi theo `use()`, vì method đó không tạo ticket mới.

### 16.2. Tạo hai objects tăng shared counter

Constructor gọi trên từng object và cập nhật static Ticket.created. Đây là ví dụ single-thread để IDs deterministic, không phải concurrent ID generator production-ready.

### 16.3. Nếu Java class bị load lại bằng classloader khác?

Class identity và static state liên quan class loader. Một JVM có thể có distinct copies của “cùng tên class” qua loaders khác nhau. Không cần xử lý trong bài debug cơ bản, nhưng khi debugging ứng dụng modular/plugin, kiểm tra classloader nếu static state khác mong đợi.

## 17. Constructor debugger: field mặc định và thứ tự khởi tạo

Một object có instance fields được khởi tạo theo Java initialization rules. Trong constructor chain, debugger giúp thấy thời điểm fields nào đã được gán.

Ví dụ class con extends class cha:

~~~java
class Base {
    protected int baseValue;

    Base(int n) {
        this.baseValue = n;
    }
}

class Child extends Base {
    private int childValue = 2;

    Child(int n) {
        super(n);
        this.childValue = n * 2;
    }
}
~~~

Đây là fragments.

### 17.1. Khi dừng trong Base constructor

`this` vẫn trỏ tới object cuối cùng đang được tạo (Child instance), nhưng Child-specific initialization có thể chưa hoàn tất. Debugger có thể cho phép mở rộng `this` để thấy subclass fields còn default values.

### 17.2. Khi trở lại Child constructor

Sau superclass constructor, Java tiếp tục instance field initializers/instance initializer blocks của Child rồi constructor body theo thứ tự chuẩn. Nếu Step qua câu gán `childValue = n * 2`, bạn sẽ thấy field thay.

### 17.3. Đừng gọi overridable method từ constructor chỉ để in diagnostic

Một superclass constructor gọi method có thể dispatch tới subclass override trước khi subclass fields được khởi tạo đầy đủ, tạo lỗi khó hiểu. Debugger có thể giúp quan sát điều đó, nhưng không nên cố thiết kế constructor dựa vào behavior này.

## 18. Chương trình hoàn chỉnh 6 — bước qua constructor chain

Tệp **`ConstructorStepDemo.java`**:

~~~java
public class ConstructorStepDemo {
    static class Base {
        int baseValue;

        Base(int value) {
            System.out.println("Base field initially = " + baseValue);
            baseValue = value;
            System.out.println("Base field after = " + baseValue);
        }
    }

    static final class Child extends Base {
        int childValue = 2;

        Child(int value) {
            super(value);
            System.out.println("Child initial = " + childValue);
            childValue = value * 2;
            System.out.println("Child after = " + childValue);
        }
    }

    public static void main(String[] args) {
        Child child = new Child(5);

        System.out.println("Final base = " + child.baseValue);
        System.out.println("Final child = " + child.childValue);
    }
}
~~~

Chạy:

~~~bash
javac -g -encoding UTF-8 ConstructorStepDemo.java
java ConstructorStepDemo
~~~

**Stdout chính xác:**

~~~text
Base field initially = 0
Base field after = 5
Child initial = 2
Child after = 10
Final base = 5
Final child = 10
~~~

### 18.1. Breakpoint trong Base constructor

Ở dòng in “Base field initially”, `this.baseValue` vẫn 0. Dù dynamic type của receiver là Child, subclass field initialization vẫn chưa là điều nên dựa vào lúc Base constructor đang thực thi.

### 18.2. Breakpoint sau `super(value)`

Quan sát baseValue=5; Child field initializer đặt childValue=2 trước body statement in “Child initial”.

### 18.3. Breakpoint sau phép gán Child field

Sau `childValue = value * 2`, giá trị thành 10. Parameter value vẫn 5, không tự bị thay bởi field assignment.

### 18.4. Cẩn thận thứ tự “before super”

Trong Java 17, constructor của subclass phải gọi superclass constructor theo constructor invocation rules. Không thể tự do truy cập `this`/subclass instance fields trước `super(...)` trong cách viết thông thường. Đặt breakpoints ở những vị trí thực sự hợp lệ trong source.

## 19. Call Stack: truy nguyên object và tham số qua các tầng method

Nếu chuỗi gọi:

~~~text
main()
    -> controller.handle(request)
         -> service.process(request)
              -> account.withdraw(amount)
~~~

Khi dừng trong withdraw, Call Stack hiển thị frames từ callee hiện tại tới callers. Muốn biết amount từ đâu tới:

1. Kiểm tra `amount` ở frame withdraw.
2. Chuyển lên frame `service.process`, xem local/parameter mà service đã truyền.
3. Chuyển lên `controller.handle`, xem request fields/derived values.
4. Ghi nhận nơi value bị biến đổi không mong muốn.

### 19.1. Chọn frame không sửa execution

Chuyển selection từ withdraw frame sang controller frame để inspect variables **không chạy ngược program**. Nó chỉ thay context hiển thị/evaluation.

### 19.2. Method call có thể đổi argument

Ví dụ controller nhận 100, service áp dụng discount thành 90, withdraw nhận 90. Khi debugger chọn từng frame, local values có thể khác theo design. Đừng kết luận 100 “đã bị Java truyền sai”.

### 19.3. Parameters có thể là cùng reference value ở nhiều frames

Nếu request object truyền từ controller→service→domain mà không copy, mỗi frame có reference riêng trỏ cùng object. Nếu service đổi `request.status`, controller có thể nhìn thấy thay đổi.

### 19.4. Optimized frames và native code

Trong JIT-optimized code, debugger có thể không luôn tái tạo được mọi local variable value nếu tối ưu hóa, hoặc một số frames không có source. Dùng debug build và source symbols khi cần; không giả định mọi VM đều cho inspect giống nhau mọi lúc.

## 20. Chương trình hoàn chỉnh 7 — đa hình: runtime receiver và caller frame

Tệp **`PolymorphismDebugDemo.java`**:

~~~java
public class PolymorphismDebugDemo {
    abstract static class Job {
        final String id;

        Job(String id) {
            this.id = id;
        }

        abstract String execute();
    }

    static final class PrintJob extends Job {
        PrintJob(String id) {
            super(id);
        }

        @Override
        String execute() {
            return "print:" + id;
        }
    }

    static final class SaveJob extends Job {
        SaveJob(String id) {
            super(id);
        }

        @Override
        String execute() {
            return "save:" + id;
        }
    }

    static String dispatch(Job job) {
        return job.execute();
    }

    public static void main(String[] args) {
        Job first = new PrintJob("P1");
        Job second = new SaveJob("S2");

        System.out.println(dispatch(first));
        System.out.println(dispatch(second));
        System.out.println("Same runtime type = "
                + (first.getClass() == second.getClass()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g -encoding UTF-8 PolymorphismDebugDemo.java
java PolymorphismDebugDemo
~~~

**Stdout chính xác:**

~~~text
print:P1
save:S2
Same runtime type = false
~~~

### 20.1. Breakpoint trong `dispatch(Job job)`

Static type của parameter là Job. Khi first được truyền, runtime object có type PrintJob; khi second được truyền, runtime object có type SaveJob.

### 20.2. Step Into `job.execute()`

Java virtual dispatch chọn PrintJob.execute hoặc SaveJob.execute dựa trên runtime object type. Chọn callee frame để thấy `this` trong concrete override.

### 20.3. `this` không biến thành một base-class object riêng

Khi vào PrintJob.execute, receiver là **cùng PrintJob instance** mà caller giữ qua reference kiểu Job. Truy cập inherited `id` vẫn nằm trong cùng object theo Java object model.

### 20.4. Debugger dynamic type không thay compiler static type

Compiler chỉ cho gọi methods được khai báo qua static type Job (và accessible), trừ khi pattern match/cast. Debugger hiển thị concrete runtime type là thông tin quan sát, không khiến source compiler cho truy cập arbitrarily mọi subtype method.

## 21. Local scope, shadowing và “variable not available”

Khi debugger hiển thị một biến “not available” hoặc không thấy trong danh sách, một vài nguyên nhân:

- Biến chưa vào lexical scope.
- Câu lệnh declaration có thể chưa thực thi.
- Debug build thiếu local variable table (dùng `javac -g`).
- Chọn sai stack frame.
- Compiler/JIT đã tối ưu/eliminate hoặc không bảo toàn giá trị theo cách debugger có thể hiển thị.
- Source không khớp class file.
- Biến bị capture trong lambda/anonymous class và biểu diễn khác với local thông thường.

### 21.1. Parameter và local khác field trong lifecycle

Một field không biến mất khi method return nếu object vẫn reachable. Một parameter/local thuộc frame không còn quan sát được như local của invocation đó sau khi return. Một value reference có thể tiếp tục tồn tại qua field/capture hoặc được return, nhưng biến local cũ không theo object.

### 21.2. Block scope

~~~java
if (ready) {
    int local = 10;
    System.out.println(local);
}
// local không hợp lệ ở đây.
~~~

Đây là fragment. Khi debugger đang ở dòng ngoài block, tên local có thể không còn trong scope. Không cố đọc một local đã hết scope rồi kết luận nó đã “bị garbage collected”: **scope của biến khác reachability của object mà nó từng tham chiếu**.

### 21.3. Lambda capture

Một lambda có thể capture effectively final local, làm value tiếp tục tồn tại trong lambda object sau khi method tạo lambda return. Khi debug, compiler có thể biểu diễn captured values qua fields/synthetic structures của lambda. Điều này vẫn tuân Java semantics; đừng phụ thuộc synthetic field names như một API.

## 22. Record: xem components, accessors và object value semantics

Một Java record khai báo components trong header:

~~~java
record Point(int x, int y) {
}
~~~

Record có private final component fields và public accessors `x()`, `y()`. Trong debugger, bạn có thể thấy fields x/y; đây là state của record object. Không có setters mặc định làm thay component fields.

### 22.1. Đừng nhầm local `moved` với state mutate của `original`

~~~java
Point moved = new Point(original.x() + 2, original.y());
~~~

tạo record khác; original không thay. Dùng debugger inspect original/moved references và components.

### 22.2. Giá trị bằng nhau khác identity

Hai records `new Point(2,3)` có thể `equals` true nhờ generated equality, nhưng references không `==` nếu tạo hai objects riêng. Debugger object labels có thể khác, đúng với identity khác dù value ngang nhau.

## 23. Chương trình hoàn chỉnh 8 — inspect record và object equality

Tệp **`RecordDebuggerDemo.java`**:

~~~java
public class RecordDebuggerDemo {
    record Point(int x, int y) {
    }

    static Point moveRight(Point point, int delta) {
        return new Point(point.x() + delta, point.y());
    }

    public static void main(String[] args) {
        Point original = new Point(2, 3);
        Point equalValue = new Point(2, 3);
        Point moved = moveRight(original, 2);

        System.out.println("Original = " + original);
        System.out.println("Equal values = "
                + original.equals(equalValue));
        System.out.println("Same instance = "
                + (original == equalValue));
        System.out.println("Moved = " + moved);
        System.out.println("Original still = " + original);
    }
}
~~~

Chạy:

~~~bash
javac -g -encoding UTF-8 RecordDebuggerDemo.java
java RecordDebuggerDemo
~~~

**Stdout chính xác:**

~~~text
Original = Point[x=2, y=3]
Equal values = true
Same instance = false
Moved = Point[x=4, y=3]
Original still = Point[x=2, y=3]
~~~

### 23.1. Inspect trong `moveRight`

Parameter `point` là reference value tới original record. Parameter `delta` là primitive int=2. Method tạo new Point(4,3), không đổi original.

### 23.2. Chọn frame main sau khi Step Out

`original` và `moved` là hai references khác nhau, cùng có type Point. Khi mở fields, original có x=2, moved x=4.

### 23.3. Tại sao original.equals(equalValue) true nhưng == false?

Generated record equality dựa trên component values (với rules tương ứng), trong khi `==` so reference identity. Debugger giúp quan sát hai values giống nhau ở hai objects khác nhau.

## 24. NullPointerException: chọn đúng frame và inspect chuỗi truy cập

Một biểu thức như:

~~~java
person.address().city().length()
~~~

có nhiều chặng. Null có thể là person, address() result, city() result... **Đừng sửa bằng cách rải null checks ngẫu nhiên mà chưa xác định contract.**

### 24.1. Cách tìm nơi null

1. Dừng ở dòng gây NullPointerException, hoặc bật **exception breakpoint** cho NullPointerException.
2. Xem Call Stack và chọn frame ứng dụng đầu tiên có source.
3. Inspect `person`; nếu non-null, inspect `person.address()`; sau đó `city()`.
4. Cẩn thận: gọi getter methods trong Evaluate Expression có thể thực thi code và side effects. Nếu getters không thuần, inspect fields trực tiếp hoặc đặt breakpoints trong getters.
5. Xác định nguyên nhân business: null là hợp lệ theo API, dữ liệu thiếu, khởi tạo sai hay caller vi phạm contract?
6. Sửa tại boundary phù hợp: constructor validation, Optional/nullable contract hoặc state handling.

### 24.2. Exception breakpoint trong IDE

Nhiều IDE cho phép dừng **khi exception được throw** ngay cả nếu code catch nó. Tên giao diện có thể là Exception Breakpoint, Java Exception Breakpoint hoặc Break on Caught/Uncaught. Chọn caught/uncaught cho đúng nhu cầu, không assume mặc định tất cả IDE đều như nhau.

### 24.3. Helpful NPE messages

Java 17 có thể tạo message mô tả expression gây NPE tùy runtime/configuration, nhưng đừng dùng exact message làm output portable. Nếu cần stdout ổn định, catch exception và in một thông báo do code chủ động định nghĩa.

## 25. Chương trình hoàn chỉnh 9 — null trong object graph

Tệp **`NullDebugDemo.java`**:

~~~java
public class NullDebugDemo {
    record Address(String city) {
    }

    record Person(String name, Address address) {
    }

    static int cityLength(Person person) {
        return person.address().city().length();
    }

    public static void main(String[] args) {
        Person valid = new Person("Lan", new Address("Hue"));
        Person missing = new Person("Mai", null);

        System.out.println("Valid length = " + cityLength(valid));

        try {
            cityLength(missing);
        } catch (NullPointerException ex) {
            System.out.println("Missing address detected");
        }

        System.out.println("Missing name = " + missing.name());
    }
}
~~~

Lệnh:

~~~bash
javac -g -encoding UTF-8 NullDebugDemo.java
java NullDebugDemo
~~~

**Stdout chính xác:**

~~~text
Valid length = 3
Missing address detected
Missing name = Mai
~~~

### 25.1. Breakpoint ngay trước dereference

Ở `cityLength`, inspect `person`, sau đó `person.address()`. Invocation với valid có Address object city="Hue"; invocation với missing có address=null.

### 25.2. Vì sao catch xử lý được mà không sửa object?

Catch chỉ xử lý exception. Nó không biến missing.address thành một Address hợp lệ. Mã sau đó vẫn có thể gọi `missing.name()` vì Person object non-null.

### 25.3. Sửa bằng contract

Nếu địa chỉ bắt buộc, constructor Person cần `Objects.requireNonNull(address)`, reject object invalid từ đầu. Nếu address là optional, method cityLength nên trả một defined fallback/result hoặc báo business validation error. Tránh chỉ “catch NPE và tiếp tục” trong production.

## 26. Watches và Evaluate Expression: công cụ mạnh nhưng có side effects

Một Watch như `this.balance` thường là đọc field. Nhưng expression:

~~~java
account.withdraw(100)
~~~

**sẽ thực thi một method**, có thể thay state đang debug. Getter cũng có thể lazy-load data, update counters hoặc acquire locks tùy implementation.

### 26.1. Các biểu thức nên ưu tiên

- `this.field`.
- `parameter`, `local`.
- `left == right`.
- `list.size()` nếu bạn hiểu implementation và chấp nhận method call.
- `record.x()` nếu accessor thuần theo contract.
- `object.getClass().getName()` nếu cần concrete type, nhận thức đây vẫn là method evaluation.

### 26.2. Những biểu thức cần thận trọng

- `iterator.next()`: thay iterator position.
- `list.remove(...)`: mutate state.
- `account.withdraw(...)`: mutate domain object.
- `stream.count()` trên stream one-shot: có thể consume stream.
- `toString()` custom: có thể chạy application code, I/O hoặc lock.
- `future.get()`: có thể block đang dừng, gây deadlock nếu worker cần chạy.
- Calls tới HTTP/database: có side effects bên ngoài JVM và không thể undo bằng Restart Frame.

### 26.3. Conditional breakpoint cũng có thể evaluate expressions

Một condition như `balance < 0` thuần có thể an toàn. Nhưng `expensiveMethod()` trong condition có thể chạy ở mỗi breakpoint hit, thay timing và gây side effects. IDEs thường có options **Suspend all threads / Suspend thread**, logpoints hoặc conditions; chọn phù hợp và đo overhead.

### 26.4. “Debugger changed the bug”

Nếu bug biến mất khi đặt breakpoint, nghi ngờ race, timing, initialization ordering hoặc timeout. Breakpoint không chứng minh lỗi không tồn tại. Kết hợp tests và concurrency diagnostics.

## 27. Breakpoints: chọn đúng loại cho câu hỏi

| Loại breakpoint | Khi nào dùng | Lưu ý |
| --- | --- | --- |
| Line breakpoint | Biết statement đáng nghi | Đặt ở executable line |
| Method breakpoint | Muốn dừng mỗi lần method được gọi | Có thể overhead cao hơn line breakpoint |
| Conditional breakpoint | Chỉ dừng khi amount < 0 hoặc id khớp | Condition có thể được evaluate nhiều lần |
| Exception breakpoint | Truy nguyên NPE/IllegalStateException | Có thể dừng ở cả exceptions đã được catch |
| Field watchpoint | Muốn biết field bị đọc/ghi tại đâu | Phụ thuộc debugger/VM support và overhead |
| Logpoint/tracepoint | Muốn ghi dữ liệu mà không suspend như line breakpoint | Vẫn có evaluation overhead |
| Run to Cursor | Bỏ qua đoạn code hiện tại tới một vị trí | Không bảo đảm chạy tới nếu control flow rẽ nhánh |

### 27.1. Đừng đặt breakpoint chỉ vào getter nếu field bị sửa ở nơi khác

Muốn biết **ai ghi field**, dùng field modification watchpoint nếu công cụ hỗ trợ, hoặc tìm tất cả writes và đặt breakpoints. Debug tại getter chỉ cho biết state đang được đọc.

### 27.2. Field watchpoint khác data breakpoint của native debugger

Java Debug Interface/JDWP có field access/modification events trên những VM hỗ trợ phù hợp. IDE có thể gọi chung Data Breakpoint, Field Watchpoint hoặc Watchpoint. Hãy kiểm tra semantics cụ thể; không giả định có phần cứng watchpoint giống C/C++ debugger.

### 27.3. Breakpoint hit count và filters

Nếu một method được gọi hàng triệu lần, dùng hit count hoặc condition để không dừng quá nhiều. Đừng để condition gọi expensive API hay truy cập shared state mà không hiểu concurrency impact.

## 28. Quan sát threads và tính nhất quán của object

Trong chương trình có nhiều threads, cùng một object field có thể bị đọc/ghi bởi nhiều execution contexts. Debugger có thể:

- Chỉ suspend thread chạm breakpoint.
- Suspend tất cả threads theo cấu hình.
- Cho chọn thread và call stack riêng.
- Hiển thị field values đang thay nếu threads khác tiếp tục chạy.

### 28.1. Quan sát một field không chứng minh không có race

Một lần nhìn thấy `counter.value == 10` tại breakpoint không bảo đảm phép increment an toàn trong mọi interleavings.

### 28.2. Suspend tất cả threads có thể che race

Nếu mọi thread bị dừng khi một breakpoint hit, interleaving thay đổi so với production. Nếu chỉ suspend một thread, threads khác có thể tiếp tục sửa object trong khi đang inspect. Cả hai chế độ đều có tradeoffs.

### 28.3. Thread-local variables và shared fields khác nhau

Mỗi thread có call stacks/locals riêng cho method invocations; hai threads có thể cùng giữ references tới **shared heap object**. Đừng nhầm hai frame có biến tên `counter` với hai counters riêng.

### 28.4. Đồng bộ hóa tạo happens-before/visibility theo Java memory model

Nếu code dùng `synchronized` hoặc atomic utilities đúng, có thể xác định các guarantees về visibility/atomicity phù hợp. Debugger chỉ là công cụ quan sát; nó không thay synchronization primitives.

## 29. Chương trình hoàn chỉnh 10 — shared object nhiều threads

Tệp **`ThreadDebuggerDemo.java`**:

~~~java
public class ThreadDebuggerDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int value() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter shared = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 100; i++) {
                shared.increment();
            }
        };

        Thread first = new Thread(work, "worker-A");
        Thread second = new Thread(work, "worker-B");

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("Final = " + shared.value());
        System.out.println("Same target = "
                + (first != second));
    }
}
~~~

Chạy:

~~~bash
javac -g -encoding UTF-8 ThreadDebuggerDemo.java
java ThreadDebuggerDemo
~~~

**Stdout chính xác:**

~~~text
Final = 200
Same target = true
~~~

### 29.1. Breakpoint trong `Counter.increment`

Có thể dừng trong worker-A hoặc worker-B tùy scheduling. Chọn Threads pane để thấy tên thread đang active. Không hứa thread nào chạm breakpoint trước.

### 29.2. `this` ở cả hai worker frames

Nếu cả hai gọi `shared.increment()`, receiver `this` trỏ cùng Counter object. Nhưng mỗi thread có local `i` riêng trong lambda invocation loop.

### 29.3. Vì sao final luôn 200 theo demo?

Increment được `synchronized` trên cùng shared Counter object; hai threads mỗi thread gọi 100 lần; main chờ `join` hoàn tất trước khi in. Không có lost updates với synchronization này.

### 29.4. Vì sao "Same target" true nhưng tên có vẻ gây hiểu nhầm?

Biểu thức in trong demo là `first != second`, kiểm tra **hai Thread objects là khác nhau**. Label "Same target" có thể dễ nhầm với việc Runnable target là chung; hãy hiểu dòng true theo đúng biểu thức. Khi học debugger, nên đổi nhãn thành "Distinct threads" để tránh nhầm. Việc cả hai threads dùng chung Counter được thiết lập qua captured variable `shared` trong cùng Runnable.

### 29.5. Giới hạn của demo

Đây là ví dụ lock đơn giản, không phải benchmark throughput. Chạy dưới debugger có thể kéo dài execution; không lấy timing từ đó làm thước đo hiệu suất production.

## 30. Đọc `this` trong interface default methods, lambdas và nested classes

### 30.1. Instance method của interface default

Khi một class implements interface với default method, `this` trong default method là reference tới implementation object đang nhận lời gọi. Không phải một instance của interface (interface không được instantiate trực tiếp).

### 30.2. `this` trong lambda

Trong **lambda body**, `this` có nghĩa theo lexical enclosing instance của context nơi lambda được tạo, **không nhất thiết là một "lambda object"**. Trong static method, bạn không thể dùng `this` chỉ vì đang viết lambda.

### 30.3. `this` trong anonymous inner class

Trong anonymous class body, `this` trỏ anonymous instance, khác lexical `this` trong lambda. Để truy cập outer instance, dùng dạng `OuterClass.this` ở nơi hợp lệ.

### 30.4. Variables pane có thể hiển thị synthetic fields

Captured locals và enclosing instances có thể được compiler biểu diễn qua synthetic members. Tên nội bộ thay theo compiler/version; hãy dựa trên Java language semantics chứ không hard-code synthetic field names.

## 31. Chương trình hoàn chỉnh 11 — lambda và anonymous class nhìn `this` khác nhau

Tệp **`ThisCaptureDebugDemo.java`**:

~~~java
public class ThisCaptureDebugDemo {
    private final String name;

    ThisCaptureDebugDemo(String name) {
        this.name = name;
    }

    Runnable lambda() {
        return () -> System.out.println(
                "Lambda this = " + this.name);
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        "Anonymous this = "
                        + getClass().getSimpleName());
                System.out.println(
                        "Outer this = "
                        + ThisCaptureDebugDemo.this.name);
            }
        };
    }

    public static void main(String[] args) {
        ThisCaptureDebugDemo demo =
                new ThisCaptureDebugDemo("outer");

        demo.lambda().run();
        demo.anonymous().run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -g -encoding UTF-8 ThisCaptureDebugDemo.java
java ThisCaptureDebugDemo
~~~

**Stdout đáng tin của chương trình:**

~~~text
Lambda this = outer
Anonymous this = 
Outer this = outer
~~~

### 31.1. Vì sao dòng Anonymous this trống sau dấu bằng?

Ở một anonymous class thông thường, `getClass().getSimpleName()` trả chuỗi rỗng vì anonymous class không có simple name. Đó là Java reflection behavior hợp với ví dụ. Đừng dựa tên class binary tự sinh như `ThisCaptureDebugDemo$1`.

### 31.2. Debugger của lambda

Khi dừng ở print trong lambda, `this` theo lexical context là ThisCaptureDebugDemo object. Nó có field `name="outer"`.

### 31.3. Debugger của anonymous Runnable

`this` trong `run()` là anonymous Runnable instance. Muốn xem outer object, đánh giá `ThisCaptureDebugDemo.this` theo scope Java cho phép.

### 31.4. Vì sao hướng dẫn này liên quan aliasing?

Một lambda hoặc anonymous class có thể giữ reference tới enclosing object. Nếu được giữ trong long-lived registry, nó có thể kéo dài lifetime của outer object. Debugger có thể cho thấy reference path/capture, dù chi tiết synthetic fields phụ thuộc compiler.

## 32. Trường hợp lỗi: breakpoint không dừng hoặc giá trị không đúng kỳ vọng

### 32.1. Đặt breakpoint vào dòng không có bytecode

Ví dụ đóng ngoặc, comment hoặc variable declaration đã bị tối ưu có thể không tạo location phù hợp. Đặt vào câu lệnh thật sự thực thi như field assignment, method call hoặc conditional branch.

### 32.2. Nhầm class/package/main configuration

Đôi khi IDE đang debug một module khác hoặc Java process khác. Kiểm tra main class, classpath, module, working directory và JDK version.

### 32.3. Source khác class file

Rebuild sạch phần liên quan, đảm bảo debug session dùng compiled output mới; nếu source mismatched, debugger line mapping có thể khiến vị trí dừng gây hiểu nhầm.

### 32.4. Thiếu debug symbols

Dùng `javac -g`. Nếu chỉ có class file build không chứa local variable information, debugger có thể xem fields hoặc method signatures nhưng không hiển thị tên/giá trị locals như source.

### 32.5. Chọn sai stack frame

Nếu đang ở frame `main`, không có `this` của instance method `add`; nếu ở frame `add`, không đọc local `first` của main trực tiếp như cùng một scope.

### 32.6. Getter/toString thay đổi trạng thái

Một số IDE đánh giá properties hoặc custom renderers tự động. Kiểm tra thiết lập **auto expression evaluation**/toString rendering nếu inspect làm ứng dụng thay đổi hành vi.

### 32.7. Các objects dường như có cùng nhãn

Một số IDE hiển thị cùng class name và field values cho nhiều objects. Để xác định identity, đánh giá `==` hoặc inspect reference identity qua công cụ. Không suy từ class/type name giống nhau.

### 32.8. Gặp race chỉ khi không debug

Debugger có thể thay scheduling. Dùng stress/concurrency tests, lock ordering review, thread dumps và logging với correlation IDs. Không “fix” bằng sleep ngẫu nhiên vì có thể chỉ che lỗi.

### 32.9. Source có method overloaded

Method breakpoint có thể dừng ở nhiều overloads theo IDE. `jdb stop in Class.method` cần xem resolved target; đặt line breakpoint cụ thể khi muốn phân biệt signature.

### 32.10. Native frames hoặc methods không có source

Bạn có thể không Step Into được source nếu JDK/library source chưa gắn hoặc method native. Điều này không làm bytecode/runtime behavior sai; chỉ giới hạn quan sát của debugger.

## 33. Anti-pattern khi dùng debugger

1. **Chỉ nhìn một biến `count` và không phân biệt field với parameter.**
2. **Xem `this` như tên class thay vì reference tới receiver object.**
3. **Tin rằng biến reference được truyền pass-by-reference.**
4. **Gán parameter sang new object rồi kỳ vọng caller variable đổi.**
5. **Cho rằng local và field sống cùng scope.**
6. **Nhầm static fields với instance-specific fields.**
7. **Chỉ nhìn value bằng nhau rồi kết luận two objects cùng identity.**
8. **Chỉ nhìn object IDs rồi kết luận equals false.**
9. **Dùng Evaluate Expression gọi một mutating domain operation.**
10. **Đặt conditional breakpoint với expensive I/O expressions.**
11. **Dùng Drop Frame với kỳ vọng hoàn tác database/file writes.**
12. **Không chọn đúng thread/frame trước khi đọc locals.**
13. **Xem null trong một reference path rồi mặc định object gốc null.**
14. **Không đọc constructor initialization order.**
15. **Dùng `javac` mặc định rồi tin mọi local names bắt buộc xuất hiện.**
16. **Không rebuild class file sau khi sửa source.**
17. **Giữ breakpoint ở hot path rồi dùng elapsed time làm benchmark.**
18. **Không phân biệt exception throw point với nơi catch.**
19. **Tưởng getter luôn thuần không side effects.**
20. **Không nhận ra unmodifiable List vẫn có mutable elements.**
21. **Coi cả object graph là một object lớn thay vì nhiều references.**
22. **Đánh giá stream/iterator methods trong debugger khiến state thay.**
23. **Không nghĩ đến lambda capture giữ outer object reachable.**
24. **Không xem thread state và lock ownership khi debug deadlock.**
25. **Dùng một debug run làm bằng chứng code không có concurrency bug.**
26. **Xem một non-null local nhưng không xét alias có thể mutate cùng object.**
27. **Coi console debugger diagnostics là Java program stdout.**
28. **Cố học toàn bộ phím tắt IDE thay vì hiểu Step commands và frame model.**
29. **Sửa values bằng debugger mà quên reset/re-run test data.**
30. **Dừng ở nơi field đã đổi rồi đoán thủ phạm thay vì theo dõi write path.**

## 34. Bảng gợi ý “muốn biết X thì quan sát Y”

| Câu hỏi | Điểm dừng/biểu thức |
| --- | --- |
| Constructor nhận đầu vào nào? | Breakpoint tại constructor; xem parameters |
| Field đang giữ giá trị gì? | `this.field` trong instance frame |
| Tại sao field không đổi sau assignment? | Kiểm tra shadowing `field` vs `this.field` |
| Method chạy trên object nào? | Inspect `this` và chọn receiver tại caller |
| Hai variables có trỏ cùng object? | `a == b` |
| Vì sao mutation trong method ảnh hưởng caller? | Parameter reference và caller alias cùng referent |
| Vì sao reassign parameter không ảnh hưởng caller? | So reference trong caller/callee frames |
| Static counter thuộc đâu? | `TypeName.counter` |
| Ai gọi một method? | Call Stack/`where` |
| Ai sửa field? | Field modification watchpoint hoặc breakpoints tại writes |
| Điều gì xảy ra trong nested method? | Step Into |
| Chỉ cần kết quả nested method? | Step Over |
| Quay về caller sau callee? | Step Out |
| NPE xuất hiện ở đoạn nào? | Exception breakpoint + inspect chuỗi dereference |
| Object có nested List/DTO nào? | Expand object graph trong Variables |
| List snapshot có giữ mutable element alias? | So references `==` và inspect child fields |
| Runtime type của reference base class? | `obj.getClass()` hoặc debugger concrete type |
| Một record được thay thế hay mutate? | So original/moved references, fields |
| Lỗi mất khi breakpoint bật? | Kiểm tra race/timing, stress tests |
| Local variable không hiển thị? | `javac -g`, đúng frame/scope/source symbols |

## 35. Câu hỏi ôn tập có đáp án

**Câu 1.** Trong instance method, `this` là gì?

**Đáp án:** Reference tới object đang nhận lời gọi method hiện tại.

**Câu 2.** Trong static main có dùng `this` không?

**Đáp án:** Không. Static method không có receiver instance.

**Câu 3.** Trong constructor `Person(String name)`, `name` và `this.name` khác gì?

**Đáp án:** `name` là constructor parameter; `this.name` là instance field của object đang tạo.

**Câu 4.** Muốn xem field bị shadow, viết biểu thức nào trong debugger?

**Đáp án:** So `name` với `this.name` ở đúng frame.

**Câu 5.** `this` đổi khi gọi cùng method trên hai objects khác nhau không?

**Đáp án:** Có, receiver reference của mỗi invocation trỏ tới object được gọi.

**Câu 6.** Local variable của callee có tự xuất hiện trong caller frame không?

**Đáp án:** Không; chúng thuộc stack frames/scopes khác nhau.

**Câu 7.** Khi method nhận `Box parameter`, Java truyền gì?

**Đáp án:** Bản sao của reference value tới Box object, theo pass-by-value.

**Câu 8.** Gán `parameter = new Box(...)` có đổi caller variable không?

**Đáp án:** Không; chỉ đổi reference local của callee.

**Câu 9.** Sửa `parameter.value` có thể ảnh hưởng caller không?

**Đáp án:** Có nếu caller và parameter cùng tham chiếu một mutable object.

**Câu 10.** `a == b` với references kiểm tra điều gì?

**Đáp án:** Reference identity — có cùng object hay không.

**Câu 11.** `a.equals(b)` luôn tương đương `a == b` không?

**Đáp án:** Không; classes có thể override equals để so giá trị.

**Câu 12.** Field static thuộc từng instance không?

**Đáp án:** Không; nó thuộc class identity, được chia sẻ giữa các instances theo classloader/runtime context.

**Câu 13.** Vì sao nên dùng `javac -g` khi học jdb?

**Đáp án:** Để biên dịch có local variable names/debug information đầy đủ hơn cho inspect.

**Câu 14.** Step Into khác Step Over thế nào?

**Đáp án:** Step Into vào method được gọi; Step Over thực hiện call rồi dừng ở bước tiếp theo trong caller.

**Câu 15.** Step Out làm gì?

**Đáp án:** Tiếp tục đến khi method hiện tại trả về caller, không undo side effects.

**Câu 16.** Call Stack cho biết gì?

**Đáp án:** Chuỗi frames/method invocations đang hoạt động của thread được chọn.

**Câu 17.** Chuyển chọn frame có làm chương trình chạy ngược không?

**Đáp án:** Không; chỉ đổi context quan sát/evaluation.

**Câu 18.** Vì sao local không hiển thị?

**Đáp án:** Có thể chưa/đã hết scope, thiếu debug symbols, sai frame/source, hoặc tối ưu hóa.

**Câu 19.** Debugger có thể tự đánh giá toString không?

**Đáp án:** Tùy IDE/settings, có thể; custom toString có thể chạy application code.

**Câu 20.** Evaluate Expression có thể thay object state không?

**Đáp án:** Có nếu biểu thức gọi methods có side effects.

**Câu 21.** Conditional breakpoint gọi network method có an toàn không?

**Đáp án:** Không nên giả định; evaluation có thể tốn thời gian và tác động tới chương trình.

**Câu 22.** Nếu a và b cùng class name và fields giống nhau, chắc cùng object không?

**Đáp án:** Không; dùng reference identity `a == b`.

**Câu 23.** Record có setter cho component field mặc định không?

**Đáp án:** Không; record component fields final, accessors đọc value.

**Câu 24.** Hai record Point cùng x/y có equals true mà == false được không?

**Đáp án:** Có, nếu hai instances riêng nhưng component values bằng nhau.

**Câu 25.** Dừng trong constructor Base của Child, subclass fields đã luôn hoàn tất chưa?

**Đáp án:** Chưa; constructor/init order cần được xem đúng.

**Câu 26.** Vì sao method override được chọn dù reference static type là Base?

**Đáp án:** Virtual dispatch dựa trên runtime receiver type.

**Câu 27.** Với NullPointerException, nên xem gì đầu tiên?

**Đáp án:** Exception throw site, stack frame và chuỗi reference dereferences liên quan.

**Câu 28.** Java 17 có thể in Helpful NPE message; nên hard-code exact text vào test không?

**Đáp án:** Không khi muốn output portable; message có thể phụ thuộc runtime/config.

**Câu 29.** Khi debug hai threads, `this` có thể cùng object không?

**Đáp án:** Có nếu cả hai gọi instance method trên shared receiver.

**Câu 30.** Breakpoint có thể che concurrency bug không?

**Đáp án:** Có, vì nó làm thay đổi scheduling/timing.

**Câu 31.** Watch trong IDE giống lệnh watch của jdb không?

**Đáp án:** Không hoàn toàn. IDE Watch thường evaluate expression, còn jdb watch liên quan field watchpoints.

**Câu 32.** Vì sao không nên đọc một biến bằng call `iterator.next()` ở debugger?

**Đáp án:** Vì nó có side effect tiến iterator position, làm thay đổi execution đang debug.

**Câu 33.** Có thể “undo” một giao dịch DB bằng Drop Frame không?

**Đáp án:** Không; tool không tự rollback side effects ngoài process.

**Câu 34.** Tại sao callback/lambda có thể kéo dài lifetime object?

**Đáp án:** Nó có thể capture reference tới outer object và được lưu ở một owner lâu sống hơn.

**Câu 35.** Muốn nhìn thấy một field thay sau một statement, làm gì?

**Đáp án:** Breakpoint trước mutation, xem field, Step Over statement, xem lại field.

**Câu 36.** Một local biến mất sau return có nghĩa referent object đã GC không?

**Đáp án:** Không; object có thể còn references khác, và reclamation do GC quyết định.

**Câu 37.** Debugger có thay unit tests không?

**Đáp án:** Không; debugger quan sát một execution, tests tự động kiểm tra behavior nhiều cases.

**Câu 38.** Khi stdout và Variables pane dường như mâu thuẫn, phải kiểm tra gì?

**Đáp án:** Breakpoint đang trước/sau statement nào, frame/thread nào, source/build có khớp không, evaluate side effects, buffered output và timing.

**Câu 39.** Muốn jdb hiển thị call stack dùng lệnh gì?

**Đáp án:** `where` trong session tương tác.

**Câu 40.** Quy tắc quan trọng nhất khi học debugger Java Core?

**Đáp án:** Luôn phân biệt **local/parameter trong frame**, **`this` của receiver**, **instance/static fields** và **references tới heap objects**; quan sát trước và sau mỗi state mutation thay vì suy đoán.

## 36. Bài tập thực hành

### Bài 1 — this và tên bị che

Tạo class `Person` với field name và constructor parameter name. Dừng trước/sau `this.name = name`; ghi lại giá trị field và parameter tại mỗi bước.

**Gợi ý:** Dùng `javac -g`; Watch `name` và `this.name`.

### Bài 2 — hai objects cùng class

Tạo hai `Counter` objects, lần lượt gọi increment. Dừng trong method; inspect `this`, fields và caller variables. Chứng minh field của hai objects không lẫn nhau.

**Gợi ý:** So `counterA == counterB` trong caller.

### Bài 3 — pass-by-value của reference

Dùng `ReferenceParameterDebugDemo`, chụp trạng thái parameter và caller reference trước/sau mutate và reassign. Giải thích vì sao caller chỉ thấy mutation lên original object.

**Gợi ý:** Chọn frames khác nhau trong Call Stack.

### Bài 4 — shallow copy object graph

Tạo Cart giữ List<Item>, copy List trong constructor. Mutate Item từ caller và thêm một Item mới vào source List. Debug cả hai Lists và element references.

**Gợi ý:** Dùng `==` để xác định shared Item, không chỉ nhìn strings.

### Bài 5 — static vs instance

Tạo một static counter và instance IDs, dừng ở constructor. Quan sát class-level state tăng khi tạo objects, rồi quan sát mỗi object id độc lập.

**Gợi ý:** Đánh giá `TypeName.staticField` và `this.instanceField`.

### Bài 6 — constructor chain

Đặt breakpoints trong Base và Child constructors. Theo dõi base fields, child field initializer và child constructor body; giải thích các giá trị default trước initialization.

**Gợi ý:** Tránh thay đổi logic hoặc gọi overridable method trong constructor.

### Bài 7 — exception breakpoint

Tạo Person có nullable Address, gọi chained accessor rồi gây NullPointerException. Bật exception breakpoint; tìm exact null link và sửa invariant tại constructor hoặc method boundary.

**Gợi ý:** Không dùng Helpful NPE message như một stdout cố định.

### Bài 8 — jdb độc lập IDE

Biên dịch `DebuggerBasicsDemo.java` bằng `javac -g`. Mở `jdb DebuggerBasicsDemo`, đặt `stop in DebuggerBasicsDemo$Meter.add`, dùng `where`, `locals`, `print count`, `print this.count` và `next`.

**Gợi ý:** Đọc đúng frame và nhớ transcript debugger thay theo class line numbers/JDK.

### Bài 9 — đa luồng

Chạy `ThreadDebuggerDemo` với breakpoint trong synchronized increment. Chọn từng thread stack; xác định local loop i riêng và receiver Counter shared. Thử suspend thread vs all threads khi IDE cho phép.

**Gợi ý:** Không dùng thứ tự thread chạm breakpoint làm expected output.

## 37. Checklist dùng debugger trước khi báo đã tìm ra lỗi

1. Đã debug đúng compiled class và đúng Java process chưa?
2. Source đã rebuild sau thay đổi chưa?
3. Có local variable debug symbols (`javac -g`) chưa?
4. Breakpoint ở executable line thật chưa?
5. Đang chọn đúng thread chưa?
6. Đang chọn đúng stack frame chưa?
7. `this` là receiver nào, hay method đang static?
8. Parameter/local và field có bị shadow cùng tên không?
9. Values quan sát ở **trước hay sau** statement mutate?
10. Có so field `this.x` với parameter `x` riêng chưa?
11. Có phân biệt reference value và referenced object chưa?
12. Có alias từ caller/callee hoặc nested field không?
13. Có kiểm tra identity bằng `==` đúng scope chưa?
14. Có phân biệt `equals` với `==` chưa?
15. Có static field bị tưởng nhầm là per-instance không?
16. Có nested object/collection cần mở rộng chưa?
17. Có shallow vs deep copy/defensive copy issue không?
18. Có local đã ngoài scope hoặc JIT optimization không?
19. Có constructor state chưa initialized chưa?
20. Có dynamic dispatch sang subtype override chưa?
21. Có NPE chain và exact null link chưa?
22. Có gọi mutating method trong Watches/Evaluate không?
23. Có custom toString/getter renderer làm side effects không?
24. Conditional breakpoint có quá expensive không?
25. Có breakpoint/stepping thay đổi thread scheduling không?
26. Có field writes diễn ra ở thread khác không?
27. Có cần breakpoint khi field modification thay vì chỉ line breakpoint không?
28. Có nhầm debugger diagnostics với program stdout không?
29. Có dùng debugger để xác định root cause và sau đó tạo regression test chưa?
30. Có gỡ/sửa debug-only evaluation/test values trước khi chạy production không?

## 38. Tổng kết

Khi dùng debugger để học và sửa Java Core, nên coi chương trình có **hai không gian khái niệm liên hệ nhau**: **stack frames** chứa parameters, locals và `this`; **heap objects** chứa instance fields và references tới objects khác. Java source thể hiện các quan hệ này qua tên biến, nhưng debugger cho phép quan sát chúng tại một điểm thực thi cụ thể.

`this` luôn là reference tới **receiver object trong instance context**; `this.field` phân biệt field với một local/parameter cùng tên. Java truyền **bản sao của reference value** cho parameters; mutate object qua alias có thể hiện ở caller, còn reassign parameter không đổi biến reference phía caller. Static fields thuộc class, không thuộc một receiver; records tạo value-like objects với final component fields; constructor chain và virtual dispatch quyết định vị trí thực sự của state/method đang được thực thi.

Hãy luyện **breakpoint → chọn frame/thread → inspect `this`/fields/parameters/locals → Step Into/Over/Out → so trước/sau → tìm nguyên nhân → viết regression test**. Dùng `javac -g` và `jdb` khi cần một phương pháp độc lập IDE. Khi debug đa luồng hoặc gọi Evaluate Expression, nhớ debugger có thể ảnh hưởng timing và side effects. Chính việc phân biệt đúng các khái niệm này — thay vì chỉ nhìn một giá trị trong Variables pane — tạo nên khả năng debug Java hướng đối tượng vững chắc.
