# MatchException và thay đổi hierarchy lúc chạy

Trong **Java 21**, một `switch` có thể được trình biên dịch công nhận là **exhaustive** (đủ các trường hợp) nhờ thông tin về một `sealed` hierarchy hoặc các hằng `enum`. Nhưng nếu **mã chứa `switch` không được biên dịch lại**, trong khi thư viện định nghĩa hierarchy đã đổi và được triển khai ở runtime, chương trình có thể gặp một giá trị **không khớp bất kỳ case nào**. Lúc đó, Java có thể ném **`java.lang.MatchException`**.

Đây không phải mâu thuẫn: compiler đã kiểm tra tính đầy đủ dựa trên **tập kiểu nhìn thấy ở thời điểm biên dịch**. JVM lại thực thi dựa trên **những class thực sự được nạp khi chạy**. Khi hai tập thông tin lệch nhau do *separate compilation* và nâng cấp thư viện không đồng bộ, tính exhaustive từng được chứng minh có thể không còn đúng cho dữ liệu runtime.

Nội dung trọng tâm của bài:

- Phân biệt **exhaustiveness ở compile-time** với việc chọn nhánh **ở runtime**.
- Biết khi nào Java 21 ném `MatchException`, khi nào là `NullPointerException` hoặc lỗi liên kết class khác.
- Tái hiện lỗi bằng cách **biên dịch một `switch` cũ**, sau đó mở rộng `sealed` hierarchy mà **không biên dịch lại `switch`**.
- Xử lý đúng trong hệ thống có nhiều module, JAR hoặc phiên bản triển khai độc lập.

## 1. `MatchException` là gì?

`java.lang.MatchException` xuất hiện dưới dạng API chính thức từ **Java 21**. Đây là một **unchecked exception**, cụ thể là class `final` kế thừa `RuntimeException`.

Nó biểu thị việc **pattern matching thất bại theo cách không mong đợi**. Một trường hợp điển hình: cấu trúc `switch` được coi là exhaustive tại compile-time, nhưng không có case nào áp dụng cho một giá trị xuất hiện ở runtime.

Ví dụ ý tưởng:

```java
// Thời điểm A: compiler chỉ thấy First và Second.
switch (event) {
    case First first -> handleFirst(first);
    case Second second -> handleSecond(second);
}

// Thời điểm B: runtime có thêm Third, nhưng switch cũ vẫn được sử dụng.
// Nếu event thực sự là Third, không case nào khớp => MatchException.
```

Đây là **mã minh họa**, không phải chương trình độc lập. Điều kiện cần hiểu là `First`, `Second`, `Third` đều là những subtype phù hợp của một hierarchy cho phép thêm subtype `Third` ở phiên bản mới; `switch` chỉ được biên dịch theo phiên bản cũ.

**Không phải tất cả `MatchException` đều do thay đổi hierarchy.** Java 21 còn có các trường hợp liên quan tới **nested record patterns** và `null` trong component, hoặc lỗi khi gọi record accessor trong quá trình deconstruction. Tuy nhiên, thay đổi hierarchy ở runtime là tình huống rất quan trọng khi nâng cấp thư viện và triển khai nhiều module.

## 2. Bản chất: hai thời điểm có hai góc nhìn khác nhau

Hãy hình dung một ứng dụng có hai phần:

- **Library** chứa `sealed interface Event` và các class hiện thực được cấp phép.
- **Client** chứa `switch` phân nhánh theo từng subtype của `Event`.

Tại **lần biên dịch đầu**, library v1 định nghĩa:

```text
Event (sealed)
├── Start (final)
└── Stop  (final)
```

Client v1 dùng:

```java
return switch (event) {
    case Start s -> "start";
    case Stop s -> "stop";
};
```

Vì `Event` chỉ cho phép `Start` và `Stop`, trình biên dịch Java 21 có thể chứng minh `switch expression` trên `Event` là **exhaustive với mọi đối tượng Event khác null**. Không cần `default`.

Sau đó thư viện v2 thêm subtype:

