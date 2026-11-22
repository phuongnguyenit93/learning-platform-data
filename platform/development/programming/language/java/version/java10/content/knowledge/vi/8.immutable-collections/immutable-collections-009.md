# Giới hạn bảo đảm về lớp triển khai và định danh đối tượng của collection chỉ đọc (Java 10+)

## 1. Vì sao chủ đề này quan trọng?

Java cung cấp các factory method tạo collection **không thể sửa qua API của collection** (*unmodifiable collection*):

```java
var names = java.util.List.of("An", "Binh");
var roles = java.util.Set.of("USER", "ADMIN");
var scores = java.util.Map.of("An", 9, "Binh", 8);
```

Các phương thức `List.of`, `Set.of`, `Map.of` đã có từ Java 9. Từ **Java 10**, có thêm `List.copyOf`, `Set.copyOf` và `Map.copyOf` để tạo collection không sửa được từ collection/map đầu vào. Trong cùng giai đoạn, Java 10 bổ sung `var` cho biến cục bộ, nên những cách viết như `var names = List.of(...)` thường gặp.

Điều dễ nhầm là một collection có hành vi *unmodifiable* **không đồng nghĩa** API hứa trả về một lớp triển khai cụ thể hoặc một đối tượng mới, có định danh duy nhất. Đặc tả các factory này mô tả những gì ta được phép dựa vào:

- **Có bảo đảm:** nội dung và hợp đồng giao diện tương ứng (`List`, `Set`, `Map`); các thao tác thay đổi collection được chỉ định sẽ ném `UnsupportedOperationException`; các quy tắc về `null`, phần tử trùng và thứ tự tùy loại.
- **Không bảo đảm:** lớp nội bộ cụ thể dùng để lưu dữ liệu; collection của hai lần gọi có phải cùng tham chiếu hay không; mọi thao tác dùng **định danh đối tượng** (identity) có ý nghĩa ổn định.
- **Không tự suy ra:** collection không thể sửa cấu trúc thì các đối tượng **bên trong** cũng bất biến, hay có thể dùng chính collection làm khóa đồng bộ đáng tin cậy.

Bài này tập trung vào **giới hạn của hợp đồng API**, cách sử dụng đúng các collection không sửa được và cách tránh mã phụ thuộc vào chi tiết triển khai của JDK.

## 2. Có thể dựa vào những bảo đảm nào?

| API tạo collection | Bảo đảm chính về nội dung | Những thứ không được giả định |
| --- | --- | --- |
| `List.of(...)` | Danh sách không sửa được; **thứ tự đúng theo đối số**; không nhận phần tử `null` | Lớp triển khai nội bộ, định danh tham chiếu của kết quả |
| `Set.of(...)` | Tập hợp không sửa được; không chứa `null`; phần tử trùng khi tạo gây `IllegalArgumentException` | **Thứ tự duyệt**, lớp triển khai và identity |
| `Map.of(...)` / `Map.ofEntries(...)` | Bản đồ không sửa được; không nhận khóa/giá trị `null`; khóa trùng khi tạo gây `IllegalArgumentException` | **Thứ tự duyệt entry/key**, lớp triển khai và identity |
| `List.copyOf(collection)` | Danh sách không sửa được; lấy phần tử theo **thứ tự duyệt đầu vào**; thay đổi cấu trúc đầu vào sau đó không làm danh sách kết quả đổi theo | Bắt buộc tạo một đối tượng mới, sao chép sâu phần tử, lớp triển khai |
| `Set.copyOf(collection)` | Tập hợp không sửa được; không có `null`; sửa collection đầu vào sau đó không làm kết quả đổi theo | Thứ tự duyệt; phần tử cụ thể nào được giữ khi đầu vào có các phần tử bằng nhau; bắt buộc tạo đối tượng mới |
| `Map.copyOf(map)` | Map không sửa được; không nhận khóa/giá trị `null`; sửa các ánh xạ ở map đầu vào sau đó không làm kết quả đổi theo | Thứ tự duyệt, bản sao sâu khóa/giá trị, hoặc định danh đối tượng mới |

