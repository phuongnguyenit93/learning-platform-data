# Java 10 – Ranh giới giữa suy luận biến cục bộ và hợp đồng API công khai

> **Chủ đề:** Java 10 → Kiểu suy luận nâng cao → Ranh giới giữa suy luận biến cục bộ và hợp đồng API công khai. Bài học dùng những quy tắc còn hiệu lực trong Java 17+ và các JDK hiện đại. Local-variable type inference bằng `var` bắt đầu từ Java 10 (JEP 286). Cú pháp `var` cho tham số lambda được bổ sung ở Java 11 (JEP 323); `record` và `Stream.toList()` trong ví dụ hoàn chỉnh có từ Java 16. Các mốc này giúp phân biệt chính xác tính năng của Java 10 với tiện ích hiện đại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao `var` rút gọn **khai báo biến cục bộ** nhưng không thể dùng thay kiểu trả về hay kiểu tham số trong chữ ký API công khai.
2. Phân biệt **kiểu suy luận của một biến bên trong phương thức** với **hợp đồng kiểu mà caller nhìn thấy** qua `public` interface/class/method.
3. Thiết kế API công khai bền vững bằng các kiểu tường minh như `List<UserView>`, `Optional<UserView>`, interface, generic type parameter, ngoại lệ và quy ước dữ liệu.
4. Nhận biết trường hợp `var` vô tình suy luận kiểu implementation cụ thể hoặc generic quá rộng, từ đó ảnh hưởng overload resolution và khả năng tái cấu trúc code.
5. Xử lý rõ ràng giới hạn của `var` đối với lambda/method reference, `null`, diamond (`<>`), collection rỗng và generic factory.
6. Phân biệt hợp đồng kiểu với những cam kết bổ sung như có thể sửa collection, nullability, thứ tự, quyền sở hữu, thread safety.
7. Biên dịch và chạy chương trình Java 17+ dùng một API công khai ổn định trong khi implementation tự do dùng `var`.

## 2. Khái niệm: suy luận là tiện ích tại **vị trí khai báo biến**, hợp đồng API là lời hứa với người gọi

Xét hai đoạn:

~~~java
var users = repository.findAll();             // biến cục bộ
public List<UserView> findAll() { /* ... */ } // chữ ký API
~~~

- `var users = ...`: trình biên dịch tính kiểu tĩnh của **biểu thức khởi tạo** rồi dùng nó cho biến `users`. Kiểu chỉ cần xác định được trong phạm vi khai báo đó.
- `public List<UserView> findAll()`: chữ ký công khai nói với **mọi caller** rằng phương thức trả một `List<UserView>`. Hợp đồng này được dùng để biên dịch code ở module khác, tạo tài liệu API, kiểm tra override và đánh giá khả năng tương thích giữa các phiên bản thư viện.
- Trong phần thân `findAll`, implementation vẫn có thể dùng `var` cho biến tạm. Cách viết biến tạm không tự đổi kiểu trả về công khai.

Từ Java 10, khai báo:

~~~java
var size = 10;            // int
var names = List.of("An"); // List<String>
~~~

được kiểm tra **tĩnh tại thời điểm biên dịch**. Sau đó `size` không thể trở thành `String` chỉ vì một phép gán khác. `var` cũng không mang kiểu “tùy ý” tương tự JavaScript.

**Nguyên tắc:** Dùng `var` để giảm lặp kiểu tại nơi kiểu suy luận rõ ràng và người đọc có thể quan sát initializer. Dùng tên kiểu tường minh để diễn đạt ranh giới tương tác giữa các phương thức, lớp, package và module.

## 3. Những vị trí `var` được và không được sử dụng

### 3.1. Được dùng ở khai báo biến cục bộ có initializer

~~~java
void process() {
    var attempts = 3;                           // int
    var label = "ready";                        // String
    var queue = new java.util.ArrayList<String>(); // ArrayList<String>
    for (var item : queue) {                    // String
        System.out.println(item);
    }
}
~~~

Java 10 hỗ trợ `var` cho biến cục bộ trong block, biến của vòng `for`, enhanced `for` và tài nguyên trong `try-with-resources`. Biến vẫn tuân thủ scope, definite assignment và kiểm tra kiểu tĩnh thông thường.

~~~java
try (var reader = new java.io.StringReader("abc")) {
    System.out.println(reader.read()); // 97, mã UTF-16 của 'a'
}
~~~

`var` cần initializer để suy luận kiểu và không nhận initializer là literal `null` trần:

~~~java
// var x;             // lỗi: thiếu initializer
// var x = null;      // lỗi: không suy luận được kiểu
String x = null;      // cú pháp hợp lệ; cần kiểm soát null khi sử dụng
~~~

### 3.2. Không được dùng `var` làm kiểu trong **chữ ký public method/field/constructor parameter**

Các dòng comment là ví dụ **không biên dịch** nếu bỏ comment:

~~~java
class CatalogApi {
    // public var findAll() { return java.util.List.of(); } // SAI: return type
    // public void save(var name) { }                        // SAI: method parameter
    // public var names = java.util.List.of();              // SAI: field

    public java.util.List<String> findAll() { // ĐÚNG
        var result = java.util.List.<String>of();
        return result;
    }

