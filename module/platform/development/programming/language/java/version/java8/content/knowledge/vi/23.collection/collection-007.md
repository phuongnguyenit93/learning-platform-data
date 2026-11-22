# Collection không hỗ trợ sửa đổi và UnsupportedOperationException trong Java

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích chính xác **Collection không hỗ trợ sửa đổi** (*unmodifiable collection*) và khi nào Java ném **UnsupportedOperationException** (UOE).
2. Phân biệt **unmodifiable**, **immutable**, **fixed-size**, **unmodifiable view**, **snapshot** và **collection có thể sửa đổi**.
3. Chọn giữa **List.of**, **Set.of**, **Map.of**, các phương thức **copyOf**, **Collections.unmodifiableList**, **Arrays.asList**, **Stream.toList** và các collector hiện hành.
4. Hiểu vì sao một tham chiếu kiểu List/Collection/Map không bảo đảm mọi phương thức thay đổi đều được hỗ trợ, cũng như lý do UOE có thể xảy ra ngay cả với thao tác “không làm thay đổi gì”.
5. Viết API trả dữ liệu chỉ đọc đúng mong muốn, tránh làm lộ trạng thái mutable, đồng thời hiểu giới hạn của **shallow immutability**.
6. Nhận diện và sửa những lỗi thường gặp: gọi add trên Stream.toList(), thay đổi kích thước Arrays.asList(), nghĩ unmodifiable view là bản sao, lạm dụng catch UOE.
7. Biên dịch/chạy chương trình Java 17+ và phân tích kết quả chính xác.

**Phạm vi phiên bản:** Java Collections Framework và UnsupportedOperationException vẫn là kiến thức cốt lõi, **vẫn còn áp dụng** trong Java hiện đại. Bài phân biệt rõ các API đã có từ Java 8 với List.of/Set.of/Map.of (Java 9), List.copyOf/Set.copyOf/Map.copyOf và Collectors.toUnmodifiableList (Java 10), Stream.toList (Java 16). Không sử dụng API đã legacy hoặc giả định dựa vào lớp triển khai nội bộ.

## 1. Một Collection có thể “đọc được” nhưng không “sửa được”

Java Collections Framework định nghĩa các interface như Collection<E>, List<E>, Set<E> và Map<K,V>. Interface công bố các thao tác, nhưng **không phải mọi implementation đều phải hỗ trợ tất cả thao tác thay đổi**.

Ví dụ:

~~~java
// Mảnh mã Java, cần import java.util.List.
List<String> names = List.of("An", "Binh");
String first = names.get(0); // Hợp lệ: "An"
names.add("Chi");            // Ném UnsupportedOperationException.
~~~

Biến names có kiểu List<String>, trong đó có phương thức add. Tuy nhiên, object do List.of tạo là unmodifiable. **Biên dịch thành công không đồng nghĩa lời gọi được hỗ trợ khi chạy**.

~~~text
Mã nguồn hợp lệ về mặt kiểu
          |
       compile
          |
       runtime
          |
   object cụ thể có hỗ trợ add?
       /               \
      Có              Không
      |                 |
  thêm phần tử     UnsupportedOperationException
~~~

**UOE là unchecked exception** (thuộc RuntimeException) cho biết một thao tác được yêu cầu nhưng object không hỗ trợ. Nó khác với NullPointerException (truy cập null), IndexOutOfBoundsException (vị trí ngoài phạm vi), IllegalArgumentException (đối số không hợp lệ) và ConcurrentModificationException (một số kiểu sửa đổi đồng thời/ngoài luồng phát hiện được).

Đừng dựa vào tên implementation trong thông báo stack trace để suy ra hợp đồng dài hạn; xét JavaDoc của **factory method và interface** tương ứng.

## 2. Hiểu đúng năm khái niệm

| Khái niệm | Có thể thêm/xóa/thay qua tham chiếu nhận được? | Nguồn có thể làm nội dung quan sát được thay đổi? |
|---|---|---|
| Mutable collection, ví dụ ArrayList | Có, theo các thao tác mà class hỗ trợ | Có |
| Unmodifiable collection | Không qua các mutator của collection đó | Có thể, nếu object phần tử mutable hoặc có backing collection |
| Unmodifiable view | Không qua view | **Có**, nếu nơi khác sửa backing collection |
| Fixed-size List từ Arrays.asList | Không đổi kích thước; **set được phần tử** | Có, array backing và List phản ánh lẫn nhau |
| Unmodifiable snapshot từ List.copyOf | Không qua mutator; độc lập với thay đổi cấu trúc sau này của nguồn mutable | Phần tử mutable bên trong **vẫn có thể thay đổi** |

### 2.1. Unmodifiable không nhất thiết là deep immutable

Unmodifiable nghĩa là **các mutator của collection bị cấm**: không thể dùng collection.add/remove/clear, list.set, map.put hoặc thao tác tương ứng để thay đổi cấu trúc trực tiếp. Tuy nhiên, object phần tử có thể mutable:

~~~java
// Mảnh mã: Item là object mutable do ứng dụng định nghĩa.
List<Item> items = List.of(item);
item.rename("new name"); // Có thể thay đổi trạng thái Item.
~~~

List vẫn không cho phép thay **phần tử tham chiếu** qua set, nhưng trạng thái bên trong Item có thể khác đi. Đó là lý do nói **unmodifiable container ≠ mọi object có thể truy cập từ container đều immutable**.

### 2.2. Unmodifiable view là cửa sổ đọc vào một nguồn khác

~~~java
// Mảnh mã, với import java.util.*.
List<String> source = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(source);
source.add("B");
System.out.println(view); // [A, B]
~~~

Không thể gọi view.add, nhưng nơi nắm giữ source vẫn sửa được backing List. View phản ánh kết quả mới; nó **không phải một bản sao tĩnh**.

