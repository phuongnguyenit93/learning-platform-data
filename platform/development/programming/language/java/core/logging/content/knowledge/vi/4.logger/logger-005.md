# Logger gốc (Root Logger) trong Java

## 1. Logger gốc là gì?

Trong cơ chế **Java Util Logging (JUL)** thuộc JDK, **root logger** (logger gốc) là logger đứng ở đỉnh cây phân cấp logger. Root logger có **tên là chuỗi rỗng `""`** và **không có logger cha**. Những logger được đặt tên trong hệ thống JUL thường truy ngược theo quan hệ cha–con về root logger.

Một logger dùng để phát bản ghi sự kiện; handler nhận bản ghi, lọc và đưa tới console, file hoặc một đích khác. Root logger có hai vai trò đặc biệt:

1. **Điểm thừa kế cấu hình**: logger con chưa đặt level riêng có thể kế thừa level từ logger cha gần nhất có level xác định, cuối cùng là root.
2. **Điểm nhận bản ghi được chuyển lên**: khi `useParentHandlers` bật, bản ghi do logger con phát có thể được chuyển tới handler của các logger cha, kể cả root.

Cách tổ chức này giúp ứng dụng đặt mức log và handler chung ở một chỗ thay vì cấu hình từng class.

> Phạm vi bài này là `java.util.logging` của Java 17+. Các logging backend khác như Logback/Log4j2 cũng có khái niệm root logger nhưng dùng API và cú pháp cấu hình riêng; không áp dụng máy móc mọi lệnh JUL cho các framework đó.

## 2. Cách truy cập root logger

Có thể lấy root logger qua `LogManager` hoặc tên rỗng:

```java
import java.util.logging.LogManager;
import java.util.logging.Logger;

Logger root = LogManager.getLogManager().getLogger("");
Logger sameRoot = Logger.getLogger("");

System.out.println(root == sameRoot);         // true
System.out.println(root.getName().isEmpty()); // true
System.out.println(root.getParent() == null); // true
```

Đây là **đoạn mã minh họa**, cần đặt trong một phương thức như `main` để chạy. Tên logger gốc là `""`, không phải chuỗi `"root"`. Việc gọi `Logger.getLogger("root")` tạo hoặc tìm một logger *được đặt tên* `root`, không phải lấy root logger JUL.

### Root logger khác global logger

JUL cũng có một logger toàn cục truy cập qua `Logger.getGlobal()`. Tên của nó là `"global"`, và **nó không phải root logger**:

```java
Logger global = Logger.getGlobal();
Logger root = Logger.getLogger("");

System.out.println(global.getName()); // global
System.out.println(global == root);   // false
```

Logger toàn cục là một logger *được đặt tên* để dùng chung khi không muốn tạo logger riêng theo class. Root logger có chức năng nền tảng trong cây logger. Hai từ “global” và “root” không thể thay thế cho nhau.

## 3. Cây logger và quan hệ cha–con

Các tên logger thường theo tên package/class, ví dụ `com.example.order.OrderService`, `com.example.order`, `com.example`. Dấu chấm biểu diễn phân cấp **tên**, nhưng quan hệ cha thực tế phụ thuộc vào những logger đã được tạo và đăng ký trong `LogManager`.

Ví dụ minh họa khi các logger trung gian đều tồn tại:

```text
Root Logger (tên "")
└── com
    └── com.example
        └── com.example.order
            └── com.example.order.OrderService
```

Nếu chỉ tạo `com.example.order.OrderService` mà chưa có `com`, `com.example` hoặc `com.example.order`, cha trực tiếp của nó có thể là **root**, thay vì một logger trung gian chưa tồn tại. Khi một logger trung gian được tạo về sau, JUL có thể điều chỉnh quan hệ cha–con. Vì thế, không nên kết luận logger cha chỉ bằng cách cắt chuỗi tên; dùng `logger.getParent()` để quan sát quan hệ thực tế.

