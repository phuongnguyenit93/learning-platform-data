# Scoped Value, hàm tạo linh hoạt và tệp nguồn gọn: đối chiếu với phiên bản chính thức từ JDK 25

Java 22 giới thiệu nhiều cải tiến qua các vòng preview. Ba nhánh có ảnh hưởng rõ rệt tới cách viết ứng dụng Java hiện đại là **Scoped Values**, **Flexible Constructor Bodies** và **Compact Source Files with Instance Main Methods**. Chúng lần lượt cải thiện cách truyền ngữ cảnh, cách khởi tạo đối tượng kế thừa và cách viết điểm bắt đầu của chương trình nhỏ.

Các ví dụ sử dụng phiên bản API và cú pháp đã hoàn thiện trong JDK 25 trở lên. JDK 22 được dùng làm mốc lịch sử để giải thích quá trình phát triển; mã preview cũ không phải mẫu để đưa thẳng vào ứng dụng hiện tại. Cả ba tính năng đều đã trở thành tính năng chính thức trong JDK 25 và tiếp tục dùng được trong JDK 26 mà không cần bật preview. Một lưu ý riêng là `StructuredTaskScope`, cơ chế thường kết hợp với Scoped Values để truyền binding sang tác vụ con, vẫn là API preview trong JDK 26.

## 1. Ba tính năng giải quyết ba vấn đề khác nhau

| Tính năng | Vấn đề chính | Cách giải quyết |
| --- | --- | --- |
| Scoped Values | Truyền dữ liệu ngữ cảnh qua nhiều tầng lời gọi mà không thêm tham số vào từng phương thức. | Bind một giá trị vào phạm vi thực thi; các phương thức được gọi bên trong có thể đọc giá trị qua một khóa. |
| Flexible Constructor Bodies | Cần kiểm tra dữ liệu, tính đối số hoặc khởi tạo một số field trước khi gọi constructor của lớp cha. | Cho phép một phần câu lệnh xuất hiện trước `super(...)` hoặc `this(...)`, trong giới hạn không truy cập instance đang được tạo. |
| Compact Source Files và Instance Main Methods | Một chương trình nhỏ phải khai báo class, `static`, `public` và tham số `String[]` dù chưa cần những khái niệm đó. | Cho phép viết thành viên ở cấp file và dùng một phương thức `main` đơn giản làm điểm bắt đầu. |

Đây là ba cải tiến độc lập. Scoped Values thuộc thư viện chuẩn; hai tính năng còn lại thay đổi cú pháp và quy tắc ngôn ngữ Java. Không nên xem chúng là một cơ chế thay thế lẫn nhau.

## 2. Hành trình từ preview trong JDK 22 tới tính năng chính thức

Các JEP dưới đây giúp nhận diện đúng tài liệu theo từng phiên bản. Trạng thái cần dùng khi phát triển ứng dụng hiện nay là bản hoàn thiện trong JDK 25.

| Tính năng | JDK 22 | Các vòng tiếp theo | JDK 25 |
| --- | --- | --- | --- |
| Scoped Values | JEP 464, preview lần hai. | JEP 481 trong JDK 23; JEP 487 trong JDK 24. | JEP 506, chính thức. |
| Flexible Constructor Bodies | JEP 447, preview với tên *Statements before super(...)*. | JEP 482 trong JDK 23 cho phép gán field của chính lớp trước lời gọi constructor; JEP 492 trong JDK 24 là preview lần ba. | JEP 513, chính thức. |
| Compact Source Files và Instance Main Methods | JEP 463, preview lần hai với tên *Implicitly Declared Classes and Instance Main Methods*; lần preview đầu là JEP 445 trong JDK 21. | JEP 477 trong JDK 23; JEP 495 trong JDK 24 với tên *Simple Source Files and Instance Main Methods*. | JEP 512, chính thức với tên *Compact Source Files and Instance Main Methods*. |

Một số thay đổi tên gọi phản ánh quá trình hoàn thiện thiết kế. Trong tài liệu hiện tại, hãy dùng tên **Scoped Values**, **Flexible Constructor Bodies**, **Compact Source Files** và **Instance Main Methods**. Những tên như *Statements before super(...)*, *Implicitly Declared Classes* hay *Simple Source Files* chỉ hữu ích khi đọc lịch sử preview.

