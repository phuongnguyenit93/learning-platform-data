# `List.copyOf`: Khả năng tái sử dụng một danh sách nguồn phù hợp (Java 10+)

## 1. Vấn đề: `copyOf` có bắt buộc tạo một object mới không?

Từ **Java 10**, `java.util.List.copyOf(Collection<? extends E> coll)` tạo một danh sách **không thể sửa qua API List** (*unmodifiable list*) chứa các phần tử của collection nguồn theo **thứ tự duyệt** của nguồn. Đây là API vẫn được hỗ trợ trong các bản Java hiện hành.

Một cách viết điển hình:

```java
var source = java.util.List.of("Java", "Kotlin");
var result = java.util.List.copyOf(source);
```

`source` vốn đã là danh sách không sửa được, vì được tạo bởi `List.of`. **`List.copyOf` được phép tái sử dụng một danh sách nguồn phù hợp**, thay vì cấp phát và sao chép một cấu trúc mới không cần thiết.

Điều này thường dẫn đến hai câu hỏi:

1. “`result` có phải chính là `source` không?” — **Không có bảo đảm về định danh tham chiếu**. Một triển khai có thể tái sử dụng, triển khai khác có thể tạo object mới. Đừng dựa vào `==` để viết logic.
2. “Nếu nguồn là danh sách có thể thay đổi thì sao?” — Kết quả `List.copyOf` vẫn phải **không phản ánh các thay đổi cấu trúc của nguồn sau đó**. Vì vậy không được nhầm nó với một *unmodifiable view* đang được backing bởi danh sách có thể thay đổi.

**Hợp đồng cần nhớ:** `List.copyOf` bảo đảm một kết quả không sửa được với các phần tử phù hợp; nó **không hứa một lần cấp phát object mới**, không hứa cùng identity với nguồn, và không sao chép sâu từng phần tử.

### Vì sao có quyền tái sử dụng?

Nếu danh sách nguồn đã không thể bị thay đổi theo đúng hợp đồng cần thiết, việc tạo một bản sao cấu trúc chỉ để trả lại cùng các phần tử có thể là công việc thừa. Tài liệu API Java SE 26 nêu trong *Implementation Note* của `List.copyOf` rằng, khi collection đầu vào là một unmodifiable List, thao tác `copyOf` **thông thường sẽ không tạo bản sao**.

Chú ý phân biệt từ **“thông thường”** với **“luôn luôn”**: đây là một ghi chú về cách triển khai có thể tối ưu, **không phải lời bảo đảm identity** trong API. Lập trình viên cần dựa trên nội dung và hành vi, không suy đoán cách JDK phân bổ bộ nhớ.

## 2. Hợp đồng chính xác của `List.copyOf`

Chữ ký API, viết gọn:

```java
static <E> List<E> copyOf(Collection<? extends E> coll)
```

Ý nghĩa:

- Đầu vào là `Collection<? extends E>`, nên **không bắt buộc phải là `List`**. Có thể tạo một List từ Set hoặc một loại Collection khác.
- Kết quả là `List<E>` chứa các phần tử theo **thứ tự iterator của collection đầu vào** tại thời điểm tạo.
- Kết quả là **unmodifiable**: không thể thêm, xóa, thay thế phần tử thông qua API List của kết quả; những mutator tương ứng ném `UnsupportedOperationException`.
- Nếu collection đầu vào được thay đổi **sau khi tạo bản sao**, kết quả không phản ánh sự thay đổi đó.
- Collection đầu vào **không được là `null`** và **không được chứa phần tử `null`**: nếu vi phạm, `copyOf` ném `NullPointerException`.
- Kiểu tham số `E` là generic, được trình biên dịch suy luận từ ngữ cảnh và kiểu phần tử của đầu vào; `var` vẫn nhận kiểu tĩnh đầy đủ như `List<String>`.

Trong các bảo đảm trên **không có** yêu cầu “mỗi lần gọi trả về một object hoàn toàn mới”. Cũng không có yêu cầu phải trả về lớp triển khai như `ArrayList` hoặc một tên lớp nội bộ cụ thể.

