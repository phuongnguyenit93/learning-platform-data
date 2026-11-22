# UnsupportedOperationException và thao tác tùy chọn trong Java

> **Java Core – Exception** · Nhóm: **Ngoại lệ runtime** · Phạm vi chính: các thao tác tùy chọn trên Collection, List, Iterator, Map và sự khác nhau giữa danh sách thay đổi được, danh sách cố định kích thước, view không sửa được và danh sách không sửa được. Ví dụ đã được biên dịch và chạy với **Java 17**.

## 1. UnsupportedOperationException là gì?

`java.lang.UnsupportedOperationException` (UOE) là một **unchecked exception** kế thừa `RuntimeException`. Nó thể hiện rằng thao tác được yêu cầu **không được đối tượng hoặc API cụ thể hỗ trợ**.

~~~text
java.lang.Throwable
└── java.lang.Exception
    └── java.lang.RuntimeException
        └── java.lang.UnsupportedOperationException
~~~

Một ví dụ rất phổ biến:

~~~java
List<String> names = List.of("Lan", "Mai");
names.add("An"); // Ném UnsupportedOperationException.
~~~

Đoạn này là mã Java minh họa trong một method, cần import `java.util.List`. Đối tượng do `List.of(...)` trả về là **unmodifiable list**, nên việc thêm phần tử bằng `add` không được hỗ trợ.

**Điểm cốt lõi:** UOE **không nhất thiết** có nghĩa là “Java chưa cài đặt xong method”. Trong nhiều API của Java Collections Framework, một số thao tác thay đổi nội dung được quy định là **optional operations**: interface có method, nhưng một implementation hợp lệ **được phép không hỗ trợ** thao tác đó. Khi bị yêu cầu thực hiện thao tác không được hỗ trợ, nó có thể ném UOE theo hợp đồng.

Do đó, phải phân biệt:

- **Phương thức có trong interface:** ví dụ biến có kiểu `List<String>` luôn gọi được `add()` về mặt cú pháp.
- **Đối tượng tại runtime có hỗ trợ thao tác đó không:** `ArrayList` cho phép thêm, còn `List.of(...)` không cho phép.
- **Dữ liệu có hợp lệ cho thao tác hay không:** một danh sách hỗ trợ `add` vẫn có thể từ chối phần tử không hợp lệ, chẳng hạn theo chính sách cấm `null`, dẫn đến exception khác.
- **Kết quả có phù hợp nghiệp vụ không:** một thao tác được phép ở runtime vẫn có thể sai về yêu cầu nghiệp vụ.

### Những điều cần đạt sau bài

1. Hiểu vì sao `UnsupportedOperationException` là unchecked và tại sao cùng kiểu `List` có thể có tập thao tác khác nhau.
2. Phân biệt chính xác `Arrays.asList` (**fixed-size, backed by array**), `Collections.unmodifiableList` (**unmodifiable view**) và `List.of` (**unmodifiable list**).
3. Dự đoán UOE với `add`, `remove`, `set`, `clear`, thao tác qua `Iterator`, `Map` và các factory.
4. Biết rằng thao tác **không làm thay đổi gì** chưa chắc được mọi implementation chấp nhận.
5. Viết API khai báo rõ khả năng thay đổi dữ liệu, biết cách tạo mutable copy và không dùng catch UOE để thay cho thiết kế hợp đồng.
6. Kiểm chứng output từ một chương trình Java 17 độc lập.

## 2. “Optional operation” nghĩa chính xác là gì?

Các interface như `Collection<E>`, `List<E>`, `Iterator<E>` và `Map<K,V>` định nghĩa những method chung. Nhưng không phải mọi đối tượng triển khai đều bắt buộc hỗ trợ **mọi thao tác cập nhật**.

Ví dụ:

~~~java
List<String> first = new ArrayList<>();
List<String> second = List.of();
first.add("A");  // Hợp lệ.
second.add("A"); // Ném UnsupportedOperationException.
~~~

Đây là đoạn minh họa cần import `List` và `ArrayList`. Hai biến có **cùng kiểu tĩnh** là `List<String>`, nhưng implementation và hợp đồng mutation khác nhau.

Điều này vẫn tuân quy tắc Java: interface định nghĩa một thao tác có thể gọi; hợp đồng Collection Framework cho phép implementation **không hỗ trợ** một số thao tác cập nhật và thông báo bằng UOE.

### 2.1. Những nhóm thao tác thường là optional

| API | Các thao tác có khả năng không được hỗ trợ | Ví dụ |
| --- | --- | --- |
| `Collection` | `add`, `addAll`, `remove`, `removeAll`, `retainAll`, `clear` | Collection không cho sửa |
| `List` | `set`, `add(index,...)`, `remove(index)` và các thao tác cấu trúc | List cố định kích thước hoặc không cho sửa |
| `Iterator` | `remove()` | Iterator chỉ đọc |
| `ListIterator` | `remove()`, `set(...)`, `add(...)` | Iterator không cho cập nhật |
| `Map` | `put`, `putAll`, `remove`, `clear` | Map không cho sửa |
| `Map.Entry` | `setValue(...)` có thể không được hỗ trợ | Entry chỉ đọc |

Đây là **nhóm ví dụ**, không có nghĩa mọi method của mọi implementation trong bảng đều bắt buộc ném UOE. Tùy implementation, cách gọi và hợp đồng cụ thể, cùng một tên method có thể hoạt động hoặc từ chối.

### 2.2. Unchecked không có nghĩa là có thể bỏ qua

UOE thuộc `RuntimeException`, nên compiler **không bắt buộc** khai báo `throws UnsupportedOperationException` hoặc `catch`. Nhưng nếu xảy ra và không được xử lý, hoạt động hiện tại vẫn kết thúc bất thường.

Một method:

~~~java
static void appendName(List<String> list, String name) {
    list.add(name);
}
~~~

có thể biên dịch dù không `throws`. Nhưng **hợp đồng của method chưa đầy đủ** nếu không nói rõ rằng nó yêu cầu một danh sách có hỗ trợ thêm phần tử. Khi caller truyền `List.of("A")`, method sẽ ném UOE tại runtime.

