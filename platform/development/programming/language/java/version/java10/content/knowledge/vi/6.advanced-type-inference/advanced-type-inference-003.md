# Kiểu giao nhau và kiểu không thể viết trực tiếp trong khai báo với `var`

## 1. Vì sao đây là một phần quan trọng của suy luận kiểu nâng cao?

Trong Java, phần lớn biến được khai báo bằng tên kiểu quen thuộc:

~~~java
String name = "Java";
List<String> names = List.of("A", "B");
Runnable task = () -> System.out.println("run");
~~~

Tuy nhiên, trình biên dịch Java còn làm việc với những **kiểu không thể biểu diễn trực tiếp bằng cú pháp kiểu thông thường tại vị trí khai báo biến cục bộ** (*non-denotable types*). Ví dụ:

- **Kiểu giao nhau** (*intersection type*), biểu thị một giá trị đồng thời đáp ứng nhiều ràng buộc kiểu, ví dụ `Runnable & AutoCloseable`.
- **Kiểu của lớp vô danh** (*anonymous class type*), có danh tính kiểu do trình biên dịch tạo ra nhưng không có tên lớp để viết lại.
- **Kiểu bắt giữ wildcard** (*capture type*), ví dụ một kiểu nội bộ hình thành khi truy cập `List<? extends Number>`; trường hợp này có quy tắc riêng về việc không để các biến kiểu nội bộ “rò rỉ” ra khỏi biểu thức.

Từ Java 10, `var` cho phép suy luận một số kiểu không thể viết trực tiếp ấy thay vì buộc biến cục bộ phải có tên kiểu tường minh. Đây vẫn là cơ chế của **Java định kiểu tĩnh**: biến có một kiểu được xác định khi biên dịch, các phương thức truy cập được quyết định dựa vào kiểu đó. Không có kiểu động runtime tên `var`.

**Mục tiêu học tập:** Sau bài này, bạn có thể giải thích intersection type, phân biệt *denotable/non-denotable*, dùng `var` an toàn với anonymous class, hiểu upward projection của wildcard capture, dự đoán lỗi biên dịch và chọn kiểu tường minh khi cần thiết kế API rõ ràng.

Bài chỉ dùng những quy tắc còn hiệu lực trong Java hiện đại, đối chiếu với **Java Language Specification (JLS) `4.9, `4.10.5 và `14.4.1**.

## 2. “Không thể viết trực tiếp” nghĩa là gì?

Trong ngữ cảnh bài này, một kiểu *denotable* là kiểu có thể diễn đạt bằng cú pháp tên kiểu hợp lệ ở vị trí tương ứng của Java, chẳng hạn `String`, `List<String>`, `List<? extends Number>`, `int[]`. Một kiểu *non-denotable* có thể tồn tại trong quá trình kiểm tra kiểu của compiler nhưng không có cú pháp khai báo biến cục bộ tường minh tương đương.

**Cần phân biệt ba trường hợp:**

| Trường hợp | Kiểu có thể xuất hiện ở đâu? | Có thể ghi nguyên kiểu vào phần kiểu của khai báo biến cục bộ? |
| --- | --- | --- |
| `List<String>` | Khai báo, tham số, kiểu trả về... | Có: `List<String> xs = ...;` |
| `Runnable & AutoCloseable` | Intersection cast, bound của type parameter, kiểu do compiler suy luận... | Không thể viết `Runnable & AutoCloseable task = ...;` |
| Kiểu lớp vô danh `new Object() { ... }` | Biểu thức tạo anonymous class; compiler tự đặt danh tính kiểu | Không có tên lớp để viết lại trong mã Java |
| Capture của `? extends Number` | Kiểu nội bộ khi compiler xử lý generic wildcard | Không có tên Java thông thường như `CAP#1` để đưa vào source |

