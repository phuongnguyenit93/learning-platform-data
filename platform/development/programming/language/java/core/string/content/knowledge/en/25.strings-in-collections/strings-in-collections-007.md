# Phân biệt String[] và List<String> khi chuyển đổi dữ liệu trong Java

## 1. Vì sao cần phân biệt?

Trong Java, **String[]** (mảng String) và **List<String>** (danh sách String) đều lưu một chuỗi các phần tử có thứ tự và truy cập bằng chỉ số bắt đầu từ 0. Tuy nhiên, **chúng không có cùng cơ chế lưu trữ, kích thước hay quyền thay đổi nội dung**.

Khi chuyển đổi dữ liệu, điều quan trọng không chỉ là “đọc được các String” mà còn là:

- Danh sách có **dùng chung mảng ban đầu** hay tạo cấu trúc độc lập?
- Có thể **thêm/xóa phần tử** hay chỉ thay thế phần tử hiện có?
- Có thể **thay đổi phần tử** qua danh sách hay không?
- Dữ liệu có được **sao chép tại thời điểm chuyển đổi** hay tiếp tục phản ánh thay đổi bên nguồn?
- Có cho phép **null** không? Kiểu trả về thực sự của phương thức chuyển đổi là gì?

Hiểu những điều này giúp tránh lỗi **UnsupportedOperationException**, **ClassCastException**, **ArrayStoreException** và lỗi dữ liệu thay đổi ngoài ý muốn.

Bài sử dụng **Java 17+**, chủ yếu các API chuẩn trong **java.util.Arrays**, **java.util.ArrayList**, **java.util.List** và **java.util.stream**.

## 2. So sánh cấu trúc cơ bản

| Tiêu chí | **String[]** | **List<String>** |
| --- | --- | --- |
| Kiểu | Mảng Java với phần tử kiểu String | Interface collection có phần tử kiểu String |
| Độ dài | Cố định khi tạo mảng; dùng **length** | Dùng **size()**; khả năng tăng/giảm phụ thuộc implementation |
| Truy cập | **arr[i]** | **list.get(i)** |
| Gán phần tử | **arr[i] = value** | **list.set(i, value)** nếu implementation hỗ trợ |
| Thêm/xóa | Không thể thay đổi số phần tử của chính mảng | Có thể được hỗ trợ, ví dụ **ArrayList** |
| Có chứa null? | Có | Tùy danh sách: **ArrayList** cho phép, **List.of** không cho phép |
| In nội dung | **Arrays.toString(arr)** | Thường dùng **list.toString()** |
| Duyệt | **for**, **Arrays.stream(arr)** | **for**, **list.stream()** |
| Vấn đề thường gặp | Kích thước cố định, hiệp biến mảng | Quyền sửa phụ thuộc cách tạo List |

**Không phải mọi List đều có thể thêm/xóa.** **List** là interface; bản thân kiểu **List<String>** không bảo đảm được gọi **add()**, **remove()** hoặc **set()** thành công. Quyền sửa phụ thuộc đối tượng cụ thể:

- **ArrayList**: có thể thay đổi kích thước và thay phần tử.
- **Arrays.asList(array)**: thay phần tử được, nhưng **không** thêm/xóa làm đổi kích thước.
- **List.of(...)** và **List.copyOf(...)**: danh sách **unmodifiable**, không cho sửa cấu trúc hoặc gán phần tử bằng các phương thức thay đổi List.

Các danh sách này vẫn cùng có kiểu tham chiếu **List<String>**, nên cần biết cách chúng được tạo.

## 3. Chuyển String[] thành List<String> bằng Arrays.asList()

Đây là cách thông dụng khi muốn dùng các thao tác theo giao diện **List** trên dữ liệu mảng sẵn có:

~~~java
import java.util.Arrays;
import java.util.List;

String[] names = {"An", "Binh", "Chi"};
List<String> list = Arrays.asList(names);
~~~

