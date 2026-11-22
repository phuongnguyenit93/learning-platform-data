# Sử dụng bản sao danh sách ở hàm tạo và kiểu trả về với `List.copyOf`

**Chủ đề:** `List.copyOf` — Java 10 trở lên. Bài học hướng dẫn cách dùng `List.copyOf` để bảo vệ trạng thái bên trong đối tượng khi nhận danh sách qua constructor và khi trả danh sách từ phương thức. Trọng tâm là **defensive copying**, sự khác nhau giữa **bản sao không sửa được** và **unmodifiable view**, các giới hạn sao chép nông, cùng cách thiết kế kiểu trả về ổn định.

`List.copyOf(Collection<? extends E>)` có từ Java 10 và tiếp tục được hỗ trợ trong Java hiện đại. Bốn chương trình hoàn chỉnh trong bài sử dụng cú pháp biên dịch được với `javac --release 10`; những quy tắc liên quan đến `var` cũng thuộc Java 10 trở lên.

## 1. Vì sao constructor và getter là hai ranh giới cần bảo vệ?

Khi một lớp nhận `List` từ bên ngoài, có hai hướng mà trạng thái nội bộ có thể bị sửa ngoài ý muốn:

1. **Đầu vào constructor:** caller giữ reference đến danh sách ban đầu, rồi thay đổi nó sau khi đối tượng đã tạo. Nếu constructor lưu thẳng reference, dữ liệu bên trong đối tượng cũng bị ảnh hưởng.
2. **Đầu ra getter:** đối tượng trả thẳng reference đến danh sách mutable bên trong. Caller có thể gọi `add`, `remove`, `clear` hoặc `set` để sửa trạng thái của đối tượng mà không đi qua API kiểm soát của lớp.

Ví dụ **minh họa cách làm dễ lộ trạng thái**, không phải chương trình chạy độc lập:

~~~java
class UnsafeCatalog {
    private final List<String> topics;

    UnsafeCatalog(List<String> topics) {
        this.topics = topics; // chỉ giữ cùng reference, không sao chép
    }

    List<String> topics() {
        return topics; // trả thẳng reference vào trạng thái nội bộ
    }
}
~~~

Dù field có `final`, điều đó **chỉ ngăn việc gán lại field**, không ngăn danh sách mà field trỏ tới bị sửa. Nếu caller gọi `original.add("new")` hoặc `catalog.topics().clear()`, nội dung quan sát qua đối tượng có thể thay đổi.

Khi một lớp cần giữ **ảnh chụp dữ liệu tại lúc khởi tạo** và không cho caller sửa cấu trúc danh sách, `List.copyOf` là một công cụ phù hợp.

## 2. Hợp đồng của `List.copyOf`

Cú pháp:

~~~java
List<String> result = List.copyOf(source);
~~~

Trong đó `source` là một `Collection<? extends String>` thích hợp. Phương thức trả về một `List<String>` có những đặc tính quan trọng:

| Đặc tính | Hành vi |
| --- | --- |
| Khả năng sửa danh sách trả về | **Không cho phép**: `add`, `remove`, `set`, `clear`, `sort`, `replaceAll`... có thể ném `UnsupportedOperationException` |
| Thứ tự và phần tử | Chứa các phần tử theo thứ tự duyệt của nguồn tại lúc sao chép; với `List` đầu vào, thứ tự danh sách được giữ |
| Giá trị `null` | Nguồn `null` hoặc phần tử `null` làm phát sinh `NullPointerException` |
| Phần tử trùng nhau | Vẫn được giữ trong `List`, không tự loại trùng như cấu trúc `Set` |
| Thay đổi cấu trúc nguồn sau đó | Không xuất hiện trong bản sao kết quả theo hợp đồng của `copyOf` |
| Đối tượng phần tử | **Không deep-copy**: vẫn tham chiếu tới các phần tử gốc |
| Kiểu trả về | `List<E>`, nên API nên công bố `List<E>` thay vì phụ thuộc vào lớp triển khai cụ thể |
| Phân bổ bộ nhớ | Có thể tái sử dụng một danh sách không sửa được phù hợp; không được giả định lúc nào cũng cấp phát object mới |