Từ JDK 25, ba tính năng trong bài không còn là preview. Không cần `--enable-preview` để biên dịch hoặc chạy mã chỉ sử dụng chúng. Nếu chương trình còn dùng một API preview khác, chẳng hạn Structured Concurrency, yêu cầu bật preview của API đó vẫn áp dụng.

## 3. Scoped Values: truyền ngữ cảnh trong một phạm vi có giới hạn

### 3.1. Khi nào cần Scoped Values?

Tham số phương thức vẫn là cách truyền dữ liệu tường minh và nên được ưu tiên khi một phương thức thực sự cần nhận dữ liệu đó. Tuy nhiên, một request có thể đi qua nhiều lớp controller, service, repository và callback. Nếu chỉ một vài phương thức ở đầu và cuối chuỗi gọi cần `requestId`, việc thêm tham số vào mọi phương thức trung gian khiến chữ ký phương thức phình to.

`ThreadLocal` từng được dùng để lưu ngữ cảnh theo thread. Cách này có vòng đời gắn với thread và mã có tham chiếu tới biến có thể thay đổi giá trị. Khi thread được tái sử dụng, ứng dụng phải quản lý việc xóa giá trị để tránh mang ngữ cảnh của tác vụ trước sang tác vụ sau.

`ScopedValue<T>` cung cấp một khóa để bind dữ liệu trong một phạm vi thực thi. Caller thiết lập binding trước khi gọi tác vụ; các phương thức được gọi trực tiếp hoặc gián tiếp bên trong có thể đọc giá trị qua khóa đó. Khi tác vụ kết thúc bình thường hoặc ném exception, binding được khôi phục về trạng thái trước đó.

### 3.2. API chuẩn trong JDK 25

`ScopedValue` thuộc package `java.lang`, vì vậy không cần import riêng. Các thành phần thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `ScopedValue.newInstance()` | Tạo khóa mới, ban đầu chưa được bind. |
| `ScopedValue.where(key, value)` | Tạo `ScopedValue.Carrier` chứa một binding. |
| `Carrier.where(key, value)` | Trả về carrier mới với binding được bổ sung hoặc thay thế. |
| `Carrier.run(Runnable)` | Chạy tác vụ không trả về kết quả trong phạm vi binding. |
| `Carrier.call(ScopedValue.CallableOp)` | Chạy tác vụ có trả về kết quả trong phạm vi binding. |
| `ScopedValue.get()` | Đọc giá trị đang bind trong thread hiện tại; ném `NoSuchElementException` nếu chưa bind. |
| `ScopedValue.isBound()` và `orElse(value)` | Kiểm tra binding hoặc đọc giá trị với giá trị mặc định. |

`Carrier` là immutable và thread-safe. Gọi `where` trên carrier trả về một carrier mới, không sửa carrier cũ.

### 3.3. Ví dụ: truyền request context

```java
public final class RequestContextExample {
    private static final ScopedValue<RequestContext> CURRENT_REQUEST =
            ScopedValue.newInstance();

    record RequestContext(String requestId, String tenantId) {}

    public static void main(String[] args) {
        var context = new RequestContext("req-42", "tenant-a");

        ScopedValue.where(CURRENT_REQUEST, context)
                .run(RequestContextExample::handleRequest);
    }

    private static void handleRequest() {
        loadOrder();
    }

    private static void loadOrder() {
        RequestContext context = CURRENT_REQUEST.get();
        System.out.printf("request=%s, tenant=%s%n",
                context.requestId(), context.tenantId());
    }
}
```

`handleRequest` không cần nhận `RequestContext` làm tham số, nhưng `loadOrder` vẫn đọc được context vì nó chạy trong phạm vi binding. Ví dụ dùng một `record` để gom các trường liên quan vào một giá trị bất biến.

Có thể bind nhiều khóa trong cùng phạm vi:

```java
public final class MultiContextExample {
    private static final ScopedValue<String> USER_ID = ScopedValue.newInstance();
    private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(USER_ID, "user-17")
                .where(REQUEST_ID, "req-42")
                .run(MultiContextExample::processRequest);
    }

    private static void processRequest() {
        System.out.printf("user=%s, request=%s%n", USER_ID.get(), REQUEST_ID.get());
    }
}
```

Khi có nhiều trường luôn đi cùng nhau, thường nên gom chúng vào một `record` rồi bind một Scoped Value. API được thiết kế để dùng với số lượng khóa tương đối nhỏ.

### 3.4. Binding lồng nhau và giới hạn đa luồng

Một phạm vi bên trong có thể bind lại cùng khóa với giá trị khác. Khi phạm vi bên trong kết thúc, giá trị của phạm vi bên ngoài được khôi phục:

```java
private static final ScopedValue<String> TENANT = ScopedValue.newInstance();

static void runForTenants() {
    ScopedValue.where(TENANT, "tenant-A").run(() -> {
        printTenant(); // tenant-A

        ScopedValue.where(TENANT, "tenant-B")
                .run(() -> printTenant()); // tenant-B

        printTenant(); // tenant-A được khôi phục
    });
}

private static void printTenant() {
    System.out.println(TENANT.get());
}
```

Binding là theo từng thread. Hai thread có thể dùng cùng khóa nhưng nhận các giá trị khác nhau. Scoped Values cũng hỗ trợ kế thừa binding vào các thread con được tạo bằng `StructuredTaskScope.fork`; scope capture binding khi được mở. Cơ chế này chỉ áp dụng cho cấu trúc tác vụ được hỗ trợ, không có nghĩa binding tự động xuất hiện trong mọi thread hoặc mọi tác vụ gửi vào executor.

Trong JDK 26, `StructuredTaskScope` vẫn là API preview theo JEP 525. Do đó, có thể dùng riêng `ScopedValue` như API chính thức mà không bật preview, nhưng đoạn mã sử dụng `StructuredTaskScope` vẫn phải tuân theo yêu cầu preview của Structured Concurrency. Giá trị được chia sẻ giữa các thread nên là immutable; nếu dùng đối tượng mutable, mọi truy cập cần được đồng bộ phù hợp.

### 3.5. Scoped Values và ThreadLocal

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Vòng đời | Giới hạn bởi `run` hoặc `call`; tự khôi phục khi thoát phạm vi. | Gắn với thread; ứng dụng phải quản lý vòng đời, thường gọi `remove()` khi hoàn tất tác vụ. |
| Hướng truyền | Phù hợp truyền dữ liệu một chiều từ caller xuống callee. | Có thể đọc và thay đổi từ bất kỳ mã nào có tham chiếu. |
| Binding lồng nhau | Hỗ trợ rebinding và khôi phục giá trị cũ theo phạm vi. | Có thể thay đổi bằng `set()`; không có quy tắc khôi phục theo phạm vi tương đương. |
| Kế thừa | Hỗ trợ trong cấu trúc đa luồng có giới hạn như `StructuredTaskScope`. | `ThreadLocal` thông thường không tự kế thừa; `InheritableThreadLocal` có cơ chế riêng. |
| Phù hợp | Request context, tenant, principal, locale hoặc dữ liệu tracing ít thay đổi. | Trạng thái thực sự thuộc về thread và cần thay đổi theo vòng đời thread. |

Scoped Values không thay thế mọi trường hợp dùng `ThreadLocal`. Chọn Scoped Values khi mục tiêu là truyền context một chiều và có ranh giới thực thi rõ ràng; giữ `ThreadLocal` khi trạng thái mutable thực sự thuộc về thread và vòng đời của nó được quản lý đúng.

## 4. Flexible Constructor Bodies: chuẩn bị trước khi gọi constructor cha

### 4.1. Vấn đề của quy tắc cũ

Trong quy tắc constructor truyền thống, lời gọi `super(...)` hoặc `this(...)` phải đứng đầu phần thân constructor (nếu không viết lời gọi tường minh, compiler chèn lời gọi `super()` thích hợp). Điều này gây khó khăn khi lớp con cần kiểm tra đối số hoặc chuẩn bị dữ liệu trước khi gọi constructor lớp cha.