    public void save(String name) {           // ĐÚNG
        var normalized = name.trim();
        System.out.println(normalized);
    }
}
~~~

Điều này đúng cả với phương thức `private`: `var` không phải kiểu trả về hoặc kiểu tham số phương thức thông thường, bất kể mức visibility. Tương tự, không dùng `var` làm type argument hoặc kiểu phần tử field tùy tiện như một tên kiểu thực.

### 3.3. Ngoại lệ cần biết: `var` trong lambda từ Java 11

Java 11 cho phép viết:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (var a, var b) -> a + b;
~~~

Kiểu `a` và `b` vẫn đến từ **target type** `BiFunction<Integer,Integer,Integer>`; đây là lambda expression, không phải chữ ký của một phương thức `public`. Không trộn `(var a, int b)` hoặc `(var a, b)` trong cùng danh sách tham số lambda.

Java 10 tự nó chưa có cú pháp `var` cho lambda parameters, nên ví dụ này là kiến thức mở rộng dành cho Java hiện đại. Phân biệt chỗ dùng này để tránh nhận định thiếu chính xác rằng “`var` chỉ được viết trước biến cục bộ và không bao giờ xuất hiện trước tham số”.

## 4. API công khai cần kiểu tường minh vì code ở nơi khác phải dựa vào hợp đồng

Giả sử xây dựng module đọc người dùng:

~~~java
public interface UserReader {
    List<UserView> findAll();
    Optional<UserView> findById(String id);
}
~~~

Từ chữ ký này, caller có thể biết **trước khi chạy chương trình**:

- `findAll()` trả `List<UserView>`; phần tử phải tuân theo kiểu `UserView`.
- `findById(String id)` nhận một `String` và trả `Optional<UserView>`, thể hiện khả năng không tìm thấy bằng `Optional.empty()`.
- Caller không cần biết implementation dùng `ArrayList`, truy vấn database, HTTP client hay in-memory cache.
- Trình biên dịch có đủ thông tin cho method references, generic calls và overload resolution.

Khi code bên ngoài viết:

~~~java
var users = reader.findAll(); // vẫn là List<UserView>
~~~

`var` của **caller** suy luận từ **kiểu trả về được công bố** của `UserReader.findAll()`. Nó không nhìn vào thân phương thức triển khai, không tự chuyển `List<UserView>` thành `ArrayList<UserView>` dựa trên object thực tế.

Đây là ranh giới quan trọng: **implementation sở hữu quyết định nội bộ; API sở hữu lời hứa với caller**. Thay đổi cách implementation tạo danh sách không buộc caller sửa mã nếu chữ ký và hợp đồng hành vi được giữ nguyên.

### 4.1. Kiểu trong API còn hỗ trợ JavaDoc, IDE, reflection và công cụ

Một chữ ký công khai `List<UserView> findAll()` có thể được hệ thống tài liệu/IDE trình bày rõ, giúp IDE kiểm tra compile-time khi caller dùng method, và được class file mô tả bằng metadata phương thức. Generic type arguments được ghi trong thông tin signature, nhưng **type erasure** có nghĩa không thể giả định `List<UserView>` còn đầy đủ type argument ở mọi phép kiểm tra runtime.

Ngược lại, `var` là tiện ích của **source code cục bộ**; nó không tạo thêm một loại API dynamic và không thay thế việc thiết kế các public declarations. Các biến cục bộ có thể xuất hiện trong thông tin debug tùy cách biên dịch, nhưng chúng không tạo thành chữ ký mà các module khác gọi.

## 5. Đừng để `var` vô tình khóa code vào kiểu implementation

### 5.1. Cùng initializer nhưng kiểu biến có thể khác

~~~java
var concrete = new java.util.ArrayList<String>();
java.util.List<String> abstraction = new java.util.ArrayList<>();
~~~

- `concrete` có kiểu tĩnh `ArrayList<String>` do `var` lấy kiểu của initializer.
- `abstraction` có kiểu tĩnh `List<String>` do kiểu được khai báo ở vế trái.
- Hai biến lúc này đều trỏ đến object `ArrayList`, nhưng **bộ phương thức thấy được và lựa chọn overload** có thể khác.

Ví dụ minh họa (hai overload ở cùng lớp):

~~~java
static String inspect(java.util.Collection<String> x) { return "Collection"; }
static String inspect(java.util.ArrayList<String> x) { return "ArrayList"; }

// var concrete = new ArrayList<String>();
// List<String> abstraction = new ArrayList<>();
System.out.println(inspect(concrete));    // ArrayList
System.out.println(inspect(abstraction)); // Collection
~~~

Overload được chọn **lúc biên dịch** theo **kiểu tĩnh của biểu thức truyền vào**. Trong ví dụ, biến khai báo dưới kiểu `List<String>` chỉ khớp trực tiếp với overload nhận `Collection<String>`; compiler không chọn overload `ArrayList<String>` bằng cách đoán runtime type.

Vì vậy, khi dùng `var` với constructor class cụ thể, thay đổi initializer sang một implementation khác có thể buộc sửa các chỗ sử dụng phương thức đặc thù hoặc làm thay đổi overload được chọn. Cân nhắc kiểu interface khi ý định là chỉ phụ thuộc hợp đồng của interface.