### So sánh các trường hợp nguồn

| Nguồn truyền vào `List.copyOf` | Tính chất nguồn | Điều có thể tin cậy về kết quả |
| --- | --- | --- |
| `List.of("A", "B")` | Danh sách không sửa được và không có `null` | Kết quả có `["A", "B"]`, không sửa được; **có thể tái sử dụng nguồn**, identity không được bảo đảm |
| `List.copyOf(other)` | Bản thân đã không sửa được, không `null` | Copy tiếp thường không cần cấp phát lại; chỉ tin vào nội dung/hợp đồng |
| `new ArrayList<>(List.of("A","B"))` | Danh sách có thể thêm, xóa, thay thế | Kết quả không phản ánh các sửa đổi cấu trúc sau đó; không được coi là view nguồn |
| `Collections.unmodifiableList(mutable)` | **View không sửa được** nhưng backing list vẫn có thể bị sửa | Kết quả của `copyOf` phải độc lập trước những sửa đổi cấu trúc tiếp theo của backing list |
| `LinkedHashSet` có thứ tự duyệt | Collection không phải List | Kết quả List giữ thứ tự duyệt của set tại thời điểm copy; không được dựa vào kiểu triển khai cụ thể |
| Collection chứa `null` | Không hợp lệ với `List.copyOf` | `NullPointerException`; không có kết quả hợp lệ |

**Điểm quan trọng:** câu “unmodifiable List thì thường tái sử dụng” không có nghĩa ta được phép bỏ qua phần backing có thể thay đổi của một wrapper, hoặc áp dụng máy móc cho **mọi** class tự triển khai `List`.

## 3. Trường hợp nguồn phù hợp: `List.of` và kết quả `copyOf`

### 3.1. Danh sách được tạo bởi `List.of`

```java
var original = java.util.List.of("A", "B");
var again = java.util.List.copyOf(original);

System.out.println(again);                 // [A, B]
System.out.println(original.equals(again)); // true
```

Giải thích:

- `List.of` từ Java 9 tạo danh sách không sửa được, không cho `null`.
- `List.copyOf` có từ Java 10; nhận nguồn đã phù hợp này và có thể trả lại cùng một object.
- Dù JDK hiện tại thực tế tái sử dụng hay không, **`equals` phải trả về `true`** vì nội dung và thứ tự phần tử giống nhau.
- Kết quả không cho `add` hoặc `set`, kể cả khi được tái sử dụng.

Cách viết **không nên dùng để khẳng định hành vi API**:

```java
var original = java.util.List.of("A", "B");
var again = java.util.List.copyOf(original);

// Không dùng điều kiện này để xác nhận copy thành công:
// if (again == original) { ... }

// Cũng không được giả định luôn đúng:
// if (again != original) { ... }
```

`==` so sánh **identity tham chiếu**, không phải nội dung. Nó là biểu thức Java hợp lệ, nhưng việc nhận được `true` hay `false` trên một runtime cụ thể **không đại diện cho một bảo đảm API**.

### 3.2. Sao chép nhiều lần có làm biến đổi nội dung không?

```java
var first = java.util.List.of("A", "B");
var second = java.util.List.copyOf(first);
var third = java.util.List.copyOf(second);

System.out.println(first.equals(second)); // true
System.out.println(second.equals(third)); // true
```

Các lần sao chép liên tiếp giữ cùng nội dung. Về mặt **giá trị**, thao tác giống một lần lặp lại không làm đổi kết quả; về mặt **định danh và cấp phát**, tài liệu không buộc `first`, `second` và `third` là cùng một object hay ba object khác nhau.

Vì vậy, không tạo test kiểu “`copyOf(copyOf(x))` phải trả cùng reference với `copyOf(x)`”. Hãy kiểm thử đúng **hành vi công khai**.

## 4. Nguồn có thể sửa: `List.copyOf` phải giữ một snapshot cấu trúc

