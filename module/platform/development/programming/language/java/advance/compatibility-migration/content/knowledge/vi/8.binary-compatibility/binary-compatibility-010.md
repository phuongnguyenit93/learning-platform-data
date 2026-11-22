# Hằng số compile-time và giá trị đã được nhúng vào mã bên sử dụng

## 1. Một thay đổi rất nhỏ có thể khiến hai phiên bản cùng nhìn thấy hai giá trị

Giả sử thư viện Java công bố một giá trị dùng chung:

```java
package example.api;

public final class Limits {
    public static final int MAX_ATTEMPTS = 3;

    private Limits() {
    }
}
```

Ứng dụng sử dụng thư viện:

```java
if (attempts >= Limits.MAX_ATTEMPTS) {
    throw new IllegalStateException("Too many attempts");
}
```

Nhà phát triển thư viện thay `MAX_ATTEMPTS` từ `3` thành `5`, đóng gói JAR mới và triển khai. Một số ứng dụng đã được **biên dịch trước khi thay đổi** vẫn so sánh với `3`, mặc dù class `Limits` ở runtime chứa giá trị `5`. Nguyên nhân là compiler Java có thể đưa giá trị của **hằng số tại thời điểm biên dịch** vào bytecode của mã sử dụng, thay vì để lại một thao tác đọc field từ thư viện khi chạy.

Đây là vấn đề quan trọng trong **binary compatibility**: một thay đổi có thể giữ nguyên tên, kiểu và quyền truy cập của field nên không tạo lỗi liên kết nhị phân, nhưng làm phiên bản đã biên dịch cũ và phiên bản mới quan sát các giá trị khác nhau. Lỗi thường khó nhận thấy vì ứng dụng có thể khởi động bình thường, không có `NoSuchFieldError`, và chỉ biểu hiện thành quy tắc nghiệp vụ, giao thức hoặc kiểm tra bảo mật không nhất quán.

Mục tiêu bài học:

- Nhận diện chính xác field nào là *constant variable* theo quy tắc của ngôn ngữ Java.
- Hiểu cách `javac` đưa giá trị vào bytecode và cách `ConstantValue` được lưu trong class file.
- Phân biệt tương thích nhị phân với sự thống nhất về giá trị và hành vi.
- Dự đoán tác động khi thay giá trị, kiểu, tên hoặc cách khởi tạo một hằng số public.
- Kiểm tra artifact cũ bằng `javap`, xây dựng phép thử library/client qua nhiều phiên bản và lựa chọn chiến lược migration phù hợp.

## 2. Hằng số compile-time trong Java là gì?

### 2.1. Định nghĩa *constant variable*

Theo Java Language Specification, một biến `final` có kiểu nguyên thủy (*primitive*) hoặc `String` và được khởi tạo bằng một *constant expression* là một **constant variable**. Kiểu và biểu thức khởi tạo đều quan trọng; chỉ có `final` hoặc chỉ có `static final` là chưa đủ.

Trong API, trường hợp thường gây rủi ro nhất là field `public static final` đáp ứng định nghĩa trên:

```java
public final class Protocol {
    public static final int VERSION = 2;
    public static final long TIMEOUT_MILLIS = 5_000L;
    public static final boolean ENABLED = true;
    public static final char DELIMITER = '|';
    public static final String PREFIX = "APP-";
}
```

Các field này đều là compile-time constants. Khi mã client dùng chúng trong biểu thức, compiler có thể dùng ngay các giá trị `2`, `5000L`, `true`, `'|'` hoặc `"APP-"` khi biên dịch.

Không phải mọi `static final` đều là compile-time constant:

```java
import java.time.Duration;
import java.util.List;

public final class Settings {
    // Constant variable: primitive + final + constant expression.
    public static final int DEFAULT_PORT = 8080;

    // Constant variable: String + final + constant expression.
    public static final String SERVICE = "catalog" + "-api";

    // Không phải constant variable: lời gọi phương thức.
    public static final int PORT_FROM_CONFIG =
            Integer.parseInt(System.getProperty("app.port", "8080"));

    // Không phải constant variable: kiểu Duration không phải primitive/String.
    public static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(5);

    // Không phải constant variable: kiểu List.
    public static final List<String> ROLES = List.of("reader", "writer");

    // Không phải constant variable: mảng, dù reference là final.
    public static final int[] CODES = {200, 201};
}
```

`static` không phải điều kiện bắt buộc trong định nghĩa ngôn ngữ của constant variable; biến cục bộ `final` cũng có thể đáp ứng định nghĩa. Tuy nhiên, đối với tương thích giữa các JAR, các **field public `static final`** và constant field trong interface là những điểm cần khảo sát trước tiên vì chúng tạo hợp đồng giữa thư viện và consumer.

### 2.2. Bảng nhận diện

| Khai báo | Constant variable? | Lý do |
| --- | --- | --- |
| `public static final int CODE = 200;` | Có | Primitive, `final`, initializer là constant expression |
| `public static final String NAME = "A" + "B";` | Có | Ghép hai string literal tại compile time |
| `public static final boolean ACTIVE = 1 < 2;` | Có | Biểu thức hằng trả boolean |
| `public static final Integer CODE = 200;` | Không | Kiểu wrapper `Integer`, không phải primitive |
| `public static final String NAME = new String("A");` | Không | Biểu thức tạo object |
| `public static final int CODE = Integer.parseInt("200");` | Không | Có lời gọi method |
| `public static final int[] CODES = {200};` | Không | Kiểu mảng |
| `public static int CODE = 200;` | Không | Thiếu `final` |
| `public static final String NAME = System.getenv("NAME");` | Không | Giá trị chỉ biết ở runtime |
| `public final int CODE = 200;` | Có | Instance field `final`, primitive, initializer là constant expression; cần xem thêm ngữ cảnh sử dụng |

Với các khai báo không phải constant variable, mã client thường phải đọc field lúc chạy bằng lệnh bytecode như `getstatic` hoặc `getfield`. Với compile-time constant được dùng như giá trị, compiler thường nhúng giá trị vào biểu thức của client và không cần đọc field ở runtime.

## 3. Constant expression và cơ chế gộp biểu thức tại biên dịch

