# Đọc stack trace và tìm vị trí phát sinh lỗi — Java 17+

## 1. Stack trace giúp trả lời điều gì?

Khi một lỗi hoặc ngoại lệ (exception) xảy ra trong Java, **stack trace** ghi lại chuỗi lời gọi phương thức đang hoạt động tại thời điểm lỗi được tạo hoặc khi stack trace được thu thập. Nhìn vào đó, lập trình viên có thể xác định:

- **Loại lỗi:** `NumberFormatException`, `NullPointerException`, `ArrayIndexOutOfBoundsException`, `IllegalStateException`...
- **Thông điệp:** cung cấp thêm ngữ cảnh, có thể chứa đầu vào hoặc mô tả điều kiện sai.
- **Vị trí trong mã:** lớp, phương thức, file `.java` và số dòng khi thông tin có sẵn.
- **Đường đi của lời gọi:** phương thức nào gọi phương thức nào dẫn đến lỗi.
- **Nguyên nhân lồng nhau:** dòng `Caused by:` cho thấy ngoại lệ nguyên nhân khi một ngoại lệ bị bọc trong ngoại lệ khác.

**Mục tiêu:** đọc trace từ lỗi thực tế để tìm đoạn mã cần kiểm tra và **nguyên nhân gốc**, thay vì chỉ xóa một dòng khiến ứng dụng báo lỗi.

Stack trace là **ảnh chụp call stack**, không phải toàn bộ lịch sử hoạt động của chương trình; nó không tự ghi mọi giá trị biến hoặc mọi sự kiện đã diễn ra.

## 2. Cấu trúc một stack trace thường thấy

Một trace minh họa (số dòng trong ví dụ là **minh họa**, thay đổi theo bản mã và bản JDK):

~~~text
Exception in thread "main" java.lang.NumberFormatException: For input string: "bad"
    at java.base/java.lang.NumberFormatException.forInputString(NumberFormatException.java:67)
    at java.base/java.lang.Integer.parseInt(Integer.java:668)
    at StackTraceReadingDemo.parsePart(StackTraceReadingDemo.java:9)
    at StackTraceReadingDemo.calculate(StackTraceReadingDemo.java:13)
    at StackTraceReadingDemo.load(StackTraceReadingDemo.java:18)
    at StackTraceReadingDemo.main(StackTraceReadingDemo.java:31)
~~~

Cách đọc:

| Thành phần | Ý nghĩa |
|---|---|
| `Exception in thread "main"` | Có ngoại lệ chưa được xử lý trên luồng `main` |
| `java.lang.NumberFormatException` | **Kiểu ngoại lệ** (không chuyển đổi được chuỗi sang số) |
| `For input string: "bad"` | Thông điệp giúp xác định đầu vào không hợp lệ |
| `at java.base/java.lang.Integer.parseInt(...)` | Frame thuộc thư viện chuẩn Java trong module `java.base` |
| `at StackTraceReadingDemo.parsePart(...:9)` | Frame của **mã ứng dụng** tại `parsePart`, dòng minh họa 9 |
| `at ...calculate(...)`, `...load(...)`, `...main(...)` | Chuỗi các phương thức gọi dẫn tới `parsePart` |

Dòng `at Class.method(File.java:line)` thường mô tả:

- `Class`: tên lớp, có thể gồm package.
- `method`: tên phương thức/constructor (constructor thường hiện là `<init>`).
- `File.java`: tên file nguồn khi có thông tin.
- `line`: số dòng được gắn với frame khi có debug line information.

Dấu `at` không có nghĩa là mỗi dòng ấy đều **ném một ngoại lệ khác nhau**: chúng thường là những frame trong **cùng một chuỗi lời gọi**.

## 3. Đọc từ trên xuống và tìm frame ứng dụng đầu tiên

Với trace thông thường, các frame liệt kê từ **nơi gần điểm tạo lỗi nhất** xuống những hàm gọi ở phía ngoài:

~~~text
Integer.parseInt -> parsePart -> calculate -> load -> main
         ^              ^            ^         ^       ^
    API thư viện     mã ứng dụng đang dẫn tới lỗi