Xem trường hợp nguồn `ArrayList`:

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B")
);
var snapshot = java.util.List.copyOf(source);

source.add("C");

System.out.println(source);   // [A, B, C]
System.out.println(snapshot); // [A, B]
```

`snapshot` là kết quả không sửa được chứa hai phần tử của nguồn tại thời điểm copy. Dù `source` có thể được sửa sau đó, `snapshot` không thể đột nhiên có thêm `"C"`.

Điều này giải thích **ranh giới của tối ưu tái sử dụng**: `copyOf` không thể trả về một alias cho danh sách mutable mà việc thay đổi nguồn về sau khiến kết quả thay đổi, vì như vậy vi phạm hợp đồng của `copyOf`.

### Không nhầm snapshot với unmodifiable view

`Collections.unmodifiableList` có một vai trò khác: nó trả về **view không sửa được** của một List, nhưng view vẫn được **backing** bởi danh sách gốc.

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("A", "B")
);
var view = java.util.Collections.unmodifiableList(source);
var snapshot = java.util.List.copyOf(view);

source.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
```

Cả `view.add(...)` và `snapshot.add(...)` đều bị từ chối, nhưng:

- `view` hiển thị `C` vì backing `source` đã thay đổi.
- `snapshot` **không** hiển thị `C`; `copyOf` phải bảo toàn hành vi độc lập với sửa đổi cấu trúc nguồn sau đó.

Vì vậy, đừng viết quy tắc sai là **“hễ object nguồn từ chối add thì `copyOf` chắc chắn trả lại cùng tham chiếu”**. Một unmodifiable view có thể bị thay đổi nội dung gián tiếp; điều này khác với một danh sách vốn không có backing mutable được phép thay đổi.

## 5. Tái sử dụng object khác với sao chép sâu phần tử

Giả sử các phần tử của danh sách là object mutable:

```java
class Note {
    String text;
    Note(String text) {
        this.text = text;
    }
}
```

Nếu có một object `Note` được lưu trong danh sách:

```java
var note = new Note("old");
var source = java.util.List.of(note);
var result = java.util.List.copyOf(source);

note.text = "new";

System.out.println(result.get(0).text); // new
```

Hai đoạn mã trên là **minh họa phải đặt trong ngữ cảnh Java hợp lệ** (ví dụ `Note` được khai báo trong lớp, các lệnh ở trong phương thức); chương trình độc lập đầy đủ ở phần 9.

`List.copyOf` **không thực hiện deep copy**. Nó giữ các **tham chiếu phần tử**, chứ không tự tạo clone cho mỗi `Note`. Vì vậy:

- Kết quả không cho thay thế phần tử tại vị trí bằng `set`.
- Nhưng nếu có tham chiếu đến object phần tử và object đó cho phép thay đổi trạng thái, trạng thái mới vẫn quan sát được qua kết quả.
- Dù `copyOf` **có tạo cấu trúc mới**, điều đó cũng **không** đồng nghĩa phần tử được nhân bản.
- Tối ưu tái sử dụng cả object List (nếu nguồn phù hợp) là một vấn đề khác với việc chia sẻ reference của các **phần tử**.

Khi cần một snapshot **bất biến sâu về mặt nghiệp vụ**, hãy dùng phần tử bất biến hoặc chuyển từng phần tử thành một đại diện bất biến; `List.copyOf` một mình không bảo đảm điều đó.

## 6. Kết quả là value-based: không dựa vào identity

Các danh sách do `List.of` và `List.copyOf` tạo ra là **value-based instances** theo tài liệu `List` hiện hành. Điều này cho phép nhà triển khai tạo mới hoặc tái sử dụng một instance tùy ý.

Những cách làm phù hợp:

```java
var a = java.util.List.of("Java", "Kotlin");
var b = java.util.List.copyOf(a);

boolean sameValues = a.equals(b); // true
int count = b.size();             // 2
String first = b.get(0);          // "Java"
```

