# Một đối tượng đảm nhận nhiều giao diện trong Java

Một thiết bị văn phòng có thể vừa **in**, vừa **quét tài liệu**, vừa **báo cáo trạng thái**. Người cần in chỉ quan tâm khả năng in; người cần quét chỉ quan tâm khả năng quét. Java cho phép **một đối tượng duy nhất thực hiện nhiều hợp đồng hành vi** bằng cách để lớp của nó `implements` nhiều `interface`.

Điểm quan trọng: mỗi `interface` mô tả một **vai trò hoặc năng lực**, không nhất thiết tương ứng với một đối tượng khác nhau. Một instance có thể được sử dụng đồng thời qua nhiều biến tham chiếu có kiểu interface khác nhau, và mọi thao tác vẫn tác động lên trạng thái của **cùng instance**.

## 1. Cú pháp cốt lõi

~~~java
interface Printable {
    void print(String document);
}

interface Scannable {
    String scan(String pageId);
}

class OfficeMachine implements Printable, Scannable {
    @Override
    public void print(String document) {
        System.out.println("In: " + document);
    }

    @Override
    public String scan(String pageId) {
        return "PDF:" + pageId;
    }
}
~~~

~~~java
OfficeMachine machine = new OfficeMachine();

Printable printer = machine;
Scannable scanner = machine;

printer.print("Báo cáo");
System.out.println(scanner.scan("HD-001")); // PDF:HD-001
~~~

Ở đây:

- `OfficeMachine` là **một lớp cụ thể** thực thi hai interface.
- `new OfficeMachine()` chỉ tạo **một đối tượng OfficeMachine**.
- `printer` và `scanner` là **hai biến tham chiếu**, mỗi biến quan sát đối tượng theo một hợp đồng khác nhau.
- Biến kiểu `Printable` chỉ cho phép gọi những hành vi công khai thuộc hợp đồng `Printable` (và những thành viên có thể gọi theo quy tắc của kiểu), dù đối tượng thực tế còn biết quét.
- Java chọn phần triển khai `print` hoặc `scan` của lớp thực tế tại thời điểm chạy.

Không tồn tại hai “nửa đối tượng” riêng biệt được tạo ra khi gán vào hai biến interface. Đây là **đa hình theo interface**: cùng một instance có thể được đối xử như nhiều kiểu hợp đồng.

## 2. Ví dụ hoàn chỉnh: một máy, nhiều vai trò

Tạo file **`MultipleInterfacesDemo.java`**. Ví dụ chạy trên Java 11+, chỉ dùng thư viện chuẩn Java.

~~~java
import java.util.Objects;

public class MultipleInterfacesDemo {

    interface Printable {
        void print(String document);
    }

    interface Scannable {
        String scan(String pageId);
    }

    interface StatusReadable {
        String status();
    }

    static final class OfficeMachine
            implements Printable, Scannable, StatusReadable {

        private final String machineId;
        private int printedPages;
        private int scannedPages;

        OfficeMachine(String machineId) {
            String checked = Objects.requireNonNull(
                    machineId, "machineId").trim();

            if (checked.isEmpty()) {
                throw new IllegalArgumentException(
                        "Mã máy không được rỗng");
            }
            this.machineId = checked;
        }

        @Override
        public void print(String document) {
            String checked = requireText(document, "document");
            printedPages++;
            System.out.println("[PRINT] " + checked);
        }

        @Override
        public String scan(String pageId) {
            String checked = requireText(pageId, "pageId");
            scannedPages++;
            return "PDF:" + checked;
        }

        @Override
        public String status() {
            return machineId + " | printed=" + printedPages
                    + " | scanned=" + scannedPages;
        }

        private static String requireText(String value, String name) {
            String checked = Objects.requireNonNull(
                    value, name).trim();
            if (checked.isEmpty()) {
                throw new IllegalArgumentException(
                        name + " không được rỗng");
            }
            return checked;
        }
    }

    // Thành phần chỉ yêu cầu năng lực in.
    static final class PrintDesk {
        private final Printable printer;

        PrintDesk(Printable printer) {
            this.printer = Objects.requireNonNull(printer);
        }

        void printReport(String report) {
            printer.print(report);
        }
    }

    // Thành phần chỉ yêu cầu năng lực quét.
    static final class ScanDesk {
        private final Scannable scanner;

