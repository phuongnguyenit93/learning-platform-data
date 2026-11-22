# Đặc tính dựa trên giá trị và tránh phụ thuộc định danh

Trong Java 9, các factory method `List.of()`, `Set.of()`, `Map.of()`, `Map.ofEntries()` và `Map.entry()` tạo ra các collection hoặc entry không cho phép sửa đổi. Các đối tượng collection được tạo theo cách này có **đặc tính dựa trên giá trị (value-based)**: chương trình nên xem chúng là giá trị được xác định bởi nội dung, thay vì dựa vào danh tính của từng object.

Điều này ảnh hưởng trực tiếp đến cách so sánh, lưu trữ và đồng bộ hóa. Hãy dùng `equals()` và `hashCode()` để làm việc với giá trị. Tránh dùng tham chiếu collection làm khóa đồng bộ và không dựa vào việc hai lần gọi factory có trả về cùng một instance hay không.

## Mục tiêu

- Hiểu sự khác nhau giữa equality theo giá trị và identity của object.
- Nhận biết các factory method collection được bổ sung trong Java 9.
- Nắm các đặc điểm không cho sửa đổi, từ chối `null`, xử lý phần tử hoặc key trùng và thứ tự duyệt.
- Tránh các thao tác phụ thuộc identity như so sánh tham chiếu, identity hash code và đồng bộ hóa trên chính collection.
- Chọn đúng collection factory và kiểm thử theo hợp đồng API.

## 1. Value-based nghĩa là gì?

Java có hai cách nhìn khác nhau về object:

| Cách nhìn | Câu hỏi | Cách kiểm tra |
| --- | --- | --- |
| Equality theo giá trị | Hai object có biểu diễn cùng nội dung hay không? | `equals()` và `hashCode()` |
| Identity | Hai biến có cùng trỏ đến một object cụ thể hay không? | `==`, `System.identityHashCode()` và các thao tác dựa trên monitor của object |

Với một value-based object, hợp đồng API yêu cầu chương trình quan tâm đến giá trị mà object biểu diễn. Danh tính của instance không phải một phần của hợp đồng. Vì vậy, không được giả định rằng hai lần tạo collection có cùng nội dung sẽ tạo ra hai object khác nhau, hoặc luôn tạo ra cùng một object.

Factory có thể tạo instance mới hoặc tái sử dụng instance phù hợp. Cách triển khai cụ thể có thể thay đổi giữa các phiên bản Java hoặc giữa các lần chạy. Chương trình dựa vào identity sẽ trở nên không ổn định dù nội dung collection không đổi.

Ví dụ về equality theo giá trị:

~~~java
List<String> first = List.of("Java", "Kotlin");
List<String> second = List.of("Java", "Kotlin");

System.out.println(first.equals(second)); // true
~~~

Hai list có cùng phần tử theo cùng thứ tự nên `equals()` trả về `true`. Đây là hợp đồng cần dùng khi so sánh nội dung. Không cần và không nên kiểm tra xem hai biến có trỏ đến cùng một instance hay không.

## 2. Các factory method collection trong Java 9

Java 9 cung cấp các factory method tĩnh để tạo collection ngắn gọn, không cho sửa đổi:

| API | Kết quả | Đặc điểm chính |
| --- | --- | --- |
| `List.of(e1, e2, ...)` | `List<E>` | Giữ thứ tự phần tử; cho phép phần tử trùng; từ chối `null` |
| `Set.of(e1, e2, ...)` | `Set<E>` | Không cho phần tử trùng theo `equals()`; thứ tự duyệt không được bảo đảm; từ chối `null` |
| `Map.of(k1, v1, ...)` | `Map<K,V>` | Key phải duy nhất theo `equals()`; value có thể trùng; thứ tự duyệt không được bảo đảm; từ chối key/value `null` |
| `Map.ofEntries(entry1, entry2, ...)` | `Map<K,V>` | Tạo map từ nhiều `Map.Entry`; key phải duy nhất; từ chối entry, key hoặc value `null` |
| `Map.entry(key, value)` | `Map.Entry<K,V>` | Tạo entry không cho thay key/value; từ chối key/value `null`; bản thân entry có đặc tính value-based |

