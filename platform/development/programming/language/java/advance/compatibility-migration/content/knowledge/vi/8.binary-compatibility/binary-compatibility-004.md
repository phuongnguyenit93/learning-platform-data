# Thay đổi tham số, kiểu trả về và constructor

## 1. Vì sao các thay đổi chữ ký có thể phá vỡ tương thích nhị phân?

Trong Java, mã nguồn được biên dịch thành bytecode. Khi biên dịch một lời gọi method hoặc constructor, compiler ghi vào bytecode thông tin về tên lớp, tên thành viên, loại lời gọi và descriptor của thành viên đó. Khi chạy, JVM dùng các thông tin này để liên kết lời gọi với method hoặc constructor thực tế trong class đang được nạp.

Vì vậy, một chương trình đã biên dịch có thể tiếp tục chạy với phiên bản thư viện mới nếu các thành viên mà bytecode tham chiếu vẫn tồn tại với descriptor và cách truy cập phù hợp. Ngược lại, thay đổi một tham số, kiểu trả về hoặc constructor có thể làm descriptor thay đổi. Mã nguồn của thư viện mới vẫn biên dịch thành công, nhưng ứng dụng client cũ có thể thất bại khi liên kết hoặc gọi thành viên.

Đây là vấn đề **binary compatibility (tương thích nhị phân)**. Nó khác với source compatibility:

- Source compatibility hỏi mã nguồn client cũ có biên dịch lại được với API mới hay không.
- Binary compatibility hỏi bytecode client đã biên dịch có tiếp tục liên kết và chạy với API mới hay không.
- Behavioral compatibility hỏi chương trình có tiếp tục cho kết quả và tác dụng phụ đúng như trước hay không.

Ba khía cạnh này có thể cho kết quả khác nhau. Một thay đổi có thể không làm đổi descriptor nhưng vẫn làm hành vi thay đổi; một thay đổi có thể khiến mã nguồn không biên dịch lại được nhưng bytecode cũ vẫn liên kết; và một thay đổi khác có thể làm bytecode cũ ném `NoSuchMethodError` dù mã nguồn thư viện mới hoàn toàn hợp lệ.

Trong migration Java, cần đặc biệt chú ý ba nhóm thay đổi:

1. Thay đổi kiểu, số lượng hoặc thứ tự tham số của method.
2. Thay đổi kiểu trả về của method.
3. Thêm, xóa hoặc thay đổi constructor.

Bài này giải thích cách JVM nhận diện method/constructor, các trường hợp phá vỡ tương thích, những ngoại lệ cần hiểu như bridge method và type erasure, cách chẩn đoán lỗi và cách thiết kế lộ trình chuyển đổi API.

## 2. Method descriptor trong JVM

### 2.1. Descriptor mô tả tham số và kiểu trả về

Trong class file, một method được mô tả bằng tên và descriptor. Descriptor thể hiện kiểu của tất cả tham số theo thứ tự, sau đó là kiểu trả về. Ví dụ:

| Khai báo Java | Descriptor JVM |
| --- | --- |
| `int size()` | `()I` |
| `String name()` | `()Ljava/lang/String;` |
| `int parse(String text)` | `(Ljava/lang/String;)I` |
| `void save(long id, String value)` | `(JLjava/lang/String;)V` |
| `boolean contains(int[] values, int target)` | `([II)Z` |

Một số ký hiệu kiểu cơ bản:

| Kiểu Java | Ký hiệu descriptor |
| --- | --- |
| `void` | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| Kiểu tham chiếu, ví dụ `java.lang.String` | `Ljava/lang/String;` |
| Mảng `int[]` | `[I` |
| Mảng `String[]` | `[Ljava/lang/String;` |

Descriptor method có dạng tổng quát:

```text
(parameter-descriptors)return-descriptor
```

Ví dụ `public int add(int left, int right)` có descriptor `(II)I`. Method `public void print(String value)` có descriptor `(Ljava/lang/String;)V`.

### 2.2. Tên tham số không nằm trong descriptor

Đổi tên tham số trong mã nguồn:

```java
public void setName(String name) { ... }
```

thành:

```java
public void setName(String displayName) { ... }
```

không làm thay đổi descriptor `(Ljava/lang/String;)V`. Vì thế, việc đổi tên tham số đơn thuần không phá vỡ liên kết nhị phân. Tên tham số có thể xuất hiện trong metadata nếu biên dịch với `-parameters`, và reflection hoặc công cụ tài liệu có thể quan sát metadata đó, nhưng JVM không dùng tên tham số để phân giải lời gọi method.

Điều này không áp dụng cho kiểu tham số. Đổi `String` thành `CharSequence` làm descriptor thay đổi, dù cả hai đều là kiểu tham chiếu và `String` triển khai `CharSequence`.

### 2.3. Kiểu trả về cũng nằm trong descriptor

Một điểm quan trọng là descriptor JVM bao gồm cả kiểu trả về. Ví dụ:

```java
public int calculate(String input)
```

có descriptor `(Ljava/lang/String;)I`, còn:

```java
public long calculate(String input)
```

có descriptor `(Ljava/lang/String;)J`.