        ScanDesk(Scannable scanner) {
            this.scanner = Objects.requireNonNull(scanner);
        }

        String digitize(String pageId) {
            return scanner.scan(pageId);
        }
    }

    public static void main(String[] args) {
        OfficeMachine machine = new OfficeMachine("OFFICE-01");

        Printable printPort = machine;
        Scannable scanPort = machine;
        StatusReadable monitorPort = machine;

        System.out.println("Cùng instance: "
                + ((Object) printPort == (Object) scanPort));

        PrintDesk printDesk = new PrintDesk(printPort);
        ScanDesk scanDesk = new ScanDesk(scanPort);

        printDesk.printReport("Báo cáo tháng");
        String file = scanDesk.digitize("HD-001");

        System.out.println("Kết quả quét: " + file);
        System.out.println("Trạng thái: " + monitorPort.status());
    }
}
~~~

Chạy:

~~~bash
javac MultipleInterfacesDemo.java
java MultipleInterfacesDemo
~~~

Kết quả:

~~~text
Cùng instance: true
[PRINT] Báo cáo tháng
Kết quả quét: PDF:HD-001
Trạng thái: OFFICE-01 | printed=1 | scanned=1
~~~

**Điều gì xảy ra?**

1. `machine` tham chiếu tới đối tượng `OfficeMachine` mới tạo.
2. Gán `printPort = machine`, `scanPort = machine` và `monitorPort = machine` **sao chép giá trị tham chiếu**; không gọi `new` lần nữa.
3. `PrintDesk` nhận đối tượng đó dưới vai trò `Printable`, gọi `print`, làm tăng `printedPages`.
4. `ScanDesk` nhận chính đối tượng ấy dưới vai trò `Scannable`, gọi `scan`, làm tăng `scannedPages`.
5. `monitorPort.status()` quan sát **cả hai bộ đếm trên cùng đối tượng**.

Lưu ý: trong một ví dụ sản xuất, việc tăng bộ đếm trước khi in/quét thành công có thể không phản ánh số tác vụ đã hoàn tất; ở đây các phương thức chỉ mô phỏng bằng chuỗi và console, nên không có thiết bị hay I/O thực.

## 3. Mô hình quan hệ class–interface và đối tượng tại runtime

Một lớp có thể `implements` nhiều giao diện bằng dấu phẩy:

~~~java
class OfficeMachine implements Printable, Scannable, StatusReadable {
    // ...
}
~~~

~~~mermaid
classDiagram
    class Printable {
        <<interface>>
        +print(String) void
    }
    class Scannable {
        <<interface>>
        +scan(String) String
    }
    class StatusReadable {
        <<interface>>
        +status() String
    }
    class OfficeMachine {
        -machineId String
        -printedPages int
        -scannedPages int
        +print(String) void
        +scan(String) String
        +status() String
    }
    Printable <|.. OfficeMachine
    Scannable <|.. OfficeMachine
    StatusReadable <|.. OfficeMachine
~~~

Sơ đồ lớp thể hiện **một kiểu cụ thể** hiện thực hóa **ba hợp đồng**. Còn sơ đồ tham chiếu bên dưới thể hiện **một instance đang tồn tại**:

~~~mermaid
flowchart LR
    P["printPort: Printable"] --> M["OfficeMachine instance\nOFFICE-01\nprinted=1, scanned=1"]
    S["scanPort: Scannable"] --> M
    R["monitorPort: StatusReadable"] --> M
~~~

Đừng nhầm ba **kiểu tham chiếu** với ba đối tượng. Khi một đối tượng triển khai nhiều interface, nó được phép xuất hiện ở nhiều API có yêu cầu kiểu khác nhau.

## 4. Kiểu khai báo quyết định thao tác nào có thể gọi

Giả sử:

~~~java
OfficeMachine machine = new OfficeMachine("OFFICE-02");
Printable printer = machine;
Scannable scanner = machine;
~~~

Các lời gọi hợp lệ:

~~~java
printer.print("Tài liệu A");
String result = scanner.scan("Trang B");

machine.print("Tài liệu C");
machine.scan("Trang D");
machine.status();
~~~

Nhưng:

~~~java
// printer.scan("Trang E"); // LỖI BIÊN DỊCH
// scanner.print("Tài liệu F"); // LỖI BIÊN DỊCH
~~~