Một cấu hình JUL thường gặp:

```java
import java.util.logging.Logger;

Logger orderLogger =
        Logger.getLogger("com.example.order.OrderService");

Logger parent = orderLogger.getParent();
System.out.println(parent.getName());
```

Kết quả phụ thuộc những logger nào đang có trong cùng `LogManager`. Trong chương trình nhỏ chỉ đăng ký một logger tên dài, `parent.getName()` thường là chuỗi rỗng (root).

## 4. Kế thừa level từ root logger

Mỗi logger có thể đặt level riêng bằng `setLevel(...)`. Nếu một logger được đặt `setLevel(null)`, nó **kế thừa level hiệu lực** từ logger cha gần nhất có level không null. Root logger là điểm cuối của chuỗi kế thừa. Mặc định phổ biến khi JUL khởi tạo theo cấu hình JDK là root ở mức `INFO`, nhưng hệ thống có thể thay đổi mức này bằng file cấu hình hoặc bằng mã.

Các mức JUL theo thứ tự từ nghiêm trọng tới chi tiết:

```text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
```

`ALL` cho phép mọi mức và `OFF` vô hiệu hóa; đây là các giá trị điều khiển đặc biệt. Với logger kế thừa mức `WARNING`:

- `logger.severe(...)` và `logger.warning(...)` được phép tạo log record.
- `logger.info(...)` và `logger.fine(...)` bị lọc ngay tại logger.
- Nếu logger con đặt `Level.FINE` riêng, nó có thể tạo cả `FINE` bất kể root vẫn đặt `WARNING`.

Có thể kiểm tra level được thiết lập trực tiếp bằng `getLevel()`. Giá trị **`null` không có nghĩa là tắt log**, mà có nghĩa là dùng level được kế thừa. Để xác định một mức cụ thể có thể đi qua bộ lọc logger hay không, dùng `isLoggable(level)`:

```java
Logger logger = Logger.getLogger("com.example.order");
logger.setLevel(null); // Cho phép kế thừa level từ cha.

boolean allowFine = logger.isLoggable(java.util.logging.Level.FINE);
```

Đoạn mã trên kiểm tra quyết định ở **logger**; ngay cả khi trả về `true`, handler vẫn có thể lọc bản ghi trước khi xuất ra đích.

## 5. Bản ghi đi từ logger con tới root như thế nào?

Đây là phần quan trọng nhất khi phân biệt **level của logger** với **level của handler**.

Một bản ghi được xử lý theo ý tưởng sau:

```text
orderLogger.log(FINE, "...")
  │
  ├─ Kiểm tra level/filter của orderLogger
  │   ├─ Không đạt → dừng, không phát log record
  │   └─ Đạt → phát record
  │
  ├─ Handler gắn trực tiếp vào orderLogger
  │   └─ Handler kiểm tra level/filter riêng
  │
  └─ Nếu useParentHandlers=true
      └─ Handler của logger cha gần nhất
          └─ ... tiếp tục tới handler của root
```

**Một chi tiết dễ nhầm:** khi bản ghi đã vượt qua bộ lọc tại logger phát sinh, JUL chuyển record tới handler của các logger cha mà **không kiểm tra lại level hoặc filter của từng logger cha**. Mỗi handler vẫn tự kiểm tra mức và filter của chính nó.

Ví dụ: root logger đặt `WARNING`, logger `com.example.order` đặt **`FINE`**, handler của root đặt `FINE`. Bản ghi `FINE` của logger con vẫn có thể hiển thị qua root handler, vì logger con đã chấp nhận nó; level `WARNING` của root không được áp lại trong quá trình truyền lên.

Ngược lại, nếu handler của root chỉ chấp nhận `INFO`, bản ghi `FINE` từ logger con sẽ bị handler loại bỏ. Điều chỉnh **root level thôi** không đồng nghĩa đã cấu hình hết độ chi tiết log của mọi logger con.