### 2.3. Snapshot tách cấu trúc khỏi nguồn

~~~java
// Mảnh mã, với import java.util.*.
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);
source.add("B");
System.out.println(snapshot); // [A]
~~~

List.copyOf tạo danh sách không sửa được và **không phản ánh các sửa đổi sau này của Collection nguồn** theo hợp đồng API. Nhưng đây là **shallow copy của tham chiếu phần tử**, không tự sao chép sâu các object mutable bên trong.

**Chi tiết quan trọng:** Khi đầu vào đã là một unmodifiable List thích hợp, List.copyOf có thể tái sử dụng object; **không dựa vào == để kiểm tra có copy hay không**. Điều đáng tin là hợp đồng giá trị/cấu trúc của List trả về.

## 3. Vì sao UnsupportedOperationException được phép tồn tại trong interface?

Trong Java Collection, nhiều thao tác thay đổi là **optional operations**. Ví dụ, Collection.add, remove, clear, addAll, removeAll, retainAll hoặc List.set có thể không được hỗ trợ bởi một implementation cụ thể.

Do đó:

- Interface cho phép bạn **gọi** phương thức theo kiểu tĩnh.
- Implementation quyết định thao tác đó **có được hỗ trợ** không.
- Nếu không hỗ trợ, implementation có thể ném UnsupportedOperationException theo hợp đồng.

Một sắc thái quan trọng: đối với thao tác *về thực tế không làm thay đổi gì* — chẳng hạn addAll(emptyList) hoặc remove một phần tử không tồn tại — Java Collection cho phép một số implementation **ném UOE hoặc không ném UOE**, tùy hợp đồng cụ thể. Vì thế **không dùng “thao tác sẽ không làm gì” như mẹo chắc chắn tránh exception**.

Các List do List.of và List.copyOf tạo có hợp đồng chặt hơn: gọi **bất kỳ mutator nào** trên List đều ném UOE, kể cả trường hợp có vẻ không gây thay đổi thực tế. Khi viết code generic, dựa vào JavaDoc của Collection cụ thể.

### UOE không có nghĩa object đã bị chỉnh sửa một phần

Các factory unmodifiable tiêu chuẩn không chấp nhận các mutator như add/set/remove. Tuy nhiên, với một implementation tùy biến do thư viện khác cung cấp, bạn phải đọc contract của nó thay vì tự khẳng định trạng thái luôn được rollback khi exception phát sinh.

### Phân biệt lỗi khác

| Exception | Ví dụ thường gặp |
|---|---|
| UnsupportedOperationException | List.of(...).add(...); Arrays.asList(...).remove(0) |
| NullPointerException | List.of("A", null); List.copyOf(listCóNull) |
| IllegalArgumentException | Set.of("A","A"); Map.of("x",1,"x",2) |
| IndexOutOfBoundsException | mutableList.get(99) khi danh sách quá ngắn |
| ConcurrentModificationException | Một số iterator phát hiện sửa cấu trúc backing không đúng quy tắc; không được bảo đảm phát hiện mọi race |

Trong phần tiếp theo, các ví dụ có cả UOE lẫn exception của dữ liệu factory, để người học không gọi mọi lỗi là UnsupportedOperationException.

## 4. Các cách tạo collection hiện hành: so sánh

| API | Phiên bản | Thuộc tính chính | Cho null? |
|---|---|---|---|
| new ArrayList<>(...) | Từ rất lâu, hiện hành | List có thể thêm/xóa/set | ArrayList cho phép null |
| Collections.unmodifiableList(list) | Java cũ, vẫn hiện hành | **Read-only view** trên backing List | Phụ thuộc backing List |
| Arrays.asList(array) | Java cũ, vẫn hiện hành | **Fixed-size view** trên array; set được, add/remove không được | Có thể chứa null |
| List.of(elements...) | Java 9+ | Unmodifiable List, không có backing mutable được truyền vào | **Không** |
| Set.of(elements...) | Java 9+ | Unmodifiable Set, các phần tử phải khác nhau | **Không** |
| Map.of(...), Map.ofEntries(...) | Java 9+ | Unmodifiable Map | **Không** |
| List.copyOf(collection) | Java 10+ | Unmodifiable List snapshot theo nội dung nguồn tại thời điểm tạo | **Không** |
| Set.copyOf(collection) | Java 10+ | Unmodifiable Set từ phần tử nguồn | **Không** |
| Map.copyOf(map) | Java 10+ | Unmodifiable Map từ các entry nguồn | **Không** |
| Stream.toList() | Java 16+ | Unmodifiable List theo encounter order nếu có | **Có thể chứa null** |
| Collectors.toUnmodifiableList() | Java 10+ | Unmodifiable List từ Stream | **Không** |
| Collectors.toList() | Java 8+ | Thu thập vào List; API không bảo đảm kiểu/mutability | API không cam kết loại bỏ null |
| Collectors.toCollection(ArrayList::new) | Java 8+ | Tạo loại Collection bạn chủ động chọn | Theo loại Collection đó |

Không trộn lẫn hai điều: **unmodifiable** và **không có null**. Ví dụ Stream.toList có thể trả một danh sách không sửa được **nhưng chứa null**, trong khi List.of, List.copyOf và Collectors.toUnmodifiableList không cho phép null.

### Trường hợp đặc biệt của Set.of và Map.of