JEP 447 đưa vào preview trong JDK 22 khả năng đặt một số câu lệnh trước `super(...)`. JDK 23 mở rộng tính năng để cho phép gán field của chính lớp trước lời gọi constructor. JDK 24 tiếp tục preview và JDK 25 hoàn thiện thiết kế bằng JEP 513.

### 4.2. Prologue, early construction context và epilogue

Phần câu lệnh trước lời gọi constructor được gọi là *prologue*; phần sau lời gọi là *epilogue*. Các câu lệnh trong prologue và các đối số của lời gọi constructor thuộc *early construction context*.

Early construction context không được đọc hoặc sử dụng instance đang được tạo như một giá trị. Cụ thể, không được đọc field instance, dùng `this` để gọi phương thức hay truyền instance vào biểu thức, hoặc truy cập thành viên của `super`. Riêng phép gán trực tiếp field của chính lớp đang được tạo được cho phép. Constructor có thể:

- Kiểm tra tham số và ném exception nếu dữ liệu không hợp lệ.
- Khai báo biến cục bộ và tính toán đối số truyền cho `super(...)` hoặc `this(...)`.
- Gán field của chính lớp đang được tạo bằng phép gán, trước lời gọi `super(...)`.

Điểm cuối là phần mở rộng xuất hiện từ JEP 482 trong JDK 23. Dù có thể gán field trước `super(...)`, không được đọc field đó trong early construction context.

### 4.3. Ví dụ: kiểm tra và chuẩn hóa đối số cho lớp cha

```java
class TextBase {
    private final String text;

    TextBase(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

class NormalizedText extends TextBase {
    NormalizedText(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }

        super(raw.strip());
    }
}
```

Constructor của `NormalizedText` kiểm tra và chuẩn hóa dữ liệu đầu vào trước khi gọi constructor của `TextBase`. Các thao tác này chỉ dùng tham số `raw`, chưa đọc instance đang được tạo.

### 4.4. Ví dụ: gán field trước `super(...)`

Một lý do thực tế để gán field sớm là constructor lớp cha có thể gọi một phương thức được override ở lớp con. Nếu field của lớp con chưa có giá trị, phương thức override có thể nhìn thấy giá trị mặc định như `0`, `false` hoặc `null`.

```java
class Base {
    Base() {
        report();
    }

    void report() {
        System.out.println("Base");
    }
}

class Child extends Base {
    private final int id;

    Child(int id) {
        this.id = id;
        super();
    }

    @Override
    void report() {
        System.out.println("Child id=" + id);
    }
}
```

Trong ví dụ, `id` được gán trước khi constructor `Base` chạy. Khi `Base` gọi `report()`, phiên bản override trong `Child` đọc được giá trị đã gán. Ví dụ minh họa khả năng của ngôn ngữ; trong thiết kế thực tế vẫn nên tránh gọi phương thức có thể override từ constructor lớp cha vì đối tượng con có thể còn chưa hoàn tất quá trình khởi tạo.

### 4.5. Constructor ủy quyền bằng `this(...)` và record

Flexible Constructor Bodies cũng hữu ích cho constructor ủy quyền. Một constructor có thể phân tích, kiểm tra tham số rồi gọi constructor khác bằng `this(...)`. Với record, constructor không canonical phải ủy quyền cho canonical constructor:

```java
record Point(int x, int y) {
    Point(String coordinates) {
        String[] parts = coordinates.split(",");
        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected x,y");
        }

        int parsedX = Integer.parseInt(parts[0].trim());
        int parsedY = Integer.parseInt(parts[1].trim());
        this(parsedX, parsedY);
    }
}
```

Phần prologue chỉ xử lý dữ liệu đầu vào và biến cục bộ. Lời gọi `this(parsedX, parsedY)` chuyển việc khởi tạo thành phần record cho canonical constructor.

## 5. Compact Source Files và Instance Main Methods: viết chương trình nhỏ gọn

### 5.1. Từ class tường minh đến class được khai báo ngầm

