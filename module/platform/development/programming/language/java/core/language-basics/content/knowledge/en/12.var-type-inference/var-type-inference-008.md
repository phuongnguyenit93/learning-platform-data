# Chọn `var` khi kiểu vẫn rõ ràng với người đọc — Java 17+

`var` cho phép Java **suy luận kiểu tĩnh của biến cục bộ** từ biểu thức khởi tạo. Lợi ích chính là giảm lặp tên kiểu, **không phải** biến Java thành ngôn ngữ kiểu động. Một khai báo tốt cần đồng thời đạt hai mục tiêu:

1. **Compiler biết kiểu chính xác** để kiểm tra mọi phép gán và lời gọi tiếp theo.
2. **Người đọc hiểu đủ nhanh** biến chứa loại dữ liệu gì, ý nghĩa nghiệp vụ ra sao, và các thao tác nào hợp lệ.

Hãy chọn `var` **khi biểu thức khởi tạo, tên biến và ngữ cảnh khiến kiểu đủ rõ**. Khi kiểu đích hoặc ý đồ thiết kế không rõ, khai báo tường minh thường tốt hơn.

~~~java
var student = new Student("An", 8);  // De thay la Student.
var names = new ArrayList<String>(); // De thay kieu phan tu String.
var retryCount = 3;                  // Don gian va ro rang: int.

// Can the hien y do API la interface:
List<String> visibleNames = new ArrayList<>();
~~~

Cả `var` và khai báo tường minh đều có chỗ đứng. **Không có quy tắc “luôn dùng” hoặc “luôn tránh” `var`** áp dụng cho mọi dự án.

## 1. Bảng quyết định nhanh

| Tình huống | Ví dụ | Gợi ý | Vì sao |
| --- | --- | --- | --- |
| Constructor cho biết lớp | `var user = new User("An");` | **Thường dùng `var`** | Tên kiểu hiện ngay tại initializer |
| Kiểu phần tử generic nêu rõ | `var names = new ArrayList<String>();` | **Có thể dùng `var`** | `String` không bị che khuất |
| Literal đơn giản | `var retries = 3;` | **Có thể dùng `var`** | Kiểu `int` dễ nhận biết |
| Kết quả phương thức khó đoán | `var result = load();` | **Cân nhắc viết kiểu** | Phải tra chữ ký `load()` mới hiểu kết quả |
| Muốn ràng buộc qua interface | `List<String> items = new ArrayList<>();` | **Viết kiểu tường minh** | Làm rõ API mà biến cam kết |
| Diamond thiếu kiểu phần tử | `var items = new ArrayList<>();` | **Nên tránh** | Có thể suy thành `ArrayList<Object>` |
| Giá trị số cần độ rộng cụ thể | `long bytes = 1_000_000;` | **Cân nhắc viết kiểu** | Tránh nhầm `int`, `long` hoặc số thực |
| Chuỗi gọi phương thức phức tạp | `var summary = pipeline.compute();` | **Viết rõ nếu giúp hiểu** | Tên phương thức không bảo đảm rõ kiểu |
| Biến phần tử trong vòng lặp | `for (var item : typedItems)` | **Thường dùng `var`** | Có thể suy kiểu từ collection/mảng |

“Rõ” là tiêu chí dành cho người đọc **tại vị trí khai báo**, không phải chỉ người đã thuộc toàn bộ mã nguồn.

## 2. Ví dụ Java 17+ biên dịch và chạy bằng CLI