**Arrays.asList(names)** trả về danh sách kích thước cố định, **được hỗ trợ bởi chính mảng names** (*backed by the array*).

Điều đó dẫn tới ba quy tắc quan trọng.

### 3.1. Có thể thay phần tử, và việc thay đổi phản ánh hai chiều

~~~java
String[] names = {"An", "Binh"};
List<String> list = Arrays.asList(names);

list.set(0, "Chi");
System.out.println(Arrays.toString(names)); // [Chi, Binh]

names[1] = "Dung";
System.out.println(list);                    // [Chi, Dung]
~~~

Thay phần tử qua **list.set(...)** làm thay giá trị tại vị trí tương ứng của mảng. Thay phần tử qua **names[index]** cũng được phản ánh khi đọc từ List.

**String bất biến** không làm điều này biến mất: ta không sửa nội dung đối tượng String; ta đổi **tham chiếu đến phần tử String** tại một vị trí.

### 3.2. Không thể thêm hoặc xóa để đổi kích thước

~~~java
String[] names = {"An", "Binh"};
List<String> list = Arrays.asList(names);

// list.add("Chi");       // UnsupportedOperationException nếu thực thi
// list.remove(0);        // UnsupportedOperationException nếu thực thi
list.set(1, "Chi");       // Hợp lệ: thay giá trị ở chỉ số sẵn có
~~~

Lý do là mảng ban đầu có độ dài cố định; List do **Arrays.asList** trả về không hỗ trợ thao tác làm thay đổi số lượng phần tử.

Một số tên phương thức như **sort()** hoặc **replaceAll()** có thể thực hiện vì chúng cập nhật phần tử trong kích thước hiện có; ngược lại, **clear()** hoặc **add()** sẽ thất bại. Không suy ra rằng chỉ vì có interface List thì mọi thao tác của List đều được hỗ trợ.

### 3.3. Đây là một dạng view, không phải bản sao tách biệt

**Arrays.asList** không sao chép mảng để tạo dữ liệu độc lập. Nếu code khác còn giữ biến **names** thì nó có thể ảnh hưởng đến danh sách.

Nếu chỉ cần truyền nhanh một mảng cho API nhận **List<String>**, cách này tiện. Nếu muốn danh sách có thể tăng/giảm hoặc muốn tách việc thay đổi phần tử khỏi mảng, hãy tạo **ArrayList** mới.

## 4. Chuyển String[] thành ArrayList có thể thay đổi kích thước

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

String[] names = {"An", "Binh"};

List<String> editable = new ArrayList<>(Arrays.asList(names));
editable.add("Chi");
editable.remove("An");
editable.set(0, "Dung");

System.out.println(editable);              // [Dung, Chi]
System.out.println(Arrays.toString(names)); // [An, Binh]
~~~

**new ArrayList<>(...)** tạo cấu trúc danh sách độc lập với mảng ban đầu:

- Có thể gọi **add**, **remove**, **clear**, **set** theo khả năng của ArrayList.
- Gán phần tử hoặc thay đổi kích thước trong danh sách không đổi các vị trí của mảng nguồn.
- Gán phần tử mới vào mảng nguồn không đổi các vị trí trong danh sách đã tạo.

Đây là **bản sao nông (shallow copy)**: phần tử được sao chép dưới dạng tham chiếu. Với **String**, mỗi String là immutable nên chia sẻ tham chiếu String không gây thay đổi nội dung String. Với danh sách các đối tượng **mutable** khác, việc sao chép danh sách **không** tự động sao chép sâu từng đối tượng.

**Khi cần List có thể sửa, đây thường là lựa chọn rõ ràng nhất.** Có thể viết biến kiểu interface **List<String>** để không ràng buộc code gọi vào implementation cụ thể.

## 5. Tạo List không thể sửa bằng List.of()

Từ Java 9, **List.of(...)** tạo danh sách **unmodifiable**:

~~~java
import java.util.Arrays;
import java.util.List;

