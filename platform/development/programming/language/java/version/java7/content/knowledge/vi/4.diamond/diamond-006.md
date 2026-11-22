# Suy luận tham số kiểu từ ngữ cảnh với Diamond (`<>`) và khi cần ghi rõ kiểu

## 1. Mục tiêu

Trong Java, một khai báo generic có thể chứa nhiều tham số kiểu:

~~~java
Map<String, List<Integer>> groups = new HashMap<String, List<Integer>>();
~~~

Nếu vế trái đã xác định đầy đủ kiểu, việc lặp lại `<String, List<Integer>>` ở lệnh khởi tạo làm mã dài hơn mà thường không bổ sung thông tin. Từ **Java 7**, toán tử **diamond** `<>` cho phép trình biên dịch suy luận tham số kiểu của **lớp generic đang được khởi tạo**:

~~~java
Map<String, List<Integer>> groups = new HashMap<>();
~~~

Hai biểu thức trên cùng thể hiện mục đích tạo `HashMap<String, List<Integer>>`. Cú pháp diamond **vẫn đang được hỗ trợ và sử dụng trong Java hiện đại**, không yêu cầu cài JDK 7 cũ. Bài này thực hành trên JDK 21 hoặc JDK mới hơn hỗ trợ biên dịch mức `--release 21`.

Sau bài học, bạn sẽ:

- Hiểu “ngữ cảnh” mà trình biên dịch có thể dùng khi gặp `new ArrayList<>()`.
- Biết chọn giữa **khai báo kiểu bên trái**, **tham số kiểu tường minh bên phải** và **`var`**.
- Nhận ra trường hợp thiếu thông tin khiến `<>` suy luận thành `Object` thay vì kiểu mong muốn.
- Phân biệt suy luận kiểu khi biên dịch với kiểu của dữ liệu ở runtime; tránh raw type và nhầm lẫn variance.
- Biên dịch và chạy ví dụ độc lập, kiểm chứng kết quả thực tế.

## 2. Cơ chế: compiler lấy thông tin kiểu từ đâu?

Giả sử có:

~~~java
List<String> names = new ArrayList<>();
~~~

Trình biên dịch thấy:

1. **Kiểu đích (`target type`)** của biến là `List<String>`.
2. `ArrayList<E>` là lớp generic thực thi `List<E>`.
3. Nó ràng buộc tham số `E` sao cho đối tượng được tạo tương thích với kiểu đích và suy luận `E` là `String`.
4. Mã được kiểm tra kiểu tại **thời điểm biên dịch**. Chẳng hạn, `names.add("Java")` hợp lệ nhưng `names.add(42)` báo lỗi biên dịch.

Điều này không có nghĩa runtime giữ riêng hai lớp `ArrayList<String>` và `ArrayList<Integer>`. Java dùng **type erasure** cho phần lớn thông tin tham số generic ở runtime. Diamond hỗ trợ kiểm tra kiểu tĩnh; bản thân cặp `<>` không tạo kiểu dữ liệu runtime mới.

### 2.1. Ngữ cảnh khai báo hoặc gán

~~~java
List<String> names = new ArrayList<>();
Map<String, Integer> scores = new HashMap<>();

List<String> otherNames;
otherNames = new ArrayList<>();
~~~

Ở mỗi vị trí, ngữ cảnh gán cung cấp kiểu đích. Cũng có thể đặt kiểu cụ thể bên phải nếu muốn:

~~~java
List<String> names = new ArrayList<String>();
~~~

Việc viết đầy đủ cả hai phía vẫn hợp lệ; trong trường hợp rõ ràng như trên, `<>` thường dễ đọc hơn.

### 2.2. Ngữ cảnh đối số khi gọi phương thức

~~~java
static void consume(List<String> values) {
    System.out.println(values.size());
}

// Trong một phương thức khác:
consume(new ArrayList<>());
~~~

Đây là **đoạn mã minh họa**, cần đặt trong lớp để chạy. Tham số `List<String>` của `consume` cung cấp ngữ cảnh cho `new ArrayList<>()`; trình biên dịch không mặc định chọn `ArrayList<Object>` ở mọi chỗ.

Khi lời gọi có overload, generic bounds hoặc nhiều tham số phụ thuộc nhau, việc suy luận phải thỏa **toàn bộ ràng buộc**. Nếu không thể xác định một phương án hợp lệ, trình biên dịch báo lỗi; `<>` không có quyền lờ đi các ràng buộc kiểu.

