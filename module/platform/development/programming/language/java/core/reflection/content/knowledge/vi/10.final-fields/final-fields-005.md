# Giá trị hằng có thể đã được nhúng vào mã sử dụng

## 1. Vì sao sửa `final` field mà chương trình khác vẫn thấy giá trị cũ?

Trong Java, khi một field đủ điều kiện là **hằng tại thời điểm biên dịch** (*compile-time constant variable*), compiler có thể thay thao tác đọc field bằng chính giá trị hằng ngay trong bytecode của lớp sử dụng. Hiện tượng thường gọi là **constant inlining** hoặc **constant folding tại chỗ sử dụng**.

Hệ quả quan trọng: nếu thư viện thay đổi giá trị một hằng như `public static final int LIMIT = 10` thành `20` và chỉ biên dịch lại thư viện, bytecode của ứng dụng đã được biên dịch trước đó **có thể tiếp tục dùng 10**. Đổi file `.class` chứa field không tự động sửa những giá trị đã được nhúng vào file `.class` của các chương trình sử dụng.

~~~java
public class Limits {
    public static final int MAX_ITEMS = 100;
    public static final String VERSION = "v1";
}
~~~

Với mã sử dụng:

~~~java
System.out.println(Limits.MAX_ITEMS);
System.out.println(Limits.VERSION);
~~~

Hai biểu thức trên có thể được compiler thay bằng literal `100` và `"v1"`. Ở bytecode của caller, có thể **không còn lệnh đọc field `Limits.MAX_ITEMS`/`Limits.VERSION`**. Vì vậy cần phân biệt:

- **Giá trị runtime của field:** giá trị hiện có trong lớp được JVM nạp.
- **Giá trị đã nhúng vào mã sử dụng:** literal được đặt trong bytecode của caller khi caller được biên dịch.
- **Giá trị quan sát qua Reflection:** `Field.get(...)` đọc field của lớp runtime sau khi áp dụng các quy tắc quyền truy cập, không đọc literal đã nhúng trong caller.

Điều này đặc biệt quan trọng với field `final` của API thư viện, module dùng chung, cấu hình dưới dạng constant và các dự án build nhiều module.

## 2. Field nào thực sự là compile-time constant?

Theo quy tắc ngôn ngữ Java, một **constant variable** là biến `final` có kiểu **primitive** hoặc `String`, được khởi tạo bằng **constant expression**. Trong thực tế, các field dễ gặp nhất là `static final` kiểu `int`, `long`, `boolean`, `char`, `String`... gán trực tiếp bằng literal hoặc biểu thức hằng.

| Khai báo | Là constant variable? | Vì sao |
| --- | --- | --- |
| `public static final int PORT = 8080;` | Có | Primitive, `final` và biểu thức literal |
| `public static final int TOTAL = 40 + 2;` | Có | `40 + 2` là constant expression |
| `public static final String LABEL = "core" + "-api";` | Có | Ghép các chuỗi hằng tại compile time |
| `public static final boolean ENABLED = true;` | Có | Primitive, biểu thức hằng |
| `public static final Integer COUNT = 42;` | Không | `Integer` là kiểu tham chiếu khác `String`, dù giá trị biểu diễn số nguyên |
| `public static final int PORT = Integer.parseInt("8080");` | Không | Lời gọi method thông thường không phải constant expression |
| `public static final String LABEL = new String("core");` | Không | Tạo đối tượng bằng `new` không phải constant expression |
| `public static final long CREATED_AT = System.currentTimeMillis();` | Không | Giá trị tính lúc runtime |
| `public final int id = 7;` | Có, xét định nghĩa constant variable | Field instance cũng có thể là constant variable nếu `final`, primitive/`String` và khởi tạo bằng constant expression |
| `public final int id;` được gán trong constructor | Không | Không khởi tạo bằng constant expression ngay tại khai báo |

**Không phải cứ có `final` là sẽ được nhúng.** `final` thể hiện giới hạn gán lại field theo ngôn ngữ, còn khả năng xem như compile-time constant phụ thuộc thêm **kiểu** và **biểu thức khởi tạo**. Hằng `static final` là trường hợp có ảnh hưởng lớn nhất đến API công khai vì nhiều class khác cùng tham chiếu một field.

