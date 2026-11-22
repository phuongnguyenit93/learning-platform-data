# 19.4 Attach hoặc launch bằng jdb và quản lý vòng đời phiên

## 1. Mục tiêu: kết nối đúng JVM, điều khiển đúng vòng đời

**`jdb` (Java Debugger)** là trình gỡ lỗi dòng lệnh đi kèm JDK, sử dụng **Java Debug Interface (JDI)** để giao tiếp với JVM đích qua cơ chế của **Java Platform Debugger Architecture (JPDA)**. Nó cho phép đặt breakpoint, xem stack/local variables, kiểm tra thread, chạy từng bước và tiếp tục thực thi mà không cần IDE.

Tuy nhiên, thao tác debug đúng không chỉ là “mở được prompt `jdb`”. Bạn phải xác định:

- **Ai tạo JVM đích?** `jdb` *launch* một tiến trình mới hay chỉ *attach* vào ứng dụng đã chạy?
- **Ai lắng nghe kết nối?** JVM đích với `server=y` hay trình debugger với `server=n`?
- **Ứng dụng chạy hay đang đợi?** `suspend=y/n` quyết định việc chờ trước khi đi qua giai đoạn khởi động; breakpoint cũng có thể làm thread/VM dừng sau đó.
- **Làm gì khi hoàn tất?** `cont`/`resume`, `clear` và `quit` mang ý nghĩa khác nhau với dừng ứng dụng hoặc kết thúc phiên.
- **Làm gì nếu mất kết nối?** Debugger và JVM là hai tiến trình/đối tượng khác nhau; không được suy ra trạng thái tiến trình chỉ từ việc cửa sổ `jdb` đóng.

Bài học tập trung vào **JDK 17+ và HotSpot/JDWP socket trên máy phát triển**; tham chiếu cú pháp Oracle JDK 21. Một số connector hoặc hành vi cụ thể phụ thuộc nền tảng, JDK và quy trình chạy service.

**Kết quả mong đợi:** tự chạy được hai quy trình *launch* và *attach*, giải thích mối quan hệ giữa debugger/JVM/port/PID, quan sát và điều khiển một breakpoint, rồi đóng phiên có kiểm soát mà không vô tình treo hoặc ngắt ứng dụng quan trọng.

## 2. Mô hình ba lớp: JDI, JDWP, transport

```text
Terminal người debug                  JVM ứng dụng (debuggee)
+------------------+                 +---------------------------+
| jdb              |                 | Java code + threads       |
| lệnh breakpoint, |                 | JDWP agent               |
| step, cont, quit |                 |                           |
|     JDI          |                 | JVM TI / runtime          |
+---------+--------+                 +-------------+-------------+
          |                                        |
          +----------- JDWP messages --------------+
                   qua dt_socket TCP
                      (hoặc transport khác)
```

- **JDI**: API để phía debugger điều khiển/quan sát target VM. `jdb` là một ứng dụng client dùng JDI; giao diện jdb không phải giao diện riêng của mọi JVM.
- **JDWP**: giao thức trao đổi yêu cầu và event, ví dụ đặt breakpoint hoặc báo một thread đang dừng.
- **`dt_socket`**: transport dựa trên TCP. Thông thường phía `jdb` và JVM dùng `host:port` để gặp nhau.
- **JDWP agent**: được nạp vào target JVM bằng `-agentlib:jdwp=...` khi dùng attach vào chương trình đã được chuẩn bị cho debug.

Cần phân biệt rõ ba loại định danh:

| Định danh | Ví dụ | Vai trò |
| --- | --- | --- |
| **PID** của JVM | `12345` | Hệ điều hành định danh tiến trình; dùng để kiểm tra đúng ứng dụng, log, `jcmd`... |
| **JDWP address** | `127.0.0.1:5005` | Địa chỉ kết nối debugger; `jdb -attach` dùng **address**, không phải PID |
| **Tên main class** | `JdbSessionDemo` | Cần trong lệnh **launch** để JVM mới biết chạy chương trình nào; attach không cần chạy lại `main` |

**Sai lầm dễ gặp:** `jdb -attach 12345` không có nghĩa “attach vào PID 12345” trên Linux/macOS. Với connector socket mặc định, `12345` trong cú pháp đó được hiểu là **địa chỉ/port JDWP**; nếu JVM đã có PID 12345 nhưng không bật JDWP thì lệnh này không tự tạo được phiên debug.

Với một số connector nâng cao, JDI có `com.sun.jdi.ProcessAttach` nhận `pid`, nhưng yêu cầu/cơ chế khác với cách attach socket thông thường. Khi học `jdb`, nên bắt đầu từ `-attach host:port` có cấu hình rõ ràng.

## 3. Bốn chế độ kết nối cần phân biệt

| Chế độ | JVM đích khởi động thế nào? | Phía nhận kết nối | Lệnh phổ biến | Khi nào dùng |
| --- | --- | --- | --- | --- |
| **Launch (default)** | `jdb` tạo JVM mới cho class được chỉ định | Connector launch quản lý kết nối | `jdb -classpath . JdbSessionDemo` | Kiểm soát từ trước khi `main` chạy |
| **Launch ngay (`-launch`)** | `jdb` tạo JVM mới ngay, dừng trước tải class ứng dụng đầu tiên | Connector launch | `jdb -launch -classpath . JdbSessionDemo` | Muốn target sẵn sàng ở trạng thái dừng, dùng `cont` thay `run` |
| **Attach** | JVM **đã được khởi động với JDWP agent** | Thường target JVM: `server=y` | `jdb -attach 127.0.0.1:5005` | Điều tra ứng dụng đang chạy, không khởi chạy bản sao |
| **Listen / reverse connect** | Target JVM tự mở kết nối đến debugger | `jdb`: listener, target `server=n` | `jdb -listen 5006` và JVM `server=n` | Debugger phải là phía lắng nghe, ví dụ do ràng buộc kết nối mạng |

