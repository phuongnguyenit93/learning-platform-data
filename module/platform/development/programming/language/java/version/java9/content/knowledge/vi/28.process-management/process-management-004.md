# ProcessHandle.Info và thông tin tiến trình có thể không có sẵn trong Java

## Mục tiêu

Trong nhóm kiến thức **quản lý tiến trình**, Java 9 bổ sung Process API để quan sát và quản lý tiến trình của hệ điều hành. **ProcessHandle** đại diện cho một tiến trình; **ProcessHandle.Info** cung cấp snapshot các thuộc tính mô tả tiến trình đó.

Các thuộc tính trong **ProcessHandle.Info** được trả về bằng **Optional**. Một trường có thể không có sẵn vì hệ điều hành, runtime, quyền truy cập hoặc trạng thái tiến trình không cung cấp dữ liệu. Vì vậy, mã ứng dụng phải xử lý từng thuộc tính độc lập, kể cả khi một số trường khác vẫn có giá trị.

Bài này trình bày API còn dùng trong Java 17+, cách đọc các thuộc tính, phân biệt thông tin thiếu với dữ liệu rỗng và cách dùng Optional an toàn.

## 1. ProcessHandle và ProcessHandle.Info

**ProcessHandle** đại diện cho một tiến trình của hệ điều hành. Các phương thức thường dùng:

- **ProcessHandle.current()** lấy handle của tiến trình Java hiện tại.
- **ProcessHandle.of(pid)** tìm handle theo PID và trả về **Optional<ProcessHandle>**.
- **pid()** trả về PID; **isAlive()** kiểm tra tiến trình còn hoạt động.
- **info()** lấy snapshot thông tin dạng **ProcessHandle.Info**.
- **parent()**, **children()** và **descendants()** truy vấn quan hệ giữa các tiến trình.
- **onExit()** trả về **CompletableFuture<ProcessHandle>** hoàn tất khi tiến trình kết thúc.

**ProcessHandle.Info** là interface lồng trong **ProcessHandle**, chứa các thuộc tính như lệnh khởi chạy, tham số, thời điểm bắt đầu, thời lượng CPU và người dùng.

Cần phân biệt hai lớp Optional:

1. **ProcessHandle.of(pid)** trả **Optional<ProcessHandle>** vì runtime có thể không tìm được handle cho PID đó.
2. Khi đã có handle, **handle.info()** trả một đối tượng **ProcessHandle.Info**; từng thuộc tính trong đối tượng này lại có Optional riêng.

Có handle không có nghĩa mọi trường thông tin đều có sẵn.

## 2. Các thuộc tính của ProcessHandle.Info

| Phương thức | Kiểu trả về | Nội dung |
|---|---|---|
| **command()** | **Optional<String>** | Đường dẫn hoặc tên lệnh thực thi |
| **commandLine()** | **Optional<String>** | Dòng lệnh khởi chạy tiến trình |
| **arguments()** | **Optional<String[]>** | Mảng đối số truyền cho lệnh |
| **startInstant()** | **Optional<Instant>** | Thời điểm tiến trình bắt đầu |
| **totalCpuDuration()** | **Optional<Duration>** | Tổng thời gian CPU đã sử dụng |
| **user()** | **Optional<String>** | Người dùng sở hữu tiến trình |

Các phương thức có thể trả về **Optional.empty()**. Đây là một phần hợp đồng API, không nhất thiết là lỗi.

- **command()** cung cấp tên hoặc đường dẫn executable. Định dạng có thể khác nhau giữa Windows, Linux và macOS; không nên giả định luôn có đường dẫn tuyệt đối.
- **commandLine()** cung cấp dòng lệnh nếu runtime lấy được. Trường này có thể vắng mặt ngay cả khi **command()** có giá trị.
- **arguments()** trả mảng chuỗi. **Optional.empty()** nghĩa là không lấy được thông tin đối số; Optional có mặt với mảng độ dài 0 nghĩa là mảng có sẵn nhưng không có phần tử.
- **startInstant()** là thời điểm bắt đầu dạng **Instant**. Có thể dùng để tính thời gian tồn tại gần đúng khi kết hợp với thời gian hiện tại.
- **totalCpuDuration()** là tổng thời gian CPU dạng **Duration**, không phải thời gian thực từ lúc tiến trình bắt đầu. Tiến trình chờ I/O lâu có thể có thời gian CPU thấp hơn nhiều so với thời gian tồn tại.
- **user()** là tên người dùng liên quan đến tiến trình nếu runtime truy xuất được. Không nên giả định đây luôn là tên tài khoản của ứng dụng đang gọi API.