~~~

Ở ví dụ trên, `Integer.parseInt` trong JDK phát hiện chuỗi không phải số. Nhưng vị trí **mã ứng dụng đầu tiên** cần kiểm tra là lời gọi `Integer.parseInt(...)` bên trong `parsePart`.

Quy trình:

1. Đọc **kiểu ngoại lệ và thông điệp**, chưa vội sửa code.
2. Tìm các frame mang tên package/lớp của **dự án**; mở **file và số dòng** được nêu.
3. Xem câu lệnh ở dòng ấy, đặc biệt đối số truyền vào method có thể gây lỗi.
4. Theo các frame tiếp theo để biết **ai cung cấp dữ liệu** và vì sao chuỗi `"bad"` tới được `parseInt`.
5. Dựng lại đầu vào, thêm kiểm tra/validation hoặc điều chỉnh logic tại nơi phù hợp, rồi chạy lại test.

**Không mặc định frame đầu tiên là dòng cần sửa**: nếu ngoại lệ được ném trong JDK/framework, frame đầu tiên ở thư viện. Cũng không mặc định **frame ứng dụng đầu tiên** luôn là nguyên nhân nghiệp vụ: có thể dữ liệu đã sai từ lớp gọi bên ngoài. Nó là một **điểm bắt đầu để điều tra**.

## 4. Từ file và số dòng quay về mã nguồn

Giả sử một dòng trace có dạng:

~~~text
at com.example.service.UserService.load(UserService.java:42)
~~~

Hãy tìm lớp `com.example.service.UserService`, mở file `UserService.java` và xem **dòng 42** của **đúng phiên bản mã đã biên dịch**. Nếu mã đang mở đã khác bản chạy, số dòng có thể không còn khớp.

Một số trường hợp đặc biệt:

| Dạng trong trace | Điều cần hiểu |
|---|---|
| `File.java:42` | Có thông tin tên file/số dòng |
| `Unknown Source` | Thiếu thông tin nguồn/dòng thích hợp |
| `Native Method` | Frame đi qua phương thức native |
| `Class$$Lambda...` hoặc các frame framework | Có thể do lambda, reflection, proxy hay thư viện trung gian |
| `at ...main(Main.java:...)` | Entry point thường nằm gần đáy chuỗi lời gọi đồng bộ |

Biên dịch bằng `javac` thông thường giữ thông tin dòng hữu ích. Nếu file `.class` được biên dịch/biến đổi mà không còn debug line info, không nên tự khẳng định số dòng. Với `javac -g` có thể yêu cầu thông tin debug đầy đủ hơn; `-g:none` bỏ thông tin debug tương ứng.

Thao tác quan trọng là **đối chiếu trace với artifact/version đang chạy**, không chỉ với bản nguồn mới nhất trên máy.

## 5. Phân biệt nơi phát sinh và nơi bắt lỗi

~~~java
static int parseNumber(String text) {
    return Integer.parseInt(text);
}

static int readValue() {
    return parseNumber("oops");
}

public static void main(String[] args) {
    try {
        System.out.println(readValue());
    } catch (NumberFormatException ex) {
        System.out.println("Cannot parse input");
    }
}
~~~

**Exact stdout** khi đặt các phương thức đúng trong một lớp chạy được:

~~~text
Cannot parse input
~~~

- Ngoại lệ **phát sinh** ở lời gọi `Integer.parseInt("oops")` trong `parseNumber`.
- `readValue` gọi `parseNumber` và không xử lý ngoại lệ.
- `main` **bắt ngoại lệ** nên chương trình có thể tiếp tục.
- Nếu chỉ in `"Cannot parse input"` và **không ghi log cause/stack**, thông tin vị trí lỗi bị thiếu; việc bắt lỗi không làm cho đoạn chuyển đổi tự thành công.

Với trường hợp đầu vào người dùng, bắt `NumberFormatException` và thông báo dữ liệu sai có thể hợp lý. Với bug không mong đợi, cần log đủ bối cảnh để điều tra, không “nuốt” lỗi một cách im lặng.

## 6. `Caused by`: lần theo ngoại lệ gốc trong chuỗi bọc