Biến `printer` có **kiểu tĩnh** là `Printable`; compiler không cho phép gọi `scan` qua biến này vì hợp đồng `Printable` không khai báo `scan`. Điều đó **không có nghĩa** instance phía sau mất năng lực quét.

Nếu một API thực sự cần cả hai vai trò, có thể khai báo một kiểu hợp đồng bao gồm hai interface:

~~~java
interface MultiFunctionDevice extends Printable, Scannable {
    // Kế thừa hai hợp đồng; chưa cần khai báo thêm phương thức.
}

class FullOfficeMachine implements MultiFunctionDevice {
    @Override
    public void print(String document) {
        System.out.println("In: " + document);
    }

    @Override
    public String scan(String pageId) {
        return "PDF:" + pageId;
    }
}

MultiFunctionDevice device = new FullOfficeMachine();
device.print("Kế hoạch");
System.out.println(device.scan("Trang 01"));
~~~

Đây là **một interface kế thừa nhiều interface**, cũng hợp lệ trong Java. Nó khác với việc một class kế thừa nhiều class: Java **không hỗ trợ một class `extends` đồng thời nhiều class**.

Bảng đối chiếu:

| Khai báo | Hợp lệ? | Ý nghĩa |
| --- | --- | --- |
| `class X implements A, B` | Có | Một lớp hiện thực nhiều interface |
| `interface C extends A, B` | Có | Gộp/kế thừa nhiều hợp đồng |
| `class X extends Parent implements A, B` | Có | Một lớp cha trực tiếp, nhiều interface |
| `class X extends Parent1, Parent2` | Không | Java không cho đa kế thừa lớp |
| `Printable p = new OfficeMachine(...)` | Có | Dùng instance concrete qua tham chiếu interface |
| `new Printable()` | Không | Không khởi tạo interface trực tiếp |

## 5. Một client chỉ cần nhìn thấy vai trò nó sử dụng

`PrintDesk(Printable printer)` cho phép truyền `OfficeMachine` hoặc một máy chỉ hỗ trợ in. Nếu constructor nhận hẳn `OfficeMachine`, nó vô tình ràng buộc việc in với cả các chức năng quét và giám sát của một model cụ thể.

~~~java
class CloudPrinter implements Printable {
    @Override
    public void print(String document) {
        System.out.println("Đưa vào hàng đợi: " + document);
    }
}

// PrintDesk desk = new PrintDesk(new CloudPrinter());
~~~

Bài học ở đây là **một class có thể đáp ứng nhiều vai trò, nhưng mỗi client chỉ nên yêu cầu vai trò mình cần**. Nếu ép máy in một chức năng implement cả `Scannable` rồi ném `UnsupportedOperationException`, hợp đồng đã quá rộng. Bài *Giao diện nhỏ và phân tách vai trò* phân tích sâu Interface Segregation Principle và cách tách interface theo nhóm client.

## 6. Interface không chia sẻ các field instance

| Thành phần | Interface | Class |
|---|---|---|
| Hợp đồng phương thức | Có | Có thể khai báo/thực hiện |
| Field trạng thái riêng theo instance | Không | Có |
| Constructor | Không | Có |
| Kế thừa nhiều interface | Có, qua `extends` | Có thể `implements` nhiều interface |
| Kế thừa class | Không | Chỉ `extends` trực tiếp một class |

Bởi vậy `OfficeMachine` đặt `printedPages` và `scannedPages` trong **class**, còn `Printable`, `Scannable` chỉ công bố những thao tác mà client gọi được. Một phương thức abstract trong interface ngầm là `public`; class thực hiện không thể giảm quyền truy cập. Interface cũng có thể có `default`/`static`/`private` method nhưng không vì thế có state instance riêng.

So sánh khi nào nên dùng abstract class để dùng chung constructor, trạng thái và thuật toán được triển khai ở bài *Chọn giao diện hay lớp trừu tượng*.

## 7. Trùng tên phương thức giữa hai interface

Một lớp implement nhiều interface có thể gặp các phương thức cùng tên. Cần phân biệt **cùng hợp đồng abstract**, **overload khác tham số** và **xung đột default implementation**.

### Hai interface cùng yêu cầu một phương thức abstract

~~~java
interface Auditable {
    void log(String message);
}

interface Loggable {
    void log(String message);
}

class AuditConsole implements Auditable, Loggable {
    @Override
    public void log(String message) {
        System.out.println(message);
    }
}
~~~