- Set.of có thể từ chối phần tử trùng bằng **IllegalArgumentException**; Set.copyOf có thể lấy một đại diện từ các phần tử trùng của nguồn.
- Map.of không cho phép key trùng, và từ chối null ở cả key/value; Map.ofEntries cho phép viết nhiều entry.
- **Không suy ra thứ tự duyệt ổn định** từ Set.of hoặc Map.of. Nếu thứ tự xuất ra báo cáo là yêu cầu, dùng một kiểu sắp xếp phù hợp hoặc chủ động sắp xếp trước khi hiển thị.
- Với List.of, thứ tự phần tử giữ đúng thứ tự tham số. Nhưng đừng coi identity hoặc lớp implementation cụ thể là một phần của hợp đồng.

## 5. Ví dụ chạy được 1 — UOE từ factory unmodifiable

Tệp **UnmodifiableFactoriesDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class UnmodifiableFactoriesDemo {
    static void expectUnsupported(String operation, Runnable action) {
        try {
            action.run();
            System.out.println(operation + "=supported");
        } catch (UnsupportedOperationException expected) {
            System.out.println(operation + "=UnsupportedOperationException");
        }
    }

    static void expectNullPointer(String operation, Runnable action) {
        try {
            action.run();
            System.out.println(operation + "=accepted");
        } catch (NullPointerException expected) {
            System.out.println(operation + "=NullPointerException");
        }
    }

    static void expectIllegalArgument(String operation, Runnable action) {
        try {
            action.run();
            System.out.println(operation + "=accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println(operation + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        Set<String> tags = Set.of("java", "stream");
        Map<String, Integer> scores = Map.of("An", 90, "Binh", 80);

        System.out.println("names=" + names);
        System.out.println("first=" + names.get(0));

        expectUnsupported("list.add", () -> names.add("Chi"));
        expectUnsupported("list.set", () -> names.set(0, "Mai"));
        expectUnsupported("list.clear", names::clear);
        expectUnsupported("set.add", () -> tags.add("collect"));
        expectUnsupported("map.put", () -> scores.put("Chi", 70));

        expectNullPointer("list.null", () -> List.of("A", (String) null));
        expectIllegalArgument("set.duplicate",
                () -> Set.of("A", "A"));
        expectIllegalArgument("map.duplicate",
                () -> Map.of("key", 1, "key", 2));

        System.out.println("still=" + names);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~text
javac --release 17 UnmodifiableFactoriesDemo.java
java UnmodifiableFactoriesDemo
~~~

Stdout:

~~~text
names=[An, Binh]
first=An
list.add=UnsupportedOperationException
list.set=UnsupportedOperationException
list.clear=UnsupportedOperationException
set.add=UnsupportedOperationException
map.put=UnsupportedOperationException
list.null=NullPointerException
set.duplicate=IllegalArgumentException
map.duplicate=IllegalArgumentException
still=[An, Binh]
~~~

**Giải thích:** List.of cho phép đọc và lặp nhưng không cho phép thêm, thay thế hay xóa. Set.of/Map.of cũng chặn thay đổi. Khi xây dựng factory với dữ liệu không hợp lệ, lỗi là NPE hoặc IllegalArgumentException **ngay lúc tạo**, không phải UOE. Chương trình không in trực tiếp Set/Map để tránh phụ thuộc thứ tự duyệt không được bảo đảm.

**Không áp dụng kiểu “catch UOE rồi bỏ qua” cho nghiệp vụ.** Các hàm expectUnsupported chỉ phục vụ kiểm thử hành vi API. Trong ứng dụng, chọn dữ liệu mutable nếu cần sửa, thay vì luôn ném exception rồi xử lý.

## 6. Collections.unmodifiableList: view không phải snapshot

Collections.unmodifiableList(list) tạo **unmodifiable view**. Query operation đọc thông tin từ backing List; các thao tác sửa thông qua view bị cấm. Nhưng nếu ai đó còn giữ tham chiếu tới backing List và thay đổi nó, view sẽ phản ánh thay đổi.

Tệp **ViewAndSnapshotDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewAndSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("red", "blue")
        );

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> mutableCopy = new ArrayList<>(source);

        System.out.println("before.view=" + view);
        System.out.println("before.snapshot=" + snapshot);

        source.set(0, "green");
        source.add("yellow");

        System.out.println("after.view=" + view);
        System.out.println("after.snapshot=" + snapshot);
        System.out.println("after.mutableCopy=" + mutableCopy);

        try {
            view.add("black");
        } catch (UnsupportedOperationException expected) {
            System.out.println("view.add=UnsupportedOperationException");
        }

        mutableCopy.add("white");
        System.out.println("editedCopy=" + mutableCopy);
        System.out.println("source=" + source);
    }
}
~~~

Chạy:

~~~text
javac --release 17 ViewAndSnapshotDemo.java
java ViewAndSnapshotDemo
~~~

Stdout:

~~~text
before.view=[red, blue]
before.snapshot=[red, blue]
after.view=[green, blue, yellow]
after.snapshot=[red, blue]
after.mutableCopy=[red, blue]
view.add=UnsupportedOperationException
editedCopy=[red, blue, white]
source=[green, blue, yellow]
~~~

**Phân tích:**

1. view và source liên kết qua backing List; source.set/source.add làm nội dung quan sát qua view thay đổi.
2. snapshot là danh sách không sửa được **tách cấu trúc** khỏi source. Sau khi source được sửa, snapshot vẫn là [red, blue].
3. mutableCopy là một ArrayList khác; sửa source không ảnh hưởng danh sách đã copy, và mutableCopy.add thành công.
4. view.add ném UOE vì view không hỗ trợ mutator, dù source có hỗ trợ add.
5. Bản sao từ new ArrayList<>(source) cũng là **shallow copy**; ví dụ này dùng String (immutable), nên không có trường hợp phần tử mutable làm kết quả quan sát thay đổi.

### Khi nào nên dùng view?

Dùng view khi bạn **cố ý cho phép người đọc thấy các thay đổi hiện tại** của backing collection, nhưng không muốn họ sửa qua tham chiếu trả về. Ví dụ giao diện chỉ đọc dùng nội bộ có quản lý vòng đời và đồng bộ hóa.

Không dùng view như một cơ chế “đóng băng dữ liệu tại thời điểm trả về” trong trường hợp source còn thay đổi. Khi công khai API cần một snapshot độc lập, List.copyOf(source) thường thể hiện ý định rõ hơn.

### Khi nào nên dùng copy?

- Cần **danh sách không sửa được, không phản ánh thay đổi cấu trúc nguồn**: List.copyOf(source), nếu không có null.
- Cần một **danh sách mới có thể sửa**: new ArrayList<>(source).
- Cần **snapshot cho dữ liệu có thể chứa null**: cân nhắc bản sao ArrayList rồi Collections.unmodifiableList(copy) nếu yêu cầu cho phép null, hoặc chuẩn hóa/loại null trước khi dùng List.copyOf.
- Cần **deep immutable**: phải tạo bản sao/đối tượng bất biến cho từng phần tử theo chính sách dữ liệu, không chỉ bọc List.

## 7. Arrays.asList: fixed-size, không phải unmodifiable hoàn toàn

Một trong những nguồn gây UOE phổ biến nhất là Arrays.asList(array).

Arrays.asList trả **List có kích thước cố định (fixed-size)** và được **backed bởi array truyền vào**. Nó hỗ trợ đọc và **set** (thay phần tử cùng vị trí), nhưng không hỗ trợ thao tác làm **thay đổi kích thước** như add/remove.

Tệp **FixedSizeListDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FixedSizeListDemo {
    public static void main(String[] args) {
        String[] names = {"An", "Binh"};
        List<String> fixed = Arrays.asList(names);

        fixed.set(0, "Chi");
        System.out.println("array.afterSet="
                + Arrays.toString(names));

        names[1] = "Dung";
        System.out.println("list.afterArrayChange=" + fixed);

        try {
            fixed.add("Ha");
        } catch (UnsupportedOperationException expected) {
            System.out.println("fixed.add=UnsupportedOperationException");
        }

        try {
            fixed.remove(0);
        } catch (UnsupportedOperationException expected) {
            System.out.println("fixed.remove=UnsupportedOperationException");
        }

        List<String> resizable = new ArrayList<>(fixed);
        resizable.add("Ha");

        System.out.println("resizable=" + resizable);
        System.out.println("fixed.final=" + fixed);
    }
}
~~~

Chạy:

~~~text
javac --release 17 FixedSizeListDemo.java
java FixedSizeListDemo
~~~

Stdout:

~~~text
array.afterSet=[Chi, Binh]
list.afterArrayChange=[Chi, Dung]
fixed.add=UnsupportedOperationException
fixed.remove=UnsupportedOperationException
resizable=[Chi, Dung, Ha]
fixed.final=[Chi, Dung]
~~~

**Giải thích:**

- set thay phần tử, nên array backing cũng đổi theo; việc thay phần tử trong array cũng hiển thị qua List.
- add/remove cần đổi kích thước trong khi array cố định độ dài, nên List đó không hỗ trợ.
- new ArrayList<>(fixed) tạo List có thể thay đổi kích thước độc lập với array ban đầu.
- Arrays.asList **không giống** List.of: List.of không cho set; Arrays.asList có thể cho set.
- Arrays.asList **không giống** Collections.unmodifiableList: wrapper unmodifiable cấm set, nhưng backing List có thể được thay từ nơi khác.

### Mẹo kiểm tra mảng nguyên thủy

Arrays.asList(intArray) không cho List<Integer> gồm từng số nguyên nếu intArray là int[]. Vì generic varargs nhận **một phần tử int[]**, kết quả thường là List<int[]> kích thước 1. Muốn List<Integer>, hãy dùng IntStream.of(intArray).boxed().toList() (Java 16+) hoặc collect thích hợp. Đây là lỗi **kiểu phần tử**, không phải trực tiếp lỗi UOE, nhưng rất dễ nhầm khi xử lý array-backed List.

## 8. Stream.toList và các collector: điểm khác cần nhớ

Cùng mong muốn “thu được List từ Stream” nhưng các API có **hợp đồng mutability khác nhau**:

~~~java
// Mảnh mã, JDK 17+:
List<String> unmodifiable = Stream.of("A", "B").toList();

List<String> explicitlyMutable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

List<String> unspecifiedMutability = Stream.of("A", "B")
        .collect(Collectors.toList());

List<String> noNulls = Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableList());
~~~