### 2.3. Ngữ cảnh kiểu trả về

~~~java
static List<String> emptyNames() {
    return new ArrayList<>();
}
~~~

Phương thức khai báo trả về `List<String>`, vì vậy `new ArrayList<>()` trong `return` được kiểm tra theo kiểu đích tương ứng. Đây là cú pháp hợp lệ trên JDK hiện đại và biên dịch ở mức Java 21.

### 2.4. Dữ liệu truyền vào constructor cũng có thể ràng buộc kiểu

~~~java
var copy = new ArrayList<>(List.of("A", "B"));
~~~

Ở đây không có khai báo `List<String>` bên trái, nhưng `List.of("A", "B")` cung cấp các giá trị kiểu `String`; trình biên dịch suy luận được kiểu phần tử, nên `copy` có kiểu `ArrayList<String>`.

Hai cú pháp đi kèm là tính năng hiện đại: `List.of(...)` có từ Java 9 và suy luận biến cục bộ bằng `var` có từ Java 10. **Diamond có từ Java 7**; không nên nhầm lịch sử ra đời của từng tính năng. Ví dụ toàn bài chủ động dùng JDK 21 để thể hiện cách viết còn áp dụng.

## 3. Khi thiếu ngữ cảnh: `var` + `<>` không biết kiểu bạn sẽ thêm sau này

Xem hai khai báo:

~~~java
List<String> names = new ArrayList<>();
var values = new ArrayList<>();
~~~

Ở dòng thứ nhất, trình biên dịch biết đích là `List<String>`. Ở dòng thứ hai, `var` yêu cầu suy luận kiểu biến **từ biểu thức khởi tạo**, còn `new ArrayList<>()` không có đối số để ràng buộc `E`. Kiểu được suy luận là `ArrayList<Object>`.

~~~java
var values = new ArrayList<>();
values.add("text");     // Hợp lệ
values.add(21);         // Cũng hợp lệ: phần tử là Object
~~~

Việc thêm chuỗi trước **không khiến** trình biên dịch quay lại sửa kiểu `values` thành `ArrayList<String>`. Kiểu của biến được xác định khi khai báo.

Nếu cần một danh sách chuỗi, chọn **một** trong hai cách:

~~~java
List<String> values = new ArrayList<>(); // Kiểu đích rõ ở vế trái
var values2 = new ArrayList<String>();   // Kiểu generic rõ ở vế phải
~~~

Cả hai buộc danh sách chứa `String` theo kiểm tra kiểu thông thường. Với `var`, có thể giữ kiểu cụ thể bằng cách cung cấp dữ liệu đủ rõ trong constructor, như `var copy = new ArrayList<>(List.of("A", "B"))`.

Tình huống tương tự với một map trống:

~~~java
var cache = new HashMap<>();                // HashMap<Object, Object>
var typedCache = new HashMap<String, Long>(); // HashMap<String, Long>
Map<String, Long> another = new HashMap<>(); // HashMap<String, Long> khi khởi tạo
~~~

Cú pháp `var` hợp lệ đối với **biến cục bộ có biểu thức khởi tạo**, không dùng `var` để suy luận kiểu field, tham số phương thức hoặc kiểu trả về của phương thức thông thường.

**Bài học cốt lõi:** `<>` biểu thị **“hãy suy luận tham số generic theo dữ kiện tại đây”**, không biểu thị **“hãy suy luận từ những giá trị được thêm vào sau này”**.

## 4. Ví dụ Java hoàn chỉnh: suy luận từ nhiều loại ngữ cảnh

Tạo file `src/main/java/demo/DiamondContextExample.java` trong thư mục ví dụ:

~~~java
package demo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class DiamondContextExample {
    private DiamondContextExample() {
    }

    static void acceptStrings(List<String> values) {
        System.out.println("argumentSize=" + values.size());
    }

    static List<String> emptyNames() {
        return new ArrayList<>();
    }

    static void seed(Map<String, List<Integer>> groups) {
        groups.put("backend", new ArrayList<>());
        groups.get("backend").add(7);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Java");

        List<Integer> numbers = new ArrayList<>(List.of(7, 21));
        Map<String, List<Integer>> groups = new HashMap<>();
        seed(groups);
        acceptStrings(new ArrayList<>());

        var loose = new ArrayList<>();
        loose.add("text");
        loose.add(21);

        var strict = new ArrayList<String>();
        strict.add("typed");

        var copy = new ArrayList<>(List.of("A", "B"));

        System.out.println("names=" + names);
        System.out.println("numbers=" + numbers);
        System.out.println("backend=" + groups.get("backend"));
        System.out.println("returned=" + emptyNames());
        System.out.println("loose=" + loose);
        System.out.println("strict=" + strict);
        System.out.println("copy=" + copy);
    }
}
~~~