Trong mã nguồn Java, không thể khai báo hai method cùng tên và cùng kiểu tham số chỉ khác kiểu trả về để tạo overload. Nhưng ở cấp bytecode, kiểu trả về vẫn là một phần của descriptor mà client đã biên dịch tham chiếu.

### 2.4. Constructor có tên đặc biệt `<init>`

Constructor được biểu diễn trong class file bằng tên đặc biệt `<init>`. Descriptor của constructor chứa danh sách tham số và luôn có kiểu trả về `V` (void), vì constructor không trả về giá trị theo cú pháp Java.

Ví dụ:

| Khai báo Java | Descriptor JVM |
| --- | --- |
| `new Customer()` | `<init>()V` |
| `new Customer(String name)` | `<init>(Ljava/lang/String;)V` |
| `new Customer(long id, String name)` | `<init>(JLjava/lang/String;)V` |

Khi client gọi `new Customer()`, bytecode tham chiếu constructor `<init>()V`. Nếu phiên bản thư viện mới không còn constructor đó, JVM không tự chuyển lời gọi sang constructor nhận tham số khác.

## 3. Thay đổi kiểu tham số

### 3.1. Đổi kiểu tham số làm descriptor thay đổi

Giả sử phiên bản thư viện 1 có:

```java
package com.example;

public class PriceCalculator {
    public int calculate(String amount) {
        return Integer.parseInt(amount);
    }
}
```

Client biên dịch với API này:

```java
PriceCalculator calculator = new PriceCalculator();
int result = calculator.calculate("120");
```

Bytecode client tham chiếu method `calculate` với descriptor `(Ljava/lang/String;)I`.

Nếu thư viện phiên bản 2 đổi method thành:

```java
public int calculate(CharSequence amount) {
    return Integer.parseInt(amount.toString());
}
```

descriptor mới là `(Ljava/lang/CharSequence;)I`. Khi chạy client cũ với thư viện mới, JVM tìm method theo descriptor cũ nhưng không tìm thấy. Khi lời gọi được liên kết, chương trình có thể ném `NoSuchMethodError`.

Mã nguồn client nếu được biên dịch lại có thể vẫn chạy vì `String` là subtype của `CharSequence`. Tuy nhiên, điều đó không cứu bytecode đã biên dịch trước đó. Đây là ví dụ điển hình cho trường hợp source compatibility và binary compatibility cho kết quả khác nhau.

### 3.2. Đổi kiểu primitive cũng phá vỡ descriptor

Các kiểu primitive có ký hiệu descriptor riêng. Đổi tham số `int` thành `long` làm descriptor đổi từ `I` sang `J`:

```java
// Phiên bản 1
public void setTimeout(int seconds) { ... }

// Phiên bản 2
public void setTimeout(long seconds) { ... }
```

Bytecode cũ gọi `setTimeout(I)V`; method mới có descriptor `(J)V`. JVM không thực hiện phép widening `int` sang `long` trong bước liên kết method để tìm một descriptor thay thế. Compiler có thể tự chuyển `int` sang `long` khi biên dịch lại mã nguồn, nhưng bytecode cũ vẫn tham chiếu chữ ký cũ.

Tương tự, đổi `Integer` thành `int`, `double` thành `BigDecimal`, hoặc `byte[]` thành `ByteBuffer` đều làm descriptor thay đổi.

### 3.3. Đổi số lượng hoặc thứ tự tham số

Thay đổi số lượng hoặc thứ tự tham số cũng làm descriptor thay đổi:

```java
// Phiên bản 1
public void transfer(String source, String destination) { ... }

// Phiên bản 2
public void transfer(String source, String destination, boolean overwrite) { ... }
```

Descriptor cũ là `(Ljava/lang/String;Ljava/lang/String;)V`, descriptor mới là `(Ljava/lang/String;Ljava/lang/String;Z)V`. Bytecode client cũ vẫn gọi descriptor hai tham số và có thể nhận `NoSuchMethodError` nếu method cũ đã bị xóa.

Đổi thứ tự hai tham số có cùng kiểu có thể không làm descriptor thay đổi:

```java
public void move(String source, String destination)
```

và:

```java
public void move(String destination, String source)
```

đều có descriptor `(Ljava/lang/String;Ljava/lang/String;)V`. Bytecode vẫn liên kết được, nhưng ý nghĩa hai tham số có thể bị đảo. Đây là thay đổi hành vi nguy hiểm: compiler và JVM không biết tên hoặc ý định nghiệp vụ của tham số. Kiểm thử hành vi và review API là cần thiết ngay cả khi descriptor không đổi.

### 3.4. Thêm overload thường giữ được binary compatibility

Nếu phiên bản mới giữ method cũ và thêm overload:

```java
public void transfer(String source, String destination) {
    transfer(source, destination, false);
}

public void transfer(String source, String destination, boolean overwrite) {
    // Implementation mới
}
```

descriptor cũ vẫn tồn tại nên bytecode client cũ có thể tiếp tục liên kết. Client mới có thể dùng overload mới.