### Bảng tình huống

| Level hiệu lực ở logger phát | Level của root logger | Level root handler | Bản ghi phát | Kết quả tại root handler |
| --- | --- | --- | --- | --- |
| `WARNING` (kế thừa root) | `WARNING` | `ALL` | `INFO` | Không tới handler: logger phát đã lọc |
| `WARNING` (kế thừa root) | `WARNING` | `ALL` | `WARNING` | Hiển thị |
| `FINE` (đặt riêng) | `WARNING` | `FINE` | `FINE` | Hiển thị khi có parent propagation |
| `FINE` (đặt riêng) | `WARNING` | `INFO` | `FINE` | Root handler loại bỏ |
| `FINE` (đặt riêng) | `WARNING` | `ALL` | `FINE` | Không tới root nếu `useParentHandlers=false` ở logger phát |

Bảng giả định không có filter bổ sung, handler hoạt động bình thường và đường truyền tới root không bị chặn ở một logger trung gian.

## 6. Ví dụ Java 17 chạy được: root level, kế thừa và handler

Ví dụ này chủ động tạo **một chương trình chạy độc lập** để kết quả ổn định: lưu cấu hình root hiện tại, tạm thời gỡ handler cũ, gắn một `ConsoleHandler` có định dạng ngắn, chạy ba phép thử rồi khôi phục cấu hình trong `finally`.

Tạo tệp `RootLoggerDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RootLoggerDemo {
    public static void main(String[] args) {
        Logger root = LogManager.getLogManager().getLogger("");
        Logger global = Logger.getGlobal();
        Logger child = Logger.getLogger("course.logging.orders");

        // Chứng minh root khác global logger.
        System.out.println("rootNameEmpty=" + root.getName().isEmpty());
        System.out.println("rootParentNull=" + (root.getParent() == null));
        System.out.println("globalIsRoot=" + (global == root));

        // Lưu trạng thái ban đầu để khôi phục sau ví dụ.
        Handler[] savedHandlers = root.getHandlers();
        Level savedRootLevel = root.getLevel();
        Level savedChildLevel = child.getLevel();
        boolean savedPropagation = child.getUseParentHandlers();

        ConsoleHandler demoHandler = new ConsoleHandler();
        demoHandler.setLevel(Level.ALL);
        demoHandler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        try {
            // Gỡ tạm handler mặc định để không in trùng dòng.
            for (Handler handler : savedHandlers) {
                root.removeHandler(handler);
            }
            root.addHandler(demoHandler);
            root.setLevel(Level.WARNING);

            child.setUseParentHandlers(true);
            child.setLevel(null); // Kế thừa WARNING từ root.
            child.info("Hidden INFO"); // Bị lọc tại child.
            child.warning("Inherited WARNING");

            child.setLevel(Level.FINE); // Override level kế thừa.
            child.fine("Explicit FINE from child");
        } finally {
            // Khôi phục các cấu hình đã thay đổi.
            child.setLevel(savedChildLevel);
            child.setUseParentHandlers(savedPropagation);
            root.setLevel(savedRootLevel);
            root.removeHandler(demoHandler);
            demoHandler.close();
            for (Handler handler : savedHandlers) {
                root.addHandler(handler);
            }
        }
    }
}
```

Chạy từ thư mục chứa file:

```bash
javac RootLoggerDemo.java
java RootLoggerDemo
```

**Đầu ra trên `stdout`:**

```text
rootNameEmpty=true
rootParentNull=true
globalIsRoot=false
```

**Các dòng log trên `stderr` của `ConsoleHandler`:**

```text
WARNING | Inherited WARNING
FINE | Explicit FINE from child
```

Không có dòng `Hidden INFO`. Trong một terminal, `stdout` và `stderr` thường cùng xuất hiện; nếu công cụ gom hai luồng, thứ tự hiển thị giữa các luồng không được đảm bảo hoàn toàn.