**`server=y/n` nằm trong cấu hình agent của JVM đích**, **không** có nghĩa `jdb` tự động được chạy trên server hoặc client ứng dụng. Cả hai phía có thể trên cùng máy, container hoặc hai máy có mạng được bảo vệ.

**Các kết nối từ xa phải được coi là thao tác đặc quyền.** JDWP cung cấp khả năng xem dữ liệu/chạy lệnh thông qua debugger, không phải một endpoint HTTP có xác thực người dùng mặc định. Trong bài thực hành chỉ bind loopback; không đặt `address=*:5005` trên internet hoặc mạng dùng chung.

## 4. Chương trình Java 17+ để thực hành

Chương trình dưới đây tồn tại đủ lâu để bạn attach, có method nhỏ để đặt breakpoint, không dùng framework và chỉ in một vài dòng để terminal dễ đọc.

Lưu **toàn bộ** thành file **`JdbSessionDemo.java`**:

```java
public final class JdbSessionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        int rounds = args.length == 0
                ? 60
                : Integer.parseInt(args[0]);
        if (rounds < 1 || rounds > 600) {
            throw new IllegalArgumentException(
                    "rounds must be from 1 to 600");
        }

        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("rounds=" + rounds);

        for (int i = 1; i <= rounds; i++) {
            int score = calculate(i);
            if (i <= 3 || i % 10 == 0) {
                System.out.println("tick=" + i
                        + " score=" + score);
            }
            Thread.sleep(1_000);
        }

        System.out.println("completed");
    }

    private static int calculate(int value) {
        int squared = value * value;
        return squared + 10;
    }
}
```

Biên dịch với **thông tin debug đầy đủ**:

```bash
javac -g JdbSessionDemo.java
```

`javac -g` yêu cầu ghi thông tin dòng/source/local variables vào bytecode. Không có thông tin local variable thích hợp, `locals` trong `jdb` có thể không hiển thị biến mong muốn, dù chương trình vẫn chạy bình thường. Hãy biên dịch **đúng file nguồn và đúng bản class** dùng khi debug.

Chạy độc lập để kiểm tra:

```bash
java JdbSessionDemo 10
```

Với `rounds=10`, các dòng **kết quả logic xác định** gồm:

```text
PID=<PID thực của tiến trình>
rounds=10
tick=1 score=11
tick=2 score=14
tick=3 score=19
tick=10 score=110
completed
```

Dòng PID thay đổi theo mỗi lần chạy; `<PID thực của tiến trình>` là **chú thích**, không phải stdout nguyên văn. Các dòng `score` được tính từ công thức `value * value + 10`. Giữa các vòng có `Thread.sleep(1_000)` nên `rounds=10` chạy khoảng 10 giây, có thể lâu hơn nếu máy chịu tải hoặc debugger dừng nó.

Nếu cần cửa sổ attach dài hơn, dùng `120` hoặc `180` vòng. Không đặt vòng vô hạn trong demo vì khó xác minh kết thúc phiên và thu hồi tiến trình.

## 5. Quy trình A — jdb launch một JVM mới

Đây là cách rõ ràng nhất khi muốn debug từ đầu. Mở terminal trong thư mục chứa `JdbSessionDemo.class` rồi chạy:

```bash
jdb -classpath . JdbSessionDemo 20
```

Phân tích câu lệnh:

- `jdb` chạy **debugger process**.
- `-classpath .` cho **target JVM** tìm class trong thư mục hiện tại; không phải đường dẫn riêng của file `.java`.
- `JdbSessionDemo` là tên class chứa `main` (không thêm `.java`).
- `20` được truyền vào `main(String[] args)` như tham số `rounds`; không phải thời gian breakpoint.
- Với launch mặc định, có thể cấu hình breakpoint ở prompt rồi dùng lệnh **`run`** để khởi chạy/cho thực thi target theo mô hình launch của jdb.

Tại prompt `jdb`, nhập lần lượt:

```text
help
stop in JdbSessionDemo.calculate
run
```

`stop in ...` đặt method-entry breakpoint cho `calculate`. Khi target chạm breakpoint, jdb dừng theo chính sách của event; prompt có thể chứa tên thread và số frame, không cần khớp nguyên văn ví dụ nào. Sau đó kiểm tra:

```text
where
locals
next
locals
```

- `where` hiển thị stack của thread hiện hành, giúp xác nhận đang ở `calculate`.
- `locals` liệt kê local variables trong frame khi bytecode có debug info và thread đang dừng. Ở method entry, `value` đã có giá trị, nhưng `squared` có thể chưa được gán; sau khi `next` đi qua phép gán, nó mới có giá trị.
- `next` thực hiện dòng tiếp theo **trong frame hiện hành**; `step` đi vào method được gọi khi phù hợp. Với compiler/JVM/line mapping, bước chính xác giữa các dòng có thể khác; quan sát line hiện thời trên prompt.