**Không thể viết trong khai báo** không có nghĩa kiểu ấy “không có thật”, “là lỗi” hay “Java tự chuyển sang `Object`”. Nó chỉ nói đến **khả năng biểu diễn bằng cú pháp nguồn tại một vị trí cụ thể**. Intersection type vẫn có cú pháp hợp lệ trong cast và generic bound; wildcard có cú pháp `? extends ...`, nhưng **capture variable cụ thể** do compiler tạo thì không.

Ví dụ về hai khai báo đều hợp lệ nhưng có đặc tính khác nhau:

~~~java
// Ví dụ trong thân một phương thức:
CharSequence text = "Java";                           // một kiểu tường minh
var both = (CharSequence & Comparable<String>) "Java"; // kiểu giao nhau được suy luận
~~~

Với `text`, chỉ các thành viên được phép qua `CharSequence` là hiển thị ở thời điểm biên dịch. Với `both`, compiler biết giá trị được xem là **đồng thời** `CharSequence` và `Comparable<String>`.

## 3. Intersection type: giá trị đáp ứng nhiều kiểu cùng lúc

### 3.1. Khái niệm và cú pháp

**Intersection type** có dạng:

~~~text
T1 & T2 & ... & Tn
~~~

và biểu thị giá trị thỏa **tất cả** các ràng buộc `T1`, `T2`, ... chứ không chỉ một trong số đó.

Ví dụ `Runnable & AutoCloseable` yêu cầu đối tượng đồng thời có hành vi `run()` và tài nguyên hỗ trợ `close()`. Nó khác với phép OR/union: một đối tượng chỉ triển khai `Runnable` mà không triển khai `AutoCloseable` không thỏa kiểu giao nhau.

JLS `4.9 quy định kiểu giao nhau có thể sinh ra từ generic bound, phép ép kiểu (*cast*), capture conversion và phép tính kiểu cha chung (*least upper bound*, LUB).

### 3.2. Dùng intersection cast cùng `var`

Xét một lớp triển khai cả hai interface:

~~~java
class WorkerResource implements Runnable, AutoCloseable {
    @Override
    public void run() {
        System.out.println("running");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}
~~~

Bên trong phương thức có thể viết:

~~~java
var resource = (Runnable & AutoCloseable) new WorkerResource();
resource.run();
resource.close();
~~~

Ở đây:

1. `new WorkerResource()` tạo một đối tượng thỏa cả hai interface.
2. Cast `(Runnable & AutoCloseable)` yêu cầu compiler xem biểu thức có **intersection type**.
3. `var resource` giữ kiểu giao nhau thích hợp của initializer.
4. Vì thế có thể gọi cả `run()` lẫn `close()` qua `resource`.

Đoạn trên minh họa cú pháp; ở nơi gọi `close()` thông qua `AutoCloseable`, phải xử lý hoặc khai báo `Exception` nếu cần theo chữ ký phương thức. Chương trình đầy đủ ở mục 8 dùng `main(... ) throws Exception` để xử lý vấn đề này.

Không thể viết:

~~~java
// KHÔNG HỢP LỆ: intersection không phải cú pháp LocalVariableType tường minh
// Runnable & AutoCloseable resource = new WorkerResource();
~~~

Nếu chỉ khai báo `Runnable resource = new WorkerResource();`, biến có kiểu biên dịch `Runnable` nên không gọi trực tiếp `resource.close()`. Nếu chỉ khai báo `AutoCloseable` thì không gọi trực tiếp `run()`. Với `var` và initializer là intersection cast, cả hai khía cạnh đều được giữ ở kiểu suy luận.

### 3.3. Intersection type trong generic bound

Dấu `&` cũng hợp lệ ở một vị trí khác: **ràng buộc của tham số kiểu generic**:

~~~java
static <T extends Runnable & AutoCloseable> void execute(T task) throws Exception {
    task.run();
    task.close();
}
~~~

Phương thức `execute` chỉ chấp nhận kiểu `T` đáp ứng đồng thời hai interface. Ở đây `T` là **tên tham số kiểu viết được trong source**, còn `Runnable & AutoCloseable` là **intersection bound**. Cú pháp này khác với việc viết nguyên `Runnable & AutoCloseable` làm kiểu của biến cục bộ.

Nếu dùng một class bound và các interface bound, thứ tự và tính hợp lệ còn phải tuân theo quy tắc của Java; ví dụ class bound phải đặt đầu danh sách. Với nhu cầu API thường xuyên, việc tạo **một interface có tên** kế thừa các interface cần thiết giúp chữ ký và tài liệu dễ hiểu hơn.

### 3.4. Ví dụ không chỉ có interface được đặt tên

~~~java
var info = (CharSequence & Comparable<String>) "Java";
System.out.println(info.length());            // 4
System.out.println(info.compareTo("Java"));   // 0
~~~

`String` thực hiện cả `CharSequence` lẫn `Comparable<String>`, nên cast này phù hợp. Biến `info` cho phép gọi:

- `length()` từ `CharSequence`.
- `compareTo(String)` từ `Comparable<String>`.

Một phép cast giao nhau **không tạo lớp mới hay sao chép đối tượng**. Nó cung cấp một kiểu biên dịch thể hiện nhiều ràng buộc và, khi thích hợp, yêu cầu kiểm tra cast ở runtime.

### 3.5. Intersection type có thể phát sinh từ phép tính kiểu cha chung (LUB)

Khi một biểu thức có thể trả về nhiều loại tham chiếu, chẳng hạn hai nhánh của toán tử điều kiện, compiler đôi khi tính **least upper bound** và kết quả có thể chứa nhiều interface chung, biểu diễn bằng intersection type.

Ví dụ về mặt ý tưởng: nếu hai lớp khác nhau cùng triển khai `Serializable` và `CharSequence`, kiểu chung mà compiler tính toán có thể chứa cả hai ràng buộc, tùy hình dạng chính xác của các kiểu đầu vào và quy tắc LUB.

**Không nên đoán** kiểu chính xác của một biểu thức điều kiện phức tạp chỉ từ tên các class; hãy xem JLS `4.10.4 hoặc dùng compiler/IDE. Nếu phần mềm chỉ cần chức năng `CharSequence` thì một khai báo tường minh `CharSequence value = ...;` thường rõ ý định hơn việc giữ nguyên kiểu giao nhau dài và khó đoán.