Từ thư mục chứa `src/`, biên dịch với mức Java 21 và chạy:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/DiamondContextExample.java
java -cp out demo.DiamondContextExample
~~~

Stdout chính xác:

~~~text
argumentSize=0
names=[Java]
numbers=[7, 21]
backend=[7]
returned=[]
loose=[text, 21]
strict=[typed]
copy=[A, B]
~~~

### Diễn giải chi tiết

| Dòng ví dụ | Nguồn thông tin kiểu | Kiểu được xác định |
| --- | --- | --- |
| `List<String> names = new ArrayList<>()` | Kiểu đích ở khai báo | `ArrayList<String>` |
| `List<Integer> numbers = new ArrayList<>(List.of(7, 21))` | Kiểu đích và đối số constructor | `ArrayList<Integer>` |
| `Map<String, List<Integer>> groups = new HashMap<>()` | Hai tham số kiểu từ vế trái | `HashMap<String, List<Integer>>` |
| `groups.put("backend", new ArrayList<>())` | Kiểu đối số thứ hai của `put` | `ArrayList<Integer>` tương thích với `List<Integer>` |
| `acceptStrings(new ArrayList<>())` | Kiểu tham số phương thức | `ArrayList<String>` |
| `return new ArrayList<>()` ở `emptyNames` | Kiểu trả về của phương thức | `ArrayList<String>` |
| `var loose = new ArrayList<>()` | Không có dữ kiện ràng buộc kiểu phần tử | `ArrayList<Object>` |
| `var strict = new ArrayList<String>()` | Kiểu tường minh trên constructor | `ArrayList<String>` |
| `var copy = new ArrayList<>(List.of("A", "B"))` | Đối số constructor đủ xác định kiểu phần tử | `ArrayList<String>` |

`groups.get("backend")` được in riêng thay vì in cả `HashMap` vì không cần dựa vào thứ tự duyệt của map để kiểm tra stdout. Ví dụ độc lập và không phụ thuộc dịch vụ ngoài, đường dẫn cứng, thời gian hay nguồn dữ liệu không ổn định.

## 5. Trường hợp nên ghi kiểu tường minh

Mục tiêu không phải loại bỏ mọi chữ `String`/`Integer`, mà là đặt thông tin kiểu **tại nơi khiến người đọc và compiler hiểu đúng ý nghĩa**.

### 5.1. Khởi tạo container trống bằng `var`

Nếu bắt buộc dùng `var` cho biến cục bộ mà constructor không nhận dữ kiện giúp suy luận, hãy ghi tham số kiểu ở constructor:

~~~java
var users = new ArrayList<String>();
var prices = new HashMap<String, Integer>();
~~~

Nếu muốn chỉ viết kiểu generic ở một chỗ, cách khai báo có kiểu đích cũng rất rõ ràng:

~~~java
List<String> users = new ArrayList<>();
Map<String, Integer> prices = new HashMap<>();
~~~

Chọn cách hợp với quy ước của nhóm; **không** chọn `var x = new ArrayList<>()` chỉ để giảm số ký tự khi yêu cầu danh sách có kiểu phần tử xác định.

### 5.2. Kiểu là một phần của hợp đồng phương thức, field hoặc API

~~~java
private final Map<String, List<Integer>> indexes = new HashMap<>();

public List<String> labels() {
    return new ArrayList<>();
}
~~~

Đây là **đoạn thành viên lớp để minh họa**, không phải file độc lập. Tham số generic ở field/return type là thông tin giao tiếp với các phần mã khác. Diamond chỉ giảm lặp ở biểu thức khởi tạo; nó không thay thế việc công bố hợp đồng kiểu.

### 5.3. Kiểu suy luận được nhưng không rõ nghĩa với người đọc

Nếu một biểu thức constructor phức tạp, việc ghi `new HashMap<String, Integer>(source)` hoặc `Map<String, Integer> copy = new HashMap<>(source)` có thể khiến ý định rõ hơn `var copy = new HashMap<>(source)`, tùy mức dễ đọc của `source`. Quyết định dựa trên **khả năng hiểu mã**; trình biên dịch có thể suy luận đúng mà người đọc vẫn phải truy ngược nhiều chỗ mới thấy kiểu.