Nếu API được thiết kế để nhận danh sách chỉ đọc, nó **không nên âm thầm gọi `add`**. Nếu cần thay đổi, hãy tài liệu hóa yêu cầu hoặc tạo mutable copy.

## 3. Phân biệt ba mô hình thường gặp

Nhiều lỗi UOE đến từ việc nhầm ba kiểu đối tượng sau:

| Cách tạo | Thay thế phần tử bằng `set`? | Thêm/xóa làm đổi kích thước? | Quan hệ với dữ liệu nguồn |
| --- | --- | --- | --- |
| `new ArrayList<>(...)` | Có | Có | Tạo list mới chứa các tham chiếu phần tử |
| `Arrays.asList(array)` | **Có** | **Không** | **Backed by** mảng được truyền vào |
| `Collections.unmodifiableList(source)` | Không qua view | Không qua view | **View** phản ánh thay đổi từ source |
| `List.of(...)` | Không | Không | List không sửa được do factory tạo |
| `List.copyOf(source)` | Không | Không | Cung cấp list không sửa được, có thể tái sử dụng instance phù hợp |
| `Stream.of(...).toList()` trên Java 17 | Không | Không | Kết quả là list không sửa được |

**Chú ý:** “không sửa được qua một reference” khác “dữ liệu nền không thể bị thay đổi từ nơi khác”, và cả hai đều khác “đối tượng phần tử được giữ bên trong là bất biến”.

## 4. Arrays.asList: danh sách có kích thước cố định, không phải ArrayList thông thường

Phương thức `java.util.Arrays.asList(T... a)` trả một `List` có kích thước cố định **được hậu thuẫn bởi mảng**.

~~~java
String[] colors = {"red", "blue"};
List<String> list = Arrays.asList(colors);

list.set(0, "green");    // Được hỗ trợ.
list.add("gold");        // UnsupportedOperationException.
list.remove(0);         // UnsupportedOperationException.
~~~

Đây là đoạn minh họa cần import `Arrays` và `List`. Sau `set(0, "green")`, phần tử đầu của **mảng gốc** cũng trở thành `"green"` vì list và array liên kết qua cùng vùng chứa phần tử.

Điểm dễ sai:

- `Arrays.asList` **không trả về `java.util.ArrayList`**, dù tên gần giống.
- Phương thức `set` được hỗ trợ vì nó **thay thế** phần tử tại vị trí có sẵn, không đổi kích thước.
- `add/remove` theo cách thông thường sẽ đổi số phần tử nên không được hỗ trợ.
- Thay đổi phần tử trong array gốc có thể quan sát qua list, và thay đổi bằng `set` của list có thể quan sát qua array.
- Danh sách **fixed-size không đồng nghĩa immutable/unmodifiable**: việc thay thế phần tử vẫn được phép.
- Array vẫn có thể chứa `null`; danh sách thu được có thể chứa `null` nếu array tương ứng chứa null.

Một phương án nếu muốn thêm/xóa:

~~~java
List<String> editable = new ArrayList<>(Arrays.asList("red", "blue"));
editable.add("gold");  // Hợp lệ.
editable.remove("red"); // Hợp lệ.
~~~

Đây là đoạn minh họa, cần import `ArrayList`, `Arrays` và `List`. Constructor của ArrayList tạo **danh sách mới có thể đổi kích thước**. Nó sao chép **các tham chiếu phần tử**, không tự clone sâu các object bên trong.

### 4.1. Một bẫy khác: mảng primitive

~~~java
int[] numbers = {1, 2, 3};
List<int[]> list = Arrays.asList(numbers);
System.out.println(list.size()); // 1
~~~

Đây là một ví dụ Java hợp lệ với import phù hợp. Với một đối số `int[]`, danh sách thu được có một **phần tử kiểu int[]**, không phải `List<Integer>` gồm ba số. Đây là vấn đề generic/varargs riêng, không phải nguyên nhân trực tiếp gây UOE, nhưng thường gặp trong những đoạn code dùng `Arrays.asList` rồi cố thêm/xóa.

## 5. Collections.unmodifiableList: một view không cho sửa

Một wrapper không sửa được được tạo bằng:

~~~java
List<String> source = new ArrayList<>(List.of("one", "two"));
List<String> view = Collections.unmodifiableList(source);
~~~

Đoạn minh họa cần import `Collections`, `ArrayList`, `List`.

Với `view`:

~~~java
view.add("three");       // UnsupportedOperationException.
view.set(0, "changed");  // UnsupportedOperationException.
~~~

Tuy nhiên, wrapper **giữ liên hệ với list nền**:

~~~java
source.add("three");
System.out.println(view); // [one, two, three]
~~~

Khi nguồn thay đổi qua reference `source`, việc đọc `view` phản ánh thay đổi đó. Đây là **unmodifiable view**, không phải **snapshot bất biến của dữ liệu ở thời điểm tạo**.

**Hệ quả thiết kế:**

- Nếu một method trả về `Collections.unmodifiableList(internal)` nhưng vẫn giữ và sửa `internal`, caller có thể thấy dữ liệu thay đổi theo thời gian.
- Nếu muốn cung cấp kết quả **ổn định về cấu trúc** trước những thay đổi tiếp theo của danh sách nguồn, hãy cân nhắc một bản sao không sửa được như `List.copyOf(source)` (theo điều kiện dữ liệu và hợp đồng null phù hợp).
- Unmodifiable wrapper **không bảo vệ bạn** khỏi việc một thread khác sửa list nền không đồng bộ. Nó cũng không làm backing collection tự nhiên trở thành thread-safe.
- Nếu phần tử trong list là mutable object, caller vẫn có thể sửa **trạng thái bên trong phần tử** khi có reference tới chúng. Không sửa được **cấu trúc list** không có nghĩa deep immutability.