## 4. Anonymous class type: kiểu có thật nhưng không có tên để viết lại

### 4.1. Vì sao một lớp vô danh là non-denotable?

Ví dụ:

~~~java
var report = new Object() {
    String title = "Java";
    String summary() {
        return title + " 10";
    }
};
System.out.println(report.summary()); // Java 10
~~~

Biểu thức `new Object() { ... }` tạo một **anonymous class** mở rộng `Object`, có thêm field `title` và phương thức `summary()`. Kiểu anonymous class này được compiler biết đầy đủ ở nơi khai báo, nhưng lập trình viên **không có tên lớp nguồn** để viết trong phần khai báo biến.

Với `var report`, Java suy luận **kiểu thực tế của anonymous class**, vì vậy `report.summary()` được compiler chấp nhận trong phạm vi phù hợp.

Trong khi đó:

~~~java
Object report = new Object() {
    String title = "Java";
    String summary() {
        return title + " 10";
    }
};
// report.summary(); // lỗi biên dịch: Object không có summary()
~~~

Hai đoạn đều tạo một đối tượng anonymous class, nhưng **kiểu khai báo của biến khác nhau**. Trường hợp thứ hai chỉ công khai API của `Object` qua biến `report`.

### 4.2. Giới hạn quan trọng

- Lớp vô danh không có tên Java để tác giả viết lại như một loại dữ liệu cho field, tham số hoặc kiểu trả về công khai.
- Thành viên riêng của anonymous class có thể truy cập được qua biến `var` trong **ngữ cảnh có quyền truy cập phù hợp**; không có nghĩa mọi thành viên `private` của một đối tượng đều tự nhiên trở thành public.
- Nếu gán đối tượng sang `Object` hoặc interface khác, kiểu biên dịch của biến đích chỉ hiển thị các thành viên của `Object`/interface đó.
- Không dùng anonymous class + `var` để lách thiết kế API lâu dài. Khi cần truyền dữ liệu giữa nhiều lớp/phương thức, hãy tạo **class, record hoặc interface có tên** phù hợp.

