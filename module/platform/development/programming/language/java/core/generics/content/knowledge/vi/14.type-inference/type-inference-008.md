# var với diamond và trường hợp Java suy luận kiểu thành Object

## 1. Vấn đề cần hiểu

Trong Java Generics, hai cú pháp thường xuất hiện cùng nhau:

- **var**: từ Java 10, cho phép trình biên dịch suy luận kiểu **của biến cục bộ** từ biểu thức khởi tạo.
- **Diamond operator (<>)**: từ Java 7, cho phép bỏ bớt tham số kiểu khi tạo đối tượng generic; trình biên dịch sẽ suy luận tham số kiểu dựa trên các ràng buộc và ngữ cảnh đang có.

Khi viết:

~~~java
var items = new ArrayList<>();
~~~

nhiều người tưởng items sẽ tự trở thành danh sách String sau khi thêm một chuỗi. Thực tế, với ArrayList<E> không có ràng buộc cụ thể nào cho E trong câu lệnh này, Java suy luận **E = Object**. Kiểu tĩnh của items là **ArrayList<Object>**. Các lệnh thêm phần tử về sau **không làm Java suy luận lại kiểu**.

Điểm mấu chốt: **var suy luận từ biểu thức khởi tạo, còn diamond phải giải bài toán suy luận tham số generic ngay tại lúc tạo đối tượng.** Nếu cả hai phía đều thiếu thông tin kiểu cụ thể, tham số generic không bị ràng buộc thường được suy luận thành Object.

## 2. Phân biệt kiểu của biến và tham số generic

Xem ba khai báo:

~~~java
List<String> first = new ArrayList<>();
var second = new ArrayList<String>();
var third = new ArrayList<>();
~~~

| Khai báo | Kiểu tĩnh của biến | Tham số kiểu của ArrayList | Vì sao? |
| --- | --- | --- | --- |
| first | List<String> | String | Vế trái có kiểu đích List<String>, nên diamond suy ra String. |
| second | ArrayList<String> | String | Vế phải ghi rõ String; var suy ra kiểu của biểu thức khởi tạo. |
| third | ArrayList<Object> | Object | var không cung cấp một kiểu đích cụ thể cho diamond, và constructor rỗng không ràng buộc E. |

Trong khai báo đầu tiên, kiểu biến là **List<String>**, không phải ArrayList<String>, dù đối tượng được tạo là ArrayList<String>. Trong hai khai báo dùng var, kiểu tĩnh của biến theo kiểu biểu thức khởi tạo là **ArrayList<...>**, nên có thể dùng các phương thức riêng của ArrayList.

**var không có nghĩa là dynamic, Object hoặc kiểu bất kỳ.** Sau khi trình biên dịch xác định được kiểu, biến vẫn được kiểm tra kiểu tĩnh như mọi khai báo Java khác.

## 3. Vì sao var + diamond có thể cho ra Object?

Ví dụ sau là mã hợp lệ:

~~~java
import java.util.ArrayList;

class Example {
    public static void main(String[] args) {
        var values = new ArrayList<>();
        values.add("Java");
        values.add(21);
    }
}
~~~

Cơ chế suy luận của câu lệnh khai báo:

1. Trình biên dịch gặp biểu thức new ArrayList<>().
2. Constructor không tham số không đưa ra đối số nào để xác định E.
3. Với khai báo var, phía trái không có kiểu khai báo như List<String> để áp ràng buộc String cho biểu thức khởi tạo.
4. E của ArrayList<E> không bị ràng buộc cụ thể; giới hạn trên mặc định là Object, nên diamond được suy luận thành ArrayList<Object>.
5. var nhận kiểu tĩnh ArrayList<Object>. Các lệnh add phía sau chỉ được kiểm tra theo kiểu đã suy luận; chúng không sửa quyết định ở bước 4.

Vì Object là kiểu cha của String và Integer, cả hai lệnh add trên đều hợp lệ. Tuy vậy, danh sách này **không tương đương List<String>** và không thể sử dụng tại nơi yêu cầu List<String>.

Nếu tham số generic có cận trên khác Object, kết quả mặc định có thể chịu ảnh hưởng của cận đó. Vì vậy không nên biến câu “diamond luôn ra Object khi đi cùng var” thành quy tắc tuyệt đối: **Object là kết quả điển hình khi tham số kiểu không có thông tin cụ thể và cận trên mặc định là Object**.