Để tránh nhầm lẫn, `static final Integer VALUE = 42` **không** là compile-time constant theo quy tắc này. Compiler khi dùng field đó theo cơ chế thông thường phải lấy tham chiếu runtime; autoboxing số 42 ở chỗ khởi tạo không biến một field `Integer` thành constant variable.

## 3. Ví dụ Java 17+: sửa class chứa hằng nhưng không biên dịch lại caller

Bài thực hành này dùng **hai file nằm cùng thư mục**. Thực hiện qua hai vòng biên dịch để nhìn thấy sự khác nhau giữa bytecode của thư viện và bytecode của consumer.

### Bước A — Phiên bản đầu tiên

Tạo file `Constants.java`:

~~~java
public class Constants {
    static {
        System.out.println("Constants initialized");
    }

    public static final int LIMIT = 10;
    public static final String LABEL = "v1";
    public static final int RUNTIME = Integer.parseInt("10");
}
~~~

Tạo file `Consumer.java`:

~~~java
public class Consumer {
    public static void main(String[] args) throws Exception {
        System.out.println("direct LIMIT = " + Constants.LIMIT);
        System.out.println("direct LABEL = " + Constants.LABEL);
        System.out.println("direct RUNTIME = " + Constants.RUNTIME);

        System.out.println("reflection LIMIT = "
                + Constants.class.getField("LIMIT").getInt(null));
        System.out.println("reflection LABEL = "
                + Constants.class.getField("LABEL").get(null));
    }
}
~~~

Trong terminal tại thư mục chứa hai file:

~~~bash
javac --release 17 Constants.java Consumer.java
java Consumer
~~~

Kết quả:

~~~text
direct LIMIT = 10
direct LABEL = v1
Constants initialized
direct RUNTIME = 10
reflection LIMIT = 10
reflection LABEL = v1
~~~

Giải thích: `LIMIT` và `LABEL` là compile-time constants. Hai dòng `direct` đầu tiên được tạo từ giá trị có thể nhúng ngay vào bytecode của `Consumer`; chúng **không làm `Constants` được khởi tạo**. Đến dòng dùng `Constants.RUNTIME`, JVM phải đọc field runtime bằng cơ chế truy cập static field, nên lớp `Constants` được khởi tạo và static initializer in `Constants initialized`. Reflection ở cuối đọc đúng giá trị field của lớp đã nạp.

### Bước B — Đổi thư viện, không biên dịch lại `Consumer`

**Chỉ thay nội dung `Constants.java`** bằng:

~~~java
public class Constants {
    static {
        System.out.println("Constants initialized");
    }

    public static final int LIMIT = 20;
    public static final String LABEL = "v2";
    public static final int RUNTIME = Integer.parseInt("20");
}
~~~

Sau đó chỉ chạy:

~~~bash
javac --release 17 Constants.java
java Consumer
~~~

Chú ý **không** chạy lại `javac Consumer.java` ở bước này. `Consumer.class` cũ vẫn tồn tại.

Kết quả đã kiểm tra với Java 21:

~~~text
direct LIMIT = 10
direct LABEL = v1
Constants initialized
direct RUNTIME = 20
reflection LIMIT = 20
reflection LABEL = v2
~~~

Cùng một lần chạy, chương trình vừa thấy `10`, `"v1"` qua code sử dụng đã biên dịch từ trước, vừa thấy `20`, `"v2"` trong field hiện tại. Đây không phải JVM “ghi nhớ sai” field; bytecode `Consumer.class` vẫn chứa các literal cũ.

- `Constants.LIMIT` và `Constants.LABEL` ở hai câu lệnh `direct` đã được biên dịch thành các chuỗi đầu ra chứa literal cũ.
- `Constants.RUNTIME` **không** là constant variable vì được khởi tạo bằng `Integer.parseInt(...)`; caller dùng phép đọc field runtime nên thấy `20` từ `Constants.class` mới.
- `Constants.class.getField("LIMIT").getInt(null)` và `getField("LABEL").get(null)` đọc metadata/giá trị field từ lớp `Constants` thực sự được nạp tại runtime. Chúng thấy phiên bản mới.
- Trong ví dụ, `Constants` là public class và các field đều public; `getField` thành công và `getInt(null)` hợp lệ với static field primitive `int`.