Một ứng dụng đôi khi bọc ngoại lệ thấp tầng bằng một ngoại lệ có ý nghĩa nghiệp vụ cao hơn:

~~~java
static void loadConfig() {
    try {
        Integer.parseInt("not-a-number");
    } catch (NumberFormatException ex) {
        throw new IllegalStateException("invalid configuration", ex);
    }
}
~~~

Nếu không có `catch` ở lớp ngoài, stack trace thường có hai phần:

~~~text
java.lang.IllegalStateException: invalid configuration
    at StackTraceReadingDemo.loadConfig(StackTraceReadingDemo.java:45)
    at StackTraceReadingDemo.main(StackTraceReadingDemo.java:70)
Caused by: java.lang.NumberFormatException: For input string: "not-a-number"
    at java.base/java.lang.Integer.parseInt(Integer.java:668)
    at StackTraceReadingDemo.loadConfig(StackTraceReadingDemo.java:43)
    ... 1 more
~~~

**Đây là trace minh họa**, không phải stdout được cam kết chính xác cho chương trình ở mục thực hành; số dòng của JVM và mã ứng dụng có thể khác.

- **Ngoại lệ ngoài:** `IllegalStateException`, mang ngữ cảnh “invalid configuration”.
- **Ngoại lệ nguyên nhân:** `NumberFormatException`, do chuỗi sai định dạng số.
- `getCause()` cho phép đọc nguyên nhân nếu có.
- Phần `Caused by` nằm sâu hơn trong chuỗi nguyên nhân thường là điểm hữu ích để hiểu lỗi bắt nguồn từ đâu.

Dòng `... 1 more` có nghĩa là một số frame cuối **trùng với phần trace trước đó và đã được rút gọn khi in**, không có nghĩa “thêm một ngoại lệ mới”. Tương tự, `Suppressed:` có thể liệt kê ngoại lệ bị giữ lại (thường gặp khi đóng tài nguyên trong try-with-resources), và **không đồng nghĩa với `Caused by`**.

Khi bọc một ngoại lệ để thêm ngữ cảnh, truyền **cause** vào constructor (ví dụ `new IllegalStateException("...", ex)`) để không đánh mất trace của lỗi ban đầu.

## 7. `printStackTrace`, logger và luồng stdout/stderr

Java hỗ trợ:

~~~java
try {
    Integer.parseInt("NaN");
} catch (NumberFormatException ex) {
    ex.printStackTrace(); // Mặc định in vào System.err.
}
~~~

`printStackTrace()` thường in **kiểu ngoại lệ, thông điệp, frames và chuỗi causes**. Theo mặc định nó viết lên **stderr** (`System.err`), khác với `System.out.println` vốn viết vào **stdout**. Khi chạy từ terminal hoặc hệ thống log, stdout và stderr có thể được thu thập/hiển thị theo cơ chế khác nhau, không nên dùng thứ tự xen kẽ hai luồng làm cam kết chính xác.

Trong ứng dụng lớn, nên dùng hệ thống log với thông điệp có bối cảnh và đối tượng ngoại lệ (logger có thể in stack trace tùy API/cấu hình). Đừng ghi những dữ liệu nhạy cảm như mật khẩu, token hoặc thông tin cá nhân vào lỗi/log.

**Để minh họa stdout ổn định**, chương trình ở mục 9 **không dùng `printStackTrace()`**; thay vào đó đọc dữ liệu có cấu trúc bằng `getStackTrace()`, chỉ in tên những phương thức thuộc class demo. Trong thực tế, đừng thay toàn bộ stack trace bằng tên method khi cần điều tra: giữ file/line và cause trong hệ thống chẩn đoán thích hợp.

## 8. `StackTraceElement` và cách lọc frame thuộc dự án

Mỗi phần tử trả về bởi:

~~~java
StackTraceElement[] frames = error.getStackTrace();
~~~

cung cấp metadata:

| API của `StackTraceElement` | Trả về |
|---|---|
| `getClassName()` | Tên lớp chứa frame |
| `getMethodName()` | Tên method/constructor |
| `getFileName()` | Tên file nguồn, có thể `null` |
| `getLineNumber()` | Số dòng nếu biết, có thể âm nếu không biết |
| `isNativeMethod()` | Frame có thuộc native method không |

Một vòng lặp lọc những frame của chương trình:

~~~java
for (StackTraceElement frame : error.getStackTrace()) {
    if (frame.getClassName().equals(StackTraceReadingDemo.class.getName())) {
        System.out.println("at=" + frame.getMethodName());
    }
}
~~~

Với lỗi từ `parsePart` thông qua `calculate` và `load`, các frame ứng dụng dự kiến theo thứ tự **parsePart → calculate → load → main**. Đây là thứ tự call stack tại điểm lỗi; vòng lặp dùng tên class để tránh phụ thuộc vào số dòng hoặc frame thư viện Java.

**Đừng chỉ lọc class name trong một dự án lớn**: đây là cách trình bày có chủ đích cho chương trình demo đơn file. Với hệ thống nhiều lớp, lọc dựa trên các package dự án và đọc cả các frame liên quan từ thư viện.

## 9. Chương trình Java 17+ chạy độc lập

Lưu đúng file **`StackTraceReadingDemo.java`**:

~~~java
public final class StackTraceReadingDemo {
    private StackTraceReadingDemo() {}

    static int parsePart(String[] parts, int index) {
        return Integer.parseInt(parts[index]);
    }

    static int calculate(String[] parts) {
        return parsePart(parts, 1) + 2;
    }

    static void load() {
        String[] fields = {"10", "bad"};
        System.out.println("value=" + calculate(fields));
    }