Những giả định **không an toàn**:

- Dùng `a == b` hoặc `a != b` như hợp đồng để kiểm tra `copyOf` đã hoạt động hay đã tạo bộ nhớ mới.
- Dựa vào `System.identityHashCode(b)` để suy ra cache, tính duy nhất hay số lần cấp phát.
- Sử dụng một instance value-based làm monitor khóa trong `synchronized (b)`. Tài liệu cảnh báo không dùng value-based objects cho đồng bộ, vì hành vi có thể không đoán trước.
- Ép kiểu kết quả sang một lớp nội bộ hay so sánh `b.getClass().getName()` với tên triển khai cụ thể.

**Đúng mục đích:** `equals` và `hashCode` để so sánh nội dung, cùng `List` interface và các method chuẩn để truy cập dữ liệu. Lớp nội bộ, identity và cơ chế tối ưu không thuộc hợp đồng mà ứng dụng nên bám vào.

Nếu thật sự cần một đối tượng khác có identity do ứng dụng kiểm soát, hãy xây dựng object riêng với vòng đời và quy ước rõ ràng; **đừng dựa vào `List.copyOf` để buộc tạo một tham chiếu mới**.

## 7. Điều kiện của một nguồn “phù hợp” và những ranh giới cần biết

### 7.1. Nguồn phải không có `null`

```java
// java.util.List.copyOf(null); // Ném NullPointerException

var source = java.util.Arrays.asList("A", null);
// var result = java.util.List.copyOf(source); // Ném NullPointerException
```

Không nên cho rằng “nguồn không sửa được” sẽ vượt qua quy tắc `null`. Một số wrapper hoặc loại List khác có thể không cho sửa qua reference nhưng vẫn chứa `null`; `List.copyOf` vẫn phải áp dụng hợp đồng không chứa `null`.

### 7.2. Không được suy luận từ tên class hoặc interface

Ngay cả khi một object có kiểu tĩnh `List<String>` và không hỗ trợ `add`, lập trình viên vẫn không thể kết luận rằng Java **bắt buộc** trả lại cùng object từ `copyOf`. Quyền tối ưu là chi tiết của triển khai phù hợp với hợp đồng, không phải một phép kiểm tra dựa trên tên class.

Không có yêu cầu rằng output phải là `ArrayList`, `LinkedList`, hay class nội bộ cụ thể. **Kiểu tĩnh** của `List.copyOf` là `List<E>`.

### 7.3. Thứ tự của kết quả đến từ iterator nguồn

```java
var orderedSet = new java.util.LinkedHashSet<>(
        java.util.List.of("Z", "A")
);
var list = java.util.List.copyOf(orderedSet);

System.out.println(list); // [Z, A]
```

`LinkedHashSet` bảo đảm thứ tự duyệt theo thứ tự thêm trong trường hợp minh họa này, nên `List.copyOf` giữ thứ tự đó.

Với một Set **không có bảo đảm thứ tự**, ví dụ `Set.of("Z", "A")`, `List.copyOf` sẽ lấy theo **thứ tự iterator tại thời điểm sao chép**, nhưng **không được hứa** kết quả luôn là `["Z", "A"]`. Nếu ứng dụng cần thứ tự cố định, sắp xếp hoặc dùng nguồn có thứ tự được đặc tả rõ.

### 7.4. Không phải phép sao chụp đồng bộ xuyên luồng

`List.copyOf` không phải công cụ thực hiện một **atomic snapshot** của một collection đang bị luồng khác sửa đồng thời. Nếu dữ liệu nguồn có thể thay đổi trong khi copy, phải áp dụng quy tắc đồng bộ/thiết kế concurrency của nguồn, hoặc xây dựng một snapshot ổn định trước.

Hợp đồng “thay đổi nguồn **sau khi** tạo kết quả không ảnh hưởng kết quả” không có nghĩa “vừa đọc vừa bị sửa cũng tự động an toàn”. Đây là hai thời điểm khác nhau.