Một *constant expression* có thể gồm literal, tham chiếu đến constant variable khác và một tập phép toán được Java cho phép: phép toán số học, so sánh, toán tử logic, toán tử điều kiện, ép kiểu hợp lệ, nối chuỗi và dấu ngoặc. Không phải mọi biểu thức không đổi khi chạy đều là constant expression theo ngôn ngữ.

```java
public final class WireFormat {
    public static final int HEADER_SIZE = 8;
    public static final int CHECKSUM_SIZE = 4;

    public static final int MIN_PACKET_SIZE =
            HEADER_SIZE + CHECKSUM_SIZE; // 12 tại compile time

    public static final String MAJOR = "2";
    public static final String MESSAGE_VERSION =
            "wire-v" + MAJOR;           // "wire-v2" tại compile time

    public static final boolean STRICT =
            MIN_PACKET_SIZE >= 12;      // true tại compile time

    private WireFormat() {
    }
}
```

Ứng dụng sử dụng `WireFormat.MIN_PACKET_SIZE + 2` có thể được biên dịch thành giá trị `14`. Thư viện sau đó thay `HEADER_SIZE` thành `16`, tạo `MIN_PACKET_SIZE = 20` ở phiên bản mới, nhưng client cũ vẫn có thể giữ giá trị `14` trong bytecode. Việc thay hằng số gốc có thể ảnh hưởng dây chuyền đến nhiều constant expression ở module khác.

Phân biệt hai kiểu viết:

```java
public static final int STATIC_LIMIT = 10;
public static final int COMPUTED_LIMIT = Math.max(8, 10);
```

Mặc dù `Math.max(8, 10)` luôn trả `10` trong ví dụ này, đó vẫn là lời gọi method và không phải constant expression theo quy tắc của Java. `STATIC_LIMIT` có thể được nhúng vào bytecode client, còn `COMPUTED_LIMIT` cần khởi tạo tại runtime và thông thường được đọc qua field.

Điểm quan trọng: **tính bất biến về mặt ý định** không giống **khả năng tính được tại compile time theo JLS**. Compiler áp dụng các quy tắc cụ thể của ngôn ngữ, không chỉ đoán rằng một biểu thức “chắc chắn không đổi”.

## 4. Giá trị đã được nhúng vào bytecode như thế nào?

### 4.1. Tham chiếu field có thể biến thành literal

Xét một thư viện:

```java
package example;

public final class BuildInfo {
    public static final int FORMAT = 7;
    public static final String LABEL = "v7";

    private BuildInfo() {
    }
}
```

Và client:

```java
package example;

public final class Reader {
    public static int requiredFormat() {
        return BuildInfo.FORMAT;
    }

    public static String label() {
        return BuildInfo.LABEL;
    }
}
```

Khi biên dịch, `Reader.requiredFormat()` thường chứa instruction đẩy giá trị số `7` lên operand stack, còn `Reader.label()` tải literal `"v7"` từ constant pool. Thay cho `getstatic example/BuildInfo.FORMAT`, lời gọi chỉ dùng giá trị đã có ở artifact `Reader.class`.

Trình biên dịch chọn instruction phù hợp với kiểu và kích thước giá trị:

- `iconst_*` cho một số nguyên nhỏ.
- `bipush` hoặc `sipush` cho những khoảng giá trị tương ứng.
- `ldc`, `ldc_w` hoặc `ldc2_w` cho literal nằm trong constant pool.

Không nên phụ thuộc vào một instruction cụ thể trong thiết kế API; đó là chi tiết code generation. Điều cần kiểm tra là client có đọc field tại runtime hay đã dùng literal.

### 4.2. Attribute `ConstantValue` trong class file

Class file có thể mang attribute `ConstantValue` cho field được biểu diễn bằng hằng số. Ví dụ khi dùng:

```bash
javap -classpath library.jar -p -v example.BuildInfo
```

Output chi tiết có thể chứa thông tin tương tự:

```text
public static final int FORMAT;
  descriptor: I
  flags: (0x0019) ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 7

public static final java.lang.String LABEL;
  descriptor: Ljava/lang/String;
  flags: (0x0019) ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: String v7
```

`ConstantValue` mô tả giá trị trong **class định nghĩa field**. Nó không tự cập nhật các literal đã được compiler đưa vào **class sử dụng field**. Hai artifact có thể chứa các giá trị khác nhau và vẫn đều là class file hợp lệ.

### 4.3. Cách nhìn vào bytecode của client

Để xem phần client có đọc field hay không:

```bash
javap -classpath client-classes:library.jar -c -v example.Reader
```

Quan sát phần code của `requiredFormat()` và `label()`. Nếu thấy instruction tải literal và không thấy `getstatic` tương ứng với `BuildInfo.FORMAT`/`BuildInfo.LABEL`, giá trị đã được nhúng vào bytecode. Trên Windows, dấu phân cách classpath thường là dấu chấm phẩy (`;`), còn trên Linux/macOS là dấu hai chấm (`:`).

Tham chiếu chỉ sử dụng compile-time constant có thể **không để lại class reference** đến class định nghĩa hằng số trong phần bytecode tương ứng. Do vậy, chỉ nhìn dependency graph ở runtime hoặc output của `jdeps` có thể không tìm được mọi mối phụ thuộc **ở cấp mã nguồn** vào constant API.

## 5. Thí nghiệm hoàn chỉnh: thư viện đổi giá trị nhưng client vẫn giữ giá trị cũ

### 5.1. Tạo phiên bản thư viện thứ nhất

File `library-v1/example/RetryPolicy.java`:

```java
package example;

public final class RetryPolicy {
    public static final int MAX_RETRIES = 3;
    public static final String LEVEL = "standard";

    private RetryPolicy() {
    }

    public static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
```

Phương thức `currentMaxRetries()` được biên dịch vào class của **thư viện**. Nếu thư viện được biên dịch lại, bytecode phương thức này sẽ phản ánh giá trị mới trong phiên bản mới.

### 5.2. Tạo client dựa trên thư viện v1

File `client/example/RetryClient.java`:

```java
package example;

public final class RetryClient {
    public static void main(String[] args) {
        System.out.println("constant = " + RetryPolicy.MAX_RETRIES);
        System.out.println("method   = " + RetryPolicy.currentMaxRetries());
        System.out.println("level    = " + RetryPolicy.LEVEL);
    }
}
```

Biên dịch library v1 và client bằng đúng library v1:

```bash
javac -d out/lib-v1 library-v1/example/RetryPolicy.java
javac -cp out/lib-v1 -d out/client client/example/RetryClient.java
java -cp out/client:out/lib-v1 example.RetryClient
```

Kết quả mong đợi khi chạy toàn bộ v1:

```text
constant = 3
method   = 3
level    = standard
```

### 5.3. Thay thư viện bằng v2, không biên dịch lại client

File `library-v2/example/RetryPolicy.java`:

```java
package example;

public final class RetryPolicy {
    public static final int MAX_RETRIES = 5;
    public static final String LEVEL = "strict";

    private RetryPolicy() {
    }

    public static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
```

Biên dịch thư viện v2, giữ nguyên toàn bộ `out/client`:

```bash
javac -d out/lib-v2 library-v2/example/RetryPolicy.java
java -cp out/client:out/lib-v2 example.RetryClient
```

Kết quả minh họa:

```text
constant = 3
method   = 5
level    = standard
```

Giải thích:

- `RetryPolicy.MAX_RETRIES` trong `RetryClient.class` vẫn là literal `3` từ lần compile v1.
- Phương thức `RetryPolicy.currentMaxRetries()` được gọi từ **thư viện v2**, nên trả `5`.
- `RetryPolicy.LEVEL` trong client vẫn là `"standard"` dù field của v2 có giá trị `"strict"`.
- Không nhất thiết xuất hiện lỗi `NoSuchFieldError` hoặc `NoSuchMethodError`, vì method vẫn tồn tại và bytecode dùng giá trị hằng cho các field còn lại.

### 5.4. Biên dịch lại client với v2

```bash
javac -cp out/lib-v2 -d out/client-v2 client/example/RetryClient.java
java -cp out/client-v2:out/lib-v2 example.RetryClient
```

Khi cả thư viện lẫn client được biên dịch theo v2, kết quả sẽ là:

```text
constant = 5
method   = 5
level    = strict
```

Đó là khác biệt cốt lõi: **nâng dependency tại runtime** không giống **biên dịch lại mã phụ thuộc vào compile-time constant**.

Nếu làm thử trên Windows, hãy thay dấu `:` trong các ví dụ `-cp` bằng `;`. Các lệnh là ví dụ học tập; khi áp dụng cho dự án thật cần dùng artifact, toolchain và quy trình build được tổ chức kiểm soát.

## 6. Vì sao đây là rủi ro tương thích dù JVM không báo lỗi?

### 6.1. Tương thích liên kết khác tương thích giá trị

Khi thay duy nhất giá trị:

```java
// Library v1
public static final int MAX_RETRIES = 3;

// Library v2
public static final int MAX_RETRIES = 5;
```

field vẫn có cùng owner, tên, kiểu, descriptor `I` và quyền truy cập. Không phải thay đổi nào ở cấp binary cũng tạo lỗi linkage. Nhưng ứng dụng cũ đã nhúng `3` có thể không bao giờ đọc field của v2, nên giá trị được triển khai ở runtime không quyết định hành vi của nó.

Trong báo cáo migration cần phân biệt:

1. **Linkage compatibility:** client cũ có nạp và liên kết với thư viện mới không?
2. **Value consistency:** client cũ và thư viện mới có cùng nhận thức về giá trị hay không?
3. **Behavioral compatibility:** logic dựa trên giá trị đó còn đúng không?

Với compile-time constant public, chỉ kiểm thử mục thứ nhất là chưa đủ.

### 6.2. Thay kiểu field tạo thêm rủi ro

Đổi:

```java
public static final int MAX_RETRIES = 3;
```

thành:

```java
public static final long MAX_RETRIES = 5L;
```

làm descriptor field đổi từ `I` thành `J`. Các client **đã nhúng literal** có thể tiếp tục dùng giá trị cũ mà không cần phân giải field ở runtime. Nhưng client dùng reflection, method handle hoặc một truy cập field được biên dịch dưới dạng `getstatic` với descriptor cũ có thể gặp lỗi hoặc không tìm thấy field phù hợp. Mã nguồn biên dịch lại cũng có thể cần sửa vì kiểu đã thay đổi.

Không được kết luận rằng mọi client đều an toàn hoặc mọi client đều lỗi chỉ vì kiểu field đã đổi. Cần xác định **cách từng client truy cập field**.

### 6.3. Xóa constant field đôi khi không làm client cũ lỗi ngay

Nếu client đã biên dịch chỉ còn literal, việc xóa field trong JAR mới có thể không gây lỗi tại đường chạy đó. Đây không phải dấu hiệu cho thấy việc xóa API là an toàn: client biên dịch lại sẽ không tìm thấy field, còn reflection hoặc các đường truy cập runtime có thể thất bại.

Đặc biệt, một test chỉ chạy bytecode cũ mà không biên dịch lại consumer có thể bỏ sót lỗi source compatibility. Ngược lại, chỉ build lại toàn bộ consumer có thể che đi vấn đề stale constant mà sản phẩm đã phát hành đang gặp.

## 7. `static final` không luôn đồng nghĩa với việc nhúng giá trị

So sánh:

```java
public final class Config {
    public static final int COMPILE_TIME = 10;
    public static final int RUNTIME_COMPUTED = Integer.parseInt("10");

    private Config() {
    }
}
```

`COMPILE_TIME` là constant variable; `RUNTIME_COMPUTED` không phải, vì initializer gọi `Integer.parseInt`. Tham chiếu từ client đến `RUNTIME_COMPUTED` cần đọc field ở runtime, thường qua `getstatic`. Khi thay thư viện mới mà vẫn giữ tên, kiểu và tính khả dụng của field, mã client có thể đọc giá trị do thư viện mới khởi tạo.