Đoạn trên giả định các import tương ứng. Các kết luận chính:

- **Stream.toList() (Java 16+)**: trả List **unmodifiable**, các mutator ném UOE. **Có thể chứa null**. Thứ tự phần tử theo encounter order nếu Stream có thứ tự.
- **Collectors.toList() (Java 8+)**: không bảo đảm loại List cụ thể, tính mutable, serializable hoặc thread-safety. Có thể thấy ArrayList trong một JDK, nhưng không dựa vào đó làm hợp đồng.
- **Collectors.toCollection(ArrayList::new)**: chủ động tạo ArrayList mutable, có thể add/remove/set theo API.
- **Collectors.toUnmodifiableList() (Java 10+)**: trả List unmodifiable và **không chấp nhận null**.

### Ví dụ chạy được 4 — Streams, null và quyền sửa

Tệp **StreamCollectionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamCollectionDemo {
    public static void main(String[] args) {
        List<String> streamed = Stream.of("A", null, "B").toList();
        System.out.println("streamed=" + streamed);

        try {
            streamed.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("streamed.add=UnsupportedOperationException");
        }

        List<String> mutable = Stream.of("A", "B")
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add("C");
        System.out.println("mutable=" + mutable);

        List<String> collected = Stream.of("A", "B")
                .collect(Collectors.toList());
        System.out.println("collectors.toList=" + collected);

        try {
            Stream.of("A", null, "B")
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException expected) {
            System.out.println("toUnmodifiableList.null=NullPointerException");
        }

        List<String> copied = List.copyOf(mutable);
        System.out.println("copied=" + copied);

        try {
            copied.remove(0);
        } catch (UnsupportedOperationException expected) {
            System.out.println("copied.remove=UnsupportedOperationException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 StreamCollectionDemo.java
java StreamCollectionDemo
~~~

Stdout:

~~~text
streamed=[A, null, B]
streamed.add=UnsupportedOperationException
mutable=[A, B, C]
collectors.toList=[A, B]
toUnmodifiableList.null=NullPointerException
copied=[A, B, C]
copied.remove=UnsupportedOperationException
~~~

**Giải thích quan trọng:**

1. Stream.toList() giữ cả phần tử null nhưng **không cho sửa cấu trúc**.
2. toCollection(ArrayList::new) làm rõ rằng chương trình cần sửa collection sau khi collect.
3. Với Collectors.toList, chương trình **không thử add/remove**, vì mutability không được API cam kết.
4. toUnmodifiableList cấm null ngay trong quá trình thu thập.
5. List.copyOf(mutable) lấy snapshot không sửa được và không có phần tử null. Thao tác copied.remove bị chặn.

**Đừng thay cơ học** collect(Collectors.toList()) thành toList() nếu code phía sau có thao tác thêm/xóa: lời gọi mới có thể ném UOE, dù danh sách ban đầu trong môi trường cũ thường là ArrayList.

## 9. Không sửa được cấu trúc vẫn có thể thay đổi phần tử bên trong

Collection unmodifiable **không tự tạo deep immutable graph**. Nếu các phần tử là object mutable, gọi phương thức trên object đó có thể thay đổi nội dung nhìn thấy qua List.

Tệp **ShallowUnmodifiableDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowUnmodifiableDemo {
    static final class Item {
        private String name;

        Item(String name) {
            this.name = name;
        }

        void rename(String value) {
            this.name = value;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        Item item = new Item("A");
        List<Item> source = new ArrayList<>();
        source.add(item);

        List<Item> snapshot = List.copyOf(source);
        source.add(new Item("C"));
        item.rename("B");

        System.out.println("snapshot=" + snapshot);
        System.out.println("source=" + source);

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> nested = List.of(inner);
        inner.add("y");

        System.out.println("nested=" + nested);
        try {
            nested.add(List.of("z"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("nested.add=UnsupportedOperationException");
        }
    }
}
~~~

Chạy:

~~~text
javac --release 17 ShallowUnmodifiableDemo.java
java ShallowUnmodifiableDemo
~~~

Stdout:

~~~text
snapshot=[B]
source=[B, C]
nested=[[x, y]]
nested.add=UnsupportedOperationException
~~~

**Tại sao snapshot thành [B]?** Nó đã copy cấu trúc danh sách ban đầu gồm đúng một tham chiếu Item. Khi source được thêm Item thứ hai, snapshot không có thêm phần tử đó. Nhưng Item đầu tiên vẫn là **cùng object mutable**, nên khi rename("B"), snapshot thấy tên mới.

**Tại sao nested thành [[x, y]]?** List.of chỉ làm List **bên ngoài** không sửa được. List bên trong vẫn là ArrayList mutable và có thể add. Vì thế nested.add bị chặn, còn inner.add vẫn thành công.

### Thiết kế bất biến sâu hơn

Nếu muốn một snapshot thật sự ổn định, hãy bảo đảm **bản thân các phần tử** bất biến hoặc được sao chép phòng vệ. Ví dụ, một record có các thành phần String/long (immutable về mặt dữ liệu) thường phù hợp để chứa trong List.copyOf. Nếu record có thành phần List hoặc object mutable, cũng cần copy thành phần đó trong constructor và tránh làm lộ tham chiếu mutable.

Ví dụ mẫu với record giữ các chuỗi (đây là **mảnh mã độc lập về định nghĩa kiểu**, cần import List):

~~~java
record Team(String name, List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
~~~

Nhờ compact constructor, record giữ List đã được sao chép thành unmodifiable. Vì String cũng immutable, dữ liệu danh sách tên có tính bất biến hiệu quả. Nếu thành phần là List<Item> với Item mutable thì chỉ List.copyOf vẫn **không đủ** để bảo đảm tính bất biến sâu.

## 10. UOE trên Iterator, ListIterator, view và thao tác mặc định

Không chỉ add/remove trực tiếp mới gây UOE. Đối với collection không sửa được, các lối sửa gián tiếp cũng phải được xét:

- Iterator.remove() trên unmodifiable collection.
- ListIterator.add hoặc ListIterator.set trên unmodifiable List.
- List.set(index, value), replaceAll, sort và removeIf trên List unmodifiable theo hợp đồng tương ứng.
- Map.put, remove, clear, replace, compute hoặc entry.setValue trên Map unmodifiable khi các thao tác đó có ý định thay đổi.
- Collection.removeAll/retainAll/clear trên các view unmodifiable.

**Cẩn thận với no-op và optional operations:** ở mức hợp đồng Collection tổng quát, implementation có thể không ném UOE cho một thao tác không làm gì, nhưng cũng được phép ném. Do đó, không viết code phụ thuộc vào việc removeIf(predicateLuônFalse) chắc chắn thành công trên mọi Collection không hỗ trợ sửa đổi.

Cũng cần phân biệt:

- Một **iterator fail-fast** có thể ném ConcurrentModificationException nếu phát hiện nguồn bị sửa bất thường.
- Một **iterator unmodifiable** có thể ném UOE khi yêu cầu iterator.remove.
- Đây là hai câu chuyện khác nhau. Fail-fast không được bảo đảm phát hiện tất cả sửa đổi đồng thời và không phải cơ chế đồng bộ dữ liệu.

## 11. Trả dữ liệu ra khỏi API: view hay snapshot?

Giả sử một service giữ một List mutable trong field:

~~~java
// Mảnh mã có User và users do ứng dụng định nghĩa.
List<User> getUsers() {
    return users;
}
~~~

Cách này đưa thẳng tham chiếu mutable, có thể cho caller gọi add/remove và làm hỏng trạng thái bên trong service.

Có ba lựa chọn tùy hợp đồng:

~~~java
// 1) View: caller không sửa qua kết quả,
// nhưng vẫn thấy các thay đổi tiếp theo của users.
return Collections.unmodifiableList(users);

// 2) Snapshot không sửa được: caller thấy cấu trúc tại lúc trả.
return List.copyOf(users);

// 3) Bản sao mutable: caller sửa bản sao, không sửa trực tiếp field.
return new ArrayList<>(users);
~~~

Cả ba là **mảnh mã minh họa**, không phải ba return đặt liền nhau trong cùng phương thức. Chỉ dùng List.copyOf khi collection đầu vào không chứa null (và khi shallow copy đủ cho miền dữ liệu).

### Câu hỏi khi thiết kế API

1. Người nhận có cần thêm/xóa phần tử không?
2. Người nhận có nên **nhìn thấy cập nhật mới** của nguồn sau khi gọi không?
3. Nguồn có thể chứa null không?
4. Các phần tử có mutable không? Nếu có, người nhận được phép sửa trạng thái phần tử không?
5. Dữ liệu có được truy cập song song từ nhiều thread không?
6. Có yêu cầu snapshot ổn định để log, audit hoặc tính toán nhất quán không?
7. Có phải trả dữ liệu ra ngoài ranh giới module/process và cần serialization hay DTO thích hợp không?

**Không có một factory đúng cho mọi mục đích.** Một view read-only hữu ích khi muốn phản chiếu trạng thái hiện tại; một snapshot thường hợp lý ở ranh giới API phải giữ tính ổn định; một bản sao mutable phù hợp khi caller cần tự làm việc với dữ liệu mà không đụng đến nguồn.

## 12. Unmodifiable không đồng nghĩa thread-safe

Bọc một ArrayList bằng Collections.unmodifiableList **không làm ArrayList bên dưới tự thread-safe**. Nếu backing List còn bị thread khác sửa, việc đọc view trong lúc thay đổi vẫn phải tuân thủ quy tắc đồng bộ và an toàn bộ nhớ của Java.

Tương tự, một List.of chứa các phần tử mutable không bảo đảm an toàn nếu các thread đồng thời sửa **trạng thái từng phần tử**. Việc “không sửa được List” chỉ khóa các thao tác ở **cấu trúc collection**, không tự đồng bộ hóa mọi object tham chiếu.

Nếu cần chia sẻ dữ liệu giữa thread:

- Ưu tiên **immutable elements** và snapshot rõ ràng khi thiết kế có thể.
- Nếu dữ liệu thật sự cần thay đổi đồng thời, chọn concurrent collection thích hợp (chẳng hạn ConcurrentHashMap) hoặc cơ chế đồng bộ hóa/phát hành dữ liệu phù hợp.
- Với unmodifiable view trên backing mutable, phải quản lý synchronized/lock hoặc snapshot ở ranh giới truy cập theo yêu cầu nhất quán.
- Không dùng Collections.unmodifiableList như một giải pháp thay thế Collections.synchronizedList; hai API giải quyết **hai vấn đề khác nhau**.

Không suy ra từ tên “immutable” rằng object graph đã bất biến sâu hoặc mọi thao tác truy cập đồng thời tự động an toàn.

## 13. Lưu ý với Map và Set không sửa được

### Map.of, Map.copyOf và Collections.unmodifiableMap

~~~java
// Mảnh mã:
Map<String, Integer> map = Map.of("An", 1, "Binh", 2);
map.put("Chi", 3); // UnsupportedOperationException.
~~~

Map.of không nhận key/value null; các key trùng bị từ chối ngay lúc tạo. Map.copyOf(mapNguồn) tạo Map không sửa được từ entry của nguồn; nó không phản ánh những thay đổi cấu trúc tiếp theo của Map nguồn theo contract, nhưng value object mutable vẫn có thể bị sửa ở nơi khác.

~~~java
// Mảnh mã:
Map<String, Integer> source = new HashMap<>();
source.put("A", 1);
Map<String, Integer> view = Collections.unmodifiableMap(source);
source.put("B", 2); // View có thể nhìn thấy B.
~~~

Các view như keySet(), values() và entrySet() của Map unmodifiable không được cung cấp con đường lách để sửa cấu trúc Map. Tránh cố dùng Iterator.remove hoặc Map.Entry.setValue trên view và mong rằng có thể sửa ngầm.

### Set.of và Set.copyOf

~~~java
// Mảnh mã:
Set<String> tags = Set.of("java", "collections");
tags.add("stream"); // UnsupportedOperationException.
~~~

Set.of yêu cầu phần tử không null và không trùng; Set.copyOf nhận Collection nguồn và bỏ các phần tử trùng theo Set semantics, không yêu cầu đầu vào đã là Set. Với Set.of/Map.of, thứ tự iteration không được bảo đảm; không dựa vào thứ tự tình cờ quan sát được để kiểm tra hoặc in kết quả.

Nếu cần một thứ tự xác định, dùng Comparator/TreeSet/TreeMap hoặc sắp xếp các phần tử trước khi xuất. Một object mutable được dùng làm key của Map/Set còn có nguy cơ phá hợp đồng equals/hashCode nếu thay đổi sau khi chèn; đó là vấn đề **tính ổn định của khóa**, không được giải quyết bằng việc Map/Set không sửa được.

## 14. Cách sửa UOE đúng nguyên nhân

Khi gặp UnsupportedOperationException, xác định object thực tế đến từ đâu và **quyền sửa đổi nào** ứng dụng cần.

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý có chủ đích |
|---|---|---|
| List.of(...).add(...) ném UOE | List unmodifiable | Tạo new ArrayList<>(list) nếu cần sửa |
| Stream.toList().remove(...) ném UOE | Stream.toList trả unmodifiable List | Dùng collect(toCollection(ArrayList::new)) hoặc new ArrayList<>(...) |
| Arrays.asList(...).add(...) ném UOE | List fixed-size | new ArrayList<>(Arrays.asList(...)) |
| Collections.unmodifiableList(...).set(...) ném UOE | View chỉ đọc | Nếu sở hữu backing thì sửa nó theo hợp đồng, hoặc tạo bản sao mutable |
| Iterator.remove trên unmodifiable List | Iterator không được quyền thay đổi | Lọc sang danh sách mới, hoặc sửa bản sao mutable |
| Map.of(...).put(...) ném UOE | Map unmodifiable | new HashMap<>(map) nếu cần cập nhật |
| Collections.unmodifiableMap thay đổi khi nguồn sửa | View phản ánh backing | Dùng Map.copyOf(backing) nếu cần snapshot cấu trúc |
| List.copyOf(listCóNull) ném NPE | Factory không chấp nhận null | Chuẩn hóa/loại null hoặc dùng lựa chọn hỗ trợ null |
| Set.of(...) có phần tử trùng ném IllegalArgumentException | Factory yêu cầu đầu vào không trùng | Chọn Set.copyOf khi mong muốn loại trùng, hoặc xử lý dữ liệu trước |

**Không “sửa” bằng cách catch UOE rồi bỏ qua mutator.** Khi chương trình thật sự cần thêm dữ liệu nhưng exception bị nuốt, kết quả nghiệp vụ sẽ thiếu phần tử. Ngược lại, nếu collection cố ý bất biến, chính việc cố gắng sửa nó là lỗi thiết kế ở phía caller.

### Khi cần copy sang mutable

~~~java
// Mảnh mã:
List<String> editableList = new ArrayList<>(readOnlyList);
Map<String, Integer> editableMap = new HashMap<>(readOnlyMap);
Set<String> editableSet = new HashSet<>(readOnlySet);
~~~

Đây là các shallow copy có thể chỉnh sửa cấu trúc. **Không** tự chuyển đổi object phần tử thành immutable. Các constructor cũng có những yêu cầu null/kiểu riêng theo implementation. Nếu dùng Map/Set dựa trên hashing, cần keys có equals/hashCode nhất quán.

## 15. Tình huống thực tế

### 15.1. Trả cấu hình chỉ đọc

Một module cấu hình nhận các chuỗi không null và không muốn module khác sửa danh sách sau khi khởi tạo. List.copyOf(input) là cách hợp lý để tạo một snapshot không sửa được. Đối với String immutable, dữ liệu kết quả thực tế ổn định nếu không có ràng buộc khác.

### 15.2. Hiển thị dữ liệu đang cập nhật

Một phần giao diện nội bộ cần xem danh sách thay đổi trong service và muốn cấm caller sửa qua tham chiếu. Collections.unmodifiableList(backing) có thể hợp lý, **nhưng** cần suy nghĩ về concurrency, snapshot khi duyệt và tính nhất quán giữa các lần đọc.

### 15.3. Tạo request payload rồi bổ sung item

Một pipeline tạo danh sách với Stream.toList() rồi lại gọi add để bổ sung phần tử mặc định sẽ ném UOE. Nếu yêu cầu nghiệp vụ cần chỉnh sửa, hãy thu thập ngay vào ArrayList qua toCollection hoặc khởi tạo bản sao ArrayList trước khi add.

### 15.4. Cấu trúc lồng nhau trong domain model

Map<String, List<Order>> có Map ngoài không sửa được chưa đủ để bảo vệ các List giá trị hoặc các Order mutable. Muốn dữ liệu chỉ đọc đầy đủ, phải chủ động xử lý từng tầng: tạo List snapshot cho từng key, sao chép Order hoặc dùng value object bất biến khi phù hợp, rồi tạo Map snapshot.

### 15.5. Chia sẻ giữa nhiều thread

Không nên dùng một unmodifiable view của một ArrayList đang được cập nhật như một **bản snapshot thread-safe**. Nếu cần nhất quán tại một thời điểm, chụp snapshot dưới đồng bộ hóa thích hợp hoặc dùng mô hình trạng thái bất biến được phát hành an toàn.

## 16. Kiểm thử Collection có giới hạn sửa đổi

Khi code của bạn trả về một Collection dự kiến không sửa được, hãy test:

1. **Nội dung ban đầu**: đủ phần tử, không mất thứ tự nếu List có encounter order.
2. **Mutator chủ yếu**: add, remove, set, clear, iterator.remove, replaceAll/sort nếu áp dụng.
3. **Null và trùng**: factory yêu cầu gì ở đầu vào? Có ném NPE/IllegalArgumentException đúng không?
4. **Backing source**: thay đổi source sau khi tạo có phản ánh ở kết quả không? Hành vi đó có đúng thiết kế API không?
5. **Shallow copy**: sửa object phần tử có thay đổi nội dung quan sát được không? Có chấp nhận không?
6. **Concurrent access**: nếu chia sẻ giữa thread, có snapshot hoặc đồng bộ hóa đúng không?
7. **Không giả định implementation**: không test tên class nội bộ hay object identity của List.of/copyOf.
8. **Phiên bản Java**: kiểm tra đúng JDK mà ứng dụng chạy, nhất là Stream.toList (Java 16+) và List.copyOf (Java 10+).

Với một custom Collection, nhớ rằng **optional mutator** có thể ném hoặc không ném UOE trong một số trường hợp không làm thay đổi dữ liệu; test theo contract của implementation, không áp một giả định chung cho tất cả collection.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** List.of("A").add("B") có biên dịch không? Chạy thế nào?

*Đáp án:* Có thể biên dịch vì List có add. Nhưng object từ List.of không hỗ trợ add, nên lúc chạy ném UnsupportedOperationException.

**Câu 2.** Arrays.asList("A","B").set(0,"C") có bắt buộc ném UOE không?

*Đáp án:* Không. Arrays.asList tạo List fixed-size cho phép thay phần tử cùng vị trí bằng set. Thêm/xóa làm đổi kích thước mới là vấn đề.

**Câu 3.** Gọi Collections.unmodifiableList(backing), sau đó backing.add("X"), view có thấy X không?

*Đáp án:* Có. Đó là unmodifiable **view**, không phải snapshot; nếu source được sửa, query thông qua view phản ánh backing.

**Câu 4.** List.copyOf(backing) có khiến các object phần tử mutable trở thành immutable không?

*Đáp án:* Không. Chỉ tạo snapshot cấu trúc List và chặn sửa qua List. Các object bên trong vẫn có thể đổi trạng thái.

**Câu 5.** Stream.toList có giống Collectors.toList về mutability không?

*Đáp án:* Không. Stream.toList trả List unmodifiable; Collectors.toList không cam kết khả năng sửa. Nếu cần ArrayList mutable, dùng toCollection(ArrayList::new).

**Câu 6.** List.copyOf(collectionCóNull) trả unmodifiable List có null chứ?

*Đáp án:* Không, nó ném NullPointerException. Nếu cần List unmodifiable nhưng chấp nhận null, có thể tạo một bản sao ArrayList rồi bọc Collections.unmodifiableList(copy).

**Câu 7.** addAll(Collections.emptyList()) trên mọi Collection unmodifiable có chắc không ném exception không?

*Đáp án:* Không. Với optional operations của Collection, một số trường hợp no-op có thể ném UOE hoặc không, tùy hợp đồng implementation. Không dùng no-op làm điều kiện đảm bảo an toàn.

**Câu 8.** Collections.unmodifiableList có tự biến truy cập đồng thời vào ArrayList backing thành thread-safe không?

*Đáp án:* Không. Nó cấm sửa qua view, không tự đồng bộ hóa sửa đổi nơi khác vào backing.

**Câu 9.** Nếu Set.of("A","A") thất bại thì exception gì?

*Đáp án:* IllegalArgumentException vì phần tử trùng tại lúc tạo Set; không phải UnsupportedOperationException.

**Câu 10.** Khi một API cần trả dữ liệu không sửa được và không thay đổi cấu trúc sau này, dùng view hay snapshot?

*Đáp án:* Thường dùng snapshot qua List.copyOf hoặc cơ chế sao chép phù hợp, đồng thời kiểm tra vấn đề null và object phần tử mutable.

## 18. Checklist áp dụng trong dự án

Trước khi chọn cách trả hoặc nhận một Collection, hãy tự hỏi:

- **Ai sở hữu dữ liệu?** Có thể trả tham chiếu trực tiếp hay cần defensive copy?
- **Có quyền sửa cấu trúc không?** Người nhận có cần add/remove/set không?
- **Có quyền sửa object phần tử không?** Nếu không, dùng immutable elements/deep copy.
- **Có cần snapshot tại một thời điểm không?** Nếu có, đừng chỉ dùng unmodifiable view trên backing mutable.
- **Có null/trùng không?** List.of, copyOf, Set.of và Map.of có các ràng buộc riêng.
- **Có yêu cầu thứ tự không?** List giữ thứ tự; Set.of/Map.of không cam kết iteration order.
- **Có thao tác trong Stream không?** Phân biệt Stream.toList và Collectors.toList/toCollection.
- **Có đọc/ghi đồng thời không?** Unmodifiable không tương đương đồng bộ hóa.
- **Có phụ thuộc vào tên class nội bộ hoặc tên exception message không?** Hãy dựa vào contract API.
- **Có cần tương thích Java 8 thuần không?** Những factory Java 9+, copyOf Java 10+ và Stream.toList Java 16+ phải được thay thế bằng API phù hợp phiên bản.

## Tài liệu tham khảo chính thức, còn được duy trì

- Oracle Java SE 25 — Collection (optional operations, unmodifiable và view): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html
- Oracle Java SE 25 — List (List.of, List.copyOf): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html
- Oracle Java SE 25 — Collections (unmodifiableList): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html
- Oracle Java SE 25 — Arrays (asList): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html
- Oracle Java SE 25 — Stream.toList: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Oracle Java SE 25 — Collectors: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- Oracle Java SE 25 — Tạo unmodifiable collections: https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html

**Kết luận:** UnsupportedOperationException là phản hồi đúng khi một object Collection không hỗ trợ thao tác thay đổi bạn yêu cầu. Đừng chỉ nhìn kiểu List/Set/Map ở phía trái; hãy biết object đến từ **factory nào**, là **view, snapshot hay fixed-size**, và người gọi cần quyền sửa đến mức nào. Nếu cần sửa, tạo một collection mutable có chủ đích; nếu cần bất biến, bảo vệ cả cấu trúc, tham chiếu tới backing và các object phần tử.