Không nên công khai một view dựa trên cấu trúc nội bộ mutable nếu cần tránh side effect khó đoán; hãy lựa chọn rõ giữa “live read-only view” và “detached snapshot”.

## 6. List.of và List.copyOf: cấu trúc danh sách không sửa được

Từ Java 9, `List.of(...)` tạo các danh sách không sửa được (*unmodifiable lists*).

~~~java
List<String> names = List.of("Lan", "Mai");
names.add("An");      // UnsupportedOperationException.
names.set(0, "Hoa");  // UnsupportedOperationException.
names.remove(0);      // UnsupportedOperationException.
~~~

Ở đây không chỉ thay đổi kích thước bị cấm; **thay thế phần tử** cũng bị cấm.

Đặc điểm quan trọng của `List.of`:

- Không cho thêm/xóa/thay thế phần tử qua các thao tác cập nhật.
- Không chấp nhận phần tử `null`; ví dụ `List.of("A", (String) null)` ném `NullPointerException` **trong lúc tạo**, không phải UOE do gọi add.
- Thứ tự các phần tử phản ánh thứ tự đối số khai báo; bạn có thể truy cập bằng `get(index)` khi index hợp lệ.
- Object chứa bên trong **vẫn có thể mutable**. Việc list không hỗ trợ `set` không ngăn thay đổi trạng thái của object phần tử nếu class phần tử cho phép.
- Không nên dùng đồng nhất đối tượng (`==`) hoặc khóa đồng bộ dựa trên danh sách từ factory mà không hiểu tính chất *value-based* của các instance từ nhóm factory này.

Từ Java 10, `List.copyOf(source)` tạo hoặc trả về một danh sách **không sửa được** chứa các phần tử của source tại thời điểm tạo về mặt cấu trúc:

~~~java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> snapshot = List.copyOf(source);
source.add("C");
System.out.println(snapshot); // [A, B]
~~~

Ví dụ này giả định source là một ArrayList mutable. Kết quả snapshot **không phản ánh lần thêm C vào source**. Nhưng:

- `List.copyOf` không phải thao tác **deep copy** phần tử.
- Nó **từ chối phần tử null** trong input; có thể ném NPE nếu collection chứa null.
- API được phép tái sử dụng một unmodifiable list phù hợp; không được giả định hai lần gọi luôn tạo hai instance khác nhau.
- Nếu phần tử là mutable object, đổi trạng thái object đó vẫn có thể thấy qua cả source và snapshot.

**Tóm tắt:** `Arrays.asList` = fixed-size backed by array; `Collections.unmodifiableList` = wrapper view; `List.of/List.copyOf` = danh sách không cho sửa cấu trúc với hợp đồng cụ thể. Chúng **không thể thay thế cho nhau một cách vô điều kiện**.

## 7. Map.of và các thao tác cập nhật tùy chọn

Không chỉ List mới có optional operations. `Map` cũng định nghĩa nhiều thao tác cập nhật:

~~~java
Map<String, Integer> quantities = Map.of("apple", 2);
quantities.put("banana", 3); // UnsupportedOperationException.
quantities.remove("apple");  // UnsupportedOperationException.
~~~

Đây là đoạn minh họa cần import `java.util.Map`.

Với `Map.of`, map không sửa được. Nếu cần cập nhật, hãy tạo mutable copy:

~~~java
Map<String, Integer> editable = new HashMap<>(Map.of("apple", 2));
editable.put("banana", 3); // Hợp lệ.
~~~

Cần import `HashMap` và `Map`. `Map.of` cũng không chấp nhận key hoặc value null; việc đưa null vào factory sẽ có thể ném NPE thay vì UOE.

**Đừng suy rộng:** `Map` có method `put` không chứng minh mọi instance Map hỗ trợ put. Một view không sửa được cũng có thể phát sinh thông qua `Collections.unmodifiableMap(source)`, với điểm khác biệt giữa view và snapshot tương tự List.

### 7.1. Cẩn trọng với view của keySet, values và entrySet

Một `Map` thường cung cấp các view như `keySet()`, `values()` và `entrySet()`. Khả năng xóa/sửa thông qua các view **phụ thuộc vào hợp đồng map nguồn**.

Một ví dụ:

~~~java
Map<String, Integer> mutable = new HashMap<>();
mutable.put("A", 1);
mutable.keySet().remove("A"); // Thao tác thường được hỗ trợ với HashMap.
~~~

Nhưng cùng tên method qua một view của map không sửa được có thể ném UOE. Không nên tự suy rằng “keySet là Set nên chắc chắn được add/remove”: API view có thể chặn hoặc cho phép từng thao tác.

Với entry từ những map khác nhau, `Map.Entry.setValue(...)` cũng có thể được hoặc không được hỗ trợ. Hãy đọc Javadoc của implementation.

## 8. Iterator.remove và ListIterator: thao tác tùy chọn

`Iterator<E>` cung cấp một method `remove()` để loại bỏ phần tử cuối cùng được trả bởi `next()`, **nếu iterator hỗ trợ**.

Ví dụ với ArrayList:

~~~java
List<String> words = new ArrayList<>(List.of("first", "second"));
Iterator<String> iterator = words.iterator();

iterator.next();
iterator.remove(); // Được hỗ trợ đối với iterator ArrayList.
System.out.println(words); // [second]
~~~

Đoạn này yêu cầu import `ArrayList`, `Iterator`, `List`. Nhưng:

~~~java
Iterator<String> iterator = List.of("first").iterator();
iterator.next();
iterator.remove(); // UnsupportedOperationException.
~~~

Một iterator của danh sách không sửa được không thể dùng để xóa phần tử cấu trúc.

**Phân biệt với IllegalStateException:** Ngay cả iterator **có hỗ trợ remove**, việc gọi `remove()` trước `next()` hoặc gọi `remove()` lặp lại mà không có `next()` mới có thể ném `IllegalStateException` theo hợp đồng của Iterator. Còn UOE thể hiện **bản thân thao tác remove không được hỗ trợ**. Hai lỗi có nguyên nhân khác nhau.