Những đặc điểm trên là hợp đồng ổn định của Java Collections Framework hiện đại, **không phụ thuộc vào tên lớp nội bộ của một bản JDK cụ thể**.

### 2.1. Không được sửa collection qua API

```java
var list = java.util.List.of("A", "B");
// list.add("C"); // Hợp lệ ở mức cú pháp, nhưng ném UnsupportedOperationException khi chạy.
```

Các phương thức làm thay đổi cấu trúc hoặc thay phần tử như `add`, `remove`, `set` sẽ thất bại trên danh sách do `List.of` trả về. Tương tự, `Set.of` không cho thêm/xóa phần tử và `Map.of` không cho `put`, `remove` hay cập nhật ánh xạ.

**Đừng dùng việc gọi một phương thức mutator như một cách kiểm tra “đây có phải loại collection nào”**: điều đó chỉ kiểm tra hành vi của lời gọi, không xác định một lớp triển khai hay identity ổn định.

### 2.2. `null` và phần tử/khóa trùng

```java
// List.of("A", null);          // Ném NullPointerException.
// Set.of("A", "A");            // Ném IllegalArgumentException.
// Map.of("x", 1, "x", 2);      // Ném IllegalArgumentException vì trùng khóa.
// Map.of("x", null);           // Ném NullPointerException.
```

`List.of("A", "A")` lại **hợp lệ**, vì `List` cho phép phần tử trùng. Với `Set.copyOf` từ collection có phần tử trùng, kết quả là một set không trùng; nếu có nhiều đối tượng bằng nhau, **không được dựa vào việc đối tượng cụ thể nào sẽ được giữ**. Đây là quy tắc khác với `Set.of`, vốn từ chối các đối số trùng.

### 2.3. Thứ tự có bảo đảm khác nhau

```java
var list = java.util.List.of("A", "B", "C");
System.out.println(list); // [A, B, C], thứ tự do List bảo đảm
```

Với `Set.of("A", "B", "C")` hoặc `Map.of("A", 1, "B", 2)`, **thứ tự duyệt không được đặc tả** và có thể thay đổi giữa lần chạy, phiên bản JDK hoặc cách cài đặt. Không viết test giả định `Set.of` luôn duyệt theo đúng thứ tự đối số.

Nếu cần thứ tự, hãy chọn cấu trúc hoặc bản sao có **hợp đồng thứ tự được quy định rõ**, ví dụ sắp xếp kết quả bằng `List` hoặc dùng collection phù hợp với yêu cầu thứ tự; đừng suy từ thứ tự mình nhìn thấy trên một máy.

## 3. Không có bảo đảm về **lớp triển khai cụ thể**

Phương thức khai báo trả về giao diện:

```java
java.util.List<String> names = java.util.List.of("An", "Binh");
```

Hợp đồng mà lập trình viên nhận được là **`List<String>` không sửa được** cùng các đặc điểm được tài liệu mô tả. JDK có thể dùng các lớp nội bộ khác nhau dựa trên số phần tử, tối ưu bộ nhớ hoặc phiên bản triển khai. Do đó:

- Không ép sang `ArrayList`, `LinkedList` hay một lớp nội bộ mà bạn thấy trong debugger.
- Không so sánh chuỗi từ `getClass().getName()` với một tên class JDK cụ thể để quyết định logic nghiệp vụ.
- Không giả định collection của một, hai hoặc nhiều phần tử phải có cùng tên lớp nội bộ.
- Không dùng reflection để xây dựng đối tượng của lớp nội bộ này hoặc phụ thuộc cấu trúc trường private của nó.

Ví dụ cố ý minh họa cách suy nghĩ **không an toàn**:

```java
// Không nên viết:
// boolean isExpected = list.getClass().getName()
//         .equals("java.util.ImmutableCollections$ListN");
// var arrayList = (java.util.ArrayList<String>) java.util.List.of("A");
```