Một implementation `log(String)` là đủ, vì cả hai giao diện yêu cầu cùng chữ ký với kiểu trả về tương thích. Hai interface **không tạo hai bản sao phương thức** trong đối tượng.

### Hai interface có phương thức overload

~~~java
interface TextWriter {
    void write(String text);
}

interface NumberWriter {
    void write(int number);
}

class Writer implements TextWriter, NumberWriter {
    @Override
    public void write(String text) {
        System.out.println(text);
    }

    @Override
    public void write(int number) {
        System.out.println(number);
    }
}
~~~

Hai `write` có danh sách tham số khác nhau, nên lớp triển khai cả hai dưới dạng **overloading**.

### Hai interface khai báo `default` method trùng chữ ký

Đây là trường hợp dễ gây nhầm:

~~~java
interface LocalLabel {
    default String label() {
        return "LOCAL";
    }
}

interface RemoteLabel {
    default String label() {
        return "REMOTE";
    }
}

// LỖI nếu bỏ override:
// class Hybrid implements LocalLabel, RemoteLabel { }
~~~

Java không tự chọn ngẫu nhiên một `default`. Lớp phải giải quyết xung đột, chẳng hạn tự cung cấp implementation:

~~~java
class Hybrid implements LocalLabel, RemoteLabel {
    @Override
    public String label() {
        return LocalLabel.super.label()
                + " + " + RemoteLabel.super.label();
    }
}
~~~

~~~java
Hybrid hybrid = new Hybrid();
System.out.println(hybrid.label()); // LOCAL + REMOTE
~~~

Bản `Hybrid.label()` là một phương thức duy nhất, chủ động kết hợp hai cách mặc định. Nếu logic miền nghiệp vụ cần chọn chỉ một bên, lớp có thể trả về một trong hai hoặc viết lại hoàn toàn.

**Quy tắc ưu tiên quan trọng:** nếu một superclass có phương thức instance phù hợp, phương thức của class thường được ưu tiên so với default method cùng chữ ký của interface; các xung đột default không phải lúc nào cũng cần override. Riêng trường hợp hai default không thể phân giải, compiler yêu cầu xử lý rõ.

**Không thể chỉ đổi kiểu trả về** để overload hai phương thức cùng tên/cùng tham số. Nếu hai interface yêu cầu return type không tương thích, có thể không tồn tại implementation hợp lệ; cần chỉnh lại thiết kế hợp đồng.

## 8. Một đối tượng, nhiều tham chiếu và việc ép kiểu

Trong chương trình chính:

~~~java
OfficeMachine machine = new OfficeMachine("OFFICE-03");
Printable a = machine;
Scannable b = machine;
StatusReadable c = machine;
~~~

`a`, `b`, `c` cùng tham chiếu **một** đối tượng, nhưng các thao tác có thể gọi qua từng biến là khác nhau. Phép gán không tạo bản sao của thiết bị hay trạng thái.

Ta có thể kiểm tra kiểu thực tế bằng `instanceof`:

~~~java
if (a instanceof Scannable) {
    Scannable scanner = (Scannable) a;
    System.out.println(scanner.scan("HD-002"));
}
~~~

Đoạn trên hợp lệ vì đối tượng mà `a` đang trỏ tới thực sự hỗ trợ `Scannable`. Nhưng không phải mọi `Printable` đều là `Scannable`: `new CloudPrinter()` ở ví dụ trên không tự hỗ trợ quét. Ép kiểu thiếu kiểm tra có thể gây `ClassCastException`.

Nếu một hàm **luôn cần cả in và quét**, nên khai báo tham số kiểu `MultiFunctionDevice` hoặc một abstraction phù hợp thay vì luôn nhận `Printable` rồi ép kiểu để tìm tính năng bổ sung. Dùng `instanceof` như cơ chế tùy chọn đôi khi hợp lý, nhưng lạm dụng sẽ làm giảm lợi ích của thiết kế dựa trên interface.

Lưu ý cách so sánh trong ví dụ chạy được:

~~~java
((Object) printPort == (Object) scanPort)
~~~

`==` với tham chiếu kiểm tra **cùng instance**, không kiểm tra nội dung hay hợp đồng. Việc ép hai phía sang `Object` ở đây chỉ để thể hiện rõ ta đang so sánh danh tính đối tượng.