## 3. Vì sao thông tin có thể không có sẵn?

Process API dựa trên dữ liệu mà hệ điều hành và runtime có thể truy xuất. Mức hỗ trợ khác nhau giữa nền tảng và cấu hình chạy.

Các nguyên nhân thường gặp:

1. **Khác biệt hệ điều hành**: không phải nền tảng nào cũng cung cấp cùng một tập thuộc tính.
2. **Quyền truy cập**: người dùng hoặc tiến trình hiện tại có thể không được phép xem một số dữ liệu của tiến trình khác.
3. **Giới hạn runtime**: implementation có thể không lấy được một trường dù handle vẫn tồn tại.
4. **Vòng đời tiến trình**: tiến trình có thể kết thúc trong khi ứng dụng đang truy vấn hoặc đang sử dụng dữ liệu đã lấy.
5. **Dữ liệu hệ điều hành không đầy đủ**: hệ điều hành có thể không ghi nhận hoặc không cung cấp trường cần thiết.

Vì vậy, không viết logic giả định **command()**, **arguments()**, **user()** hay các trường khác luôn có giá trị.

### Snapshot không phải dữ liệu cập nhật liên tục

**ProcessHandle.info()** trả snapshot tại thời điểm truy vấn, không phải đối tượng theo dõi liên tục mọi thay đổi của tiến trình.

Nếu cần thông tin mới, hãy truy vấn lại tại thời điểm cần thiết và kiểm tra **isAlive()** khi phù hợp. Không dùng snapshot cũ làm bằng chứng rằng tiến trình vẫn chạy hoặc mọi thuộc tính vẫn còn đúng.

Giữa lúc lấy handle và lúc truy vấn thuộc tính, tiến trình có thể đã kết thúc. Mã cần chấp nhận tình huống đó thay vì giả định tiến trình tồn tại suốt thao tác.

## 4. Kiểm tra Optional đúng cách

Có thể dùng các phương thức Optional tiêu chuẩn:

- **isPresent()** kiểm tra có giá trị.
- **ifPresent(action)** chỉ chạy action khi có giá trị.
- **ifPresentOrElse(action, emptyAction)** xử lý riêng hai trường hợp.
- **orElse(defaultValue)** cung cấp giá trị thay thế.
- **orElseGet(supplier)** chỉ gọi supplier khi cần giá trị thay thế.
- **orElseThrow()** ném exception nếu thiếu giá trị.
- **map()** biến đổi giá trị khi có mặt và giữ kết quả ở dạng Optional.

Ví dụ:

```java
ProcessHandle.Info info = ProcessHandle.current().info();

info.command().ifPresentOrElse(
        command -> System.out.println("Command is available"),
        () -> System.out.println("Command is unavailable"));
```

Nếu chỉ cần hiển thị trạng thái, không cần gọi **get()** hoặc giả định thuộc tính luôn có mặt.

Đoạn mã sau có thể ném **NoSuchElementException**:

```java
String command = info.command().get();
```

Cách an toàn hơn:

```java
String command = info.command()
        .orElse("Command information unavailable");
```

Chỉ dùng giá trị thay thế khi ứng dụng thật sự chấp nhận dữ liệu thiếu. Nếu thiếu thuộc tính khiến thao tác không thể tiếp tục, dùng **orElseThrow()** với thông báo rõ ràng hoặc trả kết quả lỗi theo hợp đồng ứng dụng.

Không tự đặt 0, chuỗi rỗng hoặc một thời điểm mặc định rồi coi đó là dữ liệu tiến trình thật. Ví dụ, thay **totalCpuDuration()** rỗng bằng **Duration.ZERO** có thể khiến báo cáo hiểu nhầm rằng tiến trình chưa dùng CPU. Nếu hiển thị giá trị mặc định, cần nói rõ đó là giá trị thay thế.