### 5.4. Cần một kiểu khác kiểu mặc định suy luận

Nếu không có target type hoặc tham số constructor không đủ thông tin, bạn phải thêm ràng buộc kiểu:

~~~java
var ids = new ArrayList<Long>();
var byCategory = new HashMap<String, List<Long>>();
~~~

`<>` không thể đọc suy nghĩ “sau này chỉ dùng `Long`”. Việc tường minh kiểu cũng giúp IDE và compiler báo lỗi ở đúng chỗ nếu phần tử sai.

### 5.5. Khi generic bounds hoặc overload khiến biểu thức quá mơ hồ

Có trường hợp nhiều ràng buộc generic, lời gọi overload hoặc tham số phương thức generic khiến trình biên dịch không tìm được cách suy luận phù hợp. Hãy đọc thông báo lỗi để xác định ràng buộc nào không thỏa, rồi bổ sung kiểu đích, kiểu generic tường minh hoặc tách biểu thức phức tạp thành biến có kiểu rõ ràng. **Ghi kiểu tường minh không sửa được một phép gán thực sự không tương thích.**

## 6. Những lỗi thường gặp dù có `<>`

### 6.1. Diamond không thay thế generic và không sửa raw type

~~~java
List<String> safe = new ArrayList<>(); // Parameterized type + diamond
List raw = new ArrayList();            // Raw type, bỏ kiểm tra phần tử ở compile time
~~~

Đây là đoạn **minh họa**, không phải chương trình `main`. Với `raw`, compiler có thể phát cảnh báo raw/unchecked; mã dễ bị đưa sai loại dữ liệu và dẫn tới lỗi khi đọc ở chỗ khác. Đừng dùng raw type để “né” lỗi suy luận. `new ArrayList<>()` có diamond; `new ArrayList()` thì không.

### 6.2. Diamond chỉ khởi tạo lớp có generic phù hợp

~~~java
List<String> names = new ArrayList<>(); // Hợp lệ
// List<String> wrong = new List<>();    // Không thể new interface List
// String wrongText = new String<>();    // String không phải lớp generic
~~~

Hai dòng chú thích cố ý minh họa mã **không biên dịch**; `<>` không biến interface thành lớp có thể khởi tạo, không thêm tham số generic vào lớp không khai báo generic.

### 6.3. Generic thường bất biến (invariant)

~~~java
List<Number> numbers = new ArrayList<>(); // Hợp lệ, E suy luận Number
// List<Number> bad = new ArrayList<Integer>(); // Không hợp lệ
~~~

`Integer` là một `Number`, nhưng `List<Integer>` không phải subtype của `List<Number>`. Nếu cần một danh sách chỉ đọc phần tử như `Number` từ các subtype khác nhau, cân nhắc kiểu wildcard phù hợp với API, ví dụ `List<? extends Number>`, và hiểu giới hạn khi thêm phần tử. **Diamond không thay đổi quy tắc variance** của generic.

### 6.4. Suy luận không đồng nghĩa có “kiểu động”

~~~java
List<String> names = new ArrayList<>();
// names.add(42); // Lỗi biên dịch: yêu cầu String
~~~

Kiểu `List<String>` vẫn có hiệu lực trong toàn bộ phạm vi. Với `var`, compiler cũng gán kiểu tĩnh tại khai báo; `var` không giống kiểu động, không tự đổi kiểu khi nhận giá trị sau này.

### 6.5. Kiểu generic không phải chứng cứ runtime

~~~java
List<String> names = new ArrayList<>();
System.out.println(names.getClass().getSimpleName()); // ArrayList
~~~

Đây là đoạn minh họa; class object của `ArrayList<String>` không chứa một runtime class riêng mang tên `ArrayList<String>`. Muốn kiểm tra kiểu dữ liệu từ JSON, API hoặc nguồn bên ngoài, hãy xác định schema/parser/validation phù hợp, không suy luận an toàn dữ liệu từ dấu `<>`.

## 7. Bảng quyết định thực tế

