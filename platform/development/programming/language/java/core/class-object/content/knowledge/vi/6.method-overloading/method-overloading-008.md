# Thiết kế tập phương thức nạp chồng dễ sử dụng trong Java

**Nạp chồng phương thức (method overloading)** cho phép nhiều phương thức cùng tên nhưng có danh sách tham số khác nhau. Khi thiết kế API, mục tiêu không phải tạo càng nhiều overload càng tốt, mà là giúp người dùng **đoán được cách gọi, hiểu đúng ý nghĩa, khó truyền nhầm đối số và nhận được hành vi nhất quán**. Một tập overload tốt cung cấp vài cách gọi thuận tiện cho **cùng một thao tác**; một tập overload kém khiến người gọi phải dò compiler sẽ chọn phương thức nào hoặc không biết trường hợp `null`, số nguyên, mảng và tham số mặc định được xử lý ra sao.

Bài này tập trung vào **tư duy thiết kế tập phương thức nạp chồng** trong Java Core, kết hợp nguyên tắc API, ví dụ Java 17+ chạy được, những lỗi thiết kế và quy trình kiểm tra trước khi công bố API.

## 1. Phân biệt “overload hợp lệ” với “overload dễ sử dụng”

Theo cách hiểu cơ bản, các khai báo sau có **chữ ký khác nhau**:

~~~java
void send(String message) { }
void send(String message, int retries) { }
void send(String message, int retries, long delayMillis) { }
~~~

Chúng khác nhau về số lượng và kiểu tham số, nên có thể cùng nằm trong một lớp. Tuy nhiên, chỉ nhìn chữ ký chưa thể biết `retries` có được âm không, `delayMillis` là mili giây hay giây, hoặc `send(message)` mặc định gửi lại bao nhiêu lần.

Đó là khoảng cách giữa **tính hợp lệ cú pháp** và **khả năng sử dụng API**:

| Tiêu chí | Chỉ cần biên dịch được | Thiết kế dễ sử dụng còn cần |
| --- | --- | --- |
| Chữ ký | Tên và danh sách kiểu tham số khác nhau | Chữ ký thể hiện ý nghĩa rõ ràng |
| Tham số | Compiler chấp nhận kiểu truyền vào | Thứ tự, đơn vị đo, giới hạn dễ đoán |
| Mặc định | Overload ít tham số có thể gọi được | Giá trị mặc định được định nghĩa nhất quán |
| Kết quả | Kiểu trả về hợp lệ | Cùng khái niệm kết quả cho cùng thao tác |
| Lỗi | Có thể ném exception | Quy tắc kiểm tra và lỗi không bất ngờ |
| Mở rộng | Thêm chữ ký mới có thể biên dịch | Không làm lời gọi cũ trở nên mơ hồ khi biên dịch lại |

**Nguyên tắc nền:** chỉ dùng chung tên khi các phương thức có thể được giải thích tự nhiên như **những cách gọi khác nhau của cùng một hành động**.

## 2. Xác định “thao tác cốt lõi” trước khi tạo overload

Giả sử cần một API tạo lời chào. Các biến thể hợp lý:

- `greet(name)`: chào bằng câu mặc định và lặp một lần;
- `greet(name, salutation)`: người gọi chọn câu chào, vẫn lặp một lần;
- `greet(name, salutation, repetitions)`: người gọi chọn cả câu chào và số lần lặp.

Ba lời gọi này đều trả về **một chuỗi lời chào**. Chúng có cùng ý nghĩa và khác nhau ở **mức độ cấu hình**. Đây là trường hợp nạp chồng tự nhiên.

Ngược lại, nếu `greet(name, int)` gửi lời chào qua email, còn `greet(name, String)` xóa lịch sử lời chào thì cùng tên `greet` không phản ánh được sự khác biệt lớn về hành vi. Nên đặt tên `sendGreeting`, `deleteGreetingHistory` hoặc các tên nghiệp vụ tương đương.

Một câu hỏi hữu ích: **“Nếu che danh sách tham số, tất cả phương thức cùng tên có đang trả lời một câu hỏi hoặc thực hiện một loại hành động hay không?”** Nếu không, nạp chồng thường không phải công cụ phù hợp.

## 3. Dùng một phương thức triển khai chung và để overload ngắn ủy quyền

Một cách thiết kế đáng tin cậy là chọn **một phương thức lõi** chứa kiểm tra đầu vào và logic chính; các overload tiện lợi gọi lại nó với giá trị mặc định. Nhờ vậy:

1. Quy tắc validation và định dạng kết quả nằm ở **một chỗ**.
2. Sửa lỗi trong thuật toán không phải sửa ba bản sao.
3. Các giá trị mặc định được đặt tường minh và dễ kiểm chứng.
4. Có thể viết unit test cho các con đường ủy quyền và những biên quan trọng.
5. Người dùng không phải tự truyền các giá trị mặc định lặp đi lặp lại.

Sơ đồ lời gọi:

~~~text
greet(name)
    |
    +--> greet(name, "Xin chào")
               |
               +--> greet(name, salutation, 1)
                               |
                               +--> validate
                               +--> tạo và trả chuỗi

greet(name, salutation, repetitions)
    |
    +--> validate
    +--> tạo và trả chuỗi
~~~

Mũi tên thể hiện **lời gọi ủy quyền** trong code, không phải quan hệ kế thừa lớp. Đây là cách tổ chức đơn giản cho những API có ít lựa chọn; khi số tùy chọn tăng quá nhiều, cần xem xét object cấu hình hoặc builder.

## 4. Ví dụ hoàn chỉnh: thiết kế GreetingApi

Tạo tệp **`GreetingApi.java`** trong thư mục làm việc. Mọi overload `greet` là `public static`, trả về `String`, không ghi stdout; chỉ `main` hiển thị kết quả demo.

~~~java
import java.util.StringJoiner;

public final class GreetingApi {
    private GreetingApi() {
        // Lớp tiện ích: không cần tạo instance.
    }

    public static String greet(String name) {
        return greet(name, "Xin chào");
    }

    public static String greet(String name, String salutation) {
        return greet(name, salutation, 1);
    }

    public static String greet(
            String name, String salutation, int repetitions) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (salutation == null || salutation.isBlank()) {
            throw new IllegalArgumentException("Lời chào không hợp lệ");
        }
        if (repetitions < 1 || repetitions > 5) {
            throw new IllegalArgumentException(
                    "Số lần phải từ 1 đến 5");
        }

