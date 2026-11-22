# Kiểu an toàn động với Collections.checkedCollection và các biến thể

Generics kiểm tra kiểu khi biên dịch, nhưng dữ liệu vẫn có thể đi qua một ranh giới không giữ được đầy đủ thông tin kiểu, chẳng hạn một API nhận collection không có đối số kiểu hoặc một thao tác ép kiểu unchecked.

`Collections.checkedCollection` và các biến thể tạo **chế độ xem có kiểm tra kiểu lúc chạy**. Khi thêm một giá trị sai kiểu qua chế độ xem đó, lỗi được phát hiện ngay tại thao tác ghi thay vì để dữ liệu sai đi sâu rồi mới lỗi khi đọc.

Đây là một công cụ bổ sung cho generics, đặc biệt hữu ích để đặt kiểm tra tại ranh giới tích hợp hoặc khoanh vùng nguồn gây ô nhiễm kiểu. Không nên bỏ generics rồi xem lớp bao động là sự thay thế toàn bộ.

## 1. Vấn đề: lỗi có thể xuất hiện xa nơi ghi dữ liệu sai

Đoạn minh họa:

```java
List<String> names = new ArrayList<>();
```

Qua biến `names` có kiểu đầy đủ, `names.add(42)` bị từ chối khi biên dịch.

Nhưng nếu một đường truy cập raw hoặc unchecked ghi được số 42 vào đối tượng danh sách, mã đọc sau đó có thể lỗi:

```java
String name = names.get(0);
```

Lỗi tại dòng đọc không nhất thiết là nơi tạo ra dữ liệu sai. Một lớp bao checked giúp đưa điểm phát hiện về thao tác ghi đi qua chính nó.

Các đoạn trên giả định đã import các kiểu collection và đặt trong một phương thức. Raw type chỉ được dùng có chủ đích trong thí nghiệm bên dưới để mô phỏng ranh giới mất an toàn kiểu; đó không phải cách viết API mới được khuyến khích.

## 2. Lớp bao kiểm tra bằng Class token

Chữ ký chính:

```java
public static <E> Collection<E> checkedCollection(
        Collection<E> collection, Class<E> type)
```

Đây là mô tả API, không phải khai báo hoàn chỉnh để đặt nguyên vào lớp.

Ví dụ sử dụng:

```java
Collection<String> names = Collections.checkedCollection(
        new ArrayList<>(), String.class);
```

`String.class` là đối tượng mô tả kiểu được dùng để kiểm tra ở thời gian chạy, thường gọi là `Class token`.

Lớp bao không tạo một collection dữ liệu độc lập. Các thao tác đọc và ghi hợp lệ được chuyển tới collection nền. Kiểm tra kiểu được bổ sung trước những thao tác có thể đưa phần tử vào thông qua chế độ xem.

Với token một lớp cha, giá trị thuộc lớp con phù hợp vẫn được chấp nhận:

```java
Collection<Number> numbers = Collections.checkedCollection(
        new ArrayList<>(), Number.class);
numbers.add(1);      // Integer là Number.
numbers.add(2.5);    // Double là Number.
```

Kiểm tra không đòi lớp thời gian chạy phải bằng chính xác `Number.class`; nó đòi giá trị thuộc kiểu được chấp nhận.

Với giá trị nguyên thủy qua boxing, dùng token kiểu bao như `Integer.class`. Không dùng `int.class` với kỳ vọng kiểm tra đối tượng `Integer` như một lớp tham chiếu tương ứng.

## 3. Chọn biến thể giữ đúng API cần dùng

| Factory | Chế độ xem trả về | Dữ liệu được kiểm tra |
| --- | --- | --- |
| `checkedCollection` | `Collection<E>` | Kiểu phần tử |
| `checkedList` | `List<E>` | Kiểu phần tử, kể cả thao tác thay thế qua API danh sách |
| `checkedSet` | `Set<E>` | Kiểu phần tử |
| `checkedSortedSet` | `SortedSet<E>` | Kiểu phần tử |
| `checkedNavigableSet` | `NavigableSet<E>` | Kiểu phần tử |
| `checkedQueue` | `Queue<E>` | Kiểu phần tử qua API hàng đợi |
| `checkedMap` | `Map<K,V>` | Kiểu khóa và kiểu giá trị |
| `checkedSortedMap` | `SortedMap<K,V>` | Kiểu khóa và kiểu giá trị |
| `checkedNavigableMap` | `NavigableMap<K,V>` | Kiểu khóa và kiểu giá trị |

Chọn `checkedList` nếu bên sử dụng cần `get`, `set` hoặc `ListIterator`. Chỉ bọc bằng `checkedCollection` rồi ép kết quả thành `List` không phải cách giữ hợp đồng: chế độ xem `Collection` không cam kết nó là một `List`.

`checkedMap` cần hai token:

```java
Map<String, Integer> counts = Collections.checkedMap(
        new HashMap<>(), String.class, Integer.class);
```

Không thể chỉ kiểm tra kiểu giá trị rồi giả định kiểu khóa cũng đã được bảo vệ.

## 4. Chương trình kiểm chứng hoàn chỉnh

