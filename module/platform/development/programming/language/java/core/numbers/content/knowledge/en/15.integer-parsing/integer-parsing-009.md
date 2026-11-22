# Integer.getInteger và Long.getLong: đọc system property, không phải parse thông thường

## 1. Điểm dễ nhầm nhất

Tên `Integer.getInteger(String)` và `Long.getLong(String)` khiến nhiều người nghĩ chúng là cách chuyển một chuỗi số thành `Integer` hay `Long`. **Đó là cách hiểu sai.**

Hai phương thức này nhận **tên của một Java system property**; chúng tìm **giá trị chuỗi được gán cho tên property đó**, sau đó giải mã giá trị tìm được thành số nguyên. Ngược lại, `Integer.parseInt(String)` và `Long.parseLong(String)` xử lý **chính nội dung chuỗi được truyền vào**.

~~~java
// Mã minh họa đặt trong một phương thức:
System.setProperty("app.retries", "5");

Integer retries = Integer.getInteger("app.retries");  // 5
int direct = Integer.parseInt("5");                    // 5

// Integer.getInteger("5") KHÔNG có nghĩa là parse số 5:
// Nó tìm system property có TÊN là "5".
~~~

Phân biệt hai vai trò của chuỗi:

- **Property key/name**: `"app.retries"` — tên khóa dùng để tìm cấu hình.
- **Property value**: `"5"` — văn bản chứa số, đọc được bằng `System.getProperty("app.retries")`.

Đối với `getInteger`/`getLong`, bước tra cứu **luôn xuất hiện trước bước giải mã số**. Không có property phù hợp thì mặc định kết quả `null` hoặc giá trị fallback do lập trình viên chỉ định.

## 2. Bảng phân biệt các API dễ lẫn

| API | Chuỗi tham số được hiểu là | Kiểu trả về | Phản ứng khi không có/sai dữ liệu |
| --- | --- | --- | --- |
| `Integer.parseInt("42")` | Chính văn bản số `"42"` | `int` | Ném `NumberFormatException` khi chuỗi không phải số nguyên hợp lệ |
| `Long.parseLong("42")` | Chính văn bản số `"42"` | `long` | Ném `NumberFormatException` nếu không parse được |
| `Integer.valueOf("42")` | Chính văn bản số `"42"` | `Integer` | Ném `NumberFormatException` khi không hợp lệ |
| `Long.valueOf("42")` | Chính văn bản số `"42"` | `Long` | Ném `NumberFormatException` khi không hợp lệ |
| `Integer.decode("0x2A")` | Chuỗi biểu diễn số có thể mang tiền tố radix | `Integer` | Ném `NumberFormatException` nếu không hợp lệ |
| `Long.decode("0x2A")` | Chuỗi biểu diễn số có thể mang tiền tố radix | `Long` | Ném `NumberFormatException` nếu không hợp lệ |
| `System.getProperty("app.port")` | **Tên** system property | `String` hoặc `null` | Trả về chuỗi property; không tự parse |
| `Integer.getInteger("app.port")` | **Tên** system property | `Integer` hoặc `null` | Không có/không giải mã được → `null` |
| `Long.getLong("app.limit")` | **Tên** system property | `Long` hoặc `null` | Không có/không giải mã được → `null` |

Các phương thức đọc property còn có overload nhận **giá trị mặc định**:

~~~java
Integer count = Integer.getInteger("app.count", 10);
Long limit = Long.getLong("app.limit", 1_000L);
~~~

Nếu property **không tồn tại hoặc không được giải mã thành số hợp lệ**, các overload này trả về wrapper chứa giá trị mặc định. Chúng không ghi mặc định đó vào danh sách system properties.

**Ghi chú quan trọng:** trong môi trường có cơ chế bảo vệ quyền truy cập property, thao tác đọc có thể phát sinh `SecurityException`. Giá trị mặc định không phải một cơ chế vượt qua hoặc vô hiệu hóa giới hạn truy cập.