### Bước C — Biên dịch lại caller

Sau khi đã cập nhật `Constants.java`, tiếp tục:

~~~bash
javac --release 17 Consumer.java
java Consumer
~~~

Giờ hai dòng `direct` đọc theo hằng mới vì `Consumer.class` được biên dịch lại:

~~~text
direct LIMIT = 20
direct LABEL = v2
Constants initialized
direct RUNTIME = 20
reflection LIMIT = 20
reflection LABEL = v2
~~~

Quy tắc thực hành: khi **thay giá trị public compile-time constant** trong thư viện, cần **biên dịch lại cả các consumer liên quan** để chắc chắn bytecode của họ không giữ literal cũ.

## 4. Nhìn vào bytecode để hiểu nguyên nhân

Sau bước B (trước khi biên dịch lại `Consumer`), chạy:

~~~bash
javap -c Consumer
~~~

Trong bytecode của `main` sẽ thấy phần tương đương:

- Lệnh `ldc` nạp chuỗi đã tạo sẵn `"direct LIMIT = 10"`.
- Lệnh `ldc` nạp chuỗi đã tạo sẵn `"direct LABEL = v1"`.
- Với `RUNTIME`, lệnh `getstatic Constants.RUNTIME:I` đọc trường số nguyên của lớp `Constants` lúc runtime.

`javap` có thể hiển thị thêm chỉ số constant pool và các lệnh `invokedynamic` phục vụ nối chuỗi; vị trí/chỉ số bytecode có thể khác tùy JDK. Điều cần kiểm chứng là **không có `getstatic` đến `Constants.LIMIT` hay `Constants.LABEL` trong hai biểu thức direct đã được compiler rút gọn**. Vì caller không thực hiện thao tác đọc static field cho hai hằng đó, thay đổi giá trị field trong class khác không sửa được các literal trong bytecode cũ.

Đây là một tối ưu hóa và ngữ nghĩa được ngôn ngữ Java cho phép; không nên quy kết chung cho JIT cache. JIT có thể thực hiện các tối ưu khác ở runtime, nhưng ví dụ trên tái hiện vấn đề ngay trong **file `Consumer.class` sau bước compile**.

## 5. Reflection nhìn thấy gì, và có nên sửa `final` bằng Reflection?

Với `public static final int LIMIT = 20`:

~~~java
java.lang.reflect.Field field = Constants.class.getField("LIMIT");
System.out.println(field.getType());  // int
System.out.println(field.getInt(null)); // 20
System.out.println(field.get(null));    // Integer chứa 20
~~~

Đây là **đoạn minh họa** dùng lại `Constants` phiên bản ở bước B, không phải chương trình độc lập. `getInt(null)` đọc primitive `int` trực tiếp; `get(null)` trả `Object` nên boxing thành `Integer`. Đối với static field, receiver có thể là `null`.

Điều Reflection **không** làm là thay literal đã nhúng trong bytecode `Consumer.class`. `getInt(null)` phản ánh giá trị field đang tồn tại; còn câu lệnh `System.out.println("direct LIMIT = " + Constants.LIMIT)` của caller cũ đã được dịch sang chuỗi chứa `10`.

**Đừng cố sửa `static final` bằng `Field.set` để “cập nhật mọi nơi”.** Trong Java hiện đại, `static final` là nhóm final field không được phép ghi qua Reflection, kể cả khi `setAccessible(true)` có thể được chấp nhận cho mục đích đọc. Thêm nữa, ngay cả một cơ chế có thể chỉnh một giá trị nào đó ở runtime cũng **không thể sửa những literal đã có sẵn trong caller bytecode**. Mở quyền truy cập không đồng nghĩa thay đổi cách compiler tạo và sử dụng compile-time constants.