Để tránh breakpoint này kích hoạt ở **mọi** vòng lặp tiếp theo, bỏ nó rồi tiếp tục:

```text
clear JdbSessionDemo.calculate
cont
```

`clear` bỏ breakpoint đã đặt; `cont` tiếp tục thực thi đang dừng. Nếu chưa clear, lần gọi `calculate` tiếp theo sẽ lại dừng và bạn phải `cont` nhiều lần. Muốn xem các breakpoint còn hoạt động, nhập `stop` hoặc `clear` không tham số tùy hỗ trợ của bản `jdb`.

Khi target chạy đủ 20 vòng, ứng dụng in `completed` và kết thúc bình thường. Debugger có thể thông báo target VM đã thoát; **đây là một kết thúc của target**, không phải bằng chứng rằng `jdb` hoặc shell đã bị kill cưỡng bức. Kết thúc giao diện debugger bằng `quit` khi cần.

### Biến thể `-launch`: không dùng `run` lần nữa

```bash
jdb -launch -classpath . JdbSessionDemo 20
```

Oracle JDK 21 mô tả `-launch` bắt đầu debugged application **ngay khi khởi động jdb**, target dừng trước khi ứng dụng bắt đầu chạy. Vì vậy, trong phiên này:

```text
stop in JdbSessionDemo.calculate
cont
```

`-launch` **loại bỏ nhu cầu dùng `run`**. Trộn `run` của luồng launch mặc định vào phiên `-launch` có thể khiến người học hiểu sai trạng thái target hoặc thử khởi động lại không mong muốn.

**Điểm nhận biết launch:** Không cần JDWP port thủ công hay PID trước đó. Debugger là phía tạo JVM mới; khi cấu hình kết thúc phiên phải kiểm tra riêng trạng thái tiến trình do nó launch (xem mục 10).

## 6. Quy trình B — jdb attach vào JVM đang chạy

**Attach** không tạo bản sao ứng dụng; nó kết nối tới JVM đang có. Bạn **phải chuẩn bị JDWP agent** khi bắt đầu tiến trình đích theo quy trình đơn giản của bài học.

### Bước 1 — khởi động target JVM, bật JDWP nhưng không chờ

Mở terminal A, chạy:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 JdbSessionDemo 120
```

Thành phần quan trọng:

| Tham số | Vai trò | Nếu hiểu sai |
| --- | --- | --- |
| `-agentlib:jdwp=...` | Nạp agent JDWP bên trong JVM đích | `jdb` không tự debug được một JVM bất kỳ không chuẩn bị |
| `transport=dt_socket` | Dùng TCP socket | Không phải file Unix socket hay HTTP |
| `server=y` | **Target JVM lắng nghe** debugger kết nối | Không phải đặt ứng dụng Java thành HTTP server |
| `suspend=n` | Cho phép ứng dụng bắt đầu chạy dù chưa có debugger | Có thể bỏ lỡ code path trước khi attach |
| `address=127.0.0.1:5005` | Chỉ bind loopback port 5005 | PID của target **không phải** 5005 |
| `JdbSessionDemo 120` | Chạy 120 vòng, đủ thời gian attach | Tham số 120 không liên quan debugger timeout |

Terminal A có thể in thông báo agent đang lắng nghe và các dòng `PID=...`, `tick=...`. Giữ terminal A mở để nhìn **dấu hiệu JVM tiếp tục chạy** khi debugger detach.

**Nếu chọn port khác:** đổi cả phía Java và `jdb`. Nếu port đang bị sử dụng, JDWP có thể thất bại khi bind; giải quyết xung đột ở môi trường lab thay vì cố kết nối một tiến trình lạ.

### Bước 2 — kết nối bằng jdb

Mở terminal B:

```bash
jdb -attach 127.0.0.1:5005
```

Hoặc với địa chỉ loopback mặc định trong môi trường hỗ trợ:

```bash
jdb -attach 5005
```

**Đây là thao tác attach theo socket address.** Không truyền `JdbSessionDemo` vào command line, vì target đã chạy `main` của nó. Nếu attach thành công, jdb cung cấp prompt và bạn có thể đặt breakpoint khi ứng dụng còn sống.

### Bước 3 — điều khiển phiên attach

Tại prompt:

```text
threads
stop in JdbSessionDemo.calculate
```

Đợi vòng tiếp theo gọi `calculate`. Khi breakpoint dừng:

```text
where
locals
next
locals
clear JdbSessionDemo.calculate
cont
```

Do `suspend=n`, target đã chạy trước khi attach; nếu chương trình kết thúc trước khi jdb kịp kết nối, lỗi kết nối là bình thường. Chạy lại với `rounds` dài hơn **trong môi trường lab**; không thể dùng jdb khôi phục những dòng code đã chạy qua.

### Bước 4 — rời phiên mà không yêu cầu tắt service

Nếu mục tiêu là ngừng quan sát và **để target tiếp tục chạy**, phải:

1. Kiểm tra không còn breakpoint gây dừng hoặc watchpoint không mong muốn; `clear`/`unwatch` nếu đã tạo.
2. Nếu target đang bị dừng tại breakpoint, dùng `cont`; nếu bạn chủ động `suspend` thread/VM, dùng lệnh `resume` phù hợp. Đừng nghĩ “đóng cửa sổ terminal” là một bước quản lý trạng thái an toàn.
3. Dùng `quit` (hoặc `exit` theo lệnh nội bộ của jdb) để **thoát trình debugger**. Trong mô hình attach thông thường, disconnect giải phóng các suspension/event requests thuộc debugger và target tiếp tục chạy nếu còn công việc. Tuy nhiên kết thúc JDB **không tự bảo đảm** target không bị ảnh hưởng bởi timeout, lỗi ứng dụng hoặc một debugger/process khác.
4. Quan sát terminal A: JVM còn in `tick` và sau đó `completed` theo vòng đời ứng dụng không? Kiểm tra PID/health check nếu đây là service thật.

Đừng nhầm lệnh `quit` bên trong **jdb** với `System.exit()` của ứng dụng hoặc `VirtualMachine.exit(int)` của API JDI. Cái trước là đóng giao diện debugger; cái sau yêu cầu target VM terminate và không phải cách “detach nhẹ nhàng”.

## 7. `suspend=y` — chờ debugger ngay từ startup

Đôi khi cần đặt breakpoint **trước** khi `main` đi qua đoạn cần quan sát. Khi launch một target riêng rồi attach sau, dùng:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 JdbSessionDemo 20
```