Với đối tượng dữ liệu nhỏ, bất biến, hiện đại, một `record` có tên thường là giải pháp sáng rõ hơn:

~~~java
record Report(String title, int count) {}

// Trong phương thức:
var report = new Report("Java", 10);
System.out.println(report.title()); // Java
~~~

Record là một tính năng khác của Java hiện đại; đoạn trên chỉ là gợi ý thiết kế **khi cần kiểu có tên**, không phải định nghĩa của non-denotable type.

## 5. Wildcard capture: kiểu nội bộ và upward projection

### 5.1. Wildcard `?` và capture type khác nhau

Ví dụ:

~~~java
List<? extends Number> numbers = List.of(4, 5);
~~~

`List<? extends Number>` là **một kiểu có thể viết trực tiếp**. Nó nói danh sách chứa phần tử thuộc một kiểu cụ thể nào đó là subtype của `Number`, nhưng tại nơi sử dụng không biết chính xác đó là `Integer`, `Double` hay kiểu con nào phù hợp.

Khi truy cập dữ liệu hoặc gọi phương thức generic, compiler có thể tạo một kiểu nội bộ tạm thời, thường hiển thị trong thông báo lỗi dưới dạng `CAP#1 extends Number`. Đây gọi là **capture variable** và không phải tên kiểu bạn được phép gõ vào source.

Giả sử:

~~~java
List<? extends Number> numbers = List.of(4, 5);
var first = numbers.get(0);
System.out.println(first.intValue()); // 4
~~~

Giá trị từ `get(0)` được phân tích với các quy tắc capture. Trong khai báo `var first`, **upward projection** loại bỏ capture variable nội bộ của kiểu initializer, vì vậy có thể dùng `first` như `Number` và gọi `intValue()`. Đây là một trường hợp thích hợp để hiểu cơ chế; không nên dựa vào tên `CAP#1` hiện ra từ IDE hay compiler như một kiểu nguồn có thể viết được.

### 5.2. Vì sao compiler phải làm upward projection?

JLS `14.4.1 mô tả:

1. Lấy kiểu `T` của initializer **khi xem nó như biểu thức độc lập**, không có kiểu đích từ khai báo ở vế trái.
2. Kiểu của biến là **upward projection** của `T` đối với các biến kiểu tổng hợp (*synthetic type variables*) được nhắc đến trong `T`, theo JLS `4.10.5.
3. Nếu `T` là *null type*, khai báo bằng `var` bị từ chối.

Upward projection tìm một kiểu cha phù hợp mà **không còn tham chiếu đến synthetic capture variables**. Tùy cấu trúc generic, phép chiếu có thể đưa kiểu về upper bound hoặc dùng wildcard (`? extends ...`, `? super ...`, `?`). Nó **không có nghĩa mọi kiểu non-denotable đều bị chuyển thành `Object`**.

**Tại sao?** Nếu giữ nguyên một capture variable qua nhiều câu lệnh, phạm vi của kiểu nội bộ sẽ bị kéo dài vượt biểu thức đã sinh capture. Upward projection duy trì ranh giới an toàn: capture variable không “rò rỉ” ra các câu lệnh tiếp theo chỉ vì dùng `var`.

### 5.3. Tránh hiểu nhầm về quyền thêm phần tử

~~~java
List<? extends Number> source = List.of(4, 5);
var first = source.get(0); // Number qua quy tắc suy luận/projection
// source.add(first);       // lỗi biên dịch
~~~

Dù `first` được sử dụng như `Number`, danh sách `List<? extends Number>` vẫn có thể là danh sách của một subtype cụ thể mà caller không biết. Không thể thêm một `Number` tùy ý vào nó; `var` không loại bỏ hạn chế type safety của wildcard.

Ngược lại, có thể ghi:

~~~java
Number value = source.get(0); // đúng khi chỉ cần Number
~~~

Dùng kiểu tường minh thường dễ hiểu hơn khi nghiệp vụ chỉ cần các phương thức của `Number`.

### 5.4. Ví dụ `getClass()` cũng cho thấy kiểu phức tạp nhưng có thể viết

~~~java
var clazz = "Java".getClass();
~~~

Theo JLS `14.4.1, `clazz` có kiểu suy luận tương đương `Class<? extends String>` (không tự trở thành `Class<String>`). Ở đây kiểu với wildcard **có cú pháp viết được**; đây là ví dụ cho thấy `var` không chỉ suy luận những kiểu đơn giản, chứ không có nghĩa bản thân `Class<? extends String>` là non-denotable.

## 6. Những trường hợp `var` chấp nhận và từ chối

Bảng sau phân biệt **initializer non-denotable được phép** với **initializer không thể suy luận**:

| Cú pháp (trong phương thức) | Hợp lệ? | Lý do |
| --- | --- | --- |
| `var n = 10;` | Có | Kiểu `int` đơn giản, denotable. |
| `var a = new Object() { int x = 1; };` | Có | Giữ được kiểu anonymous class. |
| `var b = (Runnable & AutoCloseable) resource;` | Có nếu cast hợp lệ | Giữ intersection type. |
| `var c = "Java".getClass();` | Có | Suy luận `Class<? extends String>`. |
| `var d = numbers.get(0);` | Có nếu `numbers` phù hợp | Capture nếu phát sinh được upward projection. |
| `var e = null;` | Không | Initializer có *null type*, bị JLS từ chối. |
| `var f = () -> "Hello";` | Không | Lambda không có target type trong biểu thức độc lập. |
| `var g = String::length;` | Không | Method reference không có target type. |
| `var h;` | Không | Thiếu initializer. |
| `var x = 1, y = 2;` | Không | `var` không hỗ trợ nhiều declarator trong cùng khai báo. |

**Điểm phân biệt quan trọng:** `null` cũng là một kiểu không có tên trong mô hình kiểu của Java, nhưng `var x = null;` **bị từ chối**, còn anonymous class type và intersection type **có thể được suy luận**. Vì thế không thể khẳng định “`var` nhận mọi non-denotable type”.

Nếu muốn dùng lambda/method reference, hãy cung cấp **kiểu đích**:

~~~java
java.util.function.Supplier<String> factory = () -> "Hello";
java.util.function.ToIntFunction<String> length = String::length;
~~~

Hoặc có thể viết một cast kiểu hàm để initializer đã có kiểu rõ ràng:

~~~java
var factory = (java.util.function.Supplier<String>) () -> "Hello";
~~~

Đây là cách dùng khác với suy luận kiểu giao nhau; hãy chọn cách rõ ràng nhất cho code đang bảo trì.

## 7. Các khác biệt ngữ nghĩa cần nhớ

### 7.1. `var` không phải “định kiểu động”

~~~java
var text = "Java"; // String
// text = 10;       // lỗi: int không gán được cho String
~~~

Kiểu của biến do initializer quyết định một lần ở **thời điểm biên dịch**. Với một anonymous class, kiểu của biến là kiểu anonymous class đó; với intersection cast, kiểu biến chứa các ràng buộc giao nhau. Không có việc compiler liên tục tính lại kiểu sau các phép gán.

### 7.2. Không phải lúc nào viết lại tên kiểu bên trái cũng tương đương

~~~java
var named = new java.util.ArrayList<String>(); // ArrayList<String>
java.util.List<String> asInterface = new java.util.ArrayList<>();
~~~

Hai biến có thể tham chiếu đến đối tượng cùng loại nhưng **kiểu khai báo khác nhau**: một bên là `ArrayList<String>`, một bên là `List<String>`. Với anonymous class và intersection type, có khi **không thể** viết một khai báo biến cục bộ có kiểu tường minh tương đương hoàn toàn.

### 7.3. Cần phân biệt kiểu không thể viết, kiểu không truy cập được và kiểu bị xóa

- **Non-denotable**: không thể biểu diễn kiểu đó bằng cú pháp nguồn ở vị trí khai báo đang xét, ví dụ anonymous class type hoặc intersection type.
- **Không truy cập được**: tên kiểu có thể tồn tại nhưng code hiện tại bị giới hạn quyền truy cập bởi package/module/access modifier.
- **Type erasure**: quy tắc triển khai generic khi biên dịch, không biến `var` thành một đối tượng runtime chứa danh sách tất cả các interface của intersection.

Những khái niệm này liên quan đến hệ thống kiểu Java nhưng **không đồng nghĩa** với nhau.

## 8. Chương trình độc lập: xác nhận anonymous class, intersection type và projection

Tạo tệp **`AdvancedVarTypesDemo.java`**:

~~~java
import java.util.List;

public class AdvancedVarTypesDemo {
    static final class Dual implements Runnable, AutoCloseable {
        @Override
        public void run() {
            System.out.println("run");
        }

        @Override
        public void close() {
            System.out.println("close");
        }
    }

    static void showFirst(List<? extends Number> numbers) {
        var first = numbers.get(0);
        System.out.println("first=" + first.intValue());
    }

    public static void main(String[] args) throws Exception {
        var both = (Runnable & AutoCloseable) new Dual();
        both.run();
        both.close();

        var text = (CharSequence & Comparable<String>) "Java";
        System.out.println(
                "intersection=" + text.length() + "/" + text.compareTo("Java"));

        var anonymous = new Object() {
            String title() {
                return "local";
            }
        };
        System.out.println("anonymous=" + anonymous.title());

        var clazz = "alpha".getClass();
        System.out.println("class=" + clazz.getSimpleName());

        showFirst(List.of(4, 5));
    }
}
~~~

Chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac AdvancedVarTypesDemo.java
java AdvancedVarTypesDemo
~~~

**Kết quả stdout:**

~~~text
run
close
intersection=4/0
anonymous=local
class=String
first=4
~~~

### Giải thích chính xác các dòng kết quả

1. **`run` và `close`:** biến `both` có intersection type `Runnable & AutoCloseable`, nên cả hai phương thức đều gọi được. Chữ ký `main throws Exception` đáp ứng khả năng `close()` khai báo checked exception ở interface.
2. **`intersection=4/0`:** `text.length()` là 4 và `text.compareTo("Java")` là 0, chứng minh hai interface cùng đóng góp API cho biến `text`.
3. **`anonymous=local`:** `anonymous` có kiểu của anonymous class, nên gọi được phương thức `title()` do lớp vô danh khai báo.
4. **`class=String`:** `clazz` có kiểu phù hợp với `Class<? extends String>`; tên đơn giản của lớp ở runtime là `String`.
5. **`first=4`:** `numbers.get(0)` bắt nguồn từ wildcard; phép suy luận và upward projection cho phép sử dụng `first` như `Number` để gọi `intValue()`.

Ví dụ sử dụng thư viện Java chuẩn và các tính năng vẫn được hỗ trợ. Nó không cần reflection hoặc khai báo kiểu nội bộ của compiler như `CAP#1`.