```text
Event (sealed)
├── Start (final)
├── Stop  (final)
└── Pause (final)   <-- mới
```

Nếu client **vẫn chạy bytecode đã biên dịch từ v1**:

- Khi nhận `Start` hoặc `Stop`, các case cũ vẫn có thể xử lý bình thường.
- Khi nhận `Pause`, không có case nào trong bytecode client dành cho subtype mới.
- Nếu việc nạp class và các liên kết khác đều hợp lệ, đường đi “không case nào khớp” có thể kết thúc bằng **`MatchException`**.

Như vậy, `MatchException` có thể xuất hiện **mặc dù chương trình gốc đã biên dịch thành công và vượt kiểm tra exhaustiveness**. Nó là dấu hiệu cho thấy một giả định mà compiler từng chấp nhận không còn phản ánh đúng runtime.

## 3. Demo đầy đủ: biên dịch riêng library và client

Đây là cách tái hiện bằng **JDK 21**, không cần `--enable-preview`. Thực hiện trong **một thư mục thử nghiệm riêng**, không làm trên thư viện đang phục vụ production.

### Bước 1 — Tạo phiên bản v1 của hierarchy

Tệp **`Event.java`**:

```java
public sealed interface Event permits Start, Stop {
    static Event sample() {
        return new Start();
    }
}
```

Tệp **`Start.java`**:

```java
public final class Start implements Event {}
```

Tệp **`Stop.java`**:

```java
public final class Stop implements Event {}
```

`sealed` giới hạn subtype trực tiếp mà `Event` cho phép. Các implementor trực tiếp `Start`, `Stop` được khai báo `final`, nên không thể sinh thêm subtype qua chúng.

### Bước 2 — Tạo client chỉ biết v1

Tệp **`Client.java`**:

```java
public class Client {
    static String describe(Event event) {
        return switch (event) {
            case Start ignored -> "start";
            case Stop ignored -> "stop";
        };
    }

    public static void main(String[] args) {
        try {
            System.out.println(describe(Event.sample()));
        } catch (MatchException unexpected) {
            System.out.println("MatchException");
        }
    }
}
```

Ở đây `Client.describe` là **switch expression exhaustive**, vì compiler nhìn thấy `Event` chỉ cho phép `Start` và `Stop`.

Khối `catch` có chủ đích **chỉ để demo cho stdout ổn định**. Trong ứng dụng thật, không nên dùng `catch (MatchException)` làm nhánh nghiệp vụ thông thường để thay thế việc cập nhật hierarchy và handler.

Biên dịch cả library v1 lẫn client vào thư mục `out`:

```bash
javac --release 21 -d out Event.java Start.java Stop.java Client.java
java -cp out Client
```

Kết quả lần chạy v1:

```text
start
```

Ở thời điểm này, `out/Client.class` là bytecode được tạo **theo thông tin Event v1**.

### Bước 3 — Thay đổi hierarchy thành v2

**Thay toàn bộ nội dung** `Event.java` bằng phiên bản v2:

```java
public sealed interface Event permits Start, Stop, Pause {
    static Event sample() {
        return new Pause();
    }
}
```

**Thêm tệp mới** `Pause.java`:

```java
public final class Pause implements Event {}
```

Giữ nguyên các tệp `Start.java`, `Stop.java`, **và giữ nguyên `Client.java`**.

Điểm quyết định: **chỉ biên dịch lại library**, không đưa `Client.java` vào lệnh `javac` tiếp theo, cũng không xóa `out/Client.class`:

```bash
javac --release 21 -cp out -d out Event.java Start.java Stop.java Pause.java
java -cp out Client
```

Kết quả lần chạy với **client cũ + library v2**:

```text
MatchException
```

Vì `Event.sample()` v2 trả `Pause`, `Client.describe` được biên dịch ở v1 gặp subtype mà nó không có nhánh xử lý. `MatchException` bị bắt trong `main` và in đúng một dòng, nên không có stack trace trong stdout của demo này. Nếu bỏ `catch`, chương trình sẽ kết thúc với exception chưa xử lý và thông tin stack trace do JVM in ra luồng lỗi.