### Vì sao kết quả như vậy?

1. `child.setLevel(null)` làm child kế thừa `WARNING` của root, vì chương trình độc lập này không tạo logger trung gian giữa `course.logging.orders` và root.
2. `child.info(...)` bị lọc trước khi tạo log record; không handler nào nhận được.
3. `child.warning(...)` được child chấp nhận và chuyển tới handler của root.
4. `child.setLevel(Level.FINE)` cho phép child phát bản ghi `FINE`. Mặc dù root vẫn ở `WARNING`, JUL không áp lại root level khi truyền record tới root handler.
5. `demoHandler.setLevel(Level.ALL)` chấp nhận `FINE` nên dòng này xuất hiện.

Ví dụ sửa cấu hình toàn cục chỉ phù hợp khi chạy **một mình để học và thử nghiệm**. Trong ứng dụng hoặc test suite nhiều thành phần, việc thay root level/handler có thể ảnh hưởng mọi logger dùng JUL. Thường nên cấu hình một lần khi ứng dụng khởi động và không thay root giữa các request. Khi chỉ cần kiểm soát một khu vực mã, ưu tiên cấu hình logger tên package/class và handler tương ứng.

## 7. Cấu hình root logger bằng logging.properties

JUL hỗ trợ cấu hình qua file `logging.properties`. Root logger được biểu diễn bằng **dấu chấm đứng đầu tên thuộc tính** (ví dụ `.level`), còn thuộc tính `handlers` khai báo handler của root trong cấu hình JUL.

Tạo `logging.properties`:

```properties
# Handler gắn vào root logger
handlers=java.util.logging.ConsoleHandler

# Logger gốc chỉ chấp nhận WARNING khi logger con kế thừa
.level=WARNING

# Handler vẫn có thể xuất FINE từ logger con đặt FINE riêng
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

# Đặt level riêng cho logger nghiệp vụ
course.logging.orders.level=FINE
```

Tạo `RootConfigDemo.java`:

```java
import java.util.logging.Logger;

public class RootConfigDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("course.logging.orders");

        logger.fine("Order lookup started");
        logger.info("Order lookup completed");
    }
}
```

Biên dịch rồi chỉ định cấu hình **ngay khi khởi động JVM**:

```bash
javac RootConfigDemo.java
java -Djava.util.logging.config.file=logging.properties RootConfigDemo
```

Với cấu hình này, cả `FINE` và `INFO` từ `course.logging.orders` đều có thể ra console, dù `.level=WARNING`. Lý do: logger con có `level=FINE` riêng và handler root có `level=FINE`. Kết quả thực tế của `SimpleFormatter` còn có ngày giờ, tên logger và các metadata khác nên không cố định từng dòng như formatter trong ví dụ đầu.

Nếu xóa dòng `course.logging.orders.level=FINE`, logger con kế thừa root `WARNING`: cả `FINE` lẫn `INFO` sẽ bị lọc tại logger, dù console handler vẫn chấp nhận `FINE`. Nếu đổi handler level thành `WARNING`, cả hai bản ghi cũng không được hiển thị vì handler lọc chúng sau khi logger phát.

**Lưu ý:** cách root khai báo `handlers` trong `logging.properties` thuộc JUL. Nếu dự án Spring Boot dùng SLF4J/Logback, cấu hình level/appenders thường ở `application.properties`/`application.yml` và cấu hình Logback. Root logger Logback không được quản lý bằng `LogManager` JUL theo cách trên trừ khi có bridge/tích hợp được cấu hình rõ ràng.

## 8. useParentHandlers và hiện tượng log trùng

Mặc định, logger có tên thường cho phép truyền bản ghi lên logger cha bằng `getUseParentHandlers() == true`. Khi **cả child và root** đều gắn console handler, một sự kiện có thể được in hai lần:

```text
Logger OrderService
   ├─ ConsoleHandler của OrderService → in một lần
   └─ chuyển tới Root Logger
       └─ ConsoleHandler của root       → in lần thứ hai
```

Không phải do hàm `logger.info(...)` được gọi hai lần, mà do hai handler cùng nhận một `LogRecord`. Có hai cách xử lý phổ biến:

**Cách A — Dùng handler chung của root.** Không gắn handler riêng cho từng logger con. Để parent propagation bật và dùng cấu hình root cho các đích log chung:

```java
Logger logger = Logger.getLogger("com.example.order");
logger.setUseParentHandlers(true);
logger.info("Order submitted");
```

**Cách B — Logger con tự quản lý đích riêng.** Nếu logger con cần một handler riêng, tắt chuyển lên cha khi muốn tránh lặp:

```java
Logger logger = Logger.getLogger("com.example.order");
logger.setUseParentHandlers(false);
// Phải gắn handler phù hợp cho logger này trước khi kỳ vọng
// các log được hiển thị hoặc lưu lại.
```

Không nên gọi `setUseParentHandlers(false)` mà quên gắn handler riêng; lúc đó logger có thể tạo sự kiện nhưng không có đích nào nhận, khiến log “biến mất”.

**Không nhầm với kế thừa level:** tắt `useParentHandlers` chỉ ngăn **chuyển record tới handler cha**. Một logger có `getLevel() == null` vẫn có thể **kế thừa mức level từ cha**. Hai cơ chế này độc lập.

Nếu có nhiều tầng logger, việc tắt propagation tại một logger trung gian có thể chặn record không đi tiếp tới các handler cao hơn; khi chẩn đoán log trùng hoặc thiếu, cần kiểm tra chuỗi thực tế từ logger phát sinh lên root.

## 9. Khi nào nên thay đổi root logger?

### Các tình huống hợp lý

- **Chương trình dòng lệnh nhỏ:** dùng cấu hình root chung để gửi mọi log JUL ra console.
- **Ứng dụng dùng JUL nhất quán:** dùng root để áp cấu hình mặc định cho các thành phần, rồi override level của package cần debug.
- **Khởi động ứng dụng:** cấu hình handler cho console/file/collector một lần tại giai đoạn bootstrap.
- **Debug tạm thời:** hạ ngưỡng handler và logger liên quan để xem `FINE`, sau đó hoàn nguyên để tránh log quá nhiều.

### Các rủi ro cần tránh

1. **Tăng mức chi tiết trên root quá rộng:** các package và thư viện kế thừa có thể tạo lượng log lớn. Chọn logger cụ thể để debug nếu có thể.
2. **Chỉ đổi level logger mà quên handler:** bản ghi `FINE` vẫn bị handler mức `INFO` hoặc `WARNING` lọc.
3. **Chỉ chỉnh root level và nghĩ đã chặn mọi logger con:** các logger đặt level riêng vẫn có thể phát log và root handler có thể nhận.
4. **Gắn thêm handler lên root mỗi lần chạy request/test:** có thể làm log trùng, mở nhiều file, giữ tài nguyên. Cấu hình handler theo vòng đời ứng dụng.
5. **Thay đổi handler toàn cục khi nhiều thread đang log:** có thể gây thay đổi hành vi quan sát của các thread khác. Khởi tạo có kiểm soát, đóng handler thuộc sở hữu của mình đúng thời điểm.
6. **Đóng handler mà mình không sở hữu:** handler của root có thể đang được thành phần khác dùng; tránh gọi `close()` bừa bãi với handler được chia sẻ.
7. **Lẫn JUL và SLF4J/Logback:** root của JUL và root của Logback là hai đối tượng/cơ chế khác nhau. Tìm logging backend đang hoạt động trước khi sửa cấu hình.
8. **Ghi thông tin nhạy cảm:** cấu hình root quá chi tiết có thể khiến token, header xác thực hoặc dữ liệu người dùng lọt vào log. Hạn chế trường log và quyền truy cập từ nguồn.