### 5.2. Tình huống nên dùng kiểu tường minh

~~~java
List<String> names = new ArrayList<>();           // contract theo interface
Map<String, Integer> counts = new HashMap<>();    // contract key/value rõ
Collection<UserView> users = loadUserViews();      // chỉ cần thao tác Collection
~~~

Kiểu tường minh đặc biệt hữu ích ở các ranh giới logic dài, với code cần thay implementation mà không ảnh hưởng caller hoặc khi tên biến/initializer không tiết lộ đủ ý nghĩa. `var` không xấu; vấn đề là chọn nó ở vị trí khiến ý định kiểu bị che khuất.

### 5.3. `var` vẫn hữu ích với method đã có chữ ký tốt

~~~java
var response = client.fetchUsers();     // kiểu theo return type của fetchUsers()
var users = response.users();           // kiểu theo return type của users()
var count = users.size();               // int
~~~

Nếu các method đã có API rõ ràng và tên biến có nghĩa, `var` giúp đoạn code ngắn và dễ đọc. Cần kiểm tra hợp đồng trả về của method, không chỉ suy đoán từ tên method hay dạng giá trị khi chạy.

## 6. Generic type inference: API rõ kiểu bảo vệ caller và cả code cục bộ

### 6.1. Diamond với `var` có thể suy luận `Object` ngoài ý muốn

~~~java
var values = new ArrayList<>(); // ArrayList<Object>
values.add("An");
values.add(42);                 // biên dịch được: Integer là Object
~~~

Khi `new ArrayList<>()` không nhận target type cũng không có constructor argument mang loại phần tử, kiểu generic của instance thường được suy luận là `Object`. Các lệnh `add` ở phía sau **không làm suy luận lại** generic type.

Nếu ý định là danh sách String, nên viết:

~~~java
List<String> names = new ArrayList<>(); // vế trái làm target type
var names2 = new ArrayList<String>();  // constructor ghi rõ type argument
~~~

### 6.2. Generic factory rỗng cũng cần target type hoặc type witness

~~~java
var unknown = List.of();                 // List<Object>
List<String> names = List.of();          // List<String> nhờ target type
var names2 = List.<String>of();          // List<String> nhờ type witness
~~~

Đặt `var` trước `List.of()` rỗng có thể làm mất thông tin domain. Còn chữ ký API:

~~~java
public List<String> emptyNames() {
    return List.of(); // target type ở return context là List<String>
}
~~~

vẫn rõ và hợp lệ. Caller sử dụng `var result = emptyNames();` có kiểu `List<String>` do chữ ký phương thức, bất kể runtime trả danh sách rỗng.

Cần nhớ generic type và mutability là hai chuyện khác nhau: `List.<String>of()` có kiểu phần tử String nhưng không cho sửa cấu trúc; `new ArrayList<String>()` vừa mang kiểu String vừa có thể thêm/bớt phần tử.

### 6.3. API generic công khai và suy luận ở lời gọi là hai tầng riêng biệt

~~~java
public static <T> List<T> snapshot(Collection<? extends T> source) {
    return List.copyOf(source);
}
~~~

Chữ ký `<T> List<T> snapshot(Collection<? extends T> source)` công bố **mối quan hệ kiểu** giữa tham số và kết quả cho mọi caller. Khi gọi:

~~~java
List<String> names = List.of("An");
var snapshot = snapshot(names); // List<String>
~~~

trình biên dịch suy luận type argument `T` của generic method từ đối số `names`, rồi `var` lấy kiểu của **biểu thức gọi method**. Đây là hai cơ chế liên quan nhưng khác vị trí: generic method type inference diễn ra ở lời gọi API; local-variable inference diễn ra ở khai báo biến.

API dùng generic type parameter tường minh để bảo toàn tính an toàn kiểu. Không thay method generic bằng kiểu `List<Object>` chỉ để thuận tiện cho implementation: `List<Object>` và `List<String>` là các parameterized types bất biến (invariant) theo quan hệ subtype, không hoán đổi trực tiếp.

## 7. Method references và lambda cần một hợp đồng kiểu đích

Với lambda hoặc method reference đứng độc lập, compiler thường cần functional interface làm target type:

~~~java
// var formatter = text -> text.trim(); // lỗi: lambda thiếu target type
// var cleaner = String::trim;           // lỗi: method reference thiếu target type

java.util.function.Function<String, String> cleaner = String::trim;
var normalized = cleaner.apply("  ready  "); // String
~~~

Không có kiểu “lambda” chung chung để `var` tự suy ra như từ constructor. Nếu thật sự cần dùng `var`, có thể cung cấp target type bằng cast:

~~~java
var cleaner = (java.util.function.Function<String, String>) String::trim;
~~~

Nhưng kiểu tường minh ở vế trái thường dễ đọc hơn ở trường hợp này. Public API nào **nhận callback** cũng nên khai báo rõ functional interface:

~~~java
public void mapNames(java.util.function.Function<String, String> transform) {
    // ...
}
~~~

Caller có thể truyền lambda với các parameter được suy luận theo `Function<String,String>`. Đây là **target typing của lambda**, không phải việc đưa `var` vào method parameter công khai.