Dòng thứ nhất phụ thuộc chi tiết nội bộ; dòng thứ hai ép kiểu không đúng hợp đồng và có thể thất bại lúc chạy. Tên `ImmutableCollections$ListN` ở đây chỉ là **ví dụ tên triển khai nội bộ từng thấy trong một JDK**, không phải tên lớp được API bảo đảm hay phần mà ứng dụng nên sử dụng.

Cách đúng là làm việc qua **giao diện** và phương thức chuẩn:

```java
java.util.List<String> names = java.util.List.of("A", "B");
System.out.println(names.size());   // 2
System.out.println(names.get(0));  // A
```

Với `var`, quy tắc vẫn như vậy:

```java
var names = java.util.List.of("A", "B"); // Kiểu tĩnh List<String>
```

`var` nhận **kiểu trả về tĩnh `List<String>`** của factory method. Nó **không** biến khai báo thành kiểu class thực tế mà `getClass()` có thể quan sát tại runtime.

## 4. Không có bảo đảm về **định danh đối tượng** (identity)

Các collection tạo bởi `List.of`/`List.copyOf`, `Set.of`/`Set.copyOf` và `Map.of`/`Map.copyOf` thuộc nhóm **value-based instances** theo tài liệu API.

Điều đó có nghĩa người dùng phải coi những instance **bằng nhau về giá trị** là có thể thay thế cho nhau. Nhà cung cấp JDK có quyền **tạo mới hoặc tái sử dụng** đối tượng cho kết quả factory. Vì vậy, mã không được phụ thuộc vào việc hai lời gọi:

```java
var left  = java.util.List.of("A", "B");
var right = java.util.List.of("A", "B");
```

trả về **cùng một tham chiếu** hay **hai tham chiếu khác nhau**. Các biểu thức `left == right` và `left != right` đều là các phép so sánh tham chiếu hợp lệ về cú pháp, nhưng **giá trị Boolean của chúng không phải một lời hứa ổn định của API factory**. Chúng có thể khác trên cách triển khai khác; không viết kiểm thử hoặc điều kiện nghiệp vụ dựa trên kết quả đó.

### 4.1. So sánh nội dung bằng `equals`

Với collection:

```java
var a = java.util.List.of("A", "B");
var b = java.util.List.of("A", "B");
System.out.println(a.equals(b)); // true
```

`List.equals` so sánh **theo thứ tự các phần tử**. Với `Set.equals`, thứ tự không phải yếu tố quyết định; với `Map.equals`, các ánh xạ khóa–giá trị quyết định tính bằng nhau. Ví dụ:

```java
var setA = java.util.Set.of("red", "blue");
var setB = java.util.Set.of("blue", "red");
System.out.println(setA.equals(setB)); // true

var mapA = java.util.Map.of("x", 1, "y", 2);
var mapB = java.util.Map.of("y", 2, "x", 1);
System.out.println(mapA.equals(mapB)); // true
```

`hashCode()` theo hợp đồng collection cũng dựa trên nội dung phù hợp với `equals`. **Đừng thay bằng `System.identityHashCode`** khi ý định là so sánh hoặc phân nhóm các collection có nội dung tương đương.

### 4.2. Không dùng value-based collection làm khóa đồng bộ

Vì identity không được bảo đảm, hãy tránh:

```java
// Không nên dùng làm thiết kế đồng bộ:
var items = java.util.List.of("A", "B");
synchronized (items) {
    // Mã giả định identity của items là lock ổn định.
}
```

Dù cú pháp `synchronized` hiện có thể biên dịch, tài liệu API cảnh báo **không dùng value-based instances để đồng bộ**, vì hành vi có thể không đoán trước và có thể thay đổi trong tương lai.

Thay vào đó, dùng một lock có identity được kiểm soát riêng:

```java
final Object lock = new Object();
var items = java.util.List.of("A", "B");

synchronized (lock) {
    System.out.println(items.size());
}
```

Đây là **đoạn minh họa cú pháp** đặt trong phương thức; trong ứng dụng đa luồng, lock phải được chia sẻ đúng giữa các luồng cần đồng bộ, không được tùy tiện tạo lock mới ở mỗi lần truy cập. Nếu chỉ đọc dữ liệu bất biến, nhiều tình huống **không cần** synchronized; việc an toàn giữa các luồng còn phụ thuộc cách công bố dữ liệu và trạng thái của các phần tử bên trong.