## 9. Khi nào nên dùng `var`, khi nào nên khai báo kiểu có tên?

| Mục đích | Phương án nên cân nhắc | Vì sao |
| --- | --- | --- |
| Đoạn xử lý cục bộ ngắn với anonymous class | `var local = new Object() { ... };` | Có thể truy cập thành viên cục bộ của anonymous class. |
| Giá trị phải đồng thời thỏa nhiều interface tại một nơi sử dụng | `var both = (A & B) instance;` | Giữ intersection type sau cast; tránh phải đổi qua lại giữa A/B. |
| Ràng buộc generic được dùng ở nhiều phương thức | `<T extends A & B>` | Giao diện sử dụng thể hiện được ràng buộc bằng type parameter. |
| Kiểu giao nhau là hợp đồng nghiệp vụ lâu dài | Khai báo một interface/class có tên | Dễ đọc, dễ tái sử dụng và tài liệu hóa API. |
| Chỉ cần đọc phần tử `Number` từ `List<? extends Number>` | `Number item = source.get(0);` | Đủ ý nghĩa, không phơi bày tính phức tạp của capture. |
| Kiểu generic hoặc wildcard không hiển nhiên | Khai báo tường minh nếu giúp rõ ngữ nghĩa | Giảm nguy cơ hiểu nhầm kiểu suy luận. |
| API public, field, tham số hoặc kiểu trả về | Kiểu có tên và truy cập được | `var` của Java 10 chủ yếu dành cho khai báo cục bộ hợp lệ. |