`List.of()`, `Set.of()` và `Map.of()` cũng có overload không tham số để tạo collection rỗng. Các API trả về interface chuẩn (`List`, `Set`, `Map`, `Map.Entry`); không nên phụ thuộc vào class triển khai nội bộ.

### 2.1. `List.of()`

`List.of()` tạo list không cho sửa đổi và giữ nguyên thứ tự phần tử được truyền vào. Phần tử trùng được phép:

~~~java
List<String> languages = List.of("Java", "Java", "Kotlin");
System.out.println(languages);
~~~

Kết quả:

~~~text
[Java, Java, Kotlin]
~~~

List so sánh theo thứ tự: hai list chỉ bằng nhau theo `equals()` nếu có cùng số phần tử và các phần tử tương ứng bằng nhau theo đúng thứ tự.

### 2.2. `Set.of()`

`Set.of()` tạo set không cho sửa đổi. Hai phần tử được xem là trùng nếu chúng bằng nhau theo `equals()`. Nếu đối số có phần tử trùng, factory ném `IllegalArgumentException` thay vì âm thầm loại bỏ một phần tử.

~~~java
Set<String> languages = Set.of("Java", "Kotlin", "Go");
~~~

Set không cam kết thứ tự duyệt cho collection tạo bởi `Set.of()`. Không viết logic hoặc bài kiểm thử giả định phần tử sẽ luôn được duyệt theo thứ tự truyền vào.

### 2.3. `Map.of()`

`Map.of()` nhận các cặp key/value. Key phải duy nhất theo `equals()`; value không cần duy nhất. Nếu có key trùng, factory ném `IllegalArgumentException`.

~~~java
Map<String, Integer> versions = Map.of(
    "Java", 9,
    "Kotlin", 8,
    "Go", 7
);

System.out.println(versions.get("Java")); // 9
~~~

Các overload trực tiếp của `Map.of()` hỗ trợ tối đa 10 cặp key/value. Khi cần tạo map từ nhiều hơn 10 cặp, dùng `Map.ofEntries()`.

### 2.4. `Map.ofEntries()` và `Map.entry()`

`Map.entry(key, value)` tạo một entry không cho thay đổi key hoặc value. `Map.ofEntries()` nhận các entry này để tạo map:

~~~java
Map<String, Integer> versions = Map.ofEntries(
    Map.entry("Java", 9),
    Map.entry("Kotlin", 8),
    Map.entry("Go", 7)
);
~~~

`Map.ofEntries()` phù hợp khi có nhiều cặp key/value hoặc khi dữ liệu đã có dạng các entry. Nếu hai entry có key bằng nhau theo `equals()`, việc tạo map thất bại với `IllegalArgumentException`.

## 3. Các đặc điểm chung cần nhớ

### 3.1. Không cho sửa đổi

Collection được tạo bởi các factory trên không hỗ trợ thao tác thay đổi cấu trúc hoặc thay phần tử. Các lời gọi như `add`, `remove`, `clear`, `set`, `put` hoặc `replace` sẽ ném `UnsupportedOperationException`.

~~~java
List<String> names = List.of("An", "Binh");
names.add("Chi"); // UnsupportedOperationException
~~~

Không nên dùng một lời gọi mutator để kiểm tra xem collection có cho sửa đổi hay không trong luồng nghiệp vụ. Hãy chọn đúng loại collection từ đầu và thiết kế API theo hợp đồng không cho sửa đổi.

### 3.2. Không chấp nhận `null`

`List.of()` và `Set.of()` từ chối phần tử `null`. `Map.of()` và `Map.entry()` từ chối cả key `null` lẫn value `null`. `Map.ofEntries()` cũng từ chối entry `null` và các entry có key hoặc value `null`.

Đầu vào không hợp lệ sẽ gây `NullPointerException` ngay trong quá trình tạo collection. Nếu miền dữ liệu cần biểu diễn giá trị vắng mặt, hãy biểu diễn trạng thái đó rõ ràng bằng kiểu dữ liệu phù hợp hoặc chọn một implementation có hợp đồng hỗ trợ `null`; đừng truyền `null` vào các factory này.