## 8. `var` và kiểu generic trong kết quả `List.copyOf`

`List.copyOf` trả về một `List<E>`; dùng `var` không biến nó thành kiểu động hay kiểu nội bộ của JDK.

```java
var source = java.util.List.of("Java", "Kotlin"); // List<String>
var copied = java.util.List.copyOf(source);       // List<String>
```

Trình biên dịch suy luận `E = String` từ `source`; `var copied` có kiểu tĩnh `List<String>`. Do đó:

```java
String first = copied.get(0); // Hợp lệ, first là "Java"
// copied.add(42);            // Sai kiểu generic tại compile time
// copied.add("C");           // Biên dịch được, nhưng chạy sẽ ném UnsupportedOperationException
```

Ở dòng `copied.add(42)`, Java bác bỏ vì `42` không phù hợp với `String`; ở dòng `copied.add("C")`, Java vẫn cho biên dịch vì phương thức `List.add` có trong interface, nhưng collection kết quả là unmodifiable nên thao tác khi chạy thất bại.

**Phân biệt compile-time với runtime:** generic kiểm tra **kiểu phần tử**, còn hợp đồng unmodifiable giới hạn **khả năng thay đổi**. Tối ưu tái sử dụng instance không tác động đến hai quy tắc này.

## 9. Ví dụ Java 17+ hoàn chỉnh

Lưu mã sau trong tệp **`ListCopyReuseDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;

public class ListCopyReuseDemo {
    static final class Note {
        String text;

        Note(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        // Nguồn đã không sửa được: copyOf có thể tái sử dụng.
        var source = List.of("Java", "Kotlin");
        var copied = List.copyOf(source);
        System.out.println("sameContent=" + copied.equals(source));

        // View không sửa được nhưng backing vẫn mutable.
        var mutable = new ArrayList<>(List.of("A", "B"));
        var view = Collections.unmodifiableList(mutable);
        var snapshot = List.copyOf(view);
        mutable.add("C");
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        // Không copy sâu phần tử mutable.
        var originalNote = new Note("old");
        var noteCopy = List.copyOf(List.of(originalNote));
        originalNote.text = "new";
        System.out.println("shallowElement=" + noteCopy.get(0).text);

        // copyOf lấy thứ tự theo iterator của Collection nguồn.
        var ordered = new LinkedHashSet<>(List.of("Z", "A"));
        var orderedCopy = List.copyOf(ordered);
        System.out.println("fromSet=" + orderedCopy);

        try {
            List.copyOf(java.util.Arrays.asList("ok", null));
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        try {
            copied.add("X");
        } catch (UnsupportedOperationException expected) {
            System.out.println("addRejected=true");
        }
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 ListCopyReuseDemo.java
java ListCopyReuseDemo
```

**Stdout chính xác:**

```text
sameContent=true
snapshot=[A, B]
view=[A, B, C]
shallowElement=new
fromSet=[Z, A]
nullRejected=true
addRejected=true
```

Giải thích:

1. `source.equals(copied)` đúng vì danh sách có cùng nội dung và thứ tự. Chương trình **cố ý không in `source == copied`** vì identity không được API bảo đảm.
2. `snapshot` giữ `[A, B]` sau khi backing list thêm `C`; `view` nhìn thấy `[A, B, C]`. Đây là minh chứng về sự khác nhau giữa copy độc lập cấu trúc và unmodifiable view.
3. `shallowElement=new` vì object `Note` được chia sẻ qua tham chiếu phần tử, không được deep-copy.
4. `fromSet=[Z, A]` do `LinkedHashSet` của ví dụ có thứ tự duyệt được quy định theo thứ tự thêm.
5. `List.copyOf` từ chối `null` và kết quả không cho gọi `add`.

Chương trình chỉ sử dụng API Java SE còn hiệu lực và các cú pháp chính thức, không cần preview feature.