Mặc định của tùy chọn `suspend` trong cấu hình JDWP có thể là `y` nếu không chỉ định; nên **viết tường minh** để không gây nhầm. Với `suspend=y`:

- JVM đã khởi tạo agent và đang đợi debugger; chương trình **chưa thực thi `main` bình thường**.
- Ở terminal B, chạy `jdb -attach 127.0.0.1:5005`, kiểm tra kết nối và đặt breakpoint `stop in JdbSessionDemo.calculate`.
- Dùng `cont` để cho target tiếp tục. Lệnh `run` **không dùng** trong phiên attach vì `main` được khởi chạy bởi lệnh `java` ở terminal A, không phải bởi `jdb`.

Nếu terminal A chỉ báo “Listening for transport...” và không in `PID=...`, đó có thể là **trạng thái chờ có chủ đích**, không phải ứng dụng deadlock. Tuy nhiên trên một service thực, `suspend=y` có thể làm health check/ready probe thất bại trong lúc đợi debugger, gây restart loop; chỉ áp dụng trong thời điểm bảo trì có kiểm soát.

**Lưu ý:** Một số môi trường/debugger có thể tự resume VMStart event theo cách khác; hãy đọc prompt và trạng thái thực tế, dùng `cont` khi target đang dừng chờ.

## 8. Chế độ listen: đảo phía chủ động kết nối

Trong chế độ attach thông thường, target là **server JDWP** (`server=y`) và jdb chủ động kết nối. **Listen** đảo chiều: jdb đợi, target mở kết nối tới debugger bằng `server=n`. Cấu hình trong phòng lab trên cùng máy:

**Terminal B — chạy debugger ở chế độ listen trước:**

```bash
jdb -listen 5006
```

**Terminal A — khởi động target sau:**

```bash
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5006 JdbSessionDemo 20
```

- `server=n` cho biết JVM đích là **bên kết nối ra ngoài**, còn `jdb` phải lắng nghe trước.
- `address` chỉ tới endpoint mà `jdb` đang listen. Nếu chưa có listener hoặc network không thông, target có thể thất bại kết nối/khởi động theo cấu hình timeout.
- Với `suspend=y`, target dừng ở startup theo cơ chế JDWP; đặt breakpoint khi jdb kết nối rồi `cont`.
- `-listenany` có thể chọn một địa chỉ listener tự động trong cấu hình JDI, nhưng khi học nên dùng port rõ ràng; không nhầm chữ “any” với cấp phép kết nối qua mọi giao diện mạng.

Đây là **quy trình kết nối khác**, không phải attach qua port `5005` ở mục 6. Không khởi động một JVM với `server=y` rồi đồng thời chờ `jdb -listen` mà kỳ vọng hai bên tự tìm nhau: cả hai đều listen thì không có bên chủ động mở kết nối.

Trong môi trường có firewall/NAT, bất cứ chiều nào cũng cần đường mạng được ủy quyền, xác thực ở lớp mạng và giới hạn endpoint. Không biến JDWP thành cổng công khai.

## 9. Connector nâng cao và tham số CLI cần dùng đúng

`jdb` cung cấp connector shortcuts và cách chỉ định connector tường minh. Để xem connector tồn tại ở **JDK của bạn**:

```bash
jdb -listconnectors
```

Cách attach qua connector socket tương đương:

```bash
jdb -connect com.sun.jdi.SocketAttach:hostname=127.0.0.1,port=5005
```

Để debug một ứng dụng mà **jdb tạo JVM mới**, dùng shortcut `jdb JdbSessionDemo` hoặc connector `com.sun.jdi.CommandLineLaunch` với `main` thích hợp (tên argument và quoting tùy shell). Không cần dùng connector tường minh chỉ để thực hiện một demo cơ bản.

**Lựa chọn đáng phân biệt:**