### 4.3. Không dùng identity làm hợp đồng dữ liệu

Với các value-based collection, nên tránh lấy kết quả của `==`, `System.identityHashCode`, cơ chế gắn metadata theo **identity** hay giả định giá trị identity bất biến qua tái sử dụng/khôi phục làm căn cứ nghiệp vụ. Ví dụ, nếu muốn một key đại diện cho danh sách mặt hàng, hãy dùng `List.equals`/`hashCode` hoặc một khóa nghiệp vụ riêng, không dùng địa chỉ hay định danh tham chiếu của object.

**Phân biệt:** nhận xét này dành cho **các collection trả về từ những factory được mô tả là value-based**. Không kết luận rằng mọi instance `ArrayList` hoặc mọi view tạo bởi `Collections.unmodifiableList` đều có cùng đặc tính identity này.

## 5. `copyOf` không bảo đảm cấp phát đối tượng mới

Các phương thức `copyOf` không đồng nghĩa với lời hứa “mỗi lần gọi luôn trả về một object khác”:

```java
var original = java.util.List.of("A", "B");
var copied = java.util.List.copyOf(original);
```

Vì `original` vốn là danh sách không sửa được, `List.copyOf` **được phép tái sử dụng instance phù hợp**. Không dựa vào `original == copied` hoặc `original != copied`; API bảo đảm tính chất và nội dung của kết quả, không bảo đảm identity.

Tương tự, `Set.copyOf` và `Map.copyOf` có thể tối ưu không tạo bản sao mới khi đầu vào đã phù hợp. Lý do để dùng `copyOf` là thiết lập **hợp đồng không sửa được và tách cấu trúc dữ liệu đầu ra khỏi nguồn có thể thay đổi**, chứ không phải ép phát sinh identity mới.

### 5.1. Bản sao cấu trúc từ collection có thể thay đổi

```java
var source = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var snapshot = java.util.List.copyOf(source);
source.add("C");

System.out.println(snapshot); // [A, B]
System.out.println(source);   // [A, B, C]
```

`List.copyOf(source)` lấy các phần tử tại thời điểm tạo kết quả. Khi thay đổi cấu trúc `source` sau đó, danh sách `snapshot` không phản ánh thao tác `add("C")`. `Map.copyOf` cũng có tính chất tương tự với việc sửa ánh xạ của map đầu vào.

### 5.2. Khác với view không sửa được từ `Collections.unmodifiableList`

```java
var source = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var view = java.util.Collections.unmodifiableList(source);
source.add("C");

System.out.println(view); // [A, B, C]
```

`Collections.unmodifiableList(source)` tạo **view không sửa được nhưng được backing bởi list gốc**. Không thể `view.add(...)`, song nếu một bên khác vẫn sửa `source`, nội dung quan sát qua `view` sẽ đổi. Ngược lại, `List.copyOf(source)` lấy một kết quả không bị cập nhật theo các lần sửa cấu trúc của `source` về sau.

| Cách dùng | Sửa qua biến kết quả | Sửa list nguồn sau đó | Đảm bảo object kết quả mới mỗi lần? |
| --- | --- | --- | --- |
| `List.of("A", "B")` | Không | Không có list nguồn có thể thay đổi được truyền vào | Không |
| `List.copyOf(source)` | Không | Không ảnh hưởng cấu trúc danh sách kết quả | Không |
| `Collections.unmodifiableList(source)` | Không | Có thể phản ánh thay đổi của source | Cần xem hợp đồng wrapper riêng, không dùng nó để suy ra quy tắc identity của `List.of` |

Không đánh đồng **unmodifiable view** với **snapshot không sửa được** trong thiết kế API.

## 6. Collection không sửa được vẫn có thể chứa phần tử thay đổi được

Tính chất *unmodifiable* nói về **cấu trúc collection và phép thay thế tham chiếu phần tử**, không bảo đảm các object được chứa là bất biến.