Tuy nhiên, cách viết cố tình gọi method chỉ để tránh inline không phải lúc nào cũng là API tốt. Một field runtime có thể kéo theo class initialization và ngoại lệ khởi tạo. Với giá trị có thể thay đổi qua các bản phát hành, **accessor method** thường diễn đạt hợp đồng tốt hơn:

```java
public final class RetryPolicy {
    private static final int DEFAULT_MAX_RETRIES = 5;

    private RetryPolicy() {
    }

    public static int maxRetries() {
        return DEFAULT_MAX_RETRIES;
    }
}
```

Mã client `RetryPolicy.maxRetries()` sẽ gọi method của phiên bản thư viện hiện đang được nạp. Khi chỉ thay giá trị trong implementation và giữ nguyên method descriptor, client cũ có thể nhận được giá trị mới tại runtime. Đây là một cách tách implementation detail khỏi hợp đồng nhị phân của consumer.

Không phải giá trị nào cũng nên đọc qua method. Những đại lượng thật sự bất biến theo định nghĩa, ví dụ số byte trong một `short` Java hoặc một mã protocol được đóng băng vĩnh viễn, có thể hợp lý khi công bố dưới dạng compile-time constant. Quyết định phụ thuộc vào khả năng **giá trị phải thay đổi mà không rebuild consumer**.

## 8. Truy cập compile-time constant có thể không khởi tạo class

Tham chiếu tới constant variable trong một số ngữ cảnh không khiến JVM khởi tạo class chứa field. Điều này tạo khác biệt quan sát được khi mã khởi tạo có side effect:

```java
public final class RuntimeFlags {
    static {
        System.out.println("RuntimeFlags initialized");
    }

    public static final int STATIC_CODE = 42;
    public static final int DYNAMIC_CODE = Integer.parseInt("42");

    private RuntimeFlags() {
    }
}
```

Client:

```java
System.out.println(RuntimeFlags.STATIC_CODE);
System.out.println(RuntimeFlags.DYNAMIC_CODE);
```

Ở câu đầu, compiler có thể dùng literal `42` mà không đọc field và không cần khởi tạo `RuntimeFlags`. Ở câu sau, đọc `DYNAMIC_CODE` qua `getstatic` là một tình huống khiến class được khởi tạo trước khi đọc, nên khối `static` có thể in ra thông báo.

Nếu thư viện đổi `STATIC_CODE` thành một field tính ở runtime, client **được biên dịch lại** có thể bắt đầu kích hoạt class initialization khi truy cập. Client **đã biên dịch cũ** có thể vẫn chỉ dùng literal. Ngoài giá trị, sự thay đổi này có thể ảnh hưởng thứ tự khởi tạo, chi phí khởi động hoặc exception từ initializer.

Không thiết kế logic cần side effect của `static` initializer dựa vào việc consumer sẽ đọc một compile-time constant. Nếu class phải được khởi tạo cho một tác vụ cụ thể, hãy đưa tác vụ đó vào API/runtime flow được định nghĩa rõ.

## 9. Hằng số trong interface và rủi ro đối với mã dùng chung

Mọi field khai báo trong Java interface đều ngầm có các modifier `public static final`. Nếu field là primitive hoặc `String` được khởi tạo bằng constant expression, nó là compile-time constant.

```java
public interface MessageCodes {
    int OK = 200;
    int NOT_FOUND = 404;
    String TYPE = "application/vnd.example.v1+json";
}
```

Mã client:

```java
int code = MessageCodes.OK;
String type = MessageCodes.TYPE;
```

có thể nhúng các giá trị này vào bytecode. Nếu module định nghĩa interface đổi `TYPE` sang `v2` nhưng service consumer không rebuild, service đó vẫn gửi hoặc kiểm tra media type cũ.

Không nên dùng interface chỉ để gom các hằng số (thường gọi là *constant interface antipattern*), đặc biệt nếu class triển khai interface chỉ nhằm kế thừa tên hằng số. Với bộ giá trị cần chia sẻ, một class utility được tổ chức rõ namespace có thể hợp lý hơn, nhưng việc chuyển từ interface sang class cũng **không tự giải quyết inlining** nếu vẫn dùng `public static final` compile-time constants.

Nếu giá trị được quản lý theo phiên bản giao thức hoặc có thể thay đổi độc lập, hãy cân nhắc một API cung cấp giá trị theo phương thức, cấu hình runtime hoặc type riêng có hợp đồng rõ.

## 10. Trường hợp đặc biệt: `switch`, annotation và constant folding

### 10.1. Nhãn `case` trong `switch`

Trong nhiều dạng `switch` trên số nguyên hoặc chuỗi, nhãn `case` dùng constant expression. Ví dụ:

```java
public final class StatusCodes {
    public static final int ACCEPTED = 202;

    private StatusCodes() {
    }
}
```

```java
String describe(int code) {
    return switch (code) {
        case StatusCodes.ACCEPTED -> "accepted";
        default -> "other";
    };
}
```

Client đã biên dịch mã `switch` có thể sử dụng ngay literal `202` trong bảng nhảy hoặc logic so sánh. Nếu thư viện sau đó đổi `ACCEPTED` sang `203` mà client không rebuild, logic `switch` cũ không tự chuyển sang nhận `203`. Đây là ví dụ stale constant có thể làm lệch protocol handling.

Chú ý: enum constant và pattern matching có quy tắc riêng, không nên đồng nhất chúng với constant variable primitive/`String`. Phần ví dụ trên tập trung vào `case` sử dụng constant expression.

### 10.2. Giá trị trong annotation

Annotation có thể yêu cầu constant expression cho nhiều loại element. Ví dụ:

```java
public final class Routes {
    public static final String ROOT = "/v1/orders";

    private Routes() {
    }
}
```

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Route {
    String value();
}