Đây là minh họa **separate compilation**: nhiều file/class được biên dịch ở các thời điểm khác nhau rồi được lắp ghép thành một ứng dụng chạy. **Không được xóa và biên dịch lại toàn bộ thư mục `out` ở bước này** nếu mục tiêu là tái hiện lỗi; khi đó compiler sẽ phát hiện thiếu case của `Pause` trước khi chạy.

### Bước 4 — Sửa client và biên dịch lại

Trong `Client.describe`, cập nhật `switch`:

```java
static String describe(Event event) {
    return switch (event) {
        case Start ignored -> "start";
        case Stop ignored -> "stop";
        case Pause ignored -> "pause";
    };
}
```

Đây là method thay thế trong `Client.java`, không phải tệp độc lập. Sau đó:

```bash
javac --release 21 -cp out -d out Client.java
java -cp out Client
```

Kết quả:

```text
pause
```

Nếu ở v2 bạn **biên dịch lại client nhưng chưa thêm case `Pause`**, compiler sẽ báo `switch expression` không exhaustive. Đó là phản hồi **đáng mong muốn**: lỗi thiết kế được phát hiện lúc build thay vì chờ runtime.

## 4. Vì sao thay đổi `permits` có thể gây lỗi dù class cũ vẫn tồn tại?

Với `sealed` interface/class, danh sách `permits` định nghĩa những kiểu được phép trực tiếp triển khai/kế thừa. Compiler dùng thông tin này trong kiểm tra exhaustiveness.

Thêm `Pause` không nhất thiết khiến các class `Start` hoặc `Stop` biến mất hoặc khiến việc nạp `Event` v2 bị lỗi. Ứng dụng có thể khởi động và hoạt động bình thường trong nhiều tình huống. **Chỉ khi một instance `Pause` chạm tới `switch` cũ**, vấn đề mới lộ diện dưới dạng thiếu nhánh.

Điều này khác với các thay đổi làm class không còn liên kết hợp lệ, ví dụ xóa class hoặc thay đổi hierarchy khiến một class cũ không còn được phép triển khai sealed type. Khi đó JVM có thể phát sinh **`NoClassDefFoundError`, `IncompatibleClassChangeError` hoặc lỗi liên kết phù hợp khác** trước khi tới `switch`. Không nên gộp tất cả lỗi nâng cấp thư viện thành `MatchException`.

Sự khác biệt quan trọng là **`MatchException` phản ánh thất bại lựa chọn pattern của một cấu trúc đáng lẽ exhaustive**, không phải thông báo chung “mọi thay đổi binary đều gây ra exception này”.

## 5. Với enum cũng có thể xảy ra điều tương tự

Một `switch expression` trên enum có thể exhaustive khi liệt kê mọi constant mà compiler biết:

```java
enum Mode { READ, WRITE }

static String modeName(Mode mode) {
    return switch (mode) {
        case READ -> "read";
        case WRITE -> "write";
    };
}
```

Đây là đoạn minh họa đặt trong một class. Nếu một phiên bản mới của enum bổ sung `ARCHIVE`, nhưng class chứa `modeName` **không được biên dịch lại** và runtime truyền `Mode.ARCHIVE`, `switch expression` cũ có thể ném `MatchException`.

Tại sao? Compiler của phiên bản cũ xác nhận `READ` và `WRITE` là đủ. Phiên bản mới có thêm một giá trị mà code cũ chưa biết.

Lưu ý hai tình huống:

- **Switch expression exhaustive theo enum v1**: có cơ chế bảo vệ khi runtime gặp constant mới không được nhận diện.
- **Traditional switch statement không bắt buộc exhaustive**: một statement chỉ xử lý vài constant có thể kết thúc bình thường khi gặp constant không có nhãn phù hợp. Không phải mọi cú pháp `switch` trên enum đều có cùng kết quả.