## 8. Kiểu trả về công khai khác hợp đồng hành vi: mutability, null và ownership

### 8.1. `List<T>` không tự hứa danh sách immutable

Hai cách triển khai cùng một chữ ký `public List<String> names()`:

~~~java
public List<String> namesA() {
    return new ArrayList<>(List.of("An")); // caller có thể sửa list trả ra
}
public List<String> namesB() {
    return List.of("An");                 // caller không sửa được cấu trúc
}
~~~

Kiểu trả về tường minh `List<String>` **không** tự đảm bảo danh sách có thể sửa hay không, có đồng bộ hay không hoặc việc sửa list có ảnh hưởng kho dữ liệu gốc hay không. Những điều đó thuộc hợp đồng hành vi cần được thiết kế/tài liệu hóa và kiểm thử.

Nếu API muốn trả snapshot không sửa được, có thể chọn:

~~~java
public List<UserView> findAll() {
    var rows = readCurrentRows();  // giả định trả List<UserView>
    return List.copyOf(rows);      // cấu trúc không sửa được qua List API
}
~~~

`List.copyOf` có từ Java 10 và vẫn dùng rộng rãi. Nó ngăn thay đổi **cấu trúc collection** và, với nguồn mutable, không phản ánh lần thêm/bớt source sau khi copy. Tuy nhiên nó **không deep-copy** object phần tử. Muốn snapshot dữ liệu bất biến sâu, phần tử cũng phải immutable hoặc được sao chép phòng vệ.

### 8.2. `Optional<T>` thể hiện khả năng vắng mặt tốt hơn quy ước null tùy tiện

~~~java
public Optional<UserView> findById(String id);
~~~

Caller biết cách xử lý có/không có giá trị mà không giả định object luôn khác null. Nhưng `Optional<UserView>` **không tự động** xác thực `id`, không bảo đảm thread safety, và cũng không mô tả đầy đủ các lỗi I/O/nghiệp vụ có thể xảy ra. Hợp đồng API cần xác định thêm ngoại lệ, điều kiện hợp lệ và thông điệp lỗi khi chúng quan trọng.

Nếu dữ liệu nghiệp vụ cho phép `null` trong một public method trả `UserView`, cần quy định/annotation nullability theo tiêu chuẩn dự án. Kiểu `UserView` trong Java thông thường không có ý nghĩa “non-null tuyệt đối” như một số type system khác. Dùng `var` ở caller không giúp suy luận nullability.

### 8.3. Những điều hợp đồng public API có thể phải nêu ngoài kiểu

| Thành phần | Ví dụ | Lý do |
| --- | --- | --- |
| Kiểu và generic | `List<UserView>`, `Optional<UserView>` | Caller biết phần tử/kết quả có kiểu gì |
| Mutability/ownership | Trả snapshot hoặc view; caller có quyền sửa không | Tránh sửa dữ liệu không mong muốn |
| Nullability | Có nhận/trả null không; quy tắc với dữ liệu rỗng | Tránh lỗi runtime và mơ hồ |
| Thứ tự | Kết quả được sắp xếp theo tiêu chí nào | Caller không dựa trên thứ tự ngẫu nhiên |
| Ngoại lệ | `IllegalArgumentException`, `IOException` hoặc lỗi nghiệp vụ | Caller biết xử lý failure |
| Thread safety | Có thể gọi đồng thời hay không | Tránh truy cập cạnh tranh vào state |
| Phiên bản/tương thích | Kiểu và semantics có được giữ khi nâng cấp không | Tránh làm hỏng client đã biên dịch/triển khai |

`var` không thay thế bất kỳ thành phần hợp đồng nào ở bảng trên. Chọn kiểu và tài liệu công khai là quyết định thiết kế API; chọn `var` là quyết định cục bộ về độ rõ và sự lặp cú pháp.

## 9. Ví dụ Java 17+ hoàn chỉnh: dùng `var` trong implementation, API vẫn rõ kiểu

Lưu đoạn code dưới đây trong file **`ApiBoundaryDemo.java`**. Ví dụ gồm một public interface `UserReader`, DTO `record UserView` (Java 16+), implementation có danh sách mutable nội bộ, API trả snapshot qua `List.copyOf` (Java 10), và caller dùng `var` để lấy kiểu từ chữ ký public.

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.function.Function;

public class ApiBoundaryDemo {
    public record UserView(String id, String name) {}

    public interface UserReader {
        List<UserView> findAll();
        Optional<UserView> findById(String id);
    }

    private static final class InMemoryUserReader implements UserReader {
        private final List<UserView> data = new ArrayList<>(
                List.of(new UserView("u1", "An"),
                        new UserView("u2", "Binh")));

        @Override
        public List<UserView> findAll() {
            var snapshot = List.copyOf(data);
            return snapshot;
        }

        @Override
        public Optional<UserView> findById(String id) {
            return data.stream().filter(user -> user.id().equals(id)).findFirst();
        }

        void addUser(UserView user) {
            data.add(user);
        }
    }

    public static List<String> displayNames(UserReader reader) {
        var users = reader.findAll();
        var labels = users.stream().map(UserView::name).toList();
        return labels;
    }