Nếu cần cập nhật giá trị sau khi phát hành, hãy thiết kế điểm truy cập runtime chính thức (method, cấu hình, dịch vụ/registry có lifecycle rõ ràng) thay vì dùng một public compile-time constant như giá trị cấu hình có thể thay đổi.

## 6. Đọc `static final` có luôn kích hoạt class initialization không?

**Không.** Theo quy tắc Java về khởi tạo class, việc sử dụng một `static final` **constant variable** có thể được biên dịch thành literal và không phải thao tác kích hoạt khởi tạo class sở hữu field.

Trong ví dụ:

~~~java
System.out.println("direct LIMIT = " + Constants.LIMIT);
System.out.println("direct LABEL = " + Constants.LABEL);
~~~

Không có dòng `Constants initialized` xen giữa hai lệnh này. Lớp `Constants` chỉ được khởi tạo khi chương trình đọc `Constants.RUNTIME`, là field `static final` **không** phải constant variable vì nó được tính bằng lời gọi method lúc runtime.

Phân biệt:

| Phép sử dụng | Kết quả thường gặp |
| --- | --- |
| Tham chiếu `Constants.LIMIT` compile-time constant qua code đã biên dịch | Bytecode dùng literal; không cần đọc field runtime và không khởi tạo lớp vì phép đọc đó |
| Tham chiếu `Constants.RUNTIME` có initializer không hằng | Lệnh `getstatic`; JVM khởi tạo class trước khi đọc theo quy tắc JVM |
| Lấy `Constants.class` | Class literal không tự nó kích hoạt class initialization |
| Dùng Reflection để lấy giá trị static field bằng `Field.get` | Thao tác đọc static field có thể kích hoạt khởi tạo class nếu chưa khởi tạo |
| Gọi static method hoặc tạo instance | Thường là thao tác kích hoạt class initialization theo quy tắc Java |

Vì vậy logging trong static initializer **không phải phép đo tin cậy** cho việc caller đã đọc một compile-time constant hay chưa. Compiler có thể loại bỏ hoàn toàn truy cập field tại runtime.

## 7. Ảnh hưởng đến binary compatibility và versioning

Thay một constant từ `10` thành `20` không nhất thiết tạo lỗi liên kết (`LinkageError`). Ứng dụng vẫn có thể chạy với file `Constants.class` mới nhưng giữ giá trị cũ do đã được nhúng tại thời điểm biên dịch. Đây là nguy cơ **thay đổi hành vi khi cập nhật phiên bản** rất dễ bị bỏ sót.

Một tình huống điển hình:

1. Thư viện `api-v1.jar` công bố `public static final int MAX_RETRY = 3`.
2. Dịch vụ A biên dịch với `api-v1.jar`; bytecode A mang literal `3` tại các chỗ dùng compile-time constant.
3. Thư viện phát hành `api-v2.jar` thay `MAX_RETRY = 5`.
4. Nếu chỉ thay JAR thư viện và chạy lại dịch vụ A mà **không biên dịch lại A**, A vẫn có thể dùng `3` trong logic đã compile.
5. Recompile toàn bộ consumer với `api-v2.jar` mới làm các literal đó được cập nhật thành `5`.

Do vậy, với hằng công khai là một phần của hợp đồng giữa module, **việc thay giá trị phải được đánh giá như thay đổi API về mặt hành vi**. Build sạch/rebuild và kiểm tra bytecode giúp phát hiện trạng thái trộn giữa mã tiêu thụ cũ và thư viện mới.

Nếu một giá trị cần có thể thay đổi theo cấu hình, phiên bản triển khai hoặc môi trường, cân nhắc API runtime:

~~~java
public final class RuntimeSettings {
    private RuntimeSettings() {}

    public static int maxRetry() {
        return Integer.getInteger("app.maxRetry", 3);
    }
}
~~~

Đoạn code trên là một ví dụ API runtime; gọi `RuntimeSettings.maxRetry()` đọc property hệ thống hiện tại (nếu không phải số hợp lệ thì `Integer.getInteger` trả giá trị mặc định theo hợp đồng API). Đây không phải compile-time constant nên caller không thể nhúng sẵn kết quả như literal từ field constant. Thiết kế cấu hình thực tế phải tính đến validation, caching và thời điểm cho phép thay đổi giá trị.