Vì vậy, trong bài toán nâng cấp enum, cần kiểm tra **dạng switch** và **mã đã thực sự được biên dịch lại chưa** chứ không chỉ nhìn vào tên enum.

## 6. `switch statement` có pattern cũng bị ảnh hưởng

Java 21 yêu cầu **enhanced switch statement** exhaustive, trong đó có các statement dùng pattern label:

```java
static void consume(Event event) {
    switch (event) {
        case Start start -> System.out.println("start");
        case Stop stop -> System.out.println("stop");
    }
}
```

Đây là method được **biên dịch với Event v1** trong phần demo; không phải một tệp hoàn chỉnh. Nếu chạy đúng bytecode cũ với `Event` v2 và gặp `Pause`, một enhanced switch statement không có case phù hợp có thể ném `MatchException`, tương tự switch expression.

Ngược lại, ví dụ traditional switch statement sau vẫn hợp lệ dù không đầy đủ:

```java
static void oldStyle(int code) {
    switch (code) {
        case 1 -> System.out.println("one");
    }
}
```

Gọi `oldStyle(2)` đơn giản là không thực hiện nhánh nào; trường hợp này **không tự sinh `MatchException`**. Đây là lý do cần phân biệt yêu cầu exhaustive của enhanced switch statement với traditional switch statement.

## 7. `null`: NPE ở selector khác với MatchException do hierarchy đổi

Đối với selector tham chiếu, khi **chính giá trị selector là `null`** và không có nhãn `case null` áp dụng, Java 21 ném **`NullPointerException`**, kể cả khi các nhánh được đánh giá exhaustive đối với những subtype không null.

Ví dụ, với `Event`:

```java
static String nullable(Event event) {
    return switch (event) {
        case null -> "missing";
        case Start ignored -> "start";
        case Stop ignored -> "stop";
    };
}
```

Đây là ví dụ theo **Event v1**, đã xử lý `null` tường minh. Nếu bỏ `case null` và truyền `null`, `NullPointerException` sẽ xảy ra; không nên gọi tình huống ấy là `MatchException` do có subtype mới.

Một nhầm lẫn khác: **`default` không tự bắt `null`** trong pattern switch. Nếu muốn cùng xử lý `null` và các giá trị dự phòng, có thể dùng cấu trúc đặc biệt `case null, default -> ...` khi phù hợp.

Phân biệt thêm: với **nested record pattern**, đôi khi **selector ngoài không null** nhưng **component bên trong null**. Trong một số switch được compiler xem là exhaustive nhờ pattern lồng nhau, trường hợp component `null` có thể dẫn tới `MatchException`. Điều đó khác hẳn `switch(null)` không có nhánh null, vốn ném `NullPointerException`.

## 8. Khi không đổi hierarchy mà vẫn có MatchException

Theo API Java 21, `MatchException` không chỉ gắn với separate compilation. Hai nhóm đáng nhớ:

### Null bên trong một nested record pattern

Giả sử `Part` là sealed type chỉ có `One` và `Two`, còn một record `Box` có component `Part`. Hai record pattern `Box(One ...)` và `Box(Two ...)` có thể được compiler đánh giá đủ cho kiểu `Box`, nhưng **`new Box(null)` không khớp cả hai pattern con**.

Chương trình đầy đủ minh họa trên JDK 21 — tạo file **`NestedNullMatchDemo.java`**:

```java
public class NestedNullMatchDemo {
    sealed interface Part permits One, Two {}

    record One() implements Part {}
    record Two() implements Part {}
    record Box(Part part) {}

    static String describe(Box box) {
        return switch (box) {
            case Box(One one) -> "one";
            case Box(Two two) -> "two";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Box(new One())));

        try {
            System.out.println(describe(new Box(null)));
        } catch (MatchException ex) {
            System.out.println("nested-MatchException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 NestedNullMatchDemo.java
java NestedNullMatchDemo
```

Stdout:

```text
one
nested-MatchException
```

Trường hợp này không cần đổi JAR hoặc hierarchy. **`Box` là selector khác null**, nhưng `part` bên trong bằng null và không đáp ứng hai pattern `One`/`Two`.