## 3. System property là gì và lấy từ đâu?

Java system properties là tập hợp các cặp **khóa/giá trị chuỗi** thuộc tiến trình JVM. Ví dụ khóa `"java.version"` hoặc những khóa ứng dụng tự đặt như `"app.worker.count"`.

Có thể cung cấp giá trị khi khởi động JVM với tùy chọn `-Dkey=value`:

~~~bash
java -Dapp.retries=5 -Dapp.limit=0x100 MyApplication
~~~

Tại thời điểm chạy, ứng dụng có thể đọc:

~~~java
String text = System.getProperty("app.retries");
Integer retries = Integer.getInteger("app.retries");
Long limit = Long.getLong("app.limit");
~~~

Trong ví dụ lệnh trên:

- `text` là chuỗi `"5"`.
- `retries` là wrapper `Integer` mang giá trị `5`.
- `limit` là wrapper `Long` mang giá trị `256L` vì văn bản `0x100` được giải mã theo hệ 16.

Trong mã, ứng dụng còn có thể thay đổi property bằng `System.setProperty(key, value)` hoặc xóa bằng `System.clearProperty(key)`. System properties thường được chia sẻ trong **một tiến trình JVM**, không phải kho lưu trữ cấu hình trên hệ điều hành.

### System property khác environment variable

`System.getProperty("APP_PORT")` và `System.getenv("APP_PORT")` là **hai nguồn dữ liệu khác nhau**:

- `System.getProperty` đọc bảng Java system properties, thường từ `-D` hoặc do mã Java thiết lập.
- `System.getenv` đọc các biến môi trường tiến trình do hệ điều hành cấp.
- `Integer.getInteger` và `Long.getLong` **không tự đọc environment variable**.

~~~java
// Minh họa: hai lệnh đọc hai không gian khóa khác nhau.
String property = System.getProperty("APP_PORT");
String environment = System.getenv("APP_PORT");
~~~

Có thể thiết kế ứng dụng cho phép cả hai nguồn, nhưng phải triển khai chính sách ưu tiên/kiểm tra minh bạch; Java không tự động đổi khóa environment thành system property cho hai phương thức `getInteger`/`getLong`.

## 4. Cơ chế của Integer.getInteger

Về cách sử dụng, có thể hình dung `Integer.getInteger(name)` tương đương luồng xử lý sau:

1. Nhận chuỗi `name` là **tên khóa**.
2. Đọc `System.getProperty(name)`.
3. Nếu không nhận được giá trị chuỗi hợp lệ, trả `null`.
4. Nếu có chuỗi, giải mã số bằng quy tắc giống `Integer.decode(String)`.
5. Nếu giải mã được số trong miền `int`, trả `Integer` tương ứng; nếu sai định dạng hoặc ngoài miền, trả `null`.

Đây là **mô hình giải thích hành vi công khai**, không phải cam kết về từng câu lệnh trong triển khai nội bộ JDK.

~~~java
System.setProperty("demo.threads", "8");
Integer threads = Integer.getInteger("demo.threads");

System.out.println(threads); // 8
~~~

Nếu không có property mang tên `"demo.threads"`:

~~~java
System.clearProperty("demo.threads");
Integer threads = Integer.getInteger("demo.threads");
System.out.println(threads); // null
~~~

`null` nói rằng lời gọi không cung cấp một giá trị số `Integer`; nó **không phải số 0**. Trên thực tế, `null` có thể do property không tồn tại, tên không hợp lệ hoặc giá trị chuỗi không giải mã được. Chỉ nhìn kết quả `null` không đủ để xác định nguyên nhân nếu chưa kiểm tra property gốc và trạng thái truy cập.

## 5. Cơ chế của Long.getLong

`Long.getLong(name)` cũng đọc **property có tên `name`**, nhưng phân tích thành số nguyên `long` 64 bit có dấu thay vì `int` 32 bit:

~~~java
System.setProperty("demo.max.id", "9223372036854775807");

Long id = Long.getLong("demo.max.id");
System.out.println(id); // 9223372036854775807
~~~

Con số trên đúng bằng `Long.MAX_VALUE`; `Integer.getInteger("demo.max.id")` sẽ không biểu diễn được giá trị đó và trả `null`.

| Đặc điểm | `Integer.getInteger` | `Long.getLong` |
| --- | --- | --- |
| Kiểu trả về | `Integer` | `Long` |
| Miền số | −2³¹ đến 2³¹−1 | −2⁶³ đến 2⁶³−1 |
| Phương thức giải mã cùng quy tắc | `Integer.decode` | `Long.decode` |
| Không có/sai property | `null` hoặc default | `null` hoặc default |
| Có đọc môi trường trực tiếp? | Không | Không |

Tên `Long.getLong` không có nghĩa “đọc một Long từ biến tên bất kỳ” hay “đổi giá trị của biến `String` truyền vào thành long”. Nó dùng chính **giá trị của tham số `name` như một khóa tra cứu**.

## 6. Quy tắc giải mã: thập phân, hexadecimal, octal

`getInteger` và `getLong` giải mã **giá trị property** theo quy tắc `Integer.decode`/`Long.decode`. Những chuỗi phổ biến:

| Property value | Cách hiểu của `decode` | Giá trị thập phân |
| --- | --- | --- |
| `"42"` | Thập phân | 42 |
| `"+42"` | Thập phân, dấu cộng | 42 |
| `"-42"` | Thập phân, dấu trừ | −42 |
| `"0x2A"` hoặc `"0X2A"` | Hexadecimal | 42 |
| `"#2A"` | Hexadecimal | 42 |
| `"052"` | Octal vì có số 0 dẫn đầu | 42 |
| `"-0x2A"` | Hexadecimal âm | −42 |
| `"0"` | Số không | 0 |

Nhớ rằng **số 0 ở đầu có ý nghĩa**:

~~~java
System.setProperty("demo.mode", "010");
System.out.println(Integer.getInteger("demo.mode")); // 8
System.out.println(Integer.parseInt("010"));         // 10
~~~

`Integer.getInteger` đọc giá trị property `"010"` rồi decode thành **octal 8**. `Integer.parseInt("010")` mặc định dùng **radix 10** nên nhận **10**.

Đây là khác biệt dễ tạo lỗi cấu hình: người viết cấu hình có thể tưởng `010` là mười, nhưng người đọc bằng `getInteger` nhận tám. Khi tài liệu cấu hình quy định giá trị decimal, cách đọc `System.getProperty` rồi `parseInt` có thể phù hợp hơn.

### Tiền tố nào không được decode hỗ trợ?

`Integer.decode`/`Long.decode` không nhận tiền tố `0b`/`0B` của **literal nhị phân trong mã nguồn Java**. Những chuỗi như `"0b1010"` thường làm `getInteger`/`getLong` trả `null` hoặc fallback.

Ngoài ra, dấu gạch dưới `_` trong **literal Java source** như `1_000` là cú pháp của trình biên dịch, không mặc nhiên hợp lệ khi đưa vào chuỗi cấu hình `"1_000"`. Không dựa vào hỗ trợ của Java literal để suy ra khả năng parse của các API trên.

Ví dụ sai:

~~~java
System.setProperty("demo.binary", "0b1010");
Integer value = Integer.getInteger("demo.binary", -1);
System.out.println(value); // -1: 0b không được decode hỗ trợ
~~~

Nếu cấu hình thực sự quy định hệ 2, dùng `Integer.parseInt(text, 2)` với văn bản chữ số `"1010"`, hoặc thiết kế bước xử lý rõ ràng cho tiền tố `0b` trước khi parse.

### Dấu, khoảng trắng và định dạng