Một chương trình Java truyền thống thường bắt đầu như sau:

```java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
```

Với chương trình một file rất nhỏ, khai báo class, `public`, `static` và `String[] args` có thể làm người mới phải học nhiều khái niệm trước khi viết được câu lệnh đầu tiên. JEP 512 cho phép viết các field và method ở cấp file mà không đặt chúng trong một class tường minh. Compiler tạo một class top-level ngầm định chứa các thành viên đó; file như vậy được gọi là *compact source file*.

### 5.2. Ví dụ theo cú pháp chính thức từ JDK 25

Lưu nội dung sau trong file `Hello.java`:

```java
String greeting = "Java 25";

void main() {
    IO.println("Hello, " + greeting);
}
```

Chạy trực tiếp ở chế độ source-file:

```shell
java Hello.java
```

Hoặc biên dịch rồi chạy class đã sinh:

```shell
javac Hello.java
java Hello
```

`greeting` và `main()` được xem là thành viên của class được khai báo ngầm. Vì `main()` là instance method, launcher tạo instance bằng constructor mặc định không tham số rồi gọi phương thức đó.

### 5.3. Quy tắc của class được khai báo ngầm

Class được khai báo ngầm trong compact source file có các đặc điểm quan trọng:

- Là class top-level `final` trong unnamed package và có tên do môi trường host xác định.
- Kế thừa `Object`, không trực tiếp triển khai interface nào.
- Có constructor mặc định không tham số; không khai báo constructor riêng trong compact source file.
- Chứa các field, method, class thành viên và interface thành viên được khai báo ở cấp file.
- Phải có một `main` method mà launcher có thể gọi.

Class này không thể được tham chiếu bằng tên trong mã nguồn. Vì vậy, compact source file phù hợp với chương trình độc lập, ví dụ học tập, thử nghiệm hoặc tiện ích một file; nó không phải cách khai báo một kiểu public để các package khác phụ thuộc vào.

### 5.4. Instance Main Methods và cách launcher chọn điểm bắt đầu

Từ JDK 25, một `main` method có thể là static hoặc instance, có thể nhận `String[]` hoặc không nhận tham số, miễn là có kiểu trả về `void` và mức truy cập được launcher chấp nhận (`public`, `protected` hoặc package access). `private` không phải mức truy cập hợp lệ cho candidate main method.

Launcher chọn phương thức theo thứ tự:

1. Nếu có candidate `main(String[] args)`, launcher chọn phương thức đó.
2. Nếu không có, launcher chọn candidate `main()` không tham số.
3. Nếu phương thức được chọn là `static`, launcher gọi trực tiếp. Nếu là instance method, launcher tạo instance bằng constructor không tham số có thể truy cập rồi gọi phương thức trên instance đó.

Ví dụ compact source file có thể nhận đối số dòng lệnh mà không cần `static`:

```java
void main(String[] args) {
    if (args.length == 0) {
        IO.println("Hello, Java");
    } else {
        IO.println("Hello, " + args[0]);
    }
}
```

### 5.5. Import tự động và `java.lang.IO` trong JDK 25

Compact source file tự động import các public top-level class và interface thuộc những package được export bởi module `java.base`. Vì vậy, các kiểu như `List`, `Map` và `Stream` có thể được dùng mà không cần import riêng trong compact source file. Quy tắc này không có nghĩa là mọi thư viện hoặc mọi module đều được import tự động.

JDK 25 cũng có `java.lang.IO` với các phương thức console cơ bản:

| Phương thức | Chức năng |
| --- | --- |
| `IO.print(Object)` | In biểu diễn của đối tượng, không thêm ký tự xuống dòng. |
| `IO.println(Object)` | In biểu diễn của đối tượng và xuống dòng. |
| `IO.println()` | In một dòng trống. |
| `IO.readln()` | Đọc một dòng từ standard input. |
| `IO.readln(String prompt)` | In lời nhắc rồi đọc một dòng. |