```java
class Note {
    String text;

    Note(String text) {
        this.text = text;
    }
}

var note = new Note("ban dau");
var notes = java.util.List.of(note);
note.text = "da sua";

System.out.println(notes.get(0).text); // da sua
```

Đây là **đoạn minh họa** với lớp `Note` cần được khai báo trong lớp bao ngoài hoặc một vị trí Java hợp lệ; ví dụ hoàn chỉnh ở phần tiếp theo có chương trình biên dịch độc lập.

`notes.add(...)` bị cấm, nhưng `notes.get(0)` vẫn trỏ tới object `note` ban đầu, có thể thay đổi trường `text`. Điều tương tự áp dụng cho **khóa/giá trị map** hoặc **phần tử set**. Nếu một phần tử set hoặc khóa map có `equals`/`hashCode` phụ thuộc trạng thái thay đổi, việc sửa trạng thái đó có thể phá vỡ các giả định tra cứu hoặc tính nhất quán của collection.

Khi cần dữ liệu bất biến về mặt logic, hãy dùng các phần tử bất biến phù hợp (ví dụ `String` hoặc một object có trạng thái không thể thay đổi), hoặc tự sao chép sâu theo yêu cầu nghiệp vụ. `copyOf` **không phải phép deep copy**.

## 7. Chương trình Java 17+ hoàn chỉnh và stdout đã kiểm tra

Lưu mã dưới đây vào tệp **`UnmodifiableContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class UnmodifiableContractDemo {
    static final class Note {
        String text;

        Note(String text) {
            this.text = text;
        }
    }

    public static void main(String[] args) {
        var listA = List.of("A", "B");
        var listB = List.of("A", "B");
        var setA = Set.of("red", "blue");
        var setB = Set.of("blue", "red");
        var mapA = Map.of("x", 1, "y", 2);
        var mapB = Map.of("y", 2, "x", 1);

        System.out.println("listEquals=" + listA.equals(listB));
        System.out.println("setEquals=" + setA.equals(setB));
        System.out.println("mapEquals=" + mapA.equals(mapB));

        var source = new ArrayList<>(List.of("A", "B"));
        var snapshot = List.copyOf(source);
        var view = Collections.unmodifiableList(source);
        source.add("C");
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        var note = new Note("v1");
        var notes = List.of(note);
        note.text = "v2";
        System.out.println("elementAfter=" + notes.get(0).text);

        try {
            snapshot.add("D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("addRejected=true");
        }
        try {
            Set.of("same", "same");
        } catch (IllegalArgumentException expected) {
            System.out.println("duplicateRejected=true");
        }
        try {
            List.of("ok", null);
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 UnmodifiableContractDemo.java
java UnmodifiableContractDemo
```

**Kết quả chính xác**:

```text
listEquals=true
setEquals=true
mapEquals=true
snapshot=[A, B]
view=[A, B, C]
elementAfter=v2
addRejected=true
duplicateRejected=true
nullRejected=true
```

Diễn giải:

1. `List.equals` kiểm tra nội dung theo thứ tự. `Set.equals` và `Map.equals` so sánh phần tử/ánh xạ không phụ thuộc thứ tự duyệt. Vì vậy ba dòng đầu đều là `true`.
2. `snapshot` không đổi theo `source.add("C")`, trong khi `view` vẫn nhìn thấy `C` vì được backing bởi `source`.
3. Phần tử `Note` vẫn thay đổi được dù đang ở trong `List.of(note)`, nên dòng `elementAfter` in `v2`.
4. Gọi `add` trên danh sách `copyOf` ném `UnsupportedOperationException`; truyền hai phần tử trùng vào `Set.of` ném `IllegalArgumentException`; truyền `null` vào `List.of` ném `NullPointerException`.

Chương trình **cố ý không in `getClass().getName()` hay kết quả `listA == listB`**, vì đó không phải giá trị mà tài liệu API bảo đảm nhất quán giữa các bản JDK.

## 8. Các tình huống triển khai thực tế

### 8.1. Trả về một danh sách chỉ đọc qua API

```java
public java.util.List<String> getSupportedLanguages() {
    return java.util.List.of("Java", "Kotlin");
}
```