@Route(Routes.ROOT)
class OrderHandler {
}
```

Compiler ghi giá trị của `Routes.ROOT` vào metadata annotation trong `OrderHandler.class`. Sau khi nâng thư viện đổi `ROOT` thành `"/v2/orders"`, class `OrderHandler` đã biên dịch vẫn có thể mang annotation `"/v1/orders"`. Framework đọc annotation qua reflection sẽ thấy giá trị đã được lưu trong **artifact consumer**, không có cơ chế tự đọc lại constant field từ class `Routes`.

Đây là nguy cơ lớn với routing, serializer, validation, message mapping và các framework dùng annotation để cấu hình behavior.

### 10.3. Biểu thức được gộp qua nhiều lớp

```java
public final class Headers {
    public static final String PRODUCT = "service";
    public static final String X_PRODUCT_HEADER = "X-" + PRODUCT;
}
```

Nếu code consumer khai báo:

```java
public static final String EXPECTED_HEADER = Headers.X_PRODUCT_HEADER;
```

thì `EXPECTED_HEADER` cũng có thể trở thành constant variable chứa literal `"X-service"`. Thay đổi `Headers.PRODUCT` ở thư viện có thể đòi hỏi rebuild nhiều tầng module vì mỗi tầng có thể tiếp tục nhúng giá trị cũ.

## 11. Hậu quả trong migration phiên bản và triển khai nhiều service

Thay đổi compile-time constant có thể lan ra các ranh giới sau:

| Vị trí sử dụng | Rủi ro khi thư viện cập nhật nhưng consumer không rebuild |
| --- | --- |
| Giới hạn retry/timeout | Logic client vẫn áp dụng ngưỡng cũ, dù method runtime báo ngưỡng mới |
| Mã trạng thái hoặc mã thông điệp | Producer và consumer hiểu hai bộ mã khác nhau |
| Route, header, media type | Annotation hoặc String literal đã biên dịch vẫn dùng định dạng cũ |
| Feature flag mặc định | Module cũ quyết định theo giá trị cũ, module mới theo giá trị mới |
| Giới hạn input bảo mật | Kiểm tra ở ứng dụng cũ có thể giữ ngưỡng mà bản vá muốn thay đổi |
| Tham số cache hoặc TTL | Module được rebuild và module chưa rebuild vận hành theo chính sách khác nhau |
| Tên bảng, trường dữ liệu hoặc schema ID | Consumer lưu/đọc tên cũ dù thư viện định nghĩa đã đổi |
| Nhãn `case` hoặc annotation element | Giá trị được ghi sẵn trong bytecode/metadata cần biên dịch lại |

### 11.1. Thay đổi mức an toàn hoặc bảo mật

Giả sử thư viện v1 có:

```java
public static final int MAX_PAYLOAD_BYTES = 1_000_000;
```

Một bản vá đặt lại mức giới hạn còn `100_000` để ngăn input quá lớn:

```java
public static final int MAX_PAYLOAD_BYTES = 100_000;
```

Nếu web gateway hoặc ứng dụng consumer đã biên dịch điều kiện `payload.length > MAX_PAYLOAD_BYTES` thành phép so sánh với `1_000_000`, chỉ thay JAR thư viện có thể **không áp dụng giới hạn mới ở đường kiểm tra đó**. Phải tìm mọi consumer phụ thuộc hằng số, rebuild và triển khai artifact mới hoặc chuyển sang một API truy vấn ngưỡng runtime.

Không nên coi một bản vá bảo mật là đã triển khai đầy đủ chỉ vì dependency scanner không còn báo phiên bản bị ảnh hưởng. Cần xác minh đường xử lý thực tế có dùng giá trị/quy tắc đã sửa hay không.

### 11.2. Rolling deployment và version skew

Trong một đợt triển khai cuốn chiếu, có thể có service A phiên bản cũ, service A phiên bản mới, consumer B cũ và consumer B mới cùng hoạt động. Nếu các service trao đổi giá trị chịu ảnh hưởng của compile-time constants, mỗi artifact có thể mang một giá trị khác nhau.

Ví dụ, producer mới bắt đầu gửi message code `25`, nhưng consumer cũ đã compile `case 20`. Nâng thư viện chứa `MESSAGE_CODE = 25` trên host consumer chưa đủ để đổi logic đã biên dịch. Cần thiết kế protocol compatibility hoặc cho phép consumer hiểu đồng thời hai mã trong giai đoạn chuyển tiếp.

Một nguyên tắc quan trọng: giá trị đánh dấu phiên bản protocol, schema hoặc message không nên thay đổi âm thầm chỉ vì một constant trong JAR chung được sửa. Nên có versioning và kế hoạch tương thích producer–consumer rõ ràng.

## 12. Ma trận ảnh hưởng khi thay đổi field

| Thay đổi trong thư viện | Bytecode client cũ đã inline | Consumer truy cập field lúc chạy | Consumer biên dịch lại |
| --- | --- | --- | --- |
| Đổi giá trị hằng cùng kiểu | Có thể tiếp tục giữ giá trị cũ | Có thể đọc giá trị mới | Thường nhận giá trị mới |
| Đổi `int` thành `long` | Có thể tiếp tục giữ literal cũ | Có nguy cơ không khớp descriptor field | Có thể cần đổi kiểu và logic |
| Đổi tên field | Có thể vẫn chạy nếu không còn tham chiếu field runtime | Có thể lỗi truy cập/không tìm thấy field | Lỗi nếu vẫn dùng tên cũ |
| Xóa field | Có thể vẫn chạy tại chỗ đã inline | Có thể gặp `NoSuchFieldError`/lỗi reflection | Lỗi biên dịch khi dùng field đã xóa |
| Đổi constant expression thành runtime initializer cùng kiểu | Vẫn giữ literal cũ | Đọc field runtime mới; có thể kích hoạt class initialization | Thường phát sinh `getstatic` thay vì literal |
| Đổi `static final` thành field mutable cùng kiểu | Giá trị cũ đã inline không tự cập nhật | Cần kiểm tra quyền truy cập, modifiers và behavior | Có thể đọc giá trị thay đổi ở runtime |
| Giữ constant và thêm accessor mới | Đường dùng constant cũ vẫn stale | Accessor có thể trả giá trị runtime của thư viện mới | Có thể chuyển sang accessor |

Bảng chỉ nêu xu hướng phân tích, không phải bảo đảm chung cho mọi field hoặc compiler. Kết quả thực tế phụ thuộc vào bytecode client, kiểu field, cách truy cập, reflection, module access và phiên bản class đang được JVM nạp.

Đặc biệt, **mã nguồn dùng tên của một constant** không bảo đảm bytecode còn một tham chiếu tới field đó. Muốn đánh giá chính xác, phải xem artifact đã biên dịch.

## 13. Phân biệt rủi ro constant với lỗi liên kết field thông thường

Một tình huống khác là code được biên dịch để đọc field tại runtime:

```java
public final class RuntimeSettings {
    public static final int MAX_RETRIES =
            Integer.parseInt("3");
}
```

Client:

```java
int retries = RuntimeSettings.MAX_RETRIES;
```

Vì đây không phải constant variable, compiler cần tạo truy cập `getstatic` cho field. Nếu thư viện đổi tên hoặc loại bỏ field, client có thể gặp `NoSuchFieldError` khi lời gọi được phân giải. Nếu thư viện đổi kiểu `int` sang `long`, descriptor `I` của lời gọi cũ không khớp field `J` mới, cũng có thể phát sinh `NoSuchFieldError`.

Đặt cạnh nhau:

- **Compile-time inlining:** thay giá trị, client cũ vẫn chạy nhưng dùng literal cũ.
- **Runtime field linkage:** lời gọi còn tham chiếu symbolic field; đổi hoặc xóa field có thể gây linkage error.
- **Reflection/annotation:** đường quan sát có thể không giống cả hai kiểu trên; reflection đọc metadata của class đã nạp, annotation value có thể được lưu sẵn trong class consumer.

Không thể suy ra rủi ro chỉ từ cách khai báo `public static final` trên source. Cần kiểm tra initializer, kiểu field và cách consumer được compile.

## 14. Cách điều tra bằng compiler và bytecode

### 14.1. Xác định API cung cấp hằng số

Tìm các field dùng trong module public/shared:

```java
public static final int ...
public static final long ...
public static final String ...
```

Đừng chỉ tìm đúng chuỗi `public static final`: field trong interface có modifier ngầm định, và code có thể sử dụng `static import`:

```java
import static example.api.Limits.MAX_ATTEMPTS;