Tuy nhiên, thêm overload có thể ảnh hưởng source compatibility vì lời gọi lambda, method reference, `null` hoặc generic inference có thể trở nên mơ hồ hoặc được phân giải sang overload khác. Vì thế, thêm overload thường an toàn hơn xóa/đổi method cũ ở cấp binary, nhưng vẫn cần xem xét tác động khi consumer biên dịch lại.

### 3.5. Varargs và mảng

Trong bytecode, tham số varargs được biểu diễn bằng kiểu mảng. Ví dụ:

```java
public void log(String... messages)
```

có descriptor tương ứng với một tham số `String[]`: `([Ljava/lang/String;)V`. Việc thay cú pháp varargs thành khai báo mảng cùng kiểu có thể giữ descriptor nhị phân, dù có thể thay đổi cách gọi trong mã nguồn và metadata `ACC_VARARGS`.

Ngược lại, đổi `String...` thành `Object...` làm descriptor đổi từ `([Ljava/lang/String;)V` sang `([Ljava/lang/Object;)V`, do đó không còn là cùng một chữ ký nhị phân.

## 4. Thay đổi kiểu trả về

### 4.1. Đổi kiểu trả về làm descriptor thay đổi

Giả sử thư viện phiên bản 1 có:

```java
public class Account {
    public int balance() {
        return 100;
    }
}
```

Client đã biên dịch gọi method với descriptor `()I`.

Nếu phiên bản 2 đổi thành:

```java
public long balance() {
    return 100L;
}
```

descriptor mới là `()J`. Dù `int` có thể được widening thành `long` khi biên dịch lại mã nguồn, JVM không tìm method `()J` để thay cho lời gọi `()I` của bytecode cũ. Kết quả có thể là `NoSuchMethodError`.

Đổi từ kiểu tham chiếu này sang kiểu tham chiếu khác cũng làm descriptor thay đổi:

```java
// Trước
public Number value() { ... }

// Sau
public Integer value() { ... }
```

Descriptor chuyển từ `()Ljava/lang/Number;` sang `()Ljava/lang/Integer;`. Sự kiện `Integer` là subtype của `Number` không khiến descriptor cũ tự động khớp descriptor mới.

### 4.2. Không thể overload chỉ bằng kiểu trả về

Java không cho phép khai báo:

```java
public int value() { ... }
public long value() { ... } // Lỗi: cùng tên và cùng tham số
```

Do đó, khi cần chuyển đổi kiểu trả về mà vẫn giữ binary compatibility, không thể chỉ thêm một method cùng tên và cùng tham số với kiểu trả về mới. Các lựa chọn thường dùng là:

- Giữ method cũ và thêm method mới với tên khác, ví dụ `balance()` và `balanceAsLong()`.
- Giữ method cũ, thêm overload có tham số phân biệt được nếu thiết kế API hợp lý.
- Tạo API mới hoặc interface phiên bản mới, có adapter cho consumer cũ.
- Nếu có thể, giữ kiểu trả về cũ và chuyển đổi nội bộ, trong khi cung cấp một API mới cho kiểu dữ liệu mở rộng.

Ví dụ:

```java
public class Account {
    /** @deprecated Use balanceAsLong() for the expanded range. */
    @Deprecated
    public int balance() {
        return Math.toIntExact(balanceAsLong());
    }

    public long balanceAsLong() {
        return 100L;
    }
}
```

Ví dụ này giữ descriptor `balance()I` để client cũ tiếp tục liên kết. `Math.toIntExact` ném `ArithmeticException` nếu giá trị vượt phạm vi `int`, vì vậy hành vi cần được tài liệu hóa và kiểm thử. Nếu không thể bảo đảm giá trị nằm trong phạm vi cũ, việc giữ method cũ có thể cần một chiến lược tương thích khác.

### 4.3. Thay đổi `void` sang kiểu có giá trị

Đổi:

```java
public void refresh() { ... }
```

sang:

```java
public boolean refresh() { ... }
```

làm descriptor đổi từ `()V` sang `()Z`. Client cũ được biên dịch với lời gọi `refresh()V`; method mới không có descriptor đó nên binary linkage bị phá vỡ.

Một số người nghĩ rằng client cũ chỉ bỏ qua giá trị trả về nên có thể tiếp tục chạy. Nhưng bytecode không chỉ tìm theo tên và tham số; kiểu trả về nằm trong descriptor. Nếu muốn giữ client cũ, có thể giữ `void refresh()` và cung cấp method mới với tên khác như `refreshAndReport()`.

### 4.4. Covariant return type và bridge method

Java cho phép method override trả về một kiểu tham chiếu cụ thể hơn kiểu trả về của method được override. Đây gọi là covariant return type.

```java
class Document { }
class PdfDocument extends Document { }

class BaseFactory {
    public Document create() {
        return new Document();
    }
}

class PdfFactory extends BaseFactory {
    @Override
    public PdfDocument create() {
        return new PdfDocument();
    }
}
```

Ở cấp mã nguồn, override này hợp lệ vì `PdfDocument` là subtype của `Document`. Nhưng descriptor của method ở hai lớp khác nhau: lớp cha có `()LDocument;`, lớp con khai báo method trả `()LPdfDocument;`.