Các phương thức `decode` cho phép dấu `+` hoặc `-` ở **đầu chuỗi**, trước tiền tố radix khi có. Không thêm dấu sau tiền tố, chẳng hạn `"0x-2A"`.

Chúng không tự tiện cắt mọi khoảng trắng. Giá trị như `" 42 "` không phải chuỗi hợp lệ đối với `decode`; `getInteger` trả `null` hoặc fallback. Nếu hợp đồng cấu hình cho phép whitespace, hãy đọc chuỗi và xử lý tường minh, ví dụ `text.trim()`, sau đó parse.

## 7. Khi thiếu property và khi nội dung không hợp lệ

Ba trạng thái có thể rất khác nhau trong cấu hình:

1. Property **không tồn tại**.
2. Property **tồn tại nhưng chuỗi rỗng hoặc sai định dạng**.
3. Property **tồn tại nhưng số vượt miền kiểu đích**.

Với `Integer.getInteger(name)`, kết quả của cả ba trường hợp có thể là `null`. Với overload có giá trị mặc định, cả ba trả về cùng fallback, trừ khi xảy ra lỗi bảo mật khi đọc property.

~~~java
System.clearProperty("demo.missing");
System.setProperty("demo.invalid", "abc");
System.setProperty("demo.too.big", "2147483648");

System.out.println(Integer.getInteger("demo.missing"));       // null
System.out.println(Integer.getInteger("demo.invalid"));       // null
System.out.println(Integer.getInteger("demo.too.big"));       // null
System.out.println(Integer.getInteger("demo.missing", 7));    // 7
System.out.println(Integer.getInteger("demo.invalid", 7));    // 7
System.out.println(Integer.getInteger("demo.too.big", 7));    // 7
~~~

`2147483648` lớn hơn `Integer.MAX_VALUE` đúng một đơn vị, nhưng vẫn nằm trong miền `long`:

~~~java
System.out.println(Long.getLong("demo.too.big")); // 2147483648
~~~

**Điều cần lưu ý:** `getInteger`/`getLong` có thể khiến dữ liệu cấu hình **không hợp lệ bị che giấu** bởi fallback. Với cấu hình bắt buộc và quan trọng (ví dụ giới hạn tài nguyên), việc tùy tiện chọn default có thể che khuất lỗi vận hành.

## 8. Overload và giá trị mặc định

`Integer` có các dạng:

~~~java
Integer getInteger(String name)
Integer getInteger(String name, int defaultValue)
Integer getInteger(String name, Integer defaultValue)
~~~

`Long` có các dạng tương ứng:

~~~java
Long getLong(String name)
Long getLong(String name, long defaultValue)
Long getLong(String name, Long defaultValue)
~~~

Chữ ký trên để tham khảo API (không phải khai báo method để copy vào lớp ứng dụng).

Các ví dụ:

~~~java
System.clearProperty("app.timeout");
System.out.println(Integer.getInteger("app.timeout", 30)); // 30
System.out.println(Long.getLong("app.timeout", 60L));      // 60

Integer fallback = Integer.valueOf(15);
Integer timeout = Integer.getInteger("app.timeout", fallback);
System.out.println(timeout); // 15
~~~

Dạng nhận wrapper cho phép truyền một giá trị mặc định kiểu wrapper; về mặt kết quả, có thể cho `null` nếu tham số default wrapper là `null`:

~~~java
Integer noDefault = Integer.getInteger("app.timeout", (Integer) null);
System.out.println(noDefault); // null
~~~

Trong trường hợp này, khi property không có hoặc không giải mã được, một fallback null vẫn cho ra null. Cần chủ động chọn kiểu overload, đặc biệt khi truyền literal `null` — dùng ép kiểu để thể hiện ý định hoặc chọn phương thức không có tham số default.

### Nếu muốn phát hiện lỗi cấu hình thay vì âm thầm lấy default