`ListIterator` bổ sung `add` và `set` ngoài `remove`, nhưng các thao tác cập nhật ấy cũng có thể tùy chọn. Dùng `ListIterator` của một danh sách không sửa được không biến nó thành editable.

### 8.1. Đừng nhầm fail-fast iterator với unsupported operation

Một iterator của một collection mutable có thể phát hiện rằng collection bị sửa cấu trúc từ bên ngoài trong lúc lặp và ném `ConcurrentModificationException` theo chính sách implementation. Đó **không phải** cùng điều kiện với `UnsupportedOperationException`.

- UOE: thao tác iterator được yêu cầu không được hỗ trợ.
- `IllegalStateException`: gọi thao tác ở trạng thái không hợp lệ theo giao thức Iterator.
- `ConcurrentModificationException`: implementation phát hiện tình huống sửa cấu trúc không đúng quy tắc trong quá trình lặp.

Không nên dựa vào fail-fast detection như một cơ chế đồng bộ thread. Đây là chủ đề khác với UOE nhưng thường bị nhầm khi code sửa collection trong vòng lặp.

## 9. Stream.toList và Collectors.toList không có cùng cam kết mutability

Từ Java 16, `Stream.toList()` trả một List **không sửa được**:

~~~java
List<String> items = Stream.of("A", "B").toList();
items.add("C"); // UnsupportedOperationException.
~~~

Ví dụ cần import `java.util.stream.Stream` và `java.util.List`. Trong Java 17, hành vi này là hợp đồng rõ ràng của `Stream.toList()`.

Ngược lại, với:

~~~java
List<String> items = stream.collect(Collectors.toList());
~~~

đây là đoạn minh họa cần biến `stream` và import `Collectors`. Javadoc của `Collectors.toList()` **không bảo đảm** kiểu implementation, mutability, serializability hay thread safety của list thu được. Vì vậy không nên biến hành vi tình cờ hiện tại thành một contract lâu dài.

Nếu yêu cầu kết quả **chắc chắn là ArrayList mutable**, có thể sử dụng:

~~~java
List<String> editable =
        Stream.of("A", "B").collect(Collectors.toCollection(ArrayList::new));
editable.add("C");
~~~

Cần import `ArrayList`, `List`, `Collectors`, `Stream`. Tại đây bạn chủ động chọn collection supplier, thay vì phỏng đoán từ tên collector.

**Mẹo:** Đọc kỹ Javadoc của factory/collector để phân biệt “unmodifiable theo đặc tả” với “đang modifiable trên một bản JDK cụ thể”.

## 10. Chương trình Java 17 hoàn chỉnh, kiểm chứng stdout