## 9. Vai trò có thể cung cấp một thao tác mặc định nhỏ

Ví dụ interface in có thể định nghĩa hành vi in hai lần **dựa trên chính hợp đồng in**:

~~~java
interface RepeatablePrinter {
    void print(String document);

    default void printTwice(String document) {
        print(document);
        print(document);
    }
}
~~~

Lớp implement `RepeatablePrinter` chỉ cần định nghĩa `print` để dùng hành vi mặc định `printTwice`; các lần gọi vẫn chạy implementation của đối tượng thực. Nhưng default method **không cấp thêm field instance**, và phải thỏa semantics chung của mọi implementation (chẳng hạn “in hai bản” chỉ hợp lý khi gọi `print` hai lần là điều hợp lệ). Đối với quy tắc `static`/`private`, xung đột default và thay đổi interface theo phiên bản Java, xem bài *Thành viên mặc định và giới hạn tùy ngôn ngữ*.

## 10. Interface không phải là “đa kế thừa trạng thái”

Một lớp Java chỉ `extends` một superclass trực tiếp nhưng có thể `implements` nhiều interface:

~~~java
class Device {
    protected final String serial;

    Device(String serial) {
        this.serial = serial;
    }
}

interface Printable {
    void print(String text);
}

interface Scannable {
    String scan(String pageId);
}

class AllInOne extends Device implements Printable, Scannable {
    AllInOne(String serial) {
        super(serial);
    }

    @Override
    public void print(String text) {
        System.out.println(serial + " in: " + text);
    }

    @Override
    public String scan(String pageId) {
        return serial + "/PDF/" + pageId;
    }
}
~~~

`AllInOne` kế thừa trạng thái `serial` từ một superclass, đồng thời đáp ứng hai hợp đồng. Nó **không** nhận hai bộ field instance từ hai interface, vì interface không có field instance.

Khi một năng lực yêu cầu một thành phần độc lập phức tạp (ví dụ kết nối máy quét hoặc hàng đợi máy in), lớp có thể dùng **composition**:

~~~java
class PrintEngine {
    void execute(String text) {
        System.out.println("Print engine: " + text);
    }
}

class ScanEngine {
    String execute(String id) {
        return "PDF:" + id;
    }
}

class ComposedOfficeMachine implements Printable, Scannable {
    private final PrintEngine printEngine = new PrintEngine();
    private final ScanEngine scanEngine = new ScanEngine();

    @Override
    public void print(String document) {
        printEngine.execute(document);
    }

    @Override
    public String scan(String pageId) {
        return scanEngine.execute(pageId);
    }
}
~~~

Trong trường hợp này, **một đối tượng `ComposedOfficeMachine`** vẫn thực hiện hai interface, còn việc thực thi được ủy quyền cho hai đối tượng thành phần. Composition giúp giữ mã thiết bị riêng biệt mà không yêu cầu đa kế thừa class.

## 11. Khi nào nên yêu cầu hai vai trò trên cùng một đối tượng?

Nếu bộ phận in và quét hoạt động độc lập, hai dependency `Printable` và `Scannable` có thể được cung cấp bởi **hai thiết bị khác nhau**, linh hoạt hơn một siêu-interface. Nếu yêu cầu nghiệp vụ là in và quét **trên cùng thiết bị**, một hợp đồng `MultiFunctionDevice extends Printable, Scannable` diễn đạt ràng buộc đó ở cấp kiểu.

Dù một lớp tự `implements` nhiều interface, caller vẫn cần kiểm tra **hợp đồng hành vi**: `scan(pageId)` có trả đúng dữ liệu hay không, `print(document)` có bảo đảm điều đã hứa không, và các phương thức có trạng thái chia sẻ có tương tác ngoài dự kiến không. Trong ví dụ học tập, bộ đếm tăng một lần cho mỗi thao tác mô phỏng; hệ thống thật phải xác định thế nào mới tính là tác vụ hoàn tất.

Thiết kế đa vai trò có lợi khi mỗi giao diện có ý nghĩa độc lập với client, không phải để biến class thành nơi gom mọi tính năng.