Chữ ký `List<String>` cho người gọi một hợp đồng ổn định. Người gọi có thể duyệt, đọc phần tử và so sánh bằng `equals`; không được ép loại triển khai cụ thể hoặc mặc định có thể thêm phần tử.

Nếu danh sách đầu vào do nơi khác sở hữu và vẫn được sửa:

```java
public java.util.List<String> snapshotOf(java.util.List<String> source) {
    return java.util.List.copyOf(source);
}
```

Đoạn trên tạo danh sách không sửa được có **cấu trúc độc lập với các lần sửa tiếp theo của `source`**. Cần thỏa yêu cầu không chứa `null`; nếu element là object mutable và cần bất biến sâu, phải thêm cơ chế riêng.

### 8.2. Khi cần tự sửa collection

Nếu muốn bắt đầu từ dữ liệu không sửa được nhưng vẫn có thể `add`/`remove`, tạo một collection modifiable phù hợp:

```java
var editable = new java.util.ArrayList<>(
        java.util.List.of("A", "B")
);
editable.add("C");
```

Ở đây ta **chủ động** chọn `ArrayList` khi hành vi thay đổi là yêu cầu thiết kế. Không cast kết quả của `List.of` thành `ArrayList`.

### 8.3. Khi cần theo dõi thay đổi của nguồn

Nếu mục đích là một **view** của collection gốc và chấp nhận nó phản ánh thay đổi bên ngoài, `Collections.unmodifiableList(source)` là API có hợp đồng phù hợp. Nhưng đừng dùng view đó như bằng chứng snapshot bất biến; thay đổi từ reference gốc vẫn thấy được.

### 8.4. Khi cần khóa hoặc định danh ổn định

Dùng một object khóa do ứng dụng quản lý (ví dụ `private final Object lock = new Object();`) hoặc một ID nghiệp vụ rõ ràng. Không dùng identity của collection value-based để làm cơ chế đồng bộ, khóa định danh hay trạng thái lâu dài.

## 9. Những lỗi suy luận dễ gặp

**Lỗi 1 — Kiểm tra tên lớp nội bộ.**  
Thấy `getClass()` in một tên trong package JDK rồi hard-code tên ấy vào nghiệp vụ hoặc test. **Sửa:** kiểm tra theo giao diện và hành vi API có đặc tả.

**Lỗi 2 — Dùng `==` để so nội dung.**  
Hai `List.of("A", "B")` có thể cùng hoặc khác reference tùy implementation. **Sửa:** `equals` khi muốn so giá trị; lưu ý `List` có thứ tự, `Set` và `Map` so theo thành viên/ánh xạ.

**Lỗi 3 — Cho rằng `copyOf` luôn tạo object mới.**  
Một nguồn đã unmodifiable có thể được tái sử dụng. **Sửa:** dựa vào hợp đồng nội dung/snapshot thay vì identity.

**Lỗi 4 — Dùng `synchronized(collectionValueBased)`.**  
Không được bảo đảm identity phù hợp làm lock. **Sửa:** dùng một lock ổn định độc lập hoặc thiết kế concurrency phù hợp.

**Lỗi 5 — Cho rằng `unmodifiable` đồng nghĩa với deep immutable.**  
Mã khác vẫn có thể thay đổi trạng thái của object bên trong. **Sửa:** dùng phần tử bất biến hoặc deep copy có chủ đích.

**Lỗi 6 — Dựa vào thứ tự duyệt `Set.of`/`Map.of`.**  
Thứ tự là unspecified. **Sửa:** sắp xếp trước khi hiển thị/so sánh theo vị trí, hoặc chọn một kiểu có hợp đồng thứ tự phù hợp.

**Lỗi 7 — Nhầm `List.copyOf` với `Collections.unmodifiableList`.**  
Một cách tạo kết quả cấu trúc không thay đổi theo sửa nguồn; cách kia là view được backing bởi nguồn. **Sửa:** chọn đúng API cho snapshot hoặc view.