Nếu yêu cầu nghiệp vụ cho phép component null, hãy kiểm tra/chuẩn hóa trước khi đưa record vào switch, hoặc thiết kế nhánh xử lý phù hợp. Không nhầm `case null` ở cấp ngoài với việc bắt null của **component lồng bên trong**.

### Record accessor ném exception trong quá trình deconstruction

Record pattern phải gọi các accessor để lấy giá trị component. Nếu accessor được gọi ngầm khi match **ném exception**, quá trình pattern matching có thể ném `MatchException` và lưu exception gốc ở `getCause()`. Đây là một lỗi **trong quá trình thực hiện pattern**, không phải thiếu nhánh do thêm subtype.

Vì vậy, khi chẩn đoán, ngoài tên exception, cần xem **stack trace**, **cause** và thời điểm xảy ra. Không được tự động kết luận rằng mọi `MatchException` đều do `sealed permits` thay đổi.

## 9. Default có ngăn lỗi khi thêm subtype không?

Giả sử hành vi thực sự cho phép một nhánh dự phòng:

```java
static String describeWithFallback(Event event) {
    return switch (event) {
        case Start ignored -> "start";
        case Stop ignored -> "stop";
        default -> "unknown event";
    };
}
```

Nếu được biên dịch theo Event v1 rồi nhận `Pause` ở runtime v2, `default` thường sẽ nhận `Pause` và cho ra `"unknown event"`. **Đó là ưu điểm khi API cần tương thích hướng mở**.

Nhưng cách này có cái giá:

- **Compiler không buộc thêm case mới** khi v2 thêm `Pause`, vì `default` đã bao phủ phần còn lại.
- Nếu mọi subtype phải có xử lý riêng (ví dụ sự kiện tài chính/luồng trạng thái bắt buộc), `default` có thể **che giấu nhánh còn thiếu**, biến lỗi cập nhật source thành hành vi fallback không mong muốn.
- Nếu một nhánh mặc định âm thầm bỏ qua dữ liệu, hệ thống có thể mất sự kiện mà không báo lỗi.

Cân nhắc hai chiến lược:

| Bối cảnh | Chính sách phù hợp |
| --- | --- |
| Sealed hierarchy đóng, mọi subtype phải xử lý tường minh | Không thêm `default` chỉ để tắt lỗi exhaustive; biên dịch lại khi hierarchy thay đổi |
| API có chủ đích chấp nhận kiểu mới với hành vi chung | Có thể dùng `default` được thiết kế rõ, kèm logging/metrics nếu cần |
| Runtime selector có thể null | Xử lý `case null` hoặc kiểm tra trước; `default` riêng lẻ không đủ |
| Nested record component có thể null | Có nhánh hoặc validation ở cấp component; không suy từ `case null` cấp ngoài |
| Tình huống yêu cầu phát hiện sai lệch deployment | Bảo đảm đồng bộ phiên bản và kiểm thử thay đổi subtype thay vì nuốt `MatchException` |

Không có đáp án “mọi switch đều phải có default” hay “không bao giờ dùng default”. Việc chọn phụ thuộc hợp đồng API và mong muốn của người bảo trì khi thêm subtype.

## 10. Cách chẩn đoán MatchException ngoài thực tế

Khi gặp stack trace có `java.lang.MatchException`, ưu tiên lần theo bằng chứng:

1. **Xác định vị trí ném lỗi:** stack trace trỏ tới class/method nào có `switch` hoặc record pattern? Kiểm tra cả `getCause()` nếu có.
2. **Xem giá trị gây lỗi:** kiểu runtime thực tế là gì? Nếu là `Pause` trong ví dụ, kiểm tra trong binary client có case tương ứng không. Chỉ log dữ liệu khi phù hợp với chính sách bảo mật.
3. **Kiểm tra class và JAR thực sự được nạp:** library và client có cùng phiên bản mong đợi không? Có hai JAR chứa cùng class trên classpath/module path không?
4. **Đối chiếu hierarchy ở thời điểm build và runtime:** `permits` hoặc danh sách enum constant đã khác chưa? Có module nào triển khai thư viện mới mà giữ client cũ?
5. **Phân biệt lỗi khác:** `NullPointerException` của selector null; `MatchException` do no-match; lỗi linkage do class bị xóa hoặc hierarchy bất hợp lệ; lỗi từ record accessor.
6. **Biên dịch lại phụ thuộc:** nếu hierarchy thay đổi, rebuild client chứa switch để compiler xác định case cần bổ sung.
7. **Thử lại trên build sạch:** kiểm tra bộ class/JAR được triển khai, chạy test với subtype mới và dữ liệu null lồng nhau.
8. **Không chữa bằng catch bao trùm:** chỉ bắt `MatchException` ở ranh giới phù hợp để ghi log hoặc chuyển thành lỗi tầng trên; vẫn phải sửa handler hoặc đồng bộ dependency.

Ví dụ một khối giám sát hợp lệ về mặt cú pháp:

```java
try {
    processEvent(event);
} catch (MatchException ex) {
    System.err.println("Unmatched pattern: " + ex);
    throw ex;
}
```

Đây là đoạn code minh họa bên trong method có `processEvent` và `event` được khai báo. Ném lại exception sau khi log giúp tránh tình trạng ứng dụng **tiếp tục như thể sự kiện đã được xử lý thành công**.

Trong hệ thống production, log nên chứa thông tin định danh phiên bản triển khai/module và loại sự kiện phù hợp, nhưng không tự động in toàn bộ payload nhạy cảm.

## 11. Ngăn ngừa khi phát hành thư viện và ứng dụng

Một số kỹ thuật hữu ích:

- **Rebuild các module phụ thuộc** khi thay đổi sealed hierarchy, thêm enum constant hoặc thay đổi record shape. Không giả định một module không thay đổi source thì chắc chắn không cần compile lại.
- **Đồng bộ release artifacts:** khóa phiên bản dependency nhất quán giữa build, test, deploy; tránh trộn client cũ với library mới theo classpath.
- **Kiểm thử exhaustive branch coverage:** thêm test cho mỗi subtype/enum constant hiện tại. Với sealed hierarchy, một switch không default sẽ hỗ trợ compiler buộc cập nhật khi biên dịch lại.
- **Kiểm thử rolling upgrade:** nếu server và client có thể chạy các phiên bản khác nhau trong một khoảng thời gian, thống nhất hợp đồng backward/forward compatibility và cách nhận kiểu mới.
- **Theo dõi lỗi runtime:** cảnh báo về `MatchException` và lỗi linkage sau deploy, đồng thời giữ đủ thông tin phiên bản để đối chiếu.
- **Không thay đổi binary tùy tiện:** cùng tên class/đường dẫn JAR không bảo đảm giữ nguyên hierarchy; mọi lớp liên quan phải được biên dịch và đóng gói nhất quán.

Đặc biệt, **`javac --release 21` chỉ ràng buộc ngôn ngữ và API Java 21** khi biên dịch. Nó **không** khóa tập subtype hay enum constant của một dependency sẽ được nạp ở runtime. Chính sách dependency và việc rebuild phụ thuộc vẫn cần được quản lý riêng.

## 12. Bảng so sánh những lỗi dễ nhầm