    static void wrapCause() {
        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException ex) {
            throw new IllegalStateException("invalid setting", ex);
        }
    }

    static String firstAppMethod(Throwable failure) {
        for (StackTraceElement frame : failure.getStackTrace()) {
            if (frame.getClassName().equals(
                    StackTraceReadingDemo.class.getName())) {
                return frame.getMethodName();
            }
        }
        return "(none)";
    }

    static void printAppFrames(Throwable failure) {
        for (StackTraceElement frame : failure.getStackTrace()) {
            if (frame.getClassName().equals(
                    StackTraceReadingDemo.class.getName())) {
                System.out.println("at=" + frame.getMethodName());
            }
        }
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (NumberFormatException ex) {
            System.out.println("caught=" + ex.getClass().getSimpleName());
            System.out.println("first app=" + firstAppMethod(ex));
            printAppFrames(ex);
        }

        try {
            wrapCause();
        } catch (IllegalStateException ex) {
            System.out.println("outer=" + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
            Throwable cause = ex.getCause();
            System.out.println("cause=" + cause.getClass().getSimpleName());
            System.out.println("cause first app=" + firstAppMethod(cause));
        }

        try {
            int[] values = {1, 2};
            System.out.println(values[3]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("bounds=" + ex.getClass().getSimpleName());
            System.out.println("bounds first app=" + firstAppMethod(ex));
        }

        System.out.println("recovered=true");
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 StackTraceReadingDemo.java
java -cp . StackTraceReadingDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\StackTraceReadingDemo.java
java -cp . StackTraceReadingDemo
~~~

Không cần Maven/Gradle, thư viện ngoài JDK hoặc preview features. Chương trình **bắt các lỗi có chủ đích**, tránh in stack trace thô phụ thuộc số dòng/version và in thông tin đã chuẩn hóa để đối chiếu.

### Exact expected stdout

~~~text
caught=NumberFormatException
first app=parsePart
at=parsePart
at=calculate
at=load
at=main
outer=IllegalStateException:invalid setting
cause=NumberFormatException
cause first app=wrapCause
bounds=ArrayIndexOutOfBoundsException
bounds first app=main
recovered=true
~~~

**Giải thích:**

1. `Integer.parseInt("bad")` ném `NumberFormatException`. Trong trace của nó, các frame do chương trình tự định nghĩa lần lượt là `parsePart`, `calculate`, `load`, `main`.
2. `wrapCause()` bắt lỗi chuyển chuỗi sang số, bọc bằng `IllegalStateException("invalid setting", ex)`. Ta đọc được kiểu của ngoại lệ ngoài và **nguyên nhân** qua `getCause()`.
3. `values[3]` vượt giới hạn mảng hai phần tử nên `ArrayIndexOutOfBoundsException` xuất hiện trực tiếp trong `main`.
4. Vì cả ba lỗi đều được bắt, cuối cùng chương trình in `recovered=true`.

Để xem trace thật trong lúc học, có thể tạm thêm `ex.printStackTrace();` trong từng khối `catch` rồi quan sát **stderr**; tuy nhiên khi làm vậy, output sẽ có thêm dòng chứa tên file, số dòng, frame JDK và có thể khác giữa môi trường.

## 10. Quy trình chẩn đoán theo một stack trace thật

1. **Giữ nguyên toàn bộ lỗi** gồm kiểu, thông điệp, dòng `at` và các phần `Caused by`. Nếu có nhiều lỗi liên tiếp, xác định lỗi ứng với lần chạy/thời điểm nào.
2. **Đọc loại lỗi**: `NullPointerException` là truy cập qua tham chiếu null; `ArrayIndexOutOfBoundsException` là chỉ số ngoài phạm vi; `NumberFormatException` là chuyển chuỗi sang số không hợp lệ. Đây là manh mối, chưa phải lời giải tự động.
3. **Tìm ứng dụng trong frames**: xác định class/package của chính dự án, mở đúng bản file nguồn cùng version với mã đang chạy.
4. **Xem đúng dòng và các giá trị liên quan**: đối số, biến có thể null, độ dài mảng, điều kiện trước đó. Dùng debugger, log an toàn và test tái hiện để kiểm chứng.
5. **Đi ngược các frame gọi** để tìm nơi đầu vào được tạo/chuyển đổi. Đọc phần `Caused by` khi có lỗi được bọc.
6. **Sửa nguyên nhân hợp lý**: xác thực đầu vào, sửa điều kiện chỉ số, giữ invariant, chuyển đổi kiểu đúng hoặc xử lý ngoại lệ tại tầng phù hợp. Đừng chỉ bắt rộng mọi `Exception` rồi bỏ qua.
7. **Chạy lại kiểm thử**: kiểm tra trường hợp gây lỗi và cả các trường hợp hợp lệ; đối chiếu trace/log mới.

Nếu một trace nói lỗi ở `UserService.java:42` nhưng file hiện tại không có dòng tương ứng, cần kiểm tra mã đã biên dịch, mapping, phiên bản triển khai và cờ debug thay vì sửa tùy đoán.

## 11. Một số trường hợp dễ gây hiểu sai

| Tình huống | Cách hiểu/giải quyết |
|---|---|
| Frame đầu thuộc thư viện chuẩn Java | Xem frame ứng dụng gọi vào thư viện và dữ liệu đầu vào |
| Trace có nhiều `Caused by` | Theo chuỗi nguyên nhân và bối cảnh; nguyên nhân sâu nhất thường quan trọng nhưng chưa chắc đủ |
| Có `... 4 more` | Một số frame trùng bị rút gọn, không phải 4 lỗi nữa |
| Có `Suppressed:` | Ngoại lệ phụ được giữ lại, khác với cause |
| Không có số dòng hoặc hiện `Unknown Source` | Kiểm tra thông tin debug, mã chạy, JAR, source tương ứng |
| `catch` chỉ in một câu chung chung | Cần giữ lại exception/cause để có thể điều tra |
| Trace rất dài, qua proxy/lambda/framework | Tìm các frame ứng dụng và đường gọi liên quan; không loại bỏ ngữ cảnh hữu ích |
| Lỗi xuất hiện từ worker thread/future | Trace tại nơi throw và nơi lấy kết quả có thể khác; đọc cause và bối cảnh thread |
| Có `Error` như `StackOverflowError` | Không mặc định đây là ngoại lệ nghiệp vụ có thể phục hồi; xem lỗi logic/tài nguyên |
| Tự sửa số dòng theo file đang mở | Số dòng phải khớp phiên bản nguồn thực sự đã chạy |
| Dùng `System.out` và `System.err` xen kẽ | Thứ tự hiển thị giữa hai stream không luôn được cam kết |
| In token/mật khẩu trong log lỗi | Rò rỉ dữ liệu; che hoặc loại bỏ nội dung nhạy cảm |

**Lưu ý:** lỗi **biên dịch** (ví dụ “cannot find symbol”) không phải runtime exception; nó thường có dạng thông báo `javac` về file, dòng và vị trí lỗi, không có runtime call stack. Đọc đúng loại thông báo trước khi áp dụng quy trình stack trace.

## 12. Bài tập có đáp án

**A.** Với dòng `at com.shop.OrderService.place(OrderService.java:57)`, cần mở file nào và kiểm tra đâu?  
**Đáp án:** mở `OrderService.java` đúng phiên bản đang chạy, xem khoảng **dòng 57** trong phương thức `place`.

**B.** Với `NumberFormatException` ở `Integer.parseInt`, phải chỉ sửa mã JDK không?  
**Đáp án:** **Không**. Tìm frame ứng dụng gọi `parseInt`, kiểm tra chuỗi đầu vào và nơi tạo chuỗi ấy.

**C.** Nếu một ngoại lệ `IllegalStateException` có `Caused by: NumberFormatException`, hai loại đó là hai dòng `at` liên tiếp của một trace giống hệt nhau không?  
**Đáp án:** **Không**. Đó là **chuỗi ngoại lệ có nguyên nhân**, mỗi ngoại lệ có thể mang stack trace riêng.

**D.** Dòng `... 2 more` cho biết có hai exception khác nữa không?  
**Đáp án:** **Không**. Đây là số frame đuôi trùng bị rút gọn khi trình bày nested trace.

**E.** Vì sao một đoạn `catch (Exception ex) { }` rỗng gây khó tìm lỗi?  
**Đáp án:** nó nuốt thông tin kiểu lỗi, thông điệp, vị trí và nguyên nhân; cần xử lý hợp lý hoặc ghi log phù hợp mà không lộ dữ liệu nhạy cảm.

**F.** Trong chương trình ở mục 9, frame ứng dụng đầu tiên của lỗi `NumberFormatException` là phương thức nào?  
**Đáp án:** `parsePart`. Các frame tiếp theo `calculate`, `load`, `main` cho biết chuỗi gọi.

## 13. Checklist và kết luận

- [ ] Biết stack trace mô tả call stack tại thời điểm lỗi/thu thập trace.
- [ ] Đọc được kiểu ngoại lệ và thông điệp ở đầu trace.
- [ ] Phân tích `at Class.method(File.java:line)` và truy về file/dòng đúng version.
- [ ] Biết frame JDK không nhất thiết là nơi cần sửa mã dự án.
- [ ] Đọc thứ tự các frame để hiểu chuỗi phương thức gọi.
- [ ] Nhận diện `Caused by`, `Suppressed:` và ý nghĩa `... N more`.
- [ ] Biết `printStackTrace()` mặc định viết stderr, khác stdout.
- [ ] Dùng được `getStackTrace()`/`StackTraceElement` khi cần xử lý có cấu trúc.
- [ ] Không “nuốt” ngoại lệ hoặc đưa dữ liệu nhạy cảm vào log.
- [ ] Biết số dòng và frame có thể khác giữa bản biên dịch/JDK.
- [ ] Chạy `StackTraceReadingDemo.java` trên JDK 17+, đối chiếu exact stdout.
- [ ] Tái hiện lỗi, xác thực nguyên nhân, sửa đúng chỗ và kiểm thử lại.

**Kết luận:** Đọc stack trace bắt đầu từ **loại lỗi và thông điệp**, sau đó tìm **frame của ứng dụng** gần nơi lỗi nhất, lần theo **chuỗi gọi** và các phần **`Caused by`** để hiểu bối cảnh. Đường dẫn file và số dòng giúp định vị mã, nhưng cần đúng phiên bản đang chạy; mục tiêu là sửa nguyên nhân dữ liệu/logic chứ không đơn thuần che giấu thông báo lỗi.