## 10. Lựa chọn API theo yêu cầu thực tế

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Danh sách hằng, không có `null` | `List.of(...)` | Tạo trực tiếp unmodifiable List |
| Trả snapshot không sửa được từ collection mutable | `List.copyOf(source)` | Tách cấu trúc kết quả khỏi những lần sửa nguồn sau đó |
| Chuẩn hóa một List vốn đã unmodifiable | `List.copyOf(source)` | Đảm bảo hợp đồng output; triển khai có thể tối ưu tái sử dụng |
| View không sửa được nhưng phản ánh thay đổi của nguồn | `Collections.unmodifiableList(source)` | Wrapper view backing bởi nguồn; không phải snapshot |
| Danh sách cần thêm/xóa phần tử | `new ArrayList<>(source)` | Chủ động tạo danh sách có thể thay đổi |
| Cần giữ bất biến cả trạng thái phần tử | Copy/biến đổi từng phần tử sang kiểu immutable thích hợp, rồi `List.copyOf` | `copyOf` không thực hiện deep copy |
| Cần một object có identity riêng cho đồng bộ | Object/lock được thiết kế riêng | `List.copyOf` không phải công cụ tạo identity |

Ví dụ khi trả kết quả cho nơi khác:

```java
public java.util.List<String> getSnapshot(java.util.Collection<String> source) {
    return java.util.List.copyOf(source);
}
```

Đây là một **phương thức Java hợp lệ trong một lớp**; chữ ký `List<String>` diễn đạt điều người dùng API được phép phụ thuộc. Nơi gọi không phải và không nên biết kết quả được tái sử dụng hay được cấp phát mới.

### Có nên lo tối ưu cấp phát thủ công?

Nếu nguồn đã không sửa được, dùng `List.copyOf(source)` có thể có lợi khi API muốn chuẩn hóa kết quả mà không nhất thiết sao chép dữ liệu. Tuy nhiên, **đừng tuyên bố số lần cấp phát, độ phức tạp thời gian hay hiệu quả bộ nhớ cụ thể trên mọi JDK** khi chưa có yêu cầu hiệu năng và phép đo đáng tin trên runtime mục tiêu.

Đối với API công khai, ưu tiên đúng **hợp đồng nội dung, tính không sửa được, quy tắc `null` và chia sẻ reference phần tử**; mọi tối ưu bên trong là quyền của nhà triển khai Java.

## 11. Các lỗi tư duy phổ biến

**Lỗi 1: “Tên là `copyOf`, vậy chắc chắn `result != source`.”**  
Sai. `copyOf` có thể tái sử dụng danh sách nguồn phù hợp. Kiểm tra bằng `equals` hoặc dữ liệu mong muốn thay vì so tham chiếu.

**Lỗi 2: “`result == source` đúng trên máy tôi, vậy luôn đúng.”**  
Sai. Ghi chú tối ưu không phải hợp đồng identity. Kết quả `==` không nên quyết định nghiệp vụ hay test.

**Lỗi 3: “Bất cứ List nào không gọi được `add` đều có thể tái sử dụng trực tiếp.”**  
Sai. `Collections.unmodifiableList(mutable)` là view backing bởi danh sách mutable; `List.copyOf` phải đảm bảo kết quả không phản ánh sửa đổi của nguồn sau khi copy.

**Lỗi 4: “`copyOf` tạo bản sao sâu, nên thay đổi phần tử không thấy.”**  
Sai. Nó chia sẻ tham chiếu phần tử; muốn bất biến sâu cần thiết kế riêng.

**Lỗi 5: “`copyOf` tự cho phép phần tử `null` vì đầu vào là List.”**  
Sai. Nguồn hoặc phần tử `null` gây `NullPointerException`.

**Lỗi 6: “`var` suy ra class triển khai của `List.copyOf`.”**  
Sai. Kiểu tĩnh của lời gọi là `List<E>`; `var` nhận đúng kiểu đó, không phải một lớp nội bộ cụ thể của JDK.