String[] names = {"An", "Binh"};
List<String> immutableList = List.of(names);

names[0] = "Chi";

System.out.println(immutableList);         // [An, Binh]
System.out.println(Arrays.toString(names)); // [Chi, Binh]
~~~

Trong trường hợp **String[]** này, **List.of(names)** nhận các phần tử của mảng làm phần tử List, và danh sách tạo ra **không liên kết với mảng nguồn như Arrays.asList**. Thay phần tử của mảng sau khi tạo danh sách không làm thay phần tử đã lưu trong List.

Quy tắc:

- Không thể **add**, **remove**, **set** vào List do **List.of** trả về; phương thức thay đổi danh sách ném **UnsupportedOperationException**.
- **List.of** **không chấp nhận phần tử null**; nếu mảng có phần tử null, lúc tạo danh sách sẽ ném **NullPointerException**.
- Danh sách **unmodifiable** khác với đảm bảo sao chép sâu mọi đối tượng phần tử. Ví dụ với **List<SomeMutableObject>**, bản thân đối tượng vẫn có thể bị sửa từ nơi khác nếu nơi đó có tham chiếu.

Một ví dụ dễ gặp lỗi:

~~~java
String[] values = {"A", null};

// List<String> x = List.of(values); // NullPointerException
List<String> y = Arrays.asList(values); // Hợp lệ: cho phép phần tử null
~~~

Nếu bài toán yêu cầu **null** là giá trị hợp lệ, đừng dùng **List.of** hoặc **List.copyOf** trước khi xác định chính sách xử lý null.

### 5.1. List.copyOf khác gì?

Từ Java 10, **List.copyOf(collection)** tạo một danh sách unmodifiable chứa các phần tử tại thời điểm thực hiện, với quy tắc **không chấp nhận null**. Có thể dùng khi nguồn đã là một **Collection**:

~~~java
List<String> editable = new ArrayList<>(List.of("A", "B"));
List<String> snapshot = List.copyOf(editable);

editable.set(0, "C");

System.out.println(snapshot); // [A, B]
~~~

**List.copyOf** có thể tái sử dụng một List đã unmodifiable phù hợp thay vì lúc nào cũng tạo đối tượng mới. Quy tắc cần quan tâm ở đây là **không để thay đổi cấu trúc/giá trị các vị trí qua nguồn làm thay đổi danh sách trả về**, không phải giả định luôn cấp phát một bản copy mới.

Với mảng nguồn, **List.of(array)** diễn đạt nhu cầu tạo List không thể sửa rất ngắn gọn. Với collection nguồn, **List.copyOf(collection)** diễn đạt rõ mục đích tạo snapshot.

## 6. Ví dụ Java 17+ độc lập: so sánh ba cách chuyển đổi