- `-classpath .`: classpath để **debuggee** load bytecode trong chế độ launch; khi attach, classpath thuộc về target đã chạy và không bị thay bởi tùy chọn jdb.
- `-sourcepath <path>`: đường dẫn tìm **source .java** cho `list`/đọc dòng source. Nó không thay classpath dùng để tìm compiled class.
- `-J-Xmx256m`: truyền `-Xmx256m` cho JVM **chạy jdb** (trình debugger).
- `-R-Xmx256m`: truyền option cho **target JVM do jdb launch**, theo tài liệu man page JDK 21.
- `-listconnectors`: liệt kê connector hiện có; không dùng lệnh này thay cho `JFR.check` hoặc `jcmd`.
- `-attach host:port`: attach qua address, không tạo JVM mới.
- `-launch`: launch target ngay, không cần gọi `run` như với luồng launch mặc định.

**Với package:** nếu class nằm trong `com.example.debug`, cần chạy `jdb -classpath ... com.example.debug.JdbSessionDemo` theo tên đầy đủ. Đặt breakpoint bằng tên class đầy đủ nếu trùng tên simple class. Mẫu demo dùng default package nhằm giảm thao tác thiết lập, không phải khuyến nghị tổ chức package cho production.

## 10. Vòng đời phiên: bảy trạng thái cần theo dõi

```text
[Chưa có target]
        |
        +-- jdb launch ---------+
        |                       |
        +-- java -agentlib JDWP +---> [Target tồn tại]
                                       |
                            [Chưa kết nối/đang listen]
                                       |
                             JDWP connection thành công
                                       |
                               [JDB kết nối]
                                 /        \
                       breakpoint         cont/resume
                          |                   |
                     [Target dừng] ------> [Target chạy]
                          |
                     step/next/where
                                       |
                         +-------------+--------------+
                         |                            |
                    quit/đứt kết nối            Target kết thúc
                         |                            |
                    [Debugger đóng]          [VMDeath/disconnect]
                         |                            |
                [Target có thể còn sống]    [Target đã kết thúc]
```

**Cần giám sát hai thực thể riêng:** (1) **tiến trình `jdb`**, (2) **tiến trình JVM đích**. Với attach, mục tiêu thông thường là **đóng kết nối debug mà không dừng service**; với launch, tiến trình được tạo ra bởi debugger và có thể có vòng đời gắn với phiên đó, vì vậy phải **xác minh target PID** thay vì đoán.

| Hành động | Ảnh hưởng tức thời | Việc kiểm tra sau đó |
| --- | --- | --- |
| `stop in ...` | Đăng ký method breakpoint; chưa nhất thiết làm target dừng ngay | Chờ đường code thực thi; xem dòng báo breakpoint |
| `stop at Class:line` | Đăng ký breakpoint theo source line | Kiểm tra class có line info đúng và line tồn tại |
| `step` / `next` | Chạy một bước từ trạng thái đang dừng | Xem stack/locals sau mỗi bước |
| `cont` | Cho chương trình tiếp tục sau breakpoint/step | Xem có breakpoint khác chặn nó không |
| `suspend` | Đặt trạng thái suspend cho VM/thread theo lệnh | Dùng `resume` tương ứng; đừng bỏ service treo |
| `clear ...` | Gỡ breakpoint được chỉ định | Lặp `clear`/`stop` để xác nhận |
| `quit` / `exit` trong jdb | Đóng phiên/giao diện debugger | Quan sát PID target, output và health riêng |
| Chương trình tự `return` từ `main` hoặc `System.exit` | JVM đi vào quá trình kết thúc theo logic ứng dụng | Lệnh debug tiếp theo có thể báo VMDisconnected |
| `kill -9` hoặc chấm dứt cưỡng bức target | Target bị giết bởi OS; không phải detach | Kiểm tra hậu quả nghiệp vụ; không dùng để thoát phiên bình thường |

**Một breakpoint theo chính sách suspend-all có thể tạm dừng nhiều thread**, không chỉ method/thread bạn quan tâm. Trên service sống, việc giữ prompt quá lâu có thể làm timeout request/health checks và khiến người quan sát hiểu nhầm “sự cố trở nên nặng hơn”. Giảm thời gian dừng và dùng phương pháp ít xâm lấn khi cần.

### Không đồng nhất quit với JDI `VirtualMachine.exit(int)`

Theo JDI API, `VirtualMachine.dispose()` đóng kênh debugger, hủy event requests, khôi phục những thread bị suspend bởi debugger và cho phép tiếp tục ứng dụng trong phạm vi cơ chế đó. `VirtualMachine.exit(int)` lại yêu cầu **kết thúc target VM đột ngột**. Đây là hai khái niệm khác nhau dù tên lệnh nội bộ jdb có thể là `exit`.

**Cách quản lý an toàn:** sử dụng `quit` để đóng giao diện debug, nhưng vẫn phải xác minh JVM đích có còn chạy hay không. Đừng dựa vào việc đóng terminal hoặc mất mạng để bảo đảm điều kiện khôi phục.

### Kịch bản A — attach vào service đang phục vụ traffic

- Ghi rõ thời điểm và PID/instance/service trước khi attach.
- Hạn chế breakpoint suspend-all và không thay giá trị biến trong production nếu không có kiểm soát.
- Xem xong thì clear breakpoint, cont/resume, quit, kiểm tra health/latency và khả năng tiếp tục xử lý.
- Nếu JDWP agent vẫn bật, **cổng debug vẫn là một bề mặt truy cập đặc quyền**; việc quit jdb không có nghĩa đã vô hiệu hóa agent. Quản lý thông qua restart/configuration theo quy trình triển khai nếu muốn đóng cổng.