**Lỗi 7: “`List.copyOf` từ Set luôn trả List theo thứ tự tôi viết literal Set.”**  
Sai. Nó giữ thứ tự **iterator thực tế của nguồn**; nếu nguồn không bảo đảm thứ tự, kết quả cũng không hứa một thứ tự cố định giữa các lần gọi.

**Lỗi 8: “Có `copyOf` là an toàn khi nguồn đang bị sửa đồng thời.”**  
Sai. API không biến việc duyệt collection đồng thời với sửa đổi thành snapshot nguyên tử; cần kiểm soát concurrency của nguồn.

## 12. Bài tập tự kiểm tra

**Câu 1.** Vì sao `List.copyOf(List.of("A"))` có thể không cần tạo một object List mới?  
**Đáp án:** Nguồn vốn không sửa được và đáp ứng hợp đồng của kết quả. Có thể tái sử dụng nhưng API không bảo đảm identity.

**Câu 2.** `var a = List.of("A"); var b = List.copyOf(a);` — có nên assert `a == b` không?  
**Đáp án:** Không. Đó là kiểm tra identity mà factory không bảo đảm. Nên assert `a.equals(b)` và hành vi không sửa được nếu cần.

**Câu 3.** `var view = Collections.unmodifiableList(mutable); var copy = List.copyOf(view);`; sau đó thêm phần tử vào `mutable`. `copy` có thấy phần tử mới không?  
**Đáp án:** Không. `copyOf` phải bảo toàn cấu trúc kết quả khỏi sửa đổi nguồn sau khi copy; `view` thì có thể phản ánh vì là wrapper backing bởi nguồn.

**Câu 4.** `List.copyOf` có tự clone các đối tượng mutable đang là phần tử không?  
**Đáp án:** Không. Kết quả chứa các reference đến phần tử; thay đổi trạng thái object có thể nhìn thấy ở cả nguồn và kết quả.

**Câu 5.** `List.copyOf(Arrays.asList("A", null))` có trả về một List mới không?  
**Đáp án:** Không. Lời gọi ném `NullPointerException` vì `copyOf` không cho phép phần tử `null`.

**Câu 6.** `var result = List.copyOf(List.of("X"));` có kiểu tĩnh gì?  
**Đáp án:** `List<String>`. `var` suy ra kiểu từ generic method; không suy ra tên lớp triển khai nội bộ.

## 13. Ghi nhớ

- **`List.copyOf` (Java 10+)** tạo unmodifiable List chứa các phần tử theo thứ tự duyệt của nguồn.
- Nếu nguồn là một **unmodifiable List phù hợp**, Java thường có thể **tái sử dụng** nó; điều này **không** hứa kết quả và nguồn luôn là cùng một tham chiếu.
- Các kết quả `List.copyOf` là **value-based**: không dùng identity để so sánh nội dung, đồng bộ hay xác nhận số object đã cấp phát.
- Nếu nguồn là mutable collection hoặc mutable-backed view, kết quả `copyOf` không được phản ánh sửa đổi cấu trúc nguồn **sau** khi tạo.
- `Collections.unmodifiableList` là **view**, không giống snapshot `copyOf`.
- `copyOf` **không deep-copy** phần tử, từ chối `null`, và không tự đồng bộ hóa khi nguồn bị sửa đồng thời.
- Dùng `equals`/`hashCode`, các phương thức `List` và hợp đồng nội dung; tránh phụ thuộc tên class nội bộ hoặc kết quả `==`.

## Tài liệu chính thức còn áp dụng

- Java SE 26 — `List.copyOf`: hợp đồng kết quả, quy tắc `null`, ghi chú về khả năng tái sử dụng unmodifiable List, value-based instances: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- Java SE 26 — *Creating Unmodifiable Lists, Sets, and Maps*: so sánh `copyOf`, snapshot và unmodifiable view: https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html
- Java SE 26 — `Collections.unmodifiableList`: view được backing bởi nguồn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)
- OpenJDK JEP 269 — Convenience Factory Methods for Collections: https://openjdk.org/jeps/269