Compiler Java thường sinh một **bridge method** trong lớp con để duy trì hợp đồng nhị phân của method cha. Bridge có descriptor trả `Document`, sau đó gọi method trả `PdfDocument`. Có thể quan sát method bridge/synthetic bằng `javap -v`.

Bridge method cũng xuất hiện trong nhiều tình huống generic do type erasure. Tuy nhiên, không nên suy luận rằng mọi thay đổi kiểu trả về của một API public đều tự động được bridge bảo vệ. Covariant return trong quan hệ override là một quy tắc ngôn ngữ cụ thể; thay đổi chữ ký method độc lập trong thư viện vẫn có thể phá vỡ binary compatibility.

## 5. Thay đổi constructor

### 5.1. Constructor là một lời gọi nhị phân riêng

Khi client viết:

```java
Customer customer = new Customer();
```

bytecode về cơ bản thực hiện cấp phát object rồi gọi constructor `<init>()V` bằng `invokespecial`. Nếu class phiên bản mới không còn constructor không tham số, lời gọi cũ không thể tự chuyển sang constructor khác.

Ví dụ phiên bản 1:

```java
public class Customer {
    public Customer() {
    }
}
```

Phiên bản 2:

```java
public class Customer {
    public Customer(String name) {
        // Khởi tạo customer
    }
}
```

Khi một class đã khai báo constructor có tham số, compiler không tự tạo constructor mặc định không tham số. Client cũ gọi `<init>()V` có thể nhận `NoSuchMethodError` khi chạy với class mới.

### 5.2. Thêm constructor overload

Thêm constructor mới mà vẫn giữ constructor cũ thường giữ binary compatibility:

```java
public class Customer {
    public Customer() {
        this("Unknown");
    }

    public Customer(String name) {
        // Khởi tạo customer
    }
}
```

Client cũ tiếp tục gọi `<init>()V`; client mới có thể gọi `<init>(Ljava/lang/String;)V`. Constructor cũ có thể được đánh dấu `@Deprecated` để hướng consumer chuyển dần.

Tuy nhiên, thêm constructor có thể làm mã nguồn trở nên mơ hồ. Ví dụ, khi có hai constructor nhận hai kiểu tham chiếu không liên quan, lời gọi `new Customer(null)` có thể không còn chọn được một overload duy nhất. Do đó, cần kiểm tra cả source compatibility của các consumer sẽ biên dịch lại.

### 5.3. Đổi kiểu hoặc thứ tự tham số constructor

Constructor không có tên tùy ý để dùng làm cơ chế overload khác. Thay đổi kiểu hoặc thứ tự tham số làm descriptor `<init>` đổi:

```java
// Trước
public Customer(String name, int age) { ... }

// Sau
public Customer(String name, long age) { ... }
```

Descriptor cũ là `<init>(Ljava/lang/String;I)V`, descriptor mới là `<init>(Ljava/lang/String;J)V`. Client cũ cần constructor cũ và có thể lỗi liên kết.

Nếu thứ tự tham số cùng kiểu bị đảo, descriptor có thể không đổi nhưng semantics thay đổi. Ví dụ hai tham số `String` đảo thứ tự vẫn có cùng descriptor. Compiler và JVM không nhận biết ý nghĩa `source` hay `destination`; chỉ test và hợp đồng API mới phát hiện lỗi.

### 5.4. Constructor visibility và constructor kế thừa

Constructor không được kế thừa như method instance. Mỗi lớp có các constructor riêng. Khi thay đổi khả năng truy cập từ `public` sang `protected` hoặc package-private, client ở package khác có thể không biên dịch lại được; bytecode cũ có thể gặp `IllegalAccessError` khi JVM kiểm tra quyền truy cập.

Thay đổi constructor của lớp cha cũng có thể làm constructor lớp con không còn biên dịch nếu lời gọi `super(...)` không còn khớp. Khi xây dựng thư viện có hệ sinh thái subclass bên ngoài, cần xem constructor được gọi từ mã nguồn subclass như một phần hợp đồng API.

### 5.5. Thêm tham số constructor và factory method

Nếu constructor cần thêm cấu hình, không nhất thiết phải xóa constructor cũ. Có thể giữ constructor cũ gọi constructor mới:

```java
public class HttpClientConfig {
    public HttpClientConfig(String endpoint) {
        this(endpoint, Duration.ofSeconds(10));
    }

    public HttpClientConfig(String endpoint, Duration timeout) {
        // Validate và lưu cấu hình
    }
}
```

Khi số lượng tham số tăng nhiều, factory method hoặc builder có thể giúp API dễ mở rộng hơn:

```java
HttpClientConfig config = HttpClientConfig.builder()
        .endpoint("https://service.example")
        .timeout(Duration.ofSeconds(10))
        .build();
```

Đây là thay đổi thiết kế API; nếu chuyển từ constructor cũ sang builder, vẫn cần giữ constructor cũ trong giai đoạn tương thích hoặc phát hành một major version có lộ trình rõ.

## 6. Generic type, type erasure và descriptor

### 6.1. Generic argument thường bị xóa khỏi descriptor