### 3.3. Collection không cho sửa đổi không có nghĩa là bất biến sâu

Factory bảo vệ cấu trúc collection, không tự biến các object bên trong thành immutable. Nếu phần tử là object có thể thay đổi, trạng thái nội bộ của phần tử vẫn có thể thay đổi sau khi collection được tạo.

~~~java
final class Profile {
    private String displayName;

    Profile(String displayName) {
        this.displayName = displayName;
    }

    void rename(String newName) {
        this.displayName = newName;
    }

    String displayName() {
        return displayName;
    }
}

Profile profile = new Profile("Lan");
List<Profile> profiles = List.of(profile);
profile.rename("Lan Nguyen");
System.out.println(profiles.get(0).displayName()); // Lan Nguyen
~~~

List vẫn giữ nguyên phần tử `profile` và không cho thay cấu trúc, nhưng object `Profile` bên trong đã thay đổi. Đây là tính không cho sửa đổi ở cấp collection, không phải deep immutability.

Nếu phần tử được dùng làm key của map hoặc thành viên của set, cần đặc biệt thận trọng khi trạng thái có thể thay đổi làm thay đổi `equals()` hoặc `hashCode()`. Thay đổi đó có thể khiến việc tra cứu hoặc kiểm tra membership không còn hoạt động như mong đợi.

### 3.4. Thứ tự duyệt

- `List.of()` giữ thứ tự phần tử theo đối số.
- `Set.of()` không cam kết thứ tự duyệt.
- `Map.of()` và `Map.ofEntries()` không cam kết thứ tự duyệt entry.

Chỉ dựa vào thứ tự khi hợp đồng API bảo đảm điều đó. Nếu cần kết quả có thứ tự cụ thể, hãy chọn một implementation có hợp đồng thứ tự phù hợp và kiểm thử theo hợp đồng ấy.

## 4. Tránh phụ thuộc vào identity

Đặc tính value-based của các collection factory có ba hệ quả thực tế.

### 4.1. Không dùng `==` để so sánh nội dung

`==` kiểm tra hai tham chiếu có cùng trỏ đến một object hay không. Nó không kiểm tra hai collection có cùng phần tử hay không.

~~~java
List<String> first = List.of("Java", "Kotlin");
List<String> second = List.of("Java", "Kotlin");

boolean sameContents = first.equals(second);
~~~

Dùng `equals()` cho equality theo giá trị. Không viết logic nghiệp vụ dựa trên kết quả `first == second`, vì identity của instance không được factory cam kết.

### 4.2. Không dựa vào identity hash code

`System.identityHashCode(object)` tạo hash code gắn với identity của object, không phải hash code theo nội dung mà collection dùng trong hợp đồng `hashCode()`. Với value-based collection, identity không phải dữ liệu ổn định để phân loại hoặc so sánh.

Nếu cần hash theo giá trị, dùng `collection.hashCode()` và bảo đảm các object phần tử có `equals()`/`hashCode()` nhất quán. Không dùng identity hash code để tạo ID nghiệp vụ hoặc để quyết định hai collection có cùng nội dung.

### 4.3. Không đồng bộ hóa trên collection value-based

Không dùng chính collection được tạo bởi các factory này làm monitor:

~~~java
synchronized (List.of("Java", "Kotlin")) {
    // Không dùng collection value-based làm khóa đồng bộ.
}
~~~

Việc đồng bộ hóa dựa trên identity của object. Khi identity không thuộc hợp đồng, hai đoạn mã có thể không khóa cùng monitor như người viết mong đợi.

Nếu cần khóa, tạo một object chuyên dụng có identity ổn định và giữ nó ở phạm vi phù hợp:

~~~java
private static final Object LOCK = new Object();

void updateSharedState() {
    synchronized (LOCK) {
        // Đọc hoặc cập nhật trạng thái dùng chung.
    }
}
~~~