Tạo tệp **StringArrayListDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class StringArrayListDemo {
    public static void main(String[] args) {
        String[] source = {"An", "Binh"};

        // View kích thước cố định, liên kết hai chiều với source.
        List<String> view = Arrays.asList(source);
        view.set(0, "Chi");
        System.out.println("array after view.set: "
                + Arrays.toString(source));

        source[1] = "Dung";
        System.out.println("view after array update: " + view);

        // Bản sao cấu trúc độc lập, có thể thêm/xóa.
        List<String> dynamic =
                new ArrayList<>(Arrays.asList(source));
        dynamic.add("Em");
        dynamic.set(0, "Giang");
        System.out.println("array after copy changes: "
                + Arrays.toString(source));
        System.out.println("dynamic: " + dynamic);

        // List unmodifiable, không cùng dùng mảng source.
        List<String> immutable = List.of(source);
        source[0] = "Hoa";
        System.out.println("List.of snapshot: " + immutable);

        // Chuyển List về mảng String[] mới.
        String[] back = dynamic.toArray(String[]::new);
        back[1] = "Khac";
        System.out.println("converted array: "
                + Arrays.toString(back));
        System.out.println("list after array edit: " + dynamic);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StringArrayListDemo.java
java StringArrayListDemo
~~~

Kết quả chuẩn:

~~~text
array after view.set: [Chi, Binh]
view after array update: [Chi, Dung]
array after copy changes: [Chi, Dung]
dynamic: [Giang, Dung, Em]
List.of snapshot: [Chi, Dung]
converted array: [Giang, Khac, Em]
list after array edit: [Giang, Dung, Em]
~~~

Diễn giải:

1. **view.set(0, "Chi")** thay vị trí 0 của chính mảng **source**.
2. **source[1] = "Dung"** phản ánh ở **view**, vì view vẫn dùng mảng đó.
3. **new ArrayList<>(...)** giữ các phần tử theo giá trị tại thời điểm tạo, nhưng có các vị trí độc lập. Sửa **dynamic** không thay **source**.
4. **List.of(source)** tạo List không thể sửa từ các phần tử hiện tại; sau khi **source[0] = "Hoa"**, **immutable** vẫn chứa **Chi**.
5. **dynamic.toArray(String[]::new)** tạo **String[]** mới. Sửa mảng **back** không làm **dynamic** đổi theo.

Đó là lý do hai lời gọi đều có dạng “chuyển mảng thành List” nhưng mang ngữ nghĩa sở hữu dữ liệu khác nhau.

## 7. Chuyển List<String> về String[]

Nếu phương thức nhận **String[]** nhưng dữ liệu đang ở **List<String>**, hãy dùng **toArray** có kiểu.

### 7.1. Cách hiện đại: toArray(String[]::new)

~~~java
List<String> names = List.of("An", "Binh", "Chi");

String[] array = names.toArray(String[]::new);
System.out.println(Arrays.toString(array)); // [An, Binh, Chi]
~~~

Biến thể **Collection.toArray(IntFunction<T[]>)** xuất hiện từ Java 11. **String[]::new** là một **array constructor reference**: nó cung cấp cách tạo mảng String đúng kiểu mà API yêu cầu.

Kết quả là một **mảng mới có kiểu String[]**, giữ thứ tự lặp của danh sách. Với List, thứ tự lặp trùng thứ tự các chỉ số.

### 7.2. Cách phổ biến lâu đời: toArray(new String[0])

~~~java
List<String> names = List.of("An", "Binh");
String[] array = names.toArray(new String[0]);
~~~

Đây cũng là cách đúng và tương thích rộng rãi. Mảng đầu vào được dùng để chỉ rõ kiểu phần tử; khi mảng quá nhỏ, API cấp phát một mảng mới có kiểu runtime tương ứng. Với **new String[0]**, kết quả là **String[]** mới có độ dài bằng số phần tử.

Có thể viết:

~~~java
String[] array = names.toArray(new String[names.size()]);
~~~

Nếu mảng truyền vào đủ dài, API có thể **dùng chính mảng đó** để chứa kết quả; khi mảng dài hơn số phần tử, phần tử ngay sau kết quả được đặt thành **null**. Đây là điểm cần biết khi dùng lại một mảng có sẵn:

~~~java
List<String> names = List.of("A", "B");
String[] buffer = new String[4];

String[] result = names.toArray(buffer);
System.out.println(result == buffer);           // true
System.out.println(Arrays.toString(buffer));   // [A, B, null, null]
~~~

**Chọn một trong hai cách dễ đọc**: **list.toArray(String[]::new)** cho Java 11+, hoặc **list.toArray(new String[0])** khi muốn cách quen thuộc và tương thích với Java cũ hơn.

### 7.3. Tránh toArray() không tham số nếu cần String[]

**list.toArray()** trả về **Object[]**, không phải **String[]**:

~~~java
List<String> names = List.of("A", "B");
Object[] generic = names.toArray();      // Đúng: Object[]
String[] typed = names.toArray(String[]::new); // Đúng: String[]
~~~

Đoạn sau sẽ thất bại ở runtime:

~~~java
// String[] wrong = (String[]) names.toArray();
// ClassCastException: Object[] không thể ép thành String[]
~~~

Việc mọi phần tử đều là **String** **không biến kiểu runtime của Object[] thành String[]**. Phải yêu cầu mảng có kiểu thành phần đúng ngay từ lúc chuyển đổi.

## 8. So sánh tính độc lập của dữ liệu sau chuyển đổi

Đây là bảng chọn API theo mục đích phổ biến:

| Từ nguồn | Cách chuyển đổi | Có sửa kích thước List được không? | Liên kết thay phần tử với mảng nguồn? |
| --- | --- | --- | --- |
| **String[]** | **Arrays.asList(arr)** | Không | Có, hai chiều |
| **String[]** | **new ArrayList<>(Arrays.asList(arr))** | Có | Không |
| **String[]** | **List.of(arr)** | Không; unmodifiable | Không |
| **List<String>** | **list.toArray(String[]::new)** | Không áp dụng: kết quả là mảng | Không: mảng mới |
| **List<String>** | **list.toArray(new String[0])** | Không áp dụng: kết quả là mảng | Không: mảng mới |

Bảng nói về **thay phần tử hoặc kích thước của cấu trúc chứa**; không khẳng định có deep copy từng đối tượng. Với String immutable, mối quan hệ này thường đủ để quyết định cách chuyển đổi.

### 8.1. Unmodifiable view không đồng nghĩa snapshot

Có thêm cách bọc một List bằng **Collections.unmodifiableList(list)**:

~~~java
String[] source = {"A", "B"};
List<String> view = Arrays.asList(source);
List<String> readOnlyView = java.util.Collections.unmodifiableList(view);

source[0] = "C";
System.out.println(readOnlyView); // [C, B]
~~~

Người giữ **readOnlyView** không được gọi **set()** để thay phần tử qua wrapper, nhưng List bọc bên dưới vẫn là view trên mảng **source**. Khi source đổi, nội dung đọc từ wrapper đổi theo.

Vì vậy, **read-only interface** và **snapshot độc lập** là hai khái niệm khác nhau:

- Cần chỉ cấm phía nhận sửa qua reference? Wrapper unmodifiable có thể đủ, nhưng dữ liệu gốc vẫn có thể thay đổi.
- Cần giữ tập phần tử ở thời điểm chuyển đổi? Dùng **List.of(array)** hoặc **List.copyOf(collection)** khi chính sách null cho phép.

## 9. Null, chuỗi rỗng và mảng/danh sách rỗng

**String rỗng ""** là một đối tượng String hợp lệ và **khác null**. Đừng loại bỏ nó chỉ vì một API không cho phần tử null.

~~~java
String[] source = {"A", null, ""};

List<String> fixed = Arrays.asList(source);
List<String> dynamic = new ArrayList<>(fixed);

System.out.println(fixed.size());        // 3
System.out.println(dynamic.get(1) == null); // true
System.out.println(dynamic.get(2).isEmpty()); // true

// List<String> immutable = List.of(source);
// Ném NullPointerException vì có phần tử null.
~~~

Khi **chính mảng nguồn bằng null**, các thao tác chuyển đổi nhận mảng không phải là “tạo danh sách rỗng”:

~~~java
String[] source = null;

// Arrays.asList(source) hoặc List.of(source) sẽ gặp lỗi null;
// cần quyết định null nghĩa là gì theo hợp đồng API.
List<String> result =
        source == null ? List.of() : new ArrayList<>(Arrays.asList(source));
~~~

Đây chỉ là **một chính sách minh họa**: chuyển null thành danh sách rỗng. Trong API khác, null có thể là dữ liệu thiếu không hợp lệ và nên được báo lỗi; không mặc định nuốt mất tín hiệu nghiệp vụ.

Với dữ liệu rỗng thực sự:

~~~java
String[] emptyArray = new String[0];
List<String> emptyList = List.of();

System.out.println(Arrays.asList(emptyArray).isEmpty()); // true
System.out.println(emptyList.toArray(String[]::new).length); // 0
~~~

Mảng độ dài 0 và List không phần tử đều là cấu trúc hợp lệ. Nhưng một List rỗng unmodifiable vẫn không cho phép **add()**.

## 10. Hiệp biến mảng và bất biến generics: vấn đề type safety

Sự khác nhau còn nằm ở hệ thống kiểu Java.

### 10.1. Mảng hiệp biến (covariant)

Java cho phép gán **String[]** vào biến **Object[]**, vì String là lớp con của Object. Nhưng mảng giữ kiểu thành phần thực tế ở runtime:

~~~java
Object[] values = new String[]{"A", "B"};
values[0] = "C"; // Hợp lệ
// values[1] = 42; // ArrayStoreException ở runtime
~~~

Biến được khai báo là **Object[]**, nhưng đối tượng thực là **String[]**. Gán Integer vào mảng đó bị từ chối ở runtime.

### 10.2. Generic List bất biến (invariant)

Java không cho phép coi **List<String>** là **List<Object>**:

~~~java
List<String> names = new ArrayList<>();
// List<Object> objects = names; // Lỗi biên dịch
~~~

Điều này ngăn việc thêm đối tượng không phải String vào danh sách qua một tham chiếu **List<Object>**. Nếu chỉ cần **đọc** các phần tử như Object, có thể sử dụng wildcard:

~~~java
List<String> names = List.of("An", "Binh");
List<? extends Object> readable = names;

Object first = readable.get(0);
// readable.add(123); // Không hợp lệ với wildcard extends
~~~

Các quy tắc này giải thích tại sao chuyển đổi dữ liệu nên **giữ kiểu String[] hoặc List<String>**, tránh ép kiểu không an toàn sang mảng/generic khác.

### 10.3. Tránh dùng raw type

Không nên viết:

~~~java
// List raw = Arrays.asList(new String[]{"A", "B"});
~~~

Raw type bỏ bớt kiểm tra kiểu ở thời điểm biên dịch, dễ dẫn đến lỗi khi đưa dữ liệu qua API khác. Với Java hiện đại, khai báo rõ **List<String>**.

## 11. Dùng Stream khi chuyển đổi cần xử lý phần tử

Nếu chỉ chuyển cấu trúc giữ nguyên các phần tử, **Arrays.asList** hoặc **toArray** thường đơn giản hơn. Nếu cần **lọc, ánh xạ, sắp xếp** trong quá trình chuyển, Stream phù hợp hơn.

### 11.1. Từ String[] thành List đã xử lý

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

String[] data = {" An ", "", " Binh ", " Chi "};

List<String> clean = Arrays.stream(data)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toCollection(ArrayList::new));

System.out.println(clean); // [An, Binh, Chi]
clean.add("Dung");         // Được: kết quả là ArrayList
~~~

**Collectors.toCollection(ArrayList::new)** làm rõ mong muốn có danh sách có thể thay đổi. Nếu dùng **Stream.toList()** (Java 16+), kết quả là List **unmodifiable**, không nên gọi **add()** hoặc **set()**.

### 11.2. Từ List thành mảng sau khi xử lý

~~~java
List<String> names = List.of("An", "Binh", "Chi");

String[] shortNames = names.stream()
        .filter(s -> s.length() <= 3)
        .toArray(String[]::new);

System.out.println(Arrays.toString(shortNames)); // [An, Chi]
~~~

**Stream.toArray(String[]::new)** tạo mảng đúng kiểu, tương tự ý tưởng dùng **Collection.toArray(String[]::new)**. Nhưng Stream phù hợp khi có thao tác trung gian; không cần mở Stream chỉ để chép List sang mảng.

### 11.3. Đừng suy ra mọi collector trả ArrayList

Các cách như **Collectors.toList()** không hứa hẹn implementation hoặc quyền sửa cụ thể trong hợp đồng API. Nếu ứng dụng cần chắc chắn có thể thêm/xóa, hãy yêu cầu bằng **Collectors.toCollection(ArrayList::new)** hoặc chuyển kết quả thành **new ArrayList<>(...)**.

## 12. Chuyển đổi ở ranh giới API và bảo vệ dữ liệu

Giả sử một phương thức nhận mảng và lưu danh sách cho sử dụng lâu dài:

~~~java
import java.util.Arrays;
import java.util.List;

public class NameRepository {
    private final List<String> names;

    public NameRepository(String[] input) {
        this.names = List.copyOf(Arrays.asList(input));
    }

    public List<String> getNames() {
        return names;
    }
}
~~~

Ý nghĩa:

- **List.copyOf** tạo danh sách unmodifiable, không phụ thuộc việc gán lại phần tử trong mảng **input** sau đó.
- Code bên ngoài không thể thay phần tử qua danh sách trả về.
- Constructor **không chấp nhận null array hoặc null element**; đây phải là lựa chọn phù hợp với hợp đồng của lớp.
- Đây là trường hợp **String** bất biến; nếu phần tử là đối tượng mutable, muốn bất biến sâu cần xem xét sao chép chính đối tượng phần tử.

Nếu API cần nhận dữ liệu có thể chứa null hoặc cần cập nhật danh sách nội bộ, có thể sử dụng **new ArrayList<>(Arrays.asList(input))**, kết hợp quy định quyền sửa/đồng bộ thích hợp.

Khi trả **String[]** cho code khác, dùng **clone()** nếu không muốn bên nhận sửa cùng mảng nội bộ:

~~~java
private final String[] stored = {"A", "B"};

public String[] getNames() {
    return stored.clone();
}
~~~

**clone()** của mảng tạo một mảng mới cùng kiểu và cùng các tham chiếu phần tử; với String immutable, cách này thường đủ để tránh code gọi thay phần tử của mảng lưu trữ.

**Không mặc định rằng chuyển đổi tự phòng thủ dữ liệu**: cụ thể, **Arrays.asList(source)** vẫn cho code gọi sửa các phần tử của mảng source qua **set()**.

## 13. Các lỗi thường gặp và cách khắc phục

| Tình huống | Nguyên nhân | Cách đúng |
| --- | --- | --- |
| **Arrays.asList(arr).add("X")** ném lỗi | List được hỗ trợ bởi mảng, kích thước cố định | **new ArrayList<>(Arrays.asList(arr))** |
| **List.of(arr).set(0, "X")** ném lỗi | List unmodifiable | Chọn **new ArrayList<>(...)** khi cần sửa |
| Sửa mảng làm List tự thay đổi | **Arrays.asList** dùng chung mảng | Dùng bản sao độc lập |
| **(String[]) list.toArray()** ném lỗi | **toArray()** không tham số trả **Object[]** | **toArray(String[]::new)** hoặc **toArray(new String[0])** |
| **List.of(arr)** ném NullPointerException | Mảng chứa phần tử null | Xử lý null hoặc chọn List cho phép null |
| In mảng ra mã nhận dạng khó đọc | **array.toString()** không hiển thị nội dung | Dùng **Arrays.toString(array)** |
| Nhầm **List<String>** luôn có thể add | Interface không bảo đảm implementation mutable | Biết nguồn gốc List; dùng ArrayList nếu cần |
| Bọc **unmodifiableList** nhưng dữ liệu vẫn đổi | Wrapper chỉ chặn thay đổi qua nó; nguồn dưới vẫn có thể đổi | Tạo snapshot độc lập |
| Ép mảng hoặc dùng raw generic không an toàn | Kiểu runtime và quy tắc generic khác nhau | Giữ **String[]**, **List<String>** đúng kiểu |
| Sao chép List rồi tưởng sao chép sâu tất cả đối tượng | Các phần tử được copy theo tham chiếu | Cân nhắc deep copy nếu phần tử mutable |

## 14. Bài tập tự kiểm tra

### Bài 1: Dự đoán đầu ra

~~~java
String[] data = {"A", "B"};
List<String> a = Arrays.asList(data);
List<String> b = new ArrayList<>(a);
List<String> c = List.of(data);

a.set(0, "X");
b.add("C");
data[1] = "Y";

System.out.println(Arrays.toString(data));
System.out.println(a);
System.out.println(b);
System.out.println(c);
~~~

Kết quả:

~~~text
[X, Y]
[X, Y]
[A, B, C]
[A, B]
~~~

Giải thích: **a** dùng chung mảng **data**; **b** tạo cấu trúc ArrayList riêng khi dữ liệu là **[A, B]**; **c** chốt các phần tử thành List unmodifiable tại thời điểm tạo. Việc thay đổi mảng sau đó không cập nhật **b** hoặc **c**.

### Bài 2: Chọn đúng API

Bạn có mảng **String[] tags** và cần:

1. Chỉ đọc các phần tử qua API nhận **List<String>**, có thể chấp nhận các thay đổi từ mảng nguồn → **Arrays.asList(tags)**.
2. Thêm/xóa các nhãn trong List mà không làm thay mảng gốc → **new ArrayList<>(Arrays.asList(tags))**.
3. Lưu một danh sách không thể sửa, không phản ánh các thay đổi vị trí mảng sau khi chuyển, và chắc chắn không có null → **List.of(tags)**.
4. Trả một mảng String độc lập từ một List → **list.toArray(String[]::new)**.
5. Lọc bỏ phần tử rỗng trước khi tạo mảng → Stream với **filter(...)** rồi **toArray(String[]::new)**.

Hãy tự thay các giá trị bằng **null**, chuỗi rỗng hoặc danh sách không phần tử để kiểm tra cách từng API xử lý.

## 15. Checklist trước khi chuyển đổi trong chương trình thật

- [ ] API đầu ra thực sự cần **String[]** hay **List<String>**?
- [ ] Nếu cần List, muốn **view chung dữ liệu**, **bản sao sửa được** hay **snapshot unmodifiable**?
- [ ] Phần tử null có hợp lệ không, hay cần loại bỏ/từ chối trước khi chuyển đổi?
- [ ] Code gọi có cần **add/remove**, **set** hay chỉ đọc?
- [ ] Có ai khác còn giữ mảng/List nguồn và có thể thay đổi nó sau chuyển đổi không?
- [ ] Khi chuyển về mảng, đã gọi **toArray(String[]::new)** hoặc **toArray(new String[0])** chưa?
- [ ] Nếu phần tử là đối tượng mutable thay vì String, đã phân biệt sao chép cấu trúc với deep copy chưa?
- [ ] Đã thử các trường hợp rỗng, một phần tử, nhiều phần tử và thay đổi dữ liệu sau chuyển đổi chưa?

**Ghi nhớ:** **String[]** có độ dài cố định; **List<String>** là một interface với quyền sửa tùy implementation. **Arrays.asList** tạo view kích thước cố định gắn với mảng; **new ArrayList<>(Arrays.asList(...))** tạo cấu trúc độc lập có thể sửa; **List.of** tạo List không thể sửa, không phản ánh việc thay phần tử của mảng nguồn; **toArray(String[]::new)** chuyển về mảng đúng kiểu. Chọn API theo **quyền sửa và quan hệ sở hữu dữ liệu**, không chỉ theo cú pháp ngắn nhất.

### Tài liệu tham khảo chính thức

- Java SE 17, **java.util.Arrays** (asList, toString, stream): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html
- Java SE 17, **java.util.List** (of, copyOf, toArray): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html
- Java SE 17, **java.util.Collection** (toArray): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html
- Java SE 17, **java.util.stream.Stream** (toList, toArray): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