Java dùng type erasure để triển khai generics. Descriptor JVM thường chứa kiểu đã xóa (erased type), không chứa đầy đủ tham số generic.

Ví dụ:

```java
public void setNames(List<String> names) { ... }
```

và:

```java
public void setNames(List<Integer> names) { ... }
```

đều có descriptor method là `(Ljava/util/List;)V`, vì cả hai tham số đều bị xóa thành `List`.

Do đó, thay `List<String>` thành `List<Integer>` có thể không làm descriptor thay đổi và bytecode cũ vẫn liên kết. Nhưng thay đổi này có thể phá source compatibility hoặc gây lỗi runtime do code cũ giả định phần tử là `String` trong khi thư viện mới cung cấp `Integer`.

Ví dụ client cũ:

```java
List<String> names = service.names();
String first = names.get(0);
```

Nếu implementation mới thực tế trả về `List<Integer>` nhưng vẫn giữ descriptor erased là `()Ljava/util/List;`, lời gọi có thể liên kết; khi compiler-generated cast sang `String` được thực thi, client có thể nhận `ClassCastException`.

### 6.2. Thay đổi bound có thể làm erasure thay đổi

Xét method:

```java
public <T> T value() { ... }
```

Nếu không có bound cụ thể, erasure của `T` thường là `Object`. Đổi thành:

```java
public <T extends Number> T value() { ... }
```

thì erasure của `T` trở thành `Number`. Descriptor có thể đổi từ `()Ljava/lang/Object;` sang `()Ljava/lang/Number;`, gây tác động binary.

Vì vậy, khi thay đổi generic API, không chỉ so sánh cách viết `T` trong mã nguồn. Cần xác định erasure của type variable, parameterized type, array và bound trước/sau.

### 6.3. Generic signature và reflection

Class file có thể lưu generic signature trong attribute `Signature` bên cạnh descriptor đã xóa. Compiler Java dùng thông tin generic khi biên dịch lại source; reflection có thể đọc generic type qua các API như `getGenericParameterTypes()` hoặc `getGenericReturnType()`.

Vì vậy, thay generic argument có thể không phá JVM linkage nhưng vẫn ảnh hưởng source consumer, reflection-based framework, dependency injection, serializer hoặc công cụ sinh mã. Binary compatibility theo descriptor không bao quát toàn bộ metadata mà framework có thể sử dụng.

## 7. Những thay đổi khác có thể ảnh hưởng dù descriptor giữ nguyên

Không phải mọi rủi ro đều thể hiện bằng một descriptor khác.

### 7.1. Đổi thứ tự tham số cùng kiểu

Như đã nêu, `send(String from, String to)` và `send(String to, String from)` có descriptor giống nhau. Client cũ liên kết bình thường nhưng dữ liệu có thể bị đảo. Đây là thay đổi hành vi, không phải linkage failure.

### 7.2. Đổi `static` thành instance hoặc ngược lại

Descriptor không mã hóa trực tiếp modifier `static`, nhưng bytecode client dùng opcode khác nhau cho lời gọi static và instance (`invokestatic` so với `invokevirtual`/`invokeinterface`). Nếu thay method instance thành static hoặc ngược lại, client cũ có thể gặp `IncompatibleClassChangeError`.

### 7.3. Đổi quyền truy cập

Đổi `public` thành `protected` hoặc package-private có thể khiến client cũ không còn quyền gọi method/constructor và gây `IllegalAccessError`. Đổi quyền truy cập cũng có thể làm source client không biên dịch lại được.

### 7.4. Thay đổi `throws`

Danh sách checked exception không nằm trong JVM method descriptor. Vì thế, thêm hoặc bỏ `throws IOException` không tự làm descriptor đổi. Tuy nhiên, source client biên dịch lại có thể phải bắt exception mới hoặc có thể nhận warning/khác biệt từ API contract. Runtime implementation vẫn có thể ném exception không được khai báo; JVM không dùng `throws` để phân giải method.

### 7.5. Thay đổi nullability hoặc semantics

Đổi hợp đồng từ chấp nhận `null` sang từ chối `null`, thay giá trị mặc định hoặc thay cách xử lý input không hợp lệ có thể giữ nguyên descriptor nhưng phá behavioral compatibility. Những thay đổi này cần test contract và release note.

## 8. Các lỗi runtime thường gặp

| Lỗi | Nguyên nhân thường gặp | Liên hệ với thay đổi chữ ký |
| --- | --- | --- |
| `NoSuchMethodError` | Bytecode tham chiếu method/constructor không còn có descriptor phù hợp trong runtime class | Xóa method cũ, đổi kiểu tham số/return hoặc constructor |
| `IncompatibleClassChangeError` | Cấu trúc class thay đổi theo cách không phù hợp với bytecode cũ | Đổi static/instance, class/interface hoặc thay đổi loại thành viên |
| `IllegalAccessError` | Bytecode gọi thành viên không còn truy cập được | Giảm visibility của method/constructor hoặc thay đổi module access |
| `AbstractMethodError` | Runtime class không cung cấp implementation phù hợp cho method mà caller cần | Thay đổi interface/abstract contract hoặc triển khai không đồng bộ |
| `ClassCastException` | Kiểu thực tế không khớp với cast được compiler chèn vào bytecode | Thay generic contract nhưng giữ erased descriptor, thay semantics dữ liệu |
| `NoSuchMethodException` | Reflection không tìm được method theo tên và kiểu tham số yêu cầu | API bị đổi; khác với `NoSuchMethodError` ở linkage bytecode |