**Nguyên tắc thực tế:** dùng `var` vì code trở nên rõ hơn, không phải chỉ vì type inference có thể tạo ra một kiểu rất phức tạp. Khi API cần ổn định, một abstraction có tên thường tốt hơn anonymous type hay intersection type quá chi tiết.

## 10. Lỗi thường gặp và cách chẩn đoán

### “Vì có `var` nên chắc kiểu của biến là `Object`”

Sai. Với `var anonymous = new Object() { String title(){...} };`, compiler có thể giữ kiểu anonymous class và cho gọi `anonymous.title()`. Với `Object anonymous = ...;`, thành viên riêng đó không nằm trong API của biến. **Đừng tự thay `var` bằng `Object` rồi giả định mã sẽ tương đương.**

### “Không thể viết kiểu giao nhau ở bất kỳ đâu trong Java”

Sai. `Runnable & AutoCloseable` hợp lệ ở **cast** và bound của type parameter như `<T extends Runnable & AutoCloseable>`. Điều không hợp lệ ở đây là viết nó nguyên dạng thành **kiểu biến cục bộ tường minh**: `Runnable & AutoCloseable x = ...;`.

### “Kiểu suy luận phải luôn có tên Java viết được”

Sai. JLS `14.4.1 cho phép `var` suy luận anonymous class type và intersection type. Bản thân `var` không bắt buộc một phép biến đổi về `Object` nếu điều đó làm mất API của expression.

### “Wildcard capture và wildcard là cùng một thứ”

Không hẳn. `? extends Number` là một đối số kiểu **viết được**; capture variable như `CAP#1` là khái niệm **nội bộ** của compiler. Upward projection xử lý cách synthetic capture types xuất hiện trong kiểu của biến `var`.

### “`var` giữ nguyên mọi capture variable”

Sai. Kiểu biến được xác định bằng upward projection đối với synthetic type variables. Điều này ngăn capture variable nội bộ kéo dài phạm vi vượt biểu thức ban đầu.

### “`var x = null;` suy luận kiểu non-denotable nên hợp lệ”

Sai. Null type là trường hợp **bị từ chối rõ ràng** trong JLS. Tương tự, lambda hay method reference đứng một mình không có target type phù hợp để suy luận trong khai báo `var`.

### “Intersection type có nghĩa có thể gọi bất kỳ phương thức nào của mọi đối tượng”

Sai. Chỉ những thành viên do các thành phần kiểu giao nhau cung cấp và thỏa quy tắc truy cập/kiểm tra kiểu mới có thể gọi. Intersection type là **phép AND của các ràng buộc**, không phải bỏ qua type checking.

## 11. Bài tập kiểm tra

**Câu 1.** Vì sao hai dòng dưới đây có hành vi biên dịch khác nhau?

~~~java
var a = new Object() {
    String name() { return "A"; }
};
Object b = new Object() {
    String name() { return "B"; }
};
System.out.println(a.name());
// System.out.println(b.name()); // lỗi biên dịch
~~~

**Đáp án:** `a` mang kiểu anonymous class có thành viên `name()`. `b` được khai báo tường minh là `Object`, vốn không có `name()`. Khác biệt nằm ở **kiểu biên dịch của biến**, không phải lớp runtime không tồn tại.