if (attempts >= MAX_ATTEMPTS) {
    // ...
}
```

Hãy xác định initializer có phải constant expression, field được dùng ở những module nào và có nằm trong annotation, `case` hay biểu thức constant khác không.

### 14.2. Xem class file của thư viện

```bash
javap -classpath old-library.jar -p -v example.api.Limits
javap -classpath new-library.jar -p -v example.api.Limits
```

Ghi lại descriptor, flags và `ConstantValue` trước/sau. Đổi `ConstantValue` nhưng giữ descriptor là tín hiệu cần tìm client đã inline, dù không nhất thiết có lỗi binary linkage.

### 14.3. Xem bytecode client

```bash
javap -classpath client.jar:old-library.jar -c -v example.app.Controller
```

Tìm những phần sử dụng giá trị constant:

- Literal được tải bằng `iconst_*`, `bipush`, `sipush`, `ldc` hoặc `ldc2_w`.
- Lệnh `getstatic` hay `getfield` trỏ tới owner và descriptor của field.
- Constant pool và annotation attributes có chứa giá trị literal cũ không.
- Biểu thức đã được constant folding thành một giá trị khác hay chưa.

Hãy xem **bytecode của consumer**, không chỉ bytecode của library. Field bên thư viện có `ConstantValue: int 5` không chứng minh consumer cũ đã dùng `5`.

### 14.4. Xác minh artifact và dependency thực tế

Khi một môi trường báo giá trị cũ, kiểm tra:

1. Commit và artifact version mà consumer đã được biên dịch.
2. JAR cụ thể được đặt trong runtime image của consumer.
3. Library version có mặt lúc consumer compile.
4. Bytecode có literal cũ hay field access.
5. Các bản client/consumer đã rebuild và triển khai trong rollout chưa.

Classpath có thể chứa nhiều bản thư viện; build cache, shaded JAR hoặc image cũ có thể khiến quá trình điều tra nhầm hướng. Phải xác minh artifact thực sự được chạy thay vì chỉ so phiên bản dependency khai báo trong build script.

## 15. Kiểm thử tương thích giữa thư viện và consumer

Khi thay đổi constant public, một phép thử đơn lẻ chưa đủ. Có thể lập ma trận:

| Client bytecode | Library runtime | Mục đích |
| --- | --- | --- |
| Biên dịch với v1 | Chạy cùng v1 | Baseline, xác nhận hành vi trước migration |
| Biên dịch với v1 | Chạy cùng v2 | Phát hiện stale constant, lỗi linkage và version skew |
| Biên dịch lại với v2 | Chạy cùng v2 | Xác nhận hành vi và giá trị mới |
| Biên dịch với v2 | Chạy cùng v1 (chỉ khi cần hỗ trợ) | Đánh giá khả năng downgrade và điều kiện hỗ trợ tương thích |

Các test nên kiểm tra cả **giá trị nhìn thấy** và **hành vi dùng giá trị đó**. Ví dụ, một test chỉ gọi `Limits.maxRetries()` có thể pass khi thư viện trả `5`, trong khi logic consumer đã compile vẫn so với `3`. Test đúng phải đi qua luồng quyết định retry của consumer đã đóng gói.

### 15.1. Kiểm thử ở cấp hợp đồng

Với hằng số có ý nghĩa giao thức, hãy kiểm tra từ hai phía:

- Consumer cũ có còn đọc/hiểu dữ liệu được producer mới gửi không?
- Có dữ liệu hay request nào phải hỗ trợ song song phiên bản cũ/mới không?
- Các annotation/route/schema được đóng gói trong consumer có đúng giá trị mục tiêu không?
- Có cần một thời kỳ chuyển đổi, dual-read/dual-write hoặc adapter protocol không?

### 15.2. Không đồng nhất clean build với cập nhật toàn hệ sinh thái

Clean build một module chỉ cập nhật class của module đó. Nếu ứng dụng dùng các JAR nội bộ được build từ trước, những JAR đó có thể vẫn chứa giá trị cũ. Bởi vậy, cần xác định danh sách consumer và rebuild theo dependency graph, bao gồm các artifact đã xuất bản, module nội bộ, plugin, ứng dụng downstream và service có lịch triển khai độc lập.

Khi một thay đổi hằng số được dùng cho bảo mật, việc truy vết mọi consumer đang chạy là một phần của xác nhận bản vá, không chỉ của công tác build.

## 16. Thiết kế API để hạn chế stale constants

### 16.1. Giữ compile-time constant cho giá trị thật sự không đổi

`public static final` compile-time constant phù hợp với những giá trị thực sự là một phần định nghĩa ổn định, chẳng hạn ký tự phân cách được tiêu chuẩn hóa và không dự kiến đổi, hoặc mã nhận diện đã được đóng băng theo phiên bản cụ thể.

Nếu giá trị phải đổi khi chuyển phiên bản, cân nhắc đặt tên phản ánh phiên bản:

```java
public static final String MEDIA_TYPE_V1 =
        "application/vnd.example.v1+json";