`NoSuchMethodError` và `NoSuchMethodException` không giống nhau. Lỗi đầu là `Error` xảy ra khi JVM liên kết một lời gọi bytecode; lỗi sau là checked exception từ API reflection khi chương trình chủ động tìm method bằng `Class.getMethod()` hoặc `getDeclaredMethod()`.

Khi có lỗi linkage, không nên chỉ thêm một dependency khác hoặc xóa cache. Trước hết cần xác định class nào đang được nạp, bytecode tham chiếu descriptor nào và runtime classpath thực tế chứa phiên bản API nào.

## 9. Chẩn đoán bằng `javap` và công cụ phân tích API

### 9.1. Xem descriptor trong class file

`javap -s` hiển thị descriptor của method và constructor. Ví dụ:

```bash
javap -classpath library-v1.jar -s com.example.PriceCalculator
javap -classpath library-v2.jar -s com.example.PriceCalculator
```

So sánh output để xem descriptor nào đã thay đổi hoặc bị loại bỏ. Với thông tin chi tiết hơn:

```bash
javap -classpath library-v1.jar -p -s -c -v com.example.PriceCalculator
```

- `-p` hiển thị cả thành viên không public.
- `-s` hiển thị descriptor.
- `-c` hiển thị bytecode của method.
- `-v` hiển thị thông tin chi tiết như flags, bridge/synthetic method và attributes.

### 9.2. Xem lời gọi mà client đã biên dịch tham chiếu

Sau khi biên dịch client với thư viện phiên bản 1, kiểm tra bytecode:

```bash
javap -classpath client-classes:library-v1.jar -c -v com.example.Client
```

Tìm lệnh `invokevirtual`, `invokeinterface`, `invokestatic` hoặc `invokespecial` và mục constant pool liên quan. Phần tham chiếu sẽ cho biết owner, tên method và descriptor mà client cần ở runtime.

Trên Windows, dấu phân cách classpath là dấu chấm phẩy (`;`) thay cho dấu hai chấm (`:`). Có thể chạy lệnh trên class file của client với classpath phù hợp với môi trường.

### 9.3. Kiểm thử client cũ với thư viện mới

Một phép thử binary compatibility quan trọng là:

1. Biên dịch client một lần với library v1.
2. Giữ nguyên bytecode client đã tạo.
3. Chạy client với library v2 trên runtime classpath.
4. Ghi nhận lỗi liên kết hoặc hành vi thay đổi.

Không biên dịch lại client giữa bước 2 và bước 3. Nếu biên dịch lại, compiler sẽ dùng API mới và phép thử không còn kiểm tra bytecode cũ.

Ví dụ cấu trúc thư mục:

```text
compat-check/
  library-v1.jar
  library-v2.jar
  client-classes/
```

Lệnh chạy minh họa:

```bash
java -cp client-classes:library-v2.jar com.example.Client
```

### 9.4. Công cụ so sánh API

Trong dự án thư viện, có thể tích hợp công cụ so sánh API như japicmp hoặc Revapi để phát hiện thay đổi public/protected API giữa hai artifact. Các công cụ này hỗ trợ phát hiện nhiều dạng breaking change trong chữ ký, class hierarchy và visibility.

Kết quả tự động cần được review theo policy của dự án. Công cụ so sánh API không thể tự quyết định một thay đổi hành vi có chấp nhận được hay không, và không phải mọi metadata mà framework sử dụng đều được đánh giá đầy đủ bằng một cấu hình mặc định.

## 10. Chiến lược giữ tương thích khi cần thay đổi API

### 10.1. Giữ method cũ và thêm method mới

Nếu thay đổi tham số, có thể giữ method cũ làm adapter:

```java
public class ReportService {
    /** @deprecated Use export(Path, ExportOptions). */
    @Deprecated
    public void export(String fileName) {
        export(Path.of(fileName), ExportOptions.defaults());
    }

    public void export(Path path, ExportOptions options) {
        // Implementation mới
    }
}
```

Client cũ tiếp tục liên kết với `export(String)`. Client mới dùng `export(Path, ExportOptions)`. Adapter cần chuyển đổi dữ liệu theo quy tắc rõ ràng, bao gồm encoding, đường dẫn tương đối, quyền truy cập và lỗi I/O.

### 10.2. Giữ constructor cũ và ủy quyền sang constructor mới

```java
public class ReportService {
    /** @deprecated Use the constructor with options. */
    @Deprecated
    public ReportService(Path outputDirectory) {
        this(outputDirectory, ExportOptions.defaults());
    }

    public ReportService(Path outputDirectory, ExportOptions options) {
        // Validate và khởi tạo
    }
}
```