### Kịch bản B — jdb launch một tiến trình thử nghiệm

- `run` cho phép chương trình thực thi, `cont` khi bị dừng.
- Để chương trình hoàn tất bình thường khi có thể; ghi code/exit status từ target.
- Nếu thoát debugger khi target còn sống, kiểm tra process còn chạy hay đã dừng theo connector/implementation; không giả định target chắc chắn được kill hoặc chắc chắn vẫn chạy.
- Không để lại các process thử nghiệm còn bind cổng debug hoặc giữ tài nguyên ngoài ý muốn.

## 11. Checklist đóng phiên không để lại “tiến trình treo”

Trước khi kết thúc debug, tự hỏi:

1. **Mục tiêu ban đầu là gì?** Attach production để quan sát hay launch một demo được phép kết thúc?
2. **Có thread nào đang dừng do breakpoint/`suspend` không?** Dùng `where`, `threads` và trạng thái prompt để nhận biết.
3. **Đã gỡ breakpoints/watchpoints không cần thiết?** Dùng `clear`/`unwatch` nếu đã thiết lập.
4. **Đã `cont` hoặc `resume` đúng ngữ cảnh chưa?** Đừng trả lại service đang bị tạm dừng rồi đi mất.
5. **Lệnh sẽ đóng cái gì?** `quit` đóng jdb; không phải lệnh tương đương `System.exit`. Xác nhận với tiến trình thật.
6. **Kết nối JDWP có còn mở sau khi jdb thoát không?** JVM `server=y` có thể vẫn lắng nghe. Đối chiếu chính sách bảo mật của môi trường.
7. **Có thay đổi runtime nào cần khôi phục không?** Biến gán bằng `set`, method invocation qua `print/eval`, trigger side effect và thread state đều có thể làm ứng dụng thay đổi.
8. **Có ghi chú sự cố đầy đủ không?** Thời điểm, PID, build, port, breakpoints, stack, bước điều khiển và trạng thái dịch vụ sau khi rời.
9. **Nếu mất kết nối bất ngờ:** cần kiểm tra JVM/agent/port và thread state độc lập; không dùng giả định để gửi tiếp lệnh vào một process khác có thể đã sử dụng lại port đó.
10. **Nếu vẫn muốn process chạy:** xác minh log/health/metrics tiến triển và target PID phù hợp; với service cluster cũng xác minh instance đúng.

## 12. An toàn khi debug qua mạng, container hoặc production

**JDWP không được xem là cổng API công khai.** Người kết nối có quyền kiểm tra dữ liệu bên trong JVM và có thể điều khiển hành vi/chạy biểu thức. Do đó:

- Trong phòng lab, ưu tiên `address=127.0.0.1:5005`; không tự ý đổi thành `address=*:5005` hay bind `0.0.0.0` trên mạng có người lạ.
- Nếu buộc phải debug từ xa, sử dụng **kênh quản trị được bảo vệ** (ví dụ SSH tunnel/vùng mạng tin cậy) và điều kiện phân quyền thích hợp; không công bố cổng JDWP trực tiếp.
- Kiểm tra network namespace: JVM trong container có thể listen trên loopback của **container**, không phải loopback host. `jdb` trên host sẽ không thấy cổng nếu không có đường kết nối được cấu hình.
- Port-forward/tunnel phải dựa trên cơ chế truy cập được duyệt, giới hạn người dùng/thời gian và được thu hồi sau điều tra.
- `suspend=y` có thể khiến container không qua readiness probe; orchestrator có thể restart tiến trình ngay khi debugger chưa kịp attach.
- Debugger breakpoint với `suspend-all` có thể tác động toàn bộ request xử lý trên instance; đánh giá mức độ ảnh hưởng trước khi dùng.
- `-agentlib:jdwp=...` là cấu hình **trên JVM**, không phải `jdb` tự có quyền bật JDWP cho bất kỳ PID. Khởi động lại ứng dụng để bật agent cần tuân thủ quy trình triển khai.
- Tập tin `.class` và `.java` dùng trong debug phải đúng build; không gửi source hoặc dữ liệu nhạy cảm lên máy không được phép.
- Với JDK mới có virtual threads, danh sách thread có thể không đầy đủ trong chế độ mặc định của jdb. JDK 21 có `-trackallthreads` khi cần quan sát thêm, nhưng có thể tăng chi phí/tải; không bật vô điều kiện trên hệ thống có rất nhiều virtual threads.

Trong production, nên cân nhắc **JFR, metrics, tracing và thread dumps** trước khi dùng breakpoints tạm dừng toàn VM. `jdb` là công cụ có khả năng thay đổi trạng thái tiến trình; một phiên debug không phải quan sát hoàn toàn thụ động.

## 13. Khắc phục lỗi kết nối và trạng thái