Tạo file UTF-8 **`ReadableVarDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ReadableVarDemo {
    record Student(String name, int points) {}

    static List<Student> loadStudents() {
        return List.of(
                new Student("An", 8),
                new Student("Binh", 9));
    }

    static String normalizeName(String text) {
        return text.strip().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) {
        var retries = 3;
        var language = "Java";
        var first = new Student("Lan", 10);

        System.out.println("retries=" + retries);
        System.out.println("language=" + language);
        System.out.println("first=" + first.name()
                + ":" + first.points());

        var names = new ArrayList<String>();
        names.add("An");
        names.add("Binh");
        System.out.println("names=" + String.join(",", names));

        // Muon API bien la List, viet kieu interface tuong minh.
        List<String> publishedNames = new ArrayList<>();
        publishedNames.add("Lan");
        System.out.println("published=" + publishedNames);

        // Ten ham chua cho nguoi doc biet chac kieu tra ve.
        List<Student> students = loadStudents();
        var total = 0;
        for (var student : students) {
            total += student.points();
        }
        System.out.println("studentCount=" + students.size());
        System.out.println("totalPoints=" + total);

        // Chon String tường minh de bieu dat hop dong du lieu.
        String normalizedName = normalizeName("  an  ");
        System.out.println("normalized=" + normalizedName);

        // Kieu co the thay ngay qua literal va API tieu chuan.
        var uppercase = "java".toUpperCase(Locale.ROOT);
        System.out.println("uppercase=" + uppercase);

        var primitive = Integer.parseInt("7");
        var wrapper = Integer.valueOf("7");
        System.out.println("parsed=" + primitive);
        System.out.println("wrapperType="
                + wrapper.getClass().getSimpleName());

        // Diamond khong co kieu dich ro rang: suy ra Object.
        var mixed = new ArrayList<>();
        mixed.add("text");
        mixed.add(7);
        System.out.println("mixed=" + mixed);

        var positions = new StringBuilder();
        for (var i = 0; i < 3; i++) {
            positions.append(i);
        }
        System.out.println("positions=" + positions);

        var integerDivision = 5 / 2;
        var decimalDivision = 5 / 2.0;
        System.out.println("integerDivision=" + integerDivision);
        System.out.println("decimalDivision=" + decimalDivision);

        long largeValue = 1_000_000_000L + 1_000_000_000L;
        System.out.println("largeValue=" + largeValue);
    }
}
~~~

Dùng JDK 17 trở lên. Tại thư mục chứa file, mở PowerShell hoặc Bash và chạy:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ReadableVarDemo.java
java ReadableVarDemo
~~~

**Exact expected output** của lệnh `java ReadableVarDemo` (không tính dòng phiên bản JDK):

~~~text
retries=3
language=Java
first=Lan:10
names=An,Binh
published=[Lan]
studentCount=2
totalPoints=17
normalized=AN
uppercase=JAVA
parsed=7
wrapperType=Integer
mixed=[text, 7]
positions=012
integerDivision=2
decimalDivision=2.5
largeValue=2000000000
~~~

### Vì sao chương trình chọn kiểu khai báo khác nhau?

- `var first = new Student(...)` rõ vì tên lớp `Student` hiện ngay tại `new`; biến suy ra kiểu `Student`.
- `var names = new ArrayList<String>()` thể hiện rõ kiểu phần tử. Trong khi đó, `List<String> publishedNames = new ArrayList<>()` chọn **kiểu interface `List<String>`** làm hợp đồng sử dụng thay vì cố định kiểu khai báo của biến là `ArrayList<String>`.
- `List<Student> students = loadStudents()` làm rõ kiểu kết quả ngay cho người đọc, không buộc họ mở định nghĩa `loadStudents()`.
- Trong `for (var student : students)`, kiểu của phần tử đã rõ từ `List<Student>`, nên tránh lặp `Student` mà vẫn dễ hiểu.
- `String normalizedName = normalizeName(...)` làm rõ kiểu dữ liệu của một hàm nghiệp vụ có tên không nhất thiết nói hết chữ ký.
- `var primitive = Integer.parseInt("7")` suy ra `int`, còn `var wrapper = Integer.valueOf("7")` suy ra `Integer`. Hai kết quả có thể cùng hiển thị là 7 nhưng **khác kiểu**.
- `var mixed = new ArrayList<>()` không có kiểu đích generic cụ thể, nên trong trường hợp này `<>` suy ra `Object` và kiểu biến là `ArrayList<Object>`. Điều đó giải thích tại sao danh sách nhận được cả `String` và `Integer`.
- `var integerDivision = 5 / 2` có kiểu `int`, giá trị 2; `var decimalDivision = 5 / 2.0` có kiểu `double`, giá trị 2.5. `var` không sửa kiểu của biểu thức trước khi gán.

## 3. `var` vẫn là kiểu tĩnh, không phải “kiểu tùy biến”

~~~java
var count = 10; // int.
count = 20;     // Hop le.
// count = "20"; // LOI bien dich: String khong gan duoc cho int.

var name = "An"; // String.
// name = 123;    // LOI bien dich: int khong gan duoc cho String.
~~~

Compiler suy kiểu **một lần tại khai báo**, sau đó áp dụng các quy tắc Java bình thường (gán kiểu, overload, generic, truy cập thành viên).

Vì vậy đừng chọn `var` chỉ vì muốn biến “linh hoạt hơn”. Nếu một biến cần mang kiểu cơ sở hoặc interface để nhận nhiều lớp triển khai, hãy **chủ động chọn kiểu tường minh** phù hợp:

~~~java
CharSequence text = new StringBuilder("Hi");
text = "Hello"; // Hop le: String cung implements CharSequence.

// var text = new StringBuilder("Hi");
// text = "Hello"; // LOI: kieu suy ra la StringBuilder.
~~~

Đây là khác biệt về **kiểu khai báo được chọn**, không phải giới hạn đặc biệt về đối tượng do `var` tạo ra.

## 4. Bẫy generic khi dùng diamond `<>`

~~~java
var values = new ArrayList<>();
values.add("Ada");
values.add(42); // Hop le, vi ArrayList<Object>.
~~~

Người đọc có thể đoán “đây là danh sách tên” nhưng compiler chỉ thấy biểu thức tạo `ArrayList<>` thiếu kiểu đích cụ thể. Đừng chờ các câu `add(...)` viết về sau để compiler suy lại kiểu phần tử: việc suy kiểu đã kết thúc tại khai báo.

Hai cách rõ ràng hơn:

~~~java
var names = new ArrayList<String>();

List<String> otherNames = new ArrayList<>();
~~~

- Cách đầu thích hợp khi muốn `ArrayList<String>` và constructor đã nêu rõ generic.
- Cách sau tốt khi muốn mã phụ thuộc vào **interface `List<String>`** thay vì lớp triển khai cụ thể.

`var` không tự tạo ràng buộc generic theo ý định nghiệp vụ; hãy thể hiện ràng buộc đó trong initializer hoặc kiểu tường minh.

## 5. Tên phương thức không phải hợp đồng kiểu

Đoạn sau **có thể hợp lệ về mặt compiler** nếu `load()` tồn tại, nhưng khó hiểu khi chỉ đọc tại vị trí khai báo:

~~~java
// var result = load();
~~~

Hãy cân nhắc khai báo trực tiếp loại dữ liệu:

~~~java
// List<Student> students = load();
~~~

Khi thực sự cần biết `result` có thể là `List<Student>`, `Optional<Student>` hay `Map<String, Student>`, người đọc phải lần ngược về chữ ký phương thức. `var` tiết kiệm vài ký tự nhưng làm tăng chi phí tìm hiểu.

Ngược lại, nếu tên hàm rất đặc trưng và ngữ cảnh gần đó đã chỉ rõ kiểu, `var` vẫn có thể hợp lý. Đây là **quy ước về khả năng đọc và bảo trì**, không phải quy tắc compiler bắt buộc. Trong code review, nên dựa vào sự rõ ràng của đoạn mã thay vì số lần xuất hiện của `var`.

## 6. Những ngữ cảnh thường đọc rõ với `var`

| Ngữ cảnh | Ví dụ hợp lệ | Nguồn suy luận |
| --- | --- | --- |
| Local có initializer | `var count = 1;` | Biểu thức `1`: `int` |
| Constructor nêu kiểu | `var builder = new StringBuilder();` | Kiểu `StringBuilder` |
| Enhanced `for` | `for (var name : names) { }` | Kiểu phần tử của `names` |
| Vòng `for` thường | `for (var i = 0; i < 3; i++) { }` | Initializer `0` |
| `try-with-resources` | `try (var reader = new java.io.StringReader("x")) { }` | Constructor của resource |
| Local bất biến tham chiếu | `final var max = 10;` | Kiểu `int` từ `10` |

`var` không được dùng để khai báo field của class, kiểu trả về phương thức hoặc kiểu tham số phương thức thông thường. Với lambda, Java 17 hỗ trợ `var` cho tham số có kiểu suy luận từ functional interface mục tiêu, nhưng đó là một ngữ cảnh riêng.

Hai khai báo sau cố ý **không hợp lệ**:

~~~java
// var value;        // Thieu initializer.
// var value = null; // Null literal khong cho kieu cu the.
~~~

Khi cần khai báo trước rồi mới gán, hoặc cần một tham chiếu nullable mà kiểu chưa hiện trong biểu thức, hãy viết kiểu tường minh như `String value = null;`.

## 7. Kiểu số và phép toán: đọc nhanh chưa chắc đoán đúng

~~~java
var a = 2;        // int.
var b = 2L;       // long.
var c = 2.0;      // double.
var d = 2.0f;     // float.

var quotient = 5 / 2;   // int, gia tri 2.
var exact = 5 / 2.0;    // double, gia tri 2.5.
~~~

Nếu dữ liệu là số tiền, bộ đếm có thể lớn, hoặc tỷ lệ cần độ chính xác cụ thể, hãy chú ý **kiểu của literal** và **kiểu biểu thức trung gian**. `var` chỉ chọn kiểu kết quả hiện có, **không ngăn tràn số** hay tự chuyển chia nguyên thành chia số thực.

Ví dụ:

~~~java
long total = 1_000_000_000L + 1_000_000_000L;
~~~

Khai báo tường minh `long` và hậu tố `L` làm chủ đích dùng số nguyên rộng dễ nhận biết, dù trong trường hợp giá trị ví dụ chưa vượt miền `int`. Nếu phép toán có thể vượt `long`, vẫn phải xử lý phù hợp.

## 8. Quy tắc code review thực tế

Khi nhìn vào một khai báo `var`, hãy tự hỏi:

1. **Người chưa đọc hàm trả về có đoán đúng kiểu không?** Nếu không, thêm kiểu tường minh.
2. **Kiểu phần tử generic có được xác định rõ?** Tránh `var items = new ArrayList<>()` khi muốn `String` hay một kiểu nghiệp vụ cụ thể.
3. **Kiểu interface hoặc superclass có phải ý đồ thiết kế?** Nếu có, viết `List<String>`, `Collection<T>` hoặc interface thích hợp bên trái.
4. **Kiểu primitive/wrapper và độ rộng số có quan trọng?** Nếu có, làm rõ literal, cast hoặc khai báo.
5. **Đặt tên biến có giúp hiểu ý nghĩa?** `var retryCount = 3` rõ hơn `var x = 3`, dù kiểu cùng là `int`.
6. **Có giảm lặp thực chất không?** `var student = new Student(...)` thường gọn hơn `Student student = new Student(...)` mà không giấu thông tin.

Không có câu trả lời tự động cho mọi khai báo. Mục tiêu là **giảm chữ thừa mà vẫn giữ lại thông tin cần thiết cho người đọc**.

## 9. Những hiểu nhầm thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Dùng `var` là bỏ kiểm tra kiểu.” | **Sai** | Java vẫn xác định kiểu tĩnh |
| “Cứ có `new` thì `var` luôn dễ hiểu.” | **Sai** | `new ArrayList<>()` có thể giấu kiểu generic |
| “`var x = 3;` có thể đổi sang `String`.” | **Sai** | `x` đã có kiểu `int` |
| “`var list = new ArrayList<>()` chắc là `ArrayList<String>`.” | **Sai** | Không có target type; trường hợp này suy ra `ArrayList<Object>` |
| “Kiểu của `var x = parseInt(...)` là wrapper.” | **Sai** | `Integer.parseInt` trả `int` |
| “Viết `List<String>` bên trái có thể thể hiện interface mong muốn.” | **Đúng** | Đó là hợp đồng kiểu tĩnh của biến |
| “Tên biến tốt có thể giúp `var` dễ đọc hơn.” | **Đúng** | Tên và initializer bổ sung ngữ cảnh |

## 10. Bài tập tự kiểm tra

1. **Rõ kiểu:** `var book = new Book("Java");` hay `var result = fetch();` dễ hiểu kiểu hơn nếu chưa đọc hàm?  
   *Gợi ý:* Câu thứ nhất thể hiện `Book` trực tiếp; câu thứ hai phụ thuộc chữ ký `fetch()`.
2. **Generic:** `var names = new ArrayList<>();` có bảo đảm `ArrayList<String>` không?  
   *Đáp án:* Không; trường hợp này suy ra `ArrayList<Object>`. Viết `new ArrayList<String>()` hoặc `List<String> names = new ArrayList<>()`.
3. **Interface:** Vì sao `List<String> names = new ArrayList<>()` có thể tốt hơn `var names = new ArrayList<String>()`?  
   *Đáp án:* Nó thể hiện biến dự kiến dùng qua API `List`, không ràng buộc kiểu khai báo vào `ArrayList`.
4. **Số học:** `var result = 5 / 2;` và `var result = 5 / 2.0;` có kiểu gì?  
   *Đáp án:* `int` và `double`, lần lượt có giá trị 2 và 2.5.
5. **Chữ ký phương thức:** Nếu `loadStudents()` trả `List<Student>`, dùng `var students = loadStudents();` có sai không?  
   *Đáp án:* Không sai về ngôn ngữ; nhưng `List<Student> students = loadStudents();` có thể rõ hơn cho người đọc.
6. **Thực hành:** Đổi tên `var x = 3;` cho dễ hiểu nếu đây là số lần thử.  
   *Gợi ý:* `var retryCount = 3;`.

## Checklist cuối bài

- [ ] Chỉ dùng `var` khi kiểu vẫn **rõ ràng tại chỗ khai báo**.
- [ ] Hiểu `var` không tạo kiểu động hay thay đổi cơ chế type checking.
- [ ] Không để diamond `<>` làm mất ràng buộc generic mong muốn.
- [ ] Chọn kiểu tường minh khi cần thể hiện interface/superclass hoặc hợp đồng API.
- [ ] Cân nhắc primitive/wrapper, độ rộng số và phép toán khi suy luận kiểu.
- [ ] Ưu tiên tên biến có nghĩa và initializer nói rõ dữ liệu.
- [ ] Trong code review, lấy **tính dễ đọc và bảo trì** làm tiêu chí, không coi việc dùng `var` là mục đích tự thân.

**Kết luận:** `var` tốt nhất khi giúp bỏ phần kiểu lặp lại **mà không bắt người đọc đi tìm kiểu ở nơi khác**. Nếu biểu thức khởi tạo không cho thấy đủ loại dữ liệu hoặc che mất hợp đồng quan trọng, viết kiểu tường minh là lựa chọn rõ ràng và an toàn hơn.