    private static String inspect(Collection<String> value) {
        return "Collection";
    }

    private static String inspect(ArrayList<String> value) {
        return "ArrayList";
    }

    private static void acceptStrings(List<String> values) {
        System.out.println("typed empty: " + values.size());
    }

    public static void main(String[] args) {
        var implementation = new InMemoryUserReader();
        UserReader api = implementation;

        var snapshot = api.findAll();
        System.out.println("snapshot: " + snapshot);
        System.out.println("names: " + displayNames(api));
        System.out.println("found: " +
                api.findById("u1").map(UserView::name).orElse("missing"));
        System.out.println("missing: " + api.findById("unknown").isEmpty());

        implementation.addUser(new UserView("u3", "Chi"));
        System.out.println("old snapshot size: " + snapshot.size());
        System.out.println("fresh result size: " + api.findAll().size());

        var concrete = new ArrayList<String>();
        List<String> abstractView = new ArrayList<>();
        System.out.println("overloads: " +
                inspect(concrete) + "/" + inspect(abstractView));

        var empty = List.of();
        List<Object> broad = empty;
        var typedEmpty = List.<String>of();
        acceptStrings(typedEmpty);
        System.out.println("broad empty: " + broad.size());

        Function<String, String> cleaner = String::trim;
        var cleaned = cleaner.apply("  ready  ");
        System.out.println("cleaned: " + cleaned);
    }
}
~~~

Chạy từ thư mục chứa file:

~~~bash
javac --release 17 ApiBoundaryDemo.java
java ApiBoundaryDemo
~~~

**Stdout chính xác** khi biên dịch và chạy trên JDK hiện đại:

~~~text
snapshot: [UserView[id=u1, name=An], UserView[id=u2, name=Binh]]
names: [An, Binh]
found: An
missing: true
old snapshot size: 2
fresh result size: 3
overloads: ArrayList/Collection
typed empty: 0
broad empty: 0
cleaned: ready
~~~

### 9.1. Phân tích chi tiết chương trình

1. `UserReader` công bố `List<UserView> findAll()` và `Optional<UserView> findById(String id)`. Caller chỉ cần interface để biên dịch; `InMemoryUserReader` là lựa chọn implementation **nội bộ**.
2. Bên trong `findAll`, `var snapshot = List.copyOf(data)` có kiểu `List<UserView>` vì `data` đã có generic type. Cách dùng `var` không biến return type public thành kiểu mơ hồ.
3. `var snapshot = api.findAll()` tại caller cũng có kiểu `List<UserView>` do chữ ký `UserReader`. Caller không thấy thông tin triển khai `ArrayList` từ body method.
4. Sau `implementation.addUser(...)`, snapshot cũ vẫn có hai phần tử, còn `api.findAll()` mới có ba. Đây là hợp đồng snapshot được **implementation chủ động tạo**, không phải tính năng tự phát của `var` hay `List<T>`.
5. `displayNames` công bố `List<String>`, còn `var users` và `var labels` là chi tiết cục bộ. `Stream.toList()` (Java 16+) tạo danh sách kết quả không cho sửa cấu trúc.
6. `inspect(concrete)` chọn overload `ArrayList` do kiểu tĩnh của `concrete`; `inspect(abstractView)` chọn overload `Collection` do biến khai báo kiểu `List<String>`.
7. `List.of()` rỗng dưới `var` được suy luận `List<Object>`, chứng minh bằng phép gán vào `List<Object> broad`. `List.<String>of()` giữ `String` thông qua type witness và có thể truyền vào `acceptStrings(List<String>)`.
8. `Function<String,String> cleaner` cung cấp target type cho method reference `String::trim`. Biến kết quả `cleaned` mới thích hợp dùng `var`.

### 9.2. Giới hạn ví dụ

`record UserView(String id, String name)` chứa hai `String` vốn immutable; ở đây kết quả `List.copyOf` là snapshot thích hợp. Nếu DTO chứa danh sách/array mutable, `record` không tự deep-freeze thành phần ấy. Implementation `InMemoryUserReader` dùng `ArrayList` không đồng bộ; chương trình là ví dụ **đơn luồng**, không chứng minh repository có thể được gọi an toàn đồng thời. API production cần quy định concurrency và bảo vệ dữ liệu tương ứng.

## 10. Ranh giới cần cân nhắc khi nâng cấp thư viện hoặc thay implementation

### 10.1. Thay đổi local `var` thường không phải thay đổi chữ ký public

Giả sử giữ nguyên:

~~~java
public List<String> names() {
    var result = new ArrayList<String>();
    result.add("An");
    return List.copyOf(result);
}
~~~

Bạn có thể đổi code nội bộ để lấy dữ liệu từ cache, database hoặc stream, miễn vẫn đáp ứng `List<String>` và các cam kết hành vi của API. Caller không cần biết nội bộ viết `var` hay `List<String>`. Tuy vậy, vì kiểu static của biến `var` phụ thuộc initializer, sửa initializer vẫn có thể gây **lỗi biên dịch hoặc thay đổi overload được chọn bên trong implementation**; cần chạy lại tests của implementation.

### 10.2. Thay đổi kiểu trong chữ ký public là quyết định tương thích

Xét API đã phát hành:

~~~java
public List<String> names();
~~~

Nếu thay thành:

~~~java
public ArrayList<String> names();
~~~

đây là thay đổi **declared return type**, dù implementation có thể vẫn trả `ArrayList` từ trước. Việc đổi kiểu trả về có thể ảnh hưởng source compatibility, override và cả khả năng liên kết binary của client đã biên dịch, tùy loại thay đổi và cách thư viện được phân phối. Không thay chữ ký public chỉ để “phù hợp kiểu mà `var` suy luận bên trong”.

Đặc biệt:

- JVM method descriptor chứa các kiểu tham số và kiểu trả về đã xóa generic. Thay kiểu trả về từ `List` sang `ArrayList` làm thay descriptor và có thể khiến client đã biên dịch không tìm được phương thức mà nó mong đợi (ví dụ `NoSuchMethodError`) nếu không xây dựng/giữ lớp tương thích phù hợp.
- Đổi type argument generic, ví dụ `List<String>` thành `List<Object>`, có thể không đổi descriptor sau erasure nhưng vẫn gây lỗi compile-time cho **source client** hoặc làm mất hợp đồng kiểu mà caller dựa vào.
- Việc thêm overload, đổi tham số, đổi tên phương thức, chuyển checked exceptions hay thay semantics cũng có thể tác động client ngay cả khi không liên quan `var`.

Khi duy trì thư viện, đánh giá thay đổi public API riêng với thay đổi implementation. Có thể dùng công cụ so sánh API/binary compatibility và chạy test client thật trên version mới; `var` không cung cấp “bảo hiểm tương thích”.

### 10.3. Chọn return interface hay concrete type

Trong API ứng dụng nói chung, một return type như `List<UserView>` hoặc `Collection<UserView>` thường cho phép đổi implementation thuận lợi hơn kiểu cụ thể `ArrayList<UserView>`. Tuy nhiên không có quy tắc tuyệt đối bắt mọi API trả interface: đôi khi một class cụ thể chính là hợp đồng có ý nghĩa (ví dụ một immutable value type chuyên biệt). Quyết định phải dựa trên tính năng caller cần và khả năng tiến hóa API, chứ không dựa trên việc dùng `var` trong body.

### 10.4. Ẩn implementation không có nghĩa che mọi chi tiết hành vi

Nếu API trả `List<T>`, caller vẫn có thể kiểm tra object ở runtime, nhưng không nên ép sử dụng implementation type không được hợp đồng công bố. Trả concrete mutable list nội bộ có thể vô tình lộ state; trả wrapper hay copy đúng giúp bảo vệ quyền sở hữu dữ liệu. Các hợp đồng về error handling, null, sort order và concurrency vẫn phải được thiết kế dù code bên trong dùng `var` hay kiểu tường minh.

## 11. Những bẫy nâng cao cần tránh

| Bẫy | Điều thực sự xảy ra | Cách xử lý |
| --- | --- | --- |
| “`var` tự chọn kiểu tốt nhất cho API về sau” | Suy luận chỉ dựa initializer ở vị trí khai báo | Viết kiểu tường minh ở public boundary, nhất là generics |
| “Method trả `var` sẽ suy ra từ `return`” | Java không cho `var` làm return type của method | Khai báo `List<UserView>`, `Optional<UserView>`, `String`… |
| “Public parameter có thể dùng `var` như lambda” | Method/constructor parameters cần kiểu; `var` lambda chỉ là cú pháp Java 11+ ở expression | Phân biệt lambda target typing với method signature |
| “`var x = new ArrayList<>()` đủ chứng minh List<String>” | Không có target type hay type argument; suy luận `ArrayList<Object>` | `List<String> x = new ArrayList<>()` hoặc `var x = new ArrayList<String>()` |
| “`var x = List.of()` tự biết domain String” | Generic factory rỗng thường suy luận `List<Object>` | `List<String> x = List.of()` hoặc `var x = List.<String>of()` |
| “`var` không thay đổi overload được gọi” | Inferred static type có thể là implementation cụ thể, ảnh hưởng overload resolution | Khi cần hợp đồng interface, khai báo interface ngay ở biến |
| “`var action = x -> ...` có thể tự suy luận” | Lambda cần functional interface làm target type | `Function<String,String> action = ...` |
| “`List<T>` cam kết không cho sửa” | Generic type chỉ nói kiểu phần tử, không nói mutability | Công bố semantics và trả copy/view phù hợp |
| “Có `final` hoặc `record` thì object sâu bên trong bất biến” | `final` khóa gán lại field; record shallow immutable | Dùng defensive copy và phần tử immutable khi cần |
| “Đổi return type public là refactor nội bộ vô hại” | Có thể phá source/binary compatibility | Giữ signature hoặc chuẩn bị migration/versioning |
| “`var` suy ra non-null, thread-safe, có thứ tự” | Những thuộc tính đó không được suy ra từ `var` | Kiểm thử/tài liệu hóa các cam kết riêng |

### 11.1. Ví dụ `var` với anonymous class: càng cần giữ ranh giới

Một số kiểu của biểu thức khởi tạo có thể là lớp ẩn danh với member không có trong interface cha:

~~~java
var local = new Object() {
    String label() { return "internal"; }
};
System.out.println(local.label()); // internal
~~~

Từ Java 10, `var` có thể giữ kiểu anonymous class ở phạm vi cục bộ, cho phép gọi member thêm vào bởi anonymous class trong tình huống thích hợp. Nhưng không thể dùng anonymous type này như kiểu trả về public được khai báo bằng `var`. Dựa vào member nội bộ mà caller bên ngoài không nhìn thấy sẽ làm code khó chuyển qua API ổn định.

Với API công khai, hãy định nghĩa interface/record/class có tên và chữ ký rõ ràng. Đoạn này chỉ là ví dụ minh họa **cú pháp nội bộ**, không khuyến nghị mở rộng diện tích code phụ thuộc vào anonymous type.

### 11.2. Vì sao không được “đọc suy luận” từ runtime object

~~~java
List<String> apiView = new ArrayList<>();
var same = apiView; // kiểu tĩnh là List<String>
~~~

`same.getClass()` có thể phản ánh `ArrayList` tại runtime, nhưng `same` vẫn có **kiểu tĩnh `List<String>`**. Việc chọn overload, kiểm tra method availability và generic safety được thực hiện theo kiểu tĩnh. Không dùng `getClass()` để đoán chữ ký generic đã bị xóa kiểu hoặc để thay thế kiểm tra code của compiler.

## 12. Checklist thiết kế và review API có sử dụng `var`

Trước khi merge PR hoặc công bố thư viện, kiểm tra tuần tự:

1. **Public surface:** Mọi public/protected method, constructor parameter, interface contract, field cần thiết đều dùng kiểu tường minh đúng ý nghĩa domain chưa?
2. **Generic precision:** Các type argument `<T>`, wildcard, type parameter `<T extends ...>` đã mô tả ràng buộc caller cần chưa? Có vô tình xuất hiện `Object`/raw type do `var` và factory rỗng không?
3. **Implementation independence:** Return type và parameter type có gắn chặt vào một implementation cụ thể khi không cần thiết không?
4. **Target typing:** Lambda/method reference có functional interface xác định không? Generic method có đủ thông tin từ đối số hoặc target context không?
5. **Overload stability:** Có phép gọi method nào đổi overload chỉ vì initializer của biến `var` thay đổi không?
6. **Null và lỗi:** API có quy định input null, output rỗng, unchecked/checked exceptions, validation và failure modes không?
7. **Collections:** API trả mutable list, live view hay snapshot? Caller có được sửa không? Phần tử bên trong có mutable không?
8. **Thread safety:** Mutable state có được đồng bộ hoặc giới hạn phạm vi sử dụng không? `var` và `final` không tự tạo thread safety.
9. **Compatibility:** Có thay chữ ký đã phát hành không? Nếu có, đã đánh giá source/binary compatibility, versioning và đường di chuyển cho caller chưa?
10. **Test:** Đã chạy build/test của module và kiểm tra call site đại diện; có tài liệu/JavaDoc cho hành vi cần biết bên ngoài không?

### 12.1. Quy ước thực hành hữu ích

- Ở **ranh giới module/API**, ưu tiên kiểu tường minh nói đúng ngôn ngữ nghiệp vụ.
- Ở **implementation cục bộ**, dùng `var` khi bên phải hiển nhiên về kiểu và tên biến đủ nghĩa.
- Khi khởi tạo generic rỗng, làm rõ type argument bằng vế trái hoặc constructor/type witness.
- Đừng yêu cầu mọi local phải dùng `var`, cũng đừng cấm toàn bộ `var`; mục tiêu là dễ đọc và ít rủi ro thay đổi.
- Khi muốn thay đổi API, điều chỉnh hợp đồng có chủ đích và kiểm thử tương thích, không thay vì một lời gọi `var` trông ngắn hơn.

## 13. Bài tập tự kiểm tra có đáp án

**Bài 1.** API sau có hợp lệ không và vì sao?

~~~java
// public var listUsers() { return List.of("An"); }
~~~

**Đáp án:** Không. `var` không được dùng làm return type của method. Dùng `public List<String> listUsers() { return List.of("An"); }` (với `import java.util.List;`) để công bố contract.

**Bài 2.** Tại caller:

~~~java
List<String> loadNames() { return List.of(); }
// Trong cùng lớp/phương thức khác:
var names = loadNames();
~~~

**Đáp án:** `names` là `List<String>`. Chữ ký method cung cấp kiểu, dù runtime trả danh sách rỗng.

**Bài 3.** Điều gì khác nhau giữa `var a = new ArrayList<String>();` và `List<String> b = new ArrayList<>();`?

**Đáp án:** `a` có kiểu tĩnh `ArrayList<String>`, `b` có kiểu tĩnh `List<String>`. Chúng có thể cùng instance implementation nhưng việc chọn overload và các phương thức nhìn thấy qua biến khác nhau.

**Bài 4.** `var xs = new ArrayList<>(); xs.add("A");` có thể truyền ngay vào `save(List<String>)` không?

**Đáp án:** Không. `xs` suy luận `ArrayList<Object>` khi không có target type/constructor argument; `add` không đổi loại phần tử đã suy luận. Chọn `List<String> xs = new ArrayList<>();` hoặc `var xs = new ArrayList<String>();`.