| Dấu hiệu | Nguyên nhân thường gặp | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| `jdb -attach 5005` báo không kết nối được | Target chưa bật JDWP, port sai, tiến trình đã thoát hoặc firewall/namespace | Xác nhận target command line, PID, listening address, port và trạng thái process |
| Target không in dòng `PID=...` sau lệnh Java | `suspend=y` khiến JVM chờ debugger ở startup | Attach đúng port rồi `cont`; hoặc dùng `suspend=n` cho phiên muốn chạy ngay |
| JDWP báo không bind được địa chỉ | Port đã có process khác sử dụng hoặc address không khả dụng | Chọn port hợp lệ trên host lab, đổi **cả** target và jdb |
| Prompt jdb có nhưng breakpoint không hit | Code path đã chạy, class chưa load, method khác overload, breakpoint sai tên | Kiểm tra `stop`, `methods`, class name đầy đủ, làm lại với `suspend=y` khi cần |
| `locals` trống hoặc “no local variables” | Thiếu debug info hoặc không đứng ở stack frame thích hợp | `javac -g`, đúng class build, `where`/`up`/`down` |
| Breakpoint trúng nhiều lần khiến service tưởng treo | Method trong loop, chưa `clear` hay chưa `cont` | Clear, cont, dùng tình huống ngắn hoặc điều kiện dừng phù hợp |
| `run` không làm gì khi attach | Chế độ attach không tạo target JVM | Dùng `cont` khi đang dừng; muốn start mới phải launch JVM riêng |
| `jdb` đóng nhưng service không chạy | Target đã crash/exit, còn suspend khác, network/process issue | Kiểm tra PID/health và trạng thái thread độc lập |
| `JDB` vừa nối vừa ngắt ngay | Target kết thúc, port đổi, network mất, lỗi chính sách attach | Xem log target, exit status, JDK tương thích và cổng thực |
| Debug source hiển thị sai dòng | `.java` không khớp `.class` đang chạy | Đồng bộ artifact/source, debug symbols, `-sourcepath` |

**Tránh “sửa” nhầm:** Nếu thấy target chờ `suspend=y`, không dùng `kill -9` như bước đầu. Đây có thể là trạng thái mong muốn. Nếu target đã thực sự mất, một kết nối JDWP không thể hồi sinh JVM hoặc phục hồi stack đã biến mất.

### Tối thiểu hóa tác động của điều tra

- Ưu tiên breakpoint ở code path ít traffic hoặc trên instance thử nghiệm.
- Khi dừng, xem đúng thông tin cần thiết rồi `cont` nhanh.
- Với method lặp liên tục, clear breakpoint trước khi cont để tránh dừng liên tiếp.
- Không thực hiện `eval`/`set` lên các object nghiệp vụ nếu chỉ cần quan sát.
- Nếu có nhiều phiên/IDE debugger, kiểm tra agent chỉ cho phép những kết nối hợp lệ theo implementation; tránh để các công cụ tranh nhau điều khiển target.

## 14. So sánh ba cuộc đối thoại mẫu

### A. Launch cho unit-like demo

Terminal:

```bash
javac -g JdbSessionDemo.java
jdb -classpath . JdbSessionDemo 20
```

Bên trong jdb:

```text
stop in JdbSessionDemo.calculate
run
where
locals
next
clear JdbSessionDemo.calculate
cont
```

**Giải thích:** JVM đích được tạo bởi jdb; `run` là hành động của launch workflow; breakpoint bắt từ lần gọi đầu. Chờ chương trình kết thúc theo logic của nó và xác minh trạng thái.

### B. Attach vào JVM đang chạy