Tạo tệp **`OptionalOperationsDemo.java`**. Chương trình chạy thử nhiều API khác nhau. Các lời gọi dự kiến ném UOE được đặt trong helper `attempt` để tiếp tục minh họa những ca sau; **đây là kỹ thuật kiểm chứng trong bài học, không phải khuyến nghị bắt UOE rồi bỏ qua trong ứng dụng sản xuất**.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public class OptionalOperationsDemo {
    private static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=supported");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        System.out.println("== fixed-size list backed by array ==");
        String[] words = {"red", "blue"};
        List<String> fixed = Arrays.asList(words);
        fixed.set(0, "green");
        System.out.println("fixed=" + fixed);
        System.out.println("array=" + Arrays.toString(words));
        attempt("fixed.add", () -> fixed.add("gold"));
        attempt("fixed.remove", () -> fixed.remove(0));
        System.out.println("fixed-after=" + fixed);

        System.out.println("== unmodifiable view ==");
        List<String> source = new ArrayList<>(List.of("one", "two"));
        List<String> view = Collections.unmodifiableList(source);
        System.out.println("view-before=" + view);
        attempt("view.add", () -> view.add("four"));
        attempt("view.set", () -> view.set(0, "changed"));
        source.add("three");
        System.out.println("view-after-source-change=" + view);

        System.out.println("== unmodifiable factories ==");
        List<String> immutable = List.of("a", "b");
        attempt("List.of.add", () -> immutable.add("c"));
        attempt("List.of.set", () -> immutable.set(0, "c"));
        List<String> copied = List.copyOf(source);
        attempt("List.copyOf.clear", copied::clear);
        List<String> streamList = Stream.of("x", "y").toList();
        attempt("Stream.toList.add", () -> streamList.add("z"));
        Map<String, Integer> map = Map.of("key", 1);
        attempt("Map.of.put", () -> map.put("other", 2));

        System.out.println("== iterator capabilities ==");
        List<String> editable = new ArrayList<>(List.of("first", "second"));
        Iterator<String> it = editable.iterator();
        it.next();
        it.remove();
        System.out.println("editable-after-remove=" + editable);
        Iterator<String> readOnlyIt = List.of("first").iterator();
        readOnlyIt.next();
        attempt("List.of.iterator.remove", readOnlyIt::remove);

        System.out.println("== explicitly mutable copy ==");
        List<String> mutableCopy = new ArrayList<>(immutable);
        mutableCopy.add("c");
        System.out.println("mutable-copy=" + mutableCopy);
        System.out.println("original=" + immutable);

        System.out.println("== null contract ==");
        System.out.println("Arrays.asList-null=" + Arrays.asList("ok", null));
        try {
            List.of("ok", (String) null);
        } catch (NullPointerException ex) {
            System.out.println("List.of-null=NullPointerException");
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 OptionalOperationsDemo.java
java OptionalOperationsDemo
~~~

**Stdout chính xác được kiểm chứng bằng việc biên dịch và chạy:**

~~~text
== fixed-size list backed by array ==
fixed=[green, blue]
array=[green, blue]
fixed.add=UnsupportedOperationException
fixed.remove=UnsupportedOperationException
fixed-after=[green, blue]
== unmodifiable view ==
view-before=[one, two]
view.add=UnsupportedOperationException
view.set=UnsupportedOperationException
view-after-source-change=[one, two, three]
== unmodifiable factories ==
List.of.add=UnsupportedOperationException
List.of.set=UnsupportedOperationException
List.copyOf.clear=UnsupportedOperationException
Stream.toList.add=UnsupportedOperationException
Map.of.put=UnsupportedOperationException
== iterator capabilities ==
editable-after-remove=[second]
List.of.iterator.remove=UnsupportedOperationException
== explicitly mutable copy ==
mutable-copy=[a, b, c]
original=[a, b]
== null contract ==
Arrays.asList-null=[ok, null]
List.of-null=NullPointerException
~~~

Đầu ra cố ý in **tên class exception**, không dựa trên `getMessage()` của UOE (có thể không có message hoặc khác giữa implementation). Mã không cần file, mạng hoặc dependency bên ngoài; tương thích mức nguồn Java 17. Các thao tác dự kiến lỗi đã được bắt trong helper, không làm tiến trình dừng giữa chừng.

### 10.1. Diễn giải nhóm fixed-size list

- `fixed.set(0,"green")` thực thi thành công, thay phần tử trong list và **array nền**. Vì vậy hai dòng `fixed` và `array` đều là `[green, blue]`.
- `fixed.add("gold")` không được hỗ trợ do sẽ đổi kích thước.
- `fixed.remove(0)` không được hỗ trợ vì xóa phần tử làm thay đổi kích thước.
- Sau hai exception, nội dung list vẫn là `[green, blue]` trong ví dụ. Không có phần tử nào được thêm hoặc xóa.

**Chú ý:** Nếu một implementation khác ném UOE khi bạn cố dùng `set`, không có mâu thuẫn: `set` bản thân là một optional operation của List; việc `Arrays.asList` hỗ trợ set là hợp đồng riêng của danh sách đó.

### 10.2. Diễn giải view không sửa được

`Collections.unmodifiableList(source)` không cho `view.add` và `view.set`. Nhưng một reference khác là `source` vẫn có thể thêm phần tử `"three"`, nên view đọc được `[one, two, three]`.

Điều này chứng minh:

- **Cấm sửa qua view** không có nghĩa cấm mọi reference khác sửa đối tượng backing.
- Một API có thể trả read-only view để ngăn caller chủ động mutate collection qua reference đó, nhưng không tự tạo snapshot.
- Nếu cần tách cấu trúc khỏi nguồn, cân nhắc tạo snapshot theo hợp đồng cụ thể.

### 10.3. Diễn giải factories và stream

`List.of`, `List.copyOf`, `Stream.toList()` và `Map.of` đều tạo giá trị mà **các thao tác cập nhật được thử nghiệm không được hỗ trợ**. Chương trình in UOE cho `add`, `set`, `clear` hoặc `put` tương ứng.

Đừng coi đây là bằng chứng rằng mọi API `List` hoặc `Map` đều immutable. **Chính nguồn tạo và hợp đồng object** mới quyết định thao tác nào được hỗ trợ.

### 10.4. Diễn giải iterator

Iterator của `ArrayList` cho phép `remove` sau `next`. Iterator của `List.of` không cho thay đổi danh sách, nên `remove` ném UOE. Một reference được khai báo kiểu `Iterator<String>` không tự xác định khả năng remove.

### 10.5. Diễn giải mutable copy và null

`new ArrayList<>(immutable)` tạo list mới cho phép thêm phần tử, trong khi list gốc `immutable` giữ nguyên. `Arrays.asList("ok", null)` có thể chứa null, còn `List.of("ok", (String)null)` ném **NPE tại factory** vì không chấp nhận null.

Đây là hai loại lỗi khác nhau: **UOE** khi yêu cầu một thao tác cập nhật không hỗ trợ; **NPE** khi đầu vào null bị cấm. Đừng bắt UOE để xử lý dữ liệu null, hoặc ngược lại.

## 11. Optional không có nghĩa mọi lần gọi đều bắt buộc ném

Một điểm tinh tế trong Collections Framework: với các thao tác tùy chọn, hành vi **khi thao tác không có tác dụng thực sự** có thể phụ thuộc vào hợp đồng implementation.

Ví dụ có thể thử:

~~~java
Collection<String> items = Collections.unmodifiableCollection(source);
items.addAll(Collections.emptyList());
~~~

Đây là đoạn minh họa cần import `Collection`, `Collections` và biến `source` tương thích. Vì tập thêm là rỗng, nếu thao tác có xảy ra thì kích thước không đổi. **Không được suy một cách phổ quát** rằng trường hợp này luôn thành công hoặc luôn ném UOE đối với mọi Collection implementation.

Theo hợp đồng tổng quát của Collection, một số optional operations **có thể** ném exception ngay cả khi lần gọi không gây thay đổi. Implementation khác có thể chọn trả một kết quả như false khi không có phần tử nào được thêm.

Hậu quả thực tế:

- Không viết business logic dựa trên mẹo “thử `addAll(empty)` để biết Collection có editable không”.
- Không đoán mutability từ một lần gọi không làm thay đổi cấu trúc.
- Đừng cố **dò khả năng cập nhật bằng cách mutate thử đối tượng đang được chia sẻ**: phép thử có thể gây side effect nếu được hỗ trợ.
- Hãy đọc **Javadoc và hợp đồng API** của đối tượng được cung cấp, hoặc chủ động tạo một copy mutable theo yêu cầu.

Tương tự, `removeIf(predicate)` có thể trả về false khi không có phần tử thỏa điều kiện ở một implementation, nhưng thao tác cập nhật không được hỗ trợ ở implementation khác. Kết quả phụ thuộc vào chính sách của class và cách cài đặt method; không sử dụng sự kiện “không có phần tử bị xóa” như bằng chứng quyền sửa collection.

## 12. Không nên dùng catch UnsupportedOperationException làm cơ chế lựa chọn chính

Một anti-pattern:

~~~java
try {
    list.add(value);
} catch (UnsupportedOperationException ex) {
    // Bỏ qua để báo hoàn thành.
}
~~~

Đây là đoạn minh họa có biến `list` và `value` đã định nghĩa. Nếu ứng dụng cần **thực sự thêm phần tử** nhưng lỗi bị bỏ qua, chương trình có thể báo thành công sai và mất dữ liệu.

Tốt hơn, chọn chiến lược theo hợp đồng:

**Nếu caller bắt buộc truyền một list mutable:**

~~~java
static void appendRequired(List<String> destination, String value) {
    destination.add(value);
}
~~~

Phải ghi rõ trong tài liệu rằng `destination` cần hỗ trợ `add`, và để lỗi lan nếu caller vi phạm hợp đồng. Không cần bắt UOE rồi trả trạng thái giả.

**Nếu method nhận bất kỳ list nào và luôn cần kết quả mới:**

~~~java
static List<String> appendCopy(List<String> input, String value) {
    List<String> result = new ArrayList<>(input);
    result.add(value);
    return result;
}
~~~

Đây là các phương thức minh họa cần import `List` và `ArrayList`. Method thứ hai tạo mutable copy nên **không cần thay đổi input**. Nếu hợp đồng muốn kết quả không sửa được, có thể trả `List.copyOf(result)` khi phần tử khác null và điều kiện API phù hợp.

**Nếu tình huống “tác vụ không được hỗ trợ” là một đường hợp lệ của framework:** có thể xử lý UOE ở một **boundary được tài liệu hóa rõ**, ví dụ chuyển sang thông báo “tính năng này không được hỗ trợ”. Nhưng không nên dùng UOE như một kiểm tra quyền thao tác chung cho mọi collection, đặc biệt khi nó có thể che bug hoặc nhầm với lỗi truy cập nghiệp vụ.

## 13. Thiết kế API có chủ đích về mutability

### 13.1. Đọc dữ liệu và sửa dữ liệu là hai hợp đồng khác nhau

Một method chỉ **đọc** danh sách:

~~~java
static long countNonBlank(List<String> items) {
    return items.stream()
            .filter(s -> s != null && !s.isBlank())
            .count();
}
~~~

Đây là một method minh họa hợp lệ, cần import `List`. Nó không cần khả năng `add/remove/set`. Caller có thể truyền `ArrayList`, `Arrays.asList` hoặc unmodifiable List có dữ liệu phù hợp.

Ngược lại:

~~~java
static void addDefault(List<String> items) {
    items.add("default");
}
~~~

method này **đòi danh sách hỗ trợ add**. Kiểu `List<String>` một mình không biểu diễn được cam kết đó ở mức compile time. Viết JavaDoc, dùng type riêng khi cần một contract mạnh hơn hoặc trả một copy mới.

### 13.2. Snapshot và defensive copy

Nếu muốn trả kết quả cho caller **không thể sửa cấu trúc** và không chịu thay đổi từ source list mutable:

~~~java
List<String> result = List.copyOf(source);
return result;
~~~

Đây là đoạn minh họa trong method thích hợp, cần import `List`. `List.copyOf` từ chối null elements, vì vậy phải kiểm tra hợp đồng dữ liệu trước.

Nếu dữ liệu nguồn có thể chứa null và vẫn muốn một bản sao không cho sửa, một cách khác là:

~~~java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<>(source));
~~~

Đoạn này tạo ArrayList mới, rồi tạo view không sửa được của **bản sao mới đó**; nếu code không giữ một mutable alias và không cho phép thay đổi phần tử bên trong theo cách không mong muốn, cấu trúc list giữ ổn định hơn so với wrapper trực tiếp quanh source. Nhưng bản sao vẫn **shallow**: phần tử mutable có thể đổi trạng thái.

### 13.3. Tránh tuyên bố “immutable” khi chỉ unmodifiable

Từ “immutable” có thể được hiểu là **toàn bộ trạng thái quan sát được không thay đổi**, nhưng unmodifiable list chỉ có hợp đồng rằng các thao tác cập nhật thông qua API list không được hỗ trợ. Nếu phần tử là `StringBuilder` hoặc object có setter, người giữ tham chiếu vẫn có thể thay đổi chúng.

Một **deeply immutable model** cần thiết kế cả object graph, không chỉ bọc một list. UOE giúp ngăn sửa list qua một reference, **không tự triển khai immutable object graph**.

## 14. Khi nào nên tự ném UnsupportedOperationException?

Một class triển khai interface có optional operation có thể ném UOE để công khai **không hỗ trợ thao tác ấy**:

~~~java
class ReadOnlyIntStore {
    private final List<Integer> values = List.of(1, 2, 3);

    int size() {
        return values.size();
    }

    void add(int value) {
        throw new UnsupportedOperationException("store is read-only");
    }
}
~~~

Đây là định nghĩa class minh họa, cần import `List`. Một API thiết kế rõ ràng có thể **không định nghĩa method add** ngay từ đầu nếu thao tác đó không thuộc năng lực của class. Nhưng khi một method xuất hiện do interface/abstract class có optional operation hoặc yêu cầu tương thích API, ném UOE có thể phù hợp.

**Không nên lạm dụng UOE:**

- Đừng dùng UOE thay cho `IllegalArgumentException` khi tham số sai, nếu thao tác vẫn được hỗ trợ với giá trị khác.
- Đừng dùng UOE thay cho `IllegalStateException` khi thao tác **có được hỗ trợ** nhưng object đang ở trạng thái tạm thời không phù hợp.
- Đừng dùng UOE cho lỗi phân quyền chỉ vì người dùng không được phép thao tác: API nghiệp vụ có thể cần một exception/response rõ về quyền truy cập.
- Đừng dùng UOE cho “chưa code xong” trong production một cách mơ hồ nếu hợp đồng đã hứa method phải hoạt động; cần làm đúng tính năng hoặc thay đổi hợp đồng.

Phân biệt khái niệm:

| Điều kiện | Exception thường phù hợp hơn |
| --- | --- |
| Thao tác không nằm trong năng lực được hỗ trợ bởi đối tượng/API | `UnsupportedOperationException` |
| Tham số không hợp lệ cho một thao tác vốn được hỗ trợ | `IllegalArgumentException`, NPE hoặc type phù hợp với contract |
| Đối tượng đang ở trạng thái không thể thực hiện thao tác vốn có | `IllegalStateException` |
| Chỉ số ngoài giới hạn list/array hợp lệ | `IndexOutOfBoundsException` hoặc subtype tương ứng |
| Iterator.remove không được triển khai hỗ trợ | `UnsupportedOperationException` |
| Iterator.remove được hỗ trợ nhưng gọi sai trình tự | `IllegalStateException` |

Điều kiện và exception cụ thể cuối cùng phải theo **Javadoc của API đang sử dụng**, không chỉ theo heuristic chung trong bảng.

## 15. AbstractCollection, AbstractList và các triển khai mặc định

Một số abstract base class trong Collections Framework cung cấp implementation mặc định cho optional operations. Ví dụ `AbstractCollection.add(E)` mặc định ném UOE, trừ khi subclass override với hành vi hỗ trợ thêm.

Một subclass có thể triển khai đủ các method truy vấn nhưng **không cung cấp một cách cập nhật tương ứng**, dẫn tới UOE khi caller gọi một optional operation. `AbstractList` cũng cung cấp những implementation mặc định có thể không hỗ trợ thao tác thêm/xóa/thay thế nếu subclass không triển khai.

Điều đó giải thích vì sao “implements List” **không tự đồng nghĩa** “sửa được như ArrayList”. Các lớp trợ giúp abstract giảm công viết code, nhưng chính subclass và contract quyết định khả năng mutation.

Khi tự viết collection:

1. Đọc kỹ contract của các method truy vấn và cập nhật.
2. Đừng ghi rằng collection editable trong JavaDoc nếu chỉ hỗ trợ `get` và `size`.
3. Nếu hỗ trợ một optional operation, triển khai cả các bất biến và lỗi cần thiết của nó.
4. Kiểm tra behavior của iterator: `remove`, `set`, `add` không nhất thiết xuất hiện đồng loạt.
5. Test các trường hợp cập nhật thành công, không hỗ trợ và sai trạng thái theo đúng contract.

## 16. Debug một UnsupportedOperationException thực tế

Khi thấy stack trace chứa:

~~~text
java.lang.UnsupportedOperationException
    at ...
    at com.example.Service.updateItems(Service.java:42)
~~~

đây là ví dụ **định dạng minh họa**, không phải stack trace cố định. Hãy làm theo các bước:

1. **Tìm method đầu tiên của code bạn** trên stack trace, ví dụ `updateItems` gọi `add` hoặc `remove`.
2. **Xác định đối tượng runtime thực sự**: nó được tạo bằng `new ArrayList`, `Arrays.asList`, `List.of`, `List.copyOf`, `Collections.unmodifiableList` hay lấy từ thư viện nào?
3. **Xem đúng operation**: thay thế (`set`) hay thay đổi kích thước (`add/remove`), hay thao tác qua iterator?
4. **Đọc Javadoc implementation** để xác định optional operation có hỗ trợ hay không.
5. **Tìm nơi tạo hoặc truyền collection**; đừng chỉ sửa đoạn method call nếu input contract là nguyên nhân.
6. **Xác định có yêu cầu mutation thật không**. Nếu không, tránh mutate; nếu có, quyết định tạo copy hay yêu cầu caller cung cấp mutable collection.
7. **Kiểm thử với nhiều implementation** phù hợp hợp đồng API, không chỉ ArrayList.
8. **Kiểm tra aliasing và threading** nếu dùng unmodifiable view có backing collection thay đổi ở nơi khác.

Nếu chỉ gọi `list.get(0)` và nhận UOE thì đó là hành vi bất thường đối với List chuẩn ở thao tác truy vấn này; cần đọc implementation thực sự và stack trace chứ không mặc định mọi UOE đều do `add`.

**Không dùng nội dung message của UOE làm logic:** một số implementation có thể ném UOE không có message, hoặc message khác giữa phiên bản. Dựa trên API contract và loại exception có ý nghĩa hơn việc parse message.

## 17. Những hiểu nhầm và lỗi phổ biến

1. **“Nếu implements List thì add luôn hoạt động.”** Sai: add là optional operation.
2. **“`Arrays.asList` trả ArrayList mutable bình thường.”** Sai: fixed-size list backed by array.
3. **“`Arrays.asList` không đổi kích thước thì mọi sửa đổi đều bị cấm.”** Sai: `set` được hỗ trợ.
4. **“UnmodifiableList là snapshot.”** Không nhất thiết: `Collections.unmodifiableList` trả một view phản ánh thay đổi source.
5. **“`List.of` chỉ cấm add, còn set được.”** Sai: set cũng ném UOE.
6. **“`List.copyOf` luôn tạo object list mới.”** Sai: API có thể tái sử dụng instance unmodifiable thích hợp.
7. **“Unmodifiable list đồng nghĩa phần tử hoàn toàn bất biến.”** Sai: mutable element có thể đổi trạng thái.
8. **“Unmodifiable view đồng nghĩa thread-safe.”** Sai: backing collection vẫn có thể bị sửa không đồng bộ.
9. **“`Stream.toList()` của Java 17 trả ArrayList editable.”** Sai: kết quả không sửa được.
10. **“`Collectors.toList()` bảo đảm editable.”** Javadoc không bảo đảm điều đó.
11. **“`getOrDefault`, `addAll(empty)` hay `removeIf` luôn kiểm tra được mutability.”** Sai: behavior có thể phụ thuộc implementation và trạng thái.
12. **“Iterator nào cũng cho remove.”** Sai: `Iterator.remove` là optional operation.
13. **“Iterator.remove ném IllegalStateException tức thao tác không được hỗ trợ.”** Không nhất thiết: có thể do gọi sai trình tự.
14. **“NPE khi `List.of(null)` cũng là UnsupportedOperationException.”** Sai: loại lỗi khác vì factory từ chối null.
15. **“Bắt UOE rồi bỏ qua luôn an toàn.”** Sai: dễ làm mất dữ liệu và báo thành công giả.
16. **“Có thể xác định mutability của mọi List bằng `instanceof List`.”** Sai: kiểu chung không mô tả toàn bộ khả năng cập nhật.
17. **“Tạo `new ArrayList<>(source)` sẽ deep-copy toàn bộ object.”** Sai: chỉ copy cấu trúc và tham chiếu phần tử.
18. **“Map có put thì mọi map đều cho put.”** Sai: `Map.of` và unmodifiable wrappers chặn mutation.
19. **“UOE luôn là lỗi do lập trình viên chưa code method.”** Sai: nhiều optional operations cố ý không được hỗ trợ theo thiết kế.
20. **“Không có thay đổi thực tế thì method trên unmodifiable collection nhất định thành công.”** Sai: có optional operation vẫn có thể ném UOE.
21. **“UOE là checked exception.”** Sai: `UnsupportedOperationException extends RuntimeException`.
22. **“`Collections.unmodifiableList` bảo vệ nguồn khỏi mọi reference khác.”** Sai: mutable alias vẫn có thể sửa source.

## 18. Bài tập tự kiểm tra

**Câu 1.** Đoạn sau có in `[B, A]` không?

~~~java
String[] a = {"A", "B"};
List<String> l = Arrays.asList(a);
l.set(0, "B");
System.out.println(Arrays.toString(a));
~~~

*Đáp án:* In `[B, B]`. Thao tác set thay vị trí 0 của mảng nền; vị trí 1 giữ `"B"`.

**Câu 2.** `Arrays.asList("A", "B").add("C")` gặp lỗi gì?

*Đáp án:* `UnsupportedOperationException` vì danh sách có kích thước cố định, không hỗ trợ thêm phần tử.

**Câu 3.** Vì sao `Collections.unmodifiableList(source)` có thể thay đổi dữ liệu quan sát được dù caller không được gọi add qua wrapper?

*Đáp án:* Nó là **view** của source. Một reference khác vẫn có thể mutate source, khiến view phản ánh thay đổi.

**Câu 4.** `List.of("A").set(0, "B")` có hợp lệ không?

*Đáp án:* Gọi được về mặt cú pháp nhưng ném UOE ở runtime, vì list không cho thay thế phần tử.

**Câu 5.** Muốn thêm phần tử vào kết quả `Stream.toList()` trên Java 17, cách nào rõ ràng?

*Đáp án:* Tạo mutable copy: `new ArrayList<>(stream.toList())` rồi thêm phần tử, hoặc dùng `Collectors.toCollection(ArrayList::new)` ngay từ đầu.

**Câu 6.** `List.copyOf(source)` có luôn tạo shallow-independent structure khỏi ArrayList nguồn không?

*Đáp án:* Với source là ArrayList mutable, list thu được không bị ảnh hưởng về cấu trúc bởi lần add/remove sau trên source. Nhưng API có thể tái sử dụng một input đã là unmodifiable phù hợp, và phần tử mutable vẫn có thể thay đổi trạng thái.

**Câu 7.** Vì sao `List.of("A", (String)null)` không ném UOE mà ném NPE?

*Đáp án:* Lỗi xảy ra **khi tạo danh sách** vì List.of cấm phần tử null, chưa phải một lời gọi thao tác cập nhật không được hỗ trợ.

**Câu 8.** Với iterator ArrayList, `remove()` ngay khi chưa gọi `next()` báo loại gì?

*Đáp án:* `IllegalStateException` theo quy tắc giao thức Iterator, khác với UOE khi iterator không hỗ trợ remove.

**Câu 9.** Vì sao không nên “thử `addAll(Collections.emptyList())`” để xác định xem một collection có thể sửa không?

*Đáp án:* Với optional operations không có tác dụng thực tế, hợp đồng có thể cho phép các implementation phản ứng khác nhau; phép thử không chắc chắn xác định năng lực mutation.

**Câu 10.** `Map.of("A", 1).put("B", 2)` ném lỗi gì?

*Đáp án:* `UnsupportedOperationException` vì map không sửa được.

**Câu 11.** Nếu method nhận `List<String>` mà phải append, điều gì cần công bố?

*Đáp án:* Cần tài liệu hóa rằng tham số phải hỗ trợ add, hoặc thiết kế method tạo/trả mutable copy để không phụ thuộc khả năng sửa input.

**Câu 12.** Có thể dùng `UnsupportedOperationException` cho “dữ liệu người dùng không hợp lệ” không?

*Đáp án:* Không nên nếu operation bản thân có được hỗ trợ; loại lỗi tham số hoặc validation phù hợp hơn.

## 19. Tài liệu tham khảo chính thức Java 17

- [API UnsupportedOperationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedOperationException.html): class unchecked biểu thị thao tác được yêu cầu không được hỗ trợ.
- [API Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): optional operations và hành vi của chúng.
- [API List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): các method cập nhật, `List.of`, `List.copyOf` và unmodifiable lists.
- [API Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by array.
- [API Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view trên list nguồn.
- [API Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): `remove()` tùy chọn và trạng thái iterator.
- [API ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html): các thao tác cập nhật của iterator hai chiều.
- [API Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `put/remove` và các unmodifiable map factories.
- [API Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): kết quả List không sửa được.
- [API Collectors.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): không bảo đảm mutability của list.
- [API AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html): các implementation mặc định của optional operations.
- [API AbstractList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractList.html): hỗ trợ tạo List với các khả năng cập nhật khác nhau.

**Ghi nhớ:** `UnsupportedOperationException` là unchecked exception thường xuất hiện khi gọi một **optional operation** mà đối tượng không hỗ trợ. Đừng đánh đồng `List` với `ArrayList`, fixed-size với unmodifiable, view với snapshot, hoặc unmodifiable với deep immutable. Để tránh UOE một cách đúng đắn, hãy **xác định contract mutability từ nơi tạo dữ liệu và từ API**, và nếu cần sửa cấu trúc, tạo một mutable copy phù hợp thay vì thử-catch lỗi rồi bỏ qua.