Constructor cũ tiếp tục tồn tại với descriptor ban đầu. Việc ủy quyền qua `this(...)` giúp giữ một nơi khởi tạo chính, tránh logic giữa các constructor bị lệch.

### 10.3. Giữ kiểu trả về cũ bằng method chuyển tiếp

Vì Java không cho overload chỉ bằng return type, dùng tên method mới:

```java
public int count() {
    return Math.toIntExact(countLong());
}

public long countLong() {
    // Tính số lượng đầy đủ
    return 0L;
}
```

Nếu method cũ có thể không biểu diễn được mọi giá trị mới, phải xác định rõ hành vi khi vượt phạm vi. Không nên âm thầm cắt cụt hoặc wrap số để giữ tương thích.

### 10.4. Dùng interface hoặc API phiên bản mới khi thay đổi quá rộng

Nếu nhiều method và constructor cùng thay đổi, việc giữ hàng loạt adapter có thể làm API khó hiểu. Khi đó có thể tạo interface/class mới, ví dụ `ClientV2`, hoặc một package API mới, sau đó cung cấp adapter giữa thế hệ cũ và mới trong thời gian chuyển tiếp.

Chiến lược này phù hợp khi hợp đồng dữ liệu, lifecycle hoặc semantics thay đổi sâu. Cần xác định thời gian hỗ trợ song song, cách chuyển consumer và thời điểm loại bỏ API cũ.

## 11. Lập kế hoạch migration theo loại thay đổi

### 11.1. Khi thay đổi tham số

1. Lấy descriptor cũ và mới bằng `javap` hoặc API diff.
2. Xác định tất cả client đã biên dịch và consumer cần biên dịch lại.
3. Kiểm tra kiểu primitive/reference, generic erasure, thứ tự tham số và null semantics.
4. Nếu cần giữ binary compatibility, duy trì method cũ và ủy quyền sang implementation mới.
5. Kiểm tra overload resolution của source consumer, đặc biệt lời gọi với `null`, lambda và method reference.
6. Chạy test client cũ với thư viện mới và contract test cho consumer mới.

### 11.2. Khi thay đổi kiểu trả về

1. Xác định descriptor cũ và mới; nhớ rằng return type nằm trong JVM descriptor.
2. Xem xét covariant return trong quan hệ override và bridge method do compiler sinh ra.
3. Nếu method độc lập cần đổi kiểu trả về, không cố thêm overload cùng tên/cùng tham số.
4. Cân nhắc method mới với tên khác hoặc interface/API thế hệ mới.
5. Nếu giữ method cũ, xác định phép chuyển đổi có mất dữ liệu, overflow hoặc thay đổi nullability không.
6. Kiểm thử bytecode client cũ và source consumer sau khi biên dịch lại.

### 11.3. Khi thay đổi constructor

1. Liệt kê mọi descriptor `<init>` hiện có và các constructor được consumer gọi.
2. Giữ constructor cũ nếu cần binary compatibility.
3. Thêm overload mới hoặc factory/builder cho cấu hình mở rộng.
4. Dùng `this(...)` để tập trung logic khởi tạo.
5. Kiểm tra visibility và khả năng biên dịch của subclass bên ngoài.
6. Kiểm tra lời gọi có `null`, literal số và overload mới để tránh source ambiguity.

### 11.4. Đặt tiêu chí phát hành rõ ràng

Với thư viện public, release note nên ghi:

- Thành viên nào đã đổi descriptor.
- API cũ còn tồn tại hay đã bị loại bỏ.
- Có bridge method hoặc adapter nào được sinh/cung cấp.
- Consumer cần biên dịch lại hay có thể dùng bytecode cũ.
- Mức Java/JDK tối thiểu của artifact mới.
- Những thay đổi hành vi hoặc giới hạn chuyển đổi.
- Phiên bản cuối cùng dự kiến hỗ trợ API cũ.

Không nên chỉ ghi “breaking changes in API” mà không nêu method/constructor cụ thể. Consumer cần biết chính xác call site nào phải sửa và cách chuyển đổi.

## 12. Ví dụ tổng hợp: nâng cấp thư viện từ phiên bản 1 lên phiên bản 2

Giả sử thư viện phiên bản 1 có:

```java
public class FileRecord {
    public FileRecord() { }

    public void setSize(int size) { }

    public int size() { return 0; }
}
```

Client cũ:

```java
FileRecord record = new FileRecord();
record.setSize(120);
int size = record.size();
```

Phiên bản 2 thay đổi đồng thời:

```java
public class FileRecord {
    public FileRecord(Path source) { }

    public void setSize(long size) { }

    public long size() { return 0L; }
}
```

Ba thay đổi đều tác động đến descriptor:

| Thành viên | Descriptor v1 | Descriptor v2 | Rủi ro với client cũ |
| --- | --- | --- | --- |
| Constructor | `<init>()V` | `<init>(Ljava/nio/file/Path;)V` | `NoSuchMethodError` khi tạo `FileRecord` |
| `setSize` | `(I)V` | `(J)V` | `NoSuchMethodError` khi gọi `setSize(int)` |
| `size` | `()I` | `()J` | `NoSuchMethodError` khi gọi `size()` |