Phần “không thể sửa” nói về **cấu trúc danh sách và các tham chiếu phần tử trong danh sách**. Nó không biến mọi object phần tử thành immutable.

Ví dụ:

~~~java
var source = new ArrayList<>(List.of("A", "B"));
List<String> snapshot = List.copyOf(source);

source.add("C");          // thay đổi source
// snapshot.add("D");     // ném UnsupportedOperationException nếu chạy
System.out.println(snapshot); // [A, B]
~~~

Đây là đoạn đặt trong phương thức, giả sử đã import `ArrayList` và `List`. `snapshot` vẫn giữ hai phần tử ban đầu dù `source` đã thêm phần tử.

**Không dùng `==` để kiểm tra `List.copyOf` có tạo object mới:** việc một input đã là unmodifiable list khiến implementation có thể trả về chính input đó là tối ưu hóa hợp lệ. Điều nên kiểm tra là **hành vi theo hợp đồng**, không phải identity của instance.

## 3. Dùng bản sao trong constructor: chặn aliasing từ đầu vào

Một pattern thường dùng là:

~~~java
public final class Catalog {
    private final List<String> topics;

    public Catalog(Collection<String> submitted) {
        this.topics = List.copyOf(submitted);
    }

    public List<String> topics() {
        return topics;
    }
}
~~~

Đây là **đoạn minh họa định nghĩa class**; ví dụ runnable đầy đủ ở phần sau. Lớp lưu kết quả `List.copyOf(submitted)` nên caller không thể tác động đến cấu trúc `topics` bằng cách tiếp tục sửa `submitted`. Getter trả danh sách không sửa được mà field đã lưu.

Về mặt thiết kế, constructor có thể nhận `Collection<String>` nếu chỉ cần duyệt và sao chép dữ liệu, hoặc `List<String>` nếu ý nghĩa danh sách có thứ tự và hợp đồng API yêu cầu list. `List.copyOf` chấp nhận `Collection<? extends E>`, nên cả hai đều thích hợp khi kiểu generic khớp.

Nếu cần báo lỗi rõ hơn với nguồn `null`, có thể dùng:

~~~java
this.topics = List.copyOf(Objects.requireNonNull(submitted, "submitted"));
~~~

`Objects.requireNonNull` cho thông báo tên tham số; `List.copyOf` cũng không chấp nhận nguồn null. Nếu hợp đồng API muốn chấp nhận null như “không có dữ liệu”, cần xử lý **có chủ đích** trước lúc gọi, chẳng hạn chuyển thành danh sách rỗng, chứ không nên ngầm coi mọi null là hợp lệ.

### Ví dụ chạy được: constructor phòng vệ và getter an toàn