public static final String MEDIA_TYPE_V2 =
        "application/vnd.example.v2+json";
```

Thêm một hằng số mới thay vì thay âm thầm giá trị của hằng số cũ giúp consumer chọn rõ hợp đồng. Tuy nhiên, consumer vẫn cần cập nhật mã khi quyết định chuyển phiên bản.

### 16.2. Dùng accessor cho giá trị cần nâng cấp ở runtime

```java
public final class Policy {
    private static final int RETRY_LIMIT = 5;

    private Policy() {
    }

    public static int retryLimit() {
        return RETRY_LIMIT;
    }
}
```

Từ phía consumer:

```java
if (attempts >= Policy.retryLimit()) {
    stopRetrying();
}
```

Method call có descriptor rõ ràng `()I`. Nếu thư viện sau này chỉ đổi giá trị trả về và vẫn giữ tên/chữ ký method, mã consumer cũ sẽ gọi implementation mới. Nếu method được inline bởi JIT khi runtime tối ưu, đó là tối ưu **trong tiến trình đang chạy**, khác với việc `javac` nhúng literal vào class file lúc compile. JIT không khiến JAR consumer đã phát hành mang giá trị cố định từ bản thư viện cũ theo cùng cách.

### 16.3. Dùng cấu hình runtime cho chính sách vận hành

Retry limit, timeout, mức cache và flag vận hành thường thích hợp với cấu hình runtime có validation, default và cơ chế rollout rõ ràng hơn là constant public. Ví dụ:

```java
public final class RetrySettings {
    private final int maxRetries;

    public RetrySettings(int maxRetries) {
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries must be non-negative");
        }
        this.maxRetries = maxRetries;
    }

    public int maxRetries() {
        return maxRetries;
    }
}
```

Khi đó bản thân việc thay chính sách là một hành động cấu hình có thể kiểm thử và quan sát, thay vì phụ thuộc vào việc các module đã recompile hay chưa.

### 16.4. Tách “giá trị ổn định” và “quyết định nghiệp vụ”

Thay vì để mọi consumer so sánh trực tiếp:

```java
if (payload.length > Limits.MAX_PAYLOAD) {
    reject();
}
```

có thể cung cấp API thể hiện quyết định:

```java
if (!PayloadPolicy.isAllowed(payload.length)) {
    reject();
}
```

Implementation kiểm soát quy tắc trong thư viện. Cách này giúp tránh nhân bản logic, nhưng cần cân nhắc dependency availability, hiệu năng, kiểm thử và nơi thực thi chính sách. Nó không thay thế thiết kế giao thức rõ ràng giữa các service.

## 17. Lộ trình thay đổi một constant public đã được nhiều consumer sử dụng

Nếu cần thay một hằng số đã được công bố lâu năm, có thể tiến hành theo giai đoạn:

### Giai đoạn 1: Khảo sát phạm vi

Xác định owner của library, các artifact consumer, phiên bản đang chạy và đường dùng constant. Tìm cả `static import`, annotation, `case`, code generation, test fixture và constant expression ở module downstream. Xác định thay đổi có thể gây sai dữ liệu, giao thức hay bảo mật không.

### Giai đoạn 2: Chọn hợp đồng mới

Quyết định có giữ nguyên tên field không, có thêm hằng số phiên bản hóa không, hay chuyển sang method/runtime config. Với consumer không thể nâng cấp đồng thời, lên kế hoạch hỗ trợ nhiều phiên bản hoặc adapter.

### Giai đoạn 3: Phát hành library có API chuyển tiếp

Cố gắng giữ field cũ nếu hợp đồng cũ vẫn cần được hỗ trợ, đồng thời cung cấp API mới:

```java
public final class Limits {
    /** @deprecated Consumers should use currentMaxAttempts(). */
    @Deprecated
    public static final int LEGACY_MAX_ATTEMPTS = 3;

    private Limits() {
    }