**Bài 5.** Vì sao `var mapper = (String value) -> value.trim();` không biên dịch?

**Đáp án:** Lambda standalone cần functional interface làm target type. Viết `Function<String,String> mapper = value -> value.trim();`. Có khai báo kiểu tham số lambda cũng không thay thế được kiểu đích của cả lambda expression.

**Bài 6.** `List<UserView> findAll()` có tự hứa trả kết quả không sửa được không?

**Đáp án:** Không. Chữ ký bảo đảm kiểu của phần tử, còn mutability/view/snapshot phải được xác định riêng. Nếu muốn snapshot không sửa cấu trúc, một cách là trả `List.copyOf(source)` và ghi rõ hợp đồng.

**Bài 7.** Một implementation đổi từ `ArrayList` sang `LinkedList` nhưng giữ `public List<String> names()` và hành vi đã công bố. Caller có bắt buộc sửa không?

**Đáp án:** Thông thường không, nếu caller tuân thủ contract và không phụ thuộc chi tiết implementation. Nhưng implementation nội bộ có dùng `var` có thể cần sửa vì kiểu suy luận theo initializer; vẫn phải chạy test.

**Bài 8.** Tại sao đổi `public List<String> names()` thành `public ArrayList<String> names()` không đơn thuần là sửa biến cục bộ?

**Đáp án:** Đây là thay chữ ký public. Client có thể bị ảnh hưởng ở compile time, override hoặc binary linkage; cần đánh giá compatibility trước khi phát hành.

**Bài 9.** `var empty = List.of();` và `List<String> empty2 = List.of();` khác nhau thế nào?

**Đáp án:** `empty` suy luận `List<Object>` vì generic factory rỗng không có target type; `empty2` là `List<String>` từ khai báo tường minh. Cả hai không cho sửa cấu trúc.

**Bài 10.** Lệnh `var result = api.findAll();` có suy ra kiểu thực tế do implementation bên trong trả `ArrayList` không?

**Đáp án:** Không. `result` suy luận theo **declared return type** của phương thức được gọi, chẳng hạn `List<UserView>`; không theo lớp runtime của object hay tên biến.

**Bài 11.** `var fn = String::trim;` có hợp lệ không? Cách thay thế rõ ràng?

**Đáp án:** Không, method reference thiếu target type. Dùng `Function<String,String> fn = String::trim;`.

**Bài 12.** Đã dùng `final var result = repository.load();` thì danh sách trả ra tự thành immutable/thread-safe chưa?

**Đáp án:** Chưa. `final` chỉ ngăn gán lại biến, `var` chỉ suy luận kiểu, còn trạng thái collection và thread safety thuộc hợp đồng/implementation.

**Bài 13.** `var local = new Object() { String label() { return "x"; } };` có thể gọi `local.label()` trong method không? Có thể khai báo `public var create()` để trả kiểu đó không?

**Đáp án:** Trong tình huống này lời gọi `local.label()` hợp lệ nhờ kiểu anonymous class mà local inference giữ được; `public var create()` vẫn không hợp lệ. Muốn công khai chức năng, định nghĩa interface/class có tên và return type tường minh.

**Bài 14.** Chức năng `var` cho lambda parameters có thuộc Java 10 không?

**Đáp án:** Không. Local-variable inference có từ Java 10; cú pháp `(var x, var y) -> ...` được bổ sung trong Java 11 và vẫn áp dụng ở Java hiện đại. Nó không cho phép `var` làm kiểu tham số method public.

## 14. Tài liệu chính thức để tra cứu

1. [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): phạm vi `var`, giới hạn của Java 10 và nguyên tắc suy luận kiểu từ initializer.
2. [OpenJDK – Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide): thực hành dùng `var`, đặc biệt với diamond, generic factory và khả năng đọc code.
3. [OpenJDK – Local Variable Type Inference FAQ](https://openjdk.org/projects/amber/guides/lvti-faq): câu hỏi về `var`, các phép gán tiếp theo, public API và những trường hợp suy luận nâng cao.
4. [JEP 323 – Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): bổ sung ở Java 11, tách biệt chữ ký method thông thường.
5. [Java Language Specification – Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4): quy tắc khai báo local và xác định kiểu.
6. [Java Language Specification – Method Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.4): cách khai báo chữ ký method, tham số và kiểu trả về.
7. [Java Language Specification – Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se26/html/jls-13.html): phân tích sự tiến hóa API và ảnh hưởng với chương trình đã biên dịch.
8. [Dev.java – Type Inference](https://dev.java/learn/language/fp/generics/type-inference/): diamond, generic method và target typing.
9. [Java SE API – List](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): hợp đồng `List.of` và `List.copyOf`.

**Ghi nhớ:** `var` là cú pháp giảm lặp khi khai báo **biến cục bộ**, còn public API là **hợp đồng lâu dài với caller**. Kiểu trả về, tham số, generic constraints và lời hứa về mutability/null/concurrency vẫn cần được thiết kế, công bố và kiểm thử rõ ràng. Chọn `var` bên trong implementation khi nó giúp code dễ đọc; giữ public API độc lập với chi tiết implementation để thay đổi hệ thống an toàn.