## 10. Cách chẩn đoán khi log không xuất hiện

Khi `logger.info(...)` hoặc `logger.fine(...)` không hiển thị như kỳ vọng, kiểm tra theo thứ tự:

1. **Đúng logger nào?** Đọc `getName()`, lấy `getParent()` để xác định vị trí trong phân cấp thực tế.
2. **Logger có chấp nhận level không?** Dùng `isLoggable(Level.FINE)`. Nếu `getLevel()==null`, lần theo level kế thừa từ cha.
3. **Log có được truyền tới cha không?** Kiểm tra `getUseParentHandlers()` và những logger trung gian.
4. **Handler có tồn tại không?** Xem `getHandlers()` ở logger phát, các cha và root.
5. **Handler chấp nhận level/filter không?** Một bản ghi có thể bị handler loại bỏ dù logger đã chấp nhận.
6. **Handler có ghi được ra đích không?** ConsoleHandler thường dùng `System.err`; FileHandler còn chịu tác động từ đường dẫn, quyền ghi, rotation và hệ thống thu thập.
7. **Có cấu hình hoặc bridge khác tác động không?** Thư viện logging, cấu hình JVM hay môi trường triển khai có thể thay đổi mức, handler hoặc đích nhận.

Một vài biểu thức hỗ trợ debug (đoạn minh họa đặt trong phương thức có biến `logger`):

```java
System.out.println("name = " + logger.getName());
System.out.println("level = " + logger.getLevel()); // null = kế thừa
System.out.println("parent = " +
        (logger.getParent() == null
                ? "(none)" : logger.getParent().getName()));
System.out.println("parentHandlers = " + logger.getUseParentHandlers());
System.out.println("canLogFine = " + logger.isLoggable(Level.FINE));
```

`getHandlers()` chỉ liệt kê handler gắn **trực tiếp** lên logger được gọi, không tự trả về toàn bộ handler kế thừa từ cha. Vì vậy, nhận thấy `logger.getHandlers().length == 0` chưa đủ để kết luận logger không có nơi xuất log: record vẫn có thể tới handler của root khi propagation bật.

## 11. Câu hỏi tự kiểm tra

**Câu 1:** Root logger JUL có tên `"root"` hay `""`?  
**Đáp án:** Chuỗi rỗng `""`. `Logger.getLogger("root")` là logger tên thường, khác root.

**Câu 2:** `Logger.getGlobal()` có phải root logger không?  
**Đáp án:** Không. Global logger có tên `global`; root logger có tên rỗng và không có cha.

**Câu 3:** Root đang có level `WARNING`. Logger con đặt `FINE`, root handler cũng `FINE` và truyền lên cha đang bật. Log `FINE` của con có ra console không?  
**Đáp án:** Có thể có. JUL không kiểm tra lại level của root khi chuyển record từ con lên handler của root; nếu handler chấp nhận và không có filter khác, record được xuất.

**Câu 4:** Tắt `setUseParentHandlers(false)` có làm logger con ngừng kế thừa root level không?  
**Đáp án:** Không. Nó chỉ điều khiển việc chuyển bản ghi tới handler cha, không điều khiển level kế thừa.

**Câu 5:** Một bản ghi `INFO` xuất hiện hai lần sau khi thêm `ConsoleHandler` vào logger con. Cần kiểm tra gì?  
**Đáp án:** Handler gắn trực tiếp và handler trên chuỗi cha/root; nếu cả hai đều xuất cùng một sự kiện, dùng handler chung của root hoặc ngăn parent propagation cho logger tự quản lý handler.

**Điểm cần nhớ:** Root logger JUL là đỉnh phân cấp có tên `""`. Nó cung cấp level mặc định cho logger chưa override và nhận record chuyển lên từ logger con. Muốn kiểm soát log chính xác phải xét **cả level tại logger phát, parent propagation và level/filter tại từng handler**.