        String sentence = salutation + ", " + name + "!";
        StringJoiner joiner = new StringJoiner(" | ");
        for (int i = 0; i < repetitions; i++) {
            joiner.add(sentence);
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        System.out.println(greet("An"));
        System.out.println(greet("Bình", "Chào"));
        System.out.println(greet("Mai", "Hello", 3));

        try {
            System.out.println(greet("An", "Hello", 0));
        } catch (IllegalArgumentException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 GreetingApi.java
java GreetingApi
~~~

**Stdout chính xác:**

~~~text
Xin chào, An!
Chào, Bình!
Hello, Mai! | Hello, Mai! | Hello, Mai!
Lỗi: Số lần phải từ 1 đến 5
~~~

### Vì sao ví dụ này dễ sử dụng?

| Lời gọi | Ý định của người gọi | Đường xử lý |
| --- | --- | --- |
| `greet("An")` | Lời chào đơn giản nhất | Tự dùng `"Xin chào"` và `1` lần |
| `greet("Bình", "Chào")` | Chọn lời chào | Tự dùng `1` lần |
| `greet("Mai", "Hello", 3)` | Cấu hình đầy đủ | Vào thẳng phương thức lõi |
| `greet("An", "Hello", 0)` | Số lần không hợp lệ | Cùng quy tắc validation, ném exception |

Các overload không tự in nội dung hay thay đổi dữ liệu bên ngoài, nên caller quyết định hiển thị ở console, giao diện hoặc lưu kết quả. Cùng một quy tắc kiểm tra được áp dụng dù gọi phiên bản ngắn hay dài.

**Phạm vi hợp đồng:** tên và lời chào phải không `null` và không chỉ gồm khoảng trắng; `repetitions` thuộc đoạn `1..5`. Ví dụ **giữ nguyên khoảng trắng đầu/cuối** của những chuỗi không rỗng; nó không tự `trim()`. Đây là quyết định có thể thay đổi theo yêu cầu, nhưng phải thống nhất giữa các overload.

## 5. Chọn overload “ngắn” dựa trên giá trị mặc định rõ ràng

Một overload ít tham số chỉ hữu ích nếu các giá trị bị lược bớt có **mặc định hợp lý, ổn định và có thể giải thích**.

Ví dụ:

~~~java
static String greet(String name) {
    return greet(name, "Xin chào");
}
~~~

Người gọi chọn `greet("An")` để áp dụng lời chào mặc định, không phải ngẫu nhiên bỏ qua một tham số bắt buộc. Còn overload hai tham số định nghĩa mặc định số lần là một:

~~~java
static String greet(String name, String salutation) {
    return greet(name, salutation, 1);
}
~~~

Hai đoạn trên trích ý tưởng từ chương trình hoàn chỉnh. Không nên phân tán những giá trị mặc định khác nhau khắp nhiều overload, khiến `greet(name)` và `greet(name, greeting)` có quy tắc lặp không nhất quán.

### Khi nào không nên đoán mặc định?

Nếu API yêu cầu **loại tiền tệ**, **múi giờ**, **đơn vị thời gian** hoặc **quyền truy cập**, một mặc định sai có thể gây lỗi nghiêm trọng. Ví dụ `schedule(10)` không đủ rõ số `10` là giây hay phút. Hãy ưu tiên kiểu có ý nghĩa:

~~~java
void schedule(java.time.Duration delay) {
    // ...
}
~~~

Đây là **minh họa chữ ký**, chưa có thân nghiệp vụ; kiểu `Duration` làm rõ ý nghĩa thời lượng hơn một số `int` không kèm đơn vị. Không bắt buộc lúc nào cũng thêm overload `schedule(int seconds)`, vì nó có thể khiến người dùng hiểu sai đơn vị.

## 6. Quy tắc nhất quán về kết quả, lỗi và tác dụng phụ

Các overload cùng tên nên duy trì một **hợp đồng có thể dự đoán**:

- **Đầu vào:** cùng một khái niệm tham số nên được kiểm tra theo cùng tiêu chuẩn. Trong `greet`, mọi đường gọi đều từ chối tên rỗng.
- **Đầu ra:** cùng một ý nghĩa kết quả. Các overload `greet` đều trả **nội dung lời chào**, không có overload nào bất ngờ trả số ký tự.
- **Tác dụng phụ:** tránh trường hợp phiên bản nhận một đối số chỉ tính toán, còn phiên bản nhận hai đối số tự động ghi tệp hoặc gửi email mà tên phương thức không thể hiện.
- **Ngoại lệ:** các trường hợp sai tương đương nên được thông báo nhất quán; đừng một nơi im lặng bỏ qua, nơi khác ném lỗi mà không có chủ đích.
- **Giá trị rỗng và `null`:** xác định rõ được chấp nhận, được diễn giải như mặc định hay bị từ chối.

Điều này không có nghĩa mọi overload **bắt buộc** có cùng kiểu trả về: Java cho phép khác kiểu trả về nếu danh sách tham số đã khác chữ ký. Tuy vậy, **về thiết kế API**, thay đổi kiểu và ý nghĩa kết quả giữa những overload giống nhau về mục đích thường gây khó sử dụng.

Ví dụ đáng ngờ:

~~~java
int find(String key) { return 0; }
String find(String key, boolean verbose) { return ""; }
~~~

Hai chữ ký khác nhau, nhưng thêm `verbose` lại thay hẳn kiểu và ý nghĩa kết quả. Tình huống này gợi ý API đang gộp hai mục đích và nên có tên rõ nghĩa hoặc kiểu kết quả nhất quán. Đây là **đoạn minh họa**, không phải chức năng tìm kiếm hoàn chỉnh.

## 7. Nạp chồng không được phân biệt chỉ bằng kiểu trả về

Hai khai báo sau **không thể cùng đặt trong một lớp**:

~~~java
int size() {
    return 1;
}

long size() {
    return 1L;
}
~~~

Cả hai có cùng chữ ký `size()`. Java không cho phép chọn overload dựa vào kiểu biến nhận kết quả như `long result = size();`.

Các thay đổi **không tạo chữ ký mới**:

| Thay đổi | Ví dụ | Có tạo overload mới không? |
| --- | --- | --- |
| Chỉ đổi return type | `int f(int)` thành `long f(int)` | Không |
| Chỉ đổi tên tham số | `f(int amount)` thành `f(int value)` | Không |
| Chỉ đổi `throws` | `throws IOException` thành `throws SQLException` | Không |
| Chỉ đổi access modifier | `private f(int)` thành `public f(int)` | Không |
| Chỉ thêm/bớt `static` | `static f(int)` và `f(int)` | Không |
| Đổi số lượng tham số | `f(int)` thành `f(int,int)` | Có |
| Đổi kiểu tham số | `f(int)` thành `f(long)` | Có |
| Đổi thứ tự kiểu tham số | `f(int,long)` thành `f(long,int)` | Có, nhưng lời gọi có thể mơ hồ |

Đối với generic method, Java còn có các quy tắc về kiểu tham số generic, *subsignature* và *erasure*, nên bảng là cách đọc nhanh cho những trường hợp cơ bản; không thay thế toàn bộ Java Language Specification.

## 8. Tránh overload khiến `null` mơ hồ

Một lỗi thiết kế dễ thấy là cung cấp nhiều overload nhận **các kiểu tham chiếu không liên quan** ở cùng vị trí:

~~~java
static void deliver(String text, java.time.Duration delay) { }
static void deliver(String text, java.util.Locale locale) { }
~~~

Hai khai báo **khác chữ ký và có thể cùng tồn tại**. Nhưng:

~~~java
deliver("Xin chào", null); // LỖI: lời gọi ambiguous
~~~

`null` phù hợp cả `Duration` và `Locale`; không kiểu nào là subtype của kiểu kia. Compiler không thể chọn một phương thức duy nhất.

Có thể ép kiểu:

~~~java
deliver("Xin chào", (java.time.Duration) null);
~~~

Nhưng ép kiểu chỉ giúp compiler lựa chọn, **không bảo đảm `null` là đối số hợp lệ theo hợp đồng**. API công khai buộc người dùng ép kiểu để gọi với `null` thường là tín hiệu cần xem lại thiết kế.

### Giải pháp ưu tiên: tên riêng cho ý nghĩa riêng

Thay vì dùng `deliver(text, Duration)` và `deliver(text, Locale)` để thực hiện hai kiểu hành vi khác nhau, cân nhắc:

~~~java
void deliverAfter(String text, java.time.Duration delay) { }
void deliverLocalized(String text, java.util.Locale locale) { }
~~~

Đây chỉ là **khai báo minh họa**; tên làm rõ hơn vai trò của tham số thứ hai và loại bỏ xung đột overload tại chỗ này.

Nếu có overload `show(Object)` và `show(String)`, lời gọi `show(null)` có thể chọn `show(String)` vì `String` cụ thể hơn `Object`. Tuy nhiên việc chọn được một overload **không có nghĩa** lựa chọn đó đúng ý người dùng. Khi API dự kiến xử lý `null`, cần đặt quy tắc rõ ràng hoặc tránh nhóm overload gây hiểu nhầm.

## 9. Chọn kiểu tham số để hạn chế chuyển đổi bất ngờ

Java có cơ chế chọn overload theo nhiều pha. Đối với trường hợp phổ biến, **mở rộng kiểu nguyên thủy** được xét trong pha strict trước khi cần boxing/unboxing và trước lời gọi varargs theo dạng variable arity.

Tạo tệp **`OverloadChoiceDemo.java`**:

~~~java
public class OverloadChoiceDemo {
    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    static String choose(int... values) {
        return "varargs: " + values.length;
    }

    public static void main(String[] args) {
        System.out.println(choose(5));
        System.out.println(choose(Integer.valueOf(5)));
        System.out.println(choose());
        System.out.println(choose(5, 6));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OverloadChoiceDemo.java
java OverloadChoiceDemo
~~~

Stdout:

~~~text
long
Integer
varargs: 0
varargs: 2
~~~

`choose(5)` chọn `long`, bởi `5` có kiểu `int`, có thể được mở rộng thành `long` trong pha strict, trước khi cần boxing thành `Integer`. `choose(Integer.valueOf(5))` chọn `Integer` nhờ kiểu đối số khớp trực tiếp. `choose()` và `choose(5, 6)` cần varargs.

**Bài học thiết kế:** không nên tạo các overload `int`, `long`, `Integer` và `Object...` chỉ để “nhận được mọi thứ” nếu hành vi thực sự không cần phân biệt các kiểu ấy. Người dùng có thể đoán sai overload được chọn, và thêm một overload trong bản cập nhật thư viện có thể thay đổi kết quả phân giải khi mã khách hàng được biên dịch lại.

Nếu API yêu cầu một đơn vị hoặc miền giá trị rõ ràng, hãy chọn **một kiểu tham số chính** và thêm overload chuyển đổi chỉ khi lợi ích sử dụng đủ lớn.

## 10. Varargs tiện lợi nhưng tăng rủi ro mơ hồ

Varargs cho phép lời gọi không phần tử, một phần tử hoặc nhiều phần tử, chẳng hạn `log("A", "B")` cho `log(String... messages)`. Tuy nhiên khi kết hợp với overload thông thường, cần xét các trường hợp sau:

~~~java
static void log(String message) { }
static void log(String... messages) { }
~~~

Hai khai báo này hợp lệ: chữ ký lần lượt là `log(String)` và `log(String[])`. Với `log("A")`, phiên bản `log(String)` được chọn ở pha fixed arity, trước khi compiler cần gộp một phần tử thành mảng cho varargs.

Tuy nhiên, `log(null)` có thể **mơ hồ**: một đối số `null` phù hợp với cả `String` và `String[]`, mà hai kiểu này không là subtype của nhau. Cần nói rõ ý định bằng `log((String) null)` hoặc `log((String[]) null)`, nhưng cách tốt hơn là thiết kế một API không buộc caller đối mặt với tình huống khó đoán.

Hai phương thức varargs khác kiểu phần tử cũng có thể gây lỗi khi gọi không đối số:

~~~java
static void collect(String... values) { }
static void collect(Integer... values) { }

// collect(); // LỖI: không chọn được overload duy nhất
~~~

**Varargs và mảng có cùng kiểu tham số trong chữ ký:** `print(String... xs)` không thể tồn tại cùng `print(String[] xs)` trong một lớp; cả hai có chữ ký tương đương `print(String[])`. Vì vậy không thể tạo overload “riêng cho lời gọi truyền mảng” chỉ bằng cách đổi `...` thành `[]`.

**Khuyến nghị:** đưa varargs vào API khi lợi ích gọi nhiều giá trị rời là rõ ràng, và kiểm tra các lời gọi rỗng, `null`, truyền mảng, đồng thời tránh nhóm overload varargs không liên quan.

## 11. Tên tham số và thứ tự tham số phải chống nhầm lẫn

Xét hai chữ ký hợp lệ:

~~~java
void schedule(String task, int priority) { }
void schedule(int priority, String task) { }
~~~

Mặc dù hai overload khác thứ tự kiểu, việc cung cấp cả hai cách gọi thường không mang lại lợi ích rõ rệt. Nó buộc người dùng nhớ hai quy ước cùng lúc.

Trường hợp nguy hiểm hơn:

~~~java
void copy(String source, String destination) { }
~~~

Lời gọi `copy(destination, source)` vẫn **biên dịch được** vì hai đối số đều `String`. Không thể thêm một overload chỉ đảo **tên biến tham số** để giải quyết vì chữ ký vẫn là `copy(String,String)`.

Để dễ sử dụng:

- Đặt tham số theo thứ tự có thể dự đoán, ví dụ “nguồn, đích”, và dùng nhất quán ở mọi API liên quan.
- Khi hai giá trị cùng kiểu nhưng khác vai trò quan trọng, cân nhắc kiểu miền nghiệp vụ riêng như `SourcePath` và `DestinationPath`, hoặc một đối tượng yêu cầu.
- Dùng tên tham số rõ nghĩa trong khai báo và Javadoc; dù không góp vào chữ ký, chúng giúp đọc code và hỗ trợ IDE.
- Tránh overload chỉ thay đổi trật tự mà không bổ sung khả năng hữu ích thực sự.

Một dấu hiệu xấu khác là các tham số `boolean` ít ý nghĩa: `send(message, true, false)` khiến người đọc không biết `true` đại diện cho điều gì. Các phương thức có tên như `sendQuietly`, `sendWithReceipt` hoặc đối tượng cấu hình có thể phù hợp hơn tùy nghiệp vụ.

## 12. Generics: tránh quá tải bị đụng type erasure

Java không cho phép nạp chồng chỉ dựa trên **đối số kiểu generic** khi erasure làm hai chữ ký xung đột:

~~~java
void save(java.util.List<String> names) { }
void save(java.util.List<Integer> numbers) { }
~~~

Đây là **ví dụ cố ý không biên dịch** khi hai khai báo nằm trong cùng lớp; chúng dẫn tới *name clash* do kiểu tham số đều bị xóa về `List`.

Một giải pháp, nếu hành vi giống nhau, là một phương thức generic:

~~~java
static <T> int count(java.util.List<T> items) {
    return items.size();
}
~~~

Đây là **đoạn minh họa trong lớp**, không có `main`. Cùng một `count` hoạt động với danh sách chứa `String`, `Integer` hoặc kiểu khác mà không cần overload theo phần tử. Có thể dùng `List<?>` nếu chỉ cần quan sát các phần tử mà không phụ thuộc loại `T`.

Nếu hành vi của `saveNames` và `saveScores` thật sự khác nhau, đặt hai tên rõ ý nghĩa còn tốt hơn cố tạo overload không phù hợp. Cũng có thể dùng kiểu wrapper miền nghiệp vụ riêng để phân biệt **đối tượng đầu vào**, nhưng tránh tạo kiểu mới chỉ để né compiler khi hai thao tác về cơ bản nên có tên khác.

## 13. Constructor overloading: cùng nguyên tắc, nhưng cần tránh bẫy boolean

Constructor cũng có thể nạp chồng, và có thể ủy quyền bằng `this(...)`. Ví dụ:

~~~java
class RetryPolicy {
    private final int attempts;
    private final long delayMillis;

    RetryPolicy() {
        this(3, 1000L);
    }

    RetryPolicy(int attempts) {
        this(attempts, 1000L);
    }

    RetryPolicy(int attempts, long delayMillis) {
        if (attempts < 1 || delayMillis < 0) {
            throw new IllegalArgumentException("Cấu hình không hợp lệ");
        }
        this.attempts = attempts;
        this.delayMillis = delayMillis;
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, không có `main`. Trong Java 17, lời gọi `this(...)` ở constructor phải là **câu lệnh đầu tiên**. Mọi đường tạo instance đều đi qua constructor nhận hai tham số và cùng áp dụng validation.

Thiết kế này dễ dùng vì mặc định rõ: ba lần thử, độ trễ 1000 ms. Nhưng caller có thể không biết `1000L` là đơn vị nào khi chỉ nhìn lời gọi `new RetryPolicy(3, 1000L)`. Với API mới, kiểu `Duration` và tên tham số `delay` thường truyền đạt ý nghĩa tốt hơn:

~~~java
RetryPolicy(int attempts, java.time.Duration delay) {
    // Khai báo minh họa; cần xác thực delay không null và không âm.
}
~~~

**Không thể đặt nguyên constructor minh họa này trong cùng lớp `RetryPolicy` bên trên mà không viết thân hợp lệ**; nó chỉ gợi ý thiết kế API thay thế.

Constructor có quá nhiều overload thường là dấu hiệu đối tượng có nhiều tùy chọn cấu hình độc lập; cân nhắc factory method hoặc builder.

## 14. Khi nào nên thay overload bằng factory method hoặc builder?

Nếu có nhiều tham số tùy chọn độc lập như định dạng, locale, đường dẫn, timeout, retries, cấp độ log, việc thêm overload cho mọi tổ hợp có thể gây “bùng nổ chữ ký”:

~~~text
send(message)
send(message, retryCount)
send(message, timeout)
send(message, locale)
send(message, retryCount, timeout)
send(message, retryCount, locale)
send(message, timeout, locale)
send(message, retryCount, timeout, locale)
...
~~~

Đây là sơ đồ các khả năng cấu hình, **không phải một tập chữ ký Java đã được kiểm chứng**. Một số tổ hợp có thể đụng kiểu hoặc mơ hồ; số tổ hợp tăng nhanh theo số lựa chọn.

**Gợi ý lựa chọn:**

| Tình huống | Thiết kế thường hợp lý |
| --- | --- |
| 2–3 cách nhập của cùng thao tác, mặc định hiển nhiên | Overload |
| Hành vi khác bản chất | Các tên phương thức khác nhau |
| Nhiều tùy chọn độc lập | Object cấu hình, builder |
| Constructor không rõ ngữ nghĩa của tham số | Static factory method có tên rõ |
| Nhiều tham số cùng primitive/`String` dễ đảo vị trí | Kiểu giá trị miền nghiệp vụ hoặc request object |
| Overload tạo lời gọi `null`/lambda mơ hồ | API mang tên khác hoặc kiểu đối số rõ ràng |

Một cách dùng builder về mặt ý tưởng:

~~~java
// Minh họa cách gọi, không phải chương trình hoàn chỉnh.
Request request = Request.builder()
        .message("Xin chào")
        .retryCount(3)
        .timeout(java.time.Duration.ofSeconds(5))
        .build();
sender.send(request);
~~~

Builder có chi phí thêm loại và mã, vì vậy không nên ép mọi API chỉ có một tùy chọn đơn giản dùng builder. Mục tiêu là chọn độ phức tạp **phù hợp số chiều cấu hình**, không tuân theo một khuôn mẫu cố định.

## 15. Phân giải overload dựa trên kiểu tĩnh, không dựa vào class runtime của đối số

Một hiểu lầm phổ biến là Java luôn tự chọn overload nhận kiểu **thực tế của object** ở runtime. Với overloading, compiler chọn chữ ký dựa trên thông tin kiểu tại điểm gọi.

Tạo tệp độc lập **`StaticTypeOverloadDemo.java`**:

~~~java
public class StaticTypeOverloadDemo {
    static String describe(Object value) {
        return "Object";
    }

    static String describe(String value) {
        return "String";
    }

    public static void main(String[] args) {
        Object first = "An";
        String second = "An";

        System.out.println(describe(first));
        System.out.println(describe(second));
        System.out.println(describe((String) first));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StaticTypeOverloadDemo.java
java StaticTypeOverloadDemo
~~~

Stdout:

~~~text
Object
String
String
~~~

Dù `first` thực sự tham chiếu tới một `String`, kiểu **khai báo** là `Object`. Do vậy `describe(first)` chọn overload nhận `Object`. Ép kiểu rõ ràng sang `String` ở `describe((String) first)` thay đổi kiểu biểu thức tại điểm gọi và khiến overload `String` được chọn.

Không nhầm với **overriding**: sau khi compiler chọn **chữ ký** của một instance method, triển khai override trên lớp runtime của đối tượng nhận vẫn có thể được dispatch động. Overloading và overriding là hai cơ chế khác nhau; thiết kế API nên tránh phụ thuộc vào sự nhầm lẫn này.

## 16. Bổ sung overload có thể gây lỗi tương thích khi biên dịch lại

Giả sử phiên bản đầu của API chỉ có:

~~~java
static String show(Object value) {
    return "Object";
}
~~~

Người dùng viết `show("hello")` và compiler chọn `show(Object)`. Sau đó thư viện thêm:

~~~java
static String show(String value) {
    return "String";
}
~~~

Khi mã khách hàng được **biên dịch lại**, lời gọi `show("hello")` có thể chọn `show(String)` cụ thể hơn, làm thay đổi hành vi dù phía caller **không sửa mã nguồn**. Đây là vấn đề tương thích **ở cấp source/recompilation**.

Một rủi ro khác:

~~~java
static void send(String value) { }
static void send(Integer value) { }
~~~

Nếu trước đây chỉ có `send(String)`, lời gọi `send(null)` có thể biên dịch và chọn `String`. Sau khi bổ sung `send(Integer)`, lời gọi cũ trở thành **mơ hồ khi biên dịch lại**.

Các ví dụ là những khai báo minh họa, không phải chương trình hoàn chỉnh. Vì vậy trước khi mở rộng API public, cần kiểm tra ít nhất:

- Lời gọi cũ dùng literal nguyên và boxing/widening;
- Lời gọi `null` và lời gọi varargs không đối số;
- Các kiểu có quan hệ kế thừa như `Object` và `String`;
- Các phương thức generic, lambda hoặc method reference nếu API có dùng;
- Các chương trình khách hàng quan trọng sau khi **recompile**.

**Lưu ý:** khả năng tương thích nhị phân của bytecode cũ và kết quả phân giải khi biên dịch lại **không phải một vấn đề**. Thêm overload có thể không thay đổi lời gọi đã được biên dịch trước đó, nhưng lại đổi lựa chọn khi compile mã nguồn mới.

## 17. Đánh giá “dễ sử dụng” bằng ví dụ lời gọi, không chỉ nhìn khai báo

Trước khi chốt thiết kế, hãy viết thử code ở phía **người dùng API**:

~~~java
GreetingApi.greet("An");
GreetingApi.greet("Mai", "Hello");
GreetingApi.greet("Mai", "Hello", 3);
~~~

Ba dòng thể hiện các mục đích rõ ràng, nhưng cần xem xét thêm:

- Người gọi có thể suy ra **lời chào mặc định** và **giới hạn repetitions** từ tên/Javadoc hoặc autocomplete không?
- Các overload có luôn trả về cùng loại thông tin không?
- Nếu một tham số bằng `null`, người gọi nhận lỗi rõ hay compiler báo ambiguous?
- Có overload mới nào sẽ làm `greet("An")` chọn khác đi sau khi thư viện cập nhật không?
- Có thể đọc tên và các tham số mà **không cần đoán kiểu thực** của một biến không?
- Nếu một overload ngắn dùng giá trị mặc định, nó có **ủy quyền về cùng logic** không?
- Mỗi giá trị mặc định và đơn vị đo đã được tài liệu hóa chưa?

Đừng chỉ thử những lời gọi “đẹp”. Hãy cố tạo các lời gọi gây hiểu nhầm như `f(null)`, `f()`, `f(0)`, `f(1,2)`, mảng rỗng, kiểu wrapper và biến tham chiếu có kiểu tĩnh rộng hơn.

## 18. Kiểm thử tập overload theo một ma trận nhỏ

Một bộ kiểm thử tốt cần xác nhận **đúng phiên bản được chọn** và **đúng kết quả/hợp đồng**. Với `GreetingApi`, các trường hợp kiểm thử cốt lõi:

| Lời gọi | Kết quả hoặc lỗi cần kiểm tra |
| --- | --- |
| `greet("An")` | `"Xin chào, An!"` |
| `greet("An", "Hi")` | `"Hi, An!"` |
| `greet("An", "Hi", 2)` | `"Hi, An! | Hi, An!"` |
| `greet("An", "Hi", 1)` | Kết quả giống overload hai tham số |
| `greet("An", "Hi", 5)` | Có đúng 5 lời chào |
| `greet("An", "Hi", 0)` | `IllegalArgumentException` |
| `greet("An", "Hi", 6)` | `IllegalArgumentException` |
| `greet(null)` | `IllegalArgumentException` |
| `greet("   ")` | `IllegalArgumentException` |
| `greet("An", null)` | `IllegalArgumentException` |
| `greet("An", "")` | `IllegalArgumentException` |

Không cần chạy toàn bộ trường hợp bằng `System.out.println` trong ví dụ chính; với dự án thật có thể dùng JUnit và các assertion so sánh giá trị/kỳ vọng exception. Khi một overload chỉ chuyển tiếp, nên kiểm tra rằng kết quả của cách gọi ngắn **bằng cách gọi dài với mặc định đã công bố**.

Đối với overload chịu ảnh hưởng compiler, cần thêm các bài kiểm tra **biên dịch thành công/thất bại** hoặc các tệp nhỏ chạy với `javac`: chẳng hạn `collect()` mơ hồ có thực sự bị từ chối không. Không thể thay thế hoàn toàn loại kiểm tra compile-time này bằng unit test runtime.

## 19. Những thiết kế nên tránh và cách cải thiện

| Thiết kế có vấn đề | Vì sao khó dùng | Hướng cải thiện |
| --- | --- | --- |
| `send(String)` và `send(String,boolean,boolean)` | Không rõ ý nghĩa hai cờ | Tên thể hiện chế độ, enum hoặc options |
| `parse(String)` trả object, `parse(String,int)` vừa parse vừa ghi DB | Cùng tên nhưng side effect khác bất ngờ | Tách parse và persist |
| `read(String path)`, `read(Path path)` nhưng xử lý lỗi khác hẳn | Người dùng khó dự đoán | Dùng cùng hợp đồng, overload chỉ đổi cách biểu diễn đầu vào |
| `set(int,long)` và `set(long,int)` | `set(1,2)` có thể ambiguous | Cấu trúc tham số nhất quán, kiểu miền nghiệp vụ rõ |
| `log(String)`, `log(String...)` mà chưa xét `null` | `log(null)` có thể mơ hồ | Thiết kế lại overload hoặc loại bỏ dạng thừa |
| `process(List<String>)`, `process(List<Integer>)` | Type erasure gây name clash | Generic method, tên khác hoặc kiểu đầu vào khác |
| 8–16 constructor chỉ khác các tập option | Caller khó nhớ thứ tự và defaults | Builder/options/factory |
| Nhiều overload sao chép nguyên thuật toán | Sửa lỗi thiếu một nhánh, behavior lệch | Một core implementation và delegating overloads |
| Overload thêm nhưng không kiểm thử mã cũ | Đổi overload được chọn khi recompile | Kiểm tra khả năng tương thích nguồn |
| Đơn vị `int delay` không rõ | Dùng sai giây/mili giây | `Duration` hoặc tên tham số/kiểu rõ đơn vị |

Cách cải thiện tốt nhất không nhất thiết là **thêm overload**. Đôi khi giải pháp là **xóa một overload thừa**, chọn tên mới hoặc tạo một request object được thiết kế tốt.

## 20. Bài tập tự luyện

**Bài 1 — Thiết kế overload.** Một API tính nhãn sản phẩm cần `label(code)`, `label(code,locale)` và `label(code,locale,style)`. Hãy chỉ ra overload nào nên là phương thức lõi, các overload khác nên chuyển tiếp ra sao và cần công bố những giá trị mặc định nào.

**Bài 2 — Nhận diện trùng chữ ký.** Có thể khai báo đồng thời `int count(String text)` và `long count(String value)` không? Vì sao việc đổi tên biến hoặc kiểu trả về không tạo chữ ký mới?

**Bài 3 — Null ambiguity.** Với `send(String,Duration)` và `send(String,Locale)`, lời gọi `send("Hi",null)` có hợp lệ không? Hãy đề xuất cách thiết kế loại bỏ khó hiểu cho caller.

**Bài 4 — Chuyển đổi kiểu.** Trong `OverloadChoiceDemo`, vì sao `choose(5)` chọn `long` chứ không chọn `Integer` hoặc varargs? Điều gì xảy ra với `choose(Integer.valueOf(5))`?

**Bài 5 — Varargs.** Nếu có `log(String)` và `log(String...)`, lời gọi `log("A")` chọn phiên bản nào? `log(null)` có rủi ro gì?

**Bài 6 — Tham số tùy chọn.** Một phương thức có sáu tùy chọn cấu hình độc lập. Có nên tạo overload cho mọi tổ hợp? Khi nào request object hoặc builder dễ dùng hơn?

**Bài 7 — Kiểu tĩnh.** Với `describe(Object)`, `describe(String)` và biến `Object x = "hello";`, tại sao `describe(x)` không tự chọn `describe(String)`?

**Bài 8 — Tương thích API.** Vì sao bổ sung `show(String)` vào API đang có `show(Object)` có thể thay đổi hành vi của `show("x")` khi ứng dụng khách được biên dịch lại?

**Đáp án tham khảo:**

1. Dùng phiên bản ba tham số làm lõi, hai phiên bản ngắn chuyển tiếp với `locale` và `style` mặc định được chọn theo yêu cầu nghiệp vụ; tránh giả định locale mặc định khi ứng dụng cần kết quả xác định.
2. Không; cả hai là `count(String)`, kiểu trả về và tên tham số không tạo khác biệt chữ ký.
3. Không; `Duration` và `Locale` đều nhận `null`, không có lựa chọn cụ thể hơn. Dùng tên `sendAfter`/`sendLocalized` hoặc request object phù hợp.
4. Mở rộng nguyên thủy `int` thành `long` được xét trước boxing và lời gọi varargs; đối số `Integer` chọn overload `Integer` tương ứng.
5. `log("A")` chọn `log(String)`; `log(null)` mơ hồ giữa `String` và `String[]`.
6. Thường không: quá nhiều tổ hợp tạo API khó hiểu. Builder/options giúp cấu hình theo tên và kiểm tra tập trung.
7. Compiler dùng kiểu tĩnh `Object` của biến để phân giải overload; không dựa vào việc object hiện tại là `String`.
8. Khi recompile, kiểu `String` là ứng viên cụ thể hơn `Object`, nên compiler có thể chọn phương thức mới.

## 21. Tài liệu tham khảo

- [Java Language Specification 17, §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2): các thành phần chữ ký, subsignature và erasure.
- [Java Language Specification 17, §8.4.9 — Overloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.9): quy tắc khai báo phương thức nạp chồng.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): các giai đoạn tìm ứng viên, most-specific method, varargs và ngữ nghĩa gọi.
- [Java SE 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): kiểu thời lượng rõ đơn vị.
- [Java SE 17 API — StringJoiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html): ghép phần tử chuỗi trong ví dụ hoàn chỉnh.

**Ghi nhớ:** overload tốt không chỉ là các chữ ký khác nhau. Nó là **một nhóm cách gọi cùng ý nghĩa**, có **mặc định rõ ràng**, **một luồng kiểm tra/triển khai nhất quán**, tránh **ambiguity** và **chuyển đổi kiểu bất ngờ**, đồng thời **dễ mở rộng** mà không làm mã khách hàng khó dùng. Hãy thiết kế từ góc nhìn caller trước, rồi mới chọn bao nhiêu overload là đủ.