Một lựa chọn khác khi dữ liệu **cố ý bất biến suốt vòng đời một phiên bản ứng dụng** là dùng `static final` như trước, nhưng phải xác định rõ consumer cần được biên dịch lại khi thay đổi giá trị.

## 8. Các hiểu lầm thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “`final` tức là compiler luôn nhúng giá trị.” | Chỉ constant variables đáp ứng kiểu primitive/`String` + biểu thức khởi tạo hằng mới có cơ chế này; field final khác vẫn có thể được đọc ở runtime |
| “`static final Integer N = 1` là hằng giống `static final int N = 1`.” | `Integer` không phải primitive hoặc `String`, nên `N` không phải constant variable |
| “Đã đổi JAR chứa field thì mọi chương trình lập tức thấy giá trị mới.” | Consumer cũ có thể giữ literal đã nhúng; cần recompile các consumer |
| “Dùng `final` đảm bảo mọi field access đều chạy `getstatic`.” | Compile-time constant có thể biến thành literal và không còn `getstatic` ở caller |
| “Reflection luôn trả cùng giá trị với code gọi field trực tiếp.” | `Field.get` đọc field runtime; code cũ có thể dùng literal nhúng |
| “Sửa field bằng Reflection sẽ cập nhật được hằng trong consumer.” | Không: code consumer có thể không còn đọc field. Ghi static final bằng Reflection còn bị hạn chế độc lập |
| “`static final` lúc nào cũng khởi tạo class khi truy cập.” | Tham chiếu compile-time constant không kích hoạt khởi tạo class nếu đã được biên dịch thành literal; static field không hằng được đọc runtime |
| “`String` nối bằng `+` luôn được tính ở runtime.” | Nếu mọi thành phần là constant expression, phép nối có thể được tính ngay khi compile |

### Cách chẩn đoán một lỗi thực tế

Nếu một thành phần báo giá trị cấu hình cũ sau khi cập nhật thư viện, hãy kiểm tra theo trình tự:

1. Field có phải `final`, kiểu primitive/`String` và initializer constant expression không?
2. Component đang chạy có phải bytecode cũ của consumer được biên dịch với giá trị trước đây không?
3. Dùng `javap -c Consumer` để tìm literal hoặc `getstatic` tại chính điểm sử dụng.
4. Đọc field qua Reflection ở runtime (trong điều kiện có quyền) để đối chiếu giá trị hiện tại của class.
5. Biên dịch lại tất cả consumer liên quan và triển khai phiên bản tương ứng; kiểm tra JAR/classpath để tránh trộn phiên bản.

## 9. Câu hỏi tự kiểm tra

**1.** `public static final String NAME = "A" + "B";` có thể được nhúng vào caller không? **Có**: phép nối các string literal là constant expression, kết quả `"AB"` có thể xuất hiện trong bytecode consumer.

**2.** `public static final String NAME = System.getProperty("name");` có giống vậy không? **Không**: method call được tính ở runtime, không phải constant expression.

**3.** Vì sao `Field.getInt(null)` thấy `20` trong khi `Consumer` vẫn in `10`? Reflection đọc field của class runtime mới; `Consumer.class` cũ dùng literal đã nhúng trước khi thư viện thay đổi.

**4.** Có thể chỉ cập nhật file thư viện mà không biên dịch lại caller để nhận giá trị hằng mới không? **Không thể bảo đảm** với compile-time constant: caller có thể không còn truy cập field runtime. Phương án chắc chắn là recompile consumer.

**5.** `final int id = 7` ở instance có phải không bao giờ là constant variable vì thiếu `static`? **Không**: định nghĩa constant variable không bắt buộc `static`, dù bài toán nhúng giá trị xuyên các lớp độc lập thường nổi bật nhất với `public static final`.

**Ghi nhớ:** `final` và *compile-time constant* là hai khái niệm có liên hệ nhưng không đồng nhất. Khi đã có constant inlining, thay đổi field sau đó không sửa được các literal trong bytecode consumer; vì vậy việc phát hành hằng public và việc build lại caller phải được xem xét cùng nhau.