| Tình huống | Kết quả điển hình trong Java 21 | Giải thích |
| --- | --- | --- |
| Enhanced `switch` không exhaustive ngay ở source hiện tại | **Lỗi biên dịch** | Compiler phát hiện còn kiểu/case chưa bao phủ |
| Switch cũ đã compile exhaustive theo sealed v1, runtime gặp subtype mới của sealed v2 | **`MatchException`** khi không case nào khớp | Thay đổi hierarchy giữa thời điểm compile và chạy |
| Switch expression enum v1, runtime nhận enum constant mới | **`MatchException`** nếu không có nhánh phù hợp | Danh sách enum constant khác phiên bản |
| Selector là `null`, không có nhãn `case null` áp dụng | **`NullPointerException`** | Không giống thiếu subtype trong hierarchy |
| Selector ngoài là record khác null, nested component null khiến các pattern con đều không khớp | Có thể là **`MatchException`** | Exhaustiveness được suy theo type pattern nhưng có lỗ hổng do component null |
| Accessor record ném exception trong lúc match | Có thể là **`MatchException`**, cause là exception gốc | Lỗi trong quá trình deconstruction |
| Thư viện đổi/xóa class khiến linkage không hợp lệ | **Lỗi linkage**, tùy tình huống | Có thể thất bại trước khi chạy tới switch |
| Traditional switch statement không exhaustive, gặp giá trị không có case | Có thể **không làm gì** | Không phải enhanced statement bắt buộc exhaustive |

Đừng dựa vào việc `MatchException` là unchecked exception để xem đây là một “nhánh dữ liệu sai kiểu” bình thường. Nó thường phản ánh một giả định thiết kế hoặc deployment bị phá vỡ và đáng được điều tra.

## 13. Bài tập tự kiểm tra

1. Với Event v1 chỉ có `Start`, `Stop`, hãy giải thích vì sao `switch` không `default` trong `Client.describe` vẫn biên dịch.
2. Thêm `Pause` và biên dịch **toàn bộ** source: lỗi xuất hiện ở giai đoạn nào? So sánh với việc chỉ biên dịch library mới và dùng `Client.class` cũ.
3. Nếu thêm `default -> "unknown"` vào `Client.describe` ở v1, runtime nhận `Pause` trong v2 sẽ ra kết quả gì? Điều đó có luôn đúng yêu cầu nghiệp vụ không?
4. Nếu `Event.sample()` trả `null`, exception nào xuất hiện khi `switch` không có `case null`?
5. Tại sao `new Box(null)` trong ví dụ nested record có thể ném `MatchException` dù không có thay đổi thư viện?
6. Vì sao **rebuild sạch** giúp phát hiện một lỗi mà việc thay JAR trong thư mục triển khai không cho thấy ngay?

### Đáp án ngắn

1. Compiler v1 thấy toàn bộ subtype được `Event` cho phép.
2. Rebuild toàn bộ với hierarchy mới làm compiler báo thiếu `Pause`; còn chạy client v1 với library v2 có thể ném `MatchException`.
3. `default` có thể nhận `Pause` và trả `"unknown"`; nhưng dễ che giấu trường hợp thực sự cần handler riêng.
4. `NullPointerException`, vì null ở **selector** chưa được xử lý.
5. Vì null của **component lồng** khiến các record pattern không khớp dù kiểu record ngoài đã khớp.
6. Compiler kiểm tra lại hierarchy mới và mọi nhánh `case` thay vì dựa vào giả định đã đóng băng trong bytecode cũ.

## Kết luận

Trong Java 21, một pattern switch exhaustive **không có nghĩa mọi binary kết hợp trong tương lai đều an toàn**. Compiler chứng minh tính đầy đủ dựa trên hierarchy hiện diện khi build; khi runtime nhận subtype hoặc enum constant mới mà bytecode switch chưa được cập nhật, **`MatchException` có thể xuất hiện**. Trách nhiệm của hệ thống build/deploy là cập nhật những module phụ thuộc, kiểm tra lại các nhánh xử lý và phát hành bộ artifacts tương thích.

Đồng thời, cần phân biệt lỗi do thay đổi hierarchy với `null` ở selector, `null` trong record component và exception từ record accessor. Phân tích đúng nguồn gốc sẽ dẫn đến cách sửa đúng: **thêm case, rebuild, đồng bộ dependency hoặc sửa dữ liệu/pattern**, chứ không chỉ thêm một `catch` rồi bỏ qua.

### Tài liệu tham khảo chính thức

- [Java SE 21 — `MatchException` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html)
- [Java Language Specification 21 — §14.11.3, Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3)
- [Java Language Specification 21 — §14.11.1.1, Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