Ví dụ dùng Java 17+. Các helper raw có `@SuppressWarnings` cục bộ để mô phỏng bên gọi bỏ qua generics. Cảnh báo bị tắt ở đúng phạm vi thí nghiệm; việc tắt cảnh báo không tạo an toàn kiểu.

Lưu thành `CheckedCollectionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;

public class CheckedCollectionsDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static void rawAdd(Collection target, Object value) {
        target.add(value);
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void rawIteratorSet(List target, Object value) {
        ListIterator iterator = target.listIterator();
        iterator.next();
        iterator.set(value);
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void rawPut(Map target, Object key, Object value) {
        target.put(key, value);
    }

    public static void main(String[] args) {
        List<String> backing = new ArrayList<>();
        List<String> checked =
                Collections.checkedList(backing, String.class);
        checked.add("java");

        try {
            rawAdd(checked, 42);
        } catch (ClassCastException e) {
            System.out.println("wrong add rejected");
        }

        try {
            rawIteratorSet(checked, 99);
        } catch (ClassCastException e) {
            System.out.println("wrong iterator set rejected");
        }
        System.out.println("checked list: " + checked);

        checked.add(null);
        System.out.println("null accepted by backing list: " + checked);

        Map<String, Integer> counts = Collections.checkedMap(
                new LinkedHashMap<>(), String.class, Integer.class);
        counts.put("java", 2);
        try {
            rawPut(counts, 7, 3);
        } catch (ClassCastException e) {
            System.out.println("wrong map key rejected");
        }
        try {
            rawPut(counts, "spring", "three");
        } catch (ClassCastException e) {
            System.out.println("wrong map value rejected");
        }
        System.out.println("checked map: " + counts);

        List<String> alreadyDirty = new ArrayList<>();
        rawAdd(alreadyDirty, 100);
        List<String> lateWrapper =
                Collections.checkedList(alreadyDirty, String.class);
        System.out.println("wrapper created around existing data");
        try {
            String value = lateWrapper.get(0);
            System.out.println(value);
        } catch (ClassCastException e) {
            System.out.println("existing wrong element fails on typed read");
        }

        List<String> exposedBacking = new ArrayList<>();
        List<String> view =
                Collections.checkedList(exposedBacking, String.class);
        rawAdd(exposedBacking, 200);
        System.out.println("bypassed view size: " + view.size());
        try {
            String value = view.get(0);
            System.out.println(value);
        } catch (ClassCastException e) {
            System.out.println("backing alias bypassed the check");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 -Xlint:unchecked CheckedCollectionsDemo.java
java CheckedCollectionsDemo
```

Stdout:

```text
wrong add rejected
wrong iterator set rejected
checked list: [java]
null accepted by backing list: [java, null]
wrong map key rejected
wrong map value rejected
checked map: {java=2}
wrapper created around existing data
existing wrong element fails on typed read
bypassed view size: 1
backing alias bypassed the check
```

### Đọc những ranh giới được bảo vệ

Hai thao tác ghi sai qua `checked` đều bị chặn, kể cả `ListIterator.set`. Dữ liệu sai không được thêm hoặc thay thế qua các lời gọi ấy.

`checkedMap` kiểm tra cả khóa lẫn giá trị. Sau hai lần thử ghi sai, map vẫn chỉ có `java=2`.

Hai phần cuối thể hiện giới hạn: wrapper không quét sạch dữ liệu đã tồn tại và không thể chặn thao tác ghi trực tiếp qua tham chiếu collection nền.

Trong các lệnh đọc lỗi, kiểu khai báo `String` yêu cầu giá trị đọc được phù hợp. Wrapper không biến số đã lọt vào thành chuỗi; lỗi được phát hiện khi đọc có kiểu.

## 5. Không quét lại dữ liệu có sẵn

Lời gọi tạo chế độ xem không phải một phép xác thực toàn bộ nội dung trước đó:

```java
List<String> view = Collections.checkedList(source, String.class);
```

Đoạn này không chứng minh mọi phần tử đang nằm trong `source` đều là `String`.

Muốn đưa dữ liệu không tin cậy về một collection có kiểu rõ ràng, cần kiểm tra từng phần tử và sao chép vào một collection sạch theo chính sách của ứng dụng. Khi đó, các lỗi cũ được xử lý tại bước chuyển đổi, còn lớp checked có thể bảo vệ các lần ghi mới.

Không dùng một phép ép kiểu unchecked từ `List<?>` sang `List<String>` rồi bọc để “chứng minh” dữ liệu đã hợp lệ. Annotation tắt cảnh báo hoặc lớp bao không làm phép ép ấy trở thành một kiểm tra nội dung tự động.

## 6. Mọi đường ghi cần đi qua chế độ xem

Mô hình an toàn hơn tại ranh giới cần bảo vệ:

```java
List<String> names = Collections.checkedList(
        new ArrayList<>(), String.class);
```

Không giữ và truyền rộng rãi một tham chiếu khác tới `ArrayList` nền nếu muốn tất cả lần ghi đều được kiểm tra.