Terminal A:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 JdbSessionDemo 120
```

Terminal B:

```bash
jdb -attach 127.0.0.1:5005
```

Bên trong jdb:

```text
stop in JdbSessionDemo.calculate
where
locals
clear JdbSessionDemo.calculate
cont
quit
```

**Giải thích:** JVM được tạo bên ngoài debugger. `quit` rời jdb sau khi đã cho chạy tiếp; tiếp tục quan sát terminal A để xác nhận target chạy tiếp. Không dùng `run` để khởi động lại `main` khi attach.

### C. Reverse connect với listener

Terminal B:

```bash
jdb -listen 5006
```

Terminal A:

```bash
java -agentlib:jdwp=transport=dt_socket,server=n,suspend=y,address=127.0.0.1:5006 JdbSessionDemo 20
```

Bên trong jdb:

```text
stop in JdbSessionDemo.calculate
cont
```

**Giải thích:** debugger lắng nghe trước; target kết nối ra ngoài tới địa chỉ đó. `server=n` không có nghĩa JDWP bị tắt. Khi hoàn thành, phải biết JVM nào còn chạy và có tiếp tục lắng nghe kết nối ngoài ý muốn hay không.

## 15. Lỗi tư duy phổ biến

1. **Nhầm port với PID:** `jdb -attach 5005` nhắm JDWP address, không tự attach hệ điều hành PID 5005.
2. **Không bật JDWP nhưng vẫn thử attach:** lệnh `java` thường không tự mở cổng remote-debugger.
3. **Nhầm `server=y` thành “ứng dụng HTTP server”:** đó là chế độ lắng nghe kết nối của agent JDWP.
4. **Đặt cả hai bên đều ở chế độ listen:** không ai khởi tạo kết nối; hiểu đúng chiều `server=y/n`.
5. **Quên `suspend=y`:** ứng dụng chưa in log vì chờ debugger, không tự động là deadlock.
6. **Cố `run` trong phiên attach:** target đã chạy; `run` thuộc workflow launch của jdb.
7. **Quên `cont` sau breakpoint:** target vẫn dừng và service health có thể suy giảm.
8. **Không clear breakpoint trong loop:** cứ tiếp tục thì lại dừng, tạo cảm giác ứng dụng kẹt.
9. **Dùng `quit` như lệnh kill target:** debugger và debuggee có vòng đời khác nhau.
10. **Đóng terminal là xong:** phải xác minh thread và target PID/health được khôi phục.
11. **Bật port JDWP ra public:** lộ quyền kiểm soát JVM, rủi ro nghiêm trọng.
12. **Thiếu `javac -g` nhưng muốn xem local variables:** bytecode có thể thiếu thông tin phục vụ debug.
13. **Đặt `-sourcepath` thay `-classpath`:** một cái tìm source, một cái tìm compiled classes khi launch.
14. **Không phân biệt `-J` và `-R`:** tác động tới hai JVM khác nhau.
15. **Không kiểm tra đúng build/class name:** breakpoint có thể đặt ở method không tồn tại trong target.
16. **Kết luận debug session mất là ứng dụng cũng mất:** lỗi kết nối không chứng minh target đã chết.
17. **Ngầm sửa biến/trạng thái chỉ để “xem thử”:** việc evaluate method hoặc set field có thể có side effect thực.
18. **Bỏ qua container namespace:** loopback trong container không nhất thiết là loopback của host.
19. **Coi một phiên debug là quan sát không tốn chi phí:** suspend-all, breakpoint/step làm chậm thời gian thực.
20. **Không ghi nhật ký session:** về sau không rõ ai đã đặt breakpoint, khi nào và đã giải phóng chưa.

## 16. Bài tập tự kiểm tra

**Câu 1 — phân biệt định danh.** Một JVM có PID `4112`, JDWP lắng nghe `127.0.0.1:5005`. Lệnh attach đúng là gì?

**Đáp án:** `jdb -attach 127.0.0.1:5005` hoặc `jdb -attach 5005` nếu công cụ mặc định dùng loopback. `4112` không phải socket address.

**Câu 2 — trạng thái startup.** JVM chạy với `server=y,suspend=y`, đã in “Listening for transport...” nhưng chưa in `PID=...` từ `main`. Có thể là bug?

**Đáp án:** Có thể là trạng thái chờ debugger hoàn toàn đúng. Kết nối, đặt breakpoint và `cont` để tiếp tục trước khi gọi đó là lỗi.

**Câu 3 — vòng đời launch.** Chạy `jdb JdbSessionDemo 20`, muốn đặt breakpoint trước khi chạy main, dùng `run` hay `cont`?

**Đáp án:** Với launch mặc định, đặt `stop in ...` rồi `run` theo workflow. Nếu dùng `-launch`, target đã được launch và dừng trước khi bắt đầu class ứng dụng, nên đặt breakpoint rồi `cont`.

**Câu 4 — vòng đời attach.** Bạn đã dừng JVM đang phục vụ request tại breakpoint. Có nên dùng `quit` ngay để “không ảnh hưởng” không?

**Đáp án:** Nên giải phóng breakpoint, cho thread/VM tiếp tục theo trạng thái hợp lệ, sau đó quit và **kiểm tra health**. Disconnect thường giải phóng suspension do debugger, nhưng không thay thế bước xác minh service.

**Câu 5 — chiều kết nối.** `jdb -listen 5006` phải đi cùng target `server=y` hay `server=n`?

**Đáp án:** `server=n`: target chủ động kết nối tới listener của jdb. Với `server=y`, target cũng chờ debugger kết nối và hai bên đều listen.

**Câu 6 — an toàn.** Vì sao không nên dùng `address=*:5005` trên production nếu không có bảo vệ?

**Đáp án:** Cổng JDWP cấp quyền thao tác sâu với JVM; nó không phải endpoint có phân quyền người dùng mặc định. Chỉ mở trong vùng mạng được ủy quyền và thời gian cần thiết.

**Thực hành:** hoàn thành hai phiên với demo, một `launch` và một `attach`. Với mỗi phiên, ghi **ai khởi động target**, PID, JDWP address (nếu có), trạng thái trước/sau breakpoint, lệnh chạy tiếp, cách rời debugger và bằng chứng target còn/chấm dứt đúng ý. Với attach, quan sát terminal A tiếp tục in `tick` sau `quit`. Tự giải thích vì sao cùng lệnh `quit` không phải là bằng chứng ứng dụng đã bị kill.

## 17. Tài liệu chính thức

- [Oracle JDK 21 — The `jdb` Command: launch, attach, `-launch`, `-listen` và breakpoint](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html).
- [Oracle JDK 21 — JPDA Connection and Invocation Details: `-agentlib:jdwp`, `server`, `suspend`, `address`, `dt_socket` và connectors](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html).
- [Oracle JDK 21 — JDI `VirtualMachine`: `dispose()` so với `exit(int)`, `resume()`/`suspend()`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/VirtualMachine.html).
- [Oracle JDK 21 — JDI `ThreadReference`: trạng thái suspend/resume và các hạn chế](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/com/sun/jdi/ThreadReference.html).
- [Oracle Java Debug Interface API (JDI), module `jdk.jdi`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jdi/module-summary.html).

**Nguyên tắc chốt:** *Launch* = debugger khởi tạo JVM; *attach* = JVM đã có được chuẩn bị cho JDWP; *listen* = debugger chờ JVM chủ động kết nối. `run`, `cont`, `clear`, `resume` và `quit` có **đích tác động khác nhau**. Một phiên debug chỉ thực sự được đóng an toàn khi bạn đã xác minh cả **kết nối debugger, trạng thái các thread, tiến trình target và cổng JDWP** theo mục tiêu ban đầu.