Nếu muốn giữ tương thích nhị phân, phiên bản 2 có thể giữ các thành viên cũ:

```java
public class FileRecord {
    @Deprecated
    public FileRecord() {
        this(Path.of("."));
    }

    public FileRecord(Path source) {
        // Khởi tạo từ source
    }

    @Deprecated
    public void setSize(int size) {
        setSize((long) size);
    }

    public void setSize(long size) {
        // Lưu size
    }

    @Deprecated
    public int size() {
        return Math.toIntExact(sizeLong());
    }

    public long sizeLong() {
        // Trả về size đầy đủ
        return 0L;
    }
}
```

Ví dụ này giữ descriptor cũ cho constructor, setter và getter. Tuy nhiên, nó cần quyết định rõ cách constructor mặc định chọn `Path`, và cách `size()` xử lý giá trị vượt phạm vi `int`. Nếu những quyết định đó không phù hợp với hợp đồng cũ, không nên giả vờ rằng adapter là tương đương hoàn toàn. Có thể cần một major release có breaking change được công bố rõ ràng.

## 13. Checklist kiểm tra binary compatibility

Khi review thay đổi public/protected API, hãy xem xét:

- [ ] Method cũ có còn tồn tại với cùng tên và descriptor không?
- [ ] Kiểu primitive/reference của từng tham số có thay đổi không?
- [ ] Số lượng hoặc thứ tự tham số có thay đổi không?
- [ ] Kiểu trả về có thay đổi không?
- [ ] Generic erasure và bound có làm descriptor thay đổi không?
- [ ] Constructor cũ có còn tồn tại với descriptor `<init>` cũ không?
- [ ] Visibility và modifier `static` có thay đổi không?
- [ ] Có bridge method cần thiết cho override/covariant return không?
- [ ] Thêm overload có gây source ambiguity cho `null`, lambda hoặc method reference không?
- [ ] Client đã biên dịch với phiên bản cũ có chạy được với artifact mới không?
- [ ] Runtime classpath thực tế có đúng artifact mới dự kiến không?
- [ ] Các thay đổi semantics, nullability và dữ liệu có contract test không?

Checklist này hỗ trợ review; bằng chứng quan trọng nhất vẫn là API diff và phép thử client cũ với thư viện mới trong một classpath được kiểm soát.

## 14. Những sai lầm thường gặp

**Cho rằng kiểu trả về không nằm trong descriptor.** Trong JVM, kiểu trả về là một phần của method descriptor. Đổi `int` thành `long` hoặc `void` thành `boolean` có thể làm client cũ không liên kết được.

**Cho rằng JVM tự widening tham số hoặc kết quả khi liên kết.** Compiler có thể chèn phép chuyển đổi khi biên dịch lại source, nhưng JVM không thay descriptor cũ bằng một descriptor gần giống.

**Xóa constructor không tham số mà quên client đã biên dịch.** Khi class khai báo constructor khác, constructor mặc định không còn tự được sinh. Hãy giữ constructor cũ hoặc phát hành breaking change có lộ trình.

**Cho rằng generic argument luôn có mặt trong descriptor.** Type erasure có thể khiến `List<String>` và `List<Integer>` có cùng descriptor. Linkage có thể thành công nhưng source/reflection/behavior vẫn hỏng.

**Cho rằng cùng descriptor nghĩa là cùng hành vi.** Đổi ý nghĩa thứ tự tham số cùng kiểu hoặc đổi semantics có thể giữ descriptor mà làm sai dữ liệu.

**Chỉ chạy test sau khi biên dịch lại toàn bộ client.** Biên dịch lại sẽ che giấu nhiều lỗi binary compatibility. Cần giữ bytecode client cũ và thay đúng thư viện runtime.

**Nhầm `NoSuchMethodError` với `NoSuchMethodException`.** Một lỗi là JVM linkage của bytecode; lỗi kia là kết quả tìm method qua reflection.

**Dùng bridge method như lời giải chung cho mọi thay đổi return type.** Bridge chủ yếu phục vụ override covariant và generic erasure; nó không tự bảo vệ mọi method public bị đổi chữ ký.

## 15. Kết luận

Tham số, kiểu trả về và constructor là một phần trực tiếp của hợp đồng nhị phân. JVM liên kết lời gọi bằng tên thành viên và descriptor, trong đó method descriptor chứa cả kiểu tham số lẫn kiểu trả về, còn constructor dùng tên đặc biệt `<init>` và luôn có descriptor trả `V`. Vì vậy, đổi kiểu tham số, số lượng tham số, return type hoặc xóa constructor có thể làm bytecode client cũ gặp lỗi linkage.

Khi cần duy trì tương thích, chiến lược thường dùng là giữ descriptor cũ, thêm API mới và chuyển tiếp qua adapter hoặc constructor delegation. Với thay đổi return type, Java không cho overload chỉ bằng kiểu trả về nên thường cần tên method mới hoặc API thế hệ mới. Cuối cùng, hãy kiểm tra descriptor bằng `javap`, dùng công cụ API diff và chạy bytecode client cũ với thư viện mới để xác nhận binary compatibility trước khi phát hành.