Lớp bao chỉ kiểm soát những thao tác thực hiện qua API của nó và các chế độ xem liên quan mà nó cung cấp. Nó không có quyền chặn một người đang giữ trực tiếp đối tượng nền gọi `add`.

Điều này cũng giải thích vì sao checked view không phải bản sao phòng vệ. Nếu bên khác sửa backing collection theo đường hợp lệ hoặc đi vòng, các thay đổi vẫn nhìn thấy qua view.

## 7. Null, bất biến và đồng bộ là các hợp đồng riêng

### Null

Lớp checked cho phép null nếu collection nền cho phép. Token `String.class` không đồng nghĩa với “chuỗi bắt buộc khác null”.

Trong chương trình, `ArrayList` nền nhận null, nên checked list cũng nhận. Với một triển khai nền cấm null, thao tác tương ứng vẫn có thể bị từ chối theo hợp đồng của nó.

### Khả năng sửa

Checked view không phải unmodifiable view. Thêm phần tử đúng kiểu vẫn được chuyển xuống collection nền nếu thao tác đó được hỗ trợ.

Bọc một danh sách không cho sửa bằng checked view không làm nó sửa được. Lỗi kiểu và lỗi thao tác không được hỗ trợ là các nguyên nhân khác nhau; không nên phụ thuộc vào thứ tự loại lỗi khi cùng lúc vi phạm nhiều điều kiện.

### Nhiều luồng

Checked view không tự thêm cơ chế đồng bộ. Nó không biến một `ArrayList` thành cấu trúc dùng đồng thời an toàn.

Nếu cần dùng nhiều luồng, phải chọn cơ chế đồng bộ hoặc collection đồng thời phù hợp. Ngoài kiểu, còn phải xét tính nguyên tử của chuỗi thao tác và cách duyệt.

## 8. Không kiểm tra sâu generic lồng hoặc quy tắc nghiệp vụ

Token `Class` không biểu diễn đầy đủ một kiểu như `List<String>` để kiểm tra từng phần tử bên trong. Không có cú pháp class literal `List<String>.class`.

Nếu kiểm tra với `List.class`, điều có thể kiểm tra là đối tượng đưa vào có thuộc kiểu `List` hay không. Nó không chứng minh các phần tử của danh sách ấy đều là chuỗi.

Tương tự, `checkedMap(..., String.class, List.class)` không tự xác thực cấu trúc dữ liệu lồng theo một schema đầy đủ; còn phải xử lý giới hạn generic của khai báo nếu chọn mô hình đó.

Các quy tắc như chuỗi không rỗng, số dương, khóa duy nhất theo nghiệp vụ hoặc dữ liệu đúng định dạng cũng không đến từ token kiểu. Cần kiểm tra tường minh trong API tiếp nhận dữ liệu.

## 9. Chọn đúng vai trò trong thiết kế

| Nhu cầu | Công cụ hoặc hướng xử lý |
| --- | --- |
| Ngăn sai kiểu trong mã được biên dịch đầy đủ | Generics |
| Phát hiện ghi sai kiểu tại một ranh giới lúc chạy | Checked view |
| Xác thực dữ liệu đã tồn tại | Duyệt kiểm tra và chuyển đổi/sao chép |
| Ngăn bên ngoài sửa collection | Hợp đồng unmodifiable hoặc bản sao phù hợp |
| Tách quyền sở hữu dữ liệu | Sao chép phòng vệ |
| Kiểm tra generic lồng và nghiệp vụ | Bộ xác thực có hiểu cấu trúc dữ liệu |
| Truy cập nhiều luồng | Collection/cơ chế đồng bộ thích hợp |

Checked view hữu ích nhất khi được đặt ngay tại nơi dữ liệu có thể bị ghi từ mã không bảo đảm kiểu. Nó cũng hỗ trợ tìm nguyên nhân một lỗi `ClassCastException` xuất hiện quá muộn: lớp bao có thể chuyển điểm lỗi về nơi thêm sai.

Không dùng nó như lý do để tiếp tục mở rộng raw API. Với API do mình kiểm soát, ưu tiên chữ ký generic rõ ràng và thu hẹp phạm vi unchecked.

## 10. Thực hành

1. Truyền số nguyên qua helper raw vào checked list có token `String.class`; lỗi xuất hiện lúc ghi hay khi đọc sau đó?
2. Ghi số nguyên qua raw alias trực tiếp của backing list có bị wrapper chặn không?
3. Wrapper có quét và từ chối mọi dữ liệu sai ngay khi được tạo không?
4. `Number.class` có chấp nhận một đối tượng `Integer` không?
5. Checked view có tự cấm null hoặc tự trở thành thread-safe không?
6. `List.class` có kiểm chứng được rằng một danh sách bên trong chỉ chứa String không?

Đáp án:

1. Lúc ghi qua checked view.
2. Không.
3. Không.
4. Có.
5. Không; đây là các hợp đồng riêng.
6. Không; nó không kiểm tra sâu đối số kiểu generic.

## Tài liệu đối chiếu

Xem hợp đồng [Collections.checkedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#checkedCollection(java.util.Collection,java.lang.Class)), [checkedList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)) và [checkedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#checkedMap(java.util.Map,java.lang.Class,java.lang.Class)).