Trong bản chính thức JDK 25, `IO` nằm trong `java.lang` và tên lớp phải được ghi khi gọi các phương thức static, ví dụ `IO.println(...)`. Các phương thức static này không được tự động static import. Đây là điểm cần chú ý khi đọc ví dụ preview JDK 23–24: các bản preview trước từng dùng `java.io.IO` và cơ chế static import tự động; không sao chép cách viết `println(...)` không có tiền tố vào mã JDK 25.

`java.lang.IO` cũng có thể dùng trong source file thông thường có class tường minh; nó không chỉ dành cho compact source file. Với chương trình cần I/O phức tạp, định dạng nâng cao hoặc quản lý luồng dữ liệu, những API như `System.out`, `System.in`, `Console`, `Scanner` và các lớp I/O khác vẫn có vai trò riêng.

## 6. Đối chiếu cách dùng trong ứng dụng hiện đại

| Nhu cầu | Nên cân nhắc | Lý do |
| --- | --- | --- |
| Truyền request ID, tenant hoặc principal qua nhiều tầng gọi | Scoped Values | Caller bind tại ranh giới tác vụ; callee đọc trong phạm vi đó mà không phải nhận thêm tham số trung gian. |
| Kiểm tra dữ liệu hoặc tính đối số trước constructor lớp cha | Flexible Constructor Bodies | Prologue cho phép chuẩn bị dữ liệu trước `super(...)` hoặc `this(...)` trong giới hạn an toàn. |
| Gán một số field trước khi constructor cha chạy | Flexible Constructor Bodies | Hữu ích khi constructor cha gọi phương thức override và phương thức đó cần field đã được gán. |
| Viết chương trình minh họa, script Java một file hoặc bài tập nhập môn | Compact Source Files và Instance Main Methods | Có thể bắt đầu với method và biến, rồi bổ sung class tường minh khi chương trình lớn lên. |
| Xây dựng API, thư viện hoặc ứng dụng nhiều package | Class và package tường minh | Kiểm soát tên kiểu, khả năng truy cập, namespace, constructor và ranh giới module rõ ràng. |

Khi nâng cấp từ ví dụ Java 22, hãy kiểm tra ba điều: mã Scoped Values dùng API `java.lang.ScopedValue` đã hoàn thiện; constructor chỉ dùng những thao tác được phép trong early construction context; compact source file dùng quy tắc JDK 25 với `java.lang.IO` và tiền tố `IO.` cho lời gọi static. Không cần bật preview cho ba tính năng đã hoàn thiện này.

## 7. Tài liệu tham khảo

**Scoped Values**

- [JEP 464 — Scoped Values (Second Preview)](https://openjdk.org/jeps/464)
- [JEP 481 — Scoped Values (Third Preview)](https://openjdk.org/jeps/481)
- [JEP 487 — Scoped Values (Fourth Preview)](https://openjdk.org/jeps/487)
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506)
- [ScopedValue, Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html)
- [ScopedValue.Carrier, Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html)

**Flexible Constructor Bodies**

- [JEP 447 — Statements before super(...)](https://openjdk.org/jeps/447)
- [JEP 482 — Flexible Constructor Bodies (Second Preview)](https://openjdk.org/jeps/482)
- [JEP 492 — Flexible Constructor Bodies (Third Preview)](https://openjdk.org/jeps/492)
- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513)
- [Flexible Constructor Bodies, Java SE 25 Language Updates](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html)

**Compact Source Files và Instance Main Methods**

- [JEP 445 — Unnamed Classes and Instance Main Methods (Preview)](https://openjdk.org/jeps/445)
- [JEP 463 — Implicitly Declared Classes and Instance Main Methods (Second Preview)](https://openjdk.org/jeps/463)
- [JEP 477 — Implicitly Declared Classes and Instance Main Methods (Third Preview)](https://openjdk.org/jeps/477)
- [JEP 495 — Simple Source Files and Instance Main Methods (Fourth Preview)](https://openjdk.org/jeps/495)
- [JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [Compact Source Files and Instance Main Methods, Java SE 25 Language Updates](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html)
- [java.lang.IO, Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IO.html)
- [Structured Concurrency, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html) — trạng thái preview của API được dùng để truyền Scoped Value sang tác vụ con.