Lưu nguyên chương trình vào **`ConstructorCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

public class ConstructorCopyDemo {
    static final class Catalog {
        private final List<String> topics;

        Catalog(Collection<String> submitted) {
            this.topics = List.copyOf(Objects.requireNonNull(submitted, "submitted"));
        }

        List<String> topics() {
            return topics;
        }
    }

    public static void main(String[] args) {
        var submitted = new ArrayList<>(List.of("var", "copyOf"));
        var catalog = new Catalog(submitted);
        System.out.println("before=" + catalog.topics());

        submitted.add("changed outside");
        System.out.println("after-source=" + catalog.topics());

        try {
            catalog.topics().add("change through getter");
            System.out.println("getter-add=allowed");
        } catch (UnsupportedOperationException expected) {
            System.out.println("getter-add=UnsupportedOperationException");
        }

        var editable = new ArrayList<>(catalog.topics());
        editable.add("local");
        System.out.println("editable=" + editable);
        System.out.println("catalog=" + catalog.topics());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 ConstructorCopyDemo.java
java ConstructorCopyDemo
~~~

**Stdout chính xác:**

~~~text
before=[var, copyOf]
after-source=[var, copyOf]
getter-add=UnsupportedOperationException
editable=[var, copyOf, local]
catalog=[var, copyOf]
~~~

Giải thích:

1. Tại thời điểm gọi constructor, dữ liệu được sao chép thành danh sách không sửa được.
2. Khi caller gọi `submitted.add(...)`, danh sách trong `Catalog` vẫn như lúc khởi tạo.
3. Getter trả một `List<String>` có thể **đọc**, nhưng `add` qua getter ném `UnsupportedOperationException`. Tên method `add` tồn tại trên interface `List`; việc instance hỗ trợ hay từ chối mới quyết định runtime.
4. Caller cần thay đổi cho mục đích riêng thì tạo `new ArrayList<>(catalog.topics())`. Bản sao mutable đó có thể sửa nhưng không sửa `Catalog`.

Trong ứng dụng, một `UnsupportedOperationException` bất ngờ thường là tín hiệu sai hợp đồng. Khối `try/catch` ở ví dụ chỉ nhằm **chứng minh hành vi**, không phải đề xuất bắt rồi bỏ qua lỗi trong nghiệp vụ.

## 4. Kiểu trả về: khai báo `List<T>` và trả trực tiếp bản sao đã lưu

Khi constructor đã lưu `List.copyOf(input)`, trường hợp các phần tử là immutable và class không tự cần sửa nội dung, getter thường nên trả thẳng field:

~~~java
private final List<String> tags;

public List<String> tags() {
    return tags;
}
~~~

Đây là đoạn khai báo **bên trong một class**. Trả thẳng field ở đây an toàn đối với việc thay đổi cấu trúc qua getter, vì chính field đã trỏ đến một danh sách không sửa được. **Không bắt buộc gọi lại `List.copyOf(tags)` trong mỗi getter**; việc sao chép lặp lại không mang thêm bảo đảm phòng vệ cấu trúc trong tình huống này.

Một API nên ưu tiên kiểu trả về **`List<String>`** thay vì phụ thuộc vào `ArrayList<String>` hoặc lớp triển khai nội bộ. Đây là hợp đồng đủ rõ để người gọi biết thứ tự, chỉ số, khả năng duyệt và generic type; tài liệu phương thức nên nói thêm danh sách **không cho phép sửa đổi** vì interface `List` bản thân không bảo đảm điều đó.

Lưu ý:

- `var` chỉ dùng cho **khai báo biến cục bộ**; không thể viết `public var tags()` để suy luận kiểu trả về của phương thức.
- `List.copyOf` trả về một `List<E>`, không hứa là `ArrayList`. Không cast kết quả sang `ArrayList` để sửa.
- `final List<String>` chỉ bảo vệ reference field khỏi bị gán lại; tính không sửa được của dữ liệu trong ví dụ này đến từ **`List.copyOf`**, không đến từ `final`.
- Việc trả thẳng danh sách sau copy vẫn **không bảo vệ trạng thái bên trong object phần tử có thể thay đổi**. Phần 7 minh họa giới hạn này.

## 5. Nếu trạng thái nội bộ cần tiếp tục sửa: snapshot ở phương thức trả về

Không phải class nào cũng có thể lưu một danh sách luôn không sửa được. Ví dụ nhật ký có method `addEntry` cho phép chính đối tượng thay đổi danh sách nội bộ theo quy tắc của nó.

Khi đó, có thể dùng:

~~~java
private final List<String> entries = new ArrayList<>();

public void addEntry(String value) {
    entries.add(value);
}

public List<String> entriesSnapshot() {
    return List.copyOf(entries);
}
~~~

Đây là **các thành viên bên trong một class**. `entries` là danh sách mutable thuộc quyền sở hữu của object; mỗi lần gọi `entriesSnapshot()` tạo ra kết quả chỉ đọc về **trạng thái tại thời điểm gọi**. Caller không sửa được kết quả, và các lần thêm tiếp theo vào `entries` không xuất hiện trong snapshot cũ.

### Ví dụ chạy được: getter chụp ảnh dữ liệu theo thời điểm

Lưu **`SnapshotGetterDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SnapshotGetterDemo {
    static final class Journal {
        private final List<String> entries = new ArrayList<>();

        void addEntry(String item) {
            entries.add(item);
        }

        List<String> entriesSnapshot() {
            return List.copyOf(entries);
        }
    }

    public static void main(String[] args) {
        var journal = new Journal();
        journal.addEntry("A");
        var first = journal.entriesSnapshot();

        journal.addEntry("B");
        var second = journal.entriesSnapshot();

        System.out.println("snapshot1=" + first);
        System.out.println("snapshot2=" + second);

        try {
            first.add("X");
            System.out.println("snapshot1-add=allowed");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot1-add=UnsupportedOperationException");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 10 SnapshotGetterDemo.java
java SnapshotGetterDemo
~~~

Stdout:

~~~text
snapshot1=[A]
snapshot2=[A, B]
snapshot1-add=UnsupportedOperationException
~~~

`first` là snapshot cũ; `second` chứa thêm `B` sau khi object thay đổi trạng thái. Cả hai đều không cho caller sửa thông qua reference trả về. Đặt tên `entriesSnapshot` giúp người dùng API hiểu rằng kết quả **không tự cập nhật theo các lần thay đổi sau**.

**Chi phí:** với danh sách mutable và cách sử dụng thông thường, snapshot cần duyệt/sao chép số phần tử tương ứng, nên việc gọi getter trong vòng lặp dày đặc có thể tạo chi phí lặp. Khi điều kiện cho phép, lấy một snapshot rồi xử lý nó; hoặc thiết kế đối tượng với dữ liệu cố định từ constructor để trả trực tiếp field. Không nên cache snapshot mãi nếu nội bộ còn thay đổi mà không cập nhật cache.

**Lưu ý đa luồng:** `List.copyOf` tự nó không biến quá trình đọc một source đang bị sửa đồng thời thành thao tác snapshot nguyên tử, và không tự mang lại thread-safety cho collection nguồn. Khi có nhiều luồng, dùng chiến lược đồng bộ/sở hữu dữ liệu phù hợp trước khi lấy snapshot.

## 6. Phân biệt `List.copyOf` với `Collections.unmodifiableList`

Một cách khác để trả danh sách không sửa được là `Collections.unmodifiableList(source)`. Cả hai đều từ chối `add` qua kết quả, nhưng ý nghĩa khi **source còn mutable** rất khác nhau.

| Tiêu chí | `List.copyOf(source)` | `Collections.unmodifiableList(source)` |
| --- | --- | --- |
| Kết quả có cho phép thêm/xóa/sửa qua reference trả về? | Không | Không |
| Có phản ánh việc source bị sửa sau đó? | Không, theo hợp đồng sao chép | **Có thể có**, vì là view bọc backing list |
| Có chấp nhận null trong source? | Không | Wrapper có thể phản ánh null từ source nếu backing list cho phép |
| Có tạo object mới mỗi lần không? | Không được bảo đảm; nguồn đã unmodifiable có thể được tái sử dụng | Thường tạo wrapper view; quan trọng là ngữ nghĩa view |
| Dùng khi nào? | Cần ảnh chụp cấu trúc ổn định | Cần cho phép đọc trạng thái hiện tại qua view nhưng không được sửa qua view |

`Collections.unmodifiableList` **không hề sao chép** dữ liệu trong source; nếu source bị đổi ở nơi khác, người đọc view có thể thấy thay đổi đó. Với API trả snapshot, đây là rủi ro nếu caller kỳ vọng kết quả giữ nguyên.

### Ví dụ chạy được: view sống và bản sao

Lưu **`ViewVersusCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVersusCopyDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> copy = List.copyOf(source);

        source.set(0, "Z");
        source.add("C");
        System.out.println("view=" + view);
        System.out.println("copy=" + copy);

        List<String> copyOfView = List.copyOf(view);
        source.add("D");
        System.out.println("view-later=" + view);
        System.out.println("copy-of-view=" + copyOfView);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 ViewVersusCopyDemo.java
java ViewVersusCopyDemo
~~~

Kết quả:

~~~text
view=[Z, B, C]
copy=[A, B]
view-later=[Z, B, C, D]
copy-of-view=[Z, B, C]
~~~

`view` phản ánh thay đổi từ `source`. `copy` giữ dữ liệu ban đầu. Trong ví dụ này, `List.copyOf(view)` tạo kết quả độc lập với các lần sửa backing list tiếp theo nên `copyOfView` không xuất hiện `D`.

Không nên dựa vào lớp implementation cụ thể hoặc so sánh `==` để quyết định snapshot/view. Hãy dựa vào hợp đồng của `List.copyOf` và `Collections.unmodifiableList`, cũng như việc **còn đường nào khác sửa được backing list hay không**.

## 7. Giới hạn quan trọng: `List.copyOf` là sao chép nông

Giả sử danh sách chứa các đối tượng có phương thức thay đổi trạng thái:

~~~java
var note = new MutableNote("draft");
var source = new ArrayList<MutableNote>();
source.add(note);
var snapshot = List.copyOf(source);

note.rename("published");       // sửa chính object phần tử
// snapshot.get(0).text() có thể quan sát "published"
~~~

Đây là **đoạn minh họa**, các class sẽ được định nghĩa đầy đủ trong chương trình dưới. `List.copyOf` làm cho người gọi không thể thêm/xóa/thay **tham chiếu trong list**, nhưng vẫn giữ tham chiếu tới chính `note`. Nếu caller nắm tham chiếu khác tới object, trạng thái phần tử có thể thay đổi.

### Ví dụ chạy được: sao chép nông và lấy giá trị immutable

Lưu **`ShallowCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;

public class ShallowCopyDemo {
    static final class Note {
        private String value;

        Note(String value) {
            this.value = value;
        }

        void rename(String next) {
            this.value = next;
        }

        String text() {
            return value;
        }
    }

    static final class NoteHolder {
        private final List<Note> notes;

        NoteHolder(Collection<Note> source) {
            this.notes = List.copyOf(source);
        }

        List<Note> notes() {
            return notes;
        }
    }

    static final class FrozenNames {
        private final List<String> names;

        FrozenNames(Collection<Note> source) {
            var items = new ArrayList<String>();
            for (var note : source) {
                items.add(note.text());
            }
            this.names = List.copyOf(items);
        }

        List<String> names() {
            return names;
        }
    }

    public static void main(String[] args) {
        var note = new Note("draft");
        var input = new ArrayList<Note>();
        input.add(note);

        var holder = new NoteHolder(input);
        var frozen = new FrozenNames(input);

        input.clear();
        note.rename("published");

        System.out.println("holder-size=" + holder.notes().size());
        System.out.println("mutable-element=" + holder.notes().get(0).text());
        System.out.println("frozen-values=" + frozen.names());

        try {
            List.copyOf(Arrays.asList("A", null));
            System.out.println("null-copy=allowed");
        } catch (NullPointerException expected) {
            System.out.println("null-copy=NullPointerException");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 10 ShallowCopyDemo.java
java ShallowCopyDemo
~~~

Stdout chính xác:

~~~text
holder-size=1
mutable-element=published
frozen-values=[draft]
null-copy=NullPointerException
~~~

Giải thích:

- `NoteHolder` giữ bản sao cấu trúc; `input.clear()` không làm `holder.notes()` mất phần tử.
- `NoteHolder` vẫn tham chiếu cùng `Note`. Khi gọi `note.rename("published")`, giá trị quan sát qua `holder.notes().get(0)` cũng đổi.
- `FrozenNames` chuyển từ các object mutable thành **`String` bất biến** tại thời điểm tạo, rồi mới gọi `List.copyOf`. Nó giữ `[draft]` bất chấp đổi tên `Note` sau đó.
- `List.copyOf` từ chối phần tử `null` bằng `NullPointerException`, được bắt riêng để minh họa.

Nếu mục tiêu là bảo vệ **toàn bộ trạng thái sâu**, cần thiết kế element immutable, hoặc sao chép mỗi element sang một kiểu giá trị immutable phù hợp. Chẳng hạn trong Java hiện đại có thể dùng record với các thành phần immutable; tuy nhiên record có field tham chiếu mutable thì vẫn cần defensive copy tương ứng. Chỉ dùng `List.copyOf` ở lớp ngoài chưa đủ để khẳng định deep immutability.

## 8. Chọn chiến lược cho constructor và phương thức trả về

Ba thiết kế thường gặp:

### Thiết kế A — Value object có danh sách cố định sau constructor

~~~java
public final class Permissions {
    private final List<String> allowedActions;

    public Permissions(Collection<String> actions) {
        this.allowedActions = List.copyOf(actions);
    }

    public List<String> allowedActions() {
        return allowedActions;
    }
}
~~~

Đây là một **định nghĩa lớp độc lập** nhưng không có `main`; cần import `Collection` và `List` nếu lưu thành tệp. Danh sách chỉ được thiết lập lúc tạo, nên sao chép một lần ở constructor và trả trực tiếp nó qua getter. Với `String` immutable, đây là cách đơn giản để giữ tập dữ liệu có thứ tự ổn định.

### Thiết kế B — Aggregate có state mutable nhưng getter trả snapshot

~~~java
private final List<String> events = new ArrayList<>();

public void append(String event) {
    events.add(event);
}

public List<String> eventsSnapshot() {
    return List.copyOf(events);
}
~~~

Đây là **đoạn thành viên trong lớp**, không chạy độc lập. Lớp có thể thêm sự kiện qua method của chính nó, nhưng không cho caller sửa danh sách nội bộ. Snapshot cũ độc lập với thay đổi cấu trúc về sau.

### Thiết kế C — Cố ý trả live unmodifiable view

~~~java
private final List<String> events = new ArrayList<>();
private final List<String> readOnlyView =
        Collections.unmodifiableList(events);

public List<String> liveEventsView() {
    return readOnlyView;
}
~~~

Đây là **đoạn thành viên trong lớp**, không chạy độc lập. Caller không sửa qua view, nhưng khi lớp sửa `events` thì view thay đổi theo. Chỉ chọn cách này nếu hợp đồng API **cần live view** và caller hiểu các thay đổi có thể xuất hiện trong quá trình sử dụng. Không mô tả nó là “snapshot”.

**Quyết định thực tế:** nếu bên trong không cần sửa, dùng Thiết kế A. Nếu lớp cần sửa mà người gọi chỉ nên nhìn ảnh chụp, dùng B. Nếu thực sự cần quan sát thay đổi theo thời gian qua một reference chỉ đọc, xem xét C và quy định rõ vấn đề concurrency, iterator và vòng đời backing list.

## 9. Tại sao kiểu trả về vẫn nên là `List<T>`?

`List.copyOf` trả về kiểu giao diện `List<E>`. Một API có chữ ký:

~~~java
public List<String> topics()
~~~

nêu rõ người gọi có thể duyệt theo thứ tự, truy cập bằng chỉ số và nhận phần tử kiểu `String`; nó giữ cho implementation chi tiết riêng tư. Để người gọi không lầm tưởng có thể sửa, hãy đặt tên phù hợp (`snapshot` nếu là snapshot) hoặc ghi rõ trong tài liệu:

> Returns an unmodifiable list snapshot. Modifying methods throw `UnsupportedOperationException`.

Đây là **ví dụ chú thích hợp đồng**, không cần nhúng chữ `var` ở kiểu trả về. Trong Java, từ khóa `var` không hợp lệ ở vị trí return type của method.

Trong một số API, `Collection<T>` hoặc `Iterable<T>` có thể là kiểu trả về phù hợp hơn nếu người gọi không cần thứ tự/chỉ số. Nhưng khi đã cố ý cam kết một **danh sách có thứ tự**, `List<T>` diễn đạt rõ hơn. Việc chọn interface không tự tạo tính bất biến: tính không sửa được đến từ object `List.copyOf(...)` hoặc cơ chế tương đương.

### Điều gì sẽ xảy ra nếu caller cần sửa kết quả?

Cho caller tạo một danh sách mutable mới:

~~~java
List<String> editable = new ArrayList<>(catalog.topics());
editable.add("extra"); // sửa được bản sao cục bộ, không sửa Catalog
~~~

Không cung cấp một getter mutable chỉ để tiện cho một caller cần thêm phần tử nếu điều đó phá vỡ invariant hoặc quyền sở hữu dữ liệu. Nếu thực sự muốn sửa state trong object, hãy tạo phương thức nghiệp vụ như `catalog.addTopic(...)` để kiểm soát validation, quyền và tính nhất quán.

## 10. Những giới hạn và lỗi thường gặp

| Trường hợp | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Constructor chỉ viết `this.items = incoming;` | Giữ reference mutable từ caller, tạo alias | Dùng `List.copyOf(incoming)` khi cần snapshot không sửa được |
| Getter trả thẳng field `ArrayList` mutable | Caller có thể `clear`/`add` trực tiếp, phá vỡ invariant | Trả `List.copyOf(items)` hoặc lưu list không sửa được từ đầu |
| Lưu `Collections.unmodifiableList(incoming)` để “sao chép” | Đây là view; caller vẫn sửa được `incoming` và làm dữ liệu thay đổi | Dùng `List.copyOf(incoming)` nếu muốn tách khỏi backing source |
| Gọi `List.copyOf` trong mỗi getter dù field đã là kết quả `copyOf` | Có thể không cần thiết về ngữ nghĩa; gây nhầm lẫn mục tiêu bảo vệ | Trả trực tiếp field unmodifiable, với điều kiện phần tử và hợp đồng phù hợp |
| Cho `null` vào `List.copyOf` | Ném `NullPointerException` | Validate từ boundary, loại bỏ hoặc chuyển đổi null theo yêu cầu domain |
| Cho danh sách chứa object mutable rồi khẳng định “deep immutable” | Caller hoặc source vẫn đổi trạng thái các element | Chọn element immutable hoặc sao chép nội dung từng element |
| Cast kết quả `List.copyOf` sang `ArrayList` | Không bảo đảm concrete type; có thể `ClassCastException` | Dùng `List<T>`; cần sửa thì `new ArrayList<>(result)` |
| Dùng `==` để chắc chắn đã có bản sao vật lý | `copyOf` có thể tái sử dụng unmodifiable input | Kiểm tra hợp đồng dữ liệu thay vì identity |
| Kỳ vọng `copyOf` giải quyết đồng bộ hóa | Không biến truy cập source concurrent thành snapshot nguyên tử | Sở hữu/đồng bộ hóa dữ liệu trước khi sao chép |
| Trả snapshot nhưng đặt tên/tài liệu là live view | Caller hiểu sai về các thay đổi sau khi gọi | Đặt tên hoặc hợp đồng rõ là snapshot hay view |

`List.copyOf` cũng không tự kiểm tra quy tắc nghiệp vụ như phần tử rỗng, trùng tên hoặc thứ tự ưu tiên. Ví dụ danh sách quyền không được chứa chuỗi trống? Hãy validate đầu vào ở constructor, rồi sao chép. Nếu cần kiểm tra null phần tử để đưa ra lỗi chi tiết hơn, thực hiện validation riêng; `List.copyOf` chỉ bảo đảm từ chối null theo hợp đồng của chính nó.

## 11. Gợi ý kiểm thử cho API dùng `List.copyOf`

Với một class nhận `List<T>` ở constructor, nên có các kiểm thử **khác nhau về mục đích**:

1. **Constructor chống aliasing:** sau khi tạo object, sửa danh sách nguồn bằng `add`, `remove` hoặc `set`; state trong object phải không đổi.
2. **Getter ngăn sửa cấu trúc:** thử `add`, `set`, `remove` qua kết quả và kiểm tra `UnsupportedOperationException` khi phương thức không hỗ trợ.
3. **Snapshot theo thời điểm:** nếu object tự thay đổi state, getter snapshot cũ phải giữ nội dung cũ; getter mới có dữ liệu mới.
4. **Phần tử mutable:** nếu domain yêu cầu bất biến sâu, sửa object phần tử gốc rồi kiểm tra dữ liệu trả về không đổi; nếu kết quả đổi, phải bổ sung element-copy.
5. **Đầu vào không hợp lệ:** kiểm tra null source/null element và business validation, không nhầm `NullPointerException` với `UnsupportedOperationException`.
6. **Hợp đồng typed API:** signature nên thể hiện đúng `List<T>`, và client không nên phụ thuộc vào implementation class.

Khi chỉ cần chứng minh một getter không lộ mutable list, thử cả đường sửa từ **source ban đầu** và từ **getter trả về**. Chỉ kiểm tra getter ném `UnsupportedOperationException` là chưa đủ: một unmodifiable view vẫn có thể bị tác động từ source bên ngoài.

## 12. Câu hỏi tự kiểm tra

1. Với `this.names = names;` trong constructor, caller còn giữ `names` và gọi `names.clear()`, điều gì có thể xảy ra?
2. Với `this.names = List.copyOf(names);`, gọi `names.clear()` sau constructor còn sửa được danh sách của object không?
3. Getter trả `List.copyOf(internal)` có gì khác getter trả `Collections.unmodifiableList(internal)` khi `internal` vẫn được object sửa tiếp?
4. Khi field đã được lưu bằng `List.copyOf` và chỉ chứa `String`, getter có bắt buộc gọi `copyOf` lần nữa không?
5. Vì sao `List.copyOf(List<MutableNote>)` không thể bảo đảm nội dung các `MutableNote` không thay đổi?
6. Vì sao `final List<T> items` chưa đủ để chặn `items.add(...)`?
7. Mức Java nào hỗ trợ `List.copyOf`? Có thể dùng `var` làm kiểu trả về của method không?
8. Khi caller muốn sửa bản sao từ getter, cách tạo `ArrayList` nào an toàn?

**Đáp án:** (1) cùng reference có thể khiến object mất dữ liệu; (2) không, bản sao `List.copyOf` tách khỏi thay đổi cấu trúc nguồn; (3) `copyOf` cho snapshot, unmodifiable wrapper cho live view; (4) không, trả trực tiếp field đã unmodifiable là đủ về mặt bảo vệ cấu trúc; (5) sao chép nông giữ reference phần tử; (6) `final` bảo vệ biến field chứ không làm object bất biến; (7) Java 10+, và `var` không hợp lệ làm return type; (8) `new ArrayList<>(getterResult)`.

## 13. Tài liệu API còn áp dụng hiện nay

- **`List.copyOf` và hợp đồng Unmodifiable Lists:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- **`Collections.unmodifiableList`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)
- **`ArrayList`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html
- **`Objects.requireNonNull`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)
- **JEP 286 — Local-Variable Type Inference (Java 10):** https://openjdk.org/jeps/286

**Ghi nhớ:** Sao chép tại constructor khi muốn ngăn dữ liệu đầu vào bị sửa ngoài ý muốn; trả trực tiếp `List` đã unmodifiable nếu trạng thái thực sự cố định; trả `List.copyOf` ở getter khi cần snapshot của state mutable; và luôn xét tính mutable của **từng phần tử** nếu yêu cầu bất biến vượt quá cấu trúc danh sách.