## 12. Lỗi thường gặp và cách nhận diện

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ `implements A, B` tạo hai đối tượng | Từ khóa `implements` chỉ công bố và đáp ứng hợp đồng ở cấp class | Theo dõi `new` để biết số instance thực được tạo |
| Gọi `scan()` qua biến `Printable` | Kiểu khai báo không có phương thức đó | Dùng `Scannable` hoặc kiểu hợp đồng gộp |
| Implement method interface với quyền truy cập mặc định | Giảm visibility của phương thức `public abstract` | Khai báo `public` khi override |
| Quên triển khai abstract method | Concrete class chưa đáp ứng đầy đủ hợp đồng | Implement đủ hoặc khai báo class `abstract` |
| Trùng `default` method nhưng không giải quyết | Java không chọn một implementation tùy ý | Override để phân giải |
| Ép mọi `Printable` sang `Scannable` | Có implementation chỉ biết in | Kiểm tra kiểu khi thật cần, hoặc thiết kế abstraction phù hợp |
| Tạo interface quá lớn | Lớp chỉ hỗ trợ một phần phải viết method vô nghĩa | Chia theo nhóm năng lực client dùng |
| Lưu trạng thái mutable vào hằng số interface | Field interface là `static final`, chia sẻ ở cấp kiểu | Đặt trạng thái instance trong class |
| Tạo interface cho mọi lớp mà không có vai trò rõ | Tăng số kiểu và độ phức tạp | Trích abstraction khi có nhu cầu thay thế/chia sẻ hợp đồng |

## 13. Thực hành tự kiểm tra

**Câu 1.** Đoạn sau tạo bao nhiêu đối tượng?

~~~java
OfficeMachine m = new OfficeMachine("A1");
Printable p = m;
Scannable s = m;
StatusReadable r = m;
~~~

**Đáp án:** Một `OfficeMachine`. Ba phép gán sau chỉ tạo các biến tham chiếu/chép giá trị tham chiếu, không tạo instance mới.

**Câu 2.** `Printable p = new OfficeMachine("A2"); p.scan("X");` có chạy được không?

**Đáp án:** Không biên dịch vì `Printable` không khai báo `scan()`. Instance có thể quét, nhưng compiler chỉ xét API có thể gọi theo kiểu tĩnh `Printable` của biến `p`.

**Câu 3.** Tại sao `PrintDesk` dùng tham số `Printable` thay vì `OfficeMachine`?

**Đáp án:** Nó chỉ cần chức năng in. Vì vậy có thể dùng `OfficeMachine`, `CloudPrinter` hay implementation phù hợp khác mà không gắn cứng vào một lớp cụ thể.

**Câu 4.** Hai interface có cùng `void reset()` abstract; lớp implement cả hai có phải viết hai phương thức `reset()` không?

**Đáp án:** Không. Nếu chữ ký và kiểu trả về tương thích, một implementation công khai `reset()` đáp ứng cả hai. Nếu hai default method `reset()` xung đột, lớp cần chủ động giải quyết.

**Câu 5.** Một interface kế thừa đồng thời `Printable` và `Scannable` có hợp lệ không? Còn class `extends` hai class?

**Đáp án:** `interface MultiFunctionDevice extends Printable, Scannable` hợp lệ. Class Java không được `extends` hai superclass trực tiếp.

**Câu 6.** `final class OfficeMachine implements Printable, Scannable` có hợp lệ không?

**Đáp án:** Có. `final` ngăn lớp khác kế thừa `OfficeMachine`, nhưng không ngăn chính `OfficeMachine` hiện thực nhiều interface. Các đối tượng của lớp vẫn dùng được như `Printable` hay `Scannable`.

**Câu 7.** Khi một phần mềm cần cả in và quét, nên truyền riêng `Printable` và `Scannable` hay dùng một kiểu gộp?

**Đáp án:** Phụ thuộc yêu cầu. Nếu hai chức năng có thể được cung cấp bởi **hai thiết bị khác nhau**, hai tham số độc lập linh hoạt hơn. Nếu nghiệp vụ bắt buộc cả hai khả năng thuộc **cùng một thiết bị**, một hợp đồng gộp như `MultiFunctionDevice` làm rõ ràng buộc đó ở cấp kiểu.

**Ghi nhớ:** Một object có thể đóng nhiều vai trò; interface mô tả **người khác có thể yêu cầu đối tượng làm gì**, còn class xác định **đối tượng thực hiện điều đó thế nào và quản lý trạng thái ra sao**. `implements` nhiều interface mở rộng các hợp đồng mà một instance đáp ứng, không nhân bản instance và cũng không cho class đa kế thừa trạng thái.