## 4. Ví dụ chạy đầy đủ trên Java 17+

Lưu đoạn sau thành tệp **VarDiamondDemo.java**.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

public class VarDiamondDemo {
    public static void main(String[] args) {
        // Không có kiểu đích hoặc đối số ràng buộc E:
        var mixed = new ArrayList<>(); // ArrayList<Object>
        mixed.add("Java");
        mixed.add(17);

        // Vế trái cung cấp kiểu đích:
        List<String> words = new ArrayList<>();
        words.add("Java");

        // Khi dùng var, ghi rõ tham số generic ở vế phải:
        var explicit = new ArrayList<String>();
        explicit.add("Generics");

        // Đối số constructor cung cấp thông tin suy luận E:
        var inferred = new ArrayList<>(List.of("Java", "Kotlin"));
        inferred.add("Scala");

        // Cả K và V đều thiếu ràng buộc cụ thể:
        var attributes = new HashMap<>(); // HashMap<Object, Object>
        attributes.put("version", 17);
        attributes.put(99, true);

        System.out.println("mixed = " + mixed);
        System.out.println("words = " + words);
        System.out.println("explicit = " + explicit);
        System.out.println("inferred = " + inferred);
        System.out.println("version = " + attributes.get("version"));
        System.out.println("key 99 = " + attributes.get(99));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VarDiamondDemo.java
java VarDiamondDemo
~~~

Kết quả chuẩn:

~~~text
mixed = [Java, 17]
words = [Java]
explicit = [Generics]
inferred = [Java, Kotlin, Scala]
version = 17
key 99 = true
~~~

Ở trường hợp **inferred**, List.of("Java", "Kotlin") tạo List<String>, nên đối số constructor giúp ArrayList<E> suy ra E là String ngay khi khởi tạo. Dùng var không bắt buộc tham số kiểu phải là Object; Java vẫn tận dụng thông tin kiểu xuất hiện **trong chính biểu thức khởi tạo**.

Các lệnh sau **cố ý gây lỗi biên dịch** và không thuộc chương trình chạy ở trên:

~~~java
var mixed = new ArrayList<>();  // ArrayList<Object>
List<String> wrong = mixed;     // Lỗi: ArrayList<Object> không chuyển thành List<String>

var inferred = new ArrayList<>(List.of("Java"));
inferred.add(42);              // Lỗi: add đòi hỏi String, không nhận int
~~~

Trong Java, generic là **bất biến (invariant)**: ArrayList<Object> không phải subtype của List<String>. Dù String là subtype của Object, quan hệ này không tự mở rộng thành List<String> là subtype của List<Object> hoặc ngược lại.

## 5. Khi có kiểu đích, khi không có kiểu đích

### 5.1. Vế trái khai báo kiểu tường minh

~~~java
List<String> names = new ArrayList<>();
~~~

Vế trái cung cấp **target type** List<String>. Diamond dùng thông tin đó để suy ra tham số String cho ArrayList. Đây là cách viết thường được ưu tiên khi muốn biểu lộ hợp đồng qua interface List.

### 5.2. var không tự tạo kiểu đích String

~~~java
var names = new ArrayList<>(); // ArrayList<Object>
~~~

Bản thân từ khóa var nói rằng trình biên dịch phải tìm kiểu từ initializer; nó không gợi ý String hay Number. Việc sau đó gọi names.add("Alice") không biến names thành ArrayList<String>.

### 5.3. Đối số constructor vẫn giúp suy luận

~~~java
var names = new ArrayList<>(List.of("Alice", "Bob"));
// ArrayList<String>
~~~

Constructor ArrayList(Collection<? extends E>) nhận Collection của phần tử String, tạo ràng buộc để suy ra E là String. Nguồn thông tin đến từ đối số constructor, không phải từ hành động add về sau.

Cần phân biệt:

~~~java
var fixed = new ArrayList<>(List.of("Alice")); // ArrayList<String>
var empty = new ArrayList<>(List.of());        // ArrayList<Object>
~~~

List.of() không có phần tử, và ở đây không có thông tin bổ sung buộc tham số kiểu thành String. Nếu mục tiêu là danh sách String rỗng, hãy cung cấp thông tin kiểu rõ ràng.

### 5.4. Lời gọi phương thức generic cũng có thể suy luận Object

~~~java
var first = java.util.Collections.emptyList();            // List<Object>
List<String> second = java.util.Collections.emptyList();  // List<String>
var third = java.util.Collections.<String>emptyList();    // List<String>
~~~

Ở dòng second, kiểu đích List<String> giúp phương thức generic suy ra String. Ở dòng third, **type witness** <String> xác định trực tiếp tham số kiểu của lời gọi phương thức. Đây là hiện tượng suy luận generic nói chung, không riêng constructor dùng diamond.

## 6. Các cách khai báo đúng với ý định

Khi cần danh sách String rỗng, có thể chọn một trong ba cách:

~~~java
// Ưu tiên kiểu interface khi chỉ cần hợp đồng List:
List<String> a = new ArrayList<>();

// Muốn dùng var nhưng vẫn giữ String:
var b = new ArrayList<String>();

// Muốn giữ diamond và có đối số mang thông tin String:
var c = new ArrayList<>(List.<String>of());
~~~

Cả a, b, c đều kiểm tra kiểu phần tử là String. Trong đó a có kiểu biến List<String>; b và c có kiểu biến ArrayList<String>. Với c, lời gọi List.<String>of() tạo List<String> rỗng để constructor có ràng buộc kiểu.

Với HashMap rỗng, vấn đề tương tự trên **hai** tham số kiểu:

~~~java
var unsafeForIntent = new java.util.HashMap<>(); // HashMap<Object, Object>
java.util.Map<String, Integer> byInterface = new java.util.HashMap<>();
var explicit = new java.util.HashMap<String, Integer>();
~~~

Nếu cần Map<String, Integer>, hãy chọn byInterface hoặc explicit. Việc ban đầu chỉ put("level", 1) vào unsafeForIntent **không suy luận lại** khóa String và giá trị Integer.

Một cách khác là khởi tạo từ nguồn có kiểu, ví dụ:

~~~java
var copy = new ArrayList<>(List.of("A", "B")); // ArrayList<String>
~~~

Không nên cố tình thêm phần tử mẫu chỉ để ép kiểu: nếu danh sách được yêu cầu rỗng, khai báo tham số generic rõ ràng dễ đọc và đúng ý định hơn.

## 7. Lỗi thực tế và cách phát hiện

### Lỗi A: Sau khi khởi tạo mới phát hiện không truyền được vào API

~~~java
import java.util.ArrayList;
import java.util.List;

class Service {
    static void saveNames(List<String> names) {
        // Xử lý các tên.
    }

    static void run() {
        var names = new ArrayList<>();
        names.add("Lan");
        // saveNames(names); // Lỗi biên dịch: names là ArrayList<Object>.
    }
}
~~~

**Nguyên nhân:** tham số của saveNames yêu cầu List<String>, nhưng names được suy luận thành ArrayList<Object> khi khai báo. **Sửa:** dùng List<String> names = new ArrayList<>(); hoặc var names = new ArrayList<String>(); ngay từ đầu.

### Lỗi B: Cho rằng diamond và var có cùng nhiệm vụ

~~~java
var numbers = new ArrayList<>();
numbers.add(10);
numbers.add("ten"); // Vẫn hợp lệ vì numbers là ArrayList<Object>.
~~~

var suy luận kiểu **biến**; diamond suy luận tham số kiểu của **kiểu được tạo**. Hai cơ chế liên quan nhưng không thay thế nhau. Trình biên dịch không xem phần tử được thêm đầu tiên là kiểu chuẩn cho các phần tử về sau.

### Lỗi C: Nhầm List<Object>, raw List và List<?>

~~~java
List<Object> objects = new ArrayList<>();
List raw = new ArrayList(); // Raw type: bỏ kiểm tra tham số kiểu, dễ có cảnh báo.
List<?> unknown = List.of("a", "b");
Object item = unknown.get(0);
// unknown.add("c");       // Lỗi: không biết kiểu phần tử cụ thể của List<?>.
~~~

- **List<Object>**: có tham số kiểu cụ thể Object; có thể thêm đối tượng của nhiều kiểu con.
- **Raw List**: sử dụng generic mà bỏ tham số kiểu; dễ tạo thao tác không an toàn và cảnh báo unchecked.
- **List<?>**: danh sách có kiểu phần tử chưa biết; có thể đọc dưới dạng Object, nhưng không tự do thêm phần tử tùy ý (ngoại trừ null).

ArrayList<Object> được suy luận bởi var + diamond là **kiểu generic có tham số Object**, không phải raw ArrayList.

### Lỗi D: Nhầm suy luận kiểu với kiểm tra kiểu lúc chạy

Java dùng **type erasure** cho phần lớn thông tin tham số generic khi chạy. Trình biên dịch vẫn biết biến là ArrayList<String> hay ArrayList<Object> khi kiểm tra lệnh add, phép gán và tham số phương thức. Không nên suy ra rằng vì không đọc được tham số kiểu trực tiếp từ đối tượng ArrayList tại runtime thì var sẽ có kiểu động.

### Lỗi E: Nghĩ var hợp lệ ở mọi nơi

var có các điều kiện sử dụng. Chẳng hạn, biến cục bộ dùng var phải có initializer để suy luận kiểu, và không thể chỉ khởi tạo bằng null:

~~~java
// var data;       // Lỗi: không có initializer.
// var data = null; // Lỗi: không có kiểu cụ thể để suy luận.
// var data = new ArrayList<>(); // Hợp lệ nhưng suy luận ArrayList<Object>.
~~~

Các câu bình luận trong ví dụ này nhằm minh họa cú pháp không hợp lệ; chúng không phải các khai báo để chạy.

## 8. Chọn cách viết nào trong mã thực tế?

- **Khai báo rõ kiểu ở phía trái** khi cần một hợp đồng ổn định qua interface hoặc khi initializer ngắn nhưng có thể mất thông tin generic: List<String> names = new ArrayList<>();.
- **Dùng var với kiểu generic tường minh ở phía phải** nếu muốn làm nổi bật cách khởi tạo cụ thể: var names = new ArrayList<String>();.
- **Dùng var và diamond cùng nhau** khi dữ liệu đầu vào của constructor hoặc những ràng buộc khác đã cung cấp chính xác kiểu mong muốn, ví dụ new ArrayList<>(List.of("A", "B"));.
- **Không tự động kết luận Object** nếu đã có đối số hoặc cận generic cụ thể; hãy xét toàn bộ ràng buộc tại initializer.
- **Kiểm tra ngay kiểu suy luận của biến** trong IDE hoặc bằng thử gán vào một kiểu mong đợi; đừng chỉ nhìn việc add một phần tử có biên dịch hay không.

Đặc biệt, một danh sách tạo bằng List.of(...) là danh sách **không thể thay đổi kích thước**; nó khác với ArrayList mới được tạo từ List.of(...). Dù cả hai có thể được suy luận là List<String>/ArrayList<String>, chỉ ArrayList trong ví dụ trên cho phép add. Đây là khác biệt về hành vi collection, không phải khác biệt về suy luận generic.

## 9. Câu hỏi tự kiểm tra

**1.** var a = new ArrayList<>(); a.add("x"); thì a có kiểu gì?

**Đáp án:** ArrayList<Object>. Lời gọi add("x") không thay đổi kết quả suy luận lúc khai báo.

**2.** var b = new ArrayList<>(List.of("x")); b.add(1); có hợp lệ không?

**Đáp án:** Không. b là ArrayList<String> do tham số của List.of("x") giúp suy luận String; add(1) không thỏa kiểu String.

**3.** Khác biệt giữa List<String> c = new ArrayList<>(); và var c = new ArrayList<String>(); là gì?

**Đáp án:** Cả hai giữ phần tử kiểu String; ở cách thứ nhất kiểu tĩnh của biến là interface List<String>, còn cách thứ hai là lớp cụ thể ArrayList<String>.

**4.** Vì sao var map = new HashMap<>(); không tự có kiểu HashMap<String, Integer> sau khi gọi put("x", 1)?

**Đáp án:** K và V được suy luận khi khởi tạo, thông thường là Object khi không có ràng buộc; lệnh put đến sau không tái suy luận chúng.

**Ghi nhớ:** Muốn generic có tham số kiểu cụ thể, hãy cung cấp thông tin đó **ngay tại câu lệnh khởi tạo** qua kiểu đích, tham số generic viết tường minh hoặc đối số/kiểu trả về có ràng buộc phù hợp. var giúp bỏ lặp kiểu, nhưng không đoán được ý định chưa xuất hiện trong biểu thức.