## 5. Xử lý từng trường thông tin

Có thể viết helper tổng quát để hiển thị trạng thái:

```java
private static void report(String label, Optional<?> value) {
    System.out.println(label + ": "
            + (value.isPresent() ? "available" : "unavailable"));
}
```

Sau đó gọi cho các thuộc tính:

```java
ProcessHandle.Info info = ProcessHandle.current().info();

report("command", info.command());
report("command line", info.commandLine());
report("arguments", info.arguments());
report("user", info.user());
report("start instant", info.startInstant());
report("total CPU duration", info.totalCpuDuration());
```

Helper chỉ báo sự hiện diện. Khi cần dùng giá trị, hãy xử lý bên trong **ifPresent**, **map**, **orElse** hoặc một thao tác Optional phù hợp.

Nếu chỉ cần số lượng đối số:

```java
info.arguments().ifPresentOrElse(
        arguments -> System.out.println(
                "Argument count: " + arguments.length),
        () -> System.out.println("Arguments unavailable"));
```

Không in toàn bộ tham số một cách mặc định. Dòng lệnh có thể chứa token, mật khẩu, đường dẫn riêng tư hoặc dữ liệu nhạy cảm được truyền qua đối số. Chỉ ghi log các trường đã được kiểm soát và thực sự cần cho chẩn đoán.

## 6. Phân biệt tiến trình không tồn tại và thông tin không có sẵn

Hai tình huống này khác nhau:

- **ProcessHandle.of(pid)** trả Optional rỗng: runtime không tìm được handle cho PID đó tại thời điểm truy vấn.
- **ProcessHandle.of(pid)** có giá trị nhưng một thuộc tính của **handle.info()** rỗng: handle có sẵn, nhưng trường thông tin cụ thể không được cung cấp.

Ví dụ:

```java
long pid = ProcessHandle.current().pid();
Optional<ProcessHandle> process = ProcessHandle.of(pid);

process.ifPresentOrElse(
        handle -> {
            System.out.println("Process handle found");
            report("command", handle.info().command());
        },
        () -> System.out.println("Process handle unavailable"));
```

Ngay cả khi **ProcessHandle.of(pid)** trả handle, tiến trình vẫn có thể kết thúc sau đó. PID cũng có thể được hệ điều hành tái sử dụng; không lưu PID lâu dài rồi coi nó là định danh duy nhất vĩnh viễn.

## 7. Ví dụ Java hoàn chỉnh

Ví dụ lấy thông tin của tiến trình Java hiện tại. Chương trình chỉ in trạng thái có sẵn/không có sẵn và số lượng đối số; không in đường dẫn executable, tên người dùng hoặc nội dung đối số.

Tạo tệp **ProcessInfoAvailabilityDemo.java**:

```java
import java.util.Optional;

public class ProcessInfoAvailabilityDemo {
    private static void report(String label, Optional<?> value) {
        System.out.println(label + ": "
                + (value.isPresent() ? "available" : "unavailable"));
    }

    public static void main(String[] args) {
        ProcessHandle current = ProcessHandle.current();
        ProcessHandle.Info info = current.info();

        System.out.println("current process alive: " + current.isAlive());
        System.out.println("pid positive: " + (current.pid() > 0));

        report("command", info.command());
        report("command line", info.commandLine());

        Optional<String[]> arguments = info.arguments();
        if (arguments.isPresent()) {
            System.out.println("arguments: available ("
                    + arguments.get().length + " entries)");
        } else {
            System.out.println("arguments: unavailable");
        }

        report("user", info.user());
        report("start instant", info.startInstant());
        report("total CPU duration", info.totalCpuDuration());
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 ProcessInfoAvailabilityDemo.java
java ProcessInfoAvailabilityDemo
```

Một lần chạy mẫu trên môi trường OpenJDK 24.0.2:

```text
current process alive: true
pid positive: true
command: available
command line: unavailable
arguments: unavailable
user: available
start instant: available
total CPU duration: available
```