| Bạn đang viết | Cách nên cân nhắc | Lý do |
| --- | --- | --- |
| Biến có kiểu generic rõ bên trái | `List<String> x = new ArrayList<>()` | Giảm lặp và giữ kiểu tĩnh |
| Field của lớp, tham số hoặc kiểu trả về | Khai báo tham số generic trong hợp đồng | Người gọi biết cấu trúc dữ liệu |
| `var` và container trống | `var x = new ArrayList<String>()` | Tránh `Object` do thiếu target type |
| `var` nhưng constructor có dữ liệu đủ rõ | `var x = new ArrayList<>(List.of("A"))` | Compiler suy luận `String` từ đối số |
| Nhiều tầng generic | `Map<String, List<Integer>> x = new HashMap<>()` | Kiểu đích phức hợp vẫn đọc được |
| Kết quả suy luận không khớp yêu cầu | Thêm kiểu đích hoặc kiểu class tường minh, kiểm tra constraints | Xác định chính xác lỗi thay vì né cảnh báo |
| Raw type/ép kiểu unchecked chỉ để biên dịch | Sửa declaration/constructor generic đúng kiểu | Tránh chuyển lỗi kiểu sang runtime |

**Quy tắc thực hành:** Giữ **một chỗ rõ ràng** chứa thông tin kiểu có ý nghĩa trong biểu thức khởi tạo đơn giản. Tránh vừa bỏ mọi thông tin kiểu (`var` + `<>` với container trống), vừa lặp lại đầy đủ kiểu ở cả hai phía khi không cần.

## 8. Tự luyện

**Bài 1 — Suy luận kiểu.** Cho:

~~~java
List<Long> ids = new ArrayList<>();
var values = new ArrayList<>();
var names = new ArrayList<>(List.of("Linh", "An"));
~~~

Hỏi tham số kiểu thực của `ArrayList` ở mỗi dòng là gì?

**Đáp án:** `Long`; `Object`; `String`. Ở dòng thứ nhất suy luận từ kiểu đích, dòng thứ hai không có dữ kiện, dòng thứ ba nhận ràng buộc từ đối số constructor.

**Bài 2 — Sửa lỗi compile.** Xét:

~~~java
var queue = new ArrayList<>();
// List<String> names = queue; // Không tương thích: ArrayList<Object>
~~~

Hãy sửa ngay lúc khai báo `queue` nếu muốn nó chứa chuỗi. **Đáp án:** `var queue = new ArrayList<String>();` hoặc `List<String> queue = new ArrayList<>();`.

**Bài 3 — Gọi phương thức.** Tại sao `acceptStrings(new ArrayList<>())` biên dịch được trong ví dụ hoàn chỉnh? **Đáp án:** Ngữ cảnh đối số cung cấp tham số `List<String>`; trình biên dịch sử dụng nó để ràng buộc diamond.

**Bài 4 — Quy tắc generic.** Vì sao `List<Number> x = new ArrayList<Integer>()` sai dù `Integer extends Number`? **Đáp án:** `List<Integer>` và `List<Number>` không có quan hệ subtype; cách viết với `<>` trên `List<Number>` sẽ suy luận `Number`.

**Bài 5 — Thiết kế API.** Nên chọn `var cache = new HashMap<>()` hay `Map<String, Long> cache = new HashMap<>()` nếu cache bắt buộc ánh xạ mã chuỗi sang số `Long`? **Đáp án:** Chọn khai báo kiểu đích rõ ràng hoặc `var cache = new HashMap<String, Long>()`; biểu thức `var + <>` rỗng suy luận `Object,Object`.

## 9. Checklist và tài liệu chính thức

- [ ] Biết kiểu đích từ khai báo, gán, return hoặc tham số phương thức nếu có.
- [ ] Nhìn rõ phần nào của constructor hoặc các đối số ràng buộc tham số generic.
- [ ] Với `var`, kiểm tra kiểu được suy luận ngay tại biểu thức khởi tạo; không dựa vào lệnh `add`/`put` chạy sau.
- [ ] Không dùng raw type hoặc ép kiểu unchecked để che lỗi.
- [ ] Kiểm tra giới hạn generics: invariant type parameters, interface/abstract class không thể `new` trực tiếp.
- [ ] Các field, tham số và kiểu trả về công khai thể hiện hợp đồng generic chính xác.
- [ ] Ví dụ Java 21 biên dịch và chạy đúng, không dùng công cụ hoặc API đã lỗi thời.

Đối chiếu: [Java Language Specification `15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9), [JLS `5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.2), [Dev.java — Type Inference](https://dev.java/learn/generics/type-inference/). Java dùng diamond từ Java 7, nhưng bài này chỉ thực hành cú pháp và công cụ vẫn phù hợp cho JDK được hỗ trợ hiện nay.