Trong ứng dụng cần cơ chế đồng bộ phức tạp hơn, dùng các công cụ trong `java.util.concurrent` phù hợp với bài toán. Collection value-based vẫn chỉ đóng vai trò lưu trữ dữ liệu.

## 5. Phân biệt với wrapper không cho sửa đổi

`Collections.unmodifiableList(list)` tạo một view không cho sửa đổi thông qua wrapper. Nếu một đoạn mã khác vẫn giữ tham chiếu đến list gốc và sửa nó, view sẽ phản ánh thay đổi đó.

Ngược lại, `List.of(e1, e2, ...)` tạo một list không cho sửa đổi từ các phần tử được cung cấp; nó không phải view có thể quan sát một list nguồn đang tiếp tục thay đổi. Tuy nhiên, các object phần tử vẫn có thể mutable như đã trình bày.

| Tiêu chí | Factory `List.of()` | `Collections.unmodifiableList(source)` |
| --- | --- | --- |
| Sửa cấu trúc qua collection trả về | Không hỗ trợ | Không hỗ trợ qua wrapper |
| Thay đổi list nguồn bên ngoài | Không có list nguồn được bọc làm view | Có thể phản ánh thay đổi của `source` |
| Identity của collection trả về | Value-based; không được dựa vào identity | Không nên giả định về chi tiết identity ngoài hợp đồng wrapper |
| Trạng thái phần tử | Phần tử có thể mutable | Phần tử có thể mutable |

Chọn factory khi cần một collection không cho sửa đổi được tạo trực tiếp từ các giá trị đầu vào. Chọn unmodifiable view khi cần cung cấp quyền đọc thông qua một wrapper của collection đang được quản lý ở nơi khác và chấp nhận rằng thay đổi từ nguồn sẽ được nhìn thấy.

## 6. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ dưới đây minh họa factory method, equality theo giá trị và một số điều kiện đầu vào. Chương trình không kiểm tra identity và không phụ thuộc thứ tự duyệt của `Set` hoặc `Map`.