~~~java
static int requiredDecimalProperty(String name) {
    String text = System.getProperty(name);
    if (text == null) {
        throw new IllegalArgumentException("Missing system property: " + name);
    }
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "Invalid decimal integer property: " + name, ex);
    }
}
~~~

Đây là **phương thức minh họa bên trong một lớp**, biên dịch được trên Java 17. Nó quy định chỉ nhận **số thập phân**; khác với `Integer.getInteger`, chuỗi `"010"` sẽ được hiểu là 10 và `"0x10"` bị từ chối. Đừng thêm `trim()` một cách ngầm định nếu hệ thống muốn phát hiện whitespace không hợp lệ.

Hàm này **không** tự kiểm tra giới hạn nghiệp vụ như “số luồng phải lớn hơn 0”; việc đó cần thêm validation sau khi parse.

## 9. Chương trình Java 17+ chạy độc lập

Tạo tệp `SystemPropertyNumberDemo.java`:

~~~java
public class SystemPropertyNumberDemo {
    public static void main(String[] args) {
        System.setProperty("lesson.count", "42");
        System.setProperty("lesson.hex", "0x2A");
        System.setProperty("lesson.octal", "010");
        System.setProperty("lesson.binary", "0b1010");
        System.setProperty("lesson.invalid", "abc");
        System.setProperty("lesson.outOfInt", "2147483648");
        System.setProperty("lesson.maxLong", "9223372036854775807");
        System.clearProperty("lesson.missing");

        System.out.println("getInteger decimal=" +
                Integer.getInteger("lesson.count"));
        System.out.println("getInteger hex=" +
                Integer.getInteger("lesson.hex"));
        System.out.println("getInteger octal=" +
                Integer.getInteger("lesson.octal"));
        System.out.println("parseInt octal text=" +
                Integer.parseInt(System.getProperty("lesson.octal")));
        System.out.println("getLong max=" +
                Long.getLong("lesson.maxLong"));

        System.out.println("missing=" +
                Integer.getInteger("lesson.missing"));
        System.out.println("missing default=" +
                Integer.getInteger("lesson.missing", 99));
        System.out.println("invalid default=" +
                Integer.getInteger("lesson.invalid", 7));
        System.out.println("binary default=" +
                Integer.getInteger("lesson.binary", -1));
        System.out.println("int overflow default=" +
                Integer.getInteger("lesson.outOfInt", -1));
        System.out.println("same number as long=" +
                Long.getLong("lesson.outOfInt"));

        System.out.println("parse direct=" + Integer.parseInt("42"));
        System.out.println("raw property=" +
                System.getProperty("lesson.count"));

        try {
            Integer.parseInt("abc");
        } catch (NumberFormatException ex) {
            System.out.println("parse invalid: NumberFormatException");
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 SystemPropertyNumberDemo.java
java SystemPropertyNumberDemo
~~~

Kết quả stdout:

~~~text
getInteger decimal=42
getInteger hex=42
getInteger octal=8
parseInt octal text=10
getLong max=9223372036854775807
missing=null
missing default=99
invalid default=7
binary default=-1
int overflow default=-1
same number as long=2147483648
parse direct=42
raw property=42
parse invalid: NumberFormatException
~~~

Giải thích:

- Các property được đặt bằng `System.setProperty` trong chính chương trình nên kết quả độc lập với cấu hình `-D` bên ngoài cho những khóa đó.
- Số `"010"` được `getInteger` giải mã theo octal thành 8; `parseInt` theo decimal thành 10.
- `"0b1010"` không thuộc tiền tố `decode` nên trở về fallback −1.
- `"2147483648"` vượt miền `int` nhưng vẫn hợp lệ với `long`.
- `Integer.parseInt("abc")` phát sinh `NumberFormatException`; `getInteger` với property có value `"abc"` lại trả default.
- `System.getProperty` trả chuỗi gốc; không ép kiểu và không thực hiện bước giải mã.

## 10. Dùng -D khi triển khai chương trình thực

Với chương trình ứng dụng có class `ServerApp` đã được biên dịch, có thể cấu hình từ command line:

~~~bash
java -Dserver.port=8080 -Dserver.workers=4 ServerApp
~~~

Đoạn mã ứng dụng:

~~~java
int port = Integer.getInteger("server.port", 8080);
int workers = Integer.getInteger("server.workers", 4);
~~~

Ở đây Java **autounbox** kết quả wrapper từ `getInteger` vào `int`. Với overload có primitive default, trường hợp property không tồn tại/sai sẽ cho wrapper chứa default trước khi unbox, vì vậy không xuất hiện null trong đường đi thông thường. Tuy nhiên, nếu hạn chế quyền truy cập property thì vẫn có thể có ngoại lệ.

Không nhầm vị trí của tham số JVM:

~~~bash
java -Dserver.port=8080 ServerApp
~~~

`-Dserver.port=8080` là tùy chọn của **JVM trước tên class**. Viết `java ServerApp -Dserver.port=8080` sẽ truyền chuỗi đó vào `main(String[] args)` như một tham số chương trình, không tự thiết lập system property tương ứng.

### Mối quan hệ với môi trường triển khai

Trên hệ thống container/service, có thể có biến môi trường tên `SERVER_PORT`, file cấu hình, tham số dòng lệnh ứng dụng, hoặc system property `server.port`. Đây là các nguồn cấu hình độc lập. Nếu yêu cầu triển khai phân cấp ưu tiên, chẳng hạn “`-D` ưu tiên hơn environment”, phải viết logic xử lý rõ ràng.

Không nên đưa mật khẩu, token hoặc thông tin nhạy cảm vào system property một cách tùy tiện chỉ vì tiện sử dụng. Thuộc tính JVM có thể lộ qua công cụ chẩn đoán, logging hoặc danh sách tham số tiến trình tùy môi trường; cần tuân thủ cơ chế lưu trữ bí mật phù hợp.

## 11. Chuỗi chứa số: parseInt, parseLong, decode hay getInteger?

Một tiêu chí thực tế:

| Nhu cầu | API đề xuất |
| --- | --- |
| Người dùng nhập chuỗi decimal `"123"` | `Integer.parseInt(text)` hoặc `Long.parseLong(text)` |
| Chuỗi decimal nhưng cần wrapper | `Integer.valueOf(text)` hoặc `Long.valueOf(text)` |
| Chuỗi số theo radix có tiền tố `0x`, `#`, số 0 đầu chuỗi | `Integer.decode(text)` hoặc `Long.decode(text)` |
| Chuỗi chữ số với radix chỉ định rõ | `Integer.parseInt(text, radix)` hoặc `Long.parseLong(text, radix)` |
| Đọc property JVM và chấp nhận quy tắc `decode`, fallback | `Integer.getInteger(name, default)` hoặc `Long.getLong(name, default)` |
| Đọc property JVM nhưng bắt buộc decimal, cần báo lỗi chính xác | `System.getProperty(name)`, kiểm tra rồi `parseInt`/`parseLong` |
| Đọc biến môi trường | `System.getenv(name)`, sau đó kiểm tra/parse nếu cần |

Một cách nghĩ an toàn:

- Có **giá trị text** cần chuyển sang số → chọn một phương thức **parse/decode**.
- Có **tên property JVM** muốn đọc cấu hình dạng số → chọn `getInteger`/`getLong` khi phù hợp hợp đồng decode/fallback.
- Có **tên environment variable** → đọc qua `System.getenv` trước, không dùng `getInteger` để tra.

## 12. Cẩn trọng với parsing số và giới hạn miền

### Số vượt miền kiểu đích

~~~java
System.setProperty("app.large", "9223372036854775807");
System.out.println(Long.getLong("app.large"));     // 9223372036854775807
System.out.println(Integer.getInteger("app.large")); // null
~~~

Nếu value vượt cả miền `long`, `Long.getLong` cũng không thể giải mã; khi không có default nó trả `null`. Phần tử cấu hình cần giá trị lớn hơn `long` có thể dùng `BigInteger` sau khi đọc text, với validation riêng.

### Null không phải số 0

~~~java
System.clearProperty("app.items");
Integer items = Integer.getInteger("app.items");

System.out.println(items == null); // true
~~~

Nếu dùng `int count = Integer.getInteger("app.items");`, unboxing giá trị `null` sẽ ném `NullPointerException`. Đây là lỗi thường gặp khi dùng overload không có default với biến primitive.

Nếu “property vắng” khác “giá trị zero”, hãy giữ `Integer` nullable và xử lý hai trường hợp tường minh, hoặc ném ngoại lệ cấu hình có thông báo.

### Không tự động bỏ qua whitespace

~~~java
System.setProperty("app.spaces", " 7 ");
System.out.println(Integer.getInteger("app.spaces", -1)); // -1
~~~

Nếu người dùng có thể nhập khoảng trắng, đọc text và áp dụng chính sách chuẩn hóa **có chủ đích**. Lỗi sai định dạng cũng nên được log có kiểm soát để người vận hành biết nguyên nhân thay vì mất dấu trong một default “có vẻ hợp lệ”.

## 13. Chính sách cấu hình: optional, required và valid range

Đối với một system property định nghĩa kích thước pool worker, ta thường cần ít nhất ba bước:

1. **Đọc** giá trị từ nguồn dự kiến.
2. **Parse** với quy tắc định dạng được công bố.
3. **Validate** miền nghiệp vụ, ví dụ worker count từ 1 đến 128.

Một hàm Java 17 minh họa:

~~~java
static int workerCount() {
    String raw = System.getProperty("app.workers");
    if (raw == null) {
        return 4; // Mặc định khi khóa không có
    }

    final int count;
    try {
        count = Integer.parseInt(raw);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "app.workers must be a decimal integer", ex);
    }

    if (count < 1 || count > 128) {
        throw new IllegalArgumentException(
                "app.workers must be in 1..128");
    }
    return count;
}
~~~

Điểm khác biệt với `Integer.getInteger("app.workers", 4)`:

- **Property vắng** → dùng 4.
- **Property sai định dạng** → báo lỗi thay vì im lặng dùng 4.
- **Property có giá trị 0, âm hoặc quá lớn theo nghiệp vụ** → báo lỗi.
- `"010"` được parse thành decimal 10, không phải octal 8.

Việc chọn fallback hay fail-fast tùy mức độ bắt buộc của cấu hình. Với thông số ảnh hưởng tài nguyên, tính an toàn hoặc dữ liệu quan trọng, **fail-fast** thường giúp phát hiện lỗi triển khai sớm.

## 14. Những lỗi thường gặp

| Nhầm lẫn | Hậu quả | Sửa đúng |
| --- | --- | --- |
| `Integer.getInteger("123")` để parse số 123 | Tra property tên `"123"`, thường nhận `null` | `Integer.parseInt("123")` |
| `Long.getLong("9223372036854775807")` để parse số | Tra property có tên nguyên chuỗi số | `Long.parseLong(text)` |
| Nghĩ `getInteger` tự đọc environment variable | Bỏ qua `System.getenv` | Đọc môi trường trước nếu đó là nguồn dữ liệu |
| Nghĩ `getInteger` luôn dùng decimal | Property `"010"` thành octal 8 | `System.getProperty` + `parseInt` khi cần decimal |
| Property `"0b1010"` được decode như binary literal | Nhận null/default | Parse radix 2 sau khi xử lý định dạng |
| Property `"1_000"` được decode như Java literal | Nhận null/default | Định nghĩa và thực hiện chuẩn hóa/parse riêng |
| Property sai định dạng nhưng fallback âm thầm | Che giấu cấu hình sai | Đọc chuỗi rồi fail-fast |
| Gán kết quả `getInteger(name)` vào `int` mà không kiểm tra | `NullPointerException` nếu không có/sai property | Dùng overload default hoặc null guard |
| `Integer.getInteger` đọc số vượt miền int | Null/default dù văn bản là số hợp lệ kiểu long | Dùng `Long.getLong` hoặc parse kiểu phù hợp |
| Nghĩ fallback sẽ ghi property mới | Nhầm trạng thái cấu hình | Fallback chỉ là giá trị kết quả |
| Đặt `-D` sau class trong lệnh `java` | Không đặt JVM property | Đặt `-Dkey=value` trước tên class/JAR |
| Dùng getInteger cho mọi kiểu cấu hình không validation | Chấp nhận số âm/zero ngoài hợp đồng | Validate miền nghiệp vụ sau khi parse |

## 15. Bài tập tự kiểm tra

**1.** Cho:

~~~java
System.setProperty("demo.number", "25");
System.out.println(Integer.getInteger("demo.number"));
System.out.println(Integer.getInteger("25"));
~~~

Dòng đầu in bao nhiêu? Dòng thứ hai có chắc in 25 không?

**Đáp án:** dòng đầu in `25`. Dòng thứ hai tra property **tên** `"25"`; kết quả có thể là `null` nếu property đó không tồn tại, không được phép suy ra sẽ in 25.

**2.** Property `demo.limit=0x20` được đọc bằng `Long.getLong("demo.limit")` thành bao nhiêu?

**Đáp án:** `32L`, vì `0x20` là hexadecimal.

**3.** Tại sao `Integer.getInteger("mode", -1)` có thể trả −1 dù property `mode` tồn tại?

**Đáp án:** Property value có thể sai định dạng hoặc vượt miền `int`, khiến decode thất bại và overload dùng fallback.

**4.** Vì sao `Integer.getInteger` đọc `"010"` khác `Integer.parseInt("010")`?

**Đáp án:** getInteger dùng quy tắc `Integer.decode` của **property value**, nên nhận octal 8; parseInt mặc định decimal nên nhận 10.

**5.** Muốn ứng dụng báo lỗi nếu `app.workers` có value `"abc"` nhưng dùng default khi property không tồn tại: nên dùng gì?

**Đáp án:** `System.getProperty("app.workers")`; nếu trả null thì dùng default, còn nếu có chuỗi thì `Integer.parseInt` trong `try/catch` và validation nghiệp vụ.

**6.** `Long.getLong` có đọc được biến môi trường `MAX_COUNT` không?

**Đáp án:** Không tự động. `Long.getLong("MAX_COUNT")` tìm **system property** tên đó. Muốn đọc environment variable, dùng `System.getenv("MAX_COUNT")` rồi parse.

## 16. Ghi nhớ

- **`Integer.getInteger(name)` và `Long.getLong(name)` nhận *tên system property*, không nhận trực tiếp một chuỗi số để parse.**
- Chúng đọc property value rồi decode theo quy tắc decimal/hex/octal, khác parse decimal mặc định.
- Không có property hoặc value không hợp lệ → trả `null` hoặc default do overload; cần kiểm tra null khi unboxing.
- `System.getProperty`, `System.getenv` và `Integer.parseInt`/`Long.parseLong` giải quyết **những bài toán khác nhau**.
- Khi cấu hình quan trọng, tách rõ đọc nguồn → parse → validate → xử lý lỗi, thay vì vô tình che lỗi bằng fallback.

Tài liệu chính thức (Java 17):

- [Integer.getInteger / Integer.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): quy tắc đọc system property và giải mã giá trị.
- [Long.getLong / Long.decode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): tương tự cho `long`.
- [System.getProperty](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#getProperty(java.lang.String)) và [System.getenv](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#getenv(java.lang.String)): phân biệt nguồn cấu hình.
- [Java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn `-Dproperty=value`.