    public static int currentMaxAttempts() {
        return 5;
    }
}
```

Trong một dự án thật, có thể cần giữ đúng **tên field cũ** để bảo toàn source compatibility cho consumer đang dùng tên đó; ví dụ trên đặt tên `LEGACY_...` để minh họa ý định, không phải mẫu thay thế tên field cũ mà không xem xét tác động. Nếu đổi tên, hãy công bố breaking change và kế hoạch chuyển đổi.

### Giai đoạn 4: Rebuild và kiểm thử consumer

Build lại những artifact cần nhận giá trị mới, rồi kiểm tra bytecode và behavior. Thực hiện ma trận client cũ/client mới với library cũ/library mới khi sản phẩm phải hỗ trợ trạng thái chuyển tiếp.

### Giai đoạn 5: Triển khai và theo dõi

Quan sát các chỉ số liên quan trực tiếp đến thay đổi như retry count, request rejection, message parse failure hoặc lỗi route. Với các thay đổi giao thức, xác nhận consumer cũ đã được nâng cấp hoặc vẫn có cơ chế tương thích.

### Giai đoạn 6: Loại bỏ API cũ theo chính sách hỗ trợ

Chỉ xóa constant cũ khi consumer không còn dùng nó và release policy cho phép. Việc đổi giá trị rồi bỏ qua các artifact đã biên dịch thường khiến hệ thống khó xác định cùng một giá trị “đúng” tại mọi nơi.

## 18. Những nhầm lẫn thường gặp

**“Có `final` thì luôn được inline.”** Sai: constant variable phải có kiểu primitive hoặc `String` và được khởi tạo bằng constant expression. `final Duration`, `final List` hoặc giá trị lấy từ method không đáp ứng điều kiện này.

**“Đổi field từ 3 sang 5 là binary breaking change.”** Không nhất thiết: thay giá trị có thể không phá linkage, nhưng vẫn gây stale constant và khác biệt hành vi. Cần phân biệt dạng tương thích đang đánh giá.

**“Chạy JAR mới là đủ để client thấy hằng số mới.”** Không đúng khi client đã mang literal cũ. Cần rebuild client hoặc thay đổi thiết kế cách lấy giá trị.

**“Lệnh `javap` trên library v2 cho thấy `ConstantValue: 5` nên mọi service dùng 5.”** Không đúng. Phải xem bytecode của consumer và artifact thực sự chạy.

**“Không có `NoSuchFieldError` nghĩa là không còn consumer dùng field.”** Không đúng. Consumer đã inline có thể không còn truy cập field khi chạy, dù nguồn của nó từng phụ thuộc field đó.

**“Chỉ cần đổi `static final int` thành runtime initializer là mọi client cũ sẽ đọc giá trị mới.”** Không đúng. Bytecode cũ không được tái biên dịch, nên literal cũ vẫn còn.

**“Dùng `enum` là cùng một dạng compile-time constant.”** Enum constant là một đối tượng với cơ chế truy cập và tương thích khác primitive/`String` constant variable. Đổi enum cũng có những rủi ro riêng; không nên áp dụng trực tiếp quy tắc inlining literal của `int`/`String` vào enum.

**“Đã clean build module library nên tất cả consumer đã cập nhật.”** Không đúng khi các JAR consumer, ứng dụng downstream hoặc container vẫn mang bytecode đã tạo từ bản cũ.

**“Giá trị trong annotation sẽ đọc lại constant field ở runtime.”** Thông thường annotation value đã được ghi vào class file chứa annotation khi biên dịch. Muốn cập nhật cần build lại artifact chứa annotation.

## 19. Checklist khi review thay đổi hằng số

Trước khi merge hoặc phát hành thay đổi của một field public `static final`:

- [ ] Xác định field có phải constant variable theo JLS không.
- [ ] Ghi lại tên, owner, kiểu, descriptor và `ConstantValue` trước/sau.
- [ ] Xác định những consumer đã compile với giá trị cũ.
- [ ] Tìm tất cả `static import`, `case`, annotation và constant expression sử dụng giá trị.
- [ ] Phân biệt consumer dùng literal và consumer dùng runtime field/method.
- [ ] Kiểm tra việc đổi giá trị có phá behavior, data contract hoặc security policy không.
- [ ] Xây dựng ma trận client cũ/mới với library cũ/mới khi cần hỗ trợ nhiều phiên bản.
- [ ] Rebuild toàn bộ artifact cần nhận giá trị mới, gồm JAR nội bộ và container image.
- [ ] Kiểm tra bytecode consumer bằng `javap -c -v` khi cần xác minh chính xác.
- [ ] Kiểm tra dependency graph và thư viện thực sự được nạp ở runtime.
- [ ] Xác định có cần accessor method, API version mới hoặc runtime config không.
- [ ] Có kế hoạch triển khai cùng consumer và theo dõi chỉ số nghiệp vụ tương ứng.
- [ ] Release notes nêu rõ thay đổi giá trị và tác động đối với consumer cần recompilation.
- [ ] Với bản vá bảo mật, xác nhận đường kiểm tra thực tế đã áp dụng chính sách mới.

Checklist không thay thế kiểm thử tích hợp. Nó giúp tránh bỏ sót một thay đổi có thể được xem là “nhỏ” trong thư viện nhưng đã được nhân bản thành giá trị cố định trong nhiều artifact downstream.

## 20. Tài liệu kỹ thuật cần tham khảo

Các quy tắc có thể đối chiếu trong đặc tả Java:

- **JLS `4.12.4 — `final` Variables:** định nghĩa *constant variable*.
- **JLS `15.29 — Constant Expressions:** các biểu thức được phép tính tại compile time trong các Java release tương ứng.
- **JLS `13.1 — The Form of a Binary:** cách tham chiếu constant variable được biểu diễn khi biên dịch.
- **JLS `13.4.9 — `final` Fields and Constant Variables:** tác động của thay đổi field đối với binary compatibility và giá trị được compiler nhúng.
- **JLS `12.4.1 — When Initialization Occurs:** khác biệt giữa tham chiếu constant variable và truy cập làm khởi tạo class.
- **JVMS `4.7.2 — The `ConstantValue` Attribute:** cách giá trị constant được biểu diễn trong class file.

Khi áp dụng vào một bản Java cụ thể, cần đọc đúng phiên bản JLS/JVMS tương ứng với toolchain đang dùng. Lệnh `javap` trên artifact thực tế là cách trực tiếp để đối chiếu mô hình lý thuyết với bytecode đã phát hành.

## 21. Kết luận

Compile-time constants trong Java là một điểm giao nhau quan trọng giữa mã nguồn, compiler và binary compatibility. Một field `public static final` có kiểu primitive hoặc `String`, được khởi tạo bằng constant expression, có thể được đưa trực tiếp vào bytecode của consumer. Khi library đổi giá trị, consumer đã biên dịch có thể tiếp tục dùng literal cũ dù vẫn khởi động và chạy không có lỗi linkage.

Vì vậy, khi migration, cần đánh giá không chỉ **field hiện có giá trị gì trong thư viện mới**, mà còn **artifact consumer đã được biên dịch với giá trị nào** và **logic nào phụ thuộc vào giá trị đó**. Dùng `javap` để xác minh, rebuild consumer khi cần, kiểm thử nhiều tổ hợp phiên bản và ưu tiên accessor hoặc hợp đồng có version cho giá trị cần thay đổi độc lập. Cách làm này giúp tránh trạng thái các service cùng chạy một hệ thống nhưng tuân theo những hằng số khác nhau.