**Lỗi 8 — Nhầm `var` với kiểu triển khai thật.**  
`var list = List.of(...)` có kiểu tĩnh `List<E>`, không khiến trình biên dịch suy ra lớp private của JDK. **Sửa:** phân biệt kiểu tĩnh biểu thức với lớp runtime.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Hai lời gọi `List.of("A")` có bắt buộc trả hai object khác nhau không?  
**Đáp án:** Không. Factory có thể tạo mới hoặc tái sử dụng object. Không dùng `==` để dự đoán kết quả theo hợp đồng API.

**Câu 2.** Tại sao `List.of("A", "B")` có thể dùng an toàn với `get(0)` nhưng không nên ép kiểu sang `ArrayList`?  
**Đáp án:** `get(0)` thuộc hợp đồng của `List`, thứ tự danh sách được bảo đảm; lớp triển khai cụ thể không được API hứa hẹn.

**Câu 3.** `var items = List.copyOf(source);` có bảo đảm `items != source` không?  
**Đáp án:** Không. `copyOf` có thể tái sử dụng đầu vào đã không sửa được. Bảo đảm quan trọng là kết quả không sửa được và thay đổi cấu trúc nguồn sau đó không làm kết quả đổi theo.

**Câu 4.** Vì sao `Collections.unmodifiableList(source)` vẫn có thể thay đổi nội dung nhìn thấy?  
**Đáp án:** Nó là một view được backing bởi nguồn. Người khác thay đổi `source` thì view quan sát được những thay đổi đó.

**Câu 5.** `Set.of("B", "A")` có bắt buộc duyệt theo thứ tự `B` rồi `A` không?  
**Đáp án:** Không. Thứ tự duyệt của set được tạo bằng `Set.of` không được đặc tả.

**Câu 6.** Một `List.of(note)` có bất biến hoàn toàn nếu `note` là object mutable không?  
**Đáp án:** Không. Ta không thay thế hay xóa phần tử bằng API `List` được, nhưng vẫn có thể thay đổi trạng thái object `note` nếu còn reference và thiết kế cho phép.

## 11. Ghi nhớ

1. `List.of`, `Set.of` và `Map.of` là factory tạo **unmodifiable collection**; các phương thức `copyOf` tương ứng có từ Java 10.
2. **Lớp triển khai và identity của kết quả không được bảo đảm.** Factory có thể tái sử dụng instance hoặc chọn lớp nội bộ theo cách tối ưu.
3. Những collection này là **value-based**: so sánh nội dung bằng `equals`/`hashCode`, không dựa vào `==`, identity hash code hay synchronization trên chính object.
4. `List` bảo đảm thứ tự phần tử; `Set.of`/`Map.of` **không bảo đảm thứ tự duyệt**. Các quy tắc `null` và phần tử/khóa trùng cũng khác nhau theo loại.
5. `copyOf` tạo kết quả unmodifiable có cấu trúc không đổi theo sửa nguồn; `Collections.unmodifiableList` là view phản ánh sửa nguồn.
6. **Unmodifiable không tự động là deep immutable.** Phần tử/khóa/giá trị mutable đòi hỏi thiết kế riêng.
7. `var` suy ra kiểu tĩnh từ biểu thức, thường là `List<E>`/`Set<E>`/`Map<K,V>`, chứ không làm lộ class private của JDK.

## Tài liệu chính thức còn áp dụng

- Java SE 26 — `List`: mục *Unmodifiable Lists*, `of` và `copyOf`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html
- Java SE 26 — `Set`: mục *Unmodifiable Sets*, `of` và `copyOf`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html
- Java SE 26 — `Map`: mục *Unmodifiable Maps*, `of`, `ofEntries` và `copyOf`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html
- Java SE 25 — `Collections`: `unmodifiableList` là view được backing bởi list nguồn: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html
- Java SE 25 — `Collection`: *Unmodifiable Collections* và giới hạn bất biến sâu: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html
- OpenJDK JEP 269 — Convenience Factory Methods for Collections: https://openjdk.org/jeps/269
- OpenJDK JEP 286 — Local-Variable Type Inference: https://openjdk.org/jeps/286