Các dòng về khả năng có sẵn có thể khác trên hệ điều hành, runtime và quyền truy cập khác. Trong lần chạy mẫu này, **command()** có giá trị nhưng **commandLine()** và **arguments()** không có sẵn. Ứng dụng cần xử lý từng Optional độc lập thay vì giả định các trường luôn xuất hiện cùng nhau.

## 8. Lưu ý về bảo mật và logging

Thông tin tiến trình có thể tiết lộ dữ liệu của hệ thống:

- **commandLine()** và **arguments()** có thể chứa token truy cập, thông tin xác thực, tham số nội bộ hoặc đường dẫn nhạy cảm.
- **user()** có thể tiết lộ tên tài khoản hệ điều hành.
- **command()** có thể tiết lộ cấu trúc thư mục hoặc vị trí cài đặt ứng dụng.
- PID và thời điểm bắt đầu hữu ích cho vận hành, nhưng vẫn cần được ghi log theo chính sách của hệ thống.

Khi ghi log, ưu tiên trạng thái có sẵn/không có sẵn, PID và số liệu thật sự cần thiết. Nếu cần ghi nội dung command hoặc arguments, hãy lọc hoặc che dữ liệu nhạy cảm trước khi ghi.

Không dùng **ProcessHandle.Info** làm cơ chế xác thực hoặc cấp quyền. Thông tin mô tả tiến trình phục vụ quan sát và chẩn đoán; quyền truy cập tài nguyên phải dựa trên cơ chế bảo mật phù hợp của hệ điều hành và ứng dụng.

## 9. Lỗi thường gặp

1. **Gọi get() trên Optional mà không kiểm tra**: nếu thuộc tính không có sẵn, chương trình ném NoSuchElementException. Dùng ifPresent, orElse hoặc orElseThrow phù hợp.
2. **Cho rằng có ProcessHandle nghĩa là mọi trường Info đều có**: mỗi thuộc tính là Optional riêng và có thể vắng mặt độc lập.
3. **Nhầm Optional rỗng với chuỗi rỗng hoặc mảng rỗng**: Optional.empty() biểu thị không có dữ liệu; Optional chứa chuỗi rỗng hoặc mảng 0 phần tử là giá trị đã có nhưng rỗng.
4. **Cho rằng command có mặt thì commandLine cũng có mặt**: các thuộc tính có thể được cung cấp độc lập; kiểm tra từng Optional.
5. **Coi snapshot là trạng thái hiện tại mãi mãi**: thông tin được lấy tại thời điểm truy vấn và có thể cũ khi tiến trình thay đổi hoặc kết thúc.
6. **Giả định mọi hệ điều hành cung cấp cùng một trường**: hỗ trợ và quyền truy cập khác nhau; luôn chuẩn bị cho Optional rỗng.
7. **Dùng giá trị mặc định như thể đó là số đo thật**: thay totalCpuDuration() rỗng bằng Duration.ZERO có thể làm sai báo cáo.
8. **Ghi toàn bộ command line và arguments vào log**: đối số có thể chứa bí mật. Chỉ ghi trường cần thiết và lọc dữ liệu nhạy cảm.
9. **Coi PID là định danh vĩnh viễn**: PID có thể được tái sử dụng sau khi tiến trình kết thúc. Kiểm tra trạng thái và thời điểm khi cần đối chiếu.

## Kết luận

**ProcessHandle.Info** cung cấp snapshot thông tin mô tả tiến trình, gồm command, command line, arguments, user, thời điểm bắt đầu và thời lượng CPU. Mỗi thuộc tính được trả về bằng Optional vì khả năng truy xuất phụ thuộc nền tảng, runtime, quyền truy cập và trạng thái tiến trình.

Hãy kiểm tra từng Optional độc lập, phân biệt dữ liệu không có với dữ liệu rỗng, không gọi get() khi chưa xử lý trường hợp vắng mặt và tránh ghi thông tin nhạy cảm vào log. Cách tiếp cận này giúp chương trình hoạt động ổn định ngay cả khi hệ điều hành chỉ cung cấp một phần thông tin tiến trình.