**Câu 2.** Vì sao `var both = (Runnable & AutoCloseable) value;` có thể gọi cả `run()` lẫn `close()`, còn `Runnable only = ...;` chỉ thấy `run()`?

**Đáp án:** Kiểu giao nhau bảo toàn hai ràng buộc của biểu thức cast; kiểu tường minh `Runnable` chỉ nêu một interface. Cast còn phải hợp lệ với giá trị runtime.

**Câu 3.** `Runnable & AutoCloseable x = ...;` có hợp lệ như khai báo biến cục bộ không?

**Đáp án:** Không. Intersection type không được viết theo cú pháp đó ở vị trí kiểu biến cục bộ. Có thể biểu diễn ở cast, bound của generic hoặc suy luận qua `var`.

**Câu 4.** `List<? extends Number>` và `CAP#1 extends Number` khác nhau ra sao?

**Đáp án:** `List<? extends Number>` là kiểu nguồn với wildcard viết được. `CAP#1` biểu thị một capture variable tổng hợp do compiler tạo ra trong quá trình phân tích generic. `var` sử dụng upward projection để capture variable không rò rỉ ra các câu lệnh tiếp theo.

**Câu 5.** Có thể dùng `var f = () -> 42;` để tạo `Supplier<Integer>` không?

**Đáp án:** Không. Lambda đơn độc thiếu target type. Viết `Supplier<Integer> f = () -> 42;` hoặc cast lambda thành functional interface nếu cần một expression có kiểu để `var` suy luận.

**Câu 6.** `var clazz = "Java".getClass();` có kiểu nào và nó có phải anonymous type không?

**Đáp án:** Kiểu được mô tả là `Class<? extends String>`. Đây là một kiểu generic **viết được**, không phải anonymous class type. Không nên đồng nhất *kiểu phức tạp* với *kiểu không thể viết trực tiếp*.

## 12. Checklist áp dụng

- [ ] Xác định kiểu của initializer theo cơ chế của Java, không suy từ chữ `var`.
- [ ] Hiểu intersection type là giá trị thỏa **tất cả** các thành phần `A & B`.
- [ ] Phân biệt intersection cast/generic bound với cú pháp khai báo biến cục bộ.
- [ ] Biết anonymous class type có thể được giữ trong biến `var` và mất API riêng khi upcast.
- [ ] Phân biệt wildcard có cú pháp nguồn và capture variable tổng hợp của compiler.
- [ ] Hiểu upward projection nhằm loại synthetic type variables khỏi kiểu biến `var`.
- [ ] Nhớ `var x = null;`, lambda độc lập và method reference độc lập vẫn không hợp lệ.
- [ ] Cân nhắc interface/record/class có tên nếu dữ liệu vượt ra ngoài phạm vi cục bộ.
- [ ] Xác minh các initializer phức tạp bằng `javac` và JLS khi IDE suy luận kiểu khó đọc.

## 13. Tài liệu tham khảo chính thống

- [Java Language Specification 25, `14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1): công thức suy luận kiểu `var`, ví dụ intersection/anonymous type và quy tắc upward projection.
- [Java Language Specification 25, `4.9 — Intersection Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.9): định nghĩa intersection type và các nơi phát sinh.
- [Java Language Specification 25, `4.10.4 — Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.4): cách compiler tìm kiểu cha chung của nhiều kiểu.
- [Java Language Specification 25, `4.10.5 — Type Projections](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.5): upward/downward projection và synthetic type variables.
- [Java Language Specification 25, `5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.10): quy tắc capture của wildcard.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): mục tiêu thiết kế của `var` từ Java 10.

**Ghi nhớ cuối bài:** `var` có thể mang một **intersection type** hoặc **anonymous class type** không viết được trực tiếp ở khai báo biến cục bộ; nhưng các **capture variables** tổng hợp trong kiểu initializer được xử lý bằng **upward projection**, và một số biểu thức như `null`/lambda độc lập vẫn không đủ điều kiện suy luận. Đây là cơ chế kiểm tra kiểu tĩnh còn nguyên giá trị trong Java hiện đại.