**Tệp:** `CollectionValueBasedDemo.java`

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionValueBasedDemo {
    public static void main(String[] args) {
        List<String> languages = List.of("Java", "Kotlin", "Go");
        List<String> sameValues = List.of("Java", "Kotlin", "Go");
        Set<String> topics = Set.of("java", "collections");
        Map<String, Integer> versions = Map.of("Java", 9, "Kotlin", 8);
        Map<String, Integer> moreVersions = Map.ofEntries(
            Map.entry("Java", 9),
            Map.entry("Kotlin", 8),
            Map.entry("Go", 7)
        );

        System.out.println(languages);
        System.out.println(languages.equals(sameValues));
        System.out.println(topics.contains("java"));
        System.out.println(versions.get("Java"));
        System.out.println(moreVersions.get("Go"));

        try {
            languages.add("Rust");
        } catch (UnsupportedOperationException exception) {
            System.out.println("list is unmodifiable");
        }

        try {
            Set.of("Java", "Java");
        } catch (IllegalArgumentException exception) {
            System.out.println("duplicate set element");
        }

        try {
            Map.of("Java", 9, "Java", 10);
        } catch (IllegalArgumentException exception) {
            System.out.println("duplicate map key");
        }

        try {
            List.of("Java", null);
        } catch (NullPointerException exception) {
            System.out.println("null elements are rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 9 trở lên:

~~~text
javac --release 9 CollectionValueBasedDemo.java
java CollectionValueBasedDemo
~~~

Output:

~~~text
[Java, Kotlin, Go]
true
true
9
7
list is unmodifiable
duplicate set element
duplicate map key
null elements are rejected
~~~

Output không in toàn bộ `Set` hoặc `Map`, vì thứ tự duyệt của các collection đó không được bảo đảm. Dòng `true` thứ nhất là kết quả so sánh hai list bằng `equals()`.

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dùng `==` để so sánh hai collection | Nhầm identity với equality theo giá trị | Dùng `equals()` |
| Dùng collection làm khóa `synchronized` | Monitor dựa trên identity của object | Tạo khóa riêng, có identity ổn định |
| Dùng `System.identityHashCode()` làm hash nội dung | Identity hash code không phản ánh hợp đồng giá trị của collection | Dùng `hashCode()` |
| Truyền phần tử trùng vào `Set.of()` | Set factory yêu cầu phần tử duy nhất theo `equals()` | Loại trùng hoặc chọn API có hành vi xử lý trùng đúng với yêu cầu |
| Truyền key trùng vào `Map.of()` hoặc `Map.ofEntries()` | Map không thể có hai mapping cùng key theo `equals()` | Chuẩn hóa key trước khi tạo map |
| Truyền `null` vào factory | Các factory này không hỗ trợ null | Kiểm tra dữ liệu hoặc chọn collection có hợp đồng null phù hợp |
| Gọi `add`, `remove` hoặc `put` | Collection factory không hỗ trợ sửa đổi | Tạo collection mutable riêng nếu nghiệp vụ cần cập nhật |
| Giả định Set/Map duyệt theo thứ tự đầu vào | API không cam kết thứ tự đó | Dùng implementation có hợp đồng thứ tự phù hợp |
| Nghĩ phần tử bên trong cũng immutable | Collection chỉ bảo vệ cấu trúc | Dùng phần tử immutable hoặc sao chép dữ liệu khi cần bất biến sâu |

## 8. Quy tắc thực hành

1. Dùng `List.of()`, `Set.of()`, `Map.of()` hoặc `Map.ofEntries()` khi dữ liệu cần một collection không cho sửa đổi.
2. Dùng `equals()` và `hashCode()` để so sánh hoặc làm việc với giá trị collection.
3. Không dựa vào `==`, `System.identityHashCode()` hoặc identity của collection factory.
4. Không đồng bộ hóa trên collection value-based; dùng một khóa riêng hoặc công cụ đồng bộ thích hợp.
5. Kiểm tra dữ liệu trùng và `null` trước khi gọi factory nếu dữ liệu đến từ nguồn bên ngoài.
6. Không giả định thứ tự duyệt của `Set.of()`, `Map.of()` hoặc `Map.ofEntries()`.
7. Nhớ rằng collection không cho sửa đổi không đồng nghĩa với các phần tử bên trong cũng bất biến.
8. Chọn `Collections.unmodifiableList()` khi cần một view đọc-only của một list nguồn đang được quản lý riêng; hiểu rằng view phản ánh thay đổi của nguồn.

## 9. Tự kiểm tra

- Hai lần gọi `List.of("Java", "Kotlin")` có được bảo đảm trả về cùng một instance không? Không. Identity không phải một phần của hợp đồng value-based.
- Khi cần so sánh hai list có cùng nội dung, dùng toán tử hay phương thức nào? Dùng `equals()`.
- `Set.of("Java", "Java")` có tự loại bỏ phần tử trùng không? Không. Factory ném `IllegalArgumentException`.
- `Map.of()` có cho phép hai key bằng nhau theo `equals()` không? Không. Key trùng gây `IllegalArgumentException`.
- Vì sao không nên `synchronized` trên collection tạo bởi `List.of()`? Vì đồng bộ hóa phụ thuộc identity/monitor của object, trong khi identity của instance value-based không được cam kết.
- `List.of(profile)` có làm object `profile` trở thành immutable không? Không. Cấu trúc list không cho sửa đổi, nhưng object phần tử vẫn có thể thay đổi.
- `Set.of()` và `Map.of()` có bảo đảm thứ tự duyệt không? Không. Không dựa vào thứ tự đó trong logic ứng dụng.

Điểm cốt lõi: **collection value-based được xác định bởi giá trị, không phải identity của instance**. Hãy so sánh bằng `equals()`, tính hash theo `hashCode()`, và dùng một khóa riêng khi cần đồng bộ hóa. Các factory method Java 9 giúp tạo collection ngắn gọn và không cho sửa đổi, đồng thời yêu cầu chương trình tôn trọng hợp đồng về `null`, phần tử trùng và thứ tự duyệt.